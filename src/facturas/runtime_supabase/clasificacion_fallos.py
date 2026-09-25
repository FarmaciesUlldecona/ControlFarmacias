"""Clasificacion de motivos de fallo de normalizacion (Hito 2AR, reglas R2/R3).

NO_SOPORTADO: falta de soporte de proveedor/layout/capacidad; el documento pasa a
PROVEEDOR_NO_SOPORTADO y solo vuelve a la cola por reprocesado explicito.
DEFECTO_DOCUMENTO y TRANSITORIO: reintentos acotados con backoff y REVISION al
maximo. Un motivo desconocido nunca se trata como no soportado.
"""
from __future__ import annotations

NO_SOPORTADO = "NO_SOPORTADO"
DEFECTO_DOCUMENTO = "DEFECTO_DOCUMENTO"
TRANSITORIO = "TRANSITORIO"
CLASES_FALLO = frozenset({NO_SOPORTADO, DEFECTO_DOCUMENTO, TRANSITORIO})

MOTIVOS_NO_SOPORTADO = frozenset({
    "PROVEEDOR_NO_SOPORTADO_MANUAL",
    "PROVEEDOR_NO_RECONOCIDO",
    "REQUIERE_OCR_O_LUNA_NO_AUTORIZADO",
    "LUNA_NO_AUTORIZADA_EN_COMPOSITOR_MANUAL",
    "ADAPTACION_NO_CERTIFICADA",
    "ADAPTADOR_MULTIFACTURA_NO_CERTIFICADO",
})

MOTIVOS_DEFECTO_DOCUMENTO = frozenset({
    "SHA256_NO_COINCIDE",
    "SHA256_REGISTRADO_INVALIDO",
    "RUTA_STORAGE_NO_COINCIDE_CON_CLAIM",
    "RUTA_STORAGE_NO_SEGURA",
    "OBJETO_STORAGE_VACIO",
    "DOCUMENTO_RECLAMADO_NO_LOCALIZADO",
    "EXTRACCION_LOCAL_ERROR",
    "DOCUMENTO_INCOMPLETO",
    "INVENTARIO_DOCUMENTAL_INVALIDO",
    "SEGMENTO_DUPLICADO_O_AUSENTE",
    "RANGO_FACTURA_INVALIDO",
    "PROVENANCE_INCOMPLETA",
    "SEGMENTOS_SOLAPADOS",
    "EVIDENCIA_FUERA_DE_FACTURA",
    "COBERTURA_DOCUMENTAL_INCOMPLETA",
    "SELECCION_NO_PERTENECE_AL_DOCUMENTO",
    "EXTRACCION_INCOMPLETA_REQUIERE_REVISION",
    "FARMACIA_DOCUMENTO_NO_DEMOSTRABLE",
    "FARMACIA_DOCUMENTO_CONTRADICTORIA",
    "NINGUNA_FACTURA_AUTORIZABLE_AUTOMATICAMENTE",
    "CAMPOS_PENDIENTES_TRAS_EXTRACCION",
    "DOCUMENTO_NORMALIZADO_AUSENTE",
    "IDEMPOTENCIA_PAYLOAD_DISTINTO",
    "INVENTARIO_RELECTURA_INCOMPATIBLE",
})

CODIGOS_DEFECTO_DOCUMENTO = frozenset({
    "ErrorCompletitudDocumental",
    "ErrorFarmaciaDocumental",
})


def clasificar_fallo(codigo: str | None, detalle: str | None) -> str:
    """Clasifica por el motivo literal; ante duda devuelve TRANSITORIO."""
    texto = str(detalle or "").strip()
    motivo = texto.split(":", 1)[0].strip()
    if motivo in MOTIVOS_NO_SOPORTADO:
        return NO_SOPORTADO
    if motivo in MOTIVOS_DEFECTO_DOCUMENTO:
        return DEFECTO_DOCUMENTO
    if any(m in texto for m in ("IDEMPOTENCIA_PAYLOAD_DISTINTO", "INVENTARIO_RELECTURA_INCOMPATIBLE")):
        return DEFECTO_DOCUMENTO
    if codigo in CODIGOS_DEFECTO_DOCUMENTO:
        return DEFECTO_DOCUMENTO
    return TRANSITORIO


# Conciliacion (Hito 2AV, regla R7): solo reintentos acotados con backoff. No
# existe "no soportado": un defecto documental o un motivo desconocido cuenta
# como intento y al maximo la factura pasa a REVISION_CONCILIACION.
CLASES_FALLO_CONCILIACION = frozenset({DEFECTO_DOCUMENTO, TRANSITORIO})

MOTIVOS_DEFECTO_CONCILIACION = frozenset({
    "IMPORTE_FACTURA_AUSENTE",
    "TIPO_DOCUMENTAL_NO_DEMOSTRADO",
    "TRAZABILIDAD_SERVICIO_INSUFICIENTE",
    "FARMACIA_DOCUMENTO_CONTRADICTORIA",
    "FARMACIA_DOCUMENTO_NO_DEMOSTRABLE",
    "EXTRACCION_INCOMPLETA_REQUIERE_REVISION",
})


def clasificar_fallo_conciliacion(codigo: str | None, detalle: str | None) -> str:
    """Clasifica un fallo de conciliacion; ante duda devuelve TRANSITORIO."""
    motivo = str(detalle or "").strip().split(":", 1)[0].strip()
    if codigo in MOTIVOS_DEFECTO_CONCILIACION or motivo in MOTIVOS_DEFECTO_CONCILIACION:
        return DEFECTO_DOCUMENTO
    if codigo in CODIGOS_DEFECTO_DOCUMENTO:
        return DEFECTO_DOCUMENTO
    return TRANSITORIO
