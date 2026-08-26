from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.cofares import AdaptadorCofares
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.coordinador_documento import crear_plan_autoridad_cofares, simular_plan_cofares
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.normalizador_v2.consolidacion_representaciones import (
    EstadoEquivalencia, RepresentacionFactura, consolidar_representaciones,
    evaluar_equivalencia,
)
from src.facturas.normalizador_v2.modelos import (
    DocumentoNormalizado, EstadoValidacion, Evidencia, FacturaNormalizada,
    FechaDocumental, NaturalezaPrincipal, ResultadoControl, ResultadoValidacion,
    Tercero, Totales, ValorDocumentado,
)


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "pruebas/facturas/resultados/normalizador_v2_end_to_end_2o_gold_corregido"
DOC = BASE / "por_pdf/documento_02.json"
PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/COFARES VTO 30.8.26 PIO.pdf"
SHA = "e28f2bde78eaa51c9e04827245a15f117dc21c0d583709e9985d07bd2fc5fc52"


def _vd(valor, literal=None, pagina=1, ubicacion=None):
    literal = str(valor) if literal is None else literal
    return ValorDocumentado(valor=valor, literal=literal, evidencia=[Evidencia(pagina=pagina, literal=literal, ubicacion=ubicacion)])


def _factura_sintetica(*, factura_id: str, proveedor: Tercero | None) -> FacturaNormalizada:
    return FacturaNormalizada(
        factura_id=factura_id,
        naturaleza_principal=NaturalezaPrincipal.MERCANCIA,
        estado_validacion=EstadoValidacion.VALIDADA,
        requiere_conciliacion_albaranes=True,
        pagina_inicio=1,
        pagina_fin=1,
        proveedor=proveedor,
        destinatario=Tercero(nombre=_vd("DESTINATARIO SINTETICO"), nif=_vd("B00000000")),
        numero_factura=_vd("F-SINTETICA-001"),
        fecha_factura=_vd(FechaDocumental(literal="01-08-2026", iso=None)),
        totales=Totales(total=_vd(Decimal("100.00"))),
        validaciones=[ResultadoValidacion(
            codigo="SINTETICO", resultado=ResultadoControl.OK, descripcion="fixture estructural",
            regla_version="test",
        )],
    )


def _reps():
    proveedor = Tercero(nombre=_vd("PROVEEDOR SINTETICO"), nif=_vd("A00000000"))
    primaria = _factura_sintetica(factura_id="primaria", proveedor=proveedor)
    segmento = _factura_sintetica(factura_id="segmento", proveedor=None)
    return [
        RepresentacionFactura(primaria, "lectura_primaria", SHA),
        RepresentacionFactura(segmento, "segmento_01", SHA, "segmento_01"),
    ]


def _reps_reales():
    documento = DocumentoNormalizado.model_validate_json(DOC.read_text(encoding="utf-8"))
    return documento, [
        RepresentacionFactura(documento.facturas[0], "lectura_primaria", SHA),
        RepresentacionFactura(documento.facturas[1], "segmento_01", SHA, "segmento_01"),
    ]


def test_caso_real_es_misma_factura_y_consolida_dos_a_una_sin_perder_evidencia():
    reps = _reps()
    eq = evaluar_equivalencia(*reps)
    assert eq.estado == EstadoEquivalencia.MISMA_FACTURA_DEMOSTRADA
    assert {"source_sha", "numero_factura", "paginas_solapadas", "fecha_factura", "importe_total"} <= set(eq.anclas_compartidas)
    resultado = consolidar_representaciones(reps)
    assert len(resultado.facturas) == 1 and resultado.consolidadas == 1 and not resultado.conflictos
    factura = resultado.facturas[0]
    assert factura.proveedor.nif.valor == "A00000000" and factura.destinatario.nif.valor == "B00000000"
    assert any(i.codigo == "REPRESENTACIONES_CONSOLIDADAS" and not i.bloqueante for i in factura.incidencias)
    origenes_total = {o for e in factura.totales.total.evidencia for o in e.ubicacion["procedencias_representacion"]}
    assert origenes_total == {"lectura_primaria", "segmento_01"}


