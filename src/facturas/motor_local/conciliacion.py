from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


CENTIMOS = Decimal("0.01")


def _dinero(valor: float | int | Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(CENTIMOS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ComponenteConciliacion:
    concepto: str
    importe: float | None
    signo_documental: str | None
    fuente: str
    pagina: int | None
    evidencia: list[Any] = field(default_factory=list)
    columnas: dict[str, float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class EspecificacionConciliacion:
    id: str
    concepto_subtotal_objetivo: str
    objetivo: ComponenteConciliacion
    componentes: list[ComponenteConciliacion]
    provenance: dict[str, Any] = field(default_factory=dict)


def evaluar_conciliacion(especificacion: EspecificacionConciliacion) -> dict[str, Any]:
    """Compara importes documentales sin explicar ni corregir diferencias."""

    faltantes = [
        componente.concepto
        for componente in [especificacion.objetivo, *especificacion.componentes]
        if componente.importe is None
    ]
    if faltantes:
        return {
            "id": especificacion.id,
            "estado": "NO_EVALUABLE",
            "concepto_subtotal_objetivo": especificacion.concepto_subtotal_objetivo,
            "valor_objetivo": especificacion.objetivo.importe,
            "valor_reconstruido": None,
            "diferencia": None,
            "formula": None,
            "componentes": [asdict(item) for item in especificacion.componentes],
            "columnas": {},
            "evidencia": especificacion.objetivo.evidencia,
            "concepto_origen": None,
            "incidencias": [{"codigo": "COMPONENTE_DOCUMENTAL_AUSENTE", "componentes": faltantes}],
            "provenance": especificacion.provenance,
        }

    objetivo = _dinero(especificacion.objetivo.importe)
    importes = [_dinero(item.importe) for item in especificacion.componentes]
    reconstruido = sum(importes, Decimal("0.00"))
    diferencia = (objetivo - reconstruido).quantize(CENTIMOS)
    estado = "OK" if diferencia == 0 else "DIFERENCIA_DOCUMENTAL"
    incidencias = [] if estado == "OK" else [{"codigo": "DIFERENCIA_CONCILIACION_NO_EXPLICADA"}]

    columnas: dict[str, dict[str, float | str | None]] = {}
    nombres_columnas = set(especificacion.objetivo.columnas)
    for componente in especificacion.componentes:
        nombres_columnas.update(componente.columnas)
    for columna in sorted(nombres_columnas):
        valor_objetivo = especificacion.objetivo.columnas.get(columna)
        valores = [item.columnas.get(columna) for item in especificacion.componentes]
        if valor_objetivo is None or any(valor is None for valor in valores):
            columnas[columna] = {
                "estado": "NO_EVALUABLE",
                "valor_objetivo": valor_objetivo,
                "valor_reconstruido": None,
                "diferencia": None,
            }
            continue
        reconstruido_columna = sum((_dinero(valor) for valor in valores), Decimal("0.00"))
        diferencia_columna = (_dinero(valor_objetivo) - reconstruido_columna).quantize(CENTIMOS)
        columnas[columna] = {
            "estado": "OK" if diferencia_columna == 0 else "DIFERENCIA_DOCUMENTAL",
            "valor_objetivo": float(_dinero(valor_objetivo)),
            "valor_reconstruido": float(reconstruido_columna),
            "diferencia": float(diferencia_columna),
        }

    return {
        "id": especificacion.id,
        "estado": estado,
        "concepto_subtotal_objetivo": especificacion.concepto_subtotal_objetivo,
        "valor_objetivo": float(objetivo),
        "valor_reconstruido": float(reconstruido),
        "diferencia": float(diferencia),
        "formula": f"{objetivo:.2f} - ({_expresion(importes)}) = {diferencia:.2f}",
        "componentes": [asdict(item) for item in especificacion.componentes],
        "columnas": columnas,
        "evidencia": especificacion.objetivo.evidencia,
        "concepto_origen": None,
        "incidencias": incidencias,
        "provenance": especificacion.provenance,
    }


def evaluar_conciliaciones(especificaciones: list[EspecificacionConciliacion]) -> list[dict[str, Any]]:
    return [evaluar_conciliacion(item) for item in especificaciones]


def _expresion(importes: list[Decimal]) -> str:
    if not importes:
        return "0.00"
    partes = [f"{importes[0]:.2f}"]
    for importe in importes[1:]:
        operador = "+" if importe >= 0 else "-"
        partes.append(f"{operador} {abs(importe):.2f}")
    return " ".join(partes)
