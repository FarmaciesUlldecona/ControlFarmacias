# Subida de facturas desde la web y «Actualizar ahora». DISEÑO

Estado: **DISEÑO** (2026-11-19). Sin código, sin migración y sin tocar producción. Petición de la web con las
decisiones de Pio del encargo (2026-11-19). La bandeja de entrada (H9) queda para más adelante.

- **Etiquetas:** `CONFIRMADO POR CÓDIGO` (fichero:línea), `CONFIRMADO POR LECTURA` (listado del espejo, solo nombres y
  conteos, sin abrir PDF) y `PROPUESTA`. Lo que tiene que decidir Pio está en §4.
- **Fuera de alcance:** Farmatic (no se toca), el lector, la conciliación y la bandeja H9.

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
- **Fecha:** la de subida, en Europe/Madrid (encargo). Ver S1 de §4 por la observación de §1.2.
- **Si la carpeta falta, se crea.** Antes de crear un mes se busca uno que ya exista y que el importador interprete
  como el mismo mes (misma normalización sin acentos: `MARÇ 26` y `MARC 26` son el mismo). Si hay uno, se usa ese; si
  hay más de uno, se rechaza la subida (`CARPETA_MES_AMBIGUA`).
- La ruta la construye el servidor: el usuario nunca escribe una ruta. La ruta final, ya resuelta, tiene que quedar
  dentro de la raíz; si no, se rechaza.

### 2.2 Reglas del fichero

| Regla | Propuesta |
|---|---|
| Tipo | Extensión `.pdf` **y** cabecera `%PDF-`, como el importador. Cualquier otra cosa → rechazo |
| Tamaño | Mayor que 0 y como máximo **20 MB** (S2) |
| Nombre | El del fichero subido, saneado: solo letras, números, espacios, puntos, guiones y paréntesis; máximo 120 caracteres; **nunca termina en `RITA`** (el importador lo ignoraría, y RITA no está habilitada para facturas). Ver S3 |
| Nunca sobrescribir | Se crea en modo exclusivo. Si ya hay un fichero con ese nombre → rechazo `NOMBRE_EXISTENTE` (S4) |
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

Tabla `cf_peticiones_actualizacion` (migración nueva; ver A4 de §4 para el número):

| Columna | Contenido |
|---|---|
| `id` | identidad |
| `tipo` | `CIRCUITO_COMPLETO` (único valor por ahora) |
| `solicitado_at`, `autor` | cuándo y quién (el autor lo pone la web, como `cf.autor` en Pagos) |
| `estado` | `EN_COLA`, `EN_MARCHA`, `OK`, `ERROR` o `RECHAZADA` |
| `inicio`, `fin` | los pone el proceso del circuito |
| `resumen` | jsonb **solo con recuentos** (documentos importados, albaranes sincronizados, reclamados, conciliadas, para revisar) |
| `motivo` | por qué `RECHAZADA` o `ERROR` |

- **Privilegios:** el rol de la web, solo `INSERT` y `SELECT` (S6 decide cuál); `cf_lectura`, `SELECT`; `anon`,
  `authenticated` y `PUBLIC`, nada.
- **Reglas al insertar** (trigger `BEFORE INSERT`; la fila queda guardada, también si se rechaza, para que la web vea
  el motivo):
  - una sola petición a la vez: si hay una `EN_COLA` o `EN_MARCHA` → `RECHAZADA` (`YA_HAY_UNA_EN_CURSO`); además, un
    índice único parcial lo garantiza;
  - entre las 21:00 y las 23:45 (Europe/Madrid) → `RECHAZADA` (`VENTANA_DE_LA_NOCHE`);
  - si la anterior terminó hace menos de 15 minutos → `RECHAZADA` (`DEMASIADO_PRONTO`);
  - con una noche `EN_CURSO` en `cf_noches_automaticas` → `RECHAZADA`;
  - la web solo puede insertar `estado = EN_COLA` (el trigger fija el resto); no puede modificar ni borrar.
- **Caducidad:** una petición `EN_COLA` con más de **10 minutos** (A3) pasa a `RECHAZADA` (`CADUCADA`) cuando el proceso
  la ve. Nunca se lanza una petición vieja.

### 3.2 Cómo se recoge la petición (propuesta)

