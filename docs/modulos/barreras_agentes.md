# Barreras y registro de los subagentes del piloto

Fecha de inspección: 2026-10-23. Salvo indicación, cada afirmación es
`CONFIRMADO POR CÓDIGO` (lectura del código, sin ejecutarlo). Las que citan un test son
`CONFIRMADO POR TEST` solo en el sentido de que el test existe y afirma eso: no se ejecutó
en esta revisión.

Es una capa adicional. No sustituye al hook de identidad ni a `obtener_conexion()`, que
siguen siendo la barrera de Farmatic (`.claude/hooks/barreras_agentes.py:17-18`).

## Piezas

| Pieza | Evento | Función | Referencia |
|---|---|---|---|
| `barreras_agentes.py` | PreToolUse, matcher `*` | Bloquea con exit 2 | `.claude/settings.json:226-242` |
| `verificar_identidad_farmatic.py` | PreToolUse, matcher `Bash\|PowerShell\|Monitor` | Exige la identidad `whoami` ante comandos que pueden tocar Farmatic | `.claude/settings.json:209-225`, `.claude/hooks/verificar_identidad_farmatic.py:1-6` |
| `registrar_uso_agente.py` | SubagentStop | Registra uso, coste y veredicto; nunca bloquea | `.claude/settings.json:244-260`, `.claude/hooks/registrar_uso_agente.py:14` |
| `estado_git.py` | Biblioteca | Huella de cambios, rutas de registro y lectura del veredicto | `.claude/hooks/estado_git.py:1-11` |
| `politica.json` | Datos | Parámetros de cada subagente y tarifas | `.claude/agentes/politica.json:3,62,71,82` |

Los tres hooks se lanzan con el Python del `.venv` y `-I -S -B`
(`.claude/settings.json:214-219`, `231-236`, `249-254`). Solo usan la biblioteca estándar
(`barreras_agentes.py:23`, `registrar_uso_agente.py:15`,
`verificar_identidad_farmatic.py:24`). Tiempos máximos: 30 s para los dos de PreToolUse
(`.claude/settings.json:221`, `238`) y 60 s para el de uso (`:256`).

La identidad del subagente llega en `agent_type`; está ausente en la sesión principal
(`barreras_agentes.py:14-15`, `633-635`).

## Orden de decisión

La función `decidir` (`barreras_agentes.py:622-645`) evalúa en este orden:

1. Barreras globales, para todos (`:629-631`).
2. Sin `agent_type` (sesión principal): se permite (`:633-635`).
3. Con política para ese agente, se aplica (`:643-645`). La tabla `POLITICAS` está en
   `:614-619`.
4. Agente sin política: bloquea Write, Edit y NotebookEdit (`agente_desconocido`); el
   resto se permite (`:637-641`).

Una entrada sin `tool_name` o sin `tool_input` válidos lanza error (`:625-626`). Cualquier
error interno bloquea con motivo `error_interno:<Tipo>` (`:681-686`).

Las rutas se resuelven con `realpath` y sin distinguir mayúsculas antes de compararlas
(`:170-173`). Las claves de ruta inspeccionadas son `file_path`, `path`, `notebook_path` y
`glob` (`:49`, `184-189`).

### Registro de bloqueos

Cada bloqueo se añade a `logs/agentes/barreras.jsonl` con `ts`, `agent_type`,
`herramienta`, `decision` y `motivo`. No se guarda el texto del comando
(`barreras_agentes.py:652-671`). El directorio respeta `CONTROLFARMACIAS_LOG_DIR`
(`estado_git.py:28-32`). Un fallo al escribir el registro no cambia la decisión
(`barreras_agentes.py:670-671`).

## Barreras globales (sesión principal y subagentes)

