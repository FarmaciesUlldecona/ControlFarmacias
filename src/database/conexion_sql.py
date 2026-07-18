import pyodbc


def obtener_conexion():
    conexion = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=MOSTRADOR;"
        "DATABASE=Farmatic;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )

    return conexion