# Hito 2BD — Resincronización de albaranes modificados en Farmatic (diseño)

Estado: **IMPLEMENTADO EN LOCAL (2BD, 2026-10-22); migración 22 NO desplegada; resincronización
desactivada hasta el despliegue** (apartado 6). Origen: propuesta Redactado el 2026-10-22 solo con lectura de código y de la
documentación exportada de Farmatic. **Revisión 2 (2026-10-22):** ajustada con las comprobaciones
READ_ONLY del apartado 3 (resultados en el apartado 4) y las decisiones de Pio: sin señal `RecepAux`,
ventana de 180 días, carga inicial desde 2026-04-01 y albarán desaparecido → revisión.

## 1. Diagnóstico

### 1.1 Sincronización actual (`CONFIRMADO POR CÓDIGO`, HEAD `e9bab76`)

- Entrada nocturna: `ejecutar_sincronizacion.bat:10` → `python -m src.sincronizar_albaranes`
  (tarea «Sincronización ControlFarmacias», 21:30). El log registra
  `Principal Windows efectivo: ControlFarmaciasRO` y `Certificacion Farmatic READ_ONLY superada |
  Identidad SQL: MOSTRADOR\ControlFarmaciasRO` (p. ej. `logs/automatizacion_albaranes.log`, noche del
  18/10). Supabase se escribe con la clave del `.env` (`service_role`).
- Marca de agua: `obtener_ultimo_id_contador` (`src/supabase_client/guardar_albaranes.py:8-29`) = máximo
  `id_contador` de PIO en Supabase.
- Lectura: `obtener_nuevos_albaranes` (`src/database/leer_albaranes.py:38-85`):
  `dbo.Albaran a LEFT JOIN dbo.Proveedor p ON a.IdProveedor = p.IDPROVEEDOR WHERE a.IdContador > ?`
  (línea 61). **Solo albaranes nuevos.** El proveedor sale de `Albaran.IdProveedor` (no de la recepción).
- Escritura: `guardar_albaran` (`guardar_albaranes.py:32-62`) hace `insert`; el duplicado (`23505`)
  se ignora y `sincronizar_albaranes.py:102-110` solo lo registra en el log. **Nunca actualiza.**
- Campos guardados (`sincronizar_albaranes.py:24-36`): `farmacia`, `id_contador`, `id_proveedor`
  (literal), `proveedor` (`FIS_NOMBRE`), `numero_albaran` (`IdAlbaran`), `fecha`, `importe_pvp`,
  `importe_puc`, `descuento` (`Dto`), `estado='PENDIENTE'`, `observaciones=null`.
- Privilegios (migración 19): `service_role` solo tiene `SELECT, INSERT` sobre `public.albaranes`.
  **Cualquier actualización necesita una RPC SECURITY DEFINER nueva (migración 22).**
- Existe `obtener_albaranes_desde_fecha` (`leer_albaranes.py:88-…`, `WHERE a.Fecha >= ?`) para la
  carga histórica; no la usa ninguna tarea.

### 1.2 Tablas de Farmatic relevantes (`docs/exportaciones/diccionario_farmatic.xlsx`, 2026-07-23)

| Tabla | Clave | Columnas útiles |
|---|---|---|
| `Albaran` | (`IdProveedor`, `IdAlbaran`) | `IdContador`, `Fecha`, `ImportePVP`, `ImportePUC`, `Dto`, `Estado`, `Tipo`. **Sin fecha de modificación.** |
| `AlbaranRecep` | (`IdProveedor`, `IdAlbaran`, `IdRecepcion`) | Enlaza albarán ↔ recepción (FK a `Albaran` y a `Recep`). |
| `Recep` | `IdRecepcion` | `Fecha`, `Hora`, `XProv_IdProveedor` (proveedor **de la recepción**), `Actualizado`. |
| `RecepAux` | `IdRecepcion` | **`UltimaModificacion`** (datetime, admite NULL), `Maquina`. |
| `LineaAlbaran` | (`IdRecepcion`, `IdNLinea`, `IdAlbaran`) | Líneas: `ImportePuc`, `ImportePvp`, **`Modificada`** (bit), `PucModificado`, `PvpModificado`, `Baja`. |
| `LineaRecepAux` | `IdNLinea` | **`PUCOld`**, `PVPOld` (por línea). |
| `ChgPuc` | `IdCont` | Histórico de cambios de PUC de **artículo** (`PucOLd`/`PucNew`, `FechaHora`, `IdProveedor`). |

