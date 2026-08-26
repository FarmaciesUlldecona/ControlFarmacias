"""Certificacion shadow E2E de V0.2.11 (escenarios A-P).

No usa red ni Codex real. Los repositorios Git creados por estas pruebas son
fixtures desechables bajo ``tmp_path``.
"""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import subprocess
from uuid import uuid4

import orquestador
from arranque import EstadoGlobalOrquestador, ServicioArranque
from ejecucion_v02 import EjecutorCicloFake, EjecutorCicloReal, ServicioEjecucionRuns
from ejecutor_local import ResultadoEjecucionLocal
from fachada_v02 import EspecificacionTareaV02, OrquestadorV02
from lenguaje_natural import (
    AccionOrden,
    AutorizacionesOrden,
    FuenteInterpretacion,
    OrdenInterpretada,
    TipoAccionNatural,
    TipoIntencion,
)
from runs_persistentes import EstadoInternoRun
from supervisor_v02 import SolicitudAccion
from tareas_persistentes import CapacidadCheckpoint, ModoTarea, crear_contrato


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(tmp_path: Path, nombre: str = "repo") -> tuple[Path, str]:
    repo = tmp_path / nombre
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    (repo / "modulo.py").write_text("VALOR = 1\n", encoding="utf-8")
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_modulo.py").write_text(
        "from modulo import VALOR\n\ndef test_valor():\n    assert VALOR >= 1\n",
        encoding="utf-8",
    )
    _git(repo, "add", "modulo.py", "tests/test_modulo.py")
    _git(
        repo, "-c", "user.name=Shadow", "-c", "user.email=shadow@example.invalid",
        "commit", "-m", "fixture base",
    )
    return repo, _git(repo, "rev-parse", "HEAD")


def _orden(
    texto: str,
    repo: Path,
    head: str,
    accion: TipoAccionNatural = TipoAccionNatural.MODIFICAR_ALCANCE,
    *,
    archivos: int = 1,
    coste=None,
    metadata: dict | None = None,
) -> OrdenInterpretada:
    return OrdenInterpretada(
        interpretation_id=str(uuid4()), schema_version=1,
        texto_original=texto, objetivo=texto,
        tipo_intencion=TipoIntencion.CREAR_TAREA,
        repo_candidato=str(repo), worktree_candidato=str(repo),
        modo_solicitado="workspace_write",
        acciones=(AccionOrden(1, accion, "REPO"),), restricciones=("no commit", "no push"),
        autorizaciones=AutorizacionesOrden(True, False, False, False),
        condiciones=("validacion local correcta",), coste_maximo=None,
        commit=False, push=False, task_id_referencia=None,
        decision_id_referencia=None, retry_id_referencia=None,
        confianza=1.0, ambigua=False, ambiguedades=(), datos_faltantes=(),
        referencias_no_resueltas=(), timestamp=datetime.now(timezone.utc).isoformat(),
        metadata={
            "archivos_afectados": archivos,
            "coste_estimado": coste,
            **(metadata or {}),
            "repo_contexto": {
                "rama": "main", "commit_inicial": head,
                "rutas_permitidas": ("modulo.py", "auxiliar.py", "tests/test_modulo.py"),
                "rutas_protegidas": (),
            },
        },
        fuente=FuenteInterpretacion.PROVEEDOR_INYECTADO,
    )


class _Proveedor:
    def __init__(self, orden: OrdenInterpretada):
        self.orden = orden
        self.llamadas = 0

    def interpretar(self, texto, contexto):
        self.llamadas += 1
        return self.orden.a_dict()


def _app_publica(tmp_path: Path, orden: OrdenInterpretada, factory):
    proveedor = _Proveedor(orden)
    app = OrquestadorV02(
        tmp_path / "estado", proveedor_interpretacion=proveedor,
        ejecutor_factory=factory,
    )
    assert app.iniciar().ok
    return app, proveedor


