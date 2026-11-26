from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations
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
    # R19 (Pio, 2BG): la plataforma ECO360 de Farmatic es siempre compra a Alliance/SAFA.
    "6PLATAFECO360AH",
})
# R19 (Pio, 2BG): id de Farmatic de ECO360 (154) -> id de SAFA (2), solo para elegir candidatos por proveedor.
# R17 sigue exigiendo el mismo id con R9 (la BD lo revalida en ``cf_linea_r17_valida``).
_ID_PROVEEDOR_GRUPO_ALLIANCE = {"154": "2"}
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
    # R22 (D6, Pio 2026-11-24): concepto/laboratorio literal de la linea (``facturas_albaranes_extraidos.descripcion``).
    concepto_literal: str | None = None


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
    # R20 (migracion 36, estado MATCH_R20): variante con letra final del mismo numero, misma recepcion.
    complementario: CandidatoAlbaranSupabase | None = None
    importe_complementario: Decimal | None = None
    # R21 (migracion 39, estado MATCH_R21): los 1 a 3 complementarios de la linea (el primero, tambien en
    # ``complementario``). Vacio en R17 y R20.
    complementarios: tuple[CandidatoAlbaranSupabase, ...] = ()
    # R21-D4: motivo de una linea que queda sin casar (``DEMASIADOS_CANDIDATOS``); va a la provenance.
    motivo: str | None = None


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


