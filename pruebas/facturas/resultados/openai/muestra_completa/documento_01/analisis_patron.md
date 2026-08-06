# Evaluación ciega: documento_01

- Archivo local: `DERMOFARM ABONO VTO 5.8.26 PIO.pdf`
- Factura o abono esperado: `2700282621`
- Proveedor esperado: DERMOFARM, S.A.U.
- Coste: 0.013164 USD
- Duración: 10.770 s

## Métricas

- Campos evaluados: 22
- Correctos: 14
- Incorrectos: 5
- Ausentes: 0
- Parciales: 3
- Inventados: 0
- Acierto estricto: 63.64 %
- Cobertura: 100.00 %

## Diferencias

- `albaranes`: **PARCIAL**
- `base_imponible_total`: **INCORRECTO**
- `destinatario`: **PARCIAL**
- `importe_total`: **INCORRECTO**
- `impuestos`: **PARCIAL**
- `iva_total`: **INCORRECTO**
- `proveedor_cif`: **INCORRECTO**
- `recargo_equivalencia_total`: **INCORRECTO**

## Diagnóstico

- Extracción literal de tablas recomendada: sí.
- Los campos de categoría, conciliación e identificación interna deben resolverse en Python.
