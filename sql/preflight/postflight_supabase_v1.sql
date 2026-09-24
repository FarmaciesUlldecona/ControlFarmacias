-- POSTFLIGHT V1: ejecutar despues de aplicar 07 a 12 y antes de 13.
-- Este archivo es deliberadamente 100 % SELECT.

select
    esperado.table_name,
    to_regclass('public.' || esperado.table_name) is not null as existe,
    'REQUERIDO_DESPUES_12' as expectativa
from (
    values
        ('proveedores'),
        ('proveedores_alias'),
        ('cf_configuracion'),
        ('normalizacion_ejecuciones'),
        ('facturas_movimientos'),
        ('facturas_incidencias'),
        ('historial_facturas'),
        ('conciliaciones'),
        ('conciliacion_detalles')
) as esperado(table_name)
order by esperado.table_name;

select
    esperado.view_name,
    to_regclass('public.' || esperado.view_name) is not null as existe,
    'REQUERIDA_DESPUES_12' as expectativa
from (
    values
        ('v_facturas_listado'),
        ('v_dashboard_diario'),
        ('v_vencimientos_calendario'),
        ('v_proveedores_estado')
) as esperado(view_name)
order by esperado.view_name;

select
    esperado.routine_name,
    exists (
        select 1
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'public'
          and p.proname = esperado.routine_name
    ) as existe,
    'REQUERIDA_DESPUES_12' as expectativa
from (
    values
        ('cf_set_updated_at'),
        ('cf_preflight_pio_valido'),
        ('cf_reclamar_documento_normalizacion'),
        ('cf_historial_append_only'),
        ('cf_resultado_conciliacion'),
        ('cf_evaluar_elegibilidad_conciliacion'),
        ('cf_reclamar_factura_conciliacion'),
        ('cf_persistir_normalizacion'),
        ('cf_registrar_fallo_normalizacion'),
        ('cf_validar_factura'),
        ('cf_desvalidar_factura'),
        ('cf_solicitar_reprocesado'),
        ('cf_solicitar_reintento_conciliacion'),
        ('cf_reintentar_todas_pendientes')
) as esperado(routine_name)
order by esperado.routine_name;

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
      'proveedores',
      'proveedores_alias',
      'cf_configuracion',
      'normalizacion_ejecuciones',
      'facturas_movimientos',
      'facturas_incidencias',
      'historial_facturas',
      'conciliaciones',
      'conciliacion_detalles'
  )
order by table_name, ordinal_position;

select
    esperado.table_name,
    esperado.column_name,
    c.data_type,
    c.udt_name,
    c.is_nullable,
    c.column_default,
    c.numeric_precision,
    c.numeric_scale,
    c.column_name is not null as existe
from (
    values
        ('documentos_facturas', 'proximo_reintento_at'),
        ('documentos_facturas', 'bloqueado_hasta'),
        ('documentos_facturas', 'bloqueado_por'),
        ('documentos_facturas', 'ultimo_error_codigo'),
        ('documentos_facturas', 'reprocesar_solicitado_at'),
        ('documentos_facturas', 'procesamiento_version'),
        ('facturas', 'proyeccion_clave'),
        ('facturas', 'proveedor_id'),
        ('facturas', 'proveedor_literal'),
        ('facturas', 'estado_normalizacion'),
        ('facturas', 'estado_conciliacion_cf'),
        ('facturas', 'estado_revision'),
        ('facturas', 'normalizacion_ejecucion_id'),
        ('facturas', 'provenance'),
        ('facturas', 'conciliacion_intentos'),
        ('facturas', 'conciliacion_proximo_at'),
        ('facturas', 'conciliacion_bloqueado_hasta'),
        ('facturas', 'conciliacion_bloqueado_por'),
        ('facturas', 'conciliacion_ultimo_error'),
        ('facturas', 'conciliacion_reintento_solicitado_at'),
        ('facturas', 'updated_at'),
        ('facturas_vencimientos', 'provenance'),
        ('facturas_vencimientos', 'literal'),
        ('facturas_impuestos', 'total_tramo'),
        ('facturas_impuestos', 'provenance'),
        ('facturas_impuestos', 'literal'),
        ('facturas_albaranes_extraidos', 'provenance'),
        ('facturas_albaranes_extraidos', 'literal'),
        ('facturas_ajustes', 'provenance'),
        ('facturas_ajustes', 'literal')
) as esperado(table_name, column_name)
left join information_schema.columns c
  on c.table_schema = 'public'
 and c.table_name = esperado.table_name
 and c.column_name = esperado.column_name
