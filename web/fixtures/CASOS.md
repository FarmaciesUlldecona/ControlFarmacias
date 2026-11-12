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
| Factura sin CIF | F06 (FEDEFARMA) sin CIF → grupo de respaldo (H4c: `id:4`, ver abajo), marcado sin CIF | proveedores, facturas |
| Incidencia INFO | MONEDA_NO_DOCUMENTADA (INFO, abierta) en F02 → solo en el detalle de F02; ni contador ni «Necesita tu atención» de Inicio | detalle, inicio |

## H4c: ajustes con la forma real de producción

Casos añadidos en `scripts/gen_fixtures.mjs` (los `v_web_*.json` no cambian). Todo ficticio.

| Caso H4c | Datos | DTO |
|---|---|---|
| CIF en `datos_extraidos` | Como en producción, `facturas.proveedor_cif` es null en todas; el CIF va en `datos_extraidos.proveedor.nif.valor` (columna `proveedor_nif_documental` de la consulta). Los CIF H4b no cambian; F02 lo tiene escrito `b-00000003` → `cif:B00000003` | facturas, detalle (`proveedor.cif`), proveedores |
| Sin CIF: respaldo R9 | F06 (FEDEFARMA) sin CIF y `id_proveedor_albaranes` `0004` → grupo `id:4` (R9: `'0004'` = `'4'`), marcado sin CIF. El nombre ya no agrupa | proveedores, facturas (`proveedores_filtro`) |
| Vencimiento con importe null | F04, 3.º vencimiento (30/11): la UI muestra «importe pendiente»; en el detalle de F04, aparte, «total factura: 568,05 € (referencia)», nunca como importe del vencimiento | detalle, inicio |
| Tipo de documento no documentado | F05 (HEFAME, 288,00 €): `datos_extraidos.tipo_documento` null (la columna quedó en FACTURA por defecto) → sentido `NO_DOCUMENTADO`: no suma como cargo ni abono | vencimientos, cashflow, detalle |
| PDF sin factura con proveedor | D08 y D13 (LAB_DEMO), D11 (BEIERSDORF), D14 (Alliance): `normalizacion_ejecuciones.proveedor_id` del catálogo → fila `catalogo:<id>` del mapa, marcada sin CIF | proveedores (`mapa_documentos`) |
| PDF sin factura sin proveedor | D09 (ERROR), D10 (PENDIENTE), D12 (PROVEEDOR_NO_SOPORTADO): sin ese campo → una sola fila «PDF sin factura (proveedor no identificado)», solo por estado | proveedores (`mapa_documentos`) |

## H4c-2: regla de sentido de Pío

El sentido de cada factura y de sus vencimientos sale **solo** de `datos_extraidos.tipo_documento.valor`, nunca de la
columna `tipo_documento`. FACTURA y FACTURA_DUPLICADO cuentan como CARGO y ABONO como ABONO. El resto queda
NO_DOCUMENTADO, que no suma y se cuenta aparte: FACTURA_RECTIFICATIVA y sus variantes (cualquier valor que contenga
RECTIFICATIVA), vacío, null, OTRO u otro valor. En las fixtures, la columna se rellena como lo hace la persistencia
(migración 28): null → FACTURA y, si el valor está fuera de la lista, OTRO.

| Factura | Tipo documental | Columna | Sentido | Efecto |
|---|---|---|---|---|
| F01, F02, F04 | FACTURA | FACTURA | CARGO | — |
| F08 | FACTURA_DUPLICADO | OTRO | CARGO | Sigue sumando como cargo (semana 2026-11-02) |
| F07 | ABONO | ABONO | ABONO | Abonos −45,30 |
| F03 | FACTURA_RECTIFICATIVA | FACTURA_RECTIFICATIVA | NO_DOCUMENTADO | Sale de los cargos de la semana 2026-11-09 (997,37 → 622,22) |
| F05 | null | FACTURA | NO_DOCUMENTADO | Sale de los cargos de la semana 2026-11-02 (592,74 → 304,74) |
| F06 | «OTRO» literal | OTRO | NO_DOCUMENTADO | Importe null; se cuenta en la semana 2026-11-16 |

