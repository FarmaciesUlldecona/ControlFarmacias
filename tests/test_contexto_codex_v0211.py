from dataclasses import replace
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from contexto_codex import ampliar_contexto, crear_plan_contexto
from ejecucion_v02 import EjecutorCicloReal
from orquestador import preparar_contexto_codex


def _candidatos(cantidad=20):
    return [
        {"ruta": f"modulo_{indice}.py", "motivo": "DEPENDENCIA_DIRECTA"}
        for indice in range(cantidad)
    ]


def test_politica_contexto_es_distinta_para_light_standard_y_heavy():
    planes = {
        nivel: crear_plan_contexto(
            task_id="task-1",
            nivel_recurso=nivel,
            objetivo="cambio acotado",
            archivos_candidatos=_candidatos(),
        )
        for nivel in ("CODEX_LIGHT", "CODEX_STANDARD", "CODEX_HEAVY")
    }

    assert len(planes["CODEX_LIGHT"].archivos) == 3
    assert len(planes["CODEX_STANDARD"].archivos) == 8
    assert len(planes["CODEX_HEAVY"].archivos) == 16
    assert len(planes["CODEX_LIGHT"].archivos_omitidos) == 17
    assert "tokens" not in planes["CODEX_LIGHT"].metricas()


def test_ampliacion_es_incremental_y_no_repite_contexto_base():
    base = crear_plan_contexto(
        task_id="task-1",
        nivel_recurso="CODEX_STANDARD",
        objetivo="resolver fallo",
        archivos_candidatos=["fachada_v02.py"],
    )

    ampliado = ampliar_contexto(
        base,
        task_id="task-1",
        motivo="ERROR_RETRY_CONCRETO",
        fragmentos=[{
            "ruta": "reintentos_persistentes.py",
            "motivo": "TRAZA_ERROR",
            "linea_inicio": 300,
            "linea_fin": 380,
        }],
        errores_concretos=["AssertionError en retry"],
    )

    assert ampliado.contexto_base == base.contexto_base
    assert len(ampliado.ampliaciones_contexto) == 1
    assert ampliado.archivos == ("fachada_v02.py", "reintentos_persistentes.py")
    assert ampliado.metricas()["contexto_ampliado"] is True
    assert ampliado.metricas()["motivo_ampliacion"] == "ERROR_RETRY_CONCRETO"


def test_contexto_no_puede_mezclarse_entre_tareas():
    plan = crear_plan_contexto(
        task_id="task-a", nivel_recurso="CODEX_LIGHT", objetivo="a"
    )

    with pytest.raises(ValueError, match="mezclar contexto"):
        ampliar_contexto(plan, task_id="task-b", motivo="incorrecto")


def test_retry_reutiliza_contexto_local_sin_fingir_sesion_cli():
    previo = crear_plan_contexto(
        task_id="task-1",
        nivel_recurso="CODEX_STANDARD",
        objetivo="corregir módulo",
        archivos_candidatos=["modulo.py"],
        session_id="sesion-anterior",
    )
    tarea = {
        "id": "task-1",
        "objetivo": "corregir módulo",
        "nivel_recurso": "CODEX_HEAVY",
        "retry": True,
        "contexto_retry": {"checkpoint_id": "cp-1", "estrategia": "RETRY_FULL_RUN"},
        "session_id": "sesion-actual",
        "contexto_codex_previo": previo.a_dict(),
    }

    recuperado = preparar_contexto_codex(tarea)

    assert recuperado.archivos == previo.archivos
    assert recuperado.nivel_recurso == "CODEX_HEAVY"
    assert recuperado.retry is True
    assert recuperado.contexto_retry["checkpoint_id"] == "cp-1"
    assert recuperado.session_id == "sesion-actual"
    assert recuperado.sesion_reutilizada is False
    assert recuperado.soporte_reanudacion_cli is False


def test_modelo_rechaza_afirmar_reutilizacion_sin_soporte_cli():
    plan = crear_plan_contexto(
        task_id="task-1", nivel_recurso="CODEX_LIGHT", objetivo="x"
    )
    with pytest.raises(ValueError, match="fingir"):
        replace(plan, sesion_reutilizada=True)


def test_retry_carga_contexto_solo_del_run_origen_de_la_misma_tarea(tmp_path):
    task_id = str(uuid4())
    run_origen = str(uuid4())
    runs = tmp_path / "runs"
    origen = runs / f"20260825_{run_origen}"
    actual = runs / f"20260825_{uuid4()}"
    origen.mkdir(parents=True)
    actual.mkdir(parents=True)
    plan = crear_plan_contexto(
        task_id=task_id,
        nivel_recurso="CODEX_STANDARD",
        objetivo="reintentar",
        archivos_candidatos=["modulo.py"],
    )
    (origen / "run.json").write_text(
        json.dumps({"task_id": task_id}), encoding="utf-8"
    )
    (origen / "state.json").write_text(
        json.dumps({"contexto_codex": plan.a_dict()}), encoding="utf-8"
    )
    run = SimpleNamespace(
        retry_de=run_origen,
        task_id=task_id,
        directorio_run=str(actual),
    )

    recuperado = EjecutorCicloReal._contexto_codex_previo(run)

    assert recuperado["task_id"] == task_id
    (origen / "run.json").write_text(
        json.dumps({"task_id": str(uuid4())}), encoding="utf-8"
    )
    assert EjecutorCicloReal._contexto_codex_previo(run) is None
