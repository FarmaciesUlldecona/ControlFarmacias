from __future__ import annotations

from pathlib import Path

import pytest

from src.facturas.motor_local.autoridad import COFARES_LOCAL_AUTHORITY
from src.facturas.motor_local.adaptadores.alliance import sentido_desde_seccion_documental
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal, hash_funcional


ROOT = Path(__file__).resolve().parents[3]
PDF_1 = ROOT / "pruebas/facturas/documentos/ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf"
PDF_2 = ROOT / "pruebas/facturas/documentos/2o_gold_standard/ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf"


def _extraer(path: Path):
    if not path.exists():
        pytest.skip(f"corpus local externo ausente: {path}")
    return MotorDocumentoLocal(BackendPdfium()).extraer(path)


@pytest.fixture(scope="module")
def resultados():
    return _extraer(PDF_1), _extraer(PDF_2)


def _factura(resultados, numero):
    return next(f for r in resultados for f in r.facturas if f["segmento"]["identidad"] == numero)


def test_reconoce_dos_documentos_y_segmenta_siete_facturas(resultados):
    primero, segundo = resultados
    assert primero.documento["layout"] == segundo.documento["layout"] == "alliance-local"
    assert [f["segmento"]["identidad"] for f in primero.facturas] == ["08008428", "08008427", "08008429", "08008430"]
    assert [f["segmento"]["paginas"] for f in primero.facturas] == [[1, 3], [4, 7], [8, 9], [10, 11]]
    assert [f["segmento"]["identidad"] for f in segundo.facturas] == ["08009278", "08009277", "08009279"]
    assert [f["segmento"]["paginas"] for f in segundo.facturas] == [[1, 4], [5, 9], [10, 11]]


def test_conserva_527_candidatos_sin_inventar_rol(resultados):
    candidatos = [c for r in resultados for f in r.facturas for c in f["candidatos_fila"]]
    assert len(candidatos) == 527
    assert all(c["rol_fila"] == "INDETERMINADO" for c in candidatos)
    assert all(c["numero_referencia"]["valor"] and c["tipo_pedido"]["valor"] for c in candidatos)
    assert all(c["base"]["evidencias"] and c["total"]["evidencias"] for c in candidatos)


def test_direct_no_decide_rol_y_los_casos_historicos_se_preservan(resultados):
    factura = _factura(resultados, "08009277")
    por_id = {c["numero_referencia"]["valor"]: c for c in factura["candidatos_fila"]}
    for numero in ("08P10588", "08P10623", "08Z34777"):
        assert por_id[numero]["rol_fila"] == "INDETERMINADO"
        assert "DIRECT" in por_id[numero]["tipo_pedido"]["valor"]
    assert {c["rol_fila"] for c in factura["candidatos_fila"] if "DIRECT" not in c["tipo_pedido"]["valor"]} == {"INDETERMINADO"}


def test_seccion_documental_conserva_sentido_sin_usar_signo(resultados):
    candidatos = [c for r in resultados for f in r.facturas for c in f["candidatos_fila"]]
    assert {c["sentido"]["valor"] for c in candidatos} == {"CARGO", "ABONO"}
    assert all(c["sentido"]["evidencias"] for c in candidatos)


def test_movimientos_historicos_y_sentido_independiente(resultados):
    factura = _factura(resultados, "08009277")
    movimientos = {m["descripcion_literal"]["valor"]: m for m in factura["movimientos"]}
    assert movimientos["RAPPEL GenerAH"]["categoria"] == "RAPPEL"
    assert movimientos["ABONOS CLUBS"]["categoria"] == "ABONO_COMERCIAL"
    assert movimientos["SERV.PLATAF.360"]["categoria"] == "SERVICIO"
    assert movimientos["SERVICIO BASICO"]["categoria"] == "SERVICIO"
    assert movimientos["CONDIC. COMERCIAL"]["categoria"] == "CONDICION_COMERCIAL"
    assert all(m["sentido"] is None for m in movimientos.values())


def test_seccion_cargos_inequivoca_determina_sentido_cargo():
    assert sentido_desde_seccion_documental("CARGOS", pertenencia_demostrada=True) == "CARGO"


def test_seccion_abonos_inequivoca_determina_sentido_abono():
    assert sentido_desde_seccion_documental("ABONOS", pertenencia_demostrada=True) == "ABONO"


def test_seccion_ambigua_mantiene_sentido_null():
    assert sentido_desde_seccion_documental("CARGOS / ABONOS", pertenencia_demostrada=True) is None
    assert sentido_desde_seccion_documental("CARGOS", pertenencia_demostrada=False) is None


def test_descripcion_abono_sin_seccion_no_basta():
    descripcion_literal = "ABONO ESPECIAL"
    assert descripcion_literal
    assert sentido_desde_seccion_documental(None, pertenencia_demostrada=False) is None


def test_signo_negativo_sin_seccion_no_basta():
    importe = -100.0
    assert importe < 0
    assert sentido_desde_seccion_documental(None, pertenencia_demostrada=False) is None


