from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import ConfigDict, BaseModel
from pypdf import PdfReader

from src.facturas.motores.openai.probar_extraccion_alliance import FacturaExtraida
from src.facturas.motores.openai.probar_extraccion_restantes_patron import PROMPT_SISTEMA


RAIZ = Path(__file__).resolve().parents[4]
FUENTE = RAIZ / "pruebas/facturas/documentos/2o_gold_standard"
SALIDA = RAIZ / "pruebas/facturas/resultados/benchmark_2o_gold_luna"
MODELO = "gpt-5.6-luna"
MAX_OUTPUT_TOKENS = 16_000
RAZONAMIENTO = "none"
PRECIO_ENTRADA = 1.00
PRECIO_ENTRADA_CACHEADA = 0.10
PRECIO_SALIDA = 6.00
LIMITE_USD = 2.00
ENTRADA_PRUDENTE_POR_PDF = 25_000
VERSION_PROMPT = "benchmark_2o_gold_luna_0_n_ciego_v1"

PROMPT_USUARIO = """Examina íntegramente el PDF adjunto y extrae conforme al esquema estricto todas las facturas o abonos que estén contenidos en él.

Devuelve una lista vacía si el contenido visible no demuestra ninguna factura o abono. No utilices el nombre del archivo como fuente de información. No presupongas ni comuniques ninguna cantidad esperada de documentos.
"""


