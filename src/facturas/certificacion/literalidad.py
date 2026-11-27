"""Verificador de literalidad independiente del lector (FACTURAS-0, Paso 0a; DISENO §2).

Comprueba, para cada valor documentado de la salida normalizada (``{valor, literal, evidencia}``), que:

1. el literal aparece en el texto de la página citada, extraído con **pypdf** (motor distinto del ``pypdfium2`` de
   los lectores);
2. el valor sale de ese literal con un analizador declarado (importe es-ES, porcentaje, fecha, texto o
   identificador);
3. la página citada está dentro del rango de la factura.

Clases de resultado por valor:

- ``LITERAL``: cumple 1–3.
- ``DERIVADO``: lo produce una regla con nombre de la lista cerrada ``REGLAS_DERIVADAS`` (p. ej. R14); el verificador
  recalcula el valor con la regla y exige que su literal aparezca en la página.
- ``DECISION_PIO``: evidencia con ``origen_autoridad = DECISION_FUNCIONAL_PIO`` y regla de la lista cerrada
  ``REGLAS_DECISION_PIO`` (vacía hoy: ningún valor documentado la usa).
- ``NO_LITERAL``: falla 1, 2 o 3, o la regla no está en ninguna lista.
- ``NO_EVALUABLE``: pypdf no da texto de la página (falla cerrado en la certificación).

No conecta a nada, no escribe nada, no importa los lectores y no lo usan la noche ni la persistencia (Paso 0a).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable

VERSION = "0.1.0"

LITERAL = "LITERAL"
DERIVADO = "DERIVADO"
DECISION_PIO = "DECISION_PIO"
NO_LITERAL = "NO_LITERAL"
NO_EVALUABLE = "NO_EVALUABLE"
CLASES_ACEPTADAS = frozenset({LITERAL, DERIVADO, DECISION_PIO})

ORIGEN_DECISION_PIO = "DECISION_FUNCIONAL_PIO"
REGLAS_DECISION_PIO: frozenset[str] = frozenset()

_RE_IMPORTE_LITERAL = re.compile(r"^[+-]?\d{1,3}(?:\.\d{3})*(?:,\d+)?-?$|^[+-]?\d+(?:,\d+)?-?$")
_RE_DECIMAL_VALOR = re.compile(r"^-?\d+(?:\.\d+)?$")
_RE_FECHA = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})$")


# ---------------------------------------------------------------------------------------------------------------
# Normalización y analizadores (sin dependencia de los lectores)
# ---------------------------------------------------------------------------------------------------------------

def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar_estricto(texto: str) -> str:
    """Mayúsculas, sin acentos y sin espacios: conserva dígitos, letras y puntuación."""
    return re.sub(r"\s+", "", _sin_acentos(texto).upper())


def normalizar_alfanumerico(texto: str) -> str:
    """Solo letras y dígitos, en mayúsculas y sin acentos (comparación de textos libres)."""
    return re.sub(r"[^A-Z0-9]", "", _sin_acentos(texto).upper())


def importe_desde_literal(literal: str) -> Decimal | None:
    """``1.234,56`` / ``30,39-`` / ``-1,48`` / ``10`` → Decimal; ``None`` si no es un importe es-ES."""
    texto = literal.strip().replace(" ", "")
    if not _RE_IMPORTE_LITERAL.match(texto):
        return None
    negativo = texto.startswith("-") or texto.endswith("-")
    texto = texto.strip("+-").replace(".", "").replace(",", ".")
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        return None
    return -valor if negativo else valor


def fecha_desde_literal(literal: str) -> str | None:
    """``dd-mm-aaaa`` / ``dd/mm/aa`` / ``dd.mm.aaaa`` → ISO; ``None`` si no es una fecha válida."""
    m = _RE_FECHA.match(literal.strip())
    if not m:
        return None
    dia, mes, anio = int(m.group(1)), int(m.group(2)), m.group(3)
    anio_n = int(anio) + (2000 if len(anio) == 2 else 0)
    if not (1 <= mes <= 12 and 1 <= dia <= 31):
        return None
    return f"{anio_n:04d}-{mes:02d}-{dia:02d}"


def valor_sale_del_literal(valor: Any, literal: str) -> tuple[bool, str]:
    """Reconstruye el valor desde el literal con el analizador que corresponde al tipo del valor."""
    if isinstance(valor, dict) and "iso" in valor:
        iso = fecha_desde_literal(str(valor.get("literal") or literal))
        if iso is None:
            return False, "FECHA_NO_ANALIZABLE"
        if normalizar_estricto(str(valor.get("literal") or "")) not in normalizar_estricto(literal):
            return False, "LITERAL_DE_FECHA_DISTINTO"
        return (iso == valor["iso"], "FECHA" if iso == valor["iso"] else "FECHA_DISTINTA")
    if isinstance(valor, bool) or valor is None:
        return False, "TIPO_DE_VALOR_NO_DOCUMENTABLE"
    texto_valor = str(valor)
    if isinstance(valor, (int, float, Decimal)) or _RE_DECIMAL_VALOR.match(texto_valor):
        numero = importe_desde_literal(literal)
        if numero is not None:
            try:
                igual = Decimal(texto_valor) == numero
            except InvalidOperation:
                return False, "VALOR_NUMERICO_INVALIDO"
            return (igual, "IMPORTE" if igual else "IMPORTE_DISTINTO")
    a, b = normalizar_alfanumerico(texto_valor), normalizar_alfanumerico(literal)
    if not a:
        return False, "VALOR_VACIO"
    return (a in b, "TEXTO" if a in b else "TEXTO_DISTINTO")


# ---------------------------------------------------------------------------------------------------------------
# Texto del PDF con pypdf
# ---------------------------------------------------------------------------------------------------------------

class TextoPdf:
    """Texto por página extraído con pypdf (1-indexado); ``None`` si la página no da texto."""

    def __init__(self, paginas: list[str | None]):
        self._paginas = paginas
        self._estricto = [normalizar_estricto(t) if t else None for t in paginas]

    @classmethod
    def desde_pdf(cls, origen: str | Path | bytes) -> "TextoPdf":
        import io

        from pypdf import PdfReader

        lector = PdfReader(io.BytesIO(origen) if isinstance(origen, bytes) else str(origen))
        paginas: list[str | None] = []
        for pagina in lector.pages:
            try:
                texto = pagina.extract_text() or ""
            except Exception:  # noqa: BLE001 - una página ilegible queda NO_EVALUABLE, no se oculta
                texto = ""
            paginas.append(texto if texto.strip() else None)
        return cls(paginas)

    @property
    def numero_paginas(self) -> int:
        return len(self._paginas)

    def tiene_texto(self, pagina: int) -> bool:
        return 1 <= pagina <= len(self._paginas) and self._paginas[pagina - 1] is not None

    def contiene(self, pagina: int, literal: str) -> bool:
        if not self.tiene_texto(pagina):
            return False
        return normalizar_estricto(literal) in self._estricto[pagina - 1]


# ---------------------------------------------------------------------------------------------------------------
# Reglas derivadas (lista cerrada)
# ---------------------------------------------------------------------------------------------------------------

def _r14_importe_es_total(campo: dict, factura: dict) -> tuple[bool, str]:
    """R14 (REGLAS_CRITICAS): con una sola fecha de vencimiento, su importe es el TOTAL FACTURA de la misma hoja."""
    total = ((factura.get("totales") or {}).get("total") or {})
    vencimientos = factura.get("vencimientos") or []
    if len(vencimientos) != 1:
        return False, "R14_SIN_VENCIMIENTO_UNICO"
    if total.get("valor") is None or campo.get("valor") is None:
        return False, "R14_SIN_TOTAL"
    try:
        igual = Decimal(str(campo["valor"])) == Decimal(str(total["valor"]))
    except InvalidOperation:
        return False, "R14_VALOR_INVALIDO"
    return (igual, "R14_IGUAL_AL_TOTAL" if igual else "R14_DISTINTO_DEL_TOTAL")


REGLAS_DERIVADAS: dict[str, Callable[[dict, dict], tuple[bool, str]]] = {
    "R14_TOTAL_MISMA_HOJA_VENCIMIENTO_UNICO": _r14_importe_es_total,
}


# ---------------------------------------------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ResultadoValor:
    ruta: str
    clase: str
    motivo: str
    regla: str | None
    pagina: int | None


@dataclass
class InformeFactura:
    factura: str | None
    resultados: list[ResultadoValor] = field(default_factory=list)

    def recuento(self) -> dict[str, int]:
        salida = {c: 0 for c in (LITERAL, DERIVADO, DECISION_PIO, NO_LITERAL, NO_EVALUABLE)}
        for r in self.resultados:
            salida[r.clase] += 1
        return salida

    @property
    def fallos(self) -> list[ResultadoValor]:
        return [r for r in self.resultados if r.clase not in CLASES_ACEPTADAS]

    @property
    def estado(self) -> str:
        """``LITERALIDAD_OK`` / ``LITERALIDAD_FALLO`` / ``NO_EVALUABLE`` (este último cuenta como fallo)."""
        if any(r.clase == NO_LITERAL for r in self.resultados):
            return "LITERALIDAD_FALLO"
        if any(r.clase == NO_EVALUABLE for r in self.resultados) or not self.resultados:
            return NO_EVALUABLE
        return "LITERALIDAD_OK"


# ---------------------------------------------------------------------------------------------------------------
# Verificación
# ---------------------------------------------------------------------------------------------------------------

def _es_valor_documentado(nodo: Any) -> bool:
    return isinstance(nodo, dict) and "valor" in nodo and "literal" in nodo and "evidencia" in nodo


def valores_documentados(factura: dict) -> Iterable[tuple[str, dict]]:
    """Recorre la factura normalizada y devuelve (ruta, valor documentado). No entra en ``extraccion_local``."""

    def recorrer(nodo: Any, ruta: str):
        if _es_valor_documentado(nodo):
            yield ruta, nodo
            return
        if isinstance(nodo, dict):
            for clave, hijo in nodo.items():
                if clave == "extraccion_local":
                    continue
                yield from recorrer(hijo, f"{ruta}/{clave}")
        elif isinstance(nodo, list):
            for i, hijo in enumerate(nodo):
                yield from recorrer(hijo, f"{ruta}[{i}]")

    yield from recorrer(factura, "")


def _verificar_valor(ruta: str, campo: dict, factura: dict, texto: TextoPdf) -> ResultadoValor:
    evidencias = campo.get("evidencia") or []
    literal = campo.get("literal")
    if not evidencias or not isinstance(literal, str) or not literal.strip():
        return ResultadoValor(ruta, NO_LITERAL, "SIN_EVIDENCIA_O_LITERAL", None, None)
    inicio, fin = factura.get("pagina_inicio"), factura.get("pagina_fin")
    regla_final, pagina_final = None, None
    for evidencia in evidencias:
        ubicacion = evidencia.get("ubicacion") or {}
        regla = ubicacion.get("regla")
        pagina = evidencia.get("pagina", ubicacion.get("pagina"))
        regla_final, pagina_final = regla, pagina
        literal_ev = evidencia.get("literal") or literal
        if not isinstance(pagina, int):
            return ResultadoValor(ruta, NO_LITERAL, "EVIDENCIA_SIN_PAGINA", regla, None)
        if isinstance(inicio, int) and isinstance(fin, int) and not inicio <= pagina <= fin:
            return ResultadoValor(ruta, NO_LITERAL, "PAGINA_FUERA_DE_LA_FACTURA", regla, pagina)
        if not texto.tiene_texto(pagina):
            return ResultadoValor(ruta, NO_EVALUABLE, "PAGINA_SIN_TEXTO_PYPDF", regla, pagina)
        if not texto.contiene(pagina, literal_ev):
            return ResultadoValor(ruta, NO_LITERAL, "LITERAL_AUSENTE_EN_LA_PAGINA", regla, pagina)
        if normalizar_estricto(literal_ev) != normalizar_estricto(literal):
            return ResultadoValor(ruta, NO_LITERAL, "LITERAL_DE_EVIDENCIA_DISTINTO", regla, pagina)
    if ubicacion.get("origen_autoridad") == ORIGEN_DECISION_PIO:
        if regla in REGLAS_DECISION_PIO:
            return ResultadoValor(ruta, DECISION_PIO, "DECISION_FUNCIONAL_PIO", regla, pagina_final)
        return ResultadoValor(ruta, NO_LITERAL, "DECISION_PIO_NO_RECONOCIDA", regla, pagina_final)
    if regla_final in REGLAS_DERIVADAS:
        ok, motivo = REGLAS_DERIVADAS[regla_final](campo, factura)
        return ResultadoValor(ruta, DERIVADO if ok else NO_LITERAL, motivo, regla_final, pagina_final)
    ok, motivo = valor_sale_del_literal(campo.get("valor"), literal)
    return ResultadoValor(ruta, LITERAL if ok else NO_LITERAL, motivo, regla_final, pagina_final)


def verificar_factura(factura: dict, texto: TextoPdf) -> InformeFactura:
    numero = ((factura.get("numero_factura") or {}).get("valor"))
    informe = InformeFactura(numero)
    for ruta, campo in valores_documentados(factura):
        informe.resultados.append(_verificar_valor(ruta, campo, factura, texto))
    return informe


def verificar_documento(normalizado: dict, texto: TextoPdf) -> list[InformeFactura]:
    """Verifica todas las facturas de un documento normalizado (``{"facturas": [...]}``)."""
    return [verificar_factura(f, texto) for f in normalizado.get("facturas") or []]
