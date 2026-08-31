from __future__ import annotations

from pathlib import Path

import pytest

from src.facturas.motor_local.autoridad import COFARES_LOCAL_AUTHORITY
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal, hash_funcional


ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "pruebas/facturas/documentos/2o_gold_standard"
PREFIJOS = ("ECOCEUTICS", "EPORTS", "FARMACIA GUIMERA", "LOGISTA PHARMA", "LOREAL", "MORETTI", "TOTALCARE")


def _pdfs():
    if not CORPUS.exists():
        pytest.skip("corpus local externo ausente")
    encontrados = [p for p in CORPUS.glob("*.pdf") if p.name.startswith(PREFIJOS)]
    if len(encontrados) != 9:
        pytest.skip("corpus GOLD pequeño externo incompleto")
    return encontrados


@pytest.fixture(scope="module")
def resultados():
    motor = MotorDocumentoLocal(BackendPdfium())
    return {p: motor.extraer(p) for p in _pdfs()}


def test_siete_proveedores_y_nueve_pdfs_quedan_clasificados(resultados):
    layouts = [r.documento["layout"] for r in resultados.values()]
    assert sum(layout is not None for layout in layouts) == 7
    assert sum(layout is None for layout in layouts) == 2
    assert set(layout for layout in layouts if layout) == {
        "ecoceutics-local", "eports-local", "logista-pharma-local",
        "loreal-local", "moretti-local", "totalcare-local",
    }


def test_documentos_con_texto_tienen_factura_completa_y_conciliaciones_ok(resultados):
    facturas = [f for r in resultados.values() for f in r.facturas]
    assert len(facturas) == 7
    for factura in facturas:
        assert factura["segmento"]["identidad"]
        assert factura["cabecera"]["numero_factura"]["evidencias"]
        assert factura["cabecera"]["importe_total"]["evidencias"]
        assert factura["impuestos"] and factura["vencimientos"] and factura["otros"]
        assert {c["estado"] for c in factura["controles_conciliacion"]} == {"OK"}
        assert factura["incidencias"] == []


def test_direcciones_visibles_quedan_estructuradas_con_evidencia(resultados):
    facturas = [f for r in resultados.values() for f in r.facturas]
    for factura in facturas:
        for rol in ("proveedor", "destinatario"):
            direccion = factura["cabecera"][rol]["direccion"]
            assert direccion["valor"]
            assert direccion["evidencias"]
            assert "E-mail:" not in direccion["valor"]


def test_guimera_queda_pendiente_ocr_sin_ejecutarlo(resultados):
    pendientes = [r for p, r in resultados.items() if p.name.startswith("FARMACIA GUIMERA")]
    assert len(pendientes) == 2
    for resultado in pendientes:
        assert resultado.documento["layout"] is None
        assert resultado.facturas == []
        assert resultado.incidencias == [{"codigo": "PENDIENTE_OCR", "estado": "SIN_TEXTO_NATIVO", "ocr_ejecutado": False}]


def test_albaranes_y_detalles_documentales_se_preservan(resultados):
    facturas = [f for r in resultados.values() for f in r.facturas]
    assert sum(len(f["albaranes"]) for f in facturas) == 5
    assert all(any(o.get("lineas") for o in f["otros"]) for f in facturas)
    assert all(
        linea["literal"]["evidencias"]
        for f in facturas for otro in f["otros"] for linea in otro.get("lineas", [])
    )


def test_quota_ready_es_servicio_y_cargo_por_decision_pio(resultados):
    movimientos = [m for r in resultados.values() for f in r.facturas for m in f["movimientos"]]
    quota = next(m for m in movimientos if "QUOTA READY" in m["descripcion_literal"]["valor"])
    assert quota["categoria"] == "SERVICIO"
    assert quota["sentido"] == "CARGO"
    assert quota["base"]["valor"] == 339.0
    assert quota["iva"]["valor"] == 71.19
    assert quota["importe"]["valor"] == 410.19
    assert quota["sentido_documentacion"]["evidencia_documental_directa"] is False
    assert quota["sentido_documentacion"]["provenance"]["autoridad"] == "PIO"


