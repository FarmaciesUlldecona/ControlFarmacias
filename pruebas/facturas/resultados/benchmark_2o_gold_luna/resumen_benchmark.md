# Benchmark ciego gpt-5.6-luna

- Gold: commit `581150265d677fe94b03268c83802bb934825162`; abierto solo despu?s del hito ciego verificado.
- 14 PDF, 30 p?ginas, 14 llamadas v?lidas, sin reintentos v?lidos.
- Duracion acumulada de extraccion: 176.461 s (media 12.604357 s/PDF).
- Facturas: 18/18 identificadas; 18 detectadas.
- Multifaktura: 2/2 PDF detectados correctamente como multifaktura.
- Campos principales: 213/234 (91.03%); cobertura 97.01%.
- Fiscalidad por l?neas: 115/195 (58.97%).
- Albaranes: 19/337 n?meros correctos; 318 ausentes; 8 inventados.
- Movimientos comerciales: 25 gold; 0 coincidencias estrictas; schema sin representaci?n directa.
- Coste registrado congelado: 0.276150 USD (0.019725 USD/PDF).
- Coste recalculado con tarifa oficial consultada: 0.055230 USD (0.003945 USD/PDF).

## Nota metodologica aprobada por Pio

El pipeline original era unifactura. Antes de las llamadas Luna, Pio autorizo un adaptador multifaktura minimo, aislado y exclusivo del benchmark para 0..N facturas por PDF, sin conocimiento del gold ni de la cantidad esperada y sin modificar produccion. El intento inicial de `documento_01` recibio HTTP 401 por credencial invalida, sin extraccion, `response_id`, tokens ni resultado utilizable; Pio autorizo repetirlo tras corregir la credencial. Solo las 14 extracciones validas congeladas forman el benchmark, que Pio acepta como valido y conforme.

## Controles prioritarios

- Guimer? 624/743 sin vencimientos: {'624': True, '743': True}
- Delivery 504918055 no albar?n: False
- HEFAME sin inventar 80 EUR: True
- Alliance 08009278/08009279 conserva 0,02 en nota: {'08009278': {'esperada': True, 'preservada_en_nota_revision': False}, '08009279': {'esperada': True, 'preservada_en_nota_revision': False}}

## Resultado por PDF

| Documento | Gold/detectadas | Identificadas | Acierto campos | Albaranes correctos | Resultado |
|---|---:|---:|---:|---:|---|
| documento_01 | 3/3 | 3 | 100.0% | 0 | CORRECTO_CON_INCIDENCIAS |
| documento_02 | 1/1 | 1 | 84.62% | 2 | CORRECTO_CON_INCIDENCIAS |
| documento_03 | 1/1 | 1 | 92.31% | 0 | CORRECTO_CON_INCIDENCIAS |
| documento_04 | 1/1 | 1 | 92.31% | 0 | CORRECTO_CON_INCIDENCIAS |
| documento_05 | 1/1 | 1 | 100.0% | 1 | CORRECTO_CON_INCIDENCIAS |
| documento_06 | 1/1 | 1 | 92.31% | 0 | CORRECTO_CON_INCIDENCIAS |
| documento_07 | 1/1 | 1 | 92.31% | 0 | CORRECTO_CON_INCIDENCIAS |
| documento_08 | 1/1 | 1 | 61.54% | 0 | CORRECTO_CON_INCIDENCIAS |
| documento_09 | 3/3 | 3 | 92.31% | 0 | CORRECTO_CON_INCIDENCIAS |
| documento_10 | 1/1 | 1 | 100.0% | 12 | CORRECTO_CON_INCIDENCIAS |
| documento_11 | 1/1 | 1 | 100.0% | 1 | CORRECTO_CON_INCIDENCIAS |
| documento_12 | 1/1 | 1 | 69.23% | 0 | CORRECTO_CON_INCIDENCIAS |
| documento_13 | 1/1 | 1 | 100.0% | 2 | CORRECTO_CON_INCIDENCIAS |
| documento_14 | 1/1 | 1 | 76.92% | 1 | CORRECTO_CON_INCIDENCIAS |

Los valores completos, discrepancias e incidencias est?n en los JSON asociados. Los nombres reales se incorporan ?nicamente en evaluaci?n, despu?s del hito ciego.
