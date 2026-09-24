# Plan de prueba controlada posterior al hito 2AE

Este documento prepara las pruebas; no las ejecuta.

## A. Sincronización de albaranes — una ejecución

Precondiciones: derecho `Log on as a batch job` demostrado para
`MOSTRADOR\ControlFarmaciasRO`, principal de la tarea cambiado sin exponer la
contraseña, acción apuntando a `ejecutar_sincronizacion.bat` y ACL mínimas
verificadas.

1. Snapshot READ ONLY de Supabase: conteo de albaranes, máximo `id_contador`,
   última `fecha_importacion`, facturas, flags y locks.
2. Confirmar que no hay otra instancia ni tarea solapada.
3. Ejecutar una única vez la tarea, sin reintento manual.
4. Conservar `logs/automatizacion_albaranes.log` y
   `logs/sincronizar_albaranes.log`.
5. Snapshot READ ONLY posterior y comparar únicamente filas nuevas con
   `id_contador > 290776`.
6. Si falla antes de Supabase, no corregir datos: restaurar la tarea desde el
   XML y diagnosticar. Nunca relajar el guard Farmatic.

## B. Importación de facturas — una ejecución

Precondiciones: mirror NTFS real configurado por Pio, ruta exacta registrada en
`FACTURAS_PIO_DIR`, carpeta accesible bajo `MOSTRADOR\Usuari` y sin tareas
solapadas.

1. Snapshot READ ONLY de `documentos_facturas`, Storage, flags y locks; guardar
   hashes existentes.
2. Validar estáticamente la ruta y seleccionar cero documentos manualmente.
3. Ejecutar una única vez la tarea programada.
4. Conservar `logs/automatizacion_facturas.log` y
   `logs/importar_facturas_drive.log`.
5. Snapshot READ ONLY posterior; atribuir cualquier alta exclusivamente a un
   SHA-256 nuevo del mirror.
6. Ante error, comprobar que no existen documentos parciales. Restaurar la
   tarea desde XML si su configuración fuese la causa.
