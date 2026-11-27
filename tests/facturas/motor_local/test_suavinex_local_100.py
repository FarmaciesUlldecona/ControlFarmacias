"""suavinex-local 1.0.0 (FACTURAS-0, fábrica de lectores; sin autoridad y sin registrar).

Usa PDF reales del espejo local si están (se saltan si no); la verdad está escrita a mano desde el PDF.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.registro import REGISTRO_ADAPTADORES_LOCALES
from src.facturas.motor_local.adaptadores.suavinex import AdaptadorSuavinex
from src.facturas.motor_local.autoridad import AUTORIDADES_EXTRACTORES_LOCALES
from src.facturas.motor_local.backend.pdfium import BackendPdfium

ESPEJO = Path(r"C:\GoogleDrive\FACTURES PIO")
# Verdad escrita a mano (verdad_conocida.json de estrategia_facturas\suavinex), por prefijo del SHA del PDF.
FACTURA_1P = ("f8ccbf1971", "JULIOL 26", [("FACTURA", "0702638508", "2026-06-19", "531.26", "139.19", "670.45",
                                            [("2026-08-19", "670.45")], ["81109681"])])
ABONO_1P = ("3f5d0257fe", "JULIOL 26", [("ABONO", "0772601174", "2026-05-20", "-10.88", "-2.85", "-13.73", [], [])])
MULTI = ("06e97d0707", "ABRIL 26", None)


def _pdf(prefijo: str, carpeta: str) -> Path | None:
    raiz = ESPEJO / carpeta
    if not raiz.exists():
        return None
    return next((p for p in raiz.rglob("*.pdf") if hashlib.sha256(p.read_bytes()).hexdigest().startswith(prefijo)), None)


def _facturas(prefijo, carpeta):
    pdf = _pdf(prefijo, carpeta)
    if pdf is None:
        pytest.skip("espejo local de Suavinex no disponible")
    documento = BackendPdfium().cargar_pdf(pdf)
    adaptador = AdaptadorSuavinex()
    assert adaptador.reconocer(documento).estado == "RECONOCIDO"
    return adaptador.extraer_facturas(documento, [])


def test_version_sin_autoridad_y_sin_registrar():
    assert (AdaptadorSuavinex.id, AdaptadorSuavinex.version) == ("suavinex-local", "1.0.0")
    assert all(not a.habilitada for a in AUTORIDADES_EXTRACTORES_LOCALES.values())
    assert all(e.clase is not AdaptadorSuavinex for e in REGISTRO_ADAPTADORES_LOCALES)


@pytest.mark.parametrize("caso", [FACTURA_1P, ABONO_1P], ids=["factura", "abono"])
def test_igual_a_la_verdad_escrita_a_mano(caso):
    prefijo, carpeta, verdad = caso
    facturas = _facturas(prefijo, carpeta)
    assert len(facturas) == len(verdad)
    for f, (tipo, numero, fecha, base, cuota, total, venc, albaranes) in zip(facturas, verdad, strict=True):
        assert f["tipo_documento"]["valor"] == tipo and f["numero_factura"]["valor"] == numero
        assert f["fecha_factura"]["valor"] == fecha
        assert Decimal(f["impuestos"][0]["base"]["valor"]) == Decimal(base)
        assert Decimal(f["impuestos"][0]["cuota"]["valor"]) == Decimal(cuota)
        assert Decimal(f["totales"]["total"]["valor"]) == Decimal(total)
        assert [(v["fecha"]["valor"], v["importe"]["valor"]) for v in f["vencimientos"]] == venc
        assert [a["numero"]["valor"] for a in f["albaranes"]] == albaranes
        assert all(c["resultado"] == "OK" for c in f["controles"])


def test_pdf_con_ocho_documentos_se_segmenta_por_numero_y_paginacion():
    facturas = _facturas(*MULTI[:2])
    assert [f["numero_factura"]["valor"] for f in facturas] == [
        "0702609432", "0702613359", "0702613798", "0702614551", "0702614552", "0702621102", "0722602677", "0772600619"]
    assert [f["paginas"] for f in facturas] == [[1, 2], [3, 3], [4, 5], [6, 6], [7, 7], [8, 9], [10, 10], [11, 11]]
    assert [f["tipo_documento"]["valor"] for f in facturas][-2:] == ["ABONO", "ABONO"]


def _factura_sintetica(**cambios):
    def c(v):
        return {"valor": v}
    f = {"lineas": [{"importe": c("10.00")}, {"importe": c("5.01")}],
         "impuestos": [{"base": c("15.00"), "tipo_iva": c("21.00"), "tipo_recargo_equivalencia": c("5.20"), "cuota": c("3.93")}],
         "totales": {"importe_bruto": c("15.00"), "importe_neto": c("15.00"), "impuestos": c("3.93"), "total": c("18.93")},
         "vencimientos": [{"importe": c("18.93")}], "forma_pago_abono_a_compensar": False}
    f.update(cambios)
    return f


def test_controles_cuadran_con_redondeo_documental():
    """Σ líneas 15,01 frente a bruto 15,00: dentro de mín(0,01 × 2; 0,50) (F0-8)."""
    assert all(c["resultado"] == "OK" for c in AdaptadorSuavinex.controles(_factura_sintetica(), False))


@pytest.mark.parametrize("cambio, codigo", [
    ({"lineas": [{"importe": {"valor": "10.00"}}, {"importe": {"valor": "5.10"}}]}, "SUMA_LINEAS_IMPORTE_BRUTO"),
    ({"vencimientos": [{"importe": {"valor": "18.92"}}]}, "SUMA_VENCIMIENTOS_TOTAL"),
    ({"vencimientos": []}, "SUMA_VENCIMIENTOS_TOTAL"),
])
def test_controles_fallan_cerrado(cambio, codigo):
    fallos = {c["codigo"] for c in AdaptadorSuavinex.controles(_factura_sintetica(**cambio), False) if c["resultado"] != "OK"}
    assert codigo in fallos


def test_abono_exige_total_negativo_sin_vencimientos_y_a_compensar():
    fallos = {c["codigo"] for c in AdaptadorSuavinex.controles(_factura_sintetica(), True) if c["resultado"] != "OK"}
    assert fallos == {"ABONO_SIN_VENCIMIENTOS", "ABONO_TOTAL_NEGATIVO", "ABONO_A_COMPENSAR"}
