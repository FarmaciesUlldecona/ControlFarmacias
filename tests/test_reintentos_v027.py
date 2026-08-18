import json
from pathlib import Path
import subprocess
from uuid import UUID

import pytest

from arranque import EstadoGlobalOrquestador, ServicioArranque
from ejecucion_v02 import EjecutorCicloFake, ServicioEjecucionRuns
from reintentos_persistentes import (
    EstadoReintento,
    EstrategiaReintento,
    ServicioReintentos,
)
from runs_persistentes import EstadoInternoRun
from tareas_persistentes import (
    CapacidadCheckpoint,
    EstadoTarea,
    ModoTarea,
    crear_contrato,
)


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _crear_tarea(servicio, tmp_path, capacidad, nombre="repo"):
    repo = tmp_path / nombre
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "base")
    tarea = servicio.gestor_tareas.crear_tarea(
        orden_original="fake",
        repo=str(repo),
        worktree=str(repo),
        rama="main",
        commit_inicial=_git(repo, "rev-parse", "HEAD"),
        modo=ModoTarea.READ_ONLY,
        contrato=crear_contrato(objetivo="retry", condiciones_finalizacion="revisar"),
        capacidad_checkpoint=capacidad,
    )
    servicio.gestor_entornos.reservar_worktree(tarea.id)
    return repo, tarea


def _interrumpida(
    servicio,
    tmp_path,
    capacidad=CapacidadCheckpoint.CHECKPOINT_RESUME,
    *,
    checkpoint=True,
    validado=True,
    nombre="repo",
):
    repo, tarea = _crear_tarea(servicio, tmp_path, capacidad, nombre)
    run = servicio.gestor_runs.preparar_run(tarea.id).run
    servicio.gestor_runs.iniciar_run(run.run_id)
    cp = None
    if checkpoint:
        cp = servicio.gestor_checkpoints.registrar_checkpoint(
            task_id=tarea.id,
            run_id=run.run_id,
            tipo="LOTE_VALIDADO",
            payload={
                "acciones_completadas": ["lote-1", "lote-2"],
                "acciones_pendientes": ["lote-3"],
                "unidades_pendientes": 1,
            },
            metadata={"utilizable": True},
            validado=validado,
        )
    servicio.gestor_runs.registrar_resultado(
        run.run_id, EstadoInternoRun.INTERRUMPIDO, resumen="crash"
    )
    return repo, tarea, servicio.gestor_runs.obtener_run(run.run_id), cp


def _listo(tmp_path, capacidad=CapacidadCheckpoint.CHECKPOINT_RESUME, **kwargs):
    servicio = ServicioArranque(tmp_path)
    datos = _interrumpida(servicio, tmp_path, capacidad, **kwargs)
    assert servicio.iniciar_orquestador().estado_global is EstadoGlobalOrquestador.LISTO
    return servicio, datos


def test_checkpoint_validado_seleccionable_y_plan_tipado(tmp_path):
    servicio, (_, tarea, run, cp) = _listo(tmp_path)

    resultado = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id)

    assert resultado.exito
    assert str(UUID(resultado.retry.retry_id)) == resultado.retry.retry_id
    assert resultado.retry.run_origen == run.run_id
    assert resultado.retry.checkpoint_id == cp.checkpoint_id
    assert resultado.retry.estado is EstadoReintento.PREPARADO
    assert resultado.retry.acciones_omitidas == ("lote-1", "lote-2")
    assert resultado.retry.acciones_pendientes == ("lote-3",)
    assert resultado.retry.unidades_pendientes == 1


def test_checkpoint_no_validado_explicito_se_rechaza(tmp_path):
    servicio, (_, tarea, _, cp) = _listo(tmp_path, validado=False)
    resultado = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id)
    assert not resultado.exito
    assert resultado.codigo == "INVALID_CHECKPOINT"
    assert "no validado" in resultado.errores[0]


def test_checkpoint_de_otra_tarea_se_rechaza(tmp_path):
    servicio = ServicioArranque(tmp_path)
    _, tarea_a, _, _ = _interrumpida(servicio, tmp_path, nombre="a")
    _, _, _, cp_b = _interrumpida(servicio, tmp_path, nombre="b")
    servicio.iniciar_orquestador()

    resultado = servicio.servicio_reintentos.preparar_reintento(
        tarea_a.id, cp_b.checkpoint_id
    )

    assert resultado.codigo == "INVALID_CHECKPOINT"
    assert "otra tarea" in resultado.errores[0]


def test_sin_checkpoint_id_elige_ultimo_validado_y_omite_no_validado(tmp_path):
    servicio = ServicioArranque(tmp_path)
    _, tarea, run, primero = _interrumpida(servicio, tmp_path)
    ultimo_no_valido = servicio.gestor_checkpoints.registrar_checkpoint(
        task_id=tarea.id, run_id=run.run_id, tipo="BORRADOR", validado=False
    )
    servicio.iniciar_orquestador()

    resultado = servicio.servicio_reintentos.preparar_reintento(tarea.id)

    assert resultado.retry.checkpoint_id == primero.checkpoint_id
    assert resultado.retry.checkpoint_id != ultimo_no_valido.checkpoint_id


