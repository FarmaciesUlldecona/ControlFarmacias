# TA4-2: guardias por asignar y estado de la guardia (migración 41), diseño

Estado (2026-11-26): **DECISIÓN DE PIO** sobre la petición de la web TA4-2. Migración 41 implementada
(`tests/facturas/runtime_supabase/test_integracion_pg17_41_trabajadores.py`), con su rollback y `desplegar_41.py`, y
**desplegada en producción en el 41-D** (2026-11-26, confirmación explícita de Pio; `CONFIRMADO EN PRODUCCIÓN`:
`desplegar_41` APLICADA y postcheck por fila sin diferencias; `desplegar_41` no se vuelve a ejecutar). Las
concreciones del §3 están aprobadas por Pio (2026-11-26).

Numeración (DECISIÓN DE PIO, 2026-11-26): TA4-2 = 41; «Actualizar ahora» pasa a 42.

## 1. Decisiones de Pio (2026-11-26)

| Id | Decisión |
|---|---|
| **TA4-2-1** | `guardias_semana` y `guardias_festivo`: `OTRA` **siempre sin persona**; PIO y RITA admiten la persona **nula** («por asignar»). Sustituye los checks de persona obligatoria |
| **TA4-2-2** | Columna `estado` en las dos: `PLANIFICADO` o `CONFIRMADO`, `NOT NULL`; **las filas existentes quedan `CONFIRMADO`**. `CONFIRMADO` sin persona se admite en PIO y RITA (se confirma la farmacia antes que la persona) |
| **TA4-2-3** | Se mantienen anular y nunca borrar y el autor por transacción; `cf_trabajadores_web` escribe las dos columnas y `cf_lectura` las lee; lista cerrada del 2BN si aplica |
| **TA4-2-4** | Rollback que **falla cerrado** si hay filas con persona nula o `PLANIFICADO` |

## 2. Migración 41

`sql/migrations/41_cf_trabajadores_guardias_estado.sql`, exige la 40 (`MIGRACION_40_AUSENTE`) y la 34
(`MIGRACION_34_AUSENTE`). Idempotente.

- **Checks retirados:** `guardias_semana_guardia_obligatoria` y `guardias_festivo_persona_obligatoria`. La petición
  los llama `guardias_*_personas_check`; en producción tienen los nombres de la 34 (`CONFIRMADO POR LECTURA`, READ_ONLY
  del 2026-11-26, `C:\ControlFarmacias\evidencias_41\guardias_pre_diseno.json`).
- **Se mantienen** `guardias_semana_otra_sin_personas` y `guardias_festivo_otra_sin_persona` (OTRA sin persona), las
  claves externas a `trabajadoras` (persona de esa farmacia), `guardias_semana_apoyo_distinto` y los triggers de la
  34. Esos triggers ya solo validan la persona cuando no es nula (`34_cf_trabajadores_guardias.sql:129-136` y
  `:156-158`, `CONFIRMADO POR CÓDIGO`): sin persona, no hay nada que validar; con persona, sigue siendo de la farmacia,
  sin anular y de alta.
- **`estado`:** `text not null default 'CONFIRMADO'` con el check `guardias_semana_estado` o `guardias_festivo_estado`
  (`PLANIFICADO`, `CONFIRMADO`). El default constante de `ADD COLUMN` no reescribe filas: las existentes quedan
  `CONFIRMADO` sin cambiar `updated_at` ni escribir historial.
- **Privilegios:** los de la 34 son de tabla (`SELECT, INSERT, UPDATE` para la web; `SELECT` para `cf_lectura`): cubren
  la columna nueva sin cambios. La 41 no crea tablas ni funciones ni concede o retira nada, así que **no nombra el rol
  del sistema**.
- **Historial:** `cf_trab_historial` guarda la fila entera, ahora con `estado`.
- **Lista cerrada del 2BN:** no incluye Trabajadores; no aplica.
- **Producción el 2026-11-26** (READ_ONLY): 67 guardias semanales y 22 de festivo, ninguna de PIO o RITA sin persona.

**Rollback** (`41_cf_trabajadores_guardias_estado.rollback.sql`): vuelve al esquema 40 exacto (retira `estado` y sus
checks y restaura los de persona obligatoria y los comentarios de la 34). Falla cerrado, sin cambiar nada, si alguna
fila de PIO o RITA, **anulada o no**, está por asignar (`ROLLBACK_41_GUARDIAS_POR_ASIGNAR`) o alguna está
`PLANIFICADO` (`ROLLBACK_41_GUARDIAS_PLANIFICADAS`): el esquema 40 no puede guardarlas sin perder información.

**`desplegar_41.py`:** patrón de `desplegar_34` y `desplegar_40`.

- 7 precondiciones:
  1. la 41 no está aplicada: sin `estado` y con los dos checks;
  2. la 40 y la 34 están aplicadas y `TRABAJADORES = {PIO, RITA}`;
  3. los roles existen;
  4. los privilegios mínimos de la 19;
  5. flags apagados y solo PIO;
  6. sin claims;
  7. propietarios 2AX.
- 5 postcondiciones:
  - **datos sin cambios:** conteos, facturas, configuración, módulos, historial de Trabajadores, filas de las guardias
    sin `estado` y su ACL;
  - **privilegios de la web,** con `SELECT`, `INSERT` y `UPDATE` de `estado` comprobados uno a uno;
  - **lectura:** `cf_lectura` lee `estado` y no escribe; sin privilegios de columna;
  - **estructura:** la columna, sus checks, todas las filas `CONFIRMADO`, los checks retirados ausentes y los de
    `OTRA` presentes, las políticas, los triggers y la RLS;
  - **propietario:** `postgres`.

## 3. Concreciones de la implementación (`DECISIÓN DE PIO`, 2026-11-26: aprobadas tal como se proponían)

1. **Default `CONFIRMADO` también para las filas nuevas.** La web actual da de alta sin `estado` y sus guardias son
   confirmadas: con el default sigue funcionando igual hasta que envíe `estado`. Alternativa: quitar el default tras
   rellenar las existentes, y la web tendría que enviar siempre `estado` (sus altas fallarían hasta adaptarla).
2. **Apoyo del sábado con la guardia por asignar:** se admite (el apoyo ya era opcional) y se valida igual. Si después
   se asigna como guardia la misma persona del apoyo, `guardias_semana_apoyo_distinto` lo rechaza.
3. **Sin reglas de transición:** `PLANIFICADO` ↔ `CONFIRMADO` en los dos sentidos, también en `OTRA` y en guardias
   anuladas; el cambio queda en el historial con su autor.
4. **El rollback cuenta también las anuladas** (por asignar o `PLANIFICADO`): devolverlas al esquema 40 cambiaría su
   contenido.
5. **Prueba de acceso de la web:** `probar_acceso_cf_trabajadores_web.py` no cambia. Tras el despliegue, Pio puede
   repetirla opcionalmente.
