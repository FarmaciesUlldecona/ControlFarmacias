from __future__ import annotations

from datetime import datetime

from ..modelos import LineaLocal, PalabraLocal
from .lineas import DATE_RE, normalizar_texto, parsear_importe


def palabras_fecha(linea: LineaLocal) -> list[PalabraLocal]:
    return [palabra for palabra in linea.palabras if DATE_RE.fullmatch(palabra.texto)]


def palabras_importe(linea: LineaLocal) -> list[tuple[PalabraLocal, float]]:
    salida = []
    for palabra in linea.palabras:
        valor = parsear_importe(palabra.texto)
        if valor is not None:
            salida.append((palabra, valor))
    return salida


def fecha_iso(literal: str) -> str | None:
    for formato in ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(literal, formato).date().isoformat()
        except ValueError:
            pass
    return None


def lineas_con_texto(lineas: list[LineaLocal], *fragmentos: str) -> list[LineaLocal]:
    objetivos = [normalizar_texto(fragmento) for fragmento in fragmentos]
    return [
        linea for linea in lineas
        if all(objetivo in normalizar_texto(linea.texto) for objetivo in objetivos)
    ]


def palabras_antes_de(linea: LineaLocal, palabra: PalabraLocal) -> list[PalabraLocal]:
    return [item for item in linea.palabras if item.bbox.x1 <= palabra.bbox.x0]
