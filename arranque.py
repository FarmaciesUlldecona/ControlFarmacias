"""Arranque controlado del Orquestador V0.2.7 antes de aceptar ejecuciones."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable
from uuid import uuid4

from checkpoints_persistentes import GestorCheckpoints
from contabilidad_recursos import ContabilidadRecursos
from decisiones_persistentes import GestorDecisiones
from ejecucion_v02 import EjecutorCiclo, EjecucionRunCompletada, ServicioEjecucionRuns
from entornos import GestorEntornos
from recuperacion import (
    AccionRecuperacion,
    InspectorProcesos,
    ResultadoRecuperacionTarea,
    ServicioRecuperacion,
)
from reintentos_persistentes import ServicioReintentos
from reglas_persistentes import GestorReglas
from runs_persistentes import GestorRuns
from supervisor_v02 import SupervisorV02
from tareas_persistentes import EstadoTarea, GestorTareas, Tarea


class EstadoGlobalOrquestador(str, Enum):
    INICIANDO = "INICIANDO"
    RECUPERANDO = "RECUPERANDO"
    LISTO = "LISTO"
    BLOQUEADO = "BLOQUEADO"


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ResultadoArranque:
    estado_global: EstadoGlobalOrquestador
    tareas_inspeccionadas: int
    tareas_recuperadas: int
    tareas_bloqueadas: int
    tareas_esperando_decision: int
    tareas_activas_detectadas: int
    locks_validos: int
    locks_ambiguos: int
    errores: tuple[str, ...]
    warnings: tuple[str, ...]
    timestamp: str
    resultados_tareas: tuple[ResultadoRecuperacionTarea, ...]

    def a_dict(self) -> dict[str, Any]:
        return {
            "estado_global": self.estado_global.value,
            "tareas_inspeccionadas": self.tareas_inspeccionadas,
            "tareas_recuperadas": self.tareas_recuperadas,
            "tareas_bloqueadas": self.tareas_bloqueadas,
            "tareas_esperando_decision": self.tareas_esperando_decision,
            "tareas_activas_detectadas": self.tareas_activas_detectadas,
            "locks_validos": self.locks_validos,
            "locks_ambiguos": self.locks_ambiguos,
            "errores": list(self.errores),
            "warnings": list(self.warnings),
            "timestamp": self.timestamp,
            "resultados_tareas": [item.__dict__ for item in self.resultados_tareas],
        }


@dataclass(frozen=True)
class ResultadoEjecucionControlada:
    exito: bool
    codigo: str
    estado_global: EstadoGlobalOrquestador
    ejecucion: EjecucionRunCompletada | None
    errores: tuple[str, ...]


class ServicioArranque:
    """Inicializa almacenamiento, fuerza recovery y abre la puerta de ejecución."""

    def __init__(
        self,
        base_dir: str | Path,
        *,
        inspector_procesos: InspectorProcesos | None = None,
        ejecutor_factory: Callable[[Tarea], EjecutorCiclo] | None = None,
        al_cambiar_estado: Callable[[EstadoGlobalOrquestador], None] | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        estado = self.base_dir / "estado"
        self.gestor_tareas = GestorTareas(estado / "tareas")
        self.gestor_entornos = GestorEntornos(self.gestor_tareas, estado / "locks")
        self.gestor_runs = GestorRuns(
            self.gestor_tareas, self.gestor_entornos, self.base_dir / "runs"
        )
        self.gestor_decisiones = GestorDecisiones(
            self.gestor_tareas, self.gestor_runs, estado / "decisiones"
        )
        self.gestor_reglas = GestorReglas(estado / "reglas")
        self.contabilidad_recursos = ContabilidadRecursos(estado / "presupuestos")
        self.supervisor = SupervisorV02(self.gestor_reglas, self.gestor_tareas)
        self.gestor_checkpoints = GestorCheckpoints(
            self.gestor_tareas, self.gestor_runs, estado / "checkpoints"
        )
        self.servicio_recuperacion = ServicioRecuperacion(
            self.gestor_tareas,
            self.gestor_entornos,
            self.gestor_runs,
            self.gestor_decisiones,
            self.gestor_checkpoints,
            inspector_procesos=inspector_procesos,
        )
        self.estado_global = EstadoGlobalOrquestador.INICIANDO
        self.ejecutor_factory = ejecutor_factory
        self.al_cambiar_estado = al_cambiar_estado
        self._resultado: ResultadoArranque | None = None
        self._startup_id = str(uuid4())
        self.directorio_auditoria = estado / "orquestador"
        self.servicio_reintentos = ServicioReintentos(
            self.gestor_tareas,
            self.gestor_entornos,
            self.gestor_runs,
            self.gestor_checkpoints,
            estado / "retries",
            estado_listo=lambda: self.estado_global is EstadoGlobalOrquestador.LISTO,
            ejecutor_factory=ejecutor_factory,
            contabilidad_recursos=self.contabilidad_recursos,
        )

    def obtener_estado_global(self) -> EstadoGlobalOrquestador:
        return self.estado_global

    def iniciar_orquestador(self) -> ResultadoArranque:
        if self._resultado is not None:
            return self._resultado
        self._cambiar_estado(EstadoGlobalOrquestador.INICIANDO)
        self._evento_global("ORCHESTRATOR_STARTING")
        self._comprobar_almacenamiento()
        self._cambiar_estado(EstadoGlobalOrquestador.RECUPERANDO)
        self._evento_global("ORCHESTRATOR_RECOVERY_STARTED")
        errores: list[str] = []
        try:
            # Durante RECUPERANDO no se inicia trabajo nuevo. Las continuaciones
            # candidatas quedan reflejadas y podrán autorizarse una vez LISTO.
            resultados = tuple(self.servicio_recuperacion.recuperar_estado(None))
        except Exception as exc:
            resultados = ()
            errores.append(f"{type(exc).__name__}: {exc}")
        bloqueadas = sum(
            item.estado_resultante == EstadoTarea.BLOQUEADA.value
            or item.accion_realizada == AccionRecuperacion.BLOQUEADA.value
            for item in resultados
        )
        esperando = sum(
            item.estado_resultante == EstadoTarea.ESPERANDO_DECISION.value
            for item in resultados
        )
        ambiguos = sum(not item.lock_valido for item in resultados) + len(
            self.servicio_recuperacion.ultimo_diagnostico_locks
        )
        warnings = [warning for item in resultados for warning in item.warnings]
        warnings.extend(self.servicio_recuperacion.ultimo_diagnostico_locks)
        final = (
            EstadoGlobalOrquestador.BLOQUEADO
            if errores or bloqueadas or ambiguos
            else EstadoGlobalOrquestador.LISTO
        )
        self._cambiar_estado(final)
        self._evento_global(
            "ORCHESTRATOR_BLOCKED" if final is EstadoGlobalOrquestador.BLOQUEADO else "ORCHESTRATOR_READY"
        )
        self._resultado = ResultadoArranque(
            estado_global=final,
            tareas_inspeccionadas=len(resultados),
            tareas_recuperadas=sum(item.recuperacion_automatica for item in resultados),
            tareas_bloqueadas=bloqueadas,
            tareas_esperando_decision=esperando,
            tareas_activas_detectadas=sum(item.proceso_detectado for item in resultados),
            locks_validos=sum(item.lock_valido for item in resultados),
            locks_ambiguos=ambiguos,
            errores=tuple(errores),
            warnings=tuple(dict.fromkeys(warnings)),
            timestamp=_ahora_utc(),
            resultados_tareas=resultados,
        )
        self._persistir_resultado(self._resultado)
        return self._resultado

    def ejecutar_run_controlado(
        self, run_id: str, ejecutor: EjecutorCiclo
    ) -> ResultadoEjecucionControlada:
        if self.estado_global is not EstadoGlobalOrquestador.LISTO:
            return ResultadoEjecucionControlada(
                False,
                "ORCHESTRATOR_NOT_READY",
                self.estado_global,
                None,
                (f"estado global actual: {self.estado_global.value}",),
            )
        try:
            ejecucion = ServicioEjecucionRuns(
                self.gestor_runs, self.gestor_decisiones, self.supervisor
            ).ejecutar_run(run_id, ejecutor)
        except Exception as exc:
            return ResultadoEjecucionControlada(
                False, "RUN_EXECUTION_REJECTED", self.estado_global, None,
                (f"{type(exc).__name__}: {exc}",),
            )
        return ResultadoEjecucionControlada(
            True, "RUN_EXECUTED", self.estado_global, ejecucion, ()
        )

    def _cambiar_estado(self, estado: EstadoGlobalOrquestador) -> None:
        self.estado_global = estado
        if self.al_cambiar_estado is not None:
            self.al_cambiar_estado(estado)

    def _comprobar_almacenamiento(self) -> None:
        self.directorio_auditoria.mkdir(parents=True, exist_ok=True)
        prueba = self.directorio_auditoria / ".storage-check.tmp"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()

    def _evento_global(self, tipo: str) -> None:
        path = self.directorio_auditoria / "eventos.json"
        self.directorio_auditoria.mkdir(parents=True, exist_ok=True)
        eventos: list[dict[str, Any]] = []
        if path.is_file():
            eventos = json.loads(path.read_text(encoding="utf-8"))
        datos = {"tipo": tipo, "startup_id": self._startup_id}
        if any(item.get("tipo") == tipo and item.get("startup_id") == self._startup_id for item in eventos):
            return
        eventos.append({**datos, "timestamp": _ahora_utc()})
        self._escribir_json(path, eventos)

    def _persistir_resultado(self, resultado: ResultadoArranque) -> None:
        self._escribir_json(
            self.directorio_auditoria / "arranque.json", resultado.a_dict()
        )

    @staticmethod
    def _escribir_json(path: Path, datos: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, nombre = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporal = Path(nombre)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(datos, archivo, ensure_ascii=False, indent=2, allow_nan=False)
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, path)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise


def iniciar_orquestador(
    base_dir: str | Path, **kwargs: Any
) -> tuple[ServicioArranque, ResultadoArranque]:
    servicio = ServicioArranque(base_dir, **kwargs)
    return servicio, servicio.iniciar_orquestador()
