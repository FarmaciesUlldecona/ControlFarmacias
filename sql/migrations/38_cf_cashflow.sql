-- Migracion 38 (Hito H7): importacion del Excel de cashflow de Pio (solo lectura para la web). Diseno:
-- pruebas/auditoria_h7/DISENO.md, con las DECISIONES DE PIO C1-C8 (2026-11-17), E1-E7 (2026-11-18), las dos propuestas
-- de redondeo aprobadas (2026-11-18) y las respuestas del 2026-11-22 (saldos sin margen; categorias nuevas en el
-- script de importacion, hito 38-B).
-- - Permiso por modulo (C4): cf_modulos_farmacias admite tambien CASHFLOW = {PIO, RITA}. cf_configuracion no cambia:
--   facturas, albaranes, normalizacion y conciliacion siguen solo PIO. RITA entra SOLO con sus datos bancarios.
-- - Tablas: cf_cashflow_cuentas (fija, PIO/RITA/SL), cf_cashflow_importaciones, cf_cashflow_importes y
--   cf_cashflow_saldos. Solo insercion: UPDATE (SOLO_INSERCION), DELETE y TRUNCATE (BORRADO_NO_PERMITIDO) se rechazan
--   por trigger; la unica excepcion es el cambio de vigente que hace la RPC (variable de transaccion
--   cf.cashflow_vigente, que solo pone la RPC). Una sola importacion vigente (unico parcial); el hash no se repite.
-- - Escritura: SOLO la RPC cf_cashflow_registrar_importacion(p_importacion, p_importes, p_saldos), security definer.
--   Valida de nuevo en la BD (falla cerrado aunque el script falle): cabecera, claves admitidas, cuentas, decenas
--   (dias 1, 11 y 21; fin el 10, el 20 o el ultimo del mes), categoria RE/RS, importe distinto de 0 y al centimo,
--   saldos al centimo, filas = numero de importes, hash nuevo, cada decena con importes tiene saldo (E5: la decena sin
--   saldo no lleva importes) y el cuadre (E1): saldo inicial + suma RE - suma RS = saldo segun formulas, con margen de
--   0,005 por importe redondeado de esa cuenta y decena (propuesta aprobada; el campo redondeado no se guarda) y SIN
--   margen por saldo redondeado (decision de Pio, 2026-11-22). El importe conserva el signo de la celda. OK -> la nueva
--   pasa a vigente y la anterior deja de serlo; ERROR -> solo la cabecera, sin importes ni saldos, nunca vigente.
--   Toda la importacion entra o no entra nada.
-- - Lectura: cf_lectura (lista cerrada ampliada con las cuatro tablas, decision de Pio), RLS con la regla de la 31 sin
--   funciones security definer (2BN): farmacia null (SL) o farmacia del modulo CASHFLOW. Ningun rol de la web.
-- - AUTORIZACION EXPRESA DE PIO (C3, 2026-11-17; reconfirmada el 2026-11-19): esta migracion y su rollback son los
--   UNICOS ficheros que nombran el rol del sistema: se le quitan los privilegios por defecto de Supabase sobre lo nuevo
--   y recibe EXECUTE solo sobre la RPC. Nada para anon, authenticated ni PUBLIC.
-- Ningun dato existente cambia, salvo la fila CASHFLOW de cf_modulos_farmacias. Idempotente. Requiere la 37.
begin;

do $$
begin
    if to_regprocedure('public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text,jsonb)') is null
    then
        raise exception 'MIGRACION_37_AUSENTE';
    end if;
end;
$$;

-- --------------------------------------------------------------------------- permiso por modulo (C4)

alter table public.cf_modulos_farmacias drop constraint if exists cf_modulos_farmacias_modulo_check;
alter table public.cf_modulos_farmacias add constraint cf_modulos_farmacias_modulo_check
    check (modulo in ('TRABAJADORES', 'CASHFLOW'));
