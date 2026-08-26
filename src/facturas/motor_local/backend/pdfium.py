from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path

import pypdfium2 as pdfium

from ..geometria.lineas import agrupar_por_linea
from ..modelos import DocumentoLocal, PaginaLocal, PalabraLocal, RegionLocal


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
