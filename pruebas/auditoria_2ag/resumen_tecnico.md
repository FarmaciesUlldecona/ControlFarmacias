# Hito 2AG — resumen técnico

El `0x80070005` del inicio manual queda localizado en la ACL de la tarea. La
ACE de `MOSTRADOR\Usuari` solo contiene lectura (`0x00120089`) y no contiene
`TASK_EXECUTE` (`0x20`). Aunque `Usuari` pertenece a Administradores, el token
observado no estaba elevado, por lo que la ACE administrativa no era efectiva.

No se aplicó la corrección porque esta sesión no dispone de un token elevado.
El intento de deshabilitar también devolvió acceso denegado, por lo que la tarea
continúa habilitada. Se deja
`reparar_acl_tarea_elevado.ps1`, que exige elevación, deshabilita primero la
tarea, conserva el descriptor y añade únicamente `TASK_EXECUTE` a la ACE de
`MOSTRADOR\Usuari`; no inicia la tarea ni rehabilita el trigger.

La ejecución automática histórica del 21/09/2026 no fue iniciada durante este
hito. Los eventos 107/100/200/201/102 prueban que Windows ejecutó la tarea como
`MOSTRADOR\ControlFarmaciasRO` y que terminó con código 0. Los logs prueban la
identidad SQL dedicada y el guard de solo lectura en Farmatic. Esa ejecución
histórica leyó 217 filas de Farmatic e insertó 217 albaranes en el destino.

La cuenta dedicada existe, está habilitada, su contraseña no expira y su último
inicio coincide con la ejecución automática. El éxito real prueba que la
credencial almacenada es válida y que el inicio por lotes no está bloqueado de
forma efectiva. No pudo determinarse si el derecho procede de política local o
GPO porque `gpresult /scope computer` requiere elevación.

Los permisos NTFS efectivos satisfacen los mínimos solicitados mediante el
grupo local `Usuarios`: proyecto y BAT con RX, `.env` con R/RX y logs con
escritura a través de `Usuarios autentificados`. No se concedió Full Control ni
se modificaron ACL NTFS.

Durante Hito 2AG no se ejecutaron la tarea, el BAT, Python de sincronización,
Farmatic, Drive, worker ni DML. No se modificó producción. No hubo commit ni
push.

Validación: sintaxis del script PowerShell correcta; tests focales `219 passed`;
suite completa `1031 passed`; cero fallos y cero regresiones.

`StartWhenAvailable` está activo. Por ello la tarea no debe rehabilitarse tras
una hora perdida sin valorar el posible arranque inmediato. En el cierre sigue
habilitada por falta de permiso para deshabilitarla; el próximo trigger observado
es 22/09/2026 a las 21:30:30.

Resultado: `CONTROLFARMACIASRO_REQUIERE_INTERVENCION`.
