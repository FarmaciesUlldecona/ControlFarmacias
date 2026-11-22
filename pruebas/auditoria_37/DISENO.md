# Migración 37: defectos de extracción directos a REVISION. DISEÑO

Estado: **IMPLEMENTADA EN LOCAL (2026-11-21)**, con las decisiones de Pio D1–D7 (D1–D4 el 2026-11-18 y D5–D7 el
2026-11-19); `CONFIRMADO POR TEST` en PostgreSQL 17 local, sin desplegar (37-D pendiente). Implementación: §10. Encargo de Pio del 2026-11-15, con el orden del 2026-11-16. Es la **migración 37** (renumerada el
2026-11-19, decisión de Pio: R20 = 36, defectos = 37, Cashflow = 38): se despliega después de la 36.

- **Decisión de Pio (2026-11-15):**
  - los defectos de extracción pasan **directamente a `REVISION`, sin reintentos**;
  - los fallos pasajeros siguen con reintentos y espera (R3);
  - un documento en `REVISION` por defecto solo vuelve a intentarse con un **reprocesado explícito cuando cambie el
    lector**.
- **Etiquetas:** `CONFIRMADO POR CÓDIGO` (con fichero:línea), `CONFIRMADO POR LECTURA READ_ONLY` (§1) y `PROPUESTA`.
  Lo que necesita a Pio está en §8.

## 0. Decisiones de Pio (2026-11-18)

| Id | Decisión |
|---|---|
| **D1** | **Solo los motivos de EXTRACCIÓN** van directos a `REVISION`. Los motivos de **almacenamiento** siguen como pasajeros, con reintentos y espera. La lista concreta, para que Pio la confirme, está en §2.1 |
| **D2** | Reprocesado: **opción B**, una columna con la versión del lector en `normalizacion_ejecuciones` (§3) |
| **D3** | Los **22 documentos en `REVISION`** de hoy **esperan a que cambie el lector** |
| **D4** | El defecto **cuenta un intento** |
| **D5** | **Lista de §2.1 confirmada (2026-11-19):** A (extracción) y B (identidad de farmacia) van **directas a `REVISION`**; C (almacenamiento) es **transitoria** |
| **D6** | La versión del lector llega a la RPC por un **8.º parámetro** `p_lector jsonb` (opción (a) de §8) |
| **D7** | **AUTORIZACIÓN EXPRESA DE PIO (2026-11-19):** nombrar el rol del sistema **SOLO** en `sql/migrations/37_*.sql` y su rollback (para el EXECUTE de la firma nueva). Tests, scripts y documentación no lo nombran; cualquier otro fichero, autorización nueva. Se registra en REGLAS_CRITICAS al implementar la 37 |

## 1. Situación actual

### 1.1 Código

`CONFIRMADO POR CÓDIGO`:

- **Clasificación** en `src/facturas/runtime_supabase/clasificacion_fallos.py`:
  - `NO_SOPORTADO` → `PROVEEDOR_NO_SOPORTADO` (R2), sin consumir intentos;
  - `DEFECTO_DOCUMENTO`: los 23 motivos de `MOTIVOS_DEFECTO_DOCUMENTO` (`clasificacion_fallos.py:26-50`), cualquier
    texto con `INVENTARIO_RELECTURA_INCOMPATIBLE` (`:68-69`) y los códigos `ErrorCompletitudDocumental` y
    `ErrorFarmaciaDocumental` (`:54-57`);
  - `TRANSITORIO`: todo lo demás. Un motivo desconocido es `TRANSITORIO` (`:72`).
- **El worker** clasifica y llama a la RPC con la clase (`repositorios.py:301-318`).
- **La RPC** `cf_registrar_fallo_normalizacion` de 7 parámetros
  (`sql/migrations/17_cf_replay_y_fallos_no_bloqueantes.sql:454-557`) trata igual `DEFECTO_DOCUMENTO` y
  `TRANSITORIO`: suma un intento y deja `ERROR` con espera (1 h, 6 h, 24 h) o `REVISION` al 4.º (`:516-528`).
  - La versión de 6 parámetros (`:561-577`) llama a la de 7 con `TRANSITORIO`.
  - La migración 25 la usa para los huérfanos limpios, con `TRANSITORIO` (`25_cf_claims_huerfanos_normalizacion.sql:163`).
  - Ninguna migración posterior a la 17 la redefine.
