"""Hito 2BA: medicion (sin tocar codigo) de R15 + R15b + R15c + R16 sobre el banco 2AY.

Uso:
  python -B pruebas/auditoria_2ba/medir_r15b.py <motor_banco.json> <supabase.json> <lectura_r15.json> <salida.json>

Reglas medidas (decision Pio 2BA):
- R15: exclusividad; prioridad al numero exacto (una linea no toma por PUC un albaran
  cuyo numero es exactamente el de una linea documental de OTRA factura extraida; dentro
  de la factura se casan primero las lineas con numero exacto).
- R15b: con numero distinto solo casa si el numero Farmatic es interno (Q039904/2026);
  si tiene formato de proveedor (Alliance: 08 + letra + digitos) -> NUMERO_PROVEEDOR_DISTINTO.
- R15c: numero exacto +-15 dias; PUC con numero distinto +-3 dias.
- R16: elegibilidad proporcional.
Decisiones Pio (2BA, segunda ronda), tratadas como coincidencia de numero (+-15 dias):
 1. Alliance + 1 letra final sobre el mismo numero (08C52171A = 08C52171).
 2. Numero Farmatic de >= 8 digitos que es el final del documental (9319977575 -> 19977575).
 3. SAFA de 12 digitos: nunca casa por importe (falla cerrado).
 4. Numero interno Farmatic: [A-Z]\\d{6}/\\d{4}.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ay"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from analisis_2ay import candidatos_operacionales, elegibilidad, simular_conciliacion  # noqa: E402
from medir_r15_r16 import REGLA, elegibilidad_r16, lineas_sumadas  # noqa: E402
from src.facturas.runtime_supabase.conciliacion import (  # noqa: E402
    PROVEEDOR_CANONICO_ALLIANCE, AlbaranDocumentalTrabajo, MovimientoDocumentalTrabajo, buscar_candidato_albaran,
    canonicalizar_proveedor, comparar_numeros_albaran, conciliar_importes,
    construir_detalles_movimientos_documentales, detalle_desde_busqueda, normalizar_numero_albaran)

FOCO = ("08007969", "08006568", "08008427", "08008430")
INTERNO = re.compile(r"^[A-Z]\d{6}/\d{4}$")
ALLIANCE = re.compile(r"^08[A-Z]\d{5}$")
ALLIANCE_SUFIJO = re.compile(r"^(08[A-Z]\d{5})[A-Z]$")
VENTANA_EXACTA, VENTANA_PUC = 15, 3
EXACTA_SOBRE_SUFIJO = False


def _clave(c) -> tuple[str, int]:
    return (c.farmacia, c.id_contador)


def coincide_sufijo(documental: str | None, farmatic: str | None) -> bool:
    m = ALLIANCE_SUFIJO.match((farmatic or "").strip().upper())
    return bool(m) and normalizar_numero_albaran(documental) == m.group(1)


def coincide_final(documental: str | None, farmatic: str | None) -> bool:
    doc, far = normalizar_numero_albaran(documental), normalizar_numero_albaran(farmatic)
    return bool(doc and far) and far.isdigit() and len(far) >= 8 and len(doc) > len(far) and doc.endswith(far)


def clase_numero(d, c, alliance: bool, modo: str = "decision") -> str:
    """EXACTA | SUFIJO | FINAL | INTERNO | PROVEEDOR | LIBRE (proveedor sin patron)."""
    if _comparar_original(d.numero, c.numero_albaran) == "EXACTA":
        return "EXACTA"
    if alliance and coincide_sufijo(d.numero, c.numero_albaran):
        return "SUFIJO"
    if coincide_final(d.numero, c.numero_albaran):
        return "FINAL"
    if INTERNO.match((c.numero_albaran or "").strip().upper()):
        return "INTERNO"
    if alliance:
        return "PROVEEDOR"  # 08+letra+digitos distinto, SAFA de 12 digitos u otro: falla cerrado
    return "LIBRE"


# La busqueda de src solo prefiere (y admite PVP) con numero EXACTA: para medir, las
# coincidencias 1 y 2 se presentan como EXACTA. No se modifica src.
import src.facturas.runtime_supabase.conciliacion as _modulo  # noqa: E402

_comparar_original = _modulo.comparar_numeros_albaran
_ALLIANCE_ACTUAL = {"valor": False}


def _comparar_decision(documental, operacional):
    base = _comparar_original(documental, operacional)
    if base == "DIFERENTE" and ((_ALLIANCE_ACTUAL["valor"] and coincide_sufijo(documental, operacional))
                                or coincide_final(documental, operacional)):
        return "EXACTA"
    return base


_modulo.comparar_numeros_albaran = _comparar_decision


def simular(f: dict, operacionales, ocupados_otras: set, numeros_otras: set, modo: str) -> dict:
    naturaleza = f.get("naturaleza_principal")
    alliance = canonicalizar_proveedor(f.get("proveedor_nombre")) == PROVEEDOR_CANONICO_ALLIANCE
    _ALLIANCE_ACTUAL["valor"] = alliance
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

    def admisibles(d, ocupados, aplicar_r15b=True, aplicar_ocupacion=True):
        if d.fecha is None:
            return []
        out = []
        for c in operacionales:
            dias = abs((c.fecha - d.fecha).days)
            if dias > VENTANA_EXACTA or (aplicar_ocupacion and _clave(c) in ocupados):
                continue
            clase = clase_numero(d, c, alliance, modo)
            if clase in ("EXACTA", "SUFIJO", "FINAL"):
                out.append(c)
                continue
            if dias > VENTANA_PUC or normalizar_numero_albaran(c.numero_albaran) in numeros_otras:
                continue
            if aplicar_r15b and clase == "PROVEEDOR":
                continue
            out.append(c)
        if EXACTA_SOBRE_SUFIJO and any(clase_numero(d, c, alliance, modo) == "EXACTA" for c in out):
            out = [c for c in out if clase_numero(d, c, alliance, modo) not in ("SUFIJO", "FINAL")]
        return out

    # Dentro de la factura, primero las lineas que tienen algun candidato con numero exacto.
    def tiene_exacto(d):
        return any(clase_numero(d, c, alliance, modo) in ("EXACTA", "SUFIJO", "FINAL") for c in admisibles(d, set()))
    orden = sorted(range(len(docs)), key=lambda i: (not tiene_exacto(docs[i]), i))
    propios: set = set()
    motivos, pares, bloqueos = Counter(), [], []
    detalle_por_indice = {}
    for i in orden:
        d = docs[i]
        ocupados = ocupados_otras | propios
        r = buscar_candidato_albaran(d, admisibles(d, ocupados), proveedor_literal=f.get("proveedor_nombre"),
                                     ventana_dias=VENTANA_EXACTA)
        estado = r.estado
        if r.candidato is None:
            sin_ocup = buscar_candidato_albaran(d, admisibles(d, ocupados, aplicar_ocupacion=False),
                                                proveedor_literal=f.get("proveedor_nombre"), ventana_dias=VENTANA_EXACTA)
            sin_r15b = buscar_candidato_albaran(d, admisibles(d, ocupados, aplicar_r15b=False),
                                                proveedor_literal=f.get("proveedor_nombre"), ventana_dias=VENTANA_EXACTA)
            if sin_ocup.candidato is not None and _clave(sin_ocup.candidato) in ocupados:
                estado = "ALBARAN_YA_CONCILIADO"
                bloqueos.append([d.numero, sin_ocup.candidato.numero_albaran, _clave(sin_ocup.candidato) in propios])
            elif sin_r15b.candidato is not None:
                estado = "NUMERO_PROVEEDOR_DISTINTO"
                bloqueos.append([d.numero, sin_r15b.candidato.numero_albaran, "R15b"])
        motivos[estado] += 1
        if r.candidato is not None:
            propios.add(_clave(r.candidato))
            pares.append([d.numero, r.candidato.numero_albaran, clase_numero(d, r.candidato, alliance, modo),
                          (r.candidato.fecha - d.fecha).days])
        detalle_por_indice[i] = detalle_desde_busqueda(d, r)
    detalles.extend(detalle_por_indice[i] for i in range(len(docs)))
    resultado = conciliar_importes(Decimal(str(f["total"])), detalles, regla=REGLA)
    return {"resultado": resultado.resultado, "diferencia": str(resultado.diferencia), "casados": resultado.albaranes_casados,
            "matching": dict(motivos), "reservados": sorted(propios), "bloqueos": bloqueos,
            "no_exactos": [p for p in pares if p[2] != "EXACTA"]}


def correr(facturas, operacionales, vigentes_prod, modo):
    numeros = {f["numero"]: {normalizar_numero_albaran(a.get("numero")) for a in f.get("albaranes", [])} - {None}
               for f in facturas}
    ocupados = dict(vigentes_prod)
    out = {}
    for f in sorted(facturas, key=lambda x: (x.get("fecha") or "9999", x["numero"])):
        el = elegibilidad_r16(f)
        if el[0] != "APTA":
            out[f["numero"]] = {"resultado": f"NO_APTA:{el[1]}"}
            continue
        otras = {k for k, v in ocupados.items() if v != f["numero"]}
        numeros_otras = set().union(*(v for k, v in numeros.items() if k != f["numero"]))
        s = simular(f, operacionales, otras, numeros_otras, modo)
        out[f["numero"]] = s
        for k in s.get("reservados", []):
            ocupados[tuple(k)] = f["numero"]
    return out


def main(motor: Path, supabase: Path, lectura: Path, salida: Path) -> None:
    docs = json.loads(motor.read_text(encoding="utf-8"))["documentos"]
    operacionales = candidatos_operacionales(json.loads(supabase.read_text(encoding="utf-8"))["albaranes"])
    vigentes_prod = {(d["albaran_farmacia"], int(d["albaran_id_contador"])): d["numero_factura"]
                     for d in json.loads(lectura.read_text(encoding="utf-8"))["detalles"]
                     if d["es_actual"] and d["tipo_relacion"] == "UNO_A_UNO" and d["albaran_id_contador"] is not None}
    facturas = [f for d in docs for f in (d.get("oficial") or {}).get("facturas_normalizadas") or [] if f.get("autorizable")]
    base = {}
    for f in facturas:
        el = elegibilidad(f)
        s = simular_conciliacion(f, operacionales) if el[0] == "APTA" else None
        base[f["numero"]] = ({"resultado": f"NO_APTA:{el[1]}"} if s is None else {
            "resultado": "CONCILIADA" if abs(Decimal(s["diferencia"])) <= REGLA.para(s["albaranes_casados"]) else "DIFERENCIA",
            "diferencia": s["diferencia"], "casados": s["albaranes_casados"]})
    variantes = {"decision": correr(facturas, operacionales, vigentes_prod, "decision")}
    resumen = {"facturas": len(facturas),
               "aptas_base": sum(1 for v in base.values() if not v["resultado"].startswith("NO_APTA")),
               "conciliadas_base": sum(1 for v in base.values() if v["resultado"] == "CONCILIADA")}
    for m, r in variantes.items():
        resumen[m] = {"aptas": sum(1 for v in r.values() if not v["resultado"].startswith("NO_APTA")),
                      "conciliadas": sum(1 for v in r.values() if v["resultado"] == "CONCILIADA"),
                      "motivos": dict(sum((Counter(v.get("matching") or {}) for v in r.values()), Counter())),
                      "no_exactos_casados": Counter(p[2] for v in r.values() for p in v.get("no_exactos", [])),
                      "dias_no_exactos": Counter(abs(p[3]) for v in r.values() for p in v.get("no_exactos", []))}
    cambios = []
    for n in sorted(base):
        fila = {"numero": n, "base": [base[n]["resultado"], base[n].get("diferencia"), base[n].get("casados")]}
        for m, r in variantes.items():
            fila[m] = [r[n]["resultado"], r[n].get("diferencia"), r[n].get("casados"),
                       {k: v for k, v in (r[n].get("matching") or {}).items() if k not in ("MATCH_UNICO",)}]
        if fila["base"][0] != fila["decision"][0] or n in FOCO:
            cambios.append(fila)
    salida.write_text(json.dumps({"resumen": resumen, "cambios": cambios, "base": base, "variantes": variantes},
                                 ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=1, default=str))
    for c in cambios:
        print(json.dumps(c, ensure_ascii=False))


if __name__ == "__main__":
    # Variante informativa: con un candidato de numero exacto, las coincidencias 1 y 2 no compiten.
    EXACTA_SOBRE_SUFIJO = "--exacta-sobre-sufijo" in sys.argv
    main(*(Path(a) for a in sys.argv[1:5]))
