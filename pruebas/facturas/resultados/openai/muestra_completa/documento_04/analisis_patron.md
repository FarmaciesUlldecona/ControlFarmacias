# Evaluación ciega: documento_04

- Archivo local: `FEDE VTO 5.8.26 PIO.pdf`
- Factura o abono esperado: `VN2605-0005381`
- Proveedor esperado: FEDERACIÓ FARMACÈUTICA, S.COOP.C.L.
- Coste: 0.025816 USD
- Duración: 15.557 s

## Métricas

- Campos evaluados: 22
- Correctos: 15
- Incorrectos: 2
- Ausentes: 1
- Parciales: 4
- Inventados: 0
- Acierto estricto: 68.18 %
- Cobertura: 95.45 %

## Diferencias

- `ajustes`: **PARCIAL**
- `albaranes`: **PARCIAL**
- `categoria`: **AUSENTE**
- `destinatario`: **PARCIAL**
- `impuestos`: **PARCIAL**
- `proveedor_cif`: **INCORRECTO**
- `proveedor_nombre`: **INCORRECTO**

## Diagnóstico

- Extracción literal de tablas recomendada: sí.
- Los campos de categoría, conciliación e identificación interna deben resolverse en Python.
