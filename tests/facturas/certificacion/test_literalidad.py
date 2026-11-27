"""FACTURAS-0, Paso 0a: verificador de literalidad independiente del lector (DISENO §2)."""
from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.certificacion import literalidad as lit

MODULO = Path(lit.__file__)


LINEAS = ["FACTURA DUPLICADO", "08015660 10-12-2025 06-04-2026",
          "02-12-2025 ECOCEUTICS 08E33517 40,45 45,07", "30-06-2026 ABONOS AGRUPADOS 08C38230 8,29- 8,66-",
          "TOTAL BASE IMPONIBLE 1.198,99 TOTAL FACTURA 1.221,68",
          "Sus datos son tratados por ALLIANCE HEALTHCARE ESPAÑA, S.A., para gestionar"]
PAGINA = "\n".join(LINEAS)


def _y(i):
    """Línea base (desde arriba) de la línea i de la página sintética."""
    return 100.0 + 20.0 * i


def _tiradas():
    return [(18.0, _y(i), "   " + linea, False) for i, linea in enumerate(LINEAS)]


def _texto(paginas=1):
    return lit.TextoPdf([PAGINA] * paginas, [_tiradas() for _ in range(paginas)])


TEXTO = _texto()


def _ev(literal, pagina=1, regla="VALOR_TRAS_ETIQUETA", origen="LITERAL_LOCAL_DETERMINISTA", linea=None, fila=None,
        bbox_fila="auto"):
    """Evidencia con la fila que vería el lector: la primera línea que contiene el literal (o la indicada)."""
    if linea is None:
        clave = lit.normalizar_estricto(literal)
        linea = next((i for i, l in enumerate(LINEAS) if clave in lit.normalizar_estricto(l)), 0)
    if bbox_fila == "auto":
        bbox_fila = [18.0, _y(linea) - 5.0, 560.0, _y(linea)]
    return {"literal": literal, "pagina": pagina,
            "ubicacion": {"regla": regla, "pagina": pagina, "origen_autoridad": origen, "tipo_evidencia": "LITERAL_LOCAL",
                          "bbox_fila": bbox_fila, "bbox": bbox_fila,
                          "fila_literal": LINEAS[linea] if fila is None else fila}}


def _campo(valor, literal, **kw):
    return {"valor": valor, "literal": literal, "evidencia": [_ev(literal, **kw)]}


def _factura(**campos):
    base = {"pagina_inicio": 1, "pagina_fin": 1, "numero_factura": _campo("08015660", "08015660")}
    base.update(campos)
    return base


def _clases(factura, texto=TEXTO):
    return [(r.ruta, r.clase, r.motivo) for r in lit.verificar_factura(factura, texto).resultados]


# --- analizadores -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("literal, esperado", [
    ("40,45", Decimal("40.45")), ("1.234,56", Decimal("1234.56")), ("8,29-", Decimal("-8.29")),
    ("-1,48", Decimal("-1.48")), ("10", Decimal("10")), ("1,40", Decimal("1.40")), ("0,00", Decimal("0")),
])
def test_importe_desde_literal(literal, esperado):
    assert lit.importe_desde_literal(literal) == esperado


@pytest.mark.parametrize("literal", ["08E33517", "40.45", "1,2,3", "", "ABC", "12.34,5.6"])
def test_importe_desde_literal_rechaza_lo_que_no_es_importe_es_es(literal):
    assert lit.importe_desde_literal(literal) is None


@pytest.mark.parametrize("literal, iso", [
    ("10-12-2025", "2025-12-10"), ("06/04/26", "2026-04-06"), ("5.10.2026", "2026-10-05"),
])
def test_fecha_desde_literal(literal, iso):
    assert lit.fecha_desde_literal(literal) == iso


@pytest.mark.parametrize("literal", ["32-01-2026", "10-13-2026", "2026-01-10", "10 12 2025"])
def test_fecha_desde_literal_rechaza_fechas_invalidas(literal):
    assert lit.fecha_desde_literal(literal) is None


# --- LITERAL ----------------------------------------------------------------------------------------------------

