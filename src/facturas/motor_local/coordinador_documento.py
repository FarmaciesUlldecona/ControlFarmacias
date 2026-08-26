from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from src.facturas.normalizador_v2.modelos import DocumentoNormalizado, FacturaNormalizada

from .adaptadores.base import Reconocimiento
from .autoridad import AutoridadExtraccion, EstadoElegibilidad, evaluar_elegibilidad_cofares
from .modelos import DocumentoExtraidoLocal, DocumentoLocal
from .puente_cofares import ResultadoEnsambladoCofares, ensamblar_factura_cofares


class EstadoIdentidad(StrEnum):
    IDENTIDAD_UNICA = "IDENTIDAD_UNICA"
    IDENTIDAD_DUPLICADA = "IDENTIDAD_DUPLICADA"
    IDENTIDAD_INSUFICIENTE = "IDENTIDAD_INSUFICIENTE"
    IDENTIDAD_CONFLICTIVA = "IDENTIDAD_CONFLICTIVA"


class EstadoMatch(StrEnum):
    MATCH_UNICO = "MATCH_UNICO"
    SIN_MATCH = "SIN_MATCH"
    MULTIPLES_MATCH = "MULTIPLES_MATCH"
    IDENTIDAD_INSUFICIENTE = "IDENTIDAD_INSUFICIENTE"
    CONFLICTO = "CONFLICTO"


@dataclass(frozen=True)
class ClaveFacturaDocumental:
    numero_factura: str | None = None
    proveedor_nif: str | None = None
    fecha_factura: str | None = None
    destinatario_nif: str | None = None
    paginas: tuple[int, int] | None = None
    sha_documento: str | None = None
    evidencias: dict[str, tuple[dict[str, Any], ...]] = field(default_factory=dict)

    @property
    def estado(self) -> EstadoIdentidad:
        return EstadoIdentidad.IDENTIDAD_UNICA if self.numero_factura and self.evidencias.get("numero_factura") else EstadoIdentidad.IDENTIDAD_INSUFICIENTE


@dataclass(frozen=True)
class ResultadoMatch:
    estado: EstadoMatch
    clave_local: ClaveFacturaDocumental
    candidatos_compatibles: tuple[str, ...]
    candidatos_conflictivos: tuple[str, ...]
    factura_destino_id: str | None
    campos_usados: tuple[str, ...]
    razones: tuple[str, ...]
    claves_pipeline: tuple[tuple[str, ClaveFacturaDocumental], ...]


@dataclass(frozen=True)
class PlanAutoridadLocal:
    estado_match: EstadoMatch
    estado_plan: str
    factura_local: ClaveFacturaDocumental
    factura_destino: str | None
    capacidad: str
    autoridad_propuesta: AutoridadExtraccion
    razones: tuple[str, ...]
    incidencias: tuple[str, ...]
    evidencia_identidad: dict[str, tuple[dict[str, Any], ...]]
    candidatos_encontrados: int
    sha_documento: str | None
    paginas_segmento: tuple[int, int] | None


@dataclass(frozen=True)
class ResultadoSimulacionDocumento:
    documento: DocumentoNormalizado
    aplicada: bool
    plan: PlanAutoridadLocal
    ensamblado_factura: ResultadoEnsambladoCofares | None


def clave_local_cofares(resultado: DocumentoExtraidoLocal) -> ClaveFacturaDocumental:
    if len(resultado.segmentos) != 1:
        return ClaveFacturaDocumental(sha_documento=resultado.documento.get("sha256"))
    segmento = resultado.segmentos[0]
    paginas = tuple(segmento.paginas) if len(segmento.paginas) == 2 else None
    evidencias_numero = tuple(
        evidencia for evidencia in segmento.evidencias
        if segmento.identidad_candidata in evidencia.get("identidades", [])
    ) if segmento.identidad_candidata else ()
    evidencias = {"numero_factura": evidencias_numero} if evidencias_numero else {}
    if paginas is not None:
        evidencias["paginas"] = ({"pagina_inicio": paginas[0], "pagina_fin": paginas[1], "origen": "SEGMENTACION_LOCAL"},)
    if resultado.documento.get("sha256"):
        evidencias["sha_documento"] = ({"sha256": resultado.documento["sha256"], "origen": "CONTENIDO_PDF"},)
    return ClaveFacturaDocumental(
        numero_factura=segmento.identidad_candidata,
        paginas=paginas,
        sha_documento=resultado.documento.get("sha256"),
        evidencias=evidencias,
    )


