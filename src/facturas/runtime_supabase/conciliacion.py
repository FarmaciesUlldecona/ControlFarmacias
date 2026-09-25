from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

from ..clasificacion_documental import TipoFacturaDocumental
from ..hefame_economia import derivar_magnitud_comparable_hefame
from .modelos import (
    DetalleConciliacion,
    ResultadoConciliacion,
    TipoRelacionConciliacion,
    conservar_id_proveedor,
)


CUATRO_DECIMALES = Decimal("0.0001")
TOLERANCIA_POR_DEFECTO = Decimal("0.0500")
VENTANA_FECHA_DIAS = 15
PROVEEDOR_CANONICO_ALLIANCE = "ALLIANCEHEALTHCARECENCORA"
PROVEEDOR_CANONICO_HEFAME_MERCANCIA = "HEFAMEMERCANCIA"
_ALIASES_ALLIANCE_AUTORIZADOS = frozenset({
    "SAFA",
    "1SAFA",
    "ALLIANCE",
    "ALLIANCEHEALTHCARE",
    "ALLIANCEHEALTHCAREESPANA",
    "CENCORA",
})
_ALIASES_HEFAME_MERCANCIA_AUTORIZADOS = frozenset({
    "3HEFAME",
    "HEFAME",
    "HDADFMCTCAMEDITSCL",
})


@dataclass(frozen=True, slots=True)
class AlbaranDocumentalTrabajo:
    id: str
    numero: str | None
    fecha: date | None
    importe: Decimal | None
    sentido: str | None = None
    magnitud_documental: str | None = None
    categoria_fiscal: str | None = None
    iva_pct: Decimal | None = None
    re_pct: Decimal | None = None
    importe_iva_derivado: Decimal | None = None
    importe_re_derivado: Decimal | None = None
    importe_comparable_operativo: Decimal | None = None
    provenance: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MovimientoDocumentalTrabajo:
    id: str
    concepto_literal: str
    tipo: str
    sentido: str | None
    importe: Decimal | None = None
    base: Decimal | None = None
    provenance: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AjusteDocumentalTrabajo:
    concepto_literal: str
    importe: Decimal
    provenance: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CandidatoAlbaranSupabase:
    id_contador: int
    farmacia: str
    id_proveedor: str
    proveedor: str
    numero_albaran: str
    fecha: date
    importe_puc: Decimal | None
    importe_pvp: Decimal | None
    estado: str | None = None

    def __post_init__(self) -> None:
        conservar_id_proveedor(self.id_proveedor)


@dataclass(frozen=True, slots=True)
class ResultadoBusquedaAlbaran:
    estado: str
    candidato: CandidatoAlbaranSupabase | None
    importe_compatible: Decimal | None
    coincidencia_numero: str
    candidatos_proveedor: int
    candidatos_fecha: int
    candidatos_importe: int
    candidatos_finales: int


def canonicalizar_proveedor(valor: str | None) -> str | None:
    """Identidad conservadora, incluida la equivalencia Alliance autorizada por Pio."""
    if valor is None:
        return None
    texto = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode().upper()
    tokens = re.findall(r"[A-Z0-9]+", texto)
    while tokens and tokens[-1] in {"SA", "SAU", "SL", "SLU", "SRL"}:
        tokens.pop()
    for suffix in (("S", "A", "U"), ("S", "L", "U"), ("S", "A"), ("S", "L")):
        if tuple(tokens[-len(suffix):]) == suffix:
            del tokens[-len(suffix):]
            break
    normalizado = "".join(tokens) or None
    if normalizado in _ALIASES_ALLIANCE_AUTORIZADOS:
        return PROVEEDOR_CANONICO_ALLIANCE
    if normalizado in _ALIASES_HEFAME_MERCANCIA_AUTORIZADOS:
        return PROVEEDOR_CANONICO_HEFAME_MERCANCIA
    return normalizado


def normalizar_numero_albaran(valor: str | None) -> str | None:
    if valor is None:
        return None
    normalizado = "".join(re.findall(r"[A-Z0-9]+", unicodedata.normalize("NFKD", valor).upper()))
    return normalizado or None


def _id_proveedor_comparable(valor: str | None) -> str | None:
    """R9 (2AV): solo para comparar; '2', '0002' y '0002 ' son el mismo proveedor.

    El literal se conserva en datos y persistencia (``conservar_id_proveedor``).
    """
    if valor is None:
        return None
    texto = valor.strip()
    if texto.isdigit():
        return texto.lstrip("0") or "0"
    return texto or None


