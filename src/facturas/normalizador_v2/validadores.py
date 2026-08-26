from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import re
import unicodedata
from typing import Iterable

from .modelos import (
    DiscrepanciaDocumental,
    EstadoValidacion,
    FacturaNormalizada,
    Incidencia,
    NaturalezaPrincipal,
    ResultadoControl,
    ResultadoValidacion,
    Sentido,
    Severidad,
    TipoDiscrepancia,
    ValorDocumentado,
)

TOLERANCIA_EUR = Decimal("0.01")
REGLA_VERSION = "normalizador-v2.validacion.1"
_PRECEDENCIA = {
    EstadoValidacion.VALIDADA: 0,
    EstadoValidacion.VALIDADA_CON_INCIDENCIAS: 1,
    EstadoValidacion.REQUIERE_SEGUNDA_LECTURA: 2,
    EstadoValidacion.REQUIERE_REVISION: 3,
    EstadoValidacion.ERROR_TECNICO: 4,
}


@dataclass(frozen=True, slots=True)
class ContextoValidacion:
    numero_paginas: int | None = None
    fallo_tecnico_global: bool = False
    senal_estructural_incompleta: bool = False
    identificadores_albaran_visibles: int = 0
    subtotal_albaranes_documental: ValorDocumentado[Decimal] | None = None


@dataclass(frozen=True, slots=True)
class EvaluacionFactura:
    estado: EstadoValidacion
    validaciones: tuple[ResultadoValidacion, ...]
    discrepancias: tuple[DiscrepanciaDocumental, ...]
    incidencias: tuple[Incidencia, ...]


def peor_estado(estados: Iterable[EstadoValidacion]) -> EstadoValidacion:
    valores = tuple(estados)
    return max(valores, key=_PRECEDENCIA.__getitem__) if valores else EstadoValidacion.REQUIERE_REVISION


def _control(codigo: str, resultado: ResultadoControl, descripcion: str, *, valores=None, tolerancia=None):
    return ResultadoValidacion(
        codigo=codigo,
        resultado=resultado,
        descripcion=descripcion,
        valores=valores or {},
        tolerancia_aplicada=tolerancia,
        regla_version=REGLA_VERSION,
    )


def _aproxima(a: Decimal, b: Decimal, tolerancia: Decimal = TOLERANCIA_EUR) -> bool:
    return abs(a - b) <= tolerancia


def _centimos(valor: Decimal) -> Decimal:
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


_SUFIJOS_SOCIALES = {"SA", "SAU", "SL", "SLU", "SRL"}
_SUFIJOS_SEPARADOS = (("S", "L", "U"), ("S", "A", "U"), ("S", "L"), ("S", "A"))


def normalizar_proveedor_identidad(nombre: str) -> str:
    texto = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().upper()
    tokens = re.findall(r"[A-Z0-9]+", texto)
    while tokens and tokens[-1] in _SUFIJOS_SOCIALES:
        tokens.pop()
    for sufijo in _SUFIJOS_SEPARADOS:
        if tuple(tokens[-len(sufijo):]) == sufijo:
            del tokens[-len(sufijo):]
            break
    while tokens and tokens[-1] in {"SOCIEDAD", "ANONIMA", "LIMITADA", "UNIPERSONAL"}:
        tokens.pop()
    return " ".join(tokens)


def clave_funcional(factura: FacturaNormalizada) -> tuple[str, str] | None:
    if factura.proveedor is None or factura.proveedor.nombre is None or factura.numero_factura is None:
        return None
    proveedor = factura.proveedor.alias_funcional or factura.proveedor.nombre.valor
    return (normalizar_proveedor_identidad(proveedor), " ".join(factura.numero_factura.valor.upper().split()))


def detectar_duplicados(facturas: Iterable[FacturaNormalizada]) -> dict[int, int]:
    primera_posicion: dict[tuple[str, str], int] = {}
    duplicados: dict[int, int] = {}
    for posicion, factura in enumerate(facturas):
        clave = clave_funcional(factura)
        if clave is None:
            continue
        if clave in primera_posicion:
            duplicados[posicion] = primera_posicion[clave]
        else:
            primera_posicion[clave] = posicion
    return duplicados


