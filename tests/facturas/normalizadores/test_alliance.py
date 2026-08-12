from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.normalizadores.alliance import (
    ConfiguracionAlliance,
    FiscalidadAllianceIncompleta,
    FilaAlbaranInvalida,
    _normalizar_impuestos,
    _tramos_gastos,
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
        ConfiguracionAlliance(
            archivo_origen="documento_origen.pdf",
            factura_separada_inequivocamente=True,
            descuadre_total=False,
            pagos_parciales_o_fraccionamiento=False,
            importes_vencimiento_distintos=False,
        ),
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
    bloques: list[dict] | None = None, separada: bool | None = True,
    descuadre: bool | None = False, pagos: bool | None = False,
    importes_distintos: bool | None = False,
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
            pagos_parciales_o_fraccionamiento=pagos,
            importes_vencimiento_distintos=importes_distintos,
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


def test_no_asigna_total_con_precondiciones_no_demostradas() -> None:
    general = cargar(RUTA_GENERAL)
    tablas = cargar(RUTA_TABLAS)
    resultado, incidencias = normalizar_alliance(
        general,
        tablas,
        ConfiguracionAlliance(archivo_origen="documento_origen.pdf"),
        fecha_ejecucion=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )
    vencimiento = resultado["resultado_normalizado"]["vencimientos"][0]
    assert vencimiento["importe"] is None
    incidencia = next(x for x in incidencias if x["campo"] == "vencimientos.importe")
    assert incidencia["requiere_revision_manual"] is True
    assert any(valor is None for valor in incidencia["datos_visibles_disponibles"]["condiciones"].values())


def test_alias_corto_ah_no_coincide_por_subcadena() -> None:
    resultado, incidencias = _normalizar_caso_vencimiento(proveedor="FARMACIA AHORRO")
    vencimiento = resultado["resultado_normalizado"]["vencimientos"][0]
    assert vencimiento["importe"] is None
    assert resultado["resultado_normalizado"]["proveedor_nombre"] == "FARMACIA AHORRO"
    assert any(x["campo"] == "vencimientos.importe" for x in incidencias)


@pytest.mark.parametrize("proveedor", ["Alliance", "Cencora", "AH"])
def test_alias_alliance_reconocido_aplica_regla(proveedor: str) -> None:
    resultado, _ = _normalizar_caso_vencimiento(proveedor=proveedor)
    vencimiento = resultado["resultado_normalizado"]["vencimientos"][0]
    assert vencimiento["importe"] == Decimal("11185.10")
    assert vencimiento["procedencia"]["importe"] == "regla_proveedor_alliance_vencimiento_unico"


@pytest.mark.parametrize(
    "cambio",
    [
        {"separada": None},
        {"descuadre": None},
        {"pagos": None},
        {"importes_distintos": None},
    ],
)
def test_cada_precondicion_desconocida_bloquea_regla(cambio: dict) -> None:
    resultado, incidencias = _normalizar_caso_vencimiento(**cambio)
    vencimiento = resultado["resultado_normalizado"]["vencimientos"][0]
    assert vencimiento["importe"] is None
    incidencia = next(x for x in incidencias if x["campo"] == "vencimientos.importe")
    assert incidencia["requiere_revision_manual"] is True


def test_identificadores_sin_evidencia_permanecen_ausentes() -> None:
    general = cargar(RUTA_GENERAL)
    tablas = cargar(RUTA_TABLAS)
    general["factura"]["numero_factura"]["evidencias"] = []
    with pytest.raises(ValueError, match="Falta numero_factura"):
        normalizar_alliance(
            general,
            tablas,
            ConfiguracionAlliance(
                archivo_origen="documento_origen.pdf",
                factura_separada_inequivocamente=True,
                descuadre_total=False,
                pagos_parciales_o_fraccionamiento=False,
                importes_vencimiento_distintos=False,
            ),
            fecha_ejecucion=datetime(2026, 8, 6, tzinfo=timezone.utc),
        )


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
        ConfiguracionAlliance(
            archivo_origen="documento_origen.pdf",
            factura_separada_inequivocamente=True,
            descuadre_total=False,
            pagos_parciales_o_fraccionamiento=False,
            importes_vencimiento_distintos=False,
        ),
    )
    primero = serializar_json(normalizar_alliance(*argumentos, fecha_ejecucion=instante))
    segundo = serializar_json(normalizar_alliance(*argumentos, fecha_ejecucion=instante))
    assert primero == segundo


