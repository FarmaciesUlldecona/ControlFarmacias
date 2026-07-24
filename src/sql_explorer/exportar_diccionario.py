from datetime import datetime
from pathlib import Path

import pandas as pd

from src.database.conexion_sql import obtener_conexion


def ejecutar_consulta(conexion, consulta: str) -> pd.DataFrame:
    """
    Ejecuta una consulta SELECT y devuelve los resultados
    en un DataFrame de pandas.

    La función no realiza ninguna operación de escritura.
    """
    cursor = conexion.cursor()
    cursor.execute(consulta)

    columnas = [columna[0] for columna in cursor.description]
    filas = cursor.fetchall()

    cursor.close()

    return pd.DataFrame.from_records(filas, columns=columnas)


def obtener_objetos(conexion) -> pd.DataFrame:
    """
    Obtiene las tablas y vistas de la base de datos.
    """
    consulta = """
    SELECT
        s.name AS Esquema,
        o.name AS Objeto,
        CASE
            WHEN o.type = 'U' THEN 'TABLA'
            WHEN o.type = 'V' THEN 'VISTA'
            ELSE o.type_desc
        END AS TipoObjeto,
        o.create_date AS FechaCreacion,
        o.modify_date AS FechaModificacion
    FROM sys.objects AS o
    INNER JOIN sys.schemas AS s
        ON o.schema_id = s.schema_id
    WHERE o.type IN ('U', 'V')
      AND o.is_ms_shipped = 0
    ORDER BY
        TipoObjeto,
        Esquema,
        Objeto;
    """

    return ejecutar_consulta(conexion, consulta)


def obtener_columnas(conexion) -> pd.DataFrame:
    """
    Obtiene las columnas, tipos de datos y propiedades principales.
    """
    consulta = """
    SELECT
        s.name AS Esquema,
        o.name AS Objeto,
        CASE
            WHEN o.type = 'U' THEN 'TABLA'
            WHEN o.type = 'V' THEN 'VISTA'
        END AS TipoObjeto,
        c.column_id AS Posicion,
        c.name AS Columna,
        t.name AS TipoDato,
        CASE
            WHEN t.name IN ('nvarchar', 'nchar')
                 AND c.max_length > 0
                THEN c.max_length / 2
            WHEN c.max_length = -1
                THEN -1
            ELSE c.max_length
        END AS LongitudMaxima,
        c.precision AS Precision,
        c.scale AS Escala,
        CASE
            WHEN c.is_nullable = 1 THEN 'SI'
            ELSE 'NO'
        END AS AdmiteNulos,
        CASE
            WHEN c.is_identity = 1 THEN 'SI'
            ELSE 'NO'
        END AS EsIdentidad,
        CASE
            WHEN c.is_computed = 1 THEN 'SI'
            ELSE 'NO'
        END AS EsCalculada
    FROM sys.columns AS c
    INNER JOIN sys.objects AS o
        ON c.object_id = o.object_id
    INNER JOIN sys.schemas AS s
        ON o.schema_id = s.schema_id
    INNER JOIN sys.types AS t
        ON c.user_type_id = t.user_type_id
    WHERE o.type IN ('U', 'V')
      AND o.is_ms_shipped = 0
    ORDER BY
        s.name,
        o.name,
        c.column_id;
    """

    return ejecutar_consulta(conexion, consulta)


def obtener_claves_primarias(conexion) -> pd.DataFrame:
    """
    Obtiene las claves primarias declaradas en SQL Server.
    """
    consulta = """
    SELECT
        s.name AS Esquema,
        t.name AS Tabla,
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
      AND t.is_ms_shipped = 0
    ORDER BY
        s.name,
        t.name,
        ic.key_ordinal;
    """

    return ejecutar_consulta(conexion, consulta)


