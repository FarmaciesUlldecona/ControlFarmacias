# Estudio: agentes y subagentes para ControlFarmacias

Fecha: 2026-10-23. Estado: **PROPUESTA, solo análisis.** No se ha modificado código, configuración,
producción ni Farmatic. Sin commit.

Fuentes: inspección local de solo lectura de `Programa` (`main`, `5012ee3`), del Orquestador
(`v0.2-dev`, `869f1cc`), del worktree `Programa_web` (`web/fase1`, `a91ca22`) y de
`C:\ControlFarmacias\Analisis_Ecoceutics` (Compras). Precios de modelos: tabla de la skill `claude-api`
(caché a 2026-10-06). Las cifras de coste y volumen son `INFERIDO` salvo que se indique otra cosa.

Este documento no es fuente de reglas: mandan `CONTEXTO_MAESTRO.md`, `ESTADO_ACTUAL.md` y
`REGLAS_CRITICAS.md`. Ninguna propuesta amplía autoridad productiva.

---

## 0. Conclusión en una línea

El núcleo productivo (sincronización, extracción, normalización, conciliación, migraciones) debe
seguir siendo **código determinista**. El valor de los agentes está en el **trabajo de desarrollo y
de análisis** (exploración de Farmatic, revisión contra reglas, redacción de preflights, informes,
borradores de adaptadores), siempre en local, en solo lectura o sobre ramas, con Pio como única
puerta hacia producción.

---

## 1. Inventario actual

### 1.1 Repositorios y componentes

| Componente | Ubicación | Qué hace | Ejecución |
|---|---|---|---|
| Sincronización de albaranes | `Programa/src/sincronizar_albaranes.py` + lectura Farmatic (`src/database/`) + `src/supabase_client/` | Farmatic → Supabase `albaranes` (nuevos por `IdContador`; resincronización v2 implementada, apagada hasta la 22) | Task Scheduler nocturno vía `.bat` |
| Ingesta de facturas | `src/facturas/importar_facturas_drive.py` | PDF de `C:\GoogleDrive\FACTURES PIO` → `documentos_facturas` | Task Scheduler vía `.bat` |
| Extracción | `src/facturas/motor_local/` (PDFium, 9 módulos de adaptadores, OCR solo Guimerà), `OrquestadorExtraccionProductiva` | Específico → local genérico → OCR local → Luna (GPT, **deshabilitada por defecto**) | Workers (0 activos); one-shot manual |
| Normalización | `src/facturas/normalizador_v2/` | Contrato, segmentación, consolidación | Worker / `MANUAL_ONE_SHOT` |
| Conciliación | `src/facturas/runtime_supabase/` (conciliación, elegibilidad, enriquecimiento, workers) + RPC SQL (migraciones 18–22) | Factura ↔ albaranes, R11/R15/R16 | `conciliacion_automatica=false`; one-shot manual |
| Migraciones | `sql/migrations/NN_*.sql` + rollback, generadores deterministas, `desplegar_NN.py` | Esquema Supabase | Manual con confirmación de Pio |
| Auditoría por hito | `pruebas/auditoria_*` (≈37 carpetas) | Preflight, snapshot, huellas, one-shot, postcheck | Manual |
| Tests | `tests/` (85 ficheros; 1694 sin BD + 136 `pg17_local`) | Certificación local | Manual, Docker |
| OCR GPT (experimentos) | `src/facturas/motores/openai/` | Benchmarks Luna/Terra/Sol | Manual, puntual |
| Compras | `Analisis_Ecoceutics/` (spec, calibración, verificaciones V1–V13) | Fichas A–D por SQL sobre Farmatic; sin código en Programa todavía | Manual (sesiones Claude Code como ControlFarmaciasRO) |
| CLI `cf` | `ControlFarmacias_Orquestador_V0_2_dev` | Tareas persistentes, locks por worktree, supervisor, ejecutor **Codex** como subprocess, presupuesto 3,80 €/semana, estados `REQUIERE_OK_PIO`/`PAUSA_PIO` | Manual |
| Web fase 1 | `Programa_web/web` | Vistas `v_web_*` con fixtures ficticios; Playwright MCP | Local, sin datos reales |

