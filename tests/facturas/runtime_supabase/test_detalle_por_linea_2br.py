"""Hito 2BR: detalle por linea en la conciliacion (Python, sin BD).

Cada detalle lleva el importe del PDF, el de Farmatic, la diferencia y el estado de SU linea; el resultado de la
factura no cambia. La equivalencia con la BD (``cf_detalles_por_linea``, migracion 30) esta en
``test_integracion_pg17_2br.py``.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    ResultadoBusquedaAlbaran,
    ValoresLinea,
    conciliar_importes,
    detalles_desde_busqueda,
    importe_documental_con_signo,
    valores_por_linea,
)
from src.facturas.runtime_supabase.modelos import DetalleConciliacion, TipoRelacionConciliacion as T
from src.facturas.runtime_supabase.repositorios import clave_idempotente_conciliacion, payload_conciliacion

D = Decimal


def _doc(id_, importe, sentido="CARGO", numero="08C00001"):
    return AlbaranDocumentalTrabajo(id=id_, numero=numero, fecha=date(2026, 6, 20),
                                    importe=None if importe is None else D(importe), sentido=sentido)


def _alb(contador, numero, puc, recepcion=1):
    return CandidatoAlbaranSupabase(id_contador=contador, farmacia="PIO", id_proveedor="2", proveedor="1.- SAFA",
                                    numero_albaran=numero, fecha=date(2026, 6, 20), importe_puc=D(puc),
                                    importe_pvp=None, id_recepcion=recepcion)


def _match(candidato, importe, **kw):
    return ResultadoBusquedaAlbaran("MATCH_UNICO", candidato, D(importe), "EXACTA", 1, 1, 1, 1, "EXACTA", **kw)


def _sin(estado="SIN_COINCIDENCIA"):
    return ResultadoBusquedaAlbaran(estado, None, None, "NO_EVALUADO", 0, 0, 0, 0)


def test_importe_documental_con_signo():
    assert importe_documental_con_signo(_doc("a", "12.5")) == D("12.5000")
    assert importe_documental_con_signo(_doc("a", "12.5", "ABONO")) == D("-12.5000")
    assert importe_documental_con_signo(_doc("a", "-12.5", "ABONO")) == D("-12.5000")
    assert importe_documental_con_signo(_doc("a", None)) is None


def test_linea_casada_1a1_dentro_y_fuera_de_la_tolerancia_por_linea():
    [d1] = detalles_desde_busqueda(_doc("l1", "12.45"), _match(_alb(1, "08C00001", "12.44"), "12.44"))
    [d2] = detalles_desde_busqueda(_doc("l2", "10.00"), _match(_alb(2, "08C00002", "9.90"), "9.90"))
    assert valores_por_linea([d1, d2]) == (
        ValoresLinea(D("12.4500"), D("12.4400"), D("0.0100"), "COINCIDE"),
        ValoresLinea(D("10.0000"), D("9.9000"), D("0.1000"), "DIFERENCIA"),
    )


def test_abono_1a1_con_signo_negativo():
    [d] = detalles_desde_busqueda(_doc("l1", "20.00", "ABONO"), _match(_alb(1, "08C00001", "-20.02"), "20.02"))
    assert d.importe_aplicado == D("-20.02")
    assert valores_por_linea([d]) == (ValoresLinea(D("-20.0000"), D("-20.0200"), D("0.0200"), "COINCIDE"),)


def test_linea_sin_coincidencia_y_linea_sin_importe():
    [d1] = detalles_desde_busqueda(_doc("l1", "504.02"), _sin())
    [d2] = detalles_desde_busqueda(_doc("l2", None), _sin("NO_EVALUADO"))
    assert valores_por_linea([d1, d2]) == (
        ValoresLinea(D("504.0200"), None, D("504.0200"), "DIFERENCIA"),
        ValoresLinea(None, None, None, "NO_EVALUABLE"),
    )


def test_linea_r17_misma_diferencia_y_estado_en_los_dos_detalles():
    a, b = _alb(280005, "08C20268", "500.86", 50898), _alb(280004, "Q039921/2026", "3.16", 50898)
    r = ResultadoBusquedaAlbaran("MATCH_R17", a, D("500.86"), "EXACTA", 1, 1, 1, 1, "EXACTA",
                                 complementario=b, importe_complementario=D("3.16"))
    detalles = detalles_desde_busqueda(_doc("l1", "504.02", numero="08C20268"), r)
    assert [d.tipo_relacion for d in detalles] == [T.UNO_A_VARIOS, T.UNO_A_VARIOS]
    assert valores_por_linea(detalles) == (
        ValoresLinea(D("504.0200"), D("500.8600"), D("0.0000"), "COINCIDE"),
        ValoresLinea(D("504.0200"), D("3.1600"), D("0.0000"), "COINCIDE"),
    )


def test_movimientos_y_ajustes_sin_contraparte_en_farmatic():
    mov = DetalleConciliacion(tipo_relacion=T.MOVIMIENTO_NO_FARMATIC, importe_aplicado=D("31.46"),
                              factura_movimiento_id="m1", provenance={"fuente": "MOVIMIENTO_DOCUMENTAL"})
    abono = DetalleConciliacion(tipo_relacion=T.MOVIMIENTO_NO_FARMATIC, importe_aplicado=D("-5"),
                                factura_movimiento_id="m2", provenance={"fuente": "MOVIMIENTO_DOCUMENTAL"})
    ajuste = DetalleConciliacion(tipo_relacion=T.MOVIMIENTO_NO_FARMATIC, importe_aplicado=D("1.20"),
                                 provenance={"fuente": "FISCALIDAD_AJUSTE_DOCUMENTAL"})
    assert valores_por_linea([mov, abono, ajuste]) == (
        ValoresLinea(D("31.4600"), None, None, "NO_EVALUABLE"),
        ValoresLinea(D("-5.0000"), None, None, "NO_EVALUABLE"),
        ValoresLinea(D("1.2000"), None, None, "NO_EVALUABLE"),
    )


def test_el_resultado_de_la_factura_no_cambia_y_el_payload_lleva_los_valores_por_linea():
    [d1] = detalles_desde_busqueda(_doc("l1", "12.45"), _match(_alb(1, "08C00001", "12.44"), "12.44"))
    [d2] = detalles_desde_busqueda(_doc("l2", "504.02"), _sin())
    mov = DetalleConciliacion(tipo_relacion=T.MOVIMIENTO_NO_FARMATIC, importe_aplicado=D("31.46"),
                              factura_movimiento_id="m1", provenance={"fuente": "MOVIMIENTO_DOCUMENTAL"})
    resultado = conciliar_importes(D("547.93"), [d1, d2, mov])
    # El importe documental no interviene en el resultado de la factura.
    sin_documental = conciliar_importes(D("547.93"), [
        DetalleConciliacion(**{**{s: getattr(d, s) for s in d.__slots__}, "importe_documental": None})
        for d in (d1, d2, mov)])
    assert (resultado.resultado, resultado.importe_explicado, resultado.diferencia, resultado.tolerancia) == \
        (sin_documental.resultado, sin_documental.importe_explicado, sin_documental.diferencia,
         sin_documental.tolerancia) == ("DIFERENCIA", D("43.9000"), D("504.0300"), D("0.0500"))
    payload = payload_conciliacion(resultado)
    assert [(x["estado"], x["importe_documental"], x["importe_farmatic"], x["diferencia"])
            for x in payload["detalles"]] == [
        ("COINCIDE", "12.4500", "12.4400", "0.0100"),
        ("DIFERENCIA", "504.0200", None, "504.0200"),
        ("NO_EVALUABLE", "31.4600", None, None),
    ]
    assert {k: payload[k] for k in ("importe_factura", "importe_explicado", "diferencia", "tolerancia",
                                    "resultado")} == {"importe_factura": "547.9300", "importe_explicado": "43.9000",
                                                      "diferencia": "504.0300", "tolerancia": "0.0500",
                                                      "resultado": "DIFERENCIA"}
    # Misma evidencia -> misma clave (replay).
    assert clave_idempotente_conciliacion("f", "MANUAL_ONE_SHOT", payload) == \
        clave_idempotente_conciliacion("f", "MANUAL_ONE_SHOT", payload_conciliacion(resultado))


def test_conciliada_puede_tener_lineas_en_diferencia():
    """Antes el estado de cada linea era el de la factura; ahora una factura CONCILIADA por tolerancia R11 puede
    tener una linea fuera de la tolerancia por linea."""
    [d1] = detalles_desde_busqueda(_doc("l1", "10.00"), _match(_alb(1, "08C00001", "9.94"), "9.94"))
    [d2] = detalles_desde_busqueda(_doc("l2", "10.00"), _match(_alb(2, "08C00002", "10.00"), "10.00"))
    resultado = conciliar_importes(D("20.00"), [d1, d2], tolerancia=D("0.0600"))
    assert resultado.resultado == "CONCILIADA"
    assert [x["estado"] for x in payload_conciliacion(resultado)["detalles"]] == ["DIFERENCIA", "COINCIDE"]


@pytest.mark.parametrize("tipo", [T.UNO_A_UNO, T.UNO_A_VARIOS])
def test_albaran_sin_importe_documental_no_es_evaluable(tipo):
    d = DetalleConciliacion(tipo_relacion=tipo, importe_aplicado=D("3"), albaran_farmacia="PIO",
                            albaran_id_contador=1, factura_albaran_extraido_id="l1")
    assert valores_por_linea([d]) == (ValoresLinea(None, D("3.0000"), None, "NO_EVALUABLE"),)
