"""Validación de entornos y locks persistentes de worktree para V0.2.2."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import ntpath
import os
from pathlib import Path
import platform
import subprocess
import tempfile
from typing import Any
from uuid import UUID, uuid4

from tareas_persistentes import (
    ErrorTarea,
    GestorTareas,
    ModoTarea,
    Tarea,
    TareaNoEncontrada,
)


LOCK_SCHEMA_VERSION = 1


class ErrorEntorno(ErrorTarea):
    """Error base de validación o reserva de un entorno."""


class ErrorValidacionEntorno(ErrorEntorno):
    """El entorno real no coincide con lo contratado por la tarea."""

    def __init__(self, resultado: ResultadoValidacionEntorno) -> None:
        self.resultado = resultado
        super().__init__("; ".join(resultado.discrepancias))


class ConflictoWorktree(ErrorEntorno):
    """Otro propietario conserva la reserva exclusiva del worktree."""

    def __init__(self, reserva: ReservaWorktree) -> None:
        self.reserva = reserva
        super().__init__(
            f"worktree reservado por {reserva.task_id}: {reserva.worktree_normalizado}"
        )


class ReservaNoEncontrada(ErrorEntorno, FileNotFoundError):
    """No existe una reserva para el worktree indicado."""


class PropietarioReservaIncorrecto(ErrorEntorno, PermissionError):
    """Una tarea intentó liberar la reserva de otra."""


class LiberacionNoPermitida(ErrorEntorno):
    """Una tarea activa no puede perder silenciosamente su reserva."""


class ErrorPersistenciaLock(ErrorEntorno):
    """Un lock persistido es inválido o no se puede actualizar con seguridad."""


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalizar_worktree(worktree: str | Path) -> str:
    """Devuelve una identidad estable frente a case, slash y segmentos redundantes."""

    if not isinstance(worktree, (str, Path)) or not str(worktree).strip():
        raise ValueError("worktree debe ser un path no vacío")
    absoluto = str(Path(worktree).expanduser().resolve(strict=False))
    return ntpath.normcase(ntpath.normpath(absoluto.replace("/", "\\")))


@dataclass(frozen=True)
class EntornoTarea:
    repo: str
    worktree: str
    rama: str
    commit_inicial: str
    modo: ModoTarea

    def __post_init__(self) -> None:
        for campo in ("repo", "worktree", "rama", "commit_inicial"):
            if not isinstance(getattr(self, campo), str) or not getattr(
                self, campo
            ).strip():
                raise ValueError(f"{campo} debe ser texto no vacío")
        object.__setattr__(self, "modo", ModoTarea(self.modo))

    @classmethod
    def desde_tarea(cls, tarea: Tarea) -> EntornoTarea:
        return cls(
            repo=tarea.repo,
            worktree=tarea.worktree,
            rama=tarea.rama,
            commit_inicial=tarea.commit_inicial,
            modo=tarea.modo,
        )


@dataclass(frozen=True)
class ResultadoValidacionEntorno:
    entorno: EntornoTarea
    worktree_normalizado: str
    path_existe: bool
    repositorio_git_valido: bool
    repo_coincide: bool
    rama_actual: str | None
    head_actual: str | None
    estado_git: tuple[str, ...]
    repo_git_dir: str | None
    worktree_git_dir: str | None
    discrepancias: tuple[str, ...]

    @property
    def es_valido(self) -> bool:
        return not self.discrepancias

    def datos_evento(self) -> dict[str, Any]:
        return {
            "worktree": self.worktree_normalizado,
            "path_existe": self.path_existe,
            "repositorio_git_valido": self.repositorio_git_valido,
            "repo_coincide": self.repo_coincide,
            "rama_esperada": self.entorno.rama,
            "rama_actual": self.rama_actual,
            "head_esperado": self.entorno.commit_inicial,
            "head_actual": self.head_actual,
            "estado_git": list(self.estado_git),
            "discrepancias": list(self.discrepancias),
        }


def _git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def _git_dir_comun(path: Path) -> str | None:
    resultado = _git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if resultado.returncode != 0 or not resultado.stdout.strip():
        return None
    salida = resultado.stdout.strip()
    git_dir = Path(salida)
    if not git_dir.is_absolute():
        git_dir = path / git_dir
    return normalizar_worktree(git_dir)


def validar_entorno(entorno: EntornoTarea | Tarea) -> ResultadoValidacionEntorno:
    """Inspecciona Git sin modificar rama, HEAD, índice ni archivos."""

    if isinstance(entorno, Tarea):
        entorno = EntornoTarea.desde_tarea(entorno)
    if not isinstance(entorno, EntornoTarea):
        raise TypeError("entorno debe ser EntornoTarea o Tarea")

    worktree = Path(entorno.worktree).expanduser().resolve(strict=False)
    normalizado = normalizar_worktree(worktree)
    discrepancias: list[str] = []
    path_existe = worktree.is_dir()
    if not path_existe:
        discrepancias.append(f"path inexistente: {normalizado}")
        return ResultadoValidacionEntorno(
            entorno,
            normalizado,
            False,
            False,
            False,
            None,
            None,
            (),
            None,
            None,
            tuple(discrepancias),
        )

    dentro = _git(worktree, "rev-parse", "--is-inside-work-tree")
    repo_git_valido = dentro.returncode == 0 and dentro.stdout.strip() == "true"
    if not repo_git_valido:
        discrepancias.append(f"repositorio Git inválido: {normalizado}")
        return ResultadoValidacionEntorno(
            entorno,
            normalizado,
            True,
            False,
            False,
            None,
            None,
            (),
            None,
            None,
            tuple(discrepancias),
        )

    worktree_git_dir = _git_dir_comun(worktree)
    repo = Path(entorno.repo).expanduser().resolve(strict=False)
    repo_git_dir = _git_dir_comun(repo) if repo.is_dir() else None
    repo_coincide = repo_git_dir is not None and repo_git_dir == worktree_git_dir
    if not repo_coincide:
        discrepancias.append("el worktree no pertenece al repo esperado")

    rama_resultado = _git(worktree, "symbolic-ref", "--short", "-q", "HEAD")
    rama_actual = (
        rama_resultado.stdout.strip() if rama_resultado.returncode == 0 else None
    )
    head_resultado = _git(worktree, "rev-parse", "--verify", "HEAD")
    head_actual = head_resultado.stdout.strip() if head_resultado.returncode == 0 else None
    status_resultado = _git(worktree, "status", "--porcelain=v1", "--untracked-files=all")
    estado_git = tuple(status_resultado.stdout.splitlines())

    if rama_actual != entorno.rama:
        discrepancias.append(
            f"rama distinta: esperada={entorno.rama}, actual={rama_actual or 'DETACHED'}"
        )
    if head_actual != entorno.commit_inicial:
        discrepancias.append(
            f"HEAD distinto: esperado={entorno.commit_inicial}, actual={head_actual}"
        )

    return ResultadoValidacionEntorno(
        entorno=entorno,
        worktree_normalizado=normalizado,
        path_existe=True,
        repositorio_git_valido=True,
        repo_coincide=repo_coincide,
        rama_actual=rama_actual,
        head_actual=head_actual,
        estado_git=estado_git,
        repo_git_dir=repo_git_dir,
        worktree_git_dir=worktree_git_dir,
        discrepancias=tuple(discrepancias),
    )


@dataclass(frozen=True)
class ReservaWorktree:
    task_id: str
    repo: str
    worktree: str
    worktree_normalizado: str
    rama_esperada: str
    head_esperado: str
    modo: ModoTarea
    fecha_creacion: str
    ultima_actualizacion: str
    session_id: str
    process_id: int
    host: str
    rama_ultima_validacion: str | None
    head_ultima_validacion: str | None
    estado_git_inicial: tuple[str, ...]

    def __post_init__(self) -> None:
        try:
            UUID(self.task_id)
            UUID(self.session_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ErrorPersistenciaLock("task_id y session_id deben ser UUID válidos") from exc
        for campo in (
            "repo",
            "worktree",
            "worktree_normalizado",
            "rama_esperada",
            "head_esperado",
            "fecha_creacion",
            "ultima_actualizacion",
        ):
            if not isinstance(getattr(self, campo), str) or not getattr(
                self, campo
            ).strip():
                raise ErrorPersistenciaLock(f"{campo} debe ser texto no vacío")
        for campo in ("fecha_creacion", "ultima_actualizacion"):
            try:
                fecha = datetime.fromisoformat(getattr(self, campo))
            except ValueError as exc:
                raise ErrorPersistenciaLock(f"{campo} no es ISO-8601 válido") from exc
            if fecha.tzinfo is None:
                raise ErrorPersistenciaLock(f"{campo} debe incluir zona horaria")
        if not isinstance(self.process_id, int) or self.process_id <= 0:
            raise ErrorPersistenciaLock("process_id debe ser un entero positivo")
        object.__setattr__(self, "modo", ModoTarea(self.modo))
        object.__setattr__(self, "estado_git_inicial", tuple(self.estado_git_inicial))
        if normalizar_worktree(self.worktree) != self.worktree_normalizado:
            raise ErrorPersistenciaLock("worktree_normalizado incoherente")

    def a_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LOCK_SCHEMA_VERSION,
            "task_id": self.task_id,
            "repo": self.repo,
            "worktree": self.worktree,
            "worktree_normalizado": self.worktree_normalizado,
            "rama_esperada": self.rama_esperada,
            "head_esperado": self.head_esperado,
            "modo": self.modo.value,
            "fecha_creacion": self.fecha_creacion,
            "ultima_actualizacion": self.ultima_actualizacion,
            "session_id": self.session_id,
            "process_id": self.process_id,
            "host": self.host,
            "rama_ultima_validacion": self.rama_ultima_validacion,
            "head_ultima_validacion": self.head_ultima_validacion,
            "estado_git_inicial": list(self.estado_git_inicial),
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> ReservaWorktree:
        copia = dict(datos)
        version = copia.pop("schema_version", None)
        if version != LOCK_SCHEMA_VERSION:
            raise ErrorPersistenciaLock(f"schema de lock no soportado: {version}")
        try:
            return cls(**copia)
        except (TypeError, ValueError) as exc:
            raise ErrorPersistenciaLock(f"lock inválido: {exc}") from exc


@dataclass(frozen=True)
class DiagnosticoLock:
    reserva: ReservaWorktree
    posible_huerfano: bool
    motivos: tuple[str, ...]


class GestorEntornos:
    """Coordina validación y propiedad exclusiva persistente de worktrees."""

    def __init__(
        self,
        gestor_tareas: GestorTareas,
        directorio_locks: str | Path = Path("estado") / "locks",
        *,
        session_id: str | None = None,
    ) -> None:
        self.gestor_tareas = gestor_tareas
        self.directorio_locks = Path(directorio_locks)
        self.session_id = str(uuid4()) if session_id is None else session_id
        try:
            UUID(self.session_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ErrorPersistenciaLock("session_id debe ser un UUID válido") from exc

    def reservar_worktree(
        self, task_id: str, worktree: str | Path | None = None
    ) -> ReservaWorktree:
        tarea = self.gestor_tareas.cargar(task_id)
        if tarea.es_terminal:
            raise ErrorEntorno("una tarea terminal no puede adquirir un worktree")
        solicitado = str(worktree) if worktree is not None else tarea.worktree
        if normalizar_worktree(solicitado) != normalizar_worktree(tarea.worktree):
            self._evento_mismatch(
                tarea,
                {"discrepancias": ["worktree solicitado distinto al contratado"]},
            )
            raise ErrorEntorno("worktree solicitado distinto al contratado")

        resultado = validar_entorno(tarea)
        if not resultado.es_valido:
            self._evento_mismatch(tarea, resultado.datos_evento())
            raise ErrorValidacionEntorno(resultado)
        self.gestor_tareas.anadir_evento(
            tarea.id, "ENVIRONMENT_VALIDATED", resultado.datos_evento()
        )

        existente = self.obtener_reserva(solicitado)
        if existente is not None:
            if existente.task_id == task_id:
                return existente
            self._registrar_conflicto(task_id, existente)
            raise ConflictoWorktree(existente)

        timestamp = _ahora_utc()
        reserva = ReservaWorktree(
            task_id=task_id,
            repo=tarea.repo,
            worktree=tarea.worktree,
            worktree_normalizado=resultado.worktree_normalizado,
            rama_esperada=tarea.rama,
            head_esperado=tarea.commit_inicial,
            modo=tarea.modo,
            fecha_creacion=timestamp,
            ultima_actualizacion=timestamp,
            session_id=self.session_id,
            process_id=os.getpid(),
            host=platform.node(),
            rama_ultima_validacion=resultado.rama_actual,
            head_ultima_validacion=resultado.head_actual,
            estado_git_inicial=resultado.estado_git,
        )
        try:
            self._crear_exclusivo(reserva)
        except FileExistsError:
            ganador = self.obtener_reserva(solicitado)
            if ganador is None:
                raise ErrorPersistenciaLock("conflicto concurrente ambiguo")
            if ganador.task_id != task_id:
                self._registrar_conflicto(task_id, ganador)
                raise ConflictoWorktree(ganador)
            return ganador

        self.gestor_tareas.anadir_evento(
            task_id,
            "WORKTREE_LOCKED",
            {
                "worktree": reserva.worktree_normalizado,
                "modo": reserva.modo.value,
                "fecha_creacion": reserva.fecha_creacion,
                "session_id": reserva.session_id,
            },
        )
        return reserva

    def obtener_reserva(self, worktree: str | Path) -> ReservaWorktree | None:
        path = self._path_lock(worktree)
        if not path.exists():
            return None
        return self._cargar_path(path)

    def listar_reservas(self) -> list[ReservaWorktree]:
        if not self.directorio_locks.exists():
            return []
        return [
            self._cargar_path(path)
            for path in sorted(self.directorio_locks.glob("*.json"))
        ]

    def comprobar_conflicto(
        self, worktree: str | Path, task_id: str | None = None
    ) -> ReservaWorktree | None:
        reserva = self.obtener_reserva(worktree)
        if reserva is None or reserva.task_id == task_id:
            return None
        return reserva

    def liberar_worktree(self, task_id: str, worktree: str | Path) -> ReservaWorktree:
        reserva = self.obtener_reserva(worktree)
        if reserva is None:
            raise ReservaNoEncontrada(f"worktree sin reserva: {worktree}")
        if reserva.task_id != task_id:
            raise PropietarioReservaIncorrecto(
                f"la reserva pertenece a {reserva.task_id}, no a {task_id}"
            )
        tarea = self.gestor_tareas.cargar(task_id)
        if not tarea.es_terminal:
            raise LiberacionNoPermitida(
                f"la tarea {task_id} sigue activa en estado {tarea.estado.value}"
            )
        path = self._path_lock(worktree)
        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise ErrorPersistenciaLock("el lock desapareció durante la liberación") from exc
        self.gestor_tareas.anadir_evento(
            task_id,
            "WORKTREE_RELEASED",
            {
                "worktree": reserva.worktree_normalizado,
                "fecha_reserva": reserva.fecha_creacion,
            },
        )
        return reserva

    def reclamar_worktree_recuperacion(
        self, task_id: str, worktree: str | Path
    ) -> ReservaWorktree:
        """Adopta un lock huérfano ya reconciliado sin liberarlo ni recrearlo."""

        reserva = self.obtener_reserva(worktree)
        if reserva is None:
            raise ReservaNoEncontrada(f"worktree sin reserva: {worktree}")
        if reserva.task_id != task_id:
            raise PropietarioReservaIncorrecto(
                f"la reserva pertenece a {reserva.task_id}, no a {task_id}"
            )
        tarea = self.gestor_tareas.cargar(task_id)
        if tarea.es_terminal:
            raise ErrorEntorno("una tarea terminal no puede reclamar un lock")
        resultado = validar_entorno(tarea)
        if not resultado.es_valido:
            raise ErrorValidacionEntorno(resultado)
        actualizada = replace(
            reserva,
            ultima_actualizacion=_ahora_utc(),
            session_id=self.session_id,
            process_id=os.getpid(),
            host=platform.node(),
            rama_ultima_validacion=resultado.rama_actual,
            head_ultima_validacion=resultado.head_actual,
        )
        self._guardar_reemplazo(actualizada)
        return actualizada

    def comprobar_integridad_entorno(
        self, worktree: str | Path
    ) -> ResultadoValidacionEntorno:
        reserva = self.obtener_reserva(worktree)
        if reserva is None:
            raise ReservaNoEncontrada(f"worktree sin reserva: {worktree}")
        entorno = EntornoTarea(
            repo=reserva.repo,
            worktree=reserva.worktree,
            rama=reserva.rama_esperada,
            commit_inicial=reserva.head_esperado,
            modo=reserva.modo,
        )
        resultado = validar_entorno(entorno)
        evento = "ENVIRONMENT_VALIDATED" if resultado.es_valido else "ENVIRONMENT_MISMATCH"
        self.gestor_tareas.anadir_evento(
            reserva.task_id, evento, resultado.datos_evento()
        )
        actualizada = replace(
            reserva,
            ultima_actualizacion=_ahora_utc(),
            rama_ultima_validacion=resultado.rama_actual,
            head_ultima_validacion=resultado.head_actual,
        )
        self._guardar_reemplazo(actualizada)
        return resultado

    def diagnosticar_locks(self) -> list[DiagnosticoLock]:
        diagnosticos: list[DiagnosticoLock] = []
        for reserva in self.listar_reservas():
            motivos: list[str] = []
            if reserva.session_id != self.session_id:
                motivos.append("lock creado por otra sesión del gestor")
            try:
                tarea = self.gestor_tareas.cargar(reserva.task_id)
            except TareaNoEncontrada:
                motivos.append("tarea propietaria inexistente")
            else:
                if tarea.es_terminal:
                    motivos.append("tarea propietaria terminal pendiente de liberación")
                if normalizar_worktree(tarea.worktree) != reserva.worktree_normalizado:
                    motivos.append("worktree del lock no coincide con la tarea")
            diagnosticos.append(
                DiagnosticoLock(reserva, bool(motivos), tuple(motivos))
            )
        return diagnosticos

    def _registrar_conflicto(
        self, task_id: str, reserva: ReservaWorktree
    ) -> None:
        self.gestor_tareas.anadir_evento(
            task_id,
            "WORKTREE_CONFLICT",
            {
                "worktree": reserva.worktree_normalizado,
                "propietario": reserva.task_id,
                "modo_propietario": reserva.modo.value,
            },
        )

    def _evento_mismatch(self, tarea: Tarea, datos: dict[str, Any]) -> None:
        self.gestor_tareas.anadir_evento(tarea.id, "ENVIRONMENT_MISMATCH", datos)

    def _path_lock(self, worktree: str | Path) -> Path:
        identidad = normalizar_worktree(worktree)
        nombre = hashlib.sha256(identidad.encode("utf-8")).hexdigest()
        return self.directorio_locks / f"{nombre}.json"

    def _cargar_path(self, path: Path) -> ReservaWorktree:
        try:
            with path.open("r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
            reserva = ReservaWorktree.desde_dict(datos)
        except (OSError, json.JSONDecodeError, ErrorPersistenciaLock) as exc:
            raise ErrorPersistenciaLock(f"no se pudo cargar {path}: {exc}") from exc
        if self._path_lock(reserva.worktree_normalizado).name != path.name:
            raise ErrorPersistenciaLock(f"identidad de lock incoherente: {path}")
        return reserva

    def _crear_exclusivo(self, reserva: ReservaWorktree) -> None:
        """Publica un JSON completo solo si ningún proceso ganó antes la reserva."""

        self.directorio_locks.mkdir(parents=True, exist_ok=True)
        temporal = self._escribir_temporal(reserva)
        destino = self._path_lock(reserva.worktree_normalizado)
        try:
            os.link(temporal, destino)
        finally:
            temporal.unlink(missing_ok=True)

    def _guardar_reemplazo(self, reserva: ReservaWorktree) -> None:
        destino = self._path_lock(reserva.worktree_normalizado)
        if not destino.exists():
            raise ErrorPersistenciaLock("no se puede actualizar un lock inexistente")
        temporal = self._escribir_temporal(reserva)
        try:
            os.replace(temporal, destino)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise

    def _escribir_temporal(self, reserva: ReservaWorktree) -> Path:
        self.directorio_locks.mkdir(parents=True, exist_ok=True)
        descriptor, nombre = tempfile.mkstemp(
            prefix=".lock.", suffix=".tmp", dir=self.directorio_locks
        )
        temporal = Path(nombre)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(
                    reserva.a_dict(),
                    archivo,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise
        return temporal
