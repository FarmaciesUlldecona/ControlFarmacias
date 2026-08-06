# Analisis de tablas literales - Alliance 08008427

## Alcance

Comparacion local de la transcripcion literal con las paginas originales 4-7 del PDF y con la factura `08008427` del patron. Las paginas de la extraccion son relativas 1-4. Las fechas visibles DD-MM-YYYY se aceptan como correctas y no se transforman en el resultado.

## Resumen

| Metrica | Resultado |
|---|---:|
| Tablas detectadas | 6 |
| Filas totales | 156 |
| Filas de albaran esperadas / encontradas | 147 / 147 |
| Filas literales completas | 147 |
| Filas literales parciales | 0 |
| Filas incorrectas | 0 |
| Filas ausentes | 0 |
| Filas inventadas | 0 |
| Porcentaje completamente correcto | 100.00 % |
| Coste real | 0.052392 USD |

## Inventario de las seis tablas

| Tabla | Pagina relativa/original | Titulo | Encabezados | Filas | Celdas por fila | Contenido |
|---:|---|---|---|---:|---|---|
| 1 | 1 / 4 | COMPRAS | CONCEPTO; BASE IMPONIBLE; IVA; R.E.; TOTALES | 6 | [11, 11, 11, 11, 12, 11] | resumen_fiscal_y_compras |
| 2 | 1 / 4 | GASTOS | CONCEPTO; BASE IMPONIBLE; IVA; TOTALES | 3 | [8, 9, 9] | servicio_basico_y_otros_gastos |
| 3 | 2 / 5 | CARGOS | FECHA; TIPO DE PEDIDO; NÚMERO ALBARÁN; TOTAL BASE; TOTAL ALBARÁN | 50 | [5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5] | albaranes |
| 4 | 2 / 5 | ABONOS | FECHA; TIPO DE PEDIDO; NÚMERO ALBARÁN; TOTAL BASE; TOTAL ALBARÁN | 2 | [5, 5] | albaranes |
| 5 | 3 / 6 | CARGOS | FECHA; TIPO DE PEDIDO; NÚMERO ALBARÁN; TOTAL BASE; TOTAL ALBARÁN | 50 | [5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5] | albaranes |
| 6 | 4 / 7 | CARGOS | FECHA; TIPO DE PEDIDO; NÚMERO ALBARÁN; TOTAL BASE; TOTAL ALBARÁN | 45 | [5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5] | albaranes |

Las tablas 3-6 contienen albaranes. La tabla 1 contiene el resumen de compras y desglose fiscal; la tabla 2 contiene GASTOS y Servicio basico. El vencimiento es un bloque separado, no una tabla.

## Albaranes

| Columna o propiedad | Porcentaje correcto |
|---|---:|
| numero_albaran | 100.00 % |
| fecha | 100.00 % |
| descripcion | 100.00 % |
| base | 100.00 % |
| total | 100.00 % |
| signo_base | 100.00 % |
| signo_total | 100.00 % |
| pagina | 100.00 % |
| posicion_fisica | 100.00 % |

Los 147 numeros, fechas visibles, descripciones, bases, totales y signos coinciden. No hay duplicados, filas ausentes, filas inventadas, subtotales usados como albaranes ni filas partidas entre paginas. Todas las tablas de albaranes conservan cinco celdas por fila sin desplazamientos.

Los abonos `08C38230` y `08C38231` aparecen correctamente en la pagina relativa 2, como filas visuales 1 y 2 de la tabla ABONOS situada a la derecha de CARGOS. El orden 2 y 4 del patron es logico, no una secuencia fisica lineal del PDF; mantener una tabla ABONOS separada conserva mejor la geometria fuente.

## Incidencias estructurales fuera de los albaranes

- Las tablas COMPRAS y GASTOS repiten sus subencabezados como primera fila, aunque ya existen en `encabezados`.
- La fila NO ESPECIALIDAD tiene 12 celdas frente a 11 en las demas filas de COMPRAS: hay una celda vacia adicional que desplaza columnas.
- SERVICIO BASICO y TOTAL GASTOS tienen 9 celdas frente a las 8 columnas del encabezado expandido: aparece una celda vacia adicional antes de 5,46.
- No se detectaron estas anomalías en las cuatro tablas de albaranes.

## Vencimiento

