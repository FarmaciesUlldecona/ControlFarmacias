# Hito 2AV — Diseño de la migración 18

Conciliación manual one-shot, cierre atómico y fallos con backoff.
Certificación exclusivamente en PostgreSQL 17 local; **no se despliega**.

## Defectos de partida (2AT)

| Id | Defecto | Regla que lo resuelve |
|---|---|---|
| C1 | Sin ruta manual: con `conciliacion_automatica=false` el claim solo devuelve facturas con reintento solicitado. | R5 |
| C2 | `guardar_conciliacion` hace 4 escrituras REST separadas. | R6 |
| C3 | `fallar_conciliacion` no fija `conciliacion_proximo_at`. | R7 |
| C4 | La conciliación se graba siempre como `AUTOMATICO`. | R8 |
| C5 | `id_proveedor` de SAFA aparece como `'2'`, `'0002 '` y `'0002'`. | R9 |

## R5 — Claim con modo de ejecución

Mismo patrón que la migración 16 para normalización.

- **Núcleo interno**
  `cf_reclamar_factura_conciliacion_nucleo(p_worker_id text, p_bloqueo_segundos integer, p_modo_ejecucion text)`
  → `setof facturas`.
  - Selector y ordering copiados literalmente de la migración 14. La única
    diferencia es el interruptor:
    `(p_modo_ejecucion = 'MANUAL_ONE_SHOT' or c.conciliacion_automatica or f.conciliacion_reintento_solicitado_at is not null)`.
  - `limit 1`, `for update of f skip locked`, el mismo lock y la misma expiración.
  - Registra `CONCILIACION_CLAIM` en `historial_facturas` con `modo_ejecucion`.
  - Sin grant a nadie: EXECUTE revocado a public, anon, authenticated y service_role.
- **Envoltorios** (SQL, SECURITY DEFINER, EXECUTE solo para service_role):
  - `cf_reclamar_factura_conciliacion(text, integer)`: la firma antigua conserva el
    comportamiento y pasa el modo `AUTOMATICO`.
  - `cf_reclamar_factura_conciliacion_manual_one_shot(text, integer)`: modo
    `MANUAL_ONE_SHOT`. No admite preselección porque no recibe ningún identificador.

## R6 — Cierre atómico

`cf_persistir_conciliacion(p_factura_id uuid, p_worker_id text, p_disparador text, p_idempotency_key text, p_resultado jsonb) returns uuid`

Funciona en una sola transacción, porque es una función invocada como RPC.

1. **Validación:** `p_disparador` debe ser `AUTOMATICO` o `MANUAL_ONE_SHOT`. La clave
   y el worker no pueden estar vacíos. `p_resultado->>'resultado'` debe ser uno de
   los resultados que admite el check de `conciliaciones`.
2. **Bloqueo:** `select … from facturas where id = p_factura_id for update`.
3. **Replay** (ya existe una conciliación con `(factura_id, idempotency_key)`):
   - Si el llamante tiene el claim, libera el lock, borra el reintento solicitado y
     restaura `estado_conciliacion_cf` según el resultado original: `CONCILIADA`
     si fue `CONCILIADA` y `PENDIENTE_CONCILIAR` en cualquier otro caso.
   - Si no lo tiene, es una retransmisión y no cambia nada.
   - En ambos casos registra `CONCILIACION_REPLAY_IDEMPOTENTE` con `claim_liberado` y
     devuelve el id original. No inserta cabecera ni detalles.
4. **Claim obligatorio:** `conciliacion_bloqueado_por = p_worker_id`, la farmacia
   habilitada y el `modo_ejecucion` del último `CONCILIACION_CLAIM` de ese worker
   para esa factura igual a `p_disparador` (R8). En otro caso, excepción sin cambios.
