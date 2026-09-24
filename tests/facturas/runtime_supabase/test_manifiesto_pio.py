from __future__ import annotations

import hashlib

import pytest

from src.facturas.runtime_supabase.manifiesto_pio import (
    clasificar_ruta_indice,
    manifiesto_sqlite_pio,
    manifiesto_supabase_pio,
    reconciliado,
)


def _hash(numero: int) -> str:
    return f"{numero:064x}"


_POR_DEFECTO = object()


def _fila(numero: int, nombre: str | None = None, archivo_hash: object = _POR_DEFECTO):
    return {
        "ruta_relativa": "JUNY 26\\1A DESENA\\" + (nombre or f"F{numero} PIO.pdf"),
        "archivo_hash": _hash(numero) if archivo_hash is _POR_DEFECTO else archivo_hash,
        "estado": "IMPORTADA",
    }


def test_116_hashes_pio_unicos_iguales_cumplen():
    filas = [_fila(i) for i in range(116)]
    local = manifiesto_sqlite_pio(filas)
    remoto = manifiesto_supabase_pio(_hash(i) for i in range(116))
    assert local.total == remoto.total == 116
    assert reconciliado(local, remoto)


def test_tres_rutas_adicionales_de_hashes_existentes_cumplen():
    filas = [_fila(i) for i in range(116)]
    filas += [_fila(i, f"COPIA {i} PIO.pdf") for i in range(3)]
    local = manifiesto_sqlite_pio(filas)
    assert local.total == 116
    assert reconciliado(local, manifiesto_supabase_pio(_hash(i) for i in range(116)))


def test_siete_rita_historicos_no_entran_y_cumplen():
    filas = [_fila(i) for i in range(116)]
    filas += [_fila(200 + i, f"R{i} RITA.pdf") for i in range(7)]
    assert reconciliado(
        manifiesto_sqlite_pio(filas),
        manifiesto_supabase_pio(_hash(i) for i in range(116)),
    )


def test_hash_pio_solo_sqlite_bloquea():
    assert not reconciliado(
        manifiesto_sqlite_pio([_fila(1), _fila(2)]),
        manifiesto_supabase_pio([_hash(1)]),
    )


def test_hash_pio_solo_supabase_bloquea():
    assert not reconciliado(
        manifiesto_sqlite_pio([_fila(1)]),
        manifiesto_supabase_pio([_hash(1), _hash(2)]),
    )


def test_mismo_conteo_con_hash_distinto_bloquea():
    assert not reconciliado(
        manifiesto_sqlite_pio([_fila(1)]),
        manifiesto_supabase_pio([_hash(2)]),
    )


@pytest.mark.parametrize("invalido", [None, "", "z" * 64, "0" * 63])
def test_hash_pio_nulo_o_invalido_bloquea(invalido):
    with pytest.raises(ValueError, match="HASH_PIO_INVALIDO"):
        manifiesto_sqlite_pio([_fila(1, archivo_hash=invalido)])


def test_duplicados_de_ruta_no_alteran_manifiesto():
    uno = manifiesto_sqlite_pio([_fila(1)])
    dos = manifiesto_sqlite_pio([_fila(1), _fila(1, "OTRA RUTA PIO.pdf")])
    assert uno == dos


def test_rita_nunca_entra_en_manifiesto_pio():
    rita = _fila(500, "PROVEEDOR RITA   .pdf")
    assert clasificar_ruta_indice(rita["ruta_relativa"]) == "RITA"
    resultado = manifiesto_sqlite_pio([rita])
    assert resultado.total == 0
    assert resultado.sha256 == hashlib.sha256(b"").hexdigest()


def test_fuera_de_periodo_o_no_pdf_queda_excluido():
    assert clasificar_ruta_indice("MAIG 26\\1A DESENA\\A PIO.pdf") == "EXCLUIDO"
    assert clasificar_ruta_indice("JUNY 26\\1A DESENA\\A PIO.txt") == "EXCLUIDO"
