"""Puerta de tareas de los preflights de despliegue y de las series: la tarea de Alliance es obligatoria.

Encargo de Pio (2026-11-15): la puerta solo exigia «Importar facturas» y «Sincronización»; la tarea de las 22:15
(«ControlFarmacias - Automatizacion Alliance», noche_automatica) tambien debe existir. La constante es unica
(``auditoria_readonly.TAREAS_ESPERADAS``) y la heredan los preflights (2BD-D en adelante) y las series 2BJ/2BP.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
import auditoria_readonly as ar  # noqa: E402

ALLIANCE = "ControlFarmacias - Automatizacion Alliance"
AHORA = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def _tarea(nombre: str, proxima: datetime | None = None) -> dict:
    return {"nombre": nombre, "estado": "Ready", "proxima": proxima.isoformat() if proxima else None,
            "ultima": None, "resultado": 0}


def test_la_tarea_de_alliance_es_obligatoria():
    assert ALLIANCE in ar.TAREAS_ESPERADAS
    assert len(ar.TAREAS_ESPERADAS) == 3


def test_sin_la_tarea_de_alliance_la_puerta_falla():
    info = {"tareas": [_tarea(n) for n in ar.TAREAS_ESPERADAS if n != ALLIANCE]}
    assert ar._puertas_tareas(info, AHORA) == [f"TAREA_NO_ENCONTRADA: {ALLIANCE}"]


def test_con_las_tres_tareas_lejos_la_puerta_pasa():
    info = {"tareas": [_tarea(n, AHORA + timedelta(hours=3)) for n in ar.TAREAS_ESPERADAS]}
    assert ar._puertas_tareas(info, AHORA) == []


def test_alliance_a_menos_de_60_minutos_para():
    info = {"tareas": [_tarea(n, AHORA + timedelta(minutes=30 if n == ALLIANCE else 300))
                       for n in ar.TAREAS_ESPERADAS]}
    fallos = ar._puertas_tareas(info, AHORA)
    assert len(fallos) == 1 and fallos[0].startswith(f"TAREA_A_MENOS_DE_60_MIN: {ALLIANCE}")
