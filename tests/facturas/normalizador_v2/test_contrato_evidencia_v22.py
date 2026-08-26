from __future__ import annotations

import copy
import json

import pytest

from src.facturas.normalizador_v2.adaptador_luna import ErrorSalidaLuna, _validar_schema, calcular_coste
from src.facturas.normalizador_v2.contrato_luna import schema_luna_v2, schema_luna_v21, schema_luna_v22
from src.facturas.normalizador_v2.multifactura import consolidar_facturas
from src.facturas.normalizador_v2.normalizador_general import normalizar_candidato
from src.facturas.normalizador_v2.pipeline import _remapear_candidato


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


def albaran(numero, orden=1, *, pagina=1, ocurrencia=1):
    contexto = f"{numero} CARGO"
    return {
        "orden": orden, "localizacion": localizacion(contexto, pagina=pagina, ocurrencia=ocurrencia),
        "fecha": None, "numero": campo(numero), "sentido": campo("CARGO"), "tipo_pedido": None,
        "importe_base": None, "importe_total": None,
    }


def test_schema_estricto_hace_inseparable_valor_y_literal_y_null_no_exige_evidencia():
    schema = schema_luna_v22()
    valido = candidato(albaranes=[albaran("A-1")])
    _validar_schema({"facturas": [valido]}, schema)
    sin_literal = copy.deepcopy(valido)
    del sin_literal["albaranes"][0]["numero"]["literal"]
    with pytest.raises(ErrorSalidaLuna):
        _validar_schema({"facturas": [sin_literal]}, schema)
    escalar = copy.deepcopy(valido)
    escalar["albaranes"][0]["numero"] = "A-1"
    with pytest.raises(ErrorSalidaLuna):
        _validar_schema({"facturas": [escalar]}, schema)
    valido["albaranes"][0]["fecha"] = None
    _validar_schema({"facturas": [valido]}, schema)


