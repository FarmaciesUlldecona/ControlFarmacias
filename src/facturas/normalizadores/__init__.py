"""Normalizadores deterministas de facturas."""

from .alliance import ConfiguracionAlliance, normalizar_alliance
from .dermofarm import ConfiguracionDermofarm, normalizar_dermofarm
from .suavinex import ConfiguracionSuavinex, normalizar_suavinex

__all__ = [
    "ConfiguracionAlliance",
    "ConfiguracionDermofarm",
    "ConfiguracionSuavinex",
    "normalizar_alliance",
    "normalizar_dermofarm",
    "normalizar_suavinex",
]
