import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import orquestador
from ejecucion_v02 import (
    EjecucionRealProhibida,
    EjecutorCicloFake,
    EjecutorCicloReal,
    ServicioDecisiones,
    ServicioEjecucionRuns,
)
from entornos import GestorEntornos
from runs_persistentes import EstadoInternoRun, EstadoRunInvalido, GestorRuns
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


def _contexto(tmp_path, nombre="repo", modo=ModoTarea.READ_ONLY):
    repo, head = _repo(tmp_path, nombre)
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    entornos = GestorEntornos(tareas, tmp_path / "estado" / "locks")
    runs = GestorRuns(tareas, entornos, tmp_path / "runs")
    contrato = crear_contrato(
        objetivo="Ciclo fake seguro",
        rutas_permitidas=["permitido/**"] if modo is ModoTarea.WORKSPACE_WRITE else [],
        rutas_protegidas=[".env"],
        condiciones_finalizacion="Resultado revisado",
    )
    tarea = tareas.crear_tarea(
        orden_original="Ejecuta el ciclo inyectado",
        repo=str(repo),
        worktree=str(repo),
        rama="main",
        commit_inicial=head,
        modo=modo,
        contrato=contrato,
    )
    entornos.reservar_worktree(tarea.id)
    preparacion = runs.preparar_run(tarea.id)
    assert preparacion.exito
    return repo, tareas, entornos, runs, tarea, preparacion.run


def test_crear_run_no_lanza_ejecutor_y_fake_se_invoca_una_vez(tmp_path):
    _, tareas, _, runs, tarea, run = _contexto(tmp_path)
    fake = EjecutorCicloFake(stdout="stdout fake", stderr="stderr fake")
    servicio = ServicioEjecucionRuns(runs)

    completada = servicio.ejecutar_run(run.run_id, fake)

    assert fake.llamadas == [(run.run_id, tarea.id)]
    assert completada.salida.task_id == tarea.id
    assert completada.salida.run_id == run.run_id
    assert completada.resultado.estado_interno is EstadoInternoRun.AUTO_CONTINUE
    tipos = [evento.tipo for evento in tareas.cargar(tarea.id).historial]
    assert "RUN_STARTED" in tipos
    assert tipos[-1] == "RUN_COMPLETED"


def test_stdout_stderr_y_metadata_quedan_persistidos(tmp_path):
    _, tareas, entornos, runs, tarea, run = _contexto(tmp_path)
    servicio = ServicioEjecucionRuns(runs)
    servicio.ejecutar_run(
        run.run_id,
        EjecutorCicloFake(stdout="salida estándar\n", stderr="aviso\n"),
    )
    run_dir = Path(run.directorio_run)

    assert (run_dir / "stdout.txt").read_text(encoding="utf-8") == "salida estándar\n"
    assert (run_dir / "stderr.txt").read_text(encoding="utf-8") == "aviso\n"
    metadata = json.loads((run_dir / "execution.json").read_text(encoding="utf-8"))
    assert metadata["run_id"] == run.run_id
    assert metadata["task_id"] == tarea.id
    assert metadata["return_code"] == 0

    reiniciado = GestorRuns(tareas, entornos, tmp_path / "runs")
    assert reiniciado.obtener_run(run.run_id).resultado.run_id == run.run_id


@pytest.mark.parametrize(
    ("estado", "causa", "esperado", "evento"),
    [
        (EstadoInternoRun.AUTO_CONTINUE, "", EstadoTarea.TRABAJANDO, "RUN_COMPLETED"),
        (
            EstadoInternoRun.REQUIERE_OK_PIO,
            "decisión",
            EstadoTarea.ESPERANDO_DECISION,
            "RUN_PAUSED",
        ),
        (
            EstadoInternoRun.PAUSA_PIO,
            "barrera de integridad",
            EstadoTarea.BLOQUEADA,
            "RUN_PAUSED",
        ),
    ],
)
def test_traduce_resultados_funcionales(tmp_path, estado, causa, esperado, evento):
    _, tareas, _, runs, tarea, run = _contexto(tmp_path)

    completada = ServicioEjecucionRuns(runs).ejecutar_run(
        run.run_id,
        EjecutorCicloFake(estado, causa_pausa=causa),
    )

    assert completada.resultado.estado_v02_propuesto is esperado
    assert tareas.cargar(tarea.id).estado is esperado
    assert any(item.tipo == evento for item in tareas.cargar(tarea.id).historial)


def test_finalizado_solo_propone_cierre_validado(tmp_path):
    _, tareas, _, runs, tarea, run = _contexto(tmp_path)

    completada = ServicioEjecucionRuns(runs).ejecutar_run(
        run.run_id,
        EjecutorCicloFake(EstadoInternoRun.FINALIZADO),
        condiciones_funcionales_validadas=True,
    )

    assert completada.resultado.estado_v02_propuesto is EstadoTarea.FINALIZADA
    assert tareas.cargar(tarea.id).estado is EstadoTarea.TRABAJANDO


