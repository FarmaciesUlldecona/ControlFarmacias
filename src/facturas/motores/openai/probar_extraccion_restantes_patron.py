from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

from src.facturas.motores.openai.probar_extraccion_alliance import FacturaExtraida


RUTA_PROYECTO = Path(__file__).resolve().parents[4]
RUTA_DOCUMENTOS = RUTA_PROYECTO / "pruebas/facturas/documentos"
RUTA_SALIDA = RUTA_PROYECTO / "pruebas/facturas/resultados/openai/muestra_completa"
PDF_EXCLUIDO = "ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf"
MODELO = "gpt-5.6-luna"
VERSION_PROMPT = "muestra_completa_ciega_v1.0"
MAX_OUTPUT_TOKENS = 16_000
PRECIO_ENTRADA = 1.00
PRECIO_ENTRADA_CACHEADA = 0.10
PRECIO_SALIDA = 6.00
LIMITE_ESTIMACION = 1.50
LIMITE_ACUMULADO = 1.00


PROMPT_SISTEMA = """Eres un sistema de extracción documental de facturas.

Trabaja exclusivamente con el contenido visible y verificable del PDF adjunto.
No uses conocimiento externo, búsquedas, herramientas, datos históricos, nombres de archivo ni hábitos del proveedor.
No deduzcas, completes, inventes ni corrijas datos que no estén visibles.
Si un dato no está visible o no es verificable, devuelve null o una lista vacía según el esquema.
No calcules fechas, vencimientos, bases, impuestos, cuotas, recargos, totales ni diferencias.
No confundas emisor o proveedor con destinatario o cliente.
No confundas importes de líneas, albaranes o vencimientos con totales de factura.
Conserva literalmente números de factura, CIF/NIF, números de albarán y signos visibles.
Identifica un documento como ABONO únicamente cuando el propio documento lo indique.
No cambies el signo de un abono si el signo negativo no aparece en el documento.

Las páginas se numeran desde 1 dentro del PDF adjunto.
Para cada valor extraído incluye evidencia textual breve y página.
La evidencia debe ser una transcripción visible, no una explicación.
Si un valor es null, su lista de evidencias debe estar vacía.
Las fechas inequívocas se devuelven como YYYY-MM-DD, conservando en la evidencia la grafía original.
Los porcentajes e importes se devuelven como números sin símbolos ni separadores de miles.
No añadas campos fuera del esquema.
"""

PROMPT_USUARIO = """Extrae la única factura o abono contenido en el PDF adjunto conforme al esquema estricto.

Revisa todas sus páginas y devuelve exclusivamente información visible y verificable. No utilices el nombre del archivo como fuente de información.
"""


@dataclass(frozen=True, slots=True)
class Documento:
    indice: int
    ruta: Path
    paginas: int
    tamano: int
    sha256: str

    @property
    def nombre_neutro(self) -> str:
        return f"documento_{self.indice:02d}.pdf"

    @property
    def directorio_salida(self) -> Path:
        return RUTA_SALIDA / f"documento_{self.indice:02d}"


def inventariar() -> list[Documento]:
    rutas = sorted(
        (ruta for ruta in RUTA_DOCUMENTOS.glob("*.pdf") if ruta.name != PDF_EXCLUIDO),
        key=lambda ruta: ruta.name.casefold(),
    )
    if len(rutas) != 7:
        raise RuntimeError(f"Se esperaban exactamente 7 PDF restantes y se encontraron {len(rutas)}.")
    documentos = []
    for indice, ruta in enumerate(rutas, start=1):
        contenido = ruta.read_bytes()
        paginas = len(PdfReader(ruta).pages)
        if paginas < 1:
            raise RuntimeError(f"El PDF no tiene páginas: {ruta}")
        documentos.append(
            Documento(indice, ruta, paginas, len(contenido), hashlib.sha256(contenido).hexdigest())
        )
    return documentos


def cargar_clave() -> str:
    load_dotenv(RUTA_PROYECTO / ".env")
    clave = os.getenv("OPENAI_API_KEY")
    if not clave:
        raise RuntimeError("OPENAI_API_KEY no está configurada.")
    return clave


def data_url(ruta: Path) -> str:
    return "data:application/pdf;base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")


def coste_desde_uso(uso: dict[str, Any]) -> dict[str, float]:
    entrada = int(uso.get("input_tokens", 0))
    salida = int(uso.get("output_tokens", 0))
    cacheados = int((uso.get("input_tokens_details") or {}).get("cached_tokens", 0))
    coste_entrada = (
        max(entrada - cacheados, 0) * PRECIO_ENTRADA
        + cacheados * PRECIO_ENTRADA_CACHEADA
    ) / 1_000_000
    coste_salida = salida * PRECIO_SALIDA / 1_000_000
    return {
        "coste_entrada": round(coste_entrada, 6),
        "coste_salida": round(coste_salida, 6),
        "coste_total": round(coste_entrada + coste_salida, 6),
    }


def metadatos_entrada(documento: Documento) -> dict[str, Any]:
    return {
        "indice": documento.indice,
        "archivo_original_local": documento.ruta.name,
        "nombre_neutro_enviado": documento.nombre_neutro,
        "numero_paginas": documento.paginas,
        "tamano_bytes": documento.tamano,
        "sha256": documento.sha256,
        "contenido_patron_incluido": False,
    }