5. **Escrituras**, dentro de la misma transacción:
   - la conciliación anterior pasa a `es_actual=false`;
   - cabecera en `conciliaciones`: `intento = max+1`, `COMPLETADA`, importes,
     `resultado`, `disparador`, `worker_id`, `idempotency_key` y
     `provenance {modo_ejecucion, resultado_hash}`;
   - detalles en `conciliacion_detalles`, desde `p_resultado->'detalles'`;
   - la factura: `estado_conciliacion_cf`, `diferencia_albaranes`,
     `conciliacion_intentos = intento`, lock liberado, reintento borrado,
     `conciliacion_intentos_fallo = 0`, `conciliacion_ultima_clase_fallo = null` y
     `conciliacion_proximo_at = null`;
   - evento `CONCILIACION_PERSISTIDA` en el historial.
6. Cualquier excepción revierte todo. El lock sigue en manos del worker, que llama a
   `cf_registrar_fallo_conciliacion` (R7) para liberarlo con backoff.

El estado resultante no cambia respecto al Python actual: `CONCILIADA` si el
resultado es `CONCILIADA` y `PENDIENTE_CONCILIAR` en otro caso.

## Clave idempotente

Se compone en Python:
`conciliacion:{factura_id}:{disparador}:{sha256(json canónico de p_resultado)}`.

- El JSON canónico usa claves ordenadas y los importes como texto con 4 decimales.
- Si el mismo claim o un claim posterior produce el mismo resultado, la clave es la
  misma: es un replay y no hay duplicado.
- Si los datos cambian (albaranes u otros), la clave es distinta y se registra un
  intento nuevo.
- Hay un índice único parcial `(factura_id, idempotency_key) where idempotency_key is not null`.

## R7 — Fallo con backoff

`cf_registrar_fallo_conciliacion(p_factura_id uuid, p_worker_id text, p_disparador text, p_error_codigo text, p_error_detalle text, p_clase_fallo text) returns boolean`

- **Clases:** `DEFECTO_DOCUMENTO` o `TRANSITORIO`, las dos cuentan. Python las
  asigna con `clasificar_fallo_conciliacion`; un motivo desconocido es `TRANSITORIO`.
- **Sin claim del llamante:** no cambia nada y devuelve `false`. Es una retransmisión
  y no rompe el worker.
- **Contador y estado:**
  - `n = 1` si la factura tenía un reintento solicitado (el reintento reinicia el
    presupuesto); en otro caso, `conciliacion_intentos_fallo + 1`.
  - Si `n < conciliacion_max_intentos`: sigue en `PENDIENTE_CONCILIAR` con
    `conciliacion_proximo_at = now() + backoff[n]` (1 h, 6 h y 24 h).
  - Si `n >= conciliacion_max_intentos` (4): pasa a `estado_conciliacion_cf = 'REVISION_CONCILIACION'`,
    que el selector no reclama porque exige `PENDIENTE_CONCILIAR`.
- **En todos los casos:** lock liberado, reintento borrado, `conciliacion_ultimo_error`,
  la clase y el evento `CONCILIACION_ERROR`. No inserta filas en `conciliaciones`,
  igual que antes.
- **Vuelta a la cola:** solo con `cf_solicitar_reintento_conciliacion`, que **no se
  redefine**.
  - Ya fija `PENDIENTE_CONCILIAR` y el reintento solicitado.
  - El reinicio del contador se aplica en el siguiente fallo (`n = 1`) o éxito (`0`).
  - Así no cambian sus privilegios actuales (authenticated sí, service_role no),
    que redefinirla con la regla de privilegios de la 18 obligaría a retirar.

## Columnas nuevas y estado de revisión

- `facturas.conciliacion_intentos_fallo integer not null default 0` (check `>= 0`).
- `facturas.conciliacion_ultima_clase_fallo text` (check: `DEFECTO_DOCUMENTO` o
  `TRANSITORIO`).
- `facturas_estado_conciliacion_cf_check`: añade `REVISION_CONCILIACION`.
- `conciliaciones.idempotency_key text` más el índice único parcial.
- `conciliaciones_disparador_check`: añade `MANUAL_ONE_SHOT`.
- `cf_configuracion.conciliacion_max_intentos integer default 4` y
  `conciliacion_backoff interval[] default {1h,6h,24h}`, con un check análogo al de R3.

`conciliacion_intentos` conserva su significado: el número de intento de la última
conciliación persistida.

## R8 — Provenance

