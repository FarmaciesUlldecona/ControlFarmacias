\set ON_ERROR_STOP on

do $$
declare
    v_doc uuid;
    v_doc_error uuid;
    v_doc_multi uuid;
    v_ejecucion_1 uuid;
    v_ejecucion_repetida uuid;
    v_ejecucion_2 uuid;
    v_payload jsonb;
begin
    select id into v_doc from public.documentos_facturas
    where farmacia = 'PIO' and archivo_nombre = 'SINTETICO_PIO_010.pdf';
    update public.documentos_facturas set reprocesar_solicitado_at = now() where id = v_doc;
    if (select id from public.cf_reclamar_documento_normalizacion('worker-rpc-a', 300) limit 1)
       is distinct from v_doc then raise exception 'claim caso A incorrecto'; end if;

    v_payload := jsonb_build_object(
        'uso_ocr', false, 'uso_luna', false, 'pasos', '[]'::jsonb,
        'resultado_json', jsonb_build_object(
            'documento_completo_demostrado', true,
            'numero_paginas', 1,
            'facturas', jsonb_build_array(jsonb_build_object(
                'factura_id', 'STG-RPC-A', 'pagina_inicio', 1, 'pagina_fin', 1,
                'naturaleza_principal', 'MERCANCIA', 'estado_validacion', 'VALIDADA',
                'requiere_conciliacion_albaranes', true,
                'numero_factura', jsonb_build_object('valor','RPC-A','literal','RPC-A'),
                'destinatario', jsonb_build_object(
                    'nif', jsonb_build_object(
                        'valor','40901058C','literal','40901058C',
                        'evidencia',jsonb_build_array(jsonb_build_object('pagina',1,'literal','40901058C')))),
                'totales', jsonb_build_object(
                    'moneda', jsonb_build_object('valor','EUR'),
                    'base_imponible', jsonb_build_object('valor','100.0000'),
                    'iva', jsonb_build_object('valor','21.0000'),
                    'total', jsonb_build_object('valor','121.0000')),
                'vencimientos', jsonb_build_array(jsonb_build_object(
                    'orden',1,'fecha',jsonb_build_object('valor',jsonb_build_object('iso','2026-02-01'),'literal','01/02/2026'),
                    'importe',jsonb_build_object('valor','121.0000','literal','121,00'))),
                'impuestos', jsonb_build_array(jsonb_build_object(
                    'orden',1,'descripcion_literal',jsonb_build_object('valor','IVA 21%','literal','IVA 21%'),
                    'base',jsonb_build_object('valor','100.0000'),'tipo_iva',jsonb_build_object('valor','21.0000'),
                    'cuota_iva',jsonb_build_object('valor','21.0000'))),
                'albaranes', jsonb_build_array(jsonb_build_object(
                    'orden',1,'numero',jsonb_build_object('valor','A-001','literal','A-001'),
                    'sentido','CARGO','importe_total',jsonb_build_object('valor','121.0000'))),
                'movimientos_comerciales', jsonb_build_array(jsonb_build_object(
                    'orden',1,'tipo','DESCUENTO','descripcion_literal',jsonb_build_object('valor','DESCUENTO','literal','DESCUENTO'),
                    'sentido','ABONO','importe',jsonb_build_object('valor','1.0000'))),
                'incidencias', jsonb_build_array(jsonb_build_object(
                    'codigo','STG_INFO','severidad','AVISO','bloqueante',false,'descripcion','Incidencia sintetica'))
            ))
        )
    );

    v_ejecucion_1 := public.cf_persistir_normalizacion(
        v_doc, 'worker-rpc-a', 'TEST', 'idem-rpc-a', repeat('a',64), v_payload);
    if (select count(*) from public.facturas where documento_id = v_doc) <> 1
       or (select count(*) from public.facturas_impuestos i join public.facturas f on f.id=i.factura_id where f.documento_id=v_doc) <> 1
       or (select count(*) from public.facturas_vencimientos v join public.facturas f on f.id=v.factura_id where f.documento_id=v_doc) <> 1
       or (select count(*) from public.facturas_movimientos m join public.facturas f on f.id=m.factura_id where f.documento_id=v_doc) <> 1 then
        raise exception 'persistencia completa caso A fallo';
    end if;

    v_ejecucion_repetida := public.cf_persistir_normalizacion(
        v_doc, 'worker-rpc-a', 'TEST', 'idem-rpc-a', repeat('a',64), v_payload);
    if v_ejecucion_repetida <> v_ejecucion_1
       or (select count(*) from public.normalizacion_ejecuciones where documento_id=v_doc) <> 1 then
        raise exception 'idempotency_key duplico ejecucion';
    end if;

    perform public.cf_solicitar_reprocesado(v_doc, 'STAGING');
    perform id from public.cf_reclamar_documento_normalizacion('worker-rpc-b', 300);
    v_ejecucion_2 := public.cf_persistir_normalizacion(
        v_doc, 'worker-rpc-b', 'REPROCESADO', 'idem-rpc-b', repeat('b',64), v_payload);
    if v_ejecucion_2 = v_ejecucion_1
       or (select count(*) from public.normalizacion_ejecuciones where documento_id=v_doc) <> 2
       or (select count(*) from public.facturas where documento_id=v_doc) <> 1 then
        raise exception 'reprocesado no conserva historial o duplica proyeccion';
    end if;

    select id into v_doc_error from public.documentos_facturas
    where farmacia='PIO' and archivo_nombre='SINTETICO_PIO_011.pdf';
    update public.documentos_facturas set reprocesar_solicitado_at=now() where id=v_doc_error;
    perform id from public.cf_reclamar_documento_normalizacion('worker-error',300);
    begin
        perform public.cf_persistir_normalizacion(
            v_doc_error, 'worker-error', 'TEST', 'idem-error', repeat('e',64),
            jsonb_build_object('resultado_json',jsonb_build_object('facturas',jsonb_build_array(
                jsonb_build_object('factura_id','STG-ERROR','pagina_inicio',1,'pagina_fin',1,
                    'naturaleza_principal','MERCANCIA','estado_validacion','VALIDADA',
                    'requiere_conciliacion_albaranes',true,'totales','{}'::jsonb,
                    'vencimientos',jsonb_build_array(jsonb_build_object('orden',null,'importe',jsonb_build_object('valor','1'))))
            ))));
        raise exception 'el error deliberado no fallo';
    exception when not_null_violation then
        null;
    end;
    if exists (select 1 from public.facturas where documento_id=v_doc_error)
       or exists (select 1 from public.normalizacion_ejecuciones where documento_id=v_doc_error) then
        raise exception 'rollback incompleto tras error deliberado';
    end if;
    perform public.cf_registrar_fallo_normalizacion(
        v_doc_error,'worker-error','TEST','idem-error-log','ERROR_STAGING','fallo deliberado');

    select id into v_doc_multi from public.documentos_facturas
    where farmacia='PIO' and archivo_nombre='SINTETICO_PIO_012.pdf';
    update public.documentos_facturas set reprocesar_solicitado_at=now() where id=v_doc_multi;
    perform id from public.cf_reclamar_documento_normalizacion('worker-multi',300);
    perform public.cf_persistir_normalizacion(
        v_doc_multi,'worker-multi','TEST','idem-multi',repeat('m',64),
        jsonb_build_object('resultado_json',jsonb_build_object('numero_paginas',2,'facturas',jsonb_build_array(
            jsonb_build_object('factura_id','STG-MULTI-A','pagina_inicio',1,'pagina_fin',1,'naturaleza_principal','MERCANCIA','estado_validacion','VALIDADA','requiere_conciliacion_albaranes',true,'totales','{}'::jsonb),
            jsonb_build_object('factura_id','STG-MULTI-B','pagina_inicio',2,'pagina_fin',2,'naturaleza_principal','MERCANCIA','estado_validacion','REQUIERE_REVISION','requiere_conciliacion_albaranes',true,'totales','{}'::jsonb)
        ))));
    if (select count(*) from public.facturas where documento_id=v_doc_multi) <> 2
       or (select estado_lectura from public.documentos_facturas where id=v_doc_multi) <> 'NORMALIZADA'
       or (select count(*) from public.facturas where documento_id=v_doc_multi and estado_normalizacion='REQUIERE_REVISION') <> 1 then
        raise exception 'multifactura/estado agregado incorrecto';
    end if;
end;
$$;

select 'RPC_NORMALIZACION_ROLLBACK_IDEMPOTENCIA_MULTIFACTURA_OK' as resultado;
