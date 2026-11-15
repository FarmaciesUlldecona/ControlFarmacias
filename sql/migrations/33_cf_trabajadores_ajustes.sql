-- Migracion 33 (Hito TRAB-33): ajustes del modulo de Trabajadores pedidos por la web (OK de Pio, 2026-11-14).
-- Diseno: pruebas/auditoria_trab/DISENO_33.md.
-- 1. eventos_calendario.anulado (boolean, default false). La unicidad (trabajadora, fecha, franja) pasa a ser solo
--    entre eventos NO anulados (indice unico parcial eventos_calendario_unico). La web debe usar
--    ON CONFLICT (trabajadora_id, fecha, franja) WHERE NOT anulado DO NOTHING. Anular un evento es un UPDATE
--    (historial por el trigger existente) y se admite aunque la trabajadora ya este anulada o de baja. La vista de
--    horas excluye los eventos anulados.
-- 2. convenio_anual.vacaciones_dias_naturales (entero) y su fuente: 30 para 2026-2028 en las filas que existan
--    (decision de Pio, pendiente de texto publicado). Los demas anos quedan sin valor.
-- 3. trabajadoras_ajustes_anuales: dias extra de vacaciones por trabajadora y ano; unica por (trabajadora, ano) entre
--    no anuladas; RLS por farmacia del modulo (PIO/RITA); escritura de cf_trabajadores_web (sin DELETE), autor por
--    transaccion (set local cf.autor) e historial por trigger; lectura para cf_lectura.
-- anon, authenticated y el rol del sistema: ningun privilegio sobre la tabla nueva (AUTORIZACION EXPRESA DE PIO,
-- 2026-11-14: el rol del sistema se nombra SOLO aqui y en el rollback, como en la 31).
-- Solo objetos de Trabajadores: facturas, albaranes, normalizacion y conciliacion no cambian. Idempotente. Requiere la 32.
begin;

do $$
begin
    if to_regclass('public.cf_noches_automaticas') is null then
        raise exception 'MIGRACION_32_AUSENTE';
    end if;
end;
$$;

-- Las actualizaciones de datos de esta migracion quedan en el historial con este autor.
set local cf.autor = 'Migracion 33';

-- --------------------------------------------------------------------------- 1. eventos anulados

alter table public.eventos_calendario add column if not exists anulado boolean not null default false;
alter table public.eventos_calendario drop constraint if exists eventos_calendario_unico;
create unique index if not exists eventos_calendario_unico
    on public.eventos_calendario (trabajadora_id, fecha, franja) where not anulado;

-- Anular (o mantener anulado) un evento no exige que siga dentro del alta de una trabajadora no anulada.
create or replace function public.cf_trab_comprobar_evento()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if new.anulado then
        return new;
    end if;
    if not exists (
        select 1 from public.trabajadoras t
        where t.id = new.trabajadora_id and not t.anulada and new.fecha >= t.fecha_alta
          and (t.fecha_baja is null or new.fecha <= t.fecha_baja)
    ) then
        raise exception 'EVENTO_FUERA_DEL_ALTA:%:%', new.trabajadora_id, new.fecha;
    end if;
    return new;
end;
$$;

-- Decision de Pio (2026-11-14): la vista de horas EXCLUYE los eventos anulados (un anulado nunca suma horas).
-- Mismas columnas que en la 31.
create or replace view public.v_eventos_calendario_horas
with (security_invoker = true) as
select e.id, e.trabajadora_id, e.farmacia, e.fecha, e.franja, e.tipo, e.estado, e.horas, e.nota,
       coalesce(e.horas, case when t.tipo_jornada = 'COMPLETA'
                              then case e.franja when 'MANANA' then 4.50 else 3.50 end
                              else t.horas_diarias end)::numeric(4,2) as horas_efectivas
from public.eventos_calendario e
join public.trabajadoras t on t.id = e.trabajadora_id
where not e.anulado;

-- --------------------------------------------------------------------------- 2. vacaciones del convenio

alter table public.convenio_anual add column if not exists vacaciones_dias_naturales integer
    check (vacaciones_dias_naturales is null or vacaciones_dias_naturales between 0 and 366);
alter table public.convenio_anual add column if not exists vacaciones_fuente text
    check (vacaciones_fuente is null or char_length(vacaciones_fuente) between 1 and 200);
