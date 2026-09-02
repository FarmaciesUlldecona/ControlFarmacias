from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import time
from typing import Any, Callable

from .adaptadores.registro import entrada_por_adapter_id
from .autoridad import AutoridadExtraccion, autoridad_productiva_habilitada
from .comparador import comparar_pipeline_local
from .configuracion import ConfiguracionShadow
from .observabilidad import DestinoObservabilidadLocal, ObservabilidadArchivoLocal
from .servicio import MotorDocumentoLocal, hash_funcional


class MotorShadowLocalAdaptativo:
    """Ejecuta PDFium nativo y reintenta con OCR solo ante PENDIENTE_OCR."""

    def __init__(
        self,
        motor_nativo: MotorDocumentoLocal | None = None,
        fabrica_motor_ocr: Callable[[], MotorDocumentoLocal] | None = None,
    ) -> None:
        if motor_nativo is None:
            from .backend.pdfium import BackendPdfium

            motor_nativo = MotorDocumentoLocal(BackendPdfium())
        self.motor_nativo = motor_nativo
        self._fabrica_motor_ocr = fabrica_motor_ocr or _crear_motor_ocr
        self._motor_ocr: MotorDocumentoLocal | None = None

    def extraer(self, ruta: str | Path):
        resultado = self.motor_nativo.extraer(ruta)
        requiere_ocr = any(
            incidencia.get("codigo") == "PENDIENTE_OCR"
            for incidencia in resultado.incidencias
        )
        if not requiere_ocr:
            return resultado
        if self._motor_ocr is None:
            self._motor_ocr = self._fabrica_motor_ocr()
        return self._motor_ocr.extraer(ruta)


def _crear_motor_ocr() -> MotorDocumentoLocal:
    from .backend.pdfium import BackendPdfiumConOcr

    return MotorDocumentoLocal(BackendPdfiumConOcr())


def crear_motor_shadow_local() -> MotorShadowLocalAdaptativo:
    return MotorShadowLocalAdaptativo()


def ejecutar_con_shadow_local(
    procesador_oficial: Callable[..., Any],
    ruta_pdf: str | Path,
    *args: Any,
    configuracion: ConfiguracionShadow | None = None,
    motor_local: Any | None = None,
    observabilidad: DestinoObservabilidadLocal | None = None,
    **kwargs: Any,
) -> Any:
    """Ejecuta el motor local lateralmente y devuelve siempre la salida oficial."""
    resultado_oficial = procesador_oficial(ruta_pdf, *args, **kwargs)
    return ejecutar_shadow_local_sobre_resultado(
        resultado_oficial,
        ruta_pdf,
        configuracion=configuracion,
        motor_local=motor_local,
        observabilidad=observabilidad,
    )


