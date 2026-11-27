"""Hito SUITE: completa sin histórica, regla de reparación, histórica y barrera de despliegue.

Lógica de ``.claude/hooks/estado_git.py`` y ``barreras_agentes.py`` con registros sintéticos en ``tmp_path``
(nunca el registro real). Diseño: pruebas/auditoria_suite/DISENO.md.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HOOKS = RAIZ / ".claude" / "hooks"
sys.path.insert(0, str(HOOKS))
import barreras_agentes as barreras  # noqa: E402
import estado_git  # noqa: E402

REPO = estado_git.clave_repositorio(estado_git.DIRECTORIO_PROYECTO)
TEST_A = "tests/test_a.py"
AHORA = datetime.datetime(2026, 11, 20, 18, 0, tzinfo=datetime.timezone.utc)


def _registro(tmp_path, *lineas) -> str:
    ruta = tmp_path / "registro_de_prueba.jsonl"
    ruta.write_text("".join(json.dumps({"repositorio": REPO, **l}) + "\n" for l in lineas), encoding="utf-8")
    return str(ruta)


def _detalle(*rutas, base="b0"):
    return {"base": base, "rutas": [list(r) for r in rutas]}


def _linea(detalle, alcance, verde=True, **extra):
    return {"base": detalle["base"], "rutas": detalle["rutas"], "huella": estado_git.huella_de(detalle),
            "alcance": alcance, "verde": verde, "failed": 0 if verde else 1, "errors": 0, **extra}


def _parcial(detalle, nodeids, verde=True, args=None, **extra):
    return _linea(detalle, "parcial", verde, nodeids=nodeids, args=args or ["tests/x.py::t"], keyword="",
                  markexpr="", deselected=0, colectados=len(nodeids), ejecutados=len(nodeids), **extra)


SRC = ("src/x.py", "1" * 64)
D0 = _detalle(SRC, (TEST_A, "a" * 64))


# --------------------------------------------------------------------------- completa directa

def test_completa_directa_o_total(tmp_path):
    for alcance in ("completa", "total"):
        r = _registro(tmp_path, _linea(D0, alcance))
        assert estado_git.completa_valida(D0, r)["via"] == "directa"
    r = _registro(tmp_path, _linea(D0, "historica"))
    assert estado_git.completa_valida(D0, r) is None


# --------------------------------------------------------------------------- regla (a)

ROJA = dict(fallados=["tests/test_a.py::t1", "tests/test_b.py::t2"])


def test_regla_a_repite_solo_los_fallados(tmp_path):
    r = _registro(tmp_path, _linea(D0, "completa", False, **ROJA),
                  _parcial(D0, ["tests/test_a.py::t1", "tests/test_b.py::t2"]))
    assert estado_git.completa_valida(D0, r)["via"] == "reparacion_a"


def test_regla_a_solo_cuenta_la_primera_repeticion(tmp_path):
    r = _registro(tmp_path, _linea(D0, "completa", False, **ROJA),
                  _parcial(D0, ["tests/test_a.py::t1", "tests/test_b.py::t2"], verde=False),
                  _parcial(D0, ["tests/test_a.py::t1", "tests/test_b.py::t2"]))
    assert not (estado_git.completa_valida(D0, r) or {}).get("verde")


@pytest.mark.parametrize("fallados, ejecutados", [
    (["t::1", "t::2", "t::3", "t::4"], ["t::1", "t::2", "t::3", "t::4"]),  # más de 3
    (["t::1", "t::2"], ["t::1"]),                                          # no los repite todos
    ([], ["t::1"]),                                                        # roja sin fallados
])
def test_regla_a_no_vale(tmp_path, fallados, ejecutados):
    r = _registro(tmp_path, _linea(D0, "completa", False, fallados=fallados), _parcial(D0, ejecutados))
    assert not (estado_git.completa_valida(D0, r) or {}).get("verde")


def test_completa_verde_posterior_no_hace_falta_reparar(tmp_path):
    r = _registro(tmp_path, _linea(D0, "completa", False, **ROJA), _linea(D0, "completa"))
    assert estado_git.completa_valida(D0, r)["via"] == "directa"


# --------------------------------------------------------------------------- regla (b)

D1 = _detalle(SRC, (TEST_A, "b" * 64))  # solo cambia un módulo de test


def test_regla_b_solo_tests(tmp_path):
    r = _registro(tmp_path, _linea(D0, "completa", False, **ROJA),
                  _parcial(D1, ["tests/test_a.py::t1", "tests/test_a.py::t9", "tests/test_b.py::t2"],
                           args=["tests/test_a.py", "tests/test_b.py::t2", "--basetemp=x"]))
    assert estado_git.completa_valida(D1, r)["via"] == "reparacion_b"


@pytest.mark.parametrize("cambio", [
    ("src/x.py", "2" * 64),                                   # código
    ("tests/conftest.py", "c" * 64),                          # infraestructura (D7)
    ("tests/facturas/runtime_supabase/pg17_local.py", "c" * 64),
    ("tests/registro_suite.py", "c" * 64),
    ("tests/consultar_suite.py", "c" * 64),
    ("tests/datos/fixture.json", "c" * 64),                   # ayudante o datos: cuenta como código
    ("pytest.ini", "c" * 64),
])
def test_regla_b_no_vale_si_toca_algo_que_no_es_un_modulo_de_test(tmp_path, cambio):
    d1 = _detalle(SRC, (TEST_A, "b" * 64), cambio) if cambio[0] != "src/x.py" else _detalle(cambio, (TEST_A, "b" * 64))
    r = _registro(tmp_path, _linea(D0, "completa", False, **ROJA),
                  _parcial(d1, ["tests/test_a.py::t1", "tests/test_b.py::t2"], args=["tests/test_a.py",
                                                                                     "tests/test_b.py::t2"]))
    assert not (estado_git.completa_valida(d1, r) or {}).get("verde")


@pytest.mark.parametrize("parcial", [
    dict(args=["tests/test_b.py::t2"]),                    # no ejecuta el módulo cambiado
    dict(args=["tests/test_a.py"], keyword="t1"),          # -k
    dict(args=["tests/test_a.py"], deselected=1),
    dict(args=["tests/test_a.py"], nodeids=["tests/test_a.py::t1"]),  # le falta un fallado
])
def test_regla_b_exige_fallados_y_modulos_cambiados_enteros(tmp_path, parcial):
    base = _parcial(D1, ["tests/test_a.py::t1", "tests/test_b.py::t2"])
    base.update(parcial)
    r = _registro(tmp_path, _linea(D0, "completa", False, **ROJA), base)
    assert not (estado_git.completa_valida(D1, r) or {}).get("verde")


def test_la_reparacion_exige_la_misma_base(tmp_path):
    otra = _detalle(SRC, (TEST_A, "b" * 64), base="b1")
    r = _registro(tmp_path, _linea(D0, "completa", False, **ROJA),
                  _parcial(otra, ["tests/test_a.py::t1", "tests/test_b.py::t2"], args=["tests/test_a.py"]))
    assert not (estado_git.completa_valida(otra, r) or {}).get("verde")


# --------------------------------------------------------------------------- histórica

def test_historica_exacta_por_rutas_de_despliegue_o_modulos_historicos():
    """PERMISOS-1 (DECISIÓN DE PIO, 2026-11-27): exacta SOLO por estas rutas; en el resto, ninguna (None)."""
    for ruta in ("sql/migrations/37_x.sql", "pruebas/auditoria_37/desplegar_37.py",
                 "pruebas/auditoria_2bn_d/preflight_readonly.py", "src/facturas/runtime_supabase/puerta_git.py",
                 "src/facturas/runtime_supabase/conciliacion.py", "src/facturas/runtime_supabase/repositorios.py",
                 "tests/facturas/runtime_supabase/pg17_local.py", "tests/facturas/runtime_supabase/conftest.py",
                 "tests/facturas/runtime_supabase/test_integracion_pg17_r20.py"):
        assert estado_git.historica_exigida(["docs/a.md", ruta]) == "exacta", ruta
    for ruta in ("pruebas/auditoria_2at/x.py", "sql/otro.sql", "src/x.py", TEST_A, "tests/conftest.py",
                 ".claude/hooks/estado_git.py", "src/facturas/runtime_supabase/noche_automatica.py"):
        assert estado_git.historica_exigida(["docs/a.md", ruta]) is None, ruta


def test_modulos_historicos_se_leen_sin_importar_el_conftest():
    modulos = estado_git.modulos_historicos()
    assert "tests/facturas/runtime_supabase/test_integracion_pg17_r20.py" in modulos
    assert "tests/facturas/runtime_supabase/test_ensayo_fase4_2at.py" in modulos


def test_sin_suite_historica_legible_se_exige_exacta(tmp_path):
    assert estado_git.historica_exigida(["src/x.py"], str(tmp_path)) == "exacta"


def _hist(dias, verde=True, huella="hx"):
    return {"huella": huella, "alcance": "historica", "verde": verde,
            "ts_fin": (AHORA - datetime.timedelta(days=dias)).isoformat()}


def test_sin_historica_semanal(tmp_path):
    """PERMISOS-1: la regla de 7 días se retira; pedir otro modo que ``exacta`` es un error (fallo cerrado)."""
    with pytest.raises(ValueError):
        estado_git.historica_valida("h", "semanal", _registro(tmp_path, _hist(1)), ahora=AHORA)
    assert not hasattr(estado_git, "DIAS_HISTORICA")


def test_historica_exacta_sobre_la_huella(tmp_path):
    r = _registro(tmp_path, _hist(0, huella="otra"), {"huella": "h", "alcance": "total", "verde": True})
    assert estado_git.historica_valida("h", "exacta", r)["alcance"] == "total"
    assert estado_git.historica_valida("z", "exacta", r) is None


# --------------------------------------------------------------------------- barrera de commit

def _pass(tmp_path, huella):
    ruta = tmp_path / "revisiones_de_prueba.jsonl"
    ruta.write_text(json.dumps({"agent_type": estado_git.AGENTE_REVISOR, "veredicto": "PASS",
                                "huella_cambios": huella}) + "\n", encoding="utf-8")
    return str(ruta)


def test_barrera_de_commit_con_reparacion_b_sin_historica(tmp_path):
    """PERMISOS-1: src/x.py y un test no exigen histórica; basta la completa (aquí, por reparación)."""
    rutas = [r[0] for r in D1["rutas"]]
    uso = _pass(tmp_path, estado_git.huella_de(D1))
    roja = _linea(D0, "completa", False, **ROJA)
    reparacion = _parcial(D1, ["tests/test_a.py::t1", "tests/test_b.py::t2"], args=["tests/test_a.py",
                                                                                   "tests/test_b.py::t2"])
    decision = barreras.barrera_commit(None, uso, rutas, _registro(tmp_path, roja, reparacion), detalle=D1,
                                       ahora=AHORA)
    assert decision.codigo == 0
    sin_reparar = _registro(tmp_path, _hist(1), roja)
    assert barreras.barrera_commit(None, uso, rutas, sin_reparar, detalle=D1, ahora=AHORA).motivo == \
        "commit_sin_suite"  # la roja es de otro árbol y no hay reparación


def test_barrera_de_commit_que_toca_la_conciliacion_exige_la_historica_exacta(tmp_path):
    d = _detalle(("src/facturas/runtime_supabase/conciliacion.py", "c" * 64), (TEST_A, "a" * 64))
    rutas = [r[0] for r in d["rutas"]]
    uso = _pass(tmp_path, estado_git.huella_de(d))
    completa = _linea(d, "completa")
    assert barreras.barrera_commit(None, uso, rutas, _registro(tmp_path, completa), detalle=d,
                                   ahora=AHORA).motivo == "commit_sin_historica"
    otra_huella = _registro(tmp_path, _hist(0), completa)
    assert barreras.barrera_commit(None, uso, rutas, otra_huella, detalle=d, ahora=AHORA).motivo == \
        "commit_sin_historica"
    roja = _registro(tmp_path, completa, _linea(d, "historica", False, **ROJA))
    assert barreras.barrera_commit(None, uso, rutas, roja, detalle=d, ahora=AHORA).motivo == \
        "commit_historica_roja"
    bien = _registro(tmp_path, completa, _linea(d, "historica"))
    assert barreras.barrera_commit(None, uso, rutas, bien, detalle=d, ahora=AHORA).codigo == 0


def test_commit_que_toca_un_despliegue_exige_la_historica_exacta(tmp_path):
    d = _detalle(("pruebas/auditoria_37/desplegar_37.py", "e" * 64))
    uso = _pass(tmp_path, estado_git.huella_de(d))
    otra_huella = _registro(tmp_path, _hist(1), _linea(d, "completa"))
    assert barreras.barrera_commit(None, uso, [d["rutas"][0][0]], otra_huella, detalle=d,
                                   ahora=AHORA).motivo == "commit_sin_historica"
    exacta = _registro(tmp_path, _linea(d, "completa"), _linea(d, "historica"))
    assert barreras.barrera_commit(None, uso, [d["rutas"][0][0]], exacta, detalle=d, ahora=AHORA).codigo == 0


def test_suites_para_commit(tmp_path):
    rutas = [r[0] for r in D1["rutas"]]
    reparacion = _parcial(D1, ["tests/test_a.py::t1", "tests/test_b.py::t2"], args=["tests/test_a.py",
                                                                                   "tests/test_b.py::t2"])
    r = _registro(tmp_path, _linea(D0, "completa", False, **ROJA), reparacion)
    estado = estado_git.suites_para_commit(rutas, r, detalle=D1, ahora=AHORA)
    assert (estado["suite"]["via"], estado["historica_modo"], estado["historica"], estado["ok"]) == \
        ("reparacion_b", None, None, True)
    docs = _detalle(("docs/a.md", "d" * 64))
    r = _registro(tmp_path, _linea(docs, "rapida"))
    assert estado_git.suites_para_commit(["docs/a.md"], r, detalle=docs)["ok"] is True


# --------------------------------------------------------------------------- barrera de despliegue

@pytest.mark.parametrize("comando, es", [
    ("./.venv/Scripts/python.exe -B pruebas/auditoria_r20/desplegar_36.py 785d70b ffe4 out.json", True),
    (".venv\\Scripts\\python.exe pruebas\\auditoria_37\\desplegar_37.py a b c", True),
    ("python -m pruebas.auditoria_37.desplegar_37", True),
    ("cat pruebas/auditoria_r20/desplegar_36.py", False),
    ("git add pruebas/auditoria_37/desplegar_37.py", False),
    ("./.venv/Scripts/python.exe -m pytest tests/ -k desplegar_36", False),
    ("python -B pruebas/auditoria_2at/auditoria_readonly.py preflight x", False),
])
def test_deteccion_de_despliegues(comando, es):
    assert estado_git.es_despliegue(comando) is es


def test_barrera_de_despliegue(tmp_path):
    assert barreras.barrera_despliegue("h", _registro(tmp_path)).motivo == "despliegue_sin_historica"
    roja = _registro(tmp_path, {"huella": "h", "alcance": "historica", "verde": False})
    assert barreras.barrera_despliegue("h", roja).motivo == "despliegue_sin_historica"
    otra = _registro(tmp_path, {"huella": "otra", "alcance": "historica", "verde": True})
    assert barreras.barrera_despliegue("h", otra).motivo == "despliegue_sin_historica"
    for alcance in ("historica", "total"):
        verde = _registro(tmp_path, {"huella": "h", "alcance": alcance, "verde": True})
        assert barreras.barrera_despliegue("h", verde).codigo == 0


# --------------------------------------------------------------------------- reparto (conftest de runtime_supabase)

def _conftest_rs():
    spec = importlib.util.spec_from_file_location(
        "conftest_rs_suite", RAIZ / "tests" / "facturas" / "runtime_supabase" / "conftest.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(RAIZ / "tests" / "facturas" / "runtime_supabase"))
    spec.loader.exec_module(modulo)
    return modulo


def test_marca_historica_y_familias():
    c = _conftest_rs()
    assert c.es_historico("test_ensayo_fase4_2at.py", "test_lo_que_sea[x]")
    assert c.es_historico("test_integracion_pg17_r20.py", "test_rollback_36_devuelve_exactamente_el_esquema_35")
    assert not c.es_historico("test_integracion_pg17_r20.py", "test_r20_concilia")
    assert c.familia("test_integracion_pg17_r20.py").startswith("familia_")
    assert estado_git.modulos_historicos() == {f"tests/facturas/runtime_supabase/{m}" for m in c.SUITE_HISTORICA}
