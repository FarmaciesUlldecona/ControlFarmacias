"""Consulta READ ONLY de frescura productiva para el hito 2AD."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))


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
        application_name="cf_2ad_readonly",
    )
    conexion.set_session(readonly=True, autocommit=False)
    try:
        with conexion.cursor() as cursor:
            cursor.execute("""
                select column_name from information_schema.columns
                 where table_schema='public' and table_name='albaranes'
                 order by ordinal_position
            """)
            columnas = [fila[0] for fila in cursor.fetchall()]
            cursor.execute("""
                select id::text, archivo_hash, archivo_nombre,
                       fecha_importacion, farmacia
                  from public.documentos_facturas
                 order by fecha_importacion desc, id desc limit 1
            """)
            ultimo_documento = cursor.fetchone()
            campo_temporal = next(
                (campo for campo in (
                    "fecha_importacion", "created_at", "fecha_creacion", "updated_at"
                )
                 if campo in columnas),
                None,
            )
            if campo_temporal:
                cursor.execute(f"""
                    select id_contador, fecha, {campo_temporal}, farmacia
                      from public.albaranes
                     order by id_contador desc limit 1
                """)
            else:
                cursor.execute("""
                    select id_contador, fecha, null, farmacia
                      from public.albaranes
                     order by id_contador desc limit 1
                """)
            ultimo_albaran = cursor.fetchone()
            cursor.execute("""
                select table_name from information_schema.tables
                 where table_schema='public'
                   and (table_name ilike '%sincron%'
                        or table_name ilike '%ejecucion%')
                 order by table_name
            """)
            tablas_ejecucion = [fila[0] for fila in cursor.fetchall()]
        print(json.dumps({
            "columnas_albaranes": columnas,
            "campo_temporal_albaran": campo_temporal,
            "ultimo_documento": ultimo_documento,
            "ultimo_albaran": ultimo_albaran,
            "tablas_ejecucion": tablas_ejecucion,
        }, default=str, ensure_ascii=False, sort_keys=True))
    finally:
        conexion.rollback()
        conexion.close()


if __name__ == "__main__":
    main()
