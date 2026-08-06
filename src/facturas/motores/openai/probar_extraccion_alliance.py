from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict
from pypdf import PdfReader, PdfWriter


RUTA_PROYECTO = Path(__file__).resolve().parents[4]
RUTA_DOCUMENTOS = RUTA_PROYECTO / "pruebas" / "facturas" / "documentos"
RUTA_RESULTADOS = RUTA_PROYECTO / "pruebas" / "facturas" / "resultados" / "openai"
RUTA_COMPARATIVA = RUTA_RESULTADOS / "comparativa_modelos"
NOMBRE_PDF = "ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf"
VERSION_PROMPT = "alliance_comparativa_modelos_ciega_v1.0"
MAX_OUTPUT_TOKENS = 16_000
RAZONAMIENTO = "none"
MODELOS = {
    "gpt-5.6-luna": {"entrada": 1.00, "entrada_cacheada": 0.10, "salida": 6.00},
    "gpt-5.6-terra": {"entrada": 2.50, "entrada_cacheada": 0.25, "salida": 15.00},
    "gpt-5.6-sol": {"entrada": 5.00, "entrada_cacheada": 0.50, "salida": 30.00},
}


PROMPT_SISTEMA = """Eres un sistema de extracción documental de facturas.

Trabaja exclusivamente con el contenido visible y verificable del PDF adjunto.
No uses conocimiento externo, búsquedas, herramientas, datos históricos, nombres de archivo ni hábitos del proveedor.
No deduzcas, completes, inventes ni corrijas datos que no estén visibles.
Si un dato no está visible o no es verificable, devuelve null o una lista vacía según el esquema.
No calcules fechas, vencimientos, bases, impuestos, cuotas, recargos, totales ni diferencias.
No confundas emisor/proveedor con destinatario/cliente.
No confundas importes de líneas, albaranes o vencimientos con totales de factura.
Conserva literalmente números de factura, CIF/NIF, números de albarán y signos de los importes.
Identifica un documento de devolución como ABONO únicamente si el propio documento lo indica.
No cambies el signo de un abono si el signo no aparece así en el documento.

Las páginas de la evidencia se numeran desde 1 dentro del PDF adjunto.
Para cada valor extraído incluye todas las evidencias visibles relevantes mediante texto_visible y pagina.
texto_visible debe ser una transcripción breve y literal; no una explicación.
Si valor es null, evidencias debe ser una lista vacía.
Para fechas inequívocas, valor debe usar YYYY-MM-DD y texto_visible debe conservar la grafía del documento.
Los porcentajes y cantidades monetarias se devuelven como números, sin símbolos ni separadores de miles.
Los campos orden solo expresan el orden visible de los elementos, empezando en 1; no inventes elementos ausentes.
No añadas campos fuera del esquema.
"""

PROMPT_USUARIO = """Extrae una única factura del PDF adjunto conforme al esquema estricto.

Revisa todas sus páginas y devuelve solamente los datos visibles y verificables. El archivo adjunto ya contiene exclusivamente las páginas de una factura; no uses su nombre como fuente de información.
"""


class ModeloEstricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidencia(ModeloEstricto):
    texto_visible: str
    pagina: int


class CampoTexto(ModeloEstricto):
    valor: str | None
    evidencias: list[Evidencia]


class CampoNumero(ModeloEstricto):
    valor: float | None
    evidencias: list[Evidencia]


class CampoEntero(ModeloEstricto):
    valor: int | None
    evidencias: list[Evidencia]


class CampoBooleano(ModeloEstricto):
    valor: bool | None
    evidencias: list[Evidencia]


class TipoDocumento(str, Enum):
    FACTURA = "FACTURA"
    ABONO = "ABONO"
    OTRO = "OTRO"


class Categoria(str, Enum):
    MERCANCIA = "MERCANCIA"
    SUMINISTRO = "SUMINISTRO"
    CUOTA_SERVICIO = "CUOTA_SERVICIO"
    OTRA = "OTRA"


class CampoTipoDocumento(ModeloEstricto):
    valor: TipoDocumento | None
    evidencias: list[Evidencia]


