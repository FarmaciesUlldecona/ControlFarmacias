from __future__ import annotations

import re
import importlib
import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from postgrest.exceptions import APIError

from src.database.leer_albaranes import convertir_fila_en_albaran
from src.models.albaran import Albaran, conservar_id_proveedor
from src.supabase_client import guardar_albaranes
from src.utils import logger as logger_modulo


CASOS_LITERALES = ("123", "00123", "ABC123", "00001", "12-34", "12 34", None)


def _fila(id_proveedor: object | None) -> SimpleNamespace:
    return SimpleNamespace(
        IdContador=1,
        IdProveedor=id_proveedor,
        Proveedor="Proveedor sintético",
        IdAlbaran="A-1",
        Fecha=datetime(2026, 1, 1),
        ImportePVP=10,
        ImportePUC=9,
        Dto=1,
    )


def _albaran(id_proveedor: str | None) -> Albaran:
    return Albaran(
        id_contador=1,
        id_proveedor=id_proveedor,
        proveedor="Proveedor sintético",
        id_albaran="A-1",
        fecha=datetime(2026, 1, 1),
        importe_pvp=10.0,
        importe_puc=9.0,
        dto=1.0,
    )


@pytest.mark.parametrize("literal", CASOS_LITERALES)
def test_modelo_y_lector_preservan_id_proveedor_literal(literal: str | None) -> None:
    assert conservar_id_proveedor(literal) == literal
    assert convertir_fila_en_albaran(_fila(literal)).id_proveedor == literal


def test_lector_solo_usa_str_para_valor_no_string() -> None:
    assert convertir_fila_en_albaran(_fila(123)).id_proveedor == "123"


@pytest.mark.parametrize("literal", CASOS_LITERALES)
def test_serializadores_productivo_e_historico_preservan_literal(
    monkeypatch, literal: str | None
) -> None:
    monkeypatch.setattr(
        logger_modulo,
        "obtener_logger",
        lambda _nombre: logging.getLogger("test-id-proveedor"),
    )
    sincronizador = importlib.import_module("src.sincronizar_albaranes")
    historico = importlib.import_module("src.importar_albaranes_historicos")
    albaran = _albaran(literal)
    assert sincronizador.convertir_albaran_para_supabase(albaran)["id_proveedor"] == literal
    assert historico.convertir_albaran_para_supabase(albaran)["id_proveedor"] == literal


@pytest.mark.parametrize("literal", CASOS_LITERALES)
def test_guardado_supabase_recibe_texto_o_null_sin_coercion(monkeypatch, literal) -> None:
    capturado = {}

    class Consulta:
        def insert(self, payload):
            capturado.update(payload)
            return self

        def execute(self):
            return SimpleNamespace(data=[dict(capturado)])

    class Cliente:
        def table(self, nombre):
            assert nombre == "albaranes"
            return Consulta()

    monkeypatch.setattr(guardar_albaranes, "obtener_cliente_supabase", lambda: Cliente())
    payload = {"farmacia": "PIO", "id_contador": 1, "id_proveedor": literal}
    assert guardar_albaranes.guardar_albaran(payload)[0]["id_proveedor"] == literal


def test_guardado_rechaza_id_proveedor_numerico_antes_de_red(monkeypatch) -> None:
    monkeypatch.setattr(
        guardar_albaranes,
        "obtener_cliente_supabase",
        lambda: pytest.fail("no debe abrir red"),
    )
    with pytest.raises(TypeError):
        guardar_albaranes.guardar_albaran({"id_proveedor": 123})


def test_guardado_interpreta_23505_como_duplicado(monkeypatch) -> None:
    class Consulta:
        def insert(self, _payload):
            return self

        def execute(self):
            raise APIError({"code": "23505", "message": "duplicate", "hint": None, "details": None})

    class Cliente:
        def table(self, nombre):
            assert nombre == "albaranes"
            return Consulta()

    monkeypatch.setattr(guardar_albaranes, "obtener_cliente_supabase", lambda: Cliente())
    payload = {"farmacia": "PIO", "id_contador": 1, "id_proveedor": "00123"}
    assert guardar_albaranes.guardar_albaran(payload) == []


def test_guardado_no_oculta_error_distinto_de_23505(monkeypatch) -> None:
    class Consulta:
        def insert(self, _payload):
            return self

        def execute(self):
            raise APIError({"code": "42501", "message": "forbidden", "hint": None, "details": None})

    class Cliente:
        def table(self, _nombre):
            return Consulta()

    monkeypatch.setattr(guardar_albaranes, "obtener_cliente_supabase", lambda: Cliente())
    with pytest.raises(APIError) as error:
        guardar_albaranes.guardar_albaran(
            {"farmacia": "PIO", "id_contador": 1, "id_proveedor": "00123"}
        )
    assert error.value.code == "42501"


def test_sincronizador_mantiene_contrato_nuevo_y_duplicado_sin_red(monkeypatch) -> None:
    sincronizador = importlib.import_module("src.sincronizar_albaranes")
    albaranes = [_albaran("00123"), _albaran("ABC123")]
    guardados = []

    monkeypatch.setattr(sincronizador, "obtener_ultimo_id_contador", lambda _farmacia: 0)
    monkeypatch.setattr(sincronizador, "obtener_nuevos_albaranes", lambda _ultimo: albaranes)

    def guardar(payload):
        guardados.append(payload)
        return [payload] if len(guardados) == 1 else []

    monkeypatch.setattr(sincronizador, "guardar_albaran", guardar)
    sincronizador.sincronizar_albaranes()

    assert len(guardados) == 2
    assert guardados[0]["id_proveedor"] == "00123"
    assert guardados[1]["id_proveedor"] == "ABC123"


def test_sql_farmatic_continua_estrictamente_read_only() -> None:
    raiz = Path(__file__).resolve().parents[1]
    codigo = (raiz / "src" / "database" / "leer_albaranes.py").read_text(encoding="utf-8")
    consultas = re.findall(r'consulta\s*=\s*"""(.*?)"""', codigo, flags=re.DOTALL)
    assert len(consultas) == 2
    for consulta in consultas:
        limpia = consulta.strip().casefold()
        assert limpia.startswith("select")
        assert not re.search(
            r"\b(insert|update|delete|merge|create|alter|drop|truncate|exec|execute)\b",
            limpia,
        )
