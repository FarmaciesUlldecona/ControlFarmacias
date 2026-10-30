-- Rollback de la migracion 25 (Hito 2BI): devuelve el esquema exacto de la 24.
-- Solo con confirmacion de Pio. Las ejecuciones, estados e historial ya registrados se conservan.
begin;

drop function if exists public.cf_recuperar_claim_huerfano_normalizacion(uuid, text, interval);
drop function if exists public.cf_huerfanos_normalizacion(interval);
drop function if exists public.cf_senales_claim_huerfano(uuid);

commit;