| Motivo | Qué bloquea | Referencia |
|---|---|---|
| `env` | Ruta cuyo nombre empieza por `.env` o que contiene un segmento `.env`; comando de shell que nombra `.env*` | `barreras_agentes.py:54`, `254-257`, `278-279` |
| `service_role` | Ruta o comando de shell que contiene `service_role` | `:258-259`, `274-275` |
| `schtasks` | Comando de shell que contiene `schtasks` | `:276-277` |
| `registro_agentes` | Escritura (Write, Edit, NotebookEdit) dentro de `logs/agentes` o del directorio de logs configurado; comando de shell que nombra `logs/agentes`, `uso.jsonl` o `barreras.jsonl` | `:47`, `260-267`, `280-281` |
| `commit_*` | `git commit` sin PASS vigente de `revisor-reglas` | `:282-283`, `288-306` |

"Shell" significa Bash o PowerShell (`:48`, `269`). Un `command` que no sea texto lanza
error y, por tanto, bloquea (`:271-272`).

## Commit condicionado al PASS de revisor-reglas

1. Al terminar `revisor-reglas`, el hook de uso lee su respuesta y registra `veredicto`,
   `repositorio` y `huella_cambios` (`registrar_uso_agente.py:216-225`).
2. La respuesta es el texto entregado con `SubagentHandback`, si existe; si no, el último
   texto del subagente (`registrar_uso_agente.py:160-180`, `204`).
3. El veredicto sale de la línea `VEREDICTO: PASS|FAIL`, con o sin asteriscos
   (`:66`). Es PASS solo si todas las coincidencias son PASS; varios veredictos distintos
   o ninguno cuentan como FAIL (`:217-220`).
4. La huella es un SHA-256 de `HEAD` más, por cada ruta que `git status` declara cambiada
   (incluidas las no rastreadas y el origen de un renombrado), el SHA-256 de su contenido
   en disco o `BORRADO`. No depende del índice (`estado_git.py:3-8`, `57-91`).
5. El veredicto queda ligado al repositorio que revisó el subagente, que puede ser un
   worktree temporal: la raíz sale del `cwd` del subagente, no del proyecto por defecto
   (`registrar_uso_agente.py:221-225`; clave normalizada en `estado_git.py:111-112`).
6. Al ver `git commit`, `barrera_commit` calcula la huella actual del proyecto y toma el
   último registro de `revisor-reglas` del proyecto. Los registros de otros repositorios se
   ignoran; uno sin campo `repositorio` cuenta como del proyecto
   (`barreras_agentes.py:289-290`, `estado_git.py:115-128`).

| Motivo | Condición | Referencia |
|---|---|---|
| `commit_sin_revisor` | No hay registro del revisor para el proyecto | `barreras_agentes.py:291-295` |
| `commit_revision_desfasada` | La huella registrada difiere de la actual | `:296-300` |
| `commit_revisor_fail` | El veredicto no es PASS | `:301-305` |

Cualquier edición posterior a la revisión cambia la huella y obliga a revisar de nuevo.
`logs/` está ignorado por Git, de modo que escribir registros no altera la huella
(`estado_git.py:6-8`).

Límite: la barrera solo mira comandos de shell que casen con `git ... commit`
(`barreras_agentes.py:282-283`).

## Políticas por subagente

### revisor-reglas

Lectura restringida (`barreras_agentes.py:319-337`):

- Read (campo `file_path`) y Grep (campo `path`) exigen una ruta concreta; sin ella,
  `lectura_fuera_de_diff` (`:328-331`).
- Solo se permiten dos conjuntos de ficheros, calculados sobre el repositorio del `cwd`:
  `docs/contexto/REGLAS_CRITICAS.md` y las rutas que `git status` declara cambiadas
  (los ficheros tocados por el diff, con no rastreadas y orígenes de renombrado). El
  contenido del diff se obtiene con `git diff`. Cualquier otra ruta:
  `lectura_fuera_de_diff` (`:319-324`, `332-336`; `estado_git.py:57-76`).
- Glob queda bloqueado, igual que cualquier otra herramienta no shell:
  `herramienta_no_permitida` (`barreras_agentes.py:338-339`).
- De shell, solo `git diff`, `git status` y `git log` (`comando_no_permitido`,
  `:343-344`).
- Se rechazan los metacaracteres de encadenado, redirección o sustitución
  (punto y coma, `&`, `|`, `<`, `>`, comilla invertida, `$` y saltos de línea; motivo
  `encadenado`) (`:52`, `341-342`).
