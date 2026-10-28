"""Hito 2BF: despliega EXCLUSIVAMENTE la migracion 23, una vez, en una transaccion.

NO se ejecuta en el hito 2BF (solo se ensaya en local). Requiere confirmacion
expresa de Pio en chat. No invoca RPC funcionales. Normaliza el SQL a LF y exige que
coincida byte a byte con la version del commit indicado (git show <commit>:...).
Revalida precondiciones dentro de la misma transaccion. Error -> rollback y parada;
nunca reintenta. Patron de pruebas/auditoria_2bd/desplegar_22.py.

Uso: python pruebas/auditoria_2bf/desplegar_23.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/23_cf_aprobaciones_albaranes.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_23_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_23_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_2bf_deploy_23")
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("set local lock_timeout='5s'; set local statement_timeout='120s'")
            cur.execute(
                # 23 no aplicada aun: sin tablas ni RPC nuevas y cf_resincronizar_albaran con el texto de la 22.
                "select to_regclass('public.albaranes_aprobaciones') is null "
                "  and to_regclass('public.albaranes_aprobaciones_aplicadas') is null "
                "  and to_regprocedure('public.cf_aplicar_aprobacion_albaran(bigint,jsonb,text)') is null "
                "  and position('cf_revision_albaran_pendiente' in pg_get_functiondef("
                "    'public.cf_resincronizar_albaran(text,bigint,jsonb,text,text)'::regprocedure)) = 0,"
                # 22 aplicada: historial, recepcion y las dos RPC de la resincronizacion.
                "to_regclass('public.albaranes_cambios') is not null "
                "  and exists(select 1 from information_schema.columns where table_schema='public' "
                "  and table_name='albaranes' and column_name='id_recepcion') "
                "  and to_regprocedure('public.cf_registrar_albaran_ausente(text,bigint,text,text)') is not null,"
                # 22 intacta: historial append-only (triggers de update/delete y truncate).
                "(select count(*)=2 from pg_trigger where tgrelid='public.albaranes_cambios'::regclass "
                "  and not tgisinternal),"
                # 19: privilegios minimos.
                "not has_table_privilege('anon', 'public.facturas', 'SELECT') "
                "  and not has_table_privilege('service_role', 'public.albaranes', 'UPDATE'),"
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
            pre = cur.fetchone()
            registro["precondiciones"] = list(pre)
            if not all(pre):
                raise RuntimeError(f"PRECONDICIONES_NO_CUMPLIDAS:{list(pre)}")
            cur.execute("select count(*), coalesce(max(id), 0) from public.albaranes_cambios")
            historial_antes = list(cur.fetchone())
            cur.execute(cuerpo)
            # Comprobacion dentro de la misma transaccion: objetos creados, nada escrito.
            cur.execute(
                "select (select count(*) from public.albaranes_aprobaciones),"
                "(select count(*) from public.albaranes_aprobaciones_aplicadas),"
                "(select array[count(*), coalesce(max(id), 0)] from public.albaranes_cambios),"
                "to_regprocedure('public.cf_registrar_aprobacion_albaran(text,bigint,jsonb,text,timestamptz,text,text)')"
                "  is not null and to_regprocedure('public.cf_aplicar_aprobacion_albaran(bigint,jsonb,text)') is not null,"
                "position('cf_revision_albaran_pendiente' in pg_get_functiondef("
                "  'public.cf_resincronizar_albaran(text,bigint,jsonb,text,text)'::regprocedure)) > 0,"
                "not has_table_privilege('service_role', 'public.albaranes', 'UPDATE') "
                "  and not has_table_privilege('service_role', 'public.albaranes_aprobaciones', 'INSERT,UPDATE,DELETE')")
            aprobaciones, aplicadas, historial, rpcs, resync, privilegios = cur.fetchone()
            registro["postcondiciones"] = {
                "albaranes_aprobaciones": aprobaciones, "albaranes_aprobaciones_aplicadas": aplicadas,
                "historial_sin_cambios": list(historial) == historial_antes, "rpcs": rpcs,
                "resync_solo_pendientes": resync, "privilegios": privilegios}
            if registro["postcondiciones"] != {"albaranes_aprobaciones": 0, "albaranes_aprobaciones_aplicadas": 0,
                                               "historial_sin_cambios": True, "rpcs": True,
                                               "resync_solo_pendientes": True, "privilegios": True}:
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
