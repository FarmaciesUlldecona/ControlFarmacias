# An?lisis Azure prebuilt-invoice ? Alliance

An?lisis local de cuatro respuestas originales contra el patr?n oficial. No se realizaron llamadas, inferencias, correcciones ni normalizaci?n posterior.

## Correspondencia

| Documento | P?ginas originales | P?ginas Azure relativas | Factura esperada | Campos Azure | Items | Tablas |
|---:|---:|---:|---|---:|---:|---:|
| 1 | 1-3 | 1-3 | `08008428` | 12 | 95 | 8 |
| 2 | 4-7 | 1-4 | `08008427` | 12 | 152 | 10 |
| 3 | 8-9 | 1-2 | `08008429` | 13 | 3 | 8 |
| 4 | 10-11 | 1-2 | `08008430` | 13 | 10 | 7 |

## Resumen cuantitativo

- Total: **72** campos (18 ? 4).
- Correctos: **21**.
- Incorrectos: **0**.
- Ausentes: **10**.
- Parciales: **19**.
- Ambiguos: **6**.
- No disponibles nativamente: **16**.
- Acierto estricto: **29.17%**.
- Cobertura: **63.89%**.

## Conclusiones

- `InvoiceId`, `InvoiceDate`, `TotalTax` e `InvoiceTotal` son correctos en las cuatro facturas.
- `SubTotal` es correcto en 08008429 y 08008430; en 08008429 tiene confianza baja (0,414). Est? ausente como campo en las dos facturas grandes, aunque sus tablas conservan el texto `TOTAL BASE IMPONIBLE` y el importe.
- `VendorName` es parcial: devuelve `cencora / Alliance Healthcare`, no la raz?n social literal completa. `VendorTaxId` est? ausente en las cuatro.
- No se observa confusi?n entre proveedor y destinatario en los campos fiscales: `CustomerTaxId` contiene correctamente `40901058C`. El destinatario sigue parcial porque el nombre no coincide literalmente con el patr?n y faltan campos internos.
- El recargo de equivalencia no tiene campo nativo. `TotalTax` coincide solo con IVA; el recargo no est? mezclado. Varias tablas conservan su etiqueta e importe, pero no se convierten mediante reglas.
- `TaxDetails` contiene ?nicamente Amount. En las facturas peque?as faltan bases, tipos y recargo; algunos `Items` clasifican cifras fiscales de forma incorrecta como `Tax` o `TaxRate`.
- Los albaranes aparecen parcialmente como `Items` y ampliamente en tablas. Los ProductCode son muy incompletos: 16 en el primer PDF, 45 en el segundo y ninguno en los dos peque?os.
- El ajuste `SERVICIO BASICO 31,46` se extrae como Item, no como ajuste.
- Cada muestra tiene un ?nico vencimiento: DueDate es correcto, pero falta su importe. No es posible evaluar vencimientos m?ltiples con estas cuatro facturas.
- No hay campos clasificados INCORRECTO y, por tanto, tampoco errores directos con confianza alta. S? existen propiedades de Items incorrectamente tipadas con confianza moderada o alta.

## Comparaci?n directa con Google

| Motor | Correctos | Total | Acierto estricto | Cobertura |
|---|---:|---:|---:|---:|
| Azure prebuilt-invoice | 21 | 72 | 29.17% | 63.89% |
| Google Invoice Parser | 26 | 72 | 36,11% | 69,44% |

Las cifras de Google son las proporcionadas en la solicitud y se usan ?nicamente aqu?; no se abrieron sus respuestas. Bajo este criterio estricto, Google supera a Azure en acierto y cobertura.

## Evaluaci?n por factura

### `08008428` ? p?ginas originales 1-3

