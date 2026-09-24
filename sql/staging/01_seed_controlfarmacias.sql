\set ON_ERROR_STOP on

-- 112 documentos PIO y uno RITA, todos sinteticos.
insert into public.documentos_facturas (
    farmacia, archivo_nombre, archivo_ruta, archivo_hash,
    estado_lectura, requiere_revision, datos_extraidos
)
select
    'PIO',
    format('SINTETICO_PIO_%s.pdf', lpad(n::text, 3, '0')),
    format('staging/PIO/%s.pdf', lpad(n::text, 3, '0')),
    encode(extensions.digest(format('CONTROLFARMACIAS-STAGING-PIO-%s', n), 'sha256'), 'hex'),
    'PENDIENTE', false, '{}'::jsonb
from generate_series(1, 112) as serie(n);

insert into public.documentos_facturas (
    farmacia, archivo_nombre, archivo_ruta, archivo_hash,
    estado_lectura, requiere_revision, datos_extraidos
) values (
    'RITA', 'SINTETICO_RITA_001.pdf', 'staging/RITA/001.pdf',
    encode(extensions.digest('CONTROLFARMACIAS-STAGING-RITA-1', 'sha256'), 'hex'),
    'PENDIENTE', false, '{}'::jsonb
);

insert into public.albaranes (
    farmacia, id_contador, id_proveedor, proveedor, numero_albaran,
    fecha, importe_pvp, importe_puc, descuento, estado
) values
    ('PIO', 1, '123', 'PROVEEDOR SINTETICO', 'A-001', date '2026-01-01', 10, 9, 1, 'PENDIENTE'),
    ('PIO', 2, '00123', 'PROVEEDOR SINTETICO', 'A-002', date '2026-01-02', 20, 18, 2, 'PENDIENTE'),
    ('PIO', 3, 'ABC123', 'PROVEEDOR SINTETICO', 'A-003', date '2026-01-03', 30, 27, 3, 'PENDIENTE'),
    ('PIO', 4, '00001', 'PROVEEDOR SINTETICO', 'Q', date '2026-01-04', -5, -5, 0, 'PENDIENTE'),
    ('RITA', 1, 'RITA-01', 'PROVEEDOR RITA SINTETICO', 'R-001', date '2026-01-01', 99, 99, 0, 'PENDIENTE');

insert into public.proveedores (codigo, nombre, farmatic_id_proveedor)
values ('PROV-STG', 'PROVEEDOR SINTETICO', '00123');

insert into public.proveedores_alias (proveedor_id, alias)
select id, 'Proveedor Sintetico' from public.proveedores where codigo = 'PROV-STG';

-- Dos identidades economicas PIO iguales en PDFs distintos y una RITA control.
insert into public.facturas (
    documento_id, farmacia, pagina_inicio, pagina_fin, numero_factura,
    fecha_factura, proveedor_nombre, importe_total, datos_extraidos
)
select id, 'PIO', 1, 1, 'DUP-STG', date '2026-01-10',
       'Proveedor Sintetico', 10, '{"legacy":true}'::jsonb
from public.documentos_facturas
where farmacia = 'PIO' order by archivo_nombre limit 2;

insert into public.facturas (
    documento_id, farmacia, pagina_inicio, pagina_fin, numero_factura,
    fecha_factura, proveedor_nombre, importe_total, datos_extraidos
)
select id, 'RITA', 1, 1, 'DUP-STG', date '2026-01-10',
       'Proveedor Sintetico', 10, '{"legacy":true}'::jsonb
from public.documentos_facturas where farmacia = 'RITA';
