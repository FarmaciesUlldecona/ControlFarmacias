from types import SimpleNamespace

import pytest

from src.facturas.completitud_documental import (
    COBERTURA_ADAPTADORES,
    ErrorCompletitudDocumental,
    evaluar_completitud_local,
    validar_documento_antes_de_persistir,
)
from src.facturas.motor_local.adaptadores.registro import adaptadores_locales
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase


def factura(*, layout="LAYOUT", bloqueante=False):
    return {
        "layout": layout,
        "destinatario": {
            "nombre": {
                "valor": "PUIG SALOMÓN, PÍO",
                "evidencia": [{"pagina": 1, "literal": "PUIG SALOMÓN, PÍO"}],
            },
            "nif": {
                "valor": "40901058C",
                "evidencia": [{"pagina": 1, "literal": "NIF: 40901058C"}],
            },
        },
        "incidencias": ([{"codigo": "X", "bloqueante": True}] if bloqueante else []),
    }


def documento_local(paginas):
    return SimpleNamespace(paginas=[SimpleNamespace(numero=i) for i in range(1, paginas + 1)])


def segmentos(*rangos):
    return [SimpleNamespace(paginas=rango) for rango in rangos]


def test_marca_positiva_y_farmacia_consistente_permiten_continuar():
    doc = {"documento_completo_demostrado": True, "facturas": [factura()]}
    assert validar_documento_antes_de_persistir("PIO", doc) == "CONSISTENTE"


@pytest.mark.parametrize("doc", [
    {"facturas": [factura()]},
    {"documento_completo_demostrado": False, "facturas": [factura()]},
])
def test_ausencia_o_negacion_de_completitud_bloquea(doc):
    with pytest.raises(ErrorCompletitudDocumental, match="EXTRACCION_INCOMPLETA"):
        validar_documento_antes_de_persistir("PIO", doc)


def test_repositorio_bloquea_incompleto_antes_de_cualquier_rpc():
    class ClienteProhibido:
        def __getattr__(self, nombre):
            pytest.fail("Acceso remoto antes de completitud: " + nombre)

    resultado = SimpleNamespace(documento_normalizado={"facturas": [factura()]})
    with pytest.raises(ErrorCompletitudDocumental, match="EXTRACCION_INCOMPLETA"):
        RepositorioRuntimeSupabase(ClienteProhibido()).persistir_normalizacion(
            SimpleNamespace(farmacia="PIO"), resultado, "hash", "worker", "MANUAL", "key"
        )


def test_conciliacion_bloquea_normalizacion_historica_sin_marca_antes_de_escribir():
    class ClienteLectura:
        def table(self, nombre):
            self.nombre = nombre
            return self

        def select(self, *args): return self
        def eq(self, *args): return self
        def single(self): return self

        def execute(self):
            data = ({"farmacia": "PIO", "normalizacion_ejecucion_id": "n"}
                    if self.nombre == "facturas" else {"resultado_json": {"facturas": [factura()]}})
            return SimpleNamespace(data=data)

        def update(self, *args): pytest.fail("UPDATE antes de completitud")
        def insert(self, *args): pytest.fail("INSERT antes de completitud")

    with pytest.raises(ErrorCompletitudDocumental, match="EXTRACCION_INCOMPLETA"):
        RepositorioRuntimeSupabase(ClienteLectura()).guardar_conciliacion(
            SimpleNamespace(farmacia="PIO", factura_id="f"), "worker", None
        )


def test_cofares_multipagina_no_puede_declararse_completo():
    assert not evaluar_completitud_local(
        "cofares-local", documento_local(2), segmentos((1, 2)), [factura()], [])


def test_fedefarma_segmento_no_soportado_es_fail_closed():
    assert not evaluar_completitud_local(
        "fedefarma-local", documento_local(2), segmentos((1, 2)),
        [factura(layout=None, bloqueante=True)], [])


def test_fedefarma_todos_los_segmentos_monopagina_procesados_es_completo():
    assert evaluar_completitud_local(
        "fedefarma-local", documento_local(2), segmentos((1, 1), (2, 2)),
        [factura(), factura()], [])


def test_adaptador_sin_cobertura_demostrada_es_fail_closed():
    assert not evaluar_completitud_local(
        "ecoceutics-local", documento_local(1), segmentos((1, 1)), [factura()], [])


def test_logista_multipagina_con_albaranes_no_afirma_completitud_global():
    assert not evaluar_completitud_local(
        "logista-pharma-local", documento_local(3), segmentos((1, 3)), [factura()], [])


def test_los_17_adaptadores_registrados_tienen_clasificacion_sin_peligrosos():
    ids = {adaptador.id for adaptador in adaptadores_locales()}
    assert len(ids) == 17
    assert ids == set(COBERTURA_ADAPTADORES)
    assert "COBERTURA_PARCIAL_PELIGROSA" not in COBERTURA_ADAPTADORES.values()
