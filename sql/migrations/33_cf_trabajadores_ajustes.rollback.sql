-- Rollback de la migracion 33 (Hito TRAB-33): devuelve el esquema exacto de la 32.
-- Elimina trabajadoras_ajustes_anuales (CON SUS DATOS), las columnas de vacaciones del convenio y la columna anulado de
-- eventos_calendario, y restaura la unicidad (trabajadora, fecha, franja) sobre todos los eventos. Falla cerrado si hay
-- eventos anulados que la romperian (ROLLBACK_33_EVENTOS_ANULADOS_DUPLICADOS): no se borra ningun evento. Solo con
-- confirmacion de Pio. Facturas, albaranes y conciliacion sin cambios.
-- (AUTORIZACION EXPRESA DE PIO, 2026-11-14: el rol del sistema solo se nombra en la 33 y en este rollback; aqui, para
-- retirar de nuevo los privilegios por defecto de Supabase sobre la vista recreada.)
begin;

do $$
begin
    if exists (
        select 1 from public.eventos_calendario
        group by trabajadora_id, fecha, franja having count(*) > 1
    ) then
        raise exception 'ROLLBACK_33_EVENTOS_ANULADOS_DUPLICADOS';
    end if;
end;
$$;

drop table if exists public.trabajadoras_ajustes_anuales;

alter table public.convenio_anual drop constraint if exists convenio_anual_vacaciones_con_fuente;
alter table public.convenio_anual drop column if exists vacaciones_dias_naturales;
alter table public.convenio_anual drop column if exists vacaciones_fuente;

-- La vista depende de la columna: se recrea tal como la dejo la 31.
drop view if exists public.v_eventos_calendario_horas;
drop index if exists public.eventos_calendario_unico;
alter table public.eventos_calendario drop column if exists anulado;
alter table public.eventos_calendario add constraint eventos_calendario_unico unique (trabajadora_id, fecha, franja);

create or replace function public.cf_trab_comprobar_evento()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
    if not exists (
        select 1 from public.trabajadoras t
        where t.id = new.trabajadora_id and not t.anulada and new.fecha >= t.fecha_alta
          and (t.fecha_baja is null or new.fecha <= t.fecha_baja)
    ) then
        raise exception 'EVENTO_FUERA_DEL_ALTA:%:%', new.trabajadora_id, new.fecha;
    end if;
    return new;
end;
$$;

create view public.v_eventos_calendario_horas
with (security_invoker = true) as
select e.id, e.trabajadora_id, e.farmacia, e.fecha, e.franja, e.tipo, e.estado, e.horas, e.nota,
       coalesce(e.horas, case when t.tipo_jornada = 'COMPLETA'
                              then case e.franja when 'MANANA' then 4.50 else 3.50 end
                              else t.horas_diarias end)::numeric(4,2) as horas_efectivas
from public.eventos_calendario e
join public.trabajadoras t on t.id = e.trabajadora_id;

revoke all on table public.v_eventos_calendario_horas from public, anon, authenticated, service_role;
grant select on public.v_eventos_calendario_horas to cf_trabajadores_web, cf_lectura;

commit;
