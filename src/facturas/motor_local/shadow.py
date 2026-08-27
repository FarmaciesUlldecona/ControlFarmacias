from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import time
from typing import Any, Callable

from .configuracion import ConfiguracionShadow
from .autoridad import autoridad_cofares
from .comparador import comparar_pipeline_local
from .observabilidad import DestinoObservabilidadLocal, ObservabilidadArchivoLocal
from .servicio import MotorDocumentoLocal, hash_funcional


def ejecutar_con_shadow_cofares(
    procesador_oficial: Callable[..., Any],
    ruta_pdf: str | Path,
    *args: Any,
    configuracion: ConfiguracionShadow | None = None,
    motor_local: MotorDocumentoLocal | None = None,
    observabilidad: DestinoObservabilidadLocal | None = None,
    **kwargs: Any,
) -> Any:
    """Devuelve siempre la salida oficial; el shadow es lateral y sin autoridad."""
    resultado_oficial = procesador_oficial(ruta_pdf, *args, **kwargs)
    return ejecutar_shadow_cofares_sobre_resultado(
        resultado_oficial, ruta_pdf, configuracion=configuracion,
        motor_local=motor_local, observabilidad=observabilidad,
    )


def ejecutar_shadow_cofares_sobre_resultado(
    resultado_oficial: Any,
    ruta_pdf: str | Path,
    *,
    configuracion: ConfiguracionShadow | None = None,
    motor_local: MotorDocumentoLocal | None = None,
    observabilidad: DestinoObservabilidadLocal | None = None,
) -> Any:
    """Ejecuta el lateral local sobre una salida ya obtenida, sin sustituirla."""
    config = configuracion or ConfiguracionShadow.desde_entorno()
    if not config.habilitado:
        return resultado_oficial
    if motor_local is None:
        from .backend.pdfium import BackendPdfium

        motor_local = MotorDocumentoLocal(BackendPdfium())
    destino = observabilidad
    if destino is None and config.directorio_observabilidad is not None:
        destino = ObservabilidadArchivoLocal(config.directorio_observabilidad)
    inicio = time.perf_counter()
    sha = _sha_local(ruta_pdf)
    try:
        resultado = motor_local.extraer(ruta_pdf)
        adaptador_id = resultado.documento.get("layout")
        if adaptador_id not in {"cofares-local", "hefame-local", "fedefarma-local"}:
            return resultado_oficial
        familias_locales = {
            "cabecera": bool(resultado.cabecera) or bool(resultado.facturas),
            "albaranes": len(resultado.albaranes) + sum(len(f["albaranes"]) for f in resultado.facturas),
            "movimientos": len(resultado.movimientos) + sum(len(f["movimientos"]) for f in resultado.facturas),
            "impuestos": len(resultado.impuestos) + sum(len(f["impuestos"]) for f in resultado.facturas),
            "vencimientos": len(resultado.vencimientos) + sum(len(f["vencimientos"]) for f in resultado.facturas),
            "otros": len(resultado.otros) + sum(len(f["otros"]) for f in resultado.facturas),
        }
        if resultado.facturas:
            familias_locales["facturas"] = len(resultado.facturas)
        evento = {
            "tipo": "SHADOW_LOCAL_RESULTADO",
            "timestamp_local": datetime.now(timezone.utc).isoformat(),
            "sha_documento": sha,
            "motor": resultado.motor,
            "adaptador": resultado.documento.get("layout"),
            "version_adaptador": resultado.documento.get("layout_version"),
            "duracion_segundos": time.perf_counter() - inicio,
            "segmentos": len(resultado.segmentos),
            "candidatos": len(resultado.albaranes) + sum(len(f["albaranes"]) for f in resultado.facturas),
            "familias_locales": familias_locales,
            "evidencias": len(resultado.evidencias),
            "incidencias": resultado.incidencias,
            "hash_funcional": hash_funcional(resultado),
            "comparacion": comparar_pipeline_local(resultado_oficial, resultado),
            "autoridad_aplicada": (
                autoridad_cofares(salida_oficial_disponible=resultado_oficial is not None).value
                if adaptador_id == "cofares-local" else "IA"
            ),
            "salida_local_aplicada": False,
        }
        if destino is not None:
            destino.registrar(evento)
    except Exception as error:
        evento = {
            "tipo": "SHADOW_LOCAL_ERROR",
            "timestamp_local": datetime.now(timezone.utc).isoformat(),
            "sha_documento": sha,
            "adaptador": "motor-local",
            "version_adaptador": None,
            "fase": "EXTRACCION_LOCAL",
            "excepcion": f"{type(error).__name__}: {error}",
        }
        if destino is not None:
            try:
                destino.registrar(evento)
            except Exception:
                pass
    return resultado_oficial


def _sha_local(ruta: str | Path) -> str:
    calculador = hashlib.sha256()
    with Path(ruta).open("rb") as stream:
        for bloque in iter(lambda: stream.read(1024 * 1024), b""):
            calculador.update(bloque)
    return calculador.hexdigest()
