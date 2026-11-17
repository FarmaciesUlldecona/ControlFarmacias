-- Migracion 35 (Hito H6): marcas de pago de vencimientos y forma de pago por proveedor, peticion de la web (excepcion
-- autorizada por Pio; D1-D9 aprobadas el 2026-11-16). Diseno: pruebas/auditoria_h6/DISENO.md. Propuesta de la web:
-- origin/web/fase1:web/docs/propuesta_tablas_h6_pagos.sql (91ae084, «NO APLICAR»).
-- - La web escribe SOLO en vencimientos_marcas_pago y proveedores_forma_pago, con el rol cf_pagos_web (LOGIN sin
--   contrasena en el repositorio: la fija Pio fuera, con SCRAM): SELECT, INSERT y UPDATE en esas dos tablas y SELECT en
--   pagos_historial. Nada sobre facturas, vencimientos, conciliacion ni ninguna otra tabla.
-- - Solo anular: una fila solo admite pasar anulada de false a true (SOLO_ANULAR); nadie borra ni vacia
--   (BORRADO_NO_PERMITIDO); corregir es anular y crear otra fila.
-- - Autor por transaccion (set local cf.autor; sin el, AUTOR_AUSENTE); historial propio por trigger, solo de insercion.
-- - Farmacia (D1): PIO o RITA en el check; la barrera es cf_configuracion.farmacias_habilitadas (la de facturas, no la
--   del modulo de Trabajadores), en los triggers y en la RLS.
-- - Vencimiento por (factura_id, vencimiento_orden), sin claves externas (D7): la persistencia borra y reinserta los
--   vencimientos y conserva el id de la factura. El trigger copia fecha e importe del vencimiento al marcar, para
--   detectar una marca desfasada tras un reproceso. Sin importe o sin fecha no se marca.
-- - Fecha de pago no posterior a hoy en Europe/Madrid (D3); DOMICILIADOS (D2): forma DOMICILIACION, fecha de pago =
--   fecha de vencimiento y vencimiento ya pasado.
-- - cf_lectura: SELECT de las tres tablas (D4), con la misma regla de farmacia que la 29 (sin funciones).
-- - El sistema no lee estas tablas para decidir nada. PAGADO_BANCO queda reservado, sin esquema (D6).
-- anon, authenticated y el rol del sistema: ningun privilegio sobre las tablas, la secuencia ni las funciones nuevas
-- (AUTORIZACION EXPRESA DE PIO, 2026-11-16, D8: el rol del sistema se nombra SOLO aqui y en el rollback).
-- Solo anade objetos: ninguna tabla, funcion, politica ni privilegio existente cambia. Idempotente. Requiere la 34.
begin;

do $$
begin
    if to_regclass('public.guardias_semana') is null then
        raise exception 'MIGRACION_34_AUSENTE';
    end if;
    if not exists (select 1 from pg_roles where rolname = 'cf_pagos_web') then
        create role cf_pagos_web login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls
            connection limit 5;
    end if;
end;
$$;

-- Los atributos solo se fijan al crear el rol (2BN-D: en Supabase postgres no es superusuario).
alter role cf_pagos_web set statement_timeout = '60s';
alter role cf_pagos_web set idle_in_transaction_session_timeout = '60s';

-- --------------------------------------------------------------------------- tablas

create table if not exists public.vencimientos_marcas_pago (
    id uuid primary key default gen_random_uuid(),
    farmacia text not null check (farmacia in ('PIO', 'RITA')),
    factura_id uuid not null,
    vencimiento_orden integer not null,
    fecha_vencimiento date not null,
    importe numeric(14,4) not null,
    fecha_pago date not null,
    forma text not null check (forma in ('DOMICILIACION', 'TRANSFERENCIA', 'EFECTIVO', 'COMPENSACION_ABONO')),
    origen text not null default 'MANUAL' check (origen in ('MANUAL', 'DOMICILIADOS')),
    anulada boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint vencimientos_marcas_pago_domiciliados_forma check (origen <> 'DOMICILIADOS' or forma = 'DOMICILIACION')
);
create unique index if not exists vencimientos_marcas_pago_vigente
    on public.vencimientos_marcas_pago (farmacia, factura_id, vencimiento_orden) where not anulada;
