from __future__ import annotations

import copy
import json
from decimal import Decimal

import pytest

from src.facturas.normalizador_v2.adaptador_luna import ErrorSalidaLuna, _validar_schema
from src.facturas.normalizador_v2.contrato_luna import schema_luna_v23
from src.facturas.normalizador_v2.modelos import OrigenDerivacion, Sentido
from src.facturas.normalizador_v2.normalizador_general import normalizar_candidato
from src.facturas.normalizador_v2.pipeline import _remapear_candidato


def span(texto: str, literal: str, desde: int = 0) -> dict:
    inicio = texto.index(literal, desde)
    return {"inicio": inicio, "fin": inicio + len(literal)}


def campo(valor, literal: str, fila: str) -> dict:
    return {"valor": valor, "literal": literal, "span_fila": span(fila, literal)}

def campo_cabecera(valor, literal: str, contexto_literal: str, pagina: int = 1) -> dict:
    return {
        "valor": valor,
        "literal": literal,
        "pagina": pagina,
        "contexto_literal": contexto_literal,
        "span_contexto": span(contexto_literal, literal),
    }


def estructura(eid="e1", sentido="CARGO", literal=None, *, paginas=None, tipo="SECCION") -> dict:
    literal = literal or ("CARGOS" if sentido == "CARGO" else "ABONOS")
    return {
        "id": eid, "tipo": "TABLA", "paginas": paginas or [1],
        "elementos": [{
            "id": f"m_{eid}", "tipo": tipo, "literal": literal, "pagina": (paginas or [1])[0],
            "span_pagina": {"inicio": 10, "fin": 10 + len(literal)}, "valor_sentido": sentido,
        }, {
            "id": f"h_{eid}", "tipo": "CABECERA", "literal": "FECHA | NUMERO | TOTAL",
            "pagina": (paginas or [1])[0], "span_pagina": {"inicio": 30, "fin": 52}, "valor_sentido": None,
        }],
    }


def contexto(fila: str, *, eid="e1", pagina=1, numero_fila=1, zona="izquierda", sentido=True) -> dict:
    return {
        "estructura_id": eid, "elementos_contexto_ids": [f"m_{eid}", f"h_{eid}"],
        "elemento_sentido_id": f"m_{eid}" if sentido else None,
        "pagina": pagina, "literal_fila": fila,
        "span_pagina": {"inicio": numero_fila * 100, "fin": numero_fila * 100 + len(fila)},
        "posicion": {"segmento": pagina, "fila": numero_fila, "zona": zona},
    }


def albaran(numero="A-1", *, eid="e1", pagina=1, orden=1, numero_fila=1, sentido="CARGO", estructural=True, linea=None, zona="izquierda") -> dict:
    linea = linea or f"01-08-2026 NORMAL {numero} 10,00 12,10"
    literal_sentido = "CARGOS" if sentido == "CARGO" else "ABONOS"
    evidencia_sentido = {"valor": sentido, "literal": literal_sentido, "span_fila": None}
    if not estructural:
        linea = f"{linea} {sentido}"
        evidencia_sentido = campo(sentido, sentido, linea)
    return {
        "orden": orden, "contexto_fila": contexto(linea, eid=eid, pagina=pagina, numero_fila=numero_fila, zona=zona, sentido=estructural),
        "fecha": campo("01-08-2026", "01-08-2026", linea), "numero": campo(numero, numero, linea),
        "sentido": evidencia_sentido, "tipo_pedido": campo("NORMAL", "NORMAL", linea),
        "importe_base": campo(10, "10,00", linea), "importe_total": campo(Decimal("12.1"), "12,10", linea),
    }


def candidato(*, estructuras=None, albaranes=None, impuestos=None, movimientos=None, paginas=(1, 5)) -> dict:
    return {
        "tipo_documento": None, "naturaleza_principal": "MERCANCIA", "requiere_conciliacion_albaranes": True,
        "pagina_inicio": paginas[0], "pagina_fin": paginas[1], "proveedor": None, "numero_factura": None,
        "fecha_factura": None, "base_imponible_total": None, "iva_total": None,
        "recargo_equivalencia_total": None, "otros_total": None, "importe_total": None, "moneda": None,
        "vencimientos": [], "impuestos": impuestos or [], "albaranes": albaranes or [],
        "movimientos_comerciales": movimientos or [], "destinatario": None, "forma_pago": None,
        "referencias_documentales": [], "discrepancias_documentales": [], "evidencias": [],
        "estructuras_documentales": estructuras if estructuras is not None else [estructura()],
    }


