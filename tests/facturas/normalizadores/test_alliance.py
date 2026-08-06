from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.normalizadores.alliance import (
    ConfiguracionAlliance,
    FilaAlbaranInvalida,
    fecha_visible_a_iso,
    importe_espanol_a_decimal,
    normalizar_alliance,
    normalizar_fila_albaran,
    serializar_json,
)


RUTA_PROYECTO = Path(__file__).resolve().parents[3]
RUTA_GENERAL = RUTA_PROYECTO / "pruebas/facturas/resultados/openai/comparativa_modelos/repeticion_01/gpt-5.6-luna/estructurado.json"
RUTA_TABLAS = RUTA_PROYECTO / "pruebas/facturas/resultados/openai/luna_tablas_literales_alliance_08008427/estructurado.json"
RUTA_MODULO = RUTA_PROYECTO / "src/facturas/normalizadores/alliance.py"
RUTA_CLI = RUTA_PROYECTO / "src/facturas/normalizar_alliance_08008427.py"


def cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def resultado_normalizado() -> tuple[dict, list[dict], dict]:
    general = cargar(RUTA_GENERAL)
    tablas = cargar(RUTA_TABLAS)
    resultado, incidencias = normalizar_alliance(
        general,
        tablas,
        ConfiguracionAlliance(archivo_origen="documento_origen.pdf"),
        fecha_ejecucion=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )
    return serializar_json(resultado), serializar_json(incidencias), tablas


def test_convierte_fecha_visible_a_iso() -> None:
    assert fecha_visible_a_iso("06-10-2026") == "2026-10-06"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1.234,56", Decimal("1234.56")),
        ("8,29-", Decimal("-8.29")),
        ("-6,13", Decimal("-6.13")),
        ("", None),
    ],
)
def test_convierte_importes_espanoles(texto: str, esperado: Decimal | None) -> None:
    assert importe_espanol_a_decimal(texto) == esperado


@pytest.mark.parametrize(("titulo", "movimiento"), [("CARGOS", "CARGO"), ("ABONOS", "ABONO")])
def test_clasifica_tablas_cargos_y_abonos(titulo: str, movimiento: str) -> None:
    fila = normalizar_fila_albaran(
        ["10-07-2026", "ABONOS AGRUPADOS", "08C38230", "8,29-", "8,66-"],
        titulo, 1, 2, 1, 1,
    )
    assert fila["tipo_movimiento"] == movimiento


def test_conserva_signos_y_extrae_celdas() -> None:
    fila = normalizar_fila_albaran(
        ["10-07-2026", "ABONOS AGRUPADOS", "08C38230", "8,29-", "8,66-"],
        "ABONOS", 1, 2, 4, 1,
    )
    assert fila["numero_albaran"] == "08C38230"
    assert fila["descripcion"] == "ABONOS AGRUPADOS"
    assert fila["fecha_albaran"] == "2026-07-10"
    assert fila["importe_base"] == Decimal("-8.29")
    assert fila["importe_total"] == Decimal("-8.66")
    assert fila["procedencia"]["celdas_literales"][3:] == ["8,29-", "8,66-"]


def test_rechaza_filas_incompletas() -> None:
    with pytest.raises(FilaAlbaranInvalida):
        normalizar_fila_albaran(["01-07-2026", "NORMAL ACUSTICO", "08C27035", "116,87"], "CARGOS", 1, 2, 3, 1)
    with pytest.raises(FilaAlbaranInvalida):
        normalizar_fila_albaran(["01-07-2026", "", "08C27035", "116,87", "127,77"], "CARGOS", 1, 2, 3, 1)


def test_detecta_servicio_basico(resultado_normalizado) -> None:
    resultado, _, _ = resultado_normalizado
    ajustes = resultado["resultado_normalizado"]["ajustes"]
    assert len(ajustes) == 1
    assert ajustes[0]["orden"] == 1
    assert ajustes[0]["tipo_ajuste"] == "GASTO"
    assert ajustes[0]["descripcion"] == "SERVICIO BASICO"
    assert ajustes[0]["importe"] == 31.46
    assert ajustes[0]["incluido_en_base"] is True
    assert ajustes[0]["incluido_en_total"] is True