Resultado: `vencimientos.totales.sentido_no_documentado` = 3, y 1 por semana en 2026-11-02, 2026-11-09 y 2026-11-16.
Diagnóstico de tipo de las fixtures: factura 3, factura_duplicado 1, abono 1, factura_rectificativa 1, otro 1,
vacio_o_null 1, otros_valores 0.

## H4d: «Necesita tu atención» agrupado

Incidencias añadidas en `scripts/gen_fixtures.mjs` (`INCIDENCIAS_H4D`). Todas son ficticias y están abiertas. Como hace la
persistencia, `mensaje_usuario` lleva el propio código, así que la web nunca lo muestra: usa `TEXTO_INCIDENCIA`.

| Caso H4d | Datos | Efecto en Inicio |
|---|---|---|
| Varios casos del mismo código | IMPORTE_VENCIMIENTO_NO_DOCUMENTADO en F04 (H3a) y F06 | Una fila «Un vencimiento de la factura no indica su importe», con 2 casos |
| Incidencia SENTIDO_NO_DOCUMENTADO | F07 (H3a), F03 (AVISO) y F02 (**ERROR**) | Desde H4d-3: nivel 7, grupo propio con 3 casos, en naranja aunque uno sea ERROR |
| MONEDA_NO_DOCUMENTADA con severidad AVISO | F04 (en producción se guarda como AVISO) | No sale en Inicio ni en el contador; sí en el detalle de F04 |
| Código sin traducción | CODIGO_FICTICIO_SIN_TRADUCCION en F05 | «Aviso técnico del motor (ver detalle)», con el código en pequeño |
| CANDIDATO_ALBARAN_NO_PROMOVIDO con dos motivos | F01 (TIPO_PEDIDO_NO_CERTIFICADO) y F02 (SENTIDO_O_SIGNO_NO_COHERENTE) | Una fila con 2 casos; el texto de cada caso depende de `detalle_tecnico.motivo` |
| Posible duplicado en vencimientos | F01 tiene POSIBLE_DUPLICADO | El vencimiento del 04/11 sale marcado «posible duplicado» |

Resultado tras H4d-3: «15 tipos, 26 casos». Incidencias abiertas en el contador: 13, de ellas 2 bloqueantes.

Orden de los grupos:

1. Diferencia con albaranes (3 casos)
2. Documentos con defecto (2)
3. Duplicados en Farmatic (1)
4. Vencimiento sin cargo/abono documentado (3: F06, F03 y F05; ver H4d-3)
5. Albarán facturado que ya no está en Farmatic (1)
6. Incidencias ERROR, un grupo por código: REQUIERE_REVISION («Facturas con datos por revisar», en **naranja**), SEGUNDA_LECTURA_FALLIDA y VALOR_SIN_EVIDENCIA
7. Avisos, un grupo por código, del más reciente al más antiguo: SENTIDO_NO_DOCUMENTADO (3), IMPORTE_VENCIMIENTO (2), SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE (1), CANDIDATO (2), POSIBLE_DUPLICADO (2) y el código sin traducción (1)
8. Correcciones aprobadas (2)

## H4d-2: ajustes de Pío

- «Facturas con datos por revisar» (REQUIERE_REVISION) sigue en el grupo 6, pero en naranja: revisión = naranja.
- Los PDF sin automatizar (PROVEEDOR_NO_SOPORTADO: D08, D11, D12 y D13) ya no salen en «Necesita tu atención».
  Siguen en el contador gris «Sin automatizar» (4) y en el mapa de Proveedores.
- Nuevos códigos solo de detalle: fuera de Inicio y de sus contadores, visibles en el detalle de su factura. Cada
  fixture lleva severidad AVISO, como la guarda producción.

| Código | Factura |
|---|---|
| MONEDA_NO_DOCUMENTADA | F04 (H4d) |
| REPRESENTACIONES_CONSOLIDADAS | F03 |
| FILAS_DUPLICADAS_EVIDENCIA_IDENTICA | F07 |
| FILA_IMPORTE_CERO_INFORMATIVA | F01 |
| ALBARANES_CONSUMIBLES_SOLO_REFERENCIA_DOCUMENTAL | F05 |

## H4d-3: sentido no documentado separado en dos

