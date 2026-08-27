from __future__ import annotations

import socket
from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.fedefarma import AdaptadorFedefarma
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.configuracion import ConfiguracionShadow
from src.facturas.motor_local.geometria.lineas import agrupar_por_linea
from src.facturas.motor_local.modelos import DocumentoLocal, PaginaLocal, PalabraLocal, RegionLocal
from src.facturas.motor_local.observabilidad import ObservabilidadMemoria
from src.facturas.motor_local.servicio import MotorDocumentoLocal, hash_funcional
from src.facturas.motor_local.shadow import ejecutar_shadow_cofares_sobre_resultado


ROOT = Path(__file__).resolve().parents[3]
PDF_DECENAL = ROOT / "pruebas/facturas/documentos/FEDE VTO 5.8.26 PIO.pdf"
PDF_MULTIFACTURA = ROOT / "pruebas/facturas/documentos/2o_gold_standard/FEDE VTO 15.8.26 PIO.pdf"
SHA_DECENAL = "8a9fba8dafff8ae6d6cdc5283de09033ed6a93bacdb454f36fdc5d741ac945d0"
SHA_MULTIFACTURA = "e9bea97f9a2b384141304c92dfd8f318ee224707d203d823c3830999987b90f3"


def _documento_indicio_sin_layout() -> DocumentoLocal:
    texto = "FEDERACIÓ FARMACÈUTICA F-08-173395 INFORMACIÓ FACTURES/CÀRREC RELACIÓ DE FACTURES/CÀRRECS"
    palabra = PalabraLocal(texto, 1, RegionLocal(10, 10, 580, 20), 1)
    pagina = PaginaLocal(1, 595, 842, texto, [palabra], agrupar_por_linea([palabra]))
    return DocumentoLocal("neutro.pdf", "a" * 64, [pagina])


def test_fedefarma_no_se_aplica_solo_por_identidad_sin_layout_conocido():
    assert AdaptadorFedefarma().reconocer(_documento_indicio_sin_layout()).estado == "AMBIGUO"


def test_continuacion_multilinea_general_no_invade_otra_columna():
    palabras = [
        PalabraLocal("ANCLA", 1, RegionLocal(10, 10, 40, 20), 1),
        PalabraLocal("CONTINUA", 1, RegionLocal(50, 22, 90, 30), 2),
        PalabraLocal("FUERA", 1, RegionLocal(150, 32, 190, 40), 3),
    ]
    lineas = agrupar_por_linea(palabras)
    assert [l.texto for l in AdaptadorFedefarma.lineas_continuacion_columna(
        lineas, lineas[0], x0=45, x1=100, salto_maximo=12,
    )] == ["CONTINUA"]


