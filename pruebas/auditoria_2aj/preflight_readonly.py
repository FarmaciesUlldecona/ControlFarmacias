"""Inventario local + snapshot PostgreSQL estrictamente READ ONLY para Hito 2AJ."""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIRROR = Path(r"C:\GoogleDrive\FACTURES PIO")
OUT = Path(__file__).with_name(os.environ.get("CF_2AJ_SNAPSHOT_NAME", "snapshot_pre.json"))
MONTHS = {
    "GENER": 1, "FEBRER": 2, "MARC": 3, "ABRIL": 4, "MAIG": 5,
    "JUNY": 6, "JULIOL": 7, "AGOST": 8, "SETEMBRE": 9,
    "OCTUBRE": 10, "NOVEMBRE": 11, "DESEMBRE": 12,
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "MAYO": 5,
    "JUNIO": 6, "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9,
    "SETIEMBRE": 9, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}


def load_env() -> None:
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch)).upper()


def valid_month_folder(path: Path) -> bool:
    words = re.sub(r"[^A-Z0-9]+", " ", normalized(path.name)).split()
    month = next((MONTHS[word] for word in words if word in MONTHS), None)
    year_text = next((word for word in words if re.fullmatch(r"\d{2}|\d{4}", word)), None)
    if month is None or year_text is None:
        return False
    year = int(year_text)
    if year < 100:
        year += 2000
    try:
        return date(year, month, 1) >= date(2026, 6, 1)
    except ValueError:
        return False


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    load_env()
    configured = Path(os.environ["FACTURAS_PIO_DIR"])
    if configured != MIRROR or not configured.is_absolute() or not configured.is_dir():
        raise RuntimeError("FACTURAS_PIO_DIR no coincide con el Mirror certificado")

    all_pdfs = sorted(
        (p for p in MIRROR.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: str(p).casefold(),
    )
    valid_roots = [p for p in MIRROR.iterdir() if p.is_dir() and valid_month_folder(p)]
    pipeline_pdfs = sorted(
        (
            p for folder in valid_roots for p in folder.rglob("*")
            if p.is_file() and p.suffix.lower() == ".pdf"
            and not p.stem.rstrip().casefold().endswith("rita")
        ),
        key=lambda p: str(p).casefold(),
    )
    rita_pdfs = [p for p in all_pdfs if p.stem.rstrip().casefold().endswith("rita")]

    inventory = []
    for path in pipeline_pdfs:
        stat = path.stat()
        inventory.append({
            "relative_path": str(path.relative_to(MIRROR)),
            "size": stat.st_size,
            "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "sha256": sha256(path),
        })

    import psycopg2

    connection = psycopg2.connect(
        os.environ["CONTROLFARMACIAS_SUPABASE_DB_URL"],
        sslmode="require",
        connect_timeout=10,
        application_name="cf_2aj_preflight_readonly",
    )
    connection.set_session(readonly=True, autocommit=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                select archivo_hash from public.documentos_facturas
                 where farmacia='PIO' and archivo_hash is not null
            """)
            db_hashes = {str(row[0]) for row in cursor.fetchall()}
            cursor.execute("""
                select count(*), count(distinct archivo_hash),
                       count(*) filter (where estado_lectura='PENDIENTE'),
                       count(*) filter (where estado_lectura='PENDIENTE'
                                        and bloqueado_por is null
                                        and bloqueado_hasta is null)
                  from public.documentos_facturas where farmacia='PIO'
            """)
            documents = cursor.fetchone()
            cursor.execute("""
                select count(*) from storage.objects
                 where bucket_id='facturas-pdf' and name like 'PIO/%'
            """)
            storage_count = cursor.fetchone()[0]
            cursor.execute("""
                select count(*),
                       count(*) filter(where estado_conciliacion_cf='CONCILIADA'),
                       count(*) filter(where estado_conciliacion_cf='PENDIENTE_CONCILIAR')
                  from public.facturas
            """)
            invoices = cursor.fetchone()
            cursor.execute("""
                select numero_factura, md5(to_jsonb(f)::text)
                  from public.facturas f order by numero_factura
            """)
            invoice_fingerprints = dict(cursor.fetchall())
            cursor.execute("""
                select (select count(*) from public.normalizacion_ejecuciones),
                       (select count(*) from public.conciliaciones),
                       (select count(*) from public.documentos_facturas
                         where bloqueado_por is not null or bloqueado_hasta is not null),
                       (select count(*) from public.facturas
                         where conciliacion_bloqueado_por is not null
                            or conciliacion_bloqueado_hasta is not null)
            """)
            runtime = cursor.fetchone()
            cursor.execute("""
                select normalizacion_automatica, conciliacion_automatica,
                       luna_habilitada, farmacias_habilitadas
                  from public.cf_configuracion where id=true
            """)
            flags = cursor.fetchone()
            cursor.execute("""
                select count(*) from pg_stat_activity
                 where pid<>pg_backend_pid()
                   and (application_name ilike '%%worker%%'
                        or application_name ilike '%%runtime%%')
            """)
            workers = cursor.fetchone()[0]
    finally:
        connection.rollback()
        connection.close()

    local_hashes = [item["sha256"] for item in inventory]
    unique_local = set(local_hashes)
    result = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "mode": "filesystem read-only + PostgreSQL READ ONLY/rollback",
        "mirror": str(MIRROR),
        "pdfs_all_under_mirror": len(all_pdfs),
        "pdfs_pipeline_detected": len(inventory),
        "pdfs_rita_excluded": len(rita_pdfs),
        "source_unique_hashes": len(unique_local),
        "source_duplicate_sha_occurrences": len(local_hashes) - len(unique_local),
        "source_known_by_sha": sum(1 for value in local_hashes if value in db_hashes),
        "source_potentially_new_unique": len(unique_local - db_hashes),
        "inventory": inventory,
        "database": {
            "documents_pio": documents[0],
            "unique_hashes_pio": documents[1],
            "pending_pio": documents[2],
            "claimable_pending_pio": documents[3],
            "storage_objects_pio": storage_count,
            "invoices": invoices,
            "invoice_fingerprints": invoice_fingerprints,
            "normalizations": runtime[0],
            "conciliations": runtime[1],
            "document_locks": runtime[2],
            "invoice_locks": runtime[3],
            "flags": flags,
            "workers": workers,
        },
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "inventory"}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
