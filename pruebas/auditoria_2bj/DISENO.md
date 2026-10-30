# Hito 2BJ: serie supervisada de normalización (y después de conciliación)

2026-10-30. Las cifras salen de evidencias ya archivadas, con su etiqueta de certeza.

**Decisiones de Pio (2026-10-30), diseño aprobado:**
1. Tandas de 5 la primera y luego hasta 20, con corte al persistir cada Alliance.
2. Los defectos de extracción consumen intentos (R3); si el plan los preveía, **no** son parada.
3. Conciliación con un n.º 1 que simula DIFERENCIA: PARADA y Pio decide caso a caso.
4. Ejecuta Claude, con confirmación expresa de Pio por tanda.

Implementación (solo normalización, en local) en el apartado 9. La serie de conciliación queda para un hito
posterior, con la decisión 3.

## 0. Punto de partida

- **Hoy:** un `ejecutar_una_manual()` por hito, que reclama el n.º 1 del ordering oficial
  (`reprocesar_solicitado_at` primero, luego `fecha_importacion`, luego `id`). Lo hacen el compositor manual
  del 2AP (autoridad solo Alliance, `alliance-local`) y el procedimiento del 2AO rev3 (8 s para un PDF Alliance
  de 13 páginas). `CONFIRMADO EN PRODUCCIÓN` (2026-09-25).
- **Lo que no es Alliance** falla con `PROVEEDOR_NO_SOPORTADO_MANUAL`, que es `NO_SOPORTADO`: pasa a
  `PROVEEDOR_NO_SOPORTADO` y sale de la cola sin reintentos ni intentos (R2). Solo vuelve con
  `cf_solicitar_reprocesado`. `CONFIRMADO POR CÓDIGO` (`compositor_manual.py:180`,
  `clasificacion_fallos.py`).
- **Defectos del documento** (`EXTRACCION_LOCAL_ERROR`, SHA, storage…) son `DEFECTO_DOCUMENTO`: intento +1,
  backoff de 1 h, 6 h y 24 h, y `REVISION` al 4.º (R3). Un motivo desconocido es `TRANSITORIO`, con el mismo
  contador.
- **Desde el 2BI:** `worker_id` único por ejecución, Ctrl+C que registra el fallo, y recuperación de huérfanos
  (25 desplegada). La conciliación sigue con el procedimiento del 2AT (envoltorio del 2BD-D).
- **Cola:**
  - Medida en el 2AU (2026-09-25, `CONFIRMADO POR CERTIFICACIÓN ARCHIVADA`): 137 documentos `PENDIENTE`; 9
    documentos Alliance reconocidos (35 facturas); 71 sin layout reconocido; 16 con error de extracción local;
    1 ausente del mirror.
  - Hoy: `documentos_facturas` = 178 (preflight del 2BI-D, 2026-10-30). Normalizados unos 6 (`INFERIDO`), así
    que quedan **unos 172 en cola**.
- **Banco Alliance** (`evidencias_2az/banco/motor.json`, mirror local):
  - 160 documentos, **12 Alliance con 47 facturas**; 2 ya normalizados en producción (08007969–73 y
    08009277–79);
  - **quedan 10 documentos Alliance con 39 facturas**;
  - los ~18 documentos importados después del banco no están medidos: los mide el plan (apartado 1).

## 1. Tanda, plan y quién ejecuta

- **Ejecuta Pio en terminal**, con un script nuevo (`pruebas/auditoria_2bj/serie_normalizacion.py`, con el
  patrón del 2AT y el 2BI). Claude prepara el plan y los postchecks READ_ONLY, y Pio confirma cada tanda en el
  chat.
- **Una ejecución sigue siendo un `ejecutar_una_manual()`** (1 documento, `MANUAL_ONE_SHOT`, sin
  preselección, sin flags): no se activa ninguna automatización. La tanda solo encadena N llamadas, cada una
  con sus puertas. **Esto cambia la práctica de «una por hito»: requiere el OK de Pio.**
- **`plan`** (READ_ONLY, sin escrituras):
  - lee la cola en el ordering oficial (el mismo selector reproducido del 2AT);
  - para cada documento predice el resultado con la extracción local del mirror, sin persistir:
    `ALLIANCE_NORMALIZABLE` (con sus facturas, números y totales), `NO_SOPORTADO` o `DEFECTO` (con el motivo).
    Es la medición del 2AU, repetida hoy;
  - se guarda como `plan.json` fuera del repositorio, con SHA.
