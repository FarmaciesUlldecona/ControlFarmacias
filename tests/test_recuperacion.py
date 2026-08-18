import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

from checkpoints_persistentes import GestorCheckpoints
from decisiones_persistentes import EstadoDecision, GestorDecisiones
from ejecucion_v02 import EjecutorCicloFake, EjecutorCicloReal, ServicioEjecucionRuns
from entornos import GestorEntornos
from recuperacion import (
    AccionRecuperacion,
    ProcesoObservado,
    ServicioRecuperacion,
)
from runs_persistentes import EstadoInternoRun, GestorRuns
from tareas_persistentes import EstadoTarea, GestorTareas, ModoTarea, crear_contrato


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


class InspectorFake:
    def __init__(self, observados=None):
        self.observados = dict(observados or {})
        self.inspecciones = []

    def inspeccionar(self, pid):
        self.inspecciones.append(pid)
        return self.observados.get(pid, ProcesoObservado(pid, False))


def _contexto(tmp_path, *, modo=ModoTarea.READ_ONLY, crear=True):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "base")
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    entornos = GestorEntornos(tareas, tmp_path / "estado" / "locks")
    runs = GestorRuns(tareas, entornos, tmp_path / "runs")
    decisiones = GestorDecisiones(tareas, runs, tmp_path / "estado" / "decisiones")
    checkpoints = GestorCheckpoints(tareas, runs, tmp_path / "estado" / "checkpoints")
    tarea = None
    if crear:
        tarea = tareas.crear_tarea(
            orden_original="solo fakes",
            repo=str(repo),
            worktree=str(repo),
            rama="main",
            commit_inicial=_git(repo, "rev-parse", "HEAD"),
            modo=modo,
            contrato=crear_contrato(
                objetivo="recuperar",
                rutas_permitidas=["permitido/**"] if modo is ModoTarea.WORKSPACE_WRITE else [],
                rutas_protegidas=[".env"],
                condiciones_finalizacion="revisado",
            ),
        )
        entornos.reservar_worktree(tarea.id)
    return repo, tareas, entornos, runs, decisiones, checkpoints, tarea


def _servicio(ctx, inspector=None):
    _, tareas, entornos, runs, decisiones, checkpoints, _ = ctx
    return ServicioRecuperacion(
        tareas, entornos, runs, decisiones, checkpoints,
        inspector_procesos=inspector or InspectorFake(),
    )


def _run_preparado(ctx):
    *_, runs, decisiones, checkpoints, tarea = ctx
    preparado = runs.preparar_run(tarea.id)
    assert preparado.exito
    return preparado.run


def _run_pausado(ctx):
    run = _run_preparado(ctx)
    _, _, _, runs, decisiones, _, _ = ctx
    completada = ServicioEjecucionRuns(runs, decisiones).ejecutar_run(
        run.run_id,
        EjecutorCicloFake(EstadoInternoRun.REQUIERE_OK_PIO, causa_pausa="elige"),
    )
    return completada.resultado, completada.decision