- **Una tarea programada nueva**, `ControlFarmacias - Actualizar ahora`, como `Usuari`, **cada 2 minutos** de 06:00 a
  20:45 (fuera de la ventana de la noche). Ejecuta un módulo del circuito (p. ej. `actualizar_ahora.py`):
  1. **lee** con una sesión de solo lectura si hay una petición `EN_COLA`; si no hay, termina (una consulta, sin coste);
  2. **reclama** la petición (`EN_COLA` → `EN_MARCHA`) con una función atómica (`for update skip locked`); caducada →
    `RECHAZADA`;
  3. **puertas**, las de la noche que aplican de día: puerta git (`ls-remote`), flags, Luna apagada y solo PIO,
    0 bloqueos, 0 reclamaciones, 0 documentos en `NORMALIZANDO`, ninguna noche `EN_CURSO`, ninguna de las tres
    tareas en marcha y hora fuera de 21:00–23:45. Una puerta falla → `RECHAZADA` con su motivo, sin lanzar nada;
  4. **lanza las tareas programadas existentes**, una tras otra, y espera a que termine cada una (con un tiempo
    máximo por tarea): `Importar facturas` (Usuari) → `Sincronización ControlFarmacias` (ControlFarmaciasRO; la
    identidad la pone el Programador de tareas, no el proceso) → el paso de normalización y conciliación (ver A1).
    Una tarea con resultado distinto de 0, o que supera su tiempo → `ERROR` y no se lanza la siguiente;
  5. **cierra** la petición (`OK` o `ERROR`) con el resumen de recuentos.
- **Por qué una tarea cada 2 minutos y no un servicio:** reutiliza el mismo mecanismo que la noche (Programador de
  tareas, `Usuari`), no deja un proceso vivo y, si falla, la siguiente vuelta lo ve. El retraso máximo es de 2
  minutos.
- **Lanzar tareas** con `Start-ScheduledTask` y seguirlas con `Get-ScheduledTaskInfo`. Para lanzar la de
  ControlFarmaciasRO, `Usuari` necesita permiso de ejecución sobre esa tarea (A2).

### 3.3 Estimación previa

- **Duración:** la de la última petición `OK` (`fin − inicio`). Si no hay ninguna, la suma de las últimas duraciones
  de las tres tareas (Programador de tareas) más la duración de la última noche (`cf_noches_automaticas`).
- **Uso de IA:** hoy **0**. Luna está desactivada (`luna_habilitada = false`, comprobado hoy) y los extractores son
  locales. Si algún día se habilita Luna, la estimación saldría de los documentos en cola por su coste medio. La web lo
  muestra como «sin uso de IA» mientras `luna_habilitada` sea `false`.

## 4. Decisiones que necesito de Pio

**Subida**

- **S1. Carpeta por fecha de subida o por fecha de factura.** El encargo dice fecha de subida, pero la factura HEFAME del
  30.09 la pusiste en `SETEMBRE 26\3A DESENA` (§1.2). Propuesta: **fecha de subida por defecto**, y que la web permita
  elegir otro mes y decena.
- **S2. Tamaño máximo:** propuesta 20 MB.
- **S3. Nombre:** se conserva el original saneado (propuesta), o se exige tu formato (`PROVEEDOR VTO dd.mm.aa PIO`), o
  se añade ` PIO` al final si falta.
- **S4. Nombre repetido con otro contenido:** rechazo (propuesta) o sufijo ` (2)`.

**«Actualizar ahora»**

- **A1. El paso de normalización y conciliación.** La tarea Alliance lanza la noche REAL, que admite una fila por fecha
  y exige que las tareas hayan corrido esa noche (§1.3). Lanzarla de día **bloquearía la noche de verdad**. Opciones:
  - **(a)** «Actualizar ahora» lanza solo la importación y la sincronización; la normalización y la conciliación
    siguen siendo de la noche. Sin cambios en la noche;
  - **(b)** una modalidad nueva del orquestador, `BAJO_DEMANDA`, con su propia fila (otra tabla o clave
    `fecha + modalidad`) y la puerta de tareas adaptada («las de esta petición»). Necesita código y migración, y
    respeta los límites, las paradas y el postcheck de la noche;
  - **Propuesta: (a) ahora y (b) como hito propio**, si quieres normalizar y conciliar de día.
- **A2. Lanzar la tarea de ControlFarmaciasRO desde `Usuari`:** dar a `Usuari` el permiso de ejecutar esa tarea (no de
  modificarla). Lo haces tú en el Programador de tareas, o la sincronización se queda solo en la noche.
- **A3. Caducidad:** propuesta 10 minutos. Tiempo máximo por tarea: propuesta 30 minutos.
- **A4. Migración de la cola:** número **39** (después de la 38 de Cashflow) o antes, si va primero. La función de
  reclamar y cerrar la usa el proceso del circuito con la clave del sistema: hace falta el EXECUTE de ese rol. O me
  autorizas a nombrar el rol del sistema en esa migración y su rollback, o se deja el que da Supabase por defecto, sin
  nombrarlo, retirando solo `anon`, `authenticated` y `PUBLIC` (habría que comprobar antes, en modo READ_ONLY, que
  los privilegios por defecto de producción lo conceden).
- **S6. Rol de la web para la cola:** uno nuevo (`cf_actualizar_web`, propuesta) o reutilizar `cf_pagos_web`.
