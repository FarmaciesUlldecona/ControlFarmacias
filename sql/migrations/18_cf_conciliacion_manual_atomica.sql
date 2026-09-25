-- Migracion 18 (Hito 2AV): ruta manual one-shot de conciliacion (R5), cierre
-- atomico con clave idempotente y replay (R6), fallos con backoff y revision
-- (R7) y provenance MANUAL_ONE_SHOT/AUTOMATICO (R8). R9 es solo Python.
-- Selector y ordering de conciliacion IDENTICOS a la migracion 14; el unico
-- cambio es que MANUAL_ONE_SHOT omite el interruptor conciliacion_automatica.
-- Idempotente. Sin DML sobre datos existentes salvo defaults de columnas nuevas.
begin;

-- R7: estado de revision no reclamable, contador y clase del ultimo fallo.
alter table public.facturas
    drop constraint if exists facturas_estado_conciliacion_cf_check;
alter table public.facturas
    add constraint facturas_estado_conciliacion_cf_check
    check (estado_conciliacion_cf in (
        'PENDIENTE_CONCILIAR',
        'CONCILIADA',
        'REVISION_CONCILIACION'
    ));

alter table public.facturas
    add column if not exists conciliacion_intentos_fallo integer not null default 0,
    add column if not exists conciliacion_ultima_clase_fallo text;
alter table public.facturas
    drop constraint if exists facturas_conciliacion_intentos_fallo_check,
    drop constraint if exists facturas_conciliacion_ultima_clase_fallo_check;
alter table public.facturas
    add constraint facturas_conciliacion_intentos_fallo_check
        check (conciliacion_intentos_fallo >= 0),
    add constraint facturas_conciliacion_ultima_clase_fallo_check
        check (conciliacion_ultima_clase_fallo is null or conciliacion_ultima_clase_fallo in
            ('DEFECTO_DOCUMENTO', 'TRANSITORIO'));

alter table public.cf_configuracion
    add column if not exists conciliacion_max_intentos integer not null default 4,
    add column if not exists conciliacion_backoff interval[] not null
        default array[interval '1 hour', interval '6 hours', interval '24 hours'];
alter table public.cf_configuracion
    drop constraint if exists cf_configuracion_reintentos_conciliacion_check;
alter table public.cf_configuracion
    add constraint cf_configuracion_reintentos_conciliacion_check check (
        conciliacion_max_intentos between 1 and 20
        and cardinality(conciliacion_backoff) >= 1
        and cardinality(conciliacion_backoff) >= conciliacion_max_intentos - 1
        and interval '0' < all(conciliacion_backoff)
    );

-- R6/R8: clave idempotente y disparador MANUAL_ONE_SHOT.
alter table public.conciliaciones
    add column if not exists idempotency_key text;
create unique index if not exists conciliaciones_factura_idempotency_unico
    on public.conciliaciones (factura_id, idempotency_key)
    where idempotency_key is not null;
alter table public.conciliaciones
    drop constraint if exists conciliaciones_disparador_check;
alter table public.conciliaciones
    add constraint conciliaciones_disparador_check
    check (disparador in ('AUTOMATICO', 'MANUAL', 'MANUAL_ONE_SHOT', 'REINTENTO', 'TEST'));

-- R5: un solo nucleo conserva filtros, ordering, lock y expiracion (copiados de
-- la migracion 14) para ambas rutas.
create or replace function public.cf_reclamar_factura_conciliacion_nucleo(
    p_worker_id text,
    p_bloqueo_segundos integer,
    p_modo_ejecucion text
)
returns setof public.facturas
language plpgsql
security definer
set search_path = public
as $$
declare
    v_id uuid;
    v_documento uuid;
begin
    if p_worker_id is null or btrim(p_worker_id) = '' then
        raise exception 'worker_id obligatorio';
    end if;
    if p_modo_ejecucion is null or p_modo_ejecucion not in ('AUTOMATICO', 'MANUAL_ONE_SHOT') then
        raise exception 'MODO_EJECUCION_NO_ADMITIDO';
    end if;

    select f.id
      into v_id
      from public.facturas f
      cross join public.cf_configuracion c
      cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e
     where c.id = true
       and f.farmacia = any(c.farmacias_habilitadas)
       -- MANUAL_ONE_SHOT salta solo el interruptor global. El resto es comun.
       and (
           p_modo_ejecucion = 'MANUAL_ONE_SHOT'
           or c.conciliacion_automatica
           or f.conciliacion_reintento_solicitado_at is not null
       )
       and f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'
       and e.estado = 'APTA'
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

    select documento_id into v_documento from public.facturas where id = v_id;
    insert into public.historial_facturas
        (documento_id, factura_id, evento, origen, actor, estado_nuevo, detalle)
    values (
        v_documento, v_id, 'CONCILIACION_CLAIM', 'RPC', p_worker_id,
        jsonb_build_object('conciliacion_bloqueado_por', p_worker_id),
        jsonb_build_object('modo_ejecucion', p_modo_ejecucion)
    );
end;
$$;

create or replace function public.cf_reclamar_factura_conciliacion(
    p_worker_id text,
    p_bloqueo_segundos integer default 300
)
returns setof public.facturas
language sql
security definer
set search_path = public
as $$
    select *
      from public.cf_reclamar_factura_conciliacion_nucleo(
          p_worker_id, p_bloqueo_segundos, 'AUTOMATICO'
      );
$$;

create or replace function public.cf_reclamar_factura_conciliacion_manual_one_shot(
    p_worker_id text,
    p_bloqueo_segundos integer default 300
)
returns setof public.facturas
language sql
security definer
set search_path = public
as $$
    select *
      from public.cf_reclamar_factura_conciliacion_nucleo(
          p_worker_id, p_bloqueo_segundos, 'MANUAL_ONE_SHOT'
      );
$$;

-- R6: cierre atomico. Una sola transaccion: cabecera, detalles, es_actual,
-- estado de la factura, liberacion del lock e historial. Replay idempotente.
create or replace function public.cf_persistir_conciliacion(
    p_factura_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_resultado jsonb
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    f public.facturas%rowtype;
    v_existente public.conciliaciones%rowtype;
    v_modo_claim text;
    v_intento integer;
    v_id uuid;
    v_estado text;
    v_resultado text := p_resultado->>'resultado';
    v_liberado boolean := false;
begin
    if p_disparador is null or p_disparador not in ('AUTOMATICO', 'MANUAL_ONE_SHOT') then
        raise exception 'DISPARADOR_CONCILIACION_NO_ADMITIDO';
    end if;
    if nullif(btrim(p_worker_id), '') is null or nullif(btrim(p_idempotency_key), '') is null then
        raise exception 'worker_id e idempotency_key obligatorios';
    end if;
    if v_resultado is null or v_resultado not in ('CONCILIADA', 'DIFERENCIA', 'SIN_CANDIDATOS', 'NO_EVALUABLE') then
        raise exception 'RESULTADO_CONCILIACION_NO_ADMITIDO';
    end if;
    if jsonb_typeof(coalesce(p_resultado->'detalles', '[]'::jsonb)) <> 'array' then
        raise exception 'DETALLES_CONCILIACION_INVALIDOS';
    end if;

    select * into f from public.facturas where id = p_factura_id for update;
    if f.id is null then
        raise exception 'factura no encontrada';
    end if;

    select * into v_existente
      from public.conciliaciones
     where factura_id = p_factura_id and idempotency_key = p_idempotency_key;

    if v_existente.id is not null then
        -- Replay: nunca duplica; libera el claim del llamante y restaura el estado.
        v_estado := f.estado_conciliacion_cf;
        if f.conciliacion_bloqueado_por is not null and f.conciliacion_bloqueado_por = p_worker_id then
            v_estado := case when v_existente.resultado = 'CONCILIADA'
                             then 'CONCILIADA' else 'PENDIENTE_CONCILIAR' end;
            update public.facturas
               set estado_conciliacion_cf = v_estado,
                   conciliacion_bloqueado_por = null,
                   conciliacion_bloqueado_hasta = null,
                   conciliacion_reintento_solicitado_at = null,
                   updated_at = now()
             where id = f.id;
            v_liberado := true;
        end if;
        insert into public.historial_facturas
            (documento_id, factura_id, evento, origen, actor, estado_nuevo, detalle)
        values (
            f.documento_id, f.id, 'CONCILIACION_REPLAY_IDEMPOTENTE', 'RPC', p_worker_id,
            jsonb_build_object('estado_conciliacion_cf', v_estado),
            jsonb_build_object('conciliacion_id', v_existente.id, 'claim_liberado', v_liberado,
                               'disparador', p_disparador)
        );
        return v_existente.id;
    end if;

    if f.conciliacion_bloqueado_por is distinct from p_worker_id then
        raise exception 'claim no pertenece al worker';
    end if;
    if not exists (
        select 1 from public.cf_configuracion c
         where c.id = true and f.farmacia = any(c.farmacias_habilitadas)
    ) then
        raise exception 'FARMACIA_NO_HABILITADA';
    end if;
    select h.detalle->>'modo_ejecucion' into v_modo_claim
      from public.historial_facturas h
     where h.factura_id = f.id and h.evento = 'CONCILIACION_CLAIM' and h.actor = p_worker_id
     order by h.created_at desc, h.id desc
     limit 1;
    if v_modo_claim is distinct from p_disparador then
        raise exception 'DISPARADOR_NO_COINCIDE_CON_CLAIM';
    end if;

    select coalesce(max(intento), 0) + 1 into v_intento
      from public.conciliaciones where factura_id = f.id;
    update public.conciliaciones
       set es_actual = false
     where factura_id = f.id and es_actual;

    insert into public.conciliaciones (
        factura_id, intento, disparador, estado, es_actual, tolerancia,
        importe_factura, importe_explicado, diferencia, resultado,
        provenance, worker_id, finalizado_at, idempotency_key
    ) values (
        f.id, v_intento, p_disparador, 'COMPLETADA', true,
        (p_resultado->>'tolerancia')::numeric,
        (p_resultado->>'importe_factura')::numeric,
        (p_resultado->>'importe_explicado')::numeric,
        (p_resultado->>'diferencia')::numeric,
        v_resultado,
        jsonb_build_object('modo_ejecucion', p_disparador,
                           'resultado_hash', encode(extensions.digest(p_resultado::text, 'sha256'), 'hex')),
        p_worker_id, now(), p_idempotency_key
    )
    returning id into v_id;

    insert into public.conciliacion_detalles (
        conciliacion_id, orden, factura_albaran_extraido_id, factura_movimiento_id,
        albaran_farmacia, albaran_id_contador, coincidencia_numero_literal,
        tipo_relacion, importe_aplicado, estado, provenance
    )
    select v_id,
           (d->>'orden')::integer,
           nullif(d->>'factura_albaran_extraido_id', '')::uuid,
           nullif(d->>'factura_movimiento_id', '')::uuid,
           d->>'albaran_farmacia',
           nullif(d->>'albaran_id_contador', '')::bigint,
           coalesce((d->>'coincidencia_numero_literal')::boolean, false),
           d->>'tipo_relacion',
           (d->>'importe_aplicado')::numeric,
           d->>'estado',
           coalesce(d->'provenance', '{}'::jsonb)
      from jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d;

    v_estado := case when v_resultado = 'CONCILIADA' then 'CONCILIADA' else 'PENDIENTE_CONCILIAR' end;
    update public.facturas
       set estado_conciliacion_cf = v_estado,
           diferencia_albaranes = (p_resultado->>'diferencia')::numeric,
           conciliacion_intentos = v_intento,
           conciliacion_intentos_fallo = 0,
           conciliacion_ultima_clase_fallo = null,
           conciliacion_proximo_at = null,
           conciliacion_ultimo_error = null,
           conciliacion_bloqueado_hasta = null,
           conciliacion_bloqueado_por = null,
           conciliacion_reintento_solicitado_at = null,
           updated_at = now()
     where id = f.id;

    insert into public.historial_facturas
        (documento_id, factura_id, evento, origen, actor, estado_anterior, estado_nuevo, detalle)
    values (
        f.documento_id, f.id, 'CONCILIACION_PERSISTIDA', 'RPC', p_worker_id,
        jsonb_build_object('estado_conciliacion_cf', f.estado_conciliacion_cf),
        jsonb_build_object('estado_conciliacion_cf', v_estado),
        jsonb_build_object('conciliacion_id', v_id, 'intento', v_intento,
                           'disparador', p_disparador, 'resultado', v_resultado,
                           'diferencia', p_resultado->>'diferencia')
    );
    return v_id;
end;
$$;

-- R7: fallo con backoff configurable; al maximo pasa a REVISION_CONCILIACION.
create or replace function public.cf_registrar_fallo_conciliacion(
    p_factura_id uuid,
    p_worker_id text,
    p_disparador text,
    p_error_codigo text,
    p_error_detalle text,
    p_clase_fallo text
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    f public.facturas%rowtype;
    v_fallos integer;
    v_max integer;
    v_backoff interval[];
    v_estado text;
    v_proximo timestamptz;
begin
    if p_disparador is null or p_disparador not in ('AUTOMATICO', 'MANUAL_ONE_SHOT') then
        raise exception 'DISPARADOR_CONCILIACION_NO_ADMITIDO';
    end if;
    if p_clase_fallo is null or p_clase_fallo not in ('DEFECTO_DOCUMENTO', 'TRANSITORIO') then
        raise exception 'CLASE_FALLO_NO_ADMITIDA';
    end if;
    if nullif(btrim(p_worker_id), '') is null then
        raise exception 'worker_id obligatorio';
    end if;

    select * into f from public.facturas where id = p_factura_id for update;
    if f.id is null or f.conciliacion_bloqueado_por is distinct from p_worker_id then
        -- Sin claim del llamante: retransmision, sin cambios.
        return false;
    end if;

    select conciliacion_max_intentos, conciliacion_backoff
      into v_max, v_backoff
      from public.cf_configuracion where id = true;

    -- Un reintento solicitado reinicia el presupuesto de fallos.
    v_fallos := case when f.conciliacion_reintento_solicitado_at is not null
                     then 1 else f.conciliacion_intentos_fallo + 1 end;
    if v_fallos >= v_max then
        v_estado := 'REVISION_CONCILIACION';
        v_proximo := null;
    else
        v_estado := 'PENDIENTE_CONCILIAR';
        v_proximo := now() + v_backoff[least(v_fallos, cardinality(v_backoff))];
    end if;

    update public.facturas
       set estado_conciliacion_cf = v_estado,
           conciliacion_intentos_fallo = v_fallos,
           conciliacion_ultima_clase_fallo = p_clase_fallo,
           conciliacion_ultimo_error = coalesce(p_error_codigo, '') || ': ' || coalesce(p_error_detalle, ''),
           conciliacion_proximo_at = v_proximo,
           conciliacion_bloqueado_hasta = null,
           conciliacion_bloqueado_por = null,
           conciliacion_reintento_solicitado_at = null,
           updated_at = now()
     where id = f.id;

    insert into public.historial_facturas
        (documento_id, factura_id, evento, origen, actor, estado_anterior, estado_nuevo, detalle)
    values (
        f.documento_id, f.id, 'CONCILIACION_ERROR', 'RPC', p_worker_id,
        jsonb_build_object('estado_conciliacion_cf', f.estado_conciliacion_cf),
        jsonb_build_object('estado_conciliacion_cf', v_estado, 'conciliacion_proximo_at', v_proximo),
        jsonb_build_object('codigo', p_error_codigo, 'clase_fallo', p_clase_fallo,
                           'intentos_fallo', v_fallos, 'max_intentos', v_max,
                           'disparador', p_disparador)
    );
    return true;
end;
$$;

-- Privilegios explicitos: el default ACL de Supabase concede EXECUTE a anon,
-- authenticated y service_role sobre funciones nuevas de public.
revoke all on function public.cf_reclamar_factura_conciliacion_nucleo(text, integer, text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_reclamar_factura_conciliacion(text, integer)
    from public, anon, authenticated;
revoke all on function public.cf_reclamar_factura_conciliacion_manual_one_shot(text, integer)
    from public, anon, authenticated;
revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
revoke all on function public.cf_registrar_fallo_conciliacion(uuid, text, text, text, text, text)
    from public, anon, authenticated;

grant execute on function public.cf_reclamar_factura_conciliacion(text, integer)
    to service_role;
grant execute on function public.cf_reclamar_factura_conciliacion_manual_one_shot(text, integer)
    to service_role;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;
grant execute on function public.cf_registrar_fallo_conciliacion(uuid, text, text, text, text, text)
    to service_role;

comment on function public.cf_reclamar_factura_conciliacion_manual_one_shot(text, integer) is
    'Claim manual de una unica factura. Salta solo conciliacion_automatica y no admite preseleccion.';

commit;
