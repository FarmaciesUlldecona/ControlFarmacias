"""Lectura local y conservadora del resultado funcional persistido de un run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runs_persistentes import RunPersistente


class ResultadoFuncionalNoDisponible(ValueError):
    """El run no conserva un resultado funcional utilizable."""


def obtener_resultado_funcional(run: RunPersistente) -> dict[str, Any]:
    """Obtiene el resultado sin consultar ni validar el repositorio de trabajo."""
    if run.resultado is None:
        raise ResultadoFuncionalNoDisponible("el run no tiene resultado persistido")
    state = (run.resultado.metadata.get("ejecucion") or {}).get("state_historico") or {}
    candidato = state.get("resultado_funcional")
    origen = "metadata del run"
    if not isinstance(candidato, dict):
        candidato, origen = _leer_artefacto_ciclo(Path(run.directorio_run))
    return {**_validar(candidato), "origen": origen}


def _leer_artefacto_ciclo(run_dir: Path) -> tuple[dict[str, Any], str]:
    candidatos = sorted(run_dir.glob("ciclo_*/resultado_correccion.json"), reverse=True)
    candidatos += sorted(run_dir.glob("ciclo_*/resultado_ejecutor.json"), reverse=True)
    for path in candidatos:
        try:
            datos = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(datos, dict):
            return datos, str(path.resolve())
    raise ResultadoFuncionalNoDisponible(
        "no existe resultado_ejecutor.json ni resultado_funcional en metadata"
    )


def _validar(datos: dict[str, Any]) -> dict[str, Any]:
    resumen = datos.get("resumen")
    if not isinstance(resumen, str) or not resumen.strip():
        raise ResultadoFuncionalNoDisponible("el resultado funcional no contiene resumen")
    archivos = datos.get("archivos_modificados", [])
    if not isinstance(archivos, list) or not all(isinstance(item, str) for item in archivos):
        raise ResultadoFuncionalNoDisponible("archivos_modificados no es una lista válida")
    tests = datos.get("tests_ejecutados", [])
    if not isinstance(tests, list) or not all(isinstance(item, str) for item in tests):
        tests = []
    return {
        "estado": datos.get("estado"),
        "resumen": resumen.strip(),
        "detalle": datos.get("detalle") if isinstance(datos.get("detalle"), str) else "",
        "siguiente_paso": datos.get("siguiente_paso") if isinstance(datos.get("siguiente_paso"), str) else "",
        "archivos_modificados": archivos,
        "tests_correctos": datos.get("tests_correctos"),
        "tests_ejecutados": tests,
    }
