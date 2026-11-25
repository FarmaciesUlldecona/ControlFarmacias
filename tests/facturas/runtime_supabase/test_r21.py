"""R21 (DECISIONES DE PIO, 2026-11-24; R21-D1 revisada el 2026-11-25; migracion 39): linea PDF = albaran exacto + 1 a 3
complementarios (internos de Farmatic o variante con letra final) del mismo proveedor, de la misma recepcion que A o,
sin recepcion, del mismo dia que A.

Sin base de datos. Caso real 08005707 / 08L82633 con los albaranes leidos en modo READ_ONLY el 2026-11-24
(``carga_abril_mayo/noche_2411/08L82633A.json``) y la regresion que encontro el banco R21-D8 del 2026-11-25 (08005706 y
08012619: un interno de la recepcion de A y una variante del mismo dia de OTRA recepcion con el mismo PUC; con la D1
original quedaban AMBIGUO_R21, con la revisada siguen MATCH_R17). Variantes que fallan cerrado, deteccion de la 39 y
repositorio sin deteccion.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.facturas.runtime_supabase.conciliacion import (
    R21_TOPE_CANDIDATOS,
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    ReglaTolerancia,
    buscar_albaranes_factura,
    conciliar_importes,
    detalles_desde_busqueda,
    valores_por_linea,
)
from src.facturas.runtime_supabase.lectura_readonly import SQL_COLUMNA_R21, SQL_VALOR_R21, r21_habilitada
from src.facturas.runtime_supabase.modelos import TipoRelacionConciliacion
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase

ALLIANCE = "ALLIANCE HEALTHCARE ESPAÑA, S.A."
DIA = date(2026, 5, 5)
REGLA = ReglaTolerancia(suelo=Decimal("0.05"), por_albaran=Decimal("0.01"), tope=Decimal("0.50"))


def cand(contador, numero, puc, recepcion, *, dias=0, id_proveedor="0002 ", proveedor="1.- SAFA", farmacia="PIO"):
    return CandidatoAlbaranSupabase(contador, farmacia, id_proveedor, proveedor, numero, DIA + timedelta(days=dias),
                                    Decimal(puc), Decimal("9999.99"), "PENDIENTE", id_recepcion=recepcion)


def doc(numero="08L82633", importe="688.13", *, ident="l1", sentido="CARGO", dias=0):
    return AlbaranDocumentalTrabajo(ident, numero, DIA + timedelta(days=dias), Decimal(importe), sentido)


# 08005707 / 08L82633 (PDF 05/05, 688,13): A + interno de la misma recepcion (06/05) + variante sin recepcion (05/05).
A = cand(272819, "08L82633", "638.82", 49490)
Q = cand(272818, "Q039320/2026", "27.32", 49490, dias=1)
V = cand(299725, "08L82633A", "21.99", None)


def buscar(docs, candidatos, *, r21=True, r20=True, **kwargs):
    return buscar_albaranes_factura(docs, candidatos, proveedor_literal=kwargs.pop("proveedor", ALLIANCE),
                                    r20_habilitada=r20, r21_habilitada=r21, **kwargs)


# --------------------------------------------------------------------------- caso real 08005707

def test_caso_real_08005707_casa_por_r21_con_tres_detalles_y_cuenta_una_linea_en_r11():
    linea = doc()
    [r] = buscar([linea], [A, Q, V])
    assert (r.estado, r.candidato, r.complementarios, r.clase_numero) == ("MATCH_R21", A, (Q, V), "EXACTA")
    detalles = detalles_desde_busqueda(linea, r)
    assert [(d.tipo_relacion, d.albaran_id_contador, d.importe_aplicado) for d in detalles] == [
        (TipoRelacionConciliacion.UNO_A_VARIOS, 272819, Decimal("638.8200")),
        (TipoRelacionConciliacion.UNO_A_VARIOS, 272818, Decimal("27.3200")),
        (TipoRelacionConciliacion.UNO_A_VARIOS, 299725, Decimal("21.9900"))]
    assert [(d.provenance["regla"], d.provenance["papel_r21"], d.provenance["motivo_r21"]) for d in detalles] == [
        ("R21", "NUMERO", None), ("R21", "INTERNO", "MISMA_RECEPCION"), ("R21", "LETRA_FINAL", "MISMO_DIA_SIN_RECEPCION")]
    assert {(d.provenance["importe_combinacion"], d.provenance["tolerancia_linea"], d.provenance["complementarios"],
             d.provenance["combinaciones_evaluadas"]) for d in detalles} == {("688.1300", "0.0500", 2, 1)}
    assert {d.factura_albaran_extraido_id for d in detalles} == {"l1"}
    assert [d.coincidencia_numero_literal for d in detalles] == [True, False, False]
    assert all("papel_r17" not in d.provenance and "papel_r20" not in d.provenance for d in detalles)
    assert {v.estado for v in valores_por_linea(detalles)} == {"COINCIDE"}
    resultado = conciliar_importes("688.13", detalles, regla=REGLA)
    assert (resultado.resultado, resultado.diferencia, resultado.albaranes_casados) == (
        "CONCILIADA", Decimal("0.0000"), 1)


def test_sin_r21_habilitada_la_linea_queda_sin_coincidencia():
    [r] = buscar([doc()], [A, Q, V], r21=False)
    assert (r.estado, r.complementario, r.complementarios) == ("SIN_COINCIDENCIA", None, ())
    [r] = buscar_albaranes_factura([doc()], [A, Q, V], proveedor_literal=ALLIANCE, r20_habilitada=True)
    assert r.estado == "SIN_COINCIDENCIA"  # por defecto, apagada


def test_con_la_d1_original_mismo_dia_de_otra_recepcion_no_entra():
    # R21-D1 revisada (Pio, 2026-11-25): el mismo dia solo vale para un complementario SIN recepcion.
    v_otra_recepcion = cand(299725, "08L82633A", "21.99", 49491)
    [r] = buscar([doc()], [A, Q, v_otra_recepcion])
    assert r.estado == "SIN_COINCIDENCIA"


# --------------------------------------------------------------------------- regresion del banco R21-D8 (2026-11-25)

@pytest.mark.parametrize("numero, importe, a, interno, variante", [
    ("08B56937", "616.07", (273064, "603.27", 49546), (273063, "Q039349/2026", "12.80", 49546),
     (273067, "08B56937A", "12.80", 49547)),
    ("08D52644", "1036.44", (294730, "1009.25", 54099), (294729, "Q040931/2026", "27.20", 54099),
     (294732, "08D52644A", "27.20", 54100)),
])
def test_r17_de_08005706_y_08012619_sigue_igual_con_r21(numero, importe, a, interno, variante):
    ca = cand(a[0], numero, a[1], a[2])
    ci = cand(interno[0], interno[1], interno[2], interno[3])
    cv = cand(variante[0], variante[1], variante[2], variante[3])
    linea = doc(numero, importe)
    sin = buscar([linea], [ca, ci, cv], r21=False)
    con = buscar([linea], [ca, ci, cv])
    assert sin == con
    assert (con[0].estado, con[0].candidato, con[0].complementario) == ("MATCH_R17", ca, ci)


# --------------------------------------------------------------------------- regla

def test_un_complementario_sin_recepcion_del_mismo_dia_casa_por_r21():
    linea = doc(importe="660.81")
    [r] = buscar([linea], [A, V])
    assert (r.estado, r.complementarios) == ("MATCH_R21", (V,))
    assert len(detalles_desde_busqueda(linea, r)) == 2


def test_tres_complementarios_casan_y_cuatro_no():
    q2, q3 = cand(272900, "Q039330/2026", "1.00", 49490), cand(272901, "Q039331/2026", "2.50", 49490)
    # 689,13 = A + Q + V + q2 (3 complementarios; ningun otro subconjunto suma lo mismo).
    [r] = buscar([doc(importe="689.13")], [A, Q, V, q2, q3])
    assert (r.estado, r.complementarios) == ("MATCH_R21", (Q, V, q2))
    assert len(detalles_desde_busqueda(doc(importe="689.13"), r)) == 4
    # 691,63 = A + los 4: haria falta un cuarto complementario.
    [r] = buscar([doc(importe="691.63")], [A, Q, V, q2, q3])
    assert r.estado == "SIN_COINCIDENCIA"


def test_dos_combinaciones_es_ambiguo():
    otro = cand(272830, "Q039399/2026", "27.32", 49490)
    [r] = buscar([doc()], [A, Q, V, otro])
    assert (r.estado, r.candidato, r.candidatos_finales) == ("AMBIGUO_R21", None, 2)


def test_el_mismo_albaran_en_dos_lineas_es_conflicto():
    l1, l2 = doc(ident="l1"), doc(ident="l2")
    r1, r2 = buscar([l1, l2], [A, Q, V])
    assert (r1.estado, r2.estado) == ("CONFLICTO_R21", "CONFLICTO_R21")


def test_mas_de_12_candidatos_es_ambiguo_con_motivo():
    internos = [cand(273000 + i, f"Q04{i:04d}/2026", "1.00", 49490) for i in range(R21_TOPE_CANDIDATOS + 1)]
    linea = doc(importe="640.82")
    [r] = buscar([linea], [A, *internos])
    assert (r.estado, r.motivo) == ("AMBIGUO_R21", "DEMASIADOS_CANDIDATOS")
    [d] = detalles_desde_busqueda(linea, r)
    assert (d.tipo_relacion, d.provenance["motivo"]) == (TipoRelacionConciliacion.SIN_COINCIDENCIA,
                                                         "DEMASIADOS_CANDIDATOS")
    # Con 12 (el tope) si se enumera: 2 internos que suman 2,00 entre 12 iguales -> muchas combinaciones, ambiguo.
    [r] = buscar([linea], [A, *internos[:R21_TOPE_CANDIDATOS]])
    assert (r.estado, r.motivo) == ("AMBIGUO_R21", None)


def test_sin_motivo_la_provenance_de_sin_coincidencia_no_cambia():
    [r] = buscar([doc()], [A], r21=False)
    [d] = detalles_desde_busqueda(doc(), r)
    assert "motivo" not in d.provenance


@pytest.mark.parametrize("caso", ["otro_proveedor", "eco360", "otra_recepcion", "sin_recepcion_otro_dia",
                                  "puc_cero", "puc_negativo", "reservado", "numero_de_otra_factura", "otra_farmacia",
                                  "no_interno_ni_variante", "variante_de_otro_numero", "a_letra_final",
                                  "a_fuera_de_ventana", "suma_fuera", "abono", "hefame", "a_sin_puc"])
def test_variantes_que_no_son_r21(caso):
    linea, a, q, v, kwargs = doc(), A, Q, V, {}
    if caso == "otro_proveedor":
        q = cand(272818, "Q039320/2026", "27.32", 49490, dias=1, id_proveedor="52")
    elif caso == "eco360":
        v = cand(299725, "08L82633A", "21.99", None, id_proveedor="154", proveedor="6- PLATAF. ECO360 AH")
    elif caso == "otra_recepcion":
        q = cand(272818, "Q039320/2026", "27.32", 49491, dias=1)
    elif caso == "sin_recepcion_otro_dia":
        v = cand(299725, "08L82633A", "21.99", None, dias=1)
    elif caso == "puc_cero":
        v = cand(299725, "08L82633A", "0.00", None)
        linea = doc(importe="666.14")
    elif caso == "puc_negativo":
        v = cand(299725, "08L82633A", "-21.99", None)
        linea = doc(importe="644.15")
    elif caso == "reservado":
        kwargs["ocupados"] = {("PIO", 299725)}
    elif caso == "numero_de_otra_factura":
        kwargs["numeros_otras_facturas"] = ["Q039320/2026"]
    elif caso == "otra_farmacia":
        v = cand(299725, "08L82633A", "21.99", None, farmacia="RITA")
    elif caso == "no_interno_ni_variante":
        v = cand(299725, "08L99999", "21.99", None)
    elif caso == "variante_de_otro_numero":
        v = cand(299725, "08L82634A", "21.99", None)
    elif caso == "a_letra_final":
        a = cand(272819, "08L82633B", "638.82", 49490)
    elif caso == "a_fuera_de_ventana":
        a, q, v = (replace(x, fecha=x.fecha + timedelta(days=16)) for x in (A, Q, V))
    elif caso == "suma_fuera":
        linea = doc(importe="688.19")
    elif caso == "abono":
        linea = doc(sentido="ABONO")
    elif caso == "hefame":
        kwargs["proveedor"] = "HEFAME"
    elif caso == "a_sin_puc":
        a = replace(A, importe_puc=None)
    [r] = buscar([linea], [a, q, v], **kwargs)
    assert r.estado != "MATCH_R21" and r.complementarios == (), caso


def test_dentro_de_la_ventana_de_15_dias_si_casa():
    a, q, v = (replace(x, fecha=x.fecha + timedelta(days=15)) for x in (A, Q, V))
    assert buscar([doc()], [a, q, v])[0].estado == "MATCH_R21"


def test_r17_y_r20_siguen_con_su_regla_con_r21_habilitada():
    # R17: A + interno de la misma recepcion. El mismo conjunto tambien es R21; conserva R17.
    linea = doc(importe="666.14")
    [r] = buscar([linea], [A, Q])
    assert (r.estado, r.complementario, r.complementarios) == ("MATCH_R17", Q, ())
    assert [d.provenance["papel_r17"] for d in detalles_desde_busqueda(linea, r)] == ["NUMERO", "INTERNO"]
    # R20: A + variante de la misma recepcion.
    v = cand(299725, "08L82633A", "21.99", 49490)
    [r] = buscar([doc(importe="660.81")], [A, v])
    assert (r.estado, r.complementario, r.complementarios) == ("MATCH_R20", v, ())


def test_el_1a1_tiene_prioridad():
    exacto = cand(1, "08L82633", "688.13", 49490)
    [r] = buscar([doc()], [exacto, Q, V])
    assert (r.candidato, r.complementarios, r.importe_compatible) == (exacto, (), Decimal("688.1300"))


def test_resultado_r21_incompleto_falla_cerrado():
    [r] = buscar([doc()], [A, Q, V])
    with pytest.raises(ValueError, match="RESULTADO_R21_INCOMPLETO"):
        detalles_desde_busqueda(doc(), replace(r, complementarios=()))
    with pytest.raises(ValueError, match="RESULTADO_R21_INCOMPLETO"):
        detalles_desde_busqueda(doc(), replace(r, complementarios=(Q, V, Q, V)))


# --------------------------------------------------------------------------- deteccion de la 39

class _Lector:
    """Lector de solo lectura simulado: ``valor`` registra las consultas; la columna solo existe si se indica."""

    def __init__(self, columna: bool, valor=True):
        self.columna, self.v, self.consultas = columna, valor, []

    def valor(self, sql, params=None):
        self.consultas.append(sql)
        if sql == SQL_COLUMNA_R21:
            return self.columna
        if sql == SQL_VALOR_R21:
            if not self.columna:
                raise AssertionError("COLUMNA_INEXISTENTE: abortaria la transaccion de solo lectura")
            return self.v
        raise AssertionError(sql)


def test_sin_la_39_solo_consulta_information_schema_y_r21_queda_desactivada():
    lector = _Lector(columna=False)
    assert r21_habilitada(lector) is False
    assert lector.consultas == [SQL_COLUMNA_R21]
    assert "information_schema.columns" in SQL_COLUMNA_R21 and "conciliacion_r21" in SQL_COLUMNA_R21


@pytest.mark.parametrize("valor, esperado", [(True, True), (False, False), (None, False)])
def test_con_la_39_lee_la_marca(valor, esperado):
    lector = _Lector(columna=True, valor=valor)
    assert r21_habilitada(lector) is esperado
    assert lector.consultas == [SQL_COLUMNA_R21, SQL_VALOR_R21]


def test_repositorio_sin_deteccion_o_con_deteccion_fallida_deja_r21_desactivada():
    assert RepositorioRuntimeSupabase(None).r21_habilitada() is False

    def rota():
        raise RuntimeError("sin conexion")

    assert RepositorioRuntimeSupabase(None, r21_habilitada=rota).r21_habilitada() is False
    assert RepositorioRuntimeSupabase(None, r21_habilitada=lambda: True).r21_habilitada() is True
    assert RepositorioRuntimeSupabase(None, r21_habilitada=lambda: "t").r21_habilitada() is False
    # R20 no depende de la marca de R21.
    assert RepositorioRuntimeSupabase(None, r21_habilitada=lambda: True).r20_habilitada() is False
