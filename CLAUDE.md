# ControlFarmacias

Repositorio principal y puerta de entrada versionada:
`C:\ControlFarmacias\Programa` y este archivo. No depender de
`C:\ControlFarmacias\CLAUDE.md` ni de conversaciones anteriores.

## Arquitectura multirepositorio

ControlFarmacias se compone de dos repositorios Git independientes:

```text
ControlFarmacias
|
+-- Programa
|   +-- repositorio principal / main
|
+-- Orquestador CLI cf
    +-- repositorio independiente / v0.2-dev
```

- `C:\ControlFarmacias\Programa` contiene el programa principal. Su rama canónica
  es `main`.
- `C:\ControlFarmacias\ControlFarmacias_Orquestador_V0_2_dev` contiene el CLI
  `cf`. Su rama de desarrollo es `v0.2-dev`.

Las historias Git no tienen `merge-base`. El CLI `cf` V0.2.12 no forma parte de
la historia de `Programa/main`: no se debe interpretar esta separación como
pérdida de trabajo, intentar fusionar las ramas ni tratar `v0.2-dev` como rama
auxiliar de Programa.

`OrquestadorExtraccionProductiva` sí pertenece a Programa y no es el CLI `cf`.

Antes de analizar o modificar el proyecto, lee completos y en este orden:

1. `docs/contexto/CONTEXTO_MAESTRO.md`;
2. `docs/contexto/ESTADO_ACTUAL.md`;
3. `docs/contexto/REGLAS_CRITICAS.md`.

Farmatic es estrictamente de solo lectura y producción no se toca sin preflight,
alcance explícito y confirmación de Pio.

El flujo es factura -> extracción -> normalización -> conciliación -> Supabase.
Ante cualquier duda de identidad, completitud, farmacia o permisos, falla cerrado.
Solo PIO está habilitada; RITA permanece bloqueada. La autoridad productiva de
todos los extractores locales está desactivada.

Estos tres documentos son el contexto canónico compartido por Claude Code y
Codex. Deben prevalecer sobre documentación histórica, según el orden de autoridad
que ellos mismos establecen.
