from pathlib import Path

import pytest

from src.facturas import importar_facturas_drive
from src.facturas.importar_facturas_drive import es_factura_rita


@pytest.mark.parametrize(
    ("nombre", "se_excluye"),
    [
        ("ALLIANCE VTO 10.9.26 PIO.pdf", False),
        ("BOIRON VTO 20.8.26 RITA.pdf", True),
        ("SISFARMA VTO 18.9.26 RITA.PDF", True),
        ("PROVEEDOR RITA VTO 20.8.26 PIO.pdf", False),
    ],
)
def test_regla_exclusion_facturas_rita(
    nombre: str,
    se_excluye: bool,
) -> None:
    assert es_factura_rita(Path(nombre)) is se_excluye


def test_regla_exclusion_rita_ignora_espacios_finales() -> None:
    assert es_factura_rita(Path("PROVEEDOR RITA   .pdf")) is True


def test_obtener_facturas_pdf_excluye_rita_del_flujo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nombres_incluidos = {
        "ALLIANCE VTO 10.9.26 PIO.pdf",
        "PROVEEDOR RITA VTO 20.8.26 PIO.pdf",
    }
    nombres_excluidos = {
        "BOIRON VTO 20.8.26 RITA.pdf",
        "SISFARMA VTO 18.9.26 RITA.PDF",
    }

    for nombre in nombres_incluidos | nombres_excluidos:
        (tmp_path / nombre).touch()

    monkeypatch.setattr(
        importar_facturas_drive,
        "obtener_carpetas_mensuales_validas",
        lambda: [tmp_path],
    )

    encontrados = {
        ruta.name
        for ruta in importar_facturas_drive.obtener_facturas_pdf()
    }

    assert encontrados == nombres_incluidos
