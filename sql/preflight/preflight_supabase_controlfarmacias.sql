-- PREFLIGHT LEGACY: ejecutar despues de 06 y antes de 07.
-- Este archivo es deliberadamente 100 % SELECT. Los objetos V1 se inspeccionan
-- solo mediante catalogos porque todavia pueden no existir.

select
    current_schema() as schema_name,
    current_setting('server_version') as server_version;

select
    esperado.table_name,
    to_regclass('public.' || esperado.table_name) is not null as existe,
    'PREEXISTENTE_ANTES_07' as clasificacion
from (
    values
        ('documentos_facturas'),
        ('facturas'),
        ('facturas_vencimientos'),
        ('facturas_impuestos'),
        ('facturas_albaranes_extraidos'),
        ('facturas_ajustes'),
        ('albaranes')
) as esperado(table_name)
order by esperado.table_name;

select
    esperado.object_type,
    esperado.object_name,
    case esperado.object_type
        when 'TABLE' then to_regclass('public.' || esperado.object_name) is not null
        when 'VIEW' then to_regclass('public.' || esperado.object_name) is not null
        when 'RPC' then exists (
            select 1
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'public'
              and p.proname = esperado.object_name
        )
    end as existe_antes_07,
    'OPCIONAL_ANTES_07' as expectativa
from (
    values
        ('TABLE', 'proveedores'),
        ('TABLE', 'proveedores_alias'),
        ('TABLE', 'cf_configuracion'),
        ('TABLE', 'normalizacion_ejecuciones'),
        ('TABLE', 'facturas_movimientos'),
        ('TABLE', 'facturas_incidencias'),
        ('TABLE', 'historial_facturas'),
        ('TABLE', 'conciliaciones'),
        ('TABLE', 'conciliacion_detalles'),
        ('VIEW', 'v_facturas_listado'),
        ('VIEW', 'v_dashboard_diario'),
        ('VIEW', 'v_vencimientos_calendario'),
        ('VIEW', 'v_proveedores_estado'),
        ('RPC', 'cf_preflight_pio_valido'),
        ('RPC', 'cf_reclamar_documento_normalizacion'),
        ('RPC', 'cf_reclamar_factura_conciliacion'),
        ('RPC', 'cf_persistir_normalizacion'),
        ('RPC', 'cf_registrar_fallo_normalizacion'),
        ('RPC', 'cf_validar_factura'),
        ('RPC', 'cf_desvalidar_factura'),
        ('RPC', 'cf_solicitar_reprocesado'),
        ('RPC', 'cf_solicitar_reintento_conciliacion'),
        ('RPC', 'cf_reintentar_todas_pendientes')
) as esperado(object_type, object_name)
order by esperado.object_type, esperado.object_name;

select
    table_schema,
    table_name,
    table_type
from information_schema.tables
where table_schema in ('public', 'storage')
  and table_name in (
      'documentos_facturas',
      'facturas',
      'facturas_vencimientos',
      'facturas_impuestos',
      'facturas_albaranes_extraidos',
      'facturas_ajustes',
      'albaranes',
      'buckets'
  )
order by table_schema, table_name;

select
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default,
    numeric_precision,
    numeric_scale
from information_schema.columns
where table_schema = 'public'
  and table_name in (
      'documentos_facturas',
      'facturas',
      'facturas_vencimientos',
      'facturas_impuestos',
      'facturas_albaranes_extraidos',
      'facturas_ajustes',
      'albaranes'
  )
order by table_name, ordinal_position;

select
    n.nspname as schema_name,
    c.relname as table_name,
    con.conname as constraint_name,
    con.contype as constraint_type,
    pg_get_constraintdef(con.oid, true) as definition
from pg_constraint con
join pg_class c on c.oid = con.conrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in (
      'documentos_facturas',
      'facturas',
      'facturas_vencimientos',
      'facturas_impuestos',
      'facturas_albaranes_extraidos',
      'facturas_ajustes',
      'albaranes'
  )
order by c.relname, con.contype, con.conname;

select
    schemaname,
    tablename,
    indexname,
    indexdef
from pg_indexes
where schemaname = 'public'
  and tablename in (
      'documentos_facturas',
      'facturas',
      'facturas_vencimientos',
      'facturas_impuestos',
      'facturas_albaranes_extraidos',
      'facturas_ajustes',
      'albaranes'
  )
order by tablename, indexname;

select
    c.relname as table_name,
    c.relrowsecurity as rls_enabled,
    c.relforcerowsecurity as rls_forced
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'r'
  and c.relname in (
      'documentos_facturas',
      'facturas',
      'facturas_vencimientos',
      'facturas_impuestos',
      'facturas_albaranes_extraidos',
      'facturas_ajustes',
      'albaranes'
  )
order by c.relname;

