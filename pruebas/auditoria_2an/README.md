# Auditoría Hito 2AN

`backup_pre.json` contiene el snapshot lógico previo, sin secretos: destino,
configuración, conteos, huellas de datos, firmas, permisos y hashes SHA-256 de
las definiciones remotas. Las definiciones completas restaurables están en las
migraciones locales 09 y 15 indicadas en el manifiesto; sus objetos fueron
contrastados contra producción antes del DDL.

Migración autorizada única:

- `sql/migrations/16_cf_worker_manual_one_shot.sql`
- SHA-256: `3c543bf7beed1b1051ef1ff9ddd23ba49a1e4e35aaac54c08f3d7e45fc7c47a4`

La certificación local ejecuta dos contenedores PostgreSQL 17 independientes,
sin red ni puertos, y elimina cada contenedor y volumen al finalizar. Ningún
script de este directorio llama a RPC de claim, workers o persistencia.
