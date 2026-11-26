"""C7 (H7, DISENO §5.2; orden de Pio del 2026-11-22): «Cashflow no en ejecucion» en la puerta de la noche y de los
preflights.

La tarea «ControlFarmacias - Importar Cashflow» (23:45) no es obligatoria ni previa: puede no existir, y su resultado
(un Excel con ERROR) no para las facturas. Solo se exige que no este en ejecucion. Puertas:
- la noche (``noche_automatica.puertas_tareas``; ``_tareas_productivas`` la lee solo si existe);
- los preflights 2BD-D en adelante y las series 2BJ/2BP (``auditoria_2bd_d/preflight_readonly``, que heredan);
- el preflight 2AT (``auditoria_readonly``), que ya la lee por el comodin '*ControlFarmacias*'.
Sin base de datos, sin Task Scheduler real (se captura el script de PowerShell).
"""
from __future__ import annotations

import base64
import datetime as dt
import importlib.util
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.cashflow import importar_cashflow as ic
from src.facturas.runtime_supabase import noche_automatica as na

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
import auditoria_readonly as ar  # noqa: E402

_spec = importlib.util.spec_from_file_location(f"preflight_2bdd_{uuid.uuid4().hex[:6]}",
                                               ROOT / "pruebas/auditoria_2bd_d/preflight_readonly.py")
bdd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bdd)

CASHFLOW = "ControlFarmacias - Importar Cashflow"
AHORA = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone.utc)
FECHA_NOCHE = dt.datetime.fromisoformat("2026-11-13T20:30:30+00:00").astimezone().date()


def test_el_nombre_de_la_tarea_es_el_mismo_en_todas_partes():
    assert na.TAREA_CASHFLOW == ic.TAREA_CASHFLOW == ar.TAREA_CASHFLOW == bdd.TAREA_CASHFLOW == CASHFLOW
    assert CASHFLOW not in na.TAREAS_PREVIAS and CASHFLOW not in ar.TAREAS_ESPERADAS
    assert "ControlFarmacias - Importar Cashflow" in (ROOT / "ejecutar_importacion_cashflow.bat").read_text(
        encoding="utf-8")


# --------------------------------------------------------------------------- noche


def _noche(cashflow: dict | None = None) -> dict:
    tareas = [{"nombre": n, "ultima": "2026-11-13T20:30:30.0000000Z", "resultado": 0} for n in na.TAREAS_PREVIAS]
    if cashflow is not None:
        tareas.append({"nombre": CASHFLOW, **cashflow})
    return {"tareas": tareas}


@pytest.mark.parametrize("cashflow", [
    None,  # la tarea no existe todavia
    {"estado": "Ready", "ultima": None, "resultado": 267011},  # nunca ejecutada
    {"estado": "Ready", "ultima": "2026-11-01T22:45:00.0000000Z", "resultado": 2},  # ERROR de Excel, otro dia
    {"estado": "Disabled", "ultima": "2026-11-12T22:45:00.0000000Z", "resultado": 0},
])
def test_noche_cashflow_no_obligatoria_ni_previa(cashflow):
    assert na.puertas_tareas(_noche(cashflow), FECHA_NOCHE) == []


@pytest.mark.parametrize("cashflow", [
    {"estado": "Running", "ultima": "2026-11-13T22:45:00.0000000Z", "resultado": 0},
    {"estado": "Ready", "ultima": "2026-11-13T22:45:00.0000000Z", "resultado": na.RESULTADO_EN_EJECUCION},
])
def test_noche_para_si_cashflow_esta_en_ejecucion(cashflow):
    assert na.puertas_tareas(_noche(cashflow), FECHA_NOCHE) == [f"TAREA_EN_EJECUCION:{CASHFLOW}"]


