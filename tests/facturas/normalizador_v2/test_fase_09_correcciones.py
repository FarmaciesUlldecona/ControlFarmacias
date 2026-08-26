from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

from pypdf import PdfWriter

from src.facturas.normalizador_v2.adaptador_luna import MetadataLuna, ResultadoLuna
from src.facturas.normalizador_v2.modelos import (
    DiscrepanciaDocumental,
    EstadoValidacion,
    Evidencia,
    FacturaNormalizada,
    FechaDocumental,
    NaturalezaPrincipal,
    ResultadoControl,
    ResultadoValidacion,
    Tercero,
    TipoDiscrepancia,
    TipoReferencia,
    Totales,
    TramoImpuesto,
    ValorDocumentado,
    Vencimiento,
)
from src.facturas.normalizador_v2.normalizador_general import normalizar_candidato
from src.facturas.normalizador_v2.pipeline import _senales_por_defecto, normalizar_pdf
from src.facturas.normalizador_v2.reglas import aplicar_reglas_pequenas
from src.facturas.normalizador_v2.splitter import (
    RangoSegmento,
    SenalesSegundaLectura,
    consolidar_lecturas,
    decidir_segunda_lectura,
)
from src.facturas.normalizador_v2.validadores import validar_factura


def vd(valor, *, pagina=1, literal=None):
    literal = str(valor) if literal is None else literal
    return ValorDocumentado(valor=valor, literal=literal, evidencia=[Evidencia(pagina=pagina, literal=literal)])


def factura(**cambios):
    datos = {
        "factura_id": "fac-prueba",
        "naturaleza_principal": NaturalezaPrincipal.MERCANCIA,
        "estado_validacion": EstadoValidacion.VALIDADA,
        "requiere_conciliacion_albaranes": True,
        "pagina_inicio": 1,
        "pagina_fin": 2,
        "proveedor": Tercero(nombre=vd("PROVEEDOR")),
        "numero_factura": vd("F-1"),
        "totales": Totales(base_imponible=vd(Decimal("100")), iva=vd(Decimal("21")), total=vd(Decimal("121"))),
        "validaciones": [ResultadoValidacion(codigo="PRE", resultado=ResultadoControl.OK, descripcion="pre", regla_version="v2")],
    }
    datos.update(cambios)
    return FacturaNormalizada(**datos)


def candidato(*, proveedor="PROVEEDOR", pagina_fin=1, albaranes=None):
    valores = {
        "tipo_documento": "Factura",
        "numero_factura": "F-1",
        "fecha_factura": "14/08/2026",
        "base_imponible_total": 100,
        "iva_total": 21,
        "recargo_equivalencia_total": None,
        "otros_total": None,
        "importe_total": 121,
        "moneda": "EUR",
    }
    evidencias = [{"campo": campo, "pagina": 1, "literal": str(valor)} for campo, valor in valores.items() if valor is not None]
    evidencias.append({"campo": "proveedor.nombre", "pagina": 1, "literal": proveedor})
    return {
        **valores,
        "naturaleza_principal": "MERCANCIA",
        "requiere_conciliacion_albaranes": True,
        "pagina_inicio": 1,
        "pagina_fin": pagina_fin,
        "proveedor": {"nombre": proveedor, "nif": None, "direccion": None},
        "destinatario": None,
        "vencimientos": [],
        "impuestos": [],
        "albaranes": list(albaranes or []),
        "movimientos_comerciales": [],
        "forma_pago": None,
        "referencias_documentales": [],
        "discrepancias_documentales": [],
        "evidencias": evidencias,
    }


def test_tramos_completamente_vacios_se_descartan_y_parcial_documentado_se_conserva():
    entrada = candidato()
    entrada["impuestos"] = [
        {"orden": 1, "descripcion_literal": None, "base": 100, "tipo_iva": 21, "cuota_iva": 21, "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": None, "total_tramo": None},
        {"orden": 2, "descripcion_literal": "IVA documentado", "base": None, "tipo_iva": None, "cuota_iva": None, "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": None, "total_tramo": None},
    ]
    entrada["evidencias"].append({"campo": "impuestos[1].descripcion_literal", "pagina": 1, "literal": "IVA documentado"})

    salida = normalizar_candidato(entrada)

    assert len(salida.impuestos) == 1
    assert salida.impuestos[0].orden == 2
    assert salida.impuestos[0].descripcion_literal.valor == "IVA documentado"