def _tabla_compras(tramos: list[tuple[str, str, str, str, str]]) -> dict:
    tipos_iva = [tramo[1] for tramo in tramos]
    tipos_re = [tramo[3] for tramo in tramos]
    total = sum(
        (importe_espanol_a_decimal(valor) or Decimal("0") for tramo in tramos for valor in (tramo[0], tramo[2], tramo[4])),
        Decimal("0"),
    )
    total_literal = f"{total:.2f}".replace(".", ",")
    celdas = (
        ["TOTAL COMPRAS"]
        + [tramo[0] for tramo in tramos]
        + [tramo[2] for tramo in tramos]
        + [tramo[4] for tramo in tramos]
        + [total_literal]
    )
    return {
        "pagina": 1,
        "titulo_visible": "COMPRAS",
        "encabezados": ["CONCEPTO", *tipos_iva, *tipos_iva, *tipos_re, "TOTALES"],
        "filas": [{"orden_visual": 1, "celdas": celdas}],
    }


def _tabla_gastos_cero() -> dict:
    return {
        "pagina": 1,
        "titulo_visible": "GASTOS",
        "encabezados": ["CONCEPTO", "4", "10", "21", "4", "10", "21", "TOTALES"],
        "filas": [{"orden_visual": 1, "celdas": ["TOTAL GASTOS", "", "", "", "", "", "", "0,00"]}],
    }


def _fiscalidad_sintetica(
    tramos: list[tuple[str, str, str, str, str]],
    *, base: str, iva: str, re: str, total: str,
) -> list[dict]:
    return _normalizar_impuestos(
        [_tabla_compras(tramos), _tabla_gastos_cero()],
        Decimal(base), Decimal(iva), Decimal(re), Decimal(total),
    )


@pytest.mark.parametrize(
    ("tramos", "totales", "cantidad"),
    [
        ([('100,00', '10', '10,00', '1,40', '1,40')], ('100.00', '10.00', '1.40', '111.40'), 1),
        ([('100,00', '10', '10,00', '1,40', '1,40'), ('50,00', '21', '10,50', '5,20', '2,60')], ('150.00', '20.50', '4.00', '174.50'), 2),
        ([('100,00', '4', '4,00', '0,50', '0,50'), ('100,00', '10', '10,00', '1,40', '1,40'), ('100,00', '21', '21,00', '5,20', '5,20')], ('300.00', '35.00', '7.10', '342.10'), 3),
    ],
)
def test_conserva_uno_dos_y_tres_tramos_completos(tramos, totales, cantidad) -> None:
    impuestos = _fiscalidad_sintetica(
        tramos, base=totales[0], iva=totales[1], re=totales[2], total=totales[3]
    )
    assert len(impuestos) == cantidad


def test_asocia_iva_y_recargo_por_columnas_explicitas() -> None:
    impuestos = _fiscalidad_sintetica(
        [('50,00', '21', '10,50', '5,20', '2,60')],
        base='50.00', iva='10.50', re='2.60', total='63.10',
    )
    assert impuestos[0]["tipo_iva"] == Decimal("21.00")
    assert impuestos[0]["tipo_recargo_equivalencia"] == Decimal("5.20")


def test_gasto_con_iva_explicito_conserva_recargo_ausente() -> None:
    tabla = {
        "pagina": 1, "titulo_visible": "GASTOS",
        "encabezados": ["CONCEPTO", "4", "10", "21", "4", "10", "21", "TOTALES"],
        "filas": [
            {"orden_visual": 1, "celdas": ["SERVICIO", "", "", "26,00", "", "", "", "5,46", "31,46"]},
            {"orden_visual": 2, "celdas": ["TOTAL GASTOS", "", "", "26,00", "", "", "", "5,46", "31,46"]},
        ],
    }
    tramo = _tramos_gastos(tabla, 1)[0]
    assert tramo["tipo_iva"] == Decimal("21.00")
    assert tramo["tipo_recargo_equivalencia"] is None
    assert tramo["cuota_recargo_equivalencia"] is None


def test_mismo_iva_con_distinto_recargo_no_se_fusiona(resultado_normalizado) -> None:
    resultado, _, _ = resultado_normalizado
    tramos_21 = [x for x in resultado["resultado_normalizado"]["impuestos"] if x["tipo_iva"] == 21]
    assert len(tramos_21) == 2
    assert {x["tipo_recargo_equivalencia"] for x in tramos_21} == {5.2, None}