comment on table public.vencimientos_marcas_pago is
    'Marca de pago manual de un vencimiento (factura_id, orden), escrita por la web. El sistema no la lee. '
    'Se anula, no se borra; historial por trigger.';

create table if not exists public.proveedores_forma_pago (
    id uuid primary key default gen_random_uuid(),
    farmacia text not null check (farmacia in ('PIO', 'RITA')),
    cif text not null check (cif ~ '^[A-Z0-9]{5,20}$'),
    forma text not null check (forma in ('DOMICILIACION', 'TRANSFERENCIA', 'EFECTIVO', 'COMPENSACION_ABONO')),
    anulada boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create unique index if not exists proveedores_forma_pago_vigente
    on public.proveedores_forma_pago (farmacia, cif) where not anulada;
comment on table public.proveedores_forma_pago is
    'Forma de pago por CIF y farmacia, escrita por la web (sin fila: DOMICILIACION). Se anula, no se borra.';

create table if not exists public.pagos_historial (
    id bigint generated always as identity primary key,
    tabla text not null check (tabla in ('vencimientos_marcas_pago', 'proveedores_forma_pago')),
    registro_id text not null,
    farmacia text,
    operacion text not null check (operacion in ('INSERT', 'UPDATE')),
    antes jsonb,
    despues jsonb not null,
    autor text not null check (char_length(autor) between 1 and 60),
    created_at timestamptz not null default now()
);
create index if not exists pagos_historial_registro_idx on public.pagos_historial (tabla, registro_id, created_at);
comment on table public.pagos_historial is
    'Historial solo de insercion de las marcas de pago (H6); lo escribe el trigger cf_pagos_historial().';

-- --------------------------------------------------------------------------- funciones

-- Farmacia habilitada para facturas (cf_configuracion). Security definer: la usa la RLS de cf_pagos_web, que no lee
-- cf_configuracion. cf_lectura no la ejecuta (2BN: ninguna funcion security definer).
create or replace function public.cf_pagos_farmacia_habilitada(p_farmacia text)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select exists (select 1 from public.cf_configuracion c where c.id and p_farmacia = any(c.farmacias_habilitadas))
$$;

-- Fecha del calendario de Espana en un momento dado (D3): no depende de la zona de la sesion.
create or replace function public.cf_pagos_dia_madrid(p_momento timestamptz)
returns date
language sql
stable
set search_path = public, pg_temp
as $$
    select (p_momento at time zone 'Europe/Madrid')::date
$$;

-- Al insertar: farmacia habilitada (vale tambien para los roles que se saltan RLS).
create or replace function public.cf_pagos_comprobar_farmacia()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if not public.cf_pagos_farmacia_habilitada(new.farmacia) then
        raise exception 'FARMACIA_NO_HABILITADA:%', new.farmacia;
    end if;
    return new;
end;
$$;

-- Al insertar una marca: la factura existe y es de esa farmacia; el vencimiento (factura, orden) existe con fecha e
-- importe, que se copian; fecha de pago no posterior a hoy en Madrid; DOMICILIADOS solo en su fecha y ya vencido.
create or replace function public.cf_pagos_validar_marca()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_farmacia text;
    v_fecha date;
    v_importe numeric(14,4);
    v_hoy date := public.cf_pagos_dia_madrid(now());
begin
    select f.farmacia into v_farmacia from public.facturas f where f.id = new.factura_id;
    if not found then
        raise exception 'FACTURA_NO_ENCONTRADA:%', new.factura_id;
    end if;
    if v_farmacia <> new.farmacia then
        raise exception 'FARMACIA_DISTINTA_DE_LA_FACTURA:%:%', new.farmacia, v_farmacia;
    end if;
    select v.fecha_vencimiento, v.importe into v_fecha, v_importe
    from public.facturas_vencimientos v
    where v.factura_id = new.factura_id and v.orden = new.vencimiento_orden;
    if not found then
        raise exception 'VENCIMIENTO_NO_ENCONTRADO:%:%', new.factura_id, new.vencimiento_orden;
    end if;
    if v_fecha is null then
        raise exception 'VENCIMIENTO_SIN_FECHA:%:%', new.factura_id, new.vencimiento_orden;
    end if;
    if v_importe is null then
        raise exception 'VENCIMIENTO_SIN_IMPORTE:%:%', new.factura_id, new.vencimiento_orden;
    end if;
    new.fecha_vencimiento := v_fecha;
    new.importe := v_importe;
    if new.fecha_pago > v_hoy then
        raise exception 'FECHA_PAGO_FUTURA:%', new.fecha_pago;
    end if;
    if new.origen = 'DOMICILIADOS' and (new.fecha_pago <> v_fecha or v_fecha >= v_hoy) then
        raise exception 'DOMICILIADO_NO_VALIDO:%:%', new.fecha_pago, v_fecha;
    end if;
    return new;
end;
$$;

-- Solo anular (false -> true, sin cambiar nada mas) y nunca borrar ni vaciar.
create or replace function public.cf_pagos_solo_anular()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    if tg_op in ('DELETE', 'TRUNCATE') then
        raise exception 'BORRADO_NO_PERMITIDO';
    end if;
    if old.anulada or not new.anulada
       or (to_jsonb(new) - 'anulada' - 'updated_at') is distinct from (to_jsonb(old) - 'anulada' - 'updated_at') then
        raise exception 'SOLO_ANULAR';
    end if;
    return new;
end;
$$;

-- Historial: una fila por INSERT o UPDATE, con el autor que indica la web.
create or replace function public.cf_pagos_historial()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_autor text := btrim(coalesce(current_setting('cf.autor', true), ''));
    v_despues jsonb := to_jsonb(new);
begin
    if v_autor = '' then
        raise exception 'AUTOR_AUSENTE';
    end if;
    insert into public.pagos_historial (tabla, registro_id, farmacia, operacion, antes, despues, autor)
    values (tg_table_name, v_despues ->> 'id', v_despues ->> 'farmacia', tg_op,
            case when tg_op = 'UPDATE' then to_jsonb(old) end, v_despues, v_autor);
    return null;
end;
$$;

create or replace function public.cf_pagos_historial_solo_insercion()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    raise exception 'pagos_historial es solo de insercion';
end;
$$;

revoke all on function public.cf_pagos_farmacia_habilitada(text) from public, anon, authenticated, service_role;
revoke all on function public.cf_pagos_dia_madrid(timestamptz) from public, anon, authenticated, service_role;
revoke all on function public.cf_pagos_comprobar_farmacia() from public, anon, authenticated, service_role;
revoke all on function public.cf_pagos_validar_marca() from public, anon, authenticated, service_role;
revoke all on function public.cf_pagos_solo_anular() from public, anon, authenticated, service_role;
revoke all on function public.cf_pagos_historial() from public, anon, authenticated, service_role;
revoke all on function public.cf_pagos_historial_solo_insercion() from public, anon, authenticated, service_role;
grant execute on function public.cf_pagos_farmacia_habilitada(text) to cf_pagos_web;

-- --------------------------------------------------------------------------- triggers

-- Por nombre, en cada momento: farmacia antes que validar; solo_anular antes que updated_at.
drop trigger if exists vencimientos_marcas_pago_farmacia on public.vencimientos_marcas_pago;
create trigger vencimientos_marcas_pago_farmacia before insert on public.vencimientos_marcas_pago
for each row execute function public.cf_pagos_comprobar_farmacia();
drop trigger if exists vencimientos_marcas_pago_validar on public.vencimientos_marcas_pago;
create trigger vencimientos_marcas_pago_validar before insert on public.vencimientos_marcas_pago
for each row execute function public.cf_pagos_validar_marca();
drop trigger if exists vencimientos_marcas_pago_solo_anular on public.vencimientos_marcas_pago;
create trigger vencimientos_marcas_pago_solo_anular before update or delete on public.vencimientos_marcas_pago
for each row execute function public.cf_pagos_solo_anular();
drop trigger if exists vencimientos_marcas_pago_sin_truncate on public.vencimientos_marcas_pago;
create trigger vencimientos_marcas_pago_sin_truncate before truncate on public.vencimientos_marcas_pago
for each statement execute function public.cf_pagos_solo_anular();
drop trigger if exists vencimientos_marcas_pago_updated_at on public.vencimientos_marcas_pago;
create trigger vencimientos_marcas_pago_updated_at before update on public.vencimientos_marcas_pago
for each row execute function public.cf_set_updated_at();
drop trigger if exists vencimientos_marcas_pago_historial on public.vencimientos_marcas_pago;
create trigger vencimientos_marcas_pago_historial after insert or update on public.vencimientos_marcas_pago
for each row execute function public.cf_pagos_historial();

drop trigger if exists proveedores_forma_pago_farmacia on public.proveedores_forma_pago;
create trigger proveedores_forma_pago_farmacia before insert on public.proveedores_forma_pago
for each row execute function public.cf_pagos_comprobar_farmacia();
drop trigger if exists proveedores_forma_pago_solo_anular on public.proveedores_forma_pago;
create trigger proveedores_forma_pago_solo_anular before update or delete on public.proveedores_forma_pago
for each row execute function public.cf_pagos_solo_anular();
drop trigger if exists proveedores_forma_pago_sin_truncate on public.proveedores_forma_pago;
create trigger proveedores_forma_pago_sin_truncate before truncate on public.proveedores_forma_pago
for each statement execute function public.cf_pagos_solo_anular();
drop trigger if exists proveedores_forma_pago_updated_at on public.proveedores_forma_pago;
create trigger proveedores_forma_pago_updated_at before update on public.proveedores_forma_pago
for each row execute function public.cf_set_updated_at();
drop trigger if exists proveedores_forma_pago_historial on public.proveedores_forma_pago;
create trigger proveedores_forma_pago_historial after insert or update on public.proveedores_forma_pago
for each row execute function public.cf_pagos_historial();

drop trigger if exists pagos_historial_bloquear_cambios on public.pagos_historial;
create trigger pagos_historial_bloquear_cambios before update or delete on public.pagos_historial
for each row execute function public.cf_pagos_historial_solo_insercion();
drop trigger if exists pagos_historial_bloquear_truncate on public.pagos_historial;
create trigger pagos_historial_bloquear_truncate before truncate on public.pagos_historial
for each statement execute function public.cf_pagos_historial_solo_insercion();

-- --------------------------------------------------------------------------- privilegios

-- Supabase concede por defecto privilegios sobre las tablas y secuencias nuevas de public: se retiran todos.
revoke all on table public.vencimientos_marcas_pago, public.proveedores_forma_pago, public.pagos_historial
from public, anon, authenticated, service_role;
revoke all on sequence public.pagos_historial_id_seq from public, anon, authenticated, service_role;

grant usage on schema public to cf_pagos_web;
grant select, insert, update on public.vencimientos_marcas_pago, public.proveedores_forma_pago to cf_pagos_web;
grant select on public.pagos_historial to cf_pagos_web;
grant select on public.vencimientos_marcas_pago, public.proveedores_forma_pago, public.pagos_historial to cf_lectura;

-- --------------------------------------------------------------------------- RLS

alter table public.vencimientos_marcas_pago enable row level security;
alter table public.proveedores_forma_pago enable row level security;
alter table public.pagos_historial enable row level security;

do $$
declare
    v_tabla text;
    v_web text := 'public.cf_pagos_farmacia_habilitada(farmacia)';
    v_lectura text := 'exists (select 1 from public.cf_configuracion c where c.id = true '
                      'and farmacia = any(c.farmacias_habilitadas))';
begin
    foreach v_tabla in array array['vencimientos_marcas_pago', 'proveedores_forma_pago', 'pagos_historial'] loop
        execute format('drop policy if exists %I on public.%I', v_tabla || '_pagos_select', v_tabla);
        execute format('create policy %I on public.%I for select to cf_pagos_web using (%s)',
                       v_tabla || '_pagos_select', v_tabla, v_web);
        execute format('drop policy if exists %I on public.%I', v_tabla || '_lectura_select', v_tabla);
        execute format('create policy %I on public.%I for select to cf_lectura using (%s)',
                       v_tabla || '_lectura_select', v_tabla, v_lectura);
        if v_tabla <> 'pagos_historial' then
            execute format('drop policy if exists %I on public.%I', v_tabla || '_pagos_insert', v_tabla);
            execute format('create policy %I on public.%I for insert to cf_pagos_web with check (%s)',
                           v_tabla || '_pagos_insert', v_tabla, v_web);
            execute format('drop policy if exists %I on public.%I', v_tabla || '_pagos_update', v_tabla);
            execute format('create policy %I on public.%I for update to cf_pagos_web using (%s) with check (%s)',
                           v_tabla || '_pagos_update', v_tabla, v_web, v_web);
        end if;
    end loop;
end;
$$;

commit;
