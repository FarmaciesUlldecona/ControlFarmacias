from __future__ import annotations

import copy
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfWriter

from src.facturas.normalizador_v2.adaptador_luna import (
    AdaptadorLuna,
    MetadataLuna,
    ResultadoLuna,
)
from src.facturas.normalizador_v2.modelos import FacturaNormalizada
from src.facturas.normalizador_v2.multifactura import consolidar_facturas
from src.facturas.normalizador_v2.normalizador_general import normalizar_candidato
from src.facturas.normalizador_v2.pipeline import (
    _senales_por_defecto,
    normalizar_pdf,
)
from src.facturas.normalizador_v2.reglas import aplicar_reglas_pequenas
from src.facturas.normalizador_v2.splitter import consolidar_lecturas, decidir_segunda_lectura


ROOT = Path(__file__).resolve().parents[4]
E2E = ROOT / "pruebas/facturas/resultados/normalizador_v2_end_to_end_2o_gold"
COLECCIONES = (
    "impuestos",
    "vencimientos",
    "albaranes",
    "movimientos_comerciales",
    "discrepancias_documentales",
)


def _ev(campo: str, literal: str, pagina: int = 1) -> dict:
    return {"campo": campo, "pagina": pagina, "literal": literal}


def candidato_sintetico(*, con_evidencias_colecciones: bool = True, alliance: bool = False) -> dict:
    proveedor = "ALLIANCE" if alliance else "PROVEEDOR SINTETICO"
    inicio, fin = (1, 2) if alliance else (1, 1)
    datos = {
        "tipo_documento": "Factura",
        "naturaleza_principal": "MIXTA",
        "requiere_conciliacion_albaranes": True,
        "pagina_inicio": inicio,
        "pagina_fin": fin,
        "proveedor": {"nombre": proveedor, "nif": None, "direccion": None},
        "numero_factura": "SYN-001",
        "fecha_factura": "14/08/2026",
        "base_imponible_total": 100,
        "iva_total": 21,
        "recargo_equivalencia_total": None,
        "otros_total": None,
        "importe_total": 121,
        "moneda": "EUR",
        "vencimientos": [
            {"orden": 1, "fecha": "20/08/2026", "importe": 60, "medio_pago": "GIRO A"},
            {"orden": 2, "fecha": "20/09/2026", "importe": 61, "medio_pago": "GIRO B"},
        ],
        "impuestos": [
            {"orden": 1, "descripcion_literal": "TRAMO A", "base": 50, "tipo_iva": 21, "cuota_iva": 10.5, "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": None, "total_tramo": 60.5},
            {"orden": 2, "descripcion_literal": "TRAMO B", "base": 50, "tipo_iva": 21, "cuota_iva": 10.5, "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": None, "total_tramo": 60.5},
        ],
        "albaranes": [
            {"orden": 1, "fecha": "01/08/2026", "numero": "ALB-SYN-A", "sentido": "CARGO", "tipo_pedido": "Pedido A", "importe_base": 40, "importe_total": 48.4},
            {"orden": 2, "fecha": "02/08/2026", "numero": "ALB-SYN-B", "sentido": "CARGO", "tipo_pedido": "Pedido B", "importe_base": 60, "importe_total": 72.6},
        ],
        "movimientos_comerciales": [
            {"orden": 1, "tipo": "OTRO", "descripcion_literal": "CONCEPTO SINTETICO A", "sentido": "CARGO", "base": 1, "iva": None, "recargo_equivalencia": None, "importe": 1},
            {"orden": 2, "tipo": "OTRO", "descripcion_literal": "CONCEPTO SINTETICO B", "sentido": "ABONO", "base": 2, "iva": None, "recargo_equivalencia": None, "importe": 2},
        ],
        "destinatario": None,
        "forma_pago": "DOMICILIACION SINTETICA",
        "referencias_documentales": [],
        "discrepancias_documentales": [
            {"tipo": "OTRA", "descripcion": "DISCREPANCIA SINTETICA A", "importe_diferencia": 1, "material": False},
            {"tipo": "OTRA", "descripcion": "DISCREPANCIA SINTETICA B", "importe_diferencia": 2, "material": False},
        ],
        "evidencias": [
            _ev("tipo_documento", "Factura"),
            _ev("proveedor.nombre", proveedor),
            _ev("numero_factura", "SYN-001"),
            _ev("fecha_factura", "14/08/2026"),
            _ev("base_imponible_total", "100,00"),
            _ev("iva_total", "21,00"),
            _ev("importe_total", "121,00"),
            _ev("moneda", "EUR"),
            _ev("forma_pago", "DOMICILIACION SINTETICA"),
        ],
    }
    if con_evidencias_colecciones:
        for i in range(2):
            datos["evidencias"].extend(
                [
                    _ev(f"vencimientos[{i}].fecha", datos["vencimientos"][i]["fecha"]),
                    _ev(f"vencimientos[{i}].importe", str(datos["vencimientos"][i]["importe"])),
                    _ev(f"vencimientos[{i}].medio_pago", datos["vencimientos"][i]["medio_pago"]),
                    _ev(f"impuestos[{i}].descripcion_literal", datos["impuestos"][i]["descripcion_literal"]),
                    _ev(f"impuestos[{i}].base", "50,00"),
                    _ev(f"impuestos[{i}].tipo_iva", "21"),
                    _ev(f"impuestos[{i}].cuota_iva", "10,50"),
                    _ev(f"impuestos[{i}].total_tramo", "60,50"),
                    _ev(f"albaranes[{i}].fecha", datos["albaranes"][i]["fecha"]),
                    _ev(f"albaranes[{i}].numero", datos["albaranes"][i]["numero"]),
                    _ev(f"albaranes[{i}].tipo_pedido", datos["albaranes"][i]["tipo_pedido"]),
                    _ev(f"albaranes[{i}].importe_base", str(datos["albaranes"][i]["importe_base"])),
                    _ev(f"albaranes[{i}].importe_total", str(datos["albaranes"][i]["importe_total"])),
                    _ev(f"movimientos_comerciales[{i}].descripcion_literal", datos["movimientos_comerciales"][i]["descripcion_literal"]),
                    _ev(f"movimientos_comerciales[{i}].base", str(datos["movimientos_comerciales"][i]["base"])),
                    _ev(f"movimientos_comerciales[{i}].importe", str(datos["movimientos_comerciales"][i]["importe"])),
                ]
            )
    return datos


