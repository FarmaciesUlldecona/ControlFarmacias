# Hito 2G.1 — manifiesto PIO canónico

## Resultado

El índice se abrió con `mode=ro&immutable=1`. Los 126 registros `IMPORTADA` se
clasifican con la regla del importador, no por una heurística nueva:

- PIO: 119 rutas, 116 SHA-256 únicos.
- RITA: 7 rutas, 7 SHA-256 únicos.
- Otros excluidos: 0.

`obtener_facturas_pdf()` solo incluye archivos `.pdf` situados en una carpeta
mensual reconocida desde junio de 2026 y descarta `es_factura_rita()`. Esta última
función evalúa `ruta_pdf.stem.rstrip().casefold().endswith("rita")`: ignora caja y
espacios finales, pero no excluye una aparición intermedia de RITA.

Los siete hashes solo SQLite pertenecen, uno por ruta, a los siete PDF cuyo stem
termina en RITA. Ninguno aparece en `documentos_facturas` (ninguna farmacia), en
`documentos_facturas` PIO ni en `storage.objects` del bucket `facturas-pdf`, ni
por ruta esperada ni por el prefijo de doce caracteres usado en el nombre Storage.
La causa demostrada es la exclusión RITA vigente.

La comprobación directa de existencia/bytes actuales en la unidad virtual G: no
pudo completarse: el sandbox denegó la lectura y el contexto elevado no dispone
del mapeo de Google Drive. No se modificó Drive ni se usó su API. El SQLite sí
conserva hash, tamaño y mtime de la importación.

## Duplicados de ruta PIO

| SHA-256 | Rutas | Tamaños registrados | mtime | Supabase PIO | Storage de la fila |
|---|---:|---|---|---:|---|
| `0cc52ac…f116b` | 2 | 30862 / 30862 | distintos | 1 | presente |
| `0dba035a…3297` | 2 | 57950 / 57950 | distintos | 1 | presente |
| `c9fbece3…560604` | 2 | 144491 / 144491 | iguales | 1 | presente |

Cada pareja conserva exactamente el mismo SHA-256 calculado durante la
importación y el mismo tamaño. La igualdad byte a byte del contenido importado se
representa por SHA-256; no se releyeron los bytes actuales de Drive por la
limitación anterior. El importador calcula SHA-256 antes de decidir y, si ya está
en el conjunto Supabase, solo actualiza la ruta en SQLite como `IMPORTADA`: no
sube otro objeto ni crea otra fila. En producción hay una fila y un objeto por
cada hash. Conforme a la identidad persistida por el sistema, son
`DUPLICADO_DE_RUTA_MISMO_DOCUMENTO`.

## Identidad y reconciliación

La identidad correcta es el conjunto de SHA-256 únicos dentro de la farmacia,
no el número de rutas. Lo prueban conjuntamente:

- `documentos_facturas` tiene UNIQUE `(farmacia, archivo_hash)`;
- el importador carga los hashes PIO en un `set` y deduplica antes de Storage;
- la ruta Storage incorpora el prefijo del hash y queda referenciada por la fila;
- la migración 13 no crea/fusiona documentos: consume una atestación externa;
- los campos del guard se denominan `hashes`, y no rutas.

Algoritmo canónico: aplicar alcance PIO, excluir RITA, exigir 64 hexadecimales,
normalizar a minúscula, deduplicar, ordenar, unir por LF y aplicar SHA-256.

| Medida | SQLite PIO | Supabase PIO |
|---|---:|---:|
| Hashes únicos | 116 | 116 |
| Hashes inválidos | 0 | 0 |
| Solo SQLite | 0 | — |
| Solo Supabase | — | 0 |
| Manifiesto | `3edc9214c5443c7e6937b91a73d24519c6954fce441842ade46501188f8082cf` | `3edc9214c5443c7e6937b91a73d24519c6954fce441842ade46501188f8082cf` |

El manifiesto anterior `02e3…ee1d` era incorrecto: incluía los siete RITA y
conservaba las tres repeticiones PIO. No había una discrepancia PIO real.

## Corrección local del guard

`manifiesto_pio.py` concentra clasificación, validación, deduplicación y hash.
La preflight informa el manifiesto Supabase vivo. El postflight compara la
atestación con ese estado. `cf_preflight_pio_valido()` ahora exige:

- cero hashes PIO nulos/inválidos;
- conteos SQLite/Supabase atestados iguales;
- conteo Supabase atestado igual al `count(distinct archivo_hash)` vivo;
- manifiestos atestados iguales;
- manifiesto Supabase atestado igual al agregado vivo canónico;
- farmacias habilitadas exactamente `{PIO}`.

Así, dos atestaciones inventadas pero iguales ya no habilitan 13. La migración 13
no cambia: sigue bloqueada por la función. El staging prueba expresamente el caso
y calcula la atestación sintética con la misma semántica canónica.

## Alcance de seguridad

Durante 2G.1 producción solo recibió SELECT en transacciones READ ONLY. No hubo
DDL/DML, migraciones, llamadas funcionales RPC, APIs, workers ni procesamiento de
PDF. SQLite, Drive, Storage, Farmatic, Scheduler, `.bat` y `.env` no se
modificaron. Las certificaciones PostgreSQL posteriores son exclusivamente
locales y sintéticas.

Dos ciclos limpios PostgreSQL 17 completaron baseline → 06b → 07 → 08 → 08b →
09 → 10 → 11 → 12 → guard canónico → 13 → validación. En ambos, la atestación
concordante pero ajena al estado vivo quedó bloqueada; la atestación canónica
sintética habilitó 13. Las dos bases se destruyeron al finalizar cada ciclo.

Tests focales: 115 passed. Suite completa: 780 passed en 44.39 s. Regresiones: 0.

Archivos creados en 2G.1:

- `src/facturas/runtime_supabase/manifiesto_pio.py`;
- `tests/facturas/runtime_supabase/test_manifiesto_pio.py`;
- `docs/SUPABASE_V1_MANIFIESTO_PIO_2G1.md`.

Archivos ajustados localmente:

- `sql/migrations/07_cf_proveedores_config.sql`;
- `sql/preflight/preflight_supabase_controlfarmacias.sql`;
- `sql/preflight/postflight_supabase_v1.sql`;
- `sql/staging/06_test_backfill_pio.sql`;
- `tests/facturas/runtime_supabase/test_modelo_supabase_v1.py`.
