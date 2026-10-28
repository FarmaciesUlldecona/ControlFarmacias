"""Hito 2BF: genera de forma determinista la migracion 23 y su rollback.

Uso: python -B pruebas/auditoria_2bf/generar_migracion_23.py

- ``cf_resincronizar_albaran`` de la 23 sale del texto EXACTO de la migracion 22 con la
  comprobacion de revisiones identicas limitada a las pendientes (reemplazos comprobados unicos).
- El rollback reinstala el texto exacto de la 22 y elimina los objetos nuevos: rollback ==
  estado 22 (se pierden aprobaciones y aplicaciones; los valores aplicados en albaranes quedan).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql/migrations"
M22 = MIG / "22_cf_resincronizacion_albaranes.sql"
DESTINO = MIG / "23_cf_aprobaciones_albaranes.sql"
ROLLBACK = MIG / "23_cf_aprobaciones_albaranes.rollback.sql"


def funcion(path: Path, nombre: str) -> str:
    texto = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    inicio = texto.index(f"create or replace function public.{nombre}(")
    fin = texto.index("$$;\n", texto.index("as $$", inicio) + 5) + 4
    return texto[inicio:fin]


def _reemplazar(texto: str, viejo: str, nuevo: str) -> str:
    assert texto.count(viejo) == 1, viejo
    return texto.replace(viejo, nuevo)


def resincronizar_23() -> str:
    f = funcion(M22, "cf_resincronizar_albaran")
    # Revision de identidad (indentacion de 4 niveles) y revision por reserva (5 niveles).
    for sangria in (" " * 16, " " * 20):
        cierre = " " * (len(sangria) - 4) + ") then\n"
        ancla = f"{sangria}   and c.valor_nuevo is not distinct from v_item->>'nuevo'\n{cierre}"
        f = _reemplazar(f, ancla, f"{sangria}   and c.valor_nuevo is not distinct from v_item->>'nuevo'\n"
                                  f"{sangria}   and public.cf_revision_albaran_pendiente(c.id)\n{cierre}")
    return f


CABECERA = """-- Migracion 23 (Hito 2BF): resolucion de revisiones de albaranes con aprobacion de Pio.
-- Generada por pruebas/auditoria_2bf/generar_migracion_23.py a partir del texto exacto
-- de la 22 (cf_resincronizar_albaran). Aprobaciones append-only (quien, cuando, IdContador,
-- cambio exacto), aplicacion solo si el cambio de identidad detectado coincide con lo aprobado
-- y el albaran no esta reservado (R15), con historial; la resincronizacion no repite una
-- revision identica pendiente. No modifica filas existentes. Idempotente. Requiere la 22.
begin;

do $$
begin
    if to_regclass('public.albaranes_cambios') is null then
        raise exception 'MIGRACION_22_AUSENTE';
    end if;
end;
$$;

-- Aprobaciones de Pio de un cambio de identidad (append-only).
create table if not exists public.albaranes_aprobaciones (
    id bigint generated always as identity primary key,
    farmacia text not null,
    id_contador bigint not null,
    motivo text not null,
    cambio jsonb not null,
    aprobado_por text not null,
    aprobado_at timestamptz not null,
    referencia text not null,
    registrado_por text not null,
    registrado_at timestamptz not null default now(),
    constraint albaranes_aprobaciones_motivo_check check (motivo = 'CAMBIO_IDENTIDAD'),
    constraint albaranes_aprobaciones_aprobado_por_check check (aprobado_por = 'Pio'),
    constraint albaranes_aprobaciones_cambio_check
        check (jsonb_typeof(cambio) = 'array' and jsonb_array_length(cambio) between 1 and 2),
    constraint albaranes_aprobaciones_unica unique (farmacia, id_contador, cambio)
);
alter table public.albaranes_aprobaciones enable row level security;
revoke all on table public.albaranes_aprobaciones from public, anon, authenticated, service_role;
grant select on table public.albaranes_aprobaciones to service_role;
revoke all on sequence public.albaranes_aprobaciones_id_seq from public, anon, authenticated, service_role;
comment on table public.albaranes_aprobaciones is
    '2BF: aprobaciones de Pio de cambios de identidad de albaranes. Escritura solo via cf_registrar_aprobacion_albaran.';

