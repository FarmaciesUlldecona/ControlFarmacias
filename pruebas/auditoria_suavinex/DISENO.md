# Suavinex: ficha del proveedor y lector `suavinex-local` (FACTURAS-0, fábrica de lectores)

Encargo de Pio del 2026-11-27. **Sin migración, sin autoridad productiva y sin enchufar a la noche.**

**Desde el 2026-11-28 (decisión de Pio, §3b):** `suavinex-local` 1.1.0 está **registrado en sombra** en
`REGISTRO_ADAPTADORES_LOCALES`, en lugar de `suavinex-historico-local`, que se retira con su texto fijo de datos
personales. Sigue sin autoridad productiva y la completitud falla cerrado (`COBERTURA_PARCIAL_FAIL_CLOSED`).

Evidencias fuera del repositorio, en `C:\ControlFarmacias\estrategia_facturas\suavinex\` (`SHA256SUMS.txt`):
`documentos_espejo.json`, `volcado_lineas_clave.txt`, `verdad_conocida.json`, `banco_suavinex.json` y `scripts\`.

Etiquetas: `CONFIRMADO POR MEDICIÓN` (espejo local), `CONFIRMADO POR TEST` y `PENDIENTE`.

## 1. Banco del espejo

`CONFIRMADO POR MEDICIÓN`:

- **Identificación por contenido:** CIF `ESB03074093` y razón social `Suavinex Group, S.L.` en el texto, nunca por
  el nombre del fichero.
- **19 PDF distintos** por SHA, con **26 documentos**: 19 facturas y 7 abonos (facturas rectificativas).
- **Todos son de texto nativo** y tienen un solo tramo fiscal: IVA 21 % + RE 5,2 %.
- **Variantes:**
  - factura de 1, 2 o 3 páginas, con un albarán («Pedido: … Albarán: …») y un vencimiento;
  - abono («FACTURA RECTIFICATIVA», «Abono Nº»), sin vencimiento y con «Vía de Pago: Abono a compensar»:
    - con 2 albaranes, 1 albarán o ninguno;
    - con importes negativos con el signo delante;
  - **un PDF de 11 páginas con 8 documentos** (6 facturas y 2 abonos), separados por número y por «Página i/n»;
  - **la misma factura en dos PDF distintos:** 0702638508 aparece en dos SHA distintos;
  - «Infor.Pto.Verde» es informativo y no entra en el total;
  - las líneas de producto llevan un código de 5 o 6 dígitos y terminan con su importe.
- **Lo que no imprime:** el importe de cada albarán. El lector da la suma de sus líneas como dato derivado
  (`importe_base_suma_lineas`), y no como valor documentado.

## 2. Verdad conocida

`verdad_conocida.json`, escrita a mano el 27/11 a partir del texto de cada PDF y sin usar el lector. Para cada
documento recoge:

- tipo, número y fecha;
- base, cuota y total;
- punto verde;
- vencimientos (fecha e importe);
- números de albarán;
- páginas, en el PDF multidocumento.

## 3. Lector `suavinex-local` 1.0.0

Código en `src/facturas/motor_local/adaptadores/suavinex.py`, sobre `AdaptadorBase`.

- **Reconocimiento** con 7 señales: razón social, CIF, número de documento, cuadro fiscal, «Total Factura:»,
  paginación y texto nativo.
- **Segmentación:** por el número impreso y «Página i/n» consecutiva. Una paginación incoherente para el lector.
- **Campos documentados:**
  - tipo, número y fecha;
  - CIF y razón social;
  - números de albarán;
  - importe de cada línea;
  - tramo fiscal: base, tipos y cuota;
  - totales: bruto, neto, impuestos, total y punto verde;
  - vencimientos.
- **Controles** (fallo cerrado, `CONTROL_SUAVINEX`):
  - Σ líneas = importe bruto, con el redondeo documental F0-8, `mín(0,01 × filas; 0,50)`. Suavinex calcula el bruto
    con el precio neto de 4 decimales.
  - bruto = neto = Σ bases.
  - cuota = base × (IVA + RE), con 0,01.
  - Σ cuotas = impuestos.
  - neto + impuestos = total.
  - **Factura:** Σ vencimientos = total.
  - **Abono:** sin vencimientos, total negativo y «Abono a compensar».

## 3b. `suavinex-local` 1.1.0 y registro en sombra (DECISIÓN DE PIO, 2026-11-28)

- **«Su Referencia»:** cada albarán recoge la «Su Referencia: O-…» impresa en su fila «Pedido», tras el número de
  albarán (`su_referencia`, campo documentado con su evidencia, regla `REFERENCIA_TRAS_SU_REFERENCIA`).
  - Sin la etiqueta, `None`.
  - Con la etiqueta y un valor que no es `O-` + dígitos, sin «Su», o con dos etiquetas: falla cerrado
    (`CONTROL_SUAVINEX:SU_REFERENCIA_ILEGIBLE`).
  - Los abonos sin albarán imprimen «Su referencia» en la fila «Pedido» sin albarán (a veces un número de 12
    dígitos): no se recogen, porque no hay albarán al que asignarla.
- **Registro:** `suavinex-local` sustituye a `suavinex-historico-local` en `REGISTRO_ADAPTADORES_LOCALES`.
  - El histórico se retira del código (`historicos_gold1.py`), con su texto fijo del destinatario.
  - `completitud_documental`: `suavinex-local` es `COBERTURA_PARCIAL_FAIL_CLOSED`; el motor nunca marca un documento
    Suavinex como completo demostrado.
  - El motor elige `suavinex-local` en los 19 PDF del banco y en el PDF de pruebas del repositorio.
- **Ajustes para la sombra:**
  - la factura lleva `otros: []`, la familia que cuenta el puente de sombra;
  - el comparador de sombra (`motor_local/comparador.py`) acepta las filas de albarán de los lectores de la fábrica,
    que son campos documentados y no `AlbaranLocal`. Sin esto, la sombra registraba `SHADOW_LOCAL_ERROR`. Solo
    observa: la salida local nunca se aplica.
- **Banco con la 1.1.0** (`banco_suavinex_110.json`): verdad 26/26 y cuadres 26/26, como en la 1.0.0. Las 22
  referencias son `LITERAL`. Literalidad 24/26, con los mismos 2 documentos y las mismas 3 filas partidas por pdfium.
- **Medido:** la «Su Referencia» es el **pedido de la farmacia**, no el albarán. `O-0570810` aparece en 3 facturas y
  `O-0545126` en otras 3. Una factura con 2 albaranes los lleva con la misma referencia. En Farmatic, `o-0540906`
  es otra entrega (25.04, 2.108,40) del pedido de 0702629937, cuyo albarán es `Q039505/2026` (169,61). De ahí la
  lectura de la regla en §5.

## 4. Banco del lector (2026-11-27)

`CONFIRMADO POR MEDICIÓN`, con el verificador de literalidad 0.2.1:

| Resultado | Documentos |
|---|---|
| Leídos, sin fallo cerrado | 26 de 26 |
| Iguales a la verdad conocida en todos sus campos | 26 de 26 |
| C1: base + cuota = total | 26 de 26 |
| C2: vencimientos = total (factura) o sin vencimientos (abono) | 26 de 26 |
| C3: Σ líneas = bruto, con diferencias de −0,04 a +0,01 dentro de F0-8, y bruto + impuestos = total | 26 de 26 |
| Literalidad 0.2.1 `LITERALIDAD_OK` | **24 de 26** |

**Los 2 fallos de literalidad** son 3 líneas de producto en 2 facturas, con una sola causa:

- Las líneas son las de «S TERMÓMETRO BAÑO PRINTS» e «INFRARROJOS».
- El motor del lector (pdfium) **parte la fila**: deja «TERMÓMETRO BAÑO» en otra línea, de modo que la fila que guarda
  la evidencia es «S PRINTS 6 4,44 …».
- `pypdf` tiene la fila entera, y el importe de la línea está, literal, en su fila.
- El verificador no se relaja para esto: el fallo queda explicado.
- Arreglarlo es cosa de la agrupación de líneas del motor, compartida con otros lectores, y lo decide Pio.

En la primera pasada fallaron además estas causas, todas corregidas:

- **Código de artículo de 5 dígitos** (`13544`): el lector perdía esa línea.
- **«Abono a compensar»** partido en dos líneas.
- **Redondeo por línea** de Suavinex.
- **En el verificador:**
  - filas con ceros repetidos, que necesitaban búsqueda con vuelta atrás;
  - filas que empiezan a media frase;
  - valores sin desplazamiento en la matriz de texto de pypdf con una matriz de página (`cm`) escalada.

  Son las mejoras de la 0.2.1, en `pruebas/auditoria_facturas0/DISENO.md` §0b.

## 5. Conciliación con Farmatic

### 5.1 Reglas (DECISIÓN DE PIO, 2026-11-28)

- **Primero por número:** la «Su Referencia: O-…» normalizada como número, a ±15 días de la factura (el albarán de
  Suavinex no trae fecha).
  - Normalización, igual en los dos lados: mayúsculas, sin `O`, sin guion y sin ceros a la izquierda. Farmatic la
    guarda como `O529779`, `O-0530657`, `0537252` u `o-0540906`.
  - El número de albarán de 8 dígitos sigue casando por la regla general (`EXACTA`, ±15 días).
- **Sin referencia que case:** por importe, con candidato único y fecha de Farmatic entre −3 y +10 días respecto a la
  factura.
- **Tolerancias:** 0,05 por línea y R11 en la factura.
- **Lectura aplicada en la simulación**, porque la referencia es el pedido (§3b): la referencia casa solo con importe
  dentro de 0,05 y candidato único; si no da ninguno, se sigue por importe, y nunca produce `DIFERENCIA`. El número
  de albarán sí identifica el albarán: con candidato único fuera de 0,05, `DIFERENCIA`. **Confirmar con Pio.**
- `NO IMPLEMENTADO` en la conciliación productiva (`runtime_supabase/conciliacion.py`): la ruta propia de Suavinex
  llegará con su hito, como F0-7 de HEFAME.

### 5.2 Simulación READ_ONLY (2026-11-28)

Captura READ_ONLY de los albaranes de Farmatic en Supabase a las 08:47: 20 de Suavinex, desde el 16.03.2026. Sin
reservas ni facturas Suavinex persistidas. Importe de cada línea = Σ líneas × (1 + (IVA + RE) / 100), con el tramo
único de la factura. Evidencias en `C:\ControlFarmacias\estrategia_facturas\simulaciones_2811b\`.

| Resultado | Documentos |
|---|---|
| **CONCILIARÍA** | **11 facturas** (12 filas: 0702638508 está en 2 PDF) |
| NO CONCILIARÍA | 3: 0702629217, 0702654770 y el abono 0722610593 |
| Anteriores al 16.03 (fuera de Supabase) | 7 |
| Abonos sin albaranes | 4 |

- Casan:
  - por **referencia** 3: 0702614551 (`O529779`), 0702614552 (`O-0530657`) y 0702621102 (`0537252`, +5 días);
  - por **número de albarán** 2: 0702642244 y 0702657563;
  - por **importe** 6, con internos `Q…`: 0702629937, 0702634096, 0702638508 (+7 días), 0702639520, 0702662583 y
    0702665632 (+7 días).
- No casan:
  - 0702629217: el único candidato, `Q039504/2026`, difiere en −4,14;
  - 0702654770: `Q040670/2026` a +6 días difiere en 0,06, por encima de 0,05;
  - 0722610593 (abono, −147,74): sin candidato.
- Sin conflictos entre facturas: ningún albarán lo casarían dos facturas.

## 6. Pendientes de Pio

1. Confirmar la lectura de la regla de referencia de §5.1.
2. La certificación y la autoridad, que siguen el criterio de la fábrica: decisión de Pio y versión exacta.
3. La ruta de conciliación de Suavinex en el código (hito propio).