def test_importes_fechas_textos_e_identificadores_literales():
    f = _factura(
        totales={"total": _campo("1221.68", "1.221,68"), "base_imponible": _campo("1198.99", "1.198,99")},
        fecha_factura=_campo({"iso": "2025-12-10", "literal": "10-12-2025"}, "10-12-2025"),
        tipo_documento=_campo("FACTURA_DUPLICADO", "FACTURA DUPLICADO"),
        proveedor={"nombre": _campo("ALLIANCE HEALTHCARE ESPANA, S.A.", "ALLIANCE HEALTHCARE ESPAÑA, S.A.,")},
        albaranes=[{"numero": _campo("08E33517", "08E33517"), "importe_total": _campo("45.07", "45,07")}],
        movimientos_comerciales=[{"importe": _campo("-8.66", "8,66-")}],
    )
    informe = lit.verificar_factura(f, TEXTO)
    assert {r.clase for r in informe.resultados} == {lit.LITERAL}
    assert informe.estado == "LITERALIDAD_OK"
    assert informe.recuento()[lit.LITERAL] == len(informe.resultados) == 9


# --- NO_LITERAL: lo que un lector podría inventar ----------------------------------------------------------------

def test_valor_inventado_con_literal_real_falla():
    f = _factura(albaranes=[{"importe_total": _campo("45.08", "45,07")}])
    assert ("/albaranes[0]/importe_total", lit.NO_LITERAL, "IMPORTE_DISTINTO") in _clases(f)


def test_signo_cambiado_falla():
    f = _factura(movimientos_comerciales=[{"importe": _campo("8.66", "8,66-")}])
    assert lit.verificar_factura(f, TEXTO).estado == "LITERALIDAD_FALLO"


def test_literal_que_no_esta_en_la_pagina_falla():
    f = _factura(totales={"total": _campo("999.99", "999,99")})
    assert ("/totales/total", lit.NO_LITERAL, "LITERAL_AUSENTE_EN_LA_PAGINA") in _clases(f)


def test_texto_constante_del_lector_que_no_esta_en_el_pdf_falla():
    f = _factura(proveedor={"direccion": _campo("CALLE INVENTADA 1", "CALLE INVENTADA 1")})
    assert ("/proveedor/direccion", lit.NO_LITERAL, "LITERAL_AUSENTE_EN_LA_PAGINA") in _clases(f)


def test_fecha_distinta_del_literal_falla():
    f = _factura(fecha_factura=_campo({"iso": "2025-12-11", "literal": "10-12-2025"}, "10-12-2025"))
    assert ("/fecha_factura", lit.NO_LITERAL, "FECHA_DISTINTA") in _clases(f)


def test_pagina_fuera_de_la_factura_falla():
    texto = _texto(2)
    f = _factura(totales={"total": _campo("1221.68", "1.221,68", pagina=2)})
    assert ("/totales/total", lit.NO_LITERAL, "PAGINA_FUERA_DE_LA_FACTURA") in _clases(f, texto)


def test_sin_evidencia_o_literal_vacio_falla():
    f = _factura(totales={"total": {"valor": "1221.68", "literal": "", "evidencia": []}})
    assert ("/totales/total", lit.NO_LITERAL, "SIN_EVIDENCIA_O_LITERAL") in _clases(f)


def test_literal_de_evidencia_distinto_del_campo_falla():
    campo = {"valor": "45.07", "literal": "45,07", "evidencia": [_ev("40,45")]}
    assert ("/albaranes[0]/importe_total", lit.NO_LITERAL, "LITERAL_DE_EVIDENCIA_DISTINTO") in _clases(
        _factura(albaranes=[{"importe_total": campo}]))


def test_decision_pio_no_reconocida_falla():
    campo = _campo("CARGO", "ECOCEUTICS", regla="REGLA_INVENTADA", origen=lit.ORIGEN_DECISION_PIO)
    assert ("/albaranes[0]/sentido", lit.NO_LITERAL, "DECISION_PIO_NO_RECONOCIDA") in _clases(
        _factura(albaranes=[{"sentido": campo}]))


# --- NO_EVALUABLE -----------------------------------------------------------------------------------------------

