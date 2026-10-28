# Estado actual

Actualizado: 2026-10-28 (Hito 2BD-D tanda RO: carga histórica y resincronización V2 manual). Las secciones sin fecha propia
conservan la de su hito.

## Git y respaldo

- 2026-10-19 (Hito 2BA-D): `origin/main` en `675cff323393a56d3741a24b4da78d1e27c1584d`, que incluye los
  commits del 2BA (`a91ca22`, `0a229cf`). Los commits locales del 2BA-D no tienen push: `PENDIENTE DE
  RESPALDO REMOTO`. `CONFIRMADO POR CÓDIGO` (Git local).
- Programa principal: repositorio `C:\ControlFarmacias\Programa`, rama operativa
  `main`, `HEAD` canónico
  `54dd951f6d661e9afd2206359f19517f90026a77` y `0 ahead / 0 behind` respecto de
  `origin/main`. Estado verificado con Git local de solo lectura el 2026-09-24;
  `CONFIRMADO POR CÓDIGO`.
- Estado base verificado al iniciar el Hito 0.1, antes de estos cambios
  documentales: `HEAD` y `origin/main` en
  `219cd9408b80f030efd18f99231498c5a2217f83`, `0 ahead / 0 behind`, y working
  tree limpio según Git de Windows. `CONFIRMADO POR CERTIFICACIÓN ARCHIVADA`,
  2026-09-24.
- Baseline anterior del Hito 0: `f87b32ba804aa6676fa7866b131b46e6c16540e5`.
  `HISTÓRICO`.
- Copias remotas adicionales verificadas:
  `backup/hito-0-preparacion-2026-09-24` en `e18acf0` y
  `hito-0-preparacion-2026-09-24` en `f87b32b`.
- Si otro entorno muestra cientos de `M` debidos solo a CRLF/LF y
  `git diff --ignore-cr-at-eol` no muestra diferencias reales, se clasifica como
  diferencia de entorno, no como working tree funcionalmente sucio.

## Arquitectura multirepositorio

```text
ControlFarmacias
|
+-- Programa
|   +-- repositorio principal / main
|
+-- Orquestador CLI cf
    +-- repositorio independiente / v0.2-dev
```

- Programa concentra facturas, ingesta, normalización, motor local, Supabase,
  albaranes, conciliación, workers, migraciones, tests y documentación
  funcional/técnica.
- El Orquestador CLI concentra el comando `cf`, interfaz CLI, lenguaje natural,
  supervisor, motor persistente, control de recursos, presupuesto Codex,
  clasificación `LOCAL_ONLY`/`CODEX_LIGHT`/`CODEX_STANDARD`/`CODEX_HEAVY`,
  estados operativos, recuperación read-only y ejecución local.
- Repositorio del Orquestador:
  `C:\ControlFarmacias\ControlFarmacias_Orquestador_V0_2_dev`; rama
  `v0.2-dev`; `HEAD` local conocido
  `869f1cc458444de914660e3e6b52e24ba5f10d40`; último commit `Certifica
  resultados funcionales y recuperacion read-only V0.2.12`.
- `origin/v0.2-dev` conocido:
  `fc77f62483566d496fb837db12e1fced07385408`. El local está `1 ahead / 0
  behind`. Clasificación: `DESARROLLO ACTIVO` y `PENDIENTE DE RESPALDO REMOTO`;
  no hacer `push` todavía.
- El CLI `cf` V0.2.12 no forma parte de la historia Git de `Programa/main`. Las
  historias son independientes y no existe `merge-base` entre ellas. No se debe
  interpretar la ausencia de commits del Orquestador en `main` como pérdida,
  fusionar ambas ramas ni tratar `v0.2-dev` como rama auxiliar de Programa.
- `OrquestadorExtraccionProductiva` vive dentro de Programa y no es el CLI `cf`.

Fuente: inspección Git local de solo lectura, 2026-09-24; `CONFIRMADO POR CÓDIGO`
para las referencias locales. El commit local `869f1cc` permanece `PENDIENTE DE
RESPALDO REMOTO`.

## Operación vigente

- PIO es la única farmacia autorizada. RITA está bloqueada.
- Valores seguros por defecto: `normalizacion_automatica=false`,
  `conciliacion_automatica=false`, `luna_habilitada=false`.
- Estos valores describen el contrato y la última certificación. El estado remoto
  vivo no se presume sin preflight productivo autorizado.
- La autoridad productiva de todos los extractores locales es `false` en el
  registro global. El compositor manual del Hito 2AP concede autoridad acotada
  solo a Alliance y únicamente para `ejecutar_una_manual()`; implementado y
  certificado en local (ver `pruebas/auditoria_2ap/`) y **ejecutado una sola vez
  en producción** en el Hito 2AO rev3 (ver "Primer MANUAL_ONE_SHOT productivo").
- El shadow local está apagado por defecto y, aun habilitado para observar, conserva
  la salida oficial y no aplica la salida local.
- `MANUAL_ONE_SHOT` está limitado a un documento y no admite preselección.

## Última evidencia operativa conocida

Los valores de esta sección proceden del encargo de consolidación Hito 0.1 de
2026-09-24. Estado común: `CONFIRMADO POR CERTIFICACIÓN ARCHIVADA`; **NO REVALIDADO
EN VIVO** durante esta consolidación documental.

### Ingesta Drive

- `FACTURAS_PIO_DIR`: `C:\GoogleDrive\FACTURES PIO`.
- Última ejecución conocida: 143 PDF elegibles, 143 omitidos por índice,
  0 importados y 0 errores.
- Resultado registrado: 140 documentos PIO.

### Albaranes

- Última ejecución conocida: 37 nuevos, `IdContador` máximo 292043 y ejecución
  automática con código 0.

### Task Scheduler

- La ejecución automática de albaranes quedó reparada.
- La lectura o administración desde una sesión ordinaria puede seguir devolviendo
  `Acceso denegado`.
- No se debe afirmar su estado vivo actual sin una consulta autorizada.

### Supabase y conciliación

- `documentos_facturas` PIO: 140; `facturas`: 7;
  `normalizacion_ejecuciones`: 7; `conciliaciones`: 12; workers: 0; locks: 0.
- Flags: `normalizacion_automatica=false`, `conciliacion_automatica=false`,
  `luna_habilitada=false`, `farmacias_habilitadas=["PIO"]`.
- Conciliación: 7 facturas, 6 conciliadas y 1 pendiente. La pendiente es HEFAME
  `0563834757`. Tolerancia: `0.0500`.

### Primer MANUAL_ONE_SHOT productivo (Hito 2AO rev3)

`CONFIRMADO EN PRODUCCIÓN`, 2026-09-25, con confirmación expresa de Pio. Una
única llamada a `ejecutar_una_manual()` mediante
`construir_worker_manual_productivo` (worker `cf-2ao-manual-one-shot`),
14:54:48–14:54:56 UTC. Scripts: `pruebas/auditoria_2ao/`.

- Documento reclamado = candidato n.º 1 del ordering oficial:
  `ae53897a-355a-488f-bc3e-1783f39e0f13` (SHA `4faa899b…`), Alliance por
  contenido, 13 páginas, 5 facturas. Resultado `NORMALIZADA/COMPLETA`, claim y
  lock liberados, 1 ejecución `MANUAL_ONE_SHOT` `COMPLETADA`, sin Luna ni OCR.
- Facturas creadas (5, todas autorizadas, `NORMALIZADA`,
  `PENDIENTE_CONCILIAR`): 08007970 (2.356,64), 08007969 (12.807,17),
  08007971 (364,47), 08007973 (22,49) y 08007972 (464,76).
- Conteos tras el hito: `documentos_facturas` 143 (2 `NORMALIZADA/COMPLETA`,
  4 `NORMALIZADA/PENDIENTE`, 137 `PENDIENTE`), `facturas` 12,
  `normalizacion_ejecuciones` 8, `conciliaciones` 12 (sin cambios), workers 0,
  locks 0/0, flags sin cambios.
- Postcheck por huellas de fila sobre columnas explícitas: ninguna diferencia
  fuera del documento reclamado y sus filas nuevas; HEFAME `0563834757` intacta.
- 08007971 no tiene albaranes extraídos (incidencia no bloqueante
  `CANDIDATO_ALBARAN_NO_PROMOVIDO`); en conciliación quedaría `NO_APTA`
  (`FALTAN_ALBARANES_MERCANCIA`). No se corrige.

### Primera conciliación manual one-shot productiva (Hito 2AT rev2)

