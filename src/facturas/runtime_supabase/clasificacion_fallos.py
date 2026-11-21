"""Clasificacion de motivos de fallo de normalizacion (Hito 2AR, reglas R2/R3).

NO_SOPORTADO: falta de soporte de proveedor/layout/capacidad; el documento pasa a
PROVEEDOR_NO_SOPORTADO y solo vuelve a la cola por reprocesado explicito.
DEFECTO_DOCUMENTO (migracion 37, decisiones de Pio D1 y D5): solo los motivos de
EXTRACCION (lista A) y de IDENTIDAD DE FARMACIA (lista B); con la 37 en la BD pasan a
REVISION en el primer fallo (sin la 37, reintentos como TRANSITORIO). Solo vuelven por
reprocesado explicito cuando cambie el lector.
TRANSITORIO: reintentos acotados con backoff y REVISION al maximo; incluye los motivos
de ALMACENAMIENTO (lista C, ``MOTIVOS_ALMACENAMIENTO``), que pueden ser una subida a
medias. Un motivo desconocido es TRANSITORIO, nunca no soportado ni defecto.
Listas: pruebas/auditoria_37/DISENO.md, seccion 2.1.
"""
from __future__ import annotations

NO_SOPORTADO = "NO_SOPORTADO"
DEFECTO_DOCUMENTO = "DEFECTO_DOCUMENTO"
TRANSITORIO = "TRANSITORIO"
CLASES_FALLO = frozenset({NO_SOPORTADO, DEFECTO_DOCUMENTO, TRANSITORIO})

MOTIVOS_NO_SOPORTADO = frozenset({
    "PROVEEDOR_NO_SOPORTADO_MANUAL",
    # AUTO-A (D1): proveedor, layout o version sin autoridad en la ruta automatica (R2).
    "PROVEEDOR_NO_SOPORTADO_AUTOMATICO",
    "PROVEEDOR_NO_RECONOCIDO",
    "REQUIERE_OCR_O_LUNA_NO_AUTORIZADO",
    "LUNA_NO_AUTORIZADA_EN_COMPOSITOR_MANUAL",
    "ADAPTACION_NO_CERTIFICADA",
    "ADAPTADOR_MULTIFACTURA_NO_CERTIFICADO",
})

# Lista A (extraccion) y lista B (identidad de farmacia): directos a REVISION con la 37 (D5).
MOTIVOS_DEFECTO_DOCUMENTO = frozenset({
    "EXTRACCION_LOCAL_ERROR",
    "EXTRACCION_INCOMPLETA_REQUIERE_REVISION",
    "CAMPOS_PENDIENTES_TRAS_EXTRACCION",
    "DOCUMENTO_NORMALIZADO_AUSENTE",
    "DOCUMENTO_INCOMPLETO",
    "COBERTURA_DOCUMENTAL_INCOMPLETA",
    "INVENTARIO_DOCUMENTAL_INVALIDO",
    "INVENTARIO_RELECTURA_INCOMPATIBLE",
    "SEGMENTO_DUPLICADO_O_AUSENTE",
    "SEGMENTOS_SOLAPADOS",
    "RANGO_FACTURA_INVALIDO",
    "EVIDENCIA_FUERA_DE_FACTURA",
    "SELECCION_NO_PERTENECE_AL_DOCUMENTO",
    "PROVENANCE_INCOMPLETA",
    "NINGUNA_FACTURA_AUTORIZABLE_AUTOMATICAMENTE",
    # Lista B: identidad de farmacia.
    "FARMACIA_DOCUMENTO_NO_DEMOSTRABLE",
    "FARMACIA_DOCUMENTO_CONTRADICTORIA",
})

# Lista C (almacenamiento, D1 y D5): TRANSITORIO, con reintentos y espera (R3).
MOTIVOS_ALMACENAMIENTO = frozenset({
    "SHA256_NO_COINCIDE",
    "SHA256_REGISTRADO_INVALIDO",
    "OBJETO_STORAGE_VACIO",
    "DOCUMENTO_RECLAMADO_NO_LOCALIZADO",
    "RUTA_STORAGE_NO_COINCIDE_CON_CLAIM",
    "RUTA_STORAGE_NO_SEGURA",
})
# 2BL: IDEMPOTENCIA_PAYLOAD_DISTINTO es un conflicto con una ejecucion ya registrada, no un defecto del
# documento (en la serie 2BJ fue un fallo de persistencia tomado por repeticion): queda como TRANSITORIO.

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
    if motivo in MOTIVOS_ALMACENAMIENTO:
        return TRANSITORIO
    if motivo in MOTIVOS_DEFECTO_DOCUMENTO:
        return DEFECTO_DOCUMENTO
    if "INVENTARIO_RELECTURA_INCOMPATIBLE" in texto:
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