def guardar_error(documento: Documento, error: Exception, duracion: float) -> None:
    salida = documento.directorio_salida
    salida.mkdir(parents=True, exist_ok=True)
    cuerpo = getattr(error, "body", None)
    seguro = cuerpo if isinstance(cuerpo, (dict, list, str, int, float, bool)) else None
    error_json = {
        "tipo": type(error).__name__,
        "status_code": getattr(error, "status_code", None),
        "mensaje": str(error),
        "cuerpo": seguro,
        "sin_reintento": True,
    }
    (salida / "original.json").write_text(
        json.dumps({"respuesta_original": None, "error": error_json}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (salida / "estructurado.json").write_text(
        json.dumps({"factura": None, "error": error_json}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (salida / "metricas.json").write_text(
        json.dumps({
            "modelo": MODELO, "response_id": None, "estado": "failed",
            "duracion_segundos": round(duracion, 3), "tokens_entrada": 0,
            "tokens_entrada_cacheados": 0, "tokens_salida": 0,
            "tokens_razonamiento": 0, "coste_entrada": 0.0,
            "coste_salida": 0.0, "coste_total": 0.0,
            "fecha_hora_utc": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (salida / "metadatos_entrada.json").write_text(
        json.dumps(metadatos_entrada(documento), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def guardar_exito(documento: Documento, respuesta: Any, duracion: float) -> float:
    salida = documento.directorio_salida
    salida.mkdir(parents=True, exist_ok=True)
    uso = respuesta.usage.model_dump(mode="json", exclude_none=True) if respuesta.usage else {}
    costes = coste_desde_uso(uso)
    entrada_detalle = uso.get("input_tokens_details") or {}
    salida_detalle = uso.get("output_tokens_details") or {}
    meta = {
        **metadatos_entrada(documento), "modelo": respuesta.model,
        "response_id": respuesta.id, "version_prompt": VERSION_PROMPT,
        "max_output_tokens": MAX_OUTPUT_TOKENS, "reasoning_effort": "none", "store": False,
    }
    (salida / "original.json").write_text(json.dumps({
        "metadatos_prueba": meta,
        "respuesta_original": respuesta.model_dump(mode="json", exclude_none=False),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (salida / "estructurado.json").write_text(json.dumps({
        "metadatos_prueba": meta, "factura": respuesta.output_parsed.model_dump(mode="json"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (salida / "metricas.json").write_text(json.dumps({
        "modelo": respuesta.model, "response_id": respuesta.id, "estado": respuesta.status,
        "duracion_segundos": round(duracion, 3), "tokens_entrada": int(uso.get("input_tokens", 0)),
        "tokens_entrada_cacheados": int(entrada_detalle.get("cached_tokens", 0)),
        "tokens_salida": int(uso.get("output_tokens", 0)),
        "tokens_razonamiento": int(salida_detalle.get("reasoning_tokens", 0)),
        **costes, "fecha_hora_utc": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (salida / "metadatos_entrada.json").write_text(
        json.dumps(metadatos_entrada(documento), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return costes["coste_total"]


def ejecutar(documentos: list[Documento], clave: str) -> None:
    cliente = OpenAI(api_key=clave, max_retries=0, timeout=300.0)
    acumulado = 0.0
    for documento in documentos:
        if acumulado > LIMITE_ACUMULADO:
            print(f"PARADA: coste acumulado {acumulado:.6f} USD superior a {LIMITE_ACUMULADO:.2f} USD.")
            break
        inicio = time.perf_counter()
        try:
            respuesta = cliente.responses.parse(
                model=MODELO,
                reasoning={"effort": "none"},
                max_output_tokens=MAX_OUTPUT_TOKENS,
                store=False,
                input=[
                    {"role": "system", "content": PROMPT_SISTEMA},
                    {"role": "user", "content": [
                        {"type": "input_text", "text": PROMPT_USUARIO},
                        {"type": "input_file", "filename": documento.nombre_neutro, "file_data": data_url(documento.ruta)},
                    ]},
                ],
                text_format=FacturaExtraida,
            )
            duracion = time.perf_counter() - inicio
            if respuesta.output_parsed is None:
                raise RuntimeError("La respuesta no contiene salida estructurada.")
            coste = guardar_exito(documento, respuesta, duracion)
            acumulado += coste
            print(f"documento_{documento.indice:02d}: OK; coste={coste:.6f} USD; acumulado={acumulado:.6f} USD")
        except Exception as error:
            duracion = time.perf_counter() - inicio
            guardar_error(documento, error, duracion)
            print(f"documento_{documento.indice:02d}: ERROR {type(error).__name__}; no se reintenta")


def mostrar_preparacion(documentos: list[Documento]) -> float:
    estimacion = len(documentos) * (25_000 * PRECIO_ENTRADA + MAX_OUTPUT_TOKENS * PRECIO_SALIDA) / 1_000_000
    print("INVENTARIO TÉCNICO")
    for documento in documentos:
        print(f"{documento.indice}: {documento.ruta.name} | {documento.tamano} bytes | "
              f"{documento.paginas} páginas | SHA-256 {documento.sha256} | enviado como {documento.nombre_neutro}")
    print(f"Llamadas exactas: {len(documentos)}")
    print(f"Estimación prudente: {estimacion:.6f} USD")
    print(f"Límite de salida por documento: {MAX_OUTPUT_TOKENS} tokens")
    print("Esquema: " + ", ".join(FacturaExtraida.model_json_schema()["properties"].keys()))
    return estimacion


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ejecutar-openai", action="store_true")
    args = parser.parse_args()
    documentos = inventariar()
    estimacion = mostrar_preparacion(documentos)
    clave = cargar_clave()
    print("OPENAI_API_KEY: configurada (valor oculto)")
    if estimacion > LIMITE_ESTIMACION:
        raise RuntimeError("La estimación supera el límite autorizado.")
    if not args.ejecutar_openai:
        print("Validación local terminada; no se realizaron llamadas.")
        return
    ejecutar(documentos, clave)


if __name__ == "__main__":
    main()
