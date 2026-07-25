begin;

-- ============================================================
-- 1. LA TABLA ACTUAL "facturas" PASA A REPRESENTAR LOS PDF
-- ============================================================

alter table public.facturas
rename to documentos_facturas;


-- ============================================================
-- 2. RENOMBRAR RESTRICCIÓN E ÍNDICES EXISTENTES
-- ============================================================

alter table public.documentos_facturas
rename constraint facturas_archivo_hash_unico
to documentos_facturas_archivo_hash_unico;

alter index if exists public.facturas_proveedor_idx
rename to documentos_facturas_proveedor_idx;

alter index if exists public.facturas_fecha_idx
rename to documentos_facturas_fecha_idx;

alter index if exists public.facturas_conciliacion_idx
rename to documentos_facturas_conciliacion_idx;

alter index if exists public.facturas_pago_idx
rename to documentos_facturas_pago_idx;


-- ============================================================
-- 3. ELIMINAR ÍNDICES QUE YA NO PERTENECEN AL DOCUMENTO PDF
-- ============================================================

drop index if exists public.documentos_facturas_proveedor_idx;
drop index if exists public.documentos_facturas_fecha_idx;
drop index if exists public.documentos_facturas_conciliacion_idx;
drop index if exists public.documentos_facturas_pago_idx;


-- ============================================================
-- 4. LIMPIAR COLUMNAS ECONÓMICAS DE LA TABLA DE DOCUMENTOS
--    Actualmente las 65 filas están pendientes y no contienen
--    todavía datos extraídos, por lo que no se pierde información.
-- ============================================================

alter table public.documentos_facturas
    drop column if exists id_proveedor_albaranes,
    drop column if exists proveedor_nombre,
    drop column if exists proveedor_cif,
    drop column if exists numero_factura,
    drop column if exists fecha_factura,
    drop column if exists importe_total,
    drop column if exists base_imponible_total,
    drop column if exists iva_total,
    drop column if exists recargo_equivalencia_total,
    drop column if exists estado_conciliacion,
    drop column if exists estado_pago,
    drop column if exists diferencia_albaranes,
    drop column if exists diferencia_aceptada_automaticamente,
    drop column if exists validada_manualmente,
    drop column if exists validada_por,
    drop column if exists fecha_validacion;


-- ============================================================
-- 5. AÑADIR CAMPOS PROPIOS DEL PDF FÍSICO
-- ============================================================

alter table public.documentos_facturas
    add column if not exists numero_paginas integer,
    add column if not exists cantidad_documentos_detectados integer,
    add column if not exists tipo_contenido text
        check (
            tipo_contenido is null
            or tipo_contenido in (
                'FACTURA_UNICA',
                'LOTE_FACTURAS',
                'DOCUMENTO_NO_FISCAL',
                'DESCONOCIDO'
            )
        ),
    add column if not exists texto_extraido text,
    add column if not exists necesita_lectura_visual boolean
        not null default false,
    add column if not exists intentos_lectura integer
        not null default 0,
    add column if not exists ultimo_error_lectura text,
    add column if not exists fecha_inicio_lectura timestamptz,
    add column if not exists fecha_fin_lectura timestamptz;


-- ============================================================
-- 6. ÍNDICES DE DOCUMENTOS
-- ============================================================

create index if not exists documentos_facturas_estado_lectura_idx
    on public.documentos_facturas (
        farmacia,
        estado_lectura
    );

create index if not exists documentos_facturas_fecha_importacion_idx
    on public.documentos_facturas (
        farmacia,
        fecha_importacion
    );


-- ============================================================
-- 7. NUEVA TABLA DE FACTURAS ECONÓMICAS
--    Un PDF puede generar una o varias filas.
-- ============================================================

create table public.facturas (
    id uuid primary key default gen_random_uuid(),

    documento_id uuid not null
        references public.documentos_facturas(id)
        on delete cascade,

    farmacia text not null
        check (farmacia in ('PIO', 'RITA')),

    -- Localización dentro del PDF
    pagina_inicio integer,
    pagina_fin integer,

    -- Clasificación
    tipo_documento text not null default 'FACTURA'
        check (
            tipo_documento in (
                'FACTURA',
                'ABONO',
                'FACTURA_RECTIFICATIVA',
                'OTRO'
            )
        ),

    categoria text not null default 'MERCANCIA'
        check (
            categoria in (
                'MERCANCIA',
                'CUOTA_SERVICIO',
                'SUMINISTRO',
                'OTRO'
            )
        ),

    requiere_conciliacion_albaranes boolean
        not null default true,

    -- Proveedor
    id_proveedor_albaranes bigint,
    proveedor_nombre text,
    proveedor_cif text,

    -- Identificación fiscal
    numero_factura text,
    fecha_factura date,
    moneda text not null default 'EUR',

    -- Importes
    base_imponible_total numeric(14,2),
    iva_total numeric(14,2),
    recargo_equivalencia_total numeric(14,2),
    importe_total numeric(14,2),

    -- Validación matemática
    cuadre_fiscal_correcto boolean,
    diferencia_cuadre numeric(14,2),

    -- Calidad de extracción
    confianza_extraccion numeric(5,4)
        check (
            confianza_extraccion is null
            or (
                confianza_extraccion >= 0
                and confianza_extraccion <= 1
            )
        ),

    requiere_revision boolean not null default false,
    motivo_revision text,

    -- Conciliación con albaranes
    estado_conciliacion text not null default 'PENDIENTE'
        check (
            estado_conciliacion in (
                'PENDIENTE',
                'SIN_ALBARAN',
                'DISCREPANCIA',
                'CONCILIADA',
                'NO_APLICA'
            )
        ),

    diferencia_albaranes numeric(14,2),
    diferencia_aceptada_automaticamente boolean
        not null default false,

    -- Pago
    estado_pago text not null default 'SIN_PAGAR'
        check (
            estado_pago in (
                'SIN_PAGAR',
                'PAGO_PARCIAL',
                'PAGADA'
            )
        ),

    -- Validación manual
    validada_manualmente boolean not null default false,
    validada_por text,
    fecha_validacion timestamptz,

    observaciones text,
    datos_extraidos jsonb not null default '{}'::jsonb,

    fecha_creacion timestamptz not null default now(),
    fecha_actualizacion timestamptz not null default now(),

    constraint facturas_documento_numero_pagina_unico
        unique (
            documento_id,
            numero_factura,
            pagina_inicio
        )
);


