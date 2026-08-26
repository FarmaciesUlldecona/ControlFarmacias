from __future__ import annotations

import unicodedata

from .modelos import (
    FacturaNormalizada, MovimientoComercial, ReferenciaDocumental,
    TipoMovimiento, TipoReferencia,
)
from .validadores import validar_factura

VERSION_REGLAS = "normalizador-v2.reglas-pequenas.3"


_CLASIFICACIONES_CONCEPTUALES = (
    ("rappel generah", TipoMovimiento.RAPPEL, "movimiento.concepto.rappel_generah.v2"),
    ("abonos clubs", TipoMovimiento.ABONO_COMERCIAL, "movimiento.concepto.abonos_clubs.v2"),
    ("servicio basico", TipoMovimiento.SERVICIO, "movimiento.concepto.servicio_basico.v2"),
    ("serv.plataf.360", TipoMovimiento.SERVICIO, "movimiento.concepto.servicio_plataforma.v2"),
)


def _clave(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in normalizado if not unicodedata.combining(c))
    return " ".join(sin_acentos.casefold().split())


def clasificacion_conceptual_documental(descripcion: str) -> tuple[TipoMovimiento, str] | None:
    """Normaliza solo categoria/concepto; nunca determina CARGO o ABONO."""
    texto = _clave(descripcion)
    coincidencias = [fila[1:] for fila in _CLASIFICACIONES_CONCEPTUALES if fila[0] in texto]
    return coincidencias[0] if len(coincidencias) == 1 else None


def _clasificacion(descripcion: str, tipo_actual: TipoMovimiento) -> TipoMovimiento:
    texto = _clave(descripcion)
    inequivoca = clasificacion_conceptual_documental(descripcion)
    if inequivoca is not None:
        return inequivoca[0]
    if "abonaments" in texto:
        return TipoMovimiento.ABONO_COMERCIAL
    if "bonificacio pagament inmediat" in texto:
        return TipoMovimiento.BONIFICACION
    if "condicio operativa" in texto:
        return TipoMovimiento.CONDICION_COMERCIAL
    if "abo/devo" in texto:
        return TipoMovimiento.OTRO
    if "aproafa" in texto:
        return TipoMovimiento.CONDICION_COMERCIAL
    if "servicios operativos" in texto:
        return TipoMovimiento.SERVICIO
    if "devolucion" in texto:
        return TipoMovimiento.DEVOLUCION_MERCANCIA
    if any(frase in texto for frase in ("serv integral distribucion", "servicio logistico")):
        return TipoMovimiento.SERVICIO
    if any(frase in texto for frase in ("domiciliacion bancaria", "cofares directo", "cargo parafarmacia")):
        return TipoMovimiento.CONDICION_COMERCIAL
    return tipo_actual


def aplicar_reglas_pequenas(factura: FacturaNormalizada) -> FacturaNormalizada:
    movimientos = []
    for movimiento in factura.movimientos_comerciales:
        tipo = _clasificacion(movimiento.descripcion_literal.valor, movimiento.tipo)
        movimientos.append(movimiento.model_copy(update={"tipo": tipo}))

    albaranes = []
    referencias = list(factura.referencias_documentales)
    for albaran in factura.albaranes:
        etiqueta = albaran.tipo_pedido.valor if albaran.tipo_pedido else ""
        if _clave(etiqueta).startswith("delivery"):
            referencias.append(ReferenciaDocumental(
                orden=albaran.orden, tipo=TipoReferencia.DELIVERY,
                identificador=albaran.numero, descripcion_literal=albaran.tipo_pedido,
            ))
            continue
        albaranes.append(albaran)

    movimientos.sort(key=lambda item: (item.orden, item.descripcion_literal.valor))
    referencias.sort(key=lambda item: (item.orden, item.identificador.valor))
    actualizado = factura.model_copy(update={
        "albaranes": albaranes,
        "movimientos_comerciales": movimientos,
        "referencias_documentales": referencias,
    })
    evaluacion = validar_factura(actualizado)
    return actualizado.model_copy(update={
        "estado_validacion": evaluacion.estado,
        "validaciones": list(evaluacion.validaciones),
        "discrepancias_documentales": list(evaluacion.discrepancias),
        "incidencias": list(evaluacion.incidencias),
    })
