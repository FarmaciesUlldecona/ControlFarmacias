"""Compositor productivo del worker manual one-shot.

Unico punto que construye ``WorkerNormalizacion`` con piezas productivas:
Storage privado -> PDF verificado -> motor local autorizado por proveedor ->
puente multifactura certificado -> persistencia oficial. No crea clientes, no
lee ni escribe flags, no usa Luna y no se ejecuta al importarse.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Callable, Mapping

from src.facturas.motor_local.adaptadores.registro import REGISTRO_ADAPTADORES_LOCALES
from src.facturas.motor_local.catalogo import ProveedorLocal

from .extraccion_productiva import (
    ConfiguracionExtraccionProductiva,
    OrquestadorExtraccionProductiva,
)
from .modelos import (
    ConfiguracionRuntime,
    DocumentoTrabajo,
    ResultadoEtapa,
    ResultadoExtraccionProductiva,
)
from .multifactura import adaptar_resultado_local
from .repositorios import RepositorioRuntimeSupabase
from .worker_automatico import WorkerAutomatico, construir_worker_automatico
from .worker_conciliacion import construir_worker_conciliacion
from .worker_normalizacion import WorkerNormalizacion


BUCKET_FACTURAS = "facturas-pdf"
CAMPO_LAYOUT = "proveedor_layout"
CAMPO_DOCUMENTO = "documento_normalizado_v2"
CAMPOS_REQUERIDOS_MANUAL = frozenset({CAMPO_LAYOUT, CAMPO_DOCUMENTO})

# Autoridad productiva exclusiva del compositor manual, distinta del registro
# global AUTORIDADES_EXTRACTORES_LOCALES (que permanece todo False). Cada entrada
# exige un puente multifactura certificado para su layout.
AUTORIDAD_COMPOSITOR_MANUAL: Mapping[ProveedorLocal, str] = MappingProxyType({
    ProveedorLocal.ALLIANCE: "alliance-local",
})
LAYOUTS_CON_PUENTE_CERTIFICADO = frozenset({"alliance-local"})

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class DocumentoNoAptoManual(ValueError):
    """Barrera fail-closed del compositor manual; siempre requiere revision."""

    requiere_revision = True


def proveedor_por_layout(layout: str | None) -> ProveedorLocal | None:
    for entrada in REGISTRO_ADAPTADORES_LOCALES:
        if entrada.adapter_id == layout:
            return entrada.proveedor
    return None


def autoridad_manual_habilitada(layout: str | None) -> bool:
    proveedor = proveedor_por_layout(layout)
    return (
        proveedor is not None
        and AUTORIDAD_COMPOSITOR_MANUAL.get(proveedor) == layout
        and layout in LAYOUTS_CON_PUENTE_CERTIFICADO
    )


def _sha256(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


@dataclass(slots=True)
class MaterializadorStoragePrivado:
    """Descarga exclusivamente el PDF del documento ya reclamado y verifica su SHA."""

    cliente: Any
    directorio: Path
    bucket: str = BUCKET_FACTURAS

    def __call__(self, documento: DocumentoTrabajo) -> Path:
        respuesta = (
            self.cliente.table("documentos_facturas")
            .select("id,archivo_ruta,archivo_hash")
            .eq("id", documento.documento_id)
            .limit(2)
            .execute()
        )
        filas = respuesta.data or []
        if len(filas) != 1:
            raise DocumentoNoAptoManual("DOCUMENTO_RECLAMADO_NO_LOCALIZADO")
        fila = filas[0]
        if str(fila.get("id")) != documento.documento_id:
            raise DocumentoNoAptoManual("DOCUMENTO_RECLAMADO_NO_LOCALIZADO")
        ruta = str(fila.get("archivo_ruta") or "")
        if ruta != documento.archivo_ruta:
            raise DocumentoNoAptoManual("RUTA_STORAGE_NO_COINCIDE_CON_CLAIM")
        partes = PurePosixPath(ruta).parts
        if not ruta or ruta.startswith("/") or "\\" in ruta or ".." in partes:
            raise DocumentoNoAptoManual("RUTA_STORAGE_NO_SEGURA")
        esperado = str(fila.get("archivo_hash") or "").lower()
        if not _SHA256.fullmatch(esperado):
            raise DocumentoNoAptoManual("SHA256_REGISTRADO_INVALIDO")
        try:
            contenido = self.cliente.storage.from_(self.bucket).download(ruta)
        except Exception as exc:
            raise DocumentoNoAptoManual(
                f"OBJETO_STORAGE_NO_DISPONIBLE:{type(exc).__name__}"
            ) from exc
        if not isinstance(contenido, (bytes, bytearray)) or not contenido:
            raise DocumentoNoAptoManual("OBJETO_STORAGE_VACIO")
        if _sha256(bytes(contenido)) != esperado:
            raise DocumentoNoAptoManual("SHA256_NO_COINCIDE")
        self.directorio.mkdir(parents=True, exist_ok=True)
        destino = self.directorio / f"{documento.documento_id}.pdf"
        destino.write_bytes(bytes(contenido))
        return destino


def _sustituir_ruta(valor: Any, ruta: str, reemplazo: str) -> Any:
    if isinstance(valor, dict):
        return {k: _sustituir_ruta(v, ruta, reemplazo) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_sustituir_ruta(v, ruta, reemplazo) for v in valor]
    if isinstance(valor, str) and valor == ruta:
        return reemplazo
    return valor


def _motor_local_productivo():
    from src.facturas.motor_local.backend.pdfium import BackendPdfium
    from src.facturas.motor_local.servicio import MotorDocumentoLocal

    return MotorDocumentoLocal(BackendPdfium())


@dataclass(slots=True)
class ExtractorDocumentalAutorizado:
    """Etapa ``ExtractorCampos`` que solo resuelve proveedores con autoridad manual."""

    crear_motor: Callable[[], Any] = _motor_local_productivo
    codigo: str = "MOTOR_LOCAL_AUTORIZADO_MANUAL"

    def extraer(self, ruta_pdf: Path, campos_pendientes: frozenset[str]) -> ResultadoEtapa:
        if not CAMPOS_REQUERIDOS_MANUAL <= campos_pendientes:
            return ResultadoEtapa(provenance={"motivo": "CAMPOS_NO_SOLICITADOS"})
        try:
            local = self.crear_motor().extraer(ruta_pdf)
        except Exception as exc:
            return ResultadoEtapa(provenance={
                "motivo": "EXTRACCION_LOCAL_ERROR", "error": type(exc).__name__,
            })
        documento = local.documento
        layout = documento.get("layout")
        incidencias = sorted({
            str(i.get("codigo")) for i in local.incidencias if isinstance(i, Mapping)
        })
        base = {
            "layout": layout,
            "sha256": documento.get("sha256"),
            "paginas": documento.get("pages"),
            "facturas_detectadas": len(local.facturas),
            "incidencias": incidencias,
        }
        if layout is None:
            motivo = (
                "REQUIERE_OCR_O_LUNA_NO_AUTORIZADO"
                if "PENDIENTE_OCR" in incidencias
                else "PROVEEDOR_NO_RECONOCIDO"
            )
            return ResultadoEtapa(provenance={**base, "motivo": motivo})
        if not autoridad_manual_habilitada(layout):
            return ResultadoEtapa(provenance={**base, "motivo": "PROVEEDOR_NO_SOPORTADO_MANUAL"})
        if local.documento_completo_demostrado is not True:
            return ResultadoEtapa(provenance={**base, "motivo": "DOCUMENTO_INCOMPLETO"})
        try:
            normalizado = adaptar_resultado_local(local)
        except Exception as exc:
            return ResultadoEtapa(provenance={
                **base, "motivo": "ADAPTACION_NO_CERTIFICADA", "error": str(exc),
            })
        sha = str(documento.get("sha256") or "")
        normalizado = _sustituir_ruta(normalizado, str(documento.get("source")), f"sha256:{sha}")
        return ResultadoEtapa(
            valores={CAMPO_LAYOUT: layout, CAMPO_DOCUMENTO: normalizado},
            provenance={**base, "motivo": "AUTORIZADO", "proveedor": proveedor_por_layout(layout)},
        )


def ensamblar_documento_manual(
    _documento: DocumentoTrabajo,
    resultado: ResultadoExtraccionProductiva,
) -> dict:
    """Entrega el documento V2 solo si la extraccion autorizada fue completa."""
    if resultado.uso_luna is not None:
        raise DocumentoNoAptoManual("LUNA_NO_AUTORIZADA_EN_COMPOSITOR_MANUAL")
    if resultado.campos_pendientes or any(i.bloqueante for i in resultado.incidencias):
        motivos = [
            paso.provenance.get("motivo")
            for paso in resultado.pasos
            if paso.provenance.get("motivo")
        ]
        raise DocumentoNoAptoManual(motivos[-1] if motivos else "CAMPOS_PENDIENTES_TRAS_EXTRACCION")
    documento = resultado.valores.get(CAMPO_DOCUMENTO)
    if not isinstance(documento, Mapping):
        raise DocumentoNoAptoManual("DOCUMENTO_NORMALIZADO_AUSENTE")
    return dict(documento)


def construir_worker_manual_productivo(
    cliente: Any,
    configuracion: ConfiguracionRuntime,
    worker_id: str,
    directorio_trabajo: Path,
) -> WorkerAutomatico:
    """Compone el worker manual productivo. Solo debe invocarse ``ejecutar_una_manual``."""
    if configuracion.luna_habilitada:
        raise ValueError("LUNA_NO_AUTORIZADA_EN_COMPOSITOR_MANUAL")
    if configuracion.farmacias_habilitadas != ("PIO",):
        raise ValueError("SOLO_PIO_AUTORIZADA_EN_COMPOSITOR_MANUAL")
    if not worker_id.strip():
        raise ValueError("WORKER_ID_OBLIGATORIO")
    repositorio = RepositorioRuntimeSupabase(cliente)
    orquestador = OrquestadorExtraccionProductiva(
        extractor_especifico=ExtractorDocumentalAutorizado(),
        extractor_generico_local=None,
        extractor_ocr_local=None,
        extractor_luna=None,
        configuracion=ConfiguracionExtraccionProductiva(luna_habilitada=False),
    )
    normalizacion = WorkerNormalizacion(
        repositorio=repositorio,
        materializar_pdf=MaterializadorStoragePrivado(cliente, Path(directorio_trabajo)),
        orquestador=orquestador,
        campos_requeridos=CAMPOS_REQUERIDOS_MANUAL,
        worker_id=worker_id,
        ensamblar_documento=ensamblar_documento_manual,
    )
    conciliacion = construir_worker_conciliacion(
        repositorio,
        worker_id,
        tolerancia=configuracion.tolerancia_conciliacion,
    )
    return construir_worker_automatico(normalizacion, conciliacion, configuracion)
