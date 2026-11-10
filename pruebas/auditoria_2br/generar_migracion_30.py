"""Hito 2BR: genera de forma determinista la migracion 30 (detalle por linea) y su rollback.

Uso: python -B pruebas/auditoria_2br/generar_migracion_30.py

- ``cf_detalles_por_linea``: calcula por detalle el importe del PDF, el de Farmatic, la diferencia y el estado de la
  LINEA (espejo exacto de ``conciliacion.valores_por_linea``).
- ``cf_persistir_conciliacion`` de la 30 sale del texto EXACTO de la 24 (las 25-29 no lo cambian) con tres
  reemplazos comprobados unicos: una variable, la comprobacion de los valores por linea que traiga el resultado
  (``DETALLE_LINEA_NO_COINCIDE``) y el alta de los detalles con los valores calculados por la BD.
- Relleno de los detalles existentes con la misma funcion, una sola vez; los valores previos se guardan en
  ``conciliacion_detalles_previo_30`` para que el rollback los devuelva exactamente.
- El rollback reinstala el texto exacto de la 24, devuelve los valores previos y elimina lo nuevo: rollback == 29.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql/migrations"
M24 = MIG / "24_cf_r17_recepcion.sql"
DESTINO = MIG / "30_cf_detalle_por_linea.sql"
ROLLBACK = MIG / "30_cf_detalle_por_linea.rollback.sql"

DETALLES_JSON = "coalesce(p_resultado->'detalles', '[]'::jsonb)"
PERSISTIR = "public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)"
POR_LINEA = "public.cf_detalles_por_linea(uuid, jsonb)"
PREVIO = "public.conciliacion_detalles_previo_30"


def funcion(path: Path, nombre: str) -> str:
    texto = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    inicio = texto.index(f"create or replace function public.{nombre}(")
    fin = texto.index("$$;\n", texto.index("as $$", inicio) + 5) + 4
    return texto[inicio:fin]


def _reemplazar(texto: str, viejo: str, nuevo: str) -> str:
    assert texto.count(viejo) == 1, viejo
    return texto.replace(viejo, nuevo)


DETALLES_POR_LINEA = """create or replace function public.cf_detalles_por_linea(
    p_factura_id uuid,
    p_detalles jsonb
)
returns table (
    orden integer,
    importe_documental numeric,
    importe_farmatic numeric,
    diferencia numeric,
    estado text
)
language sql
stable
set search_path = public
as $$
    with d as (
        select (x->>'orden')::integer as orden,
               x->>'tipo_relacion' as tipo,
               nullif(x->>'factura_albaran_extraido_id', '')::uuid as linea,
               round((x->>'importe_aplicado')::numeric, 4) as aplicado
          from jsonb_array_elements(coalesce(p_detalles, '[]'::jsonb)) x
    ), l as (
        select d.orden, d.tipo, d.aplicado,
               case when d.tipo = 'MOVIMIENTO_NO_FARMATIC' or e.importe_total is null then null
                    when e.tipo_movimiento = 'ABONO' then -abs(round(e.importe_total, 4))
                    else round(e.importe_total, 4) end as documental,
               sum(d.aplicado) filter (where d.tipo in ('UNO_A_UNO', 'UNO_A_VARIOS', 'VARIOS_A_UNO'))
                   over (partition by d.linea) as suma_linea
          from d
          left join public.facturas_albaranes_extraidos e
            on e.id = d.linea and e.factura_id = p_factura_id
    )
    select l.orden,
           case when l.tipo = 'MOVIMIENTO_NO_FARMATIC' then l.aplicado else l.documental end,
           case when l.tipo in ('MOVIMIENTO_NO_FARMATIC', 'SIN_COINCIDENCIA') then null else l.aplicado end,
           case when l.tipo = 'MOVIMIENTO_NO_FARMATIC' or l.documental is null then null
                when l.tipo = 'SIN_COINCIDENCIA' then l.documental
                else l.documental - l.suma_linea end,
           case when l.tipo = 'MOVIMIENTO_NO_FARMATIC' or l.documental is null then 'NO_EVALUABLE'
                when l.tipo = 'SIN_COINCIDENCIA' then 'DIFERENCIA'
                when abs(l.documental - l.suma_linea) <= 0.0500 then 'COINCIDE'
                else 'DIFERENCIA' end
      from l
