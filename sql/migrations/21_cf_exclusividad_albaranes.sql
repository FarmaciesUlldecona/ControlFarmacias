-- Migracion 21 (Hito 2BA): R15 exclusividad de albaranes y R16 elegibilidad con
-- tolerancia proporcional. Generada por pruebas/auditoria_2ba/generar_migracion_21.py
-- a partir del texto exacto de la 20 (cf_persistir_conciliacion) y de la 14
-- (cf_evaluar_elegibilidad_conciliacion). No toca selector, ordering, normalizacion ni
-- filas existentes: el unico DML es la carga de la tabla nueva desde las conciliaciones
-- vigentes. Idempotente. Requiere la migracion 20.
begin;

do $$
begin
    if not exists (
        select 1 from information_schema.columns
         where table_schema = 'public' and table_name = 'cf_configuracion'
           and column_name = 'conciliacion_tolerancia_tope'
    ) then
        raise exception 'MIGRACION_20_AUSENTE';
    end if;
end;
$$;

-- R15: un albaran de Farmatic (farmacia, IdContador) solo puede estar reservado por una
-- linea de una conciliacion vigente. Solo escribe cf_persistir_conciliacion.
create table if not exists public.conciliacion_albaranes_reservados (
    albaran_farmacia text not null,
    albaran_id_contador bigint not null,
    factura_id uuid not null references public.facturas(id),
    conciliacion_id uuid not null references public.conciliaciones(id),
    orden integer not null,
    reservado_at timestamptz not null default now(),
    constraint conciliacion_albaranes_reservados_pkey
        primary key (albaran_farmacia, albaran_id_contador)
);
create index if not exists conciliacion_albaranes_reservados_factura_idx
    on public.conciliacion_albaranes_reservados (factura_id);
alter table public.conciliacion_albaranes_reservados enable row level security;
revoke all on table public.conciliacion_albaranes_reservados
    from public, anon, authenticated, service_role;
grant select on table public.conciliacion_albaranes_reservados to service_role;
comment on table public.conciliacion_albaranes_reservados is
    'R15 (2BA): albaranes de Farmatic que justifican una linea de una conciliacion vigente. Escritura solo via cf_persistir_conciliacion.';

-- Carga inicial desde las conciliaciones vigentes. Si dos lineas vigentes comparten
-- albaran, la clave primaria aborta la migracion (falla cerrado).
insert into public.conciliacion_albaranes_reservados
    (albaran_farmacia, albaran_id_contador, factura_id, conciliacion_id, orden)
select d.albaran_farmacia, d.albaran_id_contador, c.factura_id, c.id, d.orden
  from public.conciliaciones c
  join public.conciliacion_detalles d on d.conciliacion_id = c.id
 where c.es_actual and d.albaran_id_contador is not null
   and not exists (
       select 1 from public.conciliacion_albaranes_reservados r
        where r.conciliacion_id = c.id and r.orden = d.orden
   );

-- R15: cierre atomico de la 20 con validacion y mantenimiento de reservas.
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

-- R16: elegibilidad con tolerancia proporcional.
create or replace function public.cf_evaluar_elegibilidad_conciliacion(
    p_factura_id uuid
)
returns table (estado text, razon text)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
    v_factura public.facturas%rowtype;
    v_resultado jsonb;
    v_tipo text;
    v_nif text;
    v_nombre text;
    v_tiene_identidad boolean;
    v_albaranes integer;
    v_albaranes_total numeric;
    v_movimientos integer;
    v_movimientos_incompletos integer;
    v_movimientos_con_importe integer;
    v_movimientos_con_base integer;
    v_movimientos_importe numeric;
    v_movimientos_base numeric;
    v_fiscalidad_coherente boolean;
    v_traza_servicio boolean;
    v_total_explicado boolean;
    v_tolerancia numeric;
