from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
RESULTS = OUT.parent
GOLD = ROOT / "pruebas/facturas/gold_standard"
SOURCE = ROOT / "pruebas/facturas/documentos/2o_gold_standard"
DIRS = {
    "A": RESULTS / "benchmark_2o_gold_luna",
    "B": RESULTS / "benchmark_2o_gold_luna_v2",
    "C": RESULTS / "benchmark_2o_gold_google_splitter_luna_v2",
}
MAIN_FIELDS = [
    "naturaleza_principal", "requiere_conciliacion_albaranes", "pagina_inicio", "pagina_fin",
    "proveedor_nombre", "proveedor_cif", "numero_factura", "fecha_factura",
    "base_imponible_total", "iva_total", "recargo_equivalencia_total", "importe_total",
    "destinatario_nombre", "destinatario_cif", "forma_pago",
]
MONEY_FIELDS = {"base_imponible_total", "iva_total", "recargo_equivalencia_total", "importe_total"}
APPROVED_A_HITO = "D2F0228CA301A06D6D24E72C0D57A095FE1B2B040B19DA13F67CEE64A2DB16F0"
PROMPT_HASH = "169CDBA865E9A130FC0A5C07AB9B9AF3C1A94F980A319893DD94377EA3C8C60D"
SCHEMA_HASH = "BFB6D2C277A585EB75703EC6F03548B282EF927D0C5850E6E66590F0FBA1EC71"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def unwrap(value: Any) -> Any:
    return value.get("valor") if isinstance(value, dict) and "valor" in value else value


def text(value: Any) -> str | None:
    value = unwrap(value)
    if value is None:
        return None
    return " ".join(str(value).strip().split()) or None


def canon(value: Any) -> str | None:
    value = text(value)
    if value is None:
        return None
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", value).strip().upper()


def invoice_key(value: Any) -> str | None:
    value = canon(value)
    return re.sub(r"[^A-Z0-9]", "", value) if value else None


def number(value: Any) -> float | None:
    value = unwrap(value)
    if value is None or value == "":
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def date(value: Any) -> str | None:
    value = text(value)
    if not value:
        return None
    value = value.replace("/", "-").replace(".", "-")
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d-%m-%y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return canon(value)


def equal(field: str, left: Any, right: Any) -> bool:
    if field in MONEY_FIELDS or field.startswith("money:"):
        a, b = number(left), number(right)
        return a is not None and b is not None and abs(a - b) <= 0.01
    if "fecha" in field:
        return date(left) == date(right)
    if field in {"pagina_inicio", "pagina_fin", "requiere_conciliacion_albaranes"}:
        return left == right
    if field in {"numero_factura", "numero"}:
        return invoice_key(left) == invoice_key(right)
    return canon(left) == canon(right)


def normalize_gold(f: dict[str, Any], document: str) -> dict[str, Any]:
    totals = f.get("totales") or {}
    taxes = f.get("impuestos") or {}
    recipient = f.get("destinatario") or {}
    return {
        "documento": document,
        "numero_factura": f.get("numero_factura"),
        "tipo_documento": None,
        "naturaleza_principal": f.get("naturaleza_principal"),
        "requiere_conciliacion_albaranes": f.get("requiere_conciliacion_albaranes"),
        "pagina_inicio": f.get("pagina_inicio"), "pagina_fin": f.get("pagina_fin"),
        "proveedor_nombre": (f.get("emisor") or {}).get("nombre"),
        "proveedor_cif": (f.get("emisor") or {}).get("nif"),
        "fecha_factura": f.get("fecha_emision"),
        "base_imponible_total": totals.get("base_imponible_total"),
        "iva_total": taxes.get("iva_total"),
        "recargo_equivalencia_total": taxes.get("recargo_equivalencia_total"),
        "importe_total": totals.get("total_factura"),
        "destinatario_nombre": recipient.get("nombre"), "destinatario_cif": recipient.get("nif"),
        "forma_pago": None,
        "vencimientos": [{"fecha": x.get("fecha"), "importe": x.get("importe")} for x in f.get("vencimientos", [])],
        "impuestos": [{
            "base": x.get("base"), "tipo_iva": x.get("porcentaje_iva"), "cuota_iva": x.get("iva"),
            "tipo_recargo_equivalencia": x.get("porcentaje_recargo_equivalencia"),
            "cuota_recargo_equivalencia": x.get("recargo_equivalencia"),
        } for x in f.get("bases", [])],
        "albaranes": [{
            "numero": x.get("numero") or x.get("pedido"), "fecha": x.get("fecha"),
            "naturaleza": x.get("sentido"), "tipo_pedido": x.get("tipo_pedido"),
            "importe_base": x.get("base"), "importe_total": x.get("total"),
        } for x in f.get("albaranes", [])],
        "movimientos_comerciales": [{
            "tipo": x.get("tipo"), "descripcion_literal": x.get("descripcion"), "sentido": x.get("sentido"),
            "base": x.get("base") if x.get("base") is not None else x.get("base_calculo"),
            "iva": x.get("iva"), "recargo_equivalencia": x.get("recargo_equivalencia"), "importe": x.get("importe"),
        } for x in f.get("movimientos_comerciales", [])],
        "discrepancias_documentales": f.get("discrepancias", []),
    }


def normalize_prediction(f: dict[str, Any], baseline: str, document: str, page_offset: int = 0) -> dict[str, Any]:
    recipient = f.get("destinatario") or {}
    if baseline == "A":
        invoices = f.get("impuestos", [])
        taxes = [{
            "base": unwrap(x.get("base_imponible")), "tipo_iva": unwrap(x.get("tipo_iva")),
            "cuota_iva": unwrap(x.get("cuota_iva")), "tipo_recargo_equivalencia": unwrap(x.get("tipo_recargo_equivalencia")),
            "cuota_recargo_equivalencia": unwrap(x.get("cuota_recargo_equivalencia")),
        } for x in invoices]
        due = [{"fecha": x.get("fecha_vencimiento"), "importe": x.get("importe")} for x in f.get("vencimientos", [])]
        deliveries = [{
            "numero": unwrap(x.get("numero_albaran") or x.get("numero")), "fecha": unwrap(x.get("fecha_albaran") or x.get("fecha")),
            "naturaleza": unwrap(x.get("naturaleza") or x.get("sentido")), "tipo_pedido": unwrap(x.get("tipo_pedido")),
            "importe_base": unwrap(x.get("importe_base") or x.get("base")), "importe_total": unwrap(x.get("importe_total") or x.get("total")),
        } for x in f.get("albaranes", [])]
        movements = [{
            "tipo": unwrap(x.get("tipo_ajuste")), "descripcion_literal": unwrap(x.get("descripcion")),
            "sentido": unwrap(x.get("sentido")), "base": unwrap(x.get("base")), "iva": unwrap(x.get("iva")),
            "recargo_equivalencia": unwrap(x.get("recargo_equivalencia")), "importe": unwrap(x.get("importe")),
        } for x in f.get("ajustes", [])]
        nature = None
        discrepancies = []
    else:
        taxes = f.get("impuestos", [])
        due = f.get("vencimientos", [])
        deliveries = f.get("albaranes", [])
        movements = f.get("movimientos_comerciales", [])
        nature = f.get("naturaleza_principal")
        discrepancies = f.get("discrepancias_documentales", [])
    start = unwrap(f.get("pagina_inicio"))
    end = unwrap(f.get("pagina_fin"))
    if baseline == "C":
        start = start + page_offset if isinstance(start, int) else start
        end = end + page_offset if isinstance(end, int) else end
    return {
        "documento": document, "numero_factura": unwrap(f.get("numero_factura")),
        "tipo_documento": unwrap(f.get("tipo_documento")), "naturaleza_principal": nature,
        "requiere_conciliacion_albaranes": unwrap(f.get("requiere_conciliacion_albaranes")),
        "pagina_inicio": start, "pagina_fin": end,
        "proveedor_nombre": unwrap(f.get("proveedor_nombre")), "proveedor_cif": unwrap(f.get("proveedor_cif")),
        "fecha_factura": unwrap(f.get("fecha_factura")), "base_imponible_total": unwrap(f.get("base_imponible_total")),
        "iva_total": unwrap(f.get("iva_total")), "recargo_equivalencia_total": unwrap(f.get("recargo_equivalencia_total")),
        "importe_total": unwrap(f.get("importe_total")),
        "destinatario_nombre": unwrap(recipient.get("nombre")), "destinatario_cif": unwrap(recipient.get("cif")),
        "forma_pago": unwrap(f.get("forma_pago")), "vencimientos": due, "impuestos": taxes,
        "albaranes": deliveries, "movimientos_comerciales": movements, "discrepancias_documentales": discrepancies,
    }


