# Estado actual

Actualizado: 2026-09-24.

## Git y respaldo

- Repositorio: `C:\ControlFarmacias\Programa`.
- Rama operativa: `main`.
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

## Operación vigente

- PIO es la única farmacia autorizada. RITA está bloqueada.
- Valores seguros por defecto: `normalizacion_automatica=false`,
  `conciliacion_automatica=false`, `luna_habilitada=false`.
- Estos valores describen el contrato y la última certificación. El estado remoto
  vivo no se presume sin preflight productivo autorizado.
- La autoridad productiva de todos los extractores locales es `false`.
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

### Evolución histórica útil

- La certificación 2AJ del 2026-09-22 registró 141 PDF omitidos y 138 documentos
  PIO. La 2AK conservó 138 documentos, 7 facturas, 7 normalizaciones,
  12 conciliaciones, 0 workers y 0 locks. `HISTÓRICO`; fue superada por la captura
  del Hito 0.1.
- La certificación 2AH del 2026-09-22 registró 43 albaranes nuevos y máximo
  `IdContador` 291852. `HISTÓRICO`; fue superada por la evidencia indicada arriba.

## Versiones y certificación

- Migración más reciente: `16_cf_worker_manual_one_shot.sql`.
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
