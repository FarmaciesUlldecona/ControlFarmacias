-- Migracion 19 (Hito 2AX): privilegios minimos. Generada por
-- pruebas/auditoria_2ax/generar_migracion_19.py desde el inventario productivo READ_ONLY.
-- P1: tablas, vistas y secuencias de public sin privilegios para PUBLIC, anon y
--     authenticated; service_role solo con lo que usa el codigo. RLS no cambia.
-- P2: cf_validar_factura y cf_desvalidar_factura solo para el propietario.
-- P3: privilegios por defecto de postgres cerrados para PUBLIC, anon y authenticated.
-- No toca funciones de trigger, cf_resultado_conciliacion, rls_auto_enable,
-- politicas ni otros esquemas. Idempotente. Sin DML.
begin;

-- P1
revoke all on sequence public.albaranes_id_seq from public, anon, authenticated, service_role;
revoke all on sequence public.historial_facturas_id_seq from public, anon, authenticated, service_role;
revoke all on table public.albaranes from public, anon, authenticated, service_role;
revoke all on table public.cf_configuracion from public, anon, authenticated, service_role;
revoke all on table public.conciliacion_detalles from public, anon, authenticated, service_role;
revoke all on table public.conciliaciones from public, anon, authenticated, service_role;
revoke all on table public.documentos_facturas from public, anon, authenticated, service_role;
revoke all on table public.facturas from public, anon, authenticated, service_role;
revoke all on table public.facturas_ajustes from public, anon, authenticated, service_role;
revoke all on table public.facturas_albaranes_extraidos from public, anon, authenticated, service_role;
revoke all on table public.facturas_impuestos from public, anon, authenticated, service_role;
revoke all on table public.facturas_incidencias from public, anon, authenticated, service_role;
revoke all on table public.facturas_movimientos from public, anon, authenticated, service_role;
revoke all on table public.facturas_vencimientos from public, anon, authenticated, service_role;
revoke all on table public.historial_facturas from public, anon, authenticated, service_role;
revoke all on table public.normalizacion_ejecuciones from public, anon, authenticated, service_role;
revoke all on table public.proveedores from public, anon, authenticated, service_role;
revoke all on table public.proveedores_alias from public, anon, authenticated, service_role;
revoke all on table public.v_dashboard_diario from public, anon, authenticated, service_role;
revoke all on table public.v_facturas_listado from public, anon, authenticated, service_role;
revoke all on table public.v_proveedores_estado from public, anon, authenticated, service_role;
revoke all on table public.v_vencimientos_calendario from public, anon, authenticated, service_role;

grant select, insert on table public.documentos_facturas to service_role;
grant select, insert on table public.albaranes to service_role;
grant select on table public.facturas to service_role;
grant select on table public.cf_configuracion to service_role;
grant select on table public.proveedores to service_role;
grant select on table public.facturas_movimientos to service_role;
grant select on table public.facturas_albaranes_extraidos to service_role;
grant select on table public.normalizacion_ejecuciones to service_role;

-- P2
revoke all on function public.cf_validar_factura(uuid, text) from public, anon, authenticated, service_role;
revoke all on function public.cf_desvalidar_factura(uuid, text) from public, anon, authenticated, service_role;

-- P3: por esquema (anon y authenticated) y global para PUBLIC en funciones:
-- un REVOKE por esquema no puede quitar el EXECUTE a PUBLIC incorporado por defecto.
alter default privileges for role postgres in schema public
    revoke all on tables from public, anon, authenticated;
alter default privileges for role postgres in schema public
    revoke all on sequences from public, anon, authenticated;
alter default privileges for role postgres in schema public
    revoke all on functions from public, anon, authenticated;
alter default privileges for role postgres
    revoke execute on functions from public;

commit;
