# Hito 2R - Alliance multifactura

Estado final: **ALLIANCE_MULTIFACTURA_PARCIAL**.

## Regla documental certificada

La promoción candidato -> ALBARAN_DEMOSTRADO exige conjuntamente:

1. segmento de factura DETERMINISTA, con número propio y paginación interna;
2. página incluida en ese segmento;
3. cabecera literal de tabla con columnas `NUMERO ALBARAN`;
4. número de albarán documentado en la fila con evidencia geométrica;
5. todo campo opcional presente (fecha, tipo, base, total, sentido) con evidencia;
6. provenance con factura documental, rango, página, lado y fila literal.

El patrón del número, `DIRECT`, filename, orden aislado o datos Supabase no
conceden rol. Fecha o importe ausentes se conservan null. Segmentación ambigua,
cabecera no concluyente o evidencia incompleta dejan el objeto como candidato.

En el PDF real cada página de detalle repite la cabecera de factura/paginación y
la tabla `CARGOS ABONOS / NUMERO ALBARAN`; todas las 279 filas cumplen la regla.
Se conservan los candidatos originales y se publican además 279 albaranes con
rol demostrado. Candidatos no promovidos: cero. No hay mezcla entre facturas.

Tres filas de 08009277 tienen relación documental exacta 1:1 con movimientos
del resumen. La extracción cruda conserva ambos objetos y las relaciones. En la
proyección económica se excluyen esos tres movimientos duplicados y se conservan
los dos movimientos independientes: CONDIC. COMERCIAL y SERVICIO BASICO.

## Resultado documental en memoria

| Factura | Páginas | Total | Fiscalidad base/IVA/RE | Vencimiento | Albaranes | No promovidos | Completitud |
| --- | --- | ---: | --- | --- | ---: | ---: | --- |
| 08009278 | 1-4 | 3824.59 | 3506.46 / 272.07 / 46.06 | 2026-09-30 | 109 | 0 | demostrada |
| 08009277 | 5-9 | 10111.55 | 9539.43 / 507.28 / 64.84 | 2026-10-06 | 165 | 0 | demostrada |
| 08009279 | 10-11 | 141.01 | 125.51 / 13.44 / 2.06 | 2026-11-06 | 5 | 0 | demostrada |

Identidades económicas independientes y demostradas. Incidencias no bloqueantes:
MONEDA_NO_DOCUMENTADA e IMPORTE_VENCIMIENTO_NO_DOCUMENTADO en cada factura.

## Matching Supabase READ ONLY

Se consultaron 1235 albaranes PIO de la ventana temporal. Resultado:

| Factura | EXACTO | ECONOMICO_UNICO | AMBIGUO | NO_LOCALIZADO |
| --- | ---: | ---: | ---: | ---: |
| 08009278 | 0 | 0 | 0 | 109 |
| 08009277 | 0 | 0 | 0 | 165 |
| 08009279 | 0 | 0 | 0 | 5 |

No existe proveedor/alias Alliance o Cencora en `proveedores` ni en
`proveedores_alias`. En `albaranes` tampoco existe ese literal. El principal
proveedor operacional del periodo es `1.- SAFA`, id proveedor 2, pero no existe
evidencia certificada que autorice Alliance = SAFA. No se inventó esa equivalencia.
Farmatic no fue consultado.

## Precheck y persistencia

Precheck: dos facturas productivas, Logista y Cofares intactas, migraciones 14/15
presentes, flags false/false/false, farmacias [PIO], workers/locks/reprocesos cero,
RITA sin habilitar y documento Alliance pendiente con inventario vacío.

PDF SHA256:
`7b806565a4f09e182c5ec9d75b40b959fd39c4af86da77b7a8cb745c6e1192b2`.
Documento: `ffee3c1c-ebcc-4287-99b2-79ccbae45f22`.

Las tres facturas se persistieron juntas mediante una única operación
`cf_persistir_documento_multifactura`, transaccional, con segmentos 1-4, 5-9 y
10-11. Ejecución `cac2dd70-af4f-4e2b-a19a-abd2135fae53`. El documento quedó
NORMALIZADA / COMPLETA, inventario 3, las tres PERSISTIDAS. Facturas totales: 5.

## Elegibilidad, claim y conciliación

- 08009278: APTA_MERCANCIA; claim individual.
- 08009277: APTA_MIXTA; claim individual.
- 08009279: APTA_MERCANCIA; claim individual.

Cada llamada al claim devolvió una sola factura Alliance; nunca el PDF. Logista y
Cofares no fueron reclamadas. Las conciliaciones se registraron independientemente.

| Factura | Estado | Albaranes doc./oper. | Explicado | Diferencia | Detalles |
| --- | --- | --- | ---: | ---: | ---: |
| 08009278 | NORMALIZADA / PENDIENTE_CONCILIAR / NO_REQUERIDA | 109 / 0 | 0.00 | 3824.59 | 109 SIN_COINCIDENCIA |
| 08009277 | NORMALIZADA / PENDIENTE_CONCILIAR / NO_REQUERIDA | 165 / 0 | 58.71 | 10052.84 | 165 SIN_COINCIDENCIA + 2 movimientos |
| 08009279 | NORMALIZADA / PENDIENTE_CONCILIAR / NO_REQUERIDA | 5 / 0 | 0.00 | 141.01 | 5 SIN_COINCIDENCIA |

Ninguna se declaró CONCILIADA porque no existe trazabilidad operacional suficiente.
La tolerancia de 0.05 no altera ese resultado.

## Aislamiento y pruebas

- Logista: NORMALIZADA/CONCILIADA, 448.00, intacta.
- Cofares: NORMALIZADA/CONCILIADA, 177.74, intacta.
- HEFAME procesada: NO. Facturas HEFAME: 0.
- RITA afectada: NO. Facturas RITA: 0.
- Otro PDF procesado: NO; solo una ejecución para el documento objetivo.
- Workers al cierre: 0; locks documentales/conciliación: 0/0.
- Flags al cierre: false/false/false; farmacias [PIO].
- Farmatic: NO. Luna/API: NO. Commit/push: NO.
- Focales finales: 273 passed, 0 failed, 8.35 s.
- Suite completa final: 946 passed, 0 failed, 55.00 s.
- Referencia: 933; incremento: 13; regresiones: 0.

Conteos finales: facturas 5, normalizaciones 4, conciliaciones 6, detalles 287,
albaranes documentales persistidos 280 (1 previo + 279 Alliance), movimientos 6
(4 previos + 2 Alliance). El cierre READ ONLY se repitió después de los tests.

Producción queda estable. El resultado es PARCIAL exclusivamente porque la
conciliación operacional no puede demostrarse sin una autoridad Alliance/SAFA.
