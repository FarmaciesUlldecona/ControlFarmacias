"""Hito 2AW: preflight/backup/postcheck productivo ESTRICTAMENTE READ_ONLY (sin secretos).

Uso:
  python pruebas/auditoria_2aw/preflight_readonly.py remoto <salida.json>
  python pruebas/auditoria_2aw/preflight_readonly.py local <contenedor> <db> <salida.json>

``remoto`` abre una sesion ``readonly=True`` tras demostrar el project ref y
vuelca: esquema afectado por la migracion 18 (definiciones LF, checks, columnas,
vistas, grants, default ACL), operacion, conteos y un snapshot por fila con
huellas de facturas, conciliaciones (sin idempotency_key), conciliacion_detalles,
cf_configuracion e historial_facturas. ``local`` calcula el mismo bloque de
esquema con ``docker exec psql`` sobre PostgreSQL 17 local. No llama a ninguna RPC.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
PROJECT_REF = "vklaiuytvegkelgyspxc"

FUNCIONES = (
    "cf_reclamar_factura_conciliacion",
    "cf_reclamar_factura_conciliacion_nucleo",
    "cf_reclamar_factura_conciliacion_manual_one_shot",
    "cf_persistir_conciliacion",
    "cf_registrar_fallo_conciliacion",
    "cf_solicitar_reintento_conciliacion",
    "cf_evaluar_elegibilidad_conciliacion",
    "cf_reintentar_todas_pendientes",
    "cf_resultado_conciliacion",
)
TABLAS = ("facturas", "conciliaciones", "conciliacion_detalles", "cf_configuracion", "historial_facturas")
_F = ",".join(f"'{f}'" for f in FUNCIONES)
_T = ",".join(f"'{t}'" for t in TABLAS)

SQL_ESQUEMA = f"""
select jsonb_build_object(
  'funciones', coalesce((select jsonb_object_agg(p.oid::regprocedure::text,
        replace(pg_get_functiondef(p.oid), chr(13), ''))
      from pg_proc p where p.pronamespace='public'::regnamespace and p.proname in ({_F})), '{{}}'::jsonb),
  'propiedades', coalesce((select jsonb_object_agg(p.oid::regprocedure::text,
        jsonb_build_array(p.prosecdef, pg_get_userbyid(p.proowner)))
      from pg_proc p where p.pronamespace='public'::regnamespace and p.proname in ({_F})), '{{}}'::jsonb),
  'grants', coalesce((select jsonb_object_agg(p.oid::regprocedure::text, jsonb_build_object(
        'public', p.proacl is null or exists(select 1 from aclexplode(p.proacl) a
                                             where a.grantee = 0 and a.privilege_type = 'EXECUTE'),
        'anon', has_function_privilege('anon', p.oid, 'EXECUTE'),
        'authenticated', has_function_privilege('authenticated', p.oid, 'EXECUTE'),
        'service_role', has_function_privilege('service_role', p.oid, 'EXECUTE'),
        'acl', p.proacl::text))
      from pg_proc p where p.pronamespace='public'::regnamespace and p.proname in ({_F})), '{{}}'::jsonb),
  'checks', coalesce((select jsonb_object_agg(c.conrelid::regclass::text||'.'||c.conname, pg_get_constraintdef(c.oid))
      from pg_constraint c where c.contype in ('c','u')
       and c.conrelid in (select ('public.'||t)::regclass from unnest(array[{_T}]) t)), '{{}}'::jsonb),
  'indices', coalesce((select jsonb_object_agg(indexname, indexdef) from pg_indexes
      where schemaname='public' and tablename in ({_T})), '{{}}'::jsonb),
  'columnas', coalesce((select jsonb_object_agg(table_name||'.'||column_name,
        jsonb_build_array(data_type, column_default, is_nullable))
      from information_schema.columns where table_schema='public' and table_name in ({_T})), '{{}}'::jsonb),
  'vistas', coalesce((select jsonb_object_agg(c.relname, md5(pg_get_viewdef(c.oid)))
      from pg_class c where c.relkind='v' and c.relnamespace='public'::regnamespace), '{{}}'::jsonb),
  'default_acl', coalesce((select jsonb_agg(jsonb_build_array(defaclrole::regrole::text,
        coalesce(defaclnamespace::regnamespace::text,'*'), defaclobjtype::text, defaclacl::text)
        order by 1,2,3) from pg_default_acl), '[]'::jsonb)
)::text
"""

MARCAS = (
    "select jsonb_build_object("
    "'17_replay', to_regprocedure('public.cf_cerrar_replay_normalizacion(uuid,text,uuid,text)') is not null,"
    "'17_fallo7', to_regprocedure('public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text)') is not null,"
    "'16_manual', to_regprocedure('public.cf_reclamar_documento_normalizacion_manual_one_shot(text,integer)') is not null,"
    "'15_multifactura', to_regprocedure('public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[])') is not null,"
    "'14_elegibilidad', to_regprocedure('public.cf_evaluar_elegibilidad_conciliacion(uuid)') is not null,"
    "'11_conciliaciones', to_regclass('public.conciliaciones') is not null,"
    "'18_nucleo', to_regprocedure('public.cf_reclamar_factura_conciliacion_nucleo(text,integer,text)') is not null,"
    "'18_manual', to_regprocedure('public.cf_reclamar_factura_conciliacion_manual_one_shot(text,integer)') is not null,"
    "'18_persistir', to_regprocedure('public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)') is not null,"
    "'18_fallo', to_regprocedure('public.cf_registrar_fallo_conciliacion(uuid,text,text,text,text,text)') is not null,"
    "'18_columna', exists(select 1 from information_schema.columns where table_schema='public' "
    "  and table_name='conciliaciones' and column_name='idempotency_key'))::text"
)

# Huellas por fila sobre todas las columnas; en conciliaciones sin idempotency_key
# (columna nueva de la 18) para comparar antes/despues.
HUELLAS = {
    "facturas": "select t.id::text, md5((to_jsonb(t) - 'conciliacion_intentos_fallo' - "
                "'conciliacion_ultima_clase_fallo')::text) from public.facturas t order by t.id",
    "conciliaciones": "select t.id::text, md5((to_jsonb(t) - 'idempotency_key')::text) "
                      "from public.conciliaciones t order by t.id",
    "conciliacion_detalles": "select t.id::text, md5(to_jsonb(t)::text) from public.conciliacion_detalles t order by t.id",
    "cf_configuracion": "select t.id::text, md5((to_jsonb(t) - 'conciliacion_max_intentos' - "
                        "'conciliacion_backoff')::text) from public.cf_configuracion t",
    "historial_facturas": "select t.id::text, md5(to_jsonb(t)::text) from public.historial_facturas t order by t.id",
}


def _operacion(rows) -> dict:
    out = {}
    out["flags"] = list(rows("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,"
                             "farmacias_habilitadas::text from public.cf_configuracion where id")[0])
    out["cf_configuracion"] = rows("select to_jsonb(c)::text from public.cf_configuracion c")[0][0]
    out["locks"] = list(rows(
        "select (select count(*) from public.documentos_facturas where bloqueado_hasta>now() or bloqueado_por is not null),"
        "(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now() "
        " or conciliacion_bloqueado_por is not null)")[0])
    out["normalizando"] = rows("select count(*) from public.documentos_facturas where estado_lectura='NORMALIZANDO'")[0][0]
    out["workers"] = rows(
        "select application_name,state,count(*) from pg_stat_activity where pid<>pg_backend_pid() and "
        "(application_name ilike '%worker%' or application_name ilike '%runtime%') group by 1,2 order by 1,2")
    out["facturas_por_estado_conciliacion"] = rows(
        "select estado_conciliacion_cf, count(*) from public.facturas group by 1 order by 1")
    out["reintentos_solicitados"] = rows(
        "select count(*) from public.facturas where conciliacion_reintento_solicitado_at is not null")[0][0]
    out["conteos"] = {t: rows(f"select count(*) from public.{t}")[0][0] for t in TABLAS}
    out["conciliaciones_disparador"] = rows("select disparador, count(*) from public.conciliaciones group by 1 order by 1")
    out["hefame_0563834757"] = rows(
        "select id::text, estado_conciliacion_cf from public.facturas where numero_factura='0563834757'")
    return out


def remoto(salida: Path) -> None:
    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    from dotenv import dotenv_values
    import psycopg2

    dsn = os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"]
    app = urlparse(dotenv_values(ROOT / ".env").get("SUPABASE_URL", ""))
    db = urlparse(dsn)
    ref = (app.hostname or "").split(".")[0]
    assert ref == PROJECT_REF and (
        db.hostname == f"db.{ref}.supabase.co"
        or ((db.hostname or "").endswith(".pooler.supabase.com")
            and unquote(db.username or "").endswith("." + ref))
    ), "DESTINO_PRODUCTIVO_NO_DEMOSTRADO"
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_2aw_readonly")
    conn.set_session(readonly=True, autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("set local statement_timeout='120s'")

            def rows(sql):
                cur.execute(sql)
                return cur.fetchall()

            out = {"project_ref": ref,
                   "transaction_read_only": rows("select current_setting('transaction_read_only')")[0][0],
                   "capturado_utc": rows("select now()::text")[0][0],
                   "marcas": json.loads(rows(MARCAS)[0][0]),
                   "esquema": json.loads(rows(SQL_ESQUEMA)[0][0])}
            out.update(_operacion(rows))
            out["huellas_por_fila"] = {t: dict(rows(q)) for t, q in HUELLAS.items()}
            out["volcado"] = {t: [r[0] for r in rows(f"select to_jsonb(t)::text from public.{t} t order by 1")]
                              for t in TABLAS}
    finally:
        conn.rollback()
        conn.close()
    salida.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    resumen = {k: out[k] for k in ("project_ref", "transaction_read_only", "capturado_utc", "marcas", "flags",
                                    "locks", "normalizando", "workers", "facturas_por_estado_conciliacion",
                                    "reintentos_solicitados", "conteos", "conciliaciones_disparador",
                                    "hefame_0563834757")}
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    print("sha256", hashlib.sha256(salida.read_bytes()).hexdigest())


def local(contenedor: str, db: str, salida: Path) -> None:
    def psql(sql):
        r = subprocess.run(["docker", "exec", "-i", contenedor, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                            "-U", "postgres", "-d", db], input=sql + ";", text=True, encoding="utf-8",
                           capture_output=True, timeout=120)
        if r.returncode:
            raise RuntimeError(r.stderr)
        return r.stdout.rstrip("\n")

    out = {"marcas": json.loads(psql(MARCAS)), "esquema": json.loads(psql(SQL_ESQUEMA))}
    salida.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1] == "remoto":
        remoto(Path(sys.argv[2]))
    elif sys.argv[1] == "local":
        local(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
    else:
        raise SystemExit("modo desconocido")
