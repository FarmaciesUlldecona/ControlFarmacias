from dataclasses import dataclass
from datetime import datetime


@dataclass
class Albaran:
    id_contador: int
    id_proveedor: int
    proveedor: str
    id_albaran: str
    fecha: datetime
    importe_pvp: float
    importe_puc: float
    dto: float