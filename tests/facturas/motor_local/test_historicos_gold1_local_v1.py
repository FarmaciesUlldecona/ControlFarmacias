from pathlib import Path

import pytest

from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.adaptadores.historicos_gold1 import (
    documentar_sentido_decision_funcional_pio_gas_casa,
    documentar_sentido_decision_funcional_pio_pierre_fabre,
)
from src.facturas.motor_local.servicio import MotorDocumentoLocal, hash_funcional


ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "pruebas/facturas/documentos"
PDFS = {
    "dermofarm": DOCS / "DERMOFARM ABONO VTO 5.8.26 PIO.pdf",
    "gas_casa": DOCS / "GAS CASA ABRIL-MAIG 2026.pdf",
    "pierre_fabre": DOCS / "PIERRE FABRE ABONO VTO 7.9.26 PIO.pdf",
    "suavinex": DOCS / "SUAVINEX VTO 15.8.26 PIO.pdf",
}


@pytest.fixture(scope="module")
def resultados():
    motor = MotorDocumentoLocal(BackendPdfium())
    return {proveedor: motor.extraer(ruta) for proveedor, ruta in PDFS.items()}


def test_cuatro_documentos_nativos_segmentados_y_reconocidos(resultados):
    assert set(resultados) == set(PDFS)
    assert all(resultado.documento["pages"] in {1, 2} for resultado in resultados.values())
    assert all(len(resultado.segmentos) == 1 for resultado in resultados.values())
    assert all(resultado.segmentos[0].estado == "DETERMINISTA" for resultado in resultados.values())
    assert all(len(resultado.facturas) == 1 for resultado in resultados.values())
    assert all(resultado.capacidades["ocr"] == "NO_NECESARIO_TEXTO_NATIVO" for resultado in resultados.values())
    assert all(resultado.capacidades["autoridad"] == "SHADOW_SIN_AUTORIDAD_PRODUCTIVA" for resultado in resultados.values())


def test_dermofarm_abono_completo(resultados):
    factura = resultados["dermofarm"].facturas[0]
    assert factura["layout"] == "DERMOFARM_ABONO_PRODUCTOS_V1"
    assert factura["cabecera"]["tipo_documento"]["valor"] == "ABONO"
    assert factura["cabecera"]["codigo_cliente"]["evidencias"]
    assert len(factura["albaranes"]) == 1
    assert factura["albaranes"][0].sentido == "ABONO"
    assert len(factura["impuestos"]) == 1
    assert len(next(o for o in factura["otros"] if o["tipo"] == "DETALLE_PRODUCTOS")["lineas"]) == 4
    assert factura["cabecera"]["forma_pago"] is None
    assert factura["vencimientos"] == []


def test_gas_casa_factura_completa_y_sentidos_decision_pio(resultados):
    factura = resultados["gas_casa"].facturas[0]
    assert factura["layout"] == "ENDESA_GAS_FACTURA_CONSUMO_V1"
    assert factura["segmento"]["paginas"] == [1, 2]
    assert len(factura["movimientos"]) == 5
    assert {m["categoria"] for m in factura["movimientos"]} == {
        "SUMINISTRO_GAS", "DESCUENTO", "ALQUILER_EQUIPO", "IMPUESTO_HIDROCARBUROS",
    }
    sentidos = {m["descripcion_literal"]["valor"]: m["sentido"] for m in factura["movimientos"]}
    assert sentidos == {
        "Término Fijo Gas": "CARGO",
        "Término Energía Gas": "CARGO",
        "Descuento promocional": "ABONO",
        "Alquiler de Equipos Gas": "CARGO",
        "Impto.HC general (#)": "CARGO",
    }
    for movimiento in factura["movimientos"]:
        assert movimiento["sentido_fuente"] == "DECISION_FUNCIONAL_PIO"
        assert movimiento["sentido_documentacion"]["autoridad"] == "PIO"
        assert movimiento["sentido_documentacion"]["fuente"] == "DECISION_FUNCIONAL_PIO"
        assert movimiento["sentido_documentacion"]["evidencia_documental_directa"] is False
        assert movimiento["sentido_documentacion"]["alcance"] == {
            "proveedor": "GAS_CASA", "layout": "ENDESA_GAS_FACTURA_CONSUMO_V1",
        }
        assert movimiento["incidencias"] == []
    assert len(factura["vencimientos"]) == 1
    assert factura["cabecera"]["periodo_facturacion_inicio"]["valor"] < factura["cabecera"]["periodo_facturacion_fin"]["valor"]
    assert factura["cabecera"]["fecha_cargo"]["valor"] == factura["vencimientos"][0]["fecha"]["valor"]
    assert factura["cabecera"]["forma_pago"]["valor"] == "Domiciliación bancaria"


