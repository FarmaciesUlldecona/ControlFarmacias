# ALLIANCE — microhito final de rol, relaciones y sentido

Estado: `LOCAL_COMPLETO` para `ALLIANCE_FACTURA_DENSO_V1`, con `alliance-local@1.0.0`, únicamente local y sin autoridad productiva.

El replay ciego procesó dos PDFs, 22 páginas y siete facturas internas. Conservó 527 candidatos: cero se promueven a `DETALLE_ALBARAN` y 527 permanecen `INDETERMINADO`, porque el documento no aporta evidencia estructural positiva de rol. No existen reglas por ID, prefijo, `DIRECT`, signo, orden, posición ni gold.

Se conservaron seis movimientos y se crearon tres relaciones documentales candidato/movimiento mediante base y total exactos y únicos dentro de una misma factura. La relación mantiene la identidad, página, región, evidencia y provenance de ambos objetos. No fusiona, elimina, deduplica ni transfiere rol, categoría o sentido.

Los movimientos aparecen geométricamente bajo `COMPRAS` o `GASTOS`. Ninguno pertenece a una sección explícita `CARGO(S)` o `ABONO(S)`, por lo que los seis mantienen `sentido=null` y `SENTIDO_NO_DOCUMENTADO`. Esto incluye `RAPPEL GenerAH`, `ABONOS CLUBS`, `SERV.PLATAF.360`, ambos `SERVICIO BASICO` y `CONDIC. COMERCIAL`. En cambio, las filas candidatas sí conservan su sentido documental de la tabla paralela `CARGOS/ABONOS`, sin que ello determine su rol.

El freeze separado reproduce 3/3 ejecuciones idénticas por PDF. Conserva 20 tramos fiscales, 22 ocurrencias de vencimiento, 21 conciliaciones `OK`, 14 `NO_EVALUABLE` y cero diferencias. La evaluación posterior contra gold no modificó el freeze: candidatos 276/3/0, movimientos 4/1/0, relaciones 3/0/0, roles fuertes 0/0/276 y sentidos de movimiento 0/0/4.

Validación final: focales 25, motor local 69, Normalizador V2 + motor 276 y suite completa de facturas 592; regresiones 0. Luna/API/Google/web/OCR: 0. PDFs o corpus en la allowlist: 0. Git add/commit/push: no.