- **Tamaño de tanda** (propuesta):
  - **tanda 1: 5 ejecuciones** (rodaje);
  - **después, hasta 20**;
  - **toda tanda termina inmediatamente después de un documento Alliance persistido**, aunque no haya llegado
    a N. Ese documento crea facturas y tiene postcheck propio.

  Un `NO_SOPORTADO` solo cambia la fila del documento y una ejecución; agruparlos es seguro y barato.
- **Guard por tanda** (`tanda_<n>.guard`, exclusivo y que no se borra) y registro JSON por ejecución. Sin
  reintentos.

## 2. Puertas y PARADA

**Antes de cada ejecución** (READ_ONLY, dentro del script):
- flags `f|f|f|{PIO}`, tolerancia y `cf_configuracion` iguales a los del preflight de la tanda;
- 0 documentos en `NORMALIZANDO`, `cf_huerfanos_normalizacion('30 minutes')` vacío, 0 locks y claims, 0
  workers;
- tareas programadas a 60 min o más y ninguna en ejecución (`Get-ScheduledTaskInfo`);
- n.º 1 del selector = siguiente documento del plan, con la huella de su fila igual a la del plan;
- sin la 25 o con esquema distinto del preflight → PARADA.

**PARADA inmediata** (no se ejecuta nada más en la tanda; Claude diagnostica y Pio decide):
- excepción del proceso, `RETORNO` distinto de 1 documento reclamado, o interrupción;
- **huérfano:** documento en `NORMALIZANDO` tras la llamada (ver apartado 5);
- **resultado inesperado** respecto del plan:
  - un Alliance que no queda `NORMALIZADA`, o con un número de facturas, números o totales distintos del plan;
  - un previsto `NO_SOPORTADO` que acaba con otro estado;
  - cualquier `TRANSITORIO`;
  - un `DEFECTO` no previsto;
- **diferencia de huellas:** alguna fila cambiada fuera del documento reclamado y de sus filas nuevas
  (ejecución, facturas, extraídos, movimientos, vencimientos e historial de ese documento);
- `REVISION` de un documento, por R3 o por persistencia `PARCIAL`/`REQUIERE_REVISION`.

## 3. Postcheck entre tandas (criterio 2AX por fila)

Snapshot por fila antes y después de la tanda (columnas declaradas del 2AT; 10 tablas, incluidas `albaranes`,
`albaranes_cambios` y las reservas). Sale `POSTCHECK_OK` solo si:
- en `documentos_facturas` cambian solo las filas de los documentos reclamados en la tanda, con transiciones
  `PENDIENTE`/`ERROR` → el estado previsto por el plan;
- las filas nuevas (ejecuciones, facturas, extraídos, movimientos, vencimientos e historial) son todas de esos
  documentos, y las facturas coinciden en número y totales con el plan;
- no cambia ninguna fila de `facturas` previas, `conciliaciones`, `conciliacion_detalles`, reservas,
  `albaranes`, `albaranes_cambios`, aprobaciones ni aplicaciones;
- esquema, privilegios, `cf_configuracion` y operación son idénticos; 0 en `NORMALIZANDO`; 0 huérfanos.

Si sale cualquier otra cosa → `POSTCHECK_REVISAR`: PARADA de la serie, sin rollback salvo confirmación de Pio.

## 4. No Alliance, Alliance con incidencias y fallos (R3)

- **No Alliance (unos 160):** `PROVEEDOR_NO_SOPORTADO` y fuera de la cola (R2). No es un error: es el resultado
  esperado. Quedan registrados para hitos de proveedor (COFARES, HEFAME y los demás) y vuelven con
  `cf_solicitar_reprocesado` cuando haya autoridad.
- **Alliance con incidencias:**
  - facturas no autorizables o persistencia `PARCIAL` → PARADA (revisión de Pio), aunque el plan lo previera;
  - avisos no bloqueantes (moneda o vencimiento) → se anotan y no paran si el plan los preveía;
  - `FACTURA_DUPLICADO` → `OTRO` es una deuda conocida (2AO rev3), no para.
