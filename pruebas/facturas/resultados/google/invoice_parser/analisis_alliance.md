# An?lisis Google Document AI Invoice Parser ? Alliance

An?lisis local de las cuatro respuestas originales. No se realizaron nuevas llamadas a Google, no se normaliz? contra el modelo interno y no se aplicaron reglas de negocio ni inferencias.

## Correspondencia de documentos

| Documento | P?ginas originales | P?ginas Google relativas | Factura esperada | Entidades principales |
|---:|---:|---:|---|---:|
| 1 | 1-3 | 1-3 | `08008428` | 87 |
| 2 | 4-7 | 1-4 | `08008427` | 165 |
| 3 | 8-9 | 1-2 | `08008429` | 18 |
| 4 | 10-11 | 1-2 | `08008430` | 23 |

## Resumen cuantitativo

- Total de campos evaluados: **72** (18 ? 4).
- Correctos: **26**.
- Incorrectos: **10**.
- Ausentes: **6**.
- Parciales: **11**.
- Entidad ambigua: **3**.
- No disponible de forma nativa: **16**.
- Porcentaje de acierto: **36.11%** (`CORRECTO / total`).
- Porcentaje de cobertura: **69.44%** (campos con extracci?n utilizable, aunque pueda ser err?nea, parcial o ambigua, dividido por el total).

## Conclusiones principales

- `invoice_id`, `invoice_date`, `net_amount` y `total_tax_amount` son correctos en las cuatro facturas.
- `total_amount` tambi?n es correcto en las cuatro, pero en la factura 08008428 tiene confianza baja (0,273504) y en 08008427 tambi?n baja (0,441756).
- `supplier_name` es incorrecto en las cuatro: Google devuelve `DUPLICADO`.
- `supplier_tax_id` es correcto pero con confianza baja en 08008428, 08008429 y 08008430. En 08008427 devuelve err?neamente `40901058C`, que es el CIF esperado del destinatario.
- El recargo de equivalencia no aparece como campo independiente. `total_tax_amount` coincide ?nicamente con `iva_total`; por tanto, el recargo no queda incluido ni recuperado. Las entidades `vat` de las dos primeras facturas contienen bases parciales (`555,42` y `1.683,59`) como `vat/amount`, no el desglose esperado.
- No se detect? ninguna entidad `purchase_order`. Los posibles albaranes se fragmentan entre `line_item`, `line_item/product_code`, `line_item/unit_price` y `line_item/amount`, con omisiones y errores OCR.
- En 08008427, `SERVICIO BASICO 31,46` aparece como `line_item` y adem?s el importe `31,46` aparece duplicado en otra l?nea; no se clasifica como ajuste.
- No hay campos err?neos con confianza alta (umbral ?0,80) entre los campos directos evaluados. S? hay errores de estructura: `line_item` padre recibe confianza 1,0 aun cuando sus hijos son incompletos o err?neos.
- Cada factura Alliance tiene un solo vencimiento. La fecha se detecta correctamente, pero el importe no se representa; estas muestras no permiten evaluar vencimientos m?ltiples.

## Resultados por factura

### Factura `08008428` ? p?ginas originales 1-3

