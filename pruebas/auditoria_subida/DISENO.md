# Subida de facturas desde la web y «Actualizar ahora». DISEÑO

Estado: **DISEÑO CON LAS DECISIONES DE PIO** (2026-11-19, §0; A1 cambiada por Pio el mismo día). Sin código, sin
migración y sin tocar producción. Petición de la web con las decisiones de Pio del encargo (2026-11-19). La bandeja de entrada (H9) queda para más adelante.

**Numeración (DECISIONES DE PIO del 2026-11-25 y del 2026-11-26):** «Actualizar ahora» era la migración 39; pasó a 41
(R21 = 39, H7b = 40) y ahora a **42** (la 41 es TA4-2 de Trabajadores). En este documento, «la 42» es la antigua «39».
La autorización A4 para nombrar el rol del sistema se dio para esta migración con el número 39: **se reconfirma con
Pio al implementarla con el número 42** (como en la renumeración de C3, 2026-11-19). **DECISIÓN DE PIO (2026-11-27):** la
42 pasa a ser el Paso 0 de FACTURAS-0 y «Actualizar ahora» es la **43**. Donde este documento dice «la 42», léase «la
43»; la autorización A4 se reconfirma al implementar la 43.

- **Etiquetas:** `CONFIRMADO POR CÓDIGO` (fichero:línea), `CONFIRMADO POR LECTURA` (listado del espejo, solo nombres y
  conteos, sin abrir PDF) y `PROPUESTA`. Lo que tiene que decidir Pio está en §4.
- **Fuera de alcance:** Farmatic (no se toca), el lector, la conciliación y la bandeja H9.

## 0. Decisiones de Pio (2026-11-19)

| Id | Decisión |
|---|---|
| **A1** (cambiada) | El botón ejecuta el **circuito COMPLETO** (importar, sincronizar, normalizar y conciliar) en **modalidad «bajo demanda»**, dentro de la **migración 42**: varias ejecuciones al día **sin bloquear la noche**, con **las mismas puertas y límites** (§3.3) |
| **V1** | **Velocidad**, también en la 42: **encadenar los pasos** (cada uno arranca al terminar el anterior), en el botón **y en la noche**, e **insertar en bloque** los albaranes de la sincronización. Tiempos medidos y estimados en §1.4 y §3.6 |
| **E1** | «Evidencia en llamadas aparte»: **sigue `PENDIENTE`** (decisión de Pio, sin cambios) |
| **B1** | Las ejecuciones bajo demanda tienen **fila propia en `cf_noches_automaticas`** (columnas `modalidad`, `id` y `peticion_id`; índice único parcial para la noche) |
| **B2** | **Mismos límites por ejecución**, **sin máximo diario**. La escalada 5 + 5 → 20 + 20 cuenta **SOLO las noches** |
| **B3** | **Una sola tarea `ControlFarmacias - Circuito` a las 21:00.** La de Cashflow (23:45) sigue aparte |
| **B4** | Albaranes en **lotes de 200** |
| **V2** | Franjas prohibidas del botón: **20:50–21:30** y **23:40–23:55**, con «ninguna noche `EN_CURSO`» para los días largos y la noche esperando (máximo 30 minutos) a una ejecución bajo demanda en marcha (§3.7) |
| **I1** | La espera fija de 1 s por PDF se **sustituye** por **antigüedad > 60 s** y **tamaño y fecha de modificación sin cambios antes y después del hash** (§3.8) |
| **S1** | Carpeta por **fecha de subida por defecto**, con opción de **elegir mes y decena** en la web |
| **S2** | Tamaño máximo: **20 MB** |
| **S3** | Nombre: **el original saneado** |
| **S4** | Nombre repetido: **rechazo** (`NOMBRE_EXISTENTE`) |
| **A2** | **Sí:** `Usuari` puede **EJECUTAR** la tarea de sincronización, sin modificarla. **Ya lo tiene desde el hito 2AG** (comprobado hoy, §5): no hace falta ningún cambio |
| **A3** | Caducidad de una petición: **10 minutos**. Tiempo máximo por paso: **30 minutos** |
| **A4** | La cola va en la **migración 42** (antes 39). **AUTORIZACIÓN EXPRESA DE PIO (2026-11-19):** nombrar el rol del sistema **SOLO** en la migración de «Actualizar ahora» y su rollback (para el EXECUTE de las funciones de reclamar y cerrar); se dio como `sql/migrations/39_*.sql` y **se reconfirma con Pio para `42_*.sql` al implementarla**. Tests, scripts y documentación no lo nombran; cualquier otro fichero, autorización nueva. Se registra en REGLAS_CRITICAS al implementar la 42 |
| **S6** | Rol de la web para la cola: **nuevo, `cf_actualizar_web`** (solo `INSERT` y `SELECT` sobre la cola) |
| **Orden** | **37 → 38 → 39 (R21) → 40 (H7b) → 41 (TA4-2) → 42.** Cada migración exige la anterior |