@pytest.mark.parametrize(
    ("fake", "tipo_error"),
    [
        (EjecutorCicloFake(excepcion=RuntimeError("fallo fake")), "EXECUTOR_EXCEPTION"),
        (
            EjecutorCicloFake(return_code=17, stderr="error proceso", resumen="falló"),
            None,
        ),
        (
            EjecutorCicloFake(
                timeout=True,
                timeout_seconds=321,
                tipo_error="CODEX_TIMEOUT",
                errores=("timeout",),
            ),
            "CODEX_TIMEOUT",
        ),
    ],
)
def test_fallos_tecnicos_producen_run_failed_y_conservan_lock(
    tmp_path, fake, tipo_error
):
    repo, tareas, entornos, runs, tarea, run = _contexto(tmp_path)

    completada = ServicioEjecucionRuns(runs).ejecutar_run(run.run_id, fake)

    assert completada.resultado.estado_interno is EstadoInternoRun.FALLIDO
    assert completada.resultado.estado_v02_propuesto is EstadoTarea.BLOQUEADA
    assert tareas.cargar(tarea.id).estado is EstadoTarea.BLOQUEADA
    assert any(evento.tipo == "RUN_FAILED" for evento in tareas.cargar(tarea.id).historial)
    assert entornos.obtener_reserva(repo).task_id == tarea.id
    if tipo_error:
        assert completada.salida.tipo_error == tipo_error


def test_no_ejecuta_sin_lock_valido(tmp_path):
    _, _, entornos, runs, _, run = _contexto(tmp_path)
    next(entornos.directorio_locks.glob("*.json")).unlink()
    fake = EjecutorCicloFake()

    with pytest.raises(EstadoRunInvalido, match="sin lock"):
        ServicioEjecucionRuns(runs).ejecutar_run(run.run_id, fake)

    assert fake.llamadas == []


def test_no_ejecuta_con_entorno_invalido(tmp_path):
    repo, _, _, runs, _, run = _contexto(tmp_path)
    _git(repo, "branch", "otra")
    _git(repo, "symbolic-ref", "HEAD", "refs/heads/otra")
    fake = EjecutorCicloFake()

    with pytest.raises(EstadoRunInvalido, match="rama distinta"):
        ServicioEjecucionRuns(runs).ejecutar_run(run.run_id, fake)

    assert fake.llamadas == []


def test_no_ejecuta_tarea_terminal(tmp_path):
    _, tareas, _, runs, tarea, run = _contexto(tmp_path)
    tareas.actualizar_estado(tarea.id, EstadoTarea.CANCELADA)
    fake = EjecutorCicloFake()

    with pytest.raises(EstadoRunInvalido, match="terminal"):
        ServicioEjecucionRuns(runs).ejecutar_run(run.run_id, fake)

    assert fake.llamadas == []


def test_no_ejecuta_dos_veces_un_run_completado(tmp_path):
    _, _, _, runs, _, run = _contexto(tmp_path)
    fake = EjecutorCicloFake()
    servicio = ServicioEjecucionRuns(runs)
    servicio.ejecutar_run(run.run_id, fake)

    with pytest.raises(EstadoRunInvalido):
        servicio.ejecutar_run(run.run_id, fake)

    assert len(fake.llamadas) == 1


def test_outputs_de_runs_distintos_no_se_mezclan(tmp_path):
    _, _, _, runs, tarea, primero = _contexto(tmp_path)
    servicio = ServicioEjecucionRuns(runs)
    servicio.ejecutar_run(primero.run_id, EjecutorCicloFake(stdout="PRIMERO"))
    segundo = runs.preparar_run(tarea.id).run
    servicio.ejecutar_run(segundo.run_id, EjecutorCicloFake(stdout="SEGUNDO"))

    assert (Path(primero.directorio_run) / "stdout.txt").read_text() == "PRIMERO"
    assert (Path(segundo.directorio_run) / "stdout.txt").read_text() == "SEGUNDO"


def test_fake_permite_resume_con_mismo_task_id(tmp_path):
    _, tareas, _, runs, tarea, primero = _contexto(tmp_path)
    servicio = ServicioEjecucionRuns(runs)
    pausa = servicio.ejecutar_run(
        primero.run_id,
        EjecutorCicloFake(EstadoInternoRun.REQUIERE_OK_PIO),
    )
    completada = ServicioDecisiones(
        servicio.gestor_decisiones, runs
    ).responder_y_reanudar(
        pausa.decision.decision_id,
        EjecutorCicloFake(),
        texto="Continúa seguro",
    )
    resume = completada.run

    assert completada.ejecucion.salida.task_id == tarea.id
    assert resume.resume_de == primero.run_id
    assert tareas.cargar(tarea.id).estado is EstadoTarea.TRABAJANDO


