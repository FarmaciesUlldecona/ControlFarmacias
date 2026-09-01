from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from ..conciliacion import ComponenteConciliacion, EspecificacionConciliacion, evaluar_conciliacion
from ..geometria.lineas import normalizar_texto
from ..modelos import AlbaranLocal, DocumentoLocal, LineaLocal, PalabraLocal
from .gold_pequenos import (
    AdaptadorGoldPequenoBase,
    NIF_RE,
    _decision_funcional_pio,
    _fecha,
    _importe_token,
)


def documentar_sentido_decision_funcional_pio_gas_casa(descripcion_literal: str) -> dict[str, Any] | None:
    """Decisiones de sentido de Pio limitadas al layout histórico de Gas Casa."""
    decisiones = {
        "TERMINO FIJO GAS": ("CARGO", "TERMINO_FIJO_GAS_CARGO_DECISION_PIO"),
        "TERMINO ENERGIA GAS": ("CARGO", "TERMINO_ENERGIA_GAS_CARGO_DECISION_PIO"),
        "DESCUENTO PROMOCIONAL": ("ABONO", "DESCUENTO_PROMOCIONAL_ABONO_DECISION_PIO"),
        "ALQUILER DE EQUIPOS GAS": ("CARGO", "ALQUILER_EQUIPOS_GAS_CARGO_DECISION_PIO"),
        "IMPTO.HC GENERAL (#)": ("CARGO", "IMPUESTO_HIDROCARBUROS_CARGO_DECISION_PIO"),
    }
    decision = decisiones.get(normalizar_texto(descripcion_literal))
    if decision is None:
        return None
    sentido, regla = decision
    return _decision_funcional_pio(
        proveedor="GAS_CASA",
        layout="ENDESA_GAS_FACTURA_CONSUMO_V1",
        regla=regla,
        valor=sentido,
    )


def documentar_sentido_decision_funcional_pio_pierre_fabre(descripcion_literal: str) -> dict[str, Any] | None:
    """Decisión de sentido de Pio limitada al descuento del layout Pierre Fabre."""
    if normalizar_texto(descripcion_literal) != "DESCUENTO COMERC.":
        return None
    return _decision_funcional_pio(
        proveedor="PIERRE_FABRE",
        layout="PIERRE_FABRE_ABONO_COMERCIAL_V1",
        regla="DESCUENTO_COMERCIAL_ABONO_DECISION_PIO",
        valor="ABONO",
    )


def _fecha_larga(texto: str) -> str | None:
    meses = {
        "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
        "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
        "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
    }
    match = re.search(r"(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+(\d{4})", normalizar_texto(texto))
    if not match or match.group(2) not in meses:
        return None
    return datetime(int(match.group(3)), meses[match.group(2)], int(match.group(1))).date().isoformat()