- **Grupo 4, «Vencimiento sin cargo/abono documentado»** (naranja): un caso por vencimiento con sentido NO_DOCUMENTADO
  según la regla de Pío (`datos_extraidos.tipo_documento.valor`). Texto: «No se sabe si esta factura es un pago o un
  abono; no se suma en el cashflow». No lleva código técnico y el enlace va a la factura. Casos: F06 (OTRO, 19/11),
  F03 (FACTURA_RECTIFICATIVA, 14/11) y F05 (sin tipo, 07/11).
- **Incidencias del motor SENTIDO_NO_DOCUMENTADO y SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE**: cada código tiene su
  propio grupo en el nivel 7 (naranja), con su texto de movimiento o de línea. Fixture nueva:
  SENTIDO_NO_ETIQUETADO_DOCUMENTALMENTE (AVISO) en F04, que sube el contador de incidencias a 13.
- **Diagnóstico `sentido` de check:real.** Sobre las fixtures daría vencimiento_regla 3,
  incidencia_sentido_no_documentado 3 e incidencia_sentido_no_etiquetado 1.

## H5: pantalla Facturas (listado y detalle)

Casos añadidos en `scripts/gen_fixtures.mjs` sobre las líneas H3a (mismos importes: las conciliaciones no cambian). Todo ficticio.

| Caso H5 | Datos | Efecto |
|---|---|---|
| Letra final (Alliance) | F02 línea 8: PDF 08X20008 ↔ Farmatic 08X20008A, `clase_numero` LETRA_FINAL | «Mismo número con una letra final» |
| ECO360 (R19) | F02 línea 7: albarán de Farmatic con `id_proveedor` 154 y proveedor 6PLATAFECO360AH | Nota «Albarán de la plataforma ECO360: Farmatic lo registra como compra a Alliance» |
| Final documental | F04 línea 3: PDF CF-26007012 ↔ Farmatic 26007012, `clase_numero` FINAL_DOCUMENTAL | «El número de Farmatic es el final del número de la factura» |
| R17 (misma recepción) | F03 línea 2 (98,70): dos detalles UNO_A_VARIOS, 77002 (60,00, papel NUMERO) + Q039904/2026 (38,70, papel INTERNO); la línea sin coincidencia pasa al orden 4 | Una línea del PDF con dos albaranes de Farmatic |
| Cargo sin albarán | F04 movimiento «SERVICIO INTEGRAL DE DISTRIBUCION»: `sentido_documental` = CARGO, como la consulta (`coalesce(fae.tipo_movimiento, fm.sentido)`) | «Cargo o servicio sin albarán: no se busca en Farmatic» |
| Impuestos | Un tramo por factura con base e IVA conocidos (IVA 10 % y recargo 1,4 %, los de los totales H3a); F06 sin tramos | Desplegable Fiscalidad |
| Otras facturas del PDF | D03: F03 (págs. 1–3) y F04 (págs. 4–5) | «El PDF contiene también…» en el recuadro del PDF |

Ya existían: número exacto (F01, F02…), Hefame número e importe (F05, EXACTO_ECONOMICO), albarán no localizado (F03,
SIN_COINCIDENCIA), varios candidatos (F05, AMBIGUO) y movimiento sin sentido (F07).

Listado (generado_at 02/11/2026 = «hoy»): F04 muestra el vencimiento del 15/11 con «+2» (el del 30/10 ya pasó); F06,
«importe pendiente». Pestañas: Todas 8, Conciliadas 3, Pendientes de conciliar 4, En revisión 2, No revisadas por Pío 3.
Insignias: posible duplicado F01 y F08; abono F07; sentido no documentado F03, F05 y F06.

## H5-2: bases de importe, cómo casó y búsqueda por importe

Las líneas de conciliación de las fixtures siguen la forma de producción:
- **Columnas que la persistencia no escribe.** `importe_documental`, `importe_farmatic` y `diferencia` de `conciliacion_detalles` van a null, porque la persistencia solo escribe `importe_aplicado` (migración 24, líneas 338-354).
- **Importes del albarán en el PDF** (`facturas_albaranes_extraidos`):
  - `importe_total` es el importe documental de H3a: total con IVA y RE, que es lo que compara el motor.
  - `importe_base` es su base sin IVA, ficticia (÷ 1,114).
  - Hefame (F05): `importe_total` es la base neta e `importe_base` no consta.
