-- Migracion 17 (Hito 2AR): replay idempotente sin estado intermedio (R1),
-- estado PROVEEDOR_NO_SOPORTADO (R2) y reintentos acotados con backoff (R3).
-- R4: no redefine el selector ni el ordering; el nucleo de la migracion 16 ya
-- excluye estados distintos de PENDIENTE/ERROR y proximo_reintento_at futuro.
-- Idempotente. Sin DML sobre datos existentes salvo defaults de columnas nuevas.
-- Generada por pruebas/auditoria_2ar/generar_migracion_17.py.
begin;

-- R2: nuevo estado documental no reclamable.
alter table public.documentos_facturas
    drop constraint if exists cf_documentos_estado_lectura_check;
alter table public.documentos_facturas
    add constraint cf_documentos_estado_lectura_check
    check (estado_lectura in (
        'PENDIENTE','PROCESANDO','EXTRAIDA','REVISION','ERROR',
        'NORMALIZANDO','NORMALIZADA',
        'PROVEEDOR_NO_SOPORTADO'
    ));

-- R3: contador, clase del ultimo fallo y parametros configurables.
alter table public.documentos_facturas
    add column if not exists intentos_fallo_normalizacion integer not null default 0,
    add column if not exists ultima_clase_fallo text;
alter table public.documentos_facturas
    drop constraint if exists cf_documentos_intentos_fallo_check,
    drop constraint if exists cf_documentos_ultima_clase_fallo_check;
alter table public.documentos_facturas
    add constraint cf_documentos_intentos_fallo_check
        check (intentos_fallo_normalizacion >= 0),
    add constraint cf_documentos_ultima_clase_fallo_check
        check (ultima_clase_fallo is null or ultima_clase_fallo in
            ('NO_SOPORTADO', 'DEFECTO_DOCUMENTO', 'TRANSITORIO'));

alter table public.normalizacion_ejecuciones
    add column if not exists clase_fallo text;
alter table public.normalizacion_ejecuciones
    drop constraint if exists cf_ejecuciones_clase_fallo_check;
alter table public.normalizacion_ejecuciones
    add constraint cf_ejecuciones_clase_fallo_check
        check (clase_fallo is null or clase_fallo in
            ('NO_SOPORTADO', 'DEFECTO_DOCUMENTO', 'TRANSITORIO'));

alter table public.cf_configuracion
    add column if not exists normalizacion_max_intentos integer not null default 4,
    add column if not exists normalizacion_backoff interval[] not null
        default array[interval '1 hour', interval '6 hours', interval '24 hours'];
alter table public.cf_configuracion
    drop constraint if exists cf_configuracion_reintentos_check;
alter table public.cf_configuracion
    add constraint cf_configuracion_reintentos_check check (
        normalizacion_max_intentos between 1 and 20
        and cardinality(normalizacion_backoff) >= 1
        and cardinality(normalizacion_backoff) >= normalizacion_max_intentos - 1
        and interval '0' < all(normalizacion_backoff)
    );

-- R1: cierre comun del replay. Libera el claim del llamante y restaura el estado
-- final de la ejecucion original. No crea ni modifica facturas ni ejecuciones.
create or replace function public.cf_cerrar_replay_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_ejecucion_id uuid,
    p_origen text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    d public.documentos_facturas%rowtype;
    v_persistencia text;
    v_lectura text;
    v_liberado boolean := false;
begin
    if p_origen not in ('MULTIFACTURA', 'NORMALIZACION') then
        raise exception 'ORIGEN_REPLAY_NO_ADMITIDO';
    end if;
    select * into d from public.documentos_facturas where id = p_documento_id for update;
    if d.id is null then
        raise exception 'documento no encontrado';
    end if;
    v_persistencia := d.estado_persistencia;
    v_lectura := d.estado_lectura;
    if d.bloqueado_por is not null and d.bloqueado_por = p_worker_id then
        if p_origen = 'MULTIFACTURA' then
            select h.estado_nuevo->>'estado_persistencia' into v_persistencia
              from public.historial_facturas h
             where h.documento_id = d.id
               and h.evento = 'INVENTARIO_MULTIFACTURA'
               and h.detalle->>'ejecucion_id' = p_ejecucion_id::text
             order by h.created_at desc, h.id desc
             limit 1;
            v_persistencia := coalesce(v_persistencia, d.estado_persistencia);
            v_lectura := case when v_persistencia = 'COMPLETA' then 'NORMALIZADA' else 'REVISION' end;
        else
            v_lectura := 'NORMALIZADA';
        end if;
        update public.documentos_facturas
           set estado_lectura = v_lectura,
               estado_persistencia = v_persistencia,
               bloqueado_por = null,
               bloqueado_hasta = null,
               reprocesar_solicitado_at = null,
               fecha_actualizacion = now()
         where id = d.id;
        v_liberado := true;
    end if;
    insert into public.historial_facturas
        (documento_id, evento, origen, actor, estado_nuevo, detalle)
    values (
        d.id, 'NORMALIZACION_REPLAY_IDEMPOTENTE', 'RPC', p_worker_id,
        jsonb_build_object('estado_lectura', v_lectura, 'estado_persistencia', v_persistencia),
        jsonb_build_object('ejecucion_id', p_ejecucion_id, 'origen', p_origen,
                           'claim_liberado', v_liberado)
    );
