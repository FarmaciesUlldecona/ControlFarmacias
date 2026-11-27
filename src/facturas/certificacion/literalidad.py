"""Verificador de literalidad independiente del lector (FACTURAS-0, Paso 0a; DISENO §2).

Comprueba, para cada valor documentado de la salida normalizada (``{valor, literal, evidencia}``), que:

1. el literal aparece en el texto de la página citada, extraído con **pypdf** (motor distinto del ``pypdfium2`` de
   los lectores);
2. (0.2.0) el literal aparece **en su fila**: en el texto que pypdf sitúa dentro de la banda vertical del
   ``bbox_fila`` de la evidencia (coordenadas desde el borde superior, como las del lector), no solo en la página;
3. el valor sale de ese literal con un analizador declarado (importe es-ES, porcentaje, fecha, texto o
   identificador);
4. la página citada está dentro del rango de la factura.

Clases de resultado por valor:

- ``LITERAL``: cumple 1–3.
- ``DERIVADO``: lo produce una regla con nombre de la lista cerrada ``REGLAS_DERIVADAS`` (R14 y, desde 0.2.2, el
  cargo cooperativo H1 de HEFAME); el verificador recalcula el valor con la regla y exige que el literal de la
  evidencia aparezca en su fila de la página.
- ``DECISION_PIO``: evidencia con ``origen_autoridad = DECISION_FUNCIONAL_PIO`` y regla de la lista cerrada
  ``REGLAS_DECISION_PIO`` (vacía hoy: ningún valor documentado la usa).
- ``NO_LITERAL``: falla 1, 2 o 3, o la regla no está en ninguna lista.
- ``NO_EVALUABLE``: pypdf no da texto de la página (falla cerrado en la certificación).

No conecta a nada, no escribe nada, no importa los lectores y no lo usan la noche ni la persistencia (Paso 0a).
"""
from __future__ import annotations

import datetime
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable

VERSION = "0.2.2"
# 0.2.1 (Pio, 2026-11-27): posición heredada, tirada entera corta, borde de tirada, búsqueda con vuelta atrás.
# 0.2.2 (Pio, 2026-11-28): H1 (cargo cooperativo HEFAME de fin de mes) en la lista cerrada de reglas derivadas.

# Banda vertical de la fila (puntos PDF): la línea base de pypdf cae en el borde inferior del bbox del lector.
MARGEN_FILA_ARRIBA = 1.5
MARGEN_FILA_ABAJO = 3.0

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

TROZO_MINIMO = 4


def compuesto_en_tiradas(literal: str, tiradas: list[str]) -> bool:
    """El literal (normalizado) está entero en una tirada, o se compone de trozos consecutivos de al menos
    ``TROZO_MINIMO`` caracteres, cada uno dentro de una tirada del bloque y, si se repite tirada, siempre más a la derecha
    que el trozo anterior en esa tirada (literales de varias líneas y filas con etiquetas y valores intercalados)."""
    if not literal:
        return False
    if any(literal in t for t in tiradas):
        return True
    # Búsqueda en profundidad con memoria (0.2.1): una elección voraz se equivoca con filas de ceros repetidos
    # («1 0,00 0,0000 0,00»). Tope de pasos: si se agota, no se demuestra (falla cerrado).
    fallidos: set[tuple[int, tuple[int, ...]]] = set()
    pasos = [0]

    def candidatos(resto: str, cursor: tuple[int, ...], desde: int):
        salida = []
        for i, t in enumerate(tiradas):
            for k in range(len(resto), TROZO_MINIMO - 1, -1):
                p = t.find(resto[:k], cursor[i])
                if p >= 0:
                    salida.append((k, i, p))
                    break
            # Una tirada entera (p. ej. la etiqueta «IVA») cuenta como trozo aunque sea más corta que el mínimo.
            if cursor[i] == 0 and t and len(t) < TROZO_MINIMO and resto.startswith(t):
                salida.append((len(t), i, 0))
            # Trozo corto pegado al borde de una tirada, solo en los extremos del literal: al principio, el final de una
            # tirada; al final, el principio de una tirada (la fila del lector empieza o acaba a media frase de pypdf,
            # p. ej. «…ABONO A» | «COMPENSAR.»).
            for k in range(min(TROZO_MINIMO - 1, len(resto)), 0, -1):
                trozo = resto[:k]
                if desde == 0 and t.endswith(trozo) and len(t) - k >= cursor[i]:
                    salida.append((k, i, len(t) - k))
                if k == len(resto) and cursor[i] == 0 and t.startswith(trozo):
                    salida.append((k, i, 0))
        return sorted(set(salida), key=lambda c: -c[0])

    def buscar(desde: int, cursor: tuple[int, ...]) -> bool:
        if desde == len(literal):
            return True
        if (desde, cursor) in fallidos or pasos[0] > 20000:
            return False
        pasos[0] += 1
        for k, i, p in candidatos(literal[desde:], cursor, desde):
            nuevo = cursor[:i] + (p + k,) + cursor[i + 1:]
            if buscar(desde + k, nuevo):
                return True
        fallidos.add((desde, cursor))
        return False

    return buscar(0, tuple(0 for _ in tiradas))


