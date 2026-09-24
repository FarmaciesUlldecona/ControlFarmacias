# Hito 2N — despliegue productivo migracion 14

Estado: MIGRACION_14_PRODUCTIVA_DESPLEGADA.

- Destino cotejado con SUPABASE_URL: base postgres, rol postgres, esquema public.
- Inicio UTC: 2026-09-15T18:31:00.531260+00:00.
- Fin UTC: 2026-09-15T18:31:01.024417+00:00.
- SHA-256 migracion: 7f13eeac1e395e30c7707df5f4b7708f8ebcafd4763121a3dfd5adc429d2ab15.
- Aplicada exclusivamente migracion 14; rollback no ejecutado.
- Huellas de todas las tablas auditadas identicas antes y despues.
- Facturas: 2; nuevas normalizaciones: 0; nuevas conciliaciones: 0.
- Logista: NORMALIZADA/CONCILIADA, 448.00; misma conciliacion actual.
- Cofares: NORMALIZADA/CONCILIADA, 177.74, SERVICIOS, 0 albaranes, diferencia 0; misma conciliacion actual.
- Evaluacion READ ONLY: APTA_MERCANCIA y APTA_GASTO_SERVICIO.
- Grants, RLS y policies preservados; funciones cotejadas con el SQL aplicado.
- Flags: false/false/false; farmacias habilitadas: [PIO].
- Workers Windows antes/despues: 0/0; bloqueos activos de procesamiento: 0.
- Focales locales: 147 passed in 3.00s.
- Suite local: 915 passed in 59.35s; 0 fallos.
- Ninguna llamada al claim ni procesamiento, Farmatic, Luna, commit o push.

Artefactos: snapshot_pre.json, snapshot_post.json, rollback_funciones.sql y despliegue.log.
Los snapshots contienen definiciones, metadatos, resumen autorizado de las dos facturas y huellas calculadas en servidor; no documentos ni registros economicos completos.
rollback_funciones.sql restaura exclusivamente funciones; la definicion previa de la restriccion alterada esta conservada en snapshot_pre.json.
