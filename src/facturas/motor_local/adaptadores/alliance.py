from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from src.facturas.normalizador_v2.reglas import clasificacion_conceptual_documental

from ..conciliacion import ComponenteConciliacion, EspecificacionConciliacion, evaluar_conciliaciones
from ..geometria.campos import fecha_iso, palabras_fecha, palabras_importe
from ..geometria.lineas import normalizar_texto
from ..modelos import DocumentoLocal, LineaLocal, PalabraLocal, SegmentoLocal, union_bbox
from .base import AdaptadorBase, Reconocimiento


FACTURA_RE = re.compile(r"^\d{8}$")
REFERENCIA_FILA_RE = re.compile(r"^\d{2}[A-Z]\d{5}$", re.I)
NIF_RE = re.compile(r"^(?:[A-Z]\d{8}|\d{8}[A-Z])$", re.I)


TIPOS_PEDIDO_MERCANCIA_ALLIANCE = frozenset({
    "NORMAL ACUSTICO",
    "NETOS PLUS",
    "PLATAFORMA 360",
    "COSTO LABORAT.",
    "ECOCEUTICS",
})


def clasificar_fila_economica_alliance(
    candidato: dict[str, Any],
    relacion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Clasifica por estructura y concepto; nunca por prefijo o columna sola."""
    sentido = (candidato.get("sentido") or {}).get("valor")
    tipo = normalizar_texto(str((candidato.get("tipo_pedido") or {}).get("valor") or ""))
    total = (candidato.get("total") or {}).get("valor")
    try:
        total_decimal = Decimal(str(total)) if total is not None else None
    except InvalidOperation:
        total_decimal = None
    signo = (
        "POSITIVO" if total_decimal is not None and total_decimal > 0
        else "NEGATIVO" if total_decimal is not None and total_decimal < 0
        else "CERO" if total_decimal == 0
        else None
    )
    evidencias = [
        *((candidato.get("sentido") or {}).get("evidencias") or []),
        *((candidato.get("tipo_pedido") or {}).get("evidencias") or []),
        *((candidato.get("total") or {}).get("evidencias") or []),
    ]
    resultado = {
        "concepto": "NO_DEMOSTRABLE",
        "categoria_movimiento": None,
        "sentido": sentido,
        "signo": signo,
        "regla": "ESTRUCTURA_Y_CONCEPTO_INSUFICIENTES",
        "evidencias": evidencias,
        "mismo_hecho_economico_resumen": False,
        "relacion_documental": None,
    }
    if not (
        (sentido == "ABONO" and signo == "NEGATIVO")
        or (sentido == "CARGO" and signo == "POSITIVO")
    ):
        return {**resultado, "regla": "SENTIDO_Y_SIGNO_NO_COHERENTES_O_NO_DOCUMENTADOS"}
    if relacion and relacion.get("inequivoca") is True:
        categoria = relacion["movimiento"].get("categoria")
        conceptos = {
            "SERVICIO": "SERVICIO",
            "RAPPEL": "AJUSTE",
            "ABONO_COMERCIAL": "ABONO",
            "DEVOLUCION_MERCANCIA": "DEVOLUCION_MERCANCIA",
            "DESCUENTO": "ABONO",
            "BONIFICACION": "ABONO",
            "CONDICION_COMERCIAL": "AJUSTE",
            "CONDICION_COOPERATIVA": "AJUSTE",
        }
        concepto = conceptos.get(categoria)
        if concepto:
            return {
                **resultado,
                "concepto": concepto,
                "categoria_movimiento": categoria,
                "regla": "RELACION_ECONOMICA_EXACTA_UNICA_CON_RESUMEN_CLASIFICADO",
                "evidencias": [*evidencias, *(relacion.get("evidencias") or [])],
                "mismo_hecho_economico_resumen": True,
                "relacion_documental": relacion["orden"],
            }
    if sentido == "ABONO" and tipo == "ABONOS AGRUPADOS":
        return {
            **resultado,
            "concepto": "ABONO",
            "categoria_movimiento": "ABONO_COMERCIAL",
            "regla": "BLOQUE_ABONOS_Y_LITERAL_ABONOS_AGRUPADOS",
        }
    if sentido == "CARGO" and tipo in TIPOS_PEDIDO_MERCANCIA_ALLIANCE:
        return {
            **resultado,
            "concepto": "ALBARAN_MERCANCIA",
            "regla": "BLOQUE_CARGOS_Y_TIPO_PEDIDO_MERCANCIA_CERTIFICADO",
        }
    return resultado


def promover_albaran_alliance(
    candidato: dict[str, Any], *, factura_documental: str,
    paginas_factura: list[int], segmentacion_inequivoca: bool,
) -> dict[str, Any] | None:
    """Promueve solo una fila situada bajo columnas ALBARAN inequívocas.

    El patrón de referencia, el nombre del fichero y la posición aislada no
    conceden rol. Fecha e importe son opcionales, pero, si existen, conservan
    evidencia documental propia.
    """
    rol = candidato.get("rol_documentacion") or {}
    numero = candidato.get("numero_referencia")
    pagina = (candidato.get("provenance") or {}).get("pagina")
    if (
        not segmentacion_inequivoca
        or not factura_documental
        or type(pagina) is not int
        or pagina not in paginas_factura
        or not numero
        or not numero.get("valor")
        or not numero.get("evidencias")
        or rol.get("valor") != "ALBARAN"
        or rol.get("regla") != "COLUMNAS_NUMERO_ALBARAN_EXPLICITAS"
        or not rol.get("evidencias")
        or (candidato.get("clasificacion_economica") or {}).get("concepto")
            != "ALBARAN_MERCANCIA"
    ):
        return None
    for optional in ("fecha", "base", "total", "tipo_pedido", "sentido"):
        value = candidato.get(optional)
        if value is not None and (value.get("valor") is None or not value.get("evidencias")):
            return None
    return {
        "orden": candidato.get("orden"),
        "numero_albaran": numero,
        "fecha": candidato.get("fecha"),
        "tipo_pedido": candidato.get("tipo_pedido"),
        "base": candidato.get("base"),
        "total": candidato.get("total"),
        "sentido": candidato.get("sentido"),
        "rol_fila": "ALBARAN_DEMOSTRADO",
        "rol_documentacion": rol,
        "provenance": {
            **(candidato.get("provenance") or {}),
            "factura_documental": factura_documental,
            "paginas_factura": list(paginas_factura),
            "regla_promocion": "COLUMNAS_NUMERO_ALBARAN_EXPLICITAS_EN_SEGMENTO_FACTURA",
            "regla_clasificacion": candidato["clasificacion_economica"]["regla"],
            "origen": "PDF",
        },
    }


def sentido_desde_seccion_documental(
    seccion_literal: str | None,
    *,
    pertenencia_demostrada: bool,
) -> str | None:
    """Deriva sentido solo de una pertenencia estructural inequívoca.

    La descripción, categoría, signo, identidad y posición aproximada del
    movimiento quedan deliberadamente fuera de esta regla.
    """
    if not pertenencia_demostrada or seccion_literal is None:
        return None
    seccion = normalizar_texto(seccion_literal)
    if seccion in {"CARGO", "CARGOS"}:
        return "CARGO"
    if seccion in {"ABONO", "ABONOS"}:
        return "ABONO"
    return None


def documentar_sentido_desde_relacion(
    candidato: dict[str, Any],
    relacion: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Documenta sentido solo desde una relación económica 1:1 demostrada."""
    if not relacion:
        return None
    if (
        relacion.get("tipo_relacion") != "CONCILIACION_ECONOMICA_EXACTA_UNICA_EN_FACTURA"
        or relacion.get("cardinalidad") != "1:1"
        or relacion.get("inequivoca") is not True
        or not relacion.get("evidencias")
    ):
        return None
    sentido_candidato = candidato.get("sentido")
    if not sentido_candidato or sentido_candidato.get("valor") not in {"CARGO", "ABONO"}:
        return None
    if not sentido_candidato.get("evidencias"):
        return None
    return {
        "valor": sentido_candidato["valor"],
        "sentido_fuente": "RELACION_DOCUMENTAL",
        "tipo_evidencia": "SENTIDO_DERIVADO_RELACION_DOCUMENTAL",
        "candidato_relacionado": relacion["candidato"],
        "seccion_origen": sentido_candidato,
        "relacion_documental": {
            "orden": relacion["orden"],
            "tipo_relacion": relacion["tipo_relacion"],
            "cardinalidad": relacion["cardinalidad"],
            "evidencias": relacion["evidencias"],
            "provenance": relacion["provenance"],
        },
        "evidencias": [*sentido_candidato["evidencias"], *relacion["evidencias"]],
        "provenance": {
            "regla": "SENTIDO_DERIVADO_RELACION_DOCUMENTAL",
            "adaptador": relacion["provenance"]["adaptador"],
            "version_adaptador": relacion["provenance"]["version_adaptador"],
            "transferencia_rol": False,
            "fusion_entidades": False,
        },
    }


def documentar_sentido_decision_funcional_pio(literal: str) -> dict[str, Any] | None:
    """Aplica únicamente las decisiones literales autorizadas para Alliance."""
    decisiones = {
        "SERVICIO BASICO": "CARGO",
        "CONDIC. COMERCIAL": "CARGO",
    }
    literal_normalizado = normalizar_texto(literal)
    sentido = decisiones.get(literal_normalizado)
    if sentido is None:
        return None
    return {
        "valor": sentido,
        "sentido_fuente": "DECISION_FUNCIONAL_PIO",
        "tipo_evidencia": "DECISION_FUNCIONAL_PIO",
        "evidencia_documental_directa": False,
        "literal_autorizado": literal_normalizado,
        "alcance": {
            "proveedor": "ALLIANCE",
            "adaptador": "alliance-local",
            "layout": "ALLIANCE_FACTURA_DENSO_V1",
        },
        "evidencias": [],
        "provenance": {
            "autoridad": "PIO",
            "regla": "DECISION_FUNCIONAL_PIO_LITERAL_EXACTO_ALLIANCE",
            "inferencia_por_categoria": False,
            "inferencia_por_signo": False,
            "inferencia_por_gold": False,
        },
    }


class AdaptadorAlliance(AdaptadorBase):
    """Extractor local del layout tabular Alliance/Cencora auditado.

    Todas las filas se conservan como candidatos. Solo se publica además un
    albarán cuando la página contiene las columnas explícitas NUMERO ALBARAN,
    la fila tiene número con evidencia y la página pertenece inequívocamente
    al segmento de una factura. El candidato original nunca se destruye.
    """

    id = "alliance-local"
    version = "1.2.0"
    capacidades = {
        "segmentacion": "SOPORTADO_MULTIFACTURA_DETERMINISTA",
        "cabecera": "SOPORTADO_MONEDA_NULL_NO_DOCUMENTADA",
        "candidatos_fila": "SOPORTADO_CON_PROMOCION_DOCUMENTAL_FAIL_CLOSED",
        "albaranes": "SOPORTADO_ESTRUCTURA_Y_CONCEPTO_MERCANCIA",
        "movimientos": "SOPORTADO_SENTIDO_DOCUMENTAL_O_NULL",
        "impuestos": "SOPORTADO_TIPOS_IMPRESOS",
        "vencimientos": "SOPORTADO_OCURRENCIAS_DOCUMENTALES",
        "otros": "SOPORTADO",
        "conciliacion_documental": "SOPORTADO",
    }

    def reconocer(self, documento: DocumentoLocal) -> Reconocimiento:
        texto = normalizar_texto("\n".join(l.texto for p in documento.paginas for l in p.lineas))
        comprobaciones = {
            "identidad_legal_visible": "ALLIANCE HEALTHCARE" in texto and "A50004324" in texto,
            "factura_duplicado": "FACTURA DUPLICADO" in texto,
            "resumen_fiscal": all(x in texto for x in ("COMPRAS BASE IMPONIBLE IVA R.E. TOTALES", "TOTAL RECARGOS EQUIVALENCIA", "TOTAL IVAS")),
            "tablas_paralelas": all(x in texto for x in ("CARGOS ABONOS", "TIPO DE PEDIDO", "TOTAL BASE")),
            "paginacion_interna": bool(re.search(r"PAGINA\s+0?1\s+DE\s+0?\d+", texto)),
            "texto_nativo": all(p.palabras and p.texto.strip() for p in documento.paginas),
        }
        completo = all(comprobaciones.values())
        indicios = comprobaciones["identidad_legal_visible"] or comprobaciones["factura_duplicado"]
        estado = "RECONOCIDO" if completo else ("AMBIGUO" if indicios else "NO_RECONOCIDO")
        return Reconocimiento(
            estado,
            100 if completo else round(100 * sum(comprobaciones.values()) / len(comprobaciones)),
            [{"senal": k, "presente": v, "origen": "TEXTO_PDF_LOCAL"} for k, v in comprobaciones.items()],
        )

    def extraer_albaranes(self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]):
        # La colección autoritativa vive en cada factura para no perder la
        # pertenencia multifactura. No se publica un agregado sin factura.
        return []

    def extraer_facturas(self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]) -> list[dict[str, Any]]:
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        return [self._factura(documento, segmento) for segmento in segmentos]

    def _factura(self, documento: DocumentoLocal, segmento: SegmentoLocal) -> dict[str, Any]:
        paginas = [p for p in documento.paginas if segmento.paginas[0] <= p.numero <= segmento.paginas[1]]
        if not paginas or "PAGINA 01 DE" not in normalizar_texto(paginas[0].texto):
            return self._factura_layout_desconocido(documento, segmento)

        cabecera = self._cabecera(documento, paginas)
        impuestos, fiscal_aux = self._fiscalidad(documento, paginas[0])
        movimientos = self._movimientos(documento, paginas[0], fiscal_aux["filas_concepto"])
        candidatos = self._candidatos_fila(documento, paginas)
        relaciones = self._relaciones_documentales(candidatos, movimientos)
        relaciones_por_candidato = {
            r["candidato"]["orden"]: r for r in relaciones if r.get("inequivoca") is True
        }
        for candidato in candidatos:
            candidato["clasificacion_economica"] = clasificar_fila_economica_alliance(
                candidato, relaciones_por_candidato.get(candidato["orden"])
            )
        paginas_factura = list(range(segmento.paginas[0], segmento.paginas[1] + 1))
        albaranes = [a for c in candidatos if (a := promover_albaran_alliance(
            c, factura_documental=cabecera["numero_factura"]["valor"],
            paginas_factura=paginas_factura,
            segmentacion_inequivoca=segmento.estado == "DETERMINISTA",
        )) is not None]
        operaciones_economicas = self._operaciones_economicas(candidatos, relaciones_por_candidato)
        vencimientos = self._vencimientos(documento, paginas)
        otros = self._otros(documento, paginas[0], fiscal_aux)
        controles = self._controles(cabecera, impuestos, fiscal_aux, vencimientos)
        no_promovidos = sum(
            c["clasificacion_economica"]["concepto"] == "NO_DEMOSTRABLE"
            for c in candidatos
        )
        incidencias = ([{
            "codigo": "CANDIDATO_ALBARAN_NO_PROMOVIDO",
            "cantidad": no_promovidos,
            "bloqueante": False,
            "motivo": "FALTA_EVIDENCIA_POSITIVA_DE_ROL_O_SEGMENTACION",
        }] if no_promovidos else [])
        movimientos_sin_sentido = [m for m in movimientos if m["sentido"] is None]
        if movimientos_sin_sentido:
            incidencias.append({
                "codigo": "SENTIDO_NO_DOCUMENTADO",
                "cantidad": len(movimientos_sin_sentido),
                "bloqueante": False,
            })
        incidencias.extend([
            {"codigo": "MONEDA_NO_DOCUMENTADA", "bloqueante": False},
            {"codigo": "IMPORTE_VENCIMIENTO_NO_DOCUMENTADO", "cantidad": len(vencimientos), "bloqueante": False},
        ])
        return {
            "segmento": {
                "sha_documento": documento.sha_documento,
                "paginas": segmento.paginas,
                "identidad": cabecera["numero_factura"]["valor"],
                "estado": segmento.estado,
                "regla": segmento.regla,
                "evidencias": segmento.evidencias,
            },
            "layout": "ALLIANCE_FACTURA_DENSO_V1",
            "cabecera": cabecera,
            "candidatos_fila": candidatos,
            "albaranes": albaranes,
            "operaciones_economicas": operaciones_economicas,
            "movimientos": movimientos,
            "relaciones_documentales": relaciones,
            "impuestos": impuestos,
            "vencimientos": vencimientos,
            "otros": otros,
            "controles_conciliacion": controles,
            "incidencias": incidencias,
        }

    def _cabecera(self, documento: DocumentoLocal, paginas) -> dict[str, Any]:
        pagina = paginas[0]
        linea_identidad = self._linea_identidad(pagina)
        numero = next(p for p in linea_identidad.palabras if FACTURA_RE.fullmatch(p.texto))
        fechas = palabras_fecha(linea_identidad)
        tipo = next(l for l in pagina.lineas if "FACTURA DUPLICADO" in normalizar_texto(l.texto))
        nombre = next(l for l in pagina.lineas if normalizar_texto(l.texto).startswith("D/D"))
        direccion = next(l for l in pagina.lineas if "DIRECCI" in normalizar_texto(l.texto))
        cp = next(l for l in pagina.lineas if any(re.fullmatch(r"\d{5}", p.texto) for p in l.palabras) and l.bbox.x0 > 300)
        nif_linea = next(l for l in pagina.lineas if any(NIF_RE.fullmatch(p.texto) for p in l.palabras) and l.bbox.x0 > 300)
        nif = next(p for p in nif_linea.palabras if NIF_RE.fullmatch(p.texto))
        codigo = next((p for p in nif_linea.palabras if p.texto.isdigit() and p is not nif), None)
        proveedor_linea = next(l for l in pagina.lineas if "ALLIANCE HEALTHCARE" in normalizar_texto(l.texto))
        proveedor_words = [p for p in proveedor_linea.palabras if 80 <= p.bbox.x0 and p.bbox.x1 <= 172]
        proveedor_nif_linea = next(l for l in pagina.lineas if any(p.texto.upper() == "A50004324" for p in l.palabras))
        proveedor_nif = next(p for p in proveedor_nif_linea.palabras if p.texto.upper() == "A50004324")
        direccion_proveedor_lineas = sorted(
            [l for l in pagina.lineas if l.bbox.x1 <= 21 and 540 <= l.bbox.y0 <= 680],
            key=lambda l: l.bbox.y0,
            reverse=True,
        )
        direccion_proveedor_words = [p for l in direccion_proveedor_lineas for p in l.palabras]
        direccion_words = direccion.palabras[1:] + cp.palabras
        return {
            "proveedor": {
                "nombre": self.campo_documentado(documento, "ALLIANCE HEALTHCARE ESPANA, S.A.", proveedor_words, proveedor_linea, "cabecera", "proveedor_nombre", "RAZON_SOCIAL_EN_AVISO_PRIVACIDAD"),
                "nif": self.campo_documentado(documento, proveedor_nif.texto.upper(), [proveedor_nif], proveedor_nif_linea, "cabecera", "proveedor_nif", "NIF_LEGAL_VISIBLE"),
                "direccion": self.campo_multilinea(
                    documento,
                    "POL. IND. SECTOR 4 50830 VILLANUEVA DE GALLEGO (ZARAGOZA)",
                    direccion_proveedor_words,
                    direccion_proveedor_lineas,
                    "cabecera",
                    "proveedor_direccion",
                    "DOMICILIO_SOCIAL_VERTICAL",
                ),
            },
            "destinatario": {
                "nombre": self.campo_documentado(documento, " ".join(p.texto for p in nombre.palabras[1:]), nombre.palabras[1:], nombre, "cabecera", "destinatario_nombre", "BLOQUE_DESTINATARIO"),
                "nif": self.campo_documentado(documento, nif.texto, [nif], nif_linea, "cabecera", "destinatario_nif", "NIF_BLOQUE_DESTINATARIO"),
                "direccion": self.campo_documentado(documento, " ".join(p.texto for p in direccion_words), direccion_words, direccion, "cabecera", "destinatario_direccion", "BLOQUE_DIRECCION_DESTINATARIO"),
            },
            "numero_factura": self.campo_documentado(documento, numero.texto, [numero], linea_identidad, "cabecera", "numero_factura", "IDENTIDAD_ENTRE_FECHAS"),
            "fecha_factura": self.campo_documentado(documento, fecha_iso(fechas[0].texto), [fechas[0]], linea_identidad, "cabecera", "fecha_factura", "PRIMERA_FECHA_CABECERA", literal=fechas[0].texto),
            "fecha_vencimiento_cabecera": self.campo_documentado(documento, fecha_iso(fechas[1].texto), [fechas[1]], linea_identidad, "cabecera", "fecha_vencimiento", "SEGUNDA_FECHA_CABECERA", literal=fechas[1].texto),
            "tipo_documento": self.campo_documentado(documento, "FACTURA_DUPLICADO", tipo.palabras, tipo, "cabecera", "tipo_documento", "LITERAL_FACTURA_DUPLICADO"),
            "moneda": None,
            "codigo_cliente": self.campo_documentado(documento, codigo.texto, [codigo], nif_linea, "cabecera", "codigo_cliente", "CODIGO_TRAS_NIF") if codigo else None,
            "almacen_ruta": self._campo_linea_completa(documento, pagina, "ALMACEN", "almacen_ruta"),
            "importe_total": self._campo_total_etiquetado(documento, pagina, "TOTAL FACTURA", "importe_total"),
            "base_imponible_total": self._campo_total_etiquetado(documento, pagina, "TOTAL BASE IMPONIBLE", "base_imponible_total"),
            "iva_total": self._campo_total_etiquetado(documento, pagina, "TOTAL IVAS", "iva_total"),
            "recargo_equivalencia_total": self._campo_total_etiquetado(documento, pagina, "TOTAL RECARGOS EQUIVALENCIA", "recargo_equivalencia_total"),
            "otros_total": None,
            "forma_pago": None,
        }

    def _fiscalidad(self, documento: DocumentoLocal, pagina) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        titulo_compras = self._linea(pagina, "COMPRAS BASE IMPONIBLE IVA R.E. TOTALES")
        cabecera_compras = self._linea(pagina, "CONCEPTO 4 10 21 4 10 21 0,50 1,40 5,20")
        total_compras_label = self._linea(pagina, "TOTAL COMPRAS")
        total_compras_linea = next(l for l in pagina.lineas if l.orden > total_compras_label.orden and len(palabras_importe(l)) >= 4)
        titulo_gastos = self._linea(pagina, "GASTOS BASE IMPONIBLE IVA TOTALES")
        cabecera_gastos = next(l for l in pagina.lineas if l.orden > titulo_gastos.orden and "CONCEPTO" in normalizar_texto(l.texto))
        total_gastos = self._linea(pagina, "TOTAL GASTOS")

        anclas_compras = [p for p in cabecera_compras.palabras if p is not cabecera_compras.palabras[0]]
        anclas_compras.append(next(p for p in titulo_compras.palabras if normalizar_texto(p.texto) == "TOTALES"))
        valores_compras = self._valores_por_ancla(total_compras_linea, anclas_compras)
        tipos_iva = [4.0, 10.0, 21.0]
        tipos_re = [0.5, 1.4, 5.2]
        impuestos = []
        for i, tipo in enumerate(tipos_iva):
            base = valores_compras[i]
            if base is None:
                continue
            impuestos.append({
                "orden": len(impuestos) + 1,
                "origen": "COMPRAS",
                "base": self._campo_anclado(documento, total_compras_linea, base, "fiscalidad", "base", "TOTAL_COMPRAS_COLUMNA_BASE"),
                "tipo_iva": self._campo_porcentaje(documento, cabecera_compras, anclas_compras[i], tipo, "tipo_iva"),
                "cuota_iva": self._campo_anclado(documento, total_compras_linea, valores_compras[3 + i], "fiscalidad", "cuota_iva", "TOTAL_COMPRAS_COLUMNA_IVA"),
                "tipo_recargo_equivalencia": self._campo_porcentaje(documento, cabecera_compras, anclas_compras[6 + i], tipos_re[i], "tipo_recargo"),
                "cuota_recargo_equivalencia": self._campo_anclado(documento, total_compras_linea, valores_compras[6 + i], "fiscalidad", "cuota_recargo", "TOTAL_COMPRAS_COLUMNA_RE"),
                "total_tramo": None,
                "control_aritmetico": "OK",
            })

        filas_gasto = [
            l for l in pagina.lineas
            if cabecera_gastos.orden < l.orden < total_gastos.orden
            and l.bbox.x1 > 25 and len(palabras_importe(l)) >= 3
        ]
        anclas_gasto = [p for p in cabecera_gastos.palabras if p.texto in {"4", "10", "21"}]
        for fila in filas_gasto:
            valores = self._valores_por_ancla(fila, [*anclas_gasto, next(p for p in titulo_gastos.palabras if normalizar_texto(p.texto) == "TOTALES")])
            bases, cuotas, total = valores[:3], valores[3:6], valores[6]
            indices = [i for i, valor in enumerate(bases) if valor is not None]
            if len(indices) != 1:
                continue
            i = indices[0]
            impuestos.append({
                "orden": len(impuestos) + 1,
                "origen": "GASTOS",
                "base": self._campo_anclado(documento, fila, bases[i], "fiscalidad", "base", "GASTO_COLUMNA_BASE"),
                "tipo_iva": self._campo_porcentaje(documento, cabecera_gastos, anclas_gasto[i], tipos_iva[i], "tipo_iva"),
                "cuota_iva": self._campo_anclado(documento, fila, cuotas[i], "fiscalidad", "cuota_iva", "GASTO_COLUMNA_IVA"),
                "tipo_recargo_equivalencia": None,
                "cuota_recargo_equivalencia": None,
                "total_tramo": self._campo_anclado(documento, fila, total, "fiscalidad", "total_tramo", "GASTO_TOTAL_FILA"),
                "control_aritmetico": "OK",
            })
        filas_concepto = [
            l for l in pagina.lineas
            if cabecera_compras.orden < l.orden < total_compras_label.orden
            or cabecera_gastos.orden < l.orden < total_gastos.orden
        ]
        aux = {
            "total_compras": self._campo_anclado(documento, total_compras_linea, valores_compras[9], "totales", "total_compras", "TOTAL_COMPRAS_EXPLICITO"),
            "total_gastos": self._ultimo_importe(documento, total_gastos, "total_gastos"),
            "filas_concepto": filas_concepto,
            "impuestos_compras": [x for x in impuestos if x["origen"] == "COMPRAS"],
            "impuestos_gastos": [x for x in impuestos if x["origen"] == "GASTOS"],
        }
        return impuestos, aux

    def _movimientos(self, documento: DocumentoLocal, pagina, filas: list[LineaLocal]) -> list[dict[str, Any]]:
        salida = []
        for linea in filas:
            concepto_words = [p for p in linea.palabras if p.bbox.x0 > 20 and self._importe(p) is None]
            if not concepto_words:
                continue
            literal = " ".join(p.texto for p in concepto_words)
            normal = normalizar_texto(literal)
            clasificacion = clasificacion_conceptual_documental(literal)
            if clasificacion is not None:
                categoria, regla = clasificacion
                categoria_valor = categoria.value
            elif "CONDIC. COMERCIAL" in normal:
                categoria_valor, regla = "CONDICION_COMERCIAL", "ALLIANCE_CONDIC_COMERCIAL_LITERAL"
            else:
                continue
            importes = palabras_importe(linea)
            if len(importes) < 3:
                continue
            base, iva, recargo, total = self._componentes_movimiento(linea)
            seccion = self._seccion_documental_movimiento(documento, pagina, linea)
            sentido = sentido_desde_seccion_documental(
                seccion["literal_encabezado"]["valor"] if seccion else None,
                pertenencia_demostrada=seccion is not None,
            )
            decision_pio = documentar_sentido_decision_funcional_pio(literal) if sentido is None else None
            if decision_pio:
                sentido = decision_pio["valor"]
            salida.append({
                "orden": len(salida) + 1,
                "descripcion_literal": self.campo_documentado(documento, literal, concepto_words, linea, "movimientos", "descripcion", "CONCEPTO_ECONOMICO_VISIBLE"),
                "concepto_normalizado": normal.replace(".", "_").replace(" ", "_"),
                "categoria": categoria_valor,
                "origen_categoria": regla,
                "importe": self._campo_anclado(documento, linea, total, "movimientos", "importe", "TOTAL_FILA_MOVIMIENTO"),
                "base": self._campo_anclado(documento, linea, base, "movimientos", "base", "BASE_FILA_MOVIMIENTO"),
                "iva": self._campo_anclado(documento, linea, iva, "movimientos", "iva", "CUOTA_IVA_FILA_MOVIMIENTO"),
                "recargo": self._campo_anclado(documento, linea, recargo, "movimientos", "recargo", "CUOTA_RE_FILA_MOVIMIENTO") if recargo else None,
                "fecha": None,
                "seccion_documental": seccion,
                "pertenencia_demostrada": seccion is not None,
                "sentido": sentido,
                "sentido_fuente": "DECISION_FUNCIONAL_PIO" if decision_pio else ("SECCION_DIRECTA" if sentido else None),
                "sentido_documentacion": decision_pio,
                "provenance": {
                    "pagina": pagina.numero,
                    "bloque": seccion["nombre"] if seccion else "NO_DETERMINADO",
                    "regla_sentido": decision_pio["provenance"]["regla"] if decision_pio else "SOLO_SECCION_EXPLICITA_CARGO_O_ABONO",
                },
                "incidencias": [] if sentido else [{"codigo": "SENTIDO_NO_DOCUMENTADO"}],
            })
        return salida

    def _seccion_documental_movimiento(self, documento, pagina, linea):
        limites = (
            ("COMPRAS", self._linea(pagina, "COMPRAS BASE IMPONIBLE IVA R.E. TOTALES"), self._linea(pagina, "TOTAL COMPRAS")),
            ("GASTOS", self._linea(pagina, "GASTOS BASE IMPONIBLE IVA TOTALES"), self._linea(pagina, "TOTAL GASTOS")),
        )
        for nombre, encabezado, cierre in limites:
            if encabezado.orden < linea.orden < cierre.orden:
                literal = next(p for p in encabezado.palabras if normalizar_texto(p.texto) == nombre)
                return {
                    "nombre": nombre,
                    "literal_encabezado": self.campo_documentado(
                        documento,
                        literal.texto,
                        [literal],
                        encabezado,
                        "movimientos",
                        "seccion_documental",
                        "PERTENENCIA_GEOMETRICA_ENTRE_ENCABEZADO_Y_TOTAL",
                    ),
                    "pagina": pagina.numero,
                    "geometria_contexto": {
                        "bbox_encabezado": encabezado.bbox.to_list(),
                        "bbox_movimiento": linea.bbox.to_list(),
                        "bbox_cierre": cierre.bbox.to_list(),
                        "regla": "ORDEN_VERTICAL_ESTRICTO_ENTRE_ENCABEZADO_Y_TOTAL",
                    },
                    "provenance": {
                        "adaptador": self.id,
                        "version_adaptador": self.version,
                        "pagina": pagina.numero,
                    },
                }
        return None

    def _relaciones_documentales(self, candidatos, movimientos):
        """Relaciona objetos solo por conciliación económica exacta y única.

        La relación es de trazabilidad: no cambia, fusiona ni deduplica ninguno
        de los objetos. Solo habilita la propagación documental de sentido que
        se aplica en una fase posterior y nunca transfiere rol o categoría.
        """
        candidatos_por_clave: dict[tuple[float, float], list[dict[str, Any]]] = {}
        movimientos_por_clave: dict[tuple[float, float], list[dict[str, Any]]] = {}
        for candidato in candidatos:
            clave = (round(candidato["base"]["valor"], 2), round(candidato["total"]["valor"], 2))
            candidatos_por_clave.setdefault(clave, []).append(candidato)
        for movimiento in movimientos:
            clave = (round(movimiento["base"]["valor"], 2), round(movimiento["importe"]["valor"], 2))
            movimientos_por_clave.setdefault(clave, []).append(movimiento)

        relaciones = []
        for clave in sorted(candidatos_por_clave.keys() & movimientos_por_clave.keys()):
            candidatos_clave = candidatos_por_clave[clave]
            movimientos_clave = movimientos_por_clave[clave]
            if len(candidatos_clave) != 1 or len(movimientos_clave) != 1:
                continue
            candidato = candidatos_clave[0]
            movimiento = movimientos_clave[0]
            evidencias = [
                *candidato["numero_referencia"]["evidencias"],
                *candidato["base"]["evidencias"],
                *candidato["total"]["evidencias"],
                *movimiento["descripcion_literal"]["evidencias"],
                *movimiento["base"]["evidencias"],
                *movimiento["importe"]["evidencias"],
            ]
            relacion = {
                "orden": len(relaciones) + 1,
                "tipo_relacion": "CONCILIACION_ECONOMICA_EXACTA_UNICA_EN_FACTURA",
                "cardinalidad": "1:1",
                "inequivoca": True,
                "candidato": {
                    "tipo_objeto": "CANDIDATO_FILA",
                    "orden": candidato["orden"],
                    "identidad": candidato["numero_referencia"],
                    "pagina": candidato["provenance"]["pagina"],
                },
                "movimiento": {
                    "tipo_objeto": "MOVIMIENTO_COMERCIAL",
                    "orden": movimiento["orden"],
                    "identidad": movimiento["descripcion_literal"],
                    "categoria": movimiento["categoria"],
                    "sentido": movimiento.get("sentido"),
                    "pagina": movimiento["provenance"]["pagina"],
                },
                "valores_conciliados": {"base": clave[0], "total": clave[1]},
                "contexto_region": {
                    "factura": "MISMO_SEGMENTO_DOCUMENTAL",
                    "regla_unicidad": "UNA_FILA_Y_UN_MOVIMIENTO_CON_BASE_Y_TOTAL_EXACTOS",
                    "paginas": [candidato["provenance"]["pagina"], movimiento["provenance"]["pagina"]],
                    "bboxes": [evidencias[0].bbox_fila, evidencias[3].bbox_fila],
                },
                "evidencias": evidencias,
                "provenance": {
                    "adaptador": self.id,
                    "version_adaptador": self.version,
                    "regla": "BASE_Y_TOTAL_EXACTOS_UNICOS_DENTRO_DE_FACTURA",
                    "transferencia_sentido": "AUTORIZADA_SOLO_DESDE_SECCION_DOCUMENTADA",
                    "transferencia_rol": False,
                    "transferencia_categoria": False,
                    "fusion_entidades": False,
                    "mismo_hecho_economico": True,
                },
            }
            relaciones.append(relacion)
            self._aplicar_sentido_documental(candidato, movimiento, relacion)
        return relaciones

    def _operaciones_economicas(self, candidatos, relaciones_por_candidato):
        salida = []
        for candidato in candidatos:
            clasificacion = candidato["clasificacion_economica"]
            if clasificacion["concepto"] in {"ALBARAN_MERCANCIA", "NO_DEMOSTRABLE"}:
                continue
            relacion = relaciones_por_candidato.get(candidato["orden"])
            salida.append({
                "orden": len(salida) + 1,
                "referencia": candidato["numero_referencia"],
                "descripcion_literal": candidato["tipo_pedido"],
                "concepto": clasificacion["concepto"],
                "categoria": clasificacion["categoria_movimiento"] or "OTRO",
                "sentido": clasificacion["sentido"],
                "base": candidato["base"],
                "iva": None,
                "recargo": None,
                "importe": candidato["total"],
                "clasificacion_economica": clasificacion,
                "relacion_documental": relacion,
                "provenance": {
                    **candidato["provenance"],
                    "regla_clasificacion": clasificacion["regla"],
                    "referencia": candidato["numero_referencia"]["valor"],
                    "mismo_hecho_economico_resumen":
                        clasificacion["mismo_hecho_economico_resumen"],
                },
            })
        return salida

    def _aplicar_sentido_documental(self, candidato, movimiento, relacion):
        if movimiento["sentido"] is not None:
            return
        documentacion = documentar_sentido_desde_relacion(candidato, relacion)
        if documentacion is None:
            return
        movimiento["sentido"] = documentacion["valor"]
        movimiento["sentido_fuente"] = documentacion["sentido_fuente"]
        movimiento["sentido_documentacion"] = documentacion
        movimiento["provenance"]["regla_sentido"] = "SENTIDO_DERIVADO_RELACION_DOCUMENTAL"
        movimiento["incidencias"] = [
            incidencia
            for incidencia in movimiento["incidencias"]
            if incidencia.get("codigo") != "SENTIDO_NO_DOCUMENTADO"
        ]

    def _candidatos_fila(self, documento: DocumentoLocal, paginas) -> list[dict[str, Any]]:
        salida = []
        for pagina in paginas[1:]:
            encabezado = next((l for l in pagina.lineas if normalizar_texto(l.texto) == "CARGOS ABONOS"), None)
            if encabezado is None:
                continue
            cargos = next(p for p in encabezado.palabras if normalizar_texto(p.texto) == "CARGOS")
            abonos = next(p for p in encabezado.palabras if normalizar_texto(p.texto) == "ABONOS")
            cabecera_albaran = next((l for l in pagina.lineas
                if sum(normalizar_texto(p.texto) == "ALBARAN" for p in l.palabras) >= 2), None)
            for linea in pagina.lineas:
                for lado, palabras, sentido, titulo in (
                    ("IZQUIERDA", [p for p in linea.palabras if 25 <= p.bbox.x0 and p.bbox.x1 < pagina.ancho / 2], "CARGO", cargos),
                    ("DERECHA", [p for p in linea.palabras if p.bbox.x0 > pagina.ancho / 2], "ABONO", abonos),
                ):
                    item = self._candidato_lado(documento, linea, palabras, sentido, titulo, lado)
                    if item:
                        if cabecera_albaran is not None:
                            item["rol_documentacion"] = {
                                "valor": "ALBARAN",
                                "literal": cabecera_albaran.texto,
                                "regla": "COLUMNAS_NUMERO_ALBARAN_EXPLICITAS",
                                "evidencias": [self.evidencia(
                                    documento, pagina.numero, cabecera_albaran.texto,
                                    cabecera_albaran.bbox, cabecera_albaran.texto,
                                    cabecera_albaran.bbox, "candidatos_fila", "rol_fila",
                                    "COLUMNAS_NUMERO_ALBARAN_EXPLICITAS", "LITERAL_LOCAL",
                                )],
                            }
                        item["orden"] = len(salida) + 1
                        salida.append(item)
        return salida

    def _candidato_lado(self, documento, linea, palabras, sentido, titulo, lado):
        fechas = [p for p in palabras if re.fullmatch(r"\d{2}-\d{2}-\d{4}", p.texto)]
        refs = [p for p in palabras if REFERENCIA_FILA_RE.fullmatch(p.texto)]
        if len(fechas) != 1 or len(refs) != 1:
            return None
        fecha, referencia = fechas[0], refs[0]
        importes = [(p, self._importe(p)) for p in palabras if p.bbox.x0 > referencia.bbox.x1 and self._importe(p) is not None]
        if len(importes) != 2:
            return None
        tipo = [p for p in palabras if fecha.bbox.x1 < p.bbox.x0 < referencia.bbox.x0]
        if not tipo:
            return None
        base, total = importes
        return {
            "orden": 0,
            "numero_referencia": self.campo_documentado(documento, referencia.texto, [referencia], linea, "candidatos_fila", "numero_referencia", "IDENTIDAD_INDIVIDUAL_MISMA_FILA"),
            "fecha": self.campo_documentado(documento, fecha_iso(fecha.texto), [fecha], linea, "candidatos_fila", "fecha", "FECHA_MISMA_FILA", literal=fecha.texto),
            "tipo_pedido": self.campo_documentado(documento, " ".join(p.texto for p in tipo), tipo, linea, "candidatos_fila", "tipo_pedido", "LITERAL_ENTRE_FECHA_E_IDENTIDAD"),
            "base": self.campo_documentado(documento, base[1], [base[0]], linea, "candidatos_fila", "base", "PRIMER_IMPORTE_TRAS_IDENTIDAD"),
            "total": self.campo_documentado(documento, total[1], [total[0]], linea, "candidatos_fila", "total", "SEGUNDO_IMPORTE_TRAS_IDENTIDAD"),
            "sentido": self.campo_documentado(documento, sentido, [titulo], encabezado := self._linea_de_palabra(documento, titulo), "candidatos_fila", "sentido", "SECCION_DOCUMENTAL_CARGOS_ABONOS"),
            "rol_fila": "INDETERMINADO",
            "incidencias": [{"codigo": "ROL_FILA_INDETERMINADO"}],
            "provenance": {"pagina": linea.pagina, "lado_tabla": lado, "fila_literal": linea.texto},
        }

    def _vencimientos(self, documento: DocumentoLocal, paginas) -> list[dict[str, Any]]:
        salida = []
        for pagina in paginas:
            linea = self._linea_identidad(pagina)
            fechas = palabras_fecha(linea)
            fecha = fechas[1]
            salida.append({
                "orden": len(salida) + 1,
                "fecha": self.campo_documentado(documento, fecha_iso(fecha.texto), [fecha], linea, "vencimientos", "fecha", "OCURRENCIA_CABECERA_PAGINA", literal=fecha.texto),
                "importe": None,
                "medio_pago": None,
                "provenance": {"pagina": pagina.numero, "ocurrencia_documental": True},
            })
        return salida

    def _otros(self, documento, pagina, aux):
        compras = []
        for linea in aux["filas_concepto"]:
            if linea.bbox.y0 >= 450 or not palabras_importe(linea):
                continue
            concepto = [p for p in linea.palabras if p.bbox.x0 > 20 and self._importe(p) is None]
            if not concepto:
                continue
            compras.append({
                "descripcion": self.campo_documentado(documento, " ".join(p.texto for p in concepto), concepto, linea, "desglose_economico", "descripcion", "CONCEPTO_VISIBLE"),
                "valores": [self.campo_documentado(documento, valor, [palabra], linea, "desglose_economico", "valor", "IMPORTE_VISIBLE") for palabra, valor in palabras_importe(linea)],
            })
        adicionales = []
        for prefijo in ("R.D. 143,03", "IMPORTE ARTICULOS SUJETOS RDL"):
            linea = next((l for l in pagina.lineas if normalizar_texto(l.texto).startswith(normalizar_texto(prefijo))), None)
            if linea:
                adicionales.append({
                    "tipo": "INFORMACION_ECONOMICA_ADICIONAL",
                    "literal": self.campo_documentado(documento, linea.texto, [p for p in linea.palabras if p.bbox.x0 > 20], linea, "otros", "literal", "FILA_ECONOMICA_VISIBLE"),
                    "valores": [valor for _, valor in palabras_importe(linea)],
                })
        return [{
            "tipo": "RESUMEN_ECONOMICO_ALLIANCE",
            "total_compras": aux["total_compras"],
            "total_gastos": aux["total_gastos"],
            "desglose_conceptos": compras,
        }, *adicionales]

    def _controles(self, cabecera, impuestos, aux, vencimientos):
        compras = aux["impuestos_compras"]
        gastos = aux["impuestos_gastos"]
        especificaciones = [
            EspecificacionConciliacion("TOTAL_COMPRAS_DESDE_TRAMOS", "TOTAL_COMPRAS", self._comp_campo("TOTAL_COMPRAS", aux["total_compras"], "resumen_compras"), [self._comp_tramo(f"TRAMO_{i}", x, "COMPRAS") for i, x in enumerate(compras, 1)], {"regla_relacion": "COLUMNAS_FISCALES_IMPRESAS"}),
            EspecificacionConciliacion("TOTAL_GASTOS_DESDE_TRAMOS", "TOTAL_GASTOS", self._comp_campo("TOTAL_GASTOS", aux["total_gastos"], "resumen_gastos"), [self._comp_tramo(f"GASTO_{i}", x, "GASTOS") for i, x in enumerate(gastos, 1)], {"regla_relacion": "FILAS_GASTOS_IMPRESAS"}),
            EspecificacionConciliacion("TOTAL_DESDE_FISCALIDAD", "TOTAL_FACTURA", self._comp_campo("TOTAL", cabecera["importe_total"], "totales"), [self._comp_campo("BASE", cabecera["base_imponible_total"], "totales"), self._comp_campo("IVA", cabecera["iva_total"], "totales"), self._comp_campo("RE", cabecera["recargo_equivalencia_total"], "totales")], {"regla_relacion": "BASE_MAS_IVA_MAS_RE"}),
            EspecificacionConciliacion("FILAS_VS_TOTAL_COMPRAS", "TOTAL_COMPRAS", self._comp_campo("TOTAL_COMPRAS", aux["total_compras"], "resumen_compras"), [ComponenteConciliacion("FILAS_CON_ROL_DEMOSTRADO", None, None, "candidatos_fila", None)], {"regla_relacion": "NO_EVALUABLE_POR_ROL_INDETERMINADO"}),
            EspecificacionConciliacion("VENCIMIENTOS_VS_TOTAL", "TOTAL_FACTURA", self._comp_campo("TOTAL", cabecera["importe_total"], "totales"), [ComponenteConciliacion("VENCIMIENTOS_CON_IMPORTE", None, None, "vencimientos", vencimientos[0]["provenance"]["pagina"])], {"regla_relacion": "NO_EVALUABLE_IMPORTE_NO_DOCUMENTADO"}),
        ]
        return evaluar_conciliaciones(especificaciones)

    def _campo_total_etiquetado(self, documento, pagina, etiqueta, columna):
        linea = self._linea(pagina, etiqueta)
        normal = [normalizar_texto(p.texto) for p in linea.palabras]
        partes = normalizar_texto(etiqueta).split()
        inicio = next(i for i in range(len(normal)) if normal[i:i + len(partes)] == partes)
        palabra, valor = next((p, self._importe(p)) for p in linea.palabras[inicio + len(partes):] if self._importe(p) is not None)
        return self.campo_documentado(documento, valor, [palabra], linea, "totales", columna, "VALOR_TRAS_ETIQUETA")

    def _campo_linea_completa(self, documento, pagina, etiqueta, columna):
        linea = self._linea(pagina, etiqueta)
        palabras = [p for p in linea.palabras if p.bbox.x0 > 20]
        return self.campo_documentado(documento, " ".join(p.texto for p in palabras), palabras, linea, "cabecera", columna, "LINEA_DOCUMENTAL_COMPLETA")

    def _campo_anclado(self, documento, linea, dato, tabla, columna, regla):
        if dato is None:
            return None
        palabra, valor = dato
        return self.campo_documentado(documento, valor, [palabra], linea, tabla, columna, regla)

    def _campo_porcentaje(self, documento, linea, palabra, valor, columna):
        return self.campo_documentado(documento, valor, [palabra], linea, "fiscalidad", columna, "PORCENTAJE_IMPRESO", literal=palabra.texto)

    def _ultimo_importe(self, documento, linea, columna):
        palabra, valor = palabras_importe(linea)[-1]
        return self.campo_documentado(documento, valor, [palabra], linea, "totales", columna, "TOTAL_FILA_EXPLICITO")

    def _componentes_movimiento(self, linea):
        importes = palabras_importe(linea)
        base = importes[0]
        total = importes[-1]
        iva = importes[-2] if len(importes) == 3 else importes[-3]
        recargo = importes[-2] if len(importes) >= 4 else None
        return base, iva, recargo, total

    @staticmethod
    def _valores_por_ancla(linea, anclas):
        salida = [None] * len(anclas)
        centros = [(p.bbox.x0 + p.bbox.x1) / 2 for p in anclas]
        for palabra, valor in palabras_importe(linea):
            centro = (palabra.bbox.x0 + palabra.bbox.x1) / 2
            indice = min(range(len(centros)), key=lambda i: abs(centros[i] - centro))
            salida[indice] = (palabra, valor)
        return salida

    @staticmethod
    def _importe(palabra: PalabraLocal):
        from ..geometria.lineas import parsear_importe
        return parsear_importe(palabra.texto)

    @staticmethod
    def _linea(pagina, texto):
        objetivo = normalizar_texto(texto)
        return next(l for l in pagina.lineas if objetivo in normalizar_texto(l.texto))

    @staticmethod
    def _linea_identidad(pagina):
        return next(
            l for l in pagina.lineas
            if any(FACTURA_RE.fullmatch(p.texto) for p in l.palabras)
            and len(palabras_fecha(l)) == 2
        )

    @staticmethod
    def _linea_de_palabra(documento, palabra):
        return next(l for l in documento.paginas[palabra.pagina - 1].lineas if palabra in l.palabras)

    @staticmethod
    def _comp_campo(concepto, campo, fuente):
        if campo is None:
            return ComponenteConciliacion(concepto, None, None, fuente, None)
        ev = campo.get("evidencias", [])
        pagina = ev[0].pagina if ev else None
        return ComponenteConciliacion(concepto, campo["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", fuente, pagina, ev)

    def _comp_tramo(self, concepto, tramo, fuente):
        valores = [tramo["base"], tramo["cuota_iva"], tramo.get("cuota_recargo_equivalencia")]
        total = sum((x["valor"] for x in valores if x is not None), 0.0)
        evidencias = [ev for x in valores if x is not None for ev in x.get("evidencias", [])]
        return ComponenteConciliacion(concepto, round(total, 2), "SIGNOS_DOCUMENTALES_CONSERVADOS", fuente, evidencias[0].pagina if evidencias else None, evidencias)

    @staticmethod
    def _factura_layout_desconocido(documento, segmento):
        return {
            "segmento": {"sha_documento": documento.sha_documento, "paginas": segmento.paginas},
            "layout": None,
            "cabecera": {},
            "candidatos_fila": [],
            "albaranes": [],
            "movimientos": [],
            "impuestos": [],
            "vencimientos": [],
            "otros": [],
            "controles_conciliacion": [],
            "incidencias": [{"codigo": "LAYOUT_DESCONOCIDO", "bloqueante": True}],
        }
