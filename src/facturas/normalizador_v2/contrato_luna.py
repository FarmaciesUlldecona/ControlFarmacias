from __future__ import annotations

from copy import deepcopy

MODELO_LUNA = "gpt-5.6-luna"
PROMPT_B_SHA256 = "169cdba865e9a130fc0a5c07ab9b9af3c1a94f980a319893dd94377ea3c8c60d"
SCHEMA_B_SHA256 = "bfb6d2c277a585eb75703ec6f03548b282ef927d0c5850e6e66590f0fba1ec71"
CONTRATO_VERSION = "normalizador-v2-luna-1"
CONTRATO_VERSION_V21 = "normalizador-v2.1-luna-1"
CONTRATO_VERSION_V22 = "normalizador-v2.2-luna-1"
CONTRATO_VERSION_V23 = "normalizador-v2.3-luna-2"
CONTRATO_VERSION_V24 = "normalizador-v2.4-luna-1"

PROMPT_LUNA_V2 = """Eres un extractor documental estrictamente literal. Examina integramente el PDF adjunto y devuelve un unico objeto JSON que cumpla exactamente el schema proporcionado.

El PDF puede contener cero, una o varias facturas. Extrae todas las facturas demostrables por el contenido visible. No uses el nombre del archivo como evidencia. No presupongas cantidades esperadas, proveedores ni resultados externos.

Cero invenciones: todo dato ausente, ilegible o no demostrable es null o []. Conserva literales e identificadores completos. No corrijas discrepancias ni reconstruyas importes. Naturaleza describe actividad: MERCANCIA, SERVICIOS, MIXTA o CONDICIONES_COMERCIALES; CARGO y ABONO son exclusivamente sentidos de movimientos. Delivery, PO, Pedido, Order o Document son referencias, nunca albaranes salvo rotulo explicito. Extrae todos los tramos, vencimientos, albaranes, movimientos y referencias visibles sin resumir. Cada valor no nulo debe estar respaldado en evidencias por campo con pagina y literal. Devuelve exclusivamente JSON estructurado."""

PROMPT_LUNA_V21 = PROMPT_LUNA_V2.replace(
    "Cada valor no nulo debe estar respaldado en evidencias por campo con pagina y literal.",
    """Cada valor documental no nulo debe estar respaldado en evidencias por campo. En vencimientos, impuestos, albaranes, movimientos_comerciales y referencias_documentales emite una evidencia individual por cada campo documental no nulo: campo con ruta indexada exacta, valor tipado identico al campo, pagina, literal minimo que contiene el valor y localizador. El localizador usa contexto_literal de la misma fila/celda y ocurrencia_en_pagina cuando haga falta para distinguir literales identicos. No uses cabeceras, paginas, colecciones ni texto generico como evidencia de una fila/celda. No reutilices una evidencia entre campos o filas. Si falta evidencia individual o es ambigua, devuelve null o elimina la fila cuando su identificador critico no sea demostrable.""",
)

PROMPT_LUNA_V22 = PROMPT_LUNA_V2.replace(
    "Cada valor no nulo debe estar respaldado en evidencias por campo con pagina y literal.",
    """En vencimientos, impuestos, albaranes, movimientos_comerciales y referencias_documentales, cada fila lleva una localizacion propia (pagina, contexto_literal de esa fila y ocurrencia_en_pagina). Cada campo documental es null o un objeto con valor no nulo y su literal individual; no extraigas un valor sin ese literal anidado. El literal debe aparecer en el contexto de la misma fila y demostrar el valor. Trata cada fila de forma independiente. Filas repetidas o valores iguales requieren ocurrencias distintas; no reutilices una localizacion entre filas. Comparte la localizacion solo entre campos de la misma fila. Si el identificador critico de una fila no es demostrable, omite la fila; para los demas campos no demostrables usa null. evidencias no es el respaldo principal de estas cinco colecciones.""",
)

