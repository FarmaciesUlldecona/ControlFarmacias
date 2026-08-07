from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from src.facturas.normalizadores.comun import (
    AliasProveedor,
    EstadoValidacion,
    aplicar_regla_determinista,
    fecha_visible_a_iso,
    importe_espanol_a_decimal,
    normalizar_identificador,
    validar_suma_monetaria,
    valor_visible,
)
from src.models.factura import FacturaNormalizada


VERSION_NORMALIZADOR = "alliance_v1.1"
TITULOS_ALBARANES = {"CARGOS": "CARGO", "ABONOS": "ABONO"}
NOMBRE_CANONICO_ALLIANCE = "ALLIANCE HEALTHCARE ESPAÑA, S.A."
ALIAS_ALLIANCE = AliasProveedor(
    nombre_canonico=NOMBRE_CANONICO_ALLIANCE,
    alias=("CENCORA", "AH", "ALLIANCE", "ALLIANCE HEALTHCARE"),
)


class FilaAlbaranInvalida(ValueError):
    """Una fila literal no contiene las cinco celdas mínimas exigidas."""


@dataclass(frozen=True, slots=True)
class ConfiguracionAlliance:
    archivo_origen: str
    pagina_inicio: int = 4
    pagina_fin: int = 7
    farmacia: str = "PIO"
    proveedor: str = "Alliance"
    categoria: str = "MERCANCIA"
    requiere_conciliacion_albaranes: bool = True
    destinatario_id_farmacia: str = "PIO"
    destinatario_metodo_identificacion: str = "CIF"
    factura_separada_inequivocamente: bool | None = None
    descuadre_total: bool | None = None
    pagos_parciales_o_fraccionamiento: bool | None = None
    importes_vencimiento_distintos: bool | None = None


def _normalizar_razon_social(valor: str | None) -> str | None:
    return ALIAS_ALLIANCE.normalizar(valor)


def _decimal_general(campo: Any) -> Decimal | None:
    valor = valor_visible(campo)
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation as error:
        raise ValueError(f"Importe general no válido: {valor!r}") from error


def _fecha_general(campo: Any) -> str | None:
    valor = valor_visible(campo)
    if valor is None:
        return None
    texto = str(valor).strip()
    return fecha_visible_a_iso(texto)


def normalizar_fila_albaran(
    celdas: list[str],
    titulo_tabla: str,
    orden: int,
    pagina_relativa: int,
    orden_tabla: int,
    orden_visual: int,
) -> dict[str, Any]:
    if titulo_tabla not in TITULOS_ALBARANES:
        raise FilaAlbaranInvalida(f"Tabla no admitida como albaranes: {titulo_tabla!r}")
    if len(celdas) != 5:
        raise FilaAlbaranInvalida(f"La fila debe contener 5 celdas y contiene {len(celdas)}")
    fecha, descripcion, numero, base, total = [celda.strip() for celda in celdas]
    if not all((fecha, descripcion, numero, base, total)):
        raise FilaAlbaranInvalida("La fila de albarán contiene celdas obligatorias vacías")
    return {
        "orden": orden,
        "numero_albaran": normalizar_identificador(numero),
        "fecha_albaran": fecha_visible_a_iso(fecha),
        "tipo_movimiento": TITULOS_ALBARANES[titulo_tabla],
        "descripcion": descripcion,
        "importe_base": importe_espanol_a_decimal(base),
        "importe_total": importe_espanol_a_decimal(total),
        "orden_reconstruido": True,
        "procedencia": {
            "fuente": "luna_tablas_literales",
            "pagina_relativa": pagina_relativa,
            "orden_tabla": orden_tabla,
            "titulo_tabla": titulo_tabla,
            "orden_visual": orden_visual,
            "celdas_literales": list(celdas),
        },
    }


