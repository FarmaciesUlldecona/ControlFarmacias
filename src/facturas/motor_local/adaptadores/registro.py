from .base import AdaptadorBase
from .cofares import AdaptadorCofares
from .hefame import AdaptadorHefame


def adaptadores_productivos() -> tuple[AdaptadorBase, ...]:
    return (AdaptadorCofares(), AdaptadorHefame())
