import getpass
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from config.config import NOMBRE_FARMACIA
from src.database.leer_albaranes import (
    obtener_albaranes_entre_fechas,
    obtener_albaranes_por_contadores,
    obtener_nuevos_albaranes,
    obtener_nuevos_albaranes_con_recepcion,
)
from src.models.albaran import Albaran, conservar_id_proveedor
from src.supabase_client import resincronizacion_albaranes as resync
from src.supabase_client.conexion_supabase import obtener_cliente_supabase
from src.supabase_client.guardar_albaranes import (
    guardar_albaran,
    obtener_ultimo_id_contador,
)
from src.utils.logger import obtener_logger


logger = obtener_logger("sincronizar_albaranes")

# 2BD: códigos de salida. 0 = todo bien; 2 = nuevos sincronizados, resincronización con errores.
CODIGO_OK = 0
CODIGO_RESYNC_CON_ERRORES = 2


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
        "id_proveedor": conservar_id_proveedor(albaran.id_proveedor),
        "proveedor": albaran.proveedor.strip(),
        "numero_albaran": albaran.id_albaran.strip(),
        "fecha": albaran.fecha.date().isoformat(),
        "importe_pvp": float(albaran.importe_pvp),
        "importe_puc": float(albaran.importe_puc),
        "descuento": float(albaran.dto),
        "estado": "PENDIENTE",
        "observaciones": None,
    }


def _sincronizar_nuevos(v2: bool) -> None:
    ultimo_id_contador = obtener_ultimo_id_contador(
        NOMBRE_FARMACIA
    )

    logger.info(
        "Último IdContador existente en Supabase: %s",
        ultimo_id_contador,
    )

    albaranes = (
        obtener_nuevos_albaranes_con_recepcion(ultimo_id_contador)
        if v2
        else obtener_nuevos_albaranes(ultimo_id_contador)
    )

    logger.info(
        "Lectura Farmatic READ_ONLY terminada | Filas posteriores: %s | "
        "Maximo IdContador leido: %s",
        len(albaranes),
        max((item.id_contador for item in albaranes), default=ultimo_id_contador),
    )

    if not albaranes:
        logger.info(
            "No hay albaranes nuevos para sincronizar"
        )
        return

    insertados = 0
    duplicados = 0

    for albaran in albaranes:
        albaran_para_supabase = convertir_albaran_para_supabase(albaran)
        if v2:
            # 2BD: la recepción de cada albarán (AlbaranRecep, proveedor del albarán).
            albaran_para_supabase["id_recepcion"] = albaran.id_recepcion

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


def preparar_resincronizacion(cliente, hoy: date, *, con_recepcion: bool, tolerar_sin_22: bool = False) -> dict:
    """2BD: lee la ventana de Farmatic y de Supabase y construye el plan (sin escribir)."""
    desde = resync.fecha_inicio_ventana(cliente, NOMBRE_FARMACIA, hoy)
    hasta = hoy + timedelta(days=1)
    farmatic = [
        resync.payload_albaran(a, NOMBRE_FARMACIA, con_recepcion=True)
        for a in obtener_albaranes_entre_fechas(desde, hasta)
    ]
    esquema_22 = True
    try:
        supabase = resync.leer_supabase(cliente, NOMBRE_FARMACIA, desde, hasta, con_recepcion=con_recepcion)
        ausentes_abiertos = resync.leer_ausentes_abiertos(cliente, NOMBRE_FARMACIA)
    except Exception:
        if not tolerar_sin_22:
            raise
        # Modo informe antes de desplegar la 22: sin columna id_recepcion ni historial.
        esquema_22 = False
        supabase = resync.leer_supabase(cliente, NOMBRE_FARMACIA, desde, hasta, con_recepcion=False)
        ausentes_abiertos = set()
    if not esquema_22 or not con_recepcion:
        for fila in farmatic:
            fila.pop("id_recepcion", None)
    plan = resync.planificar(farmatic, supabase, ausentes_abiertos)
    if plan.ausentes:
        encontrados = [
            resync.payload_albaran(a, NOMBRE_FARMACIA, con_recepcion=esquema_22 and con_recepcion)
            for a in obtener_albaranes_por_contadores(plan.ausentes)
        ]
        plan = resync.confirmar_ausentes(plan, encontrados, supabase)
    return {"plan": plan, "desde": desde, "hasta": hasta, "esquema_22": esquema_22}


