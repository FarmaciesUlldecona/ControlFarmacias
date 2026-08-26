from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class ConfiguracionShadow:
    """Configuracion conservadora: el shadow queda apagado por defecto."""

    habilitado: bool = False
    directorio_observabilidad: Path | None = None

    @classmethod
    def desde_entorno(cls) -> "ConfiguracionShadow":
        valor = os.getenv("CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW_COFARES", "false")
        habilitado = valor.strip().casefold() in {"1", "true", "si", "yes"}
        ruta = os.getenv("CONTROLFARMACIAS_MOTOR_LOCAL_OBSERVABILIDAD")
        return cls(habilitado=habilitado, directorio_observabilidad=Path(ruta) if ruta else None)
