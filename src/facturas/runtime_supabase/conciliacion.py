from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping

from ..clasificacion_documental import TipoFacturaDocumental
from ..hefame_economia import derivar_magnitud_comparable_hefame
from .modelos import (
    DetalleConciliacion,
    ResultadoConciliacion,
    TipoRelacionConciliacion,
    conservar_id_proveedor,
)


CUATRO_DECIMALES = Decimal("0.0001")
TOLERANCIA_POR_DEFECTO = Decimal("0.0500")
VENTANA_FECHA_DIAS = 15
# R15c (2BA): sin coincidencia de numero (solo PUC) la ventana es de +-3 dias.
VENTANA_SIN_NUMERO_DIAS = 3
# Clases de numero que cuentan como coincidencia (ventana +-15, PUC o PVP, preferentes).
COINCIDENCIAS_NUMERO = frozenset({"EXACTA", "LETRA_FINAL", "FINAL_DOCUMENTAL"})
# R15b (2BA): numeracion interna de Farmatic (p. ej. Q039904/2026).
_NUMERO_INTERNO_FARMATIC = re.compile(r"^[A-Z]\d{6}/\d{4}$")
# Decision Pio (2BA): numero Alliance + una letra final = mismo numero (08C52171A = 08C52171).
_ALLIANCE_LETRA_FINAL = re.compile(r"^(08[A-Z]\d{5})[A-Z]$")
_FINAL_DOCUMENTAL_MIN_DIGITOS = 8
PROVEEDOR_CANONICO_ALLIANCE = "ALLIANCEHEALTHCARECENCORA"
PROVEEDOR_CANONICO_HEFAME_MERCANCIA = "HEFAMEMERCANCIA"
_ALIASES_ALLIANCE_AUTORIZADOS = frozenset({
    "SAFA",
    "1SAFA",
    "ALLIANCE",
    "ALLIANCEHEALTHCARE",
    "ALLIANCEHEALTHCAREESPANA",
    "CENCORA",
})
_ALIASES_HEFAME_MERCANCIA_AUTORIZADOS = frozenset({
    "3HEFAME",
    "HEFAME",
    "HDADFMCTCAMEDITSCL",
})


@dataclass(frozen=True, slots=True)
class AlbaranDocumentalTrabajo:
    id: str
    numero: str | None
    fecha: date | None
    importe: Decimal | None
    sentido: str | None = None
    magnitud_documental: str | None = None
    categoria_fiscal: str | None = None
    iva_pct: Decimal | None = None
    re_pct: Decimal | None = None
    importe_iva_derivado: Decimal | None = None
    importe_re_derivado: Decimal | None = None
    importe_comparable_operativo: Decimal | None = None
    provenance: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class MovimientoDocumentalTrabajo:
    id: str
    concepto_literal: str
    tipo: str
    sentido: str | None
    importe: Decimal | None = None
    base: Decimal | None = None
    provenance: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AjusteDocumentalTrabajo:
    concepto_literal: str
    importe: Decimal
    provenance: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CandidatoAlbaranSupabase:
    id_contador: int
    farmacia: str
    id_proveedor: str
    proveedor: str
    numero_albaran: str
    fecha: date
    importe_puc: Decimal | None
    importe_pvp: Decimal | None
    estado: str | None = None
    # 2BE (R17): IdRecepcion de Farmatic (migracion 22); sin recepcion no hay R17.
    id_recepcion: int | None = None

    def __post_init__(self) -> None:
        conservar_id_proveedor(self.id_proveedor)


@dataclass(frozen=True, slots=True)
class ResultadoBusquedaAlbaran:
    estado: str
    candidato: CandidatoAlbaranSupabase | None
    importe_compatible: Decimal | None
    coincidencia_numero: str
    candidatos_proveedor: int
    candidatos_fecha: int
    candidatos_importe: int
    candidatos_finales: int
    # 2BA: EXACTA | LETRA_FINAL | FINAL_DOCUMENTAL | INTERNO | PROVEEDOR | SIN_PATRON | NO_DISPONIBLE
    clase_numero: str | None = None
    # 2BE (R17, estado MATCH_R17): albaran interno de la misma recepcion que completa la linea.
    complementario: CandidatoAlbaranSupabase | None = None
    importe_complementario: Decimal | None = None


def canonicalizar_proveedor(valor: str | None) -> str | None:
    """Identidad conservadora, incluida la equivalencia Alliance autorizada por Pio."""
    if valor is None:
        return None
    texto = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode().upper()
    tokens = re.findall(r"[A-Z0-9]+", texto)
    while tokens and tokens[-1] in {"SA", "SAU", "SL", "SLU", "SRL"}:
        tokens.pop()
    for suffix in (("S", "A", "U"), ("S", "L", "U"), ("S", "A"), ("S", "L")):
        if tuple(tokens[-len(suffix):]) == suffix:
            del tokens[-len(suffix):]
            break
    normalizado = "".join(tokens) or None
    if normalizado in _ALIASES_ALLIANCE_AUTORIZADOS:
        return PROVEEDOR_CANONICO_ALLIANCE
    if normalizado in _ALIASES_HEFAME_MERCANCIA_AUTORIZADOS:
        return PROVEEDOR_CANONICO_HEFAME_MERCANCIA
    return normalizado