@pytest.mark.parametrize("sentido", ["CARGO", "ABONO"])
def test_seccion_explicita_determina_sentido(sentido):
    e = estructura(sentido=sentido, tipo="SECCION")
    fila = albaran(sentido=sentido)
    salida = normalizar_candidato(candidato(estructuras=[e], albaranes=[fila]))
    assert salida.albaranes[0].tipo_movimiento == Sentido(sentido)
    assert salida.derivaciones[0].regla_id == "sentido.estructura_documental_inequivoca.v1"


def test_literal_explicito_en_fila_sigue_siendo_valido_y_trazado():
    salida = normalizar_candidato(candidato(albaranes=[albaran(estructural=False)]))
    assert salida.albaranes[0].tipo_movimiento == Sentido.CARGO
    assert salida.derivaciones[0].origen == OrigenDerivacion.LITERAL_EXPLICITO


def test_cabecera_compartida_por_101_filas_no_duplica_texto():
    filas = [albaran(f"A-{i:03d}", orden=i + 1, numero_fila=i + 1) for i in range(101)]
    raw = candidato(albaranes=filas)
    assert len(normalizar_candidato(raw).albaranes) == 101
    assert json.dumps(raw, ensure_ascii=False, default=str).count("FECHA | NUMERO | TOTAL") == 1


def test_signo_sin_semantica_y_cabecera_ambigua_se_rechazan():
    fila = albaran(sentido="ABONO")
    fila["contexto_fila"]["literal_fila"] = "01-08-2026 NORMAL A-1 10,00-"
    fila["numero"] = campo("A-1", "A-1", fila["contexto_fila"]["literal_fila"])
    fila["fecha"] = campo("01-08-2026", "01-08-2026", fila["contexto_fila"]["literal_fila"])
    fila["tipo_pedido"] = campo("NORMAL", "NORMAL", fila["contexto_fila"]["literal_fila"])
    fila["importe_base"] = fila["importe_total"] = None
    sin_semantica = normalizar_candidato(candidato(estructuras=[], albaranes=[fila]))
    assert sin_semantica.albaranes == []  # faltan tambien referencias estructurales de identidad
    ambigua = estructura(literal="CARGOS / ABONOS")
    con_cabecera_ambigua = normalizar_candidato(candidato(estructuras=[ambigua], albaranes=[albaran()]))
    assert len(con_cabecera_ambigua.albaranes) == 1 and con_cabecera_ambigua.albaranes[0].sentido is None


def test_dos_secciones_misma_pagina_y_tabla_multipagina():
    cargo = estructura("e1", "CARGO", paginas=[1, 2])
    abono = estructura("e2", "ABONO", paginas=[1, 2])
    for e in (cargo, abono):
        e["elementos"][0]["pagina"] = 2
    filas = [albaran("C-1", eid="e1", pagina=2, sentido="CARGO", zona="izquierda"),
             albaran("A-1", eid="e2", pagina=2, sentido="ABONO", zona="derecha")]
    salida = normalizar_candidato(candidato(estructuras=[cargo, abono], albaranes=filas))
    assert [x.tipo_movimiento for x in salida.albaranes] == [Sentido.CARGO, Sentido.ABONO]


def test_remapeo_splitter_incluye_estructura_elemento_y_fila():
    raw = candidato(estructuras=[estructura(paginas=[2])], albaranes=[albaran(pagina=2)], paginas=(1, 2))
    remapeado = _remapear_candidato(raw, (4, 5))
    assert remapeado["estructuras_documentales"][0]["paginas"] == [5]
    assert remapeado["albaranes"][0]["contexto_fila"]["pagina"] == 5
    assert normalizar_candidato(remapeado).albaranes[0].numero.evidencia[0].pagina == 5


def test_misma_linea_con_movimiento_e_impuesto_usa_spans_individuales():
    linea = "SERVICIO 10,00 IVA 21,00"
    ctx = contexto(linea, sentido=False)
    mov = {"orden": 1, "contexto_fila": copy.deepcopy(ctx), "tipo": campo("SERVICIO", "SERVICIO", linea),
           "descripcion_literal": campo("SERVICIO", "SERVICIO", linea), "sentido": {"valor": "CARGO", "literal": "CARGOS", "span_fila": None},
           "base": campo(10, "10,00", linea), "iva": None, "recargo_equivalencia": None, "importe": None}
    mov["contexto_fila"]["elemento_sentido_id"] = "m_e1"
    imp = {"orden": 1, "contexto_fila": copy.deepcopy(ctx), "descripcion_literal": campo("IVA", "IVA", linea),
           "base": campo(21, "21,00", linea), "tipo_iva": None, "cuota_iva": None,
           "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": None, "total_tramo": None}
    salida = normalizar_candidato(candidato(movimientos=[mov], impuestos=[imp]))
    assert len(salida.movimientos_comerciales) == len(salida.impuestos) == 1


