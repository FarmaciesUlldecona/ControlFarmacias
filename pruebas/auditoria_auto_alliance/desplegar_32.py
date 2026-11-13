"""Hito AUTO-32-D: despliega EXCLUSIVAMENTE la migracion 32 (tabla de resumen nocturno), una vez, en una transaccion.

NO se ejecuta en AUTO-A (solo se ensaya en local, con el rol que imita al postgres de Supabase). Requiere confirmacion
expresa de Pio en chat (hito AUTO-32-D). No invoca RPC. Normaliza el SQL a LF y exige que coincida byte a byte con
la version del commit indicado (git show <commit>:...). Revalida precondiciones dentro de la misma transaccion.
Error -> rollback y parada; nunca reintenta. Patron de pruebas/auditoria_trab/desplegar_31.py.

Uso: python pruebas/auditoria_auto_alliance/desplegar_32.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/32_cf_noches_automaticas.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
TABLA = "cf_noches_automaticas"
LECTURA_GENERAL = "cf_lectura"
POLITICA = "cf_noches_automaticas_lectura_select"

PRECONDICIONES = (
    # 1. 32 no aplicada.
    f"select to_regclass('public.{TABLA}') is null,"
    # 2. 31 aplicada.
    "to_regclass('public.cf_modulos_farmacias') is not null,"
    # 3. cf_lectura (29) presente.
    f"exists (select 1 from pg_roles where rolname = '{LECTURA_GENERAL}'),"
    # 4. 19: privilegios minimos.
    "not has_table_privilege('anon', 'public.facturas', 'SELECT') "
    "  and not has_table_privilege('authenticated', 'public.albaranes', 'UPDATE'),"
    # 5. Flags apagados y solo PIO (la 32 se despliega antes de cualquier noche).
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
         "(select count(*) from public.trabajadoras)], "
         "(select md5(coalesce(string_agg(md5(to_jsonb(f)::text), '' order by f.id), '')) from public.facturas f), "
         "(select md5(to_jsonb(c)::text) from public.cf_configuracion c where c.id)")

# ACL de la tabla (decision de Pio, 2026-11-12), sin nombrar el rol del sistema: ademas del propietario y de
# cf_lectura (solo SELECT), exactamente UN beneficiario (el del orquestador) con SELECT, INSERT y UPDATE y sin DELETE,
# TRUNCATE, REFERENCES ni TRIGGER. PUBLIC, anon y authenticated: nada.
_ACL = ("from pg_class c cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a "
        f"where c.oid = 'public.{TABLA}'::regclass and a.grantee <> c.relowner")
_ESCRITOR = f"a.grantee <> 0 and pg_get_userbyid(a.grantee) <> '{LECTURA_GENERAL}'"
ACL_ESCRITOR = (
    # (beneficiarios distintos, privilegios del unico beneficiario ordenados)
    f"select count(distinct a.grantee) = 1 and array_agg(distinct a.privilege_type order by a.privilege_type) "
    f"= array['INSERT', 'SELECT', 'UPDATE'] {_ACL} and {_ESCRITOR}")
ACL_AJENA = (
    f"select count(*) {_ACL} and (a.grantee = 0 or pg_get_userbyid(a.grantee) in ('anon', 'authenticated') "
    f"  or (pg_get_userbyid(a.grantee) = '{LECTURA_GENERAL}' and a.privilege_type <> 'SELECT'))")

POSTCONDICIONES = (
    f"{DATOS},"
    # Tabla con RLS, una sola politica (SELECT para cf_lectura) y propietario = quien despliega (postgres).
    f"(select relrowsecurity from pg_class where oid = 'public.{TABLA}'::regclass)"
    f" and (select count(*) = 1 from pg_policy where polrelid = 'public.{TABLA}'::regclass)"
    f" and exists (select 1 from pg_policy where polrelid = 'public.{TABLA}'::regclass and polname = '{POLITICA}' "
    f"  and polcmd = 'r' and polroles = array['{LECTURA_GENERAL}'::regrole::oid])"
    f" and (select pg_get_userbyid(relowner) = current_user from pg_class where oid = 'public.{TABLA}'::regclass),"
    # Lectura: cf_lectura lee y no escribe; anon y authenticated nada; ningun beneficiario ajeno.
    f"has_table_privilege('{LECTURA_GENERAL}', 'public.{TABLA}', 'SELECT')"
    f" and not has_table_privilege('{LECTURA_GENERAL}', 'public.{TABLA}', 'INSERT,UPDATE,DELETE,TRUNCATE')"
    f" and not has_table_privilege('anon', 'public.{TABLA}', 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')"
    f" and not has_table_privilege('authenticated', 'public.{TABLA}', 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')"
    f" and ({ACL_AJENA}) = 0 and ({ACL_ESCRITOR}),"
    # Configuracion global intacta.
    "(select farmacias_habilitadas = array['PIO']::text[] and not normalizacion_automatica "
    "  and not conciliacion_automatica and not luna_habilitada from public.cf_configuracion where id)")


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_32_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_32_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_auto_deploy_32")
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
            conteos, facturas, configuracion, tabla, lectura, global_ = cur.fetchone()
            registro["postcondiciones"] = {
                "datos_sin_cambios": [list(conteos), facturas, configuracion] == datos_antes, "tabla": tabla,
                "lectura_y_acl": lectura, "configuracion_global": global_}
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
