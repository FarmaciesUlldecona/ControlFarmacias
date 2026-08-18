# ControlFarmacias — Orquestador supervisado V0.2

## Tareas persistentes (V0.2.1)

V0.2 introduce una entidad de tarea persistente, superior e independiente de los
`runs/`. Cada tarea se guarda en su propio JSON dentro de `estado/tareas/` mediante
escritura atómica, e incluye su contrato, estado e historial append-only.

Los estados admitidos son `PREPARANDO`, `TRABAJANDO`, `ESPERANDO_DECISION`,
`RECUPERANDO`, `BLOQUEADA`, `FINALIZADA` y `CANCELADA`. Las transiciones están
controladas; `FINALIZADA` y `CANCELADA` son terminales. El contrato conserva el
objetivo, permisos y prohibiciones, condiciones de finalización, restricciones,
autorizaciones de commit/push y presupuesto API.

El alcance de V0.2.1 es solo el modelo, validación, persistencia e API interna de
tareas. Todavía no integra interfaz gráfica, lenguaje natural/IA, ejecución de
Codex, `--task`, `--resume`, locks, cola, costes reales, commits, push, múltiples
agentes ni arquitectura distribuida.

## Entornos y locks (V0.2.2)

Una tarea puede describir su entorno mediante repositorio, worktree, rama, HEAD
inicial y modo. La capa de entornos comprueba en solo lectura que el path y el
repositorio Git sean válidos y detecta diferencias de rama, HEAD o repositorio sin
hacer `checkout`, `reset` ni otras correcciones automáticas.

Cada worktree admite una única tarea activa, incluso cuando ambas tareas sean
`read_only`. Los locks se conservan como JSON independientes en `estado/locks/`,
con identidad de path normalizada para Windows, creación exclusiva atómica y
metadata de auditoría. Worktrees diferentes sí pueden reservarse simultáneamente.

Un reinicio no elimina locks. Una sesión posterior los diagnostica como posibles
huérfanos y bloquea de forma conservadora hasta que una capa superior decida. Solo
el propietario puede liberar explícitamente su lock y, en V0.2.2, debe estar en
`FINALIZADA` o `CANCELADA`. Esta versión aún no ejecuta Codex ni recupera locks de
forma automática.

## Tareas y runs integrados (V0.2.3)

La tarea persistente representa el objetivo global y continúa siendo la fuente de
verdad. Un run representa un intento concreto y queda subordinado mediante
`task_id`; una tarea puede acumular varios runs numerados dentro de `runs/`, con su
entorno, snapshot inicial, resultado y relación de reanudación.

Antes de preparar un run se comprueban estado no terminal, lock propietario no
ambiguo, repositorio, rama y HEAD. Al registrar el resultado se repiten las
validaciones y se compara el snapshot usando las barreras de rutas ya probadas por
el motor histórico. La capa V0.2 consume sus estados mediante un adaptador interno:
`AUTO_CONTINUE` mantiene `TRABAJANDO`, `REQUIERE_OK_PIO` propone
`ESPERANDO_DECISION` y las pausas con barrera proponen `BLOQUEADA`.

`FINALIZADO` es únicamente un candidato a `FINALIZADA`: nunca cierra la tarea de
forma automática, aunque las validaciones sean correctas. V0.2.3 prepara también
un resume como un intento nuevo ligado al run pausado, conservando el mismo
`task_id`, pero todavía no automatiza decisiones humanas ni ejecuta Codex mediante
esta API.

## Ejecución in-process y Codex real (V0.2.4)

V0.2 dispone de un `EjecutorCiclo` inyectable. La implementación fake permite
probar el flujo completo sin procesos externos ni consumo API; la implementación
real llama directamente a `ejecutar_ciclo` dentro del proceso V0.2. Solo Codex se
lanza como subprocess: nunca se inicia un segundo Orquestador V0.1.3.

Antes de invocar el ejecutor se vuelven a comprobar tarea, lock, repositorio, rama,
HEAD y snapshot. Cada ejecución conserva `stdout.txt`, `stderr.txt` y
`execution.json` dentro de su run, incluyendo timestamps, PID observado, return
code, timeout configurable y errores técnicos. La integridad posterior prevalece
sobre el resultado funcional: cualquier escritura en `read_only` bloquea aunque
Codex declare éxito.

Pytest bloquea por defecto el ejecutor real y utiliza fakes. La comprobación con
Codex real es un smoke test manual, explícito y separado. V0.2.4 todavía no
automatiza decisiones humanas, reanudaciones conversacionales ni cancelación de
procesos desde una interfaz.

