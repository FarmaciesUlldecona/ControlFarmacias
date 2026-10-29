"""Hito 2BE: R17 (linea PDF = albaran de su numero + 1 interno de la misma recepcion), sin base de datos.

Caso real: 08007969 / 08C20268 = 280005 (500,86) + Q039921/2026 (280004, 3,16), recepcion 50898
(medicion READ_ONLY del 2026-10-29). El resto, variantes que deben fallar cerrado.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    ReglaTolerancia,
    buscar_albaranes_factura,
    conciliar_importes,
    detalle_desde_busqueda,
    detalles_desde_busqueda,
)
from src.facturas.runtime_supabase.modelos import TipoRelacionConciliacion

ALLIANCE = "ALLIANCE HEALTHCARE ESPAÑA, S.A."
DIA = date(2026, 6, 25)


def cand(contador, numero, puc, recepcion, *, dias=0, id_proveedor="2", proveedor="1.- SAFA"):
    return CandidatoAlbaranSupabase(contador, "PIO", id_proveedor, proveedor, numero, DIA + timedelta(days=dias),
                                    Decimal(puc), Decimal("9999.99"), "PENDIENTE", id_recepcion=recepcion)


def doc(numero, importe, *, ident="l1", sentido="CARGO"):
    return AlbaranDocumentalTrabajo(ident, numero, DIA, Decimal(importe), sentido)


A = cand(280005, "08C20268", "500.86", 50898)
B = cand(280004, "Q039921/2026", "3.16", 50898)
LINEA = doc("08C20268", "504.02")


def buscar(docs, candidatos, **kwargs):
    return buscar_albaranes_factura(docs, candidatos, proveedor_literal=kwargs.pop("proveedor", ALLIANCE), **kwargs)


def test_caso_real_08c20268_casa_con_su_numero_y_el_interno_de_la_recepcion():
    [r] = buscar([LINEA], [A, B])
    assert (r.estado, r.candidato, r.complementario) == ("MATCH_R17", A, B)
    assert (r.importe_compatible, r.importe_complementario, r.clase_numero) == (Decimal("500.8600"),
                                                                                 Decimal("3.1600"), "EXACTA")
    detalles = detalles_desde_busqueda(LINEA, r)
    assert [(d.tipo_relacion, d.albaran_id_contador, d.importe_aplicado, d.factura_albaran_extraido_id)
            for d in detalles] == [(TipoRelacionConciliacion.UNO_A_VARIOS, 280005, Decimal("500.8600"), "l1"),
                                   (TipoRelacionConciliacion.UNO_A_VARIOS, 280004, Decimal("3.1600"), "l1")]
    assert [d.provenance["papel_r17"] for d in detalles] == ["NUMERO", "INTERNO"]
    assert {d.provenance["id_recepcion"] for d in detalles} == {50898}
    assert detalles[0].coincidencia_numero_literal and not detalles[1].coincidencia_numero_literal
    # R11: la linea R17 cuenta como un albaran casado.
    resultado = conciliar_importes("504.03", detalles, regla=ReglaTolerancia())
    assert (resultado.resultado, resultado.diferencia, resultado.albaranes_casados) == (
        "CONCILIADA", Decimal("0.0100"), 1)


def test_el_detalle_unico_falla_cerrado_ante_un_resultado_r17():
    [r] = buscar([LINEA], [A, B])
    with pytest.raises(ValueError, match="RESULTADO_R17_REQUIERE_DOS_DETALLES"):
        detalle_desde_busqueda(LINEA, r)


def test_letra_final_y_el_exacto_se_impone():
    letra = cand(280005, "08C20268A", "500.86", 50898)
    [r] = buscar([LINEA], [letra, B])
    assert (r.estado, r.clase_numero) == ("MATCH_R17", "LETRA_FINAL")
    # Con exacto y letra final en la ventana, solo cuenta el exacto (decision de Pio, 2BA).
    exacto_otra_recepcion = cand(280099, "08C20268", "500.86", 77777)
    [r] = buscar([LINEA], [letra, B, exacto_otra_recepcion])
    assert r.estado == "SIN_COINCIDENCIA"


def test_el_casado_1a1_tiene_prioridad():
    exacto = cand(280005, "08C20268", "504.01", 50898)
    [r] = buscar([LINEA], [exacto, B])
    assert (r.estado, r.candidato, r.complementario) == ("MATCH_UNICO", exacto, None)


@pytest.mark.parametrize("candidatos,kwargs", [
    ([A, cand(280004, "Q039921/2026", "3.16", 50899)], {}),                          # otra recepcion
    ([cand(280005, "08C20268", "500.86", None), cand(280004, "Q039921/2026", "3.16", None)], {}),  # sin recepcion
    ([A, cand(280004, "08M99999", "3.16", 50898)], {}),                              # B sin numeracion interna
    ([cand(280005, "08C20269", "500.86", 50898), B], {}),                            # A no es el de su numero
    ([A, cand(280004, "Q039921/2026", "3.22", 50898)], {}),                          # suma fuera de 0,05
    ([A, cand(280004, "Q039921/2026", "3.16", 50898, id_proveedor="52")], {}),       # otro proveedor (R9)
    ([A, B], {"ocupados": [("PIO", 280004)]}),                                       # B reservado
    ([A, B], {"ocupados": [("PIO", 280005)]}),                                       # A reservado
    ([A, B], {"numeros_otras_facturas": ["Q039921/2026"]}),                          # numero de otra factura
    ([cand(280005, "08C20268", "500.86", 50898, dias=16), B], {}),                   # A fuera de la ventana
])
def test_variantes_que_no_casan(candidatos, kwargs):
    [r] = buscar([LINEA], candidatos, **kwargs)
    assert r.estado == "SIN_COINCIDENCIA" and r.complementario is None


def test_abono_y_hefame_no_usan_r17():
    [r] = buscar([doc("08C20268", "504.02", sentido="ABONO")], [A, B])
    assert r.complementario is None
    [r] = buscar([LINEA], [cand(280005, "08C20268", "500.86", 50898, proveedor="HEFAME"),
                           cand(280004, "Q039921/2026", "3.16", 50898, proveedor="HEFAME")], proveedor="HEFAME")
    assert r.complementario is None


def test_el_interno_que_casa_1a1_con_otra_linea_no_se_reutiliza():
    otra = doc("08M11111", "3.16", ident="l2")
    r1, r2 = buscar([LINEA, otra], [A, B])
    assert (r2.estado, r2.candidato) == ("MATCH_UNICO", B)
    assert r1.estado == "SIN_COINCIDENCIA"


def test_dos_internos_posibles_es_ambiguo():
    otro = cand(280003, "Q039920/2026", "3.17", 50898)
    [r] = buscar([LINEA], [A, B, otro])
    assert (r.estado, r.candidato, r.candidatos_finales) == ("AMBIGUO_R17", None, 2)


def test_dos_lineas_con_la_misma_pareja_no_casan_ninguna():
    r1, r2 = buscar([LINEA, doc("08C20268", "504.03", ident="l2")], [A, B])
    assert (r1.estado, r2.estado) == ("CONFLICTO_R17", "CONFLICTO_R17")
    assert r1.candidato is None and r2.candidato is None


def test_varias_lineas_r17_en_una_factura():
    lineas = [LINEA, doc("08C16042", "314.70", ident="l2")]
    otros = [cand(279349, "08C16042", "310.27", 50779), cand(279348, "Q039882/2026", "4.42", 50779, dias=2)]
    resultados = buscar(lineas, [A, B, *otros])
    assert [r.estado for r in resultados] == ["MATCH_R17", "MATCH_R17"]
    detalles = [d for x, r in zip(lineas, resultados) for d in detalles_desde_busqueda(x, r)]
    assert conciliar_importes("818.72", detalles, regla=ReglaTolerancia()).albaranes_casados == 2
