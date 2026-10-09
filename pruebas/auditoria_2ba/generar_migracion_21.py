"""Hito 2BA: genera de forma determinista la migracion 21 y su rollback.

Uso: python -B pruebas/auditoria_2ba/generar_migracion_21.py

- ``cf_persistir_conciliacion`` de la 21 sale del texto EXACTO de la migracion 20 con
  los bloques R15 insertados (cada reemplazo se comprueba unico).
- ``cf_evaluar_elegibilidad_conciliacion`` de la 21 sale del texto EXACTO de la 14 con R16.
- El rollback reinstala ambos textos exactos y elimina la tabla de reservas, de modo
  que rollback == estado 20.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql/migrations"
M14 = MIG / "14_cf_claim_conciliacion_v2.sql"
M20 = MIG / "20_cf_alliance_tolerancia_enriquecimiento.sql"
DESTINO = MIG / "21_cf_exclusividad_albaranes.sql"
ROLLBACK = MIG / "21_cf_exclusividad_albaranes.rollback.sql"


def funcion(path: Path, nombre: str) -> str:
    texto = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    inicio = texto.index(f"create or replace function public.{nombre}(")
    fin = texto.index("$$;\n", texto.index("as $$", inicio) + 5) + 4
    return texto[inicio:fin]


def _reemplazar(texto: str, viejo: str, nuevo: str) -> str:
    assert texto.count(viejo) == 1, viejo
    return texto.replace(viejo, nuevo)


DETALLES = "jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d"


def persistir_conciliacion_21() -> str:
    f = funcion(M20, "cf_persistir_conciliacion")
    f = _reemplazar(f, "    v_regla jsonb;\nbegin\n",
                    "    v_regla jsonb;\n"
                    "    -- R15 (2BA)\n"
                    "    v_conflicto text;\n"
                    "begin\n")
    f = _reemplazar(f, "                                  'albaranes_casados', v_casados, 'tolerancia', v_tolerancia);\n",
                    "                                  'albaranes_casados', v_casados, 'tolerancia', v_tolerancia);\n\n"
                    "    -- R15 (2BA): un albaran (farmacia, IdContador) solo justifica una linea de una\n"
                    "    -- conciliacion vigente: ni dos lineas de este resultado ni una reserva de otra\n"
                    "    -- factura. Un nuevo intento de la misma factura puede reutilizar sus albaranes.\n"
                    "    select (d->>'albaran_farmacia') || ':' || nullif(d->>'albaran_id_contador', '')::bigint\n"
                    "      into v_conflicto\n"
                    f"      from {DETALLES}\n"
                    "     where nullif(d->>'albaran_id_contador', '') is not null\n"
                    "     group by d->>'albaran_farmacia', nullif(d->>'albaran_id_contador', '')::bigint\n"
                    "    having count(*) > 1\n"
                    "     limit 1;\n"
                    "    if v_conflicto is not null then\n"
                    "        raise exception 'ALBARAN_YA_CONCILIADO:%', v_conflicto;\n"
                    "    end if;\n"
                    "    select r.albaran_farmacia || ':' || r.albaran_id_contador\n"
                    "      into v_conflicto\n"
                    f"      from {DETALLES}\n"
                    "      join public.conciliacion_albaranes_reservados r\n"
                    "        on r.albaran_farmacia = d->>'albaran_farmacia'\n"
                    "       and r.albaran_id_contador = nullif(d->>'albaran_id_contador', '')::bigint\n"
                    "     where r.factura_id <> f.id\n"
                    "     limit 1;\n"
                    "    if v_conflicto is not null then\n"
                    "        raise exception 'ALBARAN_YA_CONCILIADO:%', v_conflicto;\n"
                    "    end if;\n")
    f = _reemplazar(f, f"      from {DETALLES};\n",
                    f"      from {DETALLES};\n\n"
                    "    -- R15 (2BA): las reservas pasan a la nueva conciliacion vigente. La clave primaria\n"
                    "    -- (farmacia, IdContador) lo garantiza tambien ante escrituras concurrentes.\n"
                    "    delete from public.conciliacion_albaranes_reservados where factura_id = f.id;\n"
                    "    begin\n"
                    "        insert into public.conciliacion_albaranes_reservados\n"
                    "            (albaran_farmacia, albaran_id_contador, factura_id, conciliacion_id, orden)\n"
                    "        select d.albaran_farmacia, d.albaran_id_contador, f.id, v_id, d.orden\n"
                    "          from public.conciliacion_detalles d\n"
                    "         where d.conciliacion_id = v_id and d.albaran_id_contador is not null;\n"
                    "    exception when unique_violation then\n"
                    "        raise exception 'ALBARAN_YA_CONCILIADO';\n"
                    "    end;\n")
    return f


def elegibilidad_21() -> str:
    f = funcion(M14, "cf_evaluar_elegibilidad_conciliacion")
    f = _reemplazar(f, "    v_tolerancia numeric := 0.0500;\n", "    v_tolerancia numeric;\n")
    f = _reemplazar(f, "      from public.facturas_movimientos m\n     where m.factura_id = v_factura.id;\n",
                    "      from public.facturas_movimientos m\n     where m.factura_id = v_factura.id;\n\n"
                    "    -- R16 (2BA): la misma tolerancia proporcional de R11 con n = lineas sumadas\n"
                    "    -- (albaranes con importe + movimientos), en todas las comparaciones.\n"
                    "    select greatest(c.conciliacion_tolerancia_suelo,\n"
                    "                    least(c.conciliacion_tolerancia_por_albaran * (v_albaranes + v_movimientos),\n"
                    "                          c.conciliacion_tolerancia_tope))\n"
                    "      into v_tolerancia\n"
                    "      from public.cf_configuracion c\n"
                    "     where c.id = true;\n"
                    "    if v_tolerancia is null then\n"
                    "        raise exception 'TOLERANCIA_R16_NO_DISPONIBLE';\n"
                    "    end if;\n")
    return f


CABECERA = """-- Migracion 21 (Hito 2BA): R15 exclusividad de albaranes y R16 elegibilidad con
-- tolerancia proporcional. Generada por pruebas/auditoria_2ba/generar_migracion_21.py
-- a partir del texto exacto de la 20 (cf_persistir_conciliacion) y de la 14
-- (cf_evaluar_elegibilidad_conciliacion). No toca selector, ordering, normalizacion ni
-- filas existentes: el unico DML es la carga de la tabla nueva desde las conciliaciones
-- vigentes. Idempotente. Requiere la migracion 20.
begin;

