# H6: marcas de pago de vencimientos y forma de pago por proveedor (migración 35). DISEÑO

Estado: **DISEÑO APROBADO** (2026-11-16). No hay migración, script ni test. Nada desplegado.

## 0. Decisiones de Pio (2026-11-16)

- **D1–D9 aprobadas tal como se proponen** en §3 y §4. Donde las secciones siguientes dicen `PROPUESTA`, queda
  decidido. En D1, el check admite `PIO` o `RITA`, y la barrera efectiva es `cf_configuracion`.
- **D8: AUTORIZACIÓN EXPRESA DE PIO (2026-11-16)** para nombrar el rol del sistema **solo** en
  `sql/migrations/35_*.sql` y su rollback. Tests, scripts y documentación no lo nombran; cualquier otro fichero
  requiere una autorización nueva. Se registra en REGLAS_CRITICAS al implementar la 35.
- **Orden de trabajo (2026-11-17):**
  1. Commit con código:
     - `TABLAS_PAGOS` en los postchecks de la noche y de las series 2BJ y 2BP (§6);
     - defectos de extracción directos a REVISION;
     - la tarea de Alliance en la puerta de tareas de los preflights;
     - `probar_acceso_cf_trabajadores_web.py` actualizado a la 34.
  2. Migración 35, solo local, con `desplegar_35` ensayado (§7, punto 2).

- **Origen:** petición de la web, propuesta `web/docs/propuesta_tablas_h6_pagos.sql` de la rama `origin/web/fase1`
  (commit 91ae084, «NO APLICAR»).
- **Excepción:** autorizada por Pio. Es la segunda escritura de la web en Supabase, después de Trabajadores.
- **Etiquetas:** lo que se afirma del esquema actual está `CONFIRMADO POR CÓDIGO` (migraciones de `sql/migrations/`,
  con fichero:línea). Lo demás es `PROPUESTA`.

## 1. Reglas que enmarcan el diseño

### 1.1 Lo que dicen hoy REGLAS_CRITICAS

Números de línea de `main` (1d450b1). En la copia de `origin/web/fase1` son la 424 y las 482–484.

- **Línea 427** («Trabajadores»): «Rol de escritura de la web limitado EXCLUSIVAMENTE a Trabajadores».
- **Líneas 501–503** («Capacidades no implementadas»): la web «hoy solo lee Supabase con `cf_lectura`; su única
  escritura prevista es el módulo de Trabajadores».

### 1.2 Lo que habría que cambiar al implementar

Al implementar H6 (no en este commit), esas dos frases pasan a decir:

> La web escribe en Trabajadores (`cf_trabajadores_web`) y **solo** en `vencimientos_marcas_pago` y
> `proveedores_forma_pago` (`cf_pagos_web`, H6).

Además habría que añadir a REGLAS_CRITICAS una sección «Pagos (H6)» con estas reglas:

- **Escritura de la web, solo en dos tablas.**
  - `cf_pagos_web` tiene `SELECT`, `INSERT` y `UPDATE` sobre las dos tablas y `SELECT` sobre su historial.
  - Nunca escribe en `facturas`, `facturas_vencimientos`, conciliación (`conciliaciones`, `conciliacion_detalles`,
    `conciliacion_albaranes_reservados`), albaranes ni ninguna otra tabla.
  - No tiene ningún privilegio sobre ellas, tampoco de lectura (§2.5).
- **Anulación en lugar de DELETE.** Nadie tiene `DELETE` ni `TRUNCATE`, y un trigger rechaza el borrado. Una fila
  anulada no se reactiva: se crea otra.
- **Autor e historial.**
  - El autor va por transacción, con `set local cf.autor`; las tablas no tienen columna de autor.
  - Sin autor, la escritura falla con `AUTOR_AUSENTE`.
  - El historial se escribe por trigger, solo por inserción, y es inmutable.
- **El sistema no usa las marcas.**
  - Ni la normalización, ni la conciliación, ni la persistencia, ni la noche leen estas tablas para decidir nada.
  - Las marcas no cambian ningún estado de factura, vencimiento ni conciliación.
