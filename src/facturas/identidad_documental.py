"""Contratos locales: evidencia documental separada de localizacion y binario.

No decide sustituciones, pagos ni deduplicaciones automaticamente.
Los valores documentales deben proceder de una extraccion con provenance.
"""
from dataclasses import dataclass
from decimal import Decimal
import hashlib


@dataclass(frozen=True)
class EvidenciaContenido:
    valor: str
    pagina: int
    literal: str

    def __post_init__(self):
        if self.pagina < 1 or not self.literal.strip() or not self.valor.strip():
            raise ValueError("EVIDENCIA_DOCUMENTAL_INVALIDA")


@dataclass(frozen=True)
class IdentidadEconomica:
    proveedor: EvidenciaContenido | None = None
    numero: EvidenciaContenido | None = None
    tipo: EvidenciaContenido | None = None
    destinatario: EvidenciaContenido | None = None
    fecha: EvidenciaContenido | None = None
    total: EvidenciaContenido | None = None


def identidad_binaria(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def contrastar_farmacia(operativa: str, documental: EvidenciaContenido | None) -> str:
    if documental is None or documental.valor not in {"PIO", "RITA"}:
        return "NO_DEMOSTRABLE"
    if operativa != documental.valor:
        return "FARMACIA_DOCUMENTO_CONTRADICTORIA"
    return "CONSISTENTE"


def comparar_identidad(a: IdentidadEconomica, b: IdentidadEconomica) -> str:
    """Devuelve una propuesta de revision; nunca una orden de fusion o pago.

Proveedor/destinatario deben ser identificadores documentados normalizados
por el llamador, preferiblemente fiscales. Fecha/total son corroboracion;
no son obligatorios para proponer una relacion cuando el nucleo es completo.
"""
    campos = ("proveedor", "numero", "tipo", "destinatario")
    for campo in campos:
        x, y = getattr(a, campo), getattr(b, campo)
        if x is not None and y is not None and x.valor.casefold() != y.valor.casefold():
            return "FACTURAS_DIFERENTES"
    if any(getattr(obj, campo) is None for obj in (a, b) for campo in campos):
        return "IDENTIDAD_ECONOMICA_NO_DEMOSTRADA"
    for campo in ("fecha", "total"):
        x, y = getattr(a, campo), getattr(b, campo)
        if x is not None and y is not None:
            iguales = Decimal(x.valor) == Decimal(y.valor) if campo == "total" else x.valor == y.valor
            if not iguales:
                return "POSIBLE_VERSION_REQUIERE_REVISION"
    return "POSIBLE_MISMA_FACTURA_REQUIERE_REVISION"
