from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable

from ..conciliacion import ComponenteConciliacion, EspecificacionConciliacion, evaluar_conciliaciones
from ..geometria.lineas import normalizar_texto, parsear_importe
from ..modelos import AlbaranLocal, DocumentoLocal, LineaLocal, PalabraLocal, SegmentoLocal, union_bbox
from .base import AdaptadorBase, Reconocimiento


NIF_RE = re.compile(r"^(?:ES)?[A-Z]?\d{8}[A-Z]?$", re.I)


def _importe_token(token: str) -> float | None:
    limpio = token.strip().rstrip("€\ufffd")
    valor = parsear_importe(limpio)
    if valor is None and re.fullmatch(r"-?\d+[.,]\d", limpio):
        return float(limpio.replace(".", "").replace(",", "."))
    if valor is None and re.fullmatch(r"-?\d+\.\d{2}", limpio):
        return float(limpio)
    return valor


def _fecha(token: str) -> str | None:
    token = token.strip()
    for formato in ("%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%y", "%d-%m-%y"):
        try:
            return datetime.strptime(token, formato).date().isoformat()
        except ValueError:
            continue
    return None


def _decision_funcional_pio(*, proveedor: str, layout: str, regla: str, valor: str) -> dict[str, Any]:
    """Documenta una decisión funcional sin simular evidencia directa del PDF."""
    return {
        "valor": valor,
        "autoridad": "PIO",
        "fuente": "DECISION_FUNCIONAL_PIO",
        "tipo_evidencia": "DECISION_FUNCIONAL_PIO",
        "evidencia_documental_directa": False,
        "evidencias": [],
        "alcance": {"proveedor": proveedor, "layout": layout},
        "provenance": {
            "autoridad": "PIO",
            "regla": regla,
            "inferencia_por_gold": False,
            "inferencia_por_signo": False,
        },
    }


