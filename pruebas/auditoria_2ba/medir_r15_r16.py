"""Hito 2BA: medicion previa (sin tocar codigo) del efecto de R15 y R16 sobre el banco 2AY.

Uso:
  python -B pruebas/auditoria_2ba/medir_r15_r16.py <motor_banco.json> <supabase.json> <snapshot_2azd.json> <salida.json>

No se conecta a nada. Parte de las facturas Alliance autorizables del banco (motor
con el codigo vigente), de los albaranes de un volcado READ_ONLY y de las
conciliaciones vigentes de produccion (snapshot READ_ONLY del 2AZ-D).

- Base: reglas vigentes (D11 + R11; elegibilidad con 0,05 fija).
- R16: elegibilidad con max(0,05; min(0,01 x lineas sumadas; 0,50)).
- R15 (+R16): las facturas aptas se concilian en el orden del selector (fecha,
  numero); un albaran (farmacia, IdContador) solo justifica una linea de una
  conciliacion vigente. Ocupados de partida: los de las conciliaciones vigentes de
  produccion de OTRAS facturas. Una linea cuyo unico candidato esta ocupado queda
  sin casar con motivo ALBARAN_YA_CONCILIADO.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ay"))

from analisis_2ay import candidatos_operacionales, elegibilidad, simular_conciliacion  # noqa: E402
from src.facturas.runtime_supabase.conciliacion import (  # noqa: E402
    VENTANA_FECHA_DIAS, AlbaranDocumentalTrabajo, MovimientoDocumentalTrabajo, ReglaTolerancia,
    buscar_candidato_albaran, conciliar_importes, construir_detalles_movimientos_documentales, detalle_desde_busqueda)

REGLA = ReglaTolerancia()
FOCO = ("08007969", "08006568", "08008427", "08008430")
PRIORIDAD_EXACTA = False


def lineas_sumadas(f: dict) -> int:
    return sum(1 for a in f.get("albaranes", []) if a.get("importe_total") is not None) + len(f.get("movimientos", []))


def elegibilidad_r16(f: dict) -> tuple[str, str]:
    return elegibilidad(f, REGLA.para(lineas_sumadas(f)))


def _clave(c) -> tuple[str, int]:
    return (c.farmacia, c.id_contador)


def simular_exclusivo(f: dict, operacionales, ocupados_otras: set) -> dict:
    """Como simular_conciliacion (2AY) pero con exclusividad R15 entre facturas y entre lineas."""
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
            return {"camino": "FALLO", "codigo": "TRAZABILIDAD_SERVICIO_INSUFICIENTE"}
        detalles.extend(md)
    docs = [AlbaranDocumentalTrabajo(f"a{i}", a.get("numero"), date.fromisoformat(a["fecha"]) if a.get("fecha") else None,
                                     Decimal(str(a["importe_total"])) if a.get("importe_total") is not None else None,
                                     a.get("sentido"))
            for i, a in enumerate(f.get("albaranes", []), 1)] if naturaleza in {"MERCANCIA", "MIXTA"} else []
    fechas = [d.fecha for d in docs if d.fecha]
    ventana = []
    if fechas:
        ini, fin = min(fechas) - timedelta(days=VENTANA_FECHA_DIAS), max(fechas) + timedelta(days=VENTANA_FECHA_DIAS)
        ventana = [c for c in operacionales if ini <= c.fecha <= fin]
    propios: set = set()
    motivos = Counter()
    bloqueos: list = []
    coincidencias: dict = {}
    for d in docs:
        ocupados = ocupados_otras | propios
        libres = [c for c in ventana if _clave(c) not in ocupados]
        r = buscar_candidato_albaran(d, libres, proveedor_literal=f.get("proveedor_nombre"))
        if r.candidato is None:
            todos = buscar_candidato_albaran(d, ventana, proveedor_literal=f.get("proveedor_nombre"))
            if todos.candidato is not None and _clave(todos.candidato) in ocupados:
                motivos["ALBARAN_YA_CONCILIADO"] += 1
                bloqueos.append({"linea": d.numero, "albaran": todos.candidato.numero_albaran,
                                 "id_contador": todos.candidato.id_contador,
                                 "coincidencia_propia": todos.coincidencia_numero,
                                 "propio_de_esta_factura": _clave(todos.candidato) in propios})
        motivos[r.estado] += 1
        if r.candidato is not None:
            propios.add(_clave(r.candidato))
            coincidencias[_clave(r.candidato)] = [d.numero, r.coincidencia_numero]
        detalles.append(detalle_desde_busqueda(d, r))
    resultado = conciliar_importes(Decimal(str(f["total"])), detalles, regla=REGLA)
    return {"camino": "PERSISTIR", "resultado": resultado.resultado, "diferencia": str(resultado.diferencia),
            "tolerancia": str(resultado.tolerancia), "casados": resultado.albaranes_casados, "matching": dict(motivos),
            "reservados": sorted(propios), "bloqueos": bloqueos,
            "coincidencias": {f"{k[0]}:{k[1]}": v for k, v in coincidencias.items()}}


def main(motor: Path, supabase: Path, snapshot: Path, salida: Path) -> None:
    docs = json.loads(motor.read_text(encoding="utf-8"))["documentos"]
    operacionales = candidatos_operacionales(json.loads(supabase.read_text(encoding="utf-8"))["albaranes"])
    auditoria = json.loads(snapshot.read_text(encoding="utf-8"))["auditoria_conciliaciones"]["detalles"]
    vigentes_prod: dict = {}
    for d in auditoria:
        if d["es_actual"] and d["tipo_relacion"] == "UNO_A_UNO" and d["albaran_id_contador"] is not None:
            vigentes_prod[(d["albaran_farmacia"], int(d["albaran_id_contador"]))] = d["numero_factura"]
    facturas = [f for d in docs for f in (d.get("oficial") or {}).get("facturas_normalizadas") or [] if f.get("autorizable")]
    filas = []
    for f in facturas:
        base_el = elegibilidad(f)
        base_sim = simular_conciliacion(f, operacionales) if base_el[0] == "APTA" else None
        filas.append({"numero": f["numero"], "fecha": f.get("fecha"), "lineas": lineas_sumadas(f),
                      "tolerancia_r16": str(REGLA.para(lineas_sumadas(f))),
                      "base": {"elegibilidad": base_el, "resultado": None if base_sim is None else (
                          "CONCILIADA" if abs(Decimal(base_sim["diferencia"])) <= REGLA.para(base_sim["albaranes_casados"])
                          else "DIFERENCIA"), "diferencia": None if base_sim is None else base_sim["diferencia"],
                          "casados": None if base_sim is None else base_sim["albaranes_casados"]},
                      "r16_elegibilidad": elegibilidad_r16(f), "_f": f})
    # Variante (solo medicion): los albaranes casados por numero EXACTO quedan reservados de
    # antemano para su factura, de modo que otra factura no los tome por PUC con numero distinto.
    exactos: dict = {}
    if PRIORIDAD_EXACTA:
        for fila in filas:
            if fila["r16_elegibilidad"][0] == "APTA":
                libre = simular_exclusivo(fila["_f"], operacionales, set())
                for k, (_, coinc) in libre.get("coincidencias", {}).items():
                    far, idc = k.split(":")
                    if coinc == "EXACTA":
                        exactos.setdefault((far, int(idc)), fila["numero"])
    # R15 + R16: orden del selector (fecha, numero), ocupacion progresiva.
    ocupados_globales = {k: v for k, v in vigentes_prod.items()}
    for fila in sorted(filas, key=lambda x: (x["fecha"] or "9999", x["numero"])):
        if fila["r16_elegibilidad"][0] != "APTA":
            fila["r15_r16"] = {"resultado": f"NO_APTA:{fila['r16_elegibilidad'][1]}"}
            continue
        otras = {k for k, v in ocupados_globales.items() if v != fila["numero"]}
        otras |= {k for k, v in exactos.items() if v != fila["numero"] and k not in vigentes_prod}
        sim = simular_exclusivo(fila["_f"], operacionales, otras)
        fila["r15_r16"] = sim
        for k in sim.get("reservados", []):
            ocupados_globales[tuple(k)] = fila["numero"]
    cambios = []
    for fila in filas:
        b, n = fila["base"], fila["r15_r16"]
        base_estado = b["resultado"] or f"NO_APTA:{b['elegibilidad'][1]}"
        nuevo_estado = n.get("resultado")
        if (base_estado, b.get("diferencia"), b.get("casados")) != (nuevo_estado, n.get("diferencia"), n.get("casados")):
            cambios.append({"numero": fila["numero"], "antes": [base_estado, b.get("diferencia"), b.get("casados")],
                            "despues": [nuevo_estado, n.get("diferencia"), n.get("casados")],
                            "ya_conciliado": (n.get("matching") or {}).get("ALBARAN_YA_CONCILIADO", 0),
                            "lineas": fila["lineas"], "tolerancia_r16": fila["tolerancia_r16"]})
        fila.pop("_f")
    resumen = {
        "facturas": len(filas),
        "aptas_base": sum(1 for x in filas if x["base"]["elegibilidad"][0] == "APTA"),
        "aptas_r16": sum(1 for x in filas if x["r16_elegibilidad"][0] == "APTA"),
        "conciliadas_base": sum(1 for x in filas if x["base"]["resultado"] == "CONCILIADA"),
        "conciliadas_r15_r16": sum(1 for x in filas if x["r15_r16"].get("resultado") == "CONCILIADA"),
        "lineas_albaran_ya_conciliado": sum((x["r15_r16"].get("matching") or {}).get("ALBARAN_YA_CONCILIADO", 0) for x in filas),
        "foco": {x["numero"]: {"base": x["base"], "r16": x["r16_elegibilidad"], "r15_r16": {k: v for k, v in x["r15_r16"].items()
                                                                                         if k != "reservados"}}
                 for x in filas if x["numero"] in FOCO},
        "ocupados_produccion_de_partida": len(vigentes_prod),
    }
    salida.write_text(json.dumps({"resumen": resumen, "cambios": cambios, "filas": filas}, ensure_ascii=False, indent=1,
                                 default=str), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    for c in cambios:
        print(json.dumps(c, ensure_ascii=False))


if __name__ == "__main__":
    PRIORIDAD_EXACTA = "--prioridad-exacta" in sys.argv
    main(*(Path(a) for a in sys.argv[1:5]))
