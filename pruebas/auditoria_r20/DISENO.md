# R20: una línea del PDF = su albarán exacto + su variante con letra final (migración 36). DISEÑO

Estado: **IMPLEMENTADO EN LOCAL** (2026-11-19, `CONFIRMADO POR TEST` en PostgreSQL 17 local), con las decisiones de
Pio (§0 y §8). Migración 36 **sin desplegar**; producción solo con lecturas READ_ONLY de diagnóstico, medición y
verificación (§2.3).

- **Origen:** primera noche `REAL` (18→19/11). 08013495 (Alliance, 14.163,25) queda para revisar con una diferencia de
  118,16. La línea 08D79747 (09/11, 118,25) está en Farmatic partida en `08D79747` (77,49) y `08D79747A` (40,76), de la
  misma recepción 54736. R17 no la cubre, porque exige que el segundo albarán tenga numeración interna
  (`conciliacion.py:488-525`). **Pio no puede unificarlos en Farmatic.**
- **Etiquetas:** `CONFIRMADO POR CÓDIGO` (con fichero:línea), `CONFIRMADO POR LECTURA READ_ONLY` (§2) y `PROPUESTA`.

## 0. Decisiones de Pio (2026-11-19)

| Id | Decisión |
|---|---|
| **R20** | Una línea del PDF casa con la suma de **su albarán exacto y su variante con letra final**, como R17: misma recepción, mismo proveedor (R9), solo 1+1, sin HEFAME ni abonos. Python + migración que amplíe la validación de la BD; detalle por línea `UNO_A_VARIOS` |
| **N1** | Numeración: **R20 = migración 36**, defectos directos a REVISION = 37, Cashflow = 38. R20 se despliega antes que las otras dos |
| **N2** | **AUTORIZACIÓN EXPRESA (reconfirmada):** el rol del sistema se nombra **solo** en la 38 y su rollback. La 36 **no** lo nombra |
| **B1** | La 36 **redefine `cf_linea_r17_valida`**, sin regenerar `cf_persistir_conciliacion`. Mismo código de rechazo, `LINEA_R17_NO_VALIDA` |
| **B2** | En R20, **la BD sí comprueba la ventana de ±15 días** (en R17 es deuda aceptada) |
| **B3** | **El código usa R20 solo si detecta la 36 en la BD.** Si no, la factura sigue para revisar, sin gastar intentos |

## 1. Regla R20

Una línea documental **cargo** que queda `SIN_COINCIDENCIA` tras el casado 1:1 y tras R17 puede casar con la suma de
**dos** albaranes de Farmatic:

- **A:** el de su número **exacto** (`EXACTA`), con fecha a ±15 días de la línea;
- **B:** la variante de ese número **con una letra final** (`LETRA_FINAL`, `^08[A-Z]\d{5}[A-Z]$` sobre el número de la
  línea), también a ±15 días.

Condiciones (las de R17 salvo el tipo de B):

- **misma recepción** (`albaranes.id_recepcion`, no nula);
- **mismo proveedor** (R9, id comparable; ECO360 + SAFA no es pareja, igual que en R17);
- ninguno reservado (R15) ni casado por otra línea; el número de B no es una línea de otra factura;
- **PUC(A) + PUC(B)** dentro de la tolerancia por línea (0,05). Cada detalle aplica el PUC de su albarán;
- **solo 1+1**: nunca exacto + dos variantes;
- solo cargos; nunca HEFAME (casado propio) ni abonos.

`CONFIRMADO POR CÓDIGO`: `LETRA_FINAL` solo existe para Alliance (`conciliacion.py:30` y `:198-200`), así que R20 es en
la práctica solo Alliance.

Decisiones de implementación (no cambian la regla):

- **Prioridad:** 1:1 → R17 → R20 solo sobre lo que sigue `SIN_COINCIDENCIA`.
- **Falla cerrado sin depender del orden:** las parejas R17 y R20 de una línea se cuentan juntas.
  - Más de una pareja (de cualquiera de las dos reglas) → `AMBIGUO_R17` o `AMBIGUO_R20`.
  - Un albarán en las parejas de dos líneas → `CONFLICTO_R17` o `CONFLICTO_R20` en ambas.
  - La línea queda sin casar.
