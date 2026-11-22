"""Migracion 37: despliega EXCLUSIVAMENTE la migracion 37 (defectos de extraccion directos a REVISION, columna lector y
firma de 8 parametros de cf_registrar_fallo_normalizacion), una vez, en una transaccion.

NO se ejecuta en el hito 37 (solo se ensaya en local, con el rol que imita al postgres de Supabase). Requiere
confirmacion expresa de Pio en chat (hito 37-D) y los flags apagados por Pio durante la ventana. No invoca RPC.
Normaliza el SQL a LF y exige que coincida byte a byte con la version del commit indicado (git show <commit>:...), y la
entrada de linea de ordenes exige ademas ese commit ya subido al main del remoto. Revalida precondiciones dentro de la
misma transaccion. Error -> rollback y parada; nunca reintenta. Patron de pruebas/auditoria_r20/desplegar_36.py.

La migracion nombra el rol del sistema (autorizacion D7 de Pio, solo en la 37 y su rollback); este script no: comprueba
que la firma nueva tiene exactamente los mismos beneficiarios de EXECUTE que la de 7 parametros (la 17) y ninguno de
anon, authenticated ni PUBLIC.

Uso: python pruebas/auditoria_37/desplegar_37.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/37_cf_defectos_directos_a_revision.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
FIRMA_8 = "public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text,jsonb)"
FIRMA_7 = "public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text)"
FIRMA_6 = "public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text)"
REPROCESADO = "public.cf_solicitar_reprocesado(uuid,text)"

_COLUMNA_EXISTE = ("exists (select 1 from information_schema.columns where table_schema = 'public' "
                   "and table_name = 'normalizacion_ejecuciones' and column_name = 'lector')")


def _beneficiarios(firma: str) -> str:
    """Roles (distintos del propietario) con EXECUTE sobre la funcion, ordenados; sin nombrarlos."""
    return (f"(select coalesce(string_agg(a.grantee::regrole::text, ',' order by a.grantee::regrole::text), '') "
            f" from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
            f" where p.oid = '{firma}'::regprocedure and a.grantee <> p.proowner and a.grantee <> 0 "
            f" and a.privilege_type = 'EXECUTE')")


PRECONDICIONES = (
    # 1. 37 no aplicada: sin la firma de 8 parametros ni la columna lector.
    f"select to_regprocedure('{FIRMA_8}') is null and not {_COLUMNA_EXISTE},"
    # 2. 36 aplicada (marca R20) y la RPC de fallo de la 17 (7 y 6 parametros) presente.
    "exists (select 1 from information_schema.columns where table_schema = 'public' "
    "  and table_name = 'cf_configuracion' and column_name = 'conciliacion_r20') "
    f"  and to_regprocedure('{FIRMA_7}') is not null and to_regprocedure('{FIRMA_6}') is not null,"
    # 3. Flags apagados y solo PIO.
    "(select normalizacion_automatica=false and conciliacion_automatica=false and luna_habilitada=false "
    "  and farmacias_habilitadas=array['PIO']::text[] from public.cf_configuracion where id),"
    # 4. Sin claims de conciliacion ni de normalizacion.
    "(select count(*)=0 from public.facturas where conciliacion_bloqueado_por is not null "
    "  or conciliacion_bloqueado_hasta>now()) and "
    "(select count(*)=0 from public.documentos_facturas where bloqueado_por is not null "
    "  or bloqueado_hasta>now() or estado_lectura='NORMALIZANDO'),"
    # 5. 2AX: ningun objeto de public con propietario distinto de postgres.
    "(select count(*)=0 from pg_class c where c.relnamespace='public'::regnamespace "
    "  and c.relkind in ('r','p','v','m','S','f') and pg_get_userbyid(c.relowner)<>'postgres') and "
    "(select count(*)=0 from pg_proc p where p.pronamespace='public'::regnamespace "
    "  and pg_get_userbyid(p.proowner)<>'postgres' "
    "  and not exists(select 1 from pg_depend d where d.objid=p.oid and d.deptype='e'))")

# Lo que la 37 no puede tocar: conteos y huellas de documentos, ejecuciones (sin la columna nueva), historial, facturas
# y conciliaciones; la configuracion; la ACL de la firma de 7 parametros; texto y ACL de la de 6 y del reprocesado.
DATOS = ("select array[(select count(*) from public.documentos_facturas), "
         "(select count(*) from public.normalizacion_ejecuciones), "
         "(select count(*) from public.historial_facturas), "
         "(select count(*) from public.facturas), "
         "(select count(*) from public.conciliaciones)], "
         "(select md5(coalesce(string_agg(md5(to_jsonb(d)::text), '' order by d.id), '')) "
         " from public.documentos_facturas d), "
         "(select md5(coalesce(string_agg(md5((to_jsonb(e) - 'lector')::text), '' order by e.id), '')) "
         " from public.normalizacion_ejecuciones e), "
         "(select md5(coalesce(string_agg(md5(to_jsonb(h)::text), '' order by h.id), '')) "
         " from public.historial_facturas h), "
         "(select md5(coalesce(string_agg(md5(to_jsonb(f)::text), '' order by f.id), '')) from public.facturas f), "
         "(select md5(coalesce(string_agg(md5(to_jsonb(c)::text), '' order by c.id), '')) from public.conciliaciones c), "
         "(select md5(to_jsonb(c)::text) from public.cf_configuracion c where c.id), "
         f"(select coalesce(proacl::text, '') || pg_get_userbyid(proowner) || prosecdef::text from pg_proc "
         f" where oid = '{FIRMA_7}'::regprocedure), "
         f"(select md5(prosrc || coalesce(proacl::text, '') || prosecdef::text) from pg_proc "
         f" where oid = '{FIRMA_6}'::regprocedure), "
         f"(select md5(prosrc || coalesce(proacl::text, '') || prosecdef::text) from pg_proc "
         f" where oid = '{REPROCESADO}'::regprocedure)")

POSTCONDICIONES = (
    f"{DATOS},"
    # Columna lector: jsonb, admite null y sin valor por defecto; todas las filas existentes en null.
    f"{_COLUMNA_EXISTE} and (select data_type = 'jsonb' and is_nullable = 'YES' and column_default is null "
    "  from information_schema.columns where table_schema = 'public' and table_name = 'normalizacion_ejecuciones' "
    "  and column_name = 'lector') and (select count(*) = 0 from public.normalizacion_ejecuciones "
    "  where lector is not null),"
    # Firma de 8 parametros: regla nueva, security definer, propietario quien despliega (postgres en Supabase, como
    # en desplegar_35), mismos beneficiarios que la de 7 (al menos uno) y nada para anon, authenticated ni PUBLIC.
    f"(select prosrc like '%DEFECTO_DIRECTO_A_REVISION%' and prosecdef and pg_get_userbyid(proowner) = current_user "
    f"  from pg_proc where oid = '{FIRMA_8}'::regprocedure) "
    f"  and {_beneficiarios(FIRMA_8)} = {_beneficiarios(FIRMA_7)} and {_beneficiarios(FIRMA_8)} <> '' "
    f"  and not has_function_privilege('anon', '{FIRMA_8}', 'EXECUTE') "
    f"  and not has_function_privilege('authenticated', '{FIRMA_8}', 'EXECUTE') "
    f"  and not exists (select 1 from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, "
    f"       acldefault('f', p.proowner))) a where p.oid = '{FIRMA_8}'::regprocedure and a.grantee = 0),"
    # Firma de 7 parametros: envoltorio SQL de la de 8 con p_lector null.
    f"(select l.lanname = 'sql' and p.prosrc like '%null::jsonb%' and p.prosecdef from pg_proc p "
    f"  join pg_language l on l.oid = p.prolang where p.oid = '{FIRMA_7}'::regprocedure)")


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_37_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_37_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_37_deploy")
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
            datos, (columna, firma_8, firma_7) = fila[:n], fila[n:]
            registro["postcondiciones"] = {
                "datos_sin_cambios": [list(datos[0]), *datos[1:]] == datos_antes,
                "columna_lector": columna, "firma_8_regla_y_privilegios": firma_8, "firma_7_envoltorio": firma_7}
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
