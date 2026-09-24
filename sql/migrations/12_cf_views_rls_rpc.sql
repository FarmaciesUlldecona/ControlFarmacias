begin;

alter table public.documentos_facturas enable row level security;
alter table public.facturas enable row level security;
alter table public.facturas_vencimientos enable row level security;
alter table public.facturas_impuestos enable row level security;
alter table public.facturas_albaranes_extraidos enable row level security;
alter table public.facturas_ajustes enable row level security;
alter table public.proveedores enable row level security;
alter table public.proveedores_alias enable row level security;
alter table public.cf_configuracion enable row level security;
alter table public.normalizacion_ejecuciones enable row level security;
alter table public.facturas_movimientos enable row level security;
alter table public.facturas_incidencias enable row level security;
alter table public.historial_facturas enable row level security;
alter table public.conciliaciones enable row level security;
alter table public.conciliacion_detalles enable row level security;

revoke all on table public.proveedores from anon, authenticated;
revoke all on table public.proveedores_alias from anon, authenticated;
revoke all on table public.cf_configuracion from anon, authenticated;
revoke all on table public.normalizacion_ejecuciones from anon, authenticated;
revoke all on table public.facturas_movimientos from anon, authenticated;
revoke all on table public.facturas_incidencias from anon, authenticated;
revoke all on table public.historial_facturas from anon, authenticated;
revoke all on table public.conciliaciones from anon, authenticated;
revoke all on table public.conciliacion_detalles from anon, authenticated;
revoke all on table public.documentos_facturas from anon, authenticated;
revoke all on table public.facturas from anon, authenticated;
revoke all on table public.facturas_vencimientos from anon, authenticated;
revoke all on table public.facturas_impuestos from anon, authenticated;
revoke all on table public.facturas_albaranes_extraidos from anon, authenticated;
revoke all on table public.facturas_ajustes from anon, authenticated;

grant select on table public.proveedores to authenticated;
grant select on table public.proveedores_alias to authenticated;
grant select on table public.cf_configuracion to authenticated;
grant select on table public.normalizacion_ejecuciones to authenticated;
grant select on table public.facturas_movimientos to authenticated;
grant select on table public.facturas_incidencias to authenticated;
grant select on table public.historial_facturas to authenticated;
grant select on table public.conciliaciones to authenticated;
grant select on table public.conciliacion_detalles to authenticated;
grant select on table public.documentos_facturas to authenticated;
grant select on table public.facturas to authenticated;
grant select on table public.facturas_vencimientos to authenticated;
grant select on table public.facturas_impuestos to authenticated;
grant select on table public.facturas_albaranes_extraidos to authenticated;
grant select on table public.facturas_ajustes to authenticated;

