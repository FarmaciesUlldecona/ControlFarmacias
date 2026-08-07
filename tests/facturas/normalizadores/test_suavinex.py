from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.facturas.normalizadores.suavinex import (
    ConfiguracionSuavinex,
    normalizar_suavinex,
)
from src.models.factura import serializar_valor


RAIZ = Path(__file__).resolve().parents[3]
RUTA_EXTRACCION = (
    RAIZ
    / "pruebas/facturas/resultados/openai/benchmark_luna_terra_sol_v1"
    / "general/caso_03/gpt-5.6-luna/estructurado.json"
)
INSTANTE = datetime(2026, 8, 7, tzinfo=timezone.utc)


def cargar() -> dict:
    return json.loads(RUTA_EXTRACCION.read_text(encoding="utf-8"))


def ejecutar(
    extraccion: dict | None = None,
    configuracion: ConfiguracionSuavinex | None = None,
) -> tuple[dict, list[dict]]:
    datos = extraccion or cargar()
    return normalizar_suavinex(
        datos,
        datos["metadatos_prueba"],
        configuracion
        or ConfiguracionSuavinex(
            archivo_origen="documento_suavinex.pdf",
            albaran_unico_abarca_factura=True,
        ),
        fecha_ejecucion=INSTANTE,
    )


@pytest.fixture(scope="module")
def normalizado() -> tuple[dict, list[dict]]:
    return ejecutar()


def test_reconoce_suavinex_por_alias_exacto(normalizado) -> None:
    factura = normalizado[0]["resultado_normalizado"]
    assert factura["proveedor_nombre"] == "SUAVINEX GROUP, S.L."


def test_no_reconoce_suavinex_por_subcadena() -> None:
    extraccion = cargar()
    extraccion["factura"]["proveedor_nombre"]["valor"] = "DISTRIBUCIONES SUAVINEX SUR"
    resultado, incidencias = ejecutar(extraccion)
    assert resultado["resultado_normalizado"]["proveedor_nombre"] == (
        "DISTRIBUCIONES SUAVINEX SUR"
    )
    assert any(
        x["tipo_incidencia"] == "PROVEEDOR_SUAVINEX_NO_RECONOCIDO"
        for x in incidencias
    )


def test_identificadores_fecha_y_cif(normalizado) -> None:
    factura = normalizado[0]["resultado_normalizado"]
    assert factura["tipo_documento"] == "FACTURA"
    assert factura["numero_factura"] == "0702638508"
    assert isinstance(factura["numero_factura"], str)
    assert factura["fecha_factura"] == "2026-06-19"
    assert factura["proveedor_cif"] == "B03074093"


def test_fiscalidad_separa_cuota_agregada_con_decimal(normalizado) -> None:
    factura = normalizado[0]["resultado_normalizado"]
    assert factura["base_imponible_total"] == Decimal("531.26")
    assert factura["iva_total"] == Decimal("111.56")
    assert factura["recargo_equivalencia_total"] == Decimal("27.63")
    assert factura["importe_total"] == Decimal("670.45")
    assert factura["impuestos"] == [
        {
            "orden": 1,
            "base_imponible": Decimal("531.26"),
            "tipo_iva": Decimal("21.0"),
            "cuota_iva": Decimal("111.56"),
            "tipo_recargo_equivalencia": Decimal("5.2"),
            "cuota_recargo_equivalencia": Decimal("27.63"),
            "nota": "El PDF agrupa IVA y recargo en una cuota total de 139,19 €",
        }
    ]


def test_validaciones_monetarias_correctas(normalizado) -> None:
    validaciones = normalizado[0]["validaciones_monetarias"]
    assert [x["nombre"] for x in validaciones] == [
        "total_factura",
        "cuota_fiscal_agregada",
        "cuota_iva",
        "cuota_recargo_equivalencia",
    ]
    assert {x["estado"] for x in validaciones} == {"OK"}
    assert {x["tolerancia"] for x in validaciones} == {"0.01"}


def test_fiscalidad_sin_evidencia_no_se_completa() -> None:
    extraccion = cargar()
    extraccion["factura"]["impuestos"][0]["tipo_recargo_equivalencia"][
        "evidencias"
    ] = []
    resultado, incidencias = ejecutar(extraccion)
    factura = resultado["resultado_normalizado"]
    assert factura["iva_total"] is None
    assert factura["recargo_equivalencia_total"] is None
    assert factura["impuestos"] == []
    assert any(x["tipo_incidencia"] == "SEPARACION_FISCAL_BLOQUEADA" for x in incidencias)


def test_vencimiento_solo_con_fecha_e_importe_visibles(normalizado) -> None:
    vencimiento = normalizado[0]["resultado_normalizado"]["vencimientos"][0]
    assert vencimiento == {
        "orden": 1,
        "fecha_vencimiento": "2026-08-19",
        "importe": Decimal("670.45"),
        "nota": None,
    }


def test_vencimiento_sin_importe_no_recibe_total_factura() -> None:
    extraccion = cargar()
    extraccion["factura"]["vencimientos"][0]["importe"]["evidencias"] = []
    resultado, incidencias = ejecutar(extraccion)
    vencimiento = resultado["resultado_normalizado"]["vencimientos"][0]
    assert vencimiento["importe"] is None
    assert any(
        x["tipo_incidencia"] == "IMPORTE_VENCIMIENTO_NO_VISIBLE"
        for x in incidencias
    )


