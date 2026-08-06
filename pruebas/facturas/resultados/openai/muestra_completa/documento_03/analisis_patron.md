# Evaluación ciega: documento_03

- Archivo local: `FARMACIA GUIMERA VTO 30.6.26 PIO.pdf`
- Factura o abono esperado: `509`
- Proveedor esperado: FARMACIA GUIMERA C.B.
- Coste: 0.010828 USD
- Duración: 6.976 s

## Métricas

- Campos evaluados: 22
- Correctos: 15
- Incorrectos: 2
- Ausentes: 2
- Parciales: 1
- Inventados: 2
- Acierto estricto: 68.18 %
- Cobertura: 90.91 %

## Diferencias

- `ajustes`: **PARCIAL**
- `destinatario`: **INCORRECTO**
- `nota_revision`: **AUSENTE**
- `periodo_facturacion_fin`: **INVENTADO**
- `periodo_facturacion_inicio`: **INVENTADO**
- `proveedor_cif`: **AUSENTE**
- `proveedor_nombre`: **INCORRECTO**

## Diagnóstico

- Extracción literal de tablas recomendada: no.
- Los campos de categoría, conciliación e identificación interna deben resolverse en Python.
