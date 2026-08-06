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
    / "luna_especializada_alliance_08008427"
)
NOMBRE_ORIGEN = "ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf"
NOMBRE_ENVIADO = "documento.pdf"
MODELO = "gpt-5.6-luna"
RAZONAMIENTO = "none"
MAX_OUTPUT_TOKENS = 32_000
VERSION_PROMPT = "alliance_08008427_campos_complejos_v1.0"
PRECIO_ENTRADA_USD_MILLON = 1.00
PRECIO_ENTRADA_CACHEADA_USD_MILLON = 0.10
PRECIO_SALIDA_USD_MILLON = 6.00


PROMPT_SISTEMA = """Eres un sistema de extracción documental especializado en tablas y movimientos de facturas.

Trabaja exclusivamente con el contenido visible y verificable del PDF adjunto.
No uses conocimiento externo, nombres de archivo, resultados anteriores ni reglas de negocio.
No deduzcas, calcules, completes ni inventes datos.
Si un valor no está visible, devuelve null.
No confundas:
- albaranes con líneas de producto;
- ajustes con impuestos;
- importes de vencimiento con totales generales;
- bases imponibles con importes de albarán.
Conserva literalmente números, fechas, descripciones y signos visibles.
Extrae todos los albaranes visibles en todas las páginas, sin limitar el número de elementos.
Respeta el orden en que aparecen.
Las páginas se numeran del 1 al 4 dentro del PDF adjunto.
"""

PROMPT_USUARIO = """Extrae exclusivamente vencimientos, impuestos, albaranes y ajustes visibles en esta factura. Revisa las cuatro páginas completas y devuelve todos los elementos conforme al esquema."""


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Vencimiento(Estricto):
    orden: int
    fecha_vencimiento: str | None
    importe: float | None
    pagina: int


class Impuesto(Estricto):
    orden: int
    base_imponible: float | None
    tipo_iva: float | None
    cuota_iva: float | None
    tipo_recargo_equivalencia: float | None
    cuota_recargo_equivalencia: float | None
    pagina: int


class Albaran(Estricto):
    orden: int
    numero_albaran: str | None
    fecha_albaran: str | None
    tipo_movimiento: str | None
    descripcion: str | None
    importe_base: float | None
    importe_total: float | None
    pagina: int


class Ajuste(Estricto):
    orden: int
    tipo_ajuste: str | None
    descripcion: str | None
    importe: float | None
    pagina: int


class ExtraccionEspecializada(Estricto):
    vencimientos: list[Vencimiento]
    impuestos: list[Impuesto]
    albaranes: list[Albaran]
    ajustes: list[Ajuste]


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


def costes(uso: dict[str, Any]) -> dict[str, float]:
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


def guardar_fallo(modelo: str, error: Exception, duracion: float) -> None:
    RUTA_SALIDA.mkdir(parents=True, exist_ok=True)
    cuerpo = getattr(error, "body", None)
    detalle = {
        "modelo": modelo,
        "tipo_error": type(error).__name__,
        "status_code": getattr(error, "status_code", None),
        "cuerpo_error_openai": limpiar_error(cuerpo if cuerpo is not None else {"message": str(error)}),
    }
    (RUTA_SALIDA / "original.json").write_text(
        json.dumps({"respuesta_original": None, "error": detalle}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (RUTA_SALIDA / "estructurado.json").write_text(
        json.dumps({"extraccion": None, "error": detalle}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (RUTA_SALIDA / "metricas.json").write_text(
        json.dumps(
            {
                "modelo": modelo,
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


def guardar_exito(respuesta: Any, extraccion: ExtraccionEspecializada, duracion: float) -> None:
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
        **costes(uso),
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
            {"metadatos_prueba": meta, "extraccion": extraccion.model_dump(mode="json")},
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
                        {
                            "type": "input_file",
                            "filename": NOMBRE_ENVIADO,
                            "file_data": archivo_data_url(ruta_pdf),
                        },
                    ],
                },
            ],
            text_format=ExtraccionEspecializada,
        )
    except Exception as error:
        guardar_fallo(MODELO, error, time.perf_counter() - inicio)
        print("La unica llamada fallo y no se reintentara.")
        return
    duracion = time.perf_counter() - inicio
    if respuesta.output_parsed is None:
        error = RuntimeError("La respuesta no contiene salida estructurada.")
        guardar_fallo(MODELO, error, duracion)
        print("La respuesta no fue estructurada y no se reintentara.")
        return
    guardar_exito(respuesta, respuesta.output_parsed, duracion)
    print(f"Estado: {respuesta.status}; response_id: {respuesta.id}")


def mostrar_preparacion(ruta_pdf: Path) -> None:
    print("PRUEBA CIEGA ESPECIALIZADA - ALLIANCE 08008427")
    print(f"Modelo: {MODELO}")
    print(f"PDF local verificado: {ruta_pdf.name}; paginas: {len(PdfReader(ruta_pdf).pages)}")
    print(f"Razonamiento: {RAZONAMIENTO}; max_output_tokens: {MAX_OUTPUT_TOKENS}; store=False")
    print("Una llamada, max_retries=0, sin herramientas")
    print("\nPROMPT DE SISTEMA:\n" + PROMPT_SISTEMA)
    print("PROMPT DE USUARIO:\n" + PROMPT_USUARIO)
    print("JSON SCHEMA:\n" + json.dumps(ExtraccionEspecializada.model_json_schema(), ensure_ascii=False, indent=2))
    print("Estimacion prudente: aproximadamente 0,22 USD; techo operativo recomendado: 0,25 USD.")
    print("Supuesto: unos 18.000-25.000 tokens de entrada y hasta 32.000 tokens de salida.")


def preparar(ejecutar: bool) -> None:
    clave = cargar_clave()
    with tempfile.TemporaryDirectory(prefix="alliance_luna_especializada_") as temporal:
        ruta_pdf = crear_pdf_temporal(Path(temporal))
        mostrar_preparacion(ruta_pdf)
        if not ejecutar:
            print("\nValidacion local terminada. No se ha llamado a OpenAI.")
            return
        confirmacion = input("Escribe EJECUTAR_ESPECIALIZADA para realizar una unica llamada: ")
        if confirmacion != "EJECUTAR_ESPECIALIZADA":
            print("Operacion cancelada. No se ha llamado a OpenAI.")
            return
        ejecutar_llamada(clave, ruta_pdf)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prueba ciega especializada con Luna.")
    parser.add_argument("--ejecutar-openai", action="store_true")
    argumentos = parser.parse_args()
    preparar(argumentos.ejecutar_openai)


if __name__ == "__main__":
    main()
