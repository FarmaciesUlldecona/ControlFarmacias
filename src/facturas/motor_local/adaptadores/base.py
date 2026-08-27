from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..conciliacion import EspecificacionConciliacion
from ..modelos import AlbaranLocal, DocumentoLocal, EvidenciaLocal, LineaLocal, PalabraLocal, SegmentoLocal, union_bbox


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

    def extraer_facturas(self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]) -> list[dict[str, Any]]:
        """Devuelve facturas independientes cuando el documento es multifactura."""
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
        facturas: list[dict[str, Any]],
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

    def campo_documentado(
        self,
        documento: DocumentoLocal,
        valor: Any,
        palabras: list[PalabraLocal],
        linea,
        tabla: str,
        columna: str,
        regla: str,
        *,
        literal: str | None = None,
    ) -> dict[str, Any]:
        literal = " ".join(p.texto for p in palabras) if literal is None else literal
        return {
            "valor": valor,
            "literal": literal,
            "evidencias": [self.evidencia(
                documento, linea.pagina, literal, union_bbox([p.bbox for p in palabras]),
                linea.texto, linea.bbox, tabla, columna, regla, "LITERAL_LOCAL",
            )],
        }

    def campo_multilinea(
        self,
        documento: DocumentoLocal,
        valor: Any,
        palabras: list[PalabraLocal],
        lineas: list[LineaLocal],
        tabla: str,
        columna: str,
        regla: str,
    ) -> dict[str, Any]:
        """Conserva como una unidad documentada texto demostrado en varias líneas."""
        literal = " ".join(p.texto for p in palabras)
        contexto = " | ".join(linea.texto for linea in lineas)
        return {
            "valor": valor,
            "literal": literal,
            "evidencias": [self.evidencia(
                documento, lineas[0].pagina, literal, union_bbox([p.bbox for p in palabras]),
                contexto, union_bbox([linea.bbox for linea in lineas]), tabla, columna, regla,
                "LITERAL_LOCAL",
            )],
        }

    @staticmethod
    def lineas_continuacion_columna(
        lineas: list[LineaLocal],
        ancla: LineaLocal,
        *,
        x0: float,
        x1: float,
        salto_maximo: float = 12.0,
    ) -> list[LineaLocal]:
        """Une solo líneas consecutivas enteramente contenidas en la misma columna."""
        salida: list[LineaLocal] = []
        limite_y = ancla.bbox.y1
        for linea in sorted((l for l in lineas if l.bbox.y0 > ancla.bbox.y0), key=lambda l: l.bbox.y0):
            if linea.bbox.y0 - limite_y > salto_maximo:
                break
            if not linea.palabras or any(p.bbox.x0 < x0 or p.bbox.x1 > x1 for p in linea.palabras):
                break
            salida.append(linea)
            limite_y = linea.bbox.y1
        return salida
