begin;

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
    v_tolerancia numeric := 0.0500;
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

revoke all on function public.cf_evaluar_elegibilidad_conciliacion(uuid)
    from public, anon, authenticated;
grant execute on function public.cf_evaluar_elegibilidad_conciliacion(uuid)
    to service_role;

alter table public.conciliacion_detalles
    drop constraint if exists conciliacion_detalles_origen_check;
alter table public.conciliacion_detalles
    add constraint conciliacion_detalles_origen_check
    check (
        num_nonnulls(factura_albaran_extraido_id, factura_movimiento_id) >= 1
        or tipo_relacion = 'SIN_COINCIDENCIA'
        or (
            tipo_relacion = 'MOVIMIENTO_NO_FARMATIC'
            and provenance->>'fuente' = 'FISCALIDAD_AJUSTE_DOCUMENTAL'
        )
    );

create or replace function public.cf_reclamar_factura_conciliacion(
    p_worker_id text,
    p_bloqueo_segundos integer default 300
)
returns setof public.facturas
language plpgsql
security definer
set search_path = public
as $$
declare
    v_id uuid;
begin
    if p_worker_id is null or btrim(p_worker_id) = '' then
        raise exception 'worker_id obligatorio';
    end if;

    select f.id
      into v_id
      from public.facturas f
      cross join public.cf_configuracion c
      cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e
     where c.id = true
       and f.farmacia = any(c.farmacias_habilitadas)
       and (c.conciliacion_automatica or f.conciliacion_reintento_solicitado_at is not null)
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
end;
$$;

revoke all on function public.cf_reclamar_factura_conciliacion(text, integer)
    from public, anon, authenticated;
grant execute on function public.cf_reclamar_factura_conciliacion(text, integer)
    to service_role;

commit;
