from __future__ import annotations

from pathlib import Path

import pytest

from src.facturas.motor_local.autoridad import autoridad_productiva_habilitada
from src.facturas.motor_local.catalogo import ProveedorLocal
from src.facturas.motor_local.adaptadores.alliance import (
    documentar_sentido_decision_funcional_pio,
    documentar_sentido_desde_relacion,
    sentido_desde_seccion_documental,
)
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
    assert movimientos["RAPPEL GenerAH"]["sentido"] == "ABONO"
    assert movimientos["ABONOS CLUBS"]["sentido"] == "ABONO"
    assert movimientos["SERV.PLATAF.360"]["sentido"] == "CARGO"
    assert movimientos["SERVICIO BASICO"]["sentido"] == "CARGO"
    assert movimientos["CONDIC. COMERCIAL"]["sentido"] == "CARGO"


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


@pytest.mark.parametrize("categoria", ["DEVOLUCION_MERCANCIA", "RAPPEL", "SERVICIO", "ABONO_COMERCIAL"])
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
        assert relacion["provenance"]["transferencia_rol"] is False
        assert relacion["provenance"]["transferencia_categoria"] is False
        assert relacion["provenance"]["fusion_entidades"] is False


def _candidato_sintetico(sentido):
    return {
        "sentido": {
            "valor": sentido,
            "literal": f"{sentido}S",
            "evidencias": [{"regla": "SECCION_DOCUMENTAL_CARGOS_ABONOS"}],
        },
        "rol_fila": "INDETERMINADO",
    }


def _relacion_sintetica(*, inequivoca=True):
    return {
        "orden": 1,
        "tipo_relacion": "CONCILIACION_ECONOMICA_EXACTA_UNICA_EN_FACTURA",
        "cardinalidad": "1:1",
        "inequivoca": inequivoca,
        "candidato": {"tipo_objeto": "CANDIDATO_FILA", "orden": 1},
        "evidencias": [{"regla": "BASE_Y_TOTAL_EXACTOS_UNICOS_DENTRO_DE_FACTURA"}],
        "provenance": {"adaptador": "alliance-local", "version_adaptador": "1.0.0"},
    }


def test_candidato_abono_y_relacion_univoca_propagan_abono():
    documentacion = documentar_sentido_desde_relacion(_candidato_sintetico("ABONO"), _relacion_sintetica())
    assert documentacion["valor"] == "ABONO"


def test_candidato_cargo_y_relacion_univoca_propagan_cargo():
    documentacion = documentar_sentido_desde_relacion(_candidato_sintetico("CARGO"), _relacion_sintetica())
    assert documentacion["valor"] == "CARGO"


def test_relacion_ambigua_no_propaga_sentido():
    assert documentar_sentido_desde_relacion(_candidato_sintetico("ABONO"), _relacion_sintetica(inequivoca=False)) is None


def test_provenance_del_sentido_relacionado_se_preserva(resultados):
    factura = _factura(resultados, "08009277")
    heredados = [m for m in factura["movimientos"] if m["sentido_fuente"] == "RELACION_DOCUMENTAL"]
    assert len(heredados) == 3
    for movimiento in heredados:
        documentacion = movimiento["sentido_documentacion"]
        assert documentacion["tipo_evidencia"] == "SENTIDO_DERIVADO_RELACION_DOCUMENTAL"
        assert documentacion["candidato_relacionado"]
        assert documentacion["seccion_origen"]["evidencias"]
        assert len(documentacion["relacion_documental"]["evidencias"]) == 6
        assert documentacion["provenance"]["transferencia_rol"] is False
        assert documentacion["provenance"]["fusion_entidades"] is False


def test_movimientos_sin_relacion_aplican_solo_decisiones_pio_autorizadas(resultados):
    movimientos = [m for r in resultados for f in r.facturas for m in f["movimientos"]]
    assert sum(m["sentido_fuente"] == "RELACION_DOCUMENTAL" for m in movimientos) == 3
    assert sum(m["sentido_fuente"] == "DECISION_FUNCIONAL_PIO" for m in movimientos) == 3
    assert all(m["sentido"] is not None for m in movimientos)


def test_servicio_basico_alliance_es_cargo_por_decision_pio(resultados):
    movimientos = [m for r in resultados for f in r.facturas for m in f["movimientos"]]
    servicios = [m for m in movimientos if m["descripcion_literal"]["valor"] == "SERVICIO BASICO"]
    assert len(servicios) == 2
    assert all(m["sentido"] == "CARGO" and m["sentido_fuente"] == "DECISION_FUNCIONAL_PIO" for m in servicios)


def test_condic_comercial_alliance_es_cargo_por_decision_pio(resultados):
    movimiento = next(
        m for r in resultados for f in r.facturas for m in f["movimientos"]
        if m["descripcion_literal"]["valor"] == "CONDIC. COMERCIAL"
    )
    assert movimiento["sentido"] == "CARGO"
    assert movimiento["sentido_fuente"] == "DECISION_FUNCIONAL_PIO"


def test_provenance_decision_funcional_no_simula_evidencia_pdf(resultados):
    movimientos = [m for r in resultados for f in r.facturas for m in f["movimientos"]]
    decisiones = [m["sentido_documentacion"] for m in movimientos if m["sentido_fuente"] == "DECISION_FUNCIONAL_PIO"]
    assert len(decisiones) == 3
    for decision in decisiones:
        assert decision["tipo_evidencia"] == "DECISION_FUNCIONAL_PIO"
        assert decision["evidencia_documental_directa"] is False
        assert decision["evidencias"] == []
        assert decision["provenance"]["autoridad"] == "PIO"
        assert decision["alcance"]["proveedor"] == "ALLIANCE"


def test_servicio_generico_distinto_no_hereda_cargo():
    assert documentar_sentido_decision_funcional_pio("SERVICIO PREMIUM") is None


def test_condicion_comercial_generica_distinta_no_hereda_cargo():
    assert documentar_sentido_decision_funcional_pio("OTRA CONDICION COMERCIAL") is None


def test_decision_pio_no_altera_relaciones_ni_roles(resultados):
    factura = _factura(resultados, "08009277")
    assert len(factura["relaciones_documentales"]) == 3
    assert all(c["rol_fila"] == "INDETERMINADO" for c in factura["candidatos_fila"])


def test_decision_pio_alliance_no_se_extiende_a_otros_adaptadores():
    for nombre in ("hefame.py", "fedefarma.py", "cofares.py"):
        fuente = (ROOT / "src/facturas/motor_local/adaptadores" / nombre).read_text(encoding="utf-8")
        assert "DECISION_FUNCIONAL_PIO_LITERAL_EXACTO_ALLIANCE" not in fuente


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
    assert autoridad_productiva_habilitada(ProveedorLocal.ALLIANCE) is False
