"""Puerta de tareas del importador de Cashflow (orden de Pio del 2026-11-23, tras la PARADA TAREAS_NO_DETERMINABLES
de la primera ejecucion de la tarea de las 23:45, la noche del 22/11):

1. el texto del error de PowerShell se guarda en el informe (``tareas_error`` y resumen.txt), saneado: sin rutas,
   SID, correos ni cuentas, y sin las lineas que repiten el script;
2. las tareas se leen cada una por su nombre exacto (``Get-ScheduledTaskInfo -ErrorAction Stop``, como
   ``noche_automatica._tareas_productivas``), no por el comodin '*ControlFarmacias*'.
Sin base de datos ni Task Scheduler real (se captura el script de PowerShell).
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.cashflow import importar_cashflow as ic
from src.facturas.runtime_supabase import noche_automatica as na

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
import auditoria_readonly as ar  # noqa: E402

PREVIAS_OK = {"noches_en_curso": 0, "migracion_38": True}


def _salida(tareas: list[dict], returncode: int = 0, stderr: bytes = b"") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=json.dumps(tareas).encode("utf-8"), stderr=stderr)


def _capturar(monkeypatch, resultado) -> list[str]:
    scripts: list[str] = []

    def falso(argumentos, **_kw):
        scripts.append(base64.b64decode(argumentos[argumentos.index("-EncodedCommand") + 1]).decode("utf-16-le"))
        if isinstance(resultado, BaseException):
            raise resultado
        return resultado
    monkeypatch.setattr(ic.subprocess, "run", falso)
    return scripts


def _todas(**cambios) -> list[dict]:
    return [{"nombre": n, "estado": "Ready", "resultado": 0, **cambios.get(n, {})} for n in ic.TAREAS_CONSULTADAS]


# --------------------------------------------------------------------------- lectura por nombre


def test_las_tareas_consultadas_son_las_de_la_noche_y_los_preflights():
    assert set(na.TAREAS_PREVIAS) <= set(ic.TAREAS_CONSULTADAS)
    assert set(ic.TAREAS_CONSULTADAS) == set(ar.TAREAS_ESPERADAS) | {ic.TAREA_CASHFLOW}
    assert ic.RESULTADO_EN_EJECUCION == na.RESULTADO_EN_EJECUCION
    assert ic.TAREAS_CONSULTADAS[1] == "Sincronizaci\u00f3n ControlFarmacias"


def test_lee_cada_tarea_por_su_nombre_y_no_por_comodin(monkeypatch):
    scripts = _capturar(monkeypatch, _salida(_todas()))
    assert ic._tareas_productivas() == {"tareas": _todas()}
    [script] = scripts
    assert "*ControlFarmacias*" not in script and "*" not in script.replace("**", "")
    assert "Get-ScheduledTaskInfo -TaskName $n -ErrorAction Stop" in script
    assert "Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue" in script
    for nombre in ic.TAREAS_CONSULTADAS:
        assert f"'{nombre}'" in script


def test_si_falta_una_tarea_falla_cerrado(monkeypatch):
    _capturar(monkeypatch, _salida(_todas()[:-1]))
    assert ic._tareas_productivas() == {"error": "TAREAS_INCOMPLETAS"}


def test_una_sola_tarea_devuelta_como_objeto_tambien_es_incompleta(monkeypatch):
    _capturar(monkeypatch, SimpleNamespace(returncode=0, stdout=json.dumps(_todas()[0]).encode(), stderr=b""))
    assert ic._tareas_productivas() == {"error": "TAREAS_INCOMPLETAS"}


def test_salida_no_json_falla_cerrado(monkeypatch):
    _capturar(monkeypatch, SimpleNamespace(returncode=0, stdout=b"no es json", stderr=b""))
    assert ic._tareas_productivas() == {"error": "SALIDA_NO_JSON"}


def test_codigo_distinto_de_cero_devuelve_el_texto_del_error(monkeypatch):
    _capturar(monkeypatch, _salida([], returncode=1, stderr=b"Get-ScheduledTaskInfo : Acceso denegado."))
    assert ic._tareas_productivas() == {"error": "CODIGO_1: Get-ScheduledTaskInfo : Acceso denegado."}


@pytest.mark.parametrize("excepcion, esperado", [
    (OSError("no powershell"), "OSError"),
    (subprocess.TimeoutExpired("powershell.exe", 60), "TimeoutExpired"),
])
def test_excepciones_dan_su_tipo(monkeypatch, excepcion, esperado):
    _capturar(monkeypatch, excepcion)
    assert ic._tareas_productivas() == {"error": esperado}


# --------------------------------------------------------------------------- saneado del error


CLIXML = (
    '#< CLIXML\r\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
    '<S S="Error">Get-ScheduledTaskInfo : Acceso denegado a C:\\Users\\Usuari\\AppData\\x.xml para '
    'MOSTRADOR\\Usuari (S-1-5-21-1664616495-3062778491-1001) &lt;pio@ejemplo.com&gt;_x000D__x000A_</S>'
    '<S S="Error">En l\u00ednea: 1 Car\u00e1cter: 61_x000D__x000A_</S>'
    '<S S="Error">At line:1 char:61_x000D__x000A_</S>'
    '<S S="Error">+ ... ($n in @(\'ControlFarmacias - Importar facturas\')) '
    '{ $i = Get-ScheduledTaskInfo -Ta ..._x000D__x000A_</S>'
    '<S S="Error">+                                                     ~~~~~~~~~~~~_x000D__x000A_</S>'
    '<S S="Error">    + CategoryInfo          : PermissionDenied: '
    '(MSFT_TaskDynamicInfo:Root/Microsoft/...TaskDynamicInfo) [Get-ScheduledTaskInfo], CimException_x000D__x000A_</S>'
    '<S S="Error">    + FullyQualifiedErrorId : HRESULT 0x80070005,Get-ScheduledTaskInfo_x000D__x000A_</S></Objs>')


def test_sanear_clixml_quita_el_script_y_los_datos_sensibles():
    texto = ic.sanear_texto_error(CLIXML)
    assert texto.startswith("Get-ScheduledTaskInfo : Acceso denegado a <ruta> para <cuenta> (<sid>) <<correo>>")
    assert "CategoryInfo : PermissionDenied" in texto and "FullyQualifiedErrorId : HRESULT 0x80070005" in texto
    for prohibido in ("Usuari", "MOSTRADOR", "S-1-5-21", "pio@", "C:\\", "At line", "En l\u00ednea", "$i =",
                      "Importar facturas", "~~~", "_x000D_", "&lt;", "\n", "\r"):
        assert prohibido not in texto


def test_sanear_texto_plano_unc_y_limite():
    assert ic.sanear_texto_error("fallo en \\\\servidor\\recurso\\x") == "fallo en <ruta>"
    assert ic.sanear_texto_error("") == "SIN_DETALLE"
    assert ic.sanear_texto_error("At line:1 char:1\n+ $t = @(x)") == "SIN_DETALLE"
    largo = ic.sanear_texto_error("x" * 5000)
    assert len(largo) == ic.MAX_TEXTO_ERROR


# --------------------------------------------------------------------------- puerta e informe


def _entorno(tmp_path: Path, info: dict) -> ic.Entorno:
    return ic.Entorno(abrir_lectura=None, cliente=None, tareas=lambda: info, puerta_git=lambda: ("head", []),
                      carpeta_excel=tmp_path, directorio=tmp_path / "cf")


def test_la_puerta_guarda_el_error_saneado_en_el_informe(tmp_path):
    informe: dict = {}
    fallos = ic._puertas(_entorno(tmp_path, {"error": "CODIGO_1: " + CLIXML}), "NOCHE", "SIMULAR", PREVIAS_OK,
                         informe)
    assert fallos == ["TAREAS_NO_DETERMINABLES"]
    assert informe["tareas_error"].startswith("CODIGO_1: Get-ScheduledTaskInfo : Acceso denegado a <ruta>")
    assert "CLIXML" not in informe["tareas_error"] and "Usuari" not in informe["tareas_error"]


def test_el_error_saneado_llega_al_resumen(tmp_path):
    informe = {"origen": "NOCHE", "modo": "REAL", "resultado": "PARADA", "motivo": "PUERTAS",
               "puertas": ["TAREAS_NO_DETERMINABLES"], "tareas_error": ic.sanear_texto_error(CLIXML)}
    inicio = dt.datetime(2026, 11, 23, 22, 45, tzinfo=dt.timezone.utc)
    ic._escribir_informe(_entorno(tmp_path, {}), informe, inicio)
    [carpeta] = (tmp_path / "cf" / "informes").glob("*/*")
    resumen = (carpeta / "resumen.txt").read_text(encoding="utf-8")
    assert "Error de tareas: Get-ScheduledTaskInfo : Acceso denegado" in resumen and "Usuari" not in resumen
    guardado = json.loads((carpeta / "informe.json").read_text(encoding="utf-8"))
    assert guardado["tareas_error"] == informe["tareas_error"]


def test_sin_error_no_hay_campo_ni_linea(tmp_path):
    informe: dict = {}
    assert ic._puertas(_entorno(tmp_path, {"tareas": _todas()}), "NOCHE", "SIMULAR", PREVIAS_OK, informe) == []
    assert "tareas_error" not in informe


@pytest.mark.parametrize("cambio", [{"estado": "Running"}, {"estado": None, "resultado": 267009},
                                    {"estado": "Ready", "resultado": 267009}])
def test_en_ejecucion_por_estado_o_por_resultado(tmp_path, cambio):
    alliance = "ControlFarmacias - Automatizacion Alliance"
    info = {"tareas": _todas(**{alliance: cambio})}
    assert ic._puertas(_entorno(tmp_path, info), "NOCHE", "SIMULAR", PREVIAS_OK) == [f"TAREA_EN_EJECUCION:{alliance}"]


def test_la_propia_tarea_en_ejecucion_solo_se_admite_en_noche(tmp_path):
    info = {"tareas": _todas(**{ic.TAREA_CASHFLOW: {"estado": "Running", "resultado": 267009}})}
    assert ic._puertas(_entorno(tmp_path, info), "NOCHE", "SIMULAR", PREVIAS_OK) == []
    assert ic._puertas(_entorno(tmp_path, info), "MANUAL", "SIMULAR", PREVIAS_OK) == [
        f"TAREA_EN_EJECUCION:{ic.TAREA_CASHFLOW}"]