def test_cuadre_total_es_idempotente_y_preserva_discrepancia_documental_distinta():
    documental = DiscrepanciaDocumental(
        tipo=TipoDiscrepancia.CUADRE_FISCAL,
        descripcion="Los componentes impresos no cuadran con el total impreso",
        importe_diferencia=Decimal("4"),
        material=True,
    )
    original = factura(
        totales=Totales(base_imponible=vd(Decimal("100")), iva=vd(Decimal("21")), total=vd(Decimal("125"))),
        discrepancias_documentales=[documental],
    )
    primera = validar_factura(original)
    tras_primera = original.model_copy(update={"discrepancias_documentales": list(primera.discrepancias)})
    segunda = validar_factura(tras_primera)

    assert primera.discrepancias == segunda.discrepancias
    assert documental in segunda.discrepancias
    assert len(segunda.discrepancias) == 2


def test_reglas_repetidas_mantienen_discrepancias_automaticas_estables():
    entrada = candidato()
    entrada["importe_total"] = 125
    entrada["evidencias"] = [
        e if e["campo"] != "importe_total" else {**e, "literal": "125,00"}
        for e in entrada["evidencias"]
    ]
    primera = aplicar_reglas_pequenas(normalizar_candidato(entrada))
    segunda = aplicar_reglas_pequenas(primera)
    assert primera.discrepancias_documentales == segunda.discrepancias_documentales


def test_consolidacion_fusiona_vencimientos_en_orden_y_sin_duplicados():
    v1 = Vencimiento(orden=1, fecha=vd(FechaDocumental(literal="20/08/2026", iso=date(2026, 8, 20))), importe=vd(Decimal("60")))
    v1_misma_identidad = Vencimiento(orden=9, fecha=vd(FechaDocumental(literal="20.08.2026", iso=date(2026, 8, 20))), importe=vd(Decimal("60")), medio_pago=vd("GIRO"))
    v2 = Vencimiento(orden=2, fecha=vd(FechaDocumental(literal="20/09/2026", iso=date(2026, 9, 20))), importe=vd(Decimal("61")))
    resultado = consolidar_lecturas([factura(vencimientos=[v1])], [factura(vencimientos=[v1_misma_identidad, v2])])[0]
    assert resultado.vencimientos == [v1, v2]


def test_consolidacion_fusiona_impuestos_en_orden_y_sin_duplicados():
    def tramo(orden, base):
        return TramoImpuesto(
            orden=orden,
            base=vd(Decimal(base)), tipo_iva=vd(Decimal("21")), cuota_iva=vd(Decimal(base) * Decimal("0.21")),
            tipo_recargo_equivalencia=vd(Decimal("5.2")), cuota_recargo_equivalencia=vd(Decimal(base) * Decimal("0.052")),
        )
    primero, repetido, segundo = tramo(1, "50"), tramo(8, "50"), tramo(2, "25")
    resultado = consolidar_lecturas([factura(impuestos=[primero])], [factura(impuestos=[repetido, segundo])])[0]
    assert resultado.impuestos == [primero, segundo]


def test_consolidacion_fusiona_discrepancias_en_orden_y_sin_duplicados():
    primera = DiscrepanciaDocumental(tipo=TipoDiscrepancia.OTRA, descripcion="primera", importe_diferencia=Decimal("1"), material=False)
    repetida = primera.model_copy(update={"material": True})
    segunda = DiscrepanciaDocumental(tipo=TipoDiscrepancia.OTRA, descripcion="segunda", importe_diferencia=Decimal("2"), material=False)
    resultado = consolidar_lecturas(
        [factura(discrepancias_documentales=[primera])],
        [factura(discrepancias_documentales=[repetida, segunda])],
    )[0]
    assert resultado.discrepancias_documentales[:2] == [primera, segunda]


