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


def test_alcance_completa():
    assert rs.alcance(**BASE) == "completa"


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
    {"pg17_colectados": 0},                   # completa sin ningun pg17
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
    assert (linea["alcance"], linea["verde"], linea["passed"], linea["failed"]) == ("completa", True, 2, 0)
    assert linea["huella"] == rs._estado_git().huella_de(ARBOL) and linea["base"] == "abc"
    assert linea["repositorio"] == rs._estado_git().clave_repositorio(str(rs.ROOT))


def test_linea_con_fallo_no_es_verde(monkeypatch, tmp_path):
    registro = _registro(monkeypatch, inicio=ARBOL, fin=ARBOL)
    stats = {"passed": [_reporte("a", ["pg17_local"])], "failed": [_reporte("b")]}
    datos = registro.escribir(_sesion(stats), 1, tmp_path / "suites.jsonl")
    assert (datos["failed"], datos["verde"]) == (1, False)


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