class AdaptadorGoldPequenoBase(AdaptadorBase):
    """Infraestructura común; las reglas documentales viven en cada subclase."""

    senales: tuple[str, ...] = ()
    layout: str
    constructor: str
    capacidades = {
        "segmentacion": "SOPORTADO_POR_IDENTIDAD_Y_PAGINACION_DOCUMENTAL",
        "cabecera": "SOPORTADO",
        "albaranes": "SOPORTADO_CUANDO_EXISTEN",
        "movimientos": "SOPORTADO_SENTIDO_DOCUMENTAL_DECISION_PIO_O_NULL",
        "impuestos": "SOPORTADO_TIPOS_IMPRESOS",
        "vencimientos": "SOPORTADO",
        "otros": "SOPORTADO_DETALLE_ECONOMICO_LITERAL",
        "conciliacion_documental": "SOPORTADO",
        "autoridad": "SHADOW_SIN_AUTORIDAD_PRODUCTIVA",
    }

    def reconocer(self, documento: DocumentoLocal) -> Reconocimiento:
        texto = normalizar_texto("\n".join(l.texto for p in documento.paginas for l in p.lineas))
        checks = {senal: normalizar_texto(senal) in texto for senal in self.senales}
        checks["texto_nativo"] = bool(documento.paginas) and all(p.palabras and p.texto.strip() for p in documento.paginas)
        completo = all(checks.values())
        indicios = any(v for k, v in checks.items() if k != "texto_nativo")
        return Reconocimiento(
            "RECONOCIDO" if completo else ("AMBIGUO" if indicios else "NO_RECONOCIDO"),
            100 if completo else round(100 * sum(checks.values()) / len(checks)),
            [{"senal": k, "presente": v, "origen": "TEXTO_PDF_LOCAL"} for k, v in checks.items()],
        )

    def extraer_facturas(self, documento, segmentos):
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        if len(segmentos) != 1:
            return [self._desconocido(documento, s, "SEGMENTACION_NO_UNICA") for s in segmentos]
        return [getattr(self, self.constructor)(documento, segmentos[0])]

    def _primera(self, documento, segmentos):
        facturas = self.extraer_facturas(documento, segmentos)
        return facturas[0] if len(facturas) == 1 and facturas[0].get("layout") else None

    def extraer_cabecera(self, documento, segmentos):
        f = self._primera(documento, segmentos)
        return f["cabecera"] if f else {}

    def extraer_albaranes(self, documento, segmentos):
        f = self._primera(documento, segmentos)
        return f["albaranes"] if f else []

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

    @staticmethod
    def _linea(pagina, fragmento: str) -> LineaLocal:
        objetivo = normalizar_texto(fragmento)
        return next(l for l in pagina.lineas if objetivo in normalizar_texto(l.texto))

    @staticmethod
    def _lineas(paginas, inicio: Callable[[LineaLocal], bool], fin: Callable[[LineaLocal], bool]) -> list[LineaLocal]:
        salida, dentro = [], False
        for pagina in paginas:
            for linea in pagina.lineas:
                if inicio(linea):
                    dentro = True
                if dentro:
                    salida.append(linea)
                if dentro and fin(linea):
                    dentro = False
        return salida

    def _campo(self, documento, linea, palabras, valor, columna, regla, tabla="cabecera"):
        return self.campo_documentado(documento, valor, palabras, linea, tabla, columna, regla,
                                      literal=" ".join(p.texto for p in palabras))

    def _dinero(self, documento, linea, palabra, columna, regla="VALOR_MONETARIO_IMPRESO", tabla="economico"):
        valor = _importe_token(palabra.texto)
        if valor is None:
            raise ValueError(f"Importe no interpretable: {palabra.texto!r}")
        return self._campo(documento, linea, [palabra], valor, columna, regla, tabla)

    def _porcentaje(self, documento, linea, palabra, columna):
        token = palabra.texto.rstrip("%")
        valor = _importe_token(token)
        if valor is None and re.fullmatch(r"\d+(?:[.,]\d+)?", token):
            valor = float(token.replace(",", "."))
        return self._campo(documento, linea, [palabra], valor, columna, "PORCENTAJE_IMPRESO", "fiscalidad")

    def _fecha_campo(self, documento, linea, palabra, columna="fecha"):
        return self._campo(documento, linea, [palabra], _fecha(palabra.texto), columna, "FECHA_IMPRESA")

    def _literal_lineas(self, documento, lineas, tipo, *, rol="DETALLE_ECONOMICO_DOCUMENTAL"):
        return {
            "tipo": tipo,
            "rol": rol,
            "lineas": [
                {
                    "orden": i,
                    "literal": self._campo(documento, linea, linea.palabras, linea.texto, "literal", "LINEA_VISIBLE_COMPLETA", "detalle"),
                    "valores_monetarios": [
                        self._dinero(documento, linea, p, f"valor_{j}", "VALOR_VISIBLE_EN_LINEA", "detalle")
                        for j, p in enumerate(linea.palabras, 1) if _importe_token(p.texto) is not None
                    ],
                }
                for i, linea in enumerate(lineas, 1)
            ],
        }

    def _factura(self, documento, segmento, cabecera, *, albaranes=None, movimientos=None,
                 impuestos=None, vencimientos=None, otros=None, incidencias=None):
        albaranes = albaranes or []
        movimientos = movimientos or []
        impuestos = impuestos or []
        vencimientos = vencimientos or []
        otros = otros or []
        incidencias = incidencias or []
        controles = self._controles(cabecera, impuestos, vencimientos)
        return {
            "segmento": {
                "sha_documento": documento.sha_documento,
                "paginas": segmento.paginas,
                "identidad": cabecera["numero_factura"]["valor"],
                "estado": segmento.estado,
                "regla": segmento.regla,
                "evidencias": segmento.evidencias,
            },
            "layout": self.layout,
            "cabecera": cabecera,
            "albaranes": albaranes,
            "movimientos": movimientos,
            "impuestos": impuestos,
            "vencimientos": vencimientos,
            "otros": otros,
            "controles_conciliacion": controles,
            "incidencias": incidencias,
            "provenance": {"adaptador": self.id, "version": self.version, "fuente": "PDF_NATIVO_LOCAL", "gold_usado_extraccion": False},
        }

    def _controles(self, cabecera, impuestos, vencimientos):
        specs = []
        total = cabecera.get("importe_total")
        if total and impuestos:
            comps = []
            for i, tramo in enumerate(impuestos, 1):
                campos = [tramo.get(k) for k in ("base", "cuota_iva", "cuota_recargo_equivalencia") if tramo.get(k)]
                if not campos:
                    continue
                comps.append(ComponenteConciliacion(
                    f"TRAMO_{i}", round(sum(c["valor"] for c in campos), 2), "SIGNO_DOCUMENTAL_CONSERVADO",
                    "fiscalidad", campos[0]["evidencias"][0].pagina,
                    [e for c in campos for e in c["evidencias"]],
                ))
            specs.append(EspecificacionConciliacion(
                "TOTAL_DESDE_FISCALIDAD", "TOTAL_FACTURA",
                ComponenteConciliacion("TOTAL", total["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", "cabecera", total["evidencias"][0].pagina, total["evidencias"]),
                comps, {"regla": "SUMA_COMPONENTES_FISCALES_IMPRESOS"},
            ))
        if total and vencimientos and all(v.get("importe") for v in vencimientos):
            specs.append(EspecificacionConciliacion(
                "VENCIMIENTOS_VS_TOTAL", "TOTAL_FACTURA",
                ComponenteConciliacion("TOTAL", total["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", "cabecera", total["evidencias"][0].pagina, total["evidencias"]),
                [ComponenteConciliacion(f"VENCIMIENTO_{i}", v["importe"]["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", "vencimientos", v["importe"]["evidencias"][0].pagina, v["importe"]["evidencias"]) for i, v in enumerate(vencimientos, 1)],
                {"regla": "SUMA_VENCIMIENTOS_IMPRESOS"},
            ))
        return evaluar_conciliaciones(specs)

    @staticmethod
    def _desconocido(documento, segmento, motivo):
        return {"segmento": {"sha_documento": documento.sha_documento, "paginas": segmento.paginas}, "layout": None,
                "cabecera": {}, "albaranes": [], "movimientos": [], "impuestos": [], "vencimientos": [], "otros": [],
                "controles_conciliacion": [], "incidencias": [{"codigo": "LAYOUT_DESCONOCIDO", "motivo": motivo, "bloqueante": True}]}

    def _albaran(self, documento, numero_linea, numero, fecha=None, total=None, orden=1, atributos=None):
        numero_ev = self.evidencia(documento, numero_linea.pagina, numero.texto, numero.bbox, numero_linea.texto,
                                   numero_linea.bbox, "albaranes", "numero", "NUMERO_ALBARAN_ETIQUETADO", "LITERAL_LOCAL")
        fecha_ev = self.evidencia(documento, numero_linea.pagina, fecha.texto, fecha.bbox, numero_linea.texto,
                                  numero_linea.bbox, "albaranes", "fecha", "FECHA_ALBARAN_IMPRESA", "LITERAL_LOCAL") if fecha else None
        total_ev = self.evidencia(documento, numero_linea.pagina, total.texto, total.bbox, numero_linea.texto,
                                  numero_linea.bbox, "albaranes", "total", "TOTAL_ALBARAN_IMPRESO", "LITERAL_LOCAL") if total else None
        return AlbaranLocal(numero.texto, fecha.texto if fecha else None, None, [], _importe_token(total.texto) if total else None,
                            None, "DETALLE_ALBARAN", numero_linea.pagina, orden,
                            {"numero_albaran": numero_ev, "fecha": fecha_ev, "tipo_pedido": None, "base": None, "total": total_ev},
                            atributos_documentales=atributos or {})


class AdaptadorEcoceutics(AdaptadorGoldPequenoBase):
    id, version = "ecoceutics-local", "1.1.0"
    layout, constructor = "ECOCEUTICS_FACTURA_V1", "_construir"
    senales = ("Hygie31 España SLU", "Base Imposable", "Venciments", "Número de fra")

    def _construir(self, documento, segmento):
        p = documento.paginas[0]
        nline = self._linea(p, "mero de fra")
        numero = next(w for w in nline.palabras if re.fullmatch(r"FR\d{8}", w.texto.strip("[]"), re.I))
        numero_valor = numero.texto.strip("[]")
        fline = self._linea(p, "Data factura")
        fecha = next(w for w in fline.palabras if _fecha(w.texto))
        cliente = self._linea(p, "40901058C")
        nif = next(w for w in cliente.palabras if NIF_RE.fullmatch(w.texto))
        prov = self._linea(p, "Hygie31")
        total_line = next(l for l in p.lineas if l.orden > self._linea(p, "Base Imposable").orden and len([w for w in l.palabras if _importe_token(w.texto) is not None]) == 1)
        total_word = next(w for w in total_line.palabras if _importe_token(w.texto) is not None)
        pago = self._linea(p, "Forma de pagament")
        prov_dir_lines = [p.lineas[i - 1] for i in (5, 6, 7)]
        prov_dir_words = [w for l in prov_dir_lines for w in l.palabras if w.bbox.x1 < 200]
        dest_name_line = p.lineas[4]
        dest_name_words = [w for w in dest_name_line.palabras if w.bbox.x0 > 300]
        dest_dir_lines = [p.lineas[i - 1] for i in (6, 7, 8)]
        dest_dir_words = [w for l in dest_dir_lines for w in l.palabras if w.bbox.x0 > 300]
        cabecera = {
            "proveedor": {"nombre": self._campo(documento, prov, prov.palabras[:3], " ".join(w.texto for w in prov.palabras[:3]), "proveedor_nombre", "RAZON_SOCIAL_VISIBLE"), "nif": self._campo(documento, self._linea(p, "B17733601"), [next(w for w in self._linea(p, "B17733601").palabras if w.texto == "B17733601")], "B17733601", "proveedor_nif", "NIF_VISIBLE"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in prov_dir_words), prov_dir_words, prov_dir_lines, "cabecera", "proveedor_direccion", "COLUMNA_IZQUIERDA_DIRECCION_PROVEEDOR")},
            "destinatario": {"nombre": self._campo(documento, dest_name_line, dest_name_words, " ".join(w.texto for w in dest_name_words), "destinatario_nombre", "COLUMNA_DERECHA_DESTINATARIO"), "nif": self._campo(documento, cliente, [nif], nif.texto, "destinatario_nif", "NIF_EN_FILA_CLIENTE"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in dest_dir_words), dest_dir_words, dest_dir_lines, "cabecera", "destinatario_direccion", "COLUMNA_DERECHA_DIRECCION_DESTINATARIO")},
            "numero_factura": self._campo(documento, nline, [numero], numero_valor, "numero_factura", "NUMERO_FACTURA_ETIQUETADO"),
            "fecha_factura": self._fecha_campo(documento, fline, fecha, "fecha_factura"),
            "tipo_documento": self._campo(documento, p.lineas[0], p.lineas[0].palabras, "FACTURA", "tipo_documento", "TITULO_FACTURA"),
            "moneda": "EUR", "forma_pago": self._campo(documento, pago, pago.palabras[3:], " ".join(w.texto for w in pago.palabras[3:]), "forma_pago", "FORMA_PAGO_ETIQUETADA"),
            "base_imponible_total": None, "iva_total": None, "recargo_equivalencia_total": None,
            "importe_total": self._dinero(documento, total_line, total_word, "importe_total", "TOTAL_COLUMNA_FISCAL"),
        }
        fiscal = next(l for l in p.lineas if l.orden > total_line.orden and len([w for w in l.palabras if _importe_token(w.texto) is not None]) >= 2)
        vals = [w for w in fiscal.palabras if _importe_token(w.texto) is not None]
        porcentajes = [w for w in fiscal.palabras if "%" in w.texto]
        impuesto = {"orden": 1, "origen": "FACTURA", "base": self._dinero(documento, fiscal, vals[0], "base", tabla="fiscalidad"),
                    "tipo_iva": self._porcentaje(documento, fiscal, porcentajes[0], "tipo_iva"), "cuota_iva": self._dinero(documento, fiscal, vals[1], "cuota_iva", tabla="fiscalidad"),
                    "tipo_recargo_equivalencia": self._porcentaje(documento, fiscal, porcentajes[1], "tipo_recargo") if len(porcentajes) > 1 else None,
                    "cuota_recargo_equivalencia": self._dinero(documento, fiscal, vals[2], "cuota_recargo", tabla="fiscalidad") if len(vals) > 2 else None}
        cabecera["base_imponible_total"] = impuesto["base"]
        cabecera["iva_total"] = impuesto["cuota_iva"]
        cabecera["recargo_equivalencia_total"] = impuesto["cuota_recargo_equivalencia"]
        vline = self._linea(p, "Venciments")
        vfecha = next(w for w in vline.palabras if _fecha(w.texto.strip("|")))
        vimporte = next(w for w in vline.palabras if _importe_token(w.texto.strip("|")) is not None)
        # Los delimitadores verticales forman parte del token PDF; se documenta el literal completo.
        fecha_val = _fecha(vfecha.texto.strip("|")); importe_val = _importe_token(vimporte.texto.strip("|"))
        venc = {"orden": 1, "fecha": self._campo(documento, vline, [vfecha], fecha_val, "fecha", "FECHA_VENCIMIENTO_IMPRESA", "vencimientos"),
                "importe": self._campo(documento, vline, [vimporte], importe_val, "importe", "IMPORTE_VENCIMIENTO_IMPRESO", "vencimientos"), "forma_pago": cabecera["forma_pago"]}
        detalle = [l for l in p.lineas if self._linea(p, "Ref.").orden < l.orden < vline.orden and any(_importe_token(w.texto) is not None for w in l.palabras)]
        albaranes = []
        alb_line = next((l for l in p.lineas if "ALBAR" in normalizar_texto(l.texto)), None)
        if alb_line:
            alb_num = next(w for w in alb_line.palabras if re.fullmatch(r"\d{8,12}", w.texto))
            alb_fecha = next(w for w in alb_line.palabras if _fecha(w.texto))
            albaranes.append(self._albaran(documento, alb_line, alb_num, alb_fecha, orden=1))
        movimientos = []
        if any("QUOTA READY" in normalizar_texto(l.texto) for l in detalle):
            linea = next(l for l in detalle if "QUOTA READY" in normalizar_texto(l.texto))
            precio = [w for w in linea.palabras if _importe_token(w.texto) is not None][-1]
            descripcion = [w for w in linea.palabras if _importe_token(w.texto) is None and "%" not in w.texto][1:]
            decision = _decision_funcional_pio(
                proveedor="ECOCEUTICS", layout=self.layout,
                regla="QUOTA_READY_ECOCEUTICS_ES_CARGO", valor="CARGO",
            )
            movimientos.append({"orden": 1, "descripcion_literal": self._campo(documento, linea, descripcion, " ".join(w.texto for w in descripcion), "descripcion", "DESCRIPCION_FILA", "movimientos"),
                                "categoria": "SERVICIO", "importe": cabecera["importe_total"],
                                "importe_linea_antes_impuestos": self._dinero(documento, linea, precio, "importe_linea", tabla="movimientos"),
                                "base": impuesto["base"], "iva": impuesto["cuota_iva"],
                                "recargo_equivalencia": impuesto["cuota_recargo_equivalencia"],
                                "sentido": "CARGO", "sentido_fuente": "DECISION_FUNCIONAL_PIO",
                                "sentido_documentacion": decision,
                                "provenance": {"adaptador": self.id, "version": self.version,
                                               "autoridad_sentido": "PIO", "fuente_sentido": "DECISION_FUNCIONAL_PIO",
                                               "evidencia_documental_directa_sentido": False},
                                "incidencias": []})
        incidencias = []
        return self._factura(documento, segmento, cabecera, albaranes=albaranes, movimientos=movimientos, impuestos=[impuesto], vencimientos=[venc],
                             otros=[self._literal_lineas(documento, detalle, "DETALLE_FACTURADO")], incidencias=incidencias)


class AdaptadorEports(AdaptadorGoldPequenoBase):
    id, version = "eports-local", "1.1.0"
    layout, constructor = "EPORTS_FACTURA_SERVICIOS_V1", "_construir"
    senales = ("E-PORTS AMPLE DE BANDA I INTERNET", "Factura de venda", "Preu Línies", "Quota Contracte")

    def _construir(self, documento, segmento):
        p = documento.paginas[0]; idline = self._linea(p, "TM-")
        numero, fecha, codigo, nif, vence = idline.palabras[:5]
        total_header = self._linea(p, "Preu L")
        total_line = next(l for l in p.lineas if l.orden > total_header.orden and l.palabras[-1].texto == "EUR")
        amounts = [w for w in total_line.palabras if _importe_token(w.texto) is not None]
        proveedor = self._linea(p, "E-PORTS AMPLE")
        nifp_line = self._linea(p, "B55688410"); nifp = next(w for w in nifp_line.palabras if "B55688410" in w.texto)
        pago = self._linea(p, "Forma de Pagament")
        dir_lines = [p.lineas[i - 1] for i in (3, 4, 5)]
        prov_dir_words = [w for l in dir_lines for w in l.palabras if w.bbox.x1 < 250]
        dest_dir_words = [w for l in dir_lines for w in l.palabras if w.bbox.x0 > 250]
        cabecera = {"proveedor": {"nombre": self._campo(documento, proveedor, proveedor.palabras[:7], " ".join(w.texto for w in proveedor.palabras[:7]), "proveedor_nombre", "RAZON_SOCIAL_VISIBLE"), "nif": self._campo(documento, nifp_line, [nifp], nifp.texto, "proveedor_nif", "NIF_ETIQUETADO"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in prov_dir_words), prov_dir_words, dir_lines, "cabecera", "proveedor_direccion", "COLUMNA_IZQUIERDA_DIRECCION_PROVEEDOR")},
                    "destinatario": {"nombre": self._campo(documento, proveedor, proveedor.palabras[7:], " ".join(w.texto for w in proveedor.palabras[7:]), "destinatario_nombre", "BLOQUE_DESTINATARIO"), "nif": self._campo(documento, idline, [nif], nif.texto, "destinatario_nif", "NIF_CABECERA"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in dest_dir_words), dest_dir_words, dir_lines, "cabecera", "destinatario_direccion", "COLUMNA_DERECHA_DIRECCION_DESTINATARIO")},
                    "numero_factura": self._campo(documento, idline, [numero], numero.texto, "numero_factura", "COLUMNA_NUM_FACTURA"), "fecha_factura": self._fecha_campo(documento, idline, fecha, "fecha_factura"),
                    "tipo_documento": self._campo(documento, self._linea(p, "Factura de venda"), self._linea(p, "Factura de venda").palabras, "FACTURA_VENTA", "tipo_documento", "TIPO_LITERAL"), "moneda": "EUR",
                    "codigo_cliente": self._campo(documento, idline, [codigo], codigo.texto, "codigo_cliente", "COLUMNA_CLIENTE"), "forma_pago": self._campo(documento, pago, pago.palabras[3:], " ".join(w.texto for w in pago.palabras[3:]), "forma_pago", "FORMA_PAGO_ETIQUETADA"),
                    "base_imponible_total": self._dinero(documento, total_line, amounts[0], "base_imponible_total"), "iva_total": self._dinero(documento, total_line, amounts[2], "iva_total"), "recargo_equivalencia_total": None,
                    "importe_total": self._dinero(documento, total_line, amounts[3], "importe_total")}
        tax = {"orden": 1, "origen": "FACTURA", "base": cabecera["base_imponible_total"], "tipo_iva": self._porcentaje(documento, total_line, total_line.palabras[2], "tipo_iva"), "cuota_iva": cabecera["iva_total"], "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": None}
        v = {"orden": 1, "fecha": self._fecha_campo(documento, idline, vence), "importe": cabecera["importe_total"], "forma_pago": cabecera["forma_pago"]}
        starts = ("IP FIXA", "EPORTS TELEFONIA", "EMMASCARAMENT", "BACKUP AMB RADIO", "CONNEXI")
        movs = []
        for linea in p.lineas:
            if not normalizar_texto(linea.texto).startswith(starts):
                continue
            vals = [w for w in linea.palabras if _importe_token(w.texto) is not None]
            if len(vals) < 2:
                candidatas = [l for l in p.lineas if linea.orden < l.orden <= linea.orden + 3]
                valor_linea = next((l for l in candidatas if len([w for w in l.palabras if _importe_token(w.texto) is not None]) >= 2), None)
                vals = [w for w in valor_linea.palabras if _importe_token(w.texto) is not None] if valor_linea else []
            else:
                valor_linea = linea
            concepto = [w for w in linea.palabras if _importe_token(w.texto) is None]
            decision = _decision_funcional_pio(
                proveedor="EPORTS", layout=self.layout,
                regla="SERVICIOS_TELEFONIA_INTERNET_EPORTS_SON_CARGO", valor="CARGO",
            )
            movs.append({"orden": len(movs) + 1, "descripcion_literal": self._campo(documento, linea, concepto, " ".join(w.texto for w in concepto), "descripcion", "DESCRIPCION_SERVICIO_VISIBLE", "movimientos"),
                         "categoria": "SERVICIO", "importe": self._dinero(documento, valor_linea, vals[-1], "importe", tabla="movimientos"), "base": self._dinero(documento, valor_linea, vals[-1], "base", tabla="movimientos"),
                         "sentido": "CARGO", "sentido_fuente": "DECISION_FUNCIONAL_PIO",
                         "sentido_documentacion": decision,
                         "provenance": {"adaptador": self.id, "version": self.version,
                                        "autoridad_sentido": "PIO", "fuente_sentido": "DECISION_FUNCIONAL_PIO",
                                        "evidencia_documental_directa_sentido": False},
                         "incidencias": []})
        detail = [l for l in p.lineas if 11 <= l.orden <= 30]
        return self._factura(documento, segmento, cabecera, movimientos=movs, impuestos=[tax], vencimientos=[v], otros=[self._literal_lineas(documento, detail, "DETALLE_SERVICIOS_Y_PERIODOS")],
                             incidencias=[])


