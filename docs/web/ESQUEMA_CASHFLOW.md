# Esquema de Cashflow para la web

Actualizado: 2026-11-22. Fuente: migración 38 (`sql/migrations/38_cf_cashflow.sql`), desplegada en producción el
2026-11-22. Reglas en `docs/contexto/REGLAS_CRITICAS.md` («Cashflow (H7)») y diseño en
`pruebas/auditoria_h7/DISENO.md`.

## Qué es y quién escribe

- Los datos salen del Excel de cashflow de Pio. El sistema lo importa cada noche a las 23:45 (tarea «ControlFarmacias
  - Importar Cashflow») y, además, cuando Pio lanza una importación manual.
- **La web solo lee**, con el rol `cf_lectura`. Nadie escribe directamente en estas tablas. La única escritura es la
  función de importación del sistema, que la web no puede ejecutar.
- Las tablas son **solo de inserción**: no hay `UPDATE` ni `DELETE`. Una importación nueva no modifica las anteriores;
  solo cambia cuál es la vigente.
- Primera importación real: 2026-11-22, `OK`, con 5131 importes y 539 saldos.

## Tablas

### `cf_cashflow_cuentas` (fija: 3 filas)

| Columna | Tipo | Significado |
|---|---|---|
| `codigo` | `text`, clave primaria | `PIO`, `RITA` o `SL` |
| `farmacia` | `text`, nulo en `SL` | `PIO`, `RITA` o nulo (cuenta sin farmacia) |
| `hoja` | `text` | Hoja del Excel: `PÍO` (con tilde), `RITA` o `SL` |

