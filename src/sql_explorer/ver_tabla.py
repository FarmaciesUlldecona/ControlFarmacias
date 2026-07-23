"""
Herramienta 6 del Explorador SQL de Farmatic.

Permite visualizar una muestra de los registros de una tabla o vista
de SQL Server sin modificar ningún dato.

Características:
- Solo ejecuta consultas SELECT.
- Comprueba que el objeto existe.
- Muestra 20 registros por defecto.
- Permite elegir otro límite, con un máximo de 100.
- Ordena alfabéticamente cuando encuentra una columna de nombre.
- En la tabla Proveedor permite excluir los registros ECO.
- Si no existe una columna de nombre, busca una columna adecuada
  para ordenar los registros.
"""

from typing import Any

from src.database.conexion_sql import obtener_conexion
from src.sql_explorer.seguridad_sql import validar_consulta_lectura


LIMITE_PREDETERMINADO = 20
LIMITE_MAXIMO = 100


def proteger_identificador(nombre: str) -> str:
    """
    Protege un nombre de esquema, tabla o columna para utilizarlo
    de forma segura como identificador de SQL Server.

    El nombre solo se utiliza después de haber sido comprobado
    contra los metadatos de la base de datos.
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
) -> list[str]:
    """
    Obtiene las columnas de una tabla o vista en su orden original.
    """

    consulta = """
        SELECT COLUMN_NAME
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
            str(fila.COLUMN_NAME)
            for fila in cursor.fetchall()
        ]

    finally:
        conexion.close()