- **Defectos (los 16 con error de extracción del 2AU):**
  - el plan dice cuáles son; cada ejecución consume un intento y el documento vuelve con backoff;
  - **propuesta:** el script no los retoma a propósito. Si vuelven al n.º 1 tras el backoff, cuentan como una
    ejecución prevista más;
  - al 4.º pasan a `REVISION` (R3).

  Coste: hasta 4 ejecuciones por documento repartidas en unas 31 h. Si Pio prefiere no consumir intentos en
  documentos que se sabe que fallan, haría falta un hito propio (por ejemplo, apartarlos con un estado o una
  marca): **decisión de Pio**.
- `TRANSITORIO` (motivo desconocido) siempre para la tanda.

## 5. Ventanas y huérfanos

- **Ventana:**
  - no se empieza una tanda entre las 20:00 y el final de la sincronización (unas 21:45, hora local de
    invierno): la importación es a las 21:00 y la sincronización a las 21:30, con margen de 60 min;
  - cada tanda (preflight, ejecución y postcheck) termina antes de las 20:00, porque la noche cambia
    `albaranes` y `documentos_facturas` y el postcheck por fila fallaría;
  - la serie se reparte en días, con un preflight nuevo cada día.
- **Huérfanos:**
  - con el 2BI, Ctrl+C ya registra el fallo; un huérfano solo queda si muere el proceso o el PC;
  - si aparece: PARADA;
  - pasados 30 min, `recuperar_huerfanos.py informe` y, con confirmación de Pio, `recuperar <documento>`;
  - la serie no sigue hasta que `cf_huerfanos_normalizacion` esté vacío.

## 6. Después de normalizar: serie de conciliación (mismo esquema)

- Mismo procedimiento del 2AT (envoltorio del 2BD-D), en tandas: preflight, snapshot, simulación del n.º 1 y
  ejecución, con postcheck por fila entre tandas (solo cambian la factura, sus filas nuevas y sus reservas).
- **Puerta adicional:** solo se ejecuta si la simulación del n.º 1 es **CONCILIADA**.
- **Si el n.º 1 simula DIFERENCIA:** PARADA, porque una DIFERENCIA persiste una conciliación vigente,
  **reserva sus albaranes (R15)** y consume un intento (D-A). Pio decide en cada caso: ejecutarla, diagnosticar
  (como 08007970) o dejarla. Mientras no se ejecute, bloquea la cola, porque el ordering es por fecha.
- Tanda de conciliación: hasta 10 CONCILIADA seguidas, cortando en la primera simulación que no sea CONCILIADA.

## 7. Estimación (`INFERIDO`)

| | Cifra |
|---|---|
| Documentos en cola | ~172 (178 − ~6 normalizados) |
| Alliance (banco) | 10 documentos, **39 facturas** (+ las Alliance de los ~18 documentos posteriores, sin medir) |
| No Alliance → `PROVEEDOR_NO_SOPORTADO` | ~160 ejecuciones |
| Defectos (R3) | hasta 16 documentos × 4 intentos, repartidos en ~31 h |
| Tandas de normalización | ~10 cortadas por Alliance + ~8 de 20 no soportados → **~18 tandas** |
| Tiempo por tanda | ~2 min de preflight + 1–3 min de ejecución (2–8 s por documento) + ~2 min de postcheck ≈ **6–8 min** |
| Tiempo total de normalización | **~2–2,5 h de supervisión**, en 2–3 días por ventanas y backoff |
| Facturas Alliance conciliables | simulación con R17 y R19 y los albaranes del 29–30/10: **29 CONCILIADA y 10 DIFERENCIA** (08006568, 08006571, 08007499, 08008427, 08009716, 08010085, 08010461, 08011304, 08011733 y 08011734) |
| Tandas de conciliación | ~3–4 de CONCILIADA más hasta 10 PARADAS por DIFERENCIA |

Fuente de la simulación: `evidencias_2be/verificacion_src_2be.json` más los cambios de R19 de
`evidencias_2bg/medicion.json`, sobre el banco del 2AZ y con las reservas vigentes del 29/10. Cambiará con
albaranes nuevos, con correcciones en Farmatic y con facturas que no estén en el banco.

## 8. Decisiones de Pio

1. Serie de N `ejecutar_una_manual()` por tanda con confirmación por tanda, en lugar de una por hito. Tamaño
   5, luego hasta 20, cortando en cada Alliance.
