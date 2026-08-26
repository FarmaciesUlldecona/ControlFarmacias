from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.facturas.normalizador_v2.modelos import OrigenDerivacion, Sentido, TipoMovimiento
from src.facturas.normalizador_v2.normalizador_general import normalizar_candidato

def campo(valor, literal=None):
    return {"valor": valor, "literal": str(valor) if literal is None else literal}


def localizacion(contexto, *, pagina=1, ocurrencia=1):
    return {"pagina": pagina, "contexto_literal": contexto, "ocurrencia_en_pagina": ocurrencia}


def candidato(**cambios):
    raw = {
        "tipo_documento": None, "naturaleza_principal": "MERCANCIA",
        "requiere_conciliacion_albaranes": True, "pagina_inicio": 1, "pagina_fin": 5,
        "proveedor": None, "numero_factura": None, "fecha_factura": None,
        "base_imponible_total": None, "iva_total": None, "recargo_equivalencia_total": None,
        "otros_total": None, "importe_total": None, "moneda": None,
        "vencimientos": [], "impuestos": [], "albaranes": [], "movimientos_comerciales": [],
        "destinatario": None, "forma_pago": None, "referencias_documentales": [],
        "discrepancias_documentales": [], "evidencias": [],
    }
    raw.update(cambios)
    return raw


def albaran(numero, orden=1, *, ocurrencia=1):
    contexto = f"{numero} CARGO"
    return {
        "orden": orden, "localizacion": localizacion(contexto, ocurrencia=ocurrencia),
        "fecha": None, "numero": campo(numero), "sentido": campo("CARGO"),
        "tipo_pedido": None, "importe_base": None, "importe_total": None,
    }


def movimiento(descripcion: str, tipo: str, sentido: str, contexto: str | None = None) -> dict:
    contexto = contexto or f"{descripcion} 10,00 12,10"
    return {
        "orden": 1, "localizacion": localizacion(contexto),
        "tipo": campo(tipo, descripcion), "descripcion_literal": campo(descripcion),
        "sentido": campo(sentido, "NO LITERAL"), "base": campo(10, "10,00"),
        "iva": None, "recargo_equivalencia": None, "importe": campo(12.1, "12,10"),
    }


def impuesto(contexto: str) -> dict:
    return {
        "orden": 1, "localizacion": localizacion(contexto),
        "descripcion_literal": campo("SERVICIO BASICO"), "base": campo(10, "10,00"),
        "tipo_iva": None, "cuota_iva": None, "tipo_recargo_equivalencia": None,
        "cuota_recargo_equivalencia": None, "total_tramo": campo(12.1, "12,10"),
    }


def test_descripcion_clasifica_concepto_pero_no_inventa_sentido():
    raw = candidato(movimientos_comerciales=[movimiento("SERVICIO BASICO", "SERVICIO", "CARGO")])
    salida = normalizar_candidato(raw)
    assert salida.movimientos_comerciales[0].sentido is None
    assert salida.movimientos_comerciales[0].tipo == TipoMovimiento.SERVICIO
    assert not any(traza.campo.endswith(".sentido") for traza in salida.derivaciones)
    assert any(i.codigo == "SENTIDO_NO_DOCUMENTADO" for i in salida.incidencias)


def test_descripcion_ambigua_o_sentido_no_documentado_preserva_movimiento():
    ambiguo = movimiento("SERVICIO BASICO RAPPEL GenerAH", "SERVICIO", "CARGO")
    incompatible = movimiento("SERVICIO BASICO", "SERVICIO", "ABONO")
    salidas = [normalizar_candidato(candidato(movimientos_comerciales=[item])) for item in (ambiguo, incompatible)]
    assert all(len(s.movimientos_comerciales) == 1 for s in salidas)
    assert all(s.movimientos_comerciales[0].sentido is None for s in salidas)
    assert all(s.movimientos_comerciales[0].descripcion_literal.valor for s in salidas)