- Se rechazan el argumento `-c` y `--output`, `--ext-diff`, `--textconv`, `--no-index`,
  `--exec` (motivo `argumento_git`) (`:56-62`, `345-347`).

### adaptador-facturas

- Read, Grep y Glob libres (`:352-353`).
- Write y Edit solo en `src/facturas/motor_local/adaptadores` y
  `tests/facturas/motor_local` (`politica.json:72-75`, `barreras_agentes.py:362-364`).
- Protegidos, con mensaje `REQUIERE_OK_PIO` y motivo `ruta_protegida`: `registro.py`,
  `__init__.py` y `base.py` de adaptadores. Se comprueba antes que la ruta permitida
  (`politica.json:76-80`, `barreras_agentes.py:357-361`).
- Shell: solo pytest con el Python del `.venv`, sin encadenar (`:365-374`) y con
  `--basetemp` (`sin_basetemp`, `:375-376`).
- NotebookEdit y otras herramientas: `herramienta_no_permitida` (`:378`).

### documentador

- Read, Grep y Glob libres (`:382-383`).
- Write y Edit solo en `docs/` (`politica.json:83-85`, `barreras_agentes.py:389-391`).
- `docs/contexto` protegido, con motivo `ruta_protegida` y mensaje "los documentos
  canónicos los actualiza la sesión principal" (`politica.json:86-88`,
  `barreras_agentes.py:387-388`).
- Cualquier otra herramienta, incluida la shell, queda bloqueada (`:392`).

### explorador-farmatic

- Read, Grep y Glob libres; otras herramientas salvo shell, bloqueadas (`:587-590`).
- Shell: solo `<python del .venv> [-B] -c "<código>"` (`:593-602`). `$`, comilla invertida
  y saltos de línea se rechazan en cualquier posición; `;&|<>()` solo dentro de comillas
  (`:204-219`).
- El código se valida con el AST: lista blanca de nodos, atributos, builtins e
  importaciones (`:133-151`, `491-524`). Solo importa funciones listadas de
  `src.sql_explorer` y `obtener_conexion` (`:79-110`).
- Las funciones de ejecución solo aceptan el resultado de un constructor, nunca SQL
  escrito a mano (`:66-71`, `554-581`).
- Los constructores exigen `esquema` y `tabla` literales y columnas literales
  (`:439-455`).
- Límite de filas: entero literal entre 1 y `top_maximo` (50) y obligatorio en los
  constructores que lo tienen (`:456-459`, `474-475`; `politica.json:6`).
- La clasificación de tablas (siguiente sección) se aplica al constructor
  (`:477-487`).
- Acceso a Farmatic: se comprueba después de validar el código y solo pasa si
  `acceso_farmatic` es `true`; si no, `farmatic_sin_ok` (`:603-610`). Hoy es `true`, por
  OK de Pio del 2026-10-23 (`politica.json:4-5`). El hook de identidad exige además la
  sesión `MOSTRADOR\ControlFarmaciasRO` (`politica.json:5`,
  `verificar_identidad_farmatic.py:36`, `141-153`).

## Clasificación de tablas de Farmatic

`clasificar_tabla` devuelve una de tres clases (`barreras_agentes.py:395-420`). El nombre se
compara sin esquema, sin corchetes y sin distinguir mayúsculas (`:406-407`). Orden de
evaluación:

| Orden | Regla | Clase | Referencia |
|---|---|---|---|
| 1 | Tabla en `columnas_restringidas` con `activa` igual a `true` | `RESTRINGIDA` | `:408-411` |
| 2 | Tabla en `columnas_restringidas` inactiva | `SOLO_ESTRUCTURA`, motivo `tabla_restringida_inactiva` | `:412`, `479` |
| 3 | Nombre en `excepciones` | `DATOS` | `:414-415` |
| 4 | Nombre en `exactas` | `SOLO_ESTRUCTURA` | `:416-417` |
| 5 | Coincide con algún patrón regex de `patrones` | `SOLO_ESTRUCTURA` | `:418-419` |
| 6 | Resto | `DATOS` | `:420` |

