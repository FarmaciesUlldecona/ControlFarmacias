# Esquema de Cashflow para la web

Actualizado: 2026-11-26. Fuentes:

- migración 38 (`sql/migrations/38_cf_cashflow.sql`), desplegada en producción el 2026-11-22: lo importado del Excel;
- migración 40 (`sql/migrations/40_cf_cashflow_prevision.sql`), desplegada en producción el 2026-11-26: la previsión
  que escribe la web (ver «Previsión: apuntes de la web (migración 40)»).

Reglas en `docs/contexto/REGLAS_CRITICAS.md` («Cashflow (H7)») y diseños en `pruebas/auditoria_h7/DISENO.md` y
`pruebas/auditoria_h7b/DISENO.md`.

## Qué es y quién escribe

- Los datos salen del Excel de cashflow de Pio. El sistema lo importa cada noche a las 23:45 (tarea «ControlFarmacias
  - Importar Cashflow») y, además, cuando Pio lanza una importación manual.
- **En lo importado, la web solo lee**, con el rol `cf_lectura`. Nadie escribe directamente en estas tablas. La única
  escritura es la función de importación del sistema, que la web no puede ejecutar. Lo que escribe la web son los
  apuntes de previsión de la migración 40, en otras tablas y con otro rol.
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

## Previsión: apuntes de la web (migración 40)

Desplegada en producción el 2026-11-26. Son los apuntes que no tienen factura. Solo previsión futura: nada de esto
cambia lo importado ni lo pasado, y el sistema no lo usa para decidir nada.

### Rol de escritura `cf_cashflow_web`

- Rol con `LOGIN`. **Pio entrega la contraseña aparte**; no está en el repositorio. Por el pooler el usuario es
  `cf_cashflow_web.<project_ref>`. Límite de 5 conexiones; `statement_timeout` e `idle_in_transaction_session_timeout`
  de 60 s.
- Permisos:
  - `SELECT` e `INSERT` en `cf_cashflow_conceptos`, `cf_cashflow_recurrentes` y `cf_cashflow_apuntes`;
  - `UPDATE` solo de `anulado` y `motivo_anulacion` y, en apuntes, también de `sustituido_factura_id` y
    `sustituido_vencimiento_orden`;
  - `SELECT` de `cf_cashflow_apuntes_historial`;
  - `EXECUTE` de `cf_cashflow_ocurrencias` y `cf_cashflow_fechas_recurrente`;
  - `EXECUTE` de `cf_cashflow_farmacia_habilitada(farmacia)`, la función de su RLS (security definer: comprueba si
    la farmacia está en el módulo `CASHFLOW`). La usan las políticas; la web no necesita llamarla.
- **No lee** lo importado (cuentas, importaciones, importes, saldos), facturas ni vencimientos: eso se lee con
  `cf_lectura`. No borra (`DELETE` y `TRUNCATE` se rechazan).
- **Autor obligatorio:** cada transacción que escriba hace antes `set local cf.autor = '<usuario>'` (1–60
  caracteres). Sin él, `AUTOR_AUSENTE`.
- RLS: solo las filas de una farmacia del módulo `CASHFLOW` de `cf_modulos_farmacias` (hoy PIO y RITA).

`cf_lectura` también lee las cuatro tablas (con la misma RLS) y ejecuta las dos funciones; no escribe.

### Tablas

Columnas comunes de las tres tablas de escritura:

| Columna | Tipo | Significado |
|---|---|---|
| `id` | `uuid`, clave primaria | Lo genera la BD |
| `cuenta` | `text` | `PIO` o `RITA` |
| `farmacia` | `text` | La pone el trigger (igual a la cuenta); lo que envíe la web se ignora |
| `categoria` | `text` | Una categoría `RE …`/`RS …` de la plantilla de la cuenta en la importación vigente |
| `autor` | `text` | Lo pone el trigger desde `cf.autor` |
| `creado_at` | `timestamptz` | Lo pone el trigger |
| `anulado`, `anulado_por`, `anulado_at`, `motivo_anulacion` | | Anulación; ver «Anular» |

- **`cf_cashflow_conceptos`:** `nombre` (1–120) y `proveedor_cif` opcional (`^[A-Z0-9]{5,20}$`), para colocar los
  vencimientos de ese proveedor. Un nombre vigente por cuenta y categoría (sin distinguir mayúsculas ni espacios
  repetidos) y un concepto vigente por cuenta y CIF.
- **`cf_cashflow_recurrentes`:** `concepto` (1–255), `importe` (> 0), `nota` (≤ 500), `frecuencia` (`MENSUAL`,
  `TRIMESTRAL` o `ANUAL`), `dia` (1–31; si el mes no lo tiene, el último día del mes), `inicio` (debe ser una
  ocurrencia: la primera) y `fin` opcional (≥ `inicio`).
- **`cf_cashflow_apuntes`:** `fecha`, `concepto` (1–255), `importe`, `nota` (≤ 500), `recurrente_id`,
  `fecha_ocurrencia`, `sustituido_factura_id`, `sustituido_vencimiento_orden`. Dos tipos:
  - **suelto:** `importe` > 0, sin `recurrente_id` ni `fecha_ocurrencia`;
  - **anulación de una ocurrencia:** `recurrente_id` y `fecha_ocurrencia`, sin `importe`. Cuenta, categoría y
    concepto los copia el trigger de la recurrente, y `fecha` = `fecha_ocurrencia`.
