"""Hito 2BH: registro verificable de cada ejecución de la suite.

pytest añade, al terminar, una línea JSON a ``logs/agentes/suites.jsonl`` del proyecto (no a la raíz aislada
de los tests: es el registro que exige la barrera de commit, no un artefacto de un test) con:
- la huella exacta del árbol probado (la misma que la barrera de commit y ``revisor-reglas``:
  ``.claude/hooks/estado_git.py``), calculada al empezar y al terminar; si difieren, el árbol cambió durante
  la ejecución y la línea no vale (``huella`` nula);
- passed/failed/errors/skipped, fechas y el alcance: ``completa`` (todo ``tests/``, sin ``-k``/``-m``, nada
  deseleccionado, todo ejecutado y ningún ``pg17_local`` omitido), ``rapida`` (lo mismo con
  ``-m "not pg17_local"``) o ``parcial`` (cualquier otra cosa);
- ``verde``: código de salida 0, sin failed ni errors.

Un fallo al registrar nunca altera el resultado de la suite: solo deja de haber registro (y la barrera de
commit bloquea).
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
MARCA_PG17 = "pg17_local"


def _estado_git():
    spec = importlib.util.spec_from_file_location("estado_git_2bh", ROOT / ".claude/hooks/estado_git.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def ruta_registro() -> Path:
    return ROOT / "logs" / "agentes" / "suites.jsonl"


def _ahora() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _detalle() -> dict | None:
    try:
        return _estado_git().detalle_cambios(str(ROOT))
    except Exception:  # sin git: no hay huella
        return None


def _cubre_tests(config) -> bool:
    """Los argumentos posicionales son exactamente ``tests/`` (o ninguno: ``testpaths``)."""
    args = [a for a in config.args if a]
    base = Path(config.invocation_params.dir)
    return all((base / a).resolve() == TESTS for a in args)


def alcance(*, cubre_tests: bool, markexpr: str, keyword: str, deselected: int, colectados: int,
            ejecutados: int, pg17_colectados: int, pg17_omitidos: int) -> str:
    completo = cubre_tests and not keyword and ejecutados == colectados
    if completo and not markexpr.strip() and not deselected and pg17_colectados and not pg17_omitidos:
        return "completa"
    if completo and " ".join(markexpr.split()) == f"not {MARCA_PG17}" and not pg17_omitidos:
        return "rapida"
    return "parcial"


class RegistroSuite:
    def __init__(self):
        self.inicio = _ahora()
        self.detalle_inicio = _detalle()
        self.colectados = 0
        self.pg17_colectados = 0

    def coleccion(self, items) -> None:
        self.colectados = len(items)
        self.pg17_colectados = sum(1 for i in items if i.get_closest_marker(MARCA_PG17))

    def linea(self, session, exitstatus) -> dict:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        stats = getattr(reporter, "stats", {}) or {}

        def n(clave):  # mismas cifras que la línea final de pytest
            return len(stats.get(clave, []))

        omitidos = stats.get("skipped", [])
        pg17_omitidos = sum(1 for r in omitidos if MARCA_PG17 in getattr(r, "keywords", {}))
        ejecutados = len({r.nodeid for clave in ("passed", "failed", "skipped", "xfailed", "xpassed", "error")
                          for r in stats.get(clave, []) if hasattr(r, "nodeid")})
        deselected = len(stats.get("deselected", []))
        detalle_fin = _detalle()
        mismo_arbol = self.detalle_inicio is not None and self.detalle_inicio == detalle_fin
        eg = _estado_git()
        markexpr = session.config.getoption("markexpr", "") or ""
        keyword = session.config.getoption("keyword", "") or ""
        datos = {
            "ts_inicio": self.inicio, "ts_fin": _ahora(),
            "repositorio": eg.clave_repositorio(str(ROOT)),
            "base": (detalle_fin or {}).get("base"),
            "rutas": (detalle_fin or {}).get("rutas"),
            "huella": eg.huella_de(detalle_fin) if mismo_arbol else None,
            "arbol_cambiado_durante_la_suite": not mismo_arbol,
            "args": list(session.config.invocation_params.args),
            "markexpr": markexpr, "keyword": keyword,
            "colectados": self.colectados, "ejecutados": ejecutados, "deselected": deselected,
            "passed": n("passed"), "failed": n("failed"), "errors": n("error"), "skipped": n("skipped"),
            "xfailed": n("xfailed"), "xpassed": n("xpassed"),
            "pg17_colectados": self.pg17_colectados, "pg17_omitidos": pg17_omitidos,
            "exitstatus": int(exitstatus),
        }
        datos["alcance"] = alcance(cubre_tests=_cubre_tests(session.config), markexpr=markexpr, keyword=keyword,
                                   deselected=deselected, colectados=self.colectados, ejecutados=ejecutados,
                                   pg17_colectados=self.pg17_colectados, pg17_omitidos=pg17_omitidos)
        datos["verde"] = (datos["exitstatus"] == 0 and not datos["failed"] and not datos["errors"]
                          and datos["huella"] is not None)
        return datos

    def escribir(self, session, exitstatus, ruta: Path | None = None) -> dict | None:
        try:
            datos = self.linea(session, exitstatus)
            ruta = ruta or ruta_registro()
            os.makedirs(ruta.parent, exist_ok=True)
            with open(ruta, "a", encoding="utf-8", newline="\n") as archivo:
                archivo.write(json.dumps(datos, ensure_ascii=False) + "\n")
            return datos
        except Exception as error:  # nunca altera el resultado de la suite
            print(f"\n[registro_suite] no se pudo registrar la ejecución: {type(error).__name__}: {error}")
            return None
