-- Rollback de la migracion 19 (Hito 2AX). Restaura EXACTAMENTE la matriz de
-- privilegios y los privilegios por defecto de postgres inventariados en
-- produccion (2026-09-28 16:57:12.999634+00). Generado por
-- pruebas/auditoria_2ax/generar_migracion_19.py. Sin DML.
begin;

revoke all on sequence public.albaranes_id_seq from public, anon, authenticated, service_role;
grant select, update, usage on sequence public.albaranes_id_seq to anon;
grant select, update, usage on sequence public.albaranes_id_seq to authenticated;
grant select, update, usage on sequence public.albaranes_id_seq to service_role;
revoke all on sequence public.historial_facturas_id_seq from public, anon, authenticated, service_role;
grant select, update, usage on sequence public.historial_facturas_id_seq to anon;
grant select, update, usage on sequence public.historial_facturas_id_seq to authenticated;
grant select, update, usage on sequence public.historial_facturas_id_seq to service_role;
revoke all on table public.albaranes from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.albaranes to anon;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.albaranes to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.albaranes to service_role;
revoke all on table public.cf_configuracion from public, anon, authenticated, service_role;
grant select on table public.cf_configuracion to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.cf_configuracion to service_role;
revoke all on table public.conciliacion_detalles from public, anon, authenticated, service_role;
grant select on table public.conciliacion_detalles to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.conciliacion_detalles to service_role;
revoke all on table public.conciliaciones from public, anon, authenticated, service_role;
grant select on table public.conciliaciones to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.conciliaciones to service_role;
revoke all on table public.documentos_facturas from public, anon, authenticated, service_role;
grant select on table public.documentos_facturas to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.documentos_facturas to service_role;
revoke all on table public.facturas from public, anon, authenticated, service_role;
grant select on table public.facturas to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.facturas to service_role;
revoke all on table public.facturas_ajustes from public, anon, authenticated, service_role;
grant select on table public.facturas_ajustes to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.facturas_ajustes to service_role;
revoke all on table public.facturas_albaranes_extraidos from public, anon, authenticated, service_role;
grant select on table public.facturas_albaranes_extraidos to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.facturas_albaranes_extraidos to service_role;
revoke all on table public.facturas_impuestos from public, anon, authenticated, service_role;
grant select on table public.facturas_impuestos to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.facturas_impuestos to service_role;
revoke all on table public.facturas_incidencias from public, anon, authenticated, service_role;
grant select on table public.facturas_incidencias to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.facturas_incidencias to service_role;
revoke all on table public.facturas_movimientos from public, anon, authenticated, service_role;
grant select on table public.facturas_movimientos to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.facturas_movimientos to service_role;
revoke all on table public.facturas_vencimientos from public, anon, authenticated, service_role;
grant select on table public.facturas_vencimientos to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.facturas_vencimientos to service_role;
revoke all on table public.historial_facturas from public, anon, authenticated, service_role;
grant select on table public.historial_facturas to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.historial_facturas to service_role;
revoke all on table public.normalizacion_ejecuciones from public, anon, authenticated, service_role;
grant select on table public.normalizacion_ejecuciones to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.normalizacion_ejecuciones to service_role;
revoke all on table public.proveedores from public, anon, authenticated, service_role;
grant select on table public.proveedores to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.proveedores to service_role;
revoke all on table public.proveedores_alias from public, anon, authenticated, service_role;
grant select on table public.proveedores_alias to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.proveedores_alias to service_role;
revoke all on table public.v_dashboard_diario from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_dashboard_diario to anon;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_dashboard_diario to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_dashboard_diario to service_role;
revoke all on table public.v_facturas_listado from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_facturas_listado to anon;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_facturas_listado to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_facturas_listado to service_role;
revoke all on table public.v_proveedores_estado from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_proveedores_estado to anon;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_proveedores_estado to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_proveedores_estado to service_role;
revoke all on table public.v_vencimientos_calendario from public, anon, authenticated, service_role;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_vencimientos_calendario to anon;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_vencimientos_calendario to authenticated;
grant delete, insert, maintain, references, select, trigger, truncate, update on table public.v_vencimientos_calendario to service_role;
revoke all on function public.cf_validar_factura(uuid, text) from public, anon, authenticated, service_role;
grant execute on function public.cf_validar_factura(uuid, text) to authenticated;
grant execute on function public.cf_validar_factura(uuid, text) to service_role;
revoke all on function public.cf_desvalidar_factura(uuid, text) from public, anon, authenticated, service_role;
grant execute on function public.cf_desvalidar_factura(uuid, text) to authenticated;
grant execute on function public.cf_desvalidar_factura(uuid, text) to service_role;

-- Privilegios por defecto de postgres en public (inventario 1.2).
alter default privileges for role postgres in schema public grant select, update, usage on sequences to postgres;
alter default privileges for role postgres in schema public grant select, update, usage on sequences to anon;
alter default privileges for role postgres in schema public grant select, update, usage on sequences to authenticated;
alter default privileges for role postgres in schema public grant select, update, usage on sequences to service_role;
alter default privileges for role postgres in schema public grant execute on functions to postgres;
alter default privileges for role postgres in schema public grant execute on functions to anon;
alter default privileges for role postgres in schema public grant execute on functions to authenticated;
alter default privileges for role postgres in schema public grant execute on functions to service_role;
alter default privileges for role postgres in schema public grant select, insert, update, delete, truncate, references, trigger, maintain on tables to postgres;
alter default privileges for role postgres in schema public grant select, insert, update, delete, truncate, references, trigger, maintain on tables to anon;
alter default privileges for role postgres in schema public grant select, insert, update, delete, truncate, references, trigger, maintain on tables to authenticated;
alter default privileges for role postgres in schema public grant select, insert, update, delete, truncate, references, trigger, maintain on tables to service_role;
-- Sin privilegios por defecto globales de postgres en el inventario: se restaura el
-- EXECUTE a PUBLIC incorporado por defecto (elimina la entrada global de la 19).
alter default privileges for role postgres grant execute on functions to public;

commit;
