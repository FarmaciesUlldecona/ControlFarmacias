"""Runtime ControlFarmacias V1 para normalizacion y conciliacion en Supabase.

El paquete no ejecuta procesos al importarse. Los workers exigen dependencias
inyectadas y respetan los interruptores almacenados en ``cf_configuracion``.
"""

from .conciliacion import conciliar_importes
from .extraccion_productiva import OrquestadorExtraccionProductiva
from .modelos import (
    ConfiguracionRuntime,
    EstadoConciliacion,
    EstadoNormalizacion,
    EstadoRevision,
)

__all__ = [
    "ConfiguracionRuntime",
    "EstadoConciliacion",
    "EstadoNormalizacion",
    "EstadoRevision",
    "OrquestadorExtraccionProductiva",
    "conciliar_importes",
]
