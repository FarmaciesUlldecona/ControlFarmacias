from src.supabase_client.conexion_supabase import obtener_cliente_supabase


def main() -> None:
    try:
        cliente = obtener_cliente_supabase()

        respuesta = (
            cliente
            .table("albaranes")
            .select("id")
            .limit(1)
            .execute()
        )

        print("Conexión con Supabase correcta.")
        print(f"Respuesta recibida: {respuesta.data}")

    except Exception as error:
        print("ERROR al conectar con Supabase:")
        print(error)


if __name__ == "__main__":
    main()