- **F05:** sus tres albaranes casados pasan a número exacto (antes INTERNO), como los clasifica el motor en Hefame.
- **F04:** el movimiento lleva `magnitud_usada` IMPORTE y su base en `facturas_movimientos.base`.

| Caso | Efecto |
|---|---|
| Cómo casó | Principal = forma del número (mismo número, letra final, final documental, numeración interna, Hefame número e importe) o motivo de no casar. Secundario = relación (1 línea = 1 albarán, 1 línea = 2 albaranes de la misma recepción R17, sin albarán, sin casar). R17 en F03: «Mismo número de albarán» + «Numeración interna…», los dos con la relación R17 |
| Bases rotuladas | Total albarán (PDF) y Aplicado (Farmatic): con IVA y RE, se comparan. Base (PDF): sin IVA, no se compara. Sin columna de diferencia por línea (el motor no la guarda) |
| Filtro «Con importe pendiente» | Cualquier vencimiento con importe null: F04 (3.º) y F06 |
| Búsqueda por importe | Probada en el e2e con importes ficticios inyectados (F02 total 5.000,10; F04 2.º vencimiento 5.000,95): «5000», «5.000» y «5 000 €» → F02 y F04; «5000,1» → F02; «5000,95» → F04 |

## H5-3: estados de casado no previstos

| Caso | Datos | Efecto |
|---|---|---|
| Sin número para comparar | F07 línea 1: PDF sin número, `clase_numero` NO_DISPONIBLE | «Sin número para comparar: casa por importe (PUC) y fecha (±3 días)» |
| Estado no previsto con forma de código | F07 línea 3 (77091): `estado_matching` ESTADO_FUTURO_PRUEBA | «Estado del motor sin descripción (ver evidencia técnica)»; el literal solo en Evidencia técnica. Diagnóstico: `estado_matching.no_previsto.ESTADO_FUTURO_PRUEBA=1` |
| Valor que no es código | F07 línea 4 (77092): `estado_matching` «valor raro (no es código)» | Mismo texto en la web; en el diagnóstico solo suma en `estado_matching.otros_no_codigo` |
| Albarán ya conciliado | F07 línea 5 (77093): ALBARAN_YA_CONCILIADO | «El albarán ya justifica otra factura o línea» |
| Clase no prevista | F04 línea 2: `clase_numero` CLASE_FUTURA_PRUEBA | Sin descripción; diagnóstico `clase_numero.no_previsto.CLASE_FUTURA_PRUEBA=1` |

Las líneas 3 a 5 de F07 son sin casar con `importe_aplicado` 0, así que el explicado y la conciliación de F07 no cambian.

## H5-5: estados de una versión anterior del motor

| Caso | Datos | Efecto |
|---|---|---|
| EXACTO | F01 línea 1: `estado_matching` EXACTO, sin `clase_numero` | «Un único albarán; el motor anterior lo dio por número coincidente (versión anterior del motor)»; secundario «Versión anterior del motor: …». H5-6: texto neutro, nunca «mismo número» (hay líneas reales con prefijo o letra final, p. ej. 57517 ↔ 08C57517A). Casada (verde). Diagnóstico `estado_matching.exacto` (etiqueta fija) |
| ECONOMICO_UNICO | F01 línea 2: `estado_matching` ECONOMICO_UNICO, sin `clase_numero`, Farmatic 08X10002B | «Un único albarán por importe; el número no es idéntico (versión anterior del motor)». Casada (verde). Diagnóstico `estado_matching.economico_unico` |

Fuente (H5-5): commit e18acf0, `pruebas/auditoria_2t/flujo_controlado.py:210-211,370` y `pruebas/auditoria_2v/conciliar_08009277.py:72-73,197` (EXACTO = MATCH_UNICO con número EXACTA; ECONOMICO_UNICO = MATCH_UNICO sin número exacto); `pruebas/auditoria_2t/resultado.md:36-40` (criterios del casado económico). Importes y conciliación de F01 sin cambios.

