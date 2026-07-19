import pyodbc

from src.database.conexion_sql import obtener_conexion
from src.models.albaran import Albaran


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
        albaranes: list[Albaran] = []

        for fila in filas:
            proveedor = (
                fila.Proveedor.strip()
                if fila.Proveedor is not None
                else ""
            )

            albaranes.append(
                Albaran(
                    id_contador=int(fila.IdContador),
                    id_proveedor=int(fila.IdProveedor),
                    proveedor=proveedor,
                    id_albaran=fila.IdAlbaran.strip(),
                    fecha=fila.Fecha,
                    importe_pvp=float(fila.ImportePVP),
                    importe_puc=float(fila.ImportePUC),
                    dto=float(fila.Dto),
                )
            )

        return albaranes

    finally:
        if conexion is not None:
            conexion.close()


def leer_nuevos_albaranes(
    ultimo_id_contador: int = 0,
) -> None:
    """
    Función de prueba para mostrar en pantalla los albaranes
    posteriores al IdContador indicado.
    """

    try:
        albaranes = obtener_nuevos_albaranes(
            ultimo_id_contador
        )

        print(f"\nAlbaranes encontrados: {len(albaranes)}\n")

        for albaran in albaranes:
            print(
                f"Contador: {albaran.id_contador} | "
                f"Proveedor: {albaran.proveedor} | "
                f"Albarán: {albaran.id_albaran} | "
                f"Fecha: {albaran.fecha:%d/%m/%Y} | "
                f"PVP: {albaran.importe_pvp:.2f} € | "
                f"PUC: {albaran.importe_puc:.2f} € | "
                f"Dto.: {albaran.dto:.2f} %"
            )

    except pyodbc.Error as error:
        print("\nERROR al conectar o consultar Farmatic:")
        print(error)


if __name__ == "__main__":
    leer_nuevos_albaranes()