def ejecutar_shadow_local_sobre_resultado(
    resultado_oficial: Any,
    ruta_pdf: str | Path,
    *,
    configuracion: ConfiguracionShadow | None = None,
    motor_local: Any | None = None,
    observabilidad: DestinoObservabilidadLocal | None = None,
) -> Any:
    """Bridge multiproveedor: registra comparacion sin aplicar resultado local."""
    config = configuracion or ConfiguracionShadow.desde_entorno()
    if not config.habilitado:
        return resultado_oficial
    motor_local = motor_local or crear_motor_shadow_local()
    destino = observabilidad
    if destino is None and config.directorio_observabilidad is not None:
        destino = ObservabilidadArchivoLocal(config.directorio_observabilidad)
    inicio = time.perf_counter()
    sha = _sha_local(ruta_pdf)
    try:
        resultado = motor_local.extraer(ruta_pdf)
        adaptador_id = resultado.documento.get("layout")
        entrada = entrada_por_adapter_id(adaptador_id)
        registrado = entrada is not None
        shadow_permitido = bool(entrada and entrada.shadow_habilitable)
        autoridad_habilitada = bool(
            entrada and autoridad_productiva_habilitada(entrada.proveedor)
        )
        # El bridge no aplica autoridad local: este campo describe la fuente
        # de la salida efectivamente devuelta, no una autoridad configurada.
        autoridad_aplicada = (
            AutoridadExtraccion.IA
            if resultado_oficial is not None
            else AutoridadExtraccion.INDETERMINADO
        )
        familias_locales = _familias_locales(resultado)
        comparacion = comparar_pipeline_local(resultado_oficial, resultado)
        layouts_documentales = sorted({
            factura["layout"]
            for factura in resultado.facturas
            if factura.get("layout")
        })
        evento = {
            "tipo": "SHADOW_LOCAL_RESULTADO",
            "timestamp_local": datetime.now(timezone.utc).isoformat(),
            "sha_documento": sha,
            "motor": resultado.motor,
            "adaptador": adaptador_id,
            "proveedor": entrada.proveedor.value if entrada else None,
            "version_adaptador": resultado.documento.get("layout_version"),
            "layouts_documentales": layouts_documentales,
            "duracion_segundos": time.perf_counter() - inicio,
            "segmentos": len(resultado.segmentos),
            "candidatos": _cantidad(resultado, "albaranes"),
            "familias_locales": familias_locales,
            "evidencias": len(resultado.evidencias),
            "incidencias": resultado.incidencias,
            "hash_funcional": hash_funcional(resultado),
            "comparacion": comparacion,
            "autoridad_aplicada": autoridad_aplicada.value,
            "salida_local_aplicada": False,
            "contrato_bridge": {
                "estado_registro": "REGISTRADO_LOCAL" if registrado else "SIN_ADAPTADOR_REGISTRADO",
                "adapter_id": adaptador_id,
                "proveedor": entrada.proveedor.value if entrada else None,
                "version": resultado.documento.get("layout_version"),
                "layout": layouts_documentales[0] if len(layouts_documentales) == 1 else None,
                "layouts": layouts_documentales,
                "shadow_habilitable": shadow_permitido,
                "shadow_ejecutado": True,
                "estado_shadow": (
                    "SHADOW_HABILITADO"
                    if registrado and shadow_permitido
                    else "SHADOW_NO_APLICABLE"
                ),
                "autoridad_productiva": autoridad_habilitada,
                "estado_autoridad": (
                    "AUTORIDAD_PRODUCTIVA_ON"
                    if autoridad_habilitada
                    else "AUTORIDAD_PRODUCTIVA_OFF"
                ),
                "backend_requerido": entrada.backend_requerido.value if entrada else None,
                "backend_ejecutado": resultado.motor.get("backend"),
                "resultado_local_disponible": registrado and shadow_permitido,
                "incidencias": resultado.incidencias,
                "comparabilidad": "COMPARACION_GENERADA",
                "provenance": {
                    "registro": "REGISTRO_ADAPTADORES_LOCALES",
                    "seleccion_por_contenido_y_geometria": True,
                    "filename_usado_en_routing": False,
                    "hash_usado_en_routing": False,
                    "salida_oficial_preservada": True,
                },
            },
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
            "salida_local_aplicada": False,
        }
        if destino is not None:
            try:
                destino.registrar(evento)
            except Exception:
                pass
    return resultado_oficial


def ejecutar_con_shadow_cofares(
    procesador_oficial: Callable[..., Any],
    ruta_pdf: str | Path,
    *args: Any,
    configuracion: ConfiguracionShadow | None = None,
    motor_local: Any | None = None,
    observabilidad: DestinoObservabilidadLocal | None = None,
    **kwargs: Any,
) -> Any:
    """LEGACY_COMPATIBILITY del nombre historico; ahora es multiproveedor."""
    return ejecutar_con_shadow_local(
        procesador_oficial,
        ruta_pdf,
        *args,
        configuracion=configuracion,
        motor_local=motor_local,
        observabilidad=observabilidad,
        **kwargs,
    )


def ejecutar_shadow_cofares_sobre_resultado(
    resultado_oficial: Any,
    ruta_pdf: str | Path,
    *,
    configuracion: ConfiguracionShadow | None = None,
    motor_local: Any | None = None,
    observabilidad: DestinoObservabilidadLocal | None = None,
) -> Any:
    """LEGACY_COMPATIBILITY del nombre historico; ahora es multiproveedor."""
    return ejecutar_shadow_local_sobre_resultado(
        resultado_oficial,
        ruta_pdf,
        configuracion=configuracion,
        motor_local=motor_local,
        observabilidad=observabilidad,
    )


def _cantidad(resultado, nombre: str) -> int:
    superior = list(getattr(resultado, nombre))
    internas = [item for factura in resultado.facturas for item in factura[nombre]]
    if not resultado.facturas:
        return len(superior)
    return len(internas) if superior == internas else len(superior) + len(internas)


def _familias_locales(resultado) -> dict[str, Any]:
    familias = {
        "cabecera": bool(resultado.cabecera) or bool(resultado.facturas),
        "albaranes": _cantidad(resultado, "albaranes"),
        "movimientos": _cantidad(resultado, "movimientos"),
        "impuestos": _cantidad(resultado, "impuestos"),
        "vencimientos": _cantidad(resultado, "vencimientos"),
        "otros": _cantidad(resultado, "otros"),
    }
    if resultado.facturas:
        familias["facturas"] = len(resultado.facturas)
    return familias


def _sha_local(ruta: str | Path) -> str:
    calculador = hashlib.sha256()
    with Path(ruta).open("rb") as stream:
        for bloque in iter(lambda: stream.read(1024 * 1024), b""):
            calculador.update(bloque)
    return calculador.hexdigest()
