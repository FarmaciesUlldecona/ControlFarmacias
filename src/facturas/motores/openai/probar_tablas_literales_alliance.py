from __future__ import annotations

import argparse
import base64
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


RUTA_PROYECTO = Path(__file__).resolve().parents[4]
RUTA_DOCUMENTOS = RUTA_PROYECTO / "pruebas" / "facturas" / "documentos"
RUTA_SALIDA = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "resultados"
    / "openai"
    / "luna_tablas_literales_alliance_08008427"
)
NOMBRE_ORIGEN = "ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf"
NOMBRE_ENVIADO = "documento.pdf"
MODELO = "gpt-5.6-luna"
RAZONAMIENTO = "none"
MAX_OUTPUT_TOKENS = 32_000
VERSION_PROMPT = "alliance_08008427_tablas_literales_v1.0"
PRECIO_ENTRADA_USD_MILLON = 1.00
PRECIO_ENTRADA_CACHEADA_USD_MILLON = 0.10
PRECIO_SALIDA_USD_MILLON = 6.00


PROMPT_SISTEMA = """Eres un sistema de transcripción documental especializado en tablas y bloques visibles de facturas.

Trabaja exclusivamente con el contenido visible y verificable del PDF adjunto.
No uses conocimiento externo, nombres de archivo, resultados anteriores ni reglas de negocio.
Tu tarea es transcribir la estructura visible, no interpretarla ni convertirla al modelo final de una factura.

Reglas obligatorias:
1. Transcribe literalmente el texto de las celdas.
2. No conviertas fechas a formato ISO.
3. No conviertas descripciones en tipos de movimiento.
4. No decidas si una fila es cargo, abono, impuesto o ajuste.
5. No calcules importes.
6. No cambies signos, separadores decimales ni separadores de miles.
7. No reordenes filas.
8. Conserva el orden físico exacto en que aparecen.
9. Incluye todas las filas visibles de todas las páginas.
10. No crees una fila si no está visible.
11. No agrupes filas similares.
12. No completes columnas vacías; usa una cadena vacía para conservar una celda visible vacía cuando sea necesario mantener la estructura de columnas.
13. Si un bloque o lista no tiene información visible, devuelve una lista vacía.
14. No incluyas campos del modelo definitivo de factura.
15. Cada elemento de encabezados y celdas debe contener únicamente su texto visible, sin explicaciones.
16. Las páginas se numeran del 1 al 4 dentro del PDF adjunto.
"""

PROMPT_USUARIO = """Transcribe exclusivamente los bloques de vencimiento, las tablas visibles completas, los textos de posibles ajustes y los textos fiscales visibles de esta factura.

Revisa las cuatro páginas completas. Conserva literalmente encabezados, celdas, signos, fechas, importes y el orden físico de todas las filas conforme al esquema estricto."""


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BloqueVencimiento(Estricto):
    texto_fecha: str | None
    texto_importe: str | None
    pagina: int


class FilaTabla(Estricto):
    orden_visual: int
    celdas: list[str]


class TablaVisible(Estricto):
    pagina: int
    titulo_visible: str | None
    encabezados: list[str]
    filas: list[FilaTabla]


class TextoVisible(Estricto):
    texto_visible: str
    pagina: int


class TranscripcionTablas(Estricto):
    bloques_vencimiento: list[BloqueVencimiento]
    tablas: list[TablaVisible]
    textos_ajustes: list[TextoVisible]
    textos_fiscales: list[TextoVisible]


def cargar_clave() -> str:
    load_dotenv(RUTA_PROYECTO / ".env")
    clave = os.getenv("OPENAI_API_KEY")
    if not clave:
        raise ValueError("Falta OPENAI_API_KEY en .env.")
    return clave


