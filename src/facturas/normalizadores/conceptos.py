"""Clasificacion conservadora de conceptos antes del ensamblado mecanico."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from collections.abc import Mapping
import re
from typing import Any
import unicodedata

from src.facturas.normalizadores.comun import decimal_visible, valor_visible


class CategoriaConcepto(str, Enum):
    AJUSTE = "AJUSTE"
    COMPONENTE_BASE = "COMPONENTE_BASE"
    RESUMEN = "RESUMEN"
    IMPUESTO_ESPECIAL = "IMPUESTO_ESPECIAL"
    INCIERTO = "INCIERTO"


@dataclass(frozen=True, slots=True)
class EvidenciaConcepto:
    campo: str
    texto_visible: str
    pagina: int | None


@dataclass(frozen=True, slots=True)
class ClasificacionConcepto:
    categoria: CategoriaConcepto
    motivo: str
    evidencias: tuple[EvidenciaConcepto, ...]


_TIPOS_AJUSTE_EXPLICITOS = frozenset(
    {
        "bonificacion",
        "bonificacio",
        "descuento",
    }
)
_TERMINOS_AJUSTE_EXPLICITOS = frozenset(
    {
        "bonificacion",
        "bonificacio",
        "descuento",
        "dto",
        "dt",
    }
)
_MARCADORES_DUDA = frozenset(
    {
        "confirmar",
        "pendiente",
        "revisar",
        "revision",
    }
)
_PATRON_NUMERO = re.compile(r"[-+]?\s*\d+(?:[.,]\d+)?")


def _normalizar_texto(texto: str) -> str:
    sin_tildes = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )
    return " ".join(re.findall(r"[a-z0-9]+", sin_tildes.casefold()))


def _extraer_evidencias(fila: Mapping[str, Any]) -> tuple[EvidenciaConcepto, ...]:
    resultado: list[EvidenciaConcepto] = []
    for campo, contenido in fila.items():
        if not isinstance(contenido, Mapping):
            continue
        evidencias = contenido.get("evidencias")
        if not isinstance(evidencias, list):
            continue
        for evidencia in evidencias:
            if not isinstance(evidencia, Mapping):
                continue
            texto = evidencia.get("texto_visible")
            pagina = evidencia.get("pagina")
            if not isinstance(texto, str) or not texto.strip():
                continue
            resultado.append(
                EvidenciaConcepto(
                    campo=str(campo),
                    texto_visible=texto,
                    pagina=pagina if isinstance(pagina, int) else None,
                )
            )
    return tuple(resultado)


def _texto_declara_ajuste(texto: str) -> bool:
    tokens = frozenset(_normalizar_texto(texto).split())
    return bool(tokens & _TERMINOS_AJUSTE_EXPLICITOS) and not bool(
        tokens & _MARCADORES_DUDA
    )


def _texto_contiene_importe(texto: str, importe: Decimal) -> bool:
    for coincidencia in _PATRON_NUMERO.finditer(texto):
        candidato = coincidencia.group().replace(" ", "").replace(",", ".")
        try:
            if Decimal(candidato) == importe:
                return True
        except ArithmeticError:
            continue
    return False


def clasificar_concepto_factura(fila: Any) -> ClasificacionConcepto:
    """Certifica solo ajustes explicitos; ante cualquier duda devuelve INCIERTO."""
    if not isinstance(fila, Mapping) or not fila:
        return ClasificacionConcepto(
            categoria=CategoriaConcepto.INCIERTO,
            motivo="La fila no contiene una estructura documental clasificable.",
            evidencias=(),
        )

    evidencias = _extraer_evidencias(fila)
    try:
        tipo = valor_visible(fila.get("tipo_ajuste"))
        importe = decimal_visible(fila.get("importe"))
    except ValueError:
        return ClasificacionConcepto(
            categoria=CategoriaConcepto.INCIERTO,
            motivo="El tipo o el importe visible no es interpretable.",
            evidencias=evidencias,
        )

    tipo_normalizado = (
        _normalizar_texto(tipo) if isinstance(tipo, str) else None
    )
    if tipo_normalizado not in _TIPOS_AJUSTE_EXPLICITOS:
        return ClasificacionConcepto(
            categoria=CategoriaConcepto.INCIERTO,
            motivo="El tipo estructurado no demuestra un ajuste explicito.",
            evidencias=evidencias,
        )
    if importe is None:
        return ClasificacionConcepto(
            categoria=CategoriaConcepto.INCIERTO,
            motivo="No existe un importe visible asociado al concepto.",
            evidencias=evidencias,
        )

    evidencia_coherente = any(
        _texto_declara_ajuste(evidencia.texto_visible)
        and _texto_contiene_importe(evidencia.texto_visible, importe)
        for evidencia in evidencias
    )
    if not evidencia_coherente:
        return ClasificacionConcepto(
            categoria=CategoriaConcepto.INCIERTO,
            motivo=(
                "La evidencia no vincula de forma inequívoca la semantica del "
                "ajuste con su importe."
            ),
            evidencias=evidencias,
        )

    return ClasificacionConcepto(
        categoria=CategoriaConcepto.AJUSTE,
        motivo="Tipo, semantica e importe visibles demuestran un ajuste.",
        evidencias=evidencias,
    )