### 1.2 Flujos de extremo a extremo y su grado de automatización

| Flujo | Automático hoy | Manual hoy |
|---|---|---|
| Albaranes | Nocturno, código 0 | Revisar log; diagnosticar modificados (hasta desplegar la 22) |
| Facturas (pdfium + reglas + OCR GPT) | Ingesta a `documentos_facturas` | Extracción/normalización one-shot; 71 de 137 documentos en cola sin layout reconocido |
| Conciliación | Nada (flag apagado) | One-shot por factura con preflight, confirmación y postcheck |
| Compras | Nada | Consultas, calibración con el portal bifarmaeco, decisiones D1–D20 |
| Web | Nada productivo | Desarrollo con fixtures |

### 1.3 Puntos manuales, repetitivos o propensos a error

1. **Ciclo de hito repetido** (2AT, 2AZ-D, 2BA-D, 2BB, 08007971…): puerta Git → preflight READ_ONLY →
   backup y huellas → PARA → one-shot → postcheck → ESTADO_ACTUAL → commit. Cada hito reescribe en
   parte scripts parecidos (`desplegar_21.py`, `desplegar_22.py`, `enriquecer_una_vez.py`,
   `ejecutar_una_vez.py`). Riesgo: precondición omitida (antecedente: primer intento de la 19).
2. **Actualización de documentos canónicos** tras cada hito (ESTADO_ACTUAL tiene 828 líneas): manual,
   con riesgo de desfase entre documentos.
3. **Diagnóstico de discrepancias** factura ↔ albarán (08007969: tabla línea a línea PDF vs Farmatic).
4. **Proveedores sin extractor**: SAFA, Beiersdorf, tipos de pedido Alliance no certificados.
5. **Exploración SQL de Farmatic** para Compras: muchas consultas, mucho contexto, identidad RO.
6. **Revisión de cambios** contra reglas (solo SELECT, fallo cerrado, privilegios patrón 19/20/21,
   rollback = esquema anterior): hoy depende de la memoria de la sesión.
7. **Vigilancia de la noche** (logs `automatizacion_*.log`, códigos de salida, 42501).

### 1.4 Uso actual de Claude Code

- `Programa/CLAUDE.md` (versionado) + `C:\ControlFarmacias\CLAUDE.md`; `AGENTS.md` para Codex.
- `.claude/settings.json`: allow de lectura Git y de los módulos de exploración de Farmatic; **ask**
  para commit, Docker, `supabase`, `psql`, migraciones, `desplegar`, `pruebas/`, `schtasks`,
  scripts de Farmatic; **deny** para `push`, `reset`, `clean`, `restore`, `pip install`, `winget`.
- Hook `PreToolUse` (`verificar_identidad_farmatic.py`): bloquea comandos con nombres de módulos de
  Farmatic si `whoami` no es `MOSTRADOR\ControlFarmaciasRO`.
- Skill `farmatic-sql-explorer`.
- `Programa_web/web`: settings propios (deny `supabase`, `docker`, migraciones), plugin
  `frontend-design`, MCP Playwright.
- **No hay subagentes** (`.claude/agents/` no existe) ni ejecución headless/programada de Claude.

---

## 2. Candidatos a agente o subagente

Leyenda de la clasificación: **D** = mantener script determinista · **S** = skill (procedimiento
documentado que la sesión carga) · **SA** = subagente de Claude Code (`.claude/agents`, contexto
aislado, herramientas acotadas) · **AA** = agente autónomo (Agent SDK / `claude -p` headless /
programado).

### 2.1 Desarrollo

| Tarea | Entrada | Salida | Frecuencia | Determinismo | Riesgo | ¿LLM? | Clase |
|---|---|---|---|---|---|---|---|
| Exploración SQL Farmatic | Pregunta funcional | Tablas, columnas, consultas SELECT, hallazgos con etiqueta de certeza | Diaria en Compras | Bajo | Medio (datos de clientes en Farmatic) | Sí: navegar un esquema desconocido | **SA** `explorador-farmatic` + la skill existente |
| Redacción de specs | Hallazgos, decisiones de Pio | Borrador de spec/DISENO.md | Por hito | Bajo | Bajo (documento) | Sí | Sesión principal (no merece subagente) |
| Escritura de tests | Spec, código | Tests pytest / pg17_local | Por hito | Medio | Bajo (local) | Sí | Sesión principal; SA opcional `autor-tests` más adelante |
| Revisión de código contra reglas | Diff | Hallazgos con `archivo:línea` y regla afectada | Por commit | Bajo | Nulo (solo lectura) | Sí | **SA** `revisor-reglas` (piloto) |
| Preflight / postcheck | Alcance del hito | Consultas READ_ONLY, huellas, informe | Por despliegue | **Alto** | Alto si se improvisa | **No** para ejecutar; sí para redactar el informe | **D** (librería común) + **S** `procedimiento-one-shot` |
| Migraciones | Diseño | SQL + rollback + generador | Por hito | Alto (generador) | Alto | Para redactar sí; nunca para desplegar | **D** (generador + `desplegar_NN.py`) + sesión principal |
| Documentación canónica | Commits, evidencias | Sección de ESTADO_ACTUAL | Por hito | Medio | Bajo | Sí | **SA** `redactor-estado` (fase 2) |

### 2.2 Operación

| Tarea | Entrada | Salida | Frecuencia | Determinismo | Riesgo | ¿LLM? | Clase |
|---|---|---|---|---|---|---|---|
| Sincronización / extracción | Farmatic, PDF | Filas Supabase | Diaria | Total | Alto | **No** | **D** |
| Lectura de facturas de layout conocido | PDF | Campos normalizados | Por documento | Total | Alto | **No** | **D** (motor local) |
| Proveedor no soportado | PDF del mirror local | Borrador de adaptador + tests, sin autoridad | Por proveedor (decenas en total) | Bajo | Medio: nunca productivo sin certificación | Sí, gran ahorro | **SA** `autor-adaptador` (fase 3) |
| OCR de campos pendientes (Luna) | PDF | Campos | Por documento | Bajo | Alto | Ya existe (GPT), apagado | Mantener apagado; decisión aparte |
| Conciliación | Factura + albaranes | Resultado | Por factura | Total | Alto | **No** | **D** |
| Diagnóstico de incidencias (`NO_APTA`, diferencias) | Factura, albaranes, PDF | Explicación con tabla y causa probable | Semanal | Bajo | Bajo (solo lectura) | Sí | **SA** `diagnosticador` (fase 2) |
| Vigilancia nocturna | Logs, códigos de salida | Resumen y alertas | Diaria | Alto | Bajo | Para el resumen, poco | **D** (parser) + **AA** opcional solo lectura (fase 4) |
| Calibración bifarmaeco | Portal (con credenciales) + consultas Q-A | Tabla de diferencias | Mensual | Medio | Credenciales del portal | Poco | **D** (script de comparación) + Pio; **ningún agente con el portal** |

### 2.3 Futuro

| Área | Candidato | Clase | Nota |
|---|---|---|---|
| Compras (sync a Supabase, spec §5) | Exploración y calibración | SA `explorador-farmatic` | La sincronización en sí será **D** |
| Stock / reaprovisionamiento | Propuesta de pedido | **D** para el cálculo; SA para explicar excepciones | Nunca emitir pedidos |
| Ventas | Agregados por artículo y día | **D** | Tabla 15 ya diseñada sin datos de cliente; ningún LLM sobre tickets |
| Tesorería / Norma 43 | Conciliación bancaria | **D** (Norma 43 es formato fijo) | LLM solo para conceptos ambiguos, en revisión |
| Correo / Telegram | Avisos y consultas | **D** para avisos; AA de consulta solo lectura (fase 4+) | Canal externo: ver §4.3 |

---

## 3. Arquitectura propuesta

