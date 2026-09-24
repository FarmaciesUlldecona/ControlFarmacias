"""Aislamiento obligatorio de artefactos locales durante pytest."""

import logging
import os
from pathlib import Path
import shutil
import tempfile


_RAIZ_AISLADA = Path(tempfile.mkdtemp(prefix="controlfarmacias_pytest_"))
os.environ["CONTROLFARMACIAS_TEST_MODE"] = "1"
os.environ["CONTROLFARMACIAS_LOG_DIR"] = str(_RAIZ_AISLADA / "logs")
os.environ["CONTROLFARMACIAS_DATA_DIR"] = str(_RAIZ_AISLADA / "data")


def pytest_sessionfinish(session, exitstatus):
    """Cierra handlers y elimina logs/índices efímeros de la certificación."""
    del session, exitstatus
    for logger in logging.Logger.manager.loggerDict.values():
        if not isinstance(logger, logging.Logger):
            continue
        for handler in tuple(logger.handlers):
            archivo = getattr(handler, "baseFilename", None)
            if archivo and Path(archivo).is_relative_to(_RAIZ_AISLADA):
                logger.removeHandler(handler)
                handler.close()
    shutil.rmtree(_RAIZ_AISLADA, ignore_errors=True)
