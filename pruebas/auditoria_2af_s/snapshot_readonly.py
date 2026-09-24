"""Snapshot productivo READ ONLY para la prueba unica de albaranes."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def cargar_env() -> None:
    for linea in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if not linea or linea.lstrip().startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def main() -> None:
    cargar_env()
    import psycopg2

    conexion = psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"],
        sslmode="require",
        connect_timeout=10,
        application_name="cf_2af_s_readonly",
    )
    conexion.set_session(readonly=True, autocommit=False)
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                select count(*), max(id_contador), max(fecha_importacion)
                  from public.albaranes where farmacia='PIO'
            """)
            albaranes = cursor.fetchone()
            cursor.execute("""
                select id_contador, fecha, fecha_importacion
                  from public.albaranes where farmacia='PIO'
                 order by id_contador desc limit 1
            """)
            ultimo_albaran = cursor.fetchone()
            cursor.execute("""
                select count(*),
                       count(*) filter(where estado_conciliacion_cf='CONCILIADA'),
                       count(*) filter(where estado_conciliacion_cf='PENDIENTE_CONCILIAR')
                  from public.facturas
            """)
            facturas = cursor.fetchone()
            cursor.execute("""
                select f.id::text, f.documento_id::text, f.numero_factura,
                       f.estado_normalizacion, f.estado_conciliacion_cf,
                       f.estado_revision, f.normalizacion_ejecucion_id::text,
                       coalesce((select c.id::text from public.conciliaciones c
                                 where c.factura_id=f.id and c.es_actual), ''),
                       md5(to_jsonb(f)::text)
                  from public.facturas f order by f.id
            """)
            huellas_facturas = cursor.fetchall()
            cursor.execute("""
                select (select count(*) from public.normalizacion_ejecuciones),
                       (select count(*) from public.conciliaciones),
                       (select count(*) from public.documentos_facturas)
            """)
            tablas = cursor.fetchone()
            cursor.execute("""
                select
                  (select count(*) from public.documentos_facturas
                    where bloqueado_por is not null or bloqueado_hasta is not null),
                  (select count(*) from public.facturas
                    where conciliacion_bloqueado_por is not null
                       or conciliacion_bloqueado_hasta is not null)
            """)
            locks = cursor.fetchone()
            cursor.execute("""
                select count(*) from pg_stat_activity
                 where pid<>pg_backend_pid()
                   and (application_name ilike '%%worker%%'
                        or application_name ilike '%%runtime%%')
            """)
            workers = cursor.fetchone()[0]
            cursor.execute("""
                select normalizacion_automatica, conciliacion_automatica,
                       luna_habilitada, farmacias_habilitadas
                  from public.cf_configuracion where id=true
            """)
            flags = cursor.fetchone()
        print(json.dumps({
            "albaranes": albaranes,
            "ultimo_albaran": ultimo_albaran,
            "facturas": facturas,
            "huellas_facturas": huellas_facturas,
            "normalizaciones_conciliaciones_documentos": tablas,
            "locks": locks,
            "workers": workers,
            "flags": flags,
        }, ensure_ascii=False, default=str, sort_keys=True))
    finally:
        conexion.rollback()
        conexion.close()


if __name__ == "__main__":
    main()
