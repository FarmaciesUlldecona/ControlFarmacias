# Privacidad del motor local

`controlfarmacias-local-engine@0.5.0` procesa documentos exclusivamente en el equipo local. No contiene red, telemetría, analítica, cloud, autoactualización, OpenAI, Google ni Azure. PDF, texto, coordenadas, identificadores, importes, hashes, métricas y errores permanecen en el proceso o en destinos locales configurados explícitamente.

La dependencia PDF sigue siendo `pypdfium2==5.12.1`, encapsulada en `backend/pdfium.py`. Para PDFs sin texto, el backend OCR opcional usa `Windows.Media.Ocr` mediante una API propia y Pillow para raster temporal. El OCR es fuente documental secundaria, no autoridad: conserva literal, bbox, idioma, hash, preprocesado, confianza `null` cuando WinRT no la publica y provenance. Los adaptadores no reciben objetos WinRT. No se escriben rasterizaciones en Git.

El shadow está desactivado por defecto. Cuando se habilita expresamente, su salida es lateral, local y sin autoridad. Todos los adaptadores locales permanecen en shadow y `COFARES_LOCAL_AUTHORITY` permanece `False`.

Los PDFs, rasterizaciones y resultados OCR documentales reales son corpus local externo. Los tests de replay los detectan y hacen `skip` explícito cuando no están presentes; no deben incorporarse a Git.