def test_clave_incompleta_no_colapsa_elementos_distintos_por_none():
    a = Vencimiento(orden=1, fecha=vd(FechaDocumental(literal="20/08/2026", iso=date(2026, 8, 20))))
    b = Vencimiento(orden=2, fecha=vd(FechaDocumental(literal="20/08/2026", iso=date(2026, 8, 20))), medio_pago=vd("OTRO"))
    resultado = consolidar_lecturas([factura(vencimientos=[a])], [factura(vencimientos=[b])])[0]
    assert resultado.vencimientos == [a, b]


def test_clave_incompleta_si_elimina_duplicado_exacto():
    incompleto = Vencimiento(orden=1, fecha=vd(FechaDocumental(literal="20/08/2026", iso=date(2026, 8, 20))))
    resultado = consolidar_lecturas([factura(vencimientos=[incompleto])], [factura(vencimientos=[incompleto])])[0]
    assert resultado.vencimientos == [incompleto]


def _candidato_con_albaranes(cantidad, *, proveedor="PROVEEDOR", paginas=2):
    albaranes = [
        {"orden": i + 1, "fecha": None, "numero": f"ID-{i:03d}", "sentido": "CARGO", "tipo_pedido": None, "importe_base": None, "importe_total": None}
        for i in range(cantidad)
    ]
    salida = candidato(proveedor=proveedor, pagina_fin=paginas, albaranes=albaranes)
    for i, item in enumerate(albaranes):
        pagina = 1 + (i % paginas)
        salida["evidencias"].append({"campo": f"albaranes[{i}].numero", "pagina": pagina, "literal": item["numero"]})
    return salida


def test_identificadores_visibles_provienen_del_candidato_y_omision_activa():
    raw = _candidato_con_albaranes(3)
    completa = normalizar_candidato(raw)
    omitida = completa.model_copy(update={"albaranes": completa.albaranes[:1]})
    senales = _senales_por_defecto(omitida, raw)
    assert senales.identificadores_visibles == 3
    assert senales.filas_extraidas == 1
    assert decidir_segunda_lectura(senales).activar


def test_alliance_densa_activa_por_estructura_independiente():
    raw = _candidato_con_albaranes(100, proveedor="ALLIANCE", paginas=2)
    factura_alliance = normalizar_candidato(raw)
    senales = _senales_por_defecto(factura_alliance, raw)
    assert senales.identificadores_visibles == 100
    assert senales.tabla_multipagina and senales.continuidad_tabla and senales.densidad_alta
    assert decidir_segunda_lectura(senales).activar


def test_fedefarma_compuesto_por_si_solo_no_activa():
    raw = _candidato_con_albaranes(1, proveedor="FEDEFARMA", paginas=1)
    raw["albaranes"][0]["numero"] = "123456/07"
    raw["evidencias"][-1]["literal"] = "123456/07"
    senales = _senales_por_defecto(normalizar_candidato(raw), raw)
    assert senales.identificadores_visibles == senales.filas_extraidas == 1
    assert not decidir_segunda_lectura(senales).activar


class LectorLocal:
    def __init__(self, resultados):
        self.resultados = iter(resultados)
        self.llamadas = 0

    def extraer(self, _ruta):
        self.llamadas += 1
        return ResultadoLuna(
            tuple(next(self.resultados)),
            MetadataLuna(f"local-{self.llamadas}", "gpt-5.6-luna", "gpt-5.6-luna", 0, 0, 0, Decimal("0"), 0),
        )


class SplitterLocal:
    def segmentar(self, _ruta):
        return (RangoSegmento("s1", 1, 1), RangoSegmento("s2", 2, 2))


def _pdf(tmp_path, paginas=1):
    ruta = tmp_path / "sintetico.pdf"
    writer = PdfWriter()
    for _ in range(paginas):
        writer.add_blank_page(width=72, height=72)
    with ruta.open("wb") as stream:
        writer.write(stream)
    return ruta


def _ahora():
    return datetime(2026, 8, 14, tzinfo=timezone.utc)


