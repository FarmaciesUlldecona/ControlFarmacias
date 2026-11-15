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

## 1. Inventario del espejo

`CONFIRMADO POR MEDICIÓN`:

- **Identificación por contenido:** razón social `HDAD.FMCTCA.MEDIT.,S.C.L.` y CIF `F30004444` en el texto, nunca por
  el nombre del fichero (S5). El espejo es `C:\GoogleDrive\FACTURES PIO`: 641 PDF, 618 distintos por SHA.
- **14 facturas HEFAME distintas**, todas con el formato conocido. Tienen las 7 señales del reconocedor de
  `hefame-local`: razón social, CIF, relación de albaranes, tabla de bases, desglose total factura, vencimientos y
  paginación interna. Todas tienen 2 páginas.
- **Periodo:** del 10.06.2026 al 31.10.2026, con una factura por decena (los días 10, 20 y fin de mes).
  - **Falta la del 30.09.2026:** hay 15 decenas y solo 14 facturas. `PENDIENTE` (Pio): comprobar si existe.
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
- **`APROAFA`:** positivo, pequeño (0,11–0,26 de base) y siempre en la base No. Aparece en 4 facturas. Su naturaleza
  está `PENDIENTE` (Pio).
- **`Resumen Liquidaciones Comerciales`:** negativo y en la base S.R. Aparece en 2 facturas (−0,96 y −1,17 con
  impuestos).
- **`Resumen Servicios Operativos`:** siempre en la base No., con **21 % de IVA y sin RE** (evidencia: el RE No. de la
  página 2 excluye esta base).
  - 110,00 de base (133,10 con IVA) en las facturas de fin de mes; 113,43 en la de junio.
  - Importes pequeños en otras dos (0,06 y 2,16).
- **`Autoconsumo`:** 0 en las 14. Se lee, y si no es 0 se aplica la fórmula por clase.

### 2.4 Cargo cooperativo no listado

`CONFIRMADO POR MEDICIÓN` en cuanto al importe; su naturaleza está `PENDIENTE` (Pio).

- En las **4 facturas de fin de mes** presentes (30.06, 31.07, 31.08 y 31.10), los `Totales` de la base S.R. superan en
  **80,00 exactos** a la suma de las filas de S.R. Ninguna fila lo lista, pero está incluido en
  `Desglose importes pedidos` y en la base imponible S.R. de la página 2.
- Lleva el IVA y el RE de S.R. (4 % + 0,5 % → **83,60**).
- No aparece en ninguna factura de los días 10 y 20.
- **Evidencia que debe guardar el lector:** la fila `Totales` y la columna S.R. de las filas (sus bbox), el desfase
  calculado y que el desfase es exclusivo de S.R.
- Ya existe `detectar_comision_hefame`: reconoce solo un desfase positivo y exclusivo de S.R., con
  `periodicidad: NO_DEMOSTRADA`.
  - **Propuesta:** periodicidad «mensual, en la factura de fin de mes», con la evidencia de las 4 facturas.
  - **Propuesta:** el nombre definitivo del concepto (cuota o cargo cooperativo), que decide Pio.
  - Si el desfase aparece en otra clase, es negativo o no es de fin de mes, el lector falla cerrado.

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
- **9 dígitos que empiezan por `91`** (3 filas). Uno casa por importe con un interno `Q0…`. Su naturaleza está
  `PENDIENTE`.
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

## 5. Qué falta para la autoridad productiva

1. **Decisiones de Pio:**
   - tolerancia del control de la página 2 (§2.5);
   - naturaleza y nombre del cargo de 80,00 y su periodicidad (§2.4);
   - naturaleza de `APROAFA`, de las liquidaciones comerciales y de los números `91…`;
   - reglas de §4 (normalización, ventana y tolerancia por línea);
   - qué hacer con la factura del 30.09 que falta.
2. **Código** (hito propio, con su suite). La farmacia se demuestra por el destinatario impreso (código de cliente,
   NIF y dirección del bloque de cliente), nunca por la carpeta del espejo ni por el nombre del fichero (S3/S5):
   - corrección del RE No. a 5,2 % en `hefame_economia.py`;
   - lector `hefame-local` 1.3.0 con §2.3–§2.5 y evidencia por celda;
   - conciliación con §4;
   - tests con las 14 facturas reales y sus totales esperados.
3. **Banco** de las 14 facturas con la versión nueva (como el banco Alliance 1.3.0 → 1.3.1), con cada diferencia
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