def normalizar_numero_albaran(valor: str | None) -> str | None:
    if valor is None:
        return None
    normalizado = "".join(re.findall(r"[A-Z0-9]+", unicodedata.normalize("NFKD", valor).upper()))
    return normalizado or None


def _id_proveedor_comparable(valor: str | None) -> str | None:
    """R9 (2AV): solo para comparar; '2', '0002' y '0002 ' son el mismo proveedor.

    El literal se conserva en datos y persistencia (``conservar_id_proveedor``).
    """
    if valor is None:
        return None
    texto = valor.strip()
    if texto.isdigit():
        return texto.lstrip("0") or "0"
    return texto or None


def comparar_numeros_albaran(documental: str | None, operacional: str | None) -> str:
    izquierda = normalizar_numero_albaran(documental)
    derecha = normalizar_numero_albaran(operacional)
    if izquierda is None or derecha is None:
        return "NO_DISPONIBLE"
    if izquierda == derecha:
        return "EXACTA"
    return "DIFERENTE"


def clasificar_numero_albaran(documental: str | None, operacional: str | None, *, alliance: bool) -> str:
    """R15b (2BA) y decisiones de Pio sobre la comparacion de numeros de albaran.

    - EXACTA: mismo numero normalizado.
    - LETRA_FINAL (solo Alliance): 08+letra+5 digitos y una letra final sobre el numero documental.
    - FINAL_DOCUMENTAL: numero Farmatic de >= 8 digitos que es el final del documental.
    - INTERNO: numeracion interna de Farmatic; puede casar por PUC con numero distinto.
    - PROVEEDOR (solo Alliance): cualquier otro numero (formato Alliance distinto, SAFA de
      12 digitos...): nunca casa por importe (falla cerrado).
    - SIN_PATRON: proveedor sin patron de numeracion: puede casar por PUC (+-3 dias).
    """
    base = comparar_numeros_albaran(documental, operacional)
    if base == "EXACTA":
        return base
    op_literal = (operacional or "").strip().upper()
    doc = normalizar_numero_albaran(documental)
    op = normalizar_numero_albaran(operacional)
    if doc is not None and op is not None:
        letra = _ALLIANCE_LETRA_FINAL.match(op)
        if alliance and letra and letra.group(1) == doc:
            return "LETRA_FINAL"
        if op.isdigit() and len(op) >= _FINAL_DOCUMENTAL_MIN_DIGITOS and len(doc) > len(op) and doc.endswith(op):
            return "FINAL_DOCUMENTAL"
    if op is None:
        return "NO_DISPONIBLE"
    if _NUMERO_INTERNO_FARMATIC.match(op_literal):
        return "INTERNO"
    return "PROVEEDOR" if alliance else "SIN_PATRON"


def _importe_compatible(
    documental: Decimal,
    candidato: CandidatoAlbaranSupabase,
    tolerancia: Decimal,
    *,
    comparar_magnitud: bool = False,
    solo_puc: bool = False,
) -> Decimal | None:
    esperado = abs(dinero(documental)) if comparar_magnitud else dinero(documental)
    compatibles = []
    valores = (candidato.importe_puc,) if solo_puc else (candidato.importe_puc, candidato.importe_pvp)
    for valor in valores:
        if valor is None:
            continue
        candidato_normalizado = dinero(valor)
        comparable = abs(candidato_normalizado) if comparar_magnitud else candidato_normalizado
        if abs(comparable - esperado) <= tolerancia:
            compatibles.append(comparable)
    return min(compatibles, key=lambda value: abs(value - esperado)) if compatibles else None


def _filas_del_proveedor(
    rows: tuple[CandidatoAlbaranSupabase, ...],
    proveedor_literal: str | None,
    farmatic_id_proveedor: str | None,
) -> tuple[str | None, list[CandidatoAlbaranSupabase]]:
    provider_key = canonicalizar_proveedor(proveedor_literal)
    provider_id = conservar_id_proveedor(farmatic_id_proveedor)
    if provider_id is not None:
        provider_comparable = _id_proveedor_comparable(provider_id)
        return provider_key, [
            row for row in rows
            if provider_comparable is not None
            and _id_proveedor_comparable(row.id_proveedor) == provider_comparable
        ]
    if provider_key is not None:
        return provider_key, [row for row in rows if canonicalizar_proveedor(row.proveedor) == provider_key]
    return provider_key, []


def _clave_albaran(row: CandidatoAlbaranSupabase) -> tuple[str, int]:
    return (row.farmacia, row.id_contador)


