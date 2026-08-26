"""Validación determinista entre llamadas Codex, sin red ni IA."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Iterable


MAX_TESTS_POR_NIVEL = {
    "CODEX_LIGHT": 2,
    "CODEX_STANDARD": 6,
    "CODEX_HEAVY": 12,
}


@dataclass(frozen=True)
class ResultadoValidacionLocal:
    exito: bool
    comprobaciones: tuple[str, ...]
    errores: tuple[str, ...]
    tests_ejecutados: tuple[str, ...]
    comandos: tuple[tuple[str, ...], ...]

    def a_dict(self) -> dict:
        return asdict(self)


def validar_cambios_localmente(
    repo: str | Path,
    paths_cambiados: Iterable[str],
    *,
    nivel_recurso: str,
    tests_relevantes: Iterable[str] = (),
    timeout_seconds: int = 600,
) -> ResultadoValidacionLocal:
    raiz = Path(repo).resolve()
    paths = tuple(dict.fromkeys(str(item).replace("\\", "/") for item in paths_cambiados))
    errores: list[str] = []
    comprobaciones: list[str] = []
    comandos: list[tuple[str, ...]] = []

    diff_cmd = ("git", "diff", "--check")
    diff = subprocess.run(
        diff_cmd, cwd=raiz, capture_output=True, text=True, check=False,
        timeout=timeout_seconds,
    )
    comandos.append(diff_cmd)
    comprobaciones.append("GIT_DIFF_CHECK")
    if diff.returncode != 0:
        errores.append((diff.stdout + diff.stderr).strip() or "git diff --check falló")

    for relativo in paths:
        destino = (raiz / relativo).resolve()
        try:
            destino.relative_to(raiz)
        except ValueError:
            errores.append(f"ruta fuera del repositorio: {relativo}")
            continue
        if not destino.is_file():
            continue
        try:
            texto = destino.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errores.append(f"no se pudo leer {relativo}: {exc}")
            continue
        if any(linea.rstrip("\r\n").endswith((" ", "\t")) for linea in texto.splitlines(True)):
            errores.append(f"espacios finales detectados: {relativo}")
        if destino.suffix.casefold() == ".py":
            comprobaciones.append(f"PY_COMPILE:{relativo}")
            try:
                compile(texto, str(destino), "exec")
            except SyntaxError as exc:
                errores.append(f"{relativo}:{exc.lineno}: {exc.msg}")

    tests = _seleccionar_tests(
        raiz, paths, tests_relevantes,
        max_tests=MAX_TESTS_POR_NIVEL.get(nivel_recurso, 0),
    )
    if tests and not errores:
        with tempfile.TemporaryDirectory(prefix="cf_codex_validacion_") as basetemp:
            test_cmd = (
                sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                "--basetemp", basetemp, *tests,
            )
            prueba = subprocess.run(
                test_cmd, cwd=raiz, capture_output=True, text=True, check=False,
                timeout=timeout_seconds,
            )
            comandos.append(test_cmd)
            comprobaciones.append("PYTEST_FOCAL")
            if prueba.returncode != 0:
                salida = (prueba.stdout + prueba.stderr).strip()
                errores.append(salida[-4000:] or "pytest focal falló")

    return ResultadoValidacionLocal(
        not errores,
        tuple(comprobaciones),
        tuple(errores),
        tests,
        tuple(comandos),
    )


def _seleccionar_tests(
    repo: Path,
    paths_cambiados: tuple[str, ...],
    declarados: Iterable[str],
    *,
    max_tests: int,
) -> tuple[str, ...]:
    if max_tests <= 0:
        return ()
    candidatos: list[str] = []
    for valor in declarados:
        ruta = str(valor).replace("\\", "/")
        if (repo / ruta).is_file() and ruta.endswith(".py"):
            candidatos.append(ruta)
    for relativo in paths_cambiados:
        ruta = Path(relativo)
        if ruta.name.startswith("test_") and ruta.suffix == ".py" and (repo / ruta).is_file():
            candidatos.append(ruta.as_posix())
            continue
        if ruta.suffix != ".py":
            continue
        patron = f"test_{ruta.stem}*.py"
        tests_dir = repo / "tests"
        if tests_dir.is_dir():
            candidatos.extend(
                item.relative_to(repo).as_posix()
                for item in sorted(tests_dir.rglob(patron))
            )
    return tuple(dict.fromkeys(candidatos))[:max_tests]
