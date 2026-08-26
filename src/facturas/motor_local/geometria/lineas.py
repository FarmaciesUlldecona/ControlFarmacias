from __future__ import annotations

import re
import statistics
import unicodedata

from ..modelos import LineaLocal, PalabraLocal


DATE_RE = re.compile(r"^\d{2}[./-]\d{2}[./-]\d{4}$")
MONEY_RE = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}-?$|^-?\d+,\d{2}-?$")


def normalizar_texto(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).upper().split())


def parsear_importe(token: str) -> float | None:
    text = token.strip().replace("€", "")
    trailing = text.endswith("-")
    text = text.rstrip("-")
    if not MONEY_RE.fullmatch(text):
        return None
    value = float(text.replace(".", "").replace(",", "."))
    return -value if trailing else value


def agrupar_por_linea(palabras: list[PalabraLocal], tolerancia_y: float = 1.6) -> list[LineaLocal]:
    grupos: list[list[PalabraLocal]] = []
    anclas: list[float] = []
    for palabra in sorted(palabras, key=lambda p: (p.bbox.y0, p.bbox.x0, p.orden)):
        indice = next((i for i, y in enumerate(anclas) if abs(y - palabra.bbox.y0) <= tolerancia_y), None)
        if indice is None:
            grupos.append([palabra])
            anclas.append(palabra.bbox.y0)
        else:
            grupos[indice].append(palabra)
            anclas[indice] = statistics.fmean(p.bbox.y0 for p in grupos[indice])
    salida = []
    for orden, grupo in enumerate(grupos, 1):
        grupo.sort(key=lambda p: (p.bbox.x0, p.orden))
        salida.append(LineaLocal(grupo[0].pagina, grupo, orden))
    return salida