def _admisible(
    documental: AlbaranDocumentalTrabajo,
    row: CandidatoAlbaranSupabase,
    clase: str,
    *,
    ventana_dias: int,
    ventana_sin_numero_dias: int,
    numeros_otras_facturas: frozenset[str],
) -> bool:
    """R15c y opcion 2 de R15: ventana segun la clase y numeros reservados a otras facturas."""
    if documental.fecha is None:
        return False
    dias = abs((row.fecha - documental.fecha).days)
    if clase in COINCIDENCIAS_NUMERO:
        return dias <= ventana_dias
    if dias > ventana_sin_numero_dias:
        return False
    return normalizar_numero_albaran(row.numero_albaran) not in numeros_otras_facturas


def _seleccionar(
    documental: AlbaranDocumentalTrabajo,
    by_provider: list[CandidatoAlbaranSupabase],
    provider_key: str | None,
    tolerancia_decimal: Decimal,
    *,
    ventana_dias: int,
    ventana_sin_numero_dias: int,
    ocupados: frozenset[tuple[str, int]],
    numeros_otras_facturas: frozenset[str],
    aplicar_r15b: bool = True,
) -> ResultadoBusquedaAlbaran:
    alliance = provider_key == PROVEEDOR_CANONICO_ALLIANCE
    hefame = provider_key == PROVEEDOR_CANONICO_HEFAME_MERCANCIA
    libres = [row for row in by_provider if _clave_albaran(row) not in ocupados]
    if hefame:
        clases = {row.id_contador: comparar_numeros_albaran(documental.numero, row.numero_albaran) for row in libres}
        by_date = [
            row for row in libres
            if documental.fecha is not None and abs((row.fecha - documental.fecha).days) <= ventana_dias
        ]
    else:
        clases = {
            row.id_contador: clasificar_numero_albaran(documental.numero, row.numero_albaran, alliance=alliance)
            for row in libres
        }
        by_date = [
            row for row in libres
            if _admisible(documental, row, clases[row.id_contador], ventana_dias=ventana_dias,
                          ventana_sin_numero_dias=ventana_sin_numero_dias,
                          numeros_otras_facturas=numeros_otras_facturas)
        ]
        # Decision Pio (2BA): el numero exacto se impone a la letra final y al final del documental.
        if any(clases[row.id_contador] == "EXACTA" for row in by_date):
            by_date = [row for row in by_date if clases[row.id_contador] not in ("LETRA_FINAL", "FINAL_DOCUMENTAL")]
        if aplicar_r15b:
            by_date = [row for row in by_date if clases[row.id_contador] != "PROVEEDOR"]
    amounts = []
    importe_para_matching = documental.importe_comparable_operativo if hefame else documental.importe
    if importe_para_matching is not None:
        expected = dinero(importe_para_matching)
        for row in by_date:
            clase = clases[row.id_contador]
            # D11 (2AZ): sin coincidencia de numero solo se admite el PUC; casar por PVP queda prohibido.
            compatible = _importe_compatible(
                expected,
                row,
                tolerancia_decimal,
                comparar_magnitud=documental.sentido == "ABONO",
                solo_puc=clase not in COINCIDENCIAS_NUMERO,
            )
            if compatible is not None:
                amounts.append((row, compatible, clase))
    if hefame:
        exact_number = [
            row for row in libres
            if clases[row.id_contador] == "EXACTA"
        ]
        if not exact_number:
            return ResultadoBusquedaAlbaran(
                "NUMERO_AUSENTE", None, None, "DIFERENTE",
                len(by_provider), len(by_date), len(amounts), 0,
            )
        exact_in_window = [row for row in by_date if row in exact_number]
        if not exact_in_window or importe_para_matching is None:
            return ResultadoBusquedaAlbaran(
                "NO_DEMOSTRABLE", None, None, "EXACTA",
                len(by_provider), len(by_date), len(amounts), 0,
            )
        finalists = [item for item in amounts if item[2] == "EXACTA"]
        if not finalists:
            return ResultadoBusquedaAlbaran(
                "NUMERO_EXACTO_ECONOMIA_INCOMPATIBLE",
                exact_in_window[0] if len(exact_in_window) == 1 else None,
                None, "EXACTA", len(by_provider), len(by_date), len(amounts), 0,
            )
    else:
        with_number = [item for item in amounts if item[2] in COINCIDENCIAS_NUMERO]
        finalists = with_number if with_number else amounts
    if finalists:
        expected_comparable = abs(expected) if documental.sentido == "ABONO" else expected
        diferencia_minima = min(abs(item[1] - expected_comparable) for item in finalists)
        closest_amount = [
            item for item in finalists
            if abs(item[1] - expected_comparable) == diferencia_minima
        ]
        finalists = closest_amount
    # Decision Pio (2BA): varias coincidencias por letra final o final del documental que el
    # importe no separa -> no casa (la fecha no desempata).
    sin_desempate = len(finalists) > 1 and any(item[2] in ("LETRA_FINAL", "FINAL_DOCUMENTAL") for item in finalists)
    with_exact_date = [item for item in finalists if documental.fecha == item[0].fecha]
    if len(with_exact_date) == 1 and not sin_desempate:
        finalists = with_exact_date
    if len(finalists) == 1:
        row, amount, clase = finalists[0]
        return ResultadoBusquedaAlbaran(
            "EXACTO_ECONOMICO" if hefame else "MATCH_UNICO",
            row, amount, comparar_numeros_albaran(documental.numero, row.numero_albaran),
            len(by_provider), len(by_date), len(amounts), 1, clase,
        )
    return ResultadoBusquedaAlbaran(
        "AMBIGUO" if len(finalists) > 1 else "SIN_COINCIDENCIA",
        None,
        None,
        "DIFERENTE" if amounts else "NO_EVALUADO",
        len(by_provider),
        len(by_date),
        len(amounts),
        len(finalists),
    )