def test_pierre_fabre_abono_y_descuento_no_independiente(resultados):
    factura = resultados["pierre_fabre"].facturas[0]
    assert factura["layout"] == "PIERRE_FABRE_ABONO_COMERCIAL_V1"
    assert factura["cabecera"]["tipo_documento"]["valor"] == "ABONO"
    assert factura["cabecera"]["importe_total"]["valor"] < 0
    assert factura["albaranes"][0].sentido == "ABONO"
    assert len(factura["movimientos"]) == 1
    descuento = factura["movimientos"][0]
    assert descuento["categoria"] == "DESCUENTO_COMERCIAL"
    assert descuento["sentido"] == "ABONO"
    assert descuento["sentido_fuente"] == "DECISION_FUNCIONAL_PIO"
    assert descuento["sentido_documentacion"]["autoridad"] == "PIO"
    assert descuento["sentido_documentacion"]["fuente"] == "DECISION_FUNCIONAL_PIO"
    assert descuento["sentido_documentacion"]["evidencia_documental_directa"] is False
    assert descuento["sentido_documentacion"]["alcance"] == {
        "proveedor": "PIERRE_FABRE", "layout": "PIERRE_FABRE_ABONO_COMERCIAL_V1",
    }
    assert descuento["es_movimiento_economico_independiente"] is False
    assert factura["vencimientos"][0]["importe"] is None


def test_suavinex_detalle_fiscalidad_agregada_y_punto_verde(resultados):
    factura = resultados["suavinex"].facturas[0]
    assert factura["layout"] == "SUAVINEX_FACTURA_MERCANCIA_V1"
    assert len(next(o for o in factura["otros"] if o["tipo"] == "DETALLE_PRODUCTOS")["lineas"]) == 19
    assert factura["albaranes"][0].sentido == "CARGO"
    fiscalidad = factura["impuestos"][0]
    assert factura["cabecera"]["importe_bruto"]["valor"] == factura["cabecera"]["base_imponible_total"]["valor"]
    assert fiscalidad["cuota_fiscal_resumen_visible"]["valor"] == fiscalidad["cuota_fiscal_agregada_visible"]["valor"]
    assert fiscalidad["cuota_iva"]["provenance"]["evidencia_documental_directa"] is False
    assert fiscalidad["cuota_recargo_equivalencia"]["provenance"]["evidencia_documental_directa"] is False
    punto_verde = next(o for o in factura["otros"] if o["tipo"] == "APORTACION_AMBIENTAL_INFORMATIVA")
    assert punto_verde["es_movimiento_economico_independiente"] is False
    assert punto_verde["incluido_en_base"] is True
    assert len(factura["vencimientos"]) == 1


def test_todas_las_conciliaciones_cierran_y_hay_evidencia(resultados):
    for resultado in resultados.values():
        controles = resultado.facturas[0]["controles_conciliacion"]
        assert controles
        assert all(control["estado"] == "OK" for control in controles)
        assert resultado.evidencias
        assert all(evidencia.bbox and evidencia.literal for evidencia in resultado.evidencias)


def test_decisiones_pio_historicas_no_se_generalizan_a_otros_conceptos_o_proveedores():
    assert documentar_sentido_decision_funcional_pio_gas_casa("Quota Ready") is None
    assert documentar_sentido_decision_funcional_pio_gas_casa("TOTAL DEVOLUCIONES") is None
    assert documentar_sentido_decision_funcional_pio_pierre_fabre("Descuento promocional") is None
    assert documentar_sentido_decision_funcional_pio_pierre_fabre("DESCUENTO COMERC.")["alcance"]["proveedor"] == "PIERRE_FABRE"


@pytest.mark.parametrize("proveedor", PDFS)
def test_reproducibilidad_tres_de_tres(proveedor):
    motor = MotorDocumentoLocal(BackendPdfium())
    hashes = [hash_funcional(motor.extraer(PDFS[proveedor])) for _ in range(3)]
    assert len(set(hashes)) == 1