def candidato_sintetico_v23() -> dict:
    datos = copy.deepcopy(candidato_sintetico())
    datos["evidencias"] = []

    def cabecera(valor, literal=None, pagina=1):
        if valor is None:
            return None
        literal = str(valor) if literal is None else literal
        contexto = literal
        return {
            "valor": valor,
            "literal": literal,
            "pagina": pagina,
            "contexto_literal": contexto,
            "span_contexto": {"inicio": 0, "fin": len(literal)},
        }

    datos["tipo_documento"] = cabecera(datos["tipo_documento"])
    datos["numero_factura"] = cabecera(datos["numero_factura"])
    datos["fecha_factura"] = cabecera(datos["fecha_factura"])
    datos["base_imponible_total"] = cabecera(datos["base_imponible_total"])
    datos["iva_total"] = cabecera(datos["iva_total"])
    datos["recargo_equivalencia_total"] = cabecera(datos["recargo_equivalencia_total"])
    datos["otros_total"] = cabecera(datos["otros_total"])
    datos["importe_total"] = cabecera(datos["importe_total"])
    datos["moneda"] = cabecera(datos["moneda"])
    datos["forma_pago"] = cabecera(datos["forma_pago"])

    if datos["proveedor"] is not None:
        datos["proveedor"] = {
            "nombre": cabecera(datos["proveedor"].get("nombre")),
            "nif": cabecera(datos["proveedor"].get("nif")),
            "direccion": cabecera(datos["proveedor"].get("direccion")),
        }

    if datos["destinatario"] is not None:
        datos["destinatario"] = {
            "nombre": cabecera(datos["destinatario"].get("nombre")),
            "nif": cabecera(datos["destinatario"].get("nif")),
            "direccion": cabecera(datos["destinatario"].get("direccion")),
        }
    datos["estructuras_documentales"] = [{
        "id": "e1",
        "tipo": "TABLA",
        "paginas": [1],
        "elementos": [{
            "id": "h1",
            "tipo": "CABECERA",
            "literal": "DATOS SINTETICOS",
            "pagina": 1,
            "span_pagina": {"inicio": 1, "fin": 17},
            "valor_sentido": None,
        }],
    }]
    numero_fila = 0
    for coleccion in ("vencimientos", "impuestos", "albaranes", "movimientos_comerciales", "referencias_documentales"):
        for fila in datos[coleccion]:
            numero_fila += 1
            valores = [(clave, valor) for clave, valor in fila.items() if clave != "orden" and valor is not None]
            literal_fila = " | ".join(str(valor) for _, valor in valores)
            fila["contexto_fila"] = {
                "estructura_id": "e1",
                "elementos_contexto_ids": ["h1"],
                "elemento_sentido_id": None,
                "pagina": 1,
                "literal_fila": literal_fila,
                "span_pagina": {"inicio": numero_fila * 100, "fin": numero_fila * 100 + len(literal_fila)},
                "posicion": {"segmento": 1, "fila": numero_fila, "zona": "cuerpo"},
            }
            cursor = 0
            for clave, valor in valores:
                literal = str(valor)
                inicio = literal_fila.index(literal, cursor)
                fin = inicio + len(literal)
                fila[clave] = {"valor": valor, "literal": literal, "span_fila": {"inicio": inicio, "fin": fin}}
                cursor = fin
    return datos