def buscar_candidato_albaran(
    documental: AlbaranDocumentalTrabajo,
    candidatos: Iterable[CandidatoAlbaranSupabase],
    *,
    proveedor_literal: str | None,
    farmatic_id_proveedor: str | None = None,
    tolerancia: Decimal | int | float | str = TOLERANCIA_POR_DEFECTO,
    ventana_dias: int = VENTANA_FECHA_DIAS,
    ventana_sin_numero_dias: int = VENTANA_SIN_NUMERO_DIAS,
    ocupados: Iterable[tuple[str, int]] = (),
    numeros_otras_facturas: Iterable[str] = (),
) -> ResultadoBusquedaAlbaran:
    """Selecciona solo una coincidencia demostrable; nunca resuelve ambiguedad por orden.

    R15 (2BA): se salta los albaranes ``ocupados`` (otra conciliacion vigente u otra linea
    de esta factura) y no toma por importe un numero que es exactamente el de una linea
    documental de otra factura (``numeros_otras_facturas``, normalizados). R15b/R15c y las
    decisiones de Pio sobre la letra final y el final del documental: ``clasificar_numero_albaran``.
    Si la linea solo encuentra un albaran ocupado: ``ALBARAN_YA_CONCILIADO``; si solo un
    numero de proveedor distinto: ``NUMERO_PROVEEDOR_DISTINTO``.
    """
    tolerancia_decimal = dinero(tolerancia)
    if tolerancia_decimal < 0 or ventana_dias < 0 or ventana_sin_numero_dias < 0:
        raise ValueError("tolerancia y ventana deben ser no negativas")
    rows = tuple(candidatos)
    provider_key, by_provider = _filas_del_proveedor(rows, proveedor_literal, farmatic_id_proveedor)
    ocupados_set = frozenset(ocupados)
    numeros_set = frozenset(n for n in (normalizar_numero_albaran(x) for x in numeros_otras_facturas) if n)
    parametros = dict(ventana_dias=ventana_dias, ventana_sin_numero_dias=ventana_sin_numero_dias,
                      numeros_otras_facturas=numeros_set)
    resultado = _seleccionar(documental, by_provider, provider_key, tolerancia_decimal,
                             ocupados=ocupados_set, **parametros)
    if resultado.candidato is not None or resultado.estado not in ("SIN_COINCIDENCIA", "NUMERO_AUSENTE",
                                                                   "NO_DEMOSTRABLE"):
        return resultado
    if ocupados_set:
        sin_ocupacion = _seleccionar(documental, by_provider, provider_key, tolerancia_decimal,
                                     ocupados=frozenset(), **parametros)
        if sin_ocupacion.candidato is not None and _clave_albaran(sin_ocupacion.candidato) in ocupados_set:
            return replace(resultado, estado="ALBARAN_YA_CONCILIADO")
    if provider_key == PROVEEDOR_CANONICO_ALLIANCE:
        sin_r15b = _seleccionar(documental, by_provider, provider_key, tolerancia_decimal,
                                ocupados=ocupados_set, aplicar_r15b=False, **parametros)
        if sin_r15b.candidato is not None:
            return replace(resultado, estado="NUMERO_PROVEEDOR_DISTINTO")
    return resultado