def resincronizar_modificados(hoy: date | None = None) -> dict:
    """2BD: nuevos fuera de la marca de agua, modificados y ausentes de la ventana."""
    cliente = obtener_cliente_supabase()
    datos = preparar_resincronizacion(cliente, hoy or date.today(), con_recepcion=True)
    plan = datos["plan"]
    logger.info(
        "Resincronización | Ventana desde: %s | Nuevos: %s | Cambios: %s | Reaparecidos: %s | "
        "Ausentes: %s | Iguales: %s",
        datos["desde"], len(plan.nuevos), len(plan.cambios), len(plan.reaparecidos),
        len(plan.ausentes), plan.iguales,
    )
    resumen = resync.ejecutar_plan(
        cliente, plan, NOMBRE_FARMACIA, origen=resync.ORIGEN_VENTANA,
        ejecucion_id=resync.nueva_ejecucion_id("resync"), registrar=logger.warning,
    )
    logger.info(
        "Resincronización terminada | Insertados: %s | Actualizados: %s | Revisiones: %s | "
        "Ausentes registrados: %s | Errores: %s",
        resumen["insertados"], resumen["actualizados"], resumen["revisiones"],
        resumen["ausentes_registrados"], len(resumen["errores"]),
    )
    for error in resumen["errores"]:
        logger.error("Error de resincronización | %s", error)
    return resumen


def sincronizar_albaranes() -> int:
    """
    Consulta el último IdContador existente en Supabase,
    lee de Farmatic únicamente los albaranes posteriores
    y guarda los nuevos registros.

    2BD (solo con CONTROLFARMACIAS_ALBARANES_V2=1, tras desplegar la migración 22): guarda
    también la recepción y después resincroniza los albaranes modificados de la ventana.
    Un fallo de la resincronización no deshace los nuevos: devuelve código 2.
    """

    v2 = resync.activada()

    logger.info(
        "Configuración: farmacia = %s",
        NOMBRE_FARMACIA,
    )
    logger.info("Inicio de sincronización de albaranes")

    logger.info("Principal Windows efectivo: %s", getpass.getuser())

    try:
        _sincronizar_nuevos(v2)
    except Exception:
        logger.exception(
            "Ha ocurrido un error durante "
            "la sincronización de albaranes"
        )
        raise

    if not v2:
        return CODIGO_OK

    try:
        resumen = resincronizar_modificados()
    except Exception:
        logger.exception("Error en la resincronización de albaranes modificados")
        return CODIGO_RESYNC_CON_ERRORES
    return CODIGO_RESYNC_CON_ERRORES if resumen["errores"] else CODIGO_OK


def generar_informe(salida: Path, hoy: date | None = None) -> dict:
    """2BD: modo informe. Lee Farmatic y Supabase y escribe el plan en ``salida``; no escribe en
    ninguna base de datos. Funciona también antes de desplegar la migración 22."""
    cliente = obtener_cliente_supabase()
    datos = preparar_resincronizacion(cliente, hoy or date.today(), con_recepcion=True, tolerar_sin_22=True)
    try:
        reservas = resync.leer_reservas(cliente, NOMBRE_FARMACIA)
    except Exception:
        reservas = {}
    contenido = resync.informe(datos["plan"], reservas, desde=datos["desde"], hasta=datos["hasta"],
                               esquema_22=datos["esquema_22"])
    contenido["farmacia"] = NOMBRE_FARMACIA
    salida.write_text(json.dumps(contenido, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    logger.info("Informe de resincronización (sin escritura) | %s | %s", salida, contenido["resumen"])
    return contenido


def main(argumentos: list[str]) -> int:
    if argumentos[:1] == ["--informe"]:
        if len(argumentos) != 2:
            raise SystemExit("Uso: --informe <salida.json> (fuera del repositorio)")
        raiz = Path(__file__).resolve().parents[1]
        generar_informe(resync.ruta_fuera_del_repositorio(argumentos[1], raiz))
        return CODIGO_OK
    return sincronizar_albaranes()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
