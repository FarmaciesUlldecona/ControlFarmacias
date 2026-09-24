"""Contrato multifactura: contenido economico separado de cobertura y seleccion.

No realiza I/O ni decide pagos. La seleccion usa segmentos tecnicos; la clave
economica no contiene documento, SHA, nombre, paginas ni posicion del segmento.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import re

from src.facturas.barrera_farmacia import resolver_farmacia_documental


def _valor(campo):
    if not isinstance(campo, dict) or not campo.get("evidencia"):
        return None
    value = campo.get("valor")
    if not any(isinstance(e, dict) and type(e.get("pagina")) is int
               and e["pagina"] > 0 and str(e.get("literal", "")).strip()
               for e in campo["evidencia"]):
        return None
    return value


def componentes_identidad(factura):
    """NIF documentado como canonico conservador; sin NIF requiere revision."""
    try:
        proveedor = _valor(factura.get("proveedor", {}).get("nif"))
        destinatario = _valor(factura.get("destinatario", {}).get("nif"))
        numero = _valor(factura.get("numero_factura"))
        tipo = _valor(factura.get("tipo_documento"))
        fecha = _valor(factura.get("fecha_factura"))
        total = _valor(factura.get("totales", {}).get("total"))
        if any(x is None for x in (proveedor, destinatario, numero, tipo, fecha, total)):
            return None
        tipo = str(tipo).strip().upper()
        if tipo == "FACTURA_DUPLICADO":
            tipo = "FACTURA"
        if tipo not in {"FACTURA", "ABONO", "FACTURA_RECTIFICATIVA"}:
            return None
        norm = lambda s: re.sub(r"[^A-Z0-9]", "", str(s).upper())
        numero = str(numero).strip().upper()
        amount = Decimal(str(total))
        if (not amount.is_finite() or amount != amount.quantize(Decimal(".0001"))
                or abs(amount) >= Decimal("100000000000000")):
            return None
        if amount == 0:
            amount = Decimal(0)
        parts = [norm(proveedor), numero, tipo, norm(destinatario),
                 date.fromisoformat(fecha["iso"]).isoformat(), format(amount, ".4f")]
        if not all(parts) or any("\x1f" in x for x in parts):
            return None
        return parts
    except (ValueError, TypeError, KeyError, ArithmeticError):
        return None


def clave_economica(factura):
    parts = componentes_identidad(factura)
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest() if parts else None


def clasificar_identidad(factura, existentes):
    parts = componentes_identidad(factura)
    if parts is None:
        return "IDENTIDAD_NO_DEMOSTRADA"
    duplicate = False
    for other in existentes:
        previous = componentes_identidad(other)
        if previous and previous[:4] == parts[:4]:
            if previous != parts:
                return "IDENTIDAD_NO_DEMOSTRADA"
            duplicate = True
    return "DUPLICADA" if duplicate else "NUEVA"


def preparar_documento(documento, segmentos_autorizados):
    """Conserva TODO el inventario. Nunca recorta facturas para persistencia parcial."""
    doc = deepcopy(documento)
    if doc.get("documento_completo_demostrado") is not True:
        raise ValueError("DOCUMENTO_INCOMPLETO")
    facturas = doc.get("facturas")
    if not facturas or type(doc.get("numero_paginas")) is not int:
        raise ValueError("INVENTARIO_DOCUMENTAL_INVALIDO")
    segments, pages = set(), set()
    for factura in facturas:
        provenance = factura.get("provenance", {})
        segment = provenance.get("segment_id")
        if not segment or segment in segments:
            raise ValueError("SEGMENTO_DUPLICADO_O_AUSENTE")
        segments.add(segment)
        start, end = factura.get("pagina_inicio"), factura.get("pagina_fin")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= doc["numero_paginas"]:
            raise ValueError("RANGO_FACTURA_INVALIDO")
        expected = list(range(start, end + 1))
        if provenance.get("paginas") != expected:
            raise ValueError("PROVENANCE_INCOMPLETA")
        if pages.intersection(expected):
            raise ValueError("SEGMENTOS_SOLAPADOS")
        def comprobar_evidencia(value):
            if isinstance(value, dict):
                for evidence in value.get("evidencia", []):
                    if evidence.get("pagina") not in expected:
                        raise ValueError("EVIDENCIA_FUERA_DE_FACTURA")
                for child in value.values():
                    comprobar_evidencia(child)
            elif isinstance(value, list):
                for child in value:
                    comprobar_evidencia(child)
        comprobar_evidencia(factura)
        pages.update(expected)
        key = clave_economica(factura)
        factura["identidad_economica_clave"] = key
        factura["factura_id"] = key
        factura["identidad_estado"] = "NUEVA" if key else "IDENTIDAD_NO_DEMOSTRADA"
        if resolver_farmacia_documental(factura).farmacia_documental != "PIO":
            factura["identidad_estado"] = "IDENTIDAD_NO_DEMOSTRADA"
    if pages != set(range(1, doc["numero_paginas"] + 1)):
        raise ValueError("COBERTURA_DOCUMENTAL_INCOMPLETA")
    selected = list(segmentos_autorizados)
    if len(selected) != len(set(selected)) or not set(selected) <= segments:
        raise ValueError("SELECCION_NO_PERTENECE_AL_DOCUMENTO")
    return {"resultado_json": doc, "segmentos_autorizados": selected}


def persistir_multifactura(cliente, documento_id, documento, segmentos_autorizados,
                          worker_id, idempotency_key, resultado_hash):
    payload = preparar_documento(documento, segmentos_autorizados)
    return cliente.rpc("cf_persistir_documento_multifactura", {
        "p_documento_id": documento_id, "p_worker_id": worker_id,
        "p_idempotency_key": idempotency_key, "p_resultado_hash": resultado_hash,
        "p_resultado": payload["resultado_json"],
        "p_segmentos_autorizados": payload["segmentos_autorizados"],
    }).execute()


def adaptar_resultado_local(local):
    """Puente mecanico de lectura completa Alliance; no eleva candidatos a albaranes."""
    from dataclasses import asdict, is_dataclass
    from src.facturas.normalizador_v2.modelos import FacturaNormalizada
    from src.facturas.normalizador_v2.validadores import ContextoValidacion, validar_factura

    def serializar(value):
        if is_dataclass(value):
            return serializar(asdict(value))
        if isinstance(value, dict):
            return {k: serializar(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [serializar(v) for v in value]
        if isinstance(value, Decimal):
            return str(value)
        return value

    def campo(value, fecha=False):
        if not value or value.get("valor") is None or not value.get("evidencias"):
            return None
        val = value["valor"]
        if fecha:
            val = {"iso": str(val), "literal": str(value["literal"])}
        return {"valor": val, "literal": str(value["literal"]), "evidencia": [
            {"pagina": e.pagina, "literal": e.literal, "ubicacion": serializar(e)}
            for e in value["evidencias"]]}

    if local.documento.get("layout") != "alliance-local":
        raise ValueError("ADAPTADOR_MULTIFACTURA_NO_CERTIFICADO")
    facturas = []
    for raw in local.facturas:
        h = raw["cabecera"]
        start, end = raw["segmento"]["paginas"]
        audits = raw["segmento"].get("evidencias", [])
        pags = [e.get("paginacion") or {} for e in audits]
        complete = (len(pags) == end-start+1 and
                    [p.get("current") for p in pags] == list(range(1,len(pags)+1)) and
                    all(p.get("total") == len(pags) for p in pags) and
                    not any(i.get("bloqueante") for i in raw.get("incidencias", [])))
        third = lambda key: {k: campo(v) for k,v in (h.get(key) or {}).items() if k in {"nombre","nif","direccion"}}
        related_movements = {
            relation["movimiento"]["identidad"]["valor"]
            for relation in raw.get("relaciones_documentales", [])
            if relation.get("inequivoca") is True
        }
        independent_movements = [m for m in raw.get("movimientos", [])
            if m["descripcion_literal"]["valor"] not in related_movements]
        projected_movements = [*raw.get("operaciones_economicas", []), *independent_movements]
        movements = [{"orden":index, "tipo":m["categoria"],
                      "descripcion_literal":campo(m["descripcion_literal"]), "sentido":m.get("sentido"),
                      **{k:campo(m.get(source)) for k,source in [("base","base"),("iva","iva"),("recargo_equivalencia","recargo"),("importe","importe")]}}
                     for index,m in enumerate(projected_movements,1)]
        f = {
            "factura_id":"por-calcular", "tipo_documento":campo(h.get("tipo_documento")),
            "naturaleza_principal":"MIXTA" if movements else "MERCANCIA",
            "estado_validacion":"REQUIERE_REVISION", "requiere_conciliacion_albaranes":True,
            "pagina_inicio":start, "pagina_fin":end,
            "proveedor":third("proveedor"), "destinatario":third("destinatario"),
            "numero_factura":campo(h.get("numero_factura")), "fecha_factura":campo(h.get("fecha_factura"),True),
            "totales":{k:campo(h.get(source)) for k,source in [
                ("base_imponible","base_imponible_total"),("iva","iva_total"),
                ("recargo_equivalencia","recargo_equivalencia_total"),("total","importe_total"),("otros","otros_total")]},
            "impuestos":[{"orden":i["orden"],**{k:campo(i.get(k)) for k in ["base","tipo_iva","cuota_iva","tipo_recargo_equivalencia","cuota_recargo_equivalencia","total_tramo"]}} for i in raw.get("impuestos",[])],
            "vencimientos":[{"orden":i["orden"],"fecha":campo(i.get("fecha"),True),"importe":campo(i.get("importe"))} for i in raw.get("vencimientos",[])],
            "albaranes":[{"orden":a["orden"], "numero":campo(a.get("numero_albaran")),
                "fecha":campo(a.get("fecha"),True), "sentido":(a.get("sentido") or {}).get("valor"),
                "tipo_pedido":campo(a.get("tipo_pedido")), "importe_base":campo(a.get("base")),
                "importe_total":campo(a.get("total"))} for a in raw.get("albaranes",[])],
            "movimientos_comerciales":movements,
            "validaciones":[{"codigo":"ADAPTACION_MULTIFACTURA_LOCAL", "resultado":"OK",
                "descripcion":"Adaptacion mecanica conservando extraccion y provenance",
                "regla_version":"multifactura-local-1"}],
            "incidencias":[{"codigo":i["codigo"],"severidad":"ERROR" if i.get("bloqueante") else "AVISO",
                "descripcion":i.get("motivo",i["codigo"]),"bloqueante":bool(i.get("bloqueante")),"paginas":list(range(start,end+1))} for i in raw.get("incidencias",[])],
        }
        # Cabeceras repetidas prueban el mismo vencimiento, no varios cobros.
        # Se conservan todas las evidencias y todas las filas crudas.
        vencimientos = []
        for v in f["vencimientos"]:
            prior = next((x for x in vencimientos if x["fecha"] and v["fecha"]
                and x["fecha"]["valor"] == v["fecha"]["valor"]
                and x["importe"] is None and v["importe"] is None), None)
            if prior:
                prior["fecha"]["evidencia"].extend(v["fecha"]["evidencia"])
            else:
                v["orden"] = len(vencimientos) + 1
                vencimientos.append(v)
        f["vencimientos"] = vencimientos
        model = FacturaNormalizada.model_validate(f)
        evaluation = validar_factura(model, ContextoValidacion(numero_paginas=local.documento["pages"]))
        f = model.model_copy(update={"estado_validacion":evaluation.estado,
            "incidencias":list(evaluation.incidencias),"validaciones":list(evaluation.validaciones),
            "discrepancias_documentales":list(evaluation.discrepancias)}).model_dump(mode="json")
        f.update(factura_completa_demostrada=complete,
            provenance={"segment_id":f"paginas-{start}-{end}","paginas":list(range(start,end+1)),
                        "segmento":serializar(raw["segmento"])},
            extraccion_local=serializar(raw))
        facturas.append(f)
    doc={"documento_completo_demostrado":local.documento_completo_demostrado,
         "numero_paginas":local.documento["pages"],"facturas":facturas,
         "metadata_tecnica":{"version_normalizador":"multifactura-local-1", "documento":serializar(local.documento)}}
    return preparar_documento(doc,[])['resultado_json']
