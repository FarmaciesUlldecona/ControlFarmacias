"""Hook PreToolUse de Claude Code: identidad Windows antes de acceder a Farmatic.

Se ejecuta antes de cada comando de Bash, PowerShell o Monitor. Si el comando
nombra un módulo o cliente que puede conectar con Farmatic, exige que
``whoami`` devuelva exactamente ``mostrador\\controlfarmaciasro``; en otro
caso devuelve exit 2 y Claude Code bloquea el comando.

Es una capa previa a ``obtener_conexion()`` y no la sustituye: la barrera
efectiva es la certificación de identidad y permisos de SQL Server que hace
``src/database/conexion_sql.py`` al abrir cada conexión.

Cualquier error interno devuelve exit 2 (bloquea). LIMITACIÓN CONOCIDA,
aceptada por Pio: según la semántica de Claude Code, un fallo de arranque del
intérprete (exit distinto de 2), un error de sintaxis de este archivo (exit 1)
o el timeout del hook no bloquean el comando.

Solo usa la biblioteca estándar. Se lanza con ``-I -S -B`` desde el Python
del ``.venv``.
"""

import json
import os
import subprocess
import sys


IDENTIDAD_ESPERADA = "mostrador\\controlfarmaciasro"

# Subcadenas, comparadas sin distinguir mayúsculas, que activan la
# comprobación. Cubren la forma de módulo (src.sql_explorer.x) y la de ruta
# (src\sql_explorer\x.py).
PATRONES = (
    "sql_explorer",
    "leer_albaranes",
    "conexion_sql",
    "obtener_conexion",
    "sincronizar_albaranes",
    "importar_albaranes_historicos",
    "probar_albaranes",
    "explorar_base_datos",
    "importar_facturas_drive",
    "ejecutar_sincronizacion",
    "ejecutar_importacion_facturas",
    "odbc",
    "sqlcmd",
    "sqlclient",
    "mssql",
)

TIMEOUT_WHOAMI_SEGUNDOS = 10


def extraer_comando(entrada: dict) -> str | None:
    """Devuelve el comando a revisar, o None si la herramienta no ejecuta uno."""

    tool_input = entrada["tool_input"]

    if not isinstance(tool_input, dict):
        raise ValueError("tool_input no es un objeto")

    comando = tool_input.get("command")

    if comando is None:
        if entrada.get("tool_name") == "Monitor" and "ws" in tool_input:
            return None
        raise ValueError("la herramienta no declara command")

    if not isinstance(comando, str):
        raise ValueError("command no es texto")

    return comando


def patron_sensible(comando: str) -> str | None:
    texto = comando.casefold()

    for patron in PATRONES:
        if patron in texto:
            return patron

    return None


def obtener_identidad() -> str:
    whoami = os.path.join(
        os.environ["SystemRoot"],
        "System32",
        "whoami.exe",
    )
    resultado = subprocess.run(
        [whoami],
        capture_output=True,
        text=True,
        timeout=TIMEOUT_WHOAMI_SEGUNDOS,
        check=True,
    )
    return resultado.stdout.strip()


def decidir(entrada: dict, obtener_identidad=obtener_identidad) -> tuple[int, str]:
    comando = extraer_comando(entrada)

    if comando is None:
        return 0, ""

    patron = patron_sensible(comando)

    if patron is None:
        return 0, ""

    identidad = obtener_identidad()

    if identidad != IDENTIDAD_ESPERADA:
        return 2, (
            "BLOQUEADO por el hook de identidad Farmatic: el comando contiene "
            f"{patron!r} y whoami devolvió {identidad!r}; se exige "
            f"{IDENTIDAD_ESPERADA!r}. Abre Visual Studio Code como "
            "ControlFarmaciasRO."
        )

    return 0, ""


def main() -> int:
    try:
        entrada = json.loads(sys.stdin.buffer.read())

        if not isinstance(entrada, dict):
            raise ValueError("la entrada del hook no es un objeto")

        codigo, mensaje = decidir(entrada, obtener_identidad)
    except BaseException as error:
        codigo, mensaje = 2, (
            "BLOQUEADO: error interno del hook de identidad Farmatic "
            f"({type(error).__name__}: {error})."
        )

    if mensaje:
        try:
            sys.stderr.write(mensaje + "\n")
        except BaseException:
            pass

    return codigo


if __name__ == "__main__":
    sys.exit(main())
