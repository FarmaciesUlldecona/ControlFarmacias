"""Runs V0.2 subordinados a tareas persistentes y al entorno reservado."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import UUID, uuid4

from entornos import GestorEntornos, normalizar_worktree
from orquestador import validar_rutas
from orquestador_snapshot import (
    SnapshotDiff,
    SnapshotError,
    WorkspaceSnapshot,
    comparar_snapshots,
    tomar_snapshot,
)
from tareas_persistentes import (
    CapacidadCheckpoint,
    ErrorTarea,
    EstadoTarea,
    GestorTareas,
    Tarea,
    TareaNoEncontrada,
)


RUN_SCHEMA_VERSION = 1


class ErrorRun(RuntimeError):
    """Error base de la capa persistente de runs V0.2."""


class RunNoEncontrado(ErrorRun, FileNotFoundError):
    """No existe el run solicitado."""


class EstadoRunInvalido(ErrorRun):
    """La operación no corresponde al estado actual del run."""


class ErrorPersistenciaRun(ErrorRun):
    """Los metadatos persistidos de un run son inválidos."""


class EstadoInternoRun(str, Enum):
    PREPARADO = "PREPARADO"
    INICIADO = "INICIADO"
    AUTO_CONTINUE = "AUTO_CONTINUE"
    REQUIERE_OK_PIO = "REQUIERE_OK_PIO"
    PAUSA_PIO = "PAUSA_PIO"
    FINALIZADO = "FINALIZADO"
    FALLIDO = "FALLIDO"
    INTERRUMPIDO = "INTERRUMPIDO"


ESTADOS_RESULTADO = frozenset(
    {
        EstadoInternoRun.AUTO_CONTINUE,
        EstadoInternoRun.REQUIERE_OK_PIO,
        EstadoInternoRun.PAUSA_PIO,
        EstadoInternoRun.FINALIZADO,
        EstadoInternoRun.FALLIDO,
        EstadoInternoRun.INTERRUMPIDO,
    }
)


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validar_uuid(valor: str, campo: str) -> None:
    try:
        UUID(valor)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ErrorPersistenciaRun(f"{campo} debe ser un UUID válido") from exc


def _snapshot_a_dict(snapshot: WorkspaceSnapshot) -> dict[str, Any]:
    return {
        "archivos": snapshot.archivos,
        "head": snapshot.head,
        "rama": snapshot.rama,
        "staged_paths": sorted(snapshot.staged_paths),
        "unstaged_paths": sorted(snapshot.unstaged_paths),
        "staged_fingerprint": snapshot.staged_fingerprint,
        "unstaged_fingerprint": snapshot.unstaged_fingerprint,
    }


def _snapshot_desde_dict(datos: dict[str, Any]) -> WorkspaceSnapshot:
    try:
        return WorkspaceSnapshot(
            archivos=dict(datos["archivos"]),
            head=datos["head"],
            rama=datos["rama"],
            staged_paths=frozenset(datos["staged_paths"]),
            unstaged_paths=frozenset(datos["unstaged_paths"]),
            staged_fingerprint=datos["staged_fingerprint"],
            unstaged_fingerprint=datos["unstaged_fingerprint"],
        )
    except (KeyError, TypeError) as exc:
        raise ErrorPersistenciaRun(f"snapshot inicial inválido: {exc}") from exc


def _diff_a_dict(diff: SnapshotDiff) -> dict[str, Any]:
    return {
        "creados": sorted(diff.creados),
        "eliminados": sorted(diff.eliminados),
        "modificados": sorted(diff.modificados),
        "cambio_head": diff.cambio_head,
        "cambio_rama": diff.cambio_rama,
        "cambio_staged": diff.cambio_staged,
        "cambio_unstaged": diff.cambio_unstaged,
        "paths_git_cambiados": sorted(diff.paths_git_cambiados),
        "paths_cambiados": sorted(diff.paths_cambiados),
    }


@dataclass(frozen=True)
class ResultadoRun:
    run_id: str
    task_id: str
    estado_interno: EstadoInternoRun
    estado_v02_propuesto: EstadoTarea
    requiere_decision: bool
    resumen: str
    errores: tuple[str, ...]
    timestamp: str
    siguiente_accion: str
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        _validar_uuid(self.run_id, "run_id")
        _validar_uuid(self.task_id, "task_id")
        object.__setattr__(self, "estado_interno", EstadoInternoRun(self.estado_interno))
        object.__setattr__(self, "estado_v02_propuesto", EstadoTarea(self.estado_v02_propuesto))
        object.__setattr__(self, "errores", tuple(self.errores))
        if self.estado_interno not in ESTADOS_RESULTADO:
            raise ErrorPersistenciaRun("estado_interno no es un resultado final de ciclo")

    def a_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "estado_interno": self.estado_interno.value,
            "estado_v02_propuesto": self.estado_v02_propuesto.value,
            "requiere_decision": self.requiere_decision,
            "resumen": self.resumen,
            "errores": list(self.errores),
            "timestamp": self.timestamp,
            "siguiente_accion": self.siguiente_accion,
            "metadata": self.metadata,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> ResultadoRun:
        try:
            return cls(**datos)
        except (TypeError, ValueError) as exc:
            raise ErrorPersistenciaRun(f"resultado de run inválido: {exc}") from exc


@dataclass(frozen=True)
class RunPersistente:
    run_id: str
    task_id: str
    entorno: dict[str, Any]
    estado_partida: EstadoTarea
    estado_interno: EstadoInternoRun
    timestamp: str
    numero_intento: int
    directorio_run: str
    branch_observada: str
    head_observado: str
    snapshot_inicial: dict[str, Any]
    resume_de: str | None
    decision_resume: str | None
    resultado: ResultadoRun | None
    ultima_actualizacion: str
    decision_id: str | None = None
    capacidad_checkpoint: CapacidadCheckpoint = CapacidadCheckpoint.NONE
    retry_de: str | None = None
    checkpoint_id: str | None = None
    retry_id: str | None = None
    retry_context: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _validar_uuid(self.run_id, "run_id")
        _validar_uuid(self.task_id, "task_id")
        if self.resume_de is not None:
            _validar_uuid(self.resume_de, "resume_de")
        if self.decision_id is not None:
            _validar_uuid(self.decision_id, "decision_id")
        for campo in ("retry_de", "checkpoint_id", "retry_id"):
            if getattr(self, campo) is not None:
                _validar_uuid(getattr(self, campo), campo)
        object.__setattr__(
            self,
            "capacidad_checkpoint",
            CapacidadCheckpoint(self.capacidad_checkpoint),
        )
        if self.retry_context is not None and not isinstance(self.retry_context, dict):
            raise ErrorPersistenciaRun("retry_context debe ser un objeto o null")
        object.__setattr__(self, "estado_partida", EstadoTarea(self.estado_partida))
        object.__setattr__(self, "estado_interno", EstadoInternoRun(self.estado_interno))
        if not isinstance(self.numero_intento, int) or self.numero_intento < 1:
            raise ErrorPersistenciaRun("numero_intento debe ser un entero positivo")
        if self.resultado is not None:
            if self.resultado.run_id != self.run_id or self.resultado.task_id != self.task_id:
                raise ErrorPersistenciaRun("el resultado no pertenece al run/tarea")
        _snapshot_desde_dict(self.snapshot_inicial)

    def a_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RUN_SCHEMA_VERSION,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "entorno": self.entorno,
            "estado_partida": self.estado_partida.value,
            "estado_interno": self.estado_interno.value,
            "timestamp": self.timestamp,
            "numero_intento": self.numero_intento,
            "directorio_run": self.directorio_run,
            "branch_observada": self.branch_observada,
            "head_observado": self.head_observado,
            "snapshot_inicial": self.snapshot_inicial,
            "resume_de": self.resume_de,
            "decision_resume": self.decision_resume,
            "resultado": self.resultado.a_dict() if self.resultado else None,
            "ultima_actualizacion": self.ultima_actualizacion,
            "decision_id": self.decision_id,
            "capacidad_checkpoint": self.capacidad_checkpoint.value,
            "retry_de": self.retry_de,
            "checkpoint_id": self.checkpoint_id,
            "retry_id": self.retry_id,
            "retry_context": self.retry_context,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> RunPersistente:
        copia = dict(datos)
        version = copia.pop("schema_version", None)
        if version != RUN_SCHEMA_VERSION:
            raise ErrorPersistenciaRun(f"schema de run no soportado: {version}")
        try:
            copia.setdefault("decision_id", None)
            copia.setdefault("capacidad_checkpoint", CapacidadCheckpoint.NONE.value)
            copia.setdefault("retry_de", None)
            copia.setdefault("checkpoint_id", None)
            copia.setdefault("retry_id", None)
            copia.setdefault("retry_context", None)
            if copia.get("resultado") is not None:
                copia["resultado"] = ResultadoRun.desde_dict(copia["resultado"])
            return cls(**copia)
        except (TypeError, ValueError) as exc:
            raise ErrorPersistenciaRun(f"run inválido: {exc}") from exc


@dataclass(frozen=True)
class ResultadoPreparacionRun:
    exito: bool
    task_id: str
    run: RunPersistente | None
    errores: tuple[str, ...]
    timestamp: str
    siguiente_accion: str


def traducir_estado_historico(
    estado_interno: EstadoInternoRun | str,
    *,
    causa_pausa: str = "",
    integridad_correcta: bool = True,
    condiciones_funcionales_validadas: bool = False,
) -> tuple[EstadoTarea, bool]:
    """Traduce sin confundir una decisión del motor con el estado de la tarea."""

    estado = EstadoInternoRun(estado_interno)
    # Una desviación de integridad prevalece sobre cualquier éxito funcional.
    if not integridad_correcta:
        return EstadoTarea.BLOQUEADA, True
    if estado is EstadoInternoRun.AUTO_CONTINUE:
        return EstadoTarea.TRABAJANDO, False
    if estado is EstadoInternoRun.REQUIERE_OK_PIO:
        return EstadoTarea.ESPERANDO_DECISION, True
    if estado is EstadoInternoRun.PAUSA_PIO:
        causa = causa_pausa.casefold()
        bloqueante = any(
            termino in causa
            for termino in ("barrera", "integridad", "bloque", "conflicto", "error")
        )
        return (
            EstadoTarea.BLOQUEADA if bloqueante else EstadoTarea.ESPERANDO_DECISION,
            True,
        )
    if estado is EstadoInternoRun.FALLIDO:
        return EstadoTarea.BLOQUEADA, True
    if estado is EstadoInternoRun.INTERRUMPIDO:
        return EstadoTarea.RECUPERANDO, True
    if estado is EstadoInternoRun.FINALIZADO:
        if integridad_correcta and condiciones_funcionales_validadas:
            return EstadoTarea.FINALIZADA, False
        return EstadoTarea.TRABAJANDO, False
    raise ValueError(f"estado histórico no traducible como resultado: {estado.value}")


class GestorRuns:
    """Puente persistente entre tareas/entornos V0.2 y el motor histórico."""

    def __init__(
        self,
        gestor_tareas: GestorTareas,
        gestor_entornos: GestorEntornos,
        directorio_runs: str | Path = "runs",
    ) -> None:
        self.gestor_tareas = gestor_tareas
        self.gestor_entornos = gestor_entornos
        self.directorio_runs = Path(directorio_runs)

    def preparar_run(
        self,
        task_id: str,
        *,
        resume_de: str | None = None,
        decision_resume: str | None = None,
        decision_id: str | None = None,
        retry_de: str | None = None,
        checkpoint_id: str | None = None,
        retry_id: str | None = None,
        retry_context: dict[str, Any] | None = None,
    ) -> ResultadoPreparacionRun:
        timestamp = _ahora_utc()
        if retry_de is None and any(
            valor is not None
            for valor in (checkpoint_id, retry_id, retry_context)
        ):
            return ResultadoPreparacionRun(
                False,
                task_id,
                None,
                ("metadata de retry requiere run origen",),
                timestamp,
                "usar preparar_reintento_run",
            )
        if retry_id is not None:
            try:
                _validar_uuid(retry_id, "retry_id")
            except ErrorPersistenciaRun as exc:
                return ResultadoPreparacionRun(
                    False, task_id, None, (str(exc),), timestamp,
                    "usar un retry_id UUID válido",
                )
            existente_retry = next(
                (run for run in self.listar_runs_tarea(task_id) if run.retry_id == retry_id),
                None,
            )
            if existente_retry is not None:
                return ResultadoPreparacionRun(
                    True, task_id, existente_retry, (), timestamp,
                    "reutilizar el run ya asociado al retry",
                )
        if decision_id is not None:
            try:
                _validar_uuid(decision_id, "decision_id")
            except ErrorPersistenciaRun as exc:
                return ResultadoPreparacionRun(
                    False,
                    task_id,
                    None,
                    (str(exc),),
                    timestamp,
                    "usar un decision_id UUID válido",
                )
            existente = next(
                (
                    run
                    for run in self.listar_runs_tarea(task_id)
                    if run.decision_id == decision_id
                ),
                None,
            )
            if existente is not None:
                return ResultadoPreparacionRun(
                    True,
                    task_id,
                    existente,
                    (),
                    timestamp,
                    "reutilizar el run ya asociado a la decisión",
                )
        try:
            tarea = self.gestor_tareas.cargar(task_id)
        except ErrorTarea:
            return ResultadoPreparacionRun(
                False,
                task_id,
                None,
                ("tarea inexistente",),
                timestamp,
                "crear o recuperar la tarea persistente",
            )

        errores = self._comprobar_precondiciones(tarea)
        if retry_de is not None:
            errores.extend(
                self._comprobar_reintento(
                    tarea, retry_de, checkpoint_id=checkpoint_id, retry_id=retry_id
                )
            )
        if resume_de is not None:
            errores.extend(
                self._comprobar_resume(
                    tarea,
                    resume_de,
                    decision_resume,
                    decision_id=decision_id,
                )
            )
        if errores:
            self.gestor_tareas.anadir_evento(
                task_id,
                "RUN_PRECONDITION_FAILED",
                {"errores": errores, "resume_de": resume_de},
            )
            return ResultadoPreparacionRun(
                False,
                task_id,
                None,
                tuple(errores),
                timestamp,
                "resolver las precondiciones antes de crear un run",
            )

        reserva = self.gestor_entornos.obtener_reserva(tarea.worktree)
        snapshot = tomar_snapshot(Path(tarea.worktree))
        run_id = str(uuid4())
        intento = len(self.listar_runs_tarea(task_id)) + 1
        nombre = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{run_id}"
        destino = self.directorio_runs / nombre
        run = RunPersistente(
            run_id=run_id,
            task_id=task_id,
            entorno={
                "repo": tarea.repo,
                "worktree": tarea.worktree,
                "worktree_normalizado": normalizar_worktree(tarea.worktree),
                "rama": tarea.rama,
                "commit_inicial": tarea.commit_inicial,
                "modo": tarea.modo.value,
                "lock_fecha_creacion": reserva.fecha_creacion,
                "session_id": reserva.session_id,
            },
            estado_partida=tarea.estado,
            estado_interno=EstadoInternoRun.PREPARADO,
            timestamp=timestamp,
            numero_intento=intento,
            directorio_run=str(destino.resolve()),
            branch_observada=snapshot.rama,
            head_observado=snapshot.head,
            snapshot_inicial=_snapshot_a_dict(snapshot),
            resume_de=resume_de,
            decision_resume=decision_resume.strip() if decision_resume else None,
            resultado=None,
            ultima_actualizacion=timestamp,
            decision_id=decision_id,
            capacidad_checkpoint=tarea.capacidad_checkpoint,
            retry_de=retry_de,
            checkpoint_id=checkpoint_id,
            retry_id=retry_id,
            retry_context=dict(retry_context or {}) if retry_de is not None else None,
        )
        self._crear_directorio_atomico(run, destino)
        self.gestor_tareas.anadir_evento(
            task_id,
            "RUN_CREATED",
            {
                "run_id": run.run_id,
                "directorio_run": run.directorio_run,
                "numero_intento": run.numero_intento,
                "resume_de": resume_de,
                "decision_id": decision_id,
                "retry_de": retry_de,
                "checkpoint_id": checkpoint_id,
                "retry_id": retry_id,
            },
        )
        if resume_de is not None:
            self.gestor_tareas.anadir_evento(
                task_id,
                "RUN_RESUMED",
                {
                    "run_id": run.run_id,
                    "run_anterior": resume_de,
                    "numero_intento": run.numero_intento,
                    "decision_id": decision_id,
                },
            )
        return ResultadoPreparacionRun(
            True,
            task_id,
            run,
            (),
            timestamp,
            "iniciar el run mediante el adaptador del motor",
        )

    def preparar_reintento_run(
        self,
        task_id: str,
        run_origen: str,
        retry_id: str,
        *,
        checkpoint_id: str | None = None,
        retry_context: dict[str, Any] | None = None,
    ) -> ResultadoPreparacionRun:
        return self.preparar_run(
            task_id,
            retry_de=run_origen,
            checkpoint_id=checkpoint_id,
            retry_id=retry_id,
            retry_context=retry_context,
        )

    def preparar_resume(
        self,
        task_id: str,
        run_pausado_id: str,
        decision: str,
        *,
        decision_id: str | None = None,
    ) -> ResultadoPreparacionRun:
        return self.preparar_run(
            task_id,
            resume_de=run_pausado_id,
            decision_resume=decision,
            decision_id=decision_id,
        )

    def iniciar_run(self, run_id: str) -> RunPersistente:
        run = self.obtener_run(run_id)
        if run.estado_interno is not EstadoInternoRun.PREPARADO:
            raise EstadoRunInvalido(
                f"solo se inicia un run PREPARADO, no {run.estado_interno.value}"
            )
        tarea = self.gestor_tareas.cargar(run.task_id)
        errores = self._comprobar_precondiciones(tarea)
        if errores:
            self.gestor_tareas.anadir_evento(
                run.task_id,
                "RUN_PRECONDITION_FAILED",
                {"run_id": run.run_id, "errores": errores, "fase": "inicio"},
            )
            raise EstadoRunInvalido("; ".join(errores))
        # La validación de entorno registra eventos; recargamos para no actualizar
        # una versión anterior del historial append-only.
        tarea = self.gestor_tareas.cargar(run.task_id)
        if tarea.estado in {
            EstadoTarea.PREPARANDO,
            EstadoTarea.ESPERANDO_DECISION,
            EstadoTarea.RECUPERANDO,
        }:
            tarea = self.gestor_tareas.actualizar_estado(tarea, EstadoTarea.TRABAJANDO)
        if tarea.estado is not EstadoTarea.TRABAJANDO:
            raise EstadoRunInvalido(
                f"la tarea no puede iniciar desde {tarea.estado.value}"
            )
        snapshot = tomar_snapshot(Path(tarea.worktree))
        actualizado = replace(
            run,
            estado_interno=EstadoInternoRun.INICIADO,
            branch_observada=snapshot.rama,
            head_observado=snapshot.head,
            snapshot_inicial=_snapshot_a_dict(snapshot),
            ultima_actualizacion=_ahora_utc(),
        )
        self._guardar_run(actualizado)
        self.gestor_tareas.anadir_evento(
            run.task_id,
            "RUN_STARTED",
            {"run_id": run.run_id, "numero_intento": run.numero_intento},
        )
        return actualizado

    def registrar_resultado(
        self,
        run_id: str,
        estado_interno: EstadoInternoRun | str,
        *,
        resumen: str,
        errores: tuple[str, ...] | list[str] = (),
        siguiente_accion: str = "",
        causa_pausa: str = "",
        condiciones_funcionales_validadas: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> ResultadoRun:
        run = self.obtener_run(run_id)
        if run.estado_interno is not EstadoInternoRun.INICIADO:
            raise EstadoRunInvalido("el run debe estar INICIADO para registrar resultado")
        estado = EstadoInternoRun(estado_interno)
        if estado not in ESTADOS_RESULTADO:
            raise EstadoRunInvalido(f"estado no final de ciclo: {estado.value}")

        tarea = self.gestor_tareas.cargar(run.task_id)
        errores_finales = list(errores)
        integridad, metadata_integridad = self._validar_despues(run, tarea)
        errores_finales.extend(metadata_integridad.pop("errores_integridad"))
        propuesta, requiere_decision = traducir_estado_historico(
            estado,
            causa_pausa=causa_pausa,
            integridad_correcta=integridad,
            condiciones_funcionales_validadas=condiciones_funcionales_validadas,
        )
        timestamp = _ahora_utc()
        datos = dict(metadata or {})
        datos.update(metadata_integridad)
        datos["condiciones_funcionales_validadas"] = condiciones_funcionales_validadas
        resultado = ResultadoRun(
            run_id=run.run_id,
            task_id=run.task_id,
            estado_interno=estado,
            estado_v02_propuesto=propuesta,
            requiere_decision=requiere_decision,
            resumen=resumen,
            errores=tuple(errores_finales),
            timestamp=timestamp,
            siguiente_accion=siguiente_accion,
            metadata=datos,
        )
        actualizado = replace(
            run,
            estado_interno=estado,
            resultado=resultado,
            ultima_actualizacion=timestamp,
        )
        self._guardar_run(actualizado)

        evento = self._evento_para_resultado(estado)
        self.gestor_tareas.anadir_evento(
            run.task_id,
            evento,
            {
                "run_id": run.run_id,
                "estado_interno": estado.value,
                "estado_v02_propuesto": propuesta.value,
                "integridad_correcta": integridad,
                "errores": errores_finales,
            },
        )
        self._aplicar_estado_no_terminal(run.task_id, propuesta, estado)
        return resultado

    def registrar_resultado_historico(
        self, run_id: str, status: str, state: dict[str, Any]
    ) -> ResultadoRun:
        """Seam para consumir el `(status, state)` actual de `ejecutar_ciclo`."""

        resumen = ""
        decision = state.get("ultima_decision_supervisor") or {}
        if isinstance(decision, dict):
            resumen = decision.get("motivo", "")
        return self.registrar_resultado(
            run_id,
            EstadoInternoRun(status),
            resumen=resumen or f"Resultado del motor histórico: {status}",
            siguiente_accion=state.get("siguiente_instruccion", ""),
            causa_pausa=decision.get("detalle", "") if isinstance(decision, dict) else "",
            metadata={"state_historico": state},
        )

    def obtener_run(self, run_id: str) -> RunPersistente:
        _validar_uuid(run_id, "run_id")
        coincidencias = list(self.directorio_runs.glob(f"*_{run_id}/run.json"))
        if not coincidencias:
            raise RunNoEncontrado(f"run no encontrado: {run_id}")
        if len(coincidencias) != 1:
            raise ErrorPersistenciaRun(f"run_id duplicado en disco: {run_id}")
        return self._cargar_path(coincidencias[0])

    def listar_runs_tarea(self, task_id: str) -> list[RunPersistente]:
        if not self.directorio_runs.exists():
            return []
        runs = [
            self._cargar_path(path)
            for path in self.directorio_runs.glob("*/run.json")
        ]
        return sorted(
            (run for run in runs if run.task_id == task_id),
            key=lambda run: (run.numero_intento, run.timestamp, run.run_id),
        )

    def obtener_ultimo_run(self, task_id: str) -> RunPersistente | None:
        runs = self.listar_runs_tarea(task_id)
        return runs[-1] if runs else None

    def contar_ciclos(self, task_id: str) -> int:
        return len(self.listar_runs_tarea(task_id))

    def _comprobar_precondiciones(self, tarea: Tarea) -> list[str]:
        errores: list[str] = []
        if tarea.es_terminal:
            errores.append(f"tarea terminal: {tarea.estado.value}")
            return errores
        if tarea.estado is EstadoTarea.BLOQUEADA:
            errores.append("tarea bloqueada pendiente de recuperación explícita")
        reserva = self.gestor_entornos.obtener_reserva(tarea.worktree)
        if reserva is None:
            errores.append("worktree sin lock")
            return errores
        if reserva.task_id != tarea.id:
            errores.append(f"lock propiedad de otra tarea: {reserva.task_id}")
            return errores
        diagnostico = next(
            (
                item
                for item in self.gestor_entornos.diagnosticar_locks()
                if item.reserva.worktree_normalizado == reserva.worktree_normalizado
            ),
            None,
        )
        if diagnostico and diagnostico.posible_huerfano:
            errores.append("lock ambiguo: " + "; ".join(diagnostico.motivos))
            return errores
        resultado = self.gestor_entornos.comprobar_integridad_entorno(tarea.worktree)
        if not resultado.es_valido:
            errores.extend(resultado.discrepancias)
        return errores

    def _comprobar_resume(
        self,
        tarea: Tarea,
        run_pausado_id: str,
        decision: str | None,
        *,
        decision_id: str | None,
    ) -> list[str]:
        errores: list[str] = []
        try:
            anterior = self.obtener_run(run_pausado_id)
        except (RunNoEncontrado, ErrorPersistenciaRun) as exc:
            return [str(exc)]
        if anterior.task_id != tarea.id:
            errores.append("el run pausado pertenece a otra tarea")
        if anterior.estado_interno not in {
            EstadoInternoRun.REQUIERE_OK_PIO,
            EstadoInternoRun.PAUSA_PIO,
        }:
            errores.append("el run indicado no está pausado")
        if not isinstance(decision, str) or not decision.strip():
            errores.append("resume requiere una decisión explícita")
        requeridas = {
            evento.datos.get("decision_id")
            for evento in tarea.historial
            if evento.tipo == "DECISION_REQUIRED"
        }
        recibidas = {
            evento.datos.get("decision_id")
            for evento in tarea.historial
            if evento.tipo in {
                "DECISION_RECEIVED",
                "DECISION_APPLIED",
                "DECISION_CANCELLED",
            }
        }
        pendientes = {item for item in requeridas - recibidas if item}
        if pendientes and decision_id is None:
            errores.append("existe una decisión estructurada pendiente de respuesta")
        if decision_id is not None and decision_id not in recibidas:
            errores.append("la decisión estructurada no fue respondida")
        return errores

    def _comprobar_reintento(
        self,
        tarea: Tarea,
        run_origen_id: str,
        *,
        checkpoint_id: str | None,
        retry_id: str | None,
    ) -> list[str]:
        errores: list[str] = []
        if retry_id is None:
            errores.append("un reintento requiere retry_id")
        try:
            origen = self.obtener_run(run_origen_id)
        except (RunNoEncontrado, ErrorPersistenciaRun) as exc:
            return [str(exc)]
        if origen.task_id != tarea.id:
            errores.append("el run origen del retry pertenece a otra tarea")
        if origen.estado_interno is not EstadoInternoRun.INTERRUMPIDO:
            errores.append("el run origen del retry no está INTERRUMPIDO")
        if checkpoint_id is not None:
            try:
                _validar_uuid(checkpoint_id, "checkpoint_id")
            except ErrorPersistenciaRun as exc:
                errores.append(str(exc))
        return errores

    def _validar_despues(
        self, run: RunPersistente, tarea: Tarea
    ) -> tuple[bool, dict[str, Any]]:
        errores: list[str] = []
        reserva = self.gestor_entornos.obtener_reserva(tarea.worktree)
        if reserva is None:
            errores.append("lock desaparecido durante el run")
        elif reserva.task_id != tarea.id:
            errores.append(f"lock cambió de propietario: {reserva.task_id}")

        resultado_entorno = None
        if reserva is not None and reserva.task_id == tarea.id:
            resultado_entorno = self.gestor_entornos.comprobar_integridad_entorno(
                tarea.worktree
            )
            errores.extend(resultado_entorno.discrepancias)

        worktree = Path(tarea.worktree)
        snapshot_despues = None
        diff = None
        if not worktree.is_dir():
            errores.append("worktree inexistente al finalizar el run")
        else:
            try:
                snapshot_antes = _snapshot_desde_dict(run.snapshot_inicial)
                snapshot_despues = tomar_snapshot(worktree)
                diff = comparar_snapshots(snapshot_antes, snapshot_despues)
            except (SnapshotError, OSError) as exc:
                errores.append(f"snapshot final no disponible: {exc}")

        if diff is None:
            metadata = {
                "integridad_entorno": (
                    resultado_entorno.datos_evento() if resultado_entorno else None
                ),
                "snapshot_final": None,
                "cambios_run": None,
                "rutas_dentro_alcance": False,
                "errores_integridad": errores,
            }
            return False, metadata

        rutas_ok, problemas_rutas = validar_rutas(
            diff.paths_cambiados,
            rutas_permitidas=list(tarea.rutas_permitidas),
            rutas_protegidas=list(tarea.rutas_protegidas),
            permitir_escritura=tarea.modo.value == "workspace_write",
        )
        errores.extend(problemas_rutas)
        if diff.cambio_head:
            errores.append("HEAD cambió durante el run")
        if diff.cambio_rama:
            errores.append("rama cambió durante el run")
        if diff.cambio_staged:
            errores.append("índice Git cambió durante el run")
        metadata = {
            "integridad_entorno": (
                resultado_entorno.datos_evento() if resultado_entorno else None
            ),
            "snapshot_final": _snapshot_a_dict(snapshot_despues),
            "cambios_run": _diff_a_dict(diff),
            "rutas_dentro_alcance": rutas_ok,
            "errores_integridad": errores,
        }
        return not errores, metadata

    def _aplicar_estado_no_terminal(
        self,
        task_id: str,
        propuesta: EstadoTarea,
        estado_interno: EstadoInternoRun,
    ) -> None:
        # FINALIZADO es solo una propuesta: otra capa validará el cierre funcional.
        if (
            estado_interno is EstadoInternoRun.FINALIZADO
            and propuesta is not EstadoTarea.BLOQUEADA
        ):
            return
        tarea = self.gestor_tareas.cargar(task_id)
        if tarea.estado is propuesta:
            return
        self.gestor_tareas.actualizar_estado(tarea, propuesta)

    @staticmethod
    def _evento_para_resultado(estado: EstadoInternoRun) -> str:
        if estado in {EstadoInternoRun.REQUIERE_OK_PIO, EstadoInternoRun.PAUSA_PIO}:
            return "RUN_PAUSED"
        if estado is EstadoInternoRun.FALLIDO:
            return "RUN_FAILED"
        if estado is EstadoInternoRun.INTERRUMPIDO:
            return "RUN_INTERRUPTED"
        return "RUN_COMPLETED"

    def _crear_directorio_atomico(self, run: RunPersistente, destino: Path) -> None:
        self.directorio_runs.mkdir(parents=True, exist_ok=True)
        temporal = Path(
            tempfile.mkdtemp(prefix=f".{run.run_id}.", dir=self.directorio_runs)
        )
        try:
            self._escribir_json(temporal / "run.json", run.a_dict())
            os.replace(temporal, destino)
        except BaseException:
            shutil.rmtree(temporal, ignore_errors=True)
            raise

    def _guardar_run(self, run: RunPersistente) -> None:
        path = Path(run.directorio_run) / "run.json"
        if not path.is_file():
            raise ErrorPersistenciaRun(f"falta metadata del run: {path}")
        self._escribir_json(path, run.a_dict())

    def _cargar_path(self, path: Path) -> RunPersistente:
        try:
            with path.open("r", encoding="utf-8") as archivo:
                run = RunPersistente.desde_dict(json.load(archivo))
        except (OSError, json.JSONDecodeError, ErrorPersistenciaRun) as exc:
            raise ErrorPersistenciaRun(f"no se pudo cargar {path}: {exc}") from exc
        if Path(run.directorio_run).resolve() != path.parent.resolve():
            raise ErrorPersistenciaRun(f"directorio_run incoherente en {path}")
        return run

    @staticmethod
    def _escribir_json(path: Path, datos: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, nombre = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporal = Path(nombre)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(
                    datos,
                    archivo,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, path)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise
