from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from src.facturas.normalizadores.comun import RegistroIncidencias
from src.facturas.normalizadores.configuracion import ConfiguracionProveedor
from src.facturas.normalizadores.documento import (
    construir_cabecera_documental,
    construir_destinatario,
    ensamblar_factura_normalizada,
    normalizar_identificador_fiscal_es,
    normalizar_proveedor_documental,
    paginas_desde_metadatos,
)
from src.facturas.normalizadores.dermofarm import (
    ConfiguracionDermofarm,
    normalizar_dermofarm,
)


RAIZ = Path(__file__).resolve().parents[3]


def campo(valor, *, con_evidencia: bool = True) -> dict:
    return {
        "valor": valor,
        "evidencias": ([{"texto_visible": str(valor), "pagina": 1}] if con_evidencia else []),
    }


@pytest.fixture
def configuracion() -> ConfiguracionProveedor:
    return ConfiguracionProveedor(
        proveedor_nombre_canonico="PROVEEDOR, S.A.",
        aliases=("PROVEEDOR", "PROVEEDOR SA"),
        farmacia="FARMACIA_INTERNA",
        categoria="MERCANCIA",
        requiere_conciliacion_albaranes=True,
        id_farmacia="0007",
        metodo_identificacion_farmacia="CIF",
    )


def test_configuracion_representa_politica_repetida(configuracion) -> None:
    assert configuracion.proveedor_nombre_canonico == "PROVEEDOR, S.A."
    assert configuracion.aliases == ("PROVEEDOR", "PROVEEDOR SA")
    assert configuracion.categoria == "MERCANCIA"
    assert configuracion.requiere_conciliacion_albaranes is True
    assert configuracion.farmacia == "FARMACIA_INTERNA"
    assert configuracion.id_farmacia == "0007"
    assert configuracion.metodo_identificacion_farmacia == "CIF"


def test_configuracion_no_contiene_contexto_variable_de_archivo() -> None:
    nombres = {campo_configuracion.name for campo_configuracion in fields(ConfiguracionProveedor)}
    assert "archivo_origen" not in nombres


def test_misma_configuracion_sirve_a_documentos_con_origen_independiente() -> None:
    entrada = RAIZ / "pruebas/facturas/resultados/openai/muestra_completa/documento_01"
    extraccion = json.loads((entrada / "estructurado.json").read_text(encoding="utf-8"))
    metadatos = json.loads(
        (entrada / "metadatos_entrada.json").read_text(encoding="utf-8")
    )
    configuracion = ConfiguracionDermofarm()
    instante = datetime(2026, 8, 8, tzinfo=timezone.utc)

    primero, incidencias_primero = normalizar_dermofarm(
        extraccion,
        metadatos,
        configuracion,
        fecha_ejecucion=instante,
        archivo_origen="documento_uno.pdf",
    )
    segundo, incidencias_segundo = normalizar_dermofarm(
        extraccion,
        metadatos,
        configuracion,
        fecha_ejecucion=instante,
        archivo_origen="documento_dos.pdf",
    )

    assert primero["archivo_origen"] == "documento_uno.pdf"
    assert segundo["archivo_origen"] == "documento_dos.pdf"
    assert primero["configuracion_interna_aplicada"] == segundo[
        "configuracion_interna_aplicada"
    ]
    assert primero["resultado_normalizado"] == segundo["resultado_normalizado"]
    assert primero["procedencia_bloques"] == segundo["procedencia_bloques"]
    assert incidencias_primero == incidencias_segundo


@pytest.mark.parametrize(
    ("visible", "esperado", "reconocido"),
    [
        ("PROVEEDOR", "PROVEEDOR, S.A.", True),
        ("OTRO PROVEEDOR", "OTRO PROVEEDOR", False),
        ("DISTRIBUCIONES PROVEEDOR SUR", "DISTRIBUCIONES PROVEEDOR SUR", False),
    ],
)
def test_proveedor_exige_coincidencia_completa(
    configuracion, visible, esperado, reconocido
) -> None:
    original, normalizado, coincide = normalizar_proveedor_documental(
        campo(visible), configuracion
    )
    assert original == visible
    assert normalizado == esperado
    assert coincide is reconocido


