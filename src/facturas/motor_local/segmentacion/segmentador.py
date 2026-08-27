from __future__ import annotations

import re

from ..geometria.lineas import normalizar_texto
from ..modelos import DocumentoLocal, SegmentoLocal


INVOICE_FORMAT = re.compile(r"\b(?:VN\d{2,4}-\d{7}|SI\d{2}-\d{5})\b", re.I)


def identidades(text: str) -> list[str]:
    values = [m.group(0) for m in INVOICE_FORMAT.finditer(text)]
    normalized = normalizar_texto(text)
    for pattern in [
        r"(?:NUMERO\s+(?:DE\s+)?FACTURA|FACTURA)\s*[:#]?\s*(\d{8,12})\b",
        r"\bFACTURA\s*\n\s*(\d{8,12})\b",
        r"\bFACTURA\b(?:\s+\S+){0,20}\s+NUMERO\s+(\d{8,12})\b",
        # Cabeceras tabulares donde el literal NUMERO puede perder el acento
        # durante la extraccion de texto, pero la identidad queda anclada por
        # las dos fechas documentales contiguas.
        r"\b(\d{8,12})\s+\d{2}[./-]\d{2}[./-]\d{4}\s+\d{2}[./-]\d{2}[./-]\d{4}\b",
    ]:
        values.extend(m.group(1) for m in re.finditer(pattern, normalized, re.I))
    return list(dict.fromkeys(values))


def segmentar(documento: DocumentoLocal) -> tuple[list[SegmentoLocal], list[dict]]:
    paginas = []
    for pagina in documento.paginas:
        ids = identidades(pagina.texto)
        normal = normalizar_texto(pagina.texto)
        es_resumen_facturacion = any(senal in normal for senal in (
            "RELACIO DE FACTURES",
            "INFORMACIO DE FACTURES",
            "INFORMACIO FACTURES/CARREC",
        ))
        rol = "RESUMEN_MULTI_DOCUMENTO" if es_resumen_facturacion else "DOCUMENTO"
        match = re.search(r"PAGINA\s+(\d+)\s*(?:DE|[-/])\s*(\d+)", normal)
        paginacion = (
            {"current": int(match.group(1)), "total": int(match.group(2)), "literal": match.group(0)}
            if match
            else None
        )
        paginas.append({"pagina": pagina.numero, "identidades": ids, "paginacion": paginacion, "rol": rol})
    activas = [p for p in paginas if p["rol"] == "DOCUMENTO"]
    segmentos: list[SegmentoLocal] = []
    if any(p["paginacion"] for p in activas):
        actual = []
        for pagina in activas:
            if actual and pagina["paginacion"] and pagina["paginacion"]["current"] == 1:
                segmentos.append(_segmento(actual, "REINICIO_PAGINACION_INTERNA"))
                actual = []
            actual.append(pagina)
        if actual:
            segmentos.append(_segmento(actual, "PAGINACION_INTERNA"))
    else:
        for pagina in activas:
            if len(pagina["identidades"]) == 1:
                segmentos.append(_segmento([pagina], "IDENTIDAD_UNICA_DE_PAGINA"))
        if not segmentos and activas:
            segmentos = [_segmento(activas, "SIN_FRONTERA_DEMOSTRABLE", "NO_SEGMENTABLE")]
    return segmentos, paginas


def _segmento(items: list[dict], regla: str, forced: str | None = None) -> SegmentoLocal:
    ids = list(dict.fromkeys(identity for item in items for identity in item["identidades"]))
    pagination = [item["paginacion"] for item in items]
    state = forced or ("DETERMINISTA" if len(ids) == 1 or all(pagination) else "AMBIGUO")
    return SegmentoLocal([items[0]["pagina"], items[-1]["pagina"]], ids[0] if len(ids) == 1 else None, items, state, regla)