insert into public.cf_modulos_farmacias (modulo, farmacias)
values ('CASHFLOW', array['PIO', 'RITA']::text[])
on conflict (modulo) do nothing;

-- --------------------------------------------------------------------------- tablas

create table if not exists public.cf_cashflow_cuentas (
    codigo text primary key check (codigo in ('PIO', 'RITA', 'SL')),
    farmacia text check (farmacia in ('PIO', 'RITA')),
    hoja text not null,
    constraint cf_cashflow_cuentas_fija check (
        (codigo = 'PIO' and farmacia = 'PIO' and hoja = U&'P\00CDO')
        or (codigo = 'RITA' and farmacia = 'RITA' and hoja = 'RITA')
        or (codigo = 'SL' and farmacia is null and hoja = 'SL'))
);
comment on table public.cf_cashflow_cuentas is
    'Cuentas bancarias del Excel de cashflow (H7): PIO, RITA y SL (sin farmacia). Fija: la carga la migracion 38.';
insert into public.cf_cashflow_cuentas (codigo, farmacia, hoja)
values ('PIO', 'PIO', U&'P\00CDO'), ('RITA', 'RITA', 'RITA'), ('SL', null, 'SL')
on conflict (codigo) do nothing;

create table if not exists public.cf_cashflow_importaciones (
    id uuid primary key default gen_random_uuid(),
    archivo_nombre text not null check (char_length(archivo_nombre) between 1 and 255
                                        and archivo_nombre !~ '[/\\]'),
    archivo_hash text not null check (archivo_hash ~ '^[0-9a-f]{64}$'),
    origen text not null check (origen in ('NOCHE', 'MANUAL')),
    estado text not null check (estado in ('OK', 'ERROR')),
    detalle_error text,
    filas integer not null check (filas >= 0),
    importado_at timestamptz not null default now(),
    vigente boolean not null default false,
    constraint cf_cashflow_importaciones_estado check (
        (estado = 'OK' and detalle_error is null)
        or (estado = 'ERROR' and char_length(btrim(coalesce(detalle_error, ''))) > 0 and filas = 0 and not vigente))
);
create unique index if not exists cf_cashflow_importaciones_vigente
    on public.cf_cashflow_importaciones (vigente) where vigente;
create unique index if not exists cf_cashflow_importaciones_hash
    on public.cf_cashflow_importaciones (archivo_hash);
comment on table public.cf_cashflow_importaciones is
    'Importaciones del Excel de cashflow (H7), OK o ERROR; una sola vigente. Solo insercion: solo la RPC '
    'cf_cashflow_registrar_importacion escribe y solo ella cambia vigente.';

create table if not exists public.cf_cashflow_importes (
    id bigint generated always as identity primary key,
    importacion_id uuid not null references public.cf_cashflow_importaciones (id),
    cuenta text not null references public.cf_cashflow_cuentas (codigo),
    farmacia text,
    decena_inicio date not null,
    decena_fin date not null,
    categoria text not null check (categoria ~ '^R[ES] '),
    concepto text,
    importe numeric(14,2) not null check (importe <> 0),
    fila_excel integer not null check (fila_excel > 0),
    constraint cf_cashflow_importes_decena check (decena_fin >= decena_inicio),
    constraint cf_cashflow_importes_farmacia check (
        (cuenta = 'PIO' and farmacia = 'PIO') or (cuenta = 'RITA' and farmacia = 'RITA')
        or (cuenta = 'SL' and farmacia is null))
);
create index if not exists cf_cashflow_importes_importacion_idx
    on public.cf_cashflow_importes (importacion_id, cuenta, decena_inicio);
comment on table public.cf_cashflow_importes is
    'Importes por categoria y decena de una importacion de cashflow (H7), con el signo de la celda: un RS positivo es '
    'una salida (E1). Solo insercion.';

