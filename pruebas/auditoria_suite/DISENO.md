# Hito SUITE: suite paralela, suite histórica y regla de reparación. DISEÑO

Estado: **IMPLEMENTADO** (2026-11-20, decisiones de Pio D1–D8 en §0; medición en §5). Solo toca la forma de
ejecutar y registrar los tests y la barrera de commit (`.claude/`); **no toca producción, Supabase ni Farmatic**.

- **Origen:** la suite completa tarda ~41 min (3154 passed en 41:14, 2026-11-19). La parte `pg17_local` (697 tests,
  PostgreSQL 17 en Docker) se lleva ~39; la rápida (2457 tests) tarda 2:05. Cada corrección de un test obliga hoy a
  repetir los 41 min.
- **Etiquetas:** `CONFIRMADO POR CÓDIGO` (fichero:línea), `MEDIDO` (ejecución local) y `PROPUESTA`.

## 0. Decisiones de Pio (2026-11-20)

| Id | Decisión |
|---|---|
| **D1** | Dependencia nueva **pytest-xdist, fijada a una versión** |
| **D2** | Número de workers **tras medir 4, 8 y 12**; previsto 8 |
| **D3** | Reparto **por familia de plantillas** (`--dist loadgroup`) |
| **D4** | Suite **histórica**: obligatoria **antes de cada despliegue**, **por rutas tocadas** y **semanal vía la barrera** |
| **D5** | **Un contenedor TCP por worker** para los ensayos, separado de los contenedores sin red. **Corregida por Pio (2026-11-20, tras la histórica):** un contenedor TCP **limpio por módulo** (§2.3) |
| **D6** | Regla de reparación (a): **1 repetición** y **como máximo 3 tests** |
| **D7** | `tests/conftest.py`, `tests/facturas/runtime_supabase/pg17_local.py`, `tests/registro_suite.py` y `tests/consultar_suite.py` **cuentan como código** en la regla (b) |
| **D8** | Este diseño, en `pruebas/auditoria_suite/DISENO.md` (commit solo de documentación) |

## 1. Situación de partida

- **Un solo contenedor por ejecución.** `pg17_contenedor` es de sesión (`tests/facturas/runtime_supabase/conftest.py:14-39`),
  sin red y en tmpfs. Las plantillas se construyen bajo demanda y en cadena (16 → 36), y se reutilizan
  (`pg17_local.py:561-727`). Cada test copia una plantilla en una base propia y la borra al terminar
  (`conftest.py:62-77`).
- **Estado común a todas las bases del contenedor: los roles.** Las migraciones 19, 29, 31 y 35 y sus rollbacks
  crean, modifican o borran roles. En serie no choca; **varios workers en un mismo contenedor sí chocarían**. Por eso
  cada worker tiene su propio contenedor (D5 y §2.1).
- **Dos módulos arrancan cada uno un contenedor con puerto TCP** (`test_ensayo_despliegue_19_2ax.py:59-77`,
  `test_integracion_pg17_2az.py:454-473`), porque el script de despliegue se conecta con psycopg2, y reconstruyen
  desde cero las plantillas 18 y 19.
- **Lo que más pesa:** los ~70 ensayos de despliegue y rollbacks (10–25 s cada uno). En R20, el rollback y el
  ensayo completo suman 43 s de 160 (`MEDIDO`, 2026-11-20).
- **Registro de suites** (`tests/registro_suite.py`): una línea por ejecución con la huella exacta del árbol
  (`.claude/hooks/estado_git.py:120-142`), las cifras y el alcance (`completa`, `rapida` o `parcial`). Hoy **no
  guarda qué tests fallaron**. La barrera de commit exige la suite del alcance que toca sobre la huella exacta
  (`.claude/hooks/barreras_agentes.py:378-421`).

## 2. Diseño

### 2.1 Paralelo con pytest-xdist (D1–D3)

- **Versión fijada** en `pytest.ini` con `required_plugins = pytest-xdist==<versión>`: si falta o es otra, pytest no
  arranca (falla cerrado). Se instala en `.venv` con el OK de Pio.
- **Un contenedor por worker.** `pg17_contenedor` sigue siendo de sesión; con xdist, cada worker es una sesión
  propia y arranca **su** contenedor, con sus plantillas y sus bases. Nada se comparte entre workers.
- **Reparto por familia** (`--dist loadgroup`): cada módulo `pg17_local` lleva la marca `xdist_group` de su familia,
  asignada en un único sitio (`conftest.py` de `runtime_supabase`). Los tests de una familia caen en el mismo
  worker, que construye su cadena de plantillas una sola vez. Las familias se ajustan con la medición para que
  ninguna limite el tiempo total.
