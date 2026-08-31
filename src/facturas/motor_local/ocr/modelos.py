from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RegionOCR:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class PalabraOCR:
    texto: str
    bbox: RegionOCR
    orden: int
    confidence: float | None = None


@dataclass(frozen=True)
class LineaOCR:
    texto: str
    palabras: tuple[PalabraOCR, ...]
    orden: int


@dataclass(frozen=True)
class BloqueOCR:
    lineas: tuple[LineaOCR, ...]
    bbox: RegionOCR
    orden: int


@dataclass(frozen=True)
class PaginaOCR:
    numero: int
    ancho: float
    alto: float
    texto: str
    palabras: tuple[PalabraOCR, ...]
    lineas: tuple[LineaOCR, ...]
    bloques: tuple[BloqueOCR, ...]
    hash_ocr: str
    motor: str
    idioma: str
    confidence_disponible: bool
    angulo_texto: float | None
    preprocesado: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoOCR:
    paginas: tuple[PaginaOCR, ...]
    hash_ocr: str
    motor: str
    version: str
    idioma: str
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SolicitudRegionOCR:
    id: str
    pagina: int
    bbox: RegionOCR
    escala: int = 8
    escala_grises: bool = True
