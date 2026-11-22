-- Rollback de la migracion 38 (Hito H7): devuelve el esquema exacto de la 37.
-- Elimina cf_cashflow_importaciones, cf_cashflow_importes, cf_cashflow_saldos, cf_cashflow_cuentas, sus funciones,
-- triggers y politicas; quita la fila CASHFLOW de cf_modulos_farmacias y devuelve su check a solo TRABAJADORES.
-- Falla cerrado, sin borrar nada, si hay alguna importacion, importe o saldo (ROLLBACK_38_CASHFLOW_CON_DATOS): no se
-- pierde historia sin decision de Pio. Solo con confirmacion de Pio. Facturas, Trabajadores y Pagos sin cambios.
-- (AUTORIZACION EXPRESA DE PIO, C3: el rol del sistema solo se nombra en la 38 y en este rollback; aqui no hace
-- falta: sus privilegios sobre los objetos de la 38 desaparecen con ellos.)
begin;

do $$
begin
    if (to_regclass('public.cf_cashflow_importaciones') is not null
        and exists (select 1 from public.cf_cashflow_importaciones))
       or (to_regclass('public.cf_cashflow_importes') is not null and exists (select 1 from public.cf_cashflow_importes))
       or (to_regclass('public.cf_cashflow_saldos') is not null and exists (select 1 from public.cf_cashflow_saldos))
    then
        raise exception 'ROLLBACK_38_CASHFLOW_CON_DATOS';
    end if;
end;
$$;

drop table if exists public.cf_cashflow_importes;
drop table if exists public.cf_cashflow_saldos;
drop table if exists public.cf_cashflow_importaciones;
drop table if exists public.cf_cashflow_cuentas;

drop function if exists public.cf_cashflow_registrar_importacion(jsonb, jsonb, jsonb);
drop function if exists public.cf_cashflow_solo_insercion();

delete from public.cf_modulos_farmacias where modulo = 'CASHFLOW';
alter table public.cf_modulos_farmacias drop constraint if exists cf_modulos_farmacias_modulo_check;
alter table public.cf_modulos_farmacias add constraint cf_modulos_farmacias_modulo_check
    check (modulo in ('TRABAJADORES'));

commit;
