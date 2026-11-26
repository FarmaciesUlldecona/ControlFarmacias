-- Migracion 40 (Hito H7b): prevision de Cashflow con apuntes manuales de la web. Diseno:
-- pruebas/auditoria_h7b/DISENO.md, corregido a peticion de la web y aprobado por Pio (OK del 2026-11-26; decisiones
-- H7B-D1 a D8 del 2026-11-25).
-- - Tablas: cf_cashflow_conceptos (conceptos nuevos, siempre de una categoria de la plantilla; proveedor_cif opcional
--   para colocar vencimientos, H7B-D3), cf_cashflow_recurrentes (mensual, trimestral o anual; dia 29-31 -> ultimo dia
--   del mes, H7B-D1) y cf_cashflow_apuntes (sueltos y anulaciones de una ocurrencia, H7B-D2), con historial por
--   trigger en cf_cashflow_apuntes_historial (solo insercion).
-- - Anular en lugar de borrar: el unico UPDATE es anular (anulado false -> true, con motivo; anulado_por y anulado_at
--   los pone el trigger) y, en un apunte suelto, la sustitucion confirmada por Pio (factura y orden del vencimiento),
--   que lo anula (H7B-D6). Nadie borra ni vacia (BORRADO_NO_PERMITIDO).
-- - Autor por transaccion (set local cf.autor; sin el, AUTOR_AUSENTE).
-- - Validaciones al dar de alta (fallan cerrado): cuenta PIO o RITA de una farmacia del modulo CASHFLOW; importacion
--   vigente; categoria de la plantilla de la cuenta en la vigente; concepto de la plantilla o de cf_cashflow_conceptos;
--   importe > 0; fecha (o alguna ocurrencia) posterior al fin de la ultima decena con saldo de bancos de la vigente.
-- - Ocurrencias calculadas al leer, nunca guardadas: cf_cashflow_ocurrencias(desde, hasta), stable, sin security
--   definer (regla del 2BN). La eleccion de fuente por celda y la media son del motor de la web (DISENO §2.1).
-- - Rol de escritura de la web cf_cashflow_web (LOGIN sin contrasena en el repositorio: la fija Pio fuera, con SCRAM):
--   SELECT e INSERT en las tres tablas, UPDATE solo de las columnas de anulacion (y de sustitucion en apuntes), SELECT
--   del historial y EXECUTE de la funcion de ocurrencias. Nada mas.
-- - RLS por el modulo CASHFLOW (cf_modulos_farmacias: hoy PIO y RITA); cf_lectura lee las cuatro tablas con la misma
--   regla sin funciones security definer (2BN). farmacias_habilitadas no cambia: la excepcion de RITA es solo Cashflow.
-- - El sistema no lee estas tablas para decidir nada; las tablas importadas de la 38 no cambian.
-- AUTORIZACION EXPRESA DE PIO (DISENO §0 y §4; reconfirmada el 2026-11-26): esta migracion y su rollback son los
-- UNICOS ficheros de H7b que nombran el rol del sistema: se le quitan los privilegios por defecto de Supabase sobre lo
-- nuevo. Nada para anon, authenticated, el rol del sistema ni PUBLIC.
-- Solo anade objetos: ninguna tabla, funcion, politica ni privilegio existente cambia. Idempotente. Requiere la 39.
begin;

do $$
begin
    if not exists (select 1 from information_schema.columns where table_schema = 'public'
                   and table_name = 'cf_configuracion' and column_name = 'conciliacion_r21') then
        raise exception 'MIGRACION_39_AUSENTE';
    end if;
    if not exists (select 1 from pg_roles where rolname = 'cf_cashflow_web') then
        create role cf_cashflow_web login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls
            connection limit 5;
    end if;
end;
$$;

-- Los atributos solo se fijan al crear el rol (2BN-D: en Supabase postgres no es superusuario).
alter role cf_cashflow_web set statement_timeout = '60s';
alter role cf_cashflow_web set idle_in_transaction_session_timeout = '60s';

-- --------------------------------------------------------------------------- tablas

