# Checkpoint de validación Alliance 08008428

## Resultado

La factura `08008428` de `ALLIANCE HEALTHCARE ESPAÑA, S.A.` fue procesada con el adaptador Alliance existente, versión `alliance_v1.1`, sin modificar producción.

Clasificación definitiva: **A — `alliance.py` GENERALIZA**.

## Alcance

- PDF: `ALLIANCE VTO 10.9-6.10-10.10-6.11 PIO.pdf`.
- Páginas: exclusivamente 1–3.
- Una lectura general Luna.
- Una lectura literal Luna adicional.
- Sin OCR, Terra, Sol, Google ni Azure.
- Sin cambios en `alliance.py`, otros archivos de producción, tests o patrón.

## Lectura general

- Modelo: `gpt-5.6-luna`.
- Factura, proveedor, cabecera, vencimiento y totales identificados correctamente.
- Albaranes extraídos: 0.
- Coste: **0,022824 USD**.

## Lectura literal

- Modelo: `gpt-5.6-luna`.
- Filas literales totales: 104.
- Albaranes: 92.
- Cargos: 92.
- Abonos: 0.
- Correctos: 92/92.
- Faltantes, extras, duplicados e identificadores incorrectos: 0.
- Importes correctos: 184/184.
- Coste: **0,037240 USD**.
- Coste acumulado: **0,060064 USD**.

## Normalización

El adaptador `alliance_v1.1` produjo:

- factura `08008428`;
- páginas 1–3;
- 92 albaranes;
- un vencimiento con fecha `2026-09-10` e importe 2.972,70 €;
- `impuestos=[]`;
- `ajustes=[]`.

El importe del vencimiento se asignó mediante la regla determinista Alliance existente de vencimiento único. No se añadió ninguna regla nueva.

## Evaluación independiente

### Evaluación de 22 campos

- Correctos: 21.
- Incorrectos: 0.
- Parciales: 1.
- Ausentes: 0.
- Acierto estricto: 95,45%.
- Cobertura: 100%.
- Invenciones: 0.

### Evaluación atómica de negocio

- Átomos evaluados: 670.
- Correctos: 669.
- Incorrectos: 1.
- Ausentes: 0.
- Inventados: 0.
- Acierto estricto: 99,85%.

La única diferencia es el nombre visible del destinatario:

- extracción visible: `PUIG SALOMON PIUS`;
- patrón interno: `FARMACIA PIO PUIG`.

No debe corregirse: conservar el texto visible es el comportamiento prudente. El ID de farmacia `PIO`, el CIF `40901058C` y el método `CIF` son correctos.

## Incidencias conservadas

- `ORDEN_RECONSTRUIDO`.
- `DESGLOSE_FISCAL_INCOMPLETO`.

## Generalización demostrada

El mismo adaptador procesa sin cambios dos facturas Alliance reales:

| Característica | 08008427 | 08008428 |
|---|---:|---:|
| Páginas | 4 | 3 |
| Albaranes | 147 | 92 |
| Cargos | 145 | 92 |
| Abonos | 2 | 0 |
| Servicio Básico | Sí | No |
| Total | 11.185,10 € | 2.972,70 € |

## Conclusión

`alliance.py` generaliza correctamente y de forma conservadora a una segunda factura real Alliance sin modificaciones ni lógica específica por número de factura.

No iniciar todavía el caso `08008429`.