begin
    select f.*
      into v_factura
      from public.facturas f
     where f.id = p_factura_id;

    select n.resultado_json
      into v_resultado
      from public.normalizacion_ejecuciones n
     where n.id = v_factura.normalizacion_ejecucion_id;

    if v_factura.id is null then
        return query select 'NO_APTA', 'NORMALIZACION_NO_VALIDA';
        return;
    end if;
    if coalesce((v_resultado->>'documento_completo_demostrado')::boolean, false) is not true then
        return query select 'NO_APTA', 'DOCUMENTO_INCOMPLETO';
        return;
    end if;

    v_nif := regexp_replace(upper(coalesce(v_factura.datos_extraidos #>> '{destinatario,nif,valor}', '')), '[^A-Z0-9]', '', 'g');
    v_nombre := translate(upper(coalesce(v_factura.datos_extraidos #>> '{destinatario,nombre,valor}', '')), 'ÁÉÍÓÚÜÑ', 'AEIOUUN');
    v_tiene_identidad :=
        jsonb_array_length(coalesce(v_factura.datos_extraidos #> '{destinatario,nif,evidencia}', '[]'::jsonb)) > 0
        or jsonb_array_length(coalesce(v_factura.datos_extraidos #> '{destinatario,nombre,evidencia}', '[]'::jsonb)) > 0;
    if not v_tiene_identidad then
        return query select 'NO_APTA', 'FARMACIA_NO_DEMOSTRABLE';
        return;
    end if;
    if not (
        v_factura.farmacia = 'PIO'
        and (v_nif = '40901058C' or (v_nif = '' and v_nombre like '%PUIG SALOM%PIO%'))
    ) then
        return query select 'NO_APTA', 'FARMACIA_NO_CONSISTENTE';
        return;
    end if;
    if v_factura.estado_normalizacion <> 'NORMALIZADA' then
        return query select 'NO_APTA', 'NORMALIZACION_NO_VALIDA';
        return;
    end if;
    if exists (
        select 1 from public.facturas_incidencias i
         where i.factura_id = v_factura.id and i.estado = 'ABIERTA' and i.bloqueante
    ) then
        return query select 'NO_APTA', 'INCIDENCIA_BLOQUEANTE';
        return;
    end if;

    v_tipo := case v_factura.datos_extraidos->>'naturaleza_principal'
        when 'MERCANCIA' then 'FACTURA_MERCANCIA'
        when 'SERVICIOS' then 'FACTURA_GASTO_SERVICIO'
        when 'MIXTA' then 'FACTURA_MIXTA'
        when 'FACTURA_MERCANCIA' then 'FACTURA_MERCANCIA'
        when 'FACTURA_GASTO_SERVICIO' then 'FACTURA_GASTO_SERVICIO'
        when 'FACTURA_MIXTA' then 'FACTURA_MIXTA'
        else 'TIPO_NO_DEMOSTRADO'
    end;
    if v_tipo = 'TIPO_NO_DEMOSTRADO' then
        return query select 'REQUIERE_REVISION', 'TIPO_DOCUMENTAL_NO_DEMOSTRADO';
        return;
    end if;
    if v_factura.importe_total is null then
        return query select 'NO_APTA', 'TOTAL_NO_DEMOSTRADO';
        return;
    end if;

    select count(*), coalesce(sum(
               case when a.tipo_movimiento = 'ABONO' then -abs(a.importe_total)
                    else abs(a.importe_total) end
           ), 0)
      into v_albaranes, v_albaranes_total
      from public.facturas_albaranes_extraidos a
     where a.factura_id = v_factura.id and a.importe_total is not null;

    select count(*),
           count(*) filter (where nullif(btrim(m.descripcion_literal), '') is null
                              or m.sentido is null
                              or (m.importe is null and m.base is null)),
           count(m.importe), count(m.base),
           coalesce(sum(case when m.sentido = 'ABONO' then -abs(m.importe) else abs(m.importe) end), 0),
           coalesce(sum(case when m.sentido = 'ABONO' then -abs(m.base) else abs(m.base) end), 0)
      into v_movimientos, v_movimientos_incompletos,
           v_movimientos_con_importe, v_movimientos_con_base,
           v_movimientos_importe, v_movimientos_base
      from public.facturas_movimientos m
     where m.factura_id = v_factura.id;

    -- R16 (2BA): la misma tolerancia proporcional de R11 con n = lineas sumadas
    -- (albaranes con importe + movimientos), en todas las comparaciones.
    select greatest(c.conciliacion_tolerancia_suelo,
                    least(c.conciliacion_tolerancia_por_albaran * (v_albaranes + v_movimientos),
                          c.conciliacion_tolerancia_tope))
      into v_tolerancia
      from public.cf_configuracion c
     where c.id = true;
    if v_tolerancia is null then
        raise exception 'TOLERANCIA_R16_NO_DISPONIBLE';
    end if;

    v_fiscalidad_coherente :=
        v_factura.base_imponible_total is not null
        and abs(
            v_factura.importe_total
            - (v_factura.base_imponible_total
               + coalesce(v_factura.iva_total, 0)
               + coalesce(v_factura.recargo_equivalencia_total, 0)
               + coalesce(nullif(v_factura.datos_extraidos #>> '{totales,otros,valor}', '')::numeric, 0))
        ) <= v_tolerancia;

    if v_tipo = 'FACTURA_MERCANCIA' then
        if v_albaranes > 0 then
            return query select 'APTA', 'APTA_MERCANCIA';
        else
            return query select 'NO_APTA', 'FALTAN_ALBARANES_MERCANCIA';
        end if;
        return;
    end if;

    v_traza_servicio := v_movimientos > 0 and v_movimientos_incompletos = 0;
    if v_tipo = 'FACTURA_GASTO_SERVICIO' then
        v_total_explicado :=
            (v_movimientos_con_importe = v_movimientos
             and abs(v_factura.importe_total - v_movimientos_importe) <= v_tolerancia)
            or
            (v_movimientos_con_importe = 0
             and v_movimientos_con_base = v_movimientos
             and v_factura.base_imponible_total is not null
             and abs(v_factura.base_imponible_total - v_movimientos_base) <= v_tolerancia
             and v_fiscalidad_coherente);
        if not v_traza_servicio then
            return query select 'NO_APTA', 'TRAZABILIDAD_SERVICIO_INSUFICIENTE';
        elsif not v_fiscalidad_coherente then
            return query select 'NO_APTA', 'FISCALIDAD_INCOHERENTE';
        elsif not v_total_explicado then
            return query select 'NO_APTA', 'TOTAL_NO_EXPLICADO';
        else
            return query select 'APTA', 'APTA_GASTO_SERVICIO';
        end if;
        return;
    end if;

    if v_albaranes = 0 then
        return query select 'NO_APTA', 'FALTAN_ALBARANES_MERCANCIA';
    elsif not v_traza_servicio or v_movimientos_con_importe <> v_movimientos then
        return query select 'NO_APTA', 'TRAZABILIDAD_SERVICIO_INSUFICIENTE';
    elsif not v_fiscalidad_coherente then
        return query select 'NO_APTA', 'FISCALIDAD_INCOHERENTE';
    elsif abs(v_factura.importe_total - (v_albaranes_total + v_movimientos_importe)) > v_tolerancia then
        return query select 'NO_APTA', 'TOTAL_NO_EXPLICADO';
    else
        return query select 'APTA', 'APTA_MIXTA';
    end if;
end;
$$;

-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta.
revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_evaluar_elegibilidad_conciliacion(uuid)
    from public, anon, authenticated;
grant execute on function public.cf_evaluar_elegibilidad_conciliacion(uuid)
    to service_role;

commit;