create table if not exists public.cf_cashflow_conceptos (
    id uuid primary key default gen_random_uuid(),
    cuenta text not null check (cuenta in ('PIO', 'RITA')),
    farmacia text not null,
    categoria text not null check (categoria ~ '^R[ES] '),
    nombre text not null check (char_length(btrim(nombre)) between 1 and 120),
    proveedor_cif text check (proveedor_cif ~ '^[A-Z0-9]{5,20}$'),
    autor text not null check (char_length(autor) between 1 and 60),
    creado_at timestamptz not null default now(),
    anulado boolean not null default false,
    anulado_por text,
    anulado_at timestamptz,
    motivo_anulacion text,
    constraint cf_cashflow_conceptos_farmacia check (farmacia = cuenta),
    constraint cf_cashflow_conceptos_anulacion check (
        (not anulado and anulado_por is null and anulado_at is null and motivo_anulacion is null)
        or (anulado and char_length(anulado_por) between 1 and 60 and anulado_at is not null
            and char_length(btrim(motivo_anulacion)) between 1 and 500))
);
create unique index if not exists cf_cashflow_conceptos_vigente
    on public.cf_cashflow_conceptos (cuenta, categoria, lower(regexp_replace(btrim(nombre), '\s+', ' ', 'g')))
    where not anulado;
create unique index if not exists cf_cashflow_conceptos_cif
    on public.cf_cashflow_conceptos (cuenta, proveedor_cif) where not anulado and proveedor_cif is not null;
comment on table public.cf_cashflow_conceptos is
    'Conceptos nuevos de Cashflow (H7b), cada uno de una categoria de la plantilla de su cuenta; proveedor_cif coloca '
    'los vencimientos de ese proveedor (H7B-D3). Escritos por la web; se anulan, no se borran; historial por trigger.';

create table if not exists public.cf_cashflow_recurrentes (
    id uuid primary key default gen_random_uuid(),
    cuenta text not null check (cuenta in ('PIO', 'RITA')),
    farmacia text not null,
    categoria text not null check (categoria ~ '^R[ES] '),
    concepto text not null check (char_length(btrim(concepto)) between 1 and 255),
    importe numeric(14,2) not null check (importe > 0),
    nota text check (char_length(nota) <= 500),
    frecuencia text not null check (frecuencia in ('MENSUAL', 'TRIMESTRAL', 'ANUAL')),
    dia integer not null check (dia between 1 and 31),
    inicio date not null,
    fin date,
    autor text not null check (char_length(autor) between 1 and 60),
    creado_at timestamptz not null default now(),
    anulado boolean not null default false,
    anulado_por text,
    anulado_at timestamptz,
    motivo_anulacion text,
    constraint cf_cashflow_recurrentes_farmacia check (farmacia = cuenta),
    constraint cf_cashflow_recurrentes_fin check (fin is null or fin >= inicio),
    constraint cf_cashflow_recurrentes_anulacion check (
        (not anulado and anulado_por is null and anulado_at is null and motivo_anulacion is null)
        or (anulado and char_length(anulado_por) between 1 and 60 and anulado_at is not null
            and char_length(btrim(motivo_anulacion)) between 1 and 500))
);
comment on table public.cf_cashflow_recurrentes is
    'Apuntes recurrentes de Cashflow (H7b): las ocurrencias se calculan al leer (cf_cashflow_ocurrencias). Anular la '
    'recurrente anula todas sus ocurrencias. Escritos por la web; se anulan, no se borran; historial por trigger.';

create table if not exists public.cf_cashflow_apuntes (
    id uuid primary key default gen_random_uuid(),
    cuenta text not null check (cuenta in ('PIO', 'RITA')),
    farmacia text not null,
    fecha date not null,
    categoria text not null check (categoria ~ '^R[ES] '),
    concepto text not null check (char_length(btrim(concepto)) between 1 and 255),
    importe numeric(14,2) check (importe > 0),
    nota text check (char_length(nota) <= 500),
    recurrente_id uuid references public.cf_cashflow_recurrentes (id),
    fecha_ocurrencia date,
    sustituido_factura_id uuid,
    sustituido_vencimiento_orden integer,
    autor text not null check (char_length(autor) between 1 and 60),
    creado_at timestamptz not null default now(),
    anulado boolean not null default false,
    anulado_por text,
    anulado_at timestamptz,
    motivo_anulacion text,
    constraint cf_cashflow_apuntes_farmacia check (farmacia = cuenta),
    -- Suelto (con importe) o anulacion de una ocurrencia de una recurrente (sin importe).
    constraint cf_cashflow_apuntes_tipo check (
        (recurrente_id is null and fecha_ocurrencia is null and importe is not null)
        or (recurrente_id is not null and fecha_ocurrencia is not null and importe is null
            and fecha = fecha_ocurrencia)),
    constraint cf_cashflow_apuntes_sustitucion check (
        (sustituido_factura_id is null) = (sustituido_vencimiento_orden is null)
        and (sustituido_factura_id is null or recurrente_id is not null or anulado)),
    constraint cf_cashflow_apuntes_anulacion check (
        (not anulado and anulado_por is null and anulado_at is null and motivo_anulacion is null)
        or (anulado and char_length(anulado_por) between 1 and 60 and anulado_at is not null
            and char_length(btrim(motivo_anulacion)) between 1 and 500))
);
create unique index if not exists cf_cashflow_apuntes_ocurrencia
    on public.cf_cashflow_apuntes (recurrente_id, fecha_ocurrencia) where recurrente_id is not null and not anulado;
