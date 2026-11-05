-- Migracion 29 (Hito 2BN): rol PostgreSQL de solo lectura para la web y los preflights (cf_lectura).
-- Diseno: pruebas/auditoria_2bn/DISENO.md.
-- - Rol propio con LOGIN, SIN contrasena en el repositorio (la fija Pio fuera, en el editor SQL); nunca la
--   credencial del sistema. Sin superusuario, sin BYPASSRLS, sin CREATEROLE/CREATEDB/REPLICATION; transacciones
--   de solo lectura por defecto.
-- - SELECT solo sobre una lista cerrada de tablas y vistas de public (las tablas nuevas no se conceden solas).
--   Sin INSERT/UPDATE/DELETE/TRUNCATE, sin secuencias, sin EXECUTE sobre las RPC (no se concede ninguno).
-- - RLS coherente: las 15 politicas de lectura de authenticated pasan a aplicarse tambien a cf_lectura (misma
--   regla: farmacias habilitadas); las 5 tablas de albaranes y reservas sin politica reciben una equivalente.
-- Datos y funciones existentes sin cambios. Requiere la 28.
begin;

do $$
begin
    if to_regprocedure('public.cf_materializar_referencia()') is null then
        raise exception 'MIGRACION_28_AUSENTE';
    end if;
    if not exists (select 1 from pg_roles where rolname = 'cf_lectura') then
        create role cf_lectura login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls
            connection limit 5;
    end if;
end;
$$;

alter role cf_lectura login nosuperuser nocreatedb nocreaterole noinherit noreplication nobypassrls
    connection limit 5;
alter role cf_lectura set default_transaction_read_only = on;
alter role cf_lectura set statement_timeout = '60s';
alter role cf_lectura set idle_in_transaction_session_timeout = '60s';

-- Lectura: lista cerrada.
grant usage on schema public to cf_lectura;
grant select on
    public.documentos_facturas, public.facturas, public.facturas_vencimientos, public.facturas_impuestos,
    public.facturas_albaranes_extraidos, public.facturas_ajustes, public.facturas_movimientos,
    public.facturas_incidencias, public.historial_facturas, public.normalizacion_ejecuciones,
    public.conciliaciones, public.conciliacion_detalles, public.conciliacion_albaranes_reservados,
    public.albaranes, public.albaranes_cambios, public.albaranes_aprobaciones, public.albaranes_aprobaciones_aplicadas,
    public.proveedores, public.proveedores_alias, public.cf_configuracion,
    public.v_facturas_listado, public.v_dashboard_diario, public.v_vencimientos_calendario, public.v_proveedores_estado
to cf_lectura;

-- RLS: las politicas de lectura existentes se aplican tambien a cf_lectura (misma regla).
alter policy documentos_facturas_authenticated_select on public.documentos_facturas to authenticated, cf_lectura;
alter policy facturas_authenticated_select on public.facturas to authenticated, cf_lectura;
alter policy facturas_vencimientos_authenticated_select on public.facturas_vencimientos to authenticated, cf_lectura;
alter policy facturas_impuestos_authenticated_select on public.facturas_impuestos to authenticated, cf_lectura;
alter policy facturas_albaranes_extraidos_authenticated_select on public.facturas_albaranes_extraidos
    to authenticated, cf_lectura;
alter policy facturas_ajustes_authenticated_select on public.facturas_ajustes to authenticated, cf_lectura;
alter policy facturas_movimientos_authenticated_select on public.facturas_movimientos to authenticated, cf_lectura;
alter policy facturas_incidencias_authenticated_select on public.facturas_incidencias to authenticated, cf_lectura;
alter policy historial_facturas_authenticated_select on public.historial_facturas to authenticated, cf_lectura;
alter policy normalizacion_ejecuciones_authenticated_select on public.normalizacion_ejecuciones
    to authenticated, cf_lectura;
alter policy conciliaciones_authenticated_select on public.conciliaciones to authenticated, cf_lectura;
alter policy conciliacion_detalles_authenticated_select on public.conciliacion_detalles to authenticated, cf_lectura;
alter policy proveedores_authenticated_select on public.proveedores to authenticated, cf_lectura;
alter policy proveedores_alias_authenticated_select on public.proveedores_alias to authenticated, cf_lectura;
alter policy cf_configuracion_authenticated_select on public.cf_configuracion to authenticated, cf_lectura;

-- RLS: tablas sin politica de lectura; misma regla (farmacias habilitadas), solo para cf_lectura.
drop policy if exists albaranes_lectura_select on public.albaranes;
create policy albaranes_lectura_select
    on public.albaranes for select to cf_lectura
    using (exists (
        select 1 from public.cf_configuracion c
        where c.id = true and albaranes.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists albaranes_cambios_lectura_select on public.albaranes_cambios;
create policy albaranes_cambios_lectura_select
    on public.albaranes_cambios for select to cf_lectura
    using (exists (
        select 1 from public.cf_configuracion c
        where c.id = true and albaranes_cambios.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists albaranes_aprobaciones_lectura_select on public.albaranes_aprobaciones;
create policy albaranes_aprobaciones_lectura_select
    on public.albaranes_aprobaciones for select to cf_lectura
    using (exists (
        select 1 from public.cf_configuracion c
        where c.id = true and albaranes_aprobaciones.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists albaranes_aprobaciones_aplicadas_lectura_select on public.albaranes_aprobaciones_aplicadas;
create policy albaranes_aprobaciones_aplicadas_lectura_select
    on public.albaranes_aprobaciones_aplicadas for select to cf_lectura
    using (exists (
        select 1 from public.cf_configuracion c
        where c.id = true and albaranes_aprobaciones_aplicadas.farmacia = any(c.farmacias_habilitadas)
    ));

drop policy if exists conciliacion_albaranes_reservados_lectura_select on public.conciliacion_albaranes_reservados;
create policy conciliacion_albaranes_reservados_lectura_select
    on public.conciliacion_albaranes_reservados for select to cf_lectura
    using (exists (
        select 1 from public.facturas f join public.cf_configuracion c on c.id = true
        where f.id = conciliacion_albaranes_reservados.factura_id
          and f.farmacia = any(c.farmacias_habilitadas)
    ));

commit;
