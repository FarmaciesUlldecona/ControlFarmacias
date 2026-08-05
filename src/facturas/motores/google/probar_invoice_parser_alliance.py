from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from google.api_core.client_options import ClientOptions
from google.cloud import documentai
from google.protobuf.json_format import MessageToDict
from pypdf import PdfReader, PdfWriter


RUTA_PROYECTO = Path(__file__).resolve().parents[4]
RUTA_DOCUMENTOS = RUTA_PROYECTO / "pruebas" / "facturas" / "documentos"
RUTA_SPLITTER = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "resultados"
    / "google"
    / "originales"
)
RUTA_RESULTADOS = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "resultados"
    / "google"
    / "invoice_parser"
    / "originales"
)
NOMBRE_PDF = "ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf"
NOMBRE_RESPUESTA_SPLITTER = f"{Path(NOMBRE_PDF).stem}_google_original.json"
PROCESSOR_ID_CONFIRMADO = "ca1c3f1cb8054263"


@dataclass(frozen=True)
class Division:
    indice: int
    pagina_inicio: int
    pagina_fin: int

    @property
    def rango(self) -> str:
        return f"{self.pagina_inicio}-{self.pagina_fin}"

    @property
    def nombre_temporal(self) -> str:
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


def cargar_configuracion() -> tuple[str, str, str]:
    """Carga solo la configuración del Invoice Parser mediante .env."""
    load_dotenv(RUTA_PROYECTO / ".env")
    variables = {
        "GOOGLE_CLOUD_PROJECT_ID": os.getenv("GOOGLE_CLOUD_PROJECT_ID"),
        "GOOGLE_DOCUMENT_AI_LOCATION": os.getenv("GOOGLE_DOCUMENT_AI_LOCATION"),
        "GOOGLE_DOCUMENT_AI_INVOICE_PROCESSOR_ID": os.getenv(
            "GOOGLE_DOCUMENT_AI_INVOICE_PROCESSOR_ID"
        ),
    }
    ausentes = [nombre for nombre, valor in variables.items() if not valor]
    if ausentes:
        raise ValueError("Faltan variables de entorno: " + ", ".join(ausentes))

    proyecto = str(variables["GOOGLE_CLOUD_PROJECT_ID"])
    ubicacion = str(variables["GOOGLE_DOCUMENT_AI_LOCATION"])
    processor_id = str(variables["GOOGLE_DOCUMENT_AI_INVOICE_PROCESSOR_ID"])
    if ubicacion != "eu":
        raise ValueError("GOOGLE_DOCUMENT_AI_LOCATION debe ser 'eu'.")
    if processor_id != PROCESSOR_ID_CONFIRMADO:
        raise ValueError(
            "GOOGLE_DOCUMENT_AI_INVOICE_PROCESSOR_ID no coincide con el valor "
            "confirmado para esta prueba."
        )
    return proyecto, ubicacion, processor_id


def localizar_archivo(directorio: Path, nombre: str) -> Path:
    coincidencias = sorted(ruta for ruta in directorio.rglob(nombre) if ruta.is_file())
    if not coincidencias:
        raise FileNotFoundError(f"No se encuentra {nombre} en {directorio}")
    if len(coincidencias) > 1:
        raise RuntimeError(
            f"Se encontró más de una copia de {nombre}:\n"
            + "\n".join(f"- {ruta}" for ruta in coincidencias)
        )
    return coincidencias[0]


def paginas_entidad_splitter(entidad: dict[str, Any]) -> list[int]:
    referencias = entidad.get("page_anchor", {}).get("page_refs", [])
    # Document AI omite el campo page cuando su valor protobuf es cero.
    return [int(referencia.get("page", 0)) + 1 for referencia in referencias]


def validar_respuesta_splitter(ruta: Path) -> None:
    """Comprueba localmente que la respuesta guardada contiene los cuatro rangos."""
    with ruta.open("r", encoding="utf-8") as archivo:
        respuesta = json.load(archivo)
    documento = respuesta.get("document", {})
    if len(documento.get("pages", [])) != 11:
        raise ValueError("La respuesta guardada del Splitter no contiene 11 páginas.")
    rangos = [paginas_entidad_splitter(entidad) for entidad in documento.get("entities", [])]
    esperados = [
        list(range(division.pagina_inicio, division.pagina_fin + 1))
        for division in DIVISIONES
    ]
    if rangos != esperados:
        raise ValueError(
            f"Las divisiones guardadas no coinciden. Detectadas: {rangos}; "
            f"esperadas: {esperados}."
        )


def crear_pdfs_temporales(ruta_pdf: Path, directorio: Path) -> list[tuple[Division, Path]]:
    """Copia páginas originales a cuatro PDF sin rasterizarlas ni recomprimirlas."""
    lector = PdfReader(ruta_pdf)
    if len(lector.pages) != 11:
        raise ValueError(f"El PDF de Alliance tiene {len(lector.pages)} páginas, no 11.")

    salidas: list[tuple[Division, Path]] = []
    for division in DIVISIONES:
        escritor = PdfWriter()
        for numero_pagina in range(division.pagina_inicio, division.pagina_fin + 1):
            escritor.add_page(lector.pages[numero_pagina - 1])
        ruta_salida = directorio / division.nombre_temporal
        with ruta_salida.open("wb") as archivo:
            escritor.write(archivo)
        if len(PdfReader(ruta_salida).pages) != division.pagina_fin - division.pagina_inicio + 1:
            raise RuntimeError(f"Falló la verificación local de {ruta_salida}.")
        salidas.append((division, ruta_salida))
    return salidas


