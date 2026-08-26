"""Adaptadores inyectables para ejecutar un ciclo V0.2 fake o real in-process."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from threading import RLock
from time import monotonic
from typing import Any, Protocol

import orquestador
from contrato_ejecutor import (
    ContextoRetryEjecutor,
    EvidenciaRetryEjecutor,
    ValidacionCheckpointEjecutor,
)
from decisiones_persistentes import (
    DecisionPersistente,
    EstadoDecision,
    EstadoDecisionInvalido,
    GestorDecisiones,
)
from runs_persistentes import (
    EstadoInternoRun,
    GestorRuns,
    ResultadoRun,
    RunPersistente,
)
from tareas_persistentes import CapacidadCheckpoint, EstadoTarea, Tarea
from supervisor_v02 import (
    DecisionSupervisor,
    EvaluacionSupervisor,
    SolicitudAccion,
    SupervisorV02,
)


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class EjecucionRealProhibida(RuntimeError):
    """La suite normal intentó alcanzar accidentalmente Codex real."""


@dataclass(frozen=True)
class SalidaEjecucionCiclo:
    run_id: str
    task_id: str
    estado_interno: EstadoInternoRun
    inicio: str
    fin: str
    duracion_segundos: float
    return_code: int | None
    stdout: str
    stderr: str
    timeout: bool
    timeout_seconds: int
    tipo_error: str | None
    errores: tuple[str, ...]
    resumen: str
    siguiente_accion: str
    causa_pausa: str
    state_historico: dict[str, Any]
    procesos: tuple[dict[str, Any], ...]
    evidencia_retry: EvidenciaRetryEjecutor | None = None

    @property
    def fallo_tecnico(self) -> bool:
        return self.timeout or self.tipo_error is not None or self.return_code not in (0, None)

    def metadata(self, run_dir: Path) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "estado_interno": self.estado_interno.value,
            "inicio": self.inicio,
            "fin": self.fin,
            "duracion_segundos": self.duracion_segundos,
            "return_code": self.return_code,
            "timeout": self.timeout,
            "timeout_seconds": self.timeout_seconds,
            "tipo_error": self.tipo_error,
            "errores": list(self.errores),
            "stdout_path": str((run_dir / "stdout.txt").resolve()),
            "stderr_path": str((run_dir / "stderr.txt").resolve()),
            "stdout_chars": len(self.stdout),
            "stderr_chars": len(self.stderr),
            "state_historico": self.state_historico,
            "procesos": list(self.procesos),
            "evidencia_retry": (
                self.evidencia_retry.a_dict() if self.evidencia_retry else None
            ),
        }


class EjecutorCiclo(Protocol):
    def ejecutar(self, run: RunPersistente, tarea: Tarea) -> SalidaEjecucionCiclo:
        """Ejecuta exactamente una vez el ciclo asociado al run."""


_CHECKPOINT_AUTOMATICO = object()


class EjecutorCicloFake:
    """Fake determinista: nunca crea procesos ni accede a Codex/API."""

    def __init__(
        self,
        estado: EstadoInternoRun | str = EstadoInternoRun.AUTO_CONTINUE,
        *,
        stdout: str = "salida fake\n",
        stderr: str = "",
        return_code: int | None = 0,
        timeout: bool = False,
        timeout_seconds: int = 1800,
        tipo_error: str | None = None,
        errores: tuple[str, ...] = (),
        resumen: str = "Resultado fake",
        siguiente_accion: str = "",
        causa_pausa: str = "",
        excepcion: BaseException | None = None,
        capacidad_checkpoint: CapacidadCheckpoint | str = CapacidadCheckpoint.CHECKPOINT_RESUME,
        checkpoint_utilizado: str | None | object = _CHECKPOINT_AUTOMATICO,
        acciones_ejecutadas: tuple[str, ...] | None = None,
        state_historico: dict[str, Any] | None = None,
    ) -> None:
        self.estado = EstadoInternoRun(estado)
        self.stdout = stdout
        self.stderr = stderr
        self.return_code = return_code
        self.timeout = timeout
        self.timeout_seconds = timeout_seconds
        self.tipo_error = tipo_error
        self.errores = errores
        self.resumen = resumen
        self.siguiente_accion = siguiente_accion
        self.causa_pausa = causa_pausa
        self.excepcion = excepcion
        self.capacidad_checkpoint = CapacidadCheckpoint(capacidad_checkpoint)
        self.checkpoint_utilizado = checkpoint_utilizado
        self.acciones_ejecutadas = acciones_ejecutadas
        self.state_historico = dict(state_historico or {"fake": True})
        self.llamadas: list[tuple[str, str]] = []

    def ejecutar(self, run: RunPersistente, tarea: Tarea) -> SalidaEjecucionCiclo:
        salida = (
            self.ejecutar_resume(run, tarea)
            if run.resume_de is not None
            else self.ejecutar_ciclo_normal(run, tarea)
        )
        if run.retry_id is not None:
            contexto = ContextoRetryEjecutor.desde_dict(
                run.retry_id, run.retry_context
            )
            salida = replace(
                salida, evidencia_retry=self.consumir_retry_context(contexto)
            )
        return salida

    def ejecutar_ciclo_normal(
        self, run: RunPersistente, tarea: Tarea
    ) -> SalidaEjecucionCiclo:
        return self._ejecutar_base(run, tarea)

    def ejecutar_resume(
        self, run: RunPersistente, tarea: Tarea
    ) -> SalidaEjecucionCiclo:
        return self._ejecutar_base(run, tarea)

    def _ejecutar_base(
        self, run: RunPersistente, tarea: Tarea
    ) -> SalidaEjecucionCiclo:
        self.llamadas.append((run.run_id, tarea.id))
        if self.excepcion is not None:
            raise self.excepcion
        inicio = _ahora_utc()
        return SalidaEjecucionCiclo(
            run_id=run.run_id,
            task_id=tarea.id,
            estado_interno=self.estado,
            inicio=inicio,
            fin=_ahora_utc(),
            duracion_segundos=0.0,
            return_code=self.return_code,
            stdout=self.stdout,
            stderr=self.stderr,
            timeout=self.timeout,
            timeout_seconds=self.timeout_seconds,
            tipo_error=self.tipo_error,
            errores=tuple(self.errores),
            resumen=self.resumen,
            siguiente_accion=self.siguiente_accion,
            causa_pausa=self.causa_pausa,
            state_historico=self.state_historico,
            procesos=(),
        )

    def soporta_reintentos(self) -> bool:
        return self.capacidad_checkpoint is not CapacidadCheckpoint.NONE

    def validar_checkpoint(
        self, checkpoint: dict[str, Any], *, task_id: str, run_id: str
    ) -> ValidacionCheckpointEjecutor:
        if self.capacidad_checkpoint is not CapacidadCheckpoint.CHECKPOINT_RESUME:
            return ValidacionCheckpointEjecutor(
                False, "CHECKPOINT_UNSUPPORTED",
                "el ejecutor fake no declara CHECKPOINT_RESUME",
                errores=("capacidad incompatible",),
            )
        valido = (
            checkpoint.get("task_id") == task_id
            and checkpoint.get("run_id") == run_id
            and checkpoint.get("validado") is True
        )
        return ValidacionCheckpointEjecutor(
            valido,
            "CHECKPOINT_VALID" if valido else "CHECKPOINT_INVALID",
            "checkpoint aceptado" if valido else "checkpoint no pertenece al contexto",
            errores=() if valido else ("checkpoint incoherente",),
        )

    def construir_contexto_retry(
        self, contexto: ContextoRetryEjecutor
    ) -> dict[str, Any]:
        return contexto.a_dict()

    def consumir_retry_context(
        self, contexto: ContextoRetryEjecutor
    ) -> EvidenciaRetryEjecutor:
        if (
            contexto.estrategia == "RETRY_FROM_CHECKPOINT"
            and self.capacidad_checkpoint is CapacidadCheckpoint.CHECKPOINT_RESUME
        ):
            utilizado = (
                contexto.checkpoint_id
                if self.checkpoint_utilizado is _CHECKPOINT_AUTOMATICO
                else self.checkpoint_utilizado
            )
            omitidas = contexto.acciones_omitidas if utilizado else ()
            estrategia = "RETRY_FROM_CHECKPOINT"
        else:
            utilizado = None
            omitidas = ()
            estrategia = "RETRY_FULL_RUN"
        ejecutadas = (
            tuple(self.acciones_ejecutadas)
            if self.acciones_ejecutadas is not None
            else contexto.acciones_pendientes
        )
        posicion = None
        if contexto.checkpoint:
            payload = contexto.checkpoint.get("payload") or {}
            metadata = contexto.checkpoint.get("metadata") or {}
            posicion = metadata.get("posicion_reanudacion", payload.get("posicion_reanudacion"))
        return EvidenciaRetryEjecutor(
            checkpoint_id_recibido=contexto.checkpoint_id,
            checkpoint_id_utilizado=utilizado,
            estrategia_aplicada=estrategia,
            acciones_omitidas=omitidas,
            acciones_ejecutadas=ejecutadas,
            posicion_reanudacion=posicion,
        )


class EjecutorCicloReal:
    """Invoca `orquestador.ejecutar_ciclo` directamente, nunca otro orquestador."""

    def __init__(
        self,
        base_dir: str | Path,
        config: dict[str, Any],
        *,
        timeout_seconds: int | None = None,
        permitir_en_pytest: bool = False,
    ) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.config = dict(config)
        configurado = timeout_seconds or int(self.config.get("timeout_seconds", 1800))
        if configurado <= 0:
            raise ValueError("timeout_seconds debe ser positivo")
        self.timeout_seconds = configurado
        self.permitir_en_pytest = permitir_en_pytest
        self.capacidad_checkpoint = CapacidadCheckpoint.FULL_RUN_ONLY
        self.procesos_activos: dict[int, dict[str, Any]] = {}
        self.ultimo_pid: int | None = None

    def ejecutar(self, run: RunPersistente, tarea: Tarea) -> SalidaEjecucionCiclo:
        salida = (
            self.ejecutar_resume(run, tarea)
            if run.resume_de is not None
            else self.ejecutar_ciclo_normal(run, tarea)
        )
        if run.retry_id is not None:
            contexto = ContextoRetryEjecutor.desde_dict(
                run.retry_id, run.retry_context
            )
            salida = replace(
                salida, evidencia_retry=self.consumir_retry_context(contexto)
            )
        return salida

    def ejecutar_ciclo_normal(
        self, run: RunPersistente, tarea: Tarea
    ) -> SalidaEjecucionCiclo:
        return self._ejecutar_motor(run, tarea)

    def ejecutar_resume(
        self, run: RunPersistente, tarea: Tarea
    ) -> SalidaEjecucionCiclo:
        return self._ejecutar_motor(run, tarea)

    def soporta_reintentos(self) -> bool:
        return True

    def validar_checkpoint(
        self, checkpoint: dict[str, Any], *, task_id: str, run_id: str
    ) -> ValidacionCheckpointEjecutor:
        return ValidacionCheckpointEjecutor(
            False,
            "CHECKPOINT_UNSUPPORTED",
            "EjecutorCicloReal solo soporta retry completo",
            errores=("capacidad real FULL_RUN_ONLY",),
        )

    def construir_contexto_retry(
        self, contexto: ContextoRetryEjecutor
    ) -> dict[str, Any]:
        return contexto.a_dict()

    def consumir_retry_context(
        self, contexto: ContextoRetryEjecutor
    ) -> EvidenciaRetryEjecutor:
        return EvidenciaRetryEjecutor(
            checkpoint_id_recibido=contexto.checkpoint_id,
            checkpoint_id_utilizado=None,
            estrategia_aplicada="RETRY_FULL_RUN",
            acciones_omitidas=(),
            acciones_ejecutadas=contexto.acciones_pendientes,
        )

    def _ejecutar_motor(
        self, run: RunPersistente, tarea: Tarea
    ) -> SalidaEjecucionCiclo:
        if os.environ.get("PYTEST_CURRENT_TEST") and not self.permitir_en_pytest:
            raise EjecucionRealProhibida(
                "EjecutorCicloReal está bloqueado durante pytest; usa EjecutorCicloFake"
            )
        inicio = _ahora_utc()
        reloj = monotonic()
        procesos: list[dict[str, Any]] = []

        def observar(evento: str, datos: dict[str, Any]) -> None:
            registro = {"evento": evento, **datos}
            procesos.append(registro)
            pid = datos.get("pid")
            if isinstance(pid, int):
                self.ultimo_pid = pid
                if evento == "PROCESS_STARTED":
                    self.procesos_activos[pid] = registro
                else:
                    self.procesos_activos.pop(pid, None)
            self._persistir_procesos(run, procesos)

        config = dict(self.config)
        config["repo"] = tarea.worktree
        config["timeout_seconds"] = self.timeout_seconds
        protegidas = list(config.get("rutas_protegidas", []))
        config["rutas_protegidas"] = list(dict.fromkeys([*protegidas, *tarea.rutas_protegidas]))
        tarea_historica = {
            "id": tarea.id,
            "objetivo": tarea.objetivo,
            "modo": tarea.modo.value,
            "rutas_permitidas": list(tarea.rutas_permitidas),
            "rutas_protegidas": list(tarea.rutas_protegidas),
            "restricciones": list(tarea.contrato.restricciones_adicionales),
            "criterio_finalizacion": tarea.condicion_finalizacion,
            "nivel_recurso": self._nivel_recurso(tarea),
            "nivel_tests": self._nivel_tests(tarea),
            "coste_estimado": self._coste_estimado(tarea),
            "autorizacion_coste": self._autorizacion_coste(tarea),
            "archivos_candidatos": list(tarea.rutas_permitidas),
            "tests_relevantes": [],
            "session_id": run.entorno.get("session_id"),
            "retry": run.retry_id is not None,
            "contexto_retry": dict(run.retry_context or {}),
            "contexto_codex_previo": self._contexto_codex_previo(run),
        }
        state = {
            "version": "0.2.4",
            "task_id": tarea.id,
            "run_id": run.run_id,
            "run_dir": run.directorio_run,
            "ciclo": 0,
            "status": "INICIADO",
            "head_inicial": run.head_observado,
            "branch_inicial": run.branch_observada,
            "siguiente_instruccion": tarea.objetivo,
            "created_at": run.timestamp,
        }
        try:
            status, state = orquestador.ejecutar_ciclo(
                base_dir=self.base_dir,
                config=config,
                tarea=tarea_historica,
                state=state,
                run_dir=Path(run.directorio_run),
                decision_pio=run.decision_resume,
                observador_proceso=observar,
            )
            stdout, stderr = self._recoger_salidas(Path(run.directorio_run))
            decision = state.get("ultima_decision_supervisor") or {}
            resumen = (
                decision.get("motivo", "")
                if isinstance(decision, dict)
                else ""
            )
            return SalidaEjecucionCiclo(
                run.run_id,
                tarea.id,
                EstadoInternoRun(status),
                inicio,
                _ahora_utc(),
                round(monotonic() - reloj, 6),
                0,
                stdout,
                stderr,
                False,
                self.timeout_seconds,
                None,
                (),
                resumen or f"Motor histórico devolvió {status}",
                state.get("siguiente_instruccion", ""),
                decision.get("detalle", "") if isinstance(decision, dict) else "",
                state,
                tuple(procesos),
            )
        except subprocess.TimeoutExpired as exc:
            stdout_archivo, stderr_archivo = self._recoger_salidas(Path(run.directorio_run))
            stdout = self._texto_timeout(exc.output) or stdout_archivo
            stderr = self._texto_timeout(exc.stderr) or stderr_archivo
            return self._fallo(
                run,
                tarea,
                inicio,
                reloj,
                stdout,
                stderr,
                "CODEX_TIMEOUT",
                f"Codex superó el timeout configurado de {self.timeout_seconds}s",
                state,
                procesos,
                timeout=True,
            )
        except orquestador.OrquestadorError as exc:
            stdout, stderr = self._recoger_salidas(Path(run.directorio_run))
            codigo = self._extraer_return_code(str(exc))
            return self._fallo(
                run,
                tarea,
                inicio,
                reloj,
                stdout,
                stderr,
                "CODEX_PROCESS_ERROR" if "Codex" in str(exc) else "MOTOR_ERROR",
                str(exc),
                state,
                procesos,
                return_code=codigo,
            )
        except Exception as exc:
            stdout, stderr = self._recoger_salidas(Path(run.directorio_run))
            return self._fallo(
                run,
                tarea,
                inicio,
                reloj,
                stdout,
                stderr,
                "ADAPTER_ERROR",
                f"{type(exc).__name__}: {exc}",
                state,
                procesos,
            )

    @staticmethod
    def _nivel_recurso(tarea: Tarea) -> str:
        evento = next(
            (
                item for item in reversed(tarea.historial)
                if item.tipo in {"RETRY_RESOURCE_CLASSIFIED", "RESOURCE_CLASSIFIED"}
                and item.datos.get("nivel_recurso")
            ),
            None,
        )
        return str(evento.datos["nivel_recurso"]) if evento else "CODEX_STANDARD"

    @staticmethod
    def _nivel_tests(tarea: Tarea) -> str | None:
        evento = next(
            (
                item for item in reversed(tarea.historial)
                if item.tipo in {"RETRY_RESOURCE_CLASSIFIED", "RESOURCE_CLASSIFIED"}
                and item.datos.get("nivel_tests")
            ),
            None,
        )
        return str(evento.datos["nivel_tests"]) if evento else None

    @staticmethod
    def _coste_estimado(tarea: Tarea) -> Any:
        evento = next(
            (
                item for item in reversed(tarea.historial)
                if item.tipo in {"RETRY_RESOURCE_CLASSIFIED", "RESOURCE_CLASSIFIED"}
                and item.datos.get("coste_estimado") is not None
            ),
            None,
        )
        return evento.datos["coste_estimado"] if evento else None

    @staticmethod
    def _autorizacion_coste(tarea: Tarea) -> bool:
        return any(
            evento.tipo == "RESOURCE_COST_AUTHORIZATION_GRANTED"
            for evento in tarea.historial
        )

    @staticmethod
    def _contexto_codex_previo(run: RunPersistente) -> dict[str, Any] | None:
        if run.retry_de is None:
            return None
        directorio_runs = Path(run.directorio_run).parent
        coincidencias = list(directorio_runs.glob(f"*_{run.retry_de}/run.json"))
        if len(coincidencias) != 1:
            return None
        try:
            datos_run = json.loads(coincidencias[0].read_text(encoding="utf-8"))
            if datos_run.get("task_id") != run.task_id:
                return None
            estado_path = coincidencias[0].parent / "state.json"
            estado = json.loads(estado_path.read_text(encoding="utf-8"))
            contexto = estado.get("contexto_codex")
            return dict(contexto) if isinstance(contexto, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _fallo(
        self,
        run: RunPersistente,
        tarea: Tarea,
        inicio: str,
        reloj: float,
        stdout: str,
        stderr: str,
        tipo_error: str,
        error: str,
        state: dict[str, Any],
        procesos: list[dict[str, Any]],
        *,
        timeout: bool = False,
        return_code: int | None = None,
    ) -> SalidaEjecucionCiclo:
        return SalidaEjecucionCiclo(
            run.run_id,
            tarea.id,
            EstadoInternoRun.FALLIDO,
            inicio,
            _ahora_utc(),
            round(monotonic() - reloj, 6),
            return_code,
            stdout,
            stderr,
            timeout,
            self.timeout_seconds,
            tipo_error,
            (error,),
            error,
            "revisar el fallo técnico antes de reintentar",
            tipo_error,
            state,
            tuple(procesos),
        )

    @staticmethod
    def _recoger_salidas(run_dir: Path) -> tuple[str, str]:
        def combinar(patron: str) -> str:
            bloques: list[str] = []
            for path in sorted(run_dir.glob(f"ciclo_*/{patron}")):
                bloques.append(f"===== {path.relative_to(run_dir)} =====\n")
                bloques.append(path.read_text(encoding="utf-8", errors="replace"))
                if not bloques[-1].endswith("\n"):
                    bloques.append("\n")
            return "".join(bloques)

        return combinar("*.stdout.txt"), combinar("*.stderr.txt")

    @staticmethod
    def _extraer_return_code(mensaje: str) -> int | None:
        coincidencia = re.search(r"código\s+(-?\d+)", mensaje, flags=re.IGNORECASE)
        return int(coincidencia.group(1)) if coincidencia else None

    @staticmethod
    def _texto_timeout(valor: str | bytes | None) -> str:
        if valor is None:
            return ""
        return valor.decode("utf-8", errors="replace") if isinstance(valor, bytes) else valor

    @staticmethod
    def _persistir_procesos(
        run: RunPersistente, procesos: list[dict[str, Any]]
    ) -> None:
        run_dir = Path(run.directorio_run)
        destino = run_dir / "procesos.json"
        descriptor, nombre = tempfile.mkstemp(
            prefix=".procesos.", suffix=".tmp", dir=run_dir
        )
        temporal = Path(nombre)
        payload = {
            "run_id": run.run_id,
            "task_id": run.task_id,
            "session_id": run.entorno.get("session_id"),
            "actualizado": _ahora_utc(),
            "procesos": procesos,
        }
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(payload, archivo, ensure_ascii=False, indent=2, allow_nan=False)
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, destino)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise


@dataclass(frozen=True)
class EjecucionRunCompletada:
    salida: SalidaEjecucionCiclo
    resultado: ResultadoRun
    decision: DecisionPersistente | None = None
    evaluacion_supervisor: EvaluacionSupervisor | None = None
    auto_resume: "EjecucionRunCompletada | None" = None


class ServicioEjecucionRuns:
    """Orquesta una única invocación inyectada y persiste todos sus artefactos."""

    def __init__(
        self,
        gestor_runs: GestorRuns,
        gestor_decisiones: GestorDecisiones | None = None,
        supervisor: SupervisorV02 | None = None,
    ) -> None:
        self.gestor_runs = gestor_runs
        self.gestor_decisiones = gestor_decisiones or GestorDecisiones(
            gestor_runs.gestor_tareas,
            gestor_runs,
            gestor_runs.gestor_tareas.directorio.parent / "decisiones",
        )
        self.supervisor = supervisor

    def ejecutar_run(
        self,
        run_id: str,
        ejecutor: EjecutorCiclo,
        *,
        condiciones_funcionales_validadas: bool = False,
        auto_resumes_restantes: int = 8,
    ) -> EjecucionRunCompletada:
        run = self.gestor_runs.iniciar_run(run_id)
        tarea = self.gestor_runs.gestor_tareas.cargar(run.task_id)
        errores_contrato = self._validar_contrato_retry_antes(run, ejecutor)
        if errores_contrato:
            timestamp = _ahora_utc()
            salida = SalidaEjecucionCiclo(
                run.run_id,
                run.task_id,
                EstadoInternoRun.FALLIDO,
                timestamp,
                _ahora_utc(),
                0.0,
                None,
                "",
                "\n".join(errores_contrato) + "\n",
                False,
                0,
                "RETRY_CONTRACT_INVALID",
                tuple(errores_contrato),
                "El ejecutor no cumple el contrato del retry",
                "usar un ejecutor con capacidad compatible",
                "contrato de retry incompatible",
                {},
                (),
            )
        else:
            try:
                salida = ejecutor.ejecutar(run, tarea)
            except BaseException as exc:
                timestamp = _ahora_utc()
                salida = SalidaEjecucionCiclo(
                    run.run_id,
                    run.task_id,
                    EstadoInternoRun.FALLIDO,
                    timestamp,
                    _ahora_utc(),
                    0.0,
                    None,
                    "",
                    f"{type(exc).__name__}: {exc}\n",
                    isinstance(exc, subprocess.TimeoutExpired),
                    0,
                    "EXECUTOR_EXCEPTION",
                    (f"{type(exc).__name__}: {exc}",),
                    "El ejecutor lanzó una excepción",
                    "revisar el adaptador",
                    "error del adaptador",
                    {},
                    (),
                )

        salida = self._normalizar_salida(run, salida)
        salida = self._validar_evidencia_retry_despues(run, salida)
        metricas_consumo = salida.state_historico.get("metricas_consumo_codex")
        if isinstance(metricas_consumo, dict):
            tarea_actual = self.gestor_runs.gestor_tareas.cargar(run.task_id)
            if not any(
                evento.tipo == "CODEX_USAGE_RECORDED"
                and evento.datos.get("run_id") == run.run_id
                for evento in tarea_actual.historial
            ):
                self.gestor_runs.gestor_tareas.anadir_evento(
                    run.task_id,
                    "CODEX_USAGE_RECORDED",
                    {"run_id": run.run_id, **metricas_consumo},
                )
        metadata = self._persistir_salida(run, salida)
        estado = EstadoInternoRun.FALLIDO if salida.fallo_tecnico else salida.estado_interno
        resultado = self.gestor_runs.registrar_resultado(
            run.run_id,
            estado,
            resumen=salida.resumen,
            errores=salida.errores,
            siguiente_accion=salida.siguiente_accion,
            causa_pausa=salida.causa_pausa,
            condiciones_funcionales_validadas=condiciones_funcionales_validadas,
            metadata={"ejecucion": metadata},
        )
        decision = None
        evaluacion = None
        auto_resume = None
        if resultado.requiere_decision:
            evaluacion, decision, auto_resume = self._supervisar_pausa(
                salida, resultado, ejecutor,
                auto_resumes_restantes=auto_resumes_restantes,
            )
        return EjecucionRunCompletada(
            salida, resultado, decision, evaluacion, auto_resume
        )

    def _supervisar_pausa(
        self,
        salida: SalidaEjecucionCiclo,
        resultado: ResultadoRun,
        ejecutor: EjecutorCiclo,
        *,
        auto_resumes_restantes: int,
    ) -> tuple[EvaluacionSupervisor | None, DecisionPersistente | None, EjecucionRunCompletada | None]:
        if self.supervisor is None:
            return None, self._crear_decision_si_corresponde(salida, resultado), None
        datos = salida.state_historico.get("solicitud_supervisor")
        if not isinstance(datos, dict):
            datos = {
                "tipo_accion": "DECISION_FUNCIONAL",
                "ambito": "GENERAL",
                "datos": {},
                "contexto": salida.causa_pausa or salida.resumen,
                "clasificacion": "FUNCIONAL",
            }
        solicitud = SolicitudAccion.desde_dict(datos, task_id=resultado.task_id)
        evaluacion = self.supervisor.evaluar(solicitud)
        if evaluacion.decision is DecisionSupervisor.REQUIRE_PIO:
            return evaluacion, self._crear_decision_si_corresponde(salida, resultado), None
        if evaluacion.decision is DecisionSupervisor.BLOCK:
            tarea = self.gestor_runs.gestor_tareas.cargar(resultado.task_id)
            if tarea.estado is not EstadoTarea.BLOQUEADA:
                self.gestor_runs.gestor_tareas.actualizar_estado(tarea, EstadoTarea.BLOQUEADA)
            return evaluacion, None, None
        if auto_resumes_restantes <= 0:
            tarea = self.gestor_runs.gestor_tareas.cargar(resultado.task_id)
            if tarea.estado is not EstadoTarea.BLOQUEADA:
                self.gestor_runs.gestor_tareas.actualizar_estado(tarea, EstadoTarea.BLOQUEADA)
            self.gestor_runs.gestor_tareas.anadir_evento(
                resultado.task_id,
                "ACTION_BLOCKED",
                {
                    "evaluation_id": evaluacion.evaluation_id,
                    "codigo": "AUTO_RESUME_LIMIT_REACHED",
                },
            )
            limitada = replace(
                evaluacion,
                decision=DecisionSupervisor.BLOCK,
                codigo="ACTION_BLOCKED",
                motivo="límite de auto-resumes consecutivos alcanzado",
                warnings=(*evaluacion.warnings, "AUTO_RESUME_LIMIT_REACHED"),
            )
            return limitada, None, None
        tarea = self.gestor_runs.gestor_tareas.cargar(resultado.task_id)
        if tarea.estado is not EstadoTarea.ESPERANDO_DECISION:
            return evaluacion, None, None
        respuesta = json.dumps(
            {"supervisor": evaluacion.a_dict()}, ensure_ascii=False, sort_keys=True
        )
        preparacion = self.gestor_runs.preparar_resume(
            resultado.task_id, resultado.run_id, respuesta
        )
        if not preparacion.exito or preparacion.run is None:
            self.gestor_runs.gestor_tareas.anadir_evento(
                resultado.task_id,
                "RESUME_PRECONDITION_FAILED",
                {"evaluation_id": evaluacion.evaluation_id, "errores": list(preparacion.errores)},
            )
            return evaluacion, None, None
        self.gestor_runs.gestor_tareas.anadir_evento(
            resultado.task_id,
            "SUPERVISOR_AUTO_RESUME",
            {
                "evaluation_id": evaluacion.evaluation_id,
                "rule_id": evaluacion.regla_aplicada,
                "run_origen": resultado.run_id,
                "run_resume": preparacion.run.run_id,
            },
        )
        auto_resume = self.ejecutar_run(
            preparacion.run.run_id, ejecutor,
            auto_resumes_restantes=auto_resumes_restantes - 1,
        )
        return evaluacion, None, auto_resume

    @staticmethod
    def _validar_contrato_retry_antes(
        run: RunPersistente, ejecutor: EjecutorCiclo
    ) -> list[str]:
        if run.retry_id is None:
            return []
        capacidad = getattr(ejecutor, "capacidad_checkpoint", CapacidadCheckpoint.NONE)
        try:
            capacidad = CapacidadCheckpoint(capacidad)
        except ValueError:
            return ["capacidad_checkpoint del ejecutor es inválida"]
        contexto = ContextoRetryEjecutor.desde_dict(run.retry_id, run.retry_context)
        if capacidad is CapacidadCheckpoint.NONE:
            return ["el ejecutor declara capacidad NONE"]
        if contexto.estrategia == "RETRY_FROM_CHECKPOINT":
            if capacidad is not CapacidadCheckpoint.CHECKPOINT_RESUME:
                return ["RETRY_FROM_CHECKPOINT requiere ejecutor CHECKPOINT_RESUME"]
            validar = getattr(ejecutor, "validar_checkpoint", None)
            if not callable(validar) or contexto.checkpoint is None:
                return ["el ejecutor no puede validar el checkpoint recibido"]
            validacion = validar(
                contexto.checkpoint,
                task_id=run.task_id,
                run_id=run.retry_de,
            )
            if not isinstance(validacion, ValidacionCheckpointEjecutor) or not validacion.valido:
                errores = getattr(validacion, "errores", ())
                return list(errores) or ["checkpoint rechazado por el ejecutor"]
        return []

    @staticmethod
    def _validar_evidencia_retry_despues(
        run: RunPersistente, salida: SalidaEjecucionCiclo
    ) -> SalidaEjecucionCiclo:
        if run.retry_id is None or salida.fallo_tecnico:
            return salida
        contexto = ContextoRetryEjecutor.desde_dict(run.retry_id, run.retry_context)
        evidencia = salida.evidencia_retry
        errores: list[str] = []
        if evidencia is None:
            errores.append("el ejecutor no devolvió evidencia de retry")
        elif contexto.estrategia == "RETRY_FROM_CHECKPOINT":
            if evidencia.checkpoint_id_recibido != contexto.checkpoint_id:
                errores.append("checkpoint recibido no coincide con el plan")
            if evidencia.checkpoint_id_utilizado != contexto.checkpoint_id:
                errores.append("checkpoint utilizado no coincide con el plan")
            if evidencia.estrategia_aplicada != "RETRY_FROM_CHECKPOINT":
                errores.append("estrategia aplicada no confirma checkpoint resume")
            if evidencia.acciones_omitidas != contexto.acciones_omitidas:
                errores.append("acciones omitidas no coinciden con el checkpoint")
            if evidencia.acciones_ejecutadas != contexto.acciones_pendientes:
                errores.append("acciones ejecutadas no coinciden con las pendientes")
        else:
            if evidencia.checkpoint_id_utilizado is not None:
                errores.append("FULL_RUN no puede afirmar reutilización de checkpoint")
            if evidencia.estrategia_aplicada != "RETRY_FULL_RUN":
                errores.append("evidencia no confirma RETRY_FULL_RUN")
            if evidencia.acciones_omitidas:
                errores.append("FULL_RUN no puede declarar acciones omitidas")
        if not errores:
            return salida
        return replace(
            salida,
            estado_interno=EstadoInternoRun.FALLIDO,
            tipo_error="RETRY_EVIDENCE_INVALID",
            errores=(*salida.errores, *errores),
            resumen="Evidencia de retry inválida",
            siguiente_accion="revisar contrato y evidencia del ejecutor",
            causa_pausa="evidencia retry no verificable",
        )

    def _crear_decision_si_corresponde(
        self,
        salida: SalidaEjecucionCiclo,
        resultado: ResultadoRun,
    ) -> DecisionPersistente | None:
        if not resultado.requiere_decision:
            return None
        if resultado.estado_v02_propuesto is not EstadoTarea.ESPERANDO_DECISION:
            return None
        decision_historica = salida.state_historico.get(
            "ultima_decision_supervisor", {}
        )
        if not isinstance(decision_historica, dict):
            decision_historica = {}
        pregunta = (
            decision_historica.get("pregunta_para_pio")
            or salida.resumen
            or "Se requiere una decisión estructurada para continuar."
        )
        opciones = decision_historica.get("opciones_para_pio") or ()
        if not isinstance(opciones, (list, tuple)):
            opciones = ()
        return self.gestor_decisiones.crear_decision(
            task_id=resultado.task_id,
            run_id=resultado.run_id,
            pregunta=pregunta,
            contexto=salida.causa_pausa or salida.resumen,
            opciones_permitidas=opciones,
            metadata={
                "estado_interno": resultado.estado_interno.value,
                "siguiente_accion": salida.siguiente_accion,
            },
        )

    @staticmethod
    def _normalizar_salida(
        run: RunPersistente, salida: SalidaEjecucionCiclo
    ) -> SalidaEjecucionCiclo:
        if salida.run_id == run.run_id and salida.task_id == run.task_id:
            return salida
        errores = (*salida.errores, "IDs devueltos por el ejecutor no coinciden con el run")
        return SalidaEjecucionCiclo(
            run.run_id,
            run.task_id,
            EstadoInternoRun.FALLIDO,
            salida.inicio,
            salida.fin,
            salida.duracion_segundos,
            salida.return_code,
            salida.stdout,
            salida.stderr,
            salida.timeout,
            salida.timeout_seconds,
            "EXECUTOR_ID_MISMATCH",
            errores,
            salida.resumen,
            salida.siguiente_accion,
            "error de asociación",
            salida.state_historico,
            salida.procesos,
        )

    def _persistir_salida(
        self, run: RunPersistente, salida: SalidaEjecucionCiclo
    ) -> dict[str, Any]:
        run_dir = Path(run.directorio_run)
        self._escribir_texto(run_dir / "stdout.txt", salida.stdout)
        self._escribir_texto(run_dir / "stderr.txt", salida.stderr)
        metadata = salida.metadata(run_dir)
        self._escribir_json(run_dir / "execution.json", metadata)
        return metadata

    @staticmethod
    def _escribir_texto(path: Path, contenido: str) -> None:
        descriptor, nombre = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporal = Path(nombre)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                archivo.write(contenido)
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, path)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise

    @classmethod
    def _escribir_json(cls, path: Path, datos: dict[str, Any]) -> None:
        cls._escribir_texto(
            path,
            json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        )


class ErrorReanudacionDecision(RuntimeError):
    """Las precondiciones impiden aplicar una decisión sin ejecutar el motor."""


@dataclass(frozen=True)
class ResultadoReanudacionDecision:
    decision: DecisionPersistente
    run: RunPersistente | None
    ejecucion: EjecucionRunCompletada | None
    aplicada_ahora: bool
    idempotente: bool
    errores: tuple[str, ...]


class ServicioDecisiones:
    """Valida una respuesta y reanuda automáticamente el motor in-process."""

    def __init__(
        self,
        gestor_decisiones: GestorDecisiones,
        gestor_runs: GestorRuns,
    ) -> None:
        if gestor_decisiones.gestor_runs is not gestor_runs:
            raise ValueError("los gestores de decisiones y runs deben coincidir")
        self.gestor_decisiones = gestor_decisiones
        self.gestor_runs = gestor_runs
        self.servicio_runs = ServicioEjecucionRuns(gestor_runs, gestor_decisiones)
        self._lock_aplicacion = RLock()

    def responder_y_reanudar(
        self,
        decision_id: str,
        ejecutor: EjecutorCiclo,
        *,
        opcion: str | None = None,
        texto: str | None = None,
        metadata_respuesta: dict[str, Any] | None = None,
        task_id_esperado: str | None = None,
        run_id_esperado: str | None = None,
    ) -> ResultadoReanudacionDecision:
        decision = self.gestor_decisiones.responder_decision(
            decision_id,
            opcion=opcion,
            texto=texto,
            metadata_respuesta=metadata_respuesta,
        )
        return self.aplicar_decision(
            decision.decision_id,
            ejecutor,
            task_id_esperado=task_id_esperado,
            run_id_esperado=run_id_esperado,
        )

    def aplicar_decision(
        self,
        decision_id: str,
        ejecutor: EjecutorCiclo,
        *,
        task_id_esperado: str | None = None,
        run_id_esperado: str | None = None,
    ) -> ResultadoReanudacionDecision:
        with self._lock_aplicacion:
            decision = self.gestor_decisiones.obtener_decision(decision_id)
            if decision.estado is EstadoDecision.APLICADA:
                run = (
                    self.gestor_runs.obtener_run(decision.resume_run_id)
                    if decision.resume_run_id
                    else None
                )
                return ResultadoReanudacionDecision(
                    decision, run, None, False, True, ()
                )
            errores = self._validar_precondiciones(
                decision,
                task_id_esperado=task_id_esperado,
                run_id_esperado=run_id_esperado,
            )
            if errores:
                self.gestor_runs.gestor_tareas.anadir_evento(
                    decision.task_id,
                    "RESUME_PRECONDITION_FAILED",
                    {
                        "decision_id": decision.decision_id,
                        "run_id": decision.run_id,
                        "errores": errores,
                    },
                )
                raise ErrorReanudacionDecision("; ".join(errores))

            respuesta_motor = self.gestor_decisiones.respuesta_para_motor(decision)
            preparacion = self.gestor_runs.preparar_resume(
                decision.task_id,
                decision.run_id,
                respuesta_motor,
                decision_id=decision.decision_id,
            )
            if not preparacion.exito or preparacion.run is None:
                errores = list(preparacion.errores) or ["resume no preparado"]
                self.gestor_runs.gestor_tareas.anadir_evento(
                    decision.task_id,
                    "RESUME_PRECONDITION_FAILED",
                    {
                        "decision_id": decision.decision_id,
                        "run_id": decision.run_id,
                        "errores": errores,
                    },
                )
                raise ErrorReanudacionDecision("; ".join(errores))

            run = preparacion.run
            if run.estado_interno is not EstadoInternoRun.PREPARADO:
                if run.resultado is None:
                    raise ErrorReanudacionDecision(
                        "el run asociado a la decisión quedó iniciado sin resultado"
                    )
                aplicada = self.gestor_decisiones.aplicar_decision(
                    decision.decision_id, run.run_id
                )
                return ResultadoReanudacionDecision(
                    aplicada, run, None, True, True, ()
                )

            ejecucion = self.servicio_runs.ejecutar_run(run.run_id, ejecutor)
            aplicada = self.gestor_decisiones.aplicar_decision(
                decision.decision_id, run.run_id
            )
            return ResultadoReanudacionDecision(
                aplicada,
                self.gestor_runs.obtener_run(run.run_id),
                ejecucion,
                True,
                False,
                (),
            )

    def cancelar_decision(self, decision_id: str) -> DecisionPersistente:
        return self.gestor_decisiones.cancelar_decision(decision_id)

    def _validar_precondiciones(
        self,
        decision: DecisionPersistente,
        *,
        task_id_esperado: str | None,
        run_id_esperado: str | None,
    ) -> list[str]:
        errores: list[str] = []
        if decision.estado is not EstadoDecision.RESPONDIDA:
            errores.append(
                f"decisión no respondida: {decision.estado.value}"
            )
        if task_id_esperado is not None and decision.task_id != task_id_esperado:
            errores.append("la decisión pertenece a otra tarea")
        if run_id_esperado is not None and decision.run_id != run_id_esperado:
            errores.append("la decisión pertenece a otro run origen")
        try:
            tarea = self.gestor_runs.gestor_tareas.cargar(decision.task_id)
        except Exception as exc:
            return [f"tarea no disponible: {exc}"]
        if tarea.es_terminal:
            errores.append(f"tarea terminal: {tarea.estado.value}")
        elif tarea.estado is not EstadoTarea.ESPERANDO_DECISION:
            errores.append(
                f"tarea no está ESPERANDO_DECISION: {tarea.estado.value}"
            )
        try:
            origen = self.gestor_runs.obtener_run(decision.run_id)
        except Exception as exc:
            errores.append(f"run origen no disponible: {exc}")
        else:
            if origen.task_id != decision.task_id:
                errores.append("el run origen pertenece a otra tarea")
            if origen.estado_interno not in {
                EstadoInternoRun.REQUIERE_OK_PIO,
                EstadoInternoRun.PAUSA_PIO,
            }:
                errores.append("el run origen no está pausado")
        pendiente = self.gestor_decisiones.obtener_decision_pendiente(decision.task_id)
        if pendiente is not None and pendiente.decision_id != decision.decision_id:
            errores.append(
                f"existe otra decisión pendiente: {pendiente.decision_id}"
            )
        return errores
