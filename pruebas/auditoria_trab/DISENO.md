# Hito TRAB: esquema de Trabajadores (migración 31)

Diseño con **OK final de Pio** (2026-11-12). Implementado **solo en local** (`CONFIRMADO POR TEST` en PostgreSQL 17
local; migración 31, tests y `desplegar_31.py` ensayado); producción no tocada. Parte del esquema propuesto por la
web y de las decisiones de Pio del 2026-11-12 (REGLAS_CRITICAS, «Trabajadores» y excepción por módulo de «Seguridad
y operación»), con sus respuestas a las 10 preguntas (§8).

## 1. Alcance y reglas

- Migración `sql/migrations/31_cf_trabajadores.sql` + rollback exacto. Solo **añade** objetos: no cambia ninguna
  tabla, función, política ni privilegio de facturas, albaranes, normalización o conciliación.
- **Farmacias:** PIO y RITA, solo en este módulo. `cf_configuracion.farmacias_habilitadas` **no cambia** (`{PIO}`); el
  permiso de Trabajadores vive en una tabla propia por módulo (§2.1).
- **Escritura de la web:** rol propio `cf_trabajadores_web`, limitado a las tablas del módulo, **sin `DELETE`**.
- **Historial solo de inserción**, escrito por trigger, con el autor que indica la web.
- **Sin DNI ni datos de salud.** Nota de evento de 200 caracteres como máximo, comprobado en la BD.
- **Fichajes de Farmatic pospuestos:** las horas se confirman a mano; este hito no lee Farmatic.
- Falla cerrado: farmacia fuera del módulo, autor ausente, valor fuera de dominio o franja incompatible → excepción y
  nada se escribe.

## 2. Tablas

Columnas comunes de las tablas de datos: `id uuid` (`gen_random_uuid()`), `created_at`, `updated_at`
(`cf_set_updated_at()`, la existente).

### 2.1 `cf_modulos_farmacias` (permiso por módulo)

| Columna | Tipo | Regla |
|---|---|---|
| `modulo` | text PK | `in ('TRABAJADORES')` (se amplía con cada módulo, por migración) |
| `farmacias` | text[] | no vacía y `<@ {PIO,RITA}` |

- Fila inicial: `TRABAJADORES = {PIO,RITA}`. La web y `cf_lectura` solo la leen; cambiarla exige migración o el editor
  SQL de Pio.
- La comprobación es una subconsulta sobre esta tabla, en las políticas RLS y en el trigger de §3 (implementación: sin
  función auxiliar ejecutable).

### 2.2 `trabajadoras`

| Columna | Tipo | Regla |
|---|---|---|
| `farmacia` | text | `in ('PIO','RITA')` y habilitada en `TRABAJADORES` (trigger) |
| `nombre` | text | 1–80 caracteres sin espacios sobrantes; **sin DNI** (no hay columna) |
| `categoria` | text | `FARMACEUTICA_TITULAR`, `FARMACEUTICA_ADJUNTA`, `TECNICA`, `AUXILIAR`, `OTRA` |
| `tipo_jornada` | text | `COMPLETA`, `MEDIA_MANANA`, `MEDIA_TARDE` (ASCII; la web muestra «Mañana») |
| `horas_diarias` | numeric(4,2) | `COMPLETA` → = 8; medias → > 0 y < 8 |
| `computa_convenio` | boolean | not null, por defecto true |
| `fecha_alta` | date | not null |
| `fecha_baja` | date | null o ≥ `fecha_alta` |
| `anulada` | boolean | por defecto false (sustituye al `DELETE`: registro erróneo) |

- Único `(id, farmacia)` (destino de la FK compuesta de §2.4) y único parcial `(farmacia, lower(nombre))` entre las no
  anuladas.
- `fecha_baja` = la trabajadora deja la farmacia; `anulada` = el registro no debió existir. Las dos quedan en el
  historial.

### 2.3 `convenio_anual`

| Columna | Tipo | Regla |
|---|---|---|
| `anio` | integer PK | 2020–2100 |
| `jornada_max_horas` | numeric(6,2) | > 0 |
| `asuntos_propios_dias` | numeric(4,1) | ≥ 0 |
| `permiso_medico_horas` | numeric(5,2) | ≥ 0 |
| `horas_semanales_referencia` | numeric(4,2) | > 0; **40 provisional** |
| `estado` | text | `FIRMADO_PENDIENTE_PUBLICACION` / `PUBLICADO` |
| `fuente` | text | not null, 1–200 caracteres (convenio, BOE…) |