def clave_pipeline(factura: FacturaNormalizada, documento: DocumentoNormalizado) -> ClaveFacturaDocumental:
    numero, ev_numero = _documentado(factura.numero_factura)
    proveedor_nif, ev_proveedor = _documentado(factura.proveedor.nif if factura.proveedor else None)
    fecha, ev_fecha = _fecha_documentada(factura)
    destinatario_nif, ev_destino = _documentado(factura.destinatario.nif if factura.destinatario else None)
    evidencias = {
        campo: tuple(e.model_dump(mode="json") for e in valores)
        for campo, valores in {
            "numero_factura": ev_numero, "proveedor_nif": ev_proveedor,
            "fecha_factura": ev_fecha, "destinatario_nif": ev_destino,
        }.items() if valores
    }
    evidencias["paginas"] = ({"pagina_inicio": factura.pagina_inicio, "pagina_fin": factura.pagina_fin, "origen": "RANGO_FACTURA_PIPELINE"},)
    if documento.metadata_tecnica.huella_contenido:
        evidencias["sha_documento"] = ({"sha256": documento.metadata_tecnica.huella_contenido, "origen": "METADATA_DOCUMENTO"},)
    return ClaveFacturaDocumental(
        numero_factura=str(numero) if numero is not None else None,
        proveedor_nif=str(proveedor_nif) if proveedor_nif is not None else None,
        fecha_factura=fecha,
        destinatario_nif=str(destinatario_nif) if destinatario_nif is not None else None,
        paginas=(factura.pagina_inicio, factura.pagina_fin),
        sha_documento=documento.metadata_tecnica.huella_contenido,
        evidencias=evidencias,
    )


def emparejar_factura(clave_local: ClaveFacturaDocumental, documento: DocumentoNormalizado) -> ResultadoMatch:
    claves = tuple((factura.factura_id, clave_pipeline(factura, documento)) for factura in documento.facturas)
    if clave_local.estado == EstadoIdentidad.IDENTIDAD_INSUFICIENTE:
        return ResultadoMatch(EstadoMatch.IDENTIDAD_INSUFICIENTE, clave_local, (), (), None, (), ("NUMERO_FACTURA_LOCAL_NO_DOCUMENTADO",), claves)
    compatibles: list[str] = []
    conflictivos: list[str] = []
    campos_usados = {"numero_factura"}
    for factura_id, clave in claves:
        if clave.numero_factura != clave_local.numero_factura:
            continue
        conflictos = []
        for campo in ("proveedor_nif", "fecha_factura", "destinatario_nif", "paginas", "sha_documento"):
            local = getattr(clave_local, campo)
            pipeline = getattr(clave, campo)
            if local is not None and pipeline is not None and clave_local.evidencias.get(campo) and clave.evidencias.get(campo):
                campos_usados.add(campo)
                if local != pipeline:
                    conflictos.append(campo)
        (conflictivos if conflictos else compatibles).append(factura_id)
    if len(compatibles) == 1:
        estado, destino, razones = EstadoMatch.MATCH_UNICO, compatibles[0], ("UNA_IDENTIDAD_COMPATIBLE",)
    elif len(compatibles) > 1:
        estado, destino, razones = EstadoMatch.MULTIPLES_MATCH, None, ("MAS_DE_UNA_IDENTIDAD_COMPATIBLE",)
    elif conflictivos:
        estado, destino, razones = EstadoMatch.CONFLICTO, None, ("ANCLAS_DOCUMENTALES_CONTRADICTORIAS",)
    else:
        estado, destino, razones = EstadoMatch.SIN_MATCH, None, ("NINGUNA_IDENTIDAD_COMPATIBLE",)
    return ResultadoMatch(
        estado, clave_local, tuple(sorted(compatibles)), tuple(sorted(conflictivos)), destino,
        tuple(sorted(campos_usados)), razones, claves,
    )