class _ClienteLocal:
    def __init__(self, candidato: dict):
        self.responses = self
        self.candidato = candidato

    def create(self, **_kwargs):
        return SimpleNamespace(
            id="respuesta_sintetica",
            model="gpt-5.6-luna",
            status="completed",
            output_text=json.dumps({"facturas": [self.candidato]}),
            usage={"input_tokens": 0, "output_tokens": 0},
        )


class _LectorLocal:
    def __init__(self, candidato: dict):
        self.candidato = candidato

    def extraer(self, _ruta):
        return ResultadoLuna(
            (self.candidato,),
            MetadataLuna("local", "gpt-5.6-luna", "gpt-5.6-luna", 0, 0, 0, 0, 0),
        )


def _conteos(factura) -> dict[str, int]:
    return {nombre: len(getattr(factura, nombre)) for nombre in COLECCIONES}


def test_adaptador_normalizador_reglas_y_pipeline_preservan_dos_elementos(tmp_path):
    candidato = candidato_sintetico()
    candidato_adaptador = candidato_sintetico_v23()
    pdf_adaptador = tmp_path / "entrada.bin"
    pdf_adaptador.write_bytes(b"contenido sintetico no PDF")
    adaptado = AdaptadorLuna(cliente=_ClienteLocal(candidato_adaptador), reloj=iter([1.0, 1.1]).__next__).extraer(pdf_adaptador)
    assert {nombre: len(adaptado.facturas[0][nombre]) for nombre in COLECCIONES} == dict.fromkeys(COLECCIONES, 2)

    normalizada = normalizar_candidato(adaptado.facturas[0])
    tras_reglas = aplicar_reglas_pequenas(normalizada)
    assert _conteos(normalizada) == dict.fromkeys(COLECCIONES, 2)
    assert _conteos(tras_reglas) == dict.fromkeys(COLECCIONES, 2)

    pdf_pipeline = tmp_path / "documento.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_pipeline.open("wb") as stream:
        writer.write(stream)
    ahora = iter([datetime(2026, 8, 14, tzinfo=timezone.utc)] * 2).__next__
    doc = normalizar_pdf(
        pdf_pipeline,
        lector_luna=_LectorLocal(candidato),
        ahora=ahora,
        reloj=iter([1.0, 1.1]).__next__,
    )
    assert len(doc.facturas) == 1
    assert _conteos(doc.facturas[0]) == dict.fromkeys(COLECCIONES, 2)