end;
$$;

-- R1 en la persistencia de un documento (mismo patron de retorno temprano).
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
        v_documento_normalizado, p_worker_id, now(), now()
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

-- R1 en el envoltorio multifactura de 7 parametros.
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

    v_ejecucion := public.cf_persistir_documento_multifactura(
        p_documento_id,
        p_worker_id,
        p_idempotency_key,
        p_resultado_hash,
        p_resultado,
        p_segmentos_autorizados
    );

    if v_previa is not null then
        perform public.cf_cerrar_replay_normalizacion(
            p_documento_id, p_worker_id, v_ejecucion, 'MULTIFACTURA');
        return v_ejecucion;
    end if;

    update public.normalizacion_ejecuciones
       set disparador = p_disparador,
           resultado_json = coalesce(resultado_json, '{}'::jsonb)
               || jsonb_build_object(
                   'provenance_ejecucion',
                   jsonb_build_object('modo_ejecucion', p_disparador)
               )
     where id = v_ejecucion;
    return v_ejecucion;
end;
$$;

-- R2/R3: fallo clasificado. Retransmision sin claim -> devuelve la ejecucion
-- existente sin cambios; misma clave con claim vigente -> nuevo intento con clave
-- derivada unica.
create or replace function public.cf_registrar_fallo_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_error_codigo text,
    p_error_detalle text,
    p_clase_fallo text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    d public.documentos_facturas%rowtype;
    v_existente uuid;
    v_ejecucion_id uuid;
    v_intento integer;
    v_clave text := p_idempotency_key;
    v_fallos integer;
    v_max integer;
    v_backoff interval[];
    v_estado text;
    v_proximo timestamptz;
begin
    if p_clase_fallo is null
       or p_clase_fallo not in ('NO_SOPORTADO', 'DEFECTO_DOCUMENTO', 'TRANSITORIO') then
        raise exception 'CLASE_FALLO_NO_ADMITIDA';
    end if;
    if nullif(btrim(p_worker_id), '') is null
       or nullif(btrim(p_idempotency_key), '') is null then
        raise exception 'worker_id e idempotency_key obligatorios';
    end if;

    select * into d from public.documentos_facturas where id = p_documento_id for update;
    select id into v_existente
      from public.normalizacion_ejecuciones
     where documento_id = p_documento_id and idempotency_key = p_idempotency_key;

    if d.id is null
       or d.bloqueado_por is distinct from p_worker_id
       or not exists (
           select 1 from public.cf_configuracion c
            where c.id = true and d.farmacia = any(c.farmacias_habilitadas)
       ) then
        if v_existente is not null then
            return v_existente;
        end if;
        raise exception 'claim no pertenece al worker';
    end if;

    select coalesce(max(intento), 0) + 1 into v_intento
      from public.normalizacion_ejecuciones where documento_id = p_documento_id;
    if v_existente is not null then
        v_clave := p_idempotency_key || ':intento:' || v_intento;
    end if;

    select normalizacion_max_intentos, normalizacion_backoff
      into v_max, v_backoff
      from public.cf_configuracion where id = true;

    if p_clase_fallo = 'NO_SOPORTADO' then
        v_estado := 'PROVEEDOR_NO_SOPORTADO';
        v_fallos := d.intentos_fallo_normalizacion;
        v_proximo := null;
    else
        v_fallos := d.intentos_fallo_normalizacion + 1;
        if v_fallos >= v_max then
            v_estado := 'REVISION';
            v_proximo := null;
        else
            v_estado := 'ERROR';
            v_proximo := now() + v_backoff[least(v_fallos, cardinality(v_backoff))];
        end if;
    end if;

    insert into public.normalizacion_ejecuciones
        (documento_id, idempotency_key, intento, disparador, estado, worker_id,
         iniciado_at, finalizado_at, error_codigo, error_detalle, clase_fallo)
    values (p_documento_id, v_clave, v_intento, p_disparador, 'ERROR',
        p_worker_id, now(), now(), p_error_codigo, p_error_detalle, p_clase_fallo)
    returning id into v_ejecucion_id;

    update public.documentos_facturas
       set estado_lectura = v_estado,
           ultimo_error_codigo = p_error_codigo,
           ultima_clase_fallo = p_clase_fallo,
           intentos_fallo_normalizacion = v_fallos,
           proximo_reintento_at = v_proximo,
           bloqueado_hasta = null, bloqueado_por = null,
           reprocesar_solicitado_at = null, fecha_actualizacion = now()
     where id = p_documento_id;
    insert into public.historial_facturas
        (documento_id, evento, origen, actor, estado_nuevo, detalle)
    values (p_documento_id, 'NORMALIZACION_ERROR', 'RPC', p_worker_id,
        jsonb_build_object('estado_lectura', v_estado,
                           'proximo_reintento_at', v_proximo),
        jsonb_build_object('ejecucion_id', v_ejecucion_id, 'codigo', p_error_codigo,
                           'clase_fallo', p_clase_fallo, 'intentos_fallo', v_fallos,
                           'max_intentos', v_max));
    return v_ejecucion_id;