-- Aplicacion de una aprobacion (como maximo una vez por aprobacion, append-only).
create table if not exists public.albaranes_aprobaciones_aplicadas (
    aprobacion_id bigint primary key references public.albaranes_aprobaciones (id),
    farmacia text not null,
    id_contador bigint not null,
    aplicada_at timestamptz not null default now(),
    ejecucion_id text not null,
    valores_anteriores jsonb not null,
    valores_nuevos jsonb not null,
    revisiones_resueltas bigint[] not null
);
create index if not exists albaranes_aprobaciones_aplicadas_albaran_idx
    on public.albaranes_aprobaciones_aplicadas (farmacia, id_contador);
alter table public.albaranes_aprobaciones_aplicadas enable row level security;
revoke all on table public.albaranes_aprobaciones_aplicadas from public, anon, authenticated, service_role;
grant select on table public.albaranes_aprobaciones_aplicadas to service_role;
comment on table public.albaranes_aprobaciones_aplicadas is
    '2BF: aprobaciones aplicadas (valores anteriores y nuevos, revisiones resueltas). Escritura solo via cf_aplicar_aprobacion_albaran.';

create or replace function public.cf_albaranes_aprobaciones_append_only()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    raise exception 'ALBARANES_APROBACIONES_APPEND_ONLY';
end;
$$;

drop trigger if exists albaranes_aprobaciones_append_only on public.albaranes_aprobaciones;
create trigger albaranes_aprobaciones_append_only
    before update or delete on public.albaranes_aprobaciones
    for each row execute function public.cf_albaranes_aprobaciones_append_only();
drop trigger if exists albaranes_aprobaciones_sin_truncate on public.albaranes_aprobaciones;
create trigger albaranes_aprobaciones_sin_truncate
    before truncate on public.albaranes_aprobaciones
    for each statement execute function public.cf_albaranes_aprobaciones_append_only();
drop trigger if exists albaranes_aprobaciones_aplicadas_append_only on public.albaranes_aprobaciones_aplicadas;
create trigger albaranes_aprobaciones_aplicadas_append_only
    before update or delete on public.albaranes_aprobaciones_aplicadas
    for each row execute function public.cf_albaranes_aprobaciones_append_only();
drop trigger if exists albaranes_aprobaciones_aplicadas_sin_truncate on public.albaranes_aprobaciones_aplicadas;
create trigger albaranes_aprobaciones_aplicadas_sin_truncate
    before truncate on public.albaranes_aprobaciones_aplicadas
    for each statement execute function public.cf_albaranes_aprobaciones_append_only();

-- Equivalencia de identidad de la 22: numero con btrim, proveedor con R9. Solo para comparar.
create or replace function public.cf_identidad_valor_comparable(p_campo text, p_valor text)
returns text
language sql
immutable
set search_path = public
as $$
    select case when p_campo = 'id_proveedor' then public.cf_id_proveedor_comparable(p_valor)
                else btrim(p_valor) end
$$;

-- Lista {campo, anterior, nuevo} en forma comparable y ordenada por campo.
create or replace function public.cf_cambio_identidad_comparable(p_cambio jsonb)
returns jsonb
language sql
immutable
set search_path = public
as $$
    select coalesce(jsonb_agg(jsonb_build_object(
               'campo', e->>'campo',
               'anterior', public.cf_identidad_valor_comparable(e->>'campo', e->>'anterior'),
               'nuevo', public.cf_identidad_valor_comparable(e->>'campo', e->>'nuevo'))
           order by e->>'campo'), '[]'::jsonb)
      from jsonb_array_elements(coalesce(p_cambio, '[]'::jsonb)) e
$$;

-- Revision pendiente: REVISION (no de presencia) que ninguna aplicacion ha resuelto y cuyo campo
-- no se ha actualizado despues.
create or replace function public.cf_revision_albaran_pendiente(p_cambio_id bigint)
returns boolean
language sql
stable
set search_path = public
as $$
    select exists (
        select 1 from public.albaranes_cambios c
         where c.id = p_cambio_id and c.accion = 'REVISION' and c.campo <> 'presencia'
           and not exists (
               select 1 from public.albaranes_cambios u
                where u.farmacia = c.farmacia and u.id_contador = c.id_contador and u.campo = c.campo
                  and u.accion = 'ACTUALIZADO' and u.id > c.id)
           and not exists (
               select 1 from public.albaranes_aprobaciones_aplicadas p
                where p.farmacia = c.farmacia and p.id_contador = c.id_contador
                  and c.id = any(p.revisiones_resueltas)))
$$;

