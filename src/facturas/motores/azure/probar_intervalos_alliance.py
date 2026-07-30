from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv


RUTA_PROYECTO = Path(__file__).resolve().parents[4]

RUTA_DOCUMENTOS = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "documentos"
)

RUTA_SALIDA = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "resultados"
    / "azure"
    / "originales"
    / "alliance_por_intervalos"
)

NOMBRE_PDF = "ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf"

INTERVALOS_ALLIANCE = (
    {
        "paginas": "1-3",
        "factura_esperada": "08008428",
    },
    {
        "paginas": "4-7",
        "factura_esperada": "08008431",
    },
    {
        "paginas": "8-9",
        "factura_esperada": "08008429",
    },
    {
        "paginas": "10-11",
        "factura_esperada": "08008430",
    },
)


def cargar_configuracion() -> tuple[str, str]:
    """
    Carga y valida las credenciales de Azure desde .env.
    """
    ruta_env = RUTA_PROYECTO / ".env"

    if not ruta_env.exists():
        raise FileNotFoundError(
            f"No se encuentra el archivo .env: {ruta_env}"
        )

    load_dotenv(ruta_env)

    endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    clave = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")

    if not endpoint:
        raise ValueError(
            "Falta AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT en .env."
        )

    if not clave:
        raise ValueError(
            "Falta AZURE_DOCUMENT_INTELLIGENCE_KEY en .env."
        )

    return endpoint, clave


def localizar_pdf() -> Path:
    """
    Localiza el PDF de Alliance en el banco de pruebas.
    """
    coincidencias = [
        ruta
        for ruta in RUTA_DOCUMENTOS.rglob(NOMBRE_PDF)
        if ruta.is_file()
    ]

    if not coincidencias:
        raise FileNotFoundError(
            f"No se encuentra el PDF de Alliance en: "
            f"{RUTA_DOCUMENTOS}"
        )

    if len(coincidencias) > 1:
        rutas = "\n".join(
            f"- {ruta}"
            for ruta in coincidencias
        )

        raise RuntimeError(
            "Se ha encontrado más de una copia del PDF de Alliance:\n"
            f"{rutas}"
        )

    return coincidencias[0]


def serializar_json(valor: Any) -> Any:
    """
    Convierte tipos especiales a valores compatibles con JSON.
    """
    if isinstance(valor, Decimal):
        return str(valor)

    if isinstance(valor, datetime):
        return valor.isoformat()

    if isinstance(valor, date):
        return valor.isoformat()

    if isinstance(valor, bytes):
        return valor.decode(
            encoding="utf-8",
            errors="replace",
        )

    return str(valor)


def obtener_valor_campo(campo: Any) -> Any:
    """
    Obtiene el valor principal de un campo de Azure.
    """
    if campo is None:
        return None

    valor = getattr(campo, "value", None)

    if valor is not None:
        return valor

    return getattr(campo, "content", None)


def obtener_confianza(campo: Any) -> float | None:
    """
    Obtiene la confianza de un campo de Azure.
    """
    if campo is None:
        return None

    return getattr(campo, "confidence", None)


def mostrar_campo(
    nombre: str,
    campos: dict[str, Any],
    clave_azure: str,
) -> None:
    campo = campos.get(clave_azure)

    print(
        f"{nombre}: {obtener_valor_campo(campo)} "
        f"(confianza: {obtener_confianza(campo)})"
    )


def crear_ruta_salida(
    paginas: str,
    factura_esperada: str,
) -> Path:
    """
    Crea la ruta del JSON original para un intervalo.
    """
    nombre_intervalo = paginas.replace("-", "_")

    nombre_archivo = (
        f"ALLIANCE_paginas_{nombre_intervalo}"
        f"_factura_esperada_{factura_esperada}"
        f"_azure_original.json"
    )

    return RUTA_SALIDA / nombre_archivo