def test_pagina_sin_texto_es_no_evaluable_y_no_certifica():
    informe = lit.verificar_factura(_factura(), lit.TextoPdf([None]))
    assert [r.clase for r in informe.resultados] == [lit.NO_EVALUABLE]
    assert informe.estado == lit.NO_EVALUABLE


def test_factura_sin_valores_documentados_no_certifica():
    assert lit.verificar_factura({"pagina_inicio": 1, "pagina_fin": 1}, TEXTO).estado == lit.NO_EVALUABLE


# --- DERIVADO (R14) ---------------------------------------------------------------------------------------------

def _con_r14(importe, literal="1.221,68", vencimientos_extra=0):
    venc = {"fecha": _campo({"iso": "2026-04-06", "literal": "06-04-2026"}, "06-04-2026"),
            "importe": _campo(importe, literal, regla="R14_TOTAL_MISMA_HOJA_VENCIMIENTO_UNICO")}
    otros = [{"fecha": _campo({"iso": "2026-04-06", "literal": "06-04-2026"}, "06-04-2026")}] * vencimientos_extra
    return _factura(totales={"total": _campo("1221.68", "1.221,68")}, vencimientos=[venc, *otros])


def test_r14_es_derivado_no_literal():
    resultados = {r.ruta: r for r in lit.verificar_factura(_con_r14("1221.68"), TEXTO).resultados}
    r = resultados["/vencimientos[0]/importe"]
    assert (r.clase, r.motivo, r.regla) == (lit.DERIVADO, "R14_IGUAL_AL_TOTAL", "R14_TOTAL_MISMA_HOJA_VENCIMIENTO_UNICO")


def test_r14_distinto_del_total_falla():
    assert ("/vencimientos[0]/importe", lit.NO_LITERAL, "R14_DISTINTO_DEL_TOTAL") in _clases(_con_r14("1198.99", "1.198,99"))


def test_r14_con_varios_vencimientos_falla():
    assert ("/vencimientos[0]/importe", lit.NO_LITERAL, "R14_SIN_VENCIMIENTO_UNICO") in _clases(_con_r14("1221.68", vencimientos_extra=1))


def test_r14_con_literal_que_no_esta_en_la_pagina_falla():
    assert ("/vencimientos[0]/importe", lit.NO_LITERAL, "LITERAL_AUSENTE_EN_LA_PAGINA") in _clases(_con_r14("77.00", "77,00"))


# --- recorrido e independencia ----------------------------------------------------------------------------------

def test_no_entra_en_extraccion_local_ni_cuenta_valores_sin_evidencia():
    f = _factura(extraccion_local={"x": _campo("1", "NO_ESTA")}, sentido="CARGO", naturaleza_principal="MERCANCIA")
    assert [ruta for ruta, _ in lit.valores_documentados(f)] == ["/numero_factura"]


def test_verificar_documento_devuelve_un_informe_por_factura():
    doc = {"facturas": [_factura(), _factura(numero_factura=_campo("08015661", "08015661"))]}
    informes = lit.verificar_documento(doc, TEXTO)
    assert [i.factura for i in informes] == ["08015660", "08015661"]
    assert [i.estado for i in informes] == ["LITERALIDAD_OK", "LITERALIDAD_FALLO"]


def test_el_verificador_no_importa_los_lectores_ni_la_persistencia():
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    modulos = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom) and n.module}
    modulos |= {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    assert modulos <= {"__future__", "re", "unicodedata", "dataclasses", "decimal", "pathlib", "typing", "io", "pypdf"}


def test_version_0_2_1():
    assert lit.VERSION == "0.2.1"


def test_lista_cerrada_de_reglas():
    assert set(lit.REGLAS_DERIVADAS) == {"R14_TOTAL_MISMA_HOJA_VENCIMIENTO_UNICO"}
    assert lit.REGLAS_DECISION_PIO == frozenset()


# --- PDF real mínimo leído con pypdf ----------------------------------------------------------------------------

def _pdf_minimo(lineas: list[str]) -> bytes:
    """PDF de una página con texto Helvetica (sin dependencias) para probar la extracción con pypdf."""
    contenido = "BT /F1 10 Tf 50 750 Td " + " 0 -14 Td ".join(
        "(" + l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj" for l in lineas) + " ET"
    objetos = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(contenido)} >>\nstream\n{contenido}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    salida, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(salida))
        salida += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    salida += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return salida


