"""Snapshot productivo Hito 2AN, estrictamente READ ONLY y sin secretos."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))

from dotenv import dotenv_values
import psycopg2


FUNCTIONS = (
    "cf_reclamar_documento_normalizacion_nucleo",
    "cf_reclamar_documento_normalizacion",
    "cf_reclamar_documento_normalizacion_manual_one_shot",
    "cf_persistir_documento_multifactura",
)


def snapshot() -> dict:
    dsn = os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"]
    app = urlparse(dotenv_values(ROOT / ".env").get("SUPABASE_URL", ""))
    db = urlparse(dsn)
    ref = (app.hostname or "").split(".")[0]
    assert ref and (
        db.hostname == f"db.{ref}.supabase.co"
        or (
            (db.hostname or "").endswith(".pooler.supabase.com")
            and unquote(db.username or "").endswith("." + ref)
        )
    ), "DESTINO_PRODUCTIVO_NO_DEMOSTRADO"

    conn = psycopg2.connect(
        dsn,
        sslmode="require",
        connect_timeout=10,
        application_name="cf_2an_readonly",
    )
    conn.set_session(readonly=True, autocommit=False)
    out: dict = {
        "project_ref": ref,
        "project_ref_sha256": hashlib.sha256(ref.encode()).hexdigest(),
        "destino": "SUPABASE_PRODUCTIVO_CONTROLFARMACIAS_PIO",
    }
    try:
        with conn.cursor() as cur:
            cur.execute("set local statement_timeout='30s'")

            def rows(sql: str):
                cur.execute(sql)
                return cur.fetchall()

            out["conexion"] = rows(
                "select current_database(),current_user,current_schema(),"
                "current_setting('transaction_read_only'),version()"
            )
            out["flags"] = rows(
                "select normalizacion_automatica,conciliacion_automatica,"
                "luna_habilitada,farmacias_habilitadas "
                "from public.cf_configuracion where id=true"
            )
            out["conteos"] = {
                "documentos_pio": rows(
                    "select count(*) from public.documentos_facturas where farmacia='PIO'"
                )[0][0],
                "facturas": rows("select count(*) from public.facturas")[0][0],
                "normalizaciones": rows(
                    "select count(*) from public.normalizacion_ejecuciones"
                )[0][0],
                "conciliaciones": rows("select count(*) from public.conciliaciones")[0][0],
            }
            out["locks"] = rows(
                "select "
                "(select count(*) from public.documentos_facturas where bloqueado_hasta>now()),"
                "(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now())"
            )
            out["workers"] = rows(
                "select application_name,state,count(*) from pg_stat_activity "
                "where pid<>pg_backend_pid() and "
                "(application_name ilike '%worker%' or application_name ilike '%runtime%') "
                "group by 1,2 order by 1,2"
            )
            out["funciones"] = rows(
                "select p.proname,pg_get_function_identity_arguments(p.oid),"
                "pg_get_function_result(p.oid),pg_get_userbyid(p.proowner),"
                "p.prosecdef,p.provolatile,p.proconfig,p.proacl::text,"
                "has_function_privilege('anon',p.oid,'EXECUTE'),"
                "has_function_privilege('authenticated',p.oid,'EXECUTE'),"
                "has_function_privilege('service_role',p.oid,'EXECUTE'),"
                "pg_get_functiondef(p.oid) from pg_proc p "
                "where p.pronamespace='public'::regnamespace and p.proname=any(%s) "
                "order by 1,2",
            ) if False else None
            cur.execute(
                "select p.proname,pg_get_function_identity_arguments(p.oid),"
                "pg_get_function_result(p.oid),pg_get_userbyid(p.proowner),"
                "p.prosecdef,p.provolatile,p.proconfig,p.proacl::text,"
                "has_function_privilege('anon',p.oid,'EXECUTE'),"
                "has_function_privilege('authenticated',p.oid,'EXECUTE'),"
                "has_function_privilege('service_role',p.oid,'EXECUTE'),"
                "pg_get_functiondef(p.oid) from pg_proc p "
                "where p.pronamespace='public'::regnamespace and p.proname=any(%s) "
                "order by 1,2",
                (list(FUNCTIONS),),
            )
            out["funciones"] = cur.fetchall()
            out["constraint_disparador"] = rows(
                "select conname,pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid='public.normalizacion_ejecuciones'::regclass "
                "and conname='normalizacion_ejecuciones_disparador_check'"
            )
            out["marcadores_07_15"] = rows(
                "select "
                "to_regprocedure('public.cf_preflight_pio_valido()') is not null,"
                "to_regclass('public.proveedores') is not null,"
                "to_regclass('public.facturas') is not null,"
                "to_regprocedure('public.cf_reclamar_documento_normalizacion(text,integer)') is not null,"
                "to_regclass('public.facturas_movimientos') is not null,"
                "to_regclass('public.conciliaciones') is not null,"
                "to_regprocedure('public.cf_reclamar_factura_conciliacion(text,integer)') is not null,"
                "to_regprocedure('public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[])') is not null,"
                "exists(select 1 from information_schema.columns where table_schema='public' "
                "and table_name='documentos_facturas' and column_name='inventario_facturas')"
            )
            tables = (
                "documentos_facturas",
                "facturas",
                "normalizacion_ejecuciones",
                "conciliaciones",
                "cf_configuracion",
            )
            out["huellas"] = {}
            for table in tables:
                out["huellas"][table] = rows(
                    f"select count(*),md5(coalesce(string_agg(to_jsonb(t)::text,E'\\n' order by id),'')) "
                    f"from public.{table} t"
                )
        return json.loads(json.dumps(out, default=str))
    finally:
        conn.rollback()
        conn.close()


def validate_pre(out: dict) -> None:
    assert out["conexion"][0][3] == "on"
    assert out["flags"] == [[False, False, False, ["PIO"]]]
    assert out["conteos"] == {
        "documentos_pio": 140,
        "facturas": 7,
        "normalizaciones": 7,
        "conciliaciones": 12,
    }
    assert out["locks"] == [[0, 0]] and out["workers"] == []
    assert out["marcadores_07_15"] == [[True] * 9]
    signatures = {(r[0], r[1]) for r in out["funciones"]}
    assert ("cf_reclamar_documento_normalizacion", "p_worker_id text, p_bloqueo_segundos integer") in signatures
    assert ("cf_persistir_documento_multifactura", "p_documento_id uuid, p_worker_id text, p_idempotency_key text, p_resultado_hash text, p_resultado jsonb, p_segmentos_autorizados text[]") in signatures
    assert not any(r[0] in {"cf_reclamar_documento_normalizacion_nucleo", "cf_reclamar_documento_normalizacion_manual_one_shot"} for r in out["funciones"])
    assert out["constraint_disparador"] and "MANUAL_ONE_SHOT" not in out["constraint_disparador"][0][1]


if __name__ == "__main__":
    value = snapshot()
    validate_pre(value)
    print(json.dumps(value, ensure_ascii=True))
