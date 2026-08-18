"""Checkpoints persistentes mínimos para recuperación durable de runs V0.2.6."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import UUID, uuid4

from runs_persistentes import GestorRuns, RunNoEncontrado
from tareas_persistentes import GestorTareas, TareaNoEncontrada


CHECKPOINT_SCHEMA_VERSION = 1


class ErrorCheckpoint(RuntimeError):
    """Error base de checkpoints."""


class CheckpointNoEncontrado(ErrorCheckpoint, FileNotFoundError):
    """No existe el checkpoint solicitado."""


class CheckpointInvalido(ErrorCheckpoint, ValueError):
    """El checkpoint no cumple su contrato o sus referencias."""


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid(valor: Any, campo: str) -> None:
    try:
        UUID(valor)
    except (ValueError, TypeError, AttributeError) as exc:
        raise CheckpointInvalido(f"{campo} debe ser un UUID válido") from exc


@dataclass(frozen=True)
class CheckpointPersistente:
    checkpoint_id: str
    task_id: str
    run_id: str
    timestamp: str
    tipo: str
    payload: dict[str, Any]
    metadata: dict[str, Any]
    validado: bool

    def __post_init__(self) -> None:
        _uuid(self.checkpoint_id, "checkpoint_id")
        _uuid(self.task_id, "task_id")
        _uuid(self.run_id, "run_id")
        if not isinstance(self.tipo, str) or not self.tipo.strip():
            raise CheckpointInvalido("tipo debe ser texto no vacío")
        try:
            fecha = datetime.fromisoformat(self.timestamp)
        except (TypeError, ValueError) as exc:
            raise CheckpointInvalido("timestamp debe ser ISO-8601") from exc
        if fecha.tzinfo is None:
            raise CheckpointInvalido("timestamp debe incluir zona horaria")
        if not isinstance(self.payload, dict) or not isinstance(self.metadata, dict):
            raise CheckpointInvalido("payload y metadata deben ser objetos")
        if not isinstance(self.validado, bool):
            raise CheckpointInvalido("validado debe ser booleano")

    def a_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "checkpoint_id": self.checkpoint_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "tipo": self.tipo,
            "payload": self.payload,
            "metadata": self.metadata,
            "validado": self.validado,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "CheckpointPersistente":
        if not isinstance(datos, dict):
            raise CheckpointInvalido("checkpoint debe ser un objeto JSON")
        copia = dict(datos)
        if copia.pop("schema_version", None) != CHECKPOINT_SCHEMA_VERSION:
            raise CheckpointInvalido("schema_version de checkpoint no soportada")
        try:
            return cls(**copia)
        except TypeError as exc:
            raise CheckpointInvalido(f"checkpoint inválido: {exc}") from exc


class GestorCheckpoints:
    """Persiste checkpoints independientes y valida su relación tarea/run."""

    def __init__(
        self,
        gestor_tareas: GestorTareas,
        gestor_runs: GestorRuns,
        directorio: str | Path = Path("estado") / "checkpoints",
    ) -> None:
        self.gestor_tareas = gestor_tareas
        self.gestor_runs = gestor_runs
        self.directorio = Path(directorio)

    def registrar_checkpoint(
        self,
        *,
        task_id: str,
        run_id: str,
        tipo: str,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        validado: bool = False,
    ) -> CheckpointPersistente:
        try:
            tarea = self.gestor_tareas.cargar(task_id)
            run = self.gestor_runs.obtener_run(run_id)
        except (TareaNoEncontrada, RunNoEncontrado) as exc:
            raise CheckpointInvalido(str(exc)) from exc
        if run.task_id != tarea.id:
            raise CheckpointInvalido("el run no pertenece a la tarea")
        checkpoint = CheckpointPersistente(
            checkpoint_id=str(uuid4()),
            task_id=task_id,
            run_id=run_id,
            timestamp=_ahora_utc(),
            tipo=tipo,
            payload=dict(payload or {}),
            metadata=dict(metadata or {}),
            validado=validado,
        )
        self._guardar(checkpoint)
        return checkpoint

    def obtener_checkpoint(self, checkpoint_id: str) -> CheckpointPersistente:
        _uuid(checkpoint_id, "checkpoint_id")
        path = self.directorio / f"{checkpoint_id}.json"
        if not path.is_file():
            raise CheckpointNoEncontrado(f"checkpoint no encontrado: {checkpoint_id}")
        try:
            checkpoint = CheckpointPersistente.desde_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, CheckpointInvalido) as exc:
            raise CheckpointInvalido(f"no se pudo cargar {path}: {exc}") from exc
        if checkpoint.checkpoint_id != checkpoint_id:
            raise CheckpointInvalido("checkpoint_id interno no coincide con el archivo")
        return checkpoint

    def listar_checkpoints(
        self, *, task_id: str | None = None, run_id: str | None = None
    ) -> list[CheckpointPersistente]:
        if task_id is not None:
            _uuid(task_id, "task_id")
        if run_id is not None:
            _uuid(run_id, "run_id")
        if not self.directorio.exists():
            return []
        checkpoints = [
            self.obtener_checkpoint(path.stem)
            for path in sorted(self.directorio.glob("*.json"))
        ]
        return sorted(
            (
                item
                for item in checkpoints
                if (task_id is None or item.task_id == task_id)
                and (run_id is None or item.run_id == run_id)
            ),
            key=lambda item: (item.timestamp, item.checkpoint_id),
        )

    def obtener_ultimo_checkpoint(
        self, *, task_id: str, run_id: str | None = None
    ) -> CheckpointPersistente | None:
        items = self.listar_checkpoints(task_id=task_id, run_id=run_id)
        return items[-1] if items else None

    def _guardar(self, checkpoint: CheckpointPersistente) -> None:
        self.directorio.mkdir(parents=True, exist_ok=True)
        destino = self.directorio / f"{checkpoint.checkpoint_id}.json"
        descriptor, nombre = tempfile.mkstemp(
            prefix=f".{checkpoint.checkpoint_id}.", suffix=".tmp", dir=self.directorio
        )
        temporal = Path(nombre)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(
                    checkpoint.a_dict(), archivo, ensure_ascii=False, indent=2, allow_nan=False
                )
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, destino)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise
