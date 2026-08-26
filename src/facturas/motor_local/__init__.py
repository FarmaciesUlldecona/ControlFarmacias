"""Motor documental local de ControlFarmacias.

El paquete no importa el backend concreto al cargarse. De ese modo, modelos,
geometria, evidencia y adaptadores siguen siendo utilizables sin PDFium.
"""

from .configuracion import ConfiguracionShadow
from .autoridad import AutoridadExtraccion, COFARES_LOCAL_AUTHORITY
from .comparador import comparar_pipeline_local
from .servicio import MotorDocumentoLocal
from .shadow import ejecutar_con_shadow_cofares, ejecutar_shadow_cofares_sobre_resultado

__all__ = ["AutoridadExtraccion", "COFARES_LOCAL_AUTHORITY", "ConfiguracionShadow", "MotorDocumentoLocal", "comparar_pipeline_local", "ejecutar_con_shadow_cofares", "ejecutar_shadow_cofares_sobre_resultado"]
