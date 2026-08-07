"""Normalizador determinista FEDEFARMA v1 con fusion literal de albaranes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from src.facturas.normalizadores.comun import (
    AliasProveedor,
    EstadoValidacion,
    NivelIncidencia,
    Procedencia,
    RegistroIncidencias,
    TipoProcedencia,
    aplicar_regla_determinista,
    fecha_visible_a_iso,
    importe_espanol_a_decimal,
    normalizar_identificador,
    validar_suma_monetaria,
    valor_visible,
)
from src.models.factura import FacturaNormalizada


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
_CIF_SEPARADO = re.compile(r"^([A-Z])-([0-9]{2})-([0-9]{6})$", re.IGNORECASE)
_ETIQUETA_ALBARAN = re.compile(
    r"^(?:albar(?:[aá]n|à)|n[ºo]\s*albar(?:[aá]n|à))\s*:\s*(.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ConfiguracionFedefarma:
    archivo_origen: str
    farmacia: str = "PIO"
    categoria: str = "MERCANCIA"
    requiere_conciliacion_albaranes: bool = True
    destinatario_id_farmacia: str = "PIO"
    destinatario_metodo_identificacion: str = "CIF"
    usar_tablas_literales: bool | None = None


def _decimal_visible(campo: Any) -> Decimal | None:
    valor = valor_visible(campo)
    return importe_espanol_a_decimal(valor) if valor is not None else None


def _porcentaje_visible(campo: Any) -> Decimal | None:
    valor = valor_visible(campo)
    if valor is None:
        return None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"Porcentaje fiscal no valido: {valor!r}") from error
    if not numero.is_finite():
        raise ValueError(f"Porcentaje fiscal no finito: {valor!r}")
    return numero


def _fecha_visible(campo: Any) -> str | None:
    valor = valor_visible(campo)
    return fecha_visible_a_iso(str(valor)) if valor is not None else None


def _procedencia_visible(fuente: str) -> dict[str, str]:
    return Procedencia(TipoProcedencia.LECTURA_VISIBLE, fuente).a_diccionario()


def _procedencia_regla(nombre: str) -> dict[str, str]:
    return Procedencia(
        TipoProcedencia.REGLA_DETERMINISTA,
        "python",
        regla=nombre,
        version_regla=VERSION_NORMALIZADOR,
    ).a_diccionario()


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
        base = _decimal_visible(fila.get("base_imponible"))
        cuota_iva = _decimal_visible(fila.get("cuota_iva"))
        cuota_recargo = _decimal_visible(fila.get("cuota_recargo_equivalencia"))
        tipo_iva = _porcentaje_visible(fila.get("tipo_iva"))
        tipo_recargo = _porcentaje_visible(fila.get("tipo_recargo_equivalencia"))
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
        fecha = _fecha_visible(fila.get("fecha_albaran"))
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
                "importe_base": _decimal_visible(fila.get("importe_base")),
                "importe_total": _decimal_visible(fila.get("importe_total")),
                "pagina": _pagina_evidencia(fila),
                "seccion": "extraccion_general",
                "procedencia": _procedencia_visible("luna_general"),
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
                "procedencia": _procedencia_visible("luna_tablas_literales"),
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
        fecha = _fecha_visible(fila.get("fecha_vencimiento"))
        importe = _decimal_visible(fila.get("importe"))
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
        importe = _decimal_visible(fila.get("importe"))
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
                    _procedencia_regla("clasificacion_bonificacion_fedefarma")
                    if es_bonificacion
                    else _procedencia_visible("luna_general")
                ),
            }
        )
    return resultado


def _paginas_originales(metadatos: dict[str, Any]) -> tuple[int, int]:
    paginas = metadatos.get("paginas_originales")
    if (
        isinstance(paginas, list)
        and len(paginas) == 2
        and all(isinstance(x, int) and not isinstance(x, bool) and x >= 1 for x in paginas)
        and paginas[1] >= paginas[0]
    ):
        return paginas[0], paginas[1]
    raise ValueError("Los metadatos tecnicos deben declarar paginas originales validas.")


def _agregar_validacion(
    validaciones: list[dict[str, Any]],
    incidencias: RegistroIncidencias,
    nombre: str,
    sumandos: list[Decimal | None],
    esperado: Decimal | None,
) -> None:
    validacion = validar_suma_monetaria(
        sumandos, esperado, tolerancia=TOLERANCIA_MONETARIA
    )
    validaciones.append({"nombre": nombre, **validacion.a_diccionario()})
    if validacion.estado is not EstadoValidacion.OK:
        incidencias.agregar(
            campo=nombre,
            tipo=f"VALIDACION_MONETARIA_{validacion.estado.value}",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="La validacion monetaria no se ha confirmado.",
            datos_visibles=validacion.a_diccionario(),
            decision="No se modifican cifras para forzar el cuadre.",
        )


def normalizar_fedefarma(
    extraccion_general: dict[str, Any],
    extraccion_literal: dict[str, Any] | None,
    metadatos_tecnicos: dict[str, Any],
    configuracion: ConfiguracionFedefarma,
    fecha_ejecucion: datetime | None = None,
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

    proveedor_visible = valor_visible(general.get("proveedor_nombre"))
    proveedor = ALIAS_FEDEFARMA.normalizar(proveedor_visible)
    if proveedor_visible is not None and proveedor != NOMBRE_CANONICO_FEDEFARMA:
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
    base = _decimal_visible(general.get("base_imponible_total"))
    iva = _decimal_visible(general.get("iva_total"))
    recargo = _decimal_visible(general.get("recargo_equivalencia_total"))
    total = _decimal_visible(general.get("importe_total"))
    destinatario_bruto = general.get("destinatario") or {}
    pagina_inicio, pagina_fin = _paginas_originales(metadatos_tecnicos)

    factura = {
        "tipo_documento": tipo_documento,
        "categoria": configuracion.categoria,
        "requiere_conciliacion_albaranes": configuracion.requiere_conciliacion_albaranes,
        "pagina_inicio": pagina_inicio,
        "pagina_fin": pagina_fin,
        "proveedor_nombre": proveedor,
        "proveedor_cif": _normalizar_cif(
            valor_visible(general.get("proveedor_cif")), incidencias
        ),
        "numero_factura": normalizar_identificador(
            valor_visible(general.get("numero_factura"))
        ),
        "fecha_factura": _fecha_visible(general.get("fecha_factura")),
        "base_imponible_total": base,
        "iva_total": iva,
        "recargo_equivalencia_total": recargo,
        "importe_total": total,
        "vencimientos": vencimientos,
        "impuestos": impuestos,
        "albaranes": albaranes,
        "ajustes": ajustes,
        "destinatario": {
            "id_farmacia": normalizar_identificador(
                configuracion.destinatario_id_farmacia
            ),
            "nombre": valor_visible(destinatario_bruto.get("nombre")),
            "cif": normalizar_identificador(
                valor_visible(destinatario_bruto.get("cif"))
            ),
            "metodo_identificacion": configuracion.destinatario_metodo_identificacion,
        },
        "fecha_cargo": None,
        "periodo_facturacion_inicio": None,
        "periodo_facturacion_fin": None,
        "nota_revision": None,
    }

    validaciones: list[dict[str, Any]] = []
    _agregar_validacion(validaciones, incidencias, "total_factura", [base, iva, recargo], total)
    _agregar_validacion(
        validaciones,
        incidencias,
        "suma_bases_fiscales",
        [fila["base_imponible"] for fila in impuestos],
        base,
    )
    _agregar_validacion(
        validaciones,
        incidencias,
        "suma_cuotas_iva",
        [fila["cuota_iva"] for fila in impuestos],
        iva,
    )
    _agregar_validacion(
        validaciones,
        incidencias,
        "suma_cuotas_recargo",
        [fila["cuota_recargo_equivalencia"] for fila in impuestos],
        recargo,
    )

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

    instante = fecha_ejecucion or datetime.now(timezone.utc)
    resultado = {
        "version_normalizador": VERSION_NORMALIZADOR,
        "fecha_ejecucion": instante.astimezone(timezone.utc).isoformat(),
        "archivo_origen": configuracion.archivo_origen,
        "paginas_originales": [pagina_inicio, pagina_fin],
        "resultado_normalizado": factura,
        "procedencia_bloques": {
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
        "configuracion_interna_aplicada": {
            "farmacia": configuracion.farmacia,
            "categoria": configuracion.categoria,
            "requiere_conciliacion_albaranes": configuracion.requiere_conciliacion_albaranes,
            "destinatario_id_farmacia": configuracion.destinatario_id_farmacia,
            "destinatario_metodo_identificacion": configuracion.destinatario_metodo_identificacion,
            "usar_tablas_literales": configuracion.usar_tablas_literales,
        },
        "validaciones_monetarias": validaciones,
    }
    return resultado, incidencias.como_lista()