def test_observabilidad_persiste_candidato_senales_etapas_y_roundtrip_sin_alterar_json(tmp_path):
    ruta = _pdf(tmp_path)
    raw = candidato()
    sin_traza = normalizar_pdf(ruta, lector_luna=LectorLocal([[raw]]), ahora=_ahora, reloj=iter([1.0, 1.1]).__next__)
    capturas = []
    con_traza = normalizar_pdf(
        ruta,
        lector_luna=LectorLocal([[raw]]),
        ahora=_ahora,
        reloj=iter([1.0, 1.1]).__next__,
        directorio_observabilidad=tmp_path / "observabilidad",
        sink_observabilidad=capturas.append,
    )
    persistidas = list((tmp_path / "observabilidad").glob("*.observabilidad.json"))
    assert len(persistidas) == 1
    datos = json.loads(persistidas[0].read_text(encoding="utf-8"))
    assert datos == capturas[0]
    assert datos["etapas"]["A_CANDIDATO_LUNA"][0]["facturas"][0]["numero_factura"] == "F-1"
    assert "identificadores_visibles" in datos["etapas"]["B_DECISION_SEGUNDA_LECTURA"][0]["senales"]
    assert all(datos["etapas"][etapa] is not None for etapa in datos["etapas"])
    assert json.loads(json.dumps(datos, ensure_ascii=False, sort_keys=True)) == datos
    assert sin_traza.json_estable() == con_traza.json_estable()
    assert not list((tmp_path / "observabilidad").glob("*.tmp"))


def test_observabilidad_etapa_e_contiene_consolidacion_segmentada(tmp_path):
    ruta = _pdf(tmp_path, paginas=2)
    primaria = candidato(pagina_fin=2)
    segmento = candidato()
    capturas = []

    def activar(_factura, _raw):
        return SenalesSegundaLectura(
            naturaleza=NaturalezaPrincipal.MERCANCIA,
            multipagina=True,
            tabla_multipagina=True,
            filas_extraidas=0,
            identificadores_visibles=1,
        )

    normalizar_pdf(
        ruta,
        lector_luna=LectorLocal([[primaria], [segmento], []]),
        splitter=SplitterLocal(),
        detector_senales=activar,
        directorio_segmentos=tmp_path / "segmentos",
        sink_observabilidad=capturas.append,
        ahora=_ahora,
        reloj=iter([1.0, 1.1]).__next__,
    )
    etapa = capturas[0]["etapas"]["E_CONSOLIDACION_SEGMENTADA"]
    assert etapa["aplicada"] is True
    assert len(etapa["facturas"]) == 1


def test_fallback_inequivoco_conserva_candidato_con_literal_real_y_mismatch_de_ruta():
    entrada = candidato(albaranes=[{
        "orden": 1, "fecha": None, "numero": "A-7788", "sentido": "CARGO",
        "tipo_pedido": None, "importe_base": None, "importe_total": None,
    }])
    entrada["evidencias"].append({"campo": "albaranes.1", "pagina": 1, "literal": "Albarán A-7788"})
    salida = normalizar_candidato(entrada)
    assert [item.numero.valor for item in salida.albaranes] == ["A-7788"]


def test_fallback_no_acepta_sin_evidencia_ni_evidencia_ambigua():
    sin_evidencia = candidato(albaranes=[{
        "orden": 1, "fecha": None, "numero": "A-1", "sentido": "CARGO",
        "tipo_pedido": None, "importe_base": None, "importe_total": None,
    }])
    assert normalizar_candidato(sin_evidencia).albaranes == []

    ambigua = candidato(albaranes=sin_evidencia["albaranes"])
    ambigua["evidencias"].extend([
        {"campo": "albaranes", "pagina": 1, "literal": "Fila A-1"},
        {"campo": "albaranes", "pagina": 1, "literal": "Resumen A-1"},
    ])
    assert normalizar_candidato(ambigua).albaranes == []


def test_una_evidencia_no_inventa_dos_items_indistinguibles():
    filas = [
        {"orden": orden, "fecha": None, "numero": "MISMO", "sentido": "CARGO", "tipo_pedido": None, "importe_base": None, "importe_total": None}
        for orden in (1, 2)
    ]
    entrada = candidato(albaranes=filas)
    entrada["evidencias"].append({"campo": "albaranes", "pagina": 1, "literal": "Albarán MISMO"})
    salida = normalizar_candidato(entrada)
    assert [item.numero.valor for item in salida.albaranes] == ["MISMO"]


