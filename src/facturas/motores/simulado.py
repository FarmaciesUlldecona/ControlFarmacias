from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from time import sleep
from typing import Any

from src.facturas.motores.base import (
    InformacionMotor,
    MotorExtraccionFacturas,
)
from src.models.factura import (
    DestinatarioFactura,
    DocumentoFacturas,
    FacturaNormalizada,
)


class MotorSimulado(MotorExtraccionFacturas):
    """
    Motor de prueba sin conexión a servicios externos.

    Permite comprobar la infraestructura común antes de
    implementar Azure, Google Document AI y OpenAI.
    """

    def __init__(self) -> None:
        super().__init__(
            informacion_motor=InformacionMotor(
                proveedor="SIMULADO",
                nombre_modelo="motor-pruebas",
                version_modelo="1.0",
            )
        )

    def extraer_documento(
        self,
        ruta_pdf: Path,
    ) -> tuple[
        DocumentoFacturas,
        dict[str, Any] | list[Any] | str | None,
        Decimal | None,
        Decimal | None,
    ]:
        """
        Genera un resultado ficticio válido para probar
        el flujo completo de procesamiento.
        """
        sleep(0.1)

        factura = FacturaNormalizada(
            tipo_documento="FACTURA",
            categoria="PRUEBA",
            requiere_conciliacion_albaranes=False,
            pagina_inicio=1,
            pagina_fin=1,
            proveedor_nombre="PROVEEDOR SIMULADO",
            proveedor_cif="B12345678",
            numero_factura="SIM-0001",
            fecha_factura=None,
            base_imponible_total=Decimal("100.00"),
            iva_total=Decimal("21.00"),
            recargo_equivalencia_total=Decimal("0.00"),
            importe_total=Decimal("121.00"),
            vencimientos=[],
            impuestos=[],
            albaranes=[],
            ajustes=[],
            destinatario=DestinatarioFactura(
                id_farmacia="PIO",
                nombre="FARMACIA PIO PUIG",
                cif="40901058C",
                metodo_identificacion="CIF",
            ),
        )

        documento = DocumentoFacturas(
            archivo=ruta_pdf.name,
            tipo_contenido="PDF_DIGITAL",
            numero_paginas=1,
            necesita_lectura_visual=False,
            cantidad_documentos_esperados=1,
            facturas=[factura],
        )

        respuesta_original = {
            "motor": "simulado",
            "archivo": ruta_pdf.name,
            "resultado": "correcto",
        }

        coste_estimado = Decimal("0.00")
        confianza_global = Decimal("0.99")

        return (
            documento,
            respuesta_original,
            coste_estimado,
            confianza_global,
        )