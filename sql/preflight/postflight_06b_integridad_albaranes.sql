-- Ejecutar despues de 06b y antes de 07. Es 100 % SELECT.

select
    estado.garantia_unique_efectiva,
    estado.duplicados_materiales,
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
    i.indexrelid::regclass as garantia,
    i.indisunique,
    i.indisvalid,
    i.indisready,
    (
        select array_agg(a.attname order by k.ordinality)
        from unnest(i.indkey) with ordinality as k(attnum, ordinality)
        join pg_attribute a
          on a.attrelid = t.oid
         and a.attnum = k.attnum
        where k.ordinality <= i.indnkeyatts
    ) as columnas
from pg_index i
join pg_class t on t.oid = i.indrelid
join pg_namespace n on n.oid = t.relnamespace
where n.nspname = 'public'
  and t.relname = 'albaranes'
  and i.indisunique
order by i.indexrelid::regclass::text;
