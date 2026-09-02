from __future__ import annotations

from enum import StrEnum
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping

from .adaptadores.base import Reconocimiento
from .catalogo import ProveedorLocal
from .modelos import AlbaranLocal, DocumentoExtraidoLocal, DocumentoLocal, EvidenciaLocal


class AutoridadExtraccion(StrEnum):
    LOCAL = "LOCAL"
    IA = "IA"
    INDETERMINADO = "INDETERMINADO"


@dataclass(frozen=True)
class AutoridadExtractorLocal:
    """Autoridad productiva independiente; no representa ejecucion shadow."""

    proveedor: ProveedorLocal
    habilitada: bool = False


AUTORIDADES_EXTRACTORES_LOCALES: Mapping[ProveedorLocal, AutoridadExtractorLocal] = MappingProxyType({
    proveedor: AutoridadExtractorLocal(proveedor=proveedor, habilitada=False)
    for proveedor in ProveedorLocal
})


def autoridad_productiva_habilitada(proveedor: ProveedorLocal | str) -> bool:
    return AUTORIDADES_EXTRACTORES_LOCALES[ProveedorLocal(proveedor)].habilitada


def autoridad_para_proveedor(
    proveedor: ProveedorLocal | str,
    *,
    salida_oficial_disponible: bool,
) -> AutoridadExtraccion:
    if autoridad_productiva_habilitada(proveedor):
        return AutoridadExtraccion.LOCAL
    return AutoridadExtraccion.IA if salida_oficial_disponible else AutoridadExtraccion.INDETERMINADO


# LEGACY_COMPATIBILITY: alias booleano exclusivo de COFARES. No es una
# autoridad global y permanece ligado a la entrada COFARES del registro nuevo.
COFARES_LOCAL_AUTHORITY = autoridad_productiva_habilitada(ProveedorLocal.COFARES)


class EstadoElegibilidad(StrEnum):
    ELEGIBLE = "ELEGIBLE"
    LOCAL_NO_APLICABLE = "LOCAL_NO_APLICABLE"


@dataclass(frozen=True)
class ElegibilidadAutoridad:
    estado: EstadoElegibilidad
    razones: tuple[str, ...]
    filas_validas: int


def evaluar_elegibilidad_cofares(
    documento: DocumentoLocal,
    resultado: DocumentoExtraidoLocal,
    reconocimiento: Reconocimiento,
) -> ElegibilidadAutoridad:
    razones: list[str] = []
    if reconocimiento.estado != "RECONOCIDO":
        razones.append(f"RECONOCIMIENTO_{reconocimiento.estado}")
    if resultado.documento.get("layout") != "cofares-local":
        razones.append("LAYOUT_NO_COMPATIBLE")
    if resultado.capacidades.get("albaranes") != "SOPORTADO":
        razones.append("CAPACIDAD_ALBARANES_NO_SOPORTADA")
    if len(documento.paginas) != 1:
        razones.append("SOLO_MONOPAGINA_SOPORTADO")
    if len(resultado.segmentos) != 1 or resultado.segmentos[0].estado != "DETERMINISTA":
        razones.append("SEGMENTACION_NO_DETERMINISTA")
    if not resultado.albaranes:
        razones.append("SIN_FILAS_EXTRAIDAS")
    if resultado.incidencias:
        razones.append("EXTRACCION_CON_INCIDENCIAS")
    ordenes = [fila.orden for fila in resultado.albaranes]
    if ordenes != list(range(1, len(ordenes) + 1)):
        razones.append("ORDEN_NO_ESTABLE")
    numeros = [fila.numero_albaran for fila in resultado.albaranes]
    if len(numeros) != len(set(numeros)):
        razones.append("IDENTIDAD_FILA_DUPLICADA")
    for indice, fila in enumerate(resultado.albaranes, 1):
        razones.extend(_validar_fila(fila, documento.sha_documento, indice))
    if _hay_solapamientos(resultado.albaranes):
        razones.append("FILAS_SOLAPADAS")
    razones = list(dict.fromkeys(razones))
    return ElegibilidadAutoridad(
        EstadoElegibilidad.LOCAL_NO_APLICABLE if razones else EstadoElegibilidad.ELEGIBLE,
        tuple(razones),
        len(resultado.albaranes) if not razones else 0,
    )


def _validar_fila(fila: AlbaranLocal, sha: str, indice: int) -> list[str]:
    prefijo = f"FILA_{indice}_"
    errores: list[str] = []
    if not fila.numero_albaran or not fila.fecha or not fila.tipo_pedido or not fila.bases or fila.total is None:
        errores.append(prefijo + "INCOMPLETA")
    try:
        datetime.strptime(fila.fecha or "", "%d.%m.%Y")
    except ValueError:
        errores.append(prefijo + "FECHA_INVALIDA")
    if any(not isfinite(float(valor)) for valor in [*fila.bases, fila.total] if valor is not None):
        errores.append(prefijo + "IMPORTE_INVALIDO")
    requeridas = ("numero_albaran", "fecha", "tipo_pedido", "base", "total")
    if any(fila.evidencias.get(campo) is None for campo in requeridas):
        errores.append(prefijo + "EVIDENCIA_INCOMPLETA")
        return errores
    evidencias = [fila.evidencias[campo] for campo in requeridas]
    if any(ev.sha_documento != sha or ev.pagina != fila.pagina or not ev.literal or not ev.fila_literal or ev.bbox is None or ev.bbox_fila is None for ev in evidencias):
        errores.append(prefijo + "TRAZABILIDAD_INCOMPLETA")
    xs = [fila.evidencias[campo].bbox[0] for campo in ("fecha", "numero_albaran", "total", "base", "tipo_pedido")]
    if xs != sorted(xs) or len(set(xs)) != len(xs):
        errores.append(prefijo + "COLUMNAS_AMBIGUAS")
    if fila.sentido is not None:
        errores.append(prefijo + "SENTIDO_NO_LITERAL")
    if fila.rol_fila != "DETALLE_ALBARAN":
        errores.append(prefijo + "ROL_NO_COMPATIBLE")
    return errores


def _hay_solapamientos(filas: list[AlbaranLocal]) -> bool:
    por_pagina: dict[int, list[list[float]]] = {}
    for fila in filas:
        evidencia = fila.evidencias.get("numero_albaran")
        if evidencia and evidencia.bbox_fila:
            por_pagina.setdefault(fila.pagina, []).append(evidencia.bbox_fila)
    for cajas in por_pagina.values():
        cajas.sort(key=lambda caja: (caja[1], caja[0]))
        for anterior, actual in zip(cajas, cajas[1:]):
            interseccion_x = min(anterior[2], actual[2]) > max(anterior[0], actual[0])
            interseccion_y = min(anterior[3], actual[3]) > max(anterior[1], actual[1])
            if interseccion_x and interseccion_y:
                return True
    return False


def autoridad_cofares(*, salida_oficial_disponible: bool) -> AutoridadExtraccion:
    """LEGACY_COMPATIBILITY para consumidores historicos exclusivos de COFARES."""
    return autoridad_para_proveedor(
        ProveedorLocal.COFARES,
        salida_oficial_disponible=salida_oficial_disponible,
    )
