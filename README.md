# ControlFarmacias — Orquestador supervisado V0.1.3

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

## Archivos principales

- `orquestador.py`: motor del flujo supervisado y barreras.
- `orquestador_snapshot.py`: snapshots y comparación del workspace/Git.
- `config.json`: repositorio objetivo, modelos, tiempos y rutas protegidas.
- `prompts/reglas_supervisor.md`: reglas permanentes.
- `schemas/executor.schema.json`: contrato de salida del ejecutor.
- `schemas/supervisor.schema.json`: contrato de decisión del supervisor.
- `tareas/`: definiciones de tareas aprobadas.
- `tests/`: pruebas automáticas del snapshot y las barreras.
- `runs/`: historial local ignorado por Git.
