from pathlib import Path

import pytest

from src.facturas.motor_local.autoridad import COFARES_LOCAL_AUTHORITY
from src.facturas.motor_local.adaptadores.cofares import documentar_sentido_decision_funcional_pio_cofares
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal, hash_funcional


ROOT = Path(__file__).resolve().parents[3]
PDFS = sorted((ROOT / "pruebas/facturas/documentos/2o_gold_standard").glob("COFARES*.pdf"))


@pytest.mark.skipif(len(PDFS) != 2, reason="corpus COFARES auditado no disponible")
def test_dos_layouts_cofares_completos_y_shadow_off():
    motor = MotorDocumentoLocal(BackendPdfium())
    resultados = [motor.extraer(path) for path in PDFS]
    facturas = [r.facturas[0] for r in resultados]
    assert {f["layout"] for f in facturas} == {
        "COFARES_SUMINISTROS_V1", "COFARES_LIQUIDACIONES_COMERCIALES_V1",
    }
    assert sum(len(f["albaranes"]) for f in facturas) == 39
    assert sum(len(f["movimientos"]) for f in facturas) == 7
    assert sum(len(f["impuestos"]) for f in facturas) == 8
    assert sum(len(f["vencimientos"]) for f in facturas) == 2
    movimientos = {m["concepto_normalizado"]: m for f in facturas for m in f["movimientos"]}
    assert {k: m["sentido"] for k, m in movimientos.items()} == {
        "TOTAL_DEVOLUCIONES": "ABONO",
        "SERV_INTEGRAL_DISTRIBUCION": "CARGO",
        "DOMICILIACION_BANCARIA": "CARGO",
        "CARGO_PARAFARMACIA": "CARGO",
        "SERVICIO_COFARES_DIRECTO": "CARGO",
        "SERVICIO_LOGISTICO": "CARGO",
        "DTO__ADICIONAL_LABORATORIO": "ABONO",
    }
    assert movimientos["DOMICILIACION_BANCARIA"]["categoria"] == "SERVICIO"
    assert all(m["sentido_fuente"] == "DECISION_FUNCIONAL_PIO" for m in movimientos.values())
    assert all(m["sentido_documentacion"]["autoridad"] == "PIO" for m in movimientos.values())
    assert all(m["sentido_documentacion"]["evidencia_documental_directa"] is False for m in movimientos.values())
    assert all(m["sentido_documentacion"]["alcance"] == "SOLO_COFARES" for m in movimientos.values())
    assert movimientos["TOTAL_DEVOLUCIONES"]["importe"]["valor"] == -52.79
    assert movimientos["TOTAL_DEVOLUCIONES"]["base"]["valor"] == -47.37
    assert movimientos["SERV_INTEGRAL_DISTRIBUCION"]["base"]["valor"] == 82.5
    assert movimientos["DOMICILIACION_BANCARIA"]["base"]["valor"] == 2.89
    assert movimientos["CARGO_PARAFARMACIA"]["base"]["valor"] == 27.77
    assert movimientos["CARGO_PARAFARMACIA"]["base_calculo"]["valor"] == 370.28
    assert movimientos["SERVICIO_COFARES_DIRECTO"]["base"]["valor"] == 6.95
    assert movimientos["SERVICIO_COFARES_DIRECTO"]["base_calculo"]["valor"] == 409.11
    assert movimientos["SERVICIO_LOGISTICO"]["base"]["valor"] == 115.0
    assert movimientos["DTO__ADICIONAL_LABORATORIO"]["base"]["valor"] == -1.44
    assert all(m["mapeo_columnas"]["regla"] == "CABECERAS_Y_GEOMETRIA_VISIBLES_COFARES" for m in movimientos.values())
    suministros = next(f for f in facturas if f["layout"] == "COFARES_SUMINISTROS_V1")
    assert suministros["albaranes"][3].bases_por_categoria == {"BASE_SR": 43.54, "BASE_N": 5.94}
    liquidaciones = next(f for f in facturas if f["layout"] == "COFARES_LIQUIDACIONES_COMERCIALES_V1")
    compras = [x for x in liquidaciones["otros"] if x["tipo"] == "DESGLOSE_INFORMATIVO_COMPRAS_MENSUALES"]
    assert len(compras) == 3
    assert {k: v["valor"] for k, v in compras[-1]["columnas"].items()} == {
        "T_BASES": 350.24, "BASE_SR": 217.20, "BASE_R": 97.06, "BASE_N": 35.98,
    }
    assert all([c["estado"] for c in f["controles_conciliacion"]] == ["OK", "OK", "OK", "NO_EVALUABLE"] for f in facturas)
    assert COFARES_LOCAL_AUTHORITY is False


def test_decision_servicios_es_explicita_y_exclusiva_de_cofares():
    decision = documentar_sentido_decision_funcional_pio_cofares("Servicio COFARES futuro", "SERVICIO")
    assert decision == {
        "valor": "CARGO", "autoridad": "PIO", "fuente": "DECISION_FUNCIONAL_PIO",
        "tipo_evidencia": "DECISION_FUNCIONAL_PIO", "evidencia_documental_directa": False,
        "proveedor": "COFARES", "literal": "Servicio COFARES futuro",
        "regla": "SERVICIOS_COFARES_SON_CARGO_DECISION_PIO", "alcance": "SOLO_COFARES",
    }
    assert documentar_sentido_decision_funcional_pio_cofares("Otro concepto", "OTRO") is None


@pytest.mark.skipif(len(PDFS) != 2, reason="corpus COFARES auditado no disponible")
def test_cofares_reproducible_tres_de_tres():
    motor = MotorDocumentoLocal(BackendPdfium())
    for path in PDFS:
        hashes = [hash_funcional(motor.extraer(path)) for _ in range(3)]
        assert len(set(hashes)) == 1
