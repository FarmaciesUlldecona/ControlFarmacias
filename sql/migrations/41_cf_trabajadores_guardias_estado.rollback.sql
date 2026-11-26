-- Rollback de la migracion 41 (Hito TA4-2): devuelve el esquema exacto de la 40.
-- Retira la columna estado (y sus checks) de guardias_semana y guardias_festivo, restaura los checks de persona
-- obligatoria en PIO y RITA (guardias_semana_guardia_obligatoria, guardias_festivo_persona_obligatoria) y los
-- comentarios de la 34.
-- Falla cerrado, sin cambiar nada, si alguna fila (anulada o no) de PIO o RITA tiene la persona por asignar
-- (ROLLBACK_41_GUARDIAS_POR_ASIGNAR) o alguna esta PLANIFICADO (ROLLBACK_41_GUARDIAS_PLANIFICADAS): el esquema 40 no
-- puede guardarlas sin perder informacion. Solo con confirmacion de Pio. Facturas, albaranes, conciliacion y Cashflow
-- sin cambios. No nombra el rol del sistema.
begin;

do $$
begin
    if exists (select 1 from public.guardias_semana where farmacia <> 'OTRA' and persona_guardia_id is null)
       or exists (select 1 from public.guardias_festivo where farmacia <> 'OTRA' and persona_id is null) then
        raise exception 'ROLLBACK_41_GUARDIAS_POR_ASIGNAR';
    end if;
    if exists (select 1 from information_schema.columns where table_schema = 'public'
               and table_name = 'guardias_semana' and column_name = 'estado') then
        if exists (select 1 from public.guardias_semana where (to_jsonb(guardias_semana) ->> 'estado') = 'PLANIFICADO')
        then
            raise exception 'ROLLBACK_41_GUARDIAS_PLANIFICADAS';
        end if;
    end if;
    if exists (select 1 from information_schema.columns where table_schema = 'public'
               and table_name = 'guardias_festivo' and column_name = 'estado') then
        if exists (select 1 from public.guardias_festivo
                   where (to_jsonb(guardias_festivo) ->> 'estado') = 'PLANIFICADO') then
            raise exception 'ROLLBACK_41_GUARDIAS_PLANIFICADAS';
        end if;
    end if;
end;
$$;

alter table public.guardias_semana drop column if exists estado;
alter table public.guardias_festivo drop column if exists estado;

alter table public.guardias_semana drop constraint if exists guardias_semana_guardia_obligatoria;
alter table public.guardias_semana add constraint guardias_semana_guardia_obligatoria
    check (farmacia = 'OTRA' or persona_guardia_id is not null);
alter table public.guardias_festivo drop constraint if exists guardias_festivo_persona_obligatoria;
alter table public.guardias_festivo add constraint guardias_festivo_persona_obligatoria
    check (farmacia = 'OTRA' or persona_id is not null);

comment on table public.guardias_semana is
    'Guardia semanal (lunes a domingo) de PIO, RITA u OTRA. Se anula, no se borra; historial por trigger.';
comment on table public.guardias_festivo is
    'Guardia de un festivo comun (PIO, RITA u OTRA). Se anula, no se borra; historial por trigger.';

commit;
