from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import re
import unicodedata


def _normalizar_identificador(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


class TipoEconomicoHefame(StrEnum):
    HEFAME_MERCANCIA = "HEFAME_MERCANCIA"
    HEFAME_CONSUMIBLES = "HEFAME_CONSUMIBLES"


@dataclass(frozen=True, slots=True)
class IdentidadFuncionalProveedor:
    proveedor_documental: str
    nif_documental: str
    grupo_funcional: str
    tipo_economico: TipoEconomicoHefame
    requiere_albaran_operativo: bool
    regla: str

    def to_dict(self):
        data = asdict(self)
        data["tipo_economico"] = self.tipo_economico.value
        return data


def clasificar_grupo_hefame(
    *, proveedor_documental: str, nif_documental: str, layout: str,
    contenido_consumibles_demostrado: bool = False,
) -> IdentidadFuncionalProveedor | None:
    """Agrupa funcionalmente sin fusionar las identidades fiscales."""
    nif = _normalizar_identificador(nif_documental)
    if nif == "F30004444" and layout == "hefame-local":
        return IdentidadFuncionalProveedor(
            proveedor_documental, nif, "HEFAME",
            TipoEconomicoHefame.HEFAME_MERCANCIA, True,
            "NIF_F30004444_Y_LAYOUT_HEFAME_MERCANCIA",
        )
    if (
        nif == "B30462451"
        and layout == "hplus-consumo-local"
        and contenido_consumibles_demostrado
    ):
        return IdentidadFuncionalProveedor(
            proveedor_documental, nif, "HEFAME",
            TipoEconomicoHefame.HEFAME_CONSUMIBLES, False,
            "NIF_B30462451_Y_CONTENIDO_CONSUMIBLES_DOCUMENTADO",
        )
    return None
