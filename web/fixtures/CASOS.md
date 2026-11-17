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

Fichas ficticias en `fixtures/rrhh/trabajadoras.json` (nombres inventados; solo nombre, sin DNI ni otros datos personales). El servidor FIXTURES las carga en memoria (`app/server/rrhh/adaptador_fixtures.ts`); alta, edición y baja cambian solo esa memoria y se pierden al reiniciar. Cada cambio queda en el historial (quién, cuándo, antes/después). Modo REAL: ver la sección TA-REAL (tablas reales de la migración 31).

TA1-2 (decisiones de Pío): la jornada se guarda en **horas diarias** (lunes a viernes): completa = 8 h/día; media mañana = menos de 8 h/día, siempre de mañana; TA1-3: media tarde = menos de 8 h/día, por defecto 3,5 h (17:00–20:30). El **porcentaje es derivado** (horas semanales / 40 h de referencia; la referencia está en `convenio_anual.horas_semanales_referencia`, rotulada «provisional») y nunca se edita. Objetivo anual = jornada máxima del año × horas semanales / referencia, redondeado a 0,1 h al final. Autor del historial: «Marc».

| Caso | Datos | Efecto |
|---|---|---|
| PIO | 3 técnicas completas (8 h/día) + Elena Mas Garriga, media mañana 4,5 h/día | Elena: 22,5 h/sem = 56,25 %; objetivo 2026: 1767 × 22,5 / 40 = 993,9 h; 2027–2028: 985,5 h |
| RITA | Laura Serra Coll (farmacéutica adjunta) + 4 técnicas completas + Paula Riera Bover, media mañana 4,5 h/día | Paula: igual que Elena (993,9 h en 2026) |
| Media tarde (TA1-3) | RITA: Irene Gual Torrent, técnica, media tarde 3,5 h/día (17:00–20:30; por defecto 3,5 h, editable) | 17,5 h/sem = 43,75 %; objetivo 2026: 1767 × 17,5 / 40 = 773,1 h; 2027–2028: 766,5 h. Validación igual que la media mañana (> 0 y < 8 h) |
| Completa | 8 h/día × 5 = 40 h/sem | 100 %; objetivo = jornada máxima (1767 h en 2026; 1752 h en 2027–2028) |
| Titular | «Titular de ejemplo», categoría Farmacéutica titular (FARMACEUTICA_TITULAR), dos fichas (PIO y RITA), media mañana 4,5 h/día en cada una | Computa «No · titular»; objetivo «fuera del cómputo» en todos los años; sus horas se registrarán (T5) |
| Convenio | 2026: 1767 h, 1 día de asuntos propios; 2027–2028: 1752 h, 0 días; permiso médico 24 h/año; referencia 40 h/sem; firmado, pendiente de publicación oficial | Objetivo rotulado «provisional: convenio pendiente de publicación»; referencia «provisional» |
| Validación | Nombre vacío; campo `dni`, `porcentaje_jornada` u otro no admitido; horas ≤ 0, > 8 o con más de 2 decimales; completa distinta de 8; media mañana de 8 h | 400 con error por campo; la pantalla lo muestra junto al campo y lo retira al corregirlo |
| Escritura | POST `/api/rrhh/trabajadoras`; PUT `/api/rrhh/trabajadoras/:id` y `/:id/baja` | Solo con sesión, Origin del mismo sitio (obligatorio) y JSON. El resto de la API sigue de solo lectura (405) |
| Horas | Planificadas, confirmadas y pendientes | TA-FICHA: sustituido por la ficha anual (ver la sección TA-FICHA) |

## TA2: Trabajadores · calendario (datos de ejemplo en memoria)

Semilla ficticia en `fixtures/rrhh/eventos.json`; contrato, validación y almacén en `app/server/rrhh/eventos.ts`. Al arrancar, el servidor FIXTURES carga las ausencias de ejemplo, rellena la jornada habitual de todas las fichas activas del 2 al 29 de noviembre de 2026 sin pisarlas, y deja confirmada la semana del 2 al 8. La carga no deja historial. Los cambios solo viven en memoria. Modo REAL: ver la sección TA-REAL.

Reglas:
- **TA2-2: un evento por persona, día y franja** (mañana o tarde). Por ejemplo, mañana JORNADA y tarde PERMISO_MEDICO.
- Las franjas salen de la ficha: completa, mañana y tarde; media mañana, solo mañana; media tarde, solo tarde (con todas sus horas).
- **TA2-3: la jornada completa es mañana 4,5 h (9:00–13:30) + tarde 3,5 h (17:00–20:30) = 8 h**, el horario real de Pío. El reparto se configura en un único punto, `HORARIO_COMPLETA` en `app/server/rrhh/contrato.ts`, que falla al cargar si no suma 8 h. Las medias jornadas no cambian (mañana 4,5 h; tarde 3,5 h por defecto). Pintar una franja que la persona no tiene falla cerrado (`FRANJA_NO_VALIDA`) y no se aplica nada.
- La farmacia es la de la ficha, nunca la que mande el cliente.
- Todo nace PLANIFICADO. CONFIRMADO se marca a mano: una franja confirmada no se pinta, no se borra ni se le editan horas o nota sin quitar antes la confirmación.
- **TA2-2: nota opcional por evento**, de 200 caracteres como máximo, con el aviso «No anotes datos de salud ni diagnósticos». Se ve al pasar el ratón (marca ✎) y en el detalle del día, y queda en el historial. Al pintar otro tipo encima, la nota anterior se quita (sigue en la traza).
- Fechas admitidas: solo los años del convenio (2026–2028). Rellenar y confirmar por periodo, hasta 366 días.
- **TA2-4: los mensajes cuentan días × personas**, no días de persona. El formato es `<qué> <periodo>: N días laborables × P personas`, por ejemplo «Rellenado 2027: 261 días laborables × 5 personas», nunca «1305 días».
  - **Periodo:** el pedido al rellenar o confirmar un rango (semana, mes o año, también al deshacerlo). Si no hay rango pedido, el afectado («10 nov 2026», «2–8 nov 2026», «diciembre de 2026», «2027»).
  - **«días» sin «laborables»:** cuando entra algún fin de semana.
  - **Franjas:** se añade «· N franjas» cuando alguna persona-día se tocó solo en parte (p. ej., solo la tarde de una completa).
  - **Deshacer:** «Deshecho «Rellenado 2027»: 261 días laborables × 5 personas».