def paginas_entidad(entidad: Any) -> list[int]:
    paginas: set[int] = set()
    for referencia in getattr(getattr(entidad, "page_anchor", None), "page_refs", ()):
        paginas.add(int(referencia.page) + 1)
    return sorted(paginas)


def recorrer_entidades(entidades: Iterable[Any], nivel: int = 0) -> Iterable[tuple[int, Any]]:
    for entidad in entidades:
        yield nivel, entidad
        yield from recorrer_entidades(getattr(entidad, "properties", ()), nivel + 1)


def mostrar_entidades(documento: Any, division: Division) -> None:
    entidades = list(documento.entities)
    print(f"Páginas enviadas: {division.rango}")
    print(f"Entidades detectadas: {len(entidades)} entidades principales")
    for nivel, entidad in recorrer_entidades(entidades):
        sangria = "  " * nivel
        normalizado = MessageToDict(
            entidad.normalized_value._pb,
            preserving_proto_field_name=True,
        ) if entidad._pb.HasField("normalized_value") else None
        paginas = paginas_entidad(entidad)
        print(f"{sangria}- Tipo de entidad: {entidad.type_ or '(vacío)'}")
        print(f"{sangria}  Texto detectado: {entidad.mention_text!r}")
        print(f"{sangria}  Valor normalizado: {normalizado!r}")
        print(f"{sangria}  Confianza: {entidad.confidence:.6f}")
        print(f"{sangria}  Páginas: {paginas or 'no disponibles'}")


def guardar_respuesta(
    respuesta: Any,
    ruta_origen: Path,
    division: Division,
    processor_id: str,
) -> Path:
    RUTA_RESULTADOS.mkdir(parents=True, exist_ok=True)
    ruta_salida = RUTA_RESULTADOS / (
        f"ALLIANCE_documento_{division.indice:02d}_"
        f"paginas_{division.pagina_inicio}_{division.pagina_fin}_google_original.json"
    )
    contenido = {
        "metadatos_prueba": {
            "archivo_origen": ruta_origen.name,
            "rango_paginas": division.rango,
            "indice_documento": division.indice,
            "processor_id": processor_id,
        },
        "respuesta_original": MessageToDict(
            respuesta._pb,
            preserving_proto_field_name=True,
        ),
    }
    with ruta_salida.open("w", encoding="utf-8") as archivo:
        json.dump(contenido, archivo, ensure_ascii=False, indent=2)
    return ruta_salida


def procesar_facturas(
    archivos: list[tuple[Division, Path]],
    ruta_origen: Path,
    proyecto: str,
    ubicacion: str,
    processor_id: str,
) -> None:
    endpoint = f"{ubicacion}-documentai.googleapis.com"
    cliente = documentai.DocumentProcessorServiceClient(
        client_options=ClientOptions(api_endpoint=endpoint)
    )
    nombre_processor = cliente.processor_path(proyecto, ubicacion, processor_id)
    for division, ruta_pdf in archivos:
        solicitud = documentai.ProcessRequest(
            name=nombre_processor,
            raw_document=documentai.RawDocument(
                content=ruta_pdf.read_bytes(),
                mime_type="application/pdf",
            ),
        )
        print(f"\nDOCUMENTO {division.indice} - páginas {division.rango}")
        try:
            # retry=None garantiza un único intento facturable por cada PDF.
            respuesta = cliente.process_document(request=solicitud, retry=None)
        except Exception as error:
            print(
                "La única llamada permitida para este documento ha fallado: "
                f"{type(error).__name__}: {error}"
            )
            continue
        mostrar_entidades(respuesta.document, division)
        ruta_guardada = guardar_respuesta(
            respuesta, ruta_origen, division, processor_id
        )
        print(f"Respuesta original guardada en: {ruta_guardada}")


def ejecutar(ejecutar_google: bool) -> None:
    proyecto, ubicacion, processor_id = cargar_configuracion()
    ruta_pdf = localizar_archivo(RUTA_DOCUMENTOS, NOMBRE_PDF)
    ruta_splitter = localizar_archivo(RUTA_SPLITTER, NOMBRE_RESPUESTA_SPLITTER)
    validar_respuesta_splitter(ruta_splitter)

    with tempfile.TemporaryDirectory(prefix="alliance_invoice_parser_") as temporal:
        archivos = crear_pdfs_temporales(ruta_pdf, Path(temporal))
        print("PRUEBA CONTROLADA GOOGLE DOCUMENT AI - INVOICE PARSER")
        print("-----------------------------------------------------")
        print(f"PDF de origen: {ruta_pdf}")
        print(f"Respuesta Splitter validada: {ruta_splitter}")
        print(f"Processor ID preparado: {processor_id}")
        print("PDF temporales creados y verificados:")
        for division, ruta_temporal in archivos:
            print(f"- Documento {division.indice}: páginas {division.rango}: {ruta_temporal.name}")

        if not ejecutar_google:
            print("\nModo local finalizado. No se ha llamado a Google Document AI.")
            print("Quedan pendientes 4 llamadas facturables, una por PDF temporal.")
            return

        confirmacion = input(
            "\nSe realizarán 4 llamadas facturables al Invoice Parser. "
            "Escribe EJECUTAR para continuar: "
        )
        if confirmacion != "EJECUTAR":
            print("Operación cancelada. No se ha llamado a Google Document AI.")
            return
        procesar_facturas(
            archivos, ruta_pdf, proyecto, ubicacion, processor_id
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepara y, con confirmación explícita, prueba Invoice Parser con Alliance."
    )
    parser.add_argument(
        "--ejecutar-google",
        action="store_true",
        help="Habilita la confirmación interactiva previa a las 4 llamadas facturables.",
    )
    argumentos = parser.parse_args()
    ejecutar(argumentos.ejecutar_google)


if __name__ == "__main__":
    main()
