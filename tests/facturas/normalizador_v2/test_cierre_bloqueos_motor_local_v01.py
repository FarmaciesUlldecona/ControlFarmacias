from __future__ import annotations

from decimal import Decimal

from src.facturas.normalizador_v2.modelos import (
    AlbaranDocumental, EstadoValidacion, Evidencia, FacturaNormalizada,
    NaturalezaPrincipal, ResultadoControl, ResultadoValidacion, Sentido,
    Tercero, Totales, ValorDocumentado,
)
from src.facturas.normalizador_v2.normalizador_general import normalizar_candidato
from src.facturas.normalizador_v2.validadores import ContextoValidacion, validar_factura


def _vd(valor):
    return ValorDocumentado(valor=valor, literal=str(valor), evidencia=[Evidencia(pagina=1, literal=str(valor))])


def _candidato_sin_sentido():
    valores = {"tipo_documento": "Factura", "numero_factura": "F1", "importe_total": "10,00"}
    return {
        **valores, "naturaleza_principal": "MERCANCIA", "requiere_conciliacion_albaranes": True,
        "pagina_inicio": 1, "pagina_fin": 1, "proveedor": {"nombre": "COFARES", "nif": None, "direccion": None},
        "destinatario": None, "fecha_factura": None, "base_imponible_total": None, "iva_total": None,
        "recargo_equivalencia_total": None, "otros_total": None, "moneda": None,
        "vencimientos": [], "impuestos": [], "movimientos_comerciales": [], "forma_pago": None,
        "referencias_documentales": [], "discrepancias_documentales": [],
        "albaranes": [{"orden": 1, "numero": "A-1", "fecha": None, "sentido": None, "tipo_pedido": None, "importe_base": None, "importe_total": "10,00"}],
        "evidencias": [
            {"campo": "tipo_documento", "pagina": 1, "literal": "Factura"},
            {"campo": "numero_factura", "pagina": 1, "literal": "F1"},
            {"campo": "importe_total", "pagina": 1, "literal": "10,00"},
            {"campo": "proveedor.nombre", "pagina": 1, "literal": "COFARES"},
            {"campo": "albaranes[0].numero", "pagina": 1, "literal": "A-1"},
            {"campo": "albaranes[0].importe_total", "pagina": 1, "literal": "10,00"},
        ],
    }


def test_albaran_sin_sentido_se_conserva_con_incidencia_no_bloqueante():
    factura = normalizar_candidato(_candidato_sin_sentido())
    assert len(factura.albaranes) == 1
    assert factura.albaranes[0].sentido is None
    incidencia = next(i for i in factura.incidencias if i.codigo == "SENTIDO_NO_DOCUMENTADO")
    assert incidencia.bloqueante is False


def test_cuadre_dependiente_de_sentido_es_no_evaluable():
    albaran = AlbaranDocumental(orden=1, numero=_vd("A-1"), sentido=None, importe_total=_vd(Decimal("10")))
    factura = FacturaNormalizada(
        factura_id="f", naturaleza_principal=NaturalezaPrincipal.MERCANCIA,
        estado_validacion=EstadoValidacion.VALIDADA, requiere_conciliacion_albaranes=True,
        pagina_inicio=1, pagina_fin=1, proveedor=Tercero(nombre=_vd("COFARES")), numero_factura=_vd("F1"),
        totales=Totales(total=_vd(Decimal("10"))), albaranes=[albaran],
        validaciones=[ResultadoValidacion(codigo="X", resultado=ResultadoControl.OK, descripcion="x", regla_version="v")],
    )
    resultado = validar_factura(factura, ContextoValidacion(subtotal_albaranes_documental=_vd(Decimal("10"))))
    control = next(c for c in resultado.validaciones if c.codigo == "CUADRE_ALBARANES")
    assert control.resultado == ResultadoControl.NO_EVALUABLE
    assert resultado.discrepancias == ()


def test_compatibilidad_entrada_tipo_movimiento_y_salida_sentido():
    albaran = AlbaranDocumental(orden=1, numero=_vd("A-1"), tipo_movimiento=Sentido.CARGO)
    assert albaran.sentido == Sentido.CARGO
    assert albaran.tipo_movimiento == Sentido.CARGO
    assert "sentido" in albaran.model_dump(mode="json")
    assert "tipo_movimiento" not in albaran.model_dump(mode="json")
