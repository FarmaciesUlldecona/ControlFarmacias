from __future__ import annotations

import re
from typing import Any

from ..conciliacion import ComponenteConciliacion, EspecificacionConciliacion, evaluar_conciliaciones
from ..geometria.campos import fecha_iso, palabras_fecha, palabras_importe
from ..geometria.lineas import DATE_RE, normalizar_texto, parsear_importe
from ..geometria.tablas import zonas_relativas
from ..modelos import AlbaranLocal, DocumentoLocal, SegmentoLocal, union_bbox
from .base import AdaptadorBase, Reconocimiento


FACTURA_RE = re.compile(r"^\d{8,12}$")
NIF_RE = re.compile(r"^(?:[A-Z]\d{8}|\d{8}[A-Z])$", re.I)


def documentar_sentido_decision_funcional_pio_cofares(
    descripcion_literal: str,
    categoria: str,
) -> dict[str, Any] | None:
    """Documenta decisiones de Pio exclusivas de COFARES.

    La decision no se presenta como evidencia directa del PDF. En particular,
    la regla general de servicios no se comparte con otros proveedores.
    """
    literal = normalizar_texto(descripcion_literal)
    if categoria == "SERVICIO":
        sentido, regla = "CARGO", "SERVICIOS_COFARES_SON_CARGO_DECISION_PIO"
    elif literal == "TOTAL DEVOLUCIONES":
        sentido, regla = "ABONO", "TOTAL_DEVOLUCIONES_COFARES_DECISION_PIO"
    elif literal == "CARGO PARAFARMACIA":
        sentido, regla = "CARGO", "CARGO_PARAFARMACIA_COFARES_DECISION_PIO"
    elif literal == "DTO. ADICIONAL LABORATORIO":
        sentido, regla = "ABONO", "DTO_ADICIONAL_LABORATORIO_COFARES_DECISION_PIO"
    else:
        return None
    return {
        "valor": sentido,
        "autoridad": "PIO",
        "fuente": "DECISION_FUNCIONAL_PIO",
        "tipo_evidencia": "DECISION_FUNCIONAL_PIO",
        "evidencia_documental_directa": False,
        "proveedor": "COFARES",
        "literal": descripcion_literal,
        "regla": regla,
        "alcance": "SOLO_COFARES",
    }


