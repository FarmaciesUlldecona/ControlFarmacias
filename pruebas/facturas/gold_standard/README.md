# Segundo gold standard de facturas

Este directorio congela el segundo gold standard validado manualmente previamente por Pio.

- Fecha de congelación: 2026-08-13.
- Fuentes documentales: 14 PDF locales de pruebas/facturas/documentos/2o_gold_standard.
- Cobertura: 18 facturas/documentos económicos.
- Artefactos: 14 JSON documentales, indice.json y este README.md.

Los datos se transcribieron exclusivamente desde los PDF fuente. Los nombres de archivo no se utilizaron como evidencia de datos y no se usaron resultados previos, modelos externos, APIs de extracción, normalizadores, prompts ni patrones históricos. Todo dato no demostrable se representa como null o [], según corresponda.

FEDEFARMA contiene tres facturas; su primera página es un resumen y no una cuarta factura. ALLIANCE/CENCORA contiene tres facturas. Los albaranes y los movimientos comerciales se mantienen separados, y las diferencias documentales de conciliación se conservan sin corregir.

Cualquier benchmark posterior debe ejecutarse de forma ciega respecto de esta carpeta: no puede leerla ni usar su contenido para orientar extracción, normalización, prompts o lógica de producción.
