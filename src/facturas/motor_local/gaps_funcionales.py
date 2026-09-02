from __future__ import annotations

from dataclasses import dataclass

from .catalogo import ProveedorLocal


@dataclass(frozen=True)
class GapFuncionalPendiente:
    proveedor: ProveedorLocal
    codigo: str
    descripcion: str
    estado: str = "GAP_FUNCIONAL_PENDIENTE"


GAPS_FUNCIONALES_PENDIENTES: tuple[GapFuncionalPendiente, ...] = (
    GapFuncionalPendiente(
        ProveedorLocal.COFARES,
        "COFARES_DTO_PRONTO_PAGO_SENTIDO",
        "Dto. Pronto pago = ABONO pendiente de decision de implementacion.",
    ),
    GapFuncionalPendiente(
        ProveedorLocal.DERMOFARM,
        "DERMOFARM_ABONO_FACTURA_MES_SIGUIENTE",
        "Relacion de abonos descontados en la primera factura del mes siguiente.",
    ),
)
