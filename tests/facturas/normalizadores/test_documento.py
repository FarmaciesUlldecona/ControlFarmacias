from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from src.facturas.normalizadores.comun import RegistroIncidencias
from src.facturas.normalizadores.configuracion import ConfiguracionProveedor
from src.facturas.normalizadores.documento import (
    construir_cabecera_documental,
    construir_destinatario,
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
