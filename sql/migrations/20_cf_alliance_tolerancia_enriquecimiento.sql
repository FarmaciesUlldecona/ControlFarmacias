-- Migracion 20 (Hito 2AZ): R11 tolerancia proporcional de conciliacion y R12
-- enriquecimiento de facturas persistidas. Generada por
-- pruebas/auditoria_2az/generar_migracion_20.py a partir del texto exacto de la 18.
-- No toca selector, ordering ni elegibilidad. Sin DML sobre filas existentes
-- (solo defaults de columnas nuevas en cf_configuracion). Idempotente.
begin;

-- R11: parametros protegidos por check.
alter table public.cf_configuracion
    add column if not exists conciliacion_tolerancia_suelo numeric(14,4) not null default 0.0500,
    add column if not exists conciliacion_tolerancia_por_albaran numeric(14,4) not null default 0.0100,
    add column if not exists conciliacion_tolerancia_tope numeric(14,4) not null default 0.5000;
alter table public.cf_configuracion
    drop constraint if exists cf_configuracion_tolerancia_r11_check;
alter table public.cf_configuracion
    add constraint cf_configuracion_tolerancia_r11_check check (
        conciliacion_tolerancia_suelo > 0
        and conciliacion_tolerancia_suelo <= conciliacion_tolerancia_tope
        and conciliacion_tolerancia_tope <= 1.0000
        and conciliacion_tolerancia_por_albaran >= 0
        and conciliacion_tolerancia_por_albaran <= 0.0500
    );

