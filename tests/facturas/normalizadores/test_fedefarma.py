from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.facturas.normalizadores.configuracion import ConfiguracionProveedor
from src.facturas.normalizadores.fedefarma import (
    ConfiguracionFedefarma,
    limpiar_etiqueta_albaran,
    normalizar_fedefarma,
)
from src.models.factura import serializar_valor


RAIZ = Path(__file__).resolve().parents[3]
RUTA_GENERAL = (
    RAIZ
    / "pruebas/facturas/resultados/openai/benchmark_luna_terra_sol_v1"
    / "general/caso_04/gpt-5.6-luna/estructurado.json"
)
RUTA_LITERAL = (
    RAIZ
    / "pruebas/facturas/resultados/openai/fedefarma_tablas_literales"
    / "estructurado.json"
)
INSTANTE = datetime(2026, 8, 7, tzinfo=timezone.utc)


def cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def ejecutar(
    general: dict | None = None,
    literal: dict | None = None,
    configuracion: ConfiguracionFedefarma | None = None,
    archivo_origen: str = "documento_fedefarma.pdf",
) -> tuple[dict, list[dict]]:
    entrada_general = general if general is not None else cargar(RUTA_GENERAL)
    entrada_literal = literal if literal is not None else cargar(RUTA_LITERAL)
    return normalizar_fedefarma(
        entrada_general,
        entrada_literal,
        entrada_general["metadatos_prueba"],
        configuracion
        or ConfiguracionFedefarma(
            usar_tablas_literales=True,
        ),
        fecha_ejecucion=INSTANTE,
        archivo_origen=archivo_origen,
    )


@pytest.fixture(scope="module")
def normalizado() -> tuple[dict, list[dict]]:
    return ejecutar()


def test_reconoce_fedefarma_por_alias_exacto(normalizado) -> None:
    assert normalizado[0]["resultado_normalizado"]["proveedor_nombre"] == (
        "FEDERACIÓ FARMACÈUTICA, S.COOP.C.L."
    )


def test_no_reconoce_fedefarma_por_subcadena() -> None:
    general = cargar(RUTA_GENERAL)
    general["factura"]["proveedor_nombre"]["valor"] = "SERVICIOS FEDEFARMA NORTE"
    resultado, incidencias = ejecutar(general=general)
    assert resultado["resultado_normalizado"]["proveedor_nombre"] == (
        "SERVICIOS FEDEFARMA NORTE"
    )
    assert any(
        x["tipo_incidencia"] == "PROVEEDOR_FEDEFARMA_NO_RECONOCIDO"
        for x in incidencias
    )


def test_numero_factura_fecha_y_cif(normalizado) -> None:
    factura = normalizado[0]["resultado_normalizado"]
    assert factura["tipo_documento"] == "FACTURA"
    assert factura["numero_factura"] == "VN2605-0005381"
    assert isinstance(factura["numero_factura"], str)
    assert factura["fecha_factura"] == "2026-07-20"
    assert factura["proveedor_cif"] == "F08173395"


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Albarán: 00123456", "00123456"),
        ("Nº Albarà: 0007-A", "0007-A"),
        ("PA 00123456", "PA 00123456"),
        ("2620A-196245", "2620A-196245"),
    ],
)
def test_limpieza_etiquetas_sin_alterar_identificador(entrada, esperado) -> None:
    assert limpiar_etiqueta_albaran(entrada) == esperado


def test_fusion_literal_recupera_todas_las_filas_sin_duplicados(normalizado) -> None:
    albaranes = normalizado[0]["resultado_normalizado"]["albaranes"]
    assert [x["numero_albaran"] for x in albaranes] == [
        "2620-2051956",
        "2620-2090700",
        "2620-2100818",
        "2620-2100853",
        "2620A-196245",
    ]
    assert len({x["numero_albaran"] for x in albaranes}) == len(albaranes)
    assert [x["orden"] for x in albaranes] == [1, 2, 3, 4, 5]


def test_albaranes_conservan_fechas_importes_signos_y_movimientos(normalizado) -> None:
    albaranes = normalizado[0]["resultado_normalizado"]["albaranes"]
    assert [x["fecha_albaran"] for x in albaranes] == [
        "2026-07-13",
        "2026-07-16",
        "2026-07-17",
        "2026-07-17",
        "2026-07-17",
    ]
    assert [x["importe_total"] for x in albaranes] == [
        Decimal("40.98"),
        Decimal("19.29"),
        Decimal("3.35"),
        Decimal("4.78"),
        Decimal("-14.04"),
    ]
    assert [x["tipo_movimiento"] for x in albaranes] == [
        "CARGO",
        "CARGO",
        "CARGO",
        "CARGO",
        "ABONO",
    ]
    assert all(x["importe_base"] is None for x in albaranes)