def test_compras_y_gastos_reconcilian_sin_doble_conteo(resultado_normalizado) -> None:
    resultado, _, _ = resultado_normalizado
    factura = resultado["resultado_normalizado"]
    assert sum(x["base_imponible"] for x in factura["impuestos"]) == factura["base_imponible_total"]
    assert factura["ajustes"][0]["incluido_en_base"] is True
    assert factura["ajustes"][0]["incluido_en_total"] is True


def test_tabla_truncada_rechaza_fiscalidad() -> None:
    compras = _tabla_compras([('100,00', '10', '10,00', '1,40', '1,40')])
    compras["filas"][0]["celdas"].pop()
    with pytest.raises(FiscalidadAllianceIncompleta, match="truncada"):
        _normalizar_impuestos([compras, _tabla_gastos_cero()], Decimal('100'), Decimal('10'), Decimal('1.4'), Decimal('111.4'))


def test_total_compras_no_reconciliado_rechaza_fiscalidad() -> None:
    compras = _tabla_compras([('100,00', '10', '10,00', '1,40', '1,40')])
    compras["filas"][0]["celdas"][-1] = "111,41"
    with pytest.raises(FiscalidadAllianceIncompleta, match="total visible"):
        _normalizar_impuestos(
            [compras, _tabla_gastos_cero()],
            Decimal('100'), Decimal('10'), Decimal('1.4'), Decimal('111.4'),
        )


def test_columna_ambigua_rechaza_fiscalidad() -> None:
    compras = _tabla_compras([('100,00', '10', '10,00', '1,40', '1,40')])
    compras["encabezados"][2] = "21"
    with pytest.raises(FiscalidadAllianceIncompleta, match="ambiguas"):
        _normalizar_impuestos([compras, _tabla_gastos_cero()], Decimal('100'), Decimal('10'), Decimal('1.4'), Decimal('111.4'))


@pytest.mark.parametrize(
    ("totales", "mensaje"),
    [
        (("99.99", "10.00", "1.40", "111.39"), "sumas fiscales"),
        (("100.00", "9.99", "1.40", "111.39"), "sumas fiscales"),
        (("100.00", "10.00", "1.39", "111.39"), "sumas fiscales"),
        (("100.00", "10.00", "1.40", "111.41"), "total de factura"),
    ],
)
def test_rechaza_desajustes_de_base_iva_re_y_total(totales, mensaje) -> None:
    with pytest.raises(FiscalidadAllianceIncompleta, match=mensaje):
        _fiscalidad_sintetica(
            [('100,00', '10', '10,00', '1,40', '1,40')],
            base=totales[0], iva=totales[1], re=totales[2], total=totales[3],
        )


def test_orden_fiscal_es_estable() -> None:
    impuestos = _fiscalidad_sintetica(
        [('100,00', '21', '21,00', '5,20', '5,20'), ('100,00', '4', '4,00', '0,50', '0,50')],
        base='200', iva='25', re='5.7', total='230.7',
    )
    assert [(x["orden"], x["tipo_iva"]) for x in impuestos] == [(1, Decimal('21')), (2, Decimal('4'))]


def test_fiscalidad_es_determinista() -> None:
    argumentos = ([('100,00', '10', '10,00', '1,40', '1,40')],)
    primero = _fiscalidad_sintetica(*argumentos, base='100', iva='10', re='1.4', total='111.4')
    segundo = _fiscalidad_sintetica(*argumentos, base='100', iva='10', re='1.4', total='111.4')
    assert primero == segundo


def test_regla_fiscal_no_necesita_numero_factura_ni_proveedor() -> None:
    impuestos = _fiscalidad_sintetica(
        [('100,00', '10', '10,00', '1,40', '1,40')],
        base='100', iva='10', re='1.4', total='111.4',
    )
    assert len(impuestos) == 1


def test_produccion_no_contiene_facturas_ni_importes_de_evidencia() -> None:
    texto = RUTA_MODULO.read_text(encoding="utf-8")
    prohibidos = ("08008427", "08008428", "08008429", "08008430", "2.751,75", "11.185,10")
    assert all(valor not in texto for valor in prohibidos)


def test_fiscalidad_completa_elimina_incidencia(resultado_normalizado) -> None:
    resultado, incidencias, _ = resultado_normalizado
    assert len(resultado["resultado_normalizado"]["impuestos"]) == 4
    assert not any(x["tipo_incidencia"] == "DESGLOSE_FISCAL_INCOMPLETO" for x in incidencias)


