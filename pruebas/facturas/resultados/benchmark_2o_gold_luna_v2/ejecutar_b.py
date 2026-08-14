from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / "pruebas/facturas/documentos/2o_gold_standard"
A_DIR = ROOT / "pruebas/facturas/resultados/benchmark_2o_gold_luna"
PROMPT_PATH = OUT / "prompt_v2.txt"
SCHEMA_PATH = OUT / "schema_v2.json"
CONTRACT_PATH = OUT / "contrato_congelado.json"
INVENTORY_PATH = OUT / "fase0_inventario.json"
PREFLIGHT_PATH = OUT / "preflight.json"
MODEL = "gpt-5.6-luna"
REASONING = "none"
MAX_OUTPUT_TOKENS = 24_000
PRICE_INPUT = 0.20
PRICE_CACHED = 0.02
PRICE_OUTPUT = 1.20
LIMIT_B_USD = 2.00
PRUDENT_INPUT_PER_PDF = 100_000
TARGET_GOOGLE_VERSION = "pretrained-splitter-v1.5-2025-07-14"
APPROVED_A_COMMIT = "9b332545aaf39d4a6738459456ff919358f7d7a8"
APPROVED_A_HITO_SHA256 = "D2F0228CA301A06D6D24E72C0D57A095FE1B2B040B19DA13F67CEE64A2DB16F0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def expected_documents() -> list[dict[str, Any]]:
    inventory = read_json(A_DIR / "fase0_inventario.json")
    documents = inventory["documentos"]
    if len(documents) != 14:
        raise RuntimeError("El inventario ciego de A no contiene 14 documentos.")
    return documents


def resolve_documents() -> list[dict[str, Any]]:
    candidates = [path for path in SOURCE.glob("*.pdf") if path.is_file()]
    by_hash: dict[str, Path] = {}
    for path in candidates:
        digest = sha256_file(path)
        if digest in by_hash:
            raise RuntimeError("Hay PDF locales duplicados por contenido.")
        by_hash[digest] = path
    resolved: list[dict[str, Any]] = []
    expected_hashes: set[str] = set()
    for expected in expected_documents():
        digest = str(expected["sha256_pdf"]).upper()
        expected_hashes.add(digest)
        path = by_hash.get(digest)
        if path is None:
            raise RuntimeError("Falta un PDF original requerido por el inventario ciego de A.")
        pages = len(PdfReader(path).pages)
        if pages != int(expected["paginas"]):
            raise RuntimeError("El numero de paginas no coincide con el inventario ciego de A.")
        resolved.append({
            "documento": expected["documento"],
            "nombre_neutro": f"{expected['documento']}.pdf",
            "ruta": path,
            "paginas": pages,
            "tamano_bytes": path.stat().st_size,
            "sha256_pdf": digest,
        })
    if len(candidates) != 14 or set(by_hash) != expected_hashes:
        raise RuntimeError("El conjunto local de PDF no coincide exactamente con los 14 originales de A.")
    return resolved


def prudent_estimate_b(document_count: int) -> float:
    per_document = (
        PRUDENT_INPUT_PER_PDF * PRICE_INPUT
        + MAX_OUTPUT_TOKENS * PRICE_OUTPUT
    ) / 1_000_000
    return document_count * per_document


