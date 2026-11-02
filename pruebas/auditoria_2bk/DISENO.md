# Hito 2BK: persistencia multifactura indexada (migración 26)

Solo local. La serie 2BJ está en pausa desde la tanda 5 (2026-11-02). Sin push.

## 1. Problema

En la tanda 5 de la serie 2BJ, la RPC `cf_persistir_documento_multifactura` del Alliance de la posición 57
(08007499–502) superó el `statement_timeout` de 8 s que fija el rol `authenticator` (código 57014, `APIError`,
`TRANSITORIO`; diagnóstico READ_ONLY en `C:\ControlFarmacias\evidencias_2bk_diag`).

- Las tres persistencias multifactura que sí terminaron tardaron entre 3,7 y 7,1 s (`pg_stat_statements`).
- El fallo fue atómico: no quedó ninguna escritura parcial.

## 2. Causa (medida en PostgreSQL 17 local)

La función de la 15 (envuelta por la 17) recorre `public.facturas` completa por cada factura del documento y
calcula `cf_componentes_identidad_factura(datos_extraidos)` en cada fila. Eso descomprime un JSON de entre 0,1 y
1 MB por fila. El coste crece con el volumen de la tabla.

- **Medición con la 25** (14 Alliance del volumen final; el último es el de 274 líneas): la RPC pasa de 1,3 s
  con 3 facturas en la tabla a **7,9 s** con 54 (sin contar el transporte del payload, de unos 4,6 MB).
- **Perfil (`auto_explain`):** las 4 búsquedas de identidad suman unos 6,7 s; el resto, aproximadamente 1 s.
- **Primer intento con índice de expresión:** el índice existía, pero dentro de PL/pgSQL el planificador seguía
  recorriendo la tabla. La función tenía el coste por defecto (100) y la tabla parecía pequeña. Ese coste no
  refleja la descompresión de cada `datos_extraidos`.

## 3. Migración 26 (decisión de Pio: índice de expresión, sin columna nueva)

`sql/migrations/26_cf_persistencia_multifactura_indexada.sql`, generada por `generar_migracion_26.py` a partir
del texto literal de la 15 y la 17. Cada sustitución se comprueba y un test verifica que el fichero coincide con
el generador.

1. **`facturas_identidad_nucleo_idx`:** índice de expresión sobre
   `(cf_componentes_identidad_factura(datos_extraidos))[1:4]`, la misma función del bucle. No hay columna nueva
   y las filas de `facturas` no cambian.
2. **`cf_componentes_identidad_factura` declara `COST 10000`.** Solo cambia el plan: el planificador usa el índice
   incluso sin estadísticas (test con plan genérico).
3. **El bucle solo visita las filas con el mismo núcleo `[1:4]`**, `order by ctid` (el orden de la lectura
   secuencial). Las demás filas nunca cumplían la condición del bucle, así que el resultado es el mismo por
   construcción.
4. **La ejecución se escribe una vez** (antes: inserción y dos actualizaciones de un `resultado_json` de MB):
   - el núcleo de normalización recibe el `resultado_json` final (lectura completa, `multifactura` y, en la
     firma de 7 parámetros, `provenance_ejecucion`);
   - el `disparador` real va en la inserción.
5. **Firmas y privilegios:** `cf_persistir_normalizacion` y las dos firmas de
   `cf_persistir_documento_multifactura` mantienen firma, privilegios y comportamiento, y delegan en dos núcleos
   internos, accesibles solo al propietario.
6. **Requiere la 25** (`MIGRACION_25_AUSENTE`).
7. **Rollback:** devuelve literalmente las funciones de la 15 y la 17, quita el índice y vuelve a `COST 100`.
   Esquema idéntico al de la 25 (test con `pg_dump`).

**Límite conocido:** si alguna vez se redefine `cf_componentes_identidad_factura`, hay que reconstruir el índice
(`REINDEX`).

## 4. Resultado (PostgreSQL 17 local, `medir_persistencia.py`)

| | 25 | 26 |
|---|---|---|
| Peor persistencia multifactura, neta (274 líneas, 54 facturas en la tabla) | 7,87 s | **1,07 s** |
| Peor persistencia multifactura, con transporte | 8,33 s | **1,54 s** |
| ¿Crece con el volumen? | sí, de 1,3 a 7,9 s | no, entre 0,6 y 1,1 s |
| `cf_persistir_conciliacion`, la mayor prevista (08009277, 160 líneas, 167 detalles, CONCILIADA) | 0,08 s | 0,18 s |

- **Factor local/producción** `INFERIDO` (≈ 3,2): la 25 tardó 2,2 s en local con 11 facturas en la tabla y 7,1 s
  en producción con 12.
- **Estimación en producción para la 26:** unos 3,5 s en el peor caso, frente al límite de 8 s. El objetivo de
  menos de 3 s **se cumple en local**; en producción se confirmará con la primera persistencia tras desplegarla.
- **Conciliación:** muy por debajo del límite; la 26 no la toca. La diferencia entre 0,08 y 0,18 s es ruido de
  una sola medición.

Evidencias, fuera del repositorio: `C:\ControlFarmacias\evidencias_2bk`.

## 5. Tests (`test_integracion_pg17_2bk.py`)

- **Equivalencia con la 25.** Mismo payload real (PDF Alliance del 2AP), estado completo de las 9 tablas de
  normalización igual, 9 escenarios:
  - nuevo;
  - duplicado (`DUPLICADAS`);
  - versión incompatible (`REQUIERE_REVISION`; la fila indexada se actualiza antes);
  - replay e idempotencia con payload distinto;
  - relectura;
  - autorización parcial (`PARCIAL`);
  - firma de 6 parámetros;
  - RPC de un documento;
  - claim ajeno.
- **Escritura única:** 1 inserción y 0 actualizaciones de la ejecución, frente a 1 y 2 con la 25, con el mismo
  contenido.
- **Plan:** índice con plan genérico y sin `ANALYZE`; la 25 hace `Seq Scan`.
- **Migración:** generador reproducible; rollback igual al esquema de la 25; exige la 25; no altera datos;
  privilegios.
- **Despliegue:** `desplegar_26.py` ensayado (aplicada; el segundo intento se revierte) y rechazo de un SQL
  distinto del commit.

## 6. Serie 2BJ: postcheck también al parar

`serie_normalizacion.py tanda` hace el postcheck 2AX por fila de toda la tanda también cuando se para; antes
solo lo hacía al terminar. Si el postcheck no puede hacerse, la parada se registra igual, con
`POSTCHECK_NO_REALIZADO`. Test nuevo con el caso de producción: la RPC multifactura cae, la tanda se para y el
postcheck queda OK, sin facturas del Alliance.

## 7. Pendiente (con confirmación de Pio)

1. Preflight READ_ONLY y despliegue de la 26 con `desplegar_26.py` (commit y SHA) y postcheck 2AX.
2. Reanudar la serie: el Alliance de la posición 57 está en `ERROR`, intento 1 de 4, reclamable de nuevo desde
   las 10:27 UTC del 2026-11-02.
