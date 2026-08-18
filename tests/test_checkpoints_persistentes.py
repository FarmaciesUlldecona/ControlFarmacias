import json
import subprocess

import pytest

from checkpoints_persistentes import CheckpointInvalido, GestorCheckpoints
from entornos import GestorEntornos
from runs_persistentes import GestorRuns
from tareas_persistentes import GestorTareas, ModoTarea, crear_contrato


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _contexto(tmp_path):
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    entornos = GestorEntornos(tareas, tmp_path / "estado" / "locks")
    runs = GestorRuns(tareas, entornos, tmp_path / "runs")
    checkpoints = GestorCheckpoints(
        tareas, runs, tmp_path / "estado" / "checkpoints"
    )
    items = []
    for nombre in ("a", "b"):
        repo = tmp_path / nombre
        repo.mkdir()
        _git(repo, "init", "-b", "main")
        (repo / "base.txt").write_text("base\n", encoding="utf-8")
        _git(repo, "add", "base.txt")
        _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "base")
        tarea = tareas.crear_tarea(
            orden_original="fake",
            repo=str(repo),
            worktree=str(repo),
            rama="main",
            commit_inicial=_git(repo, "rev-parse", "HEAD"),
            modo=ModoTarea.READ_ONLY,
            contrato=crear_contrato(objetivo="fake", condiciones_finalizacion="revisar"),
        )
        entornos.reservar_worktree(tarea.id)
        run = runs.preparar_run(tarea.id).run
        items.append((tarea, run))
    return tareas, runs, checkpoints, items


def test_checkpoint_se_crea_y_su_json_es_atomico_legible(tmp_path):
    _, _, gestor, ((tarea, run), _) = _contexto(tmp_path)
    checkpoint = gestor.registrar_checkpoint(
        task_id=tarea.id,
        run_id=run.run_id,
        tipo="DOCUMENTO_COMPLETADO",
        payload={"documento": "a"},
        metadata={"paso": 1},
        validado=True,
    )

    datos = json.loads((gestor.directorio / f"{checkpoint.checkpoint_id}.json").read_text(encoding="utf-8"))
    assert datos["task_id"] == tarea.id
    assert datos["validado"] is True
    assert not list(gestor.directorio.glob("*.tmp"))


def test_checkpoint_persiste_y_se_recupera_con_instancia_nueva(tmp_path):
    tareas, runs, gestor, ((tarea, run), _) = _contexto(tmp_path)
    creado = gestor.registrar_checkpoint(
        task_id=tarea.id, run_id=run.run_id, tipo="PASO", payload={"n": 1}
    )

    reiniciado = GestorCheckpoints(tareas, runs, gestor.directorio)

    assert reiniciado.obtener_checkpoint(creado.checkpoint_id) == creado
    assert reiniciado.listar_checkpoints(task_id=tarea.id) == [creado]


def test_ultimo_checkpoint_usa_orden_persistido(tmp_path):
    _, _, gestor, ((tarea, run), _) = _contexto(tmp_path)
    primero = gestor.registrar_checkpoint(task_id=tarea.id, run_id=run.run_id, tipo="UNO")
    segundo = gestor.registrar_checkpoint(task_id=tarea.id, run_id=run.run_id, tipo="DOS")

    assert gestor.obtener_ultimo_checkpoint(task_id=tarea.id) == segundo
    assert primero.checkpoint_id != segundo.checkpoint_id


def test_checkpoints_de_tareas_y_runs_distintos_no_se_mezclan(tmp_path):
    _, _, gestor, ((tarea_a, run_a), (tarea_b, run_b)) = _contexto(tmp_path)
    a = gestor.registrar_checkpoint(task_id=tarea_a.id, run_id=run_a.run_id, tipo="A")
    b = gestor.registrar_checkpoint(task_id=tarea_b.id, run_id=run_b.run_id, tipo="B")

    assert gestor.listar_checkpoints(task_id=tarea_a.id, run_id=run_a.run_id) == [a]
    assert gestor.listar_checkpoints(task_id=tarea_b.id, run_id=run_b.run_id) == [b]


def test_checkpoint_rechaza_run_de_otra_tarea(tmp_path):
    _, _, gestor, ((tarea_a, _), (_, run_b)) = _contexto(tmp_path)

    with pytest.raises(CheckpointInvalido, match="no pertenece"):
        gestor.registrar_checkpoint(task_id=tarea_a.id, run_id=run_b.run_id, tipo="MAL")
