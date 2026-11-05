-- Rollback de la migracion 29 (Hito 2BN): devuelve el esquema exacto de la 28.
-- Retira las politicas y privilegios de cf_lectura y elimina el rol. Un rol es del cluster: si otra base del mismo
-- cluster aun le concede algo (no es el caso en produccion, una sola base), no se puede eliminar y queda sin
-- privilegios en esta base. Solo con confirmacion de Pio. Sin cambios de datos.
begin;

drop policy if exists albaranes_lectura_select on public.albaranes;
drop policy if exists albaranes_cambios_lectura_select on public.albaranes_cambios;
drop policy if exists albaranes_aprobaciones_lectura_select on public.albaranes_aprobaciones;
drop policy if exists albaranes_aprobaciones_aplicadas_lectura_select on public.albaranes_aprobaciones_aplicadas;
drop policy if exists conciliacion_albaranes_reservados_lectura_select on public.conciliacion_albaranes_reservados;

alter policy documentos_facturas_authenticated_select on public.documentos_facturas to authenticated;
alter policy facturas_authenticated_select on public.facturas to authenticated;
alter policy facturas_vencimientos_authenticated_select on public.facturas_vencimientos to authenticated;
alter policy facturas_impuestos_authenticated_select on public.facturas_impuestos to authenticated;
alter policy facturas_albaranes_extraidos_authenticated_select on public.facturas_albaranes_extraidos to authenticated;
alter policy facturas_ajustes_authenticated_select on public.facturas_ajustes to authenticated;
alter policy facturas_movimientos_authenticated_select on public.facturas_movimientos to authenticated;
alter policy facturas_incidencias_authenticated_select on public.facturas_incidencias to authenticated;
alter policy historial_facturas_authenticated_select on public.historial_facturas to authenticated;
alter policy normalizacion_ejecuciones_authenticated_select on public.normalizacion_ejecuciones to authenticated;
alter policy conciliaciones_authenticated_select on public.conciliaciones to authenticated;
alter policy conciliacion_detalles_authenticated_select on public.conciliacion_detalles to authenticated;
alter policy proveedores_authenticated_select on public.proveedores to authenticated;
alter policy proveedores_alias_authenticated_select on public.proveedores_alias to authenticated;
alter policy cf_configuracion_authenticated_select on public.cf_configuracion to authenticated;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'cf_lectura') then
        execute 'revoke all on all tables in schema public from cf_lectura';
        execute 'revoke all on schema public from cf_lectura';
        begin
            execute 'drop role cf_lectura';
        exception when dependent_objects_still_exist then
            -- Sin tocar los atributos del rol (son del cluster): en esta base ya no tiene ningun privilegio.
            raise notice 'ROLLBACK_29: cf_lectura conserva privilegios en otra base del cluster; no se elimina';
        end;
    end if;
end;
$$;

commit;