order by esperado.table_name, esperado.column_name;

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
      'proveedores',
      'proveedores_alias',
      'cf_configuracion',
      'normalizacion_ejecuciones',
      'facturas_movimientos',
      'facturas_incidencias',
      'historial_facturas',
      'conciliaciones',
      'conciliacion_detalles'
  )
order by c.relname, con.contype, con.conname;

select
    esperado.constraint_name,
    con.contype as constraint_type,
    pg_get_constraintdef(con.oid, true) as definition,
    con.oid is not null as existe
from (
    values
        ('facturas_estado_normalizacion_check'),
        ('facturas_estado_conciliacion_cf_check'),
        ('facturas_estado_revision_check'),
        ('facturas_conciliacion_intentos_check'),
        ('facturas_normalizacion_ejecucion_fk'),
        ('normalizacion_ejecuciones_documento_intento_unico'),
        ('normalizacion_ejecuciones_documento_idempotency_unico'),
        ('facturas_movimientos_orden_unico'),
        ('facturas_incidencias_ambito_check'),
        ('historial_facturas_ambito_check'),
        ('conciliaciones_factura_intento_unico'),
        ('conciliacion_detalles_orden_unico'),
        ('conciliacion_detalles_origen_check'),
        ('conciliacion_detalles_albaran_operacional_check')
) as esperado(constraint_name)
left join pg_constraint con on con.conname = esperado.constraint_name
order by esperado.constraint_name;

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
      'proveedores',
      'proveedores_alias',
      'cf_configuracion',
      'normalizacion_ejecuciones',
      'facturas_movimientos',
      'facturas_incidencias',
      'historial_facturas',
      'conciliaciones',
      'conciliacion_detalles'
  )
order by tablename, indexname;

select
    esperado.indexname,
    i.indexdef,
    i.indexname is not null as existe
from (
    values
        ('proveedores_codigo_ci_unico'),
        ('proveedores_farmatic_id_unico'),
        ('proveedores_alias_ci_unico'),
        ('proveedores_alias_proveedor_idx'),
        ('documentos_facturas_cola_normalizacion_idx'),
        ('facturas_proveedor_cf_idx'),
        ('facturas_documento_proyeccion_clave_unico'),
        ('facturas_estado_normalizacion_idx'),
        ('facturas_cola_conciliacion_idx'),
        ('facturas_estado_revision_cf_idx'),
        ('normalizacion_ejecuciones_documento_idx'),
        ('normalizacion_ejecuciones_estado_idx'),
        ('facturas_movimientos_factura_idx'),
        ('facturas_incidencias_documento_idx'),
        ('facturas_incidencias_factura_idx'),
        ('historial_facturas_documento_idx'),
        ('historial_facturas_factura_idx'),
        ('conciliaciones_actual_factura_unico'),
        ('conciliaciones_factura_idx'),
        ('conciliacion_detalles_conciliacion_idx'),
        ('conciliacion_detalles_albaran_idx')
) as esperado(indexname)
left join pg_indexes i
  on i.schemaname = 'public'
 and i.indexname = esperado.indexname
order by esperado.indexname;

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
      'proveedores',
      'proveedores_alias',
      'cf_configuracion',
      'normalizacion_ejecuciones',
      'facturas_movimientos',
      'facturas_incidencias',
      'historial_facturas',
      'conciliaciones',
      'conciliacion_detalles'
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
      'proveedores',
      'proveedores_alias',
      'cf_configuracion',
      'normalizacion_ejecuciones',
      'facturas_movimientos',
      'facturas_incidencias',
      'historial_facturas',
      'conciliaciones',
      'conciliacion_detalles'
  )
order by tablename, policyname;

select
    esperado.policyname,
    p.tablename,
    p.roles,
    p.cmd,
    p.qual,
    p.with_check,
    p.policyname is not null as existe
from (
    values
        ('documentos_facturas_authenticated_select'),
        ('facturas_authenticated_select'),
        ('facturas_vencimientos_authenticated_select'),
        ('facturas_impuestos_authenticated_select'),
        ('facturas_albaranes_extraidos_authenticated_select'),
        ('facturas_ajustes_authenticated_select'),
        ('proveedores_authenticated_select'),
        ('proveedores_alias_authenticated_select'),
        ('cf_configuracion_authenticated_select'),
        ('normalizacion_ejecuciones_authenticated_select'),
        ('facturas_movimientos_authenticated_select'),
        ('facturas_incidencias_authenticated_select'),
        ('historial_facturas_authenticated_select'),
        ('conciliaciones_authenticated_select'),
        ('conciliacion_detalles_authenticated_select')
) as esperado(policyname)
left join pg_policies p
  on p.schemaname = 'public'
 and p.policyname = esperado.policyname
