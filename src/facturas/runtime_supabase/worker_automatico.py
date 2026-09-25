"""Coordinador oficial one-shot del runtime automático.

No crea clientes, no activa flags y no ejecuta nada al importarse. La futura
automatización debe componerlo explícitamente desde un proceso backend.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .modelos import ConfiguracionRuntime
from .worker_conciliacion import WorkerConciliacion
from .worker_normalizacion import WorkerNormalizacion


MAX_DOCUMENTOS_POR_EJECUCION = 1


@dataclass(frozen=True, slots=True)
class ResultadoEjecucionAutomatica:
    documentos_reclamados: int
    facturas_conciliacion_reclamadas: int
    automatismos_habilitados: bool
    modo_ejecucion: str = "AUTOMATICO"


@dataclass(slots=True)
class WorkerAutomatico:
    normalizacion: WorkerNormalizacion
    conciliacion: WorkerConciliacion
    configuracion: ConfiguracionRuntime

    def ejecutar_una(self) -> ResultadoEjecucionAutomatica:
        """Ejecuta como máximo un claim documental y uno de conciliación."""
        documentos = 0
        conciliaciones = 0
        if self.configuracion.normalizacion_automatica:
            documentos = int(self.normalizacion.ejecutar_una())
        if self.configuracion.conciliacion_automatica:
            conciliaciones = int(self.conciliacion.ejecutar_una())
        return ResultadoEjecucionAutomatica(
            documentos_reclamados=documentos,
            facturas_conciliacion_reclamadas=conciliaciones,
            automatismos_habilitados=(
                self.configuracion.normalizacion_automatica
                or self.configuracion.conciliacion_automatica
            ),
            modo_ejecucion="AUTOMATICO",
        )

    def ejecutar_una_manual(self) -> ResultadoEjecucionAutomatica:
        """Procesa como maximo el siguiente PDF sin habilitar automatismos.

        Esta entrada no recibe selectores y no ejecuta conciliacion: autoriza
        exclusivamente el claim documental efimero MANUAL_ONE_SHOT.
        """
        documentos = int(self.normalizacion.ejecutar_una_manual_one_shot())
        return ResultadoEjecucionAutomatica(
            documentos_reclamados=documentos,
            facturas_conciliacion_reclamadas=0,
            automatismos_habilitados=False,
            modo_ejecucion="MANUAL_ONE_SHOT",
        )

    def ejecutar_una_manual_conciliacion(self) -> ResultadoEjecucionAutomatica:
        """Concilia como maximo una factura sin habilitar automatismos (migracion 18).

        No normaliza: autoriza exclusivamente el claim de conciliacion MANUAL_ONE_SHOT.
        """
        facturas = int(self.conciliacion.ejecutar_una_manual())
        return ResultadoEjecucionAutomatica(
            documentos_reclamados=0,
            facturas_conciliacion_reclamadas=facturas,
            automatismos_habilitados=False,
            modo_ejecucion="MANUAL_ONE_SHOT",
        )


def construir_worker_automatico(
    normalizacion: WorkerNormalizacion,
    conciliacion: WorkerConciliacion,
    configuracion: ConfiguracionRuntime,
) -> WorkerAutomatico:
    if (
        configuracion.tolerancia_conciliacion > Decimal("0.0500")
        or
        conciliacion.tolerancia > Decimal("0.0500")
        or conciliacion.tolerancia > configuracion.tolerancia_conciliacion
    ):
        raise ValueError("TOLERANCIA_RUNTIME_SUPERIOR_A_LA_CERTIFICADA")
    if configuracion.luna_habilitada:
        raise ValueError("LUNA_NO_AUTORIZADA_EN_WORKER_AUTOMATICO")
    if configuracion.farmacias_habilitadas != ("PIO",):
        raise ValueError("SOLO_PIO_AUTORIZADA_EN_WORKER_AUTOMATICO")
    return WorkerAutomatico(normalizacion, conciliacion, configuracion)
