"""Auditoria 2AC y unica invocacion del coordinador oficial.

Los modos ``preflight`` y ``postcheck`` abren una transaccion READ ONLY.
``execute`` construye el worker con la configuracion leida en READ ONLY y
realiza literalmente una unica llamada a ``ejecutar_una``. Los centinelas
impiden cualquier extraccion si los flags productivos no son los certificados.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def cargar_env() -> None:
    for linea in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if not linea or linea.lstrip().startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


cargar_env()

HEFAME_NUMERO = "0563834757"
HEFAME_FACTURA_ID = "42aa360d-d02a-4715-b477-518ad9ce7742"


def conectar():
    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    sys.modules.pop("psycopg2", None)
    import psycopg2

    if not hasattr(psycopg2, "connect"):
        raise RuntimeError(f"DRIVER_INCOMPLETO:{getattr(psycopg2, '__file__', None)}:{ROOT}")

    conexion = psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"],
        sslmode="require",
        connect_timeout=10,
        application_name="cf_2ac_readonly",
    )
    conexion.set_session(readonly=True, autocommit=False)
    return conexion


def fila(cursor, sql: str, params=()):
    cursor.execute(sql, params)
    return cursor.fetchone()


def filas(cursor, sql: str, params=()):
    cursor.execute(sql, params)
    return cursor.fetchall()


def snapshot() -> dict:
    conexion = conectar()
    try:
        with conexion.cursor() as cursor:
            flags = fila(cursor, """
                select normalizacion_automatica, conciliacion_automatica,
                       luna_habilitada, farmacias_habilitadas,
                       tolerancia_conciliacion
                  from public.cf_configuracion where id=true
            """)
            counts = fila(cursor, """
                select count(*),
                       count(*) filter(where estado_conciliacion_cf='CONCILIADA'),
                       count(*) filter(where estado_conciliacion_cf='PENDIENTE_CONCILIAR')
                  from public.facturas
            """)
            pending = filas(cursor, """
                select id::text, documento_id::text, numero_factura,
                       importe_total::text, normalizacion_ejecucion_id::text,
                       estado_conciliacion_cf
                  from public.facturas
                 where estado_conciliacion_cf='PENDIENTE_CONCILIAR'
                 order by id
            """)
            locks = fila(cursor, """
                select
                  (select count(*) from public.documentos_facturas
                    where bloqueado_por is not null or bloqueado_hasta is not null),
                  (select count(*) from public.facturas
                    where conciliacion_bloqueado_por is not null
                       or conciliacion_bloqueado_hasta is not null)
            """)
            workers = fila(cursor, """
                select count(*) from pg_stat_activity
                 where pid<>pg_backend_pid()
                   and (application_name ilike '%%worker%%'
                        or application_name ilike '%%runtime%%')
            """)[0]
            functions = filas(cursor, """
                select proname, pg_get_function_identity_arguments(oid)
                  from pg_proc
                 where pronamespace='public'::regnamespace
                   and proname in (
                     'cf_evaluar_elegibilidad_conciliacion',
                     'cf_reclamar_factura_conciliacion',
                     'cf_persistir_documento_multifactura')
                 order by proname
            """)
            claim_v2 = fila(cursor, """
                select position(
                  'cross join lateral public.cf_evaluar_elegibilidad_conciliacion'
                  in lower(pg_get_functiondef(p.oid))) > 0
                  from pg_proc p
                 where p.pronamespace='public'::regnamespace
                   and p.proname='cf_reclamar_factura_conciliacion'
            """)[0]
            official_next = filas(cursor, """
                select d.id::text, d.archivo_hash, d.farmacia, d.estado_lectura,
                       d.reprocesar_solicitado_at, d.fecha_importacion,
                       (select count(*) from public.facturas f
                         where f.documento_id=d.id) as facturas_existentes
                  from public.documentos_facturas d
                  cross join public.cf_configuracion c
                 where c.id=true
                   and d.farmacia=any(c.farmacias_habilitadas)
                   and (c.normalizacion_automatica
                        or d.reprocesar_solicitado_at is not null)
                   and d.estado_lectura in ('PENDIENTE','ERROR')
                   and coalesce(d.proximo_reintento_at, '-infinity'::timestamptz)<=now()
                   and coalesce(d.bloqueado_hasta, '-infinity'::timestamptz)<=now()
                 order by (d.reprocesar_solicitado_at is not null) desc,
                          d.fecha_importacion, d.id
                 limit 1
            """)
            latent_pending = filas(cursor, """
                select d.id::text, d.archivo_hash, d.farmacia, d.estado_lectura,
                       d.reprocesar_solicitado_at, d.fecha_importacion,
                       (select count(*) from public.facturas f
                         where f.documento_id=d.id) as facturas_existentes
                  from public.documentos_facturas d
                 where d.farmacia='PIO'
                   and d.estado_lectura in ('PENDIENTE','ERROR')
                 order by d.fecha_importacion, d.id
                 limit 5
            """)
            fingerprints = filas(cursor, """
                select id::text, documento_id::text, numero_factura,
                       importe_total::text, estado_normalizacion,
                       estado_conciliacion_cf, normalizacion_ejecucion_id::text,
                       coalesce((select c.id::text from public.conciliaciones c
                                 where c.factura_id=f.id and c.es_actual), '')
                  from public.facturas f order by id
            """)
            totals = fila(cursor, """
                select
                  (select count(*) from public.documentos_facturas),
                  (select count(*) from public.normalizacion_ejecuciones),
                  (select count(*) from public.conciliaciones)
            """)
            rita = fila(cursor, """
                select (select count(*) from public.documentos_facturas where farmacia='RITA'),
                       (select count(*) from public.facturas where farmacia='RITA')
            """)
        result = {
            "flags": [flags[0], flags[1], flags[2], flags[3], str(flags[4])],
            "facturas": list(counts),
            "pendientes": pending,
            "locks": list(locks),
            "workers": workers,
            "funciones": functions,
            "claim_v2": claim_v2,
            "siguiente_oficial": official_next,
            "pendientes_latentes": latent_pending,
            "huellas_facturas": fingerprints,
            "totales": list(totals),
            "rita": list(rita),
        }
        assert result["flags"] == [False, False, False, ["PIO"], "0.0500"]
        assert result["facturas"] == [7, 6, 1]
        assert len(pending) == 1
        assert pending[0][0] == HEFAME_FACTURA_ID and pending[0][2] == HEFAME_NUMERO
        assert result["locks"] == [0, 0] and workers == 0
        assert result["rita"] == [0, 0]
        assert {item[0] for item in functions} == {
            "cf_evaluar_elegibilidad_conciliacion",
            "cf_reclamar_factura_conciliacion",
            "cf_persistir_documento_multifactura",
        }
        assert claim_v2 is True
        return result
    finally:
        conexion.rollback()
        conexion.close()


class CentinelaExtraccion:
    def extraer(self, *_args, **_kwargs):
        raise RuntimeError("EXTRACCION_NO_AUTORIZADA_CON_FLAGS_FALSE")


def ejecutar_exactamente_una_vez() -> dict:
    from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
    from src.facturas.runtime_supabase.worker_automatico import (
        MAX_DOCUMENTOS_POR_EJECUCION,
        construir_worker_automatico,
    )
    from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion
    from src.facturas.runtime_supabase.worker_normalizacion import WorkerNormalizacion
    from src.supabase_client.conexion_supabase import obtener_cliente_supabase

    repositorio = RepositorioRuntimeSupabase(obtener_cliente_supabase())
    configuracion = repositorio.obtener_configuracion()
    assert configuracion.normalizacion_automatica is False
    assert configuracion.conciliacion_automatica is False
    assert configuracion.luna_habilitada is False
    assert configuracion.farmacias_habilitadas == ("PIO",)
    normalizacion = WorkerNormalizacion(
        repositorio=repositorio,
        materializar_pdf=lambda _documento: (_ for _ in ()).throw(
            RuntimeError("MATERIALIZACION_NO_AUTORIZADA_CON_FLAGS_FALSE")
        ),
        orquestador=CentinelaExtraccion(),
        campos_requeridos=frozenset(),
        worker_id="manual-hito-2ac-unica-iteracion",
    )
    conciliacion = construir_worker_conciliacion(
        repositorio,
        "manual-hito-2ac-unica-iteracion",
        tolerancia=configuracion.tolerancia_conciliacion,
    )
    worker = construir_worker_automatico(normalizacion, conciliacion, configuracion)
    assert MAX_DOCUMENTOS_POR_EJECUCION == 1
    resultado = worker.ejecutar_una()  # UNICA llamada productiva autorizada del hito 2AC.
    return {
        "llamadas_worker": 1,
        "max_documentos": MAX_DOCUMENTOS_POR_EJECUCION,
        "documentos_reclamados": resultado.documentos_reclamados,
        "facturas_conciliacion_reclamadas": resultado.facturas_conciliacion_reclamadas,
        "automatismos_habilitados": resultado.automatismos_habilitados,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("modo", choices=("preflight", "execute", "postcheck"))
    args = parser.parse_args()
    result = ejecutar_exactamente_una_vez() if args.modo == "execute" else snapshot()
    print(json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
