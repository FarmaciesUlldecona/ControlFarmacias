from types import SimpleNamespace
import pytest
from src.facturas.motor_local.adaptadores.gold_pequenos import AdaptadorLogista
from src.facturas.motor_local.modelos import DocumentoLocal, PaginaLocal, PalabraLocal, RegionLocal, LineaLocal


@pytest.mark.parametrize("cantidad", [0, 1, 2, 3])
def test_albaranes_todas_paginas_independientes_del_nombre(cantidad):
    paginas = []
    for i in range(cantidad):
        palabras = [PalabraLocal(t, i+1, RegionLocal(j*50, 10, j*50+40, 20), j)
                    for j,t in enumerate(f"Albaran {9319977575+i} 29.07.2026 Total 448,00 EUR".split())]
        linea = LineaLocal(i+1, palabras, 1)
        paginas.append(PaginaLocal(i+1, 600, 800, linea.texto, palabras, [linea]))
    # Filename enganoso: ni proveedor ni numero entran como evidencia.
    documento = DocumentoLocal("OTRO_PROVEEDOR_9999999999_RITA.pdf", "a"*64, paginas)
    segmento = SimpleNamespace(paginas=(1, cantidad) if cantidad else ())
    filas = list(AdaptadorLogista._filas_albaranes(documento, segmento))
    assert len(filas) == cantidad
    assert [x[1].texto for x in filas] == [str(9319977575+i) for i in range(cantidad)]
    assert [x[0].pagina for x in filas] == list(range(1,cantidad+1))


def test_no_lee_albaranes_fuera_del_segmento():
    documento = DocumentoLocal("albaran_9319977575.pdf", "a"*64, [])
    assert list(AdaptadorLogista._filas_albaranes(documento, SimpleNamespace(paginas=[]))) == []


def test_multiples_albaranes_en_misma_pagina():
    lineas = []
    for orden, numero in enumerate((9319977575, 9319977576), 1):
        palabras = [PalabraLocal(t, 1, RegionLocal(j*50, orden*20, j*50+40, orden*20+10), j)
                    for j, t in enumerate(f"Albaran {numero} 29.07.2026 Total 448,00 EUR".split())]
        lineas.append(LineaLocal(1, palabras, orden))
    pagina = PaginaLocal(1, 600, 800, "\n".join(l.texto for l in lineas),
                          [w for l in lineas for w in l.palabras], lineas)
    doc = DocumentoLocal("nombre_irrelevante.pdf", "a"*64, [pagina])
    filas = list(AdaptadorLogista._filas_albaranes(doc, SimpleNamespace(paginas=(1, 1))))
    assert [fila[1].texto for fila in filas] == ["9319977575", "9319977576"]
