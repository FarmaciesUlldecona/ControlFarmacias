"""Piloto manual 2I para un unico documento PIO, con barreras fail-closed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))

import psycopg2  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

from src.facturas.motor_local.backend.pdfium import BackendPdfium  # noqa: E402
from src.facturas.motor_local.servicio import MotorDocumentoLocal  # noqa: E402
from src.facturas.runtime_supabase.conciliacion import conciliar_importes  # noqa: E402
from src.facturas.runtime_supabase.modelos import (  # noqa: E402
    DetalleConciliacion,
    FacturaTrabajo,
    TipoRelacionConciliacion,
)
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase  # noqa: E402
from src.supabase_client.conexion_supabase import obtener_cliente_supabase  # noqa: E402
from src.facturas.normalizador_v2.modelos import (  # noqa: E402
    AlbaranDocumental,
    EstadoValidacion,
    Evidencia,
    FacturaNormalizada,
    FechaDocumental,
    FormaPago,
    Incidencia,
    NaturalezaPrincipal,
    ResultadoControl,
    ResultadoValidacion,
    Sentido,
    Severidad,
    Tercero,
    Totales,
    TramoImpuesto,
    ValorDocumentado,
    Vencimiento,
)
from src.facturas.normalizador_v2.validadores import (  # noqa: E402
    ContextoValidacion,
    normalizar_proveedor_identidad,
    validar_factura,
)


DOCUMENTO_ID = "0387e00a-e861-48f0-88ad-9236b92078e8"
DOCUMENTO_SHA256 = "742b36450bbe8d116fd92375a6b20d457043da53b73415672a4730629c832494"
PDF = ROOT / "pruebas" / "facturas" / "documentos" / "2o_gold_standard" / "LOGISTA PHARMA VTO 29.9.26 PIO.pdf"
WORKER_NORMALIZACION = "manual-hito-2i-normalizacion"
WORKER_CONCILIACION = "manual-hito-2i-conciliacion"
TOLERANCIA = Decimal("0.0500")


def _connect(*, readonly: bool, autocommit: bool = False):
    url = os.environ.get("CONTROLFARMACIAS_SUPABASE_DB_URL", "")
    if not url:
        raise RuntimeError("CONTROLFARMACIAS_SUPABASE_DB_URL ausente")
    connection = psycopg2.connect(url, connect_timeout=10, sslmode="require")
    connection.set_session(readonly=readonly, autocommit=autocommit)
    return connection


def _evidencia(local: Any) -> Evidencia:
    ubicacion = {
        "bbox": local.bbox,
        "contexto": local.contexto,
        "fila_literal": local.fila_literal,
        "bbox_fila": local.bbox_fila,
        "tabla": local.tabla,
        "columna": local.columna,
        "sha_documento": local.sha_documento,
        "adaptador": local.adaptador,
        "version_adaptador": local.version_adaptador,
        "regla": local.regla,
        "tipo_evidencia": local.tipo_evidencia,
        "origen_autoridad": local.origen_autoridad,
    }
    return Evidencia(pagina=local.pagina, literal=local.literal, ubicacion=ubicacion)


def _documentado(item: Any, convertir=lambda value: value):
    if item is None or not isinstance(item, dict) or item.get("valor") is None:
        return None
    evidencias = [_evidencia(evidence) for evidence in item.get("evidencias", [])]
    if not evidencias:
        return None
    return ValorDocumentado(
        valor=convertir(item["valor"]),
        literal=str(item["literal"]),
        evidencia=evidencias,
    )


def _fecha(value: Any) -> FechaDocumental:
    literal = str(value)
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return FechaDocumental(literal=literal, iso=datetime.strptime(literal, pattern).date())
        except ValueError:
            pass
    return FechaDocumental(literal=literal, iso=None)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _tercero(data: dict[str, Any] | None) -> Tercero | None:
    if not data:
        return None
    nombre = _documentado(data.get("nombre"), str)
    nif = _documentado(data.get("nif"), str)
    direccion = _documentado(data.get("direccion"), str)
    if nombre is None and nif is None and direccion is None:
        return None
    return Tercero(
        nombre=nombre,
        nif=nif,
        direccion=direccion,
        alias_funcional=normalizar_proveedor_identidad(nombre.valor) if nombre else None,
    )


def _stable_invoice_id(sha: str, provider: str | None, number: str | None, start: int, end: int) -> str:
    identity = {
        "sha256": sha,
        "proveedor": provider,
        "numero": number,
        "pagina_inicio": start,
        "pagina_fin": end,
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return "fac_" + digest[:24]


def normalizar_en_memoria() -> tuple[dict[str, Any], dict[str, Any]]:
    if hashlib.sha256(PDF.read_bytes()).hexdigest() != DOCUMENTO_SHA256:
        raise RuntimeError("el binario local no coincide con el SHA-256 productivo")
    local = MotorDocumentoLocal(BackendPdfium()).extraer(PDF)
    if local.documento.get("sha256") != DOCUMENTO_SHA256:
        raise RuntimeError("el extractor devolvio un SHA-256 distinto")
    if local.documento.get("layout") != "logista-pharma-local":
        raise RuntimeError("extractor local esperado no seleccionado")
    if len(local.facturas) != 1 or local.incidencias:
        raise RuntimeError("extraccion local no apta para piloto unitario")
    raw = local.facturas[0]
    header = raw["cabecera"]
    start, end = map(int, raw["segmento"]["paginas"])
    provider = _tercero(header.get("proveedor"))
    recipient = _tercero(header.get("destinatario"))
    number = _documentado(header.get("numero_factura"), str)

    taxes = [
        TramoImpuesto(
            orden=int(item["orden"]),
            base=_documentado(item.get("base"), _decimal),
            tipo_iva=_documentado(item.get("tipo_iva"), _decimal),
            cuota_iva=_documentado(item.get("cuota_iva"), _decimal),
            tipo_recargo_equivalencia=_documentado(item.get("tipo_recargo_equivalencia"), _decimal),
            cuota_recargo_equivalencia=_documentado(item.get("cuota_recargo_equivalencia"), _decimal),
        )
        for item in raw.get("impuestos", [])
    ]
    due_dates = [
        Vencimiento(
            orden=int(item["orden"]),
            fecha=_documentado(item.get("fecha"), _fecha),
            importe=_documentado(item.get("importe"), _decimal),
            medio_pago=_documentado(item.get("forma_pago"), str),
        )
        for item in raw.get("vencimientos", [])
    ]
    delivery_notes = []
    incidents = []
    for item in raw.get("albaranes", []):
        number_ev = item.evidencias.get("numero_albaran")
        date_ev = item.evidencias.get("fecha")
        total_ev = item.evidencias.get("total")
        base_ev = item.evidencias.get("base")
        type_ev = item.evidencias.get("tipo_pedido")
        number_documented = (
            ValorDocumentado(valor=str(item.numero_albaran), literal=number_ev.literal, evidencia=[_evidencia(number_ev)])
            if number_ev else None
        )
        if number_documented is None:
            continue
        delivery_notes.append(AlbaranDocumental(
            orden=int(item.orden),
            fecha=(ValorDocumentado(valor=_fecha(item.fecha), literal=date_ev.literal, evidencia=[_evidencia(date_ev)]) if item.fecha and date_ev else None),
            numero=number_documented,
            sentido=Sentido(item.sentido) if item.sentido else None,
            tipo_pedido=(ValorDocumentado(valor=str(item.tipo_pedido), literal=type_ev.literal, evidencia=[_evidencia(type_ev)]) if item.tipo_pedido and type_ev else None),
            importe_base=(ValorDocumentado(valor=sum((Decimal(str(x)) for x in item.bases), Decimal("0")), literal=base_ev.literal, evidencia=[_evidencia(base_ev)]) if item.bases and base_ev else None),
            importe_total=(ValorDocumentado(valor=Decimal(str(item.total)), literal=total_ev.literal, evidencia=[_evidencia(total_ev)]) if item.total is not None and total_ev else None),
        ))
        if item.sentido is None:
            incidents.append(Incidencia(
                codigo="SENTIDO_NO_DOCUMENTADO",
                severidad=Severidad.AVISO,
                descripcion="El documento demuestra el albaran, pero no CARGO/ABONO",
                paginas=[int(item.pagina)],
                bloqueante=False,
                evidencias=[_evidencia(number_ev)],
            ))

    invoice = FacturaNormalizada(
        factura_id=_stable_invoice_id(
            DOCUMENTO_SHA256,
            provider.alias_funcional if provider else None,
            number.valor if number else None,
            start,
            end,
        ),
        tipo_documento=_documentado(header.get("tipo_documento"), str),
        naturaleza_principal=NaturalezaPrincipal.MERCANCIA,
        estado_validacion=EstadoValidacion.REQUIERE_REVISION,
        requiere_conciliacion_albaranes=bool(delivery_notes),
        pagina_inicio=start,
        pagina_fin=end,
        proveedor=provider,
        numero_factura=number,
        fecha_factura=_documentado(header.get("fecha_factura"), _fecha),
        destinatario=recipient,
        totales=Totales(
            moneda=None,
            base_imponible=_documentado(header.get("base_imponible_total"), _decimal),
            iva=_documentado(header.get("iva_total"), _decimal),
            recargo_equivalencia=_documentado(header.get("recargo_equivalencia_total"), _decimal),
            otros=None,
            total=_documentado(header.get("importe_total"), _decimal),
        ),
        vencimientos=due_dates,
        impuestos=taxes,
        albaranes=delivery_notes,
        movimientos_comerciales=[],
        forma_pago=(FormaPago(descripcion_literal=_documentado(header.get("forma_pago"), str)) if _documentado(header.get("forma_pago"), str) else None),
        incidencias=incidents,
        validaciones=[ResultadoValidacion(
            codigo="ADAPTACION_LOCAL_V1",
            resultado=ResultadoControl.OK,
            descripcion="Adaptacion mecanica del extractor local al contrato V1",
            regla_version="piloto-2i.local-v1.1",
        )],
    )
    evaluation = validar_factura(invoice, ContextoValidacion(numero_paginas=int(local.documento["pages"])))
    invoice = invoice.model_copy(update={
        "estado_validacion": evaluation.estado,
        "validaciones": list(evaluation.validaciones),
        "discrepancias_documentales": list(evaluation.discrepancias),
        "incidencias": list(evaluation.incidencias),
    })
    now = datetime.now(timezone.utc).isoformat()
    document = {
        "documento_completo_demostrado": local.documento_completo_demostrado,
        "documento_id": "doc_" + DOCUMENTO_SHA256[:24],
        "archivo_origen": PDF.name,
        "tipo_contenido": "PDF_NATIVO",
        "numero_paginas": int(local.documento["pages"]),
        "estado_documento": invoice.estado_validacion.value,
        "estrategia_lectura": "LOCAL_CERTIFICADO",
        "facturas": [invoice.model_dump(mode="json")],
        "metadata_tecnica": {
            "version_normalizador": "piloto-2i.local-v1.1",
            "version_configuracion": "supabase-v1",
            "lector_primario": str(local.motor["id"]),
            "intentos": [{
                "orden": 1,
                "estrategia": "LOCAL_CERTIFICADO",
                "estado_tecnico": "COMPLETADO",
                "motivo": None,
                "paginas_o_segmentos": list(range(1, int(local.documento["pages"]) + 1)),
                "version_lector": str(local.motor["version"]),
                "duracion_ms": 0,
            }],
            "segmentos": [],
            "huella_contenido": DOCUMENTO_SHA256,
            "inicio": now,
            "fin": now,
            "duracion_ms": 0,
            "correlacion_id": "piloto2i_" + DOCUMENTO_SHA256[:20],
            "extractor": local.documento["layout"],
            "extractor_version": local.documento["layout_version"],
            "ocr": bool(local.documento.get("ocr")),
            "provenance_local": raw.get("provenance", {}),
        },
    }
    summary = {
        "documento_id": DOCUMENTO_ID,
        "sha256": DOCUMENTO_SHA256,
        "proveedor": provider.nombre.valor if provider and provider.nombre else None,
        "extractor": local.documento["layout"],
        "extractor_version": local.documento["layout_version"],
        "ocr": bool(local.documento.get("ocr")),
        "luna": False,
        "estado": invoice.estado_validacion.value,
        "factura_id_documental": invoice.factura_id,
        "numero_factura": number.valor if number else None,
        "fecha_factura": invoice.fecha_factura.valor.iso.isoformat() if invoice.fecha_factura and invoice.fecha_factura.valor.iso else None,
        "base": str(invoice.totales.base_imponible.valor) if invoice.totales.base_imponible else None,
        "iva": str(invoice.totales.iva.valor) if invoice.totales.iva else None,
        "recargo_equivalencia": str(invoice.totales.recargo_equivalencia.valor) if invoice.totales.recargo_equivalencia else None,
        "total": str(invoice.totales.total.valor) if invoice.totales.total else None,
        "vencimientos": len(invoice.vencimientos),
        "impuestos": len(invoice.impuestos),
        "movimientos": len(invoice.movimientos_comerciales),
        "albaranes": len(invoice.albaranes),
        "incidencias": [item.codigo for item in invoice.incidencias],
        "validaciones": {item.codigo: item.resultado.value for item in invoice.validaciones},
    }
    return document, summary


def precheck() -> None:
    connection = _connect(readonly=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select current_database(), current_user")
            if cursor.fetchone() is None:
                raise RuntimeError("destino PostgreSQL no identificable")
            cursor.execute("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas,tolerancia_conciliacion from public.cf_configuracion where id=true")
            config = cursor.fetchone()
            if config != (False, False, False, ["PIO"], TOLERANCIA):
                raise RuntimeError("configuracion productiva no segura")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("facturas no esta vacia")
            cursor.execute("select count(*) from public.normalizacion_ejecuciones")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("normalizacion_ejecuciones no esta vacia")
            cursor.execute("select count(*) from public.conciliaciones")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("conciliaciones no esta vacia")
            cursor.execute("select farmacia,estado_lectura,archivo_hash from public.documentos_facturas where id=%s", (DOCUMENTO_ID,))
            if cursor.fetchone() != ("PIO", "PENDIENTE", DOCUMENTO_SHA256):
                raise RuntimeError("documento piloto productivo no elegible")
            cursor.execute("select count(*) from public.documentos_facturas where reprocesar_solicitado_at is not null")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("existen solicitudes de reprocesado ajenas")
    finally:
        connection.close()


def persist(document: dict[str, Any]) -> dict[str, str]:
    from src.facturas.completitud_documental import validar_documento_antes_de_persistir
    validar_documento_antes_de_persistir("PIO", document)
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    idempotency_key = f"hito-2i:{DOCUMENTO_SHA256}:{result_hash}"
    payload = {
        "estado": "COMPLETADA",
        "resultado_hash": result_hash,
        "uso_ocr": False,
        "uso_luna": False,
        "luna_modelo": None,
        "luna_campos": [],
        "tokens_entrada": None,
        "tokens_salida": None,
        "tokens_total": None,
        "coste_luna": None,
        "pasos": [{"orden": 1, "estrategia": "LOCAL_CERTIFICADO", "uso_ocr": False, "estado": "COMPLETADO"}],
        "resultado_json": document,
        "incidencias_runtime": [],
    }
    connection = _connect(readonly=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute("set local lock_timeout = '5s'")
            cursor.execute("set local statement_timeout = '60s'")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("barrera final: facturas no esta vacia")
            cursor.execute("select count(*) from public.documentos_facturas where reprocesar_solicitado_at is not null")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("barrera final: existe otro reprocesado solicitado")
            cursor.execute("select (public.cf_solicitar_reprocesado(%s,%s)).id::text", (DOCUMENTO_ID, "PIO-HITO-2I"))
            if cursor.fetchone()[0] != DOCUMENTO_ID:
                raise RuntimeError("la solicitud manual no devolvio el documento piloto")
            cursor.execute("select id::text from public.cf_reclamar_documento_normalizacion(%s,%s)", (WORKER_NORMALIZACION, 300))
            claimed = [row[0] for row in cursor.fetchall()]
            if claimed != [DOCUMENTO_ID]:
                raise RuntimeError("claim no exclusivo del documento piloto")
            cursor.execute(
                "select public.cf_persistir_normalizacion(%s,%s,%s,%s,%s,%s)::text",
                (DOCUMENTO_ID, WORKER_NORMALIZACION, "MANUAL", idempotency_key, result_hash, Json(payload)),
            )
            execution_id = cursor.fetchone()[0]
            cursor.execute("select id::text from public.facturas where documento_id=%s", (DOCUMENTO_ID,))
            invoices = [row[0] for row in cursor.fetchall()]
            if len(invoices) != 1:
                raise RuntimeError("la RPC no genero exactamente una factura")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("la RPC afecto a mas de una factura")
            cursor.execute("select count(*) from public.normalizacion_ejecuciones")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("la RPC no genero exactamente una ejecucion")
        connection.commit()
        return {"ejecucion_id": execution_id, "factura_id": invoices[0], "resultado_hash": result_hash}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def validate_persistence() -> dict[str, Any]:
    connection = _connect(readonly=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select id::text,estado_lectura,cantidad_documentos_detectados from public.documentos_facturas where id=%s", (DOCUMENTO_ID,))
            document = cursor.fetchone()
            if document != (DOCUMENTO_ID, "NORMALIZADA", 1):
                raise RuntimeError("documento persistido incoherente")
            cursor.execute("select id::text,numero_factura,proveedor_literal,importe_total,estado_normalizacion,estado_conciliacion_cf,estado_revision,requiere_conciliacion_albaranes from public.facturas where documento_id=%s", (DOCUMENTO_ID,))
            invoice = cursor.fetchone()
            if invoice is None:
                raise RuntimeError("factura persistida ausente")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("existe mas de una factura productiva")
            cursor.execute("select count(*) from public.normalizacion_ejecuciones where documento_id=%s and uso_luna=false", (DOCUMENTO_ID,))
            executions = cursor.fetchone()[0]
            if executions != 1:
                raise RuntimeError("ejecucion unica sin Luna no demostrada")
            child_counts = {}
            for table in ("facturas_vencimientos", "facturas_impuestos", "facturas_albaranes_extraidos", "facturas_movimientos"):
                cursor.execute(f"select count(*) from public.{table} where factura_id=%s", (invoice[0],))
                child_counts[table] = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas_incidencias where factura_id=%s", (invoice[0],))
            child_counts["facturas_incidencias"] = cursor.fetchone()[0]
            if child_counts != {
                "facturas_vencimientos": 1,
                "facturas_impuestos": 1,
                "facturas_albaranes_extraidos": 1,
                "facturas_movimientos": 0,
                "facturas_incidencias": 1,
            }:
                raise RuntimeError("hijos persistidos incoherentes")
            cursor.execute("select id::text,numero_albaran,fecha_albaran,importe_total from public.facturas_albaranes_extraidos where factura_id=%s", (invoice[0],))
            extracted = cursor.fetchone()
            cursor.execute("select id_contador,numero_albaran,fecha,importe_puc,importe_pvp from public.albaranes where farmacia=%s and numero_albaran=%s", ("PIO", extracted[1]))
            exact = cursor.fetchall()
            cursor.execute("select id_contador,numero_albaran,fecha,importe_puc,importe_pvp from public.albaranes where farmacia=%s and fecha=%s and (abs(coalesce(importe_puc,0)-%s)<=%s or abs(coalesce(importe_pvp,0)-%s)<=%s)", ("PIO", extracted[2], extracted[3], TOLERANCIA, extracted[3], TOLERANCIA))
            economic = cursor.fetchall()
            return {
                "factura_id": invoice[0],
                "numero_factura": invoice[1],
                "proveedor": invoice[2],
                "importe_total": str(invoice[3]),
                "estado_normalizacion": invoice[4],
                "estado_conciliacion": invoice[5],
                "estado_revision": invoice[6],
                "requiere_conciliacion": invoice[7],
                "ejecuciones": executions,
                "hijos": child_counts,
                "albaran_extraido_id": extracted[0],
                "numero_albaran": extracted[1],
                "importe_albaran": str(extracted[3]),
                "matches_numero": len(exact),
                "matches_economicos_fecha": len(economic),
            }
    finally:
        connection.close()


def reconcile() -> dict[str, Any]:
    state = validate_persistence()
    if state["matches_numero"] or state["matches_economicos_fecha"]:
        raise RuntimeError("el piloto requiere una decision de matching no implementada")
    invoice = FacturaTrabajo(
        factura_id=state["factura_id"],
        documento_id=DOCUMENTO_ID,
        farmacia="PIO",
        importe_total=Decimal(state["importe_total"]),
        proveedor_id=None,
    )
    detail = DetalleConciliacion(
        tipo_relacion=TipoRelacionConciliacion.SIN_COINCIDENCIA,
        importe_aplicado=Decimal("0"),
        factura_albaran_extraido_id=state["albaran_extraido_id"],
        coincidencia_numero_literal=False,
        provenance={
            "fuente": "ALBARANES_SUPABASE_PIO",
            "criterio": "SIN_COINCIDENCIA_NUMERO_FECHA_IMPORTE",
            "numero_albaran_documental": state["numero_albaran"],
            "importe_documental": state["importe_albaran"],
            "farmatic_consultado": False,
        },
    )
    result = conciliar_importes(invoice.importe_total, [detail], tolerancia=TOLERANCIA)
    if result.resultado != "DIFERENCIA":
        raise RuntimeError("resultado de conciliacion inesperado")

    connection = _connect(readonly=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select count(*) from public.conciliaciones")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("conciliaciones dejo de estar vacia")
            cursor.execute("select (public.cf_solicitar_reintento_conciliacion(%s,%s)).id::text", (invoice.factura_id, "PIO-HITO-2I"))
            if cursor.fetchone()[0] != invoice.factura_id:
                raise RuntimeError("solicitud manual de conciliacion incorrecta")
            cursor.execute("select id::text from public.cf_reclamar_factura_conciliacion(%s,%s)", (WORKER_CONCILIACION, 300))
            claimed = [row[0] for row in cursor.fetchall()]
            if claimed != [invoice.factura_id]:
                raise RuntimeError("claim de conciliacion no exclusivo")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    repository = RepositorioRuntimeSupabase(obtener_cliente_supabase())
    reconciliation_id = repository.guardar_conciliacion(
        invoice,
        WORKER_CONCILIACION,
        result,
        disparador="MANUAL",
    )
    return {
        "conciliacion_id": reconciliation_id,
        "resultado": result.resultado,
        "importe_factura": str(result.importe_factura),
        "importe_explicado": str(result.importe_explicado),
        "diferencia": str(result.diferencia),
        "tolerancia": str(result.tolerancia),
        "detalles": len(result.detalles),
        "matches_numero": state["matches_numero"],
        "matches_economicos_fecha": state["matches_economicos_fecha"],
    }


def final_report() -> dict[str, Any]:
    from src.facturas.motor_local.autoridad import AUTORIDADES_EXTRACTORES_LOCALES

    connection = _connect(readonly=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion where id=true")
            config = cursor.fetchone()
            if config != (False, False, False, ["PIO"]):
                raise RuntimeError("flags finales inseguros")
            cursor.execute("select estado_lectura,count(*) from public.documentos_facturas where farmacia=%s group by estado_lectura order by estado_lectura", ("PIO",))
            states = cursor.fetchall()
            if states != [("NORMALIZADA", 1), ("PENDIENTE", 115)]:
                raise RuntimeError("se proceso un numero de documentos distinto de uno")
            cursor.execute("select count(*) from public.documentos_facturas where farmacia=%s", ("RITA",))
            rita_documents = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas")
            invoice_count = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.normalizacion_ejecuciones")
            execution_count = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.conciliaciones")
            reconciliation_count = cursor.fetchone()[0]
            if (invoice_count, execution_count, reconciliation_count) != (1, 1, 1):
                raise RuntimeError("conteos finales funcionales inesperados")
            cursor.execute("select f.id::text,f.numero_factura,f.proveedor_literal,f.importe_total,f.estado_normalizacion,f.estado_conciliacion_cf,f.estado_revision,f.conciliacion_bloqueado_por,n.uso_ocr,n.uso_luna,n.estado,n.disparador,n.resultado_json from public.facturas f join public.normalizacion_ejecuciones n on n.id=f.normalizacion_ejecucion_id where f.documento_id=%s", (DOCUMENTO_ID,))
            invoice = cursor.fetchone()
            normalized = invoice[12]
            evidence = []
            for value in normalized["facturas"]:
                stack = [value]
                while stack:
                    item = stack.pop()
                    if isinstance(item, dict):
                        if "evidencia" in item and isinstance(item["evidencia"], list):
                            evidence.extend(item["evidencia"])
                        stack.extend(item.values())
                    elif isinstance(item, list):
                        stack.extend(item)
            if not evidence or not all(item.get("pagina") and item.get("literal") for item in evidence):
                raise RuntimeError("provenance documental no preservada")
            if not any((item.get("ubicacion") or {}).get("sha_documento") == DOCUMENTO_SHA256 for item in evidence):
                raise RuntimeError("SHA de provenance no preservado")
            cursor.execute("select c.id::text,c.disparador,c.estado,c.tolerancia,c.importe_factura,c.importe_explicado,c.diferencia,c.resultado,count(cd.id) from public.conciliaciones c left join public.conciliacion_detalles cd on cd.conciliacion_id=c.id where c.factura_id=%s group by c.id", (invoice[0],))
            reconciliation = cursor.fetchone()
            if reconciliation[1:] != ("MANUAL", "COMPLETADA", TOLERANCIA, Decimal("448.0000"), Decimal("0.0000"), Decimal("448.0000"), "DIFERENCIA", 1):
                raise RuntimeError("conciliacion final incoherente")
            cursor.execute("select tipo_relacion,coincidencia_numero_literal,albaran_farmacia,albaran_id_contador from public.conciliacion_detalles where conciliacion_id=%s", (reconciliation[0],))
            detail = cursor.fetchone()
            if detail != ("SIN_COINCIDENCIA", False, None, None):
                raise RuntimeError("detalle de conciliacion incoherente")
            cursor.execute("select count(*) from public.documentos_facturas where bloqueado_por is not null or bloqueado_hasta is not null")
            document_locks = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas where conciliacion_bloqueado_por is not null or conciliacion_bloqueado_hasta is not null")
            invoice_locks = cursor.fetchone()[0]
            if document_locks or invoice_locks:
                raise RuntimeError("locks del piloto no liberados")
            child_counts = {}
            for table in ("facturas_vencimientos", "facturas_impuestos", "facturas_albaranes_extraidos", "facturas_movimientos", "facturas_incidencias"):
                cursor.execute(f"select count(*) from public.{table} where factura_id=%s", (invoice[0],))
                child_counts[table] = cursor.fetchone()[0]
            return {
                "flags": {
                    "normalizacion_automatica": config[0],
                    "conciliacion_automatica": config[1],
                    "luna_habilitada": config[2],
                    "farmacias_habilitadas": config[3],
                },
                "documentos_pio_por_estado": states,
                "documentos_rita": rita_documents,
                "facturas": invoice_count,
                "normalizacion_ejecuciones": execution_count,
                "conciliaciones": reconciliation_count,
                "factura": {
                    "id": invoice[0],
                    "numero": invoice[1],
                    "proveedor": invoice[2],
                    "total": str(invoice[3]),
                    "estado_normalizacion": invoice[4],
                    "estado_conciliacion": invoice[5],
                    "estado_revision": invoice[6],
                    "uso_ocr": invoice[8],
                    "uso_luna": invoice[9],
                    "ejecucion_estado": invoice[10],
                    "ejecucion_disparador": invoice[11],
                },
                "hijos": child_counts,
                "provenance_evidencias": len(evidence),
                "conciliacion": {
                    "id": reconciliation[0],
                    "disparador": reconciliation[1],
                    "estado": reconciliation[2],
                    "tolerancia": str(reconciliation[3]),
                    "importe_factura": str(reconciliation[4]),
                    "importe_explicado": str(reconciliation[5]),
                    "diferencia": str(reconciliation[6]),
                    "resultado": reconciliation[7],
                    "detalles": reconciliation[8],
                    "tipo_detalle": detail[0],
                },
                "autoridades_locales_false": sum(not item.habilitada for item in AUTORIDADES_EXTRACTORES_LOCALES.values()),
                "autoridades_locales_total": len(AUTORIDADES_EXTRACTORES_LOCALES),
                "locks": {"documentos": document_locks, "facturas": invoice_locks},
            }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("precheck", "dry-run", "persist", "validate", "reconcile", "final"))
    args = parser.parse_args()
    if args.mode == "precheck":
        precheck()
        print("PILOTO_2I_PRECHECK_OK")
        return
    if args.mode == "validate":
        print("PERSISTENCIA_VALIDADA=" + json.dumps(validate_persistence(), ensure_ascii=False, sort_keys=True))
        return
    if args.mode == "reconcile":
        print("CONCILIACION=" + json.dumps(reconcile(), ensure_ascii=False, sort_keys=True))
        return
    if args.mode == "final":
        print("FINAL=" + json.dumps(final_report(), ensure_ascii=False, sort_keys=True))
        return
    precheck()
    document, summary = normalizar_en_memoria()
    print("NORMALIZACION=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if args.mode == "dry-run":
        return
    result = persist(document)
    print("PERSISTENCIA=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