PROMPT_LUNA_V23 = PROMPT_LUNA_V2.replace(
    "Cada valor no nulo debe estar respaldado en evidencias por campo con pagina y literal.",
    """En vencimientos, impuestos, albaranes, movimientos_comerciales y referencias_documentales conserva contexto estructural verificable por fila. En cada factura emite una sola vez estructuras_documentales con ids cortos y unicos para tablas, secciones o bloques observados y sus elementos CABECERA, COLUMNA, SECCION o BLOQUE. Cada fila referencia una estructura de esa misma factura y conserva pagina original, literal_fila completo, span_pagina y posicion inequivoca; cada campo es null o contiene valor, literal y span_fila individual. Los spans usan inicio inclusivo y fin exclusivo. No uses indices de arrays como referencias.

Para los campos documentales de cabecera tipo_documento, numero_factura, fecha_factura, base_imponible_total, iva_total, recargo_equivalencia_total, otros_total, importe_total, moneda y forma_pago, y para nombre, nif y direccion de proveedor y destinatario, cada valor no nulo debe incluir valor, literal, pagina, contexto_literal y span_contexto. contexto_literal debe ser una porcion visible y suficiente del documento que contenga literalmente el dato; span_contexto localiza exactamente el literal dentro de ese contexto. Si el dato no puede localizarse de forma inequivoca, devuelve null. No uses el nombre del archivo, conocimiento externo ni otros campos como sustituto de evidencia.

Solo emite sentido CARGO o ABONO si: (A) el literal explicito inequivoco aparece en la propia fila; o (B) un elemento estructural explicito contiene solo ese sentido, la fila referencia ese elemento y pertenece inequivocamente a su tabla, columna, seccion o bloque. No derives sentido por signo, proveedor, numero, pagina, posicion aislada, tipo de pedido, correlacion ni contexto no vinculado. Si una cabecera contiene ambas alternativas, varias estructuras aplican o el vinculo no es demostrable, omite la fila critica. Conserva el elemento fuente, la fila fuente y sus spans.

Una linea fisica puede contener varios hechos. Emite cada hecho por separado con tipo/campo, literal o span individual y contexto estructural; compartir linea no es conflicto. No reutilices el mismo span para valores incompatibles ni emitas filas indistinguibles. Repite solo contexto propio de la fila; comparte cabeceras, secciones y bloques mediante ids dentro de la misma factura. evidencias laterales conserva compatibilidad, pero no sustituye este respaldo.""",
)

PROMPT_LUNA_V24 = PROMPT_LUNA_V23.replace(
    "Si una cabecera contiene ambas alternativas, varias estructuras aplican o el vinculo no es demostrable, omite la fila critica.",
    "Si una cabecera contiene ambas alternativas, varias estructuras aplican o el vinculo no es demostrable, usa sentido null y conserva la fila cuando su identidad o descripcion documental sea demostrable.",
).replace(
    "Conserva el elemento fuente, la fila fuente y sus spans.",
    "Conserva el elemento fuente, la fila fuente y sus spans. La descripcion de un concepto, su proveedor, signo, numero, prefijo, posicion u orden no determinan CARGO o ABONO. Un movimiento comercial con descripcion demostrable se conserva aunque sentido sea null.",
)


def _nullable(tipo: str) -> dict:
    return {"type": [tipo, "null"]}


def _fila(campos: dict, requeridos: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": requeridos or list(campos),
        "properties": campos,
    }


def _texto_no_vacio() -> dict:
    return {"type": "string", "minLength": 1}


def _campo_v22(valor_schema: dict, *, nullable: bool = True) -> dict:
    documentado = _fila({"valor": valor_schema, "literal": _texto_no_vacio()})
    return {"anyOf": [documentado, {"type": "null"}]} if nullable else documentado


def _campo_v23(valor_schema: dict, *, nullable: bool = True) -> dict:
    documentado = _fila({
        "valor": valor_schema,
        "literal": _texto_no_vacio(),
        "span_fila": {"anyOf": [SPAN_V23, {"type": "null"}]},
    })
    return {"anyOf": [documentado, {"type": "null"}]} if nullable else documentado

def _campo_cabecera_v23(valor_schema: dict, *, nullable: bool = True) -> dict:
    documentado = _fila({
        "valor": valor_schema,
        "literal": _texto_no_vacio(),
        "pagina": {"type": "integer", "minimum": 1},
        "contexto_literal": _texto_no_vacio(),
        "span_contexto": SPAN_V23,
    })
    return {"anyOf": [documentado, {"type": "null"}]} if nullable else documentado