# (x, y desde el borde superior, texto, vertical) de cada fragmento de pypdf; ``vertical`` = texto girado 90°.
Tirada = tuple[float, float, str, bool]


class TextoPdf:
    """Texto por página extraído con pypdf (1-indexado); ``None`` si la página no da texto.

    ``tiradas[i]`` son los fragmentos con posición de la página i+1 (``None`` si no hay posiciones fiables, p. ej.
    página girada): sin posiciones, la comprobación de fila es NO_EVALUABLE.
    """

    def __init__(self, paginas: list[str | None], tiradas: list[list[Tirada] | None] | None = None):
        self._paginas = paginas
        self._estricto = [normalizar_estricto(t) if t else None for t in paginas]
        self._tiradas = tiradas if tiradas is not None else [None] * len(paginas)

    @classmethod
    def desde_pdf(cls, origen: str | Path | bytes) -> "TextoPdf":
        import io

        from pypdf import PdfReader

        lector = PdfReader(io.BytesIO(origen) if isinstance(origen, bytes) else str(origen))
        paginas: list[str | None] = []
        tiradas: list[list[Tirada] | None] = []
        for pagina in lector.pages:
            propias: list[Tirada] = []
            alto = float(pagina.mediabox.top)
            ultima: list[Tirada] = []

            def visitar(texto, cm, tm, _fuente, _tamano, propias=propias, alto=alto, ultima=ultima):
                if not texto or not texto.strip():
                    return
                a, b, c, d, e, f = (float(v) for v in cm)
                x = float(tm[4]) * a + float(tm[5]) * c + e
                y = float(tm[4]) * b + float(tm[5]) * d + f
                dir_x = float(tm[0]) * a + float(tm[1]) * c
                dir_y = float(tm[0]) * b + float(tm[1]) * d
                tirada = (x, alto - y, texto, abs(dir_y) > abs(dir_x))
                if abs(float(tm[4])) < 0.01 and abs(float(tm[5])) < 0.01:  # matriz de texto sin desplazamiento
                    # pypdf no siempre da la posición de un fragmento que sigue a otro en el mismo objeto de texto (p. ej.
                    # el valor tras su etiqueta): puede ser la calculada (si la lleva la cm) o la del último fragmento
                    # posicionado. Se registran las dos; la heredada no pasa a ser la última.
                    propias.append(tirada)
                    if ultima:
                        x0, y0, _, vertical0 = ultima[-1]
                        propias.append((x0, y0, texto, vertical0))
                    return
                propias.append(tirada)
                ultima[:] = [tirada]

            try:
                texto = pagina.extract_text(visitor_text=visitar) or ""
            except Exception:  # noqa: BLE001 - una página ilegible queda NO_EVALUABLE, no se oculta
                texto, propias = "", []
            girada = int(pagina.get("/Rotate", 0) or 0) % 360 != 0
            paginas.append(texto if texto.strip() else None)
            tiradas.append(None if girada or not propias else propias)
        return cls(paginas, tiradas)

    def contiene_en_fila(self, pagina: int, literal: str, cajas: list) -> bool | None:
        """``True``/``False`` si el literal está en su fila o bloque; ``None`` si no se puede evaluar.

        ``cajas`` son el ``bbox_fila`` y el ``bbox`` de la evidencia (su unión es el bloque). Texto horizontal: la línea
        base de la tirada cae en la banda vertical del bloque. Texto vertical: la tirada cae en su franja horizontal.
        """
        en_bloque = self._en_bloque(pagina, cajas)
        if en_bloque is None:
            return None
        return compuesto_en_tiradas(normalizar_estricto(literal), [t for t, _ in en_bloque])

    def fila_en_su_posicion(self, pagina: int, fila: str, cajas: list) -> bool | None:
        """La fila entera que vio el lector está en el bloque. Las palabras que solo aparecen en texto vertical que
        cruza la banda (p. ej. el texto legal del margen) y en ninguna tirada horizontal no cuentan."""
        en_bloque = self._en_bloque(pagina, cajas)
        if en_bloque is None:
            return None
        palabras = [normalizar_estricto(p) for p in fila.split()]
        cajas_validas = [c for c in cajas if c and len(c) == 4]
        fila_vertical = any((float(c[3]) - float(c[1])) > (float(c[2]) - float(c[0])) for c in cajas_validas[:1])
        if not fila_vertical:
            horizontales = [t for t, vertical in en_bloque if not vertical]
            verticales = [t for t, vertical in en_bloque if vertical]
            palabras = [p for p in palabras if p and not (
                all(p not in h for h in horizontales) and any(p in v for v in verticales))]
        return compuesto_en_tiradas("".join(palabras), [t for t, _ in en_bloque])

    def _en_bloque(self, pagina: int, cajas: list) -> list[tuple[str, bool]] | None:
        if not (1 <= pagina <= len(self._tiradas)) or self._tiradas[pagina - 1] is None:
            return None
        cajas = [c for c in cajas if c and len(c) == 4]
        if not cajas:
            return None
        x0 = min(float(c[0]) for c in cajas) - MARGEN_FILA_ARRIBA
        x1 = max(float(c[2]) for c in cajas) + MARGEN_FILA_ABAJO
        y0 = min(float(c[1]) for c in cajas) - MARGEN_FILA_ARRIBA
        y1 = max(float(c[3]) for c in cajas) + MARGEN_FILA_ABAJO
        return [(normalizar_estricto(t[2]), t[3]) for t in self._tiradas[pagina - 1]
                if (x0 <= t[0] <= x1 if t[3] else y0 <= t[1] <= y1)]

    def lineas(self, pagina: int) -> list[str]:
        """Líneas del texto pypdf de la página (vacía si no tiene texto)."""
        if not self.tiene_texto(pagina):
            return []
        return (self._paginas[pagina - 1] or "").splitlines()

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

