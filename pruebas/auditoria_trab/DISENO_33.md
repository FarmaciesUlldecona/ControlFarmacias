# Migración 33: ajustes del módulo de Trabajadores (Hito TRAB-33)

Petición de la web con OK de Pio (2026-11-14). **Solo local**: migración, rollback, `desplegar_33.py` ensayado con la
imitación del `postgres` de Supabase y tests en PostgreSQL 17 local. El despliegue (TRAB-33-D) requiere preflight,
alcance explícito y confirmación de Pio.

Ficheros: `sql/migrations/33_cf_trabajadores_ajustes.sql` y su rollback, `pruebas/auditoria_trab/desplegar_33.py`,
`tests/facturas/runtime_supabase/test_integracion_pg17_33_trabajadores.py`. Requiere la 32 (estado productivo).

**AUTORIZACIÓN EXPRESA DE PIO (2026-11-14):** el rol del sistema se nombra solo en la 33 y en su rollback (como en la 31),
para retirarle los privilegios por defecto de Supabase sobre la tabla nueva y sobre la vista que recrea el rollback.

## 1. Eventos anulados

- `eventos_calendario.anulado boolean not null default false`. Los eventos existentes quedan no anulados.
- La restricción única `eventos_calendario_unico (trabajadora_id, fecha, franja)` pasa a ser un **índice único parcial**
  con el mismo nombre, `where not anulado`: puede haber varios eventos anulados en la misma franja y como máximo uno
  vigente.
- Anular = `update ... set anulado = true` (la web no tiene DELETE). El historial lo escribe el trigger existente
  (`cf_trab_historial`), con `antes`/`despues` y el autor.
- `cf_trab_comprobar_evento`: un evento anulado no exige estar dentro del alta, para poder anular eventos de una
  trabajadora que ya está de baja o anulada. Crear o cambiar un evento vigente fuera del alta sigue prohibido.
- `v_eventos_calendario_horas` **excluye los eventos anulados** (DECISIÓN DE PIO, 2026-11-14: un anulado nunca suma
  horas). Conserva las mismas columnas que en la 31. Para ver los anulados, la web lee `eventos_calendario`.

**ON CONFLICT de la web (obligatorio desde la 33):**

```sql
insert into public.eventos_calendario (...) values (...)
on conflict (trabajadora_id, fecha, franja) where not anulado do nothing
```

Con un índice parcial, PostgreSQL solo lo infiere si el `ON CONFLICT` repite su predicado. El `ON CONFLICT` anterior
(sin `where not anulado`) **falla** con «there is no unique or exclusion constraint matching the ON CONFLICT
specification». Esto afecta también al relleno del año: con el `ON CONFLICT` nuevo no pisa eventos vigentes y vuelve a
rellenar las franjas cuyo único evento está anulado.

## 2. Vacaciones del convenio

- `convenio_anual.vacaciones_dias_naturales integer` (0–366, nulo admitido) y `vacaciones_fuente text` (1–200).
  Restricción: si hay días, hay fuente.
- La migración pone **30** días, con fuente «Decision de Pio (2026-11-14), pendiente de texto publicado», en las filas
  **existentes** de 2026, 2027 y 2028 que no tengan valor. No crea filas (el resto de columnas del convenio no se
  conoce). Esas actualizaciones quedan en el historial con autor «Migracion 33». Los demás años, sin valor.

## 3. `trabajadoras_ajustes_anuales`

| Columna | Tipo |
|---|---|
| `id` | uuid, clave primaria |
| `trabajadora_id`, `farmacia` | clave externa compuesta a `trabajadoras (id, farmacia)` |
| `anio` | entero 2020–2100 |
| `vacaciones_dias_extra` | numeric(5,2) ≥ 0, default 0 |
| `nota` | texto opcional, máximo 200 caracteres (la web avisa de no anotar datos de salud) |
| `anulada` | boolean, default false |
| `created_at`, `updated_at` | timestamptz |

- Única por `(trabajadora_id, anio)` entre no anuladas (índice parcial `trabajadoras_ajustes_anuales_unico`).
- Triggers de la 31: farmacia habilitada en el módulo, `updated_at` e historial (autor obligatorio por transacción con
  `set local cf.autor`; sin autor, `AUTOR_AUSENTE`).
- RLS: lectura para `cf_trabajadores_web` y `cf_lectura`; inserción y actualización para `cf_trabajadores_web`; todo
  limitado a las farmacias del módulo (PIO y RITA).
- Privilegios: `SELECT`, `INSERT` y `UPDATE` para la web (sin `DELETE` ni `TRUNCATE`); `SELECT` para `cf_lectura`;
  ninguno para anon, authenticated, el rol del sistema ni PUBLIC.

## 4. Rollback

Devuelve el esquema exacto de la 32: elimina la tabla nueva (con sus datos), las columnas de vacaciones y `anulado`,
restaura la restricción única sobre todos los eventos, la función y la vista de la 31. **Falla cerrado** con
`ROLLBACK_33_EVENTOS_ANULADOS_DUPLICADOS` si hay eventos anulados que romperían la unicidad: no borra ningún evento.

## 5. `desplegar_33.py`

Mismo patrón que `desplegar_31.py`: SQL igual al del commit (LF) y SHA esperado; una transacción; 7 precondiciones
(33 ausente; 31 y 32 presentes con la unicidad de la 31; roles; privilegios mínimos; flags solo PIO; sin claims;
propietarios 2AX) y postcondiciones (datos de facturas sin cambios; privilegios de la web; lectura y ACL de la tabla
nueva; estructura, índices parciales y RLS; vacaciones 30 solo en 2026–2028; propietario). Ensayado completo con la
imitación del `postgres` de Supabase, segundo intento revertido en precondiciones y rollback con la imitación.
