"""
Herramienta 7 del Explorador SQL de Farmatic.

Permite analizar los valores distintos de una columna y saber
cuántas veces aparece cada uno.

La columna puede seleccionarse escribiendo:
- Su número.
- Su nombre completo.
- Una parte de su nombre, cuando solo exista una coincidencia.

La herramienta:
- Solo ejecuta consultas SELECT.
- Comprueba que la tabla o vista existe.
- Comprueba que la columna existe.
- Agrupa por el valor seleccionado.
- Ordena de mayor a menor frecuencia.
- Limita el resultado para evitar consultas excesivas.
"""

from typing import Any

from src.database.conexion_sql import obtener_conexion
from src.sql_explorer.seguridad_sql import validar_consulta_lectura


LIMITE_PREDETERMINADO = 50
LIMITE_MAXIMO = 500


def proteger_identificador(nombre: str) -> str:
    """
    Protege un identificador de SQL Server.

    El identificador solo se utiliza después de comprobar
    que existe en los metadatos de la base de datos.
    """

    return f"[{nombre.replace(']', ']]')}]"


def localizar_objeto(
    nombre_buscado: str,
) -> tuple[str, str, str] | None:
    """
    Busca una tabla o vista por su nombre.

    Devuelve:
        esquema, nombre real y tipo de objeto.

    Si no existe, devuelve None.
    """

    consulta = """
        SELECT
            TABLE_SCHEMA,
            TABLE_NAME,
            TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE LOWER(TABLE_NAME) = LOWER(?)
        ORDER BY
            CASE
                WHEN TABLE_SCHEMA = 'dbo' THEN 0
                ELSE 1
            END,
            TABLE_SCHEMA;
    """

    validar_consulta_lectura(consulta)

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(consulta, nombre_buscado)

        fila = cursor.fetchone()

        if fila is None:
            return None

        return (
            str(fila.TABLE_SCHEMA),
            str(fila.TABLE_NAME),
            str(fila.TABLE_TYPE),
        )

    finally:
        conexion.close()


def obtener_columnas(
    esquema: str,
    tabla: str,
) -> list[tuple[str, str]]:
    """
    Devuelve las columnas de una tabla o vista junto con su tipo de dato.
    """

    consulta = """
        SELECT
            COLUMN_NAME,
            DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = ?
          AND TABLE_NAME = ?
        ORDER BY ORDINAL_POSITION;
    """

    validar_consulta_lectura(consulta)

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(consulta, esquema, tabla)

        return [
            (
                str(fila.COLUMN_NAME),
                str(fila.DATA_TYPE),
            )
            for fila in cursor.fetchall()
        ]

    finally:
        conexion.close()


def mostrar_columnas(
    columnas: list[tuple[str, str]],
) -> None:
    """
    Muestra las columnas disponibles con su número y tipo.
    """

    print("\nColumnas disponibles:")
    print("-" * 70)

    for numero, (nombre, tipo_dato) in enumerate(
        columnas,
        start=1,
    ):
        print(
            f"{numero:>3}. "
            f"{nombre} "
            f"({tipo_dato})"
        )


def seleccionar_columna(
    columnas: list[tuple[str, str]],
) -> tuple[str, str] | None:
    """
    Permite seleccionar una columna mediante:
    - Número.
    - Nombre completo.
    - Parte del nombre.

    Si una búsqueda parcial encuentra varias coincidencias,
    las muestra y solicita una nueva elección.
    """

    while True:
        seleccion = input(
            "\nColumna que quieres analizar "
            "(número, nombre o parte del nombre): "
        ).strip()

        if not seleccion:
            print("No se ha indicado ninguna columna.")
            return None

        # Selección por número
        if seleccion.isdigit():
            numero = int(seleccion)

            if 1 <= numero <= len(columnas):
                return columnas[numero - 1]

            print(
                f"El número debe estar entre 1 y {len(columnas)}."
            )
            continue

        seleccion_normalizada = seleccion.lower()

        # Coincidencia exacta
        for nombre, tipo_dato in columnas:
            if nombre.lower() == seleccion_normalizada:
                return nombre, tipo_dato

        # Coincidencias parciales
        coincidencias = [
            (nombre, tipo_dato)
            for nombre, tipo_dato in columnas
            if seleccion_normalizada in nombre.lower()
        ]

        if len(coincidencias) == 1:
            nombre, tipo_dato = coincidencias[0]

            print(
                f"Columna seleccionada: "
                f"{nombre} ({tipo_dato})"
            )

            return nombre, tipo_dato

        if len(coincidencias) > 1:
            print(
                "\nSe han encontrado varias columnas:"
            )

            for nombre, tipo_dato in coincidencias:
                numero_real = columnas.index(
                    (nombre, tipo_dato)
                ) + 1

                print(
                    f"{numero_real:>3}. "
                    f"{nombre} "
                    f"({tipo_dato})"
                )

            print(
                "\nEscribe el número o el nombre completo "
                "de una de ellas."
            )
            continue

        print(
            f"No se ha encontrado ninguna columna "
            f"que coincida con '{seleccion}'."
        )


def solicitar_limite() -> int:
    """
    Solicita el número máximo de valores distintos que se mostrarán.
    """

    texto = input(
        f"\nNúmero máximo de valores distintos "
        f"(Enter = {LIMITE_PREDETERMINADO}, "
        f"máximo = {LIMITE_MAXIMO}): "
    ).strip()

    if not texto:
        return LIMITE_PREDETERMINADO

    try:
        limite = int(texto)

    except ValueError:
        print(
            "El límite no es válido. "
            f"Se utilizará {LIMITE_PREDETERMINADO}."
        )
        return LIMITE_PREDETERMINADO

    if limite < 1:
        print(
            "El límite debe ser superior a cero. "
            f"Se utilizará {LIMITE_PREDETERMINADO}."
        )
        return LIMITE_PREDETERMINADO

    if limite > LIMITE_MAXIMO:
        print(
            f"El máximo permitido es {LIMITE_MAXIMO}. "
            f"Se utilizará {LIMITE_MAXIMO}."
        )
        return LIMITE_MAXIMO

    return limite


