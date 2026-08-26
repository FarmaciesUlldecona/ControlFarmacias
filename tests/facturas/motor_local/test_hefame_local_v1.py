from __future__ import annotations

import socket
from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.hefame import AdaptadorHefame
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.geometria.lineas import agrupar_por_linea
from src.facturas.motor_local.modelos import DocumentoLocal, PaginaLocal, PalabraLocal, RegionLocal
from src.facturas.motor_local.servicio import MotorDocumentoLocal, hash_funcional
from src.facturas.motor_local.configuracion import ConfiguracionShadow
from src.facturas.motor_local.observabilidad import ObservabilidadMemoria
from src.facturas.motor_local.shadow import ejecutar_shadow_cofares_sobre_resultado


ROOT = Path(__file__).resolve().parents[3]
PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/HEFAME VTO 5.8.26 PIO.pdf"
SHA = "4e66185426265ae5a000b5268557271a2a589af9701ec14d533fcb0bd939c4e7"


def _documento_reconocible() -> DocumentoLocal:
    texto = (
        "HDAD.FMCTCA.MEDIT.,S.C.L. CIF: F30004444 RELACIÓN ALBARANES/DOC.ENTREGA "
        "BASE S.R. BASE RE. BASE NO. TOTAL BASES DESGLOSE IMPORTES TOTAL FACTURA "
        "RESUMEN DE VENCIMIENTOS PÁGINA 1 / 1"
    )
    palabra = PalabraLocal(texto, 1, RegionLocal(10, 10, 580, 20), 1)
    pagina = PaginaLocal(1, 595, 842, texto, [palabra], agrupar_por_linea([palabra]))
    return DocumentoLocal("sintetico.pdf", "a" * 64, [pagina])


def test_reconocimiento_hefame_exige_identidad_y_estructura_documental():
    adaptador = AdaptadorHefame()
    assert adaptador.reconocer(_documento_reconocible()).estado == "RECONOCIDO"
    documento = _documento_reconocible()
    documento.paginas[0].texto = documento.paginas[0].texto.replace("RESUMEN DE VENCIMIENTOS", "")
    assert adaptador.reconocer(documento).estado == "AMBIGUO"


@pytest.mark.skipif(not PDF.exists(), reason="corpus externo HEFAME no disponible")
def test_replay_hefame_completo_ciego():
    resultado = MotorDocumentoLocal(BackendPdfium()).extraer(PDF)
    assert resultado.documento["sha256"] == SHA
    assert resultado.documento["layout"] == "hefame-local"
    assert len(resultado.segmentos) == 1
    assert resultado.segmentos[0].paginas == [1, 2]
    assert resultado.segmentos[0].identidad_candidata == "0563820041"
    assert resultado.cabecera["numero_factura"]["valor"] == "0563820041"
    assert resultado.cabecera["fecha_factura"]["valor"] == "2026-07-31"
    assert resultado.cabecera["importe_total"]["valor"] == 677.99
    assert resultado.cabecera["base_imponible_total"]["valor"] == 594.64
    assert resultado.cabecera["iva_total"]["valor"] == 72.98
    assert resultado.cabecera["recargo_equivalencia_total"]["valor"] == 10.37
    assert resultado.cabecera["moneda"] is None
    assert len(resultado.albaranes) == 12
    assert all(item.sentido is None and item.rol_fila == "DETALLE_ALBARAN" for item in resultado.albaranes)
    assert len(resultado.movimientos) == 3
    assert all(item["sentido"] is None for item in resultado.movimientos)
    movimientos = {item["concepto_normalizado"]: item for item in resultado.movimientos}
    assert movimientos["ABONO_DEVOLUCION"]["categoria"] == "DEVOLUCION_MERCANCIA"
    assert movimientos["ABONO_DEVOLUCION"]["sentido"] is None
    assert movimientos["APROAFA"]["categoria"] == "CONDICION_COMERCIAL"
    assert movimientos["APROAFA"]["sentido"] is None
    assert len(resultado.impuestos) == 4
    assert all(item["control_aritmetico"] == "OK" for item in resultado.impuestos)
    assert len(resultado.vencimientos) == 1
    assert resultado.vencimientos[0]["importe"]["valor"] == 677.99
    assert len(resultado.otros) == 4
    controles = {item["id"]: item for item in resultado.controles_conciliacion}
    assert controles["PEDIDOS_DESDE_DETALLE"]["estado"] == "DIFERENCIA_DOCUMENTAL"
    assert controles["PEDIDOS_DESDE_DETALLE"]["valor_reconstruido"] == 404.64
    assert controles["PEDIDOS_DESDE_DETALLE"]["diferencia"] == 80.0
    assert controles["PEDIDOS_DESDE_DETALLE"]["concepto_origen"] is None
    assert controles["PEDIDOS_DESDE_DETALLE"]["columnas"]["BASE_S_R"]["diferencia"] == 80.0
    assert controles["PEDIDOS_DESDE_DETALLE"]["columnas"]["BASE_RE"]["diferencia"] == 0.0
    assert controles["PEDIDOS_DESDE_DETALLE"]["columnas"]["BASE_NO"]["diferencia"] == 0.0
    assert controles["BASE_IMPONIBLE_DESDE_BLOQUES"]["estado"] == "OK"
    assert controles["TOTAL_FACTURA_DESDE_FISCALIDAD"]["estado"] == "OK"
    assert controles["VENCIMIENTO_DESDE_TOTAL_FACTURA"]["estado"] == "OK"
    assert not any(item.get("importe", {}).get("valor") == 80.0 for item in resultado.movimientos)
    assert resultado.evidencias


@pytest.mark.skipif(not PDF.exists(), reason="corpus externo HEFAME no disponible")
def test_tres_replays_hefame_son_funcionalmente_identicos_y_sin_red(monkeypatch):
    motor = MotorDocumentoLocal(BackendPdfium())
    hashes = [hash_funcional(motor.extraer(PDF)) for _ in range(3)]
    assert len(set(hashes)) == 1

    def red_bloqueada(*args, **kwargs):
        raise AssertionError("intento de red")

    monkeypatch.setattr(socket, "socket", red_bloqueada)
    monkeypatch.setattr(socket, "create_connection", red_bloqueada)
    monkeypatch.setattr(socket, "getaddrinfo", red_bloqueada)
    assert hash_funcional(motor.extraer(PDF)) == hashes[0]


@pytest.mark.skipif(not PDF.exists(), reason="corpus externo HEFAME no disponible")
def test_hefame_solo_observa_en_shadow_y_no_sustituye_salida_oficial():
    oficial = object()
    eventos = ObservabilidadMemoria([])
    salida = ejecutar_shadow_cofares_sobre_resultado(
        oficial, PDF, configuracion=ConfiguracionShadow(True),
        motor_local=MotorDocumentoLocal(BackendPdfium()), observabilidad=eventos,
    )
    assert salida is oficial
    assert len(eventos.eventos) == 1
    evento = eventos.eventos[0]
    assert evento["adaptador"] == "hefame-local"
    assert evento["autoridad_aplicada"] == "IA"
    assert evento["salida_local_aplicada"] is False
    assert evento["familias_locales"] == {
        "cabecera": True, "albaranes": 12, "movimientos": 3,
        "impuestos": 4, "vencimientos": 1, "otros": 4,
    }
