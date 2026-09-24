"""Renormalizacion 2K acotada: nueva ejecucion, misma proyeccion economica."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))

import psycopg2
from psycopg2.extras import Json

from pruebas.piloto_productivo_2i import normalizar_en_memoria
from src.facturas.completitud_documental import validar_documento_antes_de_persistir


DOCUMENTO_ID = "0387e00a-e861-48f0-88ad-9236b92078e8"
FACTURA_ID = "14f7808e-cb2b-41fd-94fb-6eb82703de21"
WORKER = "manual-hito-2k-renormalizacion"


def _valor(campo):
    if campo is None:
        return None
    valor = campo.get("valor") if isinstance(campo, dict) else campo
    return valor.get("iso") if isinstance(valor, dict) and "iso" in valor else valor


def _resumen_funcional(documento):
    facturas = documento.get("facturas") or []
    if len(facturas) != 1:
        raise RuntimeError("se esperaba exactamente una factura normalizada")
    f = facturas[0]
    return {
        "proveedor": _valor((f.get("proveedor") or {}).get("nombre")),
        "numero": _valor(f.get("numero_factura")),
        "fecha": _valor(f.get("fecha_factura")),
        "destinatario": _valor((f.get("destinatario") or {}).get("nombre")),
        "totales": {k: _valor(v) for k, v in (f.get("totales") or {}).items()},
        "vencimientos": [
            (v.get("orden"), _valor(v.get("fecha")), _valor(v.get("importe")))
            for v in f.get("vencimientos", [])
        ],
        "impuestos": [
            (i.get("orden"), _valor(i.get("base")), _valor(i.get("tipo_iva")),
             _valor(i.get("cuota_iva")), _valor(i.get("tipo_recargo_equivalencia")),
             _valor(i.get("cuota_recargo_equivalencia")))
            for i in f.get("impuestos", [])
        ],
        "albaranes": [
            (a.get("orden"), _valor(a.get("numero")), _valor(a.get("fecha")),
             _valor(a.get("importe_total")), a.get("sentido"))
            for a in f.get("albaranes", [])
        ],
        "movimientos": f.get("movimientos_comerciales") or [],
        "incidencias": [
            (i.get("codigo"), i.get("bloqueante")) for i in f.get("incidencias", [])
        ],
    }


def main():
    documento, _ = normalizar_en_memoria()
    documento["metadata_tecnica"]["contrato_documental"] = "2J.1"
    if validar_documento_antes_de_persistir("PIO", documento) != "CONSISTENTE":
        raise RuntimeError("barreras documentales no superadas")
    canonico = json.dumps(documento, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    resultado_hash = hashlib.sha256(canonico.encode("utf-8")).hexdigest()
    idempotency_key = f"hito-2k:{documento['metadata_tecnica']['huella_contenido']}:{resultado_hash}"

    conexion = psycopg2.connect(os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"])
    try:
        with conexion.cursor() as cursor:
            cursor.execute("set local lock_timeout = '5s'")
            cursor.execute("set local statement_timeout = '60s'")
            cursor.execute("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion where id=true")
            if cursor.fetchone() != (False, False, False, ["PIO"]):
                raise RuntimeError("flags productivos no seguros")
            cursor.execute("select farmacia,estado_lectura from public.documentos_facturas where id=%s for update", (DOCUMENTO_ID,))
            if cursor.fetchone() != ("PIO", "NORMALIZADA"):
                raise RuntimeError("documento objetivo fuera del estado esperado")
            cursor.execute("select normalizacion_ejecucion_id::text,numero_factura,importe_total from public.facturas where id=%s and documento_id=%s for update", (FACTURA_ID, DOCUMENTO_ID))
            factura = cursor.fetchone()
            if factura is None or factura[1:] != ("5011640669", 448):
                raise RuntimeError("factura objetivo fuera del estado esperado")
            normalizacion_anterior = factura[0]
            cursor.execute("select resultado_json from public.normalizacion_ejecuciones where id=%s", (normalizacion_anterior,))
            persistido = cursor.fetchone()[0]
            if _resumen_funcional(persistido) != _resumen_funcional(documento):
                raise RuntimeError("DIFERENCIA_FUNCIONAL: renormalizacion abortada")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("existen facturas ajenas al alcance")
            cursor.execute("select count(*) from public.conciliaciones where factura_id=%s", (FACTURA_ID,))
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("historico de conciliacion inesperado")
            cursor.execute("select factura_albaran_extraido_id::text from public.conciliacion_detalles where conciliacion_id=(select id from public.conciliaciones where factura_id=%s and intento=1)", (FACTURA_ID,))
            detalle_historico = cursor.fetchone()[0]
            cursor.execute("select id::text from public.normalizacion_ejecuciones where documento_id=%s and idempotency_key=%s", (DOCUMENTO_ID, idempotency_key))
            existente = cursor.fetchone()
            if existente:
                nueva_id = existente[0]
            else:
                cursor.execute("select coalesce(max(intento),0)+1 from public.normalizacion_ejecuciones where documento_id=%s", (DOCUMENTO_ID,))
                intento = cursor.fetchone()[0]
                cursor.execute(
                    """insert into public.normalizacion_ejecuciones
                    (documento_id,idempotency_key,intento,disparador,estado,normalizador_version,
                     resultado_hash,uso_ocr,uso_luna,luna_campos,pasos,resultado_json,worker_id,
                     iniciado_at,finalizado_at)
                    values (%s,%s,%s,'REPROCESADO','COMPLETADA',%s,%s,false,false,'{}',%s,%s,%s,now(),now())
                    returning id::text""",
                    (DOCUMENTO_ID, idempotency_key, intento,
                     documento["metadata_tecnica"]["version_normalizador"], resultado_hash,
                     Json([{"orden": 1, "estrategia": "LOCAL_CERTIFICADO_2J1", "uso_ocr": False, "estado": "COMPLETADO"}]),
                     Json(documento), WORKER),
                )
                nueva_id = cursor.fetchone()[0]
                cursor.execute(
                    """update public.facturas set normalizacion_ejecucion_id=%s,
                    provenance=jsonb_build_object('fuente','DOCUMENTO_NORMALIZADO','ejecucion_id',%s::uuid),
                    updated_at=now(),fecha_actualizacion=now()
                    where id=%s and normalizacion_ejecucion_id=%s::uuid""",
                    (nueva_id, nueva_id, FACTURA_ID, normalizacion_anterior),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("no se pudo enlazar exclusivamente la factura objetivo")
                cursor.execute(
                    """insert into public.historial_facturas
                    (documento_id,factura_id,evento,origen,actor,estado_anterior,estado_nuevo,detalle)
                    values (%s,%s,'PROYECCION_NORMALIZACION_REVALIDADA','CONTROL_2K',%s,
                    jsonb_build_object('normalizacion_ejecucion_id',%s::text),
                    jsonb_build_object('normalizacion_ejecucion_id',%s::text,'documento_completo_demostrado',true),
                    jsonb_build_object('campos_economicos_modificados',false,'contrato_documental','2J.1'))""",
                    (DOCUMENTO_ID, FACTURA_ID, WORKER, normalizacion_anterior, nueva_id),
                )
            cursor.execute("select resultado_json->>'documento_completo_demostrado' from public.normalizacion_ejecuciones where id=%s", (nueva_id,))
            if cursor.fetchone()[0] != "true":
                raise RuntimeError("marca de completitud no persistida")
            cursor.execute("select factura_albaran_extraido_id::text from public.conciliacion_detalles where conciliacion_id=(select id from public.conciliaciones where factura_id=%s and intento=1)", (FACTURA_ID,))
            if cursor.fetchone()[0] != detalle_historico:
                raise RuntimeError("detalle historico alterado")
            cursor.execute("select count(*) from public.facturas_incidencias where factura_id=%s and codigo='SENTIDO_NO_DOCUMENTADO' and estado='ABIERTA'", (FACTURA_ID,))
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("incidencia legitima alterada")
        conexion.commit()
        print(json.dumps({
            "documento_id": DOCUMENTO_ID,
            "factura_id": FACTURA_ID,
            "normalizacion_anterior": normalizacion_anterior,
            "normalizacion_nueva": nueva_id,
            "documento_completo_demostrado": True,
            "campos_economicos_modificados": False,
            "detalle_historico_preservado": detalle_historico,
            "incidencia_preservada": "SENTIDO_NO_DOCUMENTADO",
        }, sort_keys=True))
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
