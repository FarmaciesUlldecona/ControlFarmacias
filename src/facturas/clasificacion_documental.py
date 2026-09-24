from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Mapping


class TipoFacturaDocumental(StrEnum):
    FACTURA_MERCANCIA = "FACTURA_MERCANCIA"
    FACTURA_GASTO_SERVICIO = "FACTURA_GASTO_SERVICIO"
    FACTURA_MIXTA = "FACTURA_MIXTA"
    TIPO_NO_DEMOSTRADO = "TIPO_NO_DEMOSTRADO"


@dataclass(frozen=True, slots=True)
class ClasificacionDocumental:
    tipo: TipoFacturaDocumental
    mercancia_demostrada: bool
    gasto_servicio_demostrado: bool
    requiere_revision: bool
    regla: str = "CONTENIDO_DOCUMENTAL_ALBARANES_Y_MOVIMIENTOS_V1"


_MOVIMIENTOS_MERCANCIA = {"DEVOLUCION_MERCANCIA"}
_MOVIMIENTOS_GASTO_SERVICIO = {
    "SERVICIO",
    "CONDICION_COMERCIAL",
    "CONDICION_COOPERATIVA",
    "DESCUENTO",
    "ABONO_COMERCIAL",
    "BONIFICACION",
    "RAPPEL",
}


def _valor(valor: Any) -> Any:
    if isinstance(valor, Mapping) and "valor" in valor:
        return valor["valor"]
    return getattr(valor, "value", valor)


def clasificar_factura_por_contenido(
    albaranes: Iterable[Any],
    movimientos: Iterable[Any],
    *,
    tipo_funcional: str | None = None,
) -> ClasificacionDocumental:
    """Clasifica por colecciones documentales, nunca por nombre de archivo."""
    albaranes = tuple(albaranes)
    movimientos = tuple(movimientos)
    if tipo_funcional == "HEFAME_CONSUMIBLES":
        return ClasificacionDocumental(
            tipo=TipoFacturaDocumental.FACTURA_GASTO_SERVICIO,
            mercancia_demostrada=False,
            gasto_servicio_demostrado=True,
            requiere_revision=False,
            regla="DECISION_FUNCIONAL_PIO_HEFAME_CONSUMIBLES_SIN_ALBARAN_OPERATIVO",
        )
    if tipo_funcional == "HEFAME_MERCANCIA":
        if not albaranes:
            return ClasificacionDocumental(
                tipo=TipoFacturaDocumental.TIPO_NO_DEMOSTRADO,
                mercancia_demostrada=False,
                gasto_servicio_demostrado=False,
                requiere_revision=True,
                regla="HEFAME_MERCANCIA_REQUIERE_ALBARAN_DOCUMENTAL",
            )
        return ClasificacionDocumental(
            tipo=TipoFacturaDocumental.FACTURA_MERCANCIA,
            mercancia_demostrada=True,
            gasto_servicio_demostrado=False,
            requiere_revision=False,
            regla="HEFAME_MERCANCIA_CON_ALBARANES_DOCUMENTALES",
        )
    mercancia = bool(albaranes)
    gasto_servicio = False
    movimiento_indeterminado = False

    for movimiento in movimientos:
        if isinstance(movimiento, Mapping):
            tipo = _valor(movimiento.get("tipo", movimiento.get("categoria")))
            sentido = _valor(movimiento.get("sentido"))
        else:
            tipo = _valor(getattr(movimiento, "tipo", None))
            sentido = _valor(getattr(movimiento, "sentido", None))
        if sentido not in {"CARGO", "ABONO"}:
            movimiento_indeterminado = True
            continue
        if tipo in _MOVIMIENTOS_MERCANCIA:
            mercancia = True
        elif tipo in _MOVIMIENTOS_GASTO_SERVICIO:
            gasto_servicio = True
        else:
            movimiento_indeterminado = True

    if movimiento_indeterminado:
        tipo = TipoFacturaDocumental.TIPO_NO_DEMOSTRADO
    elif mercancia and gasto_servicio:
        tipo = TipoFacturaDocumental.FACTURA_MIXTA
    elif mercancia:
        tipo = TipoFacturaDocumental.FACTURA_MERCANCIA
    elif gasto_servicio:
        tipo = TipoFacturaDocumental.FACTURA_GASTO_SERVICIO
    else:
        tipo = TipoFacturaDocumental.TIPO_NO_DEMOSTRADO
    return ClasificacionDocumental(
        tipo=tipo,
        mercancia_demostrada=mercancia,
        gasto_servicio_demostrado=gasto_servicio,
        requiere_revision=tipo == TipoFacturaDocumental.TIPO_NO_DEMOSTRADO,
    )
