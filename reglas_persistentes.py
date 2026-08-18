"""Catálogo persistente y tipado de reglas del Supervisor V0.2.9."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5


RULE_SCHEMA_VERSION = 1


class ErrorRegla(RuntimeError):
    pass


class ReglaNoEncontrada(ErrorRegla, FileNotFoundError):
    pass


class ReglaInvalida(ErrorRegla, ValueError):
    pass


class TipoRegla(str, Enum):
    ABSOLUTA = "ABSOLUTA"
    FUNCIONAL = "FUNCIONAL"


class AccionRegla(str, Enum):
    AUTO_APPLY = "AUTO_APPLY"
    BLOCK = "BLOCK"


def _ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid_estable(nombre: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"controlfarmacias:v0.2.9:{nombre}"))


@dataclass(frozen=True)
class CambioEstadoRegla:
    activa: bool
    timestamp: str
    motivo: str

    def a_dict(self) -> dict[str, Any]:
        return {"activa": self.activa, "timestamp": self.timestamp, "motivo": self.motivo}

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "CambioEstadoRegla":
        return cls(bool(datos["activa"]), str(datos["timestamp"]), str(datos["motivo"]))


@dataclass(frozen=True)
class ReglaPersistente:
    rule_id: str
    nombre: str
    ambito: str
    condicion: dict[str, Any]
    accion: dict[str, Any]
    prioridad: int
    activa: bool
    origen: str
    fecha_creacion: str
    metadata: dict[str, Any]
    version: int
    tipo: TipoRegla
    historial_estado: tuple[CambioEstadoRegla, ...]

    def __post_init__(self) -> None:
        try:
            UUID(self.rule_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ReglaInvalida("rule_id debe ser UUID") from exc
        for campo in ("nombre", "ambito", "origen", "fecha_creacion"):
            if not isinstance(getattr(self, campo), str) or not getattr(self, campo).strip():
                raise ReglaInvalida(f"{campo} debe ser texto no vacío")
        if not isinstance(self.condicion, dict) or not isinstance(self.accion, dict):
            raise ReglaInvalida("condicion y accion deben ser objetos estructurados")
        if isinstance(self.prioridad, bool) or not isinstance(self.prioridad, int):
            raise ReglaInvalida("prioridad debe ser entera")
        if not isinstance(self.activa, bool) or self.version < 1:
            raise ReglaInvalida("activa/version inválidos")
        if not isinstance(self.metadata, dict):
            raise ReglaInvalida("metadata debe ser un objeto")
        object.__setattr__(self, "tipo", TipoRegla(self.tipo))
        object.__setattr__(self, "historial_estado", tuple(self.historial_estado))

    def a_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RULE_SCHEMA_VERSION,
            "rule_id": self.rule_id,
            "nombre": self.nombre,
            "ambito": self.ambito,
            "condicion": self.condicion,
            "accion": self.accion,
            "prioridad": self.prioridad,
            "activa": self.activa,
            "origen": self.origen,
            "fecha_creacion": self.fecha_creacion,
            "metadata": self.metadata,
            "version": self.version,
            "tipo": self.tipo.value,
            "historial_estado": [item.a_dict() for item in self.historial_estado],
        }

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> "ReglaPersistente":
        copia = dict(datos)
        if copia.pop("schema_version", None) != RULE_SCHEMA_VERSION:
            raise ReglaInvalida("schema de regla no soportado")
        copia["historial_estado"] = tuple(
            CambioEstadoRegla.desde_dict(item) for item in copia["historial_estado"]
        )
        return cls(**copia)


REGLAS_ABSOLUTAS_INICIALES: tuple[dict[str, Any], ...] = (
    {
        "rule_id": _uuid_estable("FARMATIC_READ_ONLY"),
        "nombre": "FARMATIC_READ_ONLY",
        "ambito": "FARMATIC",
        "condicion": {
            "campo": "tipo_accion",
            "operador": "IN",
            "valor": ["INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "TRUNCATE", "PROCEDIMIENTO_MODIFICADOR", "ESCRIBIR"],
        },
        "accion": {"decision": "BLOCK", "codigo": "ABSOLUTE_RULE_VIOLATION", "motivo": "Farmatic / SQL Server es siempre solo lectura"},
        "prioridad": 1_000_000,
        "origen": "regla absoluta del proyecto ControlFarmacias",
        "metadata": {"inmutable": True},
    },
    {
        "rule_id": _uuid_estable("FACTURAS_ZERO_INVENTIONS"),
        "nombre": "FACTURAS_ZERO_INVENTIONS",
        "ambito": "FACTURAS",
        "condicion": {
            "any": [
                {"campo": "datos.dato_demostrable", "operador": "EQ", "valor": False},
                {"campo": "tipo_accion", "operador": "IN", "valor": ["INVENTAR_DATO", "INFERIR_DESDE_NOMBRE_ARCHIVO", "USAR_NOMBRE_ARCHIVO_COMO_EVIDENCIA"]},
            ]
        },
        "accion": {"decision": "BLOCK", "codigo": "ABSOLUTE_RULE_VIOLATION", "motivo": "Facturas: cero invenciones; usar null o [] sin evidencia documental"},
        "prioridad": 1_000_000,
        "origen": "regla absoluta del proyecto ControlFarmacias",
        "metadata": {"inmutable": True, "nombre_archivo_no_es_evidencia": True},
    },
)

REGLAS_FUNCIONALES_CONFIRMADAS: tuple[dict[str, Any], ...] = (
    {
        "rule_id": _uuid_estable("DIFFERENCE_LT_1_RECONCILE"),
        "nombre": "DIFFERENCE_LT_1_RECONCILE",
        "ambito": "CONCILIACION",
        "condicion": {"all": [
            {"campo": "datos.diferencia_absoluta", "operador": "LT", "valor": 1},
            {"campo": "datos.trazabilidad_economica_completa", "operador": "EQ", "valor": True},
        ]},
        "accion": {"decision": "AUTO_APPLY", "codigo": "ACTION_AUTO_APPROVED", "resultado": "CONCILIAR_CON_DISCREPANCIA_REGISTRADA"},
        "prioridad": 100,
        "origen": "regla funcional previamente aprobada",
        "metadata": {"discrepancia_debe_registrarse": True},
    },
    {
        "rule_id": _uuid_estable("ECONOMIC_TRACE_REQUIRED"),
        "nombre": "ECONOMIC_TRACE_REQUIRED",
        "ambito": "CONCILIACION",
        "condicion": {"all": [
            {"campo": "tipo_accion", "operador": "EQ", "valor": "CONCILIAR"},
            {"campo": "datos.trazabilidad_economica_completa", "operador": "NE", "valor": True},
        ]},
        "accion": {"decision": "BLOCK", "codigo": "ACTION_BLOCKED", "motivo": "la trazabilidad económica completa es obligatoria"},
        "prioridad": 200,
        "origen": "regla funcional previamente aprobada",
        "metadata": {},
    },
    {
        "rule_id": _uuid_estable("DELIVERY_NOTE_EXACT_NOT_REQUIRED"),
        "nombre": "DELIVERY_NOTE_EXACT_NOT_REQUIRED",
        "ambito": "CONCILIACION",
        "condicion": {"campo": "tipo_accion", "operador": "EQ", "valor": "VALIDAR_COINCIDENCIA_ALBARAN"},
        "accion": {"decision": "AUTO_APPLY", "codigo": "ACTION_AUTO_APPROVED", "resultado": "NO_BLOQUEAR_POR_COINCIDENCIA_NO_EXACTA"},
        "prioridad": 100,
        "origen": "regla funcional previamente aprobada",
        "metadata": {},
    },
)


class GestorReglas:
    """Guarda una regla por JSON; desactivar crea una nueva versión, nunca borra."""

    def __init__(self, directorio: str | Path = Path("estado") / "reglas") -> None:
        self.directorio = Path(directorio)

    def asegurar_reglas_absolutas(self) -> tuple[ReglaPersistente, ...]:
        resultado = []
        for datos in REGLAS_ABSOLUTAS_INICIALES:
            try:
                regla = self.obtener_regla(datos["rule_id"])
            except ReglaNoEncontrada:
                regla = self.crear_regla(tipo=TipoRegla.ABSOLUTA, activa=True, **datos)
            resultado.append(regla)
        return tuple(resultado)

    def asegurar_reglas_confirmadas(self) -> tuple[ReglaPersistente, ...]:
        resultado = list(self.asegurar_reglas_absolutas())
        for datos in REGLAS_FUNCIONALES_CONFIRMADAS:
            try:
                regla = self.obtener_regla(datos["rule_id"])
            except ReglaNoEncontrada:
                regla = self.crear_regla(tipo=TipoRegla.FUNCIONAL, activa=True, **datos)
            resultado.append(regla)
        return tuple(resultado)

    def crear_regla(
        self, *, nombre: str, ambito: str, condicion: dict[str, Any],
        accion: dict[str, Any], prioridad: int, origen: str,
        metadata: dict[str, Any] | None = None, activa: bool = True,
        tipo: TipoRegla | str = TipoRegla.FUNCIONAL, rule_id: str | None = None,
    ) -> ReglaPersistente:
        timestamp = _ahora_utc()
        regla = ReglaPersistente(
            rule_id=rule_id or str(uuid4()), nombre=nombre, ambito=ambito.upper(),
            condicion=dict(condicion), accion=dict(accion), prioridad=prioridad,
            activa=activa, origen=origen, fecha_creacion=timestamp,
            metadata=dict(metadata or {}), version=1, tipo=TipoRegla(tipo),
            historial_estado=(CambioEstadoRegla(activa, timestamp, "creación"),),
        )
        if (self.directorio / f"{regla.rule_id}.json").exists():
            raise ReglaInvalida(f"rule_id duplicado: {regla.rule_id}")
        self._guardar(regla)
        return regla

    def obtener_regla(self, rule_id: str) -> ReglaPersistente:
        try:
            UUID(rule_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ReglaInvalida("rule_id debe ser UUID") from exc
        path = self.directorio / f"{rule_id}.json"
        if not path.is_file():
            raise ReglaNoEncontrada(f"regla no encontrada: {rule_id}")
        try:
            regla = ReglaPersistente.desde_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ReglaInvalida) as exc:
            raise ReglaInvalida(f"regla persistida inválida: {exc}") from exc
        if regla.rule_id != rule_id:
            raise ReglaInvalida("rule_id interno no coincide con el archivo")
        return regla

    def listar_reglas(self, *, activas: bool | None = None, tipo: TipoRegla | str | None = None) -> list[ReglaPersistente]:
        if not self.directorio.exists():
            return []
        reglas = [self.obtener_regla(path.stem) for path in sorted(self.directorio.glob("*.json"))]
        if activas is not None:
            reglas = [item for item in reglas if item.activa is activas]
        if tipo is not None:
            tipo_final = TipoRegla(tipo)
            reglas = [item for item in reglas if item.tipo is tipo_final]
        return sorted(reglas, key=lambda item: (-item.prioridad, item.fecha_creacion, item.rule_id))

    def cambiar_estado(self, rule_id: str, activa: bool, *, motivo: str = "cambio explícito") -> ReglaPersistente:
        regla = self.obtener_regla(rule_id)
        if regla.tipo is TipoRegla.ABSOLUTA and not activa:
            raise ReglaInvalida("una regla absoluta no puede desactivarse")
        if regla.activa is activa:
            return regla
        actualizada = replace(
            regla, activa=activa, version=regla.version + 1,
            historial_estado=(*regla.historial_estado, CambioEstadoRegla(activa, _ahora_utc(), motivo)),
        )
        self._guardar(actualizada)
        return actualizada

    def desactivar_regla(self, rule_id: str, *, motivo: str = "desactivación explícita") -> ReglaPersistente:
        return self.cambiar_estado(rule_id, False, motivo=motivo)

    def activar_regla(self, rule_id: str, *, motivo: str = "activación explícita") -> ReglaPersistente:
        return self.cambiar_estado(rule_id, True, motivo=motivo)

    def _guardar(self, regla: ReglaPersistente) -> None:
        self.directorio.mkdir(parents=True, exist_ok=True)
        destino = self.directorio / f"{regla.rule_id}.json"
        descriptor, nombre = tempfile.mkstemp(prefix=f".{regla.rule_id}.", suffix=".tmp", dir=self.directorio)
        temporal = Path(nombre)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
                json.dump(regla.a_dict(), archivo, ensure_ascii=False, indent=2, allow_nan=False)
                archivo.write("\n")
                archivo.flush()
                os.fsync(archivo.fileno())
            os.replace(temporal, destino)
        except BaseException:
            temporal.unlink(missing_ok=True)
            raise
