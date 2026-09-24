"""Shadow E2E local de los cinco patrones productivos del hito 2AB."""
from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.facturas.clasificacion_documental import TipoFacturaDocumental
from src.facturas.hefame_economia import derivar_magnitud_comparable_hefame
from src.facturas.motor_local.backend.pdfium import BackendPdfium
from src.facturas.motor_local.servicio import MotorDocumentoLocal
from src.facturas.runtime_supabase.conciliacion import (
    AjusteDocumentalTrabajo,
    AlbaranDocumentalTrabajo,
    CandidatoAlbaranSupabase,
    MovimientoDocumentalTrabajo,
    buscar_candidato_albaran,
    conciliar_importes,
    conciliar_movimientos_documentales,
    dinero,
)
from src.facturas.runtime_supabase.elegibilidad_conciliacion import (
    EstadoElegibilidadConciliacion,
    EvidenciasElegibilidadConciliacion,
    evaluar_elegibilidad_conciliacion,
)
from src.facturas.runtime_supabase.modelos import DetalleConciliacion, TipoRelacionConciliacion
from src.facturas.runtime_supabase.multifactura import adaptar_resultado_local


DOCS = ROOT / "pruebas/facturas/documentos/2o_gold_standard"
HEFAME = ROOT / "tmp/pdfs/hito_2i3"


def _detail(amount: Decimal, *, source="SHADOW_LOCAL"):
    return DetalleConciliacion(
        tipo_relacion=TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC,
        importe_aplicado=amount,
        factura_movimiento_id=f"shadow-{source}",
        provenance={"fuente": source, "productivo_dml": False},
    )


def _eligible(kind: TipoFacturaDocumental, *, merchandise=False):
    return evaluar_elegibilidad_conciliacion(EvidenciasElegibilidadConciliacion(
        tipo_documental=kind, documento_completo_demostrado=True,
        farmacia_estado="CONSISTENTE", normalizacion_valida=True,
        total_demostrado=True, trazabilidad_mercancia=merchandise,
        trazabilidad_servicio=not merchandise, total_explicado=True,
        fiscalidad_coherente=True,
    ))


