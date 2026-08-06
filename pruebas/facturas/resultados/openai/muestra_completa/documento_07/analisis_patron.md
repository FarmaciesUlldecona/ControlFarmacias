# Evaluación ciega: documento_07

- Archivo local: `SUAVINEX VTO 15.8.26 PIO.pdf`
- Factura o abono esperado: `0702638508`
- Proveedor esperado: SUAVINEX GROUP, S.L.
- Coste: 0.010828 USD
- Duración: 7.392 s

## Métricas

- Campos evaluados: 22
- Correctos: 13
- Incorrectos: 2
- Ausentes: 2
- Parciales: 5
- Inventados: 0
- Acierto estricto: 59.09 %
- Cobertura: 90.91 %

## Diferencias

- `ajustes`: **AUSENTE**
- `albaranes`: **PARCIAL**
- `destinatario`: **PARCIAL**
- `impuestos`: **PARCIAL**
- `iva_total`: **INCORRECTO**
- `proveedor_cif`: **INCORRECTO**
- `proveedor_nombre`: **PARCIAL**
- `recargo_equivalencia_total`: **AUSENTE**
- `vencimientos`: **PARCIAL**

## Diagnóstico

- Extracción literal de tablas recomendada: sí.
- Los campos de categoría, conciliación e identificación interna deben resolverse en Python.
