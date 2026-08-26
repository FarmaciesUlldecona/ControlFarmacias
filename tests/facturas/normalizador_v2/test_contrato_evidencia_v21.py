from __future__ import annotations

import copy
import json
from decimal import Decimal

import pytest

from src.facturas.normalizador_v2.adaptador_luna import ErrorSalidaLuna, _validar_schema
from src.facturas.normalizador_v2.contrato_luna import schema_luna_v2, schema_luna_v21
from src.facturas.normalizador_v2.multifactura import consolidar_facturas
from src.facturas.normalizador_v2.normalizador_general import normalizar_candidato
from src.facturas.normalizador_v2.pipeline import _remapear_candidato


def evidencia(campo, valor, *, pagina=1, literal=None, ocurrencia=1, contexto=None):
    literal = str(valor) if literal is None else literal
    return {
        "campo": campo,
        "valor": valor,
        "pagina": pagina,
        "literal": literal,
        "localizador": {
            "contexto_literal": contexto,
            "ocurrencia_en_pagina": ocurrencia,
        },
    }


def candidato(**colecciones):
    salida = {
        "tipo_documento": None,
        "naturaleza_principal": "MERCANCIA",
        "requiere_conciliacion_albaranes": True,
        "pagina_inicio": 1,
        "pagina_fin": 3,
        "proveedor": None,
        "numero_factura": None,
        "fecha_factura": None,
        "base_imponible_total": None,
        "iva_total": None,
        "recargo_equivalencia_total": None,
        "otros_total": None,
        "importe_total": None,
        "moneda": None,
        "vencimientos": [],
        "impuestos": [],
        "albaranes": [],
        "movimientos_comerciales": [],
        "destinatario": None,
        "forma_pago": None,
        "referencias_documentales": [],
        "discrepancias_documentales": [],
        "evidencias": [],
    }
    salida.update(colecciones)
    return salida


def albaran(numero, orden=1):
    return {
        "orden": orden,
        "fecha": None,
        "numero": numero,
        "sentido": "CARGO",
        "tipo_pedido": None,
        "importe_base": None,
        "importe_total": None,
    }


