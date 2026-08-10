# Evaluaci?n independiente de Alliance 08008428 normalizada

La evaluaci?n proyecta el resultado al contrato de negocio del patr?n. Los campos internos de trazabilidad (`procedencia`, `orden_reconstruido`, etc.) no se contabilizan como invenciones.

## Resumen de 22 campos

- Correctos: 21/22.
- Incorrectos: 0.
- Parciales: 1.
- Ausentes: 0.
- Acierto estricto: 95.45%.
- Cobertura: 100.00%.
- Invenciones: 0.

## Evaluaci?n at?mica de negocio

- ?tomos evaluados: 670.
- Correctos: 669.
- Incorrectos: 1.
- Ausentes: 0.
- Inventados: 0.
- Acierto estricto: 99.85%.

## Campos no completamente correctos

- `destinatario`: PARCIAL

## Albaranes

- Esperados/normalizados: 92/92.
- N?meros correctos: 92.
- Fechas correctas: 92.
- Importes correctos: 184/184.
- Ordenes correctos: 92.
- Faltantes: 0; inventados: 0; duplicados: 0.

## Incidencias

- `ORDEN_RECONSTRUIDO` en `albaranes.orden`: Orden estable por página, orden de tabla y orden visual; orden_reconstruido=true.
- `DESGLOSE_FISCAL_INCOMPLETO` en `impuestos`: Se devuelve impuestos=[]; los totales agregados proceden de luna_general.
