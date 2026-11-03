# Hito 2BM: persistencia multifactura ligera (migración 28)

Solo local. La serie 2BJ está PARADA hasta desplegar la 28 (decisión de Pio, 2026-11-03). Sin push.

## 1. Problema

- Tanda 7: la persistencia del Alliance de la posición 57 tardó **5,90 s** en producción (primera medición con la
  26; `pg_stat_statements`).
- Tanda 9: la del Alliance de la posición 82 superó el `statement_timeout` de 8 s (57014). Está en `ERROR`, intento
  1 de 4, sin escritura parcial.

## 2. Diagnóstico (PostgreSQL 17 local, sin producción)

PG17 con los ajustes de producción que pesan (`pglz`, `wal_compression=zstd`, `shared_buffers` 224 MB, `jit` off),
la sentencia **exacta** de PostgREST (texto de `pg_stat_statements` de producción) y el payload real de la
posición 122 (274 líneas, 4,6 MB, 4 facturas), con el volumen final simulado. Evidencias y scripts, fuera del
repositorio: `C:\ControlFarmacias\evidencias_2bm_diag` (`diag_persistencia.py`, `medir_28.py`).

Con la 27, 1,20 s en el servidor:

| Etapa | Tiempo |
|---|---|
| Parseo del cuerpo (JSON a jsonb) | 0,16 s |
| Firma SHA-256 (objeto intermedio con todo el payload) | 0,11 s |
| Bucle de validación e identidad (hermanas: identidad recalculada) | 0,31–0,37 s |
| Copias del payload hasta el núcleo de normalización | 0,21 s |
| Inserción de la ejecución con `resultado_json` (4,6 MB) | 0,12–0,20 s |
| Facturas y líneas (`datos_extraidos`, 4,6 MB) | 0,21–0,32 s |
| Documento e historial | 0,05 s |

`lz4`: −15 % (producción lo admite: `{pglz,lz4}`). `wal_compression`: sin efecto.

## 3. Migración 28 (decisiones de Pio)

`sql/migrations/28_cf_persistencia_multifactura_ligera.sql`, generada por `generar_migracion_28.py` a partir del
texto literal de la 27. Cada sustitución se comprueba y un test verifica que el fichero coincide con el generador.

1. **`lz4`** en `resultado_json`, `datos_extraidos` y los `provenance`/`detalle_tecnico` de las líneas. Solo
   valores nuevos: no reescribe filas.
2. **Sin duplicar el contenido.** En el `resultado_json` de la multifactura, cada factura que persiste la propia
   ejecución es una referencia `{"_factura_persistida": {"proyeccion_clave", "claves_originales"}}` a
   `facturas.datos_extraidos` (completo). Las demás (pendientes, duplicadas, en revisión, ya persistidas) siguen
   completas. La lectura completa se reconstruye exactamente (`cf_factura_desde_referencia`).
   - **Histórico (decisión de Pio: conservarlo):** trigger `facturas_materializar_referencia`. Antes de que cambie
     `datos_extraidos` de una fila o de que se borre, por cualquier camino, toda ejecución del documento que la
     referencia recibe la copia completa de su factura. La copia completa solo se escribe en ese caso. No depende
     de `normalizacion_ejecucion_id`: un upsert con datos idénticos lo cambia sin cambiar el contenido (hallazgo
     del revisor). Borrar una factura persistida ya es imposible (historial append-only); el `DELETE` queda
     cubierto igualmente.
   - **Conciliación:** la revalidación de farmacia (`repositorios.py`) reconstruye la lectura desde
     `datos_extraidos` (`reconstruir_resultado_json`). Una referencia sin su fila falla cerrado.
3. **Sin copias del payload:** núcleo de normalización de 9 parámetros (documento y facturas aparte; el de 7 queda
   como envoltorio fino de la RPC de un documento), y las facturas nuevas se acumulan en un array.
4. **Identidad calculada una vez** por factura (antes, al comparar con cada hermana).
5. **Firma sin objeto intermedio** (decisión de Pio): `sha256(p_resultado::text || '|' || selección)`. La
   concatenación no es ambigua porque el texto jsonb de un objeto termina donde termina el objeto. Una repetición
   de una ejecución guardada con la fórmula de la 15–27 se comprueba con esa fórmula: sin falsos rechazos.

Firmas, privilegios de las RPC, filas existentes, replay, rechazo, inventario y estados: los de la 27. Requiere la
27 (`MIGRACION_27_AUSENTE`). Funciones internas solo para el propietario.

**Rollback:** materializa todas las referencias (todo `resultado_json` vuelve al formato 27; si alguna no se
resuelve, aborta) y reproduce literalmente las funciones de la 27, sin trigger ni funciones nuevas y con la
compresión por defecto. Esquema idéntico al de la 27 (test).

**Serie 2BJ:** la puerta de la 27 (`SQL_MARCAS_27`) comprueba por nombre de función, porque desde la 28 el núcleo
que usa `cf_ejecucion_persistida` es el de 9 parámetros. Los tests de la serie usan la plantilla 28.

## 4. Medición (posición 122, misma base, 5 repeticiones alternadas)

| | 27 | 28 |
|---|---|---|
| Puntos 1–4 | 1,23–1,25 s | 0,58–0,60 s |
| Puntos 1–4 y firma sin copia | 1,29 s | 0,52–0,54 s |
| Migración definitiva (histórico con trigger) | 1,22 s | **0,52–0,55 s** |

Objetivo de Pio: ≤ 0,55 s en local (≈ 4 s en producción con un factor ≈ 7, `INFERIDO`). Lo que queda: parseo del
cuerpo (0,16 s), firma (≈ 0,06 s), recorridos del JSON e inserciones.

## 5. Tests (`test_integracion_pg17_2bm.py`, 30)

- **Equivalencia 27 = 28** en los 9 escenarios del 2BK: estado completo de las tablas de normalización, con
  `resultado_json` reconstruido y sin la firma (su fórmula cambia).
- Referencias solo de las facturas que persiste la ejecución (nuevo: 3; parcial: 1 + 2 completas; duplicado: 0);
  `datos_extraidos` completo; la lectura reconstruida es el payload; `resultado_json` más de 20 veces menor.
- Firma: replay y rechazo con la nueva; ejecución guardada con la 27 y 28 desplegada después: replay sin falso
  rechazo y rechazo de otra solicitud.
- Histórico: relectura que sobrescribe con la RPC de un documento, `UPDATE` directo, upsert con datos idénticos
  seguido de un cambio, y borrado; la ejecución previa conserva su lectura; otros cambios de la fila no tocan las
  ejecuciones.
- Conciliación: reconstrucción pura (incluida la referencia no resuelta); sin reconstruir, la barrera de farmacia
  rechaza la lectura; el worker de conciliación da el mismo resultado con la 27 y la 28.
- Generador; rollback igual a la 27 y `resultado_json` de vuelta al formato 27; exige la 27; no altera datos;
  privilegios y `lz4`; `desplegar_28.py` ensayado (aplicada; el segundo intento se revierte) y rechazo de un SQL
  distinto del commit.

## 6. Plan tras desplegar (decisión de Pio)

1. Preflight READ_ONLY, despliegue de la 28 con `desplegar_28.py` (commit y SHA) y postcheck 2AX.
2. Reintentar el Alliance de la posición 82 y medir el tiempo real en producción.
3. Con ese factor, decidir la alternativa 2 (evidencia en tabla aparte, comprimida) antes de la posición 122.
