from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..clasificacion_documental import TipoFacturaDocumental


class EstadoElegibilidadConciliacion(StrEnum):
    APTA = "APTA"
    NO_APTA = "NO_APTA"
    REQUIERE_REVISION = "REQUIERE_REVISION"


class RazonElegibilidadConciliacion(StrEnum):
    APTA_MERCANCIA = "APTA_MERCANCIA"
    APTA_GASTO_SERVICIO = "APTA_GASTO_SERVICIO"
    APTA_MIXTA = "APTA_MIXTA"
    FALTAN_ALBARANES_MERCANCIA = "FALTAN_ALBARANES_MERCANCIA"
    TRAZABILIDAD_SERVICIO_INSUFICIENTE = "TRAZABILIDAD_SERVICIO_INSUFICIENTE"
    TOTAL_NO_DEMOSTRADO = "TOTAL_NO_DEMOSTRADO"
    TOTAL_NO_EXPLICADO = "TOTAL_NO_EXPLICADO"
    FISCALIDAD_INCOHERENTE = "FISCALIDAD_INCOHERENTE"
    TIPO_DOCUMENTAL_NO_DEMOSTRADO = "TIPO_DOCUMENTAL_NO_DEMOSTRADO"
    DOCUMENTO_INCOMPLETO = "DOCUMENTO_INCOMPLETO"
    FARMACIA_NO_CONSISTENTE = "FARMACIA_NO_CONSISTENTE"
    FARMACIA_NO_DEMOSTRABLE = "FARMACIA_NO_DEMOSTRABLE"
    NORMALIZACION_NO_VALIDA = "NORMALIZACION_NO_VALIDA"
    INCIDENCIA_BLOQUEANTE = "INCIDENCIA_BLOQUEANTE"


@dataclass(frozen=True, slots=True)
class EvidenciasElegibilidadConciliacion:
    tipo_documental: TipoFacturaDocumental
    documento_completo_demostrado: bool
    farmacia_estado: str
    normalizacion_valida: bool
    total_demostrado: bool
    trazabilidad_mercancia: bool
    trazabilidad_servicio: bool
    total_explicado: bool
    fiscalidad_coherente: bool
    incidencia_bloqueante: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoElegibilidadConciliacion:
    estado: EstadoElegibilidadConciliacion
    razon: RazonElegibilidadConciliacion


def evaluar_elegibilidad_conciliacion(
    evidencia: EvidenciasElegibilidadConciliacion,
) -> ResultadoElegibilidadConciliacion:
    """Matriz fail-closed compartida conceptualmente con el claim PostgreSQL V2."""
    no_apta = EstadoElegibilidadConciliacion.NO_APTA
    if not evidencia.documento_completo_demostrado:
        return ResultadoElegibilidadConciliacion(no_apta, RazonElegibilidadConciliacion.DOCUMENTO_INCOMPLETO)
    if evidencia.farmacia_estado == "NO_DEMOSTRABLE":
        return ResultadoElegibilidadConciliacion(no_apta, RazonElegibilidadConciliacion.FARMACIA_NO_DEMOSTRABLE)
    if evidencia.farmacia_estado != "CONSISTENTE":
        return ResultadoElegibilidadConciliacion(no_apta, RazonElegibilidadConciliacion.FARMACIA_NO_CONSISTENTE)
    if not evidencia.normalizacion_valida:
        return ResultadoElegibilidadConciliacion(no_apta, RazonElegibilidadConciliacion.NORMALIZACION_NO_VALIDA)
    if evidencia.incidencia_bloqueante:
        return ResultadoElegibilidadConciliacion(no_apta, RazonElegibilidadConciliacion.INCIDENCIA_BLOQUEANTE)
    if evidencia.tipo_documental == TipoFacturaDocumental.TIPO_NO_DEMOSTRADO:
        return ResultadoElegibilidadConciliacion(
            EstadoElegibilidadConciliacion.REQUIERE_REVISION,
            RazonElegibilidadConciliacion.TIPO_DOCUMENTAL_NO_DEMOSTRADO,
        )
    if not evidencia.total_demostrado:
        return ResultadoElegibilidadConciliacion(no_apta, RazonElegibilidadConciliacion.TOTAL_NO_DEMOSTRADO)
    if evidencia.tipo_documental == TipoFacturaDocumental.FACTURA_MERCANCIA:
        razon = (
            RazonElegibilidadConciliacion.APTA_MERCANCIA
            if evidencia.trazabilidad_mercancia
            else RazonElegibilidadConciliacion.FALTAN_ALBARANES_MERCANCIA
        )
        return ResultadoElegibilidadConciliacion(
            EstadoElegibilidadConciliacion.APTA if evidencia.trazabilidad_mercancia else no_apta,
            razon,
        )
    if evidencia.tipo_documental == TipoFacturaDocumental.FACTURA_MIXTA and not evidencia.trazabilidad_mercancia:
        return ResultadoElegibilidadConciliacion(no_apta, RazonElegibilidadConciliacion.FALTAN_ALBARANES_MERCANCIA)
    if not evidencia.trazabilidad_servicio:
        return ResultadoElegibilidadConciliacion(no_apta, RazonElegibilidadConciliacion.TRAZABILIDAD_SERVICIO_INSUFICIENTE)
    if not evidencia.fiscalidad_coherente:
        return ResultadoElegibilidadConciliacion(no_apta, RazonElegibilidadConciliacion.FISCALIDAD_INCOHERENTE)
    if not evidencia.total_explicado:
        return ResultadoElegibilidadConciliacion(no_apta, RazonElegibilidadConciliacion.TOTAL_NO_EXPLICADO)
    razon = (
        RazonElegibilidadConciliacion.APTA_MIXTA
        if evidencia.tipo_documental == TipoFacturaDocumental.FACTURA_MIXTA
        else RazonElegibilidadConciliacion.APTA_GASTO_SERVICIO
    )
    return ResultadoElegibilidadConciliacion(EstadoElegibilidadConciliacion.APTA, razon)
