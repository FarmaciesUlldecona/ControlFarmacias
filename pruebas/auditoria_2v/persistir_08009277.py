"""Hito 2V: renormalizacion productiva, transaccional y aislada de 08009277."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tmp_pg_probe_deps")]

import psycopg2
from psycopg2.extras import Json

from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.runtime_supabase.multifactura import adaptar_resultado_local


DOCUMENTO = "ffee3c1c-ebcc-4287-99b2-79ccbae45f22"
OBJETIVO = "08009277"
HERMANAS = ("08009278", "08009279")
WORKER = "manual-hito-2v-renormalizacion-08009277"
PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf"


def payload_objetivo():
    local = MotorDocumentoLocal(BackendPdfium()).extraer(PDF)
    normalizado = adaptar_resultado_local(local)
    facturas = [f for f in normalizado["facturas"] if f["numero_factura"]["valor"] == OBJETIVO]
    if len(facturas) != 1:
        raise RuntimeError("FACTURA_OBJETIVO_NO_UNICA")
    factura = facturas[0]
    if len(factura["albaranes"]) != 160 or len(factura["movimientos_comerciales"]) != 7:
        raise RuntimeError("PROYECCION_2V_NO_CERTIFICADA")
    if len(factura["extraccion_local"]["operaciones_economicas"]) != 5:
        raise RuntimeError("OPERACIONES_ECONOMICAS_2V_INCOMPLETAS")
    factura["provenance"] = {
        **factura["provenance"],
        "alcance_persistencia": "SOLO_FACTURA_08009277",
        "autoridad": "HITO_2V_PIO",
    }
    normalizado["facturas"] = facturas
    normalizado["metadata_tecnica"] = {
        **normalizado["metadata_tecnica"],
        "version_normalizador": "multifactura-local-2v",
        "alcance_persistencia": "SOLO_FACTURA_08009277",
        "autoridad": "HITO_2V_PIO",
    }
    canonico = json.dumps(normalizado, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    resultado_hash = hashlib.sha256(canonico.encode("utf-8")).hexdigest()
    return normalizado, resultado_hash


def main():
    payload, resultado_hash = payload_objetivo()
    idempotencia = f"hito-2v:{DOCUMENTO}:{OBJETIVO}:{resultado_hash}"
    conexion = psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"], sslmode="require",
        connect_timeout=10, application_name="cf_2v_persistencia_controlada",
    )
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
                "select estado_lectura,estado_persistencia,cantidad_documentos_detectados,tipo_contenido,"
                "inventario_facturas,numero_paginas from public.documentos_facturas where id=%s for update",
                (DOCUMENTO,),
            )
            doc_antes = cursor.fetchone()
            if not doc_antes or doc_antes[:4] != ("NORMALIZADA", "COMPLETA", 3, "LOTE_FACTURAS"):
                raise RuntimeError("DOCUMENTO_MULTIFACTURA_FUERA_DE_ESTADO")
            if len(doc_antes[4]) != 3 or doc_antes[5] != 11:
                raise RuntimeError("INVENTARIO_MULTIFACTURA_INESPERADO")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != 5:
                raise RuntimeError("TOTAL_FACTURAS_INESPERADO")
            cursor.execute(
                "select id::text,normalizacion_ejecucion_id::text,estado_normalizacion,estado_conciliacion_cf,"
                "importe_total,proveedor_id::text from public.facturas where documento_id=%s and numero_factura=%s for update",
                (DOCUMENTO, OBJETIVO),
            )
            objetivo_antes = cursor.fetchone()
            if not objetivo_antes or objetivo_antes[2:5] != (
                "NORMALIZADA", "PENDIENTE_CONCILIAR", Decimal("10111.5500")
            ):
                raise RuntimeError("FACTURA_OBJETIVO_FUERA_DE_ESTADO")
            factura_id, ejecucion_anterior = objetivo_antes[:2]
            cursor.execute(
                "select f.numero_factura,f.normalizacion_ejecucion_id::text,f.estado_normalizacion,"
                "f.estado_conciliacion_cf,f.importe_total,f.datos_extraidos,"
                "(select count(*) from public.facturas_albaranes_extraidos a where a.factura_id=f.id),"
                "(select count(*) from public.facturas_movimientos m where m.factura_id=f.id),"
                "(select row_to_json(c) from public.conciliaciones c where c.factura_id=f.id and c.es_actual) "
                "from public.facturas f where f.documento_id=%s and f.numero_factura=any(%s) order by f.numero_factura",
                (DOCUMENTO, list(HERMANAS)),
            )
            hermanas_antes = cursor.fetchall()
            if len(hermanas_antes) != 2 or any(x[3] != "CONCILIADA" for x in hermanas_antes):
                raise RuntimeError("FACTURAS_HERMANAS_FUERA_DE_ESTADO")
            cursor.execute("select count(*) from public.conciliaciones")
            conciliaciones_antes = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.normalizacion_ejecuciones")
            ejecuciones_antes = cursor.fetchone()[0]
            cursor.execute(
                "select id::text from public.normalizacion_ejecuciones where documento_id=%s and idempotency_key=%s",
                (DOCUMENTO, idempotencia),
            )
            existente = cursor.fetchone()
            if existente:
                nueva_ejecucion = existente[0]
            else:
                cursor.execute(
                    """create temporary table cf_2v_detalles_snapshot on commit drop as
                    select cd.id detalle_id,cd.tipo_relacion tipo_relacion_anterior,
                           cd.factura_albaran_extraido_id albaran_anterior,
                           cd.factura_movimiento_id movimiento_anterior,
                           a.numero_albaran,a.fecha_albaran,a.importe_total importe_albaran,
                           a.tipo_movimiento sentido_albaran,
                           m.descripcion_literal,m.importe importe_movimiento,m.sentido sentido_movimiento
                      from public.conciliacion_detalles cd
                      join public.conciliaciones c on c.id=cd.conciliacion_id
                      left join public.facturas_albaranes_extraidos a on a.id=cd.factura_albaran_extraido_id
                      left join public.facturas_movimientos m on m.id=cd.factura_movimiento_id
                     where c.factura_id=%s""",
                    (factura_id,),
                )
                cursor.execute(
                    """update public.conciliacion_detalles cd set tipo_relacion='SIN_COINCIDENCIA'
                      from cf_2v_detalles_snapshot s
                     where cd.id=s.detalle_id and cd.tipo_relacion<>'SIN_COINCIDENCIA'"""
                )
                cursor.execute(
                    "update public.documentos_facturas set bloqueado_por=%s,bloqueado_hasta=now()+interval '120 seconds',"
                    "estado_lectura='NORMALIZANDO' where id=%s",
                    (WORKER, DOCUMENTO),
                )
                cursor.execute(
                    "select public.cf_persistir_normalizacion(%s,%s,'REPROCESADO',%s,%s,%s)::text",
                    (DOCUMENTO, WORKER, idempotencia, resultado_hash, Json(payload)),
                )
                nueva_ejecucion = cursor.fetchone()[0]
                cursor.execute(
                    """update public.conciliacion_detalles cd
                          set factura_albaran_extraido_id=a.id
                         from cf_2v_detalles_snapshot s
                         join public.facturas_albaranes_extraidos a
                           on a.factura_id=%s
                          and a.numero_albaran=s.numero_albaran
                          and a.fecha_albaran is not distinct from s.fecha_albaran
                          and a.importe_total is not distinct from s.importe_albaran
                          and a.tipo_movimiento is not distinct from s.sentido_albaran
                        where cd.id=s.detalle_id and s.albaran_anterior is not null""",
                    (factura_id,),
                )
                cursor.execute(
                    """update public.conciliacion_detalles cd
                          set factura_movimiento_id=m.id
                         from cf_2v_detalles_snapshot s
                         join public.facturas_movimientos m
                           on m.factura_id=%s
                          and m.descripcion_literal=s.descripcion_literal
                          and m.importe is not distinct from s.importe_movimiento
                          and m.sentido is not distinct from s.sentido_movimiento
                        where cd.id=s.detalle_id and s.movimiento_anterior is not null""",
                    (factura_id,),
                )
                cursor.execute(
                    """update public.conciliacion_detalles cd
                          set factura_movimiento_id=m.id
                         from cf_2v_detalles_snapshot s
                         join public.facturas_movimientos m
                           on m.factura_id=%s
                          and m.importe is not distinct from s.importe_albaran
                          and m.sentido is not distinct from s.sentido_albaran
                        where cd.id=s.detalle_id
                          and s.numero_albaran='08C61795'
                          and cd.factura_albaran_extraido_id is null""",
                    (factura_id,),
                )
                cursor.execute(
                    """update public.conciliacion_detalles cd
                          set tipo_relacion=s.tipo_relacion_anterior
                         from cf_2v_detalles_snapshot s
                        where cd.id=s.detalle_id
                          and s.tipo_relacion_anterior<>'SIN_COINCIDENCIA'
                          and num_nonnulls(cd.factura_albaran_extraido_id,cd.factura_movimiento_id)>=1"""
                )
                cursor.execute(
                    """select count(*) from cf_2v_detalles_snapshot s
                       join public.conciliacion_detalles cd on cd.id=s.detalle_id
                      where s.tipo_relacion_anterior<>'SIN_COINCIDENCIA'
                        and (cd.tipo_relacion<>s.tipo_relacion_anterior
                             or num_nonnulls(cd.factura_albaran_extraido_id,cd.factura_movimiento_id)<1)"""
                )
                if cursor.fetchone()[0] != 0:
                    raise RuntimeError("HISTORICO_CONCILIACION_NO_REENLAZADO")
                cursor.execute(
                    "update public.documentos_facturas set estado_lectura=%s,estado_persistencia=%s,"
                    "cantidad_documentos_detectados=%s,tipo_contenido=%s,inventario_facturas=%s,numero_paginas=%s,"
                    "bloqueado_por=null,bloqueado_hasta=null where id=%s",
                    (doc_antes[0], doc_antes[1], doc_antes[2], doc_antes[3],
                     Json(doc_antes[4]), doc_antes[5], DOCUMENTO),
                )
            cursor.execute(
                "select normalizacion_ejecucion_id::text,estado_normalizacion,estado_conciliacion_cf,importe_total,"
                "proveedor_id::text,(select count(*) from public.facturas_albaranes_extraidos a where a.factura_id=f.id),"
                "(select count(*) from public.facturas_movimientos m where m.factura_id=f.id),"
                "datos_extraidos #>> '{provenance,alcance_persistencia}' "
                "from public.facturas f where id=%s",
                (factura_id,),
            )
            objetivo_despues = cursor.fetchone()
            if objetivo_despues[:7] != (
                nueva_ejecucion, "NORMALIZADA", "PENDIENTE_CONCILIAR", Decimal("10111.5500"),
                objetivo_antes[5], 160, 7,
            ):
                raise RuntimeError(f"PERSISTENCIA_OBJETIVO_INCORRECTA:{objetivo_despues}")
            if objetivo_despues[7] != "SOLO_FACTURA_08009277":
                raise RuntimeError("PROVENANCE_2V_NO_PERSISTIDA")
            cursor.execute(
                "select f.numero_factura,f.normalizacion_ejecucion_id::text,f.estado_normalizacion,"
                "f.estado_conciliacion_cf,f.importe_total,f.datos_extraidos,"
                "(select count(*) from public.facturas_albaranes_extraidos a where a.factura_id=f.id),"
                "(select count(*) from public.facturas_movimientos m where m.factura_id=f.id),"
                "(select row_to_json(c) from public.conciliaciones c where c.factura_id=f.id and c.es_actual) "
                "from public.facturas f where f.documento_id=%s and f.numero_factura=any(%s) order by f.numero_factura",
                (DOCUMENTO, list(HERMANAS)),
            )
            if cursor.fetchall() != hermanas_antes:
                raise RuntimeError("AISLAMIENTO_HERMANAS_VIOLADO")
            cursor.execute("select count(*) from public.facturas")
            if cursor.fetchone()[0] != 5:
                raise RuntimeError("SE_CREO_FACTURA_ECONOMICA_NUEVA")
            cursor.execute("select count(*) from public.conciliaciones")
            if cursor.fetchone()[0] != conciliaciones_antes:
                raise RuntimeError("CONCILIACION_INESPERADA_EN_RENORMALIZACION")
            cursor.execute("select count(*) from public.normalizacion_ejecuciones")
            esperado = ejecuciones_antes if existente else ejecuciones_antes + 1
            if cursor.fetchone()[0] != esperado:
                raise RuntimeError("HISTORICO_EJECUCIONES_INESPERADO")
            cursor.execute("select count(*) from public.normalizacion_ejecuciones where id=%s", (ejecucion_anterior,))
            if cursor.fetchone()[0] != 1:
                raise RuntimeError("EJECUCION_ANTERIOR_NO_PRESERVADA")
        conexion.commit()
        print(json.dumps({
            "factura": OBJETIVO,
            "factura_id": factura_id,
            "ejecucion_anterior": ejecucion_anterior,
            "ejecucion_nueva": nueva_ejecucion,
            "albaranes": 160,
            "movimientos": 7,
            "facturas_totales": 5,
            "hermanas_intactas": list(HERMANAS),
            "inventario_multifactura_preservado": True,
            "resultado_hash": resultado_hash,
        }, ensure_ascii=False))
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
