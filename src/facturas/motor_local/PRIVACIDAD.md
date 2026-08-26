# Privacidad del motor local

`controlfarmacias-local-engine@0.4.0` procesa documentos exclusivamente en el equipo local. No contiene red, telemetría, analítica, cloud, autoactualización, OpenAI, Google, Azure ni OCR. PDF, texto, coordenadas, identificadores, importes, hashes, métricas y errores permanecen en el proceso o en destinos locales configurados explícitamente.

La única dependencia PDF del runtime es `pypdfium2==5.12.1`, encapsulada en `backend/pdfium.py`. La geometría, segmentación, evidencia, reglas, consolidación, matcher y simulación pertenecen a ControlFarmacias.

El shadow está desactivado por defecto. Cuando se habilita expresamente, su salida es lateral, local y sin autoridad. HEFAME permanece en shadow y `COFARES_LOCAL_AUTHORITY` permanece `False`. Las rutas externas existentes del programa están separadas y este paquete no las importa ni las llama.

Los PDFs y resultados documentales reales son corpus local externo. Los tests de replay los detectan y hacen `skip` explícito cuando no están presentes; no deben incorporarse a Git.