def _r14_importe_es_total(campo: dict, factura: dict, _contexto: dict | None = None) -> tuple[bool, str]:
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


# H1 (decisión de Pio, 2026-11-18; REGLAS_CRITICAS, fila HEFAME): el desfase de 80,00 de base S.R. entre el subtotal
# impreso «Desglose importes pedidos» de la página 1 y el detalle (albaranes + abonos por devolución + APROAFA) es el
# cargo cooperativo HEFAME, solo en la factura de fin de mes y una sola vez. El verificador no usa el cálculo del
# lector: lee él mismo la fila del subtotal con pypdf, suma el detalle (cuyos valores verifica uno a uno como
# literales) y recalcula la diferencia. La constante es la de la decisión de Pio, no la del lector.
H1_CARGO_BASE_S_R = Decimal("80.00")
H1_FILA_SUBTOTAL = "Desglose importes pedidos"
H1_CONCEPTO = "COMISION_HEFAME"
H1_DESCRIPCION = "CARGO_COOPERATIVO_HEFAME"
H1_MOVIMIENTOS_DEL_DETALLE = frozenset({"ABONO_DEVOLUCION", "APROAFA"})
H1_CATEGORIAS = ("BASE_S_R", "BASE_RE", "BASE_NO")
_RE_IMPORTE_EN_FILA = re.compile(r"(?<![\d,.])-?\d{1,3}(?:\.\d{3})*,\d{2}-?(?![\d,])")
_CENT = Decimal("0.01")
_CERO = Decimal("0.00")


def _valor_decimal(nodo: Any) -> Decimal | None:
    valor = nodo.get("valor") if isinstance(nodo, dict) else nodo
    if valor is None or isinstance(valor, bool):
        return None
    try:
        return Decimal(str(valor)).quantize(_CENT)
    except InvalidOperation:
        return None


