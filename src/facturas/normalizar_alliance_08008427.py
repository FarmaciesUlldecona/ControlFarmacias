from __future__ import annotations

import json
from pathlib import Path

from src.facturas.normalizadores.alliance import (
    ConfiguracionAlliance,
    normalizar_alliance,
    serializar_json,
)


RUTA_PROYECTO = Path(__file__).resolve().parents[2]
RUTA_GENERAL = RUTA_PROYECTO / "pruebas/facturas/resultados/openai/comparativa_modelos/repeticion_01/gpt-5.6-luna/estructurado.json"
RUTA_TABLAS = RUTA_PROYECTO / "pruebas/facturas/resultados/openai/luna_tablas_literales_alliance_08008427/estructurado.json"
RUTA_SALIDA = RUTA_PROYECTO / "pruebas/facturas/resultados/openai/normalizacion_alliance_08008427"
ARCHIVO_ORIGEN = "ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf"


def cargar_json(ruta: Path) -> dict:
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra la entrada permitida: {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def ejecutar() -> tuple[Path, Path]:
    general = cargar_json(RUTA_GENERAL)
    tablas = cargar_json(RUTA_TABLAS)
    resultado, incidencias = normalizar_alliance(
        general,
        tablas,
        ConfiguracionAlliance(archivo_origen=ARCHIVO_ORIGEN),
    )
    RUTA_SALIDA.mkdir(parents=True, exist_ok=True)
    ruta_factura = RUTA_SALIDA / "factura_normalizada.json"
    ruta_incidencias = RUTA_SALIDA / "incidencias.json"
    ruta_factura.write_text(
        json.dumps(serializar_json(resultado), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ruta_incidencias.write_text(
        json.dumps(
            {
                "version_normalizador": resultado["version_normalizador"],
                "archivo_origen": ARCHIVO_ORIGEN,
                "incidencias": serializar_json(incidencias),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Factura normalizada: {ruta_factura}")
    print(f"Incidencias: {ruta_incidencias}")
    print(f"Albaranes reconstruidos: {len(resultado['resultado_normalizado']['albaranes'])}")
    return ruta_factura, ruta_incidencias


if __name__ == "__main__":
    ejecutar()
