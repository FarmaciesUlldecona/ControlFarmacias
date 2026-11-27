"""Aislamiento obligatorio de artefactos locales durante pytest y registro de la ejecución (2BH).

Hito SUITE: con pytest-xdist cada worker es un proceso con su propia raíz aislada; solo el proceso principal
escribe el registro de suites, con las cifras de colección que le pasan los workers.
"""

import logging
import os
from pathlib import Path
import shutil
import tempfile

import pytest

from registro_suite import RegistroSuite


_RAIZ_AISLADA = Path(tempfile.mkdtemp(prefix="controlfarmacias_pytest_"))
os.environ["CONTROLFARMACIAS_TEST_MODE"] = "1"
os.environ["CONTROLFARMACIAS_LOG_DIR"] = str(_RAIZ_AISLADA / "logs")
os.environ["CONTROLFARMACIAS_DATA_DIR"] = str(_RAIZ_AISLADA / "data")
_ES_WORKER = "PYTEST_XDIST_WORKER" in os.environ
_REGISTRO = RegistroSuite(worker=_ES_WORKER)


def pytest_sessionstart(session):
    """PERMISOS-1: el proceso principal marca la suite en curso (la quita al terminar)."""
    if not _ES_WORKER:
        _REGISTRO.marcar_inicio()


def pytest_collection_finish(session):
    _REGISTRO.coleccion(session.items)


def pytest_deselected(items):
    _REGISTRO.deseleccion(items)


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    """Proceso principal con xdist: cifras de colección de cada worker."""
    _REGISTRO.datos_worker((getattr(node, "workeroutput", None) or {}).get("registro_suite"))


def pytest_sessionfinish(session, exitstatus):
    """Registra la ejecución (logs/agentes/suites.jsonl), cierra handlers y elimina logs/índices efímeros."""
    if hasattr(session.config, "workeroutput"):
        session.config.workeroutput["registro_suite"] = _REGISTRO.resumen_worker()
    else:
        try:
            _REGISTRO.escribir(session, exitstatus)
        finally:
            _REGISTRO.quitar_marca()
    for logger in logging.Logger.manager.loggerDict.values():
        if not isinstance(logger, logging.Logger):
            continue
        for handler in tuple(logger.handlers):
            archivo = getattr(handler, "baseFilename", None)
            if archivo and Path(archivo).is_relative_to(_RAIZ_AISLADA):
                logger.removeHandler(handler)
                handler.close()
    shutil.rmtree(_RAIZ_AISLADA, ignore_errors=True)
