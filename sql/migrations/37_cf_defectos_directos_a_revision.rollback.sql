-- Rollback de la migracion 37: devuelve el esquema exacto de la 36.
-- Restaura el texto exacto de la firma de 7 parametros de cf_registrar_fallo_normalizacion de la migracion 17 (y su
-- comentario), quita la firma de 8 parametros y la columna normalizacion_ejecuciones.lector. create or replace conserva
-- la ACL de la 17 en la de 7 parametros. No mueve documentos: los que entraron en REVISION por la regla de la 37 se
-- quedan ahi y solo vuelven a la cola por reprocesado explicito. Se pierden los lectores guardados. Solo con
-- confirmacion de Pio. Idempotente. La autorizacion de Pio (D7) cubre este fichero, que no necesita nombrar el rol del
-- sistema.
begin;

create or replace function public.cf_registrar_fallo_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_error_codigo text,
    p_error_detalle text,
    p_clase_fallo text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    d public.documentos_facturas%rowtype;
    v_existente uuid;
    v_ejecucion_id uuid;
    v_intento integer;
    v_clave text := p_idempotency_key;
    v_fallos integer;
    v_max integer;
    v_backoff interval[];
    v_estado text;
    v_proximo timestamptz;
begin
    if p_clase_fallo is null
       or p_clase_fallo not in ('NO_SOPORTADO', 'DEFECTO_DOCUMENTO', 'TRANSITORIO') then
        raise exception 'CLASE_FALLO_NO_ADMITIDA';
    end if;
    if nullif(btrim(p_worker_id), '') is null
       or nullif(btrim(p_idempotency_key), '') is null then
        raise exception 'worker_id e idempotency_key obligatorios';
    end if;

    select * into d from public.documentos_facturas where id = p_documento_id for update;
    select id into v_existente
      from public.normalizacion_ejecuciones
     where documento_id = p_documento_id and idempotency_key = p_idempotency_key;

    if d.id is null
       or d.bloqueado_por is distinct from p_worker_id
       or not exists (
           select 1 from public.cf_configuracion c
            where c.id = true and d.farmacia = any(c.farmacias_habilitadas)
       ) then
        if v_existente is not null then
            return v_existente;
        end if;
        raise exception 'claim no pertenece al worker';
    end if;

    select coalesce(max(intento), 0) + 1 into v_intento
      from public.normalizacion_ejecuciones where documento_id = p_documento_id;
    if v_existente is not null then
        v_clave := p_idempotency_key || ':intento:' || v_intento;
    end if;

    select normalizacion_max_intentos, normalizacion_backoff
      into v_max, v_backoff
      from public.cf_configuracion where id = true;

    if p_clase_fallo = 'NO_SOPORTADO' then
        v_estado := 'PROVEEDOR_NO_SOPORTADO';
        v_fallos := d.intentos_fallo_normalizacion;
        v_proximo := null;
    else
        v_fallos := d.intentos_fallo_normalizacion + 1;
        if v_fallos >= v_max then
            v_estado := 'REVISION';
            v_proximo := null;
        else
            v_estado := 'ERROR';
            v_proximo := now() + v_backoff[least(v_fallos, cardinality(v_backoff))];
        end if;
    end if;

    insert into public.normalizacion_ejecuciones
        (documento_id, idempotency_key, intento, disparador, estado, worker_id,
         iniciado_at, finalizado_at, error_codigo, error_detalle, clase_fallo)
    values (p_documento_id, v_clave, v_intento, p_disparador, 'ERROR',
        p_worker_id, now(), now(), p_error_codigo, p_error_detalle, p_clase_fallo)
    returning id into v_ejecucion_id;

    update public.documentos_facturas
       set estado_lectura = v_estado,
           ultimo_error_codigo = p_error_codigo,
           ultima_clase_fallo = p_clase_fallo,
           intentos_fallo_normalizacion = v_fallos,
           proximo_reintento_at = v_proximo,
           bloqueado_hasta = null, bloqueado_por = null,
           reprocesar_solicitado_at = null, fecha_actualizacion = now()
     where id = p_documento_id;
    insert into public.historial_facturas
        (documento_id, evento, origen, actor, estado_nuevo, detalle)
    values (p_documento_id, 'NORMALIZACION_ERROR', 'RPC', p_worker_id,
        jsonb_build_object('estado_lectura', v_estado,
                           'proximo_reintento_at', v_proximo),
        jsonb_build_object('ejecucion_id', v_ejecucion_id, 'codigo', p_error_codigo,
                           'clase_fallo', p_clase_fallo, 'intentos_fallo', v_fallos,
                           'max_intentos', v_max));
    return v_ejecucion_id;
end;
$$;

comment on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text) is
    'Fallo clasificado (R2/R3): NO_SOPORTADO -> PROVEEDOR_NO_SOPORTADO; resto -> ERROR con backoff o REVISION al maximo.';

drop function if exists public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text, jsonb);

alter table public.normalizacion_ejecuciones drop column if exists lector;

commit;
