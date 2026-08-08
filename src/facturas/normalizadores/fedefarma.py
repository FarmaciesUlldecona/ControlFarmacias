"""Normalizador determinista FEDEFARMA v1 con fusion literal de albaranes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import re
from typing import Any

from src.facturas.normalizadores.comun import (
    AliasProveedor,
    NivelIncidencia,
    RegistroIncidencias,
    aplicar_regla_determinista,
    decimal_visible,
    fecha_visible,
    fecha_visible_a_iso,
    importe_espanol_a_decimal,
    normalizar_identificador,
    porcentaje_visible,
    procedencia_determinista,
    procedencia_visible,
    registrar_validacion_monetaria,
    valor_visible,
)
from src.facturas.normalizadores.configuracion import ConfiguracionProveedor
from src.facturas.normalizadores.documento import (
    construir_cabecera_documental,
    construir_destinatario,
    ensamblar_factura_normalizada,
    normalizar_proveedor_documental,
)


VERSION_NORMALIZADOR = "fedefarma_v1"
NOMBRE_CANONICO_FEDEFARMA = "FEDERACIÓ FARMACÈUTICA, S.COOP.C.L."
ALIAS_FEDEFARMA = AliasProveedor(
    nombre_canonico=NOMBRE_CANONICO_FEDEFARMA,
    alias=(
        "Federació Farmacèutica S.Coop.C.L.",
        "FEDERACIO FARMACEUTICA S.COOP.C.L.",
        "FEDEFARMA",
    ),
)
TOLERANCIA_MONETARIA = Decimal("0.01")
_DESCRIPCION_VALIDACION = "La validacion monetaria no se ha confirmado."
_DECISION_VALIDACION = "No se modifican cifras para forzar el cuadre."
_CIF_SEPARADO = re.compile(r"^([A-Z])-([0-9]{2})-([0-9]{6})$", re.IGNORECASE)
_ETIQUETA_ALBARAN = re.compile(
    r"^(?:albar(?:[aá]n|à)|n[ºo]\s*albar(?:[aá]n|à))\s*:\s*(.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguracionFedefarma(ConfiguracionProveedor):
    proveedor_nombre_canonico: str = NOMBRE_CANONICO_FEDEFARMA
    aliases: tuple[str, ...] = ALIAS_FEDEFARMA.alias
    usar_tablas_literales: bool | None = None


def limpiar_etiqueta_albaran(valor: str | int | None) -> str | None:
    """Separa solo etiquetas estructurales completas; no recorta prefijos arbitrarios."""
    identificador = normalizar_identificador(valor)
    if identificador is None:
        return None
    coincidencia = _ETIQUETA_ALBARAN.fullmatch(identificador)
    return coincidencia.group(1).strip() if coincidencia else identificador


def _normalizar_cif(valor: Any, incidencias: RegistroIncidencias) -> str | None:
    cif = normalizar_identificador(valor)
    if cif is None:
        return None
    coincidencia = _CIF_SEPARADO.fullmatch(cif)
    if coincidencia is None:
        return cif
    normalizado = "".join(coincidencia.groups()).upper()
    incidencias.agregar(
        campo="proveedor_cif",
        tipo="SEPARADORES_CIF_ELIMINADOS",
        nivel=NivelIncidencia.AVISO,
        descripcion="El CIF visible separa sus grupos mediante guiones tipograficos.",
        datos_visibles={"valor": cif},
        decision=f"Se conserva el identificador continuo {normalizado}.",
    )
    return normalizado


def _normalizar_impuestos(
    filas: list[dict[str, Any]], incidencias: RegistroIncidencias
) -> list[dict[str, Any]]:
    resultado = []
    for fila in filas:
        base = decimal_visible(fila.get("base_imponible"))
        cuota_iva = decimal_visible(fila.get("cuota_iva"))
        cuota_recargo = decimal_visible(fila.get("cuota_recargo_equivalencia"))
        tipo_iva = porcentaje_visible(fila.get("tipo_iva"))
        tipo_recargo = porcentaje_visible(fila.get("tipo_recargo_equivalencia"))
        importes = (base, cuota_iva, cuota_recargo)
        if all(valor == Decimal("0") for valor in importes):
            incidencias.agregar(
                campo="impuestos",
                tipo="TRAMO_FISCAL_SIN_IMPORTE_OMITIDO",
                nivel=NivelIncidencia.AVISO,
                descripcion="El tramo visible no aporta base, IVA ni recargo.",
                datos_visibles={"tipo_iva": tipo_iva, "tipo_recargo": tipo_recargo},
                decision="No se crea un tramo fiscal contable con importes cero.",
            )
            continue
        resultado.append(
            {
                "orden": len(resultado) + 1,
                "base_imponible": base,
                "tipo_iva": tipo_iva,
                "cuota_iva": cuota_iva,
                "tipo_recargo_equivalencia": tipo_recargo,
                "cuota_recargo_equivalencia": cuota_recargo,
                "nota": valor_visible(fila.get("nota")),
            }
        )
    return resultado


def _normalizar_general_albaranes(
    filas: list[dict[str, Any]], tipo_documento: str | None
) -> list[dict[str, Any]]:
    resultado = []
    for fila in filas:
        numero = limpiar_etiqueta_albaran(valor_visible(fila.get("numero_albaran")))
        fecha = fecha_visible(fila.get("fecha_albaran"))
        if numero is None and fecha is None:
            continue
        marcador = valor_visible(fila.get("tipo_movimiento"))
        movimiento = (
            "CARGO"
            if tipo_documento == "FACTURA" and marcador in {"P", "PA", "P PA"}
            else None
        )
        resultado.append(
            {
                "numero_albaran": numero,
                "fecha_albaran": fecha,
                "tipo_movimiento": movimiento,
                "descripcion": valor_visible(fila.get("descripcion")),
                "importe_base": decimal_visible(fila.get("importe_base")),
                "importe_total": decimal_visible(fila.get("importe_total")),
                "pagina": _pagina_evidencia(fila),
                "seccion": "extraccion_general",
                "procedencia": procedencia_visible("luna_general"),
            }
        )
    return resultado


def _pagina_evidencia(fila: dict[str, Any]) -> int | None:
    for campo in ("numero_albaran", "fecha_albaran", "importe_total"):
        dato = fila.get(campo)
        if not isinstance(dato, dict):
            continue
        evidencias = dato.get("evidencias") or []
        if evidencias and isinstance(evidencias[0], dict):
            pagina = evidencias[0].get("pagina")
            if isinstance(pagina, int) and not isinstance(pagina, bool):
                return pagina
    return None


def _normalizar_literal_albaranes(
    transcripcion: dict[str, Any], incidencias: RegistroIncidencias
) -> list[dict[str, Any]]:
    resultado = []
    for indice, fila in enumerate(transcripcion.get("filas", []), start=1):
        numero = limpiar_etiqueta_albaran(fila.get("numero_albaran"))
        seccion = normalizar_identificador(fila.get("seccion_visible"))
        es_detalle_abono = bool(
            seccion and "detall abonaments" in seccion.casefold()
        )
        fecha_visible = (
            fila.get("fecha_albaran") if es_detalle_abono else fila.get("fecha_entrega")
        )
        fecha = fecha_visible_a_iso(fecha_visible, permitir_iso=False) if fecha_visible else None
        importe = importe_espanol_a_decimal(fila.get("importe"))
        marcadores = fila.get("marcadores_antes_numero") or []
        if numero is None:
            incidencias.agregar(
                campo=f"tablas_literales.filas[{indice - 1}]",
                tipo="FILA_LITERAL_SIN_IDENTIFICADOR",
                nivel=NivelIncidencia.REVISION_MANUAL,
                descripcion="La fila literal no contiene un numero de albaran demostrable.",
                datos_visibles=fila,
                decision="La fila no se incorpora a los albaranes normalizados.",
            )
            continue
        if fecha is None:
            incidencias.agregar(
                campo=f"albaranes[{len(resultado)}].fecha_albaran",
                tipo="ALBARAN_SIN_FECHA_VISIBLE",
                nivel=NivelIncidencia.REVISION_MANUAL,
                descripcion="La fila literal no contiene una fecha de albaran.",
                datos_visibles={"numero_albaran": numero},
                decision="La fecha permanece en null.",
            )
        if importe is None:
            incidencias.agregar(
                campo=f"albaranes[{len(resultado)}].importe_total",
                tipo="ALBARAN_SIN_IMPORTE_VISIBLE",
                nivel=NivelIncidencia.REVISION_MANUAL,
                descripcion="La fila literal no contiene un importe asociado.",
                datos_visibles={"numero_albaran": numero},
                decision="El importe permanece en null.",
            )
        if es_detalle_abono:
            movimiento = "ABONO"
        elif marcadores == ["P", "PA"]:
            movimiento = "CARGO"
        else:
            movimiento = None
            incidencias.agregar(
                campo=f"albaranes[{len(resultado)}].tipo_movimiento",
                tipo="MARCADORES_ALBARAN_AMBIGUOS",
                nivel=NivelIncidencia.REVISION_MANUAL,
                descripcion="Los marcadores literales no permiten clasificar el movimiento.",
                datos_visibles={"numero_albaran": numero, "marcadores": marcadores},
                decision="tipo_movimiento permanece en null.",
            )
        resultado.append(
            {
                "numero_albaran": numero,
                "fecha_albaran": fecha,
                "tipo_movimiento": movimiento,
                "descripcion": None,
                "importe_base": None,
                "importe_total": importe,
                "pagina": fila.get("pagina_original"),
                "seccion": seccion,
                "procedencia": procedencia_visible("luna_tablas_literales"),
            }
        )
    return resultado


def _fusionar_albaranes(
    generales: list[dict[str, Any]],
    literales: list[dict[str, Any]],
    usar_literal: bool | None,
    incidencias: RegistroIncidencias,
) -> list[dict[str, Any]]:
    regla = aplicar_regla_determinista(
        nombre="usar_tablas_literales_fedefarma",
        version=VERSION_NORMALIZADOR,
        precondiciones={"fallback_literal_autorizado": usar_literal},
        entradas={"filas_literales": literales or None},
        derivar=lambda datos: datos["filas_literales"],
    )
    if not regla.aplicada:
        if literales:
            incidencias.agregar(
                campo="albaranes",
                tipo="FUSION_LITERAL_BLOQUEADA",
                nivel=NivelIncidencia.REVISION_MANUAL,
                descripcion="La configuracion no autoriza usar la transcripcion literal.",
                datos_visibles={"bloqueos": regla.bloqueos},
                decision="Se conservan solo los albaranes de la extraccion general.",
            )
        fuente = generales
    else:
        fuente = [*literales]
        por_numero_literal = {fila["numero_albaran"]: fila for fila in literales}
        for general in generales:
            numero = general["numero_albaran"]
            literal = por_numero_literal.get(numero)
            if literal is None:
                fuente.append(general)
                continue
            conflictos = [
                campo
                for campo in ("fecha_albaran", "importe_total")
                if general[campo] is not None
                and literal[campo] is not None
                and general[campo] != literal[campo]
            ]
            incidencias.agregar(
                campo="albaranes",
                tipo=(
                    "DUPLICADO_CONFLICTIVO_PRIORIZADO_LITERAL"
                    if conflictos
                    else "DUPLICADO_GENERAL_LITERAL_DEDUPLICADO"
                ),
                nivel=(
                    NivelIncidencia.REVISION_MANUAL if conflictos else NivelIncidencia.AVISO
                ),
                descripcion="La misma referencia aparece en ambas extracciones.",
                datos_visibles={"numero_albaran": numero, "conflictos": conflictos},
                decision="Se conserva una unica fila procedente de la tabla literal.",
            )

    vistos: set[str] = set()
    resultado = []
    for fila in fuente:
        numero = fila["numero_albaran"]
        if numero in vistos:
            incidencias.agregar(
                campo="albaranes",
                tipo="IDENTIFICADOR_ALBARAN_DUPLICADO",
                nivel=NivelIncidencia.REVISION_MANUAL,
                descripcion="Dos filas de la misma fuente comparten identificador.",
                datos_visibles={"numero_albaran": numero},
                decision="Se conserva solo la primera aparicion.",
            )
            continue
        vistos.add(numero)
        resultado.append({"orden": len(resultado) + 1, **fila})
    return resultado


def _normalizar_vencimientos(
    filas: list[dict[str, Any]], incidencias: RegistroIncidencias
) -> list[dict[str, Any]]:
    resultado = []
    for fila in filas:
        fecha = fecha_visible(fila.get("fecha_vencimiento"))
        importe = decimal_visible(fila.get("importe"))
        if fecha is None and importe is None:
            continue
        if importe is None:
            incidencias.agregar(
                campo=f"vencimientos[{len(resultado)}].importe",
                tipo="IMPORTE_VENCIMIENTO_NO_VISIBLE",
                nivel=NivelIncidencia.REVISION_MANUAL,
                descripcion="No existe importe visible asociado al vencimiento.",
                datos_visibles={"fecha_vencimiento": fecha},
                decision="No se asigna automaticamente el total de factura.",
            )
        resultado.append(
            {
                "orden": len(resultado) + 1,
                "fecha_vencimiento": fecha,
                "importe": importe,
                "nota": valor_visible(fila.get("nota")),
            }
        )
    return resultado


def _normalizar_ajustes(
    filas: list[dict[str, Any]],
    albaranes: list[dict[str, Any]],
    incidencias: RegistroIncidencias,
) -> list[dict[str, Any]]:
    importes_abono = {
        fila["importe_total"]
        for fila in albaranes
        if fila["tipo_movimiento"] == "ABONO" and fila["importe_total"] is not None
    }
    resultado = []
    for fila in filas:
        tipo = valor_visible(fila.get("tipo_ajuste"))
        descripcion = valor_visible(fila.get("descripcion"))
        importe = decimal_visible(fila.get("importe"))
        if tipo == "ABONO" and importe in importes_abono:
            incidencias.agregar(
                campo="ajustes",
                tipo="ABONO_RECLASIFICADO_COMO_ALBARAN",
                nivel=NivelIncidencia.AVISO,
                descripcion="El resumen general corresponde a una fila literal de abono.",
                datos_visibles={"descripcion": descripcion, "importe": importe},
                decision="No se duplica el abono como ajuste.",
            )
            continue
        es_bonificacion = (
            isinstance(tipo, str)
            and tipo.casefold() in {"bonificación", "bonificació"}
        )
        resultado.append(
            {
                "orden": len(resultado) + 1,
                "tipo_ajuste": "BONIFICACION" if es_bonificacion else None,
                "descripcion": "Bonificación pago inmediato" if es_bonificacion else descripcion,
                "importe": importe,
                "incluido_en_base": valor_visible(fila.get("incluido_en_base")),
                "incluido_en_total": valor_visible(fila.get("incluido_en_total")),
                "procedencia": (
                    procedencia_determinista(
                        "clasificacion_bonificacion_fedefarma",
                        VERSION_NORMALIZADOR,
                    )
                    if es_bonificacion
                    else procedencia_visible("luna_general")
                ),
            }
        )
    return resultado


def normalizar_fedefarma(
    extraccion_general: dict[str, Any],
    extraccion_literal: dict[str, Any] | None,
    metadatos_tecnicos: dict[str, Any],
    configuracion: ConfiguracionFedefarma,
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
            tipo="PROVEEDOR_FEDEFARMA_NO_RECONOCIDO",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="El nombre visible no coincide exactamente con un alias FEDEFARMA.",
            datos_visibles={"valor": proveedor_visible},
            decision="Se conserva el texto visible sin canonizar.",
        )

    impuestos = _normalizar_impuestos(list(general.get("impuestos", [])), incidencias)
    generales = _normalizar_general_albaranes(
        list(general.get("albaranes", [])), tipo_documento
    )
    transcripcion = (extraccion_literal or {}).get("transcripcion") or {}
    literales = _normalizar_literal_albaranes(transcripcion, incidencias)
    albaranes = _fusionar_albaranes(
        generales, literales, configuracion.usar_tablas_literales, incidencias
    )
    ajustes = _normalizar_ajustes(list(general.get("ajustes", [])), albaranes, incidencias)
    vencimientos = _normalizar_vencimientos(
        list(general.get("vencimientos", [])), incidencias
    )
    base = decimal_visible(general.get("base_imponible_total"))
    iva = decimal_visible(general.get("iva_total"))
    recargo = decimal_visible(general.get("recargo_equivalencia_total"))
    total = decimal_visible(general.get("importe_total"))
    cabecera = construir_cabecera_documental(
        general,
        metadatos_tecnicos,
        configuracion,
        incidencias,
        tipo_documento=tipo_documento,
        proveedor_nombre=proveedor,
        normalizar_cif=_normalizar_cif,
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
        "suma_bases_fiscales",
        [fila["base_imponible"] for fila in impuestos],
        base,
        tolerancia=TOLERANCIA_MONETARIA,
        descripcion_incidencia=_DESCRIPCION_VALIDACION,
        decision_incidencia=_DECISION_VALIDACION,
    )
    registrar_validacion_monetaria(
        validaciones,
        incidencias,
        "suma_cuotas_iva",
        [fila["cuota_iva"] for fila in impuestos],
        iva,
        tolerancia=TOLERANCIA_MONETARIA,
        descripcion_incidencia=_DESCRIPCION_VALIDACION,
        decision_incidencia=_DECISION_VALIDACION,
    )
    registrar_validacion_monetaria(
        validaciones,
        incidencias,
        "suma_cuotas_recargo",
        [fila["cuota_recargo_equivalencia"] for fila in impuestos],
        recargo,
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
            "cabecera_totales_fiscalidad_vencimientos": "luna_general",
            "albaranes": (
                "luna_tablas_literales_fusion_determinista"
                if configuracion.usar_tablas_literales is True
                else "luna_general"
            ),
            "paginas": "metadato_tecnico",
            "categoria": "configuracion_interna",
            "requiere_conciliacion_albaranes": "configuracion_interna",
            "destinatario.id_farmacia": "configuracion_interna",
            "destinatario.metodo_identificacion": "configuracion_interna",
            "signos": "lectura_visible_sin_regla_dermofarm",
        },
        configuracion=configuracion,
        configuracion_adicional={
            "usar_tablas_literales": configuracion.usar_tablas_literales,
        },
        validaciones_monetarias=validaciones,
    )
    return resultado, incidencias.como_lista()
