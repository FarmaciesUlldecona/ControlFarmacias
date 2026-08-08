"""Ejecucion reutilizable del normalizador estandar sobre una extraccion existente."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from src.facturas.normalizadores.configuracion import ConfiguracionProveedor
from src.facturas.normalizadores.estandar import normalizar_estandar
from src.models.factura import serializar_valor


def cargar_json(ruta: Path) -> dict:
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra la entrada permitida: {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def ejecutar(
    ruta_extraccion: Path,
    ruta_salida: Path,
    configuracion: ConfiguracionProveedor,
    *,
    ruta_metadatos: Path | None = None,
    archivo_origen: str | None = None,
    fecha_ejecucion: datetime | None = None,
) -> tuple[Path, Path]:
    extraccion = cargar_json(ruta_extraccion)
    metadatos = (
        cargar_json(ruta_metadatos)
        if ruta_metadatos is not None
        else dict(extraccion.get("metadatos_prueba") or {})
    )
    origen = archivo_origen or metadatos.get("archivo_original_local")
    if not isinstance(origen, str) or not origen.strip():
        raise ValueError("La ejecucion debe recibir un archivo_origen explicito.")
    resultado, incidencias = normalizar_estandar(
        extraccion,
        metadatos,
        configuracion,
        fecha_ejecucion,
        archivo_origen=origen,
    )

    ruta_salida.mkdir(parents=True, exist_ok=True)
    ruta_factura = ruta_salida / "factura_normalizada.json"
    ruta_incidencias = ruta_salida / "incidencias.json"
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