create unique index if not exists cf_cashflow_apuntes_sustituto
    on public.cf_cashflow_apuntes (sustituido_factura_id, sustituido_vencimiento_orden)
    where sustituido_factura_id is not null and (recurrente_id is null or not anulado);
create index if not exists cf_cashflow_apuntes_cuenta_fecha_idx on public.cf_cashflow_apuntes (cuenta, fecha);
comment on table public.cf_cashflow_apuntes is
    'Apuntes sueltos de Cashflow (H7b, importe > 0; el sentido lo da la categoria) y anulaciones de una ocurrencia de '
    'una recurrente (sin importe). Sustitucion confirmada por Pio: factura y orden del vencimiento; el apunte queda '
    'anulado. Escritos por la web; se anulan, no se borran; historial por trigger.';

create table if not exists public.cf_cashflow_apuntes_historial (
    id bigint generated always as identity primary key,
    tabla text not null check (tabla in ('cf_cashflow_conceptos', 'cf_cashflow_recurrentes', 'cf_cashflow_apuntes')),
    registro_id uuid not null,
    cuenta text not null,
    farmacia text not null,
    operacion text not null check (operacion in ('INSERT', 'UPDATE')),
    antes jsonb,
    despues jsonb not null,
    autor text not null check (char_length(autor) between 1 and 60),
    created_at timestamptz not null default now()
);
create index if not exists cf_cashflow_apuntes_historial_registro_idx
    on public.cf_cashflow_apuntes_historial (tabla, registro_id, created_at);
comment on table public.cf_cashflow_apuntes_historial is
    'Historial solo de insercion de conceptos, recurrentes y apuntes de Cashflow (H7b); lo escribe el trigger '
    'cf_cashflow_prevision_historial().';

-- --------------------------------------------------------------------------- funciones de lectura

-- Fechas de una recurrente entre dos fechas (H7B-D1): el dia del mes de cada periodo desde el mes de inicio; si el mes
-- no tiene ese dia, el ultimo del mes. Sin acceso a tablas.
create or replace function public.cf_cashflow_fechas_recurrente(p_frecuencia text, p_dia integer, p_inicio date,
                                                                 p_fin date, p_desde date, p_hasta date)
returns setof date
language sql
immutable
set search_path = public, pg_temp
as $$
    select x.fecha
    from (select case p_frecuencia when 'MENSUAL' then 1 when 'TRIMESTRAL' then 3 when 'ANUAL' then 12 end as paso) p
    cross join lateral generate_series(0, greatest(0, ((extract(year from p_hasta) - extract(year from p_inicio)) * 12
                                                       + extract(month from p_hasta) - extract(month from p_inicio))::integer
                                                   / p.paso)) k
    cross join lateral (select (date_trunc('month', p_inicio::timestamp) + make_interval(months => k * p.paso))::date
                               as mes) m
    cross join lateral (select (m.mes + (least(p_dia, extract(day from (m.mes::timestamp + interval '1 month - 1 day'))
                                                          ::integer) - 1))::date as fecha) x
    where p_dia between 1 and 31
      and x.fecha >= p_inicio and x.fecha >= p_desde and x.fecha <= p_hasta
      and (p_fin is null or x.fecha <= p_fin)
    order by x.fecha
$$;

