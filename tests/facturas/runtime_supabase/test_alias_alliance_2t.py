from __future__ import annotations

import pytest

from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    PROVEEDOR_CANONICO_ALLIANCE,
    buscar_candidato_albaran,
    canonicalizar_proveedor,
    detalle_desde_busqueda,
)

from datetime import date
from decimal import Decimal


@pytest.mark.parametrize(
    "alias",
    [
        "SAFA",
        "1.- SAFA",
        "ALLIANCE",
        "ALLIANCE HEALTHCARE",
        "ALLIANCE HEALTHCARE ESPAÑA",
        "ALLIANCE HEALTHCARE ESPAÑA, S.A.",
        "CENCORA",
        "  alliance   healthcare españa, s. a.  ",
    ],
)
def test_alias_autorizado_resuelve_al_mismo_proveedor(alias: str) -> None:
    assert canonicalizar_proveedor(alias) == PROVEEDOR_CANONICO_ALLIANCE


@pytest.mark.parametrize(
    "otro",
    [
        "SAFA CADUCITATS I DEVOLUCIONS",
        "SAFAR",
        "ALIANZA HEALTHCARE",
        "CENCORA DISTRIBUCION AJENA",
        "LOGISTA PHARMA S.A.U.",
    ],
)
def test_no_hay_matching_difuso_ni_por_subcadena(otro: str) -> None:
    assert canonicalizar_proveedor(otro) != PROVEEDOR_CANONICO_ALLIANCE


def _candidato(contador: int, numero: str, fecha: date, importe: str) -> CandidatoAlbaranSupabase:
    return CandidatoAlbaranSupabase(
        contador, "PIO", "2", "1.- SAFA", numero, fecha,
        Decimal(importe), None, "PENDIENTE",
    )


def test_fecha_exacta_resuelve_economico_unico_sin_inventar_equivalencia_de_numero() -> None:
    documental = AlbaranDocumentalTrabajo(
        "doc-1", "08C52355", date(2026, 7, 23), Decimal("1.42"), "CARGO"
    )
    resultado = buscar_candidato_albaran(
        documental,
        [
            _candidato(1, "OTRO-1", date(2026, 7, 22), "1.42"),
            _candidato(2, "08C52355A", date(2026, 7, 23), "1.42"),
        ],
        proveedor_literal="ALLIANCE HEALTHCARE ESPAÑA, S.A.",
    )
    assert resultado.estado == "MATCH_UNICO"
    assert resultado.candidato.id_contador == 2
    assert resultado.coincidencia_numero == "DIFERENTE"


def test_abono_compara_magnitud_y_aplica_signo_documental() -> None:
    documental = AlbaranDocumentalTrabajo(
        "doc-2", "ABONO-DOCUMENTAL", date(2026, 7, 31), Decimal("-414.76"), "ABONO"
    )
    resultado = buscar_candidato_albaran(
        documental,
        [_candidato(3, "OTRO-NUMERO", date(2026, 7, 21), "414.75")],
        proveedor_literal="CENCORA",
    )
    detalle = detalle_desde_busqueda(documental, resultado)
    assert resultado.estado == "MATCH_UNICO"
    assert resultado.coincidencia_numero == "DIFERENTE"
    assert detalle.importe_aplicado == Decimal("-414.7500")


def test_diferencia_economica_minima_unica_resuelve_la_tolerancia_solapada() -> None:
    documental = AlbaranDocumentalTrabajo(
        "doc-3", "08C52355", date(2026, 7, 23), Decimal("1.42"), "CARGO"
    )
    resultado = buscar_candidato_albaran(
        documental,
        [
            _candidato(4, "08C52355A", date(2026, 7, 23), "1.42"),
            _candidato(5, "08M44966A", date(2026, 7, 23), "1.37"),
        ],
        proveedor_literal="SAFA",
    )
    assert resultado.estado == "MATCH_UNICO"
    assert resultado.candidato.id_contador == 4
    assert resultado.coincidencia_numero == "DIFERENTE"
