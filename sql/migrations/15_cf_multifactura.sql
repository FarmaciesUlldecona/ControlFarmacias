begin;

alter table public.documentos_facturas
    add column if not exists inventario_facturas jsonb not null default '[]'::jsonb,
    add column if not exists estado_persistencia text not null default 'PENDIENTE'
        check (estado_persistencia in ('PENDIENTE','PARCIAL','COMPLETA','REQUIERE_REVISION'));

-- Identidad conservadora basada en NIF documentado, nunca en paginas ni SHA.
create or replace function public.cf_componentes_identidad_factura(p jsonb)
returns text[] language plpgsql immutable set search_path=public as $$
declare
    campo jsonb;
    partes text[];
    tipo text;
begin
    foreach campo in array array[p#>'{proveedor,nif}',p->'numero_factura',
        p->'tipo_documento',p#>'{destinatario,nif}',p->'fecha_factura',p#>'{totales,total}']
    loop
        if campo is null or campo->'valor' is null or campo->'valor'='null'::jsonb
           or not exists (select 1 from jsonb_array_elements(coalesce(campo->'evidencia','[]')) e
                           where (e->>'pagina')::integer>0 and length(btrim(e->>'literal'))>0) then
            return null;
        end if;
    end loop;
    tipo := upper(btrim(p#>>'{tipo_documento,valor}'));
    if tipo='FACTURA_DUPLICADO' then tipo:='FACTURA'; end if;
    if tipo not in ('FACTURA','ABONO','FACTURA_RECTIFICATIVA') then return null; end if;
    if (p#>>'{totales,total,valor}')::numeric <> round((p#>>'{totales,total,valor}')::numeric,4)
       or (p#>>'{totales,total,valor}') in ('NaN','Infinity','-Infinity') then return null; end if;
    partes := array[
        regexp_replace(upper(p#>>'{proveedor,nif,valor}'),'[^A-Z0-9]','','g'),
        upper(btrim(p#>>'{numero_factura,valor}')),tipo,
        regexp_replace(upper(p#>>'{destinatario,nif,valor}'),'[^A-Z0-9]','','g'),
        to_char((p#>>'{fecha_factura,valor,iso}')::date,'YYYY-MM-DD'),
        ((p#>>'{totales,total,valor}')::numeric(18,4))::text];
    if exists(select 1 from unnest(partes) v where v is null or v='' or strpos(v,chr(31))>0) then return null; end if;
    return partes;
exception when invalid_text_representation or invalid_datetime_format or datetime_field_overflow or numeric_value_out_of_range then
    return null;
end;
$$;

create or replace function public.cf_clave_economica_factura(p jsonb)
returns text language sql immutable set search_path=public as $$
    select case when public.cf_componentes_identidad_factura(p) is not null then
      encode(extensions.digest(array_to_string(public.cf_componentes_identidad_factura(p),chr(31)),'sha256'),'hex') end;
$$;

create or replace function public.cf_persistir_documento_multifactura(
    p_documento_id uuid, p_worker_id text, p_idempotency_key text,
    p_resultado_hash text, p_resultado jsonb, p_segmentos_autorizados text[]
)
returns uuid language plpgsql security definer set search_path=public as $$
declare
    d public.documentos_facturas%rowtype;
    f jsonb; anterior jsonb; item jsonb;
    partes text[]; otras_partes text[];
    clave text; segmento text; estado text;
    existentes text[] := '{}'::text[];
    segmentos text[] := '{}'::text[];
    paginas integer[] := '{}'::integer[];
    nuevas jsonb := '[]'::jsonb;
    inventario jsonb := '[]'::jsonb;
    factura_ref uuid; otra record;
    ejecucion uuid; payload jsonb;
    firma text; replay jsonb;
    n integer; inicio integer; fin integer;
begin
    if nullif(btrim(p_worker_id),'') is null or nullif(btrim(p_idempotency_key),'') is null
       or p_segmentos_autorizados is null then raise exception 'MULTIFACTURA_ARGUMENTOS_INVALIDOS'; end if;
    -- Serializa decisiones de identidad entre documentos, ademas del lock del PDF.
    perform pg_advisory_xact_lock(2151501);
    select * into d from public.documentos_facturas where id=p_documento_id for update;
    if d.id is null or d.farmacia<>'PIO' then raise exception 'DOCUMENTO_FUERA_DE_AMBITO'; end if;
    if not exists(select 1 from public.cf_configuracion where id and d.farmacia=any(farmacias_habilitadas)) then
        raise exception 'FARMACIA_NO_HABILITADA'; end if;
    firma:=encode(extensions.digest(jsonb_build_object('documento',p_resultado,'seleccion',to_jsonb(p_segmentos_autorizados))::text,'sha256'),'hex');
    select id,resultado_json into ejecucion,replay from public.normalizacion_ejecuciones
      where documento_id=d.id and idempotency_key=p_idempotency_key;
    if ejecucion is not null then
        if replay#>>'{multifactura,firma_solicitud}' is distinct from firma then raise exception 'IDEMPOTENCIA_PAYLOAD_DISTINTO'; end if;
        return ejecucion;
    end if;
    if d.bloqueado_por is distinct from p_worker_id or d.bloqueado_hasta<=now() or d.bloqueado_hasta is null then
        raise exception 'CLAIM_DOCUMENTAL_NO_VALIDO'; end if;
    if p_resultado->'documento_completo_demostrado' is distinct from 'true'::jsonb
       or jsonb_typeof(p_resultado->'facturas') is distinct from 'array'
       or jsonb_array_length(p_resultado->'facturas')=0 then raise exception 'DOCUMENTO_INCOMPLETO'; end if;
    n:=(p_resultado->>'numero_paginas')::integer;
    if n is null or n<1 then raise exception 'PAGINAS_INVALIDAS'; end if;
    if cardinality(p_segmentos_autorizados)<>(select count(distinct s) from unnest(p_segmentos_autorizados) s) then
        raise exception 'SELECCION_DUPLICADA'; end if;
    for f in select value from jsonb_array_elements(p_resultado->'facturas') loop
        segmento:=f#>>'{provenance,segment_id}';
        inicio:=(f->>'pagina_inicio')::integer; fin:=(f->>'pagina_fin')::integer;
        if nullif(segmento,'') is null or segmento=any(segmentos) or inicio is null or fin is null
           or inicio<1 or fin<inicio or fin>n then raise exception 'SEGMENTACION_INVALIDA'; end if;
        if (f#>'{provenance,paginas}') is distinct from (select jsonb_agg(g) from generate_series(inicio,fin) g)
           or exists(select 1 from generate_series(inicio,fin) g where g=any(paginas)) then
            raise exception 'PROVENANCE_INVALIDA'; end if;
        if exists(select 1 from jsonb_path_query(f,'$.**.evidencia[*].pagina') e
            where jsonb_typeof(e)<>'number' or (e::text)::integer not between inicio and fin) then
            raise exception 'EVIDENCIA_FUERA_DE_FACTURA'; end if;
        segmentos:=array_append(segmentos,segmento);
        paginas:=paginas || array(select g from generate_series(inicio,fin) g);
        partes:=public.cf_componentes_identidad_factura(f);
        clave:=public.cf_clave_economica_factura(f);
        estado:='PENDIENTES'; factura_ref:=null;
        if clave is null or f->'factura_completa_demostrada' is distinct from 'true'::jsonb
           or partes[4]<>'40901058C' or f->>'estado_validacion' not in ('VALIDADA','VALIDADA_CON_INCIDENCIAS')
           or f->>'estado_validacion' is null then estado:='REQUIERE_REVISION'; end if;
        -- Compara todas las hermanas antes de decidir, independientemente del orden.
        if exists(select 1 from jsonb_array_elements(p_resultado->'facturas') sibling
            where (public.cf_componentes_identidad_factura(sibling))[1:4]=partes[1:4]
              and public.cf_componentes_identidad_factura(sibling)<>partes) then
            estado:='REQUIERE_REVISION'; end if;
        -- Una version incompatible del mismo nucleo nunca se deduplica automaticamente.
        for otra in select id,documento_id,datos_extraidos from public.facturas loop
            otras_partes:=public.cf_componentes_identidad_factura(otra.datos_extraidos);
            if otras_partes[1:4]=partes[1:4] then
                if otras_partes<>partes then estado:='REQUIERE_REVISION'; factura_ref:=null; exit;
                else
                    factura_ref:=otra.id;
                    if estado<>'REQUIERE_REVISION' then
                        estado:=case when otra.documento_id=d.id then 'PERSISTIDAS' else 'DUPLICADAS' end;
                    end if;
                end if;
            end if;
        end loop;
        for item in select value from jsonb_array_elements(inventario) loop
            if (item->'componentes')=to_jsonb(partes) and estado='PENDIENTES'
               and item->>'estado' in ('PERSISTIDAS','DUPLICADAS') then estado:='DUPLICADAS'; end if;
            if (item->'componentes')->>0=partes[1] and (item->'componentes')->>1=partes[2]
               and (item->'componentes')->>2=partes[3] and (item->'componentes')->>3=partes[4]
               and (item->'componentes')<>to_jsonb(partes) then estado:='REQUIERE_REVISION'; end if;
        end loop;
        if estado='PENDIENTES' and segmento=any(p_segmentos_autorizados) then
            nuevas:=nuevas || jsonb_build_array(f || jsonb_build_object('factura_id',clave,'identidad_economica_clave',clave));
            estado:='PERSISTIDAS';
        end if;
        inventario:=inventario || jsonb_build_array(jsonb_build_object('segment_id',segmento,
            'clave_economica',clave,'componentes',to_jsonb(partes),'estado',estado,
            'factura_id',factura_ref,'provenance',f->'provenance'));
    end loop;
    if cardinality(paginas)<>n or not p_segmentos_autorizados<@segmentos then raise exception 'INVENTARIO_INCOMPLETO'; end if;
    -- Relecturas deben conservar las identidades inventariadas; nunca desaparecen hermanas.
    for anterior in select value from jsonb_array_elements(d.inventario_facturas) loop
        if not exists(select 1 from jsonb_array_elements(inventario) x
            where x->>'segment_id'=anterior->>'segment_id' and x->'clave_economica' is not distinct from anterior->'clave_economica') then
            raise exception 'INVENTARIO_RELECTURA_INCOMPATIBLE'; end if;
    end loop;
    payload:=p_resultado || jsonb_build_object('facturas',nuevas);
    ejecucion:=public.cf_persistir_normalizacion(d.id,p_worker_id,'MANUAL',p_idempotency_key,p_resultado_hash,
        jsonb_build_object('resultado_json',payload,'uso_luna',false,'uso_ocr',false));
    -- Guardar lectura completa e inventario, no solo el subconjunto economico elegido.
    update public.normalizacion_ejecuciones set resultado_json=p_resultado || jsonb_build_object(
        'multifactura',jsonb_build_object('firma_solicitud',firma,'segmentos_autorizados',to_jsonb(p_segmentos_autorizados)))
      where id=ejecucion;
    select jsonb_agg(x || jsonb_build_object('factura_id',coalesce(x->>'factura_id',
          (select id::text from public.facturas where documento_id=d.id and proyeccion_clave=x->>'clave_economica')),
          'estado',case when x->>'estado'='PENDIENTES' and exists(
            select 1 from public.facturas where documento_id=d.id and proyeccion_clave=x->>'clave_economica')
            then 'DUPLICADAS' else x->>'estado' end))
      into inventario from jsonb_array_elements(inventario) x;
    estado:=case
      when not exists(select 1 from jsonb_array_elements(inventario) x where x->>'estado' not in ('PERSISTIDAS','DUPLICADAS')) then 'COMPLETA'
      when exists(select 1 from jsonb_array_elements(inventario) x where x->>'estado'='PERSISTIDAS') then 'PARCIAL'
      when exists(select 1 from jsonb_array_elements(inventario) x where x->>'estado'='REQUIERE_REVISION') then 'REQUIERE_REVISION'
      else 'PENDIENTE' end;
    update public.documentos_facturas set inventario_facturas=inventario,estado_persistencia=estado,
      estado_lectura=case when estado='COMPLETA' then 'NORMALIZADA' else 'REVISION' end,
      cantidad_documentos_detectados=jsonb_array_length(inventario),
      tipo_contenido=case when jsonb_array_length(inventario)>1 then 'LOTE_FACTURAS' else 'FACTURA_UNICA' end
      where id=d.id;
    insert into public.historial_facturas(documento_id,evento,origen,actor,estado_nuevo,detalle)
      values(d.id,'INVENTARIO_MULTIFACTURA','RPC',p_worker_id,jsonb_build_object('estado_persistencia',estado),
             jsonb_build_object('ejecucion_id',ejecucion,'inventario',inventario));
    return ejecucion;
end;
$$;

revoke all on function public.cf_componentes_identidad_factura(jsonb) from public,anon,authenticated;
revoke all on function public.cf_clave_economica_factura(jsonb) from public,anon,authenticated;
revoke all on function public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[]) from public,anon,authenticated;
grant execute on function public.cf_componentes_identidad_factura(jsonb) to service_role;
grant execute on function public.cf_clave_economica_factura(jsonb) to service_role;
grant execute on function public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[]) to service_role;
commit;
