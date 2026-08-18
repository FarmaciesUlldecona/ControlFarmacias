import json
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from contrato_ejecutor import (
    ContextoRetryEjecutor,
    ContratoEjecutorV02,
    EvidenciaRetryEjecutor,
)
from ejecucion_v02 import EjecutorCicloFake, EjecutorCicloReal
from fachada_v02 import (
    EspecificacionTareaV02,
    OrquestadorV02,
    ResultadoPublicoV02,
    ResumenSistemaV02,
)
from recuperacion import ProcesoObservado
from runs_persistentes import EstadoInternoRun
from tareas_persistentes import CapacidadCheckpoint, EstadoTarea, ModoTarea


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


class InspectorFake:
    def __init__(self, observados=None):
        self.observados = dict(observados or {})

    def inspeccionar(self, pid):
        return self.observados.get(pid, ProcesoObservado(pid, False))


def _repo(tmp_path, nombre="repo"):
    repo = tmp_path / nombre
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _spec(tmp_path, *, capacidad=CapacidadCheckpoint.NONE, nombre="repo", clave=None):
    repo, head = _repo(tmp_path, nombre)
    return repo, EspecificacionTareaV02(
        orden_original="operación estructurada",
        objetivo="probar fachada",
        repo=str(repo),
        worktree=str(repo),
        rama="main",
        commit_inicial=head,
        modo=ModoTarea.READ_ONLY,
        condicion_finalizacion="resultado revisado",
        capacidad_checkpoint=capacidad,
        clave_idempotencia=clave,
    )


def _orquestador(tmp_path, fake=None, inspector=None):
    fake = fake or EjecutorCicloFake()
    servicio = OrquestadorV02(
        tmp_path,
        ejecutor_factory=lambda _: fake,
        inspector_procesos=inspector,
    )
    return servicio, fake


def _crear(orquestador, spec):
    resultado = orquestador.crear_tarea(spec)
    assert resultado.ok, resultado
    return resultado


def _interrumpida(
    orquestador,
    tmp_path,
    *,
    capacidad=CapacidadCheckpoint.CHECKPOINT_RESUME,
    nombre="repo",
):
    _, spec = _spec(tmp_path, capacidad=capacidad, nombre=nombre)
    creada = _crear(orquestador, spec)
    internos = orquestador._arranque
    run = internos.gestor_runs.preparar_run(creada.task_id).run
    internos.gestor_runs.iniciar_run(run.run_id)
    checkpoint = internos.gestor_checkpoints.registrar_checkpoint(
        task_id=creada.task_id,
        run_id=run.run_id,
        tipo="LOTE_VALIDADO",
        payload={
            "acciones_completadas": ["uno", "dos"],
            "acciones_pendientes": ["tres"],
            "posicion_reanudacion": 3,
        },
        validado=True,
    )
    internos.gestor_runs.registrar_resultado(
        run.run_id, EstadoInternoRun.INTERRUMPIDO, resumen="crash"
    )
    return creada, run, checkpoint


def test_fachada_instanciable_y_no_ejecuta_antes_de_iniciar(tmp_path):
    orquestador, fake = _orquestador(tmp_path)
    resultado = orquestador.ejecutar_tarea(str(uuid4()))
    assert resultado.codigo == "ORCHESTRATOR_NOT_READY"
    assert not resultado.ok
    assert fake.llamadas == []


