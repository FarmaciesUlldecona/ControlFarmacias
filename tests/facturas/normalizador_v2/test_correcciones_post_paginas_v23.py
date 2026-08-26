from __future__ import annotations

import copy
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.normalizador_v2.modelos import (
    EstadoValidacion, Evidencia, FacturaNormalizada, FechaDocumental, NaturalezaPrincipal,
    ResultadoControl, ResultadoValidacion, Tercero, Totales, ValorDocumentado, Vencimiento,
)
from src.facturas.normalizador_v2.normalizador_general import normalizar_candidato
from src.facturas.normalizador_v2.splitter import consolidar_lecturas


def _span(texto: str, literal: str) -> dict[str, int]:
    inicio = texto.index(literal)
    return {"inicio": inicio, "fin": inicio + len(literal)}


def _campo(valor, literal: str, fila: str, *, span=None):
    return {"valor": valor, "literal": literal, "span_fila": _span(fila, literal) if span is None else span}


def _estructura(eid="tabla", *, literal="CARGOS", sentido="CARGO", pagina=1, tipo="SECCION"):
    return {
        "id": eid, "tipo": "TABLA", "paginas": [pagina],
        "elementos": [
            {"id": f"s_{eid}", "tipo": tipo, "literal": literal, "pagina": pagina,
             "span_pagina": {"inicio": 0, "fin": len(literal)}, "valor_sentido": sentido},
            {"id": f"h_{eid}", "tipo": "COLUMNA", "literal": "NUMERO", "pagina": pagina,
             "span_pagina": {"inicio": 10, "fin": 16}, "valor_sentido": None},
        ],
    }


def _candidato(*, externo=False, directo=False):
    fila = "01-08-2026 NORMAL A-1 10,00"
    if directo:
        fila += " CARGO"
    sentido = _campo("CARGO", "CARGO", fila) if directo else {
        "valor": "CARGO", "literal": "CARGOS", "span_fila": {"inicio": 0, "fin": 6},
    }
    tabla = _estructura()
    estructuras = [tabla]
    ids = ["s_tabla", "h_tabla"]
    sentido_id = "s_tabla"
    if externo:
        seccion = _estructura("seccion")
        seccion["tipo"] = "SECCION"
        estructuras = [tabla, seccion]
        ids = ["s_seccion", "h_tabla"]
        sentido_id = "s_seccion"
    albaran = {
        "orden": 1,
        "contexto_fila": {
            "estructura_id": "tabla", "elementos_contexto_ids": ids, "elemento_sentido_id": sentido_id,
            "pagina": 1, "literal_fila": fila, "span_pagina": {"inicio": 100, "fin": 100 + len(fila)},
            "posicion": {"segmento": 1, "fila": 1, "zona": "tabla"},
        },
        "fecha": _campo("01-08-2026", "01-08-2026", fila),
        "numero": _campo("A-1", "A-1", fila), "sentido": sentido,
        "tipo_pedido": _campo("NORMAL", "NORMAL", fila),
        "importe_base": _campo(Decimal("10"), "10,00", fila), "importe_total": None,
    }
    return {
        "tipo_documento": None, "naturaleza_principal": "MERCANCIA",
        "requiere_conciliacion_albaranes": True, "pagina_inicio": 1, "pagina_fin": 2,
        "proveedor": None, "numero_factura": None, "fecha_factura": None,
        "base_imponible_total": None, "iva_total": None, "recargo_equivalencia_total": None,
        "otros_total": None, "importe_total": None, "moneda": None, "vencimientos": [],
        "impuestos": [], "albaranes": [albaran], "movimientos_comerciales": [],
        "destinatario": None, "forma_pago": None, "referencias_documentales": [],
        "discrepancias_documentales": [], "evidencias": [], "estructuras_documentales": estructuras,
    }


def _aceptados(raw) -> int:
    return len(normalizar_candidato(raw).albaranes)


def test_fallback_same_structure_span_invalido_seccion_unica():
    assert _aceptados(_candidato()) == 1


def test_fallback_seccion_externa_estricta():
    assert _aceptados(_candidato(externo=True)) == 1


def test_fallback_rechaza_dos_secciones_compatibles():
    raw = _candidato()
    raw["estructuras_documentales"][0]["elementos"].append(copy.deepcopy(raw["estructuras_documentales"][0]["elementos"][0]) | {"id": "s_dos"})
    raw["albaranes"][0]["contexto_fila"]["elementos_contexto_ids"].append("s_dos")
    salida = normalizar_candidato(raw)
    assert len(salida.albaranes) == 1 and salida.albaranes[0].sentido is None


def test_fallback_rechaza_cargo_abono_contradictorios():
    raw = _candidato()
    raw["estructuras_documentales"][0]["elementos"].append({
        "id": "s_abono", "tipo": "SECCION", "literal": "ABONOS", "pagina": 1,
        "span_pagina": {"inicio": 20, "fin": 26}, "valor_sentido": "ABONO",
    })
    raw["albaranes"][0]["contexto_fila"]["elementos_contexto_ids"].append("s_abono")
    salida = normalizar_candidato(raw)
    assert len(salida.albaranes) == 1 and salida.albaranes[0].sentido is None