EVIDENCIA = _fila({"campo": {"type": "string"}, "pagina": {"type": "integer", "minimum": 1}, "literal": {"type": "string"}})
VALOR_TIPADO = {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]}
LOCALIZADOR_V21 = _fila({
    "contexto_literal": _nullable("string"),
    "ocurrencia_en_pagina": {"type": ["integer", "null"], "minimum": 1},
})
EVIDENCIA_V21 = _fila({
    "campo": {"type": "string"}, "valor": VALOR_TIPADO,
    "pagina": {"type": "integer", "minimum": 1}, "literal": {"type": "string"},
    "localizador": LOCALIZADOR_V21,
})
VENCIMIENTO = _fila({"orden": {"type": "integer", "minimum": 1}, "fecha": _nullable("string"), "importe": _nullable("number"), "medio_pago": _nullable("string")})
IMPUESTO = _fila({
    "orden": {"type": "integer", "minimum": 1}, "descripcion_literal": _nullable("string"),
    "base": _nullable("number"), "tipo_iva": _nullable("number"), "cuota_iva": _nullable("number"),
    "tipo_recargo_equivalencia": _nullable("number"), "cuota_recargo_equivalencia": _nullable("number"), "total_tramo": _nullable("number"),
})
ALBARAN = _fila({
    "orden": {"type": "integer", "minimum": 1}, "fecha": _nullable("string"), "numero": {"type": "string"},
    "sentido": {"type": "string", "enum": ["CARGO", "ABONO"]}, "tipo_pedido": _nullable("string"),
    "importe_base": _nullable("number"), "importe_total": _nullable("number"),
})
MOVIMIENTO = _fila({
    "orden": {"type": "integer", "minimum": 1},
    "tipo": {"type": "string", "enum": ["RAPPEL", "ABONO_COMERCIAL", "DEVOLUCION_MERCANCIA", "DESCUENTO", "BONIFICACION", "SERVICIO", "CONDICION_COMERCIAL", "OTRO"]},
    "descripcion_literal": {"type": "string"}, "sentido": {"type": "string", "enum": ["ABONO", "CARGO"]},
    "base": _nullable("number"), "iva": _nullable("number"), "recargo_equivalencia": _nullable("number"), "importe": _nullable("number"),
})
REFERENCIA = _fila({
    "orden": {"type": "integer", "minimum": 1}, "tipo": {"type": "string", "enum": ["DELIVERY", "PEDIDO", "PO", "ORDER", "DOCUMENTO", "OTRA"]},
    "identificador": {"type": "string"}, "descripcion_literal": _nullable("string"),
})