-- Registra la aprobacion de Pio de un cambio de identidad. No toca albaranes. El anterior debe
-- ser el valor actual de Supabase y el nuevo distinto. Idempotente.
create or replace function public.cf_registrar_aprobacion_albaran(
    p_farmacia text,
    p_id_contador bigint,
    p_cambio jsonb,
    p_aprobado_por text,
    p_aprobado_at timestamptz,
    p_referencia text,
    p_registrado_por text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    a public.albaranes%rowtype;
    v_item jsonb;
    v_actual text;
    v_cambio jsonb;
    v_id bigint;
begin
    if p_aprobado_por is distinct from 'Pio' then
        raise exception 'APROBADOR_NO_ADMITIDO';
    end if;
    if p_aprobado_at is null or p_aprobado_at > now() then
        raise exception 'FECHA_APROBACION_INVALIDA';
    end if;
    if nullif(btrim(p_referencia), '') is null or nullif(btrim(p_registrado_por), '') is null then
        raise exception 'REFERENCIA_Y_REGISTRADOR_OBLIGATORIOS';
    end if;
    if not exists (select 1 from public.cf_configuracion c
                    where c.id and p_farmacia = any(c.farmacias_habilitadas)) then
        raise exception 'FARMACIA_NO_HABILITADA';
    end if;
    select * into a from public.albaranes where farmacia = p_farmacia and id_contador = p_id_contador;
    if not found then
        raise exception 'ALBARAN_NO_EXISTE:%:%', p_farmacia, p_id_contador;
    end if;
    if p_cambio is null or jsonb_typeof(p_cambio) <> 'array' or jsonb_array_length(p_cambio) not between 1 and 2
       or (select count(distinct e->>'campo') from jsonb_array_elements(p_cambio) e) <> jsonb_array_length(p_cambio) then
        raise exception 'CAMBIO_INVALIDO';
    end if;
    for v_item in select * from jsonb_array_elements(p_cambio) loop
        if jsonb_typeof(v_item) <> 'object'
           or (select array_agg(k order by k) from jsonb_object_keys(v_item) k) <> array['anterior', 'campo', 'nuevo']
           or coalesce(v_item->>'campo', '') not in ('numero_albaran', 'id_proveedor')
           or jsonb_typeof(v_item->'anterior') <> 'string' or jsonb_typeof(v_item->'nuevo') <> 'string'
           or nullif(btrim(v_item->>'nuevo'), '') is null then
            raise exception 'CAMBIO_INVALIDO';
        end if;
        v_actual := case v_item->>'campo' when 'numero_albaran' then a.numero_albaran else a.id_proveedor end;
        if public.cf_identidad_valor_comparable(v_item->>'campo', v_item->>'anterior')
               is distinct from public.cf_identidad_valor_comparable(v_item->>'campo', v_actual) then
            raise exception 'APROBACION_NO_CORRESPONDE_AL_ALBARAN:%', v_item->>'campo';
        end if;
        if public.cf_identidad_valor_comparable(v_item->>'campo', v_item->>'nuevo')
               = public.cf_identidad_valor_comparable(v_item->>'campo', v_item->>'anterior') then
            raise exception 'CAMBIO_INVALIDO';
        end if;
    end loop;

    select jsonb_agg(jsonb_build_object('campo', e->>'campo', 'anterior', btrim(e->>'anterior'),
                                        'nuevo', btrim(e->>'nuevo')) order by e->>'campo')
      into v_cambio
      from jsonb_array_elements(p_cambio) e;
    select id into v_id from public.albaranes_aprobaciones
     where farmacia = p_farmacia and id_contador = p_id_contador and cambio = v_cambio;
    if v_id is not null then
        return jsonb_build_object('accion', 'YA_REGISTRADA', 'aprobacion_id', v_id);
    end if;
    insert into public.albaranes_aprobaciones
        (farmacia, id_contador, motivo, cambio, aprobado_por, aprobado_at, referencia, registrado_por)
    values (p_farmacia, p_id_contador, 'CAMBIO_IDENTIDAD', v_cambio, p_aprobado_por, p_aprobado_at,
            btrim(p_referencia), btrim(p_registrado_por))
    returning id into v_id;
    return jsonb_build_object('accion', 'REGISTRADA', 'aprobacion_id', v_id, 'cambio', v_cambio);
end;
$$;

-- Aplica UNA aprobacion con los valores actuales de Farmatic. Solo si el cambio de identidad
-- detectado ahora coincide con lo aprobado y esta registrado como revision pendiente, y el
-- albaran no esta reservado (R15, tabla bloqueada en modo SHARE) ni ausente. Si no, no
-- escribe nada y el albaran sigue en revision. Solo cambia los campos aprobados, con el literal
-- de Farmatic; el resto lo actualiza la siguiente resincronizacion.
create or replace function public.cf_aplicar_aprobacion_albaran(
    p_aprobacion_id bigint,
    p_valores jsonb,
    p_ejecucion_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    ap public.albaranes_aprobaciones%rowtype;
    a public.albaranes%rowtype;
    v_reserva text;
    v_detectado jsonb;
    v_pendiente jsonb;
    v_resueltas bigint[];
    v_numero text;
    v_proveedor text;
begin
    if nullif(btrim(p_ejecucion_id), '') is null then
        raise exception 'EJECUCION_ID_OBLIGATORIO';
    end if;
    if p_valores is null or jsonb_typeof(p_valores) <> 'object'
       or not (p_valores ?& array['id_proveedor', 'numero_albaran']) then
        raise exception 'VALORES_INCOMPLETOS';
    end if;
    select * into ap from public.albaranes_aprobaciones where id = p_aprobacion_id;
    if not found then
        raise exception 'APROBACION_NO_EXISTE:%', p_aprobacion_id;
    end if;
    if not exists (select 1 from public.cf_configuracion c
                    where c.id and ap.farmacia = any(c.farmacias_habilitadas)) then
        raise exception 'FARMACIA_NO_HABILITADA';
    end if;

    lock table public.conciliacion_albaranes_reservados in share mode;
    select * into a from public.albaranes
     where farmacia = ap.farmacia and id_contador = ap.id_contador
     for update;
    if not found then
        raise exception 'ALBARAN_NO_EXISTE:%:%', ap.farmacia, ap.id_contador;
    end if;
    if exists (select 1 from public.albaranes_aprobaciones_aplicadas where aprobacion_id = ap.id) then
        return jsonb_build_object('accion', 'YA_APLICADA', 'aprobacion_id', ap.id);
    end if;

    select coalesce(f.numero_factura, r.factura_id::text) into v_reserva
      from public.conciliacion_albaranes_reservados r
      left join public.facturas f on f.id = r.factura_id
     where r.albaran_farmacia = ap.farmacia and r.albaran_id_contador = ap.id_contador;
    if v_reserva is not null then
        return jsonb_build_object('accion', 'NO_APLICADA', 'motivo', 'RESERVADO:' || v_reserva,
                                  'aprobacion_id', ap.id);
    end if;
    if public.cf_albaran_ausente_abierto(ap.farmacia, ap.id_contador) then
        return jsonb_build_object('accion', 'NO_APLICADA', 'motivo', 'AUSENTE_EN_FARMATIC',
                                  'aprobacion_id', ap.id);
    end if;

    -- Cambio de identidad que Farmatic muestra ahora (literales como en cf_resincronizar_albaran).
    select coalesce(jsonb_agg(jsonb_build_object('campo', x.campo, 'anterior', x.anterior, 'nuevo', x.nuevo)
                              order by x.campo), '[]'::jsonb)
      into v_detectado
      from (values
          ('numero_albaran', a.numero_albaran, btrim(p_valores->>'numero_albaran')),
          ('id_proveedor', a.id_proveedor, p_valores->>'id_proveedor')
      ) x(campo, anterior, nuevo)
     where public.cf_identidad_valor_comparable(x.campo, x.anterior)
               is distinct from public.cf_identidad_valor_comparable(x.campo, x.nuevo);
    -- Revisiones CAMBIO_IDENTIDAD pendientes: cada campo detectado debe estar registrado.
    select coalesce(jsonb_agg(jsonb_build_object('campo', c.campo, 'anterior', c.valor_anterior,
                                                 'nuevo', c.valor_nuevo) order by c.id), '[]'::jsonb)
      into v_pendiente
      from public.albaranes_cambios c
     where c.farmacia = ap.farmacia and c.id_contador = ap.id_contador
       and c.accion = 'REVISION' and c.motivo = 'CAMBIO_IDENTIDAD'
       and public.cf_revision_albaran_pendiente(c.id);
    if jsonb_array_length(v_detectado) = 0
       or public.cf_cambio_identidad_comparable(ap.cambio) is distinct from public.cf_cambio_identidad_comparable(v_detectado)
       or exists (select 1 from jsonb_array_elements(public.cf_cambio_identidad_comparable(v_detectado)) d
                   where not exists (select 1 from jsonb_array_elements(public.cf_cambio_identidad_comparable(v_pendiente)) p
                                      where p = d)) then
        return jsonb_build_object('accion', 'NO_APLICADA', 'motivo', 'CAMBIO_NO_COINCIDE', 'aprobacion_id', ap.id,
                                  'aprobado', ap.cambio, 'detectado', v_detectado, 'pendiente', v_pendiente);
    end if;

    select coalesce(array_agg(c.id order by c.id), '{}') into v_resueltas
      from public.albaranes_cambios c
     where c.farmacia = ap.farmacia and c.id_contador = ap.id_contador
       and c.accion = 'REVISION' and c.motivo = 'CAMBIO_IDENTIDAD'
       and public.cf_revision_albaran_pendiente(c.id);
    v_numero := case when ap.cambio @> '[{"campo": "numero_albaran"}]'
                     then btrim(p_valores->>'numero_albaran') else a.numero_albaran end;
    v_proveedor := case when ap.cambio @> '[{"campo": "id_proveedor"}]'
                        then p_valores->>'id_proveedor' else a.id_proveedor end;
    begin
        update public.albaranes
           set numero_albaran = v_numero,
               id_proveedor = v_proveedor,
               fecha_actualizacion = now()
         where farmacia = ap.farmacia and id_contador = ap.id_contador;
    exception when unique_violation then
        raise exception 'IDENTIDAD_OCUPADA:%:%', v_proveedor, v_numero;
    end;
    insert into public.albaranes_aprobaciones_aplicadas
        (aprobacion_id, farmacia, id_contador, ejecucion_id, valores_anteriores, valores_nuevos,
         revisiones_resueltas)
    values (ap.id, ap.farmacia, ap.id_contador, p_ejecucion_id,
            jsonb_build_object('numero_albaran', a.numero_albaran, 'id_proveedor', a.id_proveedor),
            jsonb_build_object('numero_albaran', v_numero, 'id_proveedor', v_proveedor),
            v_resueltas);
    return jsonb_build_object('accion', 'APLICADA', 'aprobacion_id', ap.id, 'campos', v_detectado,
                              'revisiones_resueltas', to_jsonb(v_resueltas));
end;
$$;

-- Resincronizacion de la 22 sin repetir una revision identica pendiente.
"""

PRIVILEGIOS = """
-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta las RPC.
revoke all on function public.cf_resincronizar_albaran(text, bigint, jsonb, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_resincronizar_albaran(text, bigint, jsonb, text, text)
    to service_role;
revoke all on function public.cf_registrar_aprobacion_albaran(text, bigint, jsonb, text, timestamptz, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_registrar_aprobacion_albaran(text, bigint, jsonb, text, timestamptz, text, text)
    to service_role;
revoke all on function public.cf_aplicar_aprobacion_albaran(bigint, jsonb, text)
    from public, anon, authenticated;
grant execute on function public.cf_aplicar_aprobacion_albaran(bigint, jsonb, text)
    to service_role;
-- Auxiliares: solo el propietario (las usan las funciones SECURITY DEFINER).
revoke all on function public.cf_revision_albaran_pendiente(bigint)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_identidad_valor_comparable(text, text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_cambio_identidad_comparable(jsonb)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_albaranes_aprobaciones_append_only()
    from public, anon, authenticated, service_role;

commit;
"""

ROLLBACK_SQL = """-- Rollback de la migracion 23 (Hito 2BF): devuelve el esquema exacto de la 22.
-- Solo con confirmacion de Pio. Se pierden las aprobaciones y su historial de aplicacion; los
-- valores ya aplicados en albaranes se conservan.
begin;

-- cf_resincronizar_albaran: texto exacto de la migracion 22.
{resync_22}
drop function if exists public.cf_aplicar_aprobacion_albaran(bigint, jsonb, text);
drop function if exists public.cf_registrar_aprobacion_albaran(text, bigint, jsonb, text, timestamptz, text, text);
drop function if exists public.cf_revision_albaran_pendiente(bigint);
drop table if exists public.albaranes_aprobaciones_aplicadas;
drop table if exists public.albaranes_aprobaciones;
drop function if exists public.cf_albaranes_aprobaciones_append_only();
drop function if exists public.cf_cambio_identidad_comparable(jsonb);
drop function if exists public.cf_identidad_valor_comparable(text, text);

revoke all on function public.cf_resincronizar_albaran(text, bigint, jsonb, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_resincronizar_albaran(text, bigint, jsonb, text, text)
    to service_role;

commit;
"""


def main() -> None:
    DESTINO.write_text(CABECERA + resincronizar_23() + PRIVILEGIOS, encoding="utf-8", newline="\n")
    ROLLBACK.write_text(ROLLBACK_SQL.format(resync_22=funcion(M22, "cf_resincronizar_albaran")),
                        encoding="utf-8", newline="\n")
    print(DESTINO.name, ROLLBACK.name)


if __name__ == "__main__":
    main()
