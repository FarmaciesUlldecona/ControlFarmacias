-- Migracion 31 (Hito TRAB): esquema de Trabajadores. Diseno: pruebas/auditoria_trab/DISENO.md.
-- - Solo anade objetos: ninguna tabla, funcion, politica ni privilegio de facturas, albaranes, normalizacion o
--   conciliacion cambia; cf_configuracion.farmacias_habilitadas sigue en {PIO}.
-- - Permiso de farmacia POR MODULO (cf_modulos_farmacias): TRABAJADORES = {PIO,RITA} (decision de Pio, 2026-11-12).
-- - Rol de escritura de la web cf_trabajadores_web: LOGIN sin contrasena en el repositorio (la fija Pio fuera);
--   SELECT, INSERT y UPDATE solo en las tablas del modulo; SIN DELETE ni TRUNCATE (anulacion + historial).
-- - Historial solo de insercion, escrito por trigger; autor obligatorio (set local cf.autor), si falta -> AUTOR_AUSENTE.
-- - cf_lectura: lectura de las tablas nuevas. anon, authenticated y el rol del sistema: ningun privilegio sobre ellas
--   (AUTORIZACION EXPRESA DE PIO, 2026-11-12: el rol del sistema se nombra SOLO aqui y en el rollback).
-- Idempotente. Requiere la 30.
begin;

do $$
begin
    if to_regclass('public.conciliacion_detalles_previo_30') is null then
        raise exception 'MIGRACION_30_AUSENTE';
    end if;
    if not exists (select 1 from pg_roles where rolname = 'cf_trabajadores_web') then
        create role cf_trabajadores_web login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls
            connection limit 5;
    end if;
end;
$$;

-- Los atributos solo se fijan al crear el rol (2BN-D: en Supabase postgres no es superusuario).
alter role cf_trabajadores_web set statement_timeout = '60s';
alter role cf_trabajadores_web set idle_in_transaction_session_timeout = '60s';

-- --------------------------------------------------------------------------- permiso por modulo

create table if not exists public.cf_modulos_farmacias (
    modulo text primary key check (modulo in ('TRABAJADORES')),
    farmacias text[] not null check (cardinality(farmacias) > 0 and farmacias <@ array['PIO', 'RITA']::text[])
);
insert into public.cf_modulos_farmacias (modulo, farmacias)
values ('TRABAJADORES', array['PIO', 'RITA']::text[])
on conflict (modulo) do nothing;
comment on table public.cf_modulos_farmacias is
    'Farmacias habilitadas por modulo (no global). Facturas, albaranes y conciliacion usan cf_configuracion.';

-- --------------------------------------------------------------------------- tablas

create table if not exists public.trabajadoras (
    id uuid primary key default gen_random_uuid(),
    farmacia text not null check (farmacia in ('PIO', 'RITA')),
    nombre text not null check (char_length(nombre) between 1 and 80 and nombre = btrim(nombre)),
    categoria text not null check (categoria in ('FARMACEUTICA_TITULAR', 'FARMACEUTICA_ADJUNTA', 'TECNICA',
                                                 'AUXILIAR', 'OTRA')),
    tipo_jornada text not null check (tipo_jornada in ('COMPLETA', 'MEDIA_MANANA', 'MEDIA_TARDE')),
    horas_diarias numeric(4,2) not null,
    computa_convenio boolean not null default true,
    fecha_alta date not null,
    fecha_baja date,
    anulada boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint trabajadoras_horas_jornada check (
        (tipo_jornada = 'COMPLETA' and horas_diarias = 8)
        or (tipo_jornada <> 'COMPLETA' and horas_diarias > 0 and horas_diarias < 8)),
    constraint trabajadoras_baja_tras_alta check (fecha_baja is null or fecha_baja >= fecha_alta),
    constraint trabajadoras_id_farmacia unique (id, farmacia)
);
create unique index if not exists trabajadoras_nombre_unico
    on public.trabajadoras (farmacia, lower(nombre)) where not anulada;