LOCALIZACION_FILA_V22 = _fila({
    "pagina": {"type": "integer", "minimum": 1},
    "contexto_literal": _texto_no_vacio(),
    "ocurrencia_en_pagina": {"type": "integer", "minimum": 1},
})
SPAN_V23 = _fila({
    "inicio": {"type": "integer", "minimum": 0},
    "fin": {"type": "integer", "minimum": 1},
})
ELEMENTO_ESTRUCTURAL_V23 = _fila({
    "id": _texto_no_vacio(),
    "tipo": {"type": "string", "enum": ["CABECERA", "COLUMNA", "SECCION", "BLOQUE"]},
    "literal": _texto_no_vacio(),
    "pagina": {"type": "integer", "minimum": 1},
    "span_pagina": SPAN_V23,
    "valor_sentido": {"type": ["string", "null"], "enum": ["CARGO", "ABONO", None]},
})
ESTRUCTURA_DOCUMENTAL_V23 = _fila({
    "id": _texto_no_vacio(),
    "tipo": {"type": "string", "enum": ["TABLA", "SECCION", "BLOQUE"]},
    "paginas": {"type": "array", "items": {"type": "integer", "minimum": 1}},
    "elementos": {"type": "array", "items": ELEMENTO_ESTRUCTURAL_V23},
})
POSICION_FILA_V23 = _fila({
    "segmento": {"type": "integer", "minimum": 1},
    "fila": {"type": "integer", "minimum": 1},
    "zona": _texto_no_vacio(),
})
CONTEXTO_FILA_V23 = _fila({
    "estructura_id": _texto_no_vacio(),
    "elementos_contexto_ids": {"type": "array", "items": _texto_no_vacio()},
    "elemento_sentido_id": {"type": ["string", "null"]},
    "pagina": {"type": "integer", "minimum": 1},
    "literal_fila": _texto_no_vacio(),
    "span_pagina": SPAN_V23,
    "posicion": POSICION_FILA_V23,
})
VENCIMIENTO_V22 = _fila({
    "orden": {"type": "integer", "minimum": 1}, "localizacion": LOCALIZACION_FILA_V22,
    "fecha": _campo_v22({"type": "string"}), "importe": _campo_v22({"type": "number"}),
    "medio_pago": _campo_v22({"type": "string"}),
})
IMPUESTO_V22 = _fila({
    "orden": {"type": "integer", "minimum": 1}, "localizacion": LOCALIZACION_FILA_V22,
    "descripcion_literal": _campo_v22({"type": "string"}), "base": _campo_v22({"type": "number"}),
    "tipo_iva": _campo_v22({"type": "number"}), "cuota_iva": _campo_v22({"type": "number"}),
    "tipo_recargo_equivalencia": _campo_v22({"type": "number"}),
    "cuota_recargo_equivalencia": _campo_v22({"type": "number"}), "total_tramo": _campo_v22({"type": "number"}),
})
ALBARAN_V22 = _fila({
    "orden": {"type": "integer", "minimum": 1}, "localizacion": LOCALIZACION_FILA_V22,
    "fecha": _campo_v22({"type": "string"}), "numero": _campo_v22(_texto_no_vacio(), nullable=False),
    "sentido": _campo_v22({"type": "string", "enum": ["CARGO", "ABONO"]}, nullable=False),
    "tipo_pedido": _campo_v22({"type": "string"}), "importe_base": _campo_v22({"type": "number"}),
    "importe_total": _campo_v22({"type": "number"}),
})
MOVIMIENTO_V22 = _fila({
    "orden": {"type": "integer", "minimum": 1}, "localizacion": LOCALIZACION_FILA_V22,
    "tipo": _campo_v22({"type": "string", "enum": ["RAPPEL", "ABONO_COMERCIAL", "DEVOLUCION_MERCANCIA", "DESCUENTO", "BONIFICACION", "SERVICIO", "CONDICION_COMERCIAL", "OTRO"]}, nullable=False),
    "descripcion_literal": _campo_v22(_texto_no_vacio(), nullable=False),
    "sentido": _campo_v22({"type": "string", "enum": ["ABONO", "CARGO"]}, nullable=False),
    "base": _campo_v22({"type": "number"}), "iva": _campo_v22({"type": "number"}),
    "recargo_equivalencia": _campo_v22({"type": "number"}), "importe": _campo_v22({"type": "number"}),
})
REFERENCIA_V22 = _fila({
    "orden": {"type": "integer", "minimum": 1}, "localizacion": LOCALIZACION_FILA_V22,
    "tipo": _campo_v22({"type": "string", "enum": ["DELIVERY", "PEDIDO", "PO", "ORDER", "DOCUMENTO", "OTRA"]}, nullable=False),
    "identificador": _campo_v22(_texto_no_vacio(), nullable=False),
    "descripcion_literal": _campo_v22({"type": "string"}),
})


def _fila_v23(campos: dict[str, dict]) -> dict:
    return _fila({"orden": {"type": "integer", "minimum": 1}, "contexto_fila": CONTEXTO_FILA_V23, **campos})