def test_sha_distinto_paginas_no_solapadas_fecha_y_total_conflictivos_no_consolidan():
    a, b = _reps()
    assert evaluar_equivalencia(a, RepresentacionFactura(b.factura, b.origen, "otro-sha")).estado == EstadoEquivalencia.FACTURAS_DISTINTAS_DEMOSTRADAS
    pagina_dos = b.factura.model_copy(update={"pagina_inicio": 2, "pagina_fin": 2})
    assert evaluar_equivalencia(a, RepresentacionFactura(pagina_dos, b.origen, SHA)).estado == EstadoEquivalencia.FACTURAS_DISTINTAS_DEMOSTRADAS
    fecha = b.factura.model_copy(update={"fecha_factura": _vd(FechaDocumental(literal="30.07.2026", iso=None))})
    assert evaluar_equivalencia(a, RepresentacionFactura(fecha, b.origen, SHA)).estado == EstadoEquivalencia.CONFLICTO_DOCUMENTAL
    totales = b.factura.totales.model_copy(update={"total": _vd(Decimal("999.00"))})
    total = b.factura.model_copy(update={"totales": totales})
    assert evaluar_equivalencia(a, RepresentacionFactura(total, b.origen, SHA)).estado == EstadoEquivalencia.CONFLICTO_DOCUMENTAL


def test_proveedor_null_es_compatible_pero_dos_proveedores_documentados_distintos_conflictuan():
    a, b = _reps()
    assert b.factura.proveedor is None
    assert evaluar_equivalencia(a, b).estado == EstadoEquivalencia.MISMA_FACTURA_DEMOSTRADA
    otro = b.factura.model_copy(update={"proveedor": Tercero(nombre=_vd("OTRO"), nif=_vd("B00000000"))})
    assert evaluar_equivalencia(a, RepresentacionFactura(otro, b.origen, SHA)).estado == EstadoEquivalencia.CONFLICTO_DOCUMENTAL


def test_tres_representaciones_forman_un_grupo_y_evidencia_insuficiente_no_fusiona():
    reps = _reps()
    tercera = RepresentacionFactura(reps[0].factura.model_copy(update={"factura_id": "tercera"}), "segmento_02", SHA)
    resultado = consolidar_representaciones([*reps, tercera])
    assert len(resultado.facturas) == 1 and resultado.consolidadas == 2
    incompleta = reps[1].factura.model_copy(update={"fecha_factura": None, "totales": reps[1].factura.totales.model_copy(update={"total": None})})
    eq = evaluar_equivalencia(reps[0], RepresentacionFactura(incompleta, "incompleta", SHA))
    assert eq.estado == EstadoEquivalencia.EQUIVALENCIA_INSUFICIENTE
    assert len(consolidar_representaciones([reps[0], RepresentacionFactura(incompleta, "incompleta", SHA)]).facturas) == 2


@pytest.mark.skipif(not (PDF.exists() and DOC.exists()), reason="corpus externo COFARES no disponible")
def test_post_consolidacion_match_unico_y_simulacion_39_sin_activar_autoridad():
    pipeline, reps = _reps_reales()
    consolidada = consolidar_representaciones(reps).facturas[0]
    doc = pipeline.model_copy(update={"facturas": [consolidada]})
    backend = BackendPdfium(); local_doc = backend.cargar_pdf(PDF); local = MotorDocumentoLocal(backend).extraer(PDF); rec = AdaptadorCofares().reconocer(local_doc)
    plan = crear_plan_autoridad_cofares(doc, local_doc, local, rec)
    assert plan.estado_match == "MATCH_UNICO" and plan.estado_plan == "LISTO_SIMULACION"
    sim = simular_plan_cofares(doc, local_doc, local, rec)
    assert sim.aplicada and len(sim.documento.facturas[0].albaranes) == 39
    assert sim.documento.facturas[0].proveedor == consolidada.proveedor
    assert sim.documento.facturas[0].movimientos_comerciales == consolidada.movimientos_comerciales
    assert sim.documento.facturas[0].impuestos == consolidada.impuestos
    assert sim.documento.facturas[0].vencimientos == consolidada.vencimientos
