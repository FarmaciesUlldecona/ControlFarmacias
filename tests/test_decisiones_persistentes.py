import json
import subprocess
from uuid import UUID, uuid4

import pytest

from decisiones_persistentes import (
    ConflictoDecisionPendiente,
    DecisionInvalida,
    EstadoDecision,
    GestorDecisiones,
    TipoDecision,
)
from ejecucion_v02 import (
    EjecutorCicloFake,
    ErrorReanudacionDecision,
    ServicioDecisiones,
    ServicioEjecucionRuns,
)
from entornos import GestorEntornos
from runs_persistentes import EstadoInternoRun, GestorRuns
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


def _crear_tarea(tareas, repo, head):
    return tareas.crear_tarea(
        orden_original="Ejecuta pausa y resume fake",
        repo=str(repo),
        worktree=str(repo),
        rama="main",
        commit_inicial=head,
        modo=ModoTarea.READ_ONLY,
        contrato=crear_contrato(
            objetivo="Validar decisiones persistentes",
            condiciones_finalizacion="Resume verificado",
        ),
    )


def _contexto(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo, head = _repo(tmp_path)
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    entornos = GestorEntornos(tareas, tmp_path / "estado" / "locks")
    runs = GestorRuns(tareas, entornos, tmp_path / "runs")
    decisiones = GestorDecisiones(
        tareas, runs, tmp_path / "estado" / "decisiones"
    )
    servicio_runs = ServicioEjecucionRuns(runs, decisiones)
    servicio_decisiones = ServicioDecisiones(decisiones, runs)
    tarea = _crear_tarea(tareas, repo, head)
    entornos.reservar_worktree(tarea.id)
    run = runs.preparar_run(tarea.id).run
    return (
        repo,
        tareas,
        entornos,
        runs,
        decisiones,
        servicio_runs,
        servicio_decisiones,
        tarea,
        run,
    )


def _pausar(tmp_path, estado=EstadoInternoRun.REQUIERE_OK_PIO, causa="decisión"):
    contexto = _contexto(tmp_path)
    servicio_runs = contexto[5]
    run = contexto[8]
    completada = servicio_runs.ejecutar_run(
        run.run_id,
        EjecutorCicloFake(
            estado,
            resumen="Pio debe decidir",
            causa_pausa=causa,
        ),
    )
    return contexto, completada


def test_requiere_ok_crea_decision_persistente_y_trazable(tmp_path):
    contexto, completada = _pausar(tmp_path)
    _, tareas, _, _, decisiones, _, _, tarea, run = contexto
    decision = completada.decision

    assert decision is not None
    assert str(UUID(decision.decision_id)) == decision.decision_id
    assert decision.task_id == tarea.id
    assert decision.run_id == run.run_id
    assert decision.estado is EstadoDecision.PENDIENTE
    assert tareas.cargar(tarea.id).estado is EstadoTarea.ESPERANDO_DECISION
    assert decisiones.obtener_decision_pendiente(tarea.id) == decision
    assert decisiones.listar_decisiones(tarea.id) == [decision]
    assert tareas.cargar(tarea.id).historial[-1].tipo == "DECISION_REQUIRED"


def test_pausa_pio_humana_crea_decision_y_barrera_no(tmp_path):
    _, humana = _pausar(tmp_path / "humana", EstadoInternoRun.PAUSA_PIO, "revisión humana")
    _, barrera = _pausar(tmp_path / "barrera", EstadoInternoRun.PAUSA_PIO, "barrera de integridad")

    assert humana.decision is not None
    assert humana.resultado.estado_v02_propuesto is EstadoTarea.ESPERANDO_DECISION
    assert barrera.decision is None
    assert barrera.resultado.estado_v02_propuesto is EstadoTarea.BLOQUEADA


def test_decision_sobrevive_nueva_instancia_y_conserva_json(tmp_path):
    contexto, completada = _pausar(tmp_path)
    _, tareas, _, runs, decisiones, _, _, tarea, _ = contexto
    decision = completada.decision
    nueva = GestorDecisiones(tareas, runs, decisiones.directorio)
    datos = json.loads(
        (decisiones.directorio / f"{decision.decision_id}.json").read_text(
            encoding="utf-8"
        )
    )

    assert nueva.obtener_decision(decision.decision_id) == decision
    assert nueva.obtener_decision_pendiente(tarea.id) == decision
    assert datos["task_id"] == tarea.id
    assert datos["run_id"] == decision.run_id


@pytest.mark.parametrize("tipo", list(TipoDecision))
def test_tipos_de_decision_se_representan(tmp_path, tipo):
    contexto = _contexto(tmp_path)
    _, _, _, runs, decisiones, _, _, tarea, run = contexto
    run_iniciado = runs.iniciar_run(run.run_id)
    runs.registrar_resultado(
        run_iniciado.run_id,
        EstadoInternoRun.REQUIERE_OK_PIO,
        resumen="elige",
    )

    decision = decisiones.crear_decision(
        task_id=tarea.id,
        run_id=run.run_id,
        tipo=tipo,
        pregunta="¿Continuar?",
        impacto={"alcance": "representación"},
        autorizaciones=(tipo.value,),
    )

    assert decision.tipo is tipo
    assert decision.autorizaciones == (tipo.value,)


def test_opcion_cerrada_valida_y_rechaza_ambigua(tmp_path):
    contexto = _contexto(tmp_path)
    _, tareas, _, runs, decisiones, _, _, tarea, run = contexto
    run = runs.iniciar_run(run.run_id)
    runs.registrar_resultado(
        run.run_id, EstadoInternoRun.REQUIERE_OK_PIO, resumen="elige"
    )
    decision = decisiones.crear_decision(
        task_id=tarea.id,
        run_id=run.run_id,
        pregunta="Elige A o B",
        opciones_permitidas=("A", "B"),
    )

    with pytest.raises(DecisionInvalida, match="opción no permitida"):
        decisiones.responder_decision(decision.decision_id, opcion="C")

    respondida = decisiones.responder_decision(decision.decision_id, opcion="A")
    tipos = [evento.tipo for evento in tareas.cargar(tarea.id).historial]
    assert respondida.estado is EstadoDecision.RESPONDIDA
    assert respondida.respuesta == {"opcion": "A", "texto": None}
    assert "DECISION_REJECTED" in tipos
    assert tipos[-1] == "DECISION_RECEIVED"


def test_texto_estructurado_se_persiste_sin_interpretacion(tmp_path):
    contexto, completada = _pausar(tmp_path)
    decisiones = contexto[4]

    respondida = decisiones.responder_decision(
        completada.decision.decision_id,
        texto="Continuar únicamente con la comprobación aprobada",
        metadata_respuesta={"origen": "PIO"},
    )

    assert respondida.respuesta == {
        "opcion": None,
        "texto": "Continuar únicamente con la comprobación aprobada",
        "metadata": {"origen": "PIO"},
    }


def test_respuesta_valida_reanuda_automaticamente_in_process(tmp_path):
    contexto, completada = _pausar(tmp_path)
    _, tareas, _, runs, decisiones, _, servicio, tarea, run_origen = contexto
    fake_resume = EjecutorCicloFake(EstadoInternoRun.AUTO_CONTINUE)

    resultado = servicio.responder_y_reanudar(
        completada.decision.decision_id,
        fake_resume,
        texto="Continuar de forma controlada",
    )

    assert resultado.aplicada_ahora
    assert not resultado.idempotente
    assert resultado.run.task_id == tarea.id
    assert resultado.run.run_id != run_origen.run_id
    assert resultado.run.numero_intento == 2
    assert resultado.run.resume_de == run_origen.run_id
    assert resultado.run.decision_id == completada.decision.decision_id
    assert runs.contar_ciclos(tarea.id) == 2
    assert decisiones.obtener_decision(completada.decision.decision_id).estado is EstadoDecision.APLICADA
    assert tareas.cargar(tarea.id).estado is EstadoTarea.TRABAJANDO
    assert fake_resume.llamadas == [(resultado.run.run_id, tarea.id)]
    tipos = [evento.tipo for evento in tareas.cargar(tarea.id).historial]
    assert "RUN_RESUMED" in tipos
    assert tipos[-1] == "DECISION_APPLIED"


def test_aplicar_dos_veces_es_idempotente_y_no_repite_ejecutor(tmp_path):
    contexto, completada = _pausar(tmp_path)
    decisiones, servicio = contexto[4], contexto[6]
    fake = EjecutorCicloFake()
    decisiones.responder_decision(completada.decision.decision_id, texto="Continúa")

    primera = servicio.aplicar_decision(completada.decision.decision_id, fake)
    segunda = servicio.aplicar_decision(completada.decision.decision_id, fake)

    assert primera.aplicada_ahora
    assert segunda.idempotente
    assert not segunda.aplicada_ahora
    assert primera.run.run_id == segunda.run.run_id
    assert len(fake.llamadas) == 1


@pytest.mark.parametrize("campo", ["task", "run"])
def test_decision_ajena_o_run_incorrecto_no_reanuda(tmp_path, campo):
    contexto, completada = _pausar(tmp_path)
    tareas, decisiones, servicio = contexto[1], contexto[4], contexto[6]
    fake = EjecutorCicloFake()
    decisiones.responder_decision(completada.decision.decision_id, texto="Continúa")
    kwargs = (
        {"task_id_esperado": str(uuid4())}
        if campo == "task"
        else {"run_id_esperado": str(uuid4())}
    )

    with pytest.raises(ErrorReanudacionDecision):
        servicio.aplicar_decision(completada.decision.decision_id, fake, **kwargs)

    assert fake.llamadas == []
    assert tareas.cargar(completada.decision.task_id).historial[-1].tipo == "RESUME_PRECONDITION_FAILED"


def test_no_resume_sin_lock(tmp_path):
    contexto, completada = _pausar(tmp_path)
    entornos, decisiones, servicio = contexto[2], contexto[4], contexto[6]
    fake = EjecutorCicloFake()
    decisiones.responder_decision(completada.decision.decision_id, texto="Continúa")
    next(entornos.directorio_locks.glob("*.json")).unlink()

    with pytest.raises(ErrorReanudacionDecision, match="sin lock"):
        servicio.aplicar_decision(completada.decision.decision_id, fake)

    assert fake.llamadas == []


def test_no_resume_con_branch_incompatible(tmp_path):
    contexto, completada = _pausar(tmp_path)
    repo, decisiones, servicio = contexto[0], contexto[4], contexto[6]
    fake = EjecutorCicloFake()
    decisiones.responder_decision(completada.decision.decision_id, texto="Continúa")
    _git(repo, "branch", "otra")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/otra")

    with pytest.raises(ErrorReanudacionDecision, match="rama distinta"):
        servicio.aplicar_decision(completada.decision.decision_id, fake)

    assert fake.llamadas == []


def test_no_resume_con_head_incompatible(tmp_path):
    contexto, completada = _pausar(tmp_path)
    repo, decisiones, servicio = contexto[0], contexto[4], contexto[6]
    fake = EjecutorCicloFake()
    decisiones.responder_decision(completada.decision.decision_id, texto="Continúa")
    (repo / "otro_head.txt").write_text("cambio externo\n", encoding="utf-8")
    _git(repo, "add", "otro_head.txt")
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

    with pytest.raises(ErrorReanudacionDecision, match="HEAD distinto"):
        servicio.aplicar_decision(completada.decision.decision_id, fake)

    assert fake.llamadas == []


def test_no_resume_tarea_terminal(tmp_path):
    contexto, completada = _pausar(tmp_path)
    tareas, decisiones, servicio, tarea = contexto[1], contexto[4], contexto[6], contexto[7]
    fake = EjecutorCicloFake()
    decisiones.responder_decision(completada.decision.decision_id, texto="Continúa")
    tareas.actualizar_estado(tarea.id, EstadoTarea.CANCELADA)

    with pytest.raises(ErrorReanudacionDecision, match="terminal"):
        servicio.aplicar_decision(completada.decision.decision_id, fake)

    assert fake.llamadas == []


def test_cancelar_decision_no_reanuda_y_no_cancela_tarea(tmp_path):
    contexto, completada = _pausar(tmp_path)
    tareas, servicio, tarea = contexto[1], contexto[6], contexto[7]
    fake = EjecutorCicloFake()

    cancelada = servicio.cancelar_decision(completada.decision.decision_id)

    assert cancelada.estado is EstadoDecision.CANCELADA
    assert tareas.cargar(tarea.id).estado is EstadoTarea.ESPERANDO_DECISION
    assert tareas.cargar(tarea.id).historial[-1].tipo == "DECISION_CANCELLED"
    assert fake.llamadas == []


def test_multiples_pausas_secuenciales_generan_decisiones_distintas(tmp_path):
    contexto, primera_ejecucion = _pausar(tmp_path)
    tareas, decisiones, servicio, tarea = contexto[1], contexto[4], contexto[6], contexto[7]
    fake_segunda_pausa = EjecutorCicloFake(
        EstadoInternoRun.REQUIERE_OK_PIO,
        resumen="Segunda decisión",
    )

    primera_aplicacion = servicio.responder_y_reanudar(
        primera_ejecucion.decision.decision_id,
        fake_segunda_pausa,
        texto="Avanza al siguiente punto",
    )
    segunda = decisiones.obtener_decision_pendiente(tarea.id)

    assert primera_aplicacion.run.numero_intento == 2
    assert segunda is not None
    assert segunda.decision_id != primera_ejecucion.decision.decision_id
    assert segunda.run_id == primera_aplicacion.run.run_id
    assert decisiones.obtener_decision(primera_ejecucion.decision.decision_id).estado is EstadoDecision.APLICADA
    assert tareas.cargar(tarea.id).estado is EstadoTarea.ESPERANDO_DECISION
    assert len(
        [
            item
            for item in decisiones.listar_decisiones(tarea.id)
            if item.estado is EstadoDecision.PENDIENTE
        ]
    ) == 1


def test_no_duplica_decision_para_la_misma_pausa(tmp_path):
    contexto, completada = _pausar(tmp_path)
    decisiones, tarea = contexto[4], contexto[7]

    repetida = decisiones.crear_decision(
        task_id=tarea.id,
        run_id=completada.resultado.run_id,
        pregunta="Pregunta duplicada",
    )

    assert repetida.decision_id == completada.decision.decision_id
    assert len(decisiones.listar_decisiones(tarea.id)) == 1


def test_no_permite_resume_manual_con_decision_pendiente(tmp_path):
    contexto, completada = _pausar(tmp_path)
    runs, tarea = contexto[3], contexto[7]

    preparacion = runs.preparar_resume(
        tarea.id,
        completada.resultado.run_id,
        "texto manual no validado",
    )

    assert not preparacion.exito
    assert "decisión estructurada pendiente" in preparacion.errores[-1]
    assert runs.contar_ciclos(tarea.id) == 1


def test_decision_aplicada_se_recupera_tras_reinicio(tmp_path):
    contexto, completada = _pausar(tmp_path)
    tareas, entornos, runs, decisiones, servicio = (
        contexto[1],
        contexto[2],
        contexto[3],
        contexto[4],
        contexto[6],
    )
    resultado = servicio.responder_y_reanudar(
        completada.decision.decision_id,
        EjecutorCicloFake(),
        texto="Continúa",
    )
    runs_nuevo = GestorRuns(tareas, entornos, runs.directorio_runs)
    decisiones_nuevo = GestorDecisiones(tareas, runs_nuevo, decisiones.directorio)

    recuperada = decisiones_nuevo.obtener_decision(completada.decision.decision_id)
    assert recuperada.estado is EstadoDecision.APLICADA
    assert recuperada.resume_run_id == resultado.run.run_id
    assert runs_nuevo.obtener_run(resultado.run.run_id).decision_id == recuperada.decision_id
