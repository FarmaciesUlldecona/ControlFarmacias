from datetime import date
from decimal import Decimal
from pathlib import Path

from src.facturas.hefame_economia import (
    derivar_magnitud_comparable_hefame,
    detectar_comision_hefame,
    evaluar_conciliabilidad_operativa_hefame,
)
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal, hash_funcional
from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    buscar_candidato_albaran,
)


ROOT = Path(__file__).resolve().parents[3]
PDF = ROOT / "tmp/pdfs/hito_2i3/hefame_antiguo.pdf"
PROVEEDOR = "HDAD.FMCTCA.MEDIT.,S.C.L."
EXISTENTES = {
    "4127691753": (date(2026, 8, 27), "19.65", "23.95"),
    "4127726806": (date(2026, 8, 31), "3.84", "4.35"),
    "4127762016": (date(2026, 8, 31), "2.14", "2.90"),
    "4127762027": (date(2026, 8, 31), "4.80", "6.62"),
}
AUSENTES = {
    "4127627531", "4127654105", "4127674455", "4127689557", "4127750839",
}


def extraer():
    return MotorDocumentoLocal(BackendPdfium()).extraer(PDF)


def candidatos():
    return [
        CandidatoAlbaranSupabase(
            i, "PIO", "3", "3.- HEFAME", numero, fecha,
            Decimal(puc), Decimal(pvp), "PENDIENTE",
        )
        for i, (numero, (fecha, puc, pvp)) in enumerate(EXISTENTES.items(), 1)
    ]


def documental(albaran):
    a = albaran.atributos_documentales
    return AlbaranDocumentalTrabajo(
        str(albaran.orden), albaran.numero_albaran, date.fromisoformat(albaran.fecha),
        Decimal(str(albaran.total)), albaran.sentido,
        magnitud_documental=a["magnitud_documental"],
        categoria_fiscal=a["categoria_fiscal"],
        iva_pct=Decimal(str(a["iva_pct"])), re_pct=Decimal(str(a["re_pct"])),
        importe_iva_derivado=Decimal(str(a["importe_iva_derivado"])),
        importe_re_derivado=Decimal(str(a["importe_re_derivado"])),
        importe_comparable_operativo=Decimal(str(a["importe_comparable_operativo"])),
        provenance=a["provenance"],
    )


def resultados():
    return {
        a.numero_albaran: buscar_candidato_albaran(
            documental(a), candidatos(), proveedor_literal=PROVEEDOR,
        )
        for a in extraer().albaranes
    }


def test_01_base_neta_se_conserva():
    a = extraer().albaranes[0]
    assert a.total == a.atributos_documentales["base_neta"] == 13.74


def test_02_base_neta_no_es_la_magnitud_comparada_con_puc():
    a = next(x for x in extraer().albaranes if x.numero_albaran == "4127726806")
    assert a.total == 3.45 and a.atributos_documentales["importe_comparable_operativo"] == 3.84


def test_03_base_sr_usa_iva_4_y_re_05():
    x = derivar_magnitud_comparable_hefame("4.59", "BASE_S_R")
    assert (x["iva_pct"], x["re_pct"]) == (Decimal("4.0"), Decimal("0.5"))


def test_04_base_re_usa_iva_10_y_re_14():
    x = derivar_magnitud_comparable_hefame("3.45", "BASE_RE")
    assert (x["iva_pct"], x["re_pct"]) == (Decimal("10.0"), Decimal("1.4"))


def test_05_base_no_usa_iva_21_y_re_12():
    x = derivar_magnitud_comparable_hefame("12.22", "BASE_NO")
    assert (x["iva_pct"], x["re_pct"]) == (Decimal("21.0"), Decimal("1.2"))


def test_06_magnitud_comparable_es_campo_separado():
    x = derivar_magnitud_comparable_hefame("3.45", "BASE_RE")
    assert x["base_neta"] == Decimal("3.4500") and x["importe_comparable_operativo"] == Decimal("3.84")


def test_07_4127726806_es_exacto_economico():
    assert resultados()["4127726806"].estado == "EXACTO_ECONOMICO"


def test_08_4127762027_es_exacto_economico():
    assert resultados()["4127762027"].estado == "EXACTO_ECONOMICO"


def test_09_4127691753_es_incompatible():
    assert resultados()["4127691753"].estado == "NUMERO_EXACTO_ECONOMIA_INCOMPATIBLE"


def test_10_4127762016_es_incompatible():
    assert resultados()["4127762016"].estado == "NUMERO_EXACTO_ECONOMIA_INCOMPATIBLE"


def test_11_cinco_numeros_son_ausentes():
    r = resultados()
    assert {n for n, x in r.items() if x.estado == "NUMERO_AUSENTE"} == AUSENTES