def test_ajuste_punto_verde(normalizado) -> None:
    assert normalizado[0]["resultado_normalizado"]["ajustes"] == [
        {
            "orden": 1,
            "tipo_ajuste": "OTRO",
            "descripcion": "Información punto verde",
            "importe": Decimal("1.9"),
            "incluido_en_base": True,
            "incluido_en_total": True,
            "procedencia": {
                "tipo": "regla_determinista",
                "fuente": "python",
                "regla": "clasificacion_punto_verde_suavinex",
                "version_regla": "suavinex_v1",
            },
        }
    ]


def test_albaran_unico_y_dato_incompatible_bloqueado(normalizado) -> None:
    albaran = normalizado[0]["resultado_normalizado"]["albaranes"][0]
    assert albaran["numero_albaran"] == "81109681"
    assert isinstance(albaran["numero_albaran"], str)
    assert albaran["fecha_albaran"] is None
    assert albaran["tipo_movimiento"] == "CARGO"
    assert albaran["descripcion"] is None
    assert albaran["importe_base"] == Decimal("531.26")
    assert albaran["importe_total"] == Decimal("670.45")
    assert any(
        x["tipo_incidencia"]
        == "REFERENCIA_PEDIDO_BLOQUEADA_COMO_DESCRIPCION_ALBARAN"
        for x in normalizado[1]
    )


@pytest.mark.parametrize("relacion", [False, None])
def test_false_y_none_bloquean_importes_del_albaran(relacion) -> None:
    resultado, incidencias = ejecutar(
        configuracion=ConfiguracionSuavinex(
            archivo_origen="documento_suavinex.pdf",
            albaran_unico_abarca_factura=relacion,
        )
    )
    albaran = resultado["resultado_normalizado"]["albaranes"][0]
    assert albaran["importe_base"] is None
    assert albaran["importe_total"] is None
    assert any(
        x["tipo_incidencia"] == "RELACION_IMPORTES_ALBARAN_NO_DEMOSTRADA"
        for x in incidencias
    )


def test_no_aplica_signos_de_abono_dermofarm() -> None:
    extraccion = cargar()
    for campo in ("base_imponible_total", "importe_total"):
        extraccion["factura"][campo]["valor"] *= -1
    resultado, _ = ejecutar(
        extraccion,
        ConfiguracionSuavinex(archivo_origen="documento_suavinex.pdf"),
    )
    factura = resultado["resultado_normalizado"]
    assert factura["base_imponible_total"] == Decimal("-531.26")
    assert factura["importe_total"] == Decimal("-670.45")


def test_campo_sin_evidencia_permanece_ausente() -> None:
    extraccion = cargar()
    extraccion["factura"]["numero_factura"]["evidencias"] = []
    resultado, incidencias = ejecutar(extraccion)
    assert resultado["resultado_normalizado"]["numero_factura"] is None
    assert any(x["tipo_incidencia"] == "ESTRUCTURA_INCOMPLETA" for x in incidencias)


def test_configuracion_interna_no_procede_de_luna() -> None:
    resultado, _ = ejecutar(
        configuracion=ConfiguracionSuavinex(
            archivo_origen="documento_suavinex.pdf",
            farmacia="PRUEBA",
            categoria="CATEGORIA_INTERNA",
            requiere_conciliacion_albaranes=False,
            destinatario_id_farmacia="0007",
            destinatario_metodo_identificacion="INTERNO",
            albaran_unico_abarca_factura=True,
        )
    )
    factura = resultado["resultado_normalizado"]
    assert factura["categoria"] == "CATEGORIA_INTERNA"
    assert factura["requiere_conciliacion_albaranes"] is False
    assert factura["destinatario"] == {
        "id_farmacia": "0007",
        "nombre": "PUIG SALOMON, PIO",
        "cif": "40901058C",
        "metodo_identificacion": "INTERNO",
    }


def test_paginas_proceden_de_metadatos(normalizado) -> None:
    resultado = normalizado[0]
    assert resultado["paginas_originales"] == [1, 1]
    assert resultado["procedencia_bloques"]["paginas"] == "metadato_tecnico"


def test_determinismo() -> None:
    primero = serializar_valor(ejecutar())
    segundo = serializar_valor(ejecutar())
    assert primero == segundo


def test_aislamiento_del_normalizador() -> None:
    rutas = (
        RAIZ / "src/facturas/normalizadores/suavinex.py",
        RAIZ / "src/facturas/normalizar_suavinex.py",
    )
    prohibidos = (
        "patron_oficial",
        "facturas/patron",
        "cargar_patron",
        "evaluar_",
        ".env",
        "farmatic",
        "sql server",
        "supabase",
        "http://",
        "https://",
    )
    for ruta in rutas:
        texto = ruta.read_text(encoding="utf-8").casefold().replace("\\", "/")
        assert all(prohibido not in texto for prohibido in prohibidos)
        assert "import openai" not in texto and "from openai" not in texto
        assert "import google" not in texto and "from google" not in texto
        assert "import azure" not in texto and "from azure" not in texto
