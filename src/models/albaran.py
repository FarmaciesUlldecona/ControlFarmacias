from dataclasses import dataclass
from datetime import datetime
from typing import Any


def conservar_id_proveedor(valor: Any | None) -> str | None:
    """Preserva identificadores textuales; solo representa tipos no-string con str()."""
    if valor is None:
        return None
    if isinstance(valor, str):
        return valor
    return str(valor)


@dataclass
class Albaran:
    id_contador: int
    id_proveedor: str | None
    proveedor: str
    id_albaran: str
    fecha: datetime
    importe_pvp: float
    importe_puc: float
    dto: float