select
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
from pg_policies
where schemaname = 'public'
  and tablename in (
      'documentos_facturas',
      'facturas',
      'facturas_vencimientos',
      'facturas_impuestos',
      'facturas_albaranes_extraidos',
      'facturas_ajustes',
      'albaranes'
  )
order by tablename, policyname;

select 'documentos_facturas' as table_name, count(*) as row_count
from public.documentos_facturas
union all
select 'facturas', count(*) from public.facturas
union all
select 'facturas_vencimientos', count(*) from public.facturas_vencimientos
union all
select 'facturas_impuestos', count(*) from public.facturas_impuestos
union all
select 'facturas_albaranes_extraidos', count(*) from public.facturas_albaranes_extraidos
union all
select 'facturas_ajustes', count(*) from public.facturas_ajustes
union all
select 'albaranes', count(*) from public.albaranes
order by table_name;

select
    count(*) = 0 as facturas_vacias,
    (select count(*) from public.facturas_vencimientos) = 0 as vencimientos_vacios,
    (select count(*) from public.facturas_impuestos) = 0 as impuestos_vacios,
    (select count(*) from public.facturas_albaranes_extraidos) = 0 as albaranes_extraidos_vacios,
    (select count(*) from public.facturas_ajustes) = 0 as ajustes_vacios
from public.facturas;

select
    farmacia,
    estado_lectura,
    tipo_contenido,
    requiere_revision,
    count(*) as row_count
from public.documentos_facturas
group by farmacia, estado_lectura, tipo_contenido, requiere_revision
order by farmacia, estado_lectura, tipo_contenido, requiere_revision;

select
    farmacia,
    count(*) as documentos,
    count(distinct archivo_hash) as hashes_unicos,
    count(*) filter (where archivo_hash is null) as hashes_nulos
from public.documentos_facturas
group by farmacia
order by farmacia;

-- Identidad canonica remota: hashes SHA-256 unicos PIO, ordenados y unidos por LF.
select * from (with hashes_pio as (
    select lower(archivo_hash) as archivo_hash
    from public.documentos_facturas
    where farmacia = 'PIO'
), unicos as (
    select distinct archivo_hash
    from hashes_pio
    where archivo_hash ~ '^[0-9a-f]{64}$'
)
select
    (select count(*) from hashes_pio) as pio_registros,
    (select count(*) from unicos) as pio_hashes_unicos,
    (select count(*) from hashes_pio
      where archivo_hash is null or archivo_hash !~ '^[0-9a-f]{64}$') as pio_hashes_invalidos,
    encode(extensions.digest(coalesce(string_agg(archivo_hash, E'\n' order by archivo_hash), ''), 'sha256'), 'hex')
        as manifiesto_supabase_pio_canonico
from unicos) as manifiesto_pio_canonico;

select
    farmacia,
    estado_conciliacion,
    estado_pago,
    tipo_documento,
    categoria,
    count(*) as row_count
from public.facturas
group by farmacia, estado_conciliacion, estado_pago, tipo_documento, categoria
order by farmacia, estado_conciliacion, estado_pago, tipo_documento, categoria;

select
    farmacia,
    estado,
    count(*) as row_count,
    count(distinct id_contador) as distinct_id_contador
from public.albaranes
group by farmacia, estado
order by farmacia, estado;

select
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default,
    numeric_precision,
    numeric_scale
from information_schema.columns
where table_schema = 'public'
  and table_name = 'albaranes'
  and column_name in ('id', 'id_contador', 'id_proveedor', 'importe_pvp', 'importe_puc')
order by ordinal_position;

select
    farmacia,
    id_contador,
    count(*) as duplicate_count
from public.albaranes
group by farmacia, id_contador
having count(*) > 1
order by duplicate_count desc, farmacia, id_contador;

select
    estado.garantia_unique_efectiva,
    estado.duplicados_materiales,
    case
        when estado.garantia_unique_efectiva
             and estado.duplicados_materiales = 0
            then 'APTO_DESPLIEGUE_V1'
        when estado.duplicados_materiales > 0
            then 'BLOQUEADO_DUPLICADOS'
        else 'REQUIERE_MIGRACION_06B'
    end as estado_integridad_albaranes,
    estado.garantia_unique_efectiva
        and estado.duplicados_materiales = 0 as apto_despliegue_v1
from (
    select
        exists (
            select 1
            from pg_index i
            join pg_class t on t.oid = i.indrelid
            join pg_namespace n on n.oid = t.relnamespace
            where n.nspname = 'public'
              and t.relname = 'albaranes'
              and i.indisunique
              and i.indisvalid
              and i.indisready
              and i.indpred is null
              and i.indexprs is null
              and i.indnkeyatts = 2
              and (
                  select array_agg(a.attname order by k.ordinality)
                  from unnest(i.indkey) with ordinality as k(attnum, ordinality)
                  join pg_attribute a
                    on a.attrelid = t.oid
                   and a.attnum = k.attnum
                  where k.ordinality <= i.indnkeyatts
              ) = array['farmacia', 'id_contador']::name[]
        ) as garantia_unique_efectiva,
        (
            select count(*)
            from (
                select farmacia, id_contador
                from public.albaranes
                group by farmacia, id_contador
                having count(*) > 1
            ) as duplicados
        ) as duplicados_materiales
) as estado;

