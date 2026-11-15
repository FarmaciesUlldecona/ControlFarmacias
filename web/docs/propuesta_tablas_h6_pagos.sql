-- =====================================================================================================================
-- PROPUESTA H6 — Marcas de pago de vencimientos y forma de pago por proveedor. NO APLICAR.
-- Borrador para el circuito (revisión y decisión de Pío). Ningún script ni la web lo ejecuta.
--
-- Excepción autorizada por Marc: la web podrá escribir SOLO en estas dos tablas nuevas (y su historial, por trigger),
-- con un rol propio. Nunca en facturas, facturas_vencimientos ni conciliación.
--
-- Referencias usadas (sin leer nada fuera de web/):
--   - web/app/server/contrato.ts: consulta `vencimientos` (facturas_vencimientos v.id, v.factura_id, v.fecha_vencimiento;
--     facturas f.farmacia), CTE `hab` (cf_configuracion: cfg.id and farmacia = any(cfg.farmacias_habilitadas)) y
--     OBJETOS_PERMITIDOS (lista cerrada de cf_lectura, DISENO 2BN);
--   - web/app/server/pagos/pagos.ts: modelo y reglas de H6 en FIXTURES;
--   - web/docs/propuesta_tablas_ta3.sql: mismas convenciones (cf.autor sin columna, anular en vez de DELETE).
-- Todo lo que dependa de migraciones existentes va marcado «A CONFIRMAR».
--
-- Principios:
--   - Solo farmacia PIO (y solo si sigue habilitada en cf_configuracion): RLS en las dos tablas.
--   - Autor SOLO por transacción: set_config('cf.autor', <autor>, true). SIN columna autor en las tablas. Sin cf.autor, la
--     escritura falla con AUTOR_AUSENTE (P0001). El historial (por trigger) guarda el autor de cada cambio.
--   - Nunca DELETE: se anula (anulada = true). Una fila vigente (no anulada) por clave. Una anulación no se deshace: se
--     crea una fila nueva.
--   - Grants: rol nuevo cf_pagos_web (SELECT, INSERT, UPDATE solo en estas tablas); cf_lectura (SELECT). Nadie DELETE.
-- =====================================================================================================================

-- ---------------------------------------------------------------------------------------------------------------------
-- DECISIONES PARA EL CIRCUITO
-- ---------------------------------------------------------------------------------------------------------------------
-- D1. Columna `farmacia` en las dos tablas (además de las pedidas), para la RLS y la unicidad por farmacia. En marcas se
--     comprueba que coincide con la de la factura del vencimiento. Confirmar.
-- D2. Columna `origen` en vencimientos_marcas_pago ('MANUAL' = «Marcar pagado»; 'DOMICILIADOS' = «Confirmar
--     domiciliados»: fecha = la de vencimiento, forma DOMICILIACION). La pantalla lo muestra en el historial. Confirmar o
--     quitar (sin ella, «domiciliado confirmado» no se distingue de un marcado manual por domiciliación).
-- D3. La fecha de pago no puede ser posterior a hoy (current_date del servidor de BD, zona A CONFIRMAR).
-- D4. Ampliar la lista cerrada de cf_lectura (DISENO 2BN / OBJETOS_PERMITIDOS) con vencimientos_marcas_pago,
--     proveedores_forma_pago y pagos_historial, para que la lista REAL muestre las marcas. Decisión de Pío.
-- D5. Credencial del rol cf_pagos_web: la crea y guarda Pío fuera de la web (como cf_trabajadores_web). La web nunca la
--     lee en esta fase (H6 es solo FIXTURES).
-- D6. PAGADO_BANCO queda reservado (sin columna ni lógica) hasta tener datos bancarios.

begin;

-- ---------------------------------------------------------------------------------------------------------------------
-- 0. Rol y funciones comunes
-- ---------------------------------------------------------------------------------------------------------------------

-- A CONFIRMAR: crear el rol sin contraseña aquí; Pío la fija aparte (alter role ... password ...), nunca en el repositorio.
create role cf_pagos_web nologin noinherit;
-- Para conectar: alter role cf_pagos_web login password '<la fija Pío>';  (fuera de este script)

-- PIO habilitada en cf_configuracion. Security definer para que la política no dependa del permiso sobre la tabla.
-- A CONFIRMAR: cf_configuracion es una fila única con `id` booleano y `farmacias_habilitadas text[]` (como lee contrato.ts).
create or replace function public.cf_h6_farmacia_habilitada(p_farmacia text) returns boolean
  language sql stable security definer set search_path = public as
$$ select p_farmacia = 'PIO' and exists (select 1 from public.cf_configuracion c where c.id and p_farmacia = any (c.farmacias_habilitadas)) $$;

