begin;

do $$
begin
    if not public.cf_preflight_pio_valido() then
        raise exception using
            message = 'MIGRACION_13_BLOQUEADA: manifiesto PIO SQLite y Supabase no reconciliado',
            hint = 'RITA_EXCLUIDA_DEL_DESPLIEGUE_PIO; atestar conteos y SHA-256 del manifiesto exclusivamente PIO.';
    end if;
end;
$$;

update public.facturas
   set proveedor_literal = coalesce(proveedor_literal, proveedor_nombre),
       estado_normalizacion = case
           when datos_extraidos <> '{}'::jsonb then 'NORMALIZADA'
           else 'PENDIENTE'
       end,
       estado_conciliacion_cf = case
           when estado_conciliacion = 'CONCILIADA' then 'CONCILIADA'
           else 'PENDIENTE_CONCILIAR'
       end,
       estado_revision = case
           when validada_manualmente then 'VALIDADA_PIO'
           when requiere_revision then 'PENDIENTE_REVISION_PIO'
           else 'NO_REQUERIDA'
       end,
       updated_at = now()
 where farmacia = 'PIO';

with candidatos as (
    select
        f.id as factura_id,
        f.documento_id,
        lower(btrim(coalesce(f.proveedor_literal, f.proveedor_nombre, ''))) as proveedor_clave,
        lower(btrim(f.numero_factura)) as numero_clave,
        f.fecha_factura
    from public.facturas f
    where f.farmacia = 'PIO'
      and nullif(btrim(f.numero_factura), '') is not null
),
grupos as (
    select proveedor_clave, numero_clave, fecha_factura
    from candidatos
    group by proveedor_clave, numero_clave, fecha_factura
    having count(distinct documento_id) > 1
)
insert into public.facturas_incidencias (
    factura_id,
    codigo,
    categoria,
    severidad,
    bloqueante,
    mensaje_usuario,
    detalle_tecnico,
    estado,
    provenance
)
select
    c.factura_id,
    'POSIBLE_DUPLICADO',
    'IDENTIDAD_DOCUMENTAL',
    'AVISO',
    false,
    'Existe otra factura con la misma identidad economica en un PDF diferente.',
    jsonb_build_object(
        'proveedor_clave', c.proveedor_clave,
        'numero_clave', c.numero_clave,
        'fecha_factura', c.fecha_factura,
        'accion_automatica', 'NINGUNA'
    ),
    'ABIERTA',
    jsonb_build_object(
        'fuente', 'BACKFILL_COMPATIBILIDAD_V1',
        'fusion_automatica', false
    )
from candidatos c
join grupos g
  on g.proveedor_clave = c.proveedor_clave
 and g.numero_clave = c.numero_clave
 and g.fecha_factura is not distinct from c.fecha_factura
where not exists (
    select 1
    from public.facturas_incidencias i
    where i.factura_id = c.factura_id
      and i.codigo = 'POSIBLE_DUPLICADO'
      and i.estado = 'ABIERTA'
);

update public.facturas f
   set proveedor_id = coincidencia.proveedor_id,
       updated_at = now()
  from (
      select clave, min(proveedor_id::text)::uuid as proveedor_id
      from (
          select lower(btrim(codigo)) as clave, id as proveedor_id
          from public.proveedores
          union all
          select lower(btrim(alias)) as clave, proveedor_id
          from public.proveedores_alias
      ) fuentes
      group by clave
      having count(distinct proveedor_id) = 1
  ) coincidencia
 where f.proveedor_id is null
   and f.farmacia = 'PIO'
   and lower(btrim(coalesce(f.proveedor_literal, f.proveedor_nombre, '')))
       = coincidencia.clave;

insert into public.historial_facturas (
    documento_id,
    factura_id,
    evento,
    origen,
    actor,
    estado_nuevo,
    detalle
)
select
    f.documento_id,
    f.id,
    'BACKFILL_COMPATIBILIDAD_V1',
    'MIGRACION_13',
    'SISTEMA',
    jsonb_build_object(
        'estado_normalizacion', f.estado_normalizacion,
        'estado_conciliacion_cf', f.estado_conciliacion_cf,
        'estado_revision', f.estado_revision
    ),
    jsonb_build_object(
        'legacy_conservado', true,
        'pdfs_fusionados', false
    )
from public.facturas f
where f.farmacia = 'PIO'
  and not exists (
    select 1
    from public.historial_facturas h
    where h.factura_id = f.id
      and h.evento = 'BACKFILL_COMPATIBILIDAD_V1'
);

commit;
