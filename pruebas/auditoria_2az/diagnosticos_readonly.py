"""Hito 2AZ, fase 1: diagnosticos READ_ONLY previos (1.1 a 1.4), sin corregir nada.

Uso:
  python -B pruebas/auditoria_2az/diagnosticos_readonly.py <supabase.json> <motor_2ay.json> <salida.json>

No se conecta a nada: ``supabase.json`` es un volcado READ_ONLY
(``pruebas/auditoria_2ay/supabase_readonly.py``) y los PDF se leen del mirror
(ruta localizada por SHA en ``motor_2ay.json``). Ejecuta el motor local vigente en
memoria. El nombre del archivo no se usa como dato (R13). Salida fuera del repo.
"""
from __future__ import annotations

import itertools
import json
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ay"))

from analisis_2ay import candidatos_operacionales  # noqa: E402
from banco_extraccion import _salida_fuera_del_repo  # noqa: E402
from src.facturas.motor_local.backend.pdfium import BackendPdfium  # noqa: E402
from src.facturas.motor_local.servicio import MotorDocumentoLocal  # noqa: E402
from src.facturas.runtime_supabase.conciliacion import (  # noqa: E402
    VENTANA_FECHA_DIAS, AlbaranDocumentalTrabajo, buscar_candidato_albaran, canonicalizar_proveedor,
    normalizar_numero_albaran)
from src.facturas.runtime_supabase.multifactura import adaptar_resultado_local  # noqa: E402

CENT = Decimal("0.01")


def _v(c):
    return c.get("valor") if isinstance(c, dict) else None


def _d(x) -> Decimal | None:
    return None if x in (None, "") else Decimal(str(x))


def _localizar(motor_2ay: list[dict], numero: str) -> tuple[str, list]:
    for d in motor_2ay:
        for f in (d.get("oficial") or {}).get("facturas_local") or []:
            if f.get("numero") == numero:
                return d["ruta"], f["segmento"]["paginas"]
    raise SystemExit(f"FACTURA_NO_LOCALIZADA:{numero}")


def _factura_motor(ruta: str, numero: str):
    local = MotorDocumentoLocal(BackendPdfium()).extraer(ruta)
    raw = next(f for f in local.facturas if _v(f["cabecera"]["numero_factura"]) == numero)
    normalizada = next(f for f in adaptar_resultado_local(local)["facturas"] if _v(f["numero_factura"]) == numero)
    return local, raw, normalizada


def _filas_candidatas(raw: dict) -> list[dict]:
    return [{"referencia": _v(c.get("numero_referencia")), "fecha": _v(c.get("fecha")), "tipo_pedido": _v(c.get("tipo_pedido")),
             "bloque": _v(c.get("sentido")), "base": _v(c.get("base")), "total": _v(c.get("total")),
             "concepto": (c.get("clasificacion_economica") or {}).get("concepto"),
             "regla": (c.get("clasificacion_economica") or {}).get("regla")} for c in raw.get("candidatos_fila") or []]


def _en_supabase(albaranes: list[dict], numero: str) -> list[dict]:
    clave = normalizar_numero_albaran(numero)
    return [a for a in albaranes if normalizar_numero_albaran(a["numero_albaran"]) == clave]


def diagnostico_filas(albaranes, ruta, numero, tipos=None) -> dict:
    _, raw, _ = _factura_motor(ruta, numero)
    filas = [f for f in _filas_candidatas(raw) if tipos is None or f["tipo_pedido"] in tipos]
    operacionales = candidatos_operacionales(albaranes)
    for f in filas:
        f["supabase_por_numero"] = _en_supabase(albaranes, f["referencia"])
        doc = AlbaranDocumentalTrabajo(id="x", numero=f["referencia"], fecha=date.fromisoformat(f["fecha"]),
                                       importe=_d(f["total"]), sentido=f["bloque"])
        b = buscar_candidato_albaran(doc, operacionales, proveedor_literal="ALLIANCE HEALTHCARE ESPANA, S.A.")
        f["busqueda_con_regla_oficial"] = {"estado": b.estado, "coincidencia_numero": b.coincidencia_numero,
                                           "candidato": None if b.candidato is None else {
                                               "numero": b.candidato.numero_albaran, "fecha": str(b.candidato.fecha),
                                               "puc": str(b.candidato.importe_puc), "id_contador": b.candidato.id_contador}}
    return {"factura": numero, "total_factura": _v(raw["cabecera"]["importe_total"]), "filas": filas}


