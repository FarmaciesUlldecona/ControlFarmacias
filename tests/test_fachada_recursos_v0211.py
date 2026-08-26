from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from uuid import uuid4

from ejecutor_local import ResultadoEjecucionLocal
from ejecucion_v02 import EjecutorCicloFake
from fachada_v02 import OrquestadorV02
from lenguaje_natural import (
    AccionOrden,
    AutorizacionesOrden,
    FuenteInterpretacion,
    OrdenInterpretada,
    TipoAccionNatural,
    TipoIntencion,
)
from politica_recursos import NivelRecurso, NivelTests


def _orden(
    *acciones: TipoAccionNatural, datos_accion: dict | None = None
) -> OrdenInterpretada:
    return OrdenInterpretada(
        interpretation_id=str(uuid4()),
        schema_version=1,
        texto_original="orden de prueba",
        objetivo="objetivo de prueba",
        tipo_intencion=TipoIntencion.CREAR_TAREA,
        repo_candidato="C:\\repo",
        worktree_candidato="C:\\repo",
        modo_solicitado="workspace_write",
        acciones=tuple(
            AccionOrden(
                orden=indice,
                tipo=tipo,
                alcance="REPO",
                condicion={},
                datos=datos_accion or {},
            )
            for indice, tipo in enumerate(acciones, start=1)
        ),
        restricciones=(),
        autorizaciones=AutorizacionesOrden(
            escritura=True,
            commit=False,
            commit_condicionado_tests=False,
            push=False,
        ),
        condiciones=(),
        coste_maximo=None,
        commit=False,
        push=False,
        task_id_referencia=None,
        decision_id_referencia=None,
        retry_id_referencia=None,
        confianza=1.0,
        ambigua=False,
        ambiguedades=(),
        datos_faltantes=(),
        referencias_no_resueltas=(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata={},
        fuente=FuenteInterpretacion.PARSER_LOCAL,
    )


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=t@example.invalid",
        "commit",
        "-m",
        "base",
    )
    return repo, _git(repo, "rev-parse", "HEAD")


def _orden_repo(repo: Path, head: str, **metricas) -> OrdenInterpretada:
    base = _orden(TipoAccionNatural.MODIFICAR_ALCANCE)
    return replace(
        base,
        repo_candidato=str(repo),
        worktree_candidato=str(repo),
        metadata={
            **metricas,
            "repo_contexto": {
                "rama": "main",
                "commit_inicial": head,
                "rutas_permitidas": (),
                "rutas_protegidas": (),
            },
        },
    )


def test_comprobar_git_se_clasifica_local_only():
    evaluacion = OrquestadorV02._evaluar_recursos_orden(
        _orden(TipoAccionNatural.COMPROBAR_GIT)
    )

    assert evaluacion.nivel_recurso is NivelRecurso.LOCAL_ONLY
    assert evaluacion.requiere_codex is False


def test_ejecutar_tests_se_clasifica_local_only_y_test_focal():
    evaluacion = OrquestadorV02._evaluar_recursos_orden(
        _orden(TipoAccionNatural.EJECUTAR_TESTS)
    )

    assert evaluacion.nivel_recurso is NivelRecurso.LOCAL_ONLY
    assert evaluacion.nivel_tests is NivelTests.TEST_FOCAL
    assert evaluacion.requiere_codex is False


def test_modificar_alcance_desconocido_se_clasifica_standard_conservadoramente():
    evaluacion = OrquestadorV02._evaluar_recursos_orden(
        _orden(TipoAccionNatural.MODIFICAR_ALCANCE)
    )

    assert evaluacion.nivel_recurso is NivelRecurso.CODEX_STANDARD
    assert evaluacion.nivel_tests is NivelTests.TEST_MODULO
    assert evaluacion.requiere_codex is True


def test_accion_desconocida_no_se_clasifica_local():
    evaluacion = OrquestadorV02._evaluar_recursos_orden(
        _orden(TipoAccionNatural.OTRA)
    )

    assert evaluacion.nivel_recurso is not NivelRecurso.LOCAL_ONLY
    assert evaluacion.requiere_codex is True


def test_ejecutar_tests_local_only_no_puede_caer_en_codex(tmp_path):
    llamadas = []

    class EjecutorLocalFake:
        def ejecutar(self, solicitud):
            return ResultadoEjecucionLocal(
                operacion="EJECUTAR_TESTS",
                exito=True,
                returncode=0,
                stdout="1 passed",
            )

    class EjecutorNoPermitido:
        def ejecutar(self, *args, **kwargs):
            llamadas.append((args, kwargs))
            raise AssertionError("No debe ejecutarse Codex para LOCAL_ONLY")

    repo = tmp_path / "repo"
    repo.mkdir()

    orquestador = OrquestadorV02(
        tmp_path / "estado",
        ejecutor_factory=lambda tarea: EjecutorNoPermitido(),
        ejecutor_local=EjecutorLocalFake(),
        repos_conocidos={
            "repo": {
                "repo": str(repo),
                "worktree": str(repo),
                "rama": "main",
                "commit_inicial": "a" * 40,
                "rutas_permitidas": (),
                "rutas_protegidas": (),
            }
        },
    )

    resultado_inicio = orquestador.iniciar()
    assert resultado_inicio.ok

    orden = _orden(TipoAccionNatural.EJECUTAR_TESTS)
    resultado = orquestador._despachar_orden_natural(
        _orden(
            TipoAccionNatural.EJECUTAR_TESTS,
            datos_accion={"rutas": ["tests/test_conocido.py"]},
        )
    )

    assert resultado.ok is True
    assert resultado.codigo == "LOCAL_TESTS_EXECUTED"
    assert resultado.task_id is None
    assert resultado.run_id is None
    assert llamadas == []
    assert resultado.datos["recursos"]["nivel_recurso"] == "LOCAL_ONLY"
    assert resultado.datos["recursos"]["requiere_codex"] is False
    assert resultado.datos["ejecucion_local"]["stdout"] == "1 passed"


