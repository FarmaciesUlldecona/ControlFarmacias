"""Hito 2BH: registro verificable de cada ejecución de la suite.

pytest añade, al terminar, una línea JSON a ``logs/agentes/suites.jsonl`` del proyecto (no a la raíz aislada
de los tests: es el registro que exige la barrera de commit, no un artefacto de un test) con:
- la huella exacta del árbol probado (la misma que la barrera de commit y ``revisor-reglas``:
  ``.claude/hooks/estado_git.py``), calculada al empezar y al terminar; si difieren, el árbol cambió durante
  la ejecución y la línea no vale (``huella`` nula);
- passed/failed/errors/skipped, fechas y el alcance (Hito SUITE). En todos, ``tests/`` entero, sin ``-k``, todo lo
  colectado ejecutado y ningún ``pg17_local`` omitido:
  ``total`` (sin ``-m`` ni deseleccionados), ``completa`` (``-m "not historica"``, la de cada commit de código),
  ``historica`` (``-m historica``), ``rapida`` (``-m "not pg17_local"``); ``parcial``, cualquier otra cosa;
- ``verde``: código de salida 0, sin failed ni errors;
- ``fallados`` (tests con fallo o error) y, en las parciales, ``nodeids`` (los ejecutados), sin el sufijo
  ``@familia_*`` de xdist: los usa la regla de reparación de la barrera.

Con pytest-xdist solo escribe el proceso principal; los workers le pasan sus cifras de colección
(``workeroutput["registro_suite"]``) y las de resultado salen del proceso principal, como en serie.

Un fallo al registrar nunca altera el resultado de la suite: solo deja de haber registro (y la barrera de
commit bloquea).
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
MARCA_PG17 = "pg17_local"
MARCA_HISTORICA = "historica"
_SUFIJO_FAMILIA = re.compile(r"@familia_[\w-]+$")


def sin_familia(nodeid: str) -> str:
    return _SUFIJO_FAMILIA.sub("", nodeid)


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
    completo = cubre_tests and not keyword and colectados > 0 and ejecutados == colectados and not pg17_omitidos
    marca = " ".join(markexpr.split())
    if completo and not marca and not deselected and pg17_colectados:
        return "total"
    if completo and marca == f"not {MARCA_HISTORICA}" and pg17_colectados:
        return "completa"
    if completo and marca == MARCA_HISTORICA and pg17_colectados:
        return "historica"
    if completo and marca == f"not {MARCA_PG17}":
        return "rapida"
    return "parcial"


class RegistroSuite:
    def __init__(self, worker: bool = False):
        self.inicio = _ahora()
        self.detalle_inicio = None if worker else _detalle()
        self.colectados = 0
        self.pg17_colectados = 0
        self.deseleccionados = 0
        self.workers: list[dict] = []

    def coleccion(self, items) -> None:
        self.colectados = len(items)
        self.pg17_colectados = sum(1 for i in items if i.get_closest_marker(MARCA_PG17))

    def deseleccion(self, items) -> None:
        self.deseleccionados += len(items)

    def resumen_worker(self) -> dict:
        return {"colectados": self.colectados, "pg17_colectados": self.pg17_colectados,
                "deselected": self.deseleccionados}

    def datos_worker(self, datos) -> None:
        self.workers.append(datos if isinstance(datos, dict) else {})

    def _coleccion_de_los_workers(self) -> tuple[int, int, int | None] | None:
        """Cifras de colección con xdist: todos los workers colectan lo mismo; si no coinciden o falta alguna,
        ``colectados`` = -1 (la ejecución queda ``parcial``)."""
        if not self.workers:
            return None
        claves = {(w.get("colectados"), w.get("pg17_colectados"), w.get("deselected")) for w in self.workers}
        if len(claves) != 1 or None in next(iter(claves)):
            return -1, 0, None
        return next(iter(claves))

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
        colectados, pg17_colectados = self.colectados, self.pg17_colectados
        de_workers = self._coleccion_de_los_workers()
        if de_workers is not None:
            colectados, pg17_colectados, deselected_workers = de_workers
            deselected = deselected if deselected_workers is None else deselected_workers
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
            "colectados": colectados, "ejecutados": ejecutados, "deselected": deselected,
            "passed": n("passed"), "failed": n("failed"), "errors": n("error"), "skipped": n("skipped"),
            "xfailed": n("xfailed"), "xpassed": n("xpassed"),
            "pg17_colectados": pg17_colectados, "pg17_omitidos": pg17_omitidos,
            "exitstatus": int(exitstatus), "workers": len(self.workers),
            "fallados": sorted({sin_familia(r.nodeid) for clave in ("failed", "error")
                                for r in stats.get(clave, []) if hasattr(r, "nodeid")}),
        }
        datos["alcance"] = alcance(cubre_tests=_cubre_tests(session.config), markexpr=markexpr, keyword=keyword,
                                   deselected=deselected, colectados=colectados, ejecutados=ejecutados,
                                   pg17_colectados=pg17_colectados, pg17_omitidos=pg17_omitidos)
        if datos["alcance"] == "parcial":
            datos["nodeids"] = sorted({sin_familia(r.nodeid) for clave in
                                       ("passed", "failed", "skipped", "xfailed", "xpassed", "error")
                                       for r in stats.get(clave, []) if hasattr(r, "nodeid")})
        datos["verde"] = (datos["exitstatus"] == 0 and not datos["failed"] and not datos["errors"]
                          and datos["huella"] is not None)
        return datos

    # PERMISOS-1 (2026-11-27): marca «suite en curso» del proceso principal, para que tests/consultar_suite.py
    # responda EN_CURSO (y el revisor marque T2 INCONCLUSO) mientras la suite no ha terminado.

    def marcar_inicio(self, directorio: Path | None = None) -> Path | None:
        try:
            directorio = directorio or ruta_registro().parent / _estado_git().NOMBRE_EN_CURSO
            os.makedirs(directorio, exist_ok=True)
            self.marca = directorio / f"{os.getpid()}.json"
            self.marca.write_text(json.dumps({"pid": os.getpid(), "ts_inicio": self.inicio}), encoding="utf-8")
            return self.marca
        except Exception as error:  # nunca altera la suite; sin marca, consultar_suite lee el registro
            print(f"\n[registro_suite] no se pudo marcar la suite en curso: {type(error).__name__}: {error}")
            return None

    def quitar_marca(self) -> None:
        marca = getattr(self, "marca", None)
        if marca is None:
            return
        try:
            marca.unlink(missing_ok=True)
        except Exception as error:
            print(f"\n[registro_suite] no se pudo quitar la marca de suite en curso: {type(error).__name__}: {error}")

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
