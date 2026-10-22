-- Migracion 22 (Hito 2BD): resincronizacion de albaranes modificados en Farmatic.
-- Generada por pruebas/auditoria_2bd/generar_migracion_22.py a partir del texto exacto
-- de la 21 (cf_persistir_conciliacion). Columna albaranes.id_recepcion (metadato),
-- historial append-only albaranes_cambios, RPC de actualizacion con revalidacion de la
-- reserva R15 dentro de la transaccion y registro de albaranes ausentes en Farmatic
-- (que quedan fuera del casado). No modifica filas existentes. Idempotente. Requiere la 21.
begin;

do $$
begin
    if to_regclass('public.conciliacion_albaranes_reservados') is null then
        raise exception 'MIGRACION_21_AUSENTE';
    end if;
end;
$$;

-- IdRecepcion de Farmatic (AlbaranRecep por proveedor y numero del albaran). Metadato: no
-- interviene en la conciliacion. Nullable: hay albaranes sin recepcion.
alter table public.albaranes add column if not exists id_recepcion bigint;
comment on column public.albaranes.id_recepcion is
    '2BD: IdRecepcion de Farmatic (AlbaranRecep por proveedor y numero del albaran). Metadato.';

-- Historial append-only de diferencias entre Farmatic y Supabase.albaranes.
create table if not exists public.albaranes_cambios (
    id bigint generated always as identity primary key,
    farmacia text not null,
    id_contador bigint not null,
    detectado_at timestamptz not null default now(),
    origen text not null,
    ejecucion_id text not null,
    campo text not null,
    valor_anterior text,
    valor_nuevo text,
    accion text not null,
    motivo text,
    detalle jsonb not null default '{}'::jsonb,
    constraint albaranes_cambios_origen_check
        check (origen in ('RESYNC_VENTANA', 'CARGA_HISTORICA')),
    constraint albaranes_cambios_accion_check
        check (accion in ('ACTUALIZADO', 'REVISION', 'REVISION_CERRADA'))
);
create index if not exists albaranes_cambios_albaran_idx
    on public.albaranes_cambios (farmacia, id_contador, id);
alter table public.albaranes_cambios enable row level security;
revoke all on table public.albaranes_cambios from public, anon, authenticated, service_role;
grant select on table public.albaranes_cambios to service_role;
revoke all on sequence public.albaranes_cambios_id_seq from public, anon, authenticated, service_role;
comment on table public.albaranes_cambios is
    '2BD: historial append-only de la resincronizacion de albaranes. Escritura solo via cf_resincronizar_albaran y cf_registrar_albaran_ausente.';

create or replace function public.cf_albaranes_cambios_append_only()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    raise exception 'ALBARANES_CAMBIOS_APPEND_ONLY';
end;
$$;

drop trigger if exists albaranes_cambios_append_only on public.albaranes_cambios;
create trigger albaranes_cambios_append_only
    before update or delete on public.albaranes_cambios
    for each row execute function public.cf_albaranes_cambios_append_only();
drop trigger if exists albaranes_cambios_sin_truncate on public.albaranes_cambios;
create trigger albaranes_cambios_sin_truncate
    before truncate on public.albaranes_cambios
    for each statement execute function public.cf_albaranes_cambios_append_only();

-- R9: '2', '0002' y '0002 ' son el mismo proveedor (misma regla que
-- conciliacion._id_proveedor_comparable). Solo para comparar.
create or replace function public.cf_id_proveedor_comparable(p_valor text)
returns text
language sql
immutable
set search_path = public
as $$
    select case
        when p_valor is null then null
        when btrim(p_valor) ~ '^[0-9]+$' then coalesce(nullif(ltrim(btrim(p_valor), '0'), ''), '0')
        else nullif(btrim(p_valor), '')
    end
$$;