class AdaptadorHistoricoGold1Base(AdaptadorGoldPequenoBase):
    capacidades = {
        **AdaptadorGoldPequenoBase.capacidades,
        "ocr": "NO_NECESARIO_TEXTO_NATIVO",
        "autoridad": "SHADOW_SIN_AUTORIDAD_PRODUCTIVA",
    }

    @staticmethod
    def _buscar(documento: DocumentoLocal, fragmento: str) -> LineaLocal:
        objetivo = normalizar_texto(fragmento)
        return next(
            linea for pagina in documento.paginas for linea in pagina.lineas
            if objetivo in normalizar_texto(linea.texto)
        )

    @staticmethod
    def _palabra(linea: LineaLocal, patron: str) -> PalabraLocal:
        regex = re.compile(patron, re.I)
        return next(palabra for palabra in linea.palabras if regex.fullmatch(palabra.texto.strip("()[],:")))

    def _dinero_signado(self, documento, pagina, linea, palabra, columna, *, tabla="economico"):
        valor = _importe_token(palabra.texto)
        if valor is None:
            raise ValueError(f"Importe no interpretable: {palabra.texto!r}")
        signo = next((
            candidata for candidata in pagina.palabras
            if candidata.texto == "-"
            and palabra.bbox.x0 - 10 <= candidata.bbox.x0 <= palabra.bbox.x0
            and abs(candidata.bbox.y0 - palabra.bbox.y0) <= 5
        ), None)
        palabras = [signo, palabra] if signo else [palabra]
        valor = -abs(valor) if signo or palabra.texto.startswith("-") else valor
        return self._campo(documento, linea, palabras, valor, columna, "SIGNO_Y_VALOR_IMPRESOS", tabla)

    @staticmethod
    def _derivado(valor, campos, regla):
        return {
            "valor": valor,
            "literal": " | ".join(str(campo.get("literal", "")) for campo in campos),
            "evidencias": [evidencia for campo in campos for evidencia in campo.get("evidencias", [])],
            "provenance": {
                "regla": regla,
                "evidencia_documental_directa": False,
                "gold_usado": False,
            },
        }

    def _control_base_movimientos(self, factura):
        base = factura["cabecera"].get("base_imponible_total")
        movimientos = [item for item in factura["movimientos"] if item.get("participa_en_conciliacion_base")]
        if not base or not movimientos or any(item.get("base") is None for item in movimientos):
            return
        componentes = [
            ComponenteConciliacion(
                f"MOVIMIENTO_{item['orden']}", item["base"]["valor"], "SIGNO_DOCUMENTAL_CONSERVADO",
                "movimientos", item["base"]["evidencias"][0].pagina, item["base"]["evidencias"],
            )
            for item in movimientos
        ]
        factura["controles_conciliacion"].append(evaluar_conciliacion(EspecificacionConciliacion(
            "BASE_DESDE_MOVIMIENTOS", "BASE_IMPONIBLE",
            ComponenteConciliacion(
                "BASE", base["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", "cabecera",
                base["evidencias"][0].pagina, base["evidencias"],
            ),
            componentes,
            {"regla": "SUMA_COMPONENTES_DETALLE_IMPRESOS", "gold_usado": False},
        )))

    def _control_base_detalle(self, factura, detalles, campo="importe"):
        base = factura["cabecera"].get("base_imponible_total")
        importes = [detalle.get(campo) for detalle in detalles]
        if not base or not importes or any(importe is None for importe in importes):
            return
        factura["controles_conciliacion"].append(evaluar_conciliacion(EspecificacionConciliacion(
            "BASE_DESDE_DETALLE", "BASE_IMPONIBLE",
            ComponenteConciliacion(
                "BASE", base["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", "cabecera",
                base["evidencias"][0].pagina, base["evidencias"],
            ),
            [
                ComponenteConciliacion(
                    f"DETALLE_{i}", importe["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", "detalle",
                    importe["evidencias"][0].pagina, importe["evidencias"],
                )
                for i, importe in enumerate(importes, 1)
            ],
            {"regla": "SUMA_IMPORTES_DETALLE_IMPRESOS", "gold_usado": False},
        )))


class AdaptadorDermofarmHistorico(AdaptadorHistoricoGold1Base):
    id, version = "dermofarm-historico-local", "1.0.0"
    layout, constructor = "DERMOFARM_ABONO_PRODUCTOS_V1", "_construir"
    senales = ("DERMOFARM, S.A.U.", "ABONO ORIGINAL", "RGO.E", "Albaranes:")

    def _construir(self, documento, segmento):
        pagina = documento.paginas[0]
        tipo_line = self._linea(pagina, "ABONO ORIGINAL")
        numero_line = next(
            linea for linea in pagina.lineas
            if "NO:" in normalizar_texto(linea.texto)
            and any(re.fullmatch(r"\d{8,12}", p.texto) for p in linea.palabras)
        )
        numero = next(p for p in numero_line.palabras if re.fullmatch(r"\d{8,12}", p.texto))
        fecha_line = next(linea for linea in pagina.lineas if any(_fecha(p.texto) for p in linea.palabras) and "HOJA" in normalizar_texto(linea.texto))
        fecha = next(p for p in fecha_line.palabras if _fecha(p.texto))
        cliente_line = self._linea(pagina, "Cliente:")
        codigo_cliente = next(p for p in cliente_line.palabras if re.fullmatch(r"\d{6,}", p.texto))
        proveedor_line = self._linea(pagina, "DERMOFARM, S.A.U.")
        proveedor_nif = next(p for p in proveedor_line.palabras if NIF_RE.fullmatch(p.texto))
        proveedor_dir = [linea for linea in pagina.lineas if 730 < linea.bbox.y0 < 750 and linea.bbox.x0 < 250]
        destinatario = next(linea for linea in pagina.lineas if normalizar_texto(linea.texto) == "PUIG SALOMON, PIO")
        destinatario_nif_line = self._linea(pagina, "CIF/NIF:")
        destinatario_nif = next(p for p in destinatario_nif_line.palabras if NIF_RE.fullmatch(p.texto))
        destinatario_dir = [linea for linea in pagina.lineas if 105 < linea.bbox.y0 < 140 and linea.bbox.x0 > 280]
        base_line = self._linea(pagina, "Importe total:")
        base_word = next(p for p in base_line.palabras if _importe_token(p.texto) is not None)
        iva_line = next(linea for linea in pagina.lineas if normalizar_texto(linea.texto).startswith("I.V.A."))
        re_line = next(linea for linea in pagina.lineas if normalizar_texto(linea.texto).startswith("RGO.E"))
        total_line = self._linea(pagina, "Total impuestos incluidos")
        total_word = [p for p in total_line.palabras if _importe_token(p.texto) is not None][-1]
        iva_vals = [p for p in iva_line.palabras if _importe_token(p.texto) is not None]
        re_vals = [p for p in re_line.palabras if _importe_token(p.texto) is not None]
        iva_tipo = next(p for p in iva_line.palabras if "%" in p.texto)
        re_tipo = next(p for p in re_line.palabras if "%" in p.texto)
        indice_cif = next(i for i, p in enumerate(proveedor_line.palabras) if normalizar_texto(p.texto).startswith("CIF/VAT"))
        nombre_words = proveedor_line.palabras[:indice_cif]
        proveedor_dir_words = [p for linea in proveedor_dir for p in linea.palabras if p.bbox.x0 < 250]
        cabecera = {
            "proveedor": {
                "nombre": self._campo(documento, proveedor_line, nombre_words, " ".join(p.texto for p in nombre_words), "proveedor_nombre", "RAZON_SOCIAL_VISIBLE"),
                "nif": self._campo(documento, proveedor_line, [proveedor_nif], proveedor_nif.texto.replace("ES", ""), "proveedor_nif", "CIF_VISIBLE"),
                "direccion": self.campo_multilinea(documento, " ".join(p.texto for p in proveedor_dir_words), proveedor_dir_words, proveedor_dir, "cabecera", "proveedor_direccion", "BLOQUE_DIRECCION_PROVEEDOR"),
            },
            "destinatario": {
                "nombre": self._campo(documento, destinatario, destinatario.palabras, destinatario.texto, "destinatario_nombre", "BLOQUE_DESTINATARIO"),
                "nif": self._campo(documento, destinatario_nif_line, [destinatario_nif], destinatario_nif.texto, "destinatario_nif", "CIF_NIF_VISIBLE"),
                "direccion": self.campo_multilinea(documento, " ".join(p.texto for l in destinatario_dir for p in l.palabras), [p for l in destinatario_dir for p in l.palabras], destinatario_dir, "cabecera", "destinatario_direccion", "BLOQUE_DIRECCION_DESTINATARIO"),
            },
            "numero_factura": self._campo(documento, numero_line, [numero], numero.texto, "numero_factura", "NUMERO_ETIQUETADO"),
            "fecha_factura": self._fecha_campo(documento, fecha_line, fecha, "fecha_factura"),
            "tipo_documento": self._campo(documento, tipo_line, tipo_line.palabras[:1], "ABONO", "tipo_documento", "TITULO_ABONO_VISIBLE"),
            "naturaleza_principal": "MERCANCIA",
            "codigo_cliente": self._campo(documento, cliente_line, [codigo_cliente], codigo_cliente.texto, "codigo_cliente", "CLIENTE_ETIQUETADO"),
            "moneda": self._campo(documento, self._linea(pagina, "Moneda: Euros"), self._linea(pagina, "Moneda: Euros").palabras[-1:], "EUR", "moneda", "MONEDA_VISIBLE"),
            "forma_pago": None,
            "base_imponible_total": self._dinero(documento, base_line, base_word, "base_imponible_total"),
            "iva_total": self._dinero(documento, iva_line, iva_vals[-1], "iva_total"),
            "recargo_equivalencia_total": self._dinero(documento, re_line, re_vals[-1], "recargo_equivalencia_total"),
            "importe_total": self._dinero(documento, total_line, total_word, "importe_total"),
        }
        impuestos = [{
            "orden": 1, "origen": "RESUMEN_FISCAL", "naturaleza": "IVA_Y_RE",
            "base": self._dinero(documento, iva_line, iva_vals[0], "base", tabla="fiscalidad"),
            "tipo_iva": self._porcentaje(documento, iva_line, iva_tipo, "tipo_iva"),
            "cuota_iva": cabecera["iva_total"],
            "tipo_recargo_equivalencia": self._porcentaje(documento, re_line, re_tipo, "tipo_recargo"),
            "cuota_recargo_equivalencia": cabecera["recargo_equivalencia_total"],
        }]
        detalle = []
        for orden, linea in enumerate((l for l in pagina.lineas if l.palabras and re.fullmatch(r"\d{13}", l.palabras[0].texto)), 1):
            words = linea.palabras
            detalle.append({
                "orden": orden,
                "ean": self._campo(documento, linea, [words[0]], words[0].texto, "ean", "COLUMNA_EAN", "detalle"),
                "codigo_nacional": self._campo(documento, linea, [words[1]], words[1].texto, "codigo_nacional", "COLUMNA_CN", "detalle"),
                "codigo": self._campo(documento, linea, [words[2]], words[2].texto, "codigo", "COLUMNA_CODIGO", "detalle"),
                "descripcion_literal": self._campo(documento, linea, words[3:-5], " ".join(p.texto for p in words[3:-5]), "descripcion", "COLUMNA_DENOMINACION", "detalle"),
                "precio_unitario": self._dinero(documento, linea, words[-5], "precio_unitario", tabla="detalle"),
                "tipo_iva": self._campo(documento, linea, [words[-4]], float(words[-4].texto.replace(",", ".")), "tipo_iva", "COLUMNA_IVA", "detalle"),
                "descuento_porcentaje": self._campo(documento, linea, [words[-3]], float(words[-3].texto.replace(",", ".")), "descuento_porcentaje", "COLUMNA_DTO2", "detalle"),
                "cantidad": self._campo(documento, linea, [words[-2]], int(words[-2].texto), "cantidad", "COLUMNA_CANTIDAD", "detalle"),
                "importe": self._dinero(documento, linea, words[-1], "importe", tabla="detalle"),
                "sentido": "ABONO", "sentido_evidencia": cabecera["tipo_documento"], "incidencias": [],
            })
        albaran_line = self._linea(pagina, "Albaranes:")
        albaran_num = next(p for p in albaran_line.palabras if re.fullmatch(r"\d{8,12}", p.texto))
        albaran_fecha = next(p for p in albaran_line.palabras if _fecha(p.texto.strip("()")))
        ev_num = self._campo(documento, albaran_line, [albaran_num], albaran_num.texto, "numero_albaran", "NUMERO_ALBARAN_ETIQUETADO", "albaranes")["evidencias"][0]
        ev_fecha = self._campo(documento, albaran_line, [albaran_fecha], _fecha(albaran_fecha.texto.strip("()")), "fecha", "FECHA_ALBARAN_VISIBLE", "albaranes")["evidencias"][0]
        albaran = AlbaranLocal(
            albaran_num.texto, _fecha(albaran_fecha.texto.strip("()")), None,
            [cabecera["base_imponible_total"]["valor"]], cabecera["importe_total"]["valor"], "ABONO",
            "ALBARAN_UNICO_EN_ABONO", 1, 1,
            {"numero_albaran": ev_num, "fecha": ev_fecha, "tipo_pedido": None,
             "base": cabecera["base_imponible_total"]["evidencias"][0], "total": cabecera["importe_total"]["evidencias"][0]},
            atributos_documentales={
                "categoria": "MERCANCIA", "relacion": "UNICO_ALBARAN_PREVIO_AL_DETALLE",
                "sentido_evidencia": cabecera["tipo_documento"],
                "base_total_evidencia_documental_directa_en_fila_albaran": False,
                "base_total_regla": "DERIVACION_RELACION_UNICO_ALBARAN_CON_FACTURA",
            },
        )
        factura = self._factura(
            documento, segmento, cabecera, albaranes=[albaran], impuestos=impuestos,
            otros=[{"tipo": "DETALLE_PRODUCTOS", "rol": "MERCANCIA_ABONADA", "lineas": detalle}], incidencias=[],
        )
        self._control_base_detalle(factura, detalle)
        factura["null_legitimos"] = ["forma_pago_y_vencimientos_visiblemente_vacios"]
        return factura


class AdaptadorGasCasaHistorico(AdaptadorHistoricoGold1Base):
    id, version = "gas-casa-historico-local", "1.0.0"
    layout, constructor = "ENDESA_GAS_FACTURA_CONSUMO_V1", "_construir"
    senales = ("Endesa Energía, S.A.U.", "DATOS DE LA FACTURA", "DETALLE DE LA FACTURA", "GAS NATURAL")

    def _construir(self, documento, segmento):
        p1, p2 = documento.paginas
        numero_line = self._linea(p1, "Nº de factura")
        numero = next(p for p in numero_line.palabras if re.fullmatch(r"[A-Z]\d{2}[A-Z]{3}\d{9}", p.texto, re.I))
        fecha_line = self._linea(p1, "Fecha emisión factura")
        fecha = next(p for p in fecha_line.palabras if _fecha(p.texto))
        referencia_line = self._linea(p1, "Referencia:")
        referencia = next(p for p in referencia_line.palabras if re.fullmatch(r"\d{6,}", p.texto))
        periodo_line = self._linea(p1, "Periodo de facturación:")
        periodo_fechas = [p for p in periodo_line.palabras if _fecha(p.texto)]
        proveedor = self._linea(p1, "Endesa Energía, S.A.U.")
        proveedor_nif_line = next(
            linea for linea in p1.lineas
            if normalizar_texto(linea.texto).startswith("CIF ")
            and any(NIF_RE.fullmatch(p.texto.rstrip(".")) for p in linea.palabras)
        )
        proveedor_nif = next(p for p in proveedor_nif_line.palabras if NIF_RE.fullmatch(p.texto.rstrip(".")))
        proveedor_dir = [
            linea for linea in p1.lineas
            if linea.bbox.y0 < 150 and "C/RIBERA" in normalizar_texto(linea.texto)
        ]
        proveedor_dir_words = [
            p for linea in proveedor_dir for p in linea.palabras
            if p.bbox.x0 < 300 and normalizar_texto(p.texto) not in {"PIO", "PUIG", "SALOMON"}
        ]
        destinatario = self._linea(p1, "PIO PUIG SALOMON")
        destinatario_dir = [linea for linea in p1.lineas if 130 < linea.bbox.y0 < 170 and linea.bbox.x0 > 280]
        nif_line = next(
            linea for linea in p2.lineas
            if normalizar_texto(linea.texto).startswith("NIF:")
            and any(NIF_RE.fullmatch(p.texto) for p in linea.palabras)
        )
        nif = next(p for p in nif_line.palabras if NIF_RE.fullmatch(p.texto))
        base_line = next(
            linea for linea in p2.lineas
            if normalizar_texto(linea.texto).startswith("IMPORTE TOTAL ")
            and "FACTURA" not in normalizar_texto(linea.texto)
        )
        base_word = [p for p in base_line.palabras if _importe_token(p.texto) is not None][-1]
        iva_line = self._linea(p2, "IVA normal")
        iva_words = [p for p in iva_line.palabras if _importe_token(p.texto) is not None]
        iva_tipo = next(p for p in iva_line.palabras if re.fullmatch(r"\d+(?:[.,]\d+)?", p.texto))
        total_line = self._linea(p2, "TOTAL IMPORTE FACTURA")
        total_word = [p for p in total_line.palabras if _importe_token(p.texto) is not None][-1]
        pago_line = self._linea(p1, "Domiciliación bancaria")
        pago_words = [p for p in pago_line.palabras if p.bbox.x0 > p1.ancho * 0.55]
        cargo_line = next(linea for linea in p1.lineas if _fecha_larga(linea.texto))
        cabecera = {
            "proveedor": {
                "nombre": self._campo(documento, proveedor, proveedor.palabras, proveedor.texto, "proveedor_nombre", "RAZON_SOCIAL_VISIBLE"),
                "nif": self._campo(documento, proveedor_nif_line, [proveedor_nif], proveedor_nif.texto.rstrip("."), "proveedor_nif", "CIF_VISIBLE"),
                "direccion": self.campo_multilinea(documento, " ".join(p.texto for p in proveedor_dir_words), proveedor_dir_words, proveedor_dir, "cabecera", "proveedor_direccion", "BLOQUE_DIRECCION_PROVEEDOR"),
            },
            "destinatario": {
                "nombre": self._campo(documento, destinatario, [p for p in destinatario.palabras if p.bbox.x0 > p1.ancho * 0.5], "PIO PUIG SALOMON", "destinatario_nombre", "BLOQUE_DESTINATARIO"),
                "nif": self._campo(documento, nif_line, [nif], nif.texto, "destinatario_nif", "NIF_CONTRATO_VISIBLE"),
                "direccion": self.campo_multilinea(documento, " ".join(p.texto for l in destinatario_dir for p in l.palabras), [p for l in destinatario_dir for p in l.palabras], destinatario_dir, "cabecera", "destinatario_direccion", "BLOQUE_DIRECCION_DESTINATARIO"),
            },
            "numero_factura": self._campo(documento, numero_line, [numero], numero.texto, "numero_factura", "NUMERO_FACTURA_ETIQUETADO"),
            "fecha_factura": self._fecha_campo(documento, fecha_line, fecha, "fecha_factura"),
            "tipo_documento": self._campo(documento, self._linea(p1, "DATOS DE LA FACTURA"), self._linea(p1, "DATOS DE LA FACTURA").palabras, "FACTURA", "tipo_documento", "CABECERA_DATOS_FACTURA"),
            "naturaleza_principal": "SUMINISTRO_GAS",
            "referencia": self._campo(documento, referencia_line, [referencia], referencia.texto, "referencia", "REFERENCIA_FACTURA_VISIBLE"),
            "fecha_cargo": self._campo(documento, cargo_line, cargo_line.palabras, _fecha_larga(cargo_line.texto), "fecha_cargo", "FECHA_CARGO_VISIBLE"),
            "periodo_facturacion_inicio": self._fecha_campo(documento, periodo_line, periodo_fechas[0], "periodo_facturacion_inicio"),
            "periodo_facturacion_fin": self._fecha_campo(documento, periodo_line, periodo_fechas[1], "periodo_facturacion_fin"),
            "moneda": "EUR",
            "forma_pago": self._campo(documento, pago_line, pago_words, "Domiciliación bancaria", "forma_pago", "FORMA_PAGO_VISIBLE"),
            "base_imponible_total": self._dinero(documento, base_line, base_word, "base_imponible_total"),
            "iva_total": self._dinero(documento, iva_line, iva_words[-1], "iva_total"),
            "recargo_equivalencia_total": None,
            "importe_total": self._dinero(documento, total_line, total_word, "importe_total"),
        }
        impuestos = [{
            "orden": 1, "origen": "DETALLE_FACTURA", "naturaleza": "IVA",
            "base": cabecera["base_imponible_total"],
            "tipo_iva": self._campo(documento, iva_line, [iva_tipo], float(iva_tipo.texto.replace(",", ".")), "tipo_iva", "TIPO_IVA_VISIBLE", "fiscalidad"),
            "cuota_iva": cabecera["iva_total"],
            "tipo_recargo_equivalencia": None, "cuota_recargo_equivalencia": None,
        }]
        specs = (
            ("Término Fijo Gas", "SUMINISTRO_GAS"),
            ("Término Energía Gas", "SUMINISTRO_GAS"),
            ("Descuento promocional", "DESCUENTO"),
            ("Alquiler de Equipos Gas", "ALQUILER_EQUIPO"),
            ("Impto.HC general", "IMPUESTO_HIDROCARBUROS"),
        )
        movimientos = []
        for orden, (literal, categoria) in enumerate(specs, 1):
            linea = self._linea(p2, literal)
            importe_word = [p for p in linea.palabras if _importe_token(p.texto) is not None][-1]
            descripcion = [p for p in linea.palabras if p.bbox.x0 < p2.ancho * 0.38]
            descripcion_valor = " ".join(p.texto for p in descripcion)
            importe = self._dinero(documento, linea, importe_word, "importe", tabla="movimientos")
            decision_sentido = documentar_sentido_decision_funcional_pio_gas_casa(descripcion_valor)
            if decision_sentido is None:
                raise ValueError(f"Concepto Gas Casa sin decisión funcional acotada: {descripcion_valor!r}")
            movimientos.append({
                "orden": orden,
                "descripcion_literal": self._campo(documento, linea, descripcion, descripcion_valor, "descripcion", "CONCEPTO_DETALLE_VISIBLE", "movimientos"),
                "categoria": categoria, "importe": importe, "base": importe,
                "iva": None, "recargo_equivalencia": None,
                "sentido": decision_sentido["valor"],
                "sentido_fuente": "DECISION_FUNCIONAL_PIO",
                "sentido_documentacion": decision_sentido,
                "es_movimiento_economico_independiente": categoria != "IMPUESTO_HIDROCARBUROS",
                "participa_en_conciliacion_base": True,
                "incluido_en_base": True,
                "incidencias": [],
                "provenance": {
                    "fuente": "PDF_NATIVO_LOCAL", "gold_usado": False, "inferencia_por_signo": False,
                    "autoridad_sentido": "PIO", "fuente_sentido": "DECISION_FUNCIONAL_PIO",
                    "evidencia_documental_directa_sentido": False,
                },
            })
        vencimiento = {
            "orden": 1,
            "fecha": self._campo(documento, cargo_line, cargo_line.palabras, _fecha_larga(cargo_line.texto), "fecha", "FECHA_CARGO_VISIBLE", "vencimientos"),
            "importe": cabecera["importe_total"], "forma_pago": cabecera["forma_pago"],
        }
        resumen_lineas = [linea for linea in p1.lineas if 190 < linea.bbox.y0 < 290]
        contrato_lineas = [linea for linea in p2.lineas if linea.orden <= self._linea(p2, "DETALLE DE LA FACTURA").orden]
        consumos_lineas = [linea for linea in p2.lineas if 380 < linea.bbox.y0 < 510]
        regulados_lineas = [linea for linea in p2.lineas if 285 < linea.bbox.y0 < 360]
        factura = self._factura(
            documento, segmento, cabecera, movimientos=movimientos, impuestos=impuestos,
            vencimientos=[vencimiento], otros=[
                self._literal_lineas(documento, resumen_lineas, "RESUMEN_FACTURA_Y_PAGO"),
                self._literal_lineas(documento, contrato_lineas, "DATOS_CONTRATO"),
                self._literal_lineas(documento, consumos_lineas, "LECTURAS_Y_CONSUMOS"),
                self._literal_lineas(documento, regulados_lineas, "COSTES_REGULADOS_INCLUIDOS"),
            ], incidencias=[],
        )
        self._control_base_movimientos(factura)
        factura["null_legitimos"] = ["recargo_equivalencia_no_aparece", "albaranes_no_aparecen"]
        return factura


class AdaptadorPierreFabreHistorico(AdaptadorHistoricoGold1Base):
    id, version = "pierre-fabre-historico-local", "1.0.0"
    layout, constructor = "PIERRE_FABRE_ABONO_COMERCIAL_V1", "_construir"
    senales = ("Pierre Fabre Ibérica", "** ABONO **", "N°. ALBARAN", "TOTAL FACTURA")

    def _construir(self, documento, segmento):
        pagina = documento.paginas[0]
        tipo_line = self._linea(pagina, "** ABONO **")
        ids_line = next(
            linea for linea in pagina.lineas
            if any(re.fullmatch(r"SCN\d+", p.texto) for p in linea.palabras) and any(_fecha(p.texto) for p in linea.palabras)
        )
        fecha = next(p for p in ids_line.palabras if _fecha(p.texto))
        numeros_scn = [p for p in ids_line.palabras if re.fullmatch(r"SCN\d+", p.texto)]
        numero, albaran_num = numeros_scn[0], numeros_scn[-1]
        pedido = next(p for p in ids_line.palabras if re.fullmatch(r"SO-\d+", p.texto))
        division = ids_line.palabras[-1]
        prov_line = self._linea(pagina, "Pierre Fabre Ibérica")
        prov_words = [p for p in prov_line.palabras if p.texto in {"Pierre", "Fabre", "Ibérica:"}]
        prov_nif_line = next(
            linea for linea in pagina.lineas
            if "N.I.F." in normalizar_texto(linea.texto)
            and any(NIF_RE.fullmatch(p.texto) for p in linea.palabras)
        )
        prov_nif = next(p for p in prov_nif_line.palabras if NIF_RE.fullmatch(p.texto))
        prov_dir = [linea for linea in pagina.lineas if linea.bbox.y0 < 110 and "Ramón" in linea.texto]
        dest_line = next(linea for linea in pagina.lineas if normalizar_texto(linea.texto).startswith("PUIG SALOMON PIO"))
        dest_nif_line = next(
            linea for linea in pagina.lineas
            if normalizar_texto(linea.texto).startswith("C")
            and "NIF/DNI" in normalizar_texto(linea.texto)
        )
        dest_nif = next(p for p in dest_nif_line.palabras if NIF_RE.fullmatch(p.texto))
        dest_dir = [linea for linea in pagina.lineas if 175 < linea.bbox.y0 < 210 and linea.bbox.x0 < 300]
        dest_dir_words = [p for linea in dest_dir for p in linea.palabras if p.bbox.x0 < 300]
        total_line = next(
            linea for linea in pagina.lineas
            if "TOTAL I.V.A." in normalizar_texto(linea.texto)
            and "TOTAL FACTURA" in normalizar_texto(linea.texto)
        )
        total_vals = [p for p in total_line.palabras if _importe_token(p.texto) is not None]
        fiscal_line = next(
            linea for linea in pagina.lineas
            if normalizar_texto(linea.texto).startswith("BASE I.V.A.")
            and "CUOTA I.V.A." in normalizar_texto(linea.texto)
            and "R.E." in normalizar_texto(linea.texto)
        )
        fiscal_vals = [p for p in fiscal_line.palabras if _importe_token(p.texto) is not None]
        porcentajes = [p for p in fiscal_line.palabras if p.texto == "%"]
        cabecera = {
            "proveedor": {
                "nombre": self._campo(documento, prov_line, prov_words, " ".join(p.texto.strip(":") for p in prov_words), "proveedor_nombre", "RAZON_SOCIAL_VISIBLE_EN_REGISTRO_PRODUCTOR"),
                "nif": self._campo(documento, prov_nif_line, [prov_nif], prov_nif.texto, "proveedor_nif", "NIF_VISIBLE"),
                "direccion": self.campo_multilinea(documento, " ".join(p.texto for l in prov_dir for p in l.palabras), [p for l in prov_dir for p in l.palabras], prov_dir, "cabecera", "proveedor_direccion", "DIRECCION_CABECERA"),
            },
            "destinatario": {
                "nombre": self._campo(documento, dest_line, [p for p in dest_line.palabras if p.bbox.x0 < 300], "PUIG SALOMON PIO", "destinatario_nombre", "BLOQUE_DESTINATARIO"),
                "nif": self._campo(documento, dest_nif_line, [dest_nif], dest_nif.texto, "destinatario_nif", "NIF_VISIBLE"),
                "direccion": self.campo_multilinea(documento, " ".join(p.texto for p in dest_dir_words), dest_dir_words, dest_dir, "cabecera", "destinatario_direccion", "BLOQUE_DIRECCION_DESTINATARIO"),
            },
            "numero_factura": self._campo(documento, ids_line, [numero], numero.texto, "numero_factura", "COLUMNA_NUMERO_FACTURA"),
            "fecha_factura": self._fecha_campo(documento, ids_line, fecha, "fecha_factura"),
            "tipo_documento": self._campo(documento, tipo_line, tipo_line.palabras, "ABONO", "tipo_documento", "TITULO_ABONO_VISIBLE"),
            "naturaleza_principal": "MERCANCIA",
            "moneda": "EUR", "forma_pago": None,
            "base_imponible_total": self._dinero_signado(documento, pagina, total_line, total_vals[0], "base_imponible_total"),
            "iva_total": self._dinero_signado(documento, pagina, total_line, total_vals[1], "iva_total"),
            "recargo_equivalencia_total": self._dinero_signado(documento, pagina, total_line, total_vals[2], "recargo_equivalencia_total"),
            "importe_total": self._dinero_signado(documento, pagina, total_line, total_vals[-1], "importe_total"),
        }
        impuestos = [{
            "orden": 1, "origen": "RESUMEN_FISCAL", "naturaleza": "IVA_Y_RE",
            "base": self._dinero_signado(documento, pagina, fiscal_line, fiscal_vals[1], "base", tabla="fiscalidad"),
            "tipo_iva": self._campo(documento, fiscal_line, [fiscal_vals[0], porcentajes[0]], _importe_token(fiscal_vals[0].texto), "tipo_iva", "TIPO_IVA_VISIBLE", "fiscalidad"),
            "cuota_iva": self._dinero_signado(documento, pagina, fiscal_line, fiscal_vals[3], "cuota_iva", tabla="fiscalidad"),
            "tipo_recargo_equivalencia": self._campo(documento, fiscal_line, [fiscal_vals[4], porcentajes[-1]], _importe_token(fiscal_vals[4].texto), "tipo_recargo", "TIPO_RE_VISIBLE", "fiscalidad"),
            "cuota_recargo_equivalencia": self._dinero_signado(documento, pagina, fiscal_line, fiscal_vals[-1], "cuota_recargo", tabla="fiscalidad"),
        }]
        detalle_line = next(linea for linea in pagina.lineas if linea.palabras and re.fullmatch(r"\d{6}[.]R", linea.palabras[0].texto))
        dwords = detalle_line.palabras
        detalle = {
            "orden": 1,
            "codigo": self._campo(documento, detalle_line, [dwords[0]], dwords[0].texto, "codigo", "COLUMNA_CODIGO", "detalle"),
            "descripcion_literal": self._campo(documento, detalle_line, dwords[1:6], " ".join(p.texto for p in dwords[1:6]), "descripcion", "COLUMNA_DENOMINACION", "detalle"),
            "cantidad": self._dinero(documento, detalle_line, dwords[6], "cantidad", tabla="detalle"),
            "precio_unitario": self._dinero(documento, detalle_line, dwords[7], "precio_unitario", tabla="detalle"),
            "importe_venta": self._dinero_signado(documento, pagina, detalle_line, dwords[8], "importe_venta", tabla="detalle"),
            "descuento_porcentaje": self._campo(documento, detalle_line, [dwords[9]], float(dwords[9].texto.replace(",", ".")), "descuento_porcentaje", "COLUMNA_DTO", "detalle"),
            "descuento_importe": self._dinero_signado(documento, pagina, detalle_line, dwords[10], "descuento_importe", tabla="detalle"),
            "total": self._dinero_signado(documento, pagina, detalle_line, dwords[11], "total", tabla="detalle"),
            "tipo_iva": self._campo(documento, detalle_line, [dwords[12]], float(dwords[12].texto.replace(",", ".")), "tipo_iva", "COLUMNA_IVA", "detalle"),
            "sentido": "ABONO", "incidencias": [],
        }
        descuento_header_1 = self._linea(pagina, "DESCUENTO")
        descuento_header_2 = self._linea(pagina, "COMERC.")
        descuento_header_words = [
            next(p for p in descuento_header_1.palabras if normalizar_texto(p.texto) == "DESCUENTO"),
            next(p for p in descuento_header_2.palabras if normalizar_texto(p.texto) == "COMERC."),
        ]
        decision_descuento = documentar_sentido_decision_funcional_pio_pierre_fabre("DESCUENTO COMERC.")
        if decision_descuento is None:
            raise ValueError("Descuento Pierre Fabre sin decisión funcional acotada")
        descuento = {
            "orden": 1,
            "descripcion_literal": self.campo_multilinea(
                documento, "DESCUENTO COMERC.", descuento_header_words,
                [descuento_header_1, descuento_header_2], "movimientos", "descripcion",
                "CABECERA_DESCUENTO_COMERCIAL",
            ),
            "categoria": "DESCUENTO_COMERCIAL", "importe": detalle["descuento_importe"],
            "base": detalle["descuento_importe"], "iva": None, "recargo_equivalencia": None,
            "sentido": decision_descuento["valor"],
            "sentido_fuente": "DECISION_FUNCIONAL_PIO",
            "sentido_documentacion": decision_descuento,
            "es_movimiento_economico_independiente": False,
            "participa_en_conciliacion_base": True,
            "participacion_conciliacion_base": "RESTA_DESCUENTO_DOCUMENTAL_SOBRE_IMPORTE_VENTA",
            "incidencias": [],
            "provenance": {
                "fuente": "PDF_NATIVO_LOCAL", "gold_usado": False, "inferencia_por_signo": False,
                "autoridad_sentido": "PIO", "fuente_sentido": "DECISION_FUNCIONAL_PIO",
                "evidencia_documental_directa_sentido": False,
            },
        }
        ev_albaran = self._campo(documento, ids_line, [albaran_num], albaran_num.texto, "numero_albaran", "COLUMNA_ALBARAN", "albaranes")["evidencias"][0]
        albaran = AlbaranLocal(
            albaran_num.texto, None, None, [cabecera["base_imponible_total"]["valor"]], cabecera["importe_total"]["valor"], "ABONO",
            "ALBARAN_UNICO_EN_ABONO", 1, 1,
            {"numero_albaran": ev_albaran, "fecha": None, "tipo_pedido": None,
             "base": cabecera["base_imponible_total"]["evidencias"][0], "total": cabecera["importe_total"]["evidencias"][0]},
            atributos_documentales={
                "pedido": pedido.texto, "division": division.texto, "categoria": "MERCANCIA",
                "sentido_evidencia": cabecera["tipo_documento"],
                "base_total_evidencia_documental_directa_en_fila_albaran": False,
                "base_total_regla": "DERIVACION_RELACION_UNICO_ALBARAN_CON_FACTURA",
            },
        )
        venc_line = next(
            linea for linea in pagina.lineas
            if any(_fecha(p.texto) for p in linea.palabras)
            and "REMESA" in normalizar_texto(linea.texto)
        )
        venc_fecha = next(p for p in venc_line.palabras if _fecha(p.texto))
        remesa_words = [p for p in venc_line.palabras if normalizar_texto(p.texto) == "REMESA"]
        forma = self._campo(documento, venc_line, remesa_words, "Remesa", "forma_pago", "FORMA_PAGO_VISIBLE")
        cabecera["forma_pago"] = forma
        vencimiento = {"orden": 1, "fecha": self._fecha_campo(documento, venc_line, venc_fecha), "importe": None, "forma_pago": forma,
                       "incidencias": [{"codigo": "IMPORTE_VENCIMIENTO_NO_VISIBLE"}]}
        agente = self._linea(pagina, "VRP_PFDC")
        observaciones_header = self._linea(pagina, "OBSERVACIONES")
        observacion = next(linea for linea in pagina.lineas if linea.orden == observaciones_header.orden + 1)
        factura = self._factura(
            documento, segmento, cabecera, albaranes=[albaran], movimientos=[descuento], impuestos=impuestos,
            vencimientos=[vencimiento], otros=[
                {"tipo": "DETALLE_PRODUCTOS", "rol": "MERCANCIA_ABONADA", "lineas": [detalle]},
                self._literal_lineas(documento, [agente], "AGENTE_COMERCIAL"),
                self._literal_lineas(documento, [observacion], "OBSERVACIONES"),
            ], incidencias=[],
        )
        ajuste_descuento = self._derivado(
            -detalle["descuento_importe"]["valor"], [detalle["descuento_importe"]],
            "RESTA_DEL_DESCUENTO_IMPRESO_EN_FORMULA_DE_NETO",
        )
        factura["controles_conciliacion"].append(evaluar_conciliacion(EspecificacionConciliacion(
            "BASE_DESDE_VENTA_MENOS_DESCUENTO", "BASE_IMPONIBLE",
            ComponenteConciliacion(
                "BASE", factura["cabecera"]["base_imponible_total"]["valor"],
                "SIGNO_DOCUMENTAL_CONSERVADO", "cabecera",
                factura["cabecera"]["base_imponible_total"]["evidencias"][0].pagina,
                factura["cabecera"]["base_imponible_total"]["evidencias"],
            ),
            [
                ComponenteConciliacion(
                    "IMPORTE_VENTA", detalle["importe_venta"]["valor"], "SIGNO_DOCUMENTAL_CONSERVADO",
                    "detalle", detalle["importe_venta"]["evidencias"][0].pagina,
                    detalle["importe_venta"]["evidencias"],
                ),
                ComponenteConciliacion(
                    "AJUSTE_DESCUENTO", ajuste_descuento["valor"], "RESTA_DESCUENTO_DOCUMENTAL",
                    "detalle", ajuste_descuento["evidencias"][0].pagina, ajuste_descuento["evidencias"],
                ),
            ],
            {"regla": "IMPORTE_VENTA_MENOS_DESCUENTO_IMPRESO", "gold_usado": False},
        )))
        factura["null_legitimos"] = ["fecha_albaran_no_visible", "importe_vencimiento_no_visible"]
        return factura


class AdaptadorSuavinexHistorico(AdaptadorHistoricoGold1Base):
    id, version = "suavinex-historico-local", "1.0.0"
    layout, constructor = "SUAVINEX_FACTURA_MERCANCIA_V1", "_construir"
    senales = ("Suavinex Group, S.L.", "Factura Nº:", "Infor.Pto.Verde", "Giro domiciliado CORE")

    def _construir(self, documento, segmento):
        pagina = documento.paginas[0]
        factura_line = self._linea(pagina, "Factura Nº:")
        numero = next(p for p in factura_line.palabras if re.fullmatch(r"\d{8,12}", p.texto))
        fecha = next(p for p in factura_line.palabras if _fecha(p.texto))
        referencia = next(p for p in factura_line.palabras if re.fullmatch(r"O-\d+", p.texto))
        proveedor = self._linea(pagina, "Suavinex Group, S.L.")
        prov_nif_line = next(
            linea for linea in pagina.lineas
            if "C.I.F." in normalizar_texto(linea.texto)
            and any(NIF_RE.fullmatch(p.texto.rstrip(".")) for p in linea.palabras)
        )
        prov_nif = next(p for p in prov_nif_line.palabras if NIF_RE.fullmatch(p.texto.rstrip(".")))
        prov_dir = [linea for linea in pagina.lineas if 55 < linea.bbox.y0 < 74 and linea.bbox.x0 < 300]
        prov_dir_words = [p for linea in prov_dir for p in linea.palabras if p.bbox.x0 < 300]
        cliente_line = self._linea(pagina, "Cliente:")
        cliente = next(p for p in cliente_line.palabras if re.fullmatch(r"\d+", p.texto))
        dest_nif = next(p for p in cliente_line.palabras if NIF_RE.fullmatch(p.texto))
        dest_line = self._linea(pagina, "PUIG SALOMON, PIO")
        dest_dir = [
            linea for linea in pagina.lineas
            if 30 < linea.bbox.y0 < 80 and 300 < linea.bbox.x0 < 450
            and "PAGINA" not in normalizar_texto(linea.texto)
        ]
        base_header = self._linea(pagina, "Base IVA Recargo Cuota")
        base_line = next(
            linea for linea in pagina.lineas
            if base_header.orden < linea.orden <= base_header.orden + 3
            and len([p for p in linea.palabras if _importe_token(p.texto) is not None]) >= 4
        )
        base_vals = [p for p in base_line.palabras if _importe_token(p.texto) is not None]
        porcentajes = [p for p in base_line.palabras if "%" in p.texto]
        neto_line = self._linea(pagina, "Importe Neto")
        neto_word = [p for p in neto_line.palabras if _importe_token(p.texto) is not None][-1]
        bruto_line = self._linea(pagina, "Importe Bruto")
        bruto_word = [p for p in bruto_line.palabras if _importe_token(p.texto) is not None][-1]
        impuestos_line = self._linea(pagina, "Impuestos:")
        cuota_total_word = [p for p in impuestos_line.palabras if _importe_token(p.texto) is not None][-1]
        total_line = self._linea(pagina, "Total Factura")
        total_word = [p for p in total_line.palabras if _importe_token(p.texto) is not None][-1]
        pago_line = self._linea(pagina, "Giro domiciliado CORE")
        pago_words = [p for p in pago_line.palabras if p.bbox.x0 < pagina.ancho * 0.55]
        cabecera = {
            "proveedor": {
                "nombre": self._campo(documento, proveedor, proveedor.palabras, proveedor.texto, "proveedor_nombre", "RAZON_SOCIAL_VISIBLE"),
                "nif": self._campo(documento, prov_nif_line, [prov_nif], prov_nif.texto.strip("."), "proveedor_nif", "CIF_VISIBLE"),
                "direccion": self.campo_multilinea(documento, " ".join(p.texto for p in prov_dir_words), prov_dir_words, prov_dir, "cabecera", "proveedor_direccion", "BLOQUE_DIRECCION_PROVEEDOR"),
            },
            "destinatario": {
                "nombre": self._campo(documento, dest_line, [p for p in dest_line.palabras if p.bbox.x0 > pagina.ancho * 0.55], "PUIG SALOMON, PIO", "destinatario_nombre", "BLOQUE_DESTINATARIO"),
                "nif": self._campo(documento, cliente_line, [dest_nif], dest_nif.texto, "destinatario_nif", "NIF_CLIENTE_VISIBLE"),
                "direccion": self.campo_multilinea(documento, " ".join(p.texto for l in dest_dir for p in l.palabras), [p for l in dest_dir for p in l.palabras], dest_dir, "cabecera", "destinatario_direccion", "BLOQUE_DIRECCION_DESTINATARIO"),
            },
            "numero_factura": self._campo(documento, factura_line, [numero], numero.texto, "numero_factura", "NUMERO_FACTURA_ETIQUETADO"),
            "fecha_factura": self._fecha_campo(documento, factura_line, fecha, "fecha_factura"),
            "tipo_documento": self._campo(documento, factura_line, factura_line.palabras[:2], "FACTURA", "tipo_documento", "ETIQUETA_FACTURA_VISIBLE"),
            "naturaleza_principal": "MERCANCIA",
            "moneda": "EUR", "codigo_cliente": self._campo(documento, cliente_line, [cliente], cliente.texto, "codigo_cliente", "CLIENTE_VISIBLE"),
            "referencia": self._campo(documento, factura_line, [referencia], referencia.texto, "referencia", "REFERENCIA_VISIBLE"),
            "forma_pago": self._campo(documento, pago_line, pago_words, "Giro domiciliado CORE", "forma_pago", "FORMA_PAGO_VISIBLE"),
            "base_imponible_total": self._dinero(documento, neto_line, neto_word, "base_imponible_total"),
            "importe_bruto": self._dinero(documento, bruto_line, bruto_word, "importe_bruto"),
            "iva_total": None, "recargo_equivalencia_total": None,
            "importe_total": self._dinero(documento, total_line, total_word, "importe_total"),
        }
        base = self._dinero(documento, base_line, base_vals[0], "base", tabla="fiscalidad")
        tipo_iva = self._campo(documento, base_line, [base_vals[1], porcentajes[0]], _importe_token(base_vals[1].texto), "tipo_iva", "TIPO_IVA_VISIBLE", "fiscalidad")
        tipo_re = self._campo(documento, base_line, [base_vals[2], porcentajes[1]], _importe_token(base_vals[2].texto), "tipo_recargo", "TIPO_RE_VISIBLE", "fiscalidad")
        cuota_agregada = self._dinero(documento, base_line, base_vals[-1], "cuota_fiscal_agregada", tabla="fiscalidad")
        decimal_base = Decimal(str(base["valor"])); centimos = Decimal("0.01")
        iva_valor = (decimal_base * Decimal(str(tipo_iva["valor"])) / Decimal("100")).quantize(centimos, rounding=ROUND_HALF_UP)
        re_valor = (decimal_base * Decimal(str(tipo_re["valor"])) / Decimal("100")).quantize(centimos, rounding=ROUND_HALF_UP)
        cuota_iva = self._derivado(float(iva_valor), [base, tipo_iva, cuota_agregada], "CUOTA_IVA_DESDE_BASE_TIPO_Y_CUOTA_AGREGADA")
        cuota_re = self._derivado(float(re_valor), [base, tipo_re, cuota_agregada], "CUOTA_RE_DESDE_BASE_TIPO_Y_CUOTA_AGREGADA")
        cabecera["iva_total"] = cuota_iva
        cabecera["recargo_equivalencia_total"] = cuota_re
        impuestos = [{
            "orden": 1, "origen": "CUOTA_FISCAL_AGREGADA", "naturaleza": "IVA_Y_RE",
            "base": base, "tipo_iva": tipo_iva, "cuota_iva": cuota_iva,
            "tipo_recargo_equivalencia": tipo_re, "cuota_recargo_equivalencia": cuota_re,
            "cuota_fiscal_agregada_visible": cuota_agregada,
            "cuota_fiscal_resumen_visible": self._dinero(documento, impuestos_line, cuota_total_word, "cuota_fiscal_resumen", tabla="fiscalidad"),
        }]
        detalles = []
        for orden, linea in enumerate((l for l in pagina.lineas if l.palabras and re.fullmatch(r"\d{6}", l.palabras[0].texto)), 1):
            words = linea.palabras
            codigo = words[0]
            descripcion = [p for p in words if pagina.ancho * 0.08 <= p.bbox.x0 < pagina.ancho * 0.50]
            cantidad = next(p for p in words if pagina.ancho * 0.50 <= p.bbox.x0 < pagina.ancho * 0.57)
            precio = next(p for p in words if pagina.ancho * 0.57 <= p.bbox.x0 < pagina.ancho * 0.65)
            importe = next(p for p in words if p.bbox.x0 > pagina.ancho * 0.82 and _importe_token(p.texto) is not None)
            dto = next((p for p in words if pagina.ancho * 0.65 <= p.bbox.x0 < pagina.ancho * 0.72 and _importe_token(p.texto) is not None), None)
            neto = next(
                p for p in words
                if pagina.ancho * 0.72 <= p.bbox.x0 < pagina.ancho * 0.82
                and re.fullmatch(r"-?\d+[.,]\d{4}", p.texto)
            )
            detalles.append({
                "orden": orden,
                "codigo": self._campo(documento, linea, [codigo], codigo.texto, "codigo", "COLUMNA_CODIGO", "detalle"),
                "descripcion_literal": self._campo(documento, linea, descripcion, " ".join(p.texto for p in descripcion), "descripcion", "COLUMNA_DESCRIPCION", "detalle"),
                "cantidad": self._campo(documento, linea, [cantidad], int(cantidad.texto), "cantidad", "COLUMNA_CANTIDAD", "detalle"),
                "precio_factura": self._dinero(documento, linea, precio, "precio_factura", tabla="detalle"),
                "descuento_porcentaje": self._campo(documento, linea, [dto], float(dto.texto.replace(",", ".")), "descuento_porcentaje", "COLUMNA_DTO", "detalle") if dto else None,
                "precio_neto": self._campo(documento, linea, [neto], float(neto.texto.replace(",", ".")), "precio_neto", "COLUMNA_PRECIO_NETO", "detalle"),
                "importe": self._dinero(documento, linea, importe, "importe", tabla="detalle"),
                "incidencias": [],
            })
        albaran_line = self._linea(pagina, "Pedido:")
        pedido = next(p for p in albaran_line.palabras if re.fullmatch(r"\d{9}", p.texto))
        albaran_num = next(p for p in albaran_line.palabras if re.fullmatch(r"\d{8}", p.texto))
        ev_num = self._campo(documento, albaran_line, [albaran_num], albaran_num.texto, "numero_albaran", "NUMERO_ALBARAN_VISIBLE", "albaranes")["evidencias"][0]
        giro_line = next(
            linea for linea in pagina.lineas
            if "FACTURA GIRARA" in normalizar_texto(linea.texto)
            and "MANDATO SEPA" in normalizar_texto(linea.texto)
        )
        giro_campo = self._campo(
            documento, giro_line, giro_line.palabras, giro_line.texto,
            "sentido_albaran", "FACTURA_GIRADA_SEGUN_MANDATO_SEPA", "albaranes",
        )
        albaran = AlbaranLocal(
            albaran_num.texto, None, None, [base["valor"]], cabecera["importe_total"]["valor"], "CARGO",
            "ALBARAN_UNICO_BAJO_FACTURA_GIRADA", 1, 1,
            {"numero_albaran": ev_num, "fecha": None, "tipo_pedido": None,
             "base": base["evidencias"][0], "total": cabecera["importe_total"]["evidencias"][0]},
            atributos_documentales={
                "pedido": pedido.texto, "categoria": "MERCANCIA",
                "sentido_regla": "FACTURA_GIRADA_POR_SEPA", "sentido_evidencia": giro_campo,
                "base_total_evidencia_documental_directa_en_fila_albaran": False,
                "base_total_regla": "DERIVACION_RELACION_UNICO_ALBARAN_CON_FACTURA",
            },
        )
        punto_line = self._linea(pagina, "Infor.Pto.Verde")
        punto_word = [p for p in punto_line.palabras if _importe_token(p.texto) is not None][-1]
        punto = {
            "tipo": "APORTACION_AMBIENTAL_INFORMATIVA", "categoria": "APORTACION_AMBIENTAL_INCLUIDA",
            "descripcion_literal": self._campo(documento, punto_line, [p for p in punto_line.palabras if _importe_token(p.texto) is None], "Infor.Pto.Verde", "descripcion", "LITERAL_PUNTO_VERDE", "otros"),
            "importe": self._dinero(documento, punto_line, punto_word, "importe", tabla="otros"),
            "incluido_en_base": True, "incluido_en_total": True,
            "es_movimiento_economico_independiente": False,
            "provenance": {"regla": "NO_SE_ANADEN_IMPORTES_FUERA_DE_BASE_MAS_CUOTA_FISCAL", "gold_usado": False},
        }
        vto_line = self._linea(pagina, "Vto.:")
        vfecha = next(p for p in vto_line.palabras if _fecha(p.texto))
        vimporte_line = next(
            linea for linea in pagina.lineas
            if normalizar_texto(linea.texto).startswith("IMPORTE:")
            and any(_importe_token(p.texto) is not None for p in linea.palabras)
        )
        vimporte = [p for p in vimporte_line.palabras if _importe_token(p.texto) is not None][-1]
        vencimiento = {
            "orden": 1, "fecha": self._fecha_campo(documento, vto_line, vfecha),
            "importe": self._dinero(documento, vimporte_line, vimporte, "importe", tabla="vencimientos"),
            "forma_pago": cabecera["forma_pago"],
        }
        mandato_lineas = [linea for linea in pagina.lineas if "MANDATO SEPA" in normalizar_texto(linea.texto)]
        factura = self._factura(
            documento, segmento, cabecera, albaranes=[albaran], impuestos=impuestos,
            vencimientos=[vencimiento], otros=[
                {"tipo": "DETALLE_PRODUCTOS", "rol": "MERCANCIA_FACTURADA", "lineas": detalles},
                punto,
                self._literal_lineas(documento, mandato_lineas, "MANDATO_SEPA"),
            ], incidencias=[],
        )
        self._control_base_detalle(factura, detalles)
        factura["controles_conciliacion"].append(evaluar_conciliacion(EspecificacionConciliacion(
            "CUOTA_FISCAL_AGREGADA_VS_DESGLOSE", "CUOTA_FISCAL_AGREGADA",
            ComponenteConciliacion(
                "CUOTA_AGREGADA", cuota_agregada["valor"], "SIGNO_DOCUMENTAL_CONSERVADO", "fiscalidad",
                cuota_agregada["evidencias"][0].pagina, cuota_agregada["evidencias"],
            ),
            [
                ComponenteConciliacion(
                    "CUOTA_IVA_DERIVADA", cuota_iva["valor"], "DERIVADO_DE_BASE_Y_TIPO", "fiscalidad",
                    cuota_iva["evidencias"][0].pagina, cuota_iva["evidencias"],
                ),
                ComponenteConciliacion(
                    "CUOTA_RE_DERIVADA", cuota_re["valor"], "DERIVADO_DE_BASE_Y_TIPO", "fiscalidad",
                    cuota_re["evidencias"][0].pagina, cuota_re["evidencias"],
                ),
            ],
            {"regla": "SUMA_CUOTAS_DERIVADAS_CONTRA_CUOTA_AGREGADA_VISIBLE", "gold_usado": False},
        )))
        factura["null_legitimos"] = ["fecha_albaran_no_visible"]
        return factura
