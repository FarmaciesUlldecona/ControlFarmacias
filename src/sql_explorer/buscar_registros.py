"""
Herramienta 8 del Explorador SQL de Farmatic.

Permite buscar registros de cualquier tabla o vista aplicando
un filtro sobre una columna.

Características:
- Solo ejecuta consultas SELECT.
- Comprueba que la tabla o vista exista.
- Permite seleccionar columnas mediante número, nombre completo
  o parte del nombre.
- Admite distintos operadores de búsqueda.
- Permite mostrar todas las columnas o solo algunas.
- Permite elegir la columna y dirección de ordenación.
- Limita el número de resultados para evitar consultas excesivas.
- Muestra los registros verticalmente para facilitar su lectura.

Esta herramienta nunca modifica datos en SQL Server.
"""

from typing import Any

from src.database.conexion_sql import obtener_conexion
from src.sql_explorer.seguridad_sql import validar_consulta_lectura


LIMITE_PREDETERMINADO = 10
LIMITE_MAXIMO = 100


OPERADORES = {
    "1": {
        "nombre": "Igual a",
        "codigo": "igual",
        "necesita_valor": True,
    },
    "2": {
        "nombre": "Distinto de",
        "codigo": "distinto",
        "necesita_valor": True,
    },
    "3": {
        "nombre": "Contiene",
        "codigo": "contiene",
        "necesita_valor": True,
    },
    "4": {
        "nombre": "Empieza por",
        "codigo": "empieza",
        "necesita_valor": True,
    },
    "5": {
        "nombre": "Termina por",
        "codigo": "termina",
        "necesita_valor": True,
    },
    "6": {
        "nombre": "Mayor que",
        "codigo": "mayor",
        "necesita_valor": True,
    },
    "7": {
        "nombre": "Menor que",
        "codigo": "menor",
        "necesita_valor": True,
    },
    "8": {
        "nombre": "Mayor o igual que",
        "codigo": "mayor_igual",
        "necesita_valor": True,
    },
    "9": {
        "nombre": "Menor o igual que",
        "codigo": "menor_igual",
        "necesita_valor": True,
    },
    "10": {
        "nombre": "Es NULL",
        "codigo": "es_null",
        "necesita_valor": False,
    },
    "11": {
        "nombre": "No es NULL",
        "codigo": "no_null",
        "necesita_valor": False,
    },
}


