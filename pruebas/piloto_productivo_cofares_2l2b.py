"""Piloto 2L.2B: una sola factura COFARES PIO, fail-closed y sin workers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))

import psycopg2  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

from pruebas.piloto_productivo_2i import (  # noqa: E402
    _connect, _decimal, _documentado, _fecha, _stable_invoice_id, _tercero,
)
from src.facturas.completitud_documental import validar_documento_antes_de_persistir  # noqa: E402
from src.facturas.motor_local.backend.pdfium import BackendPdfium  # noqa: E402
from src.facturas.motor_local.servicio import MotorDocumentoLocal  # noqa: E402
from src.facturas.normalizador_v2.modelos import (  # noqa: E402
    EstadoValidacion, Evidencia, FacturaNormalizada, FormaPago, Incidencia,
    MovimientoComercial, NaturalezaPrincipal, ResultadoControl,
    ResultadoValidacion, Sentido, Severidad, TipoMovimiento, Totales,
    TramoImpuesto, ValorDocumentado, Vencimiento,
)
from src.facturas.normalizador_v2.validadores import ContextoValidacion, validar_factura  # noqa: E402
from src.facturas.runtime_supabase.conciliacion import conciliar_importes  # noqa: E402
from src.facturas.runtime_supabase.modelos import (  # noqa: E402
    DetalleConciliacion, FacturaTrabajo, TipoRelacionConciliacion,
)
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase  # noqa: E402
from src.supabase_client.conexion_supabase import obtener_cliente_supabase  # noqa: E402


DOCUMENTO_ID = "fcbd0d02-2502-4fb9-ac6a-50fad6d62dcd"
DOCUMENTO_SHA256 = "c720e95ced67b726facf4ad54a07b5a90707bc08c227445b90bacea502e4a422"
PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/COFARES VTO 31.8.26 PIO.pdf"
NUMERO = "5460017198"
TOTAL = Decimal("177.7400")
TOLERANCIA = Decimal("0.0500")
WORKER_NORMALIZACION = "manual-hito-2l2b-normalizacion"
WORKER_CONCILIACION = "manual-hito-2l2b-conciliacion"


def _valor(campo: Any) -> Any:
    if campo is None:
        return None
    valor = campo.get("valor") if isinstance(campo, dict) else campo
    return valor.get("iso") if isinstance(valor, dict) and "iso" in valor else valor


def _incidencia(codigo: str, descripcion: str, evidencias: list[Evidencia]) -> Incidencia:
    return Incidencia(
        codigo=codigo, severidad=Severidad.AVISO, descripcion=descripcion,
        paginas=sorted({e.pagina for e in evidencias}), bloqueante=False,
        evidencias=evidencias,
    )


def normalizar_en_memoria() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    sha = hashlib.sha256(PDF.read_bytes()).hexdigest()
    if sha != DOCUMENTO_SHA256:
        raise RuntimeError("HASH_DOCUMENTAL_DIFERENTE")
    local = MotorDocumentoLocal(BackendPdfium()).extraer(PDF)
    if local.documento.get("sha256") != DOCUMENTO_SHA256:
        raise RuntimeError("HASH_EXTRACTOR_DIFERENTE")
    if len(local.facturas) != 1 or not local.documento_completo_demostrado:
        raise RuntimeError("DOCUMENTO_NO_COMPLETO_O_MULTIFACTURA")
    raw = local.facturas[0]
    header = raw["cabecera"]
    if raw.get("clasificacion_documental", {}).get("tipo") != "FACTURA_GASTO_SERVICIO":
        raise RuntimeError("CLASIFICACION_NO_CERTIFICADA")
    if raw.get("albaranes") != []:
        raise RuntimeError("ALBARANES_INESPERADOS")

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
            total_tramo=_documentado(item.get("total"), _decimal),
        )
        for item in raw["impuestos"]
    ]
    due_dates = [
        Vencimiento(
            orden=int(item["orden"]), fecha=_documentado(item.get("fecha"), _fecha),
            importe=None,
            medio_pago=_documentado(item.get("forma_pago"), str),
        )
        for item in raw["vencimientos"]
    ]
    movements = [
        MovimientoComercial(
            orden=int(item["orden"]), tipo=TipoMovimiento(item["categoria"]),
            descripcion_literal=_documentado(item["descripcion_literal"], str),
            sentido=Sentido(item["sentido"]) if item.get("sentido") else None,
            base=_documentado(item.get("base"), _decimal), iva=None,
            recargo_equivalencia=None, importe=None,
        )
        for item in raw["movimientos"]
    ]
    movement_evidence = [e for m in movements for e in m.descripcion_literal.evidencia]
    due_evidence = [e for v in due_dates for e in (v.fecha.evidencia if v.fecha else [])]
    incidents = [
        _incidencia(
            "IMPORTE_MOVIMIENTO_NO_DOCUMENTADO",
            "Los importes de movimiento no son visibles; se conservan null",
            movement_evidence,
        ),
        _incidencia(
            "IMPORTE_VENCIMIENTO_NO_DOCUMENTADO",
            "El importe del vencimiento no aparece separado en el documento",
            due_evidence,
        ),
    ]
    start, end = map(int, raw["segmento"]["paginas"])
    invoice = FacturaNormalizada(
        factura_id=_stable_invoice_id(
            DOCUMENTO_SHA256,
            provider.alias_funcional if provider else None,
            number.valor if number else None,
            start, end,
        ),
        tipo_documento=_documentado(header.get("tipo_documento"), str),
        naturaleza_principal=NaturalezaPrincipal.SERVICIOS,
        estado_validacion=EstadoValidacion.REQUIERE_REVISION,
        requiere_conciliacion_albaranes=False,
        pagina_inicio=start, pagina_fin=end, proveedor=provider,
        numero_factura=number,
        fecha_factura=_documentado(header.get("fecha_factura"), _fecha),
        destinatario=recipient,
        totales=Totales(
            moneda=None,
            base_imponible=_documentado(header.get("base_imponible_total"), _decimal),
            iva=_documentado(header.get("iva_total"), _decimal),
            recargo_equivalencia=_documentado(header.get("recargo_equivalencia_total"), _decimal),
            total=_documentado(header.get("importe_total"), _decimal),
        ),
        vencimientos=due_dates, impuestos=taxes, albaranes=[],
        movimientos_comerciales=movements,
        forma_pago=(FormaPago(descripcion_literal=_documentado(header["forma_pago"], str)) if header.get("forma_pago") else None),
        incidencias=incidents,
        validaciones=[ResultadoValidacion(
            codigo="ADAPTACION_LOCAL_COFARES_2L2B", resultado=ResultadoControl.OK,
            descripcion="Adaptacion mecanica del extractor COFARES certificado",
            regla_version="piloto-2l2b.local-v1",
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
        "documento_completo_demostrado": True,
        "documento_id": "doc_" + DOCUMENTO_SHA256[:24],
        "archivo_origen": PDF.name,
        "tipo_contenido": "PDF_NATIVO", "numero_paginas": 1,
        "estado_documento": invoice.estado_validacion.value,
        "estrategia_lectura": "LOCAL_CERTIFICADO",
        "facturas": [invoice.model_dump(mode="json")],
        "metadata_tecnica": {
            "version_normalizador": "piloto-2l2b.local-v1",
            "version_configuracion": "supabase-v1",
            "lector_primario": str(local.motor["id"]),
            "intentos": [{"orden": 1, "estrategia": "LOCAL_CERTIFICADO", "estado_tecnico": "COMPLETADO", "uso_ocr": False}],
            "segmentos": [], "huella_contenido": DOCUMENTO_SHA256,
            "inicio": now, "fin": now, "duracion_ms": 0,
            "correlacion_id": "piloto2l2b_" + DOCUMENTO_SHA256[:20],
            "extractor": local.documento["layout"],
            "extractor_version": local.documento["layout_version"],
            "ocr": False, "luna": False,
            "clasificacion_documental": raw["clasificacion_documental"],
        },
    }
    if validar_documento_antes_de_persistir("PIO", document) != "CONSISTENTE":
        raise RuntimeError("CONTRASTE_FARMACIA_NO_CONSISTENTE")
    summary = {
        "sha256": sha,
        "proveedor": provider.nombre.valor if provider and provider.nombre else None,
        "numero": number.valor if number else None,
        "fecha": invoice.fecha_factura.valor.iso.isoformat() if invoice.fecha_factura else None,
        "destinatario": recipient.nombre.valor if recipient and recipient.nombre else None,
        "nif": recipient.nif.valor if recipient and recipient.nif else None,
        "farmacia_documental": "PIO", "contraste": "CONSISTENTE",
        "documento_completo_demostrado": True,
        "clasificacion": raw["clasificacion_documental"]["tipo"],
        "base": str(invoice.totales.base_imponible.valor),
        "iva": str(invoice.totales.iva.valor),
        "re": str(invoice.totales.recargo_equivalencia.valor),
        "total": str(invoice.totales.total.valor),
        "albaranes": 0, "impuestos": len(taxes), "vencimientos": len(due_dates),
        "movimientos": len(movements),
        "estado_validacion": invoice.estado_validacion.value,
        "incidencias": [i.codigo for i in invoice.incidencias],
    }
    return document, summary, raw


def _precheck_cursor(cursor, *, lock_target: bool = False) -> dict[str, Any]:
    cursor.execute("select current_database(),current_user")
    database, user = cursor.fetchone()
    cursor.execute("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas,tolerancia_conciliacion from public.cf_configuracion where id=true")
    flags = cursor.fetchone()
    if flags != (False, False, False, ["PIO"], TOLERANCIA):
        raise RuntimeError("FLAGS_PRODUCTIVOS_INSEGUROS")
    cursor.execute("select count(*) from public.facturas")
    if cursor.fetchone()[0] != 1:
        raise RuntimeError("TOTAL_FACTURAS_PRODUCTIVAS_DISTINTO_DE_1")
    cursor.execute("select id::text,estado_normalizacion,estado_conciliacion_cf,importe_total from public.facturas where numero_factura='5011640669' and upper(proveedor_literal) like 'LOGISTA%'")
    logista = cursor.fetchone()
    if logista is None or logista[1:] != ("NORMALIZADA", "CONCILIADA", Decimal("448.0000")):
        raise RuntimeError("LOGISTA_NO_CONTINUA_NORMALIZADA_CONCILIADA")
    lock = " for update" if lock_target else ""
    cursor.execute("select farmacia,estado_lectura,archivo_hash,bloqueado_por,bloqueado_hasta,reprocesar_solicitado_at from public.documentos_facturas where id=%s" + lock, (DOCUMENTO_ID,))
    target = cursor.fetchone()
    if target is None or target[:3] != ("PIO", "PENDIENTE", DOCUMENTO_SHA256):
        raise RuntimeError("DOCUMENTO_COFARES_NO_ELEGIBLE")
    if any(target[3:]):
        raise RuntimeError("DOCUMENTO_COFARES_BLOQUEADO_O_SOLICITADO")
    cursor.execute("select count(*) from public.facturas where upper(coalesce(proveedor_literal,'')) like '%%COFARES%%' or numero_factura=%s", (NUMERO,))
    if cursor.fetchone()[0] != 0:
        raise RuntimeError("DUPLICADO_ECONOMICO_DEMOSTRADO")
    cursor.execute("select count(*) from public.documentos_facturas where bloqueado_por is not null or bloqueado_hasta is not null")
    document_locks = cursor.fetchone()[0]
    cursor.execute("select count(*) from public.facturas where conciliacion_bloqueado_por is not null or conciliacion_bloqueado_hasta is not null")
    invoice_locks = cursor.fetchone()[0]
    cursor.execute("select count(*) from public.documentos_facturas where reprocesar_solicitado_at is not null")
    requests = cursor.fetchone()[0]
    if document_locks or invoice_locks or requests:
        raise RuntimeError("WORKERS_O_SOLICITUDES_ACTIVAS")
    return {
        "conexion": "OK", "database": database, "user": user,
        "flags": {"normalizacion_automatica": False, "conciliacion_automatica": False, "luna_habilitada": False, "farmacias_habilitadas": ["PIO"]},
        "facturas": 1, "cofares_existente": False,
        "documento_cofares": {"farmacia": target[0], "estado": target[1], "hash": target[2]},
        "workers": 0, "logista": {"id": logista[0], "estado_normalizacion": logista[1], "estado_conciliacion": logista[2]},
    }


def precheck() -> dict[str, Any]:
    connection = _connect(readonly=True)
    try:
        with connection.cursor() as cursor:
            return _precheck_cursor(cursor)
    finally:
        connection.close()


def _duplicado_economico(cursor, document: dict[str, Any]) -> bool:
    f = document["facturas"][0]
    cursor.execute(
        """select count(*) from public.facturas
           where upper(coalesce(proveedor_literal,''))=upper(%s)
             and numero_factura=%s and fecha_factura=%s and importe_total=%s
             and coalesce(datos_extraidos #>> '{destinatario,nombre,valor}','')=%s
             and coalesce(datos_extraidos #>> '{destinatario,nif,valor}','')=%s""",
        (_valor(f["proveedor"]["nombre"]), _valor(f["numero_factura"]),
         _valor(f["fecha_factura"]), _valor(f["totales"]["total"]),
         _valor(f["destinatario"]["nombre"]), _valor(f["destinatario"]["nif"])),
    )
    return cursor.fetchone()[0] != 0


def persist(document: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    idempotency_key = f"hito-2l2b:{DOCUMENTO_SHA256}:{result_hash}"
    payload = {
        "estado": "COMPLETADA", "resultado_hash": result_hash,
        "uso_ocr": False, "uso_luna": False, "luna_modelo": None,
        "luna_campos": [], "tokens_entrada": None, "tokens_salida": None,
        "tokens_total": None, "coste_luna": None,
        "pasos": [{"orden": 1, "estrategia": "LOCAL_CERTIFICADO", "uso_ocr": False, "estado": "COMPLETADO"}],
        "resultado_json": document, "incidencias_runtime": [],
    }
    connection = _connect(readonly=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute("set local lock_timeout='5s'")
            cursor.execute("set local statement_timeout='60s'")
            baseline = _precheck_cursor(cursor, lock_target=True)
            if _duplicado_economico(cursor, document):
                raise RuntimeError("DUPLICADO_ECONOMICO_DEMOSTRADO")
            cursor.execute("select (public.cf_solicitar_reprocesado(%s,%s)).id::text", (DOCUMENTO_ID, "PIO-HITO-2L2B"))
            if cursor.fetchone()[0] != DOCUMENTO_ID:
                raise RuntimeError("SOLICITUD_MANUAL_NO_EXCLUSIVA")
            cursor.execute("select id::text from public.cf_reclamar_documento_normalizacion(%s,%s)", (WORKER_NORMALIZACION, 300))
            if [row[0] for row in cursor.fetchall()] != [DOCUMENTO_ID]:
                raise RuntimeError("CLAIM_NORMALIZACION_NO_EXCLUSIVO")
            cursor.execute(
                "select public.cf_persistir_normalizacion(%s,%s,%s,%s,%s,%s)::text",
                (DOCUMENTO_ID, WORKER_NORMALIZACION, "MANUAL", idempotency_key, result_hash, Json(payload)),
            )
            execution_id = cursor.fetchone()[0]
            cursor.execute("select id::text from public.facturas where documento_id=%s", (DOCUMENTO_ID,))
            invoices = cursor.fetchall()
            if len(invoices) != 1:
                raise RuntimeError("RPC_NO_CREO_UNA_FACTURA_COFARES")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != 2:
                raise RuntimeError("RPC_AFECTO_TOTAL_FACTURAS_INCORRECTO")
            cursor.execute("select estado_normalizacion,estado_conciliacion_cf,importe_total from public.facturas where id=%s", (baseline["logista"]["id"],))
            if cursor.fetchone() != ("NORMALIZADA", "CONCILIADA", Decimal("448.0000")):
                raise RuntimeError("LOGISTA_MODIFICADA_DURANTE_PERSISTENCIA")
        connection.commit()
        return {"ejecucion_id": execution_id, "factura_id": invoices[0][0], "resultado_hash": result_hash}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def validate_persistence() -> dict[str, Any]:
    connection = _connect(readonly=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select id::text,categoria,numero_factura,fecha_factura,proveedor_literal,base_imponible_total,iva_total,recargo_equivalencia_total,importe_total,estado_normalizacion,estado_conciliacion_cf,estado_revision,requiere_conciliacion_albaranes,normalizacion_ejecucion_id::text from public.facturas where documento_id=%s", (DOCUMENTO_ID,))
            f = cursor.fetchone()
            expected_core = ("CUOTA_SERVICIO", NUMERO, datetime(2026, 7, 31).date(), "GRUPO COFARES", Decimal("148.2800"), Decimal("28.8700"), Decimal("0.5900"), TOTAL, "NORMALIZADA")
            expected_tail = ("NO_REQUERIDA", False)
            if f is None or f[1:10] != expected_core or f[10] not in {"PENDIENTE_CONCILIAR", "CONCILIADA"} or f[11:13] != expected_tail:
                raise RuntimeError(f"FACTURA_COFARES_PERSISTIDA_INCOHERENTE:{f}")
            factura_id, execution_id = f[0], f[13]
            cursor.execute("select count(*) from public.normalizacion_ejecuciones where documento_id=%s and id=%s and uso_luna=false and uso_ocr=false and estado='COMPLETADA'", (DOCUMENTO_ID, execution_id))
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("EJECUCION_COFARES_NO_UNICA_O_NO_LOCAL")
            counts = {}
            for table in ("facturas_impuestos", "facturas_vencimientos", "facturas_movimientos", "facturas_albaranes_extraidos", "facturas_incidencias"):
                cursor.execute(f"select count(*) from public.{table} where factura_id=%s", (factura_id,))
                counts[table] = cursor.fetchone()[0]
            if counts != {"facturas_impuestos": 4, "facturas_vencimientos": 1, "facturas_movimientos": 4, "facturas_albaranes_extraidos": 0, "facturas_incidencias": 2}:
                raise RuntimeError(f"HIJOS_COFARES_INCOHERENTES:{counts}")
            cursor.execute("select fecha_vencimiento,importe from public.facturas_vencimientos where factura_id=%s", (factura_id,))
            due = cursor.fetchone()
            if due != (datetime(2026, 8, 30).date(), None):
                raise RuntimeError("VENCIMIENTO_COFARES_INCOHERENTE")
            cursor.execute("select id::text,orden,categoria,descripcion_literal,sentido,base,iva,recargo_equivalencia,importe,provenance from public.facturas_movimientos where factura_id=%s order by orden", (factura_id,))
            movements = cursor.fetchall()
            expected_movements = [
                (1, "CONDICION_COMERCIAL", "Cargo Parafarmacia", "CARGO", Decimal("27.7700")),
                (2, "SERVICIO", "Servicio Cofares Directo", "CARGO", Decimal("6.9500")),
                (3, "SERVICIO", "Servicio Logístico", "CARGO", Decimal("115.0000")),
                (4, "DESCUENTO", "Dto. adicional laboratorio", "ABONO", Decimal("-1.4400")),
            ]
            if [(m[1], m[2], m[3], m[4], m[5]) for m in movements] != expected_movements:
                raise RuntimeError("MOVIMIENTOS_COFARES_INCOHERENTES")
            if any(m[6] is not None or m[7] is not None or m[8] is not None for m in movements):
                raise RuntimeError("IMPORTE_O_IMPUESTO_MOVIMIENTO_INVENTADO")
            if not all(m[9] for m in movements):
                raise RuntimeError("PROVENANCE_MOVIMIENTOS_AUSENTE")
            cursor.execute("select codigo,estado,bloqueante from public.facturas_incidencias where factura_id=%s order by codigo", (factura_id,))
            incidents = cursor.fetchall()
            if incidents != [("IMPORTE_MOVIMIENTO_NO_DOCUMENTADO", "ABIERTA", False), ("IMPORTE_VENCIMIENTO_NO_DOCUMENTADO", "ABIERTA", False)]:
                raise RuntimeError(f"INCIDENCIAS_COFARES_INCOHERENTES:{incidents}")
            cursor.execute("select count(*) from public.facturas")
            total_invoices = cursor.fetchone()[0]
            cursor.execute("select estado_normalizacion,estado_conciliacion_cf from public.facturas where numero_factura='5011640669'")
            logista = cursor.fetchone()
            if total_invoices != 2 or logista != ("NORMALIZADA", "CONCILIADA"):
                raise RuntimeError("AISLAMIENTO_POST_PERSISTENCIA_FALLIDO")
            return {"factura_id": factura_id, "ejecucion_id": execution_id, "hijos": counts, "vencimiento": [str(due[0]), due[1]], "movimientos": movements, "incidencias": incidents, "total_facturas": total_invoices}
    finally:
        connection.close()


def _detalle_movimiento(row: tuple[Any, ...]) -> DetalleConciliacion:
    movement_id, orden, categoria, literal, sentido, base, _, _, importe, provenance = row
    if importe is not None or sentido not in {"CARGO", "ABONO"}:
        raise RuntimeError("MOVIMIENTO_NO_APTO_PARA_MODELO_ECONOMICO_CERTIFICADO")
    raw = provenance
    base_field = raw.get("base") or {}
    evidences = base_field.get("evidencia") or []
    rates = {"base_sr": (Decimal("0.04"), Decimal("0.005")), "base_r": (Decimal("0.10"), Decimal("0.014")), "base_n": (Decimal("0.21"), Decimal("0.052")), "base_n_sin_re": (Decimal("0.21"), Decimal("0"))}
    components = []
    for evidence in evidences:
        column = str((evidence.get("ubicacion") or {}).get("columna", "")).casefold()
        if column not in rates:
            raise RuntimeError(f"COLUMNA_FISCAL_MOVIMIENTO_NO_DEMOSTRADA:{column}")
        amount_literal = str(evidence["literal"]).replace(".", "").replace(",", ".")
        if amount_literal.endswith("-"):
            amount_literal = "-" + amount_literal[:-1]
        component_base = abs(Decimal(amount_literal))
        iva_rate, re_rate = rates[column]
        tax = (component_base * iva_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        surcharge = (component_base * re_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        components.append({"columna": column, "base": str(component_base), "iva": str(tax), "re": str(surcharge)})
    if not components or sum((Decimal(x["base"]) for x in components), Decimal("0")) != abs(base):
        raise RuntimeError("DESGLOSE_BASE_MOVIMIENTO_NO_CUADRA")
    gross = sum((Decimal(x["base"]) + Decimal(x["iva"]) + Decimal(x["re"]) for x in components), Decimal("0"))
    applied = gross if sentido == "CARGO" else -gross
    return DetalleConciliacion(
        tipo_relacion=TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC,
        importe_aplicado=applied, factura_movimiento_id=movement_id,
        provenance={"fuente": "ESTRUCTURA_ECONOMICA_DOCUMENTAL", "orden": orden, "categoria": categoria, "concepto_literal": literal, "sentido": sentido, "importe_movimiento": None, "componentes_fiscales": components, "farmatic_consultado": False},
    )


def reconcile() -> dict[str, Any]:
    state = validate_persistence()
    details = tuple(_detalle_movimiento(row) for row in state["movimientos"])
    result = conciliar_importes(TOTAL, details, tolerancia=TOLERANCIA)
    if result.resultado != "CONCILIADA" or result.importe_explicado != TOTAL or result.diferencia != 0:
        raise RuntimeError(f"TOTAL_SERVICIOS_NO_EXPLICADO:{result}")
    connection = _connect(readonly=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion where id=true")
            if cursor.fetchone() != (False, False, False, ["PIO"]):
                raise RuntimeError("FLAGS_PRODUCTIVOS_INSEGUROS")
            cursor.execute("select id::text from public.conciliaciones where factura_id=%s", (state["factura_id"],))
            if cursor.fetchall():
                raise RuntimeError("CONCILIACION_COFARES_YA_EXISTE")
            cursor.execute("select count(*) from public.facturas where conciliacion_bloqueado_por is not null or conciliacion_bloqueado_hasta is not null or conciliacion_reintento_solicitado_at is not null")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("WORKER_O_SOLICITUD_CONCILIACION_ACTIVA")
    finally:
        connection.close()
    invoice = FacturaTrabajo(state["factura_id"], DOCUMENTO_ID, "PIO", TOTAL)
    reconciliation_id = RepositorioRuntimeSupabase(obtener_cliente_supabase()).guardar_conciliacion(
        invoice, WORKER_CONCILIACION, result, disparador="MANUAL"
    )
    return {"conciliacion_id": reconciliation_id, "importe_factura": str(result.importe_factura), "importe_explicado": str(result.importe_explicado), "diferencia": str(result.diferencia), "resultado": result.resultado, "detalles": len(details)}


def final_report() -> dict[str, Any]:
    state = validate_persistence()
    connection = _connect(readonly=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion where id=true")
            flags = cursor.fetchone()
            cursor.execute("select estado_normalizacion,estado_conciliacion_cf,estado_revision,diferencia_albaranes,conciliacion_bloqueado_por from public.facturas where id=%s", (state["factura_id"],))
            statuses = cursor.fetchone()
            cursor.execute("select c.importe_factura,c.importe_explicado,c.diferencia,c.resultado,count(cd.id) from public.conciliaciones c left join public.conciliacion_detalles cd on cd.conciliacion_id=c.id where c.factura_id=%s and c.es_actual group by c.id", (state["factura_id"],))
            reconciliation = cursor.fetchone()
            cursor.execute("select count(*) from public.facturas_incidencias where factura_id=%s and codigo='ALBARAN_NO_LOCALIZADO'", (state["factura_id"],))
            albaran_incident = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.documentos_facturas where bloqueado_por is not null or bloqueado_hasta is not null")
            document_locks = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas where conciliacion_bloqueado_por is not null or conciliacion_bloqueado_hasta is not null")
            invoice_locks = cursor.fetchone()[0]
            cursor.execute("select estado_normalizacion,estado_conciliacion_cf,importe_total from public.facturas where numero_factura='5011640669'")
            logista = cursor.fetchone()
            cursor.execute("select estado_lectura,count(*) from public.documentos_facturas where farmacia='PIO' group by estado_lectura order by estado_lectura")
            pio_states = cursor.fetchall()
            cursor.execute("select count(*) from public.documentos_facturas where farmacia='RITA'")
            rita_documents = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.normalizacion_ejecuciones where uso_luna=true")
            luna_executions = cursor.fetchone()[0]
            cursor.execute("select count(distinct documento_id) from public.normalizacion_ejecuciones where documento_id not in (%s,%s)", (DOCUMENTO_ID, "0387e00a-e861-48f0-88ad-9236b92078e8"))
            other_processed = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.documentos_facturas where upper(archivo_nombre) like '%%HEFAME%%' and estado_lectura<>'PENDIENTE'")
            hefame_processed = cursor.fetchone()[0]
            if flags != (False, False, False, ["PIO"]) or document_locks or invoice_locks:
                raise RuntimeError("AISLAMIENTO_FINAL_FALLIDO")
            if statuses[:3] != ("NORMALIZADA", "CONCILIADA", "NO_REQUERIDA"):
                raise RuntimeError(f"ESTADOS_FINALES_INCORRECTOS:{statuses}")
            if reconciliation != (TOTAL, TOTAL, Decimal("0.0000"), "CONCILIADA", 4):
                raise RuntimeError(f"CONCILIACION_FINAL_INCORRECTA:{reconciliation}")
            if albaran_incident or logista != ("NORMALIZADA", "CONCILIADA", Decimal("448.0000")):
                raise RuntimeError("AISLAMIENTO_ECONOMICO_FINAL_FALLIDO")
            if dict(pio_states).get("NORMALIZADA") != 2 or rita_documents != 0 or luna_executions != 0 or other_processed != 0 or hefame_processed != 0:
                raise RuntimeError(f"OTROS_DOCUMENTOS_O_SERVICIOS_AFECTADOS:{pio_states=},{rita_documents=},{luna_executions=},{other_processed=},{hefame_processed=}")
            return {"factura_id": state["factura_id"], "ejecucion_id": state["ejecucion_id"], "hijos": state["hijos"], "incidencias": state["incidencias"], "estados": statuses[:3], "conciliacion": reconciliation, "albaran_no_localizado": albaran_incident, "total_facturas": state["total_facturas"], "logista": logista, "flags": flags, "workers": 0, "documentos_pio": pio_states, "rita_documentos": rita_documents, "hefame_procesado": hefame_processed, "otros_documentos_procesados": other_processed, "luna_ejecuciones": luna_executions}
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("precheck", "dry-run", "persist", "validate", "reconcile", "final"))
    args = parser.parse_args()
    if args.mode == "precheck":
        print("PRECHECK=" + json.dumps(precheck(), ensure_ascii=False, default=str, sort_keys=True))
        return
    document, summary, _ = normalizar_en_memoria()
    if args.mode == "dry-run":
        print("REVALIDACION=" + json.dumps(summary, ensure_ascii=False, sort_keys=True))
    elif args.mode == "persist":
        print("PERSISTENCIA=" + json.dumps(persist(document), sort_keys=True))
    elif args.mode == "validate":
        print("VALIDACION=" + json.dumps(validate_persistence(), ensure_ascii=False, default=str, sort_keys=True))
    elif args.mode == "reconcile":
        print("CONCILIACION=" + json.dumps(reconcile(), sort_keys=True))
    else:
        print("FINAL=" + json.dumps(final_report(), ensure_ascii=False, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
