\set ON_ERROR_STOP on

do $$
declare
    v_tipo text;
    v_total integer;
begin
    foreach v_tipo in array array[
        'documentos_facturas', 'facturas', 'facturas_vencimientos',
        'facturas_impuestos', 'facturas_albaranes_extraidos',
        'facturas_ajustes', 'albaranes', 'proveedores',
        'normalizacion_ejecuciones', 'facturas_movimientos',
        'facturas_incidencias', 'historial_facturas',
        'conciliaciones', 'conciliacion_detalles'
    ] loop
        if to_regclass('public.' || v_tipo) is null then
            raise exception 'tabla ausente: %', v_tipo;
        end if;
    end loop;

    select count(*) into v_total
    from information_schema.columns
    where table_schema = 'public' and table_name = 'albaranes'
      and column_name = 'id_proveedor' and data_type = 'text';
    if v_total <> 1 then raise exception 'albaranes.id_proveedor no es text'; end if;

    select count(*) into v_total
    from information_schema.columns
    where table_schema = 'public' and table_name = 'facturas'
      and column_name = 'id_proveedor_albaranes' and data_type = 'text';
    if v_total <> 1 then raise exception 'facturas.id_proveedor_albaranes no es text'; end if;

    if (select count(*) from public.documentos_facturas where farmacia = 'PIO') <> 112 then
        raise exception 'seed PIO distinto de 112';
    end if;
    if (select array_agg(id_proveedor order by id_contador)
        from public.albaranes where farmacia = 'PIO' and id_contador <= 4)
       is distinct from array['123', '00123', 'ABC123', '00001']::text[] then
        raise exception 'id_proveedor no conserva literales';
    end if;

    if (select farmacias_habilitadas from public.cf_configuracion where id)
       <> array['PIO']::text[] then raise exception 'alcance inicial no es PIO'; end if;
    if (select normalizacion_automatica or conciliacion_automatica or luna_habilitada
        from public.cf_configuracion where id) then
        raise exception 'feature flag activada';
    end if;

    if (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relname in
        ('documentos_facturas','facturas','normalizacion_ejecuciones',
         'facturas_movimientos','facturas_incidencias','historial_facturas',
         'conciliaciones','conciliacion_detalles') and c.relrowsecurity) <> 8 then
        raise exception 'RLS incompleto';
    end if;

    if (select count(*) from pg_policies where schemaname = 'public') < 12 then
        raise exception 'politicas RLS incompletas';
    end if;
    if to_regprocedure('public.cf_persistir_normalizacion(uuid,text,text,text,text,jsonb)') is null
       or to_regprocedure('public.cf_reclamar_documento_normalizacion(text,integer)') is null
       or to_regprocedure('public.cf_reclamar_factura_conciliacion(text,integer)') is null then
        raise exception 'RPC requerida ausente';
    end if;
    if to_regclass('public.v_facturas_listado') is null
       or to_regclass('public.v_dashboard_diario') is null
       or to_regclass('public.v_vencimientos_calendario') is null then
        raise exception 'vista requerida ausente';
    end if;

    select count(*) into v_total from pg_constraint con
    join pg_namespace n on n.oid = con.connamespace
    where n.nspname = 'public' and con.contype in ('p','f','u','c');
    if v_total < 25 then raise exception 'PK/FK/UNIQUE/CHECK insuficientes'; end if;

    select count(*) into v_total from pg_indexes where schemaname = 'public';
    if v_total < 20 then raise exception 'indices insuficientes'; end if;

    if not exists (
        select 1 from information_schema.role_table_grants
        where grantee = 'authenticated' and table_schema = 'public'
          and table_name = 'facturas' and privilege_type = 'SELECT'
    ) then raise exception 'grant SELECT facturas ausente'; end if;

    begin
        insert into public.proveedores_alias (proveedor_id, alias)
        select proveedor_id, lower(alias) from public.proveedores_alias limit 1;
        raise exception 'alias case-insensitive permitio duplicado';
    exception when unique_violation then
        null;
    end;
end;
$$;

select 'VALIDACION_MIGRACIONES_07_12_OK' as resultado;