## Decisiones persistentes y resume automático (V0.2.5)

Una pausa no bloqueante (`REQUIERE_OK_PIO` o `PAUSA_PIO`) crea una decisión
persistente en `estado/decisiones/`, vinculada por UUID a la tarea y al run que la
originó. La decisión conserva pregunta, contexto, opciones cerradas, respuesta
estructurada, tipo, impacto, autorizaciones y estados `PENDIENTE`, `RESPONDIDA`,
`APLICADA` o `CANCELADA`.

Una respuesta válida se registra sin interpretación mediante IA y activa el resume
desde la API interna V0.2: se crea un run nuevo con el mismo `task_id`, referencia
`resume_de` al run pausado y asociación al `decision_id`. El ciclo se ejecuta
in-process mediante el adaptador existente; no se lanza V0.1.3 ni se requiere un
segundo comando manual `--resume`.

La aplicación es idempotente. Cada decisión puede asociarse a un único run de
resume y una segunda aplicación recupera ese resultado sin volver a ejecutar el
adaptador. V0.2.5 admite entradas estructuradas y opciones exactas, pero todavía
no interpreta frases libres de Pio, no aplica lógica real de costes/commit/push y
no finaliza automáticamente una tarea porque un run devuelva `FINALIZADO`.

## Recuperación durable (V0.2.6)

`ServicioRecuperacion.recuperar_estado()` reconstruye al arrancar únicamente las
tareas no terminales. Contrasta tarea, último run, decisión, lock, rama, HEAD,
workspace, proceso y último checkpoint. Una decisión `PENDIENTE` continúa en
espera; una `RESPONDIDA` puede reanudarse una sola vez tras validar precondiciones;
y un run `PREPARADO` puede iniciar ese mismo run sin crear otro.

Para runs `INICIADO`, `procesos.json` conserva atómicamente PID, comando,
timestamp, `run_id` y `session_id`. Un proceso solo se considera activo si su
identidad coincide; un PID ambiguo bloquea y nunca se mata. Si el proceso
desapareció, la tarea entra en `RECUPERANDO`: un `execution.json` completo y
coherente se reconcilia sin ejecutar de nuevo, mientras que evidencia incompleta
marca el run `INTERRUMPIDO`, nunca como éxito.

Los locks de otra sesión no se eliminan por antigüedad. Solo se adoptan de forma
controlada cuando pertenecen a la misma tarea activa, el PID anterior no existe y
Git sigue íntegro. Rama, HEAD, repositorio o cambios de workspace inexplicables
producen `BLOQUEADA` sin checkout, reset, clean ni liberación destructiva.

`estado/checkpoints/` ofrece checkpoints básicos por tarea/run con payload,
metadata y marca de validación. La recuperación es idempotente: repetirla sin
cambios externos no duplica runs, decisiones, ejecuciones ni eventos equivalentes.
El alcance actual es recuperación al arrancar o bajo demanda; no incluye watchdog,
rollback, cola, multiagente ni recuperación distribuida.

## Arranque controlado y retries (V0.2.7)

`ServicioArranque.iniciar_orquestador()` inicializa el almacenamiento y ejecuta la
recuperación durable antes de aceptar trabajo. El estado global del Orquestador es
independiente del estado de cada tarea y transita por `INICIANDO`, `RECUPERANDO` y
`LISTO`, o queda `BLOQUEADO` si existen locks o entornos ambiguos. Mientras no está
`LISTO`, cualquier nueva ejecución devuelve `ORCHESTRATOR_NOT_READY` como resultado
funcional. El resumen de arranque y sus eventos quedan auditados en
`estado/orquestador/`.

Las tareas y runs declaran una capacidad de checkpoint: `NONE`, `FULL_RUN_ONLY` o
`CHECKPOINT_RESUME`. Un checkpoint solo puede sustentar un retry cuando pertenece a
la tarea y run origen, está validado, su metadata es coherente, el entorno continúa
compatible y no existe evidencia posterior que lo invalide.

`ServicioReintentos.preparar_reintento()` crea un `PlanReintento` persistente, pero
no ejecuta nada. La llamada explícita `ejecutar_reintento()` crea un run nuevo,
conserva el histórico y relaciona `retry_id`, run interrumpido y checkpoint. La
estrategia `RETRY_FROM_CHECKPOINT` comunica al ejecutor las acciones validadas que
puede omitir; `RETRY_FULL_RUN` declara expresamente que habrá repetición y no finge
granularidad inexistente. Preparación, ejecución y cancelación son idempotentes y
un run posterior exitoso impide duplicar trabajo.

