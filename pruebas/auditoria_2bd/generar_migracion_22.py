"""Hito 2BD: genera de forma determinista la migracion 22 y su rollback.

Uso: python -B pruebas/auditoria_2bd/generar_migracion_22.py

- ``cf_persistir_conciliacion`` de la 22 sale del texto EXACTO de la migracion 21 con el
  bloque de albaranes ausentes en Farmatic insertado (reemplazo comprobado unico).
- El rollback reinstala el texto exacto de la 21, elimina los objetos nuevos y la columna
  ``albaranes.id_recepcion``: rollback == estado 21 (se pierden el historial de cambios y
  las recepciones cargadas).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql/migrations"
M21 = MIG / "21_cf_exclusividad_albaranes.sql"
DESTINO = MIG / "22_cf_resincronizacion_albaranes.sql"
ROLLBACK = MIG / "22_cf_resincronizacion_albaranes.rollback.sql"

DETALLES = "jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d"


def funcion(path: Path, nombre: str) -> str:
    texto = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    inicio = texto.index(f"create or replace function public.{nombre}(")
    fin = texto.index("$$;\n", texto.index("as $$", inicio) + 5) + 4
    return texto[inicio:fin]


def _reemplazar(texto: str, viejo: str, nuevo: str) -> str:
    assert texto.count(viejo) == 1, viejo
    return texto.replace(viejo, nuevo)


def persistir_conciliacion_22() -> str:
    f = funcion(M21, "cf_persistir_conciliacion")
    ancla = ("     where r.factura_id <> f.id\n"
             "     limit 1;\n"
             "    if v_conflicto is not null then\n"
             "        raise exception 'ALBARAN_YA_CONCILIADO:%', v_conflicto;\n"
             "    end if;\n")
    return _reemplazar(f, ancla, ancla +
                       "    -- 2BD: un albaran con revision AUSENTE_EN_FARMATIC abierta queda fuera del casado.\n"
                       "    select (d->>'albaran_farmacia') || ':' || nullif(d->>'albaran_id_contador', '')::bigint\n"
                       "      into v_conflicto\n"
                       f"      from {DETALLES}\n"
                       "     where nullif(d->>'albaran_id_contador', '') is not null\n"
                       "       and public.cf_albaran_ausente_abierto(d->>'albaran_farmacia',\n"
                       "                                             nullif(d->>'albaran_id_contador', '')::bigint)\n"
                       "     limit 1;\n"
                       "    if v_conflicto is not null then\n"
                       "        raise exception 'ALBARAN_AUSENTE_EN_FARMATIC:%', v_conflicto;\n"
                       "    end if;\n")


CABECERA = """-- Migracion 22 (Hito 2BD): resincronizacion de albaranes modificados en Farmatic.
-- Generada por pruebas/auditoria_2bd/generar_migracion_22.py a partir del texto exacto
-- de la 21 (cf_persistir_conciliacion). Columna albaranes.id_recepcion (metadato),
-- historial append-only albaranes_cambios, RPC de actualizacion con revalidacion de la
-- reserva R15 dentro de la transaccion y registro de albaranes ausentes en Farmatic
-- (que quedan fuera del casado). No modifica filas existentes. Idempotente. Requiere la 21.
begin;

do $$
begin
    if to_regclass('public.conciliacion_albaranes_reservados') is null then
        raise exception 'MIGRACION_21_AUSENTE';
    end if;
end;
$$;

-- IdRecepcion de Farmatic (AlbaranRecep por proveedor y numero del albaran). Metadato: no
-- interviene en la conciliacion. Nullable: hay albaranes sin recepcion.
alter table public.albaranes add column if not exists id_recepcion bigint;
comment on column public.albaranes.id_recepcion is
    '2BD: IdRecepcion de Farmatic (AlbaranRecep por proveedor y numero del albaran). Metadato.';

