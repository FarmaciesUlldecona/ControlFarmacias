from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from ..catalogo import BackendLocalRequerido, ProveedorLocal
from .alliance import AdaptadorAlliance
from .base import AdaptadorBase
from .cofares import AdaptadorCofares
from .fedefarma import AdaptadorFedefarma
from .gold_pequenos import (
    AdaptadorEcoceutics,
    AdaptadorEports,
    AdaptadorLogista,
    AdaptadorLoreal,
    AdaptadorMoretti,
    AdaptadorTotalcare,
)
from .guimera import AdaptadorGuimera, AdaptadorGuimeraHistorico
from .hefame import AdaptadorHefame
from .hplus_consumo import AdaptadorHplusConsumo
from .historicos_gold1 import (
    AdaptadorDermofarmHistorico,
    AdaptadorGasCasaHistorico,
    AdaptadorPierreFabreHistorico,
    AdaptadorSuavinexHistorico,
)


ClaseAdaptador: TypeAlias = type[AdaptadorBase]


@dataclass(frozen=True)
class EntradaAdaptadorLocal:
    proveedor: ProveedorLocal
    clase: ClaseAdaptador
    backend_requerido: BackendLocalRequerido = BackendLocalRequerido.PDFIUM_NATIVO
    shadow_habilitable: bool = True

    @property
    def adapter_id(self) -> str:
        return self.clase.id

    @property
    def version(self) -> str:
        return self.clase.version

    def crear(self) -> AdaptadorBase:
        return self.clase()


REGISTRO_ADAPTADORES_LOCALES: tuple[EntradaAdaptadorLocal, ...] = (
    EntradaAdaptadorLocal(ProveedorLocal.COFARES, AdaptadorCofares),
    EntradaAdaptadorLocal(ProveedorLocal.HEFAME, AdaptadorHefame),
    EntradaAdaptadorLocal(ProveedorLocal.HPLUS_CONSUMO, AdaptadorHplusConsumo),
    EntradaAdaptadorLocal(ProveedorLocal.FEDEFARMA, AdaptadorFedefarma),
    EntradaAdaptadorLocal(ProveedorLocal.ALLIANCE, AdaptadorAlliance),
    EntradaAdaptadorLocal(ProveedorLocal.ECOCEUTICS, AdaptadorEcoceutics),
    EntradaAdaptadorLocal(ProveedorLocal.EPORTS, AdaptadorEports),
    EntradaAdaptadorLocal(ProveedorLocal.LOGISTA_PHARMA, AdaptadorLogista),
    EntradaAdaptadorLocal(ProveedorLocal.LOREAL, AdaptadorLoreal),
    EntradaAdaptadorLocal(ProveedorLocal.MORETTI, AdaptadorMoretti),
    EntradaAdaptadorLocal(ProveedorLocal.TOTALCARE, AdaptadorTotalcare),
    EntradaAdaptadorLocal(
        ProveedorLocal.GUIMERA,
        AdaptadorGuimera,
        BackendLocalRequerido.PDFIUM_CON_OCR_LOCAL,
    ),
    EntradaAdaptadorLocal(
        ProveedorLocal.GUIMERA,
        AdaptadorGuimeraHistorico,
        BackendLocalRequerido.PDFIUM_CON_OCR_LOCAL,
    ),
    EntradaAdaptadorLocal(ProveedorLocal.DERMOFARM, AdaptadorDermofarmHistorico),
    EntradaAdaptadorLocal(ProveedorLocal.GAS_CASA, AdaptadorGasCasaHistorico),
    EntradaAdaptadorLocal(ProveedorLocal.PIERRE_FABRE, AdaptadorPierreFabreHistorico),
    EntradaAdaptadorLocal(ProveedorLocal.SUAVINEX, AdaptadorSuavinexHistorico),
)


def entradas_adaptadores_locales() -> tuple[EntradaAdaptadorLocal, ...]:
    return REGISTRO_ADAPTADORES_LOCALES


def entrada_por_adapter_id(adapter_id: str | None) -> EntradaAdaptadorLocal | None:
    if adapter_id is None:
        return None
    return next(
        (entrada for entrada in REGISTRO_ADAPTADORES_LOCALES if entrada.adapter_id == adapter_id),
        None,
    )


def adaptadores_locales() -> tuple[AdaptadorBase, ...]:
    """Registro veraz de adaptadores locales, todos habilitables para shadow."""
    return tuple(entrada.crear() for entrada in REGISTRO_ADAPTADORES_LOCALES)


def adaptadores_productivos() -> tuple[AdaptadorBase, ...]:
    """LEGACY_COMPATIBILITY: el nombre no confiere autoridad productiva."""
    return adaptadores_locales()
