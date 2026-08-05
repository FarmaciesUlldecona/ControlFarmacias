from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.api_core.client_options import ClientOptions
from google.cloud import documentai
from google.protobuf.json_format import MessageToDict


RUTA_PROYECTO = Path(__file__).resolve().parents[4]
RUTA_DOCUMENTOS = RUTA_PROYECTO / "pruebas" / "facturas" / "documentos"
RUTA_RESULTADOS = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "resultados"
    / "google"
    / "originales"
)
NOMBRE_PDF = "ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf"


def cargar_configuracion() -> tuple[str, str, str]:
    """Carga y valida la configuración necesaria para Document AI."""
    load_dotenv(RUTA_PROYECTO / ".env")

    proyecto = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    ubicacion = os.getenv("GOOGLE_DOCUMENT_AI_LOCATION")
    processor_id = os.getenv("GOOGLE_DOCUMENT_AI_PROCESSOR_ID")

    variables = {
        "GOOGLE_CLOUD_PROJECT_ID": proyecto,
        "GOOGLE_DOCUMENT_AI_LOCATION": ubicacion,
        "GOOGLE_DOCUMENT_AI_PROCESSOR_ID": processor_id,
    }
    ausentes = [nombre for nombre, valor in variables.items() if not valor]
    if ausentes:
        raise ValueError("Faltan variables de entorno: " + ", ".join(ausentes))

    if ubicacion != "eu":
        raise ValueError("GOOGLE_DOCUMENT_AI_LOCATION debe ser 'eu'.")

    if processor_id != "11bde8d32e98095f":
        raise ValueError(
            "GOOGLE_DOCUMENT_AI_PROCESSOR_ID no coincide con el splitter esperado."
        )

    return proyecto, ubicacion, processor_id


def localizar_pdf() -> Path:
    """Localiza de forma inequívoca el PDF completo de Alliance."""
    coincidencias = sorted(
        ruta for ruta in RUTA_DOCUMENTOS.rglob(NOMBRE_PDF) if ruta.is_file()
    )
    if not coincidencias:
        raise FileNotFoundError(f"No se encuentra {NOMBRE_PDF} en {RUTA_DOCUMENTOS}")
    if len(coincidencias) > 1:
        raise RuntimeError(
            "Se ha encontrado más de una copia del PDF:\n"
            + "\n".join(f"- {ruta}" for ruta in coincidencias)
        )
    return coincidencias[0]


def guardar_respuesta_original(respuesta: Any, ruta_pdf: Path) -> Path:
    """Guarda el ProcessResponse completo sin normalizar su contenido."""
    RUTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    ruta_salida = RUTA_RESULTADOS / f"{ruta_pdf.stem}_google_original.json"
    datos = MessageToDict(
        respuesta._pb,
        preserving_proto_field_name=True,
    )
    with ruta_salida.open("w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
    return ruta_salida


def paginas_asignadas(entidad: Any) -> list[int]:
    """Extrae los números de página (base 1) asignados por el splitter."""
    paginas: set[int] = set()
    page_anchor = getattr(entidad, "page_anchor", None)
    for referencia in getattr(page_anchor, "page_refs", ()):
        paginas.add(int(referencia.page) + 1)
    return sorted(paginas)


def mostrar_resumen(documento: Any) -> None:
    """Muestra el resultado esencial del splitter en terminal."""
    paginas = list(documento.pages)
    documentos = list(documento.entities)

    print(f"Páginas procesadas: {len(paginas)}")
    print(f"Documentos detectados: {len(documentos)}")

    for indice, entidad in enumerate(documentos, start=1):
        clase = entidad.type_ or entidad.mention_text or "sin clase"
        paginas_documento = paginas_asignadas(entidad)
        paginas_texto = ", ".join(map(str, paginas_documento)) or "no disponibles"
        print()
        print(f"Documento {indice}")
        print(f"Clase: {clase}")
        print(f"Confianza: {entidad.confidence}")
        print(f"Páginas asignadas: {paginas_texto}")


def procesar_pdf(
    ruta_pdf: Path,
    proyecto: str,
    ubicacion: str,
    processor_id: str,
) -> None:
    """Envía el PDF completo en una única petición al Custom Splitter."""
    endpoint = f"{ubicacion}-documentai.googleapis.com"
    cliente = documentai.DocumentProcessorServiceClient(
        client_options=ClientOptions(api_endpoint=endpoint)
    )
    nombre_processor = cliente.processor_path(proyecto, ubicacion, processor_id)

    with ruta_pdf.open("rb") as archivo:
        contenido_pdf = archivo.read()

    # Deliberadamente no se indican intervalos ni process_options: se envían
    # todos los bytes del PDF original en una sola llamada.
    solicitud = documentai.ProcessRequest(
        name=nombre_processor,
        raw_document=documentai.RawDocument(
            content=contenido_pdf,
            mime_type="application/pdf",
        ),
    )

    print("PRUEBA GOOGLE DOCUMENT AI - CUSTOM SPLITTER")
    print("-------------------------------------------")
    print(f"Archivo: {ruta_pdf}")
    print(f"Endpoint: {endpoint}")
    print("Enviando el PDF completo en una única petición...")

    respuesta = cliente.process_document(request=solicitud)
    ruta_guardada = guardar_respuesta_original(respuesta, ruta_pdf)
    mostrar_resumen(respuesta.document)
    print()
    print(f"Respuesta original guardada en: {ruta_guardada}")


def ejecutar() -> None:
    proyecto, ubicacion, processor_id = cargar_configuracion()
    ruta_pdf = localizar_pdf()
    procesar_pdf(ruta_pdf, proyecto, ubicacion, processor_id)


if __name__ == "__main__":
    ejecutar()
