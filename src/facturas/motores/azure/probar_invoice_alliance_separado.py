from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.core.pipeline.policies import RetryPolicy
from dotenv import load_dotenv
from pypdf import PdfReader, PdfWriter


RUTA_PROYECTO = Path(__file__).resolve().parents[4]
RUTA_DOCUMENTOS = RUTA_PROYECTO / "pruebas" / "facturas" / "documentos"
RUTA_RESULTADOS = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "resultados"
    / "azure"
    / "invoice_parser"
    / "originales"
)
NOMBRE_PDF = "ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf"
MODELO = "prebuilt-invoice"


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


DIVISIONES = (
    Division(1, 1, 3),
    Division(2, 4, 7),
    Division(3, 8, 9),
    Division(4, 10, 11),
)


def cargar_configuracion() -> tuple[str, str]:
    load_dotenv(RUTA_PROYECTO / ".env")
    endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    clave = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
    if not endpoint:
        raise ValueError("Falta AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT en .env.")
    if not clave:
        raise ValueError("Falta AZURE_DOCUMENT_INTELLIGENCE_KEY en .env.")
    return endpoint, clave


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


def serializar_json(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, bytes):
        return valor.decode("utf-8", errors="replace")
    if hasattr(valor, "as_dict"):
        return valor.as_dict()
    return str(valor)


def paginas_relativas(objeto: Any) -> list[int]:
    paginas: set[int] = set()
    for region in getattr(objeto, "bounding_regions", None) or []:
        numero = getattr(region, "page_number", None)
        if numero is not None:
            paginas.add(int(numero))
    return sorted(paginas)


def valor_normalizado(campo: Any) -> Any:
    valor = getattr(campo, "value", None)
    if valor is None:
        for atributo in (
            "value_string",
            "value_date",
            "value_time",
            "value_phone_number",
            "value_number",
            "value_integer",
            "value_currency",
            "value_selection_mark",
            "value_signature",
            "value_country_region",
            "value_boolean",
            "value_array",
            "value_object",
        ):
            valor = getattr(campo, atributo, None)
            if valor is not None:
                break
    if valor is None:
        return None
    if hasattr(valor, "as_dict"):
        return valor.as_dict()
    return valor


def mostrar_campo(nombre: str, campo: Any, nivel: int = 0) -> None:
    sangria = "  " * nivel
    contenido = getattr(campo, "content", None)
    confianza = getattr(campo, "confidence", None)
    paginas = paginas_relativas(campo)
    valor = valor_normalizado(campo)
    print(f"{sangria}- Campo Azure: {nombre}")
    print(f"{sangria}  Contenido detectado: {contenido!r}")
    print(f"{sangria}  Valor normalizado: {valor!r}")
    print(f"{sangria}  Confianza: {confianza!r}")
    print(f"{sangria}  Página relativa: {paginas or 'no disponible'}")

    tipo = getattr(campo, "type", None)
    tipo_texto = getattr(tipo, "value", tipo)
    if tipo_texto == "array":
        for indice, elemento in enumerate(valor or [], start=1):
            mostrar_campo(f"{nombre}[{indice}]", elemento, nivel + 1)
    elif tipo_texto == "object" and isinstance(valor, dict):
        for subnombre, subcampo in valor.items():
            mostrar_campo(f"{nombre}.{subnombre}", subcampo, nivel + 1)


def mostrar_documentos(resultado: Any) -> None:
    documentos = list(resultado.documents or [])
    print(f"Número de documentos devueltos: {len(documentos)}")
    for indice, documento in enumerate(documentos, start=1):
        print(f"\nDOCUMENTO {indice}")
        campos = documento.fields or {}
        print(f"Campos detectados: {len(campos)}")
        for nombre, campo in campos.items():
            mostrar_campo(nombre, campo)


def mostrar_tablas(resultado: Any) -> None:
    tablas = list(resultado.tables or [])
    print(f"\nTablas detectadas: {len(tablas)}")
    for indice, tabla in enumerate(tablas, start=1):
        print(
            f"Tabla {indice}: filas={tabla.row_count}, "
            f"columnas={tabla.column_count}, páginas={paginas_relativas(tabla)}"
        )
        for celda in tabla.cells or []:
            print(
                f"  fila={celda.row_index}, columna={celda.column_index}, "
                f"tipo={getattr(celda, 'kind', None)!r}, "
                f"páginas={paginas_relativas(celda)}, contenido={celda.content!r}"
            )


def campos_items(documentos: Iterable[Any]) -> Iterable[tuple[str, Any]]:
    for indice_documento, documento in enumerate(documentos, start=1):
        campo = (documento.fields or {}).get("Items")
        if campo is not None:
            yield f"Documento {indice_documento}.Items", campo


