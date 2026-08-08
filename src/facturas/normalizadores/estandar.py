"""Normalizador configurable para facturas con bloques visibles estandar."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.facturas.normalizadores.comun import (
    NivelIncidencia,
    RegistroIncidencias,
    decimal_visible,
    fecha_visible,
    porcentaje_visible,
    procedencia_visible,
    valor_visible,
)
from src.facturas.normalizadores.configuracion import ConfiguracionProveedor
from src.facturas.normalizadores.documento import (
    construir_cabecera_documental,
    construir_destinatario,
    construir_impuestos,
    construir_vencimientos,
    ensamblar_factura_normalizada,
    normalizar_identificador_fiscal_es,
    normalizar_proveedor_documental,
)


VERSION_NORMALIZADOR = "estandar_v1"
_TIPOS_DOCUMENTO_ADMITIDOS = frozenset({"FACTURA", "ABONO"})


def _bloquear_coleccion_no_interpretable(
    nombre: str,
    filas: Any,
    incidencias: RegistroIncidencias,
) -> list[dict[str, Any]]:
    if not filas:
        return []
    incidencias.agregar(
        campo=nombre,
        tipo=f"{nombre.upper()}_NO_INTERPRETABLES_POR_RUTA_ESTANDAR",
        nivel=NivelIncidencia.REVISION_MANUAL,
        descripcion=f"La ruta estandar no interpreta automaticamente {nombre}.",
        datos_visibles={"cantidad_filas": len(filas)} if isinstance(filas, list) else None,
        decision=f"Se devuelve {nombre}=[] para evitar crear datos no demostrados.",
    )
    return []


def normalizar_estandar(
    extraccion_general: dict[str, Any],
    metadatos_tecnicos: dict[str, Any],
    configuracion: ConfiguracionProveedor,
    fecha_ejecucion: datetime | None = None,
    *,
    archivo_origen: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normaliza campos visibles estándar sin reglas asociadas a proveedores."""
    general = extraccion_general.get("factura", extraccion_general)
    incidencias = RegistroIncidencias()

    tipo_visible = valor_visible(general.get("tipo_documento"))
    tipo_documento = (
        tipo_visible if tipo_visible in _TIPOS_DOCUMENTO_ADMITIDOS else None
    )
    if tipo_visible is not None and tipo_documento is None:
        incidencias.agregar(
            campo="tipo_documento",
            tipo="TIPO_DOCUMENTO_ESTANDAR_NO_RECONOCIDO",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="El tipo documental visible no pertenece al contrato estandar.",
            datos_visibles={"valor": tipo_visible},
            decision="tipo_documento permanece en null.",
        )

    proveedor_visible, proveedor, proveedor_reconocido = (
        normalizar_proveedor_documental(
            general.get("proveedor_nombre"), configuracion
        )
    )
    if proveedor_visible is not None and not proveedor_reconocido:
        incidencias.agregar(
            campo="proveedor_nombre",
            tipo="PROVEEDOR_CONFIGURADO_NO_RECONOCIDO",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="El nombre visible no coincide exactamente con la configuracion.",
            datos_visibles={"valor": proveedor_visible},
            decision="Se conserva el texto visible sin canonizar.",
        )

    base = decimal_visible(general.get("base_imponible_total"))
    iva = decimal_visible(general.get("iva_total"))
    recargo = decimal_visible(general.get("recargo_equivalencia_total"))
    total = decimal_visible(general.get("importe_total"))
    validaciones: list[dict[str, Any]] = []
    impuestos = construir_impuestos(
        (
            {
                "base_imponible": decimal_visible(fila.get("base_imponible")),
                "tipo_iva": porcentaje_visible(fila.get("tipo_iva")),
                "cuota_iva": decimal_visible(fila.get("cuota_iva")),
                "tipo_recargo_equivalencia": porcentaje_visible(
                    fila.get("tipo_recargo_equivalencia")
                ),
                "cuota_recargo_equivalencia": decimal_visible(
                    fila.get("cuota_recargo_equivalencia")
                ),
                "nota": valor_visible(fila.get("nota")),
                "procedencia": procedencia_visible(),
            }
            for fila in (general.get("impuestos") or [])
        ),
        validaciones=validaciones,
        incidencias=incidencias,
    )
    vencimientos = construir_vencimientos(
        (
            {
                "fecha_vencimiento": fecha_visible(fila.get("fecha_vencimiento")),
                "importe": decimal_visible(fila.get("importe")),
                "nota": valor_visible(fila.get("nota")),
                "procedencia": procedencia_visible(),
            }
            for fila in (general.get("vencimientos") or [])
        ),
        al_importe_ausente=lambda indice, vencimiento: incidencias.agregar(
            campo=f"vencimientos[{indice}].importe",
            tipo="IMPORTE_VENCIMIENTO_NO_VISIBLE",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="El vencimiento estandar no tiene un importe visible.",
            datos_visibles={
                "fecha_vencimiento": vencimiento["fecha_vencimiento"]
            },
            decision="No se asigna automaticamente el total de factura.",
        ),
    )
    albaranes = _bloquear_coleccion_no_interpretable(
        "albaranes", general.get("albaranes"), incidencias
    )
    ajustes = _bloquear_coleccion_no_interpretable(
        "ajustes", general.get("ajustes"), incidencias
    )
    cabecera = construir_cabecera_documental(
        general,
        metadatos_tecnicos,
        configuracion,
        incidencias,
        tipo_documento=tipo_documento,
        proveedor_nombre=proveedor,
        normalizar_cif=lambda valor, registro: normalizar_identificador_fiscal_es(
            valor, registro, etiqueta_visible="CIF"
        ),
    )
    destinatario = construir_destinatario(
        general.get("destinatario"), configuracion
    )

    resultado = ensamblar_factura_normalizada(
        cabecera=cabecera,
        base_imponible_total=base,
        iva_total=iva,
        recargo_equivalencia_total=recargo,
        importe_total=total,
        vencimientos=vencimientos,
        impuestos=impuestos,
        albaranes=albaranes,
        ajustes=ajustes,
        destinatario=destinatario,
        incidencias=incidencias,
        version_normalizador=VERSION_NORMALIZADOR,
        archivo_origen=archivo_origen,
        fecha_ejecucion=fecha_ejecucion,
        fecha_cargo=fecha_visible(general.get("fecha_cargo")),
        periodo_facturacion_inicio=fecha_visible(
            general.get("periodo_facturacion_inicio")
        ),
        periodo_facturacion_fin=fecha_visible(
            general.get("periodo_facturacion_fin")
        ),
        nota_revision=valor_visible(general.get("nota_revision")),
        procedencia_bloques={
            "cabecera_totales_fiscalidad_vencimientos": "lectura_visible_luna_general",
            "paginas": "metadato_tecnico",
            "categoria": "configuracion_interna",
            "requiere_conciliacion_albaranes": "configuracion_interna",
            "destinatario.id_farmacia": "configuracion_interna",
            "destinatario.metodo_identificacion": "configuracion_interna",
        },
        configuracion=configuracion,
        configuracion_adicional={
            "proveedor_nombre_canonico": configuracion.proveedor_nombre_canonico
        },
        validaciones_monetarias=validaciones,
    )
    return resultado, incidencias.como_lista()
