# Dependencias del motor local

Runtime PDF fijado: `pypdfium2==5.12.1`.

El repositorio no presenta un manifiesto general de dependencias Python; el entorno existente del proyecto ya contiene exactamente esa version. Para evitar crear un segundo mecanismo, este hito no instala paquetes ni introduce un gestor alternativo. El backend valida la version exacta al construirse y falla de forma explicita si difiere.

No se añaden PyMuPDF, pdfplumber, Camelot, OpenCV, pandas ni herramientas OCR. `pypdfium2` no declara dependencias Python obligatorias (`Requires-Dist` vacio) en la distribucion Windows instalada. Incluye el wrapper, bindings y `pypdfium2_raw/pdfium.dll`.

## Supply chain

- Version exacta y hashes del binario/metadatos registrados en los artefactos del hito.
- Instalacion o actualizacion siempre manual y fuera de la ejecucion productiva.
- Sin auto-update ni descargas durante el procesamiento.
- Cada futura actualizacion exige repetir auditoria de licencia, componentes, binarios, red, replay y tests.
