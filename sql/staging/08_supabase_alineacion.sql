-- Solo para una base PostgreSQL desechable de tests (Hito 2BQ): alineacion de la base local con Supabase. No es una
-- migracion y nunca se aplica en produccion. pg17_local lo aplica entre el rollback de la 19 y la 19.
-- 1. Copia de la funcion de Supabase public.rls_auto_enable() (activa RLS en las tablas nuevas de public; definicion
--    de la captura productiva 2BN-D). Sin GRANT: los privilegios por defecto de Supabase vigentes en ese punto le dan
--    la misma ACL que en produccion. Sin event trigger asociado.
-- 2. ACL productiva de cuatro funciones (al final).
CREATE OR REPLACE FUNCTION public.rls_auto_enable()
 RETURNS event_trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$function$;

-- ACL productiva de cuatro funciones que la 19 no toca (deuda 2AS; captura productiva 2BN-D, intento 3).
grant execute on function public.cf_historial_append_only() to anon, authenticated, service_role;
grant execute on function public.cf_resultado_conciliacion(numeric, numeric) to anon, authenticated, service_role;
grant execute on function public.cf_set_updated_at() to anon, authenticated, service_role;
grant execute on function public.cf_solicitar_reprocesado(uuid, text) to service_role;
