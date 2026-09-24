"""Despliega exclusivamente migración 16; jamás invoca RPC funcionales."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import auditar_readonly as audit

MIGRATION = ROOT / "sql" / "migrations" / "16_cf_worker_manual_one_shot.sql"
EXPECTED_MIGRATION_SHA = "3c543bf7beed1b1051ef1ff9ddd23ba49a1e4e35aaac54c08f3d7e45fc7c47a4"
EXPECTED_DEFINITION_HASHES = {
    ("cf_reclamar_documento_normalizacion", "p_worker_id text, p_bloqueo_segundos integer"): "3c80c347dc2504a804bc6fe46794365e4cb9ffc0501cf4b44a001dd304e80c32",
    ("cf_persistir_documento_multifactura", "p_documento_id uuid, p_worker_id text, p_idempotency_key text, p_resultado_hash text, p_resultado jsonb, p_segmentos_autorizados text[]"): "81c5c447b8942e5aa64c67e8fb1f314f389d01c0fe8997713178a8b557fb438c",
}


def preflight() -> dict:
    backup = json.loads((HERE / "backup_pre.json").read_text(encoding="utf-8"))
    current = audit.snapshot()
    audit.validate_pre(current)
    assert current["project_ref"] == backup["project_ref"]
    assert current["flags"] == [backup["flags"]]
    assert current["conteos"] == backup["conteos"]
    assert current["locks"] == [backup["locks"]]
    assert current["workers"] == backup["workers"]
    assert current["huellas"] == {k: [v] for k, v in backup["huellas"].items()}
    actual_hashes = {
        (row[0], row[1]): hashlib.sha256(row[11].encode()).hexdigest()
        for row in current["funciones"]
    }
    assert actual_hashes == EXPECTED_DEFINITION_HASHES, "DEFINICIONES_PREVIAS_CAMBIARON"
    return current


def validate_post(pre: dict, post: dict) -> dict:
    assert post["project_ref"] == pre["project_ref"]
    for key in ("flags", "conteos", "locks", "workers", "huellas", "marcadores_07_15"):
        assert post[key] == pre[key], "POSTCHECK_DIFERENCIA_" + key
    assert "MANUAL_ONE_SHOT" in post["constraint_disparador"][0][1]
    by_sig = {(row[0], row[1]): row for row in post["funciones"]}
    auto = by_sig[("cf_reclamar_documento_normalizacion", "p_worker_id text, p_bloqueo_segundos integer")]
    manual = by_sig[("cf_reclamar_documento_normalizacion_manual_one_shot", "p_worker_id text, p_bloqueo_segundos integer")]
    core = by_sig[("cf_reclamar_documento_normalizacion_nucleo", "p_worker_id text, p_bloqueo_segundos integer, p_modo_ejecucion text")]
    old_persist = by_sig[("cf_persistir_documento_multifactura", "p_documento_id uuid, p_worker_id text, p_idempotency_key text, p_resultado_hash text, p_resultado jsonb, p_segmentos_autorizados text[]")]
    new_persist = by_sig[("cf_persistir_documento_multifactura", "p_documento_id uuid, p_worker_id text, p_idempotency_key text, p_resultado_hash text, p_resultado jsonb, p_segmentos_autorizados text[], p_disparador text")]
    for row in (auto, manual, core, old_persist, new_persist):
        assert row[3] == "postgres" and row[4] is True and row[6] == ["search_path=public"]
        assert row[8] is False and row[9] is False
    assert auto[10] is True and manual[10] is True and new_persist[10] is True
    assert core[10] is False and old_persist[10] is False
    assert "'AUTOMATICO'" in auto[11]
    assert "'MANUAL_ONE_SHOT'" in manual[11]
    assert "from public.cf_reclamar_documento_normalizacion_nucleo" in auto[11].lower()
    assert "from public.cf_reclamar_documento_normalizacion_nucleo" in manual[11].lower()
    assert "p_disparador" in new_persist[11] and "provenance_ejecucion" in new_persist[11]
    return {
        "rpc_manual": True,
        "ruta_automatica": True,
        "ruta_manual": True,
        "grants": True,
        "constraint_manual_one_shot": True,
    }


def main() -> None:
    raw = MIGRATION.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == EXPECTED_MIGRATION_SHA, "MIGRACION_16_CAMBIADA_PARAR"
    sql = raw.decode("utf-8")
    forbidden = ("ejecutar_una_manual", "ejecutar_una()", "start-scheduledtask")
    assert all(token not in sql.casefold() for token in forbidden)
    pre = preflight()
    started = datetime.now(timezone.utc).isoformat()
    print(f"PREFLIGHT=OK|SHA256={sha}|INICIO_UTC={started}", flush=True)
    conn = audit.psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"],
        sslmode="require",
        connect_timeout=10,
        application_name="cf_2an_migracion16",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("set lock_timeout='5s'; set statement_timeout='60s'")
            cur.execute(sql)
    except audit.psycopg2.Error as exc:
        print("ERROR_SQL=" + str(exc.pgcode), flush=True)
        raise
    finally:
        conn.close()
    finished = datetime.now(timezone.utc).isoformat()
    post = audit.snapshot()
    structural = validate_post(pre, post)
    result = {
        "inicio_utc": started,
        "fin_utc": finished,
        "migration_sha256": sha,
        "objetos": [
            "normalizacion_ejecuciones_disparador_check",
            "cf_reclamar_documento_normalizacion_nucleo(text,integer,text)",
            "cf_reclamar_documento_normalizacion(text,integer)",
            "cf_reclamar_documento_normalizacion_manual_one_shot(text,integer)",
            "cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)",
            "grants de las firmas afectadas",
        ],
        "estructural": structural,
        "conteos_antes": pre["conteos"],
        "conteos_despues": post["conteos"],
        "flags_finales": post["flags"],
        "locks_finales": post["locks"],
        "workers_finales": post["workers"],
        "huellas_sin_cambios": post["huellas"] == pre["huellas"],
        "documento_reclamado": False,
        "produccion_economica_modificada": False,
    }
    print("MIGRACION_16_APLICADA=SI", flush=True)
    print("POSTCHECK=" + json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
