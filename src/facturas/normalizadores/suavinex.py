"""Normalizador determinista Suavinex v1 para la factura actual."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from src.facturas.normalizadores.comun import (
    EstadoValidacion,
    NivelIncidencia,
    RegistroIncidencias,
    aplicar_regla_determinista,
    decimal_visible,
    fecha_visible,
    normalizar_identificador,
    porcentaje_visible,
    procedencia_determinista,
    procedencia_visible,
    registrar_validacion_monetaria,
    validar_suma_monetaria,
    valor_visible,
)
from src.facturas.normalizadores.configuracion import ConfiguracionProveedor
from src.facturas.normalizadores.documento import (
    construir_cabecera_documental,
    construir_destinatario,
    ensamblar_factura_normalizada,
    normalizar_identificador_fiscal_es,
    normalizar_proveedor_documental,
)


VERSION_NORMALIZADOR = "suavinex_v1"
NOMBRE_CANONICO_SUAVINEX = "SUAVINEX GROUP, S.L."
TOLERANCIA_MONETARIA = Decimal("0.01")
_CENTIMOS = Decimal("0.01")
_DESCRIPCION_VALIDACION = (
    "La validacion monetaria no ha podido confirmarse correctamente."
)
_DECISION_VALIDACION = "No se modifican importes para hacerlos cuadrar."


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguracionSuavinex(ConfiguracionProveedor):
    proveedor_nombre_canonico: str = NOMBRE_CANONICO_SUAVINEX
    aliases: tuple[str, ...] = ("SUAVINEX", "SUAVINEX GROUP SL")
    albaran_unico_abarca_factura: bool | None = None


def _cuota(base: Decimal, porcentaje: Decimal) -> Decimal:
    return (base * porcentaje / Decimal("100")).quantize(
        _CENTIMOS, rounding=ROUND_HALF_UP
    )


def _importe_es(valor: Decimal) -> str:
    return f"{valor:.2f}".replace(".", ",")


def _normalizar_fiscalidad(
    filas: list[dict[str, Any]],
    incidencias: RegistroIncidencias,
) -> tuple[list[dict[str, Any]], Decimal | None, Decimal | None, Decimal | None]:
    if len(filas) != 1:
        incidencias.agregar(
            campo="impuestos",
            tipo="ESTRUCTURA_FISCAL_SUAVINEX_NO_DEMOSTRADA",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="La regla fiscal Suavinex exige exactamente un tramo visible.",
            datos_visibles={"cantidad_filas": len(filas)},
            decision="No se separan cuotas fiscales por plausibilidad.",
        )
        return [], None, None, None

    fila = filas[0]
    base = decimal_visible(fila.get("base_imponible"))
    tipo_iva = porcentaje_visible(fila.get("tipo_iva"))
    tipo_recargo = porcentaje_visible(fila.get("tipo_recargo_equivalencia"))
    cuota_agregada = decimal_visible(fila.get("cuota_iva"))
    cuota_recargo_visible = decimal_visible(fila.get("cuota_recargo_equivalencia"))
    regla = aplicar_regla_determinista(
        nombre="separacion_cuota_fiscal_agregada_suavinex",
        version=VERSION_NORMALIZADOR,
        precondiciones={
            "un_solo_tramo": len(filas) == 1,
            "cuota_recargo_no_separada": cuota_recargo_visible is None,
        },
        entradas={
            "base": base,
            "tipo_iva": tipo_iva,
            "tipo_recargo": tipo_recargo,
            "cuota_agregada": cuota_agregada,
        },
        derivar=lambda datos: (
            _cuota(datos["base"], datos["tipo_iva"]),
            _cuota(datos["base"], datos["tipo_recargo"]),
        ),
    )
    if not regla.aplicada:
        incidencias.agregar(
            campo="impuestos",
            tipo="SEPARACION_FISCAL_BLOQUEADA",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="Faltan precondiciones visibles para separar IVA y recargo.",
            datos_visibles={"bloqueos": regla.bloqueos},
            decision="Las cuotas IVA y recargo permanecen en null.",
        )
        return [], None, None, cuota_agregada

    cuota_iva, cuota_recargo = regla.valor
    comprobacion = validar_suma_monetaria(
        [cuota_iva, cuota_recargo],
        cuota_agregada,
        tolerancia=TOLERANCIA_MONETARIA,
    )
    if comprobacion.estado is not EstadoValidacion.OK:
        incidencias.agregar(
            campo="impuestos",
            tipo="CUOTA_FISCAL_AGREGADA_NO_CUADRA",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="Las cuotas calculadas no reproducen la cuota agregada visible.",
            datos_visibles=comprobacion.a_diccionario(),
            decision="Las cuotas IVA y recargo permanecen en null.",
        )
        return [], None, None, cuota_agregada

    incidencias.agregar(
        campo="impuestos",
        tipo="CUOTA_FISCAL_AGREGADA_SEPARADA",
        nivel=NivelIncidencia.AVISO,
        descripcion="El documento muestra una cuota conjunta de IVA y recargo.",
        datos_visibles={
            "base": base,
            "tipo_iva": tipo_iva,
            "tipo_recargo": tipo_recargo,
            "cuota_agregada": cuota_agregada,
        },
        decision=(
            f"Se calculan {cuota_iva} de IVA y {cuota_recargo} de recargo; "
            "su suma reproduce la cuota visible."
        ),
    )
    impuesto = {
        "orden": 1,
        "base_imponible": base,
        "tipo_iva": tipo_iva,
        "cuota_iva": cuota_iva,
        "tipo_recargo_equivalencia": tipo_recargo,
        "cuota_recargo_equivalencia": cuota_recargo,
        "nota": (
            "El PDF agrupa IVA y recargo en una cuota total de "
            f"{_importe_es(cuota_agregada)} €"
        ),
    }
    return [impuesto], cuota_iva, cuota_recargo, cuota_agregada


def _normalizar_vencimientos(
    filas: list[dict[str, Any]], incidencias: RegistroIncidencias
) -> list[dict[str, Any]]:
    resultado = []
    for fila in filas:
        fecha = fecha_visible(fila.get("fecha_vencimiento"))
        importe = decimal_visible(fila.get("importe"))
        if fecha is None and importe is None:
            continue
        nota_visible = valor_visible(fila.get("nota"))
        nota = nota_visible
        if isinstance(nota_visible, str) and nota_visible.casefold().startswith(
            "giro domiciliado"
        ):
            nota = None
            incidencias.agregar(
                campo=f"vencimientos[{len(resultado)}].nota",
                tipo="FORMA_PAGO_NO_ES_NOTA_VENCIMIENTO",
                nivel=NivelIncidencia.AVISO,
                descripcion="La forma de pago visible no describe el vencimiento.",
                datos_visibles={"valor": nota_visible},
                decision="La nota del vencimiento permanece en null.",
            )
        if importe is None:
            incidencias.agregar(
                campo=f"vencimientos[{len(resultado)}].importe",
                tipo="IMPORTE_VENCIMIENTO_NO_VISIBLE",
                nivel=NivelIncidencia.REVISION_MANUAL,
                descripcion="El vencimiento no tiene un importe visible con evidencia.",
                datos_visibles={"fecha_vencimiento": fecha},
                decision="No se asigna el total de factura al vencimiento.",
            )
        resultado.append(
            {
                "orden": len(resultado) + 1,
                "fecha_vencimiento": fecha,
                "importe": importe,
                "nota": nota,
            }
        )
    return resultado


def _normalizar_albaranes(
    filas: list[dict[str, Any]],
    tipo_documento: str | None,
    base_factura: Decimal | None,
    total_factura: Decimal | None,
    configuracion: ConfiguracionSuavinex,
    incidencias: RegistroIncidencias,
) -> list[dict[str, Any]]:
    resultado = []
    for fila in filas:
        numero = normalizar_identificador(valor_visible(fila.get("numero_albaran")))
        fecha = fecha_visible(fila.get("fecha_albaran"))
        if numero is None and fecha is None:
            continue
        descripcion_visible = valor_visible(fila.get("descripcion"))
        descripcion = descripcion_visible
        if isinstance(descripcion_visible, str) and descripcion_visible.casefold().startswith(
            "pedido:"
        ):
            descripcion = None
            incidencias.agregar(
                campo=f"albaranes[{len(resultado)}].descripcion",
                tipo="REFERENCIA_PEDIDO_BLOQUEADA_COMO_DESCRIPCION_ALBARAN",
                nivel=NivelIncidencia.AVISO,
                descripcion="La referencia de pedido es un concepto distinto del albaran.",
                datos_visibles={"valor": descripcion_visible},
                decision="La descripcion del albaran permanece en null.",
            )

        movimiento = "CARGO" if tipo_documento == "FACTURA" else None
        regla_importes = aplicar_regla_determinista(
            nombre="importes_factura_para_albaran_unico_suavinex",
            version=VERSION_NORMALIZADOR,
            precondiciones={
                "factura_visible": tipo_documento == "FACTURA",
                "un_albaran_visible": len(filas) == 1,
                "relacion_documental_configurada": (
                    configuracion.albaran_unico_abarca_factura
                ),
            },
            entradas={"base_factura": base_factura, "total_factura": total_factura},
            derivar=lambda datos: (datos["base_factura"], datos["total_factura"]),
        )
        importe_base = None
        importe_total = None
        if regla_importes.aplicada:
            importe_base, importe_total = regla_importes.valor
            incidencias.agregar(
                campo=f"albaranes[{len(resultado)}].importes",
                tipo="IMPORTES_ASOCIADOS_A_ALBARAN_UNICO",
                nivel=NivelIncidencia.AVISO,
                descripcion="La configuracion confirma que el unico bloque de albaran abarca la factura.",
                datos_visibles={"numero_albaran": numero, "cantidad_albaranes": 1},
                decision="Se asocian la base y el total visibles de la factura.",
            )
        else:
            incidencias.agregar(
                campo=f"albaranes[{len(resultado)}].importes",
                tipo="RELACION_IMPORTES_ALBARAN_NO_DEMOSTRADA",
                nivel=NivelIncidencia.REVISION_MANUAL,
                descripcion="No se cumplen todas las precondiciones para asociar importes.",
                datos_visibles={"bloqueos": regla_importes.bloqueos},
                decision="Los importes del albaran permanecen en null.",
            )
        resultado.append(
            {
                "orden": len(resultado) + 1,
                "numero_albaran": numero,
                "fecha_albaran": fecha,
                "tipo_movimiento": movimiento,
                "descripcion": descripcion,
                "importe_base": importe_base,
                "importe_total": importe_total,
                "procedencia": {
                    "numero_y_fecha": procedencia_visible(),
                    "tipo_movimiento": (
                        procedencia_determinista(
                            "movimiento_segun_tipo_documento_visible",
                            VERSION_NORMALIZADOR,
                        )
                        if movimiento
                        else None
                    ),
                    "importes": (
                        regla_importes.procedencia.a_diccionario()
                        if regla_importes.procedencia
                        else None
                    ),
                },
            }
        )
    return resultado


def _normalizar_ajustes(
    filas: list[dict[str, Any]], incidencias: RegistroIncidencias
) -> list[dict[str, Any]]:
    resultado = []
    for fila in filas:
        tipo_visible = valor_visible(fila.get("tipo_ajuste"))
        importe = decimal_visible(fila.get("importe"))
        if tipo_visible is None and importe is None:
            continue
        es_punto_verde = (
            isinstance(tipo_visible, str)
            and " ".join(tipo_visible.split()).casefold() == "infor.pto.verde"
        )
        if es_punto_verde:
            incidencias.agregar(
                campo=f"ajustes[{len(resultado)}]",
                tipo="PUNTO_VERDE_INFORMATIVO_NORMALIZADO",
                nivel=NivelIncidencia.AVISO,
                descripcion="El concepto visible identifica informacion de punto verde.",
                datos_visibles={"tipo": tipo_visible, "importe": importe},
                decision="Se clasifica como OTRO y se conserva como incluido en base y total.",
            )
        resultado.append(
            {
                "orden": len(resultado) + 1,
                "tipo_ajuste": "OTRO" if es_punto_verde else None,
                "descripcion": (
                    "Información punto verde"
                    if es_punto_verde
                    else valor_visible(fila.get("descripcion"))
                ),
                "importe": importe,
                "incluido_en_base": True if es_punto_verde else None,
                "incluido_en_total": True if es_punto_verde else None,
                "procedencia": (
                    procedencia_determinista(
                        "clasificacion_punto_verde_suavinex", VERSION_NORMALIZADOR
                    )
                    if es_punto_verde
                    else None
                ),
            }
        )
    return resultado


def normalizar_suavinex(
    extraccion_general: dict[str, Any],
    metadatos_tecnicos: dict[str, Any],
    configuracion: ConfiguracionSuavinex,
    fecha_ejecucion: datetime | None = None,
    *,
    archivo_origen: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    general = extraccion_general.get("factura", extraccion_general)
    incidencias = RegistroIncidencias()

    tipo_visible = valor_visible(general.get("tipo_documento"))
    tipo_documento = "FACTURA" if tipo_visible == "FACTURA" else None
    if tipo_documento is None:
        incidencias.agregar(
            campo="tipo_documento",
            tipo="TIPO_FACTURA_NO_DEMOSTRADO",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="No existe evidencia valida y exacta de FACTURA.",
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
            tipo="PROVEEDOR_SUAVINEX_NO_RECONOCIDO",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="El nombre visible no coincide exactamente con un alias Suavinex.",
            datos_visibles={"valor": proveedor_visible},
            decision="Se conserva el texto visible sin canonizar.",
        )

    base = decimal_visible(general.get("base_imponible_total"))
    total = decimal_visible(general.get("importe_total"))
    impuestos, iva, recargo, cuota_agregada = _normalizar_fiscalidad(
        list(general.get("impuestos", [])), incidencias
    )
    vencimientos = _normalizar_vencimientos(
        list(general.get("vencimientos", [])), incidencias
    )
    albaranes = _normalizar_albaranes(
        list(general.get("albaranes", [])),
        tipo_documento,
        base,
        total,
        configuracion,
        incidencias,
    )
    ajustes = _normalizar_ajustes(list(general.get("ajustes", [])), incidencias)
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
    destinatario = construir_destinatario(general.get("destinatario"), configuracion)

    validaciones: list[dict[str, Any]] = []
    registrar_validacion_monetaria(
        validaciones,
        incidencias,
        "total_factura",
        [base, iva, recargo],
        total,
        tolerancia=TOLERANCIA_MONETARIA,
        descripcion_incidencia=_DESCRIPCION_VALIDACION,
        decision_incidencia=_DECISION_VALIDACION,
    )
    registrar_validacion_monetaria(
        validaciones,
        incidencias,
        "cuota_fiscal_agregada",
        [iva, recargo],
        cuota_agregada,
        tolerancia=TOLERANCIA_MONETARIA,
        descripcion_incidencia=_DESCRIPCION_VALIDACION,
        decision_incidencia=_DECISION_VALIDACION,
    )
    if impuestos:
        tramo = impuestos[0]
        base_tramo = tramo["base_imponible"]
        registrar_validacion_monetaria(
            validaciones,
            incidencias,
            "cuota_iva",
            [
                base_tramo * tramo["tipo_iva"] / Decimal("100")
                if base_tramo is not None and tramo["tipo_iva"] is not None
                else None
            ],
            tramo["cuota_iva"],
            tolerancia=TOLERANCIA_MONETARIA,
            descripcion_incidencia=_DESCRIPCION_VALIDACION,
            decision_incidencia=_DECISION_VALIDACION,
        )
        registrar_validacion_monetaria(
            validaciones,
            incidencias,
            "cuota_recargo_equivalencia",
            [
                base_tramo * tramo["tipo_recargo_equivalencia"] / Decimal("100")
                if base_tramo is not None
                and tramo["tipo_recargo_equivalencia"] is not None
                else None
            ],
            tramo["cuota_recargo_equivalencia"],
            tolerancia=TOLERANCIA_MONETARIA,
            descripcion_incidencia=_DESCRIPCION_VALIDACION,
            decision_incidencia=_DECISION_VALIDACION,
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
        procedencia_bloques={
            "cabecera_y_totales": "lectura_visible_luna_general",
            "fiscalidad": "regla_determinista:separacion_cuota_fiscal_agregada_suavinex",
            "paginas": "metadato_tecnico",
            "categoria": "configuracion_interna",
            "requiere_conciliacion_albaranes": "configuracion_interna",
            "destinatario.id_farmacia": "configuracion_interna",
            "destinatario.metodo_identificacion": "configuracion_interna",
            "signos": "lectura_visible_sin_regla_de_abono",
        },
        configuracion=configuracion,
        configuracion_adicional={
            "albaran_unico_abarca_factura": configuracion.albaran_unico_abarca_factura,
        },
        validaciones_monetarias=validaciones,
    )
    return resultado, incidencias.como_lista()
