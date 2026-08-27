from .base import AdaptadorBase
from .cofares import AdaptadorCofares
from .hefame import AdaptadorHefame
from .fedefarma import AdaptadorFedefarma
from .alliance import AdaptadorAlliance


def adaptadores_productivos() -> tuple[AdaptadorBase, ...]:
    return (AdaptadorCofares(), AdaptadorHefame(), AdaptadorFedefarma(), AdaptadorAlliance())
