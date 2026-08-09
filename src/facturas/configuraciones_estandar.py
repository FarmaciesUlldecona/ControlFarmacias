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


CONFIGURACION_GUIMERA = ConfiguracionProveedor(
    proveedor_nombre_canonico="FARMACIA GUIMERA C.B.",
    aliases=(),
    categoria="MERCANCIA",
    requiere_conciliacion_albaranes=False,
    farmacia="PIO",
    id_farmacia="PIO",
    metodo_identificacion_farmacia="CIF",
)


CONFIGURACION_PIERRE_FABRE = ConfiguracionProveedor(
    proveedor_nombre_canonico="PIERRE FABRE IBÉRICA, S.A.",
    aliases=("Pierre Fabre Ibérica S.A.",),
    categoria="MERCANCIA",
    requiere_conciliacion_albaranes=True,
    farmacia="PIO",
    id_farmacia="PIO",
    metodo_identificacion_farmacia="CIF",
)


CONFIGURACION_ENDESA = ConfiguracionProveedor(
    proveedor_nombre_canonico="ENDESA ENERGÍA, S.A.U.",
    aliases=("Endesa Energía, S.A. Unipersonal",),
    categoria="SUMINISTRO",
    requiere_conciliacion_albaranes=False,
    farmacia="PIO",
    id_farmacia="PIO",
    metodo_identificacion_farmacia="CIF",
)
