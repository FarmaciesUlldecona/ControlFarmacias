"""Compositor productivo de la ruta AUTOMATICA (Hito AUTO-A, decision D1 de Pio, 2026-11-12).

Autoridad de extraccion SOLO para Alliance y SOLO en su version certificada (``alliance-local`` 1.3.1, con el puente
multifactura certificado; DECISION DE PIO, 2026-11-14: R10 ampliada con "ENCARGO", banco Alliance 1.3.0 frente a
1.3.1 sin otras diferencias). Reutiliza las piezas del compositor manual del 2AP (Storage privado, PDF verificado,
motor local, puente multifactura, ensamblado) y anade la comprobacion de version. Cualquier otro proveedor, layout o
version falla cerrado: el documento queda ``PROVEEDOR_NO_SOPORTADO`` (R2) o con su defecto (R3).

No crea clientes, no lee ni escribe flags, no usa Luna y no se ejecuta al importarse. Solo lo compone el orquestador
nocturno (``noche_automatica.py``); los claims ``AUTOMATICO`` siguen exigiendo los flags en la base de datos.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from src.facturas.motor_local.catalogo import ProveedorLocal

from .compositor_manual import (
    CAMPOS_REQUERIDOS_MANUAL,
    LAYOUTS_CON_PUENTE_CERTIFICADO,
    ExtractorDocumentalAutorizado,
    MaterializadorStoragePrivado,
    ensamblar_documento_manual,
    proveedor_por_layout,
)
from .conciliacion import ReglaTolerancia
from .extraccion_productiva import ConfiguracionExtraccionProductiva, OrquestadorExtraccionProductiva
from .modelos import ConfiguracionRuntime, ResultadoEtapa
from .repositorios import RepositorioRuntimeSupabase
from .worker_automatico import WorkerAutomatico, construir_worker_automatico
from .worker_conciliacion import construir_worker_conciliacion
from .worker_normalizacion import WorkerNormalizacion


# D1 (Pio, 2026-11-12): solo Alliance, solo su version certificada (1.3.1 desde el 2026-11-14).
AUTORIDAD_COMPOSITOR_AUTOMATICO: Mapping[ProveedorLocal, tuple[str, str]] = MappingProxyType({
    ProveedorLocal.ALLIANCE: ("alliance-local", "1.3.1"),
})


def autoridad_automatica_habilitada(layout: str | None, version: str | None) -> bool:
    proveedor = proveedor_por_layout(layout)
    return (
        proveedor is not None
        and AUTORIDAD_COMPOSITOR_AUTOMATICO.get(proveedor) == (layout, version)
        and layout in LAYOUTS_CON_PUENTE_CERTIFICADO
    )


@dataclass(slots=True)
class ExtractorDocumentalAutorizadoAutomatico(ExtractorDocumentalAutorizado):
    """Igual que el extractor del compositor manual, mas la version certificada del adaptador."""

    codigo: str = "MOTOR_LOCAL_AUTORIZADO_AUTOMATICO"

    def extraer(self, ruta_pdf: Path, campos_pendientes: frozenset[str]) -> ResultadoEtapa:
        if not CAMPOS_REQUERIDOS_MANUAL <= campos_pendientes:
            return ResultadoEtapa(provenance={"motivo": "CAMPOS_NO_SOLICITADOS"})
        try:
            local = self.crear_motor().extraer(ruta_pdf)
        except Exception as exc:
            return ResultadoEtapa(provenance={
                "motivo": "EXTRACCION_LOCAL_ERROR", "error": type(exc).__name__,
            })
        layout = local.documento.get("layout")
        version = local.documento.get("layout_version")
        if layout is not None and not autoridad_automatica_habilitada(layout, version):
            return ResultadoEtapa(provenance={
                "layout": layout, "layout_version": version, "sha256": local.documento.get("sha256"),
                "motivo": "PROVEEDOR_NO_SOPORTADO_AUTOMATICO",
            })
        # Mismo camino que el compositor manual sobre el mismo resultado local (sin volver a extraer).
        motor = _MotorFijo(local)
        resultado = ExtractorDocumentalAutorizado(crear_motor=lambda: motor).extraer(ruta_pdf, campos_pendientes)
        if layout is None:
            return resultado
        return ResultadoEtapa(valores=resultado.valores,
                              provenance={**resultado.provenance, "layout_version": version},
                              uso_ocr=resultado.uso_ocr)


@dataclass(slots=True)
class _MotorFijo:
    local: Any

    def extraer(self, _ruta: Path) -> Any:
        return self.local


def construir_worker_automatico_productivo(
    cliente: Any,
    configuracion: ConfiguracionRuntime,
    worker_id: str,
    directorio_trabajo: Path,
) -> WorkerAutomatico:
    """Compone el worker de la ruta AUTOMATICA. Solo lo invoca el orquestador nocturno."""
    if configuracion.luna_habilitada:
        raise ValueError("LUNA_NO_AUTORIZADA_EN_COMPOSITOR_AUTOMATICO")
    if configuracion.farmacias_habilitadas != ("PIO",):
        raise ValueError("SOLO_PIO_AUTORIZADA_EN_COMPOSITOR_AUTOMATICO")
    if not worker_id.strip():
        raise ValueError("WORKER_ID_OBLIGATORIO")
    repositorio = RepositorioRuntimeSupabase(cliente)
    orquestador = OrquestadorExtraccionProductiva(
        extractor_especifico=ExtractorDocumentalAutorizadoAutomatico(),
        extractor_generico_local=None,
        extractor_ocr_local=None,
        extractor_luna=None,
        configuracion=ConfiguracionExtraccionProductiva(luna_habilitada=False),
    )
    normalizacion = WorkerNormalizacion(
        repositorio=repositorio,
        materializar_pdf=MaterializadorStoragePrivado(cliente, Path(directorio_trabajo)),
        orquestador=orquestador,
        campos_requeridos=CAMPOS_REQUERIDOS_MANUAL,
        worker_id=worker_id,
        ensamblar_documento=ensamblar_documento_manual,
    )
    conciliacion = construir_worker_conciliacion(
        repositorio,
        worker_id,
        tolerancia=configuracion.tolerancia_conciliacion,
        regla_tolerancia=ReglaTolerancia(
            suelo=configuracion.tolerancia_suelo,
            por_albaran=configuracion.tolerancia_por_albaran,
            tope=configuracion.tolerancia_tope,
        ),
    )
    return construir_worker_automatico(normalizacion, conciliacion, configuracion)
