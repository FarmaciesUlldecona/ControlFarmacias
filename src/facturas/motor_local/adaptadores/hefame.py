from __future__ import annotations

import re
from typing import Any

from ..conciliacion import ComponenteConciliacion, EspecificacionConciliacion
from ..geometria.campos import fecha_iso, lineas_con_texto, palabras_fecha, palabras_importe
from ..geometria.lineas import normalizar_texto
from ..modelos import AlbaranLocal, DocumentoLocal, PalabraLocal, union_bbox
from .base import AdaptadorBase, Reconocimiento


NIF_RE = re.compile(r"^(?:[A-Z]\d{8}|\d{8}[A-Z])$")
ALBARAN_RE = re.compile(r"^\d{10}$")


class AdaptadorHefame(AdaptadorBase):
    id = "hefame-local"
    version = "1.1.0"
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
                salida.append(AlbaranLocal(
                    ids[0].texto, fecha_iso(fechas[0].texto), None,
                    [valores[x] for x in etiquetas[:3]], valores["TOTAL_BASES"], None,
                    "DETALLE_ALBARAN", pagina.numero, len(salida) + 1, evidencias,
                    {x: valores[x] for x in etiquetas[:3]},
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
                salida.append(self._movimiento(documento, linea, concepto_words, importes, fecha_word=fechas[0], concepto=concepto))
        servicios = lineas_con_texto(documento.paginas[0].lineas, "Resumen Servicios Operativos")
        if len(servicios) == 1:
            linea = servicios[0]
            importes = palabras_importe(linea)
            palabras = [p for p in linea.palabras if p.bbox.x1 < importes[0][0].bbox.x0]
            salida.append(self._movimiento(documento, linea, palabras, importes, fecha_word=None, concepto="SERVICIOS_OPERATIVOS"))
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
        abo_devo = self._movimiento_por_concepto(movimientos, "ABONO_DEVOLUCION")
        aproafa = self._movimiento_por_concepto(movimientos, "APROAFA")
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
                ],
                {"regla_relacion": "MISMO_BLOQUE_RELACION_ALBARANES_DOC_ENTREGA_Y_SUBTOTAL_PEDIDOS"},
            ),
            EspecificacionConciliacion(
                "BASE_IMPONIBLE_DESDE_BLOQUES",
                "BASE_IMPONIBLE",
                base_imponible,
                [self._componente_resumen("PEDIDOS", pedidos), self._componente_resumen("SERVICIOS_OPERATIVOS", servicios)],
                {"regla_relacion": "DESGLOSE_IMPORTES_PEDIDOS_MAS_RESUMEN_SERVICIOS_OPERATIVOS"},
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

    def _movimiento(self, documento, linea, concepto_words, importes, *, fecha_word, concepto):
        categorias = {
            "ABONO_DEVOLUCION": "DEVOLUCION_MERCANCIA",
            "APROAFA": "CONDICION_COMERCIAL",
            "SERVICIOS_OPERATIVOS": "SERVICIO",
        }
        return {
            "orden": 0,
            "descripcion_literal": self._campo(documento, " ".join(p.texto for p in concepto_words), concepto_words, linea, "movimientos", "descripcion", "LITERAL_CONCEPTO"),
            "concepto_normalizado": concepto,
            "categoria": categorias.get(concepto, "OTRO"),
            "origen_categoria": "NORMALIZACION_DE_DESCRIPCION_SIN_INFERIR_SENTIDO",
            "sentido": None,
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
