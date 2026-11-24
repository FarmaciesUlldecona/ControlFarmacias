# R21, R22 (caso E) y ABONOS CLUBS: diseño, re-simulación e implementación

Estado (2026-11-24):

- **R22 y ABONOS CLUBS: IMPLEMENTADOS EN LOCAL** (`CONFIRMADO POR TEST`, también en PostgreSQL 17 local).
- **R21: DISEÑADA, NO IMPLEMENTADA**, porque con los datos de hoy no cierra ninguna factura (§2).
- **Confirmación de Pio (2026-11-24, tarde):** las tres reglas pasan a REGLAS_CRITICAS (`alliance-local` 1.3.2 con
  autoridad en la noche; ABONOS CLUBS = `ABONO` solo con importe negativo; R22 acotada). D1–D5, D7 y D8 como se
  recomendaron; **D6: R22 exige el mismo concepto/laboratorio** (§3).

Sin migración, sin producción y sin push. Producción solo con lecturas READ_ONLY. Evidencias fuera del repositorio,
con `SHA256SUMS.txt`:

- `C:\ControlFarmacias\carga_abril_mayo\noche_2411\`: re-simulaciones y estado;
- `C:\ControlFarmacias\carga_abril_mayo\r21\`: borrador del 23/11;
- `C:\ControlFarmacias\evidencias_abonos_clubs\`: banco Alliance 1.3.1 frente a 1.3.2.

Etiquetas: `CONFIRMADO POR CÓDIGO` (fichero:línea), `CONFIRMADO POR TEST`, `CONFIRMADO POR LECTURA READ_ONLY`,
`PROPUESTA` y `DECISIÓN PENDIENTE`.

## 0. Decisiones de Pio (2026-11-24)

Pio corrigió Farmatic antes de la sincronización manual de las 09:24 (Madrid; resultado 0):

| Corrección | Estado en Supabase tras la sincronización |
|---|---|
| 08L65025 con fecha 07/04 | `ACTUALIZADO` (cambio 4310) |
| 08B42577A con PUC 6,09 | `ACTUALIZADO` (cambio 4308) |
| 08N27887 entrado | Insertado como 299612 (38,66) |
| Q039321/2026 son atorvastatinas bonificadas a 0, no las tamsulosinas | — |
| Tamsulosinas de 08L82633 corregidas | **No se ve en Supabase** (§2) |
| R006297/2026 → 08B18792A, confirmado correcto | — |
| Cashflow: la importación «(2) (1)» es válida | — |

| Id | Decisión |
|---|---|
| **I1** | Aplicar por el camino 2BF las 3 revisiones de identidad: 270348 (08B37018) y 276996 (08B87744), proveedor a SAFA; 267828, R006297/2026 → 08B18792A |
| **R21** | Exacto + N albaranes internos «Q0» del mismo proveedor (R9) y del **mismo día**, aunque sean de otra recepción. Sin reservar; la suma, dentro de R11. Falla cerrado si hay más de una combinación. Trazabilidad completa |
| **R22** | Un cargo sin albarán anulado exactamente por su abono en el mismo documento queda explicado con neto 0. Falla cerrado si hay más de un emparejamiento posible. No se busca en Farmatic |
| **AC** | ABONOS CLUBS: sentido `ABONO` solo si el importe es negativo, con el literal en el adaptador |
| **G** | Re-simular READ_ONLY antes de implementar, e implementar solo lo que siga haciendo falta |

## 1. Re-simulación READ_ONLY de las 7 DIFERENCIA (2026-11-24 ~09:45, tras la sincronización manual)

Es la misma cadena que la noche (`auditoria_readonly._simular` en el orden del plan, con las reservas previstas), sobre
las 25 facturas elegibles. Se hizo en tres variantes:

- `actual`: los datos tal como están;
- `con_aprobaciones`: las 3 aprobaciones I1 aplicadas solo en memoria;
- `con_aprobaciones_y_resync`: además, el nombre del proveedor `1.- SAFA`, que pone la resincronización siguiente
  (A5 del 2BF).

| Factura | 23/11 | `actual` | `con_aprobaciones` | `con_aprobaciones_y_resync` | Qué lo cierra |
|---|---|---|---|---|---|
| 08004390 | 28,76 | **CONCILIADA** (0,00) | = | = | Fecha de 08L65025 |
| 08005255 | 6,01 | **CONCILIADA** (−0,08) | = | = | PUC de 08B42577A |
| 08013909 | 38,67 | **CONCILIADA** (0,01) | = | = | 08N27887 |
| 08004806 | 52,69 | 52,69 | 52,69 | **CONCILIADA** | I1 (270348) y la resincronización |
| 08007042 | 4,93 | 4,93 | 4,93 | **CONCILIADA** | I1 (276996) y la resincronización |
| 08005257 | 505,08 | 505,08 | = | = | **R22** (§3) |
| 08005707 | 688,15 | 688,15 | = | = | Tamsulosinas: falta un albarán de ~21,99 (§2) |

- **Proveedor:** el casado elige candidatos también por el **nombre** del proveedor. Con solo la aprobación, 270348 y
  276996 siguen con MADAUS CERAFARM y FEDERACIO y no entran. Cierran la noche siguiente a la aplicación: a las 21:30 la
  resincronización actualiza el nombre (A5 del 2BF) y a las 22:15 se concilia.
- **08B35782** (270213, 17/04, 28,76): sin reserva y sin detalle de conciliación. Es una línea del PDF de **08004805**
  (17/04, 28,76). 08L65025 es la de 08004390 (07/04, 28,76). Alliance factura los dos en facturas distintas y cada uno
  casa con el suyo: **no hay indicio de mercancía duplicada**.
  - Pega menor: 08L65025 (299609) no tiene recepción en Supabase. Fue creado a mano el 23/11.
- **Las 3 no elegibles no cambian:** 08005254 `TOTAL_NO_EXPLICADO`; 08006123 `TRAZABILIDAD_SERVICIO_INSUFICIENTE`, que
  se resuelve con ABONOS CLUBS (§4); y HEFAME 0563834757.

## 2. R21 (diseñada, no implementada)

### 2.1 Por qué no se implementa hoy

- 08L82633 (PDF 05/05, 688,13) tiene en Supabase 08L82633 272819 (05/05, 638,82) y Q039320/2026 272818 (**06/05**,
  27,32), los dos de la recepción 49490. Falta 21,99.
- No hay en Supabase ningún albarán SAFA «Q0» del 05/05. Solo hay 3 «Q0» del 05/05, y son de RITA. Las tamsulosinas
  tampoco han entrado: no hay albaranes nuevos, salvo 4 de noviembre, ni cambios en 08L82633 tras la sincronización
  manual.
- Con la regla de Pio (mismo día), Q039320/2026 (06/05) **ni siquiera forma pareja** con 08L82633 (05/05).
- **R21 no cierra ninguna factura de la cola** y no hay ningún caso real con el que medirla. Implementarla exige una
  migración: `cf_linea_r17_valida` solo admite 2 detalles por línea (`36_cf_r20_letra_final.sql`), además de un
  despliegue con su preflight.
- **Recomendación:** no implementarla hasta tener el caso en Supabase (D1 y D2).

### 2.2 Regla, tal como quedaría (`PROPUESTA`)

Una línea documental `CARGO` que sigue `SIN_COINCIDENCIA` tras el 1:1, R17 y R20 casa con:

- **A** = el albarán de su número **exacto**;
- más **B1..Bn** (n ≥ 2; n = 1 es R17): internos `^[A-Z]\d{6}/\d{4}$` (`conciliacion.py:28`) del **mismo proveedor**
  (R9) y del **mismo día** que A (`DECISIÓN PENDIENTE` D1), de cualquier recepción;
- todos libres (R15 y no reclamados por otra línea) y ningún Bi es número de otra factura;
- |PUC(A) + Σ PUC(Bi) − línea| ≤ 0,05;
- en R11, la línea cuenta como un casado.

Falla cerrado:

- más de una combinación (contando juntas R17, R20 y R21) → `AMBIGUO_R21`;
- un albarán en las combinaciones de dos líneas → `CONFLICTO_R21`.

Trazabilidad: n + 1 detalles `UNO_A_VARIOS`, con `regla: R21`, el papel de cada uno (`NUMERO` o `INTERNO`) y la suma.
Necesita una migración (la siguiente libre, la 39) que amplíe `cf_linea_r17_valida` con la rama R21, y un conmutador
como R20 (B3): el código usa R21 solo si detecta la migración.

## 3. R22: cargo sin albarán anulado por su abono (IMPLEMENTADA)

`CONFIRMADO POR TEST`. Código en `src/facturas/runtime_supabase/conciliacion.py` (`aplicar_r22`, al final), aplicado
por `RepositorioRuntimeSupabase.construir_detalles` después del 1:1, R17 y R20. Lo usan el worker, la noche y el
simulador READ_ONLY.

- **Línea:** detalle `SIN_COINCIDENCIA`, documental `CARGO`, con número e importe > 0, y **sin ningún albarán de ese
  número** entre los candidatos leídos. Vale cualquier proveedor y las clases `EXACTA`, `LETRA_FINAL` y
  `FINAL_DOCUMENTAL`, con la lectura Alliance, que es la más amplia: si el albarán existe, manda el casado normal.
- **Abono:** movimiento `ABONO` del **mismo documento** (la misma factura), por importe (no por base), exactamente
  opuesto a cuatro decimales.
- **Mismo concepto (D6, Pio):** el literal de la línea (`facturas_albaranes_extraidos.descripcion`, su tipo de pedido)
  igual al del movimiento (`descripcion_literal`), sin distinguir mayúsculas ni espacios; los dos no vacíos. En
  08005257 los dos son `ECOCEUTICS` (lectura READ_ONLY `noche_241122_concepto.json`). Re-simulación con D6
  (`resim_r22_d6.json`): igual que sin D6, 08005257 CONCILIADA con 0,00.
- **Unicidad:** solo se empareja si la línea tiene un único abono posible y el abono una única línea posible. Si no,
  todo queda igual (falla cerrado).
- **Efecto:**
  - La línea pasa a `MOVIMIENTO_NO_FARMATIC` por su importe, con su origen documental y sin albarán ni reserva.
  - El abono conserva su detalle.
  - Los dos llevan `regla: R22` y la referencia del otro, y la línea lleva además `neto_par`.
  - En R11 el par no cuenta como casado.
- **Sin migración** (`CONFIRMADO POR CÓDIGO`):
  - la BD acepta un `MOVIMIENTO_NO_FARMATIC` con origen en la línea (`conciliacion_detalles_origen_check`,
    `14_cf_claim_conciliacion_v2.sql:181-189`);
  - lo trata como `NO_EVALUABLE`, con PDF = importe aplicado (`cf_detalles_por_linea`,
    `30_cf_detalle_por_linea.sql:51-66`), igual que `valores_por_linea` en Python.
- **Tests:**
  - `tests/facturas/runtime_supabase/test_r22.py`: 15 unitarios (caso 08005257, número existente o con letra, fuera de
    la regla, dos abonos, dos líneas, pares independientes);
  - `test_integracion_pg17_r22.py`: plantilla 38. El worker real persiste CONCILIADA con el par R22 sin reservar la
    línea. Con un importe distinto o con dos abonos, la línea sigue sin casar.
- **Re-simulación READ_ONLY con el código R22** (`resim_codigo_r22.json`): **solo cambia 08005257**, que pasa a
  CONCILIADA con diferencia 0,00. Las otras 24 dan exactamente lo mismo que la variante `actual`.

## 4. ABONOS CLUBS (IMPLEMENTADO; adaptador `alliance-local` 1.3.2)

`CONFIRMADO POR TEST`. Código en `src/facturas/motor_local/adaptadores/alliance.py`:
`DECISIONES_SENTIDO_SOLO_IMPORTE_NEGATIVO` y `_aplicar_decisiones_condicionadas`.

- «ABONOS CLUBS» (literal exacto normalizado) → `ABONO` solo si el total de su fila es negativo. Positivo, cero o sin
  importe: sigue `null`, falla cerrado y la factura sigue en `TRAZABILIDAD_SERVICIO_INSUFICIENTE`.
- El sentido sale del literal decidido por Pio: `inferencia_por_signo: false` y `condicion: IMPORTE_FILA_NEGATIVO`.
- **Prioridad:** se aplica **después** de la sección y de las relaciones documentales. Donde ya había sentido por
  relación (08009277 del corpus), no cambia nada: los tests previos de `test_alliance_local_v1.py` siguen sin tocar.
- **Versión 1.3.2:** la autoridad del compositor automático pasa a 1.3.2 y la 1.3.1 deja de tenerla
  (`compositor_automatico.py:38-41`; mismo procedimiento que la 1.3.1 del 2026-11-14).
- **Tests:** `tests/facturas/motor_local/test_alliance_abonos_clubs.py`, con el PDF real de 08006123 desde el espejo de
  Drive en solo lectura (si no está, el test se salta), y las versiones fijadas en los tests de autoridad y defectos 37.
- **Banco Alliance completo, 1.3.1 (HEAD exportado) frente a 1.3.2:** ver §4.1.
- **08006123 ya está `NORMALIZADA` con sentido `null`:** el cambio no la re-normaliza (D5).

### 4.1 Banco Alliance completo, 1.3.1 frente a 1.3.2

`CONFIRMADO POR TEST`. Copia del banco ENCARGO:
`C:\ControlFarmacias\evidencias_abonos_clubs\scripts\banco_alliance.py`.

- 1.3.1 = HEAD 99a0bb5 exportado con `git archive`; 1.3.2 = árbol de trabajo.
- Espejo `C:\GoogleDrive\FACTURES PIO`, en solo lectura, en memoria y sin red.
- Resultado en `comparacion_131_132.json`, sha `de01391d…`.

**94 documentos con el NIF de Alliance: 91 solo cambian la versión y 3 cambian además un único movimiento.** El cambio es
siempre «ABONOS CLUBS» de `null` a `ABONO` (con `condicion: IMPORTE_FILA_NEGATIVO`), y lo que se deriva de él:

- desaparece la validación `MOVIMIENTOS_SENTIDO NO_EVALUABLE`;
- desaparecen la incidencia `SENTIDO_NO_DOCUMENTADO` y la de la factura.

| PDF | Factura | ABONOS CLUBS |
|---|---|---|
| ALLIANCE VTO 20.7-6.8-6.9-20.10 PIO.pdf | **08006123** (el caso) | −1.582,29 |
| ALLIANCE VTO 4.2.26 PIO.pdf | 08014713 | −1.427,72 |
| ALLIANCE VTO 31.3-6.4-6.5-30.6 PIO.pdf | 08001115 | −1.324,23 |

Ningún ABONOS CLUBS positivo. Ningún otro movimiento, albarán, total ni factura cambia.

## 5. Aprobaciones de identidad I1 (preparadas; las ejecuta Pio)

`aplicar_aprobacion.py` (2BF) exige configuración `f|f|f|{PIO}` para `registrar` y `aplicar`. Hoy está `t|t|f|{PIO}`.
Además, `informe` y `aplicar` leen Farmatic y solo funcionan como ControlFarmaciasRO. Esta sesión es `Usuari`, así que
no las ejecuta.

- **Preparado en** `C:\ControlFarmacias\evidencias_identidad_2411\`:
  - `aprobaciones/aprobacion_{270348,276996,267828}.json`;
  - `scripts/captura_identidad_readonly.py`, copia exacta del procedimiento R18 (`captura` y `comparar`).
- **Valores anteriores comprobados READ_ONLY** (`estado.json`):
  - 270348 `id_proveedor` `5091 ` (revisión 4304);
  - 276996 `1` (4305);
  - 267828 `numero_albaran` `R006297/2026` (4303).
  - Ninguno está reservado, 08B18792A está libre y la siguiente aprobación será la 9.

Orden, como en R18 (§ESTADO_ACTUAL «R18 del 12/11»):

1. Pio pone los flags en `f|f|f|{PIO}`.
2. Captura `antes`.
3. `registrar` ×3 como Usuari.
4. `comparar … registro`.
5. `informe` ×3 como RO: debe dar `APLICABLE`.
6. `aplicar` ×3 como RO.
7. `comparar … aplicacion`.
8. Pio vuelve a encender los flags.

## 6. Decisiones pendientes y recomendación

| Id | Pregunta | Recomendación |
|---|---|---|
| D1 | R21, «mismo día»: ¿fecha de A en Farmatic, fecha de la línea del PDF o ±1 día? Hoy 08L82633 es del 05/05 y Q039320/2026 del 06/05 | Fecha de A, exacta. No ampliar a ±1 sin un caso medido |
| D2 | R21: ¿se implementa ya, sin ningún caso que cierre? | No. Primero, Pio localiza las tamsulosinas en Farmatic (la corrección no llegó a Supabase) y se re-simula |
| D3 | R21: tope de n | n ≤ 3 internos |
| D4 | R21, A «exacto»: ¿también `LETRA_FINAL`? | Solo `EXACTA` (es lo que dijo Pio) |
| D5 | 08006123 (ya `NORMALIZADA` con sentido `null`): camino de re-normalización con 1.3.2. Su PDF trae 4 facturas (VTO 20.7-6.8-6.9-20.10) | Reproceso one-shot del documento con confirmación de Pio, tras comprobar READ_ONLY el estado de las otras 3 facturas del PDF |
| D6 | R22: ¿solo ECOCEUTICS o cualquier abono? **Pio: mismo concepto/laboratorio** | Cualquier abono exacto del mismo documento (como lo dijo Pio), con la unicidad como barrera. Banco: hoy solo afecta a 08005257 |
| D7 | R22 sin conmutador en la BD (no hay migración) | Aceptar. Se desactiva revirtiendo el commit |
| D8 | 08L65025 sin recepción en Supabase | Informativo. No afecta al casado |

## 7. Fuera de alcance

Desplegar migraciones; ejecutar las aprobaciones I1; re-normalizar 08006123; tocar Farmatic, flags o tareas; push.

## 7. 08005707 tras 08L82633A (2026-11-24, 13:27)

`CONFIRMADO POR LECTURA READ_ONLY` (`noche_2411 8L82633A.json`, `resim_1327_08L82633A.json`):

- Pio grabó las tamsulosinas como **08L82633A** (299725, SAFA, 05/05, PUC 21,99, **sin recepción**). Farmatic no deja
  modificar 08L82633 (albarán cerrado) y 08L82633A no se anula.
- 08L82633 (638,82) + Q039320/2026 (27,32) + 08L82633A (21,99) = **688,13**, la línea exacta. El motor no lo casa:
  R17 y R20 solo emparejan 1+1 y R20 exige la misma recepción. 08005707 sigue en DIFERENCIA 688,15.
- Pio pide una aprobación manual R18 para esa línea con los 3 albaranes, sin regla general (`PENDIENTE`).