def construir_consulta(
    esquema: str,
    tabla: str,
    columna: str,
    limite: int,
) -> str:
    """
    Construye una consulta que agrupa por el valor de una columna
    y cuenta cuántas veces aparece cada valor.
    """

    esquema_sql = proteger_identificador(esquema)
    tabla_sql = proteger_identificador(tabla)
    columna_sql = proteger_identificador(columna)

    consulta = f"""
        SELECT TOP ({limite})
            {columna_sql} AS Valor,
            COUNT(*) AS NumeroRegistros
        FROM {esquema_sql}.{tabla_sql}
        GROUP BY {columna_sql}
        ORDER BY
            COUNT(*) DESC,
            {columna_sql} ASC;
    """

    validar_consulta_lectura(consulta)

    return consulta


def obtener_valores(
    consulta: str,
) -> list[tuple[Any, int]]:
    """
    Ejecuta la consulta y devuelve:
    - Valor de la columna.
    - Número de veces que aparece.
    """

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(consulta)

        return [
            (
                fila.Valor,
                int(fila.NumeroRegistros),
            )
            for fila in cursor.fetchall()
        ]

    finally:
        conexion.close()


def contar_registros_totales(
    esquema: str,
    tabla: str,
) -> int:
    """
    Cuenta el número total de registros del objeto.
    """

    esquema_sql = proteger_identificador(esquema)
    tabla_sql = proteger_identificador(tabla)

    consulta = f"""
        SELECT COUNT(*) AS TotalRegistros
        FROM {esquema_sql}.{tabla_sql};
    """

    validar_consulta_lectura(consulta)

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(consulta)

        fila = cursor.fetchone()

        if fila is None:
            return 0

        return int(fila.TotalRegistros)

    finally:
        conexion.close()


def formatear_valor(valor: Any) -> str:
    """
    Convierte un valor SQL a texto legible.
    """

    if valor is None:
        return "<NULL>"

    if isinstance(valor, bytes):
        return f"<datos binarios: {len(valor)} bytes>"

    texto = str(valor)

    if texto == "":
        return "<VACÍO>"

    if len(texto) > 120:
        return texto[:117] + "..."

    return texto


def mostrar_resultados(
    valores: list[tuple[Any, int]],
    total_registros: int,
) -> None:
    """
    Muestra los valores encontrados y su frecuencia.
    """

    if not valores:
        print("\nNo se han encontrado valores.")
        return

    print("\n" + "=" * 90)
    print(
        f"{'N.º':>4}  "
        f"{'VALOR':<60}  "
        f"{'REGISTROS':>10}  "
        f"{'%':>7}"
    )
    print("=" * 90)

    for numero, (valor, cantidad) in enumerate(
        valores,
        start=1,
    ):
        texto_valor = formatear_valor(valor)

        porcentaje = (
            cantidad / total_registros * 100
            if total_registros
            else 0
        )

        print(
            f"{numero:>4}  "
            f"{texto_valor:<60}  "
            f"{cantidad:>10}  "
            f"{porcentaje:>6.2f}%"
        )

    print("=" * 90)


def valores_columna() -> None:
    """
    Ejecuta la herramienta interactiva.
    """

    print("\n" + "=" * 70)
    print("HERRAMIENTA 7 - VALORES DISTINTOS DE UNA COLUMNA")
    print("=" * 70)

    nombre_objeto = input(
        "Nombre de la tabla o vista: "
    ).strip()

    if not nombre_objeto:
        print("No se ha indicado ninguna tabla o vista.")
        return

    objeto = localizar_objeto(nombre_objeto)

    if objeto is None:
        print(
            f"\nNo existe ninguna tabla o vista llamada "
            f"'{nombre_objeto}'."
        )
        return

    esquema, tabla, tipo = objeto

    columnas = obtener_columnas(
        esquema,
        tabla,
    )

    if not columnas:
        print(
            "\nNo se han podido obtener las columnas "
            "del objeto."
        )
        return

    mostrar_columnas(columnas)

    columna = seleccionar_columna(columnas)

    if columna is None:
        return

    columna_real, tipo_dato = columna

    limite = solicitar_limite()

    consulta = construir_consulta(
        esquema=esquema,
        tabla=tabla,
        columna=columna_real,
        limite=limite,
    )

    total_registros = contar_registros_totales(
        esquema,
        tabla,
    )

    valores = obtener_valores(consulta)

    print("\n" + "-" * 70)
    print(f"OBJETO: {esquema}.{tabla}")
    print(f"TIPO: {tipo}")
    print(f"COLUMNA: {columna_real}")
    print(f"TIPO DE DATO: {tipo_dato}")
    print(f"REGISTROS TOTALES: {total_registros}")
    print(f"VALORES MOSTRADOS: {len(valores)}")
    print("-" * 70)

    mostrar_resultados(
        valores,
        total_registros,
    )

    print("\n" + "=" * 70)
    print("FIN DEL ANÁLISIS")
    print("=" * 70)


if __name__ == "__main__":
    try:
        valores_columna()

    except Exception as error:
        print("\nSe ha producido un error:")
        print(error)