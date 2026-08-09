from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.configuraciones_estandar import (
    CONFIGURACION_ENDESA,
    CONFIGURACION_GUIMERA,
    CONFIGURACION_HYGIE31,
    CONFIGURACION_PIERRE_FABRE,
)
from src.facturas.normalizadores.configuracion import ConfiguracionProveedor
from src.facturas.normalizadores.estandar import normalizar_estandar


RAIZ = Path(__file__).resolve().parents[3]
INSTANTE = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)


def campo(valor, *, evidencia: bool = True) -> dict:
    return {
        "valor": valor,
        "evidencias": (
            [{"texto_visible": str(valor), "pagina": 1}] if evidencia else []
        ),
    }


def campo_con_evidencia(valor, texto_visible: str) -> dict:
    return {
        "valor": valor,
        "evidencias": [{"texto_visible": texto_visible, "pagina": 1}],
    }


@pytest.fixture
def configuracion() -> ConfiguracionProveedor:
    return ConfiguracionProveedor(
        proveedor_nombre_canonico="PROVEEDOR GENERAL, S.A.",
        aliases=("Proveedor General SA",),
        categoria="SERVICIO",
        requiere_conciliacion_albaranes=False,
        farmacia="FARMACIA INTERNA",
        id_farmacia="0007",
        metodo_identificacion_farmacia="CIF",
    )


@pytest.fixture
def extraccion() -> dict:
    return {
        "factura": {
            "tipo_documento": campo("FACTURA"),
            "proveedor_nombre": campo("Proveedor General SA"),
            "proveedor_cif": campo("A00123456"),
            "numero_factura": campo("0000123"),
            "fecha_factura": campo("08-08-2026"),
            "base_imponible_total": campo("100,00"),
            "iva_total": campo("21,00"),
            "recargo_equivalencia_total": campo(None, evidencia=False),
            "importe_total": campo("121,00"),
            "vencimientos": [
                {
                    "fecha_vencimiento": campo("10-09-2026"),
                    "importe": campo("121,00"),
                    "nota": campo("Pago visible"),
                }
            ],
            "impuestos": [
                {
                    "base_imponible": campo("100,00"),
                    "tipo_iva": campo(21),
                    "cuota_iva": campo("21,00"),
                    "tipo_recargo_equivalencia": campo(None, evidencia=False),
                    "cuota_recargo_equivalencia": campo(None, evidencia=False),
                    "nota": campo(None, evidencia=False),
                }
            ],
            "albaranes": [],
            "ajustes": [],
            "destinatario": {
                "nombre": campo("PERSONA VISIBLE"),
                "cif": campo("40901058C"),
            },
            "fecha_cargo": campo(None, evidencia=False),
            "periodo_facturacion_inicio": campo(None, evidencia=False),
            "periodo_facturacion_fin": campo(None, evidencia=False),
            "nota_revision": campo(None, evidencia=False),
        }
    }


def ejecutar(extraccion: dict, configuracion: ConfiguracionProveedor):
    return normalizar_estandar(
        extraccion,
        {"paginas_originales": [3, 4]},
        configuracion,
        INSTANTE,
        archivo_origen="documento_sintetico.pdf",
    )


def test_factura_estandar_completa_reutiliza_configuracion_y_documento(
    extraccion,
    configuracion,
) -> None:
    resultado, incidencias = ejecutar(extraccion, configuracion)
    factura = resultado["resultado_normalizado"]

    assert factura["tipo_documento"] == "FACTURA"
    assert factura["proveedor_nombre"] == "PROVEEDOR GENERAL, S.A."
    assert factura["categoria"] == "SERVICIO"
    assert factura["requiere_conciliacion_albaranes"] is False
    assert factura["numero_factura"] == "0000123"
    assert factura["fecha_factura"] == "2026-08-08"
    assert resultado["paginas_originales"] == [3, 4]
    assert incidencias == []