@pytest.mark.parametrize("mutacion", ["otra_pagina", "discordante", "parecido", "no_seccion"])
def test_fallback_rechaza_seccion_no_demostrativa(mutacion):
    raw = _candidato()
    elemento = raw["estructuras_documentales"][0]["elementos"][0]
    if mutacion == "otra_pagina":
        elemento["pagina"] = 2
    elif mutacion == "discordante":
        elemento["valor_sentido"] = "ABONO"
    elif mutacion == "parecido":
        elemento["literal"] = "CARGOS NETOS"
    else:
        elemento["tipo"] = "COLUMNA"
    salida = normalizar_candidato(raw)
    assert len(salida.albaranes) == 1 and salida.albaranes[0].sentido is None


def test_fallback_rechaza_externo_inexistente_doble_o_resto_fuera_de_tabla():
    inexistente = _candidato(externo=True)
    inexistente["albaranes"][0]["contexto_fila"]["elemento_sentido_id"] = "no_existe"
    assert _aceptados(inexistente) == 0

    doble = _candidato(externo=True)
    otra = _estructura("otra")
    doble["estructuras_documentales"].append(otra)
    doble["albaranes"][0]["contexto_fila"]["elementos_contexto_ids"].append("s_otra")
    assert _aceptados(doble) == 0

    fuera = _candidato(externo=True)
    fuera["albaranes"][0]["contexto_fila"]["elementos_contexto_ids"].append("h_seccion")
    assert _aceptados(fuera) == 0


def test_evidencia_directa_valida_con_referencia_externa_no_activa_fallback():
    assert _aceptados(_candidato(externo=True, directo=True)) == 0


def test_sentido_no_salva_campo_critico_no_demostrado():
    raw = _candidato(externo=True)
    raw["albaranes"][0]["numero"] = {"valor": "A-1", "literal": "NO VISIBLE", "span_fila": None}
    assert _aceptados(raw) == 0


def _vd(valor, pagina=1, *, literal=None, ubicacion=None, evidencias=None):
    literal = str(valor.literal if hasattr(valor, "literal") else valor) if literal is None else literal
    ev = evidencias or [Evidencia(pagina=pagina, literal=literal, ubicacion=ubicacion)]
    return ValorDocumentado(valor=valor, literal=literal, evidencia=ev)


def _factura(*, factura_id="f", numero="F-1", proveedor="PROVEEDOR", vencimientos=(), identidad_demostrada=False):
    tercero = Tercero(nombre=_vd(proveedor)) if proveedor is not None else None
    return FacturaNormalizada(
        factura_id=factura_id, naturaleza_principal=NaturalezaPrincipal.MERCANCIA,
        estado_validacion=EstadoValidacion.VALIDADA, requiere_conciliacion_albaranes=True,
        pagina_inicio=1, pagina_fin=5, proveedor=tercero,
        numero_factura=_vd(numero) if numero is not None else None,
        fecha_factura=_vd(FechaDocumental(literal="01-08-2026", iso=date(2026, 8, 1))) if identidad_demostrada else None,
        totales=Totales(total=_vd(Decimal("100.00")) if identidad_demostrada else None),
        vencimientos=list(vencimientos),
        validaciones=[ResultadoValidacion(codigo="T", resultado=ResultadoControl.OK, descripcion="ok", regla_version="v2")],
    )


def _vencimiento(pagina, *, importe=None, medio=None, ubicacion=None, evidencia_literal="06-10-2026"):
    fecha = FechaDocumental(literal="06-10-2026", iso=date(2026, 10, 6))
    return Vencimiento(
        orden=pagina, fecha=_vd(fecha, pagina, literal=evidencia_literal, ubicacion=ubicacion),
        importe=_vd(Decimal(importe), pagina) if importe is not None else None,
        medio_pago=_vd(medio, pagina) if medio is not None else None,
    )


def test_cinco_vencimientos_misma_fuente_factura_fusionan_cinco_provenances():
    facturas = [_factura(factura_id=f"f{i}", vencimientos=[_vencimiento(i)], identidad_demostrada=True) for i in range(1, 6)]
    salida = consolidar_lecturas(facturas[:1], facturas[1:], source_sha="sha-documento")
    assert len(salida) == 1 and len(salida[0].vencimientos) == 1
    assert [e.pagina for e in salida[0].vencimientos[0].fecha.evidencia] == [1, 2, 3, 4, 5]


def test_source_sha_ausente_no_aplica_dedup_semantica():
    facturas = [_factura(factura_id=f"f{i}", vencimientos=[_vencimiento(i)]) for i in range(1, 6)]
    assert len(consolidar_lecturas(facturas[:1], facturas[1:])[0].vencimientos) == 5