2. Defectos conocidos: dejar que consuman sus 4 intentos (R3) o apartarlos antes en un hito propio.
3. Conciliación: tratamiento de un n.º 1 que simula DIFERENCIA (PARADA y decisión caso a caso, según la
   propuesta).
4. Quién ejecuta las tandas: Pio en terminal (propuesta) o Claude con confirmación expresa por tanda, como en
   el 2BE-D y el 2BI-D.

Implementación (siguiente hito, solo local):
- script `serie_normalizacion.py` (`plan`, `tanda`, `postcheck`) y, después, el equivalente de conciliación;
- ensayo completo en PostgreSQL 17 local con la cola simulada: Alliance, no soportados, defectos, huérfano
  y resultado inesperado;
- suite completa y revisor.

## 9. Implementación (`CONFIRMADO POR TEST` en PostgreSQL 17 local; sin ejecución productiva)

`pruebas/auditoria_2bj/serie_normalizacion.py`:
- **`plan <plan.json> [mirror]`** (READ_ONLY):
  - lee la cola en el ordering del núcleo de la 16 (modo `MANUAL_ONE_SHOT`), incluidos los documentos que
    están en backoff;
  - predice cada documento con `banco_extraccion._analizar` (la cadena oficial en memoria) sobre el PDF del
    mirror con el mismo SHA;
  - traduce el resultado al motivo y la clase que registra el worker real (`prediccion_desde_analisis`):
    `ALLIANCE` (facturas, números, totales y si son autorizables), `NO_SOPORTADO`, `DEFECTO` o
    `SIN_PREDICCION`.
- **`tanda <n> <plan.json> <directorio>`:**
  - tamaño: máximo 5 si en el directorio padre no hay ninguna tanda `TANDA_OK`, y 20 en otro caso;
  - guard `tanda.guard` exclusivo;
  - preflight y snapshot por fila (todas las tablas de `public`, con su clave y su documento resueltos desde
    `information_schema`).
  - Antes de cada ejecución, puertas:
    - flags, tolerancia y locks del 2AT, y configuración igual a la del preflight;
    - la 25 presente; 0 en `NORMALIZANDO`, 0 claims y 0 huérfanos;
    - tareas a 60 min o más;
    - el n.º 1 está en el plan, con el mismo SHA y con predicción.
  - UNA llamada a `ejecutar_una_manual()` con el compositor manual del 2AP (`worker_id` base `cf-2bj-serie`,
    con sufijo único por ejecución).
  - Comprobación tras cada ejecución:
    - retorno (1 si persiste un Alliance; 0 si el fallo queda registrado);
    - estado, clase de fallo e intentos previstos (un defecto pasa a `REVISION` al máximo de R3);
    - facturas, con números y totales del plan;
    - sin huérfano;
    - filas: solo nuevas del documento y cambios en su fila.
  - Cualquier desviación → `PARADA`.
  - Corte tras cada Alliance; si la cola se vacía a mitad de tanda, se cierra.
  - Postcheck 2AX por fila de la tanda completa: solo los documentos reclamados, configuración y flags
    iguales, sin `NORMALIZANDO` ni huérfanos.
- Sin reintentos. Cada ejecución deja su JSON, más `tanda.json` y los snapshots, todo fuera del repositorio.

Tests `tests/facturas/runtime_supabase/test_serie_normalizacion_2bj.py`:
- **Sin BD:** traducción de predicciones (7 casos) y defecto → `REVISION` al máximo.
- **PostgreSQL 17 local**, con una cola real: HEFAME no autorizado, un PDF roto y el Alliance multifactura del
  2AP.
  - Plan en orden y de solo lectura (3 facturas Alliance).
  - Primera tanda limitada a 5.
  - Tanda hasta el corte Alliance (`PROVEEDOR_NO_SOPORTADO`, `ERROR` y `NORMALIZADA` con 3 facturas), con
    postcheck OK.
  - Guard.
  - Segunda tanda con máximo 20 y cola vacía → PARADA sin escrituras.
  - PARADAS:
    - resultado distinto del plan;
    - n.º 1 fuera del plan o sin predicción (antes de ejecutar y sin escrituras);
    - excepción;
    - huérfano;
    - fila ajena cambiada;
    - puertas de flags, tareas y `NORMALIZANDO` (sin escrituras).