### 3.1 Orquestador + subagentes (dentro de Claude Code)

La sesión principal de Claude Code actúa como orquestador: conserva el contexto del hito y delega
tareas acotadas a subagentes con contexto aislado, que devuelven solo su conclusión.

| Subagente | Rol | Herramientas permitidas | Modelo propuesto | Identidad |
|---|---|---|---|---|
| `revisor-reglas` | Revisar un diff contra REGLAS_CRITICAS y patrones del repo | Read, Grep, Glob, `git diff`/`git log` (Bash de solo lectura) | Opus 5.5 (fallos caros, volumen bajo) | Cualquiera |
| `explorador-farmatic` | Exploración SQL con los wrappers | Read, Grep, Bash limitado a los módulos de exploración ya permitidos | Sonnet 5.5 | **Solo** sesiones abiertas como ControlFarmaciasRO |
| `diagnosticador` | Explicar una incidencia de conciliación | Read, Grep, lectura de evidencias locales y de un snapshot exportado | Sonnet 5.5 | Usuari, sin red a Supabase |
| `redactor-estado` | Borrador de sección de ESTADO_ACTUAL | Read, Grep, `git log` | Sonnet 5.5 | Cualquiera |
| `autor-adaptador` | Borrador de adaptador + tests para un layout | Read, Grep, Write/Edit solo en `src/facturas/motor_local/adaptadores/` y `tests/`, pytest | Opus 5.5 | Usuari, en worktree propio |

Reglas comunes: ningún subagente tiene `Bash` libre, acceso a `.env`, `supabase`, `psql`, Docker,
`desplegar`, `schtasks` ni commit. Los que solo leen no reciben Write/Edit.

### 3.2 Encaje con el CLI `cf`

Recomendación: **convivir**, no sustituir ni envolver por ahora.

- `cf` ya resuelve lo difícil de un orquestador (tareas persistentes, locks por worktree, snapshots,
  estados `REQUIERE_OK_PIO`, presupuesto) y está certificado para Codex. Sustituirlo tiraría trabajo
  probado.
- Los subagentes de Claude Code operan **dentro** de una sesión interactiva; `cf` gestiona tareas
  **entre** sesiones. No compiten.
- Opción posterior (fase 4, `REQUIERE_OK_PIO`): añadir a `cf` un ejecutor `claude -p` junto al de
  Codex, reutilizando sus barreras (worktree, snapshot, integridad posterior). Solo para tareas
  `read_only` al principio.

### 3.3 Paralelismo y coordinación (facturas vs Compras)

- Una sesión por línea de trabajo y **un worktree por sesión** (patrón ya usado en `Programa_web`).
  Compras trabajaría en un worktree propio de Programa cuando llegue a código.
- Los locks de `cf` (una tarea activa por worktree) sirven de referencia; para sesiones de Claude
  Code basta la disciplina de worktree + ramas sin push.
- Recursos compartidos que no se paralelizan: el contenedor `pg17_local` (puerto), producción
  (nunca dos hitos a la vez) y los documentos canónicos (un solo redactor por hito; fusión manual).

### 3.4 Memoria, estado, trazabilidad

- Fuente de verdad: los documentos canónicos + Git. La memoria de Claude Code es auxiliar y nunca
  prevalece (orden de autoridad).
- Cada subagente entrega su resultado con etiquetas de certeza (`CONFIRMADO POR …`, `INFERIDO`…).
- Trazas: transcripciones de Claude Code (locales), `runs/` de `cf`, evidencias en
  `C:\ControlFarmacias\evidencias_*`. Propuesta: un registro append-only de invocaciones de
  subagentes mediante un hook `SubagentStop` (fase 1, verificar disponibilidad del evento).

---

## 4. Seguridad y gobierno

### 4.1 Identidades

| Identidad | Puede | No puede |
|---|---|---|
| `MOSTRADOR\ControlFarmaciasRO` | Farmatic vía `obtener_conexion()` | Supabase, credenciales de Usuari, Task Scheduler |
| `MOSTRADOR\Usuari` | Repos, pg17_local, Docker, Supabase solo en scripts con confirmación | Farmatic (rechazado por la barrera) |

