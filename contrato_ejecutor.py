"""Contrato público y evidencia verificable de ejecutores V0.2.8."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from tareas_persistentes import CapacidadCheckpoint


@dataclass(frozen=True)
class ValidacionCheckpointEjecutor:
    valido: bool
    codigo: str
    mensaje: str
    warnings: tuple[str, ...] = ()
    errores: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextoRetryEjecutor:
    retry_id: str
    estrategia: str
    checkpoint_id: str | None
    checkpoint: dict[str, Any] | None
    acciones_omitidas: tuple[str, ...]
    acciones_pendientes: tuple[str, ...]

    @classmethod
    def desde_dict(cls, retry_id: str, datos: dict[str, Any] | None) -> "ContextoRetryEjecutor":
        datos = datos or {}
        checkpoint = datos.get("checkpoint")
        return cls(
            retry_id=retry_id,
            estrategia=str(datos.get("estrategia") or "RETRY_FULL_RUN"),
            checkpoint_id=(checkpoint or {}).get("checkpoint_id") if isinstance(checkpoint, dict) else None,
            checkpoint=dict(checkpoint) if isinstance(checkpoint, dict) else None,
            acciones_omitidas=tuple(datos.get("acciones_omitidas") or ()),
            acciones_pendientes=tuple(datos.get("acciones_pendientes") or ()),
        )

    def a_dict(self) -> dict[str, Any]:
        return {
            "retry_id": self.retry_id,
            "estrategia": self.estrategia,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint": self.checkpoint,
            "acciones_omitidas": list(self.acciones_omitidas),
            "acciones_pendientes": list(self.acciones_pendientes),
        }


@dataclass(frozen=True)
class EvidenciaRetryEjecutor:
    checkpoint_id_recibido: str | None
    checkpoint_id_utilizado: str | None
    estrategia_aplicada: str
    acciones_omitidas: tuple[str, ...]
    acciones_ejecutadas: tuple[str, ...]
    posicion_reanudacion: str | int | float | None = None
    checkpoint_generado_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "acciones_omitidas", tuple(self.acciones_omitidas))
        object.__setattr__(self, "acciones_ejecutadas", tuple(self.acciones_ejecutadas))
        if not all(
            isinstance(item, str)
            for item in (*self.acciones_omitidas, *self.acciones_ejecutadas)
        ):
            raise ValueError("las acciones de evidencia retry deben ser textos")

    def a_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id_recibido": self.checkpoint_id_recibido,
            "checkpoint_id_utilizado": self.checkpoint_id_utilizado,
            "estrategia_aplicada": self.estrategia_aplicada,
            "acciones_omitidas": list(self.acciones_omitidas),
            "acciones_ejecutadas": list(self.acciones_ejecutadas),
            "posicion_reanudacion": self.posicion_reanudacion,
            "checkpoint_generado_id": self.checkpoint_generado_id,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "EvidenciaRetryEjecutor":
        return cls(**datos)


@runtime_checkable
class ContratoEjecutorV02(Protocol):
    capacidad_checkpoint: CapacidadCheckpoint

    def ejecutar(self, run: Any, tarea: Any) -> Any:
        """Punto compatible que despacha ciclo normal, resume o retry."""

    def ejecutar_ciclo_normal(self, run: Any, tarea: Any) -> Any:
        """Ejecuta un ciclo nuevo no asociado a decisión ni retry."""

    def ejecutar_resume(self, run: Any, tarea: Any) -> Any:
        """Continúa una decisión persistente sin comando CLI manual."""

    def soporta_reintentos(self) -> bool:
        """Indica si admite al menos retry completo."""

    def validar_checkpoint(
        self, checkpoint: dict[str, Any], *, task_id: str, run_id: str
    ) -> ValidacionCheckpointEjecutor:
        """Valida si el ejecutor puede consumir el checkpoint concreto."""

    def construir_contexto_retry(
        self, contexto: ContextoRetryEjecutor
    ) -> dict[str, Any]:
        """Construye la entrada explícita que recibirá el ejecutor."""

    def consumir_retry_context(
        self, contexto: ContextoRetryEjecutor
    ) -> EvidenciaRetryEjecutor:
        """Consume el contexto y devuelve evidencia comprobable."""
