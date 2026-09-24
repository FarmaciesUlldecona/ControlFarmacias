# Hito 2P - despliegue productivo controlado migracion 15

Estado final: **MIGRACION_15_PRODUCTIVA_DESPLEGADA**.

## Destino y preflight

Proyecto cotejado con SUPABASE_URL y con snapshot productivo certificado 2N.
La conexion SQL exige TLS; las auditorias usan transacciones READ ONLY.
Proyecto anonimizado SHA256:
`d146ec026bdb2d42b8e27fcb57dc81ae6d8dd5dd4f090a7f0754535275e77b80`.

Preflight sin diferencias frente al cierre 2N en facturas, flags, conteos,
huellas, claim V2, restriccion, RLS, policies y grants. Migracion 15 ausente.
Workers Windows: 0 antes y despues, consultas CIM fuera del sandbox sin cambios
de permisos. Sesiones PostgreSQL worker/runtime: 0. Locks activos: 0/0.

## Despliegue

- Archivo exclusivo: `sql/migrations/15_cf_multifactura.sql`.
- SHA256: `aa28b84225f62f0337e71b3b869b6c1e6030f4a1d8a56f9a5eb787d2de60f8a3`.
- Revalidacion previa: dos ciclos PostgreSQL 17 locales, completos y correctos.
- Inicio UTC: 2026-09-16T17:40:14.587080+00:00.
- Fin UTC: 2026-09-16T17:40:15.078395+00:00.
- Resultado SQL: correcto. No se ejecutan migraciones anteriores.
- Snapshot y rollback preparados antes de escribir. Rollback NO ejecutado.

Se incorporan exclusivamente inventario_facturas, estado_persistencia, su CHECK
y tres funciones con sus permisos. Las 130 filas documentales conservan todos sus
campos anteriores; las columnas nuevas presentan [] y PENDIENTE por defecto.
No se ha realizado backfill ni se ha recalculado el estado de facturas historicas.

## Postflight y cierre READ ONLY

Definiciones exactas de funciones cotejadas con el SQL aplicado, incluidas
firmas, tipo de retorno, volatilidad, SECURITY DEFINER y search_path.

- `cf_componentes_identidad_factura(jsonb) -> text[]`.
- `cf_clave_economica_factura(jsonb) -> text`.
- `cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[]) -> uuid`.

Las tres tienen EXECUTE para service_role; anon/authenticated no tienen EXECUTE.
El ACL esperado solo conserva propietario postgres y service_role, sin PUBLIC.
RLS, policies y grants de tablas identicos. Todas las funciones anteriores,
incluidas las dos de migracion 14/claim V2, permanecen identicas.
Constraints/indices anteriores intactos; solo se incorpora el CHECK previsto.

El esquema conserva la FK documento_id y los UNIQUE compuestos que permiten N
facturas por documento. Inventario, estados y nueva RPC permiten persistencia
parcial con hermanas pendientes. Validacion productiva exclusivamente estructural:
no se ha llamado a la RPC de persistencia ni al claim y no se insertan datos de prueba.

| Tabla / concepto | Antes | Despues | Diferencia |
| --- | ---: | ---: | ---: |
| facturas | 2 | 2 | 0 |
| normalizacion_ejecuciones | 3 | 3 | 0 |
| conciliaciones | 3 | 3 | 0 |
| conciliacion_detalles | 6 | 6 | 0 |
| facturas_movimientos | 4 | 4 | 0 |
| facturas_impuestos | 5 | 5 | 0 |
| facturas_vencimientos | 2 | 2 | 0 |
| facturas_incidencias | 3 | 3 | 0 |
| historial_facturas | 8 | 8 | 0 |

Ademas de conteos, se comparan huellas de filas completas en estas tablas y en
albaranes extraidos, ajustes y configuracion. Documentos se comparan excluyendo
solo las dos columnas nuevas. Todas las huellas comparables permanecen identicas.

- Logista antes/despues: NORMALIZADA / CONCILIADA, 448.00 EUR, misma conciliacion.
- Cofares antes/despues: NORMALIZADA / CONCILIADA, 177.74 EUR, naturaleza SERVICIOS,
  clasificacion documental FACTURA_GASTO_SERVICIO, misma conciliacion.
- Flags antes/despues: false / false / false; farmacias habilitadas [PIO].
- Alliance no persistida; ninguna tercera factura ni PDF procesado productivamente.
- RITA no afectada, HEFAME no procesado, Farmatic y Luna/API no utilizados.

## Pruebas locales posteriores

Con `C:\ControlFarmacias\Programa\.venv\Scripts\python.exe -B`:

- Focales runtime, multifactura, Alliance, identidad y completitud:
  **260 passed, 0 failed**, 6.79 segundos.
- `pytest -q -p no:cacheprovider tests/`:
  **933 passed, 0 failed**, 55.11 segundos.
- Regresiones detectadas: 0. No instalaciones ni reparaciones del entorno.
- Cierre productivo READ ONLY posterior a las pruebas: identico al postflight.

## Artefactos locales

snapshot_pre.json, snapshot_post.json, rollback_15.sql, certificacion_previa.md,
despliegue.log y cierre.json. Scripts auditar.py/desplegar.py/cierre_readonly.py
conservan las comprobaciones reproducibles. El desplegador rechaza una segunda
ejecucion porque exige igualdad con el snapshot previo y ausencia de 15.

No se modifico la migracion certificada ni codigo funcional del proyecto en 2P.
Los archivos nuevos de este hito estan solo bajo pruebas/auditoria_2p.
Cambios ajenos preservados. Sin commit/push. Produccion estable al cierre.
