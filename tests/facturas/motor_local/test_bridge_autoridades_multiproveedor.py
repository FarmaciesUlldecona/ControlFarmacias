from __future__ import annotations

from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.alliance import documentar_sentido_decision_funcional_pio
from src.facturas.motor_local.adaptadores.base import AdaptadorBase, Reconocimiento
from src.facturas.motor_local.adaptadores.registro import (
    adaptadores_locales,
    adaptadores_productivos,
    entradas_adaptadores_locales,
)
from src.facturas.motor_local.autoridad import (
    AUTORIDADES_EXTRACTORES_LOCALES,
    COFARES_LOCAL_AUTHORITY,
    autoridad_productiva_habilitada,
)
from src.facturas.motor_local.catalogo import (
    BackendLocalRequerido,
    PROVEEDORES_NO_IMPLEMENTADOS,
    ProveedorLocal,
)
from src.facturas.motor_local.configuracion import ConfiguracionShadow
from src.facturas.motor_local.gaps_funcionales import GAPS_FUNCIONALES_PENDIENTES
from src.facturas.motor_local.geometria.lineas import agrupar_por_linea
from src.facturas.motor_local.modelos import (
    DocumentoExtraidoLocal,
    DocumentoLocal,
    PaginaLocal,
    PalabraLocal,
    RegionLocal,
)
from src.facturas.motor_local.observabilidad import ObservabilidadMemoria
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.motor_local.shadow import (
    MotorShadowLocalAdaptativo,
    crear_motor_shadow_local,
    ejecutar_shadow_local_sobre_resultado,
)


class MotorResultado:
    def __init__(self, resultado):
        self.resultado = resultado

    def extraer(self, ruta):
        return self.resultado


class BackendDocumento:
    id = "backend-sintetico"
    version = "1"

    def __init__(self, documento):
        self.documento = documento

    def cargar_pdf(self, ruta):
        return self.documento


class AdaptadorReconocido(AdaptadorBase):
    version = "1"
    capacidades = {}

    def __init__(self, adapter_id):
        self.id = adapter_id

    def reconocer(self, documento):
        return Reconocimiento("RECONOCIDO", 100, [])

    def extraer_albaranes(self, documento, segmentos):
        return []


def _resultado(adapter_id: str | None) -> DocumentoExtraidoLocal:
    return DocumentoExtraidoLocal(
        documento={
            "sha256": "a" * 64,
            "source": "sintetico.pdf",
            "pages": 1,
            "layout": adapter_id,
            "layout_version": "1",
        },
        segmentos=[],
        facturas=[],
        cabecera={},
        albaranes=[],
        movimientos=[],
        impuestos=[],
        vencimientos=[],
        otros=[],
        controles_conciliacion=[],
        incidencias=[] if adapter_id else [{"codigo": "LAYOUT_NO_RECONOCIDO"}],
        evidencias=[],
        capacidades={},
        motor={"id": "motor-sintetico", "version": "1", "backend": "sintetico"},
    )


@pytest.mark.parametrize(
    "entrada",
    entradas_adaptadores_locales(),
    ids=lambda entrada: entrada.adapter_id,
)
def test_bridge_acepta_cada_adaptador_registrado_sin_aplicar_salida(tmp_path, entrada):
    ruta = tmp_path / "entrada.pdf"
    ruta.write_bytes(b"%PDF-sintetico")
    oficial = {"salida": "oficial"}
    eventos = ObservabilidadMemoria([])

    salida = ejecutar_shadow_local_sobre_resultado(
        oficial,
        ruta,
        configuracion=ConfiguracionShadow(True),
        motor_local=MotorResultado(_resultado(entrada.adapter_id)),
        observabilidad=eventos,
    )

    assert salida is oficial
    assert len(eventos.eventos) == 1
    evento = eventos.eventos[0]
    contrato = evento["contrato_bridge"]
    assert evento["adaptador"] == entrada.adapter_id
    assert evento["proveedor"] == entrada.proveedor.value
    assert evento["autoridad_aplicada"] == "IA"
    assert evento["salida_local_aplicada"] is False
    assert contrato["estado_registro"] == "REGISTRADO_LOCAL"
    assert contrato["shadow_habilitable"] is True
    assert contrato["estado_shadow"] == "SHADOW_HABILITADO"
    assert contrato["autoridad_productiva"] is False
    assert contrato["estado_autoridad"] == "AUTORIDAD_PRODUCTIVA_OFF"
    assert contrato["backend_requerido"] == entrada.backend_requerido.value
    assert contrato["provenance"]["filename_usado_en_routing"] is False


def test_autoridad_independiente_existe_y_esta_off_para_cada_proveedor():
    assert set(AUTORIDADES_EXTRACTORES_LOCALES) == set(ProveedorLocal)
    assert all(not autoridad.habilitada for autoridad in AUTORIDADES_EXTRACTORES_LOCALES.values())
    assert all(
        entrada.proveedor in AUTORIDADES_EXTRACTORES_LOCALES
        for entrada in entradas_adaptadores_locales()
    )
    assert AUTORIDADES_EXTRACTORES_LOCALES[ProveedorLocal.ALLIANCE] is not AUTORIDADES_EXTRACTORES_LOCALES[ProveedorLocal.COFARES]
    assert AUTORIDADES_EXTRACTORES_LOCALES[ProveedorLocal.HEFAME] is not AUTORIDADES_EXTRACTORES_LOCALES[ProveedorLocal.FEDEFARMA]


