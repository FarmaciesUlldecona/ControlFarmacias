from __future__ import annotations

from decimal import Decimal

import pytest

from src.facturas.normalizador_v2.modelos import EstadoValidacion
from src.facturas.normalizador_v2.normalizador_general import normalizar_candidato


def candidato(proveedor="Eports"):
    valores = {
        "tipo_documento": "Factura", "numero_factura": "F-2026", "fecha_factura": "14/08/2026",
        "base_imponible_total": "100,00", "iva_total": "21,00", "recargo_equivalencia_total": "0,00", "importe_total": "121,00", "moneda": "EUR",
    }
    evidencias = [{"campo": campo, "pagina": 1, "literal": str(valor)} for campo, valor in valores.items()]
    evidencias.append({"campo": "proveedor.nombre", "pagina": 1, "literal": proveedor})
    return {
        **valores, "naturaleza_principal": "MERCANCIA", "requiere_conciliacion_albaranes": True,
        "pagina_inicio": 1, "pagina_fin": 1, "proveedor": {"nombre": proveedor, "nif": None, "direccion": None},
        "vencimientos": [], "impuestos": [], "albaranes": [], "movimientos_comerciales": [], "destinatario": None,
        "otros_total": None, "forma_pago": None, "referencias_documentales": [], "discrepancias_documentales": [], "evidencias": evidencias,
    }


@pytest.mark.parametrize("proveedor", ["Eports", "Logista", "L'Oreal", "Moretti", "Totalcare", "Ecoceutics", "Hygie31"])
def test_normalizador_general_cubre_proveedores_sin_modulo(proveedor):
    factura = normalizar_candidato(candidato(proveedor))
    assert factura.proveedor.nombre.valor == proveedor
    assert factura.estado_validacion == EstadoValidacion.VALIDADA


def test_alias_funcional_no_reemplaza_literal():
    factura = normalizar_candidato(candidato("CENCORA"))
    assert factura.proveedor.nombre.valor == "CENCORA"
    assert factura.proveedor.alias_funcional == "ALLIANCE HEALTHCARE"


def test_decimal_fecha_y_roundtrip():
    factura = normalizar_candidato(candidato())
    assert factura.totales.total.valor == Decimal("121.00")
    assert factura.fecha_factura.valor.iso.isoformat() == "2026-08-14"
    assert type(factura).model_validate_json(factura.json_estable()) == factura


def test_valor_sin_evidencia_se_convierte_en_null_e_incidencia():
    entrada = candidato()
    entrada["evidencias"] = [e for e in entrada["evidencias"] if e["campo"] != "numero_factura"]
    factura = normalizar_candidato(entrada)
    assert factura.numero_factura is None
    assert factura.estado_validacion == EstadoValidacion.REQUIERE_REVISION
    assert any(i.codigo == "VALOR_SIN_EVIDENCIA" for i in factura.incidencias)
