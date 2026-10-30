# Hito 2BI: recuperación de claims huérfanos de normalización

2026-10-30. Solo local. Producción, Farmatic y Task Scheduler no tocados.

**Decisiones de Pio (2026-10-30):**
- diseño aprobado, con la **opción A** (script one-shot `informe`/`recuperar`, guard y confirmación de Pio);
- gracia de **30 min**;
- mejoras de Python: capturar Ctrl+C/`SystemExit` para registrar el fallo, y `worker_id` único por
  ejecución;
- conciliación sin hito: ya diagnosticada en el 2AT (el claim no cambia de estado, el lock caduca y el
  guardado es atómico desde la 18).

La implementación está en el apartado 6.

Nota: el pendiente «claims huérfanos de normalización» **no figura en `docs/contexto/ESTADO_ACTUAL.md`**
(búsqueda de «huérfano», «claim … caducado/NORMALIZANDO» sin resultados; solo hay conteos
«NORMALIZANDO 0» en los preflight). Se trata como encargo nuevo de Pio.

## 1. Diagnóstico

### Código (`CONFIRMADO POR CÓDIGO`)

- **Claim** (`cf_reclamar_documento_normalizacion_nucleo`, migración 16, común a la ruta automática y a
  `MANUAL_ONE_SHOT`): toma un documento `PENDIENTE`/`ERROR` sin backoff ni lock vigente y, en la misma
  transacción, pone `estado_lectura = NORMALIZANDO`, `bloqueado_por = worker`,
  `bloqueado_hasta = now() + 300 s` (`repositorios.py:185` y `:195`) y un evento `NORMALIZACION_CLAIM` con el
  `modo_ejecucion`. **No crea ejecución.**
- **Persistencia** (`cf_persistir_normalizacion` y `cf_persistir_documento_multifactura`, migración 17): una
  sola transacción (ejecución, facturas, inventario y estado final, o nada). Exige
  `bloqueado_por = worker`, pero **no mira `bloqueado_hasta`**: un worker lento con el lock caducado
  todavía puede persistir.
- **Fallo** (`cf_registrar_fallo_normalizacion`, 17): misma comprobación de `bloqueado_por`; aplica R2/R3
  (intento + backoff 1 h/6 h/24 h, `REVISION` al 4.º) y libera el lock.
- **Python** (`worker_normalizacion.py:93`): `except Exception` → `fallar_ejecucion`. No llegan a registrar
  el fallo:
  - `KeyboardInterrupt` (Ctrl+C) y `SystemExit`, que no son `Exception`;
  - matar el proceso o cerrar la terminal;
  - suspender o apagar el PC;
  - un corte de red o un error **dentro** de `fallar_ejecucion`.
- No hay latido de worker: los workers usan REST (PostgREST), no aparecen en `pg_stat_activity` y ninguna
  tabla registra si siguen vivos. Desde la BD **no se puede demostrar** que un worker esté muerto; solo que su
  lock caducó hace tiempo.

### Reproducción en PostgreSQL 17 local (plantilla `24` = esquema productivo; `CONFIRMADO POR TEST` manual)

Claim `MANUAL_ONE_SHOT` con lock de 1 s y proceso «muerto» (no persiste ni registra fallo):

| | Tras el claim | Lock caducado |
|---|---|---|
| `estado_lectura` | `NORMALIZANDO` | `NORMALIZANDO` |
| `bloqueado_por` | `w-muere` | `w-muere` |
| lock | vigente | caducado |
| `estado_persistencia` | `PENDIENTE` | `PENDIENTE` |
| intentos / backoff | 0 / null | 0 / null |
| ejecuciones / facturas | 0 / 0 | 0 / 0 |
| historial | `NORMALIZACION_CLAIM` | `NORMALIZACION_CLAIM` |

- Reclamable de nuevo: **no**, ni manual ni automático (el selector solo admite `PENDIENTE`/`ERROR`).
- `cf_registrar_fallo_normalizacion` por otro worker: `claim no pertenece al worker`.
- La ruta automática deja lo mismo: comparte el núcleo y solo cambia el filtro del interruptor global.
- **Única salida actual: `cf_solicitar_reprocesado`**, que pone `PENDIENTE` en cualquier estado, borra el
  lock aunque el worker siga vivo, **reinicia el contador de intentos** (no cuenta como intento, contra R3) y
  no comprueba persistencia.

### Producción

Sin documentos en `NORMALIZANDO`: «NORMALIZANDO 0» en todos los preflight READ_ONLY, el último el
2026-10-30 a las 09:22 UTC (conciliación de 08007970). La normalización solo se ejecuta a mano (one-shot);
las tareas nocturnas no importan `runtime_supabase`. El riesgo real hoy es una ejecución manual interrumpida.

## 2. Qué es un huérfano

Un documento es **candidato** si:
- `estado_lectura = NORMALIZANDO`;
- `bloqueado_por` no nulo;
- farmacia habilitada;
- `bloqueado_hasta < now() - gracia`.

Como no hay latido, «sin worker vivo» se aproxima con una **gracia** larga sobre el lock (propuesta: 30 min
sobre los 300 s del claim, es decir, 35 min desde el claim; mínimo admitido 15 min). Si aun así el worker
seguía vivo, falla cerrado: al recuperar se borra `bloqueado_por`, y su persistencia o su registro de fallo
posteriores fallan con `claim no pertenece al worker`, sin escribir nada. Pierde su trabajo, no corrompe nada.
Ambos caminos bloquean la fila (`for update`), así que no hay carrera: el primero gana y el segundo ve el
estado ya cambiado.

**Persistencia parcial → revisión.** La persistencia es atómica, así que un huérfano «normal» no tiene nada
persistido. Cualquiera de estas señales indica un estado incoherente y se manda a revisión, sin
reencolar:
- `estado_persistencia ≠ PENDIENTE`;
- facturas enlazadas al documento (incluidas las de una normalización anterior reprocesada: en la duda,
  revisión);
- ejecuciones posteriores al último `NORMALIZACION_CLAIM`;
- un último evento del historial que no sea ese claim, o de otro actor.

## 3. Propuesta (migración 25, solo local hasta su despliegue)

RPC `cf_recuperar_claim_huerfano_normalizacion(p_documento_id uuid, p_actor text, p_gracia interval)`:
SECURITY DEFINER, EXECUTE solo `service_role`, una transacción con `for update` sobre el documento.

| Situación | Efecto | Resultado |
|---|---|---|
| No existe, farmacia no habilitada o `p_gracia` < 15 min | nada | excepción |
| No está en `NORMALIZANDO` (ya persistido, ya recuperado, reprocesado…) | nada | `NO_APLICA` + estado actual (idempotente) |
| Lock vigente o caducado hace menos que la gracia | nada | `LOCK_VIGENTE` |
| Huérfano limpio | llama a `cf_registrar_fallo_normalizacion` con `p_worker_id = bloqueado_por`, clase `TRANSITORIO`, código `CLAIM_HUERFANO`, disparador = `modo_ejecucion` del claim, clave `huerfano:{documento}:{id del evento de claim}`; + evento `NORMALIZACION_CLAIM_HUERFANO` (actor, worker, claim, lock, gracia) | `RECUPERADO`: `ERROR` con backoff o `REVISION` al máximo |
| Huérfano con señales de persistencia parcial | `estado_lectura = REVISION`, lock liberado, sin tocar facturas, ejecuciones ni contadores; evento `NORMALIZACION_CLAIM_HUERFANO_REVISION` con las señales | `REVISION` |

- **Cuenta como intento (R3):** se reutiliza `cf_registrar_fallo_normalizacion` tal cual, con el mismo
  contador, backoff y paso a `REVISION` al 4.º y el mismo historial `NORMALIZACION_ERROR`. No se duplica la
  lógica.
- **Idempotente:**
  - la clave depende del evento de claim, así que repetir la llamada sobre el mismo huérfano no crea otra
    ejecución;
  - una vez recuperado, el documento ya no está en `NORMALIZANDO`, así que la siguiente llamada devuelve
    `NO_APLICA` sin escrituras.
- Una función auxiliar `cf_huerfanos_normalizacion(p_gracia)` (solo lectura) lista candidatos y señales.
- Ningún cambio en el claim, el selector, la persistencia ni `cf_solicitar_reprocesado` (R4 intacta).

## 4. Quién lo ejecuta (decisión de Pio)

- **Opción A, recomendada: script one-shot** `pruebas/auditoria_2bi/recuperar_huerfanos.py`, con el patrón
  2AT/2BF:
  - `informe`: READ_ONLY, lista candidatos, clasificación prevista y señales;
  - `recuperar <documento>`: un documento, confirmación de Pio, guard por documento y claim, sin
    reintentos, y comprobación posterior por huellas.

  Motivo: sin latido no se puede demostrar que el worker esté muerto, y hoy la normalización es manual.
  Una recuperación silenciosa en el claim podría quitarle el trabajo a un worker lento sin que nadie lo vea.
- **Opción B: al reclamar.** El núcleo del claim recupera primero los huérfanos con gracia vencida. Así se
  automatiza, pero cambia R4, el selector certificado y la ruta automática. Conviene solo cuando haya latido
  de worker y normalización automática activa.
- En ambas: preflight READ_ONLY (`NORMALIZANDO` > 0) en los preflight del 2AT ya existentes.

Mejoras complementarias de Python (no cambian la recuperación; se proponen para el mismo hito):
- `worker_normalizacion.py`: capturar también `KeyboardInterrupt` para registrar el fallo y volver a
  lanzarla, de modo que Ctrl+C deje de crear huérfanos;
- `worker_id` único por ejecución en los scripts one-shot. Hoy son fijos (p. ej.
  `cf-2ao-manual-one-shot`), y un mismo id en una ejecución posterior podría persistir sobre el claim de
  otra.

## 5. Tests previstos (PostgreSQL 17 local, plantilla `24` + 25)

