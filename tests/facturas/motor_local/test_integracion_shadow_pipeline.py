from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.motor_local.autoridad import AutoridadExtraccion, COFARES_LOCAL_AUTHORITY, autoridad_cofares
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.configuracion import ConfiguracionShadow
from src.facturas.motor_local.observabilidad import ObservabilidadMemoria
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.normalizador_v2.adaptador_luna import MetadataLuna, ResultadoLuna
from src.facturas.normalizador_v2.pipeline import normalizar_pdf


ROOT = Path(__file__).resolve().parents[3]
PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/COFARES VTO 30.8.26 PIO.pdf"


class LectorVacio:
    def extraer(self, ruta):
        return ResultadoLuna((), MetadataLuna("offline", "gpt-5.6-luna", "gpt-5.6-luna", 0, 0, 0, Decimal("0"), 0))


def _ahora():
    return datetime(2026, 8, 21, tzinfo=timezone.utc)


def test_autoridad_local_cofares_esta_preparada_pero_off():
    assert COFARES_LOCAL_AUTHORITY is False
    assert autoridad_cofares(salida_oficial_disponible=True) == AutoridadExtraccion.IA


@pytest.mark.skipif(not PDF.exists(), reason="PDF COFARES local no disponible")
def test_pipeline_real_shadow_on_genera_39_y_no_modifica_salida_oficial():
    eventos = ObservabilidadMemoria([])
    documento = normalizar_pdf(
        PDF, lector_luna=LectorVacio(), ahora=_ahora,
        configuracion_shadow_local=ConfiguracionShadow(True),
        motor_shadow_local=MotorDocumentoLocal(BackendPdfium()), sink_shadow_local=eventos,
    )
    assert documento.facturas == []
    evento = eventos.eventos[0]
    assert evento["candidatos"] == 39
    assert evento["comparacion"]["albaranes_pipeline"] == 0
    assert evento["comparacion"]["albaranes_local"] == 39
    assert evento["comparacion"]["resumen"]["SOLO_LOCAL"] == 39
    assert evento["salida_local_aplicada"] is False
    assert evento["autoridad_aplicada"] == "IA"


@pytest.mark.skipif(not PDF.exists(), reason="PDF COFARES local no disponible")
def test_pipeline_real_shadow_off_no_emite_evento():
    eventos = ObservabilidadMemoria([])
    documento = normalizar_pdf(
        PDF, lector_luna=LectorVacio(), ahora=_ahora,
        configuracion_shadow_local=ConfiguracionShadow(False), sink_shadow_local=eventos,
    )
    assert documento.facturas == []
    assert eventos.eventos == []
