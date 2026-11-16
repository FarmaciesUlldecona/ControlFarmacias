-- Migracion 34 (Hito TRAB-34, TA3): guardias y festivos del modulo de Trabajadores, peticion de la web (OK de Pio,
-- 2026-11-16). Propuesta de la web: origin/web/fase1:web/docs/propuesta_tablas_ta3.sql, con lo marcado
-- «A CONFIRMAR» resuelto contra la 31. Diseno: pruebas/auditoria_trab/DISENO_34.md.
-- 1. festivos (de la 31) se reutiliza: un festivo LOCAL puede no llevar farmacia (vacia = las dos; se retira
--    festivos_local_con_farmacia) y ambito pasa a tener 'LOCAL' por defecto. La unicidad (fecha, farmacia o comun),
--    la RLS, los privilegios y el historial de la 31 no cambian.
-- 2. guardias_semana: una guardia por semana (lunes a domingo) entre las no anuladas; farmacia PIO, RITA u OTRA (la
--    tercera farmacia del pueblo, ajena: sin personas); la persona de guardia (obligatoria en PIO y RITA) y el apoyo
--    del sabado son trabajadoras de esa farmacia, sin anular y de alta esos dias.
-- 3. guardias_festivo: la guardia de un festivo comun vigente; una por fecha entre las no anuladas; persona de esa
--    farmacia (obligatoria en PIO y RITA, ninguna en OTRA). Anular el festivo (o moverlo) anula su guardia.
-- 4. guardias_farmacia (31) se retira: la migracion falla cerrado si tiene filas (GUARDIAS_FARMACIA_NO_VACIA).
-- Mismas reglas que el resto del modulo: autor por transaccion (set local cf.autor; sin el, AUTOR_AUSENTE), se anula
-- y nunca se borra (sin DELETE), historial por trigger (cf_trab_historial), RLS por farmacia del modulo; las filas OTRA
-- son visibles para las farmacias del modulo (PIO y RITA), tambien en el historial.
-- anon, authenticated y el rol del sistema: ningun privilegio sobre las tablas ni las funciones nuevas (AUTORIZACION
-- EXPRESA DE PIO, 2026-11-16: el rol del sistema se nombra SOLO aqui y en el rollback, como en la 31 y la 33).
-- Solo objetos de Trabajadores: facturas, albaranes, normalizacion y conciliacion no cambian. Idempotente. Requiere la 33.
begin;

do $$
begin
    if to_regclass('public.trabajadoras_ajustes_anuales') is null then
        raise exception 'MIGRACION_33_AUSENTE';
    end if;
    if to_regclass('public.guardias_farmacia') is not null then
        if exists (select 1 from public.guardias_farmacia) then
            raise exception 'GUARDIAS_FARMACIA_NO_VACIA';
        end if;
    end if;
end;
$$;

-- --------------------------------------------------------------------------- 1. festivos

alter table public.festivos drop constraint if exists festivos_local_con_farmacia;
alter table public.festivos alter column ambito set default 'LOCAL';

-- --------------------------------------------------------------------------- 2 y 3. tablas de guardias

create table if not exists public.guardias_semana (
    id uuid primary key default gen_random_uuid(),
    lunes date not null check (extract(isodow from lunes) = 1),
    farmacia text not null check (farmacia in ('PIO', 'RITA', 'OTRA')),
    persona_guardia_id uuid,
    persona_apoyo_sabado_id uuid,
    anulada boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    -- La persona es de la farmacia de la guardia (clave externa compuesta; OTRA no tiene trabajadoras).
    constraint guardias_semana_persona_guardia foreign key (persona_guardia_id, farmacia)
        references public.trabajadoras (id, farmacia),
    constraint guardias_semana_persona_apoyo foreign key (persona_apoyo_sabado_id, farmacia)
        references public.trabajadoras (id, farmacia),
    constraint guardias_semana_otra_sin_personas check (
        farmacia <> 'OTRA' or (persona_guardia_id is null and persona_apoyo_sabado_id is null)),
    constraint guardias_semana_guardia_obligatoria check (farmacia = 'OTRA' or persona_guardia_id is not null),
    constraint guardias_semana_apoyo_distinto check (
        persona_apoyo_sabado_id is null or persona_apoyo_sabado_id <> persona_guardia_id)
);
create unique index if not exists guardias_semana_lunes_unico on public.guardias_semana (lunes) where not anulada;
comment on table public.guardias_semana is
    'Guardia semanal (lunes a domingo) de PIO, RITA u OTRA. Se anula, no se borra; historial por trigger.';

