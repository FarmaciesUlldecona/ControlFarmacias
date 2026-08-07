"""Primitivas comunes y deterministas para normalizar facturas.

Este modulo no conoce proveedores concretos ni fuentes externas. Sus funciones
solo interpretan valores recibidos explicitamente y nunca completan ausencias
por plausibilidad.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import re
from typing import Any, TypeVar
import unicodedata


T = TypeVar("T")


class NivelIncidencia(StrEnum):
    AVISO = "AVISO"
    REVISION_MANUAL = "REVISION_MANUAL"


class TipoProcedencia(StrEnum):
    LECTURA_VISIBLE = "lectura_visible"
    METADATO_TECNICO = "metadato_tecnico"
    CONFIGURACION_INTERNA = "configuracion_interna"
    REGLA_DETERMINISTA = "regla_determinista"


class EstadoValidacion(StrEnum):
    OK = "OK"
    ERROR = "ERROR"
    NO_EVALUABLE = "NO_EVALUABLE"


@dataclass(frozen=True, slots=True)
class Incidencia:
    orden: int
    campo: str
    tipo_incidencia: str
    nivel: NivelIncidencia
    descripcion: str
    datos_visibles_disponibles: Any
    decision_tomada: str

    @property
    def requiere_revision_manual(self) -> bool:
        return self.nivel is NivelIncidencia.REVISION_MANUAL

    def a_diccionario(self) -> dict[str, Any]:
        return {
            "orden": self.orden,
            "campo": self.campo,
            "tipo_incidencia": self.tipo_incidencia,
            "nivel": self.nivel.value,
            "descripcion": self.descripcion,
            "datos_visibles_disponibles": self.datos_visibles_disponibles,
            "decision_tomada": self.decision_tomada,
            "requiere_revision_manual": self.requiere_revision_manual,
        }


class RegistroIncidencias:
    """Acumula incidencias con un orden estable de insercion."""

    def __init__(self) -> None:
        self._incidencias: list[Incidencia] = []

    def agregar(
        self,
        *,
        campo: str,
        tipo: str,
        nivel: NivelIncidencia,
        descripcion: str,
        datos_visibles: Any,
        decision: str,
    ) -> Incidencia:
        incidencia = Incidencia(
            orden=len(self._incidencias) + 1,
            campo=campo,
            tipo_incidencia=tipo,
            nivel=nivel,
            descripcion=descripcion,
            datos_visibles_disponibles=datos_visibles,
            decision_tomada=decision,
        )
        self._incidencias.append(incidencia)
        return incidencia

    def como_lista(self) -> list[dict[str, Any]]:
        return [incidencia.a_diccionario() for incidencia in self._incidencias]


@dataclass(frozen=True, slots=True)
class Procedencia:
    tipo: TipoProcedencia
    fuente: str
    regla: str | None = None
    version_regla: str | None = None

    def __post_init__(self) -> None:
        es_regla = self.tipo is TipoProcedencia.REGLA_DETERMINISTA
        if es_regla and (not self.regla or not self.version_regla):
            raise ValueError("La procedencia determinista exige regla y version.")
        if not es_regla and (self.regla is not None or self.version_regla is not None):
            raise ValueError("Solo una regla determinista puede declarar regla y version.")

    def a_diccionario(self) -> dict[str, str]:
        resultado = {"tipo": self.tipo.value, "fuente": self.fuente}
        if self.regla is not None:
            resultado["regla"] = self.regla
        if self.version_regla is not None:
            resultado["version_regla"] = self.version_regla
        return resultado


@dataclass(frozen=True, slots=True)
class ResultadoRegla:
    valor: Any
    aplicada: bool
    procedencia: Procedencia | None
    bloqueos: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResultadoValidacionMonetaria:
    estado: EstadoValidacion
    esperado: Decimal | None
    obtenido: Decimal | None
    diferencia: Decimal | None
    tolerancia: Decimal

    def a_diccionario(self) -> dict[str, str | None]:
        return {
            "estado": self.estado.value,
            "esperado": str(self.esperado) if self.esperado is not None else None,
            "obtenido": str(self.obtenido) if self.obtenido is not None else None,
            "diferencia": str(self.diferencia) if self.diferencia is not None else None,
            "tolerancia": str(self.tolerancia),
        }


_IMPORTE_ES = re.compile(
    r"^(?P<signo_inicial>[+-])?"
    r"(?P<entero>(?:0|[1-9]\d*|[1-9]\d{0,2}(?:\.\d{3})+))"
    r"(?P<decimales>,\d{1,2})?"
    r"(?P<signo_final>[+-])?$"
)


def fecha_visible_a_iso(valor: str | date | None, *, permitir_iso: bool = True) -> str | None:
    """Interpreta una fecha demostrada, sin corregir formatos dudosos."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        raise ValueError("Una fecha visible no puede incluir hora.")
    if isinstance(valor, date):
        return valor.isoformat()
    if not isinstance(valor, str):
        raise ValueError(f"Fecha visible no valida: {valor!r}")
    texto = valor.strip()
    if not texto:
        return None
    formatos = ("%d-%m-%Y", "%Y-%m-%d") if permitir_iso else ("%d-%m-%Y",)
    for formato in formatos:
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Fecha visible no valida o en formato no autorizado: {valor!r}")