def _salida_codex(archivos=("modulo.py",), *, tests=True):
    return {
        "estado": "COMPLETADO", "resumen": "shadow completado", "detalle": "",
        "archivos_modificados": list(archivos), "tests_ejecutados": [],
        "tests_correctos": tests, "siguiente_accion_propuesta": "",
        "pregunta_para_pio": "", "opciones_para_pio": [],
    }


def test_a_consulta_estado_local_only_cero_codex(tmp_path):
    llamadas = []
    app = OrquestadorV02(tmp_path / "estado", ejecutor_factory=lambda _: llamadas.append(1))
    assert app.iniciar().ok
    resultado = app.procesar_orden("estado")
    assert resultado.codigo == "LOCAL_STATUS_QUERY"
    assert llamadas == [] and app._arranque.gestor_tareas.listar() == []


def test_b_consulta_git_local_only_cero_codex(tmp_path):
    repo, head = _repo(tmp_path)
    llamadas = []
    app = OrquestadorV02(
        tmp_path / "estado", ejecutor_factory=lambda _: llamadas.append(1),
        repos_conocidos={"HEFAME": {"repo": str(repo), "worktree": str(repo),
            "rama": "main", "commit_inicial": head, "rutas_permitidas": (),
            "rutas_protegidas": ()}},
    )
    assert app.iniciar().ok
    resultado = app.procesar_orden("Comprueba si el repo HÉFAME esta limpio")
    assert resultado.codigo == "LOCAL_GIT_QUERY"
    assert resultado.datos["recursos"]["nivel_recurso"] == "LOCAL_ONLY"
    assert llamadas == []


def test_c_test_focal_local_cero_codex(tmp_path):
    repo, head = _repo(tmp_path)
    orden = _orden("gestiona el asunto focal especial", repo, head, TipoAccionNatural.EJECUTAR_TESTS)
    orden = replace(orden, acciones=(AccionOrden(1, TipoAccionNatural.EJECUTAR_TESTS,
        "REPO", datos={"rutas": ["tests/test_modulo.py"]}),))
    llamadas = []

    class Local:
        def ejecutar(self, solicitud):
            assert solicitud.rutas == ("tests/test_modulo.py",)
            return ResultadoEjecucionLocal("EJECUTAR_TESTS", True, 0, "1 passed")

    proveedor = _Proveedor(orden)
    app = OrquestadorV02(tmp_path / "estado", proveedor_interpretacion=proveedor,
        ejecutor_factory=lambda _: llamadas.append(1), ejecutor_local=Local())
    assert app.iniciar().ok
    resultado = app.procesar_orden(orden.texto_original)
    assert resultado.codigo == "LOCAL_TESTS_EXECUTED"
    assert resultado.datos["recursos"]["nivel_tests"] == "TEST_FOCAL"
    assert llamadas == []


def test_d_light_una_llamada_validacion_local_sin_segunda(tmp_path, monkeypatch):
    repo, head = _repo(tmp_path)
    orden = _orden("gestiona el asunto light especial", repo, head, archivos=1)
    llamadas = []

    def codex_falso(**kwargs):
        llamadas.append(kwargs)
        (repo / "modulo.py").write_text("VALOR = 2\n", encoding="utf-8")
        return _salida_codex()

    monkeypatch.setattr(orquestador, "invocar_codex", codex_falso)
    app, _ = _app_publica(tmp_path, orden, lambda _: EjecutorCicloReal(
        Path(orquestador.__file__).parent, {"timeout_seconds": 30}, permitir_en_pytest=True))
    resultado = app.procesar_orden(orden.texto_original)
    assert resultado.ok and resultado.datos["recursos"]["nivel_recurso"] == "CODEX_LIGHT"
    assert len(llamadas) == 1
    run = app._arranque.gestor_runs.obtener_run(resultado.run_id)
    metricas = run.resultado.metadata["ejecucion"]["state_historico"]["metricas_consumo_codex"]
    assert metricas["llamadas_codex_ejecutadas"] == 1
    assert metricas["validacion_local_realizada"] is True


