from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import google.auth
from google.api_core.client_options import ClientOptions
from google.cloud import documentai
from google.protobuf.json_format import MessageToDict
from openai import OpenAI
from pypdf import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
B_DIR = OUT.parent / "benchmark_2o_gold_luna_v2"
A_DIR = OUT.parent / "benchmark_2o_gold_luna"
SOURCE = ROOT / "pruebas/facturas/documentos/2o_gold_standard"
PROMPT_PATH = B_DIR / "prompt_v2.txt"
SCHEMA_PATH = B_DIR / "schema_v2.json"
PREFLIGHT_PATH = OUT / "preflight_c.json"
TARGET_VERSION = "pretrained-splitter-v1.5-2025-07-14"
PROMPT_SHA256 = "169CDBA865E9A130FC0A5C07AB9B9AF3C1A94F980A319893DD94377EA3C8C60D"
SCHEMA_SHA256 = "BFB6D2C277A585EB75703EC6F03548B282EF927D0C5850E6E66590F0FBA1EC71"
A_HITO_SHA256 = "D2F0228CA301A06D6D24E72C0D57A095FE1B2B040B19DA13F67CEE64A2DB16F0"
MODEL = "gpt-5.6-luna"
MAX_OUTPUT_TOKENS = 24_000
MAX_SEGMENTS = 30
MAX_LUNA_CALLS = 30
LIMIT_C_USD = 3.0
GOOGLE_PRICE_PER_1000_PAGES = 5.0
PRICE_INPUT = 0.20
PRICE_CACHED = 0.02
PRICE_OUTPUT = 1.20


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_frozen_state() -> tuple[str, dict[str, Any]]:
    if sha256_file(A_DIR / "hito_ciego.json") != A_HITO_SHA256:
        raise RuntimeError("El hito aprobado de A ha cambiado.")
    if sha256_file(PROMPT_PATH) != PROMPT_SHA256:
        raise RuntimeError("El prompt V2 congelado ha cambiado.")
    if sha256_file(SCHEMA_PATH) != SCHEMA_SHA256:
        raise RuntimeError("El schema V2 congelado ha cambiado.")
    b_hito = read_json(B_DIR / "hito_ciego.json")
    if not b_hito.get("completo") or b_hito.get("llamadas_luna") != 14:
        raise RuntimeError("El hito ciego de B no esta completo.")
    preflight = read_json(PREFLIGHT_PATH)
    google_check = preflight.get("google_document_ai", {})
    if not (
        preflight.get("gold_consultado") is False
        and google_check.get("region") == "eu"
        and google_check.get("processor_id_coincide_con_aprobado") is True
        and google_check.get("version_objetivo") == TARGET_VERSION
        and google_check.get("coincidencias_version_exacta") == 1
        and google_check.get("version_estado") == "DEPLOYED"
    ):
        raise RuntimeError("El preflight aprobado de Google no es valido.")
    return PROMPT_PATH.read_text(encoding="utf-8"), read_json(SCHEMA_PATH)


def resolve_documents() -> list[dict[str, Any]]:
    expected = read_json(B_DIR / "fase0_inventario.json")["documentos"]
    candidates = [path for path in SOURCE.glob("*.pdf") if path.is_file()]
    by_hash = {sha256_file(path): path for path in candidates}
    if len(candidates) != 14 or len(by_hash) != 14 or len(expected) != 14:
        raise RuntimeError("El conjunto de PDF originales no contiene exactamente 14 elementos unicos.")
    documents = []
    for item in expected:
        digest = str(item["sha256_pdf"]).upper()
        path = by_hash.get(digest)
        if path is None:
            raise RuntimeError("Un PDF original no coincide con el inventario ciego.")
        pages = len(PdfReader(path).pages)
        if pages != int(item["paginas"]):
            raise RuntimeError("El numero de paginas de un PDF ha cambiado.")
        documents.append({
            "documento": item["documento"],
            "path": path,
            "pages": pages,
            "size": path.stat().st_size,
            "sha256": digest,
        })
    return documents