def test_una_linea_soporta_dos_hechos_con_literales_distintos():
    uno, dos = albaran("A-1", 1), albaran("A-2", 2)
    contexto = "A-1 A-2 CARGO"
    uno["localizacion"] = localizacion(contexto)
    dos["localizacion"] = localizacion(contexto)
    assert [x.numero.valor for x in normalizar_candidato(candidato(albaranes=[uno, dos])).albaranes] == ["A-1", "A-2"]


def test_mismo_span_no_justifica_valores_incompatibles():
    contexto = "SERVICIO BASICO 10,00 20,00"
    mov = movimiento("SERVICIO BASICO", "SERVICIO", "CARGO", contexto)
    imp = impuesto(contexto)
    imp["base"] = campo(20, "10,00 20,00")
    mov["base"] = campo(10, "10,00 20,00")
    salida = normalizar_candidato(candidato(movimientos_comerciales=[mov], impuestos=[imp]))
    assert salida.movimientos_comerciales[0].base is None
    assert salida.impuestos[0].base is None


def test_filas_iguales_se_distinguen_por_ocurrencia():
    uno, dos = albaran("MISMO", 1, ocurrencia=1), albaran("MISMO", 2, ocurrencia=2)
    assert len(normalizar_candidato(candidato(albaranes=[uno, dos])).albaranes) == 2
    indistinguibles = copy.deepcopy([uno, uno])
    assert normalizar_candidato(candidato(albaranes=indistinguibles)).albaranes == []


def test_movimiento_e_impuesto_comparten_linea_sin_compartir_hecho():
    contexto = "SERVICIO BASICO 10,00 12,10"
    salida = normalizar_candidato(candidato(
        movimientos_comerciales=[movimiento("SERVICIO BASICO", "SERVICIO", "CARGO", contexto)],
        impuestos=[impuesto(contexto)],
    ))
    assert len(salida.movimientos_comerciales) == len(salida.impuestos) == 1


def test_no_deriva_por_proveedor_contexto_general_o_signo_sin_regla():
    fila = albaran("A-NEG")
    fila["localizacion"]["contexto_literal"] = "A-NEG 10,00-"
    fila["sentido"] = campo("ABONO", "10,00-")
    fila["importe_total"] = campo(-10, "10,00-")
    raw = candidato(albaranes=[fila], proveedor={"nombre": "ALLIANCE", "nif": None, "direccion": None})
    salida = normalizar_candidato(raw)
    assert len(salida.albaranes) == 1 and salida.albaranes[0].sentido is None
    assert any(i.codigo == "SENTIDO_NO_DOCUMENTADO" for i in salida.incidencias)


def test_literal_explicito_tiene_precedencia_y_traza_origen_literal():
    fila = albaran("A-1")
    fila["sentido"]["literal"] = "CABECERA"
    salida = normalizar_candidato(candidato(albaranes=[fila]))
    assert salida.albaranes[0].tipo_movimiento == Sentido.CARGO
    assert salida.derivaciones[0].origen == OrigenDerivacion.LITERAL_EXPLICITO


RUTA_REPLAY_V22 = (
    Path(__file__).resolve().parents[3]
    / "pruebas/facturas/resultados/normalizador_v2_contrato_evidencia_v22/microprueba_real/04_candidato_v22_validado.json"
)


@pytest.mark.skipif(not RUTA_REPLAY_V22.exists(), reason="corpus externo V2.2 no disponible")
def test_replay_candidato_v22_congelado_sin_gold():
    ruta = RUTA_REPLAY_V22
    congelado = json.loads(ruta.read_text(encoding="utf-8"))["facturas"][0]
    salida = normalizar_candidato(congelado)
    assert (len(salida.albaranes), len(salida.movimientos_comerciales), len(salida.impuestos), len(salida.vencimientos)) == (165, 4, 9, 1)
    assert sum(fila.sentido is None for fila in salida.albaranes) == 162
    assert [fila.orden for fila in salida.albaranes if fila.sentido is not None] == [161, 163, 164]
    assert all(traza.fuentes and all(f.evidencias for f in traza.fuentes) for traza in salida.derivaciones)
    assert all(
        fuente.campo.split("[", 1)[0] == traza.campo.split("[", 1)[0]
        for traza in salida.derivaciones for fuente in traza.fuentes
    )
