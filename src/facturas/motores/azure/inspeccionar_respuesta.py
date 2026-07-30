from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RUTA_PROYECTO = Path(__file__).resolve().parents[4]

RUTA_RESULTADOS_ORIGINALES = (
    RUTA_PROYECTO
    / "pruebas"
    / "facturas"
    / "resultados"
    / "azure"
    / "originales"
)


def buscar_ultimo_json() -> Path:
    """
    Localiza el JSON original de Azure modificado más recientemente.
    """
    if not RUTA_RESULTADOS_ORIGINALES.exists():
        raise FileNotFoundError(
            f"No existe la carpeta: {RUTA_RESULTADOS_ORIGINALES}"
        )

    archivos_json = [
        ruta
        for ruta in RUTA_RESULTADOS_ORIGINALES.glob("*.json")
        if ruta.is_file()
    ]

    if not archivos_json:
        raise FileNotFoundError(
            f"No se encontraron archivos JSON en: "
            f"{RUTA_RESULTADOS_ORIGINALES}"
        )

    return max(
        archivos_json,
        key=lambda ruta: ruta.stat().st_mtime,
    )


def cargar_json(ruta_json: Path) -> dict[str, Any]:
    """
    Carga y valida la raíz del JSON original de Azure.
    """
    try:
        with ruta_json.open(
            mode="r",
            encoding="utf-8",
        ) as archivo:
            datos = json.load(archivo)

    except json.JSONDecodeError as error:
        raise ValueError(
            f"JSON inválido. Línea {error.lineno}, "
            f"columna {error.colno}: {error.msg}"
        ) from error

    if not isinstance(datos, dict):
        raise ValueError(
            "La raíz de la respuesta de Azure debe ser un objeto JSON."
        )

    return datos


def obtener_clave(
    objeto: dict[str, Any],
    clave_snake: str,
    clave_camel: str,
) -> Any:
    """
    Obtiene una clave admitiendo formato snake_case o camelCase.
    """
    if clave_snake in objeto:
        return objeto[clave_snake]

    return objeto.get(clave_camel)


def describir_valor(valor: Any) -> str:
    """
    Devuelve una descripción breve del tipo y tamaño de un valor.
    """
    if valor is None:
        return "null"

    if isinstance(valor, dict):
        return f"objeto con {len(valor)} claves"

    if isinstance(valor, list):
        return f"lista con {len(valor)} elementos"

    if isinstance(valor, str):
        texto = valor.replace("\n", " ").strip()

        if len(texto) > 100:
            texto = texto[:97] + "..."

        return f"texto: {texto!r}"

    return f"{type(valor).__name__}: {valor!r}"


def mostrar_claves_objeto(
    titulo: str,
    objeto: dict[str, Any],
) -> None:
    """
    Muestra las claves de un objeto y una descripción de sus valores.
    """
    print()
    print(titulo)
    print("-" * len(titulo))

    for clave, valor in objeto.items():
        print(f"{clave}: {describir_valor(valor)}")


def inspeccionar_documentos(
    documentos: Any,
) -> None:
    """
    Inspecciona los documentos estructurados devueltos por Azure.
    """
    print()
    print("DOCUMENTOS ESTRUCTURADOS")
    print("------------------------")

    if not isinstance(documentos, list):
        print("La clave documents no contiene una lista.")
        return

    print(f"Cantidad: {len(documentos)}")

    for indice, documento in enumerate(
        documentos,
        start=1,
    ):
        print()
        print(f"DOCUMENTO {indice}")
        print("-" * 20)

        if not isinstance(documento, dict):
            print(describir_valor(documento))
            continue

        doc_type = obtener_clave(
            documento,
            "doc_type",
            "docType",
        )

        bounding_regions = obtener_clave(
            documento,
            "bounding_regions",
            "boundingRegions",
        )

        print(f"doc_type: {doc_type}")
        print(f"confidence: {documento.get('confidence')}")
        print(
            f"bounding_regions: "
            f"{describir_valor(bounding_regions)}"
        )

        campos = documento.get("fields")

        if not isinstance(campos, dict):
            print("fields: no disponible")
            continue

        print(f"Campos detectados: {len(campos)}")

        for nombre_campo, contenido_campo in campos.items():
            print()
            print(f"  {nombre_campo}")

            if not isinstance(contenido_campo, dict):
                print(
                    f"    valor: "
                    f"{describir_valor(contenido_campo)}"
                )
                continue

            tipo = contenido_campo.get("type")
            contenido = contenido_campo.get("content")
            confianza = contenido_campo.get("confidence")

            print(f"    type: {tipo}")
            print(f"    content: {contenido!r}")
            print(f"    confidence: {confianza}")

            claves_valor = (
                ("value_string", "valueString"),
                ("value_date", "valueDate"),
                ("value_number", "valueNumber"),
                ("value_currency", "valueCurrency"),
                ("value_array", "valueArray"),
                ("value_object", "valueObject"),
            )

            for clave_snake, clave_camel in claves_valor:
                valor = obtener_clave(
                    contenido_campo,
                    clave_snake,
                    clave_camel,
                )

                if valor is not None:
                    print(
                        f"    {clave_camel}: "
                        f"{describir_valor(valor)}"
                    )


