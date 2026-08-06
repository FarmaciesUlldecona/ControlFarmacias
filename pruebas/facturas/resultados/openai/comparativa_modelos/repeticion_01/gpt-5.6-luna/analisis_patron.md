# Comparacion local de gpt-5.6-luna con el patron oficial

## Alcance y criterio

Se localizo una unica coincidencia para `08008427` en `$.documentos[3].facturas[1]`. Se comparo exclusivamente esa factura, correspondiente a las paginas originales 4-7. No se aplicaron inferencias ni reglas correctoras.

Los cuatro campos opcionales de Luna que no existen en el registro del patron se clasifican como NO EVALUABLE y se excluyen de los porcentajes. Acierto estricto = CORRECTO / evaluados. Cobertura = (CORRECTO + INCORRECTO + PARCIAL) / evaluados; INVENTADO no cuenta como cobertura valida.

## Resumen

| Metrica | Resultado |
|---|---:|
| Campos evaluados | 18 |
| Correctos | 9 |
| Incorrectos | 4 |
| Ausentes | 0 |
| Parciales | 3 |
| Inventados | 2 |
| No evaluables (fuera del denominador) | 4 |
| Acierto estricto | 50.00 % |
| Cobertura | 88.89 % |

## Resultado por campo

| Campo | Clasificacion | Esperado | Luna | Observacion |
|---|---|---|---|---|
| `tipo_documento` | CORRECTO | "FACTURA" | "FACTURA" | Coincidencia literal; FACTURA es visible. |
| `categoria` | INVENTADO | "MERCANCIA" | "MERCANCIA" | MERCANCIA coincide con el patron, pero esa categoria no aparece literalmente; COMPRAS no acredita por si solo MERCANCIA. |
| `requiere_conciliacion_albaranes` | INVENTADO | true | true | El booleano coincide con el patron, pero no es un dato literal del PDF; CARGOS/ABONOS no expresa este indicador. |
| `pagina_inicio` | INCORRECTO | 4 | 1 | Luna devolvio 1, pagina relativa correcta del PDF dividido, frente a la pagina original 4 exigida por el patron. |
| `pagina_fin` | INCORRECTO | 7 | 4 | Luna devolvio 4, pagina relativa correcta del PDF dividido, frente a la pagina original 7 exigida por el patron. |
| `proveedor_nombre` | CORRECTO | "ALLIANCE HEALTHCARE ESPAÑA, S.A." | "ALLIANCE HEALTHCARE ESPAÑA, S.A." | Coincidencia literal con el patron. |
| `proveedor_cif` | CORRECTO | "A50004324" | "A50004324" | Coincidencia literal con el patron. |
| `numero_factura` | CORRECTO | "08008427" | "08008427" | Coincidencia literal con el patron. |
| `fecha_factura` | CORRECTO | "2026-07-10" | "2026-07-10" | Coincidencia literal con el patron. |
| `base_imponible_total` | CORRECTO | 10531.42 | 10531.42 | Coincidencia literal con el patron. |
| `iva_total` | CORRECTO | 573.16 | 573.16 | Coincidencia literal con el patron. |
| `recargo_equivalencia_total` | CORRECTO | 80.52 | 80.52 | Coincidencia literal con el patron. |
| `importe_total` | CORRECTO | 11185.1 | 11185.1 | Coincidencia literal con el patron. |
| `vencimientos` | PARCIAL | [{"orden": 1, "fecha_vencimiento": "2026-10-06", "importe": 11185.1}] | [{"orden": 1, "fecha_vencimiento": "2026-10-06", "importe": null, "nota": null}] | Fecha y orden correctos; falta el importe 11185.10 y, por ello, la relacion fecha-importe queda incompleta. |
| `impuestos` | INCORRECTO | [] | [{"orden": 1, "base_imponible": 8548.52, "tipo_iva": 4.0, "cuota_iva": 341.94, "tipo_recargo_equivalencia":... | El patron exige una lista vacia. Luna genero cuatro elementos desde tablas visibles; el cuarto corresponde a SERVICIO BASICO y esta mal clasificado como impuesto. |
| `albaranes` | PARCIAL | [{"orden": 1, "numero_albaran": "08C26499", "fecha_albaran": "2026-06-30", "tipo_movimiento": "CARGO", "des... | [{"orden": 1, "numero_albaran": "08C26499", "fecha_albaran": "2026-06-30", "tipo_movimiento": "CARGO", "des... | Extrajo 4 de 147 albaranes. Los cuatro extraidos coinciden en numero, orden, fecha, movimiento, descripcion, base y total; faltan 143. |
| `ajustes` | INCORRECTO | [{"orden": 1, "tipo_ajuste": "GASTO", "descripcion": "Servicio básico", "importe": 31.46, "incluido_en_base... | [{"orden": 1, "tipo_ajuste": "DEDUCCION", "descripcion": null, "importe": -19.02, "incluido_en_base": null,... | No detecto el ajuste GASTO / Servicio basico / 31.46. Creo dos ajustes DEDUCCION (-19.02 y -6.13) y clasifico Servicio basico dentro de impuestos. |
| `destinatario` | PARCIAL | {"id_farmacia": "PIO", "nombre": "FARMACIA PIO PUIG", "cif": "40901058C", "metodo_identificacion": "CIF"} | {"id_farmacia": "006600", "nombre": "PUIG SALOMON PIUS", "cif": "40901058C", "metodo_identificacion": "NIF"} | CIF correcto. ID, nombre y metodo no coinciden: 006600 vs PIO; PUIG SALOMON PIUS vs FARMACIA PIO PUIG; NIF vs CIF. No confundio el destinatario con el proveedor. |
| `fecha_cargo` | NO EVALUABLE | null | null | Campo presente en el esquema de Luna pero ausente del registro de factura del patron; Luna devolvio null. |
| `periodo_facturacion_inicio` | NO EVALUABLE | null | null | Campo presente en el esquema de Luna pero ausente del registro de factura del patron; Luna devolvio null. |
| `periodo_facturacion_fin` | NO EVALUABLE | null | null | Campo presente en el esquema de Luna pero ausente del registro de factura del patron; Luna devolvio null. |
| `nota_revision` | NO EVALUABLE | null | null | Campo presente en el esquema de Luna pero ausente del registro de factura del patron; Luna devolvio null. |

## Metricas por grupo

| Grupo | Evaluados | Correctos | Incorrectos | Ausentes | Parciales | Inventados | Acierto | Cobertura |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cabecera_y_totales | 13 | 9 | 2 | 0 | 0 | 2 | 69.23 % | 84.62 % |
| impuestos | 1 | 0 | 1 | 0 | 0 | 0 | 0.00 % | 100.00 % |
| vencimientos | 1 | 0 | 0 | 0 | 1 | 0 | 0.00 % | 100.00 % |
| albaranes | 1 | 0 | 0 | 0 | 1 | 0 | 0.00 % | 100.00 % |
| ajustes | 1 | 0 | 1 | 0 | 0 | 0 | 0.00 % | 100.00 % |
| destinatario | 1 | 0 | 0 | 0 | 1 | 0 | 0.00 % | 100.00 % |

## Comprobaciones expresas

- Evidencias: 76 citas revisadas contra el texto de las paginas originales 4-7. 50 son cadenas contiguas literales, 26 combinan fragmentos visibles de la pagina y 0 no pudieron localizarse.
- Datos inventados: `categoria=MERCANCIA` y `requiere_conciliacion_albaranes=true` coinciden casualmente con el patron, pero no aparecen literalmente ni quedan acreditados por sus evidencias. Se clasifican INVENTADO.
- Proveedor/destinatario: no estan confundidos. El proveedor es correcto. En destinatario solo coincide el CIF; el resto difiere del patron.
- Recargo de equivalencia: el total 80.52 es correcto y esta respaldado por el importe visible 80,52. Los tres tipos y cuotas incluidos en el desglose de Luna tambien proceden de la tabla visible, aunque el patron no exige elementos en `impuestos`.
- Vencimiento: la fecha 2026-10-06 es correcta, pero el importe 11185.10 esta ausente y no queda relacionada la fecha con su importe.
- Albaranes: el patron espera 147; Luna extrajo 4. Los cuatro extraidos coinciden completamente; faltan 143.
- Ajuste: no detecto correctamente `GASTO / Servicio basico / 31.46`. El concepto aparece dividido como base 26.00 y IVA 5.46 dentro de `impuestos`; los ajustes devueltos son dos deducciones distintas.

## Albaranes extraidos

| Orden | Numero | Fecha | Movimiento | Descripcion | Base | Total | Resultado |
|---:|---|---|---|---|---:|---:|---|
| 1 | 08C26499 | 2026-06-30 | CARGO | NORMAL ACUSTICO | 1.62 | 1.69 | CORRECTO |
| 2 | 08C38230 | 2026-07-10 | ABONO | ABONOS AGRUPADOS | -8.29 | -8.66 | CORRECTO |
| 3 | 08C26500 | 2026-06-30 | CARGO | NORMAL ACUSTICO | 1.26 | 1.32 | CORRECTO |
| 4 | 08C38231 | 2026-07-10 | ABONO | ABONOS AGRUPADOS | -34.54 | -36.09 | CORRECTO |

### Albaranes ausentes

`08C27035`, `08C27265`, `08C27268`, `08C27311`, `08C27437`, `08C27700`, `08C27725`, `08C27896`, `08C27900`, `08M29400`, `08M29624`, `08M29915`, `08M29918`, `08M29976`, `08M30003`, `08M30063`, `08C28370`, `08C28452`, `08C28650`, `08C28658`, `08C28814`, `08C29133`, `08C29302`, `08M30406`, `08M30761`, `08M30914`, `08M30924`, `08C29766`, `08C29780`, `08C29977`, `08C29988`, `08C29989`, `08C30585`, `08M31275`, `08M31303`, `08M31366`, `08M31836`, `08M31892`, `08M31914`, `08C30750`, `08C30762`, `08C30798`, `08C30821`, `08C30958`, `08C31034`, `08C31135`, `08C31297`, `08C31301`, `08C31302`, `08C31489`, `08M32051`, `08V19185`, `08C31638`, `08C32023`, `08C32131`, `08C32157`, `08C32269`, `08C32270`, `08C32342`, `08C32348`, `08C32355`, `08C32356`, `08C32802`, `08C32805`, `08C32806`, `08C32824`, `08C32854`, `08C32877`, `08C32878`, `08C33027`, `08M32213`, `08M32226`, `08M32414`, `08M32604`, `08M32607`, `08M32612`, `08M32962`, `08M32963`, `08M32977`, `08V19262`, `08C33364`, `08C33510`, `08C33655`, `08C33660`, `08C33667`, `08C33697`, `08C34216`, `08C34434`, `08C34451`, `08M33392`, `08M33628`, `08M33646`, `08M33656`, `08M33699`, `08M33871`, `08M33960`, `08M33962`, `08M34050`, `08C34793`, `08C34914`, `08C34941`, `08C34961`, `08C34993`, `08C35060`, `08C35062`, `08C35063`, `08C35281`, `08C35567`, `08C35706`, `08M34186`, `08M34243`, `08M34283`, `08M34323`, `08M34347`, `08M34834`, `08M34837`, `08M34838`, `08C36031`, `08C36225`, `08C36245`, `08C36330`, `08C36335`, `08C36624`, `08C36870`, `08C36940`, `08C37045`, `08C37049`, `08C37065`, `08M35430`, `08M35555`, `08M35630`, `08M35691`, `08M35692`, `08M35806`, `08M35828`, `08M35863`, `08C37482`, `08C37653`, `08C37656`, `08C37737`, `08M36292`, `08M36757`, `08M36770`

## Coste

- Coste real estimado de esta extraccion: **0.034339 USD**.
- Proyeccion lineal para 60 facturas similares: **2.060340 USD**.
- La proyeccion supone el mismo consumo de tokens y la misma tarifa; no incorpora variacion en longitud o complejidad documental.

## Conclusion

Luna es muy precisa en cabecera y totales visibles, incluido el recargo de equivalencia. Su principal limitacion en esta factura es la cobertura: solo recupera 4 de 147 albaranes, deja incompleto el vencimiento y no representa el ajuste de Servicio basico conforme al patron. Ademas, emite dos campos de negocio no literalmente acreditados y confunde el ajuste con un renglon fiscal.
