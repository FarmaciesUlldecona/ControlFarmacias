# Fixtures H3a: casos

Todos los datos son **ficticios**: farmacia PIO, fechas de octubre y noviembre de 2026, `estado_pago = SIN_PAGAR`.
Los nombres de proveedor son reales del sector, pero los números, importes, NIF y fechas son inventados.

## Identificadores

- Factura `Fnn` → `f0000000-0000-4000-8000-0000000000nn`
- Documento `Dnn` → `d0000000-0000-4000-8000-0000000000nn`

Abreviaturas de vistas (`v_web_*`):

| Abreviatura | Vista |
|---|---|
| ini | inicio_resumen |
| doc | documentos_estado |
| det | factura_detalle |
| lin | conciliacion_lineas |
| inc | incidencias |
| his | historial |
| ven | vencimientos |
| cf | cashflow_semanal |
| prov | proveedores_estado |

## Facturas

| Id | Documento | Proveedor | Número | Total € | Normalización | Conciliación | Revisión Pío |
|---|---|---|---|---|---|---|---|
| F01 | D01 | ALLIANCEHEALTHCARECENCORA | AL-26-100231 | 152,37 | NORMALIZADA | CONCILIADA | VALIDADA_PIO |
| F02 | D02 | ALLIANCEHEALTHCARECENCORA | AL-26-100577 | 472,22 | NORMALIZADA | CONCILIADA | NO_REQUERIDA |
| F03 | D03 | COFARES | CF-2026-55810 | 375,15 | NORMALIZADA | PENDIENTE_CONCILIAR | NO_REQUERIDA |
| F04 | D03 | COFARES | CF-2026-55811 | 568,05 | NORMALIZADA | CONCILIADA | VALIDADA_PIO |
| F05 | D04 | HEFAME | HF-0563-889120 | 288,00 | NORMALIZADA | REVISION_CONCILIACION | PENDIENTE_REVISION_PIO |
| F06 | D05 | FEDEFARMA | FD-26/04471 | **null** | REQUIERE_REVISION | PENDIENTE_CONCILIAR | PENDIENTE_REVISION_PIO |
| F07 | D06 | COFARES | CF-AB-2026-0912 (ABONO) | −45,30 | NORMALIZADA | PENDIENTE_CONCILIAR | NO_REQUERIDA |
| F08 | D07 | ALLIANCEHEALTHCARECENCORA | AL-26-100231 | 152,37 | NORMALIZADA | PENDIENTE_CONCILIAR | PENDIENTE_REVISION_PIO |

## Casos obligatorios

| Caso | Id | Detalle | Vistas |
|---|---|---|---|
| Conciliada exacta | F01, F04 | Diferencia 0,00; tolerancia 0,05 | det, lin, his, ini, prov |
| Conciliada con diferencia dentro de R11 | F02 | 8 albaranes casados → tolerancia R11 0,08; diferencia 0,07 (> suelo 0,05) | det, lin, ini, prov |
| Diferencia fuera de tolerancia | F03 | Resultado DIFERENCIA 41,90; intentos_fallo 1, clase DIFERENCIA, próximo reintento | det, lin, ini |
| REVISION_CONCILIACION | F05 | 4 intentos agotados; diferencia 23,45; líneas EXACTO_ECONOMICO y una AMBIGUO | det, lin, ini, prov |
| REQUIERE_REVISION (normalización) | F06 | Total null; incidencia VALOR_SIN_EVIDENCIA bloqueante | det, inc, ini, prov, ven |
| PENDIENTE_REVISION_PIO | F05, F06, F08 | — | det, ven, ini, prov |
| VALIDADA_PIO | F01, F04 | Evento FACTURA_VALIDADA_PIO | det, his, ven, ini |
| Multifactura con varios albaranes | D03 → F03 (págs. 1-3) + F04 (págs. 4-5) | `cantidad_documentos_detectados` 2; evento INVENTARIO_MULTIFACTURA | doc, det, lin, his |
| 3 vencimientos, uno con importe null (R14) | F04 | 30/10 400,00 · 15/11 150,00 · 30/11 **null**; incidencia IMPORTE_VENCIMIENTO_NO_DOCUMENTADO | ven, cf, inc |
| Abono | F07 | `tipo_documento` ABONO; total y vencimiento −45,30 (signo impreso); línea con sentido ABONO | det, lin, ven, cf (`importe_abonos_conocido`) |
| Movimiento con sentido null | F07 | Línea MOVIMIENTO_NO_FARMATIC NO_EVALUABLE (`importe_aplicado` null) → conciliación NO_EVALUABLE; incidencia SENTIDO_NO_DOCUMENTADO | lin, det, inc |
| Cargo o servicio sin albarán | F04 | MOVIMIENTO_NO_FARMATIC «SERVICIO INTEGRAL DE DISTRIBUCION» 12,10 | lin |
| Albarán no localizado | F03 (77003), F05 (4471204) | `tipo_relacion` SIN_COINCIDENCIA; `estado_matching` SIN_COINCIDENCIA / AMBIGUO | lin |
| Posible duplicado | F01 + F08 | Mismo número, fecha y total en PDF distintos; incidencia POSIBLE_DUPLICADO en ambas | inc, det |
| Uso de Luna con coste | F06 | `uso_luna` true, `coste_luna` 0,0184, 5321 tokens, `luna_campos` | det |
| PDF PROVEEDOR_NO_SOPORTADO | D08 | Sin facturas; clase NO_SOPORTADO | doc, his, ini (`documentos_sin_leer`) |
| PDF ERROR | D09 | 2 fallos TRANSITORIO; próximo reintento; incidencia de documento | doc, inc, his, ini (`documentos_sin_leer`) |
| PDF PENDIENTE sin procesar | D10 | Sin páginas ni facturas | doc, ini (`pendientes_procesar`) |
| `estado_pago` SIN_PAGAR | Todas | — | det, ven |