## 1. Lo que hay hoy

### 1.1 El importador (`src/facturas/importar_facturas_drive.py`)

`CONFIRMADO POR CÓDIGO` (leído con Read y Grep, autorización de Pio del 2026-11-19):

- **Raíz:** `FACTURAS_PIO_DIR`, ruta absoluta cuyo nombre debe ser `FACTURES PIO` (`:23`, `:101-108`).
- **Carpetas de mes:** cualquier nombre con un mes en catalán o castellano y un año de 2 o 4 cifras, sin acentos ni
  mayúsculas (`:57-84`, `:133-153`, `:181-243`). Solo desde junio de 2026 (`:36`, `:272`).
- **Decenas:** el importador **no** interpreta su nombre: recorre con `rglob` todo lo que hay dentro del mes (`:301-335`).
- **Ficheros:** solo `*.pdf` (`:318-320`); excluye los PDF cuyo nombre (sin extensión) termina en `RITA` (`:338-350`).
- **Validación** de un PDF nuevo: existe, no está vacío, tamaño estable durante 1 s (no se está sincronizando) y
  cabecera `%PDF-` (`:581-630`).
- **Duplicados:** SHA-256 del fichero (`:554-578`). Si el hash ya está en `documentos_facturas.archivo_hash`, no se
  vuelve a importar (`:497-551`, `:1155-1207`). Además lleva un índice local (`data/indice_facturas.sqlite`, `:45-48`).
- **Storage:** `PIO/<mes>/<decena>/<nombre normalizado>_<12 primeros del hash>.pdf` (`:633-706`).

### 1.2 El espejo (`C:\GoogleDrive\FACTURES PIO`)

`CONFIRMADO POR LECTURA` (2026-11-19):

- 12 carpetas de mes de 2026, en catalán y en mayúsculas: `GENER 26`, `FEBRER 26`, `MARÇ 26`, `ABRIL 26`, `MAIG 26`,
  `JUNY 26`, `JULIOL 26`, `AGOST 26`, `SETEMBRE 26`, `OCTUBRE 26`, `NOVEMBRE 26` y `DESEMBRE 26`. Ya existen todas,
  incluidas las futuras.
- Cada una con 3 subcarpetas: `1A DESENA`, `2A DESENA` y `3A DESENA` (p. ej., `NOVEMBRE 26`: 8, 8 y 0 PDF).
- **Observación:** la factura HEFAME del 30.09 se subió el 18.11 a `SETEMBRE 26\3A DESENA`, es decir, **por la fecha de
  la factura y no por la fecha de subida**. Ver decisión S1 de §4.

### 1.3 Las tareas programadas y la noche

`CONFIRMADO POR CÓDIGO` y por lectura de las tareas:

- `ControlFarmacias - Importar facturas` (Usuari, 21:00), `Sincronización ControlFarmacias` (ControlFarmaciasRO, 21:30) y
  `ControlFarmacias - Automatizacion Alliance` (Usuari, 22:15, lanza `noche_automatica REAL`).
- **La noche admite una sola fila por fecha local** (`cf_noches_automaticas`, clave primaria `fecha`;
  `noche_automatica.py`, guard al empezar). Además, sus puertas exigen que la importación y la sincronización hayan
  corrido **esa noche**. **Lanzar la tarea Alliance de día ocuparía la fila de hoy y la noche de verdad pararía**
  (`NOCHE_YA_EJECUTADA`). Por eso la modalidad «bajo demanda» lleva su propia fila (§3.3).

