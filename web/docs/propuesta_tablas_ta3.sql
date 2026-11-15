-- =====================================================================================================================
-- PROPUESTA TA3 — Guardias y festivos de Trabajadores. NO APLICAR.
-- Borrador para el circuito (revisión y decisión de Pío). Ningún script ni la web lo ejecuta.
--
-- Referencias usadas (sin leer la migración 31 fuera de web/, por decisión de Pío):
--   - web/app/server/rrhh/contrato.ts:224-242 (tipos GuardiaFarmacia y Festivo de la migración 31);
--   - web/app/server/rrhh/adaptador_real.ts (consultas guardias/festivos, cf_modulos_farmacias, cf.autor);
--   - web/app/server/rrhh/guardias.ts (modelo y reglas de TA3 en FIXTURES).
-- Todo lo que dependa de la migración 31 (nombre del trigger de historial, checks exactos) va marcado «A CONFIRMAR».
--
-- Principios (los del módulo):
--   - Farmacias del módulo: cf_modulos_farmacias (modulo = 'TRABAJADORES') = {PIO, RITA}. OTRA = la tercera farmacia de
--     Ulldecona (ajena): solo ocupa el turno, nunca lleva personas.
--   - Autor SOLO por transacción: set_config('cf.autor', <autor>, true). SIN columna autor. Sin cf.autor, la escritura
--     falla con AUTOR_AUSENTE (P0001), como en el resto del módulo.
--   - Nunca DELETE: se anula (anulada / anulado = true). La unicidad solo cuenta las filas no anuladas.
--   - Grants: cf_trabajadores_web (SELECT, INSERT, UPDATE); cf_lectura (SELECT). Nadie DELETE.
-- =====================================================================================================================

-- ---------------------------------------------------------------------------------------------------------------------
-- DECISIONES PARA EL CIRCUITO
-- ---------------------------------------------------------------------------------------------------------------------
-- D1. public.festivos (migración 31: id, fecha, ambito NACIONAL|AUTONOMICO|LOCAL, farmacia null|PIO|RITA, descripcion,
--     anulado). TA3 necesita: un festivo por día, común a las 3 farmacias del pueblo, con nombre (máx. 60), alta manual
--     y baja = anular.
--     Propuesta: REUTILIZAR festivos, si el circuito acepta estos ajustes (bloque OPCIÓN A):
--       - los festivos de TA3 llevan farmacia = null (comunes) y descripcion = nombre;
--       - ambito pasa a ser opcional para TA3 (por defecto 'LOCAL'); A CONFIRMAR: si el check actual exige farmacia
--         cuando ambito = 'LOCAL', hay que relajarlo (un festivo local de Ulldecona es común a las 3 farmacias);
--       - nuevo check de longitud (1–60) y unicidad de fecha entre los no anulados y comunes.
--     Si no se acepta tocar la tabla, SUSTITUIRLA por public.festivos_ulldecona (bloque OPCIÓN B, comentado) y dejar
--     festivos de solo lectura.
-- D2. public.guardias_farmacia (migración 31: id, farmacia PIO|RITA, fecha, nota, anulada). Es un día de guardia por
--     farmacia: no admite OTRA, ni persona, ni apoyo, ni la semana de lunes a domingo. NO se reutiliza.
--     Propuesta: dejarla de solo lectura (sin pantalla ni escrituras nuevas); si check:real da 0 filas, retirarla en una
--     migración posterior; si tiene filas, decidir antes si se pasan a guardias_semana (no hay persona: quedarían sin
--     persona, lo que la regla de PIO/RITA no admite).
-- D3. Un festivo en sábado o domingo de una semana de guardia sustituye ese día (cuenta la guardia del festivo, no la
--     semanal). Es el criterio provisional de FIXTURES (guardias.ts): confirmar.
-- D4. TA3 no crea filas en eventos_calendario (TURNO_GUARDIA / LOCALIZADA / FESTIVO): las horas fuera de cómputo salen
--     de estas tablas y del horario fijo (HORARIO_GUARDIA). Confirmar.

begin;

-- ---------------------------------------------------------------------------------------------------------------------
-- 0. Funciones comunes
-- ---------------------------------------------------------------------------------------------------------------------

-- Farmacias del módulo (PIO, RITA). Security definer para que la política no dependa del permiso sobre la tabla.
create or replace function public.cf_ta3_farmacias_modulo() returns text[]
  language sql stable security definer set search_path = public as
