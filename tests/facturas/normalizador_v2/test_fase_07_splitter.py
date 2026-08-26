from __future__ import annotations

from decimal import Decimal

import pytest
from pypdf import PdfReader, PdfWriter

from src.facturas.normalizador_v2.modelos import (
    AlbaranDocumental, EstadoValidacion, Evidencia, FacturaNormalizada, NaturalezaPrincipal,
    ResultadoControl, ResultadoValidacion, Sentido, Tercero, Totales, ValorDocumentado,
)
from src.facturas.normalizador_v2.splitter import (
    ConfiguracionSplitter, ErrorSplitter, RangoSegmento, SenalesSegundaLectura,
    SplitterSelectivo, consolidar_lecturas, decidir_segunda_lectura, dividir_pdf,
)


def vd(valor, pagina=1):
    return ValorDocumentado(valor=valor, literal=str(valor), evidencia=[Evidencia(pagina=pagina, literal=str(valor))])


def fac(albaranes=()):
    return FacturaNormalizada(
        factura_id="f", naturaleza_principal=NaturalezaPrincipal.MERCANCIA, estado_validacion=EstadoValidacion.REQUIERE_SEGUNDA_LECTURA,
        requiere_conciliacion_albaranes=True, pagina_inicio=1, pagina_fin=4, proveedor=Tercero(nombre=vd("ALLIANCE"), alias_funcional="ALLIANCE HEALTHCARE"),
        numero_factura=vd("08009277"), totales=Totales(total=vd(Decimal("100"))), albaranes=list(albaranes),
        validaciones=[ResultadoValidacion(codigo="X", resultado=ResultadoControl.OK, descripcion="x", regla_version="v2")],
    )


def alb(numero, pagina=1):
    return AlbaranDocumental(orden=int(numero), numero=vd(f"A-{numero}", pagina), tipo_movimiento=Sentido.CARGO, importe_total=vd(Decimal("1"), pagina))


def test_alliance_densa_activa_por_senales_combinadas():
    d = decidir_segunda_lectura(SenalesSegundaLectura(naturaleza=NaturalezaPrincipal.MERCANCIA, multipagina=True, tabla_multipagina=True, continuidad_tabla=True, filas_extraidas=0, identificadores_visibles=162, densidad_alta=True, formato_alliance_denso_demostrado=True))
    assert d.activar and d.estado == EstadoValidacion.REQUIERE_SEGUNDA_LECTURA


def test_mercancia_o_proveedor_solos_no_activan_y_fedefarma_tampoco():
    assert not decidir_segunda_lectura(SenalesSegundaLectura(naturaleza=NaturalezaPrincipal.MERCANCIA)).activar
    f = decidir_segunda_lectura(SenalesSegundaLectura(naturaleza=NaturalezaPrincipal.MERCANCIA, multipagina=True, filas_extraidas=0, identificadores_visibles=5, perdida_prefijo_compuesto_fedefarma=True))
    assert not f.activar and "FEDEFARMA" in f.motivo


class Servicio:
    def __init__(self, segmentos=None, error=None): self.segmentos, self.error, self.kwargs = segmentos, error, None
    def procesar(self, pdf, **kwargs):
        self.kwargs = kwargs
        if self.error: raise self.error
        return self.segmentos


def pdf_paginas(tmp_path, cantidad=3):
    ruta = tmp_path / "entrada.pdf"; w = PdfWriter()
    for _ in range(cantidad): w.add_blank_page(width=100, height=100)
    with ruta.open("wb") as f: w.write(f)
    return ruta


def test_mapping_contiguo_y_division_fisica(tmp_path):
    ruta = pdf_paginas(tmp_path)
    servicio = Servicio([RangoSegmento("s1", 1, 2), RangoSegmento("s2", 3, 3)])
    rangos = SplitterSelectivo(servicio).segmentar(ruta)
    fisicos = dividir_pdf(ruta, rangos, tmp_path / "segmentos")
    assert servicio.kwargs["region"] == "eu" and servicio.kwargs["version"] == "pretrained-splitter-v1.5-2025-07-14"
    assert [len(PdfReader(s.ruta).pages) for s in fisicos] == [2, 1]
    assert fisicos[0].paginas_originales == (1, 2)


@pytest.mark.parametrize("segmentos", [[RangoSegmento("s1", 1, 1), RangoSegmento("s2", 3, 3)], [RangoSegmento("s1", 1, 3)]])
def test_fallos_y_limites(tmp_path, segmentos):
    ruta = pdf_paginas(tmp_path)
    config = ConfiguracionSplitter(max_paginas_por_segmento=2)
    with pytest.raises(ErrorSplitter): SplitterSelectivo(Servicio(segmentos), config).segmentar(ruta)


def test_fallo_servicio_no_reintenta(tmp_path):
    with pytest.raises(ErrorSplitter, match="sin reintento"):
        SplitterSelectivo(Servicio(error=RuntimeError("google"))).segmentar(pdf_paginas(tmp_path))


def test_consolidacion_recupera_y_deduplica_detalle():
    primaria = fac([alb(1)])
    segmentada = fac([alb(1), alb(2, 2), alb(3, 3)])
    salida = consolidar_lecturas([primaria], [segmentada])
    assert [a.numero.valor for a in salida[0].albaranes] == ["A-1", "A-2", "A-3"]
