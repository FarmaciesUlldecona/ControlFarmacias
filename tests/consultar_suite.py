"""Hito 2BS: consulta de solo lectura para T2 de ``revisor-reglas``.

Responde si hay una suite en verde registrada para el estado exacto de los cambios, sin exponer el registro
de suites (``logs/agentes`` no lo lee ninguna herramienta: ``.claude/hooks/barreras_agentes.py``). Usa la misma
huella, el mismo alcance exigido y la misma búsqueda que la barrera de commit (``.claude/hooks/estado_git.py``).

Uso (lo único que el revisor ejecuta además de git): ``./.venv/Scripts/python.exe -B tests/consultar_suite.py``

Imprime un JSON: ``base`` (HEAD), ``rutas`` (las de ``git status``), ``exigida`` (``completa`` o ``rapida``),
``suite`` (solo el resumen de la línea válida: alcance, verde, cifras, fechas y si el árbol cambió durante la
suite; nunca el resto del registro) y ``t2`` (``PASS`` o ``FAIL``). Código de salida 0 con PASS, 1 con FAIL.
No escribe nada.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
    huella = eg.huella_de(detalle)
    rutas = [ruta for ruta, _ in detalle["rutas"]]
    exigida = eg.suite_exigida(rutas)
    suite = eg.suite_valida(huella, exigida, ruta_suites, str(repositorio))
    pasa = bool(
        rutas and suite
        and suite.get("verde") is True
        and suite.get("arbol_cambiado_durante_la_suite") is False
        and suite.get("base") == detalle["base"]
        and suite.get("rutas") == [list(r) for r in detalle["rutas"]]
    )
    return {
        "base": detalle["base"],
        "rutas": rutas,
        "exigida": exigida,
        "suite": None if suite is None else {c: suite.get(c) for c in CAMPOS_SUITE},
        "t2": "PASS" if pasa else "FAIL",
    }


def main() -> int:
    respuesta = consultar()
    print(json.dumps(respuesta, ensure_ascii=False, indent=1))
    return 0 if respuesta["t2"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