def test_fiscalidad_insegura_devuelve_vacio_e_incidencia() -> None:
    general = cargar(RUTA_GENERAL)
    tablas = cargar(RUTA_TABLAS)
    tablas["transcripcion"]["tablas"][0]["filas"][-1]["celdas"][1] = "8.548,51"
    resultado, incidencias = normalizar_alliance(
        general, tablas,
        ConfiguracionAlliance(archivo_origen="x.pdf"),
        fecha_ejecucion=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )
    assert resultado["resultado_normalizado"]["impuestos"] == []
    assert any(x["tipo_incidencia"] == "DESGLOSE_FISCAL_INCOMPLETO" for x in incidencias)


def test_fiscalidad_no_modifica_albaranes_vencimientos_ni_ajustes(resultado_normalizado) -> None:
    resultado, _, _ = resultado_normalizado
    factura = resultado["resultado_normalizado"]
    assert len(factura["albaranes"]) == 147
    assert factura["vencimientos"][0]["fecha_vencimiento"] == "2026-10-06"
    assert factura["ajustes"][0]["importe"] == 31.46


@pytest.mark.parametrize(
    ("numero", "ruta_general", "ruta_tablas", "ruta_artefacto", "tramos"),
    [
        ("08008427", RUTA_GENERAL, RUTA_TABLAS, RUTA_PROYECTO / "pruebas/facturas/resultados/openai/normalizacion_alliance_08008427/factura_normalizada.json", 4),
        ("08008428", RUTA_PROYECTO / "pruebas/facturas/resultados/openai/alliance_08008428/documento_01/estructurado.json", RUTA_PROYECTO / "pruebas/facturas/resultados/openai/alliance_08008428/tablas_literales/estructurado.json", RUTA_PROYECTO / "pruebas/facturas/resultados/openai/alliance_08008428/normalizacion/factura_normalizada.json", 3),
        ("08008429", RUTA_PROYECTO / "pruebas/facturas/resultados/openai/alliance_08008429/documento_01/estructurado.json", RUTA_PROYECTO / "pruebas/facturas/resultados/openai/alliance_08008429/tablas_literales/estructurado.json", RUTA_PROYECTO / "pruebas/facturas/resultados/openai/alliance_08008429/normalizacion/factura_normalizada.json", 1),
        ("08008430", RUTA_PROYECTO / "pruebas/facturas/resultados/openai/alliance_08008430/documento_01/estructurado.json", RUTA_PROYECTO / "pruebas/facturas/resultados/openai/alliance_08008430/tablas_literales/estructurado.json", RUTA_PROYECTO / "pruebas/facturas/resultados/openai/alliance_08008430/normalizacion/factura_normalizada.json", 2),
    ],
)
def test_reprocesado_real_coincide_con_artefacto_y_decisiones_aprobadas(
    numero, ruta_general, ruta_tablas, ruta_artefacto, tramos
) -> None:
    artefacto = cargar(ruta_artefacto)
    config = artefacto["configuracion_interna_aplicada"]
    resultado, incidencias = normalizar_alliance(
        cargar(ruta_general), cargar(ruta_tablas),
        ConfiguracionAlliance(
            archivo_origen=artefacto["archivo_origen"],
            pagina_inicio=artefacto["paginas_originales"][0],
            pagina_fin=artefacto["paginas_originales"][1],
            **{clave: config[clave] for clave in (
                "farmacia", "proveedor", "categoria", "requiere_conciliacion_albaranes",
                "destinatario_id_farmacia", "destinatario_metodo_identificacion",
                "factura_separada_inequivocamente", "descuadre_total",
                "pagos_parciales_o_fraccionamiento", "importes_vencimiento_distintos",
            )},
        ),
        fecha_ejecucion=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    actual = serializar_json(resultado)["resultado_normalizado"]
    esperado = artefacto["resultado_normalizado"]
    assert actual["numero_factura"] == numero
    assert len(actual["impuestos"]) == tramos
    assert actual["albaranes"] == esperado["albaranes"]
    assert actual["vencimientos"] == esperado["vencimientos"]
    assert actual["ajustes"] == esperado["ajustes"]
    assert actual["destinatario"]["nombre"] == "PUIG SALOMON PIUS"
    if numero == "08008429":
        assert len(actual["vencimientos"]) == 2
        assert [item["fecha_vencimiento"] for item in actual["vencimientos"]] == [
            "2026-10-10", "2026-10-10",
        ]
        assert [item["importe"] for item in actual["vencimientos"]] == [None, None]
    assert not any(x["tipo_incidencia"] == "DESGLOSE_FISCAL_INCOMPLETO" for x in incidencias)
