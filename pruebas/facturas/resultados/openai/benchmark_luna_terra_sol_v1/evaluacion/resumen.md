# Benchmark controlado Luna / Terra / Sol

## Metodología

- 5 documentos y 3 modelos: 15 resultados de extracción general.
- Alliance añade 3 resultados de extracción literal de tablas.
- 17 llamadas nuevas y 1 artefacto Luna literal estrictamente comparable reutilizado.
- Sin normalizadores específicos y con el patrón aislado de los extractores.
- Una llamada Terra de Alliance general falló y se conserva como fallo, sin reintento.

## Resultado agregado general

| Modelo | Llamadas OK/error | Correctos | Acierto | Cobertura | Invenciones | Incidencias | Coste conocido muestra |
|---|---:|---:|---:|---:|---:|---:|---:|
| gpt-5.6-luna | 5/0 | 75/110 | 68.18% | 95.45% | 39 | 35 | 0.144272 USD |
| gpt-5.6-terra | 4/1 | 66/110 | 60.00% | 76.36% | 16 | 22 | 0.274708 USD |
| gpt-5.6-sol | 5/0 | 80/110 | 72.73% | 97.27% | 50 | 30 | 0.793682 USD |

## Resultados por documento

| Caso | Modelo | Acierto | Cobertura | Invenciones | Coste |
|---|---|---:|---:|---:|---:|
| alliance_08008427 | gpt-5.6-luna | 63.64% | 95.45% | 22 | 0.034471 USD |
| alliance_08008427 | gpt-5.6-terra | ERROR | ERROR | - | N/D |
| alliance_08008427 | gpt-5.6-sol | 63.64% | 100.00% | 27 | 0.181415 USD |
| farmacia_guimera | gpt-5.6-luna | 77.27% | 95.45% | 2 | 0.011151 USD |
| farmacia_guimera | gpt-5.6-terra | 86.36% | 95.45% | 0 | 0.025821 USD |
| farmacia_guimera | gpt-5.6-sol | 86.36% | 95.45% | 0 | 0.057853 USD |
| suavinex | gpt-5.6-luna | 59.09% | 95.45% | 1 | 0.012020 USD |
| suavinex | gpt-5.6-terra | 59.09% | 90.91% | 0 | 0.028174 USD |
| suavinex | gpt-5.6-sol | 59.09% | 95.45% | 2 | 0.062498 USD |
| fedefarma | gpt-5.6-luna | 63.64% | 95.45% | 13 | 0.025328 USD |
| fedefarma | gpt-5.6-terra | 72.73% | 100.00% | 16 | 0.066259 USD |
| fedefarma | gpt-5.6-sol | 72.73% | 100.00% | 21 | 0.159758 USD |
| ecoceutics | gpt-5.6-luna | 77.27% | 95.45% | 1 | 0.008910 USD |
| ecoceutics | gpt-5.6-terra | 81.82% | 95.45% | 0 | 0.021974 USD |
| ecoceutics | gpt-5.6-sol | 81.82% | 95.45% | 0 | 0.046138 USD |

## Alliance tablas literales

### gpt-5.6-luna

{"filas_esperadas": 147, "filas_obtenidas": 147, "numeros_correctos": 147, "fechas_correctas": 147, "descripciones_correctas": 147, "bases_correctas": 147, "totales_correctos": 147, "signos_correctos": 294, "paginas_correctas": 147, "posiciones_correctas": 147, "duplicados": 0, "ausentes": 0, "inventados": 0}

### gpt-5.6-terra

{"filas_esperadas": 147, "filas_obtenidas": 147, "numeros_correctos": 147, "fechas_correctas": 147, "descripciones_correctas": 147, "bases_correctas": 147, "totales_correctos": 147, "signos_correctos": 294, "paginas_correctas": 147, "posiciones_correctas": 147, "duplicados": 0, "ausentes": 0, "inventados": 0}

### gpt-5.6-sol

{"filas_esperadas": 147, "filas_obtenidas": 147, "numeros_correctos": 147, "fechas_correctas": 147, "descripciones_correctas": 147, "bases_correctas": 147, "totales_correctos": 147, "signos_correctos": 294, "paginas_correctas": 147, "posiciones_correctas": 147, "duplicados": 0, "ausentes": 0, "inventados": 0}

## Costes y proyecciones

El coste medio general se calcula sobre llamadas completadas. Cada escenario suma una segunda llamada literal al 20 %, 40 % o 60 % de 60 facturas mensuales. El coste de la llamada Terra fallida no está disponible; su total de muestra es un mínimo conocido.

| Modelo | Media general | Literal Alliance | 20 % mes/año | 40 % mes/año | 60 % mes/año |
|---|---:|---:|---:|---:|---:|
| gpt-5.6-luna | 0.018376 USD | 0.052392 USD | 1.73/20.78 USD | 2.36/28.32 USD | 2.99/35.86 USD |
| gpt-5.6-terra | 0.035557 USD | 0.132480 USD | 3.72/44.68 USD | 5.31/63.76 USD | 6.90/82.83 USD |
| gpt-5.6-sol | 0.101532 USD | 0.286020 USD | 9.52/114.29 USD | 12.96/155.48 USD | 16.39/196.66 USD |