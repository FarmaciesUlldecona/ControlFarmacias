"""Inspeccion local y render temporal de las paginas 5-9 del PDF Alliance."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pypdfium2 as pdfium

from src.facturas.motor_local.backend.pdfium import BackendPdfium


PDF = ROOT / "pruebas/facturas/documentos/2o_gold_standard/ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf"
OUT = ROOT / "tmp/pdfs/2u_08009277"
CODIGOS = ("08P10588", "08C61794", "08P10623", "08Z34777")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    documento = BackendPdfium().cargar_pdf(PDF)
    hallazgos = {}
    for codigo in CODIGOS:
        encontrados = []
        for pagina in documento.paginas[4:9]:
            for indice, linea in enumerate(pagina.lineas):
                if codigo not in linea.texto:
                    continue
                encontrados.append({
                    "pagina_pdf": pagina.numero,
                    "linea_indice_cero": indice,
                    "fila_literal": linea.texto,
                    "bbox_fila": linea.bbox.to_list(),
                    "palabras": [
                        {"texto": palabra.texto, "bbox": palabra.bbox.to_list()}
                        for palabra in linea.palabras
                    ],
                    "contexto": [
                        {"indice": contexto_indice, "texto": pagina.lineas[contexto_indice].texto}
                        for contexto_indice in range(max(0, indice - 4), min(len(pagina.lineas), indice + 5))
                    ],
                })
        hallazgos[codigo] = encontrados

    pdf = pdfium.PdfDocument(str(PDF))
    try:
        for numero in range(5, 10):
            page = pdf[numero - 1]
            try:
                bitmap = page.render(scale=2.5)
                try:
                    bitmap.to_pil().save(OUT / f"pagina_{numero}.png")
                finally:
                    bitmap.close()
            finally:
                page.close()
    finally:
        pdf.close()

    print(json.dumps({
        "pdf_sha256": documento.sha_documento,
        "hallazgos": hallazgos,
        "renders": [str(OUT / f"pagina_{numero}.png") for numero in range(5, 10)],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
