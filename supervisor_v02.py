"""Supervisor determinista de reglas, autorizaciones y decisiones V0.2.9."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any

from reglas_persistentes import AccionRegla, GestorReglas, ReglaPersistente, TipoRegla
from tareas_persistentes import EstadoTarea, GestorTareas, ModoTarea, Tarea


class DecisionSupervisor(str, Enum):
    AUTO_APPLY = "AUTO_APPLY"
    REQUIRE_PIO = "REQUIRE_PIO"
    BLOCK = "BLOCK"
    ALREADY_RESOLVED = "ALREADY_RESOLVED"


class ClasificacionDecision(str, Enum):
    TECNICA = "TECNICA"
    FUNCIONAL = "FUNCIONAL"
    AMBIGUA = "AMBIGUA"


@dataclass(frozen=True)
class SolicitudAccion:
    task_id: str
    tipo_accion: str
    ambito: str
    datos: dict[str, Any] = field(default_factory=dict)
    autorizacion_requerida: str | None = None
    contexto: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    clasificacion: ClasificacionDecision | str | None = None

    def __post_init__(self) -> None:
        if not self.task_id or not self.tipo_accion or not self.ambito:
            raise ValueError("task_id, tipo_accion y ambito son obligatorios")
        if not isinstance(self.datos, dict) or not isinstance(self.metadata, dict):
            raise ValueError("datos y metadata deben ser objetos")
        if self.clasificacion is not None:
            object.__setattr__(self, "clasificacion", ClasificacionDecision(self.clasificacion))

    def a_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "tipo_accion": self.tipo_accion,
            "ambito": self.ambito,
            "datos": self.datos,
            "autorizacion_requerida": self.autorizacion_requerida,
            "contexto": self.contexto,
            "metadata": self.metadata,
            "clasificacion": self.clasificacion.value if self.clasificacion else None,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any], *, task_id: str | None = None) -> "SolicitudAccion":
        copia = dict(datos)
        if task_id is not None:
            copia.setdefault("task_id", task_id)
        return cls(**copia)


@dataclass(frozen=True)
class EvaluacionSupervisor:
    decision: DecisionSupervisor
    codigo: str
    motivo: str
    impacto: dict[str, Any]
    evaluation_id: str
    regla_aplicada: str | None = None
    autorizacion_aplicada: str | None = None
    decision_id: str | None = None
    warnings: tuple[str, ...] = ()
    reglas_conflicto: tuple[str, ...] = ()
    accion_resultante: dict[str, Any] = field(default_factory=dict)

    def a_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "codigo": self.codigo,
            "motivo": self.motivo,
            "impacto": self.impacto,
            "evaluation_id": self.evaluation_id,
            "regla_aplicada": self.regla_aplicada,
            "autorizacion_aplicada": self.autorizacion_aplicada,
            "decision_id": self.decision_id,
            "warnings": list(self.warnings),
            "reglas_conflicto": list(self.reglas_conflicto),
            "accion_resultante": self.accion_resultante,
        }


ACCIONES_TECNICAS_SEGURAS = frozenset({
    "ELEGIR_FUNCION", "MODIFICAR_CLASE_EN_ALCANCE", "EJECUTAR_TEST",
    "PERSISTIR_RUN", "REINTENTAR", "VALIDAR_GIT", "ADQUIRIR_LOCK",
    "LIBERAR_LOCK", "CHECKPOINT", "WORKSPACE_WRITE",
})


class SupervisorV02:
    """Aplica la jerarquía de autoridad sin IA ni lenguaje natural libre."""

    def __init__(self, gestor_reglas: GestorReglas, gestor_tareas: GestorTareas) -> None:
        self.gestor_reglas = gestor_reglas
        self.gestor_tareas = gestor_tareas
        self.gestor_reglas.asegurar_reglas_confirmadas()

    def evaluar(self, solicitud: SolicitudAccion) -> EvaluacionSupervisor:
        if not isinstance(solicitud, SolicitudAccion):
            raise ValueError("se requiere SolicitudAccion estructurada")
        tarea = self.gestor_tareas.cargar(solicitud.task_id)
        evaluation_id = self._evaluation_id(solicitud)
        previa = self._evaluacion_previa(tarea, evaluation_id)
        if previa is not None:
            return previa

        contexto = self._contexto(solicitud)
        absolutas = self._aplicables(contexto, TipoRegla.ABSOLUTA)
        if absolutas:
            evaluacion = self._desde_regla(absolutas[0], evaluation_id, absoluta=True)
            return self._registrar(tarea, solicitud, evaluacion)

        barrera = self._restriccion_tarea(tarea, solicitud, evaluation_id)
        if barrera is not None:
            return self._registrar(tarea, solicitud, barrera)

        funcionales = self._aplicables(contexto, TipoRegla.FUNCIONAL)
        if funcionales:
            prioridad = funcionales[0].prioridad
            candidatas = [item for item in funcionales if item.prioridad == prioridad]
            acciones = {json.dumps(item.accion, sort_keys=True, ensure_ascii=False) for item in candidatas}
            if len(acciones) > 1:
                evaluacion = EvaluacionSupervisor(
                    DecisionSupervisor.REQUIRE_PIO, "RULE_CONFLICT",
                    "reglas funcionales aplicables de igual prioridad se contradicen",
                    {"requiere_resolucion_conflicto": True}, evaluation_id,
                    reglas_conflicto=tuple(item.rule_id for item in candidatas),
                )
                return self._registrar(tarea, solicitud, evaluacion)
            evaluacion = self._desde_regla(candidatas[0], evaluation_id)
            return self._registrar(tarea, solicitud, evaluacion)

        autorizacion = self._autorizacion(tarea, solicitud, evaluation_id)
        if autorizacion is not None:
            return self._registrar(tarea, solicitud, autorizacion)

        if solicitud.metadata.get("decision_pio_aprobada") is True:
            evaluacion = EvaluacionSupervisor(
                DecisionSupervisor.ALREADY_RESOLVED, "ACTION_AUTO_APPROVED",
                "la decisión puntual de Pio ya consta en la tarea",
                {"continua": True}, evaluation_id,
                autorizacion_aplicada="DECISION_PIO_DURANTE_TAREA",
                accion_resultante={"decision": "AUTO_APPLY"},
            )
            return self._registrar(tarea, solicitud, evaluacion)

        clasificacion = self._clasificar(solicitud)
        if clasificacion is ClasificacionDecision.TECNICA and self._tecnica_segura(tarea, solicitud):
            evaluacion = EvaluacionSupervisor(
                DecisionSupervisor.AUTO_APPLY, "ACTION_AUTO_APPROVED",
                "decisión técnica segura dentro del alcance contratado",
                {"continua": True, "clasificacion": clasificacion.value}, evaluation_id,
                accion_resultante={"decision": "AUTO_APPLY"},
            )
        else:
            motivo = (
                "solicitud ambigua; Pio debe fijar el criterio funcional"
                if clasificacion is ClasificacionDecision.AMBIGUA
                else "no existe una regla funcional aplicable"
            )
            evaluacion = EvaluacionSupervisor(
                DecisionSupervisor.REQUIRE_PIO, "NO_RULE_APPLICABLE",
                motivo, {"clasificacion": clasificacion.value}, evaluation_id,
            )
        return self._registrar(tarea, solicitud, evaluacion)

    def _aplicables(self, contexto: dict[str, Any], tipo: TipoRegla) -> list[ReglaPersistente]:
        ambito = str(contexto["ambito"]).upper()
        return [
            regla for regla in self.gestor_reglas.listar_reglas(activas=True, tipo=tipo)
            if regla.ambito in {ambito, "*"} and _cumple(regla.condicion, contexto)
        ]

    @staticmethod
    def _contexto(solicitud: SolicitudAccion) -> dict[str, Any]:
        return {
            "task_id": solicitud.task_id,
            "tipo_accion": solicitud.tipo_accion.upper(),
            "ambito": solicitud.ambito.upper(),
            "datos": solicitud.datos,
            "autorizacion_requerida": solicitud.autorizacion_requerida,
            "contexto": solicitud.contexto,
            "metadata": solicitud.metadata,
        }

    @staticmethod
    def _desde_regla(regla: ReglaPersistente, evaluation_id: str, *, absoluta: bool = False) -> EvaluacionSupervisor:
        decision = DecisionSupervisor(regla.accion.get("decision", AccionRegla.AUTO_APPLY.value))
        codigo = regla.accion.get("codigo") or (
            "ABSOLUTE_RULE_VIOLATION" if absoluta else "ACTION_AUTO_APPROVED"
        )
        return EvaluacionSupervisor(
            decision, codigo, str(regla.accion.get("motivo") or f"regla aplicada: {regla.nombre}"),
            {"jerarquia": 1 if absoluta else 3}, evaluation_id,
            regla_aplicada=regla.rule_id, accion_resultante=regla.accion,
        )

    @staticmethod
    def _restriccion_tarea(tarea: Tarea, solicitud: SolicitudAccion, evaluation_id: str) -> EvaluacionSupervisor | None:
        accion = solicitud.tipo_accion.upper()
        prohibidas = {item.upper() for item in tarea.contrato.acciones_prohibidas}
        ruta = str(solicitud.datos.get("ruta", ""))
        protegida = any(ruta == item or ruta.startswith(item.rstrip("/\\") + "/") or ruta.startswith(item.rstrip("/\\") + "\\") for item in tarea.rutas_protegidas)
        if accion in prohibidas or protegida or solicitud.metadata.get("viola_restriccion_tarea") is True:
            return EvaluacionSupervisor(
                DecisionSupervisor.BLOCK, "ACTION_BLOCKED",
                "la acción contradice una restricción explícita de la tarea",
                {"jerarquia": 2, "ruta_protegida": protegida}, evaluation_id,
            )
        return None

    @staticmethod
    def _autorizacion(tarea: Tarea, solicitud: SolicitudAccion, evaluation_id: str) -> EvaluacionSupervisor | None:
        requerida = (solicitud.autorizacion_requerida or solicitud.tipo_accion).upper()
        concedida = False
        conocida = requerida in {"COMMIT", "PUSH", "WORKSPACE_WRITE", "PRESUPUESTO_API"}
        if requerida == "COMMIT":
            concedida = tarea.commit_autorizado and solicitud.datos.get("tests_correctos", True) is True
        elif requerida == "PUSH":
            concedida = tarea.push_autorizado
        elif requerida == "WORKSPACE_WRITE":
            concedida = tarea.modo is ModoTarea.WORKSPACE_WRITE
        elif requerida == "PRESUPUESTO_API":
            coste = solicitud.datos.get("coste_estimado")
            concedida = coste is not None and tarea.presupuesto_api is not None and coste <= tarea.presupuesto_api
        elif requerida in {item.upper() for item in tarea.contrato.acciones_permitidas}:
            conocida = True
            concedida = True
        if conocida:
            if concedida:
                return EvaluacionSupervisor(
                    DecisionSupervisor.AUTO_APPLY, "AUTHORIZATION_ALREADY_GRANTED",
                    "la autorización ya está concedida por el contrato",
                    {"jerarquia": 4}, evaluation_id, autorizacion_aplicada=requerida,
                    accion_resultante={"decision": "AUTO_APPLY"},
                )
            return EvaluacionSupervisor(
                DecisionSupervisor.BLOCK, "ACTION_BLOCKED",
                "el contrato no autoriza la acción; no se pregunta para eludirlo",
                {"jerarquia": 2}, evaluation_id, autorizacion_aplicada=requerida,
            )
        return None

    @staticmethod
    def _clasificar(solicitud: SolicitudAccion) -> ClasificacionDecision:
        if solicitud.clasificacion is not None:
            return solicitud.clasificacion
        if solicitud.metadata.get("ambigua") is True:
            return ClasificacionDecision.AMBIGUA
        if solicitud.tipo_accion.upper() in ACCIONES_TECNICAS_SEGURAS:
            return ClasificacionDecision.TECNICA
        return ClasificacionDecision.FUNCIONAL

    @staticmethod
    def _tecnica_segura(tarea: Tarea, solicitud: SolicitudAccion) -> bool:
        if solicitud.metadata.get("segura") is False:
            return False
        ruta = solicitud.datos.get("ruta")
        if ruta and tarea.rutas_permitidas:
            return any(str(ruta) == base or str(ruta).startswith(base.rstrip("/\\") + "/") or str(ruta).startswith(base.rstrip("/\\") + "\\") for base in tarea.rutas_permitidas)
        return True

    def _registrar(self, tarea: Tarea, solicitud: SolicitudAccion, evaluacion: EvaluacionSupervisor) -> EvaluacionSupervisor:
        datos = {"evaluation_id": evaluacion.evaluation_id, "solicitud": solicitud.a_dict(), "evaluacion": evaluacion.a_dict()}
        self.gestor_tareas.anadir_evento(tarea.id, "SUPERVISOR_EVALUATED", datos)
        if evaluacion.regla_aplicada:
            self.gestor_tareas.anadir_evento(tarea.id, "RULE_APPLIED", {"evaluation_id": evaluacion.evaluation_id, "rule_id": evaluacion.regla_aplicada})
        if evaluacion.autorizacion_aplicada:
            self.gestor_tareas.anadir_evento(tarea.id, "AUTHORIZATION_APPLIED", {"evaluation_id": evaluacion.evaluation_id, "autorizacion": evaluacion.autorizacion_aplicada})
        evento = {
            DecisionSupervisor.AUTO_APPLY: "ACTION_AUTO_APPROVED",
            DecisionSupervisor.ALREADY_RESOLVED: "ACTION_AUTO_APPROVED",
            DecisionSupervisor.BLOCK: "ACTION_BLOCKED",
            DecisionSupervisor.REQUIRE_PIO: "PIO_DECISION_REQUIRED",
        }[evaluacion.decision]
        self.gestor_tareas.anadir_evento(tarea.id, evento, {"evaluation_id": evaluacion.evaluation_id, "codigo": evaluacion.codigo})
        if evaluacion.codigo == "NO_RULE_APPLICABLE":
            self.gestor_tareas.anadir_evento(tarea.id, "RULE_NOT_FOUND", {"evaluation_id": evaluacion.evaluation_id})
        return evaluacion

    @staticmethod
    def _evaluation_id(solicitud: SolicitudAccion) -> str:
        serializado = json.dumps(solicitud.a_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serializado.encode("utf-8")).hexdigest()

    @staticmethod
    def _evaluacion_previa(tarea: Tarea, evaluation_id: str) -> EvaluacionSupervisor | None:
        evento = next((item for item in reversed(tarea.historial) if item.tipo == "SUPERVISOR_EVALUATED" and item.datos.get("evaluation_id") == evaluation_id), None)
        if evento is None:
            return None
        datos = evento.datos["evaluacion"]
        return EvaluacionSupervisor(
            decision=DecisionSupervisor(datos["decision"]), codigo=datos["codigo"],
            motivo=datos["motivo"], impacto=datos["impacto"], evaluation_id=evaluation_id,
            regla_aplicada=datos.get("regla_aplicada"), autorizacion_aplicada=datos.get("autorizacion_aplicada"),
            decision_id=datos.get("decision_id"), warnings=tuple((*datos.get("warnings", ()), "evaluación idempotente reutilizada")),
            reglas_conflicto=tuple(datos.get("reglas_conflicto", ())), accion_resultante=dict(datos.get("accion_resultante", {})),
        )


def _obtener(contexto: dict[str, Any], campo: str) -> tuple[bool, Any]:
    actual: Any = contexto
    for parte in campo.split("."):
        if not isinstance(actual, dict) or parte not in actual:
            return False, None
        actual = actual[parte]
    return True, actual


def _cumple(condicion: dict[str, Any], contexto: dict[str, Any]) -> bool:
    if "all" in condicion:
        return all(_cumple(item, contexto) for item in condicion["all"])
    if "any" in condicion:
        return any(_cumple(item, contexto) for item in condicion["any"])
    if "not" in condicion:
        return not _cumple(condicion["not"], contexto)
    campo = condicion.get("campo")
    operador = str(condicion.get("operador", "EQ")).upper()
    existe, actual = _obtener(contexto, campo) if isinstance(campo, str) else (False, None)
    esperado = condicion.get("valor")
    if operador == "EXISTS":
        return existe is bool(esperado)
    if not existe:
        return False
    if operador == "EQ": return actual == esperado
    if operador == "NE": return actual != esperado
    if operador == "IN": return actual in esperado
    if operador == "NOT_IN": return actual not in esperado
    if operador == "LT": return actual < esperado
    if operador == "LE": return actual <= esperado
    if operador == "GT": return actual > esperado
    if operador == "GE": return actual >= esperado
    raise ValueError(f"operador de regla no soportado: {operador}")
