"""Hito 2BG: R19 (ECO360 de Farmatic = grupo Alliance/SAFA en conciliacion), sin base de datos.

Caso real: 08007970 / 08M26912 (39,05) = 280247, proveedor 154 «6- PLATAF. ECO360 AH» (diagnostico READ_ONLY
del 2026-10-30). R19 solo cambia la eleccion de candidatos por proveedor: numeracion, ventanas, R15b y R17
(mismo id con R9) no cambian.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.facturas.runtime_supabase.conciliacion import (
    PROVEEDOR_CANONICO_ALLIANCE,
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    _id_proveedor_comparable,
    buscar_albaranes_factura,
    canonicalizar_proveedor,
)

ALLIANCE = "ALLIANCE HEALTHCARE ESPAÑA, S.A."
ECO360 = "6- PLATAF. ECO360 AH"
DIA = date(2026, 6, 26)


def cand(contador, numero, puc, *, id_proveedor="154", proveedor=ECO360, recepcion=None, dias=0):
    return CandidatoAlbaranSupabase(contador, "PIO", id_proveedor, proveedor, numero, DIA + timedelta(days=dias),
                                    Decimal(puc), Decimal("121.23"), "PENDIENTE", id_recepcion=recepcion)


def doc(numero, importe):
    return AlbaranDocumentalTrabajo("l1", numero, DIA, Decimal(importe), "CARGO")


def buscar(docs, candidatos, **kwargs):
    return buscar_albaranes_factura(docs, candidatos, proveedor_literal=kwargs.pop("proveedor", ALLIANCE), **kwargs)


@pytest.mark.parametrize("literal", [ECO360, "6- PLATAF. ECO360 AH ", "6-PLATAF.ECO360 AH"])
def test_eco360_canonicaliza_al_grupo_alliance(literal):
    assert canonicalizar_proveedor(literal) == PROVEEDOR_CANONICO_ALLIANCE


@pytest.mark.parametrize("literal", ["ECOCEUTICS", "9028_ECO_REIG JOFRE", "PLATAFORMA ECO360"])
def test_otros_proveedores_no_entran_en_el_grupo(literal):
    assert canonicalizar_proveedor(literal) != PROVEEDOR_CANONICO_ALLIANCE


def test_caso_real_08m26912_casa_por_nombre():
    eco = cand(280247, "08M26912", "39.05", id_proveedor="154")
    [r] = buscar([doc("08M26912", "39.05")], [eco])
    assert (r.estado, r.candidato, r.clase_numero, r.importe_compatible) == (
        "MATCH_UNICO", eco, "EXACTA", Decimal("39.0500"))


@pytest.mark.parametrize("id_factura,id_albaran", [("2", "154"), ("0002 ", "0154 "), ("154", "2")])
def test_camino_por_id_154_equivale_a_2_con_r9(id_factura, id_albaran):
    albaran = cand(280247, "08M26912", "39.05", id_proveedor=id_albaran,
                   proveedor=ECO360 if id_albaran.strip().lstrip("0") == "154" else "1.- SAFA")
    [r] = buscar([doc("08M26912", "39.05")], [albaran], farmatic_id_proveedor=id_factura)
    assert (r.estado, r.candidato) == ("MATCH_UNICO", albaran)


def test_camino_por_id_otro_proveedor_no_entra():
    ecoceutics = cand(1, "08M26912", "39.05", id_proveedor="150", proveedor="ECOCEUTICS")
    [r] = buscar([doc("08M26912", "39.05")], [ecoceutics], farmatic_id_proveedor="2")
    assert r.candidato is None


def test_eco360_con_numero_de_proveedor_distinto_no_casa_por_importe():
    """R15b se mantiene: un ECO360 con otro numero Alliance y el mismo importe falla cerrado."""
    [r] = buscar([doc("08M26912", "39.05")], [cand(280999, "08M26913", "39.05")])
    assert (r.estado, r.candidato) == ("NUMERO_PROVEEDOR_DISTINTO", None)


def test_r17_no_mezcla_eco360_y_safa():
    """R17 sigue exigiendo el mismo id con R9 (la BD lo revalida): ECO360 + interno SAFA no es pareja."""
    a = cand(280247, "08M26912", "36.00", id_proveedor="154", recepcion=50955)
    b = cand(280248, "Q039999/2026", "3.05", id_proveedor="2", proveedor="1.- SAFA", recepcion=50955)
    [r] = buscar([doc("08M26912", "39.05")], [a, b])
    assert r.estado != "MATCH_R17" and r.complementario is None
    # Control: con el mismo id la misma pareja si es R17 (lo que la impide es solo el id).
    b_mismo_id = cand(280248, "Q039999/2026", "3.05", id_proveedor="0154 ", recepcion=50955)
    [r] = buscar([doc("08M26912", "39.05")], [a, b_mismo_id])
    assert (r.estado, r.complementario) == ("MATCH_R17", b_mismo_id)


def test_r9_sin_r19_fuera_de_la_conciliacion():
    """La comparacion R9 (resincronizacion, R17) no incorpora R19: 154 sigue siendo 154."""
    assert _id_proveedor_comparable("0154 ") == "154"
