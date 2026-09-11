"""Modelo y persistencia local de tareas del Orquestador V0.2.1."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable
from uuid import UUID, uuid4


SCHEMA_VERSION = 1


class ErrorTarea(RuntimeError):
    """Error base de la capa de tareas persistentes."""


class ErrorValidacionTarea(ErrorTarea, ValueError):
    """Los datos de una tarea o contrato no cumplen su contrato."""


class TareaNoEncontrada(ErrorTarea, FileNotFoundError):
    """No existe una tarea persistida con el ID solicitado."""


class TransicionEstadoInvalida(ErrorTarea, ValueError):
    """El cambio de estado solicitado no está permitido."""


class ErrorPersistenciaTarea(ErrorTarea):
    """El estado persistido no es válido o no puede guardarse con seguridad."""


class ModoTarea(str, Enum):
    READ_ONLY = "read_only"
    WORKSPACE_WRITE = "workspace_write"


class CapacidadCheckpoint(str, Enum):
    NONE = "NONE"
    FULL_RUN_ONLY = "FULL_RUN_ONLY"
    CHECKPOINT_RESUME = "CHECKPOINT_RESUME"


class EstadoTarea(str, Enum):
    PREPARANDO = "PREPARANDO"
    TRABAJANDO = "TRABAJANDO"
    ESPERANDO_DECISION = "ESPERANDO_DECISION"
    RECUPERANDO = "RECUPERANDO"
    BLOQUEADA = "BLOQUEADA"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"

    @property
    def es_terminal(self) -> bool:
        return self in {EstadoTarea.FINALIZADA, EstadoTarea.CANCELADA}


TRANSICIONES_PERMITIDAS: dict[EstadoTarea, frozenset[EstadoTarea]] = {
    EstadoTarea.PREPARANDO: frozenset(
        {EstadoTarea.TRABAJANDO, EstadoTarea.BLOQUEADA, EstadoTarea.CANCELADA}
    ),
    EstadoTarea.TRABAJANDO: frozenset(
        {
            EstadoTarea.ESPERANDO_DECISION,
            EstadoTarea.BLOQUEADA,
            EstadoTarea.RECUPERANDO,
            EstadoTarea.FINALIZADA,
            EstadoTarea.CANCELADA,
        }
    ),
    EstadoTarea.ESPERANDO_DECISION: frozenset(
        {EstadoTarea.TRABAJANDO, EstadoTarea.BLOQUEADA, EstadoTarea.CANCELADA}
    ),
    EstadoTarea.RECUPERANDO: frozenset(
        {
            EstadoTarea.TRABAJANDO,
            EstadoTarea.ESPERANDO_DECISION,
            EstadoTarea.BLOQUEADA,
            EstadoTarea.FINALIZADA,
            EstadoTarea.CANCELADA,
        }
    ),
    # Una tarea bloqueada requiere un paso explícito de recuperación o decisión.
    EstadoTarea.BLOQUEADA: frozenset(
        {
            EstadoTarea.BLOQUEADA,
            EstadoTarea.RECUPERANDO,
            EstadoTarea.ESPERANDO_DECISION,
            EstadoTarea.CANCELADA,
        }
    ),
    EstadoTarea.FINALIZADA: frozenset(),
    EstadoTarea.CANCELADA: frozenset(),
}


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texto_no_vacio(valor: Any, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorValidacionTarea(f"{campo} debe ser texto no vacío")
    return valor


def _lista_textos(valor: Any, campo: str) -> tuple[str, ...]:
    if not isinstance(valor, (list, tuple)):
        raise ErrorValidacionTarea(f"{campo} debe ser una lista de textos")
    if not all(isinstance(elemento, str) for elemento in valor):
        raise ErrorValidacionTarea(f"{campo} debe contener solo textos")
    return tuple(valor)


def _presupuesto_valido(valor: Any) -> int | float | None:
    if valor is not None and (
        isinstance(valor, bool)
        or not isinstance(valor, (int, float))
        or not math.isfinite(valor)
        or valor < 0
    ):
        raise ErrorValidacionTarea(
            "presupuesto_api debe ser un número no negativo o null"
        )
    return valor


@dataclass(frozen=True)
class ContratoTarea:
    objetivo: str
    acciones_permitidas: tuple[str, ...]
    rutas_permitidas: tuple[str, ...]
    acciones_prohibidas: tuple[str, ...]
    rutas_protegidas: tuple[str, ...]
    condiciones_finalizacion: str
    restricciones_adicionales: tuple[str, ...]
    commit_autorizado: bool
    push_autorizado: bool
    presupuesto_api: int | float | None

    def __post_init__(self) -> None:
        _texto_no_vacio(self.objetivo, "objetivo")
        _texto_no_vacio(
            self.condiciones_finalizacion, "condiciones_finalizacion"
        )
        for campo in (
            "acciones_permitidas",
            "rutas_permitidas",
            "acciones_prohibidas",
            "rutas_protegidas",
            "restricciones_adicionales",
        ):
            object.__setattr__(self, campo, _lista_textos(getattr(self, campo), campo))
        if not isinstance(self.commit_autorizado, bool):
            raise ErrorValidacionTarea("commit_autorizado debe ser booleano")
        if not isinstance(self.push_autorizado, bool):
            raise ErrorValidacionTarea("push_autorizado debe ser booleano")
        _presupuesto_valido(self.presupuesto_api)

    def a_dict(self) -> dict[str, Any]:
        return {
            "objetivo": self.objetivo,
            "acciones_permitidas": list(self.acciones_permitidas),
            "rutas_permitidas": list(self.rutas_permitidas),
            "acciones_prohibidas": list(self.acciones_prohibidas),
            "rutas_protegidas": list(self.rutas_protegidas),
            "condiciones_finalizacion": self.condiciones_finalizacion,
            "restricciones_adicionales": list(self.restricciones_adicionales),
            "commit_autorizado": self.commit_autorizado,
            "push_autorizado": self.push_autorizado,
            "presupuesto_api": self.presupuesto_api,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> ContratoTarea:
        if not isinstance(datos, dict):
            raise ErrorValidacionTarea("contrato debe ser un objeto JSON")
        try:
            return cls(**datos)
        except TypeError as exc:
            raise ErrorValidacionTarea(f"contrato inválido: {exc}") from exc


@dataclass(frozen=True)
class EventoTarea:
    tipo: str
    timestamp: str
    datos: dict[str, Any]

    def __post_init__(self) -> None:
        _texto_no_vacio(self.tipo, "tipo de evento")
        _validar_timestamp(self.timestamp, "timestamp de evento")
        if not isinstance(self.datos, dict):
            raise ErrorValidacionTarea("datos del evento debe ser un objeto")

    def a_dict(self) -> dict[str, Any]:
        return {"tipo": self.tipo, "timestamp": self.timestamp, "datos": self.datos}

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> EventoTarea:
        if not isinstance(datos, dict):
            raise ErrorValidacionTarea("evento debe ser un objeto JSON")
        try:
            return cls(**datos)
        except TypeError as exc:
            raise ErrorValidacionTarea(f"evento inválido: {exc}") from exc


def _validar_timestamp(valor: Any, campo: str) -> None:
    if not isinstance(valor, str):
        raise ErrorValidacionTarea(f"{campo} debe ser texto ISO-8601")
    try:
        fecha = datetime.fromisoformat(valor)
    except ValueError as exc:
        raise ErrorValidacionTarea(f"{campo} no es ISO-8601 válido") from exc
    if fecha.tzinfo is None:
        raise ErrorValidacionTarea(f"{campo} debe incluir zona horaria")


@dataclass(frozen=True)
class Tarea:
    id: str
    orden_original: str
    objetivo: str
    repo: str
    worktree: str
    rama: str
    commit_inicial: str
    modo: ModoTarea
    rutas_permitidas: tuple[str, ...]
    rutas_protegidas: tuple[str, ...]
    estado: EstadoTarea
    condicion_finalizacion: str
    presupuesto_api: int | float | None
    commit_autorizado: bool
    push_autorizado: bool
    fecha_creacion: str
    fecha_actualizacion: str
    historial: tuple[EventoTarea, ...]
    contrato: ContratoTarea
    capacidad_checkpoint: CapacidadCheckpoint = CapacidadCheckpoint.NONE

    def __post_init__(self) -> None:
        try:
            UUID(self.id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ErrorValidacionTarea("id debe ser un UUID válido") from exc
        for campo in (
            "orden_original",
            "objetivo",
            "repo",
            "worktree",
            "rama",
            "commit_inicial",
            "condicion_finalizacion",
        ):
            _texto_no_vacio(getattr(self, campo), campo)
        try:
            object.__setattr__(self, "modo", ModoTarea(self.modo))
        except ValueError as exc:
            raise ErrorValidacionTarea(f"modo inexistente: {self.modo}") from exc
        try:
            object.__setattr__(self, "estado", EstadoTarea(self.estado))
        except ValueError as exc:
            raise ErrorValidacionTarea(f"estado inexistente: {self.estado}") from exc
        try:
            object.__setattr__(
                self,
                "capacidad_checkpoint",
                CapacidadCheckpoint(self.capacidad_checkpoint),
            )
        except ValueError as exc:
            raise ErrorValidacionTarea(
                f"capacidad_checkpoint inexistente: {self.capacidad_checkpoint}"
            ) from exc
        object.__setattr__(
            self,
            "rutas_permitidas",
            _lista_textos(self.rutas_permitidas, "rutas_permitidas"),
        )
        object.__setattr__(
            self,
            "rutas_protegidas",
            _lista_textos(self.rutas_protegidas, "rutas_protegidas"),
        )
        object.__setattr__(self, "historial", tuple(self.historial))
        _validar_timestamp(self.fecha_creacion, "fecha_creacion")
        _validar_timestamp(self.fecha_actualizacion, "fecha_actualizacion")
        _presupuesto_valido(self.presupuesto_api)
        if not isinstance(self.commit_autorizado, bool) or not isinstance(
            self.push_autorizado, bool
        ):
            raise ErrorValidacionTarea("las autorizaciones deben ser booleanas")
        self._validar_coherencia_contrato()

    def _validar_coherencia_contrato(self) -> None:
        pares = {
            "objetivo": (self.objetivo, self.contrato.objetivo),
            "rutas_permitidas": (
                self.rutas_permitidas,
                self.contrato.rutas_permitidas,
            ),
            "rutas_protegidas": (
                self.rutas_protegidas,
                self.contrato.rutas_protegidas,
            ),
            "condicion_finalizacion": (
                self.condicion_finalizacion,
                self.contrato.condiciones_finalizacion,
            ),
            "presupuesto_api": (self.presupuesto_api, self.contrato.presupuesto_api),
            "commit_autorizado": (
                self.commit_autorizado,
                self.contrato.commit_autorizado,
            ),
            "push_autorizado": (
                self.push_autorizado,
                self.contrato.push_autorizado,
            ),
        }
        incoherentes = [campo for campo, valores in pares.items() if valores[0] != valores[1]]
        if incoherentes:
            raise ErrorValidacionTarea(
                "campos incoherentes con el contrato: " + ", ".join(incoherentes)
            )

    @property
    def es_terminal(self) -> bool:
        return self.estado.es_terminal

    def a_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "orden_original": self.orden_original,
            "objetivo": self.objetivo,
            "repo": self.repo,
            "worktree": self.worktree,
            "rama": self.rama,
            "commit_inicial": self.commit_inicial,
            "modo": self.modo.value,
            "rutas_permitidas": list(self.rutas_permitidas),
            "rutas_protegidas": list(self.rutas_protegidas),
            "estado": self.estado.value,
            "condicion_finalizacion": self.condicion_finalizacion,
            "presupuesto_api": self.presupuesto_api,
            "commit_autorizado": self.commit_autorizado,
            "push_autorizado": self.push_autorizado,
            "fecha_creacion": self.fecha_creacion,
            "fecha_actualizacion": self.fecha_actualizacion,
            "historial": [evento.a_dict() for evento in self.historial],
            "contrato": self.contrato.a_dict(),
            "capacidad_checkpoint": self.capacidad_checkpoint.value,
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> Tarea:
        if not isinstance(datos, dict):
            raise ErrorValidacionTarea("la tarea debe ser un objeto JSON")
        copia = dict(datos)
        version = copia.pop("schema_version", None)
        if version != SCHEMA_VERSION:
            raise ErrorValidacionTarea(f"schema_version no soportada: {version}")
        try:
            copia.setdefault("capacidad_checkpoint", CapacidadCheckpoint.NONE.value)
            copia["contrato"] = ContratoTarea.desde_dict(copia["contrato"])
            copia["historial"] = tuple(
                EventoTarea.desde_dict(evento) for evento in copia["historial"]
            )
            return cls(**copia)
        except KeyError as exc:
            raise ErrorValidacionTarea(f"falta el campo obligatorio {exc.args[0]}") from exc
        except TypeError as exc:
            raise ErrorValidacionTarea(f"tarea inválida: {exc}") from exc


class GestorTareas:
    """Crea y mantiene tareas, una por archivo JSON independiente."""

    def __init__(self, directorio: str | Path = Path("estado") / "tareas") -> None:
        self.directorio = Path(directorio)

    def crear_tarea(
        self,
        *,
        orden_original: str,
        repo: str,
        worktree: str,
        rama: str,
        commit_inicial: str,
        modo: ModoTarea | str,
        contrato: ContratoTarea,
        capacidad_checkpoint: CapacidadCheckpoint | str = CapacidadCheckpoint.NONE,
    ) -> Tarea:
        if not isinstance(contrato, ContratoTarea):
            raise ErrorValidacionTarea("contrato debe ser una instancia de ContratoTarea")
        timestamp = _ahora_utc()
        eventos = (
            EventoTarea("TASK_CREATED", timestamp, {"estado": EstadoTarea.PREPARANDO.value}),
            EventoTarea("CONTRACT_CREATED", timestamp, {}),
        )
        tarea = Tarea(
            id=str(uuid4()),
            orden_original=orden_original,
            objetivo=contrato.objetivo,
            repo=repo,
            worktree=worktree,
            rama=rama,
            commit_inicial=commit_inicial,
            modo=modo,
            rutas_permitidas=contrato.rutas_permitidas,
            rutas_protegidas=contrato.rutas_protegidas,
            estado=EstadoTarea.PREPARANDO,
            condicion_finalizacion=contrato.condiciones_finalizacion,
            presupuesto_api=contrato.presupuesto_api,
            commit_autorizado=contrato.commit_autorizado,
            push_autorizado=contrato.push_autorizado,
            fecha_creacion=timestamp,
            fecha_actualizacion=timestamp,
            historial=eventos,
            contrato=contrato,
            capacidad_checkpoint=capacidad_checkpoint,
        )
        self.guardar(tarea)
        return tarea

    def cargar(self, task_id: str) -> Tarea:
        path = self._path_tarea(task_id)
        if not path.is_file():
            raise TareaNoEncontrada(f"tarea no encontrada: {task_id}")
        try:
            with path.open("r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
            tarea = Tarea.desde_dict(datos)
        except (OSError, json.JSONDecodeError, ErrorValidacionTarea) as exc:
            raise ErrorPersistenciaTarea(f"no se pudo cargar {path}: {exc}") from exc
        if tarea.id != task_id:
            raise ErrorPersistenciaTarea(
                f"el ID interno {tarea.id} no coincide con el archivo {path.name}"
            )
        return tarea

    def listar(self) -> list[Tarea]:
        if not self.directorio.exists():
            return []
        return [self.cargar(path.stem) for path in sorted(self.directorio.glob("*.json"))]

    def actualizar_estado(
        self, tarea_o_id: Tarea | str, nuevo_estado: EstadoTarea | str
    ) -> Tarea:
        tarea = self._resolver(tarea_o_id)
        try:
            destino = EstadoTarea(nuevo_estado)
        except ValueError as exc:
            raise ErrorValidacionTarea(f"estado inexistente: {nuevo_estado}") from exc
        if destino not in TRANSICIONES_PERMITIDAS[tarea.estado]:
            raise TransicionEstadoInvalida(
                f"transición no permitida: {tarea.estado.value} -> {destino.value}"
            )
        timestamp = _ahora_utc()
        evento = EventoTarea(
            "STATUS_CHANGED",
            timestamp,
            {"estado_anterior": tarea.estado.value, "estado_nuevo": destino.value},
        )
        actualizada = replace(
            tarea,
            estado=destino,
            fecha_actualizacion=timestamp,
            historial=(*tarea.historial, evento),
        )
        self.guardar(actualizada)
        return actualizada

    def anadir_evento(
        self, tarea_o_id: Tarea | str, tipo: str, datos: dict[str, Any] | None = None
    ) -> Tarea:
        tarea = self._resolver(tarea_o_id)
        timestamp = _ahora_utc()
        evento = EventoTarea(tipo, timestamp, datos or {})
        actualizada = replace(
            tarea,
            fecha_actualizacion=timestamp,
            historial=(*tarea.historial, evento),
        )
        self.guardar(actualizada)
        return actualizada

    def guardar(self, tarea: Tarea) -> None:
        if not isinstance(tarea, Tarea):
            raise ErrorValidacionTarea("solo se pueden guardar instancias de Tarea")
        path = self._path_tarea(tarea.id)
        if path.exists():
            anterior = self.cargar(tarea.id)
            if len(tarea.historial) < len(anterior.historial):
                raise ErrorPersistenciaTarea("no se puede truncar el historial persistido")
            if tarea.historial[: len(anterior.historial)] != anterior.historial:
                raise ErrorPersistenciaTarea("el historial persistido es append-only")
            self._validar_actualizacion(anterior, tarea)
        elif tarea.estado is not EstadoTarea.PREPARANDO:
            raise ErrorPersistenciaTarea(
                "una tarea nueva debe guardarse en estado PREPARANDO"
            )
        self.directorio.mkdir(parents=True, exist_ok=True)
        descriptor, temporal = tempfile.mkstemp(
            prefix=f".{tarea.id}.", suffix=".tmp", dir=self.directorio
        )
        temporal_path = Path(temporal)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(
                    tarea.a_dict(),
                    archivo,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal_path, path)
        except BaseException:
            temporal_path.unlink(missing_ok=True)
            raise

    def es_terminal(self, tarea_o_id: Tarea | str) -> bool:
        return self._resolver(tarea_o_id).es_terminal

    def _resolver(self, tarea_o_id: Tarea | str) -> Tarea:
        return tarea_o_id if isinstance(tarea_o_id, Tarea) else self.cargar(tarea_o_id)

    def _validar_actualizacion(self, anterior: Tarea, nueva: Tarea) -> None:
        if anterior.estado is nueva.estado:
            return
        if nueva.estado not in TRANSICIONES_PERMITIDAS[anterior.estado]:
            raise TransicionEstadoInvalida(
                f"transición no permitida: {anterior.estado.value} -> {nueva.estado.value}"
            )
        eventos_nuevos = nueva.historial[len(anterior.historial) :]
        if not eventos_nuevos:
            raise ErrorPersistenciaTarea(
                "un cambio de estado requiere un evento STATUS_CHANGED"
            )
        evento = eventos_nuevos[-1]
        esperado = {
            "estado_anterior": anterior.estado.value,
            "estado_nuevo": nueva.estado.value,
        }
        if evento.tipo != "STATUS_CHANGED" or evento.datos != esperado:
            raise ErrorPersistenciaTarea(
                "el último evento no documenta correctamente el cambio de estado"
            )

    def _path_tarea(self, task_id: str) -> Path:
        try:
            UUID(task_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ErrorValidacionTarea("task_id debe ser un UUID válido") from exc
        return self.directorio / f"{task_id}.json"


def crear_contrato(
    *,
    objetivo: str,
    acciones_permitidas: Iterable[str] = (),
    rutas_permitidas: Iterable[str] = (),
    acciones_prohibidas: Iterable[str] = (),
    rutas_protegidas: Iterable[str] = (),
    condiciones_finalizacion: str,
    restricciones_adicionales: Iterable[str] = (),
    commit_autorizado: bool = False,
    push_autorizado: bool = False,
    presupuesto_api: int | float | None = None,
) -> ContratoTarea:
    """Constructor cómodo que normaliza iterables a estructuras inmutables."""

    return ContratoTarea(
        objetivo=objetivo,
        acciones_permitidas=tuple(acciones_permitidas),
        rutas_permitidas=tuple(rutas_permitidas),
        acciones_prohibidas=tuple(acciones_prohibidas),
        rutas_protegidas=tuple(rutas_protegidas),
        condiciones_finalizacion=condiciones_finalizacion,
        restricciones_adicionales=tuple(restricciones_adicionales),
        commit_autorizado=commit_autorizado,
        push_autorizado=push_autorizado,
        presupuesto_api=presupuesto_api,
    )
