from config.config import NOMBRE_FARMACIA
from src.database.leer_albaranes import obtener_nuevos_albaranes
from src.models.albaran import Albaran
from src.supabase_client.guardar_albaranes import (
    guardar_albaran,
    obtener_ultimo_id_contador,
)
from src.utils.logger import obtener_logger


logger = obtener_logger("sincronizar_albaranes")


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


def sincronizar_albaranes() -> None:
    """
    Consulta el último IdContador existente en Supabase,
    lee de Farmatic únicamente los albaranes posteriores
    y guarda los nuevos registros.
    """

    logger.info(
        "Configuración: farmacia = %s",
        NOMBRE_FARMACIA,
    )
    logger.info("Inicio de sincronización de albaranes")

    try:
        ultimo_id_contador = obtener_ultimo_id_contador(
            NOMBRE_FARMACIA
        )

        logger.info(
            "Último IdContador existente en Supabase: %s",
            ultimo_id_contador,
        )

        albaranes = obtener_nuevos_albaranes(
            ultimo_id_contador
        )

        if not albaranes:
            logger.info(
                "No hay albaranes nuevos para sincronizar"
            )
            return

        insertados = 0
        duplicados = 0

        for albaran in albaranes:
            albaran_para_supabase = (
                convertir_albaran_para_supabase(albaran)
            )

            resultado = guardar_albaran(
                albaran_para_supabase
            )

            if resultado:
                insertados += 1

                logger.info(
                    "Albarán nuevo insertado | "
                    "IdContador: %s | Albarán: %s",
                    albaran.id_contador,
                    albaran.id_albaran,
                )
            else:
                duplicados += 1

                logger.warning(
                    "Albarán ya existente | "
                    "IdContador: %s | Albarán: %s",
                    albaran.id_contador,
                    albaran.id_albaran,
                )

        logger.info(
            "Sincronización terminada | "
            "Nuevos: %s | Existentes: %s",
            insertados,
            duplicados,
        )

    except Exception:
        logger.exception(
            "Ha ocurrido un error durante "
            "la sincronización de albaranes"
        )
        raise


if __name__ == "__main__":
    sincronizar_albaranes()