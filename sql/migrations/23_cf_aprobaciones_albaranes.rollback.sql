-- Rollback de la migracion 23 (Hito 2BF): devuelve el esquema exacto de la 22.
-- Solo con confirmacion de Pio. Se pierden las aprobaciones y su historial de aplicacion; los
-- valores ya aplicados en albaranes se conservan.
begin;

-- cf_resincronizar_albaran: texto exacto de la migracion 22.
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

drop function if exists public.cf_aplicar_aprobacion_albaran(bigint, jsonb, text);
drop function if exists public.cf_registrar_aprobacion_albaran(text, bigint, jsonb, text, timestamptz, text, text);
drop function if exists public.cf_revision_albaran_pendiente(bigint);
drop table if exists public.albaranes_aprobaciones_aplicadas;
drop table if exists public.albaranes_aprobaciones;
drop function if exists public.cf_albaranes_aprobaciones_append_only();
drop function if exists public.cf_cambio_identidad_comparable(jsonb);
drop function if exists public.cf_identidad_valor_comparable(text, text);

revoke all on function public.cf_resincronizar_albaran(text, bigint, jsonb, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_resincronizar_albaran(text, bigint, jsonb, text, text)
    to service_role;

commit;