def test_factura_sin_recargo_conserva_none(extraccion, configuracion) -> None:
    resultado, _ = ejecutar(extraccion, configuracion)
    factura = resultado["resultado_normalizado"]
    tramo = factura["impuestos"][0]

    assert factura["recargo_equivalencia_total"] is None
    assert tramo["tipo_recargo_equivalencia"] is None
    assert tramo["cuota_recargo_equivalencia"] is None


def test_factura_con_recargo_visible_lo_conserva(extraccion, configuracion) -> None:
    general = extraccion["factura"]
    general["recargo_equivalencia_total"] = campo("5,20")
    general["importe_total"] = campo("126,20")
    tramo = general["impuestos"][0]
    tramo["tipo_recargo_equivalencia"] = campo("5.2")
    tramo["cuota_recargo_equivalencia"] = campo("5,20")

    resultado, incidencias = ejecutar(extraccion, configuracion)
    normalizado = resultado["resultado_normalizado"]["impuestos"][0]
    assert normalizado["tipo_recargo_equivalencia"] == Decimal("5.2")
    assert normalizado["cuota_recargo_equivalencia"] == Decimal("5.20")
    assert incidencias == []


def test_vencimiento_visible_completo_y_sin_vencimientos(
    extraccion,
    configuracion,
) -> None:
    resultado, _ = ejecutar(extraccion, configuracion)
    assert resultado["resultado_normalizado"]["vencimientos"][0] == {
        "orden": 1,
        "fecha_vencimiento": "2026-09-10",
        "importe": Decimal("121.00"),
        "nota": "Pago visible",
        "procedencia": {"tipo": "lectura_visible", "fuente": "luna_general"},
    }

    sin_vencimiento = deepcopy(extraccion)
    sin_vencimiento["factura"]["vencimientos"] = []
    resultado, _ = ejecutar(sin_vencimiento, configuracion)
    assert resultado["resultado_normalizado"]["vencimientos"] == []


def test_fecha_vencimiento_sin_importe_no_recibe_total(
    extraccion,
    configuracion,
) -> None:
    extraccion["factura"]["vencimientos"][0]["importe"] = campo(
        None, evidencia=False
    )
    resultado, incidencias = ejecutar(extraccion, configuracion)
    vencimiento = resultado["resultado_normalizado"]["vencimientos"][0]

    assert vencimiento["fecha_vencimiento"] == "2026-09-10"
    assert vencimiento["importe"] is None
    assert any(
        incidencia["tipo_incidencia"] == "IMPORTE_VENCIMIENTO_NO_VISIBLE"
        for incidencia in incidencias
    )


def test_fechas_iguales_con_evidencias_independientes_se_conservan(
    extraccion,
    configuracion,
) -> None:
    general = extraccion["factura"]
    general["fecha_cargo"] = campo("10-09-2026")
    general["vencimientos"][0]["fecha_vencimiento"] = {
        "valor": "10-09-2026",
        "evidencias": [
            {"texto_visible": "Vencimiento: 10-09-2026", "pagina": 1}
        ],
    }

    resultado, _ = ejecutar(extraccion, configuracion)
    factura = resultado["resultado_normalizado"]

    assert factura["fecha_cargo"] == "2026-09-10"
    assert factura["vencimientos"][0]["fecha_vencimiento"] == "2026-09-10"


def test_fecha_etiquetada_solo_como_cargo_no_crea_vencimiento(
    extraccion,
    configuracion,
) -> None:
    general = extraccion["factura"]
    general["fecha_cargo"] = campo("10-09-2026")
    general["vencimientos"][0]["fecha_vencimiento"] = {
        "valor": "10-09-2026",
        "evidencias": [
            {"texto_visible": "Fecha de cargo: 10-09-2026", "pagina": 1}
        ],
    }

    resultado, incidencias = ejecutar(extraccion, configuracion)
    factura = resultado["resultado_normalizado"]

    assert factura["fecha_cargo"] == "2026-09-10"
    assert factura["vencimientos"] == []
    assert incidencias == []