### 1.4 Tiempos reales de cada paso

`CONFIRMADO POR LECTURA READ_ONLY` (2026-11-19, marcas de tiempo de Supabase; sin leer `logs/`; el historial del
Programador de tareas no devuelve eventos). Evidencias en `C:\ControlFarmacias\evidencias_tiempos\`
(`SHA256SUMS.txt`). Horas locales:

| Paso | Arranque | Medido | Notas |
|---|---|---|---|
| **Importación** (21:00) | 21:00:00 | primer documento a los **7–12 s**; después **~1,5 s por PDF nuevo** (4 documentos el 18/11: 21:00:07–21:00:12; 6 el 21/10: 8,4 s entre el primero y el último) | El arranque recorre el espejo, el índice y los hashes de Supabase. Cada PDF nuevo espera **1 s** fijo de tamaño estable (`importar_facturas_drive.py:609`). El final de la tarea no tiene marca |
| **Sincronización** (21:30:30) | 21:30:30 | la resincronización registra cambios a los **19–29 s** (`albaranes_cambios.detectado_at`: 21:30:49 y 21:30:59 los días 9 y 10/11) | Los nuevos se guardan **uno a uno**, con una petición cada uno (`sincronizar_albaranes.py:86-113`). El final no tiene marca. Unos 30 albaranes nuevos al día (6.525 desde abril) |
| **Noche** (22:15) | 22:15:03 | **63 s** la REAL del 18/11 (5 documentos y 3 conciliaciones); **19 s** las SOMBRA sin trabajo | Arranque, puertas y snapshot: ~18 s. Documento Alliance: hasta los 18 s; cada no soportado, ~1,5 s; cada conciliación, ~6–11 s (con su simulación); postcheck e informe, ~15 s |

- **Tiempo de pared hoy:** de 21:00 a ~22:16, **unos 76 minutos**, de los que **el trabajo real es de unos 2–3
  minutos**. El resto son esperas fijas entre tareas (30 y 45 minutos).
- Lo que no tiene marca (final de la importación y de la sincronización) se medirá con el encadenado: cada paso
  guarda su inicio y su fin (§3.4).

## 2. Subir una factura desde la web

`PROPUESTA`.

### 2.1 Dónde se guarda

- La web (servidor local en 127.0.0.1, como `Usuari`) guarda el PDF en
  `C:\GoogleDrive\FACTURES PIO\<MES AA>\<N>A DESENA\`.
- **`<MES AA>`:** el mes en catalán y en mayúsculas, como en el espejo (`GENER`, `FEBRER`, `MARÇ`, `ABRIL`, `MAIG`,
  `JUNY`, `JULIOL`, `AGOST`, `SETEMBRE`, `OCTUBRE`, `NOVEMBRE`, `DESEMBRE`), un espacio y el año con 2 cifras.
- **`<N>A DESENA`:** día 1–10 → `1A DESENA`; 11–20 → `2A DESENA`; del 21 a fin de mes → `3A DESENA`.
- **Fecha (S1):** por defecto, la de subida en Europe/Madrid. La web deja elegir otro mes y otra decena (por ejemplo,
  para una factura atrasada, como la HEFAME del 30.09 de §1.2). El servidor valida la elección: un mes reconocible por
  el importador desde junio de 2026 y una de las tres decenas.
- **Si la carpeta falta, se crea.** Antes de crear un mes se busca uno que ya exista y que el importador interprete
  como el mismo mes (misma normalización sin acentos: `MARÇ 26` y `MARC 26` son el mismo). Si hay uno, se usa ese; si
  hay más de uno, se rechaza la subida (`CARPETA_MES_AMBIGUA`).
- La ruta la construye el servidor: el usuario nunca escribe una ruta. La ruta final, ya resuelta, tiene que quedar
  dentro de la raíz; si no, se rechaza.

### 2.2 Reglas del fichero

| Regla | Propuesta |
|---|---|
| Tipo | Extensión `.pdf` **y** cabecera `%PDF-`, como el importador. Cualquier otra cosa → rechazo |
| Tamaño | Mayor que 0 y como máximo **20 MB** (S2, decidido) |
| Nombre | El del fichero subido, saneado: solo letras, números, espacios, puntos, guiones y paréntesis; máximo 120 caracteres; **nunca termina en `RITA`** (el importador lo ignoraría, y RITA no está habilitada para facturas). Decidido (S3) |
| Nunca sobrescribir | Se crea en modo exclusivo. Si ya hay un fichero con ese nombre → rechazo `NOMBRE_EXISTENTE` (S4, decidido) |
| Duplicado por hash | SHA-256 del fichero. Si ya está en `documentos_facturas.archivo_hash` (lo lee `cf_lectura`) o en algún PDF de la misma carpeta de mes → rechazo `DUPLICADO`, con el documento que ya existe |
| Escritura | Primero a un temporal con otra extensión en la misma carpeta y después se renombra a `.pdf`. Así el importador nunca ve un PDF a medias (ya exige además tamaño estable) |
| Registro | Una línea por subida, con fecha, nombre, hash, tamaño, carpeta y resultado, en un registro de la web fuera del repositorio. Sin contenido del PDF |

- Lo que no hace la web: no borra, no mueve, no renombra ni abre PDF ya existentes; no escribe fuera de esa carpeta; no
  llama al importador. El fichero lo recoge la importación (de la noche o de «Actualizar ahora»).
- El nombre y la carpeta siguen siendo metadatos: no prueban proveedor, farmacia ni sentido (regla S5 de
  REGLAS_CRITICAS).

### 2.3 Excepción en REGLAS_CRITICAS

`PROPUESTA` de texto, que se aplica en el commit de la implementación:

> **Subida de facturas desde la web (DECISIÓN DE PIO, 2026-11-19):** el servidor local de la web (127.0.0.1, `Usuari`)
> escribe **solo PDF** y **solo** en `C:\GoogleDrive\FACTURES PIO\<MES AA>\<N>A DESENA\`. Para ello puede, y solo ahí:
> crear la carpeta de mes o de decena que falte (con el formato del espejo) y escribir un temporal del mismo PDF con
> otra extensión, que renombra a `.pdf` al terminar. Nunca sobrescribe, nunca borra ni mueve ficheros ya existentes y
> nunca escribe en otra ruta. Duplicado por SHA-256 → rechazo. El importador no cambia; la
> farmacia sigue demostrándose por el contenido, nunca por la carpeta ni por el nombre.

## 3. «Actualizar ahora»

`PROPUESTA`.

### 3.1 Cola

Tabla `cf_peticiones_actualizacion`, en la **migración 42** (A4), después de la 41:

| Columna | Contenido |
|---|---|
| `id` | identidad |
| `tipo` | `CIRCUITO_COMPLETO` (único valor por ahora) |
| `solicitado_at`, `autor` | cuándo y quién (el autor lo pone la web, como `cf.autor` en Pagos) |
| `estado` | `EN_COLA`, `EN_MARCHA`, `OK`, `ERROR` o `RECHAZADA` |
| `inicio`, `fin` | los pone el proceso del circuito |
| `resumen` | jsonb **solo con recuentos** (documentos importados, albaranes sincronizados, reclamados, conciliadas, para revisar) |
| `motivo` | por qué `RECHAZADA` o `ERROR` |

- **Privilegios:** el rol nuevo de la web `cf_actualizar_web` (S6), solo `INSERT` y `SELECT`; `cf_lectura`, `SELECT`;
  el rol del sistema, solo el EXECUTE de las funciones de reclamar y cerrar (autorización A4); `anon`, `authenticated`
  y `PUBLIC`, nada. La contraseña de `cf_actualizar_web` la fija Pio fuera del repositorio, con SCRAM.
- **Reglas al insertar** (trigger `BEFORE INSERT`; la fila queda guardada, también si se rechaza, para que la web vea
  el motivo):
  - una sola petición a la vez: si hay una `EN_COLA` o `EN_MARCHA` → `RECHAZADA` (`YA_HAY_UNA_EN_CURSO`); además, un
    índice único parcial lo garantiza;
  - dentro de las franjas prohibidas (Europe/Madrid, §3.7): **20:50–21:30** (circuito de la noche) y
    **23:40–23:55** (Cashflow) → `RECHAZADA` (`VENTANA_DE_LA_NOCHE` o `VENTANA_CASHFLOW`);
  - si la anterior terminó hace menos de 15 minutos → `RECHAZADA` (`DEMASIADO_PRONTO`);
  - con una noche `EN_CURSO` en `cf_noches_automaticas` → `RECHAZADA`;
  - la web solo puede insertar `estado = EN_COLA` (el trigger fija el resto); no puede modificar ni borrar.
- **Caducidad:** una petición `EN_COLA` con más de **10 minutos** (A3, decidido) pasa a `RECHAZADA` (`CADUCADA`) cuando el proceso
  la ve. Nunca se lanza una petición vieja.

### 3.2 Cómo se recoge la petición

- **Una tarea programada nueva**, `ControlFarmacias - Actualizar ahora`, como `Usuari`, **cada 2 minutos** de 06:00 a
  23:58. Fuera de las franjas prohibidas (§3.7) recoge la petición; dentro de ellas termina sin hacer nada. Ejecuta el
  módulo del circuito:
  1. **lee** con una sesión de solo lectura si hay una petición `EN_COLA`; si no hay, termina (una consulta, sin coste);
  2. **reclama** la petición (`EN_COLA` → `EN_MARCHA`) con una función atómica (`for update skip locked`); caducada →
    `RECHAZADA`;
  3. ejecuta el **circuito encadenado** (§3.4) en modalidad `BAJO_DEMANDA` (§3.3);
  4. **cierra** la petición (`OK` o `ERROR`) con el resumen de recuentos y los tiempos de cada paso.
- **Por qué una tarea cada 2 minutos y no un servicio:** reutiliza el mismo mecanismo que la noche (Programador de
  tareas, `Usuari`), no deja un proceso vivo y, si falla, la siguiente vuelta lo ve. El retraso máximo es de 2
  minutos.

### 3.3 Modalidad «bajo demanda» (migración 42)

`PROPUESTA` que concreta A1.

- **El mismo orquestador** (`noche_automatica.py`) con una modalidad nueva, `BAJO_DEMANDA`, junto a `SOMBRA` y `REAL`.
  Mismo código de normalización y conciliación, mismas puertas, mismos límites, mismas paradas y mismo postcheck por
  fila. Lo que cambia:
  - **Fila propia** en `cf_noches_automaticas` (B1, decidido): la 42 añade `modalidad` (`NOCHE` o `BAJO_DEMANDA`), un
    `id` y `peticion_id`. La guarda de una noche por fecha pasa a un **índice único parcial** `(fecha) where modalidad =
    'NOCHE'`: la noche sigue siendo una sola por fecha y las ejecuciones bajo demanda no la ocupan.
  - **Puerta de pasos** en lugar de la de tareas: en vez de «las tareas han corrido esta noche», «la importación y la
    sincronización de **esta ejecución** han terminado con código 0» (§3.4).
  - **Límites (B2, decidido):** los mismos que tendría la noche de ese día, **por ejecución** y **sin máximo
    diario**. `limites_por_historial` cuenta **solo las filas `modalidad = 'NOCHE'`**: la escalada 5 + 5 → 20 + 20 no
    avanza con las ejecuciones bajo demanda.
  - **Ventana:** nunca dentro de las franjas prohibidas de §3.7; nunca con una noche o una ejecución `EN_CURSO`; al
    menos 15 minutos desde el final de la anterior.
  - **Informe:** en `noches_auto/<fecha>/bajo_demanda_<id>/`, con su SHA en la fila, igual que la noche.
- **La noche no cambia de comportamiento:** su fila, su informe y sus puertas siguen igual. Solo cuenta lo que ya
  hicieron las ejecuciones del día (documentos y facturas que ya no están en cola).

### 3.4 Encadenado de los pasos (botón y noche)

`PROPUESTA` que concreta V1.

- **Un solo proceso del circuito** hace los tres pasos seguidos, cada uno al terminar el anterior:
  1. **Importación**, en el mismo proceso (`Usuari`, como hoy);
  2. **Sincronización**, lanzando la tarea existente `Sincronización ControlFarmacias` para que corra como
     **ControlFarmaciasRO** (la identidad de Farmatic la pone el Programador de tareas, nunca el proceso). Se espera a
     que termine (`Get-ScheduledTaskInfo`) y se exige resultado 0. `Usuari` ya puede lanzarla (§5);
  3. **Normalización y conciliación** (`noche_automatica` con la modalidad que toque).
  Un paso con resultado distinto de 0, o que supera 30 minutos (A3) → `ERROR` (botón) o `PARADA` (noche), y no se
  lanza el siguiente.
- **En la noche:** una sola tarea `ControlFarmacias - Circuito` a las 21:00 (`Usuari`) sustituye los disparadores de
  las 21:30 y las 22:15. La tarea de sincronización se queda sin disparador propio: solo se lanza desde el circuito.
  La tarea de Cashflow (23:45) sigue aparte (B3, decidido). Los cambios de tareas los hace Pio, con instrucciones en el
  hito.
- **Tiempos por paso:** cada paso guarda su inicio y su fin en el informe y en la fila (la de la noche o la de la
  ejecución). Así se mide lo que hoy no tiene marca (§1.4).

### 3.5 Albaranes de la sincronización en bloque

`PROPUESTA` que concreta V1.

- Hoy la sincronización guarda **cada albarán nuevo con una petición** (`guardar_albaran`,
  `sincronizar_albaranes.py:86-113`) y la resincronización aplica su plan fila a fila.
- **Decidido (B4):** insertar los nuevos en **lotes de 200** con una sola petición por lote, con las mismas
  restricciones de la tabla. Si un lote falla (por ejemplo, por un duplicado), ese lote se repite fila a fila, como
  hoy, para conservar el recuento exacto de nuevos y existentes. Los inserts de la resincronización van igual; las
  actualizaciones siguen una a una (son pocas y llevan su historial).
- **Farmatic no cambia:** la lectura sigue siendo la misma consulta READ_ONLY con la misma identidad.

### 3.6 Estimación de tiempos

`PROPUESTA` (estimación; se medirá con las marcas de §3.4):

| Paso | Hoy | Con la 42 |
|---|---|---|
| Esperas entre pasos | 30 + 45 minutos | **0** (encadenado) |
| Importación | 7–12 s + ~1,5 s por PDF | ~0,5 s por PDF con la propuesta de §3.8 (sin la espera fija de 1 s) |
| Sincronización | ~20–30 s hasta la resincronización, más una petición por albarán | **unos segundos menos**: ~30 albaranes al día pasan de ~30 peticiones a 1 |
| Normalización y conciliación | 63 s con 5 + 3; 19 s sin trabajo | igual |
| **Circuito completo** | **~76 minutos de pared** | **~2–3 minutos** con la carga de un día normal |

- **Estimación que muestra el botón:** la duración de la última ejecución `OK` (`fin − inicio`). Si no hay ninguna, la
  suma de los tiempos medidos de cada paso.
- **Uso de IA:** hoy **0**. Luna está desactivada (`luna_habilitada = false`, comprobado hoy) y los extractores son
  locales. Si algún día se habilita Luna, la estimación saldría de los documentos en cola por su coste medio.

### 3.7 Franjas prohibidas del botón

**Decidido (V2, 2026-11-19).** Con el circuito encadenado, la noche ocupa unos minutos y no hora y tres cuartos:

| Franja | Por qué | Margen |
|---|---|---|
| **20:50–21:30** | El circuito de la noche arranca a las 21:00 y hoy tarda ~2–3 minutos (§3.6) | 10 minutos antes, para no arrancar una ejecución que llegue a las 21:00, y ~27 después para un día con mucha carga |
| **23:40–23:55** | La tarea de Cashflow (23:45) va aparte (B3) | 5 minutos antes y 10 después |

- **Si el circuito de la noche dura más** de lo previsto, el botón sigue rechazado por la regla «ninguna noche
  `EN_CURSO`» (§3.1), aunque la franja haya terminado. La franja protege el arranque; `EN_CURSO` protege la
  duración.
- **Simétricamente**, si una ejecución bajo demanda sigue en marcha a las 21:00, el circuito de la noche **espera**
  a que termine (con un máximo de 30 minutos) antes de empezar. Si no termina, la noche para con
  `EJECUCION_BAJO_DEMANDA_EN_CURSO`, como cualquier puerta.
- Con la regla de los 15 minutos, la última petición útil antes de la noche es la que termina hacia las 20:50.

### 3.8 La espera fija de 1 s por PDF en la importación

`CONFIRMADO POR CÓDIGO`. **Decidido (I1, 2026-11-19):** se sustituye la espera como se describe abajo.

- **Hoy es la única comprobación de tamaño estable.** `validar_pdf_nuevo` mira el tamaño, espera 1 s y lo vuelve a
  mirar (`importar_facturas_drive.py:600-619`). El índice compara tamaño y fecha **con la ejecución anterior**
  (`:472-494`, `:1113-1143`), lo que sirve para saltarse lo ya importado, pero **no** comprueba que un fichero nuevo
  haya terminado de escribirse. **Quitarla sin más no es seguro:** un PDF que Google Drive está bajando al espejo
  podría importarse a medias.
- Solo se paga por cada PDF **nuevo o modificado** (los ya importados se saltan por el índice): 4–6 s por noche.
- **Decidido (I1): sustituirla por una comprobación sin espera, de la misma seguridad o más:**
  1. **antigüedad:** si la última modificación del fichero tiene más de 60 s, se considera asentado sin esperar;
     si es más reciente, se deja para la siguiente ejecución (no se importa a medias ni se espera);
  2. **lectura sin cambios:** se toma tamaño y fecha de modificación antes de calcular el hash y otra vez después;
     si cambian, el fichero no se importa en esta ejecución. Detecta un cambio **durante** la lectura, cosa que la
     espera de 1 s no hace;
  3. la cabecera `%PDF-` y el resto de validaciones siguen igual.
- **Subidas desde la web:** el fichero aparece ya completo (temporal y renombrado, §2.2), con lo que pasa la
  comprobación sin esperar.
- Ahorro: ~1 s por PDF nuevo (4–6 s por noche). Es pequeño, pero quita la única espera fija del circuito.

## 4. Decisiones de Pio

Tomadas el 2026-11-19 (§0), incluidas B1–B4, V2 e I1. **Queda para Pio:**

- **E1.** «Evidencia en llamadas aparte»: sigue `PENDIENTE`.

Para el hito de implementación (la 42 va después de la 41):

- migración 42: cola, trigger, funciones de reclamar y cerrar, rol `cf_actualizar_web`, columnas de B1 y su rollback,
  con `desplegar_42` ensayado con la imitación del `postgres` de Supabase; la autorización A4, reconfirmada por Pio para
  la 42, se registra entonces en REGLAS_CRITICAS;
- código: modalidad `BAJO_DEMANDA`, circuito encadenado, lotes de albaranes, tarea del botón;
- el servidor de subida de la web y la excepción de §2.3 en REGLAS_CRITICAS;
- la prueba de lanzar la sincronización desde el circuito, sin ejecutarla en producción salvo con la confirmación de
  Pio.

## 5. Permiso de `Usuari` para ejecutar la sincronización (A2)

`CONFIRMADO POR LECTURA` (2026-11-19, solo lectura del descriptor de seguridad de la tarea, sin cambiarlo):

| Cuenta | Máscara | Ejecutar |
|---|---|---|
| `MOSTRADOR\Usuari` | `0x001200A9` (lectura + ejecución) | **sí** |
| `MOSTRADOR\ControlFarmaciasRO` | `0x00120089` (lectura) | no |
| `BUILTIN\Administradores`, `NT AUTHORITY\SYSTEM` | control total | sí |

- Es el permiso que se concedió en el **hito 2AG** (`pruebas/auditoria_2ag/reparar_acl_tarea_elevado.ps1`: añade
  `TASK_EXECUTE` a la entrada de `Usuari` en el descriptor de seguridad de la tarea). `Usuari` no tiene escritura: no
  puede modificar ni borrar la tarea.
- **No hace falta que Pio haga nada.** Las instrucciones con `icacls` de la versión anterior de este diseño quedan
  retiradas: el permiso de las tareas se gestiona en su descriptor de seguridad, como en el 2AG.
- La tarea sigue ejecutándose como ControlFarmaciasRO con su contraseña guardada; `Usuari` no la conoce ni la
  necesita.
