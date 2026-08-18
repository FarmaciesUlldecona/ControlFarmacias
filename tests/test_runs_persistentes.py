import json
import subprocess
from uuid import UUID, uuid4

import pytest

import orquestador
from entornos import GestorEntornos
from runs_persistentes import (
    EstadoInternoRun,
    EstadoRunInvalido,
    GestorRuns,
    traducir_estado_historico,
)
from tareas_persistentes import EstadoTarea, GestorTareas, ModoTarea, crear_contrato


def _git(repo, *args):
    resultado = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return resultado.stdout.strip()


def _repo(tmp_path, nombre="repo"):
    repo = tmp_path / nombre
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(
        repo,
        "-c",
        "user.name=Prueba local",
        "-c",
        "user.email=prueba@example.invalid",
        "commit",
        "-m",
        "Base",
    )
    return repo, _git(repo, "rev-parse", "HEAD")


def _crear_tarea(gestor, repo, head, modo=ModoTarea.READ_ONLY):
    contrato = crear_contrato(
        objetivo="Ejecutar ciclo simulado",
        rutas_permitidas=["permitido/**"] if modo is ModoTarea.WORKSPACE_WRITE else [],
        rutas_protegidas=[".env"],
        condiciones_finalizacion="Resultado validado",
    )
    return gestor.crear_tarea(
        orden_original="Ejecuta sin Codex real",
        repo=str(repo),
        worktree=str(repo),
        rama="main",
        commit_inicial=head,
        modo=modo,
        contrato=contrato,
    )


def _contexto(tmp_path, nombre="repo", modo=ModoTarea.READ_ONLY):
    repo, head = _repo(tmp_path, nombre)
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    entornos = GestorEntornos(tareas, tmp_path / "estado" / "locks")
    runs = GestorRuns(tareas, entornos, tmp_path / "runs")
    tarea = _crear_tarea(tareas, repo, head, modo)
    entornos.reservar_worktree(tarea.id)
    return repo, tareas, entornos, runs, tarea


def _preparar_iniciar(runs, task_id):
    preparacion = runs.preparar_run(task_id)
    assert preparacion.exito
    return runs.iniciar_run(preparacion.run.run_id)