def test_datos_sin_evidencia_quedan_none_y_ids_siguen_siendo_texto(
    extraccion,
    configuracion,
) -> None:
    extraccion["factura"]["proveedor_cif"] = campo("A99999999", evidencia=False)
    resultado, _ = ejecutar(extraccion, configuracion)
    factura = resultado["resultado_normalizado"]

    assert factura["proveedor_cif"] is None
    assert factura["numero_factura"] == "0000123"
    assert isinstance(factura["numero_factura"], str)


@pytest.mark.parametrize(
    ("visible", "esperado", "incidencia"),
    [
        ("PROVEEDOR GENERAL, S.A.", "PROVEEDOR GENERAL, S.A.", False),
        ("Proveedor General SA", "PROVEEDOR GENERAL, S.A.", False),
        ("OTRO PROVEEDOR", "OTRO PROVEEDOR", True),
        (
            "DISTRIBUCIONES PROVEEDOR GENERAL SA SUR",
            "DISTRIBUCIONES PROVEEDOR GENERAL SA SUR",
            True,
        ),
    ],
)
def test_reconocimiento_proveedor_exige_alias_completo(
    extraccion,
    configuracion,
    visible,
    esperado,
    incidencia,
) -> None:
    extraccion["factura"]["proveedor_nombre"] = campo(visible)
    resultado, incidencias = ejecutar(extraccion, configuracion)
    assert resultado["resultado_normalizado"]["proveedor_nombre"] == esperado
    assert (
        any(x["tipo_incidencia"] == "PROVEEDOR_CONFIGURADO_NO_RECONOCIDO" for x in incidencias)
        is incidencia
    )


def test_destinatario_combina_visible_y_configuracion_interna(
    extraccion,
    configuracion,
) -> None:
    resultado, _ = ejecutar(extraccion, configuracion)
    assert resultado["resultado_normalizado"]["destinatario"] == {
        "id_farmacia": "0007",
        "nombre": "PERSONA VISIBLE",
        "cif": "40901058C",
        "metodo_identificacion": "CIF",
    }


def test_fiscalidad_valida_conserva_decimal_y_registra_validacion(
    extraccion,
    configuracion,
) -> None:
    resultado, incidencias = ejecutar(extraccion, configuracion)
    tramo = resultado["resultado_normalizado"]["impuestos"][0]

    assert tramo["base_imponible"] == Decimal("100.00")
    assert isinstance(tramo["base_imponible"], Decimal)
    assert resultado["validaciones_monetarias"][0]["estado"] == "OK"
    assert incidencias == []


def test_fiscalidad_con_descuadre_detecta_pero_no_corrige(
    extraccion,
    configuracion,
) -> None:
    extraccion["factura"]["impuestos"][0]["cuota_iva"] = campo("20,00")
    resultado, incidencias = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["impuestos"][0][
        "cuota_iva"
    ] == Decimal("20.00")
    assert resultado["validaciones_monetarias"][0]["estado"] == "ERROR"
    assert any(
        x["tipo_incidencia"] == "VALIDACION_MONETARIA_ERROR"
        for x in incidencias
    )


def test_fiscalidad_con_dos_tramos_conserva_orden_recargo_y_validaciones(
    extraccion,
    configuracion,
) -> None:
    segundo = deepcopy(extraccion["factura"]["impuestos"][0])
    segundo["base_imponible"] = campo("50,00")
    segundo["tipo_iva"] = campo("10")
    segundo["cuota_iva"] = campo("5,00")
    segundo["tipo_recargo_equivalencia"] = campo(1.4)
    segundo["cuota_recargo_equivalencia"] = campo("0,70")
    extraccion["factura"]["impuestos"].append(segundo)

    resultado, incidencias = ejecutar(extraccion, configuracion)
    impuestos = resultado["resultado_normalizado"]["impuestos"]

    assert [tramo["orden"] for tramo in impuestos] == [1, 2]
    assert impuestos[1]["tipo_recargo_equivalencia"] == Decimal("1.4")
    assert impuestos[1]["cuota_recargo_equivalencia"] == Decimal("0.70")
    assert [validacion["estado"] for validacion in resultado["validaciones_monetarias"]] == [
        "OK",
        "OK",
        "OK",
    ]
    assert incidencias == []


