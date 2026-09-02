"""Motor documental local de ControlFarmacias.

El paquete no importa el backend concreto al cargarse. De ese modo, modelos,
geometria, evidencia y adaptadores siguen siendo utilizables sin PDFium.
"""

from .configuracion import ConfiguracionShadow
from .autoridad import (
    AUTORIDADES_EXTRACTORES_LOCALES,
    AutoridadExtraccion,
    COFARES_LOCAL_AUTHORITY,
    autoridad_productiva_habilitada,
)
from .catalogo import ProveedorLocal
from .comparador import comparar_pipeline_local
from .servicio import MotorDocumentoLocal
from .shadow import (
    ejecutar_con_shadow_cofares,
    ejecutar_con_shadow_local,
    ejecutar_shadow_cofares_sobre_resultado,
    ejecutar_shadow_local_sobre_resultado,
)

__all__ = [
    "AUTORIDADES_EXTRACTORES_LOCALES",
    "AutoridadExtraccion",
    "COFARES_LOCAL_AUTHORITY",
    "ConfiguracionShadow",
    "MotorDocumentoLocal",
    "ProveedorLocal",
    "autoridad_productiva_habilitada",
    "comparar_pipeline_local",
    "ejecutar_con_shadow_cofares",
    "ejecutar_con_shadow_local",
    "ejecutar_shadow_cofares_sobre_resultado",
    "ejecutar_shadow_local_sobre_resultado",
]