Sin columna de farmacia: el convenio es el mismo para las dos.

### 2.4 `eventos_calendario`

| Columna | Tipo | Regla |
|---|---|---|
| `trabajadora_id`, `farmacia` | uuid, text | FK compuesta a `trabajadoras (id, farmacia)`: la farmacia del evento es la de la trabajadora |
| `fecha` | date | not null |
| `franja` | text | `MANANA` / `TARDE` (ASCII) |
| `tipo` | text | lista cerrada (abajo) |
| `estado` | text | `PLANIFICADO` / `CONFIRMADO` |
| `horas` | numeric(4,2) | opcional; null o > 0 y ≤ 8 (por defecto, abajo) |
| `nota` | text | null o `char_length(nota) <= 200` |

- **Tipos:**
  - `JORNADA`, `VACACIONES`, `ASUNTOS_PROPIOS`;
  - `PERMISO_RETRIBUIDO`, `PERMISO_NO_RETRIBUIDO`, `PERMISO_MEDICO`;
  - `DESCANSO_COMPENSATORIO`;
  - `BAJA`: sin motivo ni diagnóstico, y no hay columna para ellos;
  - `FESTIVO`: día festivo no trabajado;
  - `TURNO_GUARDIA`: también el festivo trabajado; **se registra, no computa**;
  - `LOCALIZADA`.
- **Horas por defecto** si `horas` es null: `COMPLETA` → `MANANA` 4,5 h (9:00–13:30) y `TARDE` 3,5 h (17:00–20:30);
  `MEDIA_MANANA` / `MEDIA_TARDE` → `horas_diarias` en su franja. Las calcula la vista `v_eventos_calendario_horas`
  (§2.8), no se guardan.
- **Único `(trabajadora_id, fecha, franja)`** en la BD.
- Trigger: la fecha debe estar dentro de `[fecha_alta, fecha_baja]` de una trabajadora no anulada. La franja contraria
  a una media jornada **no se bloquea** en la BD (cambios de turno): la web avisa.
- **Relleno del año:**
  - Lo hace la web con `INSERT … ON CONFLICT DO NOTHING` (basta `INSERT`), así que nunca pisa un evento existente.
  - Cubre de lunes a viernes, en las franjas de la jornada de cada trabajadora (las dos si es `COMPLETA`, la suya si es
    media) y dentro de su alta y baja.
  - Los laborables quedan como `JORNADA` `PLANIFICADO`. Los días de la tabla `festivos` (de su farmacia o sin farmacia)
    quedan como `FESTIVO` `PLANIFICADO`.
  - Si trabaja un festivo, Pio lo cambia a `TURNO_GUARDIA`.
  - No hay `DELETE`: un evento se corrige con `UPDATE` (tipo, estado, horas, nota), que queda en el historial.
- La web avisa de no anotar datos de salud en la nota. La BD solo limita la longitud: no puede reconocer un dato de
  salud.

### 2.5 `guardias_farmacia`

`farmacia`, `fecha`, `nota` (null o ≤ 200), `anulada`; único parcial `(farmacia, fecha)` entre las no anuladas.
Es el calendario de guardias de la farmacia. Quién la cubre se anota en `eventos_calendario` con
`tipo = TURNO_GUARDIA`.

### 2.6 `festivos`

`fecha`, `ambito` (`NACIONAL` / `AUTONOMICO` / `LOCAL`), `farmacia` (null = las dos; un `LOCAL` exige farmacia),
`descripcion` (1–100), `anulado`. Único parcial `(fecha, coalesce(farmacia, '*'))` entre los no anulados.

### 2.7 `trabajadores_historial` (solo inserción)

`id bigint identity`, `tabla`, `registro_id`, `operacion` (`INSERT`/`UPDATE`), `antes jsonb`, `despues jsonb`, `autor`,
`created_at`.

- Lo escribe un trigger `AFTER INSERT OR UPDATE` de cada tabla de §2.2–2.6. La función es `SECURITY DEFINER` con
  `search_path` fijo, así que la web no necesita `INSERT` sobre el historial.