def get_google_client_and_version() -> tuple[Any, Any]:
    credentials, project = google.auth.default()
    if credentials is None or not project:
        raise RuntimeError("ADC no proporciona autenticacion y proyecto por defecto.")
    client = documentai.DocumentProcessorServiceClient(
        credentials=credentials,
        client_options=ClientOptions(api_endpoint="eu-documentai.googleapis.com"),
    )
    parent = f"projects/{project}/locations/eu"
    processors = [
        processor
        for processor in client.list_processors(parent=parent)
        if str(processor.type_) == "CUSTOM_SPLITTING_PROCESSOR"
    ]
    if len(processors) != 1:
        raise RuntimeError("No hay exactamente un Custom Splitter en EU.")
    versions = [
        version
        for version in client.list_processor_versions(parent=processors[0].name)
        if version.name.rsplit("/", 1)[-1] == TARGET_VERSION
    ]
    if len(versions) != 1 or int(versions[0].state) != 1:
        raise RuntimeError("La version exacta fijada no esta desplegada de forma unica.")
    return client, versions[0]


def page_numbers(entity: Any) -> list[int]:
    refs = list(getattr(getattr(entity, "page_anchor", None), "page_refs", ()))
    return sorted({int(ref.page) + 1 for ref in refs})


def validate_segments(entities: list[Any], total_pages: int) -> list[dict[str, Any]]:
    segments = []
    assigned: list[int] = []
    for entity in entities:
        pages = page_numbers(entity)
        if not pages or pages != list(range(pages[0], pages[-1] + 1)):
            raise RuntimeError("El Splitter devolvio un segmento sin paginas contiguas validas.")
        if pages[0] < 1 or pages[-1] > total_pages:
            raise RuntimeError("El Splitter devolvio paginas fuera del PDF.")
        assigned.extend(pages)
        segments.append({
            "pagina_inicio": pages[0],
            "pagina_fin": pages[-1],
            "paginas": pages,
            "confianza": float(entity.confidence),
        })
    if sorted(assigned) != list(range(1, total_pages + 1)) or len(assigned) != len(set(assigned)):
        raise RuntimeError("La cobertura del Splitter no asigna cada pagina exactamente una vez.")
    segments.sort(key=lambda item: item["pagina_inicio"])
    return segments


def make_segment(source: Path, pages: list[int], destination: Path) -> None:
    reader = PdfReader(source)
    writer = PdfWriter()
    for page in pages:
        writer.add_page(reader.pages[page - 1])
    writer.metadata = {}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        writer.write(output)


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
    return usage, {
        "coste_entrada_usd": round(input_cost, 8),
        "coste_salida_usd": round(output_cost, 8),
        "coste_total_usd": round(input_cost + output_cost, 8),
    }


def sanitized_error(exc: Exception) -> dict[str, Any]:
    return {
        "tipo": type(exc).__name__,
        "status_code": getattr(exc, "status_code", None),
        "codigo": getattr(exc, "code", None),
        "mensaje": str(exc),
        "sin_reintento": True,
    }


def fail(stage: str, exc: Exception, context: dict[str, Any]) -> None:
    write_json(OUT / "checkpoint_fallo.json", {
        "baseline": "C",
        "fecha_hora_utc": utc_now(),
        "etapa": stage,
        **context,
        "incidencia": sanitized_error(exc),
        "requiere_ok_pio": True,
        "sin_reintento": True,
    })