- **Valor por defecto** en `addopts` (`-n <N> --dist loadgroup`), con N fijado tras medir 4, 8 y 12 workers.
  `-n 0` sigue disponible para ejecutar en serie.
- **Registro con xdist:**
  - solo escribe el proceso principal;
  - los workers le pasan las cifras de colección (colectados, `pg17_local`, deseleccionados) por `workeroutput`;
  - las cifras de resultado salen del proceso principal, como hoy.
  
  La regla del alcance no cambia.

### 2.2 Suite histórica (D4)

- **Marca nueva `historica`.** La lista vive en un único diccionario, `SUITE_HISTORICA`, del `conftest.py` de
  `runtime_supabase`, por módulo y nombre de test. Incluye:
  - los ensayos de despliegue de las migraciones **ya desplegadas** (19–36);
  - los tests de que cada rollback devuelve el esquema exacto;
  - los preflights `2b*_d`;
  - el ensayo de la fase 4 del 2AT y el del despliegue de la 19.
- **Alcances del registro:**

  | Alcance | Ejecución | Sustituye a |
  |---|---|---|
  | `rapida` | `-m "not pg17_local"` | — |
  | `completa` | `-m "not historica"` (la suite de cada commit de código) | `rapida` |
  | `historica` | `-m historica` | — |
  | `total` | sin `-m` | `completa`, `historica` y `rapida` |

  En todos se exigen `tests/` completo, sin `-k`, todo lo colectado ejecutado y ningún `pg17_local` omitido.
- **Cambiado por PERMISOS-1 (DECISIÓN DE PIO, 2026-11-27):** la histórica es obligatoria (exacta) **solo** si el
  commit toca `sql/migrations/`, un `desplegar_*` o `preflight*` de `pruebas/`, `pg17_local.py`, el `conftest.py`
  de `runtime_supabase`, un módulo de `SUITE_HISTORICA`, `conciliacion.py`, `repositorios.py` o `puerta_git.py`.
  Se retiran la regla semanal, `pruebas/auditoria_2at/` y el resto de `sql/`. Vigente: `REGLAS_CRITICAS`
  («Hito SUITE»). Lo que sigue es el diseño original.
- **Cuándo es obligatoria la histórica** (la barrera lo comprueba en cada commit de código):
  - **por rutas tocadas:** si el cambio toca `sql/`, `pg17_local.py`, el `conftest.py` de `runtime_supabase`, un
    `desplegar_*` o un `preflight*` de `pruebas/`, `pruebas/auditoria_2at/`, `src/facturas/runtime_supabase/puerta_git.py`
    o un módulo con tests de `SUITE_HISTORICA` → histórica en verde **sobre la misma huella**;
  - **semanal:** en cualquier otro commit de código → una histórica (o total) en verde de **7 días o menos**, sobre
    cualquier huella del repositorio;
  - **antes de cada despliegue:** la barrera bloquea un comando `desplegar_<n>` si no hay histórica (o total) en
    verde **sobre la huella actual**, es decir, el árbol limpio del commit que se despliega.
- **Al desplegar una migración nueva**, sus ensayos pasan a `SUITE_HISTORICA` en el commit que registra el
  despliegue (el «D»). Hasta entonces van en la suite de cada commit.

### 2.3 Contenedor TCP limpio por módulo (D5, corregida)

- Fixture única, `pg17_contenedor_tcp`, en el `conftest.py` de `runtime_supabase`, con el mismo arranque que antes
  (puerto **solo en 127.0.0.1**, tmpfs) y sustituyendo a los dos contenedores de módulo de 2AX y 2AZ. Los módulos que
  importan la fixture de 2AZ la usan igual.
- **Por módulo, no por worker** (`MEDIDO`, 2026-11-20): con uno por worker, la histórica dio 126 de 127. El ensayo
  de la 29 comprueba, como en producción, que su rol aún no existe; otro módulo anterior del mismo worker ya lo
  había creado en el clúster (los roles son comunes a todas sus bases). Pio decidió volver al contenedor limpio
  por módulo. Casi todos los ensayos TCP son históricos, así que solo encarece la histórica.
- Sigue separado de los contenedores sin red: mezclar ambos rompería el modo certificado.

### 2.4 Regla de reparación (D6 y D7)

- **El registro guarda además:**
  - `fallados`: los tests con fallo o error, sin el sufijo `@familia` de xdist;
  - en las ejecuciones parciales, `nodeids`: los tests ejecutados.
  
  Ya guardaba la base y `[ruta, sha256]` de cada fichero cambiado.
