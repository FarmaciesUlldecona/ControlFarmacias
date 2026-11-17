-- Rollback de la migracion 35 (Hito H6): devuelve el esquema exacto de la 34.
-- Elimina vencimientos_marcas_pago, proveedores_forma_pago, pagos_historial, sus funciones y politicas, y el rol
-- cf_pagos_web. Falla cerrado, sin borrar nada, si alguna de las tres tablas tiene filas (ROLLBACK_35_PAGOS_CON_DATOS):
-- no se pierde historia sin decision de Pio. Un rol es del cluster: si otra base del mismo cluster aun le concede algo,
-- no se puede eliminar y queda sin privilegios en esta base. Solo con confirmacion de Pio. Facturas, vencimientos,
-- albaranes y conciliacion sin cambios.
-- (AUTORIZACION EXPRESA DE PIO, 2026-11-16, D8: el rol del sistema solo se nombra en la 35 y en este rollback; aqui no
-- hace falta: sus privilegios sobre los objetos de la 35 desaparecen con ellos.)
begin;

do $$
begin
    if (to_regclass('public.vencimientos_marcas_pago') is not null
        and exists (select 1 from public.vencimientos_marcas_pago))
       or (to_regclass('public.proveedores_forma_pago') is not null
           and exists (select 1 from public.proveedores_forma_pago))
       or (to_regclass('public.pagos_historial') is not null and exists (select 1 from public.pagos_historial)) then
        raise exception 'ROLLBACK_35_PAGOS_CON_DATOS';
    end if;
end;
$$;

drop table if exists public.vencimientos_marcas_pago;
drop table if exists public.proveedores_forma_pago;
drop table if exists public.pagos_historial;

drop function if exists public.cf_pagos_historial_solo_insercion();
drop function if exists public.cf_pagos_historial();
drop function if exists public.cf_pagos_solo_anular();
drop function if exists public.cf_pagos_validar_marca();
drop function if exists public.cf_pagos_comprobar_farmacia();
drop function if exists public.cf_pagos_dia_madrid(timestamptz);
drop function if exists public.cf_pagos_farmacia_habilitada(text);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'cf_pagos_web') then
        execute 'revoke all on all tables in schema public from cf_pagos_web';
        execute 'revoke all on schema public from cf_pagos_web';
        begin
            execute 'drop role cf_pagos_web';
        exception when dependent_objects_still_exist then
            raise notice 'ROLLBACK_35: cf_pagos_web conserva privilegios en otra base del cluster; no se elimina';
        end;
    end if;
end;
$$;

commit;
