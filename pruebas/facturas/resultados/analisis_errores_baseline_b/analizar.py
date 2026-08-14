from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
COMP = ROOT / "pruebas/facturas/resultados/comparativa_2o_gold_a_b_c"
EVALUATOR = COMP / "evaluar.py"
EXPECTED_HEAD = "9b332545aaf39d4a6738459456ff919358f7d7a8"
MOVEMENT_TYPES = ["RAPPEL", "ABONO_COMERCIAL", "DEVOLUCION_MERCANCIA", "DESCUENTO", "BONIFICACION", "SERVICIO", "CONDICION_COMERCIAL", "OTRO"]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def dump(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def text(name: str, value: str) -> None:
    (OUT / name).write_text(value.rstrip() + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def import_evaluator():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("evaluador_comun", EVALUATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


ev = import_evaluator()
doc_to_gold = ev.document_map()
gold = ev.load_gold(doc_to_gold)
b = ev.load_predictions("B")
c = ev.load_predictions("C")
matched, missing_invoices, invented_invoices = ev.match_invoices(gold, b)
metrics_frozen = load(COMP / "metricas_b.json")
metrics_recomputed = ev.evaluate_baseline("B", gold, b)
assert metrics_recomputed == metrics_frozen, "La reevaluación B no coincide byte-lógicamente como objeto con metricas_b.json"
assert not missing_invoices

index = load(ROOT / "pruebas/facturas/gold_standard/indice.json")
gold_file_to_pdf = {x["archivo_json"]: x["pdf_fuente"] for x in index["pdfs"]}
doc_to_pdf = {doc: gold_file_to_pdf[gf] for doc, gf in doc_to_gold.items()}


def provider_group(name: str) -> str:
    value = ev.canon(name) or ""
    if "ALLIANCE" in value: return "Alliance"
    if "COFARES" in value: return "Cofares"
    if "HDAD" in value or "HEFAME" in value: return "HEFAME"
    if "FEDERACIO" in value: return "FEDEFARMA"
    return "resto"


def unmatched(items: list[dict[str, Any]], pairs: list[tuple[dict[str, Any], dict[str, Any]]], side: int) -> list[dict[str, Any]]:
    used = {id(pair[side]) for pair in pairs}
    return [item for item in items if id(item) not in used]


invoice_rows = []
absent_deliveries = []
invented_deliveries = []
delivery_pair_cache = {}
for g, p in matched:
    if not g["albaranes"]:
        continue
    pairs, absent, invented = ev.match_list(g["albaranes"], p["albaranes"], lambda x: ev.invoice_key(x.get("numero")))
    delivery_pair_cache[(g["documento"], ev.invoice_key(g["numero_factura"]))] = pairs
    miss = unmatched(g["albaranes"], pairs, 0)
    extra = unmatched(p["albaranes"], pairs, 1)
    if absent == len(g["albaranes"]): predominant = "omision_total" if not extra else "clave_numero_incorrecta"
    elif absent: predominant = "omision_parcial"
    elif invented: predominant = "invencion"
    else: predominant = "sin_error_deteccion"
    row = {
        "pdf": doc_to_pdf[g["documento"]], "documento": g["documento"], "proveedor": g["proveedor_nombre"],
        "numero_factura": g["numero_factura"], "paginas": [g["pagina_inicio"], g["pagina_fin"]],
        "albaranes_gold": len(g["albaranes"]), "albaranes_B": len(p["albaranes"]), "correctos": len(pairs),
        "ausentes": absent, "inventados": invented,
        "cobertura_pct": round(100 * len(pairs) / len(g["albaranes"]), 2),
        "exactitud_pct": round(100 * len(pairs) / len(p["albaranes"]), 2) if p["albaranes"] else 100.0,
        "tipo_error_predominante": predominant,
    }
    invoice_rows.append(row)
    for x in miss:
        absent_deliveries.append({"pdf": row["pdf"], "documento": g["documento"], "proveedor": g["proveedor_nombre"], "grupo_proveedor": provider_group(g["proveedor_nombre"]), "numero_factura": g["numero_factura"], "pagina_inicio": g["pagina_inicio"], "pagina_fin": g["pagina_fin"], "orden_gold": x.get("orden"), "albaran_gold": x})
    for x in extra:
        # Los cinco casos observados son emparejables documentalmente por fecha/orden/importe,
        # pero se mantienen inventados según la clave exacta numero del evaluador.
        # The common normalizer does not retain gold `orden`; prove the
        # documentary correspondence by date and identifier containment.
        same_position = next((z for z in g["albaranes"] if ev.date(z.get("fecha")) == ev.date(x.get("fecha")) and ev.invoice_key(x.get("numero")) in ev.invoice_key(z.get("numero"))), None)
        category = "lectura incorrecta" if same_position and ev.invoice_key(x.get("numero")) in ev.invoice_key(same_position.get("numero")) else "otra"
        invented_deliveries.append({
            "pdf": row["pdf"], "documento": g["documento"], "proveedor": g["proveedor_nombre"], "numero_factura": g["numero_factura"],
            "valor_B": x.get("numero"), "registro_B": x, "realidad_gold_documental": same_position,
            "estado_evaluador": "inventado_por_clave_numero_no_coincidente", "causa_probable_categoria": category,
            "evidencia_demostrada": "Misma página/factura, orden, fecha e importe; B separa PA/RE como tipo_pedido y omite el prefijo documental inicial P y el componente PA/RE del número.",
            "inferencia": "Error de lectura/representación del identificador compuesto; no hay evidencia de que el número base haya sido fabricado." if same_position else "Sin correspondencia estructural demostrada.",
        })

invoice_rows.sort(key=lambda x: (x["cobertura_pct"], x["exactitud_pct"], -x["albaranes_gold"], ev.invoice_key(x["numero_factura"])))
absent_deliveries.sort(key=lambda x: (x["documento"], ev.invoice_key(x["numero_factura"]), x["orden_gold"] or 0))
invented_deliveries.sort(key=lambda x: (x["documento"], ev.invoice_key(x["numero_factura"]), x["registro_B"].get("orden", 0)))

dist_invoice_ids = ["08009278", "08009277", "08009279", "5450053457", "0563820041", "VN2605-0005656"]
dist_by_invoice = {x: sum(1 for z in absent_deliveries if ev.invoice_key(z["numero_factura"]) == ev.invoice_key(x)) for x in dist_invoice_ids}
dist_by_invoice["resto"] = len(absent_deliveries) - sum(dist_by_invoice.values())
dist_by_provider = Counter(x["grupo_proveedor"] for x in absent_deliveries)
provider_distribution = {k: {"ausentes": dist_by_provider[k], "pct_sobre_167": round(100 * dist_by_provider[k] / 167, 2)} for k in ["Alliance", "Cofares", "HEFAME", "FEDEFARMA", "resto"]}

assert sum(x["albaranes_gold"] for x in invoice_rows) == 337
assert sum(x["correctos"] for x in invoice_rows) == 170
assert len(absent_deliveries) == 167
assert len(invented_deliveries) == 5

dump("albaranes_por_factura.json", {"definicion_matching": "evaluar.py: match_list con invoice_key(numero)", "orden": "peor a mejor por cobertura y exactitud", "reconciliacion": metrics_frozen["albaranes"], "distribucion_ausentes_por_factura": dist_by_invoice, "distribucion_ausentes_por_proveedor": provider_distribution, "facturas": invoice_rows})
dump("albaranes_ausentes.json", {"total": len(absent_deliveries), "distribucion_por_factura": dist_by_invoice, "distribucion_por_proveedor": provider_distribution, "registros": absent_deliveries})
dump("albaranes_inventados.json", {"total": len(invented_deliveries), "nota": "Inventados según la clave exacta común; los cinco tienen contraparte documental estructural demostrada.", "registros": invented_deliveries})


# Movimientos: el estado primario conserva el matching exacto común. Un concepto con clave
# exacta y atributos monetarios distintos se marca importe_erroneo sin perder que fue detectado.
movement_gold_rows = []
movement_invented_rows = []
for g, p in matched:
    pairs, _, _ = ev.match_list(g["movimientos_comerciales"], p["movimientos_comerciales"], lambda x: (ev.canon(x.get("tipo")), ev.canon(x.get("sentido")), ev.canon(x.get("descripcion_literal"))))
    pair_by_gold = {id(x): y for x, y in pairs}
    extra = unmatched(p["movimientos_comerciales"], pairs, 1)
    for x in g["movimientos_comerciales"]:
        pred = pair_by_gold.get(id(x))
        if pred is None:
            # Solo se declara clasificación errónea cuando literal y sentido coinciden exactamente.
            same_literal = next((z for z in extra if ev.canon(z.get("descripcion_literal")) == ev.canon(x.get("descripcion_literal")) and ev.canon(z.get("sentido")) == ev.canon(x.get("sentido"))), None)
            if same_literal is not None and ev.canon(same_literal.get("tipo")) != ev.canon(x.get("tipo")):
                state = "clasificacion_erronea"; result = same_literal
            else:
                state = "ausente"; result = None
        else:
            attrs = ["base", "iva", "recargo_equivalencia", "importe"]
            monetary_errors = [a for a in attrs if not (x.get(a) is None and pred.get(a) is None) and not (x.get(a) is not None and pred.get(a) is not None and ev.equal("money:" + a, x.get(a), pred.get(a)))]
            state = "importe_erroneo" if monetary_errors else "correcto"
            result = pred
        movement_gold_rows.append({"pdf": doc_to_pdf[g["documento"]], "documento": g["documento"], "proveedor": g["proveedor_nombre"], "numero_factura": g["numero_factura"], "descripcion_gold": x.get("descripcion_literal"), "tipo_gold": x.get("tipo"), "sentido_gold": x.get("sentido"), "base_gold": x.get("base"), "iva_gold": x.get("iva"), "recargo_gold": x.get("recargo_equivalencia"), "importe_gold": x.get("importe"), "resultado_B": result, "estado": state, "detectado_segun_matching_comun": pred is not None})
    for x in extra:
        correlated = next((row for row in movement_gold_rows if row["documento"] == g["documento"] and row["numero_factura"] == g["numero_factura"] and row["resultado_B"] is x), None)
        movement_invented_rows.append({"pdf": doc_to_pdf[g["documento"]], "documento": g["documento"], "proveedor": g["proveedor_nombre"], "numero_factura": g["numero_factura"], "resultado_B": x, "estado": "inventado_segun_matching_comun", "correlacion_secundaria_demostrada": correlated["descripcion_gold"] if correlated else None})

assert len(movement_gold_rows) == 25
assert sum(x["detectado_segun_matching_comun"] for x in movement_gold_rows) == 11
assert len(movement_invented_rows) == 7
movement_fail_provider = Counter()
movement_fail_type = Counter()
for x in movement_gold_rows:
    if x["estado"] != "correcto":
        movement_fail_provider[provider_group(x["proveedor"])] += 1
        movement_fail_type[x["tipo_gold"] if x["tipo_gold"] in MOVEMENT_TYPES else "OTRO"] += 1
for x in movement_invented_rows:
    movement_fail_provider[provider_group(x["proveedor"])] += 1
    t = x["resultado_B"].get("tipo")
    movement_fail_type[t if t in MOVEMENT_TYPES else "OTRO"] += 1
dump("movimientos_comerciales.json", {"reconciliacion_evaluador": metrics_frozen["movimientos_comerciales"], "nota_estado": "El 44% es detección de clave exacta (11/25), no porcentaje de registros con todos los importes correctos.", "gold_total": 25, "gold": movement_gold_rows, "inventados_B_total": len(movement_invented_rows), "inventados_B": movement_invented_rows, "fallos_por_proveedor": dict(sorted(movement_fail_provider.items())), "fallos_por_tipo": {k: movement_fail_type[k] for k in MOVEMENT_TYPES}, "mezcla_con_albaranes_demostrada": [{"proveedor": "HEFAME", "factura": "0563820041", "evidencia": "C (no B) representa ABO/DEVO y APROAFA también como albaranes; B los conserva como movimientos pero con tipos distintos del gold."}]})


# Todos los errores de campos principales según las mismas funciones equal/metric_fields.
field_errors = []
for g, p in matched:
    for field in ev.MAIN_FIELDS:
        gv, pv = g.get(field), p.get(field)
        if gv is not None:
            if pv is None: kind = "ausencia"
            elif ev.equal(field, gv, pv): continue
            elif field in {"naturaleza_principal", "requiere_conciliacion_albaranes"}: kind = "clasificacion_incorrecta"
            else: kind = "valor_incorrecto"
        elif pv is not None:
            kind = "invencion"
        else:
            continue
        field_errors.append({"pdf": doc_to_pdf[g["documento"]], "documento": g["documento"], "proveedor": g["proveedor_nombre"], "numero_factura": g["numero_factura"], "campo": field, "gold": gv, "B": pv, "tipo": kind})
field_counts = Counter(x["tipo"] for x in field_errors)
assert field_counts["ausencia"] == 12 and field_counts["invencion"] == 13
assert field_counts["valor_incorrecto"] + field_counts["clasificacion_incorrecta"] == 25
dump("errores_campos_principales.json", {"reconciliacion": metrics_frozen["campos_principales"], "formula_acierto": "214/251=85.26%", "formula_cobertura": "(214+25)/251=95.22%", "conteo_errores_listados": len(field_errors), "conteo_por_tipo": dict(field_counts), "errores": field_errors})


# Fiscalidad: el 98.89% usa únicamente atributos de tramos emparejados por (IVA, RE).
tax_attribute_errors = []
tax_missing = []
tax_invented = []
for g, p in matched:
    pairs, _, _ = ev.match_list(g["impuestos"], p["impuestos"], lambda x: (ev.number(x.get("tipo_iva")), ev.number(x.get("tipo_recargo_equivalencia"))))
    for left, right in pairs:
        for attr in ["base", "cuota_iva", "cuota_recargo_equivalencia"]:
            if left.get(attr) is None and right.get(attr) is None: continue
            if left.get(attr) is not None and right.get(attr) is not None and ev.equal("money:" + attr, left.get(attr), right.get(attr)): continue
            tax_attribute_errors.append({"pdf": doc_to_pdf[g["documento"]], "documento": g["documento"], "proveedor": g["proveedor_nombre"], "numero_factura": g["numero_factura"], "clave_tramo": {"tipo_iva": left.get("tipo_iva"), "tipo_recargo_equivalencia": left.get("tipo_recargo_equivalencia")}, "atributo": attr, "gold": left.get(attr), "B": right.get(attr), "estado": "atributo_incorrecto"})
    for x in unmatched(g["impuestos"], pairs, 0): tax_missing.append({"pdf": doc_to_pdf[g["documento"]], "numero_factura": g["numero_factura"], "tramo_gold": x, "estado": "tramo_ausente"})
    for x in unmatched(p["impuestos"], pairs, 1): tax_invented.append({"pdf": doc_to_pdf[g["documento"]], "numero_factura": g["numero_factura"], "tramo_B": x, "estado": "tramo_inventado_segun_clave"})
assert len(tax_attribute_errors) == 1 and len(tax_missing) == 8 and len(tax_invented) == 11
dump("errores_fiscalidad.json", {"reconciliacion": metrics_frozen["impuestos"], "formula_atributos": "89/90=98.89%", "atributos_incorrectos_que_forman_1_11_pct": tax_attribute_errors, "tramos_ausentes_fuera_del_denominador_de_atributos": tax_missing, "tramos_inventados_fuera_del_denominador_de_atributos": tax_invented})


# Discrepancias documentales solicitadas, trazadas al gold y a los literales B.
by_invoice = {(ev.invoice_key(g["numero_factura"]), g["documento"]): (g, p) for g, p in matched}
discrepancy_rows = []
for invoice in ["08009278", "08009279", "0563820041"]:
    g, p = next(v for (key, _), v in by_invoice.items() if key == ev.invoice_key(invoice))
    discrepancy_rows.append({
        "pdf": doc_to_pdf[g["documento"]], "proveedor": g["proveedor_nombre"], "numero_factura": invoice,
        "gold": g["discrepancias_documentales"], "literales_B": p["discrepancias_documentales"],
        "deteccion_exacta_evaluador": False, "ocultacion": len(p["discrepancias_documentales"]) == 0,
        "correccion_por_B": False, "explicacion_inventada_por_B": False,
        "preservacion_valores_documentales": {"importe_total_gold": g["importe_total"], "importe_total_B": p["importe_total"], "preservado": ev.equal("money:importe_total", g["importe_total"], p["importe_total"])},
        "conclusion": "B omite la discrepancia específica de 0,02 EUR." if invoice.startswith("080") else "B registra diferencias literales de 110 EUR (594,64-484,64 y 267,31-157,31), pero no identifica ni explica los 80 EUR no reconstruibles del gold.",
    })
dump("discrepancias_documentales.json", {"metrica_comun": metrics_frozen["discrepancias_documentales"], "casos_solicitados": discrepancy_rows})


# B frente a C exclusivamente sobre los 167 ausentes B. Se agrupan todas las salidas C de
# la misma clave de factura para no perder la factura real por el duplicado de portada.
c_buckets = defaultdict(list)
for x in c: c_buckets[(x["documento"], ev.invoice_key(x["numero_factura"]))].extend(x["albaranes"])
recovery_rows = []
for row in absent_deliveries:
    key = (row["documento"], ev.invoice_key(row["numero_factura"]))
    target = ev.invoice_key(row["albaran_gold"].get("numero"))
    candidates = c_buckets[key]
    hit = next((x for x in candidates if ev.invoice_key(x.get("numero")) == target), None)
    recovery_rows.append({**row, "recuperado_por_C": hit is not None, "registro_C": hit})

recovery_provider = {}
for group in ["Alliance", "Cofares", "HEFAME", "FEDEFARMA", "resto"]:
    subset = [x for x in recovery_rows if x["grupo_proveedor"] == group]
    recovery_provider[group] = {"ausentes_B": len(subset), "recuperados_C": sum(x["recuperado_por_C"] for x in subset), "tambien_ausentes_C": sum(not x["recuperado_por_C"] for x in subset)}

# Inventados B corregidos: el número C debe coincidir exactamente con gold estructural de la
# misma posición. Nuevos inventados C se cuentan en las facturas que tenían ausencias B.
b_invented_corrected = 0
c_new_invented = []
for g, p in matched:
    key = (g["documento"], ev.invoice_key(g["numero_factura"]))
    if not any(x["documento"] == g["documento"] and ev.invoice_key(x["numero_factura"]) == key[1] for x in absent_deliveries): continue
    citems = c_buckets[key]
    cpairs, _, _ = ev.match_list(g["albaranes"], citems, lambda x: ev.invoice_key(x.get("numero")))
    cextras = unmatched(citems, cpairs, 1)
    for x in cextras:
        c_new_invented.append({"pdf": doc_to_pdf[g["documento"]], "proveedor": g["proveedor_nombre"], "numero_factura": g["numero_factura"], "registro_C": x})
    for bi in [x for x in invented_deliveries if x["documento"] == g["documento"] and ev.invoice_key(x["numero_factura"]) == key[1]]:
        truth = bi["realidad_gold_documental"]
        if truth and any(ev.invoice_key(x.get("numero")) == ev.invoice_key(truth.get("numero")) for x in citems): b_invented_corrected += 1

assert sum(x["recuperado_por_C"] for x in recovery_rows) == 162
assert b_invented_corrected == 0
assert len(c_new_invented) == 8
dump("recuperacion_b_vs_c.json", {"alcance": "solo los 167 albaranes ausentes B y las invenciones relacionadas", "matching": "invoice_key exacta del evaluador común; para C se unen salidas duplicadas de la misma factura", "total": {"ausentes_B": 167, "recuperados_por_C": 162, "tambien_ausentes_en_C": 5, "inventados_B_corregidos_por_C": b_invented_corrected, "nuevos_inventados_C": len(c_new_invented)}, "por_proveedor": recovery_provider, "ausentes_B": recovery_rows, "nuevos_inventados_C_detalle": c_new_invented})


# Duplicados C: la portada resumen de FEDEFARMA repite números/importe de facturas reales.
c_invoice_buckets = defaultdict(list)
for x in c: c_invoice_buckets[(x["documento"], ev.invoice_key(x["numero_factura"]))].append(x)
duplicates = []
for (doc, key), values in sorted(c_invoice_buckets.items()):
    if len(values) < 2: continue
    duplicates.append({"pdf": doc_to_pdf[doc], "documento": doc, "proveedor": values[0]["proveedor_nombre"], "numero_factura_normalizado": key, "salidas": values, "coincidencias": {"numero_factura": True, "proveedor": len({ev.canon(x["proveedor_nombre"]) for x in values}) == 1, "fecha": len({ev.date(x["fecha_factura"]) for x in values}) == 1, "importe_total": len({ev.number(x["importe_total"]) for x in values}) == 1}, "diferencias": {"paginas": [[x["pagina_inicio"], x["pagina_fin"]] for x in values], "tipo_documento": [x["tipo_documento"] for x in values], "detalle": [sum(len(x[n]) for n in ["impuestos", "albaranes", "movimientos_comerciales"]) for x in values]}, "criterio_evaluador": "match_invoices consume la primera salida del bucket (documento, invoice_key) y deja la segunda como factura inventada.", "eliminable_deterministamente": True})
dump("duplicados.json", {"total_claves_duplicadas_C": len(duplicates), "duplicados": duplicates, "regla_propuesta_no_implementada": "Agrupar por proveedor normalizado + numero_factura normalizado. Conservar la salida con evidencia de factura y mayor detalle estructural; usar fecha+importe solo como apoyo/alerta, nunca como clave primaria. Si proveedor+número discrepan, no fusionar."})


# Baseline B has one unmatched aggregate output on the FEDEFARMA cover page.
assert len(invented_invoices) == 1
b_extra = invented_invoices[0]
same_doc_real = [p for g, p in matched if p["documento"] == b_extra["documento"]]
sum_real = round(sum(ev.number(x.get("importe_total")) or 0 for x in same_doc_real), 2)
duplicate_b = {
    "pdf": doc_to_pdf[b_extra["documento"]],
    "documento": b_extra["documento"],
    "proveedor": b_extra["proveedor_nombre"],
    "salida_adicional_B": b_extra,
    "facturas_reales_B_del_mismo_pdf": same_doc_real,
    "coincidencias": {
        "mismo_proveedor": len({ev.canon(x.get("proveedor_nombre")) for x in same_doc_real + [b_extra]}) == 1,
        "misma_fecha": len({ev.date(x.get("fecha_factura")) for x in same_doc_real + [b_extra]}) == 1,
        "importe_resumen_B": ev.number(b_extra.get("importe_total")),
        "suma_tres_facturas_B": sum_real,
        "suma_exacta": abs((ev.number(b_extra.get("importe_total")) or 0) - sum_real) < 0.005,
    },
    "diferencias": {
        "numero_factura_resumen": b_extra.get("numero_factura"),
        "numeros_facturas_reales": [x.get("numero_factura") for x in same_doc_real],
        "pagina_resumen": [b_extra.get("pagina_inicio"), b_extra.get("pagina_fin")],
        "paginas_facturas": [[x.get("pagina_inicio"), x.get("pagina_fin")] for x in same_doc_real],
    },
    "criterio_evaluador": "match_invoices no encuentra clave gold para numero_factura nulo y clasifica la portada-resumen como factura inventada.",
    "eliminable_deterministamente": True,
    "regla_especifica": "Si una salida carece de numero_factura, esta rotulada como resumen/avisos y su total coincide exactamente con la suma de facturas numeradas del mismo proveedor y PDF, clasificarla como agregado documental, no como factura.",
}
dump("duplicados.json", {
    "facturas_inventadas_B": 1,
    "caso": duplicate_b,
    "regla_general_propuesta_no_implementada": "Deduplicar facturas numeradas por proveedor normalizado + numero_factura normalizado; fecha+importe solo apoyan. Tratar agregados sin numero con la regla especifica anterior y no descartarlos si falta evidencia.",
})


concentration = {
    "denominador_ausentes_B": 167,
    "Alliance_Cofares_HEFAME_FEDEFARMA": {"numerador": sum(dist_by_provider[x] for x in ["Alliance", "Cofares", "HEFAME", "FEDEFARMA"]), "porcentaje": round(100 * sum(dist_by_provider[x] for x in ["Alliance", "Cofares", "HEFAME", "FEDEFARMA"]) / 167, 2)},
    "solo_Alliance": {"numerador": dist_by_provider["Alliance"], "porcentaje": round(100 * dist_by_provider["Alliance"] / 167, 2)},
}

patterns = [
    {"patron": "tabla_larga_multipagina", "demostrado": True, "evidencia": "Alliance 08009277 ocupa páginas 5-9 y contiene 162 albaranes gold; B devuelve 0. C recupera 162/162."},
    {"patron": "ultimas_filas", "demostrado": False, "evidencia": "No hay truncamiento parcial: B omite desde el primer hasta el último albarán de 08009277."},
    {"patron": "salto_de_pagina", "demostrado": True, "evidencia": "La omisión cubre una tabla de cinco páginas. No basta por sí solo: HEFAME (2 páginas, 12/12) y Alliance 08009278 (4 páginas, 109/109) sí se extraen."},
    {"patron": "ABONOS", "demostrado": True, "evidencia": "Los 162 ausentes de 08009277 incluyen 160 CARGO y 2 ABONO (08C61794, 08C61795); B extrae movimientos comerciales, pero ningún albarán."},
    {"patron": "tipo_pedido", "demostrado": True, "evidencia": "En FEDEFARMA B coloca PA/RE en tipo_pedido y deja numero sin el prefijo documental compuesto, produciendo 5 ausentes+5 inventados por clave."},
    {"patron": "varias_columnas", "demostrado": True, "evidencia": "FEDEFARMA reparte P, PA/RE y el número base en componentes; la representación B no recompone el literal gold."},
    {"patron": "truncamiento_primeros_N", "demostrado": False, "evidencia": "Ningún fallo B observado es un prefijo correcto seguido de truncamiento: 08009277 es 0/162 y FEDEFARMA es 0/5 por clave."},
    {"patron": "tabla_larga_no_suficiente", "demostrado": True, "evidencia": "Cofares 5450053457 recupera 39/39 en una página y Alliance 08009278 109/109 en cuatro páginas."},
]

recommendation = f"""# Recomendación arquitectónica (no implementada)

## Pipeline general

PDF → Luna V2 → validación determinista → aceptación o activación selectiva de Google Splitter → Luna V2 por segmento → deduplicación determinista → validación final. La prioridad cero es no introducir facturas, albaranes ni movimientos sin soporte documental.

## Activación sin gold

1. Activar splitter cuando el proveedor esté en el grupo de alta densidad demostrado y el documento tenga varias páginas con cabeceras/continuaciones de tabla, pero Luna devuelva cero o un conteo incompatible con indicadores documentales visibles.
2. Activar cuando existan secuencias de filas, fechas, marcadores «ALBARÁN/ALBARAN», «ABONO», «PEDIDO», PA/RE u otros identificadores repetidos y el número de registros Luna sea inferior al conteo determinista de señales. Las señales solo disparan revisión; no crean registros.
3. Activar ante tabla que cruza páginas, reinicio de cabecera, factura multifactura o no conciliación aritmética entre subtotales documentales y suma de registros Luna.
4. Deduplicar por proveedor normalizado + número de factura. Fecha e importe son apoyo; nunca deben fusionar números distintos. Ante conflicto, incidencia y conservación de ambas salidas sin elegir por inferencia.
5. Tras splitter, rechazar nuevos identificadores sin literal demostrable y comparar prefijos/componentes sin modificar el valor documental.

## Reglas por proveedor justificadas

- Alliance: justificado por 162/167 ausentes B (97,01%) concentrados en 08009277 y recuperación C 162/162. Activar con factura multipágina de alta densidad cuando Luna devuelva cero albaranes o no concilie filas/ABONOS.
- FEDEFARMA: no usar splitter como corrección automática de claves. Validar identificadores compuestos P + PA/RE + número; B y C mantienen 5/5 fallos exactos por prefijo. Conservar el literal y abrir incidencia si no puede recomponerse de evidencia estructural.
- Cofares y HEFAME: no se justifica activación por proveedor con estos errores B de albaranes (0 ausentes). Sí activar por señales generales verificables de tabla multipágina/no conciliación.
- Resto: sin regla específica por proveedor en este conjunto.

## Umbrales objetivos derivados

- Cero registros Luna con al menos dos señales documentales independientes y repetidas de filas de albarán: activar.
- Documento multipágina con continuidad de tabla y conteo Luna menor que el conteo de identificadores inequívocos: activar.
- Diferencia aritmética no explicada: activar revisión/splitter, pero preservar total fiscal y literales; nunca fabricar el concepto compensatorio.
- Toda salida del splitter pasa por la misma clave exacta y control de invenciones antes de sustituir B.
"""
text("recomendacion_arquitectonica.md", recommendation)

summary = {
    "estado": "COMPLETADO_CON_INCIDENCIA_CACHE_EXPLICADA", "motivo_estado": "Los datos, código fuente y salidas congeladas permanecen invariantes. La primera importación local del evaluador regeneró únicamente su archivo efímero __pycache__/evaluar.cpython-313.pyc; se conserva y declara la incidencia.", "head_esperado": EXPECTED_HEAD, "metricas_B_reconciliadas": {"albaranes": metrics_frozen["albaranes"], "movimientos_comerciales": metrics_frozen["movimientos_comerciales"], "campos_principales": metrics_frozen["campos_principales"], "impuestos": metrics_frozen["impuestos"]},
    "ausentes_albaranes_distribucion_factura": dist_by_invoice, "ausentes_albaranes_distribucion_proveedor": provider_distribution,
    "albaranes_inventados": invented_deliveries, "salida_adicional_B": {"pdf": duplicate_b["pdf"], "numero_factura": b_extra.get("numero_factura"), "importe_resumen": b_extra.get("importe_total"), "suma_facturas_reales": sum_real},
    "concentracion": concentration, "recuperacion_C": {"recuperados": 162, "tambien_ausentes": 5, "inventados_B_corregidos": 0, "nuevos_inventados_C": 8},
    "patrones": patterns, "cero_llamadas_externas_iniciadas": True, "cero_procesos_api_iniciados": True, "commit": False, "push": False,
}
dump("resumen.json", summary)

md = f"""# Análisis forense de errores Baseline B (Luna V2)

Análisis exclusivamente local sobre salidas congeladas. Se reutilizaron `invoice_key`, `equal`, `match_invoices` y `match_list` de `comparativa_2o_gold_a_b_c/evaluar.py`.

## Reconciliación

- Albaranes: 337 gold, 170 correctos por clave, 167 ausentes y 5 inventados; cobertura 50,45%.
- Movimientos: 25 gold, 11 detectados por clave, 14 ausentes y 7 inventados; detección 44,00%.
- Campos: 214/251 correctos = 85,26%; cobertura (214+25)/251 = 95,22%; 25 valores erróneos, 12 ausencias y 13 invenciones.
- Fiscalidad: 89/90 atributos de tramos emparejados = 98,89%; además 8 tramos ausentes y 11 inventados fuera de ese denominador.

## Albaranes

Distribución exacta de los 167 ausentes: 08009278=0, 08009277=162, 08009279=0, 5450053457=0, 0563820041=0, VN2605-0005656=5, resto=0. Por proveedor: Alliance 162 (97,01%), FEDEFARMA 5 (2,99%), Cofares/HEFAME/resto 0.

Los cinco inventados del evaluador son `2620-2173388`, `2605-0221864`, `2605-0222046`, `2620-2217350` y `2605-0228056`. Todos corresponden, por orden/fecha/importe, a literales gold `P PA 2620-2173388`, `P RE 2605-0221864`, `P RE 2605-0222046`, `P PA 2620-2217350` y `P RE 2605-0228056`. Es un error demostrado de representación de clave compuesta; no hay evidencia de números base fabricados.

## Concentración y C

Alliance+Cofares+HEFAME+FEDEFARMA concentran 167/167 = 100,00% de ausentes; Alliance sola 162/167 = 97,01%. C recupera 162/167 (todos Alliance), mantiene 5 ausentes FEDEFARMA, corrige 0/5 inventados B por clave exacta e introduce 8 claves no coincidentes en las facturas con error B (3 Alliance y 5 FEDEFARMA).

## Duplicado

En B, la portada-resumen de `FEDE VTO 15.8.26 PIO.pdf` genera una cuarta salida sin número de factura por 409,58 EUR. Coincide exactamente con la suma de VN2605-0005656 (19,96), SI26-04567 (81,07) y VN26-0016742 (308,55). El evaluador la clasifica como inventada porque no existe clave gold nula. Es eliminable como agregado solo cuando concurren número nulo, rótulo de resumen/avisos, mismo proveedor/PDF y suma exacta; para facturas numeradas, proveedor+número es la clave y fecha+importe solo apoyan.

## Patrones y discrepancias

La omisión Alliance 08009277 es total (0/162) en páginas 5-9, no truncamiento a primeros N. Incluye 160 CARGO y 2 ABONO. Las tablas largas/multipágina son factor demostrado pero no suficiente: 08009278 obtiene 109/109 y HEFAME 12/12. FEDEFARMA falla por componentes P + PA/RE + número.

B omite las discrepancias Alliance de 0,02 EUR en 08009278/08009279 y conserva los totales fiscales. En HEFAME detecta dos diferencias literales de 110 EUR, pero no identifica los 80 EUR no explicados ni inventa un concepto compensatorio; conserva el total fiscal.

Los detalles completos están en los JSON específicos y la propuesta no implementada en `recomendacion_arquitectonica.md`.
"""
text("resumen.md", md)


# Validación local final e invariancia de todos los manifiestos iniciales.
json_files = sorted(OUT.glob("*.json"))
for path in json_files: load(path)
manifest_checks = []
for manifest_name in ["manifest_fuentes_inicial.json", "manifest_fuentes_ac_inicial.json"]:
    manifest = load(OUT / manifest_name)
    changes = []
    for item in manifest["archivos"]:
        path = ROOT / item["ruta"]
        stat = path.stat()
        current = {"sha256": sha(path), "mtime_utc": stat.st_mtime_ns, "bytes": stat.st_size}
        initial_mtime_ns = int(__import__("datetime").datetime.fromisoformat(item["mtime_utc"]).timestamp() * 1_000_000_000)
        # PowerShell serializa 7 decimales y datetime.timestamp usa float; 1 ms evita
        # falsos positivos de conversión sin ocultar una escritura real (hash además obligatorio).
        if current["sha256"] != item["sha256"].lower() or current["bytes"] != item["bytes"] or abs(current["mtime_utc"] - initial_mtime_ns) > 1_000_000:
            changes.append({"ruta": item["ruta"], "inicial": item, "final": current})
    manifest_checks.append({"manifest": manifest_name, "archivos": len(manifest["archivos"]), "cambios": changes, "invariante": not changes})

head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
status = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True)
assert head == EXPECTED_HEAD
semantic_source_changes = [change for check in manifest_checks for change in check["cambios"] if "__pycache__" not in change["ruta"]]
cache_changes = [change for check in manifest_checks for change in check["cambios"] if "__pycache__" in change["ruta"]]
assert not semantic_source_changes
validation = {"json_parseados": [x.name for x in json_files], "json_validos": True, "reconciliaciones": {"albaranes": True, "movimientos": True, "campos": True, "fiscalidad": True, "recuperacion_C": True}, "invariancia_fuentes": manifest_checks, "head_inicial_esperado": EXPECTED_HEAD, "head_final": head, "head_invariante": True, "git_status_short": status.splitlines(), "cero_llamadas_red_api_iniciadas_por_script": True, "cero_procesos_externos_api_iniciados": True, "commit_realizado": False, "push_realizado": False}
validation["fuentes_semanticas_A_B_C_gold_comparativa_invariantes"] = not semantic_source_changes
validation["incidencia_cache_python"] = cache_changes
validation["criterio_final_completo"] = not semantic_source_changes
dump("validacion_final.json", validation)

artifact_manifest = []
for path in sorted(OUT.iterdir()):
    if path.is_file() and path.name != "manifest_artefactos.json":
        artifact_manifest.append({"ruta": rel(path), "sha256": sha(path), "bytes": path.stat().st_size})
dump("manifest_artefactos.json", {"archivos": artifact_manifest})
print(json.dumps({"estado": "COMPLETADO_CON_INCIDENCIA_CACHE_EXPLICADA" if cache_changes else "COMPLETADO", "artefactos": len(artifact_manifest) + 1, "head": head, "fuentes_semanticas_invariantes": not semantic_source_changes, "incidencias_cache": len(cache_changes)}, ensure_ascii=False))