class CampoCategoria(ModeloEstricto):
    valor: Categoria | None
    evidencias: list[Evidencia]


class Vencimiento(ModeloEstricto):
    orden: CampoEntero
    fecha_vencimiento: CampoTexto
    importe: CampoNumero
    nota: CampoTexto


class Impuesto(ModeloEstricto):
    orden: CampoEntero
    base_imponible: CampoNumero
    tipo_iva: CampoNumero
    cuota_iva: CampoNumero
    tipo_recargo_equivalencia: CampoNumero
    cuota_recargo_equivalencia: CampoNumero
    nota: CampoTexto


class Albaran(ModeloEstricto):
    orden: CampoEntero
    numero_albaran: CampoTexto
    fecha_albaran: CampoTexto
    tipo_movimiento: CampoTexto
    descripcion: CampoTexto
    importe_base: CampoNumero
    importe_total: CampoNumero


class Ajuste(ModeloEstricto):
    orden: CampoEntero
    tipo_ajuste: CampoTexto
    descripcion: CampoTexto
    importe: CampoNumero
    incluido_en_base: CampoBooleano
    incluido_en_total: CampoBooleano


class Destinatario(ModeloEstricto):
    id_farmacia: CampoTexto
    nombre: CampoTexto
    cif: CampoTexto
    metodo_identificacion: CampoTexto


class FacturaExtraida(ModeloEstricto):
    tipo_documento: CampoTipoDocumento
    categoria: CampoCategoria
    requiere_conciliacion_albaranes: CampoBooleano
    pagina_inicio: CampoEntero
    pagina_fin: CampoEntero
    proveedor_nombre: CampoTexto
    proveedor_cif: CampoTexto
    numero_factura: CampoTexto
    fecha_factura: CampoTexto
    base_imponible_total: CampoNumero
    iva_total: CampoNumero
    recargo_equivalencia_total: CampoNumero
    importe_total: CampoNumero
    vencimientos: list[Vencimiento]
    impuestos: list[Impuesto]
    albaranes: list[Albaran]
    ajustes: list[Ajuste]
    destinatario: Destinatario
    fecha_cargo: CampoTexto
    periodo_facturacion_inicio: CampoTexto
    periodo_facturacion_fin: CampoTexto
    nota_revision: CampoTexto


@dataclass(frozen=True)
class Division:
    indice: int
    pagina_inicio: int
    pagina_fin: int

    @property
    def rango(self) -> str:
        return f"{self.pagina_inicio}-{self.pagina_fin}"

    @property
    def nombre_pdf(self) -> str:
        return (
            f"ALLIANCE_documento_{self.indice:02d}_"
            f"paginas_{self.pagina_inicio}_{self.pagina_fin}.pdf"
        )


DIVISION_PRUEBA = Division(2, 4, 7)


def cargar_clave() -> str:
    load_dotenv(RUTA_PROYECTO / ".env")
    clave = os.getenv("OPENAI_API_KEY")
    if not clave:
        raise ValueError("Falta OPENAI_API_KEY en .env.")
    return clave


def localizar_pdf() -> Path:
    ruta = RUTA_DOCUMENTOS / NOMBRE_PDF
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el PDF: {ruta}")
    return ruta


def crear_pdfs(ruta_origen: Path, directorio: Path) -> list[tuple[Division, Path]]:
    lector = PdfReader(ruta_origen)
    if len(lector.pages) != 11:
        raise ValueError(f"El PDF tiene {len(lector.pages)} páginas, no 11.")
    archivos: list[tuple[Division, Path]] = []
    for division in DIVISIONES:
        escritor = PdfWriter()
        for pagina in range(division.pagina_inicio, division.pagina_fin + 1):
            escritor.add_page(lector.pages[pagina - 1])
        salida = directorio / division.nombre_pdf
        with salida.open("wb") as archivo:
            escritor.write(archivo)
        paginas_esperadas = division.pagina_fin - division.pagina_inicio + 1
        if len(PdfReader(salida).pages) != paginas_esperadas:
            raise RuntimeError(f"No se pudo verificar el PDF temporal: {salida}")
        archivos.append((division, salida))
    return archivos


