from datetime import date

from config.config import NOMBRE_FARMACIA
from src.database.leer_albaranes import obtener_albaranes_desde_fecha
from src.models.albaran import Albaran
from src.supabase_client.guardar_albaranes import guardar_albaran
from src.utils.logger import obtener_logger


logger = obtener_logger("importar_albaranes_historicos")

FECHA_INICIO = date(2026, 6, 1)


def convertir_albaran_para_supabase(
    albaran: Albaran,
) -> dict:
    """
    Convierte un objeto Albaran leído desde Farmatic
    al formato utilizado por Supabase.
    """

    return {
        "farmacia": NOMBRE_FARMACIA,
        "id_contador": int(albaran.id_contador),
        "id_proveedor": int(albaran.id_proveedor),
        "proveedor": albaran.proveedor.strip(),
        "numero_albaran": albaran.id_albaran.strip(),
        "fecha": albaran.fecha.date().isoformat(),
        "importe_pvp": float(albaran.importe_pvp),
        "importe_puc": float(albaran.importe_puc),
        "descuento": float(albaran.dto),
        "estado": "PENDIENTE",
        "observaciones": None,
    }


def importar_albaranes_historicos() -> None:
    """
    Importa en Supabase todos los albaranes de Farmatic
    con fecha igual o posterior al 01/06/2026.

    Los albaranes ya existentes se ignoran automáticamente.

    Farmatic se utiliza exclusivamente en modo lectura.
    """

    logger.info(
        "Inicio de carga histórica | Farmacia: %s | Fecha: %s",
        NOMBRE_FARMACIA,
        FECHA_INICIO.isoformat(),
    )

    try:
        albaranes = obtener_albaranes_desde_fecha(
            FECHA_INICIO
        )

        total = len(albaranes)

        logger.info(
            "Albaranes encontrados en Farmatic: %s",
            total,
        )

        if not albaranes:
            logger.info(
                "No se han encontrado albaranes para importar"
            )
            return

        insertados = 0
        duplicados = 0

        for posicion, albaran in enumerate(
            albaranes,
            start=1,
        ):
            datos = convertir_albaran_para_supabase(
                albaran
            )

            resultado = guardar_albaran(datos)

            if resultado:
                insertados += 1
            else:
                duplicados += 1

            if posicion % 100 == 0 or posicion == total:
                logger.info(
                    "Progreso: %s/%s | "
                    "Insertados: %s | Existentes: %s",
                    posicion,
                    total,
                    insertados,
                    duplicados,
                )

        logger.info(
            "Carga histórica finalizada | "
            "Procesados: %s | "
            "Insertados: %s | "
            "Existentes: %s",
            total,
            insertados,
            duplicados,
        )

        print()
        print("CARGA HISTORICA FINALIZADA")
        print("--------------------------")
        print(f"Fecha inicial: {FECHA_INICIO:%d/%m/%Y}")
        print(f"Procesados: {total}")
        print(f"Insertados: {insertados}")
        print(f"Ya existentes: {duplicados}")

    except Exception:
        logger.exception(
            "Error durante la carga histórica de albaranes"
        )
        raise


if __name__ == "__main__":
    importar_albaranes_historicos()