$$ select coalesce((select farmacias from public.cf_modulos_farmacias where modulo = 'TRABAJADORES'), '{}'::text[]) $$;

-- Autor obligatorio por transacción (sin columna autor) y nunca DELETE.
create or replace function public.cf_ta3_exigir_autor() returns trigger language plpgsql as
$$
begin
  if tg_op = 'DELETE' then
    raise exception 'BORRADO_NO_PERMITIDO' using errcode = 'P0001', detail = 'Se anula; nunca se borra';
  end if;
  if coalesce(current_setting('cf.autor', true), '') = '' then
    raise exception 'AUTOR_AUSENTE' using errcode = 'P0001';
  end if;
  return new;
end
$$;

-- Persona válida para un servicio: ficha sin anular, de esa farmacia y de alta todos esos días (titular permitido).
create or replace function public.cf_ta3_persona_valida(p_persona uuid, p_farmacia text, p_desde date, p_hasta date) returns boolean
  language sql stable as
$$
  select exists (
    select 1 from public.trabajadoras t
    where t.id = p_persona and not t.anulada and t.farmacia = p_farmacia
      and t.fecha_alta <= p_desde and (t.fecha_baja is null or t.fecha_baja >= p_hasta)
  )
$$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 1. Festivos (D1)
-- ---------------------------------------------------------------------------------------------------------------------

-- OPCIÓN A (propuesta): reutilizar public.festivos.
-- A CONFIRMAR el nombre del check actual de ambito/farmacia antes de relajarlo.
-- alter table public.festivos drop constraint <check_local_exige_farmacia>;
alter table public.festivos alter column ambito set default 'LOCAL';
alter table public.festivos add constraint festivos_descripcion_largo check (char_length(btrim(descripcion)) between 1 and 60) not valid;
create unique index festivos_fecha_comun_unico on public.festivos (fecha) where not anulado and farmacia is null;
create trigger festivos_ta3_autor before insert or update or delete on public.festivos
  for each row execute function public.cf_ta3_exigir_autor();

-- OPCIÓN B (si no se acepta tocar festivos): tabla nueva; festivos queda de solo lectura.
-- create table public.festivos_ulldecona (
--   id uuid primary key default gen_random_uuid(),
--   fecha date not null,
--   nombre text not null check (char_length(btrim(nombre)) between 1 and 60 and nombre !~ '[<>[:cntrl:]]'),
--   anulado boolean not null default false,
--   created_at timestamptz not null default now(),
--   updated_at timestamptz not null default now()
-- );
-- create unique index festivos_ulldecona_fecha_unico on public.festivos_ulldecona (fecha) where not anulado;
-- (con la opción B, en guardias_festivo y en las funciones de abajo se usa festivos_ulldecona en lugar de festivos)

-- ---------------------------------------------------------------------------------------------------------------------
-- 2. guardias_semana: una por semana (lunes a domingo)
-- ---------------------------------------------------------------------------------------------------------------------

create table public.guardias_semana (
  id uuid primary key default gen_random_uuid(),
  lunes date not null check (extract(isodow from lunes) = 1),
  farmacia text not null check (farmacia in ('PIO', 'RITA', 'OTRA')),
  persona_guardia_id uuid references public.trabajadoras (id),
  persona_apoyo_sabado_id uuid references public.trabajadoras (id),
  anulada boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- OTRA sin personas; PIO/RITA con persona de guardia; apoyo distinto de la guardia.
  constraint guardias_semana_otra_sin_personas check (farmacia <> 'OTRA' or (persona_guardia_id is null and persona_apoyo_sabado_id is null)),
  constraint guardias_semana_guardia_obligatoria check (farmacia = 'OTRA' or persona_guardia_id is not null),
  constraint guardias_semana_apoyo_distinto check (persona_apoyo_sabado_id is null or persona_apoyo_sabado_id <> persona_guardia_id)
);
create unique index guardias_semana_lunes_unico on public.guardias_semana (lunes) where not anulada;

