"""ABONOS CLUBS (DECISION DE PIO, 2026-11-24; adaptador alliance-local 1.3.2; caso 08006123).

"ABONOS CLUBS" es ABONO solo si el importe de su fila es negativo; si no, el sentido sigue null (falla cerrado). El
sentido sale del literal decidido por Pio, no del signo (el signo es solo la condicion). Las decisiones previas
(SERVICIO BASICO y CONDIC. COMERCIAL -> CARGO) no cambian. PDF real: espejo local de Drive, solo lectura; sin el
fichero, el test se salta. Sin produccion, Supabase ni Farmatic.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.alliance import (
    AdaptadorAlliance,
    documentar_sentido_decision_funcional_pio,
)
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal

PDF_08006123 = Path(r"C:\GoogleDrive\FACTURES PIO\MAIG 26\3A DESENA\ALLIANCE VTO 20.7-6.8-6.9-20.10 PIO.pdf")


def test_version_1_3_2():
    assert AdaptadorAlliance.version == "1.3.2"


def test_abonos_clubs_con_importe_negativo_es_abono():
    decision = documentar_sentido_decision_funcional_pio("ABONOS CLUBS", -1582.29)
    assert decision["valor"] == "ABONO"
    assert decision["literal_autorizado"] == "ABONOS CLUBS"
    assert decision["provenance"]["condicion"] == "IMPORTE_FILA_NEGATIVO"
    assert decision["provenance"]["inferencia_por_signo"] is False


@pytest.mark.parametrize("importe", [1582.29, 0.0, None])
def test_abonos_clubs_sin_importe_negativo_falla_cerrado(importe):
    assert documentar_sentido_decision_funcional_pio("ABONOS CLUBS", importe) is None


@pytest.mark.parametrize("literal", ["ABONOS CLUB", "ABONO CLUBS", "ABONOS CLUBS EXTRA"])
def test_solo_el_literal_exacto(literal):
    assert documentar_sentido_decision_funcional_pio(literal, -10.0) is None


@pytest.mark.parametrize("importe", [None, 31.46, -5.0])
def test_decisiones_previas_sin_cambios(importe):
    for literal in ("SERVICIO BASICO", "CONDIC. COMERCIAL"):
        decision = documentar_sentido_decision_funcional_pio(literal, importe)
        assert decision["valor"] == "CARGO" and "condicion" not in decision["provenance"]


def test_pdf_real_08006123_abonos_clubs_sale_abono():
    if not PDF_08006123.exists():
        pytest.skip(f"espejo local ausente: {PDF_08006123}")
    resultado = MotorDocumentoLocal(BackendPdfium()).extraer(PDF_08006123)
    [factura] = [f for f in resultado.facturas if f["segmento"]["identidad"] == "08006123"]
    [mov] = [m for m in factura["movimientos"] if m["descripcion_literal"]["valor"] == "ABONOS CLUBS"]
    assert mov["importe"]["valor"] == -1582.29
    assert mov["categoria"] == "ABONO_COMERCIAL"
    assert (mov["sentido"], mov["sentido_fuente"]) == ("ABONO", "DECISION_FUNCIONAL_PIO")
    assert mov["sentido_documentacion"]["provenance"]["condicion"] == "IMPORTE_FILA_NEGATIVO"
    # Ningun otro movimiento del documento queda con sentido null.
    assert all(m["sentido"] in ("CARGO", "ABONO") for f in resultado.facturas for m in f["movimientos"])
