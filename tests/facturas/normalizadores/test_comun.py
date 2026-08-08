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
    decimal_visible,
    fecha_visible,
    fecha_visible_a_iso,
    importe_espanol_a_decimal,
    normalizar_identificador,
    porcentaje_visible,
    procedencia_configuracion_interna,
    procedencia_determinista,
    procedencia_metadato_tecnico,
    procedencia_visible,
    registrar_validacion_monetaria,
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


def campo_visible(valor, *, evidencia: bool = True) -> dict:
    return {
        "valor": valor,
        "evidencias": ([{"texto_visible": str(valor), "pagina": 1}] if evidencia else []),
    }


@pytest.mark.parametrize(
    ("campo", "esperado"),
    [
        (campo_visible("1.234,56"), Decimal("1234.56")),
        (campo_visible("0,00"), Decimal("0.00")),
        (campo_visible(None), None),
        (campo_visible("1,00", evidencia=False), None),
    ],
)
def test_decimal_visible_exige_evidencia(campo, esperado) -> None:
    assert decimal_visible(campo) == esperado


@pytest.mark.parametrize("valor", [True, "1,234.56"])
def test_decimal_visible_rechaza_valores_invalidos(valor) -> None:
    with pytest.raises(ValueError):
        decimal_visible(campo_visible(valor))


@pytest.mark.parametrize(
    ("campo", "esperado"),
    [
        (campo_visible("21.00"), Decimal("21.00")),
        (campo_visible(Decimal("5.2")), Decimal("5.2")),
        (campo_visible(0), Decimal("0")),
        (campo_visible(None), None),
        (campo_visible("21", evidencia=False), None),
    ],
)
def test_porcentaje_visible_conserva_decimal_y_evidencia(campo, esperado) -> None:
    assert porcentaje_visible(campo) == esperado


def test_porcentaje_visible_no_se_calcula_desde_importes() -> None:
    campo = {
        "valor": None,
        "base": Decimal("100"),
        "cuota": Decimal("21"),
        "evidencias": [{"texto_visible": "100,00 21,00", "pagina": 1}],
    }
    assert porcentaje_visible(campo) is None


@pytest.mark.parametrize(
    ("campo", "esperado"),
    [
        (campo_visible("2026-08-08"), "2026-08-08"),
        (campo_visible("08-08-2026"), "2026-08-08"),
        (campo_visible(None), None),
        (campo_visible("08-08-2026", evidencia=False), None),
    ],
)
def test_fecha_visible_exige_evidencia_y_formato_soportado(campo, esperado) -> None:
    assert fecha_visible(campo) == esperado


def test_fecha_visible_rechaza_fecha_invalida() -> None:
    with pytest.raises(ValueError):
        fecha_visible(campo_visible("31-02-2026"))


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


def test_registro_comun_de_validaciones_conserva_orden_estado_y_decimales() -> None:
    validaciones: list[dict] = []
    incidencias = RegistroIncidencias()
    argumentos = {
        "validaciones": validaciones,
        "incidencias": incidencias,
        "tolerancia": Decimal("0.005"),
        "descripcion_incidencia": "Validacion no confirmada.",
        "decision_incidencia": "No se corrigen importes.",
    }
    ok = registrar_validacion_monetaria(
        nombre="ok",
        sumandos=[Decimal("10.00"), Decimal("1.00")],
        esperado=Decimal("11.00"),
        **argumentos,
    )
    error = registrar_validacion_monetaria(
        nombre="error",
        sumandos=[Decimal("10.00")],
        esperado=Decimal("11.00"),
        **argumentos,
    )
    no_evaluable = registrar_validacion_monetaria(
        nombre="no_evaluable",
        sumandos=[None],
        esperado=Decimal("11.00"),
        **argumentos,
    )
    assert [x["nombre"] for x in validaciones] == ["ok", "error", "no_evaluable"]
    assert ok.estado is EstadoValidacion.OK
    assert error.estado is EstadoValidacion.ERROR
    assert error.diferencia == Decimal("-1.00")
    assert no_evaluable.estado is EstadoValidacion.NO_EVALUABLE
    assert all(x["tolerancia"] == "0.005" for x in validaciones)
    assert [x["campo"] for x in incidencias.como_lista()] == ["error", "no_evaluable"]


def test_constructores_de_procedencia_conservan_json_historico() -> None:
    assert procedencia_visible("luna_general") == {
        "tipo": "lectura_visible",
        "fuente": "luna_general",
    }
    assert procedencia_metadato_tecnico("pdf") == {
        "tipo": "metadato_tecnico",
        "fuente": "pdf",
    }
    assert procedencia_configuracion_interna() == {
        "tipo": "configuracion_interna",
        "fuente": "python",
    }
    assert procedencia_determinista("regla", "v1") == {
        "tipo": "regla_determinista",
        "fuente": "python",
        "regla": "regla",
        "version_regla": "v1",
    }


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