def test_iniciar_ejecuta_recovery_y_lleva_a_listo_idempotente(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    primero = orquestador.iniciar()
    segundo = orquestador.iniciar()
    assert primero.ok and segundo.ok
    assert primero.codigo == segundo.codigo == "ORCHESTRATOR_READY"
    assert primero.datos["estado_global"] == "LISTO"
    assert orquestador.estado().value == "LISTO"


def test_crear_tarea_valida_entorno_reserva_lock_y_devuelve_task_id(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    repo, spec = _spec(tmp_path)

    resultado = orquestador.crear_tarea(spec)

    assert resultado.ok and resultado.codigo == "TASK_CREATED"
    assert resultado.task_id
    assert resultado.estado_tarea == EstadoTarea.PREPARANDO.value
    assert resultado.datos == {"entorno_validado": True, "lock_reservado": True}
    assert orquestador._arranque.gestor_entornos.obtener_reserva(repo).task_id == resultado.task_id


def test_crear_tarea_con_clave_es_idempotente(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    _, spec = _spec(tmp_path, clave="alta-001")
    primero = orquestador.crear_tarea(spec)
    segundo = orquestador.crear_tarea(spec)
    assert segundo.codigo == "TASK_ALREADY_CREATED"
    assert segundo.task_id == primero.task_id
    assert len(orquestador.listar_tareas().datos["tareas"]) == 1


def test_conflicto_worktree_es_estructurado_sin_segunda_tarea(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    repo, spec = _spec(tmp_path)
    primera = _crear(orquestador, spec)
    segunda_spec = EspecificacionTareaV02(
        orden_original="otra", objetivo="otra", repo=str(repo), worktree=str(repo),
        rama="main", commit_inicial=spec.commit_inicial,
    )
    segunda = orquestador.crear_tarea(segunda_spec)
    assert segunda.codigo == "WORKTREE_BUSY"
    assert segunda.task_id == primera.task_id
    assert len(orquestador.listar_tareas().datos["tareas"]) == 1


def test_entorno_invalido_es_error_funcional_sin_crear_media_tarea(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    _, spec = _spec(tmp_path)
    spec = EspecificacionTareaV02(**{**spec.__dict__, "rama": "otra"})
    resultado = orquestador.crear_tarea(spec)
    assert resultado.codigo == "INVALID_ENVIRONMENT"
    assert orquestador.listar_tareas().datos["tareas"] == []


def test_ejecutar_tarea_crea_run_interno_e_invoca_fake_sin_run_id_del_consumidor(tmp_path):
    orquestador, fake = _orquestador(tmp_path)
    orquestador.iniciar()
    _, spec = _spec(tmp_path)
    tarea = _crear(orquestador, spec)

    resultado = orquestador.ejecutar_tarea(tarea.task_id)

    assert resultado.ok and resultado.codigo == "RUN_COMPLETED"
    assert resultado.run_id
    assert resultado.datos["estado_interno"] == "AUTO_CONTINUE"
    assert fake.llamadas == [(resultado.run_id, tarea.task_id)]
    assert len(orquestador._arranque.gestor_runs.listar_runs_tarea(tarea.task_id)) == 1


def test_ejecucion_publica_con_clave_no_duplica_run(tmp_path):
    orquestador, fake = _orquestador(tmp_path)
    orquestador.iniciar()
    _, spec = _spec(tmp_path)
    tarea = _crear(orquestador, spec)
    primero = orquestador.ejecutar_tarea(tarea.task_id, clave_idempotencia="ciclo-1")
    segundo = orquestador.ejecutar_tarea(tarea.task_id, clave_idempotencia="ciclo-1")
    assert segundo.codigo == "RUN_ALREADY_EXECUTED"
    assert segundo.run_id == primero.run_id
    assert len(fake.llamadas) == 1


def test_pausa_crea_decision_y_responder_reanuda_sin_resume_manual(tmp_path):
    pausa = EjecutorCicloFake(EstadoInternoRun.REQUIERE_OK_PIO, causa_pausa="elige")
    orquestador, _ = _orquestador(tmp_path, pausa)
    orquestador.iniciar()
    _, spec = _spec(tmp_path)
    tarea = _crear(orquestador, spec)
    ejecutada = orquestador.ejecutar_tarea(tarea.task_id)

    pendiente = orquestador.obtener_decision_pendiente(tarea.task_id)
    resume = EjecutorCicloFake()
    respondida = orquestador.responder_decision(
        tarea.task_id, texto="continuar", ejecutor=resume
    )

    assert ejecutada.codigo == "DECISION_REQUIRED"
    assert pendiente.decision_id == ejecutada.decision_id
    assert pendiente.datos["pregunta"]
    assert respondida.ok and respondida.codigo == "DECISION_APPLIED"
    assert respondida.run_id != ejecutada.run_id
    assert resume.llamadas == [(respondida.run_id, tarea.task_id)]


def test_responder_decision_aplicada_es_idempotente(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    _, spec = _spec(tmp_path)
    tarea = _crear(orquestador, spec)
    orquestador.ejecutar_tarea(
        tarea.task_id,
        ejecutor=EjecutorCicloFake(EstadoInternoRun.REQUIERE_OK_PIO),
    )
    fake = EjecutorCicloFake()
    primero = orquestador.responder_decision(tarea.task_id, texto="sí", ejecutor=fake)
    segundo = orquestador.responder_decision(tarea.task_id, texto="sí", ejecutor=fake)
    assert segundo.codigo == "DECISION_ALREADY_APPLIED"
    assert segundo.run_id == primero.run_id
    assert len(fake.llamadas) == 1


def test_tarea_terminal_rechaza_ejecucion_y_cancelacion_es_idempotente(tmp_path):
    orquestador, fake = _orquestador(tmp_path)
    orquestador.iniciar()
    _, spec = _spec(tmp_path)
    tarea = _crear(orquestador, spec)
    cancelada = orquestador.cancelar_tarea(tarea.task_id)
    repetida = orquestador.cancelar_tarea(tarea.task_id)
    ejecucion = orquestador.ejecutar_tarea(tarea.task_id)
    assert cancelada.codigo == "TASK_CANCELLED"
    assert repetida.codigo == "TASK_ALREADY_CANCELLED"
    assert ejecucion.codigo == "TASK_TERMINAL"
    assert fake.llamadas == []


def test_cancelacion_segura_conserva_runs_y_libera_lock(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    repo, spec = _spec(tmp_path)
    tarea = _crear(orquestador, spec)
    run = orquestador.ejecutar_tarea(tarea.task_id)

    cancelada = orquestador.cancelar_tarea(tarea.task_id)

    assert cancelada.ok
    assert orquestador._arranque.gestor_runs.obtener_run(run.run_id).resultado is not None
    assert orquestador._arranque.gestor_entornos.obtener_reserva(repo) is None


def test_cancelacion_no_mata_proceso_activo(tmp_path):
    pid = 99881
    inspector = InspectorFake({pid: ProcesoObservado(pid, True)})
    orquestador, _ = _orquestador(tmp_path, inspector=inspector)
    orquestador.iniciar()
    _, spec = _spec(tmp_path)
    tarea = _crear(orquestador, spec)
    run = orquestador._arranque.gestor_runs.iniciar_run(
        orquestador._arranque.gestor_runs.preparar_run(tarea.task_id).run.run_id
    )
    Path(run.directorio_run, "procesos.json").write_text(
        json.dumps({
            "run_id": run.run_id, "task_id": run.task_id,
            "procesos": [{"evento": "PROCESS_STARTED", "pid": pid, "comando": ["codex"]}],
        }), encoding="utf-8"
    )
    resultado = orquestador.cancelar_tarea(tarea.task_id)
    assert resultado.codigo == "ACTIVE_PROCESS_CONTROL_REQUIRED"
    assert resultado.estado_tarea == EstadoTarea.TRABAJANDO.value


def test_resumen_sistema_limpio_activo_decision_y_bloqueo(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    limpio = orquestador.resumen_sistema()
    assert isinstance(limpio, ResumenSistemaV02)
    assert limpio.tareas_activas == 0
    _, spec_a = _spec(tmp_path, nombre="a")
    activa = _crear(orquestador, spec_a)
    con_activa = orquestador.resumen_sistema()
    assert con_activa.tareas_activas == 1 and con_activa.worktrees_ocupados == 1
    orquestador.ejecutar_tarea(
        activa.task_id,
        ejecutor=EjecutorCicloFake(EstadoInternoRun.REQUIERE_OK_PIO),
    )
    assert orquestador.resumen_sistema().decisiones_pendientes == 1
    _, spec_b = _spec(tmp_path, nombre="b")
    bloqueada = _crear(orquestador, spec_b)
    orquestador._arranque.gestor_tareas.actualizar_estado(
        bloqueada.task_id, EstadoTarea.BLOQUEADA
    )
    resumen = orquestador.resumen_sistema()
    assert resumen.tareas_bloqueadas == 1
    assert resumen.tareas_esperando_decision == 1


def test_resultados_y_errores_publicos_son_tipados(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    no_lista = orquestador.crear_tarea("no es spec")
    orquestador.iniciar()
    ausente = orquestador.obtener_tarea(str(uuid4()))
    decision = orquestador.obtener_decision_pendiente(str(uuid4()))
    assert isinstance(no_lista, ResultadoPublicoV02)
    assert no_lista.codigo == "ORCHESTRATOR_NOT_READY"
    assert ausente.codigo == "TASK_NOT_FOUND"
    assert decision.codigo == "TASK_NOT_FOUND"
    assert isinstance(ausente.errores, tuple)


@pytest.mark.parametrize(
    ("capacidad", "soporta"),
    [
        (CapacidadCheckpoint.NONE, False),
        (CapacidadCheckpoint.FULL_RUN_ONLY, True),
        (CapacidadCheckpoint.CHECKPOINT_RESUME, True),
    ],
)
def test_contrato_formal_declara_capacidades(capacidad, soporta):
    fake = EjecutorCicloFake(capacidad_checkpoint=capacidad)
    assert isinstance(fake, ContratoEjecutorV02)
    assert fake.capacidad_checkpoint is capacidad
    assert fake.soporta_reintentos() is soporta


def test_ejecutor_codex_actual_declara_full_run_only(tmp_path):
    real = EjecutorCicloReal(tmp_path, {})
    assert isinstance(real, ContratoEjecutorV02)
    assert real.capacidad_checkpoint is CapacidadCheckpoint.FULL_RUN_ONLY
    assert real.soporta_reintentos()


def test_checkpoint_resume_verifica_evidencia_y_persiste_acciones(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    tarea, _, cp = _interrumpida(orquestador, tmp_path)
    preparado = orquestador.preparar_reintento(tarea.task_id, cp.checkpoint_id)
    fake = EjecutorCicloFake(capacidad_checkpoint=CapacidadCheckpoint.CHECKPOINT_RESUME)

    resultado = orquestador.ejecutar_reintento(
        preparado.datos["retry_id"], ejecutor=fake
    )

    assert resultado.ok and resultado.codigo == "RETRY_COMPLETED"
    run = orquestador._arranque.gestor_runs.obtener_run(resultado.run_id)
    evidencia = run.resultado.metadata["ejecucion"]["evidencia_retry"]
    assert evidencia["checkpoint_id_recibido"] == cp.checkpoint_id
    assert evidencia["checkpoint_id_utilizado"] == cp.checkpoint_id
    assert evidencia["estrategia_aplicada"] == "RETRY_FROM_CHECKPOINT"
    assert evidencia["acciones_omitidas"] == ["uno", "dos"]
    assert evidencia["acciones_ejecutadas"] == ["tres"]
    assert evidencia["posicion_reanudacion"] == 3


def test_mismatch_checkpoint_hace_fallar_retry_y_run(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    tarea, _, cp = _interrumpida(orquestador, tmp_path)
    preparado = orquestador.preparar_reintento(tarea.task_id, cp.checkpoint_id)
    fake = EjecutorCicloFake(
        capacidad_checkpoint=CapacidadCheckpoint.CHECKPOINT_RESUME,
        checkpoint_utilizado=str(uuid4()),
    )

    resultado = orquestador.ejecutar_reintento(preparado.datos["retry_id"], ejecutor=fake)

    assert not resultado.ok and resultado.codigo == "RETRY_FAILED"
    run = orquestador._arranque.gestor_runs.obtener_run(resultado.run_id)
    assert run.estado_interno is EstadoInternoRun.FALLIDO
    assert run.resultado.metadata["ejecucion"]["tipo_error"] == "RETRY_EVIDENCE_INVALID"


def test_full_run_only_no_afirma_reutilizar_checkpoint(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    tarea, _, cp = _interrumpida(
        orquestador, tmp_path, capacidad=CapacidadCheckpoint.FULL_RUN_ONLY
    )
    preparado = orquestador.preparar_reintento(tarea.task_id, cp.checkpoint_id)
    resultado = orquestador.ejecutar_reintento(
        preparado.datos["retry_id"],
        ejecutor=EjecutorCicloFake(capacidad_checkpoint=CapacidadCheckpoint.FULL_RUN_ONLY),
    )
    evidencia = orquestador._arranque.gestor_runs.obtener_run(
        resultado.run_id
    ).resultado.metadata["ejecucion"]["evidencia_retry"]
    assert resultado.ok
    assert preparado.datos["estrategia"] == "RETRY_FULL_RUN"
    assert evidencia["checkpoint_id_utilizado"] is None
    assert evidencia["acciones_omitidas"] == []


def test_capacidad_none_rechaza_retry_desde_fachada(tmp_path):
    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    tarea, _, cp = _interrumpida(
        orquestador, tmp_path, capacidad=CapacidadCheckpoint.NONE
    )
    resultado = orquestador.preparar_reintento(tarea.task_id, cp.checkpoint_id)
    assert resultado.codigo == "RETRY_NOT_SUPPORTED"
    assert not resultado.ok


def test_retry_context_llega_al_ejecutor_y_doble_llamada_es_idempotente(tmp_path):
    capturados = []

    class FakeCaptura(EjecutorCicloFake):
        def construir_contexto_retry(self, contexto: ContextoRetryEjecutor):
            capturados.append(contexto)
            return super().construir_contexto_retry(contexto)

    orquestador, _ = _orquestador(tmp_path)
    orquestador.iniciar()
    tarea, _, cp = _interrumpida(orquestador, tmp_path)
    preparado = orquestador.preparar_reintento(tarea.task_id, cp.checkpoint_id)
    fake = FakeCaptura(capacidad_checkpoint=CapacidadCheckpoint.CHECKPOINT_RESUME)
    primero = orquestador.ejecutar_reintento(preparado.datos["retry_id"], ejecutor=fake)
    segundo = orquestador.ejecutar_reintento(preparado.datos["retry_id"], ejecutor=fake)
    assert primero.ok and segundo.ok
    assert segundo.datos["idempotente"] is True
    assert capturados[0].checkpoint_id == cp.checkpoint_id
    assert capturados[0].acciones_pendientes == ("tres",)
    assert len(fake.llamadas) == 1
