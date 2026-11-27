"""hefame-local 1.3.0 (FACTURAS-0, decisiones de Pio H1-H7, F0-4 y F0-6; pruebas/auditoria_hefame/DISENO.md)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.hefame_economia import CARGO_COOPERATIVO_BASE_S_R, FISCALIDAD_HEFAME
from src.facturas.motor_local.adaptadores import hefame as modulo
from src.facturas.motor_local.adaptadores.hefame import ALBARAN_RE, AdaptadorHefame
from src.facturas.motor_local.autoridad import AUTORIDADES_EXTRACTORES_LOCALES
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.segmentacion.segmentador import segmentar
from src.facturas.motor_local.servicio import MotorDocumentoLocal

ROOT = Path(__file__).resolve().parents[3]
PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/HEFAME VTO 5.8.26 PIO.pdf"  # 0563820041, 31.07.2026
con_pdf = pytest.mark.skipif(not PDF.exists(), reason="corpus externo HEFAME no disponible")


def _local():
    return MotorDocumentoLocal(BackendPdfium()).extraer(PDF)


def test_version_y_fiscalidad_f0_4():
    assert AdaptadorHefame.version == "1.3.0"
    assert FISCALIDAD_HEFAME["BASE_NO"] == (Decimal("21.0"), Decimal("5.2"))
    assert CARGO_COOPERATIVO_BASE_S_R == Decimal("80.00")


def test_sin_autoridad_productiva():
    assert all(not a.habilitada for a in AUTORIDADES_EXTRACTORES_LOCALES.values())


@pytest.mark.parametrize("numero, valido", [
    ("4127627531", True), ("7070398", True), ("912776450", True), ("914618399", True),
    ("41276275", False), ("812776450", False), ("41276275311", False), ("Q039867", False),
])
def test_numeracion_de_albaranes_disenio_4_1(numero, valido):
    assert bool(ALBARAN_RE.fullmatch(numero)) is valido


@pytest.mark.parametrize("bases, esperado", [
    ((-1.0, -2.0, 0.0, -3.0), "ABONO"), ((1.95, 0.0, 0.0, 1.95), "CARGO"),
    ((1.53, -24.72, -23.64, -46.83), None), ((0.0, 0.0, 0.0, 0.0), None),
])
def test_sentido_neto_de_abo_devo(bases, esperado):
    assert AdaptadorHefame._sentido_neto([(None, v) for v in bases]) == esperado


@con_pdf
def test_lectura_completa_y_controles_de_pagina_2():
    r = _local()
    assert r.documento["layout"] == "hefame-local" and r.documento["layout_version"] == "1.3.0"
    assert r.cabecera["numero_factura"]["valor"] == "0563820041" and r.cabecera["importe_total"]["valor"] == 677.99
    documento = BackendPdfium().cargar_pdf(PDF)
    segmentos, _ = segmentar(documento)
    controles = AdaptadorHefame().controles_pagina2(documento, segmentos)
    assert controles and all(c["resultado"] == "OK" for c in controles)
    por_codigo = {c["codigo"]: c for c in controles}
    assert por_codigo["SUMA_TOTALES_CLASE_TOTAL_FACTURA"]["tolerancia"] == "0"  # impreso: exacto
    assert por_codigo["TOTAL_FACTURA_VENCIMIENTOS"]["tolerancia"] == "0"
    assert por_codigo["BASE_NO_TOTAL_CLASE"]["tolerancia"] == "0"
    assert por_codigo["BASE_S_R_BASE"]["tolerancia"] == "0.01"  # recalculado: 0,01 (F0-6)
    assert por_codigo["BASE_NO_RE"]["tolerancia"] == "0.01"


@con_pdf
def test_cargo_cooperativo_h1_en_fin_de_mes():
    c = next(m for m in _local().movimientos if m["concepto_normalizado"] == "COMISION_HEFAME")
    assert c["importe"]["valor"] == 80.0 and c["sentido"] == "CARGO" and c["periodicidad"] == "MENSUAL_FIN_DE_MES"


@con_pdf
def test_h6_desfase_fuera_de_fin_de_mes_falla_cerrado(monkeypatch):
    monkeypatch.setattr(AdaptadorHefame, "_fecha_factura", staticmethod(lambda documento: "2026-07-30"))
    with pytest.raises(ValueError, match="DESFASE_PEDIDOS_NO_AUTORIZADO_H6"):
        _local()


@con_pdf
def test_h7_aproafa_negativo_falla_cerrado(monkeypatch):
    original = modulo.palabras_importe

    def negativo(linea):
        valores = original(linea)
        return [(p, -abs(v)) for p, v in valores] if "APROAFA" in linea.texto.upper() else valores

    monkeypatch.setattr(modulo, "palabras_importe", negativo)
    with pytest.raises(ValueError, match="APROAFA_NEGATIVO_H7"):
        _local()


@con_pdf
@pytest.mark.parametrize("desvio, falla", [(Decimal("0.01"), False), (Decimal("0.02"), True)])
def test_f0_6_tolerancia_de_0_01_en_lo_recalculado(monkeypatch, desvio, falla):
    original = AdaptadorHefame._fila_resumen

    def desviado(lineas, texto, n):
        valores = original(lineas, texto, n)
        if texto == "Desglose importes pedidos" and valores:
            return [valores[0] + desvio, *valores[1:]]
        return valores

    monkeypatch.setattr(AdaptadorHefame, "_fila_resumen", staticmethod(desviado))
    if falla:
        with pytest.raises(ValueError, match="CONTROL_PAGINA2_HEFAME:BASE_S_R_BASE"):
            _local()
    else:
        assert _local().cabecera["numero_factura"]["valor"] == "0563820041"
