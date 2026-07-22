from src.database.conexion_sql import obtener_conexion
from src.sql_explorer.seguridad_sql import validar_consulta_lectura


def buscar_columnas(texto: str) -> list[dict]:

    consulta = f"""
    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME,
        DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE COLUMN_NAME LIKE '%{texto}%'
    ORDER BY
        TABLE_NAME,
        ORDINAL_POSITION
    """

    consulta = validar_consulta_lectura(consulta)

    conexion = obtener_conexion()

    try:

        cursor = conexion.cursor()
        cursor.execute(consulta)

        resultados = []

        for fila in cursor.fetchall():

            resultados.append({

                "esquema": fila.TABLE_SCHEMA,
                "tabla": fila.TABLE_NAME,
                "columna": fila.COLUMN_NAME,
                "tipo": fila.DATA_TYPE

            })

        return resultados

    finally:
        conexion.close()


def mostrar_resultados(texto):

    resultados = buscar_columnas(texto)

    print("=" * 90)
    print(f"BÚSQUEDA DE COLUMNAS: {texto}")
    print("=" * 90)

    if not resultados:
        print("No se han encontrado columnas.")
        return

    print(
        f"{'Tabla':<35}"
        f"{'Columna':<35}"
        f"{'Tipo'}"
    )

    print("-" * 90)

    for r in resultados:

        print(
            f"{r['tabla']:<35}"
            f"{r['columna']:<35}"
            f"{r['tipo']}"
        )

    print()
    print(f"Total encontrados: {len(resultados)}")
    print("OK: búsqueda realizada sin modificar SQL Server.")


def ejecutar():

    texto = input("Texto a buscar: ").strip()

    mostrar_resultados(texto)


if __name__ == "__main__":
    ejecutar()