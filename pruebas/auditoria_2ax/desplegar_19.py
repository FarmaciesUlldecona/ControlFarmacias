"""Hito 2AX: despliega EXCLUSIVAMENTE la migracion 19, una vez, en una transaccion.

Requiere confirmacion expresa de Pio en chat antes de ejecutarse. No invoca RPC
funcionales. Normaliza el SQL a LF y exige que coincida byte a byte con la
version del commit de la Fase 0 (git show <commit>:...). Revalida precondiciones
dentro de la misma transaccion. Error -> rollback y parada; nunca reintenta.

Uso: python pruebas/auditoria_2ax/desplegar_19.py <commit> <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/19_cf_privilegios_minimos.sql"
PROJECT_REF = "vklaiuytvegkelgyspxc"
CONCILIACIONES_ESPERADAS = 12


def sql_lf(commit: str) -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    versionada = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{RUTA}"], capture_output=True,
                                check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != versionada:
        raise SystemExit("MIGRACION_19_NO_COINCIDE_CON_COMMIT")
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
        raise SystemExit(f"SHA256_MIGRACION_19_INESPERADO:{sha}")
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
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_2ax_deploy_19")
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("set local lock_timeout='5s'; set local statement_timeout='120s'")
            cur.execute(
                # 19 no aplicada aun: anon conserva los grants heredados sobre albaranes y las vistas.
                "has_table_privilege('anon', 'public.albaranes', 'SELECT'),"
                "has_table_privilege('authenticated', 'public.facturas', 'SELECT'),"
                # 18 presente.
                "to_regprocedure('public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)') is not null,"
                "exists(select 1 from information_schema.columns where table_schema='public' "
                "  and table_name='conciliaciones' and column_name='idempotency_key'),"
                "(select normalizacion_automatica=false and conciliacion_automatica=false and luna_habilitada=false "
                "  and farmacias_habilitadas=array['PIO']::text[] from public.cf_configuracion where id),"
                "(select count(*)=0 from public.facturas where conciliacion_bloqueado_por is not null "
                "  or conciliacion_bloqueado_hasta>now()),"
                "(select count(*)=0 from public.documentos_facturas where bloqueado_por is not null "
                "  or bloqueado_hasta>now() or estado_lectura='NORMALIZANDO'),"
                f"(select count(*)={CONCILIACIONES_ESPERADAS} from public.conciliaciones)")
            pre = cur.fetchone()
            registro["precondiciones"] = list(pre)
            if not all(pre):
                raise RuntimeError(f"PRECONDICIONES_NO_CUMPLIDAS:{list(pre)}")
            cur.execute(cuerpo)
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
    print(json.dumps({k: registro[k] for k in ("resultado", "sha256_lf", "precondiciones")}, ensure_ascii=False))
    if registro["resultado"] != "APLICADA":
        raise SystemExit(registro.get("error"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