Las funciones de tipo `ESTRUCTURA` (catálogo y recuento total) no pasan por esta
clasificación y funcionan en todos los objetos (`:66-67`, `79-110`, `566-583`).

### Estructura y datos (`DATOS`)

Cualquier tabla no marcada. El constructor se acepta y se pueden ejecutar filas
(`barreras_agentes.py:477-488`). La intención declarada es que el resto de Farmatic admita
estructura y datos (`politica.json:8`).

### Solo estructura

Tablas con datos personales: metadatos y recuento total, nunca filas ni valores
(`politica.json:8`). Un constructor que apunte a ellas se bloquea con
`tabla_solo_estructura` (`barreras_agentes.py:477-480`).

- Patrones (cliente, paciente, receta, tarjeta, venta, ticket, caja, factura, histórico y
  otros): `politica.json:9-37`.
- Exacta: `TIPOCLIENTE` (`politica.json:38-40`).
- Excepciones que vuelven a `DATOS`: `LineaFacturaCompra`, `Fedicom_Factura`,
  `Fedicom_AlbaranFactura`, `Fedicom_CargoFactura`, `vFedicom_Factura`
  (`politica.json:41-47`).

### Columnas restringidas: `Factura`

`Factura` está en `columnas_restringidas` y activa por OK de Pio del 2026-10-23
(`politica.json:49-52`). La nota de `politica.json:58` la describe como tabla mixta de
compras a proveedor y facturas emitidas a clientes y cita `spec_compras D14`; esa cita no se
ha verificado aquí (`PENDIENTE`). Las cifras de filas de esa nota no se reproducen.

- Se permite leerla con columnas explícitas (`politica.json:58`).
- Se bloquean `CliPro`, `Nif` y `Titular` (`politica.json:53-57`) con motivo
  `columna_excluida` (`barreras_agentes.py:484-487`).
- `ver_tabla.construir_consulta` lee todas las columnas (SELECT \*) y se bloquea con
  `select_todas_restringida` (`:129-131`, `482-483`).
- Se revisan las columnas de resultado, de filtro y de orden, y las demás de
  `PARAMETROS_COLUMNA` (`:124-127`, `443-455`, `485-487`).

Cambiar `acceso_farmatic`, `solo_estructura` o `columnas_restringidas` requiere OK de Pio
(`politica.json:2`).

## Registro de uso

`registrar_uso_agente.py` añade una línea JSON a `logs/agentes/uso.jsonl` por subagente
(`:3`, `241-247`; ruta en `estado_git.py:35-36`). Campos (`:190-214`):

| Campo | Contenido |
|---|---|
| `ts`, `agent_type`, `agent_id`, `session_id` | Identificación (`:192-197`) |
| `modelo` | Último modelo visto en el transcript (`:123`) |
| `tarea` | Primeros 300 caracteres del primer mensaje de usuario no meta (`:29`, `81-83`, `110-113`) |
| `tokens` | Suma por petición a la API (ver abajo) |
| `coste` | `{usd, eur}` o `null` |
| `peticiones_api` | Número de peticiones distintas (`:154`) |
| `llamadas_herramientas` | Bloques `tool_use` del subagente (`:136-140`) |
| `herramientas_bloqueadas` | Resultados con error que contienen `BLOQUEADO` (`:115-120`) |
| `resultado` | Primeros 300 caracteres de la respuesta (`:213`) |
| `veredicto`, `repositorio`, `huella_cambios` | Solo `revisor-reglas` (`:216-225`) |

### Tokens y desglose de caché

- Se registran `input_tokens`, `output_tokens`, `cache_creation_input_tokens`,
  `cache_read_input_tokens` y el desglose de la escritura de caché
  `ephemeral_5m_input_tokens` y `ephemeral_1h_input_tokens` (`:30-36`, `145-148`).
- Una petición a la API aparece en varias entradas del transcript y su uso crece mientras se
  emite. Por eso se toma el máximo de cada campo por petición y luego se suman las
  peticiones (`:87-90`, `127-134`).