V0.2.7 sigue sin incluir GUI, lenguaje natural, cálculo monetario, watchdog,
rollback ni ejecución automática de retries al detectar una interrupción.

## Fachada operativa y contrato del ejecutor (V0.2.8)

`OrquestadorV02` es la fachada pública única. Un consumidor crea la instancia,
llama a `iniciar()` y espera `ORCHESTRATOR_READY`; antes de `LISTO`, las operaciones
ejecutables devuelven `ORCHESTRATOR_NOT_READY`. La fachada ofrece creación y consulta
de tareas, ejecución de ciclos, decisiones y resume automáticos, cancelación segura,
retries y `resumen_sistema()` sin exigir IDs de run, locks, rutas de estado ni
comandos `--resume`.

Las operaciones públicas devuelven `ResultadoPublicoV02`, con código funcional,
mensaje, IDs relacionados, estados, datos, warnings y errores. Situaciones esperables
como tarea inexistente, terminal, bloqueada, entorno inválido, worktree ocupado o
decisión requerida no obligan a capturar excepciones internas.

`ContratoEjecutorV02` formaliza ciclo normal, resume, soporte de retries, capacidad
de checkpoint, validación, construcción y consumo del contexto. Un
`RETRY_FROM_CHECKPOINT` solo puede finalizar correctamente cuando la evidencia del
ejecutor confirma el mismo checkpoint recibido/utilizado, estrategia, acciones
omitidas, acciones ejecutadas y posición de reanudación disponible. Cualquier
mismatch persiste `RETRY_EVIDENCE_INVALID` y falla el run. `FULL_RUN_ONLY` prohíbe
afirmar reutilización granular; el ejecutor Codex actual se clasifica honestamente
con esa capacidad.

La CLI histórica mantiene `--task`, `--resume`, `--decision` y `--check`. El nuevo
`--v02-status` inicia la fachada, ejecuta recovery y muestra el estado global sin
ejecutar una tarea. V0.2.8 todavía no incorpora GUI, lenguaje natural ni control
agresivo de procesos activos.

## Finalidad

El Orquestador V0.1.3 automatiza tareas mecánicas previamente aprobadas sobre el
repositorio ControlFarmacias sin delegar decisiones nuevas al ejecutor. Su flujo es:

`Tarea aprobada → ejecutor Codex → supervisor Codex read-only → continuar, pausar o finalizar`

El ejecutor trabaja en modo `read_only` o `workspace_write`, según la tarea. El
supervisor siempre se ejecuta en modo `read-only`: revisa el resultado, el estado Git
y las rutas modificadas, pero no programa ni corrige archivos.

## Estados del supervisor

- `AUTO_CONTINUE`: autoriza el siguiente paso únicamente cuando es mecánico,
  inequívoco y ya está comprendido en el objetivo aprobado.
- `REQUIERE_OK_PIO`: detiene físicamente el run cuando aparece una decisión,
  desviación o barrera y genera `PAUSA_PIO.md`.
- `FINALIZADO`: confirma que el criterio aprobado está satisfecho y genera
  `FINALIZADO.md`.

## Snapshot y detección de cambios

En cada ciclo el orquestador toma un snapshot inmediatamente antes y después del
ejecutor. El snapshot registra:

- huellas SHA-256 del contenido del workspace, incluidos archivos no versionados;
- HEAD y rama actuales;
- rutas staged y unstaged;
- huellas de los deltas staged y unstaged.

La comparación antes/después permite atribuir al ciclo solo los cambios nuevos,
incluso si el repositorio ya estaba sucio al comenzar. También detecta cambios en
archivos no versionados que existían previamente.

## Modos de ejecución

### `read_only`

No admite cambios en el workspace. Cualquier escritura detectada activa una pausa.

### `workspace_write`

Exige una lista `rutas_permitidas`. El ejecutor solo puede escribir en las rutas o
patrones explícitamente autorizados; cualquier cambio fuera de la allowlist activa
una barrera dura antes de invocar al supervisor.

Ejemplo:

```json
{
  "modo": "workspace_write",
  "rutas_permitidas": [
    "pruebas/orquestador_v0/**"
  ]
}
```

La plantilla está en `tareas/PLANTILLA_workspace_write.json`.

## Barreras duras

