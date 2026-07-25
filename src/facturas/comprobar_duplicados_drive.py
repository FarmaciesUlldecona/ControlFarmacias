import hashlib
from collections import defaultdict
from datetime import date
from pathlib import Path

from src.facturas.importar_facturas_drive import (
    FECHA_INICIO_IMPORTACION,
    RUTA_FACTURAS,
    obtener_facturas_pdf,
)


def calcular_hash_archivo(ruta_archivo: Path) -> str:
    """
    Calcula el hash SHA-256 de un archivo.
    """

    calculador = hashlib.sha256()

    with ruta_archivo.open("rb") as archivo:
        while True:
            bloque = archivo.read(1024 * 1024)

            if not bloque:
                break

            calculador.update(bloque)

    return calculador.hexdigest()


def comprobar_duplicados() -> None:
    """
    Agrupa los PDF por contenido y muestra los archivos repetidos.

    No modifica Drive.
    No modifica Supabase.
    """

    print()
    print("COMPROBACION DE PDF DUPLICADOS")
    print("------------------------------")
    print(f"Carpeta raiz: {RUTA_FACTURAS}")
    print(
        "Fecha inicial: "
        f"{FECHA_INICIO_IMPORTACION:%d/%m/%Y}"
    )
    print()

    facturas = obtener_facturas_pdf()

    archivos_por_hash: dict[str, list[Path]] = defaultdict(list)

    for posicion, ruta_pdf in enumerate(
        facturas,
        start=1,
    ):
        ruta_relativa = ruta_pdf.relative_to(RUTA_FACTURAS)

        print(
            f"[{posicion}/{len(facturas)}] "
            f"Analizando: {ruta_relativa}"
        )

        archivo_hash = calcular_hash_archivo(ruta_pdf)

        archivos_por_hash[archivo_hash].append(ruta_pdf)

    grupos_duplicados = {
        archivo_hash: rutas
        for archivo_hash, rutas in archivos_por_hash.items()
        if len(rutas) > 1
    }

    total_archivos = len(facturas)
    total_pdf_unicos = len(archivos_por_hash)
    archivos_repetidos = total_archivos - total_pdf_unicos

    print()
    print("RESULTADO")
    print("---------")
    print(f"Archivos encontrados: {total_archivos}")
    print(f"PDF únicos: {total_pdf_unicos}")
    print(f"Archivos repetidos: {archivos_repetidos}")
    print(
        "Grupos con contenido duplicado: "
        f"{len(grupos_duplicados)}"
    )

    if not grupos_duplicados:
        print()
        print("No se han encontrado PDF duplicados.")
        return

    print()
    print("PDF DUPLICADOS")
    print("--------------")

    for numero_grupo, (
        archivo_hash,
        rutas,
    ) in enumerate(
        grupos_duplicados.items(),
        start=1,
    ):
        print()
        print(
            f"Grupo {numero_grupo} | "
            f"Hash: {archivo_hash[:16]}..."
        )

        for ruta in rutas:
            print(
                "- "
                f"{ruta.relative_to(RUTA_FACTURAS)}"
            )

    print()
    print("Comprobación finalizada.")
    print("No se ha modificado ningún archivo ni registro.")


if __name__ == "__main__":
    comprobar_duplicados()