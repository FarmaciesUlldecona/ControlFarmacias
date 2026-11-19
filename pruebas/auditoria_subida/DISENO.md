# Subida de facturas desde la web y «Actualizar ahora». DISEÑO

Estado: **DISEÑO CON LAS DECISIONES DE PIO** (2026-11-19, §0). Sin código, sin migración y sin tocar producción. Petición de la web con las
decisiones de Pio del encargo (2026-11-19). La bandeja de entrada (H9) queda para más adelante.

- **Etiquetas:** `CONFIRMADO POR CÓDIGO` (fichero:línea), `CONFIRMADO POR LECTURA` (listado del espejo, solo nombres y
  conteos, sin abrir PDF) y `PROPUESTA`. Lo que tiene que decidir Pio está en §4.
- **Fuera de alcance:** Farmatic (no se toca), el lector, la conciliación y la bandeja H9.

## 0. Decisiones de Pio (2026-11-19)

| Id | Decisión |
|---|---|
| **A1** | «Actualizar ahora» lanza **solo la importación y la sincronización**. La normalización y la conciliación siguen siendo de la noche. La modalidad «bajo demanda» es un **hito futuro** |
| **S1** | Carpeta por **fecha de subida por defecto**, con opción de **elegir mes y decena** en la web |
| **S2** | Tamaño máximo: **20 MB** |
| **S3** | Nombre: **el original saneado** |
| **S4** | Nombre repetido: **rechazo** (`NOMBRE_EXISTENTE`) |
| **A2** | **Sí:** Pio da a `Usuari` permiso para **EJECUTAR** la tarea de sincronización, sin modificarla. Instrucciones en §5 |
| **A3** | Caducidad de una petición: **10 minutos**. Tiempo máximo por tarea: **30 minutos** |
| **A4** | La cola va en la **migración 39**. **AUTORIZACIÓN EXPRESA DE PIO (2026-11-19):** nombrar el rol del sistema **SOLO** en `sql/migrations/39_*.sql` y su rollback (para el EXECUTE de las funciones de reclamar y cerrar). Tests, scripts y documentación no lo nombran; cualquier otro fichero, autorización nueva. Se registra en REGLAS_CRITICAS al implementar la 39 |
| **S6** | Rol de la web para la cola: **nuevo, `cf_actualizar_web`** (solo `INSERT` y `SELECT` sobre la cola) |
| **Orden** | **37 → 38 → 39.** Cada migración exige la anterior |

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
  (`NOCHE_YA_EJECUTADA`). Ver decisión A1 de §4.

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

Tabla `cf_peticiones_actualizacion`, en la **migración 39** (A4), después de la 37 y la 38:

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
  - entre las 21:00 y las 23:45 (Europe/Madrid) → `RECHAZADA` (`VENTANA_DE_LA_NOCHE`);
  - si la anterior terminó hace menos de 15 minutos → `RECHAZADA` (`DEMASIADO_PRONTO`);
  - con una noche `EN_CURSO` en `cf_noches_automaticas` → `RECHAZADA`;
  - la web solo puede insertar `estado = EN_COLA` (el trigger fija el resto); no puede modificar ni borrar.
- **Caducidad:** una petición `EN_COLA` con más de **10 minutos** (A3, decidido) pasa a `RECHAZADA` (`CADUCADA`) cuando el proceso
  la ve. Nunca se lanza una petición vieja.

### 3.2 Cómo se recoge la petición

- **Una tarea programada nueva**, `ControlFarmacias - Actualizar ahora`, como `Usuari`, **cada 2 minutos** de 06:00 a
  20:45 (fuera de la ventana de la noche). Ejecuta un módulo del circuito (p. ej. `actualizar_ahora.py`):
  1. **lee** con una sesión de solo lectura si hay una petición `EN_COLA`; si no hay, termina (una consulta, sin coste);
  2. **reclama** la petición (`EN_COLA` → `EN_MARCHA`) con una función atómica (`for update skip locked`); caducada →
    `RECHAZADA`;
  3. **puertas**, las de la noche que aplican de día: puerta git (`ls-remote`), flags, Luna apagada y solo PIO,
    0 bloqueos, 0 reclamaciones, 0 documentos en `NORMALIZANDO`, ninguna noche `EN_CURSO`, ninguna de las tres
    tareas de la noche en marcha y hora fuera de 21:00–23:45. Una puerta falla → `RECHAZADA` con su motivo, sin lanzar nada;
  4. **lanza las dos tareas programadas existentes (A1)**, una tras otra, y espera a que termine cada una (como
    máximo **30 minutos** por tarea, A3): `Importar facturas` (Usuari) → `Sincronización ControlFarmacias`
    (ControlFarmaciasRO; la identidad la pone el Programador de tareas, no el proceso). **Nunca lanza la tarea
    Alliance** (§1.3). Una tarea con resultado distinto de 0, o que supera su tiempo → `ERROR` y no se lanza la
    siguiente;
  5. **cierra** la petición (`OK` o `ERROR`) con el resumen de recuentos.