def fila_fiscal_vacia() -> dict:
    return {
        "orden": campo(None, evidencia=False),
        "base_imponible": campo(None, evidencia=False),
        "tipo_iva": campo(None, evidencia=False),
        "cuota_iva": campo(None, evidencia=False),
        "tipo_recargo_equivalencia": campo(None, evidencia=False),
        "cuota_recargo_equivalencia": campo(None, evidencia=False),
        "nota": campo(None, evidencia=False),
    }


def incidencias_fiscales(incidencias: list[dict]) -> list[dict]:
    return [
        incidencia
        for incidencia in incidencias
        if incidencia["tipo_incidencia"]
        == "CONCEPTO_FISCAL_NO_REPRESENTABLE"
    ]


def test_fila_iva_parcial_representable_conserva_comportamiento_historico(
    extraccion,
    configuracion,
) -> None:
    fila = fila_fiscal_vacia()
    fila["base_imponible"] = campo("40,00")
    extraccion["factura"]["impuestos"] = [fila]

    resultado, incidencias = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["impuestos"][0][
        "base_imponible"
    ] == Decimal("40.00")
    assert incidencias_fiscales(incidencias) == []


def test_fila_recargo_valida_no_genera_incidencia(
    extraccion,
    configuracion,
) -> None:
    fila = fila_fiscal_vacia()
    fila["base_imponible"] = campo("100,00")
    fila["tipo_recargo_equivalencia"] = campo("5.2")
    fila["cuota_recargo_equivalencia"] = campo("5,20")
    extraccion["factura"]["impuestos"] = [fila]

    resultado, incidencias = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["impuestos"][0][
        "cuota_recargo_equivalencia"
    ] == Decimal("5.20")
    assert incidencias_fiscales(incidencias) == []


def test_fila_fiscal_realmente_vacia_se_omite_sin_incidencia(
    extraccion,
    configuracion,
) -> None:
    extraccion["factura"]["impuestos"] = [fila_fiscal_vacia()]

    resultado, incidencias = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["impuestos"] == []
    assert incidencias == []


def test_fila_fiscal_solo_con_nota_visible_genera_una_incidencia(
    extraccion,
    configuracion,
) -> None:
    fila = fila_fiscal_vacia()
    fila["nota"] = campo_con_evidencia(
        "Concepto fiscal visible", "Concepto fiscal visible 1,23 EUR"
    )
    extraccion["factura"]["impuestos"] = [fila]

    resultado, incidencias = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["impuestos"] == []
    assert len(incidencias_fiscales(incidencias)) == 1


def test_fila_fiscal_solo_con_evidencia_visible_genera_incidencia(
    extraccion,
    configuracion,
) -> None:
    fila = fila_fiscal_vacia()
    fila["orden"] = campo_con_evidencia(None, "Concepto fiscal visible")
    extraccion["factura"]["impuestos"] = [fila]

    _, incidencias = ejecutar(extraccion, configuracion)

    incidencia = incidencias_fiscales(incidencias)[0]
    assert incidencia["datos_visibles_disponibles"]["nota"] is None
    assert incidencia["datos_visibles_disponibles"]["evidencias"] == [
        {
            "campo": "orden",
            "texto_visible": "Concepto fiscal visible",
            "pagina": 1,
        }
    ]


def test_varias_evidencias_de_una_fila_generan_una_sola_incidencia(
    extraccion,
    configuracion,
) -> None:
    fila = fila_fiscal_vacia()
    fila["nota"] = {
        "valor": "Concepto visible",
        "evidencias": [
            {"texto_visible": "Primera evidencia", "pagina": 1},
            {"texto_visible": "Segunda evidencia", "pagina": 2},
        ],
    }
    extraccion["factura"]["impuestos"] = [fila]

    _, incidencias = ejecutar(extraccion, configuracion)

    fiscales = incidencias_fiscales(incidencias)
    assert len(fiscales) == 1
    assert fiscales[0]["datos_visibles_disponibles"]["paginas"] == [1, 2]
    assert len(fiscales[0]["datos_visibles_disponibles"]["evidencias"]) == 2


