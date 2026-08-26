from __future__ import annotations

import re

from ..geometria.lineas import DATE_RE, normalizar_texto, parsear_importe
from ..geometria.tablas import zonas_relativas
from ..modelos import AlbaranLocal, DocumentoLocal, union_bbox
from .base import AdaptadorBase, Reconocimiento


class AdaptadorCofares(AdaptadorBase):
    id = "cofares-local"
    version = "1.0.0"
    capacidades = {
        "segmentacion": "SOPORTADO_MONOPAGINA",
        "cabecera": "NO_SOPORTADO",
        "albaranes": "SOPORTADO",
        "movimientos": "NO_SOPORTADO",
        "impuestos": "NO_SOPORTADO",
        "vencimientos": "NO_SOPORTADO",
    }

    def reconocer(self, documento: DocumentoLocal) -> Reconocimiento:
        text = normalizar_texto("\n".join(p.texto for p in documento.paginas))
        comprobaciones = {
            "identidad_proveedor": "GRUPO COFARES" in text,
            "titulo_resumen": "RESUMEN DE SUMINISTROS" in text,
            "cabecera_fecha": "F.PEDIDO" in text,
            "cabecera_albaran": any(literal in text for literal in ("Nº ALBARAN", "N° ALBARAN", "NO ALBARAN", "N ALBARAN")),
            "cabecera_total": "TOTAL" in text,
            "cabecera_bases": "BASES" in text or "BASE SR" in text,
            "cabecera_tipo_pedido": "T.PED" in text,
            "monopagina": len(documento.paginas) == 1,
            "fila_tabular_visible": bool(re.search(r"\b\d{2}\.\d{2}\.\d{4}\s+\d{8,12}\s+\d+[.,]\d{2}.*\s\d{3}\b", text)),
        }
        evidencias = [
            {"senal": nombre, "presente": presente, "origen": "TEXTO_PDF_LOCAL"}
            for nombre, presente in comprobaciones.items()
        ]
        completas = all(comprobaciones.values())
        indicios = comprobaciones["identidad_proveedor"] or any(
            comprobaciones[nombre] for nombre in comprobaciones if nombre.startswith("cabecera_")
        )
        estado = "RECONOCIDO" if completas else ("AMBIGUO" if indicios else "NO_RECONOCIDO")
        puntuacion = 100 if completas else round(100 * sum(comprobaciones.values()) / len(comprobaciones))
        return Reconocimiento(estado, puntuacion, evidencias)

    def extraer_albaranes(self, documento: DocumentoLocal, segmentos):
        salida = []
        reconocimiento = self.reconocer(documento)
        if reconocimiento.estado != "RECONOCIDO":
            return salida
        for pagina in documento.paginas:
            for linea in pagina.lineas:
                for zone_words in zonas_relativas(pagina.ancho, linea.palabras):
                    dates = [w for w in zone_words if DATE_RE.fullmatch(w.texto)]
                    ids = [w for w in zone_words if re.fullmatch(r"\d{8,12}", w.texto)]
                    if len(dates) != 1 or len(ids) != 1:
                        continue
                    after = [w for w in zone_words if w.bbox.x0 > ids[0].bbox.x1]
                    monies = [(w, parsear_importe(w.texto)) for w in after]
                    monies = [(w, v) for w, v in monies if v is not None]
                    types = [w for w in after if re.fullmatch(r"\d{3}", w.texto) and parsear_importe(w.texto) is None]
                    if len(monies) < 2 or len(types) != 1:
                        continue
                    row_words = sorted(zone_words, key=lambda w: w.bbox.x0)
                    literal = " ".join(w.texto for w in row_words)
                    row_box = union_bbox([w.bbox for w in row_words])
                    bases = [v for _, v in monies[1:]]
                    evidencias = {
                        "numero_albaran": self.evidencia(documento, pagina.numero, ids[0].texto, ids[0].bbox, literal, row_box, "resumen_suministros", "Nº Albarán", "TOKEN_BAJO_N_ALBARAN"),
                        "fecha": self.evidencia(documento, pagina.numero, dates[0].texto, dates[0].bbox, literal, row_box, "resumen_suministros", "F.Pedido", "FECHA_MISMA_FILA"),
                        "tipo_pedido": self.evidencia(documento, pagina.numero, types[0].texto, types[0].bbox, literal, row_box, "resumen_suministros", "T.Ped", "TOKEN_BAJO_T_PED"),
                        "base": self.evidencia(documento, pagina.numero, "+".join(w.texto for w, _ in monies[1:]), union_bbox([w.bbox for w, _ in monies[1:]]), literal, row_box, "resumen_suministros", "Bases", "SUMA_COLUMNAS_BASE", "DERIVACION_LOCAL"),
                        "total": self.evidencia(documento, pagina.numero, monies[0][0].texto, monies[0][0].bbox, literal, row_box, "resumen_suministros", "Total", "PRIMER_IMPORTE_TRAS_ALBARAN"),
                    }
                    salida.append(AlbaranLocal(ids[0].texto, dates[0].texto, types[0].texto, bases, monies[0][1], None, "DETALLE_ALBARAN", pagina.numero, 0, evidencias))
        salida.sort(key=lambda x: (x.pagina, x.evidencias["numero_albaran"].bbox[1], x.evidencias["numero_albaran"].bbox[0]))
        for index, row in enumerate(salida, 1):
            row.orden = index
        return salida
