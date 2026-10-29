"""Hito 2BE: genera de forma determinista la migracion 24 (R17) y su rollback.

Uso: python -B pruebas/auditoria_2be/generar_migracion_24.py

- ``cf_persistir_conciliacion`` de la 24 sale del texto EXACTO de la migracion 22 (la 23 no lo
  cambia) con dos reemplazos comprobados unicos: R11 cuenta una linea R17 como un albaran casado y,
  tras el rechazo de albaranes ausentes, cada linea ``UNO_A_VARIOS`` se revalida con
  ``cf_linea_r17_valida``.
- El rollback reinstala el texto exacto de la 22 y elimina la auxiliar: rollback == estado 23.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql/migrations"
M22 = MIG / "22_cf_resincronizacion_albaranes.sql"
DESTINO = MIG / "24_cf_r17_recepcion.sql"
ROLLBACK = MIG / "24_cf_r17_recepcion.rollback.sql"

DETALLES = "jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d"


def funcion(path: Path, nombre: str) -> str:
    texto = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    inicio = texto.index(f"create or replace function public.{nombre}(")
    fin = texto.index("$$;\n", texto.index("as $$", inicio) + 5) + 4
    return texto[inicio:fin]


def _reemplazar(texto: str, viejo: str, nuevo: str) -> str:
    assert texto.count(viejo) == 1, viejo
    return texto.replace(viejo, nuevo)


def persistir_conciliacion_24() -> str:
    f = funcion(M22, "cf_persistir_conciliacion")
    f = _reemplazar(
        f,
        "    select count(*) into v_casados\n"
        f"      from {DETALLES}\n"
        "     where d->>'tipo_relacion' = 'UNO_A_UNO';\n",
        "    -- R17 (2BE): una linea UNO_A_VARIOS (dos detalles) cuenta como un albaran casado.\n"
        "    select count(*) filter (where d->>'tipo_relacion' = 'UNO_A_UNO')\n"
        "           + count(distinct d->>'factura_albaran_extraido_id')\n"
        "                 filter (where d->>'tipo_relacion' = 'UNO_A_VARIOS')\n"
        "      into v_casados\n"
        f"      from {DETALLES};\n")
    ancla = ("    if v_conflicto is not null then\n"
             "        raise exception 'ALBARAN_AUSENTE_EN_FARMATIC:%', v_conflicto;\n"
             "    end if;\n")
    return _reemplazar(f, ancla, ancla +
                       "    -- R17 (2BE): cada linea UNO_A_VARIOS es exactamente una pareja R17, revalidada aqui.\n"
                       "    select coalesce(g.linea, 'SIN_ORIGEN')\n"
                       "      into v_conflicto\n"
                       "      from (select d->>'factura_albaran_extraido_id' as linea, jsonb_agg(d) as detalles\n"
                       f"              from {DETALLES}\n"
                       "             where d->>'tipo_relacion' = 'UNO_A_VARIOS'\n"
                       "             group by 1) g\n"
                       "     where not public.cf_linea_r17_valida(f.id, g.linea, g.detalles,\n"
                       "                                          coalesce(p_resultado->'detalles', '[]'::jsonb))\n"
                       "     limit 1;\n"
                       "    if v_conflicto is not null then\n"
                       "        raise exception 'LINEA_R17_NO_VALIDA:%', v_conflicto;\n"
                       "    end if;\n")


CABECERA = """-- Migracion 24 (Hito 2BE): R17, linea PDF = albaran de su numero + 1 interno de la misma recepcion.
-- Generada por pruebas/auditoria_2be/generar_migracion_24.py a partir del texto exacto de la 22
-- (cf_persistir_conciliacion; la 23 no lo cambia). Una linea R17 se persiste como dos detalles
-- UNO_A_VARIOS con el mismo origen documental; ambos albaranes quedan reservados (R15, sin cambios).
-- La BD revalida la pareja y R11 cuenta la linea como un albaran casado. No modifica filas
-- existentes. Idempotente. Requiere la 23.
begin;

do $$
begin
    if to_regclass('public.albaranes_aprobaciones') is null
       or to_regprocedure('public.cf_albaran_ausente_abierto(text,bigint)') is null then
        raise exception 'MIGRACION_23_AUSENTE';
    end if;
end;
$$;

