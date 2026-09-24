"""Matching READ_ONLY y conciliacion manual acotada de Alliance 08009277."""
from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tmp_pg_probe_deps")]

import psycopg2
from psycopg2.extras import Json

from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    buscar_candidato_albaran,
    dinero,
)


DOCUMENTO = "ffee3c1c-ebcc-4287-99b2-79ccbae45f22"
OBJETIVO = "08009277"
WORKER = "manual-hito-2v-conciliacion-08009277"


def conectar(readonly=False):
    conexion = psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"], sslmode="require",
        connect_timeout=10, application_name=f"cf_2v_{'readonly' if readonly else 'conciliacion'}",
    )
    conexion.set_session(readonly=readonly, autocommit=False)
    return conexion


def construir_matching():
    conexion = conectar(readonly=True)
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                "select id::text,importe_total,proveedor_literal from public.facturas "
                "where documento_id=%s and numero_factura=%s",
                (DOCUMENTO, OBJETIVO),
            )
            factura_id, total, proveedor = cursor.fetchone()
            cursor.execute(
                "select id::text,numero_albaran,fecha_albaran,importe_total,tipo_movimiento "
                "from public.facturas_albaranes_extraidos where factura_id=%s order by orden",
                (factura_id,),
            )
            documentales = cursor.fetchall()
            if len(documentales) != 160:
                raise RuntimeError("ALBARANES_MERCANCIA_NO_CERTIFICADOS")
            fechas = [x[2] for x in documentales]
            inicio, fin = min(fechas) - timedelta(days=15), max(fechas) + timedelta(days=15)
            cursor.execute(
                "select id_contador,farmacia,id_proveedor,proveedor,numero_albaran,fecha,"
                "importe_puc,importe_pvp,estado from public.albaranes "
                "where farmacia='PIO' and fecha between %s and %s",
                (inicio, fin),
            )
            candidatos = tuple(CandidatoAlbaranSupabase(*x) for x in cursor.fetchall())
            detalles = []
            for aid, numero, fecha, importe, sentido in documentales:
                documental = AlbaranDocumentalTrabajo(aid, numero, fecha, Decimal(importe), sentido)
                match = buscar_candidato_albaran(documental, candidatos, proveedor_literal=proveedor)
                clase = (
                    "EXACTO" if match.estado == "MATCH_UNICO" and match.coincidencia_numero == "EXACTA"
                    else "ECONOMICO_UNICO" if match.estado == "MATCH_UNICO"
                    else "AMBIGUO" if match.estado == "AMBIGUO"
                    else "NO_LOCALIZADO"
                )
                detalles.append({
                    "id": aid, "numero": numero, "fecha": fecha,
                    "importe": dinero(importe), "sentido": sentido,
                    "clase": clase, "match": match,
                })
            cursor.execute(
                "select id::text,descripcion_literal,importe,sentido from public.facturas_movimientos "
                "where factura_id=%s order by orden", (factura_id,),
            )
            movimientos = cursor.fetchall()
            resumen = {k: sum(x["clase"] == k for x in detalles)
                       for k in ("EXACTO", "ECONOMICO_UNICO", "AMBIGUO", "NO_LOCALIZADO")}
            explicado_albaranes = sum((
                -abs(dinero(x["match"].importe_compatible)) if x["sentido"] == "ABONO"
                else dinero(x["match"].importe_compatible)
                for x in detalles if x["match"].candidato
            ), Decimal("0"))
            explicado_movimientos = sum((
                abs(dinero(x[2])) if x[3] == "CARGO" else -abs(dinero(x[2]))
                for x in movimientos
            ), Decimal("0"))
            explicado = dinero(explicado_albaranes + explicado_movimientos)
            diferencia = dinero(Decimal(total) - explicado)
            if resumen != {"EXACTO": 157, "ECONOMICO_UNICO": 3, "AMBIGUO": 0, "NO_LOCALIZADO": 0}:
                raise RuntimeError(f"MATCHING_NO_CERTIFICADO:{resumen}")
            if len(movimientos) != 7 or abs(diferencia) > Decimal("0.0500"):
                raise RuntimeError(f"CUADRE_NO_CERTIFICADO:{len(movimientos)}:{diferencia}")
            return {
                "factura_id": factura_id, "total": dinero(total), "proveedor": proveedor,
                "detalles": detalles, "movimientos": movimientos, "resumen": resumen,
                "importe_explicado": explicado, "diferencia": diferencia,
                "candidatos_operacionales": len(candidatos),
            }
    finally:
        conexion.rollback()
        conexion.close()


