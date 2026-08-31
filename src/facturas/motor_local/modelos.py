from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RegionLocal:
    """Caja (x0, y0, x1, y1) en puntos PDF, origen arriba-izquierda."""

    x0: float
    y0: float
    x1: float
    y1: float

    def to_list(self) -> list[float]:
        return [round(self.x0, 3), round(self.y0, 3), round(self.x1, 3), round(self.y1, 3)]


@dataclass(frozen=True)
class PalabraLocal:
    texto: str
    pagina: int
    bbox: RegionLocal
    orden: int


@dataclass
class LineaLocal:
    pagina: int
    palabras: list[PalabraLocal]
    orden: int

    @property
    def texto(self) -> str:
        return " ".join(p.texto for p in self.palabras)

    @property
    def bbox(self) -> RegionLocal:
        return union_bbox([p.bbox for p in self.palabras])


@dataclass
class BloqueLocal:
    pagina: int
    lineas: list[LineaLocal]
    bbox: RegionLocal
    orden: int


@dataclass
class CeldaLocal:
    columna: str
    palabras: list[PalabraLocal]
    bbox: RegionLocal | None


@dataclass
class FilaLocal:
    pagina: int
    celdas: list[CeldaLocal]
    literal: str
    bbox: RegionLocal
    orden: int


@dataclass
class TablaLocal:
    id: str
    pagina: int
    encabezados: dict[str, RegionLocal]
    filas: list[FilaLocal]
    bbox: RegionLocal


@dataclass
class PaginaLocal:
    numero: int
    ancho: float
    alto: float
    texto: str
    palabras: list[PalabraLocal]
    lineas: list[LineaLocal]
    origen: str = "TEXTO_NATIVO"
    metadatos_ocr: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentoLocal:
    ruta: str
    sha_documento: str
    paginas: list[PaginaLocal]
    ocr: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenciaLocal:
    sha_documento: str
    pagina: int
    literal: str
    bbox: list[float] | None
    contexto: str
    fila_literal: str | None
    bbox_fila: list[float] | None
    tabla: str | None
    columna: str | None
    adaptador: str
    version_adaptador: str
    regla: str
    tipo_evidencia: str
    origen_autoridad: str


@dataclass
class EvidenciaOCRLocal(EvidenciaLocal):
    confidence: float | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class SegmentoLocal:
    paginas: list[int]
    identidad_candidata: str | None
    evidencias: list[dict[str, Any]]
    estado: str
    regla: str


@dataclass
class AlbaranLocal:
    numero_albaran: str
    fecha: str | None
    tipo_pedido: str | None
    bases: list[float]
    total: float | None
    sentido: str | None
    rol_fila: str
    pagina: int
    orden: int
    evidencias: dict[str, EvidenciaLocal | None]
    bases_por_categoria: dict[str, float] = field(default_factory=dict)
    atributos_documentales: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentoExtraidoLocal:
    documento: dict[str, Any]
    segmentos: list[SegmentoLocal]
    facturas: list[dict[str, Any]]
    cabecera: dict[str, Any]
    albaranes: list[AlbaranLocal]
    movimientos: list[dict[str, Any]]
    impuestos: list[dict[str, Any]]
    vencimientos: list[dict[str, Any]]
    otros: list[dict[str, Any]]
    controles_conciliacion: list[dict[str, Any]]
    incidencias: list[dict[str, Any]]
    evidencias: list[EvidenciaLocal]
    capacidades: dict[str, str]
    motor: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def union_bbox(boxes: list[RegionLocal]) -> RegionLocal:
    if not boxes:
        raise ValueError("union_bbox requiere al menos una caja")
    return RegionLocal(
        min(b.x0 for b in boxes),
        min(b.y0 for b in boxes),
        max(b.x1 for b in boxes),
        max(b.y1 for b in boxes),
    )