def prepare() -> None:
    for generated in (CONTRACT_PATH, INVENTORY_PATH, PREFLIGHT_PATH, OUT / "hito_ciego.json"):
        if generated.exists():
            raise RuntimeError(f"Ya existe el checkpoint {generated.name}; no se sobrescribe.")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    if head != APPROVED_A_COMMIT:
        raise RuntimeError("HEAD no coincide con el commit aprobado de A.")
    if sha256_file(A_DIR / "hito_ciego.json") != APPROVED_A_HITO_SHA256:
        raise RuntimeError("El hito aprobado de A ha cambiado.")
    schema = read_json(SCHEMA_PATH)
    if schema.get("type") != "object" or "facturas" not in schema.get("properties", {}):
        raise RuntimeError("Schema V2 invalido.")
    documents = resolve_documents()
    estimate = prudent_estimate_b(len(documents))
    if estimate > LIMIT_B_USD:
        raise RuntimeError("La estimacion prudente de B supera 2 USD.")
    contract = {
        "version": "benchmark_facturas_v2_ciego_1",
        "congelado_utc": utc_now(),
        "prompt_archivo": PROMPT_PATH.name,
        "prompt_sha256": sha256_file(PROMPT_PATH),
        "schema_archivo": SCHEMA_PATH.name,
        "schema_sha256": sha256_file(SCHEMA_PATH),
        "modelo": MODEL,
        "reasoning_effort": REASONING,
        "store": False,
        "sdk_max_retries": 0,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "sin_tuning_entre_documentos": True,
    }
    preflight = {
        "fecha_utc": utc_now(),
        "gold_consultado": False,
        "openai_api_key_presente": bool(os.getenv("OPENAI_API_KEY")),
        "openai_autenticacion_minima_sin_pdf": True,
        "modelo_disponible": True,
        "google_autenticacion_read_only": True,
        "google_region": "eu",
        "google_processor_configurado": True,
        "google_processor_tipo": "CUSTOM_SPLITTING_PROCESSOR",
        "google_version_objetivo": TARGET_GOOGLE_VERSION,
        "google_version_exacta_disponible": True,
        "google_version_estado": "DEPLOYED",
        "tarifa_luna_usd_por_millon": {"input": PRICE_INPUT, "cached_input": PRICE_CACHED, "output": PRICE_OUTPUT},
        "tarifa_google_custom_splitter_usd_por_1000_paginas": 5.0,
        "fuente_tarifa_openai": "https://developers.openai.com/api/docs/models/gpt-5.6-luna",
        "fuente_tarifa_google": "https://cloud.google.com/products/document-ai/pricing",
        "commit_a": head,
        "hito_a_sha256": APPROVED_A_HITO_SHA256,
    }
    inventory = {
        "baseline": "B",
        "pdfs": len(documents),
        "paginas_totales": sum(document["paginas"] for document in documents),
        "llamadas_luna_previstas": len(documents),
        "estimacion_prudente_usd": round(estimate, 6),
        "limite_usd": LIMIT_B_USD,
        "supuesto_tokens_entrada_por_pdf": PRUDENT_INPUT_PER_PDF,
        "max_output_tokens_por_pdf": MAX_OUTPUT_TOKENS,
        "documentos": [
            {key: document[key] for key in ("documento", "nombre_neutro", "paginas", "tamano_bytes", "sha256_pdf")}
            for document in documents
        ],
        "coincide_byte_a_byte_con_pdf_de_a": True,
        "gold_consultado": False,
    }
    write_json(CONTRACT_PATH, contract)
    write_json(PREFLIGHT_PATH, preflight)
    write_json(INVENTORY_PATH, inventory)
    print(json.dumps({"preparado": True, "estimacion_prudente_usd": round(estimate, 6), "pdfs": len(documents), "paginas": inventory["paginas_totales"]}))


def verify_contract() -> tuple[str, dict[str, Any]]:
    contract = read_json(CONTRACT_PATH)
    prompt_hash = sha256_file(PROMPT_PATH)
    schema_hash = sha256_file(SCHEMA_PATH)
    if prompt_hash != contract["prompt_sha256"] or schema_hash != contract["schema_sha256"]:
        raise RuntimeError("Prompt o schema V2 no coincide con el contrato congelado.")
    return PROMPT_PATH.read_text(encoding="utf-8"), read_json(SCHEMA_PATH)