def test_desviacion_read_only_bloquea_aunque_fake_devuelva_exito(tmp_path):
    repo, tareas, _, runs, tarea, run = _contexto(tmp_path)

    class FakeQueEscribe(EjecutorCicloFake):
        def ejecutar(self, run_actual, tarea_actual):
            (Path(tarea_actual.worktree) / "intruso.txt").write_text("cambio")
            return super().ejecutar(run_actual, tarea_actual)

    completada = ServicioEjecucionRuns(runs).ejecutar_run(run.run_id, FakeQueEscribe())

    assert completada.resultado.estado_v02_propuesto is EstadoTarea.BLOQUEADA
    assert any("solo lectura" in error for error in completada.resultado.errores)
    assert tareas.cargar(tarea.id).estado is EstadoTarea.BLOQUEADA


def test_ejecutor_real_es_inyectable_y_llama_funcion_in_process(tmp_path, monkeypatch):
    _, _, _, runs, tarea, run = _contexto(tmp_path)
    llamadas = []

    def ciclo_falso(**kwargs):
        llamadas.append(kwargs)
        ciclo = kwargs["run_dir"] / "ciclo_01"
        ciclo.mkdir()
        (ciclo / "resultado_ejecutor.stdout.txt").write_text("real simulado")
        state = kwargs["state"]
        state["ciclo"] = 1
        state["status"] = "AUTO_CONTINUE"
        state["siguiente_instruccion"] = "continúa"
        return "AUTO_CONTINUE", state

    monkeypatch.setattr(orquestador, "ejecutar_ciclo", ciclo_falso)
    real = EjecutorCicloReal(
        Path(__file__).resolve().parents[1],
        {"timeout_seconds": 777},
        permitir_en_pytest=True,
    )

    completada = ServicioEjecucionRuns(runs).ejecutar_run(run.run_id, real)

    assert len(llamadas) == 1
    assert llamadas[0]["config"]["timeout_seconds"] == 777
    assert completada.salida.stdout.endswith("real simulado\n")
    assert "V0_1_3" not in json.dumps(completada.salida.procesos)


def test_pytest_bloquea_ejecutor_real_por_defecto(tmp_path):
    _, tareas, _, _, tarea, run = _contexto(tmp_path)
    real = EjecutorCicloReal(Path(__file__).resolve().parents[1], {})

    with pytest.raises(EjecucionRealProhibida):
        real.ejecutar(run, tareas.cargar(tarea.id))


def test_cli_historica_conserva_argumentos():
    entorno = dict(os.environ)
    entorno["PYTHONIOENCODING"] = "utf-8"
    resultado = subprocess.run(
        [sys.executable, str(Path(orquestador.__file__)), "--help"],
        check=True,
        capture_output=True,
        text=True,
        env=entorno,
    )

    for argumento in ("--task", "--resume", "--decision", "--check"):
        assert argumento in resultado.stdout


def test_motor_captura_pid_return_code_stdout_y_stderr(tmp_path):
    eventos = []

    resultado = orquestador.ejecutar(
        [
            sys.executable,
            "-c",
            "import sys; print('salida'); print('aviso', file=sys.stderr)",
        ],
        cwd=tmp_path,
        observador_proceso=lambda evento, datos: eventos.append((evento, datos)),
    )

    assert resultado.returncode == 0
    assert resultado.stdout.strip() == "salida"
    assert resultado.stderr.strip() == "aviso"
    assert [evento for evento, _ in eventos] == ["PROCESS_STARTED", "PROCESS_FINISHED"]
    assert eventos[0][1]["pid"] > 0
    assert eventos[-1][1]["returncode"] == 0


def test_motor_distingue_timeout_y_termina_proceso(tmp_path):
    eventos = []

    with pytest.raises(subprocess.TimeoutExpired):
        orquestador.ejecutar(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=tmp_path,
            timeout=0.05,
            observador_proceso=lambda evento, datos: eventos.append((evento, datos)),
        )

    assert [evento for evento, _ in eventos] == ["PROCESS_STARTED", "PROCESS_TIMEOUT"]
    assert eventos[-1][1]["terminacion"] in {"terminate", "kill_after_terminate_timeout"}


def test_invocacion_codex_deriva_homes_del_perfil_sin_lanzarlo(tmp_path, monkeypatch):
    capturado = {}
    salida = tmp_path / "resultado.json"

    def ejecutar_falso(args, **kwargs):
        capturado.update(kwargs)
        salida.write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setenv("USERPROFILE", str(tmp_path / "perfil"))
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(orquestador, "ejecutar", ejecutar_falso)

    orquestador.invocar_codex(
        codex_exe="codex-falso",
        repo=tmp_path,
        sandbox="read-only",
        schema=tmp_path / "schema.json",
        output_path=salida,
        prompt="prueba",
        timeout=10,
        model=None,
    )

    assert capturado["env"]["HOME"] == str(tmp_path / "perfil")
    assert capturado["env"]["CODEX_HOME"] == str(tmp_path / "perfil" / ".codex")
