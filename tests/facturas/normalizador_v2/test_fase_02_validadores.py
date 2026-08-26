from __future__ import annotations

from decimal import Decimal

from src.facturas.normalizador_v2.modelos import (
    AlbaranDocumental, EstadoValidacion, Evidencia, FacturaNormalizada, NaturalezaPrincipal,
    ReferenciaDocumental, ResultadoControl, ResultadoValidacion, Sentido, Tercero,
    TipoReferencia, Totales, TramoImpuesto, ValorDocumentado,
)
from src.facturas.normalizador_v2.validadores import ContextoValidacion, detectar_duplicados, validar_factura


def vd(valor, literal=None):
    literal = str(valor) if literal is None else literal
    return ValorDocumentado(valor=valor, literal=literal, evidencia=[Evidencia(pagina=1, literal=literal)])


def fac(**cambios):
    datos = dict(
        factura_id="f1", naturaleza_principal=NaturalezaPrincipal.MERCANCIA,
        estado_validacion=EstadoValidacion.VALIDADA, requiere_conciliacion_albaranes=True,
        pagina_inicio=1, pagina_fin=1,
        proveedor=Tercero(nombre=vd("Proveedor")), numero_factura=vd("F-1"),
        totales=Totales(base_imponible=vd(Decimal("100")), iva=vd(Decimal("21")), recargo_equivalencia=vd(Decimal("0")), total=vd(Decimal("121"))),
        validaciones=[ResultadoValidacion(codigo="PRE", resultado=ResultadoControl.OK, descripcion="pre", regla_version="v2")],
    )
    datos.update(cambios)
    return FacturaNormalizada(**datos)


def test_factura_correcta_validada():
    evaluacion = validar_factura(fac(), ContextoValidacion(numero_paginas=1))
    assert evaluacion.estado == EstadoValidacion.VALIDADA
    assert all(v.resultado != ResultadoControl.FALLO for v in evaluacion.validaciones)


def test_diferencia_002_se_conserva_sin_corregir():
    original = fac(totales=Totales(base_imponible=vd(Decimal("100")), iva=vd(Decimal("21.02")), total=vd(Decimal("121"))))
    evaluacion = validar_factura(original)
    assert evaluacion.estado == EstadoValidacion.VALIDADA_CON_INCIDENCIAS
    assert evaluacion.discrepancias[0].importe_diferencia == Decimal("0.02")
    assert original.totales.iva.valor == Decimal("21.02")


def test_subtotal_no_explicado_por_albaranes():
    albaran = AlbaranDocumental(orden=1, numero=vd("A-1"), tipo_movimiento=Sentido.CARGO, importe_total=vd(Decimal("90")))
    evaluacion = validar_factura(fac(albaranes=[albaran]), ContextoValidacion(subtotal_albaranes_documental=vd(Decimal("100"))))
    assert any(d.tipo == "CUADRE_ALBARANES" and d.importe_diferencia == Decimal("10") for d in evaluacion.discrepancias)


def test_sin_vencimiento_documental_no_inventa():
    evaluacion = validar_factura(fac(vencimientos=[]))
    control = next(v for v in evaluacion.validaciones if v.codigo == "VENCIMIENTOS")
    assert control.resultado == ResultadoControl.NO_APLICA


def test_servicios_sin_albaranes_es_correcto():
    factura = fac(naturaleza_principal=NaturalezaPrincipal.SERVICIOS, requiere_conciliacion_albaranes=False, albaranes=[])
    assert validar_factura(factura).estado == EstadoValidacion.VALIDADA


def test_mercancia_incompleta_requiere_segunda_lectura():
    contexto = ContextoValidacion(senal_estructural_incompleta=True, identificadores_albaran_visibles=20)
    assert validar_factura(fac(albaranes=[]), contexto).estado == EstadoValidacion.REQUIERE_SEGUNDA_LECTURA


def test_delivery_es_referencia_no_albaran():
    ref = ReferenciaDocumental(orden=1, tipo=TipoReferencia.DELIVERY, identificador=vd("504918055"))
    factura = fac(referencias_documentales=[ref], albaranes=[])
    assert validar_factura(factura).estado == EstadoValidacion.VALIDADA
    assert factura.albaranes == [] and factura.referencias_documentales[0].tipo == TipoReferencia.DELIVERY


def test_tramo_fiscal_incorrecto_genera_incidencia_sin_reconstruir():
    tramo = TramoImpuesto(orden=1, base=vd(Decimal("100")), tipo_iva=vd(Decimal("21")), cuota_iva=vd(Decimal("20")))
    evaluacion = validar_factura(fac(impuestos=[tramo]))
    assert evaluacion.estado == EstadoValidacion.VALIDADA_CON_INCIDENCIAS
    assert any(v.codigo == "TRAMO_1_IVA" and v.resultado == ResultadoControl.FALLO for v in evaluacion.validaciones)


def test_duplicado_por_proveedor_numero_y_precedencia():
    facturas = [fac(), fac(factura_id="f2")]
    assert detectar_duplicados(facturas) == {1: 0}
    assert validar_factura(facturas[1], duplicada=True).estado == EstadoValidacion.REQUIERE_REVISION
    assert validar_factura(fac(), ContextoValidacion(fallo_tecnico_global=True, senal_estructural_incompleta=True, identificadores_albaran_visibles=2)).estado == EstadoValidacion.ERROR_TECNICO
