from __future__ import annotations

import json
from pathlib import Path

from src.facturas.normalizadores.suavinex import (
    ConfiguracionSuavinex,
    normalizar_suavinex,
)
from src.models.factura import serializar_valor


RAIZ = Path(__file__).resolve().parents[2]
RUTA_EXTRACCION = (
    RAIZ
    / "pruebas/facturas/resultados/openai/benchmark_luna_terra_sol_v1"
    / "general/caso_03/gpt-5.6-luna/estructurado.json"
)
RUTA_SALIDA = RAIZ / "pruebas/facturas/resultados/openai/normalizacion_suavinex"


def cargar_json(ruta: Path) -> dict:
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra la entrada permitida: {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def ejecutar() -> tuple[Path, Path]:
    extraccion = cargar_json(RUTA_EXTRACCION)
    metadatos = extraccion["metadatos_prueba"]
    resultado, incidencias = normalizar_suavinex(
        extraccion,
        metadatos,
        ConfiguracionSuavinex(
            archivo_origen=metadatos["documento_local"],
            albaran_unico_abarca_factura=True,
        ),
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
    print(f"Factura normalizada: {ruta_factura}")
    print(f"Incidencias: {ruta_incidencias}")
    return ruta_factura, ruta_incidencias


if __name__ == "__main__":
    ejecutar()