create table if not exists public.cf_cashflow_saldos (
    id bigint generated always as identity primary key,
    importacion_id uuid not null references public.cf_cashflow_importaciones (id),
    cuenta text not null references public.cf_cashflow_cuentas (codigo),
    farmacia text,
    decena_inicio date not null,
    saldo_inicial numeric(14,2) not null,
    saldo_formulas numeric(14,2) not null,
    saldo_bancos numeric(14,2),
    constraint cf_cashflow_saldos_unico unique (importacion_id, cuenta, decena_inicio),
    constraint cf_cashflow_saldos_farmacia check (
        (cuenta = 'PIO' and farmacia = 'PIO') or (cuenta = 'RITA' and farmacia = 'RITA')
        or (cuenta = 'SL' and farmacia is null))
);
comment on table public.cf_cashflow_saldos is
    'Saldos por cuenta y decena de una importacion de cashflow (H7): inicial, segun formulas y segun bancos (null si la '
    'decena no esta cuadrada; distinto del de formulas nunca es error, E7). Solo insercion.';

-- --------------------------------------------------------------------------- solo insercion

-- UPDATE, DELETE y TRUNCATE rechazados. Excepcion: el cambio de vigente (solo esa columna) en importaciones, dentro de
-- la RPC (cf.cashflow_vigente = on) y nunca vigente sin OK.
create or replace function public.cf_cashflow_solo_insercion()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    if tg_op in ('DELETE', 'TRUNCATE') then
        raise exception 'BORRADO_NO_PERMITIDO';
    end if;
    -- plpgsql no garantiza el cortocircuito: la tabla se comprueba antes de leer sus columnas.
    if tg_table_name = 'cf_cashflow_importaciones'
       and coalesce(current_setting('cf.cashflow_vigente', true), '') = 'on' then
        if (to_jsonb(new) - 'vigente') = (to_jsonb(old) - 'vigente')
           and (to_jsonb(new) ->> 'vigente') is distinct from (to_jsonb(old) ->> 'vigente')
           and ((to_jsonb(new) ->> 'vigente') = 'false' or (to_jsonb(new) ->> 'estado') = 'OK') then
            return new;
        end if;
    end if;
    raise exception 'SOLO_INSERCION';
end;
$$;

do $$
declare
    v_tabla text;
begin
    foreach v_tabla in array array['cf_cashflow_cuentas', 'cf_cashflow_importaciones', 'cf_cashflow_importes',
                                   'cf_cashflow_saldos'] loop
        execute format('drop trigger if exists %I on public.%I', v_tabla || '_solo_insercion', v_tabla);
        execute format('create trigger %I before update or delete on public.%I '
                       'for each row execute function public.cf_cashflow_solo_insercion()',
                       v_tabla || '_solo_insercion', v_tabla);
        execute format('drop trigger if exists %I on public.%I', v_tabla || '_sin_truncate', v_tabla);
        execute format('create trigger %I before truncate on public.%I '
                       'for each statement execute function public.cf_cashflow_solo_insercion()',
                       v_tabla || '_sin_truncate', v_tabla);
    end loop;
end;
$$;

-- --------------------------------------------------------------------------- RPC de escritura