Corrección a la premisa del encargo: `RecepAux` solo aporta `UltimaModificacion` (por **recepción**,
no por albarán); `Modificada` y `PUCOld` están en tablas de **líneas** (`LineaAlbaran`,
`LineaRecepAux`). No existe en el material exportado un `docs/exportaciones/analisis_tablas` para
estas tablas (solo `Albaran.md`).

Cadena para relacionar un albarán con su última modificación:
`Albaran (IdProveedor, IdAlbaran)` → `AlbaranRecep` → `Recep.IdRecepcion` → `RecepAux.UltimaModificacion`.
El enlace **debe hacerse por `Albaran.IdProveedor` + `IdAlbaran`**, nunca por `Recep.XProv_IdProveedor`
(ver riesgo e).

**`RecepAux.UltimaModificacion` no es fiable y no se usa** (`CONFIRMADO POR LECTURA READ_ONLY`, 2BD):
la recepción de 08C20268 conserva `2026-06-25 19:08` tras la corrección del 2026-10-21; en 180 días,
4.662 recepciones la tienen el mismo día de la recepción, 24 en días posteriores y 429 no tienen fila en
`RecepAux`. Registra el cierre de la recepción, no las correcciones posteriores de la cabecera.

## 2. Propuesta

### a) Albaranes modificados

**Fuente de verdad:** los valores actuales de la cabecera `dbo.Albaran` (los mismos campos que hoy).
El cambio se decide siempre comparando valores; no hay señal de modificación en Farmatic (`RecepAux`
descartada, apartado 1.2) ni se usan las líneas.

**Candidatos (unión):**
1. Ventana por fecha: `Albaran.Fecha >= hoy − 180 días` (**decidido**). Motivo: el caso real
   (08C20268, fecha 2026-06-25, corregido el 2026-10-21) tenía **118 días**. Volumen medido (2BD):
   **5.130 albaranes** (~900/mes), una sola SELECT por noche.
2. Albaranes en la ventana ±15 días de las facturas `PENDIENTE_CONCILIAR` o `REVISION_CONCILIACION`
   de Supabase (conjunto pequeño; cubre facturas antiguas fuera de los 180 días).

**Comparación** por `(farmacia, id_contador)` frente a `Supabase.albaranes`. `id_proveedor` se compara
**normalizado** (`_id_proveedor_comparable`): Supabase guarda formatos mezclados (`'2'` en 2.217 filas y
`'0002 '` en 1.044 para SAFA, volcado 2BC); una comparación literal daría miles de falsos cambios de
identidad.

| Situación | Acción |
|---|---|
| Igual | nada |
| Cambia `importe_puc`, `importe_pvp`, `descuento` o `fecha` | ver reserva |
| Cambia `numero_albaran` o `id_proveedor` (normalizado) del mismo `IdContador` | **REVISIÓN** (cambio de identidad), no actualizar |
| `IdContador` de Supabase dentro de la ventana que ya no existe en Farmatic | **REVISIÓN** `AUSENTE_EN_FARMATIC`, **nunca borrar** (ver abajo) |
| Cambia solo `proveedor` (`FIS_NOMBRE`) | **implementado como campo de valor** (actualizar, o revisión si está reservado): la conciliación usa el nombre cuando falta el id de Farmatic |