def test_roundtrip_modelo_json_y_persistencia_local_preservan_colecciones(tmp_path):
    factura = aplicar_reglas_pequenas(normalizar_candidato(candidato_sintetico()))
    restaurada = FacturaNormalizada.model_validate_json(factura.json_estable())
    assert _conteos(restaurada) == dict.fromkeys(COLECCIONES, 2)
    ruta = tmp_path / "por_factura_sintetica.json"
    ruta.write_text(factura.json_estable(), encoding="utf-8")
    persistida = FacturaNormalizada.model_validate(json.loads(ruta.read_text(encoding="utf-8")))
    assert _conteos(persistida) == dict.fromkeys(COLECCIONES, 2)


def test_multifactura_dedup_preserva_colecciones_de_factura_retenida():
    base = aplicar_reglas_pequenas(normalizar_candidato(candidato_sintetico()))
    duplicada = base.model_copy(update={"factura_id": "zz_duplicada"})
    resultado = consolidar_facturas([duplicada, base])
    assert len(resultado.facturas) == 1
    assert _conteos(resultado.facturas[0]) == dict.fromkeys(COLECCIONES, 2)


def test_consolidacion_segmentada_fusiona_las_tres_colecciones_corregidas():
    completa = aplicar_reglas_pequenas(normalizar_candidato(candidato_sintetico()))
    primaria = completa.model_copy(update={
        "vencimientos": [],
        "impuestos": [],
        "discrepancias_documentales": [],
    })
    resultado = consolidar_lecturas([primaria], [completa])[0]
    assert len(resultado.albaranes) == 2
    assert len(resultado.movimientos_comerciales) == 2
    # Este diagnÃ³stico reproducÃ­a deliberadamente la pÃ©rdida ya corregida.
    assert len(resultado.vencimientos) == 2
    assert len(resultado.impuestos) == 2
    assert len(resultado.discrepancias_documentales) == 2


def test_sin_evidencia_normalizador_elimina_anclas_e_impuestos_vacios():
    salida = normalizar_candidato(candidato_sintetico(con_evidencias_colecciones=False))
    assert len(salida.vencimientos) == 0
    assert len(salida.albaranes) == 0
    assert len(salida.movimientos_comerciales) == 0
    assert len(salida.discrepancias_documentales) == 2
    # Los dos objetos vacÃ­os eran la reproducciÃ³n exacta del defecto de Fase 9.
    assert salida.impuestos == []


def test_validacion_repetida_no_duplica_discrepancia_calculada():
    candidato = candidato_sintetico()
    candidato["importe_total"] = 125
    candidato["evidencias"] = [e if e["campo"] != "importe_total" else _ev("importe_total", "125,00") for e in candidato["evidencias"]]
    normalizada = normalizar_candidato(candidato)
    tras_reglas = aplicar_reglas_pequenas(normalizada)
    generadas = [d for d in tras_reglas.discrepancias_documentales if d.descripcion == "Los componentes impresos no cuadran con el total impreso"]
    # La discrepancia automÃ¡tica CUADRE_TOTAL debe ser idempotente.
    assert len(generadas) == 1