-- Autor obligatorio por transacción (sin columna autor), nunca DELETE y anulación sin vuelta atrás.
create or replace function public.cf_h6_exigir_autor() returns trigger language plpgsql as
$$
begin
  if tg_op = 'DELETE' then
    raise exception 'BORRADO_NO_PERMITIDO' using errcode = 'P0001', detail = 'Se anula; nunca se borra';
  end if;
  if coalesce(current_setting('cf.autor', true), '') = '' then
    raise exception 'AUTOR_AUSENTE' using errcode = 'P0001';
  end if;
  if tg_op = 'UPDATE' then
    -- Solo se puede anular (false → true); el resto de columnas no cambia.
    if old.anulada or not new.anulada
       or (to_jsonb(new) - 'anulada' - 'updated_at') <> (to_jsonb(old) - 'anulada' - 'updated_at') then
      raise exception 'SOLO_ANULAR' using errcode = 'P0001', detail = 'Una fila solo se puede anular';
    end if;
    new.updated_at := now();
  end if;
  return new;
end
$$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 1. vencimientos_marcas_pago: marca de pago manual de un vencimiento (una vigente por vencimiento)
-- ---------------------------------------------------------------------------------------------------------------------

create table public.vencimientos_marcas_pago (
  id uuid primary key default gen_random_uuid(),
  farmacia text not null default 'PIO' check (farmacia = 'PIO'),
  -- A CONFIRMAR: facturas_vencimientos.id es uuid (la web lo lee como texto uuid).
  vencimiento_id uuid not null references public.facturas_vencimientos (id),
  fecha_pago date not null,
  forma text not null check (forma in ('DOMICILIACION', 'TRANSFERENCIA', 'EFECTIVO', 'COMPENSACION_ABONO')),
  origen text not null default 'MANUAL' check (origen in ('MANUAL', 'DOMICILIADOS')),
  anulada boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint marcas_domiciliados_forma check (origen <> 'DOMICILIADOS' or forma = 'DOMICILIACION')
);
create unique index vencimientos_marcas_pago_vigente on public.vencimientos_marcas_pago (farmacia, vencimiento_id) where not anulada;

-- El vencimiento es de una factura de esa farmacia; fecha de pago no futura; «domiciliados»: fecha = vencimiento.
create or replace function public.cf_h6_validar_marca() returns trigger
  language plpgsql security definer set search_path = public as
$$
declare
  v_farmacia text;
  v_fecha date;
begin
  if tg_op = 'UPDATE' then return new; end if; -- anular: ya lo controla cf_h6_exigir_autor
  select f.farmacia, v.fecha_vencimiento into v_farmacia, v_fecha
    from public.facturas_vencimientos v join public.facturas f on f.id = v.factura_id
   where v.id = new.vencimiento_id;
  if v_farmacia is null or v_farmacia <> new.farmacia then
    raise exception 'VENCIMIENTO_NO_ENCONTRADO' using errcode = 'P0001';
  end if;
  if new.fecha_pago > current_date then
    raise exception 'FECHA_FUTURA' using errcode = 'P0001';
  end if;
  if new.origen = 'DOMICILIADOS' and (v_fecha is null or new.fecha_pago <> v_fecha or v_fecha >= current_date) then
    raise exception 'NO_DOMICILIADO_PREVISTO' using errcode = 'P0001';
  end if;
  return new;
end
$$;

create trigger vencimientos_marcas_pago_autor before insert or update or delete on public.vencimientos_marcas_pago
  for each row execute function public.cf_h6_exigir_autor();
create trigger vencimientos_marcas_pago_validar before insert or update on public.vencimientos_marcas_pago
  for each row execute function public.cf_h6_validar_marca();

-- ---------------------------------------------------------------------------------------------------------------------
-- 2. proveedores_forma_pago: forma de pago por CIF (una vigente por CIF; sin fila = DOMICILIACION por defecto)
-- ---------------------------------------------------------------------------------------------------------------------

