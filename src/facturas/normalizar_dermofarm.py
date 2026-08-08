from __future__ import annotations

import json
from pathlib import Path

from src.facturas.normalizadores.dermofarm import (
    ConfiguracionDermofarm,
    normalizar_dermofarm,
)
from src.models.factura import serializar_valor


RUTA_PROYECTO = Path(__file__).resolve().parents[2]
RUTA_ENTRADA = RUTA_PROYECTO / "pruebas/facturas/resultados/openai/muestra_completa/documento_01"
RUTA_EXTRACCION = RUTA_ENTRADA / "estructurado.json"
RUTA_METADATOS = RUTA_ENTRADA / "metadatos_entrada.json"
RUTA_SALIDA = RUTA_PROYECTO / "pruebas/facturas/resultados/openai/normalizacion_dermofarm"


def cargar_json(ruta: Path) -> dict:
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra la entrada permitida: {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def ejecutar() -> tuple[Path, Path]:
    extraccion = cargar_json(RUTA_EXTRACCION)
    metadatos = cargar_json(RUTA_METADATOS)
    resultado, incidencias = normalizar_dermofarm(
        extraccion,
        metadatos,
        ConfiguracionDermofarm(),
        archivo_origen=metadatos["archivo_original_local"],
    )
    RUTA_SALIDA.mkdir(parents=True, exist_ok=True)
    ruta_factura = RUTA_SALIDA / "factura_normalizada.json"
    ruta_incidencias = RUTA_SALIDA / "incidencias.json"
    ruta_factura.write_text(
        json.dumps(serializar_valor(resultado), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ruta_incidencias.write_text(
        json.dumps(
            {
                "version_normalizador": resultado["version_normalizador"],
                "archivo_origen": resultado["archivo_origen"],
                "incidencias": serializar_valor(incidencias),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Abono normalizado: {ruta_factura}")
    print(f"Incidencias: {ruta_incidencias}")
    return ruta_factura, ruta_incidencias


if __name__ == "__main__":
    ejecutar()
