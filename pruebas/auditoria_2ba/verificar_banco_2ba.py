"""Hito 2BA: el codigo de src (R15 + R15b + R15c + R16 + decisiones de Pio) reproduce la medicion.

Uso:
  python -B pruebas/auditoria_2ba/verificar_banco_2ba.py <motor_banco.json> <supabase.json> <lectura_r15.json> \
      <medicion_aprobada.json> <salida.json>

Concilia las facturas Alliance autorizables del banco 2AY en el orden del selector
(fecha, numero) con ``buscar_albaranes_factura`` de src, partiendo de los albaranes
ocupados por las conciliaciones vigentes de produccion (lectura READ_ONLY), y compara
resultado, diferencia y casados con la medicion aprobada por Pio
(``medicion_r15b_exacta_sobre_sufijo.json``). Sale con codigo 1 ante cualquier diferencia.
No se conecta a nada.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ay"))

from analisis_2ay import candidatos_operacionales, elegibilidad  # noqa: E402
from src.facturas.runtime_supabase.conciliacion import (  # noqa: E402
    AlbaranDocumentalTrabajo, MovimientoDocumentalTrabajo, ReglaTolerancia, buscar_albaranes_factura,
    conciliar_importes, construir_detalles_movimientos_documentales, detalle_desde_busqueda)

REGLA = ReglaTolerancia()


def lineas_sumadas(f: dict) -> int:
    return sum(1 for a in f.get("albaranes", []) if a.get("importe_total") is not None) + len(f.get("movimientos", []))


def conciliar(f: dict, operacionales, ocupados: set, numeros_otras: set) -> dict:
    naturaleza = f.get("naturaleza_principal")
    detalles = []
    if naturaleza in {"SERVICIOS", "MIXTA"}:
        movs = [MovimientoDocumentalTrabajo(id=f"m{i}", concepto_literal=str(m.get("descripcion")), tipo=str(m.get("tipo")),
                                            sentido=m.get("sentido"),
                                            importe=Decimal(str(m["importe"])) if m.get("importe") is not None else None,
                                            base=Decimal(str(m["base"])) if m.get("base") is not None else None)
                for i, m in enumerate(f.get("movimientos", []), 1)]
        md = construir_detalles_movimientos_documentales(movs)
        if md is None:
            return {"resultado": "FALLO:TRAZABILIDAD_SERVICIO_INSUFICIENTE"}
        detalles.extend(md)
    docs = [AlbaranDocumentalTrabajo(f"a{i}", a.get("numero"), date.fromisoformat(a["fecha"]) if a.get("fecha") else None,
                                     Decimal(str(a["importe_total"])) if a.get("importe_total") is not None else None,
                                     a.get("sentido"))
            for i, a in enumerate(f.get("albaranes", []), 1)] if naturaleza in {"MERCANCIA", "MIXTA"} else []
    resultados = buscar_albaranes_factura(docs, operacionales, proveedor_literal=f.get("proveedor_nombre"),
                                          ocupados=ocupados, numeros_otras_facturas=numeros_otras)
    detalles.extend(detalle_desde_busqueda(d, r) for d, r in zip(docs, resultados))
    r = conciliar_importes(Decimal(str(f["total"])), detalles, regla=REGLA)
    reservados = [(x.candidato.farmacia, x.candidato.id_contador) for x in resultados
                  if x.candidato is not None and x.importe_compatible is not None]
    motivos: dict = {}
    for x in resultados:
        motivos[x.estado] = motivos.get(x.estado, 0) + 1
    return {"resultado": r.resultado, "diferencia": str(r.diferencia), "casados": r.albaranes_casados,
            "matching": motivos, "reservados": reservados}


def main(motor: Path, supabase: Path, lectura: Path, aprobada: Path, salida: Path) -> int:
    docs = json.loads(motor.read_text(encoding="utf-8"))["documentos"]
    operacionales = candidatos_operacionales(json.loads(supabase.read_text(encoding="utf-8"))["albaranes"])
    vigentes = {(d["albaran_farmacia"], int(d["albaran_id_contador"])): d["numero_factura"]
                for d in json.loads(lectura.read_text(encoding="utf-8"))["detalles"]
                if d["es_actual"] and d["albaran_id_contador"] is not None}
    esperado = json.loads(aprobada.read_text(encoding="utf-8"))["variantes"]["decision"]
    facturas = [f for d in docs for f in (d.get("oficial") or {}).get("facturas_normalizadas") or [] if f.get("autorizable")]
    numeros = {f["numero"]: {a.get("numero") for a in f.get("albaranes", []) if a.get("numero")} for f in facturas}
    ocupados = dict(vigentes)
    obtenido = {}
    for f in sorted(facturas, key=lambda x: (x.get("fecha") or "9999", x["numero"])):
        el = elegibilidad(f, REGLA.para(lineas_sumadas(f)))
        if el[0] != "APTA":
            obtenido[f["numero"]] = {"resultado": f"NO_APTA:{el[1]}"}
            continue
        otras = {k for k, v in ocupados.items() if v != f["numero"]}
        numeros_otras = set().union(*(v for k, v in numeros.items() if k != f["numero"]))
        s = conciliar(f, operacionales, otras, numeros_otras)
        obtenido[f["numero"]] = s
        for k in s.get("reservados", []):
            ocupados[k] = f["numero"]
    diferencias = []
    for n, e in esperado.items():
        o = obtenido[n]
        clave_e = (e["resultado"], e.get("diferencia"), e.get("casados"))
        clave_o = (o["resultado"], o.get("diferencia"), o.get("casados"))
        if clave_e != clave_o:
            diferencias.append({"numero": n, "aprobado": clave_e, "src": clave_o})
    resumen = {"facturas": len(obtenido),
               "aptas": sum(1 for v in obtenido.values() if not v["resultado"].startswith("NO_APTA")),
               "conciliadas": sorted(n for n, v in obtenido.items() if v["resultado"] == "CONCILIADA"),
               "diferencias_con_medicion_aprobada": diferencias}
    salida.write_text(json.dumps({"resumen": resumen, "obtenido": obtenido}, ensure_ascii=False, indent=1, default=str),
                      encoding="utf-8")
    print(json.dumps({**resumen, "conciliadas": len(resumen["conciliadas"])}, ensure_ascii=False, indent=1, default=str))
    return 1 if diferencias else 0


if __name__ == "__main__":
    sys.exit(main(*(Path(a) for a in sys.argv[1:6])))
