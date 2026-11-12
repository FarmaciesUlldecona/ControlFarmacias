"""Hito TRAB: despliega EXCLUSIVAMENTE la migracion 31 (esquema de Trabajadores), una vez, en una transaccion.

NO se ejecuta en el hito TRAB (solo se ensaya en local, con el rol que imita al postgres de Supabase). Requiere
confirmacion expresa de Pio en chat (hito TRAB-D). No invoca RPC. Normaliza el SQL a LF y exige que coincida byte a
byte con la version del commit indicado (git show <commit>:...). Revalida precondiciones dentro de la misma
transaccion. Error -> rollback y parada; nunca reintenta. La contrasena del rol cf_trabajadores_web NO forma parte de
la migracion: la fija Pio despues, fuera del repositorio. Patron de pruebas/auditoria_2bn/desplegar_29.py.

Uso: python pruebas/auditoria_trab/desplegar_31.py <commit> <sha256_lf_esperado> <salida.json>
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
RUTA = "sql/migrations/31_cf_trabajadores.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
ROL = "cf_trabajadores_web"
LECTURA_GENERAL = "cf_lectura"
ESCRITURA = ("trabajadoras", "convenio_anual", "eventos_calendario", "guardias_farmacia", "festivos")
SOLO_LECTURA = ("trabajadores_historial", "cf_modulos_farmacias", "v_eventos_calendario_horas")
TABLAS = ("cf_modulos_farmacias",) + ESCRITURA + ("trabajadores_historial",)
OBJETOS = TABLAS + ("v_eventos_calendario_horas",)
FUNCIONES = ("cf_trab_comprobar_farmacia()", "cf_trab_comprobar_evento()", "cf_trab_historial()",
             "cf_trab_historial_solo_insercion()")
ESQUEMAS_VEDADOS = ("auth", "storage", "vault", "pgsodium", "pgsodium_masks", "supabase_functions", "net", "cron",
                    "realtime", "graphql")


def _lista(nombres) -> str:
    return "array[" + ", ".join(f"'{n}'" for n in nombres) + "]"


PRECONDICIONES = (
    # 1. 31 no aplicada: ningun objeto nuevo; el rol (del cluster), si existe, sin ningun privilegio en public.
    "select " + " and ".join(f"to_regclass('public.{o}') is null" for o in OBJETOS)
    + " and " + " and ".join(f"to_regprocedure('public.{f}') is null" for f in FUNCIONES)
    + f" and case when exists (select 1 from pg_roles where rolname = '{ROL}') then not exists ("
    f"  select 1 from pg_class c where c.relnamespace = 'public'::regnamespace "
    f"  and has_table_privilege('{ROL}', c.oid, 'SELECT,INSERT,UPDATE,DELETE')) else true end,"
    # 2. 30 aplicada.
    "to_regclass('public.conciliacion_detalles_previo_30') is not null,"
    # 3. cf_lectura (29) presente.
    f"exists (select 1 from pg_roles where rolname = '{LECTURA_GENERAL}'),"
    # 4. 19: privilegios minimos.
    "not has_table_privilege('anon', 'public.facturas', 'SELECT') "
    "  and not has_table_privilege('authenticated', 'public.albaranes', 'UPDATE'),"
    # 5. Flags: solo PIO para facturas, albaranes y conciliacion.
    "(select normalizacion_automatica=false and conciliacion_automatica=false and luna_habilitada=false "
    "  and farmacias_habilitadas=array['PIO']::text[] from public.cf_configuracion where id),"
    # 6. Sin claims de conciliacion ni de normalizacion.
    "(select count(*)=0 from public.facturas where conciliacion_bloqueado_por is not null "
    "  or conciliacion_bloqueado_hasta>now()) and "
    "(select count(*)=0 from public.documentos_facturas where bloqueado_por is not null "
    "  or bloqueado_hasta>now() or estado_lectura='NORMALIZANDO'),"
    # 7. 2AX: ningun objeto de public con propietario distinto de postgres.
    "(select count(*)=0 from pg_class c where c.relnamespace='public'::regnamespace "
    "  and c.relkind in ('r','p','v','m','S','f') and pg_get_userbyid(c.relowner)<>'postgres') and "
    "(select count(*)=0 from pg_proc p where p.pronamespace='public'::regnamespace "
    "  and pg_get_userbyid(p.proowner)<>'postgres' "
    "  and not exists(select 1 from pg_depend d where d.objid=p.oid and d.deptype='e'))")

DATOS = ("select array[(select count(*) from public.documentos_facturas), "
         "(select count(*) from public.facturas), "
         "(select count(*) from public.normalizacion_ejecuciones), "
         "(select count(*) from public.historial_facturas), "
         "(select count(*) from public.conciliaciones), "
         "(select count(*) from public.conciliacion_detalles), "
         "(select count(*) from public.conciliacion_albaranes_reservados), "
         "(select count(*) from public.albaranes)], "
         "(select md5(coalesce(string_agg(md5(to_jsonb(f)::text), '' order by f.id), '')) from public.facturas f), "
         "(select md5(to_jsonb(c)::text) from public.cf_configuracion c where c.id)")

# ACL de los objetos nuevos: solo el propietario (quien despliega), el rol de la web y cf_lectura. Cualquier otro
# beneficiario (anon, authenticated, el rol del sistema o PUBLIC) -> falla.
ACL_AJENA = (
    "select count(*) from pg_class c cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a "
    f"where c.oid = any(array(select to_regclass('public.' || o) from unnest({_lista(OBJETOS)}) o)) "
    "  and a.grantee <> c.relowner "
    f"  and (a.grantee = 0 or pg_get_userbyid(a.grantee) <> all(array['{ROL}', '{LECTURA_GENERAL}']))")
ACL_AJENA_SECUENCIA = (
    "select count(*) from pg_class c cross join lateral aclexplode(coalesce(c.relacl, acldefault('s', c.relowner))) a "
    "where c.oid = 'public.trabajadores_historial_id_seq'::regclass and a.grantee <> c.relowner")
ACL_AJENA_FUNCIONES = (
    "select count(*) from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
    f"where p.oid = any(array(select to_regprocedure('public.' || f) from unnest({_lista(FUNCIONES)}) f)) "
    "  and a.grantee <> p.proowner")

PRIVILEGIOS_WEB = (
    " and ".join(f"has_table_privilege('{ROL}', 'public.{t}', 'SELECT,INSERT,UPDATE')" for t in ESCRITURA)
    + " and " + " and ".join(f"has_table_privilege('{ROL}', 'public.{t}', 'SELECT')" for t in SOLO_LECTURA)
    # Nada mas: ni DELETE/TRUNCATE en el modulo, ni escritura en historial o permisos, ni lectura fuera del modulo.
    + f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace "
    f"  and c.relkind in ('r','p','v','m','f') and (has_table_privilege('{ROL}', c.oid, "
    f"  'DELETE,TRUNCATE,REFERENCES,TRIGGER') "
    f"  or (has_table_privilege('{ROL}', c.oid, 'INSERT,UPDATE') and c.relname <> all({_lista(ESCRITURA)})) "
    f"  or (has_table_privilege('{ROL}', c.oid, 'SELECT') and c.relname <> all({_lista(OBJETOS)}))))"
    f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind = 'S' "
    f"  and case when c.relkind = 'S' then has_sequence_privilege('{ROL}', c.oid, 'USAGE,SELECT,UPDATE') end)"
    f" and not exists (select 1 from pg_proc p where p.pronamespace = 'public'::regnamespace "
    f"  and has_function_privilege('{ROL}', p.oid, 'EXECUTE') and p.prorettype <> 'event_trigger'::regtype "
    f"  and (p.prosecdef or (p.provolatile = 'v' and p.prorettype <> 'trigger'::regtype)))"
    + "".join(f" and not coalesce(has_schema_privilege('{ROL}', to_regnamespace('{e}'), 'USAGE'), false)"
              for e in ESQUEMAS_VEDADOS))

POSTCONDICIONES = (
    f"{DATOS},"
    # Rol: LOGIN, sin atributos privilegiados, sin pertenencias.
    f"(select rolcanlogin and not rolsuper and not rolbypassrls and not rolcreaterole and not rolcreatedb "
    f"  and not rolreplication and not rolinherit and rolconnlimit = 5 "
    f"  and 'statement_timeout=60s' = any(rolconfig) from pg_roles where rolname = '{ROL}') "
    f"  and not exists (select 1 from pg_auth_members where member = '{ROL}'::regrole),"
    # Privilegios de la web.
    f"{PRIVILEGIOS_WEB},"
    # cf_lectura lee los objetos nuevos y no escribe; nadie mas tiene privilegios sobre ellos.
    + " and ".join(f"has_table_privilege('{LECTURA_GENERAL}', 'public.{o}', 'SELECT')" for o in OBJETOS)
    + " and " + " and ".join(f"not has_table_privilege('{LECTURA_GENERAL}', 'public.{t}', "
                             f"'INSERT,UPDATE,DELETE,TRUNCATE')" for t in TABLAS)
    + f" and ({ACL_AJENA}) = 0 and ({ACL_AJENA_SECUENCIA}) = 0 and ({ACL_AJENA_FUNCIONES}) = 0,"
    # RLS en las 7 tablas, con politicas; permiso del modulo = {PIO,RITA}; global intacto.
    + " and ".join(f"(select relrowsecurity from pg_class where oid = 'public.{t}'::regclass)" for t in TABLAS)
    + " and (select count(*) from pg_policy where polrelid = any(array(select to_regclass('public.' || t) "
    f"  from unnest({_lista(TABLAS)}) t))) = 17"
    " and (select farmacias = array['PIO', 'RITA']::text[] from public.cf_modulos_farmacias "
    "  where modulo = 'TRABAJADORES') and (select count(*) = 1 from public.cf_modulos_farmacias)"
    " and (select farmacias_habilitadas = array['PIO']::text[] from public.cf_configuracion where id),"
    # Propietarios: los objetos nuevos, de quien despliega (postgres en Supabase).
    + " and ".join(f"(select pg_get_userbyid(relowner) = current_user from pg_class "
                   f"where oid = 'public.{o}'::regclass)" for o in OBJETOS)
    + " and " + " and ".join(f"(select pg_get_userbyid(proowner) = current_user from pg_proc "
                             f"where oid = 'public.{f}'::regprocedure)" for f in FUNCIONES))


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_31_NO_COINCIDE_CON_COMMIT")
    return local


def cuerpo_transaccional(sql: str) -> str:
    """Quita el begin/commit exterior: la transaccion la gestiona el script."""
    lineas = sql.split("\n")
    inicio = lineas.index("begin;")
    fin = len(lineas) - 1 - lineas[::-1].index("commit;")
    assert all(l.startswith("--") or not l.strip() for l in lineas[:inicio])
    assert all(not l.strip() for l in lineas[fin + 1:])
    return "\n".join(lineas[inicio + 1:fin])


def main(commit: str, esperado: str, salida: Path) -> None:
    sql = sql_lf(commit)
    sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    if sha != esperado:
        raise SystemExit(f"SHA256_MIGRACION_31_INESPERADO:{sha}")
    cuerpo = cuerpo_transaccional(sql)

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

    registro = {"project_ref": ref, "migracion": RUTA, "commit": commit, "sha256_lf": sha,
                "inicio_utc": datetime.now(timezone.utc).isoformat()}
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_trab_deploy_31")
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("set local lock_timeout='5s'; set local statement_timeout='120s'")
            cur.execute(PRECONDICIONES)
            pre = cur.fetchone()
            registro["precondiciones"] = list(pre)
            if not all(pre):
                raise RuntimeError(f"PRECONDICIONES_NO_CUMPLIDAS:{list(pre)}")
            cur.execute(DATOS)
            datos_antes = list(cur.fetchone())
            cur.execute(cuerpo)
            cur.execute(POSTCONDICIONES)
            conteos, facturas, configuracion, rol, privilegios, acl, rls, propietarios = cur.fetchone()
            registro["postcondiciones"] = {
                "datos_sin_cambios": [list(conteos), facturas, configuracion] == datos_antes, "rol": rol,
                "privilegios_web": privilegios, "acl": acl, "rls_y_modulo": rls, "propietarios": propietarios}
            if set(registro["postcondiciones"].values()) != {True}:
                raise RuntimeError(f"POSTCONDICIONES_NO_CUMPLIDAS:{registro['postcondiciones']}")
        conn.commit()
        registro["resultado"] = "APLICADA"
    except Exception as exc:
        conn.rollback()
        registro["resultado"] = "REVERTIDA"
        registro["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        conn.close()
        registro["fin_utc"] = datetime.now(timezone.utc).isoformat()
        salida.write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: registro.get(k) for k in ("resultado", "sha256_lf", "precondiciones", "postcondiciones")},
                     ensure_ascii=False))
    if registro["resultado"] != "APLICADA":
        raise SystemExit(registro.get("error"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
