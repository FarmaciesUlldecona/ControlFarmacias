from __future__ import annotations

from decimal import Decimal

import pytest

from src.facturas.normalizador_v2.modelos import (
    AlbaranDocumental, EstadoValidacion, Evidencia, FacturaNormalizada,
    MovimientoComercial, NaturalezaPrincipal, ResultadoControl, ResultadoValidacion,
    Sentido, Tercero, TipoMovimiento, Totales, ValorDocumentado,
)
from src.facturas.normalizador_v2.reglas import aplicar_reglas_pequenas


def vd(valor):
    return ValorDocumentado(valor=valor, literal=str(valor), evidencia=[Evidencia(pagina=1, literal=str(valor))])


def factura(*, movimientos=(), albaranes=()):
    return FacturaNormalizada(
        factura_id="f", naturaleza_principal=NaturalezaPrincipal.MERCANCIA,
        estado_validacion=EstadoValidacion.VALIDADA, requiere_conciliacion_albaranes=True,
        pagina_inicio=1, pagina_fin=1, proveedor=Tercero(nombre=vd("Proveedor")), numero_factura=vd("F1"),
        totales=Totales(total=vd(Decimal("1"))), movimientos_comerciales=list(movimientos), albaranes=list(albaranes),
        validaciones=[ResultadoValidacion(codigo="X", resultado=ResultadoControl.OK, descripcion="x", regla_version="v2")],
    )


def mov(texto, sentido=None, tipo=TipoMovimiento.OTRO, base=None, importe=None):
    return MovimientoComercial(orden=1, tipo=tipo, descripcion_literal=vd(texto), sentido=sentido, base=vd(base) if base is not None else None, importe=vd(importe) if importe is not None else None)


@pytest.mark.parametrize("texto,tipo", [
    ("RAPPEL GenerAH", TipoMovimiento.RAPPEL),
    ("ABONOS CLUBS", TipoMovimiento.ABONO_COMERCIAL),
    ("SERVICIO BASICO", TipoMovimiento.SERVICIO),
    ("SERV.PLATAF.360", TipoMovimiento.SERVICIO),
    ("abonaments", TipoMovimiento.ABONO_COMERCIAL),
    ("Bonificacio pagament inmediat", TipoMovimiento.BONIFICACION),
    ("Condicio Operativa", TipoMovimiento.CONDICION_COMERCIAL),
    ("ABO/DEVO", TipoMovimiento.OTRO),
    ("APROAFA", TipoMovimiento.CONDICION_COMERCIAL),
    ("Servicios Operativos", TipoMovimiento.SERVICIO),
    ("Devoluciones", TipoMovimiento.DEVOLUCION_MERCANCIA),
    ("Serv Integral Distribucion", TipoMovimiento.SERVICIO),
    ("Domiciliacion bancaria", TipoMovimiento.CONDICION_COMERCIAL),
    ("Servicio Logistico", TipoMovimiento.SERVICIO),
    ("Cargo Parafarmacia", TipoMovimiento.CONDICION_COMERCIAL),
])
def test_concepto_se_clasifica_sin_inventar_sentido(texto, tipo):
    actual = aplicar_reglas_pequenas(factura(movimientos=[mov(texto)]))
    assert actual.movimientos_comerciales[0].tipo == tipo
    assert actual.movimientos_comerciales[0].sentido is None
    assert any(i.codigo == "SENTIDO_NO_DOCUMENTADO" and not i.bloqueante for i in actual.incidencias)


@pytest.mark.parametrize("sentido", [Sentido.CARGO, Sentido.ABONO])
def test_sentido_documentado_no_se_modifica_por_descripcion(sentido):
    actual = aplicar_reglas_pequenas(factura(movimientos=[mov("SERVICIO BASICO", sentido=sentido)]))
    assert actual.movimientos_comerciales[0].sentido == sentido


@pytest.mark.parametrize("numero", ["08P10588", "08P10623", "08Z34777"])
def test_ids_historicos_alliance_no_deciden_el_rol(numero):
    albaran = AlbaranDocumental(orden=1, numero=vd(numero), sentido=None, importe_total=vd(Decimal("2")))
    actual = aplicar_reglas_pequenas(factura(albaranes=[albaran]))
    assert [item.numero.valor for item in actual.albaranes] == [numero]
    assert actual.albaranes[0].sentido is None
    assert actual.movimientos_comerciales == []


def test_delivery_nunca_albaran_sin_literal_explicito():
    albaran = AlbaranDocumental(orden=1, numero=vd("504918055"), tipo_movimiento=Sentido.CARGO, tipo_pedido=vd("Delivery"))
    actual = aplicar_reglas_pequenas(factura(albaranes=[albaran]))
    assert actual.albaranes == []
    assert actual.referencias_documentales[0].tipo == "DELIVERY"


def test_cofares_directo_no_confunde_base_y_coste():
    actual = aplicar_reglas_pequenas(factura(movimientos=[mov("Cofares Directo", base=Decimal("409.11"), importe=Decimal("6.95"))]))
    movimiento = actual.movimientos_comerciales[0]
    assert movimiento.base.valor == Decimal("409.11")
    assert movimiento.importe.valor == Decimal("6.95")