- Un subagente hereda la identidad Windows de la sesión: **no hay cruce posible** mientras las dos
  identidades vivan en sesiones distintas de VS Code. Mantener esa separación es la barrera principal.
- **Ningún agente con `service_role`** ni con lectura de `.env`: añadir `deny` de `Read(**/.env*)` y
  `Bash(*service_role*)` (hoy solo hay `ask` genérico sobre `supabase`). `REQUIERE_OK_PIO`.

### 4.2 Puertas `REQUIERE_OK_PIO` y cómo se fuerzan

| Puerta | Mecanismo hoy | Refuerzo propuesto |
|---|---|---|
| Escritura en producción (one-shot, despliegue) | `ask` sobre `desplegar`, `supabase`, `psql`, `pruebas/` | Hook que exija un fichero de confirmación firmado por Pio (SHA del commit + alcance) antes de ejecutar `desplegar_*`/`*_una_vez.py` |
| Commit | `ask` | Igual; los subagentes sin herramienta de commit |
| Push | `deny` | Sin cambios |
| Task Scheduler / flags / workers | `ask` sobre `schtasks` | Pasar a `deny` en sesiones de agentes; solo Pio a mano |
| Farmatic | Hook de identidad + barrera SQL | Sin cambios (la barrera efectiva es `obtener_conexion()`) |
| Modo headless | No existe | `--permission-mode` restrictivo, `--allowedTools` explícito, sin `bypassPermissions` jamás |

Principio: las puertas se aplican por **configuración y hooks** (el harness), no por instrucciones en
el prompt. Un subagente que "promete" no escribir no es una barrera.

### 4.3 Qué no puede salir a un LLM

- **Nunca:** datos de clientes de Farmatic (tickets, recetas, clientes, DNI/NIE, tarjetas de
  fidelización, filas `Factura IdTipo='S'`), credenciales (`.env`, `EcoceuticsDV.config`, portal
  bifarmaeco, FTP), claves de Supabase.
- **Con cautela (ya ocurre en las sesiones actuales):** filas de Supabase privado, albaranes y
  facturas de proveedores (datos de empresa, no personales), PDFs de facturas.
- Consecuencia práctica: `explorador-farmatic` no consulta tablas de ventas/clientes salvo agregados
  sin identificadores; añadir esa lista negra a la skill y, si es viable, a la barrera SQL.
  `REQUIERE_OK_PIO`.
- Revisar el plan de datos de la cuenta (retención, uso para entrenamiento) antes de cualquier agente
  headless. `PENDIENTE`.

### 4.4 Nivel máximo de acción autónoma por agente

| Nivel | Significado | Agentes |
|---|---|---|
| 0 | Solo lectura, informe | `revisor-reglas`, `diagnosticador`, vigilancia nocturna |
| 1 | Escribe en el worktree local, sin commit | `redactor-estado`, `autor-adaptador`, `autor-tests` |
| 2 | Lee Farmatic con la identidad RO | `explorador-farmatic` |
| 3 | Escribe en Supabase/producción | **Ningún agente.** Solo scripts deterministas lanzados tras confirmación escrita de Pio |

---

## 5. Coste y rendimiento

### 5.1 Precios de referencia (USD por millón de tokens)

| Modelo | Entrada | Salida | Lectura de caché |
|---|---|---|---|
| Opus 5.5 | 4,00 | 20,00 | 0,20 |
| Sonnet 5.5 | 2,00 | 10,00 | 0,20 |
| Haiku 5.5 | 0,10 | 0,50 | — (no consultado) |

Si Claude Code se usa con suscripción, los subagentes consumen cuota de la suscripción y no
facturan por token; las cifras siguientes aplican a ejecución por API (headless/Agent SDK). Cuál es
el caso hoy: `PENDIENTE` (dato de Pio).

### 5.2 Estimación por tarea (`INFERIDO`, suponiendo ~70 % de entrada servida desde caché)