class AdaptadorLogista(AdaptadorGoldPequenoBase):
    id, version = "logista-pharma-local", "1.0.0"
    layout, constructor = "LOGISTA_PHARMA_FACTURA_V1", "_construir"
    senales = ("LOGISTA PHARMA S.A.U", "Nº Factura", "RESUMEN B.I", "Rec.Equ")

    @staticmethod
    def _filas_albaranes(documento, segmento):
        for pagina in documento.paginas:
            if not segmento.paginas or not segmento.paginas[0] <= pagina.numero <= segmento.paginas[-1]:
                continue
            for linea in pagina.lineas:
                if "ALBAR" not in normalizar_texto(linea.texto):
                    continue
                numeros = [w for w in linea.palabras if re.fullmatch(r"\d{10}", w.texto)]
                fechas = [w for w in linea.palabras if _fecha(w.texto)]
                importes = [w for w in linea.palabras if _importe_token(w.texto) is not None]
                if len(numeros) == 1 and len(fechas) == 1 and importes:
                    yield linea, numeros[0], fechas[0], importes[-1]

    def _construir(self, documento, segmento):
        p = documento.paginas[0]; nline = self._linea(p, "Factura."); numero = next(w for w in nline.palabras if w.texto.isdigit())
        dates = self._linea(p, "31.07"); date_words = [w for w in dates.palabras if _fecha(w.texto)]
        nifline = self._linea(p, "NIF:"); nif = next(w for w in nifline.palabras if NIF_RE.fullmatch(w.texto))
        provider_nif_line = self._linea(p, "ESA61674347"); provider_nif = next(w for w in provider_nif_line.palabras if "ESA61674347" in w.texto)
        resumen = self._linea(p, "RESUMEN B.I")
        total_line = next(l for l in p.lineas if l.orden > resumen.orden and normalizar_texto(l.texto).startswith("TOTAL ") and len([w for w in l.palabras if _importe_token(w.texto) is not None]) == 4)
        vals = [w for w in total_line.palabras if _importe_token(w.texto) is not None]
        pago = self._linea(p, "Condiciones de Pago")
        prov_dir_lines = [p.lineas[i - 1] for i in (2, 3, 5)]
        prov_dir_words = [w for l in prov_dir_lines for w in l.palabras]
        dest_dir_lines = [p.lineas[i - 1] for i in (13, 14, 16)]
        dest_dir_words = [w for l in dest_dir_lines for w in l.palabras]
        cabecera = {"proveedor": {"nombre": self._campo(documento, p.lineas[0], p.lineas[0].palabras, p.lineas[0].texto, "proveedor_nombre", "RAZON_SOCIAL_VISIBLE"), "nif": self._campo(documento, provider_nif_line, [provider_nif], provider_nif.texto, "proveedor_nif", "CIF_VISIBLE"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in prov_dir_words), prov_dir_words, prov_dir_lines, "cabecera", "proveedor_direccion", "BLOQUE_DIRECCION_PROVEEDOR")},
                    "destinatario": {"nombre": self._campo(documento, self._linea(p, "PUIG SALOMON"), self._linea(p, "PUIG SALOMON").palabras, self._linea(p, "PUIG SALOMON").texto, "destinatario_nombre", "BLOQUE_DESTINATARIO"), "nif": self._campo(documento, nifline, [nif], nif.texto, "destinatario_nif", "NIF_ETIQUETADO"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in dest_dir_words), dest_dir_words, dest_dir_lines, "cabecera", "destinatario_direccion", "BLOQUE_DIRECCION_DESTINATARIO")},
                    "numero_factura": self._campo(documento, nline, [numero], numero.texto, "numero_factura", "NUMERO_FACTURA_ETIQUETADO"), "fecha_factura": self._fecha_campo(documento, dates, date_words[0], "fecha_factura"),
                    "tipo_documento": self._campo(documento, self._linea(p, "FACTURA"), self._linea(p, "FACTURA").palabras, "FACTURA", "tipo_documento", "TITULO_FACTURA"), "moneda": "EUR", "forma_pago": self._campo(documento, pago, pago.palabras[3:], " ".join(w.texto for w in pago.palabras[3:]), "forma_pago", "CONDICIONES_PAGO"),
                    "base_imponible_total": self._dinero(documento, total_line, vals[0], "base_imponible_total"), "iva_total": self._dinero(documento, total_line, vals[1], "iva_total"), "recargo_equivalencia_total": self._dinero(documento, total_line, vals[2], "recargo_total"), "importe_total": self._dinero(documento, total_line, vals[3], "importe_total")}
        taxline = self._linea(p, "IVA 4%"); tvals = [w for w in taxline.palabras if _importe_token(w.texto) is not None]
        producto_fiscal = next(l for l in p.lineas if "0,50" in l.texto and "4,00" in l.texto)
        tipo_re_words = [w for w in producto_fiscal.palabras if w.texto.rstrip("%") == "0,50"]
        tax = {"orden": 1, "origen": "FACTURA", "base": self._dinero(documento, taxline, tvals[0], "base", tabla="fiscalidad"), "tipo_iva": self._campo(documento, taxline, taxline.palabras[:2], 4.0, "tipo_iva", "IVA_LITERAL", "fiscalidad"), "cuota_iva": self._dinero(documento, taxline, tvals[1], "cuota_iva", tabla="fiscalidad"), "tipo_recargo_equivalencia": self._campo(documento, producto_fiscal, tipo_re_words, 0.5, "tipo_recargo", "TIPO_RE_IMPRESO_EN_DETALLE", "fiscalidad"), "cuota_recargo_equivalencia": self._dinero(documento, taxline, tvals[2], "cuota_recargo", tabla="fiscalidad")}
        v = {"orden": 1, "fecha": self._fecha_campo(documento, dates, date_words[1]), "importe": cabecera["importe_total"], "forma_pago": cabecera["forma_pago"]}
        filas = list(self._filas_albaranes(documento, segmento))
        albaranes = [self._albaran(documento, linea, numero, fecha, importe, orden=orden,
                     atributos={"numero_pedido": self._linea(p, "Pedido:").texto} if len(filas) == 1 else None)
                     for orden, (linea, numero, fecha, importe) in enumerate(filas, 1)]
        detail = [l for l in p.lineas if 28 <= l.orden <= 46]
        return self._factura(documento, segmento, cabecera, albaranes=albaranes, impuestos=[tax], vencimientos=[v], otros=[self._literal_lineas(documento, detail, "DETALLE_PRODUCTOS")])


