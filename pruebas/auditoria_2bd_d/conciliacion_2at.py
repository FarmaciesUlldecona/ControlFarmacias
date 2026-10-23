"""Hito 2BD-D: procedimiento de conciliacion one-shot del 2AT con tareas consultadas SOLO por
``Get-ScheduledTaskInfo`` (restriccion de Pio para este hito).

Sustituye unicamente la consulta de tareas programadas (``_tareas`` y ``_puertas_tareas``) de
``pruebas/auditoria_2at/auditoria_readonly.py`` y de ``ejecutar_una_vez.py`` por las de
``preflight_readonly.py`` del 2BD-D; el resto del procedimiento certificado no cambia. La tarea en
ejecucion se detecta por ``LastTaskResult = 267009`` (SCHED_S_TASK_RUNNING).

Uso:
  python -B pruebas/auditoria_2bd_d/conciliacion_2at.py auditoria <argumentos de auditoria_readonly.py>
  python -B pruebas/auditoria_2bd_d/conciliacion_2at.py ejecutar <argumentos de ejecutar_una_vez.py>
"""
from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR_2AT = ROOT / "pruebas/auditoria_2at"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DIR_2AT))

_spec = importlib.util.spec_from_file_location("preflight_2bdd", Path(__file__).resolve().parent / "preflight_readonly.py")
pre_2bdd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pre_2bdd)

import auditoria_readonly  # noqa: E402

auditoria_readonly._tareas = pre_2bdd._tareas
auditoria_readonly._puertas_tareas = pre_2bdd._puertas_tareas

def _auditoria(argumentos: list[str]) -> int:
    # Mismo despacho que el __main__ de auditoria_readonly.py, sobre el modulo ya parcheado.
    a = auditoria_readonly
    modo = argumentos[0]
    if modo == "preflight":
        return a.preflight(a._salida_fuera_del_repo(argumentos[1]))
    if modo == "snapshot":
        return a.snapshot(a._salida_fuera_del_repo(argumentos[1]))
    if modo == "candidato":
        return a.candidato(a._salida_fuera_del_repo(argumentos[1]),
                           Path(argumentos[2]) if len(argumentos) > 2 else None)
    if modo == "comparar":
        return a.comparar(Path(argumentos[1]), Path(argumentos[2]), argumentos[3])
    raise SystemExit("modo desconocido")


if __name__ == "__main__":
    modo, resto = sys.argv[1], sys.argv[2:]
    if modo == "auditoria":
        sys.exit(_auditoria(resto))
    if modo != "ejecutar":
        raise SystemExit("modo desconocido")
    # ejecutar_una_vez.py importa _tareas/_puertas_tareas del modulo auditoria_readonly ya cargado
    # (sys.modules), que esta parcheado.
    sys.argv = [str(DIR_2AT / "ejecutar_una_vez.py"), *resto]
    runpy.run_path(str(DIR_2AT / "ejecutar_una_vez.py"), run_name="__main__")
