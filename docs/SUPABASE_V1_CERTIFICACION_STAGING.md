# Certificación PostgreSQL de Supabase V1

## Recertificación 2F.1 local aislada

La recertificación 2F.1 usa `pruebas/certificacion_2f1.py` mediante Docker local
sin red ni puertos publicados, sin URL y con datos sintéticos. Ejecuta dos ciclos
completos, casos A–I y concurrencia real de dos sesiones. Véase el informe
[SUPABASE_V1_ESTADO_LECTURA_2F1.md](SUPABASE_V1_ESTADO_LECTURA_2F1.md).
La secuencia incluye 08b antes de 09. Los resultados SELECT de pre/postflight
deben evaluarse: finalizar sin error SQL no demuestra que todos los guards pasen.

Este procedimiento se ejecuta exclusivamente sobre una base PostgreSQL desechable y sin datos reales. No usar `SUPABASE_URL`, `SUPABASE_KEY` ni ninguna URL del proyecto productivo.

## Precondiciones

1. Disponer de PostgreSQL compatible con Supabase y del cliente `psql`.
2. Crear una base vacía destinada únicamente a esta prueba.
3. Definir `STAGING_DATABASE_URL` con la conexión de esa base. No guardar la URL en el repositorio.
4. Confirmar manualmente que host, proyecto y nombre de base no corresponden a producción.
5. Trabajar desde la raíz del repositorio.

En PowerShell:

```powershell
if (-not $env:STAGING_DATABASE_URL) { throw 'Falta STAGING_DATABASE_URL' }
if ($env:STAGING_DATABASE_URL -match 'SUPABASE_URL|controlfarmacias-prod|production|produccion') {
    throw 'La URL parece productiva; certificación abortada'
}
```

## Secuencia determinista

Todos los comandos usan `ON_ERROR_STOP`; el primer error debe detener el proceso.
La secuencia completa debe ejecutarse dos veces, cada vez sobre una base nueva y vacia.

```powershell
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/staging/00_baseline_controlfarmacias.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/migrations/06b_cf_integridad_albaranes.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/preflight/postflight_06b_integridad_albaranes.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/migrations/07_cf_proveedores_config.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/migrations/08_cf_core_facturas.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/migrations/08b_cf_estado_lectura_compatibilidad.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/migrations/09_cf_normalizacion_runtime.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/migrations/10_cf_movimientos_incidencias_historial.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/migrations/11_cf_conciliacion.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/migrations/12_cf_views_rls_rpc.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/migrations/14_cf_claim_conciliacion_v2.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/staging/01_seed_controlfarmacias.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/staging/02_validar_migraciones.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/staging/03_test_rpc_normalizacion.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/staging/04_test_concurrencia_idempotencia.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/staging/05_test_conciliacion.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/staging/07_test_claim_conciliacion_v2.sql
psql $env:STAGING_DATABASE_URL -X -v ON_ERROR_STOP=1 -f sql/staging/06_test_backfill_pio.sql
```

`06_test_backfill_pio.sql` comprueba primero el guard bloqueado, prueba un manifiesto incorrecto, carga una atestación sintética correcta y solo entonces incluye la migración 13. No aplicar `13_cf_backfill_compatibilidad.sql` por separado en esta certificación.

Antes de los ciclos completos, certificar `06b_cf_integridad_albaranes.sql` en cuatro
bases o esquemas desechables: ausencia de UNIQUE sin duplicados, segunda ejecucion,
UNIQUE equivalente con otro nombre y duplicado real. El ultimo caso debe abortar sin
borrar, fusionar ni modificar ninguna fila.

## Prueba concurrente en dos sesiones

Preparar un documento PIO sintético con `estado_lectura='PENDIENTE'` y `reprocesar_solicitado_at=now()`. Abrir dos terminales conectadas a la misma base.

Sesión A:

```sql
begin;
select id from public.cf_reclamar_documento_normalizacion('sesion-a', 300);
-- Mantener abierta esta transacción.
```

Mientras A sigue abierta, sesión B:

```sql
begin;
select id from public.cf_reclamar_documento_normalizacion('sesion-b', 300);
commit;
```

La sesión B no debe bloquearse ni recibir el documento retenido por A. Terminar con `rollback;` en A. Repetir el mismo patrón con `cf_reclamar_factura_conciliacion`.

## Evidencias requeridas

Conservar fuera del repositorio:

- versión de PostgreSQL;
- salida y código de retorno individual de cada script;
- resultado de ambas sesiones concurrentes;
- conteos finales de documentos, facturas, ejecuciones e historial;
- confirmación de que RITA no fue modificada por el backfill;
- confirmación de que todos los datos utilizados eran sintéticos.

No conservar dumps, credenciales ni resultados productivos en el repositorio.

## Criterio de aprobación

El paquete queda certificado únicamente si:

- 06b reconoce una garantia equivalente o crea exactamente una sobre
  `(farmacia, id_contador)`, y bloquea cualquier duplicado real sin alterar datos;

- 07–12 se aplican secuencialmente sin error;
- todas las validaciones y pruebas devuelven sus marcadores `OK`;
- el error deliberado de persistencia deja cero filas parciales;
- la repetición de una clave idempotente no crea otra ejecución;
- el reprocesado crea una ejecución nueva y mantiene el historial;
- la segunda sesión no reclama el trabajo bloqueado;
- `0.0500` concilia y `0.0501` queda pendiente;
- 13 modifica solo PIO y no inventa, borra ni fusiona documentos.

## Destrucción

Finalizada la certificación, destruir la base o el proyecto desechable mediante el mecanismo aprobado por su propietario. No reutilizarla como staging permanente ni trasladar sus datos a producción.
