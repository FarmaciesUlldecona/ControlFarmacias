from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.normalizadores.comun import (
    AliasProveedor,
    EstadoValidacion,
    NivelIncidencia,
    RegistroIncidencias,
    TipoProcedencia,
    aplicar_regla_determinista,
    fecha_visible_a_iso,
    importe_espanol_a_decimal,
    normalizar_identificador,
    validar_suma_monetaria,
    valor_visible,
)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("06-10-2026", "2026-10-06"),
        ("2026-10-06", "2026-10-06"),
        (date(2026, 10, 6), "2026-10-06"),
        ("", None),
        (None, None),
    ],
)
def test_parsea_fechas_admitidas(valor, esperado) -> None:
    assert fecha_visible_a_iso(valor) == esperado


@pytest.mark.parametrize("valor", ["31-02-2026", "06/10/2026", 20261006])
def test_rechaza_fechas_imposibles_o_formatos_no_autorizados(valor) -> None:
    with pytest.raises(ValueError):
        fecha_visible_a_iso(valor)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("1.234,56", Decimal("1234.56")),
        ("1.234,56 €", Decimal("1234.56")),
        ("-1.234,56", Decimal("-1234.56")),
        ("1.234,56-", Decimal("-1234.56")),
        ("0,00", Decimal("0.00")),
        (None, None),
        ("", None),
    ],
)
def test_parsea_importes_espanoles(valor, esperado) -> None:
    assert importe_espanol_a_decimal(valor) == esperado


@pytest.mark.parametrize(
    "valor",
    [True, False, "1,234.56", "1.23", "1.234,5,6", "--1,00"],
)
def test_rechaza_importes_invalidos_o_ambiguos(valor) -> None:
    with pytest.raises(ValueError):
        importe_espanol_a_decimal(valor)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("001234", "001234"), (1234, "1234"), ("  AB-001  ", "AB-001"), ("", None), (None, None)],
)
def test_normaliza_identificadores_como_texto(valor, esperado) -> None:
    assert normalizar_identificador(valor) == esperado


def test_solo_admite_valor_de_ia_con_evidencia_valida() -> None:
    assert valor_visible({"valor": "F-001", "evidencias": [{"pagina": 1}]}) == "F-001"
    assert valor_visible({"valor": "F-002", "evidencias": []}) is None
    assert valor_visible({"valor": "F-003"}) is None
    assert valor_visible({"valor": "F-004", "evidencias": [{"pagina": None}]}) is None
    assert valor_visible(None) is None


def test_incidencias_tienen_orden_y_json_estables() -> None:
    registro = RegistroIncidencias()
    registro.agregar(
        campo="numero_factura",
        tipo="DATO_NO_VISIBLE",
        nivel=NivelIncidencia.REVISION_MANUAL,
        descripcion="No existe evidencia valida.",
        datos_visibles=None,
        decision="Se devuelve null.",
    )
    registro.agregar(
        campo="albaranes.orden",
        tipo="ORDEN_RECONSTRUIDO",
        nivel=NivelIncidencia.AVISO,
        descripcion="Orden tecnico estable.",
        datos_visibles={"filas": 2},
        decision="Se conserva el orden reconstruido.",
    )
    incidencias = registro.como_lista()
    assert [item["orden"] for item in incidencias] == [1, 2]
    assert incidencias[0]["requiere_revision_manual"] is True
    assert incidencias[1]["requiere_revision_manual"] is False


@pytest.mark.parametrize(
    ("sumandos", "esperado", "tolerancia", "estado"),
    [
        ([Decimal("100.00"), Decimal("21.00")], Decimal("121.00"), Decimal("0.00"), EstadoValidacion.OK),
        ([Decimal("100.00"), Decimal("20.999")], Decimal("121.00"), Decimal("0.01"), EstadoValidacion.OK),
        ([Decimal("100.00"), Decimal("20.98")], Decimal("121.00"), Decimal("0.01"), EstadoValidacion.ERROR),
        ([Decimal("100.00"), None], Decimal("121.00"), Decimal("0.01"), EstadoValidacion.NO_EVALUABLE),
    ],
)
def test_valida_sumas_monetarias(sumandos, esperado, tolerancia, estado) -> None:
    resultado = validar_suma_monetaria(sumandos, esperado, tolerancia=tolerancia)
    assert resultado.estado is estado


def test_validacion_monetaria_rechaza_tipos_no_decimales() -> None:
    with pytest.raises(TypeError):
        validar_suma_monetaria([100, Decimal("21.00")], Decimal("121.00"))


def test_alias_de_proveedor_usa_igualdad_normalizada_y_no_subcadenas() -> None:
    aliases = AliasProveedor(
        nombre_canonico="ALLIANCE HEALTHCARE ESPAÑA, S.A.",
        alias=("Alliance", "Cencora", "AH"),
    )
    assert aliases.normalizar("Alliance") == "ALLIANCE HEALTHCARE ESPAÑA, S.A."
    assert aliases.normalizar("  cEnCoRa  ") == "ALLIANCE HEALTHCARE ESPAÑA, S.A."
    assert aliases.normalizar("AH") == "ALLIANCE HEALTHCARE ESPAÑA, S.A."
    assert aliases.normalizar("FARMACIA AHORRO") == "FARMACIA AHORRO"


def test_procedencias_comunes_estan_definidas() -> None:
    assert {tipo.value for tipo in TipoProcedencia} == {
        "lectura_visible",
        "metadato_tecnico",
        "configuracion_interna",
        "regla_determinista",
    }


def test_regla_se_aplica_solo_con_condiciones_y_entradas_demostradas() -> None:
    resultado = aplicar_regla_determinista(
        nombre="vencimiento_unico",
        version="1.0",
        precondiciones={"proveedor": True, "fecha_unica": True},
        entradas={"importe_total": Decimal("121.00")},
        derivar=lambda entradas: entradas["importe_total"],
    )
    assert resultado.aplicada is True
    assert resultado.valor == Decimal("121.00")
    assert resultado.procedencia is not None
    assert resultado.procedencia.tipo is TipoProcedencia.REGLA_DETERMINISTA
    assert resultado.procedencia.regla == "vencimiento_unico"
    assert resultado.procedencia.version_regla == "1.0"


@pytest.mark.parametrize(
    ("precondiciones", "entradas"),
    [
        ({"proveedor": False}, {"total": Decimal("1.00")}),
        ({"proveedor": None}, {"total": Decimal("1.00")}),
        ({"proveedor": True}, {"total": None}),
        ({}, {"total": Decimal("1.00")}),
        ({"proveedor": True}, {}),
    ],
)
def test_regla_bloqueada_deja_el_valor_ausente(precondiciones, entradas) -> None:
    resultado = aplicar_regla_determinista(
        nombre="regla",
        version="1.0",
        precondiciones=precondiciones,
        entradas=entradas,
        derivar=lambda valores: valores.get("total"),
    )
    assert resultado.aplicada is False
    assert resultado.valor is None
    assert resultado.procedencia is None
    assert resultado.bloqueos


def test_nucleo_comun_permanece_aislado() -> None:
    ruta = Path(__file__).resolve().parents[3] / "src/facturas/normalizadores/comun.py"
    texto = ruta.read_text(encoding="utf-8").casefold().replace("\\", "/")
    prohibidos = (
        "patron_oficial",
        "facturas/patron",
        "cargar_patron",
        "evaluar_",
        "openai",
        "google",
        "azure",
        "farmatic",
        "sql server",
        ".env",
    )
    assert all(prohibido not in texto for prohibido in prohibidos)