-- R11: cierre atomico de la 18 con validacion y registro de la tolerancia aplicada.
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
    v_resultado_efectivo text;
    v_max integer;
    v_backoff interval[];
    v_fallos integer;
    v_proximo timestamptz;
    v_clase text;
    -- R11 (2AZ)
    v_casados integer;
    v_suelo numeric;
    v_por_albaran numeric;
    v_tope numeric;
    v_tolerancia numeric;
    v_regla jsonb;
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

    -- D-A: CONCILIADA reinicia el contador; cualquier otro resultado consume un
    -- intento con el backoff de R7 y al maximo pasa a REVISION_CONCILIACION.
    v_resultado_efectivo := coalesce(v_existente.resultado, v_resultado);
    select conciliacion_max_intentos, conciliacion_backoff
      into v_max, v_backoff
      from public.cf_configuracion where id = true;
    if v_resultado_efectivo = 'CONCILIADA' then
        v_estado := 'CONCILIADA';
        v_fallos := 0;
        v_proximo := null;
        v_clase := null;
    else
        -- Un reintento solicitado reinicia el presupuesto de intentos.
        v_fallos := case when f.conciliacion_reintento_solicitado_at is not null
                         then 1 else f.conciliacion_intentos_fallo + 1 end;
        v_clase := 'DIFERENCIA';
        if v_fallos >= v_max then
            v_estado := 'REVISION_CONCILIACION';
            v_proximo := null;
        else
            v_estado := 'PENDIENTE_CONCILIAR';
            v_proximo := now() + v_backoff[least(v_fallos, cardinality(v_backoff))];
        end if;
    end if;

    if v_existente.id is not null then
        -- Replay: nunca duplica. Con el claim del llamante (nueva evaluacion con la
        -- misma evidencia) libera el lock y aplica el estado del resultado original.
        if f.conciliacion_bloqueado_por is not null and f.conciliacion_bloqueado_por = p_worker_id then
            update public.facturas
               set estado_conciliacion_cf = v_estado,
                   conciliacion_intentos_fallo = v_fallos,
                   conciliacion_ultima_clase_fallo = v_clase,
                   conciliacion_proximo_at = v_proximo,
                   conciliacion_bloqueado_por = null,
                   conciliacion_bloqueado_hasta = null,
                   conciliacion_reintento_solicitado_at = null,
                   updated_at = now()
             where id = f.id;
            v_liberado := true;
        else
            -- Retransmision sin claim: sin cambios.
            v_estado := f.estado_conciliacion_cf;
            v_fallos := f.conciliacion_intentos_fallo;
            v_proximo := f.conciliacion_proximo_at;
        end if;
        insert into public.historial_facturas
            (documento_id, factura_id, evento, origen, actor, estado_nuevo, detalle)
        values (
            f.documento_id, f.id, 'CONCILIACION_REPLAY_IDEMPOTENTE', 'RPC', p_worker_id,
            jsonb_build_object('estado_conciliacion_cf', v_estado,
                               'conciliacion_proximo_at', v_proximo),
            jsonb_build_object('conciliacion_id', v_existente.id, 'claim_liberado', v_liberado,
                               'disparador', p_disparador, 'resultado', v_existente.resultado,
                               'intentos_fallo', v_fallos, 'max_intentos', v_max)
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

    -- R11 (2AZ): la tolerancia aplicada debe ser la proporcional calculada aqui
    -- con los albaranes casados (UNO_A_UNO) y los parametros de cf_configuracion.
    select count(*) into v_casados
      from jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d
     where d->>'tipo_relacion' = 'UNO_A_UNO';
    select conciliacion_tolerancia_suelo, conciliacion_tolerancia_por_albaran,
           conciliacion_tolerancia_tope
      into v_suelo, v_por_albaran, v_tope
      from public.cf_configuracion where id = true;
    v_tolerancia := greatest(v_suelo, least(v_por_albaran * v_casados, v_tope));
    if (p_resultado->>'tolerancia') is null
       or (p_resultado->>'tolerancia')::numeric <> v_tolerancia then
        raise exception 'TOLERANCIA_NO_COINCIDE_CON_R11';
    end if;
    if p_resultado ? 'tolerancia_regla' and (
           (p_resultado #>> '{tolerancia_regla,suelo}')::numeric is distinct from v_suelo
        or (p_resultado #>> '{tolerancia_regla,por_albaran}')::numeric is distinct from v_por_albaran
        or (p_resultado #>> '{tolerancia_regla,tope}')::numeric is distinct from v_tope
        or (p_resultado #>> '{tolerancia_regla,albaranes_casados}')::integer is distinct from v_casados
    ) then
        raise exception 'TOLERANCIA_REGLA_NO_COINCIDE';
    end if;
    if (v_resultado = 'CONCILIADA' and abs((p_resultado->>'diferencia')::numeric) > v_tolerancia)
       or (v_resultado = 'DIFERENCIA' and abs((p_resultado->>'diferencia')::numeric) <= v_tolerancia) then
        raise exception 'RESULTADO_INCOHERENTE_CON_TOLERANCIA';
    end if;
    v_regla := jsonb_build_object('suelo', v_suelo, 'por_albaran', v_por_albaran, 'tope', v_tope,
                                  'albaranes_casados', v_casados, 'tolerancia', v_tolerancia);

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
                           'resultado_hash', encode(extensions.digest(p_resultado::text, 'sha256'), 'hex'),
                           'tolerancia_regla', v_regla),
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

    update public.facturas
       set estado_conciliacion_cf = v_estado,
           diferencia_albaranes = (p_resultado->>'diferencia')::numeric,
           conciliacion_intentos = v_intento,
           conciliacion_intentos_fallo = v_fallos,
           conciliacion_ultima_clase_fallo = v_clase,
           conciliacion_proximo_at = v_proximo,
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
        jsonb_build_object('estado_conciliacion_cf', v_estado,
                           'conciliacion_proximo_at', v_proximo),
        jsonb_build_object('conciliacion_id', v_id, 'intento', v_intento,
                           'disparador', p_disparador, 'resultado', v_resultado,
                           'diferencia', p_resultado->>'diferencia',
                           'tolerancia', p_resultado->>'tolerancia',
                           'intentos_fallo', v_fallos, 'max_intentos', v_max,
                           'albaranes_casados', v_casados)
    );
    return v_id;
end;
$$;

-- R12: enriquecimiento.
create or replace function public.cf_enriquecer_factura(
    p_factura_id uuid,
    p_worker_id text,
    p_idempotency_key text,
    p_enriquecimiento jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    f public.facturas%rowtype;
    v_hash_archivo text;
    v_hash text;
    v_previo jsonb;
    v_ident jsonb;
    v_cif text;
    v_prov jsonb;
    v_item jsonb;
    v_orden integer;
    v_n integer;
    v_venc_id uuid;
    v_venc_importe numeric;
    v_albaranes integer := 0;
    v_movimientos integer := 0;
    v_vencimientos integer := 0;
begin
    if nullif(btrim(p_worker_id), '') is null or nullif(btrim(p_idempotency_key), '') is null then
        raise exception 'worker_id e idempotency_key obligatorios';
    end if;
    if p_idempotency_key not like 'enriquecimiento:' || p_factura_id::text || ':%' then
        raise exception 'IDEMPOTENCY_KEY_NO_VALIDA';
    end if;
    if p_enriquecimiento is null or jsonb_typeof(p_enriquecimiento) <> 'object' then
        raise exception 'ENRIQUECIMIENTO_INVALIDO';
    end if;
    v_hash := encode(extensions.digest(p_enriquecimiento::text, 'sha256'), 'hex');
    v_ident := coalesce(p_enriquecimiento->'identidad', '{}'::jsonb);

    select * into f from public.facturas where id = p_factura_id for update;
    if f.id is null then
        raise exception 'factura no encontrada';
    end if;
    if not exists (
        select 1 from public.cf_configuracion c
         where c.id = true and f.farmacia = any(c.farmacias_habilitadas)
    ) then
        raise exception 'FARMACIA_NO_HABILITADA';
    end if;

    -- Replay: misma clave y mismo contenido -> sin ninguna escritura.
    select h.detalle into v_previo
      from public.historial_facturas h
     where h.factura_id = f.id and h.evento = 'FACTURA_ENRIQUECIDA'
       and h.detalle->>'idempotency_key' = p_idempotency_key
     order by h.id desc
     limit 1;
    if v_previo is not null then
        if v_previo->>'payload_sha256' is distinct from v_hash then
            raise exception 'IDEMPOTENCY_KEY_REUTILIZADA';
        end if;
        return jsonb_build_object('replay', true, 'factura_id', f.id, 'idempotency_key', p_idempotency_key);
    end if;

    if f.estado_conciliacion_cf = 'CONCILIADA' then
        raise exception 'FACTURA_YA_CONCILIADA';
    end if;
    if f.estado_conciliacion_cf <> 'PENDIENTE_CONCILIAR' then
        raise exception 'FACTURA_EN_REVISION_CONCILIACION';
    end if;
    if f.conciliacion_bloqueado_por is not null
       and (f.conciliacion_bloqueado_hasta is null or f.conciliacion_bloqueado_hasta > now()) then
        raise exception 'FACTURA_RECLAMADA_EN_CONCILIACION';
    end if;

    -- Mismo documento origen, mismo SHA e identidad economica identica.
    if p_enriquecimiento->>'documento_id' is distinct from f.documento_id::text then
        raise exception 'DOCUMENTO_NO_COINCIDE';
    end if;
    select archivo_hash into v_hash_archivo from public.documentos_facturas where id = f.documento_id;
    if v_hash_archivo is null or v_hash_archivo is distinct from p_enriquecimiento->>'archivo_hash' then
        raise exception 'SHA_NO_COINCIDE';
    end if;
    if v_ident->>'numero_factura' is distinct from f.numero_factura then
        raise exception 'IDENTIDAD_NO_COINCIDE:numero_factura';
    end if;
    if nullif(v_ident->>'fecha_factura', '')::date is distinct from f.fecha_factura then
        raise exception 'IDENTIDAD_NO_COINCIDE:fecha_factura';
    end if;
    if nullif(v_ident->>'importe_total', '')::numeric is distinct from f.importe_total then
        raise exception 'IDENTIDAD_NO_COINCIDE:importe_total';
    end if;
    v_cif := regexp_replace(upper(coalesce(nullif(f.proveedor_cif, ''),
                                           f.datos_extraidos #>> '{proveedor,nif,valor}', '')), '[^A-Z0-9]', '', 'g');
    if v_cif = '' or regexp_replace(upper(coalesce(v_ident->>'proveedor_cif', '')), '[^A-Z0-9]', '', 'g') <> v_cif then
        raise exception 'IDENTIDAD_NO_COINCIDE:proveedor_cif';
    end if;
    if v_ident->>'identidad_economica_clave' is null
       or v_ident->>'identidad_economica_clave' is distinct from f.datos_extraidos->>'identidad_economica_clave' then
        raise exception 'IDENTIDAD_NO_COINCIDE:identidad_economica_clave';
    end if;

    v_prov := jsonb_build_object('idempotency_key', p_idempotency_key, 'worker_id', p_worker_id,
                                 'normalizador_version', p_enriquecimiento->>'normalizador_version',
                                 'enriquecido_at', now());

    -- Albaranes: solo filas nuevas (mapeo identico al de la migracion 17).
    select coalesce(max(orden), 0) into v_orden
      from public.facturas_albaranes_extraidos where factura_id = f.id;
    for v_item in select value from jsonb_array_elements(coalesce(p_enriquecimiento->'albaranes', '[]'::jsonb)) loop
        if nullif(btrim(v_item #>> '{numero,valor}'), '') is null then
            raise exception 'ALBARAN_SIN_NUMERO';
        end if;
        if exists (
            select 1 from public.facturas_albaranes_extraidos a
             where a.factura_id = f.id
               and regexp_replace(upper(a.numero_albaran), '[^A-Z0-9]', '', 'g')
                 = regexp_replace(upper(v_item #>> '{numero,valor}'), '[^A-Z0-9]', '', 'g')
        ) then
            raise exception 'ALBARAN_YA_PRESENTE:%', v_item #>> '{numero,valor}';
        end if;
        v_orden := v_orden + 1;
        insert into public.facturas_albaranes_extraidos
            (factura_id, numero_albaran, fecha_albaran, tipo_movimiento,
             importe_base, importe_total, descripcion, orden, literal, provenance)
        values (f.id, v_item #>> '{numero,valor}',
            nullif(v_item #>> '{fecha,valor,iso}', '')::date, v_item->>'sentido',
            nullif(v_item #>> '{importe_base,valor}', '')::numeric,
            nullif(v_item #>> '{importe_total,valor}', '')::numeric,
            v_item #>> '{tipo_pedido,valor}', v_orden,
            v_item #>> '{numero,literal}', v_item || jsonb_build_object('enriquecimiento', v_prov));
        v_albaranes := v_albaranes + 1;
    end loop;

    -- Movimientos: solo en facturas MIXTA (cambiar la naturaleza modificaria la factura).
    if jsonb_array_length(coalesce(p_enriquecimiento->'movimientos', '[]'::jsonb)) > 0
       and coalesce(f.datos_extraidos->>'naturaleza_principal', '') <> 'MIXTA' then
        raise exception 'MOVIMIENTOS_REQUIEREN_NATURALEZA_MIXTA';
    end if;
    select coalesce(max(orden), 0) into v_orden
      from public.facturas_movimientos where factura_id = f.id;
    for v_item in select value from jsonb_array_elements(coalesce(p_enriquecimiento->'movimientos', '[]'::jsonb)) loop
        if exists (
            select 1 from public.facturas_movimientos m
             where m.factura_id = f.id
               and upper(btrim(m.descripcion_literal)) = upper(btrim(v_item #>> '{descripcion_literal,valor}'))
               and m.sentido is not distinct from v_item->>'sentido'
               and m.importe is not distinct from nullif(v_item #>> '{importe,valor}', '')::numeric
        ) then
            raise exception 'MOVIMIENTO_YA_PRESENTE:%', v_item #>> '{descripcion_literal,valor}';
        end if;
        v_orden := v_orden + 1;
        insert into public.facturas_movimientos
            (factura_id, normalizacion_ejecucion_id, orden, categoria,
             descripcion_literal, sentido, base, iva, recargo_equivalencia,
             importe, provenance)
        values (f.id, null, v_orden,
            case v_item->>'tipo'
                when 'SERVICIO' then 'SERVICIO'
                when 'DESCUENTO' then 'DESCUENTO'
                when 'DEVOLUCION_MERCANCIA' then 'DEVOLUCION'
                when 'CONDICION_COMERCIAL' then 'CONDICION_COMERCIAL'
                else 'OTRO' end,
            v_item #>> '{descripcion_literal,valor}', v_item->>'sentido',
            nullif(v_item #>> '{base,valor}', '')::numeric,
            nullif(v_item #>> '{iva,valor}', '')::numeric,
            nullif(v_item #>> '{recargo_equivalencia,valor}', '')::numeric,
            nullif(v_item #>> '{importe,valor}', '')::numeric,
            v_item || jsonb_build_object('enriquecimiento', v_prov));
        v_movimientos := v_movimientos + 1;
    end loop;

    -- Vencimientos: solo rellena importes NULL; nunca sobrescribe un valor no nulo.
    for v_item in select value from jsonb_array_elements(coalesce(p_enriquecimiento->'vencimientos', '[]'::jsonb)) loop
        if nullif(v_item #>> '{importe,valor}', '') is null then
            raise exception 'VENCIMIENTO_SIN_IMPORTE';
        end if;
        select count(*) into v_n
          from public.facturas_vencimientos v
         where v.factura_id = f.id
           and v.fecha_vencimiento = nullif(v_item #>> '{fecha,valor,iso}', '')::date;
        if v_n <> 1 then
            raise exception 'VENCIMIENTO_NO_LOCALIZADO:%', v_item #>> '{fecha,valor,iso}';
        end if;
        select v.id, v.importe into v_venc_id, v_venc_importe
          from public.facturas_vencimientos v
         where v.factura_id = f.id
           and v.fecha_vencimiento = nullif(v_item #>> '{fecha,valor,iso}', '')::date;
        if v_venc_importe is not null then
            raise exception 'VENCIMIENTO_CON_IMPORTE_EXISTENTE:%', v_item #>> '{fecha,valor,iso}';
        end if;
        update public.facturas_vencimientos
           set importe = (v_item #>> '{importe,valor}')::numeric,
               provenance = coalesce(provenance, '{}'::jsonb)
                   || jsonb_build_object('enriquecimiento_importe', v_prov || jsonb_build_object('importe', v_item->'importe'))
         where id = v_venc_id and importe is null;
        v_vencimientos := v_vencimientos + 1;
    end loop;

    if v_albaranes + v_movimientos + v_vencimientos = 0 then
        raise exception 'SIN_FILAS_NUEVAS';
    end if;

    insert into public.historial_facturas
        (documento_id, factura_id, evento, origen, actor, estado_nuevo, detalle)
    values (
        f.documento_id, f.id, 'FACTURA_ENRIQUECIDA', 'RPC', p_worker_id,
        jsonb_build_object('albaranes_anadidos', v_albaranes, 'movimientos_anadidos', v_movimientos,
                           'vencimientos_rellenados', v_vencimientos),
        jsonb_build_object('idempotency_key', p_idempotency_key, 'payload_sha256', v_hash,
                           'normalizador_version', p_enriquecimiento->>'normalizador_version',
                           'worker_id', p_worker_id)
    );
    return jsonb_build_object('replay', false, 'factura_id', f.id,
                              'albaranes_anadidos', v_albaranes, 'movimientos_anadidos', v_movimientos,
                              'vencimientos_rellenados', v_vencimientos);
end;
$$;

-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta.
revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_enriquecer_factura(uuid, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_enriquecer_factura(uuid, text, text, jsonb)
    to service_role;

comment on function public.cf_enriquecer_factura(uuid, text, text, jsonb) is
    'R12: anade albaranes/movimientos no promovidos y rellena importes de vencimiento NULL de una factura no conciliada. Idempotente; nunca modifica filas ni importes existentes.';

commit;