def comparar_numeros_albaran(documental: str | None, operacional: str | None) -> str:
    izquierda = normalizar_numero_albaran(documental)
    derecha = normalizar_numero_albaran(operacional)
    if izquierda is None or derecha is None:
        return "NO_DISPONIBLE"
    if izquierda == derecha:
        return "EXACTA"
    return "DIFERENTE"


def _importe_compatible(
    documental: Decimal,
    candidato: CandidatoAlbaranSupabase,
    tolerancia: Decimal,
    *,
    comparar_magnitud: bool = False,
) -> Decimal | None:
    esperado = abs(dinero(documental)) if comparar_magnitud else dinero(documental)
    compatibles = []
    for valor in (candidato.importe_puc, candidato.importe_pvp):
        if valor is None:
            continue
        candidato_normalizado = dinero(valor)
        comparable = abs(candidato_normalizado) if comparar_magnitud else candidato_normalizado
        if abs(comparable - esperado) <= tolerancia:
            compatibles.append(comparable)
    return min(compatibles, key=lambda value: abs(value - esperado)) if compatibles else None


def buscar_candidato_albaran(
    documental: AlbaranDocumentalTrabajo,
    candidatos: Iterable[CandidatoAlbaranSupabase],
    *,
    proveedor_literal: str | None,
    farmatic_id_proveedor: str | None = None,
    tolerancia: Decimal | int | float | str = TOLERANCIA_POR_DEFECTO,
    ventana_dias: int = VENTANA_FECHA_DIAS,
) -> ResultadoBusquedaAlbaran:
    """Selecciona solo una coincidencia demostrable; nunca resuelve ambiguedad por orden."""
    tolerancia_decimal = dinero(tolerancia)
    if tolerancia_decimal < 0 or ventana_dias < 0:
        raise ValueError("tolerancia y ventana deben ser no negativas")
    rows = tuple(candidatos)
    provider_key = canonicalizar_proveedor(proveedor_literal)
    provider_id = conservar_id_proveedor(farmatic_id_proveedor)
    if provider_id is not None:
        provider_comparable = _id_proveedor_comparable(provider_id)
        by_provider = [
            row for row in rows
            if provider_comparable is not None
            and _id_proveedor_comparable(row.id_proveedor) == provider_comparable
        ]
    elif provider_key is not None:
        by_provider = [row for row in rows if canonicalizar_proveedor(row.proveedor) == provider_key]
    else:
        by_provider = []
    by_date = [
        row for row in by_provider
        if documental.fecha is not None and abs((row.fecha - documental.fecha).days) <= ventana_dias
    ]
    amounts = []
    importe_para_matching = (
        documental.importe_comparable_operativo
        if provider_key == PROVEEDOR_CANONICO_HEFAME_MERCANCIA
        else documental.importe
    )
    if importe_para_matching is not None:
        expected = dinero(importe_para_matching)
        for row in by_date:
            compatible = _importe_compatible(
                expected,
                row,
                tolerancia_decimal,
                comparar_magnitud=documental.sentido == "ABONO",
            )
            if compatible is not None:
                amounts.append((row, compatible, comparar_numeros_albaran(documental.numero, row.numero_albaran)))
    if provider_key == PROVEEDOR_CANONICO_HEFAME_MERCANCIA:
        exact_number = [
            row for row in by_provider
            if comparar_numeros_albaran(documental.numero, row.numero_albaran) == "EXACTA"
        ]
        if not exact_number:
            return ResultadoBusquedaAlbaran(
                "NUMERO_AUSENTE", None, None, "DIFERENTE",
                len(by_provider), len(by_date), len(amounts), 0,
            )
        exact_in_window = [row for row in by_date if row in exact_number]
        if not exact_in_window or importe_para_matching is None:
            return ResultadoBusquedaAlbaran(
                "NO_DEMOSTRABLE", None, None, "EXACTA",
                len(by_provider), len(by_date), len(amounts), 0,
            )
        finalists = [item for item in amounts if item[2] == "EXACTA"]
        if not finalists:
            return ResultadoBusquedaAlbaran(
                "NUMERO_EXACTO_ECONOMIA_INCOMPATIBLE",
                exact_in_window[0] if len(exact_in_window) == 1 else None,
                None, "EXACTA", len(by_provider), len(by_date), len(amounts), 0,
            )
    else:
        with_number = [item for item in amounts if item[2] == "EXACTA"]
        finalists = with_number if with_number else amounts
    if finalists:
        expected_comparable = abs(expected) if documental.sentido == "ABONO" else expected
        diferencia_minima = min(abs(item[1] - expected_comparable) for item in finalists)
        closest_amount = [
            item for item in finalists
            if abs(item[1] - expected_comparable) == diferencia_minima
        ]
        finalists = closest_amount
    with_exact_date = [item for item in finalists if documental.fecha == item[0].fecha]
    if len(with_exact_date) == 1:
        finalists = with_exact_date
    if len(finalists) == 1:
        row, amount, number_match = finalists[0]
        return ResultadoBusquedaAlbaran(
            "EXACTO_ECONOMICO" if provider_key == PROVEEDOR_CANONICO_HEFAME_MERCANCIA else "MATCH_UNICO",
            row, amount, number_match,
            len(by_provider), len(by_date), len(amounts), 1,
        )
    return ResultadoBusquedaAlbaran(
        "AMBIGUO" if len(finalists) > 1 else "SIN_COINCIDENCIA",
        None,
        None,
        "DIFERENTE" if amounts else "NO_EVALUADO",
        len(by_provider),
        len(by_date),
        len(amounts),
        len(finalists),
    )


