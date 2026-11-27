from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from src.facturas.grupos_funcionales import clasificar_grupo_hefame
import datetime

from src.facturas.hefame_economia import (
    CARGO_COOPERATIVO_BASE_S_R,
    FISCALIDAD_HEFAME,
    derivar_magnitud_comparable_hefame,
)

from ..conciliacion import ComponenteConciliacion, EspecificacionConciliacion
from ..geometria.campos import fecha_iso, lineas_con_texto, palabras_fecha, palabras_importe
from ..geometria.lineas import normalizar_texto
from ..modelos import AlbaranLocal, DocumentoLocal, PalabraLocal, union_bbox
from .base import AdaptadorBase, Reconocimiento


NIF_RE = re.compile(r"^(?:[A-Z]\d{8}|\d{8}[A-Z])$")
# DISENO HEFAME §4.1: albaranes de 10 dígitos (41…), documentos de entrega de 7 dígitos (desde octubre) y números de
# 9 dígitos que empiezan por 91 (H4).
ALBARAN_RE = re.compile(r"^(?:\d{10}|\d{7}|91\d{7})$")
_POR_CONCEPTO = object()  # sentido del movimiento: el que fija su concepto (decisiones de Pio)
TOLERANCIA_PAGINA2 = Decimal("0.01")  # F0-6: por componente, solo en lo que el lector recalcula


def _d(valor) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"))