def archivo_como_data_url(ruta: Path) -> str:
    contenido = base64.b64encode(ruta.read_bytes()).decode("ascii")
    return f"data:application/pdf;base64,{contenido}"


def uso_como_dict(respuesta: Any) -> dict[str, Any]:
    if respuesta.usage is None:
        return {}
    return respuesta.usage.model_dump(mode="json", exclude_none=True)


def estimar_coste(uso: dict[str, Any]) -> dict[str, Any] | None:
    if not uso:
        return None
    entrada = int(uso.get("input_tokens", 0))
    salida = int(uso.get("output_tokens", 0))
    detalles = uso.get("input_tokens_details") or {}
    cacheados = int(detalles.get("cached_tokens", 0))
    no_cacheados = max(entrada - cacheados, 0)
    coste = (
        no_cacheados * PRECIO_ENTRADA_USD_MILLON
        + cacheados * PRECIO_ENTRADA_CACHE_USD_MILLON
        + salida * PRECIO_SALIDA_USD_MILLON
    ) / 1_000_000
    return {
        "moneda": "USD",
        "importe_estimado": round(coste, 6),
        "precios_usados_por_millon_tokens": {
            "entrada": PRECIO_ENTRADA_USD_MILLON,
            "entrada_cacheada": PRECIO_ENTRADA_CACHE_USD_MILLON,
            "salida": PRECIO_SALIDA_USD_MILLON,
        },
        "nota": "Estimación basada en usage; no sustituye la facturación oficial.",
    }


def metadatos(
    division: Division,
    respuesta: Any,
    uso: dict[str, Any],
) -> dict[str, Any]:
    return {
        "archivo_origen": NOMBRE_PDF,
        "archivo_enviado": division.nombre_pdf,
        "rango_paginas_originales": division.rango,
        "modelo_solicitado": MODELO,
        "modelo_utilizado": respuesta.model,
        "response_id": respuesta.id,
        "uso_tokens": uso,
        "coste_estimado": estimar_coste(uso),
        "fecha_hora_utc": datetime.now(timezone.utc).isoformat(),
        "version_prompt": VERSION_PROMPT,
    }