$$;
"""


def persistir_conciliacion_30() -> str:
    f = funcion(M24, "cf_persistir_conciliacion")
    f = _reemplazar(
        f,
        "    -- R15 (2BA)\n    v_conflicto text;\n",
        "    -- R15 (2BA)\n    v_conflicto text;\n"
        "    -- 2BR (30): detalle por linea\n    v_detalles jsonb := " + DETALLES_JSON + ";\n")
    ancla = ("    if v_conflicto is not null then\n"
             "        raise exception 'LINEA_R17_NO_VALIDA:%', v_conflicto;\n"
             "    end if;\n")
    f = _reemplazar(f, ancla, ancla +
                    "    -- 2BR (30): los valores por linea los calcula la BD; si el resultado los trae, deben coincidir.\n"
                    "    select coalesce(d->>'orden', 'SIN_ORDEN')\n"
                    "      into v_conflicto\n"
                    "      from jsonb_array_elements(v_detalles) d\n"
                    "      left join public.cf_detalles_por_linea(f.id, v_detalles) v\n"
                    "        on v.orden = (d->>'orden')::integer\n"
                    "     where d ? 'importe_documental'\n"
                    "       and ((d->>'importe_documental')::numeric is distinct from v.importe_documental\n"
                    "         or (d->>'importe_farmatic')::numeric is distinct from v.importe_farmatic\n"
                    "         or (d->>'diferencia')::numeric is distinct from v.diferencia\n"
                    "         or d->>'estado' is distinct from v.estado)\n"
                    "     limit 1;\n"
                    "    if v_conflicto is not null then\n"
                    "        raise exception 'DETALLE_LINEA_NO_COINCIDE:%', v_conflicto;\n"
                    "    end if;\n")
    return _reemplazar(
        f,
        "        tipo_relacion, importe_aplicado, estado, provenance\n"
        "    )\n"
        "    select v_id,\n"
        "           (d->>'orden')::integer,\n"
        "           nullif(d->>'factura_albaran_extraido_id', '')::uuid,\n"
        "           nullif(d->>'factura_movimiento_id', '')::uuid,\n"
        "           d->>'albaran_farmacia',\n"
        "           nullif(d->>'albaran_id_contador', '')::bigint,\n"
        "           coalesce((d->>'coincidencia_numero_literal')::boolean, false),\n"
        "           d->>'tipo_relacion',\n"
        "           (d->>'importe_aplicado')::numeric,\n"
        "           d->>'estado',\n"
        "           coalesce(d->'provenance', '{}'::jsonb)\n"
        "      from jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d;\n",
        "        tipo_relacion, importe_documental, importe_farmatic, importe_aplicado, diferencia, estado,\n"
        "        provenance\n"
        "    )\n"
        "    select v_id,\n"
        "           (d->>'orden')::integer,\n"
        "           nullif(d->>'factura_albaran_extraido_id', '')::uuid,\n"
        "           nullif(d->>'factura_movimiento_id', '')::uuid,\n"
        "           d->>'albaran_farmacia',\n"
        "           nullif(d->>'albaran_id_contador', '')::bigint,\n"
        "           coalesce((d->>'coincidencia_numero_literal')::boolean, false),\n"
        "           d->>'tipo_relacion',\n"
        "           v.importe_documental,\n"
        "           v.importe_farmatic,\n"
        "           (d->>'importe_aplicado')::numeric,\n"
        "           v.diferencia,\n"
        "           v.estado,\n"
        "           coalesce(d->'provenance', '{}'::jsonb)\n"
        "      from jsonb_array_elements(v_detalles) d\n"
        "      left join public.cf_detalles_por_linea(f.id, v_detalles) v\n"
        "        on v.orden = (d->>'orden')::integer;\n")


CABECERA = """-- Migracion 30 (Hito 2BR): detalle por linea en la conciliacion.
-- Generada por pruebas/auditoria_2br/generar_migracion_30.py a partir del texto exacto de la 24
-- (cf_persistir_conciliacion; las 25-29 no lo cambian). Cada detalle guarda el importe del PDF, el importe de
-- Farmatic, la diferencia y el estado de SU LINEA (antes: NULL y el estado de la factura). Los calcula la BD con
-- cf_detalles_por_linea; si el resultado los trae, deben coincidir (DETALLE_LINEA_NO_COINCIDE). El resultado de
-- la factura no cambia. Rellena una sola vez los detalles existentes con la misma funcion y guarda los valores
-- previos para el rollback. No toca facturas, conciliaciones, reservas ni historial. Idempotente. Requiere la 29.
begin;

do $$
begin
    if not exists (select 1 from pg_policy where polrelid = 'public.albaranes'::regclass
                                             and polname = 'albaranes_lectura_select') then
        raise exception 'MIGRACION_29_AUSENTE';
    end if;
end;
$$;