end;
$$;

-- Firma de 6 parametros conservada por compatibilidad: sin clase explicita se
-- trata como TRANSITORIO (reintentos acotados), nunca como no soportado.
create or replace function public.cf_registrar_fallo_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_error_codigo text,
    p_error_detalle text
)
returns uuid
language sql
security definer
set search_path = public
as $$
    select public.cf_registrar_fallo_normalizacion(
        p_documento_id, p_worker_id, p_disparador, p_idempotency_key,
        p_error_codigo, p_error_detalle, 'TRANSITORIO');
$$;

-- Reprocesado explicito: unica via de vuelta a la cola para
-- PROVEEDOR_NO_SOPORTADO y REVISION; reinicia el presupuesto de reintentos.
create or replace function public.cf_solicitar_reprocesado(
    p_documento_id uuid,
    p_actor text default null
)
returns public.documentos_facturas
language plpgsql
security definer
set search_path = public
as $$
declare
    v_documento public.documentos_facturas%rowtype;
    v_actor text := coalesce(auth.uid()::text, nullif(btrim(p_actor), ''), 'SISTEMA');
begin
    update public.documentos_facturas d
       set reprocesar_solicitado_at = now(),
           proximo_reintento_at = null,
           intentos_fallo_normalizacion = 0,
           ultima_clase_fallo = null,
           bloqueado_hasta = null,
           bloqueado_por = null,
           ultimo_error_codigo = null,
           estado_lectura = 'PENDIENTE',
           fecha_actualizacion = now()
     where d.id = p_documento_id
       and exists (
           select 1 from public.cf_configuracion c
           where c.id = true and d.farmacia = any(c.farmacias_habilitadas)
       )
     returning * into v_documento;

    if v_documento.id is null then
        raise exception 'documento no encontrado';
    end if;

    insert into public.historial_facturas (
        documento_id, evento, origen, actor, estado_nuevo
    ) values (
        v_documento.id, 'REPROCESADO_SOLICITADO', 'RPC', v_actor,
        jsonb_build_object('estado_lectura', v_documento.estado_lectura)
    );

    return v_documento;
end;
$$;

revoke all on function public.cf_cerrar_replay_normalizacion(uuid, text, uuid, text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text)
    from public, anon, authenticated;
revoke all on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text)
    to service_role;
grant execute on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text)
    to service_role;

-- 2AS: privilegios explicitos tambien en las funciones redefinidas. En Supabase
-- las funciones nuevas de public reciben EXECUTE por defecto para anon,
-- authenticated y service_role; ninguna funcion de la 17 depende de la ACL previa.
revoke all on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    to service_role;
-- Ningun rol del sistema invoca el reprocesado: solo accion explicita de Pio.
-- Retira el EXECUTE de authenticated concedido por la migracion 12.
revoke all on function public.cf_solicitar_reprocesado(uuid, text)
    from public, anon, authenticated;

comment on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text) is
    'Fallo clasificado (R2/R3): NO_SOPORTADO -> PROVEEDOR_NO_SOPORTADO; resto -> ERROR con backoff o REVISION al maximo.';

commit;