def guardar_resultados(
    division: Division,
    respuesta: Any,
    factura: FacturaExtraida,
) -> tuple[Path, Path]:
    RUTA_ORIGINALES.mkdir(parents=True, exist_ok=True)
    RUTA_ESTRUCTURADOS.mkdir(parents=True, exist_ok=True)
    uso = uso_como_dict(respuesta)
    meta = metadatos(division, respuesta, uso)
    nombre_base = Path(division.nombre_pdf).stem
    ruta_original = RUTA_ORIGINALES / f"{nombre_base}_openai_original.json"
    ruta_estructurada = RUTA_ESTRUCTURADOS / f"{nombre_base}_openai_estructurado.json"
    original = {
        "metadatos_prueba": meta,
        "respuesta_original": respuesta.model_dump(mode="json", exclude_none=False),
    }
    estructurado = {
        "metadatos_prueba": meta,
        "factura": factura.model_dump(mode="json"),
    }
    ruta_original.write_text(
        json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ruta_estructurada.write_text(
        json.dumps(estructurado, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ruta_original, ruta_estructurada


def ejecutar_llamadas(clave: str, archivos: list[tuple[Division, Path]]) -> None:
    cliente = OpenAI(api_key=clave, max_retries=0, timeout=180.0)
    for division, ruta_pdf in archivos:
        print(f"\nDocumento {division.indice}: páginas originales {division.rango}")
        try:
            respuesta = cliente.responses.parse(
                model=MODELO,
                reasoning={"effort": "none"},
                store=False,
                input=[
                    {"role": "system", "content": PROMPT_SISTEMA},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": PROMPT_USUARIO},
                            {
                                "type": "input_file",
                                "filename": ruta_pdf.name,
                                "file_data": archivo_como_data_url(ruta_pdf),
                                "detail": "high",
                            },
                        ],
                    },
                ],
                text_format=FacturaExtraida,
            )
        except Exception as error:
            codigo = getattr(error, "status_code", None)
            print(
                "La única llamada permitida para este PDF ha fallado: "
                f"{type(error).__name__}; status_code={codigo!r}. No se reintentará."
            )
            continue
        if respuesta.output_parsed is None:
            print("La respuesta no contiene JSON estructurado. No se hará otra llamada.")
            continue
        original, estructurado = guardar_resultados(
            division, respuesta, respuesta.output_parsed
        )
        print(f"Response ID: {respuesta.id}")
        print(f"Uso: {json.dumps(uso_como_dict(respuesta), ensure_ascii=False)}")
        print(f"Respuesta original: {original}")
        print(f"JSON estructurado: {estructurado}")


def mostrar_preparacion(archivos: list[tuple[Division, Path]]) -> None:
    schema = FacturaExtraida.model_json_schema()
    print("PRUEBA CIEGA OPENAI - ALLIANCE")
    print("-------------------------------")
    print(f"Modelo: {MODELO}")
    print("Motivo: modelo insignia actual con visión, Responses y Structured Outputs.")
    print("Número de llamadas pendientes: 4")
    print("Archivos exactos que se enviarían:")
    for division, ruta in archivos:
        print(f"- {ruta.name} (páginas originales {division.rango})")
    print("\nEsquema resumido:")
    print(", ".join(schema["properties"].keys()))
    print("Todos los objetos tienen additionalProperties=false mediante Pydantic extra=forbid.")
    print("\nPROMPT DE SISTEMA COMPLETO:\n")
    print(PROMPT_SISTEMA)
    print("PROMPT DE USUARIO COMPLETO:\n")
    print(PROMPT_USUARIO)
    print("Estimación previa: aproximadamente USD 1,00-4,00 para las 4 llamadas.")
    print("La cifra es orientativa: los PDF aportan texto e imágenes y el coste final depende de usage.")


def ejecutar(habilitar_openai: bool) -> None:
    clave = cargar_clave()
    ruta_origen = localizar_pdf()
    with tempfile.TemporaryDirectory(prefix="alliance_openai_ciega_") as temporal:
        archivos = crear_pdfs(ruta_origen, Path(temporal))
        mostrar_preparacion(archivos)
        if not habilitar_openai:
            print("\nValidación local terminada. No se ha llamado a OpenAI.")
            return
        confirmacion = input(
            "\nSe realizarán exactamente 4 llamadas facturables sin reintentos. "
            "Escribe EJECUTAR para continuar: "
        )
        if confirmacion != "EJECUTAR":
            print("Operación cancelada. No se ha llamado a OpenAI.")
            return
        ejecutar_llamadas(clave, archivos)


def crear_pdf_comparativa(ruta_origen: Path, directorio: Path) -> Path:
    lector = PdfReader(ruta_origen)
    if len(lector.pages) != 11:
        raise ValueError(f"El PDF debe tener 11 paginas y tiene {len(lector.pages)}.")
    salida = directorio / DIVISION_PRUEBA.nombre_pdf
    escritor = PdfWriter()
    for indice in range(3, 7):
        escritor.add_page(lector.pages[indice])
    with salida.open("wb") as archivo:
        escritor.write(archivo)
    if len(PdfReader(salida).pages) != 4:
        raise RuntimeError("El PDF temporal no conserva exactamente cuatro paginas.")
    return salida


def coste_comparativa(modelo: str, uso: dict[str, Any]) -> dict[str, float]:
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
        "coste_entrada": round(coste_entrada, 6),
        "coste_salida": round(coste_salida, 6),
        "coste_total_estimado": round(coste_entrada + coste_salida, 6),
    }


def cuerpo_error_seguro(error: Exception) -> Any:
    sensibles = {"authorization", "api_key", "apikey", "token", "access_token"}

    def limpiar(valor: Any) -> Any:
        if isinstance(valor, dict):
            return {
                clave: "[REDACTADO]" if clave.lower() in sensibles else limpiar(dato)
                for clave, dato in valor.items()
            }
        if isinstance(valor, list):
            return [limpiar(elemento) for elemento in valor]
        return valor

    cuerpo = getattr(error, "body", None)
    if cuerpo is not None:
        return limpiar(cuerpo)
    return {
        "message": str(error),
        "code": getattr(error, "code", None),
        "type": getattr(error, "type", None),
        "param": getattr(error, "param", None),
    }


