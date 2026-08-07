from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader, PdfWriter

from src.facturas.motores.openai.probar_extraccion_alliance import (
    FacturaExtraida,
    MODELOS,
    PROMPT_SISTEMA as PROMPT_GENERAL_SISTEMA,
    PROMPT_USUARIO as PROMPT_GENERAL_USUARIO,
)
from src.facturas.motores.openai.probar_tablas_literales_alliance import (
    PROMPT_SISTEMA as PROMPT_TABLAS_SISTEMA,
    PROMPT_USUARIO as PROMPT_TABLAS_USUARIO,
    TranscripcionTablas,
)


RAIZ = Path(__file__).resolve().parents[4]
DOCUMENTOS = RAIZ / "pruebas/facturas/documentos"
SALIDA = RAIZ / "pruebas/facturas/resultados/openai/benchmark_luna_terra_sol_v1"
MODELOS_BENCHMARK = tuple(MODELOS)
VERSION_GENERAL = "benchmark_modelos_general_v1"
VERSION_TABLAS = "alliance_08008427_tablas_literales_v1.0"
MAX_TOKENS_GENERAL = 16_000
MAX_TOKENS_TABLAS = 32_000
RAZONAMIENTO = "none"
LIMITE_COSTE_TOTAL_USD = 5.0


@dataclass(frozen=True, slots=True)
class Caso:
    indice: int
    clave: str
    archivo: str
    paginas_inicio: int
    paginas_fin: int

    @property
    def nombre_neutro(self) -> str:
        return f"documento_{self.indice:02d}.pdf"


CASOS = (
    Caso(1, "alliance_08008427", "ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf", 4, 7),
    Caso(2, "farmacia_guimera", "FARMACIA GUIMERA VTO 30.6.26 PIO.pdf", 1, 1),
    Caso(3, "suavinex", "SUAVINEX VTO 15.8.26 PIO.pdf", 1, 1),
    Caso(4, "fedefarma", "FEDE VTO 5.8.26 PIO.pdf", 1, 2),
    Caso(5, "ecoceutics", "ECOCEUTICS MENSUALIDAD PIO.pdf", 1, 1),
)


def cargar_clave() -> str:
    load_dotenv(RAIZ / ".env")
    clave = os.getenv("OPENAI_API_KEY")
    if not clave:
        raise RuntimeError("OPENAI_API_KEY no esta configurada.")
    return clave


def _crear_pdf_caso(caso: Caso, temporal: Path) -> Path:
    origen = DOCUMENTOS / caso.archivo
    if not origen.is_file():
        raise FileNotFoundError(f"No se encuentra el PDF: {origen}")
    lector = PdfReader(origen)
    if caso.paginas_inicio < 1 or caso.paginas_fin > len(lector.pages):
        raise ValueError(f"Rango de paginas invalido para {caso.clave}.")
    if caso.paginas_inicio == 1 and caso.paginas_fin == len(lector.pages):
        return origen
    salida = temporal / caso.nombre_neutro
    escritor = PdfWriter()
    for indice in range(caso.paginas_inicio - 1, caso.paginas_fin):
        escritor.add_page(lector.pages[indice])
    with salida.open("wb") as archivo:
        escritor.write(archivo)
    return salida


def _data_url(ruta: Path) -> str:
    return "data:application/pdf;base64," + base64.b64encode(ruta.read_bytes()).decode("ascii")


def _metadatos(caso: Caso, ruta_pdf: Path, tipo: str) -> dict[str, Any]:
    contenido = ruta_pdf.read_bytes()
    return {
        "caso": caso.clave,
        "documento_local": caso.archivo,
        "archivo_enviado": caso.nombre_neutro,
        "tipo_extraccion": tipo,
        "paginas_originales": [caso.paginas_inicio, caso.paginas_fin],
        "paginas_enviadas": len(PdfReader(ruta_pdf).pages),
        "tamano_bytes_enviado": len(contenido),
        "sha256_enviado": hashlib.sha256(contenido).hexdigest(),
        "contenido_patron_incluido": False,
    }


def _uso(respuesta: Any) -> dict[str, Any]:
    return respuesta.usage.model_dump(mode="json", exclude_none=True) if respuesta.usage else {}


def _costes(modelo: str, uso: dict[str, Any]) -> dict[str, float]:
    entrada = int(uso.get("input_tokens", 0))
    salida = int(uso.get("output_tokens", 0))
    cacheados = int((uso.get("input_tokens_details") or {}).get("cached_tokens", 0))
    precios = MODELOS[modelo]
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
        return [_limpiar_error(elemento) for elemento in valor]
    return valor


