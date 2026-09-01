from __future__ import annotations

from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.guimera import AdaptadorGuimera, AdaptadorGuimeraHistorico
from src.facturas.motor_local.backend.pdfium import BackendPdfiumConOcr
from src.facturas.motor_local.geometria.lineas import agrupar_por_linea
from src.facturas.motor_local.modelos import DocumentoLocal, PaginaLocal, PalabraLocal, RegionLocal
from src.facturas.motor_local.servicio import MotorDocumentoLocal


ROOT = Path(__file__).resolve().parents[3]
PDF_HISTORICO = ROOT / "pruebas/facturas/documentos/FARMACIA GUIMERA VTO 30.6.26 PIO.pdf"


@pytest.fixture(scope="module")
def resultado_historico():
    if not PDF_HISTORICO.exists():
        pytest.skip("PDF GUIMERA historico externo no disponible")
    return MotorDocumentoLocal(BackendPdfiumConOcr()).extraer(PDF_HISTORICO)


def _documento_sin_ancla_combinada():
    tokens = ["FARMACIA", "GUIMERA", "C.B.", "FACTURA", "BASE", "IMP.", "DEBE"]
    palabras = [
        PalabraLocal(token, 1, RegionLocal(10 + orden * 40, 10, 45 + orden * 40, 20), orden)
        for orden, token in enumerate(tokens, 1)
    ]
    pagina = PaginaLocal(1, 600, 800, " ".join(tokens), palabras, agrupar_por_linea(palabras), origen="OCR_LOCAL")
    return DocumentoLocal("nombre-neutral.pdf", "a" * 64, [pagina], ocr={"ejecutado": True})


def test_layout_historico_se_reconoce_por_contenido_sin_colisionar_con_actual(resultado_historico):
    assert resultado_historico.documento["layout"] == "farmacia-guimera-historico-ocr-local"
    assert resultado_historico.documento["layout_version"] == "1.0.0"
    reconocimientos = {item["adaptador"]: item["estado"] for item in resultado_historico.documento["reconocimientos"]}
    assert reconocimientos["farmacia-guimera-historico-ocr-local"] == "RECONOCIDO"
    assert reconocimientos["farmacia-guimera-ocr-local"] != "RECONOCIDO"
    assert resultado_historico.facturas[0]["layout"] == "GUIMERA_FACTURA_FORMULACION_OCR_HISTORICO_V1"


def test_totales_fiscalidad_y_diferencia_documental_historicos(resultado_historico):
    factura = resultado_historico.facturas[0]
    cabecera = factura["cabecera"]
    assert cabecera["numero_factura"]["valor"] == "509"
    assert cabecera["base_imponible_total"]["valor"] == 228.58
    assert cabecera["iva_total"]["valor"] == 12.95
    assert cabecera["recargo_equivalencia_total"]["valor"] == 1.71
    assert cabecera["importe_total"]["valor"] == 243.24
    assert [
        (tramo["tipo_iva"]["valor"], tramo["base"]["valor"], tramo["cuota_iva"]["valor"],
         tramo["tipo_recargo_equivalencia"]["valor"], tramo["cuota_recargo_equivalencia"]["valor"])
        for tramo in factura["impuestos"]
    ] == [(4.0, 165.22, 6.61, 0.5, 0.83), (10.0, 63.36, 6.34, 1.4, 0.89)]
    assert [(control["estado"], control["diferencia"]) for control in factura["controles_conciliacion"]] == [
        ("DIFERENCIA_DOCUMENTAL", -0.01),
    ]
    assert factura["incidencias"] == []


def test_descuento_y_detalle_historicos_preservados(resultado_historico):
    factura = resultado_historico.facturas[0]
    assert len(factura["movimientos"]) == 1
    descuento = factura["movimientos"][0]
    assert descuento["descripcion_literal"]["valor"] == "Dto."
    assert descuento["importe"]["valor"] == -70.31
    assert descuento["categoria"] == "DESCUENTO"
    assert descuento["sentido"] is None
    assert descuento["es_movimiento_economico_independiente"] is False
    assert descuento["importe"]["provenance"]["evidencia_documental_directa"] is False
    detalles = factura["otros"][0]["lineas"]
    assert len(detalles) == 12
    assert all(not fila["incidencias"] for fila in detalles)
    assert all(all(fila[campo] is not None for campo in (
        "numero", "literal", "suma", "descuento", "base", "cuota_iva", "cuota_re", "pvf", "pvp", "concepto_literal",
    )) for fila in detalles)
    assert round(sum(fila["descuento"]["valor"] for fila in detalles), 2) == -70.31


def test_ocr_historico_es_local_reproducible_y_con_provenance(resultado_historico):
    factura = resultado_historico.facturas[0]
    assert resultado_historico.documento["ocr"]["motor"] == "windows-media-ocr-local"
    assert resultado_historico.documento["ocr"]["red"] is False
    assert factura["provenance"]["fuente"] == "OCR_LOCAL_SECUNDARIO"
    assert factura["provenance"]["gold_usado_extraccion"] is False
    assert all(evidencia.origen_autoridad == "OCR_LOCAL_SECUNDARIO" for evidencia in resultado_historico.evidencias)
    assert all(evidencia.provenance.get("gold_usado") is False for evidencia in resultado_historico.evidencias)


def test_ancla_opcional_ausente_no_lanza_stop_iteration():
    documento = _documento_sin_ancla_combinada()
    assert AdaptadorGuimera().solicitudes_ocr(documento) == []
    assert AdaptadorGuimeraHistorico().solicitudes_ocr(documento) == []


def test_reglas_productivas_no_dependen_de_nombre_factura_ni_gold():
    fuente = (ROOT / "src/facturas/motor_local/adaptadores/guimera.py").read_text(encoding="utf-8").lower()
    assert "509" not in fuente
    assert "gold_usado_extraccion\": true" not in fuente
    assert "vto 30.6.26" not in fuente
