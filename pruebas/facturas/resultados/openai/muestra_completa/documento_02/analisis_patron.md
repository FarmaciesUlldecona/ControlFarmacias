# Evaluación ciega: documento_02

- Archivo local: `ECOCEUTICS MENSUALIDAD PIO.pdf`
- Factura o abono esperado: `FR00263029`
- Proveedor esperado: HYGIE31 ESPAÑA, S.L.U.
- Coste: 0.008587 USD
- Duración: 14.107 s

## Métricas

- Campos evaluados: 22
- Correctos: 18
- Incorrectos: 1
- Ausentes: 1
- Parciales: 2
- Inventados: 0
- Acierto estricto: 81.82 %
- Cobertura: 95.45 %

## Diferencias

- `destinatario`: **PARCIAL**
- `impuestos`: **PARCIAL**
- `proveedor_nombre`: **INCORRECTO**
- `recargo_equivalencia_total`: **AUSENTE**

## Diagnóstico

- Extracción literal de tablas recomendada: no.
- Los campos de categoría, conciliación e identificación interna deben resolverse en Python.