-- Ocurrencias de las recurrentes no anuladas entre dos fechas, sin las anuladas una a una. Security invoker: la RLS
-- del que llama decide que filas ve. Devuelve todas las del intervalo: que cuenten solo las futuras (posteriores al
-- ultimo saldo de bancos de la cuenta y hasta la ultima decena de la vigente) lo aplica el motor de la web (§1.3).
create or replace function public.cf_cashflow_ocurrencias(p_desde date, p_hasta date)
returns table (recurrente_id uuid, cuenta text, farmacia text, categoria text, concepto text, importe numeric,
               fecha date)
language sql
stable
set search_path = public, pg_temp
as $$
    select r.id, r.cuenta, r.farmacia, r.categoria, r.concepto, r.importe, f.fecha
    from public.cf_cashflow_recurrentes r
    cross join lateral public.cf_cashflow_fechas_recurrente(r.frecuencia, r.dia, r.inicio, r.fin, p_desde, p_hasta)
        as f(fecha)
    where not r.anulado
      and not exists (select 1 from public.cf_cashflow_apuntes a
                      where a.recurrente_id = r.id and a.fecha_ocurrencia = f.fecha and not a.anulado)
    order by f.fecha, r.id
$$;

-- --------------------------------------------------------------------------- funciones de validacion (triggers)

-- Farmacia del modulo CASHFLOW. Security definer: la usa la RLS de cf_cashflow_web, que no lee cf_modulos_farmacias.
-- cf_lectura no la ejecuta (2BN: ninguna funcion security definer).
create or replace function public.cf_cashflow_farmacia_habilitada(p_farmacia text)
returns boolean
language sql
stable
security definer
set search_path = public, pg_temp
as $$
    select exists (select 1 from public.cf_modulos_farmacias m
                   where m.modulo = 'CASHFLOW' and p_farmacia = any(m.farmacias))
$$;

create or replace function public.cf_cashflow_autor()
returns text
language plpgsql
stable
set search_path = public, pg_temp
as $$
declare
    v_autor text := btrim(coalesce(current_setting('cf.autor', true), ''));
begin
    if v_autor = '' then
        raise exception 'AUTOR_AUSENTE';
    end if;
    return v_autor;
end;
$$;

-- Fin de la ultima decena con saldo de bancos (no nulo, E7) de la cuenta en la importacion vigente; null si no hay.
create or replace function public.cf_cashflow_ultimo_saldo_banco(p_cuenta text)
returns date
language sql
stable
set search_path = public, pg_temp
as $$
    select max(case extract(day from s.decena_inicio)::integer
                   when 21 then (date_trunc('month', s.decena_inicio::timestamp) + interval '1 month - 1 day')::date
                   else s.decena_inicio + 9 end)
    from public.cf_cashflow_saldos s
    join public.cf_cashflow_importaciones i on i.id = s.importacion_id and i.vigente
    where s.cuenta = p_cuenta and s.saldo_bancos is not null
$$;

-- Cuenta valida de una farmacia del modulo, importacion vigente, categoria de la plantilla y concepto conocido.
-- Devuelve la farmacia de la cuenta.
create or replace function public.cf_cashflow_validar_celda(p_cuenta text, p_categoria text, p_concepto text)
returns text
language plpgsql
stable
set search_path = public, pg_temp
as $$
declare
    v_farmacia text;
    v_vigente uuid;
begin
    select c.farmacia into v_farmacia from public.cf_cashflow_cuentas c
    where c.codigo = p_cuenta and p_cuenta in ('PIO', 'RITA');
    if v_farmacia is null then
        raise exception 'CUENTA_NO_VALIDA:%', p_cuenta;
    end if;
    if not public.cf_cashflow_farmacia_habilitada(v_farmacia) then
        raise exception 'FARMACIA_NO_HABILITADA:%', v_farmacia;
    end if;
    select i.id into v_vigente from public.cf_cashflow_importaciones i where i.vigente;
    if v_vigente is null then
        raise exception 'SIN_IMPORTACION_VIGENTE';
    end if;
    if not exists (select 1 from public.cf_cashflow_importes x
                   where x.importacion_id = v_vigente and x.cuenta = p_cuenta and x.categoria = p_categoria) then
        raise exception 'CATEGORIA_FUERA_DE_PLANTILLA:%', p_categoria;
    end if;
    if p_concepto is not null
       and not exists (select 1 from public.cf_cashflow_importes x
                       where x.importacion_id = v_vigente and x.cuenta = p_cuenta and x.categoria = p_categoria
                         and lower(regexp_replace(btrim(x.concepto), '\s+', ' ', 'g'))
                             = lower(regexp_replace(btrim(p_concepto), '\s+', ' ', 'g')))
       and not exists (select 1 from public.cf_cashflow_conceptos k
                       where not k.anulado and k.cuenta = p_cuenta and k.categoria = p_categoria
                         and lower(regexp_replace(btrim(k.nombre), '\s+', ' ', 'g'))
                             = lower(regexp_replace(btrim(p_concepto), '\s+', ' ', 'g'))) then
        raise exception 'CONCEPTO_DESCONOCIDO:%', p_concepto;
    end if;
    return v_farmacia;