def detalle_desde_busqueda(
    documental: AlbaranDocumentalTrabajo,
    resultado: ResultadoBusquedaAlbaran,
) -> DetalleConciliacion:
    if resultado.candidato is None or resultado.importe_compatible is None:
        return DetalleConciliacion(
            tipo_relacion=TipoRelacionConciliacion.SIN_COINCIDENCIA,
            importe_aplicado=Decimal("0"),
            factura_albaran_extraido_id=documental.id,
            provenance={
                "fuente": "ALBARANES_SUPABASE",
                "estado_matching": resultado.estado,
                "candidatos_finales": resultado.candidatos_finales,
                "sentido_documental": documental.sentido,
            },
        )
    candidate = resultado.candidato
    return DetalleConciliacion(
        tipo_relacion=TipoRelacionConciliacion.UNO_A_UNO,
        importe_aplicado=(
            -abs(resultado.importe_compatible)
            if documental.sentido == "ABONO"
            else resultado.importe_compatible
        ),
        albaran_farmacia=candidate.farmacia,
        albaran_id_contador=candidate.id_contador,
        factura_albaran_extraido_id=documental.id,
        coincidencia_numero_literal=resultado.coincidencia_numero == "EXACTA",
        provenance={
            "fuente": "ALBARANES_SUPABASE",
            "estado_matching": resultado.estado,
            "coincidencia_numero": resultado.coincidencia_numero,
            "numero_documental": documental.numero,
            "numero_operacional": candidate.numero_albaran,
            "id_proveedor": candidate.id_proveedor,
            "fecha_documental": documental.fecha.isoformat() if documental.fecha else None,
            "fecha_operacional": candidate.fecha.isoformat(),
            "sentido_documental": documental.sentido,
        },
    )


def dinero(valor: Decimal | int | float | str) -> Decimal:
    return Decimal(str(valor)).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def _importe_con_sentido(valor: Decimal, sentido: str) -> Decimal:
    magnitud = abs(dinero(valor))
    return magnitud if sentido == "CARGO" else -magnitud


def conciliar_movimientos_documentales(
    importe_factura: Decimal | int | float | str,
    movimientos: Iterable[MovimientoDocumentalTrabajo],
    *,
    ajustes: Iterable[AjusteDocumentalTrabajo] = (),
    tolerancia: Decimal | int | float | str = TOLERANCIA_POR_DEFECTO,
) -> ResultadoConciliacion:
    """Concilia servicios por importes o, si todos faltan, por bases y fiscalidad visible."""
    movimientos = tuple(movimientos)
    ajustes = tuple(ajustes)
    detalles = construir_detalles_movimientos_documentales(movimientos, ajustes=ajustes)
    if detalles is None:
        factura = dinero(importe_factura)
        return ResultadoConciliacion(
            importe_factura=factura,
            importe_explicado=Decimal("0.0000"),
            diferencia=factura,
            tolerancia=dinero(tolerancia),
            resultado="PENDIENTE_REVISION_PIO",
            detalles=(),
        )
    return conciliar_importes(importe_factura, detalles, tolerancia=tolerancia)


