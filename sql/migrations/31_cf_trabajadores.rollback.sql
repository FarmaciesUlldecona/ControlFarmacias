-- Rollback de la migracion 31 (Hito TRAB): devuelve el esquema exacto de la 30.
-- Elimina las tablas, la vista, las funciones y las politicas del modulo de Trabajadores (CON SUS DATOS) y el rol
-- cf_trabajadores_web. Un rol es del cluster: si otra base del mismo cluster aun le concede algo, no se puede eliminar
-- y queda sin privilegios en esta base. Solo con confirmacion de Pio. Facturas, albaranes y conciliacion sin cambios.
-- (AUTORIZACION EXPRESA DE PIO, 2026-11-12: el rol del sistema solo se nombra en la 31 y en este rollback; aqui no
-- hace falta: sus privilegios sobre los objetos del modulo desaparecen con ellos.)
begin;

drop view if exists public.v_eventos_calendario_horas;
drop table if exists public.eventos_calendario;
drop table if exists public.trabajadores_historial;
drop table if exists public.trabajadoras;
drop table if exists public.convenio_anual;
drop table if exists public.guardias_farmacia;
drop table if exists public.festivos;
drop table if exists public.cf_modulos_farmacias;

drop function if exists public.cf_trab_comprobar_farmacia();
drop function if exists public.cf_trab_comprobar_evento();
drop function if exists public.cf_trab_historial();
drop function if exists public.cf_trab_historial_solo_insercion();

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'cf_trabajadores_web') then
        execute 'revoke all on all tables in schema public from cf_trabajadores_web';
        execute 'revoke all on schema public from cf_trabajadores_web';
        begin
            execute 'drop role cf_trabajadores_web';
        exception when dependent_objects_still_exist then
            raise notice 'ROLLBACK_31: cf_trabajadores_web conserva privilegios en otra base del cluster; no se elimina';
        end;
    end if;
end;
$$;

commit;