def test_albaran_individual_y_cien_filas_con_ruta_indexada():
    filas = [albaran(f"A-{i:03d}", i + 1) for i in range(101)]
    raw = candidato(albaranes=filas)
    raw["evidencias"] = [
        evidencia(f"albaranes[{i}].numero", fila["numero"], pagina=1 + i // 50)
        for i, fila in enumerate(filas)
    ]
    salida = normalizar_candidato(raw)
    assert len(salida.albaranes) == 101
    assert salida.albaranes[-1].numero.valor == "A-100"


def test_literales_repetidos_misma_pagina_exigen_ocurrencias_distintas():
    raw = candidato(albaranes=[albaran("REPETIDO", 1), albaran("REPETIDO", 2)])
    raw["evidencias"] = [
        evidencia("albaranes[0].numero", "REPETIDO", ocurrencia=1),
        evidencia("albaranes[1].numero", "REPETIDO", ocurrencia=2),
    ]
    assert [a.orden for a in normalizar_candidato(raw).albaranes] == [1, 2]

    raw["evidencias"][1]["localizador"]["ocurrencia_en_pagina"] = 1
    assert normalizar_candidato(raw).albaranes == []


def test_misma_referencia_en_paginas_distintas_y_delivery_no_es_albaran():
    refs = [
        {"orden": 1, "tipo": "DELIVERY", "identificador": "REF-X", "descripcion_literal": None},
        {"orden": 2, "tipo": "DELIVERY", "identificador": "REF-X", "descripcion_literal": None},
    ]
    raw = candidato(referencias_documentales=refs)
    raw["evidencias"] = [
        evidencia("referencias_documentales[0].identificador", "REF-X", pagina=1),
        evidencia("referencias_documentales[1].identificador", "REF-X", pagina=2),
    ]
    salida = normalizar_candidato(raw)
    assert len(salida.referencias_documentales) == 2
    assert salida.albaranes == []


def test_movimiento_impuesto_vencimiento_y_referencia_con_evidencia_individual():
    raw = candidato(
        movimientos_comerciales=[{
            "orden": 1, "tipo": "RAPPEL", "descripcion_literal": "RAPPEL",
            "sentido": "ABONO", "base": 10, "iva": None,
            "recargo_equivalencia": None, "importe": None,
        }],
        impuestos=[{
            "orden": 1, "descripcion_literal": "IVA 21%", "base": Decimal("10"),
            "tipo_iva": Decimal("21"), "cuota_iva": None,
            "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": None,
            "total_tramo": None,
        }],
        vencimientos=[{"orden": 1, "fecha": "17/08/2026", "importe": None, "medio_pago": None}],
        referencias_documentales=[{
            "orden": 1, "tipo": "DELIVERY", "identificador": "D-1", "descripcion_literal": None,
        }],
    )
    raw["evidencias"] = [
        evidencia("movimientos_comerciales[0].descripcion_literal", "RAPPEL", contexto="Fila RAPPEL", ocurrencia=None),
        evidencia("movimientos_comerciales[0].base", 10, literal="Base 10", contexto="Fila Base 10", ocurrencia=None),
        evidencia("impuestos[0].descripcion_literal", "IVA 21%"),
        evidencia("impuestos[0].base", 10, literal="Base 10,00", pagina=2),
        evidencia("impuestos[0].tipo_iva", 21, literal="IVA 21%", pagina=2),
        evidencia("vencimientos[0].fecha", "17/08/2026", pagina=3),
        evidencia("referencias_documentales[0].identificador", "D-1", pagina=3),
    ]
    salida = normalizar_candidato(raw)
    assert len(salida.movimientos_comerciales) == 1
    assert len(salida.impuestos) == 1
    assert len(salida.vencimientos) == 1
    assert len(salida.referencias_documentales) == 1


@pytest.mark.parametrize("campo", ["albaranes", "pagina", "albaranes[1].numero"])
def test_evidencia_de_coleccion_generica_o_ruta_ambigua_se_rechaza(campo):
    raw = candidato(albaranes=[albaran("A-1")])
    raw["evidencias"] = [evidencia(campo, "A-1", literal="Pagina con albaranes A-1")]
    assert normalizar_candidato(raw).albaranes == []


def test_dos_evidencias_para_un_campo_y_valor_tipado_incorrecto_se_rechazan():
    raw = candidato(albaranes=[albaran("A-1")])
    prueba = evidencia("albaranes[0].numero", "A-1")
    raw["evidencias"] = [prueba, copy.deepcopy(prueba)]
    assert normalizar_candidato(raw).albaranes == []
    raw["evidencias"] = [evidencia("albaranes[0].numero", "OTRO", literal="A-1")]
    assert normalizar_candidato(raw).albaranes == []


def test_roundtrip_schema_v21_y_compatibilidad_schema_v2():
    v21 = schema_luna_v21()
    assert json.loads(json.dumps(v21)) == v21
    assert v21["additionalProperties"] is False
    evidencia_schema = v21["properties"]["facturas"]["items"]["properties"]["evidencias"]["items"]
    assert evidencia_schema["additionalProperties"] is False
    assert set(evidencia_schema["required"]) == set(evidencia_schema["properties"])
    nuevo = candidato(albaranes=[albaran("V21-1")])
    nuevo["evidencias"] = [evidencia("albaranes[0].numero", "V21-1")]
    _validar_schema({"facturas": [nuevo]}, v21)

    viejo = candidato(albaranes=[albaran("HIST-1")])
    viejo["evidencias"] = [{"campo": "albaranes[0].numero", "pagina": 1, "literal": "HIST-1"}]
    _validar_schema({"facturas": [viejo]}, schema_luna_v2())
    assert normalizar_candidato(viejo).albaranes[0].numero.valor == "HIST-1"


def test_schema_v21_rechaza_evidencia_v2_incompleta():
    viejo = candidato(albaranes=[albaran("HIST-1")])
    viejo["evidencias"] = [{"campo": "albaranes[0].numero", "pagina": 1, "literal": "HIST-1"}]
    with pytest.raises(ErrorSalidaLuna):
        _validar_schema({"facturas": [viejo]}, schema_luna_v21())


def test_segmentada_remapea_pagina_sin_perder_localizador_y_multifactura_aisla_consumo():
    uno = candidato(pagina_inicio=1, pagina_fin=1, albaranes=[albaran("S-1")])
    uno["evidencias"] = [evidencia("albaranes[0].numero", "S-1")]
    remapeado = _remapear_candidato(uno, (3,))
    assert remapeado["evidencias"][0]["pagina"] == 3
    assert normalizar_candidato(remapeado).albaranes[0].numero.evidencia[0].pagina == 3

    dos = copy.deepcopy(remapeado)
    dos["numero_factura"] = None
    facturas = [normalizar_candidato(remapeado), normalizar_candidato(dos)]
    # La no reutilizacion se limita correctamente a cada factura/lectura.
    assert all(len(f.albaranes) == 1 for f in facturas)
    assert len(consolidar_facturas(facturas).facturas) >= 1
