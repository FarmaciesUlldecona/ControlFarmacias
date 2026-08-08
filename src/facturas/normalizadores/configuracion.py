"""Configuracion estable compartida por normalizadores de proveedor."""

from __future__ import annotations

from dataclasses import dataclass

from src.facturas.normalizadores.comun import AliasProveedor


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguracionProveedor:
    """Politica documental y de farmacia, sin datos de facturas concretas."""

    proveedor_nombre_canonico: str
    aliases: tuple[str, ...] = ()
    farmacia: str = "PIO"
    categoria: str = "MERCANCIA"
    requiere_conciliacion_albaranes: bool = True
    id_farmacia: str = "PIO"
    metodo_identificacion_farmacia: str = "CIF"

    def __post_init__(self) -> None:
        if not self.farmacia.strip():
            raise ValueError("La farmacia no puede estar vacia.")
        if not self.categoria.strip():
            raise ValueError("La categoria no puede estar vacia.")
        if not self.metodo_identificacion_farmacia.strip():
            raise ValueError("El metodo de identificacion no puede estar vacio.")
        self.alias_proveedor

    @property
    def alias_proveedor(self) -> AliasProveedor:
        return AliasProveedor(
            nombre_canonico=self.proveedor_nombre_canonico,
            alias=self.aliases,
        )
