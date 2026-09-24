# Hito 2O.1 - flujo multifactura exclusivamente local

## Alcance y auditoría

No se ha consultado ni escrito Supabase productivo. No se ha ejecutado ningún
piloto real, worker, llamada Luna/API, Farmatic, cambio de flags, commit o push.
Solo se usa el Python existente de `.venv`. Los datos del PDF real solo se
extraen y normalizan en memoria; las bases PostgreSQL contienen datos sintéticos.

La equivalencia documento/factura NO está impuesta por el esquema:

| Componente auditado | Situación anterior y decisión |
| --- | --- |
| `facturas` / migración 08 | La FK real es `documento_id`, no `documento_factura_id`. El UNIQUE `(documento_id, proyeccion_clave)` ya permite N. Se conserva. |
| `documentos_facturas` | Estado global de lectura y contador, sin inventario de hermanas pendientes. No bastaba para persistencia parcial explícita. |
| `normalizacion_ejecuciones` | Unidad de extracción documental, puede conservar el resultado completo con N facturas. No equivale a una factura. |
| RPC `cf_persistir_normalizacion`, migración 12 | Ya recorre N facturas en una transacción, pero siempre termina el documento como NORMALIZADA y cuenta solamente el payload. Recortar B ocultaba A/C/D. |
| `pruebas/piloto_productivo_2i.py` | Rechaza `len(local.facturas) != 1`, usa `[0]`; `_stable_invoice_id` mezcla SHA y páginas. Se deja intacto; no es entrada multifactura. |
| `pruebas/piloto_productivo_cofares_2l2b.py` | También exige exactamente una y hereda el identificador técnico. Se deja intacto. |
| Modelos normalizador V2 | Factura individual y resultado con lista; ya permiten N. Se reutiliza la validación individual. |
| `alliance-local` 1.0.0 | Ya extrae varias facturas y segmentos. El puente nuevo conserva la extracción original, sin elevar candidatos a albaranes. |
| `completitud_documental.py` | Marca global y cobertura de segmentos. El puente añade demostración de completitud para cada factura. |
| Identidad documental | Ya diferencia contenido y localización. El nuevo contrato usa NIF documentado canónico, número, tipo, destinatario, fecha y total; no filename/SHA/páginas. |
| Repositorio runtime anterior | Llama a la RPC documental antigua; no coordina selección parcial e inventario. Se ofrece entrada explícita separada `persistir_multifactura`. |
| Elegibilidad, claim V2 y conciliación | Ya trabajan con `factura_id`, no con PDF. No se modifica migración 14 ni el reconciliador. |

## Contrato y barreras

`resultado_documento` contiene marca de completitud global, número de páginas,
metadata común y lista completa de facturas. La selección autorizada se envía
aparte, como lista de `segment_id`. Nunca se recorta el inventario.

Cada factura conserva campos económicos documentados, fiscalidad, vencimientos,
movimientos, incidencias, datos crudos y provenance. El identificador técnico del
segmento solo selecciona; la clave económica SHA-256 se calcula sobre seis
componentes de contenido separados por U+001F. FACTURA_DUPLICADO se canoniza como
FACTURA: la leyenda impresa DUPLICADO no demuestra que ya exista en la base.

NIF ausente, evidencia ausente, destinatario no PIO o versión incompatible del
mismo núcleo requieren revisión. La comparación de fecha/total incompatible
prevalece sobre coincidencias exactas, independientemente del orden. La RPC
decide NUEVA/duplicada/revisión frente a las facturas locales existentes.

Cobertura documental: todas las páginas, sin huecos ni solapes. Cobertura por
factura: rango completo, páginas de provenance coincidentes y evidencias dentro
de su propia factura. Alliance exige paginación interna 1..N y total N para cada
segmento. Dos facturas compartiendo una página no están certificadas por este
contrato: se rechazan, no se inventa una separación de bloques.

## Transacción e inventario

Se añade migración **15 solo local**, sin cambiar migraciones anteriores ni
crear tablas. No es necesaria para cardinalidad N: incorpora dos columnas
necesarias para el contrato explícito de persistencia parcial elegido:
`inventario_facturas` y `estado_persistencia`, y la RPC coordinadora nueva.

`cf_persistir_documento_multifactura` verifica claim documental vigente, PIO,
cobertura y selección. Un advisory lock transaccional serializa decisiones de
identidad entre documentos que usan esta entrada. Un lock de fila protege el
documento. Se invoca la RPC anterior UNA vez con las nuevas facturas autorizadas,
dentro de la misma transacción, y se guarda el resultado completo de extracción.
Un error técnico revierte facturas, hijos, ejecución, historial e inventario.

