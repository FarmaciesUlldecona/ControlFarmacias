from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class EstadoNormalizacion(StrEnum):
    PENDIENTE = "PENDIENTE"
    NORMALIZANDO = "NORMALIZANDO"
    NORMALIZADA = "NORMALIZADA"
    REQUIERE_REVISION = "REQUIERE_REVISION"


class EstadoConciliacion(StrEnum):
    PENDIENTE_CONCILIAR = "PENDIENTE_CONCILIAR"
    CONCILIADA = "CONCILIADA"


class EstadoRevision(StrEnum):
    NO_REQUERIDA = "NO_REQUERIDA"
    PENDIENTE_REVISION_PIO = "PENDIENTE_REVISION_PIO"
    VALIDADA_PIO = "VALIDADA_PIO"


class EstadoEjecucion(StrEnum):
    PENDIENTE = "PENDIENTE"
    EJECUTANDO = "EJECUTANDO"
    COMPLETADA = "COMPLETADA"
    INCOMPLETA = "INCOMPLETA"
    ERROR = "ERROR"


class EstadoLecturaDocumento(StrEnum):
    """Estado tecnico agregado del PDF, separado del estado economico de sus facturas."""

    PENDIENTE = "PENDIENTE"
    NORMALIZANDO = "NORMALIZANDO"
    NORMALIZADA = "NORMALIZADA"
    ERROR = "ERROR"


class TipoRelacionConciliacion(StrEnum):
    UNO_A_UNO = "UNO_A_UNO"
    UNO_A_VARIOS = "UNO_A_VARIOS"
    VARIOS_A_UNO = "VARIOS_A_UNO"
    MOVIMIENTO_NO_FARMATIC = "MOVIMIENTO_NO_FARMATIC"
    SIN_COINCIDENCIA = "SIN_COINCIDENCIA"


@dataclass(frozen=True, slots=True)
class ConfiguracionRuntime:
    normalizacion_automatica: bool = False
    conciliacion_automatica: bool = False
    luna_habilitada: bool = False
    farmacias_habilitadas: tuple[str, ...] = ("PIO",)
    tolerancia_conciliacion: Decimal = Decimal("0.0500")

    def __post_init__(self) -> None:
        if self.tolerancia_conciliacion < 0:
            raise ValueError("La tolerancia no puede ser negativa")
        if not self.farmacias_habilitadas:
            raise ValueError("Debe existir al menos una farmacia habilitada")
        if not set(self.farmacias_habilitadas) <= {"PIO", "RITA"}:
            raise ValueError("Farmacia no soportada")


@dataclass(frozen=True, slots=True)
class DocumentoTrabajo:
    documento_id: str
    archivo_ruta: str
    archivo_nombre: str
    farmacia: str
    ruta_local: Path | None = None
    reprocesado_manual: bool = False


@dataclass(frozen=True, slots=True)
class FacturaTrabajo:
    factura_id: str
    documento_id: str
    farmacia: str
    importe_total: Decimal | None
    proveedor_id: str | None = None


def conservar_id_proveedor(valor: str | None) -> str | None:
    """Conserva el literal Supabase sin coercion numerica ni normalizacion destructiva."""
    if valor is not None and not isinstance(valor, str):
        raise TypeError("id_proveedor debe ser texto o null")
    return valor


@dataclass(frozen=True, slots=True)
class ResultadoEtapa:
    valores: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    uso_ocr: bool = False


@dataclass(frozen=True, slots=True)
class UsoLuna:
    modelo: str
    campos: tuple[str, ...]
    tokens_entrada: int
    tokens_salida: int
    coste: Decimal

    def __post_init__(self) -> None:
        if self.tokens_entrada < 0 or self.tokens_salida < 0 or self.coste < 0:
            raise ValueError("Uso y coste Luna no pueden ser negativos")

    @property
    def tokens_total(self) -> int:
        return self.tokens_entrada + self.tokens_salida


@dataclass(frozen=True, slots=True)
class PasoExtraccion:
    etapa: str
    campos_solicitados: tuple[str, ...]
    campos_resueltos: tuple[str, ...]
    provenance: Mapping[str, Any]
    uso_ocr: bool = False


@dataclass(frozen=True, slots=True)
class IncidenciaRuntime:
    codigo: str
    categoria: str
    severidad: str
    bloqueante: bool
    mensaje_usuario: str
    detalle_tecnico: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResultadoExtraccionProductiva:
    valores: Mapping[str, Any]
    campos_pendientes: tuple[str, ...]
    pasos: tuple[PasoExtraccion, ...]
    uso_luna: UsoLuna | None
    incidencias: tuple[IncidenciaRuntime, ...]
    documento_normalizado: Mapping[str, Any] | None = None

    @property
    def completo(self) -> bool:
        return not self.campos_pendientes

    @property
    def estado_normalizacion(self) -> EstadoNormalizacion:
        return (
            EstadoNormalizacion.NORMALIZADA
            if self.completo
            else EstadoNormalizacion.REQUIERE_REVISION
        )

    @property
    def estado_revision(self) -> EstadoRevision:
        return (
            EstadoRevision.NO_REQUERIDA
            if self.completo
            else EstadoRevision.PENDIENTE_REVISION_PIO
        )


@dataclass(frozen=True, slots=True)
class DetalleConciliacion:
    tipo_relacion: TipoRelacionConciliacion
    importe_aplicado: Decimal
    albaran_farmacia: str | None = None
    albaran_id_contador: int | None = None
    factura_albaran_extraido_id: str | None = None
    factura_movimiento_id: str | None = None
    coincidencia_numero_literal: bool = False
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        referencia_operacional = (
            self.albaran_farmacia is not None,
            self.albaran_id_contador is not None,
        )
        if referencia_operacional[0] != referencia_operacional[1]:
            raise ValueError("farmacia e id_contador deben aparecer juntos")
        ajuste_documental_sin_fila = (
            self.tipo_relacion == TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC
            and self.provenance.get("fuente") == "FISCALIDAD_AJUSTE_DOCUMENTAL"
        )
        if (
            self.factura_albaran_extraido_id is None
            and self.factura_movimiento_id is None
            and self.tipo_relacion != TipoRelacionConciliacion.SIN_COINCIDENCIA
            and not ajuste_documental_sin_fila
        ):
            raise ValueError("El detalle necesita un origen documental")


@dataclass(frozen=True, slots=True)
class ResultadoConciliacion:
    importe_factura: Decimal
    importe_explicado: Decimal
    diferencia: Decimal
    tolerancia: Decimal
    resultado: str
    detalles: tuple[DetalleConciliacion, ...]
