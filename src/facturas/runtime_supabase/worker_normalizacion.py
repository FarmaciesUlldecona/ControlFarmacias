from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable
from src.facturas.completitud_documental import validar_documento_antes_de_persistir

from .extraccion_productiva import OrquestadorExtraccionProductiva
from .modelos import DocumentoTrabajo
from .repositorios import RepositorioNormalizacion


MaterializadorPdf = Callable[[DocumentoTrabajo], Path]
EnsambladorDocumento = Callable[[DocumentoTrabajo, object], dict]


@dataclass(slots=True)
class WorkerNormalizacion:
    repositorio: RepositorioNormalizacion
    materializar_pdf: MaterializadorPdf
    orquestador: OrquestadorExtraccionProductiva
    campos_requeridos: frozenset[str]
    worker_id: str
    ensamblar_documento: EnsambladorDocumento | None = None

    def _worker_de_ejecucion(self) -> str:
        """2BI: id unico por ejecucion (base + sufijo). Un claim solo lo puede cerrar la ejecucion que lo
        tomo; otra ejecucion con la misma base ya no persiste sobre un claim ajeno o recuperado."""
        return f"{self.worker_id}#{uuid.uuid4().hex[:12]}"

    def ejecutar_una(self) -> bool:
        """Ruta automatica/reprocesado; conserva el claim historico."""
        worker_id = self._worker_de_ejecucion()
        documento = self.repositorio.reclamar_documento(worker_id)
        if documento is None:
            return False
        disparador = "REPROCESADO" if documento.reprocesado_manual else "AUTOMATICO"
        return self._procesar_documento(documento, disparador, worker_id)

    def ejecutar_una_manual_one_shot(self) -> bool:
        """Autoriza un unico claim manual sin preseleccion ni cambio de flags."""
        worker_id = self._worker_de_ejecucion()
        documento = self.repositorio.reclamar_documento_manual_one_shot(worker_id)
        if documento is None:
            return False
        return self._procesar_documento(documento, "MANUAL_ONE_SHOT", worker_id)

    def _procesar_documento(
        self,
        documento: DocumentoTrabajo,
        disparador: str,
        worker_id: str,
    ) -> bool:
        idempotency_key = f"normalizacion:{documento.documento_id}:{disparador}:fallo"
        try:
            ruta = self.materializar_pdf(documento)
            resultado = self.orquestador.extraer(ruta, self.campos_requeridos)
            if self.ensamblar_documento is not None:
                resultado = replace(
                    resultado,
                    documento_normalizado=self.ensamblar_documento(documento, resultado),
                )
            validar_documento_antes_de_persistir(documento.farmacia, resultado.documento_normalizado)
            contenido_canonico = (
                resultado.documento_normalizado
                if resultado.documento_normalizado is not None
                else {
                    "valores": dict(resultado.valores),
                    "pendientes": resultado.campos_pendientes,
                }
            )
            serializado = json.dumps(
                contenido_canonico,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
            resultado_hash = hashlib.sha256(serializado).hexdigest()
            idempotency_key = (
                f"normalizacion:{documento.documento_id}:{disparador}:{resultado_hash}"
            )
            persistir = getattr(
                self.repositorio,
                "persistir_documento_automatico",
                self.repositorio.persistir_normalizacion,
            )
            persistir(
                documento,
                resultado,
                resultado_hash,
                worker_id,
                disparador,
                idempotency_key,
            )
            return True
        except Exception as exc:
            self.repositorio.fallar_ejecucion(
                documento,
                type(exc).__name__,
                str(exc),
                worker_id,
                disparador,
                idempotency_key,
            )
            return False
        except (KeyboardInterrupt, SystemExit) as exc:
            # 2BI: Ctrl+C o salida forzada tras el claim. Se registra el fallo (cuenta como intento, R3)
            # para no dejar un claim huerfano y se relanza; si el registro tambien falla, el claim queda
            # para la recuperacion (migracion 25), y la interrupcion original no se pierde.
            try:
                self.repositorio.fallar_ejecucion(
                    documento,
                    type(exc).__name__,
                    str(exc) or type(exc).__name__,
                    worker_id,
                    disparador,
                    idempotency_key,
                )
            except Exception:
                pass
            raise


def construir_worker_productivo(*args, **kwargs) -> WorkerNormalizacion:
    """Punto de composicion futuro; nunca activa Luna ni ejecuta al importarse."""
    return WorkerNormalizacion(*args, **kwargs)
