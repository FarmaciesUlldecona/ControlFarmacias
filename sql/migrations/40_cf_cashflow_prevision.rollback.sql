-- Rollback de la migracion 40 (Hito H7b): devuelve el esquema exacto de la 39.
-- Elimina cf_cashflow_apuntes, cf_cashflow_recurrentes, cf_cashflow_conceptos, cf_cashflow_apuntes_historial, sus
-- funciones, triggers y politicas, y el rol cf_cashflow_web. Falla cerrado, sin borrar nada, si alguna de las cuatro
-- tablas tiene filas (ROLLBACK_40_CON_DATOS): no se pierde historia sin decision de Pio. Un rol es del cluster: si otra
-- base del mismo cluster aun le concede algo, no se puede eliminar y queda sin privilegios en esta base. Solo con
-- confirmacion de Pio. Las tablas importadas de la 38, facturas y vencimientos sin cambios.
-- (AUTORIZACION EXPRESA DE PIO: el rol del sistema solo se nombra en la 40 y en este rollback; aqui no hace falta: sus
-- privilegios sobre los objetos de la 40 desaparecen con ellos.)
begin;

do $$
begin
    if (to_regclass('public.cf_cashflow_apuntes') is not null and exists (select 1 from public.cf_cashflow_apuntes))
       or (to_regclass('public.cf_cashflow_recurrentes') is not null
           and exists (select 1 from public.cf_cashflow_recurrentes))
       or (to_regclass('public.cf_cashflow_conceptos') is not null
           and exists (select 1 from public.cf_cashflow_conceptos))
       or (to_regclass('public.cf_cashflow_apuntes_historial') is not null
           and exists (select 1 from public.cf_cashflow_apuntes_historial)) then
        raise exception 'ROLLBACK_40_CON_DATOS';
    end if;
end;
$$;

drop table if exists public.cf_cashflow_apuntes;
drop table if exists public.cf_cashflow_recurrentes;
drop table if exists public.cf_cashflow_conceptos;
drop table if exists public.cf_cashflow_apuntes_historial;

drop function if exists public.cf_cashflow_historial_solo_insercion();
drop function if exists public.cf_cashflow_prevision_historial();
drop function if exists public.cf_cashflow_solo_anular();
drop function if exists public.cf_cashflow_alta_apunte();
drop function if exists public.cf_cashflow_alta_recurrente();
drop function if exists public.cf_cashflow_alta_concepto();
drop function if exists public.cf_cashflow_validar_sustitucion(text, uuid, integer);
drop function if exists public.cf_cashflow_referencia_futura(text);
drop function if exists public.cf_cashflow_validar_celda(text, text, text);
drop function if exists public.cf_cashflow_ultimo_saldo_banco(text);
drop function if exists public.cf_cashflow_autor();
drop function if exists public.cf_cashflow_farmacia_habilitada(text);
drop function if exists public.cf_cashflow_ocurrencias(date, date);
drop function if exists public.cf_cashflow_fechas_recurrente(text, integer, date, date, date, date);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'cf_cashflow_web') then
        execute 'revoke all on all tables in schema public from cf_cashflow_web';
        execute 'revoke all on schema public from cf_cashflow_web';
        begin
            execute 'drop role cf_cashflow_web';
        exception when dependent_objects_still_exist then
            raise notice 'ROLLBACK_40: cf_cashflow_web conserva privilegios en otra base del cluster; no se elimina';
        end;
    end if;
end;
$$;

commit;