La V0.1.3 detiene el run y solicita intervención de Pio si detecta, entre otros casos:

- una ruta protegida modificada, incluidos `.env`, `.env.*` y sus equivalentes en
  subdirectorios;
- una escritura en modo `read_only`;
- una escritura fuera de `rutas_permitidas` en modo `workspace_write`;
- un cambio de HEAD o de rama;
- un cambio en el índice Git (`git add` o staging);
- una modificación realizada durante el turno read-only del supervisor;
- una decisión de negocio, arquitectura, datos, seguridad, costes, dependencias,
  red o ampliación de alcance.

La decisión humana al reanudar no elimina ni relaja estas barreras.

## Pausa y reanudación

Cuando el estado es `REQUIERE_OK_PIO`, el run conserva su estado y genera
`PAUSA_PIO.md`. Tras una decisión explícita de Pio, se reanuda el mismo run:

```powershell
python orquestador.py --resume "C:\ruta\al\run" --decision "DECISIÓN EXPRESA DE PIO"
```

El ejecutor recibe literalmente la decisión para continuar desde el punto pausado.
El archivo de pausa atendido se conserva como historial del run.

## Validaciones completadas en V0.1.3

Se han validado satisfactoriamente:

- `read_only → FINALIZADO`;
- snapshot/baseline con un repositorio previamente sucio;
- `AUTO_CONTINUE` en un flujo multiciclo;
- `REQUIERE_OK_PIO` y generación de `PAUSA_PIO.md`;
- `--resume` con una decisión explícita de Pio;
- detección de una modificación prohibida de `.env` en un repositorio Git temporal;
- escritura permitida y escritura fuera de allowlist en repositorios Git temporales;
- una tarea real `workspace_write` limitada a un único archivo inocuo en
  ControlFarmacias;
- conservación de la rama y de HEAD del repositorio objetivo durante la validación.

Las pruebas automáticas usan repositorios temporales de pytest, datos ficticios y no
dependen de red ni de credenciales reales.

## Límites de la V0

- No está conectada directamente a una conversación web de ChatGPT ni a la
  Responses API; ejecutor y supervisor son invocaciones separadas de Codex CLI.
- No amplía permisos ni resuelve decisiones ambiguas automáticamente.
- No realiza `git add`, commit ni push como parte de los runs.
- Commit y push requieren siempre una acción explícita y separada de Pio.
- No accede a Supabase ni usa red salvo que una versión futura lo autorice de forma
  expresa.
- Farmatic y SQL Server continúan siendo exclusivamente de solo lectura; esta V0 no
  autoriza escrituras sobre ellos.
- La aprobación de comandos del ejecutor está configurada como `never`: si el
  sandbox impide una acción, debe adaptarse dentro del alcance o detenerse.

## Uso

Comprobación del entorno:

```powershell
python orquestador.py --check
```

Nueva tarea:

```powershell
python orquestador.py --task tareas\00_prueba_segura.json
```

No se requieren librerías Python adicionales para ejecutar el orquestador. Los runs
se guardan localmente en `runs/`, que está excluido de Git junto con cachés,
temporales y bytecode.

## Supervisor determinista V0.2.9

`SupervisorV02` evalúa solicitudes estructuradas, sin IA ni lenguaje natural
libre, antes de crear una decisión para Pio. Aplica esta jerarquía: reglas
absolutas del proyecto, restricciones de la tarea, reglas funcionales aprobadas,
autorizaciones del contrato, decisiones puntuales de Pio, objetivo de la tarea y,
por último, decisiones técnicas seguras.

El catálogo persistente distingue reglas absolutas de reglas funcionales. Farmatic
y SQL Server son siempre de solo lectura; en facturas rige cero invenciones y el
nombre del PDF no constituye evidencia. Las reglas funcionales tienen condición y
acción estructuradas, prioridad, versión, estado activo e historial de activación.
Desactivar conserva tanto la regla como los eventos que acreditan usos anteriores.
Una respuesta puntual de Pio no se convierte en regla: la incorporación permanente
solo ocurre mediante `registrar_regla(...)` explícito.

Las autorizaciones ya presentes en el contrato —modo de escritura, commit, push,
presupuesto, acciones y rutas— no vuelven a preguntarse. Una prohibición tampoco se
somete a consulta para intentar eludirla. Las decisiones técnicas seguras dentro
del alcance se autoaprueban; las funcionales nuevas, los conflictos de igual
prioridad y las situaciones ambiguas requieren a Pio.