create table public.proveedores_forma_pago (
  id uuid primary key default gen_random_uuid(),
  farmacia text not null default 'PIO' check (farmacia = 'PIO'),
  -- CIF comparable, como el motor: mayúsculas y solo A-Z / 0-9 (regexp_replace(upper(..), '[^A-Z0-9]', '', 'g')).
  cif text not null check (cif ~ '^[A-Z0-9]{5,20}$'),
  forma text not null check (forma in ('DOMICILIACION', 'TRANSFERENCIA', 'EFECTIVO', 'COMPENSACION_ABONO')),
  anulada boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create unique index proveedores_forma_pago_vigente on public.proveedores_forma_pago (farmacia, cif) where not anulada;
-- Cambiar de forma = anular la vigente e insertar la nueva en la misma transacción (mismo cf.autor).
-- Volver a «por defecto» = anular la vigente.

create trigger proveedores_forma_pago_autor before insert or update or delete on public.proveedores_forma_pago
  for each row execute function public.cf_h6_exigir_autor();

-- ---------------------------------------------------------------------------------------------------------------------
-- 3. Historial por trigger (autor = cf.autor de la transacción)
-- ---------------------------------------------------------------------------------------------------------------------
-- A CONFIRMAR: si se prefiere reutilizar una tabla de historial existente (p. ej. la del módulo Trabajadores de la
-- migración 31), sustituir esta tabla y la función por la existente.

create table public.pagos_historial (
  id bigint generated always as identity primary key,
  tabla text not null check (tabla in ('vencimientos_marcas_pago', 'proveedores_forma_pago')),
  fila_id uuid not null,
  farmacia text not null,
  accion text not null check (accion in ('ALTA', 'ANULACION')),
  autor text not null,
  datos jsonb not null,
  created_at timestamptz not null default now()
);

create or replace function public.cf_h6_historial() returns trigger
  language plpgsql security definer set search_path = public as
$$
begin
  insert into public.pagos_historial (tabla, fila_id, farmacia, accion, autor, datos)
  values (tg_table_name, new.id, new.farmacia, case when tg_op = 'INSERT' then 'ALTA' else 'ANULACION' end,
          current_setting('cf.autor', true), to_jsonb(new));
  return new;
end
$$;
create trigger vencimientos_marcas_pago_historial after insert or update on public.vencimientos_marcas_pago
  for each row execute function public.cf_h6_historial();
create trigger proveedores_forma_pago_historial after insert or update on public.proveedores_forma_pago
  for each row execute function public.cf_h6_historial();
-- El historial no se toca nunca a mano.
create or replace function public.cf_h6_historial_inmutable() returns trigger language plpgsql as
$$ begin raise exception 'HISTORIAL_INMUTABLE' using errcode = 'P0001'; end $$;
create trigger pagos_historial_inmutable before update or delete on public.pagos_historial
  for each row execute function public.cf_h6_historial_inmutable();

-- ---------------------------------------------------------------------------------------------------------------------
-- 4. RLS: solo farmacia PIO (y habilitada)
-- ---------------------------------------------------------------------------------------------------------------------

alter table public.vencimientos_marcas_pago enable row level security;
alter table public.proveedores_forma_pago enable row level security;
alter table public.pagos_historial enable row level security;

create policy marcas_select on public.vencimientos_marcas_pago for select to cf_pagos_web, cf_lectura
  using (public.cf_h6_farmacia_habilitada(farmacia));
create policy marcas_insert on public.vencimientos_marcas_pago for insert to cf_pagos_web
  with check (public.cf_h6_farmacia_habilitada(farmacia));
create policy marcas_update on public.vencimientos_marcas_pago for update to cf_pagos_web
  using (public.cf_h6_farmacia_habilitada(farmacia)) with check (public.cf_h6_farmacia_habilitada(farmacia));

create policy formas_select on public.proveedores_forma_pago for select to cf_pagos_web, cf_lectura
  using (public.cf_h6_farmacia_habilitada(farmacia));
create policy formas_insert on public.proveedores_forma_pago for insert to cf_pagos_web
  with check (public.cf_h6_farmacia_habilitada(farmacia));
create policy formas_update on public.proveedores_forma_pago for update to cf_pagos_web
  using (public.cf_h6_farmacia_habilitada(farmacia)) with check (public.cf_h6_farmacia_habilitada(farmacia));

create policy historial_select on public.pagos_historial for select to cf_pagos_web, cf_lectura
  using (public.cf_h6_farmacia_habilitada(farmacia));

-- ---------------------------------------------------------------------------------------------------------------------
-- 5. Grants (nunca DELETE; el rol nuevo no ve ni toca nada más)
-- ---------------------------------------------------------------------------------------------------------------------

revoke all on public.vencimientos_marcas_pago, public.proveedores_forma_pago, public.pagos_historial from public;
grant usage on schema public to cf_pagos_web;
grant select, insert, update on public.vencimientos_marcas_pago, public.proveedores_forma_pago to cf_pagos_web;
grant select on public.pagos_historial to cf_pagos_web;
grant select on public.vencimientos_marcas_pago, public.proveedores_forma_pago, public.pagos_historial to cf_lectura;
grant execute on function public.cf_h6_farmacia_habilitada(text) to cf_pagos_web, cf_lectura;
-- Sin grants sobre facturas, facturas_vencimientos ni conciliaciones para cf_pagos_web: la validación del vencimiento
-- la hace cf_h6_validar_marca (security definer) y la lista se lee con cf_lectura.

commit;

-- =====================================================================================================================
-- ROLLBACK (deshace esta propuesta; solo si se aplicó y con preflight y OK de Pío)
-- =====================================================================================================================
-- begin;
-- drop table if exists public.pagos_historial;
-- drop table if exists public.vencimientos_marcas_pago;
-- drop table if exists public.proveedores_forma_pago;
-- drop function if exists public.cf_h6_historial_inmutable();
-- drop function if exists public.cf_h6_historial();
-- drop function if exists public.cf_h6_validar_marca();
-- drop function if exists public.cf_h6_exigir_autor();
-- drop function if exists public.cf_h6_farmacia_habilitada(text);
-- revoke usage on schema public from cf_pagos_web;
-- drop role if exists cf_pagos_web;
-- commit;
