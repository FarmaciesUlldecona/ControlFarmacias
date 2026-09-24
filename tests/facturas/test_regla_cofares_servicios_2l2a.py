from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.clasificacion_documental import (
    TipoFacturaDocumental,
    clasificar_factura_por_contenido,
)
from src.facturas.motor_local.adaptadores.cofares import (
    documentar_sentido_decision_funcional_pio_cofares,
)
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.runtime_supabase.conciliacion import (
    AjusteDocumentalTrabajo,
    MovimientoDocumentalTrabajo,
    conciliar_factura_documental,
    conciliar_movimientos_documentales,
)
from src.facturas.runtime_supabase.modelos import DetalleConciliacion, TipoRelacionConciliacion


ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/COFARES VTO 31.8.26 PIO.pdf"


@pytest.mark.parametrize(
    ("concepto", "sentido"),
    [
        ("Servicio Logístico", "CARGO"),
        ("Domiciliación bancaria", "CARGO"),
        ("Servicio Cofares Directo", "CARGO"),
        ("Serv Integral Distribución", "CARGO"),
        ("TOTAL DEVOLUCIONES", "ABONO"),
    ],
)
def test_sentidos_cofares_autorizados_por_pio(concepto, sentido):
    decision = documentar_sentido_decision_funcional_pio_cofares(concepto, "SERVICIO")
    assert decision is not None
    assert decision["valor"] == sentido
    assert decision["literal"] == concepto
    assert decision["autoridad"] == "PIO"


def test_concepto_desconocido_no_inventa_sentido():
    assert documentar_sentido_decision_funcional_pio_cofares(
        "Servicio COFARES no autorizado", "SERVICIO"
    ) is None


@pytest.mark.parametrize(
    ("albaranes", "movimientos", "esperado"),
    [
        ([], [{"categoria": "SERVICIO", "sentido": "CARGO"}], "FACTURA_GASTO_SERVICIO"),
        ([{"numero": "A-1"}], [], "FACTURA_MERCANCIA"),
        ([{"numero": "A-1"}], [{"categoria": "SERVICIO", "sentido": "CARGO"}], "FACTURA_MIXTA"),
        ([], [{"categoria": "SERVICIO", "sentido": None}], "TIPO_NO_DEMOSTRADO"),
    ],
)
def test_clasificacion_procede_del_contenido(albaranes, movimientos, esperado):
    resultado = clasificar_factura_por_contenido(albaranes, movimientos)
    assert resultado.tipo.value == esperado
    assert resultado.requiere_revision is (esperado == "TIPO_NO_DEMOSTRADO")


@pytest.mark.skipif(not PDF.exists(), reason="factura COFARES auditada no disponible")
def test_factura_5460017198_es_servicio_sin_albaranes_y_con_importes_no_inventados():
    factura = MotorDocumentoLocal(BackendPdfium()).extraer(PDF).facturas[0]
    assert factura["cabecera"]["numero_factura"]["valor"] == "5460017198"
    assert factura["clasificacion_documental"]["tipo"] == "FACTURA_GASTO_SERVICIO"
    assert factura["albaranes"] == []
    assert all(m["importe"] is None for m in factura["movimientos"])
    assert any(i["codigo"] == "IMPORTE_MOVIMIENTO_NO_DOCUMENTADO" for i in factura["incidencias"])
    assert not any("ALBARAN_NO_LOCALIZADO" in i["codigo"] for i in factura["incidencias"])


@pytest.mark.skipif(not PDF.exists(), reason="factura COFARES auditada no disponible")
def test_factura_5460017198_concilia_por_bases_y_fiscalidad_documentadas():
    factura = MotorDocumentoLocal(BackendPdfium()).extraer(PDF).facturas[0]
    movimientos = [
        MovimientoDocumentalTrabajo(
            id=f"mov-{m['orden']}",
            concepto_literal=m["descripcion_literal"]["valor"],
            tipo=m["categoria"],
            sentido=m["sentido"],
            importe=None if m["importe"] is None else Decimal(str(m["importe"]["valor"])),
            base=None if m["base"] is None else Decimal(str(m["base"]["valor"])),
            provenance=m["provenance"],
        )
        for m in factura["movimientos"]
    ]
    ajustes = [
        AjusteDocumentalTrabajo("IVA total", Decimal("28.87"), {"pagina": 1}),
        AjusteDocumentalTrabajo("Recargo equivalencia total", Decimal("0.59"), {"pagina": 1}),
    ]
    resultado = conciliar_movimientos_documentales("177.74", movimientos, ajustes=ajustes)
    assert resultado.resultado == "CONCILIADA"
    assert resultado.importe_explicado == Decimal("177.7400")
    assert resultado.diferencia == Decimal("0.0000")


def test_movimiento_sin_importe_ni_base_no_fuerza_conciliacion():
    movimiento = MovimientoDocumentalTrabajo(
        id="mov-1", concepto_literal="Servicio Logístico", tipo="SERVICIO",
        sentido="CARGO", importe=None, base=None,
    )
    resultado = conciliar_movimientos_documentales("10", [movimiento])
    assert resultado.resultado == "PENDIENTE_REVISION_PIO"
    assert resultado.resultado != "CONCILIADA"


def test_total_fuera_de_tolerancia_no_concilia():
    movimiento = MovimientoDocumentalTrabajo(
        id="mov-1", concepto_literal="Servicio Logístico", tipo="SERVICIO",
        sentido="CARGO", importe=Decimal("9.94"),
    )
    resultado = conciliar_movimientos_documentales("10", [movimiento])
    assert resultado.resultado == "DIFERENCIA"
    assert resultado.diferencia == Decimal("0.0600")


def test_total_explicado_a_cinco_centimos_concilia():
    movimiento = MovimientoDocumentalTrabajo(
        id="mov-1", concepto_literal="Servicio Logístico", tipo="SERVICIO",
        sentido="CARGO", importe=Decimal("9.95"),
    )
    assert conciliar_movimientos_documentales("10", [movimiento]).resultado == "CONCILIADA"


def test_factura_mixta_suma_albaranes_y_movimientos():
    albaran = DetalleConciliacion(
        tipo_relacion=TipoRelacionConciliacion.UNO_A_UNO,
        importe_aplicado=Decimal("80"),
        albaran_farmacia="PIO", albaran_id_contador=1,
        factura_albaran_extraido_id="alb-1",
    )
    movimiento = MovimientoDocumentalTrabajo(
        id="mov-1", concepto_literal="Servicio Logístico", tipo="SERVICIO",
        sentido="CARGO", importe=Decimal("20"),
    )
    resultado = conciliar_factura_documental(
        TipoFacturaDocumental.FACTURA_MIXTA,
        "100", detalles_albaranes=[albaran], movimientos=[movimiento],
    )
    assert resultado.resultado == "CONCILIADA"
    assert resultado.importe_explicado == Decimal("100.0000")
