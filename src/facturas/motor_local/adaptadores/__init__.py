from .base import AdaptadorBase, Reconocimiento
from .cofares import AdaptadorCofares
from .fedefarma import AdaptadorFedefarma
from .hefame import AdaptadorHefame
from .registro import adaptadores_productivos

__all__ = [
    "AdaptadorBase", "AdaptadorCofares", "AdaptadorFedefarma", "AdaptadorHefame",
    "Reconocimiento", "adaptadores_productivos",
]
