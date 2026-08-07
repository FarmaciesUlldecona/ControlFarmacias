"""Transcripcion literal Luna de las secciones de albaranes del caso FEDEFARMA."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict
from pypdf import PdfReader, PdfWriter

from src.facturas.motores.openai.probar_extraccion_alliance import MODELOS


RAIZ = Path(__file__).resolve().parents[4]
RUTA_PDF = RAIZ / "pruebas/facturas/documentos/FEDE VTO 5.8.26 PIO.pdf"
RUTA_SALIDA = (
    RAIZ / "pruebas/facturas/resultados/openai/fedefarma_tablas_literales"
)
MODELO = "gpt-5.6-luna"
NOMBRE_ENVIADO = "documento.pdf"
VERSION_PROMPT = "fedefarma_tablas_literales_v1.0"
RAZONAMIENTO = "none"
MAX_OUTPUT_TOKENS = 12_000


PROMPT_SISTEMA = """Eres un sistema de transcripcion documental literal.

Trabaja solo con el contenido visible del PDF adjunto. No uses conocimiento externo,
el nombre local del documento, reglas de negocio ni resultados anteriores.

Reglas obligatorias:
1. Transcribe filas; no interpretes contabilidad.
2. No conviertas fechas a ISO.
3. No calcules, completes, corrijas ni reconstruyas valores.
4. Conserva identificadores como texto, con ceros, letras, guiones y signos visibles.
5. Separa los marcadores o etiquetas que preceden al numero de su identificador.
6. Conserva importes y signos exactamente como se ven.
7. Usa null para datos ausentes.
8. Conserva el orden fisico y no dedupliques.
9. No crees filas a partir de totales o resumentes.
10. La pagina adjunta corresponde a la pagina original 2.
"""

PROMPT_USUARIO = """Transcribe todas las filas de detalle visibles en estas dos secciones:

- la tabla cuyo encabezado comienza por "Data albara" y "N Albara";
- la tabla "DETALL ABONAMENTS".

