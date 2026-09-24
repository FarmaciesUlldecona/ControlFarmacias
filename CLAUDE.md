# ControlFarmacias

Repositorio principal: `C:\ControlFarmacias\Programa`.

Antes de analizar o modificar el proyecto, lee
`docs/contexto/CONTEXTO_MAESTRO.md`. Farmatic es estrictamente de solo lectura y
producción no se toca sin preflight, alcance explícito y confirmación de Pio.

El flujo es factura -> extracción -> normalización -> conciliación -> Supabase.
Ante cualquier duda de identidad, completitud, farmacia o permisos, falla cerrado.
Solo PIO está habilitada; RITA permanece bloqueada. La autoridad productiva de
todos los extractores locales está desactivada.

Documentos canónicos: `docs/contexto/CONTEXTO_MAESTRO.md`, `ESTADO_ACTUAL.md` y
`REGLAS_CRITICAS.md`.
