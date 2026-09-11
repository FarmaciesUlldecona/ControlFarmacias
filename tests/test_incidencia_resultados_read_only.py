from io import StringIO
import subprocess

from cli_operativo import SesionCLI
from ejecucion_v02 import EjecutorCicloFake
from fachada_v02 import EspecificacionTareaV02, OrquestadorV02
from interfaz_operativa import ProveedorContextoOperativo, resultado_humano
from runs_persistentes import EstadoInternoRun
from tareas_persistentes import EstadoTarea, ModoTarea


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(tmp_path, nombre):
    repo = tmp_path / nombre
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(
        repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid",
        "commit", "-m", "base",
    )
    return repo, _git(repo, "rev-parse", "HEAD")


def _spec(repo, head, *, modo=ModoTarea.READ_ONLY):
    return EspecificacionTareaV02(
        orden_original="analiza sin modificar",
        objetivo="resultado funcional de prueba",
        repo=str(repo),
        worktree=str(repo),
        rama="main",
        commit_inicial=head,
        modo=modo,
        rutas_permitidas=("permitido/**",) if modo is ModoTarea.WORKSPACE_WRITE else (),
        condicion_finalizacion="resultado persistido",
    )


def _resultado_funcional():
    return {
        "estado": "COMPLETADO",
        "resumen": "Alliance está preparado para validación local, no para producción.",
        "detalle": "39 pruebas superadas; autoridad productiva deshabilitada.",
        "siguiente_paso": "Pio debe decidir una futura activación productiva.",
        "archivos_modificados": [],
        "tests_correctos": True,
        "tests_ejecutados": ["39 passed"],
    }


def _crear_y_finalizar(app, repo, head, *, con_funcional=True):
    creada = app.crear_tarea(_spec(repo, head))
    fake = EjecutorCicloFake(
        EstadoInternoRun.FINALIZADO,
        state_historico=(
            {"resultado_funcional": _resultado_funcional()}
            if con_funcional else {"fake": True}
        ),
    )
    ejecutada = app.ejecutar_tarea(creada.task_id, ejecutor=fake)
    return creada, ejecutada


def test_read_only_finalizado_mismo_head_se_cierra_y_resultado_es_consultable(tmp_path):
    repo, head = _repo(tmp_path, "repo")
    app = OrquestadorV02(tmp_path / "orquestador")
    assert app.iniciar().ok
    creada, _ = _crear_y_finalizar(app, repo, head)

    reinicio = OrquestadorV02(tmp_path / "orquestador")
    assert reinicio.iniciar().ok
    consulta = reinicio.procesar_orden("resultado")

    assert consulta.codigo == "LOCAL_RESULT_QUERY"
    assert consulta.task_id == creada.task_id
    assert "Alliance está preparado" in consulta.datos["resultado_funcional"]["resumen"]
    assert reinicio._arranque.gestor_tareas.cargar(creada.task_id).estado is EstadoTarea.FINALIZADA


def test_read_only_finalizado_head_posterior_no_bloquea_y_deja_warning(tmp_path):
    repo, head = _repo(tmp_path, "repo")
    base = tmp_path / "orquestador"
    app = OrquestadorV02(base)
    assert app.iniciar().ok
    creada, _ = _crear_y_finalizar(app, repo, head)
    (repo / "posterior.txt").write_text("ajeno\n", encoding="utf-8")
    _git(repo, "add", "posterior.txt")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "posterior")

    reinicio = OrquestadorV02(
        base,
        proveedor_interpretacion=ProveedorContextoOperativo(),
        preferir_proveedor_interpretacion=True,
    )
    inicio = reinicio.iniciar()
    consulta = reinicio.procesar_orden("dime el resultado de la última tarea")

    assert inicio.ok and inicio.estado_global == "LISTO"
    assert any("ENTORNO_CAMBIADO_DESPUES_DEL_RUN" in item for item in inicio.warnings)
    assert consulta.codigo == "LOCAL_RESULT_QUERY" and consulta.task_id == creada.task_id


