"""Hito H6: despliega EXCLUSIVAMENTE la migracion 35 (marcas de pago de vencimientos y forma de pago por proveedor),
una vez, en una transaccion.

NO se ejecuta en el hito H6 (solo se ensaya en local, con el rol que imita al postgres de Supabase). Requiere
confirmacion expresa de Pio en chat (hito H6-D). No invoca RPC. Normaliza el SQL a LF y exige que coincida byte a byte
con la version del commit indicado (git show <commit>:...). Revalida precondiciones dentro de la misma transaccion.
Error -> rollback y parada; nunca reintenta. Patron de pruebas/auditoria_trab/desplegar_34.py. No comprueba ni lee la
contrasena de cf_pagos_web: la fija Pio despues, fuera del repositorio, con SCRAM (DISENO §5).

Uso: python pruebas/auditoria_h6/desplegar_35.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/35_cf_pagos_marcas.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
ROL = "cf_pagos_web"
LECTURA_GENERAL = "cf_lectura"
ROL_TRABAJADORES = "cf_trabajadores_web"
# La web escribe solo en dos tablas y lee su historial (DISENO §2.5).
ESCRITURA = ("vencimientos_marcas_pago", "proveedores_forma_pago")
SOLO_LECTURA = ("pagos_historial",)
TABLAS_NUEVAS = ESCRITURA + SOLO_LECTURA
OBJETOS = TABLAS_NUEVAS
SECUENCIA_NUEVA = "pagos_historial_id_seq"
# Funcion de la RLS de la web: la unica que cf_pagos_web puede ejecutar.
FUNCION_RLS = "cf_pagos_farmacia_habilitada"
FUNCIONES_NUEVAS = (FUNCION_RLS, "cf_pagos_dia_madrid", "cf_pagos_comprobar_farmacia", "cf_pagos_validar_marca",
                    "cf_pagos_solo_anular", "cf_pagos_historial", "cf_pagos_historial_solo_insercion")
# Tablas de facturas que las marcas referencian sin clave externa (D7): su estructura no puede cambiar.
TABLAS_FACTURAS = ("facturas", "facturas_vencimientos")
ESQUEMAS_VEDADOS = ("auth", "storage", "vault", "pgsodium", "pgsodium_masks", "supabase_functions", "net", "cron",
                    "realtime", "graphql")


def _lista(nombres) -> str:
    return "array[" + ", ".join(f"'{n}'" for n in nombres) + "]"


def _regclases(nombres) -> str:
    return "array[" + ", ".join(f"'public.{n}'::regclass" for n in nombres) + "]"


PRECONDICIONES = (
    # 1. 35 no aplicada: ninguna tabla nueva. (El rol es del cluster: si ya existiera, la postcondicion de sus
    #    atributos decide.)
    "select " + " and ".join(f"to_regclass('public.{t}') is null" for t in TABLAS_NUEVAS) + ","
    # 2. 34 aplicada (con la 31, la 32 y la 33): guardias nuevas presentes y guardias_farmacia retirada.
    "to_regclass('public.guardias_semana') is not null and to_regclass('public.guardias_festivo') is not null "
    "  and to_regclass('public.guardias_farmacia') is null "
    "  and to_regclass('public.trabajadoras_ajustes_anuales') is not null "
    "  and to_regclass('public.cf_noches_automaticas') is not null,"
    # 3. Roles presentes: cf_lectura (29) y la web de Trabajadores (31).
    f"exists (select 1 from pg_roles where rolname = '{LECTURA_GENERAL}') "
    f"  and exists (select 1 from pg_roles where rolname = '{ROL_TRABAJADORES}'),"
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

# Datos y estructura que la 35 no puede tocar: conteos, huellas de facturas, vencimientos y configuracion, y los
# triggers, restricciones y politicas de facturas y vencimientos (D7: sin claves externas hacia ellas).
DATOS = ("select array[(select count(*) from public.documentos_facturas), "
         "(select count(*) from public.facturas), "
         "(select count(*) from public.facturas_vencimientos), "
         "(select count(*) from public.normalizacion_ejecuciones), "
         "(select count(*) from public.historial_facturas), "
         "(select count(*) from public.conciliaciones), "
         "(select count(*) from public.conciliacion_detalles), "
         "(select count(*) from public.conciliacion_albaranes_reservados), "
         "(select count(*) from public.albaranes), "
         "(select count(*) from public.trabajadoras), "
         "(select count(*) from public.trabajadores_historial)], "
         "(select md5(coalesce(string_agg(md5(to_jsonb(f)::text), '' order by f.id), '')) from public.facturas f), "
         "(select md5(coalesce(string_agg(md5(to_jsonb(v)::text), '' order by v.id), '')) "
         " from public.facturas_vencimientos v), "
         "(select md5(to_jsonb(c)::text) from public.cf_configuracion c where c.id), "
         "(select md5(coalesce(string_agg(x, ',' order by x), '')) from ("
         " select 'trigger:' || tgrelid::regclass || ':' || tgname as x from pg_trigger "
         f"  where tgrelid = any({_regclases(TABLAS_FACTURAS)}) "
         " union all select 'restriccion:' || conrelid::regclass || ':' || conname || ':' "
         "  || pg_get_constraintdef(oid) from pg_constraint "
         f"  where conrelid = any({_regclases(TABLAS_FACTURAS)}) "
         f"  or confrelid = any({_regclases(TABLAS_FACTURAS)}) "
         " union all select 'politica:' || polrelid::regclass || ':' || polname from pg_policy "
         f"  where polrelid = any({_regclases(TABLAS_FACTURAS)})) e)")

# ACL de las tablas nuevas: solo el propietario (quien despliega), el rol de la web y cf_lectura. Cualquier otro
# beneficiario (anon, authenticated, el rol del sistema o PUBLIC) -> falla. La secuencia del historial: solo el
# propietario.
ACL_AJENA = (
    "select count(*) from pg_class c cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a "
    f"where c.relnamespace = 'public'::regnamespace and c.relname = any({_lista(TABLAS_NUEVAS)}) "
    "  and a.grantee <> c.relowner "
    f"  and (a.grantee = 0 or pg_get_userbyid(a.grantee) <> all(array['{ROL}', '{LECTURA_GENERAL}']))")
ACL_SECUENCIA_AJENA = (
    "select count(*) from pg_class c cross join lateral aclexplode(coalesce(c.relacl, acldefault('s', c.relowner))) a "
    f"where c.relnamespace = 'public'::regnamespace and c.relname = '{SECUENCIA_NUEVA}' and a.grantee <> c.relowner")

# Funciones nuevas de la 35: solo el propietario puede ejecutarlas (las usan los triggers), salvo la de la RLS, que
# ejecuta tambien la web.
ACL_FUNCIONES_AJENA = (
    "select count(*) from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
    f"where p.pronamespace = 'public'::regnamespace and p.proname = any({_lista(FUNCIONES_NUEVAS)}) "
    f"  and a.grantee <> p.proowner and not (p.proname = '{FUNCION_RLS}' and a.grantee <> 0 "
    f"  and pg_get_userbyid(a.grantee) = '{ROL}' and a.privilege_type = 'EXECUTE')")

PRIVILEGIOS_WEB = (
    " and ".join(f"has_table_privilege('{ROL}', 'public.{t}', 'SELECT,INSERT,UPDATE')" for t in ESCRITURA)
    + " and " + " and ".join(f"has_table_privilege('{ROL}', 'public.{t}', 'SELECT')" for t in SOLO_LECTURA)
    + f" and has_function_privilege('{ROL}', 'public.{FUNCION_RLS}(text)', 'EXECUTE')"
    # Nada mas: ni DELETE/TRUNCATE, ni escritura en el historial, ni lectura de facturas, vencimientos, conciliacion o
    # configuracion; ni secuencias; ni otra funcion privilegiada o que escriba.
    + f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace "
    f"  and c.relkind in ('r','p','v','m','f') and (has_table_privilege('{ROL}', c.oid, "
    f"  'DELETE,TRUNCATE,REFERENCES,TRIGGER') "
    f"  or (has_table_privilege('{ROL}', c.oid, 'INSERT,UPDATE') and c.relname <> all({_lista(ESCRITURA)})) "
    f"  or (has_table_privilege('{ROL}', c.oid, 'SELECT') and c.relname <> all({_lista(OBJETOS)}))))"
    f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind = 'S' "
    f"  and case when c.relkind = 'S' then has_sequence_privilege('{ROL}', c.oid, 'USAGE,SELECT,UPDATE') end)"
    f" and not exists (select 1 from pg_proc p where p.pronamespace = 'public'::regnamespace "
    f"  and has_function_privilege('{ROL}', p.oid, 'EXECUTE') and p.prorettype <> 'event_trigger'::regtype "
    f"  and (p.prosecdef or (p.provolatile = 'v' and p.prorettype <> 'trigger'::regtype)) "
    f"  and p.proname <> '{FUNCION_RLS}')"
    + "".join(f" and not coalesce(has_schema_privilege('{ROL}', to_regnamespace('{e}'), 'USAGE'), false)"
              for e in ESQUEMAS_VEDADOS))

# cf_lectura (D4): lee las tablas nuevas; sigue sin escritura en public y sin funciones privilegiadas (2BN).
LECTURA = (
    " and ".join(f"has_table_privilege('{LECTURA_GENERAL}', 'public.{t}', 'SELECT')" for t in TABLAS_NUEVAS)
    + f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace "
    f"  and c.relkind in ('r','p','v','m','f') "
    f"  and has_table_privilege('{LECTURA_GENERAL}', c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE'))"
    f" and not exists (select 1 from pg_proc p where p.pronamespace = 'public'::regnamespace "
    f"  and has_function_privilege('{LECTURA_GENERAL}', p.oid, 'EXECUTE') "
    f"  and p.prorettype <> 'event_trigger'::regtype "
    f"  and (p.prosecdef or (p.provolatile = 'v' and p.prorettype <> 'trigger'::regtype)))")

# Rol de la web con los atributos de cf_trabajadores_web (DISENO §2.5, D5). La contrasena no se comprueba ni se lee.
ATRIBUTOS_ROL = (
    "(select rolcanlogin and not rolsuper and not rolcreatedb and not rolcreaterole and not rolinherit "
    "   and not rolreplication and not rolbypassrls and rolconnlimit = 5 "
    "   and rolconfig @> array['statement_timeout=60s', 'idle_in_transaction_session_timeout=60s'] "
    f" from pg_roles where rolname = '{ROL}')")

POLITICAS_ESPERADAS = {"vencimientos_marcas_pago": 4, "proveedores_forma_pago": 4, "pagos_historial": 2}
_POLITICAS = " and ".join(
    f"(select count(*) from pg_policy where polrelid = 'public.{t}'::regclass) = {n} "
    f"and (select relrowsecurity from pg_class where oid = 'public.{t}'::regclass)"
    for t, n in POLITICAS_ESPERADAS.items())

POSTCONDICIONES = (
    f"{DATOS},"
    # Privilegios de la web y atributos del rol.
    f"{PRIVILEGIOS_WEB} and {ATRIBUTOS_ROL},"
    # cf_lectura lee y no escribe; nadie mas tiene privilegios sobre las tablas, la secuencia ni las funciones.
    f"{LECTURA} and ({ACL_AJENA}) = 0 and ({ACL_SECUENCIA_AJENA}) = 0 and ({ACL_FUNCIONES_AJENA}) = 0 "
    f"  and (select count(*) from pg_proc where pronamespace = 'public'::regnamespace "
    f"       and proname = any({_lista(FUNCIONES_NUEVAS)})) = {len(FUNCIONES_NUEVAS)},"
    # RLS con sus politicas; unicidades parciales; sin claves externas en las tablas nuevas (D7); permiso global y del
    # modulo de Trabajadores intactos.
    f"{_POLITICAS} "
    "  and (select indisunique and indpred is not null from pg_index "
    "       where indexrelid = 'public.vencimientos_marcas_pago_vigente'::regclass) "
    "  and (select indisunique and indpred is not null from pg_index "
    "       where indexrelid = 'public.proveedores_forma_pago_vigente'::regclass) "
    "  and not exists (select 1 from pg_constraint where contype = 'f' "
    f"       and conrelid = any({_regclases(TABLAS_NUEVAS)})) "
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
        raise SystemExit("MIGRACION_35_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_35_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_h6_deploy_35")
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
            fila = cur.fetchone()
            datos, (privilegios, lectura, estructura, propietario) = fila[:5], fila[5:]
            registro["postcondiciones"] = {
                "datos_sin_cambios": [list(datos[0]), *datos[1:]] == datos_antes,
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