**Albarán desaparecido de Farmatic.** Se detecta comparando los `id_contador` de Supabase con fecha
dentro de la ventana frente a los leídos de Farmatic (`IdContador` es único y no se reasigna, 2BD).
Nunca se borra ni se modifica la fila: se registra `REVISION` con motivo `AUSENTE_EN_FARMATIC` (y la
factura que lo reserva, si la hay). Se registra una sola vez por albarán mientras siga ausente
(idempotente). Caso previsto: si Pio anula en Farmatic `Q039921/2026` (280004, 3,16), cuya línea
VIDESIL ya está sumada a mano en la cabecera de 08C20268 (504,02), 280004 queda en Supabase marcado
para revisión. **Decidido por Pio (2BD):** un albarán con revisión `AUSENTE_EN_FARMATIC` abierta queda **fuera del
casado**: la conciliación lo excluye de los candidatos y `cf_persistir_conciliacion` lo rechaza
(`ALBARAN_AUSENTE_EN_FARMATIC`). Si reaparece en Farmatic, la revisión se cierra (`REVISION_CERRADA`).

**Reserva (R15):**
- **No reservado** (`conciliacion_albaranes_reservados` sin fila) → actualizar + historial.
- **Reservado por una conciliación vigente** → **no actualizar**; historial con estado `REVISION` y
  aviso en el log/informe con la factura afectada. Pio decide (p. ej. reintento de conciliación tras
  revisar).

**Supabase (migración 22, propuesta):**
- Tabla `albaranes_cambios` (append-only): `farmacia`, `id_contador`, `detectado_at`, `origen`
  (`RESYNC_VENTANA` | `RESYNC_FACTURA` | `CARGA_HISTORICA`), `campo`, `valor_anterior`,
  `valor_nuevo`, `accion` (`ACTUALIZADO` | `REVISION`), `motivo` (`RESERVADO:<factura>` |
  `CAMBIO_IDENTIDAD` | `AUSENTE_EN_FARMATIC`), `ejecucion_id`. RLS, solo `SELECT` para `service_role`.
- RPC de registro de `AUSENTE_EN_FARMATIC` (o la misma RPC con `p_valores = null`): solo escribe el
  historial; nunca `DELETE` ni `UPDATE` de `albaranes`.
- RPC `cf_resincronizar_albaran(p_farmacia, p_id_contador, p_valores jsonb, p_origen, p_ejecucion)`,
  SECURITY DEFINER, solo `service_role`: bloquea la fila (`for update`), relee la reserva **dentro de
  la transacción** (no confía en el cliente), compara, actualiza `albaranes` (+ `fecha_actualizacion`)
  o solo registra `REVISION`, y escribe el historial. Idempotente: si los valores ya coinciden, no hace
  nada.
- `service_role` sigue sin `UPDATE` directo sobre `albaranes`.

**Efecto en conciliación:** una factura no conciliada vuelve a evaluarse con los valores nuevos
(clave idempotente distinta, comprobado en 2AW: «albarán nuevo y espera cumplida reevalúan con clave
distinta»). No se lanza ninguna conciliación automáticamente; los flags no cambian.

### b) Carga única anterior a 2026-06-01 («abril y mayo»)

- Motivo (2AY): facturas de mayo sin cobertura de albaranes en Supabase. El albarán más antiguo en
  Supabase es del 2026-06-01 (`id_contador` 276412, volcado 2BC).
- Script one-shot (patrón 2AT/2AZ: preflight READ_ONLY, snapshot, una ejecución, postcheck), leyendo
  con `obtener_albaranes_desde_fecha`-like acotado: `Albaran.Fecha` en `[2026-04-01, 2026-06-01)`
  (**decidido**). Volumen: 1.273 albaranes medidos desde el 2026-04-15; abril completo no medido
  (estimado ~1.700 en total).
- Reglas: si el `IdContador` no existe → `insert` (vía el `INSERT` actual o la RPC); si existe → mismas
  reglas que a). Historial con origen `CARGA_HISTORICA`.
- Comprobación previa: que ningún `IdContador` de ese rango esté ya en Supabase con otro
  número/proveedor (si lo hay → revisión).

### c) Encaje en la tarea nocturna e identidades

- Mismo proceso `src.sincronizar_albaranes`, **después** de insertar los nuevos: 1) nuevos (como hoy),
  2) resincronización de modificados. Un fallo en 2) no deshace 1); se registra y el código de salida
  distingue «nuevos OK, resync con errores».
- Farmatic: solo `ControlFarmaciasRO` (`obtener_conexion()` con `ApplicationIntent=ReadOnly`,
  `db_datareader`, consultas `SELECT` validadas). Las nuevas SELECT pasan por los mismos wrappers.
  Ningún cambio en Farmatic.
- Supabase: `service_role` del `.env`, únicamente `INSERT` (nuevos) y la RPC nueva.
- Registro de ejecución (resumen: leídos, iguales, actualizados, revisiones) en Supabase, a decidir.
  No hay marca de agua: cada noche se recorre la ventana completa.
- Despliegue: migración 22 → código → primera noche vigilada. Primero una ejecución manual en
  **modo informe** (detecta y lista cambios, no escribe) para que Pio revise el volumen.

### d) Caso de prueba: 08C20268 (IdContador 280005)

- Estado conocido: Supabase PUC 500,86 (`fecha_actualizacion` 2026-07-25), sin reserva; Farmatic
  corregido por Pio el 2026-10-21 a 504,02 (faltaba VIDESIL 50000UI, 3,03 de base). Factura
  08007969: hoy DIFERENCIA 504,09 en simulación.
- Comprobado en 2BD: la corrección cambió **solo la cabecera** (`Albaran.ImportePUC` 504,02); las 46
  líneas de 08C20268 suman 500,86 y la línea VIDESIL 50.000 UI (3,16) sigue en `Q039921/2026`
  (280004), en la misma recepción 50898. 280004 está en Supabase (PUC 3,16, sin reserva ni detalle).
  Banco 2AY con el volcado 2BC: con 280005 = 504,02, 08007969 pasa a **CONCILIADA, diferencia 0,07**
  (128 casados) y es la única factura que cambia; ninguna línea del banco casa 280004, ni antes ni
  después (riesgo de doble cómputo hoy nulo, pero latente: 280004 es `INTERNO` y puede casar por PUC).
- Test local (PostgreSQL 17 + Farmatic simulado): Supabase 500,86, Farmatic 504,02, sin reserva →
  `ACTUALIZADO`, historial `importe_puc 500.86 → 504.02`; simulación de 08007969 → diferencia 0,07
  (≤ tolerancia R11) ⇒ CONCILIADA prevista.
- Variante con reserva de otra factura → `REVISION`, sin actualizar.
- Variante de identidad (mismo `IdContador`, otro número) → `REVISION`.
- Validado en 2BD: 280005 conserva `IdContador`, `IdProveedor` (`0002`) e `IdAlbaran`;
  `ImportePVP` sin cambios (738,96); `RecepAux.UltimaModificacion` **no** cambió.

### e) Riesgo: ~250 albaranes con recepción a nombre de otro proveedor

- Es decir, `Recep.XProv_IdProveedor ≠ Albaran.IdProveedor` (p. ej. recepciones agrupadas o
  proveedor de la recepción distinto del de facturación).
- Mitigación: el proveedor del albarán **siempre** sale de `Albaran.IdProveedor` (como hoy).
  **Decisión de Pio (2BD):** la sincronización trae además la recepción de cada albarán
  (`albaranes.id_recepcion`), enlazada por `AlbaranRecep (IdProveedor, IdAlbaran)` **del albarán**;
  nunca se lee `Recep.XProv_IdProveedor`. Es un metadato: no interviene en la conciliación.
  Nunca se actualiza `id_proveedor` desde la recepción; un cambio de `id_proveedor` en `Albaran` es
  `REVISION`.
- Recuento real (2BD): 793 enlaces en todo el histórico (0001→0002: 235; 0101→0002: 225; 0003→0002:
  103) y **44 en 180 días**. Reservas no comprobadas (ya no afecta al diseño).

### f) Patrón medido: línea PDF = albarán SAFA + albarán interno `Q…` de la misma recepción