def document_map() -> dict[str, str]:
    inventory = load(DIRS["A"] / "fase0_inventario.json")["documentos"]
    by_hash = {sha(path): path.name for path in SOURCE.glob("*.pdf")}
    index = load(GOLD / "indice.json")
    filename_to_gold = {item["pdf_fuente"]: item["archivo_json"] for item in index["pdfs"]}
    result = {}
    for item in inventory:
        filename = by_hash[str(item["sha256_pdf"]).upper()]
        result[item["documento"]] = filename_to_gold[filename]
    return result


def load_gold(mapping: dict[str, str]) -> list[dict[str, Any]]:
    values = []
    for document, filename in mapping.items():
        values.extend(normalize_gold(item, document) for item in load(GOLD / filename)["facturas"])
    return values


def load_predictions(baseline: str) -> list[dict[str, Any]]:
    values = []
    if baseline in {"A", "B"}:
        for path in sorted((DIRS[baseline] / "extracciones").glob("documento_*/estructurado.json")):
            document = path.parent.name
            values.extend(normalize_prediction(item, baseline, document) for item in load(path)["facturas"])
    else:
        manifest = load(DIRS["C"] / "manifest_segmentos.json")
        segments = {item["segmento"]: item for item in manifest["segmentos"]}
        for path in sorted((DIRS["C"] / "extracciones").glob("segmento_*/estructurado.json")):
            segment = segments[path.parent.name]
            values.extend(normalize_prediction(item, "C", segment["documento"], segment["pagina_inicio"] - 1) for item in load(path)["facturas"])
    return values


def match_invoices(gold: list[dict[str, Any]], pred: list[dict[str, Any]]) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    pred_buckets = defaultdict(list)
    for item in pred:
        pred_buckets[(item["documento"], invoice_key(item["numero_factura"]))].append(item)
    matched, missing = [], []
    used = set()
    for expected in gold:
        bucket = pred_buckets[(expected["documento"], invoice_key(expected["numero_factura"]))]
        candidate = next((item for item in bucket if id(item) not in used), None)
        if candidate is None:
            missing.append(expected)
        else:
            used.add(id(candidate)); matched.append((expected, candidate))
    invented = [item for item in pred if id(item) not in used]
    return matched, missing, invented


