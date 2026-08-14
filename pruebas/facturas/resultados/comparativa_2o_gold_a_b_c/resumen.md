# Comparativa A/B/C — segundo gold

Evaluacion determinista comun, con tolerancia monetaria de 0,01 EUR e invenciones como prioridad.

| Baseline | Facturas salida | Identificadas | Omitidas | Inventadas | Multifaktura exacta | Campos acierto | Cobertura | Fiscalidad atributos | Vencimientos | Albaranes | Alb. ausentes | Alb. inventados | Movimientos | Invenciones totales | Coste total | Coste/PDF | Coste/factura salida | Duracion |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 18 | 18 | 0 | 0 | 2/2 | 84.86% | 90.04% | 98.25% | 100.0% | 19/337 | 318 | 8 | 0.0% | 32 | $0.05523000 | $0.00394500 | $0.00306833 | 176.461s |
| B | 19 | 18 | 0 | 1 | 1/2 | 85.26% | 95.22% | 98.89% | 100.0% | 170/337 | 167 | 5 | 44.0% | 48 | $0.03466272 | $0.00247591 | $0.00182435 | 120.439s |
| C | 21 | 18 | 0 | 3 | 1/2 | 78.88% | 92.03% | 91.03% | 100.0% | 332/337 | 5 | 5 | 40.0% | 39 | $0.20285802 | $0.01448986 | $0.00965991 | 192.891s |

## Deltas

- B-A (contrato V2): `{"facturas_identificadas": 0, "campos_pp": 0.4, "albaranes_detectados": 151, "invenciones": 16, "coste_usd": -0.02056728}`
- C-B (Splitter): `{"facturas_identificadas": 0, "campos_pp": -6.38, "albaranes_detectados": 162, "invenciones": -9, "coste_usd": 0.1681953}`

## Recomendacion

Luna V2 sola. Normalizadores especificos adicionales: si.