def buscar_albaranes_factura(
    documentales: Iterable[AlbaranDocumentalTrabajo],
    candidatos: Iterable[CandidatoAlbaranSupabase],
    *,
    proveedor_literal: str | None,
    farmatic_id_proveedor: str | None = None,
    ocupados: Iterable[tuple[str, int]] = (),
    numeros_otras_facturas: Iterable[str] = (),
    tolerancia: Decimal | int | float | str = TOLERANCIA_POR_DEFECTO,
    ventana_dias: int = VENTANA_FECHA_DIAS,
    ventana_sin_numero_dias: int = VENTANA_SIN_NUMERO_DIAS,
) -> tuple[ResultadoBusquedaAlbaran, ...]:
    """R15 (2BA) para todas las lineas de una factura; resultados en el orden documental.

    Un albaran solo justifica una linea: lo elegido por una linea queda ocupado para las
    demas. Primero se buscan las lineas con algun candidato con coincidencia de numero,
    para que una linea por importe no se lleve el albaran que otra tiene por numero.
    Despues, R17 (2BE) para las lineas que quedan ``SIN_COINCIDENCIA``: ``_parejas_r17``.
    """
    docs = tuple(documentales)
    rows = tuple(candidatos)
    provider_key, by_provider = _filas_del_proveedor(rows, proveedor_literal, farmatic_id_proveedor)
    alliance = provider_key == PROVEEDOR_CANONICO_ALLIANCE

    def con_numero(documental: AlbaranDocumentalTrabajo) -> bool:
        return documental.fecha is not None and any(
            clasificar_numero_albaran(documental.numero, row.numero_albaran, alliance=alliance)
            in COINCIDENCIAS_NUMERO
            and abs((row.fecha - documental.fecha).days) <= ventana_dias
            for row in by_provider
        )

    orden = sorted(range(len(docs)), key=lambda i: (not con_numero(docs[i]), i))
    externos = frozenset(ocupados)
    numeros = tuple(numeros_otras_facturas)
    propios: set[tuple[str, int]] = set()
    resultados: list[ResultadoBusquedaAlbaran | None] = [None] * len(docs)
    for i in orden:
        resultado = buscar_candidato_albaran(
            docs[i], rows, proveedor_literal=proveedor_literal, farmatic_id_proveedor=farmatic_id_proveedor,
            tolerancia=tolerancia, ventana_dias=ventana_dias, ventana_sin_numero_dias=ventana_sin_numero_dias,
            ocupados=externos | propios, numeros_otras_facturas=numeros,
        )
        if resultado.candidato is not None and resultado.importe_compatible is not None:
            propios.add(_clave_albaran(resultado.candidato))
        resultados[i] = resultado
    if provider_key != PROVEEDOR_CANONICO_HEFAME_MERCANCIA:
        _aplicar_r17(docs, resultados, by_provider, externos | propios, alliance=alliance,
                     tolerancia=dinero(tolerancia), ventana_dias=ventana_dias,
                     numeros_otras_facturas=frozenset(
                         n for n in (normalizar_numero_albaran(x) for x in numeros) if n))
    return tuple(r for r in resultados if r is not None)


def _parejas_r17(
    documental: AlbaranDocumentalTrabajo,
    libres: list[CandidatoAlbaranSupabase],
    *,
    alliance: bool,
    tolerancia: Decimal,
    ventana_dias: int,
    numeros_otras_facturas: frozenset[str],
) -> list[tuple[CandidatoAlbaranSupabase, CandidatoAlbaranSupabase]]:
    """R17 (2BE, aprobada por Pio): parejas (A, B) que suman la linea documental.

    A = el albaran de su numero (EXACTA o LETRA_FINAL; el exacto se impone, +-ventana_dias).
    B = un albaran con numeracion interna de Farmatic (``[A-Z]\\d{6}/\\d{4}``) de la MISMA
    recepcion que A, mismo proveedor (R9), numero no reservado a otra factura (R15).
    PUC(A) + PUC(B) dentro de la tolerancia por linea. Solo cargos y solo 1+1.
    """
    if documental.fecha is None or documental.importe is None or documental.sentido != "CARGO":
        return []
    esperado = dinero(documental.importe)
    clases = {row.id_contador: clasificar_numero_albaran(documental.numero, row.numero_albaran, alliance=alliance)
              for row in libres}
    con_numero = [row for row in libres if clases[row.id_contador] in ("EXACTA", "LETRA_FINAL")
                  and abs((row.fecha - documental.fecha).days) <= ventana_dias]
    if any(clases[row.id_contador] == "EXACTA" for row in con_numero):
        con_numero = [row for row in con_numero if clases[row.id_contador] == "EXACTA"]
    parejas = []
    for a in con_numero:
        if a.id_recepcion is None or a.importe_puc is None:
            continue
        for b in libres:
            if (b.id_contador == a.id_contador or b.id_recepcion != a.id_recepcion or b.importe_puc is None
                    or not _NUMERO_INTERNO_FARMATIC.match(b.numero_albaran.strip().upper())
                    or _id_proveedor_comparable(b.id_proveedor) != _id_proveedor_comparable(a.id_proveedor)
                    or normalizar_numero_albaran(b.numero_albaran) in numeros_otras_facturas):
                continue
            if abs(dinero(a.importe_puc) + dinero(b.importe_puc) - esperado) <= tolerancia:
                parejas.append((a, b))
    return parejas