-- Historial append-only de diferencias entre Farmatic y Supabase.albaranes.
create table if not exists public.albaranes_cambios (
    id bigint generated always as identity primary key,
    farmacia text not null,
    id_contador bigint not null,
    detectado_at timestamptz not null default now(),
    origen text not null,
    ejecucion_id text not null,
    campo text not null,
    valor_anterior text,
    valor_nuevo text,
    accion text not null,
    motivo text,
    detalle jsonb not null default '{}'::jsonb,
    constraint albaranes_cambios_origen_check
        check (origen in ('RESYNC_VENTANA', 'CARGA_HISTORICA')),
    constraint albaranes_cambios_accion_check
        check (accion in ('ACTUALIZADO', 'REVISION', 'REVISION_CERRADA'))
);
create index if not exists albaranes_cambios_albaran_idx
    on public.albaranes_cambios (farmacia, id_contador, id);
alter table public.albaranes_cambios enable row level security;
revoke all on table public.albaranes_cambios from public, anon, authenticated, service_role;
grant select on table public.albaranes_cambios to service_role;
revoke all on sequence public.albaranes_cambios_id_seq from public, anon, authenticated, service_role;
comment on table public.albaranes_cambios is
    '2BD: historial append-only de la resincronizacion de albaranes. Escritura solo via cf_resincronizar_albaran y cf_registrar_albaran_ausente.';

create or replace function public.cf_albaranes_cambios_append_only()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    raise exception 'ALBARANES_CAMBIOS_APPEND_ONLY';
end;
$$;

drop trigger if exists albaranes_cambios_append_only on public.albaranes_cambios;
create trigger albaranes_cambios_append_only
    before update or delete on public.albaranes_cambios
    for each row execute function public.cf_albaranes_cambios_append_only();
drop trigger if exists albaranes_cambios_sin_truncate on public.albaranes_cambios;
create trigger albaranes_cambios_sin_truncate
    before truncate on public.albaranes_cambios
    for each statement execute function public.cf_albaranes_cambios_append_only();

-- R9: '2', '0002' y '0002 ' son el mismo proveedor (misma regla que
-- conciliacion._id_proveedor_comparable). Solo para comparar.
create or replace function public.cf_id_proveedor_comparable(p_valor text)
returns text
language sql
immutable
set search_path = public
as $$
    select case
        when p_valor is null then null
        when btrim(p_valor) ~ '^[0-9]+$' then coalesce(nullif(ltrim(btrim(p_valor), '0'), ''), '0')
        else nullif(btrim(p_valor), '')
    end
$$;

-- Revision AUSENTE_EN_FARMATIC abierta: el ultimo evento de presencia del albaran es AUSENTE.
create or replace function public.cf_albaran_ausente_abierto(p_farmacia text, p_id_contador bigint)
returns boolean
language sql
stable
set search_path = public
as $$
    select coalesce((
        select c.valor_nuevo = 'AUSENTE'
          from public.albaranes_cambios c
         where c.farmacia = p_farmacia and c.id_contador = p_id_contador and c.campo = 'presencia'
         order by c.id desc
         limit 1
    ), false)
$$;