def _id_proveedor_grupo(valor: str | None) -> str | None:
    """R9 y R19: id comparable, con ECO360 (154) dentro del grupo SAFA (2)."""
    comparable = _id_proveedor_comparable(valor)
    return _ID_PROVEEDOR_GRUPO_ALLIANCE.get(comparable, comparable)


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
        provider_comparable = _id_proveedor_grupo(provider_id)
        return provider_key, [
            row for row in rows
            if provider_comparable is not None
            and _id_proveedor_grupo(row.id_proveedor) == provider_comparable
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
    r20_habilitada: bool = False,
    r21_habilitada: bool = False,
) -> tuple[ResultadoBusquedaAlbaran, ...]:
    """R15 (2BA) para todas las lineas de una factura; resultados en el orden documental.

    Un albaran solo justifica una linea: lo elegido por una linea queda ocupado para las
    demas. Primero se buscan las lineas con algun candidato con coincidencia de numero,
    para que una linea por importe no se lleve el albaran que otra tiene por numero.
    Despues, R17 (2BE) para las lineas que quedan ``SIN_COINCIDENCIA``: ``_parejas_r17``; R20 (migracion 36,
    solo con ``r20_habilitada``, que el repositorio activa si detecta la 36 en la BD): ``_parejas_r20``; y R21
    (migracion 39, solo con ``r21_habilitada``): ``_combinaciones_r21``.
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
                         n for n in (normalizar_numero_albaran(x) for x in numeros) if n),
                     r20_habilitada=r20_habilitada, r21_habilitada=r21_habilitada)
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


def _parejas_r20(
    documental: AlbaranDocumentalTrabajo,
    libres: list[CandidatoAlbaranSupabase],
    *,
    alliance: bool,
    tolerancia: Decimal,
    ventana_dias: int,
    numeros_otras_facturas: frozenset[str],
) -> list[tuple[CandidatoAlbaranSupabase, CandidatoAlbaranSupabase]]:
    """R20 (DECISION DE PIO, 2026-11-19; migracion 36): parejas (A, B) que suman la linea documental.

    A = el albaran de su numero EXACTO y B = su variante con LETRA_FINAL (solo Alliance), los dos a
    +-ventana_dias de la linea, de la MISMA recepcion, mismo proveedor (R9), libres (R15) y B no es el
    numero de otra factura. PUC(A) + PUC(B) dentro de la tolerancia por linea. Solo cargos y solo 1+1.
    """
    if documental.fecha is None or documental.importe is None or documental.sentido != "CARGO":
        return []
    esperado = dinero(documental.importe)
    cerca = [row for row in libres if row.importe_puc is not None and row.id_recepcion is not None
             and abs((row.fecha - documental.fecha).days) <= ventana_dias]
    clases = {row.id_contador: clasificar_numero_albaran(documental.numero, row.numero_albaran, alliance=alliance)
              for row in cerca}
    exactos = [row for row in cerca if clases[row.id_contador] == "EXACTA"]
    variantes = [row for row in cerca if clases[row.id_contador] == "LETRA_FINAL"]
    parejas = []
    for a in exactos:
        for b in variantes:
            if (b.id_recepcion != a.id_recepcion
                    or _id_proveedor_comparable(b.id_proveedor) != _id_proveedor_comparable(a.id_proveedor)
                    or normalizar_numero_albaran(b.numero_albaran) in numeros_otras_facturas):
                continue
            if abs(dinero(a.importe_puc) + dinero(b.importe_puc) - esperado) <= tolerancia:
                parejas.append((a, b))
    return parejas


# R21 (migracion 39): como mucho 3 complementarios por linea y, para enumerar, como mucho 12 candidatos por A (R21-D4).
R21_MAX_COMPLEMENTARIOS = 3
R21_TOPE_CANDIDATOS = 12


def _complementario_r21(
    documental: AlbaranDocumentalTrabajo,
    a: CandidatoAlbaranSupabase,
    b: CandidatoAlbaranSupabase,
    *,
    alliance: bool,
    numeros_otras_facturas: frozenset[str],
) -> bool:
    """R21: B puede completar la linea de A (DECISIONES DE PIO 2026-11-24; R21-D1 revisada el 2026-11-25; D3).

    Interno de Farmatic o la variante con letra final del numero de la linea (solo Alliance); PUC > 0; misma farmacia y
    mismo proveedor que A (R9); la misma recepcion no nula que A, o SIN recepcion y la misma fecha que A (un albaran de
    otra recepcion es otra entrega, aunque sea del mismo dia); su numero no es el de una linea de otra factura (R15).
    Libre ya viene dado (``libres``)."""
    if (_clave_albaran(b) == _clave_albaran(a) or b.farmacia != a.farmacia or b.importe_puc is None
            or dinero(b.importe_puc) <= 0
            or _id_proveedor_comparable(b.id_proveedor) != _id_proveedor_comparable(a.id_proveedor)
            or normalizar_numero_albaran(b.numero_albaran) in numeros_otras_facturas):
        return False
    interno = bool(_NUMERO_INTERNO_FARMATIC.match(b.numero_albaran.strip().upper()))
    variante = alliance and clasificar_numero_albaran(documental.numero, b.numero_albaran,
                                                      alliance=True) == "LETRA_FINAL"
    if not (interno or variante):
        return False
    return (a.id_recepcion is not None and b.id_recepcion == a.id_recepcion) or (
        b.id_recepcion is None and b.fecha == a.fecha)


def _combinaciones_r21(
    documental: AlbaranDocumentalTrabajo,
    libres: list[CandidatoAlbaranSupabase],
    *,
    alliance: bool,
    tolerancia: Decimal,
    ventana_dias: int,
    numeros_otras_facturas: frozenset[str],
) -> tuple[list[tuple[CandidatoAlbaranSupabase, tuple[CandidatoAlbaranSupabase, ...]]], bool]:
    """R21 (DECISIONES DE PIO 2026-11-24; migracion 39): combinaciones A + 1..3 complementarios que suman la linea.

    A = el albaran del numero EXACTO de la linea (R21-D2), no interno, con PUC y proveedor, a +-ventana_dias de la linea
    (R21-D6). Complementarios: ``_complementario_r21``. |PUC(A) + suma de PUC - importe| dentro de la tolerancia por
    linea. Solo cargos. Devuelve tambien si algun A tenia mas de ``R21_TOPE_CANDIDATOS`` candidatos (R21-D4: esa A no
    se enumera y la linea queda sin casar)."""
    if documental.fecha is None or documental.importe is None or documental.sentido != "CARGO":
        return [], False
    esperado = dinero(documental.importe)
    combinaciones: list[tuple[CandidatoAlbaranSupabase, tuple[CandidatoAlbaranSupabase, ...]]] = []
    demasiados = False
    for a in libres:
        if (a.importe_puc is None or _id_proveedor_comparable(a.id_proveedor) is None
                or clasificar_numero_albaran(documental.numero, a.numero_albaran, alliance=alliance) != "EXACTA"
                or _NUMERO_INTERNO_FARMATIC.match(a.numero_albaran.strip().upper())
                or abs((a.fecha - documental.fecha).days) > ventana_dias):
            continue
        candidatos = [b for b in libres if _complementario_r21(documental, a, b, alliance=alliance,
                                                               numeros_otras_facturas=numeros_otras_facturas)]
        if len(candidatos) > R21_TOPE_CANDIDATOS:
            demasiados = True
            continue
        for k in range(1, R21_MAX_COMPLEMENTARIOS + 1):
            for bs in combinations(candidatos, k):
                suma = dinero(a.importe_puc) + sum((dinero(b.importe_puc) for b in bs), Decimal("0"))
                if abs(suma - esperado) <= tolerancia:
                    combinaciones.append((a, bs))
    return combinaciones, demasiados


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
    r20_habilitada: bool = False,
    r21_habilitada: bool = False,
) -> None:
    """R17, R20 (si ``r20_habilitada``) y R21 (si ``r21_habilitada``) despues del casado 1:1.

    Falla cerrado: mas de una combinacion para una linea (de las tres reglas, contadas juntas; cada conjunto de
    albaranes una sola vez y con la regla R17 o R20 si lo es), o un albaran en las combinaciones de dos lineas, deja
    esas lineas sin casar (sin depender del orden). R21 con mas de 12 candidatos para un A: ``AMBIGUO_R21`` con motivo
    ``DEMASIADOS_CANDIDATOS`` (R21-D4)."""
    libres = [row for row in by_provider if _clave_albaran(row) not in ocupados]
    comunes = {"alliance": alliance, "tolerancia": tolerancia, "ventana_dias": ventana_dias,
               "numeros_otras_facturas": numeros_otras_facturas}
    opciones_por_linea: dict[int, list[tuple[CandidatoAlbaranSupabase, tuple[CandidatoAlbaranSupabase, ...], str]]] = {}
    demasiados: set[int] = set()
    for i, resultado in enumerate(resultados):
        if resultado is None or resultado.estado != "SIN_COINCIDENCIA":
            continue
        por_conjunto: dict[frozenset[tuple[str, int]], tuple] = {}
        parejas = [(a, (b,), "R17") for a, b in _parejas_r17(docs[i], libres, **comunes)]
        if r20_habilitada:
            parejas += [(a, (b,), "R20") for a, b in _parejas_r20(docs[i], libres, **comunes)]
        if r21_habilitada:
            combinaciones, exceso = _combinaciones_r21(docs[i], libres, **comunes)
            parejas += [(a, bs, "R21") for a, bs in combinaciones]
            if exceso:
                demasiados.add(i)
        for a, bs, regla in parejas:
            # Un mismo conjunto de albaranes cuenta una vez; si es R17 o R20, conserva esa regla (va primero).
            por_conjunto.setdefault(frozenset(_clave_albaran(row) for row in (a, *bs)), (a, bs, regla))
        opciones_por_linea[i] = list(por_conjunto.values())
    uso: dict[tuple[str, int], int] = {}
    for opciones in opciones_por_linea.values():
        for clave in {_clave_albaran(row) for a, bs, _ in opciones for row in (a, *bs)}:
            uso[clave] = uso.get(clave, 0) + 1
    for i, opciones in opciones_por_linea.items():
        previo = resultados[i]
        assert previo is not None
        if i in demasiados:
            resultados[i] = replace(previo, estado="AMBIGUO_R21", candidatos_finales=len(opciones),
                                    motivo="DEMASIADOS_CANDIDATOS")
            continue
        if not opciones:
            continue
        if len(opciones) > 1:
            reglas = {r for _, _, r in opciones}
            regla = "R21" if "R21" in reglas else "R20" if "R20" in reglas else "R17"
            resultados[i] = replace(previo, estado=f"AMBIGUO_{regla}", candidatos_finales=len(opciones))
            continue
        a, bs, regla = opciones[0]
        if any(uso[_clave_albaran(row)] > 1 for row in (a, *bs)):
            resultados[i] = replace(previo, estado=f"CONFLICTO_{regla}")
            continue
        resultados[i] = ResultadoBusquedaAlbaran(
            f"MATCH_{regla}", a, dinero(a.importe_puc), comparar_numeros_albaran(docs[i].numero, a.numero_albaran),
            previo.candidatos_proveedor, previo.candidatos_fecha, previo.candidatos_importe, 1,
            clasificar_numero_albaran(docs[i].numero, a.numero_albaran, alliance=alliance),
            complementario=bs[0], importe_complementario=dinero(bs[0].importe_puc),
            complementarios=bs if regla == "R21" else ())


def detalles_desde_busqueda(
    documental: AlbaranDocumentalTrabajo,
    resultado: ResultadoBusquedaAlbaran,
) -> tuple[DetalleConciliacion, ...]:
    """Detalles de una linea: uno (1:1 o sin coincidencia), dos ``UNO_A_VARIOS`` (R17, 2BE; R20, migracion 36) o de
    dos a cuatro (R21, migracion 39).

    En R17, R20 y R21 cada albaran aplica su PUC; todos llevan el mismo origen documental.
    ``cf_persistir_conciliacion`` revalida la linea con ``cf_linea_r17_valida`` (24; R20 desde la 36; R21 desde la 39).
    """
    if resultado.complementario is None:
        return (detalle_desde_busqueda(documental, resultado),)
    if resultado.estado == "MATCH_R21":
        return _detalles_r21(documental, resultado)
    a, b = resultado.candidato, resultado.complementario
    if (resultado.estado not in ("MATCH_R17", "MATCH_R20") or a is None or resultado.importe_compatible is None
            or resultado.importe_complementario is None):
        raise ValueError("RESULTADO_R17_INCOMPLETO")
    regla = resultado.estado.removeprefix("MATCH_")
    comun = {
        "fuente": "ALBARANES_SUPABASE",
        "estado_matching": resultado.estado,
        "regla": regla,
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
            importe_documental=importe_documental_con_signo(documental),
            provenance={**comun, f"papel_{regla.lower()}": papel, "clase_numero": clase,
                        "numero_operacional": row.numero_albaran, "id_proveedor": row.id_proveedor,
                        "fecha_operacional": row.fecha.isoformat()},
        )

    segundo = "LETRA_FINAL" if regla == "R20" else "INTERNO"
    return (detalle(a, resultado.importe_compatible, "NUMERO", resultado.clase_numero),
            detalle(b, resultado.importe_complementario, segundo, segundo))


def _detalles_r21(
    documental: AlbaranDocumentalTrabajo,
    resultado: ResultadoBusquedaAlbaran,
) -> tuple[DetalleConciliacion, ...]:
    """R21 (migracion 39): A y sus 1 a 3 complementarios, cada uno con su PUC y su papel, su motivo y la combinacion."""
    a, bs = resultado.candidato, resultado.complementarios
    if (a is None or resultado.importe_compatible is None or not 1 <= len(bs) <= R21_MAX_COMPLEMENTARIOS
            or resultado.complementario is not bs[0] or any(b.importe_puc is None for b in bs)):
        raise ValueError("RESULTADO_R21_INCOMPLETO")
    suma = resultado.importe_compatible + sum((dinero(b.importe_puc) for b in bs), Decimal("0"))
    comun = {
        "fuente": "ALBARANES_SUPABASE",
        "estado_matching": resultado.estado,
        "regla": "R21",
        "id_recepcion": a.id_recepcion,
        "numero_documental": documental.numero,
        "fecha_documental": documental.fecha.isoformat() if documental.fecha else None,
        "importe_documental": str(documental.importe),
        "importe_combinacion": str(suma),
        "tolerancia_linea": str(TOLERANCIA_LINEA),
        "complementarios": len(bs),
        "combinaciones_evaluadas": 1,
        "sentido_documental": documental.sentido,
    }

    def detalle(row: CandidatoAlbaranSupabase, importe: Decimal, papel: str, clase: str | None,
                motivo: str | None) -> DetalleConciliacion:
        return DetalleConciliacion(
            tipo_relacion=TipoRelacionConciliacion.UNO_A_VARIOS,
            importe_aplicado=importe,
            albaran_farmacia=row.farmacia,
            albaran_id_contador=row.id_contador,
            factura_albaran_extraido_id=documental.id,
            coincidencia_numero_literal=papel == "NUMERO" and resultado.coincidencia_numero == "EXACTA",
            importe_documental=importe_documental_con_signo(documental),
            provenance={**comun, "papel_r21": papel, "clase_numero": clase, "motivo_r21": motivo,
                        "numero_operacional": row.numero_albaran, "id_proveedor": row.id_proveedor,
                        "id_recepcion_operacional": row.id_recepcion, "fecha_operacional": row.fecha.isoformat()},
        )

    detalles = [detalle(a, resultado.importe_compatible, "NUMERO", resultado.clase_numero, None)]
    for b in bs:
        papel = "INTERNO" if _NUMERO_INTERNO_FARMATIC.match(b.numero_albaran.strip().upper()) else "LETRA_FINAL"
        motivo = ("MISMA_RECEPCION" if a.id_recepcion is not None and b.id_recepcion == a.id_recepcion
                  else "MISMO_DIA_SIN_RECEPCION")
        detalles.append(detalle(b, dinero(b.importe_puc), papel, papel, motivo))
    return tuple(detalles)


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
            importe_documental=importe_documental_con_signo(documental),
            provenance={
                "fuente": "ALBARANES_SUPABASE",
                "estado_matching": resultado.estado,
                "candidatos_finales": resultado.candidatos_finales,
                "sentido_documental": documental.sentido,
                # R21-D4: solo si hay motivo (``DEMASIADOS_CANDIDATOS``); sin el, la provenance es la de antes.
                **({"motivo": resultado.motivo} if resultado.motivo else {}),
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
        importe_documental=importe_documental_con_signo(documental),
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


# 2BR (migracion 30): tolerancia por linea del detalle; la misma con la que casa una linea (0,05) y la de R17.
TOLERANCIA_LINEA = Decimal("0.0500")
_RELACIONES_ALBARAN = frozenset({
    TipoRelacionConciliacion.UNO_A_UNO,
    TipoRelacionConciliacion.UNO_A_VARIOS,
    TipoRelacionConciliacion.VARIOS_A_UNO,
})


def importe_documental_con_signo(documental: AlbaranDocumentalTrabajo) -> Decimal | None:
    """Importe de la linea del PDF con el signo de la factura: ABONO en negativo (como el importe aplicado)."""
    if documental.importe is None:
        return None
    importe = dinero(documental.importe)
    return -abs(importe) if documental.sentido == "ABONO" else importe


@dataclass(frozen=True, slots=True)
class ValoresLinea:
    """Detalle por linea (2BR): importe del PDF, importe de Farmatic, diferencia y estado de la linea."""

    importe_documental: Decimal | None
    importe_farmatic: Decimal | None
    diferencia: Decimal | None
    estado: str


def valores_por_linea(detalles: Iterable[DetalleConciliacion]) -> tuple[ValoresLinea, ...]:
    """Valores por linea de cada detalle, en el mismo orden. Espejo exacto de ``cf_detalles_por_linea`` (30).

    - Albaran casado (1:1 o R17): PDF = importe de la linea con signo; Farmatic = importe aplicado del albaran;
      diferencia = PDF - suma de los albaranes de esa linea (en R17, la misma en los dos detalles);
      COINCIDE si |diferencia| <= 0,05, si no DIFERENCIA.
    - Linea sin coincidencia: PDF = importe de la linea, Farmatic vacio, diferencia = PDF, DIFERENCIA.
    - Linea sin importe documental: NO_EVALUABLE, sin diferencia.
    - Movimiento o ajuste documental: PDF = importe aplicado; sin contraparte en Farmatic -> NO_EVALUABLE.
    No cambia el resultado de la factura (``conciliar_importes``).
    """
    detalles = tuple(detalles)
    suma_linea: dict[str, Decimal] = {}
    for d in detalles:
        if d.tipo_relacion in _RELACIONES_ALBARAN and d.factura_albaran_extraido_id is not None:
            suma_linea[d.factura_albaran_extraido_id] = (
                suma_linea.get(d.factura_albaran_extraido_id, Decimal("0.0000")) + dinero(d.importe_aplicado))
    valores = []
    for d in detalles:
        if d.tipo_relacion == TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC:
            valores.append(ValoresLinea(dinero(d.importe_aplicado), None, None, "NO_EVALUABLE"))
            continue
        documental = None
        if d.factura_albaran_extraido_id is not None and d.importe_documental is not None:
            documental = dinero(d.importe_documental)
        farmatic = None if d.tipo_relacion == TipoRelacionConciliacion.SIN_COINCIDENCIA else dinero(
            d.importe_aplicado)
        if documental is None:
            valores.append(ValoresLinea(None, farmatic, None, "NO_EVALUABLE"))
        elif d.tipo_relacion == TipoRelacionConciliacion.SIN_COINCIDENCIA:
            valores.append(ValoresLinea(documental, None, documental, "DIFERENCIA"))
        else:
            diferencia = (documental - suma_linea[d.factura_albaran_extraido_id]).quantize(CUATRO_DECIMALES)
            valores.append(ValoresLinea(documental, farmatic, diferencia,
                                        "COINCIDE" if abs(diferencia) <= TOLERANCIA_LINEA else "DIFERENCIA"))
    return tuple(valores)


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


def aplicar_r22(
    detalles: Iterable[DetalleConciliacion],
    documentales: Iterable[AlbaranDocumentalTrabajo],
    candidatos: Iterable[CandidatoAlbaranSupabase],
) -> tuple[DetalleConciliacion, ...]:
    """R22 (DECISION DE PIO, 2026-11-24; caso E, 08005257): cargo sin albaran anulado por su abono en el mismo documento.

    Una linea documental ``CARGO`` que sigue ``SIN_COINCIDENCIA`` tras el 1:1, R17, R20 y R21, con numero, y **sin ningun
    albaran** de ese numero en los candidatos leidos (cualquier proveedor; ``EXACTA``, ``LETRA_FINAL`` o
    ``FINAL_DOCUMENTAL``, con la lectura Alliance, la mas amplia) queda explicada por un movimiento ``ABONO`` del MISMO
    documento (la misma factura) del MISMO concepto/laboratorio (D6: el literal de la linea, ``descripcion``, igual al
    del movimiento, sin distinguir mayusculas ni espacios; los dos no vacios) y por importe exactamente opuesto (al
    centimo de cuatro decimales). Neto del par: 0.

    - La linea pasa a ``MOVIMIENTO_NO_FARMATIC`` con su importe (sin albaran ni reserva; la BD la trata como
      NO_EVALUABLE, ``30_cf_detalle_por_linea.sql:51-66``); el abono conserva su detalle. Los dos llevan
      ``regla: R22`` y la referencia del otro.
    - Falla cerrado: una linea con mas de un abono posible, o un abono con mas de una linea posible, deja todo igual.
    - No busca en Farmatic. Sin linea o sin abono, los detalles no cambian.
    """
    detalles = tuple(detalles)
    por_id = {d.id: d for d in documentales}
    candidatos = tuple(candidatos)

    def sin_albaran(documental: AlbaranDocumentalTrabajo) -> bool:
        return bool((documental.numero or "").strip()) and not any(
            clasificar_numero_albaran(documental.numero, row.numero_albaran, alliance=True) in COINCIDENCIAS_NUMERO
            for row in candidatos)

    def concepto(valor: Any) -> str:
        return " ".join(str(valor or "").split()).upper()

    lineas = {}
    for i, d in enumerate(detalles):
        doc = por_id.get(d.factura_albaran_extraido_id) if d.factura_albaran_extraido_id else None
        if (d.tipo_relacion == TipoRelacionConciliacion.SIN_COINCIDENCIA and doc is not None
                and doc.sentido == "CARGO" and doc.importe is not None and dinero(doc.importe) > 0
                and concepto(doc.concepto_literal) and sin_albaran(doc)):
            lineas[i] = (dinero(doc.importe), concepto(doc.concepto_literal))
    abonos = {
        i: (-dinero(d.importe_aplicado), concepto(d.provenance.get("concepto_literal")))
        for i, d in enumerate(detalles)
        if d.tipo_relacion == TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC and d.factura_movimiento_id
        and d.provenance.get("sentido") == "ABONO" and d.provenance.get("magnitud_usada") == "IMPORTE"
        and dinero(d.importe_aplicado) < 0 and concepto(d.provenance.get("concepto_literal"))
    }
    # Par = mismo (importe, concepto): importe exactamente opuesto y mismo concepto/laboratorio.
    opciones_linea = {i: [j for j, par in abonos.items() if par == clave] for i, clave in lineas.items()}
    opciones_abono = {j: [i for i, clave in lineas.items() if clave == par] for j, par in abonos.items()}
    nuevos = list(detalles)
    for i, opciones in opciones_linea.items():
        if len(opciones) != 1 or len(opciones_abono[opciones[0]]) != 1:
            continue
        j = opciones[0]
        linea, abono, doc = detalles[i], detalles[j], por_id[detalles[i].factura_albaran_extraido_id]
        importe, concepto_par = lineas[i]
        nuevos[i] = DetalleConciliacion(
            tipo_relacion=TipoRelacionConciliacion.MOVIMIENTO_NO_FARMATIC,
            importe_aplicado=importe,
            factura_albaran_extraido_id=linea.factura_albaran_extraido_id,
            importe_documental=linea.importe_documental,
            provenance={
                "fuente": "R22_CARGO_ANULADO_POR_ABONO",
                "regla": "R22",
                "estado_matching_previo": linea.provenance.get("estado_matching"),
                "numero_documental": doc.numero,
                "fecha_documental": doc.fecha.isoformat() if doc.fecha else None,
                "importe_documental": str(importe),
                "concepto_literal": doc.concepto_literal,
                "concepto_par": concepto_par,
                "factura_movimiento_id_par": abono.factura_movimiento_id,
                "neto_par": str(importe + dinero(abono.importe_aplicado)),
            },
        )
        nuevos[j] = replace(abono, provenance={
            **dict(abono.provenance), "regla": "R22",
            "factura_albaran_extraido_id_par": linea.factura_albaran_extraido_id})
    return tuple(nuevos)
