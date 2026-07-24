"""
Analizador automático de tablas de Farmatic.

La herramienta recibe el nombre de una tabla y genera un informe con:

- Información general.
- Número aproximado de registros.
- Columnas y tipos de datos.
- Clave primaria.
- Índices.
- Relaciones oficiales declaradas en SQL Server.
- Posibles relaciones no declaradas.
- Objetos SQL que utilizan la tabla.
- Informe Markdown en docs/exportaciones/analisis_tablas/.

Seguridad:
- Solo ejecuta consultas SELECT.
- Todas las consultas pasan por validar_consulta_lectura().
- No modifica datos ni estructuras de Farmatic.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from src.database.conexion_sql import obtener_conexion
from src.sql_explorer.seguridad_sql import validar_consulta_lectura


ESQUEMA_PREDETERMINADO = "dbo"


def ejecutar_consulta(
    conexion,
    consulta: str,
    parametros: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    """
    Ejecuta una consulta de lectura y devuelve una lista de diccionarios.
    """

    validar_consulta_lectura(consulta)

    cursor = conexion.cursor()

    try:
        cursor.execute(consulta, parametros)

        if cursor.description is None:
            return []

        columnas = [
            descripcion[0]
            for descripcion in cursor.description
        ]

        resultados = []

        for fila in cursor.fetchall():
            resultados.append(
                dict(zip(columnas, fila))
            )

        return resultados

    finally:
        cursor.close()


def buscar_tablas(
    conexion,
    texto: str,
) -> list[dict[str, Any]]:
    """
    Busca tablas cuyo nombre coincida total o parcialmente
    con el texto introducido.
    """

    consulta = """
        SELECT
            s.name AS Esquema,
            t.name AS Tabla
        FROM sys.tables AS t
        INNER JOIN sys.schemas AS s
            ON t.schema_id = s.schema_id
        WHERE t.is_ms_shipped = 0
          AND LOWER(t.name) LIKE LOWER(?)
        ORDER BY
            CASE
                WHEN LOWER(t.name) = LOWER(?) THEN 0
                ELSE 1
            END,
            s.name,
            t.name
    """

    patron = f"%{texto}%"

    return ejecutar_consulta(
        conexion,
        consulta,
        (
            patron,
            texto,
        ),
    )


def resolver_tabla(
    conexion,
    texto: str,
) -> tuple[str, str] | None:
    """
    Resuelve el nombre de tabla introducido por el usuario.

    Acepta:
    - Albaran
    - dbo.Albaran
    """

    texto = texto.strip()

    if not texto:
        return None

    if "." in texto:
        partes = texto.split(".", maxsplit=1)

        esquema = partes[0].strip()
        tabla = partes[1].strip()

        consulta = """
            SELECT
                s.name AS Esquema,
                t.name AS Tabla
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s
                ON t.schema_id = s.schema_id
            WHERE t.is_ms_shipped = 0
              AND LOWER(s.name) = LOWER(?)
              AND LOWER(t.name) = LOWER(?)
        """

        resultados = ejecutar_consulta(
            conexion,
            consulta,
            (
                esquema,
                tabla,
            ),
        )

        if not resultados:
            return None

        return (
            str(resultados[0]["Esquema"]),
            str(resultados[0]["Tabla"]),
        )

    resultados = buscar_tablas(
        conexion,
        texto,
    )

    coincidencias_exactas = [
        resultado
        for resultado in resultados
        if str(resultado["Tabla"]).lower() == texto.lower()
    ]

    if len(coincidencias_exactas) == 1:
        return (
            str(coincidencias_exactas[0]["Esquema"]),
            str(coincidencias_exactas[0]["Tabla"]),
        )

    if len(resultados) == 1:
        return (
            str(resultados[0]["Esquema"]),
            str(resultados[0]["Tabla"]),
        )

    if not resultados:
        print()
        print("No se ha encontrado ninguna tabla coincidente.")
        return None

    print()
    print("Se han encontrado varias tablas:")
    print()

    for numero, resultado in enumerate(
        resultados,
        start=1,
    ):
        print(
            f"{numero:>3}. "
            f"{resultado['Esquema']}."
            f"{resultado['Tabla']}"
        )

    print()
    seleccion = input(
        "Selecciona el número de la tabla: "
    ).strip()

    try:
        indice = int(seleccion) - 1
    except ValueError:
        print("La selección no es válida.")
        return None

    if indice < 0 or indice >= len(resultados):
        print("La selección está fuera de rango.")
        return None

    resultado = resultados[indice]

    return (
        str(resultado["Esquema"]),
        str(resultado["Tabla"]),
    )


def obtener_informacion_general(
    conexion,
    esquema: str,
    tabla: str,
) -> list[dict[str, Any]]:
    """
    Obtiene información general y número aproximado de filas.
    """

    consulta = """
        SELECT
            s.name AS Esquema,
            t.name AS Tabla,
            t.create_date AS FechaCreacion,
            t.modify_date AS FechaModificacion,
            COALESCE(SUM(p.row_count), 0) AS NumeroFilas
        FROM sys.tables AS t
        INNER JOIN sys.schemas AS s
            ON t.schema_id = s.schema_id
        LEFT JOIN sys.dm_db_partition_stats AS p
            ON t.object_id = p.object_id
           AND p.index_id IN (0, 1)
        WHERE t.is_ms_shipped = 0
          AND s.name = ?
          AND t.name = ?
        GROUP BY
            s.name,
            t.name,
            t.create_date,
            t.modify_date
    """

    return ejecutar_consulta(
        conexion,
        consulta,
        (
            esquema,
            tabla,
        ),
    )


def obtener_columnas(
    conexion,
    esquema: str,
    tabla: str,
) -> list[dict[str, Any]]:
    """
    Obtiene columnas, tipos y propiedades de la tabla.
    """

    consulta = """
        SELECT
            c.column_id AS Posicion,
            c.name AS Columna,
            tipo.name AS TipoDato,
            CASE
                WHEN tipo.name IN ('nvarchar', 'nchar')
                     AND c.max_length > 0
                    THEN c.max_length / 2
                WHEN c.max_length = -1
                    THEN -1
                ELSE c.max_length
            END AS LongitudMaxima,
            c.precision AS Precision,
            c.scale AS Escala,
            c.is_nullable AS AdmiteNulos,
            c.is_identity AS EsIdentidad,
            c.is_computed AS EsCalculada,
            dc.definition AS ValorPredeterminado
        FROM sys.columns AS c
        INNER JOIN sys.tables AS t
            ON c.object_id = t.object_id
        INNER JOIN sys.schemas AS s
            ON t.schema_id = s.schema_id
        INNER JOIN sys.types AS tipo
            ON c.user_type_id = tipo.user_type_id
        LEFT JOIN sys.default_constraints AS dc
            ON c.default_object_id = dc.object_id
        WHERE s.name = ?
          AND t.name = ?
        ORDER BY c.column_id
    """

    return ejecutar_consulta(
        conexion,
        consulta,
        (
            esquema,
            tabla,
        ),
    )


def obtener_clave_primaria(
    conexion,
    esquema: str,
    tabla: str,
) -> list[dict[str, Any]]:
    """
    Obtiene la clave primaria declarada.
    """

    consulta = """
        SELECT
            kc.name AS NombreClavePrimaria,
            c.name AS Columna,
            ic.key_ordinal AS OrdenColumna
        FROM sys.key_constraints AS kc
        INNER JOIN sys.tables AS t
            ON kc.parent_object_id = t.object_id
        INNER JOIN sys.schemas AS s
            ON t.schema_id = s.schema_id
        INNER JOIN sys.index_columns AS ic
            ON kc.parent_object_id = ic.object_id
           AND kc.unique_index_id = ic.index_id
        INNER JOIN sys.columns AS c
            ON ic.object_id = c.object_id
           AND ic.column_id = c.column_id
        WHERE kc.type = 'PK'
          AND s.name = ?
          AND t.name = ?
        ORDER BY ic.key_ordinal
    """

    return ejecutar_consulta(
        conexion,
        consulta,
        (
            esquema,
            tabla,
        ),
    )


def obtener_indices(
    conexion,
    esquema: str,
    tabla: str,
) -> list[dict[str, Any]]:
    """
    Obtiene los índices y sus columnas.
    """

    consulta = """
        SELECT
            i.name AS Indice,
            i.type_desc AS TipoIndice,
            i.is_unique AS EsUnico,
            i.is_primary_key AS EsClavePrimaria,
            c.name AS Columna,
            ic.key_ordinal AS OrdenColumna,
            ic.is_included_column AS ColumnaIncluida
        FROM sys.indexes AS i
        INNER JOIN sys.tables AS t
            ON i.object_id = t.object_id
        INNER JOIN sys.schemas AS s
            ON t.schema_id = s.schema_id
        INNER JOIN sys.index_columns AS ic
            ON i.object_id = ic.object_id
           AND i.index_id = ic.index_id
        INNER JOIN sys.columns AS c
            ON ic.object_id = c.object_id
           AND ic.column_id = c.column_id
        WHERE s.name = ?
          AND t.name = ?
          AND i.name IS NOT NULL
        ORDER BY
            i.name,
            ic.is_included_column,
            ic.key_ordinal,
            c.name
    """

    return ejecutar_consulta(
        conexion,
        consulta,
        (
            esquema,
            tabla,
        ),
    )


def obtener_relaciones_salientes(
    conexion,
    esquema: str,
    tabla: str,
) -> list[dict[str, Any]]:
    """
    Obtiene claves externas desde la tabla analizada
    hacia otras tablas.
    """

    consulta = """
        SELECT
            fk.name AS NombreRelacion,
            esquema_origen.name AS EsquemaOrigen,
            tabla_origen.name AS TablaOrigen,
            columna_origen.name AS ColumnaOrigen,
            esquema_destino.name AS EsquemaDestino,
            tabla_destino.name AS TablaDestino,
            columna_destino.name AS ColumnaDestino
        FROM sys.foreign_keys AS fk
        INNER JOIN sys.foreign_key_columns AS fkc
            ON fk.object_id = fkc.constraint_object_id
        INNER JOIN sys.tables AS tabla_origen
            ON fkc.parent_object_id = tabla_origen.object_id
        INNER JOIN sys.schemas AS esquema_origen
            ON tabla_origen.schema_id = esquema_origen.schema_id
        INNER JOIN sys.columns AS columna_origen
            ON fkc.parent_object_id = columna_origen.object_id
           AND fkc.parent_column_id = columna_origen.column_id
        INNER JOIN sys.tables AS tabla_destino
            ON fkc.referenced_object_id = tabla_destino.object_id
        INNER JOIN sys.schemas AS esquema_destino
            ON tabla_destino.schema_id = esquema_destino.schema_id
        INNER JOIN sys.columns AS columna_destino
            ON fkc.referenced_object_id = columna_destino.object_id
           AND fkc.referenced_column_id = columna_destino.column_id
        WHERE esquema_origen.name = ?
          AND tabla_origen.name = ?
        ORDER BY
            fk.name,
            fkc.constraint_column_id
    """

    return ejecutar_consulta(
        conexion,
        consulta,
        (
            esquema,
            tabla,
        ),
    )


def obtener_relaciones_entrantes(
    conexion,
    esquema: str,
    tabla: str,
) -> list[dict[str, Any]]:
    """
    Obtiene claves externas desde otras tablas
    hacia la tabla analizada.
    """

    consulta = """
        SELECT
            fk.name AS NombreRelacion,
            esquema_origen.name AS EsquemaOrigen,
            tabla_origen.name AS TablaOrigen,
            columna_origen.name AS ColumnaOrigen,
            esquema_destino.name AS EsquemaDestino,
            tabla_destino.name AS TablaDestino,
            columna_destino.name AS ColumnaDestino
        FROM sys.foreign_keys AS fk
        INNER JOIN sys.foreign_key_columns AS fkc
            ON fk.object_id = fkc.constraint_object_id
        INNER JOIN sys.tables AS tabla_origen
            ON fkc.parent_object_id = tabla_origen.object_id
        INNER JOIN sys.schemas AS esquema_origen
            ON tabla_origen.schema_id = esquema_origen.schema_id
        INNER JOIN sys.columns AS columna_origen
            ON fkc.parent_object_id = columna_origen.object_id
           AND fkc.parent_column_id = columna_origen.column_id
        INNER JOIN sys.tables AS tabla_destino
            ON fkc.referenced_object_id = tabla_destino.object_id
        INNER JOIN sys.schemas AS esquema_destino
            ON tabla_destino.schema_id = esquema_destino.schema_id
        INNER JOIN sys.columns AS columna_destino
            ON fkc.referenced_object_id = columna_destino.object_id
           AND fkc.referenced_column_id = columna_destino.column_id
        WHERE esquema_destino.name = ?
          AND tabla_destino.name = ?
        ORDER BY
            fk.name,
            fkc.constraint_column_id
    """

    return ejecutar_consulta(
        conexion,
        consulta,
        (
            esquema,
            tabla,
        ),
    )


def obtener_relaciones_probables(
    conexion,
    esquema: str,
    tabla: str,
) -> list[dict[str, Any]]:
    """
    Busca columnas de otras tablas con el mismo nombre y tipo
    que las columnas de la tabla analizada.

    No compara todas las tablas entre sí.
    Solo compara cada columna de la tabla analizada con el resto.
    """

    consulta = """
        SELECT
            columna_origen.name AS ColumnaAnalizada,
            tipo_origen.name AS TipoAnalizado,
            esquema_candidato.name AS EsquemaCandidato,
            tabla_candidato.name AS TablaCandidata,
            columna_candidato.name AS ColumnaCandidata,
            tipo_candidato.name AS TipoCandidato,
            columna_candidato.is_nullable AS AdmiteNulos,
            CASE
                WHEN indice_candidato.is_primary_key = 1 THEN 1
                ELSE 0
            END AS EsClavePrimaria,
            CASE
                WHEN indice_candidato.is_unique = 1 THEN 1
                ELSE 0
            END AS EsUnica
        FROM sys.tables AS tabla_origen
        INNER JOIN sys.schemas AS esquema_origen
            ON tabla_origen.schema_id = esquema_origen.schema_id
        INNER JOIN sys.columns AS columna_origen
            ON tabla_origen.object_id = columna_origen.object_id
        INNER JOIN sys.types AS tipo_origen
            ON columna_origen.user_type_id = tipo_origen.user_type_id
        INNER JOIN sys.columns AS columna_candidato
            ON LOWER(columna_candidato.name) =
               LOWER(columna_origen.name)
        INNER JOIN sys.tables AS tabla_candidato
            ON columna_candidato.object_id =
               tabla_candidato.object_id
        INNER JOIN sys.schemas AS esquema_candidato
            ON tabla_candidato.schema_id =
               esquema_candidato.schema_id
        INNER JOIN sys.types AS tipo_candidato
            ON columna_candidato.user_type_id =
               tipo_candidato.user_type_id
        LEFT JOIN sys.index_columns AS ic_candidato
            ON columna_candidato.object_id =
               ic_candidato.object_id
           AND columna_candidato.column_id =
               ic_candidato.column_id
        LEFT JOIN sys.indexes AS indice_candidato
            ON ic_candidato.object_id =
               indice_candidato.object_id
           AND ic_candidato.index_id =
               indice_candidato.index_id
        WHERE esquema_origen.name = ?
          AND tabla_origen.name = ?
          AND tabla_candidato.object_id <>
              tabla_origen.object_id
          AND tipo_origen.name = tipo_candidato.name
          AND (
                columna_origen.max_length =
                columna_candidato.max_length
                OR columna_origen.max_length = -1
                OR columna_candidato.max_length = -1
          )
        GROUP BY
            columna_origen.name,
            tipo_origen.name,
            esquema_candidato.name,
            tabla_candidato.name,
            columna_candidato.name,
            tipo_candidato.name,
            columna_candidato.is_nullable,
            indice_candidato.is_primary_key,
            indice_candidato.is_unique
        ORDER BY
            CASE
                WHEN indice_candidato.is_primary_key = 1 THEN 0
                WHEN indice_candidato.is_unique = 1 THEN 1
                ELSE 2
            END,
            columna_origen.name,
            esquema_candidato.name,
            tabla_candidato.name
    """

    resultados = ejecutar_consulta(
        conexion,
        consulta,
        (
            esquema,
            tabla,
        ),
    )

    relaciones_oficiales = obtener_relaciones_salientes(
        conexion,
        esquema,
        tabla,
    )

    oficiales = {
        (
            str(relacion["ColumnaOrigen"]).lower(),
            str(relacion["EsquemaDestino"]).lower(),
            str(relacion["TablaDestino"]).lower(),
            str(relacion["ColumnaDestino"]).lower(),
        )
        for relacion in relaciones_oficiales
    }

    filtrados = []

    for resultado in resultados:
        clave = (
            str(resultado["ColumnaAnalizada"]).lower(),
            str(resultado["EsquemaCandidato"]).lower(),
            str(resultado["TablaCandidata"]).lower(),
            str(resultado["ColumnaCandidata"]).lower(),
        )

        if clave in oficiales:
            continue

        filtrados.append(resultado)

    return filtrados


def obtener_objetos_dependientes(
    conexion,
    esquema: str,
    tabla: str,
) -> list[dict[str, Any]]:
    """
    Busca vistas, procedimientos y funciones que tengan
    una dependencia registrada hacia la tabla.
    """

    consulta = """
        SELECT DISTINCT
            esquema_dependiente.name AS Esquema,
            objeto_dependiente.name AS Objeto,
            objeto_dependiente.type_desc AS TipoObjeto
        FROM sys.sql_expression_dependencies AS dependencia
        INNER JOIN sys.objects AS objeto_dependiente
            ON dependencia.referencing_id =
               objeto_dependiente.object_id
        INNER JOIN sys.schemas AS esquema_dependiente
            ON objeto_dependiente.schema_id =
               esquema_dependiente.schema_id
        INNER JOIN sys.objects AS objeto_referenciado
            ON dependencia.referenced_id =
               objeto_referenciado.object_id
        INNER JOIN sys.schemas AS esquema_referenciado
            ON objeto_referenciado.schema_id =
               esquema_referenciado.schema_id
        WHERE esquema_referenciado.name = ?
          AND objeto_referenciado.name = ?
        ORDER BY
            objeto_dependiente.type_desc,
            esquema_dependiente.name,
            objeto_dependiente.name
    """

    return ejecutar_consulta(
        conexion,
        consulta,
        (
            esquema,
            tabla,
        ),
    )


def convertir_si_no(valor: Any) -> str:
    """
    Convierte valores booleanos de SQL Server a Sí o No.
    """

    return "Sí" if bool(valor) else "No"


def describir_tipo(columna: dict[str, Any]) -> str:
    """
    Construye una descripción legible del tipo SQL.
    """

    tipo = str(columna["TipoDato"])
    longitud = columna.get("LongitudMaxima")
    precision = columna.get("Precision")
    escala = columna.get("Escala")

    tipos_texto = {
        "char",
        "varchar",
        "nchar",
        "nvarchar",
        "binary",
        "varbinary",
    }

    tipos_numericos = {
        "decimal",
        "numeric",
    }

    if tipo.lower() in tipos_texto and longitud is not None:
        if int(longitud) == -1:
            return f"{tipo}(MAX)"

        return f"{tipo}({longitud})"

    if tipo.lower() in tipos_numericos:
        return f"{tipo}({precision},{escala})"

    return tipo


def escapar_markdown(valor: Any) -> str:
    """
    Evita que el carácter | rompa las tablas Markdown.
    """

    if valor is None:
        return ""

    return str(valor).replace("|", "\\|").replace("\n", " ")


def crear_informe_markdown(
    esquema: str,
    tabla: str,
    informacion_general: list[dict[str, Any]],
    columnas: list[dict[str, Any]],
    clave_primaria: list[dict[str, Any]],
    indices: list[dict[str, Any]],
    relaciones_salientes: list[dict[str, Any]],
    relaciones_entrantes: list[dict[str, Any]],
    relaciones_probables: list[dict[str, Any]],
    objetos_dependientes: list[dict[str, Any]],
) -> str:
    """
    Genera el contenido del informe Markdown.
    """

    lineas = [
        f"# Análisis automático: {esquema}.{tabla}",
        "",
        "> Informe técnico generado automáticamente.",
        "> Las relaciones probables deben validarse antes de",
        "> incorporarlas a la documentación funcional.",
        "",
        f"Fecha de generación: "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    lineas.append("## Información general")
    lineas.append("")

    if informacion_general:
        informacion = informacion_general[0]

        lineas.extend(
            [
                f"- Esquema: `{informacion['Esquema']}`",
                f"- Tabla: `{informacion['Tabla']}`",
                f"- Número aproximado de registros: "
                f"`{informacion['NumeroFilas']}`",
                f"- Fecha de creación SQL: "
                f"`{informacion['FechaCreacion']}`",
                f"- Fecha de modificación SQL: "
                f"`{informacion['FechaModificacion']}`",
            ]
        )
    else:
        lineas.append("No se ha obtenido información general.")

    lineas.extend(
        [
            "",
            "## Columnas",
            "",
            "| Posición | Columna | Tipo | Nulos | Identidad | "
            "Calculada | Valor predeterminado |",
            "|---:|---|---|---|---|---|---|",
        ]
    )

    for columna in columnas:
        lineas.append(
            f"| {columna['Posicion']} "
            f"| `{escapar_markdown(columna['Columna'])}` "
            f"| `{describir_tipo(columna)}` "
            f"| {convertir_si_no(columna['AdmiteNulos'])} "
            f"| {convertir_si_no(columna['EsIdentidad'])} "
            f"| {convertir_si_no(columna['EsCalculada'])} "
            f"| `{escapar_markdown(columna['ValorPredeterminado'])}` |"
        )

    lineas.extend(
        [
            "",
            "## Clave primaria",
            "",
        ]
    )

    if clave_primaria:
        for fila in clave_primaria:
            lineas.append(
                f"- `{fila['Columna']}` "
                f"(orden {fila['OrdenColumna']})"
            )
    else:
        lineas.append(
            "No se ha encontrado una clave primaria declarada."
        )

    lineas.extend(
        [
            "",
            "## Índices",
            "",
        ]
    )

    if indices:
        lineas.extend(
            [
                "| Índice | Tipo | Columna | Orden | Único | "
                "Clave primaria | Incluida |",
                "|---|---|---|---:|---|---|---|",
            ]
        )

        for indice in indices:
            lineas.append(
                f"| `{escapar_markdown(indice['Indice'])}` "
                f"| {escapar_markdown(indice['TipoIndice'])} "
                f"| `{escapar_markdown(indice['Columna'])}` "
                f"| {indice['OrdenColumna']} "
                f"| {convertir_si_no(indice['EsUnico'])} "
                f"| {convertir_si_no(indice['EsClavePrimaria'])} "
                f"| {convertir_si_no(indice['ColumnaIncluida'])} |"
            )
    else:
        lineas.append("No se han encontrado índices.")

    lineas.extend(
        [
            "",
            "## Relaciones oficiales salientes",
            "",
        ]
    )

    if relaciones_salientes:
        for relacion in relaciones_salientes:
            lineas.append(
                f"- `{relacion['EsquemaOrigen']}."
                f"{relacion['TablaOrigen']}."
                f"{relacion['ColumnaOrigen']}` → "
                f"`{relacion['EsquemaDestino']}."
                f"{relacion['TablaDestino']}."
                f"{relacion['ColumnaDestino']}` "
                f"(`{relacion['NombreRelacion']}`)"
            )
    else:
        lineas.append(
            "No se han encontrado relaciones salientes declaradas."
        )

    lineas.extend(
        [
            "",
            "## Relaciones oficiales entrantes",
            "",
        ]
    )

    if relaciones_entrantes:
        for relacion in relaciones_entrantes:
            lineas.append(
                f"- `{relacion['EsquemaOrigen']}."
                f"{relacion['TablaOrigen']}."
                f"{relacion['ColumnaOrigen']}` → "
                f"`{relacion['EsquemaDestino']}."
                f"{relacion['TablaDestino']}."
                f"{relacion['ColumnaDestino']}` "
                f"(`{relacion['NombreRelacion']}`)"
            )
    else:
        lineas.append(
            "No se han encontrado relaciones entrantes declaradas."
        )

    lineas.extend(
        [
            "",
            "## Relaciones probables",
            "",
            "Estas coincidencias no demuestran por sí solas que exista",
            "una relación funcional.",
            "",
        ]
    )

    if relaciones_probables:
        lineas.extend(
            [
                "| Columna analizada | Tabla candidata | "
                "Columna candidata | Tipo | PK | Única |",
                "|---|---|---|---|---|---|",
            ]
        )

        for relacion in relaciones_probables:
            lineas.append(
                f"| `{relacion['ColumnaAnalizada']}` "
                f"| `{relacion['EsquemaCandidato']}."
                f"{relacion['TablaCandidata']}` "
                f"| `{relacion['ColumnaCandidata']}` "
                f"| `{relacion['TipoCandidato']}` "
                f"| {convertir_si_no(relacion['EsClavePrimaria'])} "
                f"| {convertir_si_no(relacion['EsUnica'])} |"
            )
    else:
        lineas.append(
            "No se han encontrado relaciones probables."
        )

    lineas.extend(
        [
            "",
            "## Objetos que dependen de la tabla",
            "",
        ]
    )

    if objetos_dependientes:
        for objeto in objetos_dependientes:
            lineas.append(
                f"- `{objeto['Esquema']}."
                f"{objeto['Objeto']}` — "
                f"{objeto['TipoObjeto']}"
            )
    else:
        lineas.append(
            "No se han encontrado dependencias registradas."
        )

    lineas.extend(
        [
            "",
            "## Validación funcional",
            "",
            "Pendiente de completar manualmente en:",
            "",
            f"`docs/tablas/{tabla.lower()}.md`",
            "",
            "Aspectos que deben validarse:",
            "",
            "- Significado funcional de cada columna importante.",
            "- Valores posibles de estados y tipos.",
            "- Relaciones reales utilizadas por Farmatic.",
            "- Casos especiales y excepciones.",
            "- Utilidad para ControlFarmacias.",
            "",
        ]
    )

    return "\n".join(lineas)


def guardar_informe(
    esquema: str,
    tabla: str,
    contenido: str,
) -> Path:
    """
    Guarda el informe dentro de docs/exportaciones.
    """

    raiz_proyecto = Path(__file__).resolve().parents[2]

    carpeta_salida = (
        raiz_proyecto
        / "docs"
        / "exportaciones"
        / "analisis_tablas"
    )

    carpeta_salida.mkdir(
        parents=True,
        exist_ok=True,
    )

    ruta_salida = carpeta_salida / f"{tabla}.md"

    ruta_salida.write_text(
        contenido,
        encoding="utf-8",
    )

    return ruta_salida


def mostrar_resumen(
    esquema: str,
    tabla: str,
    informacion_general: list[dict[str, Any]],
    columnas: list[dict[str, Any]],
    clave_primaria: list[dict[str, Any]],
    indices: list[dict[str, Any]],
    relaciones_salientes: list[dict[str, Any]],
    relaciones_entrantes: list[dict[str, Any]],
    relaciones_probables: list[dict[str, Any]],
    objetos_dependientes: list[dict[str, Any]],
) -> None:
    """
    Muestra un resumen compacto en la terminal.
    """

    print()
    print("=" * 100)
    print(f"ANÁLISIS DE {esquema}.{tabla}")
    print("=" * 100)

    numero_filas = 0

    if informacion_general:
        numero_filas = informacion_general[0]["NumeroFilas"]

    print(f"Registros aproximados: {numero_filas}")
    print(f"Columnas: {len(columnas)}")
    print(f"Columnas de clave primaria: {len(clave_primaria)}")
    print(f"Entradas de índices: {len(indices)}")
    print(
        "Relaciones oficiales salientes: "
        f"{len(relaciones_salientes)}"
    )
    print(
        "Relaciones oficiales entrantes: "
        f"{len(relaciones_entrantes)}"
    )
    print(
        "Relaciones probables: "
        f"{len(relaciones_probables)}"
    )
    print(
        "Objetos dependientes: "
        f"{len(objetos_dependientes)}"
    )

    print()
    print("CLAVE PRIMARIA")
    print("-" * 100)

    if clave_primaria:
        for fila in clave_primaria:
            print(
                f"- {fila['Columna']} "
                f"(orden {fila['OrdenColumna']})"
            )
    else:
        print("No existe una clave primaria declarada.")

    print()
    print("RELACIONES OFICIALES SALIENTES")
    print("-" * 100)

    if relaciones_salientes:
        for relacion in relaciones_salientes:
            print(
                f"- {relacion['TablaOrigen']}."
                f"{relacion['ColumnaOrigen']} → "
                f"{relacion['TablaDestino']}."
                f"{relacion['ColumnaDestino']}"
            )
    else:
        print("No se han encontrado.")

    print()
    print("MEJORES CANDIDATOS A RELACIÓN")
    print("-" * 100)

    candidatos_principales = [
        candidato
        for candidato in relaciones_probables
        if candidato["EsClavePrimaria"]
        or candidato["EsUnica"]
    ]

    if candidatos_principales:
        for candidato in candidatos_principales[:30]:
            indicador = (
                "PK"
                if candidato["EsClavePrimaria"]
                else "ÚNICA"
            )

            print(
                f"- {tabla}."
                f"{candidato['ColumnaAnalizada']} ⇢ "
                f"{candidato['EsquemaCandidato']}."
                f"{candidato['TablaCandidata']}."
                f"{candidato['ColumnaCandidata']} "
                f"[{indicador}]"
            )
    else:
        print(
            "No se han encontrado candidatos que sean "
            "clave primaria o columna única."
        )


def analizar_tabla() -> None:
    """
    Ejecuta la herramienta interactiva.
    """

    print()
    print("=" * 100)
    print("ANALIZADOR AUTOMÁTICO DE TABLAS DE FARMATIC")
    print("=" * 100)
    print()
    print(
        "Ejemplos: Albaran, Proveedor, Pedido o dbo.Albaran"
    )

    texto_tabla = input(
        "Tabla que quieres analizar: "
    ).strip()

    if not texto_tabla:
        print("No se ha indicado ninguna tabla.")
        return

    conexion = None

    try:
        print()
        print("Conectando con Farmatic...")

        conexion = obtener_conexion()

        tabla_resuelta = resolver_tabla(
            conexion,
            texto_tabla,
        )

        if tabla_resuelta is None:
            return

        esquema, tabla = tabla_resuelta

        print(f"Analizando {esquema}.{tabla}...")

        informacion_general = obtener_informacion_general(
            conexion,
            esquema,
            tabla,
        )

        columnas = obtener_columnas(
            conexion,
            esquema,
            tabla,
        )

        clave_primaria = obtener_clave_primaria(
            conexion,
            esquema,
            tabla,
        )

        indices = obtener_indices(
            conexion,
            esquema,
            tabla,
        )

        relaciones_salientes = obtener_relaciones_salientes(
            conexion,
            esquema,
            tabla,
        )

        relaciones_entrantes = obtener_relaciones_entrantes(
            conexion,
            esquema,
            tabla,
        )

        relaciones_probables = obtener_relaciones_probables(
            conexion,
            esquema,
            tabla,
        )

        objetos_dependientes = obtener_objetos_dependientes(
            conexion,
            esquema,
            tabla,
        )

        mostrar_resumen(
            esquema,
            tabla,
            informacion_general,
            columnas,
            clave_primaria,
            indices,
            relaciones_salientes,
            relaciones_entrantes,
            relaciones_probables,
            objetos_dependientes,
        )

        informe = crear_informe_markdown(
            esquema,
            tabla,
            informacion_general,
            columnas,
            clave_primaria,
            indices,
            relaciones_salientes,
            relaciones_entrantes,
            relaciones_probables,
            objetos_dependientes,
        )

        ruta_informe = guardar_informe(
            esquema,
            tabla,
            informe,
        )

        print()
        print("=" * 100)
        print("ANÁLISIS FINALIZADO")
        print("=" * 100)
        print()
        print("Informe generado correctamente:")
        print(ruta_informe)

    except Exception as error:
        print()
        print("Se ha producido un error durante el análisis:")
        print(error)
        raise

    finally:
        if conexion is not None:
            conexion.close()
            print()
            print("Conexión cerrada correctamente.")


if __name__ == "__main__":
    analizar_tabla()