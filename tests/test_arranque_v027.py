import json
from pathlib import Path
import subprocess

from arranque import EstadoGlobalOrquestador, ServicioArranque, iniciar_orquestador
from decisiones_persistentes import EstadoDecision
from ejecucion_v02 import EjecutorCicloFake, ServicioEjecucionRuns
from recuperacion import ProcesoObservado
from runs_persistentes import EstadoInternoRun
from tareas_persistentes import EstadoTarea, ModoTarea, crear_contrato


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


class InspectorFake:
    def __init__(self, observados=None):
        self.observados = dict(observados or {})

    def inspeccionar(self, pid):
        return self.observados.get(pid, ProcesoObservado(pid, False))


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _tarea(servicio, tmp_path):
    repo, head = _repo(tmp_path)
    tarea = servicio.gestor_tareas.crear_tarea(
        orden_original="fake",
        repo=str(repo),
        worktree=str(repo),
        rama="main",
        commit_inicial=head,
        modo=ModoTarea.READ_ONLY,
        contrato=crear_contrato(objetivo="arranque", condiciones_finalizacion="revisar"),
    )
    servicio.gestor_entornos.reservar_worktree(tarea.id)
    return repo, tarea


def test_arranque_limpio_transita_iniciando_recuperando_listo_y_persiste(tmp_path):
    estados = []
    servicio = ServicioArranque(tmp_path, al_cambiar_estado=estados.append)

    resultado = servicio.iniciar_orquestador()

    assert estados == [
        EstadoGlobalOrquestador.INICIANDO,
        EstadoGlobalOrquestador.RECUPERANDO,
        EstadoGlobalOrquestador.LISTO,
    ]
    assert resultado.estado_global is EstadoGlobalOrquestador.LISTO
    assert resultado.tareas_inspeccionadas == 0
    assert servicio.obtener_estado_global() is EstadoGlobalOrquestador.LISTO
    persistido = json.loads((tmp_path / "estado" / "orquestador" / "arranque.json").read_text(encoding="utf-8"))
    assert persistido["estado_global"] == "LISTO"


def test_funcion_iniciar_orquestador_devuelve_servicio_y_resumen(tmp_path):
    servicio, resultado = iniciar_orquestador(tmp_path)
    assert servicio.obtener_estado_global() is EstadoGlobalOrquestador.LISTO
    assert resultado.timestamp


def test_no_acepta_run_mientras_recuperando_y_devuelve_resultado_funcional(tmp_path):
    intentos = []
    servicio = ServicioArranque(tmp_path)
    _, tarea = _tarea(servicio, tmp_path)
    run = servicio.gestor_runs.preparar_run(tarea.id).run

    def observar(estado):
        if estado is EstadoGlobalOrquestador.RECUPERANDO:
            intentos.append(
                servicio.ejecutar_run_controlado(run.run_id, EjecutorCicloFake())
            )

    servicio.al_cambiar_estado = observar
    servicio.iniciar_orquestador()

    assert intentos[0].codigo == "ORCHESTRATOR_NOT_READY"
    assert intentos[0].exito is False
    assert servicio.gestor_runs.obtener_run(run.run_id).estado_interno is EstadoInternoRun.PREPARADO


def test_entorno_alterado_produce_estado_global_bloqueado(tmp_path):
    servicio = ServicioArranque(tmp_path)
    repo, _ = _tarea(servicio, tmp_path)
    _git(repo, "checkout", "-b", "otra")

    resultado = servicio.iniciar_orquestador()

    assert resultado.estado_global is EstadoGlobalOrquestador.BLOQUEADO
    assert resultado.tareas_bloqueadas == 1
    assert servicio.obtener_estado_global() is EstadoGlobalOrquestador.BLOQUEADO


def test_decision_pendiente_aparece_en_resumen_sin_ejecutar(tmp_path):
    servicio = ServicioArranque(tmp_path)
    _, tarea = _tarea(servicio, tmp_path)
    run = servicio.gestor_runs.preparar_run(tarea.id).run
    completada = ServicioEjecucionRuns(
        servicio.gestor_runs, servicio.gestor_decisiones
    ).ejecutar_run(
        run.run_id,
        EjecutorCicloFake(EstadoInternoRun.REQUIERE_OK_PIO, causa_pausa="elige"),
    )

    resultado = servicio.iniciar_orquestador()

    assert completada.decision.estado is EstadoDecision.PENDIENTE
    assert resultado.tareas_esperando_decision == 1
    assert resultado.estado_global is EstadoGlobalOrquestador.LISTO