def _en_pdf(valor, literal, fila, y_base):
    caja = [50.0, y_base - 5.0, 300.0, y_base]
    return _campo(valor, literal, bbox_fila=caja, fila=fila)


def _factura_pdf(total="1221.68", literal="1.221,68", y_total=106.0):
    return {"pagina_inicio": 1, "pagina_fin": 1,
            "numero_factura": _en_pdf("08015660", "08015660", "FACTURA 08015660", 92.0),
            "totales": {"total": _en_pdf(total, literal, "TOTAL FACTURA 1.221,68", y_total)}}


def test_texto_pdf_con_pypdf_sobre_un_pdf_real():
    texto = lit.TextoPdf.desde_pdf(_pdf_minimo(["FACTURA 08015660", "TOTAL FACTURA 1.221,68"]))
    assert texto.numero_paginas == 1 and texto.tiene_texto(1) and not texto.tiene_texto(2)
    assert lit.verificar_factura(_factura_pdf(), texto).estado == "LITERALIDAD_OK"
    assert lit.verificar_factura(_factura_pdf("1221.69", "1.221,69"), texto).estado == "LITERALIDAD_FALLO"


def test_pdf_real_total_en_otra_fila_falla():
    texto = lit.TextoPdf.desde_pdf(_pdf_minimo(["FACTURA 08015660", "TOTAL FACTURA 1.221,68"]))
    motivos = {r.ruta: r.motivo for r in lit.verificar_factura(_factura_pdf(y_total=92.0), texto).resultados}
    assert motivos["/totales/total"] == "LITERAL_AUSENTE_EN_SU_FILA"


def test_pdf_girado_no_ancla_filas():
    pdf = _pdf_minimo(["FACTURA 08015660", "TOTAL FACTURA 1.221,68"]).replace(
        b"/MediaBox [0 0 595 842]", b"/MediaBox [0 0 595 842] /Rotate 90")
    informe = lit.verificar_factura(_factura_pdf(), lit.TextoPdf.desde_pdf(pdf))
    assert {(r.clase, r.motivo) for r in informe.resultados} == {(lit.NO_EVALUABLE, "FILA_NO_EVALUABLE")}
    assert informe.estado == lit.NO_EVALUABLE


# --- 0.2.0: anclaje a la fila o bloque --------------------------------------------------------------------------

def test_literal_de_otra_fila_de_la_misma_pagina_falla():
    """40,45 está en la página, pero no en la fila del total: el anclaje por página lo dejaba pasar."""
    f = _factura(totales={"total": _campo("40.45", "40,45", linea=4)})
    assert ("/totales/total", lit.NO_LITERAL, "LITERAL_AUSENTE_EN_SU_FILA") in _clases(f)


def test_fila_del_lector_que_no_esta_en_su_posicion_falla():
    campo = _campo("45.07", "45,07", fila="02-12-2025 OTRO_LABORATORIO 08E33517 40,45 45,07")
    assert ("/albaranes[0]/importe_total", lit.NO_LITERAL, "FILA_DEL_LECTOR_AUSENTE_EN_SU_POSICION") in _clases(
        _factura(albaranes=[{"importe_total": campo}]))


def test_evidencia_sin_caja_falla_cerrado():
    campo = _campo("45.07", "45,07", bbox_fila=None)
    assert ("/albaranes[0]/importe_total", lit.NO_LITERAL, "EVIDENCIA_SIN_FILA") in _clases(
        _factura(albaranes=[{"importe_total": campo}]))


def test_sin_posiciones_de_pypdf_la_fila_no_es_evaluable():
    informe = lit.verificar_factura(_factura(), lit.TextoPdf([PAGINA]))
    assert [(r.clase, r.motivo) for r in informe.resultados] == [(lit.NO_EVALUABLE, "FILA_NO_EVALUABLE")]