drop policy if exists documentos_facturas_authenticated_select on public.documentos_facturas;
create policy documentos_facturas_authenticated_select
    on public.documentos_facturas for select to authenticated
    using (exists (
        select 1 from public.cf_configuracion c
        where c.id = true and documentos_facturas.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists facturas_authenticated_select on public.facturas;
create policy facturas_authenticated_select
    on public.facturas for select to authenticated
    using (exists (
        select 1 from public.cf_configuracion c
        where c.id = true and facturas.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists facturas_vencimientos_authenticated_select on public.facturas_vencimientos;
create policy facturas_vencimientos_authenticated_select
    on public.facturas_vencimientos for select to authenticated
    using (exists (
        select 1 from public.facturas f join public.cf_configuracion c on c.id = true
        where f.id = facturas_vencimientos.factura_id
          and f.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists facturas_impuestos_authenticated_select on public.facturas_impuestos;
create policy facturas_impuestos_authenticated_select
    on public.facturas_impuestos for select to authenticated
    using (exists (
        select 1 from public.facturas f join public.cf_configuracion c on c.id = true
        where f.id = facturas_impuestos.factura_id
          and f.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists facturas_albaranes_extraidos_authenticated_select on public.facturas_albaranes_extraidos;
create policy facturas_albaranes_extraidos_authenticated_select
    on public.facturas_albaranes_extraidos for select to authenticated
    using (exists (
        select 1 from public.facturas f join public.cf_configuracion c on c.id = true
        where f.id = facturas_albaranes_extraidos.factura_id
          and f.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists facturas_ajustes_authenticated_select on public.facturas_ajustes;
create policy facturas_ajustes_authenticated_select
    on public.facturas_ajustes for select to authenticated
    using (exists (
        select 1 from public.facturas f join public.cf_configuracion c on c.id = true
        where f.id = facturas_ajustes.factura_id
          and f.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists proveedores_authenticated_select on public.proveedores;
create policy proveedores_authenticated_select
    on public.proveedores for select to authenticated using (true);

drop policy if exists proveedores_alias_authenticated_select on public.proveedores_alias;
create policy proveedores_alias_authenticated_select
    on public.proveedores_alias for select to authenticated using (true);

drop policy if exists cf_configuracion_authenticated_select on public.cf_configuracion;
create policy cf_configuracion_authenticated_select
    on public.cf_configuracion for select to authenticated using (true);

drop policy if exists normalizacion_ejecuciones_authenticated_select
    on public.normalizacion_ejecuciones;
create policy normalizacion_ejecuciones_authenticated_select
    on public.normalizacion_ejecuciones for select to authenticated
    using (exists (
        select 1 from public.documentos_facturas d join public.cf_configuracion c on c.id = true
        where d.id = normalizacion_ejecuciones.documento_id
          and d.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists facturas_movimientos_authenticated_select
    on public.facturas_movimientos;
create policy facturas_movimientos_authenticated_select
    on public.facturas_movimientos for select to authenticated
    using (exists (
        select 1 from public.facturas f join public.cf_configuracion c on c.id = true
        where f.id = facturas_movimientos.factura_id
          and f.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists facturas_incidencias_authenticated_select
    on public.facturas_incidencias;
create policy facturas_incidencias_authenticated_select
    on public.facturas_incidencias for select to authenticated
    using (exists (
        select 1
          from public.cf_configuracion c
         where c.id = true and (
             (facturas_incidencias.documento_id is not null and exists (
                 select 1 from public.documentos_facturas d
                 where d.id = facturas_incidencias.documento_id
                   and d.farmacia = any(c.farmacias_habilitadas)
             )) or
             (facturas_incidencias.factura_id is not null and exists (
                 select 1 from public.facturas f
                 where f.id = facturas_incidencias.factura_id
                   and f.farmacia = any(c.farmacias_habilitadas)
             ))
         )
    ));

drop policy if exists historial_facturas_authenticated_select
    on public.historial_facturas;
create policy historial_facturas_authenticated_select
    on public.historial_facturas for select to authenticated
    using (exists (
        select 1 from public.documentos_facturas d join public.cf_configuracion c on c.id = true
        where d.id = historial_facturas.documento_id
          and d.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists conciliaciones_authenticated_select on public.conciliaciones;
create policy conciliaciones_authenticated_select
    on public.conciliaciones for select to authenticated
    using (exists (
        select 1 from public.facturas f join public.cf_configuracion c on c.id = true
        where f.id = conciliaciones.factura_id
          and f.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists conciliacion_detalles_authenticated_select
    on public.conciliacion_detalles;
create policy conciliacion_detalles_authenticated_select
    on public.conciliacion_detalles for select to authenticated
    using (exists (
        select 1
          from public.conciliaciones co
          join public.facturas f on f.id = co.factura_id
          join public.cf_configuracion c on c.id = true
         where co.id = conciliacion_detalles.conciliacion_id
           and f.farmacia = any(c.farmacias_habilitadas)
    ));

create or replace view public.v_facturas_listado
with (security_invoker = true)
as
select
    f.id,
    f.documento_id,
    f.farmacia,
    d.archivo_nombre,
    d.archivo_ruta,
    f.numero_factura,
    f.fecha_factura,
    f.proveedor_id,
    coalesce(p.nombre, f.proveedor_literal, f.proveedor_nombre) as proveedor,
    f.importe_total,
    f.estado_normalizacion,
    f.estado_conciliacion_cf,
    f.estado_revision,
    f.estado_pago,
    f.updated_at,
    coalesce(i.incidencias_abiertas, 0) as incidencias_abiertas,
    coalesce(i.incidencias_bloqueantes, 0) as incidencias_bloqueantes,
    c.resultado as conciliacion_resultado,
    c.diferencia as conciliacion_diferencia
from public.facturas f
join public.documentos_facturas d on d.id = f.documento_id
cross join public.cf_configuracion cfg
left join public.proveedores p on p.id = f.proveedor_id
left join lateral (
    select
        count(*) filter (where estado = 'ABIERTA') as incidencias_abiertas,
        count(*) filter (where estado = 'ABIERTA' and bloqueante) as incidencias_bloqueantes
    from public.facturas_incidencias fi
    where fi.factura_id = f.id
) i on true
left join public.conciliaciones c
    on c.factura_id = f.id and c.es_actual
where cfg.id = true
  and f.farmacia = any(cfg.farmacias_habilitadas);

create or replace view public.v_dashboard_diario
with (security_invoker = true)
as
select
    f.farmacia,
    coalesce(f.fecha_factura, d.fecha_importacion::date) as fecha,
    count(*) as total_facturas,
    count(*) filter (where f.estado_normalizacion = 'PENDIENTE') as pendientes_normalizar,
    count(*) filter (where f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR') as pendientes_conciliar,
    count(*) filter (where f.estado_revision = 'PENDIENTE_REVISION_PIO') as pendientes_revision,
    count(*) filter (where f.estado_conciliacion_cf = 'CONCILIADA') as conciliadas,
    coalesce(sum(f.importe_total), 0::numeric)::numeric(14,4) as importe_total
from public.facturas f
join public.documentos_facturas d on d.id = f.documento_id
cross join public.cf_configuracion cfg
where cfg.id = true
  and f.farmacia = any(cfg.farmacias_habilitadas)
group by f.farmacia, coalesce(f.fecha_factura, d.fecha_importacion::date);

create or replace view public.v_vencimientos_calendario
with (security_invoker = true)
as
select
    v.id as vencimiento_id,
    v.factura_id,
    f.farmacia,
    f.numero_factura,
    coalesce(p.nombre, f.proveedor_literal, f.proveedor_nombre) as proveedor,
    v.fecha_vencimiento,
    v.importe,
    v.orden,
    f.estado_pago,
    f.estado_revision,
    v.provenance
from public.facturas_vencimientos v
join public.facturas f on f.id = v.factura_id
left join public.proveedores p on p.id = f.proveedor_id
cross join public.cf_configuracion cfg
where cfg.id = true
  and f.farmacia = any(cfg.farmacias_habilitadas);

create or replace view public.v_proveedores_estado
with (security_invoker = true)
as
select
    p.id,
    p.codigo,
    p.nombre,
    p.farmatic_id_proveedor,
    p.extractor_codigo,
    p.nivel_confianza,
    p.activo,
    count(f.id) as facturas,
    count(f.id) filter (where f.estado_revision = 'PENDIENTE_REVISION_PIO')
        as pendientes_revision,
    count(f.id) filter (where f.estado_conciliacion_cf = 'CONCILIADA')
        as conciliadas
from public.proveedores p
cross join public.cf_configuracion cfg
left join public.facturas f
    on f.proveedor_id = p.id
   and f.farmacia = any(cfg.farmacias_habilitadas)
where cfg.id = true
group by p.id;

grant select on public.v_facturas_listado to authenticated;
grant select on public.v_dashboard_diario to authenticated;
grant select on public.v_vencimientos_calendario to authenticated;
grant select on public.v_proveedores_estado to authenticated;

create or replace function public.cf_persistir_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_resultado_hash text,
    p_resultado jsonb
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_documento public.documentos_facturas%rowtype;
    v_ejecucion_id uuid;
    v_intento integer;
    v_documento_normalizado jsonb := coalesce(p_resultado->'resultado_json', p_resultado);
    v_factura jsonb;
    v_factura_id uuid;
    v_item jsonb;
    v_estado_factura text;
begin
    if nullif(btrim(p_worker_id), '') is null
       or nullif(btrim(p_idempotency_key), '') is null then
        raise exception 'worker_id e idempotency_key obligatorios';
    end if;

    select * into v_documento
      from public.documentos_facturas
     where id = p_documento_id
     for update;

    if v_documento.id is null then
        raise exception 'documento no encontrado';
    end if;
    if not exists (
        select 1 from public.cf_configuracion c
        where c.id = true and v_documento.farmacia = any(c.farmacias_habilitadas)
    ) then
        raise exception 'farmacia fuera del despliegue habilitado';
    end if;

    select id into v_ejecucion_id
      from public.normalizacion_ejecuciones
     where documento_id = p_documento_id
       and idempotency_key = p_idempotency_key;
    if v_ejecucion_id is not null then
        return v_ejecucion_id;
    end if;
    if v_documento.bloqueado_por is distinct from p_worker_id then
        raise exception 'claim no pertenece al worker';
    end if;

    select coalesce(max(intento), 0) + 1 into v_intento
      from public.normalizacion_ejecuciones
     where documento_id = p_documento_id;

    insert into public.normalizacion_ejecuciones (
        documento_id, idempotency_key, intento, disparador, estado,
        normalizador_version, resultado_hash, uso_ocr, uso_luna,
        luna_modelo, luna_campos, tokens_entrada, tokens_salida,
        tokens_total, coste_luna, pasos, resultado_json, worker_id,
        iniciado_at, finalizado_at
    ) values (
        p_documento_id, p_idempotency_key, v_intento, p_disparador,
        case when jsonb_array_length(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb)) > 0
             then 'COMPLETADA' else 'INCOMPLETA' end,
        v_documento_normalizado #>> '{metadata_tecnica,version_normalizador}',
        p_resultado_hash, coalesce((p_resultado->>'uso_ocr')::boolean, false),
        coalesce((p_resultado->>'uso_luna')::boolean, false),
        p_resultado->>'luna_modelo',
        coalesce(array(select jsonb_array_elements_text(coalesce(p_resultado->'luna_campos', '[]'::jsonb))), '{}'::text[]),
        nullif(p_resultado->>'tokens_entrada', '')::integer,
        nullif(p_resultado->>'tokens_salida', '')::integer,
        nullif(p_resultado->>'tokens_total', '')::integer,
        nullif(p_resultado->>'coste_luna', '')::numeric,
        coalesce(p_resultado->'pasos', '[]'::jsonb),
        v_documento_normalizado, p_worker_id, now(), now()
    ) returning id into v_ejecucion_id;

    for v_factura in
        select value from jsonb_array_elements(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb))
    loop
        if nullif(v_factura->>'factura_id', '') is null then
            raise exception 'factura_id estable obligatorio en DocumentoNormalizado';
        end if;
        v_estado_factura := case
            when v_factura->>'estado_validacion' in ('VALIDADA', 'VALIDADA_CON_INCIDENCIAS')
            then 'NORMALIZADA' else 'REQUIERE_REVISION' end;

        insert into public.facturas (
            documento_id, proyeccion_clave, farmacia, pagina_inicio, pagina_fin,
            tipo_documento, categoria, requiere_conciliacion_albaranes,
            proveedor_literal, numero_factura, fecha_factura, moneda,
            base_imponible_total, iva_total, recargo_equivalencia_total,
            importe_total, requiere_revision, estado_normalizacion,
            estado_revision, normalizacion_ejecucion_id, provenance,
            datos_extraidos, updated_at, fecha_actualizacion
        ) values (
            p_documento_id, v_factura->>'factura_id', v_documento.farmacia,
            nullif(v_factura->>'pagina_inicio', '')::integer,
            nullif(v_factura->>'pagina_fin', '')::integer,
            case
                when v_factura #>> '{tipo_documento,valor}' in
                    ('FACTURA', 'ABONO', 'FACTURA_RECTIFICATIVA', 'OTRO')
                then v_factura #>> '{tipo_documento,valor}'
                when v_factura #>> '{tipo_documento,valor}' is null then 'FACTURA'
                else 'OTRO'
            end,
            case v_factura->>'naturaleza_principal'
                when 'MERCANCIA' then 'MERCANCIA'
                when 'SERVICIOS' then 'CUOTA_SERVICIO'
                else 'OTRO' end,
            coalesce((v_factura->>'requiere_conciliacion_albaranes')::boolean, false),
            v_factura #>> '{proveedor,nombre,valor}',
            v_factura #>> '{numero_factura,valor}',
            nullif(v_factura #>> '{fecha_factura,valor,iso}', '')::date,
            coalesce(v_factura #>> '{totales,moneda,valor}', 'EUR'),
            nullif(v_factura #>> '{totales,base_imponible,valor}', '')::numeric,
            nullif(v_factura #>> '{totales,iva,valor}', '')::numeric,
            nullif(v_factura #>> '{totales,recargo_equivalencia,valor}', '')::numeric,
            nullif(v_factura #>> '{totales,total,valor}', '')::numeric,
            v_estado_factura = 'REQUIERE_REVISION', v_estado_factura,
            case when v_estado_factura = 'NORMALIZADA' then 'NO_REQUERIDA'
                 else 'PENDIENTE_REVISION_PIO' end,
            v_ejecucion_id,
            jsonb_build_object('fuente', 'DOCUMENTO_NORMALIZADO', 'ejecucion_id', v_ejecucion_id),
            v_factura, now(), now()
        ) on conflict (documento_id, proyeccion_clave) do update set
            pagina_inicio = excluded.pagina_inicio,
            pagina_fin = excluded.pagina_fin,
            tipo_documento = excluded.tipo_documento,
            categoria = excluded.categoria,
            requiere_conciliacion_albaranes = excluded.requiere_conciliacion_albaranes,
            proveedor_literal = excluded.proveedor_literal,
            numero_factura = excluded.numero_factura,
            fecha_factura = excluded.fecha_factura,
            moneda = excluded.moneda,
            base_imponible_total = excluded.base_imponible_total,
            iva_total = excluded.iva_total,
            recargo_equivalencia_total = excluded.recargo_equivalencia_total,
            importe_total = excluded.importe_total,
            requiere_revision = excluded.requiere_revision,
            estado_normalizacion = excluded.estado_normalizacion,
            estado_revision = excluded.estado_revision,
            normalizacion_ejecucion_id = excluded.normalizacion_ejecucion_id,
            provenance = excluded.provenance,
            datos_extraidos = excluded.datos_extraidos,
            updated_at = now(),
            fecha_actualizacion = now()
        returning id into v_factura_id;

        delete from public.facturas_vencimientos where factura_id = v_factura_id;
        for v_item in select value from jsonb_array_elements(coalesce(v_factura->'vencimientos', '[]'::jsonb)) loop
            insert into public.facturas_vencimientos
                (factura_id, fecha_vencimiento, importe, orden, literal, provenance)
            values (v_factura_id, nullif(v_item #>> '{fecha,valor,iso}', '')::date,
                nullif(v_item #>> '{importe,valor}', '')::numeric,
                (v_item->>'orden')::integer,
                coalesce(v_item #>> '{fecha,literal}', v_item #>> '{importe,literal}'), v_item);
        end loop;

        delete from public.facturas_impuestos where factura_id = v_factura_id;
        for v_item in select value from jsonb_array_elements(coalesce(v_factura->'impuestos', '[]'::jsonb)) loop
            insert into public.facturas_impuestos
                (factura_id, concepto, base_imponible, tipo_iva, cuota_iva,
                 tipo_recargo_equivalencia, cuota_recargo_equivalencia, total_tramo,
                 orden, literal, provenance)
            values (v_factura_id, v_item #>> '{descripcion_literal,valor}',
                nullif(v_item #>> '{base,valor}', '')::numeric,
                nullif(v_item #>> '{tipo_iva,valor}', '')::numeric,
                nullif(v_item #>> '{cuota_iva,valor}', '')::numeric,
                nullif(v_item #>> '{tipo_recargo_equivalencia,valor}', '')::numeric,
                nullif(v_item #>> '{cuota_recargo_equivalencia,valor}', '')::numeric,
                nullif(v_item #>> '{total_tramo,valor}', '')::numeric,
                (v_item->>'orden')::integer, v_item #>> '{descripcion_literal,literal}', v_item);
        end loop;

        delete from public.facturas_albaranes_extraidos where factura_id = v_factura_id;
        for v_item in select value from jsonb_array_elements(coalesce(v_factura->'albaranes', '[]'::jsonb)) loop
            insert into public.facturas_albaranes_extraidos
                (factura_id, numero_albaran, fecha_albaran, tipo_movimiento,
                 importe_base, importe_total, descripcion, orden, literal, provenance)
            values (v_factura_id, v_item #>> '{numero,valor}',
                nullif(v_item #>> '{fecha,valor,iso}', '')::date, v_item->>'sentido',
                nullif(v_item #>> '{importe_base,valor}', '')::numeric,
                nullif(v_item #>> '{importe_total,valor}', '')::numeric,
                v_item #>> '{tipo_pedido,valor}', (v_item->>'orden')::integer,
                v_item #>> '{numero,literal}', v_item);
        end loop;

        delete from public.facturas_movimientos where factura_id = v_factura_id;
        for v_item in select value from jsonb_array_elements(coalesce(v_factura->'movimientos_comerciales', '[]'::jsonb)) loop
            insert into public.facturas_movimientos
                (factura_id, normalizacion_ejecucion_id, orden, categoria,
                 descripcion_literal, sentido, base, iva, recargo_equivalencia,
                 importe, provenance)
            values (v_factura_id, v_ejecucion_id, (v_item->>'orden')::integer,
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
                nullif(v_item #>> '{importe,valor}', '')::numeric, v_item);
        end loop;

        for v_item in select value from jsonb_array_elements(coalesce(v_factura->'incidencias', '[]'::jsonb)) loop
            insert into public.facturas_incidencias
                (factura_id, normalizacion_ejecucion_id, codigo, categoria,
                 severidad, bloqueante, mensaje_usuario, detalle_tecnico, provenance)
            values (v_factura_id, v_ejecucion_id, v_item->>'codigo', 'NORMALIZACION',
                case when v_item->>'severidad' = 'ERROR' then 'ERROR' else 'AVISO' end,
                coalesce((v_item->>'bloqueante')::boolean, false),
                coalesce(v_item->>'descripcion', v_item->>'codigo'), v_item, v_item);
        end loop;

        insert into public.historial_facturas
            (documento_id, factura_id, evento, origen, actor, estado_nuevo, detalle)
        values (p_documento_id, v_factura_id, 'PROYECCION_NORMALIZACION_REEMPLAZADA',
            'RPC', p_worker_id,
            jsonb_build_object('estado_normalizacion', v_estado_factura),
            jsonb_build_object('ejecucion_id', v_ejecucion_id,
                               'proyeccion_clave', v_factura->>'factura_id'));
    end loop;

    for v_item in select value from jsonb_array_elements(coalesce(p_resultado->'incidencias_runtime', '[]'::jsonb)) loop
        insert into public.facturas_incidencias
            (documento_id, normalizacion_ejecucion_id, codigo, categoria,
             severidad, bloqueante, mensaje_usuario, detalle_tecnico, provenance)
        values (p_documento_id, v_ejecucion_id, v_item->>'codigo',
            coalesce(v_item->>'categoria', 'NORMALIZACION'),
            coalesce(v_item->>'severidad', 'AVISO'),
            coalesce((v_item->>'bloqueante')::boolean, false),
            v_item->>'mensaje_usuario', coalesce(v_item->'detalle_tecnico', '{}'::jsonb),
            jsonb_build_object('fuente', 'RUNTIME_LOCAL'));
    end loop;

    update public.documentos_facturas
       set estado_lectura = 'NORMALIZADA',
           numero_paginas = coalesce(nullif(v_documento_normalizado->>'numero_paginas', '')::integer, numero_paginas),
           cantidad_documentos_detectados = jsonb_array_length(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb)),
           tipo_contenido = case
               when jsonb_array_length(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb)) = 0
                   then 'DESCONOCIDO'
               when jsonb_array_length(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb)) = 1
                   then 'FACTURA_UNICA'
               else 'LOTE_FACTURAS'
           end,
           bloqueado_hasta = null, bloqueado_por = null,
           reprocesar_solicitado_at = null, ultimo_error_codigo = null,
           fecha_fin_lectura = now(), fecha_actualizacion = now()
     where id = p_documento_id;

    insert into public.historial_facturas
        (documento_id, evento, origen, actor, estado_nuevo, detalle)
    values (p_documento_id, 'DOCUMENTO_NORMALIZADO_PERSISTIDO', 'RPC', p_worker_id,
        jsonb_build_object('estado_lectura', 'NORMALIZADA'),
        jsonb_build_object('ejecucion_id', v_ejecucion_id, 'facturas',
            jsonb_array_length(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb))));

    return v_ejecucion_id;
end;
$$;

create or replace function public.cf_registrar_fallo_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_error_codigo text,
    p_error_detalle text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_ejecucion_id uuid;
    v_intento integer;
begin
    select id into v_ejecucion_id
      from public.normalizacion_ejecuciones
     where documento_id = p_documento_id and idempotency_key = p_idempotency_key;
    if v_ejecucion_id is not null then return v_ejecucion_id; end if;

    perform 1 from public.documentos_facturas d
     where d.id = p_documento_id
       and d.bloqueado_por = p_worker_id
       and exists (
           select 1 from public.cf_configuracion c
           where c.id = true and d.farmacia = any(c.farmacias_habilitadas)
       )
     for update;
    if not found then raise exception 'claim no pertenece al worker'; end if;

    select coalesce(max(intento), 0) + 1 into v_intento
      from public.normalizacion_ejecuciones where documento_id = p_documento_id;
    insert into public.normalizacion_ejecuciones
        (documento_id, idempotency_key, intento, disparador, estado, worker_id,
         iniciado_at, finalizado_at, error_codigo, error_detalle)
    values (p_documento_id, p_idempotency_key, v_intento, p_disparador, 'ERROR',
        p_worker_id, now(), now(), p_error_codigo, p_error_detalle)
    returning id into v_ejecucion_id;

    update public.documentos_facturas
       set estado_lectura = 'ERROR', ultimo_error_codigo = p_error_codigo,
           bloqueado_hasta = null, bloqueado_por = null,
           reprocesar_solicitado_at = null, fecha_actualizacion = now()
     where id = p_documento_id;
    insert into public.historial_facturas
        (documento_id, evento, origen, actor, estado_nuevo, detalle)
    values (p_documento_id, 'NORMALIZACION_ERROR', 'RPC', p_worker_id,
        jsonb_build_object('estado_lectura', 'ERROR'),
        jsonb_build_object('ejecucion_id', v_ejecucion_id, 'codigo', p_error_codigo));
    return v_ejecucion_id;
end;
$$;

create or replace function public.cf_validar_factura(
    p_factura_id uuid,
    p_actor text default null
)
returns public.facturas
language plpgsql
security definer
set search_path = public
as $$
declare
    v_anterior jsonb;
    v_factura public.facturas%rowtype;
    v_actor text := coalesce(auth.uid()::text, nullif(btrim(p_actor), ''), 'SISTEMA');
begin
    select jsonb_build_object(
        'estado_revision', estado_revision,
        'requiere_revision', requiere_revision,
        'validada_manualmente', validada_manualmente
    )
      into v_anterior
      from public.facturas
     where id = p_factura_id
       and exists (
           select 1 from public.cf_configuracion c
           where c.id = true and facturas.farmacia = any(c.farmacias_habilitadas)
       )
     for update;

    if v_anterior is null then
        raise exception 'factura no encontrada';
    end if;

    update public.facturas
       set estado_revision = 'VALIDADA_PIO',
           requiere_revision = false,
           validada_manualmente = true,
           validada_por = v_actor,
           fecha_validacion = now(),
           updated_at = now()
     where id = p_factura_id
     returning * into v_factura;

    insert into public.historial_facturas (
        documento_id, factura_id, evento, origen, actor,
        estado_anterior, estado_nuevo
    ) values (
        v_factura.documento_id, v_factura.id, 'FACTURA_VALIDADA_PIO',
        'RPC', v_actor, v_anterior,
        jsonb_build_object(
            'estado_revision', v_factura.estado_revision,
            'requiere_revision', v_factura.requiere_revision,
            'validada_manualmente', v_factura.validada_manualmente
        )
    );

    return v_factura;
end;
$$;

create or replace function public.cf_desvalidar_factura(
    p_factura_id uuid,
    p_actor text default null
)
returns public.facturas
language plpgsql
security definer
set search_path = public
as $$
declare
    v_anterior jsonb;
    v_factura public.facturas%rowtype;
    v_actor text := coalesce(auth.uid()::text, nullif(btrim(p_actor), ''), 'SISTEMA');
begin
    select jsonb_build_object(
        'estado_revision', estado_revision,
        'requiere_revision', requiere_revision,
        'validada_manualmente', validada_manualmente
    )
      into v_anterior
      from public.facturas
     where id = p_factura_id
       and exists (
           select 1 from public.cf_configuracion c
           where c.id = true and facturas.farmacia = any(c.farmacias_habilitadas)
       )
     for update;

    if v_anterior is null then
        raise exception 'factura no encontrada';
    end if;

    update public.facturas
       set estado_revision = 'PENDIENTE_REVISION_PIO',
           requiere_revision = true,
           validada_manualmente = false,
           validada_por = null,
           fecha_validacion = null,
           updated_at = now()
     where id = p_factura_id
     returning * into v_factura;

    insert into public.historial_facturas (
        documento_id, factura_id, evento, origen, actor,
        estado_anterior, estado_nuevo
    ) values (
        v_factura.documento_id, v_factura.id, 'FACTURA_DESVALIDADA',
        'RPC', v_actor, v_anterior,
        jsonb_build_object(
            'estado_revision', v_factura.estado_revision,
            'requiere_revision', v_factura.requiere_revision,
            'validada_manualmente', v_factura.validada_manualmente
        )
    );

    return v_factura;
end;
$$;

create or replace function public.cf_solicitar_reprocesado(
    p_documento_id uuid,
    p_actor text default null
)
returns public.documentos_facturas
language plpgsql
security definer
set search_path = public
as $$
declare
    v_documento public.documentos_facturas%rowtype;
    v_actor text := coalesce(auth.uid()::text, nullif(btrim(p_actor), ''), 'SISTEMA');
begin
    update public.documentos_facturas d
       set reprocesar_solicitado_at = now(),
           proximo_reintento_at = null,
           bloqueado_hasta = null,
           bloqueado_por = null,
           ultimo_error_codigo = null,
           estado_lectura = 'PENDIENTE',
           fecha_actualizacion = now()
     where d.id = p_documento_id
       and exists (
           select 1 from public.cf_configuracion c
           where c.id = true and d.farmacia = any(c.farmacias_habilitadas)
       )
     returning * into v_documento;

    if v_documento.id is null then
        raise exception 'documento no encontrado';
    end if;

    insert into public.historial_facturas (
        documento_id, evento, origen, actor, estado_nuevo
    ) values (
        v_documento.id, 'REPROCESADO_SOLICITADO', 'RPC', v_actor,
        jsonb_build_object('estado_lectura', v_documento.estado_lectura)
    );

    return v_documento;
end;
$$;

create or replace function public.cf_solicitar_reintento_conciliacion(
    p_factura_id uuid,
    p_actor text default null
)
returns public.facturas
language plpgsql
security definer
set search_path = public
as $$
declare
    v_factura public.facturas%rowtype;
    v_actor text := coalesce(auth.uid()::text, nullif(btrim(p_actor), ''), 'SISTEMA');
begin
    update public.facturas f
       set estado_conciliacion_cf = 'PENDIENTE_CONCILIAR',
           conciliacion_reintento_solicitado_at = now(),
           conciliacion_proximo_at = null,
           conciliacion_bloqueado_hasta = null,
           conciliacion_bloqueado_por = null,
           conciliacion_ultimo_error = null,
           updated_at = now()
     where f.id = p_factura_id
       and exists (
           select 1 from public.cf_configuracion c
           where c.id = true and f.farmacia = any(c.farmacias_habilitadas)
       )
     returning * into v_factura;

    if v_factura.id is null then
        raise exception 'factura no encontrada';
    end if;

    insert into public.historial_facturas (
        documento_id, factura_id, evento, origen, actor, estado_nuevo
    ) values (
        v_factura.documento_id, v_factura.id,
        'REINTENTO_CONCILIACION_SOLICITADO', 'RPC', v_actor,
        jsonb_build_object('estado_conciliacion_cf', v_factura.estado_conciliacion_cf)
    );

    return v_factura;
end;
$$;

create or replace function public.cf_reintentar_todas_pendientes(
    p_actor text default 'SERVICE_ROLE'
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_total integer;
begin
    update public.facturas f
       set conciliacion_reintento_solicitado_at = now(),
           conciliacion_proximo_at = null,
           conciliacion_bloqueado_hasta = null,
           conciliacion_bloqueado_por = null,
           updated_at = now()
     where f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'
       and exists (
           select 1 from public.cf_configuracion c
           where c.id = true and f.farmacia = any(c.farmacias_habilitadas)
       );

    get diagnostics v_total = row_count;

    insert into public.historial_facturas (
        factura_id, documento_id, evento, origen, actor, estado_nuevo, detalle
    )
    select
        f.id, f.documento_id, 'REINTENTO_CONCILIACION_MASIVO',
        'RPC', p_actor,
        jsonb_build_object('estado_conciliacion_cf', f.estado_conciliacion_cf),
        jsonb_build_object('total_solicitado', v_total)
    from public.facturas f
    where f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'
      and f.conciliacion_reintento_solicitado_at is not null
      and exists (
          select 1 from public.cf_configuracion c
          where c.id = true and f.farmacia = any(c.farmacias_habilitadas)
      );

    return v_total;
end;
$$;

revoke all on function public.cf_validar_factura(uuid, text)
    from public, anon;
revoke all on function public.cf_desvalidar_factura(uuid, text)
    from public, anon;
revoke all on function public.cf_solicitar_reprocesado(uuid, text)
    from public, anon;
revoke all on function public.cf_solicitar_reintento_conciliacion(uuid, text)
    from public, anon;
revoke all on function public.cf_reintentar_todas_pendientes(text)
    from public, anon, authenticated;
revoke all on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    from public, anon, authenticated;
revoke all on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text)
    from public, anon, authenticated;

grant execute on function public.cf_validar_factura(uuid, text) to authenticated;
grant execute on function public.cf_desvalidar_factura(uuid, text) to authenticated;
grant execute on function public.cf_solicitar_reprocesado(uuid, text) to authenticated;
grant execute on function public.cf_solicitar_reintento_conciliacion(uuid, text)
    to authenticated;
grant execute on function public.cf_reintentar_todas_pendientes(text) to service_role;
grant execute on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    to service_role;
grant execute on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text)
    to service_role;

update storage.buckets
   set public = false
 where id = 'facturas-pdf';

comment on view public.v_facturas_listado is
    'Listado para futura interfaz; el PDF debe abrirse mediante signed URL de backend.';

commit;
