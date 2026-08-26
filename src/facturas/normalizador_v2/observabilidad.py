from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

VERSION_OBSERVABILIDAD = "normalizador-v2.observabilidad.1"
ETAPAS = (
    "A_CANDIDATO_LUNA",
    "B_DECISION_SEGUNDA_LECTURA",
    "C_NORMALIZACION_GENERAL",
    "D_REGLAS",
    "E_CONSOLIDACION_SEGMENTADA",
    "F_ESTADO_FINAL",
)
_CLAVES_SENSIBLES = {
    "api_key", "apikey", "authorization", "cabeceras", "credentials",
    "credenciales", "headers", "password", "secret", "token",
}


def _seguro(valor: Any) -> Any:
    if isinstance(valor, bytes):
        return "<contenido_binario_omitido>"
    if isinstance(valor, BaseModel):
        return _seguro(valor.model_dump(mode="json"))
    if is_dataclass(valor) and not isinstance(valor, type):
        return _seguro(asdict(valor))
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {
            str(clave): _seguro(contenido)
            for clave, contenido in valor.items()
            if str(clave).casefold() not in _CLAVES_SENSIBLES
        }
    if isinstance(valor, (list, tuple)):
        return [_seguro(item) for item in valor]
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    return str(valor)


class TrazaObservabilidad:
    def __init__(self, documento_id: str, archivo_origen: str):
        self._datos: dict[str, Any] = {
            "version": VERSION_OBSERVABILIDAD,
            "documento_id": documento_id,
            "archivo_origen": archivo_origen,
            "etapas": {etapa: None for etapa in ETAPAS},
        }

    def registrar(self, etapa: str, valor: Any) -> None:
        if etapa not in ETAPAS:
            raise ValueError(f"etapa de observabilidad desconocida: {etapa}")
        self._datos["etapas"][etapa] = _seguro(valor)

    def datos(self) -> dict[str, Any]:
        return json.loads(self.json_estable())

    def json_estable(self) -> str:
        return json.dumps(self._datos, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


SinkObservabilidad = Callable[[dict[str, Any]], None]


def persistir_traza_atomica(traza: TrazaObservabilidad, directorio: str | Path) -> Path:
    destino = Path(directorio)
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{traza.datos()['documento_id']}.observabilidad.json"
    descriptor, temporal = tempfile.mkstemp(prefix=f".{ruta.name}.", suffix=".tmp", dir=destino)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(traza.json_estable())
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporal, ruta)
    except Exception:
        try:
            Path(temporal).unlink(missing_ok=True)
        finally:
            raise
    return ruta


def emitir_traza(
    traza: TrazaObservabilidad,
    *,
    directorio: str | Path | None = None,
    sink: SinkObservabilidad | None = None,
) -> Path | None:
    ruta = persistir_traza_atomica(traza, directorio) if directorio is not None else None
    if sink is not None:
        sink(traza.datos())
    return ruta
