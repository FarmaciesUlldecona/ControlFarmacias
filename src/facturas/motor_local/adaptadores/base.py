from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..conciliacion import EspecificacionConciliacion
from ..modelos import AlbaranLocal, DocumentoLocal, EvidenciaLocal, SegmentoLocal


@dataclass(frozen=True)
class Reconocimiento:
    estado: str
    puntuacion: int
    evidencias: list[dict[str, Any]]


class AdaptadorBase(ABC):
    id: str
    version: str
    capacidades: dict[str, str]

    @abstractmethod
    def reconocer(self, documento: DocumentoLocal) -> Reconocimiento: ...

    @abstractmethod
    def extraer_albaranes(
        self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]
    ) -> list[AlbaranLocal]: ...

    def extraer_cabecera(self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]) -> dict[str, Any]:
        return {}

    def extraer_movimientos(self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]) -> list[dict[str, Any]]:
        return []

    def extraer_impuestos(self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]) -> list[dict[str, Any]]:
        return []

    def extraer_vencimientos(self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]) -> list[dict[str, Any]]:
        return []

    def extraer_otros(self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]) -> list[dict[str, Any]]:
        return []

    def declarar_conciliaciones(
        self,
        documento: DocumentoLocal,
        segmentos: list[SegmentoLocal],
        *,
        cabecera: dict[str, Any],
        albaranes: list[AlbaranLocal],
        movimientos: list[dict[str, Any]],
        impuestos: list[dict[str, Any]],
        vencimientos: list[dict[str, Any]],
        otros: list[dict[str, Any]],
    ) -> list[EspecificacionConciliacion]:
        return []

    def incidencias_extraccion(self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]) -> list[dict[str, Any]]:
        return []

    def evidencia(
        self,
        documento: DocumentoLocal,
        pagina: int,
        literal: str,
        bbox,
        fila: str,
        bbox_fila,
        tabla: str | None,
        columna: str | None,
        regla: str,
        tipo: str = "GEOMETRIA_LOCAL",
    ) -> EvidenciaLocal:
        return EvidenciaLocal(
            documento.sha_documento,
            pagina,
            literal,
            bbox.to_list() if bbox else None,
            fila,
            fila,
            bbox_fila.to_list() if bbox_fila else None,
            tabla,
            columna,
            self.id,
            self.version,
            regla,
            tipo,
            "LITERAL_LOCAL_DETERMINISTA" if tipo == "LITERAL_LOCAL" else "DERIVACION_LOCAL_DETERMINISTA",
        )

    @staticmethod
    def segmento_de_pagina(segmentos: list[SegmentoLocal], pagina: int) -> SegmentoLocal | None:
        return next((s for s in segmentos if s.paginas[0] <= pagina <= s.paginas[1]), None)