def test_crear_run_persistente_con_task_entorno_e_intento(tmp_path):
    repo, tareas, entornos, runs, tarea = _contexto(tmp_path)

    preparacion = runs.preparar_run(tarea.id)
    run = preparacion.run

    assert preparacion.exito
    assert run.task_id == tarea.id
    assert run.numero_intento == 1
    assert run.entorno["worktree"] == str(repo)
    assert str(UUID(entornos.session_id)) == entornos.session_id
    assert run.entorno["session_id"] == entornos.session_id
    assert run.branch_observada == "main"
    assert run.head_observado == tarea.commit_inicial
    metadata = json.loads(
        (tmp_path / "runs" / run.directorio_run.split("\\")[-1] / "run.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["task_id"] == tarea.id
    assert tareas.cargar(tarea.id).historial[-1].tipo == "RUN_CREATED"


def test_run_id_unico_listado_ultimo_y_contador(tmp_path):
    _, _, _, runs, tarea = _contexto(tmp_path)
    primero = _preparar_iniciar(runs, tarea.id)
    runs.registrar_resultado(
        primero.run_id, EstadoInternoRun.AUTO_CONTINUE, resumen="continúa"
    )
    segundo = runs.preparar_run(tarea.id).run

    assert primero.run_id != segundo.run_id
    assert segundo.numero_intento == 2
    assert [run.run_id for run in runs.listar_runs_tarea(tarea.id)] == [
        primero.run_id,
        segundo.run_id,
    ]
    assert runs.obtener_ultimo_run(tarea.id).run_id == segundo.run_id
    assert runs.contar_ciclos(tarea.id) == 2


def test_recupera_runs_con_instancia_nueva(tmp_path):
    _, tareas, entornos, runs, tarea = _contexto(tmp_path)
    creado = runs.preparar_run(tarea.id).run

    reiniciado = GestorRuns(tareas, entornos, tmp_path / "runs")

    assert reiniciado.obtener_run(creado.run_id) == creado
    assert reiniciado.listar_runs_tarea(tarea.id) == [creado]


def test_runs_de_tareas_distintas_no_se_mezclan(tmp_path):
    repo_a, head_a = _repo(tmp_path, "repo_a")
    repo_b, head_b = _repo(tmp_path, "repo_b")
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    entornos = GestorEntornos(tareas, tmp_path / "estado" / "locks")
    runs = GestorRuns(tareas, entornos, tmp_path / "runs")
    tarea_a = _crear_tarea(tareas, repo_a, head_a)
    tarea_b = _crear_tarea(tareas, repo_b, head_b)
    entornos.reservar_worktree(tarea_a.id)
    entornos.reservar_worktree(tarea_b.id)

    run_a = runs.preparar_run(tarea_a.id).run
    run_b = runs.preparar_run(tarea_b.id).run

    assert [item.run_id for item in runs.listar_runs_tarea(tarea_a.id)] == [run_a.run_id]
    assert [item.run_id for item in runs.listar_runs_tarea(tarea_b.id)] == [run_b.run_id]


def test_rechaza_tarea_inexistente_sin_crear_run(tmp_path):
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    entornos = GestorEntornos(tareas, tmp_path / "estado" / "locks")
    runs = GestorRuns(tareas, entornos, tmp_path / "runs")

    resultado = runs.preparar_run(str(uuid4()))

    assert not resultado.exito
    assert resultado.run is None
    assert resultado.errores == ("tarea inexistente",)
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("terminal", [EstadoTarea.FINALIZADA, EstadoTarea.CANCELADA])
def test_rechaza_tareas_terminales_sin_crear_run(tmp_path, terminal):
    _, tareas, _, runs, tarea = _contexto(tmp_path)
    if terminal is EstadoTarea.FINALIZADA:
        tareas.actualizar_estado(tarea.id, EstadoTarea.TRABAJANDO)
    tareas.actualizar_estado(tarea.id, terminal)

    resultado = runs.preparar_run(tarea.id)

    assert not resultado.exito
    assert terminal.value in resultado.errores[0]
    assert not (tmp_path / "runs").exists()


def test_rechaza_tarea_sin_lock(tmp_path):
    repo, head = _repo(tmp_path)
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    entornos = GestorEntornos(tareas, tmp_path / "estado" / "locks")
    runs = GestorRuns(tareas, entornos, tmp_path / "runs")
    tarea = _crear_tarea(tareas, repo, head)

    resultado = runs.preparar_run(tarea.id)

    assert not resultado.exito
    assert resultado.errores == ("worktree sin lock",)
    assert tareas.cargar(tarea.id).historial[-1].tipo == "RUN_PRECONDITION_FAILED"
    assert not (tmp_path / "runs").exists()


def test_rechaza_lock_propiedad_de_otra_tarea(tmp_path):
    repo, tareas, _, runs, propietaria = _contexto(tmp_path)
    ajena = _crear_tarea(tareas, repo, propietaria.commit_inicial)

    resultado = runs.preparar_run(ajena.id)

    assert not resultado.exito
    assert "otra tarea" in resultado.errores[0]
    assert not (tmp_path / "runs").exists()


def test_rechaza_repositorio_invalido_sin_crear_run(tmp_path):
    repo, _, _, runs, tarea = _contexto(tmp_path)
    (repo / ".git").rename(repo / ".git_oculto")

    resultado = runs.preparar_run(tarea.id)

    assert not resultado.exito
    assert any("Git inválido" in error for error in resultado.errores)
    assert not (tmp_path / "runs").exists()


def test_rechaza_branch_distinta(tmp_path):
    repo, _, _, runs, tarea = _contexto(tmp_path)
    _git(repo, "branch", "otra")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/otra")

    resultado = runs.preparar_run(tarea.id)

    assert not resultado.exito
    assert any("rama distinta" in error for error in resultado.errores)
    assert not (tmp_path / "runs").exists()


def test_rechaza_head_distinto(tmp_path):
    repo, _, _, runs, tarea = _contexto(tmp_path)
    (repo / "nuevo.txt").write_text("nuevo\n", encoding="utf-8")
    _git(repo, "add", "nuevo.txt")
    _git(
        repo,
        "-c",
        "user.name=Prueba local",
        "-c",
        "user.email=prueba@example.invalid",
        "commit",
        "-m",
        "Otro HEAD",
    )

    resultado = runs.preparar_run(tarea.id)

    assert not resultado.exito
    assert any("HEAD distinto" in error for error in resultado.errores)
    assert not (tmp_path / "runs").exists()


def test_eventos_started_completed_y_resultado_persistente(tmp_path):
    _, tareas, _, runs, tarea = _contexto(tmp_path)
    run = _preparar_iniciar(runs, tarea.id)

    resultado = runs.registrar_resultado(
        run.run_id,
        EstadoInternoRun.AUTO_CONTINUE,
        resumen="Paso correcto",
        siguiente_accion="Siguiente paso",
    )
    recuperado = runs.obtener_run(run.run_id)
    tipos = [evento.tipo for evento in tareas.cargar(tarea.id).historial]

    assert resultado.estado_v02_propuesto is EstadoTarea.TRABAJANDO
    assert recuperado.resultado == resultado
    assert "RUN_STARTED" in tipos
    assert tipos[-1] == "RUN_COMPLETED"


def test_pausa_registra_evento_y_actualiza_estado_visible(tmp_path):
    _, tareas, _, runs, tarea = _contexto(tmp_path)
    run = _preparar_iniciar(runs, tarea.id)

    resultado = runs.registrar_resultado(
        run.run_id,
        EstadoInternoRun.REQUIERE_OK_PIO,
        resumen="Falta decisión",
    )

    assert resultado.requiere_decision
    assert resultado.estado_v02_propuesto is EstadoTarea.ESPERANDO_DECISION
    tarea_actual = tareas.cargar(tarea.id)
    assert tarea_actual.estado is EstadoTarea.ESPERANDO_DECISION
    assert any(evento.tipo == "RUN_PAUSED" for evento in tarea_actual.historial)


def test_traduccion_explicita_de_estados_historicos():
    assert traducir_estado_historico("AUTO_CONTINUE") == (
        EstadoTarea.TRABAJANDO,
        False,
    )
    assert traducir_estado_historico("REQUIERE_OK_PIO") == (
        EstadoTarea.ESPERANDO_DECISION,
        True,
    )
    assert traducir_estado_historico("PAUSA_PIO", causa_pausa="revisión humana") == (
        EstadoTarea.ESPERANDO_DECISION,
        True,
    )
    assert traducir_estado_historico("PAUSA_PIO", causa_pausa="barrera dura") == (
        EstadoTarea.BLOQUEADA,
        True,
    )


def test_finalizado_no_finaliza_tarea_automaticamente(tmp_path):
    _, tareas, _, runs, tarea = _contexto(tmp_path)
    run = _preparar_iniciar(runs, tarea.id)

    resultado = runs.registrar_resultado(
        run.run_id,
        EstadoInternoRun.FINALIZADO,
        resumen="Motor considera terminado",
        condiciones_funcionales_validadas=True,
    )

    assert resultado.estado_v02_propuesto is EstadoTarea.FINALIZADA
    assert tareas.cargar(tarea.id).estado is EstadoTarea.TRABAJANDO


def test_resume_conserva_task_id_e_incrementa_ciclo(tmp_path):
    _, tareas, _, runs, tarea = _contexto(tmp_path)
    primero = _preparar_iniciar(runs, tarea.id)
    runs.registrar_resultado(
        primero.run_id,
        EstadoInternoRun.REQUIERE_OK_PIO,
        resumen="Decisión necesaria",
    )

    preparacion = runs.preparar_resume(tarea.id, primero.run_id, "Continúa A")
    segundo = preparacion.run

    assert preparacion.exito
    assert segundo.task_id == tarea.id
    assert segundo.resume_de == primero.run_id
    assert segundo.decision_resume == "Continúa A"
    assert segundo.numero_intento == 2
    assert runs.contar_ciclos(tarea.id) == 2
    assert tareas.cargar(tarea.id).historial[-1].tipo == "RUN_RESUMED"


def test_resume_rechaza_run_no_pausado(tmp_path):
    _, _, _, runs, tarea = _contexto(tmp_path)
    primero = runs.preparar_run(tarea.id).run

    resultado = runs.preparar_resume(tarea.id, primero.run_id, "Continúa")

    assert not resultado.exito
    assert "no está pausado" in resultado.errores[0]
    assert runs.contar_ciclos(tarea.id) == 1


def test_fallo_registra_run_failed_y_bloquea(tmp_path):
    _, tareas, _, runs, tarea = _contexto(tmp_path)
    run = _preparar_iniciar(runs, tarea.id)

    resultado = runs.registrar_resultado(
        run.run_id,
        EstadoInternoRun.FALLIDO,
        resumen="Fallo simulado",
        errores=["error ficticio"],
    )

    assert resultado.estado_v02_propuesto is EstadoTarea.BLOQUEADA
    tarea_actual = tareas.cargar(tarea.id)
    assert tarea_actual.estado is EstadoTarea.BLOQUEADA
    assert any(evento.tipo == "RUN_FAILED" for evento in tarea_actual.historial)


def test_mismatch_posterior_bloquea_sin_finalizar_automaticamente(tmp_path):
    repo, tareas, _, runs, tarea = _contexto(tmp_path)
    run = _preparar_iniciar(runs, tarea.id)
    _git(repo, "branch", "otra")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/otra")

    resultado = runs.registrar_resultado(
        run.run_id,
        EstadoInternoRun.FINALIZADO,
        resumen="Final aparente con entorno alterado",
        condiciones_funcionales_validadas=True,
    )

    assert resultado.estado_v02_propuesto is EstadoTarea.BLOQUEADA
    assert any("rama distinta" in error for error in resultado.errores)
    assert tareas.cargar(tarea.id).estado is EstadoTarea.BLOQUEADA


def test_adaptador_historico_no_invoca_codex_real(tmp_path, monkeypatch):
    _, _, _, runs, tarea = _contexto(tmp_path)
    run = _preparar_iniciar(runs, tarea.id)

    def prohibido(*args, **kwargs):
        raise AssertionError("Codex real no debe ejecutarse")

    monkeypatch.setattr(orquestador, "invocar_codex", prohibido)
    resultado = runs.registrar_resultado_historico(
        run.run_id,
        "AUTO_CONTINUE",
        {
            "siguiente_instruccion": "Paso simulado",
            "ultima_decision_supervisor": {"motivo": "Todo correcto"},
        },
    )

    assert resultado.resumen == "Todo correcto"
    assert resultado.metadata["state_historico"]["siguiente_instruccion"] == "Paso simulado"


def test_no_permite_iniciar_dos_veces(tmp_path):
    _, _, _, runs, tarea = _contexto(tmp_path)
    run = _preparar_iniciar(runs, tarea.id)

    with pytest.raises(EstadoRunInvalido):
        runs.iniciar_run(run.run_id)