- **TA2-4: notas más visibles.**
  - **Botón «Añadir nota» en la barra de selección.**
    - Con una franja con evento en el detalle, lleva a su campo Nota.
    - Con varias, abre «Misma nota para las N franjas con evento» y aplica la misma nota a todas (acción `ANOTAR`, un solo cambio, deshacible). Las vacías y las confirmadas se omiten, y se avisa de cuántas.
  - **Detalle del día:** el campo Nota se ve siempre con su aviso de salud. En lo confirmado aparece bloqueado y en una franja libre también se ve.
  - **Franja vacía:** intentar anotarla da «Pinta primero un evento para poder anotarlo» y no se crea nada.

| Caso | Datos | Efecto |
|---|---|---|
| Carga | 21 franjas por día (8 completas × 2 + 5 medias) × 20 laborables | 420 eventos; 41 de ausencia (23 días de persona); 105 confirmados (semana del 2 al 8); nada en fin de semana |
| PIO | Aina, vacaciones 16–20 nov; Clara, asuntos propios 13 nov; Núria, permiso médico la **tarde** del 10 nov (mañana: jornada); Elena, permiso retribuido 25–26 nov (nota «Traslado de domicilio») | Semana del 9 al 15: trabajan 12, 12, 12, 12 y 11 (en Ambas) |
| RITA | Marta, baja 9–13 nov; Sílvia, vacaciones 23–27 nov; Judit, descanso compensatorio 6 nov (confirmado; nota «Compensa el sábado 31 de octubre»); Rosa, asuntos propios la **mañana** del 18 nov (tarde: jornada; nota «Gestión en el ayuntamiento»); Paula, permiso no retribuido 19 nov; Laura, permiso médico 24 nov | Irene (media tarde): solo tardes de 3,5 h |
| Vistas | Semana: dos subfilas por persona (M y T; la franja que no trabaja, rayada). Mes y por persona: cada día partido en mañana (arriba) y tarde (abajo). Año: resumen por día (personas ausentes y cuántas trabajan) | Filtros: persona, categoría y tipo de evento; los demás tipos se atenúan, nunca se ocultan |
| Pintar | Paleta de tipos (también es la leyenda). Semana: clic en una franja, o arrastre sobre las dos para el día. Mes y por persona: un clic aplica al día completo (las franjas de la persona). Toque en móvil; clic en la cabecera de un día aplica a todas las personas | Pintar sobre otro tipo lo sustituye (EDITAR con antes/después); el mismo tipo no cambia nada; las franjas confirmadas se omiten y se avisa |
| Goma | Clic o arrastre, por franja o día | Borra lo planificado; lo confirmado se omite |
| Rellenar jornada habitual | Semana o mes visible; **año completo** (TA2-2) en las vistas año y por persona, con confirmación | JORNADA de lunes a viernes por franja según la ficha vigente; no pisa lo pintado ni lo confirmado; repetirlo no crea nada; se deshace de una vez |
| Año vacío | Al abrir un año sin eventos para las personas visibles | Se ofrece «Rellenar AAAA…», con confirmación (Cancelar no crea nada). 2027 en PIO: «Rellenado 2027: 261 días laborables × 5 personas» |
| Confirmar | «Confirmar semana / mes» o selección | PLANIFICADO → CONFIRMADO; «Quitar confirmación» lo revierte |
| Detalle del día | Una celda seleccionada (franja o día completo) | Cada franja de la persona con tipo, horas, estado y nota, o «libre». **TA2-4: el campo Nota siempre está a la vista** (bloqueado en lo confirmado; en lo libre, «Pinta primero un evento para poder anotarlo»). En lo planificado se editan las horas realizadas (> 0 y ≤ 8 h, el límite de la tabla) y la nota |
| Añadir nota (TA2-4) | Botón en la barra de selección | Sin franjas con evento: «Pinta primero un evento para poder anotarlo». Con una: su editor. Con varias: misma nota para todas, omitiendo vacías y confirmadas con aviso. Ej.: 28 dic, Aina M y T y Clara M con vacaciones y Clara T libre → «Anotado 28 dic 2026: 1 día laborable × 2 personas · 3 franjas. 1 franja vacía no se ha anotado…» |
| Deshacer | Botón (dice qué deshace) o Ctrl+Z | Revierte el último cambio y luego el anterior; restaura exactamente (franjas y notas); falla cerrado si el estado ya no es el que dejó el cambio |
| Historial | **Plegado por defecto** (también el de cada ficha); un clic lo despliega. Cada cambio: qué, días, personas, cuándo y quién («Marc»); detalle franja a franja (antes → después, con la nota) | Los deshechos llevan la marca «deshecho» |
| Colores | Configurables en la leyenda | Solo en el navegador de quien los cambia; «Restablecer colores» |
| Escritura | Solo POST `/api/rrhh/eventos` (PINTAR, BORRAR, RELLENAR, CONFIRMAR, DESCONFIRMAR, EDITAR horas y nota, ANOTAR) y POST `/api/rrhh/eventos/deshacer` | Con sesión, Origin del mismo sitio y JSON. Persona anulada o inexistente, día fuera de su alta o franja ajena: no se aplica nada. DELETE, PUT y PATCH: 405 |

## TA-REAL: Trabajadores conectado a las tablas reales (migración 31)

El contrato de la web usa los nombres y valores de `sql/migrations/31_cf_trabajadores.sql`. Dos adaptadores con la misma interfaz:
- **RRHH_FIXTURES** (`app/server/rrhh/adaptador_fixtures.ts`): datos de ejemplo en memoria, para las pruebas. Mismas reglas que las tablas.
- **RRHH_REAL** (`app/server/rrhh/adaptador_real.ts`): rol `cf_trabajadores_web`, credencial propia en `.env.web` (ver `docs/CONFIG.md`), pool de 2 conexiones, TLS con la CA.

Reglas:
- **Fichas (`trabajadoras`).**
  - Categorías FARMACEUTICA_TITULAR, FARMACEUTICA_ADJUNTA, TECNICA, AUXILIAR y OTRA.
  - Titular = FARMACEUTICA_TITULAR, con `computa_convenio` false (se guarda en la tabla).
  - `tipo_jornada` (COMPLETA, MEDIA_MANANA, MEDIA_TARDE) y `horas_diarias`.
  - **`fecha_alta` obligatoria**: por defecto hoy, editable.
- **Baja y anulación.**
  - «Dar de baja» = `fecha_baja`, que no puede ser anterior al alta (check de la tabla).
  - **«Anular»** es una acción aparte, con confirmación, para registros erróneos (`anulada`).
  - Nada se borra.
  - Una ficha anulada sale del listado (salvo «Incluir bajas y anuladas») y del calendario, y libera su nombre.
