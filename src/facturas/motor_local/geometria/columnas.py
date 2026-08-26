from __future__ import annotations

from ..modelos import LineaLocal, PalabraLocal, RegionLocal
from .lineas import normalizar_texto


def detectar_encabezados(lineas: list[LineaLocal], etiquetas: list[str]) -> dict[str, RegionLocal]:
    resultado: dict[str, RegionLocal] = {}
    for etiqueta in etiquetas:
        objetivo = normalizar_texto(etiqueta)
        for linea in lineas:
            for palabra in linea.palabras:
                if objetivo in normalizar_texto(palabra.texto):
                    resultado[etiqueta] = palabra.bbox
                    break
            if etiqueta in resultado:
                break
    return resultado


def asignar_a_columnas(
    palabras: list[PalabraLocal], encabezados: dict[str, RegionLocal]
) -> dict[str, list[PalabraLocal]]:
    if not encabezados:
        return {}
    centros = {nombre: (caja.x0 + caja.x1) / 2 for nombre, caja in encabezados.items()}
    resultado = {nombre: [] for nombre in encabezados}
    for palabra in palabras:
        centro = (palabra.bbox.x0 + palabra.bbox.x1) / 2
        distancias = sorted((abs(x - centro), nombre) for nombre, x in centros.items())
        if len(distancias) > 1 and abs(distancias[0][0] - distancias[1][0]) < 1e-6:
            continue
        resultado[distancias[0][1]].append(palabra)
    return resultado
