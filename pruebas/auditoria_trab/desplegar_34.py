"""Hito TRAB-34: despliega EXCLUSIVAMENTE la migracion 34 (guardias y festivos de Trabajadores, TA3), una vez, en una
transaccion.

NO se ejecuta en el hito TRAB-34 (solo se ensaya en local, con el rol que imita al postgres de Supabase). Requiere
confirmacion expresa de Pio en chat (hito TRAB-34-D). No invoca RPC. Normaliza el SQL a LF y exige que coincida byte a
byte con la version del commit indicado (git show <commit>:...). Revalida precondiciones dentro de la misma
transaccion. Error -> rollback y parada; nunca reintenta. Patron de pruebas/auditoria_trab/desplegar_31.py.

Uso: python pruebas/auditoria_trab/desplegar_34.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/34_cf_trabajadores_guardias.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
ROL = "cf_trabajadores_web"
LECTURA_GENERAL = "cf_lectura"
TABLAS_NUEVAS = ("guardias_semana", "guardias_festivo")
TABLA_RETIRADA = "guardias_farmacia"
# Escritura de la web tras la 34 (las de la 31 sin guardias_farmacia, la de la 33 y las dos nuevas) y objetos que solo
# lee.
ESCRITURA = ("trabajadoras", "convenio_anual", "eventos_calendario", "festivos", "trabajadoras_ajustes_anuales",
             *TABLAS_NUEVAS)
SOLO_LECTURA = ("trabajadores_historial", "cf_modulos_farmacias", "v_eventos_calendario_horas")
OBJETOS = ESCRITURA + SOLO_LECTURA
ESQUEMAS_VEDADOS = ("auth", "storage", "vault", "pgsodium", "pgsodium_masks", "supabase_functions", "net", "cron",
                    "realtime", "graphql")


def _lista(nombres) -> str:
    return "array[" + ", ".join(f"'{n}'" for n in nombres) + "]"


PRECONDICIONES = (
    # 1. 34 no aplicada: ni las tablas nuevas ni el festivo local sin farmacia.
    f"select to_regclass('public.{TABLAS_NUEVAS[0]}') is null and to_regclass('public.{TABLAS_NUEVAS[1]}') is null "
    "  and exists (select 1 from pg_constraint where conname = 'festivos_local_con_farmacia'),"
    # 2. 33 aplicada (con la 31 y la 32) y guardias_farmacia presente y VACIA (si no, se para: decision de Pio).
    "to_regclass('public.trabajadoras_ajustes_anuales') is not null "
    "  and to_regclass('public.cf_noches_automaticas') is not null "
    # (query_to_xml: si la tabla ya no existe, la condicion es falsa en lugar de un error de la consulta.)
    f"  and case when to_regclass('public.{TABLA_RETIRADA}') is null then false else (xpath('/row/c/text()', "
    f"  query_to_xml('select count(*) as c from public.{TABLA_RETIRADA}', false, true, '')))[1]::text = '0' end,"
    # 3. Roles presentes: la web (31) y cf_lectura (29).
    f"exists (select 1 from pg_roles where rolname = '{ROL}') "
    f"  and exists (select 1 from pg_roles where rolname = '{LECTURA_GENERAL}'),"
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
         "(select count(*) from public.albaranes), "
         "(select count(*) from public.trabajadoras), "
         "(select count(*) from public.eventos_calendario), "
         "(select count(*) from public.festivos), "
         "(select count(*) from public.trabajadoras_ajustes_anuales)], "
         "(select md5(coalesce(string_agg(md5(to_jsonb(f)::text), '' order by f.id), '')) from public.facturas f), "
         "(select md5(to_jsonb(c)::text) from public.cf_configuracion c where c.id)")

# ACL de las tablas nuevas: solo el propietario (quien despliega), el rol de la web y cf_lectura. Cualquier otro
# beneficiario (anon, authenticated, el rol del sistema o PUBLIC) -> falla.
ACL_AJENA = (
    "select count(*) from pg_class c cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a "
    f"where c.relnamespace = 'public'::regnamespace and c.relname = any({_lista(TABLAS_NUEVAS)}) "
    "  and a.grantee <> c.relowner "
    f"  and (a.grantee = 0 or pg_get_userbyid(a.grantee) <> all(array['{ROL}', '{LECTURA_GENERAL}']))")

# Funciones nuevas de la 34: solo el propietario puede ejecutarlas (las usan los triggers).
FUNCIONES_NUEVAS = ("cf_trab_comprobar_farmacia_guardia", "cf_trab_persona_de_alta", "cf_trab_comprobar_guardia_semana",
                    "cf_trab_comprobar_guardia_festivo", "cf_trab_anular_guardia_de_festivo")
ACL_FUNCIONES_AJENA = (
    "select count(*) from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
    f"where p.pronamespace = 'public'::regnamespace and p.proname = any({_lista(FUNCIONES_NUEVAS)}) "
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

_POLITICAS = " and ".join(
    f"(select count(*) from pg_policy where polrelid = 'public.{t}'::regclass) = 3 "
    f"and (select relrowsecurity from pg_class where oid = 'public.{t}'::regclass)" for t in TABLAS_NUEVAS)

POSTCONDICIONES = (
    f"{DATOS},"
    # Privilegios de la web, con las tablas nuevas y sin guardias_farmacia.
    f"{PRIVILEGIOS_WEB},"
    # cf_lectura lee las tablas nuevas y no escribe; nadie mas tiene privilegios sobre ellas ni sobre las funciones.
    + " and ".join(f"has_table_privilege('{LECTURA_GENERAL}', 'public.{t}', 'SELECT') "
                   f"and not has_table_privilege('{LECTURA_GENERAL}', 'public.{t}', 'INSERT,UPDATE,DELETE,TRUNCATE')"
                   for t in TABLAS_NUEVAS)
    + f" and ({ACL_AJENA}) = 0 and ({ACL_FUNCIONES_AJENA}) = 0 "
    f"  and (select count(*) from pg_proc where pronamespace = 'public'::regnamespace "
    f"       and proname = any({_lista(FUNCIONES_NUEVAS)})) = {len(FUNCIONES_NUEVAS)},"
    # RLS de las tablas nuevas con sus 3 politicas; unicidades parciales; guardias_farmacia retirada; festivo local sin
    # farmacia admitido; historial visible tambien para OTRA; permiso del modulo y global intactos.
    f"{_POLITICAS} "
    "  and (select indisunique and indpred is not null from pg_index "
    "       where indexrelid = 'public.guardias_semana_lunes_unico'::regclass) "
    "  and (select indisunique and indpred is not null from pg_index "
    "       where indexrelid = 'public.guardias_festivo_fecha_unico'::regclass) "
    f"  and to_regclass('public.{TABLA_RETIRADA}') is null "
    "  and not exists (select 1 from pg_constraint where conname = 'festivos_local_con_farmacia') "
    "  and exists (select 1 from pg_trigger where tgname = 'festivos_anular_guardia' "
    "              and tgrelid = 'public.festivos'::regclass) "
    "  and (select pg_get_expr(polqual, polrelid) like '%OTRA%' from pg_policy "
    "       where polname = 'trabajadores_historial_trab_select') "
    "  and (select farmacias = array['PIO', 'RITA']::text[] from public.cf_modulos_farmacias "
    "  where modulo = 'TRABAJADORES') and (select farmacias_habilitadas = array['PIO']::text[] "
    "  from public.cf_configuracion where id),"
    # Propietario de las tablas nuevas: quien despliega (postgres en Supabase).
    "(select bool_and(pg_get_userbyid(relowner) = current_user) from pg_class "
    f" where relnamespace = 'public'::regnamespace and relname = any({_lista(TABLAS_NUEVAS)}))")


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_34_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_34_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_trab_deploy_34")
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
            conteos, facturas, configuracion, privilegios, lectura, estructura, propietario = cur.fetchone()
            registro["postcondiciones"] = {
                "datos_sin_cambios": [list(conteos), facturas, configuracion] == datos_antes,
                "privilegios_web": privilegios, "lectura_y_acl": lectura, "estructura_y_rls": estructura,
                "propietario": propietario}
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


def cli(argv: list[str]) -> None:
    """Entrada de linea de ordenes: antes de nada, el commit indicado debe estar ya en el main del remoto (leido con
    ls-remote; modulo comun ``puerta_git``, 2026-11-19). ``main`` sigue siendo ensayable sin remoto."""
    if len(argv) != 3:
        raise SystemExit(__doc__)
    sys.path.insert(0, str(ROOT))
    from src.facturas.runtime_supabase.puerta_git import exigir_commit_en_origen
    exigir_commit_en_origen(argv[0], ROOT)
    main(argv[0], argv[1], Path(argv[2]))


if __name__ == "__main__":
    cli(sys.argv[1:])
