-- Rollback de la migracion 32 (Hito AUTO-A): elimina la tabla de resumen nocturno y su politica.
-- Devuelve el esquema exacto de la 31. Las filas de resumen se pierden (son un registro, no datos de facturas).
begin;

drop table if exists public.cf_noches_automaticas;

commit;