def guardar_comparativa(
    modelo: str,
    respuesta: Any,
    factura: FacturaExtraida,
    duracion: float,
    raiz_salida: Path = RUTA_COMPARATIVA,
) -> None:
    directorio = raiz_salida / modelo
    directorio.mkdir(parents=True, exist_ok=True)
    uso = uso_como_dict(respuesta)
    entrada_detalle = uso.get("input_tokens_details") or {}
    salida_detalle = uso.get("output_tokens_details") or {}
    metadatos_prueba = {
        "archivo_origen": NOMBRE_PDF,
        "archivo_enviado": DIVISION_PRUEBA.nombre_pdf,
        "rango_paginas_originales": DIVISION_PRUEBA.rango,
        "modelo_solicitado": modelo,
        "modelo_utilizado": respuesta.model,
        "response_id": respuesta.id,
        "fecha_hora_utc": datetime.now(timezone.utc).isoformat(),
        "version_prompt": VERSION_PROMPT,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "reasoning_effort": RAZONAMIENTO,
        "store": False,
    }
    metricas = {
        "modelo": respuesta.model,
        "response_id": respuesta.id,
        "tokens_entrada": int(uso.get("input_tokens", 0)),
        "tokens_entrada_cacheados": int(entrada_detalle.get("cached_tokens", 0)),
        "tokens_salida": int(uso.get("output_tokens", 0)),
        "tokens_razonamiento": int(salida_detalle.get("reasoning_tokens", 0)),
        **coste_comparativa(modelo, uso),
        "duracion_segundos": round(duracion, 3),
        "estado_final": respuesta.status,
    }
    (directorio / "original.json").write_text(
        json.dumps(
            {
                "metadatos_prueba": metadatos_prueba,
                "respuesta_original": respuesta.model_dump(mode="json", exclude_none=False),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (directorio / "estructurado.json").write_text(
        json.dumps(
            {"metadatos_prueba": metadatos_prueba, "factura": factura.model_dump(mode="json")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (directorio / "metricas.json").write_text(
        json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def ejecutar_comparativa(
    clave: str,
    ruta_pdf: Path,
    modelos: tuple[str, ...] = tuple(MODELOS),
    raiz_salida: Path = RUTA_COMPARATIVA,
) -> None:
    cliente = OpenAI(api_key=clave, max_retries=0, timeout=300.0)
    for modelo in modelos:
        inicio = time.perf_counter()
        try:
            respuesta = cliente.responses.parse(
                model=modelo,
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
                                "filename": "documento.pdf",
                                "file_data": archivo_como_data_url(ruta_pdf),
                            },
                        ],
                    },
                ],
                text_format=FacturaExtraida,
            )
        except Exception as error:
            duracion = time.perf_counter() - inicio
            directorio = raiz_salida / modelo
            directorio.mkdir(parents=True, exist_ok=True)
            fallo = {
                "modelo": modelo,
                "tipo_error": type(error).__name__,
                "status_code": getattr(error, "status_code", None),
                "mensaje": "La unica llamada permitida fallo; no se reintentara.",
                "cuerpo_error_openai": cuerpo_error_seguro(error),
            }
            (directorio / "original.json").write_text(
                json.dumps({"respuesta_original": None, "error": fallo}, indent=2),
                encoding="utf-8",
            )
            (directorio / "estructurado.json").write_text(
                json.dumps({"factura": None, "error": fallo}, indent=2),
                encoding="utf-8",
            )
            (directorio / "metricas.json").write_text(
                json.dumps(
                    {
                        "modelo": modelo,
                        "response_id": None,
                        "tokens_entrada": 0,
                        "tokens_entrada_cacheados": 0,
                        "tokens_salida": 0,
                        "tokens_razonamiento": 0,
                        "coste_entrada": 0.0,
                        "coste_salida": 0.0,
                        "coste_total_estimado": 0.0,
                        "duracion_segundos": round(duracion, 3),
                        "estado_final": "failed",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"{modelo}: llamada fallida; no se reintentara.")
            continue
        duracion = time.perf_counter() - inicio
        if respuesta.output_parsed is None:
            raise RuntimeError(
                f"{modelo} no devolvio JSON estructurado; no se reintentara."
            )
        guardar_comparativa(
            modelo, respuesta, respuesta.output_parsed, duracion, raiz_salida
        )


def mostrar_comparativa(ruta_pdf: Path) -> None:
    print("COMPARATIVA CIEGA OPENAI - FACTURA ALLIANCE 02")
    print("Modelos: " + ", ".join(MODELOS))
    print("Llamadas pendientes: 3 (una por modelo, sin reintentos)")
    print(f"Unico PDF: {ruta_pdf.name}; paginas originales 4-7; paginas PDF: 4")
    print(f"Reasoning effort comun: {RAZONAMIENTO}")
    print(f"Maximo de salida comun: {MAX_OUTPUT_TOKENS} tokens")
    print("\nPROMPT DE SISTEMA COMPLETO:\n" + PROMPT_SISTEMA)
    print("PROMPT DE USUARIO COMPLETO:\n" + PROMPT_USUARIO)
    print("JSON SCHEMA COMPLETO:\n" + json.dumps(
        FacturaExtraida.model_json_schema(), ensure_ascii=False, indent=2
    ))


def preparar_comparativa(habilitar_openai: bool) -> None:
    clave = cargar_clave()
    with tempfile.TemporaryDirectory(prefix="alliance_openai_comparativa_") as temporal:
        ruta_pdf = crear_pdf_comparativa(localizar_pdf(), Path(temporal))
        mostrar_comparativa(ruta_pdf)
        if not habilitar_openai:
            print("\nValidacion local terminada. No se ha llamado a OpenAI.")
            return
        confirmacion = input(
            "\nSe haran exactamente 3 llamadas facturables. Escribe EJECUTAR para continuar: "
        )
        if confirmacion != "EJECUTAR":
            print("Operacion cancelada. No se ha llamado a OpenAI.")
            return
        ejecutar_comparativa(clave, ruta_pdf)


def preparar_repeticion_luna(habilitar_openai: bool) -> None:
    clave = cargar_clave()
    with tempfile.TemporaryDirectory(prefix="alliance_openai_luna_repeticion_") as temporal:
        ruta_pdf = crear_pdf_comparativa(localizar_pdf(), Path(temporal))
        print("REPETICION UNICA PREPARADA")
        print("Modelo: gpt-5.6-luna")
        print(f"PDF: {ruta_pdf.name}; paginas originales 4-7; paginas PDF: 4")
        print(f"Reasoning effort: {RAZONAMIENTO}")
        print(f"Maximo de salida: {MAX_OUTPUT_TOKENS} tokens")
        print("store=False; max_retries=0; sin herramientas")
        if not habilitar_openai:
            print("Validacion local terminada. No se ha llamado a OpenAI.")
            return
        confirmacion = input(
            "Se hara una unica llamada con gpt-5.6-luna. Escribe EJECUTAR_LUNA: "
        )
        if confirmacion != "EJECUTAR_LUNA":
            print("Operacion cancelada. No se ha llamado a OpenAI.")
            return
        ejecutar_comparativa(
            clave,
            ruta_pdf,
            modelos=("gpt-5.6-luna",),
            raiz_salida=RUTA_COMPARATIVA / "repeticion_01",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Comparativa ciega de modelos OpenAI.")
    parser.add_argument(
        "--ejecutar-openai",
        action="store_true",
        help="Habilita la barrera interactiva previa a tres llamadas facturables.",
    )
    parser.add_argument(
        "--repetir-luna",
        action="store_true",
        help="Prepara una unica repeticion de Luna; mantiene una barrera interactiva.",
    )
    argumentos = parser.parse_args()
    if argumentos.repetir_luna:
        preparar_repeticion_luna(argumentos.ejecutar_openai)
    else:
        preparar_comparativa(argumentos.ejecutar_openai)


if __name__ == "__main__":
    main()
