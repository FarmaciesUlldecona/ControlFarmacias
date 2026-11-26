-- Migracion 41 (Hito TA4-2): guardias por asignar y estado de la guardia en el modulo de Trabajadores. Peticion de la
-- web TA4-2, DECISION DE PIO del 2026-11-26. Diseno: pruebas/auditoria_trab/DISENO_41.md.
-- 1. guardias_semana y guardias_festivo: OTRA sigue siempre sin persona (guardias_semana_otra_sin_personas y
--    guardias_festivo_otra_sin_persona no cambian); PIO y RITA admiten la persona nula («por asignar»). Se retiran los
--    checks guardias_semana_guardia_obligatoria y guardias_festivo_persona_obligatoria (la peticion los llama
--    guardias_*_personas_check). Los triggers de la 34 ya comprueban la persona solo si no es nula.
-- 2. Columna estado en las dos: PLANIFICADO o CONFIRMADO, not null. Las filas existentes quedan CONFIRMADO (el default
--    constante de ADD COLUMN: no se reescribe ninguna fila, no cambia updated_at ni se escribe historial). CONFIRMADO
--    sin persona se admite en PIO y RITA (se confirma la farmacia antes que la persona).
-- 3. Sin cambios: anular y nunca borrar (sin DELETE), autor por transaccion (cf.autor), historial por trigger
--    (cf_trab_historial: guarda la fila entera, con estado), RLS por farmacia del modulo y privilegios. Los privilegios
--    de la 34 son de tabla: cf_trabajadores_web escribe la columna nueva y cf_lectura la lee sin privilegios nuevos.
-- No crea tablas ni funciones: no hay privilegios por defecto que retirar (no nombra el rol del sistema). Solo objetos de
-- Trabajadores: facturas, albaranes, normalizacion, conciliacion y Cashflow no cambian. Idempotente. Requiere la 40.
begin;

do $$
begin
    if to_regclass('public.cf_cashflow_apuntes') is null then
        raise exception 'MIGRACION_40_AUSENTE';
    end if;
    if to_regclass('public.guardias_semana') is null or to_regclass('public.guardias_festivo') is null then
        raise exception 'MIGRACION_34_AUSENTE';
    end if;
end;
$$;

-- --------------------------------------------------------------------------- 1. persona por asignar en PIO y RITA

alter table public.guardias_semana drop constraint if exists guardias_semana_guardia_obligatoria;
alter table public.guardias_festivo drop constraint if exists guardias_festivo_persona_obligatoria;

-- --------------------------------------------------------------------------- 2. estado

alter table public.guardias_semana add column if not exists estado text not null default 'CONFIRMADO';
alter table public.guardias_festivo add column if not exists estado text not null default 'CONFIRMADO';

alter table public.guardias_semana drop constraint if exists guardias_semana_estado;
alter table public.guardias_semana add constraint guardias_semana_estado
    check (estado in ('PLANIFICADO', 'CONFIRMADO'));
alter table public.guardias_festivo drop constraint if exists guardias_festivo_estado;
alter table public.guardias_festivo add constraint guardias_festivo_estado
    check (estado in ('PLANIFICADO', 'CONFIRMADO'));

comment on column public.guardias_semana.estado is
    'PLANIFICADO o CONFIRMADO (TA4-2). CONFIRMADO sin persona se admite en PIO y RITA: se confirma la farmacia antes '
    'que la persona.';
comment on column public.guardias_festivo.estado is
    'PLANIFICADO o CONFIRMADO (TA4-2). CONFIRMADO sin persona se admite en PIO y RITA: se confirma la farmacia antes '
    'que la persona.';

comment on table public.guardias_semana is
    'Guardia semanal (lunes a domingo) de PIO, RITA u OTRA; en PIO y RITA la persona puede estar por asignar (nula); '
    'estado PLANIFICADO o CONFIRMADO. Se anula, no se borra; historial por trigger.';
comment on table public.guardias_festivo is
    'Guardia de un festivo comun (PIO, RITA u OTRA); en PIO y RITA la persona puede estar por asignar (nula); estado '
    'PLANIFICADO o CONFIRMADO. Se anula, no se borra; historial por trigger.';

commit;
