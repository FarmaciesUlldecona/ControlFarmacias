# Arquitectura del motor local

`controlfarmacias-local-engine@0.4.0` es un motor documental completamente local. `BackendPdf` es el límite estable y solo `backend/pdfium.py` conoce `pypdfium2==5.12.1`; ninguna regla documental recibe objetos PDFium.

Las capas son: modelos canónicos; geometría general; segmentación; evidencia local; adaptadores; servicio de extracción; shadow y observabilidad; puente al Normalizador V2; consolidación documental; matcher; `PlanAutoridadLocal`; y ensamblador híbrido simulado.

El registro productivo contiene `cofares-local@1.0.0` y `hefame-local@1.1.0`. Alliance y FEDEFARMA no están integrados productivamente. COFARES conserva su alcance de filas. HEFAME extrae en shadow cabecera, fiscalidad, albaranes, movimientos, vencimientos y resúmenes económicos con evidencia local. Cuando el documento no demuestra CARGO/ABONO, `sentido` permanece `null`.

La conciliación documental es una capacidad común declarativa. Cada adaptador identifica objetivos, componentes y la relación estructural que permite compararlos; `conciliacion.py` realiza únicamente aritmética decimal, conserva evidencia/provenance y devuelve `OK`, `DIFERENCIA_DOCUMENTAL` o `NO_EVALUABLE`. Una diferencia nunca crea movimientos, sentidos, categorías ni explicaciones. HEFAME declara las relaciones entre detalle y Pedidos, Pedidos y Servicios Operativos, fiscalidad y total, y total y vencimiento.

Las primitivas de fechas, importes, líneas, columnas, evidencia y segmentación son comunes. Solo el reconocimiento y la interpretación del layout HEFAME permanecen en su adaptador.

Antes del matcher, las lecturas primaria y segmentadas se normalizan por separado y pasan por consolidación documental. Solo `MISMA_FACTURA_DEMOSTRADA` permite fusionar; completitud, origen, orden o primera coincidencia nunca deciden identidad.

El shadow local está apagado por defecto y conserva siempre la salida oficial. HEFAME no tiene autoridad local: solo genera observabilidad lateral. La autoridad COFARES sigue preparada, pero `COFARES_LOCAL_AUTHORITY = False`.