-- Actualiza un albaran ya sincronizado con los valores actuales de Farmatic.
-- Identidad (numero, proveedor normalizado) distinta -> REVISION, nada se actualiza.
-- Campos de conciliacion distintos y albaran reservado por una conciliacion vigente (R15,
-- releido aqui) -> REVISION, no se actualizan. Sin reserva -> se actualizan. El metadato
-- id_recepcion se actualiza siempre que la identidad coincida. Idempotente: una revision
-- identica no se vuelve a registrar; sin diferencias no escribe nada.
create or replace function public.cf_resincronizar_albaran(
    p_farmacia text,
    p_id_contador bigint,
    p_valores jsonb,
    p_origen text,
    p_ejecucion_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    a public.albaranes%rowtype;
    v_identidad jsonb;
    v_cambios jsonb;
    v_meta jsonb;
    v_reserva text;
    v_cerrada boolean := false;
    v_item jsonb;
    v_motivo text;
    v_accion text;
begin
    if p_origen is null or p_origen not in ('RESYNC_VENTANA', 'CARGA_HISTORICA') then
        raise exception 'ORIGEN_NO_ADMITIDO';
    end if;
    if nullif(btrim(p_ejecucion_id), '') is null then
        raise exception 'EJECUCION_ID_OBLIGATORIO';
    end if;
    if p_valores is null or jsonb_typeof(p_valores) <> 'object'
       or not (p_valores ?& array['id_proveedor', 'proveedor', 'numero_albaran', 'fecha',
                                  'importe_pvp', 'importe_puc', 'descuento']) then
        raise exception 'VALORES_INCOMPLETOS';
    end if;
    if not exists (select 1 from public.cf_configuracion c
                    where c.id and p_farmacia = any(c.farmacias_habilitadas)) then
        raise exception 'FARMACIA_NO_HABILITADA';
    end if;

    select * into a from public.albaranes
     where farmacia = p_farmacia and id_contador = p_id_contador
     for update;
    if not found then
        raise exception 'ALBARAN_NO_EXISTE:%:%', p_farmacia, p_id_contador;
    end if;

    -- Presente en Farmatic: se cierra una revision AUSENTE abierta.
    if public.cf_albaran_ausente_abierto(p_farmacia, p_id_contador) then
        insert into public.albaranes_cambios
            (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion, motivo)
        values (p_farmacia, p_id_contador, p_origen, p_ejecucion_id, 'presencia', 'AUSENTE', 'PRESENTE',
                'REVISION_CERRADA', 'PRESENTE_EN_FARMATIC');
        v_cerrada := true;
    end if;

    select coalesce(jsonb_agg(jsonb_build_object('campo', x.campo, 'anterior', x.anterior, 'nuevo', x.nuevo)
                              order by x.orden), '[]'::jsonb)
      into v_identidad
      from (values
          (1, 'numero_albaran', a.numero_albaran, btrim(p_valores->>'numero_albaran'),
           btrim(a.numero_albaran) is distinct from btrim(p_valores->>'numero_albaran')),
          (2, 'id_proveedor', a.id_proveedor, p_valores->>'id_proveedor',
           public.cf_id_proveedor_comparable(a.id_proveedor)
               is distinct from public.cf_id_proveedor_comparable(p_valores->>'id_proveedor'))
      ) x(orden, campo, anterior, nuevo, distinto)
     where x.distinto;

    if jsonb_array_length(v_identidad) > 0 then
        for v_item in select * from jsonb_array_elements(v_identidad) loop
            if not exists (
                select 1 from public.albaranes_cambios c
                 where c.farmacia = p_farmacia and c.id_contador = p_id_contador
                   and c.campo = v_item->>'campo' and c.accion = 'REVISION' and c.motivo = 'CAMBIO_IDENTIDAD'
                   and c.valor_anterior is not distinct from v_item->>'anterior'
                   and c.valor_nuevo is not distinct from v_item->>'nuevo'
            ) then
                insert into public.albaranes_cambios
                    (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion, motivo)
                values (p_farmacia, p_id_contador, p_origen, p_ejecucion_id, v_item->>'campo',
                        v_item->>'anterior', v_item->>'nuevo', 'REVISION', 'CAMBIO_IDENTIDAD');
            end if;
        end loop;
        return jsonb_build_object('accion', 'REVISION', 'motivo', 'CAMBIO_IDENTIDAD',
                                  'campos', v_identidad, 'revision_cerrada', v_cerrada);
    end if;

    select coalesce(jsonb_agg(jsonb_build_object('campo', x.campo, 'anterior', x.anterior, 'nuevo', x.nuevo)
                              order by x.orden), '[]'::jsonb)
      into v_cambios
      from (values
          (1, 'fecha', a.fecha::text, (p_valores->>'fecha')::date::text),
          (2, 'importe_puc', a.importe_puc::text, round((p_valores->>'importe_puc')::numeric, 2)::text),
          (3, 'importe_pvp', a.importe_pvp::text, round((p_valores->>'importe_pvp')::numeric, 2)::text),
          (4, 'descuento', a.descuento::text, round((p_valores->>'descuento')::numeric, 2)::text),
          (5, 'proveedor', a.proveedor, btrim(p_valores->>'proveedor'))
      ) x(orden, campo, anterior, nuevo)
     where x.anterior is distinct from x.nuevo;

    select coalesce(jsonb_agg(jsonb_build_object('campo', 'id_recepcion', 'anterior', a.id_recepcion::text,
                                                 'nuevo', nullif(p_valores->>'id_recepcion', '')::bigint::text)),
                    '[]'::jsonb)
      into v_meta
     where p_valores ? 'id_recepcion'
       and a.id_recepcion is distinct from nullif(p_valores->>'id_recepcion', '')::bigint;

    v_accion := 'SIN_CAMBIOS';
    if jsonb_array_length(v_cambios) > 0 then
        select f.numero_factura into v_reserva
          from public.conciliacion_albaranes_reservados r
          join public.facturas f on f.id = r.factura_id
         where r.albaran_farmacia = p_farmacia and r.albaran_id_contador = p_id_contador;
        if v_reserva is not null then
            v_motivo := 'RESERVADO:' || v_reserva;
            v_accion := 'REVISION';
            for v_item in select * from jsonb_array_elements(v_cambios) loop
                if not exists (
                    select 1 from public.albaranes_cambios c
                     where c.farmacia = p_farmacia and c.id_contador = p_id_contador
                       and c.campo = v_item->>'campo' and c.accion = 'REVISION' and c.motivo = v_motivo
                       and c.valor_anterior is not distinct from v_item->>'anterior'
                       and c.valor_nuevo is not distinct from v_item->>'nuevo'
                ) then
                    insert into public.albaranes_cambios
                        (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion, motivo)
                    values (p_farmacia, p_id_contador, p_origen, p_ejecucion_id, v_item->>'campo',
                            v_item->>'anterior', v_item->>'nuevo', 'REVISION', v_motivo);
                end if;
            end loop;
        else
            v_accion := 'ACTUALIZADO';
            update public.albaranes
               set fecha = (p_valores->>'fecha')::date,
                   importe_puc = round((p_valores->>'importe_puc')::numeric, 2),
                   importe_pvp = round((p_valores->>'importe_pvp')::numeric, 2),
                   descuento = round((p_valores->>'descuento')::numeric, 2),
                   proveedor = btrim(p_valores->>'proveedor'),
                   fecha_actualizacion = now()
             where farmacia = p_farmacia and id_contador = p_id_contador;
            insert into public.albaranes_cambios
                (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion)
            select p_farmacia, p_id_contador, p_origen, p_ejecucion_id, x->>'campo', x->>'anterior', x->>'nuevo',
                   'ACTUALIZADO'
              from jsonb_array_elements(v_cambios) x;
        end if;
    end if;

    if jsonb_array_length(v_meta) > 0 then
        update public.albaranes
           set id_recepcion = nullif(p_valores->>'id_recepcion', '')::bigint,
               fecha_actualizacion = now()
         where farmacia = p_farmacia and id_contador = p_id_contador;
        insert into public.albaranes_cambios
            (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion)
        select p_farmacia, p_id_contador, p_origen, p_ejecucion_id, x->>'campo', x->>'anterior', x->>'nuevo',
               'ACTUALIZADO'
          from jsonb_array_elements(v_meta) x;
        if v_accion = 'SIN_CAMBIOS' then
            v_accion := 'ACTUALIZADO';
        end if;
    end if;

    return jsonb_build_object('accion', v_accion, 'motivo', v_motivo, 'campos', v_cambios,
                              'metadatos', v_meta, 'revision_cerrada', v_cerrada);
end;
$$;

-- Albaran de Supabase que ya no existe en Farmatic: nunca se borra ni se modifica; queda
-- una revision AUSENTE_EN_FARMATIC (una sola vez mientras siga ausente) y sale del casado.
create or replace function public.cf_registrar_albaran_ausente(
    p_farmacia text,
    p_id_contador bigint,
    p_origen text,
    p_ejecucion_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_reserva text;
begin
    if p_origen is null or p_origen not in ('RESYNC_VENTANA', 'CARGA_HISTORICA') then
        raise exception 'ORIGEN_NO_ADMITIDO';
    end if;
    if nullif(btrim(p_ejecucion_id), '') is null then
        raise exception 'EJECUCION_ID_OBLIGATORIO';
    end if;
    if not exists (select 1 from public.cf_configuracion c
                    where c.id and p_farmacia = any(c.farmacias_habilitadas)) then
        raise exception 'FARMACIA_NO_HABILITADA';
    end if;
    perform 1 from public.albaranes
     where farmacia = p_farmacia and id_contador = p_id_contador
     for update;
    if not found then
        raise exception 'ALBARAN_NO_EXISTE:%:%', p_farmacia, p_id_contador;
    end if;
    if public.cf_albaran_ausente_abierto(p_farmacia, p_id_contador) then
        return jsonb_build_object('accion', 'YA_REGISTRADA', 'motivo', 'AUSENTE_EN_FARMATIC');
    end if;
    select f.numero_factura into v_reserva
      from public.conciliacion_albaranes_reservados r
      join public.facturas f on f.id = r.factura_id
     where r.albaran_farmacia = p_farmacia and r.albaran_id_contador = p_id_contador;
    insert into public.albaranes_cambios
        (farmacia, id_contador, origen, ejecucion_id, campo, valor_anterior, valor_nuevo, accion, motivo, detalle)
    values (p_farmacia, p_id_contador, p_origen, p_ejecucion_id, 'presencia', 'PRESENTE', 'AUSENTE',
            'REVISION', 'AUSENTE_EN_FARMATIC', jsonb_build_object('reservado_por', v_reserva));
    return jsonb_build_object('accion', 'REVISION', 'motivo', 'AUSENTE_EN_FARMATIC', 'reservado_por', v_reserva);
end;
$$;

-- Cierre atomico de la 21 con el rechazo de albaranes ausentes en Farmatic.
"""

PRIVILEGIOS = """
-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta las RPC.
revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_resincronizar_albaran(text, bigint, jsonb, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_resincronizar_albaran(text, bigint, jsonb, text, text)
    to service_role;
revoke all on function public.cf_registrar_albaran_ausente(text, bigint, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_registrar_albaran_ausente(text, bigint, text, text)
    to service_role;
-- Auxiliares: solo el propietario (las usan las funciones SECURITY DEFINER).
revoke all on function public.cf_albaran_ausente_abierto(text, bigint)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_id_proveedor_comparable(text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_albaranes_cambios_append_only()
    from public, anon, authenticated, service_role;

commit;
"""

ROLLBACK_SQL = """-- Rollback de la migracion 22 (Hito 2BD): devuelve el esquema exacto de la 21.
-- Primero el codigo, despues este SQL (solo con confirmacion de Pio). Se pierden el
-- historial albaranes_cambios y la columna albaranes.id_recepcion.
begin;

-- cf_persistir_conciliacion: texto exacto de la migracion 21.
{persistir_21}
drop function if exists public.cf_resincronizar_albaran(text, bigint, jsonb, text, text);
drop function if exists public.cf_registrar_albaran_ausente(text, bigint, text, text);
drop table if exists public.albaranes_cambios;
drop function if exists public.cf_albaranes_cambios_append_only();
drop function if exists public.cf_albaran_ausente_abierto(text, bigint);
drop function if exists public.cf_id_proveedor_comparable(text);
alter table public.albaranes drop column if exists id_recepcion;

revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;

commit;
"""


def main() -> None:
    DESTINO.write_text(CABECERA + persistir_conciliacion_22() + PRIVILEGIOS, encoding="utf-8", newline="\n")
    ROLLBACK.write_text(ROLLBACK_SQL.format(persistir_21=funcion(M21, "cf_persistir_conciliacion")),
                        encoding="utf-8", newline="\n")
    print(DESTINO.name, ROLLBACK.name)


if __name__ == "__main__":
    main()
