# Arquitectura del motor local

`controlfarmacias-local-engine@0.4.0` es un motor documental completamente local. `BackendPdf` es el límite estable y solo `backend/pdfium.py` conoce `pypdfium2==5.12.1`; ninguna regla documental recibe objetos PDFium.

Las capas son: modelos canónicos; geometría general; segmentación; evidencia local; adaptadores; servicio de extracción; shadow y observabilidad; puente al Normalizador V2; consolidación documental; matcher; `PlanAutoridadLocal`; y ensamblador híbrido simulado.

El registro productivo contiene `cofares-local@1.0.0`, `hefame-local@1.1.0` y `fedefarma-local@1.2.0`. Alliance no está integrada productivamente. COFARES conserva su alcance de filas. HEFAME y FEDEFARMA extraen en shadow cabecera, fiscalidad, albaranes, movimientos, vencimientos y resúmenes económicos con evidencia local; FEDEFARMA conserva además facturas internas segmentadas sin contaminar sus colecciones. Cuando el documento no demuestra CARGO/ABONO, `sentido` permanece `null`.

FEDEFARMA 1.2 aplica la decisión funcional de Pio que clasifica sus bloques `Total abonaments (consultar detalls)` como `DEVOLUCION_MERCANCIA`, conservando el detalle y sin derivar sentido. También preserva la cuota mensual de servicios cooperativos como `CONDICION_COOPERATIVA`; los textos meramente registrales sobre sociedades cooperativas no generan movimientos.

La conciliación documental es una capacidad común declarativa. Cada adaptador identifica objetivos, componentes y la relación estructural que permite compararlos; `conciliacion.py` realiza únicamente aritmética decimal, conserva evidencia/provenance y devuelve `OK`, `DIFERENCIA_DOCUMENTAL` o `NO_EVALUABLE`. Una diferencia nunca crea movimientos, sentidos, categorías ni explicaciones. HEFAME declara las relaciones entre detalle y Pedidos, Pedidos y Servicios Operativos, fiscalidad y total, y total y vencimiento. FEDEFARMA declara controles por factura y controles entre el resumen documental, las facturas segmentadas y sus vencimientos.

Las primitivas de fechas, fechas de impresión independientes, importes, líneas, continuaciones geométricas de columna, campos multilínea, agregados documentales, evidencia, facturas segmentadas y segmentación son comunes. Solo el reconocimiento y la interpretación de cada layout de proveedor permanecen en su adaptador.

Antes del matcher, las lecturas primaria y segmentadas se normalizan por separado y pasan por consolidación documental. Solo `MISMA_FACTURA_DEMOSTRADA` permite fusionar; completitud, origen, orden o primera coincidencia nunca deciden identidad.

El shadow local está apagado por defecto y conserva siempre la salida oficial. HEFAME y FEDEFARMA no tienen autoridad local: solo generan observabilidad lateral. La autoridad COFARES sigue preparada, pero `COFARES_LOCAL_AUTHORITY = False`.