Solo medición (2BD, banco 2AY, motor de `src`, volcado 2BC, recepciones de Farmatic). **No cambia
reglas.** De 220 líneas PDF sin casar, **12** (7 facturas, todas Alliance/SAFA `0002`, 2.407,29 €)
igualan (±0,05) la suma de los **dos** albaranes de una misma recepción: el de número exacto y un
`Q0400xx/2026` interno (130,96 € en total, de 2,78 a 23,10). Ninguno está reservado ni casado. Es el
mismo patrón que 08C20268, que Pio corrigió sumando a mano en la cabecera (por eso ya no aparece). Si
se corrigieran igual, cada `Q…` quedaría como en 280004: duplicado latente que casa por PUC. Opciones
para un hito posterior: casado 1:N dentro de una recepción con número exacto, o anular el `Q…` en
Farmatic (→ `AUSENTE_EN_FARMATIC`). **Decisión de Pio (2BD): hito 2BE (R17), NO ahora.**

## 3. Validaciones READ_ONLY previas a implementar (con `ControlFarmaciasRO`)

1. Albarán 280005: valores actuales en `Albaran`, `AlbaranRecep`, `RecepAux.UltimaModificacion`,
   `LineaAlbaran` (`Modificada`, línea VIDESIL).
2. Distribución de `RecepAux.UltimaModificacion` (NULL, frente a `Recep.Fecha`) para saber si es una
   señal fiable.
3. Volumen de la ventana de 180 días y número de diferencias actuales Supabase ↔ Farmatic (modo informe).
4. Recuento de `Recep.XProv_IdProveedor ≠ Albaran.IdProveedor`.
5. Si `IdContador` es estable ante correcciones (mismo albarán, mismo contador).

## 4. Resultados de las validaciones (2BD, 2026-10-22, `CONFIRMADO POR LECTURA READ_ONLY`)

