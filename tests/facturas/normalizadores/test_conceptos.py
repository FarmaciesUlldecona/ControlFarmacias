from __future__ import annotations

from dataclasses import asdict
import inspect
from pathlib import Path

import pytest

from src.facturas.normalizadores.conceptos import (
    CategoriaConcepto,
    clasificar_concepto_factura,
)


RAIZ = Path(__file__).resolve().parents[3]


def campo(valor, evidencia: str | None = None, pagina: int = 1) -> dict:
    return {
        "valor": valor,
        "evidencias": (
            [{"texto_visible": evidencia, "pagina": pagina}]
            if evidencia is not None
            else []
        ),
    }


def fila(
    tipo,
    importe,
    evidencia: str | None,
    *,
    descripcion: str | None = None,
    incluido_en_base=True,
    incluido_en_total=True,
) -> dict:
    return {
        "tipo_ajuste": campo(tipo, evidencia),
        "descripcion": campo(descripcion, evidencia),
        "importe": campo(importe, evidencia),
        "incluido_en_base": campo(incluido_en_base, str(incluido_en_base)),
        "incluido_en_total": campo(incluido_en_total, str(incluido_en_total)),
    }


@pytest.mark.parametrize(
    ("tipo", "importe", "evidencia"),
    (
        ("DESCUENTO", "-12,50", "Descuento aplicado -12,50 EUR"),
        ("BONIFICACIÓN", "-5,00", "Bonificación comercial -5,00 EUR"),
        ("DESCUENTO", "-70,31", "Dtº: -70,31"),
    ),
)
def test_ajuste_explicito_cuantificado_se_acepta(
    tipo,
    importe,
    evidencia,
) -> None:
    resultado = clasificar_concepto_factura(fila(tipo, importe, evidencia))
    assert resultado.categoria is CategoriaConcepto.AJUSTE


def test_tipo_descuento_sin_evidencia_suficiente_es_incierto() -> None:
    resultado = clasificar_concepto_factura(fila("DESCUENTO", "-5,00", None))
    assert resultado.categoria is CategoriaConcepto.INCIERTO


@pytest.mark.parametrize(
    ("tipo", "importe", "evidencia"),
    (
        ("OTRO", "5,00", "Cargo visible 5,00 EUR"),
        ("OTRO", "-5,00", "Regularización visible -5,00 EUR"),
        ("IMPUESTO", "5,00", "Tributo visible 5,00 EUR"),
        (None, "-5,00", "Importe genérico -5,00 EUR"),
        ("DESCUENTO", "-5,00", "Porcentaje informativo 10 %"),
    ),
)
def test_senales_aisladas_no_demuestran_ajuste(
    tipo,
    importe,
    evidencia,
) -> None:
    resultado = clasificar_concepto_factura(fila(tipo, importe, evidencia))
    assert resultado.categoria is CategoriaConcepto.INCIERTO


def test_flags_true_true_no_autorizan_concepto_generico() -> None:
    resultado = clasificar_concepto_factura(
        fila("OTRO", "3,00", "Concepto 3,00 EUR")
    )
    assert resultado.categoria is CategoriaConcepto.INCIERTO


def test_importe_negativo_por_si_solo_no_autoriza() -> None:
    resultado = clasificar_concepto_factura(
        fila(None, "-8,00", "-8,00 EUR", descripcion=None)
    )
    assert resultado.categoria is CategoriaConcepto.INCIERTO


def test_falso_positivo_pendiente_de_revision_se_bloquea() -> None:
    resultado = clasificar_concepto_factura(
        fila(
            "DESCUENTO",
            "-5,00",
            "Descuento pendiente de revisión -5,00 EUR",
        )
    )
    assert resultado.categoria is CategoriaConcepto.INCIERTO


@pytest.mark.parametrize("entrada", (None, {}, [], "fila"))
def test_entrada_ausente_o_vacia_es_incierta(entrada) -> None:
    resultado = clasificar_concepto_factura(entrada)
    assert resultado.categoria is CategoriaConcepto.INCIERTO
    assert resultado.evidencias == ()


def test_clasificacion_es_determinista() -> None:
    entrada = fila("DESCUENTO", "-2,50", "Dto. aplicado -2,50 EUR")
    assert clasificar_concepto_factura(entrada) == clasificar_concepto_factura(
        entrada
    )


def test_evidencia_y_procedencia_de_campo_se_conservan_para_auditoria() -> None:
    resultado = clasificar_concepto_factura(
        fila("DESCUENTO", "-2,50", "Descuento aplicado -2,50 EUR")
    )
    evidencias = [asdict(evidencia) for evidencia in resultado.evidencias]
    assert {
        "campo": "importe",
        "texto_visible": "Descuento aplicado -2,50 EUR",
        "pagina": 1,
    } in evidencias


def test_clasificador_no_contiene_proveedores_ni_valores_de_casos() -> None:
    fuente = inspect.getsource(
        __import__(
            "src.facturas.normalizadores.conceptos", fromlist=["dummy"]
        )
    ).casefold()
    prohibidos = (
        "endesa",
        "guimer",
        "pierre",
        "suavinex",
        "fedefarma",
        "alliance",
        "hygie",
        "56.94",
        "320.32",
        "78.18",
        "patron_oficial",
    )
    assert all(prohibido not in fuente for prohibido in prohibidos)


def test_clasificador_esta_aislado() -> None:
    ruta = RAIZ / "src/facturas/normalizadores/conceptos.py"
    texto = ruta.read_text(encoding="utf-8").casefold().replace("\\", "/")
    prohibidos = (
        "facturas/patron",
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
    assert all(prohibido not in texto for prohibido in prohibidos)
