from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Generic, TypeVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class ModeloV2(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    def json_estable(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )


class TipoContenido(StrEnum):
    PDF_NATIVO = "PDF_NATIVO"
    PDF_IMAGEN = "PDF_IMAGEN"
    PDF_MIXTO = "PDF_MIXTO"
    PDF_NO_LEIBLE = "PDF_NO_LEIBLE"


class NaturalezaPrincipal(StrEnum):
    MERCANCIA = "MERCANCIA"
    SERVICIOS = "SERVICIOS"
    MIXTA = "MIXTA"
    CONDICIONES_COMERCIALES = "CONDICIONES_COMERCIALES"


class EstadoValidacion(StrEnum):
    VALIDADA = "VALIDADA"
    VALIDADA_CON_INCIDENCIAS = "VALIDADA_CON_INCIDENCIAS"
    REQUIERE_SEGUNDA_LECTURA = "REQUIERE_SEGUNDA_LECTURA"
    REQUIERE_REVISION = "REQUIERE_REVISION"
    ERROR_TECNICO = "ERROR_TECNICO"


class EstrategiaLectura(StrEnum):
    LUNA_V2 = "LUNA_V2"
    LUNA_V2_MAS_SPLITTER_SEGMENTADO = "LUNA_V2_MAS_SPLITTER_SEGMENTADO"


class TipoReferencia(StrEnum):
    DELIVERY = "DELIVERY"
    PEDIDO = "PEDIDO"
    PO = "PO"
    ORDER = "ORDER"
    DOCUMENTO = "DOCUMENTO"
    OTRA = "OTRA"


class TipoDiscrepancia(StrEnum):
    CUADRE_FISCAL = "CUADRE_FISCAL"
    CUADRE_ALBARANES = "CUADRE_ALBARANES"
    SUBTOTAL_NO_EXPLICADO = "SUBTOTAL_NO_EXPLICADO"
    IDENTIFICADOR_AMBIGUO = "IDENTIFICADOR_AMBIGUO"
    OTRA = "OTRA"


class TipoMovimiento(StrEnum):
    RAPPEL = "RAPPEL"
    ABONO_COMERCIAL = "ABONO_COMERCIAL"
    DEVOLUCION_MERCANCIA = "DEVOLUCION_MERCANCIA"
    DESCUENTO = "DESCUENTO"
    BONIFICACION = "BONIFICACION"
    SERVICIO = "SERVICIO"
    CONDICION_COMERCIAL = "CONDICION_COMERCIAL"
    OTRO = "OTRO"


class Sentido(StrEnum):
    ABONO = "ABONO"
    CARGO = "CARGO"


class OrigenDerivacion(StrEnum):
    LITERAL_EXPLICITO = "LITERAL_EXPLICITO"
    DERIVACION_DETERMINISTA = "DERIVACION_DETERMINISTA"


class Severidad(StrEnum):
    INFO = "INFO"
    AVISO = "AVISO"
    ERROR = "ERROR"


class ResultadoControl(StrEnum):
    OK = "OK"
    FALLO = "FALLO"
    NO_APLICA = "NO_APLICA"
    NO_EVALUABLE = "NO_EVALUABLE"


class Evidencia(ModeloV2):
    pagina: int = Field(ge=1)
    segmento_id: str | None = None
    literal: str = Field(min_length=1)
    ubicacion: dict[str, Any] | None = None


T = TypeVar("T")


class ValorDocumentado(ModeloV2, Generic[T]):
    valor: T
    literal: str = Field(min_length=1)
    evidencia: list[Evidencia] = Field(min_length=1)


class FuenteDerivacion(ModeloV2):
    campo: str = Field(min_length=1)
    valor: Any
    evidencias: list[Evidencia] = Field(min_length=1)


class DerivacionCampo(ModeloV2):
    campo: str = Field(min_length=1)
    valor_final: str = Field(min_length=1)
    regla_id: str = Field(min_length=1)
    origen: OrigenDerivacion
    fuentes: list[FuenteDerivacion] = Field(min_length=1)


class FechaDocumental(ModeloV2):
    literal: str = Field(min_length=1)
    iso: date | None = None


class Tercero(ModeloV2):
    nombre: ValorDocumentado[str] | None = None
    nif: ValorDocumentado[str] | None = None
    direccion: ValorDocumentado[str] | None = None
    alias_funcional: str | None = None


class Totales(ModeloV2):
    moneda: ValorDocumentado[str] | None = None
    base_imponible: ValorDocumentado[Decimal] | None = None
    iva: ValorDocumentado[Decimal] | None = None
    recargo_equivalencia: ValorDocumentado[Decimal] | None = None
    otros: ValorDocumentado[Decimal] | None = None
    total: ValorDocumentado[Decimal] | None = None


class Vencimiento(ModeloV2):
    orden: int = Field(ge=1)
    fecha: ValorDocumentado[FechaDocumental] | None = None
    importe: ValorDocumentado[Decimal] | None = None
    medio_pago: ValorDocumentado[str] | None = None

    @model_validator(mode="after")
    def requiere_fecha_o_importe(self) -> Vencimiento:
        if self.fecha is None and self.importe is None:
            raise ValueError("un vencimiento requiere fecha o importe visible")
        return self


class TramoImpuesto(ModeloV2):
    orden: int = Field(ge=1)
    descripcion_literal: ValorDocumentado[str] | None = None
    base: ValorDocumentado[Decimal] | None = None
    tipo_iva: ValorDocumentado[Decimal] | None = None
    cuota_iva: ValorDocumentado[Decimal] | None = None
    tipo_recargo_equivalencia: ValorDocumentado[Decimal] | None = None
    cuota_recargo_equivalencia: ValorDocumentado[Decimal] | None = None
    total_tramo: ValorDocumentado[Decimal] | None = None


class AlbaranDocumental(ModeloV2):
    orden: int = Field(ge=1)
    fecha: ValorDocumentado[FechaDocumental] | None = None
    numero: ValorDocumentado[str]
    sentido: Sentido | None = Field(
        default=None,
        validation_alias=AliasChoices("sentido", "tipo_movimiento"),
    )
    tipo_pedido: ValorDocumentado[str] | None = None
    importe_base: ValorDocumentado[Decimal] | None = None
    importe_total: ValorDocumentado[Decimal] | None = None

    @property
    def tipo_movimiento(self) -> Sentido | None:
        """Alias de lectura temporal para consumidores V2 anteriores."""
        return self.sentido


class MovimientoComercial(ModeloV2):
    orden: int = Field(ge=1)
    tipo: TipoMovimiento
    descripcion_literal: ValorDocumentado[str]
    sentido: Sentido | None = None
    base: ValorDocumentado[Decimal] | None = None
    iva: ValorDocumentado[Decimal] | None = None
    recargo_equivalencia: ValorDocumentado[Decimal] | None = None
    importe: ValorDocumentado[Decimal] | None = None


class FormaPago(ModeloV2):
    descripcion_literal: ValorDocumentado[str]
    referencia: ValorDocumentado[str] | None = None


class ReferenciaDocumental(ModeloV2):
    orden: int = Field(ge=1)
    tipo: TipoReferencia
    identificador: ValorDocumentado[str]
    descripcion_literal: ValorDocumentado[str] | None = None


class DiscrepanciaDocumental(ModeloV2):
    tipo: TipoDiscrepancia
    descripcion: str
    importe_diferencia: Decimal | None = None
    valores_implicados: list[ValorDocumentado[Decimal | str]] = Field(default_factory=list)
    material: bool


class Incidencia(ModeloV2):
    codigo: str
    severidad: Severidad
    descripcion: str
    paginas: list[int] = Field(default_factory=list)
    bloqueante: bool
    evidencias: list[Evidencia] = Field(default_factory=list)


class ResultadoValidacion(ModeloV2):
    codigo: str
    resultado: ResultadoControl
    descripcion: str
    valores: dict[str, Any] = Field(default_factory=dict)
    tolerancia_aplicada: Decimal | None = None
    evidencias: list[Evidencia] = Field(default_factory=list)
    regla_version: str


class IntentoLectura(ModeloV2):
    orden: int = Field(ge=1)
    estrategia: EstrategiaLectura
    estado_tecnico: str
    motivo: str | None = None
    paginas_o_segmentos: list[int | str] = Field(default_factory=list)
    version_lector: str
    duracion_ms: int = Field(ge=0)


class Segmento(ModeloV2):
    segmento_id: str
    pagina_inicio: int = Field(ge=1)
    pagina_fin: int = Field(ge=1)
    origen: str = "SPLITTER"
    estado: str

    @model_validator(mode="after")
    def rango_valido(self) -> Segmento:
        if self.pagina_inicio > self.pagina_fin:
            raise ValueError("rango de segmento invertido")
        return self


class MetadataTecnica(ModeloV2):
    version_normalizador: str
    version_configuracion: str
    lector_primario: str
    intentos: list[IntentoLectura] = Field(default_factory=list)
    segmentos: list[Segmento] = Field(default_factory=list)
    huella_contenido: str | None = None
    inicio: str
    fin: str
    duracion_ms: int = Field(ge=0)
    correlacion_id: str


class FacturaNormalizada(ModeloV2):
    factura_id: str
    tipo_documento: ValorDocumentado[str] | None = None
    naturaleza_principal: NaturalezaPrincipal
    estado_validacion: EstadoValidacion
    requiere_conciliacion_albaranes: bool
    pagina_inicio: int = Field(ge=1)
    pagina_fin: int = Field(ge=1)
    proveedor: Tercero | None = None
    numero_factura: ValorDocumentado[str] | None = None
    fecha_factura: ValorDocumentado[FechaDocumental] | None = None
    destinatario: Tercero | None = None
    totales: Totales = Field(default_factory=Totales)
    vencimientos: list[Vencimiento] = Field(default_factory=list)
    impuestos: list[TramoImpuesto] = Field(default_factory=list)
    albaranes: list[AlbaranDocumental] = Field(default_factory=list)
    movimientos_comerciales: list[MovimientoComercial] = Field(default_factory=list)
    forma_pago: FormaPago | None = None
    referencias_documentales: list[ReferenciaDocumental] = Field(default_factory=list)
    derivaciones: list[DerivacionCampo] = Field(default_factory=list)
    discrepancias_documentales: list[DiscrepanciaDocumental] = Field(default_factory=list)
    incidencias: list[Incidencia] = Field(default_factory=list)
    validaciones: list[ResultadoValidacion] = Field(min_length=1)

    @model_validator(mode="after")
    def rango_valido(self) -> FacturaNormalizada:
        if self.pagina_inicio > self.pagina_fin:
            raise ValueError("rango de factura invertido")
        return self


class DocumentoNormalizado(ModeloV2):
    documento_id: str
    archivo_origen: str
    tipo_contenido: TipoContenido
    numero_paginas: int | None = Field(default=None, ge=1)
    estado_documento: EstadoValidacion
    estrategia_lectura: EstrategiaLectura
    facturas: list[FacturaNormalizada] = Field(default_factory=list)
    metadata_tecnica: MetadataTecnica

    @model_validator(mode="after")
    def paginas_coherentes(self) -> DocumentoNormalizado:
        if self.numero_paginas is None:
            return self
        for factura in self.facturas:
            if factura.pagina_fin > self.numero_paginas:
                raise ValueError("factura fuera del rango de paginas del documento")
        return self
