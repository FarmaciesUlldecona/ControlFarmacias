from dataclasses import replace

import pytest

from src.facturas.identidad_documental import (
    EvidenciaContenido, IdentidadEconomica, comparar_identidad,
    contrastar_farmacia, identidad_binaria,
)
from src.facturas.runtime_supabase.manifiesto_pio import auditar_inventarios


def ev(valor):
    return EvidenciaContenido(valor, 1, valor)


def factura():
    return IdentidadEconomica(ev("F30004444"), ev("0563834757"), ev("FACTURA"),
                             ev("40901058C"), ev("2026-08-31"), ev("313.29"))


def test_mismo_nombre_con_distinto_emisor_numero_no_deduplica():
    documentos = [("HEFAME.pdf", factura()),
                  ("HEFAME.pdf", replace(factura(), proveedor=ev("B30462451"), numero=ev("1132029554")))]
    assert comparar_identidad(documentos[0][1], documentos[1][1]) == "FACTURAS_DIFERENTES"


def test_nombres_y_hashes_distintos_identidad_igual_solo_proponen_revision():
    assert identidad_binaria(b"pdf1") != identidad_binaria(b"pdf2")
    assert comparar_identidad(factura(), factura()) == "POSIBLE_MISMA_FACTURA_REQUIERE_REVISION"


def test_mismo_binario_en_rutas_distintas():
    archivos = {"a.pdf": b"pdf", "otra/b.pdf": b"pdf"}
    assert len({identidad_binaria(x) for x in archivos.values()}) == 1


def test_mismo_tamano_no_demuestra_mismo_binario_ni_identidad_economica():
    uno, dos = b"abcd", b"wxyz"
    assert len(uno) == len(dos)
    assert identidad_binaria(uno) != identidad_binaria(dos)
    assert comparar_identidad(
        factura(), replace(factura(), proveedor=ev("OTRO PROVEEDOR"))
    ) == "FACTURAS_DIFERENTES"


def test_identidad_incompleta_no_se_deduplica():
    assert comparar_identidad(IdentidadEconomica(), IdentidadEconomica()) == "IDENTIDAD_ECONOMICA_NO_DEMOSTRADA"


def test_total_corregido_requiere_revision():
    assert comparar_identidad(factura(), replace(factura(), total=ev("314"))) == "POSIBLE_VERSION_REQUIERE_REVISION"


@pytest.mark.parametrize("operativa,contenido,esperado", [
    ("PIO", "PIO", "CONSISTENTE"), ("RITA", "RITA", "CONSISTENTE"),
    ("PIO", "RITA", "FARMACIA_DOCUMENTO_CONTRADICTORIA"),
    ("RITA", "PIO", "FARMACIA_DOCUMENTO_CONTRADICTORIA"),
    ("PIO", None, "NO_DEMOSTRABLE"),
])
def test_farmacia(operativa, contenido, esperado):
    assert contrastar_farmacia(operativa, ev(contenido) if contenido else None) == esperado


@pytest.mark.parametrize("local_farmacia,remota", [("RITA", "PIO"), ("PIO", "RITA")])
def test_guard_cruce_farmacias_bloquea(local_farmacia, remota):
    local = [{"ruta_relativa": f"JUNY 26/A {local_farmacia}.pdf", "archivo_hash": "a"*64, "estado": "IMPORTADA"}]
    remoto = [{"id": "doc", "farmacia": remota, "archivo_hash": "a"*64}]
    result = auditar_inventarios(local, remoto)
    assert not result["ok"]
    assert result["conflictos_farmacia"] == ["doc"]


def test_contenido_rita_bloquea_incluso_si_nombre_y_hash_encaminan_pio():
    local = [{"ruta_relativa": "JUNY 26/A PIO.pdf", "archivo_hash": "a"*64, "estado": "IMPORTADA"}]
    remoto = [{"id": "doc", "farmacia": "PIO", "archivo_hash": "a"*64, "farmacia_documental": "RITA"}]
    assert not auditar_inventarios(local, remoto)["ok"]


def test_guard_no_oculta_historico_solo_supabase():
    remoto = [{"id": "doc", "farmacia": "PIO", "archivo_hash": "a"*64}]
    result = auditar_inventarios([], remoto)
    assert not result["ok"]
    assert result["solo_supabase_pio"] == ["a"*64]
