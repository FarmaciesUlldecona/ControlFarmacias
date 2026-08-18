"""Planes de reintento explícitos, persistentes e idempotentes para V0.2.7."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable
from uuid import UUID, uuid4

from checkpoints_persistentes import (
    CheckpointNoEncontrado,
    CheckpointPersistente,
    GestorCheckpoints,
)
from contrato_ejecutor import ContextoRetryEjecutor
from ejecucion_v02 import EjecutorCiclo, ServicioEjecucionRuns
from entornos import GestorEntornos, validar_entorno
from runs_persistentes import EstadoInternoRun, GestorRuns, RunPersistente
from tareas_persistentes import (
    CapacidadCheckpoint,
    EstadoTarea,
    GestorTareas,
    Tarea,
    TareaNoEncontrada,
)


RETRY_SCHEMA_VERSION = 1


class EstrategiaReintento(str, Enum):
    RETRY_FROM_CHECKPOINT = "RETRY_FROM_CHECKPOINT"
    RETRY_FULL_RUN = "RETRY_FULL_RUN"


class EstadoReintento(str, Enum):
    PREPARADO = "PREPARADO"
    EJECUTANDO = "EJECUTANDO"
    COMPLETADO = "COMPLETADO"
    FALLIDO = "FALLIDO"
    CANCELADO = "CANCELADO"


class ErrorReintento(RuntimeError):
    """El almacenamiento de retries no puede interpretarse con seguridad."""


class ReintentoNoEncontrado(ErrorReintento, FileNotFoundError):
    """No existe el retry solicitado."""


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid(valor: Any, campo: str) -> None:
    try:
        UUID(valor)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ErrorReintento(f"{campo} debe ser un UUID válido") from exc


@dataclass(frozen=True)
class PlanReintento:
    retry_id: str
    task_id: str
    run_origen: str
    checkpoint_id: str | None
    motivo: str
    estrategia: EstrategiaReintento
    intento_nuevo: int
    acciones_omitidas: tuple[str, ...]
    acciones_pendientes: tuple[str, ...]
    timestamp: str
    estado: EstadoReintento
    capacidad_checkpoint: CapacidadCheckpoint
    repite_trabajo: bool
    potencial_nuevo_coste: bool
    unidades_pendientes: int | float | None
    run_nuevo_id: str | None = None
    ultima_actualizacion: str | None = None
    errores: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _uuid(self.retry_id, "retry_id")
        _uuid(self.task_id, "task_id")
        _uuid(self.run_origen, "run_origen")
        if self.checkpoint_id is not None:
            _uuid(self.checkpoint_id, "checkpoint_id")
        if self.run_nuevo_id is not None:
            _uuid(self.run_nuevo_id, "run_nuevo_id")
        object.__setattr__(self, "estrategia", EstrategiaReintento(self.estrategia))
        object.__setattr__(self, "estado", EstadoReintento(self.estado))
        object.__setattr__(
            self, "capacidad_checkpoint", CapacidadCheckpoint(self.capacidad_checkpoint)
        )
        object.__setattr__(self, "acciones_omitidas", tuple(self.acciones_omitidas))
        object.__setattr__(self, "acciones_pendientes", tuple(self.acciones_pendientes))
        object.__setattr__(self, "errores", tuple(self.errores))
        if not isinstance(self.intento_nuevo, int) or self.intento_nuevo < 1:
            raise ErrorReintento("intento_nuevo debe ser positivo")
        if not isinstance(self.motivo, str) or not self.motivo.strip():
            raise ErrorReintento("motivo debe ser texto no vacío")
        if not all(isinstance(item, str) for item in (*self.acciones_omitidas, *self.acciones_pendientes)):
            raise ErrorReintento("las acciones deben ser textos")
        for campo in ("timestamp", "ultima_actualizacion"):
            valor = getattr(self, campo)
            if valor is None and campo == "ultima_actualizacion":
                continue
            try:
                fecha = datetime.fromisoformat(valor)
            except (TypeError, ValueError) as exc:
                raise ErrorReintento(f"{campo} debe ser ISO-8601") from exc
            if fecha.tzinfo is None:
                raise ErrorReintento(f"{campo} debe incluir zona horaria")
        if self.unidades_pendientes is not None and (
            isinstance(self.unidades_pendientes, bool)
            or not isinstance(self.unidades_pendientes, (int, float))
            or self.unidades_pendientes < 0
        ):
            raise ErrorReintento("unidades_pendientes debe ser no negativa o null")

    def a_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RETRY_SCHEMA_VERSION,
            "retry_id": self.retry_id,
            "task_id": self.task_id,
            "run_origen": self.run_origen,
            "checkpoint_id": self.checkpoint_id,
            "motivo": self.motivo,
            "estrategia": self.estrategia.value,
            "intento_nuevo": self.intento_nuevo,
            "acciones_omitidas": list(self.acciones_omitidas),
            "acciones_pendientes": list(self.acciones_pendientes),
            "timestamp": self.timestamp,
            "estado": self.estado.value,
            "capacidad_checkpoint": self.capacidad_checkpoint.value,
            "repite_trabajo": self.repite_trabajo,
            "potencial_nuevo_coste": self.potencial_nuevo_coste,
            "unidades_pendientes": self.unidades_pendientes,
            "run_nuevo_id": self.run_nuevo_id,
            "ultima_actualizacion": self.ultima_actualizacion,
            "errores": list(self.errores),
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "PlanReintento":
        copia = dict(datos)
        if copia.pop("schema_version", None) != RETRY_SCHEMA_VERSION:
            raise ErrorReintento("schema_version de retry no soportada")
        try:
            return cls(**copia)
        except (TypeError, ValueError) as exc:
            raise ErrorReintento(f"retry inválido: {exc}") from exc


@dataclass(frozen=True)
class ResultadoOperacionReintento:
    exito: bool
    codigo: str
    retry: PlanReintento | None
    run: RunPersistente | None
    idempotente: bool
    errores: tuple[str, ...]


class ServicioReintentos:
    """Prepara y ejecuta retries solo mediante autorización/API explícita."""

    def __init__(
        self,
        gestor_tareas: GestorTareas,
        gestor_entornos: GestorEntornos,
        gestor_runs: GestorRuns,
        gestor_checkpoints: GestorCheckpoints,
        directorio: str | Path,
        *,
        estado_listo: Callable[[], bool] | None = None,
        ejecutor_factory: Callable[[Tarea], EjecutorCiclo] | None = None,
    ) -> None:
        self.gestor_tareas = gestor_tareas
        self.gestor_entornos = gestor_entornos
        self.gestor_runs = gestor_runs
        self.gestor_checkpoints = gestor_checkpoints
        self.directorio = Path(directorio)
        self.estado_listo = estado_listo or (lambda: True)
        self.ejecutor_factory = ejecutor_factory

    def preparar_reintento(
        self,
        task_id: str,
        checkpoint_id: str | None = None,
        *,
        motivo: str = "reintento explícito tras interrupción",
    ) -> ResultadoOperacionReintento:
        try:
            tarea = self.gestor_tareas.cargar(task_id)
        except TareaNoEncontrada as exc:
            return self._rechazo("TASK_NOT_FOUND", None, str(exc))
        if tarea.es_terminal:
            return self._rechazo("TERMINAL_TASK", None, "una tarea terminal no genera retry")
        if tarea.capacidad_checkpoint is CapacidadCheckpoint.NONE:
            return self._rechazo("RETRY_NOT_SUPPORTED", None, "capacidad de retry NONE")
        origen = self.gestor_runs.obtener_ultimo_run(task_id)
        if origen is None or origen.estado_interno is not EstadoInternoRun.INTERRUMPIDO:
            return self._rechazo(
                "NO_INTERRUPTED_RUN", None, "no existe un último run INTERRUMPIDO"
            )
        error_entorno = self._validar_entorno_retry(tarea)
        if error_entorno:
            self._evento_unico(task_id, "RETRY_REJECTED", {"causa": error_entorno})
            return self._rechazo("INVALID_ENVIRONMENT", None, error_entorno)
        posterior = self._run_posterior_exitoso(origen)
        if posterior is not None:
            return self._rechazo(
                "LATER_SUCCESS_EXISTS", None,
                f"ya existe el run posterior {posterior.run_id}",
            )

        checkpoint, error_checkpoint = self._seleccionar_checkpoint(
            tarea, origen, checkpoint_id
        )
        if error_checkpoint:
            self._evento_unico(
                task_id, "RETRY_REJECTED",
                {"run_origen": origen.run_id, "causa": error_checkpoint},
            )
            return self._rechazo("INVALID_CHECKPOINT", None, error_checkpoint)
        estrategia = (
            EstrategiaReintento.RETRY_FROM_CHECKPOINT
            if tarea.capacidad_checkpoint is CapacidadCheckpoint.CHECKPOINT_RESUME
            and checkpoint is not None
            else EstrategiaReintento.RETRY_FULL_RUN
        )
        clave_checkpoint = checkpoint.checkpoint_id if checkpoint else None
        existente = next(
            (
                item for item in self.listar_reintentos(task_id=task_id)
                if item.run_origen == origen.run_id
                and item.checkpoint_id == clave_checkpoint
                and item.estrategia is estrategia
                and item.estado is not EstadoReintento.CANCELADO
            ),
            None,
        )
        if existente is not None:
            return ResultadoOperacionReintento(
                True, "RETRY_ALREADY_PREPARED", existente,
                self._run_plan(existente), True, (),
            )

        omitidas = self._acciones(checkpoint, "acciones_omitidas", "acciones_completadas")
        pendientes = self._acciones(checkpoint, "acciones_pendientes")
        unidades = self._valor_checkpoint(checkpoint, "unidades_pendientes")
        timestamp = _ahora_utc()
        plan = PlanReintento(
            retry_id=str(uuid4()),
            task_id=task_id,
            run_origen=origen.run_id,
            checkpoint_id=clave_checkpoint,
            motivo=motivo,
            estrategia=estrategia,
            intento_nuevo=len(self.gestor_runs.listar_runs_tarea(task_id)) + 1,
            acciones_omitidas=omitidas if estrategia is EstrategiaReintento.RETRY_FROM_CHECKPOINT else (),
            acciones_pendientes=pendientes,
            timestamp=timestamp,
            estado=EstadoReintento.PREPARADO,
            capacidad_checkpoint=tarea.capacidad_checkpoint,
            repite_trabajo=estrategia is EstrategiaReintento.RETRY_FULL_RUN,
            potencial_nuevo_coste=True,
            unidades_pendientes=unidades,
            ultima_actualizacion=timestamp,
        )
        self._guardar(plan, nuevo=True)
        self._evento_unico(
            task_id, "RETRY_PREPARED",
            {"retry_id": plan.retry_id, "run_origen": origen.run_id,
             "checkpoint_id": clave_checkpoint, "estrategia": estrategia.value},
        )
        self._evento_unico(
            task_id,
            "RETRY_FROM_CHECKPOINT" if estrategia is EstrategiaReintento.RETRY_FROM_CHECKPOINT else "RETRY_FULL_RUN_REQUIRED",
            {"retry_id": plan.retry_id, "checkpoint_id": clave_checkpoint},
        )
        return ResultadoOperacionReintento(True, "RETRY_PREPARED", plan, None, False, ())

    def ejecutar_reintento(
        self, retry_id: str, ejecutor: EjecutorCiclo | None = None
    ) -> ResultadoOperacionReintento:
        try:
            plan = self.obtener_reintento(retry_id)
        except (ReintentoNoEncontrado, ErrorReintento) as exc:
            return self._rechazo("RETRY_NOT_FOUND", None, str(exc))
        if not self.estado_listo():
            return self._rechazo(
                "ORCHESTRATOR_NOT_READY", plan,
                "el Orquestador debe estar LISTO antes de ejecutar un retry",
            )
        if plan.estado is EstadoReintento.CANCELADO:
            return self._rechazo("RETRY_CANCELLED", plan, "retry cancelado")
        if plan.estado is EstadoReintento.COMPLETADO:
            return ResultadoOperacionReintento(
                True, "RETRY_ALREADY_COMPLETED", plan, self._run_plan(plan), True, ()
            )
        if plan.estado is EstadoReintento.FALLIDO:
            return self._rechazo("RETRY_FAILED", plan, "retry previamente fallido")

        tarea = self.gestor_tareas.cargar(plan.task_id)
        error_entorno = self._validar_entorno_retry(tarea)
        if error_entorno:
            return self._fallar(plan, "INVALID_ENVIRONMENT", error_entorno)
        origen = self.gestor_runs.obtener_run(plan.run_origen)
        posterior = self._run_posterior_exitoso(origen, excluir_retry=plan.retry_id)
        if posterior is not None:
            return self._fallar(
                plan, "LATER_SUCCESS_EXISTS",
                f"run posterior exitoso ya existente: {posterior.run_id}",
            )
        run = self._run_plan(plan)
        if run is not None and run.resultado is not None:
            return self._cerrar_desde_run(plan, run)
        if run is not None and run.estado_interno is EstadoInternoRun.INICIADO:
            return self._rechazo(
                "RETRY_IN_PROGRESS", plan, "el run del retry ya está INICIADO"
            )

        ejecutor_final = ejecutor or (
            self.ejecutor_factory(tarea) if self.ejecutor_factory is not None else None
        )
        if ejecutor_final is None:
            return self._rechazo("EXECUTOR_REQUIRED", plan, "falta ejecutor inyectado")
        if plan.estado is EstadoReintento.PREPARADO:
            plan = replace(
                plan, estado=EstadoReintento.EJECUTANDO,
                ultima_actualizacion=_ahora_utc(),
            )
            self._guardar(plan)
            self._evento_unico(plan.task_id, "RETRY_STARTED", {"retry_id": plan.retry_id})
        checkpoint = (
            self.gestor_checkpoints.obtener_checkpoint(plan.checkpoint_id)
            if plan.checkpoint_id else None
        )
        contexto_tipado = ContextoRetryEjecutor(
            retry_id=plan.retry_id,
            estrategia=plan.estrategia.value,
            checkpoint_id=plan.checkpoint_id,
            checkpoint=checkpoint.a_dict() if checkpoint else None,
            acciones_omitidas=plan.acciones_omitidas,
            acciones_pendientes=plan.acciones_pendientes,
        )
        construir_contexto = getattr(ejecutor_final, "construir_contexto_retry", None)
        if not callable(construir_contexto):
            return self._fallar(
                plan, "RETRY_CONTRACT_INVALID",
                "el ejecutor no implementa construir_contexto_retry",
            )
        retry_context = construir_contexto(contexto_tipado)
        if not isinstance(retry_context, dict):
            return self._fallar(
                plan, "RETRY_CONTRACT_INVALID",
                "construir_contexto_retry debe devolver un objeto",
            )
        if run is None:
            preparacion = self.gestor_runs.preparar_reintento_run(
                plan.task_id,
                plan.run_origen,
                plan.retry_id,
                checkpoint_id=plan.checkpoint_id,
                retry_context=retry_context,
            )
            if not preparacion.exito or preparacion.run is None:
                return self._fallar(
                    plan, "RUN_PREPARATION_FAILED",
                    "; ".join(preparacion.errores) or "run de retry no preparado",
                )
            run = preparacion.run
            plan = replace(
                plan, run_nuevo_id=run.run_id, ultima_actualizacion=_ahora_utc()
            )
            self._guardar(plan)
        completada = ServicioEjecucionRuns(self.gestor_runs).ejecutar_run(
            run.run_id, ejecutor_final
        )
        return self._cerrar_desde_run(
            self.obtener_reintento(plan.retry_id),
            self.gestor_runs.obtener_run(completada.resultado.run_id),
        )

    def cancelar_reintento(self, retry_id: str) -> ResultadoOperacionReintento:
        try:
            plan = self.obtener_reintento(retry_id)
        except (ReintentoNoEncontrado, ErrorReintento) as exc:
            return self._rechazo("RETRY_NOT_FOUND", None, str(exc))
        if plan.estado is EstadoReintento.CANCELADO:
            return ResultadoOperacionReintento(
                True, "RETRY_ALREADY_CANCELLED", plan, None, True, ()
            )
        if plan.estado is not EstadoReintento.PREPARADO:
            return self._rechazo(
                "RETRY_NOT_CANCELLABLE", plan,
                f"retry en estado {plan.estado.value}",
            )
        cancelado = replace(
            plan, estado=EstadoReintento.CANCELADO,
            ultima_actualizacion=_ahora_utc(),
        )
        self._guardar(cancelado)
        self._evento_unico(plan.task_id, "RETRY_CANCELLED", {"retry_id": retry_id})
        return ResultadoOperacionReintento(True, "RETRY_CANCELLED", cancelado, None, False, ())

    def obtener_reintento(self, retry_id: str) -> PlanReintento:
        _uuid(retry_id, "retry_id")
        path = self.directorio / f"{retry_id}.json"
        if not path.is_file():
            raise ReintentoNoEncontrado(f"retry no encontrado: {retry_id}")
        try:
            plan = PlanReintento.desde_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ErrorReintento) as exc:
            raise ErrorReintento(f"no se pudo cargar {path}: {exc}") from exc
        if plan.retry_id != retry_id:
            raise ErrorReintento("retry_id interno no coincide con el archivo")
        return plan

    def listar_reintentos(self, task_id: str | None = None) -> list[PlanReintento]:
        if task_id is not None:
            _uuid(task_id, "task_id")
        if not self.directorio.exists():
            return []
        items = [self.obtener_reintento(path.stem) for path in self.directorio.glob("*.json")]
        return sorted(
            (item for item in items if task_id is None or item.task_id == task_id),
            key=lambda item: (item.timestamp, item.retry_id),
        )

    def _seleccionar_checkpoint(
        self, tarea: Tarea, origen: RunPersistente, checkpoint_id: str | None
    ) -> tuple[CheckpointPersistente | None, str | None]:
        if checkpoint_id is not None:
            try:
                checkpoint = self.gestor_checkpoints.obtener_checkpoint(checkpoint_id)
            except Exception as exc:
                return None, str(exc)
            error = self._validar_checkpoint(checkpoint, tarea, origen)
            return (checkpoint, None) if error is None else (None, error)
        candidatos = reversed(
            self.gestor_checkpoints.listar_checkpoints(
                task_id=tarea.id, run_id=origen.run_id
            )
        )
        for checkpoint in candidatos:
            if self._validar_checkpoint(checkpoint, tarea, origen) is None:
                return checkpoint, None
        return None, None

    def _validar_checkpoint(
        self, checkpoint: CheckpointPersistente, tarea: Tarea, origen: RunPersistente
    ) -> str | None:
        if checkpoint.task_id != tarea.id:
            return "checkpoint pertenece a otra tarea"
        if checkpoint.run_id != origen.run_id:
            return "checkpoint pertenece a otro run"
        if not checkpoint.validado:
            return "checkpoint no validado"
        if checkpoint.metadata.get("invalidado") or checkpoint.metadata.get("utilizable") is False:
            return "metadata marca el checkpoint como invalidado"
        for clave in ("acciones_omitidas", "acciones_completadas", "acciones_pendientes"):
            valor = self._valor_checkpoint(checkpoint, clave)
            if valor is not None and (
                not isinstance(valor, (list, tuple))
                or not all(isinstance(item, str) for item in valor)
            ):
                return f"metadata inconsistente: {clave}"
        unidades = self._valor_checkpoint(checkpoint, "unidades_pendientes")
        if unidades is not None and (
            isinstance(unidades, bool)
            or not isinstance(unidades, (int, float))
            or unidades < 0
        ):
            return "metadata inconsistente: unidades_pendientes"
        if origen.resultado is not None and (
            datetime.fromisoformat(checkpoint.timestamp)
            > datetime.fromisoformat(origen.resultado.timestamp)
        ):
            return "checkpoint posterior al resultado del run"
        posteriores = [
            item for item in self.gestor_checkpoints.listar_checkpoints(
                task_id=tarea.id, run_id=origen.run_id
            )
            if datetime.fromisoformat(item.timestamp)
            > datetime.fromisoformat(checkpoint.timestamp)
            and (
                item.metadata.get("invalida_anteriores")
                or item.metadata.get("invalida_checkpoint_id") == checkpoint.checkpoint_id
            )
        ]
        return "evidencia posterior invalida el checkpoint" if posteriores else None

    def _validar_entorno_retry(self, tarea: Tarea) -> str | None:
        reserva = self.gestor_entornos.obtener_reserva(tarea.worktree)
        if reserva is None:
            return "worktree sin lock"
        if reserva.task_id != tarea.id:
            return f"lock propiedad de otra tarea: {reserva.task_id}"
        if reserva.session_id != self.gestor_entornos.session_id:
            return "lock ambiguo de otra sesión; ejecutar recuperación primero"
        resultado = validar_entorno(tarea)
        return "; ".join(resultado.discrepancias) if not resultado.es_valido else None

    def _run_posterior_exitoso(
        self, origen: RunPersistente, excluir_retry: str | None = None
    ) -> RunPersistente | None:
        for run in self.gestor_runs.listar_runs_tarea(origen.task_id):
            if run.numero_intento <= origen.numero_intento or run.resultado is None:
                continue
            if excluir_retry is not None and run.retry_id == excluir_retry:
                continue
            if run.estado_interno not in {
                EstadoInternoRun.FALLIDO, EstadoInternoRun.INTERRUMPIDO
            }:
                return run
        return None

    def _cerrar_desde_run(
        self, plan: PlanReintento, run: RunPersistente
    ) -> ResultadoOperacionReintento:
        fallido = run.estado_interno in {
            EstadoInternoRun.FALLIDO, EstadoInternoRun.INTERRUMPIDO
        }
        estado = EstadoReintento.FALLIDO if fallido else EstadoReintento.COMPLETADO
        actualizado = replace(
            plan,
            estado=estado,
            run_nuevo_id=run.run_id,
            ultima_actualizacion=_ahora_utc(),
            errores=run.resultado.errores if fallido and run.resultado else (),
        )
        self._guardar(actualizado)
        self._evento_unico(
            plan.task_id,
            "RETRY_FAILED" if fallido else "RETRY_COMPLETED",
            {"retry_id": plan.retry_id, "run_id": run.run_id},
        )
        return ResultadoOperacionReintento(
            not fallido,
            "RETRY_FAILED" if fallido else "RETRY_COMPLETED",
            actualizado, run, False, actualizado.errores,
        )

    def _fallar(
        self, plan: PlanReintento, codigo: str, error: str
    ) -> ResultadoOperacionReintento:
        fallido = replace(
            plan, estado=EstadoReintento.FALLIDO,
            ultima_actualizacion=_ahora_utc(), errores=(error,),
        )
        self._guardar(fallido)
        self._evento_unico(plan.task_id, "RETRY_FAILED", {"retry_id": plan.retry_id, "causa": error})
        return ResultadoOperacionReintento(False, codigo, fallido, self._run_plan(fallido), False, (error,))

    @staticmethod
    def _rechazo(
        codigo: str, plan: PlanReintento | None, error: str
    ) -> ResultadoOperacionReintento:
        return ResultadoOperacionReintento(False, codigo, plan, None, False, (error,))

    def _run_plan(self, plan: PlanReintento) -> RunPersistente | None:
        if plan.run_nuevo_id:
            try:
                return self.gestor_runs.obtener_run(plan.run_nuevo_id)
            except Exception:
                return None
        return next(
            (run for run in self.gestor_runs.listar_runs_tarea(plan.task_id) if run.retry_id == plan.retry_id),
            None,
        )

    @staticmethod
    def _valor_checkpoint(checkpoint: CheckpointPersistente | None, clave: str) -> Any:
        if checkpoint is None:
            return None
        return checkpoint.metadata.get(clave, checkpoint.payload.get(clave))

    @classmethod
    def _acciones(cls, checkpoint: CheckpointPersistente | None, *claves: str) -> tuple[str, ...]:
        for clave in claves:
            valor = cls._valor_checkpoint(checkpoint, clave)
            if isinstance(valor, (list, tuple)) and all(isinstance(item, str) for item in valor):
                return tuple(valor)
        return ()

    def _evento_unico(self, task_id: str, tipo: str, datos: dict[str, Any]) -> None:
        tarea = self.gestor_tareas.cargar(task_id)
        if any(evento.tipo == tipo and evento.datos == datos for evento in tarea.historial):
            return
        self.gestor_tareas.anadir_evento(task_id, tipo, datos)

    def _guardar(self, plan: PlanReintento, *, nuevo: bool = False) -> None:
        self.directorio.mkdir(parents=True, exist_ok=True)
        destino = self.directorio / f"{plan.retry_id}.json"
        if nuevo and destino.exists():
            raise ErrorReintento(f"retry ya existente: {plan.retry_id}")
        descriptor, nombre = tempfile.mkstemp(
            prefix=f".{plan.retry_id}.", suffix=".tmp", dir=self.directorio
        )
        temporal = Path(nombre)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(plan.a_dict(), archivo, ensure_ascii=False, indent=2, allow_nan=False)
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, destino)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise
