begin;

alter table public.normalizacion_ejecuciones
    drop constraint if exists normalizacion_ejecuciones_disparador_check;
alter table public.normalizacion_ejecuciones
    add constraint normalizacion_ejecuciones_disparador_check
    check (disparador in (
        'AUTOMATICO', 'MANUAL', 'MANUAL_ONE_SHOT', 'REPROCESADO', 'TEST'
    ));

-- Un solo nucleo conserva filtros, ordering, locks y expiracion para ambas rutas.
create or replace function public.cf_reclamar_documento_normalizacion_nucleo(
    p_worker_id text,
    p_bloqueo_segundos integer,
    p_modo_ejecucion text
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
    if p_modo_ejecucion not in ('AUTOMATICO', 'MANUAL_ONE_SHOT') then
        raise exception 'MODO_EJECUCION_NO_ADMITIDO';
    end if;

    select d.id
      into v_id
      from public.documentos_facturas d
      cross join public.cf_configuracion c
     where c.id = true
       and d.farmacia = any(c.farmacias_habilitadas)
       -- MANUAL_ONE_SHOT salta solo el interruptor global. El resto es comun.
       and (
           p_modo_ejecucion = 'MANUAL_ONE_SHOT'
           or c.normalizacion_automatica
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
           bloqueado_hasta = now() + make_interval(
               secs => greatest(p_bloqueo_segundos, 1)
           ),
           estado_lectura = 'NORMALIZANDO',
           fecha_inicio_lectura = coalesce(fecha_inicio_lectura, now()),
           fecha_actualizacion = now()
     where id = v_id
     returning *;

    insert into public.historial_facturas
        (documento_id, evento, origen, actor, estado_nuevo, detalle)
    values (
        v_id,
        'NORMALIZACION_CLAIM',
        'RPC',
        p_worker_id,
        jsonb_build_object('estado_lectura', 'NORMALIZANDO'),
        jsonb_build_object('modo_ejecucion', p_modo_ejecucion)
    );
end;
$$;

create or replace function public.cf_reclamar_documento_normalizacion(
    p_worker_id text,
    p_bloqueo_segundos integer default 300
)
returns setof public.documentos_facturas
language sql
security definer
set search_path = public
as $$
    select *
      from public.cf_reclamar_documento_normalizacion_nucleo(
          p_worker_id, p_bloqueo_segundos, 'AUTOMATICO'
      );
$$;

create or replace function public.cf_reclamar_documento_normalizacion_manual_one_shot(
    p_worker_id text,
    p_bloqueo_segundos integer default 300
)
returns setof public.documentos_facturas
language sql
security definer
set search_path = public
as $$
    select *
      from public.cf_reclamar_documento_normalizacion_nucleo(
          p_worker_id, p_bloqueo_segundos, 'MANUAL_ONE_SHOT'
      );
$$;

-- Envoltorio transaccional: reutiliza la RPC multifactura certificada y deja
-- el disparador exacto en la ejecucion, sin duplicar la logica economica.
create or replace function public.cf_persistir_documento_multifactura(
    p_documento_id uuid,
    p_worker_id text,
    p_idempotency_key text,
    p_resultado_hash text,
    p_resultado jsonb,
    p_segmentos_autorizados text[],
    p_disparador text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_ejecucion uuid;
begin
    if p_disparador not in ('AUTOMATICO', 'REPROCESADO', 'MANUAL_ONE_SHOT') then
        raise exception 'DISPARADOR_MULTIFACTURA_NO_ADMITIDO';
    end if;

    v_ejecucion := public.cf_persistir_documento_multifactura(
        p_documento_id,
        p_worker_id,
        p_idempotency_key,
        p_resultado_hash,
        p_resultado,
        p_segmentos_autorizados
    );

    update public.normalizacion_ejecuciones
       set disparador = p_disparador,
           resultado_json = coalesce(resultado_json, '{}'::jsonb)
               || jsonb_build_object(
                   'provenance_ejecucion',
                   jsonb_build_object('modo_ejecucion', p_disparador)
               )
     where id = v_ejecucion;
    return v_ejecucion;
end;
$$;

revoke all on function public.cf_reclamar_documento_normalizacion_nucleo(text, integer, text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_reclamar_documento_normalizacion(text, integer)
    from public, anon, authenticated;
revoke all on function public.cf_reclamar_documento_normalizacion_manual_one_shot(text, integer)
    from public, anon, authenticated;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[])
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated;

grant execute on function public.cf_reclamar_documento_normalizacion(text, integer)
    to service_role;
grant execute on function public.cf_reclamar_documento_normalizacion_manual_one_shot(text, integer)
    to service_role;
grant execute on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    to service_role;

comment on function public.cf_reclamar_documento_normalizacion_manual_one_shot(text, integer) is
    'Claim manual de un unico candidato. Salta solo normalizacion_automatica y no admite preseleccion.';

commit;
