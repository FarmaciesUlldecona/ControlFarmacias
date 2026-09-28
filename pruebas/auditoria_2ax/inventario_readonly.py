"""Hito 2AX: inventario de privilegios ESTRICTAMENTE READ_ONLY (sin secretos).

Uso:
  python pruebas/auditoria_2ax/inventario_readonly.py remoto <salida.json>
  python pruebas/auditoria_2ax/inventario_readonly.py local <contenedor> <db> <salida.json>

Vuelca la matriz de ACL efectivas (entradas explicitas de relacl/proacl o el ACL
por defecto del propietario si es nulo) de tablas, vistas, secuencias y
funciones de ``public`` para PUBLIC, anon, authenticated y service_role; los
privilegios por defecto (pg_default_acl) de todos los roles sobre public; RLS y
politicas; y, en remoto, storage (buckets y politicas de storage.objects),
operacion y huellas de datos. No llama a ninguna RPC.
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
ROLES = "array['PUBLIC','anon','authenticated','service_role']"

SQL_MATRIZ = f"""
with rel as (
  select c.relname as nombre, case c.relkind when 'S' then 'secuencia' when 'v' then 'vista'
         when 'm' then 'vista_materializada' else 'tabla' end as tipo,
         coalesce(c.relacl, acldefault(case when c.relkind = 'S' then 's'::"char" else 'r'::"char" end, c.relowner)) as acl,
         c.relacl is null as acl_nulo, pg_get_userbyid(c.relowner) as owner,
         c.relrowsecurity as rls
    from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind in ('r','p','v','m','S')
), fun as (
  select p.oid::regprocedure::text as nombre, 'funcion' as tipo,
         coalesce(p.proacl, acldefault('f', p.proowner)) as acl, p.proacl is null as acl_nulo,
         pg_get_userbyid(p.proowner) as owner, p.prosecdef as definer
    from pg_proc p where p.pronamespace = 'public'::regnamespace
       and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
), obj as (
  select nombre, tipo, acl, acl_nulo, owner, rls, null::boolean as definer from rel
  union all select nombre, tipo, acl, acl_nulo, owner, null, definer from fun
)
select coalesce(jsonb_object_agg(o.tipo || ':' || o.nombre, jsonb_build_object(
  'owner', o.owner, 'acl_nulo', o.acl_nulo, 'rls', o.rls, 'definer', o.definer,
  'privilegios', (select coalesce(jsonb_object_agg(r.rol, coalesce((
        select jsonb_agg(a.privilege_type order by a.privilege_type) from aclexplode(o.acl) a
         where a.grantee = case r.rol when 'PUBLIC' then 0 else (select oid from pg_roles where rolname = r.rol) end
      ), '[]'::jsonb)), '{{}}'::jsonb) from unnest({ROLES}) r(rol)))), '{{}}'::jsonb)::text
from obj o
"""

SQL_DEFAULT_ACL = """
select coalesce(jsonb_agg(jsonb_build_object(
  'rol', pg_get_userbyid(d.defaclrole), 'esquema', case when d.defaclnamespace = 0 then '*' else d.defaclnamespace::regnamespace::text end,
  'tipo', d.defaclobjtype::text, 'acl', d.defaclacl::text)
  order by pg_get_userbyid(d.defaclrole), d.defaclobjtype), '[]'::jsonb)::text
from pg_default_acl d where d.defaclnamespace = 'public'::regnamespace or d.defaclnamespace = 0
"""

SQL_POLITICAS = """
select coalesce(jsonb_object_agg(c.relname || '.' || pol.polname, jsonb_build_object(
  'cmd', pol.polcmd::text,
  'roles', array(select coalesce(rr.rolname, 'public') from unnest(pol.polroles) r(oid) left join pg_roles rr on rr.oid = r.oid),
  'using', pg_get_expr(pol.polqual, pol.polrelid))), '{}'::jsonb)::text
from pg_policy pol join pg_class c on c.oid = pol.polrelid where c.relnamespace = 'public'::regnamespace
"""

SQL_STORAGE = """
select jsonb_build_object(
  'buckets', (select coalesce(jsonb_agg(jsonb_build_object('id', id, 'public', public) order by id), '[]'::jsonb)
                from storage.buckets),
  'politicas_objects', (select coalesce(jsonb_agg(jsonb_build_object('nombre', pol.polname, 'cmd', pol.polcmd::text,
        'roles', array(select coalesce(rr.rolname, 'public') from unnest(pol.polroles) r(oid) left join pg_roles rr on rr.oid = r.oid),
        'using', pg_get_expr(pol.polqual, pol.polrelid), 'check', pg_get_expr(pol.polwithcheck, pol.polrelid))
        order by pol.polname), '[]'::jsonb)
      from pg_policy pol where pol.polrelid = 'storage.objects'::regclass),
  'objects_rls', (select relrowsecurity from pg_class where oid = 'storage.objects'::regclass)
)::text
"""

HUELLAS = {t: f"select md5(coalesce(string_agg(to_jsonb(t)::text, '|' order by to_jsonb(t)::text), '')), count(*) from public.{t} t"
           for t in ("facturas", "conciliaciones", "conciliacion_detalles", "documentos_facturas", "albaranes",
                     "normalizacion_ejecuciones", "historial_facturas", "cf_configuracion")}


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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_2ax_readonly")
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
                   "matriz": json.loads(rows(SQL_MATRIZ)[0][0]),
                   "default_acl": json.loads(rows(SQL_DEFAULT_ACL)[0][0]),
                   "politicas": json.loads(rows(SQL_POLITICAS)[0][0]),
                   "storage": json.loads(rows(SQL_STORAGE)[0][0])}
            out["flags"] = list(rows("select normalizacion_automatica,conciliacion_automatica,luna_habilitada,"
                                     "farmacias_habilitadas::text from public.cf_configuracion where id")[0])
            out["operacion"] = list(rows(
                "select (select count(*) from public.documentos_facturas where bloqueado_hasta>now() or bloqueado_por is not null),"
                "(select count(*) from public.facturas where conciliacion_bloqueado_hasta>now() "
                " or conciliacion_bloqueado_por is not null),"
                "(select count(*) from public.documentos_facturas where estado_lectura='NORMALIZANDO'),"
                "(select count(*) from pg_stat_activity where pid<>pg_backend_pid() and "
                " (application_name ilike '%worker%' or application_name ilike '%runtime%'))")[0])
            out["huellas"] = {t: list(rows(q)[0]) for t, q in HUELLAS.items()}
    finally:
        conn.rollback()
        conn.close()
    salida.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("project_ref", "transaction_read_only", "capturado_utc",
                                          "flags", "operacion", "storage")}, ensure_ascii=False, indent=1))
    print("sha256", hashlib.sha256(salida.read_bytes()).hexdigest())


def local(contenedor: str, db: str, salida: Path) -> None:
    def psql(sql):
        r = subprocess.run(["docker", "exec", "-i", contenedor, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                            "-U", "postgres", "-d", db], input=sql + ";", text=True, encoding="utf-8",
                           capture_output=True, timeout=120)
        if r.returncode:
            raise RuntimeError(r.stderr)
        return r.stdout.rstrip("\n")

    out = {"matriz": json.loads(psql(SQL_MATRIZ)), "default_acl": json.loads(psql(SQL_DEFAULT_ACL)),
           "politicas": json.loads(psql(SQL_POLITICAS))}
    salida.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1] == "remoto":
        remoto(Path(sys.argv[2]))
    elif sys.argv[1] == "local":
        local(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
    else:
        raise SystemExit("modo desconocido")
