import os

from dotenv import load_dotenv
from supabase import Client, create_client


load_dotenv()


def obtener_cliente_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    clave = os.getenv("SUPABASE_KEY")

    if not url or not clave:
        raise RuntimeError(
            "Faltan SUPABASE_URL o SUPABASE_KEY en el archivo .env."
        )

    return create_client(url, clave)