class LoteFacturas(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facturas: list[FacturaExtraida]


@dataclass(frozen=True, slots=True)
class Documento:
    indice: int
    ruta: Path
    paginas: int
    tamano: int
    sha256: str

    @property
    def clave(self) -> str:
        return f"documento_{self.indice:02d}"

    @property
    def nombre_neutro(self) -> str:
        return self.clave + ".pdf"

    @property
    def directorio(self) -> Path:
        return SALIDA / "extracciones" / self.clave


def sha256_bytes(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def sha256_archivo(ruta: Path) -> str:
    return sha256_bytes(ruta.read_bytes())


def escribir_json(ruta: Path, valor: Any) -> None:
    ruta.write_text(json.dumps(valor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def inventariar() -> list[Documento]:
    rutas = sorted(FUENTE.glob("*.pdf"), key=lambda p: p.name.casefold())
    if len(rutas) != 14:
        raise RuntimeError(f"Se esperaban exactamente 14 PDF y se encontraron {len(rutas)}.")
    documentos: list[Documento] = []
    for indice, ruta in enumerate(rutas, 1):
        contenido = ruta.read_bytes()
        paginas = len(PdfReader(ruta).pages)
        if paginas < 1:
            raise RuntimeError(f"PDF sin páginas: {ruta}")
        documentos.append(Documento(indice, ruta, paginas, len(contenido), sha256_bytes(contenido)))
    return documentos


def coste(uso: dict[str, Any]) -> dict[str, float]:
    entrada = int(uso.get("input_tokens", 0))
    salida = int(uso.get("output_tokens", 0))
    cacheados = int((uso.get("input_tokens_details") or {}).get("cached_tokens", 0))
    coste_entrada = (max(entrada - cacheados, 0) * PRECIO_ENTRADA + cacheados * PRECIO_ENTRADA_CACHEADA) / 1_000_000
    coste_salida = salida * PRECIO_SALIDA / 1_000_000
    return {
        "coste_entrada_usd": round(coste_entrada, 6),
        "coste_salida_usd": round(coste_salida, 6),
        "coste_total_usd": round(coste_entrada + coste_salida, 6),
    }


def estimacion_previa(numero_pdf: int) -> float:
    return numero_pdf * (ENTRADA_PRUDENTE_POR_PDF * PRECIO_ENTRADA + MAX_OUTPUT_TOKENS * PRECIO_SALIDA) / 1_000_000


def data_url(ruta: Path) -> str:
    return "data:application/pdf;base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")


def limpiar_error(error: Exception) -> dict[str, Any]:
    return {
        "tipo": type(error).__name__,
        "status_code": getattr(error, "status_code", None),
        "codigo": getattr(error, "code", None),
        "mensaje": str(error),
        "sin_reintento": True,
    }


def guardar_error(documento: Documento, error: Exception, duracion: float) -> None:
    documento.directorio.mkdir(parents=True, exist_ok=False)
    incidencia = limpiar_error(error)
    escribir_json(documento.directorio / "original.json", {"respuesta_original": None, "error": incidencia})
    escribir_json(documento.directorio / "estructurado.json", {"facturas": None, "error": incidencia})
    escribir_json(documento.directorio / "metadata.json", {
        "documento": documento.clave,
        "nombre_neutro_enviado": documento.nombre_neutro,
        "modelo_solicitado": MODELO,
        "response_id": None,
        "estado": "failed",
        "duracion_segundos": round(duracion, 3),
        "sha256_pdf": documento.sha256,
        "sin_reintento": True,
    })
    escribir_json(documento.directorio / "incidencias.json", [incidencia])


def guardar_exito(documento: Documento, respuesta: Any, duracion: float) -> dict[str, Any]:
    documento.directorio.mkdir(parents=True, exist_ok=False)
    uso = respuesta.usage.model_dump(mode="json", exclude_none=True) if respuesta.usage else {}
    entrada_detalle = uso.get("input_tokens_details") or {}
    salida_detalle = uso.get("output_tokens_details") or {}
    costes = coste(uso)
    metadata = {
        "documento": documento.clave,
        "archivo_original_local": documento.ruta.name,
        "nombre_neutro_enviado": documento.nombre_neutro,
        "paginas": documento.paginas,
        "tamano_bytes": documento.tamano,
        "sha256_pdf": documento.sha256,
        "modelo_solicitado": MODELO,
        "modelo_utilizado": respuesta.model,
        "response_id": respuesta.id,
        "estado": respuesta.status,
        "fecha_hora_utc": datetime.now(timezone.utc).isoformat(),
        "duracion_segundos": round(duracion, 3),
        "version_prompt": VERSION_PROMPT,
        "reasoning_effort": RAZONAMIENTO,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": False,
        "sin_reintento": True,
        "tokens_entrada": int(uso.get("input_tokens", 0)),
        "tokens_entrada_cacheados": int(entrada_detalle.get("cached_tokens", 0)),
        "tokens_salida": int(uso.get("output_tokens", 0)),
        "tokens_razonamiento": int(salida_detalle.get("reasoning_tokens", 0)),
        **costes,
    }
    original = documento.directorio / "original.json"
    estructurado = documento.directorio / "estructurado.json"
    meta = documento.directorio / "metadata.json"
    incidencias = documento.directorio / "incidencias.json"
    escribir_json(original, {"metadata": metadata, "respuesta_original": respuesta.model_dump(mode="json", exclude_none=False)})
    escribir_json(estructurado, {"metadata": metadata, "facturas": respuesta.output_parsed.model_dump(mode="json")["facturas"]})
    escribir_json(meta, metadata)
    escribir_json(incidencias, [])
    metadata["hashes_salidas"] = {
        "original.json": sha256_archivo(original),
        "estructurado.json": sha256_archivo(estructurado),
        "incidencias.json": sha256_archivo(incidencias),
    }
    escribir_json(meta, metadata)
    metadata["hashes_salidas"]["metadata.json"] = sha256_archivo(meta)
    return metadata


def ejecutar() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY no está disponible en el proceso.")
    documentos = inventariar()
    if (SALIDA / "extracciones").exists() or (SALIDA / "hito_ciego.json").exists():
        raise RuntimeError("Existe un checkpoint de extracción; no se reinicia ni se sobrescribe.")
    estimacion = estimacion_previa(len(documentos))
    if estimacion > LIMITE_USD:
        raise RuntimeError(f"Estimación previa {estimacion:.6f} USD superior al límite {LIMITE_USD:.2f} USD.")
    fase0 = {
        "modelo": MODELO,
        "pdfs": len(documentos),
        "paginas_totales": sum(d.paginas for d in documentos),
        "llamadas_previstas": len(documentos),
        "estimacion_previa_prudente_usd": round(estimacion, 6),
        "limite_usd": LIMITE_USD,
        "reasoning_effort": RAZONAMIENTO,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "reintentos_sdk": 0,
        "store": False,
        "version_prompt": VERSION_PROMPT,
        "documentos": [{"documento": d.clave, "nombre_neutro": d.nombre_neutro, "paginas": d.paginas, "tamano_bytes": d.tamano, "sha256_pdf": d.sha256} for d in documentos],
    }
    escribir_json(SALIDA / "fase0_inventario.json", fase0)
    cliente = OpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=0, timeout=600.0)
    completados: list[dict[str, Any]] = []
    coste_acumulado = 0.0
    for posicion, documento in enumerate(documentos):
        restantes_incluido_actual = len(documentos) - posicion
        prevision = coste_acumulado + estimacion_previa(restantes_incluido_actual)
        if prevision > LIMITE_USD:
            raise RuntimeError(f"Previsión antes de {documento.clave}: {prevision:.6f} USD superior al límite.")
        inicio = time.perf_counter()
        try:
            respuesta = cliente.responses.parse(
                model=MODELO,
                reasoning={"effort": RAZONAMIENTO},
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
                input=[
                    {"role": "system", "content": PROMPT_SISTEMA},
                    {"role": "user", "content": [
                        {"type": "input_text", "text": PROMPT_USUARIO},
                        {"type": "input_file", "filename": documento.nombre_neutro, "file_data": data_url(documento.ruta)},
                    ]},
                ],
                text_format=LoteFacturas,
            )
            if respuesta.output_parsed is None or respuesta.status != "completed":
                raise RuntimeError(f"Respuesta no comparable: status={respuesta.status!r}, parsed={respuesta.output_parsed is not None}.")
            metadata = guardar_exito(documento, respuesta, time.perf_counter() - inicio)
        except Exception as error:
            if not documento.directorio.exists():
                guardar_error(documento, error, time.perf_counter() - inicio)
            raise RuntimeError(f"Fallo técnico en {documento.clave}; detenido sin reintento.") from error
        completados.append(metadata)
        coste_acumulado += metadata["coste_total_usd"]
        if coste_acumulado > LIMITE_USD:
            raise RuntimeError(f"Coste acumulado {coste_acumulado:.6f} USD superior al límite.")
        print(f"{documento.clave}: OK; response_id={metadata['response_id']}; coste_acumulado={coste_acumulado:.6f} USD", flush=True)
    hito = {
        "fase": "extraccion_ciega_congelada",
        "completo": True,
        "fecha_hora_utc": datetime.now(timezone.utc).isoformat(),
        "modelo": MODELO,
        "pdfs_procesados": len(completados),
        "llamadas_realizadas": len(completados),
        "sin_reintentos": True,
        "gold_consultado_durante_extraccion": False,
        "coste_real_estimado_usd": round(coste_acumulado, 6),
        "resultados": [{"documento": m["documento"], "response_id": m["response_id"], "sha256_pdf": m["sha256_pdf"], "hashes_salidas": m["hashes_salidas"]} for m in completados],
    }
    escribir_json(SALIDA / "hito_ciego.json", hito)
    escribir_json(SALIDA / "incidencias_fase1.json", [])
    print("HITO_CIEGO_COMPLETO", flush=True)


if __name__ == "__main__":
    ejecutar()
