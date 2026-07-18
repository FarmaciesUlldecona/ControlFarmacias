import pyodbc

from config.config import NUMERO_ALBARANES_A_LEER
from src.database.conexion_sql import obtener_conexion
from src.models.albaran import Albaran


def obtener_ultimos_albaranes() -> list[Albaran]:
    """
    Obtiene los últimos albaranes de Farmatic según la configuración
    y los devuelve como objetos Albaran.
    """

    consulta = f"""
        SELECT TOP ({NUMERO_ALBARANES_A_LEER})
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
        ORDER BY a.IdContador DESC;
    """

    conexion = None

    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(consulta)

        filas = cursor.fetchall()

        albaranes: list[Albaran] = []

        for fila in filas:
            albaranes.append(
                Albaran(
                    id_contador=fila.IdContador,
                    id_proveedor=int(fila.IdProveedor),
                    proveedor=fila.Proveedor.strip(),
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


def leer_ultimos_albaranes() -> None:
    try:
        albaranes = obtener_ultimos_albaranes()

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
    leer_ultimos_albaranes()