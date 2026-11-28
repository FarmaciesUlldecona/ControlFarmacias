"""suavinex-local 1.1.0 (FACTURAS-0, fábrica de lectores): registrado en sombra en lugar de suavinex-historico-local
(retirado), sin autoridad productiva; recoge la «Su Referencia: O-…» de cada albarán (DECISIÓN DE PIO, 2026-11-28).

Usa PDF reales del espejo local si están (se saltan si no) y el PDF de pruebas del repositorio; la verdad está escrita a
mano desde el PDF.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.completitud_documental import COBERTURA_ADAPTADORES
from src.facturas.motor_local.adaptadores import historicos_gold1
from src.facturas.motor_local.adaptadores.registro import REGISTRO_ADAPTADORES_LOCALES, entrada_por_adapter_id
from src.facturas.motor_local.adaptadores.suavinex import AdaptadorSuavinex
from src.facturas.motor_local.autoridad import AUTORIDADES_EXTRACTORES_LOCALES
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.catalogo import ProveedorLocal
from src.facturas.motor_local.comparador import comparar_pipeline_local
from src.facturas.motor_local.geometria.lineas import agrupar_por_linea
from src.facturas.motor_local.modelos import PalabraLocal, RegionLocal
from src.facturas.motor_local.servicio import MotorDocumentoLocal

ESPEJO = Path(r"C:\GoogleDrive\FACTURES PIO")
PDF_REPO = Path(__file__).resolve().parents[3] / "pruebas/facturas/documentos/SUAVINEX VTO 15.8.26 PIO.pdf"
# Verdad escrita a mano (verdad_conocida.json de estrategia_facturas\suavinex), por prefijo del SHA del PDF.
FACTURA_1P = ("f8ccbf1971", "JULIOL 26", [("FACTURA", "0702638508", "2026-06-19", "531.26", "139.19", "670.45",
                                            [("2026-08-19", "670.45")], [("81109681", "O-0553809")])])
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


def test_version_registrado_en_sombra_sin_autoridad():
    assert (AdaptadorSuavinex.id, AdaptadorSuavinex.version) == ("suavinex-local", "1.1.0")
    assert all(not a.habilitada for a in AUTORIDADES_EXTRACTORES_LOCALES.values())
    entrada = entrada_por_adapter_id("suavinex-local")
    assert entrada is not None and entrada.clase is AdaptadorSuavinex and entrada.shadow_habilitable
    assert [e.adapter_id for e in REGISTRO_ADAPTADORES_LOCALES if e.proveedor is ProveedorLocal.SUAVINEX] == [
        "suavinex-local"]
    assert COBERTURA_ADAPTADORES["suavinex-local"] == "COBERTURA_PARCIAL_FAIL_CLOSED"


def test_historico_retirado_con_su_texto_fijo():
    assert entrada_por_adapter_id("suavinex-historico-local") is None
    assert "suavinex-historico-local" not in COBERTURA_ADAPTADORES
    assert not hasattr(historicos_gold1, "AdaptadorSuavinexHistorico")
    assert "SUAVINEX" not in Path(historicos_gold1.__file__).read_text(encoding="utf-8").upper()


def test_motor_elige_suavinex_local_con_su_referencia_y_sin_completitud():
    """PDF del repositorio (siempre disponible): el registro elige suavinex-local, que falla cerrado en completitud."""
    resultado = MotorDocumentoLocal(BackendPdfium()).extraer(PDF_REPO)
    assert (resultado.documento["layout"], resultado.documento["layout_version"]) == ("suavinex-local", "1.1.0")
    assert resultado.documento_completo_demostrado is False
    [factura] = resultado.facturas
    assert factura["numero_factura"]["valor"] == "0702638508"
    [albaran] = factura["albaranes"]
    assert albaran["numero"]["valor"] == "81109681"
    referencia = albaran["su_referencia"]
    assert referencia["valor"] == referencia["literal"] == "O-0553809"
    [evidencia] = referencia["evidencias"]
    assert evidencia.regla == "REFERENCIA_TRAS_SU_REFERENCIA" and evidencia.columna == "su_referencia"
    assert factura["otros"] == []
    comparacion = comparar_pipeline_local(None, resultado)
    assert comparacion["albaranes_local"] == 1 and comparacion["resumen"]["SOLO_LOCAL"] == 1
    assert comparacion["filas"][0]["local"]["base"] == albaran["importe_base_suma_lineas"]


def _linea(*textos):
    palabras = [PalabraLocal(t, 1, RegionLocal(10 + 40 * i, 100, 40 + 40 * i, 108), i) for i, t in enumerate(textos)]
    return agrupar_por_linea(palabras)[0]


def test_su_referencia_ausente_es_none():
    linea = _linea("Pedido:", "220559274", "Albarán:", "81109681")
    assert AdaptadorSuavinex()._su_referencia(None, linea, 3) is None


@pytest.mark.parametrize("textos", [
    ("Pedido:", "220559274", "Albarán:", "81109681", "Su", "Referencia:"),
    ("Pedido:", "220559274", "Albarán:", "81109681", "Su", "Referencia:", "0553809"),
    ("Pedido:", "220559274", "Albarán:", "81109681", "Su", "Referencia:", "O-05538O9"),
    ("Pedido:", "220559274", "Albarán:", "81109681", "Referencia:", "O-0553809"),
    ("Pedido:", "220559274", "Albarán:", "81109681", "Su", "Referencia:", "O-1", "Su", "Referencia:", "O-2"),
], ids=["sin-valor", "sin-O", "letra-en-el-numero", "sin-Su", "dos-referencias"])
def test_su_referencia_ilegible_falla_cerrado(textos):
    with pytest.raises(ValueError, match="CONTROL_SUAVINEX:SU_REFERENCIA_ILEGIBLE"):
        AdaptadorSuavinex()._su_referencia(None, _linea(*textos), 3)


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
        assert [(a["numero"]["valor"], a["su_referencia"]["valor"]) for a in f["albaranes"]] == albaranes
        assert all(c["resultado"] == "OK" for c in f["controles"])


def test_pdf_con_ocho_documentos_se_segmenta_por_numero_y_paginacion():
    facturas = _facturas(*MULTI[:2])
    assert [f["numero_factura"]["valor"] for f in facturas] == [
        "0702609432", "0702613359", "0702613798", "0702614551", "0702614552", "0702621102", "0722602677", "0772600619"]
    assert [f["paginas"] for f in facturas] == [[1, 2], [3, 3], [4, 5], [6, 6], [7, 7], [8, 9], [10, 10], [11, 11]]
    assert [f["tipo_documento"]["valor"] for f in facturas][-2:] == ["ABONO", "ABONO"]
    assert [[a["su_referencia"]["valor"] for a in f["albaranes"]] for f in facturas] == [
        ["O-0506230"], ["O-0529931"], ["O-0529779"], ["O-0529779"], ["O-0530657"], ["O-0537252"], ["O-0529935"], []]


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
