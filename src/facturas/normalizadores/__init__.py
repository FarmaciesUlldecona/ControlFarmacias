"""Normalizadores deterministas de facturas."""

from .alliance import ConfiguracionAlliance, normalizar_alliance
from .dermofarm import ConfiguracionDermofarm, normalizar_dermofarm
from .estandar import normalizar_estandar
from .fedefarma import ConfiguracionFedefarma, normalizar_fedefarma
from .suavinex import ConfiguracionSuavinex, normalizar_suavinex

__all__ = [
    "ConfiguracionAlliance",
    "ConfiguracionDermofarm",
    "ConfiguracionFedefarma",
    "ConfiguracionSuavinex",
    "normalizar_alliance",
    "normalizar_dermofarm",
    "normalizar_estandar",
    "normalizar_fedefarma",
    "normalizar_suavinex",
]