def test_e_standard_multifichero_una_llamada_y_test_modulo(tmp_path, monkeypatch):
    repo, head = _repo(tmp_path)
    orden = _orden("gestiona el asunto standard especial", repo, head, archivos=3,
        metadata={"multiples_modulos": True})
    llamadas = []

    def codex_falso(**kwargs):
        llamadas.append(kwargs)
        (repo / "modulo.py").write_text("VALOR = 3\n", encoding="utf-8")
        (repo / "auxiliar.py").write_text("ACTIVO = True\n", encoding="utf-8")
        return _salida_codex(("modulo.py", "auxiliar.py"))

    monkeypatch.setattr(orquestador, "invocar_codex", codex_falso)
    app, _ = _app_publica(tmp_path, orden, lambda _: EjecutorCicloReal(
        Path(orquestador.__file__).parent, {"timeout_seconds": 30}, permitir_en_pytest=True))
    resultado = app.procesar_orden(orden.texto_original)
    assert resultado.ok and resultado.datos["recursos"]["nivel_recurso"] == "CODEX_STANDARD"
    assert resultado.datos["recursos"]["nivel_tests"] == "TEST_MODULO"
    assert len(llamadas) == 1


def test_f_error_verificable_una_correccion_con_contexto_incremental(tmp_path, monkeypatch):
    repo, head = _repo(tmp_path)
    orden = _orden("gestiona el asunto corregible especial", repo, head, archivos=1)
    prompts = []

    def codex_falso(**kwargs):
        prompts.append(kwargs["prompt"])
        if len(prompts) == 1:
            (repo / "modulo.py").write_text("def roto(:\n", encoding="utf-8")
            return _salida_codex(tests=False)
        (repo / "modulo.py").write_text("VALOR = 4\n", encoding="utf-8")
        return _salida_codex()

    monkeypatch.setattr(orquestador, "invocar_codex", codex_falso)
    app, _ = _app_publica(tmp_path, orden, lambda _: EjecutorCicloReal(
        Path(orquestador.__file__).parent, {"timeout_seconds": 30}, permitir_en_pytest=True))
    resultado = app.procesar_orden(orden.texto_original)
    assert resultado.ok and len(prompts) == 2
    assert "modulo.py:1" in prompts[1] and "tests_correctos=false" in prompts[1]
    run = app._arranque.gestor_runs.obtener_run(resultado.run_id)
    metricas = run.resultado.metadata["ejecucion"]["state_historico"]["metricas_consumo_codex"]
    assert metricas["contexto_ampliado"] is True


def test_g_heavy_exige_ok_coste_antes_de_codex_y_sin_reserva(tmp_path):
    repo, head = _repo(tmp_path)
    orden = _orden("gestiona el asunto heavy especial", repo, head, archivos=8, coste=0.10,
        metadata={"multiples_modulos": True, "riesgo_transversal": True})
    llamadas = []
    app, _ = _app_publica(tmp_path, orden, lambda _: llamadas.append(1))
    resultado = app.procesar_orden(orden.texto_original)
    assert resultado.codigo == "REQUIERE_OK_PIO_COSTE" and llamadas == []
    assert resultado.datos["recursos"]["nivel_recurso"] == "CODEX_HEAVY"
    assert app.consultar_presupuesto().datos["presupuesto"]["coste_comprometido"] == "0.00"


