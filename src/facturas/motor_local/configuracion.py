from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class ConfiguracionShadow:
    """Configuracion conservadora: el shadow queda apagado por defecto."""

    habilitado: bool = False
    directorio_observabilidad: Path | None = None
    variable_origen: str | None = None

    @classmethod
    def desde_entorno(cls) -> "ConfiguracionShadow":
        general = os.getenv("CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW")
        historica = os.getenv("CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW_COFARES")
        if general is not None:
            valor = general
            variable_origen = "CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW"
        elif historica is not None:
            # LEGACY_COMPATIBILITY: alias de transicion. La variable general
            # tiene precedencia explicita cuando ambas estan presentes.
            valor = historica
            variable_origen = "CONTROLFARMACIAS_MOTOR_LOCAL_SHADOW_COFARES"
        else:
            valor = "false"
            variable_origen = None
        habilitado = valor.strip().casefold() in {"1", "true", "si", "yes"}
        ruta = os.getenv("CONTROLFARMACIAS_MOTOR_LOCAL_OBSERVABILIDAD")
        return cls(
            habilitado=habilitado,
            directorio_observabilidad=Path(ruta) if ruta else None,
            variable_origen=variable_origen,
        )
