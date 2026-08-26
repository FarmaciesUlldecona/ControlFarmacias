from __future__ import annotations

from ..modelos import CeldaLocal, FilaLocal, LineaLocal, TablaLocal, RegionLocal, union_bbox
from .columnas import asignar_a_columnas, detectar_encabezados


def reconstruir_fila(linea: LineaLocal, encabezados: dict[str, RegionLocal], orden: int) -> FilaLocal:
    asignadas = asignar_a_columnas(linea.palabras, encabezados)
    celdas = [
        CeldaLocal(nombre, palabras, union_bbox([p.bbox for p in palabras]) if palabras else None)
        for nombre, palabras in asignadas.items()
    ]
    return FilaLocal(linea.pagina, celdas, linea.texto, linea.bbox, orden)


def detectar_tabla_por_encabezados(
    pagina: int, lineas: list[LineaLocal], etiquetas: list[str], table_id: str
) -> TablaLocal | None:
    encabezados = detectar_encabezados(lineas, etiquetas)
    if len(encabezados) != len(etiquetas):
        return None
    y_header = max(box.y1 for box in encabezados.values())
    filas = [
        reconstruir_fila(linea, encabezados, i)
        for i, linea in enumerate(lineas, 1)
        if linea.bbox.y0 > y_header
    ]
    boxes = list(encabezados.values()) + [fila.bbox for fila in filas]
    return TablaLocal(table_id, pagina, encabezados, filas, union_bbox(boxes))


def zonas_relativas(ancho: float, palabras):
    izquierda, derecha = [], []
    for palabra in palabras:
        (izquierda if (palabra.bbox.x0 + palabra.bbox.x1) / 2 < ancho / 2 else derecha).append(palabra)
    return izquierda, derecha
