# Contexto canónico de ControlFarmacias

Actualizado: 2026-09-24. Repositorio operativo: `C:\ControlFarmacias\Programa`.

Este documento es la fuente de verdad compartida por Claude Code y Codex. Si el
código o una certificación reproducible lo contradicen, se debe actualizar este
archivo en el mismo cambio. Las evidencias históricas de `pruebas/` no sustituyen
el estado actual del código.

## Reglas no negociables

- Farmatic/SQL Server es estrictamente de solo lectura. Nunca ejecutar escrituras,
  migraciones, DDL, procedimientos ni consultas no demostrablemente `SELECT/WITH`.
- No tocar Supabase productivo, flags, workers, Task Scheduler ni documentos reales
  sin preflight, alcance explícito y confirmación de Pio.
- La farmacia productiva autorizada es PIO. RITA permanece bloqueada.
- Los flags por defecto son `normalizacion_automatica=false`,
  `conciliacion_automatica=false` y `luna_habilitada=false`.
- `MANUAL_ONE_SHOT` reclama como máximo un documento y no permite preselección.
- Ante duda de completitud, identidad, farmacia o permisos, el sistema falla cerrado.

## Arquitectura vigente

- `src/facturas/normalizador_v2`: contrato, validación, segmentación y normalización.
- `src/facturas/motor_local`: extractores locales por proveedor y evidencia.
- `src/facturas/runtime_supabase`: repositorios, multifactura, workers y conciliación.
- `src/database` y `src/sql_explorer`: acceso y barreras de solo lectura a Farmatic.
- `src/supabase_client`: integración histórica de albaranes/documentos.
- `sql/migrations/16_cf_worker_manual_one_shot.sql`: migración más reciente versionada.

## Barreras Farmatic

La conexión usa `ApplicationIntent=ReadOnly`, login dedicado
`MOSTRADOR\ControlFarmaciasRO`, `db_datareader`, `autocommit=False` y certificación
de ausencia de permisos de escritura/DDL/EXECUTE/CONTROL. El cursor valida
`SELECT/WITH`; `commit`, `executemany` y accesos nativos equivalentes se bloquean.
No hace falta conectar a Farmatic para los tests unitarios.

## Contrato multifactura y migración 16

La ruta vigente llama a
`cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)` con
`p_disparador` explícito. Migración 16 revoca `service_role` sobre la firma antigua
de seis parámetros y concede la firma de siete. Valores admitidos:
`AUTOMATICO`, `REPROCESADO`, `MANUAL_ONE_SHOT`.

## Pruebas y datos locales

`pytest` debe redirigir logs e índices de ingesta a una raíz temporal mediante
`CONTROLFARMACIAS_LOG_DIR` y `CONTROLFARMACIAS_DATA_DIR`. Nunca debe escribir en
`logs/` o `data/` productivos ni acceder a Farmatic/Supabase reales.

## Estado Git al iniciar Hito 0

El HEAD auditado era `e18acf072dd1baae83ecf0d022986168e5f73b0e`, 18 commits
por delante de `origin/main` (`135e45b`). Se aseguró una copia remota exacta en
`backup/hito-0-preparacion-2026-09-24` antes de modificar código.