## H5-7: detalle por línea de la conciliación (migración 30)

Las fixtures rellenan `importe_documental`, `importe_farmatic`, `diferencia` y `estado` de cada detalle como `cf_detalles_por_linea` (`sql/migrations/30_cf_detalle_por_linea.sql:43-70`; espejo en `conciliacion.py:695-730`). La web los muestra tal cual, sin recalcular.

| Caso | Datos | Efecto |
|---|---|---|
| COINCIDE | F02 (diferencias de 0,01 €), F03 R17 (dos albaranes, una línea, diferencia 0,00 €) | Insignia verde «Coincide» |
| DIFERENCIA en línea casada | F03 línea 1: el PDF trae 234,65 € y Farmatic 234,55 € (ajuste ficticio) | Diferencia 0,10 €, insignia roja «Diferencia» |
| DIFERENCIA sin casar | F03 línea 4, F05 línea 4, F07 líneas 3 y 4 | Farmatic «no consta»; diferencia = importe del PDF |
| NO_EVALUABLE con Farmatic | F02 línea 6: el PDF no trae importe (ajuste ficticio) | Gris «Sin importe del PDF para comparar»; PDF y diferencia «no consta» |
| NO_EVALUABLE sin Farmatic | F07 línea 5: sin casar y el PDF sin importe (ajuste ficticio) | Gris «Sin contraparte en Farmatic»; los tres importes «no consta» |
| Movimiento | F04 línea 4, F07 línea 2 | NO_EVALUABLE (sección Cargos y abonos); el de F07 sin importe aplicado queda null, nunca 0 |
| Hefame | F05: el PDF trae la base neta y Farmatic el importe con IVA | Diferencias −14,86 / −9,07 / −3,15 €, todas DIFERENCIA, tal cual; nota visible y aviso arriba: «El motor compara la base neta del PDF (sin IVA) con el importe de Farmatic (con IVA): la diferencia incluye el IVA y el recargo» |
| Aviso arriba | F03: «2 albaranes con diferencia · De ellos, 1 sin casar en Farmatic»; F05: 4 + advertencia Hefame; F07: 2; F02: sin aviso | Una línea R17 cuenta una vez |

Diagnóstico `estado_linea` de la comprobación en modo REAL: `lineas`, `coincide`, `diferencia`, `no_evaluable`, `sin_valor`, `otros_valores`, `diferencia_null` (solo recuentos; falla cerrado si los estados no suman el total).

## H5-8: nombre comercial de proveedor, búsqueda y fiscalidad sin tipo

Proveedor = nombre comercial (principal) + razón social del PDF (secundaria, pequeña), igual en el listado, el filtro, el detalle, Inicio (vencimientos y «Necesita tu atención») y los grupos de Proveedores. Equivalencias en `app/server/proveedor_comercial.ts`, cada una con su fichero:línea de `src/`; sin equivalencia, el literal del PDF; si el CIF y el literal dan nombres distintos, null (falla cerrado). Los grupos siguen siendo por CIF (sin cambios).

| Caso | Datos | Efecto |
|---|---|---|
| Hefame por CIF y razón social | F05: CIF F30004444 (`grupos_funcionales.py:41`, CIF de empresa que consta en el código) y razón social «HDAD.FMCTCA.MEDIT.,S.C.L.» (`hefame.py:92`) | «HEFAME» + «HDAD.FMCTCA.MEDIT.,S.C.L.» debajo; filtro «HEFAME · HDAD.FMCTCA.MEDIT.,S.C.L.»; CIF F30004444 en el detalle |
| Alliance por alias del motor | F01/F08 «ALLIANCEHEALTHCARECENCORA», F02 «Alliance Healthcare España» (CIF ficticio B00000003) | «ALLIANCE» + razón social (`conciliacion.py:34-43`) |
| Sin equivalencia | F03/F04/F07 «COFARES» (CIF ficticio), F06 «FEDEFARMA» (sin CIF) | Literal del PDF, sin línea secundaria. Cofares solo se reconoce por «GRUPO COFARES» (`cofares.py:211`) y Fedefarma por su CIF F-08-173395 (`fedefarma.py:37`) |
| Búsqueda | «hefame», «Hefame», «HDAD», «F30004444», «F-30004444» → solo F05; «alliance» → F01, F02, F08; «ESPANA» → F02 | Sin mayúsculas ni acentos; CIF también con guiones o puntos |
| Fiscalidad sin tipo | F05: tramo con `tipo_iva` y `tipo_recargo_equivalencia` null (Hefame no documenta tipos, `hefame.py:378`) | Columna Tipo «tipo no indicado» (antes «IVA —»); cuotas «25,85 €» y «3,62 €» sin nada delante. El «—» era `tipoPorcentaje(null)`, no un signo: los importes son positivos |