end;
$$;

-- Ultimo saldo de bancos de la cuenta; sin el no se admite prevision (falla cerrado).
create or replace function public.cf_cashflow_referencia_futura(p_cuenta text)
returns date
language plpgsql
stable
set search_path = public, pg_temp
as $$
declare
    v_ultimo date := public.cf_cashflow_ultimo_saldo_banco(p_cuenta);
begin
    if v_ultimo is null then
        raise exception 'SIN_SALDO_DE_BANCO:%', p_cuenta;
    end if;
    return v_ultimo;
end;
$$;

-- Sustitucion (H7B-D6): el vencimiento (factura, orden) existe y su factura es de la farmacia de la cuenta.
create or replace function public.cf_cashflow_validar_sustitucion(p_farmacia text, p_factura uuid, p_orden integer)
returns void
language plpgsql
stable
set search_path = public, pg_temp
as $$
declare
    v_farmacia text;
begin
    if (p_factura is null) <> (p_orden is null) then
        raise exception 'SUSTITUCION_INCOMPLETA';
    end if;
    if p_factura is null then
        return;
    end if;
    select f.farmacia into v_farmacia from public.facturas f where f.id = p_factura;
    if not found then
        raise exception 'FACTURA_NO_ENCONTRADA:%', p_factura;
    end if;
    if v_farmacia <> p_farmacia then
        raise exception 'FARMACIA_DISTINTA_DE_LA_FACTURA:%:%', p_farmacia, v_farmacia;
    end if;
    if not exists (select 1 from public.facturas_vencimientos v where v.factura_id = p_factura and v.orden = p_orden)
    then
        raise exception 'VENCIMIENTO_NO_ENCONTRADO:%:%', p_factura, p_orden;
    end if;
end;
$$;

-- Alta comun: autor, farmacia y anulacion vacia (lo que mande la web en esas columnas se ignora).
create or replace function public.cf_cashflow_alta_concepto()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    new.autor := public.cf_cashflow_autor();
    new.farmacia := public.cf_cashflow_validar_celda(new.cuenta, new.categoria, null);
    new.creado_at := now();
    new.anulado := false;
    new.anulado_por := null;
    new.anulado_at := null;
    new.motivo_anulacion := null;
    return new;
end;
$$;

create or replace function public.cf_cashflow_alta_recurrente()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_ultimo date;
begin
    new.autor := public.cf_cashflow_autor();
    new.farmacia := public.cf_cashflow_validar_celda(new.cuenta, new.categoria, new.concepto);
    if new.importe is null or new.importe <= 0 then
        raise exception 'IMPORTE_NO_POSITIVO';
    end if;
    if new.frecuencia is null or new.frecuencia not in ('MENSUAL', 'TRIMESTRAL', 'ANUAL') then
        raise exception 'FRECUENCIA_NO_VALIDA:%', new.frecuencia;
    end if;
    if new.dia is null or new.dia not between 1 and 31 then
        raise exception 'DIA_NO_VALIDO:%', new.dia;
    end if;
    if new.inicio is null then
        raise exception 'INICIO_AUSENTE';
    end if;
    if new.fin is not null and new.fin < new.inicio then
        raise exception 'FIN_ANTERIOR_A_INICIO';
    end if;
    -- El inicio es la primera ocurrencia (DISENO §1.3): su dia es el de la recurrente (o el ultimo del mes).
    if not exists (select 1 from public.cf_cashflow_fechas_recurrente(new.frecuencia, new.dia, new.inicio, new.fin,
                                                                       new.inicio, new.inicio)) then
        raise exception 'INICIO_NO_ES_OCURRENCIA:%:%', new.inicio, new.dia;
    end if;
    -- Alguna ocurrencia futura (posterior al ultimo saldo de bancos de la cuenta).
    v_ultimo := public.cf_cashflow_referencia_futura(new.cuenta);
    if not exists (select 1 from public.cf_cashflow_fechas_recurrente(
                       new.frecuencia, new.dia, new.inicio, new.fin, v_ultimo + 1,
                       coalesce(new.fin, greatest(new.inicio, v_ultimo) + 400))) then
        raise exception 'FECHA_NO_FUTURA:%', v_ultimo;
    end if;
    new.creado_at := now();
    new.anulado := false;
    new.anulado_por := null;
    new.anulado_at := null;
    new.motivo_anulacion := null;
    return new;
