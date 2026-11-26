"""Hito H7b: despliega EXCLUSIVAMENTE la migracion 40 (prevision de Cashflow: conceptos, recurrentes y apuntes de la
web, historial, funcion de ocurrencias y rol cf_cashflow_web), una vez, en una transaccion.

NO se ejecuta en el hito H7b (solo se ensaya en local, con el rol que imita al postgres de Supabase). Requiere
confirmacion expresa de Pio en chat (hito 40-D) y los flags apagados por Pio durante la ventana. No invoca RPC.
Normaliza el SQL a LF y exige que coincida byte a byte con la version del commit indicado (git show <commit>:...), y la
entrada de linea de ordenes exige ademas ese commit ya subido al main del remoto. Revalida precondiciones dentro de la
misma transaccion. Error -> rollback y parada; nunca reintenta. Patron de pruebas/auditoria_h6/desplegar_35.py y
pruebas/auditoria_h7/desplegar_38.py. No comprueba ni lee la contrasena de cf_cashflow_web: la fija Pio despues,
fuera del repositorio, con SCRAM (DISENO §4).

La migracion nombra el rol del sistema (autorizacion de Pio, solo en la 40 y su rollback); este script no: comprueba
que ninguna tabla, secuencia ni funcion nueva tiene otro beneficiario que su propietario, cf_cashflow_web y
cf_lectura, en los privilegios previstos.

Uso: python pruebas/auditoria_h7b/desplegar_40.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/40_cf_cashflow_prevision.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
ROL = "cf_cashflow_web"
LECTURA_GENERAL = "cf_lectura"
# La web escribe en tres tablas y lee su historial (DISENO §4).
ESCRITURA = ("cf_cashflow_conceptos", "cf_cashflow_recurrentes", "cf_cashflow_apuntes")
SOLO_LECTURA = ("cf_cashflow_apuntes_historial",)
TABLAS_NUEVAS = ESCRITURA + SOLO_LECTURA
SECUENCIA_NUEVA = "cf_cashflow_apuntes_historial_id_seq"
# UPDATE de la web: solo las columnas de anulacion y, en apuntes, de sustitucion.
COLUMNAS_UPDATE = {
    "cf_cashflow_conceptos": ("anulado", "motivo_anulacion"),
    "cf_cashflow_recurrentes": ("anulado", "motivo_anulacion"),
    "cf_cashflow_apuntes": ("anulado", "motivo_anulacion", "sustituido_factura_id", "sustituido_vencimiento_orden"),
}
# Funciones de lectura (las ejecutan la web y cf_lectura) y la de la RLS de la web (solo la web).
FUNCIONES_LECTURA = ("cf_cashflow_fechas_recurrente", "cf_cashflow_ocurrencias")
FUNCION_RLS = "cf_cashflow_farmacia_habilitada"
FUNCIONES_NUEVAS = FUNCIONES_LECTURA + (
    FUNCION_RLS, "cf_cashflow_autor", "cf_cashflow_ultimo_saldo_banco", "cf_cashflow_validar_celda",
    "cf_cashflow_referencia_futura", "cf_cashflow_validar_sustitucion", "cf_cashflow_alta_concepto",
    "cf_cashflow_alta_recurrente", "cf_cashflow_alta_apunte", "cf_cashflow_solo_anular",
    "cf_cashflow_prevision_historial", "cf_cashflow_historial_solo_insercion")
# Tablas importadas de la 38: solo insercion, la 40 no las toca.
TABLAS_IMPORTADAS = ("cf_cashflow_cuentas", "cf_cashflow_importaciones", "cf_cashflow_importes", "cf_cashflow_saldos")
TABLAS_PAGOS = ("vencimientos_marcas_pago", "proveedores_forma_pago", "pagos_historial")
TABLAS_TRABAJADORES = ("trabajadoras", "eventos_calendario", "festivos", "trabajadores_historial")
ESQUEMAS_VEDADOS = ("auth", "storage", "vault", "pgsodium", "pgsodium_masks", "supabase_functions", "net", "cron",
                    "realtime", "graphql")
POLITICAS_ESPERADAS = {"cf_cashflow_conceptos": 4, "cf_cashflow_recurrentes": 4, "cf_cashflow_apuntes": 4,
                       "cf_cashflow_apuntes_historial": 2}
# Triggers no internos: alta, solo_anular, sin_truncate e historial en cada tabla de escritura; dos en el historial.
TRIGGERS_ESPERADOS = 4 * len(ESCRITURA) + 2
INDICES_UNICOS_PARCIALES = ("cf_cashflow_conceptos_vigente", "cf_cashflow_conceptos_cif",
                            "cf_cashflow_apuntes_ocurrencia", "cf_cashflow_apuntes_sustituto")


def _lista(nombres) -> str:
    return "array[" + ", ".join(f"'{n}'" for n in nombres) + "]"


def _regclases(nombres) -> str:
    return "array[" + ", ".join(f"'public.{n}'::regclass" for n in nombres) + "]"


def _huella(tabla: str) -> str:
    return (f"(select md5(coalesce(string_agg(md5(to_jsonb(t)::text), '' order by to_jsonb(t)::text), '')) "
            f" from public.{tabla} t)")


PRECONDICIONES = (
    # 1. 40 no aplicada: ninguna tabla nueva. (El rol es del cluster: si ya existiera, la postcondicion de sus
    #    atributos decide.)
    "select " + " and ".join(f"to_regclass('public.{t}') is null" for t in TABLAS_NUEVAS) + ","
    # 2. 39 aplicada (con la 38): marca conciliacion_r21 y tablas importadas presentes; CASHFLOW = {PIO, RITA}.
    "exists (select 1 from information_schema.columns where table_schema = 'public' "
    "  and table_name = 'cf_configuracion' and column_name = 'conciliacion_r21') and "
    + " and ".join(f"to_regclass('public.{t}') is not null" for t in TABLAS_IMPORTADAS)
    + " and (select farmacias = array['PIO', 'RITA']::text[] from public.cf_modulos_farmacias "
    "       where modulo = 'CASHFLOW'),"
    # 3. cf_lectura presente (29).
    f"exists (select 1 from pg_roles where rolname = '{LECTURA_GENERAL}'),"
    # 4. 19: privilegios minimos.
    "not has_table_privilege('anon', 'public.facturas', 'SELECT') "
    "  and not has_table_privilege('authenticated', 'public.albaranes', 'UPDATE'),"
    # 5. Flags apagados y solo PIO.
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

# Lo que la 40 no puede tocar: conteos, huellas de facturas, vencimientos, configuracion, permisos por modulo, las
# tablas importadas de Cashflow, Trabajadores y Pagos.
DATOS = ("select array[(select count(*) from public.documentos_facturas), "
         "(select count(*) from public.facturas), "
         "(select count(*) from public.facturas_vencimientos), "
         "(select count(*) from public.conciliaciones), "
         "(select count(*) from public.conciliacion_detalles), "
         "(select count(*) from public.albaranes)], "
         + ", ".join(_huella(t) for t in ("facturas", "facturas_vencimientos"))
         + ", (select md5(to_jsonb(c)::text) from public.cf_configuracion c where c.id), "
         + _huella("cf_modulos_farmacias") + ", "
         + ", ".join(_huella(t) for t in TABLAS_IMPORTADAS + TABLAS_TRABAJADORES + TABLAS_PAGOS))
N_DATOS = 4 + len(TABLAS_IMPORTADAS) + len(TABLAS_TRABAJADORES) + len(TABLAS_PAGOS) + 1

# ACL de las tablas nuevas: solo el propietario (quien despliega), el rol de la web y cf_lectura. Cualquier otro
# beneficiario (anon, authenticated, el rol del sistema o PUBLIC) -> falla. La secuencia: solo el propietario.
ACL_AJENA = (
    "select count(*) from pg_class c cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a "
    f"where c.relnamespace = 'public'::regnamespace and c.relname = any({_lista(TABLAS_NUEVAS)}) "
    "  and a.grantee <> c.relowner "
    f"  and (a.grantee = 0 or pg_get_userbyid(a.grantee) <> all(array['{ROL}', '{LECTURA_GENERAL}']))")
# Privilegios de columna: solo UPDATE de la web en las columnas previstas.
ACL_COLUMNAS_AJENA = (
    "select count(*) from pg_attribute t join pg_class c on c.oid = t.attrelid "
    "cross join lateral aclexplode(t.attacl) a "
    f"where t.attrelid = any({_regclases(TABLAS_NUEVAS)}) and t.attacl is not null "
    f"  and not (a.grantee <> 0 and pg_get_userbyid(a.grantee) = '{ROL}' and a.privilege_type = 'UPDATE' "
    "  and (c.relname::text, t.attname::text) in ("
    + ", ".join(f"('{t}', '{c}')" for t, cs in COLUMNAS_UPDATE.items() for c in cs) + "))")
ACL_SECUENCIA_AJENA = (
    "select count(*) from pg_class c cross join lateral aclexplode(coalesce(c.relacl, acldefault('s', c.relowner))) a "
    f"where c.relnamespace = 'public'::regnamespace and c.relname = '{SECUENCIA_NUEVA}' and a.grantee <> c.relowner")
# Funciones nuevas: solo el propietario, salvo EXECUTE de las de lectura (web y cf_lectura) y de la RLS (web).
ACL_FUNCIONES_AJENA = (
    "select count(*) from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
    f"where p.pronamespace = 'public'::regnamespace and p.proname = any({_lista(FUNCIONES_NUEVAS)}) "
    "  and a.grantee <> p.proowner and not (a.grantee <> 0 and a.privilege_type = 'EXECUTE' and ("
    f"   (p.proname = any({_lista(FUNCIONES_LECTURA)}) "
    f"    and pg_get_userbyid(a.grantee) = any(array['{ROL}', '{LECTURA_GENERAL}'])) "
    f"   or (p.proname = '{FUNCION_RLS}' and pg_get_userbyid(a.grantee) = '{ROL}')))")

PRIVILEGIOS_WEB = (
    " and ".join(f"has_table_privilege('{ROL}', 'public.{t}', 'SELECT,INSERT')" for t in ESCRITURA)
    + " and " + " and ".join(f"has_table_privilege('{ROL}', 'public.{t}', 'SELECT')" for t in SOLO_LECTURA)
    + " and " + " and ".join(f"has_column_privilege('{ROL}', 'public.{t}', '{c}', 'UPDATE')"
                             for t, cs in COLUMNAS_UPDATE.items() for c in cs)
    + " and " + " and ".join(f"(select bool_and(has_function_privilege('{ROL}', oid, 'EXECUTE')) from pg_proc "
                             f" where pronamespace = 'public'::regnamespace and proname = '{f}')"
                             for f in FUNCIONES_LECTURA + (FUNCION_RLS,))
    # Nada mas: ni DELETE/TRUNCATE, ni UPDATE de tabla entera ni de otras columnas, ni escritura en el historial, ni
    # lectura de las tablas importadas, facturas, vencimientos, conciliacion o configuracion; ni secuencias; ni otra
    # funcion privilegiada o que escriba; ni esquemas vedados.
    + f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace "
    f"  and c.relkind in ('r','p','v','m','f') and (has_table_privilege('{ROL}', c.oid, "
    f"  'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') "
    f"  or (has_table_privilege('{ROL}', c.oid, 'INSERT') and c.relname <> all({_lista(ESCRITURA)})) "
    f"  or (has_any_column_privilege('{ROL}', c.oid, 'UPDATE') and c.relname <> all({_lista(ESCRITURA)})) "
    f"  or (has_any_column_privilege('{ROL}', c.oid, 'SELECT') and c.relname <> all({_lista(TABLAS_NUEVAS)}))))"
    f" and not exists (select 1 from pg_attribute t join pg_class c on c.oid = t.attrelid "
    f"  where t.attrelid = any({_regclases(ESCRITURA)}) and t.attnum > 0 and not t.attisdropped "
    f"  and has_column_privilege('{ROL}', t.attrelid, t.attnum, 'UPDATE') "
    "  and (c.relname::text, t.attname::text) not in ("
    + ", ".join(f"('{t}', '{c}')" for t, cs in COLUMNAS_UPDATE.items() for c in cs) + "))"
    + f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind = 'S' "
    f"  and case when c.relkind = 'S' then has_sequence_privilege('{ROL}', c.oid, 'USAGE,SELECT,UPDATE') end)"
    f" and not exists (select 1 from pg_proc p where p.pronamespace = 'public'::regnamespace "
    f"  and has_function_privilege('{ROL}', p.oid, 'EXECUTE') and p.prorettype <> 'event_trigger'::regtype "
    f"  and (p.prosecdef or (p.provolatile = 'v' and p.prorettype <> 'trigger'::regtype)) "
    f"  and p.proname <> '{FUNCION_RLS}')"
    + "".join(f" and not coalesce(has_schema_privilege('{ROL}', to_regnamespace('{e}'), 'USAGE'), false)"
              for e in ESQUEMAS_VEDADOS))

# cf_lectura: lee las tablas nuevas y ejecuta las de lectura; sigue sin escritura en public y sin funciones
# privilegiadas (2BN).
LECTURA = (
    " and ".join(f"has_table_privilege('{LECTURA_GENERAL}', 'public.{t}', 'SELECT')" for t in TABLAS_NUEVAS)
    + f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace "
    f"  and c.relkind in ('r','p','v','m','f') "
    f"  and has_table_privilege('{LECTURA_GENERAL}', c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE'))"
    f" and not exists (select 1 from pg_proc p where p.pronamespace = 'public'::regnamespace "
    f"  and has_function_privilege('{LECTURA_GENERAL}', p.oid, 'EXECUTE') "
    f"  and p.prorettype <> 'event_trigger'::regtype "
    f"  and (p.prosecdef or (p.provolatile = 'v' and p.prorettype <> 'trigger'::regtype)))")

# Rol de la web con los atributos de cf_pagos_web. La contrasena no se comprueba ni se lee.
ATRIBUTOS_ROL = (
    "(select rolcanlogin and not rolsuper and not rolcreatedb and not rolcreaterole and not rolinherit "
    "   and not rolreplication and not rolbypassrls and rolconnlimit = 5 "
    "   and rolconfig @> array['statement_timeout=60s', 'idle_in_transaction_session_timeout=60s'] "
    "   and not exists (select 1 from pg_auth_members m where m.member = r.oid) "
    f" from pg_roles r where rolname = '{ROL}')")

_POLITICAS = " and ".join(
    f"(select count(*) from pg_policy where polrelid = 'public.{t}'::regclass) = {n} "
    f"and (select relrowsecurity from pg_class where oid = 'public.{t}'::regclass)"
    for t, n in POLITICAS_ESPERADAS.items())

ESTRUCTURA = (
    f"{_POLITICAS} "
    + "".join(f" and (select indisunique and indpred is not null from pg_index "
              f"      where indexrelid = 'public.{i}'::regclass)" for i in INDICES_UNICOS_PARCIALES)
    + " and (select count(*) from pg_trigger where not tgisinternal "
    f"       and tgrelid = any({_regclases(TABLAS_NUEVAS)})) = {TRIGGERS_ESPERADOS} "
    + "".join(f" and (select count(*) from public.{t}) = 0" for t in TABLAS_NUEVAS)
    + " and (select farmacias = array['PIO', 'RITA']::text[] from public.cf_modulos_farmacias "
    "       where modulo = 'CASHFLOW') "
    "  and (select farmacias_habilitadas = array['PIO']::text[] from public.cf_configuracion where id) "
    f"  and (select count(*) from pg_proc where pronamespace = 'public'::regnamespace "
    f"       and proname = any({_lista(FUNCIONES_NUEVAS)})) = {len(FUNCIONES_NUEVAS)} "
    # Ninguna funcion de lectura es security definer ni volatil (2BN).
    f"  and not exists (select 1 from pg_proc where pronamespace = 'public'::regnamespace "
    f"       and proname = any({_lista(FUNCIONES_LECTURA)}) and (prosecdef or provolatile = 'v'))")

POSTCONDICIONES = (
    f"{DATOS},"
    # Privilegios de la web y atributos del rol.
    f"{PRIVILEGIOS_WEB} and {ATRIBUTOS_ROL},"
    # cf_lectura lee y no escribe; nadie mas tiene privilegios sobre las tablas, columnas, secuencia ni funciones.
    f"{LECTURA} and ({ACL_AJENA}) = 0 and ({ACL_COLUMNAS_AJENA}) = 0 and ({ACL_SECUENCIA_AJENA}) = 0 "
    f"  and ({ACL_FUNCIONES_AJENA}) = 0,"
    # RLS, indices, triggers, tablas vacias, permisos por modulo y global intactos.
    f"{ESTRUCTURA},"
    # Propietario de las tablas nuevas: quien despliega (postgres en Supabase).
    "(select bool_and(pg_get_userbyid(relowner) = current_user) from pg_class "
    f" where relnamespace = 'public'::regnamespace and relname = any({_lista(TABLAS_NUEVAS)}))")


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_40_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_40_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_h7b_deploy_40")
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
            datos, (privilegios, lectura, estructura, propietario) = fila[:N_DATOS], fila[N_DATOS:]
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
    ls-remote; modulo comun ``puerta_git``). ``main`` sigue siendo ensayable sin remoto."""
    if len(argv) != 3:
        raise SystemExit(__doc__)
    sys.path.insert(0, str(ROOT))
    from src.facturas.runtime_supabase.puerta_git import exigir_commit_en_origen
    exigir_commit_en_origen(argv[0], ROOT)
    main(argv[0], argv[1], Path(argv[2]))


if __name__ == "__main__":
    cli(sys.argv[1:])