def test_referencias_inexistentes_duplicadas_y_cruzadas_entre_facturas():
    inexistente = candidato(estructuras=[], albaranes=[albaran()])
    assert normalizar_candidato(inexistente).albaranes == []
    duplicada = candidato(estructuras=[estructura(), estructura()], albaranes=[albaran()])
    assert normalizar_candidato(duplicada).albaranes == []
    otra_factura = candidato(estructuras=[estructura("e2")], albaranes=[albaran(eid="e1")])
    assert normalizar_candidato(otra_factura).albaranes == []


def test_elemento_sentido_inexistente_se_rechaza():
    fila = albaran()
    fila["contexto_fila"]["elemento_sentido_id"] = "id_inexistente"
    salida = normalizar_candidato(candidato(albaranes=[fila]))
    assert salida.albaranes == []


def test_fallback_sentido_rechaza_dos_fuentes_semanticas_posibles():
    e = estructura()
    e["elementos"].append({
        "id": "m_abono", "tipo": "SECCION", "literal": "ABONOS", "pagina": 1,
        "span_pagina": {"inicio": 60, "fin": 66}, "valor_sentido": "ABONO",
    })
    fila = albaran()
    fila["contexto_fila"]["elemento_sentido_id"] = "id_inexistente"
    fila["contexto_fila"]["elementos_contexto_ids"].append("m_abono")
    assert normalizar_candidato(candidato(estructuras=[e], albaranes=[fila])).albaranes == []


@pytest.mark.parametrize("mutacion", ["duplicada", "cruzada"])
def test_fallback_sentido_rechaza_referencia_contexto_duplicada_o_cruzada(mutacion):
    fila = albaran()
    fila["contexto_fila"]["elemento_sentido_id"] = "id_inexistente"
    estructuras = [estructura()]
    if mutacion == "duplicada":
        fila["contexto_fila"]["elementos_contexto_ids"].append("m_e1")
    else:
        estructuras.append(estructura("e2"))
        fila["contexto_fila"]["elementos_contexto_ids"].append("m_e2")
    assert normalizar_candidato(candidato(estructuras=estructuras, albaranes=[fila])).albaranes == []


def test_span_ausente_literal_unico_se_infiere_y_repetido_se_rechaza():
    unico = albaran()
    unico["numero"]["span_fila"] = None
    salida = normalizar_candidato(candidato(albaranes=[unico]))
    assert "span_fila_inferido" in salida.albaranes[0].numero.evidencia[0].ubicacion

    repetido = albaran(linea="01-08-2026 NORMAL A-1 A-1 10,00 12,10")
    repetido["numero"]["span_fila"] = None
    assert normalizar_candidato(candidato(albaranes=[repetido])).albaranes == []


def test_span_incorrecto_literal_unico_se_repara_y_ambiguo_se_rechaza():
    unico = albaran()
    unico["numero"]["span_fila"] = {"inicio": 0, "fin": 3}
    evidencia = normalizar_candidato(candidato(albaranes=[unico])).albaranes[0].numero.evidencia[0]
    assert evidencia.ubicacion["span_fila_inferido"] == span(unico["contexto_fila"]["literal_fila"], "A-1")

    ambiguo = albaran(linea="01-08-2026 NORMAL A-1 A-1 10,00 12,10")
    ambiguo["numero"]["span_fila"] = {"inicio": 0, "fin": 3}
    assert normalizar_candidato(candidato(albaranes=[ambiguo])).albaranes == []


def test_mismo_span_incompatible_y_filas_indistinguibles_se_rechazan():
    uno, dos = albaran("A-1"), albaran("A-1")
    dos["importe_base"]["valor"] = 20
    assert normalizar_candidato(candidato(albaranes=[uno, dos])).albaranes == []


def test_cabecera_v23_numero_factura_documentado():
    raw = candidato()
    raw["numero_factura"] = campo_cabecera(
        "08009277",
        "08009277",
        "FACTURA NUMERO 08009277",
    )

    _validar_schema({"facturas": [raw]}, schema_luna_v23())

    salida = normalizar_candidato(raw)

    assert salida.numero_factura is not None
    assert salida.numero_factura.valor == "08009277"
    assert salida.numero_factura.literal == "08009277"
    assert salida.numero_factura.evidencia[0].pagina == 1
    assert salida.numero_factura.evidencia[0].ubicacion["span_contexto"] == {
        "inicio": 15,
        "fin": 23,
    }