def h1_subtotal_pedidos(texto: "TextoPdf", pagina: int = 1) -> list[Decimal] | None:
    """S.R., RE, No. y total de la única fila «Desglose importes pedidos» de la página, leída con pypdf; ``None`` si
    no hay exactamente una fila con cuatro importes y S.R. + RE + No. = total."""
    clave = normalizar_estricto(H1_FILA_SUBTOTAL)
    filas = [l for l in texto.lineas(pagina) if clave in normalizar_estricto(l)]
    if len(filas) != 1:
        return None
    importes = [importe_desde_literal(m) for m in _RE_IMPORTE_EN_FILA.findall(filas[0])]
    if len(importes) != 4 or any(i is None for i in importes):
        return None
    if importes[0] + importes[1] + importes[2] != importes[3]:
        return None
    return importes


def _h1_fecha(factura: dict) -> datetime.date | None:
    nodo = factura.get("fecha_factura") or (factura.get("cabecera") or {}).get("fecha_factura") or {}
    valor = nodo.get("valor") if isinstance(nodo, dict) else None
    iso = valor.get("iso") if isinstance(valor, dict) else valor
    try:
        return datetime.date.fromisoformat(str(iso))
    except ValueError:
        return None


def _h1_base_de(item: dict, categoria: str) -> Decimal | None:
    for nodo in (item.get(categoria), (item.get("bases") or {}).get(categoria),
                 (item.get("bases_por_categoria") or {}).get(categoria)):
        if nodo is not None:
            return _valor_decimal(nodo)
    return None


def _h1_cargo_cooperativo(campo: dict, factura: dict, contexto: dict | None = None) -> tuple[bool, str]:
    """H1: recalcula el cargo cooperativo desde la página 1 (pypdf) y comprueba el campo del movimiento del cargo."""
    contexto = contexto or {}
    texto, ruta = contexto.get("texto"), str(contexto.get("ruta") or "")
    if texto is None:
        return False, "H1_SIN_TEXTO"
    if contexto.get("pagina") != 1:
        return False, "H1_EVIDENCIA_FUERA_DE_LA_PAGINA_1"
    subtotal = h1_subtotal_pedidos(texto, 1)
    if subtotal is None:
        return False, "H1_SIN_SUBTOTAL_PEDIDOS_EN_LA_PAGINA_1"
    if importe_desde_literal(str(contexto.get("literal_evidencia") or "")) != subtotal[0]:
        return False, "H1_EVIDENCIA_NO_ES_EL_SUBTOTAL_S_R"
    fecha = _h1_fecha(factura)
    if fecha is None:
        return False, "H1_SIN_FECHA_DE_FACTURA"
    if (fecha + datetime.timedelta(days=1)).day != 1:
        return False, "H1_FUERA_DEL_FIN_DE_MES"
    movimientos = [m for m in factura.get("movimientos") or [] if isinstance(m, dict)]
    cargos = [i for i, m in enumerate(movimientos) if m.get("concepto_normalizado") == H1_CONCEPTO]
    if len(cargos) != 1:
        return False, "H1_CARGO_NO_UNICO"
    prefijo = f"/movimientos[{cargos[0]}]/"
    if not ruta.startswith(prefijo):
        return False, "H1_CAMPO_FUERA_DEL_CARGO"
    items = [a for a in factura.get("albaranes") or [] if isinstance(a, dict)]
    items += [m for m in movimientos if m.get("concepto_normalizado") in H1_MOVIMIENTOS_DEL_DETALLE]
    detalle = []
    for categoria in H1_CATEGORIAS:
        suma = _CERO
        for item in items:
            base = _h1_base_de(item, categoria)
            if base is None:
                return False, "H1_DETALLE_INCOMPLETO"
            suma += base
        detalle.append(suma)
    diferencias = [subtotal[i] - detalle[i] for i in range(3)]
    if diferencias != [H1_CARGO_BASE_S_R, _CERO, _CERO]:
        return False, "H1_DESFASE_NO_AUTORIZADO"
    campo_rel = ruta[len(prefijo):]
    if campo_rel == "descripcion_literal":
        ok = campo.get("valor") == H1_DESCRIPCION
    elif campo_rel in ("bases/BASE_S_R", "bases/TOTAL_BASES", "importe"):
        ok = _valor_decimal(campo) == H1_CARGO_BASE_S_R
    elif campo_rel in ("bases/BASE_RE", "bases/BASE_NO"):
        ok = _valor_decimal(campo) == _CERO
    else:
        return False, "H1_CAMPO_NO_PREVISTO"
    return ok, ("H1_IGUAL_AL_RECALCULADO" if ok else "H1_DISTINTO_DEL_RECALCULADO")


