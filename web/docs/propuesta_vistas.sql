-- PROPUESTA H1 (web fase 1). NO APLICAR. No es una migración ni está numerada.
-- Base: esquema resultante de las migraciones 06–20 (producción) y 21 (solo local).
-- Ninguna vista depende de la 21 (conciliacion_albaranes_reservados).
-- Reglas:
--   * security_invoker = true y filtro cf_configuracion.farmacias_habilitadas (solo PIO).
--   * Importe ausente = NULL. Nunca coalesce(importe, 0); sum() ignora NULL y los
--     NULL se cuentan aparte.
--   * Los tres estados (normalización / conciliación / revisión Pío) van siempre en
--     columnas separadas.
--   * Tolerancia: se muestra la del motor (R11: conciliaciones.tolerancia,
--     resultado y provenance.tolerancia_regla) y la diferencia exacta; la web no
--     recalcula ningún umbral.
--   * Signo: los importes se guardan con el signo impreso en el documento; el
--     sentido va en tipo_documento / sentido. No inferir signo del número.
--   * SIN GRANTS: la migración 19 retiró todo a anon/authenticated. A qué rol se
--     expone es una decisión aparte de Pío.

begin;

-- 1. Inicio: contadores por estado, cada eje por separado.
--    Contadores de cabecera de Inicio (CLAUDE.md):
--      pendientes_procesar = PDF en PENDIENTE / PROCESANDO
--      documentos_sin_leer = PDF en ERROR / PROVEEDOR_NO_SOPORTADO (rojo)
--      requieren_revision  = facturas en REQUIERE_REVISION (normalización)
--                            o REVISION_CONCILIACION (conciliación); una factura
--                            en ambos cuenta una vez. Desglose en norm_revision
--                            y conc_revision.
create or replace view public.v_web_inicio_resumen
with (security_invoker = true)
as
with farmacias as (
    select unnest(cfg.farmacias_habilitadas) as farmacia
      from public.cf_configuracion cfg
     where cfg.id = true
),
docs as (
    select
        d.farmacia,
        count(*) filter (where d.estado_lectura in ('PENDIENTE', 'PROCESANDO'))
            as pendientes_procesar,
        count(*) filter (where d.estado_lectura in ('ERROR', 'PROVEEDOR_NO_SOPORTADO'))
            as documentos_sin_leer
      from public.documentos_facturas d
      join farmacias fa on fa.farmacia = d.farmacia
     group by d.farmacia
),
fact as (
select
    f.farmacia,
    count(*) as facturas,
    count(*) filter (where f.estado_normalizacion = 'REQUIERE_REVISION'
                        or f.estado_conciliacion_cf = 'REVISION_CONCILIACION')
        as requieren_revision,
    -- normalización
    count(*) filter (where f.estado_normalizacion = 'PENDIENTE')            as norm_pendiente,
    count(*) filter (where f.estado_normalizacion = 'NORMALIZANDO')         as norm_en_curso,
    count(*) filter (where f.estado_normalizacion = 'NORMALIZADA')          as norm_ok,
    count(*) filter (where f.estado_normalizacion = 'REQUIERE_REVISION')    as norm_revision,
    -- conciliación
    count(*) filter (where f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR')   as conc_pendiente,
    count(*) filter (where f.estado_conciliacion_cf = 'CONCILIADA')            as conc_ok,
    count(*) filter (where f.estado_conciliacion_cf = 'REVISION_CONCILIACION') as conc_revision,
    count(*) filter (where not f.requiere_conciliacion_albaranes)              as conc_no_aplica,
    -- revisión Pío
    count(*) filter (where f.estado_revision = 'NO_REQUERIDA')           as rev_no_requerida,
    count(*) filter (where f.estado_revision = 'PENDIENTE_REVISION_PIO') as rev_pendiente,
    count(*) filter (where f.estado_revision = 'VALIDADA_PIO')           as rev_validada,
    -- importes (NULL-aware)
    count(*) filter (where f.importe_total is null) as facturas_sin_importe,
    sum(f.importe_total)                            as importe_total_conocido,
    -- incidencias de factura
    coalesce(sum(i.abiertas), 0)    as incidencias_abiertas,
    coalesce(sum(i.bloqueantes), 0) as incidencias_bloqueantes
from public.facturas f
join farmacias fa on fa.farmacia = f.farmacia
left join lateral (
    select count(*) filter (where fi.estado = 'ABIERTA') as abiertas,
           count(*) filter (where fi.estado = 'ABIERTA' and fi.bloqueante) as bloqueantes
      from public.facturas_incidencias fi
     where fi.factura_id = f.id
) i on true
group by f.farmacia
)
select
    fa.farmacia,
    coalesce(docs.pendientes_procesar, 0) as pendientes_procesar,
    coalesce(docs.documentos_sin_leer, 0) as documentos_sin_leer,
    coalesce(fact.requieren_revision, 0)  as requieren_revision,
    coalesce(fact.facturas, 0)            as facturas,
    fact.norm_pendiente, fact.norm_en_curso, fact.norm_ok, fact.norm_revision,
    fact.conc_pendiente, fact.conc_ok, fact.conc_revision, fact.conc_no_aplica,
    fact.rev_no_requerida, fact.rev_pendiente, fact.rev_validada,
    fact.facturas_sin_importe,
    fact.importe_total_conocido,          -- NULL si no hay ningún importe conocido
    fact.incidencias_abiertas, fact.incidencias_bloqueantes
from farmacias fa
left join docs on docs.farmacia = fa.farmacia
left join fact on fact.farmacia = fa.farmacia;

-- 2. Inicio: PDF y su estado técnico, incluidos los que no generan factura
--    (PROVEEDOR_NO_SOPORTADO, ERROR, REVISION...).
create or replace view public.v_web_documentos_estado
with (security_invoker = true)
as
select
    d.id as documento_id,
    d.farmacia,
    d.archivo_nombre,
    d.archivo_hash,
    d.fecha_importacion,
    d.estado_lectura,
    d.estado_persistencia,
    d.intentos_fallo_normalizacion,
    d.ultima_clase_fallo,
    d.ultimo_error_codigo,
    d.proximo_reintento_at,
    d.numero_paginas,
    d.cantidad_documentos_detectados,
    (select count(*) from public.facturas f where f.documento_id = d.id) as facturas,
    (select count(*) from public.facturas_incidencias fi
      where fi.documento_id = d.id and fi.estado = 'ABIERTA') as incidencias_documento_abiertas
from public.documentos_facturas d
cross join public.cf_configuracion cfg
where cfg.id = true
  and d.farmacia = any(cfg.farmacias_habilitadas);

-- 3. Detalle: cabecera + documento + ejecución de normalización (extractor, Luna)
--    + conciliación vigente.
create or replace view public.v_web_factura_detalle
with (security_invoker = true)
as
select
    f.id as factura_id,
    f.farmacia,
    f.documento_id,
    -- documento / PDF
    d.archivo_nombre,
    d.archivo_ruta,              -- ruta en bucket privado facturas-pdf (signed URL backend)
    d.archivo_hash,
    d.numero_paginas,
    f.pagina_inicio,
    f.pagina_fin,
    d.estado_lectura,
    d.estado_persistencia,
    d.fecha_importacion,
    -- identificación
    f.tipo_documento,
    f.categoria,
    f.numero_factura,
    f.fecha_factura,
    f.moneda,
    f.proveedor_id,
    p.codigo  as proveedor_codigo,
    coalesce(p.nombre, f.proveedor_literal, f.proveedor_nombre) as proveedor,
    f.proveedor_literal,
    f.proveedor_cif,
    f.id_proveedor_albaranes,
    -- importes (NULL = desconocido)
    f.base_imponible_total,
    f.iva_total,
    f.recargo_equivalencia_total,
    f.importe_total,
    f.cuadre_fiscal_correcto,
    f.diferencia_cuadre,
    -- tres estados separados
    f.estado_normalizacion,
    f.estado_conciliacion_cf,
    f.estado_revision,
    f.estado_pago,
    f.requiere_conciliacion_albaranes,
    f.conciliacion_intentos,
    f.conciliacion_intentos_fallo,
    f.conciliacion_ultima_clase_fallo,
    f.conciliacion_proximo_at,
    -- extractor / normalización (de la ejecución que produjo la proyección)
    p.extractor_codigo   as proveedor_extractor_codigo,
    p.nivel_confianza    as proveedor_nivel_confianza,
    ne.id                as normalizacion_ejecucion_id,
    ne.disparador        as normalizacion_disparador,
    ne.estado            as normalizacion_ejecucion_estado,
    ne.extractor_usado,
    ne.normalizador_version,
    ne.uso_ocr,
    ne.uso_luna,
    ne.luna_modelo,
    ne.luna_campos,
    ne.tokens_total,
    ne.coste_luna,
    ne.finalizado_at     as normalizacion_finalizada_at,
    f.provenance         as factura_provenance,
    -- conciliación vigente
    c.id                 as conciliacion_id,
    c.intento            as conciliacion_intento,
    c.disparador         as conciliacion_disparador,
    c.estado             as conciliacion_estado,
    c.resultado          as conciliacion_resultado,
    c.importe_factura    as conciliacion_importe_factura,
    c.importe_explicado  as conciliacion_importe_explicado,
    c.diferencia         as conciliacion_diferencia,
    c.tolerancia         as conciliacion_tolerancia,
    c.provenance -> 'tolerancia_regla' as conciliacion_tolerancia_regla,
    c.finalizado_at      as conciliacion_finalizada_at,
    f.updated_at
from public.facturas f
join public.documentos_facturas d on d.id = f.documento_id
cross join public.cf_configuracion cfg
left join public.proveedores p on p.id = f.proveedor_id
left join public.normalizacion_ejecuciones ne on ne.id = f.normalizacion_ejecucion_id
left join public.conciliaciones c on c.factura_id = f.id and c.es_actual
where cfg.id = true
  and f.farmacia = any(cfg.farmacias_habilitadas);

-- 4. Conciliación: líneas de cada conciliación con el documental y el albarán de
--    Farmatic (vía Supabase.albaranes). Tipo de casado = tipo_relacion + provenance.
create or replace view public.v_web_conciliacion_lineas
with (security_invoker = true)
as
select
    c.factura_id,
    f.farmacia,
    c.id          as conciliacion_id,
    c.intento,
    c.es_actual,
    cd.id         as detalle_id,
    cd.orden,
    cd.tipo_relacion,
    cd.estado     as estado_linea,
    cd.provenance ->> 'estado_matching'     as estado_matching,
    cd.provenance ->> 'coincidencia_numero' as coincidencia_numero,
    cd.provenance ->> 'clase_numero'        as clase_numero,
    cd.coincidencia_numero_literal,
    -- lado documental (PDF)
    cd.factura_albaran_extraido_id,
    cd.factura_movimiento_id,
    coalesce(cd.numero_albaran_documental, fae.numero_albaran) as numero_albaran_documental,
    fae.fecha_albaran   as fecha_albaran_documental,
    fae.tipo_movimiento as sentido_documental,
    cd.importe_documental,
    -- lado Farmatic
    cd.albaran_farmacia,
    cd.albaran_id_contador,
    coalesce(cd.numero_albaran_farmatic, a.numero_albaran) as numero_albaran_farmatic,
    a.fecha       as fecha_albaran_farmatic,
    a.id_proveedor as farmatic_id_proveedor,
    a.importe_puc,
    a.importe_pvp,
    cd.importe_farmatic,
    cd.importe_aplicado,
    cd.diferencia
from public.conciliacion_detalles cd
join public.conciliaciones c on c.id = cd.conciliacion_id
join public.facturas f on f.id = c.factura_id
cross join public.cf_configuracion cfg
left join public.facturas_albaranes_extraidos fae on fae.id = cd.factura_albaran_extraido_id
left join public.albaranes a
       on a.farmacia = cd.albaran_farmacia
      and a.id_contador = cd.albaran_id_contador
where cfg.id = true
  and f.farmacia = any(cfg.farmacias_habilitadas);

-- 5. Incidencias (ámbito documento o factura) con farmacia resuelta.
create or replace view public.v_web_incidencias
with (security_invoker = true)
as
select
    fi.id as incidencia_id,
    coalesce(f.farmacia, d.farmacia) as farmacia,
    fi.documento_id,
    fi.factura_id,
    f.numero_factura,
    coalesce(d.archivo_nombre, df.archivo_nombre) as archivo_nombre,
    fi.codigo,
    fi.categoria,
    fi.severidad,
    fi.bloqueante,
    fi.estado,
    fi.mensaje_usuario,
    fi.detalle_tecnico,
    fi.created_at,
    fi.resuelta_at,
    fi.resuelta_por
from public.facturas_incidencias fi
left join public.facturas f on f.id = fi.factura_id
left join public.documentos_facturas df on df.id = f.documento_id
left join public.documentos_facturas d on d.id = fi.documento_id
cross join public.cf_configuracion cfg
where cfg.id = true
  and coalesce(f.farmacia, d.farmacia) = any(cfg.farmacias_habilitadas);

-- 6. Historial (append-only) con farmacia resuelta.
create or replace view public.v_web_historial
with (security_invoker = true)
as
select
    h.id as evento_id,
    coalesce(f.farmacia, d.farmacia) as farmacia,
    h.documento_id,
    h.factura_id,
    h.evento,
    h.origen,
    h.actor,
    h.estado_anterior,
    h.estado_nuevo,
    h.detalle,
    h.created_at
from public.historial_facturas h
left join public.facturas f on f.id = h.factura_id
left join public.documentos_facturas d on d.id = h.documento_id
cross join public.cf_configuracion cfg
where cfg.id = true
  and coalesce(f.farmacia, d.farmacia) = any(cfg.farmacias_habilitadas);

-- 7. Vencimientos v2: añade literal, tipo de documento y los tres estados.
--    importe NULL se conserva (R14: sin importe + incidencia).
create or replace view public.v_web_vencimientos
with (security_invoker = true)
as
select
    v.id as vencimiento_id,
    v.factura_id,
    f.farmacia,
    f.numero_factura,
    f.tipo_documento,
    coalesce(p.nombre, f.proveedor_literal, f.proveedor_nombre) as proveedor,
    v.orden,
    v.fecha_vencimiento,
    v.importe,
    (v.importe is not null) as importe_conocido,
    v.literal,
    f.importe_total as importe_factura,
    count(*) over (partition by v.factura_id) as vencimientos_factura,
    f.estado_normalizacion,
    f.estado_conciliacion_cf,
    f.estado_revision,
    f.estado_pago,
    v.provenance
from public.facturas_vencimientos v
join public.facturas f on f.id = v.factura_id
left join public.proveedores p on p.id = f.proveedor_id
cross join public.cf_configuracion cfg
where cfg.id = true
  and f.farmacia = any(cfg.farmacias_habilitadas);

-- 8. Cashflow semanal: suma solo importes conocidos; los desconocidos se cuentan.
--    Cargos y abonos por separado (no se infiere signo). Semana NULL = sin fecha.
create or replace view public.v_web_cashflow_semanal
with (security_invoker = true)
as
select
    f.farmacia,
    date_trunc('week', v.fecha_vencimiento)::date as semana,
    count(*) as vencimientos,
    count(*) filter (where v.importe is null) as vencimientos_sin_importe,
    sum(v.importe) filter (where f.tipo_documento <> 'ABONO') as importe_cargos_conocido,
    sum(v.importe) filter (where f.tipo_documento = 'ABONO')  as importe_abonos_conocido,
    count(*) filter (where f.estado_revision <> 'VALIDADA_PIO') as vencimientos_sin_validar
from public.facturas_vencimientos v
join public.facturas f on f.id = v.factura_id
cross join public.cf_configuracion cfg
where cfg.id = true
  and f.farmacia = any(cfg.farmacias_habilitadas)
  and f.estado_pago <> 'PAGADA'
group by f.farmacia, date_trunc('week', v.fecha_vencimiento)::date;

-- 9. Proveedores v2: añade REVISION_CONCILIACION, incidencias, alias y última factura.
create or replace view public.v_web_proveedores_estado
with (security_invoker = true)
as
select
    p.id,
    p.codigo,
    p.nombre,
    p.farmatic_id_proveedor,
    p.extractor_codigo,
    p.nivel_confianza,
    p.activo,
    (select array_agg(pa.alias order by pa.alias)
       from public.proveedores_alias pa where pa.proveedor_id = p.id) as alias,
    count(f.id) as facturas,
    count(f.id) filter (where f.estado_normalizacion = 'REQUIERE_REVISION')     as norm_revision,
    count(f.id) filter (where f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR')   as conc_pendiente,
    count(f.id) filter (where f.estado_conciliacion_cf = 'CONCILIADA')            as conc_ok,
    count(f.id) filter (where f.estado_conciliacion_cf = 'REVISION_CONCILIACION') as conc_revision,
    count(f.id) filter (where f.estado_revision = 'PENDIENTE_REVISION_PIO')       as rev_pendiente,
    count(f.id) filter (where f.importe_total is null) as facturas_sin_importe,
    sum(f.importe_total)                               as importe_total_conocido,
    max(f.fecha_factura)                               as ultima_fecha_factura
from public.proveedores p
cross join public.cf_configuracion cfg
left join public.facturas f
    on f.proveedor_id = p.id
   and f.farmacia = any(cfg.farmacias_habilitadas)
where cfg.id = true
group by p.id;

-- 10. Configuración: solo interruptores y parámetros; sin hashes de preflight.
create or replace view public.v_web_configuracion
with (security_invoker = true)
as
select
    c.farmacias_habilitadas,
    c.normalizacion_automatica,
    c.conciliacion_automatica,
    c.luna_habilitada,
    c.tolerancia_conciliacion,
    c.conciliacion_tolerancia_suelo,
    c.conciliacion_tolerancia_por_albaran,
    c.conciliacion_tolerancia_tope,
    c.normalizacion_max_intentos,
    c.normalizacion_backoff,
    c.conciliacion_max_intentos,
    c.conciliacion_backoff,
    c.updated_at
from public.cf_configuracion c
where c.id = true;

rollback;  -- propuesta: nunca confirmar desde este archivo
