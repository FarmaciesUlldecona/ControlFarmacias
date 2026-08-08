"""Construccion comun de la parte documental basica de una factura."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import re
from typing import Any

from src.facturas.normalizadores.comun import (
    NivelIncidencia,
    RegistroIncidencias,
    fecha_visible_a_iso,
    normalizar_identificador,
    valor_visible,
)
from src.facturas.normalizadores.configuracion import ConfiguracionProveedor
from src.models.factura import FacturaNormalizada


_IDENTIFICADOR_FISCAL_ES_CON_PREFIJO = re.compile(
    r"^ES\s*([A-Z]\d{8})$", re.IGNORECASE
)


def paginas_desde_metadatos(metadatos: Mapping[str, Any]) -> tuple[int, int]:
    """Obtiene el intervalo original solo de metadatos tecnicos fiables."""
    paginas = metadatos.get("paginas_originales")
    if (
        isinstance(paginas, list)
        and len(paginas) == 2
        and all(
            isinstance(numero, int)
            and not isinstance(numero, bool)
            and numero >= 1
            for numero in paginas
        )
        and paginas[1] >= paginas[0]
    ):
        return paginas[0], paginas[1]

    numero_paginas = metadatos.get("numero_paginas")
    if (
        isinstance(numero_paginas, int)
        and not isinstance(numero_paginas, bool)
        and numero_paginas >= 1
    ):
        return 1, numero_paginas
    raise ValueError("Los metadatos tecnicos deben declarar paginas originales validas.")


def normalizar_identificador_fiscal_es(
    valor: Any,
    incidencias: RegistroIncidencias,
    *,
    etiqueta_visible: str,
) -> str | None:
    """Retira ES solo ante la forma fiscal espanola completa y demostrada."""
    identificador = normalizar_identificador(valor)
    if identificador is None:
        return None
    coincidencia = _IDENTIFICADOR_FISCAL_ES_CON_PREFIJO.fullmatch(
        identificador.replace(" ", "")
    )
    if coincidencia is None:
        return identificador
    normalizado = coincidencia.group(1).upper()
    incidencias.agregar(
        campo="proveedor_cif",
        tipo="PREFIJO_PAIS_ELIMINADO",
        nivel=NivelIncidencia.AVISO,
        descripcion=f"El {etiqueta_visible} visible incluye el prefijo de pais ES.",
        datos_visibles={"valor": identificador},
        decision=f"Se conserva el identificador fiscal nacional {normalizado}.",
    )
    return normalizado


def construir_cabecera_documental(
    general: Mapping[str, Any],
    metadatos: Mapping[str, Any],
    configuracion: ConfiguracionProveedor,
    incidencias: RegistroIncidencias,
    *,
    tipo_documento: str | None,
    proveedor_nombre: str | None,
    normalizar_cif: Callable[[Any, RegistroIncidencias], str | None],
) -> dict[str, Any]:
    """Normaliza campos comunes sin decidir reglas del tipo documental."""
    pagina_inicio, pagina_fin = paginas_desde_metadatos(metadatos)
    fecha_visible = valor_visible(general.get("fecha_factura"))
    return {
        "tipo_documento": tipo_documento,
        "categoria": configuracion.categoria,
        "requiere_conciliacion_albaranes": (
            configuracion.requiere_conciliacion_albaranes
        ),
        "pagina_inicio": pagina_inicio,
        "pagina_fin": pagina_fin,
        "proveedor_nombre": proveedor_nombre,
        "proveedor_cif": normalizar_cif(
            valor_visible(general.get("proveedor_cif")), incidencias
        ),
        "numero_factura": normalizar_identificador(
            valor_visible(general.get("numero_factura"))
        ),
        "fecha_factura": (
            fecha_visible_a_iso(str(fecha_visible))
            if fecha_visible is not None
            else None
        ),
    }


def normalizar_proveedor_documental(
    campo: Any,
    configuracion: ConfiguracionProveedor,
) -> tuple[str | None, str | None, bool]:
    """Canoniza solo coincidencias exactas y devuelve el texto visible auditado."""
    visible = valor_visible(campo)
    normalizado = configuracion.alias_proveedor.normalizar(visible)
    return (
        visible,
        normalizado,
        normalizado == configuracion.proveedor_nombre_canonico,
    )


def construir_destinatario(
    destinatario_visible: Mapping[str, Any] | None,
    configuracion: ConfiguracionProveedor,
) -> dict[str, str | None]:
    """Separa datos documentales visibles de identificadores internos."""
    visible = destinatario_visible or {}
    return {
        "id_farmacia": normalizar_identificador(configuracion.id_farmacia),
        "nombre": valor_visible(visible.get("nombre")),
        "cif": normalizar_identificador(valor_visible(visible.get("cif"))),
        "metodo_identificacion": configuracion.metodo_identificacion_farmacia,
    }


def ensamblar_factura_normalizada(
    *,
    cabecera: Mapping[str, Any],
    base_imponible_total: Any,
    iva_total: Any,
    recargo_equivalencia_total: Any,
    importe_total: Any,
    vencimientos: list[dict[str, Any]],
    impuestos: list[dict[str, Any]],
    albaranes: list[dict[str, Any]],
    ajustes: list[dict[str, Any]],
    destinatario: Mapping[str, Any] | None,
    incidencias: RegistroIncidencias,
    version_normalizador: str,
    archivo_origen: str,
    procedencia_bloques: Mapping[str, str],
    configuracion: ConfiguracionProveedor,
    validaciones_monetarias: list[dict[str, Any]],
    fecha_ejecucion: datetime | None = None,
    fecha_cargo: str | None = None,
    periodo_facturacion_inicio: str | None = None,
    periodo_facturacion_fin: str | None = None,
    nota_revision: str | None = None,
    configuracion_adicional: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Ensambla bloques ya normalizados sin interpretarlos ni corregirlos."""
    factura = {
        **cabecera,
        "base_imponible_total": base_imponible_total,
        "iva_total": iva_total,
        "recargo_equivalencia_total": recargo_equivalencia_total,
        "importe_total": importe_total,
        "vencimientos": vencimientos,
        "impuestos": impuestos,
        "albaranes": albaranes,
        "ajustes": ajustes,
        "destinatario": destinatario,
        "fecha_cargo": fecha_cargo,
        "periodo_facturacion_inicio": periodo_facturacion_inicio,
        "periodo_facturacion_fin": periodo_facturacion_fin,
        "nota_revision": nota_revision,
    }

    modelo = FacturaNormalizada.desde_diccionario(factura)
    for error in modelo.validar():
        incidencias.agregar(
            campo="factura",
            tipo="ESTRUCTURA_INCOMPLETA",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion=error,
            datos_visibles=None,
            decision="Se conserva null; no se completa el campo.",
        )

    configuracion_aplicada = {
        "farmacia": configuracion.farmacia,
        "categoria": configuracion.categoria,
        "requiere_conciliacion_albaranes": (
            configuracion.requiere_conciliacion_albaranes
        ),
        "destinatario_id_farmacia": configuracion.id_farmacia,
        "destinatario_metodo_identificacion": (
            configuracion.metodo_identificacion_farmacia
        ),
    }
    if configuracion_adicional:
        configuracion_aplicada.update(configuracion_adicional)

    instante = fecha_ejecucion or datetime.now(timezone.utc)
    return {
        "version_normalizador": version_normalizador,
        "fecha_ejecucion": instante.astimezone(timezone.utc).isoformat(),
        "archivo_origen": archivo_origen,
        "paginas_originales": [
            factura["pagina_inicio"],
            factura["pagina_fin"],
        ],
        "resultado_normalizado": factura,
        "procedencia_bloques": dict(procedencia_bloques),
        "configuracion_interna_aplicada": configuracion_aplicada,
        "validaciones_monetarias": validaciones_monetarias,
    }
