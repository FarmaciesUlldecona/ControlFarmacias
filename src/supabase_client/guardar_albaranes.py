from typing import Any

from postgrest.exceptions import APIError

from src.supabase_client.conexion_supabase import obtener_cliente_supabase


def guardar_albaran(albaran: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Guarda un albarán en Supabase.

    Si ya existe un registro con la misma farmacia e id_contador,
    no lo vuelve a insertar.
    """

    cliente = obtener_cliente_supabase()

    try:
        respuesta = (
            cliente
            .table("albaranes")
            .insert(albaran)
            .execute()
        )

        return respuesta.data

    except APIError as error:
     if error.code == "23505":
        return []

    raise