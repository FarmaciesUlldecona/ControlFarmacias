from __future__ import annotations

import json
from pathlib import Path

from src.models.factura import PatronFacturas


RUTA_PROYECTO = Path(__file__).resolve().parents[2]

RUTA_PATRON_OFICIAL = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "patron"
    / "pruebas_lectura_facturas_resultado_esperado_PATRON_OFICIAL_v1_0.json"
)


def cargar_patron(
    ruta_patron: Path | str = RUTA_PATRON_OFICIAL,
) -> PatronFacturas:
    """
    Carga el patrón oficial desde un archivo JSON y lo convierte
    al modelo común normalizado.
    """
    ruta = Path(ruta_patron)

    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encuentra el patrón oficial: {ruta}"
        )

    if not ruta.is_file():
        raise ValueError(
            f"La ruta del patrón no corresponde a un archivo: {ruta}"
        )

    try:
        with ruta.open(
            mode="r",
            encoding="utf-8",
        ) as archivo:
            datos = json.load(archivo)

    except json.JSONDecodeError as error:
        raise ValueError(
            f"El patrón contiene un JSON inválido. "
            f"Línea {error.lineno}, columna {error.colno}: "
            f"{error.msg}"
        ) from error

    except OSError as error:
        raise OSError(
            f"No se ha podido leer el patrón oficial: {ruta}"
        ) from error

    if not isinstance(datos, dict):
        raise ValueError(
            "La raíz del patrón debe ser un objeto JSON."
        )

    try:
        patron = PatronFacturas.desde_diccionario(datos)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"No se ha podido convertir el patrón al modelo común: "
            f"{error}"
        ) from error

    return patron


def validar_patron(
    patron: PatronFacturas,
) -> list[str]:
    """
    Ejecuta todas las validaciones estructurales del patrón.
    """
    return patron.validar()


def mostrar_resumen(
    patron: PatronFacturas,
) -> None:
    """
    Muestra un resumen básico del patrón cargado.
    """
    print("PATRÓN OFICIAL CARGADO")
    print("----------------------")
    print(f"Versión: {patron.version_patron}")
    print(f"Farmacia: {patron.farmacia}")
    print(f"Moneda: {patron.moneda}")
    print(f"Archivos: {patron.total_archivos()}")
    print(f"Facturas y abonos: {patron.total_facturas()}")


def ejecutar_comprobacion() -> None:
    """
    Carga el patrón oficial, muestra el resumen y ejecuta
    las validaciones estructurales.
    """
    print(f"Ruta del patrón: {RUTA_PATRON_OFICIAL}")
    print()

    patron = cargar_patron()
    mostrar_resumen(patron)

    errores = validar_patron(patron)

    print()
    print("VALIDACIÓN")
    print("----------")

    if errores:
        print(
            f"Se han encontrado {len(errores)} errores "
            f"estructurales:"
        )

        for numero, error in enumerate(errores, start=1):
            print(f"{numero}. {error}")

        raise SystemExit(1)

    print("Patrón válido. No se han encontrado errores estructurales.")


if __name__ == "__main__":
    ejecutar_comprobacion()