def test_h_presupuesto_cerca_avisa_y_operacion_que_cabe_continua(tmp_path):
    repo, head = _repo(tmp_path)
    orden = _orden("gestiona el asunto economico especial", repo, head, archivos=1, coste=0.10)
    fake = EjecutorCicloFake()
    app, _ = _app_publica(tmp_path, orden, lambda _: fake)
    app._arranque.contabilidad_recursos.registrar_coste_real(
        "previo", Decimal("3.04"), task_id="previa", origen="shadow")
    consulta = app.consultar_presupuesto()
    ejecutada = app.procesar_orden(orden.texto_original)
    assert consulta.datos["presupuesto"]["aviso_proximidad"] is True
    assert consulta.datos["recursos"]["requiere_codex"] is False
    assert ejecutada.ok and len(fake.llamadas) == 1


def test_i_presupuesto_insuficiente_bloquea_antes_del_ejecutor(tmp_path):
    repo, head = _repo(tmp_path)
    orden = _orden("gestiona el asunto excedido especial", repo, head, archivos=1, coste=0.20)
    llamadas = []
    app, _ = _app_publica(tmp_path, orden, lambda _: llamadas.append(1))
    app._arranque.contabilidad_recursos.registrar_coste_real(
        "previo", Decimal("3.70"), task_id="previa", origen="shadow")
    resultado = app.procesar_orden(orden.texto_original)
    assert resultado.codigo == "REQUIERE_OK_PIO_COSTE" and llamadas == []
    assert resultado.datos["recursos"]["exceso_estimado"] == "0.10"


def _interrumpida(tmp_path: Path, capacidad: CapacidadCheckpoint):
    servicio = ServicioArranque(tmp_path / "estado")
    repo, head = _repo(tmp_path, "retry_repo")
    tarea = servicio.gestor_tareas.crear_tarea(
        orden_original="shadow retry", repo=str(repo), worktree=str(repo), rama="main",
        commit_inicial=head, modo=ModoTarea.READ_ONLY,
        contrato=crear_contrato(objetivo="retry shadow", condiciones_finalizacion="ok"),
        capacidad_checkpoint=capacidad,
    )
    servicio.gestor_entornos.reservar_worktree(tarea.id)
    run = servicio.gestor_runs.preparar_run(tarea.id).run
    servicio.gestor_runs.iniciar_run(run.run_id)
    cp = servicio.gestor_checkpoints.registrar_checkpoint(
        task_id=tarea.id, run_id=run.run_id, tipo="LOTE_VALIDADO",
        payload={"acciones_completadas": ["uno"], "acciones_pendientes": ["dos"],
            "unidades_pendientes": 1}, metadata={"utilizable": True}, validado=True)
    servicio.gestor_runs.registrar_resultado(run.run_id, EstadoInternoRun.INTERRUMPIDO,
        resumen="interrupcion shadow")
    assert servicio.iniciar_orquestador().estado_global is EstadoGlobalOrquestador.LISTO
    return servicio, tarea, cp


def test_j_retry_checkpoint_barato_continua_e_idempotente(tmp_path):
    servicio, tarea, cp = _interrumpida(tmp_path, CapacidadCheckpoint.CHECKPOINT_RESUME)
    plan = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id).retry
    fake = EjecutorCicloFake(capacidad_checkpoint=CapacidadCheckpoint.CHECKPOINT_RESUME)
    primero = servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, fake,
        coste_estimado=Decimal("0.10"))
    segundo = servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, fake,
        coste_estimado=Decimal("0.10"))
    assert primero.exito and segundo.idempotente and len(fake.llamadas) == 1
    assert primero.run.retry_context["acciones_pendientes"] == ["dos"]
    assert primero.run.task_id == tarea.id


