"""
Mapa global de relaciones de Farmatic.

Esta herramienta:

- Lee las tablas y columnas de Farmatic.
- Obtiene claves primarias simples e índices únicos simples.
- Obtiene las claves externas oficiales.
- Busca posibles relaciones no declaradas.
- Asigna un nivel de confianza.
- Genera un Excel con los resultados.
- Genera un documento Markdown con un diagrama Mermaid.

Seguridad:

- Solo ejecuta consultas SELECT.
- Todas las consultas pasan por validar_consulta_lectura().
- No modifica datos ni estructuras de Farmatic.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.database.conexion_sql import obtener_conexion
from src.sql_explorer.seguridad_sql import validar_consulta_lectura
from src.utils.logger import obtener_logger


logger = obtener_logger("mapa_relaciones")


def ejecutar_consulta(
    conexion,
    consulta: str,
    parametros: tuple[Any, ...] = (),
) -> pd.DataFrame:
    """
    Ejecuta una consulta segura de lectura y devuelve un DataFrame.
    """

    consulta_segura = validar_consulta_lectura(consulta)
    cursor = conexion.cursor()

    try:
        cursor.execute(
            consulta_segura,
            parametros,
        )

        if cursor.description is None:
            return pd.DataFrame()

        columnas = [
            descripcion[0]
            for descripcion in cursor.description
        ]

        filas = cursor.fetchall()

        return pd.DataFrame.from_records(
            filas,
            columns=columnas,
        )

    finally:
        cursor.close()


def obtener_columnas(conexion) -> pd.DataFrame:
    """
    Obtiene todas las columnas de las tablas de Farmatic.
    """

    consulta = """
        SELECT
            s.name AS Esquema,
            t.name AS Tabla,
            c.column_id AS Posicion,
            c.name AS Columna,
            tipo.name AS TipoDato,
            c.max_length AS Longitud,
            c.precision AS Precision,
            c.scale AS Escala,
            c.is_nullable AS AdmiteNulos,
            c.is_identity AS EsIdentidad
        FROM sys.tables AS t
        INNER JOIN sys.schemas AS s
            ON t.schema_id = s.schema_id
        INNER JOIN sys.columns AS c
            ON t.object_id = c.object_id
        INNER JOIN sys.types AS tipo
            ON c.user_type_id = tipo.user_type_id
        WHERE t.is_ms_shipped = 0
        ORDER BY
            s.name,
            t.name,
            c.column_id
    """

    return ejecutar_consulta(
        conexion,
        consulta,
    )


def obtener_claves_primarias(conexion) -> pd.DataFrame:
    """
    Obtiene únicamente claves primarias de una sola columna.

    Las columnas individuales de una clave primaria compuesta no se
    consideran destinos únicos por sí solas.
    """

    consulta = """
        SELECT
            s.name AS Esquema,
            t.name AS Tabla,
            c.name AS Columna,
            kc.name AS NombreClavePrimaria,
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
          AND (
                SELECT COUNT(*)
                FROM sys.index_columns AS ic_contador
                WHERE ic_contador.object_id = kc.parent_object_id
                  AND ic_contador.index_id = kc.unique_index_id
                  AND ic_contador.is_included_column = 0
          ) = 1
        ORDER BY
            s.name,
            t.name,
            ic.key_ordinal
    """

    return ejecutar_consulta(
        conexion,
        consulta,
    )


def obtener_columnas_unicas(conexion) -> pd.DataFrame:
    """
    Obtiene columnas pertenecientes a índices únicos simples.

    Solo se consideran índices únicos de una única columna.
    """

    consulta = """
        SELECT
            s.name AS Esquema,
            t.name AS Tabla,
            c.name AS Columna,
            i.name AS NombreIndice
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
          AND i.is_unique = 1
          AND i.name IS NOT NULL
          AND ic.is_included_column = 0
          AND (
                SELECT COUNT(*)
                FROM sys.index_columns AS ic_contador
                WHERE ic_contador.object_id = i.object_id
                  AND ic_contador.index_id = i.index_id
                  AND ic_contador.is_included_column = 0
          ) = 1
        ORDER BY
            s.name,
            t.name,
            c.name
    """

    return ejecutar_consulta(
        conexion,
        consulta,
    )


def obtener_relaciones_oficiales(conexion) -> pd.DataFrame:
    """
    Obtiene las claves externas oficiales declaradas en SQL Server.
    """

    consulta = """
        SELECT
            fk.name AS NombreRelacion,
            esquema_origen.name AS EsquemaOrigen,
            tabla_origen.name AS TablaOrigen,
            columna_origen.name AS ColumnaOrigen,
            esquema_destino.name AS EsquemaDestino,
            tabla_destino.name AS TablaDestino,
            columna_destino.name AS ColumnaDestino,
            fkc.constraint_column_id AS OrdenColumna
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
        WHERE tabla_origen.is_ms_shipped = 0
          AND tabla_destino.is_ms_shipped = 0
        ORDER BY
            esquema_origen.name,
            tabla_origen.name,
            fk.name,
            fkc.constraint_column_id
    """

    relaciones = ejecutar_consulta(
        conexion,
        consulta,
    )

    columnas_salida = [
        "EsquemaOrigen",
        "TablaOrigen",
        "ColumnaOrigen",
        "EsquemaDestino",
        "TablaDestino",
        "ColumnaDestino",
        "TipoRelacion",
        "Confianza",
        "Puntuacion",
        "NombreRelacion",
    ]

    if relaciones.empty:
        return pd.DataFrame(
            columns=columnas_salida
        )

    resultado = relaciones.copy()
    resultado["TipoRelacion"] = "FOREIGN KEY OFICIAL"
    resultado["Confianza"] = "MUY ALTA"
    resultado["Puntuacion"] = 100

    return resultado[columnas_salida]


def normalizar_tipo(valor: Any) -> str:
    """
    Normaliza el nombre de un tipo SQL.
    """

    if valor is None:
        return ""

    return str(valor).strip().lower()


def tipos_compatibles(
    tipo_origen: str,
    tipo_destino: str,
) -> bool:
    """
    Comprueba si dos tipos SQL son compatibles.
    """

    origen = normalizar_tipo(tipo_origen)
    destino = normalizar_tipo(tipo_destino)

    if origen == destino:
        return True

    familias_enteros = {
        "tinyint",
        "smallint",
        "int",
        "bigint",
    }

    familias_texto = {
        "char",
        "varchar",
        "nchar",
        "nvarchar",
    }

    familias_decimales = {
        "decimal",
        "numeric",
        "money",
        "smallmoney",
        "float",
        "real",
    }

    if origen in familias_enteros and destino in familias_enteros:
        return True

    if origen in familias_texto and destino in familias_texto:
        return True

    if origen in familias_decimales and destino in familias_decimales:
        return True

    return False


def normalizar_nombre_relacion(valor: Any) -> str:
    """
    Normaliza nombres de columnas y tablas para comparar su significado.

    Ejemplos:
        IdProveedor -> proveedor
        IDPROVEEDOR -> proveedor
        XProv_IdProveedor -> proveedor
        IdArticu -> articu
    """

    texto = str(valor).strip().lower()

    if "_" in texto:
        partes = [
            parte
            for parte in texto.split("_")
            if parte
        ]

        if partes:
            texto = partes[-1]

    prefijos = [
        "id",
        "oid",
        "codigo",
        "cod",
        "fk",
    ]

    for prefijo in prefijos:
        if texto.startswith(prefijo) and len(texto) > len(prefijo):
            texto = texto[len(prefijo):]
            break

    caracteres = [
        caracter
        for caracter in texto
        if caracter.isalnum()
    ]

    return "".join(caracteres)


def columna_demasiado_generica(nombre_columna: Any) -> bool:
    """
    Detecta columnas cuyo nombre, por sí solo, es demasiado genérico
    para inferir una relación fiable.

    Importante:
    - Se excluye ``Usuario`` porque puede contener un nombre, código
      interno o texto libre.
    - No se excluyen identificadores concretos como ``IdUsuario``,
      ``IdProveedor`` o ``IdVenta``.
    """

    nombre = str(nombre_columna).strip().lower()

    columnas_genericas = {
        "id",
        "oid",
        "codigo",
        "cod",
        "numero",
        "num",
        "orden",
        "linea",
        "idlinea",
        "idnlinea",
        "fecha",
        "empresa",
        "ejercicio",
        "ordinal",
        "contador",
        "idcontador",
        "tipo",
        "idtipo",
        "estado",
        "resultado",
        "version",
        "indice",
        "usuario",
        "valor",
        "clave",
        "referencia",
        "descripcion",
        "nombre",
        "observaciones",
    }

    return nombre in columnas_genericas


def calcular_puntuacion_destino(
    columna_origen: Any,
    tabla_destino: Any,
    columna_destino: Any,
    es_clave_primaria: bool,
) -> int:
    """
    Puntúa cuánto sentido tiene una tabla como destino de una columna.
    """

    significado_origen = normalizar_nombre_relacion(
        columna_origen
    )

    significado_tabla = normalizar_nombre_relacion(
        tabla_destino
    )

    significado_destino = normalizar_nombre_relacion(
        columna_destino
    )

    puntuacion = 0

    if es_clave_primaria:
        puntuacion += 50
    else:
        puntuacion += 40

    if significado_origen == significado_destino:
        puntuacion += 20

    if significado_origen == significado_tabla:
        puntuacion += 30

    elif (
        significado_tabla
        and significado_tabla in significado_origen
    ):
        puntuacion += 20

    elif (
        significado_origen
        and significado_origen in significado_tabla
    ):
        puntuacion += 10

    return min(puntuacion, 100)


def preparar_conjuntos_clave(
    claves_primarias: pd.DataFrame,
    columnas_unicas: pd.DataFrame,
) -> tuple[
    set[tuple[str, str, str]],
    set[tuple[str, str, str]],
]:
    """
    Prepara conjuntos para localizar rápidamente PK e índices únicos.
    """

    claves_pk: set[tuple[str, str, str]] = set()
    claves_unicas: set[tuple[str, str, str]] = set()

    for _, fila in claves_primarias.iterrows():
        claves_pk.add(
            (
                str(fila["Esquema"]).lower(),
                str(fila["Tabla"]).lower(),
                str(fila["Columna"]).lower(),
            )
        )

    for _, fila in columnas_unicas.iterrows():
        claves_unicas.add(
            (
                str(fila["Esquema"]).lower(),
                str(fila["Tabla"]).lower(),
                str(fila["Columna"]).lower(),
            )
        )

    return claves_pk, claves_unicas


def detectar_relaciones_probables(
    columnas: pd.DataFrame,
    claves_primarias: pd.DataFrame,
    columnas_unicas: pd.DataFrame,
    relaciones_oficiales: pd.DataFrame,
) -> pd.DataFrame:
    """
    Detecta relaciones probables evitando combinaciones masivas.

    Reglas principales:

    - Excluye columnas excesivamente genéricas.
    - Solo usa PK simples o índices únicos de una columna.
    - Evita relaciones que ya sean oficiales.
    - Selecciona únicamente el mejor destino para cada columna origen.
    - Favorece la coincidencia entre columna y nombre de tabla.
    """

    claves_pk, claves_unicas = preparar_conjuntos_clave(
        claves_primarias,
        columnas_unicas,
    )

    relaciones_oficiales_existentes: set[
        tuple[str, str, str, str, str, str]
    ] = set()

    for _, fila in relaciones_oficiales.iterrows():
        relaciones_oficiales_existentes.add(
            (
                str(fila["EsquemaOrigen"]).lower(),
                str(fila["TablaOrigen"]).lower(),
                str(fila["ColumnaOrigen"]).lower(),
                str(fila["EsquemaDestino"]).lower(),
                str(fila["TablaDestino"]).lower(),
                str(fila["ColumnaDestino"]).lower(),
            )
        )

    destinos_por_significado: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for _, fila in columnas.iterrows():
        clave = (
            str(fila["Esquema"]).lower(),
            str(fila["Tabla"]).lower(),
            str(fila["Columna"]).lower(),
        )

        es_pk = clave in claves_pk
        es_unica = clave in claves_unicas

        if not es_pk and not es_unica:
            continue

        if columna_demasiado_generica(
            fila["Columna"]
        ):
            continue

        significado = normalizar_nombre_relacion(
            fila["Columna"]
        )

        if not significado:
            continue

        destino = fila.to_dict()
        destino["EsClavePrimaria"] = es_pk
        destino["EsUnica"] = es_unica

        destinos_por_significado.setdefault(
            significado,
            [],
        ).append(destino)

    relaciones_probables: list[dict[str, Any]] = []

    for _, origen in columnas.iterrows():
        nombre_columna = origen["Columna"]

        if columna_demasiado_generica(
            nombre_columna
        ):
            continue

        significado = normalizar_nombre_relacion(
            nombre_columna
        )

        if not significado:
            continue

        candidatos = destinos_por_significado.get(
            significado,
            [],
        )

        if not candidatos:
            continue

        clave_origen = (
            str(origen["Esquema"]).lower(),
            str(origen["Tabla"]).lower(),
            str(origen["Columna"]).lower(),
        )

        if clave_origen in claves_pk or clave_origen in claves_unicas:
            continue

        mejores_candidatos: list[
            tuple[int, dict[str, Any]]
        ] = []

        for destino in candidatos:
            clave_destino = (
                str(destino["Esquema"]).lower(),
                str(destino["Tabla"]).lower(),
                str(destino["Columna"]).lower(),
            )

            if clave_origen == clave_destino:
                continue

            misma_tabla = (
                str(origen["Esquema"]).lower()
                == str(destino["Esquema"]).lower()
                and str(origen["Tabla"]).lower()
                == str(destino["Tabla"]).lower()
            )

            if misma_tabla:
                continue

            if not tipos_compatibles(
                str(origen["TipoDato"]),
                str(destino["TipoDato"]),
            ):
                continue

            relacion_oficial = (
                str(origen["Esquema"]).lower(),
                str(origen["Tabla"]).lower(),
                str(origen["Columna"]).lower(),
                str(destino["Esquema"]).lower(),
                str(destino["Tabla"]).lower(),
                str(destino["Columna"]).lower(),
            )

            if relacion_oficial in relaciones_oficiales_existentes:
                continue

            puntuacion = calcular_puntuacion_destino(
                origen["Columna"],
                destino["Tabla"],
                destino["Columna"],
                bool(destino["EsClavePrimaria"]),
            )

            mejores_candidatos.append(
                (
                    puntuacion,
                    destino,
                )
            )

        if not mejores_candidatos:
            continue

        mejores_candidatos.sort(
            key=lambda elemento: (
                elemento[0],
                bool(
                    elemento[1]["EsClavePrimaria"]
                ),
                -len(str(elemento[1]["Tabla"])),
                str(elemento[1]["Tabla"]).lower(),
            ),
            reverse=True,
        )

        mejor_puntuacion, mejor_destino = (
            mejores_candidatos[0]
        )

        if mejor_puntuacion < 80:
            continue

        if mejor_puntuacion >= 95:
            confianza = "MUY ALTA"
        elif mejor_puntuacion >= 85:
            confianza = "ALTA"
        else:
            confianza = "MEDIA"

        tipo_destino = (
            "CLAVE PRIMARIA SIMPLE"
            if mejor_destino["EsClavePrimaria"]
            else "ÍNDICE ÚNICO SIMPLE"
        )

        relaciones_probables.append(
            {
                "EsquemaOrigen": origen["Esquema"],
                "TablaOrigen": origen["Tabla"],
                "ColumnaOrigen": origen["Columna"],
                "EsquemaDestino": mejor_destino["Esquema"],
                "TablaDestino": mejor_destino["Tabla"],
                "ColumnaDestino": mejor_destino["Columna"],
                "TipoRelacion": (
                    f"PROBABLE POR {tipo_destino}"
                ),
                "Confianza": confianza,
                "Puntuacion": mejor_puntuacion,
                "NombreRelacion": "",
            }
        )

    columnas_resultado = [
        "EsquemaOrigen",
        "TablaOrigen",
        "ColumnaOrigen",
        "EsquemaDestino",
        "TablaDestino",
        "ColumnaDestino",
        "TipoRelacion",
        "Confianza",
        "Puntuacion",
        "NombreRelacion",
    ]

    if not relaciones_probables:
        return pd.DataFrame(
            columns=columnas_resultado
        )

    resultado = pd.DataFrame(
        relaciones_probables,
        columns=columnas_resultado,
    )

    resultado = resultado.drop_duplicates(
        subset=[
            "EsquemaOrigen",
            "TablaOrigen",
            "ColumnaOrigen",
            "EsquemaDestino",
            "TablaDestino",
            "ColumnaDestino",
        ]
    )

    return resultado.sort_values(
        by=[
            "Puntuacion",
            "TablaDestino",
            "TablaOrigen",
            "ColumnaOrigen",
        ],
        ascending=[
            False,
            True,
            True,
            True,
        ],
    ).reset_index(drop=True)


def crear_resumen(
    columnas: pd.DataFrame,
    claves_primarias: pd.DataFrame,
    columnas_unicas: pd.DataFrame,
    relaciones_oficiales: pd.DataFrame,
    relaciones_probables: pd.DataFrame,
) -> pd.DataFrame:
    """
    Crea el resumen general del análisis.
    """

    numero_tablas = columnas[
        ["Esquema", "Tabla"]
    ].drop_duplicates().shape[0]

    datos = [
        [
            "Fecha de generación",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ],
        [
            "Base de datos",
            "Farmatic",
        ],
        [
            "Modo de acceso",
            "Solo lectura",
        ],
        [
            "Tablas analizadas",
            numero_tablas,
        ],
        [
            "Columnas analizadas",
            len(columnas),
        ],
        [
            "Claves primarias simples",
            len(claves_primarias),
        ],
        [
            "Columnas con índice único simple",
            len(columnas_unicas),
        ],
        [
            "Relaciones oficiales",
            len(relaciones_oficiales),
        ],
        [
            "Relaciones probables",
            len(relaciones_probables),
        ],
        [
            "Relaciones totales",
            len(relaciones_oficiales)
            + len(relaciones_probables),
        ],
    ]

    return pd.DataFrame(
        datos,
        columns=[
            "Concepto",
            "Valor",
        ],
    )


def ajustar_excel(writer: pd.ExcelWriter) -> None:
    """
    Ajusta anchuras, filtros y paneles inmovilizados.
    """

    for hoja in writer.book.worksheets:
        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = hoja.dimensions

        for columna in hoja.columns:
            longitud_maxima = 0
            letra = columna[0].column_letter

            for celda in columna:
                valor = (
                    ""
                    if celda.value is None
                    else str(celda.value)
                )

                longitud_maxima = max(
                    longitud_maxima,
                    len(valor),
                )

            hoja.column_dimensions[letra].width = min(
                longitud_maxima + 2,
                60,
            )


def limpiar_nombre_mermaid(nombre: Any) -> str:
    """
    Convierte un nombre en un identificador seguro para Mermaid.
    """

    texto = str(nombre)
    caracteres = []

    for caracter in texto:
        if caracter.isalnum() or caracter == "_":
            caracteres.append(caracter)
        else:
            caracteres.append("_")

    return "".join(caracteres)


def crear_documento_mermaid(
    relaciones_oficiales: pd.DataFrame,
    relaciones_probables: pd.DataFrame,
) -> str:
    """
    Genera un documento Markdown con un diagrama Mermaid.
    """

    lineas = [
        "# Mapa global de relaciones de Farmatic",
        "",
        "> Documento generado automáticamente.",
        "> Las relaciones probables deben validarse manualmente.",
        "",
        (
            "Fecha de generación: "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ),
        "",
        "## Diagrama de relaciones oficiales",
        "",
        "```mermaid",
        "flowchart LR",
    ]

    relaciones_diagrama: set[
        tuple[str, str, str]
    ] = set()

    relaciones_agrupadas: dict[
        tuple[str, str, str],
        list[str],
    ] = {}

    for _, relacion in relaciones_oficiales.iterrows():
        tabla_origen = (
            f"{relacion['EsquemaOrigen']}."
            f"{relacion['TablaOrigen']}"
        )

        tabla_destino = (
            f"{relacion['EsquemaDestino']}."
            f"{relacion['TablaDestino']}"
        )

        nombre_relacion = str(
            relacion["NombreRelacion"]
        )

        clave = (
            tabla_origen,
            tabla_destino,
            nombre_relacion,
        )

        etiqueta_columna = (
            f"{relacion['ColumnaOrigen']} → "
            f"{relacion['ColumnaDestino']}"
        )

        relaciones_agrupadas.setdefault(
            clave,
            [],
        ).append(etiqueta_columna)

    for (
        tabla_origen,
        tabla_destino,
        nombre_relacion,
    ), columnas_relacion in relaciones_agrupadas.items():
        identificador_origen = limpiar_nombre_mermaid(
            tabla_origen
        )

        identificador_destino = limpiar_nombre_mermaid(
            tabla_destino
        )

        clave_diagrama = (
            identificador_origen,
            identificador_destino,
            nombre_relacion,
        )

        if clave_diagrama in relaciones_diagrama:
            continue

        relaciones_diagrama.add(clave_diagrama)

        etiqueta = " | ".join(
            columnas_relacion
        )

        lineas.append(
            f'    {identificador_origen}["{tabla_origen}"] '
            f'-->|"{etiqueta}"| '
            f'{identificador_destino}["{tabla_destino}"]'
        )

    if relaciones_oficiales.empty:
        lineas.append(
            '    SinRelaciones["No se encontraron claves externas"]'
        )

    lineas.extend(
        [
            "```",
            "",
            "## Relaciones oficiales",
            "",
        ]
    )

    if relaciones_oficiales.empty:
        lineas.append(
            "No se encontraron relaciones oficiales."
        )
    else:
        for _, relacion in relaciones_oficiales.iterrows():
            lineas.append(
                f"- `{relacion['EsquemaOrigen']}."
                f"{relacion['TablaOrigen']}."
                f"{relacion['ColumnaOrigen']}` → "
                f"`{relacion['EsquemaDestino']}."
                f"{relacion['TablaDestino']}."
                f"{relacion['ColumnaDestino']}`"
            )

    lineas.extend(
        [
            "",
            "## Relaciones probables",
            "",
            (
                "Estas relaciones se han inferido por coincidencia "
                "de nombres, tipos y claves simples."
            ),
            "",
        ]
    )

    if relaciones_probables.empty:
        lineas.append(
            "No se encontraron relaciones probables."
        )
    else:
        for _, relacion in relaciones_probables.iterrows():
            lineas.append(
                f"- `{relacion['EsquemaOrigen']}."
                f"{relacion['TablaOrigen']}."
                f"{relacion['ColumnaOrigen']}` ⇢ "
                f"`{relacion['EsquemaDestino']}."
                f"{relacion['TablaDestino']}."
                f"{relacion['ColumnaDestino']}` "
                f"— {relacion['Confianza']} "
                f"({relacion['Puntuacion']}/100)"
            )

    lineas.extend(
        [
            "",
            "## Validación pendiente",
            "",
            (
                "Las relaciones oficiales proceden de las claves "
                "externas declaradas en SQL Server."
            ),
            "",
            (
                "Las relaciones probables son hipótesis técnicas y "
                "deben comprobarse con datos reales y conocimiento "
                "funcional de Farmatic."
            ),
            "",
        ]
    )

    return "\n".join(lineas)


def guardar_resultados(
    resumen: pd.DataFrame,
    columnas: pd.DataFrame,
    claves_primarias: pd.DataFrame,
    columnas_unicas: pd.DataFrame,
    relaciones_oficiales: pd.DataFrame,
    relaciones_probables: pd.DataFrame,
) -> tuple[Path, Path]:
    """
    Guarda el Excel y el documento Markdown.
    """

    raiz_proyecto = Path(__file__).resolve().parents[2]

    carpeta_exportaciones = (
        raiz_proyecto
        / "docs"
        / "exportaciones"
    )

    carpeta_diagramas = (
        raiz_proyecto
        / "docs"
        / "diagramas"
    )

    carpeta_exportaciones.mkdir(
        parents=True,
        exist_ok=True,
    )

    carpeta_diagramas.mkdir(
        parents=True,
        exist_ok=True,
    )

    ruta_excel = (
        carpeta_exportaciones
        / "relaciones_farmatic.xlsx"
    )

    ruta_markdown = (
        carpeta_diagramas
        / "relaciones_farmatic.md"
    )

    relaciones_totales = pd.concat(
        [
            relaciones_oficiales,
            relaciones_probables,
        ],
        ignore_index=True,
    )

    with pd.ExcelWriter(
        ruta_excel,
        engine="openpyxl",
    ) as writer:
        resumen.to_excel(
            writer,
            sheet_name="Resumen",
            index=False,
        )

        relaciones_totales.to_excel(
            writer,
            sheet_name="Todas relaciones",
            index=False,
        )

        relaciones_oficiales.to_excel(
            writer,
            sheet_name="Relaciones oficiales",
            index=False,
        )

        relaciones_probables.to_excel(
            writer,
            sheet_name="Relaciones probables",
            index=False,
        )

        claves_primarias.to_excel(
            writer,
            sheet_name="Claves primarias simples",
            index=False,
        )

        columnas_unicas.to_excel(
            writer,
            sheet_name="Columnas unicas simples",
            index=False,
        )

        columnas.to_excel(
            writer,
            sheet_name="Columnas",
            index=False,
        )

        ajustar_excel(writer)

    documento_markdown = crear_documento_mermaid(
        relaciones_oficiales,
        relaciones_probables,
    )

    ruta_markdown.write_text(
        documento_markdown,
        encoding="utf-8",
    )

    return ruta_excel, ruta_markdown


def mostrar_resumen_terminal(
    resumen: pd.DataFrame,
    relaciones_oficiales: pd.DataFrame,
    relaciones_probables: pd.DataFrame,
) -> None:
    """
    Muestra un resumen del resultado en la terminal.
    """

    print()
    print("=" * 100)
    print("MAPA GLOBAL DE RELACIONES DE FARMATIC")
    print("=" * 100)
    print()

    for _, fila in resumen.iterrows():
        print(
            f"{fila['Concepto']}: "
            f"{fila['Valor']}"
        )

    print()
    print("RELACIONES OFICIALES")
    print("-" * 100)

    if relaciones_oficiales.empty:
        print(
            "No se han encontrado claves externas oficiales."
        )
    else:
        for _, relacion in relaciones_oficiales.head(30).iterrows():
            print(
                f"- {relacion['TablaOrigen']}."
                f"{relacion['ColumnaOrigen']} → "
                f"{relacion['TablaDestino']}."
                f"{relacion['ColumnaDestino']}"
            )

        if len(relaciones_oficiales) > 30:
            print(
                f"... y {len(relaciones_oficiales) - 30} más."
            )

    print()
    print("RELACIONES PROBABLES CON MAYOR CONFIANZA")
    print("-" * 100)

    if relaciones_probables.empty:
        print(
            "No se han encontrado relaciones probables."
        )
    else:
        for _, relacion in relaciones_probables.head(30).iterrows():
            print(
                f"- {relacion['TablaOrigen']}."
                f"{relacion['ColumnaOrigen']} ⇢ "
                f"{relacion['TablaDestino']}."
                f"{relacion['ColumnaDestino']} "
                f"[{relacion['Puntuacion']}/100]"
            )

        if len(relaciones_probables) > 30:
            print(
                f"... y {len(relaciones_probables) - 30} más."
            )


def generar_mapa_relaciones() -> None:
    """
    Ejecuta la herramienta completa.
    """

    conexion = None

    try:
        logger.info(
            "Inicio de generación del mapa de relaciones"
        )

        print()
        print("=" * 100)
        print("HERRAMIENTA 9 - MAPA GLOBAL DE RELACIONES")
        print("=" * 100)
        print()
        print("Conectando con Farmatic...")

        conexion = obtener_conexion()

        print("Leyendo columnas...")
        columnas = obtener_columnas(
            conexion
        )

        print("Leyendo claves primarias simples...")
        claves_primarias = obtener_claves_primarias(
            conexion
        )

        print("Leyendo índices únicos simples...")
        columnas_unicas = obtener_columnas_unicas(
            conexion
        )

        print("Leyendo relaciones oficiales...")
        relaciones_oficiales = obtener_relaciones_oficiales(
            conexion
        )

        print("Buscando relaciones probables...")
        relaciones_probables = detectar_relaciones_probables(
            columnas,
            claves_primarias,
            columnas_unicas,
            relaciones_oficiales,
        )

        resumen = crear_resumen(
            columnas,
            claves_primarias,
            columnas_unicas,
            relaciones_oficiales,
            relaciones_probables,
        )

        mostrar_resumen_terminal(
            resumen,
            relaciones_oficiales,
            relaciones_probables,
        )

        print()
        print("Generando archivos...")

        ruta_excel, ruta_markdown = guardar_resultados(
            resumen,
            columnas,
            claves_primarias,
            columnas_unicas,
            relaciones_oficiales,
            relaciones_probables,
        )

        print()
        print("=" * 100)
        print("MAPA DE RELACIONES GENERADO CORRECTAMENTE")
        print("=" * 100)
        print()
        print("Excel:")
        print(ruta_excel)
        print()
        print("Diagrama y documentación:")
        print(ruta_markdown)

        logger.info(
            (
                "Mapa generado | Oficiales: %s | "
                "Probables: %s"
            ),
            len(relaciones_oficiales),
            len(relaciones_probables),
        )

    except Exception as error:
        logger.exception(
            "Error al generar el mapa de relaciones"
        )

        print()
        print("ERROR al generar el mapa de relaciones:")
        print(error)

        raise

    finally:
        if conexion is not None:
            conexion.close()

            print()
            print("Conexión cerrada correctamente.")


if __name__ == "__main__":
    generar_mapa_relaciones()