do $$
begin
    if not exists (
        select 1 from information_schema.columns
         where table_schema = 'public' and table_name = 'cf_configuracion'
           and column_name = 'conciliacion_tolerancia_tope'
    ) then
        raise exception 'MIGRACION_20_AUSENTE';
    end if;
end;
$$;

-- R15: un albaran de Farmatic (farmacia, IdContador) solo puede estar reservado por una
-- linea de una conciliacion vigente. Solo escribe cf_persistir_conciliacion.
create table if not exists public.conciliacion_albaranes_reservados (
    albaran_farmacia text not null,
    albaran_id_contador bigint not null,
    factura_id uuid not null references public.facturas(id),
    conciliacion_id uuid not null references public.conciliaciones(id),
    orden integer not null,
    reservado_at timestamptz not null default now(),
    constraint conciliacion_albaranes_reservados_pkey
        primary key (albaran_farmacia, albaran_id_contador)
);
create index if not exists conciliacion_albaranes_reservados_factura_idx
    on public.conciliacion_albaranes_reservados (factura_id);
alter table public.conciliacion_albaranes_reservados enable row level security;
revoke all on table public.conciliacion_albaranes_reservados
    from public, anon, authenticated, service_role;
grant select on table public.conciliacion_albaranes_reservados to service_role;
comment on table public.conciliacion_albaranes_reservados is
    'R15 (2BA): albaranes de Farmatic que justifican una linea de una conciliacion vigente. Escritura solo via cf_persistir_conciliacion.';

-- Carga inicial desde las conciliaciones vigentes. Si dos lineas vigentes comparten
-- albaran, la clave primaria aborta la migracion (falla cerrado).
insert into public.conciliacion_albaranes_reservados
    (albaran_farmacia, albaran_id_contador, factura_id, conciliacion_id, orden)
select d.albaran_farmacia, d.albaran_id_contador, c.factura_id, c.id, d.orden
  from public.conciliaciones c
  join public.conciliacion_detalles d on d.conciliacion_id = c.id
 where c.es_actual and d.albaran_id_contador is not null
   and not exists (
       select 1 from public.conciliacion_albaranes_reservados r
        where r.conciliacion_id = c.id and r.orden = d.orden
   );

-- R15: cierre atomico de la 20 con validacion y mantenimiento de reservas.
"""

PRIVILEGIOS = """
-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta.
revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_evaluar_elegibilidad_conciliacion(uuid)
    from public, anon, authenticated;
grant execute on function public.cf_evaluar_elegibilidad_conciliacion(uuid)
    to service_role;

commit;
"""

ROLLBACK_SQL = """-- Rollback de la migracion 21 (Hito 2BA): devuelve el esquema exacto de la 20.
-- Primero el codigo, despues este SQL (solo con confirmacion de Pio).
begin;

-- cf_persistir_conciliacion: texto exacto de la migracion 20.
{persistir_20}
-- cf_evaluar_elegibilidad_conciliacion: texto exacto de la migracion 14.
{elegibilidad_14}
drop table if exists public.conciliacion_albaranes_reservados;

commit;
"""


def main() -> None:
    DESTINO.write_text(CABECERA + persistir_conciliacion_21()
                       + "\n-- R16: elegibilidad con tolerancia proporcional.\n" + elegibilidad_21()
                       + PRIVILEGIOS, encoding="utf-8", newline="\n")
    ROLLBACK.write_text(ROLLBACK_SQL.format(persistir_20=funcion(M20, "cf_persistir_conciliacion"),
                                            elegibilidad_14=funcion(M14, "cf_evaluar_elegibilidad_conciliacion")),
                        encoding="utf-8", newline="\n")
    print(DESTINO.name, ROLLBACK.name)


if __name__ == "__main__":
    main()
