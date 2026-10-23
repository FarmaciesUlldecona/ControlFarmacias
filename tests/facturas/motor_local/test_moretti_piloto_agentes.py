"""Piloto de agentes: adaptador local Moretti contra el PDF real del corpus.

El nombre del archivo solo sirve para localizar la fixture del corpus externo;
el adaptador nunca lo usa para clasificar.

Las comprobaciones son por contenido, no por posición: la factura se localiza por
su número, el tramo fiscal por su tipo de IVA y el vencimiento por su fecha. Ningún
assert depende de índices de lista ni de números de línea del PDF.

Valores esperados leídos a mano de la página 1 del PDF Moretti del corpus
(`pruebas/facturas/documentos/2o_gold_standard`, fuera de Git):
- bajo el título "Factura": "Número 003463FV26 De 31/07/2026";
- recuadro inferior: "Total Neto 118,20", "Total IVA 11,82", "Total Factura 130,02";
- tabla IVA: "RED IVA 10% Reducido 118,20 11,82 0,00 130,02";
- cuerpo: "Vencimientos: € 130,02 el 30/08/2026".
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.gold_pequenos import AdaptadorMoretti
from src.facturas.motor_local.autoridad import autoridad_productiva_habilitada
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.catalogo import ProveedorLocal
from src.facturas.motor_local.segmentacion.segmentador import segmentar
from src.facturas.motor_local.servicio import MotorDocumentoLocal


ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "pruebas/facturas/documentos/2o_gold_standard"

# Página 1: "Número 003463FV26 De 31/07/2026".
NUMERO_ESPERADO = "003463FV26"
FECHA_ESPERADA = "2026-07-31"
# Página 1, recuadro inferior y tabla IVA.
BASE_ESPERADA = Decimal("118.20")
IVA_ESPERADO = Decimal("11.82")
RECARGO_ESPERADO = Decimal("0.00")
TOTAL_ESPERADO = Decimal("130.02")
TIPO_IVA_ESPERADO = Decimal("10")
# Página 1, cuerpo: "Vencimientos: € 130,02 el 30/08/2026".
FECHA_VENCIMIENTO_ESPERADA = "2026-08-30"


def _pdf(prefijo: str) -> Path:
    if not CORPUS.exists():
        pytest.skip("corpus local externo ausente")
    encontrados = [p for p in CORPUS.glob("*.pdf") if p.name.startswith(prefijo)]
    if len(encontrados) != 1:
        pytest.skip(f"corpus local externo sin un único PDF {prefijo}")
    return encontrados[0]


def _documento_y_segmentos(ruta: Path):
    documento = BackendPdfium().cargar_pdf(ruta)
    segmentos, _audit = segmentar(documento)
    return documento, segmentos


def _dec(valor) -> Decimal:
    """Importe a Decimal con 2 decimales; None falla explícitamente."""
    assert valor is not None, "importe ausente"
    return Decimal(str(valor)).quantize(Decimal("0.01"))


def _unico(elementos: list, descripcion: str):
    assert len(elementos) == 1, f"se esperaba exactamente un {descripcion}, hay {len(elementos)}"
    (unico,) = elementos
    return unico


def _assert_evidencia_pagina_1(campo: dict, nombre: str, literal: str | None = None) -> None:
    assert campo["evidencias"], nombre
    assert {e.pagina for e in campo["evidencias"]} == {1}, nombre
    if literal is not None:
        assert campo["literal"] == literal, nombre
        assert any(e.literal == literal for e in campo["evidencias"]), nombre


@pytest.fixture(scope="module")
def factura_moretti():
    documento, segmentos = _documento_y_segmentos(_pdf("MORETTI"))
    adaptador = AdaptadorMoretti()
    assert adaptador.reconocer(documento).estado == "RECONOCIDO"
    facturas = adaptador.extraer_facturas(documento, segmentos)
    # Localiza la factura por su número impreso, no por su posición en la lista.
    candidatas = [f for f in facturas if f["cabecera"]["numero_factura"]["valor"] == NUMERO_ESPERADO]
    factura = _unico(candidatas, f"factura {NUMERO_ESPERADO}")
    # Página 1 contiene una sola factura: no debe haber facturas extra con otro número.
    assert {f["cabecera"]["numero_factura"]["valor"] for f in facturas} == {NUMERO_ESPERADO}
    return factura


def _tramo_por_tipo(factura: dict, tipo: Decimal) -> dict:
    candidatos = [
        t for t in factura["impuestos"]
        if t["tipo_iva"] is not None and Decimal(str(t["tipo_iva"]["valor"])) == tipo
    ]
    return _unico(candidatos, f"tramo IVA {tipo}%")


def _vencimiento_por_fecha(factura: dict, fecha: str) -> dict:
    candidatos = [v for v in factura["vencimientos"] if v["fecha"]["valor"] == fecha]
    return _unico(candidatos, f"vencimiento {fecha}")


def test_adaptador_es_moretti_local_y_layout_certificado(factura_moretti):
    assert AdaptadorMoretti.id == "moretti-local"
    assert factura_moretti["layout"] == "MORETTI_FACTURA_V1"
    assert factura_moretti["provenance"]["adaptador"] == "moretti-local"
    assert factura_moretti["provenance"]["gold_usado_extraccion"] is False


def test_motor_clasifica_el_pdf_moretti_como_moretti_local():
    resultado = MotorDocumentoLocal(BackendPdfium()).extraer(_pdf("MORETTI"))
    assert resultado.documento["layout"] == "moretti-local"


def test_cabecera_coincide_con_valores_leidos_a_mano(factura_moretti):
    cab = factura_moretti["cabecera"]
    # Página 1, bajo el título "Factura": "Número 003463FV26 De 31/07/2026".
    assert cab["numero_factura"]["valor"] == NUMERO_ESPERADO
    _assert_evidencia_pagina_1(cab["numero_factura"], "numero_factura", "003463FV26")
    assert cab["fecha_factura"]["valor"] == FECHA_ESPERADA
    _assert_evidencia_pagina_1(cab["fecha_factura"], "fecha_factura", "31/07/2026")
    # Página 1, recuadro inferior: "Total Neto 118,20", "Total IVA 11,82", "Total Factura 130,02".
    assert _dec(cab["base_imponible_total"]["valor"]) == BASE_ESPERADA
    _assert_evidencia_pagina_1(cab["base_imponible_total"], "base_imponible_total", "118,20")
    assert _dec(cab["iva_total"]["valor"]) == IVA_ESPERADO
    _assert_evidencia_pagina_1(cab["iva_total"], "iva_total", "11,82")
    assert _dec(cab["importe_total"]["valor"]) == TOTAL_ESPERADO
    _assert_evidencia_pagina_1(cab["importe_total"], "importe_total", "130,02")


def test_fiscalidad_tramo_localizado_por_tipo_iva(factura_moretti):
    # Página 1, tabla IVA: "RED IVA 10% Reducido 118,20 11,82 0,00 130,02".
    # Único tipo de IVA impreso en la tabla: 10%.
    tipos = {Decimal(str(t["tipo_iva"]["valor"])) for t in factura_moretti["impuestos"]}
    assert tipos == {TIPO_IVA_ESPERADO}
    tramo = _tramo_por_tipo(factura_moretti, TIPO_IVA_ESPERADO)
    assert _dec(tramo["base"]["valor"]) == BASE_ESPERADA
    _assert_evidencia_pagina_1(tramo["base"], "tramo.base", "118,20")
    assert _dec(tramo["cuota_iva"]["valor"]) == IVA_ESPERADO
    _assert_evidencia_pagina_1(tramo["cuota_iva"], "tramo.cuota_iva", "11,82")
    assert _dec(tramo["cuota_recargo_equivalencia"]["valor"]) == RECARGO_ESPERADO
    _assert_evidencia_pagina_1(tramo["cuota_recargo_equivalencia"], "tramo.cuota_recargo", "0,00")
    _assert_evidencia_pagina_1(tramo["tipo_iva"], "tramo.tipo_iva")
    assert "10%" in tramo["tipo_iva"]["literal"]


def test_aritmetica_base_mas_iva_mas_recargo_igual_total(factura_moretti):
    # Página 1: 118,20 + 11,82 + 0,00 = 130,02 ("Total Factura").
    cab = factura_moretti["cabecera"]
    impuestos = factura_moretti["impuestos"]
    base = sum((_dec(t["base"]["valor"]) for t in impuestos), Decimal("0.00"))
    iva = sum((_dec(t["cuota_iva"]["valor"]) for t in impuestos), Decimal("0.00"))
    recargo = sum(
        (_dec(t["cuota_recargo_equivalencia"]["valor"]) for t in impuestos
         if t["cuota_recargo_equivalencia"] is not None),
        Decimal("0.00"),
    )
    total = _dec(cab["importe_total"]["valor"])
    assert base + iva + recargo == total == TOTAL_ESPERADO
    # Coherencia cabecera-fiscalidad: los totales impresos cuadran con los tramos.
    assert base == _dec(cab["base_imponible_total"]["valor"])
    assert iva == _dec(cab["iva_total"]["valor"])


def test_vencimiento_localizado_por_fecha(factura_moretti):
    # Página 1, cuerpo: "Vencimientos: € 130,02 el 30/08/2026".
    venc = _vencimiento_por_fecha(factura_moretti, FECHA_VENCIMIENTO_ESPERADA)
    assert _dec(venc["importe"]["valor"]) == TOTAL_ESPERADO
    _assert_evidencia_pagina_1(venc["fecha"], "vencimiento.fecha", "30/08/2026")
    _assert_evidencia_pagina_1(venc["importe"], "vencimiento.importe", "130,02")
    # La suma de vencimientos cubre exactamente el total, sea cual sea su orden.
    suma = sum((_dec(v["importe"]["valor"]) for v in factura_moretti["vencimientos"]), Decimal("0.00"))
    assert suma == TOTAL_ESPERADO
    assert {c["estado"] for c in factura_moretti["controles_conciliacion"]} == {"OK"}
    assert factura_moretti["incidencias"] == []


def test_negativo_pdf_de_otro_proveedor_no_es_moretti_local():
    ruta = _pdf("LOGISTA PHARMA")
    documento, segmentos = _documento_y_segmentos(ruta)
    adaptador = AdaptadorMoretti()
    assert adaptador.reconocer(documento).estado != "RECONOCIDO"
    assert adaptador.extraer_facturas(documento, segmentos) == []
    assert adaptador.extraer_cabecera(documento, segmentos) == {}
    resultado = MotorDocumentoLocal(BackendPdfium()).extraer(ruta)
    assert resultado.documento["layout"] != "moretti-local"


def test_negativo_busqueda_por_contenido_falla_explicitamente(factura_moretti):
    # Un tipo de IVA o una fecha de vencimiento que no aparecen en la página 1 no se
    # sustituyen por "el primero": la búsqueda por contenido falla de forma explícita.
    with pytest.raises(AssertionError, match="tramo IVA 21%"):
        _tramo_por_tipo(factura_moretti, Decimal("21"))
    with pytest.raises(AssertionError, match="vencimiento 2026-08-31"):
        _vencimiento_por_fecha(factura_moretti, "2026-08-31")


def test_autoridad_productiva_moretti_sigue_desactivada():
    assert autoridad_productiva_habilitada(ProveedorLocal.MORETTI) is False
    assert AdaptadorMoretti.capacidades["autoridad"] == "SHADOW_SIN_AUTORIDAD_PRODUCTIVA"