def run() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY no esta disponible.")
    forbidden = [OUT / "google", OUT / "segmentos", OUT / "extracciones", OUT / "hito_ciego.json", OUT / "checkpoint_fallo.json"]
    if any(path.exists() for path in forbidden):
        raise RuntimeError("C ya tiene artefactos de ejecucion; no se reinicia ni sobrescribe.")
    prompt, schema = verify_frozen_state()
    documents = resolve_documents()
    google_client, version = get_google_client_and_version()
    google_root = OUT / "google"
    segment_root = OUT / "segmentos"
    extraction_root = OUT / "extracciones"
    google_root.mkdir(parents=True, exist_ok=False)
    segment_root.mkdir(parents=True, exist_ok=False)
    extraction_root.mkdir(parents=True, exist_ok=False)
    google_results: list[dict[str, Any]] = []
    all_segments: list[dict[str, Any]] = []
    google_duration = 0.0
    for document in documents:
        started = time.perf_counter()
        try:
            request = documentai.ProcessRequest(
                name=version.name,
                raw_document=documentai.RawDocument(content=document["path"].read_bytes(), mime_type="application/pdf"),
            )
            response = google_client.process_document(request=request, retry=None, timeout=600.0)
            duration = time.perf_counter() - started
            google_duration += duration
            segments = validate_segments(list(response.document.entities), document["pages"])
            if len(all_segments) + len(segments) > MAX_SEGMENTS:
                raise RuntimeError("El total de segmentos supera el maximo autorizado de 30.")
            original_path = google_root / document["documento"] / "original.json"
            write_json(original_path, MessageToDict(response._pb, preserving_proto_field_name=True))
            metadata = {
                "baseline": "C",
                "documento": document["documento"],
                "region": "eu",
                "version": TARGET_VERSION,
                "processor_aprobado_verificado_sin_persistir_id": True,
                "paginas": document["pages"],
                "segmentos": segments,
                "numero_segmentos": len(segments),
                "duracion_segundos": round(duration, 3),
                "coste_google_usd": round(document["pages"] * GOOGLE_PRICE_PER_1000_PAGES / 1000, 8),
                "sin_reintento": True,
                "sha256_pdf_original": document["sha256"],
                "sha256_respuesta_original": sha256_file(original_path),
                "fecha_hora_utc": utc_now(),
            }
            write_json(google_root / document["documento"] / "metadata.json", metadata)
            write_json(google_root / document["documento"] / "incidencias.json", [])
            google_results.append(metadata)
            for local_index, segment in enumerate(segments, start=1):
                global_index = len(all_segments) + 1
                neutral = f"segmento_{global_index:02d}"
                pdf_path = segment_root / f"{neutral}.pdf"
                make_segment(document["path"], segment["paginas"], pdf_path)
                all_segments.append({
                    "segmento": neutral,
                    "documento": document["documento"],
                    "orden_en_documento": local_index,
                    **segment,
                    "pdf_path": pdf_path,
                    "sha256_pdf_segmento": sha256_file(pdf_path),
                    "tamano_bytes": pdf_path.stat().st_size,
                })
            print(json.dumps({"google_documento": document["documento"], "ok": True, "segmentos_acumulados": len(all_segments)}), flush=True)
        except Exception as exc:
            fail("google_splitter", exc, {"documento": document["documento"], "llamadas_google_completadas": len(google_results)})
            raise RuntimeError("Fallo tecnico Google; detenido sin reintento.") from exc
    if not all_segments or len(all_segments) > MAX_LUNA_CALLS:
        exc = RuntimeError("El numero de llamadas Luna requerido queda fuera del limite autorizado.")
        fail("limite_segmentos", exc, {"segmentos": len(all_segments)})
        raise exc
    write_json(OUT / "manifest_segmentos.json", {
        "baseline": "C",
        "pdfs": 14,
        "paginas": sum(item["pages"] for item in documents),
        "llamadas_google": len(google_results),
        "segmentos": [{key: value for key, value in item.items() if key != "pdf_path"} for item in all_segments],
        "cobertura_exacta_una_vez": True,
        "prompt_sha256": sha256_file(PROMPT_PATH),
        "schema_sha256": sha256_file(SCHEMA_PATH),
        "gold_consultado": False,
    })
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=0, timeout=600.0)
    luna_results: list[dict[str, Any]] = []
    response_ids: set[str] = set()
    luna_cost = 0.0
    for item in all_segments:
        if sha256_file(PROMPT_PATH) != PROMPT_SHA256 or sha256_file(SCHEMA_PATH) != SCHEMA_SHA256:
            exc = RuntimeError("El contrato V2 cambio durante C.")
            fail("contrato_v2", exc, {"llamadas_luna_completadas": len(luna_results)})
            raise exc
        started = time.perf_counter()
        directory = extraction_root / item["segmento"]
        directory.mkdir(parents=True, exist_ok=False)
        try:
            response = openai_client.responses.create(
                model=MODEL,
                reasoning={"effort": "none"},
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                    {"role": "user", "content": [
                        {"type": "input_text", "text": "Procesa el documento adjunto conforme al contrato congelado."},
                        {"type": "input_file", "filename": f"{item['segmento']}.pdf", "file_data": data_url(item["pdf_path"])},
                    ]},
                ],
                text={"format": {"type": "json_schema", "name": "lote_facturas_v2", "strict": True, "schema": schema}},
            )
            duration = time.perf_counter() - started
            if response.status != "completed" or not response.output_text:
                raise RuntimeError("Respuesta Luna incompleta o sin salida estructurada.")
            structured = json.loads(response.output_text)
            if not isinstance(structured, dict) or not isinstance(structured.get("facturas"), list):
                raise RuntimeError("La salida Luna no cumple la raiz del schema V2.")
            if response.id in response_ids:
                raise RuntimeError("response_id duplicado en C.")
            response_ids.add(response.id)
            usage, costs = usage_and_cost(response)
            projected_total = sum(meta["coste_google_usd"] for meta in google_results) + luna_cost + costs["coste_total_usd"]
            if projected_total > LIMIT_C_USD:
                raise RuntimeError("El coste acumulado de C supera 3 USD.")
            metadata = {
                "baseline": "C",
                "segmento": item["segmento"],
                "documento_origen": item["documento"],
                "pagina_inicio_original": item["pagina_inicio"],
                "pagina_fin_original": item["pagina_fin"],
                "confianza_splitter": item["confianza"],
                "nombre_neutro_enviado": f"{item['segmento']}.pdf",
                "sha256_pdf_segmento": item["sha256_pdf_segmento"],
                "prompt_sha256": sha256_file(PROMPT_PATH),
                "schema_sha256": sha256_file(SCHEMA_PATH),
                "modelo_solicitado": MODEL,
                "modelo_utilizado": response.model,
                "response_id": response.id,
                "estado": response.status,
                "duracion_segundos": round(duration, 3),
                "reasoning_effort": "none",
                "store": False,
                "sdk_max_retries": 0,
                "sin_reintento": True,
                "tokens": usage,
                **costs,
                "fecha_hora_utc": utc_now(),
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
            luna_cost += costs["coste_total_usd"]
            luna_results.append(metadata)
            print(json.dumps({"luna_segmento": item["segmento"], "ok": True, "llamadas_luna": len(luna_results), "coste_c_acumulado_usd": round(projected_total, 8)}), flush=True)
        except Exception as exc:
            write_json(directory / "incidencias.json", [sanitized_error(exc)])
            fail("luna", exc, {"segmento": item["segmento"], "llamadas_luna_completadas": len(luna_results)})
            raise RuntimeError("Fallo tecnico Luna; detenido sin reintento.") from exc
    google_cost = sum(meta["coste_google_usd"] for meta in google_results)
    file_hashes = {}
    for path in sorted(OUT.rglob("*"), key=lambda value: value.as_posix()):
        if path.is_file() and path.name != "hito_ciego.json" and path.suffix.lower() in {".json", ".pdf"}:
            file_hashes[path.relative_to(OUT).as_posix()] = sha256_file(path)
    hito = {
        "baseline": "C",
        "fase": "extraccion_ciega_congelada",
        "completo": True,
        "fecha_hora_utc": utc_now(),
        "region_google": "eu",
        "version_google": TARGET_VERSION,
        "modelo_luna": MODEL,
        "pdfs_procesados": 14,
        "paginas_procesadas": sum(item["pages"] for item in documents),
        "llamadas_google": len(google_results),
        "segmentos": len(all_segments),
        "llamadas_luna": len(luna_results),
        "sin_reintentos": True,
        "gold_consultado_durante_extraccion": False,
        "cobertura_paginas_exacta_una_vez": True,
        "prompt_sha256": sha256_file(PROMPT_PATH),
        "schema_sha256": sha256_file(SCHEMA_PATH),
        "contrato_v2_referenciado_directamente_desde_b": True,
        "response_ids_unicos": len(response_ids) == len(luna_results),
        "coste_google_usd": round(google_cost, 8),
        "coste_luna_usd": round(luna_cost, 8),
        "coste_total_usd": round(google_cost + luna_cost, 8),
        "duracion_google_segundos": round(google_duration, 3),
        "duracion_luna_segundos": round(sum(item["duracion_segundos"] for item in luna_results), 3),
        "resultados_luna": [{"segmento": item["segmento"], "response_id": item["response_id"], "sha256_pdf_segmento": item["sha256_pdf_segmento"]} for item in luna_results],
        "hashes_archivos": file_hashes,
    }
    write_json(OUT / "hito_ciego.json", hito)
    write_json(OUT / "incidencias_fase_c.json", [])
    print(json.dumps({"hito_ciego_c_completo": True, "llamadas_google": len(google_results), "segmentos": len(all_segments), "llamadas_luna": len(luna_results), "coste_total_usd": round(google_cost + luna_cost, 8)}), flush=True)


if __name__ == "__main__":
    run()