def test_cabecera_normaliza_campos_documentales(configuracion) -> None:
    general = {
        "tipo_documento": campo("FACTURA"),
        "proveedor_nombre": campo("PROVEEDOR"),
        "proveedor_cif": campo("A00123456"),
        "numero_factura": campo("0000123"),
        "fecha_factura": campo("08-08-2026"),
    }
    _, proveedor, _ = normalizar_proveedor_documental(
        general["proveedor_nombre"], configuracion
    )
    cabecera = construir_cabecera_documental(
        general,
        {"paginas_originales": [4, 6], "numero_paginas": 99},
        configuracion,
        RegistroIncidencias(),
        tipo_documento="FACTURA",
        proveedor_nombre=proveedor,
        normalizar_cif=lambda valor, _incidencias: valor,
    )
    assert cabecera == {
        "tipo_documento": "FACTURA",
        "categoria": "MERCANCIA",
        "requiere_conciliacion_albaranes": True,
        "pagina_inicio": 4,
        "pagina_fin": 6,
        "proveedor_nombre": "PROVEEDOR, S.A.",
        "proveedor_cif": "A00123456",
        "numero_factura": "0000123",
        "fecha_factura": "2026-08-08",
    }


def test_cabecera_no_inventa_fecha_tipo_ni_paginas(configuracion) -> None:
    general = {
        "fecha_factura": campo("08-08-2026", con_evidencia=False),
        "tipo_documento": campo("FACTURA", con_evidencia=False),
    }
    cabecera = construir_cabecera_documental(
        general,
        {"numero_paginas": 2},
        configuracion,
        RegistroIncidencias(),
        tipo_documento=None,
        proveedor_nombre=None,
        normalizar_cif=lambda valor, _incidencias: valor,
    )
    assert cabecera["fecha_factura"] is None
    assert cabecera["tipo_documento"] is None
    assert (cabecera["pagina_inicio"], cabecera["pagina_fin"]) == (1, 2)


@pytest.mark.parametrize("metadatos", [{}, {"numero_paginas": 0}, {"paginas_originales": [2, 1]}])
def test_paginas_ausentes_o_invalidas_se_bloquean(metadatos) -> None:
    with pytest.raises(ValueError):
        paginas_desde_metadatos(metadatos)


def test_identificador_fiscal_es_solo_elimina_prefijo_en_forma_completa() -> None:
    incidencias = RegistroIncidencias()
    assert normalizar_identificador_fiscal_es(
        "ES A00123456", incidencias, etiqueta_visible="VAT"
    ) == "A00123456"
    assert normalizar_identificador_fiscal_es(
        "ES- A00123456", incidencias, etiqueta_visible="VAT"
    ) == "ES- A00123456"
    assert incidencias.como_lista()[0]["tipo_incidencia"] == "PREFIJO_PAIS_ELIMINADO"


def test_destinatario_separa_datos_visibles_e_internos(configuracion) -> None:
    destinatario = construir_destinatario(
        {
            "nombre": campo("PUIG SALOMON, PIO"),
            "cif": campo("40901058C"),
            "id_farmacia": campo("ID DEL MODELO"),
            "metodo_identificacion": campo("METODO DEL MODELO"),
        },
        configuracion,
    )
    assert destinatario == {
        "id_farmacia": "0007",
        "nombre": "PUIG SALOMON, PIO",
        "cif": "40901058C",
        "metodo_identificacion": "CIF",
    }
    assert destinatario["nombre"] != configuracion.farmacia


