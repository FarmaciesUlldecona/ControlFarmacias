-- Rollback de la migracion 34 (Hito TRAB-34, TA3): devuelve el esquema exacto de la 33.
-- Elimina guardias_semana, guardias_festivo y sus funciones, restaura festivos (restriccion festivos_local_con_farmacia,
-- ambito sin valor por defecto), la politica de historial de la 31 y guardias_farmacia (vacia, como en la 31).
-- Falla cerrado, sin borrar nada, si hay guardias (ROLLBACK_34_GUARDIAS_CON_DATOS) o festivos LOCAL sin farmacia
-- (ROLLBACK_34_FESTIVOS_LOCALES_SIN_FARMACIA). Solo con confirmacion de Pio. Facturas, albaranes y conciliacion sin
-- cambios.
-- (AUTORIZACION EXPRESA DE PIO, 2026-11-16: el rol del sistema solo se nombra en la 34 y en este rollback; aqui, para
-- retirar de nuevo los privilegios por defecto de Supabase sobre guardias_farmacia recreada.)
begin;

do $$
begin
    if (to_regclass('public.guardias_semana') is not null and exists (select 1 from public.guardias_semana))
       or (to_regclass('public.guardias_festivo') is not null and exists (select 1 from public.guardias_festivo)) then
        raise exception 'ROLLBACK_34_GUARDIAS_CON_DATOS';
    end if;
    if exists (select 1 from public.festivos where ambito = 'LOCAL' and farmacia is null) then
        raise exception 'ROLLBACK_34_FESTIVOS_LOCALES_SIN_FARMACIA';
    end if;
end;
$$;

drop trigger if exists festivos_anular_guardia on public.festivos;
drop table if exists public.guardias_festivo;
drop table if exists public.guardias_semana;
drop function if exists public.cf_trab_anular_guardia_de_festivo();
drop function if exists public.cf_trab_comprobar_guardia_festivo();
drop function if exists public.cf_trab_comprobar_guardia_semana();
drop function if exists public.cf_trab_persona_de_alta(uuid, date, date);
drop function if exists public.cf_trab_comprobar_farmacia_guardia();

alter table public.festivos alter column ambito drop default;
alter table public.festivos drop constraint if exists festivos_local_con_farmacia;
alter table public.festivos add constraint festivos_local_con_farmacia check (ambito <> 'LOCAL' or farmacia is not null);

drop policy if exists trabajadores_historial_trab_select on public.trabajadores_historial;
create policy trabajadores_historial_trab_select on public.trabajadores_historial
    for select to cf_trabajadores_web, cf_lectura
    using ((farmacia is null or exists (select 1 from public.cf_modulos_farmacias m
                                        where m.modulo = 'TRABAJADORES' and farmacia = any(m.farmacias))));

-- guardias_farmacia tal como la dejo la 31.
create table if not exists public.guardias_farmacia (
    id uuid primary key default gen_random_uuid(),
    farmacia text not null check (farmacia in ('PIO', 'RITA')),
    fecha date not null,
    nota text check (nota is null or char_length(nota) <= 200),
    anulada boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create unique index if not exists guardias_farmacia_unica
    on public.guardias_farmacia (farmacia, fecha) where not anulada;

drop trigger if exists guardias_farmacia_farmacia on public.guardias_farmacia;
create trigger guardias_farmacia_farmacia before insert or update on public.guardias_farmacia
for each row execute function public.cf_trab_comprobar_farmacia();
drop trigger if exists guardias_farmacia_updated_at on public.guardias_farmacia;
create trigger guardias_farmacia_updated_at before update on public.guardias_farmacia
for each row execute function public.cf_set_updated_at();
drop trigger if exists guardias_farmacia_historial on public.guardias_farmacia;
create trigger guardias_farmacia_historial after insert or update on public.guardias_farmacia
for each row execute function public.cf_trab_historial();

revoke all on table public.guardias_farmacia from public, anon, authenticated, service_role;
grant select, insert, update on public.guardias_farmacia to cf_trabajadores_web;
grant select on public.guardias_farmacia to cf_lectura;

alter table public.guardias_farmacia enable row level security;

do $$
declare
    v_regla text := 'exists (select 1 from public.cf_modulos_farmacias m where m.modulo = ''TRABAJADORES'' '
                    'and farmacia = any(m.farmacias))';
begin
    execute 'drop policy if exists guardias_farmacia_trab_select on public.guardias_farmacia';
    execute format('create policy guardias_farmacia_trab_select on public.guardias_farmacia '
                   'for select to cf_trabajadores_web, cf_lectura using (%s)', v_regla);
    execute 'drop policy if exists guardias_farmacia_trab_insert on public.guardias_farmacia';
    execute format('create policy guardias_farmacia_trab_insert on public.guardias_farmacia '
                   'for insert to cf_trabajadores_web with check (%s)', v_regla);
    execute 'drop policy if exists guardias_farmacia_trab_update on public.guardias_farmacia';
    execute format('create policy guardias_farmacia_trab_update on public.guardias_farmacia '
                   'for update to cf_trabajadores_web using (%s) with check (%s)', v_regla, v_regla);
end;
$$;

commit;