def test_12_otro_numero_con_mismo_importe_no_hace_match():
    d = AlbaranDocumentalTrabajo(
        "x", "NO-EXISTE", date(2026, 8, 28), Decimal("3.45"),
        importe_comparable_operativo=Decimal("3.84"),
    )
    assert buscar_candidato_albaran(d, candidatos(), proveedor_literal=PROVEEDOR).estado == "NUMERO_AUSENTE"


def test_13_comision_hefame_es_cargo():
    c = next(x for x in extraer().movimientos if x["concepto_normalizado"] == "COMISION_HEFAME")
    assert c["categoria"] == c["sentido"] == "CARGO"


def test_14_comision_no_requiere_albaran():
    c = next(x for x in extraer().movimientos if x["concepto_normalizado"] == "COMISION_HEFAME")
    assert c["no_albaran"] and not c["requiere_match_operativo"]


def test_15_comision_no_genera_albaran_no_localizado():
    assert not any(i["codigo"] == "ALBARAN_NO_LOCALIZADO" for i in extraer().incidencias)


def test_16_comision_se_computa_una_sola_vez():
    r = extraer()
    assert sum(x["concepto_normalizado"] == "COMISION_HEFAME" for x in r.movimientos) == 1
    assert next(c for c in r.controles_conciliacion if c["id"] == "PEDIDOS_DESDE_DETALLE")["diferencia"] == 0.0


def test_17_comision_usa_base_sr():
    c = next(x for x in extraer().movimientos if x["concepto_normalizado"] == "COMISION_HEFAME")
    assert c["categoria_fiscal"] == "BASE_S_R"


def test_18_comision_80_deriva_iva_re_y_total():
    c = next(x for x in extraer().movimientos if x["concepto_normalizado"] == "COMISION_HEFAME")
    assert (c["importe"]["valor"], c["importe_iva_derivado"], c["importe_re_derivado"], c["importe_fiscal_total"]) == (80.0, 3.2, 0.4, 83.6)


def test_19_importe_comision_no_esta_hardcodeado():
    c = detectar_comision_hefame(
        {"BASE_S_R": 124.27, "BASE_RE": 18.15, "BASE_NO": 32.15},
        {"BASE_S_R": 34.27, "BASE_RE": 18.15, "BASE_NO": 32.15},
    )
    assert c is not None and c["base_neta"] == Decimal("90.0000")


def test_20_no_se_infiere_periodicidad_mensual():
    c = next(x for x in extraer().movimientos if x["concepto_normalizado"] == "COMISION_HEFAME")
    assert c["periodicidad"] == "NO_DEMOSTRADA"


def test_21_abo_devo_no_se_duplica():
    r = extraer()
    assert sum(x["concepto_normalizado"] == "ABONO_DEVOLUCION" for x in r.movimientos) == 1
    assert next(x for x in r.movimientos if x["concepto_normalizado"] == "ABONO_DEVOLUCION")["sentido"] == "ABONO"


def test_22_aproafa_no_se_duplica():
    r = extraer()
    assert sum(x["concepto_normalizado"] == "APROAFA" for x in r.movimientos) == 1
    assert next(x for x in r.movimientos if x["concepto_normalizado"] == "APROAFA")["sentido"] == "CARGO"


def test_23_servicios_110_son_independientes():
    s = next(x for x in extraer().movimientos if x["concepto_normalizado"] == "SERVICIOS_OPERATIVOS")
    assert s["importe"]["valor"] == 110.0 and s["categoria"] == "SERVICIO"


def test_24_total_documental_reconstruido_es_313_29():
    r = extraer()
    assert r.documento_completo_demostrado
    assert all(c["estado"] == "OK" for c in r.controles_conciliacion)
    assert r.cabecera["importe_total"]["valor"] == 313.29


def test_25_reprocesado_es_determinista():
    motor = MotorDocumentoLocal(BackendPdfium())
    assert hash_funcional(motor.extraer(PDF)) == hash_funcional(motor.extraer(PDF))


def test_26_filename_no_interviene_en_economia():
    documento = BackendPdfium().cargar_pdf(PDF)
    documento.ruta = "nombre_ajeno.pdf"
    from src.facturas.motor_local.adaptadores.hefame import AdaptadorHefame
    assert AdaptadorHefame().reconocer(documento).estado == "RECONOCIDO"


def test_conciliacion_operativa_parcial_no_autoriza_automaticamente():
    estados = [x.estado for x in resultados().values()]
    decision = evaluar_conciliabilidad_operativa_hefame(estados)
    assert decision == {
        "matches_validos": 2,
        "total_referencias": 9,
        "conciliacion_operativa": "PARCIAL",
        "decision": "PENDIENTE_CONCILIAR",
    }
