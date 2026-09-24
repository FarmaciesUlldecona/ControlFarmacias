\set ON_ERROR_STOP on

do $$
begin
    if public.cf_preflight_pio_valido() then
        raise exception 'guard deberia iniciar bloqueado';
    end if;

    update public.cf_configuracion
       set preflight_indice_pio_reconciliado=true,
           preflight_pio_hashes_sqlite=(select count(distinct archivo_hash) from public.documentos_facturas where farmacia='PIO'),
           preflight_pio_hashes_supabase=(select count(distinct archivo_hash) from public.documentos_facturas where farmacia='PIO'),
           preflight_pio_manifest_sqlite_sha256=repeat('a',64),
           preflight_pio_manifest_supabase_sha256=repeat('b',64)
     where id=true;
    if public.cf_preflight_pio_valido() then
        raise exception 'manifiesto incorrecto no bloqueo';
    end if;

    -- Dos atestaciones iguales pero distintas del conteo vivo tambien bloquean.
    update public.cf_configuracion
       set preflight_pio_hashes_sqlite=preflight_pio_hashes_sqlite + 1,
           preflight_pio_hashes_supabase=preflight_pio_hashes_supabase + 1,
           preflight_pio_manifest_sqlite_sha256=repeat('a',64),
           preflight_pio_manifest_supabase_sha256=repeat('a',64)
     where id=true;
    if public.cf_preflight_pio_valido() then
        raise exception 'atestaciones concordantes pero ajenas al estado vivo no bloquearon';
    end if;

    update public.cf_configuracion
       set preflight_pio_hashes_sqlite=(select count(distinct archivo_hash) from public.documentos_facturas where farmacia='PIO'),
           preflight_pio_hashes_supabase=(select count(distinct archivo_hash) from public.documentos_facturas where farmacia='PIO'),
           preflight_pio_manifest_sqlite_sha256=(
               select encode(extensions.digest(string_agg(archivo_hash, E'\n' order by archivo_hash), 'sha256'), 'hex')
               from (select distinct lower(archivo_hash) archivo_hash from public.documentos_facturas where farmacia='PIO') h
           ),
           preflight_pio_manifest_supabase_sha256=(
               select encode(extensions.digest(string_agg(archivo_hash, E'\n' order by archivo_hash), 'sha256'), 'hex')
               from (select distinct lower(archivo_hash) archivo_hash from public.documentos_facturas where farmacia='PIO') h
           )
     where id=true;
    if not public.cf_preflight_pio_valido() then
        raise exception 'atestacion PIO correcta no habilito guard';
    end if;
end;
$$;

\ir ../migrations/13_cf_backfill_compatibilidad.sql

do $$
begin
    if (select count(*) from public.documentos_facturas) <> 113 then
        raise exception 'backfill invento o borro documentos';
    end if;
    if exists (
        select 1 from public.facturas
        where farmacia='RITA' and estado_normalizacion <> 'PENDIENTE'
    ) then raise exception 'backfill modifico RITA'; end if;
    if (select count(*) from public.facturas_incidencias i
        join public.facturas f on f.id=i.factura_id
        where i.codigo='POSIBLE_DUPLICADO' and f.farmacia='PIO') <> 2 then
        raise exception 'POSIBLE_DUPLICADO PIO incorrecto';
    end if;
    if exists (
        select 1 from public.facturas_incidencias i
        join public.facturas f on f.id=i.factura_id
        where i.codigo='POSIBLE_DUPLICADO' and f.farmacia='RITA'
    ) then raise exception 'se genero incidencia RITA'; end if;
    if (select count(*) from public.historial_facturas h
        join public.facturas f on f.id=h.factura_id
        where h.evento='BACKFILL_COMPATIBILIDAD_V1' and f.farmacia='RITA') <> 0 then
        raise exception 'se genero historial RITA';
    end if;
    if exists (
        select 1 from public.facturas f
        join public.documentos_facturas d on d.id=f.documento_id
        group by f.id having count(distinct d.id) <> 1
    ) then raise exception 'backfill fusiono PDFs'; end if;
end;
$$;

select 'BACKFILL_PIO_OK_RITA_EXCLUIDA_SIN_DOCUMENTOS_INVENTADOS' as resultado;