def metric_fields(matched: list[tuple[dict[str, Any], dict[str, Any]]], missing: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    aggregate = Counter()
    per_field = {}
    for field in MAIN_FIELDS:
        score = Counter()
        for expected, predicted in matched:
            gold_value, pred_value = expected.get(field), predicted.get(field)
            if gold_value is not None:
                score["evaluables"] += 1
                if pred_value is None: score["ausencias"] += 1
                elif equal(field, gold_value, pred_value): score["correctos"] += 1
                else: score["errores"] += 1
            elif pred_value is not None:
                score["invenciones"] += 1
        for expected in missing:
            if expected.get(field) is not None:
                score["evaluables"] += 1; score["ausencias"] += 1
        score["cobertura_pct"] = round(100 * (score["correctos"] + score["errores"]) / score["evaluables"], 2) if score["evaluables"] else None
        score["acierto_pct"] = round(100 * score["correctos"] / score["evaluables"], 2) if score["evaluables"] else None
        per_field[field] = dict(score); aggregate.update({k: v for k, v in score.items() if isinstance(v, int)})
    aggregate["cobertura_pct"] = round(100 * (aggregate["correctos"] + aggregate["errores"]) / aggregate["evaluables"], 2)
    aggregate["acierto_pct"] = round(100 * aggregate["correctos"] / aggregate["evaluables"], 2)
    return dict(aggregate), per_field


def match_list(gold_items: list[dict[str, Any]], pred_items: list[dict[str, Any]], key_fn: Any) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], int, int]:
    buckets = defaultdict(list)
    for item in pred_items: buckets[key_fn(item)].append(item)
    used = set(); matched = []
    for expected in gold_items:
        candidate = next((x for x in buckets[key_fn(expected)] if id(x) not in used), None)
        if candidate is not None: used.add(id(candidate)); matched.append((expected, candidate))
    return matched, len(gold_items) - len(matched), len(pred_items) - len(used)


