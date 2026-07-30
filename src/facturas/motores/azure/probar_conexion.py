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

RUTA_DOCUMENTOS_PRUEBA = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "documentos"
)

RUTA_RESULTADOS_ORIGINALES = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "resultados"
    / "azure"
    / "originales"
)


def cargar_configuracion() -> tuple[str, str]:
    """
    Carga y valida las credenciales de Azure desde el archivo .env.
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
            "Falta AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT en el archivo .env."
        )

    if not clave:
        raise ValueError(
            "Falta AZURE_DOCUMENT_INTELLIGENCE_KEY en el archivo .env."
        )

    return endpoint, clave


def buscar_primer_pdf() -> Path:
    """
    Localiza el primer PDF disponible en el banco de pruebas.
    """
    if not RUTA_DOCUMENTOS_PRUEBA.exists():
        raise FileNotFoundError(
            f"No existe la carpeta de documentos: "
            f"{RUTA_DOCUMENTOS_PRUEBA}"
        )

    archivos_pdf = sorted(
        ruta
        for ruta in RUTA_DOCUMENTOS_PRUEBA.rglob("*.pdf")
        if ruta.is_file()
    )

    if not archivos_pdf:
        raise FileNotFoundError(
            f"No se han encontrado archivos PDF en: "
            f"{RUTA_DOCUMENTOS_PRUEBA}"
        )

    return archivos_pdf[0]


def obtener_valor_campo(campo: Any) -> Any:
    """
    Obtiene un valor legible de un campo devuelto por Azure.
    """
    if campo is None:
        return None

    valor = getattr(campo, "value", None)

    if valor is not None:
        return valor

    return getattr(campo, "content", None)


def obtener_confianza(campo: Any) -> float | None:
    """
    Obtiene la confianza asociada a un campo devuelto por Azure.
    """
    if campo is None:
        return None

    return getattr(campo, "confidence", None)


def mostrar_campo(
    nombre: str,
    campos: dict[str, Any],
    clave_azure: str,
) -> None:
    """
    Muestra el valor y la confianza de un campo concreto.
    """
    campo = campos.get(clave_azure)

    print(
        f"{nombre}: {obtener_valor_campo(campo)} "
        f"(confianza: {obtener_confianza(campo)})"
    )


def serializar_json(valor: Any) -> Any:
    """
    Convierte tipos especiales a valores compatibles con JSON.

    Normalmente AnalyzeResult.as_dict() ya devuelve valores
    serializables, pero esta función actúa como protección adicional.
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


def crear_nombre_resultado(
    ruta_pdf: Path,
) -> str:
    """
    Crea un nombre seguro para el JSON original de Azure.
    """
    return f"{ruta_pdf.stem}_azure_original.json"


def guardar_respuesta_original(
    resultado: Any,
    ruta_pdf: Path,
) -> Path:
    """
    Guarda sin normalizar la respuesta completa devuelta por Azure.
    """
    RUTA_RESULTADOS_ORIGINALES.mkdir(
        parents=True,
        exist_ok=True,
    )

    ruta_salida = (
        RUTA_RESULTADOS_ORIGINALES
        / crear_nombre_resultado(ruta_pdf)
    )

    if not hasattr(resultado, "as_dict"):
        raise TypeError(
            "El resultado de Azure no dispone del método as_dict()."
        )

    datos_originales = resultado.as_dict()

    with ruta_salida.open(
        mode="w",
        encoding="utf-8",
    ) as archivo:
        json.dump(
            datos_originales,
            archivo,
            ensure_ascii=False,
            indent=2,
            default=serializar_json,
        )

    return ruta_salida


def mostrar_resumen_resultado(
    resultado: Any,
) -> None:
    """
    Muestra una selección de campos para comprobar visualmente
    la extracción básica realizada por Azure.
    """
    paginas = resultado.pages or []
    documentos = resultado.documents or []

    print("Documento procesado correctamente.")
    print(f"Páginas detectadas: {len(paginas)}")
    print(f"Documentos detectados: {len(documentos)}")

    if not documentos:
        print("Azure no ha detectado ninguna factura estructurada.")
        return

    for numero, documento in enumerate(
        documentos,
        start=1,
    ):
        print()
        print(f"DOCUMENTO {numero}")
        print("-" * 20)

        campos = documento.fields or {}

        mostrar_campo(
            nombre="Proveedor",
            campos=campos,
            clave_azure="VendorName",
        )

        mostrar_campo(
            nombre="CIF proveedor",
            campos=campos,
            clave_azure="VendorTaxId",
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
            nombre="Cliente",
            campos=campos,
            clave_azure="CustomerName",
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


def analizar_factura(
    ruta_pdf: Path,
    endpoint: str,
    clave: str,
) -> None:
    """
    Envía un PDF al modelo prebuilt-invoice de Azure,
    guarda la respuesta original completa y muestra un resumen.
    """
    cliente = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(clave),
    )

    print("PRUEBA REAL DE AZURE DOCUMENT INTELLIGENCE")
    print("------------------------------------------")
    print(f"Archivo: {ruta_pdf.name}")
    print("Modelo: prebuilt-invoice")
    print("Enviando documento a Azure...")

    with ruta_pdf.open("rb") as archivo:
        contenido_pdf = archivo.read()

    operacion = cliente.begin_analyze_document(
        model_id="prebuilt-invoice",
        body=contenido_pdf,
        content_type="application/pdf",
    )

    resultado = operacion.result()

    ruta_guardada = guardar_respuesta_original(
        resultado=resultado,
        ruta_pdf=ruta_pdf,
    )

    mostrar_resumen_resultado(resultado)

    print()
    print("RESPUESTA ORIGINAL")
    print("------------------")
    print(f"Guardada en: {ruta_guardada}")


def ejecutar() -> None:
    """
    Ejecuta la prueba real de Azure sobre el primer PDF disponible.
    """
    endpoint, clave = cargar_configuracion()
    ruta_pdf = buscar_primer_pdf()

    analizar_factura(
        ruta_pdf=ruta_pdf,
        endpoint=endpoint,
        clave=clave,
    )


if __name__ == "__main__":
    ejecutar()