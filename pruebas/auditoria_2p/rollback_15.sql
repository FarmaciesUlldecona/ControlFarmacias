-- PREPARADO, NO EJECUTAR sin autorizacion. Solo antes de utilizar multifactura.
-- No CASCADE; cualquier dependencia nueva obliga a parar.
begin;
set local lock_timeout='5s';
set local statement_timeout='60s';
lock table public.documentos_facturas in access exclusive mode;
do $$
begin
    if exists(select 1 from public.documentos_facturas
              where inventario_facturas<>'[]'::jsonb or estado_persistencia<>'PENDIENTE')
       or exists(select 1 from public.normalizacion_ejecuciones where resultado_json ? 'multifactura')
       or exists(select 1 from public.historial_facturas where evento='INVENTARIO_MULTIFACTURA') then
        raise exception 'ROLLBACK_NO_SEGURO_MULTIFACTURA_YA_UTILIZADA';
    end if;
end;
$$;
drop function public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[]);
drop function public.cf_clave_economica_factura(jsonb);
drop function public.cf_componentes_identidad_factura(jsonb);
alter table public.documentos_facturas drop column inventario_facturas, drop column estado_persistencia;
commit;
