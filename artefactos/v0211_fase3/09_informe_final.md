# Orquestador V0.2.11 — Fase 3

Estado técnico: CUMPLE.

Se añadió contabilidad semanal local y durable en `estado/presupuestos`, con una configuración única predeterminada de 3,80 EUR y un archivo histórico por semana ISO. Todo importe monetario se opera con `Decimal` y se serializa como texto.

El consumo relevante es la suma del coste real y las reservas activas. El resumen estructurado permanece en estado `normal` por debajo del 80 %, pasa a `cerca_del_limite` desde el 80 % y antes del 100 %, y pasa a `limite_alcanzado_o_superado` desde el 100 %. Para el presupuesto predeterminado, el umbral es 3,04 EUR. Las consultas LOCAL_ONLY de presupuesto y consumo exponen el estado, los flags y el umbral sin lanzar Codex.

El saldo disponible descuenta coste real y reservas activas. Las estimaciones no se convierten en coste real. El registro explícito de coste real libera la reserva, conserva la estimación y registra la diferencia.

LIGHT y STANDARD pueden continuar si su estimación cabe. HEAVY y full-run mantienen la barrera estructural. Una autorización excepcional puede sobrepasar el saldo sin modificar el presupuesto semanal. LOCAL_ONLY permanece operativo con presupuesto agotado.

El evento existente `RESOURCE_BUDGET_CHECKED` incluye presupuesto, costes real y comprometido, disponible, porcentaje y estado/flags de aviso. Las métricas de fachada y retries heredan los mismos campos del resumen.

Evidencia final de módulo: 175 tests passed en 342,63 segundos. Suite completa no ejecutada por no existir necesidad técnica adicional; esta orden cierra exclusivamente la Fase 3, no la versión completa V0.2.11.