def test_destinatario_sin_evidencia_documental_conserva_null(configuracion) -> None:
    destinatario = construir_destinatario(
        {
            "nombre": campo("NOMBRE NO DEMOSTRADO", con_evidencia=False),
            "cif": campo("CIF NO DEMOSTRADO", con_evidencia=False),
        },
        configuracion,
    )
    assert destinatario["nombre"] is None
    assert destinatario["cif"] is None
    assert destinatario["id_farmacia"] == "0007"
    assert destinatario["metodo_identificacion"] == "CIF"


def test_aislamiento_de_la_capa_documental() -> None:
    rutas = (
        RAIZ / "src/facturas/normalizadores/configuracion.py",
        RAIZ / "src/facturas/normalizadores/documento.py",
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
        "openai",
        "google",
        "azure",
    )
    for ruta in rutas:
        texto = ruta.read_text(encoding="utf-8").casefold().replace("\\", "/")
        assert all(prohibido not in texto for prohibido in prohibidos)


def argumentos_ensamblado(configuracion) -> dict:
    return {
        "cabecera": {
            "tipo_documento": "FACTURA",
            "categoria": "MERCANCIA",
            "requiere_conciliacion_albaranes": True,
            "pagina_inicio": 2,
            "pagina_fin": 3,
            "proveedor_nombre": "PROVEEDOR, S.A.",
            "proveedor_cif": "A00123456",
            "numero_factura": "0000123",
            "fecha_factura": "2026-08-08",
        },
        "base_imponible_total": Decimal("100.00"),
        "iva_total": Decimal("21.00"),
        "recargo_equivalencia_total": None,
        "importe_total": Decimal("121.00"),
        "vencimientos": [],
        "impuestos": [],
        "albaranes": [],
        "ajustes": [],
        "destinatario": {
            "id_farmacia": "0007",
            "nombre": "FARMACIA VISIBLE",
            "cif": "40901058C",
            "metodo_identificacion": "CIF",
        },
        "incidencias": RegistroIncidencias(),
        "version_normalizador": "proveedor_v1",
        "archivo_origen": "factura_0001.pdf",
        "procedencia_bloques": {"cabecera": "lectura_visible"},
        "configuracion": configuracion,
        "validaciones_monetarias": [],
        "fecha_ejecucion": datetime(2026, 8, 8, 10, 30, tzinfo=timezone.utc),
    }


def test_ensamblador_minimo_preserva_decimales_ids_listas_y_contexto(
    configuracion,
) -> None:
    argumentos = argumentos_ensamblado(configuracion)
    resultado = ensamblar_factura_normalizada(**argumentos)
    factura = resultado["resultado_normalizado"]

    assert factura["base_imponible_total"] == Decimal("100.00")
    assert factura["numero_factura"] == "0000123"
    assert factura["vencimientos"] == factura["impuestos"] == []
    assert resultado["version_normalizador"] == "proveedor_v1"
    assert resultado["archivo_origen"] == "factura_0001.pdf"
    assert resultado["paginas_originales"] == [2, 3]
    assert resultado["fecha_ejecucion"] == "2026-08-08T10:30:00+00:00"
    assert argumentos["incidencias"].como_lista() == []


