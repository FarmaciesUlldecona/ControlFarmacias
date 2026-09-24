# Hito 2T - Alias SAFA / Alliance y conciliacion

Estado final: **ALLIANCE_SAFA_ALIAS_OK_CONCILIACION_PARCIAL**.

## Autoridad funcional y canonicalizacion

Pio autorizo expresamente la equivalencia `SAFA = ALLIANCE HEALTHCARE =
ALLIANCE = CENCORA`. Se registro el proveedor canonico
`ALLIANCE_HEALTHCARE_CENCORA`, con nivel de confianza `PIO_VALIDADO`, y los
aliases exactos:

- `SAFA`
- `1.- SAFA`
- `ALLIANCE`
- `ALLIANCE HEALTHCARE`
- `ALLIANCE HEALTHCARE ESPAÑA`
- `ALLIANCE HEALTHCARE ESPAÑA, S.A.`
- `CENCORA`

La auditoria previa no encontro proveedores ni aliases preexistentes, por lo
que no hubo colisiones. La provenance `AUTORIZACION_FUNCIONAL_PIO` se conservo
en la asociacion de las tres facturas y en cada conciliacion. Los literales
historicos de `albaranes` y `facturas` no se modificaron.

La resolucion es por igualdad normalizada exacta de alias. No usa subcadenas ni
matching difuso. `SAFA CADUCITATS I DEVOLUCIONS` no se considera Alliance.

## Matching y conciliacion

| Factura | Albaranes | Exactos | Economicos unicos | Ambiguos | No localizados | Movimientos | Explicado | Diferencia | Estado |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 08009278 | 109 | 105 | 4 | 0 | 0 | 0 | 3824.6400 | -0.0500 | NORMALIZADA / CONCILIADA / NO_REQUERIDA |
| 08009277 | 165 | 157 | 4 | 0 | 4 | 2 | 13279.9700 | -3168.4200 | NORMALIZADA / PENDIENTE_CONCILIAR / NO_REQUERIDA |
| 08009279 | 5 | 4 | 1 | 0 | 0 | 0 | 141.0200 | -0.0100 | NORMALIZADA / CONCILIADA / NO_REQUERIDA |

Los matches economicos aplican proveedor canonico, ventana de 15 dias,
tolerancia inclusiva de 0.05, menor diferencia economica y fecha exacta cuando
es necesaria para resolver candidatos. El sufijo operativo `A` no se declara
equivalente al numero documental. Los abonos se comparan por magnitud y se
aplican con su signo documental.

Los cuatro no localizados de `08009277` son `08P10588`, `08C61794`, `08P10623`
y `08Z34777`. No existe candidato operacional demostrable para ellos. Por esa
razon la factura permanece pendiente y no se fuerza la conciliacion.

Facturas Alliance conciliadas: 2. Pendientes: 1.

## Aislamiento y pruebas

- Facturas productivas: 5.
- Logista: intacta, NORMALIZADA / CONCILIADA, diferencia 0.
- Cofares: intacta, NORMALIZADA / CONCILIADA, diferencia 0.
- HEFAME procesada: NO; 0 facturas.
- RITA afectada: NO; 0 facturas.
- Farmatic: NO.
- Luna/API: NO.
- Workers: 0.
- Locks: 0 documentales / 0 conciliacion.
- Flags: false / false / false; farmacias habilitadas `[PIO]`.
- Tests focales: 237 passed, 0 failed.
- Suite completa: 962 passed, 0 failed, referencia 946.
- Regresiones: 0.
- Commit/push: NO.

Produccion queda estable. El cierre final fue exclusivamente READ ONLY.