def test_local_only_bloqueado_no_crea_tarea_ni_run(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    orquestador = OrquestadorV02(
        tmp_path / "estado",
        repos_conocidos={
            "repo": {
                "repo": str(repo),
                "worktree": str(repo),
                "rama": "main",
                "commit_inicial": "a" * 40,
                "rutas_permitidas": (),
                "rutas_protegidas": (),
            }
        },
    )

    resultado_inicio = orquestador.iniciar()
    assert resultado_inicio.ok

    antes_tareas = len(orquestador._arranque.gestor_tareas.listar())

    resultado = orquestador._despachar_orden_natural(
        _orden(TipoAccionNatural.EJECUTAR_TESTS)
    )

    despues_tareas = len(orquestador._arranque.gestor_tareas.listar())

    assert resultado.codigo == "LOCAL_EXECUTION_FAILED"
    assert despues_tareas == antes_tareas


def test_comprobar_git_local_incluye_clasificacion_recursos(tmp_path, monkeypatch):
    class SnapshotFake:
        rama = "v0.2-dev"
        head = "1" * 40
        staged_paths = ()
        unstaged_paths = ()

    monkeypatch.setattr("fachada_v02.tomar_snapshot", lambda path: SnapshotFake())

    orquestador = OrquestadorV02(tmp_path / "estado")
    resultado_inicio = orquestador.iniciar()
    assert resultado_inicio.ok

    orden = _orden(TipoAccionNatural.COMPROBAR_GIT)

    resultado = orquestador._despachar_orden_natural(orden)

    assert resultado.ok is True
    assert resultado.codigo == "LOCAL_GIT_QUERY"
    assert resultado.datos["recursos"]["nivel_recurso"] == "LOCAL_ONLY"
    assert resultado.datos["recursos"]["requiere_codex"] is False


def test_routing_automatico_usa_alcance_y_riesgo_de_metadata():
    standard = OrquestadorV02._evaluar_recursos_orden(
        replace(
            _orden(TipoAccionNatural.MODIFICAR_ALCANCE),
            metadata={"archivos_afectados": 3},
        )
    )
    heavy = OrquestadorV02._evaluar_recursos_orden(
        replace(
            _orden(TipoAccionNatural.MODIFICAR_ALCANCE),
            metadata={
                "archivos_afectados": 8,
                "multiples_modulos": True,
                "riesgo_transversal": True,
                "nivel_recurso_anterior": "CODEX_STANDARD",
            },
        )
    )

    assert standard.nivel_recurso.value == "CODEX_STANDARD"
    assert standard.nivel_tests.value == "TEST_MODULO"
    assert heavy.nivel_recurso.value == "CODEX_HEAVY"
    assert heavy.nivel_tests.value == "SUITE_COMPLETA"
    assert heavy.requiere_ok_pio_coste is True
    assert heavy.motivo_escalado == "escalado de CODEX_STANDARD a CODEX_HEAVY"


def test_heavy_crea_barrera_durable_antes_del_ejecutor_y_permite_ok_explicito(
    tmp_path,
):
    repo, head = _repo(tmp_path)
    fake = EjecutorCicloFake()
    llamadas_factory = []

    def factory(tarea):
        llamadas_factory.append(tarea.id)
        return fake

    orquestador = OrquestadorV02(tmp_path / "estado", ejecutor_factory=factory)
    assert orquestador.iniciar().ok

    bloqueado = orquestador._despachar_orden_natural(
        _orden_repo(
            repo,
            head,
            archivos_afectados=8,
            multiples_modulos=True,
            riesgo_transversal=True,
            nivel_recurso_anterior="CODEX_LIGHT",
        )
    )

    assert bloqueado.codigo == "REQUIERE_OK_PIO_COSTE"
    assert bloqueado.requiere_intervencion is True
    assert bloqueado.datos["recursos"]["coste_estimado"] is None
    assert bloqueado.datos["recursos"]["nivel_recurso_anterior"] == "CODEX_LIGHT"
    assert llamadas_factory == []
    tarea = orquestador._arranque.gestor_tareas.cargar(bloqueado.task_id)
    assert any(e.tipo == "RESOURCE_CLASSIFIED" for e in tarea.historial)
    assert any(
        e.tipo == "RESOURCE_COST_AUTHORIZATION_REQUIRED" for e in tarea.historial
    )

    autorizado = orquestador.ejecutar_tarea(
        bloqueado.task_id, autorizacion_coste=True
    )

    assert autorizado.ok is True
    assert len(llamadas_factory) == 1
    recargada = orquestador._arranque.gestor_tareas.cargar(bloqueado.task_id)
    assert any(
        e.tipo == "RESOURCE_COST_AUTHORIZATION_GRANTED" for e in recargada.historial
    )