En una pausa, el servicio evalúa primero `state_historico.solicitud_supervisor`.
Una regla aplicable registra evidencia y crea automáticamente un run de resume; una
violación absoluta bloquea la tarea sin preguntar; solo un caso no resuelto crea
una decisión persistente. La fachada pública añade `evaluar_accion`,
`listar_reglas`, `registrar_regla`, `desactivar_regla` y `obtener_evaluacion`.

## Lenguaje natural seguro V0.2.10

`InterpreteOrdenNatural` convierte exclusivamente órdenes recibidas por el canal
explícito del usuario en una `OrdenInterpretada` tipada. Un parser local resuelve
consultas y expresiones deterministas (solo lectura, negaciones de commit/push,
coste máximo, continuar y cancelar) sin API. Las órdenes no triviales pueden usar
un `ProveedorInterpretacion` inyectable que debe devolver el schema estricto; las
pruebas utilizan un fake y nunca llaman a IA ni Codex reales.

La interpretación conserva acciones secuenciales, condiciones, restricciones,
autorizaciones, referencias, datos faltantes y ambigüedades. No es una fuente de
autoridad: cualquier operación ejecutable pasa por los contratos y por
`SupervisorV02`, y las reglas absolutas siguen prevaleciendo. La validación impide
que un proveedor amplíe `read_only`, commit o push, rechaza acciones desconocidas
presentadas como seguras y no ejecuta interpretaciones incompletas o incoherentes.

La fachada `OrquestadorV02.procesar_orden(texto)` exige estado global `LISTO`,
resuelve referencias solo cuando existe una candidata inequívoca y atiende
consultas de estado o Git desde persistencia/localmente sin crear tareas ni lanzar
Codex. La orden original, interpretación y resultado quedan en una bitácora
append-only. Texto procedente de archivos, README, stdout o documentos externos
se trata como datos y no puede crear órdenes ni autorizaciones.

## Archivos principales

- `reglas_persistentes.py`: catálogo, versionado y reglas iniciales V0.2.9.
- `supervisor_v02.py`: jerarquía y evaluación determinista V0.2.9.
- `lenguaje_natural.py`: parser, modelo tipado, proveedor inyectable y trazabilidad V0.2.10.
- `schemas/orden_interpretada.schema.json`: contrato estricto de interpretación V0.2.10.

- `tareas_persistentes.py`: modelo, contrato, estados y persistencia atómica V0.2.1.
- `entornos.py`: validación Git y reservas exclusivas persistentes V0.2.2.
- `runs_persistentes.py`: relación tarea/run y adaptador del motor histórico V0.2.3.
- `ejecucion_v02.py`: ejecutores fake/real y servicio de ejecución V0.2.4.
- `decisiones_persistentes.py`: decisiones, respuestas y trazabilidad V0.2.5.
- `recuperacion.py`: clasificación, reconciliación e idempotencia V0.2.6.
- `checkpoints_persistentes.py`: checkpoints mínimos persistentes V0.2.6.
- `arranque.py`: estado global, recovery obligatorio y puerta de ejecución V0.2.7.
- `reintentos_persistentes.py`: planes y ejecución explícita de retries V0.2.7.
- `contrato_ejecutor.py`: protocolo y evidencia verificable del ejecutor V0.2.8.
- `fachada_v02.py`: fachada operativa y resultados públicos V0.2.8.
- `estado/tareas/`: tareas persistentes locales (un JSON por tarea, excluido de Git).
- `estado/locks/`: locks locales de worktree (un JSON por entorno, excluido de Git).
- `estado/decisiones/`: decisiones persistentes locales (excluidas de Git).
- `estado/checkpoints/`: checkpoints persistentes locales (excluidos de Git).
- `estado/retries/`: planes de retry persistentes locales (excluidos de Git).
- `estado/orquestador/`: resumen y eventos auditables del arranque.
- `orquestador.py`: motor del flujo supervisado y barreras.
- `orquestador_snapshot.py`: snapshots y comparación del workspace/Git.
- `config.json`: repositorio objetivo, modelos, tiempos y rutas protegidas.
- `prompts/reglas_supervisor.md`: reglas permanentes.
- `schemas/executor.schema.json`: contrato de salida del ejecutor.
- `schemas/supervisor.schema.json`: contrato de decisión del supervisor.
- `tareas/`: definiciones de tareas aprobadas.
- `tests/`: pruebas automáticas del snapshot y las barreras.
- `runs/`: historial local ignorado por Git.