- **El reprocesado** `cf_solicitar_reprocesado` (`17_…sql:581-624`) devuelve el documento a `PENDIENTE`, reinicia
  intentos y clase, y deja `REPROCESADO_SOLICITADO` en el historial. Solo lo usa Pio: la 17 retira el EXECUTE de
  `anon` y `authenticated` (`:650-651`).

### 1.2 Producción

`CONFIRMADO POR LECTURA READ_ONLY` (2026-11-18 18:07 UTC; evidencias en `C:\ControlFarmacias\evidencias_36\`, con
`SHA256SUMS.txt`; la carpeta conserva el número antiguo):

- `normalizacion_max_intentos` = 4 y espera `{1 h, 6 h, 24 h}`.
- **0 documentos en `ERROR`.**
- **22 en `REVISION`:** todos con clase `DEFECTO_DOCUMENTO`, 4 intentos y último motivo `EXTRACCION_LOCAL_ERROR`.
- Ejecuciones en `ERROR` por clase: `DEFECTO_DOCUMENTO` 89, `NO_SOPORTADO` 151 y `TRANSITORIO` 2.
- **Coste de la regla actual:** los 22 defectos han gastado 4 reclamaciones cada uno para llegar al mismo resultado,
  `REVISION`. En la noche, cada reintento ocupa uno de los 5 (o 20) huecos de documentos.

## 2. Regla nueva (R3 revisada)

`PROPUESTA` que concreta D1 y D4.

| Clase | Antes (17) | Después (37) |
|---|---|---|
| `NO_SOPORTADO` | `PROVEEDOR_NO_SOPORTADO`, sin intento | Sin cambios |
| `DEFECTO_DOCUMENTO` (solo extracción, §2.1) | +1 intento; `ERROR` con espera o `REVISION` al 4.º | **+1 intento (D4) y `REVISION` en el primero**, sin espera (`proximo_reintento_at` null) |
| `TRANSITORIO` (incluidos los de almacenamiento, §2.1) | +1 intento; `ERROR` con espera o `REVISION` al 4.º | Sin cambios |

- El evento del historial sigue siendo `NORMALIZACION_ERROR`. Su `detalle` añade `regla: 'DEFECTO_DIRECTO_A_REVISION'`
  para distinguirlo de un `REVISION` por agotar intentos.
- **Un motivo desconocido sigue siendo `TRANSITORIO`.** Un motivo nuevo solo pasa a defecto con una decisión de Pio y
  un cambio en `clasificacion_fallos.py`.
- **Los huérfanos limpios** (2BI) siguen igual: `TRANSITORIO` con `CLAIM_HUERFANO`.
- **La conciliación no cambia:** R7 y `MOTIVOS_DEFECTO_CONCILIACION` (`clasificacion_fallos.py:80-87`) siguen igual.

### 2.1 Motivos de extracción frente a almacenamiento (confirmada por Pio, D5)

Clasificación de los 23 motivos y los 2 códigos de `DEFECTO_DOCUMENTO` de hoy:

**A. Extracción → `DEFECTO_DOCUMENTO`, directos a `REVISION` (15 motivos y 1 código).** Salen de leer el PDF o de
validar lo leído; releer el mismo PDF con el mismo lector da lo mismo:

| Motivo | Dónde nace |
|---|---|
| `EXTRACCION_LOCAL_ERROR` | excepción del extractor local (los 22 de hoy) |
| `EXTRACCION_INCOMPLETA_REQUIERE_REVISION` | la extracción no cubre el documento |
| `CAMPOS_PENDIENTES_TRAS_EXTRACCION` | campos obligatorios sin valor (`extraccion_productiva.py:108`, `compositor_manual.py:210`) |
| `DOCUMENTO_NORMALIZADO_AUSENTE` | la extracción no entrega el documento normalizado (`compositor_manual.py:213`) |
| `DOCUMENTO_INCOMPLETO` | completitud documental |
| `COBERTURA_DOCUMENTAL_INCOMPLETA` | completitud documental |
| `INVENTARIO_DOCUMENTAL_INVALIDO` | inventario de facturas del documento |
| `INVENTARIO_RELECTURA_INCOMPATIBLE` | la relectura no coincide con el inventario ya persistido (`clasificacion_fallos.py:68-69`) |
| `SEGMENTO_DUPLICADO_O_AUSENTE` | segmentación |
| `SEGMENTOS_SOLAPADOS` | segmentación |
| `RANGO_FACTURA_INVALIDO` | páginas de cada factura |
| `EVIDENCIA_FUERA_DE_FACTURA` | evidencia fuera de su factura |
| `SELECCION_NO_PERTENECE_AL_DOCUMENTO` | selección de segmentos |
| `PROVENANCE_INCOMPLETA` | trazabilidad de lo extraído |
| `NINGUNA_FACTURA_AUTORIZABLE_AUTOMATICAMENTE` | ninguna factura del documento cumple la autoridad (`repositorios.py:290`) |
| código `ErrorCompletitudDocumental` | completitud documental |

**B. Identidad de farmacia → extracción (`REVISION`), DECIDIDO (D5) (2 motivos y 1 código).** Nacen de leer la
farmacia del documento (`barrera_farmacia.py:159-170`); sin un lector nuevo no cambian:

| Motivo | Decisión (D5) |
|---|---|
| `FARMACIA_DOCUMENTO_NO_DEMOSTRABLE` | `REVISION` |
| `FARMACIA_DOCUMENTO_CONTRADICTORIA` | `REVISION` |
| código `ErrorFarmaciaDocumental` | `REVISION` |

**C. Almacenamiento → pasan a `TRANSITORIO`, con reintentos y espera (D1) (6 motivos).** Dependen de la copia en el
almacenamiento o de su registro, y pueden ser una subida a medias:

| Motivo |
|---|
| `SHA256_NO_COINCIDE` |
| `SHA256_REGISTRADO_INVALIDO` |
| `OBJETO_STORAGE_VACIO` |
| `DOCUMENTO_RECLAMADO_NO_LOCALIZADO` |
| `RUTA_STORAGE_NO_COINCIDE_CON_CLAIM` |
| `RUTA_STORAGE_NO_SEGURA` |

`SHA256_REGISTRADO_INVALIDO` y `RUTA_STORAGE_NO_SEGURA` describen un registro mal formado más que una subida a medias:
con reintentos acabarán igualmente en `REVISION` al 4.º intento. Se proponen en C por ser de almacenamiento (D1).

**Implementación propuesta de D1:** los 6 motivos de C salen de `MOTIVOS_DEFECTO_DOCUMENTO` y pasan a una lista
`MOTIVOS_ALMACENAMIENTO` que `clasificar_fallo` devuelve como `TRANSITORIO`. Así la RPC solo necesita una regla:
`DEFECTO_DOCUMENTO` → `REVISION`.

## 3. Reprocesado explícito al cambiar el lector (D2: opción B)

`PROPUESTA` que concreta D2.

- **Columna `lector`** (jsonb: `adaptador`, `version_adaptador` y `layout`, o null si el fallo es anterior a reconocer
  el layout) en `normalizacion_ejecuciones`. La rellena el worker en cada ejecución que falla.
- **Cómo llega a la BD (D6):** un 8.º parámetro `p_lector jsonb` de la RPC de fallo. La firma nueva necesita el
  EXECUTE del rol del sistema, que la 37 puede nombrar por la autorización D7.
- **Selección para reprocesar**, con un script de plan READ_ONLY `pruebas/auditoria_37/plan_reprocesado.py`:
  - documentos en `REVISION` con clase `DEFECTO_DOCUMENTO` cuyo último fallo tiene un `lector` distinto del vigente,
    o null;
  - para cada uno, el motivo y una predicción con el lector nuevo sobre el espejo local, como la serie 2BJ.
  Pio confirma la lista, y un script one-shot llama a `cf_solicitar_reprocesado` documento a documento, con guard
  (estado y huella iguales a los del plan) y postcheck por fila (2AX). Después, los documentos entran en la cola normal
  (noche o serie 2BJ).
- **Los 22 de hoy (D3):** se quedan en `REVISION`. Su `lector` es null (fallaron antes de la 37), así que entrarán en
  el primer plan de reprocesado tras un cambio del lector Alliance.
- **Nunca automático:** ni la noche ni el worker reprocesan solos. Es una acción de Pio, como ahora (R2/R3).

## 4. Migración 37

`PROPUESTA`. `sql/migrations/37_cf_defectos_directos_a_revision.sql` y su rollback. Requiere la 36.

- `normalizacion_ejecuciones.lector jsonb` (null por defecto; las filas existentes quedan en null, sin cambios).
- `cf_registrar_fallo_normalizacion`: la rama de `DEFECTO_DOCUMENTO` deja `REVISION` en el primer fallo (§2) con el
  `detalle` del historial ampliado, y guarda `lector` en la ejecución. **Firma nueva de 8 parámetros** con
  `p_lector jsonb` (D6), con su EXECUTE para el rol del sistema (autorización D7) y nada para `anon`,
  `authenticated` ni `PUBLIC`. La de 7 parámetros se mantiene y llama a la de 8 con `p_lector` null, para el
  código anterior a la 37.
- La de 6 parámetros, `cf_solicitar_reprocesado`, el claim, el selector y la persistencia no cambian (R4).
- `comment on function` y `comment on column` actualizados.
- **Rollback:** restaura el cuerpo de la 17 y quita la columna. No mueve documentos: los que entraron en `REVISION`
  por la regla nueva se quedan ahí, y vuelven a la cola solo por reprocesado (§3).
- **Datos:** ninguna fila cambia. Con 0 documentos en `ERROR` (§1.2) no hay transición pendiente. Si al desplegar
  hubiera alguno en `ERROR` por un defecto de extracción, seguiría su espera y, en su siguiente fallo, pasaría a
  `REVISION` directamente.

## 5. Código y series

`PROPUESTA`. En el mismo commit que la 37:

- **`clasificacion_fallos.py`:** `MOTIVOS_ALMACENAMIENTO` (§2.1 C) como `TRANSITORIO`; docstring actualizado.
- **Worker:** pasa el `lector` del extractor autorizado a la RPC de fallo.
- **Serie 2BJ** (`pruebas/auditoria_2bj/serie_normalizacion.py:279-280`): la predicción de un defecto de extracción
  pasa a `REVISION` con `intentos_antes + 1`, sin depender de `max_intentos`. Los de almacenamiento, como `TRANSITORIO`.
- **Noche** (`noche_automatica.py`): ya trata `ERROR` y `REVISION` como `DEFECTO` y los anota para revisar. No
  cambia. En `para_revisar` se añade el motivo (`EXTRACCION_LOCAL_ERROR`, etc.) si no está.
- **Tests:**
  - unitarios de la clasificación (A, B y C de §2.1), de la serie 2BJ y de la predicción;
  - integración PostgreSQL 17 local:
    - defecto de extracción → `REVISION` al primer intento, con `lector`;
    - almacenamiento y `TRANSITORIO` → `ERROR` con espera y `REVISION` al 4.º;
    - `NO_SOPORTADO` y huérfano limpio, igual;
    - reprocesado tras defecto → `PENDIENTE` con 0 intentos;
    - rollback → vuelve la regla de la 17;
  - revisar los tests existentes que fijan la regla antigua (`test_integracion_pg17_2ar.py`, `_2as.py`,
    `test_migracion_17_2ar.py`, `test_serie_normalizacion_2bj.py`): los que prueban la 17 sola siguen igual, y los
    que prueban el estado final con todas las migraciones se adaptan.
- **`desplegar_37.py`**, ensayado con la imitación del `postgres` de Supabase, que exige el commit ya subido, con
  preflight READ_ONLY y postcheck 2AX por fila: solo pueden cambiar la función y la columna.

## 6. Despliegue (37-D)

`PROPUESTA`, con la confirmación de Pio por paso.

- **Los flags están encendidos desde AUTO-ON.** Los preflights de despliegue exigen los flags apagados
  (`FLAGS_ESPERADOS`, `pruebas/auditoria_2at/auditoria_readonly.py:50` y `:341`). Secuencia:
  1. fuera de la ventana de las tareas (21:00–23:15) y sin noche `EN_CURSO`;
  2. Pio apaga los dos flags;
  3. preflight READ_ONLY, `desplegar_37` una vez y postcheck;
  4. Pio vuelve a encender los flags.
- **Orden respecto de la noche:** con la firma nueva (D6), el código no puede llamar a la de 8 parámetros antes de la
  37. Como en R20, se propone que el código detecte la 37 con una sesión de solo lectura y, sin ella, use la
  llamada de 7 parámetros de la 17.

## 7. Documentos canónicos

`PROPUESTA` (se aplica en el commit de la implementación de la 37, no antes):

- **REGLAS_CRITICAS:** R3 revisada (§2); la lista de motivos de extracción y de almacenamiento (§2.1); la línea de la
  serie 2BJ «Los defectos de extracción previstos por el plan consumen intentos (R3)» pasa a «pasan a `REVISION` en
  el primer fallo»; la vía de reprocesado por `lector` (§3).
- **ESTADO_ACTUAL:** hito 37 en local y, después, 37-D.

## 8. Decisiones de Pio (2026-11-19, tomadas)

1. **Lista de §2.1: DECIDIDO (D5).** A y B, directas a `REVISION`; C, transitoria.
2. **Cómo llega el `lector` a la RPC de fallo: DECIDIDO (D6), opción (a)**, con la autorización D7. Opciones que se
   valoraron:
   - **(a) un 8.º parámetro `p_lector jsonb`:** la vía limpia; la firma nueva necesita el EXECUTE del rol del
     sistema, que Pio autorizó nombrar solo en la 37 y su rollback (D7);
   - **(b) la misma firma de 7 parámetros**, con el lector dentro de `p_error_detalle` en un formato fijo que la RPC
     separa. No nombra el rol, pero mezcla dos datos en un campo de texto.
   **Elegida: (a)** (D6, con la autorización D7).

## 9. Fuera de alcance

- La conciliación (R7) y sus reintentos.
- Cambiar la lista de motivos de defecto, salvo lo de §2.1.
- Reprocesar nada en este hito.

## 10. Implementación (2026-11-21)

`CONFIRMADO POR TEST` en PostgreSQL 17 local; sin tocar producción.

- **Migración** `sql/migrations/37_cf_defectos_directos_a_revision.sql` y su rollback, como en §4. La firma de 8
  parámetros valida que `p_lector` sea null o un objeto (`LECTOR_NO_VALIDO`).
- **Lector (§3):** el worker guarda el lector autorizado de su compositor (`adaptador` y `version_adaptador`:
  `alliance-local` 1.3.1 en la ruta automática y en la manual) con el `layout` del último paso que lo reconoció, o
  null si el fallo es anterior a reconocerlo (por ejemplo, `EXTRACCION_LOCAL_ERROR`). Sin lector autorizado, el
  fallo va sin lector.
- **Detección (§6):** `lectura_readonly.defectos_37_en_bd` (firma de 8 parámetros y columna, solo catálogo). La noche
  y la serie 2BJ la inyectan en el repositorio; sin la 37, la llamada de 7 parámetros.
- **Clasificación (§2.1):** listas A y B en `MOTIVOS_DEFECTO_DOCUMENTO` y lista C en `MOTIVOS_ALMACENAMIENTO`
  (`TRANSITORIO`).
- **Noche:** `para_revisar` añade `motivo` y la ejecución incluye `error_detalle` y `lector`.
- **`desplegar_37.py`:** el propietario de la firma nueva es quien despliega (postgres en Supabase), como en
  `desplegar_35`. Comprueba que sus beneficiarios son los de la firma de 7 parámetros. Si en producción la de 7
  tuviera otros beneficiarios, la postcondición fallaría y el despliegue se revertiría. El preflight de 37-D debe
  leerlos antes.
- **Pendiente:** el plan de reprocesado `plan_reprocesado.py` (§3), que no hace falta para desplegar.
- **Tests:** `tests/facturas/runtime_supabase/test_defectos_37.py` (unitarios) y `test_integracion_pg17_37.py`
  (PostgreSQL 17 local y ensayo del despliegue).
