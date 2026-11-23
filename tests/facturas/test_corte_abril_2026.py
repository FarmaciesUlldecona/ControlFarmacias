"""Carga Alliance abril-mayo (decision (b) de Pio, 2026-11-22; concretada el 2026-11-23): el corte de la importacion
de PDF baja a 2026-04-01 y la subcarpeta ABRIL 26\\1A DESENA queda fuera (factura de 21-31/03, sin albaranes
Farmatic). Sin Drive real ni Supabase: arbol de carpetas en tmp_path.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.facturas import importar_facturas_drive as ifd

INCLUIDOS = {
    "ABRIL 26/2A DESENA/ALLIANCE A.pdf",
    "ABRIL 26/3A DESENA/OTRO B.pdf",
    "MAIG 26/1A DESENA/ALLIANCE C.pdf",
    "MAIG 26/3A DESENA/D.PDF",
    "JUNY 26/1A DESENA/E.pdf",
    "ABRIL 27/1A DESENA/F.pdf",  # otro ano: la exclusion es solo de abril de 2026
}
EXCLUIDOS = {
    "ABRIL 26/1A DESENA/ALLIANCE 21-31.pdf",
    "ABRIL 26/1A DESENA/sub/G.pdf",
    "MARÇ 26/3A DESENA/H.pdf",
    "2025/I.pdf",
    "ABRIL 26/2A DESENA/J RITA.pdf",
    "MAIG 26/1A DESENA/K.txt",
}


@pytest.fixture
def drive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raiz = tmp_path / "FACTURES PIO"
    for relativa in INCLUIDOS | EXCLUIDOS:
        ruta = raiz / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.touch()
    monkeypatch.setattr(ifd, "RUTA_FACTURAS", raiz)
    return raiz


def test_el_corte_es_el_1_de_abril_de_2026():
    assert ifd.FECHA_INICIO_IMPORTACION == date(2026, 4, 1)
    assert ifd.SUBCARPETAS_EXCLUIDAS == frozenset({(date(2026, 4, 1), "1A DESENA")})


def test_carpetas_mensuales_desde_abril(drive: Path):
    nombres = [c.name for c in ifd.obtener_carpetas_mensuales_validas()]
    assert nombres == ["ABRIL 26", "MAIG 26", "JUNY 26", "ABRIL 27"]


def test_pdf_desde_abril_sin_abril_26_1a_desena(drive: Path):
    encontrados = {r.relative_to(drive).as_posix() for r in ifd.obtener_facturas_pdf()}
    assert encontrados == INCLUIDOS


@pytest.mark.parametrize("partes, excluida", [
    (("ABRIL 26", "1A DESENA", "x.pdf"), True),
    (("abril 2026", "1a  desena", "x.pdf"), True),
    (("ABRIL-26", "1A_DESENA", "sub", "x.pdf"), True),
    (("ABRIL 26", "2A DESENA", "x.pdf"), False),
    (("ABRIL 27", "1A DESENA", "x.pdf"), False),
    (("MAIG 26", "1A DESENA", "x.pdf"), False),
    (("ABRIL 26", "x.pdf"), False),  # PDF suelto en la carpeta del mes: no esta en la subcarpeta excluida
    (("CARPETA RARA", "1A DESENA", "x.pdf"), False),
])
def test_subcarpeta_excluida(partes, excluida):
    assert ifd.subcarpeta_excluida(partes) is excluida