Evidencias fuera del repositorio en `C:\ControlFarmacias\evidencias_2bd\` (SHA-256 en `SHA256SUMS.txt`):
`farmatic_readonly.json` (comprobaciones 1–5), `farmatic_recepciones.json` (albarán → recepción desde
2026-04-15) y `analisis_2bd.json` (análisis sin conexión sobre `evidencias_2bc\reservas_post.json`,
volcado READ_ONLY de Supabase de 2026-10-22 16:15:56 UTC; sin conexión nueva a Supabase).

1. 280005: ver d). Cabecera 504,02; líneas 500,86; VIDESIL 50.000 UI en `Q039921/2026` (280004).
2. `RecepAux.UltimaModificacion`: no fiable; descartada (apartado 1.2).
3. Ventana de 180 días: 5.130 albaranes; 120 días: 3.454. Diferencias Supabase ↔ Farmatic no medidas.
4. Recepción de otro proveedor: 793 en total, 44 en 180 días (ver e).
5. `IdContador`: único en los 54.033 albaranes, sin nulos, no se reasigna al corregir. Hay altas tardías
   con contador nuevo y fecha antigua (p. ej. 08B96275, 05/06 → 293646): las recoge la sincronización
   actual de nuevos.

## 5. Fuera de alcance

Modificar Farmatic; borrar filas de Supabase; tocar conciliaciones existentes o reservas; conciliar
automáticamente; activar flags.

## 6. Implementación (2BD, 2026-10-22; `CONFIRMADO POR TEST` en PostgreSQL 17 local)

Decisiones de Pio aplicadas: `AUSENTE_EN_FARMATIC` → revisión y fuera del casado; la sincronización trae
la recepción (proveedor del albarán); patrón exacto + `Q…` → hito 2BE (R17), no ahora; Pio revertirá
08C20268 a 500,86 en Farmatic, así que el test de modificación usa un albarán sintético (`08Z90001`,
500,86 → 504,02).

- **Migración 22** `sql/migrations/22_cf_resincronizacion_albaranes.sql` (+ rollback), generada por
  `pruebas/auditoria_2bd/generar_migracion_22.py` desde el texto exacto de la 21:
  - `albaranes.id_recepcion bigint` (nullable, metadato);
  - `albaranes_cambios` append-only (trigger contra UPDATE/DELETE/TRUNCATE), RLS, solo `SELECT` para
    `service_role`; su secuencia sin privilegios;
  - `cf_resincronizar_albaran(farmacia, id_contador, valores, origen, ejecucion)`: SECURITY DEFINER, solo
    `service_role`; bloquea la fila; identidad distinta (número o proveedor normalizado R9) → `REVISION
    CAMBIO_IDENTIDAD`; valores distintos (fecha, PUC, PVP, descuento, nombre de proveedor) con reserva
    R15 **releída en la transacción** → `REVISION RESERVADO:<factura>`; sin reserva → actualiza +
    `ACTUALIZADO`; `id_recepcion` se actualiza siempre que la identidad coincida; idempotente;
  - `cf_registrar_albaran_ausente`: revisión `AUSENTE_EN_FARMATIC` (una vez mientras siga abierta); nunca
    borra ni modifica la fila;
  - `cf_persistir_conciliacion` = 21 + rechazo `ALBARAN_AUSENTE_EN_FARMATIC`;
  - auxiliares `cf_albaran_ausente_abierto` y `cf_id_proveedor_comparable` solo para el propietario;
  - rollback = esquema 21 exacto (se pierden el historial y las recepciones).
- **Farmatic (solo lectura):** módulo de lectura de albaranes (`src/database/`):
  `obtener_nuevos_albaranes_con_recepcion`, `obtener_albaranes_entre_fechas` y
  `obtener_albaranes_por_contadores` (lotes de 500); la recepción por subconsulta
  `MIN(AlbaranRecep.IdRecepcion)` enlazada por proveedor y número del albarán. Las dos consultas
  anteriores no cambian.
- **Núcleo** `src/supabase_client/resincronizacion_albaranes.py` (no importa `runtime_supabase`): plan
  (nuevos, cambios, reaparecidos, ausentes; los ausentes se confirman por `IdContador` antes de
  registrarlos), ventana de 180 días ampliada a ±15 días de las facturas no conciliadas, ejecución por
  albarán (un error no detiene los demás) e informe.
- **Tarea nocturna** (`src/` sincronización de albaranes): con `CONTROLFARMACIAS_ALBARANES_V2` distinto de
  `1` (por defecto) el comportamiento es **exactamente el anterior**. Con `=1`: nuevos con recepción y
  después resincronización; un fallo de esta no deshace los nuevos (código de salida 2). Opción
  `--informe <salida.json>`: **modo informe sin escritura**, también antes de desplegar la 22.
- **Conciliación** (`repositorios.py`): excluye los albaranes con `AUSENTE_EN_FARMATIC` abierta; exige la 22
  (falla cerrado sin la tabla). Lector READ_ONLY del 2AT: `albaranes_cambios` en su lista blanca.
- **Carga histórica** `pruebas/auditoria_2bd/carga_historica.py` `[2026-04-01, 2026-06-01)`: `informe` (sin
  escritura) y `ejecutar` (configuración segura, guard de ejecución única, sin reintentos, exige la 22).
- **Despliegue** `pruebas/auditoria_2bd/desplegar_22.py` (patrón 21): SHA contra el commit, 9
  precondiciones, una transacción, postcondiciones (historial vacío, ninguna recepción cargada, RPC
  presentes, persistir con el rechazo de ausentes).
- **Tests:** `tests/facturas/test_resincronizacion_2bd.py` (sin BD) y
  `tests/facturas/runtime_supabase/test_integracion_pg17_2bd.py` (migración, rollback, privilegios,
  append-only, RPC con y sin reserva, identidad, ausente fuera del casado y reaparición, sincronización
  nocturna con Farmatic simulado, modo informe con 21 y 22, carga histórica, ensayo del despliegue).

**Orden de despliegue (producción, con confirmación de Pio):** 1) informe sin escritura (revisar el
volumen); 2) migración 22; 3) el código ya está en disco: sin la variable de activación la tarea nocturna
sigue igual, pero la **conciliación exige la 22** (no conciliar antes de desplegarla); 4) carga histórica
(informe → ejecutar); 5) activar `CONTROLFARMACIAS_ALBARANES_V2=1` en la tarea nocturna y vigilar la
primera noche (la primera pasada rellena `id_recepcion` de toda la ventana: ~5.100 eventos de metadato).
