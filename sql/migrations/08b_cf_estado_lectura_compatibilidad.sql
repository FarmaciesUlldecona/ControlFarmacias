begin;
set local lock_timeout = '5s';

-- Serializa inspeccion, comprobacion de filas y sustitucion de CHECK.
lock table public.documentos_facturas in access exclusive mode;
do $migration$
declare
    v record;
begin
    if exists (
        select 1 from public.documentos_facturas
        where estado_lectura is null
           or not (estado_lectura = any(array['ERROR','EXTRAIDA','NORMALIZADA','NORMALIZANDO','PENDIENTE','PROCESANDO','REVISION']::text[]))
    ) then
        raise exception 'MIGRACION_08B_BLOQUEADA: valores actuales fuera del contrato';
    end if;

    select * into v from (
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
    ) as inspeccion;
    if v is null or v.columna_valida is not true
       or v.checks_en_columna <> 1 or v.forma_reconocida is not true
       or not (v.valores_permitidos = array['ERROR','EXTRAIDA','PENDIENTE','PROCESANDO','REVISION']::text[]
               or v.valores_permitidos = array['ERROR','EXTRAIDA','NORMALIZADA','NORMALIZANDO','PENDIENTE','PROCESANDO','REVISION']::text[]) then
        raise exception 'MIGRACION_08B_BLOQUEADA: CHECK desconocido, ausente, multiple o no validado';
    end if;
    if v.valores_permitidos = array['ERROR','EXTRAIDA','NORMALIZADA','NORMALIZANDO','PENDIENTE','PROCESANDO','REVISION']::text[] then
        return;
    end if;
    if exists (
        select 1 from pg_constraint
        where conrelid='public.documentos_facturas'::regclass
          and conname='cf_documentos_estado_lectura_check'
          and conname <> v.constraint_name
    ) then
        raise exception 'MIGRACION_08B_BLOQUEADA: nombre destino ocupado';
    end if;

    execute format('alter table public.documentos_facturas drop constraint %I', v.constraint_name);
    alter table public.documentos_facturas
        add constraint cf_documentos_estado_lectura_check
        check (estado_lectura in (
            'PENDIENTE','PROCESANDO','EXTRAIDA','REVISION','ERROR',
            'NORMALIZANDO','NORMALIZADA'
        ));
end;
$migration$;
commit;
