# Estado actual

Actualizado: 2026-09-24.

## Git y respaldo

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

### Hito 2AZ: Alliance completa, tolerancia proporcional y enriquecimiento (certificado en local, NO desplegado)

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
  - **Certificada en local, NO desplegada.**
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
- **Defecto previo registrado (D12, NO corregido):** `buscar_candidato_albaran` no tiene exclusividad,
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
- Migración más reciente desplegada: `19_cf_privilegios_minimos.sql`
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