-- R17 (aprobada por Pio): la linea documental (cargo) se explica con exactamente dos albaranes de la
-- MISMA recepcion: el de su numero (exacto o letra final 08X99999A) y uno con numeracion interna de
-- Farmatic ([A-Z]999999/9999); mismo proveedor (R9); cada detalle aplica el PUC de su albaran y la
-- suma cae dentro de la tolerancia por linea (0,05). La linea no tiene otros detalles.
create or replace function public.cf_linea_r17_valida(
    p_factura_id uuid,
    p_linea text,
    p_detalles jsonb,
    p_todos jsonb
)
returns boolean
language plpgsql
stable
set search_path = public
as $$
declare
    e public.facturas_albaranes_extraidos%rowtype;
    a public.albaranes%rowtype;
    b public.albaranes%rowtype;
    v_n integer;
    v_internos integer;
    v_doc text;
    v_op text;
begin
    if p_linea is null or p_linea !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
       or jsonb_typeof(p_detalles) <> 'array' or jsonb_array_length(p_detalles) <> 2 then
        return false;
    end if;
    select * into e from public.facturas_albaranes_extraidos where id = p_linea::uuid;
    if e.id is null or e.factura_id <> p_factura_id or e.importe_total is null
       or e.tipo_movimiento is distinct from 'CARGO' then
        return false;
    end if;
    select count(*) into v_n
      from jsonb_array_elements(p_todos) d
     where d->>'factura_albaran_extraido_id' = p_linea;
    if v_n <> 2 then
        return false;
    end if;
    -- Cada detalle: un albaran existente con PUC y el PUC como importe aplicado.
    select count(*), count(*) filter (where upper(btrim(x.numero_albaran)) ~ '^[A-Z][0-9]{6}/[0-9]{4}$')
      into v_n, v_internos
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where x.importe_puc is not null
       and (d->>'importe_aplicado')::numeric = x.importe_puc;
    if v_n <> 2 or v_internos <> 1 then
        return false;
    end if;
    select x.* into a
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where upper(btrim(x.numero_albaran)) !~ '^[A-Z][0-9]{6}/[0-9]{4}$';
    select x.* into b
      from jsonb_array_elements(p_detalles) d
      join public.albaranes x
        on x.farmacia = d->>'albaran_farmacia'
       and x.id_contador = nullif(d->>'albaran_id_contador', '')::bigint
     where upper(btrim(x.numero_albaran)) ~ '^[A-Z][0-9]{6}/[0-9]{4}$';
    if a.id_contador = b.id_contador or a.farmacia <> b.farmacia
       or a.id_recepcion is null or a.id_recepcion is distinct from b.id_recepcion
       or public.cf_id_proveedor_comparable(a.id_proveedor)
          is distinct from public.cf_id_proveedor_comparable(b.id_proveedor) then
        return false;
    end if;
    -- El albaran de su numero: exacto o letra final (normalizados como en conciliacion.py).
    v_doc := regexp_replace(upper(coalesce(e.numero_albaran, '')), '[^A-Z0-9]', '', 'g');
    v_op := regexp_replace(upper(a.numero_albaran), '[^A-Z0-9]', '', 'g');
    if v_doc = '' or not (v_op = v_doc or (v_op ~ '^08[A-Z][0-9]{5}[A-Z]$' and left(v_op, 8) = v_doc)) then
        return false;
    end if;
    return abs(a.importe_puc + b.importe_puc - e.importe_total) <= 0.0500;
end;
$$;

"""

PRIVILEGIOS = """
-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta la RPC.
revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;
-- Auxiliar: solo el propietario (la usa la funcion SECURITY DEFINER).
revoke all on function public.cf_linea_r17_valida(uuid, text, jsonb, jsonb)
    from public, anon, authenticated, service_role;

commit;
"""

ROLLBACK_SQL = """-- Rollback de la migracion 24 (Hito 2BE): devuelve el esquema exacto de la 23.
-- Solo con confirmacion de Pio. Las conciliaciones y reservas ya persistidas se conservan.
begin;

-- cf_persistir_conciliacion: texto exacto de la migracion 22 (vigente en la 23).
{persistir_22}
drop function if exists public.cf_linea_r17_valida(uuid, text, jsonb, jsonb);

revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;

commit;
"""


def main() -> None:
    DESTINO.write_text(CABECERA + persistir_conciliacion_24() + PRIVILEGIOS, encoding="utf-8", newline="\n")
    ROLLBACK.write_text(ROLLBACK_SQL.format(persistir_22=funcion(M22, "cf_persistir_conciliacion")),
                        encoding="utf-8", newline="\n")
    print(DESTINO.name, ROLLBACK.name)


if __name__ == "__main__":
    main()