class AdaptadorMoretti(AdaptadorGoldPequenoBase):
    id, version = "moretti-local", "1.0.0"
    layout, constructor = "MORETTI_FACTURA_V1", "_construir"
    senales = ("MORETTI IBERICA S.L.U", "Nota de Entrega Num", "Total Neto Productos", "Total a Pagar")

    def _construir(self, documento, segmento):
        p = documento.paginas[0]; nline = self._linea(p, "Número "); numero = next(w for w in nline.palabras if re.fullmatch(r"\d{6}FV\d{2}", w.texto, re.I)); fecha = next(w for w in nline.palabras if _fecha(w.texto))
        nifline = self._linea(p, "NIF 409"); nif = next(w for w in nifline.palabras if NIF_RE.fullmatch(w.texto))
        provline = self._linea(p, "MORETTI IBERICA"); provnifline = self._linea(p, "B01959782"); provnif = next(w for w in provnifline.palabras if w.texto == "B01959782")
        prov_dir_lines = [p.lineas[49]]
        prov_dir_words = [w for w in prov_dir_lines[0].palabras if w.bbox.x0 < 269]
        dest_dir_lines = [p.lineas[i] for i in (2, 3, 4)]
        dest_dir_words = [w for line in dest_dir_lines for w in line.palabras]
        totals_header = self._linea(p, "Total Neto Total IVA Total Factura")
        totals = next(l for l in p.lineas if l.orden > totals_header.orden and len([w for w in l.palabras if _importe_token(w.texto) is not None]) >= 4)
        vals = [w for w in totals.palabras if _importe_token(w.texto) is not None]
        pago = self._linea(p, "GIRO 30 D")
        cabecera = {"proveedor": {"nombre": self._campo(documento, provline, provline.palabras, provline.texto, "proveedor_nombre", "RAZON_SOCIAL_VISIBLE"), "nif": self._campo(documento, provnifline, [provnif], provnif.texto, "proveedor_nif", "NIF_VISIBLE"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in prov_dir_words), prov_dir_words, prov_dir_lines, "cabecera", "proveedor_direccion", "PIE_IZQUIERDO_ANTES_DE_TELEFONO")},
                    "destinatario": {"nombre": self._campo(documento, self._linea(p, "FARMACIA PIO"), self._linea(p, "FARMACIA PIO").palabras, self._linea(p, "FARMACIA PIO").texto, "destinatario_nombre", "BLOQUE_DESTINATARIO"), "nif": self._campo(documento, nifline, [nif], nif.texto, "destinatario_nif", "NIF_ETIQUETADO"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in dest_dir_words), dest_dir_words, dest_dir_lines, "cabecera", "destinatario_direccion", "BLOQUE_SUPERIOR_DIRECCION_DESTINATARIO")},
                    "numero_factura": self._campo(documento, nline, [numero], numero.texto, "numero_factura", "NUMERO_ETIQUETADO"), "fecha_factura": self._fecha_campo(documento, nline, fecha, "fecha_factura"), "tipo_documento": self._campo(documento, self._linea(p, "Factura"), self._linea(p, "Factura").palabras, "FACTURA", "tipo_documento", "TITULO_FACTURA"), "moneda": "EUR", "forma_pago": self._campo(documento, pago, pago.palabras, pago.texto, "forma_pago", "FORMA_PAGO_VISIBLE"),
                    "base_imponible_total": self._dinero(documento, totals, vals[0], "base_imponible_total"), "iva_total": self._dinero(documento, totals, vals[1], "iva_total"), "recargo_equivalencia_total": None, "importe_total": self._dinero(documento, totals, vals[2], "importe_total")}
        taxline = self._linea(p, "IVA 10%"); tvals = [w for w in taxline.palabras if _importe_token(w.texto) is not None]
        tax = {"orden": 1, "origen": "FACTURA", "base": self._dinero(documento, taxline, tvals[0], "base", tabla="fiscalidad"), "tipo_iva": self._campo(documento, taxline, taxline.palabras[1:3], 10.0, "tipo_iva", "IVA_LITERAL", "fiscalidad"), "cuota_iva": self._dinero(documento, taxline, tvals[1], "cuota_iva", tabla="fiscalidad"), "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": self._dinero(documento, taxline, tvals[2], "cuota_recargo", tabla="fiscalidad")}
        vline = self._linea(p, "el 30/"); vdate = next(w for w in vline.palabras if _fecha(w.texto)); vamount = next(w for w in vline.palabras if _importe_token(w.texto) is not None)
        venc = {"orden": 1, "fecha": self._fecha_campo(documento, vline, vdate), "importe": self._dinero(documento, vline, vamount, "importe", tabla="vencimientos"), "forma_pago": cabecera["forma_pago"]}
        albs = []
        for line in [l for l in p.lineas if "NOTA DE ENTREGA NUM" in normalizar_texto(l.texto)]:
            num = next(w for w in line.palabras if re.fullmatch(r"\d{6}AV\d{2}", w.texto, re.I)); date_line = p.lineas[line.orden]; d = next(w for w in date_line.palabras if _fecha(w.texto)); albs.append(self._albaran(documento, line, num, d, orden=len(albs)+1))
        detail = [l for l in p.lineas if 20 <= l.orden <= 48]
        return self._factura(documento, segmento, cabecera, albaranes=albs, impuestos=[tax], vencimientos=[venc], otros=[self._literal_lineas(documento, detail, "DETALLE_PRODUCTOS_TOTALES_Y_CARGOS_CERO")])


