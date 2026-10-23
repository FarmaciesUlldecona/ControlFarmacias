"""Utilidades compartidas por los hooks de agentes: huella de cambios y registro.

La huella identifica el estado exacto de los cambios respecto de ``HEAD``:
commit base más, por cada ruta que ``git status`` declara cambiada (incluidas
las no rastreadas), el SHA-256 de su contenido en disco o ``BORRADO``. No
depende del índice, así que es la misma antes y después de ``git add -A``.
``logs/`` está ignorado por Git, de modo que escribir los registros no la
cambia.

Solo usa la biblioteca estándar.
"""

import hashlib
import json
import os
import shutil
import subprocess


DIRECTORIO_PROYECTO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
NOMBRE_USO = "uso.jsonl"
AGENTE_REVISOR = "revisor-reglas"
TIMEOUT_GIT_SEGUNDOS = 30


def directorio_logs() -> str:
    # Misma convención que src/utils/logger.py: pytest apunta
    # CONTROLFARMACIAS_LOG_DIR a una raíz temporal (tests/conftest.py).
    raiz = os.environ.get("CONTROLFARMACIAS_LOG_DIR") or os.path.join(DIRECTORIO_PROYECTO, "logs")
    return os.path.join(raiz, "agentes")


def ruta_uso() -> str:
    return os.path.join(directorio_logs(), NOMBRE_USO)


def _git(*argumentos: str, directorio: str) -> bytes:
    ejecutable = shutil.which("git")
    if ejecutable is None:
        raise RuntimeError("git no está en PATH")
    resultado = subprocess.run(
        [ejecutable, *argumentos],
        cwd=directorio,
        capture_output=True,
        timeout=TIMEOUT_GIT_SEGUNDOS,
        check=True,
    )
    return resultado.stdout


def raiz_repositorio(directorio: str) -> str:
    return _git("rev-parse", "--show-toplevel", directorio=directorio).decode("utf-8").strip()


def rutas_cambiadas(directorio: str = DIRECTORIO_PROYECTO) -> list[str]:
    salida = _git(
        "status", "--porcelain=v1", "-z", "--untracked-files=all",
        directorio=directorio,
    ).decode("utf-8")
    campos = salida.split("\0")
    rutas: list[str] = []
    i = 0
    while i < len(campos):
        campo = campos[i]
        i += 1
        if not campo:
            continue
        estado, ruta = campo[:2], campo[3:]
        rutas.append(ruta)
        if "R" in estado or "C" in estado:
            # El origen del renombrado viene en el campo siguiente.
            rutas.append(campos[i])
            i += 1
    return sorted(set(rutas))


def huella_cambios(directorio: str = DIRECTORIO_PROYECTO) -> str:
    base = _git("rev-parse", "HEAD", directorio=directorio).decode("ascii").strip()
    elementos = []
    for ruta in rutas_cambiadas(directorio):
        completa = os.path.join(directorio, ruta)
        if os.path.isfile(completa):
            with open(completa, "rb") as archivo:
                contenido = hashlib.sha256(archivo.read()).hexdigest()
        else:
            contenido = "BORRADO"
        elementos.append([ruta, contenido])
    texto = json.dumps({"base": base, "rutas": elementos}, sort_keys=True)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def leer_uso(ruta: str | None = None) -> list[dict]:
    ruta = ruta or ruta_uso()
    registros = []
    try:
        with open(ruta, encoding="utf-8") as archivo:
            for linea in archivo:
                try:
                    registro = json.loads(linea)
                except ValueError:
                    continue
                if isinstance(registro, dict):
                    registros.append(registro)
    except FileNotFoundError:
        pass
    return registros


def clave_repositorio(raiz: str) -> str:
    return os.path.normcase(os.path.realpath(raiz))


def ultimo_veredicto_revisor(ruta: str | None = None, repositorio: str = DIRECTORIO_PROYECTO) -> dict | None:
    """Último veredicto de revisor-reglas sobre ``repositorio``.

    Los veredictos de otros repositorios (worktrees temporales) se ignoran; un
    registro sin repositorio cuenta como del proyecto.
    """

    clave = clave_repositorio(repositorio)
    for registro in reversed(leer_uso(ruta)):
        if registro.get("agent_type") != AGENTE_REVISOR:
            continue
        if registro.get("repositorio", clave) == clave:
            return registro
    return None