def crear_plan_autoridad_cofares(
    documento_pipeline: DocumentoNormalizado,
    documento_local: DocumentoLocal,
    resultado_local: DocumentoExtraidoLocal,
    reconocimiento: Reconocimiento,
) -> PlanAutoridadLocal:
    clave = clave_local_cofares(resultado_local)
    match = emparejar_factura(clave, documento_pipeline)
    elegibilidad = evaluar_elegibilidad_cofares(documento_local, resultado_local, reconocimiento)
    lista = match.estado == EstadoMatch.MATCH_UNICO and elegibilidad.estado == EstadoElegibilidad.ELEGIBLE and resultado_local.capacidades.get("albaranes") == "SOPORTADO"
    razones = [*match.razones, *elegibilidad.razones]
    if reconocimiento.estado != "RECONOCIDO":
        razones.append(f"RECONOCIMIENTO_{reconocimiento.estado}")
    return PlanAutoridadLocal(
        estado_match=match.estado,
        estado_plan="LISTO_SIMULACION" if lista else "LOCAL_NO_APLICABLE",
        factura_local=clave,
        factura_destino=match.factura_destino_id if lista else None,
        capacidad="albaranes",
        autoridad_propuesta=AutoridadExtraccion.LOCAL if lista else AutoridadExtraccion.IA,
        razones=tuple(dict.fromkeys(razones)),
        incidencias=() if lista else (f"MATCH_{match.estado.value}",),
        evidencia_identidad=clave.evidencias,
        candidatos_encontrados=len(match.candidatos_compatibles),
        sha_documento=clave.sha_documento,
        paginas_segmento=clave.paginas,
    )


def simular_plan_cofares(
    documento_pipeline: DocumentoNormalizado,
    documento_local: DocumentoLocal,
    resultado_local: DocumentoExtraidoLocal,
    reconocimiento: Reconocimiento,
) -> ResultadoSimulacionDocumento:
    plan = crear_plan_autoridad_cofares(documento_pipeline, documento_local, resultado_local, reconocimiento)
    if plan.estado_plan != "LISTO_SIMULACION" or plan.factura_destino is None:
        return ResultadoSimulacionDocumento(documento_pipeline, False, plan, None)
    destinos = [f for f in documento_pipeline.facturas if f.factura_id == plan.factura_destino]
    if len(destinos) != 1:
        return ResultadoSimulacionDocumento(documento_pipeline, False, plan, None)
    ensamblado = ensamblar_factura_cofares(destinos[0], documento_local, resultado_local, reconocimiento, simular=True)
    if not ensamblado.aplicada:
        return ResultadoSimulacionDocumento(documento_pipeline, False, plan, ensamblado)
    facturas = [ensamblado.factura if f.factura_id == plan.factura_destino else f for f in documento_pipeline.facturas]
    return ResultadoSimulacionDocumento(documento_pipeline.model_copy(update={"facturas": facturas}), True, plan, ensamblado)


def _documentado(valor):
    return (None, ()) if valor is None or not valor.evidencia else (valor.valor, tuple(valor.evidencia))


def _fecha_documentada(factura):
    if factura.fecha_factura is None or not factura.fecha_factura.evidencia:
        return None, ()
    valor = factura.fecha_factura.valor
    return (valor.iso.isoformat() if valor.iso else valor.literal), tuple(factura.fecha_factura.evidencia)
