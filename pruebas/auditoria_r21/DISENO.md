# R21, R22 (caso E) y ABONOS CLUBS: diseño, re-simulación e implementación

Estado (2026-11-24):

- **R22 y ABONOS CLUBS: IMPLEMENTADOS EN LOCAL** (`CONFIRMADO POR TEST`, también en PostgreSQL 17 local).
- **R21: DISEÑADA, NO IMPLEMENTADA**, porque con los datos de hoy no cierra ninguna factura (§2).
- **R21 como migración 39 (diseño de la noche del 2026-11-24, §9; IMPLEMENTADA EN LOCAL el 2026-11-25, §9.11):**
  sustituye a §2.2. Exacto + hasta 3 complementarios (internos «Q0» o variante con letra). Numeración por orden de
  despliegue (DECISIÓN DE PIO, 2026-11-25): R21 = 39, H7b = 40, «Actualizar ahora» = 41. R21-D1 revisada por Pio el
  2026-11-25 tras el banco R21-D8 (§9.11). `CONFIRMADO POR TEST`, también en PostgreSQL 17 local; sin desplegar.
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

### 2.2 Regla, tal como quedaría (`PROPUESTA`, SUSTITUIDA por §9)

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
  08005257 los dos son `ECOCEUTICS` (lectura READ_ONLY `noche_2411\r22_concepto.json`). Re-simulación con D6
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

