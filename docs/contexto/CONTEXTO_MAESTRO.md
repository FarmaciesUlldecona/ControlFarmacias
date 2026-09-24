# Contexto maestro de ControlFarmacias

Actualizado: 2026-09-24. Repositorio operativo:
`C:\ControlFarmacias\Programa`.

ControlFarmacias ingiere y trata documentos de compra de farmacia. Su flujo
conceptual es:

`factura -> extracción -> normalización -> conciliación -> Supabase`

Este documento es la puerta de entrada técnica compartida por Claude Code, Codex y
futuros agentes. El estado vigente está en [ESTADO_ACTUAL.md](ESTADO_ACTUAL.md) y
las restricciones y reglas confirmadas están en
[REGLAS_CRITICAS.md](REGLAS_CRITICAS.md).

## Orden de autoridad

Cuando dos fuentes discrepen, se aplica este orden:

1. restricciones absolutas;
2. estado productivo certificado;
3. reglas funcionales confirmadas;
4. código actual;
5. tests actuales;
6. documentación vigente;
7. histórico.

Una certificación reproducible o el código vigente que contradigan este contexto
obligan a actualizar los documentos canónicos en el mismo cambio. Los artefactos de
`pruebas/` son evidencia histórica y no sustituyen el estado actual.

## Restricciones absolutas

- Farmatic/SQL Server es estrictamente de solo lectura. Solo se admiten consultas
  demostrablemente `SELECT/WITH`; quedan prohibidos escritura, DDL, procedimientos
  con efectos laterales y cualquier bypass de los wrappers.
- No tocar Supabase productivo, flags, workers, Task Scheduler ni documentos reales
  sin preflight, alcance explícito y confirmación de Pio.
- La única farmacia productiva autorizada es PIO. RITA permanece bloqueada.
- Ante duda de completitud, identidad, farmacia, evidencia o permisos, el sistema
  falla cerrado y deriva a revisión.
- Los extractores locales no tienen autoridad productiva. Su registro o ejecución
  shadow no autoriza aplicar su salida.

## Arquitectura vigente

- `src/facturas/normalizador_v2`: contrato, validación, segmentación,
  consolidación y normalización.
- `src/facturas/motor_local`: extracción local, adaptadores por proveedor,
  evidencia, shadow y autoridad local.
- `src/facturas/runtime_supabase`: repositorios, extracción productiva,
  multifactura, workers y conciliación.
- `src/database` y `src/sql_explorer`: acceso y barreras de solo lectura a
  Farmatic.
- `src/supabase_client`: integración histórica de albaranes y documentos.
- `sql/migrations/16_cf_worker_manual_one_shot.sql`: migración más reciente
  versionada.

El orquestador productivo de extracción es
`OrquestadorExtraccionProductiva`. Aplica, por orden, extractor específico, local
genérico, OCR local y Luna solo para campos pendientes. Ninguna etapa puede
sobrescribir campos ya resueltos. Luna permanece deshabilitada por defecto. La
referencia V0.1.3 corresponde a una validación histórica del ejecutor, no a una
versión declarada de esta clase.

## Seguridad de Farmatic

La conexión certificada usa `ApplicationIntent=ReadOnly`, el login dedicado
`MOSTRADOR\ControlFarmaciasRO`, rol `db_datareader` y `autocommit=False`. Los
wrappers validan `SELECT/WITH` y bloquean `execute` nativo, `executemany`, `commit`
y accesos indirectos equivalentes. Los tests unitarios no necesitan conectarse a
Farmatic.

## Persistencia multifactura

La ruta vigente usa
`cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)` con
`p_disparador` explícito. La migración 16 revoca `service_role` sobre la firma
antigua de seis parámetros y concede la firma de siete. Los disparadores admitidos
son `AUTOMATICO`, `REPROCESADO` y `MANUAL_ONE_SHOT`.

`MANUAL_ONE_SHOT` reclama como máximo un documento, no permite preselección y no
activa por sí solo la automatización general.

## Pruebas

Durante pytest, `CONTROLFARMACIAS_LOG_DIR` y `CONTROLFARMACIAS_DATA_DIR` deben
apuntar a una raíz temporal. Ningún test debe escribir en `logs/` o `data/`
productivos ni acceder a Farmatic o Supabase reales.

La última certificación reproducible documentada del Hito 0 fue `1058 passed`
en 53,54 s, sin cambios en `logs/` ni `data/` y sin conexiones productivas.