class AdaptadorHefame(AdaptadorBase):
    id = "hefame-local"
    # 1.3.0 (FACTURAS-0, 2026-11-27; pruebas/auditoria_hefame/DISENO.md y decisiones H1-H7, F0-4, F0-6): RE No. 5,2 %,
    # cargo cooperativo de 80,00 en fin de mes (H1/H6), liquidaciones comerciales como ABONO (H3), APROAFA negativo
    # falla cerrado (H7), sentido de ABO/DEVO por signo neto y controles de la pagina 2 (0,01 en lo recalculado,
    # exacto en lo impreso). Sin autoridad productiva.
    version = "1.3.0"
    capacidades = {
        "segmentacion": "SOPORTADO_MULTIPAGINA_DETERMINISTA",
        "cabecera": "SOPORTADO_PARCIAL_MONEDA_NO_DOCUMENTADA",
        "albaranes": "SOPORTADO",
        "movimientos": "SOPORTADO_SENTIDO_DOCUMENTAL_O_NULL",
        "impuestos": "SOPORTADO_PARCIAL_TIPOS_NO_EXPLICITOS",
        "vencimientos": "SOPORTADO",
        "otros": "SOPORTADO",
        "conciliacion_documental": "SOPORTADO",
    }

    def reconocer(self, documento: DocumentoLocal) -> Reconocimiento:
        normal = normalizar_texto("\n".join(p.texto for p in documento.paginas))
        comprobaciones = {
            "identidad_legal_visible": "HDAD.FMCTCA.MEDIT.,S.C.L." in normal,
            "cif_visible": bool(re.search(r"\bCIF:\s*[A-Z]\d{8}\b", normal)),
            "relacion_albaranes": "RELACION ALBARANES/DOC.ENTREGA" in normal,
            "tabla_bases": all(x in normal for x in ("BASE S.R", "BASE RE", "BASE NO", "TOTAL BASES")),
            "desglose_factura": "DESGLOSE IMPORTES TOTAL FACTURA" in normal,
            "vencimientos": "RESUMEN DE VENCIMIENTOS" in normal,
            "paginacion_interna": bool(re.search(r"PAGINA\s+1\s*/\s*\d+", normal)),
        }
        presentes = sum(comprobaciones.values())
        reconocido = all(comprobaciones.values())
        indicios = comprobaciones["identidad_legal_visible"] or comprobaciones["relacion_albaranes"]
        estado = "RECONOCIDO" if reconocido else ("AMBIGUO" if indicios else "NO_RECONOCIDO")
        return Reconocimiento(
            estado,
            100 if reconocido else round(100 * presentes / len(comprobaciones)),
            [{"senal": clave, "presente": valor, "origen": "TEXTO_PDF_LOCAL"} for clave, valor in comprobaciones.items()],
        )

    def extraer_cabecera(self, documento: DocumentoLocal, segmentos) -> dict[str, Any]:
        if self.reconocer(documento).estado != "RECONOCIDO":
            return {}
        pagina = documento.paginas[0]
        proveedor_nombre = pagina.lineas[0]
        proveedor_nif = lineas_con_texto(pagina.lineas, "CIF:")[0]
        proveedor_direccion = pagina.lineas[2:4]
        linea_tipo = lineas_con_texto(pagina.lineas, "Factura")[0]
        linea_nombre_fecha = lineas_con_texto(pagina.lineas, "Fecha")[0]
        linea_numero = lineas_con_texto(pagina.lineas, "Número")[0]
        linea_direccion = pagina.lineas[7]
        linea_cp = pagina.lineas[8]
        linea_provincia = pagina.lineas[10]
        nif_destino = next(p for p in linea_tipo.palabras if NIF_RE.fullmatch(p.texto))
        codigo_cliente = linea_tipo.palabras[0]
        tipo = linea_tipo.palabras[-1]
        fecha = palabras_fecha(linea_nombre_fecha)[0]
        numero = next(p for p in linea_numero.palabras if re.fullmatch(r"\d{10}", p.texto))
        nombre_words = [p for p in linea_nombre_fecha.palabras if p.bbox.x1 < 400]
        direccion_words = [*linea_direccion.palabras, *linea_cp.palabras, linea_provincia.palabras[0]]
        proveedor_dir_words = [*proveedor_direccion[0].palabras, *proveedor_direccion[1].palabras[:2]]
        total_line = lineas_con_texto(documento.paginas[1].lineas, "Total Factura")[-1]
        total_word, total = palabras_importe(total_line)[0]
        fiscal_lines = {
            "base_imponible_total": lineas_con_texto(documento.paginas[1].lineas, "Base imponible")[0],
            "iva_total": lineas_con_texto(documento.paginas[1].lineas, "IVA")[0],
            "recargo_equivalencia_total": lineas_con_texto(documento.paginas[1].lineas, "Rec. Equiv.")[0],
            "otros_total": lineas_con_texto(documento.paginas[1].lineas, "Gastos giro")[0],
        }
        pago_line = self._lineas_vencimiento(documento)[0]
        pago_fecha = palabras_fecha(pago_line)[0]
        pago_words = [p for p in pago_line.palabras if p.bbox.x1 < pago_fecha.bbox.x0]
        identidad_funcional = clasificar_grupo_hefame(
            proveedor_documental="HDAD.FMCTCA.MEDIT.,S.C.L.",
            nif_documental=proveedor_nif.palabras[-1].texto,
            layout=self.id,
        )
        if identidad_funcional is None:
            raise ValueError("IDENTIDAD_FUNCIONAL_HEFAME_MERCANCIA_NO_DEMOSTRADA")
        fallos = [c for c in self.controles_pagina2(documento, segmentos) if c["resultado"] != "OK"]
        if fallos:
            raise ValueError("CONTROL_PAGINA2_HEFAME:" + ";".join(
                f"{c['codigo']}:{c.get('calculado')}/{c.get('impreso')}" for c in fallos))
        return {
            "proveedor": {
                "nombre": self._campo(documento, proveedor_nombre.texto, proveedor_nombre.palabras, proveedor_nombre, "cabecera", "proveedor_nombre", "LITERAL_RAZON_SOCIAL"),
                "nif": self._campo(documento, proveedor_nif.palabras[-1].texto, [proveedor_nif.palabras[-1]], proveedor_nif, "cabecera", "proveedor_nif", "TOKEN_TRAS_CIF"),
                "direccion": self._campo(documento, " ".join(p.texto for p in proveedor_dir_words), proveedor_dir_words, proveedor_direccion[0], "cabecera", "proveedor_direccion", "BLOQUE_DIRECCION_PROVEEDOR"),
            },
            "destinatario": {
                "nombre": self._campo(documento, " ".join(p.texto for p in nombre_words), nombre_words, linea_nombre_fecha, "cabecera", "destinatario_nombre", "BLOQUE_DESTINATARIO"),
                "nif": self._campo(documento, nif_destino.texto, [nif_destino], linea_tipo, "cabecera", "destinatario_nif", "NIF_EN_BLOQUE_DESTINATARIO"),
                "direccion": self._campo(documento, " ".join(p.texto for p in direccion_words), direccion_words, linea_direccion, "cabecera", "destinatario_direccion", "BLOQUE_DIRECCION_DESTINATARIO"),
            },
            "numero_factura": self._campo(documento, numero.texto, [numero], linea_numero, "cabecera", "numero_factura", "TOKEN_TRAS_NUMERO"),
            "fecha_factura": self._campo(documento, fecha_iso(fecha.texto), [fecha], linea_nombre_fecha, "cabecera", "fecha_factura", "TOKEN_TRAS_FECHA", literal=fecha.texto),
            "tipo_documento": self._campo(documento, normalizar_texto(tipo.texto), [tipo], linea_tipo, "cabecera", "tipo_documento", "LITERAL_TIPO_DOCUMENTO"),
            "moneda": None,
            "importe_total": self._campo(documento, total, [total_word], total_line, "fiscalidad", "importe_total", "TOTAL_FACTURA_EXPLICITO"),
            "base_imponible_total": self._total_fila(documento, fiscal_lines["base_imponible_total"], "base_imponible_total"),
            "iva_total": self._total_fila(documento, fiscal_lines["iva_total"], "iva_total"),
            "recargo_equivalencia_total": self._total_fila(documento, fiscal_lines["recargo_equivalencia_total"], "recargo_equivalencia_total"),
            "otros_total": self._total_fila(documento, fiscal_lines["otros_total"], "otros_total"),
            "forma_pago": self._campo(documento, " ".join(p.texto for p in pago_words), pago_words, pago_line, "vencimientos", "forma_pago", "LITERAL_VIA_PAGO"),
            "codigo_cliente": self._campo(documento, codigo_cliente.texto, [codigo_cliente], linea_tipo, "cabecera", "codigo_cliente", "TOKEN_BLOQUE_DESTINATARIO"),
            "grupo_funcional": identidad_funcional.to_dict(),
        }

    def extraer_albaranes(self, documento: DocumentoLocal, segmentos):
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        salida = []
        for pagina in documento.paginas:
            for linea in pagina.lineas:
                fechas = palabras_fecha(linea)
                ids = [p for p in linea.palabras if ALBARAN_RE.fullmatch(p.texto)]
                importes = palabras_importe(linea)
                if len(fechas) != 1 or len(ids) != 1 or len(importes) != 4:
                    continue
                etiquetas = ("BASE_S_R", "BASE_RE", "BASE_NO", "TOTAL_BASES")
                valores = {etiqueta: valor for etiqueta, (_, valor) in zip(etiquetas, importes, strict=True)}
                base_words = [p for p, _ in importes[:3]]
                evidencias = {
                    "numero_albaran": self.evidencia(documento, pagina.numero, ids[0].texto, ids[0].bbox, linea.texto, linea.bbox, "relacion_albaranes", "numero_albaran", "TOKEN_NUMERICO_BAJO_COLUMNA_ALBARAN", "LITERAL_LOCAL"),
                    "fecha": self.evidencia(documento, pagina.numero, fechas[0].texto, fechas[0].bbox, linea.texto, linea.bbox, "relacion_albaranes", "fecha", "FECHA_MISMA_FILA", "LITERAL_LOCAL"),
                    "base": self.evidencia(documento, pagina.numero, "+".join(p.texto for p in base_words), union_bbox([p.bbox for p in base_words]), linea.texto, linea.bbox, "relacion_albaranes", "bases", "COLUMNAS_BASE_EXPLICITAS", "LITERAL_LOCAL"),
                    "total": self.evidencia(documento, pagina.numero, importes[-1][0].texto, importes[-1][0].bbox, linea.texto, linea.bbox, "relacion_albaranes", "total_bases", "TOTAL_BASES_MISMA_FILA", "LITERAL_LOCAL"),
                    "sentido": None,
                }
                for etiqueta, (palabra, _) in zip(etiquetas[:3], importes[:3], strict=True):
                    evidencias[etiqueta] = self.evidencia(
                        documento, pagina.numero, palabra.texto, palabra.bbox, linea.texto, linea.bbox,
                        "relacion_albaranes", etiqueta, f"VALOR_BAJO_COLUMNA_{etiqueta}", "LITERAL_LOCAL",
                    )
                categorias_no_cero = [
                    etiqueta for etiqueta in etiquetas[:3] if valores[etiqueta] != 0
                ]
                atributos = {
                    "numero_documental": ids[0].texto,
                    "fecha_documental": fecha_iso(fechas[0].texto),
                    "importe_documental": valores["TOTAL_BASES"],
                    "magnitud_documental": "BASE_NETA",
                    "provenance": {
                        "fuente": "RELACION_ALBARANES_DOC_ENTREGA",
                        "pagina": pagina.numero,
                        "fila_literal": linea.texto,
                        "regla": "TOTAL_BASES_NO_ES_PUC_NI_PVP",
                    },
                }
                if len(categorias_no_cero) == 1:
                    atributos.update({
                        clave: float(valor) if isinstance(valor, Decimal) else valor
                        for clave, valor in derivar_magnitud_comparable_hefame(
                            valores["TOTAL_BASES"], categorias_no_cero[0],
                        ).items()
                    })
                salida.append(AlbaranLocal(
                    ids[0].texto, fecha_iso(fechas[0].texto), None,
                    [valores[x] for x in etiquetas[:3]], valores["TOTAL_BASES"], None,
                    "DETALLE_ALBARAN", pagina.numero, len(salida) + 1, evidencias,
                    {x: valores[x] for x in etiquetas[:3]}, atributos,
                ))
        return salida

    def extraer_movimientos(self, documento: DocumentoLocal, segmentos):
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        salida = []
        for linea in documento.paginas[0].lineas:
            fechas = palabras_fecha(linea)
            importes = palabras_importe(linea)
            if len(fechas) == 1 and len(importes) == 4:
                concepto_words = [p for p in linea.palabras if p.bbox.x0 > fechas[0].bbox.x1 and p.bbox.x1 < importes[0][0].bbox.x0]
                if len(concepto_words) != 1 or ALBARAN_RE.fullmatch(concepto_words[0].texto):
                    continue
                literal = concepto_words[0].texto
                concepto = {"ABO/DEVO": "ABONO_DEVOLUCION", "APROAFA": "APROAFA"}.get(normalizar_texto(literal), normalizar_texto(literal))
                if concepto == "APROAFA" and any(valor < 0 for _, valor in importes):
                    raise ValueError("APROAFA_NEGATIVO_H7")
                sentido = self._sentido_neto(importes) if concepto == "ABONO_DEVOLUCION" else _POR_CONCEPTO
                salida.append(self._movimiento(documento, linea, concepto_words, importes, fecha_word=fechas[0], concepto=concepto, sentido=sentido))
        liquidaciones = lineas_con_texto(documento.paginas[0].lineas, "Resumen Liquidaciones Comerciales")
        if len(liquidaciones) == 1:
            linea = liquidaciones[0]
            importes = palabras_importe(linea)
            if len(importes) == 4 and importes[3][1] != 0:
                # H3 (Pio, 2026-11-19): pequeños descuentos sobre especialidad (IVA 4 %, base S.R.) = ABONO.
                if importes[1][1] != 0 or importes[2][1] != 0 or importes[3][1] > 0:
                    raise ValueError("LIQUIDACION_COMERCIAL_FUERA_DE_H3")
                palabras = [p for p in linea.palabras if p.bbox.x1 < importes[0][0].bbox.x0]
                salida.append(self._movimiento(documento, linea, palabras, importes, fecha_word=None, concepto="LIQUIDACIONES_COMERCIALES"))
        servicios = lineas_con_texto(documento.paginas[0].lineas, "Resumen Servicios Operativos")
        if len(servicios) == 1:
            linea = servicios[0]
            importes = palabras_importe(linea)
            palabras = [p for p in linea.palabras if p.bbox.x1 < importes[0][0].bbox.x0]
            salida.append(self._movimiento(documento, linea, palabras, importes, fecha_word=None, concepto="SERVICIOS_OPERATIVOS"))
        comision = self._extraer_comision_hefame(documento, segmentos, salida)
        if comision is not None:
            salida.append(comision)
        for orden, item in enumerate(salida, 1):
            item["orden"] = orden
        return salida

    def extraer_impuestos(self, documento: DocumentoLocal, segmentos):
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        pagina = documento.paginas[1]
        filas = {
            "base": lineas_con_texto(pagina.lineas, "Base imponible")[0],
            "iva": lineas_con_texto(pagina.lineas, "IVA")[0],
            "recargo": lineas_con_texto(pagina.lineas, "Rec. Equiv.")[0],
            "total": lineas_con_texto(pagina.lineas, "Totales")[0],
        }
        valores = {clave: palabras_importe(linea) for clave, linea in filas.items()}
        categorias = ("BASE_S_R", "BASE_RE", "BASE_NO", "BASE_EX")
        cabecera_fiscal = lineas_con_texto(pagina.lineas, "Base S.R.", "Base Re.", "Base No.", "Base Ex.")[0]
        palabras_cabecera = cabecera_fiscal.palabras
        grupos_cabecera = (palabras_cabecera[0:2], palabras_cabecera[2:4], palabras_cabecera[4:6], palabras_cabecera[6:8])
        salida = []
        for indice, categoria in enumerate(categorias):
            item = {
                "orden": indice + 1,
                "categoria_base": self._campo(
                    documento, categoria, list(grupos_cabecera[indice]), cabecera_fiscal,
                    "desglose_fiscal", "categoria_base", "ENCABEZADO_COLUMNA_FISCAL",
                ),
                "tipo_iva": None,
                "tipo_recargo_equivalencia": None,
            }
            for clave, destino in (("base", "base"), ("iva", "cuota_iva"), ("recargo", "cuota_recargo_equivalencia"), ("total", "total_tramo")):
                palabra, valor = valores[clave][indice]
                item[destino] = self._campo(documento, valor, [palabra], filas[clave], "desglose_fiscal", destino, f"COLUMNA_{categoria}")
            suma = item["base"]["valor"] + item["cuota_iva"]["valor"] + item["cuota_recargo_equivalencia"]["valor"]
            item["control_aritmetico"] = "OK" if round(suma - item["total_tramo"]["valor"], 2) == 0 else "NO_OK"
            salida.append(item)
        return salida

    def extraer_vencimientos(self, documento: DocumentoLocal, segmentos):
        salida = []
        for orden, linea in enumerate(self._lineas_vencimiento(documento), 1):
            fecha = palabras_fecha(linea)[0]
            importe_word, importe = palabras_importe(linea)[0]
            medio_words = [p for p in linea.palabras if p.bbox.x1 < fecha.bbox.x0]
            salida.append({
                "orden": orden,
                "fecha": self._campo(documento, fecha_iso(fecha.texto), [fecha], linea, "vencimientos", "fecha", "FECHA_FILA_VENCIMIENTO", literal=fecha.texto),
                "importe": self._campo(documento, importe, [importe_word], linea, "vencimientos", "importe", "IMPORTE_FILA_VENCIMIENTO"),
                "medio_pago": self._campo(documento, " ".join(p.texto for p in medio_words), medio_words, linea, "vencimientos", "medio_pago", "LITERAL_ANTES_FECHA"),
            })
        return salida

    def extraer_otros(self, documento: DocumentoLocal, segmentos):
        salida = []
        for linea in documento.paginas[0].lineas:
            normal = normalizar_texto(linea.texto)
            if not normal.startswith(("DESGLOSE IMPORTES PEDIDOS", "DESGLOSE IMPORTES AUTOCONSUMO", "RESUMEN LIQUIDACIONES COMERCIALES", "RESUMEN SERVICIOS OPERATIVOS")):
                continue
            importes = palabras_importe(linea)
            if len(importes) != 4:
                continue
            concepto_words = [p for p in linea.palabras if p.bbox.x1 < importes[0][0].bbox.x0]
            salida.append({
                "tipo": "RESUMEN_ECONOMICO",
                "concepto": normalizar_texto(" ".join(p.texto for p in concepto_words)),
                "descripcion_literal": self._campo(documento, " ".join(p.texto for p in concepto_words), concepto_words, linea, "resumen_economico", "descripcion", "LITERAL_CONCEPTO_RESUMEN"),
                "bases": {
                    etiqueta: self._campo(documento, valor, [palabra], linea, "resumen_economico", etiqueta, f"COLUMNA_{etiqueta}")
                    for etiqueta, (palabra, valor) in zip(("BASE_S_R", "BASE_RE", "BASE_NO", "TOTAL_BASES"), importes, strict=True)
                },
            })
        return salida

    def extraer_facturas(self, documento: DocumentoLocal, segmentos):
        if self.reconocer(documento).estado != "RECONOCIDO" or len(segmentos) != 1:
            return []
        cabecera = self.extraer_cabecera(documento, segmentos)
        segmento = segmentos[0]
        return [{
            "layout": "HEFAME_MERCANCIA_FACTURA_V2",
            "segmento": {
                "sha_documento": documento.sha_documento,
                "paginas": segmento.paginas,
                "identidad": cabecera["numero_factura"]["valor"],
                "estado": segmento.estado,
                "regla": segmento.regla,
                "evidencias": segmento.evidencias,
            },
            "clasificacion_documental": {
                "tipo": "FACTURA_MERCANCIA",
                "tipo_funcional": "HEFAME_MERCANCIA",
                "grupo_funcional": "HEFAME",
                "requiere_conciliacion_albaranes": True,
            },
            "albaranes": [],
            "movimientos": [],
            "impuestos": [],
            "vencimientos": [],
            "otros": [],
            "incidencias": [],
        }]

    def declarar_conciliaciones(
        self,
        documento,
        segmentos,
        *,
        cabecera,
        albaranes,
        movimientos,
        impuestos,
        vencimientos,
        otros,
        facturas,
    ):
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []

        pedidos = self._resumen(otros, "DESGLOSE IMPORTES PEDIDOS")
        servicios = self._resumen(otros, "RESUMEN SERVICIOS OPERATIVOS")
        autoconsumo = self._resumen(otros, "DESGLOSE IMPORTES AUTOCONSUMO")
        liquidaciones = self._resumen(otros, "RESUMEN LIQUIDACIONES COMERCIALES")
        abo_devo = self._movimiento_por_concepto(movimientos, "ABONO_DEVOLUCION")
        aproafa = self._movimiento_por_concepto(movimientos, "APROAFA")
        comision = self._movimiento_por_concepto(movimientos, "COMISION_HEFAME")
        total_factura = self._componente_campo("TOTAL_FACTURA", cabecera.get("importe_total"), "cabecera.total_factura")
        base_imponible = self._componente_campo(
            "BASE_IMPONIBLE", cabecera.get("base_imponible_total"), "desglose_fiscal.base_imponible",
            columnas=self._columnas_impuestos(impuestos, "base"),
        )
        iva = self._componente_campo("IVA", cabecera.get("iva_total"), "desglose_fiscal.iva")
        recargo = self._componente_campo("RECARGO_EQUIVALENCIA", cabecera.get("recargo_equivalencia_total"), "desglose_fiscal.recargo")
        gastos = self._componente_campo("GASTOS_GIRO", cabecera.get("otros_total"), "desglose_fiscal.gastos_giro")
        vencimiento = self._componente_campo(
            "VENCIMIENTO", vencimientos[0].get("importe") if len(vencimientos) == 1 else None, "resumen_vencimientos",
        )

        return [
            EspecificacionConciliacion(
                "PEDIDOS_DESDE_DETALLE",
                "PEDIDOS",
                self._componente_resumen("PEDIDOS", pedidos),
                [
                    self._componente_albaranes(albaranes),
                    self._componente_movimiento("ABO_DEVO", abo_devo),
                    self._componente_movimiento("APROAFA", aproafa),
                    self._componente_movimiento("COMISION_HEFAME", comision),
                ],
                {"regla_relacion": "MISMO_BLOQUE_RELACION_ALBARANES_DOC_ENTREGA_Y_SUBTOTAL_PEDIDOS"},
            ),
            EspecificacionConciliacion(
                "BASE_IMPONIBLE_DESDE_BLOQUES",
                "BASE_IMPONIBLE",
                base_imponible,
                [self._componente_resumen("PEDIDOS", pedidos), self._componente_resumen("SERVICIOS_OPERATIVOS", servicios),
                 *([self._componente_resumen("AUTOCONSUMO", autoconsumo)] if autoconsumo else []),
                 *([self._componente_resumen("LIQUIDACIONES_COMERCIALES", liquidaciones)] if liquidaciones else [])],
                {"regla_relacion": "PEDIDOS_MAS_AUTOCONSUMO_LIQUIDACIONES_Y_SERVICIOS_OPERATIVOS"},
            ),
            EspecificacionConciliacion(
                "TOTAL_FACTURA_DESDE_FISCALIDAD",
                "TOTAL_FACTURA",
                total_factura,
                [base_imponible, iva, recargo, gastos],
                {"regla_relacion": "BLOQUE_DESGLOSE_IMPORTES_TOTAL_FACTURA"},
            ),
            EspecificacionConciliacion(
                "VENCIMIENTO_DESDE_TOTAL_FACTURA",
                "VENCIMIENTO",
                vencimiento,
                [total_factura],
                {"regla_relacion": "FACTURA_UNICA_Y_RESUMEN_VENCIMIENTO_UNICO"},
            ),
        ]

    def incidencias_extraccion(self, documento: DocumentoLocal, segmentos):
        movimientos = self.extraer_movimientos(documento, segmentos)
        albaranes = self.extraer_albaranes(documento, segmentos)
        return [
            {"codigo": "MONEDA_NO_DOCUMENTADA", "bloqueante": False, "cantidad": 1},
            {"codigo": "TIPOS_FISCALES_NO_DOCUMENTADOS", "bloqueante": False, "cantidad": 4},
            {"codigo": "SENTIDO_NO_DOCUMENTADO", "bloqueante": False, "coleccion": "albaranes", "cantidad": len(albaranes)},
            {"codigo": "SENTIDO_NO_DOCUMENTADO", "bloqueante": False, "coleccion": "movimientos", "cantidad": len(movimientos)},
        ]

    def _extraer_comision_hefame(self, documento, segmentos, movimientos):
        """Materializa la diferencia Base S.R. autorizada sin fijar su importe."""
        pedidos = lineas_con_texto(documento.paginas[0].lineas, "Desglose importes pedidos")
        if len(pedidos) != 1:
            return None
        linea = pedidos[0]
        importes = palabras_importe(linea)
        if len(importes) != 4:
            return None
        categorias = ("BASE_S_R", "BASE_RE", "BASE_NO")
        objetivo = {categoria: importes[i][1] for i, categoria in enumerate(categorias)}
        albaranes = self.extraer_albaranes(documento, segmentos)
        detalle = {
            categoria: round(sum(a.bases_por_categoria.get(categoria, 0.0) for a in albaranes), 2)
            for categoria in categorias
        }
        incluidos = [
            m for m in movimientos
            if m.get("concepto_normalizado") in {"ABONO_DEVOLUCION", "APROAFA"}
        ]
        for categoria in categorias:
            detalle[categoria] = round(
                detalle[categoria]
                + sum(m["bases"][categoria]["valor"] for m in incluidos),
                2,
            )
        diferencias = {categoria: _d(objetivo[categoria]) - _d(detalle[categoria]) for categoria in categorias}
        if all(valor == 0 for valor in diferencias.values()):
            return None
        fecha = datetime.date.fromisoformat(self._fecha_factura(documento))
        fin_de_mes = (fecha + datetime.timedelta(days=1)).day == 1
        if not (fin_de_mes and diferencias["BASE_S_R"] == CARGO_COOPERATIVO_BASE_S_R
                and diferencias["BASE_RE"] == 0 and diferencias["BASE_NO"] == 0):
            # H1/H6 (Pio): solo 80,00 de base S.R. en la factura de fin de mes; cualquier otro desfase para el lector.
            raise ValueError("DESFASE_PEDIDOS_NO_AUTORIZADO_H6:" + ",".join(
                f"{c}={v}" for c, v in diferencias.items()) + f":fin_de_mes={fin_de_mes}")
        comision = derivar_magnitud_comparable_hefame(diferencias["BASE_S_R"], "BASE_S_R")

        base = float(comision["base_neta"])
        evidencia_objetivo = self.evidencia(
            documento, linea.pagina, importes[0][0].texto, importes[0][0].bbox,
            linea.texto, linea.bbox, "resumen_economico", "BASE_S_R",
            "DIFERENCIA_ENTRE_SUBTOTAL_PEDIDOS_Y_DETALLE", "LITERAL_LOCAL",
        )
        evidencias = [evidencia_objetivo]
        campo_base = {
            "valor": base,
            "literal": "DIFERENCIA BASE_S_R DERIVADA DEL SUBTOTAL",
            "evidencias": evidencias,
        }
        cero = {"valor": 0.0, "literal": "SIN DIFERENCIA", "evidencias": evidencias}
        return {
            "orden": 0,
            "descripcion_literal": {
                "valor": "CARGO_COOPERATIVO_HEFAME",
                "literal": "DECISION_PIO_H1_CARGO_COOPERATIVO_80_BASE_S_R_FIN_DE_MES",
                "evidencias": evidencias,
            },
            "concepto_normalizado": "COMISION_HEFAME",
            "categoria": "CARGO",
            "origen_categoria": "DECISION_PIO_H1",
            "sentido": "CARGO",
            "fecha": None,
            "bases": {
                "BASE_S_R": campo_base,
                "BASE_RE": cero,
                "BASE_NO": cero,
                "TOTAL_BASES": campo_base,
            },
            "importe": campo_base,
            "magnitud_documental": "BASE_NETA",
            "categoria_fiscal": "BASE_S_R",
            "iva_pct": float(comision["iva_pct"]),
            "re_pct": float(comision["re_pct"]),
            "importe_iva_derivado": float(comision["importe_iva_derivado"]),
            "importe_re_derivado": float(comision["importe_re_derivado"]),
            "importe_fiscal_total": float(comision["importe_comparable_operativo"]),
            "no_albaran": True,
            "requiere_match_operativo": False,
            "periodicidad": "MENSUAL_FIN_DE_MES",
            "provenance": {
                "autoridad_funcional": "PIO_H1_2026_11_18",
                "fuente_documental": "DESGLOSE_IMPORTES_PEDIDOS_BASE_S_R",
                "calculo": {
                    "subtotal_base_sr": objetivo["BASE_S_R"],
                    "detalle_base_sr": detalle["BASE_S_R"],
                    "diferencia": base,
                },
                "computar_una_sola_vez": True,
            },
        }

    @staticmethod
    def _fecha_factura(documento: DocumentoLocal) -> str:
        linea = lineas_con_texto(documento.paginas[0].lineas, "Fecha")[0]
        return fecha_iso(palabras_fecha(linea)[0].texto)

    @staticmethod
    def _fila_resumen(lineas, texto: str, n: int) -> list[Decimal] | None:
        """Importes de la primera línea que contiene ``texto`` y tiene exactamente ``n`` importes."""
        for linea in lineas_con_texto(lineas, texto):
            importes = palabras_importe(linea)
            if len(importes) == n:
                return [_d(valor) for _, valor in importes]
        return None

    def controles_pagina2(self, documento: DocumentoLocal, segmentos) -> list[dict[str, Any]]:
        """DISENO §2.5 con F0-6: página 2 frente a página 1, por clase. ``FALLO`` en cualquier control para el lector.

        Recalculado (tolerancia 0,01 por componente): base = pedidos + autoconsumo + liquidaciones + servicios; IVA =
        base × tipo; RE = (base − servicios) × tipo. Impreso (exacto): Σ bases de cada fila = Total Bases; totales por
        clase = base + IVA + RE + gastos; Σ totales por clase = Total Factura = Σ vencimientos; Base Ex. y gastos 0.
        """
        p1, p2 = documento.paginas[0].lineas, documento.paginas[1].lineas
        controles: list[dict[str, Any]] = []

        def control(codigo, calculado, impreso, tolerancia=Decimal("0")):
            ok = calculado is not None and impreso is not None and abs(calculado - impreso) <= tolerancia
            controles.append({"codigo": codigo, "resultado": "OK" if ok else "FALLO", "calculado": str(calculado),
                              "impreso": str(impreso), "tolerancia": str(tolerancia)})

        for albaran in self.extraer_albaranes(documento, segmentos):
            control(f"FILA_{albaran.numero_albaran}_TOTAL_BASES",
                    sum((_d(v) for v in albaran.bases_por_categoria.values()), Decimal("0")), _d(albaran.total))
        pedidos = self._fila_resumen(p1, "Desglose importes pedidos", 4)
        cero = [Decimal("0")] * 4
        autoconsumo = self._fila_resumen(p1, "Desglose importes autoconsumo", 4) or cero
        liquidaciones = self._fila_resumen(p1, "Resumen Liquidaciones Comerciales", 4) or cero
        servicios = self._fila_resumen(p1, "Resumen Servicios Operativos", 4) or cero
        filas = {clave: self._fila_resumen(p2, texto, 5) for clave, texto in (
            ("base", "Base imponible"), ("iva", "IVA"), ("re", "Rec. Equiv."), ("gastos", "Gastos giro"),
            ("totales", "Totales"))}
        if pedidos is None or any(v is None for v in filas.values()):
            controles.append({"codigo": "ESTRUCTURA_PAGINAS", "resultado": "FALLO",
                              "faltan": [k for k, v in {"pedidos": pedidos, **filas}.items() if v is None]})
            return controles
        tolerancia = TOLERANCIA_PAGINA2
        for i, categoria in enumerate(("BASE_S_R", "BASE_RE", "BASE_NO")):
            iva_pct, re_pct = FISCALIDAD_HEFAME[categoria]
            base = filas["base"][i]
            control(f"{categoria}_BASE", pedidos[i] + autoconsumo[i] + liquidaciones[i] + servicios[i], base, tolerancia)
            control(f"{categoria}_IVA", (base * iva_pct / 100).quantize(Decimal("0.01")), filas["iva"][i], tolerancia)
            control(f"{categoria}_RE", ((base - servicios[i]) * re_pct / 100).quantize(Decimal("0.01")),
                    filas["re"][i], tolerancia)
            control(f"{categoria}_TOTAL_CLASE",
                    base + filas["iva"][i] + filas["re"][i] + filas["gastos"][i], filas["totales"][i])
        for clave in ("base", "iva", "re", "totales"):
            control(f"BASE_EX_{clave.upper()}_CERO", Decimal("0"), filas[clave][3])
        control("GASTOS_GIRO_CERO", Decimal("0"), sum(filas["gastos"][:4], Decimal("0")))
        total_linea = lineas_con_texto(p2, "Total Factura")[-1]
        total_factura = _d(palabras_importe(total_linea)[0][1])
        control("SUMA_TOTALES_CLASE_TOTAL_FACTURA", sum(filas["totales"][:4], Decimal("0")), total_factura)
        vencimientos = [_d(palabras_importe(linea)[0][1]) for linea in self._lineas_vencimiento(documento)]
        control("TOTAL_FACTURA_VENCIMIENTOS", sum(vencimientos, Decimal("0")) if vencimientos else None, total_factura)
        return controles

    def _lineas_vencimiento(self, documento: DocumentoLocal):
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        return [
            linea for pagina in documento.paginas for linea in pagina.lineas
            if len(palabras_fecha(linea)) == 1 and len(palabras_importe(linea)) == 1
            and any(p.bbox.x0 < palabras_fecha(linea)[0].bbox.x0 for p in linea.palabras)
            and normalizar_texto(linea.texto).startswith("ADEUDOS")
        ]

    def _campo(self, documento, valor, palabras: list[PalabraLocal], linea, tabla, columna, regla, *, literal=None):
        literal = " ".join(p.texto for p in palabras) if literal is None else literal
        return {
            "valor": valor,
            "literal": literal,
            "evidencias": [self.evidencia(
                documento, linea.pagina, literal, union_bbox([p.bbox for p in palabras]),
                linea.texto, linea.bbox, tabla, columna, regla, "LITERAL_LOCAL",
            )],
        }

    @staticmethod
    def _sentido_neto(importes):
        """ABO/DEVO (DISENO §2.3): el del signo neto; ``None`` si el neto es 0 o los signos se mezclan entre clases."""
        signos = {valor > 0 for _, valor in importes[:3] if valor != 0}
        total = importes[3][1]
        if len(signos) > 1 or total == 0:
            return None
        return "CARGO" if total > 0 else "ABONO"

    def _movimiento(self, documento, linea, concepto_words, importes, *, fecha_word, concepto, sentido=None):
        sentido = _POR_CONCEPTO if sentido is None and concepto != "ABONO_DEVOLUCION" else sentido
        categorias = {
            "ABONO_DEVOLUCION": "ABONO_O_DEVOLUCION_NO_DESAMBIGUADO",
            "APROAFA": "OTRO_CONCEPTO_DEMOSTRADO",
            "SERVICIOS_OPERATIVOS": "SERVICIO",
            "COMISION_HEFAME": "CARGO",
            "LIQUIDACIONES_COMERCIALES": "DESCUENTO",
        }
        sentidos = {
            "ABONO_DEVOLUCION": "ABONO",
            "APROAFA": "CARGO",
            "SERVICIOS_OPERATIVOS": "CARGO",
            "COMISION_HEFAME": "CARGO",
            "LIQUIDACIONES_COMERCIALES": "ABONO",
        }
        return {
            "orden": 0,
            "descripcion_literal": self._campo(documento, " ".join(p.texto for p in concepto_words), concepto_words, linea, "movimientos", "descripcion", "LITERAL_CONCEPTO"),
            "concepto_normalizado": concepto,
            "categoria": categorias.get(concepto, "OTRO"),
            "origen_categoria": "NORMALIZACION_DE_DESCRIPCION_SIN_INFERIR_SENTIDO",
            "sentido": sentidos.get(concepto) if sentido is _POR_CONCEPTO else sentido,
            "fecha": self._campo(documento, fecha_iso(fecha_word.texto), [fecha_word], linea, "movimientos", "fecha", "FECHA_MISMA_FILA", literal=fecha_word.texto) if fecha_word else None,
            "bases": {
                etiqueta: self._campo(documento, valor, [palabra], linea, "movimientos", etiqueta, f"COLUMNA_{etiqueta}")
                for etiqueta, (palabra, valor) in zip(("BASE_S_R", "BASE_RE", "BASE_NO", "TOTAL_BASES"), importes, strict=True)
            },
            "importe": self._campo(documento, importes[-1][1], [importes[-1][0]], linea, "movimientos", "importe", "TOTAL_BASES_MISMA_FILA"),
        }

    @staticmethod
    def _resumen(otros, concepto):
        return next((item for item in otros if item.get("concepto") == concepto), None)

    @staticmethod
    def _movimiento_por_concepto(movimientos, concepto):
        return next((item for item in movimientos if item.get("concepto_normalizado") == concepto), None)

    @staticmethod
    def _signo(campo):
        if not campo:
            return None
        literal = str(campo.get("literal", "")).strip()
        return "NEGATIVO_EXPLICITO" if literal.endswith("-") else "SIN_MARCA_NEGATIVA"

    @classmethod
    def _componente_campo(cls, concepto, campo, fuente, *, columnas=None):
        if not campo:
            return ComponenteConciliacion(concepto, None, None, fuente, None, [], columnas or {})
        evidencias = campo.get("evidencias", [])
        pagina = evidencias[0].pagina if evidencias else None
        return ComponenteConciliacion(
            concepto, campo.get("valor"), cls._signo(campo), fuente, pagina, evidencias, columnas or {},
        )

    @classmethod
    def _componente_resumen(cls, concepto, resumen):
        if not resumen:
            return ComponenteConciliacion(concepto, None, None, "resumen_economico", None)
        total = resumen["bases"].get("TOTAL_BASES")
        columnas = {
            nombre: campo.get("valor") for nombre, campo in resumen["bases"].items()
        }
        return cls._componente_campo(concepto, total, "resumen_economico", columnas=columnas)

    @classmethod
    def _componente_movimiento(cls, concepto, movimiento):
        if not movimiento:
            return ComponenteConciliacion(concepto, None, None, "movimientos", None)
        columnas = {nombre: campo.get("valor") for nombre, campo in movimiento["bases"].items()}
        return cls._componente_campo(concepto, movimiento.get("importe"), "movimientos", columnas=columnas)

    @staticmethod
    def _componente_albaranes(albaranes):
        if not albaranes:
            return ComponenteConciliacion("ALBARANES", None, None, "relacion_albaranes", None)
        columnas = {
            nombre: round(sum(item.bases_por_categoria.get(nombre, 0.0) for item in albaranes), 2)
            for nombre in ("BASE_S_R", "BASE_RE", "BASE_NO")
        }
        columnas["TOTAL_BASES"] = round(sum(item.total or 0.0 for item in albaranes), 2)
        evidencias = [
            evidencia
            for item in albaranes
            for evidencia in (item.evidencias.get("total"),)
            if evidencia is not None
        ]
        paginas = {item.pagina for item in albaranes}
        return ComponenteConciliacion(
            "ALBARANES", columnas["TOTAL_BASES"], "SUMA_DE_SIGNOS_DOCUMENTALES",
            "relacion_albaranes", next(iter(paginas)) if len(paginas) == 1 else None,
            evidencias, columnas,
        )

    @staticmethod
    def _columnas_impuestos(impuestos, campo):
        salida = {}
        for item in impuestos:
            categoria = item.get("categoria_base", {}).get("valor")
            valor = item.get(campo, {}).get("valor")
            if categoria:
                salida[categoria] = valor
        salida["TOTAL_BASES"] = round(sum(valor for valor in salida.values() if valor is not None), 2)
        return salida

    def _total_fila(self, documento, linea, columna):
        palabra, valor = palabras_importe(linea)[-1]
        return self._campo(documento, valor, [palabra], linea, "desglose_fiscal", columna, "ULTIMA_COLUMNA_TOTAL_EXPLICITA")
