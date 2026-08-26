from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .modelos import (
    DiscrepanciaDocumental, EstadoValidacion, FacturaNormalizada, Incidencia,
    Severidad, TipoDiscrepancia,
)
from .validadores import TOLERANCIA_EUR, clave_funcional


@dataclass(frozen=True, slots=True)
class DescartePortada:
    factura_id: str
    motivo: str
    total_portada: Decimal
    suma_facturas: Decimal


@dataclass(frozen=True, slots=True)
class ResultadoConsolidacion:
    facturas: tuple[FacturaNormalizada, ...]
    descartes: tuple[DescartePortada, ...]
    conflictos: tuple[str, ...]


def _es_portada_literal(factura: FacturaNormalizada) -> bool:
    if factura.tipo_documento is None:
        return False
    texto = factura.tipo_documento.valor.casefold()
    return any(etiqueta in texto for etiqueta in ("portada", "resumen", "aviso"))


def _total(factura: FacturaNormalizada) -> Decimal | None:
    return factura.totales.total.valor if factura.totales.total is not None else None


def _mismo_proveedor(a: FacturaNormalizada, b: FacturaNormalizada) -> bool:
    if a.proveedor is None or a.proveedor.nombre is None or b.proveedor is None or b.proveedor.nombre is None:
        return False
    return (a.proveedor.alias_funcional or a.proveedor.nombre.valor).casefold() == (b.proveedor.alias_funcional or b.proveedor.nombre.valor).casefold()


def _sin_obligacion_fiscal_independiente(factura: FacturaNormalizada) -> bool:
    return not factura.impuestos and factura.numero_factura is None and _es_portada_literal(factura)


def _contenido_comparable(factura: FacturaNormalizada) -> dict:
    datos = factura.model_dump(mode="json", exclude={"factura_id", "estado_validacion", "incidencias", "validaciones", "discrepancias_documentales"})
    return datos


def _marcar_conflicto(base: FacturaNormalizada, otra: FacturaNormalizada) -> FacturaNormalizada:
    valores = []
    if base.totales.total is not None:
        valores.append(base.totales.total)
    if otra.totales.total is not None:
        valores.append(otra.totales.total)
    discrepancia = DiscrepanciaDocumental(
        tipo=TipoDiscrepancia.IDENTIFICADOR_AMBIGUO,
        descripcion="Misma clave proveedor+numero con versiones documentales contradictorias",
        valores_implicados=valores,
        material=True,
    )
    incidencia = Incidencia(
        codigo="DUPLICADO_CONFLICTIVO", severidad=Severidad.ERROR,
        descripcion="Dos candidatos comparten clave funcional y difieren",
        paginas=sorted({base.pagina_inicio, otra.pagina_inicio}), bloqueante=True,
    )
    return base.model_copy(update={
        "estado_validacion": EstadoValidacion.REQUIERE_REVISION,
        "discrepancias_documentales": [*base.discrepancias_documentales, discrepancia],
        "incidencias": [*base.incidencias, incidencia],
    })


def consolidar_facturas(facturas: Iterable[FacturaNormalizada]) -> ResultadoConsolidacion:
    candidatas = sorted(facturas, key=lambda f: (f.pagina_inicio, f.pagina_fin, f.factura_id))
    descartes: list[DescartePortada] = []
    activas = list(candidatas)
    for candidata in candidatas:
        if not _sin_obligacion_fiscal_independiente(candidata) or _total(candidata) is None:
            continue
        numeradas = [f for f in candidatas if f is not candidata and f.numero_factura is not None and _mismo_proveedor(candidata, f) and _total(f) is not None]
        if not numeradas:
            continue
        suma = sum((_total(f) for f in numeradas), Decimal("0"))
        if abs(_total(candidata) - suma) <= TOLERANCIA_EUR:
            activas.remove(candidata)
            descartes.append(DescartePortada(candidata.factura_id, "portada/resumen sin numero; total igual a suma de facturas numeradas; sin obligacion fiscal independiente", _total(candidata), suma))

    por_clave: dict[tuple[str, str], FacturaNormalizada] = {}
    sin_clave: list[FacturaNormalizada] = []
    conflictos: list[str] = []
    for factura in activas:
        clave = clave_funcional(factura)
        if clave is None:
            sin_clave.append(factura)
            continue
        previa = por_clave.get(clave)
        if previa is None:
            por_clave[clave] = factura
        elif _contenido_comparable(previa) != _contenido_comparable(factura):
            por_clave[clave] = _marcar_conflicto(previa, factura)
            conflictos.append(f"{clave[0]}|{clave[1]}")
    salida = sorted([*por_clave.values(), *sin_clave], key=lambda f: (f.pagina_inicio, f.pagina_fin, f.factura_id))
    return ResultadoConsolidacion(tuple(salida), tuple(descartes), tuple(conflictos))
