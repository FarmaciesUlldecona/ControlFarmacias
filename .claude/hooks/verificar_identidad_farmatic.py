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

Trazabilidad: cada decisión sobre un comando con patrón sensible, y cada
error interno, se añade como una línea JSON a
``%LOCALAPPDATA%\\ControlFarmacias\\hooks\\identidad_farmatic.jsonl``, fuera
del repositorio y de los logs productivos. Nunca se registra el texto del
comando ni el mensaje de las excepciones. Un fallo al escribir el registro no
cambia la decisión.

Solo usa la biblioteca estándar. Se lanza con ``-I -S -B`` desde el Python
del ``.venv``.
"""

import datetime
import json
import os
import subprocess
import sys
from typing import NamedTuple


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

NOMBRE_REGISTRO = "identidad_farmatic.jsonl"
TAMANO_MAXIMO_REGISTRO = 5 * 1024 * 1024


class Evaluacion(NamedTuple):
    codigo: int
    mensaje: str
    patron: str | None = None
    identidad: str | None = None
    motivo: str | None = None


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


def evaluar(entrada: dict, obtener_identidad=obtener_identidad) -> Evaluacion:
    comando = extraer_comando(entrada)

    if comando is None:
        return Evaluacion(0, "")

    patron = patron_sensible(comando)

    if patron is None:
        return Evaluacion(0, "")

    try:
        identidad = obtener_identidad()
    except BaseException as error:
        # Se relanza la misma excepción; el patrón solo sirve al registro.
        try:
            error.patron_hook = patron
        except BaseException:
            pass
        raise

    if identidad != IDENTIDAD_ESPERADA:
        return Evaluacion(
            2,
            (
                "BLOQUEADO por el hook de identidad Farmatic: el comando "
                f"contiene {patron!r} y whoami devolvió {identidad!r}; se "
                f"exige {IDENTIDAD_ESPERADA!r}. Abre Visual Studio Code como "
                "ControlFarmaciasRO."
            ),
            patron,
            identidad,
            "identidad_distinta",
        )

    return Evaluacion(0, "", patron, identidad)


def decidir(entrada: dict, obtener_identidad=obtener_identidad) -> tuple[int, str]:
    evaluacion = evaluar(entrada, obtener_identidad)
    return evaluacion.codigo, evaluacion.mensaje


def ruta_registro() -> str:
    return os.path.join(
        os.environ["LOCALAPPDATA"],
        "ControlFarmacias",
        "hooks",
        NOMBRE_REGISTRO,
    )


def ahora() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def registrar_evento(
    herramienta,
    evaluacion: Evaluacion,
    ruta: str | None = None,
    reloj=ahora,
) -> None:
    """Añade una línea JSON al registro. Nunca propaga errores."""

    try:
        if evaluacion.patron is None and evaluacion.motivo is None:
            return

        if ruta is None:
            ruta = ruta_registro()

        evento = {
            "ts": reloj().isoformat(timespec="milliseconds"),
            "herramienta": herramienta if isinstance(herramienta, str) else None,
            "patron": evaluacion.patron,
            "identidad": evaluacion.identidad,
            "decision": "permitido" if evaluacion.codigo == 0 else "bloqueado",
            "motivo": evaluacion.motivo,
        }
        linea = json.dumps(evento, ensure_ascii=False) + "\n"

        os.makedirs(os.path.dirname(ruta), exist_ok=True)

        try:
            if os.path.getsize(ruta) >= TAMANO_MAXIMO_REGISTRO:
                os.replace(ruta, ruta + ".1")
        except FileNotFoundError:
            pass

        with open(ruta, "a", encoding="utf-8", newline="\n") as archivo:
            archivo.write(linea)
    except BaseException:
        pass


def main() -> int:
    herramienta = None

    try:
        entrada = json.loads(sys.stdin.buffer.read())

        if not isinstance(entrada, dict):
            raise ValueError("la entrada del hook no es un objeto")

        herramienta = entrada.get("tool_name")
        evaluacion = evaluar(entrada, obtener_identidad)
    except BaseException as error:
        patron = getattr(error, "patron_hook", None)
        evaluacion = Evaluacion(
            2,
            (
                "BLOQUEADO: error interno del hook de identidad Farmatic "
                f"({type(error).__name__}: {error})."
            ),
            patron if isinstance(patron, str) else None,
            None,
            f"error_interno:{type(error).__name__}",
        )

    registrar_evento(herramienta, evaluacion)

    if evaluacion.mensaje:
        try:
            sys.stderr.write(evaluacion.mensaje + "\n")
        except BaseException:
            pass

    return evaluacion.codigo


if __name__ == "__main__":
    sys.exit(main())