def obtener_claves_externas(conexion) -> pd.DataFrame:
    """
    Obtiene las relaciones declaradas mediante claves externas.
    """
    consulta = """
    SELECT
        fk.name AS NombreRelacion,
        sch_origen.name AS EsquemaOrigen,
        tabla_origen.name AS TablaOrigen,
        columna_origen.name AS ColumnaOrigen,
        sch_destino.name AS EsquemaDestino,
        tabla_destino.name AS TablaDestino,
        columna_destino.name AS ColumnaDestino,
        fk.delete_referential_action_desc AS AccionAlEliminar,
        fk.update_referential_action_desc AS AccionAlActualizar
    FROM sys.foreign_keys AS fk
    INNER JOIN sys.foreign_key_columns AS fkc
        ON fk.object_id = fkc.constraint_object_id
    INNER JOIN sys.tables AS tabla_origen
        ON fkc.parent_object_id = tabla_origen.object_id
    INNER JOIN sys.schemas AS sch_origen
        ON tabla_origen.schema_id = sch_origen.schema_id
    INNER JOIN sys.columns AS columna_origen
        ON fkc.parent_object_id = columna_origen.object_id
       AND fkc.parent_column_id = columna_origen.column_id
    INNER JOIN sys.tables AS tabla_destino
        ON fkc.referenced_object_id = tabla_destino.object_id
    INNER JOIN sys.schemas AS sch_destino
        ON tabla_destino.schema_id = sch_destino.schema_id
    INNER JOIN sys.columns AS columna_destino
        ON fkc.referenced_object_id = columna_destino.object_id
       AND fkc.referenced_column_id = columna_destino.column_id
    WHERE tabla_origen.is_ms_shipped = 0
    ORDER BY
        sch_origen.name,
        tabla_origen.name,
        fk.name;
    """

    return ejecutar_consulta(conexion, consulta)


def obtener_indices(conexion) -> pd.DataFrame:
    """
    Obtiene los índices existentes y sus columnas.
    """
    consulta = """
    SELECT
        s.name AS Esquema,
        t.name AS Tabla,
        i.name AS Indice,
        i.type_desc AS TipoIndice,
        CASE
            WHEN i.is_unique = 1 THEN 'SI'
            ELSE 'NO'
        END AS EsUnico,
        CASE
            WHEN i.is_primary_key = 1 THEN 'SI'
            ELSE 'NO'
        END AS EsClavePrimaria,
        c.name AS Columna,
        ic.key_ordinal AS OrdenColumna,
        CASE
            WHEN ic.is_included_column = 1 THEN 'SI'
            ELSE 'NO'
        END AS ColumnaIncluida
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
    WHERE t.is_ms_shipped = 0
      AND i.name IS NOT NULL
    ORDER BY
        s.name,
        t.name,
        i.name,
        ic.key_ordinal,
        c.name;
    """

    return ejecutar_consulta(conexion, consulta)


def obtener_numero_filas(conexion) -> pd.DataFrame:
    """
    Obtiene una estimación rápida del número de filas por tabla.

    Utiliza estadísticas internas de SQL Server y no recorre
    completamente cada tabla.
    """
    consulta = """
    SELECT
        s.name AS Esquema,
        t.name AS Tabla,
        SUM(p.row_count) AS NumeroFilas
    FROM sys.tables AS t
    INNER JOIN sys.schemas AS s
        ON t.schema_id = s.schema_id
    INNER JOIN sys.dm_db_partition_stats AS p
        ON t.object_id = p.object_id
    WHERE t.is_ms_shipped = 0
      AND p.index_id IN (0, 1)
    GROUP BY
        s.name,
        t.name
    ORDER BY
        NumeroFilas DESC,
        s.name,
        t.name;
    """

    return ejecutar_consulta(conexion, consulta)