- **Calendario.**
  - Salen las fichas sin anular que están de alta algún día del periodo.
  - Fuera del alta o la baja, la celda no se pinta. Por petición, falla cerrado (`EVENTO_FUERA_DEL_ALTA`, como el trigger).
  - Rellenar solo crea los días de alta.
- **11 tipos de evento.**
  - FESTIVO, TURNO_GUARDIA y LOCALIZADA se ven si existen, pero se pintan desde TA3.
  - TURNO_GUARDIA y LOCALIZADA no suman horas.
- **Horas.**
  - Vacías (`horas` null) = las de la ficha. Se leen de `v_eventos_calendario_horas.horas_efectivas`.
  - La vista repite el reparto 4,5 h + 3,5 h de `HORARIO_COMPLETA`; si este cambia, hay que cambiar la vista.
  - Pintar otro tipo devuelve las horas a las de la ficha.
- **Goma y deshacer en REAL.**
  - Desactivados con el aviso «Pendiente de que la base de datos permita anular eventos» hasta que exista `eventos_calendario.anulado`.
  - El deshacer de cambios de tipo, nota o estado sí funciona (UPDATE al valor anterior), pero solo para los cambios de la sesión del servidor.
- **Escritura en REAL.**
  - Cada una en su transacción con `set_config('cf.autor', 'Marc', true)`.
  - Ante error, ROLLBACK y mensaje llano, sin reintentar.
  - Rellenar: INSERT … ON CONFLICT DO NOTHING por lotes de 500.
- **Historial en REAL.** Sale de `trabajadores_historial`: un cambio por transacción (mismo `created_at`). El origen lo da la sesión o se deduce de las filas.
- **Notas próximas.**
  - Recuadro en Calendario con las notas de hoy (reloj del navegador) en adelante, por fecha: «Persona — fecha: nota».
  - La misma nota en las dos franjas de un día sale una vez.
  - Al pasar el día desaparecen del recuadro, pero siguen en el día y en el historial.
  - Un clic abre la semana de esa persona.
- **Banner.** En FIXTURES, «Datos de ejemplo…». En REAL conectado, «Datos reales: cada cambio se guarda en la base de datos con autor Marc». En REAL sin credencial, «Falta configurar la credencial de Trabajadores», sin ningún dato.

| Caso | Datos | Efecto |
|---|---|---|
| Fichas de ejemplo | Columnas de `trabajadoras`; alta 1 ene 2026; Laura, FARMACEUTICA_ADJUNTA; titulares, FARMACEUTICA_TITULAR | Mismos totales y objetivos que en TA1 |
| Baja antes del alta | Baja con fecha anterior a `fecha_alta` | 400 «La fecha de baja no puede ser anterior a la de alta.» |
| Baja en el calendario | Clara de baja el 30 nov | Sale hasta el 30 nov; pintar el 7 dic → `EVENTO_FUERA_DEL_ALTA` |
| Alta en el calendario | Ficha con alta el 10 dic 2026 | Antes del 10 no se pinta; «Rellenado diciembre de 2026: 16 días laborables × 1 persona» |
| Anular | «Anular» → confirmación → `{ "confirmar": true }` | Ficha anulada (no se edita; historial «Anulación: Anulada No → Sí»). Repetirlo: 409 |
| Nombre duplicado | Misma farmacia y nombre (sin distinguir mayúsculas) que otra ficha sin anular | 409 (en REAL, 23505 → «Ya existe un registro igual…») |
| Convenio que falta | `convenio_anual` sin alguno de 2026–2028 | «Crear convenio 2026–2028 con los valores firmados», con confirmación que enseña los valores; POST `/api/rrhh/convenio` `{ "anios": [...] }`; los años existentes no se tocan |
| Goma (TA-REAL-2) | REAL y FIXTURES | Ver TA-REAL-2: la goma anula; ya no hay aviso de «pendiente» ni error `ANULAR_EVENTOS_PENDIENTE` |
| Deshacer (TA-REAL-2) | Último cambio, también si creó eventos | Se deshace siempre: lo creado se anula y lo borrado se vuelve a crear |
| Notas próximas | Desde el 13 nov (ejemplo) | Rosa 18 nov, Elena 25 y 26 nov; la de Judit (6 nov) ya no sale. RITA: solo las suyas |
| Errores de la BD | P0001 AUTOR_AUSENTE / FARMACIA_NO_HABILITADA_EN_MODULO / EVENTO_FUERA_DEL_ALTA; 42501; 23505; 23514; 23503; 57014/25P03; 53300 | Código propio, HTTP (500/403/409/403/409/400/409/504/503) y mensaje llano. ROLLBACK, nunca se reintenta |
| REAL simulado | `server/pruebas/rrhh_real.test.ts`: pool inyectado, sin conexión | Autor por transacción, ROLLBACK, lotes, mapeo de filas, historial, deshacer |
| check:real | Rol `cf_trabajadores_web`, solo lectura | `DIAGNOSTICO trabajadores`: recuentos por tabla, `modulo_pio_rita` y años del convenio (y los que faltan) |

## TA-FICHA: ficha anual de cada persona y resumen de plantilla

Cálculo puro en `app/server/rrhh/ficha_anual.ts`, común a FIXTURES y REAL. Usa las mismas lecturas que ya existían: fichas y eventos del año (`calendario`) y `convenio_anual`. En REAL es solo lectura (transacción READ ONLY). Semilla ficticia en `fixtures/rrhh/ficha_anual.json`: eventos de 2026 fuera de noviembre, solo de fichas de RITA. Se suma a la de TA2, que no cambia.

API (solo GET, con sesión):
- `GET /api/rrhh/fichas?farmacia&anio&hoy` devuelve el resumen de plantilla.
- `GET /api/rrhh/trabajadoras/:id/anual?anio&hoy` devuelve la ficha anual.
- `anio` admite 2026–2028; por defecto, el año de `hoy`.
- `hoy` es el día del reloj del navegador; si falta, el del servidor.

Reglas de Pío:
- **Vacaciones: los días naturales del año salen de `convenio_anual.vacaciones_dias_naturales`** (TA-REAL-2; 30 en 2026–2028).
  - Si el año no tiene el dato, la ficha muestra «pendiente»: derecho y pendientes null, nunca 30 inventados.
  - La media jornada tiene los mismos días.
  - Con alta o baja dentro del año, el derecho es proporcional a los días en alta y se redondea al entero hacia arriba (`REDONDEO_PROPORCIONAL`, configurable).