def test_evaluador_con_salida_sintetica_correcta_detecta_colecciones():
    ruta = ROOT / "pruebas/facturas/resultados/comparativa_2o_gold_a_b_c/evaluar.py"
    spec = importlib.util.spec_from_file_location("evaluador_historico_estructura", ruta)
    modulo = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(modulo)
    factura = {
        "vencimientos": [{"fecha": "2026-08-20", "importe": 60}, {"fecha": "2026-09-20", "importe": 61}],
        "impuestos": [{"base": 50, "tipo_iva": 21, "cuota_iva": 10.5, "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": None}] * 2,
        "albaranes": [{"numero": "A", "fecha": "2026-08-01", "naturaleza": "CARGO", "tipo_pedido": None, "importe_base": 40, "importe_total": 48.4}, {"numero": "B", "fecha": "2026-08-02", "naturaleza": "CARGO", "tipo_pedido": None, "importe_base": 60, "importe_total": 72.6}],
        "movimientos_comerciales": [{"tipo": "OTRO", "descripcion_literal": "A", "sentido": "CARGO", "base": 1, "iva": None, "recargo_equivalencia": None, "importe": 1}, {"tipo": "OTRO", "descripcion_literal": "B", "sentido": "ABONO", "base": 2, "iva": None, "recargo_equivalencia": None, "importe": 2}],
    }
    metricas = modulo.list_metrics([(factura, json.loads(json.dumps(factura)))], [])
    assert all(metricas[nombre]["detectados"] == 2 for nombre in ("vencimientos", "impuestos", "albaranes", "movimientos_comerciales"))
    assert all(metricas[nombre]["inventados"] == 0 for nombre in ("vencimientos", "impuestos", "albaranes", "movimientos_comerciales"))


def test_decisor_alliance_recibe_senal_independiente_de_omision():
    candidato = candidato_sintetico(con_evidencias_colecciones=False, alliance=True)
    factura = normalizar_candidato(candidato)
    senales = _senales_por_defecto(factura, candidato)
    decision = decidir_segunda_lectura(senales)
    assert senales.identificadores_visibles == 2
    assert senales.filas_extraidas == 0
    assert not senales.tabla_multipagina
    assert not senales.densidad_alta
    assert decision.activar is True


def test_reconciliacion_exacta_57_invenciones_sin_abrir_gold():
    metricas = json.loads((E2E / "metricas.json").read_text(encoding="utf-8"))
    por_factura = json.loads((E2E / "resultados_por_factura.json").read_text(encoding="utf-8"))
    assert metricas["invenciones_totales_prioritarias"] == 57
    assert metricas["campos_principales"]["invenciones"] == 11
    assert metricas["impuestos"]["inventados"] == 43
    assert metricas["discrepancias_documentales"]["inventadas"] == 3
    assert 11 + 43 + 3 == 57
    principales = {
        item["numero_factura"]: sum(estado == "INVENCION" for estado in item["campos"].values())
        for item in por_factura
    }
    assert sum(principales.values()) == 11
    assert {k: v for k, v in principales.items() if v} == {
        "5450053457": 2,
        "5460017198": 1,
        "FR00263663": 1,
        "TM-26075800": 1,
        "SI26-04567": 1,
        "VN26-0016742": 1,
        "0563820041": 1,
        "3401124788": 1,
        "003463FV26": 1,
        "G/15.931": 1,
    }
    impuestos_por_factura = {item["numero_factura"]: item["conteos"]["impuestos"]["salida"] for item in por_factura}
    assert sum(impuestos_por_factura.values()) == 43
    discrepancias = metricas["discrepancias_documentales"]["por_factura"]
    assert {x["numero_factura"]: x["inventadas"] for x in discrepancias if x["inventadas"]} == {
        "FR00263826": 1,
        "3401124788": 2,
    }


def test_43_impuestos_congelados_son_objetos_completamente_vacios():
    total = 0
    for ruta in sorted((E2E / "por_factura").glob("*.json")):
        factura = json.loads(ruta.read_text(encoding="utf-8"))
        factura = factura.get("factura", factura)
        for tramo in factura["impuestos"]:
            total += 1
            assert all(tramo[campo] is None for campo in (
                "descripcion_literal",
                "base",
                "tipo_iva",
                "cuota_iva",
                "tipo_recargo_equivalencia",
                "cuota_recargo_equivalencia",
                "total_tramo",
            ))
    assert total == 43
