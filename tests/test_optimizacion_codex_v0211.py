from pathlib import Path
import subprocess

import orquestador


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "modulo.py").write_text("VALOR = 1\n", encoding="utf-8")
    _git(repo, "add", "modulo.py")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _entrada(tmp_path: Path, *, nivel="CODEX_LIGHT"):
    repo, head = _repo(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    tarea = {
        "id": "task-1",
        "objetivo": "actualizar modulo",
        "criterio_finalizacion": "validación local correcta",
        "modo": "workspace_write",
        "rutas_permitidas": ["modulo.py"],
        "rutas_protegidas": [],
        "restricciones": ["no commit"],
        "nivel_recurso": nivel,
        "archivos_candidatos": ["modulo.py"],
        "tests_relevantes": [],
        "session_id": "session-local",
        "retry": False,
    }
    state = {
        "ciclo": 0,
        "head_inicial": head,
        "siguiente_instruccion": tarea["objetivo"],
    }
    config = {
        "repo": str(repo),
        "timeout_seconds": 30,
        "rutas_protegidas": [],
    }
    return repo, run_dir, tarea, state, config


def _completado(*, tests=True):
    return {
        "estado": "COMPLETADO",
        "resumen": "hecho",
        "detalle": "",
        "archivos_modificados": ["modulo.py"],
        "tests_ejecutados": [],
        "tests_correctos": tests,
        "siguiente_accion_propuesta": "",
        "pregunta_para_pio": "",
        "opciones_para_pio": [],
    }


def test_local_only_evita_todas_las_llamadas_codex(tmp_path, monkeypatch):
    _, run_dir, tarea, state, config = _entrada(tmp_path, nivel="LOCAL_ONLY")
    llamadas = []
    monkeypatch.setattr(orquestador, "invocar_codex", lambda **kwargs: llamadas.append(kwargs))

    estado, salida = orquestador.ejecutar_ciclo(
        base_dir=Path(orquestador.__file__).parent,
        config=config,
        tarea=tarea,
        state=state,
        run_dir=run_dir,
        decision_pio=None,
    )

    assert estado == "FINALIZADO"
    assert llamadas == []
    assert salida["metricas_consumo_codex"]["llamadas_codex_ejecutadas"] == 0
    assert salida["metricas_consumo_codex"]["llamadas_codex_evitadas"] == 1


def test_light_resuelta_hace_una_llamada_y_supervision_local(tmp_path, monkeypatch):
    _, run_dir, tarea, state, config = _entrada(tmp_path)
    llamadas = []

    def codex_falso(**kwargs):
        llamadas.append(kwargs["output_path"].name)
        return _completado()

    monkeypatch.setattr(orquestador, "invocar_codex", codex_falso)
    estado, salida = orquestador.ejecutar_ciclo(
        base_dir=Path(orquestador.__file__).parent,
        config=config,
        tarea=tarea,
        state=state,
        run_dir=run_dir,
        decision_pio=None,
    )

    assert estado == "FINALIZADO"
    assert llamadas == ["resultado_ejecutor.json"]
    assert salida["ultima_decision_supervisor"]["origen"] == "SUPERVISOR_DETERMINISTA_LOCAL"
    metricas = salida["metricas_consumo_codex"]
    assert metricas["llamadas_codex_ejecutadas"] == 1
    assert metricas["segunda_llamada_necesaria"] is False
    assert metricas["validacion_local_realizada"] is True
    assert metricas["resultado_validacion_local"] == "OK"


def test_fallo_local_pasa_error_concreto_a_una_correccion(tmp_path, monkeypatch):
    repo, run_dir, tarea, state, config = _entrada(tmp_path)
    prompts = []

    def codex_falso(**kwargs):
        prompts.append(kwargs["prompt"])
        if len(prompts) == 1:
            (repo / "modulo.py").write_text("def roto(:\n", encoding="utf-8")
            return _completado(tests=False)
        (repo / "modulo.py").write_text("VALOR = 2\n", encoding="utf-8")
        return _completado()

    monkeypatch.setattr(orquestador, "invocar_codex", codex_falso)
    estado, salida = orquestador.ejecutar_ciclo(
        base_dir=Path(orquestador.__file__).parent,
        config=config,
        tarea=tarea,
        state=state,
        run_dir=run_dir,
        decision_pio=None,
    )

    assert estado == "FINALIZADO"
    assert len(prompts) == 2
    assert "modulo.py:1" in prompts[1]
    assert "tests_correctos=false" in prompts[1]
    metricas = salida["metricas_consumo_codex"]
    assert metricas["llamadas_codex_ejecutadas"] == 2
    assert metricas["segunda_llamada_necesaria"] is True
    assert metricas["contexto_ampliado"] is True
    assert metricas["resultado_validacion_local"] == "OK"


def test_heavy_no_inicia_correccion_automatica(tmp_path, monkeypatch):
    repo, run_dir, tarea, state, config = _entrada(tmp_path, nivel="CODEX_HEAVY")
    llamadas = []

    def codex_falso(**kwargs):
        llamadas.append(kwargs)
        (repo / "modulo.py").write_text("def roto(:\n", encoding="utf-8")
        return _completado(tests=False)

    monkeypatch.setattr(orquestador, "invocar_codex", codex_falso)
    estado, salida = orquestador.ejecutar_ciclo(
        base_dir=Path(orquestador.__file__).parent,
        config=config,
        tarea=tarea,
        state=state,
        run_dir=run_dir,
        decision_pio=None,
    )

    assert estado == "REQUIERE_OK_PIO"
    assert len(llamadas) == 1
    assert salida["metricas_consumo_codex"]["segunda_llamada_necesaria"] is True
    assert salida["metricas_consumo_codex"]["llamadas_codex_evitadas"] == 1