def test_varias_filas_fiscales_no_representables_generan_una_incidencia_por_fila(
    extraccion,
    configuracion,
) -> None:
    primera = fila_fiscal_vacia()
    primera["nota"] = campo("Concepto uno")
    segunda = fila_fiscal_vacia()
    segunda["nota"] = campo("Concepto dos")
    extraccion["factura"]["impuestos"] = [primera, segunda]

    _, incidencias = ejecutar(extraccion, configuracion)

    fiscales = incidencias_fiscales(incidencias)
    assert [incidencia["campo"] for incidencia in fiscales] == [
        "impuestos[0]",
        "impuestos[1]",
    ]


def test_incidencia_fiscal_no_extrae_importe_ni_clasifica_concepto(
    extraccion,
    configuracion,
) -> None:
    fila = fila_fiscal_vacia()
    fila["nota"] = campo_con_evidencia(
        "Tributo documental", "Tributo documental 9,87 EUR"
    )
    extraccion["factura"]["impuestos"] = [fila]

    _, incidencias = ejecutar(extraccion, configuracion)

    datos = incidencias_fiscales(incidencias)[0][
        "datos_visibles_disponibles"
    ]
    assert set(datos) == {
        "orden_entrada",
        "nota",
        "evidencias",
        "paginas",
        "campos_fiscales_recibidos",
        "motivo",
    }
    assert datos["campos_fiscales_recibidos"] == {
        "base_imponible": None,
        "tipo_iva": None,
        "cuota_iva": None,
        "tipo_recargo_equivalencia": None,
        "cuota_recargo_equivalencia": None,
    }
    assert all(
        nombre not in datos
        for nombre in ("importe", "tipo_impuesto", "impuesto_especial")
    )


def test_incidencia_fiscal_es_determinista_y_acepta_proveedor_arbitrario(
    extraccion,
    configuracion,
) -> None:
    fila = fila_fiscal_vacia()
    fila["nota"] = campo("Concepto fiscal pendiente")
    extraccion["factura"]["impuestos"] = [fila]
    otra_configuracion = ConfiguracionProveedor(
        proveedor_nombre_canonico="ENTIDAD ARBITRARIA, S.L.",
        aliases=("Entidad Arbitraria",),
        categoria="SERVICIO",
        requiere_conciliacion_albaranes=False,
        farmacia="FARMACIA INTERNA",
        id_farmacia="0007",
        metodo_identificacion_farmacia="CIF",
    )
    extraccion["factura"]["proveedor_nombre"] = campo("Entidad Arbitraria")

    primero = ejecutar(deepcopy(extraccion), otra_configuracion)
    segundo = ejecutar(deepcopy(extraccion), otra_configuracion)

    assert primero == segundo
    assert len(incidencias_fiscales(primero[1])) == 1


def test_fechas_opcionales_incompletas_se_bloquean_sin_derivarlas(
    extraccion,
    configuracion,
) -> None:
    extraccion["factura"]["periodo_facturacion_inicio"] = campo("2026-05")
    extraccion["factura"]["periodo_facturacion_fin"] = campo("05-2026")

    resultado, incidencias = ejecutar(extraccion, configuracion)
    factura = resultado["resultado_normalizado"]

    assert factura["periodo_facturacion_inicio"] is None
    assert factura["periodo_facturacion_fin"] is None
    assert [incidencia["campo"] for incidencia in incidencias] == [
        "periodo_facturacion_inicio",
        "periodo_facturacion_fin",
    ]
    assert all(
        incidencia["tipo_incidencia"] == "FECHA_VISIBLE_NO_INTERPRETABLE"
        for incidencia in incidencias
    )


