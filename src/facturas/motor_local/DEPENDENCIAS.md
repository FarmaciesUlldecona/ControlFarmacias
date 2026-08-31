# Dependencias del motor local

Runtime PDF fijado: `pypdfium2==5.12.1`.

El repositorio no presenta un manifiesto general de dependencias Python; el entorno existente del proyecto ya contiene exactamente esa version. El backend valida la version exacta al construirse y falla de forma explicita si difiere.

El OCR opcional para paginas sin texto usa `Windows.Media.Ocr`, componente local del sistema operativo sujeto a la licencia de Microsoft Windows. No se distribuyen ni descargan modelos. La integracion invoca PowerShell/WinRT sin red y requiere el reconocedor `es-ES` instalado.

La rasterizacion temporal usa `Pillow==12.3.0`, ya presente en el entorno, bajo licencia permisiva MIT-CMU segun el fichero `dist-info/licenses/LICENSE` instalado. Las imagenes temporales se crean fuera del repositorio versionado y se eliminan al terminar cada llamada.

No se añaden PyMuPDF, pdfplumber, Camelot, OpenCV, pandas, Tesseract, EasyOCR ni PaddleOCR. `pypdfium2` incluye el wrapper, bindings y `pypdfium2_raw/pdfium.dll`.

## Supply chain

- Version exacta y hashes del binario/metadatos registrados en los artefactos del hito.
- Instalacion o actualizacion siempre manual y fuera de la ejecucion productiva.
- Sin auto-update ni descargas durante el procesamiento.
- Cada futura actualizacion exige repetir auditoria de licencia, componentes, binarios, red, replay y tests.