def test_procedencia_literal_pagina_y_seccion(normalizado) -> None:
    albaranes = normalizado[0]["resultado_normalizado"]["albaranes"]
    assert all(x["pagina"] == 2 for x in albaranes)
    assert albaranes[-1]["seccion"] == "DETALL ABONAMENTS"
    assert all(x["procedencia"]["fuente"] == "luna_tablas_literales" for x in albaranes)


@pytest.mark.parametrize("usar_literal", [False, None])
def test_false_y_none_bloquean_fallback_literal(usar_literal) -> None:
    resultado, incidencias = ejecutar(
        configuracion=ConfiguracionFedefarma(
            usar_tablas_literales=usar_literal,
        )
    )
    albaranes = resultado["resultado_normalizado"]["albaranes"]
    assert [x["numero_albaran"] for x in albaranes] == [
        "2620-2051956",
        "2620-2090700",
        "2620-2100818",
        "2620-2100853",
    ]
    assert any(x["tipo_incidencia"] == "FUSION_LITERAL_BLOQUEADA" for x in incidencias)


def test_fila_literal_incompleta_genera_incidencia() -> None:
    literal = cargar(RUTA_LITERAL)
    literal["transcripcion"]["filas"][0]["numero_albaran"] = None
    resultado, incidencias = ejecutar(literal=literal)
    assert len(resultado["resultado_normalizado"]["albaranes"]) == 5
    assert any(x["tipo_incidencia"] == "FILA_LITERAL_SIN_IDENTIFICADOR" for x in incidencias)


def test_albaran_sin_fecha_o_importes_no_se_completa() -> None:
    literal = cargar(RUTA_LITERAL)
    fila = literal["transcripcion"]["filas"][0]
    fila["fecha_entrega"] = None
    fila["importe"] = None
    resultado, incidencias = ejecutar(literal=literal)
    albaran = resultado["resultado_normalizado"]["albaranes"][0]
    assert albaran["fecha_albaran"] is None
    assert albaran["importe_total"] is None
    tipos = {x["tipo_incidencia"] for x in incidencias}
    assert {"ALBARAN_SIN_FECHA_VISIBLE", "ALBARAN_SIN_IMPORTE_VISIBLE"} <= tipos


def test_evidencia_ausente_no_se_completa() -> None:
    general = cargar(RUTA_GENERAL)
    general["factura"]["numero_factura"]["evidencias"] = []
    resultado, incidencias = ejecutar(general=general)
    assert resultado["resultado_normalizado"]["numero_factura"] is None
    assert any(x["tipo_incidencia"] == "ESTRUCTURA_INCOMPLETA" for x in incidencias)


def test_fiscalidad_descarta_solo_tramos_sin_importes(normalizado) -> None:
    factura = normalizado[0]["resultado_normalizado"]
    assert factura["impuestos"] == [
        {
            "orden": 1,
            "base_imponible": Decimal("20.38"),
            "tipo_iva": Decimal("4"),
            "cuota_iva": Decimal("0.82"),
            "tipo_recargo_equivalencia": Decimal("0.5"),
            "cuota_recargo_equivalencia": Decimal("0.1"),
            "nota": None,
        },
        {
            "orden": 2,
            "base_imponible": Decimal("37.06"),
            "tipo_iva": Decimal("10"),
            "cuota_iva": Decimal("3.71"),
            "tipo_recargo_equivalencia": Decimal("1.4"),
            "cuota_recargo_equivalencia": Decimal("0.52"),
            "nota": None,
        },
    ]
    assert {x["estado"] for x in normalizado[0]["validaciones_monetarias"]} == {"OK"}


def test_vencimiento_visible_y_sin_inferencia(normalizado) -> None:
    assert normalizado[0]["resultado_normalizado"]["vencimientos"] == [
        {
            "orden": 1,
            "fecha_vencimiento": "2026-08-05",
            "importe": Decimal("62.59"),
            "nota": None,
        }
    ]
    general = cargar(RUTA_GENERAL)
    general["factura"]["vencimientos"][0]["importe"]["evidencias"] = []
    resultado, _ = ejecutar(general=general)
    assert resultado["resultado_normalizado"]["vencimientos"][0]["importe"] is None


