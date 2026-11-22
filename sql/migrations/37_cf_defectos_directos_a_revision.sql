-- Migracion 37 (DECISIONES DE PIO D1-D7, 2026-11-18 y 2026-11-19): los defectos de EXTRACCION pasan directamente a
-- REVISION en el primer fallo, sin reintentos ni espera. Diseno: pruebas/auditoria_37/DISENO.md.
-- - Columna normalizacion_ejecuciones.lector (jsonb: adaptador, version_adaptador y layout del extractor autorizado; null
--   si no se conoce). Las filas existentes quedan en null (D3: los documentos en REVISION de antes de la 37 entraran en
--   el primer plan de reprocesado tras un cambio del lector).
-- - cf_registrar_fallo_normalizacion de 8 parametros (D6: p_lector jsonb, sin valor por defecto):
--   NO_SOPORTADO -> PROVEEDOR_NO_SOPORTADO sin intento (sin cambios); DEFECTO_DOCUMENTO -> +1 intento (D4) y REVISION
--   en el primero, sin espera, con regla DEFECTO_DIRECTO_A_REVISION en el detalle del historial; TRANSITORIO (incluidos
--   los motivos de almacenamiento, D1/D5, que el codigo ya clasifica asi) -> sin cambios: ERROR con espera o REVISION
--   al maximo. Guarda el lector en la ejecucion.
-- - La firma de 7 parametros se conserva (codigo anterior a la 37 y migracion 25) y llama a la de 8 con p_lector null;
--   la de 6 sigue llamando a la de 7. create or replace conserva sus ACL.
-- - AUTORIZACION EXPRESA DE PIO (2026-11-19, D7): esta migracion y su rollback son los UNICOS ficheros que nombran el
--   rol del sistema, para el EXECUTE de la firma nueva. Nada para anon, authenticated ni PUBLIC.
-- Ningun dato cambia. Idempotente. Requiere la 36.
begin;

do $$
begin
    if not exists (select 1 from information_schema.columns where table_schema = 'public'
                   and table_name = 'cf_configuracion' and column_name = 'conciliacion_r20') then
        raise exception 'MIGRACION_36_AUSENTE';
    end if;
end;
$$;

alter table public.normalizacion_ejecuciones add column if not exists lector jsonb;
comment on column public.normalizacion_ejecuciones.lector is
    'Migracion 37: lector con el que fallo la ejecucion (adaptador, version_adaptador y layout del extractor '
    'autorizado; layout null si el fallo es anterior a reconocerlo). Null en las ejecuciones anteriores a la 37. '
    'Sirve para elegir que documentos en REVISION reprocesar cuando cambie el lector (decision de Pio, D2).';

create or replace function public.cf_registrar_fallo_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_error_codigo text,
    p_error_detalle text,
    p_clase_fallo text,
    p_lector jsonb
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
    v_regla text;
begin
    if p_clase_fallo is null
       or p_clase_fallo not in ('NO_SOPORTADO', 'DEFECTO_DOCUMENTO', 'TRANSITORIO') then
        raise exception 'CLASE_FALLO_NO_ADMITIDA';
    end if;
    if p_lector is not null and jsonb_typeof(p_lector) <> 'object' then
        raise exception 'LECTOR_NO_VALIDO';
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
    elsif p_clase_fallo = 'DEFECTO_DOCUMENTO' then
        -- 37 (D1, D4, D5): el defecto de extraccion cuenta un intento y pasa a REVISION en el primero.
        v_fallos := d.intentos_fallo_normalizacion + 1;
        v_estado := 'REVISION';
        v_proximo := null;
        v_regla := 'DEFECTO_DIRECTO_A_REVISION';
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
         iniciado_at, finalizado_at, error_codigo, error_detalle, clase_fallo, lector)
    values (p_documento_id, v_clave, v_intento, p_disparador, 'ERROR',
        p_worker_id, now(), now(), p_error_codigo, p_error_detalle, p_clase_fallo, p_lector)
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
                           'max_intentos', v_max)
        || case when v_regla is null then '{}'::jsonb else jsonb_build_object('regla', v_regla) end);
    return v_ejecucion_id;
end;
$$;

-- Firma de 7 parametros (17) conservada para el codigo anterior a la 37 y la migracion 25: sin lector.
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
language sql
security definer
set search_path = public
as $$
    select public.cf_registrar_fallo_normalizacion(
        p_documento_id, p_worker_id, p_disparador, p_idempotency_key,
        p_error_codigo, p_error_detalle, p_clase_fallo, null::jsonb);
$$;

revoke all on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text, jsonb)
    to service_role;

comment on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text, jsonb) is
    'Fallo clasificado (R2/R3, 37): NO_SOPORTADO -> PROVEEDOR_NO_SOPORTADO; DEFECTO_DOCUMENTO -> REVISION en el primer '
    'fallo; TRANSITORIO -> ERROR con backoff o REVISION al maximo. Guarda el lector.';
comment on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text) is
    'Fallo clasificado sin lector (37): llama a la firma de 8 parametros con p_lector null.';

commit;