create or replace function public.cf_cashflow_registrar_importacion(p_importacion jsonb, p_importes jsonb,
                                                                    p_saldos jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_id uuid;
    v_anterior uuid;
    v_estado text;
    v_filas integer;
    v_importes integer;
    v_saldos integer;
    v_fallo text;
begin
    -- Una importacion cada vez.
    perform pg_advisory_xact_lock(hashtext('cf_cashflow_registrar_importacion'));

    -- Cabecera.
    if jsonb_typeof(p_importacion) is distinct from 'object' then
        raise exception 'IMPORTACION_NO_VALIDA';
    end if;
    if exists (select 1 from jsonb_object_keys(p_importacion) k
               where k <> all(array['archivo_nombre', 'archivo_hash', 'origen', 'estado', 'detalle_error', 'filas']))
    then
        raise exception 'CLAVE_NO_ADMITIDA:importacion';
    end if;
    if jsonb_typeof(p_importes) is distinct from 'array' or jsonb_typeof(p_saldos) is distinct from 'array' then
        raise exception 'IMPORTES_O_SALDOS_NO_VALIDOS';
    end if;
    if exists (select 1 from jsonb_array_elements(p_importes) e where jsonb_typeof(e) <> 'object')
       or exists (select 1 from jsonb_array_elements(p_saldos) e where jsonb_typeof(e) <> 'object') then
        raise exception 'IMPORTES_O_SALDOS_NO_VALIDOS';
    end if;
    if exists (select 1 from jsonb_array_elements(p_importes) e cross join lateral jsonb_object_keys(e) k
               where k <> all(array['cuenta', 'decena_inicio', 'decena_fin', 'categoria', 'concepto', 'importe',
                                    'fila_excel', 'redondeado'])) then
        raise exception 'CLAVE_NO_ADMITIDA:importes';
    end if;
    if exists (select 1 from jsonb_array_elements(p_saldos) e cross join lateral jsonb_object_keys(e) k
               where k <> all(array['cuenta', 'decena_inicio', 'saldo_inicial', 'saldo_formulas', 'saldo_bancos']))
    then
        raise exception 'CLAVE_NO_ADMITIDA:saldos';
    end if;

    v_estado := p_importacion ->> 'estado';
    v_filas := (p_importacion ->> 'filas')::integer;
    if exists (select 1 from public.cf_cashflow_importaciones where archivo_hash = p_importacion ->> 'archivo_hash')
    then
        raise exception 'HASH_YA_IMPORTADO';
    end if;
    if v_estado = 'ERROR' and (jsonb_array_length(p_importes) > 0 or jsonb_array_length(p_saldos) > 0) then
        raise exception 'ERROR_CON_DATOS';
    end if;
    if v_estado = 'OK' and (coalesce(v_filas, -1) <> jsonb_array_length(p_importes)) then
        raise exception 'FILAS_NO_COINCIDEN:%:%', v_filas, jsonb_array_length(p_importes);
    end if;
    if v_estado = 'OK' and (jsonb_array_length(p_importes) = 0 or jsonb_array_length(p_saldos) = 0) then
        raise exception 'IMPORTACION_OK_VACIA';
    end if;

    -- Los checks de la tabla validan nombre, hash, origen, estado, detalle y filas.
    insert into public.cf_cashflow_importaciones (archivo_nombre, archivo_hash, origen, estado, detalle_error, filas)
    values (p_importacion ->> 'archivo_nombre', p_importacion ->> 'archivo_hash', p_importacion ->> 'origen',
            v_estado, p_importacion ->> 'detalle_error', v_filas)
    returning id into v_id;

    if v_estado = 'ERROR' then
        return jsonb_build_object('importacion_id', v_id, 'estado', v_estado, 'vigente', false, 'importes', 0,
                                  'saldos', 0);
    end if;

    -- Datos en tablas temporales tipadas (al terminar la transaccion desaparecen).
    create temporary table if not exists pg_temp.cf_cashflow_tmp_importes (
        cuenta text, decena_inicio date, decena_fin date, categoria text, concepto text, importe numeric,
        fila_excel integer, redondeado boolean) on commit drop;
    create temporary table if not exists pg_temp.cf_cashflow_tmp_saldos (
        cuenta text, decena_inicio date, saldo_inicial numeric, saldo_formulas numeric, saldo_bancos numeric)
        on commit drop;
    truncate pg_temp.cf_cashflow_tmp_importes, pg_temp.cf_cashflow_tmp_saldos;
    insert into pg_temp.cf_cashflow_tmp_importes
    select * from jsonb_to_recordset(p_importes) as x(cuenta text, decena_inicio date, decena_fin date,
                                                    categoria text, concepto text, importe numeric,
                                                    fila_excel integer, redondeado boolean);
    insert into pg_temp.cf_cashflow_tmp_saldos
    select * from jsonb_to_recordset(p_saldos) as x(cuenta text, decena_inicio date, saldo_inicial numeric,
                                                  saldo_formulas numeric, saldo_bancos numeric);

    select case
        when exists (select 1 from pg_temp.cf_cashflow_tmp_importes i
                     where i.cuenta is null or i.decena_inicio is null or i.decena_fin is null
                        or i.categoria is null or i.importe is null or i.fila_excel is null) then 'IMPORTE_INCOMPLETO'
        when exists (select 1 from pg_temp.cf_cashflow_tmp_saldos s
                     where s.cuenta is null or s.decena_inicio is null or s.saldo_inicial is null
                        or s.saldo_formulas is null) then 'SALDO_INCOMPLETO'
        when exists (select 1 from (select cuenta from pg_temp.cf_cashflow_tmp_importes
                                    union select cuenta from pg_temp.cf_cashflow_tmp_saldos) c
                     where c.cuenta not in (select codigo from public.cf_cashflow_cuentas)) then 'CUENTA_DESCONOCIDA'
        when exists (select 1 from (select decena_inicio, decena_fin from pg_temp.cf_cashflow_tmp_importes
                                    union all select decena_inicio, null from pg_temp.cf_cashflow_tmp_saldos) d
                     where extract(day from d.decena_inicio) not in (1, 11, 21)
                        or (d.decena_fin is not null and d.decena_fin <> case extract(day from d.decena_inicio)
                                when 1 then d.decena_inicio + 9
                                when 11 then d.decena_inicio + 9
                                else (date_trunc('month', d.decena_inicio) + interval '1 month - 1 day')::date
                            end)) then 'DECENA_NO_VALIDA'
        when exists (select 1 from pg_temp.cf_cashflow_tmp_importes where categoria !~ '^R[ES] ') then 'CATEGORIA_SIN_PREFIJO'
        when exists (select 1 from pg_temp.cf_cashflow_tmp_importes where importe = 0) then 'IMPORTE_CERO'
        when exists (select 1 from pg_temp.cf_cashflow_tmp_importes where importe <> round(importe, 2))
            then 'IMPORTE_CON_MAS_DE_2_DECIMALES'
        when exists (select 1 from pg_temp.cf_cashflow_tmp_saldos
                     where saldo_inicial <> round(saldo_inicial, 2) or saldo_formulas <> round(saldo_formulas, 2)
                        or saldo_bancos <> round(saldo_bancos, 2)) then 'SALDO_CON_MAS_DE_2_DECIMALES'
        when exists (select 1 from pg_temp.cf_cashflow_tmp_saldos group by cuenta, decena_inicio having count(*) > 1)
            then 'SALDO_REPETIDO'
        when exists (select 1 from pg_temp.cf_cashflow_tmp_importes i
                     where not exists (select 1 from pg_temp.cf_cashflow_tmp_saldos s
                                       where s.cuenta = i.cuenta and s.decena_inicio = i.decena_inicio))
            then 'IMPORTES_SIN_SALDO'
        when exists (
            select 1 from pg_temp.cf_cashflow_tmp_saldos s
            left join lateral (
                select coalesce(sum(case when i.categoria like 'RE %' then i.importe else -i.importe end), 0) as neto,
                       count(*) filter (where coalesce(i.redondeado, false)) as redondeados
                from pg_temp.cf_cashflow_tmp_importes i
                where i.cuenta = s.cuenta and i.decena_inicio = s.decena_inicio) t on true
            where abs(s.saldo_inicial + t.neto - s.saldo_formulas) > 0.005 * t.redondeados)
            then 'CUADRE_NO_VALIDO'
    end into v_fallo;
    if v_fallo is not null then
        raise exception '%', v_fallo;
    end if;

    insert into public.cf_cashflow_importes (importacion_id, cuenta, farmacia, decena_inicio, decena_fin, categoria,
                                             concepto, importe, fila_excel)
    select v_id, i.cuenta, c.farmacia, i.decena_inicio, i.decena_fin, i.categoria, i.concepto, i.importe, i.fila_excel
    from pg_temp.cf_cashflow_tmp_importes i join public.cf_cashflow_cuentas c on c.codigo = i.cuenta;
    get diagnostics v_importes = row_count;
    insert into public.cf_cashflow_saldos (importacion_id, cuenta, farmacia, decena_inicio, saldo_inicial,
                                           saldo_formulas, saldo_bancos)
    select v_id, s.cuenta, c.farmacia, s.decena_inicio, s.saldo_inicial, s.saldo_formulas, s.saldo_bancos
    from pg_temp.cf_cashflow_tmp_saldos s join public.cf_cashflow_cuentas c on c.codigo = s.cuenta;
    get diagnostics v_saldos = row_count;
    if v_importes <> v_filas then
        raise exception 'FILAS_NO_COINCIDEN:%:%', v_filas, v_importes;
    end if;

    -- Vigente: la nueva sustituye a la anterior (unica excepcion al solo insercion).
    perform set_config('cf.cashflow_vigente', 'on', true);
    update public.cf_cashflow_importaciones set vigente = false where vigente returning id into v_anterior;
    update public.cf_cashflow_importaciones set vigente = true where id = v_id;
    perform set_config('cf.cashflow_vigente', 'off', true);

    return jsonb_build_object('importacion_id', v_id, 'estado', v_estado, 'vigente', true, 'importes', v_importes,
                              'saldos', v_saldos, 'anterior', v_anterior);
end;
$$;

-- --------------------------------------------------------------------------- privilegios

-- Supabase concede por defecto privilegios sobre las tablas, secuencias y funciones nuevas de public: se retiran todos.
revoke all on table public.cf_cashflow_cuentas, public.cf_cashflow_importaciones, public.cf_cashflow_importes,
    public.cf_cashflow_saldos
from public, anon, authenticated, service_role;
revoke all on sequence public.cf_cashflow_importes_id_seq, public.cf_cashflow_saldos_id_seq
from public, anon, authenticated, service_role;
revoke all on function public.cf_cashflow_solo_insercion() from public, anon, authenticated, service_role;
revoke all on function public.cf_cashflow_registrar_importacion(jsonb, jsonb, jsonb)
from public, anon, authenticated, service_role;
-- La RPC es lo unico que el sistema puede usar de Cashflow (C3).
grant execute on function public.cf_cashflow_registrar_importacion(jsonb, jsonb, jsonb) to service_role;

grant select on public.cf_cashflow_cuentas, public.cf_cashflow_importaciones, public.cf_cashflow_importes,
    public.cf_cashflow_saldos
to cf_lectura;

-- --------------------------------------------------------------------------- RLS

alter table public.cf_cashflow_cuentas enable row level security;
alter table public.cf_cashflow_importaciones enable row level security;
alter table public.cf_cashflow_importes enable row level security;
alter table public.cf_cashflow_saldos enable row level security;

drop policy if exists cf_cashflow_importaciones_lectura_select on public.cf_cashflow_importaciones;
create policy cf_cashflow_importaciones_lectura_select on public.cf_cashflow_importaciones
    for select to cf_lectura using (true);

do $$
declare
    v_tabla text;
    v_regla text := '(farmacia is null or exists (select 1 from public.cf_modulos_farmacias m '
                    'where m.modulo = ''CASHFLOW'' and farmacia = any(m.farmacias)))';
begin
    foreach v_tabla in array array['cf_cashflow_cuentas', 'cf_cashflow_importes', 'cf_cashflow_saldos'] loop
        execute format('drop policy if exists %I on public.%I', v_tabla || '_lectura_select', v_tabla);
        execute format('create policy %I on public.%I for select to cf_lectura using %s',
                       v_tabla || '_lectura_select', v_tabla, v_regla);
    end loop;
end;
$$;

commit;
