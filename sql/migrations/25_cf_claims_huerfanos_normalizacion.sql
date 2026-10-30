-- Migracion 25 (Hito 2BI): recuperacion de claims huerfanos de normalizacion.
-- Un documento queda huerfano si el proceso muere tras el claim (NORMALIZANDO, lock caducado, sin
-- ejecucion): el selector solo admite PENDIENTE/ERROR y nadie mas puede registrar su fallo. Esta
-- migracion solo anade funciones nuevas (no cambia claim, selector, persistencia ni reprocesado, R4):
-- - cf_senales_claim_huerfano (auxiliar, solo propietario): senales de persistencia parcial;
-- - cf_huerfanos_normalizacion (lectura, service_role): candidatos y prevision;
-- - cf_recuperar_claim_huerfano_normalizacion (RPC, service_role): un documento, una transaccion.
-- Huerfano limpio -> cf_registrar_fallo_normalizacion tal cual (TRANSITORIO, CLAIM_HUERFANO: cuenta como
-- intento, R3). Senales de persistencia parcial -> REVISION sin tocar nada mas. Idempotente.
-- No modifica filas existentes. Requiere la 24. Diseno: pruebas/auditoria_2bi/DISENO.md.
begin;

do $$
begin
    if to_regprocedure('public.cf_linea_r17_valida(uuid,text,jsonb,jsonb)') is null then
        raise exception 'MIGRACION_24_AUSENTE';
    end if;
end;
$$;

-- Senales de que algo se persistio o paso despues del ultimo claim. La persistencia es atomica, asi que
-- un huerfano limpio no tiene ninguna; cualquiera indica un estado incoherente (en la duda, revision).
create or replace function public.cf_senales_claim_huerfano(p_documento_id uuid)
returns text[]
language plpgsql
stable
set search_path = public
as $$
declare
    d public.documentos_facturas%rowtype;
    c public.historial_facturas%rowtype;
begin
    select * into d from public.documentos_facturas where id = p_documento_id;
    select * into c
      from public.historial_facturas
     where documento_id = p_documento_id and evento = 'NORMALIZACION_CLAIM'
     order by id desc
     limit 1;
    return array_remove(array[
        case when d.bloqueado_por is null then 'SIN_WORKER' end,
        case when c.id is null then 'SIN_EVENTO_CLAIM' end,
        case when c.id is not null and c.actor is distinct from d.bloqueado_por then 'CLAIM_DE_OTRO_WORKER' end,
        case when d.estado_persistencia <> 'PENDIENTE' then 'ESTADO_PERSISTENCIA:' || d.estado_persistencia end,
        (select 'FACTURAS_ENLAZADAS:' || count(*) from public.facturas f
          where f.documento_id = p_documento_id having count(*) > 0),
        (select 'EJECUCIONES_TRAS_CLAIM:' || count(*) from public.normalizacion_ejecuciones e
          where c.id is not null and e.documento_id = p_documento_id
            and coalesce(e.iniciado_at, e.created_at) >= c.created_at having count(*) > 0),
        (select 'EVENTOS_TRAS_CLAIM:' || count(*) from public.historial_facturas h
          where c.id is not null and h.documento_id = p_documento_id and h.id > c.id having count(*) > 0)
    ], null);
end;
$$;

create or replace function public.cf_huerfanos_normalizacion(p_gracia interval)
returns table (
    documento_id uuid,
    farmacia text,
    bloqueado_por text,
    bloqueado_hasta timestamptz,
    prevision text,
    senales text[]
)
language sql
stable
security definer
set search_path = public
as $$
    select d.id, d.farmacia, d.bloqueado_por, d.bloqueado_hasta,
           case
               when coalesce(d.bloqueado_hasta, '-infinity'::timestamptz) >= now() - p_gracia then 'LOCK_VIGENTE'
               when cardinality(public.cf_senales_claim_huerfano(d.id)) > 0 then 'REVISION'
               else 'RECUPERABLE'
           end,
           public.cf_senales_claim_huerfano(d.id)
      from public.documentos_facturas d
      cross join public.cf_configuracion c
     where c.id = true
       and d.farmacia = any(c.farmacias_habilitadas)
       and d.estado_lectura = 'NORMALIZANDO'
     order by d.bloqueado_hasta nulls first, d.id;
$$;