def crear_resumen(
    objetos: pd.DataFrame,
    columnas: pd.DataFrame,
    claves_primarias: pd.DataFrame,
    claves_externas: pd.DataFrame,
    indices: pd.DataFrame,
) -> pd.DataFrame:
    """
    Crea la pestaña de resumen general.
    """
    numero_tablas = int(
        (objetos["TipoObjeto"] == "TABLA").sum()
    )

    numero_vistas = int(
        (objetos["TipoObjeto"] == "VISTA").sum()
    )

    datos = [
        ["Fecha de exportación", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["Base de datos", "Farmatic"],
        ["Tablas", numero_tablas],
        ["Vistas", numero_vistas],
        ["Columnas", len(columnas)],
        ["Claves primarias", claves_primarias["NombreClavePrimaria"].nunique()],
        ["Claves externas", claves_externas["NombreRelacion"].nunique()],
        ["Índices", indices["Indice"].nunique()],
        ["Modo de acceso", "Solo lectura"],
    ]

    return pd.DataFrame(datos, columns=["Concepto", "Valor"])


def ajustar_anchura_columnas(writer: pd.ExcelWriter) -> None:
    """
    Ajusta automáticamente la anchura de las columnas del Excel.
    """
    for hoja in writer.book.worksheets:
        for columna in hoja.columns:
            longitud_maxima = 0
            letra_columna = columna[0].column_letter

            for celda in columna:
                valor = "" if celda.value is None else str(celda.value)
                longitud_maxima = max(longitud_maxima, len(valor))

            anchura = min(longitud_maxima + 2, 60)
            hoja.column_dimensions[letra_columna].width = anchura

        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = hoja.dimensions


def exportar_diccionario() -> None:
    """
    Extrae el diccionario técnico de Farmatic y lo guarda en Excel.
    """
    raiz_proyecto = Path(__file__).resolve().parents[2]

    carpeta_exportaciones = (
        raiz_proyecto / "docs" / "exportaciones"
    )

    carpeta_exportaciones.mkdir(parents=True, exist_ok=True)

    archivo_salida = (
        carpeta_exportaciones / "diccionario_farmatic.xlsx"
    )

    conexion = None

    try:
        print("Conectando con Farmatic...")
        conexion = obtener_conexion()

        print("Leyendo tablas y vistas...")
        objetos = obtener_objetos(conexion)

        print("Leyendo columnas...")
        columnas = obtener_columnas(conexion)

        print("Leyendo claves primarias...")
        claves_primarias = obtener_claves_primarias(conexion)

        print("Leyendo claves externas...")
        claves_externas = obtener_claves_externas(conexion)

        print("Leyendo índices...")
        indices = obtener_indices(conexion)

        print("Leyendo número de filas...")
        numero_filas = obtener_numero_filas(conexion)

        resumen = crear_resumen(
            objetos,
            columnas,
            claves_primarias,
            claves_externas,
            indices,
        )

        print("Generando archivo Excel...")

        with pd.ExcelWriter(
            archivo_salida,
            engine="openpyxl",
        ) as writer:
            resumen.to_excel(
                writer,
                sheet_name="Resumen",
                index=False,
            )

            objetos.to_excel(
                writer,
                sheet_name="Objetos",
                index=False,
            )

            columnas.to_excel(
                writer,
                sheet_name="Columnas",
                index=False,
            )

            claves_primarias.to_excel(
                writer,
                sheet_name="Claves primarias",
                index=False,
            )

            claves_externas.to_excel(
                writer,
                sheet_name="Claves externas",
                index=False,
            )

            indices.to_excel(
                writer,
                sheet_name="Indices",
                index=False,
            )

            numero_filas.to_excel(
                writer,
                sheet_name="Numero filas",
                index=False,
            )

            ajustar_anchura_columnas(writer)

        print()
        print("Diccionario generado correctamente:")
        print(archivo_salida)

    except Exception as error:
        print()
        print("ERROR al generar el diccionario:")
        print(error)
        raise

    finally:
        if conexion is not None:
            conexion.close()
            print("Conexión cerrada correctamente.")


if __name__ == "__main__":
    exportar_diccionario()