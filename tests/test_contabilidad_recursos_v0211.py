from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from contabilidad_recursos import (
    ContabilidadRecursos,
    DatoMonetarioInvalido,
)


class RelojMutable:
    def __init__(self, fecha: datetime):
        self.fecha = fecha

    def __call__(self) -> datetime:
        return self.fecha


def _reloj_lunes() -> RelojMutable:
    return RelojMutable(datetime(2026, 8, 24, 12, tzinfo=timezone(timedelta(hours=2))))


def test_inicializacion_semanal_es_idempotente_y_usa_decimal(tmp_path):
    reloj = _reloj_lunes()
    store = ContabilidadRecursos(tmp_path / "presupuestos", reloj=reloj)

    primero = store.consultar_presupuesto()
    segundo = store.consultar_presupuesto()

    assert primero.semana_id == "2026-W35"
    assert primero.presupuesto_total == Decimal("3.80")
    assert primero.coste_real_acumulado == Decimal("0.00")
    assert primero.coste_comprometido == Decimal("0.00")
    assert primero.presupuesto_disponible == Decimal("3.80")
    assert primero.umbral_proximidad_importe == Decimal("3.04")
    assert primero.estado_presupuesto == "normal"
    assert segundo == primero
    datos = json.loads((tmp_path / "presupuestos" / "2026-W35.json").read_text(encoding="utf-8"))
    assert [e["tipo"] for e in datos["eventos"]].count("WEEKLY_BUDGET_INITIALIZED") == 1


def test_reserva_es_idempotente_y_reduce_disponible(tmp_path):
    store = ContabilidadRecursos(tmp_path, reloj=_reloj_lunes())

    primera = store.reservar_coste(
        "run-1", Decimal("0.80"), task_id="task-1", run_id="run-1"
    )
    segunda = store.reservar_coste(
        "run-1", Decimal("0.80"), task_id="task-1", run_id="run-1"
    )

    assert primera.resumen.coste_comprometido == Decimal("0.80")
    assert primera.resumen.presupuesto_disponible == Decimal("3.00")
    assert segunda.idempotente is True
    assert segunda.resumen.coste_comprometido == Decimal("0.80")


def test_coste_real_inferior_libera_reserva_y_no_duplica_gasto(tmp_path):
    store = ContabilidadRecursos(tmp_path, reloj=_reloj_lunes())
    store.reservar_coste(
        "run-1", Decimal("0.80"), task_id="task-1", run_id="run-1"
    )

    primero = store.registrar_coste_real(
        "run-1", Decimal("0.50"), task_id="task-1", origen="factura"
    )
    segundo = store.registrar_coste_real(
        "run-1", Decimal("0.50"), task_id="task-1", origen="factura"
    )

    assert primero.resumen.coste_real_acumulado == Decimal("0.50")
    assert primero.resumen.coste_comprometido == Decimal("0.00")
    assert primero.resumen.presupuesto_disponible == Decimal("3.30")
    assert primero.datos["coste_estimado"] == "0.80"
    assert primero.datos["diferencia_estimado_real"] == "-0.30"
    assert segundo.idempotente is True
    assert segundo.resumen.coste_real_acumulado == Decimal("0.50")


def test_coste_real_superior_a_reserva_conserva_real_completo(tmp_path):
    store = ContabilidadRecursos(tmp_path, reloj=_reloj_lunes())
    store.reservar_coste(
        "run-2",
        Decimal("3.50"),
        task_id="task-2",
        run_id="run-2",
        autorizacion_excepcional=True,
    )

    resultado = store.registrar_coste_real(
        "run-2", Decimal("4.25"), task_id="task-2", origen="proveedor"
    )

    assert resultado.resumen.coste_real_acumulado == Decimal("4.25")
    assert resultado.resumen.presupuesto_disponible == Decimal("-0.45")
    assert resultado.datos["diferencia_estimado_real"] == "0.75"
    assert resultado.datos["autorizacion_excepcional"] is True


def test_liberar_reserva_dos_veces_no_altera_saldo(tmp_path):
    store = ContabilidadRecursos(tmp_path, reloj=_reloj_lunes())
    store.reservar_coste("op-1", Decimal("1.00"), task_id="task-1")

    primera = store.liberar_reserva(referencia="op-1", motivo="cancelada")
    segunda = store.liberar_reserva(referencia="op-1", motivo="cancelada")

    assert primera.idempotente is False
    assert segunda.idempotente is True
    assert segunda.resumen.presupuesto_disponible == Decimal("3.80")


def test_recovery_desde_nueva_instancia_reconstruye_saldo(tmp_path):
    directorio = tmp_path / "presupuestos"
    reloj = _reloj_lunes()
    primero = ContabilidadRecursos(directorio, reloj=reloj)
    primero.reservar_coste("a", Decimal("0.75"), task_id="t-a")
    primero.registrar_coste_real(
        "run-b", Decimal("1.25"), task_id="t-b", origen="registro"
    )

    recuperado = ContabilidadRecursos(directorio, reloj=reloj).consultar_presupuesto()

    assert recuperado.coste_real_acumulado == Decimal("1.25")
    assert recuperado.coste_comprometido == Decimal("0.75")
    assert recuperado.presupuesto_disponible == Decimal("1.80")


