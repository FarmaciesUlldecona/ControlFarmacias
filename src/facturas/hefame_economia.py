from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


CENTIMOS = Decimal("0.01")
CUATRO_DECIMALES = Decimal("0.0001")

FISCALIDAD_HEFAME = {
    "BASE_S_R": (Decimal("4.0"), Decimal("0.5")),
    "BASE_RE": (Decimal("10.0"), Decimal("1.4")),
    "BASE_NO": (Decimal("21.0"), Decimal("1.2")),
}


def derivar_magnitud_comparable_hefame(
    base_neta: Decimal | int | float | str,
    categoria_fiscal: str,
) -> dict[str, Decimal | str]:
    """Conserva la base y deriva el bruto con un único redondeo monetario."""
    if categoria_fiscal not in FISCALIDAD_HEFAME:
        raise ValueError("CATEGORIA_FISCAL_HEFAME_NO_DEMOSTRADA")
    base = Decimal(str(base_neta)).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
    iva_pct, re_pct = FISCALIDAD_HEFAME[categoria_fiscal]
    iva = (base * iva_pct / Decimal("100")).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
    recargo = (base * re_pct / Decimal("100")).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
    comparable = (
        base * (Decimal("100") + iva_pct + re_pct) / Decimal("100")
    ).quantize(CENTIMOS, rounding=ROUND_HALF_UP)
    return {
        "magnitud_documental": "BASE_NETA",
        "categoria_fiscal": categoria_fiscal,
        "base_neta": base,
        "iva_pct": iva_pct,
        "re_pct": re_pct,
        "importe_iva_derivado": iva,
        "importe_re_derivado": recargo,
        "importe_comparable_operativo": comparable,
    }


def detectar_comision_hefame(
    subtotal_por_categoria: dict[str, Decimal | int | float | str],
    detalle_por_categoria: dict[str, Decimal | int | float | str],
) -> dict[str, Decimal | str] | None:
    """Reconoce solo un desfase positivo y exclusivo de Base S.R."""
    diferencias = {
        categoria: (
            Decimal(str(subtotal_por_categoria[categoria]))
            - Decimal(str(detalle_por_categoria[categoria]))
        ).quantize(CENTIMOS, rounding=ROUND_HALF_UP)
        for categoria in FISCALIDAD_HEFAME
    }
    if diferencias["BASE_S_R"] <= 0 or any(
        diferencias[categoria] != 0 for categoria in ("BASE_RE", "BASE_NO")
    ):
        return None
    return {
        "concepto": "COMISION_HEFAME",
        "tipo": "CARGO",
        "sentido": "CARGO",
        "periodicidad": "NO_DEMOSTRADA",
        **derivar_magnitud_comparable_hefame(diferencias["BASE_S_R"], "BASE_S_R"),
    }


def evaluar_conciliabilidad_operativa_hefame(estados: list[str] | tuple[str, ...]) -> dict[str, object]:
    exactos = sum(estado == "EXACTO_ECONOMICO" for estado in estados)
    total = len(estados)
    completa = total > 0 and exactos == total
    return {
        "matches_validos": exactos,
        "total_referencias": total,
        "conciliacion_operativa": "COMPLETA" if completa else ("PARCIAL" if exactos else "NO_DEMOSTRADA"),
        "decision": "CONCILIABLE_AUTOMATICAMENTE" if completa else "PENDIENTE_CONCILIAR",
    }