class AdaptadorCofares(AdaptadorBase):
    """Extractor conservador de los layouts COFARES auditados."""

    id = "cofares-local"
    version = "2.1.0"
    capacidades = {
        "segmentacion": "SOPORTADO_MONOPAGINA_MULTILAYOUT",
        "cabecera": "SOPORTADO_NULLS_DOCUMENTALES",
        "albaranes": "SOPORTADO",
        "movimientos": "SOPORTADO_SENTIDO_DOCUMENTAL_O_DECISION_PIO_O_NULL",
        "impuestos": "SOPORTADO_TIPOS_IMPRESOS",
        "vencimientos": "SOPORTADO_OCURRENCIAS_DOCUMENTALES",
        "otros": "SOPORTADO",
        "conciliacion_documental": "SOPORTADO",
    }

    def reconocer(self, documento: DocumentoLocal) -> Reconocimiento:
        texto = normalizar_texto("\n".join(p.texto for p in documento.paginas))
        checks = {
            "identidad_proveedor": "GRUPO COFARES" in texto,
            "titulo_factura": bool(re.search(r"\bFACTURA\b", texto)),
            "identidad_factura": bool(re.search(r"\b\d{8,12}\b", texto)),
            "cabecera_cliente": "CLIENTE:" in texto and "NIF:" in texto,
            "cabecera_fecha": "FECHA FACTURACI" in texto,
            "fiscalidad": "TOTAL BASES" in texto and "TOTAL FACTURA" in texto,
            "layout_conocido": self._layout(documento) is not None,
            "monopagina": len(documento.paginas) == 1,
            "texto_nativo": bool(documento.paginas) and all(p.palabras and p.texto.strip() for p in documento.paginas),
        }
        legacy = all((
            checks["identidad_proveedor"],
            "RESUMEN DE SUMINISTROS" in texto,
            "F.PEDIDO" in texto,
            bool(re.search(r"N.?\s*ALBAR", texto)),
            "TOTAL" in texto,
            "BASE" in texto,
            "T.PED" in texto,
            checks["monopagina"],
        ))
        completo = all(checks.values()) or legacy
        indicios = checks["identidad_proveedor"] or checks["layout_conocido"]
        return Reconocimiento(
            "RECONOCIDO" if completo else ("AMBIGUO" if indicios else "NO_RECONOCIDO"),
            100 if completo else round(100 * sum(checks.values()) / len(checks)),
            [{"senal": k, "presente": v, "origen": "TEXTO_PDF_LOCAL"} for k, v in checks.items()],
        )

    def extraer_facturas(self, documento, segmentos):
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        if "FECHA FACTURACI" not in normalizar_texto(documento.paginas[0].texto):
            return []
        return [self._factura(documento, s) for s in segmentos]

    def _primera(self, documento, segmentos):
        if self.reconocer(documento).estado != "RECONOCIDO" or len(segmentos) != 1:
            return None
        if "FECHA FACTURACI" not in normalizar_texto(documento.paginas[0].texto):
            return None
        return self._factura(documento, segmentos[0])

    def extraer_cabecera(self, documento, segmentos):
        f = self._primera(documento, segmentos)
        return f["cabecera"] if f else {}

    def extraer_albaranes(self, documento, segmentos):
        if self.reconocer(documento).estado != "RECONOCIDO" or self._layout(documento) != "COFARES_SUMINISTROS_V1":
            return []
        return self._albaranes(documento, documento.paginas[0])

    def extraer_movimientos(self, documento, segmentos):
        f = self._primera(documento, segmentos)
        return f["movimientos"] if f else []

    def extraer_impuestos(self, documento, segmentos):
        f = self._primera(documento, segmentos)
        return f["impuestos"] if f else []

    def extraer_vencimientos(self, documento, segmentos):
        f = self._primera(documento, segmentos)
        return f["vencimientos"] if f else []

    def extraer_otros(self, documento, segmentos):
        f = self._primera(documento, segmentos)
        return f["otros"] if f else []

    def _factura(self, documento, segmento):
        pagina = documento.paginas[segmento.paginas[0] - 1]
        layout = self._layout(documento)
        if layout is None:
            return self._desconocido(documento, segmento)
        cabecera = self._cabecera(documento, pagina, layout)
        impuestos = self._fiscalidad(documento, pagina)
        albaranes = self._albaranes(documento, pagina) if layout == "COFARES_SUMINISTROS_V1" else []
        movimientos = self._movimientos(documento, pagina, layout)
        vencimientos = self._vencimientos(documento, pagina, cabecera)
        otros = self._otros(documento, pagina, cabecera, layout)
        incidencias = [
            {"codigo": "PROVEEDOR_NIF_NO_DOCUMENTADO", "bloqueante": False},
            {"codigo": "PROVEEDOR_DIRECCION_NO_DOCUMENTADA", "bloqueante": False},
            {"codigo": "MONEDA_NO_DOCUMENTADA", "bloqueante": False},
            {"codigo": "IMPORTE_VENCIMIENTO_NO_DOCUMENTADO", "cantidad": 1, "bloqueante": False},
        ]
        sin_sentido = sum(m["sentido"] is None for m in movimientos)
        if sin_sentido:
            incidencias.append({"codigo": "SENTIDO_NO_DOCUMENTADO", "cantidad": sin_sentido, "bloqueante": False})
        sin_importe = sum(m["importe"] is None for m in movimientos)
        if sin_importe:
            incidencias.append({"codigo": "IMPORTE_MOVIMIENTO_NO_DOCUMENTADO", "cantidad": sin_importe, "bloqueante": False})
        return {
            "segmento": {"sha_documento": documento.sha_documento, "paginas": segmento.paginas,
                         "identidad": cabecera["numero_factura"]["valor"], "estado": segmento.estado,
                         "regla": segmento.regla, "evidencias": segmento.evidencias},
            "layout": layout, "cabecera": cabecera, "albaranes": albaranes,
            "movimientos": movimientos, "impuestos": impuestos, "vencimientos": vencimientos,
            "otros": otros, "controles_conciliacion": self._controles(cabecera, impuestos, vencimientos),
            "incidencias": incidencias,
        }

    def _cabecera(self, documento, pagina, layout):
        nline = next(l for l in pagina.lineas if l.bbox.y0 < 50 and any(FACTURA_RE.fullmatch(p.texto) for p in l.palabras))
        numero = next(p for p in nline.palabras if FACTURA_RE.fullmatch(p.texto))
        cliente = self._linea(pagina, "CLIENTE:")
        codigo = next(p for p in cliente.palabras if p.texto.isdigit())
        nif = next(p for p in cliente.palabras if NIF_RE.fullmatch(p.texto))
        izquierdas = sorted((l for l in pagina.lineas if cliente.orden < l.orden and l.bbox.x1 < 200), key=lambda l: l.orden)
        nombre, direccion = izquierdas[0], izquierdas[1:3]
        direccion_words = [p for l in direccion for p in l.palabras]
        fecha_linea = self._linea(pagina, "FECHA FACTURACI")
        fecha = palabras_fecha(fecha_linea)[0]
        periodo = self._linea(pagina, "PERIODO FACTURACI")
        periodo_fechas = palabras_fecha(periodo)
        venc_linea = self._linea(pagina, "VENCIMIENTO")
        venc = palabras_fecha(venc_linea)[0]
        proveedor = self._linea(pagina, "GRUPO COFARES Y SUS")
        tipo = next((l for l in pagina.lineas if "RECTIFICADA DE CONDICIONES COMERCIALES" in normalizar_texto(l.texto)), None)
        if tipo:
            tipo_valor, tipo_words = "FACTURA_RECTIFICATIVA_CONDICIONES_COMERCIALES", tipo.palabras
        else:
            tipo = self._linea(pagina, "FACTURA")
            tipo_valor, tipo_words = "FACTURA", [tipo.palabras[0]]
        forma = self._despues(fecha_linea, "PAGO:")
        via = self._despues(periodo, "PAGO:")
        banco = next((l for l in pagina.lineas if "*" in l.texto), None)
        return {
            "proveedor": {"nombre": self.campo_documentado(documento, "GRUPO COFARES", proveedor.palabras[:2], proveedor, "cabecera", "proveedor_nombre", "RAZON_SOCIAL_VISIBLE_EN_PIE"), "nif": None, "direccion": None},
            "destinatario": {
                "nombre": self.campo_documentado(documento, nombre.texto, nombre.palabras, nombre, "cabecera", "destinatario_nombre", "LINEA_TRAS_CLIENTE"),
                "nif": self.campo_documentado(documento, nif.texto, [nif], cliente, "cabecera", "destinatario_nif", "NIF_ETIQUETADO"),
                "direccion": self.campo_multilinea(documento, " ".join(p.texto for p in direccion_words), direccion_words, direccion, "cabecera", "destinatario_direccion", "DOS_LINEAS_TRAS_DESTINATARIO")},
            "numero_factura": self.campo_documentado(documento, numero.texto, [numero], nline, "cabecera", "numero_factura", "NUMERO_JUNTO_TITULO_FACTURA"),
            "fecha_factura": self.campo_documentado(documento, fecha_iso(fecha.texto), [fecha], fecha_linea, "cabecera", "fecha_factura", "FECHA_FACTURACION_ETIQUETADA", literal=fecha.texto),
            "tipo_documento": self.campo_documentado(documento, tipo_valor, tipo_words, tipo, "cabecera", "tipo_documento", "TIPO_DOCUMENTAL_LITERAL"),
            "moneda": None,
            "codigo_cliente": self.campo_documentado(documento, codigo.texto, [codigo], cliente, "cabecera", "codigo_cliente", "CLIENTE_ETIQUETADO"),
            "periodo_facturacion_inicio": self._fecha_campo(documento, periodo, periodo_fechas[0], "periodo_inicio"),
            "periodo_facturacion_fin": self._fecha_campo(documento, periodo, periodo_fechas[1], "periodo_fin"),
            "fecha_vencimiento_cabecera": self._fecha_campo(documento, venc_linea, venc, "fecha_vencimiento"),
            "forma_pago": self.campo_documentado(documento, " ".join(p.texto for p in forma), forma, fecha_linea, "cabecera", "forma_pago", "TRAS_FORMA_PAGO") if forma else None,
            "via_pago": self.campo_documentado(documento, " ".join(p.texto for p in via), via, periodo, "cabecera", "via_pago", "TRAS_VIA_PAGO") if via else None,
            "domiciliacion": self.campo_documentado(documento, banco.texto, banco.palabras, banco, "cabecera", "domiciliacion", "CUENTA_ENMASCARADA") if banco else None,
            **self._totales(documento, pagina), "layout_documental": layout,
        }

    def _fiscalidad(self, documento, pagina):
        salida = []
        for linea in pagina.lineas:
            derecha = zonas_relativas(pagina.ancho, linea.palabras)[1]
            if not any(p.texto == "/" for p in derecha):
                continue
            datos = [(p, parsear_importe(p.texto)) for p in derecha]
            datos = [(p, v) for p, v in datos if v is not None]
            if len(datos) != 6:
                continue
            iva, recargo, base, cuota, cuota_re, total = datos
            salida.append({"orden": len(salida) + 1, "origen": "FACTURA",
                "base": self._importe(documento, linea, base, "base", "BASE_FISCAL_IMPRESA"),
                "tipo_iva": self._importe(documento, linea, iva, "tipo_iva", "TIPO_IVA_IMPRESO"),
                "cuota_iva": self._importe(documento, linea, cuota, "cuota_iva", "CUOTA_IVA_IMPRESA"),
                "tipo_recargo_equivalencia": self._importe(documento, linea, recargo, "tipo_recargo", "TIPO_RE_IMPRESO"),
                "cuota_recargo_equivalencia": self._importe(documento, linea, cuota_re, "cuota_recargo", "CUOTA_RE_IMPRESA"),
                "total": self._importe(documento, linea, total, "total", "TOTAL_TRAMO_IMPRESO")})
        return salida

    def _albaranes(self, documento, pagina):
        salida = []
        for linea in pagina.lineas:
            for words in zonas_relativas(pagina.ancho, linea.palabras):
                dates = [w for w in words if DATE_RE.fullmatch(w.texto)]
                ids = [w for w in words if FACTURA_RE.fullmatch(w.texto)]
                if len(dates) != 1 or len(ids) != 1:
                    continue
                after = [w for w in words if w.bbox.x0 > ids[0].bbox.x1]
                monies = [(w, parsear_importe(w.texto)) for w in after]
                monies = [(w, v) for w, v in monies if v is not None]
                tipos = [w for w in after if re.fullmatch(r"\d{3}", w.texto) and parsear_importe(w.texto) is None]
                if len(monies) < 2 or len(tipos) != 1:
                    continue
                row = sorted(words, key=lambda w: w.bbox.x0); literal = " ".join(w.texto for w in row); box = union_bbox([w.bbox for w in row])
                columnas = self._columnas_economicas(pagina, linea, "COFARES_SUMINISTROS_V1", monies)
                bases_columnas = {k: v for k, v in columnas.items() if k.startswith("BASE_")}
                bases = [dato[1] for dato in bases_columnas.values()]
                bases_por_categoria = {k: dato[1] for k, dato in bases_columnas.items()}
                evidencias = {
                    "numero_albaran": self.evidencia(documento, pagina.numero, ids[0].texto, ids[0].bbox, literal, box, "resumen_suministros", "numero_albaran", "TOKEN_BAJO_N_ALBARAN"),
                    "fecha": self.evidencia(documento, pagina.numero, dates[0].texto, dates[0].bbox, literal, box, "resumen_suministros", "fecha", "FECHA_MISMA_FILA"),
                    "tipo_pedido": self.evidencia(documento, pagina.numero, tipos[0].texto, tipos[0].bbox, literal, box, "resumen_suministros", "tipo_pedido", "TOKEN_BAJO_T_PED"),
                    "base": self.evidencia(documento, pagina.numero, "+".join(w.texto for w, _ in monies[1:]), union_bbox([w.bbox for w, _ in monies[1:]]), literal, box, "resumen_suministros", "bases", "COLUMNAS_BASES_VISIBLES", "DERIVACION_LOCAL"),
                    "total": self.evidencia(documento, pagina.numero, monies[0][0].texto, monies[0][0].bbox, literal, box, "resumen_suministros", "total", "PRIMER_IMPORTE_TRAS_ALBARAN")}
                salida.append(AlbaranLocal(
                    ids[0].texto, dates[0].texto, tipos[0].texto, bases, monies[0][1], None,
                    "DETALLE_ALBARAN", pagina.numero, 0, evidencias,
                    bases_por_categoria=bases_por_categoria,
                    atributos_documentales={
                        "mapeo_fiscal": "CABECERAS_Y_GEOMETRIA_VISIBLES",
                        "columnas": list(bases_por_categoria),
                    },
                ))
        salida.sort(key=lambda x: (x.pagina, x.evidencias["numero_albaran"].bbox[1], x.evidencias["numero_albaran"].bbox[0]))
        for i, fila in enumerate(salida, 1): fila.orden = i
        return salida

    def _movimientos(self, documento, pagina, layout):
        if layout == "COFARES_SUMINISTROS_V1":
            specs = (("TOTAL DEVOLUCIONES", "DEVOLUCION_MERCANCIA"), ("SERV INTEGRAL DISTRIBUCI", "SERVICIO"), ("DOMICILIACI", "SERVICIO"))
            filas = [(self._linea(pagina, frag), cat) for frag, cat in specs]
        else:
            filas = []
            for linea in pagina.lineas:
                izquierda = zonas_relativas(pagina.ancho, linea.palabras)[0]
                texto = normalizar_texto(" ".join(p.texto for p in izquierda))
                if any(x in texto for x in ("DTO. ADICIONAL LABORATORIO", "CARGO PARAFARMACIA", "SERVICIO COFARES DIRECTO", "SERVICIO LOG")):
                    cat = "DESCUENTO" if "DTO." in texto else ("SERVICIO" if "SERVICIO" in texto else "CONDICION_COMERCIAL")
                    filas.append((linea, cat))
        salida = []
        for linea, categoria in filas:
            words = zonas_relativas(pagina.ancho, linea.palabras)[0]
            datos = [(p, parsear_importe(p.texto)) for p in words]
            cantidades = [(p, v) for p, v in datos if v is not None]
            concepto = [p for p, v in datos if v is None and p.texto != "|"]
            literal = " ".join(p.texto for p in concepto)
            columnas = self._columnas_economicas(pagina, linea, layout, cantidades)
            campos_columnas = {
                nombre: self._importe(documento, linea, dato, nombre.casefold(), "COLUMNA_ECONOMICA_DESDE_CABECERA_Y_GEOMETRIA")
                for nombre, dato in columnas.items()
            }
            categorias_fiscales = {"BASE_SR", "BASE_R", "BASE_N", "BASE_N_SIN_RE"}
            desglose_bases = {k: v for k, v in campos_columnas.items() if k in categorias_fiscales}
            base = campos_columnas.get("T_BASES") or self._campo_derivado_suma_bases(desglose_bases)
            decision = documentar_sentido_decision_funcional_pio_cofares(literal, categoria)
            if decision is None:
                raise ValueError(f"Movimiento COFARES sin decision funcional Pio: {literal}")
            salida.append({"orden": len(salida) + 1,
                "descripcion_literal": self.campo_documentado(documento, literal, concepto, linea, "movimientos", "descripcion", "CONCEPTO_VISIBLE"),
                "concepto_normalizado": normalizar_texto(literal).replace(".", "_").replace(" ", "_"),
                "categoria": categoria, "origen_categoria": "ESPECIFICA_COFARES_LITERAL_CONCEPTUAL",
                "importe": campos_columnas.get("TOTAL"),
                "base": base,
                "base_calculo": campos_columnas.get("BASE_CALCULO"),
                "desglose_bases": desglose_bases,
                "mapeo_columnas": {
                    "SR": "BASE_SR", "R": "BASE_R", "N": "BASE_N",
                    "N_sin_RE": "BASE_N_SIN_RE", "T_Bases": "T_BASES",
                    "regla": "CABECERAS_Y_GEOMETRIA_VISIBLES_COFARES",
                },
                "iva": None, "recargo": None, "fecha": None,
                "sentido": decision["valor"],
                "sentido_fuente": "DECISION_FUNCIONAL_PIO",
                "sentido_documentacion": decision,
                "valores_documentales": [self._importe(documento, linea, x, f"valor_{i}", "VALOR_VISIBLE_SIN_SEMANTICA_INDIVIDUAL") for i, x in enumerate(cantidades, 1)],
                "provenance": {"pagina": pagina.numero, "adaptador": self.id, "version_adaptador": self.version,
                               "autoridad_sentido": "PIO", "fuente_sentido": "DECISION_FUNCIONAL_PIO",
                               "evidencia_documental_directa_sentido": False,
                               "regla_sentido": decision["regla"],
                               "inferencia_por_descripcion": False, "inferencia_por_signo": False},
                "incidencias": [] if campos_columnas.get("TOTAL") else [{"codigo": "IMPORTE_MOVIMIENTO_NO_DOCUMENTADO"}]})
        return salida

    def _vencimientos(self, documento, pagina, cabecera):
        linea = self._linea(pagina, "VENCIMIENTO"); fecha = palabras_fecha(linea)[0]
        return [{"orden": 1, "fecha": self._fecha_campo(documento, linea, fecha, "fecha"), "importe": None,
                 "forma_pago": cabecera["forma_pago"], "via_pago": cabecera["via_pago"], "domiciliacion": cabecera["domiciliacion"],
                 "provenance": {"pagina": pagina.numero, "regla": "OCURRENCIA_DOCUMENTAL"},
                 "incidencias": [{"codigo": "IMPORTE_VENCIMIENTO_NO_DOCUMENTADO"}]}]

    def _otros(self, documento, pagina, cabecera, layout):
        tipos = (("TOTAL ALBARANES", "TOTAL_ALBARANES"), ("SUBTOTAL", "SUBTOTAL_SUMINISTROS")) if layout == "COFARES_SUMINISTROS_V1" else (("SUBTOTAL", "SUBTOTAL_LIQUIDACION"), ("TOTAL", "TOTAL_LIQUIDACIONES"))
        salida = []
        for frag, tipo in tipos:
            linea = self._linea(pagina, frag); words = zonas_relativas(pagina.ancho, linea.palabras)[0]
            cantidades = [(p, parsear_importe(p.texto)) for p in words]; cantidades = [(p, v) for p, v in cantidades if v is not None]
            salida.append({"tipo": tipo, "literal": self.campo_documentado(documento, " ".join(p.texto for p in words), words, linea, "otros", "literal", "FILA_ECONOMICA_VISIBLE"),
                           "valores_documentales": [self._importe(documento, linea, x, f"valor_{i}", "VALOR_VISIBLE") for i, x in enumerate(cantidades, 1)]})
        salida.append({"tipo": "PERIODO_FACTURACION", "inicio": cabecera["periodo_facturacion_inicio"], "fin": cabecera["periodo_facturacion_fin"]})
        if layout == "COFARES_LIQUIDACIONES_COMERCIALES_V1":
            for linea in pagina.lineas:
                derecha = zonas_relativas(pagina.ancho, linea.palabras)[1]
                cantidades = [(p, parsear_importe(p.texto)) for p in derecha]
                cantidades = [(p, v) for p, v in cantidades if v is not None]
                if not cantidades or not 195 <= linea.bbox.y0 <= 230:
                    continue
                conceptos = [p for p in derecha if parsear_importe(p.texto) is None and p.texto != "|"]
                literal = " ".join(p.texto for p in conceptos) or "TOTAL COMPRAS MENSUALES"
                columnas = self._columnas_compras_mensuales(pagina, linea, cantidades)
                salida.append({"tipo": "DESGLOSE_INFORMATIVO_COMPRAS_MENSUALES",
                    "descripcion_literal": self.campo_documentado(documento, literal, conceptos, linea, "otros", "compras", "FILA_LADO_DERECHO") if conceptos else None,
                    "columnas": {nombre: self._importe(documento, linea, dato, nombre.casefold(), "COLUMNA_COMPRAS_DESDE_CABECERA_Y_GEOMETRIA") for nombre, dato in columnas.items()},
                    "mapeo_columnas": {"T_Bases": "T_BASES", "SR": "BASE_SR", "R": "BASE_R", "N": "BASE_N", "regla": "CABECERAS_Y_GEOMETRIA_VISIBLES_COFARES"},
                    "valores_documentales": [self._importe(documento, linea, x, f"valor_{i}", "VALOR_INFORMATIVO") for i, x in enumerate(cantidades, 1)]})
        return salida

    def _controles(self, cabecera, impuestos, vencimientos):
        specs = [
            EspecificacionConciliacion("TOTAL_DESDE_FISCALIDAD", "TOTAL_FACTURA", self._comp("TOTAL", cabecera["importe_total"]), [self._comp_tramo(f"TRAMO_{i}", t) for i, t in enumerate(impuestos, 1)]),
            EspecificacionConciliacion("BASE_DESDE_TRAMOS", "TOTAL_BASES", self._comp("BASE", cabecera["base_imponible_total"]), [self._comp(f"BASE_{i}", t["base"]) for i, t in enumerate(impuestos, 1)]),
            EspecificacionConciliacion("TOTAL_PAGAR_VS_FACTURA", "TOTAL_FACTURA", self._comp("TOTAL", cabecera["importe_total"]), [self._comp("PAGAR", cabecera["importe_total_pagar"])]),
            EspecificacionConciliacion("VENCIMIENTOS_VS_TOTAL", "TOTAL_FACTURA", self._comp("TOTAL", cabecera["importe_total"]), [ComponenteConciliacion("VENCIMIENTO", None, None, "vencimientos", vencimientos[0]["provenance"]["pagina"])])]
        return evaluar_conciliaciones(specs)

    def _totales(self, documento, pagina):
        bases = self._linea(pagina, "TOTAL BASES"); vals = palabras_importe(bases)
        factura = self._linea(pagina, "TOTAL FACTURA"); pagar = self._linea(pagina, "TOTAL PAGAR")
        return {"base_imponible_total": self._importe(documento, bases, vals[-4], "base_imponible_total", "TOTAL_BASES"),
                "iva_total": self._importe(documento, bases, vals[-3], "iva_total", "TOTAL_IVA"),
                "recargo_equivalencia_total": self._importe(documento, bases, vals[-2], "recargo_total", "TOTAL_RE"), "otros_total": None,
                "importe_total": self._importe(documento, factura, palabras_importe(factura)[-1], "importe_total", "TOTAL_FACTURA"),
                "importe_total_pagar": self._importe(documento, pagar, palabras_importe(pagar)[-1], "total_pagar", "TOTAL_PAGAR")}

    def _columnas_economicas(self, pagina, linea, layout, cantidades):
        """Asigna valores por cercania a cabeceras visibles del mismo lado."""
        if layout == "COFARES_SUMINISTROS_V1":
            cabecera = self._linea(pagina, "F.PEDIDO")
            lado = zonas_relativas(pagina.ancho, cabecera.palabras)[0]
            total = next(p for p in lado if normalizar_texto(p.texto) == "TOTAL")
            sr = next(p for p in lado if normalizar_texto(p.texto) == "SR")
            reducido = next(p for p in lado if normalizar_texto(p.texto) == "R")
            normal = next(p for p in lado if normalizar_texto(p.texto) == "N")
            anclas = {
                "TOTAL": self._centro(total), "BASE_SR": self._centro(sr),
                "BASE_R": self._centro(reducido), "BASE_N": self._centro(normal),
            }
        else:
            cabecera = next(l for l in pagina.lineas if "SR" in normalizar_texto(l.texto) and "RE" in normalizar_texto(l.texto) and l.bbox.y0 < 200)
            lado = zonas_relativas(pagina.ancho, cabecera.palabras)[0]
            sr = next(p for p in lado if normalizar_texto(p.texto) == "SR")
            reducido = next(p for p in lado if normalizar_texto(p.texto) == "R")
            normales = [p for p in lado if normalizar_texto(p.texto) == "N"]
            base, calculo = lado[0], lado[1]
            n_sin_re = lado[lado.index(normales[1]):]
            anclas = {
                "BASE_CALCULO": (base.bbox.x0 + calculo.bbox.x1) / 2,
                "BASE_SR": self._centro(sr), "BASE_R": self._centro(reducido),
                "BASE_N": self._centro(normales[0]),
                "BASE_N_SIN_RE": (n_sin_re[0].bbox.x0 + n_sin_re[-1].bbox.x1) / 2,
            }
        salida = {}
        for dato in cantidades:
            centro = self._centro(dato[0])
            nombre = min(anclas, key=lambda k: abs(centro - anclas[k]))
            if nombre in salida:
                raise ValueError(f"Dos valores COFARES asignados a {nombre}: {linea.texto}")
            salida[nombre] = dato
        return salida

    def _columnas_compras_mensuales(self, pagina, linea, cantidades):
        cabecera = next(l for l in pagina.lineas if "T. BASES" in normalizar_texto(l.texto))
        lado = zonas_relativas(pagina.ancho, cabecera.palabras)[1]
        t_indice = next(i for i, p in enumerate(lado) if normalizar_texto(p.texto) == "T.")
        sr = next(p for p in lado if normalizar_texto(p.texto) == "SR")
        reducido = next(p for p in lado if normalizar_texto(p.texto) == "R")
        normal = next(p for p in lado if normalizar_texto(p.texto) == "N")
        anclas = {
            "T_BASES": (lado[t_indice].bbox.x0 + lado[t_indice + 1].bbox.x1) / 2,
            "BASE_SR": self._centro(sr), "BASE_R": self._centro(reducido),
            "BASE_N": self._centro(normal),
        }
        salida = {}
        for dato in cantidades:
            nombre = min(anclas, key=lambda k: abs(self._centro(dato[0]) - anclas[k]))
            if nombre in salida:
                raise ValueError(f"Dos valores COFARES asignados a {nombre}: {linea.texto}")
            salida[nombre] = dato
        return salida

    @staticmethod
    def _campo_derivado_suma_bases(desglose):
        if not desglose:
            return None
        componentes = list(desglose.values())
        return {
            "valor": round(sum(c["valor"] for c in componentes), 2),
            "literal": "+".join(c["literal"] for c in componentes),
            "evidencias": [ev for c in componentes for ev in c["evidencias"]],
            "derivacion": {
                "regla": "SUMA_COLUMNAS_BASES_FISCALES_IMPRESAS",
                "uso": "DATO_DERIVADO_DE_CABECERAS_Y_GEOMETRIA",
                "correccion_para_CUADRAR": False,
            },
        }

    @staticmethod
    def _centro(palabra):
        return (palabra.bbox.x0 + palabra.bbox.x1) / 2

    @staticmethod
    def _layout(documento):
        texto = normalizar_texto("\n".join(p.texto for p in documento.paginas))
        if "RESUMEN DE SUMINISTROS" in texto and "T.PED" in texto and re.search(r"N.?\s*ALBAR", texto): return "COFARES_SUMINISTROS_V1"
        if "DETALLE MENSUAL DE LIQUIDACIONES COMERCIALES" in texto and "DESGLOSE INFORMATIVO COMPRAS MENSUALES" in texto: return "COFARES_LIQUIDACIONES_COMERCIALES_V1"
        return None

    @staticmethod
    def _linea(pagina, fragmento):
        objetivo = normalizar_texto(fragmento)
        return next(l for l in pagina.lineas if objetivo in normalizar_texto(l.texto))

    @staticmethod
    def _despues(linea, etiqueta):
        objetivo = normalizar_texto(etiqueta); indice = max((i for i, p in enumerate(linea.palabras) if objetivo in normalizar_texto(p.texto)), default=-1)
        return linea.palabras[indice + 1:] if indice >= 0 else []

    def _fecha_campo(self, documento, linea, palabra, columna):
        return self.campo_documentado(documento, fecha_iso(palabra.texto), [palabra], linea, "cabecera", columna, "FECHA_ETIQUETADA", literal=palabra.texto)

    def _importe(self, documento, linea, dato, columna, regla):
        palabra, valor = dato
        return self.campo_documentado(documento, valor, [palabra], linea, "fiscalidad" if "TRAMO" in regla or "IVA" in regla or "BASE_FISCAL" in regla else "economico", columna, regla, literal=palabra.texto)

    @staticmethod
    def _comp(concepto, campo):
        if campo is None: return ComponenteConciliacion(concepto, None, None, "documento", None)
        ev = campo["evidencias"]
        return ComponenteConciliacion(concepto, campo["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", "documento", ev[0].pagina, ev)

    def _comp_tramo(self, concepto, tramo):
        campos = [tramo["base"], tramo["cuota_iva"], tramo["cuota_recargo_equivalencia"]]
        ev = [e for c in campos for e in c["evidencias"]]
        return ComponenteConciliacion(concepto, round(sum(c["valor"] for c in campos), 2), "SIGNOS_DOCUMENTALES_CONSERVADOS", "fiscalidad", ev[0].pagina, ev)

    @staticmethod
    def _desconocido(documento, segmento):
        return {"segmento": {"sha_documento": documento.sha_documento, "paginas": segmento.paginas}, "layout": None, "cabecera": {}, "albaranes": [], "movimientos": [], "impuestos": [], "vencimientos": [], "otros": [], "controles_conciliacion": [], "incidencias": [{"codigo": "LAYOUT_DESCONOCIDO", "estado": "NO_APLICABLE", "bloqueante": True}]}
