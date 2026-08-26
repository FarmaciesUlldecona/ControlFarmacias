from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import subprocess
from uuid import uuid4

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


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _git(
        repo,
        "-c", "user.name=Test",
        "-c", "user.email=t@example.invalid",
        "commit", "-m", "base",
    )
    return repo, _git(repo, "rev-parse", "HEAD")


def _orden(repo: Path, head: str, **metricas) -> OrdenInterpretada:
    return OrdenInterpretada(
        interpretation_id=str(uuid4()),
        schema_version=1,
        texto_original="implementa cambio presupuestado",
        objetivo="cambio de prueba",
        tipo_intencion=TipoIntencion.CREAR_TAREA,
        repo_candidato=str(repo),
        worktree_candidato=str(repo),
        modo_solicitado="workspace_write",
        acciones=(AccionOrden(1, TipoAccionNatural.MODIFICAR_ALCANCE, "REPO"),),
        restricciones=(),
        autorizaciones=AutorizacionesOrden(True, False, False, False),
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
        metadata={
            **metricas,
            "repo_contexto": {
                "rama": "main",
                "commit_inicial": head,
                "rutas_permitidas": (),
                "rutas_protegidas": (),
            },
        },
        fuente=FuenteInterpretacion.PROVEEDOR_INYECTADO,
    )


def _app(tmp_path: Path):
    repo, head = _repo(tmp_path)
    fake = EjecutorCicloFake()
    llamadas = []

    def factory(tarea):
        llamadas.append(tarea.id)
        return fake

    app = OrquestadorV02(tmp_path / "orquestador", ejecutor_factory=factory)
    assert app.iniciar().ok
    return app, repo, head, fake, llamadas


def test_light_estimado_que_cabe_continua_y_reserva(tmp_path):
    app, repo, head, _, llamadas = _app(tmp_path)

    resultado = app._despachar_orden_natural(
        _orden(repo, head, archivos_afectados=1, coste_estimado=0.20)
    )

    assert resultado.ok is True
    assert resultado.datos["recursos"]["nivel_recurso"] == "CODEX_LIGHT"
    assert resultado.datos["recursos"]["reserva_coste"] == "0.20"
    assert len(llamadas) == 1
    presupuesto = app.consultar_presupuesto().datos["presupuesto"]
    assert presupuesto["coste_comprometido"] == "0.20"
    assert presupuesto["presupuesto_disponible"] == "3.60"


def test_light_que_no_cabe_se_bloquea_antes_del_ejecutor(tmp_path):
    app, repo, head, _, llamadas = _app(tmp_path)
    app._arranque.contabilidad_recursos.registrar_coste_real(
        "run-previo", Decimal("3.70"), task_id="previa", origen="fixture"
    )

    resultado = app._despachar_orden_natural(
        _orden(repo, head, archivos_afectados=1, coste_estimado=0.20)
    )

    assert resultado.codigo == "REQUIERE_OK_PIO_COSTE"
    assert resultado.datos["recursos"]["motivo_barrera_coste"] == "PRESUPUESTO_SEMANAL_INSUFICIENTE"
    assert resultado.datos["recursos"]["exceso_estimado"] == "0.10"
    assert llamadas == []


def test_heavy_siempre_requiere_ok_aunque_estimacion_quepa(tmp_path):
    app, repo, head, _, llamadas = _app(tmp_path)

    resultado = app._despachar_orden_natural(
        _orden(
            repo,
            head,
            archivos_afectados=8,
            multiples_modulos=True,
            riesgo_transversal=True,
            coste_estimado=0.10,
        )
    )

    assert resultado.codigo == "REQUIERE_OK_PIO_COSTE"
    assert resultado.datos["recursos"]["nivel_recurso"] == "CODEX_HEAVY"
    assert resultado.datos["recursos"]["sobre_presupuesto"] is False
    assert llamadas == []


def test_standard_dentro_y_fuera_de_presupuesto(tmp_path):
    app_cabe, repo, head, _, llamadas_cabe = _app(tmp_path / "cabe")
    dentro = app_cabe._despachar_orden_natural(
        _orden(repo, head, archivos_afectados=3, coste_estimado=0.50)
    )
    assert dentro.ok is True
    assert dentro.datos["recursos"]["nivel_recurso"] == "CODEX_STANDARD"
    assert len(llamadas_cabe) == 1

    app_fuera, repo2, head2, _, llamadas_fuera = _app(tmp_path / "fuera")
    app_fuera._arranque.contabilidad_recursos.registrar_coste_real(
        "previo", Decimal("3.75"), task_id="previa", origen="fixture"
    )
    fuera = app_fuera._despachar_orden_natural(
        _orden(repo2, head2, archivos_afectados=3, coste_estimado=0.50)
    )
    assert fuera.codigo == "REQUIERE_OK_PIO_COSTE"
    assert llamadas_fuera == []


def test_ok_excepcional_permite_sobrepasar_sin_aumentar_presupuesto(tmp_path):
    app, repo, head, _, llamadas = _app(tmp_path)
    app._arranque.contabilidad_recursos.registrar_coste_real(
        "previo", Decimal("3.70"), task_id="previa", origen="fixture"
    )
    bloqueado = app._despachar_orden_natural(
        _orden(repo, head, archivos_afectados=1, coste_estimado=0.20)
    )

    autorizado = app.ejecutar_tarea(
        bloqueado.task_id, autorizacion_coste=True
    )

    assert autorizado.ok is True
    assert len(llamadas) == 1
    presupuesto = app.consultar_presupuesto().datos["presupuesto"]
    assert presupuesto["presupuesto_total"] == "3.80"
    assert presupuesto["presupuesto_disponible"] == "-0.10"
    assert presupuesto["autorizaciones_excepcionales"] == 1


