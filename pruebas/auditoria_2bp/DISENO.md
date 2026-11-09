# Hito 2BP: serie supervisada de conciliación

Solo local. Sin push. Producción no tocada. Script: `pruebas/auditoria_2bp/serie_conciliacion.py`. Mismo esquema que
la serie de normalización (2BJ, `pruebas/auditoria_2bj/DISENO.md`).

## 1. Objetivo

Conciliar las facturas `PENDIENTE_CONCILIAR` (48 tras la serie 2BJ) de una en una, con
`ejecutar_una_manual_conciliacion()` (claim `MANUAL_ONE_SHOT`, selector y ordering oficiales de la 18, sin
preselección ni flags), en tandas confirmadas por Pio y con parada ante cualquier desviación del plan.

## 2. Plan READ_ONLY (`plan <plan.json>`)

- Lee las facturas elegibles en el orden del selector oficial (mismo SQL que el 2AT, sin `for update` ni `limit`).
- **Simula cada una** con el camino real del worker (`auditoria_readonly._simular`: `construir_detalles` productivo
  sobre un cliente de solo lectura, R11, revalidación de farmacia) y registra: camino (`PERSISTIR` o `FALLO`),
  resultado previsto (`CONCILIADA` / `DIFERENCIA`), importe, explicado, **diferencia**, tolerancia, clave idempotente
  prevista, resumen de detalles y huella de la fila de la factura.
- **Simulación en cadena (R15):** cada conciliación reserva sus albaranes, así que los de las facturas previstas antes
  quedan ocupados para las siguientes (y una factura que se vuelve a conciliar libera los suyos). Sin escrituras: se
  sustituye en memoria `_contexto_exclusividad` durante la simulación.
- Lista las no elegibles (con su razón), el estado de la 30 y la operación; resumen por resultado y posición de la
  primera factura que no simula `CONCILIADA`. `decisiones_pio` vacío.

## 3. Tandas (`tanda <n> <plan.json> <directorio>`)

- Confirmación expresa de Pio **por tanda**; como máximo 5 la primera y 20 las siguientes; guard exclusivo por
  directorio; sin reintentos; salidas fuera del repositorio.
- **Puerta git** (al empezar): árbol limpio y HEAD = `origin/main`; por delante solo con documentación (`docs/` o
  `*.md`, excepción de Pio del 2BN-D) y HEAD descendiente de `origin/main`.
- **Puertas antes de cada ejecución:**
  - operación (2AT): flags `f|f|f|{PIO}`, tolerancia 0,05, 0 locks de documentos, 0 claims de conciliación,
    0 `NORMALIZANDO`, 0 workers; configuración idéntica al preflight de la tanda;
  - **migración 30 desplegada** (decisión de Pio, 2BR): `cf_detalles_por_linea` y `cf_persistir_conciliacion` con el
    cuerpo de la 30 del repositorio y la tabla `conciliacion_detalles_previo_30`; si falta → `MIGRACION_30_AUSENTE`;
  - tareas programadas a 60 min o más y no en ejecución;
  - n.º 1 del selector en el plan y con la misma huella de fila.
- **Simulación inmediata** READ_ONLY del n.º 1: debe coincidir con la del plan (resultado, importes, diferencia,
  tolerancia y clave idempotente) → si no, `SIMULACION_DISTINTA_DEL_PLAN`.
- **PARADA si el n.º 1 no simula `CONCILIADA`** (`NUMERO_1_SIMULA_DIFERENCIA:<id>:<número>:<diferencia>` o
  `NUMERO_1_SIMULA_FALLO`), sin ejecutar. **Pio decide caso a caso:** si decide conciliarla, se registra en
  `decisiones_pio` del plan (`{"<factura_id>": {"decision": "CONCILIAR_CON_DIFERENCIA", "diferencia": "<exacta>"}}`)
  y solo vale para esa factura y esa diferencia (D-A: consume un intento con backoff).
- **UNA llamada** a `ejecutar_una_manual_conciliacion()` (cliente del `.env` con project ref y rol de servicio
  demostrados; worker con sufijo único). Comprobación: retorno (1 factura, `MANUAL_ONE_SHOT`), estado e intentos
  previstos (`_estado_previsto` del 2AT), claim liberado, conciliación vigente = resultado, diferencia y clave del plan.
- **2AX por fila** tras cada ejecución: solo filas nuevas de la factura, cambios en su fila de `facturas` y sus
  `conciliaciones` y bajas de sus reservas (R15: pasan a la conciliación nueva). Cualquier otra → PARADA.
- **Postcheck 2AX por fila de toda la tanda** al terminar y **también al parar** (y, en el postcheck, 0 claims y
  configuración y flags iguales).

## 4. Hallazgo y corrección en el simulador del 2AT

`auditoria_readonly._simular` era anterior a la 28: no reconstruía el `resultado_json` con referencias antes de la
barrera de farmacia, así que con la 28 (en producción desde el 2BM-D) simulaba `FARMACIA_DOCUMENTO_NO_DEMOSTRABLE` en
todas las facturas, mientras que el worker real (`guardar_conciliacion`) sí la reconstruye. Corregido con la réplica
literal de esa revalidación (sin cambios para ejecuciones sin referencias).

## 5. Tests (`tests/facturas/runtime_supabase/test_serie_conciliacion_2bp.py`, 24, `pg17_local`)

Escenario: las cinco facturas reales del 2AO en la plantilla 30 (08007969 con R17; las demás con albaranes
sintéticos). Puerta git (6 casos) y comprobación de la simulación (sin BD); plan en el orden del selector, solo
lectura, con R17 y R11; simulación en cadena (un albarán reservado por otra factura prevista); tanda completa con
postcheck, guard y cola vacía; máximo 5; **PARADA si el n.º 1 simula DIFERENCIA** (sin escrituras) y conciliación con
decisión de Pio; **sin la 30 (plantillas 29 y 30_rollback) → PARADA**; simulación distinta del plan; n.º 1 fuera del
plan o con la fila cambiada; puertas (git, flags, tareas, claim); fila ajena cambiada y excepción, con postcheck.
