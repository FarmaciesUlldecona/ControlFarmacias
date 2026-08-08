"""Configuraciones estables para documentos procesables por la ruta estandar."""

from src.facturas.normalizadores.configuracion import ConfiguracionProveedor


CONFIGURACION_HYGIE31 = ConfiguracionProveedor(
    proveedor_nombre_canonico="HYGIE31 ESPAÑA, S.L.U.",
    aliases=("Hygie31 España SLU.",),
    categoria="CUOTA_SERVICIO",
    requiere_conciliacion_albaranes=False,
    farmacia="PIO",
    id_farmacia="PIO",
    metodo_identificacion_farmacia="CIF",
)