`CONFIRMADO EN PRODUCCIÓN`, 2026-10-06, con confirmación expresa de Pio. Una
única llamada a `WorkerAutomatico.ejecutar_una_manual_conciliacion()` mediante
`construir_worker_manual_productivo` (worker `cf-2at-manual-conciliacion`,
cliente `service_role`), 07:26:30–07:26:32 UTC, desde el commit `522ad3e`.
Scripts: `pruebas/auditoria_2at/` (`auditoria_readonly.py`, solo lectura;
`ejecutar_una_vez.py`, con revalidación previa y guard de ejecución única),
ensayados completos en PostgreSQL 17 local
(`tests/facturas/runtime_supabase/test_ensayo_fase4_2at.py`). Evidencias fuera
del repositorio en `C:\ControlFarmacias\evidencias_2at\` (datos de negocio, no
versionar); nota de estado `C:\ControlFarmacias\encargos\2AT_rev2_ESTADO.txt`.

- Preflight READ_ONLY (`PREFLIGHT_OK`), snapshot por fila sobre columnas
  explícitas y revalidación del candidato (idéntico al de la víspera en id,
  huella de fila, simulación y elegibles).
- Elegibles en el ordering oficial: 08007973, 08007972 y 08007970 (Alliance,
  2026-06-30; desempate por id). No elegibles: 08007971 (`FALTAN_ALBARANES_MERCANCIA`,
  deuda 2AU), 08007969 y HEFAME 0563834757 (`TOTAL_NO_EXPLICADO`) y 6 ya
  `CONCILIADA`.
- Factura reclamada = candidato n.º 1 confirmado por Pio: 08007973
  (`2a1a378e-d277-45d6-a910-d4860f4151d8`), 22,49 EUR.
- Resultado: `CONCILIADA`, importe 22,4900, explicado 22,4900, diferencia
  0,0000, tolerancia 0,0500; conciliación `e835b2d6-9390-48a2-ab1b-a6a864a5f12f`,
  intento 1, disparador y provenance `MANUAL_ONE_SHOT`, `COMPLETADA`,
  `es_actual`; clave idempotente idéntica a la simulada antes de ejecutar.
  Intentos de conciliación 1, intentos fallidos 0, sin próximo reintento.
- Albaranes casados 1:1 (`MATCH_UNICO`, número EXACTO, proveedor Farmatic
  "1.- SAFA", id 2): 08M26924 (PDF 12,45, PUC 12,44, IdContador 280242) y
  08C23236 (PDF 10,04, PUC 10,05, IdContador 280269). Sin movimientos ni abonos.
- Postcheck por huellas (`POSTCHECK_OK`): solo cambió la fila de 08007973
  (estado, intentos, diferencia_albaranes, updated_at); filas nuevas: 1
  conciliación, 2 detalles y 2 eventos de historial (claim y persistida), todos
  de esa factura. Conciliaciones previas, albaranes, extraídos y movimientos
  intactos. Flags `f|f|f|{PIO}`, `cf_configuracion` idéntica, workers 0, locks
  0, claims 0, NORMALIZANDO 0.
- Conteos tras el hito: `facturas` 12 (7 `CONCILIADA`, 5 `PENDIENTE_CONCILIAR`),
  `conciliaciones` 13, `conciliacion_detalles` 751, `historial_facturas` 35,
  `albaranes` 3688, `documentos_facturas` 160.
- Verificación previa de las noches del 29/09 y 30/09 con la 19: códigos de
  salida 0 y sin `permission denied`/42501 en los logs; filas nuevas en
  `documentos_facturas` (1) y `albaranes` (46 y 29) coherentes con los logs. El
  historial del Programador de tareas ya no conserva esas noches.
- Diferencias admitidas por Pio entre el selector reproducido READ_ONLY y el
  núcleo de la migración 18: sin `for update of f skip locked`, sin `limit 1`,
  `p_modo_ejecucion` sustituido por parámetro `'MANUAL_ONE_SHOT'` y sin
  `into v_id` (fuera de PL/pgSQL sería DDL).
- Suites: 1576 passed sin `pg17_local`; 88 passed `pg17_local` (2026-10-05,
  mismo código).

### Hito 2BD-D, tanda RO: carga histórica y resincronización V2 manual en producción

`CONFIRMADO EN PRODUCCIÓN`, 2026-10-27/28, ejecutado por Pio en terminal como
`MOSTRADOR\ControlFarmaciasRO` (Farmatic certificado READ_ONLY). Evidencias (fuera del repositorio):
`C:\ControlFarmacias\evidencias_2bd_ro\`. Script: `pruebas/auditoria_2bd_ro/postcheck_readonly.py`
(captura y comparación READ_ONLY). Sin push.

- **Carga histórica** `[2026-04-01, 2026-06-01)`: `COMPLETADA`, 1.635 insertados, 0 errores (guard de
  ejecución única creado).
- **Resincronización V2 manual** (`CONTROLFARMACIAS_ALBARANES_V2=1` solo en esa sesión; 2026-10-28,
  ventana desde 2026-05-01): 24 nuevos; resincronización con 4.270 cambios = 4.269 actualizados (relleno de
  `id_recepcion` NULL → valor) + 1 revisión `CAMBIO_IDENTIDAD` (IdContador 279410); 0 ausentes; 0 errores.
- **Postcheck:** la primera comparación dio `POSTCHECK_REVISAR` solo por `OPERACION_DISTINTA`
  (`conteos.albaranes` 5.906 → 5.930). Corregido: `conteos.albaranes` no es operación; se compara aparte y
  solo se admite un incremento igual a los albaranes nuevos (test `test_postcheck_2bd_ro.py`). Recomparación
  sobre las mismas capturas: `POSTCHECK_OK` (reservas idénticas, 282; historial: 4.269 `ACTUALIZADO`
  `id_recepcion` + 2 filas de revisión de 279410; ninguna huella de `albaranes` cambiada fuera de
  `id_recepcion`; 0 recepciones sobrescritas; resto de la operación idéntico).
- **Informe V2 sin escritura posterior** (`informe_v2_postcheck.json`): 0 nuevos, 0 ausentes, 1 cambio
  (279410, `REVISION:CAMBIO_IDENTIDAD`), 5.093 iguales.
- **Explorador SQL** probado como `ControlFarmaciasRO` (metadatos de `AlbaranRecep`) y suites del explorador
  en verde.
- **279410 (08C16912): aprobación previa ampliada de Pio** para cuando exista el camino de resolución de
  revisiones (hito futuro, NO implementado): `id_proveedor` 52 → `0002` (CINFA → SAFA) y `numero_albaran`
  08C16912 → 08C16912A. Hasta entonces el albarán sigue en Supabase con los valores antiguos y en revisión.
- **V2 en la tarea nocturna:** la activa Pio a mano. `PENDIENTE`: vigilar la primera noche.

### Hito 2BD-D: migración 22 desplegada en producción (tanda Usuari; V2 APAGADA)

`CONFIRMADO EN PRODUCCIÓN`, 2026-10-23, con confirmación expresa de Pio. Evidencias (fuera del
repositorio, con `SHA256SUMS.txt`): `C:\ControlFarmacias\evidencias_2bd-d\`. Scripts:
`pruebas/auditoria_2bd_d/` (`preflight_readonly.py`, `conciliacion_2at.py`). Sin push.

- **Puerta** (decisión de Pio): `origin/main` = `5012ee3` más los 4 commits locales del piloto de agentes
  (`0962ed7`..`8b41e45`; push el martes). Suites: 1991 passed sin `pg17_local`; 137 passed `pg17_local`
  (incluido el ensayo de `desplegar_22.py`). Autorizado por Pio que los scripts productivos lean `.env` y
  `CONTROLFARMACIAS_SUPABASE_DB_URL` por dentro, sin mostrarlos. Tareas consultadas solo con
  `Get-ScheduledTaskInfo`.
- **Preflight READ_ONLY** (13:46 UTC): las 9 precondiciones de `desplegar_22.py` en verde; marcas 19/20/21
  presentes y 22 ausente; operación a cero; 282 reservas = líneas vigentes con albarán; 0 duplicados
  `(farmacia, IdContador)`; propietarios `postgres`; tareas a más de 5 h; esquema idéntico al postcheck del
  2BA-D. Alcance de la 22 derivado de las referencias locales 21/22: 9 objetos. Backup: volcado completo de
  las 9 tablas de huella (`preflight_pre.json`).
- **Diferencia de baseline hallada:** `albaranes` tiene en producción dos índices que la referencia local no
  crea (`albaranes_fecha_idx`, `albaranes_proveedor_idx`; presentes al menos desde el 2P). **Excepción
  aprobada por Pio** para el postcheck: único cambio pre→post en `albaranes` = columna `id_recepcion` (igual
  a la referencia 22) y esos dos índices idénticos pre/post. `PENDIENTE`: alinear el baseline local.
- **Despliegue:** `desplegar_22.py 1c44d1a ff6c6747…` → **APLICADA** (13:52 UTC), una transacción, sin
  reintento; postcondiciones: historial vacío, 0 recepciones, RPC presentes, persistir rechaza ausentes.
- **Postcheck:** `POSTCHECK_OK` (solo cambian los 9 objetos del alcance, iguales a la referencia 22 con la
  excepción aprobada; fuera de alcance idénticos; huellas de las 9 tablas idénticas; operación, flags y
  reservas sin cambios). **Privilegios:** `FUNCIONAL_OK` (`albaranes_cambios` solo `SELECT` para
  `service_role`, `anon`/`authenticated` denegados, RLS y triggers append-only; las dos RPC nuevas y
  `cf_persistir_conciliacion` solo `service_role`, SECURITY DEFINER, owner `postgres`; auxiliares solo
  propietario; `service_role` sigue sin `UPDATE` en `albaranes`).
- **V2 sigue APAGADA** (`CONTROLFARMACIAS_ALBARANES_V2` no activada). Tanda RO hecha el 2026-10-27/28
  (ver "Hito 2BD-D, tanda RO").
- **Conciliación one-shot de 08007972: NO ejecutada (decisión de Pio), aplazada.** Preflight y snapshot OK;
  candidato n.º 1 = 08007972, como se esperaba. Simulación sin claim: `DIFERENCIA` (explicado 41,89 de
  464,76). 08C16913→08C16913A y 08M23197 casan 1:1; **08C16912 (422,88) no casa: en Supabase existe
  (IdContador 279410, PUC 422,86, 2026-06-22) con proveedor 52 CINFA** en Farmatic (único albarán de CINFA
  en Supabase), y la factura es SAFA (proveedor 2). Probable registro con proveedor erróneo en Farmatic
  (`INFERIDO`). `PENDIENTE`: revisión de Pio en Farmatic.
- **Hito futuro registrado (NO implementado): resolución de revisiones con aprobación de Pio.** La 22 trata
  un cambio de proveedor o número como cambio de identidad (`REVISION CAMBIO_IDENTIDAD`) y no actualiza el
  albarán; corregir 08C16912 en Farmatic no se propagará solo. Hace falta un camino para aplicar esas
  revisiones con aprobación explícita de Pio.

### Hito 2BD: resincronización de albaranes (certificado en local; 22 desplegada en el 2BD-D)

`CONFIRMADO POR TEST` (PostgreSQL 17 local, Farmatic **simulado**), 2026-10-22, commit local (sin push).
**Producción y Farmatic no tocados** en la implementación (las mediciones READ_ONLY previas del 2BD
están en `C:\ControlFarmacias\evidencias_2bd\`). Diseño e implementación en
`pruebas/auditoria_2bd/DISENO.md` (apartado 6).

- **Decisiones de Pio:** albarán `AUSENTE_EN_FARMATIC` → revisión y **fuera del casado**; la sincronización
  trae también la recepción (`AlbaranRecep`, proveedor **del albarán**); patrón «número exacto + `Q…` de la
  misma recepción» → hito **2BE (R17)**, no ahora; Pio revertirá 08C20268 a 500,86 en Farmatic (el test de
  modificación usa el albarán sintético `08Z90001`, 500,86 → 504,02).
- **Migración 22** `22_cf_resincronizacion_albaranes.sql` (+ rollback = esquema 21 exacto; generada por
  `pruebas/auditoria_2bd/generar_migracion_22.py` desde la 21): `albaranes.id_recepcion`; historial
  append-only `albaranes_cambios` (solo `SELECT` para `service_role`); RPC `cf_resincronizar_albaran`
  (identidad distinta → revisión; reservado R15, releído en la transacción → revisión; si no →
  actualiza + historial; idempotente) y `cf_registrar_albaran_ausente` (nunca borra);
  `cf_persistir_conciliacion` = 21 + rechazo `ALBARAN_AUSENTE_EN_FARMATIC`. `service_role` sigue sin
  `UPDATE` sobre `albaranes`.
- **Código:** lecturas de Farmatic nuevas (nuevos con recepción, rango de fechas, confirmación por
  `IdContador`; solo SELECT); núcleo `src/supabase_client/resincronizacion_albaranes.py` (ventana de 180 días
  ampliada a ±15 días de las facturas no conciliadas; `id_proveedor` normalizado R9; no importa
  `runtime_supabase`); tarea nocturna con la v2 **desactivada por defecto**
  (`CONTROLFARMACIAS_ALBARANES_V2=1` la activa: nuevos con recepción + modificados; un fallo de la
  resincronización no deshace los nuevos, código de salida 2); **modo informe sin escritura**
  (`--informe <salida.json>`, también sin la 22); la conciliación excluye los ausentes.
- **Scripts:** `pruebas/auditoria_2bd/carga_historica.py` (`[2026-04-01, 2026-06-01)`, `informe` /
  `ejecutar` con guard de ejecución única) y `desplegar_22.py` (patrón 21). **Ensayo completo en local**
  sobre el commit `1c44d1a`: primer intento aplicado (9 precondiciones; postcondiciones: historial vacío,
  ninguna recepción cargada, RPC presentes, persistir con el rechazo de ausentes; esquema igual a la
  referencia y huellas intactas); segundo intento falla en precondiciones y revierte sin cambios.
- **Suites (2BD, `--basetemp`):** 1694 passed sin `pg17_local`; `pg17_local` 136 passed y 1 skipped antes
  del commit (el ensayo); tras el commit, el ensayo y la prueba de solo lectura de sus precondiciones:
  2 passed.
- **Efecto del código ya en disco (antes de desplegar la 22):** la tarea nocturna no cambia (v2 apagada;
  sus consultas anteriores intactas). La **conciliación** (y los scripts READ_ONLY del 2AT, que ahora
  declaran `albaranes.id_recepcion` y leen `albaranes_cambios`) **exige la 22**: no conciliar en
  producción antes de desplegarla. Los scripts del 2BA-D/2BB que usan `columnas_declaradas.json` deberán
  declarar `id_recepcion` tras la 22.
- **Orden de despliegue propuesto** (todo con confirmación de Pio): informe sin escritura → migración 22
  → carga histórica (informe → ejecutar) → activar la v2 en la tarea nocturna y vigilar la primera noche
  (primera pasada: ~5.100 eventos `id_recepcion` de metadato).
- **Tests existentes actualizados por cambio de contrato:** las bases que concilian con el código pasan
  de la plantilla 21 a la 22 (2AV, 2BA) o aplican la 22 (ensayo 2AT, 2AX, 2AZ); escenarios falsos del 2BA
  con `albaranes_cambios`; recuento de consultas de Farmatic 2 → 5 (más la subconsulta de recepción,
  todas SELECT) en dos tests; lista de migraciones; columnas declaradas del 2AT con `id_recepcion`.

### Conciliación manual one-shot de 08007971 (2026-10-22)

`CONFIRMADO EN PRODUCCIÓN`, 2026-10-22, con confirmación expresa de Pio. Procedimiento del 2AT
(`pruebas/auditoria_2at/auditoria_readonly.py` y `ejecutar_una_vez.py`); sin workers, sin flags y sin
reintentos. Evidencias en `C:\ControlFarmacias\evidencias_2bc\` (SHA en `SHA256SUMS.txt`).

- **Preflight** `PREFLIGHT_OK` (16:09 UTC) y snapshot por fila (`snapshot_pre.json`, SHA-256
  `1bb82492c72517bacae72027fe3d97fdf152cce43aa745851890ae2bb411dd33`).
- **Selector oficial** (reproducido READ_ONLY, igual al oficial; cuerpos productivos = 18 y 21): aptas
  1) 08007971, 2) 08007972, 3) 08007969, 4) 08007970 (las cuatro de 2026-06-30, desempate por id). No
  aptas: 7 ya CONCILIADA y HEFAME 0563834757 (`TOTAL_NO_EXPLICADO`).
- **Revalidación** (16:10 y 16:14 UTC, `revalidacion_b.json`): candidato, huella, simulación y elegibles
  idénticos; `CANDIDATO_OK`.
- **Ejecución:** una invocación, 16:14:24–16:14:27 UTC, worker `cf-2at-manual-conciliacion`, cliente
  `service_role`, `RETORNO`; guard de ejecución única en las evidencias (`ejecucion.json`).
- **Resultado:** 08007971 `CONCILIADA`, importe 364,47, explicado 364,48, diferencia −0,01, tolerancia
  0,05 (R11 con 3 albaranes); conciliación `fa1d6675-42f1-48fe-a7bb-d6b71a746956`, intento 1,
  `MANUAL_ONE_SHOT`, clave idempotente igual a la simulada. Albaranes casados 1:1: 08C18299 ↔
  Q039904/2026 (279694, interno, 191,84), 08M24229 ↔ 279774 (exacto, PUC 150,99) y 08M25574 ↔ 280053
  (exacto, 21,65).
- **Postcheck** (`comparacion_stdout.txt`, `POSTCHECK_OK`): solo cambió la fila de 08007971 (estado,
  intentos, `diferencia_albaranes`, `updated_at`); filas nuevas: 1 conciliación, 3 detalles y 2 eventos
  de historial, todos de esa factura. Reservas: 279 → 282 (las 3 nuevas de 08007971 = sus líneas
  vigentes; ninguna borrada). Esquema y `cf_configuracion` idénticos a los del 21/10; flags
  `f|f|f|{PIO}`; workers, locks y claims 0.
- Conteos tras la conciliación: `facturas` 12 (8 CONCILIADA, 4 PENDIENTE_CONCILIAR), `conciliaciones` 14,
  `conciliacion_detalles` 754, `historial_facturas` 38.

### Hito 2BB: diagnóstico de 08007969 y enriquecimiento de 08007971

2026-10-21. Producción: lecturas READ_ONLY y una única escritura, el enriquecimiento de 08007971. Scripts en `pruebas/auditoria_2bb/`
(`diagnostico_readonly.py`, `enriquecimiento_readonly.py`); evidencias en
`C:\ControlFarmacias\evidencias_2bb\` (SHA en `SHA256SUMS.txt`).

- **08007969: causa de la DIFERENCIA de 504,09 localizada** (`CONFIRMADO EN PRODUCCIÓN` por simulación
  READ_ONLY del worker, 2026-10-21; `diagnostico_08007969.json`):
  - 504,09 = **504,02** del albarán **08C20268** sin casar + **0,07** de residuo documental (total del PDF
    12.807,17 frente a líneas 13.020,88 − 213,78 = 12.807,10). Las otras 127 líneas casan (117 número
    exacto, 8 interno, 2 letra final; 32 con ±0,01 que se compensan, neto 0,00) y los 6 movimientos
    casan exactos. Sin filas no promovidas (solo avisos no bloqueantes de moneda y vencimiento).
  - 08C20268 (PDF página 6, `NORMAL ACUSTICO`, base 479,97, total 504,02) existe en Farmatic con el mismo
    número y fecha (IdContador 280005, SAFA, sin reserva) pero con PUC 500,86: diferencia 3,16 > tolerancia
    de importe por línea.
  - **Causa resuelta en Farmatic por Pio (2026-10-21):** al albarán le faltaba la línea VIDESIL 50000UI
    (3,03 de base); PUC en Farmatic ahora 504,02.
  - **Pendiente:** que Supabase refleje el cambio. Verificado READ_ONLY el 2026-10-21 15:55 UTC
    (`albaran_280005.json`): `Supabase.albaranes` 280005 sigue con PUC 500,86 (`fecha_actualizacion`
    2026-07-25, la de su importación). Con el PUC corregido, la diferencia prevista de 08007969 sería 0,07
    (dentro de la tolerancia R11 de 0,50), sin haberse simulado todavía.
- **Hueco detectado: la sincronización de albaranes no detecta albaranes modificados en Farmatic.**
  `CONFIRMADO POR CÓDIGO` (2026-10-21): `src/database/leer_albaranes.py:61` solo lee
  `WHERE a.IdContador > ?` desde el último `IdContador` de Supabase (`src/sincronizar_albaranes.py:55`); un
  albarán ya existente solo se registra en el log (`src/sincronizar_albaranes.py:106`) y nunca se
  actualiza. Toda corrección posterior en Farmatic (líneas añadidas, importes) queda invisible para la
  conciliación.
  - **Implementado en local en el Hito 2BD (22 NO desplegada; ver esa sección).** Diseño original:
    resincronización de albaranes modificados:
    - ventana reciente de albaranes ya sincronizados (a definir);
    - detección de cambios de importe (PUC/PVP) y de otros campos frente a Supabase;
    - historial de cada cambio (valor anterior, nuevo, fecha y origen);
    - albarán con reserva de una conciliación vigente (R15) → **revisión, no actualizar**.
    - Farmatic sigue siendo de solo lectura; el cambio afecta solo a `Supabase.albaranes`.
- **08007971: enriquecida en producción (R12).** `CONFIRMADO EN PRODUCCIÓN`, 2026-10-21, con confirmación
  expresa de Pio. Sin conciliar, sin workers y sin flags.
  - Preflight READ_ONLY `PREFLIGHT_OK` (15:04 UTC, `preflight_08007971.json`) y snapshot con huellas
    (`snapshot_pre.json`): PENDIENTE_CONCILIAR, sin claim, PDF del espejo local con el SHA registrado
    (`4faa899b…d9f1`), extracción autorizada local con identidad idéntica, payload calculado con
    `construir_enriquecimiento`; los 3 albaranes operacionales sin reserva de otra factura.
  - Repetidos a las 15:58 UTC (`preflight_08007971_b.json`, `snapshot_pre_b.json`, SHA-256
    `f1a44dce99044f41f9a55643be7163b0fa12cf3c0ebc9ef475f430694a2caea2`): idénticos, sin ningún cambio en
    las 9 tablas (`comparacion_repeticion.json`).
  - **Ejecución:** `pruebas/auditoria_2az/enriquecer_una_vez.py`, una invocación, 15:59:33–15:59:36 UTC,
    worker `cf-2az-enriquecimiento`, clave `enriquecimiento:24b94a6c…:16c8c22c…e1e4cc` (la prevista),
    `RETORNO`, sin replay; guard de ejecución única en las evidencias (`enriquecimiento.json`).
  - **Postcheck** (`comparacion_postcheck.json`, `POSTCHECK_OK`): solo cambiaron filas de 08007971:
    +3 `facturas_albaranes_extraidos` (08C18299 183,58/191,84; 08M24229 119,64/150,98; 08M25574
    20,72/21,65; DIRECTO, CARGO), el vencimiento 30-09-2026 (importe NULL → 364,47, con la provenance R14)
    y 1 evento `FACTURA_ENRIQUECIDA`. Esquema, `cf_configuracion`, operación y las 279 reservas idénticos;
    ninguna fila ajena.
  - Elegibilidad: `NO_APTA:FALTAN_ALBARANES_MERCANCIA` → `APTA:APTA_MERCANCIA` (única factura cambiada).
    En Farmatic sus albaranes son Q039904/2026 (279694, PUC 191,84), 279774 (150,99) y 280053 (21,65):
    en el test local del 2BA (`test_08007971_enriquecida_y_conciliada_con_la_21`) concilia con diferencia
    −0,01; no simulado sobre producción ni ejecutado.
  - ~~Pendiente: su conciliación~~: CONCILIADA el 2026-10-22 (ver la sección correspondiente).

### Hito 2BA-D: migración 21 desplegada en producción

`CONFIRMADO EN PRODUCCIÓN`, 2026-10-19, con confirmación expresa de Pio. Sin conciliar, sin enriquecer,
sin workers y sin flags. Scripts READ_ONLY del hito en `pruebas/auditoria_2ba_d/preflight_readonly.py`;
evidencias en `C:\ControlFarmacias\evidencias_2ba-d\` (SHA en `SHA256SUMS.txt`).

- **Puerta:** `HEAD` = `origin/main` = `675cff3` (incluye `a91ca22` y `0a229cf`); suites 1664 passed sin
  `pg17_local` y 120 passed `pg17_local` (incluido el ensayo de `desplegar_21.py`).
- **Preflight READ_ONLY** (`preflight_pre.json`, 15:44 UTC, SHA-256
  `922660849dcd7334c9100af5193ec0e341f9c1b09186ef8f044c27e9258ab173`; es también el backup: definiciones,
  ACL, privilegios por defecto, `cf_configuracion`, elegibilidad y huellas y volcado por fila de 9 tablas
  sobre columnas declaradas antes de ejecutar): `PREFLIGHT_OK`.
  - Esquema 20: alcance igual a la referencia local 20 y esquema completo y privilegios por defecto
    idénticos al postcheck del 2AZ-D (`comparacion_pre.json`); 21 ausente; 50 objetos, todos de `postgres`.
  - Operación: flags `f|f|f|{PIO}`, tolerancia 0,05, locks/claims/NORMALIZANDO/workers 0; 12 facturas
    (7 CONCILIADA, 5 PENDIENTE_CONCILIAR), 13 conciliaciones; tareas Ready, próximas a las 19:00 y
    19:30 UTC.
  - Tareas nocturnas: `ejecutar_importacion_facturas.bat:10` (`-m src.facturas.importar_facturas_drive`)
    y `ejecutar_sincronizacion.bat:10` (`-m src.sincronizar_albaranes`); el grafo estático de imports
    transitivos de ambas no alcanza `runtime_supabase` ni usa imports dinámicos (`CONFIRMADO POR CÓDIGO`).
  - Noche del 18/10: importación código 0 (164 PDF, 0 nuevos, 0 errores); sincronización código 0
    (17 albaranes nuevos, `IdContador` máximo 295057); sin `permission denied` ni 42501 en ningún log.
  - 279 líneas vigentes con albarán y 0 albaranes duplicados entre ellas.
  - Precondiciones de `desplegar_21.py` ejecutadas antes en producción en transacción READ_ONLY: 9/9.
- **Despliegue:** `desplegar_21.py a91ca22 f0a99416…bfcaca`, 15:50:22–15:50:23 UTC, una transacción,
  9 precondiciones en verde, sin reintentos; SQL normalizado a LF idéntico al de `a91ca22` (SHA-256
  `f0a99416d2739a81a762f5b788fac402cf8277454897848346aa2e45e1bfcaca`); 279 reservas cargadas = 279
  líneas vigentes con albarán.
- **Postcheck** (`comparacion_postcheck.json`, `POSTCHECK_OK`): solo cambiaron
  `cf_persistir_conciliacion`, `cf_evaluar_elegibilidad_conciliacion` y la nueva
  `conciliacion_albaranes_reservados`, iguales a la referencia local 21; todo lo demás, privilegios por
  defecto y `cf_configuracion` idénticos; huellas de las 9 tablas idénticas; operación como antes;
  reservas = líneas vigentes con albarán (279).
- **Prueba funcional READ_ONLY** (`funcional.json`, `FUNCIONAL_OK`): `service_role` lee las reservas
  (279) y ejecuta la elegibilidad; sin INSERT/UPDATE/DELETE/TRUNCATE en la tabla; `anon` y
  `authenticated` reciben «permission denied» en la tabla y en la elegibilidad; ambas funciones
  SECURITY DEFINER, propietario `postgres`, EXECUTE solo `service_role`; tabla de `postgres` con RLS.
- **Elegibilidad cambiada por R16** (informativa): solo **08007969**
  (`9a1bf74a-0d85-4017-9e33-a8f5e0a9e36e`), de `NO_APTA:TOTAL_NO_EXPLICADO` a `APTA:APTA_MIXTA`. Es
  ahora conciliable; en el banco concilia como DIFERENCIA de 504,09 (pendiente de revisión, ver 2BA).
- **Nada se concilió ni se enriqueció.**

### Hito 2BA: exclusividad de albaranes y elegibilidad proporcional (certificado en local; 21 desplegada en el 2BA-D)

`CONFIRMADO POR TEST` (PostgreSQL 17 local), 2026-10-09, commit local `a91ca22` (sin push).
**Producción no tocada:** solo lecturas READ_ONLY de medición (2026-10-08). Reglas R15, R15b, R15c, R16
y de numeración en `REGLAS_CRITICAS.md`; evidencias fuera del repositorio en
`C:\ControlFarmacias\evidencias_2ba\`.

- **Código:**
  - `conciliacion.py`: `clasificar_numero_albaran`, R15b/R15c, exacto sobre letra final,
    `buscar_albaranes_factura` (exclusividad dentro de la factura y frente a otras facturas) y
    `clase_numero` en la provenance;
  - `repositorios.py`: `leer_paginado` y contexto de exclusividad (reservas vigentes de otras facturas);
  - corrige D12 (registrado en el 2AZ) y la métrica D12 del preflight 2AZ-D (solo conciliaciones
    vigentes).
- **Migración 21** `21_cf_exclusividad_albaranes.sql` (+ rollback; generada por
  `pruebas/auditoria_2ba/generar_migracion_21.py` desde el texto exacto de la 20 y de la 14):
  - tabla `conciliacion_albaranes_reservados`, cargada desde las conciliaciones vigentes (aborta si dos
    comparten albarán);
  - R15 en `cf_persistir_conciliacion` y R16 en `cf_evaluar_elegibilidad_conciliacion`;
  - rollback igual al esquema 20 (test).
  - **Orden de despliegue:** primero la 21 y después el código. El código 2BA no concilia sobre el
    esquema 20 (falla cerrado: no existe la tabla de reservas).
  - `desplegar_21.py` (patrón 2AZ) **ensayado completo en local** sobre `a91ca22`: primer intento
    aplicado (9 precondiciones, 4 reservas cargadas, esquema igual a la referencia, huellas intactas);
    segundo intento falla en precondiciones y revierte sin cambios.
- **Scripts READ_ONLY del 2AT** (`pruebas/auditoria_2at/auditoria_readonly.py`): `_ConsultaLectura`
  pagina con `range` (falla cerrado sin `order`), lee la tabla de reservas y el preflight compara la
  elegibilidad productiva con la **21**. Desde este commit, esos scripts solo sirven con la 21
  desplegada.
- **Banco 2AY con el código 2BA** (`verificacion_src_2ba.json`): 47 facturas Alliance, 47 aptas (antes
  42), 27 conciliadas; **0 diferencias** con la medición aprobada por Pio
  (`medicion_r15b_exacta_sobre_sufijo.json`). Cambios frente al código 2AZ: 08007969, 08008834,
  08010085, 08010461 y 08010885 pasan a aptas por R16 (08008834 y 08010885 concilian); 08007970 pasa
  de CONCILIADA (−0,08) a DIFERENCIA de 38,98 y 08009716 de CONCILIADA a DIFERENCIA de 113,73 (un
  albarán sin casar en cada una; causa por línea no analizada en este hito).
- **Riesgo de las tareas nocturnas con el código 2BA en disco:** ninguno de sus puntos de entrada
  importa `runtime_supabase` (verificado en el 2BA-D, ver arriba).
- **Pendientes:**
  - ~~despliegue de la 21~~: hecho en el Hito 2BA-D (2026-10-19);
  - **08007969** (MIXTA, 12.807,17): con R16 pasa a APTA, pero en el banco concilia como DIFERENCIA de
    504,09 (127 albaranes casados, 1 sin coincidencia). Revisar antes de conciliarla. Causa localizada y
    corregida en Farmatic en el Hito 2BB (08C20268); pendiente de que Supabase refleje el cambio;
  - **duplicados en Farmatic 08C66676 / 08C66676A** (08009718, línea de 31,59): misma fecha y PUC 31,58
    (caso fijado en `test_exacto_se_impone_a_la_letra_final_08009718`). El número exacto se impone y
    deja libre el `A`; posible doble registro en Farmatic. Revisión de Pio en Farmatic (solo lectura);
  - ~~`tests/test_sql_explorer_entrada.py::test_valor_filtro_por_tuberia_sin_bom_ni_fin_de_linea`~~:
    corregido por Pio en `675cff3` (lectura de stdin por tubería como UTF-8); suite sin `pg17_local`
    en verde desde entonces (1664 passed).
- **Suites (2BA, `--basetemp`, MOSTRADOR\Usuari):**
  - 1662 passed sin `pg17_local`, 1 failed (el test anterior);
  - `pg17_local`: 119 passed y 1 skipped antes del commit (el ensayo de la 21, que exige el commit);
    tras el commit, el ensayo y la prueba de solo lectura de sus precondiciones: 2 passed.
  - Tests existentes actualizados por cambio de contrato, cada uno con su justificación:
    - 2AV, ensayo 2AT, 2AX y 2AZ concilian con la 21 aplicada; 4.2 y 4.11 siguen sobre la 18 (certifican
      la propia 18); 4.13 crea los datos de la 18 con sus RPC;
    - 08007969 APTA por R16 (4.14 y escenario del ensayo 2AT, que además la desplaza en el ordering);
    - 08D28707 casa con el interno Q040658/2026 (R15b) y 08011733 queda con diferencia 26,27;
    - sin número, ventana de ±3 días (R15c); lista de migraciones; datos de reservas en los tests de la
      21 (08007971 en estado 2AO no tiene extraídos).

### Hito 2AZ-D: migración 20 desplegada en producción

`CONFIRMADO EN PRODUCCIÓN`, 2026-10-08, con confirmación expresa de Pio.

- **Despliegue:**
  - `pruebas/auditoria_2az/desplegar_20.py 8e6bace aa8f1d55…56a1f`, aplicado de 09:07:02 a 09:07:03
    UTC;
  - SQL normalizado a LF e idéntico al del commit `8e6bace` (SHA-256
    `aa8f1d555f5b61c82c6aaa1df8468f453fca9cef741566d0de2c23baf6d56a1f`);
  - una sola transacción, con las 9 precondiciones en verde y sin reintentos.
  - Scripts READ_ONLY del hito en `pruebas/auditoria_2az_d/preflight_readonly.py`; evidencias en
    `C:\ControlFarmacias\evidencias_2az-d\`.
- **Backup y snapshot previos (READ_ONLY):**
  - `preflight_pre.json` (2026-10-07, SHA-256
    `2908b8e016cb7345cdca9662f9f71b19876f094a0759e13d2dc13d671194c8d3`);
  - base del postcheck: `preflight_predespliegue.json` (2026-10-08 07:15 UTC, SHA-256
    `da8bd03c5e8d1ed7fcc8996f5c666b394062b40d257de2489d63b208ca5ad900`), con definiciones, ACL,
    privilegios por defecto, `cf_configuracion` completa y huellas por fila de 9 tablas sobre columnas
    declaradas antes de ejecutar.
  - Antes del despliegue, los objetos del alcance eran idénticos a la referencia local 19.
- **Postcheck** (`comparacion_postcheck.json`, POSTCHECK_OK):
  - (1) solo cambiaron `cf_configuracion`, `cf_persistir_conciliacion` y la nueva
    `cf_enriquecer_factura`;
  - (2) los tres son iguales a la referencia local 20;
  - (3) todo lo demás, idéntico.
  - Privilegios por defecto sin cambios.
  - `cf_configuracion`: suelo 0,05, por_albarán 0,01, tope 0,50; el resto sin cambios.
  - Huellas de las 9 tablas idénticas.
  - Flags `f|f|f|{PIO}`; workers, locks y claims a 0.
- **Prueba funcional READ_ONLY** (`SET LOCAL ROLE`):
  - `service_role` lee la configuración con los parámetros R11;
  - `anon` recibe «permission denied» al ejecutar `cf_enriquecer_factura`;
  - ambas funciones tienen EXECUTE solo para `service_role`.
- **Nada se concilió ni se enriqueció.** 08007971 sigue pendiente de un hito posterior.
- **Auditoría READ_ONLY de las 13 conciliaciones** (informativa):
  - ningún detalle casa por PVP con número distinto, así que D11 no afecta a ninguna conciliación
    existente;
  - las conciliaciones vigentes no comparten ningún albarán (D12: 0);
  - las 7 vigentes CONCILIADA siguen CONCILIADA al simularlas con D11 y R11.
  - La métrica automática marcó 08009277 como afectada por D12, pero es un falso positivo: cuenta su
    intento previo, no vigente. **Corrección de la métrica: hito posterior.**
- **08B96275:**
  - ya está en `Supabase.albaranes`: IdContador 293646, SAFA (`id_proveedor` `0002 `), PUC 6,51,
    PVP 0,00, importado en la sincronización del 2026-10-06;
  - su fecha es **05/06/2026**, frente al 11/06 que figura en el PDF; queda dentro de la ventana de
    ±15 días.
- **Deuda conocida aceptada por Pio:** `rls_auto_enable()`.
  - Función de plataforma Supabase: *event trigger* `ensure_rls` que activa automáticamente RLS en
    tablas nuevas de `public`.
  - SECURITY DEFINER, propietario `postgres`, EXECUTE para PUBLIC, `anon` y `authenticated`.
  - Figuraba en el inventario del 2AW y quedó fuera del alcance del 2AX.
  - También hay dos índices extra en `albaranes` (por `fecha` y por `id_proveedor`): deriva del
    baseline.
- **Logs de las noches con el código `8e6bace` en disco:**
  - 06/10 y 07/10: código de salida 0;
  - sin `permission denied` ni 42501;
  - albaranes nuevos: 38 y 43.
  - Las tareas nocturnas no importan ningún módulo cambiado en el 2AZ.
- **Primera ejecución nocturna con la 20 en producción** (2026-10-08, 21:00 importación y 21:30
  sincronización): revisada por Pio el 2026-10-09, **OK** (código de salida 0, sin `permission
  denied` ni 42501, filas nuevas coherentes). Fuente: confirmación de Pio en el Hito 2BA; no
  revalidado por Claude.

### Hito 2AZ: Alliance completa, tolerancia proporcional y enriquecimiento (certificado en local; desplegado en el 2AZ-D)

`CONFIRMADO POR TEST` (PostgreSQL 17 local), 2026-10-06/07. **Producción no tocada:** solo lecturas
READ_ONLY para diagnósticos. Reglas R10–R14 y D11 en `REGLAS_CRITICAS.md`; diseño en
`pruebas/auditoria_2az/DISENO.md`; evidencias fuera del repositorio en
`C:\ControlFarmacias\evidencias_2az\`.

- **Código:**
  - adaptador Alliance 1.3.0 (R10, D8 y R14);
  - puente `multifactura-local-2`;
  - `buscar_candidato_albaran` con D11;
  - `ReglaTolerancia` (R11) en `conciliar_importes` y `WorkerConciliacion`;
  - `runtime_supabase/enriquecimiento.py` (R12) y `construir_worker_enriquecimiento_manual`.
- **Migración 20** `20_cf_alliance_tolerancia_enriquecimiento.sql` (+ rollback; generada por
  `pruebas/auditoria_2az/generar_migracion_20.py` desde el texto exacto de la 18):
  - parámetros R11 con check;
  - `cf_persistir_conciliacion` con validación y registro de R11;
  - nueva RPC `cf_enriquecer_factura` (SECURITY DEFINER, owner postgres, solo service_role).
  - Certificada en local; **desplegada en producción en el 2AZ-D (2026-10-08)**.
  - Rollback igual al esquema 19 (`pg_dump -s`).
  - Scripts ensayados completos en local: `desplegar_20.py` y `enriquecer_una_vez.py`.
- **Orden de despliegue (2AZ-D):** primero la 20 y después el código, sin conciliaciones entre medias.
- **Primer error operativo real detectado por la conciliación (08007501, Alliance, 6,51 €):**
  - el albarán 08B96275 (SAFA, 6,51 €; tipo COSTO TELEVENTA) faltaba en Farmatic por un error humano
    de entrada;
  - Pio lo registró en Farmatic el 2026-10-06 y llegará a Supabase con la sincronización nocturna;
  - el volcado READ_ONLY del 2026-10-06 18:05 UTC no lo contiene, así que el banco da 08007501 APTA
    pero no conciliada (DIFERENCIA, albarán sin casar);
  - **sin D11 el error habría quedado oculto**: la regla anterior casaba 08B96275 con 08B96475 (PUC
    2,09) por su PVP de 6,49.
  - **Pendiente para el próximo preflight con lectura de producción:** verificar READ_ONLY que
    08B96275 (o el número con que se registrara) existe en `Supabase.albaranes` con PUC 6,51 y
    proveedor SAFA. Solo informar.
- **Diagnósticos de la Fase 1** (READ_ONLY, 2026-10-06):
  - 1.1/1.2: filas COSTO TELEVENTA del corpus: 08B96275 (6,51) es mercancía; 08B79008 y 08B96274
    tienen importe 0,00 y son informativas. Ninguna está en Supabase.
  - 1.3: los 18,07 € de 08011733 se componen de 15,91 de `SERVICIO COVID19` 08D32860 (existe en
    Supabase con PUC 15,91), 2,11 de 08D28707 (ambiguo entre Q040658/2026 y 08M82343; sigue sin casar)
    y 0,05 de redondeos de 42 albaranes. Con R10 la diferencia baja a 2,16.
  - 1.4: Alliance imprime una única FECHA VENCIMIENTO por factura y ningún importe de vencimiento.
    Base de R14.
- **Banco 2AY con el código 2AZ** (comparación en `evidencias_2az\banco\comparacion_2ay_2az.json`):
  - facturas Alliance aptas: 35 → 42 (las 5 previstas por 2AU, más 08007501 y 08011733 por la R10
    ampliada);
  - conciliadas con R11: 26 de 47; 08010887 sigue CONCILIADA por el suelo.
  - **D11 cambia el emparejamiento de 11 facturas.** Antes, muchas líneas casaban por PVP con número
    distinto, casi siempre con albaranes ajenos (p. ej. 08008835 / 08C40230 ↔ 08M35806). D11 las
    elimina, y 08008835 pasa de CONCILIADA a DIFERENCIA de 18,76.
- **Defecto previo registrado (D12; corregido en el Hito 2BA con R15; 21 desplegada en el 2BA-D):** `buscar_candidato_albaran` no tiene exclusividad,
  y un mismo albarán de Farmatic puede casarse con varias líneas o facturas. D11 lo hace más visible
  (p. ej. Q039707/2026 en 08006568; 08M39484 entre 08008427 y 08008430). Hito propio.
- **Hitos futuros registrados (NO implementados):**
  - a) cierre manual de conciliación con justificación de Pio para facturas en
    `REVISION_CONCILIACION`, sin alterar albaranes ni importes, con provenance e historial;
  - b) informe periódico de «albaranes facturados no encontrados en Farmatic» por proveedor y
    periodo;
  - c) hito COFARES con la clasificación de Pio (en `REGLAS_CRITICAS.md`).
- **Suites (2AZ, `--basetemp`, MOSTRADOR\Usuari):**
  - 1612 passed sin `pg17_local` (incluye 36 tests nuevos del 2AZ);
  - banco 2AY: 13 passed;
  - `pg17_local` antes del commit: 104 passed, más el ensayo del despliegue de la 20, que exige verificar
    el SHA contra el commit y por eso se ejecuta sobre el commit del hito (resultado en el informe
    del 2AZ).
  - Tests existentes actualizados por cambio de contrato, cada uno con su justificación:
    - versión Alliance 1.3.0;
    - vencimientos con importe por R14;
    - 08007971 apta por R10;
    - lista de migraciones;
    - payloads del simulador con tolerancia R11;
    - ensayo 2AT con la 20 aplicada;
    - expectativas del parche 2AU.
- **Incidente de permisos del 2AZ interrumpido** (2026-10-06): una orden que figuraba como rechazada
  llegó a ejecutarse (cambio sin commit en `multifactura.py`; guardado y revertido). Documentado en
  `evidencias_2az\incidente_permisos.md`. Sin efecto en producción.

### Evolución histórica útil

- La certificación 2AJ del 2026-09-22 registró 141 PDF omitidos y 138 documentos
  PIO. La 2AK conservó 138 documentos, 7 facturas, 7 normalizaciones,
  12 conciliaciones, 0 workers y 0 locks. `HISTÓRICO`; fue superada por la captura
  del Hito 0.1.
- La certificación 2AH del 2026-09-22 registró 43 albaranes nuevos y máximo
  `IdContador` 291852. `HISTÓRICO`; fue superada por la evidencia indicada arriba.

## Versiones y certificación

- Migración anterior desplegada: `17_cf_replay_y_fallos_no_bloqueantes.sql`,
  reglas R1–R4 (ver `REGLAS_CRITICAS.md`). `CONFIRMADO EN PRODUCCIÓN` (Hito 2AS,
  aplicada 2026-09-25 14:08:29–14:08:30 UTC, una transacción, project ref
  `vklaiuytvegkelgyspxc`, SQL normalizado a LF con SHA-256
  `6e7e8f78bd3f45df727392e7601dff6007e19cca2384525c80330efc37698b63`, con
  confirmación expresa de Pio). Backup previo READ_ONLY fuera del repo con SHA-256
  `c91e893a01888fd6845603ae5c411b61fa28d1e609cccf92f38a02198da77cdf`.
  Parámetros R3 en `cf_configuracion`: `normalizacion_max_intentos=4`,
  `normalizacion_backoff={1 h, 6 h, 24 h}`. Postcheck: definiciones iguales a la
  referencia local 17 (LF), selector idéntico, anon/authenticated sin EXECUTE en
  las funciones de la 17 (se retiró el EXECUTE de `authenticated` sobre
  `cf_solicitar_reprocesado`), conteos, estados y huellas de facturas idénticos;
  la huella de `normalizacion_ejecuciones` solo cambia por la columna nueva
  `clase_fallo` (nula en las 7 filas). Anterior: `16_cf_worker_manual_one_shot.sql`
  (2AN, 2026-09-24).
- El Python de 2AR (envío de `p_clase_fallo`) exige la migración 17; para
  revertir, primero el código y después el rollback SQL (requiere confirmación
  de Pio).
- Migración anterior desplegada: `18_cf_conciliacion_manual_atomica.sql`
  (+ `.rollback.sql`), reglas R5–R9 y D-A/D-B (ver `REGLAS_CRITICAS.md`).
  `CONFIRMADO EN PRODUCCIÓN` (Hito 2AW, aplicada 2026-09-28
  16:09:28–16:09:29 UTC, una transacción con 8 precondiciones, project ref
  `vklaiuytvegkelgyspxc`, SQL de `e546e6b` normalizado a LF con SHA-256
  `d4832f42b756f6b89fc8fd8b2f0a4409bc4ccd044730e9cf69f90baccc44878f`, con
  confirmación expresa de Pio). Backup previo READ_ONLY fuera del repo
  (`backup_pre_2aw.json`) con SHA-256
  `a900abffd19af98c0973d647b903b4035775cb9d6e42091ee2e96df410eaca15`.
  Parámetros en `cf_configuracion`: `conciliacion_max_intentos=4`,
  `conciliacion_backoff={1 h, 6 h, 24 h}`; tolerancia sin cambios (0,05).
  Postcheck: definiciones, propiedades, checks, índices, columnas y vistas
  iguales a la referencia local 18 (LF); selector idéntico al de la 14 salvo el
  interruptor; anon/authenticated/PUBLIC sin EXECUTE en ninguna función de la 18
  (se retiró el EXECUTE de `authenticated` sobre
  `cf_solicitar_reintento_conciliacion`); núcleo sin `service_role`; huellas de
  las 12 facturas, 12 conciliaciones, 749 detalles, configuración e historial
  idénticas; flags, workers, locks y claims sin cambios. Diseño en
  `pruebas/auditoria_2av/DISENO.md`. El Python de conciliación exige la 18.
  Primera y única conciliación ejecutada con la 18: Hito 2AT rev2 (ver "Primera
  conciliación manual one-shot productiva"); sin worker automático ni cambio de flags.
- **Rollback productivo de la 18** (solo con confirmación de Pio; primero el
  código, después el SQL): el rollback versionado deja
  `cf_solicitar_reintento_conciliacion` con EXECUTE solo para `authenticated`
  (estado del esquema versionado). En producción, antes de la 18, también tenía
  `service_role` (privilegios por defecto de Supabase). Tras el rollback hay que
  ejecutar además
  `grant execute on function public.cf_solicitar_reintento_conciliacion(uuid, text) to service_role;`
  para restaurar el ACL previo, guardado en `backup_pre_2aw.json`.
- **Migración más reciente desplegada: `21_cf_exclusividad_albaranes.sql`** (+ rollback).
  `CONFIRMADO EN PRODUCCIÓN` (Hito 2BA-D, 2026-10-19 15:50:22–15:50:23 UTC):
  - SHA-256 LF `f0a99416…bfcaca` (commit `a91ca22`);
  - backup previo `preflight_pre.json` (SHA-256 `92266084…8ab173`);
  - POSTCHECK_OK y FUNCIONAL_OK.
  - Detalle en «Hito 2BA-D»; reglas en «Hito 2BA».
  - **Rollback** (solo con confirmación de Pio): primero el código y después
    `21_cf_exclusividad_albaranes.rollback.sql`, que devuelve el esquema 20 (y elimina las reservas).
- Migración anterior desplegada: `20_cf_alliance_tolerancia_enriquecimiento.sql`
  (+ rollback). `CONFIRMADO EN PRODUCCIÓN` (Hito 2AZ-D, 2026-10-08 09:07:02–09:07:03 UTC):
  - SHA-256 LF `aa8f1d55…56a1f`;
  - backup previo `preflight_predespliegue.json` (SHA-256 `da8bd03c…5ad900`);
  - POSTCHECK_OK.
  - Detalle en «Hito 2AZ-D».
  - **Rollback** (solo con confirmación de Pio): primero el código y después
    `20_cf_alliance_tolerancia_enriquecimiento.rollback.sql`, que devuelve el esquema 19.
- Migración anterior desplegada: `19_cf_privilegios_minimos.sql`
  (+ `.rollback.sql`), privilegios mínimos. `CONFIRMADO EN PRODUCCIÓN` (Hito 2AX,
  aplicada 2026-09-29 07:07:45–07:07:46 UTC, una transacción con 8
  precondiciones, project ref `vklaiuytvegkelgyspxc`, SQL de `f9ff625` en LF con
  SHA-256 `3a923261419d3a85dbe786881f428c945833f9930c188266ece8d675b4a2cd93`,
  script `pruebas/auditoria_2ax/desplegar_19.py` de `a66ff4a` ensayado completo
  en local, con confirmación expresa de Pio). Backup previo READ_ONLY fuera del
  repo (`backup_pre_2ax.json`) con SHA-256
  `8f47c66bf98ee84e4938d1b8ce87788e840fea98ebe2c40bcb1164015cba4371`; foto previa
  inmediata `inventario_predespliegue.json` (SHA-256 `4d12cd95…`). Un primer
  intento el 2026-09-28 se revirtió sin cambios (defecto del script, corregido).
  **Matriz resultante** (tablas, vistas y secuencias de `public`): PUBLIC, anon y
  authenticated sin ningún privilegio; `service_role` solo `SELECT, INSERT` en
  `documentos_facturas` y `albaranes`, y `SELECT` en `facturas`,
  `cf_configuracion`, `proveedores`, `facturas_movimientos`,
  `facturas_albaranes_extraidos` y `normalizacion_ejecuciones`; nada en el resto
  (se escribe vía RPC SECURITY DEFINER). `cf_validar_factura` y
  `cf_desvalidar_factura`: solo el propietario. RLS activado en las 16 tablas;
  políticas y storage sin cambios (bucket `facturas-pdf` privado, sin políticas
  en `storage.objects`). Privilegios por defecto de `postgres`: solo `postgres` y
  `service_role` en tablas, secuencias y funciones de `public`, y sin EXECUTE
  global a PUBLIC en funciones. Postcheck: solo cambiaron los 24 objetos del
  alcance, iguales a la referencia local 19; huellas de facturas, conciliaciones,
  `documentos_facturas` y albaranes idénticas; `service_role` lee y ejecuta
  `cf_evaluar_elegibilidad_conciliacion`; anon recibe `permission denied`.
- **Verificación de la primera ejecución nocturna con la 19** (2026-09-29, 21:00
  importación y 21:30 sincronización; revisar el 2026-09-30 por la mañana):
  1. Task Scheduler (solo lectura): "ControlFarmacias - Importar facturas" y
     "Sincronización ControlFarmacias" con Last Run Time de la noche y Last Run
     Result = 0.
  2. `logs/automatizacion_facturas.log` y `logs/automatizacion_albaranes.log`:
     la ejecución de la noche sin `permission denied`, `42501` ni errores de
     Supabase; código de salida 0.
  3. READ_ONLY en Supabase: `documentos_facturas` y `albaranes` con filas nuevas
     (`fecha_importacion` de la noche) si hubo PDF o albaranes nuevos; el
     `IdContador` máximo coherente con el log de sincronización.
  4. Si falla por privilegios: con confirmación de Pio, aplicar
     `sql/migrations/19_cf_privilegios_minimos.rollback.sql` (restaura
     exactamente la matriz y los privilegios por defecto previos) y relanzar la
     tarea afectada manualmente. No aplica el ajuste manual de la 18: el rollback
     de la 19 no toca funciones de conciliación.
- Normalizador V2 declarado por el pipeline: `2.2.0`.
- Motor documental local declarado por el servicio: `0.5.0`.
- `OrquestadorExtraccionProductiva` no declara versión propia. V0.1.3 identifica
  una validación histórica del ejecutor; V0.2.12 pertenece al CLI externo `cf`.
- Recuento estático actual: 66 archivos que contienen funciones de test y 787
  funciones `test_*`. El árbol tiene además `tests/conftest.py`, por lo que un
  conteo bruto de archivos Python da 67. `CONFIRMADO POR CÓDIGO`, 2026-09-24.
- Pytest parametriza casos: el número de funciones no equivale al número de casos
  ejecutados.
- Seguridad Farmatic: `23 passed`; finalidad: barreras de solo lectura y bypasses.
- Multifactura/RPC: `49 passed`; finalidad: firma, persistencia y workers asociados.
- Aislamiento logs/data: `3 passed`; finalidad: impedir escrituras productivas
  durante pytest.
- Suite de módulo: `216 passed`; finalidad: runtime Supabase, seguridad y
  aislamiento del módulo.
- Suite completa del Hito 0: `1058 passed`, `0 failed`, 53,54 s.
- Todos estos resultados son `CONFIRMADO POR CERTIFICACIÓN ARCHIVADA` del Hito 0,
  2026-09-24. Los focales se solapan y no se suman entre sí ni se comparan con los
  66 archivos como si fueran la misma suite.

## Producción durante el Hito 0

No se tocó Farmatic ni Supabase productivo; no se cambiaron flags, no se activaron
workers y no se modificó Task Scheduler. Estado: `CONFIRMADO POR CERTIFICACIÓN
ARCHIVADA` mediante el registro/certificación del Hito 0, 2026-09-24; no revalidado
mediante consulta remota posterior.

## Límites conocidos

- Riesgo residual aceptado por Pio (Hito 2AX, 2026-09-28): los privilegios por
  defecto de `supabase_admin` sobre `public` (ALL en tablas, secuencias y
  funciones para anon, authenticated y service_role) no se pueden alterar desde
  `postgres` (no es miembro de `supabase_admin` ni superusuario). Un objeto que
  cree `supabase_admin` en `public` nacería abierto. Hoy no hay ninguno.
  **Comprobación obligatoria en todo preflight futuro:** ningún objeto de
  `public` (tablas, vistas, secuencias, funciones) con propietario distinto de
  `postgres`; si aparece alguno → PARAR.
- Deuda del baseline (Hito 2AX, aceptada por Pio): 4 funciones fuera del alcance
  de la 19 tienen en producción privilegios explícitos que el baseline local no
  reproduce (privilegios por defecto de Supabase): `cf_historial_append_only()`,
  `cf_set_updated_at()` y `cf_resultado_conciliacion(numeric,numeric)` con
  EXECUTE explícito para PUBLIC, anon, authenticated y service_role; y
  `cf_solicitar_reprocesado(uuid,text)` con EXECUTE para service_role.
  Idénticas antes y después de la 19. Se suma a la deuda de baseline de 2AS.

- Deuda aceptada por Pio (Hito 2AS, 2026-09-25; `CONFIRMADO EN PRODUCCIÓN` por
  preflight READ_ONLY): el baseline local (`sql/staging/00`) no reproduce los
  privilegios por defecto de Supabase (`pg_default_acl` concede EXECUTE a
  `anon`, `authenticated` y `service_role` sobre funciones nuevas de `public`)
  ni la columna productiva `documentos_facturas.observaciones`. Consecuencia
  observada: `service_role` tiene EXECUTE sobre `cf_solicitar_reprocesado` en
  producción y no en local. `PENDIENTE`: alinear el baseline local con el
  esquema y privilegios de Supabase en un hito propio.
- Deuda registrada por Pio (Hito 2AS, 2026-09-25): `estado_persistencia=PENDIENTE`
  desfasado en los 4 documentos `NORMALIZADA` persistidos por la vía directa
  (`cf_persistir_normalizacion`) antes de la migración 15: Logista `0387e00a`,
  COFARES `fcbd0d02` y HEFAME `1c37b4d1`/`ee494032`. No son reclamables
  (`NORMALIZADA`). Corrección en hito propio; no se modifican ahora.
- Deuda registrada por Pio (Hito 2AO rev3, 2026-09-25; `CONFIRMADO EN
  PRODUCCIÓN`), hito propio, **no implementada**:
  - la persistencia (`cf_persistir_normalizacion`, migración 17) solo admite
    `FACTURA`, `ABONO`, `FACTURA_RECTIFICATIVA` y `OTRO`; `FACTURA_DUPLICADO` se
    guarda como `tipo_documento=OTRO` (el valor original queda en
    `datos_extraidos.tipo_documento`). Pendiente: mapear `FACTURA_DUPLICADO` →
    `FACTURA`;
  - reclasificar las facturas afectadas: Alliance 08009277/08009278/08009279 y
    08007969/08007970/08007971/08007972/08007973 (y revisar COFARES 5460017198,
    `FACTURA_RECTIFICATIVA_CONDICIONES_COMERCIALES` → `OTRO`);
  - `categoria` de 08009277 (y 08007969) es `OTRO` porque la persistencia solo
    mapea `MERCANCIA`/`SERVICIOS` y la naturaleza es `MIXTA`. La elegibilidad
    (`cf_evaluar_elegibilidad_conciliacion`) y el claim de conciliación no usan
    `tipo_documento` ni `categoria` (usan `datos_extraidos.naturaleza_principal`),
    pero la búsqueda de albaranes sí usa `categoria`:
    `runtime_supabase/repositorios.py:322-326` busca albaranes si
    `categoria = MERCANCIA` o la naturaleza es `MIXTA`, y movimientos de servicio
    si `categoria = CUOTA_SERVICIO` o `MIXTA`; en otro caso lanza
    `TIPO_DOCUMENTAL_NO_DEMOSTRADO`. Hoy no afecta porque `OTRO` solo sale de
    `MIXTA`, pero una categoría distinta de `MERCANCIA`/`CUOTA_SERVICIO` sin
    naturaleza `MIXTA` quedaría fuera de conciliación.
- Deuda para el **Hito 2AU** (diagnóstico de 08007971 en el Hito 2AO rev3,
  2026-09-25; `CONFIRMADO POR CÓDIGO` y por extracción local READ_ONLY del
  mirror). **No implementada**:
  - **Tipos de pedido Alliance no certificados.** El adaptador
    (`motor_local/adaptadores/alliance.py:21-27`,
    `TIPOS_PEDIDO_MERCANCIA_ALLIANCE`) solo certifica `NORMAL ACUSTICO`,
    `NETOS PLUS`, `PLATAFORMA 360`, `COSTO LABORAT.` y `ECOCEUTICS`; cualquier
    otro tipo se clasifica `NO_DEMOSTRABLE` y no se promueve a albarán (falla
    cerrado; el extractor lee bien número, fecha, base, total, sentido y rol).
    Alcance medido: facturas Alliance persistidas 8, afectada 1 (08007971:
    3 filas `DIRECTO`). Cola: 9 documentos Alliance reconocidos (35 facturas),
    7 documentos / 9 facturas con 14 filas no promovidas: `ENCARGO VACUNAS` 4
    (08008834, 08009716, 08010461, 08010885), `COSTO TELEVENTA` 3 (08006570,
    08007501 ×2), `DIRECTO` 2 (08006570, 08010887), `MIS RESERVAS` 2
    (08010085), `ABONO ECOCEUTICS` 2 (08006571) y `TELEVENTA 2` 1 (08006570).
    Cota inferior: de 137 documentos en cola, 71 sin layout reconocido, 16 con
    error de extracción local y 1 ausente del mirror.
    Clasificación de Pio (registrada tal cual):
    - `DIRECTO`, `ENCARGO VACUNAS`, `MIS RESERVAS`, `TELEVENTA 2`: MERCANCÍA.
      Certificables solo con albarán coincidente en `Supabase.albaranes` por
      fecha e importe.
    - `COSTO TELEVENTA`: CARGO DE SERVICIO de Alliance, NO mercancía. No se
      cruza con albaranes; es movimiento de servicio.
    - `ABONO ECOCEUTICS`: ABONO, NO cargo. Tratamiento (devolución cruzable en
      Farmatic o abono comercial sin albarán) a determinar en 2AU con evidencia.
  - **Motivo engañoso de incidencia** en `alliance.py:337-342`:
    `CANDIDATO_ALBARAN_NO_PROMOVIDO` declara
    `FALTA_EVIDENCIA_POSITIVA_DE_ROL_O_SEGMENTACION` aunque rol y segmentación
    son correctos. Sustituir por `TIPO_PEDIDO_NO_CERTIFICADO` con el tipo
    encontrado.
  - **08007971 persistida sin albaranes** (3 `DIRECTO`: 08C18299, 08M24229,
    08M25574; en conciliación quedaría `NO_APTA` `FALTAN_ALBARANES_MERCANCIA`).
    Requiere un camino de enriquecimiento, no reprocesado: la identidad
    económica bloquearía las 5 facturas del documento como duplicadas o el
    reprocesado sería un replay.
  - Evidencia de conciliación: los 3 albaranes existen en `albaranes` (SAFA,
    `PENDIENTE`); 08C18299 figura en Farmatic como `Q039904/2026` (numeración
    distinta). La sincronización no filtra por estado de facturación
    (`IdContador > último`). Simulado con `buscar_candidato_albaran`: los 3
    darían `MATCH_UNICO` (08C18299 por proveedor + fecha + importe con número
    `DIFERENTE`; los otros dos por número exacto).
  - Pendiente de verificar en 2AU: si la conciliación actual descuenta
    movimientos de servicio y abonos al calcular el importe explicado.
  - Aplazado (no necesario ahora): relación en Farmatic entre `Q039904/2026` y
    08C18299; requiere la identidad `ControlFarmaciasRO` (la sesión ordinaria
    `MOSTRADOR\Usuari` es rechazada por la barrera de solo lectura).

- Hallazgos del Hito 2AV (2026-09-25; `CONFIRMADO POR TEST` en PostgreSQL 17
  local con el PDF real del 2AO, sin producción), **no corregidos**:
  - Deuda de tolerancia (decisión de Pio D-C en 2AW: NO tocar; se trata con la
    deuda 2AU):
    08007969 (MIXTA) sale `NO_APTA` `TOTAL_NO_EXPLICADO`: albaranes extraídos
    13.020,88 + movimientos −213,78 = 12.807,10 frente a un total de 12.807,17
    (0,07 > tolerancia 0,05). Con 08007971 (sin albaranes, deuda 2AU), 2 de las
    5 facturas del 2AO no son conciliables hoy; aptas: 08007970, 08007972 y
    08007973.
  - 08007970 con albaranes operacionales sintéticos (número, fecha y PUC del
    PDF): `CONCILIADA`, explicado 2.356,68, diferencia −0,04, 71 albaranes 1:1.
    El resultado productivo dependerá de los importes reales de Farmatic.
  - Resuelto en el Hito 2AW (D-A): un resultado `DIFERENCIA` consume intento con
    backoff y al 4.º pasa a `REVISION_CONCILIACION`.

- La extracción completa no está certificada para cualquier layout posible.
- La barrera documental de identidad/farmacia no está demostrada como universal en
  todos los ensambladores históricos.
- Permanecen gaps funcionales registrados para el sentido del descuento por pronto
  pago de COFARES y la relación de abonos de DERMOFARM con la factura del mes
  siguiente.
- SAFA no tiene extractor local propio. Beiersdorf está sin extractor implementado.
  Esto no impide que SAFA, Alliance y Cencora se canonicalicen dentro del grupo
  funcional autorizado de conciliación: extracción y conciliación son niveles
  distintos.
- Conciliación bancaria, Norma 43, Telegram e interfaz web no están implementados.