order by esperado.policyname;

select
    table_schema,
    table_name,
    grantee,
    privilege_type,
    is_grantable
from information_schema.role_table_grants
where table_schema = 'public'
  and table_name in (
      'documentos_facturas',
      'facturas',
      'facturas_vencimientos',
      'facturas_impuestos',
      'facturas_albaranes_extraidos',
      'facturas_ajustes',
      'proveedores',
      'proveedores_alias',
      'cf_configuracion',
      'normalizacion_ejecuciones',
      'facturas_movimientos',
      'facturas_incidencias',
      'historial_facturas',
      'conciliaciones',
      'conciliacion_detalles',
      'v_facturas_listado',
      'v_dashboard_diario',
      'v_vencimientos_calendario',
      'v_proveedores_estado'
  )
order by table_name, grantee, privilege_type;

select
    routine_schema,
    routine_name,
    routine_type,
    data_type,
    security_type
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

select
    n.nspname as schema_name,
    c.relname as view_name,
    pg_get_viewdef(c.oid, true) as definition
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'v'
  and c.relname in (
      'v_facturas_listado',
      'v_dashboard_diario',
      'v_vencimientos_calendario',
      'v_proveedores_estado'
  )
order by c.relname;

select
    normalizacion_automatica,
    conciliacion_automatica,
    luna_habilitada,
    farmacias_habilitadas,
    normalizacion_automatica = false as normalizacion_automatica_segura,
    conciliacion_automatica = false as conciliacion_automatica_segura,
    luna_habilitada = false as luna_habilitada_segura,
    farmacias_habilitadas = array['PIO']::text[] as solo_pio_habilitada,
    preflight_indice_pio_reconciliado,
    preflight_pio_hashes_sqlite,
    preflight_pio_hashes_supabase,
    preflight_pio_manifest_sqlite_sha256,
    preflight_pio_manifest_supabase_sha256,
    tolerancia_conciliacion
from public.cf_configuracion
where id = true;

-- Contrasta la atestacion con el estado vivo canonico de documentos PIO.
select * from (with hashes_pio as (
    select lower(archivo_hash) as archivo_hash
    from public.documentos_facturas
    where farmacia = 'PIO'
), unicos as (
    select distinct archivo_hash
    from hashes_pio
    where archivo_hash ~ '^[0-9a-f]{64}$'
), vivo as (
    select
        count(*) as hashes_unicos,
        encode(extensions.digest(coalesce(string_agg(archivo_hash, E'\n' order by archivo_hash), ''), 'sha256'), 'hex') as manifiesto
    from unicos
)
select
    v.hashes_unicos as pio_hashes_unicos_vivos,
    (select count(*) from hashes_pio
      where archivo_hash is null or archivo_hash !~ '^[0-9a-f]{64}$') as pio_hashes_invalidos,
    v.manifiesto as manifiesto_supabase_pio_canonico,
    c.preflight_pio_hashes_supabase = v.hashes_unicos as conteo_atestado_coincide_vivo,
    c.preflight_pio_manifest_supabase_sha256 = v.manifiesto as manifiesto_atestado_coincide_vivo,
    public.cf_preflight_pio_valido() as guard_13_valido
from vivo v
cross join public.cf_configuracion c
where c.id = true) as guard_canonico;

select 'proveedores' as table_name, count(*) as row_count from public.proveedores
union all
select 'proveedores_alias', count(*) from public.proveedores_alias
union all
select 'cf_configuracion', count(*) from public.cf_configuracion
union all
select 'normalizacion_ejecuciones', count(*) from public.normalizacion_ejecuciones
union all
select 'facturas_movimientos', count(*) from public.facturas_movimientos
union all
select 'facturas_incidencias', count(*) from public.facturas_incidencias
union all
select 'historial_facturas', count(*) from public.historial_facturas
union all
select 'conciliaciones', count(*) from public.conciliaciones
union all
select 'conciliacion_detalles', count(*) from public.conciliacion_detalles
order by table_name;

select 'v_facturas_listado' as view_name, count(*) as row_count
from public.v_facturas_listado
union all
select 'v_dashboard_diario', count(*) from public.v_dashboard_diario
union all
select 'v_vencimientos_calendario', count(*) from public.v_vencimientos_calendario
union all
select 'v_proveedores_estado', count(*) from public.v_proveedores_estado
order by view_name;

select
    id,
    name,
    public,
    file_size_limit,
    allowed_mime_types,
    public = false as bucket_privado
from storage.buckets
where id = 'facturas-pdf';
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