| Tarea | Tokens entrada / salida | Modelo | Coste por ejecución | Volumen/mes | Coste/mes |
|---|---|---|---|---|---|
| Revisión de un diff | 120 k / 8 k | Opus 5.5 | ≈ 0,33 $ | 30 | ≈ 10 $ |
| Exploración Farmatic (sesión) | 250 k / 15 k | Sonnet 5.5 | ≈ 0,33 $ | 25 | ≈ 8 $ |
| Diagnóstico de incidencia | 150 k / 10 k | Sonnet 5.5 | ≈ 0,21 $ | 8 | ≈ 2 $ |
| Borrador de ESTADO_ACTUAL | 100 k / 6 k | Sonnet 5.5 | ≈ 0,14 $ | 8 | ≈ 1 $ |
| Borrador de adaptador | 400 k / 40 k | Opus 5.5 | ≈ 2,00 $ | 4 | ≈ 8 $ |
| Resumen nocturno (headless) | 30 k / 2 k | Haiku 5.5 | < 0,01 $ | 30 | < 0,2 $ |
| **Total orientativo** | | | | | **≈ 30 $/mes** |

Comparación: presupuesto actual de `cf` para Codex, 3,80 €/semana (≈ 16 €/mes). El coste dominante
no es el dinero sino el **tiempo de revisión de Pio**; un agente solo compensa si reduce ese tiempo.

### 5.3 Latencia, fiabilidad, detección de fallos

- Latencia: segundos a pocos minutos por subagente; irrelevante frente a hitos de horas.
- Fallos esperados: alucinación de columnas o reglas, consultas que la barrera rechaza, falsos
  positivos en revisión, borradores que no pasan tests.
- Detección: la barrera SQL rechaza lo no SELECT; los tests y `pg17_local` validan el código; cada
  hallazgo del revisor debe citar `archivo:línea` comprobable; los informes llevan etiqueta de
  certeza y Pio decide. Nada de un agente es `CONFIRMADO` sin código, test o evidencia.

---

## 6. Riesgos y límites

- **Donde un agente empeora frente al código:** cualquier paso que deba ser reproducible y auditable
  (extracción, normalización, conciliación, despliegues, preflight/postcheck). Un LLM no es
  determinista, puede "completar" datos (prohibido por las reglas: no inventar importes ni sentidos)
  y su salida no es certificable igual que un test.
- **Falsa sensación de control:** un revisor automático que no encuentra nada no certifica nada.
- **Deriva de contexto:** un subagente sin los documentos canónicos aplica reglas antiguas; cada
  definición debe ordenar leer `REGLAS_CRITICAS.md` y no duplicar reglas en su prompt.
- **Dependencia de proveedor:** formato de `.claude/agents`, flags de headless y modelos cambian.
  Mitigación: definiciones cortas, versionadas, sin lógica de negocio dentro; la lógica vive en el
  código y en los documentos canónicos.
- **Dos proveedores de LLM** (Codex en `cf`, GPT en Luna, Claude en Claude Code): más superficie de
  datos y de mantenimiento. Mantenerlos con papeles separados y documentados.
- **Mantenimiento:** cada subagente es un artefacto más que revisar cuando cambian las reglas.
  Empezar con dos.

---

## 7. Recomendación

### 7.1 Matriz

| Tarea | Opción | Beneficio | Riesgo | Esfuerzo |
|---|---|---|---|---|
| Revisión contra reglas | SA `revisor-reglas` | Alto (atrapa omisiones tipo 19) | Nulo | Bajo |
| Exploración Farmatic (Compras) | SA `explorador-farmatic` | Alto (contexto aislado, prioridad actual) | Medio (datos de cliente) | Bajo |
| Preflight/postcheck | D librería común + S procedimiento | Alto (menos scripts nuevos por hito) | Bajo | Medio |
| Diagnóstico de incidencias | SA `diagnosticador` | Medio | Bajo | Bajo |
| Documentación canónica | SA `redactor-estado` | Medio | Bajo | Bajo |
| Proveedor no soportado | SA `autor-adaptador` | Alto (71 documentos sin layout) | Medio (sin autoridad hasta certificar) | Medio |
| Vigilancia nocturna | D parser + AA headless solo lectura | Bajo-medio | Bajo | Medio |
| Ejecutor Claude en `cf` | AA vía `cf` | Medio | Medio | Alto |
| Extracción/normalización/conciliación/sync | D | — | — | — |

