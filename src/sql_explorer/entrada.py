"""
Lectura común de la entrada interactiva de las herramientas de sql_explorer.

Windows PowerShell 5.1 antepone el BOM UTF-8 (U+FEFF) al texto que canaliza
hacia un ejecutable nativo. ``str.strip()`` no lo elimina porque U+FEFF no es
un espacio, así que la primera lectura llegaba como ``"\\ufeffFamilia"`` y las
búsquedas devolvían cero resultados sin avisar.

Toda lectura interactiva de ``src/sql_explorer`` debe pasar por
``leer_texto``. Un test estático impide volver a usar ``input()`` directamente.

Cuando la entrada llega por tubería, Python decodifica ``sys.stdin`` con la
codificación del sistema (cp1252) salvo que ``PYTHONUTF8`` o
``PYTHONIOENCODING`` digan otra cosa. El BOM llegaba entonces como ``"ï»¿"`` y
no se eliminaba. Por eso, con la entrada estándar real redirigida, se leen los
bytes de ``sys.stdin.buffer`` y se decodifican siempre con ``utf-8-sig``.
"""

import re
import sys


_EXTREMOS_BOM_Y_ESPACIOS = re.compile(r"^[\s﻿]+|[\s﻿]+$")
_EXTREMOS_BOM = re.compile(r"^﻿+|﻿+$")


def limpiar_texto(texto: str, recortar_espacios: bool = True) -> str:
    """
    Elimina U+FEFF y los espacios de ambos extremos del texto.

    El interior del texto no se modifica. Con ``recortar_espacios=False``
    solo se elimina U+FEFF de los extremos y se conservan los espacios,
    para lecturas en las que un espacio puede ser significativo.
    """

    if recortar_espacios:
        return _EXTREMOS_BOM_Y_ESPACIOS.sub("", texto)

    return _EXTREMOS_BOM.sub("", texto)


def _entrada_redirigida() -> bool:
    """
    Indica si la entrada estándar real del proceso llega por tubería o archivo.

    Si ``sys.stdin`` se ha sustituido (por ejemplo, pytest) o es una consola,
    se mantiene ``input()``.
    """

    entrada = sys.stdin

    if entrada is None or entrada is not sys.__stdin__:
        return False

    if not hasattr(entrada, "buffer"):
        return False

    try:
        return not entrada.isatty()
    except (OSError, ValueError):
        return False


def _leer_linea_redirigida(mensaje: str) -> str:
    """
    Lee una línea en bytes de ``sys.stdin.buffer`` y la decodifica con
    ``utf-8-sig``, sin el fin de línea final. Imita a ``input()``: escribe el
    mensaje y lanza ``EOFError`` al final de la entrada.
    """

    if mensaje:
        sys.stdout.write(mensaje)
        sys.stdout.flush()

    datos = sys.stdin.buffer.readline()

    if not datos:
        raise EOFError

    texto = datos.decode("utf-8-sig")

    if texto.endswith("\n"):
        texto = texto[:-1]

    if texto.endswith("\r"):
        texto = texto[:-1]

    return texto


def leer_texto(mensaje: str, recortar_espacios: bool = True) -> str:
    """
    Lee una línea y la devuelve limpia con ``limpiar_texto``.

    Con la entrada redirigida se usa ``_leer_linea_redirigida``; en consola,
    ``input()``.
    """

    if _entrada_redirigida():
        texto = _leer_linea_redirigida(mensaje)
    else:
        texto = input(mensaje)

    return limpiar_texto(
        texto,
        recortar_espacios=recortar_espacios,
    )