REGLAS_DERIVADAS: dict[str, Callable[[dict, dict, dict | None], tuple[bool, str]]] = {
    "R14_TOTAL_MISMA_HOJA_VENCIMIENTO_UNICO": _r14_importe_es_total,
    # H1: nombre con el que hefame-local 1.3.0 marca la evidencia del cargo (el subtotal S.R. impreso).
    "DIFERENCIA_ENTRE_SUBTOTAL_PEDIDOS_Y_DETALLE": _h1_cargo_cooperativo,
}
# Reglas cuyo campo no copia el literal de la evidencia (la evidencia es el subtotal impreso del que se recalcula): la
# regla comprueba ella misma que ese literal es el subtotal de su fila.
REGLAS_CON_LITERAL_DE_CALCULO = frozenset({"DIFERENCIA_ENTRE_SUBTOTAL_PEDIDOS_Y_DETALLE"})


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
    regla_final, pagina_final, literal_final = None, None, None
    for evidencia in evidencias:
        ubicacion = evidencia.get("ubicacion") or {}
        regla = ubicacion.get("regla")
        pagina = evidencia.get("pagina", ubicacion.get("pagina"))
        regla_final, pagina_final = regla, pagina
        literal_ev = evidencia.get("literal") or literal
        literal_final = literal_ev
        if not isinstance(pagina, int):
            return ResultadoValor(ruta, NO_LITERAL, "EVIDENCIA_SIN_PAGINA", regla, None)
        if isinstance(inicio, int) and isinstance(fin, int) and not inicio <= pagina <= fin:
            return ResultadoValor(ruta, NO_LITERAL, "PAGINA_FUERA_DE_LA_FACTURA", regla, pagina)
        if not texto.tiene_texto(pagina):
            return ResultadoValor(ruta, NO_EVALUABLE, "PAGINA_SIN_TEXTO_PYPDF", regla, pagina)
        if not texto.contiene(pagina, literal_ev):
            return ResultadoValor(ruta, NO_LITERAL, "LITERAL_AUSENTE_EN_LA_PAGINA", regla, pagina)
        cajas = [ubicacion.get("bbox_fila"), ubicacion.get("bbox")]
        en_fila = texto.contiene_en_fila(pagina, literal_ev, cajas)
        if en_fila is None:
            motivo = "EVIDENCIA_SIN_FILA" if not any(cajas) else "FILA_NO_EVALUABLE"
            clase = NO_LITERAL if motivo == "EVIDENCIA_SIN_FILA" else NO_EVALUABLE
            return ResultadoValor(ruta, clase, motivo, regla, pagina)
        if not en_fila:
            return ResultadoValor(ruta, NO_LITERAL, "LITERAL_AUSENTE_EN_SU_FILA", regla, pagina)
        fila_lector = (ubicacion.get("fila_literal") or "").replace("|", " ")
        if fila_lector.strip() and not texto.fila_en_su_posicion(pagina, fila_lector, cajas):
            return ResultadoValor(ruta, NO_LITERAL, "FILA_DEL_LECTOR_AUSENTE_EN_SU_POSICION", regla, pagina)
        de_calculo = regla in REGLAS_CON_LITERAL_DE_CALCULO
        if normalizar_estricto(literal_ev) != normalizar_estricto(literal) and not de_calculo:
            return ResultadoValor(ruta, NO_LITERAL, "LITERAL_DE_EVIDENCIA_DISTINTO", regla, pagina)
    if ubicacion.get("origen_autoridad") == ORIGEN_DECISION_PIO:
        if regla in REGLAS_DECISION_PIO:
            return ResultadoValor(ruta, DECISION_PIO, "DECISION_FUNCIONAL_PIO", regla, pagina_final)
        return ResultadoValor(ruta, NO_LITERAL, "DECISION_PIO_NO_RECONOCIDA", regla, pagina_final)
    if regla_final in REGLAS_DERIVADAS:
        contexto = {"ruta": ruta, "texto": texto, "pagina": pagina_final, "literal_evidencia": literal_final}
        ok, motivo = REGLAS_DERIVADAS[regla_final](campo, factura, contexto)
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