### 7.2 Hoja de ruta (prioridad Compras → facturas → sincronización/web)

| Fase | Contenido | Condición de entrada |
|---|---|---|
| **1. Piloto** (2–3 semanas) | `explorador-farmatic` (Compras) y `revisor-reglas`; refuerzos de `deny` (§4.1) | OK de Pio a este estudio |
| **2. Facturas, desarrollo** | `diagnosticador`, `redactor-estado`; librería común de preflight/postcheck (D) + skill `procedimiento-one-shot` | Piloto superado |
| **3. Facturas, cobertura** | `autor-adaptador` en worktree propio (SAFA, tipos Alliance pendientes, Beiersdorf) | Fase 2 estable |
| **4. Sincronización/web y operación** | Parser nocturno (D) + resumen headless de solo lectura; posible ejecutor Claude en `cf` | Decisión de Pio sobre plan de datos y canal de aviso |

### 7.3 Piloto inicial

**P1. `explorador-farmatic`** (sesión ControlFarmaciasRO, trabajo de Compras D1/D11/D13).
- Herramientas: Read, Grep, Glob y los módulos de exploración ya en `allow`; sin Write.
- Criterio de éxito (medido sobre 10 preguntas de Compras):
  - 0 consultas rechazadas por la barrera por no ser SELECT;
  - 0 accesos a tablas de clientes/ventas con identificadores;
  - ≥ 8/10 respuestas con consulta reproducible y etiqueta de certeza correcta, verificadas por Pio;
  - el contexto de la sesión principal crece < 20 % de lo que crecería explorando en ella.

**P2. `revisor-reglas`** (cualquier sesión, antes de cada commit local).
- Herramientas: Read, Grep, Glob, `git diff`/`git log`.
- Criterio de éxito (medido sobre los diffs de 2BA, 2BD y 3 commits nuevos):
  - detecta en los diffs históricos los defectos que se corrigieron después (p. ej. la precondición
    omitida de la 19 sembrada en un diff de prueba);
  - ≤ 2 falsos positivos por revisión de media;
  - cada hallazgo cita `archivo:línea` y la regla de REGLAS_CRITICAS afectada.

Si un piloto no alcanza el criterio en 3 semanas, se retira sin más.

### 7.4 Decisiones abiertas

Ver la lista `REQUIERE_OK_PIO` al final.

---

## REQUIERE_OK_PIO

1. Aprobar o rechazar el piloto (P1 `explorador-farmatic`, P2 `revisor-reglas`) y crear
   `.claude/agents/` en Programa.
2. Modelo por subagente (Opus 5.5 para revisión y adaptadores; Sonnet 5.5 para el resto).
3. Refuerzos de configuración: `deny` de lectura de `.env*` y de `service_role`; `schtasks` de `ask`
   a `deny` en sesiones con agentes.
4. Lista negra de tablas de clientes/ventas para la exploración (en la skill y, si procede, en la
   barrera SQL).
5. Hook de confirmación por fichero para `desplegar_*` y `*_una_vez.py`.
6. Librería común de preflight/postcheck (código determinista, hito propio).
7. Modalidad de facturación de Claude Code (suscripción o API) y techo de gasto mensual.
8. Política de datos de la cuenta (retención/entrenamiento) antes de cualquier ejecución headless.
9. Convivencia con `cf` y, más adelante, si `cf` incorpora un ejecutor `claude -p`.
10. Canal de avisos (correo/Telegram) y si un agente puede leerlo o solo recibir avisos deterministas.
11. Luna (GPT) sigue deshabilitada; cualquier cambio es decisión aparte de este estudio.