def test_fuentes_distintas_se_procesan_sin_cruzar_provenance():
    a = consolidar_lecturas([_factura(vencimientos=[_vencimiento(1)])], [], source_sha="sha-a")[0]
    b = consolidar_lecturas([_factura(vencimientos=[_vencimiento(2)])], [], source_sha="sha-b")[0]
    assert [e.pagina for e in a.vencimientos[0].fecha.evidencia] == [1]
    assert [e.pagina for e in b.vencimientos[0].fecha.evidencia] == [2]


def test_multifactura_identidad_distinta_o_ambigua_no_deduplica():
    distinta = consolidar_lecturas(
        [_factura(vencimientos=[_vencimiento(1)])],
        [_factura(factura_id="otra", numero="F-2", vencimientos=[_vencimiento(2)])], source_sha="sha",
    )
    assert len(distinta) == 2
    ambiguas = [_factura(factura_id="a", proveedor=None), _factura(factura_id="b", proveedor=None)]
    salida = consolidar_lecturas(ambiguas, [_factura(factura_id="c", vencimientos=[_vencimiento(1)])], source_sha="sha")
    assert len(salida) == 3


@pytest.mark.parametrize("a,b", [
    (_vencimiento(1, importe="10"), _vencimiento(2, importe="11")),
    (_vencimiento(1, importe="10", medio="GIRO"), _vencimiento(2, importe="10", medio="TRANSFERENCIA")),
])
def test_atributos_incompatibles_no_deduplican(a, b):
    salida = consolidar_lecturas([_factura(vencimientos=[a], identidad_demostrada=True)], [_factura(factura_id="b", vencimientos=[b], identidad_demostrada=True)], source_sha="sha")
    assert len(salida[0].vencimientos) == 2


def test_dos_ocurrencias_reales_misma_pagina_estructura_no_deduplican():
    u1 = {"estructura_id": "tabla", "posicion": {"fila": 1}}
    u2 = {"estructura_id": "tabla", "posicion": {"fila": 2}}
    salida = consolidar_lecturas(
        [_factura(vencimientos=[_vencimiento(1, ubicacion=u1)], identidad_demostrada=True)],
        [_factura(factura_id="b", vencimientos=[_vencimiento(1, ubicacion=u2)], identidad_demostrada=True)], source_sha="sha",
    )
    assert len(salida[0].vencimientos) == 2


def test_evidencia_contradictoria_no_deduplica():
    salida = consolidar_lecturas(
        [_factura(vencimientos=[_vencimiento(1)], identidad_demostrada=True)],
        [_factura(factura_id="b", vencimientos=[_vencimiento(2, evidencia_literal="07-10-2026")], identidad_demostrada=True)], source_sha="sha",
    )
    assert len(salida[0].vencimientos) == 2


def test_duplicados_exactos_fusionan_evidencias_unicas_sin_repetir():
    repetida = Evidencia(pagina=1, literal="06-10-2026")
    primero = _vencimiento(1)
    primero = primero.model_copy(update={"fecha": primero.fecha.model_copy(update={"evidencia": [repetida, Evidencia(pagina=2, literal="06-10-2026")]})})
    segundo = _vencimiento(1)
    segundo = segundo.model_copy(update={"fecha": segundo.fecha.model_copy(update={"evidencia": [repetida, Evidencia(pagina=3, literal="06-10-2026")]})})
    salida = consolidar_lecturas([_factura(vencimientos=[primero], identidad_demostrada=True)], [_factura(factura_id="b", vencimientos=[segundo], identidad_demostrada=True)], source_sha="sha")
    assert [e.pagina for e in salida[0].vencimientos[0].fecha.evidencia] == [1, 2, 3]


RAIZ_REPLAY_V23 = (
    Path(__file__).resolve().parents[3]
    / "pruebas/facturas/resultados/normalizador_v2_contrato_evidencia_v23/microprueba_paginas_completas_luna2"
)
RUTAS_REPLAY_V23 = tuple(RAIZ_REPLAY_V23 / slot / "candidato_validado.json" for slot in ("p4", "p5"))


@pytest.mark.skipif(
    not all(ruta.exists() for ruta in RUTAS_REPLAY_V23),
    reason="corpus externo V2.3 por paginas no disponible",
)
def test_replay_congelado_recupera_trece_y_rechaza_referencia_injustificada():
    raiz = RAIZ_REPLAY_V23
    resultados = {}
    for slot in ("p4", "p5"):
        raw = json.loads((raiz / slot / "candidato_validado.json").read_text(encoding="utf-8"))["facturas"][0]
        resultados[slot] = [item.numero.valor for item in normalizar_candidato(raw).albaranes]
    assert len(resultados["p4"]) == 50
    assert len(resultados["p5"]) == 10
    assert "08Z34777" not in resultados["p5"]
