begin;

alter table public.facturas
    add column if not exists conciliacion_reintento_solicitado_at timestamptz;

create table if not exists public.conciliaciones (
    id uuid primary key default gen_random_uuid(),
    factura_id uuid not null references public.facturas(id) on delete cascade,
    intento integer not null check (intento > 0),
    disparador text not null
        check (disparador in ('AUTOMATICO', 'MANUAL', 'REINTENTO', 'TEST')),
    estado text not null default 'EJECUTANDO'
        check (estado in ('EJECUTANDO', 'COMPLETADA', 'ERROR')),
    es_actual boolean not null default true,
    tolerancia numeric(14,4) not null default 0.0500
        check (tolerancia >= 0),
    importe_factura numeric(14,4),
    importe_explicado numeric(14,4),
    diferencia numeric(14,4),
    resultado text
        check (resultado is null or resultado in (
            'CONCILIADA',
            'DIFERENCIA',
            'SIN_CANDIDATOS',
            'NO_EVALUABLE'
        )),
    estrategia text,
    provenance jsonb not null default '{}'::jsonb,
    worker_id text,
    iniciado_at timestamptz not null default now(),
    finalizado_at timestamptz,
    created_at timestamptz not null default now(),
    error_codigo text,
    error_detalle text,
    constraint conciliaciones_factura_intento_unico unique (factura_id, intento)
);

create unique index if not exists conciliaciones_actual_factura_unico
    on public.conciliaciones (factura_id)
    where es_actual;

create index if not exists conciliaciones_factura_idx
    on public.conciliaciones (factura_id, intento desc);

create table if not exists public.conciliacion_detalles (
    id uuid primary key default gen_random_uuid(),
    conciliacion_id uuid not null references public.conciliaciones(id) on delete cascade,
    orden integer not null check (orden > 0),
    factura_albaran_extraido_id uuid
        references public.facturas_albaranes_extraidos(id) on delete set null,
    factura_movimiento_id uuid
        references public.facturas_movimientos(id) on delete set null,
    albaran_farmacia text,
    albaran_id_contador bigint,
    numero_albaran_documental text,
    numero_albaran_farmatic text,
    coincidencia_numero_literal boolean not null default false,
    tipo_relacion text not null
        check (tipo_relacion in (
            'UNO_A_UNO',
            'UNO_A_VARIOS',
            'VARIOS_A_UNO',
            'MOVIMIENTO_NO_FARMATIC',
            'SIN_COINCIDENCIA'
        )),
    importe_documental numeric(14,4),
    importe_farmatic numeric(14,4),
    importe_aplicado numeric(14,4),
    diferencia numeric(14,4),
    estado text not null
        check (estado in ('COINCIDE', 'DIFERENCIA', 'NO_EVALUABLE')),
    provenance jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint conciliacion_detalles_orden_unico
        unique (conciliacion_id, orden),
    constraint conciliacion_detalles_origen_check
        check (
            num_nonnulls(factura_albaran_extraido_id, factura_movimiento_id) >= 1
            or tipo_relacion = 'SIN_COINCIDENCIA'
        ),
    constraint conciliacion_detalles_albaran_operacional_check
        check (
            num_nonnulls(albaran_farmacia, albaran_id_contador) in (0, 2)
        )
);

create index if not exists conciliacion_detalles_conciliacion_idx
    on public.conciliacion_detalles (conciliacion_id);

create index if not exists conciliacion_detalles_albaran_idx
    on public.conciliacion_detalles (albaran_farmacia, albaran_id_contador)
    where albaran_id_contador is not null;

create or replace function public.cf_resultado_conciliacion(
    p_diferencia numeric,
    p_tolerancia numeric default 0.0500
)
returns text
language sql
immutable
parallel safe
as $$
    select case
        when p_diferencia is null then 'NO_EVALUABLE'
        when abs(p_diferencia) <= p_tolerancia then 'CONCILIADA'
        else 'DIFERENCIA'
    end;
$$;

create or replace function public.cf_reclamar_factura_conciliacion(
    p_worker_id text,
    p_bloqueo_segundos integer default 300
)
returns setof public.facturas
language plpgsql
security definer
set search_path = public
as $$
declare
    v_id uuid;
begin
    if p_worker_id is null or btrim(p_worker_id) = '' then
        raise exception 'worker_id obligatorio';
    end if;

    select f.id
      into v_id
      from public.facturas f
      cross join public.cf_configuracion c
     where c.id = true
       and f.farmacia = any(c.farmacias_habilitadas)
       and (
           c.conciliacion_automatica
           or f.conciliacion_reintento_solicitado_at is not null
       )
       and f.estado_normalizacion = 'NORMALIZADA'
       and f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'
       and f.requiere_conciliacion_albaranes
       and coalesce(f.conciliacion_proximo_at, '-infinity'::timestamptz) <= now()
       and coalesce(f.conciliacion_bloqueado_hasta, '-infinity'::timestamptz) <= now()
     order by
       (f.conciliacion_reintento_solicitado_at is not null) desc,
       f.fecha_factura nulls last,
       f.id
     for update of f skip locked
     limit 1;

    if v_id is null then
        return;
    end if;

    return query
    update public.facturas
       set conciliacion_bloqueado_por = p_worker_id,
           conciliacion_bloqueado_hasta = now() + make_interval(secs => greatest(p_bloqueo_segundos, 1)),
           updated_at = now()
     where id = v_id
     returning *;
end;
$$;

revoke all on function public.cf_reclamar_factura_conciliacion(text, integer)
    from public, anon, authenticated;
grant execute on function public.cf_reclamar_factura_conciliacion(text, integer)
    to service_role;

comment on table public.conciliacion_detalles is
    'Referencia al albaran operacional por farmacia + id_contador; sin FK a albaranes.id.';

commit;