def crear_pdf_temporal(directorio: Path) -> Path:
    origen = RUTA_DOCUMENTOS / NOMBRE_ORIGEN
    if not origen.is_file():
        raise FileNotFoundError(f"No se encuentra el PDF de origen: {origen}")
    lector = PdfReader(origen)
    if len(lector.pages) != 11:
        raise ValueError(f"El PDF de origen debe tener 11 paginas; tiene {len(lector.pages)}.")
    salida = directorio / "ALLIANCE_documento_02_paginas_4_7.pdf"
    escritor = PdfWriter()
    for indice in range(3, 7):
        escritor.add_page(lector.pages[indice])
    with salida.open("wb") as archivo:
        escritor.write(archivo)
    if len(PdfReader(salida).pages) != 4:
        raise RuntimeError("El PDF temporal no contiene exactamente cuatro paginas.")
    return salida


def archivo_data_url(ruta: Path) -> str:
    return "data:application/pdf;base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")


def uso_dict(respuesta: Any) -> dict[str, Any]:
    if respuesta.usage is None:
        return {}
    return respuesta.usage.model_dump(mode="json", exclude_none=True)


def calcular_costes(uso: dict[str, Any]) -> dict[str, float]:
    entrada = int(uso.get("input_tokens", 0))
    salida = int(uso.get("output_tokens", 0))
    cacheados = int((uso.get("input_tokens_details") or {}).get("cached_tokens", 0))
    coste_entrada = (
        max(entrada - cacheados, 0) * PRECIO_ENTRADA_USD_MILLON
        + cacheados * PRECIO_ENTRADA_CACHEADA_USD_MILLON
    ) / 1_000_000
    coste_salida = salida * PRECIO_SALIDA_USD_MILLON / 1_000_000
    return {
        "coste_entrada_usd": round(coste_entrada, 6),
        "coste_salida_usd": round(coste_salida, 6),
        "coste_total_estimado_usd": round(coste_entrada + coste_salida, 6),
    }


def limpiar_error(valor: Any) -> Any:
    sensibles = {"authorization", "api_key", "apikey", "token", "access_token"}
    if isinstance(valor, dict):
        return {
            clave: "[REDACTADO]" if clave.lower() in sensibles else limpiar_error(dato)
            for clave, dato in valor.items()
        }
    if isinstance(valor, list):
        return [limpiar_error(elemento) for elemento in valor]
    return valor


