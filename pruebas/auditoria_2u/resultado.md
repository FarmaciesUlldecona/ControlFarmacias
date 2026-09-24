# Hito 2U - Auditoria conceptual de cuatro codigos Alliance

Estado final: **CONCEPTOS_4_ALBARANES_DETERMINADOS**.

Fuente: factura `08009277`, paginas PDF 5-9. El analisis fue local y en
memoria; produccion no se modifico.

## Evidencia individual

### 08P10588

- Pagina PDF 6, pagina interna 02/05, tabla derecha `ABONOS`, fila 1.
- Columnas: FECHA, TIPO DE PEDIDO, NUMERO ALBARAN, TOTAL BASE, TOTAL ALBARAN.
- Literal: `30-07-2026 CARGO/ABONO DIRECT 08P10588 788,00- 823,46-`.
- Relacion exacta y unica con pagina 5: `ABONOS CLUBS 788,00- 31,52- 3,94- 823,46-`.
- Concepto: ABONO (`ABONOS CLUBS`). Sentido: ABONO.
- Base -788,00; IVA -31,52; RE -3,94; total -823,46.
- No debe buscarse como albaran normal. Contribucion: -823,46.

### 08C61794

- Pagina PDF 6, pagina interna 02/05, tabla derecha `ABONOS`, fila 2.
- Literal: `31-07-2026 ABONOS AGRUPADOS 08C61794 103,34- 122,27-`.
- Concepto: ABONO AGRUPADO. Sentido: ABONO.
- Base -103,34; IVA individual null; RE individual null; total -122,27.
- No existe movimiento-resumen individual 1:1. Su fiscalidad esta agregada en
  los totales de compras, sin desglose individual demostrable.
- No debe buscarse como albaran normal. Contribucion: -122,27.

### 08P10623

- Pagina PDF 6, pagina interna 02/05, tabla derecha `ABONOS`, fila 4.
- Literal: `31-07-2026 CARGO/ABONO DIRECT 08P10623 2.310,23- 2.414,19-`.
- Relacion exacta y unica con pagina 5:
  `RAPPEL GenerAH 2.310,23- 92,41- 11,55- 2.414,19-`.
- Concepto: AJUSTE comercial (rappel) materializado como ABONO.
- Sentido: ABONO.
- Base -2.310,23; IVA -92,41; RE -11,55; total -2.414,19.
- No debe buscarse como albaran normal. Contribucion: -2.414,19.

### 08Z34777

- Pagina PDF 9, pagina interna 05/05, tabla izquierda `CARGOS`, ultima fila.
- Literal: `31-07-2026 CARGO VENTA DIRECT 08Z34777 158,30 191,54`.
- Relacion exacta y unica con pagina 5, bloque `GASTOS`:
  `SERV.PLATAF.360 158,30 33,24 191,54`.
- Concepto: SERVICIO de plataforma. Sentido: CARGO.
- Base 158,30; IVA 33,24; RE null; total 191,54.
- No debe buscarse como albaran normal. Contribucion: +191,54.

## Recalculo en memoria

- Cargos de mercancia (`NORMAL ACUSTICO` y `NETOS PLUS`): +13.635,97.
- Abonos agrupados (`08C61794` y `08C61795`): -537,03.
- Ajustes/abonos directos (`08P10588` y `08P10623`): -3.237,65.
- Servicio plataforma (`08Z34777`): +191,54.
- Movimientos independientes: `CONDIC. COMERCIAL` +27,25 y
  `SERVICIO BASICO` +31,46; total +58,71.
- Suma documental: 10.111,54 frente a total impreso 10.111,55; diferencia
  documental +0,01.

Los cuatro auditados suman -3.168,38. La conciliacion productiva actual tenia
diferencia -3.168,42 porque los cuatro estaban aplicados a cero y los matches
operativos restantes acumulan una variacion neta de +0,05 respecto de sus
literales documentales. Incorporarlos conceptualmente en memoria produce
importe explicado 10.111,59 y diferencia restante -0,04, dentro de 0,05.

Existe duplicidad documental 1:1 entre fila y resumen para `08P10588`,
`08P10623` y `08Z34777`. Se detecto y se conto una sola vez. Ninguno de los
cuatro forma parte de los dos movimientos independientes.