def _guardar_error(
    directorio: Path,
    modelo: str,
    metadatos: dict[str, Any],
    error: Exception,
    duracion: float,
) -> None:
    directorio.mkdir(parents=True, exist_ok=True)
    cuerpo = getattr(error, "body", None)
    detalle = {
        "tipo": type(error).__name__,
        "status_code": getattr(error, "status_code", None),
        "mensaje": str(error),
        "cuerpo": _limpiar_error(cuerpo),
        "sin_reintento": True,
    }
    (directorio / "original.json").write_text(
        json.dumps({"metadatos_prueba": metadatos, "respuesta_original": None, "error": detalle}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (directorio / "estructurado.json").write_text(
        json.dumps({"metadatos_prueba": metadatos, "resultado": None, "error": detalle}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (directorio / "metricas.json").write_text(
        json.dumps(
            {
                "modelo_solicitado": modelo,
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
    directorio: Path,
    modelo: str,
    metadatos: dict[str, Any],
    respuesta: Any,
    resultado: Any,
    duracion: float,
    clave_resultado: str,
) -> float:
    directorio.mkdir(parents=True, exist_ok=True)
    uso = _uso(respuesta)
    entrada_detalle = uso.get("input_tokens_details") or {}
    salida_detalle = uso.get("output_tokens_details") or {}
    costes = _costes(modelo, uso)
    meta = {
        **metadatos,
        "modelo_solicitado": modelo,
        "modelo_utilizado": respuesta.model,
        "response_id": respuesta.id,
        "fecha_hora_utc": datetime.now(timezone.utc).isoformat(),
        "reasoning_effort": RAZONAMIENTO,
        "store": False,
    }
    (directorio / "original.json").write_text(
        json.dumps(
            {"metadatos_prueba": meta, "respuesta_original": respuesta.model_dump(mode="json", exclude_none=False)},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (directorio / "estructurado.json").write_text(
        json.dumps(
            {"metadatos_prueba": meta, clave_resultado: resultado.model_dump(mode="json")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (directorio / "metricas.json").write_text(
        json.dumps(
            {
                "modelo_solicitado": modelo,
                "modelo_utilizado": respuesta.model,
                "response_id": respuesta.id,
                "estado": respuesta.status,
                "duracion_segundos": round(duracion, 3),
                "tokens_entrada": int(uso.get("input_tokens", 0)),
                "tokens_entrada_cacheados": int(entrada_detalle.get("cached_tokens", 0)),
                "tokens_salida": int(uso.get("output_tokens", 0)),
                "tokens_razonamiento": int(salida_detalle.get("reasoning_tokens", 0)),
                **costes,
                "sin_reintento": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return costes["coste_total_usd"]


def _llamar_general(cliente: OpenAI, caso: Caso, ruta_pdf: Path, modelo: str) -> float:
    directorio = SALIDA / "general" / f"caso_{caso.indice:02d}" / modelo
    meta = {
        **_metadatos(caso, ruta_pdf, "general"),
        "version_prompt": VERSION_GENERAL,
        "max_output_tokens": MAX_TOKENS_GENERAL,
    }
    inicio = time.perf_counter()
    try:
        respuesta = cliente.responses.parse(
            model=modelo,
            reasoning={"effort": RAZONAMIENTO},
            max_output_tokens=MAX_TOKENS_GENERAL,
            store=False,
            input=[
                {"role": "system", "content": PROMPT_GENERAL_SISTEMA},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": PROMPT_GENERAL_USUARIO},
                        {"type": "input_file", "filename": caso.nombre_neutro, "file_data": _data_url(ruta_pdf)},
                    ],
                },
            ],
            text_format=FacturaExtraida,
        )
        if respuesta.output_parsed is None:
            raise RuntimeError("La respuesta no contiene salida estructurada.")
        return _guardar_exito(
            directorio, modelo, meta, respuesta, respuesta.output_parsed,
            time.perf_counter() - inicio, "factura",
        )
    except Exception as error:
        _guardar_error(directorio, modelo, meta, error, time.perf_counter() - inicio)
        print(f"GENERAL {caso.clave} {modelo}: ERROR, sin reintento")
        return 0.0


def _llamar_tablas(cliente: OpenAI, caso: Caso, ruta_pdf: Path, modelo: str) -> float:
    directorio = SALIDA / "alliance_tablas" / modelo
    meta = {
        **_metadatos(caso, ruta_pdf, "tablas_literales"),
        "archivo_enviado": "documento.pdf",
        "version_prompt": VERSION_TABLAS,
        "max_output_tokens": MAX_TOKENS_TABLAS,
    }
    inicio = time.perf_counter()
    try:
        respuesta = cliente.responses.parse(
            model=modelo,
            reasoning={"effort": RAZONAMIENTO},
            max_output_tokens=MAX_TOKENS_TABLAS,
            store=False,
            input=[
                {"role": "system", "content": PROMPT_TABLAS_SISTEMA},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": PROMPT_TABLAS_USUARIO},
                        {"type": "input_file", "filename": "documento.pdf", "file_data": _data_url(ruta_pdf)},
                    ],
                },
            ],
            text_format=TranscripcionTablas,
        )
        if respuesta.output_parsed is None:
            raise RuntimeError("La respuesta no contiene salida estructurada.")
        return _guardar_exito(
            directorio, modelo, meta, respuesta, respuesta.output_parsed,
            time.perf_counter() - inicio, "transcripcion",
        )
    except Exception as error:
        _guardar_error(directorio, modelo, meta, error, time.perf_counter() - inicio)
        print(f"TABLAS {modelo}: ERROR, sin reintento")
        return 0.0


def _reutilizar_luna_tablas() -> None:
    origen = RAIZ / "pruebas/facturas/resultados/openai/luna_tablas_literales_alliance_08008427"
    destino = SALIDA / "alliance_tablas/gpt-5.6-luna"
    if destino.exists():
        raise RuntimeError(f"El destino reutilizado ya existe: {destino}")
    destino.mkdir(parents=True)
    for nombre in ("original.json", "estructurado.json", "metricas.json"):
        (destino / nombre).write_bytes((origen / nombre).read_bytes())
    (destino / "reutilizacion.json").write_text(
        json.dumps(
            {
                "reutilizado": True,
                "motivo": "Mismo prompt, esquema, modelo, reasoning, max_output_tokens y nombre neutro.",
                "llamada_nueva": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def preparar() -> None:
    print("BENCHMARK CONTROLADO LUNA / TERRA / SOL")
    print("Modelos exactos: " + ", ".join(MODELOS_BENCHMARK))
    print(f"Casos generales: {len(CASOS)} x 3 = {len(CASOS) * 3} llamadas")
    print("Alliance tablas: Terra y Sol = 2 llamadas nuevas; Luna reutilizada")
    print("Total llamadas nuevas: 17; resultados evaluables previstos: 18")
    print(f"Reasoning: {RAZONAMIENTO}; store=False; reintentos SDK=0")
    for caso in CASOS:
        ruta = DOCUMENTOS / caso.archivo
        print(f"{caso.indice}. {caso.clave}: paginas {caso.paginas_inicio}-{caso.paginas_fin}; enviado como {caso.nombre_neutro}; existe={ruta.is_file()}")


def ejecutar() -> None:
    clave = cargar_clave()
    cliente = OpenAI(api_key=clave, max_retries=0, timeout=600.0)
    SALIDA.mkdir(parents=True, exist_ok=True)
    _reutilizar_luna_tablas()
    coste_acumulado = 0.0
    with tempfile.TemporaryDirectory(prefix="benchmark_facturas_") as directorio:
        temporal = Path(directorio)
        rutas = {caso.clave: _crear_pdf_caso(caso, temporal) for caso in CASOS}
        for caso in CASOS:
            for modelo in MODELOS_BENCHMARK:
                if coste_acumulado > LIMITE_COSTE_TOTAL_USD:
                    raise RuntimeError("El coste acumulado supera el limite de seguridad.")
                coste = _llamar_general(cliente, caso, rutas[caso.clave], modelo)
                coste_acumulado += coste
                print(f"GENERAL {caso.clave} {modelo}: coste={coste:.6f}; acumulado={coste_acumulado:.6f}")
        alliance = CASOS[0]
        for modelo in ("gpt-5.6-terra", "gpt-5.6-sol"):
            if coste_acumulado > LIMITE_COSTE_TOTAL_USD:
                raise RuntimeError("El coste acumulado supera el limite de seguridad.")
            coste = _llamar_tablas(cliente, alliance, rutas[alliance.clave], modelo)
            coste_acumulado += coste
            print(f"TABLAS {modelo}: coste={coste:.6f}; acumulado={coste_acumulado:.6f}")
    (SALIDA / "ejecucion.json").write_text(
        json.dumps(
            {
                "modelos": list(MODELOS_BENCHMARK),
                "llamadas_nuevas_previstas": 17,
                "resultados_reutilizados": 1,
                "coste_nuevas_llamadas_usd": round(coste_acumulado, 6),
                "fecha_fin_utc": datetime.now(timezone.utc).isoformat(),
                "sin_reintentos": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ejecutar-openai", action="store_true")
    argumentos = parser.parse_args()
    preparar()
    if not argumentos.ejecutar_openai:
        print("Preparacion local terminada; no se realizaron llamadas.")
        return
    ejecutar()


if __name__ == "__main__":
    main()
