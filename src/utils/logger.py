import logging
from pathlib import Path


def obtener_logger(nombre: str = "farmatic") -> logging.Logger:
    """
    Devuelve un logger configurado para escribir
    tanto en pantalla como en un archivo.
    """

    # Carpeta de logs
    carpeta_logs = Path("logs")
    carpeta_logs.mkdir(exist_ok=True)

    # Archivo de log
    archivo_log = carpeta_logs / "programa.log"

    # Crear logger
    logger = logging.getLogger(nombre)

    # Evitar añadir manejadores varias veces
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Formato de los mensajes
    formato = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    # Escribir en archivo
    archivo = logging.FileHandler(
        archivo_log,
        encoding="utf-8"
    )
    archivo.setFormatter(formato)

    # Escribir también en consola
    consola = logging.StreamHandler()
    consola.setFormatter(formato)

    logger.addHandler(archivo)
    logger.addHandler(consola)

    return logger