- El desglose se lee de `usage.cache_creation` si no está al nivel superior (`:130-132`).

### Coste en USD y EUR

- `calcular_coste` multiplica entrada, salida, lectura de caché, escritura de caché a 5
  minutos y escritura a 1 hora por su tarifa, divide entre un millón y devuelve USD y EUR
  redondeados a 4 decimales (`:40-58`).
- Escritura a 5 minutos = `cache_creation_input_tokens` menos la de 1 hora; sin desglose,
  toda la escritura se cuenta a la tarifa de 5 minutos (`:41-43`, `49-50`).
- Si el modelo no está en la tabla, o falla la lectura de `politica.json`, el coste es
  `null` (`:46-48`, `183-187`).
- Tarifas (USD por millón de tokens) para `claude-opus-5-5`, `claude-sonnet-5-5` y
  `claude-haiku-5-5`, y `eur_por_usd` = 0,86: `politica.json:62-69`.
- Estado de esos datos, según la propia política (`politica.json:63`): entrada, salida y
  lectura de caché de Opus y Sonnet vienen de la tabla de precios de Anthropic;
  escrituras de caché y lectura de Haiku son `INFERIDO`; `eur_por_usd` es `PROVISIONAL` y
  `REQUIERE_OK_PIO`.

### Fallos

- Sin transcript: se registra `error: transcript_no_disponible` (`:198-201`).
- Error interno: se registra `error` con el nombre de la excepción (`:236-240`).
- Si falla escribir el registro se ignora, y el hook devuelve siempre 0 (`:246-248`).

## Mensajes en UTF-8

Claude Code lee `stderr` como UTF-8; el valor por defecto de Windows (cp1252) corrompe los
acentos. Los dos hooks de PreToolUse escriben el mensaje codificado en UTF-8 sobre
`sys.stderr.buffer`:

| Hook | Referencia código | Test |
|---|---|---|
| `barreras_agentes.py` | `:690-697` | `tests/test_hook_barreras_agentes.py:510-514` (el helper decodifica de forma estricta, `:469-470`) |
| `verificar_identidad_farmatic.py` | `:241-249` | `tests/test_hook_identidad_farmatic.py:272-283` |

Los ficheros de registro también se escriben en UTF-8 (`barreras_agentes.py:668`,
`registrar_uso_agente.py:244`, `verificar_identidad_farmatic.py:209`).

Nota `HISTÓRICO`: una prueba en vivo del 2026-10-23, hecha antes de esta corrección,
mostró acentos corruptos en el mensaje de bloqueo de `ruta_protegida`. Ya no es el
comportamiento del código vigente.

## Hook de identidad: mensajes y registro

Solo lo relativo a mensajes y registro (`verificar_identidad_farmatic.py`):

- Si un comando contiene un patrón sensible (`sql_explorer`, `obtener_conexion`, `odbc`,
  `sqlcmd` y otros) y `whoami` no devuelve `mostrador\controlfarmaciasro`, bloquea con el
  mensaje "BLOQUEADO por el hook de identidad Farmatic" (`:36`, `41-57`, `141-153`).
- Un error interno bloquea con el mensaje "BLOQUEADO: error interno del hook de
  identidad Farmatic" y motivo `error_interno:<Tipo>` (`:226-237`).
- Registra cada decisión sobre un comando con patrón sensible y cada error interno en
  `%LOCALAPPDATA%\ControlFarmacias\hooks\identidad_farmatic.jsonl`, fuera del
  repositorio. Nunca guarda el texto del comando ni el mensaje de las excepciones
  (`:17-22`, `61-62`, `163-169`, `185-198`).
- Al llegar a 5 MiB, rota el registro a `.1` (`:62`, `203-207`).
- Limitación aceptada por Pio: un fallo de arranque del intérprete, un error de sintaxis
  o el timeout no bloquean el comando (`:12-15`).

## Verificación pendiente

- No se ejecutaron los tests citados en esta revisión.
- La cita `spec_compras D14` de `politica.json:58` no se ha comprobado (`PENDIENTE`).