def diagnostico_08011733(albaranes, ruta, numero="08011733") -> dict:
    _, raw, f = _factura_motor(ruta, numero)
    total = _d(_v(f["totales"]["total"]))
    operacionales = candidatos_operacionales(albaranes)
    docs = [{"numero": _v(a.get("numero")), "fecha": (_v(a.get("fecha")) or {}).get("iso"),
             "total": _d(_v(a.get("importe_total"))), "base": _d(_v(a.get("importe_base"))),
             "sentido": a.get("sentido"), "tipo_pedido": _v(a.get("tipo_pedido"))} for a in f.get("albaranes") or []]
    fechas = [date.fromisoformat(a["fecha"]) for a in docs if a["fecha"]]
    inicio, fin = min(fechas) - timedelta(days=VENTANA_FECHA_DIAS), max(fechas) + timedelta(days=VENTANA_FECHA_DIAS)
    ventana = [c for c in operacionales if inicio <= c.fecha <= fin]
    lineas, usados = [], set()
    for a in docs:
        b = buscar_candidato_albaran(
            AlbaranDocumentalTrabajo(id="x", numero=a["numero"], fecha=date.fromisoformat(a["fecha"]), importe=a["total"],
                                     sentido=a["sentido"]), ventana, proveedor_literal="ALLIANCE HEALTHCARE ESPANA, S.A.")
        linea = {**{k: (str(v) if isinstance(v, Decimal) else v) for k, v in a.items()},
                 "estado": b.estado, "coincidencia": b.coincidencia_numero,
                 "casado": None if b.candidato is None else {"numero": b.candidato.numero_albaran, "fecha": str(b.candidato.fecha),
                                                              "puc": str(b.candidato.importe_puc), "pvp": str(b.candidato.importe_pvp),
                                                              "id_contador": b.candidato.id_contador}}
        if b.candidato is not None and b.importe_compatible is not None:
            usados.add(b.candidato.id_contador)
            aplicado = -abs(b.importe_compatible) if a["sentido"] == "ABONO" else b.importe_compatible
            documental = -abs(a["total"]) if a["sentido"] == "ABONO" else a["total"]
            linea["diferencia_doc_menos_farmatic"] = str((documental - aplicado).quantize(CENT))
        else:
            # Para AMBIGUO: candidatos del mismo numero en la ventana (informativo).
            linea["candidatos_numero"] = [{"numero": c.numero_albaran, "fecha": str(c.fecha), "puc": str(c.importe_puc),
                                           "id_contador": c.id_contador}
                                          for c in ventana if normalizar_numero_albaran(c.numero_albaran)
                                          == normalizar_numero_albaran(a["numero"])]
        lineas.append(linea)
    movs = [{"tipo": m.get("tipo"), "descripcion": _v(m.get("descripcion_literal")), "sentido": m.get("sentido"),
             "base": _v(m.get("base")), "importe": _v(m.get("importe"))} for m in f.get("movimientos_comerciales") or []]
    suma_movs = sum(((-abs(_d(m["importe"])) if m["sentido"] == "ABONO" else abs(_d(m["importe"])))
                     for m in movs if m["importe"] is not None), Decimal(0))
    suma_doc = sum(((-abs(a["total"]) if a["sentido"] == "ABONO" else a["total"]) for a in docs), Decimal(0))
    a_rondeo = sum((Decimal(l["diferencia_doc_menos_farmatic"]) for l in lineas if "diferencia_doc_menos_farmatic" in l),
                   Decimal(0))
    b_sin_casar = [l for l in lineas if l["casado"] is None]
    suma_b = sum((Decimal(l["total"]) * (-1 if l["sentido"] == "ABONO" else 1) for l in b_sin_casar), Decimal(0))
    no_promovidas = [r for r in _filas_candidatas(raw) if r["concepto"] == "NO_DEMOSTRABLE"]
    hueco_documental = total - (suma_doc + suma_movs)
    proveedor = canonicalizar_proveedor("ALLIANCE HEALTHCARE ESPANA, S.A.")
    d_farmatic = [{"numero": c.numero_albaran, "fecha": str(c.fecha), "puc": str(c.importe_puc), "id_contador": c.id_contador}
                  for c in ventana if canonicalizar_proveedor(c.proveedor) == proveedor and c.id_contador not in usados]
    diferencia = (hueco_documental + a_rondeo + suma_b).quantize(CENT)
    # Combinaciones de partidas no explicadas que suman exactamente la diferencia simulada (18,07).
    partidas = ([("RONDEO_CASADOS", a_rondeo)] + [(f"SIN_CASAR {l['numero']}", Decimal(l["total"])) for l in b_sin_casar]
                + [(f"NO_PROMOVIDA {r['tipo_pedido']} {r['referencia']}", _d(r["total"])) for r in no_promovidas]
                + [("HUECO_DOCUMENTAL_RESTANTE", hueco_documental - sum((_d(r["total"]) for r in no_promovidas), Decimal(0)))])
    combinaciones = [[n for n, _ in combo] for k in range(1, len(partidas) + 1) for combo in itertools.combinations(partidas, k)
                     if abs(sum(v for _, v in combo) - diferencia) < Decimal("0.005")]
    return {
        "factura": numero, "total": str(total), "albaranes_documentales": len(docs), "movimientos": movs,
        "suma_albaranes_documentales": str(suma_doc), "suma_movimientos": str(suma_movs),
        "hueco_documental_total_menos_doc": str(hueco_documental.quantize(CENT)),
        "a_suma_diferencias_casados_doc_menos_farmatic": str(a_rondeo.quantize(CENT)),
        "b_lineas_pdf_sin_casar": b_sin_casar, "b_suma": str(suma_b),
        "c_filas_no_promovidas": no_promovidas,
        "d_farmatic_mismo_proveedor_ventana_no_casados": d_farmatic,
        "diferencia_reconstruida": str(diferencia),
        "combinaciones_que_explican_la_diferencia": combinaciones,
        "lineas": lineas,
    }


