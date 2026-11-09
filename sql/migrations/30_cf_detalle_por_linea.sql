-- Migracion 30 (Hito 2BR): detalle por linea en la conciliacion.
-- Generada por pruebas/auditoria_2br/generar_migracion_30.py a partir del texto exacto de la 24
-- (cf_persistir_conciliacion; las 25-29 no lo cambian). Cada detalle guarda el importe del PDF, el importe de
-- Farmatic, la diferencia y el estado de SU LINEA (antes: NULL y el estado de la factura). Los calcula la BD con
-- cf_detalles_por_linea; si el resultado los trae, deben coincidir (DETALLE_LINEA_NO_COINCIDE). El resultado de
-- la factura no cambia. Rellena una sola vez los detalles existentes con la misma funcion y guarda los valores
-- previos para el rollback. No toca facturas, conciliaciones, reservas ni historial. Idempotente. Requiere la 29.
begin;

do $$
begin
    if not exists (select 1 from pg_policy where polrelid = 'public.albaranes'::regclass
                                             and polname = 'albaranes_lectura_select') then
        raise exception 'MIGRACION_29_AUSENTE';
    end if;
end;
$$;

-- Detalle por linea (2BR, decision de diseno del hito; tolerancia por linea 0,05, la misma con la que casa una
-- linea y la de R17):
--   albaran casado (1:1 o R17): PDF = importe de la linea con signo (ABONO en negativo); Farmatic = importe
--     aplicado del albaran; diferencia = PDF - suma de los albaranes de la linea (en R17, en los dos detalles);
--     COINCIDE si |diferencia| <= 0,05, si no DIFERENCIA;
--   linea sin coincidencia: PDF = importe de la linea, sin Farmatic, diferencia = PDF, DIFERENCIA;
--   linea sin importe documental (o de otra factura): NO_EVALUABLE, sin diferencia;
--   movimiento o ajuste documental: PDF = importe aplicado, sin contraparte en Farmatic, NO_EVALUABLE.

create or replace function public.cf_detalles_por_linea(
    p_factura_id uuid,
    p_detalles jsonb
)
returns table (
    orden integer,
    importe_documental numeric,
    importe_farmatic numeric,
    diferencia numeric,
    estado text
)
language sql
stable
set search_path = public
as $$
    with d as (
        select (x->>'orden')::integer as orden,
               x->>'tipo_relacion' as tipo,
               nullif(x->>'factura_albaran_extraido_id', '')::uuid as linea,
               round((x->>'importe_aplicado')::numeric, 4) as aplicado
          from jsonb_array_elements(coalesce(p_detalles, '[]'::jsonb)) x
    ), l as (
        select d.orden, d.tipo, d.aplicado,
               case when d.tipo = 'MOVIMIENTO_NO_FARMATIC' or e.importe_total is null then null
                    when e.tipo_movimiento = 'ABONO' then -abs(round(e.importe_total, 4))
                    else round(e.importe_total, 4) end as documental,
               sum(d.aplicado) filter (where d.tipo in ('UNO_A_UNO', 'UNO_A_VARIOS', 'VARIOS_A_UNO'))
                   over (partition by d.linea) as suma_linea
          from d
          left join public.facturas_albaranes_extraidos e
            on e.id = d.linea and e.factura_id = p_factura_id
    )
    select l.orden,
           case when l.tipo = 'MOVIMIENTO_NO_FARMATIC' then l.aplicado else l.documental end,
           case when l.tipo in ('MOVIMIENTO_NO_FARMATIC', 'SIN_COINCIDENCIA') then null else l.aplicado end,
           case when l.tipo = 'MOVIMIENTO_NO_FARMATIC' or l.documental is null then null
                when l.tipo = 'SIN_COINCIDENCIA' then l.documental
                else l.documental - l.suma_linea end,
           case when l.tipo = 'MOVIMIENTO_NO_FARMATIC' or l.documental is null then 'NO_EVALUABLE'
                when l.tipo = 'SIN_COINCIDENCIA' then 'DIFERENCIA'
                when abs(l.documental - l.suma_linea) <= 0.0500 then 'COINCIDE'
                else 'DIFERENCIA' end
      from l
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
    -- 2BR (30): detalle por linea
    v_detalles jsonb := coalesce(p_resultado->'detalles', '[]'::jsonb);
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
    -- 2BR (30): los valores por linea los calcula la BD; si el resultado los trae, deben coincidir.
    select coalesce(d->>'orden', 'SIN_ORDEN')
      into v_conflicto
      from jsonb_array_elements(v_detalles) d
      left join public.cf_detalles_por_linea(f.id, v_detalles) v
        on v.orden = (d->>'orden')::integer
     where d ? 'importe_documental'
       and ((d->>'importe_documental')::numeric is distinct from v.importe_documental
         or (d->>'importe_farmatic')::numeric is distinct from v.importe_farmatic
         or (d->>'diferencia')::numeric is distinct from v.diferencia
         or d->>'estado' is distinct from v.estado)
     limit 1;
    if v_conflicto is not null then
        raise exception 'DETALLE_LINEA_NO_COINCIDE:%', v_conflicto;
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
        tipo_relacion, importe_documental, importe_farmatic, importe_aplicado, diferencia, estado,
        provenance
    )
    select v_id,
           (d->>'orden')::integer,
           nullif(d->>'factura_albaran_extraido_id', '')::uuid,
           nullif(d->>'factura_movimiento_id', '')::uuid,
           d->>'albaran_farmacia',
           nullif(d->>'albaran_id_contador', '')::bigint,
           coalesce((d->>'coincidencia_numero_literal')::boolean, false),
           d->>'tipo_relacion',
           v.importe_documental,
           v.importe_farmatic,
           (d->>'importe_aplicado')::numeric,
           v.diferencia,
           v.estado,
           coalesce(d->'provenance', '{}'::jsonb)
      from jsonb_array_elements(v_detalles) d
      left join public.cf_detalles_por_linea(f.id, v_detalles) v
        on v.orden = (d->>'orden')::integer;

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

