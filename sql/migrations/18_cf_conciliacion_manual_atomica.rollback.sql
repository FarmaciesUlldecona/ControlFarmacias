-- Rollback de la migracion 18 (Hito 2AV). Restaura el esquema 17.
-- Orden obligatorio: primero revertir el Python de 2AV y despues este SQL.
-- Unico DML: valores nuevos de la 18 -> REVISION_CONCILIACION pasa a
-- PENDIENTE_CONCILIAR y el disparador MANUAL_ONE_SHOT pasa a MANUAL.
begin;

drop function if exists public.cf_reclamar_factura_conciliacion_manual_one_shot(text, integer);
drop function if exists public.cf_persistir_conciliacion(uuid, text, text, text, jsonb);
drop function if exists public.cf_registrar_fallo_conciliacion(uuid, text, text, text, text, text);

-- Claim de la migracion 14, literal.
create or replace function public.cf_reclamar_factura_conciliacion(
    p_worker_id text,
    p_bloqueo_segundos integer default 300
)
returns setof public.facturas
language plpgsql
security definer
set search_path = public
as $$
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
      cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e
     where c.id = true
       and f.farmacia = any(c.farmacias_habilitadas)
       and (c.conciliacion_automatica or f.conciliacion_reintento_solicitado_at is not null)
       and f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'
       and e.estado = 'APTA'
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
$$;

revoke all on function public.cf_reclamar_factura_conciliacion(text, integer)
    from public, anon, authenticated;
grant execute on function public.cf_reclamar_factura_conciliacion(text, integer)
    to service_role;

drop function if exists public.cf_reclamar_factura_conciliacion_nucleo(text, integer, text);

update public.facturas
   set estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'
 where estado_conciliacion_cf = 'REVISION_CONCILIACION';
alter table public.facturas
    drop constraint if exists facturas_estado_conciliacion_cf_check;
alter table public.facturas
    add constraint facturas_estado_conciliacion_cf_check
    check (estado_conciliacion_cf in (
        'PENDIENTE_CONCILIAR',
        'CONCILIADA'
    ));
alter table public.facturas
    drop constraint if exists facturas_conciliacion_intentos_fallo_check,
    drop constraint if exists facturas_conciliacion_ultima_clase_fallo_check;
alter table public.facturas
    drop column if exists conciliacion_intentos_fallo,
    drop column if exists conciliacion_ultima_clase_fallo;

alter table public.cf_configuracion
    drop constraint if exists cf_configuracion_reintentos_conciliacion_check;
alter table public.cf_configuracion
    drop column if exists conciliacion_max_intentos,
    drop column if exists conciliacion_backoff;

update public.conciliaciones
   set disparador = 'MANUAL'
 where disparador = 'MANUAL_ONE_SHOT';
alter table public.conciliaciones
    drop constraint if exists conciliaciones_disparador_check;
alter table public.conciliaciones
    add constraint conciliaciones_disparador_check
    check (disparador in ('AUTOMATICO', 'MANUAL', 'REINTENTO', 'TEST'));
drop index if exists public.conciliaciones_factura_idempotency_unico;
alter table public.conciliaciones
    drop column if exists idempotency_key;

commit;