def mostrar_lineas_articulos(resultado: Any) -> None:
    print("\nLíneas de artículos (Items):")
    encontrados = False
    for nombre, campo in campos_items(resultado.documents or []):
        encontrados = True
        mostrar_campo(nombre, campo)
    if not encontrados:
        print("No detectadas.")


def guardar_respuesta(
    resultado: Any,
    division: Division,
    duracion: float,
) -> Path:
    RUTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    paginas = [
        int(pagina.page_number)
        for pagina in (resultado.pages or [])
        if getattr(pagina, "page_number", None) is not None
    ]
    contenido = {
        "metadatos_prueba": {
            "archivo_origen": NOMBRE_PDF,
            "archivo_enviado": division.nombre_pdf,
            "rango_paginas_originales": division.rango,
            "indice_documento": division.indice,
            "modelo_utilizado": MODELO,
            "fecha_hora_utc": datetime.now(timezone.utc).isoformat(),
            "duracion_segundos": round(duracion, 3),
            "paginas_procesadas": paginas,
            "cantidad_paginas_procesadas": len(paginas),
        },
        "respuesta_original": resultado.as_dict(),
    }
    ruta = RUTA_RESULTADOS / (
        f"{Path(division.nombre_pdf).stem}_azure_original.json"
    )
    ruta.write_text(
        json.dumps(contenido, ensure_ascii=False, indent=2, default=serializar_json),
        encoding="utf-8",
    )
    return ruta


def crear_cliente(endpoint: str, clave: str) -> DocumentIntelligenceClient:
    politica = RetryPolicy(
        retry_total=0,
        retry_connect=0,
        retry_read=0,
        retry_status=0,
    )
    return DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(clave),
        retry_policy=politica,
    )


def ejecutar_llamadas(
    endpoint: str,
    clave: str,
    archivos: list[tuple[Division, Path]],
) -> None:
    cliente = crear_cliente(endpoint, clave)
    for division, ruta_pdf in archivos:
        print(f"\n{'=' * 72}")
        print(
            f"DOCUMENTO {division.indice}: páginas originales {division.rango}; "
            f"PDF enviado: {ruta_pdf.name}"
        )
        inicio = time.perf_counter()
        try:
            # No se usa pages: el cuerpo ya contiene solo una factura.
            operacion = cliente.begin_analyze_document(
                model_id=MODELO,
                body=ruta_pdf.read_bytes(),
                content_type="application/pdf",
            )
            resultado = operacion.result()
        except Exception as error:
            duracion = time.perf_counter() - inicio
            codigo = getattr(error, "status_code", None)
            print(
                "La única llamada de análisis permitida para este PDF ha fallado: "
                f"{type(error).__name__}; status_code={codigo!r}; "
                f"duración={duracion:.3f}s. No se reintentará."
            )
            continue
        duracion = time.perf_counter() - inicio
        paginas = list(resultado.pages or [])
        print(f"Páginas enviadas: {division.rango}")
        print(f"Páginas relativas procesadas: {len(paginas)}")
        print(f"Duración: {duracion:.3f}s")
        mostrar_documentos(resultado)
        mostrar_tablas(resultado)
        mostrar_lineas_articulos(resultado)
        ruta = guardar_respuesta(resultado, division, duracion)
        print(f"Respuesta original guardada en: {ruta}")


def mostrar_preparacion(archivos: list[tuple[Division, Path]]) -> None:
    print("PRUEBA AZURE PREBUILT-INVOICE - ALLIANCE SEPARADO")
    print("-------------------------------------------------")
    print(f"Modelo: {MODELO}")
    print("Número de llamadas pendientes: 4")
    print("Cada llamada recibe un PDF independiente; no se usa pages ni intervalos.")
    print("Archivos exactos:")
    for division, ruta in archivos:
        print(f"- {ruta.name} (páginas originales {division.rango})")


def ejecutar(habilitar_azure: bool) -> None:
    endpoint, clave = cargar_configuracion()
    ruta_origen = localizar_pdf()
    with tempfile.TemporaryDirectory(prefix="alliance_azure_separado_") as temporal:
        archivos = crear_pdfs(ruta_origen, Path(temporal))
        mostrar_preparacion(archivos)
        if not habilitar_azure:
            print("\nValidación local terminada. No se ha llamado a Azure.")
            return
        confirmacion = input(
            "\nSe realizarán exactamente 4 llamadas de análisis sin reintentos. "
            "Escribe EJECUTAR para continuar: "
        )
        if confirmacion != "EJECUTAR":
            print("Operación cancelada. No se ha llamado a Azure.")
            return
        ejecutar_llamadas(endpoint, clave, archivos)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prueba Azure prebuilt-invoice con cuatro PDF Alliance separados."
    )
    parser.add_argument(
        "--ejecutar-azure",
        action="store_true",
        help="Habilita la confirmación interactiva previa a cuatro llamadas.",
    )
    argumentos = parser.parse_args()
    ejecutar(argumentos.ejecutar_azure)


if __name__ == "__main__":
    main()
