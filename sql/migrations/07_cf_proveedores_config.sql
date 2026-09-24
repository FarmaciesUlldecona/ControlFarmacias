begin;

create or replace function public.cf_set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create table if not exists public.proveedores (
    id uuid primary key default gen_random_uuid(),
    codigo text not null unique,
    nombre text not null,
    farmatic_id_proveedor text,
    extractor_codigo text,
    nivel_confianza text not null default 'NO_VERIFICADO'
        check (nivel_confianza in ('NO_VERIFICADO', 'DOCUMENTAL', 'PIO_VALIDADO')),
    activo boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists proveedores_codigo_ci_unico
    on public.proveedores (lower(codigo));

create unique index if not exists proveedores_farmatic_id_unico
    on public.proveedores (farmatic_id_proveedor)
    where farmatic_id_proveedor is not null;

drop trigger if exists proveedores_set_updated_at on public.proveedores;
create trigger proveedores_set_updated_at
before update on public.proveedores
for each row execute function public.cf_set_updated_at();

create table if not exists public.proveedores_alias (
    id uuid primary key default gen_random_uuid(),
    proveedor_id uuid not null references public.proveedores(id) on delete cascade,
    alias text not null check (btrim(alias) <> ''),
    created_at timestamptz not null default now()
);

create unique index if not exists proveedores_alias_ci_unico
    on public.proveedores_alias (lower(btrim(alias)));

create index if not exists proveedores_alias_proveedor_idx
    on public.proveedores_alias (proveedor_id);

create table if not exists public.cf_configuracion (
    id boolean primary key default true check (id),
    normalizacion_automatica boolean not null default false,
    conciliacion_automatica boolean not null default false,
    luna_habilitada boolean not null default false,
    farmacias_habilitadas text[] not null default array['PIO']::text[]
        check (
            cardinality(farmacias_habilitadas) > 0
            and farmacias_habilitadas <@ array['PIO', 'RITA']::text[]
        ),
    preflight_indice_pio_reconciliado boolean not null default false,
    preflight_pio_hashes_sqlite integer
        check (preflight_pio_hashes_sqlite is null or preflight_pio_hashes_sqlite >= 0),
    preflight_pio_hashes_supabase integer
        check (preflight_pio_hashes_supabase is null or preflight_pio_hashes_supabase >= 0),
    preflight_pio_manifest_sqlite_sha256 text
        check (preflight_pio_manifest_sqlite_sha256 is null
            or preflight_pio_manifest_sqlite_sha256 ~ '^[0-9a-f]{64}$'),
    preflight_pio_manifest_supabase_sha256 text
        check (preflight_pio_manifest_supabase_sha256 is null
            or preflight_pio_manifest_supabase_sha256 ~ '^[0-9a-f]{64}$'),
    tolerancia_conciliacion numeric(14,4) not null default 0.0500
        check (tolerancia_conciliacion >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

insert into public.cf_configuracion (
    id,
    normalizacion_automatica,
    conciliacion_automatica,
    luna_habilitada,
    tolerancia_conciliacion
)
values (true, false, false, false, 0.0500)
on conflict (id) do nothing;

create or replace function public.cf_preflight_pio_valido()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    with hashes_pio as (
        select lower(archivo_hash) as archivo_hash
        from public.documentos_facturas
        where farmacia = 'PIO'
    ),
    estado_vivo as (
        select
            count(*) filter (
                where archivo_hash is null
                   or archivo_hash !~ '^[0-9a-f]{64}$'
            ) as hashes_invalidos,
            count(distinct archivo_hash)::integer as hashes_unicos
        from hashes_pio
    ),
    manifiesto_vivo as (
        select encode(
            extensions.digest(coalesce(string_agg(archivo_hash, E'\n' order by archivo_hash), ''), 'sha256'),
            'hex'
        ) as sha256
        from (select distinct archivo_hash from hashes_pio) unicos
    )
    select coalesce(
        c.preflight_indice_pio_reconciliado
        and e.hashes_invalidos = 0
        and c.preflight_pio_hashes_sqlite = c.preflight_pio_hashes_supabase
        and c.preflight_pio_hashes_supabase = e.hashes_unicos
        and c.preflight_pio_manifest_sqlite_sha256
            = c.preflight_pio_manifest_supabase_sha256
        and c.preflight_pio_manifest_supabase_sha256 = m.sha256
        and c.farmacias_habilitadas = array['PIO']::text[],
        false
    )
    from public.cf_configuracion c
    cross join estado_vivo e
    cross join manifiesto_vivo m
    where c.id = true;
$$;

revoke all on function public.cf_preflight_pio_valido()
    from public, anon, authenticated;
grant execute on function public.cf_preflight_pio_valido()
    to service_role;

drop trigger if exists cf_configuracion_set_updated_at on public.cf_configuracion;
create trigger cf_configuracion_set_updated_at
before update on public.cf_configuracion
for each row execute function public.cf_set_updated_at();

comment on table public.proveedores is
    'Catalogo funcional; no concede autoridad productiva a extractores.';

comment on table public.cf_configuracion is
    'Interruptores productivos. Todas las automatizaciones quedan apagadas inicialmente.';

comment on column public.proveedores.farmatic_id_proveedor is
    'Literal exacto de albaranes.id_proveedor; conserva ceros iniciales y codigos alfanumericos.';

comment on column public.cf_configuracion.farmacias_habilitadas is
    'Aislamiento desplegable. Inicialmente solo PIO; RITA requiere activacion futura explicita.';

comment on column public.cf_configuracion.preflight_indice_pio_reconciliado is
    'Atestacion externa canonica: SHA-256 unicos PIO, ordenados y unidos por LF. RITA excluida.';

comment on function public.cf_preflight_pio_valido() is
    'Guard verificable de conteos y manifiestos PIO; no consulta ni altera entradas RITA.';

commit;
