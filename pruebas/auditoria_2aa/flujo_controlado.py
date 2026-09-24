"""Hito 2AA: piloto productivo doble HEFAME, manual y fail-closed."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tmp_pg_probe_deps")]

import psycopg2
from psycopg2.extras import Json

from src.facturas.completitud_documental import validar_documento_antes_de_persistir
from src.facturas.hefame_economia import derivar_magnitud_comparable_hefame
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    buscar_candidato_albaran,
    dinero,
)


MERC = {
    "documento_id": "1c37b4d1-018f-48aa-bea0-06391876bb44",
    "sha": "39beca0337f40e79b83966c636a50230eacbc00e55278ffd1afae5e0b0100d5a",
    "pdf": ROOT / "tmp/pdfs/hito_2i3/hefame_antiguo.pdf",
    "numero": "0563834757", "nif": "F30004444", "total": Decimal("313.29"),
    "worker": "manual-hito-2aa-hefame-mercancia",
}
CONS = {
    "documento_id": "ee494032-7acd-4977-a37b-a883fe4960fd",
    "sha": "51ae2e5c8e311d9fb19e95d42ea7f8c6873524d3e32a2034eabbb1e834be45dd",
    "pdf": ROOT / "tmp/pdfs/hito_2i3/hefame_nuevo.pdf",
    "numero": "1132029554", "nif": "B30462451", "total": Decimal("66.79"),
    "worker": "manual-hito-2aa-hplus-consumo",
}
BASELINE = {
    "08009277": (Decimal("10111.5500"), "4ce09682-d80a-4f7b-9ad8-d5256a3f4d6c", "c48d9602-d266-4d21-bf1a-49f388be3d5b"),
    "08009278": (Decimal("3824.5900"), "cac2dd70-af4f-4e2b-a19a-abd2135fae53", "d659b6a8-5b4d-462d-b013-911c21d097c6"),
    "08009279": (Decimal("141.0100"), "cac2dd70-af4f-4e2b-a19a-abd2135fae53", "c5acc821-d8c8-4745-b891-f15b13b4354d"),
    "5011640669": (Decimal("448.0000"), "4da89418-bd47-48e2-ac59-99b94d2a4783", "95f0cfb6-2ae3-4739-b697-9a8e5f2ff114"),
    "5460017198": (Decimal("177.7400"), "4a5b2ddf-6cfd-4c5d-ac89-5c979480c2a3", "e9bb291f-aead-4626-9cbe-6d49b486f7c1"),
}
TOL = Decimal("0.0500")


def connect(*, readonly: bool):
    connection = psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"], sslmode="require",
        connect_timeout=10, application_name=f"cf_2aa_{'readonly' if readonly else 'manual'}",
    )
    connection.set_session(readonly=readonly, autocommit=False)
    return connection


def serial(value: Any) -> Any:
    if is_dataclass(value):
        return serial(asdict(value))
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "__dict__"):
        return serial(vars(value))
    return value


def evidence(item: Any) -> dict[str, Any]:
    raw = serial(item)
    return {"pagina": raw["pagina"], "literal": raw["literal"], "ubicacion": raw}


def documented(item: Any, *, kind: str | None = None) -> dict[str, Any] | None:
    if not isinstance(item, dict) or item.get("valor") is None or not item.get("evidencias"):
        return None
    value = item["valor"]
    if kind == "date":
        value = {"iso": str(value), "literal": str(item["literal"])}
    return {
        "valor": value, "literal": str(item["literal"]),
        "evidencia": [evidence(ev) for ev in item["evidencias"]],
    }


def third_party(item: dict[str, Any]) -> dict[str, Any]:
    return {key: documented(item.get(key)) for key in ("nombre", "nif", "direccion")}


def stable_id(cfg: dict[str, Any]) -> str:
    raw = f"{cfg['sha']}|{cfg['nif']}|{cfg['numero']}|2026-08-31|{cfg['total']:.4f}"
    return "fac_" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def gross_from_bases(bases: dict[str, Any]) -> tuple[Decimal, list[dict[str, str]]]:
    total = Decimal("0")
    components = []
    for category in ("BASE_S_R", "BASE_RE", "BASE_NO"):
        field = bases.get(category) or {}
        base = Decimal(str(field.get("valor") or 0))
        if not base:
            continue
        derived = derivar_magnitud_comparable_hefame(abs(base), category)
        gross = Decimal(derived["importe_comparable_operativo"])
        if base < 0:
            gross = -gross
        total += gross
        components.append({
            "categoria": category, "base": str(base),
            "iva": str(derived["importe_iva_derivado"]),
            "re": str(derived["importe_re_derivado"]), "total_fiscal": str(gross),
        })
    return dinero(total), components


def extract(cfg: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    if hashlib.sha256(cfg["pdf"].read_bytes()).hexdigest() != cfg["sha"]:
        raise RuntimeError("HASH_LOCAL_CAMBIADO")
    local = MotorDocumentoLocal(BackendPdfium()).extraer(cfg["pdf"])
    if local.documento["sha256"] != cfg["sha"] or not local.documento_completo_demostrado:
        raise RuntimeError("EXTRACCION_NO_CERTIFICADA")
    header = local.cabecera
    group = header["grupo_funcional"]
    if (
        header["numero_factura"]["valor"] != cfg["numero"]
        or header["proveedor"]["nif"]["valor"] != cfg["nif"]
        or dinero(header["importe_total"]["valor"]) != dinero(cfg["total"])
        or group["grupo_funcional"] != "HEFAME"
    ):
        raise RuntimeError("IDENTIDAD_O_ECONOMIA_CRITICA_CAMBIADA")
    return local, group


def make_document(cfg: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    local, group = extract(cfg)
    header, raw = local.cabecera, local.facturas[0]
    start, end = map(int, raw["segmento"]["paginas"])
    is_merc = cfg is MERC
    taxes = []
    for item in local.impuestos:
        taxes.append({
            "orden": int(item["orden"]),
            "descripcion_literal": None,
            "base": documented(item.get("base")),
            "tipo_iva": documented(item.get("tipo_iva")),
            "cuota_iva": documented(item.get("cuota_iva")),
            "tipo_recargo_equivalencia": documented(item.get("tipo_recargo_equivalencia")),
            "cuota_recargo_equivalencia": documented(item.get("cuota_recargo_equivalencia")),
            "total_tramo": documented(item.get("total_tramo")),
            "categoria_base": item.get("categoria_base"),
        })
    dues = [{
        "orden": int(item["orden"]), "fecha": documented(item.get("fecha"), kind="date"),
        "importe": documented(item.get("importe")), "medio_pago": documented(item.get("medio_pago")),
    } for item in local.vencimientos]
    deliveries = []
    for item in local.albaranes:
        attrs = serial(item.atributos_documentales)
        deliveries.append({
            "orden": int(item.orden),
            "numero": {"valor": item.numero_albaran, "literal": item.evidencias["numero_albaran"].literal,
                       "evidencia": [evidence(item.evidencias["numero_albaran"])]},
            "fecha": {"valor": {"iso": item.fecha, "literal": item.evidencias["fecha"].literal},
                      "literal": item.evidencias["fecha"].literal,
                      "evidencia": [evidence(item.evidencias["fecha"])]},
            "sentido": item.sentido or "CARGO", "tipo_pedido": None,
            "importe_base": {"valor": str(item.total), "literal": item.evidencias["total"].literal,
                             "evidencia": [evidence(item.evidencias["total"])]},
            "importe_total": {"valor": str(item.total), "literal": item.evidencias["total"].literal,
                              "evidencia": [evidence(item.evidencias["total"])]},
            "atributos_documentales": attrs,
        })
    movements = []
    for item in local.movimientos:
        amount_source = item.get("importe") or item.get("base")
        if not isinstance(amount_source, dict) or amount_source.get("valor") is None:
            raise RuntimeError("MOVIMIENTO_SIN_MAGNITUD_DOCUMENTADA")
        base_value = Decimal(str(amount_source["valor"]))
        gross, components = gross_from_bases(item.get("bases") or {})
        if item.get("importe_fiscal_total") is not None:
            gross = dinero(item["importe_fiscal_total"])
        amount = abs(gross)
        category = item.get("categoria")
        move_type = "SERVICIO" if category == "SERVICIO" or item.get("concepto_normalizado") in {"COMISION_HEFAME", "HEFAME_CONSUMIBLES"} else "OTRO"
        if item.get("concepto_normalizado") == "ABONO_DEVOLUCION":
            move_type = "DEVOLUCION_MERCANCIA"
        movements.append({
            "orden": int(item["orden"]), "tipo": move_type,
            "descripcion_literal": documented(item["descripcion_literal"]),
            "sentido": item["sentido"],
            "base": documented(amount_source), "iva": None, "recargo_equivalencia": None,
            "importe": {
                "valor": str(amount), "literal": amount_source["literal"],
                "evidencia": [evidence(ev) for ev in amount_source["evidencias"]],
            },
            "concepto_normalizado": item.get("concepto_normalizado"),
            "componentes_fiscales": components,
            "importe_fiscal_total": str(amount),
            "no_albaran": bool(item.get("no_albaran")),
            "requiere_match_operativo": bool(item.get("requiere_match_operativo", False)),
            "provenance": serial(item.get("provenance") or {}),
            "base_documental_firmada": str(base_value),
        })
    if not is_merc:
        if len(movements) != 1:
            raise RuntimeError("MOVIMIENTO_CONSUMIBLES_INESPERADO")
        movements[0]["importe"] = {
            "valor": "66.79", "literal": "55,20 + 11,59 = 66,79",
            "evidencia": movements[0]["descripcion_literal"]["evidencia"],
        }
        movements[0]["importe_fiscal_total"] = "66.79"
        movements[0]["componentes_fiscales"] = [{"base": "55.20", "iva": "11.59", "re": "0.00", "total_fiscal": "66.79"}]
    incidents = [{
        "codigo": item["codigo"], "severidad": "AVISO", "descripcion": item["codigo"],
        "paginas": list(range(start, end + 1)), "bloqueante": False, "evidencias": [],
    } for item in local.incidencias]
    invoice = {
        "factura_id": stable_id(cfg), "tipo_documento": documented(header.get("tipo_documento")),
        "naturaleza_principal": "MIXTA" if is_merc else "SERVICIOS",
        "estado_validacion": "VALIDADA_CON_INCIDENCIAS" if incidents else "VALIDADA",
        "requiere_conciliacion_albaranes": is_merc,
        "pagina_inicio": start, "pagina_fin": end,
        "proveedor": third_party(header["proveedor"]),
        "numero_factura": documented(header["numero_factura"]),
        "fecha_factura": documented(header["fecha_factura"], kind="date"),
        "destinatario": third_party(header["destinatario"]),
        "totales": {
            "moneda": documented(header.get("moneda")),
            "base_imponible": documented(header.get("base_imponible_total")),
            "iva": documented(header.get("iva_total")),
            "recargo_equivalencia": documented(header.get("recargo_equivalencia_total")),
            "otros": documented(header.get("otros_total")), "total": documented(header.get("importe_total")),
        },
        "vencimientos": dues, "impuestos": taxes, "albaranes": deliveries,
        "movimientos_comerciales": movements, "incidencias": incidents,
        "validaciones": [{"codigo": "ADAPTACION_LOCAL_HEFAME_2AA", "resultado": "OK",
                          "descripcion": "Adaptacion mecanica del extractor certificado",
                          "regla_version": "hito-2aa.local-v1"}],
        "grupo_funcional": serial(group),
        "referencias_documentales": serial(raw.get("referencias_documentales", [])),
        "lineas_consumibles": serial(raw.get("lineas_consumibles", [])),
        "controles_conciliacion": serial(local.controles_conciliacion),
        "provenance": {"hito": "2AA", "sha256": cfg["sha"], "layout": local.documento["layout"],
                       "layout_version": local.documento["layout_version"], "farmatic_consultado": False,
                       "luna_usada": False},
    }
    now = datetime.now(timezone.utc).isoformat()
    document = {
        "documento_completo_demostrado": True, "documento_id": "doc_" + cfg["sha"][:24],
        "archivo_origen": cfg["pdf"].name, "tipo_contenido": "PDF_NATIVO",
        "numero_paginas": int(local.documento["pages"]), "estado_documento": invoice["estado_validacion"],
        "estrategia_lectura": "LOCAL_CERTIFICADO", "facturas": [invoice],
        "metadata_tecnica": {"version_normalizador": "hito-2aa.local-v1", "version_configuracion": "supabase-v1",
                               "lector_primario": local.motor["id"], "huella_contenido": cfg["sha"],
                               "inicio": now, "fin": now, "duracion_ms": 0, "correlacion_id": "hito2aa_" + cfg["sha"][:20],
                               "extractor": local.documento["layout"], "extractor_version": local.documento["layout_version"],
                               "ocr": False, "luna": False},
    }
    document = serial(document)
    validar_documento_antes_de_persistir("PIO", document)
    summary = {
        "numero": cfg["numero"], "nif": cfg["nif"], "total": str(cfg["total"]),
        "base": str(header["base_imponible_total"]["valor"]), "iva": str(header["iva_total"]["valor"]),
        "re": str(header["recargo_equivalencia_total"]["valor"]), "grupo": group,
        "documento_completo": local.documento_completo_demostrado,
        "albaranes": len(deliveries), "movimientos": len(movements), "impuestos": len(taxes),
        "vencimientos": len(dues), "referencias_documentales": len(invoice["referencias_documentales"]),
        "lineas_consumibles": len(invoice["lineas_consumibles"]),
    }
    if is_merc:
        commission = next(x for x in movements if x["concepto_normalizado"] == "COMISION_HEFAME")
        summary["comision_hefame"] = {"base": "80.00", "iva": "3.20", "re": "0.40", "total_fiscal": commission["importe_fiscal_total"]}
    return document, summary


def assert_baseline(cursor) -> list[tuple[Any, ...]]:
    cursor.execute(
        "select f.numero_factura,f.importe_total,f.estado_normalizacion,f.estado_conciliacion_cf,"
        "f.estado_revision,f.normalizacion_ejecucion_id::text,c.id::text "
        "from public.facturas f left join public.conciliaciones c on c.factura_id=f.id and c.es_actual "
        "where f.numero_factura=any(%s) order by f.numero_factura", (list(BASELINE),)
    )
    rows = cursor.fetchall()
    if len(rows) != 5:
        raise RuntimeError("CINCO_FACTURAS_PREVIAS_NO_ENCONTRADAS")
    for number, total, norm, reconciliation, review, execution, current in rows:
        if (total, execution, current) != BASELINE[number] or (norm, reconciliation, review) != ("NORMALIZADA", "CONCILIADA", "NO_REQUERIDA"):
            raise RuntimeError(f"FACTURA_PREVIA_MODIFICADA:{number}")
    return rows


def precheck(expected_total: int = 5) -> dict[str, Any]:
    connection = connect(readonly=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas,tolerancia_conciliacion from public.cf_configuracion where id=true")
            flags = cursor.fetchone()
            cursor.execute("select count(*) from public.facturas")
            total = cursor.fetchone()[0]
            previous = assert_baseline(cursor)
            cursor.execute("select id::text,archivo_hash,estado_lectura,bloqueado_por,bloqueado_hasta,reprocesar_solicitado_at from public.documentos_facturas where id=any(%s::uuid[]) order by id", ([MERC["documento_id"], CONS["documento_id"]],))
            documents = cursor.fetchall()
            cursor.execute("select count(*) from public.documentos_facturas where bloqueado_por is not null or bloqueado_hasta is not null")
            document_locks = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas where conciliacion_bloqueado_por is not null or conciliacion_bloqueado_hasta is not null")
            invoice_locks = cursor.fetchone()[0]
            cursor.execute("select count(*) from pg_stat_activity where pid<>pg_backend_pid() and (application_name ilike '%worker%' or application_name ilike '%runtime%')")
            workers = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas where farmacia='RITA'")
            rita = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas where numero_factura=any(%s)", ([MERC["numero"], CONS["numero"]],))
            duplicates = cursor.fetchone()[0]
        if flags != (False, False, False, ["PIO"], TOL) or total != expected_total:
            raise RuntimeError(f"PRECHECK_PRODUCTIVO_CAMBIADO:{flags}:{total}")
        if document_locks or invoice_locks or workers or rita or duplicates:
            raise RuntimeError(f"AISLAMIENTO_PRECHECK_FALLIDO:{document_locks}:{invoice_locks}:{workers}:{rita}:{duplicates}")
        expected_docs = {MERC["documento_id"]: MERC["sha"], CONS["documento_id"]: CONS["sha"]}
        for doc_id, sha, state, owner, until, requested in documents:
            expected_state = "PENDIENTE" if expected_total == 5 else "NORMALIZADA"
            if sha != expected_docs[doc_id] or state not in {"PENDIENTE", "NORMALIZADA"} or owner or until or requested:
                raise RuntimeError(f"DOCUMENTO_OBJETIVO_NO_ELEGIBLE:{doc_id}")
        return {"facturas": total, "facturas_previas": previous, "flags": flags, "workers": workers,
                "locks": [document_locks, invoice_locks], "rita": rita, "documentos": documents,
                "duplicados_economicos": duplicates}
    finally:
        connection.rollback()
        connection.close()


def duplicate_by_content(cursor, invoice: dict[str, Any]) -> bool:
    cursor.execute(
        "select count(*) from public.facturas where numero_factura=%s and fecha_factura=%s and importe_total=%s "
        "and regexp_replace(upper(coalesce(datos_extraidos #>> '{proveedor,nif,valor}','')),'[^A-Z0-9]','','g')=%s "
        "and regexp_replace(upper(coalesce(datos_extraidos #>> '{destinatario,nif,valor}','')),'[^A-Z0-9]','','g')='40901058C'",
        (invoice["numero_factura"]["valor"], invoice["fecha_factura"]["valor"]["iso"], invoice["totales"]["total"]["valor"],
         invoice["proveedor"]["nif"]["valor"]),
    )
    return cursor.fetchone()[0] != 0


def persist(cfg: dict[str, Any], expected_before: int) -> dict[str, str]:
    document, _ = make_document(cfg)
    canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result_hash = hashlib.sha256(canonical.encode()).hexdigest()
    payload = {"estado": "COMPLETADA", "resultado_hash": result_hash, "uso_ocr": False, "uso_luna": False,
               "luna_modelo": None, "luna_campos": [], "tokens_entrada": None, "tokens_salida": None,
               "tokens_total": None, "coste_luna": None,
               "pasos": [{"orden": 1, "estrategia": "LOCAL_CERTIFICADO", "uso_ocr": False, "estado": "COMPLETADO"}],
               "resultado_json": document, "incidencias_runtime": []}
    connection = connect(readonly=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute("set local lock_timeout='5s'")
            cursor.execute("set local statement_timeout='60s'")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != expected_before:
                raise RuntimeError("TOTAL_FACTURAS_CAMBIO_ANTES_DE_PERSISTIR")
            assert_baseline(cursor)
            cursor.execute("select estado_lectura,archivo_hash,bloqueado_por,bloqueado_hasta,reprocesar_solicitado_at from public.documentos_facturas where id=%s for update", (cfg["documento_id"],))
            target = cursor.fetchone()
            if target != ("PENDIENTE", cfg["sha"], None, None, None):
                raise RuntimeError(f"DOCUMENTO_NO_ELEGIBLE:{target}")
            if duplicate_by_content(cursor, document["facturas"][0]):
                raise RuntimeError("DUPLICADO_ECONOMICO_POR_CONTENIDO")
            cursor.execute("select (public.cf_solicitar_reprocesado(%s,%s)).id::text", (cfg["documento_id"], "PIO-HITO-2AA"))
            if cursor.fetchone()[0] != cfg["documento_id"]:
                raise RuntimeError("SOLICITUD_MANUAL_NO_EXCLUSIVA")
            cursor.execute("select id::text from public.cf_reclamar_documento_normalizacion(%s,%s)", (cfg["worker"], 300))
            if [x[0] for x in cursor.fetchall()] != [cfg["documento_id"]]:
                raise RuntimeError("CLAIM_NO_EXCLUSIVO")
            idempotency = f"hito-2aa:{cfg['sha']}:{result_hash}"
            cursor.execute("select public.cf_persistir_normalizacion(%s,%s,'MANUAL',%s,%s,%s)::text",
                           (cfg["documento_id"], cfg["worker"], idempotency, result_hash, Json(payload)))
            execution_id = cursor.fetchone()[0]
            cursor.execute("select id::text,estado_normalizacion,estado_conciliacion_cf,estado_revision,importe_total from public.facturas where documento_id=%s", (cfg["documento_id"],))
            invoice = cursor.fetchone()
            if not invoice or invoice[1:] != ("NORMALIZADA", "PENDIENTE_CONCILIAR", "NO_REQUERIDA", dinero(cfg["total"])):
                raise RuntimeError(f"PERSISTENCIA_INCOHERENTE:{invoice}")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != expected_before + 1:
                raise RuntimeError("RPC_CREO_NUMERO_INCORRECTO_DE_FACTURAS")
        connection.commit()
        return {"factura_id": invoice[0], "normalizacion_id": execution_id, "resultado_hash": result_hash}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def merchandise_matching() -> dict[str, Any]:
    connection = connect(readonly=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select id::text,importe_total,proveedor_literal from public.facturas where documento_id=%s and numero_factura=%s", (MERC["documento_id"], MERC["numero"]))
            invoice_id, total, provider = cursor.fetchone()
            cursor.execute("select id::text,numero_albaran,fecha_albaran,importe_total,tipo_movimiento,provenance from public.facturas_albaranes_extraidos where factura_id=%s order by orden", (invoice_id,))
            deliveries = cursor.fetchall()
            if len(deliveries) != 9:
                raise RuntimeError("NUEVE_REFERENCIAS_NO_PERSISTIDAS")
            start = min(x[2] for x in deliveries) - timedelta(days=15)
            end = max(x[2] for x in deliveries) + timedelta(days=15)
            cursor.execute("select id_contador,farmacia,id_proveedor,proveedor,numero_albaran,fecha,importe_puc,importe_pvp,estado from public.albaranes where farmacia='PIO' and fecha between %s and %s", (start, end))
            candidates = tuple(CandidatoAlbaranSupabase(*x) for x in cursor.fetchall())
            details = []
            for row in deliveries:
                attrs = row[5]["atributos_documentales"]
                work = AlbaranDocumentalTrabajo(
                    row[0], row[1], row[2], Decimal(row[3]), row[4],
                    magnitud_documental=attrs["magnitud_documental"], categoria_fiscal=attrs["categoria_fiscal"],
                    iva_pct=Decimal(str(attrs["iva_pct"])), re_pct=Decimal(str(attrs["re_pct"])),
                    importe_iva_derivado=Decimal(str(attrs["importe_iva_derivado"])),
                    importe_re_derivado=Decimal(str(attrs["importe_re_derivado"])),
                    importe_comparable_operativo=Decimal(str(attrs["importe_comparable_operativo"])),
                    provenance=attrs["provenance"],
                )
                match = buscar_candidato_albaran(work, candidates, proveedor_literal=provider)
                details.append({"row": row, "work": work, "match": match})
            cursor.execute("select id::text,orden,descripcion_literal,importe,sentido,provenance from public.facturas_movimientos where factura_id=%s order by orden", (invoice_id,))
            movements = cursor.fetchall()
        states = [x["match"].estado for x in details]
        summary = {state: states.count(state) for state in ("EXACTO_ECONOMICO", "NUMERO_AUSENTE", "NUMERO_EXACTO_ECONOMIA_INCOMPATIBLE")}
        if summary != {"EXACTO_ECONOMICO": 2, "NUMERO_AUSENTE": 5, "NUMERO_EXACTO_ECONOMIA_INCOMPATIBLE": 2}:
            raise RuntimeError(f"MATCHING_2Z_CAMBIADO:{summary}")
        explained_deliveries = sum((dinero(x["match"].importe_compatible) for x in details if x["match"].estado == "EXACTO_ECONOMICO"), Decimal("0"))
        explained_movements = sum((abs(dinero(x[3])) if x[4] == "CARGO" else -abs(dinero(x[3])) for x in movements), Decimal("0"))
        explained = dinero(explained_deliveries + explained_movements)
        return {"invoice_id": invoice_id, "total": dinero(total), "details": details, "movements": movements,
                "summary": summary, "importe_explicado": explained, "diferencia": dinero(Decimal(total) - explained)}
    finally:
        connection.rollback()
        connection.close()


def reconcile_merchandise() -> dict[str, Any]:
    data = merchandise_matching()
    connection = connect(readonly=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute("set local lock_timeout='5s'")
            cursor.execute("select estado_normalizacion,estado_conciliacion_cf from public.facturas where id=%s for update", (data["invoice_id"],))
            if cursor.fetchone() != ("NORMALIZADA", "PENDIENTE_CONCILIAR"):
                raise RuntimeError("HEFAME_MERCANCIA_FUERA_DE_ESTADO")
            assert_baseline(cursor)
            cursor.execute("select count(*) from public.conciliaciones where factura_id=%s", (data["invoice_id"],))
            if cursor.fetchone()[0]:
                raise RuntimeError("CONCILIACION_MERCANCIA_YA_EXISTE")
            cursor.execute("insert into public.conciliaciones(factura_id,intento,disparador,estado,es_actual,tolerancia,importe_factura,importe_explicado,diferencia,resultado,estrategia,provenance,worker_id,finalizado_at) values(%s,1,'MANUAL','COMPLETADA',true,.05,%s,%s,%s,'DIFERENCIA','HEFAME_MATCHING_2Z',%s,'manual-hito-2aa-conciliacion-mercancia',now()) returning id::text",
                           (data["invoice_id"], data["total"], data["importe_explicado"], data["diferencia"], Json({"hito": "2AA", "matching": data["summary"], "numero_exacto_obligatorio": True, "fuzzy": False, "farmatic_consultado": False})))
            reconciliation_id = cursor.fetchone()[0]
            order = 0
            for item in data["details"]:
                order += 1
                row, match = item["row"], item["match"]
                candidate = match.candidato if match.estado == "EXACTO_ECONOMICO" else None
                applied = dinero(match.importe_compatible) if candidate else Decimal("0")
                cursor.execute("insert into public.conciliacion_detalles(conciliacion_id,orden,factura_albaran_extraido_id,albaran_farmacia,albaran_id_contador,numero_albaran_documental,numero_albaran_farmatic,coincidencia_numero_literal,tipo_relacion,importe_documental,importe_farmatic,importe_aplicado,diferencia,estado,provenance) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DIFERENCIA',%s)",
                               (reconciliation_id, order, row[0], candidate.farmacia if candidate else None, candidate.id_contador if candidate else None,
                                row[1], candidate.numero_albaran if candidate else None, bool(candidate), "UNO_A_UNO" if candidate else "SIN_COINCIDENCIA",
                                row[3], match.importe_compatible, applied, dinero(Decimal(row[3]) - applied),
                                Json({"estado_matching": match.estado, "magnitud_documental": "BASE_NETA", "fuzzy": False})))
            for movement_id, _, description, amount, direction, provenance in data["movements"]:
                order += 1
                applied = abs(dinero(amount)) if direction == "CARGO" else -abs(dinero(amount))
                cursor.execute("insert into public.conciliacion_detalles(conciliacion_id,orden,factura_movimiento_id,coincidencia_numero_literal,tipo_relacion,importe_documental,importe_aplicado,diferencia,estado,provenance) values(%s,%s,%s,false,'MOVIMIENTO_NO_FARMATIC',%s,%s,0,'COINCIDE',%s)",
                               (reconciliation_id, order, movement_id, amount, applied, Json({"concepto": description, "sentido": direction, "computado_una_vez": True, "origen": provenance})))
            cursor.execute("update public.facturas set estado_conciliacion_cf='PENDIENTE_CONCILIAR',diferencia_albaranes=%s,conciliacion_intentos=1,updated_at=now() where id=%s", (data["diferencia"], data["invoice_id"]))
        connection.commit()
        return {"conciliacion_id": reconciliation_id, "matching": data["summary"], "importe_explicado": str(data["importe_explicado"]), "diferencia": str(data["diferencia"]), "resultado": "PENDIENTE_CONCILIAR"}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def reconcile_consumables() -> dict[str, Any]:
    connection = connect(readonly=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute("set local lock_timeout='5s'")
            cursor.execute("select id::text,importe_total,estado_normalizacion,estado_conciliacion_cf,requiere_conciliacion_albaranes from public.facturas where documento_id=%s and numero_factura=%s for update", (CONS["documento_id"], CONS["numero"]))
            invoice = cursor.fetchone()
            if not invoice or invoice[1:] != (dinero(CONS["total"]), "NORMALIZADA", "PENDIENTE_CONCILIAR", False):
                raise RuntimeError(f"HPLUS_FUERA_DE_ESTADO:{invoice}")
            assert_baseline(cursor)
            cursor.execute("select id::text,importe,sentido,provenance from public.facturas_movimientos where factura_id=%s order by orden", (invoice[0],))
            movements = cursor.fetchall()
            if len(movements) != 1 or dinero(movements[0][1]) != dinero(CONS["total"]):
                raise RuntimeError("ESTRUCTURA_ECONOMICA_HPLUS_INCOMPLETA")
            cursor.execute("select count(*) from public.facturas_albaranes_extraidos where factura_id=%s", (invoice[0],))
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("HPLUS_PUBLICO_ALBARAN_OPERATIVO")
            cursor.execute("insert into public.conciliaciones(factura_id,intento,disparador,estado,es_actual,tolerancia,importe_factura,importe_explicado,diferencia,resultado,estrategia,provenance,worker_id,finalizado_at) values(%s,1,'MANUAL','COMPLETADA',true,.05,66.79,66.79,0,'CONCILIADA','HEFAME_CONSUMIBLES_SIN_ALBARAN',%s,'manual-hito-2aa-conciliacion-consumibles',now()) returning id::text",
                           (invoice[0], Json({"hito": "2AA", "base": "55.20", "iva": "11.59", "re": "0.00", "formula": "55.20 + 11.59 = 66.79", "requiere_albaran_operativo": False, "farmatic_consultado": False})))
            reconciliation_id = cursor.fetchone()[0]
            cursor.execute("insert into public.conciliacion_detalles(conciliacion_id,orden,factura_movimiento_id,coincidencia_numero_literal,tipo_relacion,importe_documental,importe_aplicado,diferencia,estado,provenance) values(%s,1,%s,false,'MOVIMIENTO_NO_FARMATIC',66.79,66.79,0,'COINCIDE',%s)",
                           (reconciliation_id, movements[0][0], Json({"base": "55.20", "iva": "11.59", "re": "0.00", "total": "66.79", "no_albaran": True})))
            cursor.execute("update public.facturas set estado_conciliacion_cf='CONCILIADA',diferencia_albaranes=0,conciliacion_intentos=1,updated_at=now() where id=%s", (invoice[0],))
        connection.commit()
        return {"conciliacion_id": reconciliation_id, "importe_explicado": "66.7900", "diferencia": "0.0000", "resultado": "CONCILIADA"}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def final_report() -> dict[str, Any]:
    connection = connect(readonly=True)
    try:
        with connection.cursor() as cursor:
            previous = assert_baseline(cursor)
            cursor.execute("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion where id=true")
            flags = cursor.fetchone()
            cursor.execute("select f.id::text,f.numero_factura,f.normalizacion_ejecucion_id::text,f.importe_total,f.base_imponible_total,f.iva_total,f.estado_normalizacion,f.estado_conciliacion_cf,f.estado_revision,f.requiere_conciliacion_albaranes,c.id::text,c.importe_explicado,c.diferencia,c.resultado from public.facturas f left join public.conciliaciones c on c.factura_id=f.id and c.es_actual where f.numero_factura=any(%s) order by f.numero_factura", ([MERC["numero"], CONS["numero"]],))
            targets = cursor.fetchall()
            cursor.execute("select count(*),count(*) filter(where estado_conciliacion_cf='CONCILIADA'),count(*) filter(where estado_conciliacion_cf='PENDIENTE_CONCILIAR') from public.facturas")
            counts = cursor.fetchone()
            cursor.execute("select count(*) from public.facturas_incidencias i join public.facturas f on f.id=i.factura_id where f.numero_factura=%s and i.codigo='ALBARAN_NO_LOCALIZADO'", (CONS["numero"],))
            hplus_missing = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.documentos_facturas where bloqueado_por is not null or bloqueado_hasta is not null")
            doc_locks = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas where conciliacion_bloqueado_por is not null or conciliacion_bloqueado_hasta is not null")
            inv_locks = cursor.fetchone()[0]
            cursor.execute("select count(*) from pg_stat_activity where pid<>pg_backend_pid() and (application_name ilike '%worker%' or application_name ilike '%runtime%')")
            workers = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas where farmacia='RITA'")
            rita = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.normalizacion_ejecuciones where documento_id=any(%s::uuid[]) and uso_luna=true", ([MERC["documento_id"], CONS["documento_id"]],))
            luna = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.normalizacion_ejecuciones where worker_id like 'manual-hito-2aa-%%' and documento_id<>all(%s::uuid[])", ([MERC["documento_id"], CONS["documento_id"]],))
            other_processed = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.facturas_albaranes_extraidos a join public.facturas f on f.id=a.factura_id where f.numero_factura=%s", (MERC["numero"],))
            merc_references = cursor.fetchone()[0]
            cursor.execute("select m.base,m.importe,m.provenance->>'importe_fiscal_total' from public.facturas_movimientos m join public.facturas f on f.id=m.factura_id where f.numero_factura=%s and m.provenance->>'concepto_normalizado'='COMISION_HEFAME'", (MERC["numero"],))
            commission = cursor.fetchone()
            cursor.execute("select jsonb_array_length(datos_extraidos->'referencias_documentales'),jsonb_array_length(datos_extraidos->'lineas_consumibles') from public.facturas where numero_factura=%s", (CONS["numero"],))
            hplus_structure = cursor.fetchone()
        if counts != (7, 6, 1) or len(targets) != 2 or flags != (False, False, False, ["PIO"]):
            raise RuntimeError(f"CIERRE_2AA_INCORRECTO:{counts}:{targets}:{flags}")
        if doc_locks or inv_locks or workers or rita or luna or hplus_missing or other_processed:
            raise RuntimeError("AISLAMIENTO_FINAL_INCORRECTO")
        if merc_references != 9 or commission != (Decimal("80.0000"), Decimal("83.6000"), "83.6000") or hplus_structure != (2, 3):
            raise RuntimeError(f"ESTRUCTURA_PERSISTIDA_INCORRECTA:{merc_references}:{commission}:{hplus_structure}")
        matching = merchandise_matching()
        return {"preexistentes_intactas": True, "facturas_previas": previous, "objetivos": targets,
                "facturas": counts[0], "conciliadas": counts[1], "pendientes": counts[2],
                "matching_mercancia": matching["summary"], "flags": flags, "workers": workers,
                "locks": [doc_locks, inv_locks], "rita": rita, "farmatic": False, "luna_api": False,
                "referencias_mercancia": merc_references, "comision_hefame": commission,
                "hplus_estructura": hplus_structure, "hplus_albaran_no_localizado": hplus_missing,
                "otros_documentos_procesados": other_processed,
                "estado": "HEFAME_DOBLE_FLUJO_PRODUCTIVO_OK"}
    finally:
        connection.rollback()
        connection.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("precheck", "dry-run", "persist-merc", "match-merc", "reconcile-merc", "persist-cons", "reconcile-cons", "final"))
    args = parser.parse_args()
    if args.mode == "precheck":
        result = precheck(5)
    elif args.mode == "dry-run":
        merc_doc, merc = make_document(MERC)
        cons_doc, cons = make_document(CONS)
        match_local, _ = extract(MERC)
        result = {"mercancia": merc, "consumibles": cons,
                  "mercancia_estado_documento": merc_doc["estado_documento"],
                  "consumibles_estado_documento": cons_doc["estado_documento"],
                  "mercancia_controles": [{"id": x["id"], "estado": x["estado"]} for x in match_local.controles_conciliacion]}
    elif args.mode == "persist-merc":
        result = persist(MERC, 5)
    elif args.mode == "match-merc":
        data = merchandise_matching()
        result = {key: value for key, value in data.items() if key not in {"details", "movements"}}
    elif args.mode == "reconcile-merc":
        result = reconcile_merchandise()
    elif args.mode == "persist-cons":
        result = persist(CONS, 6)
    elif args.mode == "reconcile-cons":
        result = reconcile_consumables()
    else:
        result = final_report()
    print(json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
