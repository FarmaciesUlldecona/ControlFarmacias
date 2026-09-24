\set ON_ERROR_STOP on

begin;

do $$
declare
    v_factura uuid;
    v_claim_1 uuid;
    v_claim_2 uuid;
    v_estado text;
    v_razon text;
begin
    select id into v_factura from public.facturas where proyeccion_clave='STG-RPC-A';

    select estado, razon into v_estado, v_razon
      from public.cf_evaluar_elegibilidad_conciliacion(v_factura);
    if (v_estado, v_razon) <> ('APTA', 'APTA_MERCANCIA') then
        raise exception 'mercancia con albaran no apta: %, %', v_estado, v_razon;
    end if;

    update public.facturas
       set categoria='CUOTA_SERVICIO', requiere_conciliacion_albaranes=false,
           base_imponible_total=100, iva_total=21,
           recargo_equivalencia_total=0, importe_total=121,
           datos_extraidos=jsonb_set(datos_extraidos,'{naturaleza_principal}','"SERVICIOS"'::jsonb),
           estado_normalizacion='NORMALIZADA', estado_conciliacion_cf='PENDIENTE_CONCILIAR',
           conciliacion_reintento_solicitado_at=now(),
           conciliacion_bloqueado_por=null, conciliacion_bloqueado_hasta=null
     where id=v_factura;
    delete from public.facturas_albaranes_extraidos where factura_id=v_factura;
    update public.facturas_movimientos
       set sentido='CARGO', base=100, importe=null
     where factura_id=v_factura;

    select estado, razon into v_estado, v_razon
      from public.cf_evaluar_elegibilidad_conciliacion(v_factura);
    if (v_estado, v_razon) <> ('APTA', 'APTA_GASTO_SERVICIO') then
        raise exception 'servicio sin albaran no apto: %, %', v_estado, v_razon;
    end if;

    update public.facturas set base_imponible_total=99 where id=v_factura;
    select estado, razon into v_estado, v_razon
      from public.cf_evaluar_elegibilidad_conciliacion(v_factura);
    if v_estado <> 'NO_APTA' then
        raise exception 'servicio con total no explicado fue apto';
    end if;
    update public.facturas set base_imponible_total=100 where id=v_factura;

    select id into v_claim_1
      from public.cf_reclamar_factura_conciliacion('staging-claim-v2-a',300);
    select id into v_claim_2
      from public.cf_reclamar_factura_conciliacion('staging-claim-v2-b',300);
    if v_claim_1 is distinct from v_factura or v_claim_2 is not null then
        raise exception 'claim de servicio no fue exclusivo';
    end if;

    update public.facturas
       set datos_extraidos=jsonb_set(datos_extraidos,'{naturaleza_principal}','"MIXTA"'::jsonb),
           categoria='OTRO', importe_total=242, base_imponible_total=200,
           iva_total=42, conciliacion_bloqueado_por=null, conciliacion_bloqueado_hasta=null
     where id=v_factura;
    insert into public.facturas_albaranes_extraidos
        (factura_id,numero_albaran,tipo_movimiento,importe_total,orden)
    values (v_factura,'MIXTO-1','CARGO',121,1);
    update public.facturas_movimientos set base=null,importe=121 where factura_id=v_factura;
    select estado, razon into v_estado, v_razon
      from public.cf_evaluar_elegibilidad_conciliacion(v_factura);
    if (v_estado, v_razon) <> ('APTA', 'APTA_MIXTA') then
        raise exception 'mixta completa no apta: %, %', v_estado, v_razon;
    end if;

    delete from public.facturas_albaranes_extraidos where factura_id=v_factura;
    if (select estado from public.cf_evaluar_elegibilidad_conciliacion(v_factura)) <> 'NO_APTA' then
        raise exception 'mixta sin mercancia fue apta';
    end if;
    update public.facturas
       set datos_extraidos=jsonb_set(datos_extraidos,'{naturaleza_principal}','"OTRO"'::jsonb)
     where id=v_factura;
    if (select estado from public.cf_evaluar_elegibilidad_conciliacion(v_factura)) <> 'REQUIERE_REVISION' then
        raise exception 'tipo no demostrado no requiere revision';
    end if;
end;
$$;

rollback;

select 'CLAIM_CONCILIACION_V2_TIPOS_CONCURRENCIA_OK' as resultado;
