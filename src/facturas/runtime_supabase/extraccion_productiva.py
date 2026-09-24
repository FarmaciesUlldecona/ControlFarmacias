from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .modelos import (
    IncidenciaRuntime,
    PasoExtraccion,
    ResultadoEtapa,
    ResultadoExtraccionProductiva,
    UsoLuna,
)


class ExtractorCampos(Protocol):
    codigo: str

    def extraer(
        self,
        ruta_pdf: Path,
        campos_pendientes: frozenset[str],
    ) -> ResultadoEtapa: ...


class ExtractorLunaCampos(Protocol):
    codigo: str

    def extraer_campos(
        self,
        ruta_pdf: Path,
        campos_pendientes: frozenset[str],
    ) -> tuple[ResultadoEtapa, UsoLuna]: ...


@dataclass(frozen=True, slots=True)
class ConfiguracionExtraccionProductiva:
    luna_habilitada: bool = False


class OrquestadorExtraccionProductiva:
    """Completa solo campos pendientes, sin invocar ``normalizar_pdf``.

    El orden productivo es especifico, local generico, OCR local y Luna
    field-only. Ninguna etapa puede sobrescribir un valor ya resuelto.
    """

    def __init__(
        self,
        *,
        extractor_especifico: ExtractorCampos | None,
        extractor_generico_local: ExtractorCampos | None,
        extractor_ocr_local: ExtractorCampos | None,
        extractor_luna: ExtractorLunaCampos | None,
        configuracion: ConfiguracionExtraccionProductiva | None = None,
    ) -> None:
        self._etapas = tuple(
            etapa
            for etapa in (
                extractor_especifico,
                extractor_generico_local,
                extractor_ocr_local,
            )
            if etapa is not None
        )
        self._luna = extractor_luna
        self._configuracion = configuracion or ConfiguracionExtraccionProductiva()

    def extraer(
        self,
        ruta_pdf: str | Path,
        campos_requeridos: set[str] | frozenset[str],
    ) -> ResultadoExtraccionProductiva:
        ruta = Path(ruta_pdf)
        pendientes = frozenset(campos_requeridos)
        valores: dict[str, object] = {}
        pasos: list[PasoExtraccion] = []
        uso_luna: UsoLuna | None = None

        for etapa in self._etapas:
            if not pendientes:
                break
            pendientes = self._aplicar_etapa(
                etapa.codigo,
                etapa.extraer(ruta, pendientes),
                pendientes,
                valores,
                pasos,
            )

        if pendientes and self._configuracion.luna_habilitada and self._luna:
            solicitados = pendientes
            resultado, uso_luna = self._luna.extraer_campos(ruta, pendientes)
            if frozenset(uso_luna.campos) != solicitados:
                raise ValueError("Luna debe declarar exactamente los campos solicitados")
            pendientes = self._aplicar_etapa(
                self._luna.codigo,
                resultado,
                pendientes,
                valores,
                pasos,
            )

        incidencias: tuple[IncidenciaRuntime, ...] = ()
        if pendientes:
            incidencias = (
                IncidenciaRuntime(
                    codigo="CAMPOS_PENDIENTES_TRAS_EXTRACCION",
                    categoria="NORMALIZACION",
                    severidad="AVISO",
                    bloqueante=True,
                    mensaje_usuario="La factura requiere revision de Pio.",
                    detalle_tecnico={"campos": sorted(pendientes)},
                ),
            )

        return ResultadoExtraccionProductiva(
            valores=valores,
            campos_pendientes=tuple(sorted(pendientes)),
            pasos=tuple(pasos),
            uso_luna=uso_luna,
            incidencias=incidencias,
        )

    @staticmethod
    def _aplicar_etapa(
        codigo: str,
        resultado: ResultadoEtapa,
        pendientes: frozenset[str],
        valores: dict[str, object],
        pasos: list[PasoExtraccion],
    ) -> frozenset[str]:
        resueltos = frozenset(resultado.valores)
        inesperados = resueltos - pendientes
        if inesperados:
            raise ValueError(
                f"{codigo} devolvio campos no solicitados: {sorted(inesperados)}"
            )
        valores.update(resultado.valores)
        pasos.append(
            PasoExtraccion(
                etapa=codigo,
                campos_solicitados=tuple(sorted(pendientes)),
                campos_resueltos=tuple(sorted(resueltos)),
                provenance=dict(resultado.provenance),
                uso_ocr=resultado.uso_ocr,
            )
        )
        return pendientes - resueltos