@pytest.mark.parametrize("caso", [
    "extra", "faltante", "pagina_fuera", "contexto_vacio", "span_fuera",
    "slice_distinto", "literal_no_demuestra", "ambiguo",
])
def test_cabecera_v23_rechaza_forma_o_evidencia_no_inequivoca(caso):
    raw = candidato()
    contexto_literal = "FACTURA NUMERO 08009277"
    cabecera = campo_cabecera("08009277", "08009277", contexto_literal)
    if caso == "extra":
        cabecera["extra"] = True
    elif caso == "faltante":
        cabecera.pop("span_contexto")
    elif caso == "pagina_fuera":
        cabecera["pagina"] = 6
    elif caso == "contexto_vacio":
        cabecera["contexto_literal"] = ""
    elif caso == "span_fuera":
        cabecera["span_contexto"] = {"inicio": 15, "fin": 99}
    elif caso == "slice_distinto":
        cabecera["span_contexto"] = {"inicio": 0, "fin": 8}
    elif caso == "literal_no_demuestra":
        cabecera["valor"] = "OTRA"
    elif caso == "ambiguo":
        cabecera["contexto_literal"] = "08009277 / 08009277"
        cabecera["span_contexto"] = {"inicio": 0, "fin": 8}
    raw["numero_factura"] = cabecera
    assert normalizar_candidato(raw).numero_factura is None


def test_clasificacion_no_contamina_span_descripcion_pero_exige_regla_propia():
    linea = "RAPPEL GenerAH 10,00"
    mov = {
        "orden": 1, "contexto_fila": contexto(linea),
        "tipo": {"valor": "RAPPEL", "literal": "RAPPEL GenerAH", "span_fila": span(linea, "RAPPEL GenerAH")},
        "descripcion_literal": campo("RAPPEL GenerAH", "RAPPEL GenerAH", linea),
        "sentido": {"valor": "ABONO", "literal": "ABONOS", "span_fila": None},
        "base": None, "iva": None, "recargo_equivalencia": None, "importe": None,
    }
    e = estructura(sentido="ABONO")
    salida = normalizar_candidato(candidato(estructuras=[e], movimientos=[mov]))
    assert len(salida.movimientos_comerciales) == 1

    sin_regla = copy.deepcopy(mov)
    sin_regla["tipo"] = {"valor": "OTRO", "literal": "RAPPEL GenerAH", "span_fila": span(linea, "RAPPEL GenerAH")}
    conservado = normalizar_candidato(candidato(estructuras=[e], movimientos=[sin_regla])).movimientos_comerciales
    assert len(conservado) == 1
    assert conservado[0].tipo == "OTRO" and conservado[0].sentido == Sentido.ABONO
    assert conservado[0].descripcion_literal.valor == "RAPPEL GenerAH"


def test_mismo_span_para_valores_documentales_incompatibles_sigue_rechazado():
    fila = albaran()
    fila["importe_base"]["span_fila"] = fila["importe_total"]["span_fila"]
    fila["importe_base"]["literal"] = fila["importe_total"]["literal"]
    salida = normalizar_candidato(candidato(albaranes=[fila]))
    assert salida.albaranes[0].importe_base is None
    assert salida.albaranes[0].importe_total is None


def test_schema_strict_roundtrip_y_traza_con_fuente_estructural_y_fila():
    raw = candidato(albaranes=[albaran()])
    schema = schema_luna_v23()
    _validar_schema({"facturas": [raw]}, schema)
    assert json.loads(json.dumps(schema)) == schema
    extra = copy.deepcopy(raw)
    extra["albaranes"][0]["contexto_fila"]["extra"] = True
    with pytest.raises(ErrorSalidaLuna):
        _validar_schema({"facturas": [extra]}, schema)
    salida = normalizar_candidato(raw)
    traza = salida.derivaciones[0]
    assert len(traza.fuentes) == 2
    assert {"elemento_id", "span_pagina"} <= set(traza.fuentes[0].evidencias[0].ubicacion)
    assert "posicion" in traza.fuentes[1].evidencias[0].ubicacion
    assert json.loads(salida.json_estable())["albaranes"][0]["numero"]["valor"] == "A-1"


def test_compatibilidad_v22_preservada():
    fila = {
        "orden": 1, "localizacion": {"pagina": 1, "contexto_literal": "V22 CARGO", "ocurrencia_en_pagina": 1},
        "fecha": None, "numero": {"valor": "V22", "literal": "V22"},
        "sentido": {"valor": "CARGO", "literal": "CARGO"}, "tipo_pedido": None,
        "importe_base": None, "importe_total": None,
    }
    raw = candidato(estructuras=None, albaranes=[fila])
    raw.pop("estructuras_documentales")
    assert normalizar_candidato(raw).albaranes[0].numero.valor == "V22"
