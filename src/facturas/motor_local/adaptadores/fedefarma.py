from __future__ import annotations

import re
from typing import Any

from ..conciliacion import ComponenteConciliacion, EspecificacionConciliacion, evaluar_conciliaciones
from ..geometria.campos import fecha_iso, palabras_fecha, palabras_importe
from ..geometria.lineas import normalizar_texto, parsear_importe
from ..modelos import AlbaranLocal, DocumentoLocal, LineaLocal, PaginaLocal, PalabraLocal, union_bbox
from .base import AdaptadorBase, Reconocimiento


FACTURA_RE = re.compile(r"^(?:VN\d{2,4}-\d{7}|SI\d{2}-\d{5})$", re.I)
ALBARAN_RE = re.compile(r"^\d{4}-\d{7}$")
ABONAMENTO_RE = re.compile(r"^\d{4}A-\d{6}$", re.I)
NIF_RE = re.compile(r"^(?:[A-Z]-?\d{2}-?\d{6}|\d{8}[A-Z])$", re.I)
CATEGORIAS = ("IVA_0", "IVA_4", "IVA_10", "IVA_21")


class AdaptadorFedefarma(AdaptadorBase):
    id = "fedefarma-local"
    version = "1.2.0"
    capacidades = {
        "segmentacion": "SOPORTADO_MULTIFACTURA_DETERMINISTA",
        "cabecera": "SOPORTADO",
        "albaranes": "SOPORTADO_LAYOUT_MERCANCIA",
        "movimientos": "SOPORTADO_SENTIDO_DOCUMENTAL_O_NULL",
        "impuestos": "SOPORTADO",
        "vencimientos": "SOPORTADO",
        "otros": "SOPORTADO",
        "conciliacion_documental": "SOPORTADO",
    }

    def reconocer(self, documento: DocumentoLocal) -> Reconocimiento:
        texto = normalizar_texto("\n".join(p.texto for p in documento.paginas))
        comprobaciones = {
            "identidad_legal": "FEDERACIO FARMACEUTICA" in texto and "F-08-173395" in texto,
            "resumen_multidocumento": "INFORMACIO" in texto and "FACTURES/CARREC" in texto and "RELACIO DE FACTURES/CARRECS" in texto,
            "layout_mercancia": "DATA ALBARA" in texto and "LIQUID FACTURA" in texto and "DETALL ABONAMENTS" in texto,
            "layout_servicios": "CONDICIONS DE COBRAMENT" in texto and "QUOTA IMPOST" in texto and "ARTICLE DESCRIPCIO" in texto,
            "paginacion_interna": texto.count("PAGINA 1 1") >= 3 or texto.count("PAGINA 1 - 1") >= 3,
            "texto_nativo": all(p.palabras for p in documento.paginas),
        }
        completas = (
            comprobaciones["identidad_legal"]
            and comprobaciones["resumen_multidocumento"]
            and (comprobaciones["layout_mercancia"] or comprobaciones["layout_servicios"])
            and comprobaciones["texto_nativo"]
        )
        indicios = comprobaciones["identidad_legal"] or comprobaciones["resumen_multidocumento"]
        estado = "RECONOCIDO" if completas else ("AMBIGUO" if indicios else "NO_RECONOCIDO")
        return Reconocimiento(
            estado,
            100 if completas else round(100 * sum(comprobaciones.values()) / len(comprobaciones)),
            [{"senal": clave, "presente": valor, "origen": "TEXTO_PDF_LOCAL"} for clave, valor in comprobaciones.items()],
        )

    def extraer_facturas(self, documento: DocumentoLocal, segmentos) -> list[dict[str, Any]]:
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        salida = []
        for segmento in segmentos:
            paginas = [p for p in documento.paginas if segmento.paginas[0] <= p.numero <= segmento.paginas[1]]
            if len(paginas) != 1:
                salida.append(self._factura_layout_desconocido(documento.sha_documento, segmento, "SEGMENTO_MULTIPAGINA_NO_SOPORTADO"))
                continue
            pagina = paginas[0]
            normal = normalizar_texto(pagina.texto)
            if "DATA ALBARA" in normal and "LIQUID FACTURA" in normal:
                salida.append(self._factura_mercancia(documento, pagina, segmento))
            elif "ARTICLE DESCRIPCIO" in normal and "CONDICIONS DE COBRAMENT" in normal:
                salida.append(self._factura_servicio(documento, pagina, segmento))
            else:
                salida.append(self._factura_layout_desconocido(documento.sha_documento, segmento, "LAYOUT_DESCONOCIDO"))
        return salida

    def extraer_albaranes(self, documento: DocumentoLocal, segmentos) -> list[AlbaranLocal]:
        """FEDEFARMA se publica exclusivamente por factura segmentada."""
        return []

    def extraer_otros(self, documento: DocumentoLocal, segmentos) -> list[dict[str, Any]]:
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        return [
            self._resumen_facturacion(documento, pagina)
            for pagina in documento.paginas
            if "RELACIO DE FACTURES/CARRECS ACTUAL" in normalizar_texto(pagina.texto)
        ]

    def _resumen_facturacion(self, documento: DocumentoLocal, pagina: PaginaLocal) -> dict[str, Any]:
        modo_linea = self._linea(pagina, "MODE DE FACTURACIO")
        indices_facturacion = [
            i for i, palabra in enumerate(modo_linea.palabras)
            if normalizar_texto(palabra.texto) == "FACTURACIO"
        ]
        modo_words = modo_linea.palabras[indices_facturacion[0] + 1:]
        fecha_facturacion_linea = self._linea(pagina, "DATA FACTURACIO")
        fecha_facturacion = palabras_fecha(fecha_facturacion_linea)[0]
        encabezado_facturas = self._linea(pagina, "RELACIO DE FACTURES/CARRECS ACTUAL")
        encabezado_pagos = self._linea(pagina, "RELACIO DE PAGAMENTS PREVISTOS PER DATA")
        filas_facturas = [
            self._fila_relacion_factura(documento, linea)
            for linea in pagina.lineas
            if encabezado_facturas.orden < linea.orden < encabezado_pagos.orden
            and any(FACTURA_RE.fullmatch(p.texto) for p in linea.palabras)
        ]
        filas_pagos = [
            self._fila_relacion_pago(documento, linea)
            for linea in pagina.lineas
            if linea.orden > encabezado_pagos.orden
            and any(FACTURA_RE.fullmatch(p.texto) for p in linea.palabras)
        ]
        total_facturas_linea = next(
            linea for linea in pagina.lineas
            if encabezado_facturas.orden < linea.orden < encabezado_pagos.orden
            and len(linea.palabras) == 1 and len(palabras_importe(linea)) == 1
        )
        total_pagos_linea = next(
            linea for linea in pagina.lineas
            if linea.orden > encabezado_pagos.orden
            and len(linea.palabras) == 1 and len(palabras_importe(linea)) == 1
        )
        return {
            "tipo": "RESUMEN_FACTURACION_Y_PAGOS",
            "pagina": pagina.numero,
            "modo_facturacion": self.campo_documentado(
                documento, normalizar_texto(" ".join(p.texto for p in modo_words)).replace(" ", "_"),
                modo_words, modo_linea, "resumen_facturacion", "modo_facturacion", "VALOR_TRAS_MODO_DE_FACTURACION",
            ),
            "fecha_facturacion": self.campo_documentado(
                documento, fecha_iso(fecha_facturacion.texto), [fecha_facturacion], fecha_facturacion_linea,
                "resumen_facturacion", "fecha_facturacion", "FECHA_FACTURACION_EXPLICITA", literal=fecha_facturacion.texto,
            ),
            "relacion_facturas": filas_facturas,
            "total_relacion_facturas": self._campo_importe_linea(documento, total_facturas_linea, "resumen_facturacion", "total_relacion_facturas"),
            "relacion_pagos": filas_pagos,
            "total_relacion_pagos": self._campo_importe_linea(documento, total_pagos_linea, "resumen_pagos", "total_relacion_pagos"),
            "condiciones_impago": self._condiciones_impago(documento, pagina, total_pagos_linea),
        }

    def _fila_relacion_factura(self, documento, linea):
        fechas = palabras_fecha(linea)
        referencia = next(p for p in linea.palabras if FACTURA_RE.fullmatch(p.texto))
        importe, valor = palabras_importe(linea)[0]
        tipo_clase = next(p for p in linea.palabras if fechas[0].bbox.x1 < p.bbox.x0 < referencia.bbox.x0)
        concepto = [p for p in linea.palabras if referencia.bbox.x1 < p.bbox.x0 < fechas[1].bbox.x0]
        return {
            "referencia": self.campo_documentado(documento, referencia.texto, [referencia], linea, "relacion_facturas", "referencia", "REFERENCIA_FACTURA_RESUMEN"),
            "fecha_factura": self.campo_documentado(documento, fecha_iso(fechas[0].texto), [fechas[0]], linea, "relacion_facturas", "fecha_factura", "FECHA_FACTURA_RESUMEN", literal=fechas[0].texto),
            "clasificacion_documental": self.campo_documentado(documento, normalizar_texto(tipo_clase.texto), [tipo_clase], linea, "relacion_facturas", "clasificacion_documental", "CLASIFICACION_RESUMEN"),
            "concepto": self.campo_documentado(documento, " ".join(p.texto for p in concepto), concepto, linea, "relacion_facturas", "concepto", "CONCEPTO_RESUMEN"),
            "vencimiento": self.campo_documentado(documento, fecha_iso(fechas[1].texto), [fechas[1]], linea, "relacion_facturas", "vencimiento", "VENCIMIENTO_RESUMEN", literal=fechas[1].texto),
            "importe": self.campo_documentado(documento, valor, [importe], linea, "relacion_facturas", "importe", "IMPORTE_RESUMEN"),
        }

    def _fila_relacion_pago(self, documento, linea):
        fechas = palabras_fecha(linea)
        referencia = next(p for p in linea.palabras if FACTURA_RE.fullmatch(p.texto))
        importe, valor = palabras_importe(linea)[0]
        concepto = [p for p in linea.palabras if referencia.bbox.x1 < p.bbox.x0 < importe.bbox.x0]
        return {
            "referencia": self.campo_documentado(documento, referencia.texto, [referencia], linea, "relacion_pagos", "referencia", "REFERENCIA_FACTURA_PAGO"),
            "fecha_pago_vencimiento": self.campo_documentado(documento, fecha_iso(fechas[0].texto), [fechas[0]], linea, "relacion_pagos", "fecha_pago_vencimiento", "FECHA_PAGO_RESUMEN", literal=fechas[0].texto),
            "fecha_factura": self.campo_documentado(documento, fecha_iso(fechas[1].texto), [fechas[1]], linea, "relacion_pagos", "fecha_factura", "FECHA_FACTURA_PAGO", literal=fechas[1].texto),
            "concepto": self.campo_documentado(documento, " ".join(p.texto for p in concepto), concepto, linea, "relacion_pagos", "concepto", "CONCEPTO_PAGO"),
            "importe": self.campo_documentado(documento, valor, [importe], linea, "relacion_pagos", "importe", "IMPORTE_PAGO"),
        }

    def _condiciones_impago(self, documento, pagina, total_pagos_linea):
        proveedor = next(l for l in pagina.lineas if "F-08-173395" in l.texto)
        lineas = [l for l in pagina.lineas if total_pagos_linea.orden < l.orden < proveedor.orden]
        comision = next(l for l in lineas if "COMISSIO FIXA" in normalizar_texto(l.texto))
        interes = next(l for l in lineas if "INTERES DE DEMORA" in normalizar_texto(l.texto))
        bloque_marco = [l for l in lineas if l.orden < comision.orden and normalizar_texto(l.texto) != "-"]
        bloque_comision = [l for l in lineas if comision.orden <= l.orden < interes.orden and normalizar_texto(l.texto) not in {"-", "PER"}]
        bloque_interes = [l for l in lineas if l.orden >= interes.orden and normalizar_texto(l.texto) not in {"-", "PER A"}]
        importe_word = next(p for p in comision.palabras if re.fullmatch(r"\(?35", p.texto))
        tasa_word = next(p for p in interes.palabras if p.texto == "0,04")
        return [
            {
                "categoria_documental": "MARCO_GENERAL_IMPAGO",
                "literal": self.campo_multilinea(documento, " | ".join(l.texto for l in bloque_marco), [p for l in bloque_marco for p in l.palabras], bloque_marco, "condiciones_impago", "literal", "BLOQUE_MARCO_GENERAL_IMPAGO"),
                "genera_movimiento": False,
            },
            {
                "categoria_documental": "COMISION_FIJA_IMPAGO",
                "literal": self.campo_multilinea(documento, " | ".join(l.texto for l in bloque_comision), [p for l in bloque_comision for p in l.palabras], bloque_comision, "condiciones_impago", "literal", "BLOQUE_COMISION_FIJA"),
                "importe_euros": self.campo_documentado(documento, 35.0, [importe_word], comision, "condiciones_impago", "importe_euros", "IMPORTE_IMPRESO_COMISION", literal=importe_word.texto),
                "genera_movimiento": False,
            },
            {
                "categoria_documental": "INTERES_DEMORA",
                "literal": self.campo_multilinea(documento, " | ".join(l.texto for l in bloque_interes), [p for l in bloque_interes for p in l.palabras], bloque_interes, "condiciones_impago", "literal", "BLOQUE_INTERES_DEMORA"),
                "tasa_diaria_centimos": self.campo_documentado(documento, 0.04, [tasa_word], interes, "condiciones_impago", "tasa_diaria_centimos", "TASA_DIARIA_IMPRESA", literal=tasa_word.texto),
                "genera_movimiento": False,
            },
        ]

    def declarar_conciliaciones(
        self, documento, segmentos, *, cabecera, albaranes, movimientos,
        impuestos, vencimientos, otros, facturas,
    ):
        if not facturas:
            return []
        resumen = next(
            (p for p in documento.paginas if "RELACIO DE FACTURES/CARRECS ACTUAL" in normalizar_texto(p.texto)),
            None,
        )
        if resumen is None:
            return []
        encabezado_facturas = self._linea(resumen, "RELACIO DE FACTURES/CARRECS ACTUAL")
        encabezado_pagos = self._linea(resumen, "RELACIO DE PAGAMENTS PREVISTOS PER DATA")
        filas_factura = [
            l for l in resumen.lineas
            if encabezado_facturas.orden < l.orden < encabezado_pagos.orden
            and any(FACTURA_RE.fullmatch(p.texto) for p in l.palabras)
            and len(palabras_importe(l)) == 1
        ]
        filas_pago = [
            l for l in resumen.lineas
            if l.orden > encabezado_pagos.orden
            and any(FACTURA_RE.fullmatch(p.texto) for p in l.palabras)
            and len(palabras_importe(l)) == 1
        ]
        ids_facturas = {f["cabecera"]["numero_factura"]["valor"] for f in facturas}
        if {next(p.texto for p in l.palabras if FACTURA_RE.fullmatch(p.texto)) for l in filas_factura} != ids_facturas:
            return []
        total_facturas_linea = next(
            l for l in resumen.lineas
            if encabezado_facturas.orden < l.orden < encabezado_pagos.orden
            and len(l.palabras) == 1 and len(palabras_importe(l)) == 1
        )
        total_pagos_linea = next(
            l for l in resumen.lineas
            if l.orden > encabezado_pagos.orden
            and len(l.palabras) == 1 and len(palabras_importe(l)) == 1
        )
        total_facturas = self._campo_importe_linea(documento, total_facturas_linea, "resumen", "total_facturas")
        total_pagos = self._campo_importe_linea(documento, total_pagos_linea, "resumen", "total_pagos")
        return [
            EspecificacionConciliacion(
                "RESUMEN_DOCUMENTOS_DESDE_FACTURAS", "TOTAL_FACTURAS_RESUMEN",
                self._comp_campo("TOTAL_RESUMEN", total_facturas, "resumen_documental"),
                [self._comp_campo(f["cabecera"]["numero_factura"]["valor"], f["cabecera"]["importe_total"], "factura_segmentada") for f in facturas],
                {"regla_relacion": "IDENTIDADES_COINCIDENTES_EN_RESUMEN_Y_SEGMENTOS", "identidades": sorted(ids_facturas)},
            ),
            EspecificacionConciliacion(
                "RESUMEN_PAGOS_DESDE_VENCIMIENTOS", "TOTAL_PAGOS_RESUMEN",
                self._comp_campo("TOTAL_PAGOS", total_pagos, "resumen_pagos"),
                [self._comp_campo(f["cabecera"]["numero_factura"]["valor"], f["vencimientos"][0]["importe"], "vencimiento_segmentado") for f in facturas],
                {"regla_relacion": "IDENTIDADES_COINCIDENTES_Y_UN_VENCIMIENTO_POR_FACTURA", "filas_pago": len(filas_pago)},
            ),
        ]

    def incidencias_extraccion(self, documento, segmentos):
        return []

    def _factura_mercancia(self, documento, pagina, segmento):
        cabecera = self._cabecera(documento, pagina, "FEDEFARMA_MERCANCIA_RESUMEN_FISCAL")
        albaranes = self._albaranes_mercancia(documento, pagina)
        movimientos = self._movimientos_mercancia(documento, pagina)
        impuestos = self._impuestos_mercancia(documento, pagina)
        vencimientos = self._vencimientos_mercancia(documento, pagina)
        otros = self._otros_mercancia(documento, pagina)
        controles = self._controles_mercancia(documento, pagina, cabecera, albaranes, movimientos, impuestos, vencimientos, otros)
        incidencias = [
            {"codigo": "MONEDA_NO_DOCUMENTADA", "bloqueante": False},
            {"codigo": "SENTIDO_NO_DOCUMENTADO", "coleccion": "albaranes", "cantidad": len(albaranes), "bloqueante": False},
            {"codigo": "SENTIDO_NO_DOCUMENTADO", "coleccion": "movimientos", "cantidad": len(movimientos), "bloqueante": False},
            {"codigo": "CATEGORIA_MOVIMIENTO_NO_DECIDIDA", "concepto": "ABONAMENTOS", "cantidad": 1, "bloqueante": False},
        ]
        return self._ensamblar_factura(documento.sha_documento, segmento, "FEDEFARMA_MERCANCIA_RESUMEN_FISCAL", cabecera, albaranes, movimientos, impuestos, vencimientos, otros, controles, incidencias)

    def _factura_servicio(self, documento, pagina, segmento):
        cabecera = self._cabecera(documento, pagina, "FEDEFARMA_SERVICIO_LINEA")
        movimientos = self._movimientos_servicio(documento, pagina)
        impuestos = self._impuestos_servicio(documento, pagina)
        vencimientos = self._vencimientos_servicio(documento, pagina)
        otros = self._otros_servicio(documento, pagina)
        controles = self._controles_servicio(cabecera, movimientos, impuestos, vencimientos)
        incidencias = [{"codigo": "SENTIDO_NO_DOCUMENTADO", "coleccion": "movimientos", "cantidad": len(movimientos), "bloqueante": False}]
        return self._ensamblar_factura(documento.sha_documento, segmento, "FEDEFARMA_SERVICIO_LINEA", cabecera, [], movimientos, impuestos, vencimientos, otros, controles, incidencias)

    def _cabecera(self, documento, pagina: PaginaLocal, layout: str):
        factura_linea = next(l for l in pagina.lineas if any(FACTURA_RE.fullmatch(p.texto) for p in l.palabras))
        numero = next(p for p in factura_linea.palabras if FACTURA_RE.fullmatch(p.texto))
        fechas = palabras_fecha(factura_linea)
        fecha = fechas[0] if layout == "FEDEFARMA_MERCANCIA_RESUMEN_FISCAL" else fechas[1]
        tipo_linea = next(
            l for l in pagina.lineas
            if any(normalizar_texto(p.texto) == "FACTURA" for p in l.palabras)
            and not any(FACTURA_RE.fullmatch(p.texto) for p in l.palabras)
        )
        tipo = next(p for p in tipo_linea.palabras if normalizar_texto(p.texto) == "FACTURA")
        nombre_linea = next(l for l in pagina.lineas if "PUIG SALOMON PIO" in normalizar_texto(l.texto))
        nombre_words = [p for p in nombre_linea.palabras if p.texto not in {"(S30213)"}]
        nif_linea = next(l for l in pagina.lineas if normalizar_texto(l.texto).startswith(("CIF ", "NIF:")))
        nif = next(p for p in nif_linea.palabras if re.fullmatch(r"\d{8}[A-Z]", p.texto))
        direccion_lineas = [l for l in pagina.lineas if normalizar_texto(l.texto).startswith(("CL SANT LLUC", "43550 ULLDECONA", "TARRAGONA"))]
        direccion_words = [
            p for l in direccion_lineas for p in l.palabras
            if layout == "FEDEFARMA_SERVICIO_LINEA" or p.bbox.x0 < 250
        ]
        proveedor_linea = next(l for l in reversed(pagina.lineas) if "F-08-173395" in l.texto)
        proveedor_nif = next(p for p in proveedor_linea.palabras if p.texto == "F-08-173395")
        proveedor_name = proveedor_linea.palabras[:3]
        proveedor_address = proveedor_linea.palabras[3:-2]
        total_linea = self._linea(pagina, "LIQUID FACTURA") if layout == "FEDEFARMA_MERCANCIA_RESUMEN_FISCAL" else self._linea(pagina, "TOTAL FACTURA")
        total_word, total = palabras_importe(total_linea)[-1]
        moneda = None
        if layout == "FEDEFARMA_SERVICIO_LINEA":
            divisa_linea = next(l for l in pagina.lineas if "EUR" in [p.texto for p in l.palabras])
            euro = next(p for p in divisa_linea.palabras if p.texto == "EUR")
            moneda = self.campo_documentado(documento, "EUR", [euro], divisa_linea, "cabecera", "moneda", "DIVISA_EXPLICITA")
        base_total, iva_total, re_total, otros_total = self._totales_fiscales(documento, pagina, layout)
        codigo = self._palabra_opcional(pagina, r"S\d{5}")
        codigo_farmacia = self._valor_despues_etiqueta(pagina, "FARMACIA")
        ruta = self._valor_despues_etiqueta(pagina, "RUTA") or self._palabra_opcional(pagina, r"\d{6}")
        zona = self._palabra_opcional(pagina, r"REUS")
        fecha_impresion = fechas[0] if layout == "FEDEFARMA_SERVICIO_LINEA" else None
        return {
            "proveedor": {
                "nombre": self.campo_documentado(documento, " ".join(p.texto for p in proveedor_name), proveedor_name, proveedor_linea, "cabecera", "proveedor_nombre", "RAZON_SOCIAL_PIE"),
                "nif": self.campo_documentado(documento, proveedor_nif.texto, [proveedor_nif], proveedor_linea, "cabecera", "proveedor_nif", "CIF_PIE"),
                "direccion": self.campo_documentado(documento, " ".join(p.texto for p in proveedor_address), proveedor_address, proveedor_linea, "cabecera", "proveedor_direccion", "DIRECCION_PIE"),
            },
            "destinatario": {
                "nombre": self.campo_documentado(documento, " ".join(p.texto for p in nombre_words), nombre_words, nombre_linea, "cabecera", "destinatario_nombre", "BLOQUE_DESTINATARIO"),
                "nif": self.campo_documentado(documento, nif.texto, [nif], nif_linea, "cabecera", "destinatario_nif", "NIF_DESTINATARIO"),
                "direccion": self.campo_multilinea(documento, " ".join(p.texto for p in direccion_words), direccion_words, direccion_lineas, "cabecera", "destinatario_direccion", "DIRECCION_DESTINATARIO"),
            },
            "numero_factura": self.campo_documentado(documento, numero.texto, [numero], factura_linea, "cabecera", "numero_factura", "IDENTIDAD_FACTURA_CABECERA"),
            "fecha_factura": self.campo_documentado(documento, fecha_iso(fecha.texto), [fecha], factura_linea, "cabecera", "fecha_factura", "FECHA_FACTURA_CABECERA", literal=fecha.texto),
            "fecha_impresion": self.campo_documentado(documento, fecha_iso(fecha_impresion.texto), [fecha_impresion], factura_linea, "cabecera", "fecha_impresion", "FECHA_IMPRESION_CABECERA", literal=fecha_impresion.texto) if fecha_impresion else None,
            "tipo_documento": self.campo_documentado(documento, "FACTURA", [tipo], tipo_linea, "cabecera", "tipo_documento", "ETIQUETA_FACTURA"),
            "moneda": moneda,
            "importe_total": self.campo_documentado(documento, total, [total_word], total_linea, "totales", "importe_total", "TOTAL_FACTURA_EXPLICITO"),
            "base_imponible_total": base_total,
            "iva_total": iva_total,
            "recargo_equivalencia_total": re_total,
            "otros_total": otros_total,
            "codigo_cliente": self._campo_palabra(documento, codigo, "cabecera", "codigo_cliente", "CODIGO_FARMACIA") if codigo else None,
            "codigo_farmacia": self._campo_palabra(documento, codigo_farmacia, "cabecera", "codigo_farmacia", "VALOR_TRAS_ETIQUETA_FARMACIA") if codigo_farmacia else None,
            "ruta": self._campo_palabra(documento, ruta, "cabecera", "ruta", "RUTA_EXPLICITA") if ruta else None,
            "zona": self._campo_palabra(documento, zona, "cabecera", "zona", "ZONA_EXPLICITA") if zona else None,
        }

    def _albaranes_mercancia(self, documento, pagina):
        salida = []
        for linea in pagina.lineas:
            ids = [p for p in linea.palabras if ALBARAN_RE.fullmatch(p.texto)]
            fechas = palabras_fecha(linea)
            importes = palabras_importe(linea)
            if len(ids) != 1 or len(fechas) != 2 or len(importes) != 5:
                continue
            tipo_words = [p for p in linea.palabras if fechas[0].bbox.x1 < p.bbox.x0 < ids[0].bbox.x0]
            valores = dict(zip(CATEGORIAS + ("TOTAL",), importes, strict=True))
            evidencias = {
                "numero_albaran": self.evidencia(documento, pagina.numero, ids[0].texto, ids[0].bbox, linea.texto, linea.bbox, "albaranes", "numero", "TOKEN_BAJO_N_ALBARA", "LITERAL_LOCAL"),
                "fecha": self.evidencia(documento, pagina.numero, fechas[0].texto, fechas[0].bbox, linea.texto, linea.bbox, "albaranes", "fecha", "FECHA_MISMA_FILA", "LITERAL_LOCAL"),
                "tipo_pedido": self.evidencia(documento, pagina.numero, " ".join(p.texto for p in tipo_words), union_bbox([p.bbox for p in tipo_words]), linea.texto, linea.bbox, "albaranes", "tipo_pedido", "TOKENS_TIPO_PEDIDO", "LITERAL_LOCAL"),
                "total": self.evidencia(documento, pagina.numero, importes[-1][0].texto, importes[-1][0].bbox, linea.texto, linea.bbox, "albaranes", "total", "IMPORTE_MISMA_FILA", "LITERAL_LOCAL"),
                "base": self.evidencia(documento, pagina.numero, "+".join(p.texto for p, _ in importes[:4]), union_bbox([p.bbox for p, _ in importes[:4]]), linea.texto, linea.bbox, "albaranes", "bases", "COLUMNAS_IVA_EXPLICITAS", "LITERAL_LOCAL"),
                "sentido": None,
            }
            bases = {categoria: valores[categoria][1] for categoria in CATEGORIAS}
            salida.append(AlbaranLocal(
                ids[0].texto, fecha_iso(fechas[0].texto), " ".join(p.texto for p in tipo_words),
                list(bases.values()), valores["TOTAL"][1], None, "DETALLE_ALBARAN", pagina.numero,
                len(salida) + 1, evidencias, bases,
                {"vencimiento": self.campo_documentado(documento, fecha_iso(fechas[1].texto), [fechas[1]], linea, "albaranes", "vencimiento", "VENCIMIENTO_MISMA_FILA", literal=fechas[1].texto)},
            ))
        return salida

    def _movimientos_mercancia(self, documento, pagina):
        abon_linea = self._linea(pagina, "TOTAL ABONAMENTS")
        detalle = next(l for l in pagina.lineas if any(ABONAMENTO_RE.fullmatch(p.texto) for p in l.palabras))
        bonif = self._linea(pagina, "BONIFICACIO PAGAMENT")
        condicion = self._linea(pagina, "CONDICIO OPERATIVA")
        salida = [
            self._movimiento_fila(documento, abon_linea, "ABONAMENTOS", "DEVOLUCION_MERCANCIA", detalle=detalle),
            self._movimiento_fila(documento, bonif, "BONIFICACION_PAGO_INMEDIATO", "BONIFICACION"),
            self._movimiento_fila(documento, condicion, "CONDICION_OPERATIVA", "CONDICION_COMERCIAL"),
        ]
        for orden, item in enumerate(salida, 1):
            item["orden"] = orden
        return salida

    def _movimiento_fila(self, documento, linea, concepto, categoria, *, detalle=None):
        importes = palabras_importe(linea)
        concepto_words = [p for p in linea.palabras if p.bbox.x1 < importes[0][0].bbox.x0]
        bases = {categoria_base: self.campo_documentado(documento, valor, [palabra], linea, "movimientos", categoria_base, f"COLUMNA_{categoria_base}") for categoria_base, (palabra, valor) in zip(CATEGORIAS, importes[:4], strict=True)}
        item = {
            "orden": 0,
            "descripcion_literal": self.campo_documentado(documento, " ".join(p.texto for p in concepto_words), concepto_words, linea, "movimientos", "descripcion", "LITERAL_CONCEPTO"),
            "concepto_normalizado": concepto,
            "categoria": categoria,
            "origen_categoria": "NORMALIZACION_CONCEPTUAL_SIN_INFERIR_SENTIDO",
            "sentido": None,
            "fecha": None,
            "bases": bases,
            "base": self.campo_documentado(documento, importes[-1][1], [importes[-1][0]], linea, "movimientos", "base", "TOTAL_FILA_MOVIMIENTO"),
            "importe": self.campo_documentado(documento, importes[-1][1], [importes[-1][0]], linea, "movimientos", "importe", "TOTAL_FILA_MOVIMIENTO"),
            "iva": None,
            "recargo": None,
            "provenance": {"bloque": "RESUMEN_ECONOMICO_MERCANCIA"},
            "incidencias": ([{"codigo": "CATEGORIA_MOVIMIENTO_NO_DECIDIDA"}] if categoria == "OTRO" else []),
        }
        if detalle is not None:
            item["detalle_documental"] = self._detalle_abonamento(documento, detalle)
            item["provenance"]["detalle"] = "DETALL_ABONAMENTS"
        return item

    def _detalle_abonamento(self, documento, linea):
        fechas = palabras_fecha(linea)
        origen = next(p for p in linea.palabras if re.fullmatch(r"\d{4}-\d{7}", p.texto))
        abono = next(p for p in linea.palabras if ABONAMENTO_RE.fullmatch(p.texto))
        posicion_abono = linea.palabras.index(abono)
        motivo = linea.palabras[posicion_abono + 1]
        pvp = next(p for p in linea.palabras[posicion_abono + 2:] if re.fullmatch(r"-?\d+,\d+", p.texto))
        posicion_pvp = linea.palabras.index(pvp)
        numericos = [p for p in linea.palabras[posicion_pvp:] if re.fullmatch(r"-?\d+(?:,\d+)?", p.texto)]
        if len(numericos) != 5:
            raise ValueError("DETALLE_ABONAMENTO_COLUMNAS_NO_DEMOSTRABLES")
        descripcion = [p for p in linea.palabras if motivo.bbox.x1 < p.bbox.x0 < pvp.bbox.x0]
        pagina = documento.paginas[linea.pagina - 1]
        continuaciones = self.lineas_continuacion_columna(
            pagina.lineas, linea, x0=motivo.bbox.x1, x1=pvp.bbox.x0, salto_maximo=10.0,
        )
        descripcion_completa = [*descripcion, *(p for l in continuaciones for p in l.palabras)]
        lineas_descripcion = [linea, *continuaciones]
        return {
            "fecha_entrega": self.campo_documentado(documento, fecha_iso(fechas[0].texto), [fechas[0]], linea, "detalle_abonamentos", "fecha_entrega", "FECHA_ENTREGA", literal=fechas[0].texto),
            "origen": self.campo_documentado(documento, origen.texto, [origen], linea, "detalle_abonamentos", "origen", "ALBARAN_ORIGEN"),
            "fecha_albaran": self.campo_documentado(documento, fecha_iso(fechas[1].texto), [fechas[1]], linea, "detalle_abonamentos", "fecha_albaran", "FECHA_ALBARAN", literal=fechas[1].texto),
            "abonamento": self.campo_documentado(documento, abono.texto, [abono], linea, "detalle_abonamentos", "abonamento", "IDENTIDAD_ABONAMENTO"),
            "motivo": self.campo_documentado(documento, motivo.texto, [motivo], linea, "detalle_abonamentos", "motivo", "CODIGO_MOTIVO"),
            "descripcion": self.campo_multilinea(documento, " ".join(p.texto for p in descripcion_completa), descripcion_completa, lineas_descripcion, "detalle_abonamentos", "descripcion", "DESCRIPCION_PRODUCTO_MULTILINEA"),
            "literal_completo": self.campo_multilinea(documento, " | ".join(l.texto for l in lineas_descripcion), [p for l in lineas_descripcion for p in l.palabras], lineas_descripcion, "detalle_abonamentos", "literal_completo", "FILA_Y_CONTINUACIONES_GEOMETRICAS"),
            "pvp": self.campo_documentado(documento, self._decimal(numericos[0].texto), [numericos[0]], linea, "detalle_abonamentos", "pvp", "COLUMNA_PVP"),
            "porcentaje_ab": self.campo_documentado(documento, self._decimal(numericos[1].texto), [numericos[1]], linea, "detalle_abonamentos", "porcentaje_ab", "COLUMNA_PORCENTAJE_AB"),
            "cantidad": self.campo_documentado(documento, self._decimal(numericos[2].texto), [numericos[2]], linea, "detalle_abonamentos", "cantidad", "COLUMNA_CANTIDAD"),
            "pvl": self.campo_documentado(documento, self._decimal(numericos[3].texto), [numericos[3]], linea, "detalle_abonamentos", "pvl", "COLUMNA_PVL"),
            "importe": self.campo_documentado(documento, self._decimal(numericos[4].texto), [numericos[4]], linea, "detalle_abonamentos", "importe", "COLUMNA_IMPORTE"),
            "conclusion_categoria": "DEVOLUCION_MERCANCIA_DECISION_FUNCIONAL_PIO",
            "sentido": None,
        }

    def _impuestos_mercancia(self, documento, pagina):
        bases_linea = self._linea(pagina, "BASES IMPOSABLES")
        iva_linea = self._linea(pagina, "I.V.A. S/BASES")
        re_linea = self._linea(pagina, "RECARREC EQUIVALENCIA")
        totals_linea = self._linea(pagina, "TOTALS")
        header = self._linea(pagina, "DATA ALBARA")
        bases = palabras_importe(bases_linea)
        cuotas_iva = palabras_importe(iva_linea)
        totals = palabras_importe(totals_linea)
        headers_iva = [p for p in header.palabras if re.fullmatch(r"I\.V\.A\.\d+%", p.texto, re.I)]
        tipos_re, cuotas_re, total_re = self._recargo_mercancia(documento, re_linea)
        salida = []
        for i, categoria in enumerate(CATEGORIAS):
            tipo_iva = int(re.search(r"(\d+)%", headers_iva[i].texto).group(1))
            item = {
                "orden": i + 1,
                "categoria_base": self.campo_documentado(documento, categoria, [headers_iva[i]], header, "fiscalidad", "categoria_base", "ENCABEZADO_IVA"),
                "base": self.campo_documentado(documento, bases[i][1], [bases[i][0]], bases_linea, "fiscalidad", "base", f"COLUMNA_{categoria}"),
                "tipo_iva": self.campo_documentado(documento, tipo_iva, [headers_iva[i]], header, "fiscalidad", "tipo_iva", "PORCENTAJE_IVA_IMPRESO"),
                "cuota_iva": self.campo_documentado(documento, cuotas_iva[i][1], [cuotas_iva[i][0]], iva_linea, "fiscalidad", "cuota_iva", f"COLUMNA_{categoria}"),
                "tipo_recargo_equivalencia": tipos_re[i],
                "cuota_recargo_equivalencia": cuotas_re[i],
                "total_tramo": self.campo_documentado(documento, totals[i][1], [totals[i][0]], totals_linea, "fiscalidad", "total_tramo", f"COLUMNA_{categoria}"),
            }
            calculado = round(item["base"]["valor"] + item["cuota_iva"]["valor"] + item["cuota_recargo_equivalencia"]["valor"], 2)
            item["control_aritmetico"] = "OK" if calculado == item["total_tramo"]["valor"] else "DIFERENCIA_DOCUMENTAL"
            salida.append(item)
        salida.append({
            "tipo": "TOTALES_FISCALES",
            "base": self.campo_documentado(documento, bases[-1][1], [bases[-1][0]], bases_linea, "fiscalidad", "base_total", "TOTAL_FILA_BASES"),
            "cuota_iva": self.campo_documentado(documento, cuotas_iva[-1][1], [cuotas_iva[-1][0]], iva_linea, "fiscalidad", "iva_total", "TOTAL_FILA_IVA"),
            "cuota_recargo_equivalencia": total_re,
            "total": self.campo_documentado(documento, totals[-1][1], [totals[-1][0]], totals_linea, "fiscalidad", "total", "TOTAL_FILA_FISCAL"),
        })
        return salida

    def _recargo_mercancia(self, documento, linea):
        words = linea.palabras
        numeric = [p for p in words if re.fullmatch(r"-?\d+(?:,\d+)+", p.texto)]
        values: list[tuple[PalabraLocal, str, float]] = []
        for palabra in numeric:
            fused = re.fullmatch(r"(-?\d+,\d{2})(-?\d+,\d)", palabra.texto)
            if fused:
                values.extend([(palabra, fused.group(1), self._decimal(fused.group(1))), (palabra, fused.group(2), self._decimal(fused.group(2)))])
            else:
                values.append((palabra, palabra.texto, self._decimal(palabra.texto)))
        tipos_raw = (values[0], values[2], values[4], values[6])
        cuotas_raw = (values[1], values[3], values[5], values[7])
        tipos = [self.campo_documentado(documento, value, [word], linea, "fiscalidad", "tipo_recargo", "PORCENTAJE_RE_IMPRESO", literal=literal) for word, literal, value in tipos_raw]
        cuotas = [self.campo_documentado(documento, value, [word], linea, "fiscalidad", "cuota_recargo", "CUOTA_RE_IMPRESA", literal=literal) for word, literal, value in cuotas_raw]
        total_word, total_literal, total_value = values[8]
        total = self.campo_documentado(documento, total_value, [total_word], linea, "fiscalidad", "recargo_total", "TOTAL_FILA_RE", literal=total_literal)
        return tipos, cuotas, total

    def _vencimientos_mercancia(self, documento, pagina):
        encabezado = self._linea(pagina, "VENCIMENTS")
        linea = next(
            l for l in pagina.lineas
            if l.orden > encabezado.orden
            and len(palabras_fecha(l)) == 1
            and len(palabras_importe(l)) == 1
        )
        fecha = palabras_fecha(linea)[0]
        importe, valor = palabras_importe(linea)[0]
        return [{
            "orden": 1,
            "fecha": self.campo_documentado(documento, fecha_iso(fecha.texto), [fecha], linea, "vencimientos", "fecha", "FECHA_VENCIMIENTO", literal=fecha.texto),
            "importe": self.campo_documentado(documento, valor, [importe], linea, "vencimientos", "importe", "IMPORTE_VENCIMIENTO"),
            "medio_pago": None,
        }]

    def _otros_mercancia(self, documento, pagina):
        total_albaranes_linea = self._linea(pagina, "TOTAL ALBARANS")
        total_albaranes_importes = palabras_importe(total_albaranes_linea)
        labels = self._linea(pagina, "TRANSFER DIRECT")
        values = next(
            l for l in pagina.lineas
            if l.orden > labels.orden and len(palabras_importe(l)) == 5
        )
        nombres = ["TRANSFER", "DIRECT", "RDS", "RESTA_ESPECIALITATS", "RESTA_PARAFARMACIA_OTROS"]
        salida = [{
            "tipo": "AGREGADO_TOTAL_ALBARANES",
            "literal": self.campo_documentado(documento, total_albaranes_linea.texto, total_albaranes_linea.palabras, total_albaranes_linea, "otros", "total_albaranes_literal", "FILA_TOTAL_ALBARANES"),
            "desglose": {
                nombre: self.campo_documentado(documento, valor, [palabra], total_albaranes_linea, "otros", nombre, f"TOTAL_ALBARANES_{nombre}")
                for nombre, (palabra, valor) in zip((*CATEGORIAS, "TOTAL"), total_albaranes_importes, strict=True)
            },
            "total": self.campo_documentado(documento, total_albaranes_importes[-1][1], [total_albaranes_importes[-1][0]], total_albaranes_linea, "otros", "total_albaranes", "TOTAL_ALBARANES_EXPLICITO"),
        }, {
            "tipo": "DISTRIBUCION_ECONOMICA",
            "valores": {
                nombre: self.campo_documentado(documento, valor, [palabra], values, "otros", nombre, "COLUMNA_DISTRIBUCION")
                for nombre, (palabra, valor) in zip(nombres, palabras_importe(values), strict=True)
            },
            "encabezado": self.campo_documentado(documento, labels.texto, labels.palabras, labels, "otros", "encabezado", "ENCABEZADO_DISTRIBUCION"),
        }]
        salida.extend(self._aviso_scrap(documento, pagina))
        return salida

    def _movimientos_servicio(self, documento, pagina):
        linea = next(l for l in pagina.lineas if any(re.fullmatch(r"\d{4}\.\d{2}\.\d{5}", p.texto) for p in l.palabras))
        articulo = next(p for p in linea.palabras if re.fullmatch(r"\d{4}\.\d{2}\.\d{5}", p.texto))
        importes = palabras_importe(linea)
        descripcion = [p for p in linea.palabras if articulo.bbox.x1 < p.bbox.x0 < importes[0][0].bbox.x0]
        continuaciones = self.lineas_continuacion_columna(
            pagina.lineas, linea, x0=articulo.bbox.x1, x1=importes[0][0].bbox.x0, salto_maximo=12.0,
        )
        description_words = descripcion + [p for l in continuaciones for p in l.palabras]
        desc = self.campo_multilinea(documento, " ".join(p.texto for p in description_words), description_words, [linea, *continuaciones], "movimientos", "descripcion", "LINEA_ARTICULO_SERVICIO")
        net_word, net = importes[-1]
        es_condicion_cooperativa = "CUOTA MENSUAL SERVICIOS COOPERATIVOS" in normalizar_texto(desc["valor"])
        return [{
            "orden": 1,
            "descripcion_literal": desc,
            "concepto_normalizado": "CONDICION_COOPERATIVA" if es_condicion_cooperativa else "SERVICIO_FEDEFARMA",
            "categoria": "CONDICION_COOPERATIVA" if es_condicion_cooperativa else "SERVICIO",
            "origen_categoria": "LITERAL_CUOTA_MENSUAL_SERVICIOS_COOPERATIVOS" if es_condicion_cooperativa else "DESCRIPCION_DOCUMENTAL_DE_SERVICIO",
            "sentido": None,
            "fecha": None,
            "base": self.campo_documentado(documento, net, [net_word], linea, "movimientos", "base", "IMPORTE_NETO_LINEA"),
            "importe": self.campo_documentado(documento, net, [net_word], linea, "movimientos", "importe", "IMPORTE_NETO_LINEA"),
            "iva": None,
            "recargo": None,
            "articulo": self.campo_documentado(documento, articulo.texto, [articulo], linea, "movimientos", "articulo", "CODIGO_ARTICULO"),
            "cantidad": self.campo_documentado(documento, importes[0][1], [importes[0][0]], linea, "movimientos", "cantidad", "CANTIDAD_FACTURADA"),
            "precio": self.campo_documentado(documento, importes[1][1], [importes[1][0]], linea, "movimientos", "precio", "PRECIO_IMPRESO"),
            "tipo_iva": self.campo_documentado(documento, importes[2][1], [importes[2][0]], linea, "movimientos", "tipo_iva", "PORCENTAJE_IMPUESTO_LINEA"),
            "provenance": {"bloque": "TABLA_ARTICULOS_SERVICIOS"},
            "incidencias": [],
        }]

    def _impuestos_servicio(self, documento, pagina):
        linea = next(l for l in pagina.lineas if "NACIONAL ORDINARIO" in normalizar_texto(l.texto))
        importes = palabras_importe(linea)
        sin_recargo = [p for p in linea.palabras if normalizar_texto(p.texto).strip("()") in {"SIN", "RECARGO"}]
        return [{
            "orden": 1,
            "categoria_base": self.campo_documentado(documento, "NACIONAL_ORDINARIO_SIN_RECARGO", linea.palabras[:-3], linea, "fiscalidad", "categoria_base", "DESCRIPCION_FISCAL"),
            "base": self.campo_documentado(documento, importes[0][1], [importes[0][0]], linea, "fiscalidad", "base", "BASE_IMPONIBLE_IMPRESA"),
            "tipo_iva": self.campo_documentado(documento, importes[1][1], [importes[1][0]], linea, "fiscalidad", "tipo_iva", "PORCENTAJE_IVA_IMPRESO"),
            "cuota_iva": self.campo_documentado(documento, importes[2][1], [importes[2][0]], linea, "fiscalidad", "cuota_iva", "CUOTA_IVA_IMPRESA"),
            "tipo_recargo_equivalencia": None,
            "cuota_recargo_equivalencia": None,
            "estado_recargo": self.campo_documentado(documento, "SIN_RECARGO_CUALITATIVO", sin_recargo, linea, "fiscalidad", "estado_recargo", "LITERAL_SIN_RECARGO"),
            "total_tramo": None,
            "control_aritmetico": "NO_EVALUABLE",
        }]

    def _vencimientos_servicio(self, documento, pagina):
        linea = next(l for l in pagina.lineas if "RECIBO DOMICILIADO BANCO" in normalizar_texto(l.texto))
        fecha = palabras_fecha(linea)[0]
        importe, valor = palabras_importe(linea)[0]
        medio = [p for p in linea.palabras if p.bbox.x1 < fecha.bbox.x0]
        return [{
            "orden": 1,
            "fecha": self.campo_documentado(documento, fecha_iso(fecha.texto), [fecha], linea, "vencimientos", "fecha", "FECHA_VENCIMIENTO", literal=fecha.texto),
            "importe": self.campo_documentado(documento, valor, [importe], linea, "vencimientos", "importe", "IMPORTE_VENCIMIENTO"),
            "medio_pago": self.campo_documentado(documento, " ".join(p.texto for p in medio), medio, linea, "vencimientos", "medio_pago", "VIA_PAGO_EXPLICITA"),
        }]

    def _otros_servicio(self, documento, pagina):
        factura = next(l for l in pagina.lineas if any(FACTURA_RE.fullmatch(p.texto) for p in l.palabras))
        comerciales = next(l for l in pagina.lineas if any(p.texto == "EUR" for p in l.palabras))
        fechas = palabras_fecha(factura)
        importes = [p for p in comerciales.palabras if re.fullmatch(r"-?\d+,\d{3}", p.texto)]
        euro = next(p for p in comerciales.palabras if p.texto == "EUR")
        delegacion = comerciales.palabras[comerciales.palabras.index(euro) + 1]
        ports = [p for p in factura.palabras if fechas[1].bbox.x1 < p.bbox.x0 < fechas[2].bbox.x0]
        salida = [{
            "tipo": "CONDICIONES_COMERCIALES_SERVICIO",
            "descuento_pago_inmediato": self.campo_documentado(documento, self._decimal(importes[0].texto), [importes[0]], comerciales, "otros", "descuento_pago_inmediato", "VALOR_BAJO_DESCUENTO_P_INMEDIATO"),
            "descuento_general": self.campo_documentado(documento, self._decimal(importes[1].texto), [importes[1]], comerciales, "otros", "descuento_general", "VALOR_BAJO_DESCUENTO_GENERAL"),
            "portes": self.campo_documentado(documento, " ".join(p.texto for p in ports), ports, factura, "otros", "portes", "VALOR_BAJO_PORTS"),
            "fecha_valor": self.campo_documentado(documento, fecha_iso(fechas[2].texto), [fechas[2]], factura, "otros", "fecha_valor", "VALOR_BAJO_DATA_VALOR", literal=fechas[2].texto),
            "delegacion": self.campo_documentado(documento, delegacion.texto, [delegacion], comerciales, "otros", "delegacion", "VALOR_BAJO_DELEGACIO"),
        }]
        restantes = comerciales.palabras[comerciales.palabras.index(delegacion) + 1:]
        if restantes:
            salida[0]["estado_comercial"] = self.campo_documentado(documento, " ".join(p.texto for p in restantes), restantes, comerciales, "otros", "estado_comercial", "LITERAL_COMERCIAL_ADICIONAL")
        salida.extend(self._aviso_scrap(documento, pagina))
        return salida

    def _aviso_scrap(self, documento, pagina):
        linea = next((l for l in pagina.lineas if "CONTRIBUCIO AL SCRAP" in normalizar_texto(l.texto)), None)
        if linea is None:
            return []
        return [{
            "tipo": "AVISO_SCRAP",
            "literal": self.campo_documentado(documento, linea.texto, linea.palabras, linea, "otros", "aviso_scrap", "AVISO_DOCUMENTAL_PIE"),
        }]

    def _controles_mercancia(self, documento, pagina, cabecera, albaranes, movimientos, impuestos, vencimientos, otros):
        fiscal_total = impuestos[-1]
        total_albaranes = round(sum(a.total or 0 for a in albaranes), 2)
        mov = {m["concepto_normalizado"]: m for m in movimientos}
        subtotal_linea = next(
            linea for linea in pagina.lineas
            if normalizar_texto(linea.palabras[0].texto) == "TOTAL"
            and len(palabras_importe(linea)) == 5
            and len(linea.palabras) == 6
        )
        subtotal_campo = self.campo_documentado(
            documento, palabras_importe(subtotal_linea)[-1][1],
            [palabras_importe(subtotal_linea)[-1][0]], subtotal_linea,
            "totales", "subtotal_mercancia", "TOTAL_RESUMEN_MERCANCIA",
        )
        controles = [
            EspecificacionConciliacion("SUBTOTAL_DESDE_DETALLE", "TOTAL", self._comp_campo("TOTAL", subtotal_campo, "fila_total"), [self._comp("ALBARANES", total_albaranes, "albaranes"), self._comp_campo("ABONAMENTOS", mov["ABONAMENTOS"]["importe"], "movimientos"), self._comp_campo("BONIFICACION", mov["BONIFICACION_PAGO_INMEDIATO"]["importe"], "movimientos")], {"regla_relacion": "BLOQUE_RESUMEN_MERCANCIA"}),
            EspecificacionConciliacion("BASE_DESDE_SUBTOTAL", "BASE_IMPONIBLE", self._comp_campo("BASE_IMPONIBLE", cabecera["base_imponible_total"], "fiscalidad"), [self._comp_campo("SUBTOTAL", subtotal_campo, "fila_total"), self._comp_campo("CONDICION_OPERATIVA", mov["CONDICION_OPERATIVA"]["importe"], "movimientos")], {"regla_relacion": "TOTAL_MAS_CONDICION_OPERATIVA"}),
            EspecificacionConciliacion("TOTAL_DESDE_FISCALIDAD", "TOTAL_FACTURA", self._comp_campo("TOTAL", cabecera["importe_total"], "totales"), [self._comp_campo("BASE", cabecera["base_imponible_total"], "fiscalidad"), self._comp_campo("IVA", cabecera["iva_total"], "fiscalidad"), self._comp_campo("RE", cabecera["recargo_equivalencia_total"], "fiscalidad")], {"regla_relacion": "BASE_MAS_IVA_MAS_RE"}),
            EspecificacionConciliacion("VENCIMIENTO_DESDE_TOTAL", "VENCIMIENTO", self._comp_campo("VENCIMIENTO", vencimientos[0]["importe"], "vencimientos"), [self._comp_campo("TOTAL", cabecera["importe_total"], "totales")], {"regla_relacion": "FACTURA_Y_VENCIMIENTO_UNICOS"}),
        ]
        return evaluar_conciliaciones(controles)

    def _controles_servicio(self, cabecera, movimientos, impuestos, vencimientos):
        return evaluar_conciliaciones([
            EspecificacionConciliacion("BASE_DESDE_LINEA_SERVICIO", "BASE_IMPONIBLE", self._comp_campo("BASE", cabecera["base_imponible_total"], "fiscalidad"), [self._comp_campo("LINEA_SERVICIO", movimientos[0]["base"], "movimientos")], {"regla_relacion": "UNICA_LINEA_Y_UNICO_TRAMO"}),
            EspecificacionConciliacion("TOTAL_DESDE_FISCALIDAD", "TOTAL_FACTURA", self._comp_campo("TOTAL", cabecera["importe_total"], "totales"), [self._comp_campo("BASE", cabecera["base_imponible_total"], "fiscalidad"), self._comp_campo("IVA", cabecera["iva_total"], "fiscalidad")], {"regla_relacion": "BASE_MAS_IVA"}),
            EspecificacionConciliacion("VENCIMIENTO_DESDE_TOTAL", "VENCIMIENTO", self._comp_campo("VENCIMIENTO", vencimientos[0]["importe"], "vencimientos"), [self._comp_campo("TOTAL", cabecera["importe_total"], "totales")], {"regla_relacion": "FACTURA_Y_VENCIMIENTO_UNICOS"}),
        ])

    def _totales_fiscales(self, documento, pagina, layout):
        if layout == "FEDEFARMA_MERCANCIA_RESUMEN_FISCAL":
            base_l = self._linea(pagina, "BASES IMPOSABLES")
            iva_l = self._linea(pagina, "I.V.A. S/BASES")
            re_l = self._linea(pagina, "RECARREC EQUIVALENCIA")
            base_w, base = palabras_importe(base_l)[-1]
            iva_w, iva = palabras_importe(iva_l)[-1]
            re_values = self._numeric_fragments(re_l)
            re_w, re_literal, re_value = re_values[-1]
            return (
                self.campo_documentado(documento, base, [base_w], base_l, "fiscalidad", "base_total", "TOTAL_BASES"),
                self.campo_documentado(documento, iva, [iva_w], iva_l, "fiscalidad", "iva_total", "TOTAL_IVA"),
                self.campo_documentado(documento, re_value, [re_w], re_l, "fiscalidad", "recargo_total", "TOTAL_RE", literal=re_literal),
                None,
            )
        fiscal = next(l for l in pagina.lineas if "NACIONAL ORDINARIO" in normalizar_texto(l.texto))
        vals = palabras_importe(fiscal)
        return (
            self.campo_documentado(documento, vals[0][1], [vals[0][0]], fiscal, "fiscalidad", "base_total", "BASE_IMPONIBLE_IMPRESA"),
            self.campo_documentado(documento, vals[2][1], [vals[2][0]], fiscal, "fiscalidad", "iva_total", "CUOTA_IVA_IMPRESA"),
            None,
            None,
        )

    def _numeric_fragments(self, linea):
        salida = []
        for palabra in linea.palabras:
            if not re.fullmatch(r"-?\d+(?:,\d+)+", palabra.texto):
                continue
            fused = re.fullmatch(r"(-?\d+,\d{2})(-?\d+,\d)", palabra.texto)
            if fused:
                salida.extend([(palabra, fused.group(1), self._decimal(fused.group(1))), (palabra, fused.group(2), self._decimal(fused.group(2)))])
            else:
                salida.append((palabra, palabra.texto, self._decimal(palabra.texto)))
        return salida

    @staticmethod
    def _decimal(value):
        return float(value.replace(".", "").replace(",", "."))

    @staticmethod
    def _ensamblar_factura(sha_documento, segmento, layout, cabecera, albaranes, movimientos, impuestos, vencimientos, otros, controles, incidencias):
        return {
            "segmento": {"sha_documento": sha_documento, "paginas": segmento.paginas, "identidad": segmento.identidad_candidata, "estado": segmento.estado, "regla": segmento.regla, "evidencias": segmento.evidencias},
            "layout": layout,
            "cabecera": cabecera,
            "albaranes": albaranes,
            "movimientos": movimientos,
            "impuestos": impuestos,
            "vencimientos": vencimientos,
            "otros": otros,
            "controles_conciliacion": controles,
            "incidencias": incidencias,
        }

    @staticmethod
    def _factura_layout_desconocido(sha_documento, segmento, codigo):
        return {"segmento": {"sha_documento": sha_documento, "paginas": segmento.paginas, "identidad": segmento.identidad_candidata, "estado": segmento.estado, "regla": segmento.regla, "evidencias": segmento.evidencias}, "layout": None, "cabecera": {}, "albaranes": [], "movimientos": [], "impuestos": [], "vencimientos": [], "otros": [], "controles_conciliacion": [], "incidencias": [{"codigo": codigo, "bloqueante": True}]}

    @staticmethod
    def _linea(pagina, inicio):
        objetivo = normalizar_texto(inicio)
        return next(l for l in pagina.lineas if normalizar_texto(l.texto).startswith(objetivo))

    def _campo_palabra(self, documento, palabra, tabla, columna, regla):
        linea = self._linea_de_palabra(documento, palabra)
        return self.campo_documentado(documento, palabra.texto, [palabra], linea, tabla, columna, regla)

    def _campo_importe_linea(self, documento, linea, tabla, columna):
        palabra, valor = palabras_importe(linea)[0]
        return self.campo_documentado(documento, valor, [palabra], linea, tabla, columna, "TOTAL_DOCUMENTAL_EXPLICITO")

    @staticmethod
    def _linea_de_palabra(documento, palabra):
        pagina = documento.paginas[palabra.pagina - 1]
        return next(l for l in pagina.lineas if palabra in l.palabras)

    @staticmethod
    def _palabra_opcional(pagina, patron):
        return next((p for p in pagina.palabras if re.fullmatch(patron, p.texto)), None)

    @staticmethod
    def _valor_despues_etiqueta(pagina, etiqueta):
        objetivo = normalizar_texto(etiqueta).rstrip(":")
        for linea in pagina.lineas:
            for i, palabra in enumerate(linea.palabras[:-1]):
                if normalizar_texto(palabra.texto).rstrip(":") == objetivo:
                    return linea.palabras[i + 1]
        return None

    @staticmethod
    def _comp(concepto, valor, fuente):
        return ComponenteConciliacion(concepto, valor, "SUMA_DOCUMENTAL", fuente, None)

    @staticmethod
    def _comp_campo(concepto, campo, fuente):
        if not campo:
            return ComponenteConciliacion(concepto, None, None, fuente, None)
        ev = campo.get("evidencias", [])
        pagina = ev[0].pagina if ev and hasattr(ev[0], "pagina") else None
        return ComponenteConciliacion(concepto, campo["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", fuente, pagina, ev)
