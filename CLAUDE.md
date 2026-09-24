# ControlFarmacias

Repositorio principal y puerta de entrada versionada:
`C:\ControlFarmacias\Programa` y este archivo. No depender de
`C:\ControlFarmacias\CLAUDE.md` ni de conversaciones anteriores.

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