def guardar_fallo(error: Exception, duracion: float) -> None:
    RUTA_SALIDA.mkdir(parents=True, exist_ok=True)
    cuerpo = getattr(error, "body", None)
    detalle = {
        "modelo": MODELO,
        "tipo_error": type(error).__name__,
        "status_code": getattr(error, "status_code", None),
        "cuerpo_error_openai": limpiar_error(cuerpo if cuerpo is not None else {"message": str(error)}),
    }
    (RUTA_SALIDA / "original.json").write_text(
        json.dumps({"respuesta_original": None, "error": detalle}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (RUTA_SALIDA / "estructurado.json").write_text(
        json.dumps({"transcripcion": None, "error": detalle}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (RUTA_SALIDA / "metricas.json").write_text(
        json.dumps(
            {
                "modelo": MODELO,
                "response_id": None,
                "tokens_entrada": 0,
                "tokens_entrada_cacheados": 0,
                "tokens_salida": 0,
                "tokens_razonamiento": 0,
                "coste_entrada_usd": 0.0,
                "coste_salida_usd": 0.0,
                "coste_total_estimado_usd": 0.0,
                "duracion_segundos": round(duracion, 3),
                "estado_final": "failed",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def guardar_exito(respuesta: Any, transcripcion: TranscripcionTablas, duracion: float) -> None:
    RUTA_SALIDA.mkdir(parents=True, exist_ok=True)
    uso = uso_dict(respuesta)
    entrada_detalle = uso.get("input_tokens_details") or {}
    salida_detalle = uso.get("output_tokens_details") or {}
    meta = {
        "archivo_enviado": NOMBRE_ENVIADO,
        "paginas_pdf": 4,
        "modelo_solicitado": MODELO,
        "modelo_utilizado": respuesta.model,
        "response_id": respuesta.id,
        "fecha_hora_utc": datetime.now(timezone.utc).isoformat(),
        "version_prompt": VERSION_PROMPT,
        "reasoning_effort": RAZONAMIENTO,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": False,
    }
    metricas = {
        "modelo": respuesta.model,
        "response_id": respuesta.id,
        "tokens_entrada": int(uso.get("input_tokens", 0)),
        "tokens_entrada_cacheados": int(entrada_detalle.get("cached_tokens", 0)),
        "tokens_salida": int(uso.get("output_tokens", 0)),
        "tokens_razonamiento": int(salida_detalle.get("reasoning_tokens", 0)),
        **calcular_costes(uso),
        "duracion_segundos": round(duracion, 3),
        "estado_final": respuesta.status,
    }
    (RUTA_SALIDA / "original.json").write_text(
        json.dumps(
            {"metadatos_prueba": meta, "respuesta_original": respuesta.model_dump(mode="json", exclude_none=False)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (RUTA_SALIDA / "estructurado.json").write_text(
        json.dumps(
            {"metadatos_prueba": meta, "transcripcion": transcripcion.model_dump(mode="json")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (RUTA_SALIDA / "metricas.json").write_text(
        json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def ejecutar_llamada(clave: str, ruta_pdf: Path) -> None:
    cliente = OpenAI(api_key=clave, max_retries=0, timeout=600.0)
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
                        {"type": "input_file", "filename": NOMBRE_ENVIADO, "file_data": archivo_data_url(ruta_pdf)},
                    ],
                },
            ],
            text_format=TranscripcionTablas,
        )
    except Exception as error:
        guardar_fallo(error, time.perf_counter() - inicio)
        print("La unica llamada fallo y no se reintentara.")
        return
    duracion = time.perf_counter() - inicio
    if respuesta.output_parsed is None:
        guardar_fallo(RuntimeError("La respuesta no contiene salida estructurada."), duracion)
        print("La respuesta no fue estructurada y no se reintentara.")
        return
    guardar_exito(respuesta, respuesta.output_parsed, duracion)
    print(f"Estado: {respuesta.status}; response_id: {respuesta.id}")


def mostrar_preparacion(ruta_pdf: Path) -> None:
    print("PRUEBA CIEGA DE TABLAS LITERALES - ALLIANCE 08008427")
    print(f"Modelo: {MODELO}")
    print(f"PDF verificado: {ruta_pdf.name}; paginas: {len(PdfReader(ruta_pdf).pages)}")
    print(f"Razonamiento: {RAZONAMIENTO}; max_output_tokens: {MAX_OUTPUT_TOKENS}; store=False")
    print("Una llamada, max_retries=0, sin herramientas")
    print("\nPROMPT DE SISTEMA COMPLETO:\n" + PROMPT_SISTEMA)
    print("PROMPT DE USUARIO COMPLETO:\n" + PROMPT_USUARIO)
    print("JSON SCHEMA COMPLETO:\n" + json.dumps(TranscripcionTablas.model_json_schema(), ensure_ascii=False, indent=2))
    print("Estimacion: 17.000-25.000 tokens de entrada y 10.000-20.000 de salida.")
    print("Coste esperado: 0,08-0,15 USD; techo prudente con 32.000 de salida: 0,22 USD.")


def preparar(ejecutar: bool) -> None:
    clave = cargar_clave()
    with tempfile.TemporaryDirectory(prefix="alliance_luna_tablas_literales_") as temporal:
        ruta_pdf = crear_pdf_temporal(Path(temporal))
        mostrar_preparacion(ruta_pdf)
        if not ejecutar:
            print("\nValidacion local terminada. No se ha llamado a OpenAI.")
            return
        confirmacion = input("Escribe EJECUTAR_TABLAS para realizar una unica llamada: ")
        if confirmacion != "EJECUTAR_TABLAS":
            print("Operacion cancelada. No se ha llamado a OpenAI.")
            return
        ejecutar_llamada(clave, ruta_pdf)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prueba ciega de tablas literales con Luna.")
    parser.add_argument("--ejecutar-openai", action="store_true")
    argumentos = parser.parse_args()
    preparar(argumentos.ejecutar_openai)


if __name__ == "__main__":
    main()
