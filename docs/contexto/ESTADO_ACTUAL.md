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

### Evolución histórica útil

- La certificación 2AJ del 2026-09-22 registró 141 PDF omitidos y 138 documentos
  PIO. La 2AK conservó 138 documentos, 7 facturas, 7 normalizaciones,
  12 conciliaciones, 0 workers y 0 locks. `HISTÓRICO`; fue superada por la captura
  del Hito 0.1.
- La certificación 2AH del 2026-09-22 registró 43 albaranes nuevos y máximo
  `IdContador` 291852. `HISTÓRICO`; fue superada por la evidencia indicada arriba.

## Versiones y certificación

- Migración más reciente desplegada: `17_cf_replay_y_fallos_no_bloqueantes.sql`,
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
    mapea `MERCANCIA`/`SERVICIOS` y la naturaleza es `MIXTA`. Ni la elegibilidad
    ni el claim de conciliación usan `tipo_documento` ni `categoria` (usan
    `datos_extraidos.naturaleza_principal`), por lo que no afecta a conciliar.

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