alter table public.convenio_anual drop constraint if exists convenio_anual_vacaciones_con_fuente;
alter table public.convenio_anual add constraint convenio_anual_vacaciones_con_fuente
    check (vacaciones_dias_naturales is null or vacaciones_fuente is not null);

update public.convenio_anual
set vacaciones_dias_naturales = 30,
    vacaciones_fuente = 'Decision de Pio (2026-11-14), pendiente de texto publicado'
where anio between 2026 and 2028 and vacaciones_dias_naturales is null;

-- --------------------------------------------------------------------------- 3. ajustes anuales

create table if not exists public.trabajadoras_ajustes_anuales (
    id uuid primary key default gen_random_uuid(),
    trabajadora_id uuid not null,
    farmacia text not null,
    anio integer not null check (anio between 2020 and 2100),
    vacaciones_dias_extra numeric(5,2) not null default 0 check (vacaciones_dias_extra >= 0),
    nota text check (nota is null or char_length(nota) <= 200),
    anulada boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint trabajadoras_ajustes_anuales_trabajadora foreign key (trabajadora_id, farmacia)
        references public.trabajadoras (id, farmacia)
);
create unique index if not exists trabajadoras_ajustes_anuales_unico
    on public.trabajadoras_ajustes_anuales (trabajadora_id, anio) where not anulada;
comment on table public.trabajadoras_ajustes_anuales is
    'Ajustes anuales por trabajadora (dias extra de vacaciones). Se anula, no se borra; historial por trigger.';

drop trigger if exists trabajadoras_ajustes_anuales_farmacia on public.trabajadoras_ajustes_anuales;
create trigger trabajadoras_ajustes_anuales_farmacia before insert or update on public.trabajadoras_ajustes_anuales
for each row execute function public.cf_trab_comprobar_farmacia();
drop trigger if exists trabajadoras_ajustes_anuales_updated_at on public.trabajadoras_ajustes_anuales;
create trigger trabajadoras_ajustes_anuales_updated_at before update on public.trabajadoras_ajustes_anuales
for each row execute function public.cf_set_updated_at();
drop trigger if exists trabajadoras_ajustes_anuales_historial on public.trabajadoras_ajustes_anuales;
create trigger trabajadoras_ajustes_anuales_historial after insert or update on public.trabajadoras_ajustes_anuales
for each row execute function public.cf_trab_historial();

-- Supabase concede por defecto privilegios sobre las tablas nuevas de public: se retiran todos.
revoke all on table public.trabajadoras_ajustes_anuales from public, anon, authenticated, service_role;
grant select, insert, update on public.trabajadoras_ajustes_anuales to cf_trabajadores_web;
grant select on public.trabajadoras_ajustes_anuales to cf_lectura;

alter table public.trabajadoras_ajustes_anuales enable row level security;

drop policy if exists trabajadoras_ajustes_anuales_trab_select on public.trabajadoras_ajustes_anuales;
create policy trabajadoras_ajustes_anuales_trab_select on public.trabajadoras_ajustes_anuales
    for select to cf_trabajadores_web, cf_lectura
    using (exists (select 1 from public.cf_modulos_farmacias m where m.modulo = 'TRABAJADORES'
                   and farmacia = any(m.farmacias)));
drop policy if exists trabajadoras_ajustes_anuales_trab_insert on public.trabajadoras_ajustes_anuales;
create policy trabajadoras_ajustes_anuales_trab_insert on public.trabajadoras_ajustes_anuales
    for insert to cf_trabajadores_web
    with check (exists (select 1 from public.cf_modulos_farmacias m where m.modulo = 'TRABAJADORES'
                        and farmacia = any(m.farmacias)));
drop policy if exists trabajadoras_ajustes_anuales_trab_update on public.trabajadoras_ajustes_anuales;
create policy trabajadoras_ajustes_anuales_trab_update on public.trabajadoras_ajustes_anuales
    for update to cf_trabajadores_web
    using (exists (select 1 from public.cf_modulos_farmacias m where m.modulo = 'TRABAJADORES'
                   and farmacia = any(m.farmacias)))
    with check (exists (select 1 from public.cf_modulos_farmacias m where m.modulo = 'TRABAJADORES'
                        and farmacia = any(m.farmacias)));

commit;
