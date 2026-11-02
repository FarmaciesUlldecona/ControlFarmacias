-- Migracion 26 (Hito 2BK): persistencia multifactura sin recorrer facturas.datos_extraidos.
-- Generada por pruebas/auditoria_2bk/generar_migracion_26.py a partir del texto de la 15 y la 17.
-- En produccion la RPC multifactura supero el statement_timeout de 8 s (Alliance de 4 facturas, serie 2BJ):
-- por cada factura del documento se leia y descomprimia datos_extraidos de toda la tabla facturas, coste
-- que crece con cada documento. Cambios, con el mismo resultado que la 17:
-- - indice de expresion sobre la misma funcion de identidad del bucle; el bucle solo visita las filas con
--   el mismo nucleo [1:4], en el orden de la lectura secuencial (order by ctid); la funcion declara su coste
--   real para que el planificador use el indice;
-- - la ejecucion se escribe una sola vez (antes: insercion y dos actualizaciones de resultado_json).
-- cf_persistir_normalizacion y las dos firmas de cf_persistir_documento_multifactura delegan en dos nucleos
-- internos (solo propietario). Firmas, privilegios de las RPC y filas existentes no cambian.
-- Si se redefine cf_componentes_identidad_factura hay que reconstruir el indice (REINDEX).
-- Requiere la 25. Diseno: pruebas/auditoria_2bk/DISENO.md.
begin;

do $$
begin
    if to_regprocedure('public.cf_recuperar_claim_huerfano_normalizacion(uuid,text,interval)') is null then
        raise exception 'MIGRACION_25_AUSENTE';
    end if;
end;
$$;

create index if not exists facturas_identidad_nucleo_idx
    on public.facturas (((public.cf_componentes_identidad_factura(datos_extraidos))[1:4]));

-- Con el coste por defecto (100) el planificador recorre la tabla y descomprime datos_extraidos de cada fila
-- (perfil 2BK: 1,5-1,8 s por factura con 54 facturas). Coste declarado acorde: solo cambia el plan.
alter function public.cf_componentes_identidad_factura(jsonb) cost 10000;

-- Nucleo de cf_persistir_normalizacion (17) con la ejecucion ya completa como argumento opcional.

