# Orquestador V0.2.11 — Fase 4

Estado técnico: CUMPLE.

La ejecución Codex deja de realizar una segunda llamada de supervisión por defecto. Una llamada primaria recibe un contexto estructurado y limitado; después se aplican barreras y validaciones locales. Si todo pasa, la supervisión determinista finaliza el trabajo sin otro Codex.

LIGHT y STANDARD permiten una única corrección automática solamente ante un fallo local demostrado. HEAVY conserva un máximo automático de una llamada y requiere autorización adicional antes de corregir. LOCAL_ONLY mantiene cero llamadas.

El contexto se representa como base más ampliaciones, está aislado por `task_id` y puede recuperarse localmente para retries de la misma tarea. El `session_id` existente continúa siendo identificador de la sesión/lock del Orquestador; no se declara continuación de sesión Codex CLI porque la infraestructura actual no la demuestra.

Validación modular final: 262 tests passed en 570,79 segundos. Suite completa no ejecutada; se usó un conjunto transversal acotado de 14 módulos y no se inició la Fase 5.
