"""Hito 2AS: preflight/postcheck productivo ESTRICTAMENTE READ_ONLY (sin secretos).

Uso:
  python pruebas/auditoria_2as/preflight_readonly.py remoto <salida.json>
  python pruebas/auditoria_2as/preflight_readonly.py local <contenedor> <db> <salida.json>

``remoto`` abre una sesion ``readonly=True`` contra el destino de
CONTROLFARMACIAS_SUPABASE_DB_URL tras demostrar el project ref (como 2AN).
``local`` ejecuta la misma consulta de definiciones con ``docker exec psql`` sobre
una base PostgreSQL 17 local, para comparar hashes. No llama a ninguna RPC.
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

FUNCIONES = (
    "cf_persistir_normalizacion",
    "cf_registrar_fallo_normalizacion",
    "cf_solicitar_reprocesado",
    "cf_persistir_documento_multifactura",
    "cf_reclamar_documento_normalizacion_nucleo",
    "cf_reclamar_documento_normalizacion",
    "cf_reclamar_documento_normalizacion_manual_one_shot",
    "cf_cerrar_replay_normalizacion",
)
SELECTOR = FUNCIONES[4:7]
TABLAS = ("documentos_facturas", "normalizacion_ejecuciones", "cf_configuracion")
_LISTA_F = ",".join(f"'{f}'" for f in FUNCIONES)
_LISTA_T = ",".join(f"'{t}'" for t in TABLAS)

SQL_DEFINICIONES = f"""
select jsonb_build_object(
  'funciones', coalesce((select jsonb_object_agg(p.oid::regprocedure::text, md5(pg_get_functiondef(p.oid)))
      from pg_proc p where p.pronamespace='public'::regnamespace and p.proname in ({_LISTA_F})), '{{}}'::jsonb),
  'privilegios', coalesce((select jsonb_object_agg(p.oid::regprocedure::text||'@'||r,
        has_function_privilege(r, p.oid, 'EXECUTE'))
      from pg_proc p cross join unnest(array['anon','authenticated','service_role']) r
      where p.pronamespace='public'::regnamespace and p.proname in ({_LISTA_F})), '{{}}'::jsonb),
  'checks', coalesce((select jsonb_object_agg(c.conrelid::regclass::text||'.'||c.conname, pg_get_constraintdef(c.oid))
      from pg_constraint c where c.contype='c'
       and c.conrelid in (select ('public.'||t)::regclass from unnest(array[{_LISTA_T}]) t)), '{{}}'::jsonb),
  'columnas', coalesce((select jsonb_object_agg(table_name||'.'||column_name,
        jsonb_build_array(data_type, column_default, is_nullable))
      from information_schema.columns where table_schema='public' and table_name in ({_LISTA_T})), '{{}}'::jsonb),
  'vistas', coalesce((select jsonb_object_agg(c.relname, md5(pg_get_viewdef(c.oid)))
      from pg_class c where c.relkind='v' and c.relnamespace='public'::regnamespace), '{{}}'::jsonb)
)::text
"""

# Matriz de EXECUTE por funcion: PUBLIC (acl nula = default de PostgreSQL = PUBLIC),
# anon, authenticated y service_role.
SQL_MATRIZ_GRANTS = f"""
select coalesce(jsonb_object_agg(p.oid::regprocedure::text, jsonb_build_object(
    'public', p.proacl is null or exists(select 1 from aclexplode(p.proacl) a
                                         where a.grantee = 0 and a.privilege_type = 'EXECUTE'),
    'anon', has_function_privilege('anon', p.oid, 'EXECUTE'),
    'authenticated', has_function_privilege('authenticated', p.oid, 'EXECUTE'),
    'service_role', has_function_privilege('service_role', p.oid, 'EXECUTE'),
    'acl', p.proacl::text)), '{{}}'::jsonb)::text
