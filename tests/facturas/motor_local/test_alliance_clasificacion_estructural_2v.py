from pathlib import Path

from src.facturas.motor_local.adaptadores.alliance import (
    clasificar_fila_economica_alliance,
    promover_albaran_alliance,
)
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.runtime_supabase.multifactura import adaptar_resultado_local


ROOT = Path(__file__).resolve().parents[3]
PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf"


def campo(valor, pagina=2):
    return {"valor": valor, "evidencias": [{"pagina": pagina, "literal": str(valor)}]}


def candidato(tipo="NORMAL ACUSTICO", sentido="CARGO", numero="08P00001"):
    importe = -10.0 if sentido == "ABONO" else 10.0
    return {
        "orden": 1,
        "numero_referencia": campo(numero),
        "fecha": campo("2026-07-20"),
        "tipo_pedido": campo(tipo),
        "base": campo(9.0),
        "total": campo(importe),
        "sentido": campo(sentido),
        "rol_documentacion": {
            "valor": "ALBARAN",
            "regla": "COLUMNAS_NUMERO_ALBARAN_EXPLICITAS",
            "evidencias": [{"pagina": 2, "literal": "NUMERO ALBARAN"}],
        },
        "provenance": {"pagina": 2},
    }


def relacion(categoria):
    return {
        "orden": 1,
        "inequivoca": True,
        "movimiento": {"categoria": categoria},
        "evidencias": [{"pagina": 1, "literal": categoria}],
    }


def test_columna_albaran_sola_no_demuestra_mercancia():
    c = candidato(tipo="DESCONOCIDO")
    c["clasificacion_economica"] = clasificar_fila_economica_alliance(c)
    assert c["clasificacion_economica"]["concepto"] == "NO_DEMOSTRABLE"
    assert promover_albaran_alliance(c, factura_documental="F1", paginas_factura=[1, 2], segmentacion_inequivoca=True) is None


def test_cargo_tipo_mercancia_certificado_si_promueve():
    c = candidato()
    c["clasificacion_economica"] = clasificar_fila_economica_alliance(c)
    assert promover_albaran_alliance(c, factura_documental="F1", paginas_factura=[1, 2], segmentacion_inequivoca=True)


def test_abonos_agrupados_es_abono_y_no_mercancia():
    c = candidato(tipo="ABONOS AGRUPADOS", sentido="ABONO")
    assert clasificar_fila_economica_alliance(c)["concepto"] == "ABONO"


def test_relacion_con_abonos_clubs_clasifica_abono():
    c = candidato(tipo="CARGO/ABONO DIRECT", sentido="ABONO")
    result = clasificar_fila_economica_alliance(c, relacion("ABONO_COMERCIAL"))
    assert (result["concepto"], result["mismo_hecho_economico_resumen"]) == ("ABONO", True)


def test_relacion_con_rappel_clasifica_ajuste():
    c = candidato(tipo="CARGO/ABONO DIRECT", sentido="ABONO")
    assert clasificar_fila_economica_alliance(c, relacion("RAPPEL"))["concepto"] == "AJUSTE"


def test_relacion_con_servicio_clasifica_servicio():
    c = candidato(tipo="CARGO VENTA DIRECT", sentido="CARGO")
    assert clasificar_fila_economica_alliance(c, relacion("SERVICIO"))["concepto"] == "SERVICIO"


def test_prefijo_del_numero_no_clasifica():
    conceptos = {
        clasificar_fila_economica_alliance(candidato(tipo="DESCONOCIDO", numero=n))["concepto"]
        for n in ("08P00001", "08C00001", "08Z00001")
    }
    assert conceptos == {"NO_DEMOSTRABLE"}


def test_relacion_no_inequivoca_no_transfiere_concepto():
    c = candidato(tipo="CARGO VENTA DIRECT")
    r = relacion("SERVICIO")
    r["inequivoca"] = False
    assert clasificar_fila_economica_alliance(c, r)["concepto"] == "NO_DEMOSTRABLE"


def test_bloque_y_signo_incompatibles_fallan_cerrado():
    c = candidato(tipo="ABONOS AGRUPADOS", sentido="ABONO")
    c["total"] = campo(10.0)
    result = clasificar_fila_economica_alliance(c)
    assert (result["concepto"], result["regla"]) == (
        "NO_DEMOSTRABLE", "SENTIDO_Y_SIGNO_NO_COHERENTES_O_NO_DOCUMENTADOS"
    )


def test_casos_certificados_08009277_y_doble_conteo():
    local = MotorDocumentoLocal(BackendPdfium()).extraer(PDF)
    raw = next(f for f in local.facturas if f["segmento"]["identidad"] == "08009277")
    ops = {o["referencia"]["valor"]: o for o in raw["operaciones_economicas"]}
    assert len(raw["albaranes"]) == 160
    assert [(n, ops[n]["concepto"], ops[n]["importe"]["valor"]) for n in
            ("08P10588", "08C61794", "08P10623", "08Z34777")] == [
        ("08P10588", "ABONO", -823.46),
        ("08C61794", "ABONO", -122.27),
        ("08P10623", "AJUSTE", -2414.19),
        ("08Z34777", "SERVICIO", 191.54),
    ]
    assert {"08P10588", "08P10623", "08Z34777"} == {
        n for n, o in ops.items() if o["clasificacion_economica"]["mismo_hecho_economico_resumen"]
    }


def test_proyeccion_normalizada_cuenta_cada_hecho_una_vez():
    local = MotorDocumentoLocal(BackendPdfium()).extraer(PDF)
    normalized = adaptar_resultado_local(local)
    invoice = next(f for f in normalized["facturas"] if f["numero_factura"]["valor"] == "08009277")
    assert len(invoice["albaranes"]) == 160
    assert len(invoice["movimientos_comerciales"]) == 7
    assert [m["tipo"] for m in invoice["movimientos_comerciales"]].count("SERVICIO") == 2