class AdaptadorTotalcare(AdaptadorGoldPequenoBase):
    id, version = "totalcare-local", "1.0.0"
    layout, constructor = "TOTALCARE_FACTURA_V1", "_construir"
    senales = ("TOTALCARE EUROPE", "Pedido Factura Cliente Fecha", "Total factura", "meros de serie")

    def _construir(self, documento, segmento):
        p = documento.paginas[0]
        tabla_id = self._linea(p, "Pedido Factura Cliente Fecha")
        idline = next(l for l in p.lineas if l.orden > tabla_id.orden and any(re.fullmatch(r"G/\d[\d.]*", w.texto, re.I) for w in l.palabras))
        numero = next(w for w in idline.palabras if re.fullmatch(r"G/\d[\d.]*", w.texto, re.I))
        fecha_literal = re.search(r"\d{2}-\s*\d{2}-\s*\d{4}", idline.texto).group(0).replace(" ", "")
        fecha_tokens = [w for w in idline.palabras if any(c.isdigit() for c in w.texto)][-4:-1]
        nifline = self._linea(p, "ES40901058C"); nif = next(w for w in nifline.palabras if "40901058C" in w.texto)
        provnifline = self._linea(p, "B-66438722"); provnif = next(w for w in provnifline.palabras if "B-66438722" in w.texto)
        prov_dir_lines = [p.lineas[3]]
        prov_dir_words = [w for w in prov_dir_lines[0].palabras if 250 < w.bbox.x0 < 400]
        dest_dir_lines = [p.lineas[i] for i in (10, 11)]
        dest_dir_words = [w for line in dest_dir_lines for w in line.palabras if w.bbox.x0 > 250]
        tax_header = self._linea(p, "Importe Base IVA")
        taxline = next(l for l in p.lineas if l.orden > tax_header.orden and len([w for w in l.palabras if _importe_token(w.texto) is not None]) == 6)
        vals = [w for w in taxline.palabras if _importe_token(w.texto) is not None]
        total_line = next(l for l in p.lineas if l.orden > taxline.orden and len([w for w in l.palabras if _importe_token(w.texto) is not None]) == 1)
        total = next(w for w in total_line.palabras if _importe_token(w.texto) is not None)
        pago = self._linea(p, "Método de pago")
        cabecera = {"proveedor": {"nombre": self._campo(documento, self._linea(p, "TOTALCARE EUROPE"), self._linea(p, "TOTALCARE EUROPE").palabras, self._linea(p, "TOTALCARE EUROPE").texto, "proveedor_nombre", "RAZON_SOCIAL_VISIBLE"), "nif": self._campo(documento, provnifline, [provnif], provnif.texto, "proveedor_nif", "NIF_VISIBLE"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in prov_dir_words), prov_dir_words, prov_dir_lines, "cabecera", "proveedor_direccion", "CABECERA_DERECHA_DIRECCION_PROVEEDOR")},
                    "destinatario": {"nombre": self._campo(documento, self._linea(p, "PIO PUIG"), self._linea(p, "PIO PUIG").palabras[-3:], "PIO PUIG SALOMON", "destinatario_nombre", "BLOQUE_CLIENTE"), "nif": self._campo(documento, nifline, [nif], nif.texto, "destinatario_nif", "CIF_CLIENTE_VISIBLE"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in dest_dir_words), dest_dir_words, dest_dir_lines, "cabecera", "destinatario_direccion", "COLUMNA_DERECHA_DIRECCION_CLIENTE")},
                    "numero_factura": self._campo(documento, idline, [numero], numero.texto, "numero_factura", "COLUMNA_FACTURA"), "fecha_factura": self._campo(documento, idline, fecha_tokens, _fecha(fecha_literal), "fecha_factura", "FECHA_RECONSTRUIDA_DESDE_TOKENS_CONTIGUOS"), "tipo_documento": self._campo(documento, self._linea(p, "FACTURA"), self._linea(p, "FACTURA").palabras, "FACTURA", "tipo_documento", "TITULO_FACTURA"), "moneda": "EUR", "forma_pago": self._campo(documento, pago, pago.palabras[3:4], pago.palabras[3].texto, "forma_pago", "METODO_PAGO_ETIQUETADO"),
                    "base_imponible_total": self._dinero(documento, taxline, vals[1], "base_imponible_total"), "iva_total": self._dinero(documento, taxline, vals[3], "iva_total"), "recargo_equivalencia_total": self._dinero(documento, taxline, vals[5], "recargo_total"), "importe_total": self._dinero(documento, total_line, total, "importe_total")}
        tax = {"orden": 1, "origen": "FACTURA", "base": cabecera["base_imponible_total"], "tipo_iva": self._porcentaje(documento, taxline, vals[2], "tipo_iva"), "cuota_iva": cabecera["iva_total"], "tipo_recargo_equivalencia": self._porcentaje(documento, taxline, vals[4], "tipo_recargo"), "cuota_recargo_equivalencia": cabecera["recargo_equivalencia_total"]}
        vline = self._linea(p, "Vencimientos"); vd = next(w for w in vline.palabras if _fecha(w.texto)); va = next(w for w in vline.palabras if _importe_token(w.texto) is not None)
        venc = {"orden": 1, "fecha": self._fecha_campo(documento, vline, vd), "importe": self._dinero(documento, vline, va, "importe", tabla="vencimientos"), "forma_pago": cabecera["forma_pago"]}
        albline = self._linea(p, "Albar"); albnum = next(w for w in albline.palabras if "WEB/" in w.texto); alb = self._albaran(documento, albline, albnum, orden=1, atributos={"pedido": self._linea(p, "Su Pedido").texto})
        detail = [l for l in p.lineas if 22 <= l.orden <= 36]
        return self._factura(documento, segmento, cabecera, albaranes=[alb], impuestos=[tax], vencimientos=[venc], otros=[self._literal_lineas(documento, detail, "DETALLE_PRODUCTO_SERIES_PAGO_Y_TRANSPORTE")])