def construir_detalles_movimientos_documentales(
    movimientos: Iterable[MovimientoDocumentalTrabajo],
    *,
    ajustes: Iterable[AjusteDocumentalTrabajo] = (),
) -> tuple[DetalleConciliacion, ...] | None:
    """Materializa detalles sin inventar importes; ``None`` indica traza insuficiente."""
    movimientos = tuple(movimientos)
    ajustes = tuple(ajustes)
    sentidos_completos = all(m.sentido in {"CARGO", "ABONO"} for m in movimientos)
    por_importes = bool(movimientos) and all(m.importe is not None for m in movimientos)
    por_bases = bool(movimientos) and all(m.importe is None and m.base is not None for m in movimientos)
    if not sentidos_completos or not (por_importes or por_bases):
        return None

    detalles = []
    for movimiento in movimientos:
        valor = movimiento.importe if por_importes else movimiento.base
        assert valor is not None and movimiento.sentido is not None
        detalles.append(DetalleConciliacion(
            tipo_relacion=TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC,
            importe_aplicado=_importe_con_sentido(valor, movimiento.sentido),
            factura_movimiento_id=movimiento.id,
            provenance={
                **dict(movimiento.provenance or {}),
                "fuente": "MOVIMIENTO_DOCUMENTAL",
                "concepto_literal": movimiento.concepto_literal,
                "tipo": movimiento.tipo,
                "sentido": movimiento.sentido,
                "magnitud_usada": "IMPORTE" if por_importes else "BASE",
            },
        ))
    if por_bases:
        detalles.extend(
            DetalleConciliacion(
                tipo_relacion=TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC,
                importe_aplicado=dinero(ajuste.importe),
                provenance={
                    **dict(ajuste.provenance),
                    "fuente": "FISCALIDAD_AJUSTE_DOCUMENTAL",
                    "concepto_literal": ajuste.concepto_literal,
                },
            )
            for ajuste in ajustes
        )
    return tuple(detalles)


def conciliar_factura_documental(
    tipo: TipoFacturaDocumental | str,
    importe_factura: Decimal | int | float | str,
    *,
    detalles_albaranes: Iterable[DetalleConciliacion] = (),
    movimientos: Iterable[MovimientoDocumentalTrabajo] = (),
    ajustes: Iterable[AjusteDocumentalTrabajo] = (),
    tolerancia: Decimal | int | float | str = TOLERANCIA_POR_DEFECTO,
) -> ResultadoConciliacion:
    """Despacha la conciliacion por el tipo demostrado y suma ambos bloques en mixtas."""
    tipo = TipoFacturaDocumental(tipo)
    detalles_albaranes = tuple(detalles_albaranes)
    movimientos = tuple(movimientos)
    ajustes = tuple(ajustes)
    if tipo == TipoFacturaDocumental.TIPO_NO_DEMOSTRADO:
        factura = dinero(importe_factura)
        return ResultadoConciliacion(
            importe_factura=factura, importe_explicado=Decimal("0.0000"),
            diferencia=factura, tolerancia=dinero(tolerancia),
            resultado="PENDIENTE_REVISION_PIO", detalles=(),
        )
    if tipo == TipoFacturaDocumental.FACTURA_MERCANCIA:
        return conciliar_importes(importe_factura, detalles_albaranes, tolerancia=tolerancia)
    movimientos_resultado = conciliar_movimientos_documentales(
        importe_factura if tipo == TipoFacturaDocumental.FACTURA_GASTO_SERVICIO else 0,
        movimientos,
        ajustes=ajustes,
        tolerancia=tolerancia,
    )
    if movimientos_resultado.resultado == "PENDIENTE_REVISION_PIO":
        factura = dinero(importe_factura)
        return ResultadoConciliacion(
            importe_factura=factura, importe_explicado=Decimal("0.0000"),
            diferencia=factura, tolerancia=dinero(tolerancia),
            resultado="PENDIENTE_REVISION_PIO", detalles=(),
        )
    if tipo == TipoFacturaDocumental.FACTURA_GASTO_SERVICIO:
        return movimientos_resultado
    return conciliar_importes(
        importe_factura,
        (*detalles_albaranes, *movimientos_resultado.detalles),
        tolerancia=tolerancia,
    )


def conciliar_importes(
    importe_factura: Decimal | int | float | str,
    detalles: Iterable[DetalleConciliacion],
    *,
    tolerancia: Decimal | int | float | str = TOLERANCIA_POR_DEFECTO,
) -> ResultadoConciliacion:
    tolerancia_decimal = dinero(tolerancia)
    if tolerancia_decimal < 0:
        raise ValueError("La tolerancia no puede ser negativa")
    detalles_tuple = tuple(detalles)
    factura = dinero(importe_factura)
    explicado = sum(
        (dinero(detalle.importe_aplicado) for detalle in detalles_tuple),
        Decimal("0.0000"),
    ).quantize(CUATRO_DECIMALES)
    diferencia = (factura - explicado).quantize(CUATRO_DECIMALES)
    resultado = (
        "CONCILIADA"
        if abs(diferencia) <= tolerancia_decimal
        else "DIFERENCIA"
    )
    return ResultadoConciliacion(
        importe_factura=factura,
        importe_explicado=explicado,
        diferencia=diferencia,
        tolerancia=tolerancia_decimal,
        resultado=resultado,
        detalles=detalles_tuple,
    )
