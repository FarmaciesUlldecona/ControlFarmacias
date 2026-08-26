from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.facturas.normalizador_v2.modelos import (
    DocumentoNormalizado,
    EstadoValidacion,
    EstrategiaLectura,
    Evidencia,
    FacturaNormalizada,
    FechaDocumental,
    MetadataTecnica,
    NaturalezaPrincipal,
    ResultadoControl,
    ResultadoValidacion,
    TipoContenido,
    Totales,
    ValorDocumentado,
)


def vd(valor, literal=None):
    texto = str(valor) if literal is None else literal
    return ValorDocumentado(valor=valor, literal=texto, evidencia=[Evidencia(pagina=1, literal=texto)])


def factura(**cambios):
    datos = {
        "factura_id": "fac-1",
        "naturaleza_principal": NaturalezaPrincipal.MERCANCIA,
        "estado_validacion": EstadoValidacion.VALIDADA,
        "requiere_conciliacion_albaranes": True,
        "pagina_inicio": 1,
        "pagina_fin": 1,
        "totales": Totales(total=vd(Decimal("10.20"), "10,20")),
        "validaciones": [ResultadoValidacion(codigo="IDENTIDAD", resultado=ResultadoControl.OK, descripcion="ok", regla_version="v2.1")],
    }
    datos.update(cambios)
    return FacturaNormalizada(**datos)


def documento(**cambios):
    datos = {
        "documento_id": "doc-hash",
        "archivo_origen": "entrada.pdf",
        "tipo_contenido": TipoContenido.PDF_NATIVO,
        "numero_paginas": 1,
        "estado_documento": EstadoValidacion.VALIDADA,
        "estrategia_lectura": EstrategiaLectura.LUNA_V2,
        "facturas": [factura()],
        "metadata_tecnica": MetadataTecnica(version_normalizador="2.0", version_configuracion="2.0", lector_primario="gpt-5.6-luna", inicio="2026-08-14T00:00:00Z", fin="2026-08-14T00:00:01Z", duracion_ms=1000, correlacion_id="corr-1"),
    }
    datos.update(cambios)
    return DocumentoNormalizado(**datos)


def test_construccion_nulls_y_arrays_independientes():
    primera = factura()
    segunda = factura(factura_id="fac-2")
    assert primera.proveedor is None
    assert primera.vencimientos == primera.albaranes == []
    primera.vencimientos.append(None)  # type: ignore[arg-type]
    assert segunda.vencimientos == []


def test_enums_completos_y_naturaleza_no_admite_cargo_abono():
    assert set(NaturalezaPrincipal) == {"MERCANCIA", "SERVICIOS", "MIXTA", "CONDICIONES_COMERCIALES"}
    assert set(EstadoValidacion) == {"VALIDADA", "VALIDADA_CON_INCIDENCIAS", "REQUIERE_SEGUNDA_LECTURA", "REQUIERE_REVISION", "ERROR_TECNICO"}
    with pytest.raises(ValidationError):
        factura(naturaleza_principal="CARGO")


def test_decimal_seguro_fecha_tipada_json_y_roundtrip():
    fecha = FechaDocumental(literal="14/08/2026", iso=date(2026, 8, 14))
    original = documento(facturas=[factura(fecha_factura=vd(fecha, "14/08/2026"))])
    texto = original.json_estable()
    assert '"10.20"' in texto
    assert '"2026-08-14"' in texto
    reconstruido = DocumentoNormalizado.model_validate_json(texto)
    assert reconstruido == original
    assert reconstruido.facturas[0].totales.total.valor == Decimal("10.20")


def test_json_estable_independiente_del_orden_de_entrada():
    datos = documento().model_dump(mode="json")
    invertido = dict(reversed(list(datos.items())))
    assert DocumentoNormalizado.model_validate(invertido).json_estable() == documento().json_estable()


def test_schema_raiz_y_factura_completos():
    schema = DocumentoNormalizado.model_json_schema()
    assert set(schema["properties"]) == {"documento_id", "archivo_origen", "tipo_contenido", "numero_paginas", "estado_documento", "estrategia_lectura", "facturas", "metadata_tecnica"}
    factura_props = schema["$defs"]["FacturaNormalizada"]["properties"]
    assert set(factura_props) == {"factura_id", "tipo_documento", "naturaleza_principal", "estado_validacion", "requiere_conciliacion_albaranes", "pagina_inicio", "pagina_fin", "proveedor", "numero_factura", "fecha_factura", "destinatario", "totales", "vencimientos", "impuestos", "albaranes", "movimientos_comerciales", "forma_pago", "referencias_documentales", "derivaciones", "discrepancias_documentales", "incidencias", "validaciones"}
    json.dumps(schema)


def test_evidencia_obligatoria_y_paginas_validas():
    with pytest.raises(ValidationError):
        ValorDocumentado(valor="x", literal="x", evidencia=[])
    with pytest.raises(ValidationError):
        documento(facturas=[factura(pagina_fin=2)])
    with pytest.raises(ValidationError):
        factura(pagina_inicio=2, pagina_fin=1)


def test_modelos_rechazan_campos_desconocidos():
    with pytest.raises(ValidationError):
        DocumentoNormalizado(**documento().model_dump(), inventado=True)
