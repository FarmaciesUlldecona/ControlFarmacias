"""Hito 2AS: despliega EXCLUSIVAMENTE la migracion 17, una vez, en una transaccion.

Requiere confirmacion expresa de Pio en chat antes de ejecutarse. No invoca RPC
funcionales. Normaliza el SQL a LF y exige que coincida byte a byte con la
version commiteada (git show HEAD:...). Revalida precondiciones dentro de la
misma transaccion. Error -> rollback y parada; nunca reintenta.

Uso: python pruebas/auditoria_2as/desplegar_17.py <sha256_lf_esperado> <salida.json>
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
RUTA = "sql/migrations/17_cf_replay_y_fallos_no_bloqueantes.sql"


def sql_lf() -> str:
    local = (ROOT / RUTA).read_bytes().decode("utf-8").replace("\r\n", "\n")
    commit = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{RUTA}"], capture_output=True,
                            check=True).stdout.decode("utf-8").replace("\r\n", "\n")
    if local != commit:
        raise SystemExit("MIGRACION_17_NO_COINCIDE_CON_COMMIT")
    return local


def cuerpo_transaccional(sql: str) -> str:
    """Quita el begin/commit exterior: la transaccion la gestiona el script."""
    lineas = sql.split("\n")
    inicio = lineas.index("begin;")
    fin = len(lineas) - 1 - lineas[::-1].index("commit;")
    assert all(l.startswith("--") or not l.strip() for l in lineas[:inicio])
    assert all(not l.strip() for l in lineas[fin + 1:])
    return "\n".join(lineas[inicio + 1:fin])


def main(esperado: str, salida: Path) -> None:
    sql = sql_lf()
    sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    if sha != esperado:
        raise SystemExit(f"SHA256_MIGRACION_17_INESPERADO:{sha}")
    cuerpo = cuerpo_transaccional(sql)

    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    from dotenv import dotenv_values
    import psycopg2

    dsn = os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"]
    app = urlparse(dotenv_values(ROOT / ".env").get("SUPABASE_URL", ""))
    db = urlparse(dsn)
    ref = (app.hostname or "").split(".")[0]
    assert ref and (
        db.hostname == f"db.{ref}.supabase.co"
        or ((db.hostname or "").endswith(".pooler.supabase.com")
            and unquote(db.username or "").endswith("." + ref))
    ), "DESTINO_PRODUCTIVO_NO_DEMOSTRADO"

    registro = {"project_ref": ref, "migracion": RUTA, "sha256_lf": sha,
                "inicio_utc": datetime.now(timezone.utc).isoformat()}
    conn = psycopg2.connect(dsn, sslmode="require", connect_timeout=10, application_name="cf_2as_deploy_17")
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("set local lock_timeout='5s'; set local statement_timeout='120s'")
            cur.execute(
                "select to_regprocedure('public.cf_cerrar_replay_normalizacion(uuid,text,uuid,text)') is null,"
                "to_regprocedure('public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text)') is null,"
                "not exists(select 1 from information_schema.columns where table_schema='public' "
                "  and table_name='documentos_facturas' and column_name='intentos_fallo_normalizacion'),"
                "(select normalizacion_automatica=false and conciliacion_automatica=false and luna_habilitada=false "
                "  and farmacias_habilitadas=array['PIO']::text[] from public.cf_configuracion where id),"
                "(select count(*)=0 from public.documentos_facturas where bloqueado_por is not null "
                "  or bloqueado_hasta>now()),"
                "(select count(*)=0 from public.documentos_facturas where estado_lectura='NORMALIZANDO')")
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
    main(sys.argv[1], Path(sys.argv[2]))
