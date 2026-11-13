-- Migracion 32 (Hito AUTO-A): tabla de resumen nocturno de la automatizacion Alliance.
-- Diseno: pruebas/auditoria_auto_alliance/DISENO.md (decision D4 de Pio, 2026-11-12).
-- - Una fila por noche (fecha local, clave primaria): es tambien el guard de "una sola ejecucion por noche".
-- - La escribe solo el orquestador nocturno con la credencial del sistema: SELECT, INSERT y UPDATE explicitos, sin
--   DELETE, TRUNCATE, REFERENCES ni TRIGGER (no depende de los privilegios por defecto de Supabase).
-- - Lectura: cf_lectura (SELECT y politica RLS). anon, authenticated y PUBLIC: ningun privilegio.
-- - Solo anade objetos: ninguna tabla, funcion, politica ni privilegio existente cambia.
-- Idempotente. Requiere la 31.
begin;

do $$
begin
    if to_regclass('public.cf_modulos_farmacias') is null then
        raise exception 'MIGRACION_31_AUSENTE';
    end if;
end;
$$;

create table if not exists public.cf_noches_automaticas (
    fecha date primary key,
    modo text not null check (modo in ('SOMBRA', 'REAL')),
    inicio timestamptz not null default now(),
    fin timestamptz,
    resultado text not null check (resultado in ('EN_CURSO', 'NOCHE_OK', 'FIN_LIMITE', 'PARADA')),
    motivo text check (motivo is null or char_length(motivo) <= 2000),
    commit_codigo text check (commit_codigo is null or commit_codigo ~ '^[0-9a-f]{40}$'),
    limites jsonb not null default '{}'::jsonb,
    documentos_reclamados integer not null default 0 check (documentos_reclamados >= 0),
    alliance_persistidos integer not null default 0 check (alliance_persistidos >= 0),
    facturas_creadas integer not null default 0 check (facturas_creadas >= 0),
    no_soportados integer not null default 0 check (no_soportados >= 0),
    defectos integer not null default 0 check (defectos >= 0),
    conciliadas integer not null default 0 check (conciliadas >= 0),
    para_revisar jsonb not null default '[]'::jsonb check (jsonb_typeof(para_revisar) = 'array'),
    cola_restante jsonb not null default '{}'::jsonb check (jsonb_typeof(cola_restante) = 'object'),
    informe_sha256 text check (informe_sha256 is null or informe_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz not null default now(),
    constraint cf_noches_automaticas_fin check (
        (resultado = 'EN_CURSO' and fin is null) or (resultado <> 'EN_CURSO' and fin is not null and fin >= inicio))
);
comment on table public.cf_noches_automaticas is
    'Resumen de cada noche de la automatizacion Alliance (AUTO-ALLIANCE). Una fila por fecha local; la escribe el '
    'orquestador nocturno; la web la lee con cf_lectura.';

-- Supabase concede por defecto privilegios sobre las tablas nuevas de public: se retiran todos. El rol del sistema
-- (escritura del orquestador) recibe explicitamente SELECT, INSERT y UPDATE; sin DELETE, TRUNCATE, REFERENCES ni
-- TRIGGER (AUTORIZACION EXPRESA DE PIO, 2026-11-12: el rol del sistema se nombra SOLO aqui y en el rollback).
revoke all on table public.cf_noches_automaticas from public, anon, authenticated, service_role;
grant select, insert, update on public.cf_noches_automaticas to service_role;
grant select on public.cf_noches_automaticas to cf_lectura;

alter table public.cf_noches_automaticas enable row level security;
drop policy if exists cf_noches_automaticas_lectura_select on public.cf_noches_automaticas;
create policy cf_noches_automaticas_lectura_select on public.cf_noches_automaticas
    for select to cf_lectura using (true);

commit;
