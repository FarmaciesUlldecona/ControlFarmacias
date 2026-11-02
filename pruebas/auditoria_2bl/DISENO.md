# Hito 2BL: un fallo registrado no bloquea el reintento de la persistencia (migración 27)

Solo local. La serie 2BJ está en pausa hasta desplegar la 27 (decisión de Pio, 2026-11-02). Sin push.

## 1. Problema (tanda 6, 2026-11-02)

El Alliance de la posición 57 (08007499–502) falló en la tanda 6 con `IDEMPOTENCIA_PAYLOAD_DISTINTO` (P0001),
clasificado `DEFECTO_DOCUMENTO`. Ya tenía la 26 desplegada, pero la RPC falló antes de llegar a la búsqueda
indexada. Evidencias: `C:\ControlFarmacias\evidencias_2bj\tanda_06*`.

1. El worker calcula la clave de idempotencia a partir del hash del resultado
   (`src/facturas/runtime_supabase/worker_normalizacion.py:83-85`). Si la persistencia falla, registra el fallo
   con esa misma clave (líneas 100-108).
2. En la tanda 5, el `statement_timeout` dejó una ejecución en `ERROR` con esa clave y sin `resultado_json`.
3. En el reintento (mismo PDF, mismo hash, misma clave):
   - la multifactura encontraba la fila en `ERROR` y la trataba como una repetición; al comparar la firma
     (nula) la rechazaba siempre;
   - la RPC de un documento devolvía la ejecución del fallo como si fuera un replay, **sin persistir nada**.

Defecto presente desde la 15/17, no introducido por la 26. Cualquier documento cuya persistencia fallase una vez
de forma transitoria no podía guardarse nunca reintentando.

## 2. Migración 27 (decisión de Pio)

`sql/migrations/27_cf_reintento_tras_fallo_de_persistencia.sql`, generada por `generar_migracion_27.py` a
partir del texto literal de la 26. Cada sustitución se comprueba y un test verifica que el fichero coincide con
el generador.

1. **`cf_ejecucion_persistida(documento, clave)`**, interna (solo propietario): la ejecución que hace de
   repetición, es decir, la persistida con esa clave o con su clave derivada `<clave>:intento:<n>`. Una ejecución
   en `ERROR` sin resultado persistido (`estado = 'ERROR' and resultado_json is null`) nunca lo es.
2. Los dos núcleos y el envoltorio de 7 parámetros usan esa función para detectar la repetición.
3. **Intento nuevo con fila y clave propias:** si la clave ya la ocupa un fallo, la ejecución persistida usa
   `<clave>:intento:<n>` (`unique (documento_id, idempotency_key)`), el mismo patrón de
   `cf_registrar_fallo_normalizacion`.
4. **Sin cambios:** ejecución persistida con la misma solicitud → replay como hoy (con su evento
   `NORMALIZACION_REPLAY_IDEMPOTENTE`); multifactura con otra firma → `IDEMPOTENCIA_PAYLOAD_DISTINTO` como hoy;
   la RPC de un documento no compara el payload, como hoy.
5. Firmas, privilegios de las RPC y filas existentes no cambian. Requiere la 26 (`MIGRACION_26_AUSENTE`).
6. **Rollback:** devuelve literalmente las funciones de la 26 y quita `cf_ejecucion_persistida`. Esquema idéntico
   al de la 26 (test).

## 3. Clasificación del fallo

`IDEMPOTENCIA_PAYLOAD_DISTINTO` pasa de `DEFECTO_DOCUMENTO` a `TRANSITORIO`
(`src/facturas/runtime_supabase/clasificacion_fallos.py`): es un conflicto con una ejecución ya registrada, no
un defecto del documento. Ambas clases tienen el mismo tratamiento (reintentos acotados con backoff y `REVISION`
al máximo); cambia la etiqueta. `INVENTARIO_RELECTURA_INCOMPATIBLE` sigue como `DEFECTO_DOCUMENTO`. Un timeout
(57014) ya era `TRANSITORIO`.

## 4. Tests (`test_integracion_pg17_2bl.py`, 24)

- **Fallo transitorio → reintento guarda**, en la multifactura y en la RPC de un documento: con la 26 se
  reproduce el defecto de producción; con la 27, `NORMALIZADA/COMPLETA`, fallo (intento 1, clave original) y
  persistencia (intento 2, `<clave>:intento:2`).
- **Replay** con la misma solicitud: misma ejecución; solo se añade el evento de replay de siempre.
- **Payload distinto** tras persistir: rechazo en la multifactura y ninguna escritura.
- **Camino completo con el worker manual real:** la primera llamada a la RPC multifactura cae como el timeout de
  producción, el worker registra el fallo y el reintento persiste las 3 facturas del PDF Alliance del 2AP.
- **Equivalencia 26 = 27 sin fallo previo** en los 9 escenarios del 2BK.
- Clasificación; generador reproducible; rollback igual a la 26; exige la 26; no altera datos; privilegios;
  `desplegar_27.py` ensayado (aplicada; el segundo intento se revierte) y rechazo de un SQL distinto del commit.

## 5. Estado en producción del Alliance de la posición 57

`ERROR`, 2 de 4 intentos, reclamable desde las 22:38 UTC del 2026-11-02, dos ejecuciones en `ERROR` (la del
timeout con la clave original y la de la tanda 6 con `:intento:2`). Con la 27, el reintento persistiría con
`<clave>:intento:3`. Con la normalización automática desactivada no se reintenta solo.

## 6. Serie 2BJ: la 27 es puerta

Decisión de Pio: `serie_normalizacion.py tanda` comprueba antes de cada ejecución las marcas de la 27
(`cf_ejecucion_persistida` existe y la usan los dos núcleos y el envoltorio de 7 parámetros). Si faltan, la tanda
para sin ejecutar con `MIGRACION_27_AUSENTE` (test con las plantillas 26 y 27_rollback). Los tests de la serie
usan ahora la plantilla 27.

## 7. Pendiente (con confirmación de Pio)

1. Preflight READ_ONLY y despliegue de la 27 con `desplegar_27.py` (commit y SHA) y postcheck 2AX.
2. Reanudar la serie (tanda: el Alliance de la posición 57 en reintento, tras los defectos previstos).
