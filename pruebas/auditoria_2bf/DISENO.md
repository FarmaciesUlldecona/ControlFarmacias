# Hito 2BF — Resolución de revisiones de albaranes con aprobación de Pio (diseño)

Estado: **IMPLEMENTADO EN LOCAL (2BF, 2026-10-28); migración 23 NO desplegada.** Solo local: sin
producción, sin Farmatic, sin push. Parte de `pruebas/auditoria_2bd/DISENO.md` (migración 22) y de la
sección «Hito 2BD-D, tanda RO» de `docs/contexto/ESTADO_ACTUAL.md`.

## 1. Problema

La 22 trata un cambio de `numero_albaran` o de `id_proveedor` (normalizado R9) de un mismo `IdContador`
como cambio de identidad: registra `REVISION CAMBIO_IDENTIDAD` en `albaranes_cambios` y **no** actualiza
el albarán (`22_cf_resincronizar_albaran`, `sql/migrations/22_cf_resincronizacion_albaranes.sql:174-191`).
No existe ningún camino para aplicar esa revisión aunque Pio la apruebe. Caso real: **279410**
(Supabase `08C16912`, `id_proveedor` `52`, CINFA; Farmatic `08C16912A`, `0002 `, `1.- SAFA`; informe V2
del 2026-10-28 en `C:\ControlFarmacias\evidencias_2bd_ro\informe_v2_postcheck.json`). Pio aprobó por
adelantado `id_proveedor` 52 → `0002` y `numero_albaran` 08C16912 → 08C16912A (ESTADO_ACTUAL, tanda RO).

Duplicados nocturnos: la 22 **ya** evita repetir una revisión idéntica, pero lo comprueba contra **todo**
el historial (`:176-182`, `:222-228`). Consecuencia con un camino de resolución: una revisión ya resuelta
que reaparece idéntica (p. ej. un cambio revertido y vuelto a hacer) quedaría silenciada para siempre.
La 23 limita la comprobación a revisiones **pendientes**.

## 2. Reglas (decisiones de Pio en el encargo 2BF)

- **A1 aprobación registrada en BD:** quién aprueba (`aprobado_por`, solo `Pio`), cuándo
  (`aprobado_at`), qué albarán (`farmacia`, `id_contador`), el cambio exacto aprobado (`cambio`: lista de
  `{campo, anterior, nuevo}`), la referencia de la aprobación y quién la registra (`registrado_por`,
  `registrado_at`). Append-only.
- **A2 aplicación solo con coincidencia exacta:** se aplica solo si el cambio aprobado es **el mismo
  conjunto** que el cambio de identidad que Farmatic muestra **ahora** para ese `IdContador`, y cada campo
  de ese cambio está registrado como revisión `CAMBIO_IDENTIDAD` **pendiente** (la resincronización lo
  detectó). Cualquier diferencia (un campo de más o de menos, otro valor, Farmatic cambiado otra vez,
  revisión no registrada) → `NO_APLICADA`, sin escrituras: el albarán **sigue en revisión**. Al aplicar
  se resuelven todas las revisiones de identidad pendientes del albarán (también las superadas, p. ej.
  un `08C16912B` intermedio que Farmatic ya no muestra).
  - «Mismo valor» usa la equivalencia que ya define el cambio de identidad en la 22: `numero_albaran` con
    `btrim`, `id_proveedor` con R9 (`'0002' == '0002 ' == '2'`). Sin ella, la aprobación de Pio (`0002`)
    nunca casaría con el literal de Farmatic (`0002 `). Fuera de esa equivalencia, nada se aproxima.
  - El valor escrito es el **literal de Farmatic** (`0002 `), como en toda la sincronización.
- **A3 nunca si está reservado:** si el albarán tiene fila en `conciliacion_albaranes_reservados` (R15),
  `NO_APLICADA RESERVADO:<factura>`. La reserva se relee en la transacción con la tabla bloqueada en modo
  `SHARE` (ninguna conciliación puede reservarlo mientras se aplica). También `NO_APLICADA` si tiene una
  revisión `AUSENTE_EN_FARMATIC` abierta.
- **A4 con historial:** la aplicación deja una fila en `albaranes_aprobaciones_aplicadas` (valores
  anteriores y nuevos, revisiones resueltas, ejecución). Una aprobación se aplica como máximo una vez
  (clave primaria); repetir devuelve `YA_APLICADA` sin escribir.
- **A5 solo lo aprobado:** se actualizan solo los campos de identidad aprobados. Los demás (nombre del
  proveedor, importes, fecha, recepción) los actualiza la **siguiente resincronización** con las reglas de
  la 22 (historial `ACTUALIZADO`, o `REVISION RESERVADO` si se reservara entretanto). Para 279410:
  `proveedor` CINFA → `1.- SAFA` e `id_recepcion` → 50781 la noche siguiente.
- **A6 resync sin duplicados:** una revisión idéntica (mismo campo, anterior, nuevo y motivo) **pendiente**
  no se registra de nuevo. Pendiente = `REVISION` (no de presencia) que ninguna aplicación ha resuelto y
  cuyo campo no se ha actualizado después (`ACTUALIZADO` posterior del mismo albarán y campo).

