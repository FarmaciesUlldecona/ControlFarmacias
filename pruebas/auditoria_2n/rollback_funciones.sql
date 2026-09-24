-- Hito 2N: restauracion de funcion previa; ejecutar solo con criterio de rollback demostrado.
BEGIN;
CREATE OR REPLACE FUNCTION public.cf_reclamar_factura_conciliacion(p_worker_id text, p_bloqueo_segundos integer DEFAULT 300)
 RETURNS SETOF facturas
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
declare
    v_id uuid;
begin
    if p_worker_id is null or btrim(p_worker_id) = '' then
        raise exception 'worker_id obligatorio';
    end if;

    select f.id
      into v_id
      from public.facturas f
      cross join public.cf_configuracion c
     where c.id = true
       and f.farmacia = any(c.farmacias_habilitadas)
       and (
           c.conciliacion_automatica
           or f.conciliacion_reintento_solicitado_at is not null
       )
       and f.estado_normalizacion = 'NORMALIZADA'
       and f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'
       and f.requiere_conciliacion_albaranes
       and coalesce(f.conciliacion_proximo_at, '-infinity'::timestamptz) <= now()
       and coalesce(f.conciliacion_bloqueado_hasta, '-infinity'::timestamptz) <= now()
     order by
       (f.conciliacion_reintento_solicitado_at is not null) desc,
       f.fecha_factura nulls last,
       f.id
     for update of f skip locked
     limit 1;

    if v_id is null then
        return;
    end if;

    return query
    update public.facturas
       set conciliacion_bloqueado_por = p_worker_id,
           conciliacion_bloqueado_hasta = now() + make_interval(secs => greatest(p_bloqueo_segundos, 1)),
           updated_at = now()
     where id = v_id
     returning *;
end;
$function$
;
ALTER FUNCTION public.cf_reclamar_factura_conciliacion(text,integer) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.cf_reclamar_factura_conciliacion(text,integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cf_reclamar_factura_conciliacion(text,integer) TO service_role;
DROP FUNCTION IF EXISTS public.cf_evaluar_elegibilidad_conciliacion(uuid);
COMMIT;
