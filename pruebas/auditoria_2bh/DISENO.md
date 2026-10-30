# Hito 2BH: infraestructura de tests (velocidad de `pg17_local` y resultado verificable)

2026-10-30. Solo local. Sin producción, sin Farmatic, sin cambiar qué prueba cada test.

## 1. Velocidad de la suite `pg17_local`

### Diagnóstico (medido)

- La propuesta del encargo (plantilla con las migraciones preparada una vez y copiada por test) **ya existía**:
  `pg17_local.construir_plantilla` construye cada variante de esquema una vez por sesión y `base_desde` da a
  cada test una copia con `createdb -T`.
- Perfil antes del cambio (`--durations=0`, 2026-10-30): suite rápida 2040 tests en **81 s**; `pg17_local`
  205 tests en **35:57** (1.735 s en `call`, 413 s en `setup`).
- Causa: `_Pg.sql` lanzaba un `docker exec psql` **por sentencia**, y el cliente simulado de Supabase hace una
  por cada lectura REST o RPC. Medido en este equipo: **0,225 s** por `docker exec` frente a **0,003 s** en
  una sesión `psql` persistente. Unas 9.500 llamadas por suite.

### Cambio

`tests/facturas/runtime_supabase/pg17_local.py`, `_Sesion`: una sesión `psql` persistente por
(contenedor, base) sobre `docker exec -i` (sigue `--network none`, sin puertos). Por llamada conserva lo que
daba un proceso nuevo:

- `ON_ERROR_STOP=1`: ante un error psql termina (lo ya ejecutado queda, como antes) y se lanza el mismo
  `RuntimeError` con su stderr; la siguiente llamada abre otra sesión;
- tras cada llamada, `rollback` y `discard all`: rol (`set role service_role`), parámetros, transacción
  abierta, temporales, locks de sesión, planes y secuencias, como al cerrar el proceso;
- un `;` final ejecuta una última sentencia sin punto y coma, como hacía psql al llegar a EOF;
- `application_name` = `cf_pg17_test` (no coincide con los filtros de «workers» de los preflight);
- stdout y stderr se leen en hilos (sin bloqueos con salidas grandes); timeout de 180 s, como `_docker`.

Aislamiento: cada test sigue recibiendo su propia copia de la plantilla. Las sesiones se cierran al final de
cada test (fixture `autouse` en `tests/facturas/runtime_supabase/conftest.py`), antes de cada
`createdb -T` sobre su origen (PostgreSQL exige que nadie esté conectado) y al retirar el contenedor. No hay
tests concurrentes (comprobado: ninguno usa hilos ni procesos) ni metacomandos de psql en el SQL ejecutado
salvo `\ir`, que ya se expandía.

### Resultado

| Parte | Antes | Después |
|---|---|---|
| `pg17_local` (205) | 35:57 | **12:21** |
| rápida (2040) | 1:21 | 1:21 |
| completa | ~37 min | ~14 min |

Mismos tests, mismo resultado (todos en verde antes y después). El objetivo de ~10 min no se alcanza sin
paralelizar:
- lo que queda es trabajo real de cada test: la extracción del PDF del 2AO con el worker (~3 s por test que
  la usa), los ensayos de despliegue con su contenedor TCP propio (~9 s por módulo) y los tests que esperan
  errores (cada error cierra psql por `ON_ERROR_STOP`, como antes; p. ej. los dos tests de rol público del
  2AX, 82 errores cada uno, 20 s);
- **propuesta (decisión de Pio, no hecha):** `pytest-xdist` (dependencia nueva) con un contenedor por
  proceso; o compartir el contenedor TCP de los ensayos entre módulos (~45 s).

## 2. Resultado verificable

- `tests/registro_suite.py` + `tests/conftest.py`: al terminar, pytest añade una línea a
  `logs/agentes/suites.jsonl` del proyecto (Git lo ignora). La escribe el ejecutor de pytest, no un test; es
  la única escritura en `logs/` y la pidió Pio.
- Contenido:
  - `huella`: la misma que la barrera de commit y `revisor-reglas` (`estado_git.huella_de(detalle_cambios())`:
    HEAD + SHA-256 de cada ruta cambiada), calculada al empezar y al terminar; si difieren, `huella` es nula y
    `arbol_cambiado_durante_la_suite` verdadero;
  - `base`, `rutas`, fechas, argumentos, passed/failed/errors/skipped, `pg17_colectados` y `pg17_omitidos`,
    código de salida;
  - `alcance`:
    - `completa`: todo `tests/`, sin `-k`/`-m`, nada deseleccionado, todo ejecutado y ningún `pg17_local`
      omitido;
    - `rapida`: lo mismo con `-m "not pg17_local"`;
    - `parcial`: el resto;
  - `verde`: código 0, sin failed ni errors y con huella.
- Un fallo al registrar nunca cambia el resultado de pytest: solo falta la línea (y la barrera bloquea).
- **Barrera de commit** (`.claude/hooks/barreras_agentes.py`), tras el PASS del revisor:
  - suite exigida: `completa` salvo que todo sean `.md` fuera de `.claude/` (`rapida`);
  - exige la última línea con la huella actual y alcance suficiente, y que esté en verde;
  - motivos `commit_sin_suite` y `commit_suite_roja`.
  - Una ejecución parcial posterior no invalida una completa; una completa posterior roja sí.
- **`revisor-reglas` (T2)** puede leer `logs/agentes/suites.jsonl` (política del hook) y exige una línea con
  `base` = HEAD, `rutas` = `git status`, alcance suficiente y `verde`. La barrera compara además la huella
  exacta, que incluye el contenido.
- `logs/agentes` sigue vetado a Write/Edit y a cualquier comando que lo nombre (barrera global).

## 3. Tests

- `tests/test_registro_suite_2bh.py`: alcance (completa, rápida, siete casos parciales), línea completa con la
  huella de la barrera, fallo, árbol cambiado, pg17 omitido, fichero concreto, error al registrar.
- `tests/test_hook_barreras_agentes.py`: sin suite, otro árbol, código con rápida, `.claude/` exige completa,
  documentación con rápida, parcial, roja, parcial posterior, otro repositorio, lectura del revisor y
  huella = detalle. Los dos tests que ya permitían el commit pasan ahora también la suite.
- Suite completa en verde, registrada por el propio mecanismo.