## H3b: DTO del contrato

Los DTO de `dto/*.json` los genera `scripts/gen_fixtures.mjs` pasando estas filas (H3a + casos H3b) por los
constructores de `web/app/server/contrato.ts` (los mismos del modo REAL). `scripts/check_fixtures.mjs` los valida.
`generado_at` fijo: 2026-11-02T08:00:00+00:00.

| Caso H3b | Datos | DTO |
|---|---|---|
| Albarán facturado no en Farmatic | IdContador 900102 (08X10002), reservado por F01; último evento `presencia` = AUSENTE (AUSENTE_EN_FARMATIC) | inicio, bandeja (`alertas`) |
| Duplicado en Farmatic (H3d, regla B validada por Pío: `VALIDADA`) | Cumple: 08C66676 (900301, `0002`) y 08C66676A (900302, `2`), 57,40 € los dos → alerta. No cumple: 08C70015 (900311) y 08C70015A (900312), 61,20 € y 64,85 € → sin alerta | inicio y bandeja (`alertas`); no en contadores |
| Documento con defecto (H3c, 1A) | D14 en `REVISION` (FACTURA_INCOMPLETA); con D09 (`ERROR`) → "Documentos con defecto" = 2. Los 4 `PROVEEDOR_NO_SOPORTADO` → "Sin automatizar" = 4 | inicio |
| Corrección aprobada aplicada | Aprobación 1, 900150, `numero_albaran` 08X10050 → 08X10050A (verde) | inicio, bandeja (`alertas`) |
| Corrección aprobada pendiente | Aprobación 2, 900160, `id_proveedor` 0004 → 0001, sin aplicar (azul) | inicio, bandeja (`alertas`) |
| Varios PROVEEDOR_NO_SOPORTADO | D08 (LAB_DEMO, H3a), D11 (BEIERSDORF ficticio), D12 (proveedor sin identificar), D13 (LAB_DEMO) | inicio, facturas (`documentos_sin_factura`), proveedores (`mapa_documentos`) |

Diferencias con los contadores H3a (por diseño): `incidencias.abiertas`/`bloqueantes` cuentan también las de
documento (D09); `documentos_sin_leer` = 5 por los PDF nuevos. Detalle: `impuestos` y `ajustes` vacíos (H3a no los
tenía); albaranes extraídos y movimientos derivados de las líneas de conciliación.

## Otros datos

- `v_web_proveedores_estado`: incluye LAB_DEMO (ficticio, sin extractor ni facturas), que corresponde al PDF D08.
- `v_web_configuracion`: interruptores apagados, solo PIO y parámetros R11 0,05 / 0,01 / 0,50.
- Hueco: los movimientos comerciales no tienen vista propia. Solo aparecen como líneas de conciliación, y un movimiento sin conciliación no se vería.

## H4b: proveedores por CIF e incidencias INFO

Casos añadidos en `scripts/gen_fixtures.mjs` sobre las filas H3a (los `v_web_*.json` no cambian). Todo ficticio.

| Caso H4b | Datos | DTO |
|---|---|---|
| CIF distinto por proveedor | COFARES `A00000001`, HEFAME `B00000002`, Alliance `B00000003` (H3a los tenía todos en `B00000000`) | proveedores, facturas (`proveedores_filtro`, `proveedor_grupo`) |
| CIF escrito de otra forma + otro literal | F02: `b-00000003` y literal «Alliance Healthcare España» → mismo grupo que Alliance; etiqueta = literal más frecuente (ALLIANCEHEALTHCARECENCORA), el otro como alias | proveedores, facturas |
| Factura sin CIF | F06 (FEDEFARMA) sin CIF → grupo `nombre:FEDEFARMA` (nombre canónico R9), marcado sin CIF | proveedores, facturas |
| Incidencia INFO | MONEDA_NO_DOCUMENTADA (INFO, abierta) en F02 → solo en el detalle de F02; ni contador ni «Necesita tu atención» de Inicio | detalle, inicio |