def inspeccionar_tablas(
    tablas: Any,
) -> None:
    """
    Resume todas las tablas detectadas por Azure.
    """
    print()
    print("TABLAS")
    print("------")

    if not isinstance(tablas, list):
        print("La clave tables no contiene una lista.")
        return

    print(f"Cantidad: {len(tablas)}")

    for indice, tabla in enumerate(
        tablas,
        start=1,
    ):
        if not isinstance(tabla, dict):
            continue

        filas = obtener_clave(
            tabla,
            "row_count",
            "rowCount",
        )

        columnas = obtener_clave(
            tabla,
            "column_count",
            "columnCount",
        )

        celdas = tabla.get("cells")

        print()
        print(f"Tabla {indice}")
        print(f"Filas: {filas}")
        print(f"Columnas: {columnas}")

        if not isinstance(celdas, list):
            print("Celdas: no disponibles")
            continue

        print(f"Celdas: {len(celdas)}")

        for celda in celdas:
            if not isinstance(celda, dict):
                continue

            fila = obtener_clave(
                celda,
                "row_index",
                "rowIndex",
            )

            columna = obtener_clave(
                celda,
                "column_index",
                "columnIndex",
            )

            fila_span = obtener_clave(
                celda,
                "row_span",
                "rowSpan",
            )

            columna_span = obtener_clave(
                celda,
                "column_span",
                "columnSpan",
            )

            kind = celda.get("kind")
            content = celda.get("content")

            print(
                f"  Fila {fila}, columna {columna}, "
                f"fila_span {fila_span}, "
                f"columna_span {columna_span}, "
                f"kind {kind}: {content!r}"
            )


def inspeccionar_paginas(
    paginas: Any,
) -> None:
    """
    Resume las páginas y líneas OCR detectadas.
    """
    print()
    print("PÁGINAS")
    print("-------")

    if not isinstance(paginas, list):
        print("La clave pages no contiene una lista.")
        return

    print(f"Cantidad: {len(paginas)}")

    for pagina in paginas:
        if not isinstance(pagina, dict):
            continue

        numero = obtener_clave(
            pagina,
            "page_number",
            "pageNumber",
        )

        lineas = pagina.get("lines")

        print()
        print(f"Página {numero}")
        print(
            f"Líneas OCR: "
            f"{len(lineas) if isinstance(lineas, list) else 0}"
        )

        if isinstance(lineas, list):
            for linea in lineas:
                if isinstance(linea, dict):
                    print(
                        f"  {linea.get('content')}"
                    )


def ejecutar() -> None:
    ruta_json = buscar_ultimo_json()
    datos = cargar_json(ruta_json)

    print("INSPECCIÓN DE RESPUESTA ORIGINAL DE AZURE")
    print("----------------------------------------")
    print(f"Archivo: {ruta_json.name}")

    mostrar_claves_objeto(
        titulo="CLAVES PRINCIPALES",
        objeto=datos,
    )

    inspeccionar_documentos(
        datos.get("documents")
    )

    inspeccionar_tablas(
        datos.get("tables")
    )

    inspeccionar_paginas(
        datos.get("pages")
    )


if __name__ == "__main__":
    ejecutar()