create or replace function public.cf_ta3_validar_guardia_semana() returns trigger language plpgsql as
$$
begin
  if new.anulada or new.farmacia = 'OTRA' then return new; end if;
  -- Guardia: de alta sábado y domingo; apoyo: de alta el sábado.
  if not public.cf_ta3_persona_valida(new.persona_guardia_id, new.farmacia, new.lunes + 5, new.lunes + 6) then
    raise exception 'PERSONA_NO_VALIDA' using errcode = 'P0001';
  end if;
  if new.persona_apoyo_sabado_id is not null
     and not public.cf_ta3_persona_valida(new.persona_apoyo_sabado_id, new.farmacia, new.lunes + 5, new.lunes + 5) then
    raise exception 'PERSONA_NO_VALIDA' using errcode = 'P0001';
  end if;
  new.updated_at := now();
  return new;
end
$$;
create trigger guardias_semana_autor before insert or update or delete on public.guardias_semana
  for each row execute function public.cf_ta3_exigir_autor();
create trigger guardias_semana_validar before insert or update on public.guardias_semana
  for each row execute function public.cf_ta3_validar_guardia_semana();

-- ---------------------------------------------------------------------------------------------------------------------
-- 3. guardias_festivo: la guardia de un festivo (rotación propia)
-- ---------------------------------------------------------------------------------------------------------------------

create table public.guardias_festivo (
  id uuid primary key default gen_random_uuid(),
  fecha date not null,
  farmacia text not null check (farmacia in ('PIO', 'RITA', 'OTRA')),
  persona_id uuid references public.trabajadoras (id),
  anulada boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint guardias_festivo_otra_sin_persona check (farmacia <> 'OTRA' or persona_id is null),
  constraint guardias_festivo_persona_obligatoria check (farmacia = 'OTRA' or persona_id is not null)
);
create unique index guardias_festivo_fecha_unico on public.guardias_festivo (fecha) where not anulada;

-- La fecha debe ser un festivo vigente; la persona, de esa farmacia y de alta ese día. La persona por defecto (la de
-- guardia de esa semana si es la misma farmacia) la propone la web; la tabla guarda siempre la persona elegida.
create or replace function public.cf_ta3_validar_guardia_festivo() returns trigger language plpgsql as
$$
begin
  if new.anulada then return new; end if;
  if not exists (select 1 from public.festivos f where f.fecha = new.fecha and not f.anulado and f.farmacia is null) then
    raise exception 'NO_ES_FESTIVO' using errcode = 'P0001';
  end if;
  if new.farmacia <> 'OTRA' and not public.cf_ta3_persona_valida(new.persona_id, new.farmacia, new.fecha, new.fecha) then
    raise exception 'PERSONA_NO_VALIDA' using errcode = 'P0001';
  end if;
  new.updated_at := now();
  return new;
end
$$;
create trigger guardias_festivo_autor before insert or update or delete on public.guardias_festivo
  for each row execute function public.cf_ta3_exigir_autor();
create trigger guardias_festivo_validar before insert or update on public.guardias_festivo
  for each row execute function public.cf_ta3_validar_guardia_festivo();

-- Baja de un festivo: anula también su guardia (misma transacción, mismo cf.autor).
create or replace function public.cf_ta3_anular_guardia_de_festivo() returns trigger language plpgsql as
$$
begin
  if new.anulado and not old.anulado then
    update public.guardias_festivo set anulada = true where fecha = old.fecha and not anulada;
  end if;
  return new;
end
$$;
create trigger festivos_ta3_anular_guardia after update of anulado on public.festivos
  for each row execute function public.cf_ta3_anular_guardia_de_festivo();

-- Historial: A CONFIRMAR el nombre de la función de trabajadores_historial de la migración 31 (la misma que usan
-- trabajadoras y eventos_calendario) y engancharla a guardias_semana, guardias_festivo y festivos:
-- create trigger guardias_semana_historial after insert or update on public.guardias_semana
--   for each row execute function public.<funcion_historial_migracion_31>();
-- create trigger guardias_festivo_historial after insert or update on public.guardias_festivo
--   for each row execute function public.<funcion_historial_migracion_31>();

-- ---------------------------------------------------------------------------------------------------------------------
-- 4. RLS por farmacia del módulo
-- ---------------------------------------------------------------------------------------------------------------------
-- Semanas y guardias de festivo: filas de PIO/RITA si la farmacia está en el módulo; OTRA, visible y editable (es el
-- turno compartido del pueblo, sin personas). Festivos comunes (farmacia null): visibles y editables por el módulo.

alter table public.guardias_semana enable row level security;
alter table public.guardias_festivo enable row level security;