from pg_proc p where p.pronamespace='public'::regnamespace and p.proname in ({_LISTA_F})
"""

SQL_ELEGIBLES = (
    "select d.id::text from public.documentos_facturas d cross join public.cf_configuracion c "
    "where c.id = true and d.farmacia = any(c.farmacias_habilitadas) "
    "and d.estado_lectura in ('PENDIENTE','ERROR') "
    "and coalesce(d.proximo_reintento_at,'-infinity'::timestamptz) <= now() "
    "and coalesce(d.bloqueado_hasta,'-infinity'::timestamptz) <= now() "
    "order by (d.reprocesar_solicitado_at is not null) desc, d.fecha_importacion, d.id"
)

SQL_SELECTOR_TEXTO = (
    "select string_agg(pg_get_functiondef(p.oid), E'\\n' order by p.oid::regprocedure::text) "
    "from pg_proc p where p.pronamespace='public'::regnamespace and p.proname in ("
    + ",".join(f"'{f}'" for f in SELECTOR) + ")"
)

SQL_DEFINICIONES_COMPLETAS = (
    "select coalesce(jsonb_object_agg(p.oid::regprocedure::text, pg_get_functiondef(p.oid)),'{}'::jsonb)::text "
    f"from pg_proc p where p.pronamespace='public'::regnamespace and p.proname in ({_LISTA_F})"
)


def _operacion(rows):
    out = {}
    out["flags"] = rows(
        "select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas::text "
        "from public.cf_configuracion where id=true")
    out["cf_configuracion"] = rows("select to_jsonb(c)::text from public.cf_configuracion c")
    out["locks"] = rows(
        "select (select count(*) from public.documentos_facturas where bloqueado_hasta>now()),"
        "(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now())")
    out["claims_activos"] = rows(
        "select count(*) from public.documentos_facturas where bloqueado_por is not null")
    out["workers"] = rows(
        "select application_name,state,count(*) from pg_stat_activity where pid<>pg_backend_pid() and "
        "(application_name ilike '%worker%' or application_name ilike '%runtime%') group by 1,2 order by 1,2")
    out["documentos_por_estado"] = rows(
        "select farmacia,estado_lectura,estado_persistencia,count(*) from public.documentos_facturas "
        "group by 1,2,3 order by 1,2,3")
    out["error"] = rows("select count(*) from public.documentos_facturas where estado_lectura='ERROR'")
    out["normalizando"] = rows(
        "select id::text, bloqueado_por, bloqueado_hasta::text, fecha_inicio_lectura::text, "
        "fecha_actualizacion::text, (now()-fecha_actualizacion)::text "
        "from public.documentos_facturas where estado_lectura='NORMALIZANDO' order by fecha_actualizacion")
    out["conteos"] = {
        t: rows(f"select count(*) from public.{t}")[0][0]
        for t in ("documentos_facturas", "facturas", "normalizacion_ejecuciones", "conciliaciones",
                  "historial_facturas", "facturas_incidencias")
    }
    out["huella_estados_documentales"] = rows(
        "select md5(coalesce(string_agg(concat_ws('|',id,estado_lectura,estado_persistencia,"
        "proximo_reintento_at,bloqueado_por,bloqueado_hasta,reprocesar_solicitado_at,ultimo_error_codigo,"
        "inventario_facturas::text),E'\\n' order by id),'')) from public.documentos_facturas")[0][0]
    out["huellas_facturas"] = dict(rows(
        "select id::text, md5(to_jsonb(f)::text) from public.facturas f order by id"))
    out["huella_normalizaciones"] = rows(
        "select md5(coalesce(string_agg(to_jsonb(e)::text,'' order by id),'')) "
        "from public.normalizacion_ejecuciones e")[0][0]
    out["huella_conciliaciones"] = rows(
        "select md5(coalesce(string_agg(to_jsonb(c)::text,'' order by id),'')) from public.conciliaciones c")[0][0]
    return out


def remoto(salida: Path) -> None:
    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    from dotenv import dotenv_values
    import psycopg2

    dsn = os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"]
    app = urlparse(dotenv_values(ROOT / ".env").get("SUPABASE_URL", ""))
    db = urlparse(dsn)
    ref = (app.hostname or "").split(".")[0]
    assert ref and (
        db.hostname == f"db.{ref}.supabase.co"
        or ((db.hostname or "").endswith(".pooler.supabase.com")
            and unquote(db.username or "").endswith("." + ref))
    ), "DESTINO_PRODUCTIVO_NO_DEMOSTRADO"
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_2as_readonly")
    conn.set_session(readonly=True, autocommit=False)
    try:
        with conn.cursor() as cur:
            cur.execute("set local statement_timeout='60s'")

            def rows(sql):
                cur.execute(sql)
                return cur.fetchall()

            out = {"project_ref": ref,
                   "transaction_read_only": rows("select current_setting('transaction_read_only')")[0][0],
                   "version": rows("select version()")[0][0]}
            out["definiciones"] = json.loads(rows(SQL_DEFINICIONES)[0][0])
            out["definiciones_completas"] = json.loads(rows(SQL_DEFINICIONES_COMPLETAS)[0][0])
            out["selector_sha256"] = hashlib.sha256(rows(SQL_SELECTOR_TEXTO)[0][0].encode()).hexdigest()
            out["marcadores"] = rows(
                "select to_regprocedure('public.cf_preflight_pio_valido()') is not null,"
                "to_regclass('public.proveedores') is not null,"
                "to_regprocedure('public.cf_reclamar_documento_normalizacion(text,integer)') is not null,"
                "to_regclass('public.facturas_movimientos') is not null,"
                "to_regclass('public.conciliaciones') is not null,"
                "to_regprocedure('public.cf_evaluar_elegibilidad_conciliacion(uuid)') is not null,"
                "to_regprocedure('public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[])') is not null,"
                "to_regprocedure('public.cf_reclamar_documento_normalizacion_manual_one_shot(text,integer)') is not null,"
                "to_regprocedure('public.cf_cerrar_replay_normalizacion(uuid,text,uuid,text)') is not null,"
                "to_regprocedure('public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text)') is not null,"
                "exists(select 1 from information_schema.columns where table_schema='public' "
                "and table_name='documentos_facturas' and column_name='intentos_fallo_normalizacion')")
            out.update(_operacion(rows))
            out["default_acl"] = rows(
                "select defaclrole::regrole::text, coalesce(defaclnamespace::regnamespace::text,'*'), "
                "defaclobjtype::text, defaclacl::text from pg_default_acl order by 1,2,3")
            out["matriz_grants"] = json.loads(rows(SQL_MATRIZ_GRANTS)[0][0])
            out["propietarios"] = rows(
                "select p.oid::regprocedure::text, pg_get_userbyid(p.proowner) from pg_proc p "
                f"where p.pronamespace='public'::regnamespace and p.proname in ({_LISTA_F}) order by 1")
            elegibles = [r[0] for r in rows(SQL_ELEGIBLES)]
            out["elegibles"] = {"total": len(elegibles), "primeros_5": elegibles[:5]}
            out["normalizada_pendiente"] = rows(
                "select d.id::text, d.fecha_importacion::text, d.estado_lectura, d.estado_persistencia, "
                "jsonb_array_length(d.inventario_facturas), d.reprocesar_solicitado_at::text, "
                "(select count(*) from public.facturas f where f.documento_id=d.id), "
                "(select string_agg(e.disparador||'/'||e.estado||'/'||e.iniciado_at::date, ', ' order by e.intento) "
                "   from public.normalizacion_ejecuciones e where e.documento_id=d.id), "
                "(select string_agg(distinct h.evento, ', ') from public.historial_facturas h where h.documento_id=d.id), "
                "(select min(h.created_at)::text from public.historial_facturas h where h.documento_id=d.id "
                "   and h.evento='INVENTARIO_MULTIFACTURA') "
                "from public.documentos_facturas d "
                "where d.estado_lectura='NORMALIZADA' and d.estado_persistencia='PENDIENTE' "
                "order by d.fecha_importacion")
            out["normalizada_pendiente"] = [list(f) for f in out["normalizada_pendiente"]]
            for fila in out["normalizada_pendiente"]:
                fila_id = fila[0]
                fila.append(elegibles.index(fila_id) + 1 if fila_id in elegibles else None)
            out["migracion_15_desplegada_hacia"] = rows(
                "select min(created_at)::text from public.historial_facturas where evento='INVENTARIO_MULTIFACTURA'")
    finally:
        conn.rollback()
        conn.close()
    salida.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def local(contenedor: str, db: str, salida: Path) -> None:
    def psql(sql):
        r = subprocess.run(["docker", "exec", "-i", contenedor, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                            "-U", "postgres", "-d", db], input=sql + ";", text=True, encoding="utf-8",
                           capture_output=True, timeout=120)
        if r.returncode:
            raise RuntimeError(r.stderr)
        return r.stdout.rstrip("\n")

    out = {"definiciones": json.loads(psql(SQL_DEFINICIONES)),
           "definiciones_completas": json.loads(psql(SQL_DEFINICIONES_COMPLETAS)),
           "selector_sha256": hashlib.sha256(psql(SQL_SELECTOR_TEXTO).encode()).hexdigest(),
           "matriz_grants": json.loads(psql(SQL_MATRIZ_GRANTS))}
    salida.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1] == "remoto":
        remoto(Path(sys.argv[2]))
    elif sys.argv[1] == "local":
        local(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
    else:
        raise SystemExit("modo desconocido")