def list_metrics(matched_invoices: list[tuple[dict[str, Any], dict[str, Any]]], missing_invoices: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    specs = {
        "vencimientos": (lambda x: date(x.get("fecha")), ["fecha", "money:importe"]),
        "impuestos": (lambda x: (number(x.get("tipo_iva")), number(x.get("tipo_recargo_equivalencia"))), ["money:base", "money:cuota_iva", "money:cuota_recargo_equivalencia"]),
        "albaranes": (lambda x: invoice_key(x.get("numero")), ["numero", "fecha", "naturaleza", "tipo_pedido", "money:importe_base", "money:importe_total"]),
        "movimientos_comerciales": (lambda x: (canon(x.get("tipo")), canon(x.get("sentido")), canon(x.get("descripcion_literal"))), ["tipo", "descripcion_literal", "sentido", "money:base", "money:iva", "money:recargo_equivalencia", "money:importe"]),
    }
    for name, (key_fn, attrs) in specs.items():
        score = Counter(); attr_score = Counter()
        for expected, predicted in matched_invoices:
            pairs, absent, invented = match_list(expected[name], predicted[name], key_fn)
            score["gold"] += len(expected[name]); score["detectados"] += len(pairs)
            score["ausentes"] += absent; score["inventados"] += invented
            for left, right in pairs:
                full = True
                for attr in attrs:
                    field = attr.removeprefix("money:")
                    if left.get(field) is None and right.get(field) is None: continue
                    attr_score["evaluables"] += 1
                    if left.get(field) is not None and right.get(field) is not None and equal(attr, left.get(field), right.get(field)):
                        attr_score["correctos"] += 1
                    else:
                        attr_score["errores"] += 1; full = False
                if full: score["registros_completamente_correctos"] += 1
        for expected in missing_invoices:
            score["gold"] += len(expected[name]); score["ausentes"] += len(expected[name])
        score["deteccion_pct"] = round(100 * score["detectados"] / score["gold"], 2) if score["gold"] else 100.0
        score["atributos_pct"] = round(100 * attr_score["correctos"] / attr_score["evaluables"], 2) if attr_score["evaluables"] else 100.0
        score["atributos"] = dict(attr_score)
        result[name] = dict(score)
    return result


def discrepancy_metrics(matched: list[tuple[dict[str, Any], dict[str, Any]]], missing: list[dict[str, Any]]) -> dict[str, Any]:
    score = Counter()
    def key(x: Any) -> str | None:
        if isinstance(x, dict): return canon(x.get("descripcion") or json.dumps(x, ensure_ascii=False, sort_keys=True))
        return canon(x)
    for expected, predicted in matched:
        gold_values = [key(x) for x in expected["discrepancias_documentales"]]
        pred_values = [key(x) for x in predicted["discrepancias_documentales"]]
        pairs, absent, invented = match_list([{"v": x} for x in gold_values], [{"v": x} for x in pred_values], lambda x: x["v"])
        score["gold"] += len(gold_values); score["detectadas"] += len(pairs); score["ausentes"] += absent; score["inventadas"] += invented
    for expected in missing:
        score["gold"] += len(expected["discrepancias_documentales"]); score["ausentes"] += len(expected["discrepancias_documentales"])
    score["deteccion_pct"] = round(100 * score["detectadas"] / score["gold"], 2) if score["gold"] else 100.0
    return dict(score)


def evaluate_baseline(name: str, gold: list[dict[str, Any]], pred: list[dict[str, Any]]) -> dict[str, Any]:
    matched, missing, invented = match_invoices(gold, pred)
    fields, per_field = metric_fields(matched, missing)
    lists = list_metrics(matched, missing)
    discrepancies = discrepancy_metrics(matched, missing)
    by_doc_gold = defaultdict(list); by_doc_pred = defaultdict(list)
    for item in gold: by_doc_gold[item["documento"]].append(invoice_key(item["numero_factura"]))
    for item in pred: by_doc_pred[item["documento"]].append(invoice_key(item["numero_factura"]))
    pdfs = []
    for document in sorted(by_doc_gold):
        g, p = Counter(by_doc_gold[document]), Counter(by_doc_pred[document])
        pdfs.append({"documento": document, "facturas_gold": sum(g.values()), "facturas_detectadas": sum(p.values()), "omitidas": sum((g-p).values()), "inventadas": sum((p-g).values()), "multifactura_gold": sum(g.values()) > 1, "multifactura_exacta": g == p})
    hito = load(DIRS[name] / "hito_ciego.json")
    if name == "A":
        cost = float(load(DIRS["A"] / "costes.json")["coste_recalculado_tarifa_oficial_2026_08_13_usd"])
        duration = sum(float(load(path).get("metadata", {}).get("duracion_segundos", 0)) for path in (DIRS["A"] / "extracciones").glob("documento_*/estructurado.json"))
    else:
        cost = float(hito["coste_total_usd"])
        duration = float(hito.get("duracion_total_segundos", hito.get("duracion_google_segundos", 0) + hito.get("duracion_luna_segundos", 0)))
    total_inventions = len(invented) + fields.get("invenciones", 0) + sum(lists[x]["inventados"] for x in lists) + discrepancies.get("inventadas", 0)
    controls = {}
    for invoice in ("08009278", "08009279"):
        pair = next(((g, p) for g, p in matched if invoice_key(g["numero_factura"]) == invoice_key(invoice)), None)
        controls[f"{invoice}_diferencia_total_0_02"] = bool(pair and number(pair[1]["importe_total"]) is not None and abs(abs(number(pair[1]["importe_total"]) - number(pair[0]["importe_total"])) - 0.02) <= 0.001)
    hefame = next(((g, p) for g, p in matched if invoice_key(g["numero_factura"]) == invoice_key("0563820041")), None)
    controls["hefame_80_eur_no_explicados_detectado"] = bool(hefame and any("80" in (canon(x) or "") for x in hefame[1]["discrepancias_documentales"]))
    controls["delivery_504918055_no_es_albaran"] = not any(invoice_key(x.get("numero")) == invoice_key("504918055") for item in pred for x in item["albaranes"])
    per_invoice = []
    predicted_by_gold_id = {(g["documento"], invoice_key(g["numero_factura"])): p for g, p in matched}
    for expected in gold:
        predicted = predicted_by_gold_id.get((expected["documento"], invoice_key(expected["numero_factura"])))
        detail = {"documento": expected["documento"], "numero_factura_gold": expected["numero_factura"], "estado": "OMITIDA" if predicted is None else "IDENTIFICADA"}
        if predicted is not None:
            detail["campos_principales"] = {field: ("AUSENTE" if predicted.get(field) is None and expected.get(field) is not None else "CORRECTO" if expected.get(field) is not None and equal(field, expected.get(field), predicted.get(field)) else "ERROR" if expected.get(field) is not None else "INVENCION" if predicted.get(field) is not None else "NO_EVALUABLE") for field in MAIN_FIELDS}
            detail["listas"] = {}
            list_specs = {
                "vencimientos": lambda x: date(x.get("fecha")),
                "impuestos": lambda x: (number(x.get("tipo_iva")), number(x.get("tipo_recargo_equivalencia"))),
                "albaranes": lambda x: invoice_key(x.get("numero")),
                "movimientos_comerciales": lambda x: (canon(x.get("tipo")), canon(x.get("sentido")), canon(x.get("descripcion_literal"))),
            }
            for list_name, key_fn in list_specs.items():
                pairs, absent, invented_count = match_list(expected[list_name], predicted[list_name], key_fn)
                detail["listas"][list_name] = {"gold": len(expected[list_name]), "detectados": len(pairs), "ausentes": absent, "inventados": invented_count}
        per_invoice.append(detail)
    per_invoice.extend({"documento": item["documento"], "numero_factura_salida": item["numero_factura"], "estado": "INVENTADA"} for item in invented)
    return {
        "baseline": name, "facturas_gold": len(gold), "facturas_detectadas": len(pred), "facturas_correctamente_identificadas": len(matched),
        "facturas_omitidas": len(missing), "facturas_inventadas": len(invented),
        "pdfs_multifactura_gold": sum(x["multifactura_gold"] for x in pdfs), "pdfs_multifactura_exactos": sum(x["multifactura_gold"] and x["multifactura_exacta"] for x in pdfs),
        "campos_principales": fields, "metricas_por_campo": per_field, **lists,
        "discrepancias_documentales": discrepancies, "invenciones_totales_prioritarias": total_inventions,
        "coste_total_usd": round(cost, 8), "coste_por_pdf_usd": round(cost / 14, 8), "coste_por_factura_detectada_usd": round(cost / len(pred), 8) if pred else None,
        "duracion_segundos": round(duration, 3),
        "llamadas_google": hito.get("llamadas_google", 0), "segmentos": hito.get("segmentos", 0),
        "llamadas_luna": hito.get("llamadas_luna", hito.get("llamadas_realizadas", 0)),
        "controles": controls, "resultados_por_pdf": pdfs,
        "facturas_omitidas_ids": [x["numero_factura"] for x in missing], "facturas_inventadas_ids": [x["numero_factura"] for x in invented],
        "resultados_por_factura": per_invoice,
    }


def validation(metrics: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "head_baseline_a": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip().startswith("9b33254"),
        "hito_a_sha256": sha(DIRS["A"] / "hito_ciego.json") == APPROVED_A_HITO,
        "gold_igual_commit_congelado": subprocess.run(["git", "diff", "--quiet", "581150265d677fe94b03268c83802bb934825162", "--", "pruebas/facturas/gold_standard"], cwd=ROOT).returncode == 0,
        "prompt_hash": sha(DIRS["B"] / "prompt_v2.txt") == PROMPT_HASH,
        "schema_hash": sha(DIRS["B"] / "schema_v2.json") == SCHEMA_HASH,
        "contrato_b_c_byte_a_byte": load(DIRS["C"] / "hito_ciego.json")["prompt_sha256"] == PROMPT_HASH and load(DIRS["C"] / "hito_ciego.json")["schema_sha256"] == SCHEMA_HASH,
        "coste_b_bajo_2": metrics["B"]["coste_total_usd"] <= 2,
        "coste_c_bajo_3": metrics["C"]["coste_total_usd"] <= 3,
        "c_limites_llamadas": load(DIRS["C"] / "hito_ciego.json")["segmentos"] <= 30 and load(DIRS["C"] / "hito_ciego.json")["llamadas_luna"] <= 30,
        "c_cobertura_paginas": load(DIRS["C"] / "hito_ciego.json")["cobertura_paginas_exacta_una_vez"],
        "gold_no_consultado_en_hitos_b_c": not load(DIRS["B"] / "hito_ciego.json")["gold_consultado_durante_extraccion"] and not load(DIRS["C"] / "hito_ciego.json")["gold_consultado_durante_extraccion"],
    }
    response_ids = []
    for baseline in ("B", "C"):
        response_ids.extend(x["response_id"] for x in (load(DIRS[baseline] / "hito_ciego.json").get("resultados") or load(DIRS[baseline] / "hito_ciego.json").get("resultados_luna")))
    checks["response_ids_unicos_b_c"] = len(response_ids) == len(set(response_ids))
    for baseline in ("B", "C"):
        hito = load(DIRS[baseline] / "hito_ciego.json")
        hashes = hito.get("hashes_archivos_json") or hito.get("hashes_archivos")
        checks[f"hashes_hito_{baseline.lower()}"] = all((DIRS[baseline] / rel).is_file() and sha(DIRS[baseline] / rel) == digest for rel, digest in hashes.items())
    return {"checks": checks, "todos_correctos": all(checks.values())}


def recommendation(metrics: dict[str, Any]) -> dict[str, Any]:
    def rank(name: str) -> tuple[Any, ...]:
        value = metrics[name]
        return (-value["facturas_inventadas"], -value["invenciones_totales_prioritarias"], value["facturas_correctamente_identificadas"], value["albaranes"]["detectados"], value["campos_principales"]["correctos"])
    winner = max(("B", "C"), key=rank)
    need_normalizers = any(metrics[winner][key]["deteccion_pct"] < 95 or metrics[winner][key]["inventados"] > 0 for key in ("albaranes", "movimientos_comerciales")) or metrics[winner]["invenciones_totales_prioritarias"] > 0
    return {
        "opcion_recomendada": "Google Splitter + Luna V2" if winner == "C" else "Luna V2 sola",
        "criterio": "prioridad lexicografica: menos facturas inventadas; menos invenciones totales; mas facturas identificadas; mas albaranes detectados; mas campos principales correctos",
        "mantener_normalizadores_especificos_adicionales": need_normalizers,
        "motivo_normalizadores": "Se mantienen si la opcion ganadora tiene invenciones o menos de 95% de deteccion sin invenciones en albaranes/movimientos.",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mapping = document_map(); gold = load_gold(mapping)
    metrics = {name: evaluate_baseline(name, gold, load_predictions(name)) for name in ("A", "B", "C")}
    deltas = {
        "B-A": {"facturas_identificadas": metrics["B"]["facturas_correctamente_identificadas"] - metrics["A"]["facturas_correctamente_identificadas"], "campos_pp": round(metrics["B"]["campos_principales"]["acierto_pct"] - metrics["A"]["campos_principales"]["acierto_pct"], 2), "albaranes_detectados": metrics["B"]["albaranes"]["detectados"] - metrics["A"]["albaranes"]["detectados"], "invenciones": metrics["B"]["invenciones_totales_prioritarias"] - metrics["A"]["invenciones_totales_prioritarias"], "coste_usd": round(metrics["B"]["coste_total_usd"] - metrics["A"]["coste_total_usd"], 8)},
        "C-B": {"facturas_identificadas": metrics["C"]["facturas_correctamente_identificadas"] - metrics["B"]["facturas_correctamente_identificadas"], "campos_pp": round(metrics["C"]["campos_principales"]["acierto_pct"] - metrics["B"]["campos_principales"]["acierto_pct"], 2), "albaranes_detectados": metrics["C"]["albaranes"]["detectados"] - metrics["B"]["albaranes"]["detectados"], "invenciones": metrics["C"]["invenciones_totales_prioritarias"] - metrics["B"]["invenciones_totales_prioritarias"], "coste_usd": round(metrics["C"]["coste_total_usd"] - metrics["B"]["coste_total_usd"], 8)},
    }
    summary = {"gold_commit": "581150265d677fe94b03268c83802bb934825162", "logica_comun": True, "tolerancia_importes_eur": 0.01, "metricas": metrics, "deltas": deltas, "recomendacion": recommendation(metrics)}
    valid = validation(metrics)
    dump(OUT / "resumen.json", summary); dump(OUT / "validacion_final.json", valid)
    for name in ("A", "B", "C"):
        dump(OUT / f"metricas_{name.lower()}.json", metrics[name])
        dump(OUT / f"resultados_por_pdf_{name.lower()}.json", metrics[name]["resultados_por_pdf"])
        dump(OUT / f"resultados_por_factura_{name.lower()}.json", metrics[name]["resultados_por_factura"])
    rows = []
    for name in ("A", "B", "C"):
        m = metrics[name]
        rows.append(f"| {name} | {m['facturas_detectadas']} | {m['facturas_correctamente_identificadas']} | {m['facturas_omitidas']} | {m['facturas_inventadas']} | {m['pdfs_multifactura_exactos']}/{m['pdfs_multifactura_gold']} | {m['campos_principales']['acierto_pct']}% | {m['campos_principales']['cobertura_pct']}% | {m['impuestos']['atributos_pct']}% | {m['vencimientos']['deteccion_pct']}% | {m['albaranes']['detectados']}/{m['albaranes']['gold']} | {m['albaranes']['ausentes']} | {m['albaranes']['inventados']} | {m['movimientos_comerciales']['deteccion_pct']}% | {m['invenciones_totales_prioritarias']} | ${m['coste_total_usd']:.8f} | ${m['coste_por_pdf_usd']:.8f} | ${m['coste_por_factura_detectada_usd']:.8f} | {m['duracion_segundos']:.3f}s |")
    md = """# Comparativa A/B/C — segundo gold\n\nEvaluacion determinista comun, con tolerancia monetaria de 0,01 EUR e invenciones como prioridad.\n\n| Baseline | Facturas salida | Identificadas | Omitidas | Inventadas | Multifaktura exacta | Campos acierto | Cobertura | Fiscalidad atributos | Vencimientos | Albaranes | Alb. ausentes | Alb. inventados | Movimientos | Invenciones totales | Coste total | Coste/PDF | Coste/factura salida | Duracion |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n""" + "\n".join(rows)
    md += f"\n\n## Deltas\n\n- B-A (contrato V2): `{json.dumps(deltas['B-A'], ensure_ascii=False)}`\n- C-B (Splitter): `{json.dumps(deltas['C-B'], ensure_ascii=False)}`\n\n## Recomendacion\n\n{summary['recomendacion']['opcion_recomendada']}. Normalizadores especificos adicionales: {'si' if summary['recomendacion']['mantener_normalizadores_especificos_adicionales'] else 'no'}.\n"
    (OUT / "resumen.md").write_text(md, encoding="utf-8")
    manifest = {}
    for path in sorted(OUT.glob("*"), key=lambda value: value.name):
        if path.is_file() and path.name != "manifest_archivos.json":
            manifest[path.name] = sha(path)
    dump(OUT / "manifest_archivos.json", {"archivos": manifest, "todos_hasheados": True})
    print(json.dumps({"ok": valid["todos_correctos"], "recomendacion": summary["recomendacion"], "deltas": deltas, "tabla": {k: {x: metrics[k][x] for x in ("facturas_detectadas", "facturas_correctamente_identificadas", "facturas_omitidas", "facturas_inventadas", "invenciones_totales_prioritarias", "coste_total_usd")} for k in metrics}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
