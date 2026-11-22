"""Excel de cashflow FICTICIO para los tests del hito 38-B (ningun dato real en el repositorio; DISENO §7.3).

Misma forma que el Excel verificado (DISENO §1): hojas PIO (con tilde), RITA y SL; decenas desde la columna D con
inicio (fila 2) y fin (fila 3) como fechas, una columna TOTAL entre medias; categoria en la columna A y concepto en
la B; filas de saldo localizadas por el texto de la B; hoja de plantilla Banco_4 con formulas sin importes y una hoja
no listada. openpyxl no calcula formulas: ``guardar`` inyecta en el XML el valor guardado de las celdas indicadas.

Cuadre (E1: saldo inicial + RE - RS = saldo segun formulas, con el signo de la celda):
- PIO, D: 500 + 1000 - 300 - (-50) = 1250 (formula guardada); E: 1250 + 200,10 = 1450,10; F: sin importes, bancos
  1449 (E7); H (febrero): 1450,10 - 100 = 1350,10.
- RITA, D: 100 + 200 = 300 (bancos 299, E7); E y F sin importes; H: 300 + 50,50 = 350,50.
- SL: D sin saldo ni importes (E5); E, F y H a 0.
Total: 7 importes (PIO 5, RITA 2) y 11 saldos (PIO 4, RITA 4, SL 3).
"""
from __future__ import annotations

import copy
import datetime as dt
import re
import zipfile
from pathlib import Path

HOJA_PIO = "P" + chr(0xCD) + "O"


class Texto(str):
    """Texto literal aunque empiece por '=' (openpyxl lo tomaria por formula): como las celdas '=' del Excel real."""
COLUMNAS = {"D": (dt.datetime(2026, 1, 1), dt.datetime(2026, 1, 10)),
            "E": (dt.datetime(2026, 1, 11), dt.datetime(2026, 1, 20)),
            "F": (dt.datetime(2026, 1, 21), dt.datetime(2026, 1, 31)),
            "H": (dt.datetime(2026, 2, 1), dt.datetime(2026, 2, 10))}
FILA_SI, FILA_SF, FILA_SB = 4, 9, 10
CATEGORIAS = {5: ("RE Cobros ficticios", "Concepto ficticio uno"), 6: ("RS Pagos ficticios", "Concepto ficticio dos"),
              7: ("RS Devoluciones ficticias", "Concepto ficticio tres")}


def _hoja(saldos: dict, importes: dict) -> dict:
    """saldos: {col: (inicial, formulas, bancos)}; importes: {(fila, col): valor}."""
    celdas: dict[str, object] = {"A1": None, "B1": "Concepto"}
    for col, (inicio, fin) in COLUMNAS.items():
        celdas[f"{col}1"] = inicio.strftime("%B")
        celdas[f"{col}2"], celdas[f"{col}3"] = inicio, fin
    celdas["G1"] = "TOTAL ENERO"
    celdas[f"B{FILA_SI}"] = "Saldo inicial"
    for fila, (categoria, concepto) in CATEGORIAS.items():
        celdas[f"A{fila}"], celdas[f"B{fila}"] = categoria, concepto
        celdas[f"G{fila}"] = f"=SUM(D{fila}:F{fila})"
    celdas["B8"] = "Total movimientos"
    celdas[f"B{FILA_SF}"] = "Saldo final según fórmulas"
    celdas[f"B{FILA_SB}"] = "Saldo final según bancos"
    celdas["B11"] = "Cuadre"
    for col, (si, sf, sb) in saldos.items():
        celdas[f"{col}{FILA_SI}"], celdas[f"{col}{FILA_SF}"], celdas[f"{col}{FILA_SB}"] = si, sf, sb
    for (fila, col), valor in importes.items():
        celdas[f"{col}{fila}"] = valor
    for col in COLUMNAS:
        celdas[f"{col}8"] = f"=SUM({col}5:{col}7)"
        celdas[f"{col}11"] = f"={col}{FILA_SF}-{col}{FILA_SB}"
    return celdas


def libro_base() -> tuple[dict[str, dict], dict[tuple[str, str], object]]:
    """(hojas en orden: nombre -> {celda: valor}, valores guardados de formulas: (hoja, celda) -> valor)."""
    pio = _hoja({"D": (500, "=D4+D5-D6-D7", None), "E": (1250, 1450.1, 1450.1), "F": (1450.1, 1450.1, 1449),
                 "H": (1450.1, 1350.1, None)},
                {(5, "D"): 1000, (6, "D"): 300, (7, "D"): -50, (5, "E"): 200.1, (6, "H"): 100})
    rita = _hoja({"D": (100, 300, 299), "E": (300, 300, None), "F": (300, 300, None), "H": (300, 350.5, None)},
                 {(5, "D"): 200, (5, "H"): 50.5})
    sl = _hoja({"E": (0, 0, None), "F": (0, 0, None), "H": (0, 0, None)}, {})
    plantilla = _hoja({}, {})
    for fila in CATEGORIAS:
        for col in COLUMNAS:
            plantilla[f"{col}{fila}"] = f"=0*{col}{FILA_SI}"
    otra = {"A1": "Hoja no listada", "D5": 12345, "E6": "texto cualquiera"}
    hojas = {HOJA_PIO: pio, "RITA": rita, "SL": sl, "Banco_4": plantilla, "Otra hoja": otra}
    cacheados: dict[tuple[str, str], object] = {(HOJA_PIO, "D9"): 1250}
    for nombre in (HOJA_PIO, "RITA", "SL", "Banco_4"):
        for celda, valor in hojas[nombre].items():
            if isinstance(valor, str) and valor.startswith("=") and (nombre, celda) not in cacheados:
                cacheados[(nombre, celda)] = 0
    return hojas, cacheados


def guardar(ruta: Path, hojas: dict[str, dict], cacheados: dict[tuple[str, str], object]) -> Path:
    import openpyxl

    libro = openpyxl.Workbook()
    libro.remove(libro.active)
    for nombre, celdas in hojas.items():
        ws = libro.create_sheet(nombre)
        for celda, valor in celdas.items():
            if isinstance(valor, Texto):
                ws[celda].value = str(valor)
                ws[celda].data_type = "s"
            elif valor is not None:
                ws[celda] = valor
    ruta.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta)
    _inyectar(ruta, list(hojas), cacheados)
    return ruta


def _inyectar(ruta: Path, nombres: list[str], cacheados: dict[tuple[str, str], object]) -> None:
    """Valor guardado de formulas: <c r="X"><f>..</f><v /></c> -> <c r="X" [t="str"]><f>..</f><v>valor</v></c>."""
    with zipfile.ZipFile(ruta) as z:
        contenido = {n: z.read(n) for n in z.namelist()}
    for (hoja, celda), valor in cacheados.items():
        if hoja not in nombres:  # hoja quitada por el test
            continue
        nombre = f"xl/worksheets/sheet{nombres.index(hoja) + 1}.xml"
        xml = contenido[nombre].decode("utf-8")
        patron = re.compile(rf'<c r="{celda}"( [^>]*)?><f>(.*?)</f><v ?/>(?:</v>)?</c>')
        tipo = ' t="str"' if isinstance(valor, str) else ""
        nuevo, n = patron.subn(lambda m: f'<c r="{celda}"{tipo}><f>{m.group(2)}</f><v>{valor}</v></c>', xml)
        assert n == 1, (hoja, celda)
        contenido[nombre] = nuevo.encode("utf-8")
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for n, datos in contenido.items():
            z.writestr(n, datos)


def excel(carpeta: Path, nombre: str = "CASHFLOW 2026 ficticio.xlsm", cambiar=None) -> Path:
    """Escribe el libro base (o el que devuelva ``cambiar(hojas, cacheados)``) en ``carpeta/nombre``."""
    hojas, cacheados = libro_base()
    if cambiar is not None:
        hojas, cacheados = copy.deepcopy(hojas), dict(cacheados)
        cambiar(hojas, cacheados)
    return guardar(carpeta / nombre, hojas, cacheados)