def validar_factura(
    factura: FacturaNormalizada,
    contexto: ContextoValidacion | None = None,
    *,
    duplicada: bool = False,
) -> EvaluacionFactura:
    contexto = contexto or ContextoValidacion()
    controles: list[ResultadoValidacion] = []
    discrepancias: list[DiscrepanciaDocumental] = list(factura.discrepancias_documentales)
    incidencias: list[Incidencia] = list(factura.incidencias)
    estado_candidatos = [EstadoValidacion.VALIDADA]

    if contexto.fallo_tecnico_global:
        controles.append(_control("TECNICO", ResultadoControl.FALLO, "fallo tecnico global"))
        estado_candidatos.append(EstadoValidacion.ERROR_TECNICO)
    else:
        controles.append(_control("TECNICO", ResultadoControl.OK, "lectura evaluable"))

    identidad_ok = clave_funcional(factura) is not None
    controles.append(_control("IDENTIDAD", ResultadoControl.OK if identidad_ok else ResultadoControl.FALLO, "proveedor y numero forman la clave preferida" if identidad_ok else "falta proveedor o numero demostrable"))
    if not identidad_ok:
        estado_candidatos.append(EstadoValidacion.REQUIERE_REVISION)

    paginas_ok = factura.pagina_inicio <= factura.pagina_fin and (
        contexto.numero_paginas is None or factura.pagina_fin <= contexto.numero_paginas
    )
    controles.append(_control("PAGINAS", ResultadoControl.OK if paginas_ok else ResultadoControl.FALLO, "rango de paginas valido" if paginas_ok else "rango fuera del documento"))
    if not paginas_ok:
        estado_candidatos.append(EstadoValidacion.REQUIERE_REVISION)

    controles.append(_control("DUPLICADO_FACTURA", ResultadoControl.FALLO if duplicada else ResultadoControl.OK, "clave repetida" if duplicada else "clave unica"))
    if duplicada:
        estado_candidatos.append(EstadoValidacion.REQUIERE_REVISION)

    totales = factura.totales
    componentes = [totales.base_imponible, totales.iva, totales.recargo_equivalencia, totales.otros]
    if totales.total is not None and any(valor is not None for valor in componentes):
        calculado = sum((valor.valor for valor in componentes if valor is not None), Decimal("0"))
        diferencia = calculado - totales.total.valor
        ok = _aproxima(calculado, totales.total.valor)
        controles.append(_control("CUADRE_TOTAL", ResultadoControl.OK if ok else ResultadoControl.FALLO, "componentes frente a total impreso", valores={"calculado": str(calculado), "impreso": str(totales.total.valor), "diferencia": str(diferencia)}, tolerancia=TOLERANCIA_EUR))
        if not ok:
            automatica = DiscrepanciaDocumental(tipo=TipoDiscrepancia.CUADRE_FISCAL, descripcion="Los componentes impresos no cuadran con el total impreso", importe_diferencia=abs(diferencia), valores_implicados=[valor for valor in componentes if valor is not None] + [totales.total], material=False)
            if automatica not in discrepancias:
                discrepancias.append(automatica)
            estado_candidatos.append(EstadoValidacion.VALIDADA_CON_INCIDENCIAS)
    else:
        controles.append(_control("CUADRE_TOTAL", ResultadoControl.NO_EVALUABLE, "faltan componentes o total visible", tolerancia=TOLERANCIA_EUR))

    fiscal_fallo = False
    for tramo in factura.impuestos:
        for sufijo, tipo, cuota in (
            ("IVA", tramo.tipo_iva, tramo.cuota_iva),
            ("RE", tramo.tipo_recargo_equivalencia, tramo.cuota_recargo_equivalencia),
        ):
            codigo = f"TRAMO_{tramo.orden}_{sufijo}"
            if tramo.base is None or tipo is None or cuota is None:
                controles.append(_control(codigo, ResultadoControl.NO_EVALUABLE, "faltan datos fiscales visibles", tolerancia=TOLERANCIA_EUR))
                continue
            esperado = _centimos(tramo.base.valor * tipo.valor / Decimal("100"))
            ok = _aproxima(esperado, cuota.valor)
            controles.append(_control(codigo, ResultadoControl.OK if ok else ResultadoControl.FALLO, "cuota fiscal frente a base y tipo", valores={"esperado": str(esperado), "impreso": str(cuota.valor)}, tolerancia=TOLERANCIA_EUR))
            fiscal_fallo |= not ok
    if not factura.impuestos:
        controles.append(_control("TRAMOS_FISCALES", ResultadoControl.NO_APLICA, "no hay tramos documentales"))
    if fiscal_fallo:
        discrepancias.append(DiscrepanciaDocumental(tipo=TipoDiscrepancia.CUADRE_FISCAL, descripcion="Al menos una cuota fiscal impresa difiere de base por tipo", material=False))
        estado_candidatos.append(EstadoValidacion.VALIDADA_CON_INCIDENCIAS)

    if factura.vencimientos:
        importes = [v.importe.valor for v in factura.vencimientos if v.importe is not None]
        if totales.total is not None and len(importes) == len(factura.vencimientos):
            suma = sum(importes, Decimal("0"))
            ok = _aproxima(suma, totales.total.valor)
            controles.append(_control("VENCIMIENTOS", ResultadoControl.OK if ok else ResultadoControl.FALLO, "suma de vencimientos visibles", valores={"suma": str(suma), "total": str(totales.total.valor)}, tolerancia=TOLERANCIA_EUR))
            if not ok:
                estado_candidatos.append(EstadoValidacion.VALIDADA_CON_INCIDENCIAS)
        else:
            controles.append(_control("VENCIMIENTOS", ResultadoControl.NO_EVALUABLE, "vencimientos visibles sin importes completos"))
    else:
        controles.append(_control("VENCIMIENTOS", ResultadoControl.NO_APLICA, "no hay vencimientos documentales"))

    movimientos_sin_sentido = [m for m in factura.movimientos_comerciales if m.sentido is None]
    if movimientos_sin_sentido:
        controles.append(_control(
            "MOVIMIENTOS_SENTIDO", ResultadoControl.NO_EVALUABLE,
            "uno o mas movimientos documentados no demuestran CARGO/ABONO",
            valores={"indeterminados": len(movimientos_sin_sentido), "total": len(factura.movimientos_comerciales)},
        ))
        descripcion_incidencia = "El documento demuestra movimientos comerciales, pero no su sentido CARGO/ABONO"
        if not any(i.codigo == "SENTIDO_NO_DOCUMENTADO" and i.descripcion == descripcion_incidencia for i in incidencias):
            evidencias = [e for m in movimientos_sin_sentido for e in m.descripcion_literal.evidencia]
            incidencias.append(Incidencia(
                codigo="SENTIDO_NO_DOCUMENTADO", severidad=Severidad.AVISO,
                descripcion=descripcion_incidencia,
                paginas=sorted({e.pagina for e in evidencias}), bloqueante=False,
                evidencias=evidencias,
            ))

    numeros = [albaran.numero.valor for albaran in factura.albaranes]
    duplicados_albaran = len(numeros) != len(set(numeros))
    controles.append(_control("ALBARANES_DUPLICADOS", ResultadoControl.FALLO if duplicados_albaran else (ResultadoControl.OK if numeros else ResultadoControl.NO_APLICA), "identificadores literales duplicados" if duplicados_albaran else "sin duplicados"))
    if duplicados_albaran:
        estado_candidatos.append(EstadoValidacion.REQUIERE_REVISION)

    if factura.naturaleza_principal == NaturalezaPrincipal.SERVICIOS and not factura.albaranes:
        controles.append(_control("ALBARANES_COMPLETITUD", ResultadoControl.NO_APLICA, "servicios sin entregas documentales"))
    elif contexto.senal_estructural_incompleta and contexto.identificadores_albaran_visibles > len(factura.albaranes):
        controles.append(_control("ALBARANES_COMPLETITUD", ResultadoControl.FALLO, "conteo visible incompatible con filas extraidas"))
        estado_candidatos.append(EstadoValidacion.REQUIERE_SEGUNDA_LECTURA)
    else:
        controles.append(_control("ALBARANES_COMPLETITUD", ResultadoControl.OK, "sin evidencia objetiva de omision estructural"))

    if contexto.subtotal_albaranes_documental is not None and factura.albaranes:
        comparables = [a.importe_total for a in factura.albaranes]
        if any(albaran.sentido is None for albaran in factura.albaranes):
            controles.append(_control("CUADRE_ALBARANES", ResultadoControl.NO_EVALUABLE, "sentido no documentado en una o mas filas"))
        elif all(valor is not None for valor in comparables):
            suma = sum(((valor.valor if albaran.sentido == Sentido.CARGO else -valor.valor) for albaran, valor in zip(factura.albaranes, comparables, strict=True)), Decimal("0"))
            subtotal = contexto.subtotal_albaranes_documental.valor
            ok = _aproxima(suma, subtotal)
            controles.append(_control("CUADRE_ALBARANES", ResultadoControl.OK if ok else ResultadoControl.FALLO, "detalle con sentido frente a subtotal", valores={"detalle": str(suma), "subtotal": str(subtotal), "diferencia": str(suma - subtotal)}, tolerancia=TOLERANCIA_EUR))
            if not ok:
                discrepancias.append(DiscrepanciaDocumental(tipo=TipoDiscrepancia.CUADRE_ALBARANES, descripcion="Detalle documental distinto del subtotal impreso", importe_diferencia=abs(suma - subtotal), valores_implicados=[contexto.subtotal_albaranes_documental], material=False))
                estado_candidatos.append(EstadoValidacion.VALIDADA_CON_INCIDENCIAS)
        else:
            controles.append(_control("CUADRE_ALBARANES", ResultadoControl.NO_EVALUABLE, "filas sin importes comparables"))
    else:
        controles.append(_control("CUADRE_ALBARANES", ResultadoControl.NO_APLICA, "no existe subtotal comparable"))

    controles.append(_control("SEPARACION_COLECCIONES", ResultadoControl.OK, "albaranes, movimientos y referencias usan contratos independientes"))
    controles.append(_control("EVIDENCIA_CERO_INVENCIONES", ResultadoControl.OK, "todo ValorDocumentado fue validado por el modelo estricto"))

    if discrepancias or incidencias:
        estado_candidatos.append(EstadoValidacion.VALIDADA_CON_INCIDENCIAS)
    estado = peor_estado(estado_candidatos)
    return EvaluacionFactura(estado, tuple(controles), tuple(discrepancias), tuple(incidencias))
