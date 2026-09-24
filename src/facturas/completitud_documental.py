"""Prueba conservadora de completitud antes de persistencia economica."""
from collections.abc import Mapping


MARCA_COMPLETITUD = "documento_completo_demostrado"

# Clasificacion transversal del contrato disponible, no de un PDF concreto.
# Los adaptadores parciales solo pueden emitir la marca positiva en el
# subconjunto estructural que evaluar_completitud_local demuestra expresamente.
COBERTURA_ADAPTADORES = {
    "alliance-local": "COBERTURA_COMPLETA",
    "hefame-local": "COBERTURA_COMPLETA",
    "hplus-consumo-local": "COBERTURA_COMPLETA",
    "cofares-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "fedefarma-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "ecoceutics-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "eports-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "logista-pharma-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "moretti-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "totalcare-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "loreal-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "farmacia-guimera-ocr-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "farmacia-guimera-historico-ocr-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "dermofarm-historico-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "gas-casa-historico-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "pierre-fabre-historico-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
    "suavinex-historico-local": "COBERTURA_PARCIAL_FAIL_CLOSED",
}


class ErrorCompletitudDocumental(ValueError):
    requiere_revision = True


def validar_completitud_antes_de_persistir(documento):
    """Solo una afirmacion positiva y explicita permite continuar.

    La ausencia de la marca no equivale a completitud. Nombre, ruta, bytes y
    hashes quedan deliberadamente fuera de este contrato.
    """
    if not isinstance(documento, Mapping) or documento.get(MARCA_COMPLETITUD) is not True:
        raise ErrorCompletitudDocumental("EXTRACCION_INCOMPLETA_REQUIERE_REVISION")
    return "DOCUMENTO_COMPLETO_DEMOSTRADO"


def validar_documento_antes_de_persistir(operativa, documento):
    """Barrera comun e indivisible de completitud y farmacia documental."""
    from src.facturas.barrera_farmacia import validar_farmacia_antes_de_persistir

    validar_completitud_antes_de_persistir(documento)
    return validar_farmacia_antes_de_persistir(operativa, documento)


def evaluar_completitud_local(adapter_id, documento, segmentos, facturas, incidencias):
    """Decide sobre cobertura inspeccionable; ante duda devuelve fail-closed."""
    bloqueantes = any(i.get("bloqueante") is True for i in incidencias if isinstance(i, Mapping))
    bloqueantes = bloqueantes or any(
        i.get("bloqueante") is True
        for factura in facturas if isinstance(factura, Mapping)
        for i in factura.get("incidencias", []) if isinstance(i, Mapping)
    )
    layouts_validos = bool(facturas) and all(f.get("layout") for f in facturas)
    segmentos_cubiertos = bool(segmentos) and len(facturas) == len(segmentos)
    estructura_valida = not bloqueantes and layouts_validos and segmentos_cubiertos

    if adapter_id in {"alliance-local", "hefame-local", "hplus-consumo-local"}:
        return estructura_valida
    if adapter_id == "cofares-local":
        return estructura_valida and len(documento.paginas) == 1
    if adapter_id == "fedefarma-local":
        return estructura_valida and all(s.paginas[0] == s.paginas[-1] for s in segmentos)
    if adapter_id == "logista-pharma-local":
        return estructura_valida and len(documento.paginas) == 1
    return False
