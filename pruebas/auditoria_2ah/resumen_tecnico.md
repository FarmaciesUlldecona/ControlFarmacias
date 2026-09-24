# Hito 2AH — certificación

Se verificó la ACE de `MOSTRADOR\Usuari`: máscara exacta `0x001200A9`
(READ + TASK_EXECUTE). La tarea comenzó deshabilitada y finalizó deshabilitada.
No se añadieron ACL ni privilegios.

Windows no permite ejecutar una tarea deshabilitada (`0x80041326`). La primera
habilitación transitoria desde el token no elevado fue bloqueada antes de Run
(`0x80070005`) y produjo cero instancias. El lanzador elevado aplicó el flujo
autorizado: habilitar, una única llamada `Schedule.Service.Run` y deshabilitar
inmediatamente en `finally`. El guard persistente impide una segunda llamada.

La única instancia aceptada fue
`{349FA34D-C37C-4E04-9954-63FC02B8945C}`. Task Scheduler registró exactamente
un evento 100, principal `MOSTRADOR\ControlFarmaciasRO`, inicio 17:56:24, fin
17:57:07 y código 0. `LastTaskResult=0`.

La configuración auditada conserva `ApplicationIntent=ReadOnly`; el log
certifica identidad SQL `MOSTRADOR\ControlFarmaciasRO`, guard de permisos
superado, SELECT permitido y
ningún permiso Farmatic de INSERT/UPDATE/DELETE/ALTER/EXECUTE/CONTROL ni roles
de escritura/administración. Farmatic no fue modificado.

Supabase pasó de 3310 a 3353 albaranes PIO: 43 nuevos, 0 existentes; máximo
`id_contador` de 291694 a 291852. Las 7 facturas conservaron estados y huellas,
incluida HEFAME `0563834757`; normalizaciones 7, conciliaciones 12, documentos
138, locks 0, workers 0 y flags automáticos apagados.

Tests focales: `219 passed`. Suite completa: `1031 passed`. Regresiones: 0.
No se reactivó el automatismo, no se ejecutaron Drive, worker, RITA ni Luna y
no hubo commit ni push.

Resultado: `SINCRONIZACION_MANUAL_CERTIFICADA`.
