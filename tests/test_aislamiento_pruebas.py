import importlib
import os
from pathlib import Path


def test_pytest_redirige_logs_y_datos_fuera_del_repositorio():
    raiz = Path(__file__).resolve().parents[1]
    logs = Path(os.environ["CONTROLFARMACIAS_LOG_DIR"])
    datos = Path(os.environ["CONTROLFARMACIAS_DATA_DIR"])

    assert logs.is_absolute() and datos.is_absolute()
    assert raiz not in logs.parents
    assert raiz not in datos.parents
    assert logs.name == "logs"
    assert datos.name == "data"


def test_logger_de_prueba_escribe_solo_en_ruta_aislada():
    from src.utils.logger import obtener_logger

    logger = obtener_logger("aislamiento_hito_0")
    archivo = next(
        Path(handler.baseFilename)
        for handler in logger.handlers
        if hasattr(handler, "baseFilename")
    )
    assert archivo.parent == Path(os.environ["CONTROLFARMACIAS_LOG_DIR"])


def test_indice_de_ingesta_usa_ruta_aislada():
    modulo = importlib.import_module("src.facturas.importar_facturas_drive")
    assert modulo.CARPETA_DATOS == Path(
        os.environ["CONTROLFARMACIAS_DATA_DIR"]
    )