VENCIMIENTO_V23 = _fila_v23({
    "fecha": _campo_v23({"type": "string"}), "importe": _campo_v23({"type": "number"}),
    "medio_pago": _campo_v23({"type": "string"}),
})
IMPUESTO_V23 = _fila_v23({
    "descripcion_literal": _campo_v23({"type": "string"}), "base": _campo_v23({"type": "number"}),
    "tipo_iva": _campo_v23({"type": "number"}), "cuota_iva": _campo_v23({"type": "number"}),
    "tipo_recargo_equivalencia": _campo_v23({"type": "number"}),
    "cuota_recargo_equivalencia": _campo_v23({"type": "number"}), "total_tramo": _campo_v23({"type": "number"}),
})
ALBARAN_V23 = _fila_v23({
    "fecha": _campo_v23({"type": "string"}), "numero": _campo_v23(_texto_no_vacio(), nullable=False),
    "sentido": _campo_v23({"type": "string", "enum": ["CARGO", "ABONO"]}, nullable=False),
    "tipo_pedido": _campo_v23({"type": "string"}), "importe_base": _campo_v23({"type": "number"}),
    "importe_total": _campo_v23({"type": "number"}),
})
MOVIMIENTO_V23 = _fila_v23({
    "tipo": _campo_v23({"type": "string", "enum": ["RAPPEL", "ABONO_COMERCIAL", "DEVOLUCION_MERCANCIA", "DESCUENTO", "BONIFICACION", "SERVICIO", "CONDICION_COMERCIAL", "OTRO"]}, nullable=False),
    "descripcion_literal": _campo_v23(_texto_no_vacio(), nullable=False),
    "sentido": _campo_v23({"type": "string", "enum": ["ABONO", "CARGO"]}, nullable=False),
    "base": _campo_v23({"type": "number"}), "iva": _campo_v23({"type": "number"}),
    "recargo_equivalencia": _campo_v23({"type": "number"}), "importe": _campo_v23({"type": "number"}),
})
REFERENCIA_V23 = _fila_v23({
    "tipo": _campo_v23({"type": "string", "enum": ["DELIVERY", "PEDIDO", "PO", "ORDER", "DOCUMENTO", "OTRA"]}, nullable=False),
    "identificador": _campo_v23(_texto_no_vacio(), nullable=False),
    "descripcion_literal": _campo_v23({"type": "string"}),
})
TERCERO = _fila({"nombre": _nullable("string"), "nif": _nullable("string"), "direccion": _nullable("string")})
TERCERO_V23 = _fila({
    "nombre": _campo_cabecera_v23({"type": "string"}),
    "nif": _campo_cabecera_v23({"type": "string"}),
    "direccion": _campo_cabecera_v23({"type": "string"}),
})
DISCREPANCIA = _fila({"tipo": {"type": "string", "enum": ["CUADRE_FISCAL", "CUADRE_ALBARANES", "SUBTOTAL_NO_EXPLICADO", "IDENTIFICADOR_AMBIGUO", "OTRA"]}, "descripcion": {"type": "string"}, "importe_diferencia": _nullable("number"), "material": {"type": "boolean"}})

FACTURA = _fila({
    "tipo_documento": _nullable("string"),
    "naturaleza_principal": {"type": "string", "enum": ["MERCANCIA", "SERVICIOS", "MIXTA", "CONDICIONES_COMERCIALES"]},
    "requiere_conciliacion_albaranes": {"type": "boolean"},
    "pagina_inicio": {"type": "integer", "minimum": 1}, "pagina_fin": {"type": "integer", "minimum": 1},
    "proveedor": {"anyOf": [TERCERO, {"type": "null"}]}, "numero_factura": _nullable("string"), "fecha_factura": _nullable("string"),
    "base_imponible_total": _nullable("number"), "iva_total": _nullable("number"), "recargo_equivalencia_total": _nullable("number"), "otros_total": _nullable("number"), "importe_total": _nullable("number"), "moneda": _nullable("string"),
    "vencimientos": {"type": "array", "items": VENCIMIENTO}, "impuestos": {"type": "array", "items": IMPUESTO},
    "albaranes": {"type": "array", "items": ALBARAN}, "movimientos_comerciales": {"type": "array", "items": MOVIMIENTO},
    "destinatario": {"anyOf": [TERCERO, {"type": "null"}]}, "forma_pago": _nullable("string"),
    "referencias_documentales": {"type": "array", "items": REFERENCIA}, "discrepancias_documentales": {"type": "array", "items": DISCREPANCIA},
    "evidencias": {"type": "array", "items": EVIDENCIA},
})