-- ============================================================
-- 8. VENCIMIENTOS
-- ============================================================

create table public.facturas_vencimientos (
    id uuid primary key default gen_random_uuid(),

    factura_id uuid not null
        references public.facturas(id)
        on delete cascade,

    fecha_vencimiento date,
    importe numeric(14,2),

    orden integer not null default 1,

    confianza_extraccion numeric(5,4)
        check (
            confianza_extraccion is null
            or (
                confianza_extraccion >= 0
                and confianza_extraccion <= 1
            )
        ),

    fecha_creacion timestamptz not null default now(),

    constraint facturas_vencimientos_orden_unico
        unique (factura_id, orden)
);


-- ============================================================
-- 9. DESGLOSE DE IVA Y RECARGO DE EQUIVALENCIA
-- ============================================================

create table public.facturas_impuestos (
    id uuid primary key default gen_random_uuid(),

    factura_id uuid not null
        references public.facturas(id)
        on delete cascade,

    concepto text,

    base_imponible numeric(14,2),

    tipo_iva numeric(6,3),
    cuota_iva numeric(14,2),

    tipo_recargo_equivalencia numeric(6,3),
    cuota_recargo_equivalencia numeric(14,2),

    orden integer not null default 1,

    confianza_extraccion numeric(5,4)
        check (
            confianza_extraccion is null
            or (
                confianza_extraccion >= 0
                and confianza_extraccion <= 1
            )
        ),

    fecha_creacion timestamptz not null default now(),

    constraint facturas_impuestos_orden_unico
        unique (factura_id, orden)
);


-- ============================================================
-- 10. ALBARANES LEÍDOS EN EL PDF
-- ============================================================

create table public.facturas_albaranes_extraidos (
    id uuid primary key default gen_random_uuid(),

    factura_id uuid not null
        references public.facturas(id)
        on delete cascade,

    numero_albaran text,
    fecha_albaran date,

    tipo_movimiento text not null default 'CARGO'
        check (
            tipo_movimiento in (
                'CARGO',
                'ABONO'
            )
        ),

    importe_base numeric(14,2),
    importe_total numeric(14,2),

    descripcion text,
    orden integer not null default 1,

    confianza_extraccion numeric(5,4)
        check (
            confianza_extraccion is null
            or (
                confianza_extraccion >= 0
                and confianza_extraccion <= 1
            )
        ),

    fecha_creacion timestamptz not null default now(),

    constraint facturas_albaranes_extraidos_orden_unico
        unique (factura_id, orden)
);


-- ============================================================
-- 11. AJUSTES, BONIFICACIONES Y OTROS CONCEPTOS
-- ============================================================

create table public.facturas_ajustes (
    id uuid primary key default gen_random_uuid(),

    factura_id uuid not null
        references public.facturas(id)
        on delete cascade,

    tipo_ajuste text not null
        check (
            tipo_ajuste in (
                'DESCUENTO',
                'BONIFICACION',
                'CONDICION_OPERATIVA',
                'GASTO',
                'DEDUCCION',
                'OTRO'
            )
        ),

    descripcion text,
    importe numeric(14,2),

    incluido_en_base boolean,
    incluido_en_total boolean,

    orden integer not null default 1,

    confianza_extraccion numeric(5,4)
        check (
            confianza_extraccion is null
            or (
                confianza_extraccion >= 0
                and confianza_extraccion <= 1
            )
        ),

    fecha_creacion timestamptz not null default now(),

    constraint facturas_ajustes_orden_unico
        unique (factura_id, orden)
);


-- ============================================================
-- 12. ÍNDICES DE LAS NUEVAS TABLAS
-- ============================================================

create index facturas_documento_idx
    on public.facturas (documento_id);

create index facturas_proveedor_idx
    on public.facturas (
        farmacia,
        id_proveedor_albaranes
    );

create index facturas_numero_idx
    on public.facturas (
        farmacia,
        numero_factura
    );

create index facturas_fecha_idx
    on public.facturas (
        farmacia,
        fecha_factura
    );

create index facturas_conciliacion_idx
    on public.facturas (
        farmacia,
        estado_conciliacion
    );

create index facturas_pago_idx
    on public.facturas (
        farmacia,
        estado_pago
    );

create index facturas_revision_idx
    on public.facturas (
        farmacia,
        requiere_revision
    );

create index facturas_vencimientos_factura_idx
    on public.facturas_vencimientos (factura_id);

create index facturas_vencimientos_fecha_idx
    on public.facturas_vencimientos (fecha_vencimiento);

create index facturas_impuestos_factura_idx
    on public.facturas_impuestos (factura_id);

create index facturas_albaranes_extraidos_factura_idx
    on public.facturas_albaranes_extraidos (factura_id);

create index facturas_albaranes_extraidos_numero_idx
    on public.facturas_albaranes_extraidos (numero_albaran);

create index facturas_ajustes_factura_idx
    on public.facturas_ajustes (factura_id);


commit;