@pytest.mark.skipif(not PDF_DECENAL.exists(), reason="corpus externo FEDEFARMA decenal no disponible")
def test_fedefarma_decena_completa_ciega():
    resultado = MotorDocumentoLocal(BackendPdfium()).extraer(PDF_DECENAL)
    assert resultado.documento["sha256"] == SHA_DECENAL
    assert resultado.documento["layout"] == "fedefarma-local"
    assert resultado.documento["layout_version"] == "1.2.0"
    assert resultado.documento["segmentation_audit"][0]["rol"] == "RESUMEN_MULTI_DOCUMENTO"
    assert [(s.paginas, s.identidad_candidata) for s in resultado.segmentos] == [([2, 2], "VN2605-0005381")]
    assert len(resultado.facturas) == 1
    factura = resultado.facturas[0]
    assert factura["segmento"]["sha_documento"] == SHA_DECENAL
    assert factura["layout"] == "FEDEFARMA_MERCANCIA_RESUMEN_FISCAL"
    assert factura["cabecera"]["numero_factura"]["valor"] == "VN2605-0005381"
    assert factura["cabecera"]["fecha_factura"]["valor"] == "2026-07-20"
    assert factura["cabecera"]["importe_total"]["valor"] == 62.59
    assert factura["cabecera"]["moneda"] is None
    assert factura["cabecera"]["codigo_farmacia"]["valor"] == "0500"
    assert len(factura["albaranes"]) == 4
    assert [a.numero_albaran for a in factura["albaranes"]] == [
        "2620-2051956", "2620-2090700", "2620-2100818", "2620-2100853",
    ]
    assert all(a.sentido is None and a.rol_fila == "DETALLE_ALBARAN" for a in factura["albaranes"])
    assert len(factura["movimientos"]) == 3
    assert all(m["sentido"] is None for m in factura["movimientos"])
    assert factura["movimientos"][0]["detalle_documental"]["motivo"]["valor"] == "FG"
    assert factura["movimientos"][0]["detalle_documental"]["descripcion"]["valor"].endswith("500ML")
    assert factura["movimientos"][0]["detalle_documental"]["conclusion_categoria"] == "DEVOLUCION_MERCANCIA_DECISION_FUNCIONAL_PIO"
    assert factura["movimientos"][0]["categoria"] == "DEVOLUCION_MERCANCIA"
    assert factura["movimientos"][0]["sentido"] is None
    assert factura["movimientos"][1]["categoria"] == "BONIFICACION"
    assert factura["movimientos"][1]["sentido"] is None
    assert len(factura["impuestos"]) == 5
    assert len(factura["vencimientos"]) == 1
    assert factura["vencimientos"][0]["importe"]["valor"] == 62.59
    assert len(factura["otros"]) == 3
    agregado = next(x for x in factura["otros"] if x["tipo"] == "AGREGADO_TOTAL_ALBARANES")
    assert agregado["total"]["valor"] == 68.40
    assert agregado["desglose"]["IVA_4"]["valor"] == 19.29
    resumen = resultado.otros[0]
    assert resumen["modo_facturacion"]["valor"] == "FACTURACIO_DECENAL"
    assert [x["clasificacion_documental"]["valor"] for x in resumen["relacion_facturas"]] == ["NOR"]
    assert len(resumen["relacion_facturas"]) == len(resumen["relacion_pagos"]) == 1
    assert {x["categoria_documental"] for x in resumen["condiciones_impago"]} == {"MARCO_GENERAL_IMPAGO", "COMISION_FIJA_IMPAGO", "INTERES_DEMORA"}
    assert all(x["genera_movimiento"] is False for x in resumen["condiciones_impago"])
    assert all(c["estado"] == "OK" for c in factura["controles_conciliacion"])
    assert all(c["estado"] == "OK" for c in resultado.controles_conciliacion)


@pytest.mark.skipif(not PDF_MULTIFACTURA.exists(), reason="corpus externo FEDEFARMA multifactura no disponible")
def test_fedefarma_multifactura_completa_ciega_y_sin_contaminacion():
    resultado = MotorDocumentoLocal(BackendPdfium()).extraer(PDF_MULTIFACTURA)
    assert resultado.documento["sha256"] == SHA_MULTIFACTURA
    assert [(s.paginas, s.identidad_candidata) for s in resultado.segmentos] == [
        ([2, 2], "VN2605-0005656"), ([3, 3], "SI26-04567"), ([4, 4], "VN26-0016742"),
    ]
    assert [f["cabecera"]["numero_factura"]["valor"] for f in resultado.facturas] == [
        "VN2605-0005656", "SI26-04567", "VN26-0016742",
    ]
    mercancia, servicio_tecnico, cuota = resultado.facturas
    assert [f["segmento"]["paginas"] for f in resultado.facturas] == [[2, 2], [3, 3], [4, 4]]
    assert [len(f["albaranes"]) for f in resultado.facturas] == [5, 0, 0]
    assert [len(f["movimientos"]) for f in resultado.facturas] == [3, 1, 1]
    assert [len(f["impuestos"]) for f in resultado.facturas] == [5, 1, 1]
    assert [len(f["vencimientos"]) for f in resultado.facturas] == [1, 1, 1]
    assert mercancia["cabecera"]["importe_total"]["valor"] == 19.96
    assert servicio_tecnico["cabecera"]["importe_total"]["valor"] == 81.07
    assert cuota["cabecera"]["importe_total"]["valor"] == 308.55
    assert mercancia["cabecera"]["moneda"] is None
    assert mercancia["cabecera"]["codigo_farmacia"]["valor"] == "0500"
    assert servicio_tecnico["cabecera"]["moneda"]["valor"] == "EUR"
    assert cuota["cabecera"]["moneda"]["valor"] == "EUR"
    assert servicio_tecnico["cabecera"]["fecha_factura"]["valor"] == "2026-07-31"
    assert servicio_tecnico["cabecera"]["fecha_impresion"]["valor"] == "2026-08-04"
    assert servicio_tecnico["cabecera"]["fecha_factura"]["valor"] != servicio_tecnico["cabecera"]["fecha_impresion"]["valor"]
    assert mercancia["movimientos"][0]["detalle_documental"]["motivo"]["valor"] == "NI"
    assert mercancia["movimientos"][0]["detalle_documental"]["descripcion"]["valor"].endswith("DUOC")
    assert "-24,52" not in mercancia["movimientos"][0]["detalle_documental"]["descripcion"]["valor"]
    assert mercancia["movimientos"][0]["categoria"] == "DEVOLUCION_MERCANCIA"
    assert mercancia["movimientos"][0]["sentido"] is None
    assert mercancia["movimientos"][0]["detalle_documental"]["conclusion_categoria"] == "DEVOLUCION_MERCANCIA_DECISION_FUNCIONAL_PIO"
    assert mercancia["movimientos"][1]["categoria"] == "BONIFICACION"
    assert mercancia["movimientos"][1]["sentido"] is None
    assert all(f["impuestos"][0]["tipo_recargo_equivalencia"] is None for f in (servicio_tecnico, cuota))
    assert all(f["impuestos"][0]["cuota_recargo_equivalencia"] is None for f in (servicio_tecnico, cuota))
    assert all(f["impuestos"][0]["estado_recargo"]["valor"] == "SIN_RECARGO_CUALITATIVO" for f in (servicio_tecnico, cuota))
    assert servicio_tecnico["movimientos"][0]["categoria"] == "SERVICIO"
    assert cuota["movimientos"][0]["categoria"] == "CONDICION_COOPERATIVA"
    assert cuota["movimientos"][0]["concepto_normalizado"] == "CONDICION_COOPERATIVA"
    assert cuota["movimientos"][0]["sentido"] is None
    assert cuota["movimientos"][0]["base"]["valor"] == 255.0
    resumen = resultado.otros[0]
    assert [x["clasificacion_documental"]["valor"] for x in resumen["relacion_facturas"]] == ["NOR", "NVE", "NVE"]
    assert len(resumen["relacion_pagos"]) == 3
    assert all(m["sentido"] is None for f in resultado.facturas for m in f["movimientos"])
    assert all(c["estado"] == "OK" for f in resultado.facturas for c in f["controles_conciliacion"])
    assert all(c["estado"] == "OK" for c in resultado.controles_conciliacion)
    assert all(e.sha_documento == SHA_MULTIFACTURA for e in resultado.evidencias)


