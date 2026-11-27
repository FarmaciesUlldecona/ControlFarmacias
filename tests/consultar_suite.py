"""Hito 2BS: consulta de solo lectura para T2 de ``revisor-reglas``.

Responde si hay una suite en verde registrada para el estado exacto de los cambios, sin exponer el registro
de suites (``logs/agentes`` no lo lee ninguna herramienta: ``.claude/hooks/barreras_agentes.py``). Usa la misma
huella, el mismo alcance exigido y la misma búsqueda que la barrera de commit (``.claude/hooks/estado_git.py``).

Uso (lo único que el revisor ejecuta además de git): ``./.venv/Scripts/python.exe -B tests/consultar_suite.py``

Imprime un JSON: ``base`` (HEAD), ``rutas`` (las de ``git status``), ``exigida`` (``completa`` o ``rapida``),
``suite`` (solo el resumen de la línea válida: alcance, verde, cifras, fechas y si el árbol cambió durante la
suite; nunca el resto del registro) y ``t2`` (``PASS`` o ``FAIL``). Código de salida 0 con PASS, 1 con FAIL.
PERMISOS-1: si hay una suite en curso, solo ``base``, ``rutas``, ``suites_en_curso`` y ``t2: "EN_CURSO"``
(código 1), sin leer el registro. No escribe nada.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Hito SUITE: también ``historica_exigida`` (``exacta``/``semanal``/null) e ``historica`` (resumen de la línea).
CAMPOS_SUITE = ("alcance", "verde", "passed", "failed", "errors", "skipped", "ts_inicio", "ts_fin",
                "arbol_cambiado_durante_la_suite")


def _estado_git():
    spec = importlib.util.spec_from_file_location("estado_git_2bs", ROOT / ".claude/hooks/estado_git.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def consultar(repositorio: Path = ROOT, ruta_suites: str | None = None) -> dict:
    eg = _estado_git()
    detalle = eg.detalle_cambios(str(repositorio))
    rutas = [ruta for ruta, _ in detalle["rutas"]]
    # PERMISOS-1 (DECISIÓN DE PIO, 2026-11-27): con una suite en curso no se lee el registro; el revisor marca T2
    # INCONCLUSO y lo vuelve a consultar cuando las suites hayan terminado.
    en_curso = eg.suites_en_curso(eg.directorio_en_curso(ruta_suites))
    if en_curso:
        return {"base": detalle["base"], "rutas": rutas, "suites_en_curso": len(en_curso), "t2": "EN_CURSO"}
    # Hito SUITE: las mismas reglas que la barrera de commit (completa directa o por reparación + histórica).
    estado = eg.suites_para_commit(rutas, ruta_suites, str(repositorio), detalle=detalle)
    exigida, suite, historica = estado["exigida"], estado["suite"], estado["historica"]
    pasa = bool(
        rutas and suite and estado["ok"]
        and suite.get("verde") is True
        and suite.get("arbol_cambiado_durante_la_suite") is False
        and suite.get("base") == detalle["base"]
        and suite.get("rutas") == [list(r) for r in detalle["rutas"]]
    )
    return {
        "base": detalle["base"],
        "rutas": rutas,
        "exigida": exigida,
        "suite": None if suite is None else {**{c: suite.get(c) for c in CAMPOS_SUITE}, "via": suite.get("via")},
        "historica_exigida": estado["historica_modo"],
        "historica": None if historica is None else {c: historica.get(c) for c in CAMPOS_SUITE},
        "t2": "PASS" if pasa else "FAIL",
    }


def main() -> int:
    respuesta = consultar()
    print(json.dumps(respuesta, ensure_ascii=False, indent=1))
    return 0 if respuesta["t2"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
