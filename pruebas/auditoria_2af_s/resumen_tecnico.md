# Hito 2AF-S — resumen técnico

- La tarea existe y su configuración final es correcta: principal
  `MOSTRADOR\ControlFarmaciasRO`, `Password`, `Limited`, BAT absoluto y StartIn
  del proyecto.
- El proceso de auditoría no posee permiso para ordenar la ejecución de esa
  tarea. Tanto `Start-ScheduledTask` como `schtasks /Run` devolvieron acceso
  denegado antes de crear una instancia.
- No cambió `LastRunTime`, no apareció evento 100/107/129, no hubo proceso ni
  log de wrapper. Por tanto hubo cero sincronizaciones reales.
- Los snapshots productivos pre/post son idénticos: 3093 albaranes, máximo
  290776; 7 facturas, 7 normalizaciones y 12 conciliaciones; flags apagados,
  0 locks y 0 workers.
- La seguridad Farmatic permanece intacta. No hubo conexión a Farmatic en este
  hito y no se ejecutó importador, Google Drive ni worker.
- Tests focales: 219 passed. Suite completa: 1031 passed. Regresiones: 0.
- Postcheck Task Scheduler: `Ready`, principal `ControlFarmaciasRO`, nivel
  `Limited`, BAT y StartIn intactos; LastRunTime sigue siendo 20/09/2026
  21:30:30, resultado anterior 1 y próxima ejecución 21/09/2026 21:30:30.

Resultado: `SINCRONIZACION_BLOQUEADA_SEGURA`.
