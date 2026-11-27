"""suavinex-local 1.0.0 (FACTURAS-0, fábrica de lectores, 2026-11-27). Sin autoridad productiva y SIN REGISTRAR.

Lector determinista de las facturas y abonos (facturas rectificativas) de Suavinex Group, S.L. (CIF B03074093), sobre
la plantilla común (``AdaptadorBase``). Un PDF puede llevar varios documentos seguidos: se segmenta por el número
impreso («Factura Nº» / «Abono Nº») y la paginación «Página i/n». No está en ``REGISTRO_ADAPTADORES_LOCALES`` (el
registro necesita el OK de Pio y hoy convive ``suavinex-historico-local``): se usa llamando a ``extraer_facturas``.

Falla cerrado (``ValueError("CONTROL_SUAVINEX:...")``) si no cuadra lo impreso: Σ líneas = importe bruto = importe neto =
Σ bases; cuota = base × (IVA + RE) con 0,01; Σ cuotas = impuestos; neto + impuestos = total; factura con vencimientos
cuya suma es el total; abono sin vencimientos, con total negativo y «Abono a compensar».
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from ..geometria.campos import fecha_iso, lineas_con_texto, palabras_fecha, palabras_importe
from ..geometria.lineas import normalizar_texto
from ..modelos import DocumentoLocal, PalabraLocal
from .base import AdaptadorBase, Reconocimiento

CIF_LITERAL = "ESB03074093"
CIF = "B03074093"
RE_NUMERO = re.compile(r"\b(Factura|Abono)\s+N\S*:\s*(\d{10})")
RE_PAGINA = re.compile(r"P\S*gina\s+(\d+)\s*/\s*(\d+)")
RE_CODIGO = re.compile(r"^\d{4,7}$")  # códigos de artículo de 5 y 6 dígitos en el espejo
RE_ALBARAN = re.compile(r"^\d{8}$")
C = Decimal("0.01")


def _d(palabra: PalabraLocal) -> Decimal:
    """Importe es-ES de la palabra impresa (``1.985,19`` / ``-10,88``), sin pasar por float."""
    texto = palabra.texto.strip()
    negativo = texto.startswith("-") or texto.endswith("-")
    valor = Decimal(texto.strip("+-").replace(".", "").replace(",", "."))
    return -valor if negativo else valor


class AdaptadorSuavinex(AdaptadorBase):
    id = "suavinex-local"
    version = "1.0.0"
    capacidades = {
        "segmentacion": "SOPORTADO_MULTIDOCUMENTO_POR_NUMERO_Y_PAGINACION",
        "cabecera": "SOPORTADO",
        "albaranes": "SOPORTADO_NUMERO_SIN_IMPORTE_IMPRESO",
        "movimientos": "NO_APLICA",
        "impuestos": "SOPORTADO",
        "vencimientos": "SOPORTADO",
    }

    def reconocer(self, documento: DocumentoLocal) -> Reconocimiento:
        texto = "\n".join(p.texto for p in documento.paginas)
        normal = normalizar_texto(texto)
        comprobaciones = {
            "razon_social": "SUAVINEX GROUP, S.L." in normal,
            "cif_visible": CIF_LITERAL in texto,
            "numero_documento": bool(RE_NUMERO.search(texto)),
            "cuadro_fiscal": "BASE IVA RECARGO CUOTA" in normal,
            "total_factura": "TOTAL FACTURA:" in normal,
            "paginacion": bool(RE_PAGINA.search(texto)),
            "texto_nativo": bool(documento.paginas) and all(p.palabras for p in documento.paginas),
        }
        presentes = sum(comprobaciones.values())
        reconocido = all(comprobaciones.values())
        indicios = comprobaciones["razon_social"] or comprobaciones["cif_visible"]
        return Reconocimiento(
            "RECONOCIDO" if reconocido else ("AMBIGUO" if indicios else "NO_RECONOCIDO"),
            100 if reconocido else round(100 * presentes / len(comprobaciones)),
            [{"senal": k, "presente": v, "origen": "TEXTO_PDF_LOCAL"} for k, v in comprobaciones.items()],
        )

    # Los datos van por factura (``extraer_facturas``); el documento no tiene albaranes propios.
    def extraer_albaranes(self, documento: DocumentoLocal, segmentos):
        return []

    def segmentar_documentos(self, documento: DocumentoLocal) -> list[list[int]]:
        """Grupos de páginas por documento: mismo número impreso y paginación 1..n consecutiva."""
        grupos: list[list[int]] = []
        actual: tuple[str, str] | None = None
        for pagina in documento.paginas:
            numero, paginacion = RE_NUMERO.search(pagina.texto), RE_PAGINA.search(pagina.texto)
            if numero is None or paginacion is None:
                raise ValueError(f"CONTROL_SUAVINEX:PAGINA_SIN_NUMERO_O_PAGINACION:{pagina.numero}")
            clave, i, n = (numero.group(1), numero.group(2)), int(paginacion.group(1)), int(paginacion.group(2))
            if i == 1:
                grupos.append([pagina.numero])
                actual = clave
            elif clave == actual and grupos and len(grupos[-1]) == i - 1:
                grupos[-1].append(pagina.numero)
            else:
                raise ValueError(f"CONTROL_SUAVINEX:PAGINACION_INCOHERENTE:{pagina.numero}")
            if i == n:
                actual = None
        if actual is not None:
            raise ValueError("CONTROL_SUAVINEX:DOCUMENTO_INCOMPLETO")
        return grupos

    def extraer_facturas(self, documento: DocumentoLocal, segmentos) -> list[dict[str, Any]]:
        if self.reconocer(documento).estado != "RECONOCIDO":
            return []
        return [self._factura(documento, paginas) for paginas in self.segmentar_documentos(documento)]

    # --- una factura --------------------------------------------------------------------------------------------

    def _factura(self, documento: DocumentoLocal, paginas: list[int]) -> dict[str, Any]:
        lineas = [l for p in documento.paginas if p.numero in paginas for l in p.lineas]
        primera = [l for l in documento.paginas[paginas[0] - 1].lineas]
        linea_numero = next(l for l in primera if RE_NUMERO.search(l.texto))
        es_abono = RE_NUMERO.search(linea_numero.texto).group(1) == "Abono"
        numero = next(p for p in linea_numero.palabras if re.fullmatch(r"\d{10}", p.texto))
        fecha = palabras_fecha(linea_numero)[0]
        tipo_palabra = linea_numero.palabras[0]
        nif_linea = next(l for l in lineas if CIF_LITERAL in l.texto)
        nif_palabra = next(p for p in nif_linea.palabras if CIF_LITERAL in p.texto)
        razon = next(l for l in primera if normalizar_texto(l.texto).startswith("SUAVINEX GROUP"))
        razon_palabras = razon.palabras[:3]

        albaranes, lineas_producto = [], []
        for linea in lineas:
            if linea.palabras and linea.palabras[0].texto.startswith("Pedido"):
                for i, p in enumerate(linea.palabras):
                    if p.texto.startswith("Albar") and i + 1 < len(linea.palabras) and RE_ALBARAN.fullmatch(linea.palabras[i + 1].texto):
                        palabra = linea.palabras[i + 1]
                        albaranes.append({"numero": self.campo_documentado(documento, palabra.texto, [palabra], linea, "albaranes", "numero_albaran", "NUMERO_TRAS_ALBARAN"),
                                          "importe_base_suma_lineas": "0"})
            elif linea.palabras and RE_CODIGO.fullmatch(linea.palabras[0].texto) and palabras_importe(linea):
                importe = palabras_importe(linea)[-1][0]
                if importe is not linea.palabras[-1]:
                    raise ValueError(f"CONTROL_SUAVINEX:LINEA_SIN_IMPORTE_FINAL:{linea.texto[:60]}")
                fila = {"importe": self.campo_documentado(documento, str(_d(importe)), [importe], linea, "lineas", "importe", "ULTIMA_COLUMNA_IMPORTE")}
                lineas_producto.append(fila)
                if albaranes:
                    albaranes[-1]["importe_base_suma_lineas"] = str(Decimal(albaranes[-1]["importe_base_suma_lineas"]) + _d(importe))

        impuestos = []
        for linea in lineas:
            if linea.texto.count("%") == 2 and linea.palabras[-1].texto == "EUR":
                importes = [p for p, _ in palabras_importe(linea)]
                if len(importes) != 4:
                    raise ValueError(f"CONTROL_SUAVINEX:FILA_FISCAL:{linea.texto[:60]}")
                base, iva, recargo, cuota = importes
                impuestos.append({
                    "base": self.campo_documentado(documento, str(_d(base)), [base], linea, "impuestos", "base", "COLUMNA_BASE"),
                    "tipo_iva": self.campo_documentado(documento, str(_d(iva)), [iva], linea, "impuestos", "tipo_iva", "PORCENTAJE_IMPRESO"),
                    "tipo_recargo_equivalencia": self.campo_documentado(documento, str(_d(recargo)), [recargo], linea, "impuestos", "tipo_re", "PORCENTAJE_IMPRESO"),
                    "cuota": self.campo_documentado(documento, str(_d(cuota)), [cuota], linea, "impuestos", "cuota", "COLUMNA_CUOTA"),
                })

        def total(etiqueta, columna):
            candidatas = [l for l in lineas_con_texto(lineas, etiqueta) if palabras_importe(l)]
            if len(candidatas) != 1:
                return None
            palabra = palabras_importe(candidatas[0])[0][0]
            return self.campo_documentado(documento, str(_d(palabra)), [palabra], candidatas[0], "totales", columna, "VALOR_TRAS_ETIQUETA")

        totales = {"importe_bruto": total("Importe Bruto:", "importe_bruto"), "importe_neto": total("Importe Neto:", "importe_neto"),
                   "impuestos": total("Impuestos:", "impuestos"), "total": total("Total Factura:", "total"),
                   "punto_verde_informativo": total("Pto.Verde:", "punto_verde")}

        vencimientos = []
        fechas_vto = [l for l in lineas if normalizar_texto(l.texto).startswith("VTO.:")]
        importes_vto = [l for l in lineas if normalizar_texto(l.texto).startswith("IMPORTE:")]
        if len(fechas_vto) != len(importes_vto):
            raise ValueError("CONTROL_SUAVINEX:VENCIMIENTOS_DESPAREJADOS")
        for linea_f, linea_i in zip(fechas_vto, importes_vto, strict=True):
            f, (i, _) = palabras_fecha(linea_f)[0], palabras_importe(linea_i)[0]
            vencimientos.append({
                "fecha": self.campo_documentado(documento, fecha_iso(f.texto), [f], linea_f, "vencimientos", "fecha", "FECHA_TRAS_VTO", literal=f.texto),
                "importe": self.campo_documentado(documento, str(_d(i)), [i], linea_i, "vencimientos", "importe", "IMPORTE_DEL_VENCIMIENTO"),
            })

        factura = {
            "paginas": [paginas[0], paginas[-1]],
            "tipo_documento": self.campo_documentado(documento, "ABONO" if es_abono else "FACTURA", [tipo_palabra], linea_numero, "cabecera", "tipo_documento", "LITERAL_ABONO_O_FACTURA"),
            "numero_factura": self.campo_documentado(documento, numero.texto, [numero], linea_numero, "cabecera", "numero_factura", "NUMERO_TRAS_ETIQUETA"),
            "fecha_factura": self.campo_documentado(documento, fecha_iso(fecha.texto), [fecha], linea_numero, "cabecera", "fecha_factura", "FECHA_MISMA_LINEA", literal=fecha.texto),
            "proveedor": {
                "nif": self.campo_documentado(documento, CIF, [nif_palabra], nif_linea, "cabecera", "proveedor_nif", "CIF_TRAS_ES_EN_PIE"),
                "nombre": self.campo_documentado(documento, " ".join(p.texto for p in razon_palabras), razon_palabras, razon, "cabecera", "proveedor_nombre", "RAZON_SOCIAL_PRIMERA_LINEA"),
            },
            "albaranes": albaranes,
            "lineas": lineas_producto,
            "movimientos": [],
            "impuestos": impuestos,
            "totales": totales,
            "vencimientos": vencimientos,
            "forma_pago_abono_a_compensar": any(
                "abono a compensar" in p.texto.lower() for p in documento.paginas if p.numero in paginas),
        }
        factura["controles"] = self.controles(factura, es_abono)
        fallos = [c for c in factura["controles"] if c["resultado"] != "OK"]
        if fallos:
            raise ValueError("CONTROL_SUAVINEX:" + numero.texto + ":" + ";".join(
                f"{c['codigo']}:{c['calculado']}/{c['impreso']}" for c in fallos))
        return factura

    @staticmethod
    def controles(f: dict[str, Any], es_abono: bool) -> list[dict[str, Any]]:
        salida = []

        def v(campo):
            return None if campo is None else Decimal(campo["valor"])

        def control(codigo, calculado, impreso, tolerancia=Decimal("0")):
            ok = calculado is not None and impreso is not None and abs(calculado - impreso) <= tolerancia
            salida.append({"codigo": codigo, "resultado": "OK" if ok else "FALLO", "calculado": str(calculado),
                           "impreso": str(impreso), "tolerancia": str(tolerancia)})

        t = f["totales"]
        suma_lineas = sum((v(l["importe"]) for l in f["lineas"]), Decimal("0"))
        # Redondeo documental (F0-8, Pio 2026-11-27): Suavinex calcula el bruto con el precio neto de 4 decimales y
        # cada línea impresa va redondeada; tolerancia mín(0,01 × filas; 0,50).
        control("SUMA_LINEAS_IMPORTE_BRUTO", suma_lineas, v(t["importe_bruto"]),
                min(C * len(f["lineas"]), Decimal("0.50")))
        control("BRUTO_NETO", v(t["importe_bruto"]), v(t["importe_neto"]))
        control("SUMA_BASES_NETO", sum((v(i["base"]) for i in f["impuestos"]), Decimal("0")) if f["impuestos"] else None,
                v(t["importe_neto"]))
        for n, i in enumerate(f["impuestos"], 1):
            esperado = (v(i["base"]) * (v(i["tipo_iva"]) + v(i["tipo_recargo_equivalencia"])) / 100).quantize(C, rounding=ROUND_HALF_UP)
            control(f"TRAMO_{n}_CUOTA", esperado, v(i["cuota"]), C)
        control("SUMA_CUOTAS_IMPUESTOS", sum((v(i["cuota"]) for i in f["impuestos"]), Decimal("0")), v(t["impuestos"]))
        control("NETO_MAS_IMPUESTOS_TOTAL", (v(t["importe_neto"]) or Decimal("0")) + (v(t["impuestos"]) or Decimal("0"))
                if t["importe_neto"] and t["impuestos"] else None, v(t["total"]))
        if es_abono:
            control("ABONO_SIN_VENCIMIENTOS", Decimal(len(f["vencimientos"])), Decimal("0"))
            control("ABONO_TOTAL_NEGATIVO", Decimal("1") if t["total"] and v(t["total"]) < 0 else Decimal("0"), Decimal("1"))
            control("ABONO_A_COMPENSAR", Decimal("1") if f["forma_pago_abono_a_compensar"] else Decimal("0"), Decimal("1"))
        else:
            control("SUMA_VENCIMIENTOS_TOTAL", sum((v(x["importe"]) for x in f["vencimientos"]), Decimal("0"))
                    if f["vencimientos"] else None, v(t["total"]))
        return salida


__all__ = ["AdaptadorSuavinex"]