def importe_espanol_a_decimal(
    valor: str | int | float | Decimal | None,
) -> Decimal | None:
    """Interpreta un importe espanol estricto y conserva cero como dato."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ValueError("Un booleano no es un importe valido.")
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            raise ValueError(f"Importe no finito: {valor!r}")
        return valor
    if isinstance(valor, (int, float)):
        try:
            numero = Decimal(str(valor))
        except InvalidOperation as error:
            raise ValueError(f"Importe no valido: {valor!r}") from error
        if not numero.is_finite():
            raise ValueError(f"Importe no finito: {valor!r}")
        return numero
    if not isinstance(valor, str):
        raise ValueError(f"Importe no valido: {valor!r}")

    texto = valor.strip()
    if not texto:
        return None
    texto = re.sub(r"\s*€\s*$", "", texto).strip()
    coincidencia = _IMPORTE_ES.fullmatch(texto)
    if coincidencia is None:
        raise ValueError(f"Importe espanol no valido o ambiguo: {valor!r}")

    signo_inicial = coincidencia.group("signo_inicial")
    signo_final = coincidencia.group("signo_final")
    if signo_inicial and signo_final:
        raise ValueError(f"Importe con mas de un signo: {valor!r}")

    entero = coincidencia.group("entero").replace(".", "")
    decimales = coincidencia.group("decimales") or ""
    numero = Decimal(entero + decimales.replace(",", "."))
    return -numero if signo_inicial == "-" or signo_final == "-" else numero


def normalizar_identificador(valor: str | int | None) -> str | None:
    """Devuelve identificadores como texto y conserva sus ceros iniciales."""
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (str, int)):
        raise ValueError(f"Identificador no valido: {valor!r}")
    texto = str(valor).strip()
    return texto or None


def valor_visible(campo: Any) -> Any:
    """Solo devuelve valores de IA respaldados por evidencia no vacia."""
    if not isinstance(campo, Mapping):
        return None
    evidencias = campo.get("evidencias")
    if not isinstance(evidencias, Sequence) or isinstance(evidencias, (str, bytes)):
        return None
    if not evidencias or not all(_evidencia_valida(evidencia) for evidencia in evidencias):
        return None
    return campo.get("valor")


def _evidencia_valida(evidencia: Any) -> bool:
    if evidencia is None:
        return False
    if isinstance(evidencia, str):
        return bool(evidencia.strip())
    if isinstance(evidencia, Mapping):
        return any(
            valor is not None and (not isinstance(valor, str) or bool(valor.strip()))
            for valor in evidencia.values()
        )
    return False


def validar_suma_monetaria(
    sumandos: Sequence[Decimal | None],
    esperado: Decimal | None,
    *,
    tolerancia: Decimal = Decimal("0.01"),
) -> ResultadoValidacionMonetaria:
    valores = (*sumandos, esperado, tolerancia)
    if any(valor is not None and not isinstance(valor, Decimal) for valor in valores):
        raise TypeError("Las validaciones monetarias solo admiten Decimal o None.")
    if not tolerancia.is_finite() or any(
        valor is not None and not valor.is_finite() for valor in (*sumandos, esperado)
    ):
        raise ValueError("Las validaciones monetarias exigen valores finitos.")
    if tolerancia < 0:
        raise ValueError("La tolerancia no puede ser negativa.")
    if esperado is None or any(valor is None for valor in sumandos):
        return ResultadoValidacionMonetaria(
            EstadoValidacion.NO_EVALUABLE, esperado, None, None, tolerancia
        )
    obtenido = sum((valor for valor in sumandos if valor is not None), Decimal("0"))
    diferencia = obtenido - esperado
    estado = EstadoValidacion.OK if abs(diferencia) <= tolerancia else EstadoValidacion.ERROR
    return ResultadoValidacionMonetaria(estado, esperado, obtenido, diferencia, tolerancia)


@dataclass(frozen=True, slots=True)
class AliasProveedor:
    nombre_canonico: str
    alias: tuple[str, ...]

    def __post_init__(self) -> None:
        nombres = (self.nombre_canonico, *self.alias)
        normalizados = [_clave_proveedor(nombre) for nombre in nombres]
        if any(not nombre for nombre in normalizados):
            raise ValueError("El proveedor y sus alias no pueden estar vacios.")
        if len(normalizados) != len(set(normalizados)):
            raise ValueError("El proveedor contiene alias duplicados.")

    def normalizar(self, valor: str | None) -> str | None:
        if valor is None:
            return None
        texto = valor.strip()
        if not texto:
            return None
        permitidos = {_clave_proveedor(self.nombre_canonico), *map(_clave_proveedor, self.alias)}
        return self.nombre_canonico if _clave_proveedor(texto) in permitidos else texto


def _clave_proveedor(valor: str) -> str:
    normalizado = unicodedata.normalize("NFKC", valor)
    return " ".join(normalizado.split()).casefold()


def aplicar_regla_determinista(
    *,
    nombre: str,
    version: str,
    precondiciones: Mapping[str, bool | None],
    entradas: Mapping[str, Any],
    derivar: Callable[[Mapping[str, Any]], T],
) -> ResultadoRegla:
    """Aplica una regla solo con condiciones verdaderas y entradas presentes."""
    if not nombre.strip() or not version.strip():
        raise ValueError("La regla debe declarar nombre y version.")

    bloqueos = [
        f"precondicion:{clave}={valor!r}"
        for clave, valor in precondiciones.items()
        if valor is not True
    ]
    bloqueos.extend(
        f"entrada:{clave}=ausente" for clave, valor in entradas.items() if valor is None
    )
    if not precondiciones:
        bloqueos.append("precondiciones=ausentes")
    if not entradas:
        bloqueos.append("entradas=ausentes")
    if bloqueos:
        return ResultadoRegla(None, False, None, tuple(bloqueos))

    valor = derivar(entradas)
    if valor is None:
        return ResultadoRegla(None, False, None, ("resultado=ausente",))
    procedencia = Procedencia(
        tipo=TipoProcedencia.REGLA_DETERMINISTA,
        fuente="python",
        regla=nombre,
        version_regla=version,
    )
    return ResultadoRegla(valor, True, procedencia, ())
