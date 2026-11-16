# Migración 34: guardias y festivos del módulo de Trabajadores (Hito TRAB-34, TA3)

Petición de la web con OK de Pio (2026-11-16). Propuesta de la web en
`origin/web/fase1:web/docs/propuesta_tablas_ta3.sql`. **Solo local**: migración, rollback, `desplegar_34.py` ensayado
con la imitación del `postgres` de Supabase y tests en PostgreSQL 17 local. El despliegue (TRAB-34-D) requiere
preflight, alcance explícito y confirmación de Pio.

Ficheros:

- `sql/migrations/34_cf_trabajadores_guardias.sql` y su rollback;
- `pruebas/auditoria_trab/desplegar_34.py`;
- `tests/facturas/runtime_supabase/test_integracion_pg17_34_trabajadores.py` (38 tests).

Requiere la 33 (estado productivo).

**AUTORIZACIÓN EXPRESA DE PIO (2026-11-16):** el rol del sistema se nombra solo en la 34 y en su rollback (como en la
31 y la 33). Sirve para retirarle los privilegios por defecto de Supabase sobre las tablas y funciones nuevas, y sobre
`guardias_farmacia` cuando el rollback la recrea.

Preflight READ_ONLY de producción (2026-11-16 09:01 UTC; evidencia fuera del repositorio en
`C:\ControlFarmacias\evidencias_trab_34`):

- `guardias_farmacia`: 0 filas y 0 filas de historial;
- `festivos`: 0 filas;
- `guardias_semana` y `guardias_festivo`: no existen;
- restricciones, políticas y triggers de `festivos` y `guardias_farmacia`: iguales a la 31.

## 1. Lo marcado «A CONFIRMAR», resuelto con la 31

| Punto de la propuesta | En la 31 | En la 34 |
|---|---|---|
| Check de `ambito`/`farmacia` de `festivos` | `festivos_local_con_farmacia` (`ambito <> 'LOCAL' or farmacia is not null`) | Se retira: un festivo LOCAL sin farmacia es de las dos (decisión de Pio) |
| Unicidad de festivos comunes | `festivos_unico (fecha, coalesce(farmacia, '*')) where not anulado` ya da uno común por fecha | Sin índice nuevo |
| RLS de `festivos` | Ya tiene RLS: `farmacia is null` o farmacia del módulo, para la web y `cf_lectura` | Sin políticas nuevas |
| Privilegios de `festivos` | `SELECT`, `INSERT` y `UPDATE` para la web, sin `DELETE`; `SELECT` para `cf_lectura` | Sin cambios |
| Función de historial | `cf_trab_historial()`; ya lanza `AUTOR_AUSENTE` sin `cf.autor` | Se engancha a las dos tablas nuevas; `festivos` ya la tenía |
| Autor y DELETE | Autor por `cf.autor` en el historial; sin `DELETE` por privilegios | Igual: no hace falta el trigger `cf_ta3_exigir_autor` de la propuesta |
| Farmacias del módulo en las políticas | `exists (select 1 from cf_modulos_farmacias ...)` | Igual, más `farmacia = 'OTRA'`; sin la función `security definer` ejecutable por la web de la propuesta (`desplegar_3x` exige que la web no ejecute funciones `security definer`) |

## 2. `festivos` (se reutiliza)

- Se retira `festivos_local_con_farmacia`: un festivo LOCAL puede no llevar farmacia (vacía = las dos).
- `ambito` toma `'LOCAL'` por defecto.
- Lo demás sigue como en la 31: unicidad, la descripción de 1 a 100 caracteres, RLS, privilegios e historial.
  - La propuesta limitaba la descripción a 60 caracteres. No se aplica, porque no lo pidió Pio: la web puede limitarla
    en su formulario.
- Trigger nuevo `festivos_anular_guardia` (AFTER UPDATE). Si un festivo común vigente se anula, cambia de fecha o pasa
  a tener farmacia, anula la guardia de esa fecha en la misma transacción. El historial lleva el mismo `cf.autor`.

## 3. `guardias_semana`

| Columna | Tipo |
|---|---|
| `id` | uuid, clave primaria |
| `lunes` | date; tiene que ser lunes (`isodow = 1`) |
| `farmacia` | `PIO`, `RITA` u `OTRA` (la tercera farmacia del pueblo, ajena) |
| `persona_guardia_id` | uuid; clave externa compuesta `(persona_guardia_id, farmacia)` a `trabajadoras (id, farmacia)` |
| `persona_apoyo_sabado_id` | uuid, opcional; clave externa compuesta igual |
| `anulada` | boolean, default false |
| `created_at`, `updated_at` | timestamptz |

- Una guardia por semana entre las no anuladas (índice parcial `guardias_semana_lunes_unico`).
- `OTRA` no lleva personas. En PIO y RITA la persona de guardia es obligatoria, y el apoyo es distinto de ella.
- Las personas son de la farmacia de la guardia. Lo garantiza la clave externa compuesta: `OTRA` no tiene
  trabajadoras.