def proteger_identificador(nombre: str) -> str:
    """
    Protege un identificador para utilizarlo de forma segura
    en una consulta de SQL Server.

    El identificador solo se utiliza después de comprobar que
    existe realmente en los metadatos de la base de datos.
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
    Obtiene las columnas de una tabla o vista junto con su tipo.
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
    titulo: str = "Columnas disponibles",
) -> None:
    """
    Muestra las columnas disponibles con su número y tipo.
    """

    print(f"\n{titulo}:")
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


def resolver_columna(
    columnas: list[tuple[str, str]],
    seleccion: str,
) -> tuple[str, str] | None:
    """
    Intenta localizar una columna mediante:
    - Número.
    - Nombre completo.
    - Parte del nombre.

    Devuelve una columna únicamente cuando la coincidencia
    es inequívoca.
    """

    seleccion = seleccion.strip()

    if not seleccion:
        return None

    if seleccion.isdigit():
        numero = int(seleccion)

        if 1 <= numero <= len(columnas):
            return columnas[numero - 1]

        return None

    seleccion_normalizada = seleccion.lower()

    for nombre, tipo_dato in columnas:
        if nombre.lower() == seleccion_normalizada:
            return nombre, tipo_dato

    coincidencias = [
        (nombre, tipo_dato)
        for nombre, tipo_dato in columnas
        if seleccion_normalizada in nombre.lower()
    ]

    if len(coincidencias) == 1:
        return coincidencias[0]

    return None


def buscar_coincidencias_columnas(
    columnas: list[tuple[str, str]],
    seleccion: str,
) -> list[tuple[int, str, str]]:
    """
    Devuelve todas las columnas que coinciden parcialmente
    con el texto indicado.
    """

    seleccion_normalizada = seleccion.strip().lower()

    if not seleccion_normalizada:
        return []

    coincidencias = []

    for numero, (nombre, tipo_dato) in enumerate(
        columnas,
        start=1,
    ):
        if seleccion_normalizada in nombre.lower():
            coincidencias.append(
                (
                    numero,
                    nombre,
                    tipo_dato,
                )
            )

    return coincidencias


def seleccionar_una_columna(
    columnas: list[tuple[str, str]],
    mensaje: str,
) -> tuple[str, str] | None:
    """
    Solicita una columna hasta recibir una selección válida.
    """

    while True:
        seleccion = input(mensaje).strip()

        if not seleccion:
            print("No se ha indicado ninguna columna.")
            return None

        columna = resolver_columna(
            columnas,
            seleccion,
        )

        if columna is not None:
            nombre, tipo_dato = columna

            print(
                f"Columna seleccionada: "
                f"{nombre} ({tipo_dato})"
            )

            return columna

        if seleccion.isdigit():
            print(
                f"El número debe estar entre "
                f"1 y {len(columnas)}."
            )
            continue

        coincidencias = buscar_coincidencias_columnas(
            columnas,
            seleccion,
        )

        if len(coincidencias) > 1:
            print(
                "\nSe han encontrado varias coincidencias:"
            )

            for numero, nombre, tipo_dato in coincidencias:
                print(
                    f"{numero:>3}. "
                    f"{nombre} "
                    f"({tipo_dato})"
                )

            print(
                "\nEscribe el número o el nombre completo "
                "de la columna."
            )
            continue

        print(
            f"No se ha encontrado ninguna columna "
            f"que coincida con '{seleccion}'."
        )


def seleccionar_operador() -> dict[str, Any]:
    """
    Muestra los operadores disponibles y solicita uno.
    """

    print("\nOperadores disponibles:")
    print("-" * 45)

    for numero, operador in OPERADORES.items():
        print(
            f"{numero:>2}. "
            f"{operador['nombre']}"
        )

    while True:
        seleccion = input(
            "\nSelecciona un operador: "
        ).strip()

        operador = OPERADORES.get(seleccion)

        if operador is not None:
            print(
                f"Operador seleccionado: "
                f"{operador['nombre']}"
            )

            return operador

        print(
            "Operador no válido. "
            f"Escribe un número entre 1 y {len(OPERADORES)}."
        )


def solicitar_valor_filtro(
    operador: dict[str, Any],
) -> str | None:
    """
    Solicita el valor que se utilizará en el filtro.

    Los operadores NULL no necesitan valor.
    """

    if not operador["necesita_valor"]:
        return None

    while True:
        valor = input(
            "Valor que quieres buscar: "
        )

        if valor != "":
            return valor

        print(
            "No se ha indicado ningún valor. "
            "Para buscar NULL utiliza los operadores 10 u 11."
        )


def solicitar_limite() -> int:
    """
    Solicita el máximo de registros que se mostrarán.
    """

    texto = input(
        f"\nNúmero máximo de registros "
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
            f"Se utilizarán {LIMITE_PREDETERMINADO} registros."
        )
        return LIMITE_PREDETERMINADO

    if limite < 1:
        print(
            "El límite debe ser superior a cero. "
            f"Se utilizarán {LIMITE_PREDETERMINADO} registros."
        )
        return LIMITE_PREDETERMINADO

    if limite > LIMITE_MAXIMO:
        print(
            f"El máximo permitido es {LIMITE_MAXIMO}. "
            f"Se utilizarán {LIMITE_MAXIMO} registros."
        )
        return LIMITE_MAXIMO

    return limite


def seleccionar_columnas_resultado(
    columnas: list[tuple[str, str]],
) -> list[str]:
    """
    Permite mostrar:
    - Todas las columnas.
    - Una selección de columnas.

    Para seleccionar varias se pueden escribir números o nombres
    separados por comas.

    Ejemplo:
        1, 3, Fecha, ImportePUC
    """

    respuesta = input(
        "\n¿Mostrar todas las columnas? "
        "(S/N, Enter = S): "
    ).strip().lower()

    if respuesta in {"", "s", "si", "sí"}:
        return [
            nombre
            for nombre, _ in columnas
        ]

    mostrar_columnas(
        columnas,
        titulo="Columnas que puedes mostrar",
    )

    while True:
        texto = input(
            "\nEscribe las columnas separadas por comas: "
        ).strip()

        if not texto:
            print(
                "No se ha seleccionado ninguna columna."
            )
            continue

        selecciones = [
            parte.strip()
            for parte in texto.split(",")
            if parte.strip()
        ]

        columnas_elegidas: list[str] = []
        errores: list[str] = []

        for seleccion in selecciones:
            columna = resolver_columna(
                columnas,
                seleccion,
            )

            if columna is None:
                errores.append(seleccion)
                continue

            nombre, _ = columna

            if nombre not in columnas_elegidas:
                columnas_elegidas.append(nombre)

        if errores:
            print(
                "\nNo se han podido identificar "
                "estas columnas:"
            )

            for error in errores:
                print(f"- {error}")

            print(
                "\nUtiliza el número o el nombre completo "
                "cuando haya varias coincidencias."
            )
            continue

        if not columnas_elegidas:
            print(
                "Debes seleccionar al menos una columna."
            )
            continue

        print("\nColumnas que se mostrarán:")

        for nombre in columnas_elegidas:
            print(f"- {nombre}")

        return columnas_elegidas


def encontrar_columna_preferida(
    columnas: list[tuple[str, str]],
) -> tuple[str | None, str]:
    """
    Elige una columna de ordenación automática.

    Prioridad:
    1. Columnas de nombre o descripción, en orden ascendente.
    2. Identificadores crecientes o fechas, en orden descendente.
    """

    nombres = [
        "Nombre",
        "FIS_NOMBRE",
        "Descripcion",
        "Descripción",
        "Denominacion",
        "Denominación",
        "RazonSocial",
        "RazónSocial",
        "NombreComercial",
    ]

    descendentes = [
        "IdContador",
        "Fecha",
        "FechaVenta",
        "FechaPedido",
        "FechaAlbaran",
        "FechaFactura",
        "FechaAlta",
        "FechaCreacion",
        "Id",
    ]

    columnas_por_nombre = {
        nombre.lower(): nombre
        for nombre, _ in columnas
    }

    for preferencia in nombres:
        columna = columnas_por_nombre.get(
            preferencia.lower()
        )

        if columna:
            return columna, "ASC"

    for preferencia in descendentes:
        columna = columnas_por_nombre.get(
            preferencia.lower()
        )

        if columna:
            return columna, "DESC"

    for nombre, _ in columnas:
        if nombre.lower().startswith("id"):
            return nombre, "DESC"

    for nombre, _ in columnas:
        if "fecha" in nombre.lower():
            return nombre, "DESC"

    return None, ""


def seleccionar_ordenacion(
    columnas: list[tuple[str, str]],
) -> tuple[str | None, str, str]:
    """
    Permite elegir cómo ordenar los resultados.

    Opciones:
    - Ordenación automática.
    - Sin ordenar.
    - Elegir una columna.
    """

    columna_automatica, direccion_automatica = (
        encontrar_columna_preferida(columnas)
    )

    print("\nOrdenación:")
    print("-" * 45)

    if columna_automatica:
        print(
            f"1. Automática "
            f"({columna_automatica} "
            f"{direccion_automatica})"
        )
    else:
        print("1. Automática (no disponible)")

    print("2. Sin ordenación")
    print("3. Elegir una columna")

    while True:
        seleccion = input(
            "\nSelecciona una opción "
            "(Enter = automática): "
        ).strip()

        if seleccion in {"", "1"}:
            if columna_automatica:
                descripcion = (
                    f"{columna_automatica} "
                    f"{direccion_automatica}"
                )

                return (
                    columna_automatica,
                    direccion_automatica,
                    descripcion,
                )

            return None, "", "Sin ordenación"

        if seleccion == "2":
            return None, "", "Sin ordenación"

        if seleccion == "3":
            mostrar_columnas(
                columnas,
                titulo="Columnas disponibles para ordenar",
            )

            columna = seleccionar_una_columna(
                columnas,
                "\nColumna para ordenar: ",
            )

            if columna is None:
                continue

            nombre_columna, _ = columna

            while True:
                direccion = input(
                    "Dirección "
                    "(A = ascendente, "
                    "D = descendente, "
                    "Enter = D): "
                ).strip().lower()

                if direccion in {"a", "asc", "ascendente"}:
                    return (
                        nombre_columna,
                        "ASC",
                        f"{nombre_columna} ASC",
                    )

                if direccion in {
                    "",
                    "d",
                    "desc",
                    "descendente",
                }:
                    return (
                        nombre_columna,
                        "DESC",
                        f"{nombre_columna} DESC",
                    )

                print(
                    "Dirección no válida. "
                    "Escribe A o D."
                )

        print(
            "Opción no válida. "
            "Escribe 1, 2 o 3."
        )


def construir_condicion(
    columna: str,
    operador: dict[str, Any],
    valor: str | None,
) -> tuple[str, list[Any]]:
    """
    Construye únicamente la condición WHERE y sus parámetros.
    """

    columna_sql = proteger_identificador(columna)
    codigo = operador["codigo"]

    if codigo == "igual":
        return (
            f"{columna_sql} = ?",
            [valor],
        )

    if codigo == "distinto":
        return (
            f"{columna_sql} <> ?",
            [valor],
        )

    if codigo == "contiene":
        return (
            "UPPER(CAST("
            f"{columna_sql} "
            "AS NVARCHAR(MAX))) LIKE UPPER(?)",
            [f"%{valor}%"],
        )

    if codigo == "empieza":
        return (
            "UPPER(CAST("
            f"{columna_sql} "
            "AS NVARCHAR(MAX))) LIKE UPPER(?)",
            [f"{valor}%"],
        )

    if codigo == "termina":
        return (
            "UPPER(CAST("
            f"{columna_sql} "
            "AS NVARCHAR(MAX))) LIKE UPPER(?)",
            [f"%{valor}"],
        )

    if codigo == "mayor":
        return (
            f"{columna_sql} > ?",
            [valor],
        )

    if codigo == "menor":
        return (
            f"{columna_sql} < ?",
            [valor],
        )

    if codigo == "mayor_igual":
        return (
            f"{columna_sql} >= ?",
            [valor],
        )

    if codigo == "menor_igual":
        return (
            f"{columna_sql} <= ?",
            [valor],
        )

    if codigo == "es_null":
        return (
            f"{columna_sql} IS NULL",
            [],
        )

    if codigo == "no_null":
        return (
            f"{columna_sql} IS NOT NULL",
            [],
        )

    raise ValueError(
        f"Operador desconocido: {codigo}"
    )


def construir_consulta_registros(
    esquema: str,
    tabla: str,
    columnas_resultado: list[str],
    columna_filtro: str,
    operador: dict[str, Any],
    valor: str | None,
    limite: int,
    columna_orden: str | None,
    direccion_orden: str,
) -> tuple[str, list[Any]]:
    """
    Construye la consulta principal que devuelve los registros.
    """

    esquema_sql = proteger_identificador(esquema)
    tabla_sql = proteger_identificador(tabla)

    columnas_sql = ", ".join(
        proteger_identificador(columna)
        for columna in columnas_resultado
    )

    condicion, parametros = construir_condicion(
        columna_filtro,
        operador,
        valor,
    )

    consulta = (
        f"SELECT TOP ({limite}) "
        f"{columnas_sql} "
        f"FROM {esquema_sql}.{tabla_sql} "
        f"WHERE {condicion}"
    )

    if columna_orden:
        columna_orden_sql = proteger_identificador(
            columna_orden
        )

        direccion_segura = (
            "ASC"
            if direccion_orden == "ASC"
            else "DESC"
        )

        consulta += (
            f" ORDER BY "
            f"{columna_orden_sql} "
            f"{direccion_segura}"
        )

    consulta += ";"

    validar_consulta_lectura(consulta)

    return consulta, parametros


def construir_consulta_recuento(
    esquema: str,
    tabla: str,
    columna_filtro: str,
    operador: dict[str, Any],
    valor: str | None,
) -> tuple[str, list[Any]]:
    """
    Construye una consulta para contar todos los registros
    que cumplen el filtro.
    """

    esquema_sql = proteger_identificador(esquema)
    tabla_sql = proteger_identificador(tabla)

    condicion, parametros = construir_condicion(
        columna_filtro,
        operador,
        valor,
    )

    consulta = (
        "SELECT COUNT(*) AS TotalCoincidencias "
        f"FROM {esquema_sql}.{tabla_sql} "
        f"WHERE {condicion};"
    )

    validar_consulta_lectura(consulta)

    return consulta, parametros


def ejecutar_consulta_registros(
    consulta: str,
    parametros: list[Any],
) -> tuple[list[str], list[tuple[Any, ...]]]:
    """
    Ejecuta la consulta principal y devuelve columnas y registros.
    """

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(
            consulta,
            *parametros,
        )

        columnas = [
            str(descripcion[0])
            for descripcion in cursor.description
        ]

        registros = [
            tuple(fila)
            for fila in cursor.fetchall()
        ]

        return columnas, registros

    finally:
        conexion.close()


def ejecutar_consulta_recuento(
    consulta: str,
    parametros: list[Any],
) -> int:
    """
    Ejecuta la consulta de recuento.
    """

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(
            consulta,
            *parametros,
        )

        fila = cursor.fetchone()

        if fila is None:
            return 0

        return int(fila.TotalCoincidencias)

    finally:
        conexion.close()


def formatear_valor(valor: Any) -> str:
    """
    Convierte un valor SQL en texto legible.
    """

    if valor is None:
        return "NULL"

    if isinstance(valor, bytes):
        return (
            f"<datos binarios: "
            f"{len(valor)} bytes>"
        )

    texto = str(valor)

    if texto == "":
        return "<VACÍO>"

    if len(texto) > 300:
        return texto[:297] + "..."

    return texto


def mostrar_registros(
    columnas: list[str],
    registros: list[tuple[Any, ...]],
) -> None:
    """
    Muestra los registros verticalmente.
    """

    if not registros:
        print("\nNo se han encontrado registros.")
        return

    anchura_nombre = max(
        len(columna)
        for columna in columnas
    )

    for numero, registro in enumerate(
        registros,
        start=1,
    ):
        print("\n" + "=" * 80)
        print(f"REGISTRO {numero}")
        print("=" * 80)

        for columna, valor in zip(
            columnas,
            registro,
        ):
            print(
                f"{columna:<{anchura_nombre}} : "
                f"{formatear_valor(valor)}"
            )


def describir_filtro(
    columna: str,
    operador: dict[str, Any],
    valor: str | None,
) -> str:
    """
    Genera una descripción legible del filtro aplicado.
    """

    if operador["necesita_valor"]:
        return (
            f"{columna} "
            f"{operador['nombre']} "
            f"'{valor}'"
        )

    return (
        f"{columna} "
        f"{operador['nombre']}"
    )


def buscar_registros() -> None:
    """
    Ejecuta la Herramienta 8 de forma interactiva.
    """

    print("\n" + "=" * 70)
    print("HERRAMIENTA 8 - BUSCAR REGISTROS POR VALOR")
    print("=" * 70)

    nombre_buscado = input(
        "Nombre de la tabla o vista: "
    ).strip()

    if not nombre_buscado:
        print(
            "No se ha indicado ninguna tabla o vista."
        )
        return

    objeto = localizar_objeto(nombre_buscado)

    if objeto is None:
        print(
            f"\nNo existe ninguna tabla o vista llamada "
            f"'{nombre_buscado}'."
        )
        return

    esquema, tabla, tipo = objeto

    columnas = obtener_columnas(
        esquema,
        tabla,
    )

    if not columnas:
        print(
            "\nEl objeto existe, pero no se han podido "
            "obtener sus columnas."
        )
        return

    mostrar_columnas(columnas)

    columna_filtro = seleccionar_una_columna(
        columnas,
        "\nColumna por la que quieres filtrar "
        "(número, nombre o parte del nombre): ",
    )

    if columna_filtro is None:
        return

    nombre_columna_filtro, tipo_columna_filtro = (
        columna_filtro
    )

    operador = seleccionar_operador()

    valor = solicitar_valor_filtro(
        operador
    )

    limite = solicitar_limite()

    columnas_resultado = seleccionar_columnas_resultado(
        columnas
    )

    (
        columna_orden,
        direccion_orden,
        descripcion_orden,
    ) = seleccionar_ordenacion(columnas)

    consulta_registros, parametros_registros = (
        construir_consulta_registros(
            esquema=esquema,
            tabla=tabla,
            columnas_resultado=columnas_resultado,
            columna_filtro=nombre_columna_filtro,
            operador=operador,
            valor=valor,
            limite=limite,
            columna_orden=columna_orden,
            direccion_orden=direccion_orden,
        )
    )

    consulta_recuento, parametros_recuento = (
        construir_consulta_recuento(
            esquema=esquema,
            tabla=tabla,
            columna_filtro=nombre_columna_filtro,
            operador=operador,
            valor=valor,
        )
    )

    total_coincidencias = ejecutar_consulta_recuento(
        consulta_recuento,
        parametros_recuento,
    )

    columnas_obtenidas, registros = (
        ejecutar_consulta_registros(
            consulta_registros,
            parametros_registros,
        )
    )

    descripcion_filtro = describir_filtro(
        nombre_columna_filtro,
        operador,
        valor,
    )

    print("\n" + "-" * 80)
    print(f"OBJETO: {esquema}.{tabla}")
    print(f"TIPO: {tipo}")
    print(
        f"COLUMNA FILTRADA: "
        f"{nombre_columna_filtro} "
        f"({tipo_columna_filtro})"
    )
    print(f"FILTRO: {descripcion_filtro}")
    print(
        f"COINCIDENCIAS TOTALES: "
        f"{total_coincidencias}"
    )
    print(
        f"REGISTROS MOSTRADOS: "
        f"{len(registros)}"
    )
    print(f"ORDENACIÓN: {descripcion_orden}")
    print(
        "COLUMNAS MOSTRADAS: "
        + ", ".join(columnas_resultado)
    )
    print("-" * 80)

    mostrar_registros(
        columnas_obtenidas,
        registros,
    )

    print("\n" + "=" * 70)
    print("FIN DE LA BÚSQUEDA")
    print("=" * 70)


if __name__ == "__main__":
    try:
        buscar_registros()

    except Exception as error:
        print("\nSe ha producido un error:")
        print(error)