def test_decision_respondida_se_inspecciona_pero_no_ejecuta_durante_startup(tmp_path):
    servicio = ServicioArranque(tmp_path)
    _, tarea = _tarea(servicio, tmp_path)
    run = servicio.gestor_runs.preparar_run(tarea.id).run
    completada = ServicioEjecucionRuns(
        servicio.gestor_runs, servicio.gestor_decisiones
    ).ejecutar_run(
        run.run_id, EjecutorCicloFake(EstadoInternoRun.REQUIERE_OK_PIO)
    )
    servicio.gestor_decisiones.responder_decision(
        completada.decision.decision_id, texto="continuar"
    )
    fake = EjecutorCicloFake()
    servicio.ejecutor_factory = lambda _: fake

    resultado = servicio.iniciar_orquestador()

    assert resultado.tareas_esperando_decision == 1
    assert fake.llamadas == []
    assert servicio.gestor_decisiones.obtener_decision(completada.decision.decision_id).estado is EstadoDecision.RESPONDIDA


def test_run_interrumpido_se_refleja_en_resultado_de_arranque(tmp_path):
    servicio = ServicioArranque(tmp_path)
    _, tarea = _tarea(servicio, tmp_path)
    run = servicio.gestor_runs.preparar_run(tarea.id).run
    servicio.gestor_runs.iniciar_run(run.run_id)
    servicio.gestor_runs.registrar_resultado(
        run.run_id, EstadoInternoRun.INTERRUMPIDO, resumen="crash"
    )

    resultado = servicio.iniciar_orquestador()

    assert resultado.tareas_inspeccionadas == 1
    assert resultado.resultados_tareas[0].run_id == run.run_id
    assert resultado.resultados_tareas[0].estado_resultante == EstadoTarea.RECUPERANDO.value


def test_proceso_activo_verificado_se_cuenta_sin_duplicar(tmp_path):
    pid = 45678
    inspector = InspectorFake()
    servicio = ServicioArranque(tmp_path, inspector_procesos=inspector)
    _, tarea = _tarea(servicio, tmp_path)
    run = servicio.gestor_runs.iniciar_run(servicio.gestor_runs.preparar_run(tarea.id).run.run_id)
    Path(run.directorio_run, "procesos.json").write_text(
        json.dumps({
            "run_id": run.run_id,
            "task_id": run.task_id,
            "procesos": [{
                "evento": "PROCESS_STARTED", "pid": pid,
                "comando": ["codex.exe", str(Path(run.directorio_run) / "salida.json")],
            }],
        }), encoding="utf-8"
    )
    inspector.observados[pid] = ProcesoObservado(
        pid, True, "codex.exe", f"codex {run.directorio_run} {run.run_id}"
    )

    resultado = servicio.iniciar_orquestador()

    assert resultado.tareas_activas_detectadas == 1
    assert servicio.gestor_runs.obtener_run(run.run_id).estado_interno is EstadoInternoRun.INICIADO


def test_lock_ambiguo_se_refleja_y_bloquea(tmp_path):
    creador = ServicioArranque(tmp_path)
    repo, _ = _tarea(creador, tmp_path)
    reserva = creador.gestor_entornos.obtener_reserva(repo)
    reiniciado = ServicioArranque(
        tmp_path,
        inspector_procesos=InspectorFake(
            {reserva.process_id: ProcesoObservado(reserva.process_id, True)}
        ),
    )

    resultado = reiniciado.iniciar_orquestador()

    assert resultado.estado_global is EstadoGlobalOrquestador.BLOQUEADO
    assert resultado.locks_ambiguos >= 1


def test_iniciar_dos_veces_es_idempotente_sin_duplicar_eventos(tmp_path):
    servicio = ServicioArranque(tmp_path)
    primero = servicio.iniciar_orquestador()
    eventos_path = tmp_path / "estado" / "orquestador" / "eventos.json"
    eventos_antes = json.loads(eventos_path.read_text(encoding="utf-8"))

    segundo = servicio.iniciar_orquestador()
    eventos_despues = json.loads(eventos_path.read_text(encoding="utf-8"))

    assert segundo is primero
    assert eventos_despues == eventos_antes
    assert [item["tipo"] for item in eventos_despues] == [
        "ORCHESTRATOR_STARTING", "ORCHESTRATOR_RECOVERY_STARTED", "ORCHESTRATOR_READY"
    ]
