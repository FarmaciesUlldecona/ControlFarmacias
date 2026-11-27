# Suavinex: ficha del proveedor y lector `suavinex-local` 1.0.0 (FACTURAS-0, fábrica de lectores)

Encargo de Pio del 2026-11-27. **Sin migración, sin autoridad productiva y sin enchufar a la noche.** El lector
**no está registrado** en `REGISTRO_ADAPTADORES_LOCALES`: registrarlo requiere el OK de Pio, y hoy convive con
`suavinex-historico-local` en sombra, así que se usa llamando a `extraer_facturas`.

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

## 5. Simulación de la conciliación con Farmatic: PENDIENTE

No hecha el 27/11: el encargo llegó a las 20:00, dentro de la franja en la que no se trabaja en producción
(20:00–23:15). La lectura READ_ONLY de los albaranes de Suavinex en Supabase queda para antes de las 20:00 de otro
día.

- Casamiento propuesto: número de albarán de 8 dígitos igual, e importe operativo = Σ líneas × (1 + 0,21 + 0,052).
- Que Suavinex use ese importe es **PENDIENTE** de comprobar en Farmatic.

## 6. Pendientes de Pio

1. Registrar `suavinex-local` en `REGISTRO_ADAPTADORES_LOCALES` y decidir qué hacer con `suavinex-historico-local`.
2. La simulación de la conciliación (§5).
3. La certificación y la autoridad, que siguen el criterio de la fábrica: decisión de Pio y versión exacta.