## TA1: Trabajadores (fichas con datos de ejemplo en memoria)

Fichas ficticias en `fixtures/rrhh/trabajadoras.json` (nombres inventados; solo nombre, sin DNI ni otros datos personales). El servidor FIXTURES las carga en memoria (`app/server/rrhh/adaptador_fixtures.ts`); alta, edición y baja cambian solo esa memoria y se pierden al reiniciar. Cada cambio queda en el historial (quién, cuándo, antes/después). En modo REAL, `/api/rrhh/*` responde 503 «Módulo pendiente de conexión (T1)» sin datos; las tablas reales las creará el circuito en T1.

TA1-2 (decisiones de Pío): la jornada se guarda en **horas diarias** (lunes a viernes): completa = 8 h/día; media mañana = menos de 8 h/día, siempre de mañana; TA1-3: media tarde = menos de 8 h/día, por defecto 3,5 h (17:00–20:30). El **porcentaje es derivado** (horas semanales / 40 h de referencia; la referencia está en `convenio_anual.horas_semanales_referencia`, rotulada «provisional») y nunca se edita. Objetivo anual = jornada máxima del año × horas semanales / referencia, redondeado a 0,1 h al final. Autor del historial: «Marc».

| Caso | Datos | Efecto |
|---|---|---|
| PIO | 3 técnicas completas (8 h/día) + Elena Mas Garriga, media mañana 4,5 h/día | Elena: 22,5 h/sem = 56,25 %; objetivo 2026: 1767 × 22,5 / 40 = 993,9 h; 2027–2028: 985,5 h |
| RITA | Laura Serra Coll (farmacéutica) + 4 técnicas completas + Paula Riera Bover, media mañana 4,5 h/día | Paula: igual que Elena (993,9 h en 2026) |
| Media tarde (TA1-3) | RITA: Irene Gual Torrent, técnica, media tarde 3,5 h/día (17:00–20:30; por defecto 3,5 h, editable) | 17,5 h/sem = 43,75 %; objetivo 2026: 1767 × 17,5 / 40 = 773,1 h; 2027–2028: 766,5 h. Validación igual que la media mañana (> 0 y < 8 h) |
| Completa | 8 h/día × 5 = 40 h/sem | 100 %; objetivo = jornada máxima (1767 h en 2026; 1752 h en 2027–2028) |
| Titular | «Titular de ejemplo», dos fichas (PIO y RITA), media mañana 4,5 h/día en cada una | Computa «No · titular»; objetivo «fuera del cómputo» en todos los años; sus horas se registrarán (T5) |
| Convenio | 2026: 1767 h, 1 día de asuntos propios; 2027–2028: 1752 h, 0 días; permiso médico 24 h/año; referencia 40 h/sem; firmado, pendiente de publicación oficial | Objetivo rotulado «provisional: convenio pendiente de publicación»; referencia «provisional» |
| Validación | Nombre vacío; campo `dni`, `porcentaje_jornada` u otro no admitido; horas ≤ 0, > 8 o con más de 2 decimales; completa distinta de 8; media mañana de 8 h | 400 con error por campo; la pantalla lo muestra junto al campo y lo retira al corregirlo |
| Escritura | POST `/api/rrhh/trabajadoras`; PUT `/api/rrhh/trabajadoras/:id` y `/:id/baja` | Solo con sesión, Origin del mismo sitio (obligatorio) y JSON. El resto de la API sigue de solo lectura (405) |
| Horas | Planificadas, confirmadas y pendientes | Huecos rotulados «pendiente motor de horas (T5)» |
