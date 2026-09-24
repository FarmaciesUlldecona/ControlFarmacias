# Hito 2AK — bloqueo seguro

Se ejecutó literalmente una sola vez
`construir_worker_automatico(...).ejecutar_una()` con la configuración
productiva leída desde Supabase. El coordinador devolvió límite 1, cero
documentos reclamados, cero facturas de conciliación reclamadas y automatismos
deshabilitados.

La causa es una barrera de diseño demostrada: el coordinador no invoca el
worker de normalización con `normalizacion_automatica=false`, y el claim SQL
solo admite documentos cuando ese flag está activo o existe una solicitud
manual de reproceso. El snapshot mostró `siguiente_reclamable_oficial=[]`.

No se activó ningún flag. Tampoco se marcó manualmente un documento para
reproceso, porque eso habría preseleccionado el candidato e infringido la orden
de dejar que el worker aplicase su selección real. No se creó una composición
o regla alternativa no certificada.

Pre/post permanecen idénticos: 138 documentos PIO, 133 pendientes, 7 facturas
(6 conciliadas y HEFAME `0563834757` pendiente legítima), 7 normalizaciones,
12 conciliaciones, RITA 0/0, locks 0 y workers 0. Las siete huellas económicas
son idénticas. No hubo materialización, extracción, Luna, normalización,
conciliación ni persistencia.

Tests focales: `262 passed`; suite completa: `1031 passed`; regresiones: 0.
No hubo una segunda llamada, commit ni push.

Resultado: `PRIMER_DOCUMENTO_WORKER_BLOQUEADO_SEGURO`.