- **Autor:** la web abre cada transacción con `set local cf.autor = 'Marc'`. Si `current_setting('cf.autor', true)`
  está vacío, la escritura falla (`AUTOR_AUSENTE`) y no se guarda nada. Es una atribución que declara la web, no una
  autenticación.
- `BEFORE UPDATE OR DELETE` y `TRUNCATE` → excepción (como `cf_historial_append_only` de la 10).

### 2.8 `v_eventos_calendario_horas` (vista)

Cada evento con sus horas efectivas: `horas`, o el valor por defecto de §2.4. Usa `security_invoker`, así que aplica la
RLS de quien la consulta. La leen `cf_trabajadores_web` y `cf_lectura`.

## 3. Permiso de farmacia por módulo

- **Trigger `BEFORE INSERT OR UPDATE`** en las tablas con farmacia (`cf_trab_comprobar_farmacia()`): farmacia en `TRABAJADORES`
  o excepción `FARMACIA_NO_HABILITADA_EN_MODULO`. Vale para cualquier rol, también los que se saltan RLS.
- **RLS activada** en las 7 tablas nuevas. Políticas para `cf_trabajadores_web` (select, insert y update, con
  `using` / `with check` por módulo) y para `cf_lectura` (select). `anon` y `authenticated`: ninguna política.
- Facturas, albaranes y conciliación **siguen con `farmacias_habilitadas = {PIO}`**: no se toca ninguna de sus
  funciones ni políticas.

## 4. Roles y privilegios

- **`cf_trabajadores_web`** (nuevo, mismo patrón que `cf_lectura` de la 29):
  - LOGIN sin contraseña en el repositorio (la fija Pio en el editor SQL);
  - nosuperuser, nocreatedb, nocreaterole, noinherit, noreplication, nobypassrls;
  - `connection limit 5`, `statement_timeout` e `idle_in_transaction_session_timeout` de 60 s.
  - Privilegios:
    - `USAGE` de `public`;
    - `SELECT`, `INSERT` y `UPDATE` solo sobre `trabajadoras`, `convenio_anual`, `eventos_calendario`,
      `guardias_farmacia` y `festivos`;
    - `SELECT` sobre `trabajadores_historial`, `cf_modulos_farmacias` y `v_eventos_calendario_horas`.
  - **Sin `DELETE` ni `TRUNCATE`.** Ningún privilegio sobre el resto del esquema y ningún `EXECUTE` explícito.
- **`cf_lectura`:** `SELECT` sobre las 7 tablas nuevas y la vista, más sus políticas.
- **Privilegios por defecto de Supabase:** las tablas y la vista nuevas de `public` los reciben solas. La 31 revoca
  todo sobre ellas a `anon`, a `authenticated` y **al rol del sistema** (decisión de Pio, §8.10): ningún worker las
  necesita.
- **AUTORIZACIÓN EXPRESA DE PIO (2026-11-12):** el rol del sistema se puede nombrar **solo** en
  `31_cf_trabajadores.sql` y en su rollback. Los tests, `desplegar_31.py` y la documentación lo llaman «rol del
  sistema» y lo leen de los privilegios por defecto sin escribir su nombre; si eso no fuera posible → PARA y
  autorización nueva.

## 5. Tests (`tests/facturas/runtime_supabase/test_integracion_pg17_31_trabajadores.py`, `pg17_local`, 73)

1. La 31 se aplica con la imitación del `postgres` de Supabase y el rollback deja la base idéntica.
2. **`cf_trabajadores_web`:**
   - puede `SELECT`/`INSERT`/`UPDATE` en el módulo;
   - `DELETE` y `TRUNCATE` → permiso denegado;
   - `SELECT`/`INSERT` en `facturas`, `documentos_facturas`, `albaranes`, `conciliaciones` y `cf_configuracion` →
     denegado;
   - `EXECUTE` sobre cada función de facturas, albaranes y conciliación → denegado;
   - no puede escribir en el historial ni en `cf_modulos_farmacias`.
3. **PIO y RITA** escriben en Trabajadores; una farmacia fuera de `TRABAJADORES` → `FARMACIA_NO_HABILITADA_EN_MODULO`
   (con y sin RLS).