def _escribir_proceso(run, pid=43210):
    Path(run.directorio_run, "procesos.json").write_text(
        json.dumps(
            {
                "run_id": run.run_id,
                "task_id": run.task_id,
                "session_id": run.entorno["session_id"],
                "procesos": [
                    {
                        "evento": "PROCESS_STARTED",
                        "pid": pid,
                        "comando": ["codex.exe", "exec", "--output", str(Path(run.directorio_run) / "result.json")],
                        "inicio": "2026-01-01T00:00:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return pid


def _escribir_execution(run, estado="AUTO_CONTINUE", return_code=0):
    run_dir = Path(run.directorio_run)
    (run_dir / "stdout.txt").write_text("ok\n", encoding="utf-8")
    (run_dir / "stderr.txt").write_text("", encoding="utf-8")
    (run_dir / "execution.json").write_text(
        json.dumps(
            {
                "run_id": run.run_id,
                "task_id": run.task_id,
                "estado_interno": estado,
                "inicio": "2026-01-01T00:00:00+00:00",
                "fin": "2026-01-01T00:01:00+00:00",
                "return_code": return_code,
                "errores": [],
            }
        ),
        encoding="utf-8",
    )


def test_recuperar_sin_tareas_devuelve_lista_vacia(tmp_path):
    ctx = _contexto(tmp_path, crear=False)
    assert _servicio(ctx).recuperar_estado() == []


@pytest.mark.parametrize("terminal", [EstadoTarea.FINALIZADA, EstadoTarea.CANCELADA])
def test_tareas_terminales_se_ignoran_y_conservan_lock(tmp_path, terminal):
    ctx = _contexto(tmp_path)
    repo, tareas, entornos, _, _, _, tarea = ctx
    if terminal is EstadoTarea.FINALIZADA:
        tareas.actualizar_estado(tarea.id, EstadoTarea.TRABAJANDO)
    tareas.actualizar_estado(tarea.id, terminal)

    assert _servicio(ctx).recuperar_estado() == []
    assert entornos.obtener_reserva(repo).task_id == tarea.id


def test_decision_pendiente_se_mantiene_y_no_ejecuta(tmp_path):
    ctx = _contexto(tmp_path)
    _, decision = _run_pausado(ctx)
    fake = EjecutorCicloFake()

    resultado = _servicio(ctx).recuperar_estado(lambda _: fake)[0]

    assert resultado.accion_realizada == AccionRecuperacion.ESPERANDO_DECISION.value
    assert resultado.estado_resultante == EstadoTarea.ESPERANDO_DECISION.value
    assert resultado.decision_id == decision.decision_id
    assert fake.llamadas == []


def test_crash_despues_decision_received_reanuda_exactamente_una_vez(tmp_path):
    ctx = _contexto(tmp_path)
    _, _, _, runs, decisiones, _, tarea = ctx
    _, decision = _run_pausado(ctx)
    decisiones.responder_decision(decision.decision_id, texto="continuar")
    fake = EjecutorCicloFake()
    servicio = _servicio(ctx)

    primero = servicio.recuperar_estado(lambda _: fake)[0]
    segundo = servicio.recuperar_estado(lambda _: fake)[0]

    aplicada = decisiones.obtener_decision(decision.decision_id)
    assert primero.accion_realizada == AccionRecuperacion.DECISION_REANUDADA.value
    assert aplicada.estado is EstadoDecision.APLICADA
    assert len(fake.llamadas) == 1
    assert len(runs.listar_runs_tarea(tarea.id)) == 2
    assert segundo.accion_realizada == AccionRecuperacion.SIN_ACCION.value


def test_crash_despues_run_created_inicia_mismo_run_sin_duplicar(tmp_path):
    ctx = _contexto(tmp_path)
    *_, runs, _, _, tarea = ctx
    run = _run_preparado(ctx)
    fake = EjecutorCicloFake()
    servicio = _servicio(ctx)

    primero = servicio.recuperar_estado(lambda _: fake)[0]
    servicio.recuperar_estado(lambda _: fake)

    assert primero.run_id == run.run_id
    assert primero.accion_realizada == AccionRecuperacion.RUN_PREPARADO_INICIADO.value
    assert fake.llamadas == [(run.run_id, tarea.id)]
    assert len(runs.listar_runs_tarea(tarea.id)) == 1


def test_started_proceso_vivo_verificado_no_duplica_ejecucion(tmp_path):
    ctx = _contexto(tmp_path)
    *_, runs, _, _, _ = ctx
    run = runs.iniciar_run(_run_preparado(ctx).run_id)
    pid = _escribir_proceso(run)
    inspector = InspectorFake(
        {pid: ProcesoObservado(pid, True, "codex.exe", f"codex exec --output {run.directorio_run} {run.run_id}")}
    )
    fake = EjecutorCicloFake()

    resultado = _servicio(ctx, inspector).recuperar_estado(lambda _: fake)[0]

    assert resultado.accion_realizada == AccionRecuperacion.PROCESO_ACTIVO.value
    assert resultado.proceso_detectado is True
    assert fake.llamadas == []
    assert runs.obtener_run(run.run_id).estado_interno is EstadoInternoRun.INICIADO


def test_resume_de_decision_ya_iniciado_y_vivo_no_se_inicia_dos_veces(tmp_path):
    ctx = _contexto(tmp_path)
    _, _, _, runs, decisiones, _, tarea = ctx
    _, decision = _run_pausado(ctx)
    respondida = decisiones.responder_decision(decision.decision_id, texto="continúa")
    preparado = runs.preparar_resume(
        tarea.id,
        decision.run_id,
        decisiones.respuesta_para_motor(respondida),
        decision_id=decision.decision_id,
    ).run
    run = runs.iniciar_run(preparado.run_id)
    pid = _escribir_proceso(run)
    inspector = InspectorFake(
        {pid: ProcesoObservado(pid, True, "codex.exe", f"codex {run.directorio_run} {run.run_id}")}
    )
    fake = EjecutorCicloFake()

    resultado = _servicio(ctx, inspector).recuperar_estado(lambda _: fake)[0]

    assert resultado.accion_realizada == AccionRecuperacion.PROCESO_ACTIVO.value
    assert decisiones.obtener_decision(decision.decision_id).estado is EstadoDecision.RESPONDIDA
    assert fake.llamadas == []
    assert len(runs.listar_runs_tarea(tarea.id)) == 2


def test_metadata_proceso_se_persiste_atomicamente_con_run_y_sesion(tmp_path):
    ctx = _contexto(tmp_path)
    run = _run_preparado(ctx)
    eventos = [{"evento": "PROCESS_STARTED", "pid": 12345, "comando": ["codex.exe"]}]

    EjecutorCicloReal._persistir_procesos(run, eventos)

    path = Path(run.directorio_run, "procesos.json")
    datos = json.loads(path.read_text(encoding="utf-8"))
    assert datos["run_id"] == run.run_id
    assert datos["task_id"] == run.task_id
    assert datos["session_id"] == run.entorno["session_id"]
    assert datos["procesos"] == eventos
    assert not list(Path(run.directorio_run).glob(".procesos.*.tmp"))


def test_pid_ambiguo_bloquea_y_no_mata_proceso(tmp_path):
    ctx = _contexto(tmp_path)
    *_, runs, _, _, _ = ctx
    run = runs.iniciar_run(_run_preparado(ctx).run_id)
    pid = _escribir_proceso(run)
    inspector = InspectorFake({pid: ProcesoObservado(pid, True, "otro.exe", "otro comando")})

    resultado = _servicio(ctx, inspector).recuperar_estado()[0]

    assert resultado.estado_resultante == EstadoTarea.BLOQUEADA.value
    assert "no se mata" in resultado.causa
    assert inspector.inspecciones == [pid]


def test_started_sin_proceso_ni_resultado_entra_recuperando_no_exito(tmp_path):
    ctx = _contexto(tmp_path)
    _, tareas, _, runs, _, _, tarea = ctx
    run = runs.iniciar_run(_run_preparado(ctx).run_id)

    resultado = _servicio(ctx).recuperar_estado()[0]

    persistido = runs.obtener_run(run.run_id)
    assert resultado.accion_realizada == AccionRecuperacion.RUN_INTERRUMPIDO.value
    assert persistido.estado_interno is EstadoInternoRun.INTERRUMPIDO
    assert persistido.resultado.estado_v02_propuesto is EstadoTarea.RECUPERANDO
    assert tareas.cargar(tarea.id).estado is EstadoTarea.RECUPERANDO
    assert not any(e.tipo == "RUN_COMPLETED" for e in tareas.cargar(tarea.id).historial)


def test_started_proceso_ausente_con_execution_completa_reconcilia_sin_ejecutar(tmp_path):
    ctx = _contexto(tmp_path)
    *_, runs, _, _, _ = ctx
    run = runs.iniciar_run(_run_preparado(ctx).run_id)
    pid = _escribir_proceso(run)
    _escribir_execution(run)
    fake = EjecutorCicloFake()

    resultado = _servicio(ctx, InspectorFake({pid: ProcesoObservado(pid, False)})).recuperar_estado(lambda _: fake)[0]

    assert resultado.accion_realizada == AccionRecuperacion.RUN_RECONCILIADO.value
    assert runs.obtener_run(run.run_id).estado_interno is EstadoInternoRun.AUTO_CONTINUE
    assert fake.llamadas == []


def test_execution_completa_de_pausa_reconstruye_decision_una_sola_vez(tmp_path):
    ctx = _contexto(tmp_path)
    *_, runs, decisiones, _, tarea = ctx
    run = runs.iniciar_run(_run_preparado(ctx).run_id)
    _escribir_execution(run, estado="REQUIERE_OK_PIO")
    servicio = _servicio(ctx)

    primero = servicio.recuperar_estado()[0]
    segundo = servicio.recuperar_estado()[0]

    creadas = decisiones.listar_decisiones(tarea.id)
    assert primero.accion_realizada == AccionRecuperacion.RUN_RECONCILIADO.value
    assert segundo.accion_realizada == AccionRecuperacion.ESPERANDO_DECISION.value
    assert len(creadas) == 1
    assert creadas[0].estado is EstadoDecision.PENDIENTE
    assert creadas[0].run_id == run.run_id


def test_execution_incompleta_no_se_considera_resultado_final(tmp_path):
    ctx = _contexto(tmp_path)
    *_, runs, _, _, _ = ctx
    run = runs.iniciar_run(_run_preparado(ctx).run_id)
    Path(run.directorio_run, "execution.json").write_text("{}", encoding="utf-8")

    _servicio(ctx).recuperar_estado()

    assert runs.obtener_run(run.run_id).estado_interno is EstadoInternoRun.INTERRUMPIDO


def test_crash_tras_run_resultado_antes_estado_tarea_se_reconcilia(tmp_path, monkeypatch):
    ctx = _contexto(tmp_path)
    _, tareas, _, runs, _, _, tarea = ctx
    run = runs.iniciar_run(_run_preparado(ctx).run_id)
    original = tareas.actualizar_estado

    def crash(*args, **kwargs):
        raise RuntimeError("crash simulado antes de actualizar tarea")

    monkeypatch.setattr(tareas, "actualizar_estado", crash)
    with pytest.raises(RuntimeError, match="crash simulado"):
        runs.registrar_resultado(run.run_id, EstadoInternoRun.REQUIERE_OK_PIO, resumen="pausa")
    monkeypatch.setattr(tareas, "actualizar_estado", original)

    resultado = _servicio(ctx).recuperar_estado()[0]

    assert resultado.accion_realizada == AccionRecuperacion.RUN_RECONCILIADO.value
    assert tareas.cargar(tarea.id).estado is EstadoTarea.ESPERANDO_DECISION


def test_tarea_sale_de_recuperando_al_estado_del_resultado_persistido(tmp_path):
    ctx = _contexto(tmp_path)
    _, tareas, _, runs, decisiones, _, tarea = ctx
    run = _run_preparado(ctx)
    ServicioEjecucionRuns(runs, decisiones).ejecutar_run(
        run.run_id, EjecutorCicloFake(EstadoInternoRun.AUTO_CONTINUE)
    )
    tareas.actualizar_estado(tarea.id, EstadoTarea.RECUPERANDO)

    resultado = _servicio(ctx).recuperar_estado()[0]

    assert resultado.accion_realizada == AccionRecuperacion.RUN_RECONCILIADO.value
    assert resultado.estado_previo == EstadoTarea.RECUPERANDO.value
    assert resultado.estado_resultante == EstadoTarea.TRABAJANDO.value
    assert any(
        e.tipo == "RECOVERY_COMPLETED" and e.datos.get("run_id") == run.run_id
        for e in tareas.cargar(tarea.id).historial
    )


def test_lock_valido_se_conserva(tmp_path):
    ctx = _contexto(tmp_path)
    repo, _, entornos, _, _, _, tarea = ctx

    resultado = _servicio(ctx).recuperar_estado()[0]

    assert resultado.lock_valido is True
    assert entornos.obtener_reserva(repo).task_id == tarea.id


def test_lock_de_otra_tarea_bloquea(tmp_path):
    ctx = _contexto(tmp_path)
    _, _, entornos, _, _, _, _ = ctx
    path = next(entornos.directorio_locks.glob("*.json"))
    datos = json.loads(path.read_text(encoding="utf-8"))
    datos["task_id"] = str(uuid4())
    path.write_text(json.dumps(datos), encoding="utf-8")

    resultado = _servicio(ctx).recuperar_estado()[0]

    assert resultado.estado_resultante == EstadoTarea.BLOQUEADA.value
    assert "otra tarea" in resultado.causa


def test_lock_sesion_anterior_pid_ausente_se_adopta_una_vez(tmp_path):
    ctx = _contexto(tmp_path)
    repo, tareas, entornos, runs, _, checkpoints, tarea = ctx
    anterior = entornos.obtener_reserva(repo)
    nuevos_entornos = GestorEntornos(tareas, entornos.directorio_locks)
    nuevos_runs = GestorRuns(tareas, nuevos_entornos, runs.directorio_runs)
    nuevas_decisiones = GestorDecisiones(tareas, nuevos_runs, tmp_path / "estado" / "decisiones")
    servicio = ServicioRecuperacion(
        tareas, nuevos_entornos, nuevos_runs, nuevas_decisiones,
        GestorCheckpoints(tareas, nuevos_runs, checkpoints.directorio),
        inspector_procesos=InspectorFake({anterior.process_id: ProcesoObservado(anterior.process_id, False)}),
    )

    primero = servicio.recuperar_estado()[0]
    adoptado = nuevos_entornos.obtener_reserva(repo)
    segundo = servicio.recuperar_estado()[0]

    assert primero.lock_valido and adoptado.session_id == nuevos_entornos.session_id
    assert adoptado.task_id == tarea.id
    assert segundo.lock_valido
    eventos = [e for e in tareas.cargar(tarea.id).historial if e.tipo == "RECOVERY_LOCK_VALIDATED"]
    assert len(eventos) == 1


def test_lock_sesion_anterior_pid_vivo_es_ambiguo_y_no_se_libera(tmp_path):
    ctx = _contexto(tmp_path)
    repo, tareas, entornos, runs, decisiones, checkpoints, _ = ctx
    anterior = entornos.obtener_reserva(repo)
    nuevos_entornos = GestorEntornos(tareas, entornos.directorio_locks)
    servicio = ServicioRecuperacion(
        tareas, nuevos_entornos, GestorRuns(tareas, nuevos_entornos, runs.directorio_runs),
        decisiones, checkpoints,
        inspector_procesos=InspectorFake({anterior.process_id: ProcesoObservado(anterior.process_id, True)}),
    )

    resultado = servicio.recuperar_estado()[0]

    assert resultado.estado_resultante == EstadoTarea.BLOQUEADA.value
    assert nuevos_entornos.obtener_reserva(repo).session_id == anterior.session_id


@pytest.mark.parametrize("alteracion", ["branch", "head", "missing"])
def test_entorno_git_incompatible_bloquea_sin_corregir(tmp_path, alteracion):
    ctx = _contexto(tmp_path)
    repo = ctx[0]
    if alteracion == "branch":
        _git(repo, "checkout", "-b", "otra")
    elif alteracion == "head":
        (repo / "nuevo.txt").write_text("x", encoding="utf-8")
        _git(repo, "add", "nuevo.txt")
        _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "otro")
    else:
        # El contrato se conserva; se renombra el repo temporal sin borrarlo.
        repo.rename(tmp_path / "repo_movido")

    resultado = _servicio(ctx).recuperar_estado()[0]

    assert resultado.estado_resultante == EstadoTarea.BLOQUEADA.value
    assert resultado.entorno_valido is False


def test_cambios_inesperados_en_run_preparado_bloquean_sin_limpiar(tmp_path):
    ctx = _contexto(tmp_path, modo=ModoTarea.WORKSPACE_WRITE)
    repo = ctx[0]
    _run_preparado(ctx)
    (repo / "ajeno.txt").write_text("no explicado", encoding="utf-8")

    resultado = _servicio(ctx).recuperar_estado(lambda _: EjecutorCicloFake())[0]

    assert resultado.estado_resultante == EstadoTarea.BLOQUEADA.value
    assert (repo / "ajeno.txt").is_file()


def test_cambios_explicados_y_dentro_alcance_no_bloquean(tmp_path):
    ctx = _contexto(tmp_path, modo=ModoTarea.WORKSPACE_WRITE)
    repo, _, _, runs, decisiones, _, _ = ctx
    run = _run_preparado(ctx)
    fake = EjecutorCicloFake()

    class EscritorFake:
        def ejecutar(self, run_actual, tarea):
            destino = repo / "permitido" / "resultado.txt"
            destino.parent.mkdir()
            destino.write_text("generado", encoding="utf-8")
            return fake.ejecutar(run_actual, tarea)

    ServicioEjecucionRuns(runs, decisiones).ejecutar_run(run.run_id, EscritorFake())

    resultado = _servicio(ctx).recuperar_estado()[0]

    assert resultado.entorno_valido is True
    assert resultado.estado_resultante != EstadoTarea.BLOQUEADA.value


def test_eventos_recovery_no_se_duplican_en_doble_recuperacion(tmp_path):
    ctx = _contexto(tmp_path)
    _, tareas, _, runs, _, _, tarea = ctx
    runs.iniciar_run(_run_preparado(ctx).run_id)
    servicio = _servicio(ctx)

    servicio.recuperar_estado()
    servicio.recuperar_estado()

    eventos = [
        (e.tipo, json.dumps(e.datos, sort_keys=True))
        for e in tareas.cargar(tarea.id).historial
        if e.tipo.startswith("RECOVERY_")
    ]
    assert len(eventos) == len(set(eventos))


def test_resultado_estructurado_incluye_checkpoint_y_campos_requeridos(tmp_path):
    ctx = _contexto(tmp_path)
    *_, checkpoints, tarea = ctx
    run = _run_preparado(ctx)
    checkpoint = checkpoints.registrar_checkpoint(
        task_id=tarea.id, run_id=run.run_id, tipo="PASO", validado=True
    )

    resultado = _servicio(ctx).recuperar_estado()[0]

    assert resultado.task_id == tarea.id
    assert resultado.run_id == run.run_id
    assert resultado.checkpoint_id == checkpoint.checkpoint_id
    assert isinstance(resultado.warnings, tuple)


def test_lock_sin_tarea_se_diagnostica_y_no_se_elimina(tmp_path):
    ctx = _contexto(tmp_path)
    _, _, entornos, _, _, _, _ = ctx
    path = next(entornos.directorio_locks.glob("*.json"))
    datos = json.loads(path.read_text(encoding="utf-8"))
    datos["task_id"] = str(uuid4())
    path.write_text(json.dumps(datos), encoding="utf-8")
    servicio = _servicio(ctx)

    servicio.recuperar_estado()

    assert servicio.ultimo_diagnostico_locks
    assert path.is_file()


def test_pytest_solo_usa_fake_y_no_inicia_subprocesos_codex(tmp_path, monkeypatch):
    ctx = _contexto(tmp_path)
    _run_preparado(ctx)
    fake = EjecutorCicloFake()

    _servicio(ctx).recuperar_estado(lambda _: fake)

    assert len(fake.llamadas) == 1
    assert all("codex" not in item[0].casefold() for item in fake.llamadas)