def test_domingo_a_lunes_crea_semana_nueva_sin_rollover_y_conserva_historico(tmp_path):
    reloj = RelojMutable(
        datetime(2026, 8, 30, 12, tzinfo=timezone(timedelta(hours=2)))
    )
    store = ContabilidadRecursos(tmp_path, reloj=reloj)
    anterior = store.registrar_coste_real(
        "run-domingo", Decimal("2.50"), task_id="task", origen="registro"
    )
    reloj.fecha = datetime(2026, 8, 31, 12, tzinfo=timezone(timedelta(hours=2)))

    nueva = store.consultar_presupuesto()
    historico = store.consultar_consumo(historico=True)

    assert anterior.resumen.semana_id == "2026-W35"
    assert nueva.semana_id == "2026-W36"
    assert nueva.presupuesto_total == Decimal("3.80")
    assert nueva.coste_real_acumulado == Decimal("0.00")
    assert nueva.coste_comprometido == Decimal("0.00")
    assert nueva.presupuesto_disponible == Decimal("3.80")
    assert len(historico["historico"]) == 2


def test_actualizacion_semanal_explicita_no_cambia_default_de_semana_nueva(tmp_path):
    reloj = _reloj_lunes()
    store = ContabilidadRecursos(tmp_path, reloj=reloj)

    actualizado = store.establecer_presupuesto_semanal(
        Decimal("5.00"), motivo="autorización explícita"
    )
    reloj.fecha += timedelta(days=7)
    nueva = store.consultar_presupuesto()

    assert actualizado.resumen.presupuesto_total == Decimal("5.00")
    assert nueva.presupuesto_total == Decimal("3.80")


def test_coste_desconocido_no_se_considera_cero_ni_reduce_saldo(tmp_path):
    store = ContabilidadRecursos(tmp_path, reloj=_reloj_lunes())

    primero = store.registrar_coste_desconocido("op-x", task_id="task-x")
    segundo = store.registrar_coste_desconocido("op-x", task_id="task-x")

    assert primero.codigo == "COSTE_DESCONOCIDO"
    assert primero.resumen.presupuesto_disponible == Decimal("3.80")
    assert primero.resumen.costes_desconocidos_registrados == 1
    assert segundo.idempotente is True


@pytest.mark.parametrize(
    ("consumo", "estado", "aviso", "limite"),
    [
        (Decimal("3.03"), "normal", False, False),
        (Decimal("3.04"), "cerca_del_limite", True, False),
        (Decimal("3.79"), "cerca_del_limite", True, False),
        (Decimal("3.80"), "limite_alcanzado_o_superado", False, True),
        (Decimal("4.00"), "limite_alcanzado_o_superado", False, True),
    ],
)
def test_estado_presupuesto_en_limites_del_umbral(
    consumo, estado, aviso, limite, tmp_path
):
    store = ContabilidadRecursos(tmp_path, reloj=_reloj_lunes())

    resultado = store.reservar_coste("umbral", consumo, task_id="task")

    assert resultado.resumen.consumo_relevante == consumo
    assert resultado.resumen.umbral_proximidad_porcentaje == Decimal("80.00")
    assert resultado.resumen.umbral_proximidad_importe == Decimal("3.04")
    assert resultado.resumen.estado_presupuesto == estado
    assert resultado.resumen.aviso_proximidad is aviso
    assert resultado.resumen.limite_alcanzado_o_superado is limite


def test_evento_chequeo_refleja_estado_presupuesto(tmp_path):
    directorio = tmp_path / "presupuestos"
    store = ContabilidadRecursos(directorio, reloj=_reloj_lunes())
    store.reservar_coste("previa", Decimal("3.04"), task_id="previa")

    store.comprobar_presupuesto(Decimal("0.10"), referencia="nueva")

    datos = json.loads((directorio / "2026-W35.json").read_text(encoding="utf-8"))
    evento = next(
        e for e in datos["eventos"] if e["tipo"] == "RESOURCE_BUDGET_CHECKED"
    )
    assert evento["datos"]["estado_presupuesto"] == "cerca_del_limite"
    assert evento["datos"]["aviso_proximidad"] is True
    assert evento["datos"]["porcentaje_consumido"] == "80.00"


@pytest.mark.parametrize("valor", [Decimal("-0.01"), Decimal("0.001"), 0.5, True])
def test_importes_invalidos_se_rechazan(valor, tmp_path):
    store = ContabilidadRecursos(tmp_path, reloj=_reloj_lunes())
    with pytest.raises(DatoMonetarioInvalido):
        store.establecer_presupuesto_semanal(valor)