Solo es aprobable el motivo `CAMBIO_IDENTIDAD`. `RESERVADO:<factura>` no lo es por A3 (se resuelve en
conciliación) y `AUSENTE_EN_FARMATIC` tampoco (nunca se borra un albarán).

## 3. Migración 23 (`sql/migrations/23_cf_aprobaciones_albaranes.sql` + rollback)

Generada por `pruebas/auditoria_2bf/generar_migracion_23.py` desde el texto exacto de la 22. Requiere la
22 (`MIGRACION_22_AUSENTE`). No modifica filas existentes; idempotente.

- `albaranes_aprobaciones` (append-only, RLS, solo `SELECT` para `service_role`): `farmacia`,
  `id_contador`, `motivo` (`CAMBIO_IDENTIDAD`), `cambio` jsonb (ordenado por campo), `aprobado_por`
  (check `= 'Pio'`), `aprobado_at`, `referencia`, `registrado_por`, `registrado_at`. Única por
  `(farmacia, id_contador, cambio)`.
- `albaranes_aprobaciones_aplicadas` (append-only, RLS, solo `SELECT`): `aprobacion_id` (PK, FK),
  `farmacia`, `id_contador`, `aplicada_at`, `ejecucion_id`, `valores_anteriores`, `valores_nuevos`,
  `revisiones_resueltas` (ids de `albaranes_cambios`).
- `cf_registrar_aprobacion_albaran(farmacia, id_contador, cambio, aprobado_por, aprobado_at, referencia,
  registrado_por)` — SECURITY DEFINER, solo `service_role`. Valida farmacia habilitada, albarán existente,
  campos de identidad sin repetir, `anterior` = valor actual de Supabase y `nuevo` distinto. Idempotente
  (`YA_REGISTRADA`). No toca `albaranes`.
- `cf_aplicar_aprobacion_albaran(aprobacion_id, valores, ejecucion_id)` — SECURITY DEFINER, solo
  `service_role`. `valores` = cabecera actual de Farmatic (mismo formato que `cf_resincronizar_albaran`).
  Bloquea reservas (`SHARE`) y la fila del albarán; aplica A2–A4. Si la nueva identidad ya la tiene otro
  albarán (`albaranes_numero_unico` en la referencia local) → error `IDENTIDAD_OCUPADA` y no cambia nada.
- `cf_resincronizar_albaran` = 22 con la comprobación de duplicados limitada a pendientes (A6), vía el
  auxiliar `cf_revision_albaran_pendiente(id)` (solo propietario).
- `service_role` sigue sin `UPDATE` directo sobre `albaranes`.
- **Rollback** = esquema 22 exacto (texto de la 22 para `cf_resincronizar_albaran`; borra las dos tablas
  nuevas, sus funciones y las RPC). Se pierden aprobaciones y aplicaciones; los valores ya aplicados en
  `albaranes` se quedan (la 22 los ve como estado normal).

## 4. Script one-shot (`pruebas/auditoria_2bf/aplicar_aprobacion.py`)

Patrón 2BD (`carga_historica.py`): Farmatic solo con `ControlFarmaciasRO` (lectura por `IdContador`),
Supabase con `service_role`, salidas fuera del repositorio, sin reintentos.

1. `informe <id_contador> <salida.json>` — sin escritura: fila de Supabase, revisiones pendientes,
   aprobaciones, reserva, cabecera actual de Farmatic y previsión (`APLICABLE` o el motivo).
2. `registrar <aprobacion.json> <salida.json>` — registra la aprobación (solo la tabla de aprobaciones).
   Para 279410: `pruebas/auditoria_2bf/aprobacion_279410.json`.
3. `aplicar <aprobacion_id> <salida.json>` — **una** aprobación: exige configuración `f|f|f|{PIO}`, la 23 y
   que no exista el guard `aplicar_aprobacion_<id>.guard` (se crea en exclusiva antes de escribir y no se
   borra); relee Farmatic y llama una vez a `cf_aplicar_aprobacion_albaran`.

`registrar` y `aplicar` escriben en Supabase: solo con la 23 desplegada y confirmación expresa de Pio.

## 5. Tarea nocturna (copias del repositorio)

La V2 está activada en la tarea por Pio. Acción real (exportación del 2026-10-28 20:05):
`C:\Windows\System32\cmd.exe /c "set CONTROLFARMACIAS_ALBARANES_V2=1&&C:\ControlFarmacias\Programa\ejecutar_sincronizacion.bat"`
(sin espacio antes de `&&`: el valor es exactamente `1`, que es lo que exige
`resincronizacion_albaranes.activada()`). Copias byte a byte de las exportaciones reales en
`pruebas/auditoria_2bf/backup_tasks/` (ver su `README.md`). `pruebas/auditoria_2ae/backup_tasks/` sigue
siendo el inventario **original** del 2AE (base de `rollback_tasks.ps1`) y no se modifica. Los scripts de
2AH/2AI identifican la tarea por `Command = ejecutar_sincronizacion.bat`: con la acción actual no la
encuentran y fallan cerrado (`Tarea no identificada de forma unica`). Son históricos; no se reutilizan sin
adaptarlos.