- **R11:** la línea R20 cuenta como **un** albarán casado. La BD ya lo hace para toda línea `UNO_A_VARIOS`
  (`30_cf_detalle_por_linea.sql:213-216`).
- **Detalle por línea (2BR):** sin cambios. `cf_detalles_por_linea` ya suma por línea los detalles `UNO_A_VARIOS`
  (`30_cf_detalle_por_linea.sql:54-55` y `:63-69`).

## 2. Caso real y medición

`CONFIRMADO POR LECTURA READ_ONLY`. Evidencias en `C:\ControlFarmacias\evidencias_08013495\` y
`C:\ControlFarmacias\evidencias_r20\`, con `SHA256SUMS.txt`.

### 2.1 08013495 / 08D79747

- **Hoy** (simulación 2AT, sin R20): 125 casadas 1:1 y 1 `SIN_COINCIDENCIA`, 0 líneas R17 y 3 movimientos.
  - Explicado: 14.045,09.
  - Diferencia: **118,16** = 118,25 (la línea) − 0,04 (céntimos de 6 líneas 1:1) − 0,05 (total de la factura menos la
    suma de sus líneas).
- **Con R20** (cálculo sobre los mismos datos; se verificará con el código):
  - la línea casa con `08D79747` (77,49) + `08D79747A` (40,76) = 118,25 en la recepción 54736, mismo proveedor
    `0002`, fechas iguales;
  - explicado: 14.163,34;
  - **diferencia −0,09**;
  - tolerancia R11 con 126 líneas casadas: máx(0,05; mín(0,01 × 126; 0,50)) = 0,50 (`conciliacion.py:856-872`);
  - resultado: **`CONCILIADA`**. El detalle de la línea queda `COINCIDE` con diferencia 0,00.
- Ninguno de los dos albaranes está reservado ni aparece en otra factura.

### 2.2 Banco Alliance completo: qué cambia

Medición READ_ONLY sobre Supabase (2026-11-19, `medicion.json`, sha `9b59b085…`):

- **3.512 líneas Alliance** (`08X99999`) en `facturas_albaranes_extraidos` de PIO.
- **163 albaranes** de Farmatic con variante de letra final.
- **1 sola línea** con exacto + variante en la misma recepción, y suma dentro de 0,05: **08013495 / 08D79747**.
  - 0 líneas con más de una pareja.
  - Ninguna otra variante comparte recepción con su exacto.
- **Qué cambia:**
  - 08013495 pasa a `CONCILIADA` (−0,09);
  - después la noche llega a 08013498, hoy bloqueada detrás de 08013495;
  - las conciliaciones ya persistidas no se tocan: R20 solo actúa en conciliaciones nuevas, y no hay reprocesado;
  - en las demás facturas no cambia nada.
- **Pendiente tras implementar** (como `verificar` del 2BE):
  - rehacer el banco del espejo (PDF que no están en Supabase) con el código de `src`;
  - comprobar que no aparece ninguna otra línea R20 y que las 47 facturas del banco 2AZ no cambian.

### 2.3 Verificación con el código de `src` (2026-11-19)

`CONFIRMADO POR LECTURA READ_ONLY`. `pruebas/auditoria_r20/verificar_banco_r20.py` construye los detalles de cada
factura de PIO con líneas de albarán (`construir_detalles` sobre el cliente de lectura del 2AT), con R20 apagado y
encendido. Resultado (`verificacion_banco.json`, sha `d1dce320…`):

- 65 facturas revisadas, 0 errores;
- **un solo cambio:** 08013495 / 08D79747, de `SIN_COINCIDENCIA` a dos detalles `UNO_A_VARIOS` con regla R20
  (297826 = 77,49 y 297825 = 40,76);
- en las demás facturas, todos los detalles son iguales.

El test del caso real (`test_r20.py`) reproduce con las mismas entradas (fixture READ_ONLY) `DIFERENCIA` 118,16 sin
R20 y `CONCILIADA` −0,09 con R20, y comprueba que ninguna otra línea cambia.

## 3. Implementación en Python (hecha)

- **`src/facturas/runtime_supabase/conciliacion.py`:**
  - `_parejas_r20(documental, libres, …)`: A `EXACTA` y B `LETRA_FINAL` del mismo número, las dos a ±15 días, misma
    recepción, mismo id de proveedor comparable, B no reservado ni número de otra factura, PUC + PUC ≤ 0,05, solo
    `CARGO`;
  - `_aplicar_r17` pasa a aplicar R17 y R20 con el recuento conjunto de §1. Estados `MATCH_R20`, `AMBIGUO_R20` y
    `CONFLICTO_R20`. Solo si `r20_habilitada` (B3);
  - `detalles_desde_busqueda`: una línea R20 da dos detalles `UNO_A_VARIOS` con `regla: "R20"` y
    `papel_r20: NUMERO | LETRA_FINAL` en la provenance, cada uno con su PUC;
  - `buscar_albaranes_factura(…, r20_habilitada: bool = False)`. **Por defecto, apagada.**
- **Detección de la 36 (B3)**, sin depender del cliente (instrucción de Pio):
  - `lectura_readonly.r20_habilitada(lector)`: con una sesión de solo lectura consulta `information_schema` y, solo si
    la columna existe, su valor. Así nunca aborta la transacción de solo lectura;
  - `RepositorioRuntimeSupabase(cliente, r20_habilitada=...)` recibe esa detección de quien lo construye: la noche
    (`noche_automatica._r20_en_bd`, con su conexión de lectura), la simulación de la noche, el simulador 2AT y el
    worker de la serie 2BP. Los compositores la reciben como parámetro opcional;
  - sin detección, o si falla, R20 queda apagada;
  - la línea queda `SIN_COINCIDENCIA`, la simulación da `DIFERENCIA` y la noche la deja para revisar sin reclamarla
    (`noche_automatica.py:467-482`): **no se gasta ningún intento**. Igual en la serie 2BP, que para si no simula
    `CONCILIADA`;
  - el simulador 2AT y la noche usan el mismo camino (`construir_detalles`), así que siempre simulan lo mismo que
    persistiría el worker.
- **Simulador 2AT** (`auditoria_readonly._simular`): `resumen_detalles.lineas_r20` junto a `lineas_r17`.

## 4. Migración 36 (hecha, sin desplegar)

`sql/migrations/36_cf_r20_letra_final.sql` y su rollback. Requiere la 35. Idempotente. **No nombra el rol del
sistema** (N2).

- **`create or replace function public.cf_linea_r17_valida(uuid, text, jsonb, jsonb)`** con la misma firma (B1):
  - devuelve cierto si la pareja es **R17**, con el cuerpo de la 24 sin cambios (`24_cf_r17_recepcion.sql:22-95`),
    **o** si es **R20**:
    - exactamente 2 detalles y ningún otro en la línea;
    - la línea es un `CARGO` de la propia factura, con importe;
    - los dos albaranes existen, tienen PUC y cada detalle aplica su PUC;
    - **ninguno** tiene numeración interna;
    - uno con el número de la línea **exacto** y el otro `^08[A-Z][0-9]{5}[A-Z]$` con `left(…, 8)` igual al de la
      línea;
    - misma farmacia y misma recepción, no nula;
    - mismo proveedor (`cf_id_proveedor_comparable`);
    - **las dos fechas a ±15 días de `fecha_albaran` de la línea** (B2);
    - |PUC + PUC − importe| ≤ 0,05.
  - Si no se cumple, `cf_persistir_conciliacion` (de la 30, sin cambios) sigue lanzando `LINEA_R17_NO_VALIDA`
    (`30_cf_detalle_por_linea.sql:278-290`).
  - `create or replace` conserva la ACL de la 24 (nadie salvo el propietario; `:407`).
- **Marca de la 36 (B3):** columna `cf_configuracion.conciliacion_r20 boolean not null default true`, legible por el
  cliente del worker como el resto de la configuración, sin grants nuevos. Es el único cambio de datos: añade el valor
  a la única fila de `cf_configuracion`. Ver decisión 1 de §8.
- `comment on function` actualizado (R17 y R20).
- **Rollback:**
  - restaura el cuerpo exacto de la 24 y quita la columna;
  - no toca conciliaciones: las líneas R20 ya persistidas siguen siendo válidas como datos, pero una nueva no
    persistiría (y el código, sin la marca, no la propone).

## 5. Tests (hechos)

- **`tests/facturas/runtime_supabase/test_r20.py`, sin BD:**
  - caso real 08D79747;
  - prioridad del 1:1 y de R17;
  - variantes que no casan: otra recepción, sin recepción, otro proveedor, ECO360, suma fuera, fuera de ventana (A o
    B), reservado, número de otra factura, dos letras, abono y HEFAME;
  - `AMBIGUO_R20` (dos variantes), ambigüedad R17 + R20 y conflicto entre líneas;
  - con `r20_habilitada=False`, nada cambia.
- **`test_integracion_pg17_r20.py` (`pg17_local`; plantillas `36` y `36_rollback`):**
  - la 36 exige la 35; rollback = esquema 35 exacto y datos intactos; ACL de la función sin cambios;
  - 08013495 reproducido: `CONCILIADA` −0,09 con las dos reservas y el detalle por línea `COINCIDE`;
  - sin la 36: `DIFERENCIA` 118,16, sin fallo ni intento consumido;
  - la BD rechaza las parejas falsas (incluida la fecha fuera de ventana) y sigue aceptando R17;
  - simulador 2AT con la línea R20;
  - noche: sin la 36 la deja para revisar; con la 36, la concilia;
  - `desplegar_36.py`: precondiciones de solo lectura y ensayo completo.
- Revisar los tests que fijan el cuerpo de `cf_linea_r17_valida` (2BE, 2BR).

## 6. Despliegue 36-D (`PROPUESTA`, con la confirmación de Pio por paso)

- **El orden ya no es peligroso (B3):** el código puede ir a `main` antes que la 36. Sin la marca, R20 está apagada y
  la noche sigue dejando 08013495 para revisar.
- **Secuencia:**
  1. commit con código (36, rollback, Python, `desplegar_36`, tests), suite completa y revisor PASS; push de Pio.
     `desplegar_36` exige el commit ya subido (puerta git del 2026-11-19);
  2. fuera de la ventana de las tareas (21:00–23:15), sin noche `EN_CURSO`, Pio apaga los dos flags (los preflights los
     exigen apagados);
  3. preflight READ_ONLY, `desplegar_36` una vez y postcheck por fila (solo cambian la función y la columna);
  4. Pio vuelve a encender los flags.
- **Primera conciliación con R20:** ver decisión 2 de §8.

## 7. Documentos canónicos (en el commit de la implementación)

- **REGLAS_CRITICAS:** regla R20 junto a R17 (2BE), con la ventana revalidada en la BD; numeración 36/37/38 (ya
  registrada el 2026-11-19).
- **ESTADO_ACTUAL:** hito R20 en local y, después, 36-D.

## 8. Decisiones de Pio (2026-11-19, tomadas)

1. **Marca de la 36 (B3): DECIDIDO, columna `cf_configuracion.conciliacion_r20`.**
   - Ventaja: el worker ya lee esa tabla, no hace falta ningún grant y la 36 no nombra el rol del sistema.
   - Coste: añade un valor a la fila de configuración, y el postcheck de 36-D lo espera.
   - Además, se puede usar como interruptor: `false` apaga R20 sin rollback.
   - Alternativa: una función marca. Necesitaría EXECUTE para el rol del sistema, que la 36 no puede nombrar (N2).
2. **Primera conciliación de 08013495 tras 36-D: DECIDIDO, la noche.** Es su n.º 1, simulará `CONCILIADA` y
   seguirá con 08013498.
3. **La columna a `false` apaga R20 sin rollback: DECIDIDO, sí**, como un flag más.

## 9. Fuera de alcance

- Parejas 1+N (exacto + dos variantes), N+1 y abonos.
- Proveedores distintos de Alliance.
- Reprocesar conciliaciones ya persistidas.
- Modificar Farmatic.