create table if not exists public.guardias_festivo (
    id uuid primary key default gen_random_uuid(),
    fecha date not null,
    farmacia text not null check (farmacia in ('PIO', 'RITA', 'OTRA')),
    persona_id uuid,
    anulada boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint guardias_festivo_persona foreign key (persona_id, farmacia) references public.trabajadoras (id, farmacia),
    constraint guardias_festivo_otra_sin_persona check (farmacia <> 'OTRA' or persona_id is null),
    constraint guardias_festivo_persona_obligatoria check (farmacia = 'OTRA' or persona_id is not null)
);
create unique index if not exists guardias_festivo_fecha_unico on public.guardias_festivo (fecha) where not anulada;
comment on table public.guardias_festivo is
    'Guardia de un festivo comun (PIO, RITA u OTRA). Se anula, no se borra; historial por trigger.';

-- --------------------------------------------------------------------------- funciones de trigger

-- Farmacia de una guardia: OTRA, o habilitada en el modulo (vale tambien para los roles que se saltan RLS).
create or replace function public.cf_trab_comprobar_farmacia_guardia()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if new.farmacia <> 'OTRA' and not exists (
        select 1 from public.cf_modulos_farmacias m
        where m.modulo = 'TRABAJADORES' and new.farmacia = any(m.farmacias)
    ) then
        raise exception 'FARMACIA_NO_HABILITADA_EN_MODULO:%', new.farmacia;
    end if;
    return new;
end;
$$;

-- Trabajadora sin anular y de alta todos los dias del servicio (la farmacia la asegura la clave externa).
create or replace function public.cf_trab_persona_de_alta(p_persona uuid, p_desde date, p_hasta date)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select exists (
        select 1 from public.trabajadoras t
        where t.id = p_persona and not t.anulada and t.fecha_alta <= p_desde
          and (t.fecha_baja is null or t.fecha_baja >= p_hasta)
    )
$$;

-- Guardia semanal vigente: la persona de guardia, de alta sabado y domingo; el apoyo, de alta el sabado.
-- Anular (o mantener anulada) una guardia no exige que las personas sigan de alta. Una persona nula la rechazan los
-- checks de la tabla.
create or replace function public.cf_trab_comprobar_guardia_semana()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if new.anulada or new.farmacia = 'OTRA' then
        return new;
    end if;
    if new.persona_guardia_id is not null
       and not public.cf_trab_persona_de_alta(new.persona_guardia_id, new.lunes + 5, new.lunes + 6) then
        raise exception 'PERSONA_NO_VALIDA:%:%', new.persona_guardia_id, new.lunes;
    end if;
    if new.persona_apoyo_sabado_id is not null
       and not public.cf_trab_persona_de_alta(new.persona_apoyo_sabado_id, new.lunes + 5, new.lunes + 5) then
        raise exception 'PERSONA_NO_VALIDA:%:%', new.persona_apoyo_sabado_id, new.lunes;
    end if;
    return new;
end;
$$;

-- Guardia de festivo vigente: la fecha es un festivo comun (sin farmacia) no anulado; la persona, de alta ese dia.
create or replace function public.cf_trab_comprobar_guardia_festivo()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if new.anulada then
        return new;
    end if;
    if not exists (select 1 from public.festivos f where f.fecha = new.fecha and f.farmacia is null and not f.anulado)
    then
        raise exception 'NO_ES_FESTIVO:%', new.fecha;
    end if;
    if new.persona_id is not null and not public.cf_trab_persona_de_alta(new.persona_id, new.fecha, new.fecha) then
        raise exception 'PERSONA_NO_VALIDA:%:%', new.persona_id, new.fecha;
    end if;
    return new;
end;
$$;

-- Un festivo comun que se anula, cambia de fecha o pasa a tener farmacia deja de sostener su guardia: se anula en la
-- misma transaccion (historial con el mismo cf.autor).
create or replace function public.cf_trab_anular_guardia_de_festivo()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if old.farmacia is null and not old.anulado
       and (new.anulado or new.fecha <> old.fecha or new.farmacia is not null) then
        update public.guardias_festivo set anulada = true where fecha = old.fecha and not anulada;
    end if;
    return null;
end;
$$;

revoke all on function public.cf_trab_comprobar_farmacia_guardia() from public, anon, authenticated, service_role;
revoke all on function public.cf_trab_persona_de_alta(uuid, date, date) from public, anon, authenticated, service_role;
revoke all on function public.cf_trab_comprobar_guardia_semana() from public, anon, authenticated, service_role;
revoke all on function public.cf_trab_comprobar_guardia_festivo() from public, anon, authenticated, service_role;
revoke all on function public.cf_trab_anular_guardia_de_festivo() from public, anon, authenticated, service_role;

