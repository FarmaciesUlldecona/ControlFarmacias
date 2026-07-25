from datetime import date

import pyodbc

from src.database.conexion_sql import obtener_conexion
from src.models.albaran import Albaran


def convertir_fila_en_albaran(fila) -> Albaran:
    """
    Convierte una fila devuelta por SQL Server en un objeto Albaran.
    """

    proveedor = (
        fila.Proveedor.strip()
        if fila.Proveedor is not None
        else ""
    )

    id_albaran = (
        fila.IdAlbaran.strip()
        if fila.IdAlbaran is not None
        else ""
    )

    return Albaran(
        id_contador=int(fila.IdContador),
        id_proveedor=int(fila.IdProveedor),
        proveedor=proveedor,
        id_albaran=id_albaran,
        fecha=fila.Fecha,
        importe_pvp=float(fila.ImportePVP),
        importe_puc=float(fila.ImportePUC),
        dto=float(fila.Dto),
    )


def obtener_nuevos_albaranes(
    ultimo_id_contador: int,
) -> list[Albaran]:
    """
    Lee de Farmatic únicamente los albaranes cuyo IdContador
    sea superior al último que ya existe en Supabase.

    SQL Server se utiliza exclusivamente en modo lectura.
    """

    consulta = """
        SELECT
            a.IdContador,
            a.IdProveedor,
            p.FIS_NOMBRE AS Proveedor,
            a.IdAlbaran,
            a.Fecha,
            a.ImportePVP,
            a.ImportePUC,
            a.Dto
        FROM dbo.Albaran AS a
        LEFT JOIN dbo.Proveedor AS p
            ON a.IdProveedor = p.IDPROVEEDOR
        WHERE a.IdContador > ?
        ORDER BY a.IdContador ASC;
    """

    conexion = None

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()

        cursor.execute(
            consulta,
            ultimo_id_contador,
        )

        filas = cursor.fetchall()

        return [
            convertir_fila_en_albaran(fila)
            for fila in filas
        ]

    finally:
        if conexion is not None:
            conexion.close()


def obtener_albaranes_desde_fecha(
    fecha_inicio: date,
) -> list[Albaran]:
    """
    Lee de Farmatic todos los albaranes cuya fecha sea igual
    o posterior a la fecha indicada.

    Esta función se utilizará para la carga histórica inicial.

    SQL Server se utiliza exclusivamente en modo lectura.
    """

    consulta = """
        SELECT
            a.IdContador,
            a.IdProveedor,
            p.FIS_NOMBRE AS Proveedor,
            a.IdAlbaran,
            a.Fecha,
            a.ImportePVP,
            a.ImportePUC,
            a.Dto
        FROM dbo.Albaran AS a
        LEFT JOIN dbo.Proveedor AS p
            ON a.IdProveedor = p.IDPROVEEDOR
        WHERE a.Fecha >= ?
        ORDER BY a.IdContador ASC;
    """

    conexion = None

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()

        cursor.execute(
            consulta,
            fecha_inicio,
        )

        filas = cursor.fetchall()

        return [
            convertir_fila_en_albaran(fila)
            for fila in filas
        ]

    finally:
        if conexion is not None:
            conexion.close()


def probar_albaranes_desde_fecha() -> None:
    """
    Prueba controlada de lectura desde el 01/06/2026.

    No guarda nada en Supabase.
    No modifica Farmatic.
    Solo ejecuta una consulta SELECT y muestra un resumen.
    """

    fecha_inicio = date(2026, 6, 1)

    try:
        albaranes = obtener_albaranes_desde_fecha(
            fecha_inicio
        )

        print()
        print("PRUEBA DE CARGA HISTORICA")
        print("-------------------------")
        print(f"Fecha inicial: {fecha_inicio:%d/%m/%Y}")
        print(f"Albaranes encontrados: {len(albaranes)}")

        if not albaranes:
            print("No se han encontrado albaranes.")
            return

        primer_albaran = albaranes[0]
        ultimo_albaran = albaranes[-1]

        print()
        print("Primer albaran encontrado:")
        print(
            f"IdContador: {primer_albaran.id_contador} | "
            f"Fecha: {primer_albaran.fecha:%d/%m/%Y} | "
            f"Proveedor: {primer_albaran.proveedor} | "
            f"Numero: {primer_albaran.id_albaran}"
        )

        print()
        print("Ultimo albaran encontrado:")
        print(
            f"IdContador: {ultimo_albaran.id_contador} | "
            f"Fecha: {ultimo_albaran.fecha:%d/%m/%Y} | "
            f"Proveedor: {ultimo_albaran.proveedor} | "
            f"Numero: {ultimo_albaran.id_albaran}"
        )

        print()
        print("Prueba finalizada correctamente.")
        print("No se ha guardado ningun dato en Supabase.")

    except pyodbc.Error as error:
        print()
        print("ERROR al conectar o consultar Farmatic:")
        print(error)


if __name__ == "__main__":
    probar_albaranes_desde_fecha()