- `conciliaciones.disparador` es `MANUAL_ONE_SHOT` en la ruta manual y `AUTOMATICO`
  en la automática.
- `provenance.modo_ejecucion` repite el mismo valor.
- La RPC lo valida contra el modo del claim (R6, paso 4).

## R9 — `id_proveedor` tolerante

Solo cambia la comparación, en `buscar_candidato_albaran`:
`_id_proveedor_comparable(v)` quita espacios y, si el resultado es numérico, también
los ceros a la izquierda (`'2' == '0002' == '0002 '`).

`conservar_id_proveedor` sigue conservando el literal: no se modifican ni los
datos ni la persistencia. El cálculo de `conciliar_importes` y el resto de
`buscar_candidato_albaran` no cambian.

## Python

- **`RepositorioRuntimeSupabase`:**
  - `reclamar_factura_manual_one_shot(worker_id)` es nueva;
  - `guardar_conciliacion` mantiene la revalidación previa (la barrera de farmacia
    y completitud, antes de cualquier escritura) y después hace una única RPC,
    `cf_persistir_conciliacion`;
  - `fallar_conciliacion(factura, codigo, detalle, worker_id, disparador="AUTOMATICO")`
    llama a `cf_registrar_fallo_conciliacion` con la clase de fallo.
- **`WorkerConciliacion`:**
  - `ejecutar_una()` sin cambios de comportamiento (`AUTOMATICO`);
  - `ejecutar_una_manual()` es nuevo: `MANUAL_ONE_SHOT`, como máximo 1 factura y sin
    selector alternativo.
- **`WorkerAutomatico`:** `ejecutar_una_manual_conciliacion()` es nuevo. No toca
  `ejecutar_una()` ni `ejecutar_una_manual()` de normalización.
- **`clasificacion_fallos.clasificar_fallo_conciliacion`:** nueva.

### Contratos modificados

- `guardar_conciliacion`: disparadores admitidos `AUTOMATICO` o `MANUAL_ONE_SHOT`,
  antes `AUTOMATICO`, `MANUAL`, `REINTENTO` o `TEST`. Motivo: R8, la RPC valida
  contra el modo del claim.
- `fallar_conciliacion`: recibe `worker_id` y `disparador`. Motivo: la RPC exige
  el claim del llamante.
- `RepositorioConciliacion` (Protocol): añade `reclamar_factura_manual_one_shot` y
  la firma nueva de `fallar_conciliacion`.
- Test estático de la barrera de farmacia (`test_barrera_farmacia.py`): la marca de
  la primera escritura de `guardar_conciliacion` pasa a ser la RPC.

## Compatibilidad

- Las firmas existentes se mantienen. `cf_reclamar_factura_conciliacion(text, integer)`
  pasa a ser envoltorio del núcleo, con el mismo selector, ordering y grants.
- `cf_evaluar_elegibilidad_conciliacion`, `cf_solicitar_reintento_conciliacion`,
  `cf_reintentar_todas_pendientes` y `cf_resultado_conciliacion` no se modifican.
- La ruta automática sigue funcionando con el flag a `true`. Con el flag a `false`
  no reclama nada salvo que haya un reintento solicitado.
- El Python de 2AV exige la migración 18 (usa sus RPC).
- Orden de reversión: primero el código y después el rollback SQL.

## Impacto sobre datos existentes

- Sin DML sobre las 12 conciliaciones ni sobre las facturas existentes; las columnas
  nuevas reciben sus defaults.
- Las conciliaciones existentes quedan con `idempotency_key` a null.
- El rollback solo ejecuta DML sobre valores nuevos de la 18:
  - `REVISION_CONCILIACION` → `PENDIENTE_CONCILIAR`;
  - `MANUAL_ONE_SHOT` → `MANUAL` en `conciliaciones.disparador`.

## Observación (no se corrige en 2AV)

Un resultado `DIFERENCIA` deja la factura en `PENDIENTE_CONCILIAR` sin backoff, igual
que antes. Con el automático activado se volvería a reclamar, aunque sin duplicar
filas: la misma evidencia da la misma clave y se trata como replay. Queda registrado
como observación para el despliegue.