| Campo del patr?n | Esperado | Entidad Google | Valor Google | Confianza | Clasificaci?n | Observaci?n |
|---|---|---|---|---:|---|---|
| `tipo_documento` | FACTURA | invoice_type | invoice_statement | 0.60855234 | **INCORRECTO** | Google normaliza invoice_type como invoice_statement, que no coincide literalmente con FACTURA. |
| `categoria` | MERCANCIA | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | No existe entidad nativa observada para la categor?a del patr?n. |
| `requiere_conciliacion_albaranes` | true | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | Indicador interno del patr?n; no se observa entidad nativa. |
| `pagina_inicio` | 1 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango procede de la divisi?n validada, no de una entidad extra?da por Invoice Parser. |
| `pagina_fin` | 3 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango procede de la divisi?n validada, no de una entidad extra?da por Invoice Parser. |
| `proveedor_nombre` | ALLIANCE HEALTHCARE ESPAÑA, S.A. | supplier_name | DUPLICADO | 0.30458418 | **INCORRECTO** | supplier_name contiene DUPLICADO, no el proveedor esperado. |
| `proveedor_cif` | A50004324 | supplier_tax_id | A50004324 | 0.33982456 | **CORRECTO** | Coincidencia literal; confianza baja (<0,50). |
| `numero_factura` | 08008428 | invoice_id | 08008428 | 0.9558247 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `fecha_factura` | 2026-07-10 | invoice_date | 2026-07-10 | 0.93246096 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `base_imponible_total` | 2751.75 | net_amount | 2751.75 | 0.8312698 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `iva_total` | 189.45 | total_tax_amount | 189.45 | 0.8207224 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `importe_total` | 2972.7 | total_amount | 2972.7 | 0.2735038 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. Campo correcto con confianza baja (<0,50). |
| `recargo_equivalencia_total` | 31.5 | ? | null | ? | **AUSENTE** | No hay entidad nativa espec?fica. total_tax_amount coincide solo con iva_total y no contiene el recargo. |
| `vencimientos` | [{"orden":1,"fecha_vencimiento":"2026-09-10","importe":2972.7}] | due_date | {"fechas":["2026-09-10"],"importes":[]} | [0.95724785] | **PARCIAL** | La fecha de vencimiento coincide, pero Google no devuelve el importe del vencimiento. Estas cuatro facturas tienen un solo vencimiento; no permiten evaluar vencimientos m?ltiples. |
| `impuestos` | [] | vat | [{"tipo":"vat","texto":"555,42","valor_normalizado":null,"confianza":1.0,"paginas_relativas":[1],"propiedades_hijas":[{"tipo":"vat/amount","texto":"555,42","valor_normalizado":{"text":"555.42","float_value":555.42},"confianza":0.16292413,"? | [1.0] | **ENTIDAD AMBIGUA** | El patr?n deja impuestos vac?o, pero Google crea una entidad vat cuyo vat/amount es una base parcial, no un desglose fiscal v?lido. |
| `albaranes` | [{"orden":1,"numero_albaran":"08C27029","fecha_albaran":"2026-07-01","tipo_movimiento":"CARGO","descripcion":"PLATAFORMA 360","importe_base":48.45,"importe_total":53.98},{"orden":2,"numero_albaran":"08C27032","fecha_albaran":"2026-07-01","? | line_item | {"albaranes_esperados":92,"identificadores_literales_en_line_item":["08C27899","08M29583","08M29917","08M30064","08C28369","08C28649","08C28657","08C28662","08C28668","08C28813","08C29059","08C29168","08M30656","08M30923","08M31070","08C35? | [1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.? | **PARCIAL** | Google no gener? purchase_order. Algunos posibles albaranes aparecen como line_item/product_code y muchos importes como line_item/amount; no se recupera la estructura completa con n?mero, fecha, movimiento, descripci?n, base y total. |
| `ajustes` | [] | ? | [] | ? | **CORRECTO** | El patr?n no espera ajustes y no se observa una entidad nativa de ajuste asignable. |
| `destinatario` | {"id_farmacia":"PIO","nombre":"FARMACIA PIO PUIG","cif":"40901058C","metodo_identificacion":"CIF"} | receiver_tax_id | {"receiver_tax_id":"006600"} | [0.3277284] | **INCORRECTO** | receiver_tax_id es 006600 y no se detecta receiver_name; ning?n componente exigido del destinatario queda correctamente representado. |

#### Inventario completo de entidades principales

> Las p?ginas de esta tabla son relativas al PDF dividido. Las propiedades hijas se enumeran dentro de su entidad padre.

| # | Tipo | Texto | Normalizado | Confianza | P?gina relativa | Propiedades hijas |
|---:|---|---|---|---:|---|---|
| 1 | `vat` | 555,42 | null | 1.000000 | [1] | vat/amount \| texto=555,42 \| norm={"text":"555.42","float_value":555.42} \| conf=0.162924 \| p?g=[1] |
| 2 | `due_date` | 10-09-2026 | {"text":"2026-09-10","date_value":{"year":2026,"month":9,"day":10}} | 0.957248 | [2] | ? |
| 3 | `invoice_id` | 08008428 | null | 0.955825 | [1] | ? |
| 4 | `invoice_date` | 10-07-2026 | {"text":"2026-07-10","date_value":{"year":2026,"month":7,"day":10}} | 0.932461 | [1] | ? |
| 5 | `net_amount` | 2.751,75 | {"text":"2751.75","float_value":2751.75} | 0.831270 | [1] | ? |
| 6 | `total_tax_amount` | 189,45 | {"text":"189.45","float_value":189.45} | 0.820722 | [1] | ? |
| 7 | `supplier_email` | privacy@cencora.com | null | 0.665872 | [1] | ? |
| 8 | `invoice_type` |  | {"text":"invoice_statement"} | 0.608552 | [1, 2, 3] | ? |
| 9 | `supplier_tax_id` | A50004324 | null | 0.339825 | [1] | ? |
| 10 | `receiver_tax_id` | 006600 | null | 0.327728 | [1] | ? |
| 11 | `supplier_name` | DUPLICADO | null | 0.304584 | [1] | ? |
| 12 | `total_amount` | 2.972,70 | {"text":"2972.7","float_value":2972.7} | 0.273504 | [1] | ? |
| 13 | `supplier_address` | CR SANT LLUC 34 ? 43550 ULLDECONA ? RUTA 16 | null | 0.100470 | [1] | ? |
| 14 | `line_item` | ESPECIALIDAD 687,381 718,31 | null | 1.000000 | [1] | line_item/description \| texto=ESPECIALIDAD \| norm=null \| conf=0.339129 \| p?g=[1]; line_item/amount \| texto=718,31 \| norm={"text":"718.31","float_value":718.31} \| conf=0.753089 \| p?g=[1] |
| 15 | `line_item` | GENERICOS 1.237,99 1.293,70 | null | 1.000000 | [1] | line_item/description \| texto=GENERICOS \| norm=null \| conf=0.326512 \| p?g=[1]; line_item/amount \| texto=1.237,99 \| norm={"text":"1237.99","float_value":1237.99} \| conf=0.700129 \| p?g=[1] |
| 16 | `line_item` | 960,69 | null | 1.000000 | [1] | line_item/amount \| texto=960,69 \| norm={"text":"960.69","float_value":960.69} \| conf=0.644214 \| p?g=[1] |
| 17 | `line_item` | 2.972,70 | null | 1.000000 | [1] | line_item/amount \| texto=2.972,70 \| norm={"text":"2972.7","float_value":2972.7} \| conf=0.362598 \| p?g=[1] |
| 18 | `line_item` | PLATAFORMA 360 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.138356 \| p?g=[2] |
| 19 | `line_item` | PLATAFORMA 360 PLATAFORMA 360 PLATAFORMA 360 PLATAFORMA 360 108M30656 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 ? PLATAFORMA 360 ? PLATAFORMA 360 ? PLATAFORMA 360 \| norm=null \| conf=0.158805 \| p?g=[2]; line_item/product_code \| texto=108M30656 \| norm=null \| conf=0.094178 \| p?g=[2] |
| 20 | `line_item` | PLATAFORMA 360 68,97 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.141300 \| p?g=[2]; line_item/amount \| texto=68,97 \| norm={"text":"68.97","float_value":68.97} \| conf=0.329342 \| p?g=[2] |
| 21 | `line_item` | PLATAFORMA 360 8,37 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.138679 \| p?g=[2]; line_item/amount \| texto=8,37 \| norm={"text":"8.37","float_value":8.37} \| conf=0.348784 \| p?g=[2] |
| 22 | `line_item` | PLATAFORMA 360 5,87 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.144302 \| p?g=[2]; line_item/amount \| texto=5,87 \| norm={"text":"5.87","float_value":5.87} \| conf=0.385990 \| p?g=[2] |
| 23 | `line_item` | PLATAFORMA 360 55,99 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.091562 \| p?g=[2]; line_item/amount \| texto=55,99 \| norm={"text":"55.99","float_value":55.99} \| conf=0.424174 \| p?g=[2] |
| 24 | `line_item` | PLATAFORMA 360 11,06 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.131524 \| p?g=[2]; line_item/amount \| texto=11,06 \| norm={"text":"11.06","float_value":11.06} \| conf=0.412418 \| p?g=[2] |
| 25 | `line_item` | PLATAFORMA 360 11,52 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.144475 \| p?g=[2]; line_item/amount \| texto=11,52 \| norm={"text":"11.52","float_value":11.52} \| conf=0.414112 \| p?g=[2] |
| 26 | `line_item` | PLATAFORMA 360 2,61 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.133288 \| p?g=[2]; line_item/amount \| texto=2,61 \| norm={"text":"2.61","float_value":2.61} \| conf=0.383171 \| p?g=[2] |
| 27 | `line_item` | 45,83 | null | 1.000000 | [2] | line_item/amount \| texto=45,83 \| norm={"text":"45.83","float_value":45.83} \| conf=0.287068 \| p?g=[2] |
| 28 | `line_item` | 8,41 | null | 1.000000 | [2] | line_item/amount \| texto=8,41 \| norm={"text":"8.41","float_value":8.41} \| conf=0.276167 \| p?g=[2] |
| 29 | `line_item` | 65,05 | null | 1.000000 | [2] | line_item/amount \| texto=65,05 \| norm={"text":"65.05","float_value":65.05} \| conf=0.408016 \| p?g=[2] |
| 30 | `line_item` | 83,32 | null | 1.000000 | [2] | line_item/amount \| texto=83,32 \| norm={"text":"83.32","float_value":83.32} \| conf=0.330319 \| p?g=[2] |
| 31 | `line_item` | 108C27899 8,12 | null | 1.000000 | [2] | line_item/product_code \| texto=108C27899 \| norm=null \| conf=0.143413 \| p?g=[2]; line_item/amount \| texto=8,12 \| norm={"text":"8.12","float_value":8.12} \| conf=0.432580 \| p?g=[2] |
| 32 | `line_item` | 08M29583 31,57 | null | 1.000000 | [2] | line_item/product_code \| texto=08M29583 \| norm=null \| conf=0.080276 \| p?g=[2]; line_item/amount \| texto=31,57 \| norm={"text":"31.57","float_value":31.57} \| conf=0.397041 \| p?g=[2] |
| 33 | `line_item` | 08M29917 10,47 | null | 1.000000 | [2] | line_item/product_code \| texto=08M29917 \| norm=null \| conf=0.093129 \| p?g=[2]; line_item/amount \| texto=10,47 \| norm={"text":"10.47","float_value":10.47} \| conf=0.442920 \| p?g=[2] |
| 34 | `line_item` | 08M30064 6,56 6,85 | null | 1.000000 | [2] | line_item/product_code \| texto=08M30064 \| norm=null \| conf=0.112067 \| p?g=[2]; line_item/unit_price \| texto=6,56 \| norm={"text":"6.56","float_value":6.56} \| conf=0.474776 \| p?g=[2]; line_item/amount \| texto=6,85 \| norm={"text":"6.85","float_value":6.85} \| conf=0.584835 \| p?g=[2] |
| 35 | `line_item` | 108C28369 6,721 7,02 | null | 1.000000 | [2] | line_item/product_code \| texto=108C28369 \| norm=null \| conf=0.196316 \| p?g=[2]; line_item/unit_price \| texto=6,721 \| norm=null \| conf=0.461180 \| p?g=[2]; line_item/amount \| texto=7,02 \| norm={"text":"7.02","float_value":7.02} \| conf=0.650411 \| p?g=[2] |
| 36 | `line_item` | 08C28649 34,81 36,37 | null | 1.000000 | [2] | line_item/product_code \| texto=08C28649 \| norm=null \| conf=0.094575 \| p?g=[2]; line_item/unit_price \| texto=34,81 \| norm={"text":"34.81","float_value":34.81} \| conf=0.478084 \| p?g=[2]; line_item/amount \| texto=36,37 \| norm={"text":"36.37","float_value":36.37} \| conf=0.616603 \| p?g=[2] |
| 37 | `line_item` | 108C28657 294,411 307,66 | null | 1.000000 | [2] | line_item/product_code \| texto=108C28657 \| norm=null \| conf=0.221157 \| p?g=[2]; line_item/unit_price \| texto=294,411 \| norm=null \| conf=0.509995 \| p?g=[2]; line_item/amount \| texto=307,66 \| norm={"text":"307.66","float_value":307.66} \| conf=0.737997 \| p?g=[2] |
| 38 | `line_item` | 08C28662 34,51 37,48 | null | 1.000000 | [2] | line_item/product_code \| texto=08C28662 \| norm=null \| conf=0.116685 \| p?g=[2]; line_item/unit_price \| texto=34,51 \| norm={"text":"34.51","float_value":34.51} \| conf=0.479027 \| p?g=[2]; line_item/amount \| texto=37,48 \| norm={"text":"37.48","float_value":37.48} \| conf=0.692523 \| p?g=[2] |
| 39 | `line_item` | 108C28668 220,491 230,41 | null | 1.000000 | [2] | line_item/product_code \| texto=108C28668 \| norm=null \| conf=0.239628 \| p?g=[2]; line_item/unit_price \| texto=220,491 \| norm=null \| conf=0.490124 \| p?g=[2]; line_item/amount \| texto=230,41 \| norm={"text":"230.41","float_value":230.41} \| conf=0.806971 \| p?g=[2] |
| 40 | `line_item` | 08C28813 2,24 2,34 | null | 1.000000 | [2] | line_item/product_code \| texto=08C28813 \| norm=null \| conf=0.110059 \| p?g=[2]; line_item/unit_price \| texto=2,24 \| norm={"text":"2.24","float_value":2.24} \| conf=0.507185 \| p?g=[2]; line_item/amount \| texto=2,34 \| norm={"text":"2.34","float_value":2.34} \| conf=0.703012 \| p?g=[2] |
| 41 | `line_item` | 108C29059 11,421 11,94 | null | 1.000000 | [2] | line_item/product_code \| texto=108C29059 \| norm=null \| conf=0.241178 \| p?g=[2]; line_item/unit_price \| texto=11,421 \| norm=null \| conf=0.486658 \| p?g=[2]; line_item/amount \| texto=11,94 \| norm={"text":"11.94","float_value":11.94} \| conf=0.767947 \| p?g=[2] |
| 42 | `line_item` | 08C29168 1,41 1,48 | null | 1.000000 | [2] | line_item/product_code \| texto=08C29168 \| norm=null \| conf=0.115882 \| p?g=[2]; line_item/unit_price \| texto=1,41 \| norm={"text":"1.41","float_value":1.41} \| conf=0.506269 \| p?g=[2]; line_item/amount \| texto=1,48 \| norm={"text":"1.48","float_value":1.48} \| conf=0.729048 \| p?g=[2] |
| 43 | `line_item` | 9,95 | null | 1.000000 | [2] | line_item/amount \| texto=9,95 \| norm={"text":"9.95","float_value":9.95} \| conf=0.594425 \| p?g=[2] |
| 44 | `line_item` | 108M30923 | null | 1.000000 | [2] | line_item/product_code \| texto=108M30923 \| norm=null \| conf=0.108948 \| p?g=[2] |
| 45 | `line_item` | 108M31070 3,05 | null | 1.000000 | [2] | line_item/product_code \| texto=108M31070 \| norm=null \| conf=0.111464 \| p?g=[2]; line_item/amount \| texto=3,05 \| norm={"text":"3.05","float_value":3.05} \| conf=0.211807 \| p?g=[2] |
| 46 | `line_item` | 7,57 | null | 1.000000 | [2] | line_item/amount \| texto=7,57 \| norm={"text":"7.57","float_value":7.57} \| conf=0.283813 \| p?g=[2] |
| 47 | `line_item` | 24,71 | null | 1.000000 | [2] | line_item/amount \| texto=24,71 \| norm={"text":"24.71","float_value":24.71} \| conf=0.359263 \| p?g=[2] |
| 48 | `line_item` | 104,86 | null | 1.000000 | [2] | line_item/amount \| texto=104,86 \| norm={"text":"104.86","float_value":104.86} \| conf=0.465950 \| p?g=[2] |
| 49 | `line_item` | 20,17 | null | 1.000000 | [2] | line_item/amount \| texto=20,17 \| norm={"text":"20.17","float_value":20.17} \| conf=0.485534 \| p?g=[2] |
| 50 | `line_item` | 28,71 | null | 1.000000 | [2] | line_item/amount \| texto=28,71 \| norm={"text":"28.71","float_value":28.71} \| conf=0.439242 \| p?g=[2] |
| 51 | `line_item` | 67,53 | null | 1.000000 | [2] | line_item/amount \| texto=67,53 \| norm={"text":"67.53","float_value":67.53} \| conf=0.408003 \| p?g=[2] |
| 52 | `line_item` | 53,09 | null | 1.000000 | [2] | line_item/amount \| texto=53,09 \| norm={"text":"53.09","float_value":53.09} \| conf=0.435171 \| p?g=[2] |
| 53 | `line_item` | PLATAFORMA 360 91,52 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.134611 \| p?g=[2]; line_item/amount \| texto=91,52 \| norm={"text":"91.52","float_value":91.52} \| conf=0.489008 \| p?g=[2] |
| 54 | `line_item` | PLATAFORMA 360 27,40 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.153510 \| p?g=[2]; line_item/amount \| texto=27,40 \| norm={"text":"27.4","float_value":27.4} \| conf=0.271093 \| p?g=[2] |
| 55 | `line_item` | PLATAFORMA 360 7,50 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.150933 \| p?g=[2]; line_item/amount \| texto=7,50 \| norm={"text":"7.5","float_value":7.5} \| conf=0.375050 \| p?g=[2] |
| 56 | `line_item` | PLATAFORMA 360 9,20 | null | 1.000000 | [2] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.106369 \| p?g=[2]; line_item/amount \| texto=9,20 \| norm={"text":"9.2","float_value":9.2} \| conf=0.306682 \| p?g=[2] |
| 57 | `line_item` | 27,77 | null | 1.000000 | [3] | line_item/amount \| texto=27,77 \| norm={"text":"27.77","float_value":27.77} \| conf=0.304511 \| p?g=[3] |
| 58 | `line_item` | 24,04 | null | 1.000000 | [3] | line_item/amount \| texto=24,04 \| norm={"text":"24.04","float_value":24.04} \| conf=0.265749 \| p?g=[3] |
| 59 | `line_item` | 9,38 | null | 1.000000 | [3] | line_item/amount \| texto=9,38 \| norm={"text":"9.38","float_value":9.38} \| conf=0.272322 \| p?g=[3] |
| 60 | `line_item` | 47,16 | null | 1.000000 | [3] | line_item/amount \| texto=47,16 \| norm={"text":"47.16","float_value":47.16} \| conf=0.247679 \| p?g=[3] |
| 61 | `line_item` | 24,45 | null | 1.000000 | [3] | line_item/amount \| texto=24,45 \| norm={"text":"24.45","float_value":24.45} \| conf=0.245478 \| p?g=[3] |
| 62 | `line_item` | 11,77 | null | 1.000000 | [3] | line_item/amount \| texto=11,77 \| norm={"text":"11.77","float_value":11.77} \| conf=0.245631 \| p?g=[3] |
| 63 | `line_item` | 43,92 | null | 1.000000 | [3] | line_item/amount \| texto=43,92 \| norm={"text":"43.92","float_value":43.92} \| conf=0.283528 \| p?g=[3] |
| 64 | `line_item` | 92,20 | null | 1.000000 | [3] | line_item/amount \| texto=92,20 \| norm={"text":"92.2","float_value":92.2} \| conf=0.291885 \| p?g=[3] |
| 65 | `line_item` | PLATAFORMA 360 08C35280 13,02 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.225254 \| p?g=[3]; line_item/product_code \| texto=08C35280 \| norm=null \| conf=0.043507 \| p?g=[3]; line_item/amount \| texto=13,02 \| norm={"text":"13.02","float_value":13.02} \| conf=0.501662 \| p?g=[3] |
| 66 | `line_item` | PLATAFORMA 360 7,00 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.162863 \| p?g=[3]; line_item/amount \| texto=7,00 \| norm={"text":"7","float_value":7.0} \| conf=0.431580 \| p?g=[3] |
| 67 | `line_item` | PLATAFORMA 360 17,26 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.160411 \| p?g=[3]; line_item/amount \| texto=17,26 \| norm={"text":"17.26","float_value":17.26} \| conf=0.506605 \| p?g=[3] |
| 68 | `line_item` | PLATAFORMA 360 8,03 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.134955 \| p?g=[3]; line_item/amount \| texto=8,03 \| norm={"text":"8.03","float_value":8.03} \| conf=0.477459 \| p?g=[3] |
| 69 | `line_item` | PLATAFORMA 360 108C36328 56,19 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.171693 \| p?g=[3]; line_item/product_code \| texto=108C36328 \| norm=null \| conf=0.083779 \| p?g=[3]; line_item/amount \| texto=56,19 \| norm={"text":"56.19","float_value":56.19} \| conf=0.503579 \| p?g=[3] |
| 70 | `line_item` | PLATAFORMA 360 89,80 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.184679 \| p?g=[3]; line_item/amount \| texto=89,80 \| norm={"text":"89.8","float_value":89.8} \| conf=0.498564 \| p?g=[3] |
| 71 | `line_item` | PLATAFORMA 360 108C36401 29,59 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.154560 \| p?g=[3]; line_item/product_code \| texto=108C36401 \| norm=null \| conf=0.114043 \| p?g=[3]; line_item/amount \| texto=29,59 \| norm={"text":"29.59","float_value":29.59} \| conf=0.567829 \| p?g=[3] |
| 72 | `line_item` | PLATAFORMA 360 4,34 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.144516 \| p?g=[3]; line_item/amount \| texto=4,34 \| norm={"text":"4.34","float_value":4.34} \| conf=0.459001 \| p?g=[3] |
| 73 | `line_item` | 21,18 | null | 1.000000 | [3] | line_item/amount \| texto=21,18 \| norm={"text":"21.18","float_value":21.18} \| conf=0.542183 \| p?g=[3] |
| 74 | `line_item` | 162,46 | null | 1.000000 | [3] | line_item/amount \| texto=162,46 \| norm={"text":"162.46","float_value":162.46} \| conf=0.513132 \| p?g=[3] |
| 75 | `line_item` | 43,42 | null | 1.000000 | [3] | line_item/amount \| texto=43,42 \| norm={"text":"43.42","float_value":43.42} \| conf=0.524270 \| p?g=[3] |
| 76 | `line_item` | 5,23 | null | 1.000000 | [3] | line_item/amount \| texto=5,23 \| norm={"text":"5.23","float_value":5.23} \| conf=0.354813 \| p?g=[3] |
| 77 | `line_item` | 6,02 | null | 1.000000 | [3] | line_item/amount \| texto=6,02 \| norm={"text":"6.02","float_value":6.02} \| conf=0.329775 \| p?g=[3] |
| 78 | `line_item` | 5,77 | null | 1.000000 | [3] | line_item/amount \| texto=5,77 \| norm={"text":"5.77","float_value":5.77} \| conf=0.332498 \| p?g=[3] |
| 79 | `line_item` | 1,12 | null | 1.000000 | [3] | line_item/amount \| texto=1,12 \| norm={"text":"1.12","float_value":1.12} \| conf=0.302213 \| p?g=[3] |
| 80 | `line_item` | 2,84 | null | 1.000000 | [3] | line_item/amount \| texto=2,84 \| norm={"text":"2.84","float_value":2.84} \| conf=0.299097 \| p?g=[3] |
| 81 | `line_item` | 43,18 | null | 1.000000 | [3] | line_item/amount \| texto=43,18 \| norm={"text":"43.18","float_value":43.18} \| conf=0.265990 \| p?g=[3] |
| 82 | `line_item` | PLATAFORMA 1,12 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA \| norm=null \| conf=0.181058 \| p?g=[3]; line_item/amount \| texto=1,12 \| norm={"text":"1.12","float_value":1.12} \| conf=0.164819 \| p?g=[3] |
| 83 | `line_item` | PLATAFORMA 360 1,89 1,98 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.125287 \| p?g=[3]; line_item/amount \| texto=1,98 \| norm={"text":"1.98","float_value":1.98} \| conf=0.239004 \| p?g=[3] |
| 84 | `line_item` | PLATAFORMA 360 32,911 35,16 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.104995 \| p?g=[3]; line_item/unit_price \| texto=32,911 \| norm=null \| conf=0.417567 \| p?g=[3]; line_item/amount \| texto=35,16 \| norm={"text":"35.16","float_value":35.16} \| conf=0.375983 \| p?g=[3] |
| 85 | `line_item` | PLATAFORMA 360 31,70 37,43 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.143032 \| p?g=[3]; line_item/amount \| texto=37,43 \| norm={"text":"37.43","float_value":37.43} \| conf=0.342759 \| p?g=[3] |
| 86 | `line_item` | PLATAFORMA 360 2,05 2,14 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.094928 \| p?g=[3]; line_item/amount \| texto=2,14 \| norm={"text":"2.14","float_value":2.14} \| conf=0.387050 \| p?g=[3] |
| 87 | `line_item` | PLATAFORMA 360 6,81 7,59 | null | 1.000000 | [3] | line_item/description \| texto=PLATAFORMA 360 \| norm=null \| conf=0.080900 \| p?g=[3]; line_item/amount \| texto=7,59 \| norm={"text":"7.59","float_value":7.59} \| conf=0.418927 \| p?g=[3] |

### Factura `08008427` ? p?ginas originales 4-7

| Campo del patr?n | Esperado | Entidad Google | Valor Google | Confianza | Clasificaci?n | Observaci?n |
|---|---|---|---|---:|---|---|
| `tipo_documento` | FACTURA | invoice_type | invoice_statement | 0.54554015 | **INCORRECTO** | Google normaliza invoice_type como invoice_statement, que no coincide literalmente con FACTURA. |
| `categoria` | MERCANCIA | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | No existe entidad nativa observada para la categor?a del patr?n. |
| `requiere_conciliacion_albaranes` | true | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | Indicador interno del patr?n; no se observa entidad nativa. |
| `pagina_inicio` | 4 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango procede de la divisi?n validada, no de una entidad extra?da por Invoice Parser. |
| `pagina_fin` | 7 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango procede de la divisi?n validada, no de una entidad extra?da por Invoice Parser. |
| `proveedor_nombre` | ALLIANCE HEALTHCARE ESPAÑA, S.A. | supplier_name | DUPLICADO | 0.44475478 | **INCORRECTO** | supplier_name contiene DUPLICADO, no el proveedor esperado. |
| `proveedor_cif` | A50004324 | supplier_tax_id | 40901058C | 0.28589877 | **INCORRECTO** | El identificador no coincide literalmente; en el documento 2 corresponde al CIF del destinatario y est? mal tipado como supplier_tax_id. |
| `numero_factura` | 08008427 | invoice_id | 08008427 | 0.95595187 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `fecha_factura` | 2026-07-10 | invoice_date | 2026-07-10 | 0.9173732 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `base_imponible_total` | 10531.42 | net_amount | 10531.42 | 0.74028355 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `iva_total` | 573.16 | total_tax_amount | 573.16 | 0.73860216 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `importe_total` | 11185.1 | total_amount | 11185.1 | 0.44175568 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. Campo correcto con confianza baja (<0,50). |
| `recargo_equivalencia_total` | 80.52 | ? | null | ? | **AUSENTE** | No hay entidad nativa espec?fica. total_tax_amount coincide solo con iva_total y no contiene el recargo. |
| `vencimientos` | [{"orden":1,"fecha_vencimiento":"2026-10-06","importe":11185.1}] | due_date | {"fechas":["2026-10-06"],"importes":[]} | [0.91471416] | **PARCIAL** | La fecha de vencimiento coincide, pero Google no devuelve el importe del vencimiento. Estas cuatro facturas tienen un solo vencimiento; no permiten evaluar vencimientos m?ltiples. |
| `impuestos` | [] | vat | [{"tipo":"vat","texto":"1.683,59","valor_normalizado":null,"confianza":1.0,"paginas_relativas":[1],"propiedades_hijas":[{"tipo":"vat/amount","texto":"1.683,59","valor_normalizado":{"text":"1683.59","float_value":1683.59},"confianza":0.2375? | [1.0] | **ENTIDAD AMBIGUA** | El patr?n deja impuestos vac?o, pero Google crea una entidad vat cuyo vat/amount es una base parcial, no un desglose fiscal v?lido. |
| `albaranes` | [{"orden":1,"numero_albaran":"08C26499","fecha_albaran":"2026-06-30","tipo_movimiento":"CARGO","descripcion":"NORMAL ACUSTICO","importe_base":1.62,"importe_total":1.69},{"orden":2,"numero_albaran":"08C38230","fecha_albaran":"2026-07-10","t? | line_item | {"albaranes_esperados":147,"identificadores_literales_en_line_item":["08M29915","08M29918","08M29976","08M30003","08M30063","08C28370","08C28452","08C28650","08C28658","08M30914","08C29977","08M32612","08M34323","08M34347","08M34834","08M3? | [1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.? | **PARCIAL** | Google no gener? purchase_order. Algunos posibles albaranes aparecen como line_item/product_code y muchos importes como line_item/amount; no se recupera la estructura completa con n?mero, fecha, movimiento, descripci?n, base y total. |
| `ajustes` | [{"orden":1,"tipo_ajuste":"GASTO","descripcion":"Servicio básico","importe":31.46,"incluido_en_base":true,"incluido_en_total":true}] | line_item | [{"tipo":"line_item","texto":"SERVICIO BASICO 31,46","valor_normalizado":null,"confianza":1.0,"paginas_relativas":[1],"propiedades_hijas":[{"tipo":"line_item/description","texto":"SERVICIO BASICO","valor_normalizado":null,"confianza":0.330? | [1.0,1.0] | **PARCIAL** | Servicio b?sico e importe 31,46 aparecen como line_item, incluso duplicados, pero no como ajuste ni con sus indicadores incluido_en_base/incluido_en_total. |
| `destinatario` | {"id_farmacia":"PIO","nombre":"FARMACIA PIO PUIG","cif":"40901058C","metodo_identificacion":"CIF"} | receiver_tax_id | {"receiver_tax_id":"006600"} | [0.30585188] | **ENTIDAD AMBIGUA** | receiver_tax_id es 006600; el CIF correcto 40901058C aparece clasificado err?neamente como supplier_tax_id. |

#### Inventario completo de entidades principales

> Las p?ginas de esta tabla son relativas al PDF dividido. Las propiedades hijas se enumeran dentro de su entidad padre.

| # | Tipo | Texto | Normalizado | Confianza | P?gina relativa | Propiedades hijas |
|---:|---|---|---|---:|---|---|
| 1 | `vat` | 1.683,59 | null | 1.000000 | [1] | vat/amount \| texto=1.683,59 \| norm={"text":"1683.59","float_value":1683.59} \| conf=0.237511 \| p?g=[1] |
| 2 | `invoice_id` | 08008427 | null | 0.955952 | [1] | ? |
| 3 | `invoice_date` | 10-07-2026 | {"text":"2026-07-10","date_value":{"year":2026,"month":7,"day":10}} | 0.917373 | [1] | ? |
| 4 | `due_date` | 06-10-2026 | {"text":"2026-10-06","date_value":{"year":2026,"month":10,"day":6}} | 0.914714 | [2] | ? |
| 5 | `net_amount` | 10.531,42 | {"text":"10531.42","float_value":10531.42} | 0.740284 | [1] | ? |
| 6 | `total_tax_amount` | 573,16 | {"text":"573.16","float_value":573.16} | 0.738602 | [1] | ? |
| 7 | `supplier_email` | privacy@cencora.com | null | 0.712499 | [4] | ? |
| 8 | `invoice_type` |  | {"text":"invoice_statement"} | 0.545540 | [1, 2, 3, 4] | ? |
| 9 | `supplier_name` | DUPLICADO | null | 0.444755 | [1] | ? |
| 10 | `total_amount` | 11.185,10 | {"text":"11185.1","float_value":11185.1} | 0.441756 | [1] | ? |
| 11 | `receiver_tax_id` | 006600 | null | 0.305852 | [1] | ? |
| 12 | `supplier_tax_id` | 40901058C | null | 0.285899 | [1] | ? |
| 13 | `supplier_address` | CR SANT LLUC 34 ? 43550 ULLDECONA ? RUTA 16 | null | 0.222310 | [1] | ? |
| 14 | `line_item` | ESPECIALIDAD 6.658,52 6.958,15 | null | 1.000000 | [1] | line_item/description \| texto=ESPECIALIDAD \| norm=null \| conf=0.383385 \| p?g=[1]; line_item/amount \| texto=6.658,52 \| norm={"text":"6658.52","float_value":6658.52} \| conf=0.694479 \| p?g=[1] |
| 15 | `line_item` | GENERICOS 736,37 769,50 | null | 1.000000 | [1] | line_item/description \| texto=GENERICOS \| norm=null \| conf=0.415522 \| p?g=[1]; line_item/amount \| texto=769,50 \| norm={"text":"769.5","float_value":769.5} \| conf=0.619543 \| p?g=[1] |
| 16 | `line_item` | NO ESPECIALIDAD 2.220,44 | null | 1.000000 | [1] | line_item/description \| texto=NO ESPECIALIDAD \| norm=null \| conf=0.166703 \| p?g=[1]; line_item/amount \| texto=2.220,44 \| norm={"text":"2220.44","float_value":2220.44} \| conf=0.589768 \| p?g=[1] |
| 17 | `line_item` | 1.153,63 1.205,55 | null | 1.000000 | [1] | line_item/amount \| texto=1.153,63 \| norm={"text":"1153.63","float_value":1153.63} \| conf=0.678222 \| p?g=[1] |
| 18 | `line_item` | SERVICIO BASICO 31,46 | null | 1.000000 | [1] | line_item/description \| texto=SERVICIO BASICO \| norm=null \| conf=0.330496 \| p?g=[1]; line_item/amount \| texto=31,46 \| norm={"text":"31.46","float_value":31.46} \| conf=0.545811 \| p?g=[1] |
| 19 | `line_item` | 11.153,64 | null | 1.000000 | [1] | line_item/amount \| texto=11.153,64 \| norm={"text":"11153.64","float_value":11153.64} \| conf=0.278532 \| p?g=[1] |
| 20 | `line_item` | 5,46 31,46 | null | 1.000000 | [1] | line_item/quantity \| texto=5,46 \| norm={"text":"5.46","float_value":5.46} \| conf=0.099702 \| p?g=[1]; line_item/amount \| texto=31,46 \| norm={"text":"31.46","float_value":31.46} \| conf=0.482098 \| p?g=[1] |
| 21 | `line_item` | 1,69 ABONOS AGRUPADOS 8,66- | null | 1.000000 | [2] | line_item/description \| texto=ABONOS AGRUPADOS \| norm=null \| conf=0.171490 \| p?g=[2]; line_item/amount \| texto=8,66- \| norm={"text":"8.66","float_value":8.66} \| conf=0.359512 \| p?g=[2] |
| 22 | `line_item` | 1,32 ABONOS AGRUPADOS 36,09- | null | 1.000000 | [2] | line_item/description \| texto=ABONOS AGRUPADOS \| norm=null \| conf=0.134159 \| p?g=[2]; line_item/amount \| texto=36,09- \| norm={"text":"36.09","float_value":36.09} \| conf=0.419771 \| p?g=[2] |
| 23 | `line_item` | 127,77 | null | 1.000000 | [2] | line_item/amount \| texto=127,77 \| norm={"text":"127.77","float_value":127.77} \| conf=0.278328 \| p?g=[2] |
| 24 | `line_item` | 733,361 775,24 | null | 1.000000 | [2] | line_item/unit_price \| texto=733,361 \| norm=null \| conf=0.413727 \| p?g=[2]; line_item/amount \| texto=775,24 \| norm={"text":"775.24","float_value":775.24} \| conf=0.298332 \| p?g=[2] |
| 25 | `line_item` | 39,46 | null | 1.000000 | [2] | line_item/amount \| texto=39,46 \| norm={"text":"39.46","float_value":39.46} \| conf=0.259742 \| p?g=[2] |
| 26 | `line_item` | 4,131 4,32 | null | 1.000000 | [2] | line_item/unit_price \| texto=4,131 \| norm=null \| conf=0.426671 \| p?g=[2]; line_item/amount \| texto=4,32 \| norm={"text":"4.32","float_value":4.32} \| conf=0.288471 \| p?g=[2] |
| 27 | `line_item` | 3,36 3,51 | null | 1.000000 | [2] | line_item/unit_price \| texto=3,36 \| norm={"text":"3.36","float_value":3.36} \| conf=0.458191 \| p?g=[2]; line_item/amount \| texto=3,51 \| norm={"text":"3.51","float_value":3.51} \| conf=0.275807 \| p?g=[2] |
| 28 | `line_item` | 103,881 115,72 | null | 1.000000 | [2] | line_item/unit_price \| texto=103,881 \| norm=null \| conf=0.495796 \| p?g=[2]; line_item/amount \| texto=115,72 \| norm={"text":"115.72","float_value":115.72} \| conf=0.407693 \| p?g=[2] |
| 29 | `line_item` | 33,87 37,73 | null | 1.000000 | [2] | line_item/unit_price \| texto=33,87 \| norm={"text":"33.87","float_value":33.87} \| conf=0.475330 \| p?g=[2]; line_item/amount \| texto=37,73 \| norm={"text":"37.73","float_value":37.73} \| conf=0.353354 \| p?g=[2] |
| 30 | `line_item` | 15,031 15,71 | null | 1.000000 | [2] | line_item/unit_price \| texto=15,031 \| norm=null \| conf=0.513182 \| p?g=[2]; line_item/amount \| texto=15,71 \| norm={"text":"15.71","float_value":15.71} \| conf=0.408125 \| p?g=[2] |
| 31 | `line_item` | 8,48 10,70 | null | 1.000000 | [2] | line_item/unit_price \| texto=8,48 \| norm={"text":"8.48","float_value":8.48} \| conf=0.494153 \| p?g=[2]; line_item/amount \| texto=10,70 \| norm={"text":"10.7","float_value":10.7} \| conf=0.345620 \| p?g=[2] |
| 32 | `line_item` | 39,711 41,50 | null | 1.000000 | [2] | line_item/unit_price \| texto=39,711 \| norm=null \| conf=0.520146 \| p?g=[2]; line_item/amount \| texto=41,50 \| norm={"text":"41.5","float_value":41.5} \| conf=0.454137 \| p?g=[2] |
| 33 | `line_item` | 52,29 58,25 | null | 1.000000 | [2] | line_item/unit_price \| texto=52,29 \| norm={"text":"52.29","float_value":52.29} \| conf=0.518981 \| p?g=[2]; line_item/amount \| texto=58,25 \| norm={"text":"58.25","float_value":58.25} \| conf=0.520269 \| p?g=[2] |
| 34 | `line_item` | 08M29915 64,78 | null | 1.000000 | [2] | line_item/product_code \| texto=08M29915 \| norm=null \| conf=0.067041 \| p?g=[2]; line_item/amount \| texto=64,78 \| norm={"text":"64.78","float_value":64.78} \| conf=0.659458 \| p?g=[2] |
| 35 | `line_item` | 08M29918 9,57 | null | 1.000000 | [2] | line_item/product_code \| texto=08M29918 \| norm=null \| conf=0.069029 \| p?g=[2]; line_item/amount \| texto=9,57 \| norm={"text":"9.57","float_value":9.57} \| conf=0.539276 \| p?g=[2] |
| 36 | `line_item` | 108M29976 9,09 | null | 1.000000 | [2] | line_item/product_code \| texto=108M29976 \| norm=null \| conf=0.090026 \| p?g=[2]; line_item/amount \| texto=9,09 \| norm={"text":"9.09","float_value":9.09} \| conf=0.642651 \| p?g=[2] |
| 37 | `line_item` | 08M30003 4,91 | null | 1.000000 | [2] | line_item/product_code \| texto=08M30003 \| norm=null \| conf=0.080943 \| p?g=[2]; line_item/amount \| texto=4,91 \| norm={"text":"4.91","float_value":4.91} \| conf=0.552810 \| p?g=[2] |
| 38 | `line_item` | 108M30063 14,91 | null | 1.000000 | [2] | line_item/product_code \| texto=108M30063 \| norm=null \| conf=0.100371 \| p?g=[2]; line_item/amount \| texto=14,91 \| norm={"text":"14.91","float_value":14.91} \| conf=0.583447 \| p?g=[2] |
| 39 | `line_item` | 08C28370 343,97 362,80 | null | 1.000000 | [2] | line_item/product_code \| texto=08C28370 \| norm=null \| conf=0.078671 \| p?g=[2]; line_item/unit_price \| texto=343,97 \| norm={"text":"343.97","float_value":343.97} \| conf=0.463491 \| p?g=[2]; line_item/amount \| texto=362,80 \| norm={"text":"362.8","float_value":362.8} \| conf=0.593241 \| p?g=[2] |
| 40 | `line_item` | 108C28452 4,62 | null | 1.000000 | [2] | line_item/product_code \| texto=108C28452 \| norm=null \| conf=0.144250 \| p?g=[2]; line_item/amount \| texto=4,62 \| norm={"text":"4.62","float_value":4.62} \| conf=0.618635 \| p?g=[2] |
| 41 | `line_item` | 08C28650 147,38 154,02 | null | 1.000000 | [2] | line_item/product_code \| texto=08C28650 \| norm=null \| conf=0.086621 \| p?g=[2]; line_item/unit_price \| texto=147,38 \| norm={"text":"147.38","float_value":147.38} \| conf=0.467931 \| p?g=[2]; line_item/amount \| texto=154,02 \| norm={"text":"154.02","float_value":154.02} \| conf=0.647963 \| p?g=[2] |
| 42 | `line_item` | 108C28658 9,44 | null | 1.000000 | [2] | line_item/product_code \| texto=108C28658 \| norm=null \| conf=0.163171 \| p?g=[2]; line_item/amount \| texto=9,44 \| norm={"text":"9.44","float_value":9.44} \| conf=0.646168 \| p?g=[2] |
| 43 | `line_item` | 4,44 | null | 1.000000 | [2] | line_item/amount \| texto=4,44 \| norm={"text":"4.44","float_value":4.44} \| conf=0.599023 \| p?g=[2] |
| 44 | `line_item` | 25,84 | null | 1.000000 | [2] | line_item/amount \| texto=25,84 \| norm={"text":"25.84","float_value":25.84} \| conf=0.668828 \| p?g=[2] |
| 45 | `line_item` | 29,15 | null | 1.000000 | [2] | line_item/amount \| texto=29,15 \| norm={"text":"29.15","float_value":29.15} \| conf=0.587977 \| p?g=[2] |
| 46 | `line_item` | 3,17 | null | 1.000000 | [2] | line_item/amount \| texto=3,17 \| norm={"text":"3.17","float_value":3.17} \| conf=0.584193 \| p?g=[2] |
| 47 | `line_item` | 108M30914 168,40 | null | 1.000000 | [2] | line_item/product_code \| texto=108M30914 \| norm=null \| conf=0.090913 \| p?g=[2]; line_item/amount \| texto=168,40 \| norm={"text":"168.4","float_value":168.4} \| conf=0.683288 \| p?g=[2] |
| 48 | `line_item` | 108C29977 256,39 268,17 | null | 1.000000 | [2] | line_item/product_code \| texto=108C29977 \| norm=null \| conf=0.107752 \| p?g=[2]; line_item/unit_price \| texto=256,39 \| norm={"text":"256.39","float_value":256.39} \| conf=0.520754 \| p?g=[2]; line_item/amount \| texto=268,17 \| norm={"text":"268.17","float_value":268.17} \| conf=0.634595 \| p?g=[2] |
| 49 | `line_item` | 19,38 | null | 1.000000 | [2] | line_item/amount \| texto=19,38 \| norm={"text":"19.38","float_value":19.38} \| conf=0.624104 \| p?g=[2] |
| 50 | `line_item` | 2,21 | null | 1.000000 | [2] | line_item/amount \| texto=2,21 \| norm={"text":"2.21","float_value":2.21} \| conf=0.555810 \| p?g=[2] |
| 51 | `line_item` | 9,67 | null | 1.000000 | [2] | line_item/amount \| texto=9,67 \| norm={"text":"9.67","float_value":9.67} \| conf=0.565075 \| p?g=[2] |
| 52 | `line_item` | 213,22 223,46 | null | 1.000000 | [2] | line_item/unit_price \| texto=213,22 \| norm={"text":"213.22","float_value":213.22} \| conf=0.504434 \| p?g=[2]; line_item/amount \| texto=223,46 \| norm={"text":"223.46","float_value":223.46} \| conf=0.618310 \| p?g=[2] |
| 53 | `line_item` | 13,06 | null | 1.000000 | [2] | line_item/amount \| texto=13,06 \| norm={"text":"13.06","float_value":13.06} \| conf=0.632049 \| p?g=[2] |
| 54 | `line_item` | 1,32 | null | 1.000000 | [2] | line_item/amount \| texto=1,32 \| norm={"text":"1.32","float_value":1.32} \| conf=0.609791 \| p?g=[2] |
| 55 | `line_item` | 6,01 | null | 1.000000 | [2] | line_item/amount \| texto=6,01 \| norm={"text":"6.01","float_value":6.01} \| conf=0.590772 \| p?g=[2] |
| 56 | `line_item` | 61,87 | null | 1.000000 | [2] | line_item/amount \| texto=61,87 \| norm={"text":"61.87","float_value":61.87} \| conf=0.483184 \| p?g=[2] |
| 57 | `line_item` | 12,08 | null | 1.000000 | [2] | line_item/amount \| texto=12,08 \| norm={"text":"12.08","float_value":12.08} \| conf=0.520643 \| p?g=[2] |
| 58 | `line_item` | 1,56 | null | 1.000000 | [2] | line_item/amount \| texto=1,56 \| norm={"text":"1.56","float_value":1.56} \| conf=0.506376 \| p?g=[2] |
| 59 | `line_item` | 70,78 | null | 1.000000 | [2] | line_item/amount \| texto=70,78 \| norm={"text":"70.78","float_value":70.78} \| conf=0.285415 \| p?g=[2] |
| 60 | `line_item` | 19,22 | null | 1.000000 | [2] | line_item/amount \| texto=19,22 \| norm={"text":"19.22","float_value":19.22} \| conf=0.292278 \| p?g=[2] |
| 61 | `line_item` | 32,57 | null | 1.000000 | [2] | line_item/amount \| texto=32,57 \| norm={"text":"32.57","float_value":32.57} \| conf=0.307366 \| p?g=[2] |
| 62 | `line_item` | 15,56 | null | 1.000000 | [2] | line_item/amount \| texto=15,56 \| norm={"text":"15.56","float_value":15.56} \| conf=0.314949 \| p?g=[2] |
| 63 | `line_item` | 10,50 | null | 1.000000 | [2] | line_item/amount \| texto=10,50 \| norm={"text":"10.5","float_value":10.5} \| conf=0.386359 \| p?g=[2] |
| 64 | `line_item` | 15,17 | null | 1.000000 | [2] | line_item/amount \| texto=15,17 \| norm={"text":"15.17","float_value":15.17} \| conf=0.255397 \| p?g=[2] |
| 65 | `line_item` | 11,98 | null | 1.000000 | [2] | line_item/amount \| texto=11,98 \| norm={"text":"11.98","float_value":11.98} \| conf=0.276862 \| p?g=[2] |
| 66 | `line_item` | 10,73 | null | 1.000000 | [2] | line_item/amount \| texto=10,73 \| norm={"text":"10.73","float_value":10.73} \| conf=0.312327 \| p?g=[2] |
| 67 | `line_item` | 1,69 | null | 1.000000 | [2] | line_item/amount \| texto=1,69 \| norm={"text":"1.69","float_value":1.69} \| conf=0.470405 \| p?g=[2] |
| 68 | `line_item` | 1,86 | null | 1.000000 | [2] | line_item/amount \| texto=1,86 \| norm={"text":"1.86","float_value":1.86} \| conf=0.438822 \| p?g=[2] |
| 69 | `line_item` | 2,26 | null | 1.000000 | [2] | line_item/amount \| texto=2,26 \| norm={"text":"2.26","float_value":2.26} \| conf=0.523137 \| p?g=[2] |
| 70 | `line_item` | 301,99 318,74 | null | 1.000000 | [2] | line_item/unit_price \| texto=301,99 \| norm={"text":"301.99","float_value":301.99} \| conf=0.488608 \| p?g=[2]; line_item/amount \| texto=318,74 \| norm={"text":"318.74","float_value":318.74} \| conf=0.608627 \| p?g=[2] |
| 71 | `line_item` | 1,72 | null | 1.000000 | [3] | line_item/amount \| texto=1,72 \| norm={"text":"1.72","float_value":1.72} \| conf=0.504300 \| p?g=[3] |
| 72 | `line_item` | 197,13 206,01 | null | 1.000000 | [3] | line_item/unit_price \| texto=197,13 \| norm={"text":"197.13","float_value":197.13} \| conf=0.489295 \| p?g=[3]; line_item/amount \| texto=206,01 \| norm={"text":"206.01","float_value":206.01} \| conf=0.606510 \| p?g=[3] |
| 73 | `line_item` | 89,75 | null | 1.000000 | [3] | line_item/amount \| texto=89,75 \| norm={"text":"89.75","float_value":89.75} \| conf=0.565872 \| p?g=[3] |
| 74 | `line_item` | 8,82 | null | 1.000000 | [3] | line_item/amount \| texto=8,82 \| norm={"text":"8.82","float_value":8.82} \| conf=0.609949 \| p?g=[3] |
| 75 | `line_item` | 60,06 | null | 1.000000 | [3] | line_item/amount \| texto=60,06 \| norm={"text":"60.06","float_value":60.06} \| conf=0.556267 \| p?g=[3] |
| 76 | `line_item` | 168,481 176,06 | null | 1.000000 | [3] | line_item/unit_price \| texto=168,481 \| norm=null \| conf=0.468392 \| p?g=[3]; line_item/amount \| texto=176,06 \| norm={"text":"176.06","float_value":176.06} \| conf=0.660647 \| p?g=[3] |
| 77 | `line_item` | 228,27 238,54 | null | 1.000000 | [3] | line_item/unit_price \| texto=228,27 \| norm={"text":"228.27","float_value":228.27} \| conf=0.452242 \| p?g=[3]; line_item/amount \| texto=238,54 \| norm={"text":"238.54","float_value":238.54} \| conf=0.618857 \| p?g=[3] |
| 78 | `line_item` | 11,48 | null | 1.000000 | [3] | line_item/amount \| texto=11,48 \| norm={"text":"11.48","float_value":11.48} \| conf=0.567599 \| p?g=[3] |
| 79 | `line_item` | 34,25 | null | 1.000000 | [3] | line_item/amount \| texto=34,25 \| norm={"text":"34.25","float_value":34.25} \| conf=0.473850 \| p?g=[3] |
| 80 | `line_item` | 17,13 | null | 1.000000 | [3] | line_item/amount \| texto=17,13 \| norm={"text":"17.13","float_value":17.13} \| conf=0.522804 \| p?g=[3] |
| 81 | `line_item` | 6,42 | null | 1.000000 | [3] | line_item/amount \| texto=6,42 \| norm={"text":"6.42","float_value":6.42} \| conf=0.428568 \| p?g=[3] |
| 82 | `line_item` | 743,49 | null | 1.000000 | [3] | line_item/amount \| texto=743,49 \| norm={"text":"743.49","float_value":743.49} \| conf=0.560503 \| p?g=[3] |
| 83 | `line_item` | 15,21 | null | 1.000000 | [3] | line_item/amount \| texto=15,21 \| norm={"text":"15.21","float_value":15.21} \| conf=0.440896 \| p?g=[3] |
| 84 | `line_item` | 1,41 | null | 1.000000 | [3] | line_item/amount \| texto=1,41 \| norm={"text":"1.41","float_value":1.41} \| conf=0.444987 \| p?g=[3] |
| 85 | `line_item` | 151,51 168,78 | null | 1.000000 | [3] | line_item/unit_price \| texto=151,51 \| norm={"text":"151.51","float_value":151.51} \| conf=0.426739 \| p?g=[3]; line_item/amount \| texto=168,78 \| norm={"text":"168.78","float_value":168.78} \| conf=0.513332 \| p?g=[3] |
| 86 | `line_item` | 27,56 | null | 1.000000 | [3] | line_item/amount \| texto=27,56 \| norm={"text":"27.56","float_value":27.56} \| conf=0.521039 \| p?g=[3] |
| 87 | `line_item` | 68,49 | null | 1.000000 | [3] | line_item/amount \| texto=68,49 \| norm={"text":"68.49","float_value":68.49} \| conf=0.498093 \| p?g=[3] |
| 88 | `line_item` | 38,43 | null | 1.000000 | [3] | line_item/amount \| texto=38,43 \| norm={"text":"38.43","float_value":38.43} \| conf=0.428233 \| p?g=[3] |
| 89 | `line_item` | 5,57 | null | 1.000000 | [3] | line_item/amount \| texto=5,57 \| norm={"text":"5.57","float_value":5.57} \| conf=0.425118 \| p?g=[3] |
| 90 | `line_item` | 5,06 | null | 1.000000 | [3] | line_item/amount \| texto=5,06 \| norm={"text":"5.06","float_value":5.06} \| conf=0.388827 \| p?g=[3] |
| 91 | `line_item` | 10,14 | null | 1.000000 | [3] | line_item/amount \| texto=10,14 \| norm={"text":"10.14","float_value":10.14} \| conf=0.464546 \| p?g=[3] |
| 92 | `line_item` | 6,74 | null | 1.000000 | [3] | line_item/amount \| texto=6,74 \| norm={"text":"6.74","float_value":6.74} \| conf=0.365307 \| p?g=[3] |
| 93 | `line_item` | 44,87 | null | 1.000000 | [3] | line_item/amount \| texto=44,87 \| norm={"text":"44.87","float_value":44.87} \| conf=0.402786 \| p?g=[3] |
| 94 | `line_item` | 19,66 | null | 1.000000 | [3] | line_item/amount \| texto=19,66 \| norm={"text":"19.66","float_value":19.66} \| conf=0.340549 \| p?g=[3] |
| 95 | `line_item` | 37,60 | null | 1.000000 | [3] | line_item/amount \| texto=37,60 \| norm={"text":"37.6","float_value":37.6} \| conf=0.368056 \| p?g=[3] |
| 96 | `line_item` | 104,09 | null | 1.000000 | [3] | line_item/amount \| texto=104,09 \| norm={"text":"104.09","float_value":104.09} \| conf=0.553119 \| p?g=[3] |
| 97 | `line_item` | 108M32612 0,88 | null | 1.000000 | [3] | line_item/product_code \| texto=108M32612 \| norm=null \| conf=0.083345 \| p?g=[3]; line_item/amount \| texto=0,88 \| norm={"text":"0.88","float_value":0.88} \| conf=0.471001 \| p?g=[3] |
| 98 | `line_item` | 61,87 | null | 1.000000 | [3] | line_item/amount \| texto=61,87 \| norm={"text":"61.87","float_value":61.87} \| conf=0.466440 \| p?g=[3] |
| 99 | `line_item` | 196,38 | null | 1.000000 | [3] | line_item/amount \| texto=196,38 \| norm={"text":"196.38","float_value":196.38} \| conf=0.608803 \| p?g=[3] |
| 100 | `line_item` | 9,05 | null | 1.000000 | [3] | line_item/amount \| texto=9,05 \| norm={"text":"9.05","float_value":9.05} \| conf=0.498254 \| p?g=[3] |
| 101 | `line_item` | 36,34 | null | 1.000000 | [3] | line_item/amount \| texto=36,34 \| norm={"text":"36.34","float_value":36.34} \| conf=0.542679 \| p?g=[3] |
| 102 | `line_item` | 8,82 | null | 1.000000 | [3] | line_item/amount \| texto=8,82 \| norm={"text":"8.82","float_value":8.82} \| conf=0.511716 \| p?g=[3] |
| 103 | `line_item` | 103,53 | null | 1.000000 | [3] | line_item/amount \| texto=103,53 \| norm={"text":"103.53","float_value":103.53} \| conf=0.537609 \| p?g=[3] |
| 104 | `line_item` | 38,62 | null | 1.000000 | [3] | line_item/amount \| texto=38,62 \| norm={"text":"38.62","float_value":38.62} \| conf=0.508963 \| p?g=[3] |
| 105 | `line_item` | 11,32 | null | 1.000000 | [3] | line_item/amount \| texto=11,32 \| norm={"text":"11.32","float_value":11.32} \| conf=0.518612 \| p?g=[3] |
| 106 | `line_item` | 504,67 533,10 | null | 1.000000 | [3] | line_item/unit_price \| texto=504,67 \| norm={"text":"504.67","float_value":504.67} \| conf=0.507597 \| p?g=[3]; line_item/amount \| texto=533,10 \| norm={"text":"533.1","float_value":533.1} \| conf=0.552366 \| p?g=[3] |
| 107 | `line_item` | 18,79 21,92 | null | 1.000000 | [3] | line_item/unit_price \| texto=18,79 \| norm={"text":"18.79","float_value":18.79} \| conf=0.518270 \| p?g=[3]; line_item/amount \| texto=21,92 \| norm={"text":"21.92","float_value":21.92} \| conf=0.684036 \| p?g=[3] |
| 108 | `line_item` | 161,55 168,82 | null | 1.000000 | [3] | line_item/unit_price \| texto=161,55 \| norm={"text":"161.55","float_value":161.55} \| conf=0.514343 \| p?g=[3]; line_item/amount \| texto=168,82 \| norm={"text":"168.82","float_value":168.82} \| conf=0.689531 \| p?g=[3] |
| 109 | `line_item` | 2,431 2,54 | null | 1.000000 | [3] | line_item/unit_price \| texto=2,431 \| norm=null \| conf=0.517628 \| p?g=[3]; line_item/amount \| texto=2,54 \| norm={"text":"2.54","float_value":2.54} \| conf=0.623678 \| p?g=[3] |
| 110 | `line_item` | 133,85 139,87 | null | 1.000000 | [3] | line_item/unit_price \| texto=133,85 \| norm={"text":"133.85","float_value":133.85} \| conf=0.550004 \| p?g=[3]; line_item/amount \| texto=139,87 \| norm={"text":"139.87","float_value":139.87} \| conf=0.703562 \| p?g=[3] |
| 111 | `line_item` | 6,411 6,70 | null | 1.000000 | [3] | line_item/unit_price \| texto=6,411 \| norm=null \| conf=0.535544 \| p?g=[3]; line_item/amount \| texto=6,70 \| norm={"text":"6.7","float_value":6.7} \| conf=0.640082 \| p?g=[3] |
| 112 | `line_item` | 128,22 142,77 | null | 1.000000 | [3] | line_item/unit_price \| texto=128,22 \| norm={"text":"128.22","float_value":128.22} \| conf=0.566500 \| p?g=[3]; line_item/amount \| texto=142,77 \| norm={"text":"142.77","float_value":142.77} \| conf=0.712644 \| p?g=[3] |
| 113 | `line_item` | 169,671 177,31 | null | 1.000000 | [3] | line_item/unit_price \| texto=169,671 \| norm=null \| conf=0.559028 \| p?g=[3]; line_item/amount \| texto=177,31 \| norm={"text":"177.31","float_value":177.31} \| conf=0.720749 \| p?g=[3] |
| 114 | `line_item` | 63,68 70,94 | null | 1.000000 | [3] | line_item/unit_price \| texto=63,68 \| norm={"text":"63.68","float_value":63.68} \| conf=0.552525 \| p?g=[3]; line_item/amount \| texto=70,94 \| norm={"text":"70.94","float_value":70.94} \| conf=0.640292 \| p?g=[3] |
| 115 | `line_item` | 25,821 28,76 | null | 1.000000 | [3] | line_item/unit_price \| texto=25,821 \| norm=null \| conf=0.525363 \| p?g=[3]; line_item/amount \| texto=28,76 \| norm={"text":"28.76","float_value":28.76} \| conf=0.694007 \| p?g=[3] |
| 116 | `line_item` | 102,17 106,77 | null | 1.000000 | [3] | line_item/unit_price \| texto=102,17 \| norm={"text":"102.17","float_value":102.17} \| conf=0.580671 \| p?g=[3]; line_item/amount \| texto=106,77 \| norm={"text":"106.77","float_value":106.77} \| conf=0.711702 \| p?g=[3] |
| 117 | `line_item` | 349,70 366,12 | null | 1.000000 | [3] | line_item/unit_price \| texto=349,70 \| norm={"text":"349.7","float_value":349.7} \| conf=0.577496 \| p?g=[3]; line_item/amount \| texto=366,12 \| norm={"text":"366.12","float_value":366.12} \| conf=0.748163 \| p?g=[3] |
| 118 | `line_item` | 13,58 | null | 1.000000 | [3] | line_item/amount \| texto=13,58 \| norm={"text":"13.58","float_value":13.58} \| conf=0.678616 \| p?g=[3] |
| 119 | `line_item` | 13,17 | null | 1.000000 | [3] | line_item/amount \| texto=13,17 \| norm={"text":"13.17","float_value":13.17} \| conf=0.745245 \| p?g=[3] |
| 120 | `line_item` | 1,91 | null | 1.000000 | [3] | line_item/amount \| texto=1,91 \| norm={"text":"1.91","float_value":1.91} \| conf=0.708924 \| p?g=[3] |
| 121 | `line_item` | 297,55 314,75 | null | 1.000000 | [4] | line_item/unit_price \| texto=297,55 \| norm={"text":"297.55","float_value":297.55} \| conf=0.432654 \| p?g=[4]; line_item/amount \| texto=314,75 \| norm={"text":"314.75","float_value":314.75} \| conf=0.499695 \| p?g=[4] |
| 122 | `line_item` | 83,96 90,39 | null | 1.000000 | [4] | line_item/unit_price \| texto=83,96 \| norm={"text":"83.96","float_value":83.96} \| conf=0.450500 \| p?g=[4]; line_item/amount \| texto=90,39 \| norm={"text":"90.39","float_value":90.39} \| conf=0.543864 \| p?g=[4] |
| 123 | `line_item` | 7,60 | null | 1.000000 | [4] | line_item/amount \| texto=7,60 \| norm={"text":"7.6","float_value":7.6} \| conf=0.553654 \| p?g=[4] |
| 124 | `line_item` | 4,03 | null | 1.000000 | [4] | line_item/amount \| texto=4,03 \| norm={"text":"4.03","float_value":4.03} \| conf=0.604932 \| p?g=[4] |
| 125 | `line_item` | 97,79 | null | 1.000000 | [4] | line_item/amount \| texto=97,79 \| norm={"text":"97.79","float_value":97.79} \| conf=0.527026 \| p?g=[4] |
| 126 | `line_item` | 341,091 356,44 | null | 1.000000 | [4] | line_item/unit_price \| texto=341,091 \| norm=null \| conf=0.441493 \| p?g=[4]; line_item/amount \| texto=356,44 \| norm={"text":"356.44","float_value":356.44} \| conf=0.657128 \| p?g=[4] |
| 127 | `line_item` | 6,21 | null | 1.000000 | [4] | line_item/amount \| texto=6,21 \| norm={"text":"6.21","float_value":6.21} \| conf=0.574054 \| p?g=[4] |
| 128 | `line_item` | 1,32 | null | 1.000000 | [4] | line_item/amount \| texto=1,32 \| norm={"text":"1.32","float_value":1.32} \| conf=0.587816 \| p?g=[4] |
| 129 | `line_item` | 4,88 | null | 1.000000 | [4] | line_item/amount \| texto=4,88 \| norm={"text":"4.88","float_value":4.88} \| conf=0.510387 \| p?g=[4] |
| 130 | `line_item` | 22,18 | null | 1.000000 | [4] | line_item/amount \| texto=22,18 \| norm={"text":"22.18","float_value":22.18} \| conf=0.586267 \| p?g=[4] |
| 131 | `line_item` | 11,70 | null | 1.000000 | [4] | line_item/amount \| texto=11,70 \| norm={"text":"11.7","float_value":11.7} \| conf=0.509436 \| p?g=[4] |
| 132 | `line_item` | 23,63 | null | 1.000000 | [4] | line_item/amount \| texto=23,63 \| norm={"text":"23.63","float_value":23.63} \| conf=0.599832 \| p?g=[4] |
| 133 | `line_item` | 72,96 | null | 1.000000 | [4] | line_item/amount \| texto=72,96 \| norm={"text":"72.96","float_value":72.96} \| conf=0.430921 \| p?g=[4] |
| 134 | `line_item` | 43,56 | null | 1.000000 | [4] | line_item/amount \| texto=43,56 \| norm={"text":"43.56","float_value":43.56} \| conf=0.537575 \| p?g=[4] |
| 135 | `line_item` | 08M34323 73,60 | null | 1.000000 | [4] | line_item/product_code \| texto=08M34323 \| norm=null \| conf=0.066251 \| p?g=[4]; line_item/amount \| texto=73,60 \| norm={"text":"73.6","float_value":73.6} \| conf=0.458438 \| p?g=[4] |
| 136 | `line_item` | 108M34347 10,83 | null | 1.000000 | [4] | line_item/product_code \| texto=108M34347 \| norm=null \| conf=0.089965 \| p?g=[4]; line_item/amount \| texto=10,83 \| norm={"text":"10.83","float_value":10.83} \| conf=0.559076 \| p?g=[4] |
| 137 | `line_item` | 08M34834 1,69 | null | 1.000000 | [4] | line_item/product_code \| texto=08M34834 \| norm=null \| conf=0.059598 \| p?g=[4]; line_item/amount \| texto=1,69 \| norm={"text":"1.69","float_value":1.69} \| conf=0.473116 \| p?g=[4] |
| 138 | `line_item` | 108M34837 569,49 | null | 1.000000 | [4] | line_item/product_code \| texto=108M34837 \| norm=null \| conf=0.088344 \| p?g=[4]; line_item/amount \| texto=569,49 \| norm={"text":"569.49","float_value":569.49} \| conf=0.559646 \| p?g=[4] |
| 139 | `line_item` | 08M34838 9,07 | null | 1.000000 | [4] | line_item/product_code \| texto=08M34838 \| norm=null \| conf=0.078294 \| p?g=[4]; line_item/amount \| texto=9,07 \| norm={"text":"9.07","float_value":9.07} \| conf=0.525126 \| p?g=[4] |
| 140 | `line_item` | 108C36031 28,38 | null | 1.000000 | [4] | line_item/product_code \| texto=108C36031 \| norm=null \| conf=0.121768 \| p?g=[4]; line_item/amount \| texto=28,38 \| norm={"text":"28.38","float_value":28.38} \| conf=0.582471 \| p?g=[4] |
| 141 | `line_item` | 08C36225 7,67 | null | 1.000000 | [4] | line_item/product_code \| texto=08C36225 \| norm=null \| conf=0.072478 \| p?g=[4]; line_item/amount \| texto=7,67 \| norm={"text":"7.67","float_value":7.67} \| conf=0.451265 \| p?g=[4] |
| 142 | `line_item` | 108C36245 15,92 | null | 1.000000 | [4] | line_item/product_code \| texto=108C36245 \| norm=null \| conf=0.144791 \| p?g=[4]; line_item/amount \| texto=15,92 \| norm={"text":"15.92","float_value":15.92} \| conf=0.490194 \| p?g=[4] |
| 143 | `line_item` | 08C36330 166,17 | null | 1.000000 | [4] | line_item/product_code \| texto=08C36330 \| norm=null \| conf=0.069964 \| p?g=[4]; line_item/amount \| texto=166,17 \| norm={"text":"166.17","float_value":166.17} \| conf=0.584040 \| p?g=[4] |
| 144 | `line_item` | 08C363351 14,85 | null | 1.000000 | [4] | line_item/product_code \| texto=08C363351 \| norm=null \| conf=0.073337 \| p?g=[4]; line_item/amount \| texto=14,85 \| norm={"text":"14.85","float_value":14.85} \| conf=0.559828 \| p?g=[4] |
| 145 | `line_item` | 08C36624 22,10 | null | 1.000000 | [4] | line_item/product_code \| texto=08C36624 \| norm=null \| conf=0.075524 \| p?g=[4]; line_item/amount \| texto=22,10 \| norm={"text":"22.1","float_value":22.1} \| conf=0.523058 \| p?g=[4] |
| 146 | `line_item` | 32,66 | null | 1.000000 | [4] | line_item/amount \| texto=32,66 \| norm={"text":"32.66","float_value":32.66} \| conf=0.487521 \| p?g=[4] |
| 147 | `line_item` | 2,13 | null | 1.000000 | [4] | line_item/amount \| texto=2,13 \| norm={"text":"2.13","float_value":2.13} \| conf=0.443557 \| p?g=[4] |
| 148 | `line_item` | 10,53 | null | 1.000000 | [4] | line_item/amount \| texto=10,53 \| norm={"text":"10.53","float_value":10.53} \| conf=0.467844 \| p?g=[4] |
| 149 | `line_item` | 10,70 | null | 1.000000 | [4] | line_item/amount \| texto=10,70 \| norm={"text":"10.7","float_value":10.7} \| conf=0.474255 \| p?g=[4] |
| 150 | `line_item` | 2,86 | null | 1.000000 | [4] | line_item/amount \| texto=2,86 \| norm={"text":"2.86","float_value":2.86} \| conf=0.402543 \| p?g=[4] |
| 151 | `line_item` | 132,58 | null | 1.000000 | [4] | line_item/amount \| texto=132,58 \| norm={"text":"132.58","float_value":132.58} \| conf=0.413630 \| p?g=[4] |
| 152 | `line_item` | 43,43 | null | 1.000000 | [4] | line_item/amount \| texto=43,43 \| norm={"text":"43.43","float_value":43.43} \| conf=0.351029 \| p?g=[4] |
| 153 | `line_item` | 87,87 | null | 1.000000 | [4] | line_item/amount \| texto=87,87 \| norm={"text":"87.87","float_value":87.87} \| conf=0.385303 \| p?g=[4] |
| 154 | `line_item` | 16,10 | null | 1.000000 | [4] | line_item/amount \| texto=16,10 \| norm={"text":"16.1","float_value":16.1} \| conf=0.403654 \| p?g=[4] |
| 155 | `line_item` | 16,10 | null | 1.000000 | [4] | line_item/amount \| texto=16,10 \| norm={"text":"16.1","float_value":16.1} \| conf=0.423961 \| p?g=[4] |
| 156 | `line_item` | 12,71 | null | 1.000000 | [4] | line_item/amount \| texto=12,71 \| norm={"text":"12.71","float_value":12.71} \| conf=0.417561 \| p?g=[4] |
| 157 | `line_item` | 19,66 | null | 1.000000 | [4] | line_item/amount \| texto=19,66 \| norm={"text":"19.66","float_value":19.66} \| conf=0.454741 \| p?g=[4] |
| 158 | `line_item` | 156,99 164,05 | null | 1.000000 | [4] | line_item/unit_price \| texto=156,99 \| norm={"text":"156.99","float_value":156.99} \| conf=0.549989 \| p?g=[4]; line_item/amount \| texto=164,05 \| norm={"text":"164.05","float_value":164.05} \| conf=0.491051 \| p?g=[4] |
| 159 | `line_item` | 157,23 164,56 | null | 1.000000 | [4] | line_item/unit_price \| texto=157,23 \| norm={"text":"157.23","float_value":157.23} \| conf=0.584177 \| p?g=[4]; line_item/amount \| texto=164,56 \| norm={"text":"164.56","float_value":164.56} \| conf=0.488990 \| p?g=[4] |
| 160 | `line_item` | 485,73 507,59 | null | 1.000000 | [4] | line_item/unit_price \| texto=485,73 \| norm={"text":"485.73","float_value":485.73} \| conf=0.587997 \| p?g=[4]; line_item/amount \| texto=507,59 \| norm={"text":"507.59","float_value":507.59} \| conf=0.482260 \| p?g=[4] |
| 161 | `line_item` | 18,96 23,49 | null | 1.000000 | [4] | line_item/unit_price \| texto=18,96 \| norm={"text":"18.96","float_value":18.96} \| conf=0.535465 \| p?g=[4]; line_item/amount \| texto=23,49 \| norm={"text":"23.49","float_value":23.49} \| conf=0.488554 \| p?g=[4] |
| 162 | `line_item` | 12,83 13,40 | null | 1.000000 | [4] | line_item/unit_price \| texto=12,83 \| norm={"text":"12.83","float_value":12.83} \| conf=0.462221 \| p?g=[4]; line_item/amount \| texto=13,40 \| norm={"text":"13.4","float_value":13.4} \| conf=0.485816 \| p?g=[4] |
| 163 | `line_item` | 19,63 | null | 1.000000 | [4] | line_item/amount \| texto=19,63 \| norm={"text":"19.63","float_value":19.63} \| conf=0.476941 \| p?g=[4] |
| 164 | `line_item` | 289,53 302,56 | null | 1.000000 | [4] | line_item/unit_price \| texto=289,53 \| norm={"text":"289.53","float_value":289.53} \| conf=0.486358 \| p?g=[4]; line_item/amount \| texto=302,56 \| norm={"text":"302.56","float_value":302.56} \| conf=0.508962 \| p?g=[4] |
| 165 | `line_item` | 2,21 | null | 1.000000 | [4] | line_item/amount \| texto=2,21 \| norm={"text":"2.21","float_value":2.21} \| conf=0.459171 \| p?g=[4] |

### Factura `08008429` ? p?ginas originales 8-9

| Campo del patr?n | Esperado | Entidad Google | Valor Google | Confianza | Clasificaci?n | Observaci?n |
|---|---|---|---|---:|---|---|
| `tipo_documento` | FACTURA | invoice_type | invoice_statement | 0.5478713 | **INCORRECTO** | Google normaliza invoice_type como invoice_statement, que no coincide literalmente con FACTURA. |
| `categoria` | MERCANCIA | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | No existe entidad nativa observada para la categor?a del patr?n. |
| `requiere_conciliacion_albaranes` | true | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | Indicador interno del patr?n; no se observa entidad nativa. |
| `pagina_inicio` | 8 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango procede de la divisi?n validada, no de una entidad extra?da por Invoice Parser. |
| `pagina_fin` | 9 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango procede de la divisi?n validada, no de una entidad extra?da por Invoice Parser. |
| `proveedor_nombre` | ALLIANCE HEALTHCARE ESPAÑA, S.A. | supplier_name | DUPLICADO | 0.4912694 | **INCORRECTO** | supplier_name contiene DUPLICADO, no el proveedor esperado. |
| `proveedor_cif` | A50004324 | supplier_tax_id | A50004324 | 0.27963114 | **CORRECTO** | Coincidencia literal; confianza baja (<0,50). |
| `numero_factura` | 08008429 | invoice_id | 08008429 | 0.96156776 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `fecha_factura` | 2026-07-10 | invoice_date | 2026-07-10 | 0.956217 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `base_imponible_total` | 196.8 | net_amount | 196.8 | 0.82799345 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `iva_total` | 19.68 | total_tax_amount | 19.68 | 0.8606309 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `importe_total` | 219.24 | total_amount | 219.24 | 0.46588823 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. Campo correcto con confianza baja (<0,50). |
| `recargo_equivalencia_total` | 2.76 | ? | null | ? | **AUSENTE** | No hay entidad nativa espec?fica. total_tax_amount coincide solo con iva_total y no contiene el recargo. |
| `vencimientos` | [{"orden":1,"fecha_vencimiento":"2026-10-10","importe":219.24}] | due_date | {"fechas":["2026-10-10"],"importes":[]} | [0.966208] | **PARCIAL** | La fecha de vencimiento coincide, pero Google no devuelve el importe del vencimiento. Estas cuatro facturas tienen un solo vencimiento; no permiten evaluar vencimientos m?ltiples. |
| `impuestos` | [{"orden":1,"base_imponible":196.8,"tipo_iva":10.0,"cuota_iva":19.68,"tipo_recargo_equivalencia":1.4,"cuota_recargo_equivalencia":2.76}] | ? | [] | [] | **AUSENTE** | No se extrajo la estructura vat requerida para bases, tipos, cuotas IVA y recargo. |
| `albaranes` | [{"orden":1,"numero_albaran":"08M30618","fecha_albaran":"2026-07-02","tipo_movimiento":"CARGO","descripcion":"COSTO LABORAT.","importe_base":196.8,"importe_total":219.24}] | line_item | {"albaranes_esperados":1,"identificadores_literales_en_line_item":[],"cantidad_identificadores_literales":0,"purchase_order_detectados":0} | [1.0,1.0,1.0,1.0,1.0] | **PARCIAL** | Google no gener? purchase_order. Algunos posibles albaranes aparecen como line_item/product_code y muchos importes como line_item/amount; no se recupera la estructura completa con n?mero, fecha, movimiento, descripci?n, base y total. |
| `ajustes` | [] | ? | [] | ? | **CORRECTO** | El patr?n no espera ajustes y no se observa una entidad nativa de ajuste asignable. |
| `destinatario` | {"id_farmacia":"PIO","nombre":"FARMACIA PIO PUIG","cif":"40901058C","metodo_identificacion":"CIF"} | receiver_tax_id, receiver_address | {"receiver_tax_id":"40901058C","receiver_address":"CR SANT LLUC 34\n43550 ULLDECONA\nRUTA 16"} | [0.54797137,0.5083552] | **PARCIAL** | receiver_tax_id coincide con el CIF, pero faltan nombre, id_farmacia y metodo_identificacion. |

#### Inventario completo de entidades principales

> Las p?ginas de esta tabla son relativas al PDF dividido. Las propiedades hijas se enumeran dentro de su entidad padre.

| # | Tipo | Texto | Normalizado | Confianza | P?gina relativa | Propiedades hijas |
|---:|---|---|---|---:|---|---|
| 1 | `due_date` | 10-10-2026 | {"text":"2026-10-10","date_value":{"year":2026,"month":10,"day":10}} | 0.966208 | [2] | ? |
| 2 | `invoice_id` | 08008429 | null | 0.961568 | [1] | ? |
| 3 | `invoice_date` | 10-07-2026 | {"text":"2026-07-10","date_value":{"year":2026,"month":7,"day":10}} | 0.956217 | [2] | ? |
| 4 | `total_tax_amount` | 19,68 | {"text":"19.68","float_value":19.68} | 0.860631 | [1] | ? |
| 5 | `net_amount` | 196,80 | {"text":"196.8","float_value":196.8} | 0.827993 | [1] | ? |
| 6 | `supplier_email` | privacy@cencora.com | null | 0.726059 | [2] | ? |
| 7 | `invoice_type` |  | {"text":"invoice_statement"} | 0.547871 | [1, 2] | ? |
| 8 | `receiver_tax_id` | 40901058C | null | 0.547971 | [1] | ? |
| 9 | `receiver_address` | CR SANT LLUC 34 ? 43550 ULLDECONA ? RUTA 16 | null | 0.508355 | [1] | ? |
| 10 | `supplier_name` | DUPLICADO | null | 0.491269 | [2] | ? |
| 11 | `total_amount` | 219,24 | {"text":"219.24","float_value":219.24} | 0.465888 | [1] | ? |
| 12 | `supplier_tax_id` | A50004324 | null | 0.279631 | [1] | ? |
| 13 | `supplier_address` | Pol. Ind. Sector 4 50830 VILLANUEVA | null | 0.072735 | [1] | ? |
| 14 | `line_item` | NO ESPECIALIDAD 219,24 | null | 1.000000 | [1] | line_item/description \| texto=NO ESPECIALIDAD \| norm=null \| conf=0.373290 \| p?g=[1]; line_item/amount \| texto=219,24 \| norm={"text":"219.24","float_value":219.24} \| conf=0.661684 \| p?g=[1] |
| 15 | `line_item` | 4 | null | 1.000000 | [1] | line_item/quantity \| texto=4 \| norm={"text":"4","integer_value":4} \| conf=0.306751 \| p?g=[1] |
| 16 | `line_item` | 4 | null | 1.000000 | [1] | line_item/quantity \| texto=4 \| norm={"text":"4","integer_value":4} \| conf=0.346141 \| p?g=[1] |
| 17 | `line_item` | 219,24 | null | 1.000000 | [1] | line_item/amount \| texto=219,24 \| norm={"text":"219.24","float_value":219.24} \| conf=0.482845 \| p?g=[1] |
| 18 | `line_item` | COSTO LABORAT. 219,24 | null | 1.000000 | [2] | line_item/description \| texto=COSTO LABORAT. \| norm=null \| conf=0.197067 \| p?g=[2]; line_item/amount \| texto=219,24 \| norm={"text":"219.24","float_value":219.24} \| conf=0.268240 \| p?g=[2] |

### Factura `08008430` ? p?ginas originales 10-11

| Campo del patr?n | Esperado | Entidad Google | Valor Google | Confianza | Clasificaci?n | Observaci?n |
|---|---|---|---|---:|---|---|
| `tipo_documento` | FACTURA | invoice_type | invoice_statement | 0.5897861 | **INCORRECTO** | Google normaliza invoice_type como invoice_statement, que no coincide literalmente con FACTURA. |
| `categoria` | MERCANCIA | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | No existe entidad nativa observada para la categor?a del patr?n. |
| `requiere_conciliacion_albaranes` | true | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | Indicador interno del patr?n; no se observa entidad nativa. |
| `pagina_inicio` | 10 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango procede de la divisi?n validada, no de una entidad extra?da por Invoice Parser. |
| `pagina_fin` | 11 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango procede de la divisi?n validada, no de una entidad extra?da por Invoice Parser. |
| `proveedor_nombre` | ALLIANCE HEALTHCARE ESPAÑA, S.A. | supplier_name | DUPLICADO | 0.48707396 | **INCORRECTO** | supplier_name contiene DUPLICADO, no el proveedor esperado. |
| `proveedor_cif` | A50004324 | supplier_tax_id | A50004324 | 0.23898381 | **CORRECTO** | Coincidencia literal; confianza baja (<0,50). |
| `numero_factura` | 08008430 | invoice_id | 08008430 | 0.95710856 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `fecha_factura` | 2026-07-10 | invoice_date | 2026-07-10 | 0.9494001 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `base_imponible_total` | 144.67 | net_amount | 144.67 | 0.82321006 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `iva_total` | 15.59 | total_tax_amount | 15.59 | 0.86836284 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `importe_total` | 162.67 | total_amount | 162.67 | 0.50589347 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `recargo_equivalencia_total` | 2.41 | ? | null | ? | **AUSENTE** | No hay entidad nativa espec?fica. total_tax_amount coincide solo con iva_total y no contiene el recargo. |
| `vencimientos` | [{"orden":1,"fecha_vencimiento":"2026-11-06","importe":162.67}] | due_date | {"fechas":["2026-11-06"],"importes":[]} | [0.9625356] | **PARCIAL** | La fecha de vencimiento coincide, pero Google no devuelve el importe del vencimiento. Estas cuatro facturas tienen un solo vencimiento; no permiten evaluar vencimientos m?ltiples. |
| `impuestos` | [{"orden":1,"base_imponible":134.47,"tipo_iva":10.0,"cuota_iva":13.45,"tipo_recargo_equivalencia":1.4,"cuota_recargo_equivalencia":1.88},{"orden":2,"base_imponible":10.2,"tipo_iva":21.0,"cuota_iva":2.14,"tipo_recargo_equivalencia":5.2,"cuo? | ? | [] | [] | **AUSENTE** | No se extrajo la estructura vat requerida para bases, tipos, cuotas IVA y recargo. |
| `albaranes` | [{"orden":1,"numero_albaran":"08C26323","fecha_albaran":"2026-06-30","tipo_movimiento":"CARGO","descripcion":"ECOCEUTICS","importe_base":19.73,"importe_total":21.98},{"orden":2,"numero_albaran":"08C27758","fecha_albaran":"2026-07-01","tipo? | line_item | {"albaranes_esperados":8,"identificadores_literales_en_line_item":[],"cantidad_identificadores_literales":0,"purchase_order_detectados":0} | [1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0] | **PARCIAL** | Google no gener? purchase_order. Algunos posibles albaranes aparecen como line_item/product_code y muchos importes como line_item/amount; no se recupera la estructura completa con n?mero, fecha, movimiento, descripci?n, base y total. |
| `ajustes` | [] | ? | [] | ? | **CORRECTO** | El patr?n no espera ajustes y no se observa una entidad nativa de ajuste asignable. |
| `destinatario` | {"id_farmacia":"PIO","nombre":"FARMACIA PIO PUIG","cif":"40901058C","metodo_identificacion":"CIF"} | receiver_tax_id, receiver_address | {"receiver_tax_id":"40901058C","receiver_address":"CR SANT LLUC 34\n43550 ULLDECONA\nRUTA 16"} | [0.6016222,0.5190534] | **PARCIAL** | receiver_tax_id coincide con el CIF, pero faltan nombre, id_farmacia y metodo_identificacion. |

#### Inventario completo de entidades principales

> Las p?ginas de esta tabla son relativas al PDF dividido. Las propiedades hijas se enumeran dentro de su entidad padre.

| # | Tipo | Texto | Normalizado | Confianza | P?gina relativa | Propiedades hijas |
|---:|---|---|---|---:|---|---|
| 1 | `due_date` | 06-11-2026 | {"text":"2026-11-06","date_value":{"year":2026,"month":11,"day":6}} | 0.962536 | [2] | ? |
| 2 | `invoice_id` | 08008430 | null | 0.957109 | [1] | ? |
| 3 | `invoice_date` | 10-07-2026 | {"text":"2026-07-10","date_value":{"year":2026,"month":7,"day":10}} | 0.949400 | [1] | ? |
| 4 | `total_tax_amount` | 15,59 | {"text":"15.59","float_value":15.59} | 0.868363 | [1] | ? |
| 5 | `net_amount` | 144,67 | {"text":"144.67","float_value":144.67} | 0.823210 | [1] | ? |
| 6 | `supplier_email` | privacy@cencora.com | null | 0.707997 | [2] | ? |
| 7 | `receiver_tax_id` | 40901058C | null | 0.601622 | [1] | ? |
| 8 | `invoice_type` |  | {"text":"invoice_statement"} | 0.589786 | [1, 2] | ? |
| 9 | `receiver_address` | CR SANT LLUC 34 ? 43550 ULLDECONA ? RUTA 16 | null | 0.519053 | [1] | ? |
| 10 | `total_amount` | 162,67 | {"text":"162.67","float_value":162.67} | 0.505893 | [1] | ? |
| 11 | `supplier_name` | DUPLICADO | null | 0.487074 | [2] | ? |
| 12 | `supplier_tax_id` | A50004324 | null | 0.238984 | [1] | ? |
| 13 | `supplier_address` | Pol. Ind. Sector 4 50830 VILLANUEVA | null | 0.065922 | [1] | ? |
| 14 | `line_item` | NO ESPECIALIDAD 162,67 | null | 1.000000 | [1] | line_item/description \| texto=NO ESPECIALIDAD \| norm=null \| conf=0.254227 \| p?g=[1]; line_item/amount \| texto=162,67 \| norm={"text":"162.67","float_value":162.67} \| conf=0.694164 \| p?g=[1] |
| 15 | `line_item` | 134,47 162,67 | null | 1.000000 | [1] | line_item/amount \| texto=162,67 \| norm={"text":"162.67","float_value":162.67} \| conf=0.725914 \| p?g=[1] |
| 16 | `line_item` | ECOCEUTICS | null | 1.000000 | [2] | line_item/description \| texto=ECOCEUTICS \| norm=null \| conf=0.218151 \| p?g=[2] |
| 17 | `line_item` | ECOCEUTICS | null | 1.000000 | [2] | line_item/description \| texto=ECOCEUTICS \| norm=null \| conf=0.276967 \| p?g=[2] |
| 18 | `line_item` | ECOCEUTICS | null | 1.000000 | [2] | line_item/description \| texto=ECOCEUTICS \| norm=null \| conf=0.274836 \| p?g=[2] |
| 19 | `line_item` | ECOCEUTICS 14,88 | null | 1.000000 | [2] | line_item/description \| texto=ECOCEUTICS \| norm=null \| conf=0.363722 \| p?g=[2]; line_item/amount \| texto=14,88 \| norm={"text":"14.88","float_value":14.88} \| conf=0.368530 \| p?g=[2] |
| 20 | `line_item` | ECOCEUTICS 22,02 | null | 1.000000 | [2] | line_item/description \| texto=ECOCEUTICS \| norm=null \| conf=0.393032 \| p?g=[2]; line_item/amount \| texto=22,02 \| norm={"text":"22.02","float_value":22.02} \| conf=0.420740 \| p?g=[2] |
| 21 | `line_item` | ECOCEUTICS 11,721 13,05 | null | 1.000000 | [2] | line_item/description \| texto=ECOCEUTICS \| norm=null \| conf=0.263494 \| p?g=[2]; line_item/unit_price \| texto=11,721 \| norm=null \| conf=0.478800 \| p?g=[2]; line_item/amount \| texto=13,05 \| norm={"text":"13.05","float_value":13.05} \| conf=0.643041 \| p?g=[2] |
| 22 | `line_item` | ECOCEUTICS 6,75 8,52 | null | 1.000000 | [2] | line_item/description \| texto=ECOCEUTICS \| norm=null \| conf=0.283166 \| p?g=[2]; line_item/unit_price \| texto=6,75 \| norm={"text":"6.75","float_value":6.75} \| conf=0.486586 \| p?g=[2]; line_item/amount \| texto=8,52 \| norm={"text":"8.52","float_value":8.52} \| conf=0.546488 \| p?g=[2] |
| 23 | `line_item` | ECOCEUTICS 16,801 19,23 | null | 1.000000 | [2] | line_item/description \| texto=ECOCEUTICS \| norm=null \| conf=0.421407 \| p?g=[2]; line_item/unit_price \| texto=16,801 \| norm=null \| conf=0.452161 \| p?g=[2]; line_item/amount \| texto=19,23 \| norm={"text":"19.23","float_value":19.23} \| conf=0.642435 \| p?g=[2] |

## Duplicados exactos detectados

Se considera duplicado exacto la repetici?n del mismo tipo, texto detectado y valor normalizado dentro de una respuesta. Esto describe la salida bruta; no se deduplican datos.

| Factura | Nivel | Tipo | Texto | Valor normalizado | Repeticiones |
|---|---|---|---|---|---:|
| `08008428` | hija | `line_item/description` | PLATAFORMA 360 | null | 25 |
| `08008428` | hija | `line_item/amount` | 1,12 | {"float_value":1.12,"text":"1.12"} | 2 |
| `08008427` | hija | `line_item/amount` | 31,46 | {"float_value":31.46,"text":"31.46"} | 2 |
| `08008427` | hija | `line_item/description` | ABONOS AGRUPADOS | null | 2 |
| `08008427` | hija | `line_item/amount` | 10,70 | {"float_value":10.7,"text":"10.7"} | 2 |
| `08008427` | principal | `line_item` | 2,21 | null | 2 |
| `08008427` | hija | `line_item/amount` | 2,21 | {"float_value":2.21,"text":"2.21"} | 2 |
| `08008427` | principal | `line_item` | 1,32 | null | 2 |
| `08008427` | hija | `line_item/amount` | 1,32 | {"float_value":1.32,"text":"1.32"} | 2 |
| `08008427` | principal | `line_item` | 61,87 | null | 2 |
| `08008427` | hija | `line_item/amount` | 61,87 | {"float_value":61.87,"text":"61.87"} | 2 |
| `08008427` | hija | `line_item/amount` | 1,69 | {"float_value":1.69,"text":"1.69"} | 2 |
| `08008427` | principal | `line_item` | 8,82 | null | 2 |
| `08008427` | hija | `line_item/amount` | 8,82 | {"float_value":8.82,"text":"8.82"} | 2 |
| `08008427` | principal | `line_item` | 19,66 | null | 2 |
| `08008427` | hija | `line_item/amount` | 19,66 | {"float_value":19.66,"text":"19.66"} | 2 |
| `08008427` | principal | `line_item` | 16,10 | null | 2 |
| `08008427` | hija | `line_item/amount` | 16,10 | {"float_value":16.1,"text":"16.1"} | 2 |
| `08008429` | hija | `line_item/amount` | 219,24 | {"float_value":219.24,"text":"219.24"} | 3 |
| `08008429` | principal | `line_item` | 4 | null | 2 |
| `08008429` | hija | `line_item/quantity` | 4 | {"integer_value":4,"text":"4"} | 2 |
| `08008430` | hija | `line_item/amount` | 162,67 | {"float_value":162.67,"text":"162.67"} | 2 |
| `08008430` | principal | `line_item` | ECOCEUTICS | null | 3 |
| `08008430` | hija | `line_item/description` | ECOCEUTICS | null | 8 |
## Resultados separados por campo

| Campo | Total | Correcto | Incorrecto | Ausente | Parcial | Ambigua | No nativo |
|---|---:|---:|---:|---:|---:|---:|---:|
| `tipo_documento` | 4 | 0 | 4 | 0 | 0 | 0 | 0 |
| `categoria` | 4 | 0 | 0 | 0 | 0 | 0 | 4 |
| `requiere_conciliacion_albaranes` | 4 | 0 | 0 | 0 | 0 | 0 | 4 |
| `pagina_inicio` | 4 | 0 | 0 | 0 | 0 | 0 | 4 |
| `pagina_fin` | 4 | 0 | 0 | 0 | 0 | 0 | 4 |
| `proveedor_nombre` | 4 | 0 | 4 | 0 | 0 | 0 | 0 |
| `proveedor_cif` | 4 | 3 | 1 | 0 | 0 | 0 | 0 |
| `numero_factura` | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| `fecha_factura` | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| `base_imponible_total` | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| `iva_total` | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| `importe_total` | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| `recargo_equivalencia_total` | 4 | 0 | 0 | 4 | 0 | 0 | 0 |
| `vencimientos` | 4 | 0 | 0 | 0 | 4 | 0 | 0 |
| `impuestos` | 4 | 0 | 0 | 2 | 0 | 2 | 0 |
| `albaranes` | 4 | 0 | 0 | 0 | 4 | 0 | 0 |
| `ajustes` | 4 | 3 | 0 | 0 | 1 | 0 | 0 |
| `destinatario` | 4 | 0 | 1 | 0 | 2 | 1 | 0 |

## Resultados separados por factura

| Factura | P?ginas | Total | Correcto | Incorrecto | Ausente | Parcial | Ambigua | No nativo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `08008428` | 1-3 | 18 | 7 | 3 | 1 | 2 | 1 | 4 |
| `08008427` | 4-7 | 18 | 5 | 3 | 1 | 3 | 2 | 4 |
| `08008429` | 8-9 | 18 | 7 | 2 | 2 | 3 | 0 | 4 |
| `08008430` | 10-11 | 18 | 7 | 2 | 2 | 3 | 0 | 4 |

## Criterio de parada

Este informe es ?nicamente diagn?stico. No se ha creado una normalizaci?n definitiva. Cualquier dise?o de normalizaci?n debe comenzar en una fase posterior y requerir una decisi?n expl?cita.
