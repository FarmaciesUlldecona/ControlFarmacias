from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from pypdf import PdfWriter

from src.facturas.normalizador_v2.adaptador_luna import MetadataLuna, ResultadoLuna
from src.facturas.normalizador_v2.modelos import EstadoValidacion, EstrategiaLectura, NaturalezaPrincipal
from src.facturas.normalizador_v2.pipeline import normalizar_pdf
from src.facturas.normalizador_v2.splitter import RangoSegmento, SenalesSegundaLectura


def pdf(tmp_path, paginas=1):
    ruta = tmp_path / "factura_nombre_no_evidencia.pdf"; w = PdfWriter()
    for _ in range(paginas): w.add_blank_page(width=100, height=100)
    with ruta.open("wb") as f: w.write(f)
    return ruta


def candidato(numero="F1", pagina_inicio=1, pagina_fin=1):
    valores = {"tipo_documento": "Factura", "numero_factura": numero, "fecha_factura": "14/08/2026", "base_imponible_total": 100, "iva_total": 21, "recargo_equivalencia_total": 0, "importe_total": 121, "moneda": "EUR"}
    evidencias = [{"campo": k, "pagina": pagina_inicio, "literal": str(v)} for k, v in valores.items()]
    evidencias.append({"campo": "proveedor.nombre", "pagina": pagina_inicio, "literal": "Eports"})
    return {**valores, "naturaleza_principal": "MERCANCIA", "requiere_conciliacion_albaranes": True, "pagina_inicio": pagina_inicio, "pagina_fin": pagina_fin, "proveedor": {"nombre": "Eports", "nif": None, "direccion": None}, "otros_total": None, "vencimientos": [], "impuestos": [], "albaranes": [], "movimientos_comerciales": [], "destinatario": None, "forma_pago": None, "referencias_documentales": [], "discrepancias_documentales": [], "evidencias": evidencias}


class Lector:
    def __init__(self, resultados): self.resultados = iter(resultados); self.llamadas = 0
    def extraer(self, ruta):
        self.llamadas += 1
        facturas = next(self.resultados)
        return ResultadoLuna(tuple(facturas), MetadataLuna(f"r{self.llamadas}", "gpt-5.6-luna", "gpt-5.6-luna", 1, 0, 1, Decimal("0.0000014"), 10))


class Splitter:
    def segmentar(self, ruta): return (RangoSegmento("s1", 1, 1), RangoSegmento("s2", 2, 2))


def fijo(): return datetime(2026, 8, 14, tzinfo=timezone.utc)


def test_punto_productivo_local_sin_supabase_farmatic(tmp_path):
    doc = normalizar_pdf(pdf(tmp_path), lector_luna=Lector([[candidato()]]), ahora=fijo, reloj=iter([1.0, 1.1]).__next__)
    assert doc.estado_documento == EstadoValidacion.VALIDADA
    assert doc.facturas[0].numero_factura.valor == "F1"
    assert doc.metadata_tecnica.lector_primario == "gpt-5.6-luna"
    json.loads(doc.json_estable())


def test_cero_facturas_legible_requiere_revision(tmp_path):
    doc = normalizar_pdf(pdf(tmp_path), lector_luna=Lector([[]]), ahora=fijo, reloj=iter([1.0, 1.1]).__next__)
    assert doc.facturas == [] and doc.estado_documento == EstadoValidacion.REQUIERE_REVISION


def test_fallo_lector_es_error_tecnico_sin_reintento(tmp_path):
    class Fallo:
        def extraer(self, ruta): raise RuntimeError("api")
    doc = normalizar_pdf(pdf(tmp_path), lector_luna=Fallo(), ahora=fijo, reloj=iter([1.0, 1.1, 1.2]).__next__)
    assert doc.estado_documento == EstadoValidacion.ERROR_TECNICO and doc.facturas == []


def test_segunda_lectura_integrada_y_mapping_original(tmp_path):
    ruta = pdf(tmp_path, 2)
    lector = Lector([[candidato(pagina_fin=2)], [candidato()], []])
    def activar(f, raw):
        return SenalesSegundaLectura(naturaleza=NaturalezaPrincipal.MERCANCIA, multipagina=True, tabla_multipagina=True, filas_extraidas=0, identificadores_visibles=2)
    doc = normalizar_pdf(ruta, lector_luna=lector, splitter=Splitter(), detector_senales=activar, directorio_segmentos=tmp_path / "seg", ahora=fijo, reloj=iter([1.0, 1.1]).__next__)
    assert doc.estrategia_lectura == EstrategiaLectura.LUNA_V2_MAS_SPLITTER_SEGMENTADO
    assert lector.llamadas == 3 and len(doc.metadata_tecnica.segmentos) == 2


def test_segunda_lectura_necesaria_sin_splitter_conserva_estado(tmp_path):
    def activar(f, raw): return SenalesSegundaLectura(naturaleza=NaturalezaPrincipal.MERCANCIA, multipagina=True, tabla_multipagina=True, filas_extraidas=0, identificadores_visibles=2)
    doc = normalizar_pdf(pdf(tmp_path, 2), lector_luna=Lector([[candidato(pagina_fin=2)]]), detector_senales=activar, ahora=fijo, reloj=iter([1.0, 1.1]).__next__)
    assert doc.estado_documento == EstadoValidacion.REQUIERE_SEGUNDA_LECTURA


def test_determinismo_funcional_e_ids(tmp_path):
    ruta = pdf(tmp_path)
    a = normalizar_pdf(ruta, lector_luna=Lector([[candidato()]]), ahora=fijo, reloj=iter([1.0, 1.1]).__next__)
    b = normalizar_pdf(ruta, lector_luna=Lector([[candidato()]]), ahora=fijo, reloj=iter([1.0, 1.1]).__next__)
    assert a.json_estable() == b.json_estable()