def test_cero_monetario_no_se_omite(extraccion, configuracion) -> None:
    tramo = extraccion["factura"]["impuestos"][0]
    tramo["base_imponible"] = campo("0")
    tramo["tipo_iva"] = campo("0")
    tramo["cuota_iva"] = campo("0")
    resultado, _ = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["impuestos"][0][
        "base_imponible"
    ] == Decimal("0")


def test_albaranes_y_ajustes_no_interpretables_se_bloquean(
    extraccion,
    configuracion,
) -> None:
    extraccion["factura"]["albaranes"] = [{"referencia": campo("PEDIDO-1")}]
    extraccion["factura"]["ajustes"] = ["estructura no interpretable"]
    resultado, incidencias = ejecutar(extraccion, configuracion)

    factura = resultado["resultado_normalizado"]
    assert factura["albaranes"] == []
    assert factura["ajustes"] == []
    assert {x["campo"] for x in incidencias} >= {
        "albaranes[0]",
        "ajustes[0]",
    }


@pytest.mark.parametrize(
    "fila",
    (
        {"numero_albaran": campo(True)},
        {"fecha_albaran": campo("2026-09")},
        {"importe_total": campo("importe ambiguo")},
    ),
)
def test_albaran_estandar_con_valor_incompatible_se_bloquea(
    extraccion,
    configuracion,
    fila,
) -> None:
    extraccion["factura"]["albaranes"] = [fila]

    resultado, incidencias = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["albaranes"] == []
    assert [incidencia["tipo_incidencia"] for incidencia in incidencias] == [
        "ALBARAN_ESTANDAR_NO_INTERPRETABLE"
    ]


def test_concepto_estructurado_sin_semantica_fuerte_se_bloquea(
    extraccion,
    configuracion,
) -> None:
    extraccion["factura"]["ajustes"] = [
        {
            "tipo_ajuste": campo(None, evidencia=False),
            "descripcion": campo("BONIFICACION visible"),
            "importe": campo("-70,31"),
            "incluido_en_base": campo(True),
            "incluido_en_total": campo(True),
        }
    ]

    resultado, incidencias = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["ajustes"] == []
    assert [incidencia["tipo_incidencia"] for incidencia in incidencias] == [
        "CONCEPTO_ESTANDAR_NO_CLASIFICABLE"
    ]


def test_ajuste_seguro_pasa_al_constructor_mecanico(
    extraccion,
    configuracion,
) -> None:
    evidencia = "Descuento aplicado -10,00 EUR"
    extraccion["factura"]["ajustes"] = [
        {
            "tipo_ajuste": campo_con_evidencia("DESCUENTO", evidencia),
            "descripcion": campo_con_evidencia("Descuento aplicado", evidencia),
            "importe": campo_con_evidencia("-10,00", evidencia),
            "incluido_en_base": campo(True),
            "incluido_en_total": campo(True),
        }
    ]

    resultado, incidencias = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["ajustes"] == [
        {
            "orden": 1,
            "tipo_ajuste": "DESCUENTO",
            "descripcion": "Descuento aplicado",
            "importe": Decimal("-10.00"),
            "incluido_en_base": True,
            "incluido_en_total": True,
            "procedencia": {"tipo": "lectura_visible", "fuente": "luna_general"},
        }
    ]
    assert incidencias == []