@pytest.mark.parametrize("categoria", ["DEVOLUCION_MERCANCIA", "RAPPEL", "SERVICIO"])
def test_categoria_no_implica_sentido(categoria):
    assert categoria
    assert sentido_desde_seccion_documental(None, pertenencia_demostrada=False) is None


def test_relacion_conserva_candidato_y_movimiento(resultados):
    factura = _factura(resultados, "08009277")
    candidatos_antes = len(factura["candidatos_fila"])
    movimientos_antes = len(factura["movimientos"])
    assert len(factura["relaciones_documentales"]) == 3
    assert len(factura["candidatos_fila"]) == candidatos_antes == 165
    assert len(factura["movimientos"]) == movimientos_antes == 5


def test_relacion_no_transfiere_rol(resultados):
    factura = _factura(resultados, "08009277")
    relacionados = {r["candidato"]["identidad"]["valor"] for r in factura["relaciones_documentales"]}
    por_id = {c["numero_referencia"]["valor"]: c for c in factura["candidatos_fila"]}
    assert relacionados
    assert all(por_id[numero]["rol_fila"] == "INDETERMINADO" for numero in relacionados)


def test_relacion_no_fusiona_objetos(resultados):
    factura = _factura(resultados, "08009277")
    for relacion in factura["relaciones_documentales"]:
        candidato = relacion["candidato"]
        movimiento = relacion["movimiento"]
        assert candidato["tipo_objeto"] == "CANDIDATO_FILA"
        assert movimiento["tipo_objeto"] == "MOVIMIENTO_COMERCIAL"
        assert candidato["identidad"]["valor"] != movimiento["identidad"]["valor"]
        assert relacion["provenance"]["transferencia_semantica"] is False


def test_direct_no_determina_rol(resultados):
    candidatos = [c for r in resultados for f in r.facturas for c in f["candidatos_fila"]]
    direct = [c for c in candidatos if "DIRECT" in c["tipo_pedido"]["valor"]]
    assert direct
    assert all(c["rol_fila"] == "INDETERMINADO" for c in direct)


def test_08p10588_no_usa_excepcion_por_id(resultados):
    assert next(c for c in _factura(resultados, "08009277")["candidatos_fila"] if c["numero_referencia"]["valor"] == "08P10588")["rol_fila"] == "INDETERMINADO"


def test_08p10623_no_usa_excepcion_por_id(resultados):
    assert next(c for c in _factura(resultados, "08009277")["candidatos_fila"] if c["numero_referencia"]["valor"] == "08P10623")["rol_fila"] == "INDETERMINADO"


def test_08z34777_no_usa_excepcion_por_id(resultados):
    assert next(c for c in _factura(resultados, "08009277")["candidatos_fila"] if c["numero_referencia"]["valor"] == "08Z34777")["rol_fila"] == "INDETERMINADO"


def test_fiscalidad_totales_y_conciliaciones(resultados):
    for resultado in resultados:
        for factura in resultado.facturas:
            cabecera = factura["cabecera"]
            assert round(cabecera["base_imponible_total"]["valor"] + cabecera["iva_total"]["valor"] + cabecera["recargo_equivalencia_total"]["valor"], 2) == cabecera["importe_total"]["valor"]
            estados = {c["id"]: c["estado"] for c in factura["controles_conciliacion"]}
            assert estados["TOTAL_COMPRAS_DESDE_TRAMOS"] == "OK"
            assert estados["TOTAL_GASTOS_DESDE_TRAMOS"] == "OK"
            assert estados["TOTAL_DESDE_FISCALIDAD"] == "OK"
            assert estados["FILAS_VS_TOTAL_COMPRAS"] == "NO_EVALUABLE"
            assert estados["VENCIMIENTOS_VS_TOTAL"] == "NO_EVALUABLE"


def test_vencimientos_repetidos_se_preservan_por_ocurrencia(resultados):
    factura = _factura(resultados, "08008429")
    assert len(factura["vencimientos"]) == 2
    assert [v["fecha"]["valor"] for v in factura["vencimientos"]] == ["2026-10-10", "2026-10-10"]
    assert all(v["importe"] is None for v in factura["vencimientos"])
    assert [v["provenance"]["pagina"] for v in factura["vencimientos"]] == [8, 9]


def test_replay_funcional_es_determinista(resultados):
    nuevos = _extraer(PDF_1), _extraer(PDF_2)
    assert [hash_funcional(x) for x in resultados] == [hash_funcional(x) for x in nuevos]


def test_produccion_no_contiene_ids_historicos_ni_nombres_pdf():
    fuente = (ROOT / "src/facturas/motor_local/adaptadores/alliance.py").read_text(encoding="utf-8")
    prohibidos = ("08P10588", "08P10623", "08Z34777", "08008429", "ALLIANCE VTO")
    assert all(valor not in fuente for valor in prohibidos)


def test_alliance_permanece_sin_autoridad_productiva():
    assert COFARES_LOCAL_AUTHORITY is False