-- Revision AUSENTE_EN_FARMATIC abierta: el ultimo evento de presencia del albaran es AUSENTE.
create or replace function public.cf_albaran_ausente_abierto(p_farmacia text, p_id_contador bigint)
returns boolean
language sql
stable
set search_path = public
as $$
    select coalesce((
        select c.valor_nuevo = 'AUSENTE'
          from public.albaranes_cambios c
         where c.farmacia = p_farmacia and c.id_contador = p_id_contador and c.campo = 'presencia'
         order by c.id desc
         limit 1
    ), false)
$$;

-- Actualiza un albaran ya sincronizado con los valores actuales de Farmatic.
-- Identidad (numero, proveedor normalizado) distinta -> REVISION, nada se actualiza.
-- Campos de conciliacion distintos y albaran reservado por una conciliacion vigente (R15,
-- releido aqui) -> REVISION, no se actualizan. Sin reserva -> se actualizan. El metadato
-- id_recepcion se actualiza siempre que la identidad coincida. Idempotente: una revision
-- identica no se vuelve a registrar; sin diferencias no escribe nada.
create or replace function public.cf_resincronizar_albaran(
    p_farmacia text,
    p_id_contador bigint,
    p_valores jsonb,
    p_origen text,
    p_ejecucion_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    a public.albaranes%rowtype;
    v_identidad jsonb;
    v_cambios jsonb;
    v_meta jsonb;
    v_reserva text;
    v_cerrada boolean := false;
    v_item jsonb;
    v_motivo text;
    v_accion text;
begin
    if p_origen is null or p_origen not in ('RESYNC_VENTANA', 'CARGA_HISTORICA') then
        raise exception 'ORIGEN_NO_ADMITIDO';
    end if;
    if nullif(btrim(p_ejecucion_id), '') is null then
        raise exception 'EJECUCION_ID_OBLIGATORIO';
    end if;
    if p_valores is null or jsonb_typeof(p_valores) <> 'object'
       or not (p_valores ?& array['id_proveedor', 'proveedor', 'numero_albaran', 'fecha',
                                  'importe_pvp', 'importe_puc', 'descuento']) then
        raise exception 'VALORES_INCOMPLETOS';
    end if;
    if not exists (select 1 from public.cf_configuracion c
                    where c.id and p_farmacia = any(c.farmacias_habilitadas)) then
        raise exception 'FARMACIA_NO_HABILITADA';
    end if;

    select * into a from public.albaranes
     where farmacia = p_farmacia and id_contador = p_id_contador
     for update;
    if not found then
        raise exception 'ALBARAN_NO_EXISTE:%:%', p_farmacia, p_id_contador;
    end if;

    -- Presente en Farmatic: se cierra una revision AUSENTE abierta.
    if public.cf_albaran_ausente_abierto(p_farmacia, p_id_contador) then
        insert into public.albaranes_cambios
            (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion, motivo)
        values (p_farmacia, p_id_contador, p_origen, p_ejecucion_id, 'presencia', 'AUSENTE', 'PRESENTE',
                'REVISION_CERRADA', 'PRESENTE_EN_FARMATIC');
        v_cerrada := true;
    end if;

    select coalesce(jsonb_agg(jsonb_build_object('campo', x.campo, 'anterior', x.anterior, 'nuevo', x.nuevo)
                              order by x.orden), '[]'::jsonb)
      into v_identidad
      from (values
          (1, 'numero_albaran', a.numero_albaran, btrim(p_valores->>'numero_albaran'),
           btrim(a.numero_albaran) is distinct from btrim(p_valores->>'numero_albaran')),
          (2, 'id_proveedor', a.id_proveedor, p_valores->>'id_proveedor',
           public.cf_id_proveedor_comparable(a.id_proveedor)
               is distinct from public.cf_id_proveedor_comparable(p_valores->>'id_proveedor'))
      ) x(orden, campo, anterior, nuevo, distinto)
     where x.distinto;

    if jsonb_array_length(v_identidad) > 0 then
        for v_item in select * from jsonb_array_elements(v_identidad) loop
            if not exists (
                select 1 from public.albaranes_cambios c
                 where c.farmacia = p_farmacia and c.id_contador = p_id_contador
                   and c.campo = v_item->>'campo' and c.accion = 'REVISION' and c.motivo = 'CAMBIO_IDENTIDAD'
                   and c.valor_anterior is not distinct from v_item->>'anterior'
                   and c.valor_nuevo is not distinct from v_item->>'nuevo'
            ) then
                insert into public.albaranes_cambios
                    (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion, motivo)
                values (p_farmacia, p_id_contador, p_origen, p_ejecucion_id, v_item->>'campo',
                        v_item->>'anterior', v_item->>'nuevo', 'REVISION', 'CAMBIO_IDENTIDAD');
            end if;
        end loop;
        return jsonb_build_object('accion', 'REVISION', 'motivo', 'CAMBIO_IDENTIDAD',
                                  'campos', v_identidad, 'revision_cerrada', v_cerrada);
    end if;

    select coalesce(jsonb_agg(jsonb_build_object('campo', x.campo, 'anterior', x.anterior, 'nuevo', x.nuevo)
                              order by x.orden), '[]'::jsonb)
      into v_cambios
      from (values
          (1, 'fecha', a.fecha::text, (p_valores->>'fecha')::date::text),
          (2, 'importe_puc', a.importe_puc::text, round((p_valores->>'importe_puc')::numeric, 2)::text),
          (3, 'importe_pvp', a.importe_pvp::text, round((p_valores->>'importe_pvp')::numeric, 2)::text),
          (4, 'descuento', a.descuento::text, round((p_valores->>'descuento')::numeric, 2)::text),
          (5, 'proveedor', a.proveedor, btrim(p_valores->>'proveedor'))
      ) x(orden, campo, anterior, nuevo)
     where x.anterior is distinct from x.nuevo;

    select coalesce(jsonb_agg(jsonb_build_object('campo', 'id_recepcion', 'anterior', a.id_recepcion::text,
                                                 'nuevo', nullif(p_valores->>'id_recepcion', '')::bigint::text)),
                    '[]'::jsonb)
      into v_meta
     where p_valores ? 'id_recepcion'
       and a.id_recepcion is distinct from nullif(p_valores->>'id_recepcion', '')::bigint;

    v_accion := 'SIN_CAMBIOS';
    if jsonb_array_length(v_cambios) > 0 then
        select f.numero_factura into v_reserva
          from public.conciliacion_albaranes_reservados r
          join public.facturas f on f.id = r.factura_id
         where r.albaran_farmacia = p_farmacia and r.albaran_id_contador = p_id_contador;
        if v_reserva is not null then
            v_motivo := 'RESERVADO:' || v_reserva;
            v_accion := 'REVISION';
            for v_item in select * from jsonb_array_elements(v_cambios) loop
                if not exists (
                    select 1 from public.albaranes_cambios c
                     where c.farmacia = p_farmacia and c.id_contador = p_id_contador
                       and c.campo = v_item->>'campo' and c.accion = 'REVISION' and c.motivo = v_motivo
                       and c.valor_anterior is not distinct from v_item->>'anterior'
                       and c.valor_nuevo is not distinct from v_item->>'nuevo'
                ) then
                    insert into public.albaranes_cambios
                        (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion, motivo)
                    values (p_farmacia, p_id_contador, p_origen, p_ejecucion_id, v_item->>'campo',
                            v_item->>'anterior', v_item->>'nuevo', 'REVISION', v_motivo);
                end if;
            end loop;
        else
            v_accion := 'ACTUALIZADO';
            update public.albaranes
               set fecha = (p_valores->>'fecha')::date,
                   importe_puc = round((p_valores->>'importe_puc')::numeric, 2),
                   importe_pvp = round((p_valores->>'importe_pvp')::numeric, 2),
                   descuento = round((p_valores->>'descuento')::numeric, 2),
                   proveedor = btrim(p_valores->>'proveedor'),
                   fecha_actualizacion = now()
             where farmacia = p_farmacia and id_contador = p_id_contador;
            insert into public.albaranes_cambios
                (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion)
            select p_farmacia, p_id_contador, p_origen, p_ejecucion_id, x->>'campo', x->>'anterior', x->>'nuevo',
                   'ACTUALIZADO'
              from jsonb_array_elements(v_cambios) x;
        end if;
    end if;

    if jsonb_array_length(v_meta) > 0 then
        update public.albaranes
           set id_recepcion = nullif(p_valores->>'id_recepcion', '')::bigint,
               fecha_actualizacion = now()
         where farmacia = p_farmacia and id_contador = p_id_contador;
        insert into public.albaranes_cambios
            (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion)
        select p_farmacia, p_id_contador, p_origen, p_ejecucion_id, x->>'campo', x->>'anterior', x->>'nuevo',
               'ACTUALIZADO'
          from jsonb_array_elements(v_meta) x;
        if v_accion = 'SIN_CAMBIOS' then
            v_accion := 'ACTUALIZADO';
        end if;
    end if;

    return jsonb_build_object('accion', v_accion, 'motivo', v_motivo, 'campos', v_cambios,
                              'metadatos', v_meta, 'revision_cerrada', v_cerrada);
end;
$$;

-- Albaran de Supabase que ya no existe en Farmatic: nunca se borra ni se modifica; queda
-- una revision AUSENTE_EN_FARMATIC (una sola vez mientras siga ausente) y sale del casado.
create or replace function public.cf_registrar_albaran_ausente(
    p_farmacia text,
    p_id_contador bigint,
    p_origen text,
    p_ejecucion_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_reserva text;
begin
    if p_origen is null or p_origen not in ('RESYNC_VENTANA', 'CARGA_HISTORICA') then
        raise exception 'ORIGEN_NO_ADMITIDO';
    end if;
    if nullif(btrim(p_ejecucion_id), '') is null then
        raise exception 'EJECUCION_ID_OBLIGATORIO';
    end if;
    if not exists (select 1 from public.cf_configuracion c
                    where c.id and p_farmacia = any(c.farmacias_habilitadas)) then
        raise exception 'FARMACIA_NO_HABILITADA';
    end if;
    perform 1 from public.albaranes
     where farmacia = p_farmacia and id_contador = p_id_contador
     for update;
    if not found then
        raise exception 'ALBARAN_NO_EXISTE:%:%', p_farmacia, p_id_contador;
    end if;
    if public.cf_albaran_ausente_abierto(p_farmacia, p_id_contador) then
        return jsonb_build_object('accion', 'YA_REGISTRADA', 'motivo', 'AUSENTE_EN_FARMATIC');
    end if;
    select f.numero_factura into v_reserva
      from public.conciliacion_albaranes_reservados r
      join public.facturas f on f.id = r.factura_id
     where r.albaran_farmacia = p_farmacia and r.albaran_id_contador = p_id_contador;
    insert into public.albaranes_cambios
        (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion, motivo, detalle)
    values (p_farmacia, p_id_contador, p_origen, p_ejecucion_id, 'presencia', 'PRESENTE', 'AUSENTE',
            'REVISION', 'AUSENTE_EN_FARMATIC', jsonb_build_object('reservado_por', v_reserva));
    return jsonb_build_object('accion', 'REVISION', 'motivo', 'AUSENTE_EN_FARMATIC', 'reservado_por', v_reserva);
end;
$$;

-- Cierre atomico de la 21 con el rechazo de albaranes ausentes en Farmatic.
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

-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta las RPC.
revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_resincronizar_albaran(text, bigint, jsonb, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_resincronizar_albaran(text, bigint, jsonb, text, text)
    to service_role;
revoke all on function public.cf_registrar_albaran_ausente(text, bigint, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_registrar_albaran_ausente(text, bigint, text, text)
    to service_role;
-- Auxiliares: solo el propietario (las usan las funciones SECURITY DEFINER).
revoke all on function public.cf_albaran_ausente_abierto(text, bigint)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_id_proveedor_comparable(text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_albaranes_cambios_append_only()
    from public, anon, authenticated, service_role;

commit;