def test_mas_de_cien_albaranes_con_evidencia_independiente():
    filas = [albaran(f"A-{i:03d}", i + 1, pagina=1 + i // 50, ocurrencia=1 + i % 50) for i in range(101)]
    salida = normalizar_candidato(candidato(albaranes=filas))
    assert len(salida.albaranes) == 101
    assert salida.albaranes[-1].numero.valor == "A-100"


def test_valores_identicos_y_literal_identico_se_distinguen_por_ocurrencia():
    raw = candidato(albaranes=[albaran("MISMO", 1, ocurrencia=1), albaran("MISMO", 2, ocurrencia=2)])
    assert len(normalizar_candidato(raw).albaranes) == 2


def test_localizacion_compartida_no_inventa_fila_cuyo_literal_no_esta_en_contexto():
    raw = candidato(albaranes=[albaran("A-1", 1), albaran("A-2", 2)])
    raw["albaranes"][1]["localizacion"] = copy.deepcopy(raw["albaranes"][0]["localizacion"])
    assert [fila.numero.valor for fila in normalizar_candidato(raw).albaranes] == ["A-1"]


def test_localizacion_se_comparte_dentro_de_fila_con_literal_individual():
    fila = albaran("A-1")
    fila["fecha"] = campo("17/08/2026")
    fila["localizacion"]["contexto_literal"] = "A-1 CARGO 17/08/2026"
    salida = normalizar_candidato(candidato(albaranes=[fila]))
    assert salida.albaranes[0].numero.valor == "A-1"
    assert salida.albaranes[0].fecha.valor.iso.isoformat() == "2026-08-17"


def test_literal_debe_demostrar_valor_y_pertenecer_al_contexto_de_fila():
    raw = candidato(albaranes=[albaran("A-1")])
    raw["albaranes"][0]["numero"] = campo("A-1", "OTRO")
    assert normalizar_candidato(raw).albaranes == []
    raw = candidato(albaranes=[albaran("A-1")])
    raw["albaranes"][0]["sentido"]["literal"] = "NO DEMUESTRA"
    raw["albaranes"][0]["localizacion"]["contexto_literal"] = "A-1 SIN SENTIDO"
    salida = normalizar_candidato(raw)
    assert len(salida.albaranes) == 1 and salida.albaranes[0].sentido is None
    assert any(i.codigo == "SENTIDO_NO_DOCUMENTADO" for i in salida.incidencias)


def test_movimiento_impuesto_vencimiento_y_delivery_se_normalizan_sin_crear_albaran():
    mov_ctx = "RAPPEL ABONO 10"
    imp_ctx = "IVA 21% Base 10"
    vto_ctx = "17/08/2026 121"
    ref_ctx = "DELIVERY D-1"
    raw = candidato(
        movimientos_comerciales=[{
            "orden": 1, "localizacion": localizacion(mov_ctx, ocurrencia=1),
            "tipo": campo("RAPPEL"), "descripcion_literal": campo("RAPPEL"), "sentido": campo("ABONO"),
            "base": campo(10), "iva": None, "recargo_equivalencia": None, "importe": None,
        }],
        impuestos=[{
            "orden": 1, "localizacion": localizacion(imp_ctx, ocurrencia=2),
            "descripcion_literal": campo("IVA 21%"), "base": campo(10), "tipo_iva": campo(21, "21%"),
            "cuota_iva": None, "tipo_recargo_equivalencia": None,
            "cuota_recargo_equivalencia": None, "total_tramo": None,
        }],
        vencimientos=[{
            "orden": 1, "localizacion": localizacion(vto_ctx, ocurrencia=3),
            "fecha": campo("17/08/2026"), "importe": campo(121), "medio_pago": None,
        }],
        referencias_documentales=[{
            "orden": 1, "localizacion": localizacion(ref_ctx, ocurrencia=4),
            "tipo": campo("DELIVERY"), "identificador": campo("D-1"), "descripcion_literal": None,
        }],
    )
    salida = normalizar_candidato(raw)
    assert len(salida.movimientos_comerciales) == len(salida.impuestos) == len(salida.vencimientos) == 1
    assert len(salida.referencias_documentales) == 1
    assert salida.albaranes == []


def test_multifactura_aisla_unicidad_de_localizacion():
    uno = normalizar_candidato(candidato(albaranes=[albaran("A-1")]))
    dos = normalizar_candidato(candidato(albaranes=[albaran("A-2")]))
    assert len(uno.albaranes) == len(dos.albaranes) == 1
    assert consolidar_facturas([uno, dos]).facturas


def test_segmentada_remapea_localizacion_v22():
    raw = candidato(pagina_inicio=1, pagina_fin=1, albaranes=[albaran("S-1")])
    remapeado = _remapear_candidato(raw, (4,))
    assert remapeado["albaranes"][0]["localizacion"]["pagina"] == 4
    assert normalizar_candidato(remapeado).albaranes[0].numero.evidencia[0].pagina == 4


def test_precedencia_v22_invalida_no_cae_a_v21_o_v2():
    raw = candidato(albaranes=[albaran("A-1")])
    raw["albaranes"][0]["numero"]["literal"] = "NO"
    raw["evidencias"] = [{
        "campo": "albaranes[0].numero", "valor": "A-1", "pagina": 1, "literal": "A-1",
        "localizador": {"contexto_literal": "A-1", "ocurrencia_en_pagina": 1},
    }]
    assert normalizar_candidato(raw).albaranes == []


def test_precedencia_v21_exacta_y_fallback_v2_inequivoco_coexisten():
    v21 = candidato(albaranes=[{
        "orden": 1, "fecha": None, "numero": "V21", "sentido": "CARGO", "tipo_pedido": None,
        "importe_base": None, "importe_total": None,
    }])
    v21["evidencias"] = [{
        "campo": "albaranes[0].numero", "valor": "V21", "pagina": 1, "literal": "V21",
        "localizador": {"contexto_literal": "V21", "ocurrencia_en_pagina": 1},
    }]
    assert normalizar_candidato(v21).albaranes[0].numero.valor == "V21"
    v2 = copy.deepcopy(v21)
    v2["albaranes"][0]["numero"] = "V2"
    v2["evidencias"] = [{"campo": "albaranes[0].numero", "pagina": 1, "literal": "V2"}]
    assert normalizar_candidato(v2).albaranes[0].numero.valor == "V2"
    _validar_schema({"facturas": [v21]}, schema_luna_v21())
    _validar_schema({"facturas": [v2]}, schema_luna_v2())


def test_schema_v22_roundtrip_strict_y_sin_propiedades_adicionales():
    schema = schema_luna_v22()
    assert json.loads(json.dumps(schema)) == schema
    assert schema["additionalProperties"] is False
    fila = schema["properties"]["facturas"]["items"]["properties"]["albaranes"]["items"]
    assert fila["additionalProperties"] is False
    assert set(fila["required"]) == set(fila["properties"])
    assert fila["properties"]["numero"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "entrada,cache,salida,esperado",
    [(1000, 0, 500, "0.00400000"), (1000, 100, 500, "0.00391000"), (0, 0, 0, "0E-8"),
     (42544, 0, 4227, "0.06790600")],
)
def test_coste_luna_tarifa_actual(entrada, cache, salida, esperado):
    assert str(calcular_coste(entrada, cache, salida)) == esperado
