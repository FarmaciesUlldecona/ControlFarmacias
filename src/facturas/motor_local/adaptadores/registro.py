from .base import AdaptadorBase
from .cofares import AdaptadorCofares
from .hefame import AdaptadorHefame
from .fedefarma import AdaptadorFedefarma


def adaptadores_productivos() -> tuple[AdaptadorBase, ...]:
    return (AdaptadorCofares(), AdaptadorHefame(), AdaptadorFedefarma())
