from __future__ import annotations

from decimal import Decimal

import pytest

from src.facturas.normalizador_v2.contrato_luna import (
    CONTRATO_VERSION_V24, PROMPT_LUNA_V24, schema_luna_v24,
)
from src.facturas.normalizador_v2.modelos import (
    EstadoValidacion, Evidencia, FacturaNormalizada, MovimientoComercial,
    NaturalezaPrincipal, ResultadoControl, ResultadoValidacion, Sentido,
    TipoMovimiento, Totales, ValorDocumentado,
)
from src.facturas.normalizador_v2.reglas import aplicar_reglas_pequenas


def vd(valor):
    return ValorDocumentado(valor=valor, literal=str(valor), evidencia=[Evidencia(pagina=1, literal=str(valor))])


def factura(movimientos):
    return FacturaNormalizada(
        factura_id="f", naturaleza_principal=NaturalezaPrincipal.MERCANCIA,
        estado_validacion=EstadoValidacion.VALIDADA, requiere_conciliacion_albaranes=True,
        pagina_inicio=1, pagina_fin=1, totales=Totales(), movimientos_comerciales=movimientos,
        validaciones=[ResultadoValidacion(codigo="X", resultado=ResultadoControl.OK, descripcion="x", regla_version="v")],
    )


def movimiento(texto, *, sentido=None, tipo=TipoMovimiento.OTRO):
    return MovimientoComercial(
        orden=1, tipo=tipo, descripcion_literal=vd(texto), sentido=sentido,
        base=vd(Decimal("10.00")), importe=vd(Decimal("12.10")),
    )


@pytest.mark.parametrize("sentido", [Sentido.CARGO, Sentido.ABONO])
def test_cargo_y_abono_documentados_se_conservan(sentido):
    salida = aplicar_reglas_pequenas(factura([movimiento("SERVICIO BASICO", sentido=sentido)]))
    assert salida.movimientos_comerciales[0].sentido == sentido
    assert not any(i.codigo == "SENTIDO_NO_DOCUMENTADO" for i in salida.incidencias)


@pytest.mark.parametrize("texto,tipo", [
    ("SERVICIO BASICO", TipoMovimiento.SERVICIO),
    ("RAPPEL GenerAH", TipoMovimiento.RAPPEL),
    ("CONCEPTO NUEVO 2027", TipoMovimiento.OTRO),
])
def test_indeterminado_conserva_literal_categoria_importes_evidencia(texto, tipo):
    salida = aplicar_reglas_pequenas(factura([movimiento(texto)]))
    m = salida.movimientos_comerciales[0]
    assert m.descripcion_literal.valor == texto and m.tipo == tipo and m.sentido is None
    assert m.base.valor == Decimal("10.00") and m.importe.valor == Decimal("12.10")
    assert m.descripcion_literal.evidencia
    assert any(i.codigo == "SENTIDO_NO_DOCUMENTADO" and not i.bloqueante for i in salida.incidencias)
    assert next(v for v in salida.validaciones if v.codigo == "MOVIMIENTOS_SENTIDO").resultado == ResultadoControl.NO_EVALUABLE


def test_roundtrip_y_particion_futura_no_mezclan_indeterminados():
    original = factura([
        movimiento("A", sentido=Sentido.CARGO), movimiento("B", sentido=Sentido.ABONO),
        movimiento("SERVICIO BASICO"),
    ])
    roundtrip = FacturaNormalizada.model_validate_json(original.json_estable())
    grupos = {
        "CARGOS_CONFIRMADOS": [m for m in roundtrip.movimientos_comerciales if m.sentido == Sentido.CARGO],
        "ABONOS_CONFIRMADOS": [m for m in roundtrip.movimientos_comerciales if m.sentido == Sentido.ABONO],
        "SENTIDO_INDETERMINADO": [m for m in roundtrip.movimientos_comerciales if m.sentido is None],
    }
    assert {k: len(v) for k, v in grupos.items()} == {
        "CARGOS_CONFIRMADOS": 1, "ABONOS_CONFIRMADOS": 1, "SENTIDO_INDETERMINADO": 1,
    }
    assert roundtrip.json_estable() == original.json_estable()


def test_contrato_v24_admite_sentido_null_sin_alterar_v23_congelado():
    schema = schema_luna_v24()
    factura_schema = schema["properties"]["facturas"]["items"]
    for coleccion in ("albaranes", "movimientos_comerciales"):
        sentido = factura_schema["properties"][coleccion]["items"]["properties"]["sentido"]
        assert {opcion.get("type") for opcion in sentido["anyOf"]} >= {"object", "null"}
    assert CONTRATO_VERSION_V24 == "normalizador-v2.4-luna-1"
    assert "conserva la fila" in PROMPT_LUNA_V24 and "descripcion" in PROMPT_LUNA_V24