def test_filas_mixtas_solo_conservan_ajustes_seguros_y_reordenan(
    extraccion,
    configuracion,
) -> None:
    def ajuste(tipo, descripcion, importe, evidencia):
        return {
            "tipo_ajuste": campo_con_evidencia(tipo, evidencia),
            "descripcion": campo_con_evidencia(descripcion, evidencia),
            "importe": campo_con_evidencia(importe, evidencia),
            "incluido_en_base": campo(True),
            "incluido_en_total": campo(True),
        }

    extraccion["factura"]["ajustes"] = [
        ajuste("OTRO", "Concepto", "3,00", "Concepto 3,00 EUR"),
        ajuste("DESCUENTO", "Descuento uno", "-4,00", "Descuento uno -4,00 EUR"),
        ajuste("IMPUESTO", "Total fiscal", "5,00", "Total fiscal 5,00 EUR"),
        ajuste("BONIFICACIÓN", "Bonificación", "-1,00", "Bonificación -1,00 EUR"),
    ]

    resultado, incidencias = ejecutar(extraccion, configuracion)
    ajustes = resultado["resultado_normalizado"]["ajustes"]

    assert [ajuste["orden"] for ajuste in ajustes] == [1, 2]
    assert [ajuste["importe"] for ajuste in ajustes] == [
        Decimal("-4.00"),
        Decimal("-1.00"),
    ]
    bloqueadas = [
        incidencia
        for incidencia in incidencias
        if incidencia["tipo_incidencia"] == "CONCEPTO_ESTANDAR_NO_CLASIFICABLE"
    ]
    assert [incidencia["campo"] for incidencia in bloqueadas] == [
        "ajustes[0]",
        "ajustes[2]",
    ]
    assert all(
        incidencia["datos_visibles_disponibles"]["clasificacion"] == "INCIERTO"
        for incidencia in bloqueadas
    )


def test_abono_estandar_conserva_signos_y_limites_visibles(
    extraccion,
    configuracion,
) -> None:
    general = extraccion["factura"]
    general["tipo_documento"] = campo("ABONO")
    general["base_imponible_total"] = campo("-86,83")
    general["iva_total"] = campo("-8,68")
    general["importe_total"] = campo("-95,51")
    general["impuestos"] = [
        {
            "base_imponible": campo("-86,83"),
            "tipo_iva": campo("10"),
            "cuota_iva": campo("-8,68"),
            "tipo_recargo_equivalencia": campo(None, evidencia=False),
            "cuota_recargo_equivalencia": campo(None, evidencia=False),
            "nota": campo(None, evidencia=False),
        }
    ]
    general["vencimientos"] = [
        {
            "fecha_vencimiento": campo("07-09-2026"),
            "importe": campo(None, evidencia=False),
            "nota": campo("Remesa"),
        }
    ]
    general["albaranes"] = [{"numero_albaran": campo("AB-0001")}]
    general["ajustes"] = [
        {
            "tipo_ajuste": campo_con_evidencia(
                "DESCUENTO", "Descuento visible -33,77 EUR"
            ),
            "descripcion": campo_con_evidencia(
                "Descuento visible", "Descuento visible -33,77 EUR"
            ),
            "importe": campo_con_evidencia(
                "-33,77", "Descuento visible -33,77 EUR"
            ),
            "incluido_en_base": campo(True),
            "incluido_en_total": campo(True),
        }
    ]

    resultado, incidencias = ejecutar(extraccion, configuracion)
    factura = resultado["resultado_normalizado"]

    assert factura["tipo_documento"] == "ABONO"
    assert factura["base_imponible_total"] == Decimal("-86.83")
    assert factura["impuestos"][0]["cuota_iva"] == Decimal("-8.68")
    assert factura["ajustes"][0]["importe"] == Decimal("-33.77")
    assert factura["vencimientos"][0]["importe"] is None
    assert factura["vencimientos"][0]["nota"] is None
    assert factura["albaranes"] == [
        {
            "orden": 1,
            "numero_albaran": "AB-0001",
            "fecha_albaran": None,
            "tipo_movimiento": None,
            "descripcion": None,
            "importe_base": None,
            "importe_total": None,
            "procedencia": {
                "tipo": "lectura_visible",
                "fuente": "luna_general",
            },
        }
    ]
    assert {incidencia["tipo_incidencia"] for incidencia in incidencias} == {
        "IMPORTE_VENCIMIENTO_NO_VISIBLE",
    }


def test_ausencia_de_ajustes_produce_lista_vacia(extraccion, configuracion) -> None:
    extraccion["factura"]["ajustes"] = []

    resultado, incidencias = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["ajustes"] == []
    assert incidencias == []