SCHEMA_LUNA_V2 = _fila({"facturas": {"type": "array", "items": FACTURA}})

FACTURA_V21 = deepcopy(FACTURA)
FACTURA_V21["properties"]["evidencias"] = {"type": "array", "items": EVIDENCIA_V21}
SCHEMA_LUNA_V21 = _fila({"facturas": {"type": "array", "items": FACTURA_V21}})

FACTURA_V22 = deepcopy(FACTURA_V21)
FACTURA_V22["properties"].update({
    "vencimientos": {"type": "array", "items": VENCIMIENTO_V22},
    "impuestos": {"type": "array", "items": IMPUESTO_V22},
    "albaranes": {"type": "array", "items": ALBARAN_V22},
    "movimientos_comerciales": {"type": "array", "items": MOVIMIENTO_V22},
    "referencias_documentales": {"type": "array", "items": REFERENCIA_V22},
})
SCHEMA_LUNA_V22 = _fila({"facturas": {"type": "array", "items": FACTURA_V22}})

FACTURA_V23 = deepcopy(FACTURA_V22)
FACTURA_V23["properties"].update({
    "tipo_documento": _campo_cabecera_v23({"type": "string"}),
    "proveedor": {"anyOf": [TERCERO_V23, {"type": "null"}]},
    "numero_factura": _campo_cabecera_v23({"type": "string"}),
    "fecha_factura": _campo_cabecera_v23({"type": "string"}),
    "base_imponible_total": _campo_cabecera_v23({"type": "number"}),
    "iva_total": _campo_cabecera_v23({"type": "number"}),
    "recargo_equivalencia_total": _campo_cabecera_v23({"type": "number"}),
    "otros_total": _campo_cabecera_v23({"type": "number"}),
    "importe_total": _campo_cabecera_v23({"type": "number"}),
    "moneda": _campo_cabecera_v23({"type": "string"}),
    "destinatario": {"anyOf": [TERCERO_V23, {"type": "null"}]},
    "forma_pago": _campo_cabecera_v23({"type": "string"}),
    "estructuras_documentales": {"type": "array", "items": ESTRUCTURA_DOCUMENTAL_V23},
    "vencimientos": {"type": "array", "items": VENCIMIENTO_V23},
    "impuestos": {"type": "array", "items": IMPUESTO_V23},
    "albaranes": {"type": "array", "items": ALBARAN_V23},
    "movimientos_comerciales": {"type": "array", "items": MOVIMIENTO_V23},
    "referencias_documentales": {"type": "array", "items": REFERENCIA_V23},
})
FACTURA_V23["required"] = list(FACTURA_V23["properties"])
SCHEMA_LUNA_V23 = _fila({"facturas": {"type": "array", "items": FACTURA_V23}})

ALBARAN_V24 = deepcopy(ALBARAN_V23)
ALBARAN_V24["properties"]["sentido"] = _campo_v23({"type": "string", "enum": ["CARGO", "ABONO"]})
MOVIMIENTO_V24 = deepcopy(MOVIMIENTO_V23)
MOVIMIENTO_V24["properties"]["sentido"] = _campo_v23({"type": "string", "enum": ["ABONO", "CARGO"]})
FACTURA_V24 = deepcopy(FACTURA_V23)
FACTURA_V24["properties"]["albaranes"] = {"type": "array", "items": ALBARAN_V24}
FACTURA_V24["properties"]["movimientos_comerciales"] = {"type": "array", "items": MOVIMIENTO_V24}
SCHEMA_LUNA_V24 = _fila({"facturas": {"type": "array", "items": FACTURA_V24}})


def schema_luna_v2() -> dict:
    return deepcopy(SCHEMA_LUNA_V2)


def schema_luna_v21() -> dict:
    return deepcopy(SCHEMA_LUNA_V21)


def schema_luna_v22() -> dict:
    return deepcopy(SCHEMA_LUNA_V22)


def schema_luna_v23() -> dict:
    return deepcopy(SCHEMA_LUNA_V23)


def schema_luna_v24() -> dict:
    return deepcopy(SCHEMA_LUNA_V24)