def _aplicar_r17(
    docs: tuple[AlbaranDocumentalTrabajo, ...],
    resultados: list[ResultadoBusquedaAlbaran | None],
    by_provider: list[CandidatoAlbaranSupabase],
    ocupados: frozenset[tuple[str, int]],
    *,
    alliance: bool,
    tolerancia: Decimal,
    ventana_dias: int,
    numeros_otras_facturas: frozenset[str],
) -> None:
    """R17 despues del casado 1:1. Falla cerrado: mas de una pareja para una linea, o un albaran
    en las parejas de dos lineas, deja esas lineas sin casar (sin depender del orden)."""
    libres = [row for row in by_provider if _clave_albaran(row) not in ocupados]
    parejas = {
        i: _parejas_r17(docs[i], libres, alliance=alliance, tolerancia=tolerancia, ventana_dias=ventana_dias,
                        numeros_otras_facturas=numeros_otras_facturas)
        for i, resultado in enumerate(resultados)
        if resultado is not None and resultado.estado == "SIN_COINCIDENCIA"
    }
    uso: dict[tuple[str, int], int] = {}
    for opciones in parejas.values():
        for clave in {_clave_albaran(row) for pareja in opciones for row in pareja}:
            uso[clave] = uso.get(clave, 0) + 1
    for i, opciones in parejas.items():
        if not opciones:
            continue
        previo = resultados[i]
        assert previo is not None
        if len(opciones) > 1:
            resultados[i] = replace(previo, estado="AMBIGUO_R17", candidatos_finales=len(opciones))
            continue
        a, b = opciones[0]
        if uso[_clave_albaran(a)] > 1 or uso[_clave_albaran(b)] > 1:
            resultados[i] = replace(previo, estado="CONFLICTO_R17")
            continue
        resultados[i] = ResultadoBusquedaAlbaran(
            "MATCH_R17", a, dinero(a.importe_puc), comparar_numeros_albaran(docs[i].numero, a.numero_albaran),
            previo.candidatos_proveedor, previo.candidatos_fecha, previo.candidatos_importe, 1,
            clasificar_numero_albaran(docs[i].numero, a.numero_albaran, alliance=alliance),
            complementario=b, importe_complementario=dinero(b.importe_puc))


def detalles_desde_busqueda(
    documental: AlbaranDocumentalTrabajo,
    resultado: ResultadoBusquedaAlbaran,
) -> tuple[DetalleConciliacion, ...]:
    """Detalles de una linea: uno (1:1 o sin coincidencia) o dos ``UNO_A_VARIOS`` (R17, 2BE).

    En R17 cada albaran aplica su PUC; ambos llevan el mismo origen documental y la misma
    recepcion. ``cf_persistir_conciliacion`` (migracion 24) revalida la pareja.
    """
    if resultado.complementario is None:
        return (detalle_desde_busqueda(documental, resultado),)
    a, b = resultado.candidato, resultado.complementario
    if (resultado.estado != "MATCH_R17" or a is None or resultado.importe_compatible is None
            or resultado.importe_complementario is None):
        raise ValueError("RESULTADO_R17_INCOMPLETO")
    comun = {
        "fuente": "ALBARANES_SUPABASE",
        "estado_matching": "MATCH_R17",
        "regla": "R17",
        "id_recepcion": a.id_recepcion,
        "numero_documental": documental.numero,
        "fecha_documental": documental.fecha.isoformat() if documental.fecha else None,
        "importe_documental": str(documental.importe),
        "importe_pareja": str(resultado.importe_compatible + resultado.importe_complementario),
        "sentido_documental": documental.sentido,
    }

    def detalle(row: CandidatoAlbaranSupabase, importe: Decimal, papel: str, clase: str | None) -> DetalleConciliacion:
        return DetalleConciliacion(
            tipo_relacion=TipoRelacionConciliacion.UNO_A_VARIOS,
            importe_aplicado=importe,
            albaran_farmacia=row.farmacia,
            albaran_id_contador=row.id_contador,
            factura_albaran_extraido_id=documental.id,
            coincidencia_numero_literal=papel == "NUMERO" and resultado.coincidencia_numero == "EXACTA",
            provenance={**comun, "papel_r17": papel, "clase_numero": clase,
                        "numero_operacional": row.numero_albaran, "id_proveedor": row.id_proveedor,
                        "fecha_operacional": row.fecha.isoformat()},
        )

    return (detalle(a, resultado.importe_compatible, "NUMERO", resultado.clase_numero),
            detalle(b, resultado.importe_complementario, "INTERNO", "INTERNO"))