No incluyas filas de totales, bases, impuestos, vencimientos ni otros resumentes.
En la primera tabla, conserva por separado los marcadores anteriores al numero.
En la segunda, usa el valor de la columna "Abonament" como numero_albaran y conserva
las columnas de fecha de entrega, origen, fecha de albaran, motivo, descripcion e importe.
Devuelve exclusivamente la transcripcion conforme al esquema estricto.
"""


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FilaAlbaranLiteral(Estricto):
    seccion_visible: str
    orden_visual: int
    fecha_entrega: str | None
    texto_origen: str | None
    fecha_albaran: str | None
    marcadores_antes_numero: list[str]
    numero_albaran: str | None
    motivo: str | None
    descripcion: str | None
    importe: str | None
    signo_visible: str | None
    pagina_original: int


class TranscripcionAlbaranes(Estricto):
    filas: list[FilaAlbaranLiteral]


def _cargar_clave() -> str:
    load_dotenv(RAIZ / ".env")
    clave = os.getenv("OPENAI_API_KEY")
    if not clave:
        raise ValueError("Falta OPENAI_API_KEY en .env.")
    return clave


def _crear_pagina_temporal(directorio: Path) -> Path:
    if not RUTA_PDF.is_file():
        raise FileNotFoundError(f"No se encuentra el PDF de origen: {RUTA_PDF}")
    lector = PdfReader(RUTA_PDF)
    if len(lector.pages) != 2:
        raise ValueError("El documento debe contener exactamente dos paginas.")
    salida = directorio / NOMBRE_ENVIADO
    escritor = PdfWriter()
    escritor.add_page(lector.pages[1])
    with salida.open("wb") as archivo:
        escritor.write(archivo)
    return salida


def _data_url(ruta: Path) -> str:
    return "data:application/pdf;base64," + base64.b64encode(
        ruta.read_bytes()
    ).decode("ascii")


def _uso(respuesta: Any) -> dict[str, Any]:
    return (
        respuesta.usage.model_dump(mode="json", exclude_none=True)
        if respuesta.usage
        else {}
    )


def _costes(uso: dict[str, Any]) -> dict[str, float]:
    entrada = int(uso.get("input_tokens", 0))
    salida = int(uso.get("output_tokens", 0))
    cacheados = int((uso.get("input_tokens_details") or {}).get("cached_tokens", 0))
    precios = MODELOS[MODELO]
    coste_entrada = (
        max(entrada - cacheados, 0) * precios["entrada"]
        + cacheados * precios["entrada_cacheada"]
    ) / 1_000_000
    coste_salida = salida * precios["salida"] / 1_000_000
    return {
        "coste_entrada_usd": round(coste_entrada, 6),
        "coste_salida_usd": round(coste_salida, 6),
        "coste_total_usd": round(coste_entrada + coste_salida, 6),
    }


def _limpiar_error(valor: Any) -> Any:
    sensibles = {"authorization", "api_key", "apikey", "token", "access_token"}
    if isinstance(valor, dict):
        return {
            clave: "[REDACTADO]" if clave.casefold() in sensibles else _limpiar_error(dato)
            for clave, dato in valor.items()
        }
    if isinstance(valor, list):
        return [_limpiar_error(x) for x in valor]
    return valor


def _metadatos(ruta: Path) -> dict[str, Any]:
    contenido = ruta.read_bytes()
    return {
        "documento_local": RUTA_PDF.name,
        "archivo_enviado": NOMBRE_ENVIADO,
        "tipo_extraccion": "tablas_albaranes_literal",
        "paginas_originales": [2, 2],
        "paginas_enviadas": 1,
        "tamano_bytes_enviado": len(contenido),
        "sha256_enviado": hashlib.sha256(contenido).hexdigest(),
        "contenido_patron_incluido": False,
        "version_prompt": VERSION_PROMPT,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
    }


def _guardar_error(metadatos: dict[str, Any], error: Exception, duracion: float) -> None:
    RUTA_SALIDA.mkdir(parents=True, exist_ok=True)
    detalle = {
        "tipo": type(error).__name__,
        "status_code": getattr(error, "status_code", None),
        "mensaje": str(error),
        "cuerpo": _limpiar_error(getattr(error, "body", None)),
        "sin_reintento": True,
    }
    comun = {"metadatos_prueba": metadatos, "error": detalle}
    (RUTA_SALIDA / "original.json").write_text(
        json.dumps({**comun, "respuesta_original": None}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (RUTA_SALIDA / "estructurado.json").write_text(
        json.dumps({**comun, "transcripcion": None}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (RUTA_SALIDA / "metricas.json").write_text(
        json.dumps(
            {
                "modelo_solicitado": MODELO,
                "modelo_utilizado": None,
                "response_id": None,
                "estado": "failed",
                "duracion_segundos": round(duracion, 3),
                "tokens_entrada": None,
                "tokens_entrada_cacheados": None,
                "tokens_salida": None,
                "tokens_razonamiento": None,
                "coste_entrada_usd": None,
                "coste_salida_usd": None,
                "coste_total_usd": None,
                "sin_reintento": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _guardar_exito(
    metadatos: dict[str, Any],
    respuesta: Any,
    transcripcion: TranscripcionAlbaranes,
    duracion: float,
) -> None:
    RUTA_SALIDA.mkdir(parents=True, exist_ok=True)
    uso = _uso(respuesta)
    entrada_detalle = uso.get("input_tokens_details") or {}
    salida_detalle = uso.get("output_tokens_details") or {}
    meta = {
        **metadatos,
        "modelo_solicitado": MODELO,
        "modelo_utilizado": respuesta.model,
        "response_id": respuesta.id,
        "fecha_hora_utc": datetime.now(timezone.utc).isoformat(),
        "reasoning_effort": RAZONAMIENTO,
        "store": False,
    }
    (RUTA_SALIDA / "original.json").write_text(
        json.dumps(
            {
                "metadatos_prueba": meta,
                "respuesta_original": respuesta.model_dump(mode="json", exclude_none=False),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (RUTA_SALIDA / "estructurado.json").write_text(
        json.dumps(
            {
                "metadatos_prueba": meta,
                "transcripcion": transcripcion.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (RUTA_SALIDA / "metricas.json").write_text(
        json.dumps(
            {
                "modelo_solicitado": MODELO,
                "modelo_utilizado": respuesta.model,
                "response_id": respuesta.id,
                "estado": respuesta.status,
                "duracion_segundos": round(duracion, 3),
                "tokens_entrada": int(uso.get("input_tokens", 0)),
                "tokens_entrada_cacheados": int(entrada_detalle.get("cached_tokens", 0)),
                "tokens_salida": int(uso.get("output_tokens", 0)),
                "tokens_razonamiento": int(salida_detalle.get("reasoning_tokens", 0)),
                **_costes(uso),
                "sin_reintento": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def ejecutar() -> None:
    with tempfile.TemporaryDirectory(prefix="fedefarma_literal_") as temporal:
        ruta = _crear_pagina_temporal(Path(temporal))
        metadatos = _metadatos(ruta)
        cliente = OpenAI(api_key=_cargar_clave(), max_retries=0, timeout=600.0)
        inicio = time.perf_counter()
        try:
            respuesta = cliente.responses.parse(
                model=MODELO,
                reasoning={"effort": RAZONAMIENTO},
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
                input=[
                    {"role": "system", "content": PROMPT_SISTEMA},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": PROMPT_USUARIO},
                            {
                                "type": "input_file",
                                "filename": NOMBRE_ENVIADO,
                                "file_data": _data_url(ruta),
                            },
                        ],
                    },
                ],
                text_format=TranscripcionAlbaranes,
            )
            if respuesta.output_parsed is None:
                raise RuntimeError("La respuesta no contiene transcripcion estructurada.")
            _guardar_exito(
                metadatos, respuesta, respuesta.output_parsed, time.perf_counter() - inicio
            )
        except Exception as error:
            _guardar_error(metadatos, error, time.perf_counter() - inicio)
            raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ejecutar-openai", action="store_true")
    args = parser.parse_args()
    if not args.ejecutar_openai:
        print("Dry run: se usaria gpt-5.6-luna una sola vez, sin reintentos.")
        print(f"PDF: {RUTA_PDF}")
        print(f"Salida: {RUTA_SALIDA}")
        return
    ejecutar()
    print(f"Transcripcion guardada en: {RUTA_SALIDA}")


if __name__ == "__main__":
    main()