def mostrar():
    datos = construir_matching()
    print(json.dumps({
        "factura": OBJETIVO, "albaranes_mercancia": len(datos["detalles"]),
        "movimientos": len(datos["movimientos"]), "matching": datos["resumen"],
        "importe_factura": datos["total"], "importe_explicado": datos["importe_explicado"],
        "diferencia": datos["diferencia"],
        "candidatos_operacionales_ventana": datos["candidatos_operacionales"],
        "modo": "READ_ONLY",
    }, default=str, ensure_ascii=False))


def conciliar():
    datos = construir_matching()
    conexion = conectar()
    try:
        with conexion.cursor() as cursor:
            cursor.execute("set local lock_timeout='5s'")
            cursor.execute("set local statement_timeout='60s'")
            cursor.execute(
                "select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas "
                "from public.cf_configuracion where id=true"
            )
            if cursor.fetchone() != (False, False, False, ["PIO"]):
                raise RuntimeError("FLAGS_PRODUCTIVOS_NO_SEGUROS")
            cursor.execute(
                "select numero_factura,normalizacion_ejecucion_id::text,estado_normalizacion,"
                "estado_conciliacion_cf,importe_total,proveedor_id::text from public.facturas "
                "where id=%s for update", (datos["factura_id"],),
            )
            objetivo = cursor.fetchone()
            if objetivo[0:5] != (
                OBJETIVO, "4ce09682-d80a-4f7b-9ad8-d5256a3f4d6c",
                "NORMALIZADA", "PENDIENTE_CONCILIAR", Decimal("10111.5500"),
            ):
                raise RuntimeError(f"OBJETIVO_FUERA_DE_ESTADO:{objetivo}")
            cursor.execute(
                "select numero_factura,normalizacion_ejecucion_id::text,estado_conciliacion_cf,"
                "diferencia_albaranes from public.facturas where documento_id=%s and numero_factura<>%s "
                "order by numero_factura", (DOCUMENTO, OBJETIVO),
            )
            hermanas = cursor.fetchall()
            if len(hermanas) != 2 or any(x[2] != "CONCILIADA" for x in hermanas):
                raise RuntimeError("HERMANAS_FUERA_DE_ESTADO")
            cursor.execute("select coalesce(max(intento),0)+1 from public.conciliaciones where factura_id=%s", (datos["factura_id"],))
            intento = cursor.fetchone()[0]
            cursor.execute("update public.conciliaciones set es_actual=false where factura_id=%s and es_actual", (datos["factura_id"],))
            cursor.execute(
                """insert into public.conciliaciones(
                factura_id,intento,disparador,estado,es_actual,tolerancia,importe_factura,
                importe_explicado,diferencia,resultado,estrategia,provenance,worker_id,finalizado_at)
                values(%s,%s,'MANUAL','COMPLETADA',true,.05,%s,%s,%s,'CONCILIADA',
                'MATCHING_CERTIFICADO_V2',%s,%s,now()) returning id::text""",
                (datos["factura_id"], intento, datos["total"], datos["importe_explicado"],
                 datos["diferencia"], Json({
                     "fuente": "SUPABASE_ALBARANES",
                     "hito": "2V",
                     "regla": "SOLO_ALBARANES_MERCANCIA_CLASIFICADOS",
                     "matching": datos["resumen"],
                     "tolerancia": "0.0500",
                     "force": False,
                 }), WORKER),
            )
            conciliacion_id = cursor.fetchone()[0]
            orden = 0
            for item in datos["detalles"]:
                orden += 1
                match, candidato = item["match"], item["match"].candidato
                aplicado = (-abs(dinero(match.importe_compatible)) if item["sentido"] == "ABONO"
                            else dinero(match.importe_compatible))
                cursor.execute(
                    """insert into public.conciliacion_detalles(
                    conciliacion_id,orden,factura_albaran_extraido_id,albaran_farmacia,
                    albaran_id_contador,numero_albaran_documental,numero_albaran_farmatic,
                    coincidencia_numero_literal,tipo_relacion,importe_documental,importe_farmatic,
                    importe_aplicado,diferencia,estado,provenance)
                    values(%s,%s,%s,%s,%s,%s,%s,%s,'UNO_A_UNO',%s,%s,%s,%s,'COINCIDE',%s)""",
                    (conciliacion_id, orden, item["id"], candidato.farmacia,
                     candidato.id_contador, item["numero"], candidato.numero_albaran,
                     match.coincidencia_numero == "EXACTA", item["importe"],
                     match.importe_compatible, aplicado, dinero(item["importe"] - aplicado),
                     Json({"fuente": "ALBARANES_SUPABASE", "hito": "2V",
                           "estado_matching": item["clase"], "force": False})),
                )
            for movimiento_id, descripcion, importe, sentido in datos["movimientos"]:
                orden += 1
                aplicado = abs(dinero(importe)) if sentido == "CARGO" else -abs(dinero(importe))
                cursor.execute(
                    """insert into public.conciliacion_detalles(
                    conciliacion_id,orden,factura_movimiento_id,coincidencia_numero_literal,
                    tipo_relacion,importe_documental,importe_aplicado,diferencia,estado,provenance)
                    values(%s,%s,%s,false,'MOVIMIENTO_NO_FARMATIC',%s,%s,0,'COINCIDE',%s)""",
                    (conciliacion_id, orden, movimiento_id, importe, aplicado,
                     Json({"fuente": "MOVIMIENTO_DOCUMENTAL", "hito": "2V",
                           "concepto_literal": descripcion, "sentido": sentido})),
                )
            cursor.execute(
                """update public.facturas set estado_conciliacion_cf='CONCILIADA',
                diferencia_albaranes=%s,conciliacion_intentos=%s,
                conciliacion_bloqueado_hasta=null,conciliacion_bloqueado_por=null,
                conciliacion_reintento_solicitado_at=null,updated_at=now() where id=%s""",
                (datos["diferencia"], intento, datos["factura_id"]),
            )
            cursor.execute(
                "select numero_factura,normalizacion_ejecucion_id::text,estado_conciliacion_cf,"
                "diferencia_albaranes from public.facturas where documento_id=%s and numero_factura<>%s "
                "order by numero_factura", (DOCUMENTO, OBJETIVO),
            )
            if cursor.fetchall() != hermanas:
                raise RuntimeError("AISLAMIENTO_HERMANAS_VIOLADO")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != 5:
                raise RuntimeError("TOTAL_FACTURAS_MODIFICADO")
        conexion.commit()
        print(json.dumps({
            "factura": OBJETIVO, "conciliacion_id": conciliacion_id,
            "intento": intento, "resultado": "CONCILIADA",
            "matching": datos["resumen"], "albaranes": len(datos["detalles"]),
            "movimientos": len(datos["movimientos"]),
            "importe_explicado": datos["importe_explicado"], "diferencia": datos["diferencia"],
            "force": False, "hermanas_intactas": True,
        }, default=str, ensure_ascii=False))
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"match", "conciliar"}:
        raise SystemExit("uso: match|conciliar")
    mostrar() if sys.argv[1] == "match" else conciliar()
