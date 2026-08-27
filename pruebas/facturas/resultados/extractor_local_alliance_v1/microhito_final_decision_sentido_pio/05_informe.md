# ALLIANCE — cierre final de sentido por decisión funcional Pio

Estado: `LOCAL_COMPLETO` para `ALLIANCE_FACTURA_DENSO_V1`, con `alliance-local@1.0.0`, local y sin autoridad productiva.

Los seis movimientos conservan sentido final. `RAPPEL GenerAH` y `ABONOS CLUBS` son `ABONO`, y `SERV.PLATAF.360` es `CARGO`, mediante `RELACION_DOCUMENTAL` 1:1. Las dos ocurrencias exactas de `SERVICIO BASICO` y la ocurrencia `CONDIC. COMERCIAL` son `CARGO` mediante `DECISION_FUNCIONAL_PIO`.

La decisión funcional no se presenta como evidencia directa del PDF: conserva `evidencia_documental_directa=false`, autoridad Pio, literal exacto y alcance limitado a Alliance y al layout auditado. No existe regla global `SERVICIO => CARGO` ni `CONDICION_COMERCIAL => CARGO`; otros literales de esas categorías permanecen sin sentido salvo evidencia o autorización independiente.

El freeze ciego conserva 527 candidatos `INDETERMINADO`, cero `DETALLE_ALBARAN`, seis movimientos y tres relaciones. Sus sentidos son cuatro `CARGO`, dos `ABONO` y cero `null`; sus fuentes son tres `RELACION_DOCUMENTAL` y tres `DECISION_FUNCIONAL_PIO`. Los dos PDFs reproducen 3/3. La evaluación post-gold no modifica el freeze y da sentidos 4/0/0.

Validación: focales 38, motor local 82, Normalizador V2 + motor 289 y suite completa 605; regresiones 0. Luna/API/Google/web/OCR: 0. Git add/commit/push: no.
