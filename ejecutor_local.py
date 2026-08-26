"""Ejecución local, determinista y cerrada para operaciones LOCAL_ONLY."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Sequence

from politica_recursos import NivelTests


PYTHON_ORQUESTADOR = Path(
    r"C:\ControlFarmacias\Programa\.venv\Scripts\python.exe"
)
BASETEMP_PYTEST = Path(
    r"C:\ControlFarmacias\tmp_pytest_orquestador_codex_v0211"
)


class ErrorSolicitudLocal(ValueError):
    """La solicitud local no cumple el contrato cerrado del ejecutor."""


class OperacionLocal(str, Enum):
    GIT_STATUS = "GIT_STATUS"
    CALCULAR_SHA256 = "CALCULAR_SHA256"
    COMPROBAR_ARCHIVO = "COMPROBAR_ARCHIVO"
    LISTAR_ARCHIVOS = "LISTAR_ARCHIVOS"
    VALIDAR_JSON = "VALIDAR_JSON"
    PY_COMPILE = "PY_COMPILE"
    EJECUTAR_TESTS = "EJECUTAR_TESTS"


@dataclass(frozen=True)
class SolicitudEjecucionLocal:
    operacion: OperacionLocal | str
    raiz: str | Path
    rutas: tuple[str, ...] = ()
    nivel_tests: NivelTests | str | None = None
    timeout_segundos: float = 120.0
    recursivo: bool = False
    limite_resultados: int = 1000

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "operacion", OperacionLocal(self.operacion))
        except ValueError as exc:
            raise ErrorSolicitudLocal("operación local no soportada") from exc
        object.__setattr__(self, "raiz", Path(self.raiz).resolve())
        if not isinstance(self.rutas, tuple):
            raise ErrorSolicitudLocal("rutas debe ser una tupla")
        if self.nivel_tests is not None:
            try:
                object.__setattr__(self, "nivel_tests", NivelTests(self.nivel_tests))
            except ValueError as exc:
                raise ErrorSolicitudLocal("nivel_tests no soportado") from exc
        if (
            not isinstance(self.timeout_segundos, (int, float))
            or isinstance(self.timeout_segundos, bool)
            or not 0 < self.timeout_segundos <= 3600
        ):
            raise ErrorSolicitudLocal("timeout_segundos debe estar entre 0 y 3600")
        if not isinstance(self.recursivo, bool):
            raise ErrorSolicitudLocal("recursivo debe ser booleano")
        if (
            not isinstance(self.limite_resultados, int)
            or isinstance(self.limite_resultados, bool)
            or not 1 <= self.limite_resultados <= 10000
        ):
            raise ErrorSolicitudLocal("limite_resultados fuera de rango")
        if not all(isinstance(ruta, str) and ruta.strip() for ruta in self.rutas):
            raise ErrorSolicitudLocal("las rutas deben ser textos no vacíos")


@dataclass(frozen=True)
class ResultadoEjecucionLocal:
    operacion: str
    exito: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timeout: bool = False
    error: str | None = None
    datos: dict[str, Any] = field(default_factory=dict)

    def a_dict(self) -> dict[str, Any]:
        return {
            "operacion": self.operacion,
            "exito": self.exito,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timeout": self.timeout,
            "error": self.error,
            "datos": self.datos,
        }


class EjecutorLocal:
    """Ejecutor sin Codex, APIs externas ni comandos proporcionados por texto libre."""

    def __init__(
        self,
        *,
        python_executable: str | Path = PYTHON_ORQUESTADOR,
        pytest_basetemp: str | Path = BASETEMP_PYTEST,
    ) -> None:
        self._python_executable = Path(python_executable)
        self._pytest_basetemp = Path(pytest_basetemp)

    def ejecutar(self, solicitud: SolicitudEjecucionLocal) -> ResultadoEjecucionLocal:
        if not isinstance(solicitud, SolicitudEjecucionLocal):
            raise ErrorSolicitudLocal("solicitud local inválida")
        if not solicitud.raiz.is_dir():
            return self._fallo(solicitud, "la raíz local no existe o no es directorio")

        try:
            rutas = tuple(self._resolver_ruta(solicitud.raiz, ruta) for ruta in solicitud.rutas)
            operacion = solicitud.operacion
            if operacion is OperacionLocal.GIT_STATUS:
                return self._subprocess(
                    solicitud,
                    ["git", "-C", str(solicitud.raiz), "status", "--short", "--branch"],
                )
            if operacion is OperacionLocal.CALCULAR_SHA256:
                return self._sha256(solicitud, rutas)
            if operacion is OperacionLocal.COMPROBAR_ARCHIVO:
                return self._comprobar_archivo(solicitud, rutas)
            if operacion is OperacionLocal.LISTAR_ARCHIVOS:
                return self._listar_archivos(solicitud, rutas)
            if operacion is OperacionLocal.VALIDAR_JSON:
                return self._validar_json(solicitud, rutas)
            if operacion is OperacionLocal.PY_COMPILE:
                return self._py_compile(solicitud, rutas)
            if operacion is OperacionLocal.EJECUTAR_TESTS:
                return self._pytest(solicitud, rutas)
        except (ErrorSolicitudLocal, OSError) as exc:
            return self._fallo(solicitud, str(exc))
        return self._fallo(solicitud, "operación local no soportada")

    @staticmethod
    def _resolver_ruta(raiz: Path, ruta: str) -> Path:
        candidata = (raiz / ruta).resolve()
        try:
            candidata.relative_to(raiz)
        except ValueError as exc:
            raise ErrorSolicitudLocal("ruta fuera del alcance local") from exc
        return candidata

    @staticmethod
    def _exigir_rutas(solicitud: SolicitudEjecucionLocal, rutas: Sequence[Path]) -> None:
        if not rutas:
            raise ErrorSolicitudLocal(
                f"{solicitud.operacion.value} requiere al menos una ruta explícita"
            )

    def _sha256(
        self, solicitud: SolicitudEjecucionLocal, rutas: Sequence[Path]
    ) -> ResultadoEjecucionLocal:
        self._exigir_rutas(solicitud, rutas)
        hashes: dict[str, str] = {}
        for ruta in rutas:
            if not ruta.is_file():
                raise ErrorSolicitudLocal(f"no es un archivo: {ruta.name}")
            digest = hashlib.sha256()
            with ruta.open("rb") as archivo:
                for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
                    digest.update(bloque)
            hashes[str(ruta.relative_to(solicitud.raiz))] = digest.hexdigest()
        return self._ok(solicitud, datos={"sha256": hashes})

    def _comprobar_archivo(
        self, solicitud: SolicitudEjecucionLocal, rutas: Sequence[Path]
    ) -> ResultadoEjecucionLocal:
        self._exigir_rutas(solicitud, rutas)
        elementos = [
            {
                "ruta": str(ruta.relative_to(solicitud.raiz)),
                "existe": ruta.exists(),
                "es_archivo": ruta.is_file(),
                "es_directorio": ruta.is_dir(),
            }
            for ruta in rutas
        ]
        return self._ok(solicitud, datos={"elementos": elementos})

    def _listar_archivos(
        self, solicitud: SolicitudEjecucionLocal, rutas: Sequence[Path]
    ) -> ResultadoEjecucionLocal:
        bases = rutas or (solicitud.raiz,)
        encontrados: list[str] = []
        for base in bases:
            if not base.is_dir():
                raise ErrorSolicitudLocal(f"no es un directorio: {base.name}")
            iterator = base.rglob("*") if solicitud.recursivo else base.iterdir()
            for item in iterator:
                if item.is_file():
                    encontrados.append(str(item.relative_to(solicitud.raiz)))
                    if len(encontrados) >= solicitud.limite_resultados:
                        return self._ok(
                            solicitud,
                            datos={"archivos": sorted(encontrados), "truncado": True},
                        )
        return self._ok(
            solicitud, datos={"archivos": sorted(encontrados), "truncado": False}
        )

    def _validar_json(
        self, solicitud: SolicitudEjecucionLocal, rutas: Sequence[Path]
    ) -> ResultadoEjecucionLocal:
        self._exigir_rutas(solicitud, rutas)
        resultados: list[dict[str, Any]] = []
        todos_validos = True
        for ruta in rutas:
            if not ruta.is_file():
                raise ErrorSolicitudLocal(f"no es un archivo: {ruta.name}")
            try:
                with ruta.open("r", encoding="utf-8") as archivo:
                    json.load(archivo)
                resultados.append({"ruta": str(ruta.relative_to(solicitud.raiz)), "valido": True, "error": None})
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                todos_validos = False
                resultados.append({"ruta": str(ruta.relative_to(solicitud.raiz)), "valido": False, "error": str(exc)})
        if todos_validos:
            return self._ok(solicitud, datos={"resultados": resultados})
        return ResultadoEjecucionLocal(
            operacion=solicitud.operacion.value,
            exito=False,
            returncode=1,
            error="JSON_INVALIDO",
            datos={"resultados": resultados},
        )

    def _py_compile(
        self, solicitud: SolicitudEjecucionLocal, rutas: Sequence[Path]
    ) -> ResultadoEjecucionLocal:
        self._exigir_rutas(solicitud, rutas)
        if not self._python_executable.is_file():
            return self._fallo(solicitud, "intérprete Python configurado no disponible")
        for ruta in rutas:
            if not ruta.is_file() or ruta.suffix.lower() != ".py":
                raise ErrorSolicitudLocal(f"ruta Python inválida: {ruta.name}")
        return self._subprocess(
            solicitud,
            [str(self._python_executable), "-m", "py_compile", *(str(ruta) for ruta in rutas)],
        )

    def _pytest(
        self, solicitud: SolicitudEjecucionLocal, rutas: Sequence[Path]
    ) -> ResultadoEjecucionLocal:
        if solicitud.nivel_tests is None:
            raise ErrorSolicitudLocal("EJECUTAR_TESTS requiere nivel_tests explícito")
        if not self._python_executable.is_file():
            return self._fallo(solicitud, "intérprete Python configurado no disponible")
        if solicitud.nivel_tests is NivelTests.SUITE_COMPLETA:
            if rutas:
                raise ErrorSolicitudLocal("SUITE_COMPLETA no acepta selección parcial")
            objetivos = [str(solicitud.raiz)]
        else:
            self._exigir_rutas(solicitud, rutas)
            for ruta in rutas:
                if not ruta.exists():
                    raise ErrorSolicitudLocal(f"test no encontrado: {ruta.name}")
                if ruta.is_file() and (ruta.suffix != ".py" or not ruta.name.startswith("test_")):
                    raise ErrorSolicitudLocal(f"archivo de test no permitido: {ruta.name}")
            objetivos = [str(ruta) for ruta in rutas]
        return self._subprocess(
            solicitud,
            [
                str(self._python_executable), "-m", "pytest", *objetivos,
                "-q", "-p", "no:cacheprovider", "--basetemp", str(self._pytest_basetemp),
            ],
        )

    def _subprocess(
        self, solicitud: SolicitudEjecucionLocal, argumentos: list[str]
    ) -> ResultadoEjecucionLocal:
        try:
            completado = subprocess.run(
                argumentos,
                cwd=solicitud.raiz,
                shell=False,
                timeout=solicitud.timeout_segundos,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ResultadoEjecucionLocal(
                operacion=solicitud.operacion.value,
                exito=False,
                stdout=self._texto_timeout(exc.stdout),
                stderr=self._texto_timeout(exc.stderr),
                timeout=True,
                error="TIMEOUT",
            )
        except OSError as exc:
            return self._fallo(solicitud, str(exc))
        return ResultadoEjecucionLocal(
            operacion=solicitud.operacion.value,
            exito=completado.returncode == 0,
            returncode=completado.returncode,
            stdout=completado.stdout,
            stderr=completado.stderr,
            error=None if completado.returncode == 0 else "SUBPROCESS_FAILED",
        )

    @staticmethod
    def _texto_timeout(valor: str | bytes | None) -> str:
        if valor is None:
            return ""
        if isinstance(valor, bytes):
            return valor.decode("utf-8", errors="replace")
        return valor

    @staticmethod
    def _ok(
        solicitud: SolicitudEjecucionLocal, *, datos: dict[str, Any] | None = None
    ) -> ResultadoEjecucionLocal:
        return ResultadoEjecucionLocal(
            operacion=solicitud.operacion.value,
            exito=True,
            returncode=0,
            datos=datos or {},
        )

    @staticmethod
    def _fallo(
        solicitud: SolicitudEjecucionLocal, error: str
    ) -> ResultadoEjecucionLocal:
        return ResultadoEjecucionLocal(
            operacion=solicitud.operacion.value,
            exito=False,
            error=error,
        )
