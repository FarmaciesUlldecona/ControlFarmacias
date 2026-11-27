# Hito HEFAME: diseño del lector y medición (segundo proveedor)

Encargo de Pio (2026-11-15). **Solo diseño y medición**: sin producción (más allá de lecturas READ_ONLY), sin código
en el repositorio y sin persistir nada. Scripts y salidas fuera del repositorio, en
`C:\ControlFarmacias\evidencias_hefame\` (`SHA256SUMS.txt`):

- `inventario_hefame.py` → `inventario.json`;
- `medicion_hefame.py` → `medicion.json`;
- `albaranes_hefame_readonly.py` → `albaranes.json`;
- `documentos_hefame_readonly.py` → `documentos_supabase.json`.

Etiquetas de certeza: `CONFIRMADO POR MEDICIÓN` (espejo local o lectura READ_ONLY de Supabase) y `PROPUESTA`
(pendiente de decisión de Pio).

## 0. Decisiones de Pio (2026-11-18; H3–H5 el 2026-11-19)

| Id | Decisión de Pio |
|---|---|
| **H1** | El cargo de **80,00 € de base S.R.** de las facturas de fin de mes es el **cargo cooperativo HEFAME**, **fijo cada mes** (§2.4) |
| **H2** | **`APROAFA`** es la aportación a la Asociación para la Promoción de la Asistencia Farmacéutica en España: **CARGO** (§2.3) |
| **H3** | `Resumen Liquidaciones Comerciales` son **pequeños descuentos sobre especialidad** (medicamento, IVA 4 %, base S.R.): **ABONO** (§2.3) |
| **H4** | Los números de 9 dígitos que empiezan por `91` son **albaranes normales**. Farmatic los registra con numeración interna `Q…`/`R…`: **casan por numeración interna, importe y fecha, con candidato único** (como R15b) (§4.1). Los 2 de 0563863435 (20.10) eran formulación magistral que no se había entrado: Pio los registró el 18.11 y ya están en Supabase (914618399 a 67,15 frente a 67,01 del PDF: **Pio corrige el importe en Farmatic**; 914621188 a 33,57) |
| **H5** | Factura del 30.09.2026 **importada** el 18.11 (`HEFAME VTO 5.10.26 PIO.pdf`). El banco pasa a **15 facturas** |
| **H6** | Un desfase de S.R. distinto de 80,00 en una factura de fin de mes **para el lector** (falla cerrado). Si HEFAME cambia la cuota, se actualiza con una decisión de Pio (§2.4) |
| **H7** | Una fila `APROAFA` negativa **para el lector** (falla cerrado), sin invertir el sentido (§2.3) |

Siguen también pendientes la tolerancia del control de la página 2 (§2.5) y las reglas de conciliación de §4.

## 1. Inventario del espejo

`CONFIRMADO POR MEDICIÓN`:

- **Identificación por contenido:** razón social `HDAD.FMCTCA.MEDIT.,S.C.L.` y CIF `F30004444` en el texto, nunca por
  el nombre del fichero (S5). El espejo es `C:\GoogleDrive\FACTURES PIO`: 641 PDF, 618 distintos por SHA.
- **14 facturas HEFAME distintas**, todas con el formato conocido. Tienen las 7 señales del reconocedor de
  `hefame-local`: razón social, CIF, relación de albaranes, tabla de bases, desglose total factura, vencimientos y
  paginación interna. Todas tienen 2 páginas.
- **Periodo:** del 10.06.2026 al 31.10.2026, con una factura por decena (los días 10, 20 y fin de mes).
  - **Faltaba la del 30.09.2026** (15 decenas y 14 facturas). **Importada el 18.11** (H5): el banco queda en 15
    facturas. Esta medición es de las 14 anteriores.
- **Importe total:** 2.907,66 €. Hay 81 filas numéricas (albaranes o documentos de entrega).
- **Supabase** (READ_ONLY, por SHA): los 14 documentos están.
  - 13 están en `PROVEEDOR_NO_SOPORTADO`.
  - 0563834757 está en `NORMALIZADA` / `PENDIENTE_CONCILIAR`. Es la única factura no conciliada de las 63.

## 2. Diseño del lector

`PROPUESTA`, a partir del diagnóstico de 0563834757 y de las 14 facturas.

### 2.1 Estructura del documento

- **Página 1, relación de albaranes:** cada fila tiene fecha, identificador, `Base S.R.*`, `Base Re.`, `Base No.` y
  `Total Bases`.
  - El signo negativo puede ir detrás (`30,39-`) o delante (`-1,48`, en la fila Totales).
  - Una fila puede tener bases en más de una clase (por ejemplo, 7078164: S.R. 20,39 + Re. 12,70).
  - Las filas no numéricas (`ABO/DEVO`, `APROAFA`) son movimientos.
- **Página 1, resumen:** `Totales`, `Desglose importes pedidos`, `Autoconsumo`, `Resumen Liquidaciones Comerciales` y
  `Resumen Servicios Operativos`, cada uno por clase.
- **Página 2:** `Base imponible`, `IVA`, `Rec. Equiv.`, `Gastos giro` y `Totales`, por clase S.R., Re., No. y Ex.
  Después vienen `Total Factura` y el resumen de vencimientos, que puede tener varios (0563842626 tiene 2).

### 2.2 Cálculo por línea

Total por línea = `round2(Σ_clase base × (1 + IVA + RE))`, con un solo redondeo por línea:

| Clase | IVA | RE | Factor | Evidencia |
|---|---|---|---|---|
| S.R. (superreducido; las exentas van sumadas aquí) | 4 % | 0,5 % | 1,045 | Página 2 de las 14 facturas |
| Re. (reducido) | 10 % | 1,4 % | 1,114 | Página 2 de las 14 facturas |
| No. (normal) | 21 % | **5,2 %** | 1,262 | Página 2: RE No. = (base No. − servicios) × 5,2 % |

**Defecto del código actual** (`CONFIRMADO POR CÓDIGO`): `src/facturas/hefame_economia.py` (`FISCALIDAD_HEFAME`)
tiene RE **1,2 %** para `BASE_NO`. Debe ser **5,2 %**: con 1,2 % ninguna factura con base No. cuadra. Es la
corrección del adaptador HEFAME pendiente.

### 2.3 Movimientos, con el signo del documento

Se aplica la misma fórmula por clase. El signo y el sentido salen del documento, nunca se infieren.

- **`ABO/DEVO`** (devoluciones): aparece en 12 de 14 facturas.
  - Normalmente es negativo, pero puede ser positivo: 3 facturas (+1,95, +3,65 y +1,06).
  - Puede mezclar signos entre clases (0563791043: S.R. +1,53, Re. −24,72 y No. −23,64).
  - Sentido: el del signo neto; si el neto es positivo, CARGO. Si el neto es 0, o si los signos se mezclan entre
    clases, el sentido es `null` (sin inferir); en ese caso lleva el importe con su signo por clase.
- **`APROAFA`:** positivo, pequeño (0,11–0,26 de base) y siempre en la base No. Aparece en 4 facturas.
  **Decisión de Pio (H2, 2026-11-18):** es la aportación a la Asociación para la Promoción de la Asistencia
  Farmacéutica en España y es un **CARGO**. El importe se toma del documento con su signo. **Decidido (H7):** si una fila
  `APROAFA` sale negativa, el lector falla cerrado en lugar de invertir el sentido.
- **`Resumen Liquidaciones Comerciales`:** negativo y en la base S.R. Aparece en 2 facturas (−0,96 y −1,17 con
  impuestos). **Decisión de Pio (H3, 2026-11-19):** son pequeños descuentos sobre especialidad (medicamento, IVA 4 %,
  base S.R.) y son un **ABONO**. El importe se toma del documento con su signo.
- **`Resumen Servicios Operativos`:** siempre en la base No., con **21 % de IVA y sin RE** (evidencia: el RE No. de la
  página 2 excluye esta base).
  - 110,00 de base (133,10 con IVA) en las facturas de fin de mes; 113,43 en la de junio.
  - Importes pequeños en otras dos (0,06 y 2,16).
- **`Autoconsumo`:** 0 en las 14. Se lee, y si no es 0 se aplica la fórmula por clase.

### 2.4 Cargo cooperativo no listado

`CONFIRMADO POR MEDICIÓN` en cuanto al importe. **Decisión de Pio (H1, 2026-11-18):** es el **cargo cooperativo
HEFAME**, **fijo cada mes**, de 80,00 € de base S.R. en la factura de fin de mes.

- En las **4 facturas de fin de mes** presentes (30.06, 31.07, 31.08 y 31.10), los `Totales` de la base S.R. superan en
  **80,00 exactos** a la suma de las filas de S.R. Ninguna fila lo lista, pero está incluido en
  `Desglose importes pedidos` y en la base imponible S.R. de la página 2.
- Lleva el IVA y el RE de S.R. (4 % + 0,5 % → **83,60**).
- No aparece en ninguna factura de los días 10 y 20.
- **Evidencia que debe guardar el lector:** la fila `Totales` y la columna S.R. de las filas (sus bbox), el desfase
  calculado y que el desfase es exclusivo de S.R.
- Ya existe `detectar_comision_hefame`: reconoce solo un desfase positivo y exclusivo de S.R., con
  `periodicidad: NO_DEMOSTRADA`.
  - **Decidido (H1):** nombre «cargo cooperativo HEFAME» y periodicidad mensual, en la factura de fin de mes, con la
    evidencia de las 4 facturas.
  - Si el desfase aparece en otra clase, es negativo o no es de fin de mes, el lector falla cerrado.
  - **Decidido (H6):** un desfase de S.R. distinto de 80,00 en una factura de fin de mes también
    falla cerrado. Si HEFAME cambia la cuota, se actualiza con una decisión de Pio.

### 2.5 Comprobación contra la página 2 (falla cerrado)

`PROPUESTA`. Antes de devolver nada, el lector exige:

1. **Coherencia de la página 1:**
   - cada fila cumple Σ bases = `Total Bases`;
   - `Totales` = `Desglose importes pedidos`;
   - el desfase con las filas solo puede ser el cargo de §2.4;
   - los servicios solo van en la base No.
2. **Página 2 frente a página 1, por clase:**
   - base = pedidos + autoconsumo + liquidaciones + servicios;
   - IVA = base × IVA;
   - RE = (base − servicios) × RE;
   - totales por clase = base + IVA + RE + gastos de giro;
   - `Base Ex.` y gastos de giro valen 0;
   - Σ totales = `Total Factura` = Σ vencimientos.
3. **Medición:** **ninguna factura falla por más de 0,01 en ningún componente.** Al céntimo exacto solo pasan 6 de
   14.
   - HEFAME calcula la página 2 con las líneas de producto, que no aparecen en el PDF.
   - En una factura (0563863435), la base de la página 2 difiere en 0,01 de los `Totales` de la página 1 (S.R. 115,48
     frente a 115,49).
   - Ni redondear una vez por fila ni redondear el IVA y el RE fila a fila reproduce la página 2 al céntimo.
   - **Decisión de Pio:** tolerancia de **0,01 por componente**, con la que pasan las 14, o control exacto, con el que
     fallarían cerradas 8 de 14. Cualquier desviación mayor que la tolerancia → falla cerrado.

## 3. Medición del cálculo

En local, sin persistir. `CONFIRMADO POR MEDICIÓN`.

Total reconstruido = Σ totales por línea + movimientos de fila + liquidaciones + servicios (× 1,21) + cargo S.R.
(× 1,045).

| Resultado | Facturas |
|---|---|
| Cuadran **al céntimo** con el `Total Factura` | **4 de 14** (0563796618, 0563801595, 0563847628, 0563863435) |
| Diferencia de ±0,01 | 6 |
| Diferencia de ±0,02 | 4 |
| Diferencia mayor que 0,02 | **0** |
| Página 2 exacta / con tolerancia de 0,01 | 6 / **14** |

Con el RE No. al 1,2 % del código actual, cada factura se desvía además en el 4 % de su base No. sujeta a RE (por
cálculo; por ejemplo, 1,29 en 0563834757, con 32,15 de base).

La diferencia de 0,01–0,02 es de redondeo: la factura redondea por producto y el lector por línea de albarán. Esa
diferencia es documental y queda dentro de la tolerancia R11 de la conciliación (suelo de 0,05).

## 4. Reglas de conciliación propias de HEFAME

Propuestas, medidas READ_ONLY contra `Supabase.albaranes` (81 filas numéricas). En Supabase, HEFAME es
`3.- HEFAME`, con 133 albaranes entre el 01.04 y el 13.11.

### 4.1 Numeración

`CONFIRMADO POR MEDICIÓN`:

- **Hasta septiembre:** albaranes de 10 dígitos que empiezan por `41` (67 filas). En Farmatic aparecen con el mismo
  número o con numeración interna `Q0xxxxx/2026` / `R0xxxxx/2026` (R15b).
- **Desde octubre:** documentos de entrega de **7 dígitos** (11 filas). En Farmatic se guardan **con ceros a la
  izquierda hasta 10** (`7070398` ↔ `0007070398`).
  - **Regla:** comparar sin ceros a la izquierda; solo cuando las dos partes sean numéricas.
- **9 dígitos que empiezan por `91`** (3 filas). **Decisión de Pio (H4, 2026-11-19):** son albaranes normales;
  Farmatic los registra con numeración interna `Q…`/`R…`, así que casan por numeración interna, importe y fecha,
  con candidato único (como R15b).
  - 912776450 (18.06) casa con `Q039867/2026` (31,06, mismo día, recepción 50749).
  - Los 2 de 0563863435 (20.10) eran formulación magistral sin entrar; Pio los registró el 18.11 con su número
    (914618399 a 67,15 frente a 67,01 del PDF, que Pio corrige, y 914621188 a 33,57).
- **Resultado del casamiento:**

| Casamiento | Filas | Detalle |
|---|---|---|
| Por número | 36 | Importe exacto en 27; ≤ 0,01 en 32 |
| Solo por importe ±0,02 a ±3 días | 24 | Sobre todo internos `Q0…` |
| Sin candidato | 21 | Repartidas en 10 facturas |

### 4.2 Fechas

`CONFIRMADO POR MEDICIÓN`:

- La fecha de Farmatic es igual o posterior a la del documento: entre 0 y 4 días en 35 de los 36 casados por número.
- **Hay un caso a 70 días**: es una coincidencia de número que habría que rechazar.
- **Regla propuesta:** ventana de 0 a +4 días (o ±3, como R15b). Fuera de la ventana no hay casamiento, aunque el
  número coincida.

### 4.3 Importe operativo

Se compara el total por línea de §2.2 con el PUC.

- **Propuesta de tolerancia por línea:** 0,01. Con ella casan 32 de 36. Los otros 4 son diferencias reales: 1,82
  frente a 2,02; 0,74 frente a 0,77; 126,25 frente a 104,54; 97,06 frente a 93,68.
- **Casamiento por importe** (internos y sin número): exige unicidad. En 0563801595, dos filas de 3,91 apuntan al
  mismo albarán → ambigüedad → no se casa (R15, uno a uno).

### 4.4 La ruta HEFAME en REGLAS_CRITICAS

Hoy dice «número exacto e importe operativo». **Propuesta:**

- número normalizado sin ceros a la izquierda;
- ventana de fechas;
- importe operativo de §2.2 con tolerancia por línea;
- internos `Q0`/`R0` por PUC a ±3 días con unicidad;
- R17 no aplica (ya lo dice la regla).

## 4b. Lector `hefame-local` 1.3.0 implementado en local (2026-11-27, FACTURAS-0 vía B)

`CONFIRMADO POR TEST` y `CONFIRMADO POR MEDICIÓN` (banco local del espejo).

- **Alcance:** sin migración, sin autoridad productiva (`habilitada=False`) y sin enchufar a la noche.
- **Decisiones aplicadas:** H1–H7, F0-4 (RE «No.» al 5,2 %) y F0-6 (página 2).
- **Código** (`src/facturas/motor_local/adaptadores/hefame.py`, versión 1.3.0):
  - **RE «No.» al 5,2 %**, en `hefame_economia.FISCALIDAD_HEFAME`.
  - **Numeración (§4.1):** albaranes de 10 dígitos, documentos de entrega de 7 dígitos y números `91…` de 9 dígitos.
    La 1.2.0 solo leía los de 10 y se saltaba filas desde octubre, de modo que el desfase de la página 1 parecía un
    cargo.
  - **Cargo cooperativo (H1/H6):**
    - solo existe con **80,00 exactos de base S.R. en una factura de fin de mes**;
    - cualquier otro desfase entre `Desglose importes pedidos` y las filas **para el lector**
      (`DESFASE_PEDIDOS_NO_AUTORIZADO_H6`);
    - se nombra `CARGO_COOPERATIVO_HEFAME`, con periodicidad `MENSUAL_FIN_DE_MES` y origen `DECISION_PIO_H1`.
  - **`APROAFA` negativo** para el lector (`APROAFA_NEGATIVO_H7`).
  - **`Resumen Liquidaciones Comerciales`** es un movimiento ABONO (H3). Si no es negativo y exclusivo de la base
    S.R., para el lector.
  - **ABO/DEVO:** el sentido sale del signo neto. Con signos mezclados entre clases, o con neto 0, el sentido queda
    `null`.
  - **Controles de la página 2 (§2.5 con F0-6)**, en `controles_pagina2`. Cualquier `FALLO` para el lector
    (`CONTROL_PAGINA2_HEFAME`).
    - **Con 0,01 por componente**, lo que el lector recalcula:
      - base = pedidos + autoconsumo + liquidaciones + servicios;
      - IVA = base × tipo;
      - RE = (base − servicios) × tipo.
    - **Exacto**, lo impreso:
      - Σ bases de cada fila = `Total Bases`;
      - total de cada clase = base + IVA + RE + gastos;
      - Σ totales = `Total Factura` = Σ vencimientos;
      - `Base Ex.` y gastos de giro = 0.
  - **Conciliación declarada:** la base imponible incluye también el autoconsumo y las liquidaciones.
- **Banco** (`C:\ControlFarmacias\estrategia_facturas\hefame\`, `SHA256SUMS.txt`):
  - **Cobertura:** los **16 documentos HEFAME** de PIO en `PROVEEDOR_NO_SOPORTADO`.
  - **Lectura:** las **16 se leen** y pasan los controles de la página 2.
  - **Cuadres por factura** (los tres, 16 de 16):
    - **C1, exacto:** bases + IVA + RE + gastos = `Total Factura`.
    - **C2, exacto:** vencimientos = total. Incluye 3 facturas con 2 vencimientos.
    - **C3:** albaranes + movimientos = total, con el total por línea de §2.2. La diferencia es de 0,02 como máximo,
      dentro de `mín(0,01 × filas; 0,50)` (F0-8).
  - **Literalidad 0.2.0:**
    - **12 de 16 `LITERALIDAD_OK`.**
    - **Las 4 de fin de mes** (0563801595, 0563820041, 0563855563 y 0563869860) fallan **solo** en los 6 valores
      del cargo cooperativo H1. Esos valores no están impresos: son un **derivado por decisión de Pio**, y la lista
      cerrada del verificador solo contiene R14.
    - **Resuelto con el verificador 0.2.2** (decisión de Pio, 2026-11-28): H1 está en la lista cerrada y se recalcula
      desde la fila «Desglose importes pedidos» de la página 1. **16 de 16 `LITERALIDAD_OK`** (DISENO de FACTURAS-0
      §0b). La columna «Literalidad» de la tabla es la de la 0.2.0.

  | Factura | Fecha | Total | Albaranes | Movim. | C1 | C2 | C3 (dif./tol.) | Literalidad |
  |---|---|---|---|---|---|---|---|---|
  | 0563791043 | 10.06 | 96,86 | 5 | 2 | OK | OK | −0,02 / 0,07 | OK |
  | 0563796618 | 20.06 | 127,12 | 5 | 2 | OK | OK | 0,00 / 0,07 | OK |
  | 0563801595 | 30.06 | 263,88 | 4 | 2 | OK | OK (2) | 0,00 / 0,06 | Fallo: cargo H1 (6) |
  | 0563807670 | 10.07 | 230,86 | 6 | 2 | OK | OK | −0,02 / 0,08 | OK |
  | 0563812683 | 20.07 | 142,52 | 5 | 4 | OK | OK | 0,02 / 0,09 | OK |
  | 0563820041 | 31.07 | 677,99 | 12 | 4 | OK | OK | 0,01 / 0,16 | Fallo: cargo H1 (6) |
  | 0563825633 | 10.08 | 184,84 | 6 | 2 | OK | OK (2) | 0,01 / 0,08 | OK |
  | 0563830485 | 20.08 | 19,41 | 4 | 2 | OK | OK | −0,01 / 0,06 | OK |
  | 0563842626 | 10.09 | 64,56 | 7 | 3 | OK | OK (2) | 0,01 / 0,10 | OK |
  | 0563847628 | 20.09 | 138,81 | 5 | 1 | OK | OK | 0,00 / 0,06 | OK |
  | 0563855563 | 30.09 | 369,54 | 8 | 3 | OK | OK | 0,01 / 0,11 | Fallo: cargo H1 (6) |
  | 0563857003 | 10.10 | 45,80 | 3 | 2 | OK | OK | 0,01 / 0,05 | OK |
  | 0563863435 | 20.10 | 345,83 | 6 | 3 | OK | OK | 0,00 / 0,09 | OK |
  | 0563869860 | 31.10 | 255,89 | 4 | 2 | OK | OK | 0,01 / 0,06 | Fallo: cargo H1 (6) |
  | 0563878342 | 10.11 | 14,57 | 2 | 2 | OK | OK | 0,01 / 0,04 | OK |
  | 0563883869 | 20.11 | 152,95 | 5 | 2 | OK | OK | 0,00 / 0,07 | OK |

- **Simulación local de 0563834757** (31.08, 313,29), con las reglas F0-7 y los albaranes de una lectura
  READ_ONLY del 27/11 a las 19:27:
  - **8 de 9 líneas casan por número sin ceros**, en la ventana de 0 a +4 días, con |PUC − importe operativo| ≤
    0,01. La diferencia neta de las casadas es 0,00.
  - **La línea 4127750839** (25,01, del 31.08) **no casa:**
    - en Farmatic existe el albarán **4127750839 con el mismo importe exacto (25,01), fechado el 09.11.2026**, 70
      días después;
    - la ventana de 0 a +4 lo rechaza;
    - es el «caso a 70 días» de §4.2. Con el importe idéntico, lo más probable es **un alta tardía en Farmatic**
      del mismo albarán, no una coincidencia.
  - **Resultado de la simulación: NO CONCILIARÍA**, porque queda 1 línea sin casar.
  - **Decisión de Pio pendiente:**
    - (a) corregir en Farmatic la fecha del albarán 4127750839;
    - (b) o admitir, solo con revisión, el mismo número con el importe exacto fuera de la ventana;
    - (c) o dejar la factura en `DIFERENCIA`.
  - Los movimientos sin albarán (ABO/DEVO, APROAFA, servicios y cargo H1) no entran en esta simulación de líneas.

## 5. Qué falta para la autoridad productiva

1. **Decisiones de Pio:**
   - **tomadas (2026-11-18, §0):** el cargo de 80,00 es el cargo cooperativo HEFAME, fijo cada mes (H1);
     `APROAFA` es un CARGO (H2); un desfase distinto de 80,00 (H6) y un `APROAFA` negativo (H7) paran el lector;
   - **tomadas (2026-11-19, §0):** las liquidaciones comerciales son un ABONO (H3); los números `91…` son albaranes
     normales que casan por numeración interna, importe y fecha con candidato único (H4); la factura del 30.09 está
     importada (H5);
   - **pendientes:**
     - tolerancia del control de la página 2 (§2.5);
     - reglas de §4 (normalización, ventana y tolerancia por línea).
2. **Código** (hito propio, con su suite). La farmacia se demuestra por el destinatario impreso (código de cliente,
   NIF y dirección del bloque de cliente), nunca por la carpeta del espejo ni por el nombre del fichero (S3/S5):
   - corrección del RE No. a 5,2 % en `hefame_economia.py`;
   - lector `hefame-local` 1.3.0 con §2.3–§2.5 y evidencia por celda;
   - conciliación con §4;
   - tests con las 15 facturas reales y sus totales esperados.
3. **Banco** de las 15 facturas con la versión nueva (como el banco Alliance 1.3.0 → 1.3.1), con cada diferencia
   explicada.
4. **Autoridad:**
   - entrada en `AUTORIDAD_COMPOSITOR_MANUAL` (hoy solo Alliance) y en `LAYOUTS_CON_PUENTE_CERTIFICADO`, si hace
     falta;
   - después, en la automatización (D1), con decisión expresa de Pio;
   - mientras tanto, la autoridad productiva de `hefame-local` sigue desactivada.
5. **Producción**, con confirmación por paso:
   - plan 2BJ de los 13 documentos HEFAME en `PROVEEDOR_NO_SOPORTADO` (hoy no son reclamables: haría falta
     reabrirlos con su decisión);
   - R12 o reproceso de 0563834757;
   - conciliación con el plan 2BP.
   - Las 21 filas sin candidato acabarán en `DIFERENCIA` hasta que Farmatic tenga esos albaranes: habrá que
     revisarlas factura a factura.
