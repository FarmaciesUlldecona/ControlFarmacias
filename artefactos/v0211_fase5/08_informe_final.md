# Certificación shadow E2E — Orquestador V0.2.11

## Veredicto

**FASE 5: CUMPLE.** Clasificación: **OPERATIVO_CON_LIMITACIONES**.

La suite A–P recorre la fachada pública siempre que la operación lo permite. D, E y F atraviesan la fachada, el motor histórico real, la política, el presupuesto y la validación local, sustituyendo únicamente la invocación de Codex por un fake controlado. No hubo red, Codex real, Farmatic, commit ni push.

## Evidencia

- TEST_FOCAL: 2 passed en 13,69 s.
- SHADOW_E2E final: 16 passed en 51,18 s.
- TEST_MODULO: 268 passed en 479,02 s.
- SUITE_COMPLETA (`tests/`): 396 passed en 762,95 s.
- `git diff --check`: correcto; solo avisos informativos LF/CRLF.
- `py_compile`: correcto.

## Eficiencia y seguridad

Los escenarios resolubles D y E usan una única primaria fake. F usa exactamente una primaria y una corrección motivada por un error verificable, con contexto incremental. LOCAL_ONLY, HEAVY bloqueado, presupuesto insuficiente, Farmatic y ambigüedad no invocan Codex. No se declaran tokens ni coste real del proveedor.

El presupuesto semanal continúa en 3,80 EUR y el aviso en 3,04 EUR. HEAVY y full-run requieren autorización de coste. Las reglas FARMATIC_READ_ONLY y FACTURAS_ZERO_INVENTIONS permanecen absolutas. Commit y push requieren decisión explícita de Pio.

## Capacidad natural

Pio puede dar órdenes naturales controladas sin dirigir pasos técnicos internos para consultas, tests, cambios acotados, cambios multiarchivo, presupuesto y retries. La capacidad es operativa con limitaciones: parser local acotado, sin continuidad real de sesión CLI, coste real no automático, descubrimiento de tests conservador y locking contable intra-proceso.

No se inicia ninguna fase posterior.