- **Días extra (TA-REAL-2):** `trabajadoras_ajustes_anuales`, editables por persona y año. Derecho = base (proporcional si procede) + extra; el extra no se prorratea.
- **Días naturales.**
  - Un periodo va del primer al último día laborable seguidos de VACACIONES y cuenta todos los días naturales entre ambos.
  - Un fin de semana intermedio no corta el periodo. Tampoco un festivo, si la persona tiene un evento FESTIVO ese día.
  - Una sola franja de jornada completa = 0,5 días (cuenta suelta). La franja única de una media jornada = 1 día.
- **Disfrutadas y planificadas:** disfrutadas son las de hasta hoy, incluido; planificadas, las de desde mañana. Pendientes = derecho − disfrutadas − planificadas.
- **Libre disposición:** los `asuntos_propios_dias` del año, con las mismas medias franjas.
- **Permiso médico:** `permiso_medico_horas` (24) frente a las `horas_efectivas` de PERMISO_MEDICO.
- **Horas del año** (solo si la persona computa).
  - Objetivo del convenio, proporcional si hay alta o baja en el año.
  - Suman JORNADA, ASUNTOS_PROPIOS, PERMISO_RETRIBUIDO, PERMISO_MEDICO, BAJA y DESCANSO_COMPENSATORIO (`TIPOS_HORAS_COMPUTAN`, único punto). No suman VACACIONES ni PERMISO_NO_RETRIBUIDO.
  - **TA-FICHA-2 (regla de Pío):** el descanso compensatorio (día libre tras la semana de guardia de 24 h) cuenta como trabajado, con sus `horas_efectivas`, que son las de la jornada normal de la persona.
  - Se separan confirmadas (estado CONFIRMADO) y planificadas (PLANIFICADO).
  - Si se pasa del objetivo: «Exceso de X h ≈ Y días que podrían ser vacaciones (estimación)», con Y = X / horas diarias.
  - TA3-2 (decisión de Marc): los festivos no se descuentan del objetivo; la jornada máxima del convenio es trabajo efectivo y ya los descuenta. Se retira el aviso «Festivos aún no descontados (TA3)».
  - Titular: horas registradas, sin objetivo.
- **Aviso de octubre:** desde el 1 de octubre del año (`AVISO_VACACIONES_DESDE`, configurable) y hasta el 31 de diciembre, si quedan vacaciones sin planificar.
- **Otros avisos:** vacaciones por encima del derecho, libre disposición o permiso médico por encima del convenio, y año sin convenio.
- **Días de baja:** días naturales de los periodos de BAJA. Solo el número, nunca el motivo.
- **Próximas ausencias:** las 3 primeras desde hoy, incluida la que esté en curso. Jornada, guardia, localizada y festivo no cuentan.

| Caso | Datos | Efecto (hoy = 13 nov 2026) |
|---|---|---|
| Vacaciones con fin de semana dentro | Sílvia: 3–14 ago (L–V × 2) | 12 días naturales |
| Media franja | Sílvia: tarde del 9 oct (completa) | 0,5 días. Total: 12,5 disfrutadas + 5 planificadas (23–27 nov) → 12,5 sin planificar y aviso |
| Media jornada | Paula: 7–11 sep, su franja única | 5 días |
| Alta a mitad de año | Paula: alta 1 jul 2026, media mañana | Derecho 16 (30 × 184/365 = 15,12). Objetivo 501 h (993,9 × 184/365). En 2027: 30 y 985,5 h |
| Sin aviso | Laura: 6 jul – 4 ago | 30 días naturales → 0 pendientes, sin avisos |
| Exceso de horas | Judit: jornada confirmada de enero a octubre (217 días) + noviembre | 1776 h confirmadas + 120 planificadas → exceso de 129 h ≈ 16,1 días |
| Descanso compensatorio que suma (TA-FICHA-2) | Judit: descanso compensatorio el 6 nov, confirmado (completa: 4,5 + 3,5 h) | Suma 8 h a las confirmadas (1768 → 1776) y el exceso pasa de 121 a 129 h. Vacaciones y permiso no retribuido siguen sin sumar |
| Baja | Marta: 12–17 mar (jueves a martes) + 9–13 nov | 6 + 5 = 11 días |
| Libre disposición | Clara: 13 nov completo; Rosa: mañana del 18 nov | 1 de 1 (0 restantes); 0,5 de 1 |
| Permiso médico | Laura: 24 nov completo; Núria: tarde del 10 nov | 8 h de 24; 3,5 h de 24 |
| Aviso de octubre | Reloj del navegador el 30 sep / el 1 oct | Sin aviso / «Quedan 12,5 días de vacaciones sin planificar» |
| Resumen de plantilla | Pestaña Fichas, encima del listado; mismo selector PIO / RITA / Ambas; selector de año | Una fila por persona de alta en el año. Columnas ordenables (las cifras empiezan de más a menos). En móvil, tarjetas con «Ordenar por» |
| REAL simulado | `rrhh_real.test.ts` | El resumen solo hace transacciones READ ONLY + ROLLBACK, sin autor ni COMMIT |

## TA-REAL-2: migración 33 (eventos anulados, vacaciones del convenio y días extra)

Esquema nuevo (migración 33, ya en producción):
- `eventos_calendario.anulado` (por defecto false). La unicidad de persona, día y franja solo cuenta los no anulados. La vista de horas ya los excluye.
- `convenio_anual`: `vacaciones_dias_naturales` y `vacaciones_fuente` (obligatoria si hay días).
- `trabajadoras_ajustes_anuales` (TA-REAL-2b, columnas de producción): `id`, `trabajadora_id`, `farmacia`, `anio`, `vacaciones_dias_extra` (≥ 0), `nota`, `anulada`, `created_at`, `updated_at`. **Sin columna autor**: el autor va solo por transacción (`cf.autor`) y un trigger lo lleva a `trabajadores_historial.autor`. Enviar una columna `autor` hace fallar la sentencia; sin `cf.autor`, AUTOR_AUSENTE. Una no anulada por persona y año. Se escribe con `cf_trabajadores_web` (SELECT, INSERT, UPDATE; sin DELETE).