- **Cuando haya banco, manda el banco.** La conciliación bancaria y la Norma 43 siguen `NO IMPLEMENTADAS`.
  - Cuando existan, el estado que salga del banco prevalece sobre la marca manual.
  - La marca no se anula ni se borra: queda como histórico.
  - Hoy no se reserva nada en el esquema (D6).
- **Farmacia.** Solo PIO, con la misma fuente que facturas (`cf_configuracion.farmacias_habilitadas`). No usa la
  excepción por módulo de Trabajadores (D1).

## 2. Esquema propuesto

Sigue las convenciones del módulo de Trabajadores (31, 33 y 34) para que la web y los postchecks traten igual los
dos módulos.

### 2.1 `vencimientos_marcas_pago`

Una marca de pago manual de un vencimiento. Como mucho una vigente (no anulada) por vencimiento.

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK, `gen_random_uuid()` |
| `farmacia` | text | not null; `PIO` o `RITA` en el check; además, habilitada en `cf_configuracion` y la de la factura (D1) |
| `factura_id` | uuid | not null; factura existente, **sin FK** (D7) |
| `vencimiento_orden` | integer | not null; `facturas_vencimientos.orden` de esa factura |
| `fecha_vencimiento` | date | copia que pone el trigger al marcar (D7) |
| `importe` | numeric(14,4) | copia que pone el trigger al marcar; no admite vencimientos sin importe (D7) |
| `fecha_pago` | date | not null; no posterior a hoy en Europe/Madrid (D3) |
| `forma` | text | `DOMICILIACION`, `TRANSFERENCIA`, `EFECTIVO` o `COMPENSACION_ABONO` |
| `origen` | text | `MANUAL` (por defecto) o `DOMICILIADOS` (D2) |
| `anulada` | boolean | not null, default false |
| `created_at`, `updated_at` | timestamptz | `now()` |

- **Checks:**
  - `origen = 'DOMICILIADOS'` exige `forma = 'DOMICILIACION'`;
  - `farmacia` en `PIO` o `RITA`.
- **Único parcial:** `(farmacia, factura_id, vencimiento_orden) WHERE NOT anulada`.
- **Trigger de validación** (security definer, `search_path` fijo, EXECUTE revocado). Al insertar comprueba:
  - que el vencimiento `(factura_id, orden)` existe;
  - que la factura es de esa farmacia y que la farmacia está habilitada;
  - que el vencimiento tiene fecha e importe, y los copia en la fila;
  - la fecha de pago (D3);
  - en `DOMICILIADOS`: fecha de pago = fecha de vencimiento, y vencimiento ya pasado.

### 2.2 `proveedores_forma_pago`

Forma de pago por CIF y farmacia. Como mucho una vigente por CIF. Si un CIF no tiene fila, la web lo trata como
`DOMICILIACION`.

| Columna | Tipo | Regla |
|---|---|---|
| `id` | uuid | PK |
| `farmacia` | text | igual que en 2.1 |
| `cif` | text | not null; comparable: mayúsculas, solo `A-Z0-9`, 5–20 caracteres (check `^[A-Z0-9]{5,20}$`) |
| `forma` | text | los mismos 4 valores |
| `anulada` | boolean | not null, default false |
| `created_at`, `updated_at` | timestamptz | `now()` |

- **Único parcial:** `(farmacia, cif) WHERE NOT anulada`.
- **Cambiar de forma:** se anula la fila vigente y se inserta la nueva en la misma transacción, con el mismo autor.
- **Volver a «por defecto»:** se anula la fila vigente.

### 2.3 `pagos_historial`

Historial propio del módulo; no reutiliza `trabajadores_historial`, cuya RLS y cuya lectura van por el módulo de
Trabajadores (`31_cf_trabajadores.sql:123-133`). Columnas alineadas con las de Trabajadores, para que la web use un
solo lector:

- `id` (bigint identity) y `tabla` (las dos de H6);
- `registro_id` y `farmacia`;
- `operacion`: `INSERT` o `UPDATE`;
- `antes`, `despues` y `autor` (1–60 caracteres);
- `created_at`.