end;
$$;

create or replace function public.cf_cashflow_alta_apunte()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_recurrente public.cf_cashflow_recurrentes%rowtype;
    v_ultimo date;
begin
    new.autor := public.cf_cashflow_autor();
    if new.recurrente_id is null then
        -- Apunte suelto.
        if new.fecha_ocurrencia is not null then
            raise exception 'OCURRENCIA_SIN_RECURRENTE';
        end if;
        if new.sustituido_factura_id is not null or new.sustituido_vencimiento_orden is not null then
            raise exception 'SUSTITUCION_SOLO_AL_ANULAR';
        end if;
        new.farmacia := public.cf_cashflow_validar_celda(new.cuenta, new.categoria, new.concepto);
        if new.importe is null or new.importe <= 0 then
            raise exception 'IMPORTE_NO_POSITIVO';
        end if;
        if new.fecha is null then
            raise exception 'FECHA_AUSENTE';
        end if;
        v_ultimo := public.cf_cashflow_referencia_futura(new.cuenta);
        if new.fecha <= v_ultimo then
            raise exception 'FECHA_NO_FUTURA:%', v_ultimo;
        end if;
    else
        -- Anulacion de una ocurrencia (H7B-D2): sin importe; cuenta, categoria y concepto los de la recurrente.
        if new.importe is not null then
            raise exception 'IMPORTE_EN_ANULACION_DE_OCURRENCIA';
        end if;
        select * into v_recurrente from public.cf_cashflow_recurrentes r where r.id = new.recurrente_id;
        if not found then
            raise exception 'RECURRENTE_NO_ENCONTRADA:%', new.recurrente_id;
        end if;
        if v_recurrente.anulado then
            raise exception 'RECURRENTE_ANULADA:%', new.recurrente_id;
        end if;
        new.cuenta := v_recurrente.cuenta;
        new.categoria := v_recurrente.categoria;
        new.concepto := v_recurrente.concepto;
        new.farmacia := public.cf_cashflow_validar_celda(new.cuenta, new.categoria, null);
        if new.fecha_ocurrencia is null
           or not exists (select 1 from public.cf_cashflow_fechas_recurrente(
                              v_recurrente.frecuencia, v_recurrente.dia, v_recurrente.inicio, v_recurrente.fin,
                              new.fecha_ocurrencia, new.fecha_ocurrencia)) then
            raise exception 'OCURRENCIA_NO_VALIDA:%', new.fecha_ocurrencia;
        end if;
        new.fecha := new.fecha_ocurrencia;
        v_ultimo := public.cf_cashflow_referencia_futura(new.cuenta);
        if new.fecha <= v_ultimo then
            raise exception 'FECHA_NO_FUTURA:%', v_ultimo;
        end if;
        perform public.cf_cashflow_validar_sustitucion(new.farmacia, new.sustituido_factura_id,
                                                       new.sustituido_vencimiento_orden);
    end if;
    new.creado_at := now();
    new.anulado := false;
    new.anulado_por := null;
    new.anulado_at := null;
    new.motivo_anulacion := null;
    return new;
end;
$$;

-- Solo anular (false -> true, con motivo; autor y momento los pone el trigger) y nunca borrar ni vaciar. En un apunte
-- suelto, la anulacion puede llevar la sustitucion confirmada (factura y orden del vencimiento).
create or replace function public.cf_cashflow_solo_anular()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_permitidas text[] := array['anulado', 'anulado_por', 'anulado_at', 'motivo_anulacion'];
    v_nuevo jsonb;