def test_bloque_de_dos_lineas_con_etiqueta_intercalada():
    """Dirección en dos líneas con la etiqueta a la derecha (como el bloque del destinatario de Alliance)."""
    tiradas = [(323.0, 116.0, "DIRECCION", False), (18.0, 114.0, "     CALLE MAYOR 1", False),
               (18.0, 126.0, "     08001 BARCELONA", False), (18.0, 140.0, "OTRA FILA", False)]
    texto = lit.TextoPdf(["DIRECCION\nCALLE MAYOR 1\n08001 BARCELONA\nOTRA FILA"], [tiradas])
    campo = _campo("CALLE MAYOR 1 08001 BARCELONA", "CALLE MAYOR 1 08001 BARCELONA",
                   bbox_fila=[323.0, 108.6, 447.0, 116.0], fila="DIRECCION CALLE MAYOR 1")
    campo["evidencia"][0]["ubicacion"]["bbox"] = [384.0, 109.7, 448.0, 126.1]
    informe = lit.verificar_factura({"pagina_inicio": 1, "pagina_fin": 1, "destinatario": {"direccion": campo}}, texto)
    assert informe.estado == "LITERALIDAD_OK"


def test_texto_vertical_se_ancla_por_su_franja_y_no_contamina_las_filas():
    vertical = (20.0, 692.0, "Domicilio Social: Pol. Ind. 4 Insc. 1o CIF: A50004324", True)
    fila = (18.0, 421.0, "25-07-2026 NORMAL ACUSTICO 08C54396 6,38 7,11", False)
    texto = lit.TextoPdf([vertical[2] + "\n" + fila[2]], [[vertical, fila]])
    nif = _campo("A50004324", "A50004324", bbox_fila=[17.1, 387.0, 20.0, 407.3], fila="A50004324")
    albaran = _campo("08C54396", "08C54396", bbox_fila=[17.1, 416.5, 289.8, 422.0],
                     fila="1o 25-07-2026 NORMAL ACUSTICO 08C54396 6,38 7,11")
    otra = _campo("08C54396", "08C54396", bbox_fila=[200.0, 387.0, 300.0, 407.3], fila="08C54396")
    f = {"pagina_inicio": 1, "pagina_fin": 1, "proveedor": {"nif": nif}, "albaranes": [{"numero": albaran}, {"numero": otra}]}
    clases = {r.ruta: r.clase for r in lit.verificar_factura(f, texto).resultados}
    assert clases == {"/proveedor/nif": lit.LITERAL, "/albaranes[0]/numero": lit.LITERAL,
                      "/albaranes[1]/numero": lit.NO_LITERAL}


@pytest.mark.parametrize("literal, tiradas, esperado", [
    ("ABCDEFGH", ["XXABCDEFGHYY"], True),
    ("ABCDEFGH", ["ABCD", "EFGH"], True),
    ("ABCDEFGH", ["ABCDE", "FGH"], True),  # tirada entera corta (p. ej. la etiqueta «IVA»)
    ("ABCDEFGH", ["ABCDE", "XFGH"], False),  # trozo corto que no es una tirada entera
    ("TOTALA10TOTALB20", ["TOTALA", "TOTALB", "10XX20"], False),
    ("TOTALA10,0TOTALB20,0", ["TOTALA", "TOTALB", "10,0XX20,0"], True),
    ("TOTALA20,0TOTALB10,0", ["TOTALA", "TOTALB", "10,0XX20,0"], False),
    ("", ["ALGO"], False),
    # 0.2.1: búsqueda con vuelta atrás (la voraz tomaba «0,000» de «0,0000»)
    ("10,000,00000,00", ["1", "0,00", "0,0000", "0,00"], True),
    # 0.2.1: trozo corto pegado al borde de una tirada («…ABONO A» | «COMPENSAR.»)
    ("ACOMPENSAR.IMPORTE", ["VIADEPAGO:ABONOA", "COMPENSAR.", "IMPORTE"], True),
    ("XCOMPENSAR.", ["VIADEPAGO:ABONOA", "COMPENSAR."], False),
])
def test_composicion_por_trozos_ordenados(literal, tiradas, esperado):
    assert lit.compuesto_en_tiradas(literal, tiradas) is esperado
