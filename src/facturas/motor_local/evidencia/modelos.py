from ..modelos import EvidenciaLocal

TIPOS_EVIDENCIA = frozenset({"LITERAL_LOCAL", "GEOMETRIA_LOCAL", "DERIVACION_LOCAL", "AMBIGUA"})

__all__ = ["EvidenciaLocal", "TIPOS_EVIDENCIA"]