- **Por qué una tarea cada 2 minutos y no un servicio:** reutiliza el mismo mecanismo que la noche (Programador de
  tareas, `Usuari`), no deja un proceso vivo y, si falla, la siguiente vuelta lo ve. El retraso máximo es de 2
  minutos.
- **Lanzar tareas** con `Start-ScheduledTask` y seguirlas con `Get-ScheduledTaskInfo`. Para lanzar la de
  ControlFarmaciasRO, `Usuari` necesita permiso de ejecución sobre esa tarea (A2, §5).
- **Lo que hace la noche después:** nada distinto. A las 21:00 y 21:30 vuelven a correr las dos tareas (no importan
  dos veces: duplicado por hash) y a las 22:15 la noche normaliza y concilia lo que haya entrado.

### 3.3 Estimación previa

- **Duración:** la de la última petición `OK` (`fin − inicio`). Si no hay ninguna, la suma de las últimas duraciones
  de las dos tareas (Programador de tareas).
- **Uso de IA:** hoy **0**. Luna está desactivada (`luna_habilitada = false`, comprobado hoy) y los extractores son
  locales. Además, «Actualizar ahora» no normaliza (A1): la importación y la sincronización no usan IA. La web lo
  muestra como «sin uso de IA».

## 4. Decisiones de Pio

Todas tomadas el 2026-11-19 (§0). Quedan para el hito de implementación:

- la migración 39 (cola, trigger, funciones de reclamar y cerrar, rol `cf_actualizar_web`) con su rollback y su
  `desplegar_39`, ensayado con la imitación del `postgres` de Supabase; la autorización A4 se registra entonces en
  REGLAS_CRITICAS;
- la tarea programada nueva y el módulo que recoge la petición;
- el servidor de subida de la web y la excepción de §2.3 en REGLAS_CRITICAS;
- comprobar en local que `Usuari` puede lanzar la tarea de sincronización tras el permiso de §5, sin ejecutarla en
  producción salvo con la confirmación de Pio.

## 5. Instrucciones para Pio: permiso de `Usuari` para ejecutar la sincronización (A2)

`PROPUESTA` de pasos. No los ejecuta Claude (las barreras del repositorio impiden a los agentes usar el Programador de
tareas). Se hacen **una vez**, como administrador, fuera de 21:00–23:45:

1. **Copia de la ACL actual**, fuera del repositorio:
   `icacls "C:\Windows\System32\Tasks\Sincronización ControlFarmacias" /save C:\ControlFarmacias\acl_tarea_sincronizacion.txt`
2. **Conceder solo lectura y ejecución** a `Usuari` sobre el fichero de la tarea:
   `icacls "C:\Windows\System32\Tasks\Sincronización ControlFarmacias" /grant "MOSTRADOR\Usuari:(RX)"`
   - `RX` permite ver la tarea y lanzarla. **No** permite modificarla ni borrarla (no hay escritura).
   - La tarea sigue ejecutándose como ControlFarmaciasRO con su contraseña guardada: `Usuari` no la conoce ni la
     necesita.
3. **Comprobación sin ejecutarla:** como `Usuari`, en PowerShell, `Get-ScheduledTask -TaskName "Sincronización ControlFarmacias"`
   debe mostrarla, y `icacls` sobre el mismo fichero debe dar a `MOSTRADOR\Usuari` solo `(RX)`.
4. **Prueba de ejecución:** se deja para el hito de implementación, con tu confirmación, porque lanzarla ejecuta la
   sincronización real (solo lectura de Farmatic, escritura de albaranes en Supabase).
5. **Vuelta atrás:** `icacls "C:\Windows\System32\Tasks\Sincronización ControlFarmacias" /remove:g "MOSTRADOR\Usuari"`
   (o `/restore` con la copia del paso 1, desde `C:\Windows\System32\Tasks`).

Si Windows no permitiera lanzar la tarea solo con `RX` sobre el fichero, la alternativa es fijar el descriptor de
seguridad de la tarea con el Programador de tareas (COM). Se documentaría en el hito, con tu confirmación.