select
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types,
    public = false as bucket_privado
from storage.buckets
where id = 'facturas-pdf';

select
    table_schema,
    table_name,
    grantee,
    privilege_type,
    is_grantable
from information_schema.role_table_grants
where table_schema in ('public', 'storage')
  and table_name in (
      'documentos_facturas',
      'facturas',
      'facturas_vencimientos',
      'facturas_impuestos',
      'facturas_albaranes_extraidos',
      'facturas_ajustes',
      'albaranes',
      'buckets'
  )
order by table_schema, table_name, grantee, privilege_type;

select
    routine_schema,
    routine_name,
    routine_type,
    data_type
from information_schema.routines
where routine_schema = 'public'
  and routine_name like 'cf\_%' escape '\'
order by routine_name;

select
    routine_schema,
    routine_name,
    grantee,
    privilege_type,
    is_grantable
from information_schema.role_routine_grants
where routine_schema = 'public'
  and routine_name like 'cf\_%' escape '\'
order by routine_name, grantee, privilege_type;
-- Contrato semantico de estado_lectura; ningun resultado desconocido habilita V1.
select
    coalesce(i.columna_valida and i.checks_en_columna=1
        and i.forma_reconocida, false) as check_reconocido,
    i.constraint_name, i.expresion, i.valores_permitidos,
    d.valores_inesperados,
    case when i.columna_valida and i.checks_en_columna=1
              and i.forma_reconocida and d.valores_inesperados=0
              and i.valores_permitidos=array['ERROR','EXTRAIDA','PENDIENTE','PROCESANDO','REVISION']::text[]
         then 'ESTADO_LECTURA_LEGACY_COMPATIBLE_PARA_MIGRAR'
         when i.columna_valida and i.checks_en_columna=1
              and i.forma_reconocida and d.valores_inesperados=0
              and i.valores_permitidos=array['ERROR','EXTRAIDA','NORMALIZADA','NORMALIZANDO','PENDIENTE','PROCESANDO','REVISION']::text[]
         then 'ESTADO_LECTURA_V1_COMPATIBLE'
         else 'BLOQUEADO_ESTADO_LECTURA_DESCONOCIDO'
    end as estado_compatibilidad,
    coalesce(i.valores_permitidos=array['ERROR','EXTRAIDA','PENDIENTE','PROCESANDO','REVISION']::text[], false) as requiere_08b,
    coalesce(i.columna_valida and i.checks_en_columna=1
        and i.forma_reconocida and d.valores_inesperados=0
        and i.valores_permitidos=array['ERROR','EXTRAIDA','NORMALIZADA','NORMALIZANDO','PENDIENTE','PROCESANDO','REVISION']::text[], false) as estado_lectura_v1_ok
from (select 1) as base
left join lateral (
select
    a.attnotnull and a.atttypid = 'text'::regtype as columna_valida,
    count(c.oid) as checks_en_columna,
    min(c.conname::text) as constraint_name,
    bool_and(c.convalidated and not c.connoinherit
        and c.conkey = array[a.attnum]::smallint[]
        and regexp_replace(pg_get_expr(c.conbin,c.conrelid), '[[:space:]]', '', 'g')
          ~ '^\(estado_lectura=ANY\(ARRAY\[''[A-Z_]+''::text(,''[A-Z_]+''::text)*\]\)\)$'
    ) as forma_reconocida,
    min(pg_get_expr(c.conbin,c.conrelid)) as expresion,
    array(
        select distinct m[1]
        from regexp_matches(min(pg_get_expr(c.conbin,c.conrelid)), '''([A-Z_]+)''', 'g') m
        order by m[1]
    ) as valores_permitidos
from pg_attribute a
left join pg_constraint c on c.conrelid=a.attrelid
    and c.contype='c' and a.attnum=any(c.conkey)
where a.attrelid=to_regclass('public.documentos_facturas')
    and a.attname='estado_lectura' and not a.attisdropped
group by a.attnum,a.attnotnull,a.atttypid
) as i on true
cross join (
    select count(*) as valores_inesperados
    from public.documentos_facturas
    where estado_lectura is null
       or not (estado_lectura=any(array['ERROR','EXTRAIDA','NORMALIZADA','NORMALIZANDO','PENDIENTE','PROCESANDO','REVISION']::text[]))
) as d;
