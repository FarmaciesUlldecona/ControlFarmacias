# Hito 2AL — certificación manual one-shot

La interfaz pública del coordinador es `WorkerAutomatico.ejecutar_una_manual()`.
No recibe documento, nombre, SHA ni proveedor. Delega en una RPC explícita que
reutiliza el mismo núcleo SQL, filtros, ordering y `FOR UPDATE SKIP LOCKED` que
la ruta automática. La única diferencia del núcleo es la autorización efímera
para superar `normalizacion_automatica=false`.

La ruta manual no llama al worker de conciliación y registra el disparador
`MANUAL_ONE_SHOT`. La migración `16_cf_worker_manual_one_shot.sql` no fue
desplegada durante este hito.

El shadow usa 135 candidatos elegibles de los 140 documentos PIO actuales. Su
primera fila procede de la última auditoría READ_ONLY; los dos documentos de la
importación nocturna ocupan las posiciones 134 y 135 y el resto son datos
deterministas intermedios. Con el flag
en `false`, la ruta automática no selecciona; la manual selecciona el primer
candidato por reprocesado, fecha de importación e ID. Como el shadow no inventa
contenido documental del PDF real, demuestra el cierre seguro en ese primer
candidato y no prueba el segundo.
