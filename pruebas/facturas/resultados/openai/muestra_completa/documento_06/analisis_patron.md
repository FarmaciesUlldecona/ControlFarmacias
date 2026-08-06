# Evaluación ciega: documento_06

- Archivo local: `PIERRE FABRE ABONO VTO 7.9.26 PIO.pdf`
- Factura o abono esperado: `SCN0276685`
- Proveedor esperado: PIERRE FABRE IBÉRICA, S.A.
- Coste: 0.011906 USD
- Duración: 7.938 s

## Métricas

- Campos evaluados: 22
- Correctos: 17
- Incorrectos: 1
- Ausentes: 0
- Parciales: 4
- Inventados: 0
- Acierto estricto: 77.27 %
- Cobertura: 100.00 %

## Diferencias

- `ajustes`: **PARCIAL**
- `albaranes`: **PARCIAL**
- `destinatario`: **PARCIAL**
- `proveedor_nombre`: **INCORRECTO**
- `vencimientos`: **PARCIAL**

## Diagnóstico

- Extracción literal de tablas recomendada: sí.
- Los campos de categoría, conciliación e identificación interna deben resolverse en Python.