def test_registrar_coste_real_desde_fachada_libera_reserva_es_idempotente(tmp_path):
    app, repo, head, _, _ = _app(tmp_path)
    ejecutado = app._despachar_orden_natural(
        _orden(repo, head, archivos_afectados=1, coste_estimado=0.20)
    )

    primero = app.registrar_coste_real(
        ejecutado.run_id, Decimal("0.10"), origen="proveedor"
    )
    segundo = app.registrar_coste_real(
        ejecutado.run_id, Decimal("0.10"), origen="proveedor"
    )

    assert primero.codigo == "RESOURCE_COST_RECORDED"
    assert primero.datos["coste"]["coste_estimado"] == "0.20"
    assert primero.datos["presupuesto"]["coste_comprometido"] == "0.00"
    assert primero.datos["presupuesto"]["coste_real_acumulado"] == "0.10"
    assert segundo.codigo == "RESOURCE_COST_ALREADY_RECORDED"
    assert segundo.datos["idempotente"] is True


def test_coste_desconocido_no_se_inventa_y_consulta_es_local(tmp_path):
    app, repo, head, _, llamadas = _app(tmp_path)

    ejecutado = app._despachar_orden_natural(
        _orden(repo, head, archivos_afectados=3)
    )
    presupuesto = app.consultar_presupuesto()
    consumo = app.consultar_consumo()

    assert ejecutado.ok is True
    assert len(llamadas) == 1
    assert ejecutado.datos["recursos"]["coste_desconocido"] is True
    assert presupuesto.codigo == "LOCAL_WEEKLY_BUDGET_QUERY"
    assert presupuesto.datos["recursos"]["requiere_codex"] is False
    assert presupuesto.datos["presupuesto"]["presupuesto_disponible"] == "3.80"
    assert len(consumo.datos["consumo"]["costes_desconocidos"]) == 1


def test_presupuesto_agotado_no_bloquea_consultas_local_only(tmp_path):
    app, _, _, _, llamadas = _app(tmp_path)
    app._arranque.contabilidad_recursos.registrar_coste_real(
        "agotado", Decimal("3.80"), task_id="previa", origen="fixture"
    )

    presupuesto = app.consultar_presupuesto()
    consumo = app.consultar_consumo(historico=True)

    assert presupuesto.ok is True
    assert presupuesto.datos["presupuesto"]["presupuesto_disponible"] == "0.00"
    assert consumo.ok is True
    assert llamadas == []


def test_consultas_local_only_exponen_aviso_y_estado_sin_codex(tmp_path):
    app, _, _, _, llamadas = _app(tmp_path)
    app._arranque.contabilidad_recursos.registrar_coste_real(
        "cerca", Decimal("3.04"), task_id="previa", origen="fixture"
    )

    presupuesto = app.consultar_presupuesto()
    consumo = app.consultar_consumo()

    for resumen in (
        presupuesto.datos["presupuesto"],
        consumo.datos["consumo"]["presupuesto"],
    ):
        assert resumen["consumo_relevante"] == "3.04"
        assert resumen["umbral_proximidad_porcentaje"] == "80.00"
        assert resumen["umbral_proximidad_importe"] == "3.04"
        assert resumen["estado_presupuesto"] == "cerca_del_limite"
        assert resumen["aviso_proximidad"] is True
        assert resumen["limite_alcanzado_o_superado"] is False
    assert presupuesto.datos["recursos"]["requiere_codex"] is False
    assert consumo.datos["recursos"]["requiere_codex"] is False
    assert llamadas == []


def test_actualizacion_explicita_y_recovery_de_fachada(tmp_path):
    base = tmp_path / "orquestador"
    app = OrquestadorV02(base)
    actualizado = app.establecer_presupuesto_semanal(
        Decimal("5.00"), motivo="decisión Pio"
    )
    app._arranque.contabilidad_recursos.registrar_coste_real(
        "run", Decimal("1.25"), task_id="task", origen="fixture"
    )

    recuperado = OrquestadorV02(base).consultar_presupuesto()

    assert actualizado.datos["presupuesto"]["presupuesto_total"] == "5.00"
    assert recuperado.datos["presupuesto"]["presupuesto_total"] == "5.00"
    assert recuperado.datos["presupuesto"]["coste_real_acumulado"] == "1.25"


def test_cancelar_tarea_libera_reserva_sin_borrar_historico(tmp_path):
    app, repo, head, _, _ = _app(tmp_path)
    ejecutado = app._despachar_orden_natural(
        _orden(repo, head, archivos_afectados=1, coste_estimado=0.30)
    )
    assert app.consultar_presupuesto().datos["presupuesto"]["coste_comprometido"] == "0.30"

    cancelada = app.cancelar_tarea(ejecutado.task_id)
    presupuesto = app.consultar_presupuesto().datos["presupuesto"]
    consumo = app.consultar_consumo().datos["consumo"]

    assert cancelada.ok is True
    assert presupuesto["coste_comprometido"] == "0.00"
    assert consumo["reservas"][0]["estado"] == "LIBERADA"
