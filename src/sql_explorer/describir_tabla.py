from src.database.conexion_sql import obtener_conexion
from src.sql_explorer.seguridad_sql import validar_consulta_lectura


def obtener_columnas(nombre_tabla: str) -> list[dict]:

    consulta = f"""
    SELECT
        ORDINAL_POSITION,
        COLUMN_NAME,
        DATA_TYPE,
        CHARACTER_MAXIMUM_LENGTH,
        IS_NULLABLE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = '{nombre_tabla}'
    ORDER BY ORDINAL_POSITION
    """

    consulta = validar_consulta_lectura(consulta)

    conexion = obtener_conexion()

    try:

        cursor = conexion.cursor()
        cursor.execute(consulta)

        columnas = []

        for fila in cursor.fetchall():

            columnas.append({
                "posicion": fila.ORDINAL_POSITION,
                "nombre": fila.COLUMN_NAME,
                "tipo": fila.DATA_TYPE,
                "longitud": fila.CHARACTER_MAXIMUM_LENGTH,
                "nulos": fila.IS_NULLABLE
            })

        return columnas

    finally:
        conexion.close()


def mostrar_tabla(nombre_tabla: str):

    columnas = obtener_columnas(nombre_tabla)

    print("=" * 90)
    print(f"TABLA: {nombre_tabla}")
    print("=" * 90)

    if not columnas:
        print("No existe esa tabla.")
        return

    print(
        f"{'Nº':<4}"
        f"{'Columna':<35}"
        f"{'Tipo':<20}"
        f"{'Long.':<10}"
        f"{'NULL'}"
    )

    print("-" * 90)

    for c in columnas:

        longitud = "" if c["longitud"] is None else c["longitud"]

        print(
            f"{c['posicion']:<4}"
            f"{c['nombre']:<35}"
            f"{c['tipo']:<20}"
            f"{str(longitud):<10}"
            f"{c['nulos']}"
        )

    print()
    print(f"Total columnas: {len(columnas)}")
    print("OK: información obtenida sin modificar SQL Server.")


def ejecutar():

    tabla = input("Nombre de la tabla: ").strip()

    mostrar_tabla(tabla)


if __name__ == "__main__":
    ejecutar()