def test_cofares_legacy_mapea_solo_a_autoridad_cofares():
    assert COFARES_LOCAL_AUTHORITY is autoridad_productiva_habilitada(ProveedorLocal.COFARES)
    assert COFARES_LOCAL_AUTHORITY is False


def test_shadow_y_decision_pio_no_son_autoridad_productiva():
    decision = documentar_sentido_decision_funcional_pio("SERVICIO BASICO")
    assert decision["provenance"]["autoridad"] == "PIO"
    assert all(entrada.shadow_habilitable for entrada in entradas_adaptadores_locales())
    assert autoridad_productiva_habilitada(ProveedorLocal.ALLIANCE) is False


def test_registro_nuevo_preserva_orden_y_alias_legacy():
    nuevos = [(adaptador.id, adaptador.version) for adaptador in adaptadores_locales()]
    legacy = [(adaptador.id, adaptador.version) for adaptador in adaptadores_productivos()]
    assert nuevos == legacy
    assert len(nuevos) == 17


def test_configuracion_shadow_general_prevalece_y_legacy_sigue_admitida(monkeypatch):
    monkeypatch.delenv("CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW", raising=False)
    monkeypatch.delenv("CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW_COFARES", raising=False)
    assert ConfiguracionShadow.desde_entorno() == ConfiguracionShadow(False)

    monkeypatch.setenv("CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW_COFARES", "true")
    historica = ConfiguracionShadow.desde_entorno()
    assert historica.habilitado is True
    assert historica.variable_origen == "CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW_COFARES"

    monkeypatch.setenv("CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW", "false")
    general = ConfiguracionShadow.desde_entorno()
    assert general.habilitado is False
    assert general.variable_origen == "CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW"


def test_backend_shadow_es_adaptativo_y_guimera_declara_ocr_local():
    motor = crear_motor_shadow_local()
    assert motor.motor_nativo.backend.id == "pypdfium2"
    assert motor._motor_ocr is None
    guimera = [e for e in entradas_adaptadores_locales() if e.proveedor == ProveedorLocal.GUIMERA]
    assert len(guimera) == 2
    assert all(e.backend_requerido == BackendLocalRequerido.PDFIUM_CON_OCR_LOCAL for e in guimera)
    assert all(
        e.backend_requerido == BackendLocalRequerido.PDFIUM_NATIVO
        for e in entradas_adaptadores_locales()
        if e.proveedor != ProveedorLocal.GUIMERA
    )


def test_backend_adaptativo_solo_reintenta_ocr_ante_pendiente_ocr():
    pendiente = _resultado(None)
    pendiente.incidencias = [{"codigo": "PENDIENTE_OCR"}]
    reconocido = _resultado("farmacia-guimera-ocr-local")
    llamadas = []

    def fabricar_ocr():
        llamadas.append("OCR")
        return MotorResultado(reconocido)

    motor = MotorShadowLocalAdaptativo(MotorResultado(pendiente), fabricar_ocr)
    assert motor.extraer("sintetico.pdf") is reconocido
    assert llamadas == ["OCR"]
    assert motor.extraer("sintetico.pdf") is reconocido
    assert llamadas == ["OCR"]


def test_sin_adaptador_no_crashea_no_aplica_y_registra_no_implementado(tmp_path):
    ruta = tmp_path / "desconocido.pdf"
    ruta.write_bytes(b"%PDF-sintetico")
    oficial = object()
    eventos = ObservabilidadMemoria([])
    salida = ejecutar_shadow_local_sobre_resultado(
        oficial,
        ruta,
        configuracion=ConfiguracionShadow(True),
        motor_local=MotorResultado(_resultado(None)),
        observabilidad=eventos,
    )
    assert salida is oficial
    assert eventos.eventos[0]["contrato_bridge"]["estado_registro"] == "SIN_ADAPTADOR_REGISTRADO"
    assert eventos.eventos[0]["salida_local_aplicada"] is False
    assert PROVEEDORES_NO_IMPLEMENTADOS == ("SAFA", "BEIERSDORF")


def test_empate_de_reconocimiento_sigue_siendo_ambiguo():
    palabra = PalabraLocal("FACTURA", 1, RegionLocal(0, 0, 20, 10), 0)
    documento = DocumentoLocal(
        "sintetico.pdf",
        "b" * 64,
        [PaginaLocal(1, 100, 100, "FACTURA", [palabra], agrupar_por_linea([palabra]))],
    )
    motor = MotorDocumentoLocal(
        BackendDocumento(documento),
        (AdaptadorReconocido("uno"), AdaptadorReconocido("dos")),
    )
    resultado = motor.extraer(Path("nombre-no-usado-para-routing.pdf"))
    assert resultado.documento["layout"] is None
    assert resultado.incidencias == [{"codigo": "LAYOUT_AMBIGUO", "estado": "AMBIGUO"}]


def test_gaps_funcionales_quedan_registrados_sin_regla_nueva():
    assert [(gap.proveedor, gap.estado) for gap in GAPS_FUNCIONALES_PENDIENTES] == [
        (ProveedorLocal.COFARES, "GAP_FUNCIONAL_PENDIENTE"),
        (ProveedorLocal.DERMOFARM, "GAP_FUNCIONAL_PENDIENTE"),
    ]