-- Detalle por linea (2BR, decision de diseno del hito; tolerancia por linea 0,05, la misma con la que casa una
-- linea y la de R17):
--   albaran casado (1:1 o R17): PDF = importe de la linea con signo (ABONO en negativo); Farmatic = importe
--     aplicado del albaran; diferencia = PDF - suma de los albaranes de la linea (en R17, en los dos detalles);
--     COINCIDE si |diferencia| <= 0,05, si no DIFERENCIA;
--   linea sin coincidencia: PDF = importe de la linea, sin Farmatic, diferencia = PDF, DIFERENCIA;
--   linea sin importe documental (o de otra factura): NO_EVALUABLE, sin diferencia;
--   movimiento o ajuste documental: PDF = importe aplicado, sin contraparte en Farmatic, NO_EVALUABLE.
"""

PIE = f"""
-- Relleno de los detalles existentes (una sola vez: si la tabla de valores previos ya existe, no se repite).
do $$
begin
    if to_regclass('{PREVIO}') is null then
        create table {PREVIO} (
            detalle_id uuid primary key references public.conciliacion_detalles(id) on delete cascade,
            importe_documental numeric(14,4),
            importe_farmatic numeric(14,4),
            diferencia numeric(14,4),
            estado text not null
        );
        insert into {PREVIO} (detalle_id, importe_documental, importe_farmatic, diferencia, estado)
        select id, importe_documental, importe_farmatic, diferencia, estado
          from public.conciliacion_detalles;
        update public.conciliacion_detalles d
           set importe_documental = v.importe_documental,
               importe_farmatic = v.importe_farmatic,
               diferencia = v.diferencia,
               estado = v.estado
          from (select c.id as conciliacion_id, l.*
                  from public.conciliaciones c
                  cross join lateral public.cf_detalles_por_linea(
                      c.factura_id,
                      (select coalesce(jsonb_agg(jsonb_build_object(
                                  'orden', x.orden,
                                  'tipo_relacion', x.tipo_relacion,
                                  'factura_albaran_extraido_id', x.factura_albaran_extraido_id,
                                  'importe_aplicado', x.importe_aplicado)), '[]'::jsonb)
                         from public.conciliacion_detalles x
                        where x.conciliacion_id = c.id)) l) v
         where d.conciliacion_id = v.conciliacion_id
           and d.orden = v.orden;
    end if;
end;
$$;

comment on table {PREVIO} is
    'Migracion 30 (2BR): valores por detalle anteriores al relleno, solo para el rollback de la 30.';
alter table {PREVIO} enable row level security;

-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta la RPC.
revoke all on function {PERSISTIR}
    from public, anon, authenticated;
grant execute on function {PERSISTIR}
    to service_role;
-- Auxiliar y valores previos: solo el propietario.
revoke all on function {POR_LINEA}
    from public, anon, authenticated, service_role;
revoke all on table {PREVIO}
    from public, anon, authenticated, service_role;

commit;
"""

CABECERA_ROLLBACK = """-- Rollback de la migracion 30 (Hito 2BR): devuelve el esquema exacto de la 29.
-- Solo con confirmacion de Pio. Devuelve a cada detalle rellenado sus valores previos exactos; los detalles
-- persistidos despues de la 30 vuelven a la semantica anterior (importes por linea NULL y el estado de la
-- factura: COINCIDE si la conciliacion es CONCILIADA, si no DIFERENCIA). Conciliaciones, reservas y facturas no
-- cambian.
begin;

-- cf_persistir_conciliacion: texto exacto de la migracion 24 (vigente en la 29).
"""

PIE_ROLLBACK = f"""
revoke all on function {PERSISTIR}
    from public, anon, authenticated;
grant execute on function {PERSISTIR}
    to service_role;

do $$
begin
    if to_regclass('{PREVIO}') is not null then
        update public.conciliacion_detalles d
           set importe_documental = p.importe_documental,
               importe_farmatic = p.importe_farmatic,
               diferencia = p.diferencia,
               estado = p.estado
          from {PREVIO} p
         where p.detalle_id = d.id;
        update public.conciliacion_detalles d
           set importe_documental = null,
               importe_farmatic = null,
               diferencia = null,
               estado = case when c.resultado = 'CONCILIADA' then 'COINCIDE' else 'DIFERENCIA' end
          from public.conciliaciones c
         where c.id = d.conciliacion_id
           and not exists (select 1 from {PREVIO} p where p.detalle_id = d.id);
    end if;
end;
$$;

drop table if exists {PREVIO};
drop function if exists {POR_LINEA};

commit;
"""


def generar() -> tuple[str, str]:
    migracion = CABECERA + "\n" + DETALLES_POR_LINEA + "\n" + persistir_conciliacion_30() + PIE
    rollback = CABECERA_ROLLBACK + funcion(M24, "cf_persistir_conciliacion") + PIE_ROLLBACK
    return migracion, rollback


def main() -> None:
    migracion, rollback = generar()
    DESTINO.write_bytes(migracion.encode("utf-8"))
    ROLLBACK.write_bytes(rollback.encode("utf-8"))
    print(DESTINO.relative_to(ROOT), ROLLBACK.relative_to(ROOT))


if __name__ == "__main__":
    main()
