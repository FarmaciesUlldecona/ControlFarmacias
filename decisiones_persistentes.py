"""Decisiones persistentes y estructuradas para pausas de V0.2.5."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable
from uuid import UUID, uuid4

from runs_persistentes import EstadoInternoRun, GestorRuns, RunNoEncontrado
from tareas_persistentes import EstadoTarea, GestorTareas, TareaNoEncontrada


DECISION_SCHEMA_VERSION = 1


class ErrorDecision(RuntimeError):
    """Error base de decisiones V0.2.5."""


class DecisionNoEncontrada(ErrorDecision, FileNotFoundError):
    """No existe la decisión solicitada."""


class DecisionInvalida(ErrorDecision, ValueError):
    """La decisión o respuesta no cumple el contrato estructurado."""


class EstadoDecisionInvalido(ErrorDecision):
    """La operación no corresponde al estado actual de la decisión."""


class ConflictoDecisionPendiente(ErrorDecision):
    """Una tarea ya tiene otra decisión pendiente principal."""


class ErrorPersistenciaDecision(ErrorDecision):
    """La representación persistida de una decisión no es válida."""


class TipoDecision(str, Enum):
    DECISION_FUNCIONAL = "DECISION_FUNCIONAL"
    AUTORIZACION_ALCANCE = "AUTORIZACION_ALCANCE"
    AUTORIZACION_COSTE = "AUTORIZACION_COSTE"
    AUTORIZACION_COMMIT = "AUTORIZACION_COMMIT"
    AUTORIZACION_PUSH = "AUTORIZACION_PUSH"
    OTRA = "OTRA"


class EstadoDecision(str, Enum):
    PENDIENTE = "PENDIENTE"
    RESPONDIDA = "RESPONDIDA"
    APLICADA = "APLICADA"
    CANCELADA = "CANCELADA"


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validar_uuid(valor: Any, campo: str) -> None:
    try:
        UUID(valor)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ErrorPersistenciaDecision(f"{campo} debe ser un UUID válido") from exc


def _validar_timestamp(valor: Any, campo: str, *, opcional: bool = False) -> None:
    if opcional and valor is None:
        return
    if not isinstance(valor, str):
        raise ErrorPersistenciaDecision(f"{campo} debe ser texto ISO-8601")
    try:
        fecha = datetime.fromisoformat(valor)
    except ValueError as exc:
        raise ErrorPersistenciaDecision(f"{campo} no es ISO-8601 válido") from exc
    if fecha.tzinfo is None:
        raise ErrorPersistenciaDecision(f"{campo} debe incluir zona horaria")


def _textos(valor: Iterable[str], campo: str) -> tuple[str, ...]:
    if isinstance(valor, str):
        raise DecisionInvalida(f"{campo} debe ser una colección de textos")
    resultado = tuple(valor)
    if not all(isinstance(item, str) and item.strip() for item in resultado):
        raise DecisionInvalida(f"{campo} debe contener textos no vacíos")
    if len(set(resultado)) != len(resultado):
        raise DecisionInvalida(f"{campo} no admite duplicados")
    return resultado


@dataclass(frozen=True)
class DecisionPersistente:
    decision_id: str
    task_id: str
    run_id: str
    tipo: TipoDecision
    pregunta: str
    contexto: str
    opciones_permitidas: tuple[str, ...]
    estado: EstadoDecision
    respuesta: dict[str, Any] | None
    timestamp_creacion: str
    timestamp_respuesta: str | None
    timestamp_aplicacion: str | None
    timestamp_cancelacion: str | None
    metadata: dict[str, Any]
    impacto: dict[str, Any]
    autorizaciones: tuple[str, ...]
    resume_run_id: str | None

    def __post_init__(self) -> None:
        _validar_uuid(self.decision_id, "decision_id")
        _validar_uuid(self.task_id, "task_id")
        _validar_uuid(self.run_id, "run_id")
        if self.resume_run_id is not None:
            _validar_uuid(self.resume_run_id, "resume_run_id")
        object.__setattr__(self, "tipo", TipoDecision(self.tipo))
        object.__setattr__(self, "estado", EstadoDecision(self.estado))
        if not isinstance(self.pregunta, str) or not self.pregunta.strip():
            raise ErrorPersistenciaDecision("pregunta debe ser texto no vacío")
        if not isinstance(self.contexto, str):
            raise ErrorPersistenciaDecision("contexto debe ser texto")
        object.__setattr__(
            self,
            "opciones_permitidas",
            _textos(self.opciones_permitidas, "opciones_permitidas"),
        )
        object.__setattr__(
            self,
            "autorizaciones",
            _textos(self.autorizaciones, "autorizaciones"),
        )
        if self.respuesta is not None and not isinstance(self.respuesta, dict):
            raise ErrorPersistenciaDecision("respuesta debe ser un objeto o null")
        if not isinstance(self.metadata, dict) or not isinstance(self.impacto, dict):
            raise ErrorPersistenciaDecision("metadata e impacto deben ser objetos")
        _validar_timestamp(self.timestamp_creacion, "timestamp_creacion")
        _validar_timestamp(
            self.timestamp_respuesta, "timestamp_respuesta", opcional=True
        )
        _validar_timestamp(
            self.timestamp_aplicacion, "timestamp_aplicacion", opcional=True
        )
        _validar_timestamp(
            self.timestamp_cancelacion, "timestamp_cancelacion", opcional=True
        )
        if self.estado in {EstadoDecision.RESPONDIDA, EstadoDecision.APLICADA}:
            if self.respuesta is None or self.timestamp_respuesta is None:
                raise ErrorPersistenciaDecision(
                    "una decisión respondida/aplicada necesita respuesta y timestamp"
                )
        if self.estado is EstadoDecision.APLICADA:
            if self.timestamp_aplicacion is None or self.resume_run_id is None:
                raise ErrorPersistenciaDecision(
                    "una decisión aplicada necesita timestamp y run de resume"
                )
        if self.estado is EstadoDecision.CANCELADA and self.timestamp_cancelacion is None:
            raise ErrorPersistenciaDecision(
                "una decisión cancelada necesita timestamp_cancelacion"
            )

    def a_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DECISION_SCHEMA_VERSION,
            "decision_id": self.decision_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "tipo": self.tipo.value,
            "pregunta": self.pregunta,
            "contexto": self.contexto,
            "opciones_permitidas": list(self.opciones_permitidas),
            "estado": self.estado.value,
            "respuesta": self.respuesta,
            "timestamp_creacion": self.timestamp_creacion,
            "timestamp_respuesta": self.timestamp_respuesta,
            "timestamp_aplicacion": self.timestamp_aplicacion,
            "timestamp_cancelacion": self.timestamp_cancelacion,
            "metadata": self.metadata,
            "impacto": self.impacto,
            "autorizaciones": list(self.autorizaciones),
            "resume_run_id": self.resume_run_id,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> DecisionPersistente:
        if not isinstance(datos, dict):
            raise ErrorPersistenciaDecision("la decisión debe ser un objeto JSON")
        copia = dict(datos)
        version = copia.pop("schema_version", None)
        if version != DECISION_SCHEMA_VERSION:
            raise ErrorPersistenciaDecision(
                f"schema de decisión no soportado: {version}"
            )
        try:
            return cls(**copia)
        except (TypeError, ValueError) as exc:
            raise ErrorPersistenciaDecision(f"decisión inválida: {exc}") from exc


class GestorDecisiones:
    """Persiste una decisión por JSON y mantiene su trazabilidad con tarea/run."""

    def __init__(
        self,
        gestor_tareas: GestorTareas,
        gestor_runs: GestorRuns,
        directorio: str | Path = Path("estado") / "decisiones",
    ) -> None:
        self.gestor_tareas = gestor_tareas
        self.gestor_runs = gestor_runs
        self.directorio = Path(directorio)

    def crear_decision(
        self,
        *,
        task_id: str,
        run_id: str,
        tipo: TipoDecision | str = TipoDecision.DECISION_FUNCIONAL,
        pregunta: str,
        contexto: str = "",
        opciones_permitidas: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
        impacto: dict[str, Any] | None = None,
        autorizaciones: Iterable[str] = (),
    ) -> DecisionPersistente:
        try:
            tarea = self.gestor_tareas.cargar(task_id)
            run = self.gestor_runs.obtener_run(run_id)
        except (TareaNoEncontrada, RunNoEncontrado) as exc:
            raise DecisionInvalida(str(exc)) from exc
        if run.task_id != tarea.id:
            raise DecisionInvalida("el run no pertenece a la tarea")
        if run.estado_interno not in {
            EstadoInternoRun.REQUIERE_OK_PIO,
            EstadoInternoRun.PAUSA_PIO,
        }:
            raise DecisionInvalida("el run origen no está pausado")
        if tarea.estado is not EstadoTarea.ESPERANDO_DECISION:
            raise DecisionInvalida(
                "la tarea debe estar ESPERANDO_DECISION para crear una decisión"
            )
        existente = self.obtener_decision_pendiente(task_id)
        if existente is not None:
            if existente.run_id == run_id:
                return existente
            raise ConflictoDecisionPendiente(
                f"la tarea ya tiene la decisión pendiente {existente.decision_id}"
            )
        timestamp = _ahora_utc()
        decision = DecisionPersistente(
            decision_id=str(uuid4()),
            task_id=task_id,
            run_id=run_id,
            tipo=TipoDecision(tipo),
            pregunta=pregunta,
            contexto=contexto,
            opciones_permitidas=_textos(
                opciones_permitidas, "opciones_permitidas"
            ),
            estado=EstadoDecision.PENDIENTE,
            respuesta=None,
            timestamp_creacion=timestamp,
            timestamp_respuesta=None,
            timestamp_aplicacion=None,
            timestamp_cancelacion=None,
            metadata=dict(metadata or {}),
            impacto=dict(impacto or {}),
            autorizaciones=_textos(autorizaciones, "autorizaciones"),
            resume_run_id=None,
        )
        self._guardar(decision, nueva=True)
        self.gestor_tareas.anadir_evento(
            task_id,
            "DECISION_REQUIRED",
            {
                "decision_id": decision.decision_id,
                "run_id": run_id,
                "tipo": decision.tipo.value,
            },
        )
        return decision

    def obtener_decision(self, decision_id: str) -> DecisionPersistente:
        _validar_uuid(decision_id, "decision_id")
        path = self.directorio / f"{decision_id}.json"
        if not path.is_file():
            raise DecisionNoEncontrada(f"decisión no encontrada: {decision_id}")
        try:
            decision = DecisionPersistente.desde_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, ErrorPersistenciaDecision) as exc:
            raise ErrorPersistenciaDecision(f"no se pudo cargar {path}: {exc}") from exc
        if decision.decision_id != decision_id:
            raise ErrorPersistenciaDecision(
                "decision_id interno no coincide con el nombre del archivo"
            )
        return decision

    def listar_decisiones(self, task_id: str) -> list[DecisionPersistente]:
        _validar_uuid(task_id, "task_id")
        if not self.directorio.exists():
            return []
        decisiones = [
            self.obtener_decision(path.stem)
            for path in sorted(self.directorio.glob("*.json"))
        ]
        return sorted(
            (decision for decision in decisiones if decision.task_id == task_id),
            key=lambda item: (item.timestamp_creacion, item.decision_id),
        )

    def obtener_decision_pendiente(
        self, task_id: str
    ) -> DecisionPersistente | None:
        pendientes = [
            decision
            for decision in self.listar_decisiones(task_id)
            if decision.estado is EstadoDecision.PENDIENTE
        ]
        if len(pendientes) > 1:
            raise ErrorPersistenciaDecision(
                f"la tarea {task_id} tiene múltiples decisiones pendientes"
            )
        return pendientes[0] if pendientes else None

    def responder_decision(
        self,
        decision_id: str,
        *,
        opcion: str | None = None,
        texto: str | None = None,
        metadata_respuesta: dict[str, Any] | None = None,
    ) -> DecisionPersistente:
        decision = self.obtener_decision(decision_id)
        if decision.estado is not EstadoDecision.PENDIENTE:
            raise EstadoDecisionInvalido(
                f"solo se responde una decisión PENDIENTE, no {decision.estado.value}"
            )
        try:
            respuesta = self._validar_respuesta(decision, opcion=opcion, texto=texto)
        except DecisionInvalida as exc:
            self.gestor_tareas.anadir_evento(
                decision.task_id,
                "DECISION_REJECTED",
                {"decision_id": decision.decision_id, "motivo": str(exc)},
            )
            raise
        if metadata_respuesta is not None:
            if not isinstance(metadata_respuesta, dict):
                raise DecisionInvalida("metadata_respuesta debe ser un objeto")
            respuesta["metadata"] = dict(metadata_respuesta)
        actualizada = replace(
            decision,
            estado=EstadoDecision.RESPONDIDA,
            respuesta=respuesta,
            timestamp_respuesta=_ahora_utc(),
        )
        self._guardar(actualizada)
        self.gestor_tareas.anadir_evento(
            decision.task_id,
            "DECISION_RECEIVED",
            {
                "decision_id": decision.decision_id,
                "run_id": decision.run_id,
                "respuesta": respuesta,
            },
        )
        return actualizada

    def aplicar_decision(
        self, decision_id: str, resume_run_id: str
    ) -> DecisionPersistente:
        decision = self.obtener_decision(decision_id)
        if decision.estado is EstadoDecision.APLICADA:
            if decision.resume_run_id != resume_run_id:
                raise EstadoDecisionInvalido(
                    "la decisión ya fue aplicada a otro run"
                )
            return decision
        if decision.estado is not EstadoDecision.RESPONDIDA:
            raise EstadoDecisionInvalido(
                f"solo se aplica una decisión RESPONDIDA, no {decision.estado.value}"
            )
        _validar_uuid(resume_run_id, "resume_run_id")
        try:
            run_resume = self.gestor_runs.obtener_run(resume_run_id)
        except RunNoEncontrado as exc:
            raise DecisionInvalida("el run de resume no existe") from exc
        if run_resume.task_id != decision.task_id:
            raise DecisionInvalida("el run de resume pertenece a otra tarea")
        if run_resume.resume_de != decision.run_id:
            raise DecisionInvalida("el run de resume no referencia al run origen")
        if run_resume.decision_id != decision.decision_id:
            raise DecisionInvalida("el run de resume no referencia a la decisión")
        if run_resume.resultado is None:
            raise DecisionInvalida("el run de resume todavía no tiene resultado")
        actualizada = replace(
            decision,
            estado=EstadoDecision.APLICADA,
            timestamp_aplicacion=_ahora_utc(),
            resume_run_id=resume_run_id,
        )
        self._guardar(actualizada)
        self.gestor_tareas.anadir_evento(
            decision.task_id,
            "DECISION_APPLIED",
            {
                "decision_id": decision.decision_id,
                "run_origen": decision.run_id,
                "run_resume": resume_run_id,
            },
        )
        return actualizada

    def cancelar_decision(self, decision_id: str) -> DecisionPersistente:
        decision = self.obtener_decision(decision_id)
        if decision.estado is EstadoDecision.CANCELADA:
            return decision
        if decision.estado is EstadoDecision.APLICADA:
            raise EstadoDecisionInvalido("una decisión aplicada no puede cancelarse")
        actualizada = replace(
            decision,
            estado=EstadoDecision.CANCELADA,
            timestamp_cancelacion=_ahora_utc(),
        )
        self._guardar(actualizada)
        self.gestor_tareas.anadir_evento(
            decision.task_id,
            "DECISION_CANCELLED",
            {"decision_id": decision.decision_id, "run_id": decision.run_id},
        )
        return actualizada

    @staticmethod
    def respuesta_para_motor(decision: DecisionPersistente) -> str:
        if decision.respuesta is None:
            raise EstadoDecisionInvalido("la decisión no tiene respuesta")
        return json.dumps(decision.respuesta, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _validar_respuesta(
        decision: DecisionPersistente,
        *,
        opcion: str | None,
        texto: str | None,
    ) -> dict[str, Any]:
        opcion_normalizada = opcion.strip() if isinstance(opcion, str) else None
        texto_normalizado = texto.strip() if isinstance(texto, str) else None
        if decision.opciones_permitidas:
            if opcion_normalizada not in decision.opciones_permitidas:
                raise DecisionInvalida(
                    "opción no permitida; debe coincidir exactamente con una opción cerrada"
                )
        elif not texto_normalizado:
            raise DecisionInvalida(
                "una decisión sin opciones cerradas requiere texto estructurado no vacío"
            )
        return {"opcion": opcion_normalizada, "texto": texto_normalizado}

    def _guardar(self, decision: DecisionPersistente, *, nueva: bool = False) -> None:
        self.directorio.mkdir(parents=True, exist_ok=True)
        destino = self.directorio / f"{decision.decision_id}.json"
        if nueva and destino.exists():
            raise ErrorPersistenciaDecision(
                f"decision_id duplicado: {decision.decision_id}"
            )
        descriptor, nombre = tempfile.mkstemp(
            prefix=f".{decision.decision_id}.", suffix=".tmp", dir=self.directorio
        )
        temporal = Path(nombre)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(
                    decision.a_dict(),
                    archivo,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, destino)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise
