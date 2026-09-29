"""
Lectura común de la entrada interactiva de las herramientas de sql_explorer.

Windows PowerShell 5.1 antepone el BOM UTF-8 (U+FEFF) al texto que canaliza
hacia un ejecutable nativo. ``str.strip()`` no lo elimina porque U+FEFF no es
un espacio, así que la primera lectura llegaba como ``"\\ufeffFamilia"`` y las
búsquedas devolvían cero resultados sin avisar.

Toda lectura interactiva de ``src/sql_explorer`` debe pasar por
``leer_texto``. Un test estático impide volver a usar ``input()`` directamente.
"""

import re


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


def leer_texto(mensaje: str, recortar_espacios: bool = True) -> str:
    """
    Lee una línea con ``input()`` y la devuelve limpia con ``limpiar_texto``.
    """

    return limpiar_texto(
        input(mensaje),
        recortar_espacios=recortar_espacios,
    )
