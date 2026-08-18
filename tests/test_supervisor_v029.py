import json
from pathlib import Path
import subprocess
from uuid import UUID

import pytest

from ejecucion_v02 import EjecutorCicloFake
from fachada_v02 import EspecificacionTareaV02, OrquestadorV02
from reglas_persistentes import GestorReglas, ReglaInvalida, TipoRegla
from runs_persistentes import EstadoInternoRun
from supervisor_v02 import (
    ClasificacionDecision,
    DecisionSupervisor,
    SolicitudAccion,
    SupervisorV02,
)
from tareas_persistentes import GestorTareas, ModoTarea, crear_contrato


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def _repo(tmp_path, nombre="repo"):
    repo = tmp_path / nombre
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(repo, "-c", "user.name=Test", "-c", "user.email=t@example.invalid", "commit", "-m", "base")
    return repo, _git(repo, "rev-parse", "HEAD")


def _ctx(tmp_path, *, commit=False, push=False, modo=ModoTarea.READ_ONLY,
         permitidas=(), prohibidas=(), protegidas=(), rutas=(), presupuesto=None):
    tareas = GestorTareas(tmp_path / "estado" / "tareas")
    contrato = crear_contrato(
        objetivo="probar supervisor", acciones_permitidas=permitidas,
        acciones_prohibidas=prohibidas, rutas_permitidas=rutas,
        rutas_protegidas=protegidas, condiciones_finalizacion="validado",
        commit_autorizado=commit, push_autorizado=push, presupuesto_api=presupuesto,
    )
    tarea = tareas.crear_tarea(
        orden_original="solicitud estructurada", repo=str(tmp_path), worktree=str(tmp_path),
        rama="main", commit_inicial="0" * 40, modo=modo, contrato=contrato,
    )
    reglas = GestorReglas(tmp_path / "estado" / "reglas")
    return tareas, reglas, SupervisorV02(reglas, tareas), tarea


def _sol(tarea, tipo, ambito, **kwargs):
    return SolicitudAccion(tarea.id, tipo, ambito, **kwargs)


def test_reglas_absolutas_iniciales_persisten_y_son_tipadas(tmp_path):
    _, reglas, _, _ = _ctx(tmp_path)
    absolutas = reglas.listar_reglas(tipo=TipoRegla.ABSOLUTA)
    assert {r.nombre for r in absolutas} == {"FARMATIC_READ_ONLY", "FACTURAS_ZERO_INVENTIONS"}
    assert all(UUID(r.rule_id) and r.activa for r in absolutas)
    assert GestorReglas(reglas.directorio).obtener_regla(absolutas[0].rule_id) == absolutas[0]


