# ControlFarmacias — Orquestador supervisado V0

## V0.1.2 — orden correcto de flags Codex CLI

Se corrige la posición de los flags globales `--cd`, `--sandbox`, `--ask-for-approval`
y `--model`: ahora se envían antes de `exec`. `--output-schema` y
`--output-last-message` permanecen después de `exec`.


## V0.1.1 — corrección Windows

Se corrige el lanzamiento de Codex CLI cuando npm instala el comando como `codex.CMD`.
En Windows el orquestador lo ejecuta ahora mediante `cmd.exe`, manteniendo exactamente los mismos
sandbox, permisos, schemas y barreras de seguridad.


## Qué hace

Automatiza el bucle mecánico:

`Tarea aprobada → Codex ejecutor → Codex supervisor read-only → continuar / parar`

Estados del supervisor:

- `AUTO_CONTINUE`: sigue automáticamente con el siguiente paso mecánico.
- `REQUIERE_OK_PIO`: se detiene físicamente y crea `PAUSA_PIO.md`.
- `FINALIZADO`: termina y crea `FINALIZADO.md`.

La V0 **no hace `git add`, commit ni push**.

## Importante: qué NO es todavía

Esta V0 no está conectada directamente a la conversación web de ChatGPT.
El papel de supervisor lo realiza una segunda ejecución de Codex en modo `read-only`
usando las reglas de ControlFarmacias.

Cuando el supervisor detecta una decisión, genera `PAUSA_PIO.md`.
Ese archivo es el que puedes traer a ChatGPT para debatirlo.
Después reanudas el mismo run con tu decisión.

Una V1 futura puede sustituir el supervisor por la Responses API para tener un
supervisor separado del ejecutor.

## Instalación

1. Descomprime esta carpeta en:

   `C:\ControlFarmacias\Orquestador`

2. No la metas todavía dentro del repositorio `Programa`.

3. Comprueba que Codex CLI funciona en PowerShell:

   `codex --version`

4. Ejecuta:

   `INICIAR_ORQUESTADOR.bat`

   o:

   `python orquestador.py --check`

No se instala ninguna librería Python adicional.

## Primera prueba: SOLO LECTURA

Ejecuta:

`python orquestador.py --task tareas\00_prueba_segura.json`

La tarea solo:

- mira Git;
- ejecuta `tests/facturas`;
- informa;
- no puede escribir.

Debe terminar en `FINALIZADO`.

## Cómo funciona una pausa

Si aparece una decisión no mecánica, el proceso termina con una ruta parecida a:

`runs\20260811_...\PAUSA_PIO.md`

Abre ese archivo y tráelo a ChatGPT.

Cuando hayas decidido, reanuda:

`python orquestador.py --resume "C:\ControlFarmacias\Orquestador\runs\..." --decision "TU DECISION"`

La decisión de Pio no elimina las barreras absolutas.

## Tareas con escritura

Usa como base:

`tareas\PLANTILLA_workspace_write.json`

Toda tarea con `"modo": "workspace_write"` exige `rutas_permitidas`.

Ejemplo:

```json
{
  "modo": "workspace_write",
  "rutas_permitidas": [
    "src/facturas/normalizadores/alliance.py",
    "tests/facturas/normalizadores/test_alliance.py"
  ]
}
```

Si Codex toca otra ruta, el orquestador se para aunque el modelo diga que está bien.

## Protección del trabajo ya existente

El orquestador toma una huella SHA-256 de los archivos no seguidos por Git al inicio
de cada ciclo. Así puede detectar también si Codex modifica accidentalmente un
archivo no versionado que ya existía antes.

Esto es importante ahora porque `alliance_08008429/` y `alliance_08008430/`
están deliberadamente sin seguimiento.

## Barreras V0

- No commit/push.
- No staging.
- No cambio de rama o HEAD.
- `.env` protegido.
- patrón oficial protegido.
- Farmatic/SQL Server/Supabase fuera de alcance.
- sin ampliación automática de permisos.
- supervisor siempre `read-only`.
- ejecutor `read-only` o `workspace-write` según la tarea.
- aprobación de comandos configurada como `never`: si el sandbox no permite algo,
  Codex debe adaptarse o detenerse, no pedir más permisos.

## Archivos

- `orquestador.py`: motor.
- `config.json`: ruta del repo y configuración.
- `prompts/reglas_supervisor.md`: reglas permanentes.
- `schemas/executor.schema.json`: contrato de salida del ejecutor.
- `schemas/supervisor.schema.json`: contrato de decisión.
- `tareas/`: tareas.
- `runs/`: historial local de cada ejecución (se crea automáticamente).

## Flujo recomendado

Primero prueba la tarea `00_prueba_segura.json`.

No uses todavía la plantilla con escritura.
Cuando la prueba read-only funcione, el siguiente paso será crear juntos una tarea
mecánica real y pequeña para validar `AUTO_CONTINUE → AUTO_CONTINUE → FINALIZADO`.