def test_bloqueo_activo_conserva_proteccion_pero_permite_consultas_locales(tmp_path):
    repo_resultado, head_resultado = _repo(tmp_path, "resultado")
    repo_activo, head_activo = _repo(tmp_path, "activo")
    base = tmp_path / "orquestador"
    app = OrquestadorV02(base)
    assert app.iniciar().ok
    _, final = _crear_y_finalizar(app, repo_resultado, head_resultado)
    activa = app.crear_tarea(_spec(repo_activo, head_activo))
    (repo_activo / "posterior.txt").write_text("ajeno\n", encoding="utf-8")
    _git(repo_activo, "add", "posterior.txt")
    _git(repo_activo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "posterior")

    reinicio = OrquestadorV02(
        base,
        proveedor_interpretacion=ProveedorContextoOperativo(),
        preferir_proveedor_interpretacion=True,
    )
    assert not reinicio.iniciar().ok
    assert reinicio._arranque.gestor_tareas.cargar(activa.task_id).estado is EstadoTarea.BLOQUEADA
    assert reinicio.procesar_orden("estado").codigo == "LOCAL_STATUS_QUERY"
    assert reinicio.procesar_orden("qué presupuesto queda").codigo == "LOCAL_WEEKLY_BUDGET_QUERY"
    consulta = reinicio.procesar_orden("resultado")
    assert consulta.codigo == "LOCAL_RESULT_QUERY" and consulta.run_id == final.run_id


def test_write_finalizado_con_head_distinto_sigue_bloqueado(tmp_path):
    repo, head = _repo(tmp_path, "repo")
    base = tmp_path / "orquestador"
    app = OrquestadorV02(base)
    assert app.iniciar().ok
    creada = app.crear_tarea(_spec(repo, head, modo=ModoTarea.WORKSPACE_WRITE))
    app.ejecutar_tarea(
        creada.task_id,
        ejecutor=EjecutorCicloFake(
            EstadoInternoRun.FINALIZADO,
            state_historico={"resultado_funcional": _resultado_funcional()},
        ),
    )
    (repo / "posterior.txt").write_text("ajeno\n", encoding="utf-8")
    _git(repo, "add", "posterior.txt")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "posterior")

    reinicio = OrquestadorV02(base)
    assert not reinicio.iniciar().ok
    assert reinicio._arranque.gestor_tareas.cargar(creada.task_id).estado is EstadoTarea.BLOQUEADA


def test_cli_muestra_resultado_funcional_y_expone_ausencia_sin_inventar(tmp_path):
    repo, head = _repo(tmp_path, "repo")
    app = OrquestadorV02(tmp_path / "orquestador")
    assert app.iniciar().ok
    _, ejecutada = _crear_y_finalizar(app, repo, head)
    texto = resultado_humano("analiza", ejecutada, app.consultar_presupuesto())
    assert "RESULTADO FUNCIONAL: Alliance está preparado" in texto
    assert "ARCHIVOS MODIFICADOS: ninguno" in texto

    repo2, head2 = _repo(tmp_path, "repo2")
    _, sin_funcional = _crear_y_finalizar(app, repo2, head2, con_funcional=False)
    texto_sin = resultado_humano("analiza", sin_funcional, app.consultar_presupuesto())
    assert "RESULTADO FUNCIONAL: no disponible" in texto_sin
    consulta = app.procesar_orden("resultado")
    assert consulta.codigo == "RESULT_CONTENT_UNAVAILABLE"


def test_sesion_cli_consulta_resultado_aunque_arranque_este_bloqueado(tmp_path):
    repo, head = _repo(tmp_path, "repo")
    base = tmp_path / "orquestador"
    app = OrquestadorV02(base)
    assert app.iniciar().ok
    _crear_y_finalizar(app, repo, head)
    repo2, head2 = _repo(tmp_path, "activo")
    app.crear_tarea(_spec(repo2, head2))
    (repo2 / "posterior.txt").write_text("ajeno\n", encoding="utf-8")
    _git(repo2, "add", "posterior.txt")
    _git(repo2, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "posterior")

    salida = StringIO()
    sesion = SesionCLI(OrquestadorV02(base), salida=salida)
    assert not sesion.inicio.ok
    assert sesion.procesar("resultado") == 0
    assert "RESULTADO FUNCIONAL: Alliance está preparado" in salida.getvalue()
