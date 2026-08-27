# Microhito FEDEFARMA 1.2 y condición cooperativa

FEDEFARMA permanece `LOCAL_COMPLETO`. Por decisión funcional de Pio, los dos movimientos `Total abonaments (consultar detalls)` se clasifican `DEVOLUCION_MERCANCIA`; su `sentido` continúa `null`. Los freezes 1.0/1.1 no se reescriben.

La categoría específica no existía. El caso real se preservaba como literal, pero estaba diluido en `SERVICIO`.

La auditoría local de 20 PDFs no-Alliance encontró una aparición económica inequívoca: factura FEDEFARMA `VN26-0016742`, página 4, literal `SVCOP202607-Cuota Mensual Servicios Cooperativos 202607 -`, base 255,00 EUR, tipo IVA 21%, cuota fiscal de factura 53,55 EUR, sin RE numérico y total de factura 308,55 EUR. Su categoría es ahora `CONDICION_COOPERATIVA` y su sentido permanece `null`.

Ocho apariciones adicionales de “cooperativa(s)” son pies registrales de FEDEFARMA o HEFAME; no crean movimientos.

El modelo permite filtrar y sumar movimientos por `CONDICION_COOPERATIVA` dentro de facturas que ya preservan proveedor, fecha, farmacia y provenance. La cuota IVA permanece en la fiscalidad de la factura porque no está impresa como cuota en la fila individual.

En la evaluación posterior, `DEVOLUCION_MERCANCIA` ya coincide con el gold. El gold histórico llama `SERVICIO` a la cuota cooperativa; la categoría local más específica se registra como diferencia taxonómica, no como diferencia documental real. No se modificó ningún candidato usando gold.

Validación: 26 focales, 44 motor local, 251 Normalizador V2 + motor y 567 suite completa; cero regresiones y cero llamadas externas. La salida local sigue en shadow.
