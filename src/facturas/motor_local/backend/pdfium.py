from __future__ import annotations

import hashlib
import importlib.metadata
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from ..geometria.lineas import agrupar_por_linea
from ..modelos import DocumentoLocal, LineaLocal, PaginaLocal, PalabraLocal, RegionLocal
from ..ocr.windows_media import MotorWindowsMediaOcr


VERSION_PYPDFIUM2_REQUERIDA = "5.12.1"


class BackendPdfium:
    id = "pypdfium2"
    version = VERSION_PYPDFIUM2_REQUERIDA

    def __init__(self) -> None:
        instalada = importlib.metadata.version("pypdfium2")
        if instalada != VERSION_PYPDFIUM2_REQUERIDA:
            raise RuntimeError(
                f"pypdfium2 incompatible: instalada={instalada}, requerida={VERSION_PYPDFIUM2_REQUERIDA}"
            )

    def cargar_pdf(self, ruta: str | Path) -> DocumentoLocal:
        path = Path(ruta)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        document = pdfium.PdfDocument(str(path))
        paginas: list[PaginaLocal] = []
        try:
            for index in range(len(document)):
                page = document[index]
                width, height = map(float, page.get_size())
                text_page = page.get_textpage()
                try:
                    text = text_page.get_text_range()
                    palabras = self._palabras(text_page, text, height, index + 1)
                finally:
                    text_page.close()
                    page.close()
                paginas.append(
                    PaginaLocal(
                        index + 1,
                        width,
                        height,
                        text,
                        palabras,
                        agrupar_por_linea(palabras),
                    )
                )
        finally:
            document.close()
        return DocumentoLocal(str(path), digest, paginas)

    @staticmethod
    def _palabras(text_page, text: str, height: float, page_number: int) -> list[PalabraLocal]:
        if len(text) != text_page.count_chars():
            raise ValueError("Texto y cajas de caracteres no estan alineados")
        palabras: list[PalabraLocal] = []
        start: int | None = None
        for index in range(len(text) + 1):
            char = text[index] if index < len(text) else " "
            if not char.isspace() and start is None:
                start = index
            if char.isspace() and start is not None:
                boxes = []
                for char_index in range(start, index):
                    try:
                        left, bottom, right, top = text_page.get_charbox(char_index)
                    except Exception:
                        continue
                    if right > left and top >= bottom:
                        boxes.append((left, height - top, right, height - bottom))
                if boxes:
                    palabras.append(
                        PalabraLocal(
                            text[start:index],
                            page_number,
                            RegionLocal(
                                min(b[0] for b in boxes),
                                min(b[1] for b in boxes),
                                max(b[2] for b in boxes),
                                max(b[3] for b in boxes),
                            ),
                            len(palabras),
                        )
                    )
                start = None
        return palabras


class BackendPdfiumConOcr(BackendPdfium):
    """Completa solo paginas sin texto mediante OCR local secundario."""

    id = "pypdfium2+windows-media-ocr"
    version = f"{VERSION_PYPDFIUM2_REQUERIDA}+ocr-1.0.0"
    render_scale = 1.35

    def __init__(self, ocr: MotorWindowsMediaOcr | None = None) -> None:
        super().__init__()
        self.ocr = ocr or MotorWindowsMediaOcr()

    def cargar_pdf(self, ruta: str | Path) -> DocumentoLocal:
        documento = super().cargar_pdf(ruta)
        pendientes = [pagina for pagina in documento.paginas if not pagina.texto.strip() and not pagina.palabras]
        if not pendientes:
            return documento
        pdf = pdfium.PdfDocument(str(ruta))
        hashes: list[str] = []
        try:
            for pagina in pendientes:
                page = pdf[pagina.numero - 1]
                try:
                    image = self._imagen_ocr(page, pagina.ancho, pagina.alto)
                finally:
                    page.close()
                resultado = self.ocr.reconocer_pagina(image, pagina.numero, pagina.ancho, pagina.alto)
                palabras = [
                    PalabraLocal(
                        word.texto, pagina.numero,
                        RegionLocal(word.bbox.x0, word.bbox.y0, word.bbox.x1, word.bbox.y1),
                        word.orden,
                    )
                    for word in resultado.palabras
                ]
                lineas = [
                    LineaLocal(pagina.numero, [palabras[word.orden] for word in line.palabras], line.orden)
                    for line in resultado.lineas
                ]
                pagina.texto = resultado.texto
                pagina.palabras = palabras
                pagina.lineas = lineas
                pagina.origen = "OCR_LOCAL"
                pagina.metadatos_ocr = {
                    "motor": resultado.motor,
                    "idioma": resultado.idioma,
                    "confidence_disponible": resultado.confidence_disponible,
                    "confidence": None,
                    "angulo_texto": resultado.angulo_texto,
                    "preprocesado": resultado.preprocesado,
                    "hash_ocr": resultado.hash_ocr,
                }
                hashes.append(resultado.hash_ocr)
        finally:
            pdf.close()
        documento.ocr = {
            "ejecutado": True,
            "fuente": "OCR_LOCAL_SECUNDARIO",
            "motor": self.ocr.id,
            "version": self.ocr.version,
            "idioma": self.ocr.idioma,
            "paginas": [pagina.metadatos_ocr for pagina in documento.paginas if pagina.origen == "OCR_LOCAL"],
            "hash_resultado": hashlib.sha256("".join(hashes).encode("ascii")).hexdigest(),
            "red": False,
        }
        return documento

    def _imagen_ocr(self, page, ancho: float, alto: float):
        candidatas = []
        for objeto in page.get_objects():
            if type(objeto).__name__ != "PdfImage":
                continue
            left, bottom, right, top = objeto.get_bounds()
            cobertura = max(0.0, right - left) * max(0.0, top - bottom) / (ancho * alto)
            if cobertura >= 0.8:
                px = objeto.get_px_size()
                candidatas.append((px[0] * px[1], objeto))
        if candidatas:
            objeto = max(candidatas, key=lambda item: item[0])[1]
            if objeto.get_filters() == ["DCTDecode"]:
                with Image.open(BytesIO(bytes(objeto.get_data()))) as image:
                    return image.convert("RGB").copy()
            bitmap = objeto.get_bitmap()
            try:
                return bitmap.to_pil().copy()
            finally:
                bitmap.close()
        bitmap = page.render(scale=self.render_scale)
        try:
            return bitmap.to_pil().copy()
        finally:
            bitmap.close()

    def refinar_ocr(self, documento: DocumentoLocal, solicitudes) -> None:
        if not solicitudes:
            return
        pdf = pdfium.PdfDocument(documento.ruta)
        lecturas = []
        try:
            imagenes = {}
            for solicitud in solicitudes:
                pagina = documento.paginas[solicitud.pagina - 1]
                if solicitud.pagina not in imagenes:
                    page = pdf[solicitud.pagina - 1]
                    try:
                        imagenes[solicitud.pagina] = self._imagen_ocr(page, pagina.ancho, pagina.alto)
                    finally:
                        page.close()
                lecturas.append(self.ocr.reconocer_region(
                    imagenes[solicitud.pagina], solicitud, pagina.ancho, pagina.alto,
                ))
        finally:
            pdf.close()
        documento.ocr["regiones"] = lecturas
        documento.ocr["hash_regiones"] = hashlib.sha256(
            "".join(item["hash_ocr"] for item in lecturas).encode("ascii")
        ).hexdigest()