def detalle_desde_busqueda(
    documental: AlbaranDocumentalTrabajo,
    resultado: ResultadoBusquedaAlbaran,
) -> DetalleConciliacion:
    if resultado.complementario is not None:
        # 2BE: una linea R17 son dos detalles; usar ``detalles_desde_busqueda`` (falla cerrado).
        raise ValueError("RESULTADO_R17_REQUIERE_DOS_DETALLES")
    if resultado.candidato is None or resultado.importe_compatible is None:
        return DetalleConciliacion(
            tipo_relacion=TipoRelacionConciliacion.SIN_COINCIDENCIA,
            importe_aplicado=Decimal("0"),
            factura_albaran_extraido_id=documental.id,
            provenance={
                "fuente": "ALBARANES_SUPABASE",
                "estado_matching": resultado.estado,
                "candidatos_finales": resultado.candidatos_finales,
                "sentido_documental": documental.sentido,
            },
        )
    candidate = resultado.candidato
    return DetalleConciliacion(
        tipo_relacion=TipoRelacionConciliacion.UNO_A_UNO,
        importe_aplicado=(
            -abs(resultado.importe_compatible)
            if documental.sentido == "ABONO"
            else resultado.importe_compatible
        ),
        albaran_farmacia=candidate.farmacia,
        albaran_id_contador=candidate.id_contador,
        factura_albaran_extraido_id=documental.id,
        coincidencia_numero_literal=resultado.coincidencia_numero == "EXACTA",
        provenance={
            "fuente": "ALBARANES_SUPABASE",
            "estado_matching": resultado.estado,
            "coincidencia_numero": resultado.coincidencia_numero,
            "clase_numero": resultado.clase_numero,
            "numero_documental": documental.numero,
            "numero_operacional": candidate.numero_albaran,
            "id_proveedor": candidate.id_proveedor,
            "fecha_documental": documental.fecha.isoformat() if documental.fecha else None,
            "fecha_operacional": candidate.fecha.isoformat(),
            "sentido_documental": documental.sentido,
        },
    )


def dinero(valor: Decimal | int | float | str) -> Decimal:
    return Decimal(str(valor)).quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)


def _importe_con_sentido(valor: Decimal, sentido: str) -> Decimal:
    magnitud = abs(dinero(valor))
    return magnitud if sentido == "CARGO" else -magnitud


def conciliar_movimientos_documentales(
    importe_factura: Decimal | int | float | str,
    movimientos: Iterable[MovimientoDocumentalTrabajo],
    *,
    ajustes: Iterable[AjusteDocumentalTrabajo] = (),
    tolerancia: Decimal | int | float | str = TOLERANCIA_POR_DEFECTO,
) -> ResultadoConciliacion:
    """Concilia servicios por importes o, si todos faltan, por bases y fiscalidad visible."""
    movimientos = tuple(movimientos)
    ajustes = tuple(ajustes)
    detalles = construir_detalles_movimientos_documentales(movimientos, ajustes=ajustes)
    if detalles is None:
        factura = dinero(importe_factura)
        return ResultadoConciliacion(
            importe_factura=factura,
            importe_explicado=Decimal("0.0000"),
            diferencia=factura,
            tolerancia=dinero(tolerancia),
            resultado="PENDIENTE_REVISION_PIO",
            detalles=(),
        )
    return conciliar_importes(importe_factura, detalles, tolerancia=tolerancia)


def construir_detalles_movimientos_documentales(
    movimientos: Iterable[MovimientoDocumentalTrabajo],
    *,
    ajustes: Iterable[AjusteDocumentalTrabajo] = (),
) -> tuple[DetalleConciliacion, ...] | None:
    """Materializa detalles sin inventar importes; ``None`` indica traza insuficiente."""
    movimientos = tuple(movimientos)
    ajustes = tuple(ajustes)
    sentidos_completos = all(m.sentido in {"CARGO", "ABONO"} for m in movimientos)
    por_importes = bool(movimientos) and all(m.importe is not None for m in movimientos)
    por_bases = bool(movimientos) and all(m.importe is None and m.base is not None for m in movimientos)
    if not sentidos_completos or not (por_importes or por_bases):
        return None

    detalles = []
    for movimiento in movimientos:
        valor = movimiento.importe if por_importes else movimiento.base
        assert valor is not None and movimiento.sentido is not None
        detalles.append(DetalleConciliacion(
            tipo_relacion=TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC,
            importe_aplicado=_importe_con_sentido(valor, movimiento.sentido),
            factura_movimiento_id=movimiento.id,
            provenance={
                **dict(movimiento.provenance or {}),
                "fuente": "MOVIMIENTO_DOCUMENTAL",
                "concepto_literal": movimiento.concepto_literal,
                "tipo": movimiento.tipo,
                "sentido": movimiento.sentido,
                "magnitud_usada": "IMPORTE" if por_importes else "BASE",
            },
        ))
    if por_bases:
        detalles.extend(
            DetalleConciliacion(
                tipo_relacion=TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC,
                importe_aplicado=dinero(ajuste.importe),
                provenance={
                    **dict(ajuste.provenance),
                    "fuente": "FISCALIDAD_AJUSTE_DOCUMENTAL",
                    "concepto_literal": ajuste.concepto_literal,
                },
            )
            for ajuste in ajustes
        )
    return tuple(detalles)


