"""Hito 2BN: despliega EXCLUSIVAMENTE la migracion 29 (rol de solo lectura cf_lectura), una vez, en una transaccion.

NO se ejecuta en el hito 2BN (solo se ensaya en local). Requiere confirmacion expresa de Pio en chat. No invoca
RPC funcionales. Normaliza el SQL a LF y exige que coincida byte a byte con la version del commit indicado
(git show <commit>:...). Revalida precondiciones dentro de la misma transaccion. Error -> rollback y parada;
nunca reintenta. La contrasena del rol NO forma parte de la migracion: la fija Pio despues, fuera del repositorio.
Patron de pruebas/auditoria_2bm/desplegar_28.py.

Uso: python pruebas/auditoria_2bn/desplegar_29.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/29_cf_rol_lectura.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
ROL = "cf_lectura"
# Politicas de lectura de authenticated que pasan a aplicarse tambien a cf_lectura (tabla, politica).
POLITICAS_COMPARTIDAS = (
    ("documentos_facturas", "documentos_facturas_authenticated_select"),
    ("facturas", "facturas_authenticated_select"),
    ("facturas_vencimientos", "facturas_vencimientos_authenticated_select"),
    ("facturas_impuestos", "facturas_impuestos_authenticated_select"),
    ("facturas_albaranes_extraidos", "facturas_albaranes_extraidos_authenticated_select"),
    ("facturas_ajustes", "facturas_ajustes_authenticated_select"),
    ("facturas_movimientos", "facturas_movimientos_authenticated_select"),
    ("facturas_incidencias", "facturas_incidencias_authenticated_select"),
    ("historial_facturas", "historial_facturas_authenticated_select"),
    ("normalizacion_ejecuciones", "normalizacion_ejecuciones_authenticated_select"),
    ("conciliaciones", "conciliaciones_authenticated_select"),
    ("conciliacion_detalles", "conciliacion_detalles_authenticated_select"),
    ("proveedores", "proveedores_authenticated_select"),
    ("proveedores_alias", "proveedores_alias_authenticated_select"),
    ("cf_configuracion", "cf_configuracion_authenticated_select"),
)
POLITICAS_NUEVAS = (
    ("albaranes", "albaranes_lectura_select"),
    ("albaranes_cambios", "albaranes_cambios_lectura_select"),
    ("albaranes_aprobaciones", "albaranes_aprobaciones_lectura_select"),
    ("albaranes_aprobaciones_aplicadas", "albaranes_aprobaciones_aplicadas_lectura_select"),
    ("conciliacion_albaranes_reservados", "conciliacion_albaranes_reservados_lectura_select"),
)
LECTURA = tuple(t for t, _ in POLITICAS_COMPARTIDAS + POLITICAS_NUEVAS) + (
    "v_facturas_listado", "v_dashboard_diario", "v_vencimientos_calendario", "v_proveedores_estado")
# Esquemas con secretos o servicios de Supabase: sin USAGE para cf_lectura (los que existan).
ESQUEMAS_VEDADOS = ("auth", "storage", "vault", "pgsodium", "pgsodium_masks", "supabase_functions", "net", "cron",
                    "realtime", "graphql")


def _roles_politica(tabla: str, politica: str) -> str:
    return (f"(select array(select coalesce(r.rolname, 'public') from unnest(p.polroles) o "
            f"left join pg_roles r on r.oid = o order by 1) from pg_policy p "
            f"where p.polrelid = 'public.{tabla}'::regclass and p.polname = '{politica}')")


PRECONDICIONES = (
    # 29 no aplicada en esta base: el rol (del cluster), si existe, sin ningun privilegio en public; sin politicas
    # nuevas. CASE para no evaluar has_table_privilege con un rol inexistente.
    f"select case when exists (select 1 from pg_roles where rolname = '{ROL}') then not exists ("
    f"  select 1 from pg_class c where c.relnamespace = 'public'::regnamespace "
    f"  and has_table_privilege('{ROL}', c.oid, 'SELECT,INSERT,UPDATE,DELETE')) else true end "
    + "".join(f"  and not exists (select 1 from pg_policy where polrelid = 'public.{t}'::regclass "
              f"and polname = '{p}') " for t, p in POLITICAS_NUEVAS) + ","
    # 28 aplicada.
    "to_regprocedure('public.cf_materializar_referencia()') is not null,"
    # Las politicas que se amplian son las de la 28: solo para authenticated.
    + " and ".join(f"{_roles_politica(t, p)} = array['authenticated']::name[]" for t, p in POLITICAS_COMPARTIDAS)
    + ","
    # 19: privilegios minimos.
    "not has_table_privilege('anon', 'public.facturas', 'SELECT') "
    "  and not has_table_privilege('authenticated', 'public.albaranes', 'UPDATE'),"
    "(select normalizacion_automatica=false and conciliacion_automatica=false and luna_habilitada=false "
    "  and farmacias_habilitadas=array['PIO']::text[] from public.cf_configuracion where id),"
    "(select count(*)=0 from public.facturas where conciliacion_bloqueado_por is not null "
    "  or conciliacion_bloqueado_hasta>now()),"
    "(select count(*)=0 from public.documentos_facturas where bloqueado_por is not null "
    "  or bloqueado_hasta>now() or estado_lectura='NORMALIZANDO'),"
    # Reservas coherentes con las conciliaciones vigentes (R15).
    "(select count(*) from public.conciliacion_albaranes_reservados) = "
    "  (select count(*) from public.conciliacion_detalles d join public.conciliaciones c "
    "   on c.id=d.conciliacion_id where c.es_actual and d.albaran_id_contador is not null),"
    # 2AX: ningun objeto de public con propietario distinto de postgres.
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
         "(select count(*) from public.conciliacion_albaranes_reservados)], "
         "(select md5(coalesce(string_agg(md5(to_jsonb(f)::text), '' order by f.id), '')) from public.facturas f)")

POSTCONDICIONES = (
    f"{DATOS},"
    # Rol: LOGIN, sin atributos privilegiados, solo lectura por defecto.
    f"(select rolcanlogin and not rolsuper and not rolbypassrls and not rolcreaterole and not rolcreatedb "
    f"  and not rolreplication and 'default_transaction_read_only=on' = any(rolconfig) "
    f"  from pg_roles where rolname = '{ROL}'),"
    # Lectura de la lista cerrada; ninguna escritura en public; ninguna funcion privilegiada o que escriba.
    + " and ".join(f"has_table_privilege('{ROL}', 'public.{o}', 'SELECT')" for o in LECTURA)
    + f"  and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace "
    f"  and c.relkind in ('r','p','v','m','f') and (has_table_privilege('{ROL}', c.oid, "
    f"  'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') or (has_table_privilege('{ROL}', c.oid, 'SELECT') "
    f"  and c.relname <> all(array[{', '.join(repr(o) for o in LECTURA)}]))))"
    f"  and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind = 'S' "
    f"  and case when c.relkind = 'S' then has_sequence_privilege('{ROL}', c.oid, 'USAGE,SELECT,UPDATE') end)"
    f"  and not exists (select 1 from pg_proc p where p.pronamespace = 'public'::regnamespace "
    f"  and has_function_privilege('{ROL}', p.oid, 'EXECUTE') and (p.prosecdef or (p.provolatile = 'v' "
    f"  and p.prorettype <> 'trigger'::regtype)))"
    + "".join(f"  and not coalesce(has_schema_privilege('{ROL}', to_regnamespace('{e}'), 'USAGE'), false)"
              for e in ESQUEMAS_VEDADOS)
    + "  and not has_table_privilege('authenticated', 'public.albaranes', 'UPDATE'),"
    # RLS: politicas compartidas con cf_lectura y politicas nuevas solo para cf_lectura.
    + " and ".join(f"{_roles_politica(t, p)} = array['authenticated', '{ROL}']::name[]"
                   for t, p in POLITICAS_COMPARTIDAS)
    + "".join(f" and {_roles_politica(t, p)} = array['{ROL}']::name[]" for t, p in POLITICAS_NUEVAS))


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_29_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_29_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_2bn_deploy_29")
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
            # Comprobacion dentro de la misma transaccion: rol, privilegios y politicas; ninguna fila cambiada.
            cur.execute(POSTCONDICIONES)
            conteos, facturas, rol, privilegios, politicas = cur.fetchone()
            registro["postcondiciones"] = {"datos_sin_cambios": [list(conteos), facturas] == datos_antes,
                                           "rol": rol, "privilegios": privilegios, "politicas": politicas}
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
