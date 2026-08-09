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
    construir_ajustes,
    construir_albaranes,
    construir_cabecera_documental,
    construir_destinatario,
    construir_impuestos,
    construir_vencimientos,
    ensamblar_factura_normalizada,
    normalizar_identificador_fiscal_es,
    normalizar_nota_vencimiento,
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


def _fecha_opcional_visible(
    campo: Any,
    nombre: str,
    incidencias: RegistroIncidencias,
) -> str | None:
    try:
        return fecha_visible(campo)
    except ValueError:
        incidencias.agregar(
            campo=nombre,
            tipo="FECHA_VISIBLE_NO_INTERPRETABLE",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="El valor temporal visible no es una fecha completa autorizada.",
            datos_visibles={"valor": valor_visible(campo)},
            decision=f"{nombre} permanece en null; no se deriva una fecha.",
        )
        return None


def _interpretar_ajustes(
    filas: Any,
    incidencias: RegistroIncidencias,
) -> list[dict[str, Any]]:
    if not filas:
        return []
    if not isinstance(filas, list):
        return _bloquear_coleccion_no_interpretable(
            "ajustes", filas, incidencias
        )

    interpretadas: list[dict[str, Any]] = []
    for indice, fila in enumerate(filas):
        if not isinstance(fila, dict):
            motivo = "La fila de ajuste no tiene una estructura de campos valida."
            datos_visibles = None
        else:
            try:
                tipo = valor_visible(fila.get("tipo_ajuste"))
                descripcion = valor_visible(fila.get("descripcion"))
                importe = decimal_visible(fila.get("importe"))
                incluido_en_base = valor_visible(fila.get("incluido_en_base"))
                incluido_en_total = valor_visible(fila.get("incluido_en_total"))
            except ValueError:
                motivo = "La fila contiene un importe visible no interpretable."
                datos_visibles = {"indice": indice}
            else:
                tipos_validos = tipo is None or isinstance(tipo, str)
                descripcion_valida = descripcion is None or isinstance(
                    descripcion, str
                )
                inclusiones_validas = all(
                    valor is None or isinstance(valor, bool)
                    for valor in (incluido_en_base, incluido_en_total)
                )
                if tipos_validos and descripcion_valida and inclusiones_validas:
                    interpretadas.append(
                        {
                            "tipo_ajuste": tipo,
                            "descripcion": descripcion,
                            "importe": importe,
                            "incluido_en_base": incluido_en_base,
                            "incluido_en_total": incluido_en_total,
                            "procedencia": procedencia_visible(),
                        }
                    )
                    continue
                motivo = "La fila contiene tipos incompatibles con el contrato de ajuste."
                datos_visibles = {"indice": indice}

        incidencias.agregar(
            campo=f"ajustes[{indice}]",
            tipo="AJUSTE_ESTANDAR_NO_INTERPRETABLE",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion=motivo,
            datos_visibles=datos_visibles,
            decision="La fila no se incorpora a los ajustes normalizados.",
        )

    return construir_ajustes(interpretadas)


_CAMPOS_ALBARAN_ESTANDAR = frozenset(
    {
        "orden",
        "numero_albaran",
        "fecha_albaran",
        "tipo_movimiento",
        "descripcion",
        "importe_base",
        "importe_total",
    }
)


def _interpretar_albaranes(
    filas: Any,
    incidencias: RegistroIncidencias,
) -> list[dict[str, Any]]:
    if not filas:
        return []
    if not isinstance(filas, list):
        return _bloquear_coleccion_no_interpretable(
            "albaranes", filas, incidencias
        )

    interpretadas: list[dict[str, Any]] = []
    for indice, fila in enumerate(filas):
        motivo = None
        if not isinstance(fila, dict):
            motivo = "La fila de albaran no tiene una estructura de campos valida."
        elif not set(fila).issubset(_CAMPOS_ALBARAN_ESTANDAR):
            motivo = "La fila contiene campos ajenos al contrato estandar de albaran."
        else:
            try:
                numero = valor_visible(fila.get("numero_albaran"))
                fecha = fecha_visible(fila.get("fecha_albaran"))
                movimiento = valor_visible(fila.get("tipo_movimiento"))
                descripcion = valor_visible(fila.get("descripcion"))
                base = decimal_visible(fila.get("importe_base"))
                total = decimal_visible(fila.get("importe_total"))
            except ValueError:
                motivo = "La fila contiene una fecha o importe visible no interpretable."
            else:
                numero_valido = numero is None or (
                    isinstance(numero, (str, int))
                    and not isinstance(numero, bool)
                )
                textos_validos = numero_valido and all(
                    valor is None or isinstance(valor, str)
                    for valor in (movimiento, descripcion)
                )
                if textos_validos:
                    interpretadas.append(
                        {
                            "numero_albaran": numero,
                            "fecha_albaran": fecha,
                            "tipo_movimiento": movimiento,
                            "descripcion": descripcion,
                            "importe_base": base,
                            "importe_total": total,
                            "procedencia": procedencia_visible(),
                        }
                    )
                    continue
                motivo = "La fila contiene tipos incompatibles con el contrato de albaran."

        incidencias.agregar(
            campo=f"albaranes[{indice}]",
            tipo="ALBARAN_ESTANDAR_NO_INTERPRETABLE",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion=motivo,
            datos_visibles={"indice": indice},
            decision="La fila no se incorpora a los albaranes normalizados.",
        )

    return construir_albaranes(interpretadas)


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
                "nota": normalizar_nota_vencimiento(
                    valor_visible(fila.get("nota"))
                ),
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
    albaranes = _interpretar_albaranes(general.get("albaranes"), incidencias)
    ajustes = _interpretar_ajustes(general.get("ajustes"), incidencias)
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
        fecha_cargo=_fecha_opcional_visible(
            general.get("fecha_cargo"), "fecha_cargo", incidencias
        ),
        periodo_facturacion_inicio=_fecha_opcional_visible(
            general.get("periodo_facturacion_inicio"),
            "periodo_facturacion_inicio",
            incidencias,
        ),
        periodo_facturacion_fin=_fecha_opcional_visible(
            general.get("periodo_facturacion_fin"),
            "periodo_facturacion_fin",
            incidencias,
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
