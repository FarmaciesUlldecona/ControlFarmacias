"""Hito 2BH: registro de cada ejecución de la suite (tests/registro_suite.py).

Sin pytest anidado: la sesión es un doble mínimo. La escritura va siempre a ``tmp_path``, nunca a ``logs/``.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import registro_suite as rs

BASE = dict(cubre_tests=True, markexpr="", keyword="", deselected=0, colectados=10, ejecutados=10,
            pg17_colectados=3, pg17_omitidos=0)


def test_alcance_total():
    assert rs.alcance(**BASE) == "total"


def test_alcance_completa_sin_historica():
    assert rs.alcance(**{**BASE, "markexpr": "not  historica", "deselected": 2, "colectados": 8,
                         "ejecutados": 8}) == "completa"


def test_alcance_historica():
    assert rs.alcance(**{**BASE, "markexpr": "historica", "deselected": 7, "colectados": 3,
                         "ejecutados": 3}) == "historica"


def test_alcance_rapida():
    assert rs.alcance(**{**BASE, "markexpr": "not  pg17_local", "deselected": 3, "colectados": 7,
                         "ejecutados": 7, "pg17_colectados": 0}) == "rapida"


@pytest.mark.parametrize("cambio", [
    {"cubre_tests": False},                   # un fichero o carpeta concretos
    {"keyword": "r19"},                       # -k
    {"markexpr": "pg17_local"},               # solo pg17
    {"deselected": 1},                        # --deselect
    {"ejecutados": 9},                        # -x o interrupcion
    {"pg17_omitidos": 1},                     # sin Docker o fixture ausente
    {"pg17_colectados": 0},                   # total sin ningun pg17
    {"markexpr": "not historica", "pg17_colectados": 0},
    {"markexpr": "not historica", "pg17_omitidos": 1},
    {"markexpr": "historica", "ejecutados": 9},
    {"markexpr": "historica and pg17_local"},  # otra expresion
    {"colectados": 0, "ejecutados": 0},       # nada colectado (p. ej., xdist sin cifras)
])
def test_alcance_parcial(cambio):
    assert rs.alcance(**{**BASE, **cambio}) == "parcial"


def _reporte(nodeid, keywords=()):
    return SimpleNamespace(nodeid=nodeid, keywords={k: 1 for k in keywords})


def _sesion(stats, *, args=("tests/",), markexpr="", keyword=""):
    reporter = SimpleNamespace(stats=stats)
    opciones = {"markexpr": markexpr, "keyword": keyword}
    config = SimpleNamespace(
        pluginmanager=SimpleNamespace(get_plugin=lambda nombre: reporter),
        getoption=lambda nombre, defecto=None: opciones.get(nombre, defecto),
        args=list(args), invocation_params=SimpleNamespace(args=tuple(args), dir=str(rs.ROOT)))
    return SimpleNamespace(config=config)


def _registro(monkeypatch, *, inicio, fin, pg17=1):
    detalles = iter([inicio, fin])
    monkeypatch.setattr(rs, "_detalle", lambda: next(detalles))
    registro = rs.RegistroSuite()
    item = SimpleNamespace(get_closest_marker=lambda m: object())
    otro = SimpleNamespace(get_closest_marker=lambda m: None)
    registro.coleccion([item] * pg17 + [otro])
    return registro


ARBOL = {"base": "abc", "rutas": [["src/x.py", "1" * 64]]}


def test_linea_completa_verde_con_la_huella_de_la_barrera(monkeypatch, tmp_path):
    registro = _registro(monkeypatch, inicio=ARBOL, fin=ARBOL)
    stats = {"passed": [_reporte("a", ["pg17_local"]), _reporte("b")]}
    datos = registro.escribir(_sesion(stats), 0, tmp_path / "suites.jsonl")
    [linea] = [json.loads(l) for l in (tmp_path / "suites.jsonl").read_text(encoding="utf-8").splitlines()]
    assert linea == datos
    assert (linea["alcance"], linea["verde"], linea["passed"], linea["failed"]) == ("total", True, 2, 0)
    assert linea["fallados"] == [] and "nodeids" not in linea
    assert linea["huella"] == rs._estado_git().huella_de(ARBOL) and linea["base"] == "abc"
    assert linea["repositorio"] == rs._estado_git().clave_repositorio(str(rs.ROOT))


def test_linea_con_fallo_no_es_verde(monkeypatch, tmp_path):
    registro = _registro(monkeypatch, inicio=ARBOL, fin=ARBOL)
    stats = {"passed": [_reporte("a", ["pg17_local"])], "failed": [_reporte("b")]}
    datos = registro.escribir(_sesion(stats), 1, tmp_path / "suites.jsonl")
    assert (datos["failed"], datos["verde"]) == (1, False)
    assert datos["fallados"] == ["b"]


def test_fallados_y_nodeids_sin_el_sufijo_de_familia(monkeypatch, tmp_path):
    registro = _registro(monkeypatch, inicio=ARBOL, fin=ARBOL)
    stats = {"passed": [_reporte("t.py::a@familia_2az", ["pg17_local"])],
             "error": [_reporte("t.py::b[x@y]@familia_r20")], "failed": [_reporte("u.py::c")]}
    datos = registro.escribir(_sesion(stats, args=("tests/t.py",)), 1, tmp_path / "suites.jsonl")
    assert datos["fallados"] == ["t.py::b[x@y]", "u.py::c"]
    assert datos["alcance"] == "parcial" and datos["nodeids"] == ["t.py::a", "t.py::b[x@y]", "u.py::c"]


def _registro_xdist(monkeypatch, workers):
    detalles = iter([ARBOL, ARBOL])
    monkeypatch.setattr(rs, "_detalle", lambda: next(detalles))
    registro = rs.RegistroSuite()
    for w in workers:
        registro.datos_worker(w)
    return registro


def test_xdist_usa_las_cifras_de_coleccion_de_los_workers(monkeypatch, tmp_path):
    w = {"colectados": 2, "pg17_colectados": 1, "deselected": 1}
    registro = _registro_xdist(monkeypatch, [w, dict(w)])
    stats = {"passed": [_reporte("a@familia_x", ["pg17_local"]), _reporte("b")]}
    datos = registro.escribir(_sesion(stats, markexpr="not historica"), 0, tmp_path / "suites.jsonl")
    assert (datos["alcance"], datos["colectados"], datos["deselected"], datos["workers"]) == ("completa", 2, 1, 2)


@pytest.mark.parametrize("workers", [
    [{"colectados": 2, "pg17_colectados": 1, "deselected": 0},
     {"colectados": 3, "pg17_colectados": 1, "deselected": 0}],
    [{"colectados": 2, "pg17_colectados": 1, "deselected": 0}, {}],
    [None],
])
def test_xdist_con_cifras_distintas_o_ausentes_es_parcial(monkeypatch, tmp_path, workers):
    registro = _registro_xdist(monkeypatch, workers)
    stats = {"passed": [_reporte("a", ["pg17_local"]), _reporte("b")]}
    datos = registro.escribir(_sesion(stats), 0, tmp_path / "suites.jsonl")
    assert datos["alcance"] == "parcial"


def test_el_worker_no_calcula_la_huella(monkeypatch):
    monkeypatch.setattr(rs, "_detalle", lambda: (_ for _ in ()).throw(AssertionError("git en el worker")))
    registro = rs.RegistroSuite(worker=True)
    registro.coleccion([SimpleNamespace(get_closest_marker=lambda m: object())])
    registro.deseleccion([1, 2])
    assert registro.resumen_worker() == {"colectados": 1, "pg17_colectados": 1, "deselected": 2}


def test_arbol_cambiado_durante_la_suite_no_tiene_huella(monkeypatch, tmp_path):
    otro = {"base": "abc", "rutas": [["src/x.py", "2" * 64]]}
    registro = _registro(monkeypatch, inicio=ARBOL, fin=otro)
    stats = {"passed": [_reporte("a", ["pg17_local"]), _reporte("b")]}
    datos = registro.escribir(_sesion(stats), 0, tmp_path / "suites.jsonl")
    assert datos["huella"] is None and datos["arbol_cambiado_durante_la_suite"] and not datos["verde"]


def test_pg17_omitido_no_es_completa(monkeypatch, tmp_path):
    registro = _registro(monkeypatch, inicio=ARBOL, fin=ARBOL)
    stats = {"passed": [_reporte("b")], "skipped": [_reporte("a", ["pg17_local"])]}
    datos = registro.escribir(_sesion(stats), 0, tmp_path / "suites.jsonl")
    assert (datos["alcance"], datos["pg17_omitidos"]) == ("parcial", 1)


def test_un_fichero_concreto_es_parcial(monkeypatch, tmp_path):
    registro = _registro(monkeypatch, inicio=ARBOL, fin=ARBOL)
    stats = {"passed": [_reporte("a", ["pg17_local"]), _reporte("b")]}
    datos = registro.escribir(_sesion(stats, args=("tests/test_x.py",)), 0, tmp_path / "suites.jsonl")
    assert datos["alcance"] == "parcial"


def test_un_fallo_al_registrar_no_altera_la_suite(monkeypatch, tmp_path, capsys):
    registro = _registro(monkeypatch, inicio=ARBOL, fin=ARBOL)
    monkeypatch.setattr(registro, "linea", lambda s, e: (_ for _ in ()).throw(OSError("disco")))
    assert registro.escribir(_sesion({}), 0, tmp_path / "suites.jsonl") is None
    assert "no se pudo registrar" in capsys.readouterr().out


def test_el_registro_real_va_a_logs_agentes_del_proyecto():
    assert rs.ruta_registro() == Path(rs.ROOT) / "logs" / "agentes" / "suites.jsonl"
