from __future__ import annotations

import copy
from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.cofares import AdaptadorCofares
from src.facturas.motor_local.autoridad import COFARES_LOCAL_AUTHORITY
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.coordinador_documento import (
    ClaveFacturaDocumental, EstadoIdentidad, EstadoMatch, clave_local_cofares,
    crear_plan_autoridad_cofares, emparejar_factura, simular_plan_cofares,
)
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.normalizador_v2.modelos import DocumentoNormalizado, Evidencia, FechaDocumental, Tercero, ValorDocumentado


ROOT = Path(__file__).resolve().parents[3]
PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/COFARES VTO 30.8.26 PIO.pdf"
DOC = ROOT / "pruebas/facturas/resultados/normalizador_v2_end_to_end_2o_gold_corregido/por_pdf/documento_02.json"
CORPUS_DISPONIBLE = PDF.exists() and DOC.exists()


def _contexto():
    backend = BackendPdfium()
    local_doc = backend.cargar_pdf(PDF)
    resultado = MotorDocumentoLocal(backend).extraer(PDF)
    reconocimiento = AdaptadorCofares().reconocer(local_doc)
    pipeline = DocumentoNormalizado.model_validate_json(DOC.read_text(encoding="utf-8"))
    return local_doc, resultado, reconocimiento, pipeline


def _clave(numero="5450053457", **kwargs):
    evidencias = {"numero_factura": ({"literal": f"FACTURA {numero}"},)} if numero else {}
    for campo, valor in kwargs.items():
        if valor is not None:
            evidencias[campo] = ({"literal": str(valor)},)
    return ClaveFacturaDocumental(numero_factura=numero, evidencias=evidencias, **kwargs)


def _vd(valor):
    return ValorDocumentado(valor=valor, literal=str(valor), evidencia=[Evidencia(pagina=1, literal=str(valor))])


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_clave_local_documental_y_caso_real_son_multiples_match():
    local_doc, resultado, reconocimiento, pipeline = _contexto()
    clave = clave_local_cofares(resultado)
    assert clave.estado == EstadoIdentidad.IDENTIDAD_UNICA
    assert clave.numero_factura == "5450053457" and clave.paginas == (1, 1)
    match = emparejar_factura(clave, pipeline)
    assert match.estado == EstadoMatch.MULTIPLES_MATCH
    assert len(match.candidatos_compatibles) == 2 and match.factura_destino_id is None
    plan = crear_plan_autoridad_cofares(pipeline, local_doc, resultado, reconocimiento)
    assert plan.estado_plan == "LOCAL_NO_APLICABLE" and plan.factura_destino is None
    simulado = simular_plan_cofares(pipeline, local_doc, resultado, reconocimiento)
    assert not simulado.aplicada and simulado.documento is pipeline


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_documento_con_una_identidad_exacta_produce_match_y_simulacion_sin_concatenar():
    local_doc, resultado, reconocimiento, pipeline = _contexto()
    unico = pipeline.model_copy(update={"facturas": [pipeline.facturas[0]]})
    match = emparejar_factura(clave_local_cofares(resultado), unico)
    assert match.estado == EstadoMatch.MATCH_UNICO
    simulado = simular_plan_cofares(unico, local_doc, resultado, reconocimiento)
    assert simulado.aplicada and len(simulado.documento.facturas) == 1
    assert len(simulado.documento.facturas[0].albaranes) == 39
    assert simulado.documento.facturas[0].movimientos_comerciales == unico.facturas[0].movimientos_comerciales
    assert COFARES_LOCAL_AUTHORITY is False


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_duplicados_solo_se_desambiguan_con_ancla_documental_presente_en_ambos_lados():
    _, _, _, pipeline = _contexto()
    base = pipeline.facturas[0]
    proveedor_b = Tercero(nombre=_vd("OTRO"), nif=_vd("B00000000"))
    distinta = base.model_copy(update={"factura_id": "otra", "proveedor": proveedor_b})
    doc = pipeline.model_copy(update={"facturas": [base, distinta]})
    local = _clave(proveedor_nif="A80904576")
    assert emparejar_factura(local, doc).estado == EstadoMatch.MATCH_UNICO
    sin_proveedor = _clave()
    assert emparejar_factura(sin_proveedor, doc).estado == EstadoMatch.MULTIPLES_MATCH
    sin_evidencia = ClaveFacturaDocumental(
        numero_factura="5450053457", proveedor_nif="A80904576",
        evidencias={"numero_factura": ({"literal": "FACTURA 5450053457"},)},
    )
    assert emparejar_factura(sin_evidencia, doc).estado == EstadoMatch.MULTIPLES_MATCH


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_fecha_documental_puede_desambiguar_pero_fecha_local_ausente_no():
    _, _, _, pipeline = _contexto()
    base = pipeline.facturas[0]
    otra_fecha = _vd(FechaDocumental(literal="30.07.2026", iso=None))
    distinta = base.model_copy(update={"factura_id": "otra_fecha", "fecha_factura": otra_fecha})
    doc = pipeline.model_copy(update={"facturas": [base, distinta]})
    assert emparejar_factura(_clave(fecha_factura="2026-07-31"), doc).estado == EstadoMatch.MATCH_UNICO
    assert emparejar_factura(_clave(), doc).estado == EstadoMatch.MULTIPLES_MATCH


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_identidad_igual_insuficiente_conflictiva_y_sin_match_bloquean():
    _, resultado, _, pipeline = _contexto()
    base = pipeline.facturas[0]
    duplicada = base.model_copy(update={"factura_id": "duplicada"})
    doc_duplicado = pipeline.model_copy(update={"facturas": [base, duplicada]})
    assert emparejar_factura(_clave(proveedor_nif="A80904576", fecha_factura="2026-07-31"), doc_duplicado).estado == EstadoMatch.MULTIPLES_MATCH
    assert emparejar_factura(_clave(numero=None), pipeline).estado == EstadoMatch.IDENTIDAD_INSUFICIENTE
    doc_unico = pipeline.model_copy(update={"facturas": [base]})
    assert emparejar_factura(_clave(proveedor_nif="B00000000"), doc_unico).estado == EstadoMatch.CONFLICTO
    assert emparejar_factura(_clave(numero="NO-EXISTE"), doc_unico).estado == EstadoMatch.SIN_MATCH
    resultado_sin_numero = copy.deepcopy(resultado)
    resultado_sin_numero.segmentos[0].identidad_candidata = None
    assert clave_local_cofares(resultado_sin_numero).estado == EstadoIdentidad.IDENTIDAD_INSUFICIENTE


@pytest.mark.skipif(not CORPUS_DISPONIBLE, reason="corpus externo COFARES no disponible")
def test_plan_registra_trazabilidad_sin_seleccion_por_posicion():
    local_doc, resultado, reconocimiento, pipeline = _contexto()
    plan = crear_plan_autoridad_cofares(pipeline, local_doc, resultado, reconocimiento)
    assert plan.candidatos_encontrados == 2
    assert plan.sha_documento == resultado.documento["sha256"]
    assert plan.paginas_segmento == (1, 1)
    assert plan.evidencia_identidad["numero_factura"]
    assert plan.incidencias == ("MATCH_MULTIPLES_MATCH",)