- Trigger `cf_trab_comprobar_guardia_semana`, como en la propuesta:
  - la persona de guardia está sin anular y de alta el sábado y el domingo;
  - el apoyo, de alta el sábado;
  - si no, `PERSONA_NO_VALIDA`.
  - Anular una guardia no exige que las personas sigan de alta (igual que los eventos en la 33).

## 4. `guardias_festivo`

| Columna | Tipo |
|---|---|
| `id` | uuid, clave primaria |
| `fecha` | date |
| `farmacia` | `PIO`, `RITA` u `OTRA` |
| `persona_id` | uuid; clave externa compuesta `(persona_id, farmacia)` a `trabajadoras (id, farmacia)` |
| `anulada` | boolean, default false |
| `created_at`, `updated_at` | timestamptz |

- Una por fecha entre las no anuladas (`guardias_festivo_fecha_unico`).
- `OTRA` sin persona; PIO y RITA, con persona.
- Trigger `cf_trab_comprobar_guardia_festivo`:
  - la fecha es un festivo **común** (sin farmacia) no anulado; si no, `NO_ES_FESTIVO`;
  - la persona está sin anular y de alta ese día; si no, `PERSONA_NO_VALIDA`.
- La persona por defecto la propone la web; la tabla guarda siempre la persona elegida.

## 5. Reglas comunes de las dos tablas

- **Farmacia:** `cf_trab_comprobar_farmacia_guardia` admite `OTRA` o una farmacia del módulo, también para los roles
  que se saltan la RLS. Si no, `FARMACIA_NO_HABILITADA_EN_MODULO`.
- **`updated_at` e historial:** los triggers de la 31. Sin `cf.autor`, `AUTOR_AUSENTE`.
- **RLS** (lectura para la web y `cf_lectura`; inserción y actualización para la web): `farmacia = 'OTRA'` o una
  farmacia del módulo. Las filas `OTRA` son visibles para PIO y RITA.
- **Historial de las filas `OTRA`:** la política de lectura de `trabajadores_historial` añade `farmacia = 'OTRA'` para
  que también se vea.
- **Privilegios:**
  - la web, `SELECT`, `INSERT` y `UPDATE`, sin `DELETE` ni `TRUNCATE`;
  - `cf_lectura`, `SELECT`;
  - anon, authenticated, el rol del sistema y PUBLIC, ninguno.
  - Las cinco funciones nuevas son `security definer` y solo las ejecuta su propietario, desde los triggers.

## 6. `guardias_farmacia` (se retira)

- La migración falla cerrado con `GUARDIAS_FARMACIA_NO_VACIA` si tiene alguna fila, aunque esté anulada.
- Si está vacía, la elimina. El historial (inexistente en producción) se conserva.
- `desplegar_34.py` también lo exige en su precondición 2.
- `src/facturas/runtime_supabase/noche_automatica.py` (`TABLAS_TRABAJADORES`):
  - añade `guardias_semana`, `guardias_festivo` y `trabajadoras_ajustes_anuales`;
  - la tabla de la 33 faltaba desde su despliegue: una escritura de la web en ella habría contado como fila ajena en
    el postcheck 2AX de la noche y de las series 2BJ/2BP;
  - conserva `guardias_farmacia` mientras exista: solo se leen las tablas presentes.
- `pruebas/auditoria_trab/probar_acceso_cf_trabajadores_web.py` lee `guardias_farmacia`. Tras TRAB-34-D hay que
  actualizar su lista antes de volver a usarlo.

## 7. Rollback

- Devuelve el esquema exacto de la 33:
  - elimina las tablas y funciones nuevas y el trigger de `festivos`;
  - restaura `festivos_local_con_farmacia` y `ambito` sin valor por defecto;
  - restaura la política de historial de la 31;
  - recrea `guardias_farmacia` vacía, como en la 31.
- **Falla cerrado, sin borrar nada:**
  - con guardias (`ROLLBACK_34_GUARDIAS_CON_DATOS`);
  - con festivos LOCAL sin farmacia (`ROLLBACK_34_FESTIVOS_LOCALES_SIN_FARMACIA`).

## 8. `desplegar_34.py`

Mismo patrón que `desplegar_33.py`: SQL igual al del commit (LF), SHA esperado, una transacción y nunca reintenta.

**7 precondiciones:**

1. 34 ausente;
2. 33 presente y `guardias_farmacia` presente y vacía;
3. roles;
4. privilegios mínimos;
5. flags solo PIO;
6. sin claims;
7. propietarios 2AX.

**Postcondiciones:**

- datos de facturas, Trabajadores y festivos sin cambios;
- privilegios de la web, ya sin `guardias_farmacia`;
- lectura y ACL de las tablas y funciones nuevas;
- estructura y RLS: índices parciales, `guardias_farmacia` retirada, check retirado, trigger de festivos, historial con
  `OTRA` y módulo y global intactos;
- propietario.

Ensayado completo con la imitación del `postgres` de Supabase. El segundo intento se revierte en las precondiciones y
el rollback funciona con la imitación.

## 9. Criterios de la web que no tocan el esquema

D3 (un festivo en el fin de semana de una guardia sustituye ese día) y D4 (TA3 no crea filas en `eventos_calendario`)
son reglas de cálculo de la web. La 34 no las impone ni las impide.
