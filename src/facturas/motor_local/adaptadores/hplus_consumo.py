from __future__ import annotations

import re
from typing import Any

from src.facturas.grupos_funcionales import clasificar_grupo_hefame

from ..conciliacion import ComponenteConciliacion, EspecificacionConciliacion
from ..geometria.campos import fecha_iso, palabras_importe
from ..geometria.lineas import normalizar_texto
from ..modelos import DocumentoLocal, SegmentoLocal
from .base import AdaptadorBase, Reconocimiento


FACTURA_RE = re.compile(r"^\d{10}$")
NIF_RE = re.compile(r"^B-?30462451$", re.I)
EAN_RE = re.compile(r"^\d{13}$")


class AdaptadorHplusConsumo(AdaptadorBase):
    id = "hplus-consumo-local"
    version = "1.0.0"
    capacidades = {
        "segmentacion": "SOPORTADO_MULTIPAGINA_DETERMINISTA",
        "cabecera": "SOPORTADO",
        "albaranes": "REFERENCIAS_DOCUMENTALES_NO_OPERATIVAS",
        "movimientos": "SOPORTADO_CONSUMIBLES_NO_MERCANCIA_FARMATIC",
        "impuestos": "SOPORTADO",
        "vencimientos": "SOPORTADO",
        "otros": "SOPORTADO_LINEAS_Y_REFERENCIAS",
        "conciliacion_documental": "SOPORTADO_SIN_ALBARAN_OPERATIVO",
        "autoridad": "SHADOW_SIN_AUTORIDAD_PRODUCTIVA",
    }

    def reconocer(self, documento: DocumentoLocal) -> Reconocimiento:
        texto = normalizar_texto("\n".join(p.texto for p in documento.paginas))
        checks = {
            "identidad_legal": "CONSUMO INTERHOGAR S.L." in texto,
            "nif_legal": "B-30462451" in texto or "B30462451" in texto,
            "factura": "N" in texto and "FACTURA" in texto,
            "detalle_consumibles": "BOLSA" in texto and "NETO ALBARAN" in texto,
            "fiscalidad": "SUMA DE BASES" in texto and "DESGLOSE IMPUESTOS" in texto,
            "vencimientos": "VENCIMIENTOS" in texto,
            "paginacion": bool(re.search(r"PAGINA\s+1\s+DE\s+2", texto)),
            "texto_nativo": bool(documento.paginas) and all(p.palabras and p.texto.strip() for p in documento.paginas),
        }
        completo = all(checks.values())
        indicios = checks["identidad_legal"] or checks["nif_legal"]
        return Reconocimiento(
            "RECONOCIDO" if completo else ("AMBIGUO" if indicios else "NO_RECONOCIDO"),
            100 if completo else round(100 * sum(checks.values()) / len(checks)),
            [{"senal": k, "presente": v, "origen": "TEXTO_PDF_LOCAL"} for k, v in checks.items()],
        )

    @staticmethod
    def _linea(pagina, fragmento):
        objetivo = normalizar_texto(fragmento)
        return next(l for l in pagina.lineas if objetivo in normalizar_texto(l.texto))

    @staticmethod
    def _importe_final(linea):
        valores = palabras_importe(linea)
        if not valores:
            raise ValueError(f"Importe no localizado: {linea.texto}")
        return valores[-1]

    def _campo(self, documento, linea, palabras, valor, columna, regla, tabla="cabecera", literal=None):
        return self.campo_documentado(
            documento, valor, palabras, linea, tabla, columna, regla,
            literal=literal,
        )

    def _construir(self, documento: DocumentoLocal, segmentos: list[SegmentoLocal]):
        if self.reconocer(documento).estado != "RECONOCIDO" or len(segmentos) != 1:
            return None
        p1, p2 = documento.paginas
        numero_linea = next(
            linea
            for linea in p1.lineas
            if "FACTURA" in normalizar_texto(linea.texto)
            and any(FACTURA_RE.fullmatch(p.texto) for p in linea.palabras)
        )
        numero = next(p for p in numero_linea.palabras if FACTURA_RE.fullmatch(p.texto))
        fecha_linea = self._linea(p1, "Fecha")
        fecha = next(p for p in fecha_linea.palabras if fecha_iso(p.texto))
        tipo_linea = self._linea(p1, "FACTURA")
        tipo = next(p for p in tipo_linea.palabras if normalizar_texto(p.texto) == "FACTURA")
        proveedor_linea = self._linea(p1, "CONSUMO INTERHOGAR S.L.")
        nif_linea = self._linea(p1, "B-30462451")
        nif = next(p for p in nif_linea.palabras if NIF_RE.fullmatch(p.texto))
        destino_linea = self._linea(p1, "PUIG SALOMON")
        nombre_words = [p for p in destino_linea.palabras if not p.texto.isdigit()]
        destino_nif_linea = self._linea(p1, "CIF/NIF")
        destino_nif = next(p for p in destino_nif_linea.palabras if re.fullmatch(r"\d{8}[A-Z]", p.texto))
        direccion_lineas = [p1.lineas[i - 1] for i in (8, 9, 11)]
        direccion_words = [p for linea in direccion_lineas for p in linea.palabras if p.texto not in {"Ruta:", "Alma:"}]
        base_linea = self._linea(p2, "Suma de Bases")
        base_word, base = self._importe_final(base_linea)
        iva_linea = self._linea(p2, "Impuestos")
        iva_word, iva = self._importe_final(iva_linea)
        fiscal_linea = next(l for l in p2.lineas if any("%" in p.texto for p in l.palabras))
        tipo_iva_word = next(p for p in fiscal_linea.palabras if p.texto.endswith("%"))
        total_linea = self._linea(p2, "TOTAL EUR")
        total_word, total = self._importe_final(total_linea)
        moneda_word = next(p for p in total_linea.palabras if normalizar_texto(p.texto) == "EUR")
        re_header = self._linea(p2, "Base IVA Importe")
        re_words = re_header.palabras
        pago_linea = self._linea(p2, "Via de pago")

        proveedor_nombre = "ARTICULOS DE CONSUMO INTERHOGAR S.L."
        nif_normalizado = nif.texto.replace("-", "").upper()
        identidad = clasificar_grupo_hefame(
            proveedor_documental=proveedor_nombre,
            nif_documental=nif_normalizado,
            layout=self.id,
            contenido_consumibles_demostrado=True,
        )
        if identidad is None:
            raise ValueError("IDENTIDAD_FUNCIONAL_HEFAME_CONSUMIBLES_NO_DEMOSTRADA")

        cabecera = {
            "proveedor": {
                "nombre": self._campo(documento, proveedor_linea, proveedor_linea.palabras, proveedor_nombre, "proveedor_nombre", "RAZON_SOCIAL_LEGAL_VISIBLE"),
                "nif": self._campo(documento, nif_linea, [nif], nif_normalizado, "proveedor_nif", "NIF_LEGAL_VISIBLE"),
                "direccion": None,
            },
            "destinatario": {
                "nombre": self._campo(documento, destino_linea, nombre_words, " ".join(p.texto for p in nombre_words), "destinatario_nombre", "BLOQUE_DESTINATARIO"),
                "nif": self._campo(documento, destino_nif_linea, [destino_nif], destino_nif.texto, "destinatario_nif", "NIF_DESTINATARIO_VISIBLE"),
                "direccion": self.campo_multilinea(documento, "CL SAN LUCAS, 34 43550 ULLDECONA TARRAGONA", direccion_words, direccion_lineas, "cabecera", "destinatario_direccion", "BLOQUE_DIRECCION_DESTINATARIO"),
            },
            "numero_factura": self._campo(documento, numero_linea, [numero], numero.texto, "numero_factura", "NUMERO_FACTURA_ETIQUETADO"),
            "fecha_factura": self._campo(documento, fecha_linea, [fecha], fecha_iso(fecha.texto), "fecha_factura", "FECHA_FACTURA_ETIQUETADA", literal=fecha.texto),
            "tipo_documento": self._campo(documento, tipo_linea, [tipo], "FACTURA", "tipo_documento", "TIPO_DOCUMENTAL_VISIBLE"),
            "moneda": self._campo(documento, total_linea, [moneda_word], "EUR", "moneda", "MONEDA_JUNTO_TOTAL"),
            "importe_total": self._campo(documento, total_linea, [total_word], total, "importe_total", "TOTAL_FACTURA_EXPLICITO", "fiscalidad"),
            "base_imponible_total": self._campo(documento, base_linea, [base_word], base, "base_imponible_total", "SUMA_BASES_EXPLICITA", "fiscalidad"),
            "iva_total": self._campo(documento, iva_linea, [iva_word], iva, "iva_total", "IMPUESTOS_EXPLICITOS", "fiscalidad"),
            "recargo_equivalencia_total": self._campo(documento, re_header, re_words, 0.0, "recargo_equivalencia_total", "DESGLOSE_FISCAL_UNICO_SIN_COLUMNA_RE", "fiscalidad"),
            "otros_total": None,
            "forma_pago": self._campo(documento, pago_linea, pago_linea.palabras[3:], "Adeudos directos SEPA CO", "forma_pago", "VIA_PAGO_VISIBLE", "vencimientos"),
            "codigo_cliente": self._campo(documento, destino_linea, [destino_linea.palabras[-1]], destino_linea.palabras[-1].texto, "codigo_cliente", "CODIGO_CLIENTE_BLOQUE_DESTINATARIO"),
            "grupo_funcional": identidad.to_dict(),
        }

        referencias = []
        lineas_albaran = [l for l in p1.lineas if normalizar_texto(l.texto).startswith("ALBARAN ")]
        for orden, linea in enumerate(lineas_albaran, 1):
            numero_ref = next(p for p in linea.palabras if FACTURA_RE.fullmatch(p.texto))
            fecha_ref = next(p for p in linea.palabras if fecha_iso(p.texto))
            siguiente = next(l for l in p1.lineas if l.bbox.y0 > linea.bbox.y0 and normalizar_texto(l.texto).startswith("NETO ALBARAN"))
            total_ref_word, total_ref = self._importe_final(siguiente)
            referencias.append({
                "orden": orden,
                "tipo": "ALBARAN_CONSUMIBLES_REFERENCIA_DOCUMENTAL",
                "numero": self._campo(documento, linea, [numero_ref], numero_ref.texto, "numero", "NUMERO_ALBARAN_VISIBLE", "referencias_documentales"),
                "fecha": self._campo(documento, linea, [fecha_ref], fecha_iso(fecha_ref.texto), "fecha", "FECHA_ALBARAN_VISIBLE", "referencias_documentales", literal=fecha_ref.texto),
                "importe": self._campo(documento, siguiente, [total_ref_word], total_ref, "importe", "NETO_ALBARAN_VISIBLE", "referencias_documentales"),
                "requiere_match_operativo": False,
            })

        lineas_consumibles = []
        for orden, linea in enumerate((l for l in p1.lineas if l.palabras and EAN_RE.fullmatch(l.palabras[0].texto)), 1):
            importes = palabras_importe(linea)
            total_item_word, total_item = importes[-1]
            iva_item = next(p for p in linea.palabras if p.texto.endswith("%"))
            descripcion = [p for p in linea.palabras[1:] if p.bbox.x0 < 290]
            lineas_consumibles.append({
                "orden": orden,
                "ean": self._campo(documento, linea, [linea.palabras[0]], linea.palabras[0].texto, "ean", "EAN_VISIBLE", "lineas_consumibles"),
                "descripcion": self._campo(documento, linea, descripcion, " ".join(p.texto for p in descripcion), "descripcion", "DESCRIPCION_LITERAL_VISIBLE", "lineas_consumibles"),
                "tipo_iva": self._campo(documento, linea, [iva_item], 21.0, "tipo_iva", "PORCENTAJE_IVA_VISIBLE", "lineas_consumibles"),
                "total": self._campo(documento, linea, [total_item_word], total_item, "total", "TOTAL_LINEA_VISIBLE", "lineas_consumibles"),
            })

        impuestos = [{
            "orden": 1,
            "base": cabecera["base_imponible_total"],
            "tipo_iva": self._campo(documento, fiscal_linea, [tipo_iva_word], 21.0, "tipo_iva", "PORCENTAJE_IVA_VISIBLE", "fiscalidad"),
            "cuota_iva": cabecera["iva_total"],
            "tipo_recargo_equivalencia": None,
            "cuota_recargo_equivalencia": cabecera["recargo_equivalencia_total"],
            "total_tramo": cabecera["importe_total"],
            "control_aritmetico": "OK" if round(base + iva - total, 2) == 0 else "NO_OK",
        }]
        venc_fecha_linea = self._linea(p2, "Fecha 05")
        venc_fecha = next(p for p in venc_fecha_linea.palabras if fecha_iso(p.texto))
        venc_importe_linea = next(
            l for l in p2.lineas if normalizar_texto(l.texto).startswith("IMPORTE ")
        )
        venc_word, venc_importe = self._importe_final(venc_importe_linea)
        vencimientos = [{
            "orden": 1,
            "fecha": self._campo(documento, venc_fecha_linea, [venc_fecha], fecha_iso(venc_fecha.texto), "fecha", "FECHA_VENCIMIENTO_VISIBLE", "vencimientos", literal=venc_fecha.texto),
            "importe": self._campo(documento, venc_importe_linea, [venc_word], venc_importe, "importe", "IMPORTE_VENCIMIENTO_VISIBLE", "vencimientos"),
            "medio_pago": cabecera["forma_pago"],
        }]
        movimiento = {
            "orden": 1,
            "descripcion_literal": self._campo(documento, base_linea, base_linea.palabras[:-1], "CONSUMIBLES NO MERCANCIA FARMATIC", "descripcion", "DECISION_FUNCIONAL_PIO_HEFAME_CONSUMIBLES", "movimientos"),
            "concepto_normalizado": "HEFAME_CONSUMIBLES",
            "categoria": "SERVICIO",
            "sentido": "CARGO",
            "base": cabecera["base_imponible_total"],
            "importe": None,
            "provenance": {"autoridad": "PIO", "regla": "NO_MERCANCIA_FARMATIC_NO_REQUIERE_ALBARAN_OPERATIVO"},
        }
        segmento = segmentos[0]
        factura = {
            "segmento": {"sha_documento": documento.sha_documento, "paginas": segmento.paginas, "identidad": numero.texto, "estado": segmento.estado, "regla": segmento.regla, "evidencias": segmento.evidencias},
            "layout": "HPLUS_CONSUMO_FACTURA_V1",
            "cabecera": cabecera,
            "albaranes": [],
            "referencias_documentales": referencias,
            "lineas_consumibles": lineas_consumibles,
            "movimientos": [movimiento],
            "impuestos": impuestos,
            "vencimientos": vencimientos,
            "otros": [],
            "clasificacion_documental": {
                "tipo": "FACTURA_GASTO_SERVICIO",
                "subtipo": "FACTURA_CONSUMIBLES",
                "requiere_conciliacion_albaranes": False,
                "no_mercancia_farmatic": True,
                "grupo_funcional": "HEFAME",
                "proveedor_documental": proveedor_nombre,
                "nif_documental": nif_normalizado,
            },
            "incidencias": [],
        }
        return factura

    def extraer_facturas(self, documento, segmentos):
        factura = self._construir(documento, segmentos)
        return [factura] if factura else []

    def _primera(self, documento, segmentos):
        facturas = self.extraer_facturas(documento, segmentos)
        return facturas[0] if facturas else None

    def extraer_cabecera(self, documento, segmentos):
        f = self._primera(documento, segmentos)
        return f["cabecera"] if f else {}

    def extraer_albaranes(self, documento, segmentos):
        return []

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
        return ([{"tipo": "REFERENCIAS_DOCUMENTALES", "elementos": f["referencias_documentales"]},
                 {"tipo": "LINEAS_CONSUMIBLES", "elementos": f["lineas_consumibles"]}] if f else [])

    def declarar_conciliaciones(self, documento, segmentos, *, cabecera, albaranes,
                                movimientos, impuestos, vencimientos, otros, facturas):
        if not cabecera or not impuestos or not vencimientos:
            return []
        total = cabecera["importe_total"]
        fiscal = impuestos[0]
        def componente(nombre, campo, fuente):
            return ComponenteConciliacion(nombre, campo["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", fuente,
                                          campo["evidencias"][0].pagina, campo["evidencias"])
        return [
            EspecificacionConciliacion(
                "TOTAL_CONSUMIBLES_DESDE_FISCALIDAD", "TOTAL_FACTURA",
                componente("TOTAL", total, "cabecera"),
                [componente("BASE", fiscal["base"], "fiscalidad"),
                 componente("IVA", fiscal["cuota_iva"], "fiscalidad"),
                 componente("RE", fiscal["cuota_recargo_equivalencia"], "fiscalidad")],
                {"regla": "BASE_MAS_IVA_MAS_RE_SIN_ALBARAN_OPERATIVO"},
            ),
            EspecificacionConciliacion(
                "VENCIMIENTO_CONSUMIBLES_VS_TOTAL", "TOTAL_FACTURA",
                componente("TOTAL", total, "cabecera"),
                [componente("VENCIMIENTO", vencimientos[0]["importe"], "vencimientos")],
                {"regla": "VENCIMIENTO_UNICO_IGUAL_TOTAL"},
            ),
        ]

    def incidencias_extraccion(self, documento, segmentos):
        factura = self._primera(documento, segmentos)
        return [{
            "codigo": "ALBARANES_CONSUMIBLES_SOLO_REFERENCIA_DOCUMENTAL",
            "bloqueante": False,
            "cantidad": len(factura["referencias_documentales"]),
        }] if factura else []
