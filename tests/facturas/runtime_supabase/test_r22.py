"""R22 (DECISION DE PIO, 2026-11-24; caso E, 08005257): cargo sin albaran anulado por su abono en el mismo documento.

Unitarios de ``aplicar_r22`` y de su encaje con ``conciliar_importes`` y ``valores_por_linea`` (espejo de
``cf_detalles_por_linea``). Sin base de datos, sin produccion ni Farmatic. La aceptacion por la BD esta en
``test_integracion_pg17_r22.py``.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    MovimientoDocumentalTrabajo,
    aplicar_r22,
    conciliar_importes,
    construir_detalles_movimientos_documentales,
    valores_por_linea,
)
from src.facturas.runtime_supabase.modelos import DetalleConciliacion, TipoRelacionConciliacion

SIN = TipoRelacionConciliacion.SIN_COINCIDENCIA
MOV = TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC


def _doc(id_="L1", numero="08B45588", importe="505.08", sentido="CARGO", concepto="ECOCEUTICS"):
    return AlbaranDocumentalTrabajo(id=id_, numero=numero, fecha=date(2026, 4, 27),
                                    importe=None if importe is None else Decimal(importe), sentido=sentido,
                                    concepto_literal=concepto)


def _sin(doc):
    return DetalleConciliacion(tipo_relacion=SIN, importe_aplicado=Decimal("0"), factura_albaran_extraido_id=doc.id,
                               importe_documental=doc.importe if doc.sentido == "CARGO" else -doc.importe,
                               provenance={"fuente": "ALBARANES_SUPABASE", "estado_matching": "SIN_COINCIDENCIA"})


def _abono(id_="M1", importe="-505.08", base="-453.39", sentido="ABONO", literal="ECOCEUTICS"):
    [d] = construir_detalles_movimientos_documentales([MovimientoDocumentalTrabajo(
        id=id_, concepto_literal=literal, tipo="OTRO", sentido=sentido,
        importe=None if importe is None else Decimal(importe), base=Decimal(base))])
    return d


def _cand(numero, contador=900001):
    return CandidatoAlbaranSupabase(
        id_contador=contador, farmacia="PIO", id_proveedor="0002 ", proveedor="1.- SAFA", numero_albaran=numero,
        fecha=date(2026, 4, 27), importe_puc=Decimal("1.00"), importe_pvp=Decimal("1.00"), estado="PENDIENTE",
        id_recepcion=1)


def _casado(id_, importe):
    return DetalleConciliacion(tipo_relacion=TipoRelacionConciliacion.UNO_A_UNO, importe_aplicado=Decimal(importe),
                               albaran_farmacia="PIO", albaran_id_contador=1, factura_albaran_extraido_id=id_,
                               importe_documental=Decimal(importe))


def test_caso_08005257_la_linea_y_su_abono_quedan_explicados_con_neto_cero():
    doc, abono = _doc(), _abono()
    otras = [_casado("L2", "132.11")]
    antes = (abono, *otras, _sin(doc))
    assert conciliar_importes("132.11", antes).diferencia == Decimal("505.0800")
    despues = aplicar_r22(antes, [doc], [_cand("08B45587")])
    resultado = conciliar_importes("132.11", despues)
    assert (resultado.resultado, resultado.diferencia) == ("CONCILIADA", Decimal("0.0000"))
    linea = despues[2]
    assert linea.tipo_relacion == MOV and linea.importe_aplicado == Decimal("505.0800")
    assert linea.factura_albaran_extraido_id == "L1" and linea.factura_movimiento_id is None
    assert linea.albaran_id_contador is None
    assert linea.provenance["regla"] == "R22" and linea.provenance["factura_movimiento_id_par"] == "M1"
    assert linea.provenance["neto_par"] == "0.0000"
    assert (linea.provenance["concepto_literal"], linea.provenance["concepto_par"]) == ("ECOCEUTICS", "ECOCEUTICS")
    assert despues[0].provenance["regla"] == "R22"
    assert despues[0].provenance["factura_albaran_extraido_id_par"] == "L1"
    assert despues[0].importe_aplicado == Decimal("-505.0800")
    # R11: un par R22 no cuenta como albaran casado.
    assert resultado.albaranes_casados == 1
    # Espejo de cf_detalles_por_linea (30): movimiento -> NO_EVALUABLE, PDF = importe aplicado.
    valores = valores_por_linea(despues)
    assert (valores[2].importe_documental, valores[2].importe_farmatic, valores[2].diferencia,
            valores[2].estado) == (Decimal("505.0800"), None, None, "NO_EVALUABLE")


@pytest.mark.parametrize("candidato", ["08B45588", "08B45588A", " 08b45588 "])
def test_no_aplica_si_hay_albaran_de_ese_numero(candidato):
    doc, abono = _doc(), _abono()
    antes = (abono, _sin(doc))
    assert aplicar_r22(antes, [doc], [_cand(candidato)]) == antes


@pytest.mark.parametrize("cambio", ["importe_distinto", "linea_abono", "movimiento_cargo", "sin_numero",
                                    "sin_importe_movimiento", "linea_casada", "un_centimo"])
def test_no_aplica_fuera_de_la_regla(cambio):
    doc = _doc(sentido="ABONO") if cambio == "linea_abono" else _doc(numero=None) if cambio == "sin_numero" else _doc()
    abono = {"importe_distinto": lambda: _abono(importe="-505.00"),
             "movimiento_cargo": lambda: _abono(importe="505.08", base="453.39", sentido="CARGO"),
             "sin_importe_movimiento": lambda: _abono(importe=None),
             "un_centimo": lambda: _abono(importe="-505.09")}.get(cambio, _abono)()
    linea = _casado("L1", "505.08") if cambio == "linea_casada" else _sin(doc)
    antes = (abono, linea)
    assert aplicar_r22(antes, [doc], []) == antes


def test_falla_cerrado_con_dos_abonos_posibles():
    doc = _doc()
    antes = (_abono("M1"), _abono("M2"), _sin(doc))
    assert aplicar_r22(antes, [doc], []) == antes


def test_falla_cerrado_con_dos_lineas_posibles():
    d1, d2 = _doc("L1", "08B45588"), _doc("L2", "08B45589")
    antes = (_abono(), _sin(d1), _sin(d2))
    assert aplicar_r22(antes, [d1, d2], []) == antes


def test_dos_pares_independientes_se_emparejan_cada_uno_con_el_suyo():
    d1, d2 = _doc("L1", "08B45588", "505.08"), _doc("L2", "08B45589", "10.00")
    antes = (_abono("M1", "-505.08"), _abono("M2", "-10.00", "-9.00"), _sin(d1), _sin(d2))
    despues = aplicar_r22(antes, [d1, d2], [])
    assert [d.provenance.get("factura_movimiento_id_par") for d in despues[2:]] == ["M1", "M2"]
    assert conciliar_importes("0", despues).diferencia == Decimal("0.0000")


def test_sin_movimientos_no_cambia_nada():
    doc = _doc()
    antes = (_sin(doc),)
    assert aplicar_r22(antes, [doc], []) == antes


# D6 (Pio, 2026-11-24): el abono tiene que ser del MISMO concepto/laboratorio que la linea.
@pytest.mark.parametrize("concepto_linea,literal_abono", [
    ("ECOCEUTICS", "HEEL"), (None, "ECOCEUTICS"), ("", "ECOCEUTICS"), ("   ", "ECOCEUTICS"),
    ("ECOCEUTICS", ""), ("ECOCEUTICS", "ECOCEUTICS SL")])
def test_d6_no_aplica_sin_el_mismo_concepto(concepto_linea, literal_abono):
    doc = _doc(concepto=concepto_linea)
    antes = (_abono(literal=literal_abono), _sin(doc))
    assert aplicar_r22(antes, [doc], []) == antes


def test_d6_el_concepto_se_compara_sin_mayusculas_ni_espacios():
    doc = _doc(concepto="  Ecoceutics ")
    despues = aplicar_r22((_abono(literal="ECOCEUTICS"), _sin(doc)), [doc], [])
    assert despues[1].provenance["regla"] == "R22"


def test_d6_dos_abonos_del_mismo_importe_solo_casa_el_del_mismo_concepto():
    doc = _doc()
    antes = (_abono("M1", literal="HEEL"), _abono("M2", literal="ECOCEUTICS"), _sin(doc))
    despues = aplicar_r22(antes, [doc], [])
    assert despues[2].provenance["factura_movimiento_id_par"] == "M2"
    assert despues[0] == antes[0] and despues[1].provenance["regla"] == "R22"