def test_tabla_densa_sintetica_preserva_albaranes_y_movimientos_distintos():
    entrada = candidato(albaranes=[
        {"orden": 1, "fecha": None, "numero": "D-01", "sentido": "CARGO", "tipo_pedido": None, "importe_base": None, "importe_total": None},
        {"orden": 2, "fecha": None, "numero": "D-02", "sentido": "CARGO", "tipo_pedido": None, "importe_base": None, "importe_total": None},
    ])
    entrada["movimientos_comerciales"] = [
        {"orden": 1, "tipo": "DESCUENTO", "descripcion_literal": "RAPPEL", "sentido": "ABONO", "base": None, "iva": None, "recargo_equivalencia": None, "importe": None},
        {"orden": 2, "tipo": "SERVICIO", "descripcion_literal": "LOGISTICA", "sentido": "CARGO", "base": None, "iva": None, "recargo_equivalencia": None, "importe": None},
    ]
    entrada["evidencias"].extend([
        {"campo": "albaranes", "pagina": 1, "literal": "D-01; D-02"},
        {"campo": "movimientos_comerciales", "pagina": 1, "literal": "RAPPEL; LOGISTICA"},
    ])
    salida = normalizar_candidato(entrada)
    assert [a.numero.valor for a in salida.albaranes] == ["D-01", "D-02"]
    assert [m.descripcion_literal.valor for m in salida.movimientos_comerciales] == ["RAPPEL", "LOGISTICA"]


def test_referencias_documentales_con_fallback_no_se_convierten_en_albaranes():
    entrada = candidato()
    tipos = ["DELIVERY", "PEDIDO", "PO", "ORDER", "DOCUMENTO", "OTRA"]
    entrada["referencias_documentales"] = [
        {"orden": i + 1, "tipo": tipo, "identificador": f"REF-{i}", "descripcion_literal": None}
        for i, tipo in enumerate(tipos)
    ]
    entrada["evidencias"].extend([
        {"campo": f"referencias_documentales.{i + 1}", "pagina": 1, "literal": f"{tipo}: REF-{i}"}
        for i, tipo in enumerate(tipos)
    ])
    salida = normalizar_candidato(entrada)
    assert [r.tipo for r in salida.referencias_documentales] == [TipoReferencia(tipo) for tipo in tipos]
    assert [r.identificador.valor for r in salida.referencias_documentales] == [f"REF-{i}" for i in range(6)]
    assert salida.albaranes == []


def test_segmentada_enriquece_primaria_y_normaliza_razon_social_sin_duplicado():
    primaria = factura(proveedor=None)
    segmento = factura(
        factura_id="segmento",
        proveedor=Tercero(nombre=vd("TotalCare Europe, S.L.")),
        vencimientos=[Vencimiento(orden=1, importe=vd(Decimal("121")))],
    )
    salida = consolidar_lecturas([primaria], [segmento])
    assert len(salida) == 1
    assert salida[0].proveedor.nombre.valor == "TotalCare Europe, S.L."
    assert len(salida[0].vencimientos) == 1

    equivalente = factura(factura_id="otra", proveedor=Tercero(nombre=vd("TOTALCARE EUROPE SL")))
    assert len(consolidar_lecturas([segmento], [equivalente])) == 1


def test_consolidacion_no_colapsa_facturas_reales_ni_apoyo_ambiguo():
    numero_distinto = factura(factura_id="f2", numero_factura=vd("F-2"))
    proveedor_distinto = factura(factura_id="f3", proveedor=Tercero(nombre=vd("OTRO PROVEEDOR")))
    assert len(consolidar_lecturas([factura()], [numero_distinto])) == 2
    assert len(consolidar_lecturas([factura()], [proveedor_distinto])) == 2

    sin_proveedor_1 = factura(factura_id="p1", proveedor=None)
    sin_proveedor_2 = factura(factura_id="p2", proveedor=None)
    completa = factura(factura_id="segmentada")
    assert len(consolidar_lecturas([sin_proveedor_1, sin_proveedor_2], [completa])) == 3
