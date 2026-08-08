from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

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
    extraccion["factura"]["ajustes"] = [{"concepto": campo("DESCONOCIDO")}]
    resultado, incidencias = ejecutar(extraccion, configuracion)

    factura = resultado["resultado_normalizado"]
    assert factura["albaranes"] == []
    assert factura["ajustes"] == []
    assert {x["campo"] for x in incidencias} >= {"albaranes", "ajustes"}


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
    )
    for ruta in rutas:
        texto = ruta.read_text(encoding="utf-8").casefold().replace("\\", "/")
        assert all(prohibido not in texto for prohibido in prohibidos)
