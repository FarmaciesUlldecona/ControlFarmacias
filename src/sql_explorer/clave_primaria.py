from src.database.conexion_sql import obtener_conexion
from src.sql_explorer.seguridad_sql import validar_consulta_lectura


def obtener_clave_primaria(nombre_tabla: str) -> list[dict]:
    """
    Obtiene las columnas que forman la clave primaria de una tabla.

    Solo consulta metadatos de SQL Server.
    """

    consulta = """
    SELECT
        tc.TABLE_SCHEMA,
        tc.TABLE_NAME,
        kcu.COLUMN_NAME,
        kcu.ORDINAL_POSITION,
        tc.CONSTRAINT_NAME
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
    INNER JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
        ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
        AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
        AND tc.TABLE_NAME = kcu.TABLE_NAME
    WHERE
        tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        AND tc.TABLE_NAME = ?
    ORDER BY
        kcu.ORDINAL_POSITION
    """

    consulta_segura = validar_consulta_lectura(consulta)

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(consulta_segura, nombre_tabla)

        columnas = []

        for fila in cursor.fetchall():
            columnas.append(
                {
                    "esquema": fila.TABLE_SCHEMA,
                    "tabla": fila.TABLE_NAME,
                    "columna": fila.COLUMN_NAME,
                    "posicion": fila.ORDINAL_POSITION,
                    "restriccion": fila.CONSTRAINT_NAME,
                }
            )

        return columnas

    finally:
        conexion.close()


def mostrar_clave_primaria(nombre_tabla: str) -> None:
    columnas = obtener_clave_primaria(nombre_tabla)

    print("=" * 80)
    print(f"CLAVE PRIMARIA DE: {nombre_tabla}")
    print("=" * 80)

    if not columnas:
        print("No se ha encontrado una clave primaria declarada.")
        print()
        print("OK: metadatos leídos sin modificar SQL Server.")
        return

    print(f"Esquema: {columnas[0]['esquema']}")
    print(f"Tabla: {columnas[0]['tabla']}")
    print(f"Restricción: {columnas[0]['restriccion']}")
    print()

    print(f"{'Posición':<12}{'Columna'}")
    print("-" * 80)

    for columna in columnas:
        print(
            f"{columna['posicion']:<12}"
            f"{columna['columna']}"
        )

    print()
    print(f"Columnas en la clave primaria: {len(columnas)}")
    print("OK: metadatos leídos sin modificar SQL Server.")


def ejecutar() -> None:
    nombre_tabla = input("Nombre de la tabla: ").strip()

    if not nombre_tabla:
        print("Debes introducir un nombre de tabla.")
        return

    mostrar_clave_primaria(nombre_tabla)


if __name__ == "__main__":
    ejecutar()