Se escribe solo por el trigger (security definer). Solo admite inserciones: un trigger rechaza `UPDATE` y `DELETE`.

### 2.4 Solo anular

Una fila solo admite el `UPDATE` de `anulada` de false a true, junto con `updated_at`. Cualquier otro cambio falla
con `SOLO_ANULAR`; corregir es anular y crear otra fila.

La propuesta de la web ya lo plantea así. Es más estricto que Trabajadores, donde se edita. **PROPUESTA: aceptarlo**,
porque una marca de pago es un hecho y su historia tiene que ser legible.

### 2.5 Rol, RLS y privilegios

- **Rol `cf_pagos_web`**, creado como `cf_trabajadores_web` (`31_cf_trabajadores.sql:18-27`):
  - `login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls`, con límite de conexiones;
  - `statement_timeout` e `idle_in_transaction_session_timeout` de 60 s;
  - **sin contraseña en el repositorio** (§5).
- **Privilegios:**
  - `cf_pagos_web`: `SELECT`, `INSERT` y `UPDATE` en las dos tablas, y `SELECT` en `pagos_historial`. Ningún privilegio
    más: ni sobre facturas, vencimientos o conciliación, ni sobre secuencias, ni EXECUTE sobre las RPC.
  - **`cf_lectura`:** `SELECT` en las tres tablas (D4).
  - **Revocados:** los privilegios por defecto de Supabase sobre las tablas y la secuencia nuevas se quitan a `public`,
    `anon`, `authenticated` y al rol del sistema (D8).
- **RLS** en las tres tablas. Ven y escriben las filas solo `cf_pagos_web` (sus tres operaciones) y `cf_lectura`
  (lectura), y solo de farmacias habilitadas en `cf_configuracion`. La función de la política es security definer,
  como `cf_h6_farmacia_habilitada` en la propuesta.
- **Para validar las marcas sin dar permisos sobre las tablas de facturas:** la web no lee `facturas_vencimientos` con
  `cf_pagos_web`. La validación la hace el trigger, y la lista la sigue leyendo la web con `cf_lectura`, que ya lee
  `facturas_vencimientos` (`29_cf_rol_lectura.sql:33-35`).

## 3. Las 6 decisiones de la propuesta

**D1. Columna `farmacia` en las dos tablas.** **PROPUESTA: sí.**
- Sirve para la RLS y para la unicidad por farmacia.
- En las marcas, el trigger comprueba que coincide con la farmacia de la factura.
- La habilitación sale de `cf_configuracion.farmacias_habilitadas`, la misma fuente que facturas, y no de
  `cf_modulos_farmacias`, porque las marcas cuelgan de facturas y estas solo admiten PIO.
- Diferencia con la propuesta: el check admite `PIO` o `RITA`, como `facturas.farmacia`
  (`06_reestructurar_documentos_y_facturas.sql:123-124`), en lugar de solo `PIO`. La barrera efectiva es la
  configuración, que falla cerrado. Si algún día se habilitara RITA en facturas, no haría falta otra migración. Si Pio
  prefiere fijar `PIO` en el check, también vale; solo es más rígido.

**D2. Columna `origen` en las marcas (`MANUAL` / `DOMICILIADOS`).** **PROPUESTA: sí.**
- Sin ella, «domiciliado confirmado» no se distingue de una marca manual con forma `DOMICILIACION`.
- `DOMICILIADOS` exige forma `DOMICILIACION`, fecha de pago = fecha de vencimiento y vencimiento ya pasado (es lo que
  ya hace la propuesta).

**D3. Fecha de pago no posterior a hoy.** **PROPUESTA: sí, con «hoy» en `Europe/Madrid`:
`(now() at time zone 'Europe/Madrid')::date`.**
- `current_date` depende de la zona de la sesión. En Supabase es UTC: entre las 00:00 y la 01:00 o las 02:00 de
  España, «hoy» sería ayer y rechazaría un pago del día.
- La misma fecha vale para la regla de «vencimiento ya pasado» de `DOMICILIADOS`.