@pytest.mark.skipif(not PDF_DECENAL.exists() or not PDF_MULTIFACTURA.exists(), reason="corpus externo FEDEFARMA no disponible")
def test_tres_replays_de_todo_el_corpus_fedefarma_son_identicos_y_sin_red(monkeypatch):
    motor = MotorDocumentoLocal(BackendPdfium())
    esperados = {
        pdf: hash_funcional(motor.extraer(pdf))
        for pdf in (PDF_DECENAL, PDF_MULTIFACTURA)
    }
    for _ in range(2):
        assert {pdf: hash_funcional(motor.extraer(pdf)) for pdf in esperados} == esperados

    def red_bloqueada(*args, **kwargs):
        raise AssertionError("intento de red")

    monkeypatch.setattr(socket, "socket", red_bloqueada)
    monkeypatch.setattr(socket, "create_connection", red_bloqueada)
    monkeypatch.setattr(socket, "getaddrinfo", red_bloqueada)
    assert {pdf: hash_funcional(motor.extraer(pdf)) for pdf in esperados} == esperados


@pytest.mark.skipif(not PDF_MULTIFACTURA.exists(), reason="corpus externo FEDEFARMA no disponible")
def test_fedefarma_permanece_shadow_y_no_sustituye_salida_oficial():
    oficial = object()
    eventos = ObservabilidadMemoria([])
    salida = ejecutar_shadow_cofares_sobre_resultado(
        oficial, PDF_MULTIFACTURA, configuracion=ConfiguracionShadow(True),
        motor_local=MotorDocumentoLocal(BackendPdfium()), observabilidad=eventos,
    )
    assert salida is oficial
    assert len(eventos.eventos) == 1
    evento = eventos.eventos[0]
    assert evento["adaptador"] == "fedefarma-local"
    assert evento["autoridad_aplicada"] == "IA"
    assert evento["salida_local_aplicada"] is False
    assert evento["familias_locales"] == {
        "cabecera": True, "facturas": 3, "albaranes": 5,
        "movimientos": 5, "impuestos": 7, "vencimientos": 3, "otros": 8,
    }
    assert evento["comparacion"]["albaranes_local"] == 5