def encontrar_columna_nombre(
    columnas: list[str],
) -> str | None:
    """
    Busca una columna que probablemente contenga el nombre
    o la descripción principal del registro.
    """

    preferencias = [
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

    columnas_por_nombre = {
        columna.lower(): columna
        for columna in columnas
    }

    for preferencia in preferencias:
        columna_real = columnas_por_nombre.get(
            preferencia.lower()
        )

        if columna_real:
            return columna_real

    return None


def elegir_columna_ordenacion_automatica(
    columnas: list[str],
) -> str | None:
    """
    Elige automáticamente una columna adecuada para ordenar
    cuando no existe una columna de nombre o descripción.
    """

    preferencias = [
        "IdContador",
        "Fecha",
        "FechaVenta",
        "FechaPedido",
        "FechaAlbaran",
        "FechaFactura",
        "FechaAlta",
        "FechaCreacion",
        "IdProveedor",
        "IdArticulo",
        "IdProducto",
        "IdCliente",
        "IdFactura",
        "IdPedido",
        "IdAlbaran",
        "IdVenta",
        "IdMovimiento",
        "Id",
    ]

    columnas_por_nombre = {
        columna.lower(): columna
        for columna in columnas
    }

    for preferencia in preferencias:
        columna_real = columnas_por_nombre.get(
            preferencia.lower()
        )

        if columna_real:
            return columna_real

    for columna in columnas:
        if columna.lower().startswith("id"):
            return columna

    for columna in columnas:
        if "fecha" in columna.lower():
            return columna

    return None


def solicitar_limite() -> int:
    """
    Solicita el número de registros que se mostrarán.

    Enter:
        20 registros.

    Máximo:
        100 registros.
    """

    texto = input(
        f"Límite de registros "
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
            f"El límite máximo permitido es {LIMITE_MAXIMO}. "
            f"Se utilizarán {LIMITE_MAXIMO} registros."
        )
        return LIMITE_MAXIMO

    return limite


def solicitar_exclusion_eco(
    tabla: str,
    columna_nombre: str | None,
) -> bool:
    """
    Pregunta si deben excluirse los proveedores ECO.

    La pregunta solo aparece cuando:
    - La tabla es Proveedor.
    - Existe una columna de nombre o descripción.
    """

    if tabla.lower() != "proveedor":
        return False

    if columna_nombre is None:
        return False

    respuesta = input(
        "¿Excluir proveedores ECO? (S/N, Enter = S): "
    ).strip().lower()

    if respuesta in {"", "s", "si", "sí"}:
        return True

    return False


def construir_consulta(
    esquema: str,
    tabla: str,
    limite: int,
    columna_nombre: str | None,
    columna_ordenacion: str | None,
    excluir_eco: bool,
) -> tuple[str, list[Any], str]:
    """
    Construye la consulta SELECT que mostrará los registros.

    Devuelve:
        consulta SQL,
        parámetros,
        descripción de la ordenación.
    """

    esquema_sql = proteger_identificador(esquema)
    tabla_sql = proteger_identificador(tabla)

    consulta = (
        f"SELECT TOP ({limite}) * "
        f"FROM {esquema_sql}.{tabla_sql}"
    )

    parametros: list[Any] = []

    if excluir_eco and columna_nombre:
        columna_nombre_sql = proteger_identificador(
            columna_nombre
        )

        consulta += (
            f" WHERE "
            f"UPPER(CAST({columna_nombre_sql} AS NVARCHAR(MAX))) "
            f"NOT LIKE ?"
        )

        parametros.append("%ECO%")

    if columna_nombre:
        columna_sql = proteger_identificador(
            columna_nombre
        )

        consulta += f" ORDER BY {columna_sql} ASC"
        descripcion_orden = f"{columna_nombre} ASC"

    elif columna_ordenacion:
        columna_sql = proteger_identificador(
            columna_ordenacion
        )

        consulta += f" ORDER BY {columna_sql} DESC"
        descripcion_orden = f"{columna_ordenacion} DESC"

    else:
        descripcion_orden = "Sin ordenación automática"

    consulta += ";"

    validar_consulta_lectura(consulta)

    return consulta, parametros, descripcion_orden


def obtener_registros(
    consulta: str,
    parametros: list[Any],
) -> tuple[list[str], list[tuple[Any, ...]]]:
    """
    Ejecuta la consulta de lectura y devuelve:
    - nombres de columnas;
    - registros encontrados.
    """

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(consulta, parametros)

        columnas = [
            descripcion[0]
            for descripcion in cursor.description
        ]

        registros = [
            tuple(fila)
            for fila in cursor.fetchall()
        ]

        return columnas, registros

    finally:
        conexion.close()


def formatear_valor(valor: Any) -> str:
    """
    Convierte un valor SQL a un texto legible.
    """

    if valor is None:
        return "NULL"

    if isinstance(valor, bytes):
        return f"<datos binarios: {len(valor)} bytes>"

    texto = str(valor)

    if len(texto) > 300:
        return texto[:297] + "..."

    return texto


def mostrar_registros(
    columnas: list[str],
    registros: list[tuple[Any, ...]],
) -> None:
    """
    Muestra los registros verticalmente para facilitar
    la lectura de tablas con muchas columnas.
    """

    if not registros:
        print("\nNo se han encontrado registros.")
        return

    for numero, registro in enumerate(
        registros,
        start=1,
    ):
        print("\n" + "=" * 70)
        print(f"REGISTRO {numero}")
        print("=" * 70)

        for columna, valor in zip(
            columnas,
            registro,
        ):
            print(
                f"{columna}: "
                f"{formatear_valor(valor)}"
            )


def ver_tabla() -> None:
    """
    Ejecuta la herramienta interactiva.
    """

    print("\n" + "=" * 70)
    print("HERRAMIENTA 6 - VER TABLA O VISTA")
    print("=" * 70)

    nombre_buscado = input(
        "Nombre de la tabla o vista: "
    ).strip()

    if not nombre_buscado:
        print("No se ha indicado ningún objeto.")
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

    limite = solicitar_limite()

    columna_nombre = encontrar_columna_nombre(
        columnas
    )

    columna_ordenacion = None

    if columna_nombre is None:
        columna_ordenacion = (
            elegir_columna_ordenacion_automatica(
                columnas
            )
        )

    excluir_eco = solicitar_exclusion_eco(
        tabla,
        columna_nombre,
    )

    consulta, parametros, descripcion_orden = (
        construir_consulta(
            esquema=esquema,
            tabla=tabla,
            limite=limite,
            columna_nombre=columna_nombre,
            columna_ordenacion=columna_ordenacion,
            excluir_eco=excluir_eco,
        )
    )

    columnas_resultado, registros = obtener_registros(
        consulta,
        parametros,
    )

    print("\n" + "-" * 70)
    print(f"OBJETO: {esquema}.{tabla}")
    print(f"TIPO: {tipo}")
    print(f"REGISTROS MOSTRADOS: {len(registros)}")
    print(f"ORDENACIÓN: {descripcion_orden}")

    if tabla.lower() == "proveedor":
        if excluir_eco:
            print("PROVEEDORES ECO EXCLUIDOS: Sí")
        else:
            print("PROVEEDORES ECO EXCLUIDOS: No")

    print("-" * 70)

    mostrar_registros(
        columnas_resultado,
        registros,
    )

    print("\n" + "=" * 70)
    print("FIN DE LA CONSULTA")
    print("=" * 70)


if __name__ == "__main__":
    try:
        ver_tabla()

    except Exception as error:
        print("\nSe ha producido un error:")
        print(error)