Reglas en la web:
- **Inserción de eventos:** `ON CONFLICT (trabajadora_id, fecha, franja) WHERE NOT anulado DO NOTHING`, en todas las rutas.
- **Goma y deshacer:** anulan (`UPDATE … SET anulado = true`), nunca DELETE. Deshacer un borrado inserta una fila nueva igual a la anulada. Lo confirmado sigue sin tocarse.
- **Lecturas:** toda consulta de eventos excluye los anulados (la de la vista no se filtra: ya los excluye).
- **Convenio:** al crear 2026–2028, 30 días y fuente «decisión de Pío, pendiente de texto publicado». Para las filas ya existentes sin esos datos, «Completar vacaciones del convenio»: `POST /api/rrhh/convenio/vacaciones { "anios": [...] }`, que guarda solo esos dos campos y solo donde faltan.
- **Días extra:** `PUT /api/rrhh/trabajadoras/:id/ajustes/:anio { vacaciones_dias_extra, nota? }` (entero 0–365; nota opcional, máx. 200, sin datos de salud) y `PUT …/ajustes/:anio/anular { "confirmar": true }`. La farmacia es la de la ficha (leída en la misma transacción); el autor, solo `cf.autor` de la transacción. Si la ficha está anulada o no tiene alta ese año: 409. Sin `cf.autor`: AUTOR_AUSENTE con mensaje llano, ROLLBACK y nada guardado.

Fixtures:
- `fixtures/rrhh/ajustes_anuales.json`: Rosa, 2 días extra en 2026; Clara, un ajuste de 2026 anulado.
- `fixtures/rrhh/ficha_anual.json`: unas vacaciones de Rosa (14–18 sep) con `"anulado": true`.
- El convenio de ejemplo trae `vacaciones_dias_naturales` 30 y su fuente en los tres años.

| Caso | Datos | Efecto |
|---|---|---|
| Goma | Aina 9 nov, día completo | 2 franjas anuladas: no se leen y la franja se puede volver a pintar |
| Goma sobre confirmado | Aina 3 nov (semana confirmada) | Sin cambios: 2 franjas confirmadas no se tocan |
| Deshacer un pintado | Pintar en vacío y deshacer | Lo creado queda anulado |
| Deshacer la goma | Borrar una franja y deshacer | Vuelve la franja (en REAL, fila nueva). Si alguien la ha ocupado entre medias: `ESTADO_CAMBIADO`, sin cambios |
| Historial | UPDATE con `anulado` false → true | «Borrado …» |
| Deshacer encadenado (TA-REAL-2c) | Pintar V (4 oct 2027, M) → goma → deshacer → deshacer | Queda vacío. Deshacer la goma crea una fila nueva y la pila de cambios se reasigna a su id (`reasignarIds`), así el deshacer del pintado la encuentra. Igual con 3 niveles mezclando pintar y goma |
| ESTADO_CAMBIADO (TA-REAL-2c) | Tras restaurar, otra sesión cambia el día (otro tipo, confirmado o vacío) | 409, sin cambios. Si el día sigue igual, se deshace |
| Pie de fichas (TA-REAL-2c) | Año 2027 en el selector | «jornada máxima 2027: 1752 h» y la referencia de 2027; en el detalle se resalta el objetivo del año elegido |
| Ausencia anulada de ejemplo | Rosa 14–18 sep | 10 franjas anuladas; ninguna se lee ni cuenta |
| Días extra de ejemplo | Rosa 2026 | 30 del convenio + 2 extra = 32; 32 sin planificar. Resumen: «32 de 32 (2 extra)» |
| Ajuste anulado | Clara 2026 | No cuenta: 30 |
| Editar días extra | Irene: 3 con nota → 1 sin nota → anular | 33 → 31 → 30 |
| Convenio sin vacaciones | Año sin `vacaciones_dias_naturales` | Vacaciones «pendiente», sin regla; aviso gris «Vacaciones de 2026 pendientes: el convenio no tiene los días» |
| Completar vacaciones | Filas 2026 y 2027 sin el dato | Confirmación con los dos datos → POST `{ "anios": [2026, 2027] }`; el resto del convenio no cambia |
| REAL simulado | `rrhh_real.test.ts` con el esquema de la migración 33 en memoria | SQL con `NOT anulado`, ON CONFLICT parcial, sin DELETE, `cf.autor` en cada escritura y ninguna columna `autor`; la base simulada rechaza esa columna (42703) y la falta de `cf.autor` (AUTOR_AUSENTE) |

## TA3: guardias y festivos (FIXTURES; TA3-REAL: también REAL)

En Ulldecona hay 3 farmacias: PIO, RITA y una ajena (OTRA). La guardia semanal rota entre las 3; los festivos tienen su propia rotación. Modelo y reglas en `app/server/rrhh/guardias.ts`:
- **guardia_semana:** lunes (semana de lunes a domingo; una por semana), farmacia PIO|RITA|OTRA, persona de guardia y apoyo del sábado (opcional).
- **festivo:** fecha (una por día), nombre (máx. 60), alta manual; la baja lo anula junto con su guardia.
- **guardia_festivo:** fecha (tiene que ser festivo), farmacia y persona.
- **Reglas:** OTRA sin personas. En PIO/RITA, la persona es de esa farmacia y está de alta los días del servicio (guardia: sábado y domingo; apoyo: sábado; festivo: ese día). El titular puede hacer guardia. El apoyo es distinto de la guardia. La persona de la guardia de un festivo es, por defecto, la de guardia de esa semana si es la misma farmacia; se puede cambiar.
- **Horas fuera de cómputo** (`HORARIO_GUARDIA`, único punto): se registran y no suman en el año. Guardia: sábado 9:00–13:30 y 18:00–20:00 (6,5 h) y domingo 10:00–13:00 (3 h). Apoyo del sábado: 9:00–13:30 (4,5 h). Festivo de guardia: 10:00–13:00 (3 h). Localizada por teléfono (la persona de guardia): sin horas. Criterio provisional, a confirmar: un festivo en sábado o domingo sustituye ese día de la semana de guardia.
- **Calendario:** «Rellenar jornada habitual» salta festivos. Pintar sobre un festivo se permite, con aviso («Ojo: 8 dic (La Inmaculada) es festivo.»).
- **REAL (TA3-REAL, migración 34 en producción):** `guardias_semana`, `guardias_festivo` y `festivos` con `cf_trabajadores_web` (lectura y escritura; detalles abajo). `guardias_farmacia` ya no existe y la web no la lee.

Fixtures: `fixtures/rrhh/guardias.json`.
- Rotación de 2026: 53 semanas, del 29 dic 2025 al 28 dic 2026, PIO → RITA → OTRA; cada farmacia recorre su lista de guardia y apoyo.
- 15 festivos de ejemplo de 2026 (no es el calendario oficial), con guardia propia. El 31 ago queda sin guardia asignada.
- 2027 y 2028, sin guardias.

