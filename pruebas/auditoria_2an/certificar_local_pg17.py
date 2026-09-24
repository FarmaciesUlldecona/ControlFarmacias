"""Dos ciclos locales PostgreSQL 17 de migraciones 07..16, sin red ni producción."""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pruebas import certificacion_2f1 as pg


def q(db: str, sql: str) -> str:
    return pg.sql(db, sql)


def cycle(number: int) -> None:
    db = f"cf_2an_cycle_{number}"
    pg.docker("exec", pg.CONTAINER, "createdb", "-U", "postgres", db)
    pg.file(db, pg.STG / "00_baseline_controlfarmacias.sql")
    paths = [
        "06b_cf_integridad_albaranes.sql",
        "07_cf_proveedores_config.sql",
        "08_cf_core_facturas.sql",
        "08b_cf_estado_lectura_compatibilidad.sql",
        "09_cf_normalizacion_runtime.sql",
        "10_cf_movimientos_incidencias_historial.sql",
        "11_cf_conciliacion.sql",
        "12_cf_views_rls_rpc.sql",
    ]
    for name in paths:
        pg.file(db, pg.MIG / name)
    pg.file(db, pg.STG / "01_seed_controlfarmacias.sql")
    pg.file(db, pg.STG / "06_test_backfill_pio.sql")
    pg.file(db, pg.MIG / "14_cf_claim_conciliacion_v2.sql")
    pg.file(db, pg.MIG / "15_cf_multifactura.sql")
    before = q(db, "select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion")
    pg.file(db, pg.MIG / "16_cf_worker_manual_one_shot.sql")
    assert q(db, "show server_version").startswith("17.")
    assert before == "f|f|f|{PIO}" == q(db, "select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion")
    assert q(db, "select to_regprocedure('public.cf_reclamar_documento_normalizacion_nucleo(text,integer,text)') is not null,to_regprocedure('public.cf_reclamar_documento_normalizacion(text,integer)') is not null,to_regprocedure('public.cf_reclamar_documento_normalizacion_manual_one_shot(text,integer)') is not null,to_regprocedure('public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)') is not null") == "t|t|t|t"
    assert q(db, "select has_function_privilege('service_role','public.cf_reclamar_documento_normalizacion(text,integer)','execute'),has_function_privilege('service_role','public.cf_reclamar_documento_normalizacion_manual_one_shot(text,integer)','execute'),has_function_privilege('service_role','public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)','execute'),has_function_privilege('service_role','public.cf_reclamar_documento_normalizacion_nucleo(text,integer,text)','execute')") == "t|t|t|f"
    # Reaplicar debe compilar y no cambiar datos/configuración.
    fingerprints = q(db, "select md5(coalesce(string_agg(to_jsonb(d)::text,'' order by id),'')) from public.documentos_facturas d")
    pg.file(db, pg.MIG / "16_cf_worker_manual_one_shot.sql")
    assert fingerprints == q(db, "select md5(coalesce(string_agg(to_jsonb(d)::text,'' order by id),'')) from public.documentos_facturas d")
    assert before == q(db, "select normalizacion_automatica,conciliacion_automatica,luna_habilitada,farmacias_habilitadas from public.cf_configuracion")
    print(f"CICLO_{number}=PG17_COMPILA_IDEMPOTENTE_GRANTS_OK", flush=True)


def main() -> None:
    print("DESTINO=POSTGRESQL_17_LOCAL_SIN_RED", flush=True)
    for number in (1, 2):
        suffix = uuid.uuid4().hex[:12]
        name = "cf-2an-" + suffix
        volume = name + "-data"
        pg.CONTAINER = name
        pg.docker("volume", "create", "--label", "controlfarmacias.certificacion=2an", volume)
        try:
            pg.docker("run", "-d", "--name", name, "--label", "controlfarmacias.certificacion=2an", "--network", "none", "--mount", f"type=volume,source={volume},target=/var/lib/postgresql/data", "-e", "POSTGRES_PASSWORD=local-only", "postgres:17-alpine")
            for _ in range(40):
                if pg.docker("exec", name, "pg_isready", "-U", "postgres", check=False).returncode == 0:
                    break
                time.sleep(0.5)
            info = json.loads(pg.docker("inspect", name).stdout)[0]
            assert info["HostConfig"]["NetworkMode"] == "none" and not info["HostConfig"]["PortBindings"]
            cycle(number)
        finally:
            if pg.docker("inspect", name, check=False).returncode == 0:
                pg.docker("rm", "-f", name)
            if pg.docker("volume", "inspect", volume, check=False).returncode == 0:
                pg.docker("volume", "rm", volume)
            print(f"CICLO_{number}=RECURSOS_ELIMINADOS", flush=True)


if __name__ == "__main__":
    main()