def test_unico_vencimiento_alliance_asigna_total(resultado_normalizado) -> None:
    resultado, incidencias, _ = resultado_normalizado
    vencimiento = resultado["resultado_normalizado"]["vencimientos"][0]
    assert vencimiento["fecha_vencimiento"] == "2026-10-06"
    assert vencimiento["importe"] == 11185.10
    assert vencimiento["procedencia"]["importe"] == "regla_proveedor_alliance_vencimiento_unico"
    assert vencimiento["procedencia"]["importe_procede_de_lectura_literal"] is False
    assert not any(x["campo"] == "vencimientos.importe" for x in incidencias)


def _normalizar_caso_vencimiento(
    *, proveedor: str = "Alliance", total: float | None = 11185.10,
    bloques: list[dict] | None = None, separada: bool = True, descuadre: bool = False,
) -> tuple[dict, list[dict]]:
    general = cargar(RUTA_GENERAL)
    tablas = cargar(RUTA_TABLAS)
    general["factura"]["proveedor_nombre"]["valor"] = proveedor
    general["factura"]["importe_total"]["valor"] = total
    if total is None:
        general["factura"]["importe_total"]["evidencias"] = []
    if bloques is not None:
        tablas["transcripcion"]["bloques_vencimiento"] = bloques
    return normalizar_alliance(
        general,
        tablas,
        ConfiguracionAlliance(
            archivo_origen="documento_origen.pdf",
            factura_separada_inequivocamente=separada,
            descuadre_total=descuadre,
        ),
        fecha_ejecucion=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ("cambios", "motivo"),
    [
        ({"bloques": [
            {"texto_fecha": "06-10-2026", "texto_importe": None, "pagina": 4},
            {"texto_fecha": "06-11-2026", "texto_importe": None, "pagina": 4},
        ]}, "dos vencimientos"),
        ({"proveedor": "OTRO PROVEEDOR"}, "proveedor distinto"),
        ({"total": None}, "total ausente"),
        ({"separada": False}, "factura no separada"),
        ({"descuadre": True}, "descuadre total"),
    ],
)
def test_no_asigna_total_si_falla_condicion(cambios: dict, motivo: str) -> None:
    resultado, incidencias = _normalizar_caso_vencimiento(**cambios)
    vencimientos = resultado["resultado_normalizado"]["vencimientos"]
    assert vencimientos
    assert all(item["importe"] is None for item in vencimientos), motivo
    incidencia = next(x for x in incidencias if x["campo"] == "vencimientos.importe")
    assert incidencia["requiere_revision_manual"] is True


def test_normalizador_no_puede_acceder_al_patron() -> None:
    prohibidos = (
        "PATRON_OFICIAL", "facturas/patron", "comparacion_patron.json",
        "analisis_patron.md", "resultados/azure", "resultados/google",
        "luna_especializada_alliance_08008427",
    )
    for ruta in (RUTA_MODULO, RUTA_CLI):
        texto = ruta.read_text(encoding="utf-8").replace("\\", "/").lower()
        assert all(valor.lower() not in texto for valor in prohibidos)


def test_reconstruye_147_sin_duplicados_ni_inventados(resultado_normalizado) -> None:
    resultado, _, tablas = resultado_normalizado
    albaranes = resultado["resultado_normalizado"]["albaranes"]
    numeros = [x["numero_albaran"] for x in albaranes]
    numeros_literales = [
        fila["celdas"][2]
        for tabla in tablas["transcripcion"]["tablas"]
        if tabla["titulo_visible"] in ("CARGOS", "ABONOS")
        for fila in tabla["filas"]
    ]
    assert len(albaranes) == 147
    assert len(numeros) == len(set(numeros))
    assert set(numeros) == set(numeros_literales)
    assert all(x["orden_reconstruido"] is True for x in albaranes)


def test_resultado_estable_en_dos_ejecuciones() -> None:
    instante = datetime(2026, 8, 6, tzinfo=timezone.utc)
    argumentos = (
        cargar(RUTA_GENERAL),
        cargar(RUTA_TABLAS),
        ConfiguracionAlliance(archivo_origen="documento_origen.pdf"),
    )
    primero = serializar_json(normalizar_alliance(*argumentos, fecha_ejecucion=instante))
    segundo = serializar_json(normalizar_alliance(*argumentos, fecha_ejecucion=instante))
    assert primero == segundo
