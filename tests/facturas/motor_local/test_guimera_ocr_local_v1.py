from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from src.facturas.motor_local.backend.pdfium import BackendPdfiumConOcr
from src.facturas.motor_local.ocr.modelos import RegionOCR, SolicitudRegionOCR
from src.facturas.motor_local.ocr.windows_media import MotorWindowsMediaOcr
from src.facturas.motor_local.servicio import MotorDocumentoLocal


ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "pruebas/facturas/documentos/2o_gold_standard"


def _pdfs_guimera():
    if not CORPUS.exists():
        pytest.skip("corpus local externo ausente")
    pdfs = sorted(CORPUS.glob("FARMACIA GUIMER*.pdf"))
    if len(pdfs) != 2:
        pytest.skip("dos PDFs GUIMERA externos no disponibles")
    return pdfs


@pytest.fixture(scope="module")
def resultados_guimera():
    motor = MotorDocumentoLocal(BackendPdfiumConOcr())
    return [motor.extraer(path) for path in _pdfs_guimera()]


def test_api_ocr_propia_devuelve_region_sin_objetos_winrt():
    llamadas = []

    def runner(command, **kwargs):
        llamadas.append((command, kwargs))
        return SimpleNamespace(stdout=json.dumps({
            "engine": "Windows.Media.Ocr", "language": "es-ES", "text_angle": 0,
            "confidence_available": False,
            "lines": [{"text": "FACTURA 123", "words": [
                {"text": "FACTURA", "x": 1, "y": 1, "width": 20, "height": 8, "confidence": None},
                {"text": "123", "x": 24, "y": 1, "width": 8, "height": 8, "confidence": None},
            ]}],
        }))

    ocr = MotorWindowsMediaOcr(runner=runner)
    lectura = ocr.reconocer_region(
        Image.new("RGB", (100, 100), "white"),
        SolicitudRegionOCR("cabecera", 1, RegionOCR(0, 0, 100, 25), escala=2),
        100, 100,
    )
    assert lectura["texto"] == "FACTURA 123"
    assert lectura["confidence"] is None
    assert lectura["provenance"]["fuente"] == "OCR_LOCAL_SECUNDARIO"
    assert lectura["provenance"]["red"] is False
    assert llamadas[0][0][0] == "powershell.exe"
    assert all(key in llamadas[0][1] for key in ("check", "capture_output", "encoding"))


def test_dos_pdfs_guimera_reconocidos_y_segmentados(resultados_guimera):
    assert len(resultados_guimera) == 2
    for resultado in resultados_guimera:
        assert resultado.documento["layout"] == "farmacia-guimera-ocr-local"
        assert resultado.documento["ocr"]["ejecutado"] is True
        assert resultado.documento["ocr"]["red"] is False
        assert len(resultado.segmentos) == 1
        assert resultado.segmentos[0].identidad_candidata
        assert resultado.segmentos[0].estado == "DETERMINISTA"


def test_cabecera_fiscalidad_totales_y_conciliacion_completos(resultados_guimera):
    for resultado in resultados_guimera:
        factura = resultado.facturas[0]
        cabecera = factura["cabecera"]
        for rol in ("proveedor", "destinatario"):
            assert all(cabecera[rol][campo]["evidencias"] for campo in ("nombre", "nif", "direccion"))
        assert cabecera["numero_factura"]["valor"] == factura["segmento"]["identidad"]
        assert cabecera["fecha_factura"]["valor"]
        assert all(cabecera[campo]["valor"] > 0 for campo in (
            "base_imponible_total", "iva_total", "recargo_equivalencia_total", "importe_total",
        ))
        assert len(factura["impuestos"]) == 2
        assert [tax["tipo_iva"]["valor"] for tax in factura["impuestos"]] == [4.0, 10.0]
        assert all(tax["tipo_recargo_equivalencia"]["valor"] in (0.5, 1.4) for tax in factura["impuestos"])
        assert {control["estado"] for control in factura["controles_conciliacion"]} == {"OK"}
        assert factura["incidencias"] == []


def test_detalle_movimiento_y_nulls_legitimos(resultados_guimera):
    cantidades = []
    for resultado in resultados_guimera:
        factura = resultado.facturas[0]
        detalles = factura["otros"][0]["lineas"]
        cantidades.append(len(detalles))
        assert all(not row["incidencias"] for row in detalles)
        assert all(all(row[key] is not None for key in (
            "numero", "literal", "suma", "descuento", "base", "cuota_iva",
            "cuota_re", "pvf", "pvp", "concepto_literal",
        )) for row in detalles)
        assert factura["albaranes"] == []
        assert factura["vencimientos"] == []
        assert len(factura["movimientos"]) == 1
        descuento = factura["movimientos"][0]
        assert descuento["categoria"] == "DESCUENTO"
        assert descuento["sentido"] is None
        assert descuento["es_movimiento_economico_independiente"] is False
        assert factura["null_legitimos"]
    assert sorted(cantidades) == [11, 13]


def test_evidencia_ocr_y_provenance_sin_confianza_inventada(resultados_guimera):
    for resultado in resultados_guimera:
        assert resultado.evidencias
        assert {e.tipo_evidencia for e in resultado.evidencias} == {"OCR_LOCAL"}
        assert all(e.origen_autoridad == "OCR_LOCAL_SECUNDARIO" for e in resultado.evidencias)
        assert all(e.confidence is None for e in resultado.evidencias)
        assert all(e.provenance.get("gold_usado") is False for e in resultado.evidencias)
        assert resultado.facturas[0]["provenance"]["confidence_disponible"] is False


def test_implementacion_ocr_no_contiene_red_cloud_ni_ids_del_corpus():
    rutas = [
        ROOT / "src/facturas/motor_local/ocr/windows_media.py",
        ROOT / "src/facturas/motor_local/ocr/windows_media_ocr.ps1",
        ROOT / "src/facturas/motor_local/adaptadores/guimera.py",
    ]
    fuente = "\n".join(path.read_text(encoding="utf-8") for path in rutas).lower()
    assert all(token not in fuente for token in ("https://", "http://", "openai", "google", "azure"))
    assert all(path.stem.lower() not in fuente for path in _pdfs_guimera())
