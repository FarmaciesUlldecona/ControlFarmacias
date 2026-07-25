import logging
from pathlib import Path


def obtener_logger(nombre: str = "farmatic") -> logging.Logger:
    """
    Devuelve un logger configurado para escribir
    tanto en pantalla como en un archivo independiente.

    Cada proceso genera su propio archivo de log.
    """

    carpeta_logs = Path("logs")
    carpeta_logs.mkdir(
        parents=True,
        exist_ok=True,
    )

    nombre_archivo = f"{nombre}.log"
    archivo_log = carpeta_logs / nombre_archivo

    logger = logging.getLogger(nombre)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formato = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    manejador_archivo = logging.FileHandler(
        archivo_log,
        encoding="utf-8",
    )
    manejador_archivo.setLevel(logging.INFO)
    manejador_archivo.setFormatter(formato)

    manejador_consola = logging.StreamHandler()
    manejador_consola.setLevel(logging.INFO)
    manejador_consola.setFormatter(formato)

    logger.addHandler(manejador_archivo)
    logger.addHandler(manejador_consola)

    return logger