create or replace function public.cf_persistir_normalizacion_nucleo(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_resultado_hash text,
    p_resultado jsonb,
    p_resultado_json_guardado jsonb
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_documento public.documentos_facturas%rowtype;
    v_ejecucion_id uuid;
    v_intento integer;
    v_documento_normalizado jsonb := coalesce(p_resultado->'resultado_json', p_resultado);
    v_factura jsonb;
    v_factura_id uuid;
    v_item jsonb;
    v_estado_factura text;
begin
    if nullif(btrim(p_worker_id), '') is null
       or nullif(btrim(p_idempotency_key), '') is null then
        raise exception 'worker_id e idempotency_key obligatorios';
    end if;

    select * into v_documento
      from public.documentos_facturas
     where id = p_documento_id
     for update;

    if v_documento.id is null then
        raise exception 'documento no encontrado';
    end if;
    if not exists (
        select 1 from public.cf_configuracion c
        where c.id = true and v_documento.farmacia = any(c.farmacias_habilitadas)
    ) then
        raise exception 'farmacia fuera del despliegue habilitado';
    end if;

    select id into v_ejecucion_id
      from public.normalizacion_ejecuciones
     where documento_id = p_documento_id
       and idempotency_key = p_idempotency_key;
    if v_ejecucion_id is not null then
        -- R1: el replay nunca deja claim, lock ni estado intermedio.
        perform public.cf_cerrar_replay_normalizacion(
            p_documento_id, p_worker_id, v_ejecucion_id, 'NORMALIZACION');
        return v_ejecucion_id;
    end if;
    if v_documento.bloqueado_por is distinct from p_worker_id then
        raise exception 'claim no pertenece al worker';
    end if;

    select coalesce(max(intento), 0) + 1 into v_intento
      from public.normalizacion_ejecuciones
     where documento_id = p_documento_id;

    insert into public.normalizacion_ejecuciones (
        documento_id, idempotency_key, intento, disparador, estado,
        normalizador_version, resultado_hash, uso_ocr, uso_luna,
        luna_modelo, luna_campos, tokens_entrada, tokens_salida,
        tokens_total, coste_luna, pasos, resultado_json, worker_id,
        iniciado_at, finalizado_at
    ) values (
        p_documento_id, p_idempotency_key, v_intento, p_disparador,
        case when jsonb_array_length(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb)) > 0
             then 'COMPLETADA' else 'INCOMPLETA' end,
        v_documento_normalizado #>> '{metadata_tecnica,version_normalizador}',
        p_resultado_hash, coalesce((p_resultado->>'uso_ocr')::boolean, false),
        coalesce((p_resultado->>'uso_luna')::boolean, false),
        p_resultado->>'luna_modelo',
        coalesce(array(select jsonb_array_elements_text(coalesce(p_resultado->'luna_campos', '[]'::jsonb))), '{}'::text[]),
        nullif(p_resultado->>'tokens_entrada', '')::integer,
        nullif(p_resultado->>'tokens_salida', '')::integer,
        nullif(p_resultado->>'tokens_total', '')::integer,
        nullif(p_resultado->>'coste_luna', '')::numeric,
        coalesce(p_resultado->'pasos', '[]'::jsonb),
        coalesce(p_resultado_json_guardado, v_documento_normalizado), p_worker_id, now(), now()
    ) returning id into v_ejecucion_id;

    for v_factura in
        select value from jsonb_array_elements(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb))
    loop
        if nullif(v_factura->>'factura_id', '') is null then
            raise exception 'factura_id estable obligatorio en DocumentoNormalizado';
        end if;
        v_estado_factura := case
            when v_factura->>'estado_validacion' in ('VALIDADA', 'VALIDADA_CON_INCIDENCIAS')
            then 'NORMALIZADA' else 'REQUIERE_REVISION' end;

        insert into public.facturas (
            documento_id, proyeccion_clave, farmacia, pagina_inicio, pagina_fin,
            tipo_documento, categoria, requiere_conciliacion_albaranes,
            proveedor_literal, numero_factura, fecha_factura, moneda,
            base_imponible_total, iva_total, recargo_equivalencia_total,
            importe_total, requiere_revision, estado_normalizacion,
            estado_revision, normalizacion_ejecucion_id, provenance,
            datos_extraidos, updated_at, fecha_actualizacion
        ) values (
            p_documento_id, v_factura->>'factura_id', v_documento.farmacia,
            nullif(v_factura->>'pagina_inicio', '')::integer,
            nullif(v_factura->>'pagina_fin', '')::integer,
            case
                when v_factura #>> '{tipo_documento,valor}' in
                    ('FACTURA', 'ABONO', 'FACTURA_RECTIFICATIVA', 'OTRO')
                then v_factura #>> '{tipo_documento,valor}'
                when v_factura #>> '{tipo_documento,valor}' is null then 'FACTURA'
                else 'OTRO'
            end,
            case v_factura->>'naturaleza_principal'
                when 'MERCANCIA' then 'MERCANCIA'
                when 'SERVICIOS' then 'CUOTA_SERVICIO'
                else 'OTRO' end,
            coalesce((v_factura->>'requiere_conciliacion_albaranes')::boolean, false),
            v_factura #>> '{proveedor,nombre,valor}',
            v_factura #>> '{numero_factura,valor}',
            nullif(v_factura #>> '{fecha_factura,valor,iso}', '')::date,
            coalesce(v_factura #>> '{totales,moneda,valor}', 'EUR'),
            nullif(v_factura #>> '{totales,base_imponible,valor}', '')::numeric,
            nullif(v_factura #>> '{totales,iva,valor}', '')::numeric,
            nullif(v_factura #>> '{totales,recargo_equivalencia,valor}', '')::numeric,
            nullif(v_factura #>> '{totales,total,valor}', '')::numeric,
            v_estado_factura = 'REQUIERE_REVISION', v_estado_factura,
            case when v_estado_factura = 'NORMALIZADA' then 'NO_REQUERIDA'
                 else 'PENDIENTE_REVISION_PIO' end,
            v_ejecucion_id,
            jsonb_build_object('fuente', 'DOCUMENTO_NORMALIZADO', 'ejecucion_id', v_ejecucion_id),
            v_factura, now(), now()
        ) on conflict (documento_id, proyeccion_clave) do update set
            pagina_inicio = excluded.pagina_inicio,
            pagina_fin = excluded.pagina_fin,
            tipo_documento = excluded.tipo_documento,
            categoria = excluded.categoria,
            requiere_conciliacion_albaranes = excluded.requiere_conciliacion_albaranes,
            proveedor_literal = excluded.proveedor_literal,
            numero_factura = excluded.numero_factura,
            fecha_factura = excluded.fecha_factura,
            moneda = excluded.moneda,
            base_imponible_total = excluded.base_imponible_total,
            iva_total = excluded.iva_total,
            recargo_equivalencia_total = excluded.recargo_equivalencia_total,
            importe_total = excluded.importe_total,
            requiere_revision = excluded.requiere_revision,
            estado_normalizacion = excluded.estado_normalizacion,
            estado_revision = excluded.estado_revision,
            normalizacion_ejecucion_id = excluded.normalizacion_ejecucion_id,
            provenance = excluded.provenance,
            datos_extraidos = excluded.datos_extraidos,
            updated_at = now(),
            fecha_actualizacion = now()
        returning id into v_factura_id;

        delete from public.facturas_vencimientos where factura_id = v_factura_id;
        for v_item in select value from jsonb_array_elements(coalesce(v_factura->'vencimientos', '[]'::jsonb)) loop
            insert into public.facturas_vencimientos
                (factura_id, fecha_vencimiento, importe, orden, literal, provenance)
            values (v_factura_id, nullif(v_item #>> '{fecha,valor,iso}', '')::date,
                nullif(v_item #>> '{importe,valor}', '')::numeric,
                (v_item->>'orden')::integer,
                coalesce(v_item #>> '{fecha,literal}', v_item #>> '{importe,literal}'), v_item);
        end loop;

        delete from public.facturas_impuestos where factura_id = v_factura_id;
        for v_item in select value from jsonb_array_elements(coalesce(v_factura->'impuestos', '[]'::jsonb)) loop
            insert into public.facturas_impuestos
                (factura_id, concepto, base_imponible, tipo_iva, cuota_iva,
                 tipo_recargo_equivalencia, cuota_recargo_equivalencia, total_tramo,
                 orden, literal, provenance)
            values (v_factura_id, v_item #>> '{descripcion_literal,valor}',
                nullif(v_item #>> '{base,valor}', '')::numeric,
                nullif(v_item #>> '{tipo_iva,valor}', '')::numeric,
                nullif(v_item #>> '{cuota_iva,valor}', '')::numeric,
                nullif(v_item #>> '{tipo_recargo_equivalencia,valor}', '')::numeric,
                nullif(v_item #>> '{cuota_recargo_equivalencia,valor}', '')::numeric,
                nullif(v_item #>> '{total_tramo,valor}', '')::numeric,
                (v_item->>'orden')::integer, v_item #>> '{descripcion_literal,literal}', v_item);
        end loop;

        delete from public.facturas_albaranes_extraidos where factura_id = v_factura_id;
        for v_item in select value from jsonb_array_elements(coalesce(v_factura->'albaranes', '[]'::jsonb)) loop
            insert into public.facturas_albaranes_extraidos
                (factura_id, numero_albaran, fecha_albaran, tipo_movimiento,
                 importe_base, importe_total, descripcion, orden, literal, provenance)
            values (v_factura_id, v_item #>> '{numero,valor}',
                nullif(v_item #>> '{fecha,valor,iso}', '')::date, v_item->>'sentido',
                nullif(v_item #>> '{importe_base,valor}', '')::numeric,
                nullif(v_item #>> '{importe_total,valor}', '')::numeric,
                v_item #>> '{tipo_pedido,valor}', (v_item->>'orden')::integer,
                v_item #>> '{numero,literal}', v_item);
        end loop;

        delete from public.facturas_movimientos where factura_id = v_factura_id;
        for v_item in select value from jsonb_array_elements(coalesce(v_factura->'movimientos_comerciales', '[]'::jsonb)) loop
            insert into public.facturas_movimientos
                (factura_id, normalizacion_ejecucion_id, orden, categoria,
                 descripcion_literal, sentido, base, iva, recargo_equivalencia,
                 importe, provenance)
            values (v_factura_id, v_ejecucion_id, (v_item->>'orden')::integer,
                case v_item->>'tipo'
                    when 'SERVICIO' then 'SERVICIO'
                    when 'DESCUENTO' then 'DESCUENTO'
                    when 'DEVOLUCION_MERCANCIA' then 'DEVOLUCION'
                    when 'CONDICION_COMERCIAL' then 'CONDICION_COMERCIAL'
                    else 'OTRO' end,
                v_item #>> '{descripcion_literal,valor}', v_item->>'sentido',
                nullif(v_item #>> '{base,valor}', '')::numeric,
                nullif(v_item #>> '{iva,valor}', '')::numeric,
                nullif(v_item #>> '{recargo_equivalencia,valor}', '')::numeric,
                nullif(v_item #>> '{importe,valor}', '')::numeric, v_item);
        end loop;

        for v_item in select value from jsonb_array_elements(coalesce(v_factura->'incidencias', '[]'::jsonb)) loop
            insert into public.facturas_incidencias
                (factura_id, normalizacion_ejecucion_id, codigo, categoria,
                 severidad, bloqueante, mensaje_usuario, detalle_tecnico, provenance)
            values (v_factura_id, v_ejecucion_id, v_item->>'codigo', 'NORMALIZACION',
                case when v_item->>'severidad' = 'ERROR' then 'ERROR' else 'AVISO' end,
                coalesce((v_item->>'bloqueante')::boolean, false),
                coalesce(v_item->>'descripcion', v_item->>'codigo'), v_item, v_item);
        end loop;

        insert into public.historial_facturas
            (documento_id, factura_id, evento, origen, actor, estado_nuevo, detalle)
        values (p_documento_id, v_factura_id, 'PROYECCION_NORMALIZACION_REEMPLAZADA',
            'RPC', p_worker_id,
            jsonb_build_object('estado_normalizacion', v_estado_factura),
            jsonb_build_object('ejecucion_id', v_ejecucion_id,
                               'proyeccion_clave', v_factura->>'factura_id'));
    end loop;

    for v_item in select value from jsonb_array_elements(coalesce(p_resultado->'incidencias_runtime', '[]'::jsonb)) loop
        insert into public.facturas_incidencias
            (documento_id, normalizacion_ejecucion_id, codigo, categoria,
             severidad, bloqueante, mensaje_usuario, detalle_tecnico, provenance)
        values (p_documento_id, v_ejecucion_id, v_item->>'codigo',
            coalesce(v_item->>'categoria', 'NORMALIZACION'),
            coalesce(v_item->>'severidad', 'AVISO'),
            coalesce((v_item->>'bloqueante')::boolean, false),
            v_item->>'mensaje_usuario', coalesce(v_item->'detalle_tecnico', '{}'::jsonb),
            jsonb_build_object('fuente', 'RUNTIME_LOCAL'));
    end loop;

    update public.documentos_facturas
       set estado_lectura = 'NORMALIZADA',
           numero_paginas = coalesce(nullif(v_documento_normalizado->>'numero_paginas', '')::integer, numero_paginas),
           cantidad_documentos_detectados = jsonb_array_length(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb)),
           tipo_contenido = case
               when jsonb_array_length(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb)) = 0
                   then 'DESCONOCIDO'
               when jsonb_array_length(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb)) = 1
                   then 'FACTURA_UNICA'
               else 'LOTE_FACTURAS'
           end,
           bloqueado_hasta = null, bloqueado_por = null,
           reprocesar_solicitado_at = null, ultimo_error_codigo = null,
           intentos_fallo_normalizacion = 0, ultima_clase_fallo = null,
           proximo_reintento_at = null,
           fecha_fin_lectura = now(), fecha_actualizacion = now()
     where id = p_documento_id;

    insert into public.historial_facturas
        (documento_id, evento, origen, actor, estado_nuevo, detalle)
    values (p_documento_id, 'DOCUMENTO_NORMALIZADO_PERSISTIDO', 'RPC', p_worker_id,
        jsonb_build_object('estado_lectura', 'NORMALIZADA'),
        jsonb_build_object('ejecucion_id', v_ejecucion_id, 'facturas',
            jsonb_array_length(coalesce(v_documento_normalizado->'facturas', '[]'::jsonb))));

    return v_ejecucion_id;
end;
$$;

-- Nucleo multifactura (15) con la busqueda indexada y el modo de ejecucion.

create or replace function public.cf_persistir_documento_multifactura_nucleo(
    p_documento_id uuid, p_worker_id text, p_idempotency_key text,
    p_resultado_hash text, p_resultado jsonb, p_segmentos_autorizados text[],
    p_disparador text
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
        -- 26: solo las filas con el mismo nucleo de identidad (indice de expresion), en el orden de la
        -- lectura secuencial; las demas nunca cumplian la condicion de abajo.
        for otra in select id,documento_id,datos_extraidos from public.facturas
            where (public.cf_componentes_identidad_factura(datos_extraidos))[1:4]=partes[1:4]
            order by ctid loop
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
    -- Guardar lectura completa e inventario, no solo el subconjunto economico elegido.
    -- 26: una sola escritura de la ejecucion, con el modo de ejecucion del envoltorio de 7 parametros.
    ejecucion:=public.cf_persistir_normalizacion_nucleo(d.id,p_worker_id,coalesce(p_disparador,'MANUAL'),
        p_idempotency_key,p_resultado_hash,
        jsonb_build_object('resultado_json',payload,'uso_luna',false,'uso_ocr',false),
        p_resultado || jsonb_build_object(
        'multifactura',jsonb_build_object('firma_solicitud',firma,'segmentos_autorizados',to_jsonb(p_segmentos_autorizados)))
        || case when p_disparador is null then '{}'::jsonb else jsonb_build_object('provenance_ejecucion',
           jsonb_build_object('modo_ejecucion',p_disparador)) end);
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

-- RPC de un documento (12/17): misma firma y comportamiento; delega en el nucleo.
create or replace function public.cf_persistir_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_resultado_hash text,
    p_resultado jsonb
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
begin
    return public.cf_persistir_normalizacion_nucleo(
        p_documento_id, p_worker_id, p_disparador, p_idempotency_key, p_resultado_hash, p_resultado, null);
end;
$$;

-- Firma de 6 parametros (15): sin modo de ejecucion, como antes; solo propietario desde la 16.
create or replace function public.cf_persistir_documento_multifactura(
    p_documento_id uuid, p_worker_id text, p_idempotency_key text,
    p_resultado_hash text, p_resultado jsonb, p_segmentos_autorizados text[]
)
returns uuid language plpgsql security definer set search_path=public as $$
begin
    return public.cf_persistir_documento_multifactura_nucleo(
        p_documento_id, p_worker_id, p_idempotency_key, p_resultado_hash, p_resultado,
        p_segmentos_autorizados, null);
end;
$$;

-- R1 en el envoltorio multifactura de 7 parametros (17): el modo de ejecucion viaja al nucleo y se guarda
-- en la misma insercion de la ejecucion.
create or replace function public.cf_persistir_documento_multifactura(
    p_documento_id uuid,
    p_worker_id text,
    p_idempotency_key text,
    p_resultado_hash text,
    p_resultado jsonb,
    p_segmentos_autorizados text[],
    p_disparador text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_previa uuid;
    v_ejecucion uuid;
begin
    if p_disparador not in ('AUTOMATICO', 'REPROCESADO', 'MANUAL_ONE_SHOT') then
        raise exception 'DISPARADOR_MULTIFACTURA_NO_ADMITIDO';
    end if;
    -- Mismo candado que la RPC certificada: la deteccion de replay es serializada.
    perform pg_advisory_xact_lock(2151501);
    select id into v_previa
      from public.normalizacion_ejecuciones
     where documento_id = p_documento_id and idempotency_key = p_idempotency_key;

    v_ejecucion := public.cf_persistir_documento_multifactura_nucleo(
        p_documento_id,
        p_worker_id,
        p_idempotency_key,
        p_resultado_hash,
        p_resultado,
        p_segmentos_autorizados,
        p_disparador
    );

    if v_previa is not null then
        perform public.cf_cerrar_replay_normalizacion(
            p_documento_id, p_worker_id, v_ejecucion, 'MULTIFACTURA');
    end if;
    return v_ejecucion;
end;
$$;

-- Privilegios (patron 25): owner postgres; nucleos solo propietario; las RPC redefinidas con su ACL de la 16/17.
revoke all on function public.cf_persistir_normalizacion_nucleo(uuid, text, text, text, text, jsonb, jsonb)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura_nucleo(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[])
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    to service_role;

commit;