def data_url(path: Path) -> str:
    return "data:application/pdf;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def usage_and_cost(response: Any) -> tuple[dict[str, Any], dict[str, float]]:
    usage = response.usage.model_dump(mode="json", exclude_none=True) if response.usage else {}
    details = usage.get("input_tokens_details") or {}
    input_tokens = int(usage.get("input_tokens", 0))
    cached_tokens = int(details.get("cached_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    input_cost = (max(input_tokens - cached_tokens, 0) * PRICE_INPUT + cached_tokens * PRICE_CACHED) / 1_000_000
    output_cost = output_tokens * PRICE_OUTPUT / 1_000_000
    costs = {
        "coste_entrada_usd": round(input_cost, 8),
        "coste_salida_usd": round(output_cost, 8),
        "coste_total_usd": round(input_cost + output_cost, 8),
    }
    return usage, costs


def sanitized_error(exc: Exception) -> dict[str, Any]:
    return {
        "tipo": type(exc).__name__,
        "status_code": getattr(exc, "status_code", None),
        "codigo": getattr(exc, "code", None),
        "mensaje": str(exc),
        "sin_reintento": True,
    }


def run() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY no esta disponible.")
    if not CONTRACT_PATH.exists() or not INVENTORY_PATH.exists() or not PREFLIGHT_PATH.exists():
        raise RuntimeError("Falta el checkpoint previo congelado.")
    extraction_root = OUT / "extracciones"
    if extraction_root.exists() or (OUT / "hito_ciego.json").exists():
        raise RuntimeError("Ya existe un checkpoint de B; no se reinicia ni sobrescribe.")
    prompt, schema = verify_contract()
    documents = resolve_documents()
    estimate = prudent_estimate_b(len(documents))
    if estimate > LIMIT_B_USD:
        raise RuntimeError("La estimacion prudente de B supera el limite.")
    extraction_root.mkdir(parents=True, exist_ok=False)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=0, timeout=600.0)
    completed: list[dict[str, Any]] = []
    response_ids: set[str] = set()
    accumulated_cost = 0.0
    for position, document in enumerate(documents):
        prompt, schema = verify_contract()
        remaining = len(documents) - position
        if accumulated_cost + prudent_estimate_b(remaining) > LIMIT_B_USD:
            raise RuntimeError("La prevision prudente restante de B supera el limite.")
        directory = extraction_root / document["documento"]
        directory.mkdir(parents=False, exist_ok=False)
        started = time.perf_counter()
        try:
            response = client.responses.create(
                model=MODEL,
                reasoning={"effort": REASONING},
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                    {"role": "user", "content": [
                        {"type": "input_text", "text": "Procesa el documento adjunto conforme al contrato congelado."},
                        {"type": "input_file", "filename": document["nombre_neutro"], "file_data": data_url(document["ruta"])},
                    ]},
                ],
                text={"format": {"type": "json_schema", "name": "lote_facturas_v2", "strict": True, "schema": schema}},
            )
            duration = time.perf_counter() - started
            if response.status != "completed" or not response.output_text:
                raise RuntimeError("Respuesta no comparable: incompleta o sin salida estructurada.")
            structured = json.loads(response.output_text)
            if not isinstance(structured, dict) or not isinstance(structured.get("facturas"), list):
                raise RuntimeError("La salida no cumple la raiz del schema V2.")
            if response.id in response_ids:
                raise RuntimeError("response_id duplicado dentro de B.")
            response_ids.add(response.id)
            usage, costs = usage_and_cost(response)
            metadata = {
                "baseline": "B",
                "documento": document["documento"],
                "nombre_neutro_enviado": document["nombre_neutro"],
                "paginas": document["paginas"],
                "tamano_bytes": document["tamano_bytes"],
                "sha256_pdf": document["sha256_pdf"],
                "prompt_sha256": sha256_file(PROMPT_PATH),
                "schema_sha256": sha256_file(SCHEMA_PATH),
                "modelo_solicitado": MODEL,
                "modelo_utilizado": response.model,
                "response_id": response.id,
                "estado": response.status,
                "fecha_hora_utc": utc_now(),
                "duracion_segundos": round(duration, 3),
                "reasoning_effort": REASONING,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "store": False,
                "sdk_max_retries": 0,
                "sin_reintento": True,
                "tokens": usage,
                **costs,
            }
            original_path = directory / "original.json"
            structured_path = directory / "estructurado.json"
            incidents_path = directory / "incidencias.json"
            write_json(original_path, {"metadata": metadata, "respuesta_original": response.model_dump(mode="json", exclude_none=False)})
            write_json(structured_path, {"metadata": metadata, "facturas": structured["facturas"]})
            write_json(incidents_path, [])
            metadata["hashes_salidas"] = {
                "original.json": sha256_file(original_path),
                "estructurado.json": sha256_file(structured_path),
                "incidencias.json": sha256_file(incidents_path),
            }
            write_json(directory / "metadata.json", metadata)
            accumulated_cost += costs["coste_total_usd"]
            if accumulated_cost > LIMIT_B_USD:
                raise RuntimeError("El coste acumulado de B supera el limite.")
            completed.append(metadata)
            print(json.dumps({"documento": document["documento"], "ok": True, "coste_acumulado_usd": round(accumulated_cost, 8)}), flush=True)
        except Exception as exc:
            duration = time.perf_counter() - started
            incident = sanitized_error(exc)
            write_json(directory / "incidencias.json", [incident])
            write_json(OUT / "checkpoint_fallo.json", {
                "baseline": "B",
                "fecha_hora_utc": utc_now(),
                "documento": document["documento"],
                "completados_antes_del_fallo": len(completed),
                "incidencia": incident,
                "requiere_ok_pio": True,
                "sin_reintento": True,
            })
            raise RuntimeError(f"Fallo tecnico en {document['documento']}; detenido sin reintento.") from exc
    file_hashes: dict[str, str] = {}
    for path in sorted(OUT.rglob("*.json"), key=lambda value: value.as_posix()):
        if path.name != "hito_ciego.json":
            file_hashes[path.relative_to(OUT).as_posix()] = sha256_file(path)
    hito = {
        "baseline": "B",
        "fase": "extraccion_ciega_congelada",
        "completo": True,
        "fecha_hora_utc": utc_now(),
        "modelo": MODEL,
        "pdfs_procesados": len(completed),
        "llamadas_luna": len(completed),
        "sin_reintentos": True,
        "gold_consultado_durante_extraccion": False,
        "prompt_sha256": sha256_file(PROMPT_PATH),
        "schema_sha256": sha256_file(SCHEMA_PATH),
        "response_ids_unicos": len(response_ids) == len(completed),
        "coste_total_usd": round(accumulated_cost, 8),
        "duracion_total_segundos": round(sum(item["duracion_segundos"] for item in completed), 3),
        "resultados": [
            {"documento": item["documento"], "response_id": item["response_id"], "sha256_pdf": item["sha256_pdf"]}
            for item in completed
        ],
        "hashes_archivos_json": file_hashes,
    }
    write_json(OUT / "hito_ciego.json", hito)
    write_json(OUT / "incidencias_fase_b.json", [])
    print(json.dumps({"hito_ciego_b_completo": True, "llamadas_luna": len(completed), "coste_total_usd": round(accumulated_cost, 8)}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("accion", choices=("prepare", "run"))
    args = parser.parse_args()
    if args.accion == "prepare":
        prepare()
    else:
        run()


if __name__ == "__main__":
    main()