def test_k_retry_full_run_exige_ok_y_no_crea_bucle(tmp_path):
    servicio, tarea, cp = _interrumpida(tmp_path, CapacidadCheckpoint.FULL_RUN_ONLY)
    plan = servicio.servicio_reintentos.preparar_reintento(tarea.id, cp.checkpoint_id).retry
    fake = EjecutorCicloFake(capacidad_checkpoint=CapacidadCheckpoint.FULL_RUN_ONLY)
    bloqueado = servicio.servicio_reintentos.ejecutar_reintento(plan.retry_id, fake)
    assert bloqueado.codigo == "REQUIERE_OK_PIO_COSTE" and fake.llamadas == []
    autorizado = servicio.servicio_reintentos.ejecutar_reintento(
        plan.retry_id, fake, autorizacion_coste=True)
    repetido = servicio.servicio_reintentos.ejecutar_reintento(
        plan.retry_id, fake, autorizacion_coste=True)
    assert autorizado.exito and repetido.idempotente and len(fake.llamadas) == 1


def _tarea_publica(tmp_path: Path):
    repo, head = _repo(tmp_path)
    app = OrquestadorV02(tmp_path / "estado")
    assert app.iniciar().ok
    creada = app.crear_tarea(EspecificacionTareaV02(
        orden_original="certificacion", objetivo="seguridad", repo=str(repo),
        worktree=str(repo), rama="main", commit_inicial=head,
        modo=ModoTarea.WORKSPACE_WRITE, condicion_finalizacion="evaluar",
        commit_autorizado=False, push_autorizado=False))
    assert creada.ok
    return app, creada.task_id, repo


def test_l_escritura_farmatic_bloqueo_absoluto_cero_codex(tmp_path):
    repo, head = _repo(tmp_path)
    orden = _orden("gestiona el asunto protegido especial", repo, head,
        TipoAccionNatural.ESCRIBIR_FARMATIC)
    llamadas = []
    app, _ = _app_publica(tmp_path, orden, lambda _: llamadas.append(1))
    resultado = app.procesar_orden(orden.texto_original)
    assert resultado.codigo == "ABSOLUTE_RULE_VIOLATION" and llamadas == []


def test_m_facturas_cero_invenciones_conserva_ausencia_y_bloquea_propuesta(tmp_path):
    app, task_id, _ = _tarea_publica(tmp_path)
    ausente = {"numero_factura": None, "lineas": [], "incidencia": "dato no demostrable"}
    resultado = app.evaluar_accion(SolicitudAccion(
        task_id, "EXTRAER_DATO_DOCUMENTAL", "FACTURAS",
        datos={"dato_demostrable": False, "resultado": ausente}))
    assert resultado.codigo == "ABSOLUTE_RULE_VIOLATION"
    assert ausente["numero_factura"] is None and ausente["lineas"] == []


def test_n_commit_sin_autorizacion_requiere_pio_y_no_commit(tmp_path):
    app, task_id, repo = _tarea_publica(tmp_path)
    antes = _git(repo, "rev-parse", "HEAD")
    resultado = app.evaluar_accion(SolicitudAccion(
        task_id, "COMMIT", "GIT", autorizacion_requerida="COMMIT",
        datos={"tests_correctos": True}))
    assert resultado.requiere_intervencion and resultado.codigo != "ACTION_AUTO_APPROVED"
    assert _git(repo, "rev-parse", "HEAD") == antes


def test_o_push_sin_autorizacion_requiere_pio_y_no_push(tmp_path):
    app, task_id, repo = _tarea_publica(tmp_path)
    resultado = app.evaluar_accion(SolicitudAccion(
        task_id, "PUSH", "GIT", autorizacion_requerida="PUSH"))
    assert resultado.requiere_intervencion and resultado.codigo != "ACTION_AUTO_APPROVED"
    assert _git(repo, "remote") == ""


def test_p_orden_ambigua_pide_aclaracion_y_cero_codex(tmp_path):
    llamadas = []
    app = OrquestadorV02(tmp_path / "estado", ejecutor_factory=lambda _: llamadas.append(1))
    assert app.iniciar().ok
    resultado = app.procesar_orden("Haz lo que veas")
    assert resultado.requiere_intervencion
    assert resultado.codigo in {"AMBIGUOUS_REFERENCE", "INTERPRETATION_INCOMPLETE"}
    assert llamadas == []