| Campo | Esperado | Campo Azure | Valor Azure | Confianza | Clasificaci?n | Observaci?n |
|---|---|---|---|---:|---|---|
| `tipo_documento` | FACTURA | documents[].docType | invoice | 1 | **ENTIDAD AMBIGUA** | docType es invoice: identifica la clase del modelo, pero no devuelve literalmente FACTURA ni acredita distinci?n frente a ABONO. |
| `categoria` | MERCANCIA | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | No existe un campo nativo observado para la categor?a del patr?n. |
| `requiere_conciliacion_albaranes` | true | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | Indicador interno no disponible como campo nativo. |
| `pagina_inicio` | 1 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango original es metadato de la divisi?n, no una entidad extra?da. |
| `pagina_fin` | 3 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango original es metadato de la divisi?n, no una entidad extra?da. |
| `proveedor_nombre` | ALLIANCE HEALTHCARE ESPAÑA, S.A. | VendorName | cencora ? Alliance Healthcare | 0.652 | **PARCIAL** | Azure devuelve la marca cencora / Alliance Healthcare, pero no la raz?n social literal completa esperada. |
| `proveedor_cif` | A50004324 | ? | null | ? | **AUSENTE** | VendorTaxId no fue devuelto; no se toma el CIF desde OCR o tablas por inferencia. |
| `numero_factura` | 08008428 | InvoiceId | 08008428 | 0.938 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `fecha_factura` | 2026-07-10 | InvoiceDate | 2026-07-10 | 0.939 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `base_imponible_total` | 2751.75 | ? | {"texto_en_tabla_sin_campo_nativo":[{"tabla":5,"etiqueta":"TOTAL BASE IMPONIBLE","valor_contiguo":"2.751,75","pagina_relativa":1}]} | ? | **AUSENTE** | SubTotal est? ausente. La tabla conserva etiqueta/importe por OCR, pero no se convierte en campo ni se interpreta mediante reglas. |
| `iva_total` | 189.45 | TotalTax | 189.45 | 0.938 | **CORRECTO** | TotalTax coincide con iva_total; no incluye el recargo de equivalencia. |
| `recargo_equivalencia_total` | 31.5 | ? | {"texto_en_tabla_sin_campo_nativo":[{"tabla":6,"etiqueta":"TOTAL RECARGOS EQUIVALENCIA","valor_contiguo":"31,50","pagina_relativa":1}]} | ? | **AUSENTE** | No hay campo estructurado de recargo. La tabla puede conservar el texto, pero TotalTax contiene solo IVA y no se mezcla con el recargo. |
| `importe_total` | 2972.7 | InvoiceTotal | 2972.7 | 0.938 | **CORRECTO** | Coincidencia num?rica con el patr?n. |
| `vencimientos` | [{"orden":1,"fecha_vencimiento":"2026-09-10","importe":2972.7}] | DueDate | {"fechas":["2026-09-10"],"importes":[]} | 0.937 | **PARCIAL** | DueDate coincide con la ?nica fecha esperada, pero Azure no devuelve el importe del vencimiento. No hay vencimientos m?ltiples en estas cuatro muestras. |
| `impuestos` | [] | TaxDetails | {"nombre_campo":"TaxDetails","tipo":"array","content":null,"valor_normalizado":{},"confianza":null,"paginas_relativas":[],"elementos":[{"indice":1,"content":"TOTAL IVAS\n189,45","confianza":0.86,"paginas_relativas":[1],"propiedades":{"Amount":{"nombre_campo":? | ? | **ENTIDAD AMBIGUA** | El patr?n deja impuestos vac?o, pero TaxDetails contiene ?nicamente el importe total de IVA, sin un desglose fiscal completo. |
| `albaranes` | [{"orden":1,"numero_albaran":"08C27029","fecha_albaran":"2026-07-01","tipo_movimiento":"CARGO","descripcion":"PLATAFORMA 360","importe_base":48.45,"importe_total":53.98},{"orden":2,"numero_albaran":"08C27032","fecha_albaran":"2026-07-01","tipo_movimiento":"CA? | Items y tablas | {"items_detectados":95,"product_codes":["08C27029","08C27032","08C27899","08C28369","08C28649","08C28657","08C28668","08C29059","08C29186","08M30608","08V19089","08C29779","08C29976","08C31637","08C31645","08C32022"],"identificadores_esperados_en_product_code? | ? | **PARCIAL** | Items recupera principalmente fechas e importes y pocos ProductCode; las tablas conservan m?s n?meros, pero no existe una estructura completa y fiable de n?mero, fecha, movimiento, descripci?n, base y total. |
| `ajustes` | [] | ? | [] | ? | **CORRECTO** | El patr?n no espera ajustes y Azure no devuelve un campo espec?fico de ajustes. |
| `destinatario` | {"id_farmacia":"PIO","nombre":"FARMACIA PIO PUIG","cif":"40901058C","metodo_identificacion":"CIF"} | ['CustomerName', 'CustomerTaxId', 'CustomerAddress', 'CustomerAddressRecipient'] | {"CustomerName":{"nombre_campo":"CustomerName","tipo":"string","content":"PUIG SALOMON PIUS","valor_normalizado":{"valueString":"PUIG SALOMON PIUS"},"confianza":0.903,"paginas_relativas":[1]},"CustomerTaxId":{"nombre_campo":"CustomerTaxId","tipo":"string","co? | [0.903,0.664,0.722,0.903] | **PARCIAL** | CustomerTaxId coincide con el CIF esperado, pero CustomerName no coincide literalmente con el nombre del patr?n y faltan id_farmacia y metodo_identificacion. |

#### Inventario completo de campos Azure

> Las p?ginas son relativas al PDF separado. Items y TaxDetails incluyen todas sus propiedades hijas en el JSON; aqu? cada elemento se presenta en una fila compacta.

| Campo/elemento | Tipo | Content | Valor normalizado | Confianza | P?gina relativa |
|---|---|---|---|---:|---|
| `CustomerAddress` | address | CR SANT LLUC 34 ? 43550 ULLDECONA ? RUTA 16 | {"valueAddress":{"houseNumber":"34","road":"CR SANT LLUC","postalCode":"43550","city":"ULLDECONA","streetAddress":"34 CR SANT LLUC"}} | 0.722 | [1] |
| `CustomerAddressRecipient` | string | PUIG SALOMON PIUS | {"valueString":"PUIG SALOMON PIUS"} | 0.903 | [1] |
| `CustomerName` | string | PUIG SALOMON PIUS | {"valueString":"PUIG SALOMON PIUS"} | 0.903 | [1] |
| `CustomerTaxId` | string | 40901058C | {"valueString":"40901058C"} | 0.664 | [1] |
| `DueDate` | date | 10-09-2026 | {"valueDate":"2026-09-10"} | 0.937 | [2] |
| `InvoiceDate` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.939 | [3] |
| `InvoiceId` | string | 08008428 | {"valueString":"08008428"} | 0.938 | [2] |
| `InvoiceTotal` | currency | 2.972,70 | {"valueCurrency":{"amount":2972.7,"currencyCode":"EUR"}} | 0.938 | [1] |
| `Items` | array | None | {} | ? | [] |
| `Items[1].Amount` | currency | 718,31 | {"valueCurrency":{"amount":718.31,"currencyCode":"EUR"}} | 0.918 | [1] |
| `Items[1].Description` | string | ESPECIALIDAD | {"valueString":"ESPECIALIDAD"} | 0.867 | [1] |
| `Items[1].Tax` | currency | 3,44 | {"valueCurrency":{"amount":3.44,"currencyCode":"EUR"}} | 0.511 | [1] |
| `Items[2].Amount` | currency | 1.293,70 | {"valueCurrency":{"amount":1293.7,"currencyCode":"EUR"}} | 0.919 | [1] |
| `Items[2].Description` | string | GENERICOS | {"valueString":"GENERICOS"} | 0.886 | [1] |
| `Items[2].Tax` | currency | 6,19 | {"valueCurrency":{"amount":6.19,"currencyCode":"EUR"}} | 0.49 | [1] |
| `Items[3].Amount` | currency | 960,69 | {"valueCurrency":{"amount":960.69,"currencyCode":"EUR"}} | 0.874 | [1] |
| `Items[3].Description` | string | NO ESPECIALIDAD | {"valueString":"NO ESPECIALIDAD"} | 0.734 | [1] |
| `Items[3].Tax` | currency | 55,54 ? 56,90 | {"valueCurrency":{"amount":56.9,"currencyCode":"EUR"}} | 0.591 | [1] |
| `Items[4].Amount` | currency | 53,98 | {"valueCurrency":{"amount":53.98,"currencyCode":"EUR"}} | 0.798 | [2] |
| `Items[4].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.783 | [2] |
| `Items[4].ProductCode` | string | 08C27029 | {"valueString":"08C27029"} | 0.055 | [2] |
| `Items[5].Amount` | currency | 45,83 | {"valueCurrency":{"amount":45.83,"currencyCode":"EUR"}} | 0.8 | [2] |
| `Items[5].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.8 | [2] |
| `Items[5].ProductCode` | string | 08C27032 | {"valueString":"08C27032"} | 0.06 | [2] |
| `Items[6].Amount` | currency | 8,41 | {"valueCurrency":{"amount":8.41,"currencyCode":"EUR"}} | 0.804 | [2] |
| `Items[6].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.802 | [2] |
| `Items[7].Amount` | currency | 65,05 | {"valueCurrency":{"amount":65.05,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[7].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.79 | [2] |
| `Items[8].Amount` | currency | 83,32 | {"valueCurrency":{"amount":83.32,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[8].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.8 | [2] |
| `Items[9].Amount` | currency | 8,12 | {"valueCurrency":{"amount":8.12,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[9].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.79 | [2] |
| `Items[9].ProductCode` | string | 08C27899 | {"valueString":"08C27899"} | 0.247 | [2] |
| `Items[10].Amount` | currency | 31,57 | {"valueCurrency":{"amount":31.57,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[10].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.763 | [2] |
| `Items[11].Amount` | currency | 10,47 | {"valueCurrency":{"amount":10.47,"currencyCode":"EUR"}} | 0.8 | [2] |
| `Items[11].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.796 | [2] |
| `Items[12].Amount` | currency | 6,85 | {"valueCurrency":{"amount":6.85,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[12].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.778 | [2] |
| `Items[13].Amount` | currency | 7,02 | {"valueCurrency":{"amount":7.02,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[13].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.785 | [2] |
| `Items[13].ProductCode` | string | 08C28369 | {"valueString":"08C28369"} | 0.381 | [2] |
| `Items[14].Amount` | currency | 36,37 | {"valueCurrency":{"amount":36.37,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[14].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.785 | [2] |
| `Items[14].ProductCode` | string | 08C28649 | {"valueString":"08C28649"} | 0.245 | [2] |
| `Items[15].Amount` | currency | 307,66 | {"valueCurrency":{"amount":307.66,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[15].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.787 | [2] |
| `Items[15].ProductCode` | string | 08C28657 | {"valueString":"08C28657"} | 0.274 | [2] |
| `Items[16].Amount` | currency | 37,48 | {"valueCurrency":{"amount":37.48,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[16].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.748 | [2] |
| `Items[17].Amount` | currency | 230,41 | {"valueCurrency":{"amount":230.41,"currencyCode":"EUR"}} | 0.798 | [2] |
| `Items[17].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.77 | [2] |
| `Items[17].ProductCode` | string | 08C28668 | {"valueString":"08C28668"} | 0.063 | [2] |
| `Items[18].Amount` | currency | 2,34 | {"valueCurrency":{"amount":2.34,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[18].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.773 | [2] |
| `Items[19].Amount` | currency | 11,94 | {"valueCurrency":{"amount":11.94,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[19].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.792 | [2] |
| `Items[19].ProductCode` | string | 08C29059 | {"valueString":"08C29059"} | 0.063 | [2] |
| `Items[20].Amount` | currency | 1,48 | {"valueCurrency":{"amount":1.48,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[20].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.757 | [2] |
| `Items[21].Amount` | currency | 9,95 | {"valueCurrency":{"amount":9.95,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[21].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.776 | [2] |
| `Items[21].ProductCode` | string | 08C29186 | {"valueString":"08C29186"} | 0.255 | [2] |
| `Items[22].Amount` | currency | 25,95 | {"valueCurrency":{"amount":25.95,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[22].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.773 | [2] |
| `Items[23].Amount` | currency | 11,56 | {"valueCurrency":{"amount":11.56,"currencyCode":"EUR"}} | 0.8 | [2] |
| `Items[23].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.778 | [2] |
| `Items[24].Amount` | currency | 18,33 | {"valueCurrency":{"amount":18.33,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[24].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.797 | [2] |
| `Items[24].ProductCode` | string | 08M30608 | {"valueString":"08M30608"} | 0.055 | [2] |
| `Items[25].Amount` | currency | 5,86 | {"valueCurrency":{"amount":5.86,"currencyCode":"EUR"}} | 0.803 | [2] |
| `Items[25].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.793 | [2] |
| `Items[26].Amount` | currency | 0,93 | {"valueCurrency":{"amount":0.93,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[26].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.792 | [2] |
| `Items[27].Amount` | currency | 45,47 | {"valueCurrency":{"amount":45.47,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[27].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.795 | [2] |
| `Items[28].Amount` | currency | 2,63 | {"valueCurrency":{"amount":2.63,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[28].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.786 | [2] |
| `Items[29].Amount` | currency | 20,52 | {"valueCurrency":{"amount":20.52,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[29].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.793 | [2] |
| `Items[30].Amount` | currency | 2,46 | {"valueCurrency":{"amount":2.46,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[30].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.787 | [2] |
| `Items[31].Amount` | currency | 3,05 | {"valueCurrency":{"amount":3.05,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[31].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.773 | [2] |
| `Items[32].Amount` | currency | 13,49 | {"valueCurrency":{"amount":13.49,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[32].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.8 | [2] |
| `Items[32].ProductCode` | string | 08V19089 | {"valueString":"08V19089"} | 0.068 | [2] |
| `Items[33].Amount` | currency | 25,41 | {"valueCurrency":{"amount":25.41,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[33].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.768 | [2] |
| `Items[33].ProductCode` | string | 08C29779 | {"valueString":"08C29779"} | 0.245 | [2] |
| `Items[34].Amount` | currency | 74,14 | {"valueCurrency":{"amount":74.14,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[34].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.79 | [2] |
| `Items[35].Amount` | currency | 25,56 | {"valueCurrency":{"amount":25.56,"currencyCode":"EUR"}} | 0.8 | [2] |
| `Items[35].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.788 | [2] |
| `Items[35].ProductCode` | string | 08C29976 | {"valueString":"08C29976"} | 0.065 | [2] |
| `Items[36].Amount` | currency | 7,57 | {"valueCurrency":{"amount":7.57,"currencyCode":"EUR"}} | 0.803 | [2] |
| `Items[36].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.792 | [2] |
| `Items[37].Amount` | currency | 68,97 | {"valueCurrency":{"amount":68.97,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[37].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.796 | [2] |
| `Items[38].Amount` | currency | 24,71 | {"valueCurrency":{"amount":24.71,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[38].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.8 | [2] |
| `Items[39].Amount` | currency | 8,37 | {"valueCurrency":{"amount":8.37,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[39].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.8 | [2] |
| `Items[40].Amount` | currency | 5,87 | {"valueCurrency":{"amount":5.87,"currencyCode":"EUR"}} | 0.803 | [2] |
| `Items[40].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.797 | [2] |
| `Items[41].Amount` | currency | 104,86 | {"valueCurrency":{"amount":104.86,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[41].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.763 | [2] |
| `Items[42].Amount` | currency | 55,99 | {"valueCurrency":{"amount":55.99,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[42].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.794 | [2] |
| `Items[43].Amount` | currency | 11,06 | {"valueCurrency":{"amount":11.06,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[43].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.8 | [2] |
| `Items[44].Amount` | currency | 11,52 | {"valueCurrency":{"amount":11.52,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[44].Date` | date | 05-07-2026 | {"valueDate":"2026-07-05"} | 0.801 | [2] |
| `Items[44].ProductCode` | string | 08C31637 | {"valueString":"08C31637"} | 0.059 | [2] |
| `Items[45].Amount` | currency | 2,61 | {"valueCurrency":{"amount":2.61,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[45].Date` | date | 05-07-2026 | {"valueDate":"2026-07-05"} | 0.801 | [2] |
| `Items[46].Amount` | currency | 20,17 | {"valueCurrency":{"amount":20.17,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[46].Date` | date | 05-07-2026 | {"valueDate":"2026-07-05"} | 0.802 | [2] |
| `Items[46].ProductCode` | string | 08C31645 | {"valueString":"08C31645"} | 0.056 | [2] |
| `Items[47].Amount` | currency | 28,71 | {"valueCurrency":{"amount":28.71,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[47].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.802 | [2] |
| `Items[47].ProductCode` | string | 08C32022 | {"valueString":"08C32022"} | 0.054 | [2] |
| `Items[48].Amount` | currency | 67,53 | {"valueCurrency":{"amount":67.53,"currencyCode":"EUR"}} | 0.803 | [2] |
| `Items[48].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.801 | [2] |
| `Items[49].Amount` | currency | 53,09 | {"valueCurrency":{"amount":53.09,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[49].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.8 | [2] |
| `Items[50].Amount` | currency | 91,52 | {"valueCurrency":{"amount":91.52,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[50].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.779 | [2] |
| `Items[51].Amount` | currency | 27,40 | {"valueCurrency":{"amount":27.4,"currencyCode":"EUR"}} | 0.801 | [2] |
| `Items[51].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.794 | [2] |
| `Items[52].Amount` | currency | 7,50 | {"valueCurrency":{"amount":7.5,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[52].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.8 | [2] |
| `Items[53].Amount` | currency | 9,20 | {"valueCurrency":{"amount":9.2,"currencyCode":"EUR"}} | 0.802 | [2] |
| `Items[53].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.801 | [2] |
| `Items[54].Amount` | currency | 27,77 | {"valueCurrency":{"amount":27.77,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[54].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.848 | [3] |
| `Items[55].Amount` | currency | 24,04 | {"valueCurrency":{"amount":24.04,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[55].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.852 | [3] |
| `Items[56].Amount` | currency | 2,78 | {"valueCurrency":{"amount":2.78,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[56].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.852 | [3] |
| `Items[57].Amount` | currency | 9,38 | {"valueCurrency":{"amount":9.38,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[57].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.852 | [3] |
| `Items[58].Amount` | currency | 53,91 | {"valueCurrency":{"amount":53.91,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[58].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.852 | [3] |
| `Items[59].Amount` | currency | 47,16 | {"valueCurrency":{"amount":47.16,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[59].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.852 | [3] |
| `Items[60].Amount` | currency | 23,45 | {"valueCurrency":{"amount":23.45,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[60].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.836 | [3] |
| `Items[61].Amount` | currency | 22,15 | {"valueCurrency":{"amount":22.15,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[61].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.849 | [3] |
| `Items[62].Amount` | currency | 12,63 | {"valueCurrency":{"amount":12.63,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[62].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.843 | [3] |
| `Items[63].Amount` | currency | 24,45 | {"valueCurrency":{"amount":24.45,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[63].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.847 | [3] |
| `Items[64].Amount` | currency | 4,69 | {"valueCurrency":{"amount":4.69,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[64].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.848 | [3] |
| `Items[65].Amount` | currency | 11,77 | {"valueCurrency":{"amount":11.77,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[65].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.845 | [3] |
| `Items[66].Amount` | currency | 11,20 | {"valueCurrency":{"amount":11.2,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[66].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.834 | [3] |
| `Items[67].Amount` | currency | 43,92 | {"valueCurrency":{"amount":43.92,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[67].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.845 | [3] |
| `Items[68].Amount` | currency | 92,20 | {"valueCurrency":{"amount":92.2,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[68].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.833 | [3] |
| `Items[69].Amount` | currency | 13,02 | {"valueCurrency":{"amount":13.02,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[69].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.839 | [3] |
| `Items[70].Amount` | currency | 7,00 | {"valueCurrency":{"amount":7.0,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[70].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.837 | [3] |
| `Items[71].Amount` | currency | 21,18 | {"valueCurrency":{"amount":21.18,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[71].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.84 | [3] |
| `Items[72].Amount` | currency | 162,46 | {"valueCurrency":{"amount":162.46,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[72].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.836 | [3] |
| `Items[73].Amount` | currency | 17,26 | {"valueCurrency":{"amount":17.26,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[73].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.832 | [3] |
| `Items[74].Amount` | currency | 8,03 | {"valueCurrency":{"amount":8.03,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[74].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.839 | [3] |
| `Items[75].Amount` | currency | 56,19 | {"valueCurrency":{"amount":56.19,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[75].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.851 | [3] |
| `Items[76].Amount` | currency | 89,80 | {"valueCurrency":{"amount":89.8,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[76].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.83 | [3] |
| `Items[77].Amount` | currency | 29,59 | {"valueCurrency":{"amount":29.59,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[77].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.849 | [3] |
| `Items[78].Amount` | currency | 4,34 | {"valueCurrency":{"amount":4.34,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[78].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.845 | [3] |
| `Items[79].Amount` | currency | 43,42 | {"valueCurrency":{"amount":43.42,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[79].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.852 | [3] |
| `Items[80].Amount` | currency | 5,23 | {"valueCurrency":{"amount":5.23,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[80].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.851 | [3] |
| `Items[81].Amount` | currency | 6,02 | {"valueCurrency":{"amount":6.02,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[81].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.848 | [3] |
| `Items[82].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.8 | [3] |
| `Items[83].Amount` | currency | 1,12 | {"valueCurrency":{"amount":1.12,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[83].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.847 | [3] |
| `Items[84].Amount` | currency | 2,84 | {"valueCurrency":{"amount":2.84,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[84].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.852 | [3] |
| `Items[85].Amount` | currency | 2,31 | {"valueCurrency":{"amount":2.31,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[85].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.845 | [3] |
| `Items[86].Amount` | currency | 54,25 | {"valueCurrency":{"amount":54.25,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[86].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.852 | [3] |
| `Items[87].Amount` | currency | 16,69 | {"valueCurrency":{"amount":16.69,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[87].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.852 | [3] |
| `Items[88].Amount` | currency | 45,77 | {"valueCurrency":{"amount":45.77,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[88].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.852 | [3] |
| `Items[89].Amount` | currency | 43,18 | {"valueCurrency":{"amount":43.18,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[89].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.852 | [3] |
| `Items[90].Amount` | currency | 1,17 | {"valueCurrency":{"amount":1.17,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[90].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.852 | [3] |
| `Items[91].Amount` | currency | 1,98 | {"valueCurrency":{"amount":1.98,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[91].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.852 | [3] |
| `Items[92].Amount` | currency | 35,16 | {"valueCurrency":{"amount":35.16,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[92].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.852 | [3] |
| `Items[93].Amount` | currency | 37,43 | {"valueCurrency":{"amount":37.43,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[93].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.852 | [3] |
| `Items[94].Amount` | currency | 2,14 | {"valueCurrency":{"amount":2.14,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[94].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.852 | [3] |
| `Items[95].Amount` | currency | 7,59 | {"valueCurrency":{"amount":7.59,"currencyCode":"EUR"}} | 0.852 | [3] |
| `Items[95].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.852 | [3] |
| `TaxDetails` | array | None | {} | ? | [] |
| `TaxDetails[1].Amount` | currency | 189,45 | {"valueCurrency":{"amount":189.45,"currencyCode":"EUR"}} | 0.901 | [1] |
| `TotalTax` | currency | 189,45 | {"valueCurrency":{"amount":189.45,"currencyCode":"EUR"}} | 0.938 | [1] |
| `VendorName` | string | cencora ? Alliance Healthcare | {"valueString":"cencora\nAlliance Healthcare"} | 0.652 | [1] |

#### Tablas detectadas

| Tabla | Filas ? columnas | P?gina relativa | Celdas no vac?as |
|---:|---:|---|---:|
| 1 | 3 ? 2 | [1] | 6 |
| 2 | 2 ? 3 | [1] | 6 |
| 3 | 22 ? 12 | [1] | 44 |
| 4 | 4 ? 8 | [1] | 13 |
| 5 | 2 ? 2 | [1] | 4 |
| 6 | 2 ? 2 | [1] | 3 |
| 7 | 51 ? 10 | [2] | 260 |
| 8 | 64 ? 10 | [3] | 220 |

#### Duplicados exactos

| Content | Apariciones | Rutas |
|---|---:|---|
| PUIG SALOMON PIUS | 2 | CustomerAddressRecipient, CustomerName |
| 10-07-2026 | 11 | InvoiceDate, Items[86].Date, Items[87].Date, Items[88].Date, Items[89].Date, Items[90].Date, Items[91].Date, Items[92].Date, Items[93].Date, Items[94].Date, Items[95].Date |
| 01-07-2026 | 9 | Items[4].Date, Items[5].Date, Items[6].Date, Items[7].Date, Items[8].Date, Items[9].Date, Items[10].Date, Items[11].Date, Items[12].Date |
| 02-07-2026 | 20 | Items[13].Date, Items[14].Date, Items[15].Date, Items[16].Date, Items[17].Date, Items[18].Date, Items[19].Date, Items[20].Date, Items[21].Date, Items[22].Date, Items[23].Date, Items[24].Date, Items[25].Date, Items[26].Date, Items[27].Date, Items[28].Date, Items[29].Date, Items[30].Date, Items[31].Date, Items[32].Date |
| 03-07-2026 | 8 | Items[33].Date, Items[34].Date, Items[35].Date, Items[36].Date, Items[37].Date, Items[38].Date, Items[39].Date, Items[40].Date |
| 04-07-2026 | 3 | Items[41].Date, Items[42].Date, Items[43].Date |
| 05-07-2026 | 3 | Items[44].Date, Items[45].Date, Items[46].Date |
| 06-07-2026 | 9 | Items[47].Date, Items[48].Date, Items[49].Date, Items[50].Date, Items[51].Date, Items[52].Date, Items[53].Date, Items[54].Date, Items[55].Date |
| 07-07-2026 | 8 | Items[56].Date, Items[57].Date, Items[58].Date, Items[59].Date, Items[60].Date, Items[61].Date, Items[62].Date, Items[63].Date |
| 08-07-2026 | 11 | Items[64].Date, Items[65].Date, Items[66].Date, Items[67].Date, Items[68].Date, Items[69].Date, Items[70].Date, Items[71].Date, Items[72].Date, Items[73].Date, Items[74].Date |
| 09-07-2026 | 11 | Items[75].Date, Items[76].Date, Items[77].Date, Items[78].Date, Items[79].Date, Items[80].Date, Items[81].Date, Items[82].Date, Items[83].Date, Items[84].Date, Items[85].Date |
| 189,45 | 2 | TaxDetails[1].Amount, TotalTax |

### `08008427` ? p?ginas originales 4-7

| Campo | Esperado | Campo Azure | Valor Azure | Confianza | Clasificaci?n | Observaci?n |
|---|---|---|---|---:|---|---|
| `tipo_documento` | FACTURA | documents[].docType | invoice | 1 | **ENTIDAD AMBIGUA** | docType es invoice: identifica la clase del modelo, pero no devuelve literalmente FACTURA ni acredita distinci?n frente a ABONO. |
| `categoria` | MERCANCIA | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | No existe un campo nativo observado para la categor?a del patr?n. |
| `requiere_conciliacion_albaranes` | true | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | Indicador interno no disponible como campo nativo. |
| `pagina_inicio` | 4 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango original es metadato de la divisi?n, no una entidad extra?da. |
| `pagina_fin` | 7 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango original es metadato de la divisi?n, no una entidad extra?da. |
| `proveedor_nombre` | ALLIANCE HEALTHCARE ESPAÑA, S.A. | VendorName | cencora ? Alliance Healthcare | 0.546 | **PARCIAL** | Azure devuelve la marca cencora / Alliance Healthcare, pero no la raz?n social literal completa esperada. |
| `proveedor_cif` | A50004324 | ? | null | ? | **AUSENTE** | VendorTaxId no fue devuelto; no se toma el CIF desde OCR o tablas por inferencia. |
| `numero_factura` | 08008427 | InvoiceId | 08008427 | 0.938 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `fecha_factura` | 2026-07-10 | InvoiceDate | 2026-07-10 | 0.939 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `base_imponible_total` | 10531.42 | ? | {"texto_en_tabla_sin_campo_nativo":[{"tabla":5,"etiqueta":"TOTAL BASE IMPONIBLE","valor_contiguo":"10.531,42","pagina_relativa":1}]} | ? | **AUSENTE** | SubTotal est? ausente. La tabla conserva etiqueta/importe por OCR, pero no se convierte en campo ni se interpreta mediante reglas. |
| `iva_total` | 573.16 | TotalTax | 573.16 | 0.787 | **CORRECTO** | TotalTax coincide con iva_total; no incluye el recargo de equivalencia. |
| `recargo_equivalencia_total` | 80.52 | ? | {"texto_en_tabla_sin_campo_nativo":[{"tabla":6,"etiqueta":"TOTAL RECARGOS EQUIVALENCIA","valor_contiguo":"80,52","pagina_relativa":1}]} | ? | **AUSENTE** | No hay campo estructurado de recargo. La tabla puede conservar el texto, pero TotalTax contiene solo IVA y no se mezcla con el recargo. |
| `importe_total` | 11185.1 | InvoiceTotal | 11185.1 | 0.923 | **CORRECTO** | Coincidencia num?rica con el patr?n. |
| `vencimientos` | [{"orden":1,"fecha_vencimiento":"2026-10-06","importe":11185.1}] | DueDate | {"fechas":["2026-10-06"],"importes":[]} | 0.938 | **PARCIAL** | DueDate coincide con la ?nica fecha esperada, pero Azure no devuelve el importe del vencimiento. No hay vencimientos m?ltiples en estas cuatro muestras. |
| `impuestos` | [] | TaxDetails | {"nombre_campo":"TaxDetails","tipo":"array","content":null,"valor_normalizado":{},"confianza":null,"paginas_relativas":[],"elementos":[{"indice":1,"content":"TOTAL IVAS\n573,16","confianza":0.569,"paginas_relativas":[1],"propiedades":{"Amount":{"nombre_campo"? | ? | **ENTIDAD AMBIGUA** | El patr?n deja impuestos vac?o, pero TaxDetails contiene ?nicamente el importe total de IVA, sin un desglose fiscal completo. |
| `albaranes` | [{"orden":1,"numero_albaran":"08C26499","fecha_albaran":"2026-06-30","tipo_movimiento":"CARGO","descripcion":"NORMAL ACUSTICO","importe_base":1.62,"importe_total":1.69},{"orden":2,"numero_albaran":"08C38230","fecha_albaran":"2026-07-10","tipo_movimiento":"ABO? | Items y tablas | {"items_detectados":152,"product_codes":["08C27035","08C27311","08C27437","08C27725","08C27900","08C28814","08C29302","08C30958","08C31034","08C31135","08C31297","08C31301","08C31302","08C31489","08V19185","08C31638","08C32023","08C32131","08C32157","08C32269? | ? | **PARCIAL** | Items recupera principalmente fechas e importes y pocos ProductCode; las tablas conservan m?s n?meros, pero no existe una estructura completa y fiable de n?mero, fecha, movimiento, descripci?n, base y total. |
| `ajustes` | [{"orden":1,"tipo_ajuste":"GASTO","descripcion":"Servicio básico","importe":31.46,"incluido_en_base":true,"incluido_en_total":true}] | Items | [{"indice_item":5,"campos":{"Amount":{"nombre_campo":"Amount","tipo":"currency","content":"31,46","valor_normalizado":{"valueCurrency":{"amount":31.46,"currencyCode":"EUR"}},"confianza":0.91,"paginas_relativas":[1]},"Description":{"nombre_campo":"Description"? | ? | **PARCIAL** | Servicio b?sico y 31,46 aparecen como Item, no como ajuste; faltan tipo e indicadores incluido_en_base/incluido_en_total. |
| `destinatario` | {"id_farmacia":"PIO","nombre":"FARMACIA PIO PUIG","cif":"40901058C","metodo_identificacion":"CIF"} | ['CustomerName', 'CustomerTaxId', 'CustomerAddress', 'CustomerAddressRecipient'] | {"CustomerName":{"nombre_campo":"CustomerName","tipo":"string","content":"PUIG SALOMON PIUS","valor_normalizado":{"valueString":"PUIG SALOMON PIUS"},"confianza":0.891,"paginas_relativas":[1]},"CustomerTaxId":{"nombre_campo":"CustomerTaxId","tipo":"string","co? | [0.891,0.685,0.707,0.891] | **PARCIAL** | CustomerTaxId coincide con el CIF esperado, pero CustomerName no coincide literalmente con el nombre del patr?n y faltan id_farmacia y metodo_identificacion. |

#### Inventario completo de campos Azure

> Las p?ginas son relativas al PDF separado. Items y TaxDetails incluyen todas sus propiedades hijas en el JSON; aqu? cada elemento se presenta en una fila compacta.

| Campo/elemento | Tipo | Content | Valor normalizado | Confianza | P?gina relativa |
|---|---|---|---|---:|---|
| `CustomerAddress` | address | CR SANT LLUC 34 ? 43550 ULLDECONA ? RUTA 16 | {"valueAddress":{"houseNumber":"34","road":"CR SANT LLUC","postalCode":"43550","city":"ULLDECONA","streetAddress":"34 CR SANT LLUC"}} | 0.707 | [1] |
| `CustomerAddressRecipient` | string | PUIG SALOMON PIUS | {"valueString":"PUIG SALOMON PIUS"} | 0.891 | [1] |
| `CustomerName` | string | PUIG SALOMON PIUS | {"valueString":"PUIG SALOMON PIUS"} | 0.891 | [1] |
| `CustomerTaxId` | string | 40901058C | {"valueString":"40901058C"} | 0.685 | [1] |
| `DueDate` | date | 06-10-2026 | {"valueDate":"2026-10-06"} | 0.938 | [4] |
| `InvoiceDate` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.939 | [4] |
| `InvoiceId` | string | 08008427 | {"valueString":"08008427"} | 0.938 | [2] |
| `InvoiceTotal` | currency | 11.185,10 | {"valueCurrency":{"amount":11185.1,"currencyCode":"EUR"}} | 0.923 | [1] |
| `Items` | array | None | {} | ? | [] |
| `Items[1].Amount` | currency | 6.958,15 | {"valueCurrency":{"amount":6958.15,"currencyCode":"EUR"}} | 0.937 | [1] |
| `Items[1].Description` | string | ESPECIALIDAD | {"valueString":"ESPECIALIDAD"} | 0.925 | [1] |
| `Items[1].Tax` | currency | 266,34 | {"valueCurrency":{"amount":266.34,"currencyCode":"EUR"}} | 0.621 | [1] |
| `Items[2].Amount` | currency | 769,50 | {"valueCurrency":{"amount":769.5,"currencyCode":"EUR"}} | 0.936 | [1] |
| `Items[2].Description` | string | GENERICOS | {"valueString":"GENERICOS"} | 0.922 | [1] |
| `Items[2].Tax` | currency | 29,45 | {"valueCurrency":{"amount":29.45,"currencyCode":"EUR"}} | 0.601 | [1] |
| `Items[3].Amount` | currency | 1.205,55 | {"valueCurrency":{"amount":1205.55,"currencyCode":"EUR"}} | 0.937 | [1] |
| `Items[3].Description` | string | R.D. 5/2000 | {"valueString":"R.D. 5/2000"} | 0.92 | [1] |
| `Items[3].Tax` | currency | 46,15 | {"valueCurrency":{"amount":46.15,"currencyCode":"EUR"}} | 0.616 | [1] |
| `Items[4].Amount` | currency | 2.220,44 | {"valueCurrency":{"amount":2220.44,"currencyCode":"EUR"}} | 0.937 | [1] |
| `Items[4].Description` | string | NO ESPECIALIDAD | {"valueString":"NO ESPECIALIDAD"} | 0.906 | [1] |
| `Items[4].Tax` | currency | 168,36 ? 57,40 | {"valueCurrency":{"amount":168.36,"currencyCode":"EUR"}} | 0.528 | [1] |
| `Items[5].Amount` | currency | 31,46 | {"valueCurrency":{"amount":31.46,"currencyCode":"EUR"}} | 0.91 | [1] |
| `Items[5].Description` | string | SERVICIO BASICO | {"valueString":"SERVICIO BASICO"} | 0.722 | [1] |
| `Items[6].Amount` | currency | 8,66- | {"valueCurrency":{"amount":-8.66,"currencyCode":"EUR"}} | 0.51 | [2] |
| `Items[6].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.503 | [2] |
| `Items[7].Amount` | currency | 1,69 | {"valueCurrency":{"amount":1.69,"currencyCode":"EUR"}} | 0.884 | [2] |
| `Items[7].Date` | date | 30-06-2026 | {"valueDate":"2026-06-30"} | 0.886 | [2] |
| `Items[7].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.207 | [2] |
| `Items[8].Amount` | currency | 36,09- | {"valueCurrency":{"amount":-36.09,"currencyCode":"EUR"}} | 0.477 | [2] |
| `Items[8].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.494 | [2] |
| `Items[9].Amount` | currency | 1,32 | {"valueCurrency":{"amount":1.32,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[9].Date` | date | 30-06-2026 | {"valueDate":"2026-06-30"} | 0.885 | [2] |
| `Items[9].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.089 | [2] |
| `Items[10].Amount` | currency | 127,77 | {"valueCurrency":{"amount":127.77,"currencyCode":"EUR"}} | 0.884 | [2] |
| `Items[10].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.875 | [2] |
| `Items[10].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.355 | [2] |
| `Items[10].ProductCode` | string | 08C27035 | {"valueString":"08C27035"} | 0.138 | [2] |
| `Items[11].Amount` | currency | 775,24 | {"valueCurrency":{"amount":775.24,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[11].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.873 | [2] |
| `Items[11].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.106 | [2] |
| `Items[12].Amount` | currency | 39,46 | {"valueCurrency":{"amount":39.46,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[12].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.87 | [2] |
| `Items[12].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.295 | [2] |
| `Items[13].Amount` | currency | 4,32 | {"valueCurrency":{"amount":4.32,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[13].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.878 | [2] |
| `Items[13].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.313 | [2] |
| `Items[13].ProductCode` | string | 08C27311 | {"valueString":"08C27311"} | 0.176 | [2] |
| `Items[14].Amount` | currency | 3,51 | {"valueCurrency":{"amount":3.51,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[14].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.871 | [2] |
| `Items[14].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.299 | [2] |
| `Items[14].ProductCode` | string | 08C27437 | {"valueString":"08C27437"} | 0.188 | [2] |
| `Items[15].Amount` | currency | 115,72 | {"valueCurrency":{"amount":115.72,"currencyCode":"EUR"}} | 0.883 | [2] |
| `Items[15].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.867 | [2] |
| `Items[15].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.095 | [2] |
| `Items[16].Amount` | currency | 37,73 | {"valueCurrency":{"amount":37.73,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[16].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.863 | [2] |
| `Items[16].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.09 | [2] |
| `Items[16].ProductCode` | string | 08C27725 | {"valueString":"08C27725"} | 0.148 | [2] |
| `Items[17].Amount` | currency | 15,71 | {"valueCurrency":{"amount":15.71,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[17].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.857 | [2] |
| `Items[17].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.08 | [2] |
| `Items[18].Amount` | currency | 10,70 | {"valueCurrency":{"amount":10.7,"currencyCode":"EUR"}} | 0.884 | [2] |
| `Items[18].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.853 | [2] |
| `Items[18].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.852 | [2] |
| `Items[18].ProductCode` | string | 08C27900 | {"valueString":"08C27900"} | 0.142 | [2] |
| `Items[19].Amount` | currency | 41,50 | {"valueCurrency":{"amount":41.5,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[19].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.853 | [2] |
| `Items[19].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.101 | [2] |
| `Items[20].Amount` | currency | 58,25 | {"valueCurrency":{"amount":58.25,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[20].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.853 | [2] |
| `Items[20].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.293 | [2] |
| `Items[21].Amount` | currency | 64,78 | {"valueCurrency":{"amount":64.78,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[21].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.853 | [2] |
| `Items[21].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.399 | [2] |
| `Items[22].Amount` | currency | 9,57 | {"valueCurrency":{"amount":9.57,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[22].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.853 | [2] |
| `Items[22].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.852 | [2] |
| `Items[23].Amount` | currency | 9,09 | {"valueCurrency":{"amount":9.09,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[23].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.853 | [2] |
| `Items[23].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.403 | [2] |
| `Items[24].Amount` | currency | 4,91 | {"valueCurrency":{"amount":4.91,"currencyCode":"EUR"}} | 0.887 | [2] |
| `Items[24].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.853 | [2] |
| `Items[24].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.301 | [2] |
| `Items[25].Amount` | currency | 14,91 | {"valueCurrency":{"amount":14.91,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[25].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.86 | [2] |
| `Items[25].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.084 | [2] |
| `Items[26].Amount` | currency | 362,80 | {"valueCurrency":{"amount":362.8,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[26].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.864 | [2] |
| `Items[26].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.127 | [2] |
| `Items[27].Amount` | currency | 4,62 | {"valueCurrency":{"amount":4.62,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[27].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.868 | [2] |
| `Items[27].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.102 | [2] |
| `Items[28].Amount` | currency | 154,02 | {"valueCurrency":{"amount":154.02,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[28].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.865 | [2] |
| `Items[28].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.087 | [2] |
| `Items[29].Amount` | currency | 9,44 | {"valueCurrency":{"amount":9.44,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[29].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.86 | [2] |
| `Items[29].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.629 | [2] |
| `Items[30].Amount` | currency | 4,44 | {"valueCurrency":{"amount":4.44,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[30].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.876 | [2] |
| `Items[30].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.299 | [2] |
| `Items[30].ProductCode` | string | 08C28814 | {"valueString":"08C28814"} | 0.197 | [2] |
| `Items[31].Amount` | currency | 25,84 | {"valueCurrency":{"amount":25.84,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[31].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.857 | [2] |
| `Items[31].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.087 | [2] |
| `Items[32].Amount` | currency | 29,15 | {"valueCurrency":{"amount":29.15,"currencyCode":"EUR"}} | 0.885 | [2] |
| `Items[32].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.878 | [2] |
| `Items[32].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.298 | [2] |
| `Items[32].ProductCode` | string | 08C29302 | {"valueString":"08C29302"} | 0.168 | [2] |
| `Items[33].Amount` | currency | 3,17 | {"valueCurrency":{"amount":3.17,"currencyCode":"EUR"}} | 0.887 | [2] |
| `Items[33].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.869 | [2] |
| `Items[33].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.085 | [2] |
| `Items[34].Amount` | currency | 19,38 | {"valueCurrency":{"amount":19.38,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[34].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.876 | [2] |
| `Items[34].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.081 | [2] |
| `Items[35].Amount` | currency | 168,40 | {"valueCurrency":{"amount":168.4,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[35].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.873 | [2] |
| `Items[35].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.293 | [2] |
| `Items[36].Amount` | currency | 2,21 | {"valueCurrency":{"amount":2.21,"currencyCode":"EUR"}} | 0.887 | [2] |
| `Items[36].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.877 | [2] |
| `Items[36].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.085 | [2] |
| `Items[37].Amount` | currency | 9,67 | {"valueCurrency":{"amount":9.67,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[37].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.881 | [2] |
| `Items[37].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.085 | [2] |
| `Items[38].Amount` | currency | 223,46 | {"valueCurrency":{"amount":223.46,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[38].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.87 | [2] |
| `Items[38].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.235 | [2] |
| `Items[39].Amount` | currency | 268,17 | {"valueCurrency":{"amount":268.17,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[39].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.876 | [2] |
| `Items[39].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.293 | [2] |
| `Items[40].Amount` | currency | 13,06 | {"valueCurrency":{"amount":13.06,"currencyCode":"EUR"}} | 0.885 | [2] |
| `Items[40].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.866 | [2] |
| `Items[40].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.606 | [2] |
| `Items[41].Amount` | currency | 1,32 | {"valueCurrency":{"amount":1.32,"currencyCode":"EUR"}} | 0.887 | [2] |
| `Items[41].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.883 | [2] |
| `Items[41].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.294 | [2] |
| `Items[42].Amount` | currency | 6,01 | {"valueCurrency":{"amount":6.01,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[42].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.878 | [2] |
| `Items[42].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.08 | [2] |
| `Items[43].Amount` | currency | 61,87 | {"valueCurrency":{"amount":61.87,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[43].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.881 | [2] |
| `Items[43].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.078 | [2] |
| `Items[44].Amount` | currency | 12,08 | {"valueCurrency":{"amount":12.08,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[44].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.881 | [2] |
| `Items[44].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.298 | [2] |
| `Items[45].Amount` | currency | 1,56 | {"valueCurrency":{"amount":1.56,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[45].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.882 | [2] |
| `Items[45].Description` | string | ACUSTICO | {"valueString":"ACUSTICO"} | 0.295 | [2] |
| `Items[46].Amount` | currency | 70,78 | {"valueCurrency":{"amount":70.78,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[46].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.88 | [2] |
| `Items[46].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.092 | [2] |
| `Items[47].Amount` | currency | 19,22 | {"valueCurrency":{"amount":19.22,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[47].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.879 | [2] |
| `Items[47].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.102 | [2] |
| `Items[48].Amount` | currency | 32,57 | {"valueCurrency":{"amount":32.57,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[48].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.876 | [2] |
| `Items[48].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.102 | [2] |
| `Items[49].Amount` | currency | 15,56 | {"valueCurrency":{"amount":15.56,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[49].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.873 | [2] |
| `Items[49].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.243 | [2] |
| `Items[50].Amount` | currency | 10,50 | {"valueCurrency":{"amount":10.5,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[50].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.874 | [2] |
| `Items[50].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.292 | [2] |
| `Items[51].Amount` | currency | 15,17 | {"valueCurrency":{"amount":15.17,"currencyCode":"EUR"}} | 0.883 | [2] |
| `Items[51].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.87 | [2] |
| `Items[51].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.852 | [2] |
| `Items[52].Amount` | currency | 11,98 | {"valueCurrency":{"amount":11.98,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[52].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.88 | [2] |
| `Items[52].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.108 | [2] |
| `Items[53].Amount` | currency | 10,73 | {"valueCurrency":{"amount":10.73,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[53].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.853 | [2] |
| `Items[53].ProductCode` | string | 08C30958 | {"valueString":"08C30958"} | 0.296 | [2] |
| `Items[54].Amount` | currency | 1,69 | {"valueCurrency":{"amount":1.69,"currencyCode":"EUR"}} | 0.887 | [2] |
| `Items[54].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.853 | [2] |
| `Items[54].ProductCode` | string | 08C31034 | {"valueString":"08C31034"} | 0.301 | [2] |
| `Items[55].Amount` | currency | 1,86 | {"valueCurrency":{"amount":1.86,"currencyCode":"EUR"}} | 0.887 | [2] |
| `Items[55].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.853 | [2] |
| `Items[55].ProductCode` | string | 08C31135 | {"valueString":"08C31135"} | 0.296 | [2] |
| `Items[55].UnitPrice` | currency | 1,78 | {"valueCurrency":{"amount":1.78,"currencyCode":"EUR"}} | 0.153 | [2] |
| `Items[56].Amount` | currency | 2,26 | {"valueCurrency":{"amount":2.26,"currencyCode":"EUR"}} | 0.887 | [2] |
| `Items[56].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.852 | [2] |
| `Items[56].ProductCode` | string | 08C31297 | {"valueString":"08C31297"} | 0.298 | [2] |
| `Items[56].UnitPrice` | currency | 2,16 | {"valueCurrency":{"amount":2.16,"currencyCode":"EUR"}} | 0.199 | [2] |
| `Items[57].Amount` | currency | 318,74 | {"valueCurrency":{"amount":318.74,"currencyCode":"EUR"}} | 0.886 | [2] |
| `Items[57].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.852 | [2] |
| `Items[57].ProductCode` | string | 08C31301 | {"valueString":"08C31301"} | 0.129 | [2] |
| `Items[57].UnitPrice` | currency | 301,99 | {"valueCurrency":{"amount":301.99,"currencyCode":"EUR"}} | 0.14 | [2] |
| `Items[58].Amount` | currency | 1,72 | {"valueCurrency":{"amount":1.72,"currencyCode":"EUR"}} | 0.702 | [3] |
| `Items[58].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.681 | [3] |
| `Items[58].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.148 | [3] |
| `Items[58].ProductCode` | string | 08C31302 | {"valueString":"08C31302"} | 0.049 | [3] |
| `Items[59].Amount` | currency | 206,01 | {"valueCurrency":{"amount":206.01,"currencyCode":"EUR"}} | 0.692 | [3] |
| `Items[59].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.681 | [3] |
| `Items[59].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.229 | [3] |
| `Items[59].ProductCode` | string | 08C31489 | {"valueString":"08C31489"} | 0.054 | [3] |
| `Items[60].Amount` | currency | 89,75 | {"valueCurrency":{"amount":89.75,"currencyCode":"EUR"}} | 0.697 | [3] |
| `Items[60].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.681 | [3] |
| `Items[60].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.161 | [3] |
| `Items[61].Amount` | currency | 8,82 | {"valueCurrency":{"amount":8.82,"currencyCode":"EUR"}} | 0.703 | [3] |
| `Items[61].Date` | date | 04-07-2026 | {"valueDate":"2026-07-04"} | 0.681 | [3] |
| `Items[61].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.16 | [3] |
| `Items[61].ProductCode` | string | 08V19185 | {"valueString":"08V19185"} | 0.054 | [3] |
| `Items[62].Amount` | currency | 60,06 | {"valueCurrency":{"amount":60.06,"currencyCode":"EUR"}} | 0.687 | [3] |
| `Items[62].Date` | date | 05-07-2026 | {"valueDate":"2026-07-05"} | 0.681 | [3] |
| `Items[62].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.244 | [3] |
| `Items[62].ProductCode` | string | 08C31638 | {"valueString":"08C31638"} | 0.06 | [3] |
| `Items[63].Amount` | currency | 176,06 | {"valueCurrency":{"amount":176.06,"currencyCode":"EUR"}} | 0.69 | [3] |
| `Items[63].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[63].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.231 | [3] |
| `Items[63].ProductCode` | string | 08C32023 | {"valueString":"08C32023"} | 0.188 | [3] |
| `Items[64].Amount` | currency | 238,54 | {"valueCurrency":{"amount":238.54,"currencyCode":"EUR"}} | 0.701 | [3] |
| `Items[64].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[64].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.155 | [3] |
| `Items[64].ProductCode` | string | 08C32131 | {"valueString":"08C32131"} | 0.183 | [3] |
| `Items[65].Amount` | currency | 11,48 | {"valueCurrency":{"amount":11.48,"currencyCode":"EUR"}} | 0.688 | [3] |
| `Items[65].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[65].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.239 | [3] |
| `Items[65].ProductCode` | string | 08C32157 | {"valueString":"08C32157"} | 0.244 | [3] |
| `Items[66].Amount` | currency | 34,25 | {"valueCurrency":{"amount":34.25,"currencyCode":"EUR"}} | 0.685 | [3] |
| `Items[66].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[66].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.142 | [3] |
| `Items[66].ProductCode` | string | 08C32269 | {"valueString":"08C32269"} | 0.166 | [3] |
| `Items[67].Amount` | currency | 17,13 | {"valueCurrency":{"amount":17.13,"currencyCode":"EUR"}} | 0.691 | [3] |
| `Items[67].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[67].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.157 | [3] |
| `Items[67].ProductCode` | string | 08C32270 | {"valueString":"08C32270"} | 0.179 | [3] |
| `Items[68].Amount` | currency | 6,42 | {"valueCurrency":{"amount":6.42,"currencyCode":"EUR"}} | 0.703 | [3] |
| `Items[68].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[68].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.151 | [3] |
| `Items[68].ProductCode` | string | 08C32342 | {"valueString":"08C32342"} | 0.176 | [3] |
| `Items[69].Amount` | currency | 743,49 | {"valueCurrency":{"amount":743.49,"currencyCode":"EUR"}} | 0.688 | [3] |
| `Items[69].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[69].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.241 | [3] |
| `Items[69].ProductCode` | string | 08C32348 | {"valueString":"08C32348"} | 0.048 | [3] |
| `Items[70].Amount` | currency | 15,21 | {"valueCurrency":{"amount":15.21,"currencyCode":"EUR"}} | 0.681 | [3] |
| `Items[70].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[70].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.615 | [3] |
| `Items[70].ProductCode` | string | 08C32355 | {"valueString":"08C32355"} | 0.064 | [3] |
| `Items[71].Amount` | currency | 1,41 | {"valueCurrency":{"amount":1.41,"currencyCode":"EUR"}} | 0.712 | [3] |
| `Items[71].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.68 | [3] |
| `Items[71].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.283 | [3] |
| `Items[71].ProductCode` | string | 08C32356 | {"valueString":"08C32356"} | 0.057 | [3] |
| `Items[72].Amount` | currency | 168,78 | {"valueCurrency":{"amount":168.78,"currencyCode":"EUR"}} | 0.686 | [3] |
| `Items[72].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[72].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.293 | [3] |
| `Items[72].ProductCode` | string | 08C32802 | {"valueString":"08C32802"} | 0.16 | [3] |
| `Items[73].Amount` | currency | 27,56 | {"valueCurrency":{"amount":27.56,"currencyCode":"EUR"}} | 0.703 | [3] |
| `Items[73].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.677 | [3] |
| `Items[73].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.139 | [3] |
| `Items[73].ProductCode` | string | 08C32805 | {"valueString":"08C32805"} | 0.058 | [3] |
| `Items[74].Amount` | currency | 68,49 | {"valueCurrency":{"amount":68.49,"currencyCode":"EUR"}} | 0.699 | [3] |
| `Items[74].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[74].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.229 | [3] |
| `Items[74].ProductCode` | string | 08C32806 | {"valueString":"08C32806"} | 0.063 | [3] |
| `Items[75].Amount` | currency | 38,43 | {"valueCurrency":{"amount":38.43,"currencyCode":"EUR"}} | 0.681 | [3] |
| `Items[75].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[75].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.145 | [3] |
| `Items[75].ProductCode` | string | 08C32824 | {"valueString":"08C32824"} | 0.177 | [3] |
| `Items[76].Amount` | currency | 5,57 | {"valueCurrency":{"amount":5.57,"currencyCode":"EUR"}} | 0.707 | [3] |
| `Items[76].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[76].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.279 | [3] |
| `Items[76].ProductCode` | string | 08C32854 | {"valueString":"08C32854"} | 0.191 | [3] |
| `Items[77].Amount` | currency | 5,06 | {"valueCurrency":{"amount":5.06,"currencyCode":"EUR"}} | 0.703 | [3] |
| `Items[77].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[77].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.235 | [3] |
| `Items[77].ProductCode` | string | 08C32877 | {"valueString":"08C32877"} | 0.184 | [3] |
| `Items[78].Amount` | currency | 10,14 | {"valueCurrency":{"amount":10.14,"currencyCode":"EUR"}} | 0.687 | [3] |
| `Items[78].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[78].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.159 | [3] |
| `Items[78].ProductCode` | string | 08C32878 | {"valueString":"08C32878"} | 0.164 | [3] |
| `Items[79].Amount` | currency | 6,74 | {"valueCurrency":{"amount":6.74,"currencyCode":"EUR"}} | 0.704 | [3] |
| `Items[79].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[79].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.165 | [3] |
| `Items[79].ProductCode` | string | 08C33027 | {"valueString":"08C33027"} | 0.055 | [3] |
| `Items[80].Amount` | currency | 44,87 | {"valueCurrency":{"amount":44.87,"currencyCode":"EUR"}} | 0.681 | [3] |
| `Items[80].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[80].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.157 | [3] |
| `Items[81].Amount` | currency | 19,66 | {"valueCurrency":{"amount":19.66,"currencyCode":"EUR"}} | 0.685 | [3] |
| `Items[81].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[81].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.161 | [3] |
| `Items[82].Amount` | currency | 37,60 | {"valueCurrency":{"amount":37.6,"currencyCode":"EUR"}} | 0.688 | [3] |
| `Items[82].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[82].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.137 | [3] |
| `Items[83].Amount` | currency | 104,09 | {"valueCurrency":{"amount":104.09,"currencyCode":"EUR"}} | 0.681 | [3] |
| `Items[83].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[83].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.282 | [3] |
| `Items[84].Amount` | currency | 61,87 | {"valueCurrency":{"amount":61.87,"currencyCode":"EUR"}} | 0.694 | [3] |
| `Items[84].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[84].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.147 | [3] |
| `Items[85].Amount` | currency | 0,88 | {"valueCurrency":{"amount":0.88,"currencyCode":"EUR"}} | 0.703 | [3] |
| `Items[85].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[85].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.153 | [3] |
| `Items[85].ProductCode` | string | 08M32612 | {"valueString":"08M32612"} | 0.055 | [3] |
| `Items[86].Amount` | currency | 196,38 | {"valueCurrency":{"amount":196.38,"currencyCode":"EUR"}} | 0.701 | [3] |
| `Items[86].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[86].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.282 | [3] |
| `Items[87].Amount` | currency | 9,05 | {"valueCurrency":{"amount":9.05,"currencyCode":"EUR"}} | 0.702 | [3] |
| `Items[87].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[87].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.605 | [3] |
| `Items[88].Amount` | currency | 36,34 | {"valueCurrency":{"amount":36.34,"currencyCode":"EUR"}} | 0.701 | [3] |
| `Items[88].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[88].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.232 | [3] |
| `Items[88].ProductCode` | string | 08M32977 | {"valueString":"08M32977"} | 0.052 | [3] |
| `Items[89].Amount` | currency | 8,82 | {"valueCurrency":{"amount":8.82,"currencyCode":"EUR"}} | 0.707 | [3] |
| `Items[89].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.681 | [3] |
| `Items[89].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.282 | [3] |
| `Items[89].ProductCode` | string | 08V19262 | {"valueString":"08V19262"} | 0.164 | [3] |
| `Items[90].Amount` | currency | 103,53 | {"valueCurrency":{"amount":103.53,"currencyCode":"EUR"}} | 0.701 | [3] |
| `Items[90].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[90].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.292 | [3] |
| `Items[90].ProductCode` | string | 08C33364 | {"valueString":"08C33364"} | 0.059 | [3] |
| `Items[91].Amount` | currency | 38,62 | {"valueCurrency":{"amount":38.62,"currencyCode":"EUR"}} | 0.703 | [3] |
| `Items[91].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[91].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.157 | [3] |
| `Items[91].ProductCode` | string | 08C33510 | {"valueString":"08C33510"} | 0.048 | [3] |
| `Items[92].Amount` | currency | 11,32 | {"valueCurrency":{"amount":11.32,"currencyCode":"EUR"}} | 0.701 | [3] |
| `Items[92].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[92].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.161 | [3] |
| `Items[92].ProductCode` | string | 08C33655 | {"valueString":"08C33655"} | 0.053 | [3] |
| `Items[93].Amount` | currency | 533,10 | {"valueCurrency":{"amount":533.1,"currencyCode":"EUR"}} | 0.688 | [3] |
| `Items[93].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[93].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.228 | [3] |
| `Items[94].Amount` | currency | 21,92 | {"valueCurrency":{"amount":21.92,"currencyCode":"EUR"}} | 0.693 | [3] |
| `Items[94].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[94].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.609 | [3] |
| `Items[94].ProductCode` | string | 08C33667 | {"valueString":"08C33667"} | 0.058 | [3] |
| `Items[95].Amount` | currency | 168,82 | {"valueCurrency":{"amount":168.82,"currencyCode":"EUR"}} | 0.683 | [3] |
| `Items[95].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[95].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.293 | [3] |
| `Items[96].Amount` | currency | 2,54 | {"valueCurrency":{"amount":2.54,"currencyCode":"EUR"}} | 0.706 | [3] |
| `Items[96].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[96].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.231 | [3] |
| `Items[96].ProductCode` | string | 08C34216 | {"valueString":"08C34216"} | 0.171 | [3] |
| `Items[97].Amount` | currency | 139,87 | {"valueCurrency":{"amount":139.87,"currencyCode":"EUR"}} | 0.687 | [3] |
| `Items[97].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[97].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.162 | [3] |
| `Items[97].ProductCode` | string | 08C34434 | {"valueString":"08C34434"} | 0.05 | [3] |
| `Items[98].Amount` | currency | 6,70 | {"valueCurrency":{"amount":6.7,"currencyCode":"EUR"}} | 0.704 | [3] |
| `Items[98].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[98].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.141 | [3] |
| `Items[98].ProductCode` | string | 08C34451 | {"valueString":"08C34451"} | 0.178 | [3] |
| `Items[99].Amount` | currency | 142,77 | {"valueCurrency":{"amount":142.77,"currencyCode":"EUR"}} | 0.696 | [3] |
| `Items[99].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[99].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.235 | [3] |
| `Items[100].Amount` | currency | 177,31 | {"valueCurrency":{"amount":177.31,"currencyCode":"EUR"}} | 0.702 | [3] |
| `Items[100].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[100].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.277 | [3] |
| `Items[100].ProductCode` | string | 08M33628 | {"valueString":"08M33628"} | 0.052 | [3] |
| `Items[101].Amount` | currency | 70,94 | {"valueCurrency":{"amount":70.94,"currencyCode":"EUR"}} | 0.695 | [3] |
| `Items[101].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[101].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.289 | [3] |
| `Items[102].Amount` | currency | 28,76 | {"valueCurrency":{"amount":28.76,"currencyCode":"EUR"}} | 0.688 | [3] |
| `Items[102].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[102].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.236 | [3] |
| `Items[103].Amount` | currency | 106,77 | {"valueCurrency":{"amount":106.77,"currencyCode":"EUR"}} | 0.692 | [3] |
| `Items[103].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[103].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.285 | [3] |
| `Items[104].Amount` | currency | 13,58 | {"valueCurrency":{"amount":13.58,"currencyCode":"EUR"}} | 0.681 | [3] |
| `Items[104].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[104].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.157 | [3] |
| `Items[105].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.681 | [3] |
| `Items[105].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.318 | [3] |
| `Items[106].Amount` | currency | 13,17 | {"valueCurrency":{"amount":13.17,"currencyCode":"EUR"}} | 0.681 | [3] |
| `Items[106].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.629 | [3] |
| `Items[106].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.629 | [3] |
| `Items[106].ProductCode` | string | 08M33962 | {"valueString":"08M33962"} | 0.053 | [3] |
| `Items[106].UnitPrice` | currency | 11,82 | {"valueCurrency":{"amount":11.82,"currencyCode":"EUR"}} | 0.05 | [3] |
| `Items[107].Amount` | currency | 1,91 | {"valueCurrency":{"amount":1.91,"currencyCode":"EUR"}} | 0.682 | [3] |
| `Items[107].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.649 | [3] |
| `Items[107].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.589 | [3] |
| `Items[107].UnitPrice` | currency | 1,83 | {"valueCurrency":{"amount":1.83,"currencyCode":"EUR"}} | 0.162 | [3] |
| `Items[108].Amount` | currency | 314,75 | {"valueCurrency":{"amount":314.75,"currencyCode":"EUR"}} | 0.799 | [4] |
| `Items[108].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.8 | [4] |
| `Items[108].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.38 | [4] |
| `Items[109].Amount` | currency | 90,39 | {"valueCurrency":{"amount":90.39,"currencyCode":"EUR"}} | 0.8 | [4] |
| `Items[109].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.8 | [4] |
| `Items[109].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.409 | [4] |
| `Items[110].Amount` | currency | 7,60 | {"valueCurrency":{"amount":7.6,"currencyCode":"EUR"}} | 0.802 | [4] |
| `Items[110].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.8 | [4] |
| `Items[110].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.381 | [4] |
| `Items[111].Amount` | currency | 4,03 | {"valueCurrency":{"amount":4.03,"currencyCode":"EUR"}} | 0.803 | [4] |
| `Items[111].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.787 | [4] |
| `Items[111].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.321 | [4] |
| `Items[112].Amount` | currency | 97,79 | {"valueCurrency":{"amount":97.79,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[112].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.788 | [4] |
| `Items[112].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.403 | [4] |
| `Items[113].Amount` | currency | 356,44 | {"valueCurrency":{"amount":356.44,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[113].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.799 | [4] |
| `Items[113].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.39 | [4] |
| `Items[114].Amount` | currency | 6,21 | {"valueCurrency":{"amount":6.21,"currencyCode":"EUR"}} | 0.802 | [4] |
| `Items[114].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.792 | [4] |
| `Items[114].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.701 | [4] |
| `Items[115].Amount` | currency | 1,32 | {"valueCurrency":{"amount":1.32,"currencyCode":"EUR"}} | 0.804 | [4] |
| `Items[115].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.789 | [4] |
| `Items[115].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.381 | [4] |
| `Items[116].Amount` | currency | 4,88 | {"valueCurrency":{"amount":4.88,"currencyCode":"EUR"}} | 0.804 | [4] |
| `Items[116].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.797 | [4] |
| `Items[116].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.329 | [4] |
| `Items[117].Amount` | currency | 22,18 | {"valueCurrency":{"amount":22.18,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[117].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.791 | [4] |
| `Items[117].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.408 | [4] |
| `Items[118].Amount` | currency | 11,70 | {"valueCurrency":{"amount":11.7,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[118].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.791 | [4] |
| `Items[118].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.432 | [4] |
| `Items[119].Amount` | currency | 23,63 | {"valueCurrency":{"amount":23.63,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[119].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.779 | [4] |
| `Items[119].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.381 | [4] |
| `Items[120].Amount` | currency | 72,96 | {"valueCurrency":{"amount":72.96,"currencyCode":"EUR"}} | 0.802 | [4] |
| `Items[120].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.783 | [4] |
| `Items[120].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.451 | [4] |
| `Items[121].Amount` | currency | 43,56 | {"valueCurrency":{"amount":43.56,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[121].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.758 | [4] |
| `Items[121].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.43 | [4] |
| `Items[122].Amount` | currency | 73,60 | {"valueCurrency":{"amount":73.6,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[122].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.786 | [4] |
| `Items[122].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.428 | [4] |
| `Items[123].Amount` | currency | 10,83 | {"valueCurrency":{"amount":10.83,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[123].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.762 | [4] |
| `Items[123].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.381 | [4] |
| `Items[124].Amount` | currency | 1,69 | {"valueCurrency":{"amount":1.69,"currencyCode":"EUR"}} | 0.802 | [4] |
| `Items[124].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.776 | [4] |
| `Items[124].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.39 | [4] |
| `Items[125].Amount` | currency | 569,49 | {"valueCurrency":{"amount":569.49,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[125].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.784 | [4] |
| `Items[125].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.456 | [4] |
| `Items[126].Amount` | currency | 9,07 | {"valueCurrency":{"amount":9.07,"currencyCode":"EUR"}} | 0.802 | [4] |
| `Items[126].Date` | date | 08-07-2026 | {"valueDate":"2026-07-08"} | 0.772 | [4] |
| `Items[126].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.721 | [4] |
| `Items[127].Amount` | currency | 28,38 | {"valueCurrency":{"amount":28.38,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[127].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.774 | [4] |
| `Items[127].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.449 | [4] |
| `Items[128].Amount` | currency | 7,67 | {"valueCurrency":{"amount":7.67,"currencyCode":"EUR"}} | 0.803 | [4] |
| `Items[128].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.771 | [4] |
| `Items[128].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.413 | [4] |
| `Items[129].Amount` | currency | 15,92 | {"valueCurrency":{"amount":15.92,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[129].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.736 | [4] |
| `Items[129].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.722 | [4] |
| `Items[130].Amount` | currency | 166,17 | {"valueCurrency":{"amount":166.17,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[130].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.776 | [4] |
| `Items[130].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.404 | [4] |
| `Items[131].Amount` | currency | 14,85 | {"valueCurrency":{"amount":14.85,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[131].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.774 | [4] |
| `Items[131].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.391 | [4] |
| `Items[132].Amount` | currency | 22,10 | {"valueCurrency":{"amount":22.1,"currencyCode":"EUR"}} | 0.802 | [4] |
| `Items[132].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.768 | [4] |
| `Items[132].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.319 | [4] |
| `Items[133].Amount` | currency | 32,66 | {"valueCurrency":{"amount":32.66,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[133].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.76 | [4] |
| `Items[133].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.383 | [4] |
| `Items[134].Amount` | currency | 2,13 | {"valueCurrency":{"amount":2.13,"currencyCode":"EUR"}} | 0.803 | [4] |
| `Items[134].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.789 | [4] |
| `Items[134].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.381 | [4] |
| `Items[135].Amount` | currency | 10,53 | {"valueCurrency":{"amount":10.53,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[135].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.778 | [4] |
| `Items[135].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.388 | [4] |
| `Items[136].Amount` | currency | 10,70 | {"valueCurrency":{"amount":10.7,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[136].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.791 | [4] |
| `Items[136].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.716 | [4] |
| `Items[137].Amount` | currency | 2,86 | {"valueCurrency":{"amount":2.86,"currencyCode":"EUR"}} | 0.802 | [4] |
| `Items[137].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.789 | [4] |
| `Items[137].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.309 | [4] |
| `Items[138].Amount` | currency | 132,58 | {"valueCurrency":{"amount":132.58,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[138].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.783 | [4] |
| `Items[138].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.434 | [4] |
| `Items[139].Amount` | currency | 43,43 | {"valueCurrency":{"amount":43.43,"currencyCode":"EUR"}} | 0.8 | [4] |
| `Items[139].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.8 | [4] |
| `Items[139].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.381 | [4] |
| `Items[140].Amount` | currency | 87,87 | {"valueCurrency":{"amount":87.87,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[140].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.795 | [4] |
| `Items[140].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.415 | [4] |
| `Items[141].Amount` | currency | 16,10 | {"valueCurrency":{"amount":16.1,"currencyCode":"EUR"}} | 0.8 | [4] |
| `Items[141].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.796 | [4] |
| `Items[141].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.323 | [4] |
| `Items[142].Amount` | currency | 16,10 | {"valueCurrency":{"amount":16.1,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[142].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.796 | [4] |
| `Items[142].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.392 | [4] |
| `Items[143].Amount` | currency | 12,71 | {"valueCurrency":{"amount":12.71,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[143].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.789 | [4] |
| `Items[143].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.302 | [4] |
| `Items[144].Amount` | currency | 19,66 | {"valueCurrency":{"amount":19.66,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[144].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.786 | [4] |
| `Items[144].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.395 | [4] |
| `Items[145].Amount` | currency | 164,05 | {"valueCurrency":{"amount":164.05,"currencyCode":"EUR"}} | 0.8 | [4] |
| `Items[145].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.793 | [4] |
| `Items[145].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.396 | [4] |
| `Items[146].Amount` | currency | 164,56 | {"valueCurrency":{"amount":164.56,"currencyCode":"EUR"}} | 0.798 | [4] |
| `Items[146].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.797 | [4] |
| `Items[146].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.449 | [4] |
| `Items[147].Amount` | currency | 507,59 | {"valueCurrency":{"amount":507.59,"currencyCode":"EUR"}} | 0.797 | [4] |
| `Items[147].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.791 | [4] |
| `Items[147].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.426 | [4] |
| `Items[148].Amount` | currency | 23,49 | {"valueCurrency":{"amount":23.49,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[148].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.795 | [4] |
| `Items[148].Description` | string | NETOS PLUS | {"valueString":"NETOS PLUS"} | 0.722 | [4] |
| `Items[149].Amount` | currency | 13,40 | {"valueCurrency":{"amount":13.4,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[149].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.796 | [4] |
| `Items[149].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.43 | [4] |
| `Items[150].Amount` | currency | 19,63 | {"valueCurrency":{"amount":19.63,"currencyCode":"EUR"}} | 0.801 | [4] |
| `Items[150].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.798 | [4] |
| `Items[150].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.426 | [4] |
| `Items[151].Amount` | currency | 302,56 | {"valueCurrency":{"amount":302.56,"currencyCode":"EUR"}} | 0.798 | [4] |
| `Items[151].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.79 | [4] |
| `Items[151].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.671 | [4] |
| `Items[152].Amount` | currency | 2,21 | {"valueCurrency":{"amount":2.21,"currencyCode":"EUR"}} | 0.802 | [4] |
| `Items[152].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.796 | [4] |
| `Items[152].Description` | string | NORMAL ACUSTICO | {"valueString":"NORMAL ACUSTICO"} | 0.413 | [4] |
| `TaxDetails` | array | None | {} | ? | [] |
| `TaxDetails[1].Amount` | currency | 573,16 | {"valueCurrency":{"amount":573.16,"currencyCode":"EUR"}} | 0.725 | [1] |
| `TotalTax` | currency | 573,16 | {"valueCurrency":{"amount":573.16,"currencyCode":"EUR"}} | 0.787 | [1] |
| `VendorName` | string | cencora ? Alliance Healthcare | {"valueString":"cencora\nAlliance Healthcare"} | 0.546 | [1] |

#### Tablas detectadas

| Tabla | Filas ? columnas | P?gina relativa | Celdas no vac?as |
|---:|---:|---|---:|
| 1 | 3 ? 2 | [1] | 6 |
| 2 | 2 ? 3 | [1] | 6 |
| 3 | 13 ? 11 | [1] | 49 |
| 4 | 4 ? 8 | [1] | 19 |
| 5 | 2 ? 2 | [1] | 4 |
| 6 | 2 ? 2 | [1] | 3 |
| 7 | 2 ? 3 | [2] | 6 |
| 8 | 59 ? 10 | [2] | 270 |
| 9 | 54 ? 10 | [3] | 260 |
| 10 | 64 ? 10 | [4] | 235 |

#### Duplicados exactos

| Content | Apariciones | Rutas |
|---|---:|---|
| PUIG SALOMON PIUS | 2 | CustomerAddressRecipient, CustomerName |
| 10-07-2026 | 10 | InvoiceDate, Items[6].Date, Items[8].Date, Items[146].Date, Items[147].Date, Items[148].Date, Items[149].Date, Items[150].Date, Items[151].Date, Items[152].Date |
| 1,69 | 3 | Items[7].Amount, Items[54].Amount, Items[124].Amount |
| 30-06-2026 | 2 | Items[7].Date, Items[9].Date |
| ACUSTICO | 12 | Items[7].Description, Items[12].Description, Items[13].Description, Items[14].Description, Items[21].Description, Items[23].Description, Items[24].Description, Items[30].Description, Items[32].Description, Items[41].Description, Items[44].Description, Items[45].Description |
| 1,32 | 3 | Items[9].Amount, Items[41].Amount, Items[115].Amount |
| NORMAL ACUSTICO | 114 | Items[9].Description, Items[10].Description, Items[11].Description, Items[15].Description, Items[16].Description, Items[17].Description, Items[19].Description, Items[20].Description, Items[25].Description, Items[26].Description, Items[27].Description, Items[28].Description, Items[31].Description, Items[33].Description, Items[34].Description, Items[35].Description, Items[36].Description, Items[37].Description, Items[38].Description, Items[39].Description, Items[42].Description, Items[43].Description, Items[46].Description, Items[47].Description, Items[48].Description, Items[49].Description, Items[50].Description, Items[52].Description, Items[58].Description, Items[59].Description, Items[60].Description, Items[61].Description, Items[62].Description, Items[63].Description, Items[64].Description, Items[65].Description, Items[66].Description, Items[67].Description, Items[68].Description, Items[69].Description, Items[71].Description, Items[72].Description, Items[73].Description, Items[74].Description, Items[75].Description, Items[76].Description, Items[77].Description, Items[78].Description, Items[79].Description, Items[80].Description, Items[81].Description, Items[82].Description, Items[83].Description, Items[84].Description, Items[85].Description, Items[86].Description, Items[88].Description, Items[89].Description, Items[90].Description, Items[91].Description, Items[92].Description, Items[93].Description, Items[95].Description, Items[96].Description, Items[97].Description, Items[98].Description, Items[99].Description, Items[100].Description, Items[101].Description, Items[102].Description, Items[103].Description, Items[104].Description, Items[105].Description, Items[107].Description, Items[108].Description, Items[109].Description, Items[110].Description, Items[111].Description, Items[112].Description, Items[113].Description, Items[115].Description, Items[116].Description, Items[117].Description, Items[118].Description, Items[119].Description, Items[120].Description, Items[121].Description, Items[122].Description, Items[123].Description, Items[124].Description, Items[125].Description, Items[127].Description, Items[128].Description, Items[130].Description, Items[131].Description, Items[132].Description, Items[133].Description, Items[134].Description, Items[135].Description, Items[137].Description, Items[138].Description, Items[139].Description, Items[140].Description, Items[141].Description, Items[142].Description, Items[143].Description, Items[144].Description, Items[145].Description, Items[146].Description, Items[147].Description, Items[149].Description, Items[150].Description, Items[151].Description, Items[152].Description |
| 01-07-2026 | 16 | Items[10].Date, Items[11].Date, Items[12].Date, Items[13].Date, Items[14].Date, Items[15].Date, Items[16].Date, Items[17].Date, Items[18].Date, Items[19].Date, Items[20].Date, Items[21].Date, Items[22].Date, Items[23].Date, Items[24].Date, Items[25].Date |
| 10,70 | 2 | Items[18].Amount, Items[136].Amount |
| NETOS PLUS | 14 | Items[18].Description, Items[22].Description, Items[29].Description, Items[40].Description, Items[51].Description, Items[70].Description, Items[87].Description, Items[94].Description, Items[106].Description, Items[114].Description, Items[126].Description, Items[129].Description, Items[136].Description, Items[148].Description |
| 02-07-2026 | 11 | Items[26].Date, Items[27].Date, Items[28].Date, Items[29].Date, Items[30].Date, Items[31].Date, Items[32].Date, Items[33].Date, Items[34].Date, Items[35].Date, Items[36].Date |
| 2,21 | 2 | Items[36].Amount, Items[152].Amount |
| 03-07-2026 | 12 | Items[37].Date, Items[38].Date, Items[39].Date, Items[40].Date, Items[41].Date, Items[42].Date, Items[43].Date, Items[44].Date, Items[45].Date, Items[46].Date, Items[47].Date, Items[48].Date |
| 61,87 | 2 | Items[43].Amount, Items[84].Amount |
| 04-07-2026 | 13 | Items[49].Date, Items[50].Date, Items[51].Date, Items[52].Date, Items[53].Date, Items[54].Date, Items[55].Date, Items[56].Date, Items[57].Date, Items[58].Date, Items[59].Date, Items[60].Date, Items[61].Date |
| 8,82 | 2 | Items[61].Amount, Items[89].Amount |
| 06-07-2026 | 27 | Items[63].Date, Items[64].Date, Items[65].Date, Items[66].Date, Items[67].Date, Items[68].Date, Items[69].Date, Items[70].Date, Items[71].Date, Items[72].Date, Items[73].Date, Items[74].Date, Items[75].Date, Items[76].Date, Items[77].Date, Items[78].Date, Items[79].Date, Items[80].Date, Items[81].Date, Items[82].Date, Items[83].Date, Items[84].Date, Items[85].Date, Items[86].Date, Items[87].Date, Items[88].Date, Items[89].Date |
| 19,66 | 2 | Items[81].Amount, Items[144].Amount |
| 07-07-2026 | 18 | Items[90].Date, Items[91].Date, Items[92].Date, Items[93].Date, Items[94].Date, Items[95].Date, Items[96].Date, Items[97].Date, Items[98].Date, Items[99].Date, Items[100].Date, Items[101].Date, Items[102].Date, Items[103].Date, Items[104].Date, Items[105].Date, Items[106].Date, Items[107].Date |
| 08-07-2026 | 19 | Items[108].Date, Items[109].Date, Items[110].Date, Items[111].Date, Items[112].Date, Items[113].Date, Items[114].Date, Items[115].Date, Items[116].Date, Items[117].Date, Items[118].Date, Items[119].Date, Items[120].Date, Items[121].Date, Items[122].Date, Items[123].Date, Items[124].Date, Items[125].Date, Items[126].Date |
| 09-07-2026 | 19 | Items[127].Date, Items[128].Date, Items[129].Date, Items[130].Date, Items[131].Date, Items[132].Date, Items[133].Date, Items[134].Date, Items[135].Date, Items[136].Date, Items[137].Date, Items[138].Date, Items[139].Date, Items[140].Date, Items[141].Date, Items[142].Date, Items[143].Date, Items[144].Date, Items[145].Date |
| 16,10 | 2 | Items[141].Amount, Items[142].Amount |
| 573,16 | 2 | TaxDetails[1].Amount, TotalTax |

### `08008429` ? p?ginas originales 8-9

| Campo | Esperado | Campo Azure | Valor Azure | Confianza | Clasificaci?n | Observaci?n |
|---|---|---|---|---:|---|---|
| `tipo_documento` | FACTURA | documents[].docType | invoice | 1 | **ENTIDAD AMBIGUA** | docType es invoice: identifica la clase del modelo, pero no devuelve literalmente FACTURA ni acredita distinci?n frente a ABONO. |
| `categoria` | MERCANCIA | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | No existe un campo nativo observado para la categor?a del patr?n. |
| `requiere_conciliacion_albaranes` | true | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | Indicador interno no disponible como campo nativo. |
| `pagina_inicio` | 8 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango original es metadato de la divisi?n, no una entidad extra?da. |
| `pagina_fin` | 9 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango original es metadato de la divisi?n, no una entidad extra?da. |
| `proveedor_nombre` | ALLIANCE HEALTHCARE ESPAÑA, S.A. | VendorName | cencora ? Alliance Healthcare | 0.644 | **PARCIAL** | Azure devuelve la marca cencora / Alliance Healthcare, pero no la raz?n social literal completa esperada. |
| `proveedor_cif` | A50004324 | ? | null | ? | **AUSENTE** | VendorTaxId no fue devuelto; no se toma el CIF desde OCR o tablas por inferencia. |
| `numero_factura` | 08008429 | InvoiceId | 08008429 | 0.973 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `fecha_factura` | 2026-07-10 | InvoiceDate | 2026-07-10 | 0.972 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `base_imponible_total` | 196.8 | SubTotal | 196.8 | 0.414 | **CORRECTO** | Coincidencia num?rica con el patr?n. Campo correcto con confianza baja (<0,50). |
| `iva_total` | 19.68 | TotalTax | 19.68 | 0.938 | **CORRECTO** | TotalTax coincide con iva_total; no incluye el recargo de equivalencia. |
| `recargo_equivalencia_total` | 2.76 | ? | {"texto_en_tabla_sin_campo_nativo":[{"tabla":6,"etiqueta":"TOTAL RECARGOS EQUIVALENCIA","valor_contiguo":"2,76","pagina_relativa":1}]} | ? | **AUSENTE** | No hay campo estructurado de recargo. La tabla puede conservar el texto, pero TotalTax contiene solo IVA y no se mezcla con el recargo. |
| `importe_total` | 219.24 | InvoiceTotal | 219.24 | 0.933 | **CORRECTO** | Coincidencia num?rica con el patr?n. |
| `vencimientos` | [{"orden":1,"fecha_vencimiento":"2026-10-10","importe":219.24}] | DueDate | {"fechas":["2026-10-10"],"importes":[]} | 0.969 | **PARCIAL** | DueDate coincide con la ?nica fecha esperada, pero Azure no devuelve el importe del vencimiento. No hay vencimientos m?ltiples en estas cuatro muestras. |
| `impuestos` | [{"orden":1,"base_imponible":196.8,"tipo_iva":10.0,"cuota_iva":19.68,"tipo_recargo_equivalencia":1.4,"cuota_recargo_equivalencia":2.76}] | TaxDetails | {"nombre_campo":"TaxDetails","tipo":"array","content":null,"valor_normalizado":{},"confianza":null,"paginas_relativas":[],"elementos":[{"indice":1,"content":"TOTAL IVAS\n19,68","confianza":0.776,"paginas_relativas":[1],"propiedades":{"Amount":{"nombre_campo":? | ? | **PARCIAL** | TaxDetails contiene solo Amount; faltan bases, tipos IVA y todos los datos de recargo. Algunos Items clasifican cifras fiscales de forma incorrecta. |
| `albaranes` | [{"orden":1,"numero_albaran":"08M30618","fecha_albaran":"2026-07-02","tipo_movimiento":"CARGO","descripcion":"COSTO LABORAT.","importe_base":196.8,"importe_total":219.24}] | Items y tablas | {"items_detectados":3,"product_codes":[],"identificadores_esperados_en_product_code":[],"identificadores_esperados_en_tablas":["08M30618"],"cantidad_esperada":1} | ? | **PARCIAL** | Items recupera principalmente fechas e importes y pocos ProductCode; las tablas conservan m?s n?meros, pero no existe una estructura completa y fiable de n?mero, fecha, movimiento, descripci?n, base y total. |
| `ajustes` | [] | ? | [] | ? | **CORRECTO** | El patr?n no espera ajustes y Azure no devuelve un campo espec?fico de ajustes. |
| `destinatario` | {"id_farmacia":"PIO","nombre":"FARMACIA PIO PUIG","cif":"40901058C","metodo_identificacion":"CIF"} | ['CustomerName', 'CustomerTaxId', 'CustomerAddress', 'CustomerAddressRecipient'] | {"CustomerName":{"nombre_campo":"CustomerName","tipo":"string","content":"PUIG SALOMON PIUS","valor_normalizado":{"valueString":"PUIG SALOMON PIUS"},"confianza":0.915,"paginas_relativas":[1]},"CustomerTaxId":{"nombre_campo":"CustomerTaxId","tipo":"string","co? | [0.915,0.649,0.723,0.915] | **PARCIAL** | CustomerTaxId coincide con el CIF esperado, pero CustomerName no coincide literalmente con el nombre del patr?n y faltan id_farmacia y metodo_identificacion. |

#### Inventario completo de campos Azure

> Las p?ginas son relativas al PDF separado. Items y TaxDetails incluyen todas sus propiedades hijas en el JSON; aqu? cada elemento se presenta en una fila compacta.

| Campo/elemento | Tipo | Content | Valor normalizado | Confianza | P?gina relativa |
|---|---|---|---|---:|---|
| `CustomerAddress` | address | CR SANT LLUC 34 ? 43550 ULLDECONA ? RUTA 16 | {"valueAddress":{"houseNumber":"34","road":"CR SANT LLUC","postalCode":"43550","city":"ULLDECONA","streetAddress":"34 CR SANT LLUC"}} | 0.723 | [1] |
| `CustomerAddressRecipient` | string | PUIG SALOMON PIUS | {"valueString":"PUIG SALOMON PIUS"} | 0.915 | [1] |
| `CustomerName` | string | PUIG SALOMON PIUS | {"valueString":"PUIG SALOMON PIUS"} | 0.915 | [1] |
| `CustomerTaxId` | string | 40901058C | {"valueString":"40901058C"} | 0.649 | [1] |
| `DueDate` | date | 10-10-2026 | {"valueDate":"2026-10-10"} | 0.969 | [2] |
| `InvoiceDate` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.972 | [2] |
| `InvoiceId` | string | 08008429 | {"valueString":"08008429"} | 0.973 | [2] |
| `InvoiceTotal` | currency | 219,24 | {"valueCurrency":{"amount":219.24,"currencyCode":"EUR"}} | 0.933 | [1] |
| `Items` | array | None | {} | ? | [] |
| `Items[1].Amount` | currency | 5,20 | {"valueCurrency":{"amount":5.2,"currencyCode":"EUR"}} | 0.915 | [1] |
| `Items[1].Description` | string | CONCEPTO | {"valueString":"CONCEPTO"} | 0.73 | [1] |
| `Items[1].Tax` | currency | 10 | {"valueCurrency":{"amount":10.0,"currencyCode":"EUR"}} | 0.703 | [1] |
| `Items[1].TaxRate` | string | 21 | {"valueString":"21"} | 0.374 | [1] |
| `Items[2].Amount` | currency | 219,24 | {"valueCurrency":{"amount":219.24,"currencyCode":"EUR"}} | 0.918 | [1] |
| `Items[2].Description` | string | NO ESPECIALIDAD | {"valueString":"NO ESPECIALIDAD"} | 0.885 | [1] |
| `Items[2].Tax` | currency | 19,68 | {"valueCurrency":{"amount":19.68,"currencyCode":"EUR"}} | 0.852 | [1] |
| `Items[3].Amount` | currency | 219,24 | {"valueCurrency":{"amount":219.24,"currencyCode":"EUR"}} | 0.476 | [2] |
| `Items[3].Date` | date | 02-07-2026 | {"valueDate":"2026-07-02"} | 0.84 | [2] |
| `SubTotal` | currency | 196,80 | {"valueCurrency":{"amount":196.8,"currencyCode":"EUR"}} | 0.414 | [1] |
| `TaxDetails` | array | None | {} | ? | [] |
| `TaxDetails[1].Amount` | currency | 19,68 | {"valueCurrency":{"amount":19.68,"currencyCode":"EUR"}} | 0.803 | [1] |
| `TotalTax` | currency | 19,68 | {"valueCurrency":{"amount":19.68,"currencyCode":"EUR"}} | 0.938 | [1] |
| `VendorName` | string | cencora ? Alliance Healthcare | {"valueString":"cencora\nAlliance Healthcare"} | 0.644 | [1] |

#### Tablas detectadas

| Tabla | Filas ? columnas | P?gina relativa | Celdas no vac?as |
|---:|---:|---|---:|
| 1 | 3 ? 2 | [1] | 6 |
| 2 | 2 ? 3 | [1] | 6 |
| 3 | 23 ? 11 | [1] | 25 |
| 4 | 4 ? 8 | [1] | 13 |
| 5 | 2 ? 2 | [1] | 4 |
| 6 | 2 ? 2 | [1] | 3 |
| 7 | 2 ? 3 | [2] | 6 |
| 8 | 76 ? 10 | [2] | 15 |

#### Duplicados exactos

| Content | Apariciones | Rutas |
|---|---:|---|
| PUIG SALOMON PIUS | 2 | CustomerAddressRecipient, CustomerName |
| 219,24 | 3 | InvoiceTotal, Items[2].Amount, Items[3].Amount |
| 19,68 | 3 | Items[2].Tax, TaxDetails[1].Amount, TotalTax |

### `08008430` ? p?ginas originales 10-11

| Campo | Esperado | Campo Azure | Valor Azure | Confianza | Clasificaci?n | Observaci?n |
|---|---|---|---|---:|---|---|
| `tipo_documento` | FACTURA | documents[].docType | invoice | 1 | **ENTIDAD AMBIGUA** | docType es invoice: identifica la clase del modelo, pero no devuelve literalmente FACTURA ni acredita distinci?n frente a ABONO. |
| `categoria` | MERCANCIA | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | No existe un campo nativo observado para la categor?a del patr?n. |
| `requiere_conciliacion_albaranes` | true | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | Indicador interno no disponible como campo nativo. |
| `pagina_inicio` | 10 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango original es metadato de la divisi?n, no una entidad extra?da. |
| `pagina_fin` | 11 | ? | null | ? | **NO DISPONIBLE DE FORMA NATIVA** | El rango original es metadato de la divisi?n, no una entidad extra?da. |
| `proveedor_nombre` | ALLIANCE HEALTHCARE ESPAÑA, S.A. | VendorName | cencora ? Alliance Healthcare | 0.652 | **PARCIAL** | Azure devuelve la marca cencora / Alliance Healthcare, pero no la raz?n social literal completa esperada. |
| `proveedor_cif` | A50004324 | ? | null | ? | **AUSENTE** | VendorTaxId no fue devuelto; no se toma el CIF desde OCR o tablas por inferencia. |
| `numero_factura` | 08008430 | InvoiceId | 08008430 | 0.969 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `fecha_factura` | 2026-07-10 | InvoiceDate | 2026-07-10 | 0.969 | **CORRECTO** | Coincidencia literal/normalizada con el patr?n. |
| `base_imponible_total` | 144.67 | SubTotal | 144.67 | 0.551 | **CORRECTO** | Coincidencia num?rica con el patr?n. |
| `iva_total` | 15.59 | TotalTax | 15.59 | 0.95 | **CORRECTO** | TotalTax coincide con iva_total; no incluye el recargo de equivalencia. |
| `recargo_equivalencia_total` | 2.41 | ? | {"texto_en_tabla_sin_campo_nativo":[{"tabla":6,"etiqueta":"TOTAL RECARGOS EQUIVALENCIA","valor_contiguo":"2,41","pagina_relativa":1}]} | ? | **AUSENTE** | No hay campo estructurado de recargo. La tabla puede conservar el texto, pero TotalTax contiene solo IVA y no se mezcla con el recargo. |
| `importe_total` | 162.67 | InvoiceTotal | 162.67 | 0.94 | **CORRECTO** | Coincidencia num?rica con el patr?n. |
| `vencimientos` | [{"orden":1,"fecha_vencimiento":"2026-11-06","importe":162.67}] | DueDate | {"fechas":["2026-11-06"],"importes":[]} | 0.966 | **PARCIAL** | DueDate coincide con la ?nica fecha esperada, pero Azure no devuelve el importe del vencimiento. No hay vencimientos m?ltiples en estas cuatro muestras. |
| `impuestos` | [{"orden":1,"base_imponible":134.47,"tipo_iva":10.0,"cuota_iva":13.45,"tipo_recargo_equivalencia":1.4,"cuota_recargo_equivalencia":1.88},{"orden":2,"base_imponible":10.2,"tipo_iva":21.0,"cuota_iva":2.14,"tipo_recargo_equivalencia":5.2,"cuota_recargo_equivalen? | TaxDetails | {"nombre_campo":"TaxDetails","tipo":"array","content":null,"valor_normalizado":{},"confianza":null,"paginas_relativas":[],"elementos":[{"indice":1,"content":"TOTAL IVAS\n15,59","confianza":0.854,"paginas_relativas":[1],"propiedades":{"Amount":{"nombre_campo":? | ? | **PARCIAL** | TaxDetails contiene solo Amount; faltan bases, tipos IVA y todos los datos de recargo. Algunos Items clasifican cifras fiscales de forma incorrecta. |
| `albaranes` | [{"orden":1,"numero_albaran":"08C26323","fecha_albaran":"2026-06-30","tipo_movimiento":"CARGO","descripcion":"ECOCEUTICS","importe_base":19.73,"importe_total":21.98},{"orden":2,"numero_albaran":"08C27758","fecha_albaran":"2026-07-01","tipo_movimiento":"CARGO"? | Items y tablas | {"items_detectados":10,"product_codes":[],"identificadores_esperados_en_product_code":[],"identificadores_esperados_en_tablas":["08C26323","08C27758","08C29987","08C31639","08C32804","08C33369","08M35864","08C37655"],"cantidad_esperada":8} | ? | **PARCIAL** | Items recupera principalmente fechas e importes y pocos ProductCode; las tablas conservan m?s n?meros, pero no existe una estructura completa y fiable de n?mero, fecha, movimiento, descripci?n, base y total. |
| `ajustes` | [] | ? | [] | ? | **CORRECTO** | El patr?n no espera ajustes y Azure no devuelve un campo espec?fico de ajustes. |
| `destinatario` | {"id_farmacia":"PIO","nombre":"FARMACIA PIO PUIG","cif":"40901058C","metodo_identificacion":"CIF"} | ['CustomerName', 'CustomerTaxId', 'CustomerAddress', 'CustomerAddressRecipient'] | {"CustomerName":{"nombre_campo":"CustomerName","tipo":"string","content":"PUIG SALOMON PIUS","valor_normalizado":{"valueString":"PUIG SALOMON PIUS"},"confianza":0.918,"paginas_relativas":[1]},"CustomerTaxId":{"nombre_campo":"CustomerTaxId","tipo":"string","co? | [0.918,0.655,0.723,0.918] | **PARCIAL** | CustomerTaxId coincide con el CIF esperado, pero CustomerName no coincide literalmente con el nombre del patr?n y faltan id_farmacia y metodo_identificacion. |

#### Inventario completo de campos Azure

> Las p?ginas son relativas al PDF separado. Items y TaxDetails incluyen todas sus propiedades hijas en el JSON; aqu? cada elemento se presenta en una fila compacta.

| Campo/elemento | Tipo | Content | Valor normalizado | Confianza | P?gina relativa |
|---|---|---|---|---:|---|
| `CustomerAddress` | address | CR SANT LLUC 34 ? 43550 ULLDECONA ? RUTA 16 | {"valueAddress":{"houseNumber":"34","road":"CR SANT LLUC","postalCode":"43550","city":"ULLDECONA","streetAddress":"34 CR SANT LLUC"}} | 0.723 | [1] |
| `CustomerAddressRecipient` | string | PUIG SALOMON PIUS | {"valueString":"PUIG SALOMON PIUS"} | 0.918 | [1] |
| `CustomerName` | string | PUIG SALOMON PIUS | {"valueString":"PUIG SALOMON PIUS"} | 0.918 | [1] |
| `CustomerTaxId` | string | 40901058C | {"valueString":"40901058C"} | 0.655 | [1] |
| `DueDate` | date | 06-11-2026 | {"valueDate":"2026-11-06"} | 0.966 | [2] |
| `InvoiceDate` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.969 | [2] |
| `InvoiceId` | string | 08008430 | {"valueString":"08008430"} | 0.969 | [2] |
| `InvoiceTotal` | currency | 162,67 | {"valueCurrency":{"amount":162.67,"currencyCode":"EUR"}} | 0.94 | [1] |
| `Items` | array | None | {} | ? | [] |
| `Items[1].Tax` | currency | 10 | {"valueCurrency":{"amount":10.0,"currencyCode":"EUR"}} | 0.101 | [1] |
| `Items[1].TaxRate` | string | 21 | {"valueString":"21"} | 0.278 | [1] |
| `Items[2].Amount` | currency | 162,67 | {"valueCurrency":{"amount":162.67,"currencyCode":"EUR"}} | 0.911 | [1] |
| `Items[2].Description` | string | NO ESPECIALIDAD | {"valueString":"NO ESPECIALIDAD"} | 0.722 | [1] |
| `Items[2].Tax` | currency | 13,45 ? 2,14 | {"valueCurrency":{"amount":13.45,"currencyCode":"EUR"}} | 0.673 | [1] |
| `Items[3].Amount` | currency | 21,98 | {"valueCurrency":{"amount":21.98,"currencyCode":"EUR"}} | 0.83 | [2] |
| `Items[3].Date` | date | 30-06-2026 | {"valueDate":"2026-06-30"} | 0.836 | [2] |
| `Items[4].Amount` | currency | 48,13 | {"valueCurrency":{"amount":48.13,"currencyCode":"EUR"}} | 0.842 | [2] |
| `Items[4].Date` | date | 01-07-2026 | {"valueDate":"2026-07-01"} | 0.84 | [2] |
| `Items[5].Amount` | currency | 14,88 | {"valueCurrency":{"amount":14.88,"currencyCode":"EUR"}} | 0.828 | [2] |
| `Items[5].Date` | date | 03-07-2026 | {"valueDate":"2026-07-03"} | 0.848 | [2] |
| `Items[6].Amount` | currency | 14,88 | {"valueCurrency":{"amount":14.88,"currencyCode":"EUR"}} | 0.832 | [2] |
| `Items[6].Date` | date | 05-07-2026 | {"valueDate":"2026-07-05"} | 0.848 | [2] |
| `Items[7].Amount` | currency | 22,02 | {"valueCurrency":{"amount":22.02,"currencyCode":"EUR"}} | 0.845 | [2] |
| `Items[7].Date` | date | 06-07-2026 | {"valueDate":"2026-07-06"} | 0.846 | [2] |
| `Items[8].Amount` | currency | 13,05 | {"valueCurrency":{"amount":13.05,"currencyCode":"EUR"}} | 0.842 | [2] |
| `Items[8].Date` | date | 07-07-2026 | {"valueDate":"2026-07-07"} | 0.848 | [2] |
| `Items[9].Amount` | currency | 8,52 | {"valueCurrency":{"amount":8.52,"currencyCode":"EUR"}} | 0.833 | [2] |
| `Items[9].Date` | date | 09-07-2026 | {"valueDate":"2026-07-09"} | 0.846 | [2] |
| `Items[10].Amount` | currency | 19,23 | {"valueCurrency":{"amount":19.23,"currencyCode":"EUR"}} | 0.841 | [2] |
| `Items[10].Date` | date | 10-07-2026 | {"valueDate":"2026-07-10"} | 0.848 | [2] |
| `SubTotal` | currency | 144,67 | {"valueCurrency":{"amount":144.67,"currencyCode":"EUR"}} | 0.551 | [1] |
| `TaxDetails` | array | None | {} | ? | [] |
| `TaxDetails[1].Amount` | currency | 15,59 | {"valueCurrency":{"amount":15.59,"currencyCode":"EUR"}} | 0.911 | [1] |
| `TotalTax` | currency | 15,59 | {"valueCurrency":{"amount":15.59,"currencyCode":"EUR"}} | 0.95 | [1] |
| `VendorName` | string | cencora ? Alliance Healthcare | {"valueString":"cencora\nAlliance Healthcare"} | 0.652 | [1] |

#### Tablas detectadas

| Tabla | Filas ? columnas | P?gina relativa | Celdas no vac?as |
|---:|---:|---|---:|
| 1 | 3 ? 2 | [1] | 6 |
| 2 | 2 ? 3 | [1] | 6 |
| 3 | 26 ? 11 | [1] | 31 |
| 4 | 4 ? 8 | [1] | 13 |
| 5 | 2 ? 2 | [1] | 4 |
| 6 | 2 ? 2 | [1] | 3 |
| 7 | 74 ? 10 | [2] | 50 |

#### Duplicados exactos

| Content | Apariciones | Rutas |
|---|---:|---|
| PUIG SALOMON PIUS | 2 | CustomerAddressRecipient, CustomerName |
| 10-07-2026 | 2 | InvoiceDate, Items[10].Date |
| 162,67 | 2 | InvoiceTotal, Items[2].Amount |
| 14,88 | 2 | Items[5].Amount, Items[6].Amount |
| 15,59 | 2 | TaxDetails[1].Amount, TotalTax |

## Resultados por campo

| Campo | Total | Correcto | Incorrecto | Ausente | Parcial | Ambiguo | No nativo |
|---|---:|---:|---:|---:|---:|---:|---:|
| `tipo_documento` | 4 | 0 | 0 | 0 | 0 | 4 | 0 |
| `categoria` | 4 | 0 | 0 | 0 | 0 | 0 | 4 |
| `requiere_conciliacion_albaranes` | 4 | 0 | 0 | 0 | 0 | 0 | 4 |
| `pagina_inicio` | 4 | 0 | 0 | 0 | 0 | 0 | 4 |
| `pagina_fin` | 4 | 0 | 0 | 0 | 0 | 0 | 4 |
| `proveedor_nombre` | 4 | 0 | 0 | 0 | 4 | 0 | 0 |
| `proveedor_cif` | 4 | 0 | 0 | 4 | 0 | 0 | 0 |
| `numero_factura` | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| `fecha_factura` | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| `base_imponible_total` | 4 | 2 | 0 | 2 | 0 | 0 | 0 |
| `iva_total` | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| `recargo_equivalencia_total` | 4 | 0 | 0 | 4 | 0 | 0 | 0 |
| `importe_total` | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| `vencimientos` | 4 | 0 | 0 | 0 | 4 | 0 | 0 |
| `impuestos` | 4 | 0 | 0 | 0 | 2 | 2 | 0 |
| `albaranes` | 4 | 0 | 0 | 0 | 4 | 0 | 0 |
| `ajustes` | 4 | 3 | 0 | 0 | 1 | 0 | 0 |
| `destinatario` | 4 | 0 | 0 | 0 | 4 | 0 | 0 |

## Resultados por factura

| Factura | P?ginas | Total | Correcto | Incorrecto | Ausente | Parcial | Ambiguo | No nativo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `08008428` | 1-3 | 18 | 5 | 0 | 3 | 4 | 2 | 4 |
| `08008427` | 4-7 | 18 | 4 | 0 | 3 | 5 | 2 | 4 |
| `08008429` | 8-9 | 18 | 6 | 0 | 2 | 5 | 1 | 4 |
| `08008430` | 10-11 | 18 | 6 | 0 | 2 | 5 | 1 | 4 |

## Criterio de parada

El an?lisis termina aqu?. No se ha creado ninguna normalizaci?n ni regla de transformaci?n.
