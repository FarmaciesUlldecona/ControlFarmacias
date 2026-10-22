"""Hito 2BA: R15 (exclusividad), R15b, R15c, R16 y decisiones de Pio, sin base de datos.

Casos reales: los 9 casados de produccion sin numero exacto (lectura READ_ONLY del
2026-10-08) y 08C66676 / 08C66676A (08009718). Paginacion: un servidor que corta a
1.000 filas (o menos) no oculta albaranes de la ventana.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from simulador_conciliacion_2av import SupabaseConciliacionMemoria
from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    buscar_albaranes_factura,
    buscar_candidato_albaran,
    clasificar_numero_albaran,
)
from src.facturas.runtime_supabase.modelos import FacturaTrabajo
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase, leer_paginado

ALLIANCE = "ALLIANCE HEALTHCARE ESPAÑA, S.A."
DIA = date(2026, 7, 23)


def cand(contador, numero, puc, *, dias=0, pvp="99.99", proveedor="1.- SAFA", id_proveedor="2"):
    return CandidatoAlbaranSupabase(contador, "PIO", id_proveedor, proveedor, numero, DIA + timedelta(days=dias),
                                    Decimal(puc), Decimal(pvp), "PENDIENTE")


def doc(numero, importe, *, ident="d", fecha=DIA):
    return AlbaranDocumentalTrabajo(ident, numero, fecha, Decimal(importe), "CARGO")


def buscar(documental, candidatos, **kwargs):
    return buscar_candidato_albaran(documental, candidatos, proveedor_literal=kwargs.pop("proveedor", ALLIANCE),
                                    **kwargs)


# ----------------------------------------------------------------- clasificacion (R15b y reglas 1-4)

@pytest.mark.parametrize("documental,farmatic,alliance,clase", [
    ("08C52171", "08C52171", True, "EXACTA"),
    ("08C52171", "08C52171A", True, "LETRA_FINAL"),       # regla 1
    ("08B91475", "08B91475B", True, "LETRA_FINAL"),
    ("08C52171", "08C52172A", True, "PROVEEDOR"),          # letra sobre otro numero
    ("08C52171", "08C52171A", False, "SIN_PATRON"),        # la regla 1 es solo Alliance
    ("9319977575", "19977575", False, "FINAL_DOCUMENTAL"),  # regla 2 (Logista)
    ("9319977575", "9977575", False, "SIN_PATRON"),        # menos de 8 digitos
    ("08C18299", "Q039904/2026", True, "INTERNO"),        # regla 4
    ("08C18299", "R006751/2026", True, "INTERNO"),
    ("08C18299", "110114295466", True, "PROVEEDOR"),       # regla 3: SAFA de 12 digitos
    ("08C18299", "08M24229", True, "PROVEEDOR"),           # R15b
    ("OTRO", "123456", False, "SIN_PATRON"),
])
def test_clasificacion_de_numeros(documental, farmatic, alliance, clase):
    assert clasificar_numero_albaran(documental, farmatic, alliance=alliance) == clase


# ----------------------------------------------------------------- R15b y R15c

def test_r15b_alliance_no_casa_por_importe_con_numero_de_proveedor_distinto():
    r = buscar(doc("08D33181", "8.84"), [cand(1, "08D33182", "8.84")])
    assert (r.estado, r.candidato) == ("NUMERO_PROVEEDOR_DISTINTO", None)


def test_r15b_safa_12_digitos_falla_cerrado():
    r = buscar(doc("08C18299", "70.45"), [cand(1, "110114295466", "70.45")])
    assert (r.estado, r.candidato) == ("NUMERO_PROVEEDOR_DISTINTO", None)


def test_r15b_interno_casa_por_puc_pero_nunca_por_pvp():
    assert buscar(doc("08C18299", "191.84"), [cand(1, "Q039904/2026", "191.84")]).clase_numero == "INTERNO"
    r = buscar(doc("08C18299", "313.29"), [cand(1, "Q039904/2026", "191.84", pvp="313.29")])
    assert r.candidato is None  # D11 se mantiene


@pytest.mark.parametrize("dias,casa", [(3, True), (-3, True), (4, False), (-4, False)])
def test_r15c_numero_distinto_solo_a_3_dias(dias, casa):
    r = buscar(doc("08C18299", "191.84"), [cand(1, "Q039904/2026", "191.84", dias=dias)])
    assert (r.candidato is not None) is casa


@pytest.mark.parametrize("clase_numero,numero", [("EXACTA", "08C52171"), ("LETRA_FINAL", "08C52171A")])
@pytest.mark.parametrize("dias,casa", [(15, True), (-15, True), (16, False)])
def test_r15c_coincidencia_de_numero_a_15_dias(clase_numero, numero, dias, casa):
    r = buscar(doc("08C52171", "12.21"), [cand(1, numero, "12.21", dias=dias)])
    assert (r.candidato is not None) is casa
    if casa:
        assert r.clase_numero == clase_numero


def test_letra_final_admite_pvp_como_el_numero_exacto():
    r = buscar(doc("08C52171", "20.00"), [cand(1, "08C52171A", "12.21", pvp="20.00")])
    assert (r.estado, r.clase_numero, r.importe_compatible) == ("MATCH_UNICO", "LETRA_FINAL", Decimal("20.0000"))


# ----------------------------------------------------------------- decisiones de Pio sobre la letra final

def test_exacto_se_impone_a_la_letra_final_08009718():
    """08C66676 (31,59): Farmatic tiene 08C66676 y 08C66676A, misma fecha y PUC 31,58."""
    r = buscar(doc("08C66676", "31.59"), [cand(285616, "08C66676", "31.58", pvp="43.91"),
                                          cand(285617, "08C66676A", "31.58", pvp="43.91")])
    assert (r.estado, r.clase_numero, r.candidato.id_contador) == ("MATCH_UNICO", "EXACTA", 285616)


def test_varias_letras_finales_que_el_importe_no_separa_no_casan():
    # Distinta fecha: la fecha no desempata entre coincidencias por letra final.
    r = buscar(doc("08C52171", "12.21"), [cand(1, "08C52171A", "12.21"), cand(2, "08C52171B", "12.21", dias=1)])
    assert (r.estado, r.candidato) == ("AMBIGUO", None)
    r = buscar(doc("08C52171", "12.21"), [cand(1, "08C52171A", "12.21"), cand(2, "08C52171B", "12.50")])
    assert r.candidato.id_contador == 1  # el importe si decide


# ----------------------------------------------------------------- R15: exclusividad

def test_r15_salta_el_ocupado_y_usa_el_libre():
    candidatos = [cand(1, "08C52171", "12.21"), cand(2, "08C52171A", "12.21")]
    r = buscar(doc("08C52171", "12.21"), candidatos, ocupados={("PIO", 1)})
    assert (r.estado, r.candidato.id_contador, r.clase_numero) == ("MATCH_UNICO", 2, "LETRA_FINAL")


def test_r15_solo_ocupado_queda_albaran_ya_conciliado():
    r = buscar(doc("08C52171", "12.21"), [cand(1, "08C52171", "12.21")], ocupados={("PIO", 1)})
    assert (r.estado, r.candidato) == ("ALBARAN_YA_CONCILIADO", None)


def test_r15_opcion_2_no_toma_por_importe_el_numero_de_otra_factura():
    r = buscar(doc("08C18299", "191.84"), [cand(1, "Q039904/2026", "191.84")],
               numeros_otras_facturas={"Q039904/2026"})
    assert r.candidato is None
    # Por numero (exacto o letra final) si: el numero es de esta linea.
    r = buscar(doc("08C52171", "12.21"), [cand(1, "08C52171", "12.21")], numeros_otras_facturas={"08C52171"})
    assert r.candidato.id_contador == 1


def test_r15_dentro_de_la_factura_primero_las_lineas_con_numero():
    """La linea 1 podria casar por PUC con Q000001/2026, pero es por numero de la linea 2."""
    docs = [doc("08C11111", "50.00", ident="l1"), doc("Q000001/2026", "50.00", ident="l2")]
    resultados = buscar_albaranes_factura(docs, [cand(7, "Q000001/2026", "50.00")], proveedor_literal=ALLIANCE)
    assert [r.candidato.id_contador if r.candidato else None for r in resultados] == [None, 7]
    assert resultados[0].estado == "ALBARAN_YA_CONCILIADO"


def test_r15_un_albaran_solo_justifica_una_linea_de_la_factura():
    docs = [doc("08C52171", "12.21", ident="l1"), doc("08C52171", "12.21", ident="l2")]
    resultados = buscar_albaranes_factura(docs, [cand(1, "08C52171", "12.21")], proveedor_literal=ALLIANCE)
    assert [r.estado for r in resultados] == ["MATCH_UNICO", "ALBARAN_YA_CONCILIADO"]


# ----------------------------------------------------------------- produccion (READ_ONLY 2026-10-08)

PRODUCCION_ALLIANCE = [  # factura, documental, farmatic, PUC
    ("08009277", "08C52171", "08C52171A", "12.21"), ("08009277", "08C59254", "08C59254A", "6.37"),
    ("08009277", "08M49141", "08M49141A", "11.50"), ("08009278", "08C50781", "08C50781A", "90.73"),
    ("08009278", "08C52355", "08C52355A", "1.42"), ("08009278", "08M44966", "08M44966A", "1.37"),
    ("08009278", "08C56226", "08C56226A", "52.70"), ("08009279", "08C57517", "08C57517A", "13.54"),
]


@pytest.mark.parametrize("factura,documental,farmatic,puc", PRODUCCION_ALLIANCE)
def test_casados_de_produccion_alliance_siguen_casando(factura, documental, farmatic, puc):
    r = buscar(doc(documental, puc), [cand(1, farmatic, puc)])
    assert (r.estado, r.clase_numero) == ("MATCH_UNICO", "LETRA_FINAL"), factura


def test_casado_de_produccion_logista_sigue_casando_a_6_dias():
    documental = AlbaranDocumentalTrabajo("d", "9319977575", date(2026, 7, 29), Decimal("448.00"), "CARGO")
    candidato = CandidatoAlbaranSupabase(285484, "PIO", "158", "LOGISTAPHARMA", "19977575", date(2026, 8, 4),
                                         Decimal("448.00"), Decimal("1048.40"), "PENDIENTE")
    r = buscar_candidato_albaran(documental, [candidato], proveedor_literal="LOGISTA PHARMA S.A.U.")
    assert (r.estado, r.clase_numero, r.candidato.id_contador) == ("MATCH_UNICO", "FINAL_DOCUMENTAL", 285484)


# ----------------------------------------------------------------- simulador alineado (R15, R16)

def _resultado(*contadores, resultado="CONCILIADA"):
    detalles = [{"orden": i, "tipo_relacion": "UNO_A_UNO", "albaran_farmacia": "PIO", "albaran_id_contador": c}
                for i, c in enumerate(contadores, 1)]
    return {"resultado": resultado, "diferencia": "0" if resultado == "CONCILIADA" else "1", "tolerancia": "0.0500",
            "detalles": detalles}


def _persistir(sim, factura, clave, resultado):
    sim.facturas[factura].bloqueado_por = "w"
    sim.historial.append(("CONCILIACION_CLAIM", factura, {"modo_ejecucion": "MANUAL_ONE_SHOT", "actor": "w"}))
    return sim.rpc("cf_persistir_conciliacion", {"p_factura_id": factura, "p_worker_id": "w",
                                                 "p_disparador": "MANUAL_ONE_SHOT", "p_idempotency_key": clave,
                                                 "p_resultado": resultado}).data


def test_simulador_r15_rechaza_albaran_de_otra_factura_y_admite_los_propios():
    sim = SupabaseConciliacionMemoria()
    sim.anadir("A", "2026-07-01")
    sim.anadir("B", "2026-07-02")
    _persistir(sim, "A", "a1", _resultado(1, 2, resultado="DIFERENCIA"))
    with pytest.raises(RuntimeError, match="ALBARAN_YA_CONCILIADO"):
        _persistir(sim, "B", "b1", _resultado(2))
    with pytest.raises(RuntimeError, match="ALBARAN_YA_CONCILIADO"):
        _persistir(sim, "B", "b2", _resultado(3, 3))
    _persistir(sim, "A", "a2", _resultado(2, 4))  # nuevo intento de A: reutiliza 2 y libera 1
    assert sim.reservas == {("PIO", 2): "A", ("PIO", 4): "A"}
    _persistir(sim, "B", "b3", _resultado(1))
    assert sim.reservas[("PIO", 1)] == "B"


@pytest.mark.parametrize("lineas,tolerancia", [(0, "0.05"), (7, "0.07"), (134, "0.50")])
def test_simulador_r16_tolerancia_de_elegibilidad(lineas, tolerancia):
    assert SupabaseConciliacionMemoria().tolerancia_elegibilidad(lineas) == Decimal(tolerancia)


# ----------------------------------------------------------------- paginacion (riesgo de corte en 1.000 filas)

class _Respuesta:
    def __init__(self, data):
        self.data = data


class _Consulta:
    def __init__(self, cliente, tabla):
        self.cliente, self.tabla, self.filtros, self.rango, self.unica = cliente, tabla, [], None, False

    def select(self, _columnas):
        return self

    def eq(self, columna, valor):
        self.filtros.append(lambda f: str(f.get(columna)) == str(valor))
        return self

    def gte(self, columna, valor):
        self.filtros.append(lambda f: f.get(columna) >= valor)
        return self

    def lte(self, columna, valor):
        self.filtros.append(lambda f: f.get(columna) <= valor)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def single(self):
        self.unica = True
        return self

    def range(self, inicio, fin):
        self.rango = (inicio, fin)
        return self

    def execute(self):
        filas = [f for f in self.cliente.filas[self.tabla] if all(c(f) for c in self.filtros)]
        if self.unica:
            return _Respuesta(filas[0])
        inicio, fin = self.rango or (0, len(filas) - 1)
        self.cliente.lecturas.append((self.tabla, self.rango))
        # Como PostgREST: nunca devuelve mas de max_rows filas por peticion.
        return _Respuesta(filas[inicio:fin + 1][:self.cliente.max_rows])


class _Cliente:
    def __init__(self, filas, max_rows):
        self.filas, self.max_rows, self.lecturas = filas, max_rows, []

    def table(self, tabla):
        return _Consulta(self, tabla)


def _escenario(n_albaranes=1500, objetivo=1400):
    albaranes = [{"id_contador": i, "farmacia": "PIO", "id_proveedor": "2", "proveedor": "1.- SAFA",
                  "numero_albaran": "08C99999" if i == objetivo else f"08M{i:05d}", "fecha": "2026-07-15",
                  "importe_puc": "10.00" if i == objetivo else "1.00", "importe_pvp": "2.00", "estado": "PENDIENTE"}
                 for i in range(1, n_albaranes + 1)]
    return {
        "facturas": [{"id": "f1", "proveedor_literal": ALLIANCE, "proveedor_nombre": None, "proveedor_id": None,
                      "categoria": "MERCANCIA", "iva_total": "0", "recargo_equivalencia_total": "0",
                      "datos_extraidos": {"naturaleza_principal": "MERCANCIA"}}],
        "facturas_albaranes_extraidos": [{"id": "e1", "factura_id": "f1", "numero_albaran": "08C99999",
                                          "fecha_albaran": "2026-07-15", "importe_total": "10.00",
                                          "tipo_movimiento": "CARGO"}],
        "albaranes": albaranes,
        "conciliacion_albaranes_reservados": [],
        # 2BD (migracion 22): la conciliacion lee las revisiones AUSENTE_EN_FARMATIC.
        "albaranes_cambios": [],
    }


@pytest.mark.parametrize("max_rows", [1000, 400])
def test_lectura_de_candidatos_paginada_con_mas_de_1000_albaranes_en_ventana(max_rows):
    cliente = _Cliente(_escenario(), max_rows)
    [detalle] = RepositorioRuntimeSupabase(cliente).construir_detalles(FacturaTrabajo("f1", "d1", "PIO", Decimal("10")))
    assert (detalle.albaran_id_contador, detalle.importe_aplicado) == (1400, Decimal("10.0000"))
    lecturas = [r for t, r in cliente.lecturas if t == "albaranes"]
    assert len(lecturas) >= 2 and lecturas[-1] is not None  # paginas sucesivas hasta una vacia


def test_sin_paginar_el_corte_de_1000_filas_perderia_el_albaran():
    """Control: la consulta anterior (una sola peticion) solo veria los 1.000 primeros."""
    cliente = _Cliente(_escenario(), 1000)
    unica = cliente.table("albaranes").select("*").eq("farmacia", "PIO").execute().data
    assert len(unica) == 1000 and not [f for f in unica if f["id_contador"] == 1400]
    todas = leer_paginado(lambda: cliente.table("albaranes").select("*").eq("farmacia", "PIO").order("id_contador"))
    assert len(todas) == 1500


def test_reservas_de_otra_factura_bloquean_y_las_propias_no():
    filas = _escenario(n_albaranes=1500)
    filas["conciliacion_albaranes_reservados"] = [{"albaran_farmacia": "PIO", "albaran_id_contador": 1400,
                                                   "factura_id": "otra"}]
    [detalle] = RepositorioRuntimeSupabase(_Cliente(filas, 1000)).construir_detalles(
        FacturaTrabajo("f1", "d1", "PIO", Decimal("10")))
    assert detalle.albaran_id_contador is None
    assert detalle.provenance["estado_matching"] == "ALBARAN_YA_CONCILIADO"
    filas["conciliacion_albaranes_reservados"][0]["factura_id"] = "f1"  # nuevo intento de la misma factura
    [detalle] = RepositorioRuntimeSupabase(_Cliente(filas, 1000)).construir_detalles(
        FacturaTrabajo("f1", "d1", "PIO", Decimal("10")))
    assert detalle.albaran_id_contador == 1400


def test_2bd_albaran_ausente_en_farmatic_queda_fuera_del_casado():
    filas = _escenario(n_albaranes=1500)
    ausente = {"id": 1, "farmacia": "PIO", "id_contador": 1400, "campo": "presencia", "valor_nuevo": "AUSENTE"}
    filas["albaranes_cambios"] = [ausente]
    [detalle] = RepositorioRuntimeSupabase(_Cliente(filas, 1000)).construir_detalles(
        FacturaTrabajo("f1", "d1", "PIO", Decimal("10")))
    assert detalle.albaran_id_contador is None
    # Reaparece en Farmatic: la revision se cierra y vuelve a casar.
    filas["albaranes_cambios"].append({**ausente, "id": 2, "valor_nuevo": "PRESENTE"})
    [detalle] = RepositorioRuntimeSupabase(_Cliente(filas, 1000)).construir_detalles(
        FacturaTrabajo("f1", "d1", "PIO", Decimal("10")))
    assert detalle.albaran_id_contador == 1400
