from .base import AdaptadorBase, Reconocimiento
from .cofares import AdaptadorCofares
from .fedefarma import AdaptadorFedefarma
from .hefame import AdaptadorHefame
from .hplus_consumo import AdaptadorHplusConsumo
from .alliance import AdaptadorAlliance
from .registro import adaptadores_locales, adaptadores_productivos

__all__ = [
    "AdaptadorBase", "AdaptadorCofares", "AdaptadorFedefarma", "AdaptadorHefame", "AdaptadorHplusConsumo", "AdaptadorAlliance",
    "Reconocimiento", "adaptadores_locales", "adaptadores_productivos",
]
