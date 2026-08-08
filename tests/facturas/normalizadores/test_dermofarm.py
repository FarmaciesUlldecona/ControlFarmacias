from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.facturas.normalizadores.dermofarm import (
    ConfiguracionDermofarm,
    normalizar_dermofarm,
)
from src.models.factura import serializar_valor


RAIZ = Path(__file__).resolve().parents[3]
ENTRADA = RAIZ / "pruebas/facturas/resultados/openai/muestra_completa/documento_01"
RUTA_EXTRACCION = ENTRADA / "estructurado.json"
RUTA_METADATOS = ENTRADA / "metadatos_entrada.json"
INSTANTE = datetime(2026, 8, 7, tzinfo=timezone.utc)


def cargar(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def normalizado() -> tuple[dict, list[dict]]:
    return normalizar_dermofarm(
        cargar(RUTA_EXTRACCION),
        cargar(RUTA_METADATOS),
        ConfiguracionDermofarm(),
        fecha_ejecucion=INSTANTE,
        archivo_origen="documento_01.pdf",
    )


def test_reconoce_dermofarm_por_alias_exacto(normalizado) -> None:
    resultado, _ = normalizado
    assert resultado["resultado_normalizado"]["proveedor_nombre"] == "DERMOFARM, S.A.U."


def test_no_reconoce_dermofarm_por_subcadena() -> None:
    extraccion = cargar(RUTA_EXTRACCION)
    extraccion["factura"]["proveedor_nombre"]["valor"] = "DERMOFARMACIA DEL SUR"
    resultado, incidencias = normalizar_dermofarm(
        extraccion,
        cargar(RUTA_METADATOS),
        ConfiguracionDermofarm(),
        fecha_ejecucion=INSTANTE,
        archivo_origen="documento_01.pdf",
    )
    assert resultado["resultado_normalizado"]["proveedor_nombre"] == "DERMOFARMACIA DEL SUR"
    assert any(x["tipo_incidencia"] == "PROVEEDOR_DERMOFARM_NO_RECONOCIDO" for x in incidencias)


def test_tipo_numero_fecha_y_cif(normalizado) -> None:
    factura = normalizado[0]["resultado_normalizado"]
    assert factura["tipo_documento"] == "ABONO"
    assert factura["numero_factura"] == "2700282621"
    assert isinstance(factura["numero_factura"], str)
    assert factura["fecha_factura"] == "2026-07-17"
    assert factura["proveedor_cif"] == "A08283624"


def test_signos_contables_del_abono(normalizado) -> None:
    factura = normalizado[0]["resultado_normalizado"]
    assert factura["base_imponible_total"] == Decimal("-86.65")
    assert factura["iva_total"] == Decimal("-18.2")
    assert factura["recargo_equivalencia_total"] == Decimal("-4.51")
    assert factura["importe_total"] == Decimal("-109.36")


def test_sin_evidencia_de_abono_no_corrige_signos() -> None:
    extraccion = cargar(RUTA_EXTRACCION)
    extraccion["factura"]["tipo_documento"]["evidencias"] = []
    resultado, incidencias = normalizar_dermofarm(
        extraccion,
        cargar(RUTA_METADATOS),
        ConfiguracionDermofarm(),
        fecha_ejecucion=INSTANTE,
        archivo_origen="documento_01.pdf",
    )
    factura = resultado["resultado_normalizado"]
    assert factura["tipo_documento"] is None
    assert factura["importe_total"] == Decimal("109.36")
    assert any(x["tipo_incidencia"] == "TIPO_ABONO_NO_DEMOSTRADO" for x in incidencias)


def test_fiscalidad_unificada_y_validada(normalizado) -> None:
    resultado, _ = normalizado
    impuestos = resultado["resultado_normalizado"]["impuestos"]
    assert impuestos == [
        {
            "orden": 1,
            "base_imponible": Decimal("-86.65"),
            "tipo_iva": Decimal("21.0"),
            "cuota_iva": Decimal("-18.2"),
            "tipo_recargo_equivalencia": Decimal("5.2"),
            "cuota_recargo_equivalencia": Decimal("-4.51"),
        }
    ]
    assert {x["estado"] for x in resultado["validaciones_monetarias"]} == {"OK"}


def test_total_sin_evidencia_permanece_ausente() -> None:
    extraccion = cargar(RUTA_EXTRACCION)
    extraccion["factura"]["importe_total"]["evidencias"] = []
    resultado, incidencias = normalizar_dermofarm(
        extraccion,
        cargar(RUTA_METADATOS),
        ConfiguracionDermofarm(),
        fecha_ejecucion=INSTANTE,
        archivo_origen="documento_01.pdf",
    )
    assert resultado["resultado_normalizado"]["importe_total"] is None
    assert resultado["validaciones_monetarias"][0]["estado"] == "NO_EVALUABLE"
    assert any(x["tipo_incidencia"] == "VALIDACION_MONETARIA_NO_EVALUABLE" for x in incidencias)


def test_albaran_solo_con_datos_demostrados(normalizado) -> None:
    albaranes = normalizado[0]["resultado_normalizado"]["albaranes"]
    assert len(albaranes) == 1
    assert albaranes[0]["numero_albaran"] == "25026140"
    assert isinstance(albaranes[0]["numero_albaran"], str)
    assert albaranes[0]["fecha_albaran"] == "2026-07-17"
    assert albaranes[0]["tipo_movimiento"] == "ABONO"
    assert albaranes[0]["importe_base"] is None
    assert albaranes[0]["importe_total"] is None


def test_no_inventa_vencimientos_ajustes_ni_relaciones_futuras(normalizado) -> None:
    factura = normalizado[0]["resultado_normalizado"]
    assert factura["vencimientos"] == []
    assert factura["ajustes"] == []
    assert "compensacion" not in factura


def test_configuracion_interna_no_procede_de_luna() -> None:
    resultado, _ = normalizar_dermofarm(
        cargar(RUTA_EXTRACCION),
        cargar(RUTA_METADATOS),
        ConfiguracionDermofarm(
            farmacia="PRUEBA",
            categoria="CATEGORIA_INTERNA",
            requiere_conciliacion_albaranes=False,
            id_farmacia="0007",
            metodo_identificacion_farmacia="INTERNO",
        ),
        fecha_ejecucion=INSTANTE,
        archivo_origen="documento_01.pdf",
    )
    factura = resultado["resultado_normalizado"]
    assert factura["categoria"] == "CATEGORIA_INTERNA"
    assert factura["requiere_conciliacion_albaranes"] is False
    assert factura["destinatario"]["id_farmacia"] == "0007"
    assert factura["destinatario"]["metodo_identificacion"] == "INTERNO"


def test_paginas_proceden_de_metadatos(normalizado) -> None:
    resultado, _ = normalizado
    assert resultado["paginas_originales"] == [1, 1]
    assert resultado["procedencia_bloques"]["paginas"] == "metadato_tecnico"


def test_determinismo() -> None:
    argumentos = (
        cargar(RUTA_EXTRACCION),
        cargar(RUTA_METADATOS),
        ConfiguracionDermofarm(),
    )
    primero = serializar_valor(
        normalizar_dermofarm(
            *argumentos,
            fecha_ejecucion=INSTANTE,
            archivo_origen="documento_01.pdf",
        )
    )
    segundo = serializar_valor(
        normalizar_dermofarm(
            *argumentos,
            fecha_ejecucion=INSTANTE,
            archivo_origen="documento_01.pdf",
        )
    )
    assert primero == segundo


def test_aislamiento_del_normalizador() -> None:
    rutas = (
        RAIZ / "src/facturas/normalizadores/dermofarm.py",
        RAIZ / "src/facturas/normalizar_dermofarm.py",
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
        "compensacion",
        "mes siguiente",
    )
    for ruta in rutas:
        texto = ruta.read_text(encoding="utf-8").casefold().replace("\\", "/")
        assert all(prohibido not in texto for prohibido in prohibidos)
        assert "import openai" not in texto and "from openai" not in texto
        assert "import google" not in texto and "from google" not in texto
        assert "import azure" not in texto and "from azure" not in texto
