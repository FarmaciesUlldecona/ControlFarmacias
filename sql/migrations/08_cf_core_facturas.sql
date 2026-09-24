begin;

alter table public.documentos_facturas
    add column if not exists proximo_reintento_at timestamptz,
    add column if not exists bloqueado_hasta timestamptz,
    add column if not exists bloqueado_por text,
    add column if not exists ultimo_error_codigo text,
    add column if not exists reprocesar_solicitado_at timestamptz,
    add column if not exists procesamiento_version text;

create index if not exists documentos_facturas_cola_normalizacion_idx
    on public.documentos_facturas (
        estado_lectura,
        proximo_reintento_at,
        bloqueado_hasta,
        fecha_importacion
    );

alter table public.facturas
    add column if not exists proyeccion_clave text,
    add column if not exists proveedor_id uuid references public.proveedores(id),
    add column if not exists proveedor_literal text,
    add column if not exists estado_normalizacion text not null default 'PENDIENTE',
    add column if not exists estado_conciliacion_cf text not null default 'PENDIENTE_CONCILIAR',
    add column if not exists estado_revision text not null default 'NO_REQUERIDA',
    add column if not exists normalizacion_ejecucion_id uuid,
    add column if not exists provenance jsonb not null default '{}'::jsonb,
    add column if not exists conciliacion_intentos integer not null default 0,
    add column if not exists conciliacion_proximo_at timestamptz,
    add column if not exists conciliacion_bloqueado_hasta timestamptz,
    add column if not exists conciliacion_bloqueado_por text,
    add column if not exists conciliacion_ultimo_error text,
    add column if not exists updated_at timestamptz not null default now();

alter table public.facturas
    alter column id_proveedor_albaranes type text
        using id_proveedor_albaranes::text;

alter table public.facturas
    drop constraint if exists facturas_estado_normalizacion_check,
    add constraint facturas_estado_normalizacion_check
        check (estado_normalizacion in (
            'PENDIENTE',
            'NORMALIZANDO',
            'NORMALIZADA',
            'REQUIERE_REVISION'
        )),
    drop constraint if exists facturas_estado_conciliacion_cf_check,
    add constraint facturas_estado_conciliacion_cf_check
        check (estado_conciliacion_cf in (
            'PENDIENTE_CONCILIAR',
            'CONCILIADA'
        )),
    drop constraint if exists facturas_estado_revision_check,
    add constraint facturas_estado_revision_check
        check (estado_revision in (
            'NO_REQUERIDA',
            'PENDIENTE_REVISION_PIO',
            'VALIDADA_PIO'
        )),
    drop constraint if exists facturas_conciliacion_intentos_check,
    add constraint facturas_conciliacion_intentos_check
        check (conciliacion_intentos >= 0);

alter table public.facturas
    alter column base_imponible_total type numeric(14,4)
        using base_imponible_total::numeric(14,4),
    alter column iva_total type numeric(14,4)
        using iva_total::numeric(14,4),
    alter column recargo_equivalencia_total type numeric(14,4)
        using recargo_equivalencia_total::numeric(14,4),
    alter column importe_total type numeric(14,4)
        using importe_total::numeric(14,4),
    alter column diferencia_cuadre type numeric(14,4)
        using diferencia_cuadre::numeric(14,4),
    alter column diferencia_albaranes type numeric(14,4)
        using diferencia_albaranes::numeric(14,4);

alter table public.facturas_vencimientos
    alter column importe type numeric(14,4)
        using importe::numeric(14,4),
    add column if not exists provenance jsonb not null default '{}'::jsonb,
    add column if not exists literal text;

alter table public.facturas_impuestos
    alter column base_imponible type numeric(14,4)
        using base_imponible::numeric(14,4),
    alter column cuota_iva type numeric(14,4)
        using cuota_iva::numeric(14,4),
    alter column cuota_recargo_equivalencia type numeric(14,4)
        using cuota_recargo_equivalencia::numeric(14,4),
    add column if not exists total_tramo numeric(14,4),
    add column if not exists provenance jsonb not null default '{}'::jsonb,
    add column if not exists literal text;

alter table public.facturas_albaranes_extraidos
    alter column importe_base type numeric(14,4)
        using importe_base::numeric(14,4),
    alter column importe_total type numeric(14,4)
        using importe_total::numeric(14,4),
    alter column tipo_movimiento drop not null,
    alter column tipo_movimiento drop default,
    add column if not exists provenance jsonb not null default '{}'::jsonb,
    add column if not exists literal text;

alter table public.facturas_ajustes
    alter column importe type numeric(14,4)
        using importe::numeric(14,4),
    add column if not exists provenance jsonb not null default '{}'::jsonb,
    add column if not exists literal text;

drop trigger if exists facturas_cf_set_updated_at on public.facturas;
create trigger facturas_cf_set_updated_at
before update on public.facturas
for each row execute function public.cf_set_updated_at();

create index if not exists facturas_proveedor_cf_idx
    on public.facturas (proveedor_id);

create unique index if not exists facturas_documento_proyeccion_clave_unico
    on public.facturas (documento_id, proyeccion_clave);

create index if not exists facturas_estado_normalizacion_idx
    on public.facturas (farmacia, estado_normalizacion);

create index if not exists facturas_cola_conciliacion_idx
    on public.facturas (
        estado_conciliacion_cf,
        conciliacion_proximo_at,
        conciliacion_bloqueado_hasta
    );

create index if not exists facturas_estado_revision_cf_idx
    on public.facturas (farmacia, estado_revision);

comment on column public.facturas.estado_conciliacion_cf is
    'Estado ControlFarmacias V1; no sustituye estado_conciliacion legacy.';

comment on column public.facturas.proyeccion_clave is
    'factura_id estable de DocumentoNormalizado dentro del PDF; clave de idempotencia de la proyeccion actual.';

comment on column public.facturas.id_proveedor_albaranes is
    'Deuda legacy corregida a text: conserva literalmente albaranes.id_proveedor, incluido 00123 o ABC123.';

comment on column public.documentos_facturas.estado_lectura is
    'Estado tecnico agregado del PDF. NORMALIZADA significa lectura y persistencia coherentes; la revision economica vive en facturas.estado_normalizacion.';

commit;
