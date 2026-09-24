"""Despliegue 2H con barreras estrictas; no muestra ni persiste credenciales."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
import psycopg2  # noqa: E402

from src.facturas.runtime_supabase.manifiesto_pio import (  # noqa: E402
    manifiesto_sqlite_pio,
    manifiesto_supabase_pio,
    reconciliado,
)

DB_URL = os.environ.get("CONTROLFARMACIAS_SUPABASE_DB_URL", "")
MIG = ROOT / "sql" / "migrations"
PRE = ROOT / "sql" / "preflight"
LEGACY = {"PENDIENTE", "PROCESANDO", "EXTRAIDA", "REVISION", "ERROR"}
FINAL = LEGACY | {"NORMALIZANDO", "NORMALIZADA"}
TABLES_V1 = {
    "proveedores", "proveedores_alias", "cf_configuracion",
    "normalizacion_ejecuciones", "facturas_movimientos",
    "facturas_incidencias", "historial_facturas", "conciliaciones",
    "conciliacion_detalles",
}
RLS_TABLES = TABLES_V1 | {
    "documentos_facturas", "facturas", "facturas_vencimientos",
    "facturas_impuestos", "facturas_albaranes_extraidos", "facturas_ajustes",
}


def connect(readonly: bool = False):
    conn = psycopg2.connect(DB_URL, connect_timeout=10, sslmode="require")
    conn.set_session(readonly=readonly, autocommit=True)
    return conn


def scalar(sql: str, params=()):
    conn = connect(readonly=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]
    finally:
        conn.close()


def rows(sql: str, params=()):
    conn = connect(readonly=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def execute_select_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    clean = re.sub(r"--.*?$", "", text, flags=re.MULTILINE)
    statements = [part.strip() for part in clean.split(";") if part.strip()]
    assert statements and all(part.casefold().startswith("select") for part in statements)
    conn = connect(readonly=True)
    try:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
                names = [column.name for column in cur.description]
                result = cur.fetchall()
                if "existe" in names:
                    position = names.index("existe")
                    assert result and all(row[position] is True for row in result)
                if "rls_enabled" in names:
                    position = names.index("rls_enabled")
                    assert result and all(row[position] is True for row in result)
                if "bucket_privado" in names:
                    position = names.index("bucket_privado")
                    assert result and all(row[position] is True for row in result)
                for safe in (
                    "normalizacion_automatica_segura", "conciliacion_automatica_segura",
                    "luna_habilitada_segura", "solo_pio_habilitada",
                ):
                    if safe in names:
                        position = names.index(safe)
                        assert result and all(row[position] is True for row in result)
                if "estado_lectura_v1_ok" in names and path.name.startswith("postflight"):
                    position = names.index("estado_lectura_v1_ok")
                    assert result and all(row[position] is True for row in result)
    finally:
        conn.close()


def migrate(filename: str) -> None:
    sql = (MIG / filename).read_text(encoding="utf-8")
    assert sql.strip().casefold().startswith("begin;")
    assert sql.strip().casefold().endswith("commit;")
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("set lock_timeout = '5s'")
            cur.execute("set statement_timeout = '60s'")
            cur.execute(sql)
    finally:
        conn.close()


def fingerprint(sql: str, params=()) -> str:
    content = "\n".join(row[0] for row in rows(sql, params))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def legacy_documents_fingerprint() -> str:
    return fingerprint("""
        select row_to_json(x)::text from (
            select id,farmacia,archivo_nombre,archivo_ruta,archivo_hash,
                   estado_lectura,requiere_revision,datos_extraidos,
                   fecha_importacion,fecha_actualizacion
            from public.documentos_facturas order by id
        ) x
    """)


def full_fingerprint(table: str, farmacia: str | None = None) -> str:
    assert table in RLS_TABLES | {"albaranes"}
    clause = " where farmacia=%s" if farmacia else ""
    params = (farmacia,) if farmacia else ()
    return fingerprint(
        f"select row_to_json(t)::text from public.{table} t{clause} order by id",
        params,
    )


def check_states() -> tuple[str, set[str]]:
    result = rows("""
        select c.conname, pg_get_expr(c.conbin,c.conrelid)
        from pg_constraint c
        join pg_attribute a on a.attrelid=c.conrelid and a.attnum=any(c.conkey)
        where c.conrelid='public.documentos_facturas'::regclass
          and c.contype='c' and a.attname='estado_lectura'
    """)
    assert len(result) == 1
    name, expression = result[0]
    return name, set(re.findall(r"'([A-Z_]+)'", expression))


def unique_albaranes_ok() -> bool:
    return bool(scalar("""
        select exists (
            select 1 from pg_index i
            where i.indrelid='public.albaranes'::regclass
              and i.indisunique and i.indisvalid and i.indisready
              and i.indpred is null and i.indexprs is null and i.indnkeyatts=2
              and (select array_agg(a.attname order by k.ordinality)
                   from unnest(i.indkey) with ordinality k(attnum,ordinality)
                   join pg_attribute a on a.attrelid=i.indrelid and a.attnum=k.attnum
                   where k.ordinality<=i.indnkeyatts)
                  = array['farmacia','id_contador']::name[]
        )
    """))


def duplicate_albaranes() -> int:
    return scalar("""
        select count(*) from (
            select farmacia,id_contador from public.albaranes
            group by farmacia,id_contador having count(*)>1
        ) d
    """)


def config() -> tuple:
    return rows("""
        select normalizacion_automatica,conciliacion_automatica,luna_habilitada,
               farmacias_habilitadas
        from public.cf_configuracion where id=true
    """)[0]


def canonical_pair():
    uri = (ROOT / "data" / "indice_facturas.sqlite").resolve().as_uri()
    db = sqlite3.connect(uri + "?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    try:
        records = [dict(row) for row in db.execute(
            "select ruta_relativa,archivo_hash,estado from archivos_facturas"
        )]
    finally:
        db.close()
    local = manifiesto_sqlite_pio(records)
    remote_values = [row[0] for row in rows(
        "select archivo_hash from public.documentos_facturas where farmacia=%s",
        ("PIO",),
    )]
    remote = manifiesto_supabase_pio(remote_values)
    assert reconciliado(local, remote)
    return local, remote


def flags_ok() -> None:
    assert config() == (False, False, False, ["PIO"])


def all_empty(names: set[str]) -> None:
    for name in names:
        assert scalar(f"select count(*) from public.{name}") == 0


def validate_postflight_schema() -> None:
    assert all(scalar("select to_regclass(%s) is not null", (f"public.{x}",)) for x in TABLES_V1)
    assert all(scalar("select to_regclass(%s) is not null", (f"public.{x}",)) for x in (
        "v_facturas_listado", "v_dashboard_diario", "v_vencimientos_calendario", "v_proveedores_estado"
    ))
    expected_rpc = {
        "cf_preflight_pio_valido", "cf_reclamar_documento_normalizacion",
        "cf_reclamar_factura_conciliacion", "cf_persistir_normalizacion",
        "cf_registrar_fallo_normalizacion", "cf_validar_factura",
        "cf_desvalidar_factura", "cf_solicitar_reprocesado",
        "cf_solicitar_reintento_conciliacion", "cf_reintentar_todas_pendientes",
    }
    actual_rpc = {row[0] for row in rows("""
        select distinct p.proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace
        where n.nspname='public' and p.proname=any(%s)
    """, (list(expected_rpc),))}
    assert actual_rpc == expected_rpc
    rls = dict(rows("""
        select c.relname,c.relrowsecurity from pg_class c
        join pg_namespace n on n.oid=c.relnamespace
        where n.nspname='public' and c.relname=any(%s)
    """, (list(RLS_TABLES),)))
    assert set(rls) == RLS_TABLES and all(rls.values())
    policies = rows("""
        select tablename,cmd,roles from pg_policies
        where schemaname='public' and tablename=any(%s)
    """, (list(RLS_TABLES),))
    assert len(policies) == 15
    assert all(cmd == "SELECT" and roles == ["authenticated"] for _, cmd, roles in policies)
    auth_grants = rows("""
        select table_name,privilege_type from information_schema.role_table_grants
        where table_schema='public' and grantee='authenticated' and table_name=any(%s)
    """, (list(RLS_TABLES),))
    assert {(t, p) for t, p in auth_grants} == {(t, "SELECT") for t in RLS_TABLES}
    assert scalar("select public=false from storage.buckets where id='facturas-pdf'") is True
    _, values = check_states()
    assert values == FINAL
    assert unique_albaranes_ok() and duplicate_albaranes() == 0


def attest(local, remote) -> None:
    assert local.total == remote.total and local.sha256 == remote.sha256
    conn = connect()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("""
                update public.cf_configuracion
                   set preflight_indice_pio_reconciliado=true,
                       preflight_pio_hashes_sqlite=%s,
                       preflight_pio_hashes_supabase=%s,
                       preflight_pio_manifest_sqlite_sha256=%s,
                       preflight_pio_manifest_supabase_sha256=%s
                 where id=true
            """, (local.total, remote.total, local.sha256, remote.sha256))
            assert cur.rowcount == 1
            cur.execute("select public.cf_preflight_pio_valido()")
            assert cur.fetchone()[0] is True
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    assert DB_URL
    app = urlparse(dotenv_values(ROOT / ".env").get("SUPABASE_URL", ""))
    db = urlparse(DB_URL)
    reference = (app.hostname or "").split(".")[0]
    direct = db.hostname == f"db.{reference}.supabase.co"
    pooler = (db.hostname or "").endswith(".pooler.supabase.com") and unquote(db.username or "").endswith(f".{reference}")
    assert reference and (direct or pooler)
    assert scalar("select 1") == 1
    assert rows("""
        select n.nspname from pg_extension e
        join pg_namespace n on n.oid=e.extnamespace
        where e.extname='pgcrypto'
    """) == [("extensions",)]
    assert scalar("select to_regprocedure('extensions.digest(text,text)') is not null") is True
    print("CONEXION_POSTGRESQL_OK", flush=True)
    print("DESTINO=SUPABASE_PRODUCTIVO_CONTROLFARMACIAS_PIO", flush=True)

    execute_select_file(PRE / "preflight_supabase_controlfarmacias.sql")
    assert all(scalar("select to_regclass(%s) is not null", (f"public.{x}",)) for x in {
        "documentos_facturas", "facturas", "facturas_vencimientos", "facturas_impuestos",
        "facturas_albaranes_extraidos", "facturas_ajustes", "albaranes"
    })
    assert all(scalar("select to_regclass(%s) is null", (f"public.{x}",)) for x in TABLES_V1)
    assert check_states()[1] == LEGACY
    assert unique_albaranes_ok() and duplicate_albaranes() == 0
    assert scalar("select count(*) from public.facturas") == 0
    all_empty({"facturas_vencimientos", "facturas_impuestos", "facturas_albaranes_extraidos", "facturas_ajustes"})
    assert scalar("select count(*) from public.documentos_facturas where farmacia='PIO' and (archivo_hash is null or archivo_hash !~ '^[0-9a-fA-F]{64}$')") == 0
    assert scalar("select public=false from storage.buckets where id='facturas-pdf'") is True
    initial_counts = (
        scalar("select count(*) from public.documentos_facturas where farmacia='PIO'"),
        scalar("select count(*) from public.albaranes"),
    )
    assert initial_counts == (116, 2873)
    initial_legacy = legacy_documents_fingerprint()
    local, remote = canonical_pair()
    print(f"PREFLIGHT_OK DOCUMENTOS_PIO={initial_counts[0]} ALBARANES={initial_counts[1]}", flush=True)
    print(f"RECONCILIACION_PREVIA_OK HASHES={local.total} MANIFIESTO={local.sha256}", flush=True)

    migrate("07_cf_proveedores_config.sql")
    assert all(scalar("select to_regclass(%s) is not null", (f"public.{x}",)) for x in {"proveedores", "proveedores_alias", "cf_configuracion"})
    flags_ok()
    assert scalar("select public.cf_preflight_pio_valido()") is False
    print("MIGRACION_07_OK", flush=True)

    migrate("08_cf_core_facturas.sql")
    assert scalar("select count(*) from public.facturas") == 0
    assert legacy_documents_fingerprint() == initial_legacy
    assert scalar("select data_type='text' from information_schema.columns where table_schema='public' and table_name='facturas' and column_name='id_proveedor_albaranes'") is True
    before_08b = full_fingerprint("documentos_facturas")
    print("MIGRACION_08_OK", flush=True)

    migrate("08b_cf_estado_lectura_compatibilidad.sql")
    assert check_states()[1] == FINAL
    assert full_fingerprint("documentos_facturas") == before_08b
    print("MIGRACION_08B_OK CHECK_FINAL_EXACTO", flush=True)

    migrate("09_cf_normalizacion_runtime.sql")
    assert scalar("select count(*) from public.normalizacion_ejecuciones") == 0
    print("MIGRACION_09_OK", flush=True)

    migrate("10_cf_movimientos_incidencias_historial.sql")
    all_empty({"facturas_movimientos", "facturas_incidencias", "historial_facturas"})
    print("MIGRACION_10_OK", flush=True)

    migrate("11_cf_conciliacion.sql")
    all_empty({"conciliaciones", "conciliacion_detalles"})
    print("MIGRACION_11_OK", flush=True)

    migrate("12_cf_views_rls_rpc.sql")
    validate_postflight_schema()
    flags_ok()
    all_empty({"normalizacion_ejecuciones", "conciliaciones", "conciliacion_detalles"})
    execute_select_file(PRE / "postflight_supabase_v1.sql")
    docs_after_12 = full_fingerprint("documentos_facturas")
    rita_docs_after_12 = full_fingerprint("documentos_facturas", "RITA")
    rita_facturas_after_12 = full_fingerprint("facturas", "RITA")
    print("MIGRACION_12_Y_POSTFLIGHT_OK", flush=True)

    local2, remote2 = canonical_pair()
    print(f"RECONCILIACION_POST12_OK HASHES={local2.total} MANIFIESTO={local2.sha256}", flush=True)
    assert scalar("select public.cf_preflight_pio_valido()") is False
    flags_ok()
    assert scalar("select count(*) from public.facturas") == 0
    assert scalar("select count(*) from public.normalizacion_ejecuciones") == 0
    attest(local2, remote2)
    assert scalar("select public.cf_preflight_pio_valido()") is True
    print("GUARDS_13_OK_ATESTACION_VIVA", flush=True)

    migrate("13_cf_backfill_compatibilidad.sql")
    assert full_fingerprint("documentos_facturas") == docs_after_12
    assert legacy_documents_fingerprint() == initial_legacy
    assert full_fingerprint("documentos_facturas", "RITA") == rita_docs_after_12
    assert full_fingerprint("facturas", "RITA") == rita_facturas_after_12
    assert scalar("select count(*) from public.facturas") == 0
    all_empty({"normalizacion_ejecuciones", "facturas_movimientos", "facturas_incidencias", "historial_facturas", "conciliaciones", "conciliacion_detalles"})
    validate_postflight_schema()
    flags_ok()
    local3, remote3 = canonical_pair()
    assert local3 == local2 and remote3 == remote2
    print("MIGRACION_13_Y_VALIDACION_FINAL_OK", flush=True)
    print(f"RECONCILIACION_FINAL_OK HASHES={local3.total} MANIFIESTO={local3.sha256}", flush=True)


def verify_rollback() -> None:
    assert scalar("select to_regclass('public.proveedores') is null")
    assert scalar("select to_regclass('public.proveedores_alias') is null")
    assert scalar("select to_regclass('public.cf_configuracion') is null")
    assert scalar("select count(*) from public.documentos_facturas where farmacia='PIO'") == 116
    assert scalar("select count(*) from public.facturas") == 0
    assert scalar("select count(*) from public.albaranes") == 2873
    assert check_states()[1] == LEGACY
    local, remote = canonical_pair()
    assert reconciliado(local, remote)
    print("ROLLBACK_07_VERIFICADO_SIN_ESTADO_PARCIAL", flush=True)


def diagnose_pgcrypto() -> None:
    search_path = scalar("select current_setting('search_path')")
    extension = rows("""
        select e.extname,n.nspname,e.extversion
        from pg_extension e join pg_namespace n on n.oid=e.extnamespace
        where e.extname='pgcrypto'
    """)
    digest = rows("""
        select n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),
               pg_get_function_result(p.oid)
        from pg_proc p join pg_namespace n on n.oid=p.pronamespace
        where p.proname='digest'
        order by n.nspname,3
    """)
    resolution = rows("""
        select to_regprocedure('digest(text,text)')::text,
               to_regprocedure('extensions.digest(text,text)')::text,
               to_regprocedure('digest(bytea,text)')::text,
               to_regprocedure('extensions.digest(bytea,text)')::text
    """)[0]
    print("SEARCH_PATH=" + search_path)
    print("PGCRYPTO=" + json.dumps(extension))
    print("DIGEST=" + json.dumps(digest))
    print("RESOLUCION=" + json.dumps(resolution))


def final_report() -> None:
    execute_select_file(PRE / "postflight_supabase_v1.sql")
    validate_postflight_schema()
    flags_ok()
    local, remote = canonical_pair()
    assert reconciliado(local, remote)
    tables = [
        "documentos_facturas", "facturas", "facturas_vencimientos",
        "facturas_impuestos", "facturas_albaranes_extraidos", "facturas_ajustes",
        "albaranes", "proveedores", "proveedores_alias", "cf_configuracion",
        "normalizacion_ejecuciones", "facturas_movimientos", "facturas_incidencias",
        "historial_facturas", "conciliaciones", "conciliacion_detalles",
    ]
    counts = {name: scalar(f"select count(*) from public.{name}") for name in tables}
    states = rows("""
        select farmacia,estado_lectura,count(*)
        from public.documentos_facturas group by farmacia,estado_lectura
        order by farmacia,estado_lectura
    """)
    attestation = rows("""
        select preflight_indice_pio_reconciliado,preflight_pio_hashes_sqlite,
               preflight_pio_hashes_supabase,preflight_pio_manifest_sqlite_sha256,
               preflight_pio_manifest_supabase_sha256,public.cf_preflight_pio_valido()
        from public.cf_configuracion where id=true
    """)[0]
    from src.facturas.motor_local.autoridad import (
        AUTORIDADES_EXTRACTORES_LOCALES,
        COFARES_LOCAL_AUTHORITY,
    )
    assert len(AUTORIDADES_EXTRACTORES_LOCALES) == 15
    assert all(not item.habilitada for item in AUTORIDADES_EXTRACTORES_LOCALES.values())
    assert COFARES_LOCAL_AUTHORITY is False
    print("CONTEOS_FINALES=" + json.dumps(counts, sort_keys=True))
    print("ESTADOS_DOCUMENTOS=" + json.dumps(states))
    print("ATESTACION=" + json.dumps(attestation))
    print(f"RECONCILIACION_FINAL={local.total}|{remote.total}|{local.sha256}")
    print("AUTORIDADES=15/15_FALSE COFARES_LOCAL_AUTHORITY=FALSE")


if __name__ == "__main__":
    if sys.argv[1:] == ["--verify-rollback"]:
        verify_rollback()
    elif sys.argv[1:] == ["--diagnose-pgcrypto"]:
        diagnose_pgcrypto()
    elif sys.argv[1:] == ["--final-report"]:
        final_report()
    else:
        main()