def test_ajuste_con_tipos_incompatibles_se_bloquea(
    extraccion,
    configuracion,
) -> None:
    extraccion["factura"]["ajustes"] = [
        {
            "tipo_ajuste": campo("DESCUENTO"),
            "descripcion": campo("Visible"),
            "importe": campo("1,00"),
            "incluido_en_base": campo("QUIZA"),
            "incluido_en_total": campo(True),
        }
    ]

    resultado, incidencias = ejecutar(extraccion, configuracion)

    assert resultado["resultado_normalizado"]["ajustes"] == []
    assert [incidencia["tipo_incidencia"] for incidencia in incidencias] == [
        "AJUSTE_ESTANDAR_NO_INTERPRETABLE"
    ]


def test_misma_entrada_y_fecha_fija_producen_salida_determinista(
    extraccion,
    configuracion,
) -> None:
    primero = ejecutar(deepcopy(extraccion), configuracion)
    segundo = ejecutar(deepcopy(extraccion), configuracion)
    assert primero == segundo


def test_dos_proveedores_usan_el_mismo_normalizador_solo_cambiando_configuracion(
    extraccion,
    configuracion,
) -> None:
    primero, _ = ejecutar(deepcopy(extraccion), configuracion)
    segunda_configuracion = ConfiguracionProveedor(
        proveedor_nombre_canonico="SEGUNDO PROVEEDOR, S.L.",
        aliases=("Segundo Proveedor",),
        categoria="SERVICIO",
        requiere_conciliacion_albaranes=False,
        farmacia="OTRA FARMACIA",
        id_farmacia="0099",
        metodo_identificacion_farmacia="CIF",
    )
    segunda_extraccion = deepcopy(extraccion)
    segunda_extraccion["factura"]["proveedor_nombre"] = campo("Segundo Proveedor")
    segundo, _ = ejecutar(segunda_extraccion, segunda_configuracion)

    assert primero["resultado_normalizado"]["proveedor_nombre"] == (
        "PROVEEDOR GENERAL, S.A."
    )
    assert segundo["resultado_normalizado"]["proveedor_nombre"] == (
        "SEGUNDO PROVEEDOR, S.L."
    )
    assert segundo["resultado_normalizado"]["destinatario"]["id_farmacia"] == "0099"


def test_registro_de_configuraciones_estandar_contiene_cuatro_politicas_estables() -> None:
    assert CONFIGURACION_HYGIE31.proveedor_nombre_canonico == "HYGIE31 ESPAÑA, S.L.U."
    assert CONFIGURACION_GUIMERA.proveedor_nombre_canonico == "FARMACIA GUIMERA C.B."
    assert CONFIGURACION_PIERRE_FABRE.proveedor_nombre_canonico == (
        "PIERRE FABRE IBÉRICA, S.A."
    )
    assert CONFIGURACION_ENDESA.proveedor_nombre_canonico == (
        "ENDESA ENERGÍA, S.A.U."
    )
    configuraciones = (
        CONFIGURACION_HYGIE31,
        CONFIGURACION_GUIMERA,
        CONFIGURACION_PIERRE_FABRE,
        CONFIGURACION_ENDESA,
    )
    assert {configuracion.id_farmacia for configuracion in configuraciones} == {
        "PIO"
    }
    assert all(
        not hasattr(configuracion, "archivo_origen")
        for configuracion in configuraciones
    )


def test_normalizador_estandar_esta_aislado_y_no_conoce_casos_concretos() -> None:
    rutas = (
        RAIZ / "src/facturas/normalizadores/estandar.py",
        RAIZ / "src/facturas/normalizadores/documento.py",
    )
    prohibidos = (
        "patron_oficial",
        "facturas/patron",
        "cargar_patron",
        ".env",
        "farmatic",
        "sql server",
        "supabase",
        "http://",
        "https://",
        "openai",
        "google",
        "azure",
        "ecoceutics",
        "guimer",
        "pierre",
        "endesa",
    )
    for ruta in rutas:
        texto = ruta.read_text(encoding="utf-8").casefold().replace("\\", "/")
        assert all(prohibido not in texto for prohibido in prohibidos)
