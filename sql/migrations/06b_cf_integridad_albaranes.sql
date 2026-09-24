begin;

do $$
declare
    v_garantia_equivalente boolean;
    v_hay_duplicados boolean;
begin
    select exists (
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
    ) into v_garantia_equivalente;

    if v_garantia_equivalente then
        return;
    end if;

    select exists (
        select 1
        from public.albaranes
        group by farmacia, id_contador
        having count(*) > 1
    ) into v_hay_duplicados;

    if v_hay_duplicados then
        raise exception using
            errcode = '23505',
            message = 'MIGRACION_06B_BLOQUEADA: existen duplicados en albaranes(farmacia,id_contador)',
            hint = 'No se han borrado, fusionado ni corregido filas; resolver los duplicados mediante un procedimiento autorizado.';
    end if;

    if exists (
        select 1
        from pg_constraint con
        join pg_class t on t.oid = con.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public'
          and t.relname = 'albaranes'
          and con.conname = 'albaranes_farmacia_id_contador_unico'
    ) or to_regclass('public.albaranes_farmacia_id_contador_unico') is not null then
        raise exception
            'MIGRACION_06B_BLOQUEADA: el nombre albaranes_farmacia_id_contador_unico ya esta ocupado por una garantia no equivalente';
    end if;

    alter table public.albaranes
        add constraint albaranes_farmacia_id_contador_unico
        unique (farmacia, id_contador);
end;
$$;

commit;