**D4. Lectura de `cf_lectura`.** **PROPUESTA: ampliar su lista cerrada con las tres tablas, `SELECT` solamente.**
- Es el patrón de la 31 con Trabajadores (`31_cf_trabajadores.sql:300-302`).
- La lista REAL de la web muestra las marcas, y los preflights y postchecks READ_ONLY pueden leerlas.
- `desplegar_35` comprueba que `cf_lectura` sigue sin escritura en `public`.

**D5. Credencial de `cf_pagos_web`.** **PROPUESTA: como `cf_trabajadores_web`.**
- El rol se crea con `LOGIN` y sin contraseña (no `NOLOGIN` como en la propuesta). Así las postcondiciones de
  `desplegar_35` comprueban los atributos definitivos.
- Pio fija la contraseña fuera del repositorio con SCRAM (§5).
- La web no la usa mientras H6 siga en FIXTURES.
- Prueba de acceso de Pio por el pooler antes de conectar la web, como la de Trabajadores (`ACCESO_OK`).

**D6. `PAGADO_BANCO` reservado.** **PROPUESTA: sí, sin columna ni lógica.** Cuando exista la conciliación bancaria:
- su resultado irá en sus propias tablas, escritas por el sistema y no por la web;
- la web mostrará el estado del banco por encima de la marca;
- la marca se conserva tal cual, como histórico; el sistema no la anula.

## 4. Decisiones nuevas que salen de la revisión

**D7. Identidad del vencimiento: sin FK a `facturas_vencimientos.id`.** **PROPUESTA: referenciar por
`(factura_id, orden)`, sin FK, con copia de fecha e importe.**

El `id` de un vencimiento no es estable. La persistencia vigente borra y vuelve a insertar todos los vencimientos de
la factura en cada persistencia o reproceso (`28_cf_persistencia_multifactura_ligera.sql:265-272`, igual en la 26 y
la 27). Con la FK de la propuesta:
- **sin cascade:** reprocesar una factura con un vencimiento marcado fallaría por la FK. La web bloquearía la cadena
  de facturas, lo que va contra «nunca en facturas ni vencimientos»;
- **con cascade:** el sistema borraría marcas en silencio, lo que va contra «anulación en lugar de DELETE»;
- **en los dos casos**, la FK añade triggers internos de integridad a `facturas_vencimientos`, que es una tabla de
  facturas. El postcheck 2AX lo vería como un cambio de esquema en esa tabla.

Con la referencia por `(factura_id, orden)`:
- la factura conserva su `id` en la persistencia (upsert por `(documento_id, proyeccion_clave)`, `28_…:241-264`);
- `orden` es único por factura (`06_…:260-261`);
- tampoco se pone FK a `facturas`: el trigger comprueba que existe;
- la copia de `fecha_vencimiento` e `importe` permite detectar una marca desfasada. Si un reproceso cambia la fecha o
  el importe de ese orden, la web muestra la marca «a revisar» y **nunca «pagado»** (falla cerrado);
- no se puede marcar un vencimiento sin importe (`VENCIMIENTO_SIN_IMPORTE`). El enriquecimiento de la 20 rellena
  importes nulos (`20_…:437-460`), y una marca sobre un importe desconocido no es comprobable.

**D8. Nombrar el rol del sistema en la 35 y su rollback.** Como en la 31 y la 34, la migración tiene que revocarle
los privilegios por defecto de Supabase sobre las tablas y la secuencia nuevas.
- **Hace falta AUTORIZACIÓN EXPRESA DE PIO**, limitada a `sql/migrations/35_*.sql` y su rollback.
- Tests, scripts y documentación no lo nombran.
- Sin esa autorización, la 35 no puede quitar esos privilegios y el diseño se para.

**D9. Proveedores sin CIF.** Según R9 (REGLAS_CRITICAS, «R9 `id_proveedor` tolerante»), hay proveedores sin CIF. Con
la clave por CIF, esos proveedores no pueden tener forma de pago propia y quedan en `DOMICILIACION` por defecto.
- **PROPUESTA: aceptarlo en H6.** La web los señala como «sin CIF: forma por defecto» y, si hace falta, se amplía en
  otra migración.