@pytest.mark.parametrize("accion", ["INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "PROCEDIMIENTO_MODIFICADOR"])
def test_farmatic_read_only_bloquea_toda_escritura(tmp_path, accion):
    _, _, supervisor, tarea = _ctx(tmp_path)
    ev = supervisor.evaluar(_sol(tarea, accion, "FARMATIC", clasificacion="TECNICA"))
    assert ev.decision is DecisionSupervisor.BLOCK
    assert ev.codigo == "ABSOLUTE_RULE_VIOLATION"
    assert ev.regla_aplicada


def test_regla_funcional_no_relaja_absoluta_y_absoluta_no_se_desactiva(tmp_path):
    _, reglas, supervisor, tarea = _ctx(tmp_path)
    reglas.crear_regla(nombre="permitir update", ambito="FARMATIC",
        condicion={"campo": "tipo_accion", "operador": "EQ", "valor": "UPDATE"},
        accion={"decision": "AUTO_APPLY"}, prioridad=99_999_999, origen="test explícito")
    ev = supervisor.evaluar(_sol(tarea, "UPDATE", "FARMATIC"))
    assert ev.decision is DecisionSupervisor.BLOCK
    absoluta = next(r for r in reglas.listar_reglas() if r.nombre == "FARMATIC_READ_ONLY")
    with pytest.raises(ReglaInvalida):
        reglas.desactivar_regla(absoluta.rule_id)


@pytest.mark.parametrize("tipo,datos", [
    ("INVENTAR_DATO", {}),
    ("EXTRAER_DATO_DOCUMENTAL", {"dato_demostrable": False}),
    ("INFERIR_DESDE_NOMBRE_ARCHIVO", {}),
])
def test_facturas_cero_invenciones_bloquea(tmp_path, tipo, datos):
    _, _, supervisor, tarea = _ctx(tmp_path)
    ev = supervisor.evaluar(_sol(tarea, tipo, "FACTURAS", datos=datos))
    assert ev.decision is DecisionSupervisor.BLOCK
    assert ev.codigo == "ABSOLUTE_RULE_VIOLATION"


def test_regla_funcional_uuid_persistencia_aplicacion_y_desactivacion(tmp_path):
    _, reglas, supervisor, tarea = _ctx(tmp_path)
    regla = reglas.crear_regla(
        nombre="caso", ambito="NEGOCIO",
        condicion={"campo": "datos.valor", "operador": "EQ", "valor": 7},
        accion={"decision": "AUTO_APPLY", "resultado": "OK"},
        prioridad=10, origen="Pio, explícita",
    )
    UUID(regla.rule_id)
    assert supervisor.evaluar(_sol(tarea, "CASO", "NEGOCIO", datos={"valor": 7})).regla_aplicada == regla.rule_id
    desactivada = reglas.desactivar_regla(regla.rule_id)
    assert not desactivada.activa and desactivada.version == 2
    assert len(desactivada.historial_estado) == 2
    ev = supervisor.evaluar(_sol(tarea, "CASO", "NEGOCIO", datos={"valor": 7}, metadata={"nonce": 2}))
    assert ev.decision is DecisionSupervisor.REQUIRE_PIO


def test_prioridad_y_conflicto_a_igual_prioridad(tmp_path):
    _, reglas, supervisor, tarea = _ctx(tmp_path)
    condicion = {"campo": "datos.x", "operador": "EQ", "valor": 1}
    baja = reglas.crear_regla(nombre="baja", ambito="X", condicion=condicion,
        accion={"decision": "BLOCK"}, prioridad=1, origen="test")
    alta = reglas.crear_regla(nombre="alta", ambito="X", condicion=condicion,
        accion={"decision": "AUTO_APPLY"}, prioridad=2, origen="test")
    ev = supervisor.evaluar(_sol(tarea, "X", "X", datos={"x": 1}))
    assert ev.regla_aplicada == alta.rule_id and ev.decision is DecisionSupervisor.AUTO_APPLY
    empate = reglas.crear_regla(nombre="empate", ambito="X", condicion=condicion,
        accion={"decision": "BLOCK"}, prioridad=2, origen="test")
    ev = supervisor.evaluar(_sol(tarea, "X", "X", datos={"x": 1}, metadata={"nonce": 2}))
    assert ev.codigo == "RULE_CONFLICT"
    assert set(ev.reglas_conflicto) == {alta.rule_id, empate.rule_id}


def test_restricciones_de_tarea_prevalecen_y_bloquean(tmp_path):
    _, reglas, supervisor, tarea = _ctx(tmp_path, prohibidas=("BORRAR",), protegidas=("secret",))
    reglas.crear_regla(nombre="permite", ambito="X", condicion={"campo": "tipo_accion", "operador": "EQ", "valor": "BORRAR"},
        accion={"decision": "AUTO_APPLY"}, prioridad=999, origen="test")
    assert supervisor.evaluar(_sol(tarea, "BORRAR", "X")).decision is DecisionSupervisor.BLOCK
    assert supervisor.evaluar(_sol(tarea, "EDITAR", "X", datos={"ruta": "secret/a"})).decision is DecisionSupervisor.BLOCK


@pytest.mark.parametrize("commit,push,tipo,datos,decision,codigo", [
    (True, False, "COMMIT", {"tests_correctos": True}, "AUTO_APPLY", "AUTHORIZATION_ALREADY_GRANTED"),
    (False, False, "COMMIT", {"tests_correctos": True}, "BLOCK", "ACTION_BLOCKED"),
    (False, True, "PUSH", {}, "AUTO_APPLY", "AUTHORIZATION_ALREADY_GRANTED"),
    (False, False, "PUSH", {}, "BLOCK", "ACTION_BLOCKED"),
])
def test_autorizaciones_contractuales_no_repreguntan(tmp_path, commit, push, tipo, datos, decision, codigo):
    _, _, supervisor, tarea = _ctx(tmp_path, commit=commit, push=push)
    ev = supervisor.evaluar(_sol(tarea, tipo, "GIT", datos=datos, autorizacion_requerida=tipo))
    assert ev.decision.value == decision and ev.codigo == codigo


def test_workspace_write_presupuesto_y_accion_permitida(tmp_path):
    _, _, supervisor, tarea = _ctx(tmp_path, modo=ModoTarea.WORKSPACE_WRITE, presupuesto=5, permitidas=("FORMATEAR",))
    assert supervisor.evaluar(_sol(tarea, "WORKSPACE_WRITE", "REPO", autorizacion_requerida="WORKSPACE_WRITE")).decision is DecisionSupervisor.AUTO_APPLY
    assert supervisor.evaluar(_sol(tarea, "API", "API", autorizacion_requerida="PRESUPUESTO_API", datos={"coste_estimado": 3})).decision is DecisionSupervisor.AUTO_APPLY
    assert supervisor.evaluar(_sol(tarea, "FORMATEAR", "REPO", autorizacion_requerida="FORMATEAR")).decision is DecisionSupervisor.AUTO_APPLY


def test_tecnica_segura_auto_funcional_y_ambigua_requieren_pio(tmp_path):
    _, _, supervisor, tarea = _ctx(tmp_path)
    assert supervisor.evaluar(_sol(tarea, "EJECUTAR_TEST", "REPO")).decision is DecisionSupervisor.AUTO_APPLY
    assert supervisor.evaluar(_sol(tarea, "NUEVA_EXCEPCION_NEGOCIO", "NEGOCIO")).decision is DecisionSupervisor.REQUIRE_PIO
    assert supervisor.evaluar(_sol(tarea, "CASO", "NEGOCIO", metadata={"ambigua": True})).decision is DecisionSupervisor.REQUIRE_PIO


def test_reglas_conciliacion_confirmadas_002_80_albaran_y_trazabilidad(tmp_path):
    _, _, supervisor, tarea = _ctx(tmp_path)
    ev = supervisor.evaluar(_sol(tarea, "CONCILIAR", "CONCILIACION", datos={"diferencia_absoluta": .02, "trazabilidad_economica_completa": True}))
    assert ev.decision is DecisionSupervisor.AUTO_APPLY
    assert ev.accion_resultante["resultado"] == "CONCILIAR_CON_DISCREPANCIA_REGISTRADA"
    ev80 = supervisor.evaluar(_sol(tarea, "CONCILIAR", "CONCILIACION", datos={"diferencia_absoluta": 80, "trazabilidad_economica_completa": True}))
    assert ev80.decision is DecisionSupervisor.REQUIRE_PIO
    albaran = supervisor.evaluar(_sol(tarea, "VALIDAR_COINCIDENCIA_ALBARAN", "CONCILIACION", datos={"exacta": False}))
    assert albaran.decision is DecisionSupervisor.AUTO_APPLY
    sin_traza = supervisor.evaluar(_sol(tarea, "CONCILIAR", "CONCILIACION", datos={"diferencia_absoluta": .02, "trazabilidad_economica_completa": False}))
    assert sin_traza.decision is DecisionSupervisor.BLOCK


def test_evaluacion_idempotente_y_trazable_por_rule_id(tmp_path):
    tareas, _, supervisor, tarea = _ctx(tmp_path)
    solicitud = _sol(tarea, "CONCILIAR", "CONCILIACION", datos={"diferencia_absoluta": .02, "trazabilidad_economica_completa": True})
    primera = supervisor.evaluar(solicitud)
    segunda = supervisor.evaluar(solicitud)
    assert segunda.evaluation_id == primera.evaluation_id
    assert "idempotente" in segunda.warnings[-1]
    eventos = tareas.cargar(tarea.id).historial
    assert len([e for e in eventos if e.tipo == "SUPERVISOR_EVALUATED"]) == 1
    assert any(e.tipo == "RULE_APPLIED" and e.datos["rule_id"] == primera.regla_aplicada for e in eventos)


class FakeSecuencial(EjecutorCicloFake):
    def __init__(self, primera_solicitud, segundo_estado=EstadoInternoRun.FINALIZADO):
        super().__init__(EstadoInternoRun.REQUIERE_OK_PIO, causa_pausa="situación estructurada", state_historico={"solicitud_supervisor": primera_solicitud})
        self.segundo_estado = segundo_estado
        self.numero = 0

    def ejecutar(self, run, tarea):
        self.numero += 1
        if self.numero > 1:
            self.estado = self.segundo_estado
            self.causa_pausa = ""
            self.state_historico = {"fake": True}
        return super().ejecutar(run, tarea)


def _fachada(tmp_path, fake, *, commit=False):
    repo, head = _repo(tmp_path)
    app = OrquestadorV02(tmp_path / "orquestador", ejecutor_factory=lambda _: fake)
    assert app.iniciar().ok
    creada = app.crear_tarea(EspecificacionTareaV02(
        orden_original="estructurada", objetivo="test V029", repo=str(repo), worktree=str(repo),
        rama="main", commit_inicial=head, modo=ModoTarea.READ_ONLY,
        condicion_finalizacion="validado", commit_autorizado=commit,
    ))
    assert creada.ok
    return app, creada


def test_pausa_resoluble_por_regla_no_crea_decision_y_hace_auto_resume(tmp_path):
    solicitud = {"tipo_accion": "CONCILIAR", "ambito": "CONCILIACION", "datos": {"diferencia_absoluta": .02, "trazabilidad_economica_completa": True}, "clasificacion": "FUNCIONAL"}
    fake = FakeSecuencial(solicitud)
    app, creada = _fachada(tmp_path, fake)
    resultado = app.ejecutar_tarea(creada.task_id)
    assert resultado.codigo == "ACTION_AUTO_APPROVED"
    assert resultado.datos["auto_resume"] is True and fake.numero == 2
    assert app._arranque.gestor_decisiones.listar_decisiones(creada.task_id) == []
    tipos = [e.tipo for e in app._arranque.gestor_tareas.cargar(creada.task_id).historial]
    assert "SUPERVISOR_AUTO_RESUME" in tipos and "RULE_APPLIED" in tipos


def test_pausas_resolubles_consecutivas_no_repreguntan(tmp_path):
    solicitud = {"tipo_accion": "CONCILIAR", "ambito": "CONCILIACION", "datos": {"diferencia_absoluta": .02, "trazabilidad_economica_completa": True}, "clasificacion": "FUNCIONAL"}

    class TresPausas(FakeSecuencial):
        def ejecutar(self, run, tarea):
            self.numero += 1
            if self.numero <= 3:
                self.estado = EstadoInternoRun.REQUIERE_OK_PIO
                self.causa_pausa = "misma situación estructurada"
                self.state_historico = {"solicitud_supervisor": solicitud}
            else:
                self.estado = EstadoInternoRun.FINALIZADO
                self.causa_pausa = ""
                self.state_historico = {"fake": True}
            return EjecutorCicloFake.ejecutar(self, run, tarea)

    fake = TresPausas(solicitud)
    app, creada = _fachada(tmp_path, fake)
    resultado = app.ejecutar_tarea(creada.task_id)
    assert resultado.codigo == "ACTION_AUTO_APPROVED" and fake.numero == 4
    assert app._arranque.gestor_decisiones.listar_decisiones(creada.task_id) == []


def test_pausa_no_resoluble_crea_decision_y_decision_puntual_no_crea_regla(tmp_path):
    fake = FakeSecuencial({"tipo_accion": "NUEVA_EXCEPCION", "ambito": "NEGOCIO", "datos": {}, "clasificacion": "FUNCIONAL"})
    app, creada = _fachada(tmp_path, fake)
    antes = len(app._arranque.gestor_reglas.listar_reglas())
    pausa = app.ejecutar_tarea(creada.task_id)
    assert pausa.codigo == "DECISION_REQUIRED" and pausa.decision_id
    respuesta = app.responder_decision(creada.task_id, texto="aplicar solo a este caso", ejecutor=fake)
    assert respuesta.ok
    assert len(app._arranque.gestor_reglas.listar_reglas()) == antes
    assert any(e.tipo == "PIO_DECISION_REQUIRED" for e in app._arranque.gestor_tareas.cargar(creada.task_id).historial)


def test_pausa_que_viola_absoluta_bloquea_sin_preguntar(tmp_path):
    fake = FakeSecuencial({"tipo_accion": "UPDATE", "ambito": "FARMATIC", "datos": {}, "clasificacion": "TECNICA"})
    app, creada = _fachada(tmp_path, fake)
    resultado = app.ejecutar_tarea(creada.task_id)
    assert resultado.codigo == "ACTION_BLOCKED" and not resultado.ok
    assert resultado.decision_id is None
    assert app._arranque.gestor_decisiones.listar_decisiones(creada.task_id) == []
    assert any(e.tipo == "ACTION_BLOCKED" for e in app._arranque.gestor_tareas.cargar(creada.task_id).historial)


def test_fachada_lista_registra_desactiva_evalua_y_consulta(tmp_path):
    fake = EjecutorCicloFake()
    app, creada = _fachada(tmp_path, fake)
    inicial = app.listar_reglas()
    assert inicial.ok and len(inicial.datos["reglas"]) >= 5
    registrada = app.registrar_regla(
        nombre="explícita", ambito="X",
        condicion={"campo": "datos.x", "operador": "EQ", "valor": 1},
        accion={"decision": "AUTO_APPLY"}, prioridad=10, origen="Pio explícito",
    )
    rule_id = registrada.datos["regla"]["rule_id"]
    evaluada = app.evaluar_accion(_sol(app._arranque.gestor_tareas.cargar(creada.task_id), "X", "X", datos={"x": 1}))
    assert evaluada.ok and evaluada.datos["evaluacion"]["regla_aplicada"] == rule_id
    eid = evaluada.datos["evaluacion"]["evaluation_id"]
    assert app.obtener_evaluacion(creada.task_id, eid).codigo == "EVALUATION_FOUND"
    assert app.desactivar_regla(rule_id).codigo == "RULE_DEACTIVATED"
    todas = app.listar_reglas(solo_activas=False).datos["reglas"]
    assert next(r for r in todas if r["rule_id"] == rule_id)["historial_estado"][-1]["activa"] is False


def test_pytest_usa_fakes_y_no_hay_codex_api_en_supervisor(tmp_path, monkeypatch):
    _, _, supervisor, tarea = _ctx(tmp_path)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("no debe lanzar proceso"))
    ev = supervisor.evaluar(_sol(tarea, "EJECUTAR_TEST", "REPO"))
    assert ev.decision is DecisionSupervisor.AUTO_APPLY