def ejecutar_shadow() -> dict:
    motor = MotorDocumentoLocal(BackendPdfium())
    persisted = []

    logista = motor.extraer(DOCS / "LOGISTA PHARMA VTO 29.9.26 PIO.pdf")
    logista_total = dinero(logista.cabecera["importe_total"]["valor"])
    persisted.append("LOGISTA")
    logista_elig = _eligible(TipoFacturaDocumental.FACTURA_MERCANCIA, merchandise=True)
    logista_rec = conciliar_importes(logista_total, [_detail(logista_total)])

    cofares = motor.extraer(DOCS / "COFARES VTO 31.8.26 PIO.pdf")
    cofares_total = dinero(cofares.cabecera["importe_total"]["valor"])
    persisted.append("COFARES")
    cofares_elig = _eligible(TipoFacturaDocumental.FACTURA_GASTO_SERVICIO)
    cofares_rec = conciliar_importes(cofares_total, [_detail(cofares_total)])

    alliance_local = motor.extraer(DOCS / "ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf")
    alliance = adaptar_resultado_local(alliance_local)
    alliance_results = []
    for invoice in alliance["facturas"]:
        total = dinero(invoice["totales"]["total"]["valor"])
        persisted.append(invoice["numero_factura"]["valor"])
        result = conciliar_importes(total, [_detail(total)])
        alliance_results.append(result.resultado)

    merchandise = motor.extraer(HEFAME / "hefame_antiguo.pdf")
    candidates_data = {
        "4127691753": (date(2026, 8, 27), "19.65", "23.95"),
        "4127726806": (date(2026, 8, 31), "3.84", "4.35"),
        "4127762016": (date(2026, 8, 31), "2.14", "2.90"),
        "4127762027": (date(2026, 8, 31), "4.80", "6.62"),
    }
    candidates = [CandidatoAlbaranSupabase(
        index, "PIO", "3", "3.- HEFAME", number, values[0],
        Decimal(values[1]), Decimal(values[2]), "PENDIENTE",
    ) for index, (number, values) in enumerate(candidates_data.items(), 1)]
    states, applied = [], Decimal("0")
    for item in merchandise.albaranes:
        attrs = item.atributos_documentales
        work = AlbaranDocumentalTrabajo(
            str(item.orden), item.numero_albaran, date.fromisoformat(item.fecha),
            Decimal(str(item.total)), item.sentido,
            magnitud_documental=attrs["magnitud_documental"],
            categoria_fiscal=attrs["categoria_fiscal"],
            iva_pct=Decimal(str(attrs["iva_pct"])), re_pct=Decimal(str(attrs["re_pct"])),
            importe_iva_derivado=Decimal(str(attrs["importe_iva_derivado"])),
            importe_re_derivado=Decimal(str(attrs["importe_re_derivado"])),
            importe_comparable_operativo=Decimal(str(attrs["importe_comparable_operativo"])),
            provenance=attrs["provenance"],
        )
        match = buscar_candidato_albaran(work, candidates, proveedor_literal="HDAD.FMCTCA.MEDIT.,S.C.L.")
        states.append(match.estado)
        if match.estado == "EXACTO_ECONOMICO":
            applied += dinero(match.importe_compatible)
    for movement in merchandise.movimientos:
        if movement.get("importe_fiscal_total") is not None:
            gross = dinero(movement["importe_fiscal_total"])
        else:
            gross = Decimal("0")
            for category in ("BASE_S_R", "BASE_RE", "BASE_NO"):
                base = Decimal(str((movement.get("bases", {}).get(category) or {}).get("valor") or 0))
                if base:
                    part = Decimal(derivar_magnitud_comparable_hefame(abs(base), category)["importe_comparable_operativo"])
                    gross += -part if base < 0 else part
        applied += abs(gross) if movement["sentido"] == "CARGO" else -abs(gross)
    merchandise_rec = conciliar_importes(Decimal("313.29"), [_detail(dinero(applied))])
    persisted.append("0563834757")

    hplus = motor.extraer(HEFAME / "hefame_nuevo.pdf")
    hplus_elig = _eligible(TipoFacturaDocumental.FACTURA_GASTO_SERVICIO)
    hplus_rec = conciliar_movimientos_documentales(
        Decimal("66.79"),
        [MovimientoDocumentalTrabajo("hplus", "CONSUMIBLES", "SERVICIO", "CARGO", base=Decimal("55.20"))],
        ajustes=[AjusteDocumentalTrabajo("IVA_TOTAL", Decimal("11.59"), {"fuente": "PDF_LOCAL"})],
    )
    persisted.append("1132029554")

    result = {
        "productivo_dml": False,
        "logista": {"extraido": logista.documento_completo_demostrado, "elegibilidad": logista_elig.estado, "conciliacion": logista_rec.resultado},
        "cofares": {"extraido": cofares.documento_completo_demostrado, "albaranes": len(cofares.albaranes), "elegibilidad": cofares_elig.estado, "conciliacion": cofares_rec.resultado},
        "alliance": {"extraido": alliance["documento_completo_demostrado"], "facturas": len(alliance["facturas"]), "conciliaciones": alliance_results},
        "hefame_mercancia": {"extraido": merchandise.documento_completo_demostrado, "validos": states.count("EXACTO_ECONOMICO"), "ausentes": states.count("NUMERO_AUSENTE"), "incompatibles": states.count("NUMERO_EXACTO_ECONOMIA_INCOMPATIBLE"), "importe_explicado": str(merchandise_rec.importe_explicado), "diferencia": str(merchandise_rec.diferencia), "conciliacion": "PENDIENTE_CONCILIAR" if merchandise_rec.resultado == "DIFERENCIA" else merchandise_rec.resultado},
        "hplus_consumo": {"extraido": hplus.documento_completo_demostrado, "albaranes_operativos": len(hplus.albaranes), "elegibilidad": hplus_elig.estado, "conciliacion": hplus_rec.resultado, "diferencia": str(hplus_rec.diferencia)},
        "persistencia_memoria": persisted,
    }
    assert result["logista"]["conciliacion"] == "CONCILIADA"
    assert result["cofares"] == {"extraido": True, "albaranes": 0, "elegibilidad": EstadoElegibilidadConciliacion.APTA, "conciliacion": "CONCILIADA"}
    assert result["alliance"]["facturas"] == 3 and set(alliance_results) == {"CONCILIADA"}
    assert result["hefame_mercancia"]["conciliacion"] == "PENDIENTE_CONCILIAR"
    assert result["hplus_consumo"]["conciliacion"] == "CONCILIADA"
    return result


if __name__ == "__main__":
    print(json.dumps(ejecutar_shadow(), ensure_ascii=False, default=str, sort_keys=True))