La fecha `06-10-2026` esta transcrita literalmente y en la pagina relativa 1. `texto_importe` es null. Visualmente, el bloque FECHA VENCIMIENTO solo contiene la fecha; el total `11.185,10` pertenece a otro bloque. Sin una regla posterior no puede afirmarse que ambos formen el mismo bloque. Resultado: PARCIAL.

## Ajustes

Los dos `textos_ajustes` reproducen lineas visibles de R.D./RDL/DEDUCCION y no son inventados, pero ninguno contiene `SERVICIO BASICO` ni `31,46`. Servicio basico si esta localizado de forma literal en la tabla 2, fila 2, con base `26,00`, cuota `5,46` y total `31,46`. El primer texto es ajeno al ajuste esperado y el segundo corresponde a deducciones visibles.

## Fiscalidad

`textos_fiscales` esta vacio porque el modelo incluyo el desglose fiscal dentro de COMPRAS y GASTOS. La tabla 1 conserva bases, tipos de IVA, cuotas, tipos de recargo y cuotas; la tabla 2 conserva Servicio basico. Sin embargo, los totales finales `10.531,42`, `573,16`, `80,52` y `11.185,10` no quedaron ni en `textos_fiscales` ni en una tabla, por lo que la transcripcion fiscal no es completa.

## Comparacion uno a uno de los 147 albaranes

