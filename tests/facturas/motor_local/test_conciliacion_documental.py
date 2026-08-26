from __future__ import annotations

import pytest

from src.facturas.motor_local.conciliacion import (
    ComponenteConciliacion,
    EspecificacionConciliacion,
    evaluar_conciliacion,
)


def componente(concepto, importe, *, columnas=None):
    return ComponenteConciliacion(
        concepto, importe, "SIN_MARCA_NEGATIVA", "fixture_documental", 1,
        [{"literal": str(importe), "pagina": 1}], columnas or {},
    )


def especificacion(objetivo, *componentes, columnas_objetivo=None):
    return EspecificacionConciliacion(
        "CONTROL_TEST", "SUBTOTAL_TEST",
        componente("OBJETIVO", objetivo, columnas=columnas_objetivo),
        list(componentes), {"regla_relacion": "RELACION_DOCUMENTAL_FIXTURE"},
    )


def test_conciliacion_exacta_es_ok():
    control = evaluar_conciliacion(especificacion(30, componente("A", 10), componente("B", 20)))
    assert control["estado"] == "OK"
    assert control["valor_reconstruido"] == 30.0
    assert control["diferencia"] == 0.0


@pytest.mark.parametrize(
    ("objetivo", "componente_valor", "diferencia"),
    [(30, 20, 10.0), (20, 30, -10.0)],
)
def test_conciliacion_conserva_diferencia_positiva_o_negativa(objetivo, componente_valor, diferencia):
    control = evaluar_conciliacion(especificacion(objetivo, componente("A", componente_valor)))
    assert control["estado"] == "DIFERENCIA_DOCUMENTAL"
    assert control["diferencia"] == diferencia
    assert control["concepto_origen"] is None


def test_conciliacion_no_evaluable_si_falta_componente():
    control = evaluar_conciliacion(especificacion(30, componente("A", None)))
    assert control["estado"] == "NO_EVALUABLE"
    assert control["valor_reconstruido"] is None
    assert control["incidencias"] == [{"codigo": "COMPONENTE_DOCUMENTAL_AUSENTE", "componentes": ["A"]}]


def test_conciliacion_por_columnas_localiza_diferencia():
    control = evaluar_conciliacion(especificacion(
        30,
        componente("A", 20, columnas={"BASE_A": 10, "BASE_B": 10}),
        columnas_objetivo={"BASE_A": 20, "BASE_B": 10},
    ))
    assert control["columnas"]["BASE_A"]["diferencia"] == 10.0
    assert control["columnas"]["BASE_B"]["estado"] == "OK"


def test_diferencia_solo_registra_incidencia_y_no_inventa_entidades():
    control = evaluar_conciliacion(especificacion(30, componente("A", 20)))
    assert control["incidencias"] == [{"codigo": "DIFERENCIA_CONCILIACION_NO_EXPLICADA"}]
    assert control["concepto_origen"] is None
    assert "movimiento" not in control
    assert "sentido" not in control
    assert "categoria" not in control


def test_formula_respeta_signos_documentales_numericos():
    control = evaluar_conciliacion(especificacion(
        484.64,
        componente("ALBARANES", 520.70),
        componente("ABO_DEVO", -116.32),
        componente("APROAFA", 0.26),
    ))
    assert control["formula"] == "484.64 - (520.70 - 116.32 + 0.26) = 80.00"