def test_ensamblador_admite_todos_los_bloques_y_campos_opcionales(
    configuracion,
) -> None:
    argumentos = argumentos_ensamblado(configuracion)
    argumentos.update(
        vencimientos=[
            {
                "orden": 1,
                "fecha_vencimiento": "2026-09-01",
                "importe": Decimal("121.00"),
            }
        ],
        impuestos=[
            {
                "orden": 1,
                "base_imponible": Decimal("100.00"),
                "tipo_iva": Decimal("21"),
                "cuota_iva": Decimal("21.00"),
                "tipo_recargo_equivalencia": None,
                "cuota_recargo_equivalencia": None,
            }
        ],
        albaranes=[
            {
                "orden": 1,
                "numero_albaran": "000045",
                "fecha_albaran": "2026-08-01",
                "tipo_movimiento": "VENTA",
                "importe_base": Decimal("100.00"),
                "importe_total": Decimal("121.00"),
            }
        ],
        ajustes=[
            {
                "orden": 1,
                "tipo_ajuste": "DESCUENTO",
                "descripcion": "Visible",
                "importe": Decimal("1.00"),
                "incluido_en_base": True,
                "incluido_en_total": True,
            }
        ],
        fecha_cargo="2026-09-01",
        periodo_facturacion_inicio="2026-08-01",
        periodo_facturacion_fin="2026-08-08",
        nota_revision="Revisar soporte visible",
    )
    resultado = ensamblar_factura_normalizada(**argumentos)
    factura = resultado["resultado_normalizado"]

    assert factura["vencimientos"] is argumentos["vencimientos"]
    assert factura["impuestos"] is argumentos["impuestos"]
    assert factura["albaranes"][0]["numero_albaran"] == "000045"
    assert factura["ajustes"] is argumentos["ajustes"]
    assert factura["fecha_cargo"] == "2026-09-01"
    assert argumentos["incidencias"].como_lista() == []


def test_ensamblador_registra_errores_estructurales_uniformes(configuracion) -> None:
    argumentos = argumentos_ensamblado(configuracion)
    argumentos["cabecera"] = {**argumentos["cabecera"], "numero_factura": None}
    ensamblar_factura_normalizada(**argumentos)

    assert argumentos["incidencias"].como_lista() == [
        {
            "orden": 1,
            "campo": "factura",
            "tipo_incidencia": "ESTRUCTURA_INCOMPLETA",
            "nivel": "REVISION_MANUAL",
            "descripcion": "Falta numero_factura.",
            "datos_visibles_disponibles": None,
            "decision_tomada": "Se conserva null; no se completa el campo.",
            "requiere_revision_manual": True,
        }
    ]


def test_ensamblador_no_oculta_errores_de_conversion_del_modelo(configuracion) -> None:
    argumentos = argumentos_ensamblado(configuracion)
    argumentos["impuestos"] = [{"orden": "no-numerico"}]
    with pytest.raises(ValueError):
        ensamblar_factura_normalizada(**argumentos)


def test_ensamblador_aplica_configuracion_estable_y_extension_explicita(
    configuracion,
) -> None:
    argumentos = argumentos_ensamblado(configuracion)
    argumentos["configuracion_adicional"] = {"regla_proveedor": True}
    resultado = ensamblar_factura_normalizada(**argumentos)

    assert resultado["configuracion_interna_aplicada"] == {
        "farmacia": "FARMACIA_INTERNA",
        "categoria": "MERCANCIA",
        "requiere_conciliacion_albaranes": True,
        "destinatario_id_farmacia": "0007",
        "destinatario_metodo_identificacion": "CIF",
        "regla_proveedor": True,
    }
    assert "archivo_origen" not in resultado["configuracion_interna_aplicada"]


def test_ensamblador_separa_contextos_variables_sin_cambiar_politica(
    configuracion,
) -> None:
    primero = argumentos_ensamblado(configuracion)
    segundo = argumentos_ensamblado(configuracion)
    segundo["archivo_origen"] = "factura_0002.pdf"
    segundo["fecha_ejecucion"] = datetime(2026, 8, 9, tzinfo=timezone.utc)

    resultado_primero = ensamblar_factura_normalizada(**primero)
    resultado_segundo = ensamblar_factura_normalizada(**segundo)

    assert (
        resultado_primero["archivo_origen"]
        != resultado_segundo["archivo_origen"]
    )
    assert resultado_primero["fecha_ejecucion"] != resultado_segundo["fecha_ejecucion"]
    assert resultado_primero["configuracion_interna_aplicada"] == resultado_segundo[
        "configuracion_interna_aplicada"
    ]
    assert resultado_primero["resultado_normalizado"] == resultado_segundo[
        "resultado_normalizado"
    ]