create policy guardias_semana_select on public.guardias_semana for select to cf_trabajadores_web, cf_lectura
  using (farmacia = 'OTRA' or farmacia = any (public.cf_ta3_farmacias_modulo()));
create policy guardias_semana_insert on public.guardias_semana for insert to cf_trabajadores_web
  with check (farmacia = 'OTRA' or farmacia = any (public.cf_ta3_farmacias_modulo()));
create policy guardias_semana_update on public.guardias_semana for update to cf_trabajadores_web
  using (farmacia = 'OTRA' or farmacia = any (public.cf_ta3_farmacias_modulo()))
  with check (farmacia = 'OTRA' or farmacia = any (public.cf_ta3_farmacias_modulo()));

create policy guardias_festivo_select on public.guardias_festivo for select to cf_trabajadores_web, cf_lectura
  using (farmacia = 'OTRA' or farmacia = any (public.cf_ta3_farmacias_modulo()));
create policy guardias_festivo_insert on public.guardias_festivo for insert to cf_trabajadores_web
  with check (farmacia = 'OTRA' or farmacia = any (public.cf_ta3_farmacias_modulo()));
create policy guardias_festivo_update on public.guardias_festivo for update to cf_trabajadores_web
  using (farmacia = 'OTRA' or farmacia = any (public.cf_ta3_farmacias_modulo()))
  with check (farmacia = 'OTRA' or farmacia = any (public.cf_ta3_farmacias_modulo()));

-- Festivos (opción A): A CONFIRMAR si la migración 31 ya tiene RLS en festivos; si no, estas políticas.
alter table public.festivos enable row level security;
create policy festivos_ta3_select on public.festivos for select to cf_trabajadores_web, cf_lectura
  using (farmacia is null or farmacia = any (public.cf_ta3_farmacias_modulo()));
create policy festivos_ta3_insert on public.festivos for insert to cf_trabajadores_web
  with check (farmacia is null or farmacia = any (public.cf_ta3_farmacias_modulo()));
create policy festivos_ta3_update on public.festivos for update to cf_trabajadores_web
  using (farmacia is null or farmacia = any (public.cf_ta3_farmacias_modulo()))
  with check (farmacia is null or farmacia = any (public.cf_ta3_farmacias_modulo()));

-- ---------------------------------------------------------------------------------------------------------------------
-- 5. Grants (nunca DELETE)
-- ---------------------------------------------------------------------------------------------------------------------

revoke all on public.guardias_semana, public.guardias_festivo from public;
grant select, insert, update on public.guardias_semana, public.guardias_festivo, public.festivos to cf_trabajadores_web;
grant select on public.guardias_semana, public.guardias_festivo, public.festivos to cf_lectura;
revoke delete on public.festivos from cf_trabajadores_web;
grant execute on function public.cf_ta3_farmacias_modulo() to cf_trabajadores_web, cf_lectura;

commit;

-- =====================================================================================================================
-- ROLLBACK (deshace esta propuesta; solo si se aplicó y con preflight y OK de Pío)
-- =====================================================================================================================
-- begin;
-- drop trigger if exists festivos_ta3_anular_guardia on public.festivos;
-- drop trigger if exists festivos_ta3_autor on public.festivos;
-- drop policy if exists festivos_ta3_select on public.festivos;
-- drop policy if exists festivos_ta3_insert on public.festivos;
-- drop policy if exists festivos_ta3_update on public.festivos;
-- -- (si la migración 31 no tenía RLS en festivos) alter table public.festivos disable row level security;
-- drop index if exists public.festivos_fecha_comun_unico;
-- alter table public.festivos drop constraint if exists festivos_descripcion_largo;
-- alter table public.festivos alter column ambito drop default;
-- -- (restaurar el check de ambito/farmacia si se relajó: definición de la migración 31)
-- drop table if exists public.guardias_festivo;
-- drop table if exists public.guardias_semana;
-- drop function if exists public.cf_ta3_anular_guardia_de_festivo();
-- drop function if exists public.cf_ta3_validar_guardia_festivo();
-- drop function if exists public.cf_ta3_validar_guardia_semana();
-- drop function if exists public.cf_ta3_persona_valida(uuid, text, date, date);
-- drop function if exists public.cf_ta3_exigir_autor();
-- drop function if exists public.cf_ta3_farmacias_modulo();
-- -- (opción B) drop table if exists public.festivos_ulldecona;
-- commit;
