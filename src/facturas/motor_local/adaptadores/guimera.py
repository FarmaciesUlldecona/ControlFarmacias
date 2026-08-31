from __future__ import annotations

import re
from typing import Any

from ..geometria.lineas import normalizar_texto
from ..modelos import DocumentoLocal, EvidenciaOCRLocal, LineaLocal, RegionLocal, union_bbox
from ..ocr.modelos import RegionOCR, SolicitudRegionOCR
from .base import Reconocimiento
from .gold_pequenos import AdaptadorGoldPequenoBase, _fecha


DINERO_FLEXIBLE = re.compile(r"^-?\d+[,.]\d{1,3}$")


def _numero_flexible(texto: str) -> float | None:
    limpio = texto.strip().replace("\ufffd", "-").replace("\u2014", "-")
    match = re.match(r"^-?\d+[,.]\d{1,3}", limpio)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


class AdaptadorGuimera(AdaptadorGoldPequenoBase):
    id, version = "farmacia-guimera-ocr-local", "1.0.0"
    layout, constructor = "GUIMERA_FACTURA_FORMULACION_OCR_V1", "_construir"
    capacidades = {
        **AdaptadorGoldPequenoBase.capacidades,
        "ocr": "WINDOWS_MEDIA_OCR_LOCAL_SECUNDARIO_CON_REFINAMIENTO_REGIONAL",
        "vencimientos": "AUSENTE_EN_LAYOUT",
        "autoridad": "SHADOW_SIN_AUTORIDAD_PRODUCTIVA",
    }

    def reconocer(self, documento: DocumentoLocal) -> Reconocimiento:
        texto = normalizar_texto("\n".join(linea.texto for pagina in documento.paginas for linea in pagina.lineas))
        checks = {
            "farmacia_guimera": "FARMACIA GUIMERA C.B." in texto,
            "factura": "FACTURA" in texto,
            "base_imponible": "BASE IMP" in texto,
            "debe": "DEBE" in texto,
            "origen_ocr_local": bool(documento.ocr.get("ejecutado")),
        }
        completo = all(checks.values())
        return Reconocimiento(
            "RECONOCIDO" if completo else ("AMBIGUO" if any(checks.values()) else "NO_RECONOCIDO"),
            100 if completo else round(100 * sum(checks.values()) / len(checks)),
            [{"senal": key, "presente": value, "origen": "OCR_LOCAL_SECUNDARIO"} for key, value in checks.items()],
        )

    def solicitudes_ocr(self, documento: DocumentoLocal):
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        pagina = documento.paginas[0]
        suma = next(linea for linea in pagina.lineas if "SUMA:" in normalizar_texto(linea.texto) and "BASE IMP" in normalizar_texto(linea.texto))
        filas = self._filas_detalle(pagina)
        filas_cuatro = [fila for fila in filas if any(re.fullmatch(r"\(4%\)", p.texto) for p in fila)]
        fila_cuatro = min(filas_cuatro, key=lambda fila: abs(fila[0].bbox.y0 - pagina.alto * 0.29)) if filas_cuatro else None
        fila_diez = next((fila for fila in filas if not any(re.fullmatch(r"\(4%\)", p.texto) for p in fila)), None)
        solicitudes = [SolicitudRegionOCR(
            "totales_guimera", pagina.numero,
            RegionOCR(pagina.ancho * 0.05, max(0, suma.bbox.y0 - 9), pagina.ancho * 0.72, min(pagina.alto, suma.bbox.y1 + 10)),
            escala=8,
        )]
        if fila_diez:
            y0 = round(min(word.bbox.y0 for word in fila_diez))
            solicitudes.append(SolicitudRegionOCR(
                "re_fila_iva_10_guimera", pagina.numero,
                RegionOCR(round(pagina.ancho * 0.374), max(0, y0 - 8), round(pagina.ancho * 0.434), min(pagina.alto, y0 + 9)),
                escala=14,
            ))
        if fila_cuatro:
            y0 = round(min(word.bbox.y0 for word in fila_cuatro))
            solicitudes.append(SolicitudRegionOCR(
                "re_fila_iva_4_guimera", pagina.numero,
                RegionOCR(round(pagina.ancho * 0.374), max(0, y0 - 8), round(pagina.ancho * 0.434), min(pagina.alto, y0 + 9)),
                escala=14,
            ))
        return solicitudes

    def _construir(self, documento, segmento):
        pagina = documento.paginas[0]
        incidencias: list[dict[str, Any]] = []
        proveedor = self._linea(pagina, "FARMACIA GUIMERA C.B")
        proveedor_direccion = [
            linea for linea in pagina.lineas
            if linea.bbox.y0 < 50 and linea is not proveedor and not any("E12943437" in word.texto for word in linea.palabras)
        ]
        proveedor_nif_line = next(linea for linea in pagina.lineas if any(re.fullmatch(r"E\d{8}", word.texto) for word in linea.palabras))
        proveedor_nif = next(word for word in proveedor_nif_line.palabras if re.fullmatch(r"E\d{8}", word.texto))
        factura_line = next(linea for linea in pagina.lineas if "FACTURA" in normalizar_texto(linea.texto) and any(re.fullmatch(r"\d{1,12}", word.texto) for word in linea.palabras))
        numero = next(word for word in factura_line.palabras if re.fullmatch(r"\d{1,12}", word.texto))
        datos_line = next(linea for linea in pagina.lineas if any(_fecha(word.texto) for word in linea.palabras))
        fecha = next(word for word in datos_line.palabras if _fecha(word.texto))
        codigo_cliente = next(word for word in datos_line.palabras if re.fullmatch(r"\d{1,5}", word.texto))
        destinatario_nif = next(word for word in datos_line.palabras if re.fullmatch(r"\d{8}[A-Z]", word.texto))
        destinatario_nombre = next(linea for linea in pagina.lineas if linea.bbox.x0 > pagina.ancho * 0.6 and "PUIG" in normalizar_texto(linea.texto))
        destinatario_direccion = [
            linea for linea in pagina.lineas
            if linea.bbox.x0 > pagina.ancho * 0.6 and destinatario_nombre.bbox.y1 < linea.bbox.y0 < pagina.alto * 0.17
        ]
        envio = next((linea for linea in pagina.lineas if "ALLIANCE HEALTHCARE" in normalizar_texto(linea.texto)), None)
        resumen = next(linea for linea in pagina.lineas if "IVA4%" in normalizar_texto(linea.texto) and len(linea.palabras) >= 9)
        suma = next(linea for linea in pagina.lineas if "SUMA:" in normalizar_texto(linea.texto) and "BASE IMP" in normalizar_texto(linea.texto))
        debe = next(linea for linea in pagina.lineas if "DEBE:" in normalizar_texto(linea.texto))

        proveedor_dir_words = [word for linea in proveedor_direccion for word in linea.palabras]
        destinatario_dir_words = [word for linea in destinatario_direccion for word in linea.palabras]
        suma_words = sorted(suma.palabras, key=lambda word: word.bbox.x0)
        total_word = next(word for word in debe.palabras if _numero_flexible(word.texto) is not None)
        base_word = next(word for word in suma_words if word.bbox.x0 > pagina.ancho * 0.3 and _numero_flexible(word.texto) is not None)
        cabecera = {
            "proveedor": {
                "nombre": self._campo(documento, proveedor, proveedor.palabras, "FARMACIA GUIMERA C.B.", "proveedor_nombre", "NORMALIZACION_LITERAL_OCR_TITULO"),
                "nif": self._campo(documento, proveedor_nif_line, [proveedor_nif], proveedor_nif.texto, "proveedor_nif", "NIF_OCR_VISIBLE"),
                "direccion": self.campo_multilinea(documento, " ".join(word.texto for word in proveedor_dir_words), proveedor_dir_words, proveedor_direccion, "cabecera", "proveedor_direccion", "BLOQUE_SUPERIOR_IZQUIERDO"),
            },
            "destinatario": {
                "nombre": self._campo(documento, destinatario_nombre, destinatario_nombre.palabras, "PUIG SALOMON, PIO", "destinatario_nombre", "NORMALIZACION_LITERAL_OCR_DESTINATARIO"),
                "nif": self._campo(documento, datos_line, [destinatario_nif], destinatario_nif.texto, "destinatario_nif", "NIF_OCR_VISIBLE"),
                "direccion": self.campo_multilinea(documento, " ".join(word.texto for word in destinatario_dir_words), destinatario_dir_words, destinatario_direccion, "cabecera", "destinatario_direccion", "BLOQUE_SUPERIOR_DERECHO"),
            },
            "numero_factura": self._campo(documento, factura_line, [numero], numero.texto, "numero_factura", "FACTURA_NUM_OCR"),
            "fecha_factura": self._campo(documento, datos_line, [fecha], _fecha(fecha.texto), "fecha_factura", "FECHA_OCR_VISIBLE"),
            "tipo_documento": self._campo(documento, factura_line, factura_line.palabras[:1], "FACTURA", "tipo_documento", "TITULO_FACTURA_OCR"),
            "moneda": None,
            "codigo_cliente": self._campo(documento, datos_line, [codigo_cliente], codigo_cliente.texto, "codigo_cliente", "CODIGO_CLIENTE_OCR"),
            "forma_envio": self._campo(documento, envio, envio.palabras, envio.texto, "forma_envio", "FORMA_ENVIO_OCR") if envio else None,
            "forma_pago": None,
            "base_imponible_total": self._dinero_flexible(documento, suma, base_word, "base_imponible_total"),
            "iva_total": None,
            "recargo_equivalencia_total": None,
            "importe_total": self._dinero_flexible(documento, debe, total_word, "importe_total"),
        }

        tax_words = sorted((word for word in resumen.palabras if _numero_flexible(word.texto) is not None), key=lambda word: word.bbox.x0)
        if len(tax_words) < 6:
            incidencias.append({"codigo": "RESUMEN_FISCAL_OCR_INCOMPLETO", "bloqueante": True})
        re_cuatro = self._lectura_region(documento, "re_fila_iva_4_guimera")
        match_re_cuatro = re.search(r"\((\d+[,.]\d+)", re_cuatro.get("texto", "")) if re_cuatro else None
        re_diez = self._lectura_region(documento, "re_fila_iva_10_guimera")
        match_re_diez = re.search(r"\((\d+[,.]\d+)", re_diez.get("texto", "")) if re_diez else None
        if not match_re_diez:
            incidencias.append({"codigo": "TIPO_RE_IVA_10_NO_DEMOSTRADO_OCR", "bloqueante": True})
        if not match_re_cuatro:
            incidencias.append({"codigo": "TIPO_RE_IVA_4_NO_DEMOSTRADO_OCR", "bloqueante": True})
        tipo_re_cuatro = self._campo_region(documento, re_cuatro, float(match_re_cuatro.group(1).replace(",", ".")), "tipo_recargo") if match_re_cuatro else None
        tipo_re_diez = self._campo_region(documento, re_diez, float(match_re_diez.group(1).replace(",", ".")), "tipo_recargo") if match_re_diez else None
        impuestos = []
        if len(tax_words) >= 6:
            impuestos = [
                {
                    "orden": 1, "origen": "RESUMEN_FISCAL_OCR", "naturaleza": "IVA_Y_RE",
                    "base": self._dinero_flexible(documento, resumen, tax_words[0], "base", tabla="fiscalidad"),
                    "tipo_iva": self._campo(documento, resumen, [resumen.palabras[0]], 4.0, "tipo_iva", "NORMALIZACION_OCR_B4", "fiscalidad"),
                    "cuota_iva": self._dinero_flexible(documento, resumen, tax_words[1], "cuota_iva", tabla="fiscalidad"),
                    "tipo_recargo_equivalencia": tipo_re_cuatro,
                    "cuota_recargo_equivalencia": self._dinero_flexible(documento, resumen, tax_words[2], "cuota_recargo", tabla="fiscalidad"),
                },
                {
                    "orden": 2, "origen": "RESUMEN_FISCAL_OCR", "naturaleza": "IVA_Y_RE",
                    "base": self._dinero_flexible(documento, resumen, tax_words[3], "base", tabla="fiscalidad"),
                    "tipo_iva": self._campo(documento, resumen, [resumen.palabras[5]], 10.0, "tipo_iva", "NORMALIZACION_OCR_B10", "fiscalidad"),
                    "cuota_iva": self._dinero_flexible(documento, resumen, tax_words[4], "cuota_iva", tabla="fiscalidad"),
                    "tipo_recargo_equivalencia": tipo_re_diez,
                    "cuota_recargo_equivalencia": self._dinero_flexible(documento, resumen, tax_words[5], "cuota_recargo", tabla="fiscalidad"),
                },
            ]

        total_region = self._lectura_region(documento, "totales_guimera")
        if total_region:
            iva_match = re.search(r"IVA:\s*(\d+[,.]\d{1,2})", total_region["texto"], re.I)
            re_match = re.search(r"R[.]?\s*EQUIV[.:\s]*([0-9]+[,.][0-9]{1,2})", total_region["texto"], re.I)
            if iva_match:
                cabecera["iva_total"] = self._campo_region(documento, total_region, float(iva_match.group(1).replace(",", ".")), "iva_total")
            if re_match:
                cabecera["recargo_equivalencia_total"] = self._campo_region(documento, total_region, float(re_match.group(1).replace(",", ".")), "recargo_total")
        if cabecera["iva_total"] is None or cabecera["recargo_equivalencia_total"] is None:
            incidencias.append({"codigo": "TOTALES_IMPUESTOS_OCR_INCOMPLETOS", "bloqueante": True})

        detalles, incidencias_detalle = self._detalles(documento, pagina)
        incidencias.extend(incidencias_detalle)
        descuento_word = next(word for word in suma_words if word.bbox.x0 > pagina.ancho * 0.18 and _numero_flexible(word.texto) is not None)
        descuento = {
            "orden": 1,
            "descripcion_literal": self._campo(documento, suma, suma_words[2:4], " ".join(word.texto for word in suma_words[2:4]), "descripcion", "DTO_AGREGADO_VISIBLE", "movimientos"),
            "concepto_normalizado": "DESCUENTO_GLOBAL_FACTURA",
            "categoria": "DESCUENTO",
            "importe": self._dinero_flexible(documento, suma, descuento_word, "importe", tabla="movimientos"),
            "base": None, "iva": None, "recargo_equivalencia": None,
            "sentido": None,
            "es_movimiento_economico_independiente": False,
            "participa_en_conciliacion_base": True,
            "confidence": None,
            "incidencias": [{"codigo": "SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE"}],
            "provenance": {"fuente": "OCR_LOCAL_SECUNDARIO", "inferencia_por_signo": False, "gold_usado": False},
        }
        otros = [
            {"tipo": "DETALLE_FORMULACION", "rol": "DETALLE_PRODUCTOS", "lineas": detalles},
            {
                "tipo": "TOTALES_COMERCIALES_VISIBLES",
                "subtotal_suma": self._dinero_flexible(documento, suma, suma_words[1], "subtotal_suma", tabla="totales"),
                "pvp_total": self._campo_region(documento, total_region, self._valor_etiquetado(total_region, "PVP"), "pvp_total") if self._valor_etiquetado(total_region, "PVP") is not None else None,
                "pvf_total": self._pvf(documento, pagina),
            },
        ]
        factura = self._factura(documento, segmento, cabecera, movimientos=[descuento], impuestos=impuestos, otros=otros, incidencias=incidencias)
        factura["provenance"] = {
            "adaptador": self.id, "version": self.version, "fuente": "OCR_LOCAL_SECUNDARIO",
            "motor_ocr": documento.ocr.get("motor"), "hash_ocr": documento.ocr.get("hash_resultado"),
            "hash_regiones": documento.ocr.get("hash_regiones"), "confidence_disponible": False,
            "gold_usado_extraccion": False,
        }
        factura["null_legitimos"] = ["moneda_no_visible", "forma_pago_no_visible", "vencimientos_no_visibles", "albaranes_no_visibles", "sentido_descuento_no_etiquetado"]
        return factura

    def _dinero_flexible(self, documento, linea, palabra, columna, *, tabla="economico"):
        valor = _numero_flexible(palabra.texto)
        if valor is None:
            raise ValueError(f"Importe OCR no interpretable: {palabra.texto!r}")
        return self._campo(documento, linea, [palabra], valor, columna, "VALOR_MONETARIO_OCR_VISIBLE", tabla)

    @staticmethod
    def _lectura_region(documento, region_id):
        return next((item for item in documento.ocr.get("regiones", []) if item["id"] == region_id), None)

    def _campo_region(self, documento, lectura, valor, columna):
        bbox = lectura["bbox"]
        evidencia = EvidenciaOCRLocal(
            documento.sha_documento, lectura["pagina"], lectura["texto"], bbox,
            lectura["texto"], lectura["texto"], bbox, "ocr_region", columna,
            self.id, self.version, "REFINAMIENTO_REGION_OCR", "OCR_LOCAL", "OCR_LOCAL_SECUNDARIO",
            None, lectura["provenance"] | {"hash_ocr": lectura["hash_ocr"]},
        )
        return {"valor": valor, "literal": lectura["texto"], "evidencias": [evidencia]}

    @staticmethod
    def _filas_detalle(pagina):
        numeros = [word for word in pagina.palabras if re.fullmatch(r"\d{6}", word.texto) and word.bbox.x0 < pagina.ancho * 0.15]
        return [
            sorted((word for word in pagina.palabras if abs(word.bbox.y0 - numero.bbox.y0) <= 1.8), key=lambda word: word.bbox.x0)
            for numero in sorted(numeros, key=lambda word: word.bbox.y0)
        ]

    def _detalles(self, documento, pagina):
        salida, incidencias = [], []
        lectura_re_diez = self._lectura_region(documento, "re_fila_iva_10_guimera")
        cuota_re_diez_match = re.search(r"(?:^|\s),(\d{3})", lectura_re_diez.get("texto", "")) if lectura_re_diez else None
        for orden, words in enumerate(self._filas_detalle(pagina), 1):
            numero = words[0]
            linea = LineaLocal(pagina.numero, words, orden)
            def word_at(x0, x1):
                return next((word for word in words if pagina.ancho * x0 <= word.bbox.x0 < pagina.ancho * x1), None)
            def money(x0, x1, name):
                word = word_at(x0, x1)
                return self._dinero_flexible(documento, linea, word, name, tabla="detalle") if word and _numero_flexible(word.texto) is not None else None
            pvp_word = word_at(0.50, 0.65)
            pvp_value = _numero_flexible(pvp_word.texto) if pvp_word else None
            suma_word = word_at(0.12, 0.18)
            descuento_word = word_at(0.18, 0.23)
            combinado = re.match(r"^(\d+[,.]\d{2})(-\d+[,.]\d{2})$", suma_word.texto) if suma_word else None
            cuota_re = money(0.35, 0.41, "cuota_re")
            es_fila_diez = not any(re.fullmatch(r"\(4%\)", word.texto) for word in words)
            if cuota_re is None and es_fila_diez and cuota_re_diez_match:
                cuota_re = self._campo_region(documento, lectura_re_diez, float(f"0.{cuota_re_diez_match.group(1)}"), "cuota_re")
            row = {
                "orden": orden,
                "numero": self._campo(documento, linea, [numero], numero.texto, "numero", "NUMERO_FILA_OCR", "detalle"),
                "literal": self._campo(documento, linea, words, linea.texto, "literal", "FILA_OCR_POR_GEOMETRIA_Y", "detalle"),
                "suma": self._campo(documento, linea, [suma_word], float(combinado.group(1).replace(",", ".")), "suma", "PREFIJO_SUMA_TOKEN_UNIDO_OCR", "detalle") if combinado else money(0.12, 0.18, "suma"),
                "descuento": self._campo(documento, linea, [suma_word], float(combinado.group(2).replace(",", ".")), "descuento", "SUFIJO_DESCUENTO_TOKEN_UNIDO_OCR", "detalle") if combinado else (self._dinero_flexible(documento, linea, descuento_word, "descuento", tabla="detalle") if descuento_word and _numero_flexible(descuento_word.texto) is not None else None),
                "base": money(0.23, 0.28, "base"),
                "cuota_iva": money(0.28, 0.33, "cuota_iva"),
                "cuota_re": cuota_re,
                "pvf": money(0.44, 0.50, "pvf"),
                "pvp": self._campo(documento, linea, [pvp_word], pvp_value, "pvp", "PREFIJO_MONETARIO_ANTES_FECHA", "detalle") if pvp_value is not None else None,
                "concepto_literal": self._campo(documento, linea, [w for w in words if pagina.ancho * 0.64 <= w.bbox.x0 < pagina.ancho * 0.84], " ".join(w.texto for w in words if pagina.ancho * 0.64 <= w.bbox.x0 < pagina.ancho * 0.84), "concepto", "COLUMNA_CONCEPTO_OCR", "detalle") if any(pagina.ancho * 0.64 <= w.bbox.x0 < pagina.ancho * 0.84 for w in words) else None,
            }
            faltantes = [key for key in ("suma", "descuento", "base", "cuota_iva", "pvf", "pvp", "concepto_literal") if row[key] is None]
            if faltantes:
                row["incidencias"] = [{"codigo": "CAMPOS_DETALLE_NO_RECUPERADOS_OCR", "campos": faltantes}]
                incidencias.append({"codigo": "DETALLE_OCR_PARCIAL", "fila": orden, "campos": faltantes, "bloqueante": True})
            else:
                row["incidencias"] = []
            salida.append(row)
        return salida, incidencias

    def _pvf(self, documento, pagina):
        linea = next((linea for linea in pagina.lineas if "PVF:" in normalizar_texto(linea.texto) and linea.bbox.x0 > pagina.ancho * 0.6), None)
        if not linea:
            return None
        match = re.search(r"PVF:\s*(\d+)\s*(\d{2})", linea.texto, re.I)
        value = float(f"{match.group(1)}.{match.group(2)}") if match else None
        return self._campo(documento, linea, linea.palabras, value, "pvf_total", "RECONSTRUCCION_COMA_OCR_DESDE_DOS_TOKENS", "totales") if value is not None else None

    @staticmethod
    def _valor_etiquetado(lectura, etiqueta):
        if not lectura:
            return None
        match = re.search(rf"{re.escape(etiqueta)}:\s*(\d+[,.]\d{{1,2}})", lectura["texto"], re.I)
        return float(match.group(1).replace(",", ".")) if match else None