4. **Facturas, albaranes y conciliación siguen solo PIO:**
   - `farmacias_habilitadas = {PIO}`;
   - la normalización, la persistencia de conciliación y el selector rechazan o ignoran RITA como antes;
   - las políticas existentes no ven filas de RITA.
5. **Dominios:**
   - `horas_diarias` según la jornada;
   - los once tipos, las cinco categorías y los dos estados de convenio; los valores fuera de la lista y los valores
     con Ñ se rechazan;
   - horas por defecto de la vista (4,5 / 3,5 en `COMPLETA`; `horas_diarias` en medias) y `horas` explícitas;
   - relleno del año: lunes a viernes, `JORNADA` en laborables y `FESTIVO` en los festivos de su farmacia o comunes,
     nada fuera del alta o la baja, y un segundo relleno sin cambios;
   - una franja contraria a la media jornada se acepta;
   - el rol del sistema no tiene privilegios sobre las tablas nuevas;
   - nota de 200 caracteres aceptada y de 201 rechazada;
   - un evento duplicado `(trabajadora, fecha, franja)` se rechaza;
   - franja incompatible con media jornada y evento fuera del alta o la baja se rechazan;
   - `ON CONFLICT DO NOTHING` no pisa un evento existente.
6. **Historial:**
   - una fila por cada `INSERT`/`UPDATE`, con autor y antes/después;
   - sin `cf.autor` → `AUTOR_AUSENTE` y nada escrito;
   - `UPDATE`/`DELETE`/`TRUNCATE` del historial → excepción.
7. **`cf_lectura`** lee las tablas nuevas y no puede escribir. `anon` y `authenticated` no ven nada.
8. Ensayo completo de `desplegar_31.py` (norma 2AX): SHA, precondiciones, aplicación y postcondiciones; un segundo
   ensayo falla en precondiciones y revierte sin cambios.

## 6. Despliegue (hito TRAB-D, aparte y con confirmación de Pio)

- Preflight READ_ONLY:
  - la 30 presente;
  - las tablas y el rol nuevos ausentes;
  - flags `f|f|f|{PIO}`;
  - tareas a 60 min o más.
- `desplegar_31.py` con postcheck 2AX: solo cambian los objetos de la 31; fuera de ellos todo idéntico, también
  `cf_configuracion`.
- Después, Pio fija la contraseña de `cf_trabajadores_web` en el editor SQL y la guarda en la web, nunca en el
  repositorio.

## 7. Fuera de alcance

- La web, que vive fuera de este repositorio.
- Los fichajes de Farmatic.
- Cálculos de saldo de horas o vacaciones: se derivan en la web o en una vista posterior.
- Cualquier cambio en facturas, albaranes o conciliación.

## 8. Decisiones de Pio (2026-11-12)

1. **Tipos:** los once de §2.4. `BAJA` va sin motivo ni diagnóstico. `TURNO_GUARDIA` también cubre el festivo
   trabajado.
2. **`horas` opcional** con los valores por defecto de §2.4.
3. **Relleno del año:** de lunes a viernes en las franjas de su jornada; laborables `JORNADA` y festivos `FESTIVO`,
   todos `PLANIFICADO`. Un festivo trabajado pasa a `TURNO_GUARDIA`: se registra, no computa.
4. **Franja contraria en media jornada:** no se bloquea; la web avisa.
5. **`categoria`:** lista cerrada de §2.2.
6. **Estados del convenio:** `FIRMADO_PENDIENTE_PUBLICACION` / `PUBLICADO`.
7. **Guardias:** `guardias_farmacia` = farmacia y fecha; quién la cubre, `TURNO_GUARDIA` en el calendario.
8. **Festivos:** farmacia vacía = las dos.
9. **ASCII:** `MEDIA_MANANA` y `MANANA`.
10. **Revocar** al rol del sistema los privilegios por defecto sobre las tablas nuevas. Autorización expresa para
    nombrarlo solo en la 31 y su rollback (§4).

11. **Cómputo (DECISIÓN DE PIO, 2026-11-12):** `TURNO_GUARDIA` (también el festivo trabajado) y `LOCALIZADA` **no
    computan**: se registran, no suman. El cómputo de horas sigue fuera de alcance (§7).
