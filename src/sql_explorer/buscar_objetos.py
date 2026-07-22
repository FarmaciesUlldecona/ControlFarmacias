from src.sql_explorer.listar_objetos import obtener_tablas_y_vistas


def buscar_objetos(texto_busqueda: str) -> list[dict]:
    """
    Busca tablas y vistas cuyo nombre contenga el texto indicado.

    La búsqueda se realiza sobre el inventario ya leído desde SQL Server.
    No modifica ningún dato.
    """

    texto = texto_busqueda.strip().lower()

    if not texto:
        raise ValueError("Debes indicar un texto de búsqueda.")

    objetos = obtener_tablas_y_vistas()

    resultados = [
        objeto
        for objeto in objetos
        if texto in objeto["nombre"].lower()
        or texto in objeto["esquema"].lower()
    ]

    return resultados


def mostrar_resultados(texto_busqueda: str) -> None:
    resultados = buscar_objetos(texto_busqueda)

    print("=" * 70)
    print(f"RESULTADOS PARA: {texto_busqueda}")
    print("=" * 70)

    if not resultados:
        print("No se han encontrado tablas ni vistas.")
        return

    for objeto in resultados:
        tipo_legible = (
            "TABLA"
            if objeto["tipo"] == "BASE TABLE"
            else "VISTA"
        )

        print(
            f"{tipo_legible:<8} "
            f"{objeto['esquema']}.{objeto['nombre']}"
        )

    print()
    print(f"Total de resultados: {len(resultados)}")
    print("OK: búsqueda realizada sin modificar SQL Server.")


def ejecutar_programa() -> None:
    texto_busqueda = input(
        "Texto que quieres buscar en tablas y vistas: "
    )

    mostrar_resultados(texto_busqueda)


if __name__ == "__main__":
    ejecutar_programa()