@pytest.mark.parametrize(
    ("capacidad", "estrategia", "exito"),
    [
        (CapacidadCheckpoint.CHECKPOINT_RESUME, EstrategiaReintento.RETRY_FROM_CHECKPOINT, True),
        (CapacidadCheckpoint.FULL_RUN_ONLY, EstrategiaReintento.RETRY_FULL_RUN, True),
        (CapacidadCheckpoint.NONE, None, False),
    ],
)
def test_distingue_capacidad_y_estrategia(tmp_path, capacidad, estrategia, exito):
    servicio, (_, tarea, _, cp) = _listo(tmp_path, capacidad)
    resultado = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id)
    assert resultado.exito is exito
    if exito:
        assert resultado.retry.estrategia is estrategia
        assert resultado.retry.repite_trabajo is (estrategia is EstrategiaReintento.RETRY_FULL_RUN)
    else:
        assert resultado.codigo == "RETRY_NOT_SUPPORTED"


def test_checkpoint_resume_sin_checkpoint_cae_a_full_run_explicito(tmp_path):
    servicio, (_, tarea, _, _) = _listo(tmp_path, checkpoint=False)
    resultado = servicio.servicio_reintentos.preparar_reintento(tarea.id)
    assert resultado.retry.estrategia is EstrategiaReintento.RETRY_FULL_RUN
    assert resultado.retry.checkpoint_id is None
    assert resultado.retry.repite_trabajo


def test_retry_persiste_y_se_recupera_con_instancia_nueva(tmp_path):
    servicio, (_, tarea, _, cp) = _listo(tmp_path)
    creado = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id).retry
    reiniciado = ServicioReintentos(
        servicio.gestor_tareas,
        servicio.gestor_entornos,
        servicio.gestor_runs,
        servicio.gestor_checkpoints,
        tmp_path / "estado" / "retries",
    )
    assert reiniciado.obtener_reintento(creado.retry_id) == creado
    assert reiniciado.listar_reintentos(tarea.id) == [creado]
    datos = json.loads((tmp_path / "estado" / "retries" / f"{creado.retry_id}.json").read_text(encoding="utf-8"))
    assert datos["run_origen"] == creado.run_origen


def test_preparar_dos_veces_reutiliza_mismo_retry(tmp_path):
    servicio, (_, tarea, _, cp) = _listo(tmp_path)
    primero = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id)
    segundo = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id)
    assert segundo.idempotente
    assert segundo.retry.retry_id == primero.retry.retry_id
    assert len(servicio.servicio_reintentos.listar_reintentos(tarea.id)) == 1


@pytest.mark.parametrize(
    "capacidad",
    [CapacidadCheckpoint.CHECKPOINT_RESUME, CapacidadCheckpoint.FULL_RUN_ONLY],
)
def test_ejecutar_retry_crea_nuevo_run_trazable(tmp_path, capacidad):
    servicio, (_, tarea, origen, cp) = _listo(tmp_path, capacidad)
    plan = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id).retry
    fake = EjecutorCicloFake()

    resultado = servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, fake)

    assert resultado.exito
    assert resultado.retry.estado is EstadoReintento.COMPLETADO
    assert resultado.run.task_id == tarea.id
    assert resultado.run.run_id != origen.run_id
    assert resultado.run.retry_de == origen.run_id
    assert resultado.run.retry_id == plan.retry_id
    assert resultado.run.checkpoint_id == cp.checkpoint_id
    assert resultado.run.numero_intento == origen.numero_intento + 1
    assert len(fake.llamadas) == 1
    if capacidad is CapacidadCheckpoint.CHECKPOINT_RESUME:
        assert resultado.run.retry_context["estrategia"] == "RETRY_FROM_CHECKPOINT"
        assert resultado.run.retry_context["acciones_omitidas"] == ["lote-1", "lote-2"]
    else:
        assert resultado.run.retry_context["estrategia"] == "RETRY_FULL_RUN"
        assert resultado.run.retry_context["acciones_omitidas"] == []


def test_ejecutar_retry_dos_veces_no_duplica_run_ni_ejecutor(tmp_path):
    servicio, (_, tarea, _, cp) = _listo(tmp_path)
    plan = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id).retry
    fake = EjecutorCicloFake()
    primero = servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, fake)
    segundo = servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, fake)
    assert segundo.exito and segundo.idempotente
    assert segundo.run.run_id == primero.run.run_id
    assert len(fake.llamadas) == 1
    assert len(servicio.gestor_runs.listar_runs_tarea(tarea.id)) == 2


