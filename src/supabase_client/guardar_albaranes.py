from typing import Any

from postgrest.exceptions import APIError

from src.supabase_client.conexion_supabase import obtener_cliente_supabase


def obtener_ultimo_id_contador(farmacia: str) -> int:
    """
    Devuelve el IdContador más alto almacenado en Supabase
    para la farmacia indicada.
    """

    cliente = obtener_cliente_supabase()

    respuesta = (
        cliente
        .table("albaranes")
        .select("id_contador")
        .eq("farmacia", farmacia)
        .order("id_contador", desc=True)
        .limit(1)
        .execute()
    )

    if not respuesta.data:
        return 0

    return int(respuesta.data[0]["id_contador"])


def guardar_albaran(
    albaran: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Guarda un albarán en Supabase.

    Si ya existe un registro con la misma farmacia e id_contador,
    no vuelve a insertarlo.
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