-- Relleno de los detalles existentes (una sola vez: si la tabla de valores previos ya existe, no se repite).
do $$
begin
    if to_regclass('public.conciliacion_detalles_previo_30') is null then
        create table public.conciliacion_detalles_previo_30 (
            detalle_id uuid primary key references public.conciliacion_detalles(id) on delete cascade,
            importe_documental numeric(14,4),
            importe_farmatic numeric(14,4),
            diferencia numeric(14,4),
            estado text not null
        );
        insert into public.conciliacion_detalles_previo_30 (detalle_id, importe_documental, importe_farmatic, diferencia, estado)
        select id, importe_documental, importe_farmatic, diferencia, estado
          from public.conciliacion_detalles;
        update public.conciliacion_detalles d
           set importe_documental = v.importe_documental,
               importe_farmatic = v.importe_farmatic,
               diferencia = v.diferencia,
               estado = v.estado
          from (select c.id as conciliacion_id, l.*
                  from public.conciliaciones c
                  cross join lateral public.cf_detalles_por_linea(
                      c.factura_id,
                      (select coalesce(jsonb_agg(jsonb_build_object(
                                  'orden', x.orden,
                                  'tipo_relacion', x.tipo_relacion,
                                  'factura_albaran_extraido_id', x.factura_albaran_extraido_id,
                                  'importe_aplicado', x.importe_aplicado)), '[]'::jsonb)
                         from public.conciliacion_detalles x
                        where x.conciliacion_id = c.id)) l) v
         where d.conciliacion_id = v.conciliacion_id
           and d.orden = v.orden;
    end if;
end;
$$;

comment on table public.conciliacion_detalles_previo_30 is
    'Migracion 30 (2BR): valores por detalle anteriores al relleno, solo para el rollback de la 30.';
alter table public.conciliacion_detalles_previo_30 enable row level security;

-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta la RPC.
revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;
-- Auxiliar y valores previos: solo el propietario.
revoke all on function public.cf_detalles_por_linea(uuid, jsonb)
    from public, anon, authenticated, service_role;
revoke all on table public.conciliacion_detalles_previo_30
    from public, anon, authenticated, service_role;

commit;
