from __future__ import annotations

import copy
from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.cofares import AdaptadorCofares
from src.facturas.motor_local.autoridad import COFARES_LOCAL_AUTHORITY, EstadoElegibilidad, evaluar_elegibilidad_cofares
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.puente_cofares import adaptar_albaranes_cofares, ensamblar_factura_cofares
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.normalizador_v2.modelos import FacturaNormalizada


ROOT = Path(__file__).resolve().parents[3]
PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/COFARES VTO 30.8.26 PIO.pdf"
FACTURA = ROOT / "pruebas/facturas/resultados/normalizador_v2_end_to_end_2o_gold_corregido/por_factura/documento_02_factura_01.json"
CORPUS_DISPONIBLE = PDF.exists() and FACTURA.exists()


def _cargar():
    backend = BackendPdfium()
    documento = backend.cargar_pdf(PDF)
    resultado = MotorDocumentoLocal(backend).extraer(PDF)
    reconocimiento = AdaptadorCofares().reconocer(documento)
    return documento, resultado, reconocimiento


def _factura():
    return FacturaNormalizada.model_validate_json(FACTURA.read_text(encoding="utf-8"))


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_reconocimiento_inequivoco_y_capacidades_honestas():
    documento, resultado, reconocimiento = _cargar()
    assert reconocimiento.estado == "RECONOCIDO" and reconocimiento.puntuacion == 100
    assert all(item["presente"] for item in reconocimiento.evidencias)
    assert resultado.capacidades == {
        "segmentacion": "SOPORTADO_MONOPAGINA_MULTILAYOUT",
        "cabecera": "SOPORTADO_NULLS_DOCUMENTALES",
        "albaranes": "SOPORTADO",
        "movimientos": "SOPORTADO_SENTIDO_DOCUMENTAL_O_DECISION_PIO_O_NULL",
        "impuestos": "SOPORTADO_TIPOS_IMPRESOS",
        "vencimientos": "SOPORTADO_OCURRENCIAS_DOCUMENTALES",
        "otros": "SOPORTADO",
        "conciliacion_documental": "SOPORTADO",
    }
    assert evaluar_elegibilidad_cofares(documento, resultado, reconocimiento).estado == EstadoElegibilidad.ELEGIBLE


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_adaptacion_39_preserva_evidencia_sha_bbox_bases_y_sentido_null():
    documento, resultado, _ = _cargar()
    albaranes, incidencias = adaptar_albaranes_cofares(resultado)
    assert len(albaranes) == len(incidencias) == 39
    assert all(a.sentido is None for a in albaranes)
    assert all(i.codigo == "SENTIDO_NO_DOCUMENTADO" and not i.bloqueante for i in incidencias)
    for original, adaptado in zip(resultado.albaranes, albaranes, strict=True):
        ubicacion = adaptado.numero.evidencia[0].ubicacion
        assert ubicacion["sha_documento"] == documento.sha_documento
        assert ubicacion["bbox"] and ubicacion["fila_literal"]
        assert ubicacion["adaptador"] == "cofares-local" and ubicacion["version_adaptador"] == "2.1.0"
        assert adaptado.importe_base.evidencia[0].ubicacion["bases_componentes"] == original.bases


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_bandera_off_devuelve_misma_factura_y_simulacion_reemplaza_sin_duplicar():
    documento, resultado, reconocimiento = _cargar()
    oficial = _factura()
    assert COFARES_LOCAL_AUTHORITY is False
    apagado = ensamblar_factura_cofares(oficial, documento, resultado, reconocimiento)
    assert apagado.factura is oficial and not apagado.aplicada and apagado.razon == "BANDERA_AUTORIDAD_OFF"
    dummy = adaptar_albaranes_cofares(resultado)[0][0]
    oficial_con_ia = oficial.model_copy(update={"albaranes": [dummy]})
    simulado = ensamblar_factura_cofares(oficial_con_ia, documento, resultado, reconocimiento, simular=True)
    assert simulado.aplicada and simulado.autoridad_albaranes == "LOCAL"
    assert len(simulado.factura.albaranes) == 39
    assert simulado.factura.movimientos_comerciales == oficial.movimientos_comerciales
    assert simulado.factura.impuestos == oficial.impuestos
    assert simulado.factura.vencimientos == oficial.vencimientos
    assert simulado.trazabilidad["salida_local_aplicada"] is True


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_negativos_reconocimiento_y_layout_nuevo():
    documento, resultado, _ = _cargar()
    sin_cofares = copy.deepcopy(documento)
    sin_cofares.paginas[0].texto = "FACTURA DE OTRO PROVEEDOR"
    assert AdaptadorCofares().reconocer(sin_cofares).estado == "NO_RECONOCIDO"
    solo_nombre = copy.deepcopy(documento)
    solo_nombre.paginas[0].texto = "Grupo COFARES documento informativo"
    assert AdaptadorCofares().reconocer(solo_nombre).estado == "AMBIGUO"
    sin_cabecera = copy.deepcopy(documento)
    sin_cabecera.paginas[0].texto = sin_cabecera.paginas[0].texto.replace("Nº Albarán", "Referencia")
    rec = AdaptadorCofares().reconocer(sin_cabecera)
    assert rec.estado == "AMBIGUO"
    cambiado = copy.deepcopy(resultado)
    cambiado.documento["layout"] = "cofares-local-futuro"
    elegibilidad = evaluar_elegibilidad_cofares(documento, cambiado, AdaptadorCofares().reconocer(documento))
    assert elegibilidad.estado == EstadoElegibilidad.LOCAL_NO_APLICABLE
    assert "LAYOUT_NO_COMPATIBLE" in elegibilidad.razones


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_negativos_fila_incompleta_columnas_ambiguas_cero_filas_y_multipagina():
    documento, resultado, reconocimiento = _cargar()
    incompleto = copy.deepcopy(resultado)
    incompleto.albaranes[0].total = None
    assert any("INCOMPLETA" in r for r in evaluar_elegibilidad_cofares(documento, incompleto, reconocimiento).razones)
    ambiguo = copy.deepcopy(resultado)
    ambiguo.albaranes[0].evidencias["base"].bbox[0] = 1.0
    assert any("COLUMNAS_AMBIGUAS" in r for r in evaluar_elegibilidad_cofares(documento, ambiguo, reconocimiento).razones)
    vacio = copy.deepcopy(resultado)
    vacio.albaranes = []
    assert "SIN_FILAS_EXTRAIDAS" in evaluar_elegibilidad_cofares(documento, vacio, reconocimiento).razones
    multipagina = copy.deepcopy(documento)
    segunda = copy.deepcopy(multipagina.paginas[0]); segunda.numero = 2; multipagina.paginas.append(segunda)
    assert AdaptadorCofares().reconocer(multipagina).estado == "AMBIGUO"


def test_salida_json_canonica_es_sentido_y_entrada_historica_sigue_admitida():
    from src.facturas.normalizador_v2.modelos import AlbaranDocumental, Evidencia, Sentido, ValorDocumentado
    numero = ValorDocumentado(valor="A1", literal="A1", evidencia=[Evidencia(pagina=1, literal="A1")])
    actual = AlbaranDocumental(orden=1, numero=numero, sentido=Sentido.CARGO)
    historico = AlbaranDocumental.model_validate({"orden": 1, "numero": numero.model_dump(), "tipo_movimiento": "ABONO"})
    assert actual.model_dump(mode="json")["sentido"] == "CARGO"
    assert "tipo_movimiento" not in actual.model_dump(mode="json")
    assert historico.sentido == Sentido.ABONO