## 6. Plan 2BF-D (producción; cada paso con confirmación de Pio)

**Despliegue:** `pruebas/auditoria_2bf/desplegar_23.py <commit> <sha256_lf> <salida.json>` (patrón
`desplegar_22.py`): SHA de la 23 contra el commit; 9 precondiciones en la misma transacción (23 ausente y
`cf_resincronizar_albaran` con el texto de la 22; 22 presente e intacta; privilegios 19; flags `f|f|f|{PIO}`;
sin locks; reservas = líneas vigentes; propietarios `postgres`); aplicación; postcondiciones (0 aprobaciones,
0 aplicadas, `albaranes_cambios` sin cambios, RPC presentes, resync con la comprobación de pendientes,
`service_role` sin `UPDATE` en `albaranes` ni escritura en aprobaciones). Ensayado completo en local
(`test_ensayo_completo_despliegue_23_y_segundo_intento_revierte`: aplica; el segundo intento falla solo en
la precondición 1 y revierte sin cambios). SQL de precondiciones comprobado de solo lectura.

Identidades: **Usuari** = sesión Windows `MOSTRADOR\Usuari`, sin Farmatic, con conexión directa a la base
(`CONTROLFARMACIAS_SUPABASE_DB_URL`, propietario `postgres`). **RO** = sesión `MOSTRADOR\ControlFarmaciasRO`
(Farmatic certificado READ_ONLY; el hook de Claude Code exige esta identidad para Farmatic) con el
`service_role` del `.env`. **Las escrituras las ejecuta Pio en terminal.**

| Paso | Qué | Identidad | Escribe | Ejecuta |
|---|---|---|---|---|
| 0 | Puerta: commit local, suites en verde, `sha256_lf` de la 23 | Usuari | no | Claude |
| 1 | Preflight READ_ONLY: SQL de precondiciones de `desplegar_23.py` en `begin read only … rollback` (9 × `t`); captura pre de esquema, privilegios y huellas | Usuari (DB URL, READ ONLY) | no | Claude, con autorización de Pio |
| 2 | `desplegar_23.py <commit> <sha> <salida.json>` | Usuari (DB URL) | **sí** (DDL, una transacción) | **Pio** |
| 3 | Postcheck READ_ONLY con el criterio 2AX: solo cambian los objetos de la 23, iguales a la referencia local; fuera de alcance idénticos; huellas de datos idénticas | Usuari (DB URL, READ ONLY) | no | Claude |
| 4 | `aplicar_aprobacion.py informe 279410 <salida>`: pendientes `08C16912→08C16912A` y `52→0002 `, sin reserva | RO | no | Pio, o Claude en VS Code abierto como RO |
| 5 | `aplicar_aprobacion.py registrar pruebas/auditoria_2bf/aprobacion_279410.json <salida>` | RO (`registrado_por` = usuario Windows de la sesión) | **sí** (1 fila en `albaranes_aprobaciones`) | **Pio** |
| 6 | `informe 279410`: previsión `APLICABLE` para esa aprobación | RO | no | Pio, o Claude (RO) |
| 7 | `aplicar_aprobacion.py aplicar <aprobacion_id> <salida>` (una vez; guard propio) | RO (relee Farmatic) | **sí** (279410 + 1 fila en aplicadas) | **Pio** |
| 8 | `informe 279410` (`YA_APLICADA`, sin pendientes) y postcheck READ_ONLY: solo cambian `numero_albaran`, `id_proveedor` y `fecha_actualizacion` de 279410; 1 aprobación y 1 aplicación; reservas, historial y resto idénticos | RO / Usuari | no | Claude |
| 9 | Noche V2 (tarea programada, principal RO): `proveedor` e `id_recepcion` de 279410 con historial `ACTUALIZADO`, sin revisiones nuevas; revisar log y código de salida | tarea (RO) | sí (automática) | Task Scheduler |
| 10 | Simulación sin claim de 08007972 (08C16912A debería casar por número) | Usuari (READ_ONLY) | no | Claude |

`PENDIENTE` antes del paso 1: herramientas READ_ONLY del 2BF-D para la captura y el postcheck de los pasos
1, 3 y 8 (adaptar `pruebas/auditoria_2bd_d/preflight_readonly.py` con alcance local 22 ↔ 23, y
`pruebas/auditoria_2bd_ro/postcheck_readonly.py`). Rollback de la 23: solo con confirmación de Pio (Usuari,
`23_cf_aprobaciones_albaranes.rollback.sql`); conserva los valores ya aplicados en `albaranes`.

La tarea nocturna funciona igual con la 22 o con la 23 (el código Python no cambia).

## 7. Fuera de alcance

Desplegar la 23 (es el 2BF-D); aprobar otros motivos; anular aprobaciones; conciliar; tocar Farmatic, flags o tareas.
