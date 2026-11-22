"""Hito H7: despliega EXCLUSIVAMENTE la migracion 38 (Cashflow: cuentas, importaciones, importes y saldos del Excel de
cashflow, RPC de importacion y permiso de modulo CASHFLOW), una vez, en una transaccion.

NO se ejecuta en el hito H7 (solo se ensaya en local, con el rol que imita al postgres de Supabase). Requiere
confirmacion expresa de Pio en chat (hito H7-D) y los flags apagados por Pio durante la ventana. No invoca RPC.
Normaliza el SQL a LF y exige que coincida byte a byte con la version del commit indicado (git show <commit>:...), y la
entrada de linea de ordenes exige ademas ese commit ya subido al main del remoto. Revalida precondiciones dentro de la
misma transaccion. Error -> rollback y parada; nunca reintenta. Patron de pruebas/auditoria_h6/desplegar_35.py y
pruebas/auditoria_37/desplegar_37.py.

La migracion nombra el rol del sistema (autorizacion C3 de Pio, solo en la 38 y su rollback); este script no: comprueba
que la RPC nueva tiene exactamente los mismos beneficiarios de EXECUTE que la firma de 8 parametros de
cf_registrar_fallo_normalizacion (la 37) y que ninguna tabla, secuencia ni funcion auxiliar nueva tiene otro
beneficiario que su propietario y, en las tablas, cf_lectura.

Uso: python pruebas/auditoria_h7/desplegar_38.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/38_cf_cashflow.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
LECTURA_GENERAL = "cf_lectura"
TABLAS_NUEVAS = ("cf_cashflow_cuentas", "cf_cashflow_importaciones", "cf_cashflow_importes", "cf_cashflow_saldos")
SECUENCIAS_NUEVAS = ("cf_cashflow_importes_id_seq", "cf_cashflow_saldos_id_seq")
RPC = "public.cf_cashflow_registrar_importacion(jsonb,jsonb,jsonb)"
FUNCION_TRIGGER = "public.cf_cashflow_solo_insercion()"
# Referencia de beneficiarios: la firma de 8 parametros de la 37 (EXECUTE solo para el rol del sistema).
FIRMA_FALLO_8 = "public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text,jsonb)"
# Tablas de Pagos (35) y Trabajadores (31-34) que la 38 no toca.
TABLAS_PAGOS = ("vencimientos_marcas_pago", "proveedores_forma_pago", "pagos_historial")
TABLAS_TRABAJADORES = ("trabajadoras", "eventos_calendario", "festivos", "trabajadores_historial")
POLITICAS_ESPERADAS = {t: 1 for t in TABLAS_NUEVAS}
# La hoja de PIO lleva tilde (U+00CD): se compone con chr para que el fuente sea ASCII.
CUENTAS_ESPERADAS = "PIO:PIO:P" + chr(0xCD) + "O,RITA:RITA:RITA,SL:-:SL"


def _lista(nombres) -> str:
    return "array[" + ", ".join(f"'{n}'" for n in nombres) + "]"


def _regclases(nombres) -> str:
    return "array[" + ", ".join(f"'public.{n}'::regclass" for n in nombres) + "]"


def _beneficiarios(firma: str) -> str:
    """Roles (distintos del propietario) con EXECUTE sobre la funcion, ordenados; sin nombrarlos."""
    return (f"(select coalesce(string_agg(a.grantee::regrole::text, ',' order by a.grantee::regrole::text), '') "
            f" from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
            f" where p.oid = '{firma}'::regprocedure and a.grantee <> p.proowner and a.grantee <> 0 "
            f" and a.privilege_type = 'EXECUTE')")


def _huella(tabla: str) -> str:
    return (f"(select md5(coalesce(string_agg(md5(to_jsonb(t)::text), '' order by to_jsonb(t)::text), '')) "
            f" from public.{tabla} t)")


PRECONDICIONES = (
    # 1. 38 no aplicada: ninguna tabla nueva, ninguna RPC nueva y sin fila CASHFLOW.
    "select " + " and ".join(f"to_regclass('public.{t}') is null" for t in TABLAS_NUEVAS)
    + f" and to_regprocedure('{RPC}') is null "
    "  and not exists (select 1 from public.cf_modulos_farmacias where modulo = 'CASHFLOW'),"
    # 2. 37 aplicada (firma de 8 parametros) y 31 con TRABAJADORES = {PIO, RITA}; cf_lectura presente (29).
    f"to_regprocedure('{FIRMA_FALLO_8}') is not null "
    "  and (select farmacias = array['PIO', 'RITA']::text[] from public.cf_modulos_farmacias "
    "       where modulo = 'TRABAJADORES') "
    f"  and exists (select 1 from pg_roles where rolname = '{LECTURA_GENERAL}'),"
    # 3. 19: privilegios minimos.
    "not has_table_privilege('anon', 'public.facturas', 'SELECT') "
    "  and not has_table_privilege('authenticated', 'public.albaranes', 'UPDATE'),"
    # 4. Flags apagados y solo PIO.
    "(select normalizacion_automatica=false and conciliacion_automatica=false and luna_habilitada=false "
    "  and farmacias_habilitadas=array['PIO']::text[] from public.cf_configuracion where id),"
    # 5. Sin claims de conciliacion ni de normalizacion.
    "(select count(*)=0 from public.facturas where conciliacion_bloqueado_por is not null "
    "  or conciliacion_bloqueado_hasta>now()) and "
    "(select count(*)=0 from public.documentos_facturas where bloqueado_por is not null "
    "  or bloqueado_hasta>now() or estado_lectura='NORMALIZANDO'),"
    # 6. 2AX: ningun objeto de public con propietario distinto de postgres.
    "(select count(*)=0 from pg_class c where c.relnamespace='public'::regnamespace "
    "  and c.relkind in ('r','p','v','m','S','f') and pg_get_userbyid(c.relowner)<>'postgres') and "
    "(select count(*)=0 from pg_proc p where p.pronamespace='public'::regnamespace "
    "  and pg_get_userbyid(p.proowner)<>'postgres' "
    "  and not exists(select 1 from pg_depend d where d.objid=p.oid and d.deptype='e'))")

# Lo que la 38 no puede tocar: conteos y huellas de documentos, facturas, conciliaciones, historial y albaranes; la
# configuracion; la fila TRABAJADORES; Trabajadores y Pagos; la ACL de la firma de referencia de la 37.
DATOS = ("select array[(select count(*) from public.documentos_facturas), "
         "(select count(*) from public.facturas), "
         "(select count(*) from public.normalizacion_ejecuciones), "
         "(select count(*) from public.historial_facturas), "
         "(select count(*) from public.conciliaciones), "
         "(select count(*) from public.conciliacion_detalles), "
         "(select count(*) from public.albaranes)], "
         + ", ".join(_huella(t) for t in ("documentos_facturas", "facturas", "conciliaciones", "historial_facturas"))
         + ", (select md5(to_jsonb(c)::text) from public.cf_configuracion c where c.id), "
         "(select md5(to_jsonb(m)::text) from public.cf_modulos_farmacias m where m.modulo = 'TRABAJADORES'), "
         + ", ".join(_huella(t) for t in TABLAS_TRABAJADORES + TABLAS_PAGOS)
         + f", (select coalesce(proacl::text, '') || pg_get_userbyid(proowner) || prosecdef::text from pg_proc "
         f"  where oid = '{FIRMA_FALLO_8}'::regprocedure)")

_POLITICAS = " and ".join(
    f"(select count(*) from pg_policy where polrelid = 'public.{t}'::regclass) = {n} "
    f"and (select relrowsecurity from pg_class where oid = 'public.{t}'::regclass)"
    for t, n in POLITICAS_ESPERADAS.items())

# Estructura: RLS y politicas; cuentas fijas; ninguna importacion; unicos (vigente parcial y hash); 8 triggers de solo
# insercion; permiso CASHFLOW = {PIO, RITA} y global solo PIO.
ESTRUCTURA = (
    f"{_POLITICAS} "
    "  and (select string_agg(codigo || ':' || coalesce(farmacia, '-') || ':' || hoja, ',' order by codigo) "
    f"       from public.cf_cashflow_cuentas) = '{CUENTAS_ESPERADAS}' "
    "  and (select count(*) from public.cf_cashflow_importaciones) = 0 "
    "  and (select count(*) from public.cf_cashflow_importes) = 0 "
    "  and (select count(*) from public.cf_cashflow_saldos) = 0 "
    "  and (select indisunique and indpred is not null from pg_index "
    "       where indexrelid = 'public.cf_cashflow_importaciones_vigente'::regclass) "
    "  and (select indisunique and indpred is null from pg_index "
    "       where indexrelid = 'public.cf_cashflow_importaciones_hash'::regclass) "
    "  and (select count(*) from pg_trigger where not tgisinternal "
    f"       and tgrelid = any({_regclases(TABLAS_NUEVAS)}) "
    f"       and tgfoid = '{FUNCION_TRIGGER}'::regprocedure) = 8 "
    "  and (select farmacias = array['PIO', 'RITA']::text[] from public.cf_modulos_farmacias "
    "       where modulo = 'CASHFLOW') "
    "  and (select pg_get_constraintdef(oid) like '%CASHFLOW%' from pg_constraint "
    "       where conrelid = 'public.cf_modulos_farmacias'::regclass "
    "       and conname = 'cf_modulos_farmacias_modulo_check') "
    "  and (select farmacias_habilitadas = array['PIO']::text[] from public.cf_configuracion where id)")

# Privilegios: cf_lectura lee las cuatro tablas y sigue sin escribir ni ejecutar funciones privilegiadas (2BN); en las
# tablas nuevas, nadie mas que el propietario y cf_lectura; secuencias y funcion del trigger, solo el propietario.
ACL_TABLAS_AJENA = (
    "select count(*) from pg_class c cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a "
    f"where c.relnamespace = 'public'::regnamespace and c.relname = any({_lista(TABLAS_NUEVAS)}) "
    "  and a.grantee <> c.relowner "
    f"  and (a.grantee = 0 or pg_get_userbyid(a.grantee) <> '{LECTURA_GENERAL}' or a.privilege_type <> 'SELECT')")
ACL_SECUENCIAS_AJENA = (
    "select count(*) from pg_class c cross join lateral aclexplode(coalesce(c.relacl, acldefault('s', c.relowner))) a "
    f"where c.relnamespace = 'public'::regnamespace and c.relname = any({_lista(SECUENCIAS_NUEVAS)}) "
    "  and a.grantee <> c.relowner")
ACL_TRIGGER_AJENA = (
    "select count(*) from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
    f"where p.oid = '{FUNCION_TRIGGER}'::regprocedure and a.grantee <> p.proowner")
LECTURA = (
    " and ".join(f"has_table_privilege('{LECTURA_GENERAL}', 'public.{t}', 'SELECT')" for t in TABLAS_NUEVAS)
    + f" and not exists (select 1 from pg_class c where c.relnamespace = 'public'::regnamespace "
    f"  and c.relkind in ('r','p','v','m','f') "
    f"  and has_table_privilege('{LECTURA_GENERAL}', c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE'))"
    f" and not exists (select 1 from pg_proc p where p.pronamespace = 'public'::regnamespace "
    f"  and has_function_privilege('{LECTURA_GENERAL}', p.oid, 'EXECUTE') "
    f"  and p.prorettype <> 'event_trigger'::regtype "
    f"  and (p.prosecdef or (p.provolatile = 'v' and p.prorettype <> 'trigger'::regtype)))")
PRIVILEGIOS = (f"{LECTURA} and ({ACL_TABLAS_AJENA}) = 0 and ({ACL_SECUENCIAS_AJENA}) = 0 "
               f"and ({ACL_TRIGGER_AJENA}) = 0")

# RPC: security definer con search_path fijo, propietario quien despliega (postgres en Supabase), los mismos
# beneficiarios de EXECUTE que la firma de referencia de la 37 (al menos uno) y nada para anon, authenticated ni PUBLIC.
RPC_PRIVILEGIOS = (
    f"(select prosecdef and pg_get_userbyid(proowner) = current_user "
    f"   and proconfig @> array['search_path=public, pg_temp'] "
    f"  from pg_proc where oid = '{RPC}'::regprocedure) "
    f"  and {_beneficiarios(RPC)} = {_beneficiarios(FIRMA_FALLO_8)} and {_beneficiarios(RPC)} <> '' "
    f"  and not has_function_privilege('anon', '{RPC}', 'EXECUTE') "
    f"  and not has_function_privilege('authenticated', '{RPC}', 'EXECUTE') "
    f"  and not has_function_privilege('{LECTURA_GENERAL}', '{RPC}', 'EXECUTE') "
    f"  and not exists (select 1 from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, "
    f"       acldefault('f', p.proowner))) a where p.oid = '{RPC}'::regprocedure and a.grantee = 0)")

POSTCONDICIONES = (
    f"{DATOS},"
    f"{ESTRUCTURA},"
    f"{PRIVILEGIOS},"
    f"{RPC_PRIVILEGIOS},"
    # Propietario de las tablas nuevas: quien despliega (postgres en Supabase).
    "(select bool_and(pg_get_userbyid(relowner) = current_user) from pg_class "
    f" where relnamespace = 'public'::regnamespace and relname = any({_lista(TABLAS_NUEVAS)}))")


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_38_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_38_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_h7_deploy_38")
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
            n = len(datos_antes)
            datos, (estructura, privilegios, rpc, propietario) = fila[:n], fila[n:]
            registro["postcondiciones"] = {
                "datos_sin_cambios": [list(datos[0]), *datos[1:]] == datos_antes,
                "estructura_y_rls": estructura, "privilegios_y_acl": privilegios, "rpc_y_beneficiarios": rpc,
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
