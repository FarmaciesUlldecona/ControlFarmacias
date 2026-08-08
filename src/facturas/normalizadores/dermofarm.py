"""Normalizador determinista Dermofarm v1 para el abono actual."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from src.facturas.normalizadores.comun import (
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
from src.facturas.normalizadores.configuracion import ConfiguracionProveedor
from src.facturas.normalizadores.documento import (
    construir_cabecera_documental,
    construir_destinatario,
    normalizar_identificador_fiscal_es,
    normalizar_proveedor_documental,
)
from src.models.factura import FacturaNormalizada


VERSION_NORMALIZADOR = "dermofarm_v1"
NOMBRE_CANONICO_DERMOFARM = "DERMOFARM, S.A.U."


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguracionDermofarm(ConfiguracionProveedor):
    proveedor_nombre_canonico: str = NOMBRE_CANONICO_DERMOFARM
    aliases: tuple[str, ...] = ("DERMOFARM",)


def _decimal_visible(campo: Any) -> Decimal | None:
    valor = valor_visible(campo)
    if valor is None:
        return None
    return importe_espanol_a_decimal(valor)


def _porcentaje_visible(campo: Any) -> Decimal | None:
    valor = valor_visible(campo)
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"Porcentaje fiscal no valido: {valor!r}") from error


def _fecha_visible(campo: Any) -> str | None:
    valor = valor_visible(campo)
    if valor is None:
        return None
    return fecha_visible_a_iso(str(valor))


def _procedencia_visible(fuente: str = "luna_general") -> dict[str, str]:
    return Procedencia(TipoProcedencia.LECTURA_VISIBLE, fuente).a_diccionario()


def _importe_contable(
    valor: Decimal | None,
    tipo_documento: str | None,
) -> tuple[Decimal | None, dict[str, str] | None]:
    if valor is None:
        return None, None
    if tipo_documento != "ABONO":
        return valor, _procedencia_visible()
    resultado = aplicar_regla_determinista(
        nombre="signo_contable_abono_dermofarm",
        version=VERSION_NORMALIZADOR,
        precondiciones={"tipo_abono_visible": True},
        entradas={"importe_visible": valor},
        derivar=lambda entradas: -abs(entradas["importe_visible"]),
    )
    return resultado.valor, resultado.procedencia.a_diccionario() if resultado.procedencia else None


def _normalizar_impuestos(
    filas: list[dict[str, Any]],
    tipo_documento: str | None,
    incidencias: RegistroIncidencias,
) -> list[dict[str, Any]]:
    normalizadas = []
    for fila in filas:
        base, _ = _importe_contable(_decimal_visible(fila.get("base_imponible")), tipo_documento)
        cuota_iva, _ = _importe_contable(_decimal_visible(fila.get("cuota_iva")), tipo_documento)
        cuota_recargo, _ = _importe_contable(
            _decimal_visible(fila.get("cuota_recargo_equivalencia")), tipo_documento
        )
        normalizadas.append(
            {
                "base_imponible": base,
                "tipo_iva": _porcentaje_visible(fila.get("tipo_iva")),
                "cuota_iva": cuota_iva,
                "tipo_recargo_equivalencia": _porcentaje_visible(
                    fila.get("tipo_recargo_equivalencia")
                ),
                "cuota_recargo_equivalencia": cuota_recargo,
            }
        )

    filas_iva = [fila for fila in normalizadas if fila["tipo_iva"] is not None]
    filas_recargo = [
        fila for fila in normalizadas if fila["tipo_recargo_equivalencia"] is not None
    ]
    if (
        len(normalizadas) == 2
        and len(filas_iva) == 1
        and len(filas_recargo) == 1
        and filas_iva[0]["base_imponible"] is not None
        and filas_iva[0]["base_imponible"] == filas_recargo[0]["base_imponible"]
    ):
        iva = filas_iva[0]
        recargo = filas_recargo[0]
        incidencias.agregar(
            campo="impuestos",
            tipo="FILAS_FISCALES_COMPLEMENTARIAS_UNIFICADAS",
            nivel=NivelIncidencia.AVISO,
            descripcion="Las filas visibles de IVA y recargo comparten la misma base.",
            datos_visibles={"cantidad_filas": 2, "base_comun": iva["base_imponible"]},
            decision="Se representa un unico tramo fiscal con IVA y recargo.",
        )
        return [
            {
                "orden": 1,
                "base_imponible": iva["base_imponible"],
                "tipo_iva": iva["tipo_iva"],
                "cuota_iva": iva["cuota_iva"],
                "tipo_recargo_equivalencia": recargo["tipo_recargo_equivalencia"],
                "cuota_recargo_equivalencia": recargo["cuota_recargo_equivalencia"],
            }
        ]

    return [{"orden": indice, **fila} for indice, fila in enumerate(normalizadas, start=1)]


def _normalizar_albaranes(
    filas: list[dict[str, Any]],
    tipo_documento: str | None,
    incidencias: RegistroIncidencias,
) -> list[dict[str, Any]]:
    resultado = []
    for fila in filas:
        numero = normalizar_identificador(valor_visible(fila.get("numero_albaran")))
        fecha = _fecha_visible(fila.get("fecha_albaran"))
        if numero is None and fecha is None:
            continue
        movimiento = tipo_documento if tipo_documento == "ABONO" else None
        importe_base, _ = _importe_contable(
            _decimal_visible(fila.get("importe_base")), tipo_documento
        )
        importe_total, _ = _importe_contable(
            _decimal_visible(fila.get("importe_total")), tipo_documento
        )
        if importe_base is None and importe_total is None:
            incidencias.agregar(
                campo=f"albaranes[{len(resultado)}].importes",
                tipo="IMPORTES_ALBARAN_NO_VISIBLES",
                nivel=NivelIncidencia.REVISION_MANUAL,
                descripcion="La referencia de albaran no muestra importes asociados.",
                datos_visibles={"numero_albaran": numero, "fecha_albaran": fecha},
                decision="Los importes del albaran permanecen en null.",
            )
        resultado.append(
            {
                "orden": len(resultado) + 1,
                "numero_albaran": numero,
                "fecha_albaran": fecha,
                "tipo_movimiento": movimiento,
                "descripcion": valor_visible(fila.get("descripcion")),
                "importe_base": importe_base,
                "importe_total": importe_total,
                "procedencia": {
                    "numero_y_fecha": _procedencia_visible(),
                    "tipo_movimiento": (
                        Procedencia(
                            TipoProcedencia.REGLA_DETERMINISTA,
                            "python",
                            regla="movimiento_segun_tipo_documento_visible",
                            version_regla=VERSION_NORMALIZADOR,
                        ).a_diccionario()
                        if movimiento is not None
                        else None
                    ),
                },
            }
        )
    return resultado


def _agregar_validacion(
    validaciones: list[dict[str, Any]],
    incidencias: RegistroIncidencias,
    nombre: str,
    sumandos: list[Decimal | None],
    esperado: Decimal | None,
    tolerancia: Decimal = Decimal("0.01"),
) -> None:
    resultado = validar_suma_monetaria(sumandos, esperado, tolerancia=tolerancia)
    validaciones.append({"nombre": nombre, **resultado.a_diccionario()})
    if resultado.estado is not EstadoValidacion.OK:
        incidencias.agregar(
            campo=nombre,
            tipo=f"VALIDACION_MONETARIA_{resultado.estado.value}",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="La validacion monetaria no ha podido confirmarse correctamente.",
            datos_visibles=resultado.a_diccionario(),
            decision="No se corrigen importes por plausibilidad.",
        )


def normalizar_dermofarm(
    extraccion_general: dict[str, Any],
    metadatos_tecnicos: dict[str, Any],
    configuracion: ConfiguracionDermofarm,
    fecha_ejecucion: datetime | None = None,
    *,
    archivo_origen: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    general = extraccion_general.get("factura", extraccion_general)
    incidencias = RegistroIncidencias()

    tipo_visible = valor_visible(general.get("tipo_documento"))
    tipo_documento = "ABONO" if tipo_visible == "ABONO" else None
    if tipo_documento is None:
        incidencias.agregar(
            campo="tipo_documento",
            tipo="TIPO_ABONO_NO_DEMOSTRADO",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="No existe evidencia valida y exacta del indicador ABONO.",
            datos_visibles={"valor": tipo_visible},
            decision="tipo_documento permanece en null y no se corrigen signos.",
        )

    proveedor_visible, proveedor, proveedor_reconocido = (
        normalizar_proveedor_documental(
            general.get("proveedor_nombre"), configuracion
        )
    )
    if proveedor_visible is not None and not proveedor_reconocido:
        incidencias.agregar(
            campo="proveedor_nombre",
            tipo="PROVEEDOR_DERMOFARM_NO_RECONOCIDO",
            nivel=NivelIncidencia.REVISION_MANUAL,
            descripcion="El nombre visible no coincide exactamente con un alias Dermofarm.",
            datos_visibles={"valor": proveedor_visible},
            decision="Se conserva el texto visible sin canonizar.",
        )

    importes_originales = {
        campo: _decimal_visible(general.get(campo))
        for campo in (
            "base_imponible_total",
            "iva_total",
            "recargo_equivalencia_total",
            "importe_total",
        )
    }
    importes = {
        campo: _importe_contable(valor, tipo_documento)[0]
        for campo, valor in importes_originales.items()
    }
    if tipo_documento == "ABONO" and any(
        valor is not None and valor > 0 for valor in importes_originales.values()
    ):
        incidencias.agregar(
            campo="totales",
            tipo="SIGNO_CONTABLE_ABONO_NORMALIZADO",
            nivel=NivelIncidencia.AVISO,
            descripcion="El documento visible es ABONO y presenta magnitudes positivas.",
            datos_visibles=importes_originales,
            decision="Las magnitudes contables se representan con signo negativo.",
        )

    impuestos = _normalizar_impuestos(
        list(general.get("impuestos", [])), tipo_documento, incidencias
    )
    albaranes = _normalizar_albaranes(
        list(general.get("albaranes", [])), tipo_documento, incidencias
    )
    cabecera = construir_cabecera_documental(
        general,
        metadatos_tecnicos,
        configuracion,
        incidencias,
        tipo_documento=tipo_documento,
        proveedor_nombre=proveedor,
        normalizar_cif=lambda valor, registro: normalizar_identificador_fiscal_es(
            valor, registro, etiqueta_visible="VAT"
        ),
    )
    destinatario = construir_destinatario(general.get("destinatario"), configuracion)
    pagina_inicio = cabecera["pagina_inicio"]
    pagina_fin = cabecera["pagina_fin"]

    factura = {
        **cabecera,
        **importes,
        "vencimientos": [],
        "impuestos": impuestos,
        "albaranes": albaranes,
        "ajustes": [],
        "destinatario": destinatario,
        "fecha_cargo": None,
        "periodo_facturacion_inicio": None,
        "periodo_facturacion_fin": None,
        "nota_revision": None,
    }

    validaciones: list[dict[str, Any]] = []
    _agregar_validacion(
        validaciones,
        incidencias,
        "total_factura",
        [
            factura["base_imponible_total"],
            factura["iva_total"],
            factura["recargo_equivalencia_total"],
        ],
        factura["importe_total"],
    )
    if impuestos:
        tramo = impuestos[0]
        base = tramo["base_imponible"]
        tipo_iva = tramo["tipo_iva"]
        tipo_recargo = tramo["tipo_recargo_equivalencia"]
        iva_calculado = base * tipo_iva / Decimal("100") if base is not None and tipo_iva is not None else None
        recargo_calculado = (
            base * tipo_recargo / Decimal("100")
            if base is not None and tipo_recargo is not None
            else None
        )
        _agregar_validacion(
            validaciones, incidencias, "cuota_iva", [iva_calculado], tramo["cuota_iva"]
        )
        _agregar_validacion(
            validaciones,
            incidencias,
            "cuota_recargo_equivalencia",
            [recargo_calculado],
            tramo["cuota_recargo_equivalencia"],
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
        "archivo_origen": archivo_origen,
        "paginas_originales": [pagina_inicio, pagina_fin],
        "resultado_normalizado": factura,
        "procedencia_bloques": {
            "cabecera_totales_fiscalidad_albaranes": "lectura_visible_luna_general",
            "paginas": "metadato_tecnico",
            "categoria": "configuracion_interna",
            "requiere_conciliacion_albaranes": "configuracion_interna",
            "destinatario.id_farmacia": "configuracion_interna",
            "destinatario.metodo_identificacion": "configuracion_interna",
            "signos_contables": "regla_determinista:signo_contable_abono_dermofarm",
        },
        "configuracion_interna_aplicada": {
            "farmacia": configuracion.farmacia,
            "categoria": configuracion.categoria,
            "requiere_conciliacion_albaranes": configuracion.requiere_conciliacion_albaranes,
            "destinatario_id_farmacia": configuracion.id_farmacia,
            "destinatario_metodo_identificacion": configuracion.metodo_identificacion_farmacia,
        },
        "validaciones_monetarias": validaciones,
    }
    return resultado, incidencias.como_lista()