begin
    if tg_op in ('DELETE', 'TRUNCATE') then
        raise exception 'BORRADO_NO_PERMITIDO';
    end if;
    v_nuevo := to_jsonb(new);
    if tg_table_name = 'cf_cashflow_apuntes' and (to_jsonb(old) ->> 'recurrente_id') is null then
        v_permitidas := v_permitidas || array['sustituido_factura_id', 'sustituido_vencimiento_orden'];
    end if;
    if old.anulado or not new.anulado
       or (v_nuevo - v_permitidas) is distinct from (to_jsonb(old) - v_permitidas) then
        raise exception 'SOLO_ANULAR';
    end if;
    if btrim(coalesce(new.motivo_anulacion, '')) = '' then
        raise exception 'MOTIVO_ANULACION_AUSENTE';
    end if;
    new.anulado_por := public.cf_cashflow_autor();
    new.anulado_at := now();
    if tg_table_name = 'cf_cashflow_apuntes' then
        perform public.cf_cashflow_validar_sustitucion(old.farmacia, (v_nuevo ->> 'sustituido_factura_id')::uuid,
                                                       (v_nuevo ->> 'sustituido_vencimiento_orden')::integer);
    end if;
    return new;
end;
$$;

-- Historial: una fila por INSERT o UPDATE, con el autor que indica la web.
create or replace function public.cf_cashflow_prevision_historial()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_despues jsonb := to_jsonb(new);
begin
    insert into public.cf_cashflow_apuntes_historial (tabla, registro_id, cuenta, farmacia, operacion, antes, despues,
                                                      autor)
    values (tg_table_name, (v_despues ->> 'id')::uuid, v_despues ->> 'cuenta', v_despues ->> 'farmacia', tg_op,
            case when tg_op = 'UPDATE' then to_jsonb(old) end, v_despues, public.cf_cashflow_autor());
    return null;
end;
$$;

create or replace function public.cf_cashflow_historial_solo_insercion()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    raise exception 'cf_cashflow_apuntes_historial es solo de insercion';
end;
$$;

-- --------------------------------------------------------------------------- triggers

do $$
declare
    v_tabla text;
begin
    foreach v_tabla in array array['cf_cashflow_conceptos', 'cf_cashflow_recurrentes', 'cf_cashflow_apuntes'] loop
        execute format('drop trigger if exists %I on public.%I', v_tabla || '_alta', v_tabla);
        execute format('create trigger %I before insert on public.%I for each row execute function public.%I()',
                       v_tabla || '_alta', v_tabla,
                       case v_tabla when 'cf_cashflow_conceptos' then 'cf_cashflow_alta_concepto'
                                    when 'cf_cashflow_recurrentes' then 'cf_cashflow_alta_recurrente'
                                    else 'cf_cashflow_alta_apunte' end);
        execute format('drop trigger if exists %I on public.%I', v_tabla || '_solo_anular', v_tabla);
        execute format('create trigger %I before update or delete on public.%I '
                       'for each row execute function public.cf_cashflow_solo_anular()', v_tabla || '_solo_anular',
                       v_tabla);
        execute format('drop trigger if exists %I on public.%I', v_tabla || '_sin_truncate', v_tabla);
        execute format('create trigger %I before truncate on public.%I '
                       'for each statement execute function public.cf_cashflow_solo_anular()', v_tabla || '_sin_truncate',
                       v_tabla);
        execute format('drop trigger if exists %I on public.%I', v_tabla || '_historial', v_tabla);
        execute format('create trigger %I after insert or update on public.%I '
                       'for each row execute function public.cf_cashflow_prevision_historial()', v_tabla || '_historial',
                       v_tabla);
    end loop;
end;
$$;

drop trigger if exists cf_cashflow_apuntes_historial_bloquear_cambios on public.cf_cashflow_apuntes_historial;
create trigger cf_cashflow_apuntes_historial_bloquear_cambios before update or delete
on public.cf_cashflow_apuntes_historial
for each row execute function public.cf_cashflow_historial_solo_insercion();
drop trigger if exists cf_cashflow_apuntes_historial_bloquear_truncate on public.cf_cashflow_apuntes_historial;
create trigger cf_cashflow_apuntes_historial_bloquear_truncate before truncate on public.cf_cashflow_apuntes_historial
for each statement execute function public.cf_cashflow_historial_solo_insercion();

-- --------------------------------------------------------------------------- privilegios

