from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

from PIL import Image, ImageOps

from .modelos import BloqueOCR, LineaOCR, PaginaOCR, PalabraOCR, RegionOCR, SolicitudRegionOCR


class MotorWindowsMediaOcr:
    """API propia sobre Windows.Media.Ocr; no expone objetos WinRT."""

    id = "windows-media-ocr-local"
    version = "1.0.0"
    idioma = "es-ES"
    _bandas = (
        (0.00, 0.25, 0.00, 0.22),
        (0.15, 0.58, 0.22, 0.50),
        (0.42, 0.78, 0.50, 0.70),
        (0.62, 1.00, 0.70, 1.00),
    )

    def __init__(self, *, powershell: str = "powershell.exe", runner=None) -> None:
        self.powershell = powershell
        self._runner = runner or subprocess.run
        self.script = Path(__file__).with_name("windows_media_ocr.ps1")

    def reconocer_pagina(self, image: Image.Image, numero: int, ancho_pdf: float, alto_pdf: float) -> PaginaOCR:
        if os.name != "nt":
            raise RuntimeError("Windows.Media.Ocr solo esta disponible en Windows")
        base = image.convert("RGB")
        width, height = base.size
        lineas: list[LineaOCR] = []
        palabras: list[PalabraOCR] = []
        angles: list[float] = []
        with tempfile.TemporaryDirectory(prefix="controlfarmacias_ocr_") as temp:
            for band_index, (crop_y0, crop_y1, keep_y0, keep_y1) in enumerate(self._bandas):
                top, bottom = round(height * crop_y0), round(height * crop_y1)
                crop = base.crop((0, top, width, bottom))
                scale = 3
                resized = crop.resize((crop.width * scale, crop.height * scale))
                image_path = Path(temp) / f"page_{numero}_band_{band_index}.png"
                resized.save(image_path)
                raw = self._ejecutar(image_path)
                if raw.get("text_angle") is not None:
                    angles.append(float(raw["text_angle"]))
                for raw_line in raw.get("lines", []):
                    line_words: list[PalabraOCR] = []
                    for raw_word in raw_line.get("words", []):
                        center_y = (top + (float(raw_word["y"]) + float(raw_word["height"]) / 2) / scale) / height
                        if not (keep_y0 <= center_y < keep_y1 or keep_y1 == 1.0 and center_y <= 1.0):
                            continue
                        x0 = float(raw_word["x"]) / scale / width * ancho_pdf
                        y0 = (top + float(raw_word["y"]) / scale) / height * alto_pdf
                        x1 = (float(raw_word["x"]) + float(raw_word["width"])) / scale / width * ancho_pdf
                        y1 = (top + (float(raw_word["y"]) + float(raw_word["height"])) / scale) / height * alto_pdf
                        word = PalabraOCR(
                            str(raw_word["text"]), RegionOCR(x0, y0, x1, y1),
                            len(palabras), raw_word.get("confidence"),
                        )
                        palabras.append(word)
                        line_words.append(word)
                    if line_words:
                        lineas.append(LineaOCR(" ".join(w.texto for w in line_words), tuple(line_words), len(lineas) + 1))
        texto = "\n".join(linea.texto for linea in lineas)
        payload = {
            "numero": numero,
            "texto": texto,
            "palabras": [(w.texto, asdict(w.bbox), w.confidence) for w in palabras],
            "motor": self.id,
            "version": self.version,
            "idioma": self.idioma,
            "preprocesado": "BANDAS_SOLAPADAS_ESCALA_3_PILLOW_DEFAULT",
        }
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        bbox = RegionOCR(0.0, 0.0, ancho_pdf, alto_pdf)
        bloques = (BloqueOCR(tuple(lineas), bbox, 1),) if lineas else ()
        return PaginaOCR(
            numero, ancho_pdf, alto_pdf, texto, tuple(palabras), tuple(lineas), bloques,
            digest, self.id, self.idioma, False,
            round(sum(angles) / len(angles), 6) if angles else None,
            {
                "render_base": "PDFIUM_97_2_DPI",
                "estrategia": "BANDAS_SOLAPADAS",
                "factor_refinamiento": 3,
                "original_preservado": True,
            },
        )

    def _ejecutar(self, image_path: Path) -> dict:
        completed = self._runner(
            [
                self.powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(self.script), "-ImagePath", str(image_path.resolve()),
                "-LanguageTag", self.idioma,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(completed.stdout.lstrip("\ufeff"))

    def reconocer_region(
        self, image: Image.Image, solicitud: SolicitudRegionOCR,
        ancho_pdf: float, alto_pdf: float,
    ) -> dict:
        width, height = image.size
        box = (
            round(solicitud.bbox.x0 / ancho_pdf * width),
            round(solicitud.bbox.y0 / alto_pdf * height),
            round(solicitud.bbox.x1 / ancho_pdf * width),
            round(solicitud.bbox.y1 / alto_pdf * height),
        )
        crop = image.crop(box)
        if solicitud.escala_grises:
            crop = ImageOps.autocontrast(ImageOps.grayscale(crop))
        crop = crop.resize((crop.width * solicitud.escala, crop.height * solicitud.escala))
        with tempfile.TemporaryDirectory(prefix="controlfarmacias_ocr_region_") as temp:
            path = Path(temp) / "region.png"
            crop.save(path)
            raw = self._ejecutar(path)
        texto = "\n".join(line.get("text", "") for line in raw.get("lines", []))
        digest = hashlib.sha256(json.dumps({
            "id": solicitud.id, "bbox": asdict(solicitud.bbox), "texto": texto,
            "motor": self.id, "idioma": raw.get("language"),
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return {
            "id": solicitud.id,
            "pagina": solicitud.pagina,
            "bbox": [solicitud.bbox.x0, solicitud.bbox.y0, solicitud.bbox.x1, solicitud.bbox.y1],
            "texto": texto,
            "lineas": raw.get("lines", []),
            "confidence": None,
            "confidence_disponible": False,
            "hash_ocr": digest,
            "provenance": {
                "motor": self.id, "version": self.version, "idioma": self.idioma,
                "preprocesado": {
                    "escala": solicitud.escala, "escala_grises": solicitud.escala_grises,
                    "autocontraste": solicitud.escala_grises, "original_preservado": True,
                },
                "fuente": "OCR_LOCAL_SECUNDARIO", "gold_usado": False, "red": False,
            },
        }
