from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.clasificacion_documental import TipoFacturaDocumental
from src.facturas.runtime_supabase.elegibilidad_conciliacion import (
    EstadoElegibilidadConciliacion,
    EvidenciasElegibilidadConciliacion,
    RazonElegibilidadConciliacion,
    evaluar_elegibilidad_conciliacion,
)
from src.facturas.runtime_supabase.conciliacion import conciliar_importes
from src.facturas.runtime_supabase.modelos import FacturaTrabajo
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase


SQL = (
    Path(__file__).resolve().parents[3]
    / "sql/migrations/14_cf_claim_conciliacion_v2.sql"
).read_text(encoding="utf-8")


def evidencia(tipo=TipoFacturaDocumental.FACTURA_GASTO_SERVICIO, **cambios):
    base = EvidenciasElegibilidadConciliacion(
        tipo_documental=tipo,
        documento_completo_demostrado=True,
        farmacia_estado="CONSISTENTE",
        normalizacion_valida=True,
        total_demostrado=True,
        trazabilidad_mercancia=False,
        trazabilidad_servicio=True,
        total_explicado=True,
        fiscalidad_coherente=True,
        incidencia_bloqueante=False,
    )
    return replace(base, **cambios)


def evaluar(tipo=TipoFacturaDocumental.FACTURA_GASTO_SERVICIO, **cambios):
    return evaluar_elegibilidad_conciliacion(evidencia(tipo, **cambios))


def test_mercancia_con_albaranes_validos_es_apta():
    result = evaluar(TipoFacturaDocumental.FACTURA_MERCANCIA, trazabilidad_mercancia=True)
    assert (result.estado, result.razon) == (EstadoElegibilidadConciliacion.APTA, RazonElegibilidadConciliacion.APTA_MERCANCIA)


def test_mercancia_sin_albaranes_queda_bloqueada():
    result = evaluar(TipoFacturaDocumental.FACTURA_MERCANCIA)
    assert (result.estado, result.razon) == (EstadoElegibilidadConciliacion.NO_APTA, RazonElegibilidadConciliacion.FALTAN_ALBARANES_MERCANCIA)


def test_gasto_servicio_sin_albaranes_con_traza_completa_es_apta():
    result = evaluar(trazabilidad_mercancia=False)
    assert (result.estado, result.razon) == (EstadoElegibilidadConciliacion.APTA, RazonElegibilidadConciliacion.APTA_GASTO_SERVICIO)


def test_gasto_servicio_con_total_no_explicado_no_es_apta():
    result = evaluar(total_explicado=False)
    assert (result.estado, result.razon) == (EstadoElegibilidadConciliacion.NO_APTA, RazonElegibilidadConciliacion.TOTAL_NO_EXPLICADO)


def test_gasto_servicio_no_genera_razon_de_albaran_no_localizado():
    result = evaluar(trazabilidad_mercancia=False)
    assert result.razon != RazonElegibilidadConciliacion.FALTAN_ALBARANES_MERCANCIA
    assert "ALBARAN_NO_LOCALIZADO" not in SQL


def test_mixta_con_ambas_trazabilidades_es_apta():
    result = evaluar(TipoFacturaDocumental.FACTURA_MIXTA, trazabilidad_mercancia=True)
    assert (result.estado, result.razon) == (EstadoElegibilidadConciliacion.APTA, RazonElegibilidadConciliacion.APTA_MIXTA)


def test_mixta_sin_trazabilidad_mercancia_no_es_apta():
    result = evaluar(TipoFacturaDocumental.FACTURA_MIXTA)
    assert result.razon == RazonElegibilidadConciliacion.FALTAN_ALBARANES_MERCANCIA


def test_mixta_sin_trazabilidad_servicio_no_es_apta():
    result = evaluar(TipoFacturaDocumental.FACTURA_MIXTA, trazabilidad_mercancia=True, trazabilidad_servicio=False)
    assert result.razon == RazonElegibilidadConciliacion.TRAZABILIDAD_SERVICIO_INSUFICIENTE


def test_tipo_no_demostrado_requiere_revision():
    result = evaluar(TipoFacturaDocumental.TIPO_NO_DEMOSTRADO)
    assert (result.estado, result.razon) == (EstadoElegibilidadConciliacion.REQUIERE_REVISION, RazonElegibilidadConciliacion.TIPO_DOCUMENTAL_NO_DEMOSTRADO)