| Caso | Datos | Efecto |
|---|---|---|
| Banda del año | Semana 9 nov 2026 | PIO, «G: TE · A: AB» (titular de PIO de guardia, Aina de apoyo); OTRA en gris, solo «OTRA» |
| Festivo en el año | 1 ene 2026 | Marcado con PIO, su farmacia de guardia; 31 ago sin guardia |
| Cabecera de semana | 9–15 nov 2026 | «Guardia: Titular de ejemplo · Apoyo sábado: Aina Bosch Ferrer» |
| Semana con festivo | 7–13 dic 2026 | Columna del 8 con «La Inmaculada»; cabecera con su guardia (PIO · Clara) |
| Persona por defecto | Año Nuevo 2026 (`persona: null` en la semilla) | Aina, de guardia esa semana con PIO |
| Festivo que sustituye un domingo | Semana del 26 oct 2026 (Rosa); 1 nov festivo (Laura) | Rosa 6,5 h esa semana; Laura 3 h por el festivo |
| Guardias del año | Aina 2026 | 5 semanas (47,5 h), 4 sábados de apoyo (18 h), 2 festivos (6 h) = 71,5 h fuera de cómputo |
| Cambio de año | Semana del 28 dic 2026 (Sílvia) | Cuenta en 2027 (año del sábado) |
| Rellenar | Semana del 7 dic 2026 | 4 días: el 8 se salta. Diciembre de Irene: 21 días laborables, sin el 8 ni el 25 |
| Reglas | OTRA con persona; persona de otra farmacia; apoyo igual a la guardia | 400 / 409 PERSONA_NO_VALIDA / 400, sin cambios |
| REAL simulado | Estado REAL con guardias | Pestaña de consulta (TA3-4); el calendario muestra las guardias y las 4 herramientas |

TA3-4 (decisión de Marc): las guardias se pintan en el calendario de Trabajadores, no en la pestaña. Sin fixtures nuevos; las pruebas que escriben usan semanas de 2027 y lo deshacen todo.
- **Herramientas** (paleta, junto a los tipos; también en la vista año):
  - Guardia: clic en una persona → guardia de su farmacia toda la semana. Si había guardia de su farmacia, la sustituye; si era de otra farmacia (u OTRA), pregunta antes. Conserva el apoyo si es de la misma farmacia y no es la nueva guardia. En un festivo, pone la guardia del festivo.
  - Apoyo sábado: clic en una persona en el sábado. Solo con guardia de su farmacia esa semana; si no, aviso y nada guardado.
  - Guardia otra farmacia: clic en la cabecera de un día → su semana (o su festivo) pasa a OTRA.
  - Festivo: clic en la cabecera de un día → nombre (≤60) y ámbito (local por defecto).
  - Goma: en una celda, quita eventos como antes; sobre G, A, GF, OTRA o el nombre del festivo, los anula. Dar de baja un festivo pide confirmación y arrastra su guardia.
  - Año: clic en la banda de la semana con Guardia o Apoyo → selector de farmacia, guardia y apoyo. Con OTRA o la goma, actúa sobre la banda. Con «Abrir semana», abre la semana como antes.
- **Marcas** (capa al pie de la celda; no tapan jornada ni ausencias): franja del color de la farmacia toda la semana con «G» el primer día visible; «A» el sábado del apoyo; «GF» en la guardia de festivo; cabecera gris con «OTRA».
- **Deshacer:** una pila de la sesión (sessionStorage de la pestaña) con eventos y guardias. Las guardias se deshacen con sus pasos inversos por lunes o fecha; restaurar tras la goma crea filas nuevas (ids nuevos).
- **Rutas nuevas** (goma): `PUT /api/rrhh/guardias/:lunes/anular` y `PUT /api/rrhh/festivos/:fecha/guardia/anular`, con `{ confirmar: true }`. Anulan; nunca DELETE.
- **Reglas y mensajes:** los de TA3-REAL, comprobados antes de escribir (`herramientas_guardia.ts`); el servidor y la BD los vuelven a aplicar.
- **Pestaña «Guardias y festivos»:** consulta del año, solo lectura, con «Editar en el calendario» (abre la semana).

| Caso | Datos | Efecto |
|---|---|---|
| Guardia | Aina, mié 6 ene 2027 | Guardia PIO 4–10 ene: franja ciruela 7 días, «G» el lunes |
| Apoyo | Elena (media mañana), sáb 9 ene | «A» en su sábado (en la franja vacía de tarde); viernes → «El apoyo se pinta en el sábado» |
| Otra farmacia | Laura (RITA) en esa semana PIO | Confirmación «La semana 4–10 ene 2027 es de PIO (Aina Bosch Ferrer). ¿Sustituirla…?» |
| OTRA | Cabecera del 13 ene | Semana 11–17 ene en gris con «OTRA» |
| Festivo + GF | 19 mar 2027 «Sant Josep», autonómico; Clara | Columna con el nombre; «GF» en Clara; rellenar lo salta |
| Goma del festivo | Sant Josep | Confirmación; deshacer lo vuelve a dar de alta |
| Año | Banda 15 feb 2027, RITA, Laura + Marta | «G: LS · A: MV» |

TA3-REAL (migración 34 en producción). Sin fixtures nuevos; la base simulada de `rrhh_real.test.ts` reproduce las tres tablas.
- **Lecturas:** sin filas anuladas. De los festivos, solo los comunes (`farmacia` null). Nombre = `descripcion`.
- **Editar** (semana y guardia de festivo): anular la fila vigente e insertar la nueva en la misma transacción. Si no cambia nada, no escribe.
- **Baja de un festivo:** `anulado = true`; su guardia la anula la BD. Nunca DELETE. Autor solo por `cf.autor`.
- **Alta de festivo:** común, con ámbito elegible (local por defecto: la BD admite NACIONAL, AUTONOMICO o LOCAL). En FIXTURES también se guarda el ámbito.
- **Reglas de la web (las de la BD):**
  - guardia de alta sábado y domingo; apoyo, de alta el sábado;
  - persona de esa farmacia;
  - guardia de festivo solo en un festivo común.
- **Errores de la BD con mensaje llano:**
  - `PERSONA_NO_VALIDA` (con la fecha) y `NO_ES_FESTIVO`;
  - checks `guardias_semana_*`, `guardias_festivo_*` y `festivos_*`;
  - duplicados de semana, guardia de festivo y festivo;
  - FK de persona de otra farmacia;
  - permiso denegado y RLS.
- **Calendario en REAL:** «Rellenar» salta los festivos comunes; pintar sobre uno avisa.
- **check:real:** recuentos de `guardias_semana`, `guardias_festivo` y `festivos` en lugar de `guardias_farmacia`.

