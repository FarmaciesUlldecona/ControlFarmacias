from src.database.conexion_sql import obtener_conexion
from src.utils.logger import obtener_logger


logger = obtener_logger("explorar_base_datos")


def obtener_tablas_y_vistas() -> tuple[list[tuple], list[tuple]]:
    """
    Obtiene todas las tablas y vistas disponibles
    en la base de datos Farmatic.
    """

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()

        cursor.execute(
            """
            SELECT
                SCHEMA_NAME(schema_id) AS esquema,
                name AS nombre
            FROM sys.tables
            ORDER BY esquema, nombre
            """
        )
        tablas = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                SCHEMA_NAME(schema_id) AS esquema,
                name AS nombre
            FROM sys.views
            ORDER BY esquema, nombre
            """
        )
        vistas = cursor.fetchall()

        return tablas, vistas

    finally:
        conexion.close()


def mostrar_inventario() -> None:
    """
    Muestra por pantalla las tablas y vistas encontradas.
    """

    logger.info("Inicio de exploración de la base de datos")

    tablas, vistas = obtener_tablas_y_vistas()

    print()
    print("=" * 60)
    print("TABLAS ENCONTRADAS:", len(tablas))
    print("=" * 60)

    for esquema, nombre in tablas:
        print(f"{esquema}.{nombre}")

    print()
    print("=" * 60)
    print("VISTAS ENCONTRADAS:", len(vistas))
    print("=" * 60)

    for esquema, nombre in vistas:
        print(f"{esquema}.{nombre}")

    logger.info(
        "Exploración terminada | Tablas: %s | Vistas: %s",
        len(tablas),
        len(vistas),
    )


if __name__ == "__main__":
    mostrar_inventario()