Inventario por segmento: PENDIENTES, PERSISTIDAS, REQUIERE_REVISION o DUPLICADAS;
se conserva la referencia económica correspondiente. Estado documental:
PENDIENTE, PARCIAL, COMPLETA o REQUIERE_REVISION. Solo COMPLETA tiene lectura
NORMALIZADA; mientras haya hermanas pendientes/revisión, lectura REVISION.
La ejecución de extracción puede estar completada sin que la persistencia
documental esté completa: son dimensiones distintas.

La clave idempotente guarda firma del documento y de la selección. Repetirla con
otro payload falla; repetirla exactamente no modifica filas. Releer B no actualiza
su proyección ni borra sus conciliaciones; C puede incorporarse posteriormente.
Copias internas no seleccionadas no impiden persistir una copia posterior elegida.

La nueva entrada es explícita y local. No se han activado ni redirigido workers.
La RPC antigua conserva su comportamiento para consumidores anteriores: no debe
usarse directamente para un piloto parcial ni mezclarse concurrentemente con la
nueva entrada. Una futura integración productiva requiere autorización separada.
El despliegue de migración 15 NO está realizado ni autorizado por este informe.

## Certificación PostgreSQL

Ejecutable: `pruebas/certificacion_multifactura_2o1.py`.
PostgreSQL 17 real, imagen local postgres:17-alpine, dos volúmenes y contenedores
nuevos, network=none, sin puertos publicados ni credenciales productivas.
Cada ciclo aplica baseline, migraciones previas y 15; comprueba persistencia,
rollback, relectura, claim y conciliaciones independientes. Reaplica 15 sin cambios
en datos y compara RLS/policies/grants de tablas antes/después. Las funciones nuevas
revocan PUBLIC/anon/authenticated y conceden ejecución solo a service_role.
Se comprueba `has_function_privilege` para los tres roles; una llamada real como
anon falla con SQLSTATE 42501. Todas las persistencias del certificador se
ejecutan con SET ROLE service_role, no con privilegios de postgres.
Los contenedores y volúmenes creados por el script se eliminan tras cada ciclo
mediante nombres exactos y comprobación de etiqueta. No se borran datos ajenos.

| Caso solicitado | Evidencia automatizada |
| --- | --- |
| 1, 2, 3: una/tres/cinco | Tests parametrizados + conteos reales PostgreSQL |
| 4: todas completas | COMPLETA/NORMALIZADA y N filas reales |
| 5: una incompleta | Dos persistidas y una REQUIERE_REVISION |
| 6: duplicada + dos nuevas | Inventario DUPLICADAS/PERSISTIDAS/PERSISTIDAS |
| 7: proveedor común, números distintos | Claves distintas y filas independientes |
| 8: fecha/total incompatible | IDENTIDAD_NO_DEMOSTRADA/revisión, incluidas hermanas |
| 9: N transaccional | Una RPC coordinadora y N proyecciones |
| 10: solo B | A/C/D pendientes, documento PARCIAL/REVISION |
| 11: releer B | Mismo ID, sin duplicar ni actualizar B |
| 12: después C | Dos filas con inventario completo de cuatro |
| 13, 14: claim individual | Reclama B y D, no A conciliada ni C no apta ni el lote |
| 15: conciliaciones independientes | Dos conciliaciones actuales de facturas distintas; UNIQUE impide dos actuales por factura |
| 16: error técnico | NOT NULL inválido en hija de segunda factura: fingerprint completo sin cambios |
| 17: provenance | Cobertura exacta y rechazo de evidencia de otra hermana |
| 18: filename | Cambiar nombre/SHA/páginas no cambia clave económica |

Además: copia interna seleccionada en segunda posición, conflicto independiente
del orden y equivalencia exacta de claves calculadas por Python/PostgreSQL.

## Alliance real, solo memoria

Archivo: `pruebas/facturas/documentos/2o_gold_standard/ALLIANCE VTO 30.9-6.10-6.11 PIO.pdf`.
SHA256: `7b806565a4f09e182c5ec9d75b40b959fd39c4af86da77b7a8cb745c6e1192b2`.
Lectura completa: 11 páginas. Revisión visual de las 11 páginas y contraste de
paginación/cabeceras. Proveedor ALLIANCE HEALTHCARE ESPANA S.A., NIF A50004324;
destinatario PUIG SALOMON PIUS, NIF 40901058C. Tres facturas completas, fecha
2026-07-31, separables sin cortar ni descartar filas.