| Caso | Datos (simulados) | Efecto |
|---|---|---|
| Editar semana | 4 ene 2027 PIO, Aina; añadir apoyo Elena | La fila anterior queda anulada y la nueva vigente; una sola transacción |
| Baja de festivo | Reyes 6 ene 2027 con guardia | El festivo queda anulado; su guardia la anula la BD |
| Festivo de una farmacia | 7 ene 2027 solo PIO | No sale en la lista; guardia → «Ese día no es festivo» |
| Duplicado en carrera | `guardias_semana_lunes_unico` | 409: «Esa semana ya tiene guardia… Actualiza y vuelve a intentarlo» |

TA3-2 (decisiones de Marc): se aceptan los tres criterios (el festivo sustituye el día de guardia; la semana cuenta en el año de su sábado; sin eventos). El objetivo anual no descuenta festivos. En vacaciones, un festivo de TA3 dado de alta hace de puente, solo entre días de vacaciones.

| Caso | Datos | Efecto |
|---|---|---|
| Puente de festivo | Vacaciones 24 y 28 dic, 25 festivo | Un periodo de 5 días naturales (24–28) |
| Sin festivo | Mismas fechas sin festivo de alta (o dado de baja) | Dos periodos: 1 + 1 = 2 días (regla anterior) |
| Festivo al borde | Vacaciones 9–11 dic, 8 festivo | No amplía: 3 días |
| Otros tipos | Baja y demás ausencias | No cambian (solo vacaciones) |
| Ficha (Playwright) | Irene: vacaciones 18 y 22 mar 2027, 19 festivo de ejemplo | «5 días» en un solo periodo; tras dar de baja el festivo, 2 periodos |

## H6: pantalla Vencimientos (estados de pago; marcas solo en FIXTURES)

Excepción autorizada por Marc: la web podrá escribir solo en tablas nuevas de marcas de pago y de forma de pago por proveedor (rol propio). Nunca en facturas, vencimientos ni conciliación. Modelo en `app/server/pagos/pagos.ts`; API `/api/pagos/*` en `app/server/pagos/rutas.ts`.
- **Vencimientos:** los 10 de siempre (`dto/vencimientos.json`). Añaden el nombre comercial y el CIF comparable de su factura (consulta `vencimientos`: columnas `proveedor_cif`, nif documental y `proveedor_literal` de `facturas`, sin objetos nuevos). FEDEFARMA (FD-26/04471) no tiene CIF.
- **Semilla** (`fixtures/pagos/pagos.json`):
  - Fecha de referencia de los estados: lunes 16/11/2026. Es propia de esta pantalla; el resto de pantallas sigue con el 02/11/2026 de `generado_at`.
  - Alliance (B00000003): transferencia.
  - Hefame (F30004444): efectivo, cambiado a transferencia el 15/10.
  - Cofares (A00000001): sin configurar, así que domiciliación por defecto.
  - Marca vigente de Hefame (pagada el 09/11, por transferencia).
  - Marca anulada de AL-26-100231 (historial).
- **Estados:** PENDIENTE · VENCIDO_SIN_PAGAR (rojo) · DOMICILIADO_PREVISTO (violeta propio) · PAGADO_MANUAL · PAGADO_BANCO (reservado, sin lógica). Vencido = fecha anterior a hoy.
- **Totales:** cargos menos abonos, en tres grupos:
  - por pagar: sin marca y forma no domiciliada;
  - domiciliado previsto: sin marca y con domiciliación;
  - pagado.

  Los importes pendientes (null) y los de sentido no documentado no suman: se cuentan aparte.
- **REAL:** solo lectura con cf_lectura, sin marcas ni formas. Lo vencido con CIF figura como domiciliado previsto. La escritura responde 503 `H6_PENDIENTE` «Pendiente de tablas en Supabase». Propuesta sin aplicar: `web/docs/propuesta_tablas_h6_pagos.sql`.

| Caso | Datos | Efecto |
|---|---|---|
| Estados (hoy 16/11) | 10 vencimientos | 3 pendientes, 3 vencidos sin pagar (Alliance), 3 domiciliados previstos (Cofares), 1 pagado a mano (Hefame) |
| Sin CIF | FD-26/04471 (19/11) | Forma sin determinar, aviso «sin CIF»; para marcarlo hay que elegir la forma; vencido sería rojo |
| Totales noviembre | Por pagar / domiciliado | 776,96 € / 150 − 45,30 = 104,70 €; 2 importes pendientes y 2 de sentido no documentado fuera |
| Marcar varios | Los 3 vencidos de Alliance | Pagado a mano con la fecha elegida y la forma del proveedor; si alguno ya tiene marca, 409 y no se marca ninguno |
| Confirmar domiciliados | Los 3 de Cofares | Fecha = la de vencimiento, forma domiciliación; solo DOMICILIADO_PREVISTO (otro estado: 409) |
| Anular | Marca de Hefame | Con confirmación; queda anulada en el historial con autor; vuelve a vencido sin pagar |
| Forma por proveedor | Cofares a transferencia | Sus vencidos pasan a rojo; «Volver a por defecto» los devuelve a domiciliado previsto |
| REAL simulado | Sin almacén | 8 domiciliados previstos y 1 abono pendiente de compensar (tras H6-3); botones deshabilitados con «Pendiente de tablas en Supabase» |

H6-3 (decisiones de Marc): abonos y cargos negativos.
- **Abono vencido sin marca:** estado ABONO_PENDIENTE_COMPENSAR («Abono pendiente de compensar», azul), nunca rojo ni domiciliado previsto.
  - Al marcarlo: «compensado / cobrado (marcado a mano)», con COMPENSACION_ABONO por defecto (también sin CIF).
  - «Confirmar domiciliados» no lo incluye.
- **Cargo con importe negativo:** el sentido sigue siendo «Cargo» (regla de Pío). Lleva el aviso «importe negativo: revisar» y queda fuera de los totales, contado aparte con el recuento a la vista.
- **check:real** (solo números): vencimientos de cargo con importe negativo, y abonos (total, vencidos, no vencidos y sin fecha).
- **Fixtures nuevos** (`gen_fixtures.mjs`, `VENCIMIENTOS_H6_3`), con fechas anteriores al 02/11 para no cambiar el «próximo vencimiento» de Facturas ni los próximos de Inicio:
  - V11: CF-2026-55811, −25,00 € «a cuenta» el 31/10 (4.º vencimiento).
  - V12: CF-AB-2026-0912, −20,00 € el 29/10 (2.º vencimiento, ya vencido).
- **Efecto en otras pantallas** (pruebas ajustadas):
  - Inicio: «2 de 4» y «3 de 4».
  - Facturas: F04 «+3».
  - Detalle F04: 4 vencimientos.
  - Detalle F07: 2 abonos.
  - Cashflow: semana del 26/10 con 375 € de cargos y −20 € de abonos.
  - Contrato: abonos −65,30 €.