| Orden patron | Numero | Tabla | Pagina relativa | Fila visual | Fecha | Descripcion | Base | Total | Clasificacion |
|---:|---|---:|---:|---:|---|---|---:|---:|---|
| 1 | 08C26499 | 3 | 2 | 1 | 30-06-2026 | NORMAL ACUSTICO | 1,62 | 1,69 | FILA_LITERAL_COMPLETA |
| 2 | 08C38230 | 4 | 2 | 1 | 10-07-2026 | ABONOS AGRUPADOS | 8,29- | 8,66- | FILA_LITERAL_COMPLETA |
| 3 | 08C26500 | 3 | 2 | 2 | 30-06-2026 | NORMAL ACUSTICO | 1,26 | 1,32 | FILA_LITERAL_COMPLETA |
| 4 | 08C38231 | 4 | 2 | 2 | 10-07-2026 | ABONOS AGRUPADOS | 34,54- | 36,09- | FILA_LITERAL_COMPLETA |
| 5 | 08C27035 | 3 | 2 | 3 | 01-07-2026 | NORMAL ACUSTICO | 116,87 | 127,77 | FILA_LITERAL_COMPLETA |
| 6 | 08C27265 | 3 | 2 | 4 | 01-07-2026 | NORMAL ACUSTICO | 733,36 | 775,24 | FILA_LITERAL_COMPLETA |
| 7 | 08C27268 | 3 | 2 | 5 | 01-07-2026 | NORMAL ACUSTICO | 37,76 | 39,46 | FILA_LITERAL_COMPLETA |
| 8 | 08C27311 | 3 | 2 | 6 | 01-07-2026 | NORMAL ACUSTICO | 4,13 | 4,32 | FILA_LITERAL_COMPLETA |
| 9 | 08C27437 | 3 | 2 | 7 | 01-07-2026 | NORMAL ACUSTICO | 3,36 | 3,51 | FILA_LITERAL_COMPLETA |
| 10 | 08C27700 | 3 | 2 | 8 | 01-07-2026 | NORMAL ACUSTICO | 103,88 | 115,72 | FILA_LITERAL_COMPLETA |
| 11 | 08C27725 | 3 | 2 | 9 | 01-07-2026 | NORMAL ACUSTICO | 33,87 | 37,73 | FILA_LITERAL_COMPLETA |
| 12 | 08C27896 | 3 | 2 | 10 | 01-07-2026 | NORMAL ACUSTICO | 15,03 | 15,71 | FILA_LITERAL_COMPLETA |
| 13 | 08C27900 | 3 | 2 | 11 | 01-07-2026 | NETOS PLUS | 8,48 | 10,70 | FILA_LITERAL_COMPLETA |
| 14 | 08M29400 | 3 | 2 | 12 | 01-07-2026 | NORMAL ACUSTICO | 39,71 | 41,50 | FILA_LITERAL_COMPLETA |
| 15 | 08M29624 | 3 | 2 | 13 | 01-07-2026 | NORMAL ACUSTICO | 52,29 | 58,25 | FILA_LITERAL_COMPLETA |
| 16 | 08M29915 | 3 | 2 | 14 | 01-07-2026 | NORMAL ACUSTICO | 61,99 | 64,78 | FILA_LITERAL_COMPLETA |
| 17 | 08M29918 | 3 | 2 | 15 | 01-07-2026 | NETOS PLUS | 7,59 | 9,57 | FILA_LITERAL_COMPLETA |
| 18 | 08M29976 | 3 | 2 | 16 | 01-07-2026 | NORMAL ACUSTICO | 8,70 | 9,09 | FILA_LITERAL_COMPLETA |
| 19 | 08M30003 | 3 | 2 | 17 | 01-07-2026 | NORMAL ACUSTICO | 4,70 | 4,91 | FILA_LITERAL_COMPLETA |
| 20 | 08M30063 | 3 | 2 | 18 | 01-07-2026 | NORMAL ACUSTICO | 14,27 | 14,91 | FILA_LITERAL_COMPLETA |
| 21 | 08C28370 | 3 | 2 | 19 | 02-07-2026 | NORMAL ACUSTICO | 343,97 | 362,80 | FILA_LITERAL_COMPLETA |
| 22 | 08C28452 | 3 | 2 | 20 | 02-07-2026 | NORMAL ACUSTICO | 4,42 | 4,62 | FILA_LITERAL_COMPLETA |
| 23 | 08C28650 | 3 | 2 | 21 | 02-07-2026 | NORMAL ACUSTICO | 147,38 | 154,02 | FILA_LITERAL_COMPLETA |
| 24 | 08C28658 | 3 | 2 | 22 | 02-07-2026 | NETOS PLUS | 7,65 | 9,44 | FILA_LITERAL_COMPLETA |
| 25 | 08C28814 | 3 | 2 | 23 | 02-07-2026 | NORMAL ACUSTICO | 4,25 | 4,44 | FILA_LITERAL_COMPLETA |
| 26 | 08C29133 | 3 | 2 | 24 | 02-07-2026 | NORMAL ACUSTICO | 24,73 | 25,84 | FILA_LITERAL_COMPLETA |
| 27 | 08C29302 | 3 | 2 | 25 | 02-07-2026 | NORMAL ACUSTICO | 27,89 | 29,15 | FILA_LITERAL_COMPLETA |
| 28 | 08M30406 | 3 | 2 | 26 | 02-07-2026 | NORMAL ACUSTICO | 3,03 | 3,17 | FILA_LITERAL_COMPLETA |
| 29 | 08M30761 | 3 | 2 | 27 | 02-07-2026 | NORMAL ACUSTICO | 18,55 | 19,38 | FILA_LITERAL_COMPLETA |
| 30 | 08M30914 | 3 | 2 | 28 | 02-07-2026 | NORMAL ACUSTICO | 161,14 | 168,40 | FILA_LITERAL_COMPLETA |
| 31 | 08M30924 | 3 | 2 | 29 | 02-07-2026 | NORMAL ACUSTICO | 2,12 | 2,21 | FILA_LITERAL_COMPLETA |
| 32 | 08C29766 | 3 | 2 | 30 | 03-07-2026 | NORMAL ACUSTICO | 9,25 | 9,67 | FILA_LITERAL_COMPLETA |
| 33 | 08C29780 | 3 | 2 | 31 | 03-07-2026 | NORMAL ACUSTICO | 213,22 | 223,46 | FILA_LITERAL_COMPLETA |
| 34 | 08C29977 | 3 | 2 | 32 | 03-07-2026 | NORMAL ACUSTICO | 256,39 | 268,17 | FILA_LITERAL_COMPLETA |
| 35 | 08C29988 | 3 | 2 | 33 | 03-07-2026 | NETOS PLUS | 11,73 | 13,06 | FILA_LITERAL_COMPLETA |
| 36 | 08C29989 | 3 | 2 | 34 | 03-07-2026 | NORMAL ACUSTICO | 1,26 | 1,32 | FILA_LITERAL_COMPLETA |
| 37 | 08C30585 | 3 | 2 | 35 | 03-07-2026 | NORMAL ACUSTICO | 5,75 | 6,01 | FILA_LITERAL_COMPLETA |
| 38 | 08M31275 | 3 | 2 | 36 | 03-07-2026 | NORMAL ACUSTICO | 55,54 | 61,87 | FILA_LITERAL_COMPLETA |
| 39 | 08M31303 | 3 | 2 | 37 | 03-07-2026 | NORMAL ACUSTICO | 9,57 | 12,08 | FILA_LITERAL_COMPLETA |
| 40 | 08M31366 | 3 | 2 | 38 | 03-07-2026 | NORMAL ACUSTICO | 1,40 | 1,56 | FILA_LITERAL_COMPLETA |
| 41 | 08M31836 | 3 | 2 | 39 | 03-07-2026 | NORMAL ACUSTICO | 67,53 | 70,78 | FILA_LITERAL_COMPLETA |
| 42 | 08M31892 | 3 | 2 | 40 | 03-07-2026 | NORMAL ACUSTICO | 18,39 | 19,22 | FILA_LITERAL_COMPLETA |
| 43 | 08M31914 | 3 | 2 | 41 | 03-07-2026 | NORMAL ACUSTICO | 31,16 | 32,57 | FILA_LITERAL_COMPLETA |
| 44 | 08C30750 | 3 | 2 | 42 | 04-07-2026 | NORMAL ACUSTICO | 13,96 | 15,56 | FILA_LITERAL_COMPLETA |
| 45 | 08C30762 | 3 | 2 | 43 | 04-07-2026 | NORMAL ACUSTICO | 9,43 | 10,50 | FILA_LITERAL_COMPLETA |
| 46 | 08C30798 | 3 | 2 | 44 | 04-07-2026 | NETOS PLUS | 12,02 | 15,17 | FILA_LITERAL_COMPLETA |
| 47 | 08C30821 | 3 | 2 | 45 | 04-07-2026 | NORMAL ACUSTICO | 11,46 | 11,98 | FILA_LITERAL_COMPLETA |
| 48 | 08C30958 | 3 | 2 | 46 | 04-07-2026 | NORMAL ACUSTICO | 9,64 | 10,73 | FILA_LITERAL_COMPLETA |
| 49 | 08C31034 | 3 | 2 | 47 | 04-07-2026 | NORMAL ACUSTICO | 1,62 | 1,69 | FILA_LITERAL_COMPLETA |
| 50 | 08C31135 | 3 | 2 | 48 | 04-07-2026 | NORMAL ACUSTICO | 1,78 | 1,86 | FILA_LITERAL_COMPLETA |
| 51 | 08C31297 | 3 | 2 | 49 | 04-07-2026 | NORMAL ACUSTICO | 2,16 | 2,26 | FILA_LITERAL_COMPLETA |
| 52 | 08C31301 | 3 | 2 | 50 | 04-07-2026 | NORMAL ACUSTICO | 301,99 | 318,74 | FILA_LITERAL_COMPLETA |
| 53 | 08C31302 | 5 | 3 | 1 | 04-07-2026 | NORMAL ACUSTICO | 1,64 | 1,72 | FILA_LITERAL_COMPLETA |
| 54 | 08C31489 | 5 | 3 | 2 | 04-07-2026 | NORMAL ACUSTICO | 197,13 | 206,01 | FILA_LITERAL_COMPLETA |
| 55 | 08M32051 | 5 | 3 | 3 | 04-07-2026 | NORMAL ACUSTICO | 85,88 | 89,75 | FILA_LITERAL_COMPLETA |
| 56 | 08V19185 | 5 | 3 | 4 | 04-07-2026 | NORMAL ACUSTICO | 6,99 | 8,82 | FILA_LITERAL_COMPLETA |
| 57 | 08C31638 | 5 | 3 | 5 | 05-07-2026 | NORMAL ACUSTICO | 57,47 | 60,06 | FILA_LITERAL_COMPLETA |
| 58 | 08C32023 | 5 | 3 | 6 | 06-07-2026 | NORMAL ACUSTICO | 168,48 | 176,06 | FILA_LITERAL_COMPLETA |
| 59 | 08C32131 | 5 | 3 | 7 | 06-07-2026 | NORMAL ACUSTICO | 228,27 | 238,54 | FILA_LITERAL_COMPLETA |
| 60 | 08C32157 | 5 | 3 | 8 | 06-07-2026 | NORMAL ACUSTICO | 10,99 | 11,48 | FILA_LITERAL_COMPLETA |
| 61 | 08C32269 | 5 | 3 | 9 | 06-07-2026 | NORMAL ACUSTICO | 32,78 | 34,25 | FILA_LITERAL_COMPLETA |
| 62 | 08C32270 | 5 | 3 | 10 | 06-07-2026 | NORMAL ACUSTICO | 16,39 | 17,13 | FILA_LITERAL_COMPLETA |
| 63 | 08C32342 | 5 | 3 | 11 | 06-07-2026 | NORMAL ACUSTICO | 6,14 | 6,42 | FILA_LITERAL_COMPLETA |
| 64 | 08C32348 | 5 | 3 | 12 | 06-07-2026 | NORMAL ACUSTICO | 711,47 | 743,49 | FILA_LITERAL_COMPLETA |
| 65 | 08C32355 | 5 | 3 | 13 | 06-07-2026 | NETOS PLUS | 13,40 | 15,21 | FILA_LITERAL_COMPLETA |
| 66 | 08C32356 | 5 | 3 | 14 | 06-07-2026 | NORMAL ACUSTICO | 1,35 | 1,41 | FILA_LITERAL_COMPLETA |
| 67 | 08C32802 | 5 | 3 | 15 | 06-07-2026 | NORMAL ACUSTICO | 151,51 | 168,78 | FILA_LITERAL_COMPLETA |
| 68 | 08C32805 | 5 | 3 | 16 | 06-07-2026 | NORMAL ACUSTICO | 24,74 | 27,56 | FILA_LITERAL_COMPLETA |
| 69 | 08C32806 | 5 | 3 | 17 | 06-07-2026 | NORMAL ACUSTICO | 65,54 | 68,49 | FILA_LITERAL_COMPLETA |
| 70 | 08C32824 | 5 | 3 | 18 | 06-07-2026 | NORMAL ACUSTICO | 34,50 | 38,43 | FILA_LITERAL_COMPLETA |
| 71 | 08C32854 | 5 | 3 | 19 | 06-07-2026 | NORMAL ACUSTICO | 5,33 | 5,57 | FILA_LITERAL_COMPLETA |
| 72 | 08C32877 | 5 | 3 | 20 | 06-07-2026 | NORMAL ACUSTICO | 4,85 | 5,06 | FILA_LITERAL_COMPLETA |
| 73 | 08C32878 | 5 | 3 | 21 | 06-07-2026 | NORMAL ACUSTICO | 9,70 | 10,14 | FILA_LITERAL_COMPLETA |
| 74 | 08C33027 | 5 | 3 | 22 | 06-07-2026 | NORMAL ACUSTICO | 6,45 | 6,74 | FILA_LITERAL_COMPLETA |
| 75 | 08M32213 | 5 | 3 | 23 | 06-07-2026 | NORMAL ACUSTICO | 42,94 | 44,87 | FILA_LITERAL_COMPLETA |
| 76 | 08M32226 | 5 | 3 | 24 | 06-07-2026 | NORMAL ACUSTICO | 18,82 | 19,66 | FILA_LITERAL_COMPLETA |
| 77 | 08M32414 | 5 | 3 | 25 | 06-07-2026 | NORMAL ACUSTICO | 35,98 | 37,60 | FILA_LITERAL_COMPLETA |
| 78 | 08M32604 | 5 | 3 | 26 | 06-07-2026 | NORMAL ACUSTICO | 99,61 | 104,09 | FILA_LITERAL_COMPLETA |
| 79 | 08M32607 | 5 | 3 | 27 | 06-07-2026 | NORMAL ACUSTICO | 55,54 | 61,87 | FILA_LITERAL_COMPLETA |
| 80 | 08M32612 | 5 | 3 | 28 | 06-07-2026 | NORMAL ACUSTICO | 0,85 | 0,88 | FILA_LITERAL_COMPLETA |
| 81 | 08M32962 | 5 | 3 | 29 | 06-07-2026 | NORMAL ACUSTICO | 185,95 | 196,38 | FILA_LITERAL_COMPLETA |
| 82 | 08M32963 | 5 | 3 | 30 | 06-07-2026 | NETOS PLUS | 7,17 | 9,05 | FILA_LITERAL_COMPLETA |
| 83 | 08M32977 | 5 | 3 | 31 | 06-07-2026 | NORMAL ACUSTICO | 34,78 | 36,34 | FILA_LITERAL_COMPLETA |
| 84 | 08V19262 | 5 | 3 | 32 | 06-07-2026 | NORMAL ACUSTICO | 6,99 | 8,82 | FILA_LITERAL_COMPLETA |
| 85 | 08C33364 | 5 | 3 | 33 | 07-07-2026 | NORMAL ACUSTICO | 92,94 | 103,53 | FILA_LITERAL_COMPLETA |
| 86 | 08C33510 | 5 | 3 | 34 | 07-07-2026 | NORMAL ACUSTICO | 34,98 | 38,62 | FILA_LITERAL_COMPLETA |
| 87 | 08C33655 | 5 | 3 | 35 | 07-07-2026 | NORMAL ACUSTICO | 10,84 | 11,32 | FILA_LITERAL_COMPLETA |
| 88 | 08C33660 | 5 | 3 | 36 | 07-07-2026 | NORMAL ACUSTICO | 504,67 | 533,10 | FILA_LITERAL_COMPLETA |
| 89 | 08C33667 | 5 | 3 | 37 | 07-07-2026 | NETOS PLUS | 18,79 | 21,92 | FILA_LITERAL_COMPLETA |
| 90 | 08C33697 | 5 | 3 | 38 | 07-07-2026 | NORMAL ACUSTICO | 161,55 | 168,82 | FILA_LITERAL_COMPLETA |
| 91 | 08C34216 | 5 | 3 | 39 | 07-07-2026 | NORMAL ACUSTICO | 2,43 | 2,54 | FILA_LITERAL_COMPLETA |
| 92 | 08C34434 | 5 | 3 | 40 | 07-07-2026 | NORMAL ACUSTICO | 133,85 | 139,87 | FILA_LITERAL_COMPLETA |
| 93 | 08C34451 | 5 | 3 | 41 | 07-07-2026 | NORMAL ACUSTICO | 6,41 | 6,70 | FILA_LITERAL_COMPLETA |
| 94 | 08M33392 | 5 | 3 | 42 | 07-07-2026 | NORMAL ACUSTICO | 128,22 | 142,77 | FILA_LITERAL_COMPLETA |
| 95 | 08M33628 | 5 | 3 | 43 | 07-07-2026 | NORMAL ACUSTICO | 169,67 | 177,31 | FILA_LITERAL_COMPLETA |
| 96 | 08M33646 | 5 | 3 | 44 | 07-07-2026 | NORMAL ACUSTICO | 63,68 | 70,94 | FILA_LITERAL_COMPLETA |
| 97 | 08M33656 | 5 | 3 | 45 | 07-07-2026 | NORMAL ACUSTICO | 25,82 | 28,76 | FILA_LITERAL_COMPLETA |
| 98 | 08M33699 | 5 | 3 | 46 | 07-07-2026 | NORMAL ACUSTICO | 102,17 | 106,77 | FILA_LITERAL_COMPLETA |
| 99 | 08M33871 | 5 | 3 | 47 | 07-07-2026 | NORMAL ACUSTICO | 10,76 | 13,58 | FILA_LITERAL_COMPLETA |
| 100 | 08M33960 | 5 | 3 | 48 | 07-07-2026 | NORMAL ACUSTICO | 349,70 | 366,12 | FILA_LITERAL_COMPLETA |
| 101 | 08M33962 | 5 | 3 | 49 | 07-07-2026 | NETOS PLUS | 11,82 | 13,17 | FILA_LITERAL_COMPLETA |
| 102 | 08M34050 | 5 | 3 | 50 | 07-07-2026 | NORMAL ACUSTICO | 1,83 | 1,91 | FILA_LITERAL_COMPLETA |
| 103 | 08C34793 | 6 | 4 | 1 | 08-07-2026 | NORMAL ACUSTICO | 297,55 | 314,75 | FILA_LITERAL_COMPLETA |
| 104 | 08C34914 | 6 | 4 | 2 | 08-07-2026 | NORMAL ACUSTICO | 83,96 | 90,39 | FILA_LITERAL_COMPLETA |
| 105 | 08C34941 | 6 | 4 | 3 | 08-07-2026 | NORMAL ACUSTICO | 7,27 | 7,60 | FILA_LITERAL_COMPLETA |
| 106 | 08C34961 | 6 | 4 | 4 | 08-07-2026 | NORMAL ACUSTICO | 3,62 | 4,03 | FILA_LITERAL_COMPLETA |
| 107 | 08C34993 | 6 | 4 | 5 | 08-07-2026 | NORMAL ACUSTICO | 87,78 | 97,79 | FILA_LITERAL_COMPLETA |
| 108 | 08C35060 | 6 | 4 | 6 | 08-07-2026 | NORMAL ACUSTICO | 341,09 | 356,44 | FILA_LITERAL_COMPLETA |
| 109 | 08C35062 | 6 | 4 | 7 | 08-07-2026 | NETOS PLUS | 5,09 | 6,21 | FILA_LITERAL_COMPLETA |
| 110 | 08C35063 | 6 | 4 | 8 | 08-07-2026 | NORMAL ACUSTICO | 1,26 | 1,32 | FILA_LITERAL_COMPLETA |
| 111 | 08C35281 | 6 | 4 | 9 | 08-07-2026 | NORMAL ACUSTICO | 4,67 | 4,88 | FILA_LITERAL_COMPLETA |
| 112 | 08C35567 | 6 | 4 | 10 | 08-07-2026 | NORMAL ACUSTICO | 19,91 | 22,18 | FILA_LITERAL_COMPLETA |
| 113 | 08C35706 | 6 | 4 | 11 | 08-07-2026 | NORMAL ACUSTICO | 11,19 | 11,70 | FILA_LITERAL_COMPLETA |
| 114 | 08M34186 | 6 | 4 | 12 | 08-07-2026 | NORMAL ACUSTICO | 21,21 | 23,63 | FILA_LITERAL_COMPLETA |
| 115 | 08M34243 | 6 | 4 | 13 | 08-07-2026 | NORMAL ACUSTICO | 69,82 | 72,96 | FILA_LITERAL_COMPLETA |
| 116 | 08M34283 | 6 | 4 | 14 | 08-07-2026 | NORMAL ACUSTICO | 41,68 | 43,56 | FILA_LITERAL_COMPLETA |
| 117 | 08M34323 | 6 | 4 | 15 | 08-07-2026 | NORMAL ACUSTICO | 66,07 | 73,60 | FILA_LITERAL_COMPLETA |
| 118 | 08M34347 | 6 | 4 | 16 | 08-07-2026 | NORMAL ACUSTICO | 9,83 | 10,83 | FILA_LITERAL_COMPLETA |
| 119 | 08M34834 | 6 | 4 | 17 | 08-07-2026 | NORMAL ACUSTICO | 1,62 | 1,69 | FILA_LITERAL_COMPLETA |
| 120 | 08M34837 | 6 | 4 | 18 | 08-07-2026 | NORMAL ACUSTICO | 543,92 | 569,49 | FILA_LITERAL_COMPLETA |
| 121 | 08M34838 | 6 | 4 | 19 | 08-07-2026 | NETOS PLUS | 7,19 | 9,07 | FILA_LITERAL_COMPLETA |
| 122 | 08C36031 | 6 | 4 | 20 | 09-07-2026 | NORMAL ACUSTICO | 25,47 | 28,38 | FILA_LITERAL_COMPLETA |
| 123 | 08C36225 | 6 | 4 | 21 | 09-07-2026 | NORMAL ACUSTICO | 7,34 | 7,67 | FILA_LITERAL_COMPLETA |
| 124 | 08C36245 | 6 | 4 | 22 | 09-07-2026 | NETOS PLUS | 14,29 | 15,92 | FILA_LITERAL_COMPLETA |
| 125 | 08C36330 | 6 | 4 | 23 | 09-07-2026 | NORMAL ACUSTICO | 159,01 | 166,17 | FILA_LITERAL_COMPLETA |
| 126 | 08C36335 | 6 | 4 | 24 | 09-07-2026 | NORMAL ACUSTICO | 14,21 | 14,85 | FILA_LITERAL_COMPLETA |
| 127 | 08C36624 | 6 | 4 | 25 | 09-07-2026 | NORMAL ACUSTICO | 17,51 | 22,10 | FILA_LITERAL_COMPLETA |
| 128 | 08C36870 | 6 | 4 | 26 | 09-07-2026 | NORMAL ACUSTICO | 31,25 | 32,66 | FILA_LITERAL_COMPLETA |
| 129 | 08C36940 | 6 | 4 | 27 | 09-07-2026 | NORMAL ACUSTICO | 2,04 | 2,13 | FILA_LITERAL_COMPLETA |
| 130 | 08C37045 | 6 | 4 | 28 | 09-07-2026 | NORMAL ACUSTICO | 10,08 | 10,53 | FILA_LITERAL_COMPLETA |
| 131 | 08C37049 | 6 | 4 | 29 | 09-07-2026 | NETOS PLUS | 8,48 | 10,70 | FILA_LITERAL_COMPLETA |
| 132 | 08C37065 | 6 | 4 | 30 | 09-07-2026 | NORMAL ACUSTICO | 2,74 | 2,86 | FILA_LITERAL_COMPLETA |
| 133 | 08M35430 | 6 | 4 | 31 | 09-07-2026 | NORMAL ACUSTICO | 105,06 | 132,58 | FILA_LITERAL_COMPLETA |
| 134 | 08M35555 | 6 | 4 | 32 | 09-07-2026 | NORMAL ACUSTICO | 38,98 | 43,43 | FILA_LITERAL_COMPLETA |
| 135 | 08M35630 | 6 | 4 | 33 | 09-07-2026 | NORMAL ACUSTICO | 84,09 | 87,87 | FILA_LITERAL_COMPLETA |
| 136 | 08M35691 | 6 | 4 | 34 | 09-07-2026 | NORMAL ACUSTICO | 15,40 | 16,10 | FILA_LITERAL_COMPLETA |
| 137 | 08M35692 | 6 | 4 | 35 | 09-07-2026 | NORMAL ACUSTICO | 15,40 | 16,10 | FILA_LITERAL_COMPLETA |
| 138 | 08M35806 | 6 | 4 | 36 | 09-07-2026 | NORMAL ACUSTICO | 12,16 | 12,71 | FILA_LITERAL_COMPLETA |
| 139 | 08M35828 | 6 | 4 | 37 | 09-07-2026 | NORMAL ACUSTICO | 18,82 | 19,66 | FILA_LITERAL_COMPLETA |
| 140 | 08M35863 | 6 | 4 | 38 | 09-07-2026 | NORMAL ACUSTICO | 156,99 | 164,05 | FILA_LITERAL_COMPLETA |
| 141 | 08C37482 | 6 | 4 | 39 | 10-07-2026 | NORMAL ACUSTICO | 157,23 | 164,56 | FILA_LITERAL_COMPLETA |
| 142 | 08C37653 | 6 | 4 | 40 | 10-07-2026 | NORMAL ACUSTICO | 485,73 | 507,59 | FILA_LITERAL_COMPLETA |
| 143 | 08C37656 | 6 | 4 | 41 | 10-07-2026 | NETOS PLUS | 18,96 | 23,49 | FILA_LITERAL_COMPLETA |
| 144 | 08C37737 | 6 | 4 | 42 | 10-07-2026 | NORMAL ACUSTICO | 12,83 | 13,40 | FILA_LITERAL_COMPLETA |
| 145 | 08M36292 | 6 | 4 | 43 | 10-07-2026 | NORMAL ACUSTICO | 18,79 | 19,63 | FILA_LITERAL_COMPLETA |
| 146 | 08M36757 | 6 | 4 | 44 | 10-07-2026 | NORMAL ACUSTICO | 289,53 | 302,56 | FILA_LITERAL_COMPLETA |
| 147 | 08M36770 | 6 | 4 | 45 | 10-07-2026 | NORMAL ACUSTICO | 2,12 | 2,21 | FILA_LITERAL_COMPLETA |

## Comparacion de estrategias Luna

| Estrategia | Coste | Resultado relevante | Valor tecnico |
|---|---:|---|---|
| General | 0,034339 USD | 4 albaranes | Buena en cabecera/totales, insuficiente para tablas extensas. |
| Especializada | 0,069991 USD | 147 albaranes | Cobertura total, pero mezcla descripcion/tipo y altera el orden. |
| Tablas literales | 0,052392 USD | 156 filas, 147 de albaran | Conserva celdas, signos, tablas paralelas, paginas y posiciones visuales. |

## Conclusion

La estrategia de tablas literales ofrece la mejor base tecnica para una normalizacion determinista en Python. Recupera las 147 filas completas con fidelidad de celdas y cuesta menos que la extraccion especializada. Python puede interpretar posteriormente los titulos CARGOS/ABONOS, convertir fechas e importes y reconstruir el orden deseado sin pedir al modelo que mezcle transcripcion y reglas de negocio. Antes de usarla de forma general conviene resolver deterministicamente los encabezados duplicados y las celdas vacias adicionales de las tablas fiscales.