- **Normalización del CIF:** la hace la web antes de escribir (mayúsculas, solo `A-Z0-9`), con la misma regla que el
  motor. La BD solo comprueba el formato.

## 5. Contraseña de `cf_pagos_web`

- La fija Pio fuera del repositorio, en el editor SQL de Supabase, con `password_encryption = scram-sha-256`
  (regla de Pio: contraseñas de roles siempre con SCRAM).
- No aparece en el repositorio, en argumentos, en el chat ni en salidas.
- `desplegar_35` comprueba que el rol existe con los atributos esperados. No comprueba la contraseña ni la lee.
- Una comprobación READ_ONLY posterior confirma que el verificador es SCRAM sin leerlo: solo el prefijo, como en
  TRAB-D.

## 6. Postchecks de series y automatización

Las tres tablas se informan aparte y **no hacen fallar el veredicto**, como Trabajadores:

- **Constante nueva `TABLAS_PAGOS`** en `src/facturas/runtime_supabase/noche_automatica.py`, junto a
  `TABLAS_TRABAJADORES` (`noche_automatica.py:73-77`).
  - Se añade a `TABLAS_FUERA_DEL_SNAPSHOT`, para que el snapshot 2AX no las incluya.
  - Se lee aparte en su propia sesión READ_ONLY, con el patrón de `snapshot_trabajadores`.
  - Se informa en `postcheck["pagos"] = {"afecta_al_veredicto": False, ...}`.
- **Series 2BJ y 2BP** (`pruebas/auditoria_2bj/serie_normalizacion.py:285-301` y
  `pruebas/auditoria_2bp/serie_conciliacion.py:336-352`): importan `TABLAS_PAGOS` igual que `TABLAS_TRABAJADORES`.
  - Las excluyen de las filas que deciden el veredicto.
  - Las informan aparte en `postcheck["pagos"]`.
  - Sin este cambio, una marca de la web durante una tanda se vería como fila ajena (las marcas tienen `factura_id`,
    así que el snapshot las atribuiría al documento de esa factura) y la tanda se pararía.
- **Postchecks de despliegue futuros:** las tablas de pagos se comparan aparte; no son «filas de facturas».
- **Orden:** este cambio de código va en el mismo commit que la migración 35 (o antes) y **siempre antes de
  desplegarla**. Si se despliega antes, la primera marca de la web haría fallar la noche siguiente.

## 7. Plan de hitos

1. **Hecho (2026-11-16):** este diseño (1a4cd53) y las decisiones de Pio sobre D1–D9 (§0).
2. **H6, solo local:**
   - `sql/migrations/35_cf_pagos_marcas.sql` y su rollback. El rollback falla cerrado si hay marcas o formas de pago:
     no se pierde historia sin decisión de Pio;
   - `desplegar_35.py`, ensayado con la imitación del `postgres` de Supabase;
   - tests PostgreSQL 17 de cada regla:
     - autor, solo anular y sin DELETE;
     - único parcial, D3 en el cambio de día de Madrid, `DOMICILIADOS`;
     - farmacia no habilitada, vencimiento inexistente, sin importe o desfasado tras un reproceso;
     - privilegios y RLS;
     - una persistencia que reemplaza vencimientos y no falla por las marcas (D7);
   - `TABLAS_PAGOS` en la noche y las series (§6);
   - plantillas en `pg17_local.py`;
   - suite completa y revisor PASS.
3. **H6-D:** preflight READ_ONLY, captura pre, `desplegar_35` una vez con confirmación de Pio, captura post y postcheck
   por fila. Después, Pio fija la contraseña con SCRAM y hace la prueba de acceso.
4. **Web:** pasa de FIXTURES a escritura real solo después de H6-D y de la prueba de acceso.

## 8. Fuera de alcance

- Conciliación bancaria y Norma 43: siguen `NO IMPLEMENTADAS`.
- Cambios en facturas, vencimientos, conciliación o en su lógica de cálculo.
- Cashflow del sistema: no cambia. La web calcula el estado de cada vencimiento con las marcas, y el sistema no las
  lee.
