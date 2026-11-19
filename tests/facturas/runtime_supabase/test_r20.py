"""R20 (DECISION DE PIO, 2026-11-19; migracion 36): linea PDF = albaran exacto + su variante con letra final.

Sin base de datos. Caso real 08013495 con las entradas de ``construir_detalles`` leidas en modo READ_ONLY
(``datos_r20_08013495.json``): con R20 CONCILIADA -0,09; sin R20, DIFERENCIA 118,16; el resto de lineas, igual.
Variantes que deben fallar cerrado, deteccion de la 36 (information_schema) y repositorio sin deteccion.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    MovimientoDocumentalTrabajo,
    ReglaTolerancia,
    buscar_albaranes_factura,
    conciliar_importes,
    construir_detalles_movimientos_documentales,
    detalles_desde_busqueda,
)
from src.facturas.runtime_supabase.lectura_readonly import SQL_COLUMNA_R20, SQL_VALOR_R20, r20_habilitada
from src.facturas.runtime_supabase.modelos import TipoRelacionConciliacion
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase

ALLIANCE = "ALLIANCE HEALTHCARE ESPAÑA, S.A."
DIA = date(2026, 11, 9)
DATOS = Path(__file__).with_name("datos_r20_08013495.json")
REGLA = ReglaTolerancia(suelo=Decimal("0.05"), por_albaran=Decimal("0.01"), tope=Decimal("0.50"))


def cand(contador, numero, puc, recepcion, *, dias=0, id_proveedor="0002 ", proveedor="1.- SAFA"):
    return CandidatoAlbaranSupabase(contador, "PIO", id_proveedor, proveedor, numero, DIA + timedelta(days=dias),
                                    Decimal(puc), Decimal("9999.99"), "PENDIENTE", id_recepcion=recepcion)


def doc(numero="08D79747", importe="118.25", *, ident="l1", sentido="CARGO"):
    return AlbaranDocumentalTrabajo(ident, numero, DIA, Decimal(importe), sentido)


A = cand(297826, "08D79747", "77.49", 54736)
B = cand(297825, "08D79747A", "40.76", 54736)


def buscar(docs, candidatos, *, r20=True, **kwargs):
    return buscar_albaranes_factura(docs, candidatos, proveedor_literal=kwargs.pop("proveedor", ALLIANCE),
                                    r20_habilitada=r20, **kwargs)


# --------------------------------------------------------------------------- caso real 08013495

def _caso_real(r20: bool):
    d = json.loads(DATOS.read_text(encoding="utf-8"))
    docs = tuple(AlbaranDocumentalTrabajo(i, n, date.fromisoformat(f), Decimal(imp), t)
                 for i, n, f, imp, t in d["lineas"])
    cands = tuple(CandidatoAlbaranSupabase(c, "PIO", ip, p, n, date.fromisoformat(f),
                                           None if puc is None else Decimal(puc), None if pvp is None else Decimal(pvp),
                                           est, id_recepcion=rec)
                  for c, ip, p, n, f, puc, pvp, est, rec in d["albaranes"])
    movs = tuple(MovimientoDocumentalTrabajo(id=m["id"], concepto_literal=m["descripcion_literal"], tipo=m["categoria"],
                                             sentido=m["sentido"], importe=Decimal(str(m["importe"])),
                                             base=Decimal(str(m["base"])), provenance=m["provenance"])
                 for m in d["movimientos"])
    resultados = buscar_albaranes_factura(
        docs, cands, proveedor_literal=d["factura"]["proveedor_literal"],
        ocupados={tuple(o) for o in d["ocupados"]}, numeros_otras_facturas=d["numeros_otras_facturas"],
        r20_habilitada=r20)
    detalles = list(construir_detalles_movimientos_documentales(movs))
    detalles += [x for doc_, r in zip(docs, resultados) for x in detalles_desde_busqueda(doc_, r)]
    return docs, resultados, conciliar_importes(Decimal(str(d["factura"]["importe_total"])), detalles, regla=REGLA)


def test_caso_real_08013495_sin_r20_sigue_en_diferencia_118_16():
    docs, resultados, c = _caso_real(False)
    assert (c.resultado, c.diferencia) == ("DIFERENCIA", Decimal("118.1600"))
    [sin] = [(d.numero, r.estado) for d, r in zip(docs, resultados) if r.candidato is None]
    assert sin == ("08D79747", "SIN_COINCIDENCIA")


def test_caso_real_08013495_con_r20_concilia_con_menos_0_09_y_no_cambia_nada_mas():
    docs, sin_r20, _ = _caso_real(False)
    _, con_r20, c = _caso_real(True)
    assert (c.resultado, c.diferencia, c.tolerancia) == ("CONCILIADA", Decimal("-0.0900"), Decimal("0.5000"))
    cambios = [(d.numero, a.estado, b.estado) for d, a, b in zip(docs, sin_r20, con_r20) if a != b]
    assert cambios == [("08D79747", "SIN_COINCIDENCIA", "MATCH_R20")]
    [r] = [b for d, b in zip(docs, con_r20) if d.numero == "08D79747"]
    assert (r.candidato.id_contador, r.importe_compatible, r.complementario.id_contador, r.importe_complementario) == (
        297826, Decimal("77.4900"), 297825, Decimal("40.7600"))
    assert c.albaranes_casados == 126  # 125 1:1 + la linea R20 (R11)


# --------------------------------------------------------------------------- regla

def test_pareja_r20_da_dos_detalles_uno_a_varios():
    linea = doc()
    [r] = buscar([linea], [A, B])
    assert (r.estado, r.candidato, r.complementario, r.clase_numero) == ("MATCH_R20", A, B, "EXACTA")
    detalles = detalles_desde_busqueda(linea, r)
    assert [(d.tipo_relacion, d.albaran_id_contador, d.importe_aplicado) for d in detalles] == [
        (TipoRelacionConciliacion.UNO_A_VARIOS, 297826, Decimal("77.4900")),
        (TipoRelacionConciliacion.UNO_A_VARIOS, 297825, Decimal("40.7600"))]
    assert [(d.provenance["regla"], d.provenance["papel_r20"], d.provenance["clase_numero"]) for d in detalles] == [
        ("R20", "NUMERO", "EXACTA"), ("R20", "LETRA_FINAL", "LETRA_FINAL")]
    assert {d.provenance["id_recepcion"] for d in detalles} == {54736}
    assert all("papel_r17" not in d.provenance for d in detalles)
    assert detalles[0].coincidencia_numero_literal and not detalles[1].coincidencia_numero_literal
    resultado = conciliar_importes("118.25", detalles, regla=REGLA)
    assert (resultado.resultado, resultado.diferencia, resultado.albaranes_casados) == (
        "CONCILIADA", Decimal("0.0000"), 1)


def test_sin_r20_habilitada_la_linea_queda_sin_coincidencia():
    [r] = buscar([doc()], [A, B], r20=False)
    assert (r.estado, r.complementario) == ("SIN_COINCIDENCIA", None)
    [r] = buscar_albaranes_factura([doc()], [A, B], proveedor_literal=ALLIANCE)  # por defecto, apagada
    assert r.estado == "SIN_COINCIDENCIA"


def test_el_1a1_tiene_prioridad():
    exacto = cand(1, "08D79747", "118.25", 54736)
    [r] = buscar([doc()], [exacto, B])
    assert (r.candidato, r.complementario, r.importe_compatible) == (exacto, None, Decimal("118.2500"))
    assert not r.estado.endswith("R20")


@pytest.mark.parametrize("caso", ["otra_recepcion", "sin_recepcion", "otro_proveedor", "eco360", "suma_fuera",
                                  "a_fuera_de_ventana", "b_fuera_de_ventana", "a_reservado", "b_reservado",
                                  "b_numero_de_otra_factura", "abono", "hefame", "sin_exacto", "otro_numero"])
def test_variantes_que_no_son_r20(caso):
    linea, a, b, kwargs = doc(), A, B, {}
    if caso == "otra_recepcion":
        b = cand(297825, "08D79747A", "40.76", 54737)
    elif caso == "sin_recepcion":
        a, b = cand(297826, "08D79747", "77.49", None), cand(297825, "08D79747A", "40.76", None)
    elif caso == "otro_proveedor":
        b = cand(297825, "08D79747A", "40.76", 54736, id_proveedor="52")
    elif caso == "eco360":
        b = cand(297825, "08D79747A", "40.76", 54736, id_proveedor="154", proveedor="6- PLATAF. ECO360 AH")
    elif caso == "suma_fuera":
        b = cand(297825, "08D79747A", "40.82", 54736)
    elif caso == "a_fuera_de_ventana":
        a = cand(297826, "08D79747", "77.49", 54736, dias=16)
    elif caso == "b_fuera_de_ventana":
        b = cand(297825, "08D79747A", "40.76", 54736, dias=-16)
    elif caso == "a_reservado":
        kwargs["ocupados"] = {("PIO", 297826)}
    elif caso == "b_reservado":
        kwargs["ocupados"] = {("PIO", 297825)}
    elif caso == "b_numero_de_otra_factura":
        kwargs["numeros_otras_facturas"] = ["08D79747A"]
    elif caso == "abono":
        linea = doc(sentido="ABONO")
    elif caso == "hefame":
        kwargs["proveedor"] = "HEFAME"
    elif caso == "sin_exacto":
        a = cand(297826, "08D79748", "77.49", 54736)
    elif caso == "otro_numero":
        b = cand(297825, "08D79746A", "40.76", 54736)
    [r] = buscar([linea], [a, b], **kwargs)
    assert r.estado != "MATCH_R20" and r.complementario is None, caso


def test_dentro_de_la_ventana_de_15_dias_si_casa():
    a, b = cand(297826, "08D79747", "77.49", 54736, dias=15), cand(297825, "08D79747A", "40.76", 54736, dias=-15)
    assert buscar([doc()], [a, b])[0].estado == "MATCH_R20"


def test_dos_variantes_que_cuadran_es_ambiguo():
    otra = cand(297827, "08D79747B", "40.76", 54736)
    [r] = buscar([doc()], [A, B, otra])
    assert (r.estado, r.candidato, r.candidatos_finales) == ("AMBIGUO_R20", None, 2)


def test_pareja_r17_y_pareja_r20_a_la_vez_es_ambiguo():
    interno = cand(297828, "Q040999/2026", "40.76", 54736)
    [r] = buscar([doc()], [A, B, interno])
    assert (r.estado, r.candidatos_finales) == ("AMBIGUO_R20", 2)
    # Sin R20, la misma linea casa por R17 (comportamiento de la 24, sin cambios).
    [r] = buscar([doc()], [A, B, interno], r20=False)
    assert (r.estado, r.complementario) == ("MATCH_R17", interno)


def test_el_mismo_albaran_en_dos_lineas_es_conflicto():
    l1, l2 = doc(ident="l1"), doc(ident="l2")
    r1, r2 = buscar([l1, l2], [A, B])
    assert (r1.estado, r2.estado) == ("CONFLICTO_R20", "CONFLICTO_R20")


def test_r17_sigue_igual_con_r20_habilitada():
    interno = cand(297828, "Q040999/2026", "40.76", 54736)
    [r] = buscar([doc()], [A, interno])
    assert (r.estado, r.complementario) == ("MATCH_R17", interno)
    assert [d.provenance["papel_r17"] for d in detalles_desde_busqueda(doc(), r)] == ["NUMERO", "INTERNO"]


# --------------------------------------------------------------------------- deteccion de la 36

class _Lector:
    """Lector de solo lectura simulado: ``valor`` registra las consultas; la columna solo existe si se indica."""

    def __init__(self, columna: bool, valor=True):
        self.columna, self.v, self.consultas = columna, valor, []

    def valor(self, sql, params=None):
        self.consultas.append(sql)
        if sql == SQL_COLUMNA_R20:
            return self.columna
        if sql == SQL_VALOR_R20:
            if not self.columna:
                raise AssertionError("COLUMNA_INEXISTENTE: abortaria la transaccion de solo lectura")
            return self.v
        raise AssertionError(sql)


def test_sin_la_36_solo_consulta_information_schema_y_r20_queda_desactivada():
    lector = _Lector(columna=False)
    assert r20_habilitada(lector) is False
    assert lector.consultas == [SQL_COLUMNA_R20]
    assert "information_schema.columns" in SQL_COLUMNA_R20


@pytest.mark.parametrize("valor, esperado", [(True, True), (False, False), (None, False)])
def test_con_la_36_lee_la_marca(valor, esperado):
    lector = _Lector(columna=True, valor=valor)
    assert r20_habilitada(lector) is esperado
    assert lector.consultas == [SQL_COLUMNA_R20, SQL_VALOR_R20]


def test_repositorio_sin_deteccion_o_con_deteccion_fallida_deja_r20_desactivada():
    assert RepositorioRuntimeSupabase(None).r20_habilitada() is False

    def rota():
        raise RuntimeError("sin conexion")

    assert RepositorioRuntimeSupabase(None, r20_habilitada=rota).r20_habilitada() is False
    assert RepositorioRuntimeSupabase(None, r20_habilitada=lambda: True).r20_habilitada() is True
    assert RepositorioRuntimeSupabase(None, r20_habilitada=lambda: "t").r20_habilitada() is False