-- --------------------------------------------------------------------------- triggers

drop trigger if exists guardias_semana_farmacia on public.guardias_semana;
create trigger guardias_semana_farmacia before insert or update on public.guardias_semana
for each row execute function public.cf_trab_comprobar_farmacia_guardia();
drop trigger if exists guardias_semana_personas on public.guardias_semana;
create trigger guardias_semana_personas before insert or update on public.guardias_semana
for each row execute function public.cf_trab_comprobar_guardia_semana();
drop trigger if exists guardias_semana_updated_at on public.guardias_semana;
create trigger guardias_semana_updated_at before update on public.guardias_semana
for each row execute function public.cf_set_updated_at();
drop trigger if exists guardias_semana_historial on public.guardias_semana;
create trigger guardias_semana_historial after insert or update on public.guardias_semana
for each row execute function public.cf_trab_historial();

drop trigger if exists guardias_festivo_farmacia on public.guardias_festivo;
create trigger guardias_festivo_farmacia before insert or update on public.guardias_festivo
for each row execute function public.cf_trab_comprobar_farmacia_guardia();
drop trigger if exists guardias_festivo_persona on public.guardias_festivo;
create trigger guardias_festivo_persona before insert or update on public.guardias_festivo
for each row execute function public.cf_trab_comprobar_guardia_festivo();
drop trigger if exists guardias_festivo_updated_at on public.guardias_festivo;
create trigger guardias_festivo_updated_at before update on public.guardias_festivo
for each row execute function public.cf_set_updated_at();
drop trigger if exists guardias_festivo_historial on public.guardias_festivo;
create trigger guardias_festivo_historial after insert or update on public.guardias_festivo
for each row execute function public.cf_trab_historial();

drop trigger if exists festivos_anular_guardia on public.festivos;
create trigger festivos_anular_guardia after update on public.festivos
for each row execute function public.cf_trab_anular_guardia_de_festivo();

-- --------------------------------------------------------------------------- privilegios

-- Supabase concede por defecto privilegios sobre las tablas nuevas de public: se retiran todos.
revoke all on table public.guardias_semana, public.guardias_festivo from public, anon, authenticated, service_role;
grant select, insert, update on public.guardias_semana, public.guardias_festivo to cf_trabajadores_web;
grant select on public.guardias_semana, public.guardias_festivo to cf_lectura;

-- --------------------------------------------------------------------------- RLS

alter table public.guardias_semana enable row level security;
alter table public.guardias_festivo enable row level security;

do $$
declare
    v_tabla text;
    v_regla text := '(farmacia = ''OTRA'' or exists (select 1 from public.cf_modulos_farmacias m '
                    'where m.modulo = ''TRABAJADORES'' and farmacia = any(m.farmacias)))';
begin
    foreach v_tabla in array array['guardias_semana', 'guardias_festivo'] loop
        execute format('drop policy if exists %I on public.%I', v_tabla || '_trab_select', v_tabla);
        execute format('create policy %I on public.%I for select to cf_trabajadores_web, cf_lectura using (%s)',
                       v_tabla || '_trab_select', v_tabla, v_regla);
        execute format('drop policy if exists %I on public.%I', v_tabla || '_trab_insert', v_tabla);
        execute format('create policy %I on public.%I for insert to cf_trabajadores_web with check (%s)',
                       v_tabla || '_trab_insert', v_tabla, v_regla);
        execute format('drop policy if exists %I on public.%I', v_tabla || '_trab_update', v_tabla);
        execute format('create policy %I on public.%I for update to cf_trabajadores_web using (%s) with check (%s)',
                       v_tabla || '_trab_update', v_tabla, v_regla, v_regla);
    end loop;
    -- El historial de las filas OTRA tambien es visible para el modulo.
    execute 'drop policy if exists trabajadores_historial_trab_select on public.trabajadores_historial';
    execute 'create policy trabajadores_historial_trab_select on public.trabajadores_historial '
            'for select to cf_trabajadores_web, cf_lectura using ((farmacia is null or farmacia = ''OTRA'' '
            'or exists (select 1 from public.cf_modulos_farmacias m where m.modulo = ''TRABAJADORES'' '
            'and farmacia = any(m.farmacias))))';
end;
$$;

-- --------------------------------------------------------------------------- 4. guardias_farmacia

-- Vacia (comprobado arriba): sustituida por guardias_semana y guardias_festivo. Su historial se conserva.
drop table if exists public.guardias_farmacia;

commit;
