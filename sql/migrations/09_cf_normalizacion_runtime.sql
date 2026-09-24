begin;

create table if not exists public.normalizacion_ejecuciones (
    id uuid primary key default gen_random_uuid(),
    documento_id uuid not null references public.documentos_facturas(id) on delete cascade,
    idempotency_key text not null,
    intento integer not null check (intento > 0),
    disparador text not null
        check (disparador in ('AUTOMATICO', 'MANUAL', 'REPROCESADO', 'TEST')),
    estado text not null default 'PENDIENTE'
        check (estado in ('PENDIENTE', 'EJECUTANDO', 'COMPLETADA', 'INCOMPLETA', 'ERROR')),
    proveedor_id uuid references public.proveedores(id),
    extractor_usado text,
    normalizador_version text,
    resultado_hash text,
    uso_ocr boolean not null default false,
    uso_luna boolean not null default false,
    luna_modelo text,
    luna_campos text[] not null default '{}'::text[],
    tokens_entrada integer check (tokens_entrada is null or tokens_entrada >= 0),
    tokens_salida integer check (tokens_salida is null or tokens_salida >= 0),
    tokens_total integer check (tokens_total is null or tokens_total >= 0),
    coste_luna numeric(12,6) check (coste_luna is null or coste_luna >= 0),
    pasos jsonb not null default '[]'::jsonb,
    resultado_json jsonb,
    worker_id text,
    iniciado_at timestamptz,
    finalizado_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    error_codigo text,
    error_detalle text,
    constraint normalizacion_ejecuciones_documento_intento_unico
        unique (documento_id, intento),
    constraint normalizacion_ejecuciones_documento_idempotency_unico
        unique (documento_id, idempotency_key)
);

drop trigger if exists normalizacion_ejecuciones_set_updated_at
    on public.normalizacion_ejecuciones;
create trigger normalizacion_ejecuciones_set_updated_at
before update on public.normalizacion_ejecuciones
for each row execute function public.cf_set_updated_at();

create index if not exists normalizacion_ejecuciones_documento_idx
    on public.normalizacion_ejecuciones (documento_id, intento desc);

create index if not exists normalizacion_ejecuciones_estado_idx
    on public.normalizacion_ejecuciones (estado, created_at);

alter table public.facturas
    drop constraint if exists facturas_normalizacion_ejecucion_fk,
    add constraint facturas_normalizacion_ejecucion_fk
        foreign key (normalizacion_ejecucion_id)
        references public.normalizacion_ejecuciones(id)
        on delete set null;

create or replace function public.cf_reclamar_documento_normalizacion(
    p_worker_id text,
    p_bloqueo_segundos integer default 300
)
returns setof public.documentos_facturas
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

    select d.id
      into v_id
      from public.documentos_facturas d
      cross join public.cf_configuracion c
     where c.id = true
       and d.farmacia = any(c.farmacias_habilitadas)
       and (
           c.normalizacion_automatica
           or d.reprocesar_solicitado_at is not null
       )
       and d.estado_lectura in ('PENDIENTE', 'ERROR')
       and coalesce(d.proximo_reintento_at, '-infinity'::timestamptz) <= now()
       and coalesce(d.bloqueado_hasta, '-infinity'::timestamptz) <= now()
     order by
       (d.reprocesar_solicitado_at is not null) desc,
       d.fecha_importacion,
       d.id
     for update of d skip locked
     limit 1;

    if v_id is null then
        return;
    end if;

    return query
    update public.documentos_facturas
       set bloqueado_por = p_worker_id,
           bloqueado_hasta = now() + make_interval(secs => greatest(p_bloqueo_segundos, 1)),
           estado_lectura = 'NORMALIZANDO',
           fecha_inicio_lectura = coalesce(fecha_inicio_lectura, now()),
           fecha_actualizacion = now()
     where id = v_id
     returning *;
end;
$$;

revoke all on function public.cf_reclamar_documento_normalizacion(text, integer)
    from public, anon, authenticated;
grant execute on function public.cf_reclamar_documento_normalizacion(text, integer)
    to service_role;

comment on function public.cf_reclamar_documento_normalizacion(text, integer) is
    'Claim atomico. Con configuracion inicial false no reclama documentos existentes salvo solicitud manual.';

commit;
