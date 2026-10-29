-- Migracion 24 (Hito 2BE): R17, linea PDF = albaran de su numero + 1 interno de la misma recepcion.
-- Generada por pruebas/auditoria_2be/generar_migracion_24.py a partir del texto exacto de la 22
-- (cf_persistir_conciliacion; la 23 no lo cambia). Una linea R17 se persiste como dos detalles
-- UNO_A_VARIOS con el mismo origen documental; ambos albaranes quedan reservados (R15, sin cambios).
-- La BD revalida la pareja y R11 cuenta la linea como un albaran casado. No modifica filas
-- existentes. Idempotente. Requiere la 23.
begin;

do $$
begin
    if to_regclass('public.albaranes_aprobaciones') is null
       or to_regprocedure('public.cf_albaran_ausente_abierto(text,bigint)') is null then
        raise exception 'MIGRACION_23_AUSENTE';
    end if;
end;
$$;

-- R17 (aprobada por Pio): la linea documental (cargo) se explica con exactamente dos albaranes de la
-- MISMA recepcion: el de su numero (exacto o letra final 08X99999A) y uno con numeracion interna de
-- Farmatic ([A-Z]999999/9999); mismo proveedor (R9); cada detalle aplica el PUC de su albaran y la
-- suma cae dentro de la tolerancia por linea (0,05). La linea no tiene otros detalles.
create or replace function public.cf_linea_r17_valida(
    p_factura_id uuid,
    p_linea text,
    p_detalles jsonb,
    p_todos jsonb
)
returns boolean
language plpgsql
stable
set search_path = public
as $$
declare
    e public.facturas_albaranes_extraidos%rowtype;
    a public.albaranes%rowtype;
    b public.albaranes%rowtype;
    v_n integer;
    v_internos integer;
    v_doc text;
    v_op text;
begin
    if p_linea is null or p_linea !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       or jsonb_typeof(p_detalles) <> 'array' or jsonb_array_length(p_detalles) <> 2 then
        return false;
    end if;
    select * into e from public.facturas_albaranes_extraidos where id = p_linea::uuid;
    if e.id is null or e.factura_id <> p_factura_id or e.importe_total is null
       or e.tipo_movimiento is distinct from 'CARGO' then
        return false;
    end if;
    select count(*) into v_n
      from jsonb_array_elements(p_todos) d
     where d->>'factura_albaran_extraido_id' = p_linea;
    if v_n <> 2 then
        return false;
    end if;
    -- Cada detalle: un albaran existente con PUC y el PUC como importe aplicado.
    select count(*), count(*) filter (where upper(btrim(x.numero_albaran)) ~ '^[A-Z][0-9]{6}/[0-9]{4}$')
      into v_n, v_internos
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where x.importe_puc is not null
       and (d->>'importe_aplicado')::numeric = x.importe_puc;
    if v_n <> 2 or v_internos <> 1 then
        return false;
    end if;
    select x.* into a
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where upper(btrim(x.numero_albaran)) !~ '^[A-Z][0-9]{6}/[0-9]{4}$';
    select x.* into b
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where upper(btrim(x.numero_albaran)) ~ '^[A-Z][0-9]{6}/[0-9]{4}$';
    if a.id_contador = b.id_contador or a.farmacia <> b.farmacia
       or a.id_recepcion is null or a.id_recepcion is distinct from b.id_recepcion
       or public.cf_id_proveedor_comparable(a.id_proveedor)
          is distinct from public.cf_id_proveedor_comparable(b.id_proveedor) then
        return false;
    end if;
    -- El albaran de su numero: exacto o letra final (normalizados como en conciliacion.py).
    v_doc := regexp_replace(upper(coalesce(e.numero_albaran, '')), '[^A-Z0-9]', '', 'g');
    v_op := regexp_replace(upper(a.numero_albaran), '[^A-Z0-9]', '', 'g');
    if v_doc = '' or not (v_op = v_doc or (v_op ~ '^08[A-Z][0-9]{5}[A-Z]$' and left(v_op, 8) = v_doc)) then
        return false;
    end if;
    return abs(a.importe_puc + b.importe_puc - e.importe_total) <= 0.0500;
