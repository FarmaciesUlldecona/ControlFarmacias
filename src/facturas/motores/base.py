from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

from src.models.factura import DocumentoFacturas, serializar_valor


@dataclass(slots=True)
class InformacionMotor:
    """
    Identifica el motor de extracción utilizado.
    """

    proveedor: str
    nombre_modelo: str
    version_modelo: str | None = None


@dataclass(slots=True)
class MetricasProcesamiento:
    """
    Datos técnicos y económicos de una ejecución.
    """

    tiempo_segundos: float
    coste_estimado_eur: Decimal | None = None
    paginas_procesadas: int | None = None
    confianza_global: Decimal | None = None


@dataclass(slots=True)
class ErrorExtraccion:
    """
    Error producido durante la extracción o normalización.
    """

    codigo: str
    mensaje: str
    detalle: str | None = None
    recuperable: bool = False


@dataclass(slots=True)
class ResultadoMotor:
    """
    Resultado común devuelto por cualquier motor de IA.
    """

    archivo: str
    motor: InformacionMotor
    procesado_correctamente: bool
    fecha_procesamiento: datetime
    metricas: MetricasProcesamiento

    documento_normalizado: DocumentoFacturas | None = None
    respuesta_original: dict[str, Any] | list[Any] | str | None = None
    errores: list[ErrorExtraccion] = field(default_factory=list)

    def validar(self) -> list[str]:
        errores: list[str] = []

        if not self.archivo.strip():
            errores.append("Falta el nombre del archivo procesado.")

        if self.metricas.tiempo_segundos < 0:
            errores.append(
                "El tiempo de procesamiento no puede ser negativo."
            )

        if self.procesado_correctamente:
            if self.documento_normalizado is None:
                errores.append(
                    "Una ejecución correcta debe contener "
                    "documento_normalizado."
                )

            if self.errores:
                errores.append(
                    "Una ejecución marcada como correcta no debe contener "
                    "errores."
                )

        if not self.procesado_correctamente and not self.errores:
            errores.append(
                "Una ejecución fallida debe contener al menos un error."
            )

        if self.documento_normalizado is not None:
            errores.extend(self.documento_normalizado.validar())

        return errores

    def a_diccionario(self) -> dict[str, Any]:
        return serializar_valor(asdict(self))


class MotorExtraccionFacturas(ABC):
    """
    Contrato común para todos los motores de extracción.

    Azure, Google Document AI y OpenAI deberán implementar
    esta interfaz.
    """

    def __init__(
        self,
        informacion_motor: InformacionMotor,
    ) -> None:
        self.informacion_motor = informacion_motor

    @abstractmethod
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
        Extrae y normaliza un documento.

        Debe devolver:

        1. Documento normalizado.
        2. Respuesta original del motor.
        3. Coste estimado en euros.
        4. Confianza global, entre 0 y 1.
        """
        raise NotImplementedError

    def procesar(
        self,
        ruta_pdf: Path | str,
    ) -> ResultadoMotor:
        """
        Ejecuta un motor controlando rutas, tiempo y errores.
        """
        ruta = Path(ruta_pdf)
        inicio = perf_counter()

        if not ruta.exists():
            return self._crear_resultado_error(
                ruta=ruta,
                inicio=inicio,
                codigo="ARCHIVO_NO_ENCONTRADO",
                mensaje=f"No se encuentra el archivo: {ruta}",
            )

        if not ruta.is_file():
            return self._crear_resultado_error(
                ruta=ruta,
                inicio=inicio,
                codigo="RUTA_NO_ES_ARCHIVO",
                mensaje=f"La ruta no corresponde a un archivo: {ruta}",
            )

        if ruta.suffix.lower() != ".pdf":
            return self._crear_resultado_error(
                ruta=ruta,
                inicio=inicio,
                codigo="FORMATO_NO_ADMITIDO",
                mensaje=(
                    f"El archivo debe tener extensión PDF: {ruta.name}"
                ),
            )

        try:
            (
                documento,
                respuesta_original,
                coste_estimado,
                confianza_global,
            ) = self.extraer_documento(ruta)

            tiempo_segundos = perf_counter() - inicio

            resultado = ResultadoMotor(
                archivo=ruta.name,
                motor=self.informacion_motor,
                procesado_correctamente=True,
                fecha_procesamiento=datetime.now(timezone.utc),
                metricas=MetricasProcesamiento(
                    tiempo_segundos=tiempo_segundos,
                    coste_estimado_eur=coste_estimado,
                    paginas_procesadas=documento.numero_paginas,
                    confianza_global=confianza_global,
                ),
                documento_normalizado=documento,
                respuesta_original=respuesta_original,
                errores=[],
            )

            errores_validacion = resultado.validar()

            if errores_validacion:
                return ResultadoMotor(
                    archivo=ruta.name,
                    motor=self.informacion_motor,
                    procesado_correctamente=False,
                    fecha_procesamiento=datetime.now(timezone.utc),
                    metricas=resultado.metricas,
                    documento_normalizado=documento,
                    respuesta_original=respuesta_original,
                    errores=[
                        ErrorExtraccion(
                            codigo="RESULTADO_INVALIDO",
                            mensaje=error,
                            recuperable=False,
                        )
                        for error in errores_validacion
                    ],
                )

            return resultado

        except Exception as error:
            return self._crear_resultado_error(
                ruta=ruta,
                inicio=inicio,
                codigo="ERROR_PROCESAMIENTO",
                mensaje="El motor no ha podido procesar el documento.",
                detalle=f"{type(error).__name__}: {error}",
            )

    def _crear_resultado_error(
        self,
        ruta: Path,
        inicio: float,
        codigo: str,
        mensaje: str,
        detalle: str | None = None,
    ) -> ResultadoMotor:
        return ResultadoMotor(
            archivo=ruta.name,
            motor=self.informacion_motor,
            procesado_correctamente=False,
            fecha_procesamiento=datetime.now(timezone.utc),
            metricas=MetricasProcesamiento(
                tiempo_segundos=perf_counter() - inicio,
            ),
            documento_normalizado=None,
            respuesta_original=None,
            errores=[
                ErrorExtraccion(
                    codigo=codigo,
                    mensaje=mensaje,
                    detalle=detalle,
                    recuperable=False,
                )
            ],
        )