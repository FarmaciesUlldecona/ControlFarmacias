# Hito 2AI — estado en stand by

Captura única final: `2026-09-22T19:46:47+02:00`.

- Estado temporal: `SINCRONIZACION_NOCTURNA_PENDIENTE_DE_AUDITORIA`.
- Tarea `Sincronización ControlFarmacias`: habilitada y Ready.
- Instancias activas: 0.
- Última ejecución: 22/09/2026 17:56:24 (prueba manual certificada 2AH).
- LastTaskResult: 0.
- Próxima ejecución: 22/09/2026 21:30:00.
- Principal: SID de `MOSTRADOR\ControlFarmaciasRO` terminado en `1009`.
- Acción: `C:\ControlFarmacias\Programa\ejecutar_sincronizacion.bat`.
- StartIn: `C:\ControlFarmacias\Programa`.
- Trigger: diario a las 21:30; sin cambios.
- StartWhenAvailable: true.
- Último snapshot Supabase READ_ONLY previo: 3353 albaranes PIO, máximo
  `id_contador=291852`, 7 facturas, 7 normalizaciones, 12 conciliaciones,
  locks 0, workers 0 y flags automáticos apagados.

Se detuvieron los dos mecanismos temporales de polling del Hito 2AI:

- monitor de consola: detenido;
- vigilante elevado PID 6140: detenido a las 19:46:18.

Desde la orden de stand by no se ejecutó la tarea manualmente ni se modificaron
trigger, principal, acción, credenciales, ACL, flags o estado Enabled. No se
ejecutaron BAT, Python, worker, importador, Drive, RITA ni Luna. No hubo commit
ni push.

La siguiente actuación será una auditoría READ_ONLY matinal de LastRunTime,
LastTaskResult, eventos, logs, identidades Windows/SQL, albaranes, locks, flags
y la integridad de facturas/normalizaciones/conciliaciones.