end;
$$;

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
    -- R15 (2BA)
    v_conflicto text;
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
    -- R17 (2BE): una linea UNO_A_VARIOS (dos detalles) cuenta como un albaran casado.
    select count(*) filter (where d->>'tipo_relacion' = 'UNO_A_UNO')
           + count(distinct d->>'factura_albaran_extraido_id')
                 filter (where d->>'tipo_relacion' = 'UNO_A_VARIOS')
      into v_casados
      from jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d;
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

    -- R15 (2BA): un albaran (farmacia, IdContador) solo justifica una linea de una
    -- conciliacion vigente: ni dos lineas de este resultado ni una reserva de otra
    -- factura. Un nuevo intento de la misma factura puede reutilizar sus albaranes.
    select (d->>'albaran_farmacia') || ':' || nullif(d->>'albaran_id_contador', '')::bigint
      into v_conflicto
      from jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d
     where nullif(d->>'albaran_id_contador', '') is not null
     group by d->>'albaran_farmacia', nullif(d->>'albaran_id_contador', '')::bigint
    having count(*) > 1
     limit 1;
    if v_conflicto is not null then
        raise exception 'ALBARAN_YA_CONCILIADO:%', v_conflicto;
    end if;
    select r.albaran_farmacia || ':' || r.albaran_id_contador
      into v_conflicto
      from jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d
      join public.conciliacion_albaranes_reservados r
        on r.albaran_farmacia = d->>'albaran_farmacia'
       and r.albaran_id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where r.factura_id <> f.id
     limit 1;
    if v_conflicto is not null then
        raise exception 'ALBARAN_YA_CONCILIADO:%', v_conflicto;
    end if;
    -- 2BD: un albaran con revision AUSENTE_EN_FARMATIC abierta queda fuera del casado.
    select (d->>'albaran_farmacia') || ':' || nullif(d->>'albaran_id_contador', '')::bigint
      into v_conflicto
      from jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d
     where nullif(d->>'albaran_id_contador', '') is not null
       and public.cf_albaran_ausente_abierto(d->>'albaran_farmacia',
                                             nullif(d->>'albaran_id_contador', '')::bigint)
     limit 1;
    if v_conflicto is not null then
        raise exception 'ALBARAN_AUSENTE_EN_FARMATIC:%', v_conflicto;
    end if;
    -- R17 (2BE): cada linea UNO_A_VARIOS es exactamente una pareja R17, revalidada aqui.
    select coalesce(g.linea, 'SIN_ORIGEN')
      into v_conflicto
      from (select d->>'factura_albaran_extraido_id' as linea, jsonb_agg(d) as detalles
              from jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d
             where d->>'tipo_relacion' = 'UNO_A_VARIOS'
             group by 1) g
     where not public.cf_linea_r17_valida(f.id, g.linea, g.detalles,
                                          coalesce(p_resultado->'detalles', '[]'::jsonb))
     limit 1;
    if v_conflicto is not null then
        raise exception 'LINEA_R17_NO_VALIDA:%', v_conflicto;
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

    -- R15 (2BA): las reservas pasan a la nueva conciliacion vigente. La clave primaria
    -- (farmacia, IdContador) lo garantiza tambien ante escrituras concurrentes.
    delete from public.conciliacion_albaranes_reservados where factura_id = f.id;
    begin
        insert into public.conciliacion_albaranes_reservados
            (albaran_farmacia, albaran_id_contador, factura_id, conciliacion_id, orden)
        select d.albaran_farmacia, d.albaran_id_contador, f.id, v_id, d.orden
          from public.conciliacion_detalles d
         where d.conciliacion_id = v_id and d.albaran_id_contador is not null;
    exception when unique_violation then
        raise exception 'ALBARAN_YA_CONCILIADO';
    end;

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

-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta la RPC.
revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;
-- Auxiliar: solo el propietario (la usa la funcion SECURITY DEFINER).
revoke all on function public.cf_linea_r17_valida(uuid, text, jsonb, jsonb)
    from public, anon, authenticated, service_role;

commit;
