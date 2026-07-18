from config.config import NOMBRE_FARMACIA
from src.database.leer_albaranes import obtener_ultimos_albaranes
from src.models.albaran import Albaran
from src.supabase_client.guardar_albaranes import guardar_albaran
from src.utils.logger import obtener_logger


logger = obtener_logger("sincronizar_albaranes")


def convertir_albaran_para_supabase(
    albaran: Albaran | dict,
) -> dict:
    """
    Convierte un albarán leído desde Farmatic al formato
    que necesita la tabla de albaranes de Supabase.

    Admite temporalmente dos formatos:
    - Objeto Albaran.
    - Diccionario.
    """

    if isinstance(albaran, Albaran):
        id_contador = albaran.id_contador
        id_proveedor = albaran.id_proveedor
        proveedor = albaran.proveedor
        numero_albaran = albaran.id_albaran
        fecha = albaran.fecha
        importe_pvp = albaran.importe_pvp
        importe_puc = albaran.importe_puc
        descuento = albaran.dto

    elif isinstance(albaran, dict):
        id_contador = albaran["id_contador"]
        id_proveedor = albaran["id_proveedor"]
        proveedor = albaran["proveedor"]
        numero_albaran = albaran["id_albaran"]
        fecha = albaran["fecha"]
        importe_pvp = albaran["importe_pvp"]
        importe_puc = albaran["importe_puc"]
        descuento = albaran["dto"]

    else:
        raise TypeError(
            "Formato de albarán no reconocido: "
            f"{type(albaran).__name__}"
        )

    if isinstance(id_proveedor, str):
        id_proveedor = id_proveedor.strip()

    if isinstance(proveedor, str):
        proveedor = proveedor.strip()

    if isinstance(numero_albaran, str):
        numero_albaran = numero_albaran.strip()

    return {
        "farmacia": NOMBRE_FARMACIA,
        "id_contador": int(id_contador),
        "id_proveedor": int(id_proveedor),
        "proveedor": proveedor,
        "numero_albaran": numero_albaran,
        "fecha": fecha.date().isoformat(),
        "importe_pvp": float(importe_pvp),
        "importe_puc": float(importe_puc),
        "descuento": float(descuento),
        "estado": "PENDIENTE",
        "observaciones": None,
    }


def sincronizar_albaranes() -> None:
    """
    Lee los últimos albaranes de Farmatic
    y guarda en Supabase los que todavía no existen.
    """

    logger.info("Configuración: farmacia = %s", NOMBRE_FARMACIA)
    logger.info("Inicio de sincronización de albaranes")

    try:
        albaranes = obtener_ultimos_albaranes()

        if not albaranes:
            logger.warning("No se han encontrado albaranes en Farmatic")
            return

        insertados = 0
        duplicados = 0

        for albaran in albaranes:
            albaran_para_supabase = convertir_albaran_para_supabase(
                albaran
            )

            numero_albaran = albaran_para_supabase[
                "numero_albaran"
            ]

            resultado = guardar_albaran(
                albaran_para_supabase
            )

            if resultado:
                insertados += 1
                logger.info(
                    "Albarán nuevo insertado: %s",
                    numero_albaran,
                )
            else:
                duplicados += 1
                logger.warning(
                    "Albarán ya existente: %s",
                    numero_albaran,
                )

        logger.info(
            "Sincronización terminada | Nuevos: %s | Existentes: %s",
            insertados,
            duplicados,
        )

    except Exception:
        logger.exception(
            "Ha ocurrido un error durante la sincronización de albaranes"
        )
        raise


if __name__ == "__main__":
    sincronizar_albaranes()