create table if not exists public.convenio_anual (
    anio integer primary key check (anio between 2020 and 2100),
    jornada_max_horas numeric(6,2) not null check (jornada_max_horas > 0),
    asuntos_propios_dias numeric(4,1) not null check (asuntos_propios_dias >= 0),
    permiso_medico_horas numeric(5,2) not null check (permiso_medico_horas >= 0),
    horas_semanales_referencia numeric(4,2) not null default 40 check (horas_semanales_referencia > 0),
    estado text not null check (estado in ('FIRMADO_PENDIENTE_PUBLICACION', 'PUBLICADO')),
    fuente text not null check (char_length(fuente) between 1 and 200),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.eventos_calendario (
    id uuid primary key default gen_random_uuid(),
    trabajadora_id uuid not null,
    farmacia text not null,
    fecha date not null,
    franja text not null check (franja in ('MANANA', 'TARDE')),
    tipo text not null check (tipo in ('JORNADA', 'VACACIONES', 'ASUNTOS_PROPIOS', 'PERMISO_RETRIBUIDO',
                                       'PERMISO_NO_RETRIBUIDO', 'PERMISO_MEDICO', 'DESCANSO_COMPENSATORIO', 'BAJA',
                                       'FESTIVO', 'TURNO_GUARDIA', 'LOCALIZADA')),
    estado text not null check (estado in ('PLANIFICADO', 'CONFIRMADO')),
    horas numeric(4,2) check (horas is null or (horas > 0 and horas <= 8)),
    nota text check (nota is null or char_length(nota) <= 200),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint eventos_calendario_trabajadora foreign key (trabajadora_id, farmacia)
        references public.trabajadoras (id, farmacia),
    constraint eventos_calendario_unico unique (trabajadora_id, fecha, franja)
);

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

create table if not exists public.festivos (
    id uuid primary key default gen_random_uuid(),
    fecha date not null,
    ambito text not null check (ambito in ('NACIONAL', 'AUTONOMICO', 'LOCAL')),
    farmacia text check (farmacia is null or farmacia in ('PIO', 'RITA')),
    descripcion text not null check (char_length(descripcion) between 1 and 100),
    anulado boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint festivos_local_con_farmacia check (ambito <> 'LOCAL' or farmacia is not null)
);
create unique index if not exists festivos_unico
    on public.festivos (fecha, coalesce(farmacia, '*')) where not anulado;

create table if not exists public.trabajadores_historial (
    id bigint generated always as identity primary key,
    tabla text not null,
    registro_id text not null,
    farmacia text,
    operacion text not null check (operacion in ('INSERT', 'UPDATE')),
    antes jsonb,
    despues jsonb not null,
    autor text not null check (char_length(autor) between 1 and 60),
    created_at timestamptz not null default now()
);
create index if not exists trabajadores_historial_registro_idx
    on public.trabajadores_historial (tabla, registro_id, created_at);
comment on table public.trabajadores_historial is
    'Historial solo de insercion del modulo de Trabajadores; lo escribe el trigger cf_trab_historial().';

-- --------------------------------------------------------------------------- funciones de trigger

-- Farmacia habilitada en el modulo (vale para cualquier rol, tambien los que se saltan RLS).
create or replace function public.cf_trab_comprobar_farmacia()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if new.farmacia is not null and not exists (
        select 1 from public.cf_modulos_farmacias m
        where m.modulo = 'TRABAJADORES' and new.farmacia = any(m.farmacias)
    ) then
        raise exception 'FARMACIA_NO_HABILITADA_EN_MODULO:%', new.farmacia;
    end if;
    return new;
end;
$$;

-- Evento dentro del alta y la baja de una trabajadora no anulada.
create or replace function public.cf_trab_comprobar_evento()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
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

-- Historial: una fila por INSERT o UPDATE, con el autor que indica la web.
create or replace function public.cf_trab_historial()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_autor text := btrim(coalesce(current_setting('cf.autor', true), ''));
    v_despues jsonb := to_jsonb(new);
    v_registro text := coalesce(v_despues ->> 'id', v_despues ->> 'anio');
begin
    if v_autor = '' then
        raise exception 'AUTOR_AUSENTE';
    end if;
    insert into public.trabajadores_historial (tabla, registro_id, farmacia, operacion, antes, despues, autor)
    values (tg_table_name, v_registro, v_despues ->> 'farmacia', tg_op,
            case when tg_op = 'UPDATE' then to_jsonb(old) end, v_despues, v_autor);
    return null;
end;
$$;

create or replace function public.cf_trab_historial_solo_insercion()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    raise exception 'trabajadores_historial es solo de insercion';
end;
$$;

revoke all on function public.cf_trab_comprobar_farmacia() from public, anon, authenticated, service_role;
revoke all on function public.cf_trab_comprobar_evento() from public, anon, authenticated, service_role;
revoke all on function public.cf_trab_historial() from public, anon, authenticated, service_role;
revoke all on function public.cf_trab_historial_solo_insercion() from public, anon, authenticated, service_role;

-- --------------------------------------------------------------------------- triggers

drop trigger if exists trabajadoras_farmacia on public.trabajadoras;
create trigger trabajadoras_farmacia before insert or update on public.trabajadoras
for each row execute function public.cf_trab_comprobar_farmacia();
drop trigger if exists eventos_calendario_farmacia on public.eventos_calendario;
create trigger eventos_calendario_farmacia before insert or update on public.eventos_calendario
for each row execute function public.cf_trab_comprobar_farmacia();
drop trigger if exists guardias_farmacia_farmacia on public.guardias_farmacia;
create trigger guardias_farmacia_farmacia before insert or update on public.guardias_farmacia
for each row execute function public.cf_trab_comprobar_farmacia();
drop trigger if exists festivos_farmacia on public.festivos;
create trigger festivos_farmacia before insert or update on public.festivos
for each row execute function public.cf_trab_comprobar_farmacia();

drop trigger if exists eventos_calendario_alta on public.eventos_calendario;
create trigger eventos_calendario_alta before insert or update on public.eventos_calendario
for each row execute function public.cf_trab_comprobar_evento();

drop trigger if exists trabajadoras_updated_at on public.trabajadoras;
create trigger trabajadoras_updated_at before update on public.trabajadoras
for each row execute function public.cf_set_updated_at();
drop trigger if exists convenio_anual_updated_at on public.convenio_anual;
create trigger convenio_anual_updated_at before update on public.convenio_anual
for each row execute function public.cf_set_updated_at();
drop trigger if exists eventos_calendario_updated_at on public.eventos_calendario;
create trigger eventos_calendario_updated_at before update on public.eventos_calendario
for each row execute function public.cf_set_updated_at();
drop trigger if exists guardias_farmacia_updated_at on public.guardias_farmacia;
create trigger guardias_farmacia_updated_at before update on public.guardias_farmacia
for each row execute function public.cf_set_updated_at();
drop trigger if exists festivos_updated_at on public.festivos;
create trigger festivos_updated_at before update on public.festivos
for each row execute function public.cf_set_updated_at();

drop trigger if exists trabajadoras_historial on public.trabajadoras;
create trigger trabajadoras_historial after insert or update on public.trabajadoras
for each row execute function public.cf_trab_historial();
drop trigger if exists convenio_anual_historial on public.convenio_anual;
create trigger convenio_anual_historial after insert or update on public.convenio_anual
for each row execute function public.cf_trab_historial();
drop trigger if exists eventos_calendario_historial on public.eventos_calendario;
create trigger eventos_calendario_historial after insert or update on public.eventos_calendario
for each row execute function public.cf_trab_historial();
drop trigger if exists guardias_farmacia_historial on public.guardias_farmacia;
create trigger guardias_farmacia_historial after insert or update on public.guardias_farmacia
for each row execute function public.cf_trab_historial();
drop trigger if exists festivos_historial on public.festivos;
create trigger festivos_historial after insert or update on public.festivos
for each row execute function public.cf_trab_historial();

drop trigger if exists trabajadores_historial_bloquear_cambios on public.trabajadores_historial;
create trigger trabajadores_historial_bloquear_cambios before update or delete on public.trabajadores_historial
for each row execute function public.cf_trab_historial_solo_insercion();
drop trigger if exists trabajadores_historial_bloquear_truncate on public.trabajadores_historial;
create trigger trabajadores_historial_bloquear_truncate before truncate on public.trabajadores_historial
for each statement execute function public.cf_trab_historial_solo_insercion();

-- --------------------------------------------------------------------------- vista de horas

create or replace view public.v_eventos_calendario_horas
with (security_invoker = true) as
select e.id, e.trabajadora_id, e.farmacia, e.fecha, e.franja, e.tipo, e.estado, e.horas, e.nota,
       coalesce(e.horas, case when t.tipo_jornada = 'COMPLETA'
                              then case e.franja when 'MANANA' then 4.50 else 3.50 end
                              else t.horas_diarias end)::numeric(4,2) as horas_efectivas
from public.eventos_calendario e
join public.trabajadoras t on t.id = e.trabajadora_id;

-- --------------------------------------------------------------------------- privilegios

-- Supabase concede por defecto privilegios sobre las tablas, vistas y secuencias nuevas de public: se retiran todos.
revoke all on table public.cf_modulos_farmacias, public.trabajadoras, public.convenio_anual,
    public.eventos_calendario, public.guardias_farmacia, public.festivos, public.trabajadores_historial,
    public.v_eventos_calendario_horas
from public, anon, authenticated, service_role;
revoke all on sequence public.trabajadores_historial_id_seq from public, anon, authenticated, service_role;

grant usage on schema public to cf_trabajadores_web;
grant select, insert, update on public.trabajadoras, public.convenio_anual, public.eventos_calendario,
    public.guardias_farmacia, public.festivos
to cf_trabajadores_web;
grant select on public.trabajadores_historial, public.cf_modulos_farmacias, public.v_eventos_calendario_horas
to cf_trabajadores_web;

grant select on public.cf_modulos_farmacias, public.trabajadoras, public.convenio_anual, public.eventos_calendario,
    public.guardias_farmacia, public.festivos, public.trabajadores_historial, public.v_eventos_calendario_horas
to cf_lectura;

-- --------------------------------------------------------------------------- RLS

alter table public.cf_modulos_farmacias enable row level security;
alter table public.trabajadoras enable row level security;
alter table public.convenio_anual enable row level security;
alter table public.eventos_calendario enable row level security;
alter table public.guardias_farmacia enable row level security;
alter table public.festivos enable row level security;
alter table public.trabajadores_historial enable row level security;

drop policy if exists cf_modulos_farmacias_trab_select on public.cf_modulos_farmacias;
create policy cf_modulos_farmacias_trab_select on public.cf_modulos_farmacias
    for select to cf_trabajadores_web, cf_lectura using (true);

drop policy if exists convenio_anual_trab_select on public.convenio_anual;
create policy convenio_anual_trab_select on public.convenio_anual
    for select to cf_trabajadores_web, cf_lectura using (true);
drop policy if exists convenio_anual_trab_insert on public.convenio_anual;
create policy convenio_anual_trab_insert on public.convenio_anual
    for insert to cf_trabajadores_web with check (true);
drop policy if exists convenio_anual_trab_update on public.convenio_anual;
create policy convenio_anual_trab_update on public.convenio_anual
    for update to cf_trabajadores_web using (true) with check (true);

do $$
declare
    v_tabla text;
    v_regla text := 'exists (select 1 from public.cf_modulos_farmacias m where m.modulo = ''TRABAJADORES'' '
                    'and farmacia = any(m.farmacias))';
    v_regla_opcional text := '(farmacia is null or exists (select 1 from public.cf_modulos_farmacias m '
                             'where m.modulo = ''TRABAJADORES'' and farmacia = any(m.farmacias)))';
    v_condicion text;
begin
    foreach v_tabla in array array['trabajadoras', 'eventos_calendario', 'guardias_farmacia', 'festivos'] loop
        v_condicion := case when v_tabla = 'festivos' then v_regla_opcional else v_regla end;
        execute format('drop policy if exists %I on public.%I', v_tabla || '_trab_select', v_tabla);
        execute format('create policy %I on public.%I for select to cf_trabajadores_web, cf_lectura using (%s)',
                       v_tabla || '_trab_select', v_tabla, v_condicion);
        execute format('drop policy if exists %I on public.%I', v_tabla || '_trab_insert', v_tabla);
        execute format('create policy %I on public.%I for insert to cf_trabajadores_web with check (%s)',
                       v_tabla || '_trab_insert', v_tabla, v_condicion);
        execute format('drop policy if exists %I on public.%I', v_tabla || '_trab_update', v_tabla);
        execute format('create policy %I on public.%I for update to cf_trabajadores_web using (%s) with check (%s)',
                       v_tabla || '_trab_update', v_tabla, v_condicion, v_condicion);
    end loop;
    execute 'drop policy if exists trabajadores_historial_trab_select on public.trabajadores_historial';
    execute format('create policy trabajadores_historial_trab_select on public.trabajadores_historial '
                   'for select to cf_trabajadores_web, cf_lectura using (%s)', v_regla_opcional);
end;
$$;

commit;