def test_retry_cancelado_no_ejecuta_y_cancelar_es_idempotente(tmp_path):
    servicio, (_, tarea, _, cp) = _listo(tmp_path)
    plan = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id).retry
    primero = servicio.servicio_reintentos.cancelar_reintento(plan.retry_id)
    segundo = servicio.servicio_reintentos.cancelar_reintento(plan.retry_id)
    fake = EjecutorCicloFake()
    ejecucion = servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, fake)
    assert primero.retry.estado is EstadoReintento.CANCELADO
    assert segundo.idempotente
    assert ejecucion.codigo == "RETRY_CANCELLED"
    assert fake.llamadas == []


def test_run_posterior_exitoso_impide_ejecutar_plan_preparado(tmp_path):
    servicio, (_, tarea, _, cp) = _listo(tmp_path)
    plan = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id).retry
    posterior = servicio.gestor_runs.preparar_run(tarea.id).run
    ServicioEjecucionRuns(servicio.gestor_runs).ejecutar_run(
        posterior.run_id, EjecutorCicloFake()
    )
    fake = EjecutorCicloFake()

    resultado = servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, fake)

    assert resultado.codigo == "LATER_SUCCESS_EXISTS"
    assert resultado.retry.estado is EstadoReintento.FALLIDO
    assert fake.llamadas == []


def test_retry_fallido_se_persiste_y_no_se_repite(tmp_path):
    servicio, (_, tarea, _, cp) = _listo(tmp_path)
    plan = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id).retry
    fake = EjecutorCicloFake(return_code=9, stderr="fallo")
    primero = servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, fake)
    segundo = servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, fake)
    assert not primero.exito
    assert primero.retry.estado is EstadoReintento.FALLIDO
    assert segundo.codigo == "RETRY_FAILED"
    assert len(fake.llamadas) == 1


def test_run_completo_no_genera_retry_innecesario(tmp_path):
    servicio = ServicioArranque(tmp_path)
    _, tarea = _crear_tarea(servicio, tmp_path, CapacidadCheckpoint.FULL_RUN_ONLY)
    run = servicio.gestor_runs.preparar_run(tarea.id).run
    ServicioEjecucionRuns(servicio.gestor_runs).ejecutar_run(run.run_id, EjecutorCicloFake())
    servicio.iniciar_orquestador()
    resultado = servicio.servicio_reintentos.preparar_reintento(tarea.id)
    assert resultado.codigo == "NO_INTERRUPTED_RUN"


def test_tarea_terminal_no_genera_retry(tmp_path):
    servicio, (_, tarea, _, cp) = _listo(tmp_path)
    servicio.gestor_tareas.actualizar_estado(tarea.id, EstadoTarea.CANCELADA)
    resultado = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id)
    assert resultado.codigo == "TERMINAL_TASK"


@pytest.mark.parametrize("alteracion", ["lock", "branch", "head", "missing"])
def test_entorno_invalido_impide_preparar_retry(tmp_path, alteracion):
    servicio, (repo, tarea, _, cp) = _listo(tmp_path)
    if alteracion == "lock":
        next(servicio.gestor_entornos.directorio_locks.glob("*.json")).unlink()
    elif alteracion == "branch":
        _git(repo, "checkout", "-b", "otra")
    elif alteracion == "head":
        (repo / "nuevo.txt").write_text("x", encoding="utf-8")
        _git(repo, "add", "nuevo.txt")
        _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "otro")
    else:
        repo.rename(tmp_path / "movido")

    resultado = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id)

    assert resultado.codigo == "INVALID_ENVIRONMENT"


def test_ejecutar_retry_rechaza_orquestador_no_listo(tmp_path):
    servicio = ServicioArranque(tmp_path)
    _, tarea, _, cp = _interrumpida(servicio, tmp_path)
    plan = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id).retry
    resultado = servicio.servicio_reintentos.ejecutar_reintento(
        plan.retry_id, EjecutorCicloFake()
    )
    assert resultado.codigo == "ORCHESTRATOR_NOT_READY"


def test_historial_retry_es_completo_y_sin_eventos_duplicados(tmp_path):
    servicio, (_, tarea, _, cp) = _listo(tmp_path)
    plan = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id).retry
    servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, EjecutorCicloFake())
    servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, EjecutorCicloFake())
    eventos = [
        (e.tipo, json.dumps(e.datos, sort_keys=True))
        for e in servicio.gestor_tareas.cargar(tarea.id).historial
        if e.tipo.startswith("RETRY_")
    ]
    tipos = [tipo for tipo, _ in eventos]
    assert "RETRY_PREPARED" in tipos
    assert "RETRY_FROM_CHECKPOINT" in tipos
    assert "RETRY_STARTED" in tipos
    assert "RETRY_COMPLETED" in tipos
    assert len(eventos) == len(set(eventos))


def test_capacidad_checkpoint_persiste_en_tarea_y_run(tmp_path):
    servicio, (_, tarea, run, _) = _listo(tmp_path)
    recargada = servicio.gestor_tareas.cargar(tarea.id)
    assert recargada.capacidad_checkpoint is CapacidadCheckpoint.CHECKPOINT_RESUME
    assert run.capacidad_checkpoint is CapacidadCheckpoint.CHECKPOINT_RESUME