- **Origen:** la última `completa` o `total` **roja** con la misma base (HEAD). Por la regla (a) o la (b), una
  ejecución parcial en verde **equivale** a esa suite sobre su propia huella:
  - **(a) Sin cambios en el árbol.** Misma huella que el origen; el origen tiene **como máximo 3** fallados; la
    parcial los ejecuta todos y queda en verde. **Solo cuenta la primera parcial** sobre esa huella tras el origen.
    Si falla, suite completa.
  - **(b) Solo tests.** Los ficheros que difieren entre el árbol del origen y el actual (comparados por sha256)
    están todos en `tests/` y ninguno es:
    - uno de los cuatro de D7;
    - un fichero de `tests/` que no sea un módulo `test_*.py`. Son ayudantes o datos sin dependientes conocidos;
      `PROPUESTA` en modo falla cerrado: cuentan como código.
    
    La parcial ejecuta todos los fallados del origen y **todos** los tests de cada módulo cambiado (pasados como
    argumento, sin `-k`/`-m` y sin deseleccionados), y queda en verde.
  - **(c) Toca código:** suite completa.
- La reparación sirve solo para la suite **completa** y cuenta para la barrera y para T2 (`tests/consultar_suite.py`).
  La histórica se exige aparte, según §2.2.

## 3. Cambios previstos

| Fichero | Cambio |
|---|---|
| `pytest.ini` | marca `historica`, `required_plugins`, `addopts` con `-n` y `--dist loadgroup` |
| `tests/conftest.py` | registro solo en el proceso principal; cifras de los workers por `workeroutput` |
| `tests/registro_suite.py` | alcances `completa`/`historica`/`total`, `fallados`, `nodeids` |
| `tests/facturas/runtime_supabase/conftest.py` | `SUITE_HISTORICA`, familias `xdist_group`, `pg17_contenedor_tcp` |
| `test_ensayo_despliegue_19_2ax.py`, `test_integracion_pg17_2az.py` | usan `pg17_contenedor_tcp` |
| `.claude/hooks/estado_git.py` | suite exigida (completa e histórica), equivalencia por reparación, histórica semanal y por rutas |
| `.claude/hooks/barreras_agentes.py` | barrera de commit con las reglas nuevas; barrera de `desplegar_<n>` |
| `tests/consultar_suite.py` | T2 con las mismas reglas |
| `docs/contexto/REGLAS_CRITICAS.md`, `ESTADO_ACTUAL.md` | regla de pruebas nueva |
| tests | de la barrera, del registro y de T2 |

Toca `.claude/` y REGLAS_CRITICAS: **pedirá el OK de Pio**. Instalar pytest-xdist: **pedirá el OK de Pio**.

## 4. Estimación de tiempos (antes de medir)

| Suite | Hoy | En serie, sin histórica | 4 workers | 8 workers | 12 workers |
|---|---|---|---|---|---|
| Completa (cada commit de código) | 41 min | ~23–26 min | ~8–10 min | ~5–7 min | ~4–6 min |
| Histórica | dentro de la completa | ~15–18 min | ~5–6 min | ~4–5 min | ~3–4 min |
| Rápida | 2:05 | igual | ~45 s | ~30–40 s | ~30 s |
| Reparación (a) o (b) | 41 min | — | de segundos a ~1–5 min | | |

**Límites:** la familia más larga, la reconstrucción de plantillas en cada worker (1–2 min) y el coste de cada
`docker exec` en Windows (~0,22 s; `pg17_local.py:70-80`). La memoria de Docker es de 16 GB y la CPU de 24 núcleos.

## 5. Medición

`MEDIDO` (2026-11-20, este equipo: 24 núcleos, Docker con 16 GB). Por decisión de Pio se mide solo con 4 y 8
workers (sin 12).

| Suite | Workers | Resultado | Tiempo |
|---|---|---|---|
| Rápida (`-m "not pg17_local"`) | 8 | 2470 passed | 0:49 (antes 2:05) |
| Completa nueva (`-m "not historica"`) | 4 | 3077 passed | 11:57 |
| Completa nueva (`-m "not historica"`) | 8 | 3077 passed | **9:09** (antes, la completa: 41:14) |

- **Valor por defecto: 8** (`pytest.ini`). Con 8 workers la suma de tiempos por test es de ~71 min y el reparto
  queda cerca del ideal (~8:50). La familia más larga, la serie 2BP (~8,3 min en paralelo), marca el mínimo: más
  workers apenas ganarían.
- **Coste del paralelismo:** cada test tarda más en paralelo (la competencia por Docker y `docker exec`). Por eso
  8 workers rinden ~4,5 veces lo de la serie y no 8.
- **Familias:** cada módulo `pg17_local` es su propia familia, salvo los tres de Trabajadores (31, 33 y 34), que
  comparten la cadena de plantillas y van juntos. La serie 2BP queda sola.
- La histórica (127 tests) se mide con la suite final del hito.