- **`cf_cashflow_apuntes_historial`** (solo lectura para la web): `tabla`, `registro_id`, `cuenta`, `farmacia`,
  `operacion` (`INSERT` o `UPDATE`), `antes`, `despues`, `autor`, `created_at`. Lo escribe un trigger en cada alta y
  anulación.

El importe es siempre positivo: el sentido lo da el prefijo de la categoría (`RE` entra, `RS` sale).

### Validaciones al dar de alta (la BD falla cerrado)

| Código | Cuándo |
|---|---|
| `AUTOR_AUSENTE` | Sin `set local cf.autor` |
| `CUENTA_NO_VALIDA` | La cuenta no es `PIO` ni `RITA` |
| `FARMACIA_NO_HABILITADA` | La farmacia no está en el módulo `CASHFLOW` |
| `SIN_IMPORTACION_VIGENTE` | No hay importación vigente |
| `CATEGORIA_FUERA_DE_PLANTILLA` | La categoría no está en la plantilla de la cuenta en la vigente |
| `CONCEPTO_DESCONOCIDO` | El concepto (de un apunte o una recurrente) no está, para esa cuenta y categoría, ni en la plantilla de la vigente ni en `cf_cashflow_conceptos` sin anular |
| `IMPORTE_NO_POSITIVO` | Importe ausente o ≤ 0 (suelto o recurrente) |
| `FECHA_AUSENTE` | Apunte suelto sin `fecha` |
| `SIN_SALDO_DE_BANCO` | La cuenta no tiene ninguna decena con saldo de bancos en la vigente |
| `FECHA_NO_FUTURA` | La fecha (o ninguna ocurrencia de la recurrente) es posterior al fin de la última decena con saldo de bancos |
| `FRECUENCIA_NO_VALIDA`, `DIA_NO_VALIDO`, `INICIO_AUSENTE`, `FIN_ANTERIOR_A_INICIO`, `INICIO_NO_ES_OCURRENCIA` | Recurrente mal formada |
| `OCURRENCIA_NO_VALIDA`, `RECURRENTE_NO_ENCONTRADA`, `RECURRENTE_ANULADA`, `IMPORTE_EN_ANULACION_DE_OCURRENCIA`, `OCURRENCIA_SIN_RECURRENTE` | Anulación de ocurrencia mal formada |
| `SUSTITUCION_SOLO_AL_ANULAR`, `SUSTITUCION_INCOMPLETA`, `FACTURA_NO_ENCONTRADA`, `FARMACIA_DISTINTA_DE_LA_FACTURA`, `VENCIMIENTO_NO_ENCONTRADO` | Sustitución no válida |

Al anular (`UPDATE`):

| Código | Cuándo |
|---|---|
| `SOLO_ANULAR` | Cambia algo distinto de la anulación (y, en un apunte suelto, la sustitución), o la fila ya estaba anulada |
| `MOTIVO_ANULACION_AUSENTE` | Se anula sin `motivo_anulacion` (vacío o solo espacios) |
| `AUTOR_AUSENTE` | Sin `set local cf.autor` |
| `SUSTITUCION_INCOMPLETA`, `FACTURA_NO_ENCONTRADA`, `FARMACIA_DISTINTA_DE_LA_FACTURA`, `VENCIMIENTO_NO_ENCONTRADO` | Sustitución no válida |
| `BORRADO_NO_PERMITIDO` | `DELETE` o `TRUNCATE` (además, la web no tiene esos privilegios) |

### Anular (nunca borrar)

- El único cambio admitido es `anulado` de `false` a `true` con `motivo_anulacion` (1–500). `anulado_por` y
  `anulado_at` los pone el trigger. Lo demás no cambia (`SOLO_ANULAR`), sin motivo no se anula
  (`MOTIVO_ANULACION_AUSENTE`) y lo anulado no se reabre. Para corregir, se anula y se da de alta de nuevo.
- Anular una recurrente anula todas sus ocurrencias. Anular una sola ocurrencia es dar de alta un apunte de
  «anulación de una ocurrencia».
- **Sustitución confirmada por Pio:** al anular un apunte suelto se pueden guardar `sustituido_factura_id` y
  `sustituido_vencimiento_orden` (el vencimiento que lo sustituye). Para una ocurrencia, van en el alta de su
  anulación. La BD comprueba que el vencimiento existe y que su factura es de la farmacia de la cuenta; un
  vencimiento sustituye a un solo apunte. Elegir el candidato (por ejemplo, el ±5 %) es cosa de la web.

### Ocurrencias

```sql
select * from cf_cashflow_ocurrencias(:desde, :hasta);
-- recurrente_id, cuenta, farmacia, categoria, concepto, importe, fecha
```

Devuelve las ocurrencias de las recurrentes no anuladas en el intervalo, sin las anuladas una a una, con la RLS de
quien llama. Devuelve todas las del intervalo: que solo cuenten las posteriores al último saldo de bancos de la
cuenta lo aplica el motor de la web. **La BD no elige la fuente por celda ni calcula la media:** la prioridad
(apunte > Excel > media; con vencimientos, el mayor en valor absoluto) es del motor de la web.