def vencimientos_literales(ruta: str, paginas: list) -> list[dict]:
    doc = BackendPdfium().cargar_pdf(ruta)
    salida = []
    for pag in doc.paginas[paginas[0] - 1:paginas[1]]:
        for i, l in enumerate(pag.lineas):
            if "VENCIMIENTO" in l.texto.upper():
                salida.append({"pagina": pag.numero, "cabecera": l.texto,
                               "valores": pag.lineas[i + 1].texto if i + 1 < len(pag.lineas) else None})
        salida.append({"pagina": pag.numero, "lineas_con_vencimiento_o_importe_de_pago": [
            l.texto for l in pag.lineas if re.search(r"VENC|IMPORTE A PAGAR|GIRO|RECIBO", l.texto.upper())]})
    return salida


def main(supabase: Path, motor: Path, salida: Path) -> None:
    datos = json.loads(supabase.read_text(encoding="utf-8"))
    albaranes = datos["albaranes"]
    motor_2ay = json.loads(motor.read_text(encoding="utf-8"))["documentos"]
    out = {"capturado_supabase": datos.get("capturado_utc")}
    ruta, _ = _localizar(motor_2ay, "08007501")
    out["1_1_08007501"] = diagnostico_filas(albaranes, ruta, "08007501")
    out["1_1_08007501"]["08B96275_en_supabase"] = _en_supabase(albaranes, "08B96275")
    out["1_2_costo_televenta"] = [diagnostico_filas(albaranes, _localizar(motor_2ay, n)[0], n, {"COSTO TELEVENTA"})
                                  for n in ("08006570", "08007501")]
    out["1_3_08011733"] = diagnostico_08011733(albaranes, _localizar(motor_2ay, "08011733")[0])
    out["1_4_vencimientos"] = {n: vencimientos_literales(*_localizar(motor_2ay, n)) for n in ("08011733", "08007971")}
    salida.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "1_3_08011733"}, ensure_ascii=False, indent=1, default=str))
    r = out["1_3_08011733"]
    print(json.dumps({k: v for k, v in r.items() if k != "lineas"}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), _salida_fuera_del_repo(sys.argv[3]))
