"""Reconstrucción durable y conservadora del Orquestador V0.2.6."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
from typing import Any, Callable, Protocol

import orquestador
from checkpoints_persistentes import GestorCheckpoints
from decisiones_persistentes import EstadoDecision, GestorDecisiones
from ejecucion_v02 import EjecutorCiclo, ServicioDecisiones, ServicioEjecucionRuns
from entornos import GestorEntornos, ReservaWorktree, validar_entorno
from orquestador_snapshot import SnapshotError, comparar_snapshots, tomar_snapshot
from runs_persistentes import (
    EstadoInternoRun,
    GestorRuns,
    RunPersistente,
    _snapshot_desde_dict,
)
from tareas_persistentes import EstadoTarea, GestorTareas, Tarea


class AccionRecuperacion(str, Enum):
    SIN_ACCION = "SIN_ACCION"
    ESPERANDO_DECISION = "ESPERANDO_DECISION"
    DECISION_REANUDADA = "DECISION_REANUDADA"
    RUN_PREPARADO_INICIADO = "RUN_PREPARADO_INICIADO"
    PROCESO_ACTIVO = "PROCESO_ACTIVO"
    RUN_RECONCILIADO = "RUN_RECONCILIADO"
    RUN_INTERRUMPIDO = "RUN_INTERRUMPIDO"
    BLOQUEADA = "BLOQUEADA"


@dataclass(frozen=True)
class ProcesoObservado:
    pid: int
    existe: bool
    executable: str | None = None
    command_line: str | None = None
    inicio: str | None = None


class InspectorProcesos(Protocol):
    def inspeccionar(self, pid: int) -> ProcesoObservado:
        """Inspecciona sin modificar ni señalizar el proceso."""


class InspectorProcesosSistema:
    """Comprobación portable mínima; sin identidad suficiente queda ambigua."""

    def inspeccionar(self, pid: int) -> ProcesoObservado:
        if not isinstance(pid, int) or pid <= 0:
            return ProcesoObservado(pid, False)
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, OSError):
            return ProcesoObservado(pid, False)
        return ProcesoObservado(pid, True)


@dataclass(frozen=True)
class ResultadoRecuperacionTarea:
    task_id: str
    estado_previo: str
    estado_resultante: str
    accion_realizada: str
    run_id: str | None
    decision_id: str | None
    proceso_detectado: bool
    lock_valido: bool
    entorno_valido: bool
    recuperacion_automatica: bool
    requiere_intervencion: bool
    causa: str
    warnings: tuple[str, ...]
    checkpoint_id: str | None = None


class ServicioRecuperacion:
    """Reconcilia evidencia persistida sin matar procesos ni modificar Git."""

    EVENTOS_RECOVERY = frozenset(
        {
            "RECOVERY_STARTED",
            "RECOVERY_COMPLETED",
            "RECOVERY_BLOCKED",
            "RECOVERY_RUN_RECONCILED",
            "RECOVERY_DECISION_RESUMED",
            "RECOVERY_PROCESS_FOUND",
            "RECOVERY_PROCESS_MISSING",
            "RECOVERY_LOCK_VALIDATED",
            "RECOVERY_LOCK_AMBIGUOUS",
            "ENTORNO_CAMBIADO_DESPUES_DEL_RUN",
        }
    )

    def __init__(
        self,
        gestor_tareas: GestorTareas,
        gestor_entornos: GestorEntornos,
        gestor_runs: GestorRuns,
        gestor_decisiones: GestorDecisiones,
        gestor_checkpoints: GestorCheckpoints | None = None,
        *,
        inspector_procesos: InspectorProcesos | None = None,
    ) -> None:
        self.gestor_tareas = gestor_tareas
        self.gestor_entornos = gestor_entornos
        self.gestor_runs = gestor_runs
        self.gestor_decisiones = gestor_decisiones
        self.gestor_checkpoints = gestor_checkpoints or GestorCheckpoints(
            gestor_tareas,
            gestor_runs,
            gestor_tareas.directorio.parent / "checkpoints",
        )
        self.inspector_procesos = inspector_procesos or InspectorProcesosSistema()
        self.ultimo_diagnostico_locks: tuple[str, ...] = ()

    def recuperar_estado(
        self,
        ejecutor_factory: Callable[[Tarea], EjecutorCiclo] | None = None,
    ) -> list[ResultadoRecuperacionTarea]:
        tareas = [tarea for tarea in self.gestor_tareas.listar() if not tarea.es_terminal]
        ids = {tarea.id for tarea in self.gestor_tareas.listar()}
        self.ultimo_diagnostico_locks = tuple(
            f"lock sin tarea: {reserva.worktree_normalizado} ({reserva.task_id})"
            for reserva in self.gestor_entornos.listar_reservas()
            if reserva.task_id not in ids
        )
        return [self._recuperar_tarea(tarea, ejecutor_factory) for tarea in tareas]

    def _recuperar_tarea(
        self,
        tarea: Tarea,
        ejecutor_factory: Callable[[Tarea], EjecutorCiclo] | None,
    ) -> ResultadoRecuperacionTarea:
        previo = tarea.estado
        run = self.gestor_runs.obtener_ultimo_run(tarea.id)
        decisiones = self.gestor_decisiones.listar_decisiones(tarea.id)
        decision = next(
            (item for item in reversed(decisiones) if item.estado is EstadoDecision.RESPONDIDA),
            None,
        ) or next(
            (item for item in reversed(decisiones) if item.estado is EstadoDecision.PENDIENTE),
            None,
        )
        checkpoint = self.gestor_checkpoints.obtener_ultimo_checkpoint(
            task_id=tarea.id, run_id=run.run_id if run else None
        )
        if self._es_read_only_cerrado(tarea, run, decision):
            return self._cerrar_read_only_historico(tarea, previo, run, checkpoint)
        lock_ok, entorno_ok, causa_lock, warnings = self._validar_lock_entorno(tarea, run)
        if not lock_ok or not entorno_ok:
            return self._bloquear(
                tarea,
                previo,
                run,
                decision.decision_id if decision else None,
                causa_lock,
                warnings,
                lock_ok,
                entorno_ok,
                checkpoint.checkpoint_id if checkpoint else None,
            )

        # Una decisión pendiente es una espera válida y nunca ejecuta.
        if decision is not None and decision.estado is EstadoDecision.PENDIENTE:
            return self._resultado(
                tarea.id, previo, AccionRecuperacion.ESPERANDO_DECISION, run,
                decision.decision_id, False, True, True, False, False,
                "decisión pendiente conservada", warnings, checkpoint
            )

        # Crash entre DECISION_RECEIVED y DECISION_APPLIED.
        if decision is not None and decision.estado is EstadoDecision.RESPONDIDA:
            # La aplicación pudo crear e iniciar el resume antes del crash. En
            # ese caso se reconcilia ese run, nunca se intenta iniciarlo otra vez.
            if (
                run is not None
                and run.decision_id == decision.decision_id
                and run.estado_interno is EstadoInternoRun.INICIADO
            ):
                recuperado = self._recuperar_iniciado(
                    tarea, previo, run, warnings, checkpoint
                )
                run_actual = self.gestor_runs.obtener_run(run.run_id)
                if (
                    run_actual.resultado is not None
                    and run_actual.estado_interno is not EstadoInternoRun.INTERRUMPIDO
                ):
                    self.gestor_decisiones.aplicar_decision(
                        decision.decision_id, run_actual.run_id
                    )
                    self._evento_unico(
                        tarea.id,
                        "RECOVERY_DECISION_RESUMED",
                        {"decision_id": decision.decision_id, "run_id": run_actual.run_id},
                    )
                return recuperado
            if ejecutor_factory is None:
                return self._resultado(
                    tarea.id, previo, AccionRecuperacion.SIN_ACCION, run,
                    decision.decision_id, False, True, True, False, True,
                    "decisión respondida lista para reanudar; falta ejecutor inyectado",
                    warnings, checkpoint,
                )
            self._evento_unico(tarea.id, "RECOVERY_STARTED", {"decision_id": decision.decision_id})
            reanudacion = ServicioDecisiones(
                self.gestor_decisiones, self.gestor_runs
            ).aplicar_decision(
                decision.decision_id,
                ejecutor_factory(self.gestor_tareas.cargar(tarea.id)),
                task_id_esperado=tarea.id,
                run_id_esperado=decision.run_id,
            )
            run = reanudacion.run or run
            self._evento_unico(
                tarea.id,
                "RECOVERY_DECISION_RESUMED",
                {"decision_id": decision.decision_id, "run_id": run.run_id if run else None},
            )
            self._evento_unico(tarea.id, "RECOVERY_COMPLETED", {"decision_id": decision.decision_id})
            return self._resultado(
                tarea.id, previo, AccionRecuperacion.DECISION_REANUDADA, run,
                decision.decision_id, False, True, True, True, False,
                "decisión respondida aplicada exactamente una vez", warnings, checkpoint,
            )

        if run is None:
            return self._resultado(
                tarea.id, previo, AccionRecuperacion.SIN_ACCION, None, None, False,
                True, True, False, False, "tarea activa sin runs", warnings, checkpoint
            )

        if run.resultado is not None:
            cambiado = self._reconciliar_resultado(tarea, run)
            if cambiado:
                self._evento_unico(tarea.id, "RECOVERY_STARTED", {"run_id": run.run_id})
                self._evento_unico(tarea.id, "RECOVERY_RUN_RECONCILED", {"run_id": run.run_id})
                self._evento_unico(tarea.id, "RECOVERY_COMPLETED", {"run_id": run.run_id})
            return self._resultado(
                tarea.id, previo,
                AccionRecuperacion.RUN_RECONCILIADO if cambiado else AccionRecuperacion.SIN_ACCION,
                run, None, False, True, True, cambiado, False,
                "resultado persistido reconciliado" if cambiado else "run ya reconciliado",
                warnings, checkpoint,
            )

        if run.estado_interno is EstadoInternoRun.PREPARADO:
            if ejecutor_factory is None:
                return self._resultado(
                    tarea.id, previo, AccionRecuperacion.SIN_ACCION, run, None, False,
                    True, True, False, True,
                    "run preparado listo; falta ejecutor inyectado", warnings, checkpoint,
                )
            self._evento_unico(tarea.id, "RECOVERY_STARTED", {"run_id": run.run_id})
            ServicioEjecucionRuns(self.gestor_runs, self.gestor_decisiones).ejecutar_run(
                run.run_id, ejecutor_factory(self.gestor_tareas.cargar(tarea.id))
            )
            self._evento_unico(tarea.id, "RECOVERY_COMPLETED", {"run_id": run.run_id})
            return self._resultado(
                tarea.id, previo, AccionRecuperacion.RUN_PREPARADO_INICIADO,
                self.gestor_runs.obtener_run(run.run_id), None, False, True, True,
                True, False, "mismo run preparado iniciado", warnings, checkpoint,
            )

        if run.estado_interno is EstadoInternoRun.INICIADO:
            return self._recuperar_iniciado(tarea, previo, run, warnings, checkpoint)

        return self._resultado(
            tarea.id, previo, AccionRecuperacion.SIN_ACCION, run, None, False,
            True, True, False, False, "sin acción pendiente", warnings, checkpoint,
        )

    @staticmethod
    def _es_read_only_cerrado(
        tarea: Tarea, run: RunPersistente | None, decision: Any
    ) -> bool:
        return bool(
            tarea.modo.value == "read_only"
            and run is not None
            and run.retry_id is None
            and run.estado_interno is EstadoInternoRun.FINALIZADO
            and run.resultado is not None
            and not run.resultado.requiere_decision
            and not run.resultado.errores
            and decision is None
        )

    def _cerrar_read_only_historico(
        self,
        tarea: Tarea,
        previo: EstadoTarea,
        run: RunPersistente,
        checkpoint: Any,
    ) -> ResultadoRecuperacionTarea:
        entorno = validar_entorno(tarea)
        warnings: list[str] = []
        if not entorno.es_valido:
            detalle = "; ".join(entorno.discrepancias)
            warnings.append(f"ENTORNO_CAMBIADO_DESPUES_DEL_RUN: {detalle}")
            self._evento_unico(
                tarea.id,
                "ENTORNO_CAMBIADO_DESPUES_DEL_RUN",
                {"run_id": run.run_id, "detalle": detalle},
            )

        actual = self.gestor_tareas.cargar(tarea.id)
        if actual.estado is EstadoTarea.BLOQUEADA:
            actual = self.gestor_tareas.actualizar_estado(
                actual, EstadoTarea.RECUPERANDO
            )
        if actual.estado in {EstadoTarea.RECUPERANDO, EstadoTarea.TRABAJANDO}:
            actual = self.gestor_tareas.actualizar_estado(
                actual, EstadoTarea.FINALIZADA
            )

        reserva = self.gestor_entornos.obtener_reserva(tarea.worktree)
        if reserva is not None and reserva.task_id == tarea.id and actual.es_terminal:
            self.gestor_entornos.liberar_worktree(tarea.id, tarea.worktree)

        self._evento_unico(tarea.id, "RECOVERY_STARTED", {"run_id": run.run_id})
        self._evento_unico(
            tarea.id, "RECOVERY_RUN_RECONCILED", {"run_id": run.run_id}
        )
        self._evento_unico(tarea.id, "RECOVERY_COMPLETED", {"run_id": run.run_id})
        return self._resultado(
            tarea.id,
            previo,
            AccionRecuperacion.RUN_RECONCILIADO,
            run,
            None,
            False,
            True,
            entorno.es_valido,
            True,
            False,
            "run read_only cerrado reconciliado sin depender del HEAD actual",
            tuple(warnings),
            checkpoint,
        )

    def _validar_lock_entorno(
        self, tarea: Tarea, run: RunPersistente | None
    ) -> tuple[bool, bool, str, tuple[str, ...]]:
        reserva = self.gestor_entornos.obtener_reserva(tarea.worktree)
        if reserva is None:
            return False, validar_entorno(tarea).es_valido, "worktree sin lock", ()
        if reserva.task_id != tarea.id:
            return False, False, f"lock propiedad de otra tarea: {reserva.task_id}", ()
        entorno = validar_entorno(tarea)
        if not entorno.es_valido:
            return True, False, "; ".join(entorno.discrepancias), ()
        warnings: list[str] = []
        if reserva.session_id != self.gestor_entornos.session_id:
            observado = self.inspector_procesos.inspeccionar(reserva.process_id)
            if observado.existe:
                self._evento_unico(
                    tarea.id, "RECOVERY_LOCK_AMBIGUOUS",
                    {"pid": reserva.process_id, "session_id": reserva.session_id},
                )
                return False, True, "lock de otra sesión con PID existente o ambiguo", ()
            self.gestor_entornos.reclamar_worktree_recuperacion(tarea.id, tarea.worktree)
            self._evento_unico(
                tarea.id, "RECOVERY_LOCK_VALIDATED",
                {"session_id_anterior": reserva.session_id},
            )
            warnings.append("lock huérfano adoptado de forma controlada")
        conflicto = self._validar_workspace(tarea, run)
        if conflicto:
            return True, False, conflicto, tuple(warnings)
        return True, True, "lock y entorno válidos", tuple(warnings)

    def _validar_workspace(self, tarea: Tarea, run: RunPersistente | None) -> str | None:
        if run is None:
            return None
        # Un proceso aún en curso puede estar escribiendo dentro del alcance; su
        # identidad se valida después y nunca se lanza un segundo ejecutor.
        if run.estado_interno is EstadoInternoRun.INICIADO and run.resultado is None:
            return None
        try:
            diff = comparar_snapshots(
                _snapshot_desde_dict(run.snapshot_inicial),
                tomar_snapshot(Path(tarea.worktree)),
            )
        except (SnapshotError, OSError, ValueError) as exc:
            return f"snapshot no verificable: {exc}"
        conocidos: set[str] = set()
        if run.resultado is not None:
            cambios = run.resultado.metadata.get("cambios_run") or {}
            conocidos = set(cambios.get("paths_cambiados") or ())
        if not diff.hay_cambios:
            return (
                "cambios conocidos del run ya no están presentes"
                if conocidos
                else None
            )
        if conocidos != diff.paths_cambiados:
            return "cambios de workspace inesperados o no explicados"
        rutas_ok, _ = orquestador.validar_rutas(
            diff.paths_cambiados,
            rutas_permitidas=list(tarea.rutas_permitidas),
            rutas_protegidas=list(tarea.rutas_protegidas),
            permitir_escritura=tarea.modo.value == "workspace_write",
        )
        return None if rutas_ok else "cambios conocidos fuera del alcance contratado"

    def _recuperar_iniciado(
        self,
        tarea: Tarea,
        previo: EstadoTarea,
        run: RunPersistente,
        warnings: tuple[str, ...],
        checkpoint: Any,
    ) -> ResultadoRecuperacionTarea:
        proceso, esperado = self._proceso_persistido(run)
        if proceso is not None:
            observado = self.inspector_procesos.inspeccionar(proceso["pid"])
            if observado.existe and self._identidad_coincide(observado, proceso, run):
                self._evento_unico(
                    tarea.id, "RECOVERY_PROCESS_FOUND",
                    {"run_id": run.run_id, "pid": proceso["pid"]},
                )
                return self._resultado(
                    tarea.id, previo, AccionRecuperacion.PROCESO_ACTIVO, run, None,
                    True, True, True, False, False,
                    "proceso del run verificado y aún activo", warnings, checkpoint,
                )
            if observado.existe:
                return self._bloquear(
                    tarea, previo, run, None,
                    "PID existente pero identidad del proceso ambigua; no se mata",
                    warnings, True, True,
                    checkpoint.checkpoint_id if checkpoint else None,
                    evento="RECOVERY_LOCK_AMBIGUOUS",
                )
        self._evento_unico(
            tarea.id, "RECOVERY_PROCESS_MISSING",
            {"run_id": run.run_id, "pid": proceso.get("pid") if proceso else None,
             "evidencia_proceso": esperado},
        )
        self._evento_unico(tarea.id, "RECOVERY_STARTED", {"run_id": run.run_id})
        evidencia = self._evidencia_ejecucion(run)
        if evidencia is not None:
            estado = EstadoInternoRun(evidencia["estado_interno"])
            if evidencia.get("return_code") not in (0, None):
                estado = EstadoInternoRun.FALLIDO
            resultado = self.gestor_runs.registrar_resultado(
                run.run_id,
                estado,
                resumen="resultado completo recuperado desde execution.json",
                errores=tuple(evidencia.get("errores") or ()),
                metadata={"ejecucion": evidencia, "recuperado": True},
            )
            if (
                resultado.estado_v02_propuesto is EstadoTarea.ESPERANDO_DECISION
                and not any(
                    item.run_id == run.run_id
                    for item in self.gestor_decisiones.listar_decisiones(tarea.id)
                )
            ):
                state = evidencia.get("state_historico") or {}
                historica = state.get("ultima_decision_supervisor") or {}
                if not isinstance(historica, dict):
                    historica = {}
                opciones = historica.get("opciones_para_pio") or ()
                if not isinstance(opciones, (list, tuple)):
                    opciones = ()
                self.gestor_decisiones.crear_decision(
                    task_id=tarea.id,
                    run_id=run.run_id,
                    pregunta=historica.get("pregunta_para_pio")
                    or "Se requiere una decisión para continuar el run recuperado.",
                    contexto="pausa reconstruida desde execution.json",
                    opciones_permitidas=opciones,
                    metadata={"recuperado": True},
                )
            self._evento_unico(tarea.id, "RECOVERY_RUN_RECONCILED", {"run_id": run.run_id})
            self._evento_unico(tarea.id, "RECOVERY_COMPLETED", {"run_id": run.run_id})
            return self._resultado(
                tarea.id, previo, AccionRecuperacion.RUN_RECONCILIADO,
                self.gestor_runs.obtener_run(run.run_id), None, False, True, True,
                True, False, "ejecución completa reconciliada sin relanzar", warnings,
                checkpoint,
            )
        self.gestor_runs.registrar_resultado(
            run.run_id,
            EstadoInternoRun.INTERRUMPIDO,
            resumen="proceso desaparecido sin evidencia final completa",
            errores=("run interrumpido durante cierre/crash",),
            siguiente_accion="evaluar reintento futuro desde checkpoint",
            metadata={"recuperado": True},
        )
        return self._resultado(
            tarea.id, previo, AccionRecuperacion.RUN_INTERRUMPIDO,
            self.gestor_runs.obtener_run(run.run_id), None, False, True, True,
            True, True, "run interrumpido; no se presume éxito", warnings, checkpoint,
        )

    @staticmethod
    def _proceso_persistido(run: RunPersistente) -> tuple[dict[str, Any] | None, bool]:
        path = Path(run.directorio_run) / "procesos.json"
        if not path.is_file():
            return None, False
        try:
            datos = json.loads(path.read_text(encoding="utf-8"))
            if datos.get("run_id") != run.run_id or datos.get("task_id") != run.task_id:
                return None, False
            activos: dict[int, dict[str, Any]] = {}
            for evento in datos.get("procesos", []):
                pid = evento.get("pid")
                if not isinstance(pid, int):
                    continue
                if evento.get("evento") == "PROCESS_STARTED":
                    activos[pid] = evento
                else:
                    activos.pop(pid, None)
            return (list(activos.values())[-1], True) if activos else (None, True)
        except (OSError, json.JSONDecodeError, TypeError):
            return None, False

    @staticmethod
    def _identidad_coincide(
        observado: ProcesoObservado, proceso: dict[str, Any], run: RunPersistente
    ) -> bool:
        comando = proceso.get("comando") or []
        if not comando or not observado.executable or not observado.command_line:
            return False
        esperado = Path(str(comando[0])).name.casefold()
        real = Path(observado.executable).name.casefold()
        comando_real = observado.command_line.casefold()
        return esperado == real and (
            run.run_id.casefold() in comando_real
            or str(Path(run.directorio_run)).casefold() in comando_real
        )

    @staticmethod
    def _evidencia_ejecucion(run: RunPersistente) -> dict[str, Any] | None:
        run_dir = Path(run.directorio_run)
        path = run_dir / "execution.json"
        if not path.is_file() or not (run_dir / "stdout.txt").is_file() or not (run_dir / "stderr.txt").is_file():
            return None
        try:
            datos = json.loads(path.read_text(encoding="utf-8"))
            if datos.get("run_id") != run.run_id or datos.get("task_id") != run.task_id:
                return None
            if not datos.get("inicio") or not datos.get("fin"):
                return None
            estado = EstadoInternoRun(datos.get("estado_interno"))
            if estado not in {
                EstadoInternoRun.AUTO_CONTINUE, EstadoInternoRun.REQUIERE_OK_PIO,
                EstadoInternoRun.PAUSA_PIO, EstadoInternoRun.FINALIZADO,
                EstadoInternoRun.FALLIDO,
            }:
                return None
            return datos
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def _reconciliar_resultado(self, tarea: Tarea, run: RunPersistente) -> bool:
        propuesta = run.resultado.estado_v02_propuesto
        if run.estado_interno is EstadoInternoRun.FINALIZADO and propuesta is EstadoTarea.FINALIZADA:
            propuesta = EstadoTarea.TRABAJANDO
        actual = self.gestor_tareas.cargar(tarea.id)
        if actual.estado is propuesta:
            return False
        self._evento_unico(tarea.id, "RECOVERY_STARTED", {"run_id": run.run_id})
        actual = self.gestor_tareas.cargar(tarea.id)
        if actual.estado is EstadoTarea.BLOQUEADA and propuesta is not EstadoTarea.BLOQUEADA:
            actual = self.gestor_tareas.actualizar_estado(actual, EstadoTarea.RECUPERANDO)
        self.gestor_tareas.actualizar_estado(actual, propuesta)
        return True

    def _bloquear(
        self,
        tarea: Tarea,
        previo: EstadoTarea,
        run: RunPersistente | None,
        decision_id: str | None,
        causa: str,
        warnings: tuple[str, ...],
        lock_ok: bool,
        entorno_ok: bool,
        checkpoint_id: str | None,
        *,
        evento: str = "RECOVERY_BLOCKED",
    ) -> ResultadoRecuperacionTarea:
        actual = self.gestor_tareas.cargar(tarea.id)
        if actual.estado is not EstadoTarea.BLOQUEADA:
            if actual.estado is EstadoTarea.PREPARANDO:
                actual = self.gestor_tareas.actualizar_estado(actual, EstadoTarea.BLOQUEADA)
            elif actual.estado in {
                EstadoTarea.TRABAJANDO, EstadoTarea.ESPERANDO_DECISION,
                EstadoTarea.RECUPERANDO,
            }:
                actual = self.gestor_tareas.actualizar_estado(actual, EstadoTarea.BLOQUEADA)
        self._evento_unico(
            tarea.id, evento,
            {"run_id": run.run_id if run else None, "causa": causa},
        )
        if evento != "RECOVERY_BLOCKED":
            self._evento_unico(
                tarea.id, "RECOVERY_BLOCKED",
                {"run_id": run.run_id if run else None, "causa": causa},
            )
        return ResultadoRecuperacionTarea(
            tarea.id, previo.value, self.gestor_tareas.cargar(tarea.id).estado.value,
            AccionRecuperacion.BLOQUEADA.value, run.run_id if run else None,
            decision_id, False, lock_ok, entorno_ok, False, True, causa, warnings,
            checkpoint_id,
        )

    def _evento_unico(self, task_id: str, tipo: str, datos: dict[str, Any]) -> None:
        tarea = self.gestor_tareas.cargar(task_id)
        if any(evento.tipo == tipo and evento.datos == datos for evento in tarea.historial):
            return
        self.gestor_tareas.anadir_evento(task_id, tipo, datos)

    def _resultado(
        self,
        task_id: str,
        previo: EstadoTarea,
        accion: AccionRecuperacion,
        run: RunPersistente | None,
        decision_id: str | None,
        proceso: bool,
        lock_ok: bool,
        entorno_ok: bool,
        automatica: bool,
        intervencion: bool,
        causa: str,
        warnings: tuple[str, ...],
        checkpoint: Any,
    ) -> ResultadoRecuperacionTarea:
        return ResultadoRecuperacionTarea(
            task_id=task_id,
            estado_previo=previo.value,
            estado_resultante=self.gestor_tareas.cargar(task_id).estado.value,
            accion_realizada=accion.value,
            run_id=run.run_id if run else None,
            decision_id=decision_id,
            proceso_detectado=proceso,
            lock_valido=lock_ok,
            entorno_valido=entorno_ok,
            recuperacion_automatica=automatica,
            requiere_intervencion=intervencion,
            causa=causa,
            warnings=warnings,
            checkpoint_id=checkpoint.checkpoint_id if checkpoint else None,
        )