def conciliar_factura_documental(
    tipo: TipoFacturaDocumental | str,
    importe_factura: Decimal | int | float | str,
    *,
    detalles_albaranes: Iterable[DetalleConciliacion] = (),
    movimientos: Iterable[MovimientoDocumentalTrabajo] = (),
    ajustes: Iterable[AjusteDocumentalTrabajo] = (),
    tolerancia: Decimal | int | float | str = TOLERANCIA_POR_DEFECTO,
) -> ResultadoConciliacion:
    """Despacha la conciliacion por el tipo demostrado y suma ambos bloques en mixtas."""
    tipo = TipoFacturaDocumental(tipo)
    detalles_albaranes = tuple(detalles_albaranes)
    movimientos = tuple(movimientos)
    ajustes = tuple(ajustes)
    if tipo == TipoFacturaDocumental.TIPO_NO_DEMOSTRADO:
        factura = dinero(importe_factura)
        return ResultadoConciliacion(
            importe_factura=factura, importe_explicado=Decimal("0.0000"),
            diferencia=factura, tolerancia=dinero(tolerancia),
            resultado="PENDIENTE_REVISION_PIO", detalles=(),
        )
    if tipo == TipoFacturaDocumental.FACTURA_MERCANCIA:
        return conciliar_importes(importe_factura, detalles_albaranes, tolerancia=tolerancia)
    movimientos_resultado = conciliar_movimientos_documentales(
        importe_factura if tipo == TipoFacturaDocumental.FACTURA_GASTO_SERVICIO else 0,
        movimientos,
        ajustes=ajustes,
        tolerancia=tolerancia,
    )
    if movimientos_resultado.resultado == "PENDIENTE_REVISION_PIO":
        factura = dinero(importe_factura)
        return ResultadoConciliacion(
            importe_factura=factura, importe_explicado=Decimal("0.0000"),
            diferencia=factura, tolerancia=dinero(tolerancia),
            resultado="PENDIENTE_REVISION_PIO", detalles=(),
        )
    if tipo == TipoFacturaDocumental.FACTURA_GASTO_SERVICIO:
        return movimientos_resultado
    return conciliar_importes(
        importe_factura,
        (*detalles_albaranes, *movimientos_resultado.detalles),
        tolerancia=tolerancia,
    )


@dataclass(frozen=True, slots=True)
class ReglaTolerancia:
    """R11 (2AZ): tolerancia = max(suelo; min(por_albaran x n; tope)), n = albaranes casados."""

    suelo: Decimal = TOLERANCIA_POR_DEFECTO
    por_albaran: Decimal = Decimal("0.0100")
    tope: Decimal = Decimal("0.5000")

    def __post_init__(self) -> None:
        for nombre in ("suelo", "por_albaran", "tope"):
            object.__setattr__(self, nombre, dinero(getattr(self, nombre)))
        if not (Decimal(0) < self.suelo <= self.tope <= Decimal("1.0000")) or not (
                Decimal(0) <= self.por_albaran <= Decimal("0.0500")):
            raise ValueError("REGLA_TOLERANCIA_FUERA_DE_RANGO")

    def para(self, albaranes_casados: int) -> Decimal:
        if albaranes_casados < 0:
            raise ValueError("albaranes_casados no puede ser negativo")
        return max(self.suelo, min(self.por_albaran * albaranes_casados, self.tope)).quantize(CUATRO_DECIMALES)

    def como_dict(self, albaranes_casados: int) -> dict[str, str | int]:
        return {"suelo": str(self.suelo), "por_albaran": str(self.por_albaran), "tope": str(self.tope),
                "albaranes_casados": albaranes_casados, "tolerancia": str(self.para(albaranes_casados))}


def conciliar_importes(
    importe_factura: Decimal | int | float | str,
    detalles: Iterable[DetalleConciliacion],
    *,
    tolerancia: Decimal | int | float | str = TOLERANCIA_POR_DEFECTO,
    regla: ReglaTolerancia | None = None,
) -> ResultadoConciliacion:
    detalles_tuple = tuple(detalles)
    # R11: n = lineas casadas; una linea R17 (2BE, dos detalles UNO_A_VARIOS) cuenta como una.
    casados = sum(1 for d in detalles_tuple if d.tipo_relacion == TipoRelacionConciliacion.UNO_A_UNO) + len(
        {d.factura_albaran_extraido_id for d in detalles_tuple
         if d.tipo_relacion == TipoRelacionConciliacion.UNO_A_VARIOS})
    if regla is not None:
        tolerancia = regla.para(casados)
    tolerancia_decimal = dinero(tolerancia)
    if tolerancia_decimal < 0:
        raise ValueError("La tolerancia no puede ser negativa")
    factura = dinero(importe_factura)
    explicado = sum(
        (dinero(detalle.importe_aplicado) for detalle in detalles_tuple),
        Decimal("0.0000"),
    ).quantize(CUATRO_DECIMALES)
    diferencia = (factura - explicado).quantize(CUATRO_DECIMALES)
    resultado = (
        "CONCILIADA"
        if abs(diferencia) <= tolerancia_decimal
        else "DIFERENCIA"
    )
    return ResultadoConciliacion(
        importe_factura=factura,
        importe_explicado=explicado,
        diferencia=diferencia,
        tolerancia=tolerancia_decimal,
        resultado=resultado,
        detalles=detalles_tuple,
        albaranes_casados=casados,
        regla_tolerancia=regla.como_dict(casados) if regla is not None else None,
    )