def _normalizar_albaranes(
    tablas: list[dict[str, Any]],
    incidencias: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidatos = []
    for orden_tabla, tabla in enumerate(tablas, start=1):
        titulo = str(tabla.get("titulo_visible") or "").strip().upper()
        if titulo not in TITULOS_ALBARANES:
            continue
        pagina = int(tabla["pagina"])
        for fila in tabla.get("filas", []):
            candidatos.append((pagina, orden_tabla, int(fila["orden_visual"]), titulo, fila))
    candidatos.sort(key=lambda item: (item[0], item[1], item[2]))
    resultado = []
    for orden, (pagina, orden_tabla, orden_visual, titulo, fila) in enumerate(candidatos, start=1):
        try:
            resultado.append(
                normalizar_fila_albaran(
                    celdas=list(fila.get("celdas", [])),
                    titulo_tabla=titulo,
                    orden=orden,
                    pagina_relativa=pagina,
                    orden_tabla=orden_tabla,
                    orden_visual=orden_visual,
                )
            )
        except FilaAlbaranInvalida as error:
            incidencias.append(
                crear_incidencia(
                    campo="albaranes",
                    tipo="FILA_LITERAL_INCOMPLETA",
                    descripcion=str(error),
                    datos_visibles={"tabla": titulo, "pagina": pagina, "fila": fila},
                    decision="Fila rechazada; no se crea ningún albarán.",
                    revision=True,
                )
            )
    if resultado:
        incidencias.append(
            crear_incidencia(
                campo="albaranes.orden",
                tipo="ORDEN_RECONSTRUIDO",
                descripcion=(
                    "Las tablas CARGOS y ABONOS pueden ser paralelas y no proporcionan "
                    "una secuencia global inequívoca."
                ),
                datos_visibles={"tablas": [t["titulo_visible"] for t in tablas if str(t.get("titulo_visible") or "").upper() in TITULOS_ALBARANES]},
                decision="Orden estable por página, orden de tabla y orden visual; orden_reconstruido=true.",
                revision=False,
            )
        )
    return resultado


def _buscar_tabla(tablas: list[dict[str, Any]], titulo: str) -> dict[str, Any] | None:
    return next(
        (tabla for tabla in tablas if str(tabla.get("titulo_visible") or "").strip().upper() == titulo),
        None,
    )


def _numeros_no_vacios(celdas: list[str]) -> list[Decimal]:
    numeros = []
    for celda in celdas[1:]:
        if isinstance(celda, str) and celda.strip():
            try:
                numero = importe_espanol_a_decimal(celda)
            except ValueError:
                continue
            if numero is not None:
                numeros.append(numero)
    return numeros


def _normalizar_ajustes(
    tablas: list[dict[str, Any]],
    base_total: Decimal | None,
    importe_total: Decimal | None,
    incidencias: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gastos = _buscar_tabla(tablas, "GASTOS")
    compras = _buscar_tabla(tablas, "COMPRAS")
    if gastos is None:
        return []
    ajustes = []
    for fila in gastos.get("filas", []):
        celdas = list(fila.get("celdas", []))
        if not celdas or "SERVICIO BASICO" not in celdas[0].strip().upper():
            continue
        numeros = _numeros_no_vacios(celdas)
        if len(numeros) < 3:
            incidencias.append(
                crear_incidencia(
                    campo="ajustes",
                    tipo="SERVICIO_BASICO_INCOMPLETO",
                    descripcion="La fila Servicio básico no permite identificar base, IVA y total.",
                    datos_visibles={"celdas": celdas, "pagina": gastos.get("pagina")},
                    decision="No se crea el ajuste.",
                    revision=True,
                )
            )
            continue
        base, cuota, total = numeros[-3:]
        incluido_base: bool | None = None
        incluido_total: bool | None = None
        justificacion = {}
        if compras is not None:
            total_compras = next(
                (f for f in compras.get("filas", []) if f.get("celdas") and str(f["celdas"][0]).strip().upper() == "TOTAL COMPRAS"),
                None,
            )
            if total_compras:
                valores = _numeros_no_vacios(list(total_compras["celdas"]))
                if len(valores) >= 10:
                    base_compras = sum(valores[:3], Decimal("0"))
                    total_compras_factura = valores[-1]
                    if base_total is not None:
                        incluido_base = validar_suma_monetaria(
                            [base_compras, base], base_total, tolerancia=Decimal("0")
                        ).estado is EstadoValidacion.OK
                    if importe_total is not None:
                        incluido_total = validar_suma_monetaria(
                            [total_compras_factura, total],
                            importe_total,
                            tolerancia=Decimal("0"),
                        ).estado is EstadoValidacion.OK
                    justificacion = {
                        "base_compras": base_compras,
                        "base_servicio": base,
                        "base_total_general": base_total,
                        "total_compras": total_compras_factura,
                        "total_servicio": total,
                        "importe_total_general": importe_total,
                    }
        ajustes.append(
            {
                "orden": len(ajustes) + 1,
                "tipo_ajuste": "GASTO",
                "descripcion": celdas[0].strip(),
                "importe": total,
                "incluido_en_base": incluido_base,
                "incluido_en_total": incluido_total,
                "procedencia": {
                    "fuente": "luna_tablas_literales",
                    "pagina_relativa": gastos.get("pagina"),
                    "orden_visual": fila.get("orden_visual"),
                    "celdas_literales": celdas,
                    "base_visible": base,
                    "iva_visible": cuota,
                    "justificacion_inclusion": justificacion,
                },
            }
        )
        if incluido_base is None or incluido_total is None:
            incidencias.append(
                crear_incidencia(
                    campo="ajustes.inclusion",
                    tipo="INCLUSION_NO_DEMOSTRADA",
                    descripcion="No pudo demostrarse completamente la inclusión del ajuste en base y total.",
                    datos_visibles={"celdas": celdas, "justificacion": justificacion},
                    decision="Se mantienen indicadores no demostrables en null.",
                    revision=True,
                )
            )
    return ajustes


def _es_proveedor_alliance(proveedor_normalizado: str | None) -> bool | None:
    if proveedor_normalizado is None:
        return None
    return ALIAS_ALLIANCE.normalizar(proveedor_normalizado) == NOMBRE_CANONICO_ALLIANCE


def _normalizar_vencimientos(
    bloques: list[dict[str, Any]],
    proveedor_normalizado: str | None,
    importe_total: Decimal | None,
    configuracion: ConfiguracionAlliance,
    incidencias: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    resultado = []
    for bloque in bloques:
        fecha = fecha_visible_a_iso(bloque.get("texto_fecha"))
        importe = importe_espanol_a_decimal(bloque.get("texto_importe"))
        resultado.append(
            {
                "orden": len(resultado) + 1,
                "fecha_vencimiento": fecha,
                "importe": importe,
                "origen_fecha": "visible",
                "nota": None,
                "procedencia": {
                    "fuente": "luna_tablas_literales",
                    "pagina_relativa": bloque.get("pagina"),
                    "texto_fecha": bloque.get("texto_fecha"),
                    "texto_importe": bloque.get("texto_importe"),
                    "importe": "lectura_literal" if importe is not None else None,
                },
            }
        )

    fechas_visibles = [item for item in resultado if item["fecha_vencimiento"] is not None]
    importes_visibles = [item["importe"] for item in resultado if item["importe"] is not None]
    condiciones: dict[str, bool | None] = {
        "proveedor_alliance": _es_proveedor_alliance(proveedor_normalizado),
        "factura_separada_inequivocamente": configuracion.factura_separada_inequivocamente,
        "unica_fecha_vencimiento": len(fechas_visibles) == 1 and len(resultado) == 1,
        "sin_vencimientos_multiples": len(resultado) == 1,
        "sin_pagos_parciales_o_fraccionamiento": (
            None
            if configuracion.pagos_parciales_o_fraccionamiento is None
            else not configuracion.pagos_parciales_o_fraccionamiento
        ),
        "sin_importes_vencimiento_distintos": (
            None
            if configuracion.importes_vencimiento_distintos is None
            else not configuracion.importes_vencimiento_distintos
        ),
        "importe_total_valido": importe_total is not None,
        "sin_descuadre_total": (
            None if configuracion.descuadre_total is None else not configuracion.descuadre_total
        ),
        "sin_importe_visible_incompatible": not importes_visibles,
    }
    candidato = fechas_visibles[0] if len(fechas_visibles) == 1 else None
    requiere_regla = candidato is not None and candidato["importe"] is None
    resultado_regla = aplicar_regla_determinista(
        nombre="regla_proveedor_alliance_vencimiento_unico",
        version=VERSION_NORMALIZADOR,
        precondiciones=condiciones,
        entradas={"importe_total": importe_total},
        derivar=lambda entradas: entradas["importe_total"],
    )
    if requiere_regla and resultado_regla.aplicada:
        candidato["importe"] = resultado_regla.valor
        candidato["procedencia"]["importe"] = "regla_proveedor_alliance_vencimiento_unico"
        candidato["procedencia"]["importe_procede_de_lectura_literal"] = False
        candidato["nota"] = "Importe asignado mediante regla determinista de proveedor y vencimiento unico."
    elif requiere_regla or any(item["importe"] is None for item in resultado):
        incidencias.append(
            crear_incidencia(
                campo="vencimientos.importe",
                tipo="REGLA_VENCIMIENTO_UNICO_NO_APLICABLE",
                descripcion="No se cumplen todas las condiciones para asignar el total al vencimiento.",
                datos_visibles={
                    "bloques": bloques,
                    "condiciones": condiciones,
                    "bloqueos_regla": list(resultado_regla.bloqueos),
                },
                decision="Se conserva la fecha visible y se devuelve importe=null.",
                revision=True,
            )
        )
    return resultado


def _normalizar_destinatario(general: dict[str, Any], config: ConfiguracionAlliance) -> dict[str, Any]:
    bruto = general.get("destinatario") or {}
    return {
        "id_farmacia": normalizar_identificador(config.destinatario_id_farmacia),
        "nombre": valor_visible(bruto.get("nombre")),
        "cif": normalizar_identificador(valor_visible(bruto.get("cif"))),
        "metodo_identificacion": config.destinatario_metodo_identificacion,
    }


def crear_incidencia(
    campo: str,
    tipo: str,
    descripcion: str,
    datos_visibles: Any,
    decision: str,
    revision: bool,
) -> dict[str, Any]:
    return {
        "campo": campo,
        "tipo_incidencia": tipo,
        "descripcion": descripcion,
        "datos_visibles_disponibles": datos_visibles,
        "decision_tomada": decision,
        "requiere_revision_manual": revision,
    }


def normalizar_alliance(
    extraccion_general: dict[str, Any],
    tablas_literales: dict[str, Any],
    configuracion: ConfiguracionAlliance,
    fecha_ejecucion: datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    general = extraccion_general.get("factura", extraccion_general)
    literal = tablas_literales.get("transcripcion", tablas_literales)
    incidencias: list[dict[str, Any]] = []

    proveedor_visible = valor_visible(general.get("proveedor_nombre"))
    proveedor_normalizado = _normalizar_razon_social(proveedor_visible)
    base_total = _decimal_general(general.get("base_imponible_total"))
    importe_total = _decimal_general(general.get("importe_total"))
    tablas = list(literal.get("tablas", []))

    tipo_documento = valor_visible(general.get("tipo_documento"))
    factura = {
        "tipo_documento": tipo_documento,
        "categoria": configuracion.categoria,
        "requiere_conciliacion_albaranes": configuracion.requiere_conciliacion_albaranes,
        "pagina_inicio": configuracion.pagina_inicio,
        "pagina_fin": configuracion.pagina_fin,
        "proveedor_nombre": proveedor_normalizado,
        "proveedor_cif": normalizar_identificador(valor_visible(general.get("proveedor_cif"))),
        "numero_factura": normalizar_identificador(valor_visible(general.get("numero_factura"))),
        "fecha_factura": _fecha_general(general.get("fecha_factura")),
        "base_imponible_total": base_total,
        "iva_total": _decimal_general(general.get("iva_total")),
        "recargo_equivalencia_total": _decimal_general(general.get("recargo_equivalencia_total")),
        "importe_total": importe_total,
        "vencimientos": _normalizar_vencimientos(
            list(literal.get("bloques_vencimiento", [])),
            proveedor_normalizado,
            importe_total,
            configuracion,
            incidencias,
        ),
        "impuestos": [],
        "albaranes": _normalizar_albaranes(tablas, incidencias),
        "ajustes": _normalizar_ajustes(tablas, base_total, importe_total, incidencias),
        "destinatario": _normalizar_destinatario(general, configuracion),
        "fecha_cargo": None,
        "periodo_facturacion_inicio": None,
        "periodo_facturacion_fin": None,
        "nota_revision": None,
    }
    incidencias.append(
        crear_incidencia(
            campo="impuestos",
            tipo="DESGLOSE_FISCAL_INCOMPLETO",
            descripcion="Las tablas literales contienen información fiscal parcial, pero no los totales fiscales finales completos.",
            datos_visibles={"tablas_consideradas": [t.get("titulo_visible") for t in tablas if str(t.get("titulo_visible") or "").upper() in {"COMPRAS", "GASTOS"}]},
            decision="Se devuelve impuestos=[]; los totales agregados proceden de luna_general.",
            revision=True,
        )
    )

    # Valida compatibilidad con el modelo común, que ignora los metadatos extra de procedencia.
    modelo = FacturaNormalizada.desde_diccionario(factura)
    errores = modelo.validar()
    if errores:
        raise ValueError("Factura normalizada inválida: " + "; ".join(errores))

    instante = fecha_ejecucion or datetime.now(timezone.utc)
    resultado = {
        "version_normalizador": VERSION_NORMALIZADOR,
        "fecha_ejecucion": instante.astimezone(timezone.utc).isoformat(),
        "archivo_origen": configuracion.archivo_origen,
        "paginas_originales": [configuracion.pagina_inicio, configuracion.pagina_fin],
        "resultado_normalizado": factura,
        "procedencia_bloques": {
            "cabecera_y_totales": "luna_general",
            "tipo_documento": "luna_general",
            "vencimientos": "luna_tablas_literales",
            "impuestos": "luna_tablas_literales",
            "albaranes": "luna_tablas_literales",
            "ajustes": "luna_tablas_literales",
            "paginas": "metadato_tecnico",
            "categoria": "configuracion_interna",
            "requiere_conciliacion_albaranes": "configuracion_interna",
            "destinatario.id_farmacia": "configuracion_interna",
            "destinatario.metodo_identificacion": "configuracion_interna",
            "destinatario.nombre_y_cif": "luna_general",
        },
        "configuracion_interna_aplicada": {
            "farmacia": configuracion.farmacia,
            "proveedor": configuracion.proveedor,
            "categoria": configuracion.categoria,
            "requiere_conciliacion_albaranes": configuracion.requiere_conciliacion_albaranes,
            "destinatario_id_farmacia": configuracion.destinatario_id_farmacia,
            "destinatario_metodo_identificacion": configuracion.destinatario_metodo_identificacion,
            "factura_separada_inequivocamente": configuracion.factura_separada_inequivocamente,
            "descuadre_total": configuracion.descuadre_total,
            "pagos_parciales_o_fraccionamiento": configuracion.pagos_parciales_o_fraccionamiento,
            "importes_vencimiento_distintos": configuracion.importes_vencimiento_distintos,
        },
    }
    return resultado, incidencias


def serializar_json(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {clave: serializar_json(dato) for clave, dato in valor.items()}
    if isinstance(valor, list):
        return [serializar_json(dato) for dato in valor]
    return valor