- Huérfano limpio (ruta manual y automática):
  - `RECUPERADO`, `ERROR` con backoff, intento +1, ejecución `ERROR` con clase `TRANSITORIO` y código
    `CLAIM_HUERFANO`, historial;
  - vuelve a ser reclamable al vencer el backoff.
- 4.º huérfano seguido → `REVISION` (R3).
- Idempotencia: segunda llamada `NO_APLICA` sin escrituras (huellas idénticas).
- Lock vigente o dentro de la gracia → `LOCK_VIGENTE`, sin escrituras; gracia < 15 min → excepción.
- Señales de persistencia parcial (cada una) → `REVISION` sin tocar facturas ni ejecuciones.
- Worker lento que persiste después de la recuperación → `claim no pertenece al worker`, sin escrituras;
  persistencia que gana la carrera → `NO_APLICA`.
- Farmacia no habilitada (RITA) → excepción; privilegios (solo `service_role`; `anon`/`authenticated`
  denegados); rollback = esquema 24.
- Script `informe` de solo lectura y ensayo completo de `recuperar` (norma 2AX), más `desplegar_25.py` con
  su ensayo.

## 6. Implementación (`CONFIRMADO POR TEST` en PostgreSQL 17 local; migración 25 **NO desplegada**)

- **Migración 25** `sql/migrations/25_cf_claims_huerfanos_normalizacion.sql` (+ rollback = esquema 24 exacto;
  exige la 24; idempotente; no modifica filas). Solo funciones nuevas:
  - `cf_senales_claim_huerfano(uuid)`: auxiliar, solo propietario;
  - `cf_huerfanos_normalizacion(interval)`: STABLE, SECURITY DEFINER, solo `service_role`;
  - `cf_recuperar_claim_huerfano_normalizacion(uuid, text, interval)`: SECURITY DEFINER, solo
    `service_role`; resultados `NO_APLICA`, `LOCK_VIGENTE`, `RECUPERADO` y `REVISION`; excepciones
    `GRACIA_INSUFICIENTE` (menos de 15 min), `ACTOR_OBLIGATORIO` y `FARMACIA_NO_HABILITADA`.

  Privilegios: patrón de la 24.
- **Script** `pruebas/auditoria_2bi/recuperar_huerfanos.py`:
  - `informe`: sin escritura;
  - `recuperar <documento>`: configuración `f|f|f|{PIO}`, previsión `RECUPERABLE` o `REVISION` en el
    informe, guard `recuperar_huerfano_<documento>.guard`, una llamada y sin reintentos;
  - gracia de 30 min.
- **Despliegue** `pruebas/auditoria_2bi/desplegar_25.py`, con el patrón de la 24 (SHA contra el commit,
  9 precondiciones de solo lectura y postcondiciones de datos, RPC y privilegios).
  - Ensayo completo con commit real en un repositorio git temporal (copia byte a byte del script y de la
    migración). Así no hace `skip` antes del commit, que con la norma del 2BH impediría registrar la suite
    como completa.
  - El segundo intento falla en precondiciones y revierte.
- **Python** `src/facturas/runtime_supabase/worker_normalizacion.py`:
  - `worker_id` único por ejecución (`<base>#<12 hex>`), el mismo para el claim, la persistencia y el fallo
    de esa ejecución;
  - `KeyboardInterrupt`/`SystemExit` registran el fallo (cuenta como intento, R3) y se relanzan; si el
    registro también falla, la interrupción original se conserva y el claim queda para la 25.
  - La conciliación no cambia (`construir_worker_manual_productivo` sigue pasando el mismo id base).
- **Tests:**
  - `tests/facturas/runtime_supabase/test_integracion_pg17_2bi.py`:
    - esquema, privilegios, rollback y la 25 exige la 24;
    - huérfano limpio por la ruta manual y la automática, y vuelta a la cola;
    - 4.º → `REVISION`;
    - idempotencia, lock vigente o dentro de la gracia, gracia mínima, actor obligatorio y RITA;
    - cuatro señales de persistencia parcial → `REVISION` sin tocar facturas ni ejecuciones;
    - worker vivo que persiste o registra el fallo tras la recuperación → `claim no pertenece al worker` sin
      escrituras; worker que cierra antes → `NO_APLICA`;
    - Ctrl+C con el worker y la RPC reales ya no deja huérfano;
    - script `informe`/`recuperar`, guard, lock vigente y configuración inesperada;
    - precondiciones de solo lectura, ensayo de `desplegar_25.py` y rechazo de un SQL distinto del commit.
  - `tests/facturas/runtime_supabase/test_worker_normalizacion_2bi.py` (sin BD).
  - Cambios de contrato en tests existentes:
    - `test_integracion_pg17_2aq.py`: el `bloqueado_por` del escenario D1 es ahora `manual-2aq-dos#…`;
    - `test_estado_lectura_compatibilidad.py`: el inventario de writers literales incluye `REVISION`, que
      está en el check desde la 08b;
    - plantillas `25`/`25_rollback` en `pg17_local.py` y lista de migraciones en
      `test_modelo_supabase_v1.py`.