def _capturar(monkeypatch, modulo, salida: list[dict]) -> list[str]:
    scripts: list[str] = []

    def falso(argumentos, **_kw):
        scripts.append(base64.b64decode(argumentos[argumentos.index("-EncodedCommand") + 1]).decode("utf-16-le"))
        return SimpleNamespace(returncode=0, stdout=json.dumps(salida).encode("utf-8"), stderr=b"")
    monkeypatch.setattr(modulo.subprocess, "run", falso)
    return scripts


def test_la_noche_lee_la_tarea_de_cashflow_solo_si_existe(monkeypatch):
    scripts = _capturar(monkeypatch, na, [{"nombre": CASHFLOW, "estado": "Running", "resultado": 0}])
    assert na._tareas_productivas() == {"tareas": [{"nombre": CASHFLOW, "estado": "Running", "resultado": 0}]}
    [script] = scripts
    assert f"Get-ScheduledTask -TaskName '{CASHFLOW}' -ErrorAction SilentlyContinue" in script
    assert "if ($c)" in script and "estado = [string]$c.State" in script
    # Las previas siguen siendo obligatorias (-ErrorAction Stop).
    assert "Get-ScheduledTaskInfo -TaskName $n -ErrorAction Stop" in script


# --------------------------------------------------------------------------- preflights 2BD-D y series


def _preflight(cashflow: dict | None = None, proxima_cashflow: dt.datetime | None = None) -> dict:
    tareas = [{"nombre": n, "estado": "Ready", "proxima": (AHORA + dt.timedelta(hours=8)).isoformat(),
               "ultima": None, "resultado": 0} for n in ar.TAREAS_ESPERADAS]
    if cashflow is not None:
        tareas.append({"nombre": CASHFLOW, "proxima": (proxima_cashflow or AHORA + dt.timedelta(hours=11)).isoformat(),
                       "ultima": None, **cashflow})
    return {"tareas": tareas}


@pytest.mark.parametrize("modulo", [bdd, ar], ids=["2bd_d", "2at"])
def test_preflights_sin_cashflow_o_parada_pasan(modulo):
    assert modulo._puertas_tareas(_preflight(), AHORA) == []
    assert modulo._puertas_tareas(_preflight({"estado": "Ready", "resultado": 2}), AHORA) == []


@pytest.mark.parametrize("modulo", [bdd, ar], ids=["2bd_d", "2at"])
def test_preflights_paran_si_cashflow_esta_en_ejecucion(modulo):
    fallos = modulo._puertas_tareas(_preflight({"estado": "Running", "resultado": 0}), AHORA)
    assert fallos == [f"TAREA_EN_EJECUCION: {CASHFLOW}"]


def test_preflight_2bd_d_para_con_el_codigo_de_ejecucion():
    fallos = bdd._puertas_tareas(_preflight({"estado": "Ready", "resultado": bdd.RESULTADO_EN_EJECUCION}), AHORA)
    assert fallos == [f"TAREA_EN_EJECUCION: {CASHFLOW}"]


@pytest.mark.parametrize("modulo", [bdd, ar], ids=["2bd_d", "2at"])
def test_preflights_cashflow_a_menos_de_60_minutos_para(modulo):
    fallos = modulo._puertas_tareas(_preflight({"estado": "Ready", "resultado": 0},
                                               AHORA + dt.timedelta(minutes=20)), AHORA)
    assert len(fallos) == 1 and fallos[0].startswith(f"TAREA_A_MENOS_DE_60_MIN: {CASHFLOW}")


def test_el_preflight_2bd_d_lee_la_tarea_de_cashflow_solo_si_existe(monkeypatch):
    scripts = _capturar(monkeypatch, bdd, [])
    assert bdd._tareas() == {"tareas": []}
    [script] = scripts
    assert f"Get-ScheduledTask -TaskName '{CASHFLOW}' -ErrorAction SilentlyContinue" in script
    assert "proxima = $(if ($ci.NextRunTime)" in script


def test_el_preflight_2at_lee_todas_las_tareas_de_controlfarmacias():
    import inspect

    assert "Get-ScheduledTask -TaskName '*ControlFarmacias*'" in inspect.getsource(ar._tareas)