def test_documento_incompleto_no_es_apto():
    assert evaluar(documento_completo_demostrado=False).razon == RazonElegibilidadConciliacion.DOCUMENTO_INCOMPLETO


@pytest.mark.parametrize(
    ("estado_farmacia", "razon"),
    [
        ("CONTRADICTORIA", RazonElegibilidadConciliacion.FARMACIA_NO_CONSISTENTE),
        ("NO_DEMOSTRABLE", RazonElegibilidadConciliacion.FARMACIA_NO_DEMOSTRABLE),
    ],
)
def test_farmacia_no_valida_no_es_apta(estado_farmacia, razon):
    result = evaluar(farmacia_estado=estado_farmacia)
    assert result.estado == EstadoElegibilidadConciliacion.NO_APTA
    assert result.razon == razon


def test_cofares_sintetica_es_apta_sin_albaranes():
    result = evaluar(
        trazabilidad_mercancia=False, trazabilidad_servicio=True,
        total_explicado=True, fiscalidad_coherente=True,
    )
    assert result.razon == RazonElegibilidadConciliacion.APTA_GASTO_SERVICIO


def test_logista_sintetica_sigue_apta_con_albaran():
    result = evaluar(TipoFacturaDocumental.FACTURA_MERCANCIA, trazabilidad_mercancia=True, trazabilidad_servicio=False)
    assert result.razon == RazonElegibilidadConciliacion.APTA_MERCANCIA


def test_claim_sql_solo_selecciona_elegibilidad_apta():
    claim = SQL[SQL.rfind("create or replace function public.cf_reclamar_factura_conciliacion"):].casefold()
    assert "cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e" in claim
    assert "e.estado = 'apta'" in claim
    assert "and f.requiere_conciliacion_albaranes" not in claim
    assert "for update of f skip locked" in claim
    assert "limit 1" in claim


def test_python_y_sql_comparten_estados_razones_y_orden_fail_closed():
    for value in EstadoElegibilidadConciliacion:
        assert f"'{value.value}'" in SQL
    for value in RazonElegibilidadConciliacion:
        assert f"'{value.value}'" in SQL
    assert SQL.index("DOCUMENTO_INCOMPLETO") < SQL.index("TIPO_DOCUMENTAL_NO_DEMOSTRADO")
    assert SQL.index("FARMACIA_NO_DEMOSTRABLE") < SQL.index("TIPO_DOCUMENTAL_NO_DEMOSTRADO")


def test_claim_conserva_concurrencia_reintentos_e_idempotencia_historica():
    lower = SQL.casefold()
    assert "conciliacion_reintento_solicitado_at is not null" in lower
    assert "for update of f skip locked" in lower
    assert "conciliacion_bloqueado_hasta" in lower
    assert "greatest(p_bloqueo_segundos, 1)" in lower
    assert "conciliaciones_actual_factura_unico" in (Path(__file__).resolve().parents[3] / "sql/migrations/11_cf_conciliacion.sql").read_text(encoding="utf-8")


class _Response:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: self

    def execute(self):
        return _Response(self.client.rows[self.table])


class _Client:
    def __init__(self):
        self.calls = []
        self.rows = {
            "facturas": {
                "proveedor_literal": "COFARES", "proveedor_nombre": None,
                "proveedor_id": None, "categoria": "CUOTA_SERVICIO",
                "iva_total": "21", "recargo_equivalencia_total": "0",
                "datos_extraidos": {"naturaleza_principal": "SERVICIOS"},
            },
            "facturas_movimientos": [{
                "id": "mov-1", "categoria": "SERVICIO",
                "descripcion_literal": "Servicio documentado", "sentido": "CARGO",
                "importe": None, "base": "100", "provenance": {"pagina": 1},
            }],
        }

    def table(self, name):
        self.calls.append(name)
        return _Query(self, name)


def test_repositorio_servicios_construye_movimientos_sin_consultar_albaranes():
    client = _Client()
    repo = RepositorioRuntimeSupabase(client)
    factura = FacturaTrabajo("f1", "d1", "PIO", Decimal("121"))
    detalles = repo.construir_detalles(factura)
    resultado = conciliar_importes("121", detalles)
    assert resultado.resultado == "CONCILIADA"
    assert resultado.importe_explicado == Decimal("121.0000")
    assert client.calls == ["facturas", "facturas_movimientos"]
    assert not any(detalle.provenance.get("fuente") == "ALBARANES_SUPABASE" for detalle in detalles)