def guardar_resultado(
    resultado: Any,
    paginas: str,
    factura_esperada: str,
) -> Path:
    """
    Guarda la respuesta original completa de Azure.
    """
    if not hasattr(resultado, "as_dict"):
        raise TypeError(
            "El resultado de Azure no dispone de as_dict()."
        )

    RUTA_SALIDA.mkdir(
        parents=True,
        exist_ok=True,
    )

    ruta_salida = crear_ruta_salida(
        paginas=paginas,
        factura_esperada=factura_esperada,
    )

    datos = resultado.as_dict()

    with ruta_salida.open(
        mode="w",
        encoding="utf-8",
    ) as archivo:
        json.dump(
            datos,
            archivo,
            ensure_ascii=False,
            indent=2,
            default=serializar_json,
        )

    return ruta_salida


def analizar_intervalo(
    cliente: DocumentIntelligenceClient,
    contenido_pdf: bytes,
    paginas: str,
    factura_esperada: str,
) -> None:
    """
    Procesa un intervalo concreto de páginas del PDF.
    """
    print()
    print("=" * 70)
    print(
        f"INTERVALO {paginas} "
        f"- FACTURA ESPERADA {factura_esperada}"
    )
    print("=" * 70)
    print("Enviando intervalo a Azure...")

    operacion = cliente.begin_analyze_document(
        model_id="prebuilt-invoice",
        body=contenido_pdf,
        content_type="application/pdf",
        pages=paginas,
    )

    resultado = operacion.result()

    paginas_detectadas = resultado.pages or []
    documentos_detectados = resultado.documents or []

    print("Intervalo procesado correctamente.")
    print(
        f"Páginas detectadas: "
        f"{len(paginas_detectadas)}"
    )
    print(
        f"Documentos detectados: "
        f"{len(documentos_detectados)}"
    )

    if not documentos_detectados:
        print("Azure no ha detectado ninguna factura.")
    else:
        for indice, documento in enumerate(
            documentos_detectados,
            start=1,
        ):
            print()
            print(f"DOCUMENTO {indice}")
            print("-" * 20)

            campos = documento.fields or {}

            mostrar_campo(
                nombre="Proveedor",
                campos=campos,
                clave_azure="VendorName",
            )

            mostrar_campo(
                nombre="Número de factura",
                campos=campos,
                clave_azure="InvoiceId",
            )

            mostrar_campo(
                nombre="Fecha de factura",
                campos=campos,
                clave_azure="InvoiceDate",
            )

            mostrar_campo(
                nombre="Fecha de vencimiento",
                campos=campos,
                clave_azure="DueDate",
            )

            mostrar_campo(
                nombre="CIF cliente",
                campos=campos,
                clave_azure="CustomerTaxId",
            )

            mostrar_campo(
                nombre="Subtotal",
                campos=campos,
                clave_azure="SubTotal",
            )

            mostrar_campo(
                nombre="IVA",
                campos=campos,
                clave_azure="TotalTax",
            )

            mostrar_campo(
                nombre="Total",
                campos=campos,
                clave_azure="InvoiceTotal",
            )

            print(
                f"Confianza del documento: "
                f"{getattr(documento, 'confidence', None)}"
            )

    ruta_guardada = guardar_resultado(
        resultado=resultado,
        paginas=paginas,
        factura_esperada=factura_esperada,
    )

    print()
    print(f"JSON original guardado en: {ruta_guardada}")


def ejecutar() -> None:
    """
    Procesa Alliance por los cuatro intervalos del patrón oficial.
    """
    endpoint, clave = cargar_configuracion()
    ruta_pdf = localizar_pdf()

    print("PRUEBA AZURE POR INTERVALOS - ALLIANCE")
    print("--------------------------------------")
    print(f"Archivo: {ruta_pdf.name}")
    print("Modelo: prebuilt-invoice")
    print(
        "Intervalos: "
        + ", ".join(
            intervalo["paginas"]
            for intervalo in INTERVALOS_ALLIANCE
        )
    )

    with ruta_pdf.open("rb") as archivo:
        contenido_pdf = archivo.read()

    cliente = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(clave),
    )

    for intervalo in INTERVALOS_ALLIANCE:
        analizar_intervalo(
            cliente=cliente,
            contenido_pdf=contenido_pdf,
            paginas=intervalo["paginas"],
            factura_esperada=intervalo["factura_esperada"],
        )

    print()
    print("RESULTADO FINAL")
    print("---------------")
    print(
        "Los cuatro intervalos de Alliance se han procesado "
        "y guardado por separado."
    )


if __name__ == "__main__":
    ejecutar()