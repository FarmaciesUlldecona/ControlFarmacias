"""OCR local encapsulado; los adaptadores solo consumen modelos propios."""

from .modelos import BloqueOCR, LineaOCR, PaginaOCR, PalabraOCR, RegionOCR, ResultadoOCR, SolicitudRegionOCR
from .windows_media import MotorWindowsMediaOcr

__all__ = [
    "BloqueOCR", "LineaOCR", "MotorWindowsMediaOcr", "PaginaOCR",
    "PalabraOCR", "RegionOCR", "ResultadoOCR", "SolicitudRegionOCR",
]
