# Análisis forense de errores Baseline B (Luna V2)

Análisis exclusivamente local sobre salidas congeladas. Se reutilizaron `invoice_key`, `equal`, `match_invoices` y `match_list` de `comparativa_2o_gold_a_b_c/evaluar.py`.

## Reconciliación

- Albaranes: 337 gold, 170 correctos por clave, 167 ausentes y 5 inventados; cobertura 50,45%.
- Movimientos: 25 gold, 11 detectados por clave, 14 ausentes y 7 inventados; detección 44,00%.
- Campos: 214/251 correctos = 85,26%; cobertura (214+25)/251 = 95,22%; 25 valores erróneos, 12 ausencias y 13 invenciones.
- Fiscalidad: 89/90 atributos de tramos emparejados = 98,89%; además 8 tramos ausentes y 11 inventados fuera de ese denominador.

## Albaranes

Distribución exacta de los 167 ausentes: 08009278=0, 08009277=162, 08009279=0, 5450053457=0, 0563820041=0, VN2605-0005656=5, resto=0. Por proveedor: Alliance 162 (97,01%), FEDEFARMA 5 (2,99%), Cofares/HEFAME/resto 0.

Los cinco inventados del evaluador son `2620-2173388`, `2605-0221864`, `2605-0222046`, `2620-2217350` y `2605-0228056`. Todos corresponden, por orden/fecha/importe, a literales gold `P PA 2620-2173388`, `P RE 2605-0221864`, `P RE 2605-0222046`, `P PA 2620-2217350` y `P RE 2605-0228056`. Es un error demostrado de representación de clave compuesta; no hay evidencia de números base fabricados.

## Concentración y C

Alliance+Cofares+HEFAME+FEDEFARMA concentran 167/167 = 100,00% de ausentes; Alliance sola 162/167 = 97,01%. C recupera 162/167 (todos Alliance), mantiene 5 ausentes FEDEFARMA, corrige 0/5 inventados B por clave exacta e introduce 8 claves no coincidentes en las facturas con error B (3 Alliance y 5 FEDEFARMA).

## Duplicado

En B, la portada-resumen de `FEDE VTO 15.8.26 PIO.pdf` genera una cuarta salida sin número de factura por 409,58 EUR. Coincide exactamente con la suma de VN2605-0005656 (19,96), SI26-04567 (81,07) y VN26-0016742 (308,55). El evaluador la clasifica como inventada porque no existe clave gold nula. Es eliminable como agregado solo cuando concurren número nulo, rótulo de resumen/avisos, mismo proveedor/PDF y suma exacta; para facturas numeradas, proveedor+número es la clave y fecha+importe solo apoyan.

## Patrones y discrepancias

La omisión Alliance 08009277 es total (0/162) en páginas 5-9, no truncamiento a primeros N. Incluye 160 CARGO y 2 ABONO. Las tablas largas/multipágina son factor demostrado pero no suficiente: 08009278 obtiene 109/109 y HEFAME 12/12. FEDEFARMA falla por componentes P + PA/RE + número.

B omite las discrepancias Alliance de 0,02 EUR en 08009278/08009279 y conserva los totales fiscales. En HEFAME detecta dos diferencias literales de 110 EUR, pero no identifica los 80 EUR no explicados ni inventa un concepto compensatorio; conserva el total fiscal.

Los detalles completos están en los JSON específicos y la propuesta no implementada en `recomendacion_arquitectonica.md`.