### `cf_cashflow_importaciones` (una fila por importación)

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid`, clave primaria | Identificador de la importación |
| `archivo_nombre` | `text` | Nombre del fichero Excel, sin ruta |
| `archivo_hash` | `text`, único | SHA-256 del fichero (64 caracteres hexadecimales). Un mismo fichero no se importa dos veces |
| `origen` | `text` | `NOCHE` (tarea de las 23:45) o `MANUAL` (lanzada por Pio) |
| `estado` | `text` | `OK` o `ERROR` |
| `detalle_error` | `text` | Solo en `ERROR`: códigos y posiciones de celda (por ejemplo, `CUADRE_NO_VALIDO:RITA:H`). Nulo en `OK`. Nunca lleva conceptos |
| `filas` | `integer` | Número de importes guardados; 0 en `ERROR` |
| `importado_at` | `timestamptz` | Momento de la importación |
| `vigente` | `boolean` | `true` en la importación vigente (como máximo una). Solo puede serlo una `OK` |

Una importación `ERROR` es solo la cabecera: no tiene importes ni saldos, nunca es vigente y no cambia la vigente
anterior.

### `cf_cashflow_importes` (importes por categoría y decena)

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `bigint`, clave primaria | Identificador |
| `importacion_id` | `uuid`, referencia a `cf_cashflow_importaciones.id` | Importación a la que pertenece |
| `cuenta` | `text`, referencia a `cf_cashflow_cuentas.codigo` | `PIO`, `RITA` o `SL` |
| `farmacia` | `text`, nulo en `SL` | Copia de la farmacia de la cuenta (para la RLS) |
| `decena_inicio` | `date` | Primer día de la decena |
| `decena_fin` | `date` | Último día de la decena |
| `categoria` | `text` | Literal de la columna A del Excel; empieza por `RE ` (entrada) o `RS ` (salida) |
| `concepto` | `text`, puede ser nulo | Literal de la columna B del Excel |
| `importe` | `numeric(14,2)`, distinto de 0 | Importe con el **signo de la celda** (ver «Signo») |
| `fila_excel` | `integer` | Fila de la hoja del Excel de la que sale |

Solo se guardan los importes distintos de 0. Una categoría sin fila en una decena vale 0 en esa decena.

### `cf_cashflow_saldos` (saldos por cuenta y decena)

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `bigint`, clave primaria | Identificador |
| `importacion_id` | `uuid`, referencia a `cf_cashflow_importaciones.id` | Importación a la que pertenece |
| `cuenta` | `text`, referencia a `cf_cashflow_cuentas.codigo` | `PIO`, `RITA` o `SL` |
| `farmacia` | `text`, nulo en `SL` | Copia de la farmacia de la cuenta (para la RLS) |
| `decena_inicio` | `date` | Primer día de la decena. El fin se deduce con la regla de «Decenas» |
| `saldo_inicial` | `numeric(14,2)` | Saldo inicial de la decena |
| `saldo_formulas` | `numeric(14,2)` | Saldo final según las fórmulas del Excel |
| `saldo_bancos` | `numeric(14,2)`, puede ser nulo | Saldo final según bancos, anotado por Pio (ver E7) |

Única: una fila por (`importacion_id`, `cuenta`, `decena_inicio`).

## Lectura con `cf_lectura` (RLS)

- `cf_lectura` tiene `SELECT` en las cuatro tablas y nada más: ni escritura ni la función de importación.
- **Importaciones:** visibles todas.
- **Cuentas, importes y saldos:** visibles si no tienen farmacia (`SL`) o si su farmacia está en el módulo
  `CASHFLOW` de `cf_modulos_farmacias`:

  ```sql
  farmacia is null
  or exists (select 1 from cf_modulos_farmacias m
             where m.modulo = 'CASHFLOW' and farmacia = any(m.farmacias))
  ```

- `cf_modulos_farmacias` tiene `CASHFLOW = {PIO, RITA}`. **RITA solo es visible en este módulo, con sus datos
  bancarios.** Sus facturas siguen desactivadas: en facturas, albaranes y conciliación solo aparece PIO.
- Ningún otro rol de la web (`cf_trabajadores_web`, `cf_pagos_web`), ni `anon` ni `authenticated`, tiene acceso a
  estas tablas.

## Cómo leer la importación vigente

1. Busca la importación vigente:

   ```sql
   select id, archivo_nombre, importado_at
   from cf_cashflow_importaciones
   where vigente;
   ```

   Devuelve 0 o 1 filas. Con 0, todavía no hay datos que mostrar.
2. Filtra importes y saldos por ese `id`:

   ```sql
   select * from cf_cashflow_importes where importacion_id = :id;
   select * from cf_cashflow_saldos   where importacion_id = :id;
   ```

   **No mezcles importaciones:** las anteriores se conservan con todas sus filas.
3. Para avisar de un `ERROR` reciente, mira la última por `importado_at`. Si es `ERROR`, la vigente sigue siendo la
   `OK` anterior.

## Signo y cuadre (E1)

- El importe se guarda con el signo de la celda del Excel. El sentido lo da el prefijo de la categoría:
  - `RE` es una entrada;
  - `RS` es una salida: un `RS` **positivo resta** del saldo y un `RS` **negativo** (una devolución) **suma**.
- **Cuadre** de cada cuenta y decena:

  `saldo_inicial + Σ importes RE − Σ importes RS = saldo_formulas`

  El importador lo comprueba con los valores del Excel sin redondear, y la función de importación lo vuelve a
  comprobar con los valores guardados. Esta admite una diferencia de hasta 0,005 por cada importe redondeado al
  céntimo en esa cuenta y decena, y ninguna por saldo redondeado. Si no cuadra, no se guarda ningún importe ni saldo
  de ese fichero: queda solo una cabecera `ERROR` y la vigente anterior no cambia.

## Decenas

- Empiezan el día 1, 11 o 21.
- Acaban el día 10, el 20 o el último día del mes. La tercera decena tiene 8, 9, 10 u 11 días.
- En el Excel actual hay 180 decenas por cuenta, del 2024-01-01 al 2028-12-31.

## Casos especiales

- **E5:** la primera decena de `SL` no tiene saldo en el Excel. No hay fila de saldo para esa decena y tampoco
  importes.
- **E7:** el saldo según bancos:
  - **nulo:** la decena aún no está cuadrada con el banco;
  - **distinto de `saldo_formulas`:** es una diferencia que la web muestra. Nunca es un error de la importación.
- `SL` no tiene importes en el Excel actual: solo saldos.
- Los avisos de la importación (celdas con `=` o solo espacios tratadas como vacías, redondeos) no se guardan en la
  base: están en el informe local de cada importación.
