from src.database.conexion_sql import obtener_conexion
from src.sql_explorer.seguridad_sql import validar_consulta_lectura


CONSULTA_OBJETOS = """
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA NOT IN ('sys', 'INFORMATION_SCHEMA')
ORDER BY
    TABLE_TYPE,
    TABLE_SCHEMA,
    TABLE_NAME
"""


def obtener_tablas_y_vistas() -> list[dict]:
    """
    Obtiene todas las tablas y vistas disponibles en Farmatic.

    La consulta lee exclusivamente los metadatos de SQL Server.
    No modifica ningún dato ni objeto de la base de datos.
    """

    consulta_segura = validar_consulta_lectura(CONSULTA_OBJETOS)

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(consulta_segura)

        objetos = []

        for fila in cursor.fetchall():
            objetos.append(
                {
                    "esquema": fila.TABLE_SCHEMA,
                    "nombre": fila.TABLE_NAME,
                    "tipo": fila.TABLE_TYPE,
                }
            )

        return objetos

    finally:
        conexion.close()


def mostrar_tablas_y_vistas() -> None:
    """
    Muestra todas las tablas y vistas encontradas y repite
    el resumen al final para que quede visible en la terminal.
    """

    objetos = obtener_tablas_y_vistas()

    tablas = [
        objeto
        for objeto in objetos
        if objeto["tipo"] == "BASE TABLE"
    ]

    vistas = [
        objeto
        for objeto in objetos
        if objeto["tipo"] == "VIEW"
    ]

    print("=" * 70)
    print("INVENTARIO DE OBJETOS DE FARMATIC")
    print("=" * 70)
    print(f"Tablas encontradas: {len(tablas)}")
    print(f"Vistas encontradas: {len(vistas)}")
    print(f"Total de objetos: {len(objetos)}")
    print()

    print("TABLAS")
    print("-" * 70)

    if tablas:
        for tabla in tablas:
            print(f"{tabla['esquema']}.{tabla['nombre']}")
    else:
        print("No se han encontrado tablas.")

    print()
    print("VISTAS")
    print("-" * 70)

    if vistas:
        for vista in vistas:
            print(f"{vista['esquema']}.{vista['nombre']}")
    else:
        print("No se han encontrado vistas.")

    print()
    print("=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)
    print(f"Tablas encontradas: {len(tablas)}")
    print(f"Vistas encontradas: {len(vistas)}")
    print(f"Total de objetos: {len(objetos)}")
    print()
    print("OK: inventario leído sin modificar SQL Server.")


if __name__ == "__main__":
    mostrar_tablas_y_vistas()