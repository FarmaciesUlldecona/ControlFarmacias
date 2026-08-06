# Resumen global de 11 facturas o abonos

## Alcance

Los cuatro Alliance previos se integran como antecedente Google; solo 08008427 dispone además de Luna general. No se mezclan sus campos en las tasas Luna de los siete nuevos.

## Siete extracciones Luna nuevas

- campos_evaluados: 154
- correctos: 108
- incorrectos: 15
- ausentes: 7
- parciales: 22
- inventados: 2
- acierto_estricto: 70.13
- cobertura: 95.45
- coste_total_usd: 0.102996
- coste_medio_usd: 0.014714
- paginas_totales: 9
- tokens_entrada: 44396
- tokens_entrada_cacheados: 10290
- tokens_salida: 11310
- tokens_razonamiento: 0
- documentos_requieren_tablas: 4
- porcentaje_requieren_tablas: 57.14
- porcentaje_resoluble_solo_extraccion_general: 42.86

## Resultados por documento

| Documento | Proveedor | Tipo | Acierto | Cobertura | Coste USD | Tablas |
|---|---|---|---:|---:|---:|---|
| 2700282621 | DERMOFARM, S.A.U. | ABONO | 63.64% | 100.00% | 0.013164 | sí |
| FR00263029 | HYGIE31 ESPAÑA, S.L.U. | FACTURA | 81.82% | 95.45% | 0.008587 | no |
| 509 | FARMACIA GUIMERA C.B. | FACTURA | 68.18% | 90.91% | 0.010828 | no |
| VN2605-0005381 | FEDERACIÓ FARMACÈUTICA, S.COOP.C.L. | FACTURA | 68.18% | 95.45% | 0.025816 | sí |
| P26CON024967719 | ENDESA ENERGÍA, S.A.U. | FACTURA | 72.73% | 95.45% | 0.021867 | no |
| SCN0276685 | PIERRE FABRE IBÉRICA, S.A. | ABONO | 77.27% | 100.00% | 0.011906 | sí |
| 0702638508 | SUAVINEX GROUP, S.L. | FACTURA | 59.09% | 90.91% | 0.010828 | sí |

## Alliance previo

- Google: 26 correctos de 72; acierto 36.11%; cobertura 69.44%.
- Coste OpenAI conocido para Alliance 08008427: 0.034339 USD.

## Candidatos de normalización

### Comunes

- fechas visibles a ISO
- importes españoles
- páginas técnicas
- campos internos de farmacia y categoría

### Específicos por proveedor

- vencimientos por proveedor
- tablas de albaranes
- signos de abonos
- recargo de equivalencia
- ajustes y cuotas de servicio