def test_cinco_servicios_eports_son_cargos_por_decision_pio(resultados):
    factura = next(f for r in resultados.values() for f in r.facturas if f["layout"] == "EPORTS_FACTURA_SERVICIOS_V1")
    assert len(factura["movimientos"]) == 5
    assert [m["importe"]["valor"] for m in factura["movimientos"]] == [5.0, 15.0, 10.0, 21.0, 30.0]
    assert sum(m["base"]["valor"] for m in factura["movimientos"]) == 81.0
    assert all(m["categoria"] == "SERVICIO" and m["sentido"] == "CARGO" for m in factura["movimientos"])
    assert all(m["sentido_fuente"] == "DECISION_FUNCIONAL_PIO" for m in factura["movimientos"])
    assert all(m["sentido_documentacion"]["alcance"]["proveedor"] == "EPORTS" for m in factura["movimientos"])


def test_regla_eports_no_se_aplica_a_otros_proveedores(resultados):
    otros = [m for r in resultados.values() for f in r.facturas if f["layout"] != "EPORTS_FACTURA_SERVICIOS_V1" for m in f["movimientos"]]
    assert all(m.get("sentido_documentacion", {}).get("provenance", {}).get("regla") != "SERVICIOS_TELEFONIA_INTERNET_EPORTS_SON_CARGO" for m in otros)


def test_albaranes_y_notas_conservan_sentido_null_valido(resultados):
    albaranes = [a for r in resultados.values() for f in r.facturas for a in f["albaranes"]]
    assert len(albaranes) == 5
    assert all(a.sentido is None and a.rol_fila == "DETALLE_ALBARAN" for a in albaranes)


def test_loreal_5_20_es_recargo_por_decision_pio(resultados):
    factura = next(f for r in resultados.values() for f in r.facturas if f["layout"] == "LOREAL_FACTURA_TRES_PAGINAS_V1")
    recargo = factura["impuestos"][1]
    assert recargo["naturaleza"] == "RECARGO_EQUIVALENCIA"
    assert recargo["tipo_recargo_equivalencia"]["valor"] == 5.2
    assert recargo["cuota_recargo_equivalencia"]["valor"] == 16.62
    assert recargo["naturaleza_fuente"] == "DECISION_FUNCIONAL_PIO"
    assert recargo["naturaleza_documentacion"]["evidencia_documental_directa"] is False
    assert recargo["provenance"]["evidencia_geometrica_valores_preservada"] is True


def test_punto_verde_es_aportacion_incluida_sin_doble_conteo(resultados):
    factura = next(f for r in resultados.values() for f in r.facturas if f["layout"] == "LOREAL_FACTURA_TRES_PAGINAS_V1")
    punto = next(o for o in factura["otros"] if o.get("categoria") == "APORTACION_AMBIENTAL_INCLUIDA")
    assert punto["importe"]["valor"] == 3.96
    assert punto["sentido"] is None
    assert punto["es_movimiento_economico_independiente"] is False
    assert punto["participa_en_suma_total"] is False
    assert punto["doble_conteo"] is False
    assert punto["incluido_en_factura"]["evidencias"]
    assert not any(m.get("categoria") == "APORTACION_AMBIENTAL_INCLUIDA" for m in factura["movimientos"])
    assert factura["controles_conciliacion"][0]["estado"] == "OK"


def test_replay_funcional_es_determinista(resultados):
    motor = MotorDocumentoLocal(BackendPdfium())
    assert {p: hash_funcional(r) for p, r in resultados.items()} == {
        p: hash_funcional(motor.extraer(p)) for p in resultados
    }


def test_adaptadores_nuevos_permanecen_shadow():
    assert COFARES_LOCAL_AUTHORITY is False


def test_produccion_no_contiene_ids_del_corpus_ni_nombres_de_pdf():
    fuente = (ROOT / "src/facturas/motor_local/adaptadores/gold_pequenos.py").read_text(encoding="utf-8")
    prohibidos = tuple(p.stem for p in _pdfs())
    assert all(valor not in fuente for valor in prohibidos)