-- Supabase concede por defecto privilegios sobre las tablas, secuencias y funciones nuevas de public: se retiran todos.
revoke all on table public.cf_cashflow_conceptos, public.cf_cashflow_recurrentes, public.cf_cashflow_apuntes,
    public.cf_cashflow_apuntes_historial
from public, anon, authenticated, service_role;
revoke all on sequence public.cf_cashflow_apuntes_historial_id_seq from public, anon, authenticated, service_role;
revoke all on function public.cf_cashflow_fechas_recurrente(text, integer, date, date, date, date),
    public.cf_cashflow_ocurrencias(date, date),
    public.cf_cashflow_farmacia_habilitada(text),
    public.cf_cashflow_autor(),
    public.cf_cashflow_ultimo_saldo_banco(text),
    public.cf_cashflow_validar_celda(text, text, text),
    public.cf_cashflow_referencia_futura(text),
    public.cf_cashflow_validar_sustitucion(text, uuid, integer),
    public.cf_cashflow_alta_concepto(),
    public.cf_cashflow_alta_recurrente(),
    public.cf_cashflow_alta_apunte(),
    public.cf_cashflow_solo_anular(),
    public.cf_cashflow_prevision_historial(),
    public.cf_cashflow_historial_solo_insercion()
from public, anon, authenticated, service_role;

grant usage on schema public to cf_cashflow_web;
grant select, insert on public.cf_cashflow_conceptos, public.cf_cashflow_recurrentes, public.cf_cashflow_apuntes
to cf_cashflow_web;
grant update (anulado, motivo_anulacion) on public.cf_cashflow_conceptos, public.cf_cashflow_recurrentes
to cf_cashflow_web;
grant update (anulado, motivo_anulacion, sustituido_factura_id, sustituido_vencimiento_orden)
on public.cf_cashflow_apuntes to cf_cashflow_web;
grant select on public.cf_cashflow_apuntes_historial to cf_cashflow_web;
grant execute on function public.cf_cashflow_fechas_recurrente(text, integer, date, date, date, date),
    public.cf_cashflow_ocurrencias(date, date)
to cf_cashflow_web, cf_lectura;
grant execute on function public.cf_cashflow_farmacia_habilitada(text) to cf_cashflow_web;

grant select on public.cf_cashflow_conceptos, public.cf_cashflow_recurrentes, public.cf_cashflow_apuntes,
    public.cf_cashflow_apuntes_historial
to cf_lectura;

-- --------------------------------------------------------------------------- RLS

alter table public.cf_cashflow_conceptos enable row level security;
alter table public.cf_cashflow_recurrentes enable row level security;
alter table public.cf_cashflow_apuntes enable row level security;
alter table public.cf_cashflow_apuntes_historial enable row level security;

do $$
declare
    v_tabla text;
    v_web text := 'public.cf_cashflow_farmacia_habilitada(farmacia)';
    v_lectura text := 'exists (select 1 from public.cf_modulos_farmacias m '
                      'where m.modulo = ''CASHFLOW'' and farmacia = any(m.farmacias))';
begin
    foreach v_tabla in array array['cf_cashflow_conceptos', 'cf_cashflow_recurrentes', 'cf_cashflow_apuntes',
                                   'cf_cashflow_apuntes_historial'] loop
        execute format('drop policy if exists %I on public.%I', v_tabla || '_web_select', v_tabla);
        execute format('create policy %I on public.%I for select to cf_cashflow_web using (%s)',
                       v_tabla || '_web_select', v_tabla, v_web);
        execute format('drop policy if exists %I on public.%I', v_tabla || '_lectura_select', v_tabla);
        execute format('create policy %I on public.%I for select to cf_lectura using (%s)',
                       v_tabla || '_lectura_select', v_tabla, v_lectura);
        if v_tabla <> 'cf_cashflow_apuntes_historial' then
            execute format('drop policy if exists %I on public.%I', v_tabla || '_web_insert', v_tabla);
            execute format('create policy %I on public.%I for insert to cf_cashflow_web with check (%s)',
                           v_tabla || '_web_insert', v_tabla, v_web);
            execute format('drop policy if exists %I on public.%I', v_tabla || '_web_update', v_tabla);
            execute format('create policy %I on public.%I for update to cf_cashflow_web using (%s) with check (%s)',
                           v_tabla || '_web_update', v_tabla, v_web, v_web);
        end if;
    end loop;
end;
$$;

commit;
