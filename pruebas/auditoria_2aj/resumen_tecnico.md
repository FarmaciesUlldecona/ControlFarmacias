# Hito 2AJ — certificación

La tarea `ControlFarmacias - Importar facturas` fue localizada con principal
`MOSTRADOR\Usuari`, BAT y StartIn correctos, nivel Limited, trigger diario a
las 22:00 y `StartWhenAvailable=true`. Se deshabilitó antes del piloto sin
alterar el trigger y terminó deshabilitada.

El Mirror certificado fue `C:\GoogleDrive\FACTURES PIO`: ruta absoluta, NTFS
local/FileSystem, existente y legible. El inventario encontró 587 PDF totales;
141 pertenecían al flujo desde junio de 2026 tras excluir 17 RITA. Esos 141
archivos representan 136 hashes únicos y 5 repeticiones binarias. Todos estaban
ya cubiertos por SHA en `documentos_facturas`; nuevos potenciales: 0.

Se realizó exactamente una llamada oficial a Task Scheduler. La instancia
`{DB2FED4E-7A8A-45D4-A968-DC05D9EAA3F7}` se ejecutó como
`MOSTRADOR\Usuari` de 20:02:28 a 20:02:32 y terminó con código 0. El importador
usó la ruta Mirror, detectó 141 PDF, omitió los 141 mediante el índice local y
registró 0 documentos nuevos, 0 modificaciones y 0 errores.

Los snapshots READ_ONLY pre/post son idénticos: 138 documentos PIO, 138 hashes
PIO, 138 objetos Storage PIO, 7 facturas económicas, 7 normalizaciones y 12
conciliaciones. Las huellas de las siete facturas no cambiaron. RITA importada:
0; normalizaciones nuevas: 0; conciliaciones nuevas: 0; workers y locks: 0.
Quedan 133 documentos PIO pendientes y potencialmente reclamables, sin haber
sido reclamados ni procesados.

Flags finales: normalización automática `false`, conciliación automática
`false`, Luna `false`, farmacias habilitadas `[PIO]`. Tests focales:
`229 passed`; suite completa: `1031 passed`; regresiones: 0. No hubo segunda
ejecución, worker, normalización, conciliación, RITA, Luna, modificación de
Farmatic, commit ni push.

Resultado: `IMPORTACION_DRIVE_MIRROR_CERTIFICADA`.