create or replace function public.cf_recuperar_claim_huerfano_normalizacion(
    p_documento_id uuid,
    p_actor text,
    p_gracia interval
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    d public.documentos_facturas%rowtype;
    c public.historial_facturas%rowtype;
    v_final public.documentos_facturas%rowtype;
    v_senales text[];
    v_modo text;
    v_disparador text;
    v_ejecucion uuid;
    v_anterior jsonb;
begin
    if nullif(btrim(p_actor), '') is null then
        raise exception 'ACTOR_OBLIGATORIO';
    end if;
    if p_gracia is null or p_gracia < interval '15 minutes' then
        raise exception 'GRACIA_INSUFICIENTE';
    end if;

    select * into d from public.documentos_facturas where id = p_documento_id for update;
    if d.id is null then
        raise exception 'documento no encontrado';
    end if;
    if not exists (
        select 1 from public.cf_configuracion cfg
         where cfg.id = true and d.farmacia = any(cfg.farmacias_habilitadas)
    ) then
        raise exception 'FARMACIA_NO_HABILITADA';
    end if;

    -- Ya persistido, ya recuperado o reprocesado: nada que hacer (idempotente).
    if d.estado_lectura <> 'NORMALIZANDO' then
        return jsonb_build_object('resultado', 'NO_APLICA', 'documento_id', d.id,
                                  'estado_lectura', d.estado_lectura);
    end if;
    -- Sin latido de worker: solo un lock caducado hace mas que la gracia cuenta como abandonado.
    if coalesce(d.bloqueado_hasta, '-infinity'::timestamptz) >= now() - p_gracia then
        return jsonb_build_object('resultado', 'LOCK_VIGENTE', 'documento_id', d.id,
                                  'bloqueado_por', d.bloqueado_por, 'bloqueado_hasta', d.bloqueado_hasta);
    end if;

    select * into c
      from public.historial_facturas
     where documento_id = d.id and evento = 'NORMALIZACION_CLAIM'
     order by id desc
     limit 1;
    v_senales := public.cf_senales_claim_huerfano(d.id);
    v_anterior := jsonb_build_object('estado_lectura', d.estado_lectura, 'bloqueado_por', d.bloqueado_por,
                                     'bloqueado_hasta', d.bloqueado_hasta);

    if cardinality(v_senales) > 0 then
        update public.documentos_facturas
           set estado_lectura = 'REVISION',
               bloqueado_por = null,
               bloqueado_hasta = null,
               fecha_actualizacion = now()
         where id = d.id;
        insert into public.historial_facturas
            (documento_id, evento, origen, actor, estado_anterior, estado_nuevo, detalle)
        values (d.id, 'NORMALIZACION_CLAIM_HUERFANO_REVISION', 'RPC', p_actor, v_anterior,
                jsonb_build_object('estado_lectura', 'REVISION'),
                jsonb_build_object('senales', to_jsonb(v_senales), 'gracia', p_gracia::text,
                                   'claim_evento', c.id));
        return jsonb_build_object('resultado', 'REVISION', 'documento_id', d.id,
                                  'senales', to_jsonb(v_senales));
    end if;

    -- Huerfano limpio: el fallo se registra con la RPC de R2/R3 tal cual, en nombre del claim.
    v_modo := coalesce(c.detalle->>'modo_ejecucion', 'AUTOMATICO');
    v_disparador := case when v_modo = 'AUTOMATICO' and d.reprocesar_solicitado_at is not null
                         then 'REPROCESADO' else v_modo end;
    v_ejecucion := public.cf_registrar_fallo_normalizacion(
        d.id, d.bloqueado_por, v_disparador, 'huerfano:' || d.id || ':' || c.id, 'CLAIM_HUERFANO',
        'claim sin cierre; lock caducado el ' || d.bloqueado_hasta::text, 'TRANSITORIO');

    select * into v_final from public.documentos_facturas where id = d.id;
    insert into public.historial_facturas
        (documento_id, evento, origen, actor, estado_anterior, estado_nuevo, detalle)
    values (d.id, 'NORMALIZACION_CLAIM_HUERFANO', 'RPC', p_actor, v_anterior,
            jsonb_build_object('estado_lectura', v_final.estado_lectura,
                               'proximo_reintento_at', v_final.proximo_reintento_at),
            jsonb_build_object('worker', d.bloqueado_por, 'claim_evento', c.id, 'claim_at', c.created_at,
                               'modo_ejecucion', v_modo, 'gracia', p_gracia::text,
                               'ejecucion_id', v_ejecucion,
                               'intentos_fallo', v_final.intentos_fallo_normalizacion));
    return jsonb_build_object('resultado', 'RECUPERADO', 'documento_id', d.id,
                              'estado_lectura', v_final.estado_lectura,
                              'intentos_fallo', v_final.intentos_fallo_normalizacion,
                              'proximo_reintento_at', v_final.proximo_reintento_at,
                              'ejecucion_id', v_ejecucion);
end;
$$;

-- Privilegios (patron 24): SECURITY DEFINER, owner postgres; solo service_role ejecuta las RPC.
revoke all on function public.cf_recuperar_claim_huerfano_normalizacion(uuid, text, interval)
    from public, anon, authenticated;
grant execute on function public.cf_recuperar_claim_huerfano_normalizacion(uuid, text, interval)
    to service_role;
revoke all on function public.cf_huerfanos_normalizacion(interval)
    from public, anon, authenticated;
grant execute on function public.cf_huerfanos_normalizacion(interval)
    to service_role;
-- Auxiliar: solo el propietario (la usan las funciones SECURITY DEFINER).
revoke all on function public.cf_senales_claim_huerfano(uuid)
    from public, anon, authenticated, service_role;

commit;
