from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterable

from .conciliacion import conciliar_importes
from .modelos import DetalleConciliacion, FacturaTrabajo
from .repositorios import RepositorioConciliacion


ConstructorDetalles = Callable[[FacturaTrabajo], Iterable[DetalleConciliacion]]


@dataclass(slots=True)
class WorkerConciliacion:
    repositorio: RepositorioConciliacion
    construir_detalles: ConstructorDetalles
    worker_id: str
    tolerancia: Decimal = Decimal("0.0500")

    def ejecutar_una(self) -> bool:
        factura = self.repositorio.reclamar_factura(self.worker_id)
        if factura is None:
            return False
        return self._procesar(factura, "AUTOMATICO")

    def ejecutar_una_manual(self) -> bool:
        """Concilia como maximo una factura (R5/R8, migracion 18).

        Usa el selector y el ordering oficiales mediante el claim MANUAL_ONE_SHOT;
        no admite preseleccion ni activa ``conciliacion_automatica``.
        """
        factura = self.repositorio.reclamar_factura_manual_one_shot(self.worker_id)
        if factura is None:
            return False
        return self._procesar(factura, "MANUAL_ONE_SHOT")

    def _procesar(self, factura: FacturaTrabajo, disparador: str) -> bool:
        if factura.importe_total is None:
            self.repositorio.fallar_conciliacion(
                factura,
                "IMPORTE_FACTURA_AUSENTE",
                "La factura no tiene total documental comparable",
                self.worker_id,
                disparador,
            )
            return False
        try:
            resultado = conciliar_importes(
                factura.importe_total,
                self.construir_detalles(factura),
                tolerancia=self.tolerancia,
            )
            if disparador == "AUTOMATICO":
                self.repositorio.guardar_conciliacion(factura, self.worker_id, resultado)
            else:
                self.repositorio.guardar_conciliacion(
                    factura, self.worker_id, resultado, disparador=disparador,
                )
            return True
        except Exception as exc:
            self.repositorio.fallar_conciliacion(
                factura,
                type(exc).__name__,
                str(exc),
                self.worker_id,
                disparador,
            )
            return False


def construir_worker_conciliacion(
    repositorio: RepositorioConciliacion,
    worker_id: str,
    *,
    construir_detalles: ConstructorDetalles | None = None,
    tolerancia: Decimal = Decimal("0.0500"),
) -> WorkerConciliacion:
    """Compone el runtime Supabase sin acceso directo a Farmatic."""
    constructor = construir_detalles or repositorio.construir_detalles
    return WorkerConciliacion(repositorio, constructor, worker_id, tolerancia)
