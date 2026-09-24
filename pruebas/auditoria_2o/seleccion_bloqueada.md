# Hito 2O — seleccion bloqueada antes de persistencia

No se ha seleccionado definitivamente ni persistido una tercera factura.
Busqueda: documentos productivos PIO sin factura persistida, cotejados por SHA binario con PDFs accesibles en pruebas/facturas/documentos; proveedor identificado por contenido PDF.
Se amplio la lectura a los 128 documentos productivos PIO sin factura persistida, utilizando sus copias locales o Storage. Sin errores de acceso ni discrepancias de SHA. Se identificaron por contenido diez PDF Alliance, todos multif factura (3 a 5 identidades); ninguno unitario. No se ejecutaron normalizaciones productivas de esos documentos.

## Candidatos encontrados

- Documento ffee3c1c-ebcc-4287-99b2-79ccbae45f22. SHA 7b806565a4f09e182c5ec9d75b40b959fd39c4af86da77b7a8cb745c6e1192b2. 11 paginas: 08009278 (1-4; 3824.59), 08009277 (5-9; 10111.55), 08009279 (10-11; 141.01).
- Documento fd5593a1-1021-42c5-9bf2-b5d7a88bc966. SHA 0795c8c6aa39389bd9c51713e52716bcc4d78462fd95bbca48e2c0077c58c573. 11 paginas: 08008428 (1-3; 2972.70), 08008427 (4-7; 11185.10), 08008429 (8-9; 219.24), 08008430 (10-11; 162.67).
- Ambos identificados por contenido como ALLIANCE HEALTHCARE ESPANA, S.A., NIF A50004324; destinatario PUIG SALOMON PIUS, NIF 40901058C.
- Adaptador alliance-local 1.0.0; documento_completo_demostrado=true para cada lote completo; incidencias globales vacias. Esto no constituye certificacion de un payload parcial.

## Motivo de no persistencia

El RPC cf_persistir_normalizacion (sql/migrations/12_cf_views_rls_rpc.sql) marca el documento completo NORMALIZADA y calcula cantidad_documentos_detectados/tipo_contenido a partir de todas las facturas del payload. El flujo inspeccionado no conserva un estado de lote parcialmente persistido.
Persistir el lote crearia 3 o 4 facturas; enviar solo una alteraria la representacion del PDF completo. No se ha cambiado el contrato ni recortado ningun PDF.

## Estado productivo observado

Facturas=2; normalizacion_ejecuciones=3; conciliaciones=3; detalles=6; movimientos=4; impuestos=5; vencimientos=2; incidencias=3; historial=8.
Logista y Cofares NORMALIZADA/CONCILIADA, 448.00 y 177.74, mismas conciliaciones actuales.
Flags false/false/false, farmacias [PIO], bloqueos activos 0, workers Windows 0.
Persistencias, claims y conciliaciones ejecutadas por este hito: 0. Sin acceso a Farmatic ni Luna.

Focales: 179 runtime/barreras + 92 Alliance = 271 passed.
Suite completa: 915 passed in 57.39s. Regresiones: 0.
Estado final: TERCER_PILOTO_CLAIM_V2_NO_EJECUTADO.

## Inventario Alliance por contenido

| Documento | Facturas documentales |
| --- | --- |
| 15a34707-b418-404b-ae09-1a8955b8f940 | 08010461, 08010462, 08010463, 08010464 |
| 3055503d-4685-4937-abab-7e5ac8cb43c3 | 08010085, 08010086, 08010087, 08010088 |
| 6dc84993-bedc-4f48-a138-b3abd9856708 | 08007499, 08007500, 08007501, 08007502 |
| 8595f722-868f-4ac8-a04c-ca13dbdc0b89 | 08010885, 08010886, 08010887, 08010888 |
| ae53897a-355a-488f-bc3e-1783f39e0f13 | 08007969, 08007970, 08007971, 08007972, 08007973 |
| c7c7ca6e-3b13-4fc4-b6ac-6c670ddf6e29 | 08009716, 08009717, 08009718, 08009719 |
| d99e9155-be2d-4b15-9468-bf73eba57278 | 08006568, 08006569, 08006570, 08006571 |
| ea467b3f-8b2b-42bc-b0b7-cffa34d1de2e | 08008834, 08008835, 08008836, 08008837 |
| fd5593a1-1021-42c5-9bf2-b5d7a88bc966 | 08008427, 08008428, 08008429, 08008430 |
| ffee3c1c-ebcc-4287-99b2-79ccbae45f22 | 08009277, 08009278, 08009279 |