def test_ajustes_no_duplican_abono_y_conservan_bonificacion(normalizado) -> None:
    assert normalizado[0]["resultado_normalizado"]["ajustes"] == [
        {
            "orden": 1,
            "tipo_ajuste": "BONIFICACION",
            "descripcion": "Bonificación pago inmediato",
            "importe": Decimal("-0.08"),
            "incluido_en_base": True,
            "incluido_en_total": True,
            "procedencia": {
                "tipo": "regla_determinista",
                "fuente": "python",
                "regla": "clasificacion_bonificacion_fedefarma",
                "version_regla": "fedefarma_v1",
            },
        }
    ]


def test_configuracion_y_datos_documentales_destinatario() -> None:
    resultado, _ = ejecutar(
        configuracion=ConfiguracionFedefarma(
            categoria="INTERNA",
            requiere_conciliacion_albaranes=False,
            id_farmacia="0007",
            metodo_identificacion_farmacia="INTERNO",
            usar_tablas_literales=True,
        )
    )
    factura = resultado["resultado_normalizado"]
    assert factura["categoria"] == "INTERNA"
    assert factura["requiere_conciliacion_albaranes"] is False
    assert factura["destinatario"] == {
        "id_farmacia": "0007",
        "nombre": "PUIG SALOMON PIO",
        "cif": "40901058C",
        "metodo_identificacion": "INTERNO",
    }


def test_paginas_metadatos_y_fecha_cargo_bloqueada(normalizado) -> None:
    resultado = normalizado[0]
    assert resultado["paginas_originales"] == [1, 2]
    assert resultado["resultado_normalizado"]["fecha_cargo"] is None
    assert resultado["procedencia_bloques"]["paginas"] == "metadato_tecnico"


def test_configuracion_comun_reutilizable_con_archivos_fuera_de_politica() -> None:
    configuracion = ConfiguracionFedefarma(usar_tablas_literales=True)
    assert isinstance(configuracion, ConfiguracionProveedor)
    assert not hasattr(configuracion, "archivo_origen")

    primero, incidencias_primero = ejecutar(
        configuracion=configuracion,
        archivo_origen="fedefarma_uno.pdf",
    )
    segundo, incidencias_segundo = ejecutar(
        configuracion=configuracion,
        archivo_origen="fedefarma_dos.pdf",
    )

    assert primero["archivo_origen"] == "fedefarma_uno.pdf"
    assert segundo["archivo_origen"] == "fedefarma_dos.pdf"
    assert primero["resultado_normalizado"] == segundo["resultado_normalizado"]
    assert primero["configuracion_interna_aplicada"] == segundo[
        "configuracion_interna_aplicada"
    ]
    assert incidencias_primero == incidencias_segundo


def test_adaptador_usa_cabecera_y_destinatario_comunes() -> None:
    texto = (RAIZ / "src/facturas/normalizadores/fedefarma.py").read_text(
        encoding="utf-8"
    )
    assert "class ConfiguracionFedefarma(ConfiguracionProveedor)" in texto
    assert "construir_cabecera_documental(" in texto
    assert "construir_destinatario(" in texto


def test_determinismo() -> None:
    assert serializar_valor(ejecutar()) == serializar_valor(ejecutar())


def test_aislamiento_del_patron_y_servicios_externos() -> None:
    rutas = (
        RAIZ / "src/facturas/normalizadores/fedefarma.py",
        RAIZ / "src/facturas/normalizar_fedefarma.py",
        RAIZ / "src/facturas/motores/openai/extraer_tablas_fedefarma.py",
    )
    prohibidos_produccion = (
        "patron_oficial",
        "facturas/patron",
        "cargar_patron",
        "evaluar_",
        "farmatic",
        "sql server",
        "supabase",
    )
    for ruta in rutas:
        texto = ruta.read_text(encoding="utf-8").casefold().replace("\\", "/")
        assert all(x not in texto for x in prohibidos_produccion)
    normalizador = rutas[0].read_text(encoding="utf-8").casefold()
    assert ".env" not in normalizador
    assert "openai" not in normalizador
    assert "http://" not in normalizador and "https://" not in normalizador
