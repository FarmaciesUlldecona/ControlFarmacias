import pyodbc


def main() -> None:
    drivers = pyodbc.drivers()

    if not drivers:
        print("No se ha encontrado ningún controlador ODBC.")
        return

    print("Controladores ODBC instalados:")

    for driver in drivers:
        print(f"- {driver}")


if __name__ == "__main__":
    main()