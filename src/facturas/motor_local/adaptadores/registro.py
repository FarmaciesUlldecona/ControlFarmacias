from .base import AdaptadorBase
from .cofares import AdaptadorCofares
from .hefame import AdaptadorHefame
from .fedefarma import AdaptadorFedefarma
from .alliance import AdaptadorAlliance
from .gold_pequenos import (
    AdaptadorEcoceutics,
    AdaptadorEports,
    AdaptadorLogista,
    AdaptadorLoreal,
    AdaptadorMoretti,
    AdaptadorTotalcare,
)
from .guimera import AdaptadorGuimera


def adaptadores_productivos() -> tuple[AdaptadorBase, ...]:
    # Todos los adaptadores se ejecutan en shadow; el nombre histórico de la
    # función no confiere autoridad productiva a los extractores nuevos.
    return (
        AdaptadorCofares(), AdaptadorHefame(), AdaptadorFedefarma(), AdaptadorAlliance(),
        AdaptadorEcoceutics(), AdaptadorEports(), AdaptadorLogista(), AdaptadorLoreal(),
        AdaptadorMoretti(), AdaptadorTotalcare(),
        AdaptadorGuimera(),
    )