**APLICADAS el 2026-11-24** (aprobaciones 9, 10 y 11; revisiones 4304, 4305 y 4303 resueltas). `registrar` como
Usuari (`REGISTRO_OK`), `informe` y `aplicar` como RO por Pio, sincronización manual de las 18:35. Evidencias en
`C:\ControlFarmacias\evidencias_identidad_2411\salidas\`.

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
| D6 | R22: ¿solo ECOCEUTICS o cualquier abono? | **DECIDIDO por Pio (2026-11-24): mismo concepto/laboratorio** (`descripcion` de la línea = literal del abono). Implementado en 8e63081. Re-simulación: solo afecta a 08005257 |
| D7 | R22 sin conmutador en la BD (no hay migración) | Aceptar. Se desactiva revirtiendo el commit |
| D8 | 08L65025 sin recepción en Supabase | Informativo. No afecta al casado |

## 7. Fuera de alcance

Desplegar migraciones; ejecutar las aprobaciones I1; re-normalizar 08006123; tocar Farmatic, flags o tareas; push.

## 8. 08005707 tras 08L82633A (2026-11-24, 13:27)

`CONFIRMADO POR LECTURA READ_ONLY` (`noche_2411\08L82633A.json`, `resim_1327_08L82633A.json`):

- Pio grabó las tamsulosinas como **08L82633A** (299725, SAFA, 05/05, PUC 21,99, **sin recepción**). Farmatic no deja
  modificar 08L82633 (albarán cerrado) y 08L82633A no se anula.
- 08L82633 (638,82) + Q039320/2026 (27,32) + 08L82633A (21,99) = **688,13**, la línea exacta. El motor no lo casa:
  R17 y R20 solo emparejan 1+1 y R20 exige la misma recepción. 08005707 sigue en DIFERENCIA 688,15.
- Pio pidió una aprobación manual R18 para esa línea. **R18 no lo permite** (solo cambios de identidad de albaranes)
  y no existe ninguna aprobación manual de líneas. Pio decide R21 como migración 40 (§9). 08005707 quedó fuera del
  2BP del 24/11 (tandas 01–02 en `carga_abril_mayo\2bp_2411`, 10/10 CONCILIADA).

## 9. R21 como migración 39 (DISEÑO, 2026-11-24 noche; IMPLEMENTADA EN LOCAL el 2026-11-25)

Encargo de Pio (2026-11-24): exacto + hasta 3 complementarios (internos «Q0» o variante con letra) del mismo
proveedor (R9) y del mismo día, suma en R11, falla cerrado si hay más de una combinación, trazabilidad. Se diseñó
como migración 40; **Pio la renumera a 39** (2026-11-25, §9.10). Esta sección conserva el diseño de la noche del 24;
lo que cambió al implementarla (R21-D1 revisada, número 39 y lo que exige) está en §9.10 y §9.11, que prevalecen.

### 9.1 Caso real y conflicto con «mismo día» (`CONFIRMADO POR LECTURA READ_ONLY`)

08005707, línea 08L82633 (PDF 05/05, 688,13):

| Albarán | IdContador | Fecha | PUC | Recepción | Papel |
|---|---|---|---|---|---|
| 08L82633 | 272819 | 05/05 | 638,82 | 49490 | A (exacto) |
| Q039320/2026 | 272818 | **06/05** | 27,32 | 49490 | interno |
| 08L82633A | 299725 | 05/05 | 21,99 | **ninguna** | variante con letra |

La suma es 688,13, igual a la línea. **Con «mismo día que A» estricto, Q039320/2026 no entra** (es del 06/05) y R21
no cierra 08005707. Por eso la decisión **R21-D1** (§9.7) propone que un complementario valga si es del **mismo día
que A o de la misma recepción que A**. La segunda condición es exactamente la de R17, ya aprobada. Con esa regla los
tres albaranes casan; con «mismo día» estricto, no.

### 9.2 Regla (`PROPUESTA`)

Una línea documental `CARGO` que sigue `SIN_COINCIDENCIA` tras el 1:1 casa por R21 con **A + B1..Bn**, n = 1..3:

- **A:** el albarán del número **exacto** de la línea (D4: solo `EXACTA`), con numeración no interna, a ±15 días de
  la línea (como R20), con PUC.
- **Bi (complementarios):** cada uno es
  - un interno `^[A-Z]\d{6}/\d{4}$` (`_NUMERO_INTERNO_FARMATIC`, `conciliacion.py:28`), o
  - la variante con **una letra final** del número de la línea (`08X99999A`, como R20; solo Alliance).
- Además, todos los Bi:
  - tienen el **mismo proveedor que A (R9)** (`cf_id_proveedor_comparable`) y la misma farmacia;
  - son del **mismo día que A** (`Bi.fecha = A.fecha`) **o** de la misma recepción no nula que A (R21-D1);
  - tienen **PUC > 0** (R21-D3: un PUC 0 no cambia la suma y haría ambiguas todas las combinaciones; los negativos
    son devoluciones);
  - están libres: sin reserva de otra factura (R15), no usados por otra línea de esta factura, sin revisión
    `AUSENTE_EN_FARMATIC` abierta (2BD), y su número no es una línea de otra factura.
- **Suma:** |PUC(A) + Σ PUC(Bi) − importe de la línea| ≤ 0,05 (la tolerancia por línea de R17 y R20).
- **Solo cargos**; nunca HEFAME ni abonos.

**Relación con R17 y R20.** R17 (A + 1 interno de la misma recepción) y R20 (A + su variante de la misma recepción)
son casos particulares 1+1. Se conservan tal cual (la BD los sigue validando igual) y R21 cubre el resto:

- se enumeran **todas** las combinaciones válidas de la línea (R17, R20 y R21 juntas; cada conjunto de albaranes,
  una sola vez);
- si un conjunto es R17 o R20 válido, conserva esa regla, así que lo que casa hoy no cambia.

### 9.3 Falla cerrado

- **Más de una combinación** para una línea (contando R17, R20 y R21 juntas) → `AMBIGUO_R21` (o `AMBIGUO_R17` /
  `AMBIGUO_R20` si todas son de esa regla, como hoy). La línea queda `SIN_COINCIDENCIA`.
- **Un albarán en las combinaciones de dos líneas** → `CONFLICTO_R21`. Las dos líneas quedan sin casar, sin depender
  del orden, como en `_aplicar_r17` (`conciliacion.py:578-617`, `CONFIRMADO POR CÓDIGO`).
- **Tope de enumeración:** como mucho 12 candidatos complementarios por línea (Σ C(12, k), k = 1..3, son 298
  combinaciones). Con más, la línea queda sin casar con `AMBIGUO_R21` y motivo `DEMASIADOS_CANDIDATOS` (R21-D4).
- Sin la migración 40, o con la marca apagada, R21 no se usa: la línea sigue sin casar y la noche la deja para
  revisar, como R20 sin la 36.

### 9.4 Trazabilidad y persistencia

- La línea se persiste como **n + 1 detalles `UNO_A_VARIOS`** con el mismo `factura_albaran_extraido_id`. Cada uno
  aplica su PUC y lleva en la provenance:
  - `regla: R21` y su papel (`NUMERO`, `INTERNO` o `LETRA_FINAL`);
  - el motivo del complementario (`MISMO_DIA` o `MISMA_RECEPCION`);
  - la suma de la combinación, la tolerancia y el número de combinaciones evaluadas (1).
- Todos los albaranes quedan reservados (R15, sin cambios).
- **R11:** la línea cuenta como **un** albarán casado. La BD ya lo hace con `count(distinct
  factura_albaran_extraido_id) filter (where tipo_relacion = 'UNO_A_VARIOS')` (`30_cf_detalle_por_linea.sql:214-217`,
  `CONFIRMADO POR CÓDIGO`).
- `cf_detalles_por_linea` (30) ya suma los `UNO_A_VARIOS` de una línea sin suponer que son 2 (línea 54,
  `CONFIRMADO POR CÓDIGO`). `valores_por_linea`, en Python, igual.
- `cf_persistir_conciliacion` (30) agrupa los `UNO_A_VARIOS` por línea y llama a `cf_linea_r17_valida`
  (`30_cf_detalle_por_linea.sql:278-290`, `CONFIRMADO POR CÓDIGO`). **No hay que regenerar la RPC**: basta con
  redefinir la función de validación, como hizo la 36.

### 9.5 Migración 40 (`40_cf_r21_complementarios.sql` y su rollback)

- Requiere la 36 (comprueba `cf_configuracion.conciliacion_r20`) y aborta si no está.
- Añade `cf_configuracion.conciliacion_r21 boolean not null default false` (R21-D5: **apagada por defecto**; Pio la
  enciende en el editor SQL tras el postcheck). Es el único dato que cambia.
- Redefine `public.cf_linea_r17_valida(uuid, text, jsonb, jsonb)` con `create or replace` y la **misma firma**, así
  que conserva la ACL de la 24. No nombra el rol del sistema.
  - `p_detalles` tiene entre **2 y 4** elementos, y en `p_todos` esa línea tiene los mismos.
  - Si son 2 y valen como R17 o R20, devuelve `true`. Esas dos ramas se copian de la 36 sin cambios.
  - Rama **R21**, solo si `conciliacion_r21` vale `true`:
    - línea `CARGO` de la propia factura, con número e importe;
    - cada detalle es un albarán existente con PUC y aplica su PUC; todos son distintos y de la misma farmacia;
    - exactamente **un** A con el número exacto de la línea (normalizado como en la 36), no interno, a ±15 días;
    - cada uno de los demás es interno o variante `08X99999` + letra de ese número, con **PUC > 0**;
    - todos con el mismo proveedor que A (`cf_id_proveedor_comparable`);
    - cada complementario con `fecha = A.fecha`, o con la misma recepción no nula que A;
    - |Σ PUC − importe de la línea| ≤ 0,05.
  - Cualquier otra forma devuelve `false`, y el rechazo sigue siendo `LINEA_R17_NO_VALIDA`.
- **Lo que la BD no comprueba** (solo Python, como la deuda aceptada de R17): la unicidad de la combinación y que un
  complementario no sea el número de una línea de otra factura.
- **Rollback 40:** vuelve a crear la función exactamente como la deja la 36 y quita `conciliacion_r21`. Aborta si
  hay alguna conciliación vigente con una línea R21, porque el validador antiguo no la aceptaría al volver a
  conciliar.

### 9.6 Código (para el hito de implementación; hoy no se toca nada)

- `conciliacion.py`:
  - `ResultadoBusquedaAlbaran`: `complementarios: tuple[CandidatoAlbaranSupabase, ...]` en lugar de un solo
    `complementario`, conservando la lectura de R17 y R20;
  - `_combinaciones_r21(documental, libres, …)`: enumera A + 1..3 Bi con las condiciones de §9.2;
  - `_aplicar_r17` cuenta juntas las combinaciones de R17, R20 y R21 (estados `MATCH_R21`, `AMBIGUO_R21` y
    `CONFLICTO_R21`);
  - `detalles_desde_busqueda`: n + 1 detalles.
- `lectura_readonly.r21_habilitada(lector)`: como `r20_habilitada` (`lectura_readonly.py:200-209`), primero
  `information_schema` y después el valor. Se inyecta en el repositorio, la noche, el simulador READ_ONLY del 2AT y
  las series 2BJ y 2BP.
- `REGLAS_CRITICAS`: bloque R21 en «Persistencia y conciliación», con la decisión de Pio.

### 9.7 Decisiones para Pio

**DECIDIDAS por Pio (2026-11-24, noche):** R21-D1 aprobada (complementario del mismo día que A **o** de la misma
recepción que A, como R17); R21-D2 a D8, como se recomiendan. Implementación y despliegue: 2026-11-25.

**R21-D1 REVISADA por Pio (2026-11-25), tras el banco R21-D8 (§9.11):** un complementario vale si es de la **misma
recepción (no nula) que A**, o si **no tiene recepción y es del mismo día que A**. Un albarán de otra recepción es otra
entrega aunque sea del mismo día. Descartada la alternativa (evaluar R21 solo si R17 y R20 no dan nada). La fila D1
de la tabla queda como histórico; manda este párrafo.

| Id | Pregunta | Recomendación |
|---|---|---|
| R21-D1 | «Mismo día»: con la regla literal, Q039320/2026 (06/05) no entra y **08005707 no cierra** | Complementario válido si es del **mismo día que A o de la misma recepción que A** (la condición de R17). Cierra 08005707 y no amplía a ±1 día |
| R21-D2 | ¿A puede ser `LETRA_FINAL`, como en R17? | No: solo `EXACTA` (D4) |
| R21-D3 | Complementarios con PUC 0 o negativo | Excluidos (PUC > 0). Hay internos SAFA a 0,00 (Q039321/2026 y Q039322/2026) que harían ambiguo cualquier caso |
| R21-D4 | Tope de candidatos complementarios por línea | 12; con más, `AMBIGUO_R21` con `DEMASIADOS_CANDIDATOS` |
| R21-D5 | Marca `conciliacion_r21` | `false` por defecto; Pio la enciende tras el despliegue y el postcheck (R20 se desplegó con `true`) |
| R21-D6 | Ventana de A | ±15 días de la línea, comprobada también en la BD, como R20 |
| R21-D7 | 08005707 tras el despliegue | ~~Esta noche gasta un intento~~ **Corregido (2026-11-25):** la noche del 24→25/11 la simuló, la dejó para revisar y **no gastó intento** (0 intentos fallidos, sin conciliación). Tras la 39 y la marca: entra en el 2BP de las 15 pendientes como n.º 1 del selector, sin reintento |
| R21-D8 | Banco antes de implementar | Medición READ_ONLY de todas las líneas `SIN_COINCIDENCIA` vigentes: cuántas cierra R21 y cuántas quedan `AMBIGUO`. Si cierra algo inesperado, PARAR |

### 9.8 Tests previstos

- **Unitarios (Python):**
  - el caso 08005707 con los 3 albaranes, con R21-D1 → `MATCH_R21`, 3 detalles y R11 = 1;
  - el mismo caso con «mismo día» estricto → sin casar;
  - 2 y 3 complementarios casan; 4 → sin casar;
  - dos combinaciones posibles → `AMBIGUO_R21`; un albarán en dos líneas → `CONFLICTO_R21`;
  - no entra un complementario de otro proveedor, de otro día y otra recepción, con PUC 0, reservado, ausente en
    Farmatic o que sea número de otra factura;
  - A con letra final, o fuera de ±15 días → sin casar;
  - lo que hoy casa por R17 o R20 sigue igual y con la misma regla (sus tests, sin cambios);
  - sin la 40, o con la marca a `false` → sin R21; más de 12 candidatos → `DEMASIADOS_CANDIDATOS`.
- **PostgreSQL 17 local (plantilla 38 + 40):**
  - la 40 se aplica dos veces (idempotente) y el rollback deja exactamente la función de la 36;
  - el worker real persiste CONCILIADA una línea R21 con 3 detalles y 3 reservas;
  - la RPC rechaza con `LINEA_R17_NO_VALIDA` una suma fuera de 0,05, un complementario de otro proveedor o de otro
    día y otra recepción, uno con PUC 0, 5 detalles, dos A, y cualquier R21 con la marca a `false`;
  - R17 y R20 se siguen aceptando con la marca apagada y encendida;
  - el rollback aborta con una línea R21 vigente.
- **Ensayo de despliegue:** `desplegar_40` en PostgreSQL 17 (preflight, aplicación única y postcheck por fila: solo
  cambian la función y la columna nueva), añadido a la suite histórica.

### 9.9 Plan de despliegue (39-D; texto de la noche del 24, numerado como 39)

1. Commit con código, migración 39, rollback, `desplegar_39` y tests; suite completa + histórica y revisor PASS. El
   código no usa R21 sin la 39 ni con la marca apagada, así que puede subirse antes del despliegue.
2. Push de Pio, fuera de 20:00–23:15.
3. Pio apaga los flags.
4. Preflight READ_ONLY: puerta git (ls-remote), tareas a 60 min o más, sin claims ni locks, la 38 desplegada y la 39
   ausente.
5. `desplegar_39` una sola vez, con confirmación explícita de Pio; postcheck por fila.
6. Pio enciende `conciliacion_r21` en el editor SQL (R21-D5).
7. 2BP de las 15 pendientes (08005707 la primera, R21-D7); después Pio enciende los flags.

### 9.10 Numeración: cada migración exige la anterior (`DECIDIDA por Pio, 2026-11-25`)

**DECISIÓN DE PIO (2026-11-25):** numeración por orden de despliegue: **R21 = 39**, **H7b = 40**, **«Actualizar
ahora» = 41**. La 39 exige la 38 (`MIGRACION_38_AUSENTE`) y, además, la 36 (`MIGRACION_36_AUSENTE`, marca de R20).
Texto de la noche del 24, como histórico:

`CONFIRMADO POR CÓDIGO`: cada migración aborta si falta la anterior (`MIGRACION_34_AUSENTE` en la 35:27,
`MIGRACION_35_AUSENTE` en la 36:20, `MIGRACION_36_AUSENTE` en la 37:22, `MIGRACION_37_AUSENTE` en la 38:32), y
REGLAS_CRITICAS («Cashflow (H7)», numeración) dice: «Cada migración exige la anterior».

- La 39 («Actualizar ahora») está decidida pero **no existe**. Con la regla, una 40 (R21) no puede desplegarse
  mañana sin la 39, ni una 41 (H7b) sin la 40.
- La comprobación del 24/11 («no hay ningún fichero 39, 40 ni 41») era cierta, pero no bastaba: faltaba esta regla.
- **Recomendación:** numerar por orden de despliegue: **R21 = 39** (mañana), **H7b = 40**, **«Actualizar ahora» =
  41** (o la siguiente libre cuando se implemente). Alternativa: mantener 40/41 y que cada una exija la última
  desplegada en lugar de la anterior en número, lo que cambia la regla de REGLAS_CRITICAS.

### 9.11 Implementación y banco (2026-11-25; `CONFIRMADO POR TEST` y `CONFIRMADO POR LECTURA READ_ONLY`)

**Banco R21-D8 con la D1 de la noche del 24** (`verificar_banco_r21.py`, salida en
`C:\ControlFarmacias\carga_abril_mayo\r21\banco_r21_2511.json`, 93 facturas de PIO, R20 como en la BD):

- 08005707 / 08L82633 pasa a `MATCH_R21` con 3 detalles, como se esperaba.
- **Inesperado (PARADA por R21-D8):** las líneas R17 de **08005706** (08B56937) y **08012619** (08D52644, ya
  CONCILIADA) pasaban a `AMBIGUO_R21`. Junto al interno de la recepción de A hay una variante con letra del mismo día
  pero de **otra** recepción con exactamente el mismo PUC: Q039349/2026 y 08B56937A (12,80; recepciones 49546 y
  49547); Q040931/2026 y 08D52644A (27,20; 54099 y 54100). Diagnóstico en `r21\diagnostico_ambiguo_2511.json`.
- Con la D1 revisada (probada antes sin tocar `src`, `r21\banco_r21_variante_c_2511.json`) y con el código final
  (`r21\banco_r21_final_2511.json`): **solo cambia 08005707**, nada queda `AMBIGUO_R21`, `CONFLICTO_R21` ni con
  `DEMASIADOS_CANDIDATOS`. Un error igual con y sin R21: 08006123, `TRAZABILIDAD_SERVICIO_INSUFICIENTE` (la
  re-normalización pendiente, D5).

**Implementación:**

- `sql/migrations/39_cf_r21_complementarios.sql`: exige la 38 y la 36; añade `conciliacion_r21` (default `false`);
  redefine `cf_linea_r17_valida` con la misma firma. Las ramas R17 y R20 de la 36 se conservan con el mismo criterio
  dentro de un bloque `r17_r20` (si no valen, se prueba R21 en lugar de devolver `false`); la rama R21 solo con la
  marca a `true` y de 2 a 4 detalles. Rollback: falla cerrado con una línea R21 vigente
  (`ROLLBACK_39_CON_LINEAS_R21_VIGENTES`); si no, restaura el texto exacto de la 36.
- `conciliacion.py`: `_complementario_r21`, `_combinaciones_r21` (tope 12, R21-D4) y `_aplicar_r17` con R17, R20 y
  R21 contadas juntas; cada conjunto de albaranes una vez, con la regla R17 o R20 si lo es. `_detalles_r21`: n + 1
  detalles con `papel_r21`, `motivo_r21` (`MISMA_RECEPCION` o `MISMO_DIA_SIN_RECEPCION`), `importe_combinacion`,
  `tolerancia_linea`, `complementarios` y `combinaciones_evaluadas`. Sin motivo, la provenance de una línea sin casar
  es la de siempre.
- `lectura_readonly.r21_habilitada`, inyectada en el repositorio, los dos compositores, la noche, el simulador del 2AT
  (`lineas_r21` en el resumen) y la serie 2BP.
- Tests: `tests/facturas/runtime_supabase/test_r21.py` (unitarios, con la regresión del banco) y
  `test_integracion_pg17_r21.py` (plantillas 38/39/39_rollback, la BD acepta y rechaza, R17 y R20 con la marca
  apagada y encendida, rollback que aborta, worker 08007969 convertido en R21, noche sin la 39 o sin la marca, ensayo
  de `desplegar_39`). Los ensayos del despliegue y el rollback entran en la suite histórica en el commit del 39-D.