| Caso | Datos | Efecto |
|---|---|---|
| Abono vencido | V12 (29/10, −20,00 €) | «Abono pendiente de compensar» en azul; no entra en «Confirmar domiciliados» |
| Marcar compensado | V12, forma «la de cada proveedor» | Compensación con abono; «compensado / cobrado (marcado a mano)»; historial «marcó compensado / cobrado» |
| Cargo negativo | V11 (31/10, −25,00 €, Cofares) | Sentido «Cargo», aviso «importe negativo: revisar»; semana del 26/10 y octubre: domiciliado 400 − 20 = 380 €; «1 cargo con importe negativo» |

## H6-4: Vencimientos en calendario (sin fixtures nuevos)

- **Calendario sobre la lista:** vistas Día, Semana, Mes (por defecto) y Año; vista y fecha en la URL (`vista`, `fecha`).
- **Día con pagos:** total = cargos − |abonos| con la regla de totales de H6 (también lo ya pagado). No suman el importe pendiente, el sentido no documentado ni los cargos negativos, que se cuentan aparte («N fuera»). El globo da el nº de pagos.
- **Color del día = peor estado:** vencido sin pagar (rojo) > domiciliado previsto (violeta) > abono pendiente de compensar (azul) > pendiente (neutro) > pagado (verde).
- **Desplegable:** con el cursor o el foco de teclado (flechas, Escape). En pantalla táctil, un toque abre una hoja con «Filtrar la lista a este día».
- **Filtrar la lista:** clic en un día, una semana (columna «Sem.») o un mes (Año, o «Ver este mes en la lista»). Queda en `?cal=dia:AAAA-MM-DD | semana:lunes | mes:AAAA-MM`, visible y quitable. Un valor no válido no filtra.
- **Qué filtros usa el calendario:** todos los de la lista salvo los de fecha.
- **Totales:** sin tarjetas por semana ni por mes; queda la cabecera de totales generales.
- **Lista con las capacidades de Facturas:**
  - pestañas por estado de la factura, con recuento;
  - filtros de proveedor (por CIF; sin CIF, por nombre), sentido, importe, estado de la factura y revisión de Pío;
  - búsqueda también por importe (el del vencimiento o el total de su factura);
  - orden por columna (estado por gravedad).

  Se suman los filtros de H6: periodo (ahora en un selector), estado de pago y forma de pago.
- **Lo que tiene Facturas y aquí no:** fecha de factura y diferencia del motor. No forman parte del contrato `vencimientos`.

| Caso | Datos | Efecto |
|---|---|---|
| Varios pagos el mismo día | 04/11: V01 y V10 (Alliance, 152,37 € cada uno) | Globo 2, 304,74 €, rojo; el desplegable lista los dos y la suma |
| Pagado sin total | 07/11: V07 (Hefame, no documentado, marcado) | Verde, globo 1; la celda dice «sentido no documentado» (H6-5; antes «—» y «1 fuera») |
| Abono no vencido | 21/11: V09 (−45,30 €) | Neutro (pendiente), −45,30 € |
| Semana 44 | 26/10–01/11 | 380,00 € (el cargo negativo del 31/10 fuera) |
| Noviembre | 9 pagos | 881,66 €; 2 importes pendientes y 2 de sentido no documentado fuera; intensidad 4 |
| Octubre | 3 pagos | 380,00 €, violeta; intensidad 2 |
| Pestañas | 12 vencimientos | 6 conciliadas, 5 pendientes de conciliar, 2 en revisión, 3 no revisadas por Pío |

## H6-5: vencidos sin importe en el calendario y resumen del periodo (sin fixtures nuevos)

- **Día con pagos, siempre marcado:** color del peor estado y globo aunque ningún pago sume. Sin total, la celda (y la semana, el mes del año y la vista Día) dice por qué: «importe pendiente» > «importe negativo» > «sentido no documentado»; nunca «—» ni 0. En el desplegable, «importe pendiente» en el pago y en la suma.
- **Periodo visible vacío:** si lo filtrado tiene pagos en otras fechas, aviso «Ningún pago en este periodo con estos filtros; hay N en otras fechas» con «Ir al anterior / al siguiente». Es lo visto en REAL: «Vencido sin pagar» siempre cae antes de hoy y el mes actual salía en blanco.
- **Resumen junto al título** (día, semana, mes o año visible; lo filtrado salvo fechas): Total = Pagado (verde: PAGADO_MANUAL y PAGADO_BANCO) + Domiciliado previsto (violeta: solo DOMICILIADO_PREVISTO, domiciliado ya vencido sin marca) + Falta por pagar (rojo: PENDIENTE, no vencido y de cualquier forma, también domiciliación, + VENCIDO_SIN_PAGAR) − Abonos por compensar (azul: ABONO_PENDIENTE_COMPENSAR, aparte, solo si hay). H6-6 (decisión de Marc, revierte el ajuste de TA3-4): por ESTADO, la misma regla en el resumen y en la cabecera de totales generales (que pasa a «Falta por pagar», «Domiciliado previsto» y «Abonos por compensar»). Cuadra al céntimo; un grupo sin pagos, «—»; con pagos que no suman, «sin importe». Fuera de los totales, con recuento: sin importe, cargos negativos, sentido no documentado.

| Caso | Datos | Efecto |
|---|---|---|
| Noviembre | 9 pagos | Total 881,66 € = — + 150,00 € (domiciliado vencido del 15) + 731,66 € (incluye el abono domiciliado del 21, no vencido); fuera: 2 sin importe · 2 de sentido no documentado |
| Octubre | 3 pagos | 380,00 € = — + 400,00 € + — − 20,00 € (abono V12); fuera: 1 cargo negativo |
| Cabecera (todo) | 12 vencimientos | Falta por pagar 731,66 €; domiciliado previsto 550,00 €; abonos por compensar −20,00 € |
| Domiciliados futuros (REAL simulado, hoy 1/11/2026) | Noviembre sin marcas | Todo en falta por pagar (881,66 €); domiciliado previsto «—»; la cabecera del mes coincide |
| Año 2026 | 12 pagos | 1.261,66 € |
| REAL simulado: vencido sin importe | V08 (Fedefarma, sin CIF, sin importe) movido al 20/10 en la prueba; REAL sin marcas | Con «Vencido sin pagar»: noviembre avisa e «Ir al anterior (20 oct 2026)»; 20/10 rojo, globo 1, «importe pendiente»; resumen: total «importe pendiente», falta por pagar «sin importe», 1 sin importe fuera |
