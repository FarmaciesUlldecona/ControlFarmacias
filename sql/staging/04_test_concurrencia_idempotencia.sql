\set ON_ERROR_STOP on

-- Certifica el contrato FOR UPDATE SKIP LOCKED de las RPC de claim.
-- Prueba determinista en una sesion: tras el primer claim el segundo no recibe la fila.
do $$
declare
    v_doc uuid;
    v_worker_a uuid;
    v_worker_b uuid;
begin
    select id into v_doc from public.documentos_facturas
    where farmacia='PIO' and archivo_nombre='SINTETICO_PIO_020.pdf';
    update public.documentos_facturas
       set estado_lectura='PENDIENTE', reprocesar_solicitado_at=now(),
           bloqueado_por=null, bloqueado_hasta=null
     where id=v_doc;

    select id into v_worker_a
    from public.cf_reclamar_documento_normalizacion('worker-concurrente-a',300)
    where id=v_doc;
    select id into v_worker_b
    from public.cf_reclamar_documento_normalizacion('worker-concurrente-b',300)
    where id=v_doc;

    if v_worker_a is distinct from v_doc or v_worker_b is not null then
        raise exception 'dos workers obtuvieron el mismo documento';
    end if;
end;
$$;

-- Prueba concurrente real, ejecutar en dos sesiones de staging:
-- SESION A:
--   begin;
--   select id from public.cf_reclamar_documento_normalizacion('sesion-a',300);
--   -- mantener la transaccion abierta.
-- SESION B, mientras A sigue abierta:
--   begin;
--   select id from public.cf_reclamar_documento_normalizacion('sesion-b',300);
--   commit;
-- La sesion B debe devolver cero filas para el documento bloqueado y no esperar.
-- Finalmente ejecutar ROLLBACK en la sesion A.

select 'CLAIM_SECUENCIAL_OK_CONCURRENCIA_DOS_SESIONES_PENDIENTE' as resultado;
