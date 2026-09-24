\set ON_ERROR_STOP on

do $$
declare
    v_factura uuid;
    v_conciliacion uuid;
    v_albaran_extraido uuid;
    v_movimiento uuid;
begin
    if public.cf_resultado_conciliacion(0.0000,0.0500) <> 'CONCILIADA'
       or public.cf_resultado_conciliacion(0.0100,0.0500) <> 'CONCILIADA'
       or public.cf_resultado_conciliacion(0.0500,0.0500) <> 'CONCILIADA'
       or public.cf_resultado_conciliacion(0.0501,0.0500) <> 'DIFERENCIA' then
        raise exception 'frontera de tolerancia incorrecta';
    end if;

    select f.id into v_factura from public.facturas f
    where f.proyeccion_clave='STG-RPC-A';
    select a.id into v_albaran_extraido from public.facturas_albaranes_extraidos a
    where a.factura_id=v_factura limit 1;
    select m.id into v_movimiento from public.facturas_movimientos m
    where m.factura_id=v_factura limit 1;

    update public.facturas
       set estado_conciliacion_cf = case
           when public.cf_resultado_conciliacion(0.0501,0.0500)='CONCILIADA'
           then 'CONCILIADA' else 'PENDIENTE_CONCILIAR' end
     where id=v_factura;
    if (select estado_conciliacion_cf from public.facturas where id=v_factura)
       <> 'PENDIENTE_CONCILIAR' then
        raise exception '0.0501 no quedo PENDIENTE_CONCILIAR';
    end if;

    insert into public.conciliaciones (
        factura_id,intento,disparador,estado,es_actual,tolerancia,
        importe_factura,importe_explicado,diferencia,resultado,estrategia,worker_id,finalizado_at
    ) values (
        v_factura,1,'TEST','COMPLETADA',true,0.0500,121,120.9499,0.0501,
        'DIFERENCIA','STAGING_RELACIONES','worker-staging',now()
    ) returning id into v_conciliacion;

    insert into public.conciliacion_detalles (
        conciliacion_id,orden,factura_albaran_extraido_id,factura_movimiento_id,
        albaran_farmacia,albaran_id_contador,numero_albaran_documental,
        numero_albaran_farmatic,coincidencia_numero_literal,tipo_relacion,
        importe_documental,importe_farmatic,importe_aplicado,diferencia,estado,provenance
    ) values
        (v_conciliacion,1,v_albaran_extraido,null,'PIO',1,'A-001','A-001',true,
         'UNO_A_UNO',40,40,40,0,'COINCIDE','{"caso":"cargo"}'),
        (v_conciliacion,2,v_albaran_extraido,null,'PIO',2,'A-001','A-002',false,
         'UNO_A_VARIOS',30,30,30,0,'COINCIDE','{"caso":"abono"}'),
        (v_conciliacion,3,v_albaran_extraido,null,'PIO',3,'A-001','A-003',false,
         'VARIOS_A_UNO',20,20,20,0,'COINCIDE','{"caso":"devolucion"}'),
        (v_conciliacion,4,null,v_movimiento,null,null,'Q',null,false,
         'MOVIMIENTO_NO_FARMATIC',1,null,1,0,'COINCIDE','{"caso":"descuento_sin_match_literal"}');

    if (select count(*) from public.conciliacion_detalles where conciliacion_id=v_conciliacion) <> 4
       or (select count(*) from public.conciliacion_detalles
           where conciliacion_id=v_conciliacion and not coincidencia_numero_literal) <> 3 then
        raise exception 'relaciones de conciliacion incompletas';
    end if;
end;
$$;

select 'CONCILIACION_0000_0010_0050_00501_Y_RELACIONES_OK' as resultado;
