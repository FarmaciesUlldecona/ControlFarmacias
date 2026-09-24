from __future__ import annotations

import re
import hashlib
from pathlib import Path

from src.facturas.runtime_supabase.manifiesto_pio import manifiesto_sqlite_pio

ROOT = Path(__file__).resolve().parents[3]


def test_sql_productivo_cualifica_digest_en_extensions():
    paths = [
        ROOT / "sql/migrations/07_cf_proveedores_config.sql",
        ROOT / "sql/preflight/preflight_supabase_controlfarmacias.sql",
        ROOT / "sql/preflight/postflight_supabase_v1.sql",
    ]
    for path in paths:
        sql = path.read_text(encoding="utf-8")
        assert "extensions.digest(" in sql
        assert re.search(r"(?<!extensions\.)\bdigest\s*\(", sql, re.I) is None


def test_staging_instala_pgcrypto_en_schema_productivo_y_cualifica_usos():
    baseline = (ROOT / "sql/staging/00_baseline_controlfarmacias.sql").read_text(encoding="utf-8")
    assert "create extension if not exists pgcrypto with schema extensions" in baseline.casefold()
    assert 'set search_path = "$user", public, extensions' in baseline.casefold()
    for path in (ROOT / "sql/staging").glob("*.sql"):
        sql = path.read_text(encoding="utf-8")
        assert re.search(r"(?<!extensions\.)\bdigest\s*\(", sql, re.I) is None, path.name


def test_funcion_guard_con_search_path_public_usa_referencia_cualificada():
    sql = (ROOT / "sql/migrations/07_cf_proveedores_config.sql").read_text(encoding="utf-8").casefold()
    assert "set search_path = public" in sql
    assert "extensions.digest(" in sql
    assert "c.preflight_pio_manifest_supabase_sha256 = m.sha256" in sql


def test_runner_demuestra_forma_antigua_falla_y_cualificada_funciona():
    runner = (ROOT / "pruebas/certificacion_2f1.py").read_text(encoding="utf-8")
    assert "SET search_path=public; SELECT digest('abc','sha256');" in runner
    assert "fail='42883'" in runner
    assert "extensions.digest('abc','sha256')" in runner
    assert "to_regprocedure('public.cf_preflight_pio_valido()') IS NOT NULL" in runner


def test_dataset_certificado_conserva_manifiesto_exacto():
    # Fixture binaria sintetica, independiente del inventario vivo.
    records = [
        {"ruta_relativa": f"JUNY 26/{name}.pdf", "archivo_hash": h, "estado": "IMPORTADA"}
        for name, h in (("B PIO", "b" * 64), ("A PIO", "a" * 64),
                        ("COPIA PIO", "a" * 64), ("C RITA", "c" * 64))
    ]
    manifest = manifiesto_sqlite_pio(records)
    assert manifest.total == 2
    assert manifest.sha256 == hashlib.sha256(("a" * 64 + "\n" + "b" * 64).encode("ascii")).hexdigest()