| Número | Páginas / segmento | Base | IVA | RE | Total | Vencimiento | Candidatos conservados |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| 08009278 | 1-4 / paginas-1-4 | 3506.46 | 272.07 | 46.06 | 3824.59 | 2026-09-30 | 109 |
| 08009277 | 5-9 / paginas-5-9 | 9539.43 | 507.28 | 64.84 | 10111.55 | 2026-10-06 | 165 |
| 08009279 | 10-11 / paginas-10-11 | 125.51 | 13.44 | 2.06 | 141.01 | 2026-11-06 | 5 |

Claves económicas individuales:

- 08009278: `4740d0be07c10a7a37a4ec5d0d2405b1a2ddcd3a22eab6eaae7b63a325c31344`
- 08009277: `092ce9759d1cd39fe3fb3167aece451fe9755bca4623fa8e398603a4b2ca036a`
- 08009279: `89611ce37b0992f1c95190615fc0c9ca1a35e88fbbcccd09be34a05a2c84a5b3`

Fiscalidad detallada, en orden base / %IVA / cuota IVA / %RE / cuota RE:

- 08009278: 2056.33 / 4 / 82.25 / 0.5 / 10.28;
  1042.80 / 10 / 104.28 / 1.4 / 14.60; 407.33 / 21 / 85.54 / 5.2 / 21.18.
- 08009277: 8115.00 / 4 / 324.60 / 0.5 / 40.58;
  1058.63 / 10 / 105.86 / 1.4 / 14.82; 181.50 / 21 / 38.12 / 5.2 / 9.44;
  gastos 26.00 / 21 / 5.46 / sin RE (31.46 total) y
  158.30 / 21 / 33.24 / sin RE (191.54 total).
- 08009279: 117.42 / 10 / 11.74 / 1.4 / 1.64;
  8.09 / 21 / 1.70 / 5.2 / 0.42.

Las cabeceras repiten el vencimiento en cada página. El puente conserva todas sus
evidencias bajo un solo vencimiento por fecha cuando no hay importe; no crea
cuatro/cinco/dos cobros ficticios. No infiere el importe del vencimiento.

**Albaranes demostrados por el adaptador: cero en las tres facturas.** Los 109,
165 y 5 candidatos conservan su evidencia y rol indeterminado. La separación
documental está demostrada; la aptitud de estas facturas para conciliación
automática NO. No se alteran reglas para hacerlas pasar.

## Resultados

- Focales finales: 260 passed, 0 failed (7.56 segundos).
- PostgreSQL 17: dos ciclos limpios completos después de las correcciones.
- Suite general final: 933 passed, 0 failed, 53.91 segundos; referencia 915,
  incremento 18. Ejecución anterior también verde (932 antes del caso numérico).
- Regresiones detectadas: cero. La lista explícita de migraciones del test de
  esquema se amplió de 14 a 15; no se debilitó ninguna aserción.

## Archivos de este hito

- Nuevo `src/facturas/runtime_supabase/multifactura.py`: contrato, identidad,
  cobertura, puente Alliance y entrada explícita a la RPC coordinadora.
- Nuevo `sql/migrations/15_cf_multifactura.sql`: inventario/estado y RPC
  transaccional local. Las migraciones 06b-14 quedan intactas.
- Nuevo `tests/facturas/runtime_supabase/test_multifactura.py`: pruebas sintéticas
  y lectura completa real solo en memoria, sin clientes de base de datos.
- Modificado `tests/facturas/runtime_supabase/test_modelo_supabase_v1.py`:
  únicamente se añade la migración 15 a la lista esperada.
- Nuevo `pruebas/certificacion_multifactura_2o1.py`: dos ciclos PostgreSQL aislados,
  aserciones económicas/transaccionales/seguridad y limpieza propia.
- Nuevo `docs/MULTIFACTURA_2O1.md`: auditoría, diseño, evidencia y limitaciones.

Los cambios preexistentes ajenos se conservan. El PNG de contacto usado para
revisión visual se eliminó después de inspeccionarlo; el PDF original no cambió.

Estado final local: **FLUJO_MULTIFACTURA_CERTIFICADO**. No equivale a autorización
de despliegue ni a certificación de albaranes/conciliación automática del PDF real.