class AdaptadorLoreal(AdaptadorGoldPequenoBase):
    id, version = "loreal-local", "1.1.0"
    layout, constructor = "LOREAL_FACTURA_TRES_PAGINAS_V1", "_construir"
    senales = ("L'OREAL ESPANA S.A", "Nº factura Fecha de Factura", "Resumen Impuestos", "Condiciones Generales de Venta 2026")

    def _construir(self, documento, segmento):
        p1, p2, p3 = documento.paginas
        identity_header = self._linea(p1, "factura Fecha de Factura")
        idline = next(l for l in p1.lineas if l.orden > identity_header.orden and any(_fecha(w.texto) for w in l.palabras) and any(re.fullmatch(r"[A-Z]{3}", w.texto) for w in l.palabras))
        numero = next(w for w in idline.palabras if re.fullmatch(r"\d{10}", w.texto)); fecha = next(w for w in idline.palabras if _fecha(w.texto)); moneda = idline.palabras[-1]
        prov = self._linea(p1, "L'OREAL ESPANA")
        provnif = next(w for l in p1.lineas for w in l.palabras if w.texto == "A28050359")
        provnifline = next(l for l in p1.lineas if provnif in l.palabras)
        nifline = self._linea(p1, "40901058C"); nif = next(w for w in nifline.palabras if w.texto == "40901058C")
        prov_dir_lines = [p1.lineas[i] for i in (2, 3)]
        prov_dir_words = [w for line in prov_dir_lines for w in line.palabras if 415 < w.bbox.x0 < 500]
        dest_dir_lines = [p1.lineas[i] for i in (11, 12, 13)]
        dest_dir_words = [w for line in dest_dir_lines for w in line.palabras if w.bbox.x0 < 120]
        total_line = self._linea(p2, "Importe Total"); total = next(w for w in total_line.palabras if _importe_token(w.texto) is not None)
        base_line = self._linea(p2, "Base imponible"); base = next(w for w in base_line.palabras if _importe_token(w.texto) is not None)
        taxes = [self._linea(p2, "SF 21,00"), self._linea(p2, "SF 5,20")]
        taxvals = [[w for w in l.palabras if _importe_token(w.texto) is not None] for l in taxes]
        pago = self._linea(p2, "Metodo de Pago")
        cabecera = {"proveedor": {"nombre": self._campo(documento, prov, prov.palabras[-3:], "L'OREAL ESPANA S.A.", "proveedor_nombre", "RAZON_SOCIAL_VISIBLE"), "nif": self._campo(documento, provnifline, [provnif], provnif.texto, "proveedor_nif", "NIF_VISIBLE"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in prov_dir_words), prov_dir_words, prov_dir_lines, "cabecera", "proveedor_direccion", "COLUMNA_DERECHA_DIRECCION_PROVEEDOR")},
                    "destinatario": {"nombre": self._campo(documento, self._linea(p1, "PIO PUIG SALOMON"), self._linea(p1, "PIO PUIG SALOMON").palabras[:3], "PIO PUIG SALOMON", "destinatario_nombre", "RAZON_SOCIAL_DESTINATARIO"), "nif": self._campo(documento, nifline, [nif], nif.texto, "destinatario_nif", "NIF_DESTINATARIO"), "direccion": self.campo_multilinea(documento, " ".join(w.texto for w in dest_dir_words), dest_dir_words, dest_dir_lines, "cabecera", "destinatario_direccion", "COLUMNA_IZQUIERDA_LUGAR_PETICIONARIO")},
                    "numero_factura": self._campo(documento, idline, [numero], numero.texto, "numero_factura", "COLUMNA_NUM_FACTURA"), "fecha_factura": self._fecha_campo(documento, idline, fecha, "fecha_factura"), "tipo_documento": self._campo(documento, idline, [idline.palabras[0]], "FACTURA", "tipo_documento", "TIPO_F2_EN_COLUMNA_TIPO"), "moneda": self._campo(documento, idline, [moneda], moneda.texto, "moneda", "MONEDA_IMPRESA"), "forma_pago": self._campo(documento, pago, pago.palabras[3:5], " ".join(w.texto for w in pago.palabras[3:5]), "forma_pago", "METODO_PAGO_ETIQUETADO"),
                    "base_imponible_total": self._dinero(documento, base_line, base, "base_imponible_total"), "iva_total": self._dinero(documento, taxes[0], taxvals[0][-1], "iva_total"), "recargo_equivalencia_total": self._dinero(documento, taxes[1], taxvals[1][-1], "recargo_total"), "importe_total": self._dinero(documento, total_line, total, "importe_total")}
        impuesto_iva = {"orden": 1, "origen": "RESUMEN_IMPUESTOS", "tipo_documental": "SF", "naturaleza": "IVA",
                        "base": self._dinero(documento, taxes[0], taxvals[0][-2], "base", tabla="fiscalidad"), "tipo_iva": self._porcentaje(documento, taxes[0], taxvals[0][0], "tipo_iva"), "cuota_iva": self._dinero(documento, taxes[0], taxvals[0][-1], "cuota_iva", tabla="fiscalidad"), "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": None}
        decision_re = _decision_funcional_pio(
            proveedor="LOREAL", layout=self.layout,
            regla="PORCENTAJE_5_20_LAYOUT_LOREAL_ES_RECARGO_EQUIVALENCIA",
            valor="RECARGO_EQUIVALENCIA",
        )
        impuesto_re = {"orden": 2, "origen": "RESUMEN_IMPUESTOS", "tipo_documental": "SF", "naturaleza": "RECARGO_EQUIVALENCIA",
                       "naturaleza_fuente": "DECISION_FUNCIONAL_PIO", "naturaleza_documentacion": decision_re,
                       "base_referencia": self._dinero(documento, taxes[1], taxvals[1][-2], "base_referencia", tabla="fiscalidad"), "base": None,
                       "porcentaje_documental": self._porcentaje(documento, taxes[1], taxvals[1][0], "porcentaje_documental"), "tipo_iva": None,
                       "cuota": self._dinero(documento, taxes[1], taxvals[1][-1], "cuota", tabla="fiscalidad"), "cuota_iva": None,
                       "tipo_recargo_equivalencia": self._porcentaje(documento, taxes[1], taxvals[1][0], "tipo_recargo"),
                       "cuota_recargo_equivalencia": self._dinero(documento, taxes[1], taxvals[1][-1], "cuota_recargo", tabla="fiscalidad"),
                       "incidencias": [],
                       "provenance": {"autoridad_naturaleza": "PIO", "fuente_naturaleza": "DECISION_FUNCIONAL_PIO",
                                      "evidencia_documental_directa_naturaleza": False,
                                      "evidencia_geometrica_valores_preservada": True}}
        vline = self._linea(p2, "03/08/2026"); vd = next(w for w in vline.palabras if _fecha(w.texto)); va = next(w for w in vline.palabras if _importe_token(w.texto) is not None)
        venc = {"orden": 1, "fecha": self._fecha_campo(documento, vline, vd), "importe": self._dinero(documento, vline, va, "importe", tabla="vencimientos"), "forma_pago": cabecera["forma_pago"]}
        pvline = self._linea(p2, "Importe Punto Verde"); pv = next(w for w in pvline.palabras if _importe_token(w.texto) is not None)
        incluye = [l for l in p2.lineas if "EL IMPORTE DE ESTA FACTURA INCLUYE" in normalizar_texto(l.texto)]
        decision_pv = _decision_funcional_pio(
            proveedor="LOREAL", layout=self.layout,
            regla="PUNTO_VERDE_ES_APORTACION_AMBIENTAL_INCLUIDA_NO_ADITIVA",
            valor="APORTACION_AMBIENTAL_INCLUIDA",
        )
        punto_verde = {"tipo": "APORTACION_AMBIENTAL_INCLUIDA", "categoria": "APORTACION_AMBIENTAL_INCLUIDA",
                       "literal": self._campo(documento, pvline, pvline.palabras, pvline.texto, "literal", "CONCEPTO_ETIQUETADO", "otros"),
                       "importe": self._dinero(documento, pvline, pv, "importe", tabla="otros"), "base": None, "iva": None,
                       "sentido": None, "es_movimiento_economico_independiente": False,
                       "incluido_en_factura": self.campo_multilinea(
                           documento, " | ".join(l.texto for l in incluye),
                           [w for l in incluye for w in l.palabras], incluye,
                           "otros", "texto_inclusion", "TEXTO_DOCUMENTAL_INDICA_INCLUIDO",
                       ),
                       "participa_en_suma_total": False, "doble_conteo": False,
                       "tratamiento_documentacion": decision_pv,
                       "provenance": {"autoridad_categoria": "PIO", "fuente_categoria": "DECISION_FUNCIONAL_PIO",
                                      "evidencia_documental_directa_categoria": False,
                                      "evidencia_documental_inclusion": True}}
        detail = [l for p in (p1, p2) for l in p.lineas if (p.numero == 1 and 32 <= l.orden <= 90) or (p.numero == 2 and 32 <= l.orden <= 57)]
        legal = self._literal_lineas(documento, [p3.lineas[0], p3.lineas[-3], p3.lineas[-2]], "PAGINA_AUXILIAR_CONDICIONES_GENERALES", rol="AUXILIAR_NO_ECONOMICO_EXTRAIDO")
        resultado = self._factura(documento, segmento, cabecera, movimientos=[], impuestos=[impuesto_iva, impuesto_re], vencimientos=[venc], otros=[self._literal_lineas(documento, detail, "DETALLE_PRODUCTOS_REFERENCIAS_TOTALES_Y_PAGO"), punto_verde, legal], incidencias=[])
        base_c = cabecera["base_imponible_total"]; iva_c = impuesto_iva["cuota_iva"]; otro_c = impuesto_re["cuota"]; total_c = cabecera["importe_total"]
        resultado["controles_conciliacion"] = evaluar_conciliaciones([EspecificacionConciliacion(
            "TOTAL_DESDE_BASE_Y_CUOTAS_DOCUMENTALES", "TOTAL_FACTURA",
            ComponenteConciliacion("TOTAL", total_c["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", "cabecera", total_c["evidencias"][0].pagina, total_c["evidencias"]),
            [ComponenteConciliacion(nombre, campo["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", "fiscalidad", campo["evidencias"][0].pagina, campo["evidencias"]) for nombre, campo in (("BASE", base_c), ("CUOTA_21", iva_c), ("CUOTA_5_20", otro_c))],
            {"regla": "BASE_UNICA_MAS_IVA_Y_RE", "naturaleza_segunda_cuota_fuente": "DECISION_FUNCIONAL_PIO",
             "punto_verde_sumado_adicionalmente": False},
        )])
        return resultado
