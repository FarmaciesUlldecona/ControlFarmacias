from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.facturas.normalizador_v2.modelos import (
    AlbaranDocumental, EstadoValidacion, Evidencia, FacturaNormalizada,
    FechaDocumental, Incidencia, Severidad, ValorDocumentado,
)
from src.facturas.normalizador_v2.validadores import validar_factura

from .adaptadores.base import Reconocimiento
from .autoridad import (
    COFARES_LOCAL_AUTHORITY, AutoridadExtraccion, ElegibilidadAutoridad,
    EstadoElegibilidad, evaluar_elegibilidad_cofares,
)
from .modelos import AlbaranLocal, DocumentoExtraidoLocal, DocumentoLocal, EvidenciaLocal


@dataclass(frozen=True)
class ResultadoEnsambladoCofares:
    factura: FacturaNormalizada
    aplicada: bool
    simulacion: bool
    autoridad_albaranes: AutoridadExtraccion
    elegibilidad: ElegibilidadAutoridad
    razon: str
    trazabilidad: dict[str, Any]


def adaptar_albaranes_cofares(resultado: DocumentoExtraidoLocal) -> tuple[list[AlbaranDocumental], list[Incidencia]]:
    albaranes: list[AlbaranDocumental] = []
    incidencias: list[Incidencia] = []
    for fila in resultado.albaranes:
        albaranes.append(_adaptar_fila(fila))
        ev_numero = _evidencia(fila.evidencias["numero_albaran"])
        incidencias.append(Incidencia(
            codigo="SENTIDO_NO_DOCUMENTADO", severidad=Severidad.AVISO,
            descripcion="El documento demuestra el albaran, pero no CARGO/ABONO",
            paginas=[fila.pagina], bloqueante=False, evidencias=[ev_numero],
        ))
    return albaranes, incidencias


def ensamblar_factura_cofares(
    factura_pipeline: FacturaNormalizada,
    documento: DocumentoLocal,
    resultado: DocumentoExtraidoLocal,
    reconocimiento: Reconocimiento,
    *,
    simular: bool = False,
) -> ResultadoEnsambladoCofares:
    elegibilidad = evaluar_elegibilidad_cofares(documento, resultado, reconocimiento)
    identidad_local = resultado.segmentos[0].identidad_candidata if len(resultado.segmentos) == 1 else None
    identidad_pipeline = factura_pipeline.numero_factura.valor if factura_pipeline.numero_factura else None
    if identidad_local is None or str(identidad_local) != str(identidad_pipeline):
        elegibilidad = ElegibilidadAutoridad(
            EstadoElegibilidad.LOCAL_NO_APLICABLE,
            tuple([*elegibilidad.razones, "IDENTIDAD_FACTURA_NO_COINCIDE"]), 0,
        )
    habilitada = simular or COFARES_LOCAL_AUTHORITY
    if elegibilidad.estado != EstadoElegibilidad.ELEGIBLE:
        return _resultado_sin_aplicar(factura_pipeline, simular, elegibilidad, "LOCAL_NO_APLICABLE")
    if not habilitada:
        return _resultado_sin_aplicar(factura_pipeline, False, elegibilidad, "BANDERA_AUTORIDAD_OFF")
    albaranes, incidencias = adaptar_albaranes_cofares(resultado)
    actualizado = factura_pipeline.model_copy(update={
        "albaranes": albaranes,
        "incidencias": [*factura_pipeline.incidencias, *incidencias],
        "estado_validacion": EstadoValidacion.VALIDADA_CON_INCIDENCIAS,
    })
    evaluacion = validar_factura(actualizado)
    actualizado = actualizado.model_copy(update={
        "estado_validacion": evaluacion.estado,
        "validaciones": list(evaluacion.validaciones),
        "discrepancias_documentales": list(evaluacion.discrepancias),
        "incidencias": list(evaluacion.incidencias),
    })
    return ResultadoEnsambladoCofares(
        actualizado, True, simular, AutoridadExtraccion.LOCAL, elegibilidad,
        "SIMULACION_AUTORIDAD_LOCAL" if simular else "AUTORIDAD_LOCAL_ACTIVA",
        _trazabilidad(resultado, len(albaranes)),
    )


def _resultado_sin_aplicar(factura, simular, elegibilidad, razon):
    return ResultadoEnsambladoCofares(
        factura, False, simular, AutoridadExtraccion.IA, elegibilidad, razon,
        {"coleccion": "albaranes", "fuente": "IA", "salida_local_aplicada": False},
    )


def _adaptar_fila(fila: AlbaranLocal) -> AlbaranDocumental:
    fecha = datetime.strptime(fila.fecha, "%d.%m.%Y").date()
    base = sum((Decimal(str(valor)) for valor in fila.bases), Decimal("0"))
    return AlbaranDocumental(
        orden=fila.orden,
        numero=_documentado(fila.numero_albaran, fila.evidencias["numero_albaran"]),
        fecha=_documentado(FechaDocumental(literal=fila.fecha, iso=fecha), fila.evidencias["fecha"]),
        tipo_pedido=_documentado(fila.tipo_pedido, fila.evidencias["tipo_pedido"]),
        importe_base=_documentado(base, fila.evidencias["base"], {"bases_componentes": fila.bases}),
        importe_total=_documentado(Decimal(str(fila.total)), fila.evidencias["total"]),
        sentido=None,
    )


def _documentado(valor, evidencia_local: EvidenciaLocal, extra: dict[str, Any] | None = None):
    return ValorDocumentado(valor=valor, literal=evidencia_local.literal, evidencia=[_evidencia(evidencia_local, extra)])


def _evidencia(local: EvidenciaLocal, extra: dict[str, Any] | None = None) -> Evidencia:
    ubicacion = {
        "bbox": local.bbox, "fila_literal": local.fila_literal,
        "bbox_fila": local.bbox_fila, "tabla": local.tabla, "columna": local.columna,
        "sha_documento": local.sha_documento, "adaptador": local.adaptador,
        "version_adaptador": local.version_adaptador, "regla": local.regla,
        "tipo_evidencia": local.tipo_evidencia, "origen_autoridad": local.origen_autoridad,
    }
    ubicacion.update(extra or {})
    return Evidencia(pagina=local.pagina, literal=local.literal, ubicacion=ubicacion)


def _trazabilidad(resultado: DocumentoExtraidoLocal, filas: int) -> dict[str, Any]:
    return {
        "coleccion": "albaranes", "fuente": "LOCAL", "razon": "COFARES_COMPATIBLE_Y_ELEGIBLE",
        "motor": resultado.motor.get("id"), "version_motor": resultado.motor.get("version"),
        "adaptador": resultado.documento.get("layout"), "version_adaptador": resultado.documento.get("layout_version"),
        "sha_documento": resultado.documento.get("sha256"), "filas": filas,
        "salida_local_aplicada": True,
    }
