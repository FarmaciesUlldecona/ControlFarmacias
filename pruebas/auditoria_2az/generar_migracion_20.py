"""Hito 2AZ: genera de forma determinista la migracion 20 y su rollback.

Uso: python -B pruebas/auditoria_2az/generar_migracion_20.py

``cf_persistir_conciliacion`` de la 20 se obtiene del texto EXACTO de la migracion
18 con insercion de los bloques R11 (cada reemplazo se comprueba unico). El
rollback reinstala el texto exacto de la 18, de modo que rollback == estado 19.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql/migrations"
M18 = MIG / "18_cf_conciliacion_manual_atomica.sql"
DESTINO = MIG / "20_cf_alliance_tolerancia_enriquecimiento.sql"
ROLLBACK = MIG / "20_cf_alliance_tolerancia_enriquecimiento.rollback.sql"


def funcion_18(nombre: str) -> str:
    texto = M18.read_text(encoding="utf-8").replace("\r\n", "\n")
    inicio = texto.index(f"create or replace function public.{nombre}(")
    fin = texto.index("$$;\n", texto.index("as $$", inicio) + 5) + 4
    return texto[inicio:fin]


def _reemplazar(texto: str, viejo: str, nuevo: str) -> str:
    assert texto.count(viejo) == 1, viejo
    return texto.replace(viejo, nuevo)


def persistir_conciliacion_20() -> str:
    f = funcion_18("cf_persistir_conciliacion")
    f = _reemplazar(f, "    v_clase text;\nbegin\n",
                    "    v_clase text;\n"
                    "    -- R11 (2AZ)\n"
                    "    v_casados integer;\n"
                    "    v_suelo numeric;\n"
                    "    v_por_albaran numeric;\n"
                    "    v_tope numeric;\n"
                    "    v_tolerancia numeric;\n"
                    "    v_regla jsonb;\n"
                    "begin\n")
    f = _reemplazar(f, "        raise exception 'DISPARADOR_NO_COINCIDE_CON_CLAIM';\n    end if;\n",
                    "        raise exception 'DISPARADOR_NO_COINCIDE_CON_CLAIM';\n    end if;\n\n"
                    "    -- R11 (2AZ): la tolerancia aplicada debe ser la proporcional calculada aqui\n"
                    "    -- con los albaranes casados (UNO_A_UNO) y los parametros de cf_configuracion.\n"
                    "    select count(*) into v_casados\n"
                    "      from jsonb_array_elements(coalesce(p_resultado->'detalles', '[]'::jsonb)) d\n"
                    "     where d->>'tipo_relacion' = 'UNO_A_UNO';\n"
                    "    select conciliacion_tolerancia_suelo, conciliacion_tolerancia_por_albaran,\n"
                    "           conciliacion_tolerancia_tope\n"
                    "      into v_suelo, v_por_albaran, v_tope\n"
                    "      from public.cf_configuracion where id = true;\n"
                    "    v_tolerancia := greatest(v_suelo, least(v_por_albaran * v_casados, v_tope));\n"
                    "    if (p_resultado->>'tolerancia') is null\n"
                    "       or (p_resultado->>'tolerancia')::numeric <> v_tolerancia then\n"
                    "        raise exception 'TOLERANCIA_NO_COINCIDE_CON_R11';\n"
                    "    end if;\n"
                    "    if p_resultado ? 'tolerancia_regla' and (\n"
                    "           (p_resultado #>> '{tolerancia_regla,suelo}')::numeric is distinct from v_suelo\n"
                    "        or (p_resultado #>> '{tolerancia_regla,por_albaran}')::numeric is distinct from v_por_albaran\n"
                    "        or (p_resultado #>> '{tolerancia_regla,tope}')::numeric is distinct from v_tope\n"
                    "        or (p_resultado #>> '{tolerancia_regla,albaranes_casados}')::integer is distinct from v_casados\n"
                    "    ) then\n"
                    "        raise exception 'TOLERANCIA_REGLA_NO_COINCIDE';\n"
                    "    end if;\n"
                    "    if (v_resultado = 'CONCILIADA' and abs((p_resultado->>'diferencia')::numeric) > v_tolerancia)\n"
                    "       or (v_resultado = 'DIFERENCIA' and abs((p_resultado->>'diferencia')::numeric) <= v_tolerancia) then\n"
                    "        raise exception 'RESULTADO_INCOHERENTE_CON_TOLERANCIA';\n"
                    "    end if;\n"
                    "    v_regla := jsonb_build_object('suelo', v_suelo, 'por_albaran', v_por_albaran, 'tope', v_tope,\n"
                    "                                  'albaranes_casados', v_casados, 'tolerancia', v_tolerancia);\n")
    f = _reemplazar(f, "                           'resultado_hash', encode(extensions.digest(p_resultado::text, 'sha256'), 'hex')),\n",
                    "                           'resultado_hash', encode(extensions.digest(p_resultado::text, 'sha256'), 'hex'),\n"
                    "                           'tolerancia_regla', v_regla),\n")
    f = _reemplazar(f, "                           'intentos_fallo', v_fallos, 'max_intentos', v_max)\n    );\n    return v_id;\n",
                    "                           'intentos_fallo', v_fallos, 'max_intentos', v_max,\n"
                    "                           'albaranes_casados', v_casados)\n    );\n    return v_id;\n")
    return f


ENRIQUECER = r"""create or replace function public.cf_enriquecer_factura(
    p_factura_id uuid,
    p_worker_id text,
    p_idempotency_key text,
    p_enriquecimiento jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    f public.facturas%rowtype;
    v_hash_archivo text;
    v_hash text;
    v_previo jsonb;
    v_ident jsonb;
    v_cif text;
    v_prov jsonb;
    v_item jsonb;
    v_orden integer;
    v_n integer;
    v_venc_id uuid;
    v_venc_importe numeric;
    v_albaranes integer := 0;
    v_movimientos integer := 0;
    v_vencimientos integer := 0;
begin
    if nullif(btrim(p_worker_id), '') is null or nullif(btrim(p_idempotency_key), '') is null then
        raise exception 'worker_id e idempotency_key obligatorios';
    end if;
    if p_idempotency_key not like 'enriquecimiento:' || p_factura_id::text || ':%' then
        raise exception 'IDEMPOTENCY_KEY_NO_VALIDA';
    end if;
    if p_enriquecimiento is null or jsonb_typeof(p_enriquecimiento) <> 'object' then
        raise exception 'ENRIQUECIMIENTO_INVALIDO';
    end if;
    v_hash := encode(extensions.digest(p_enriquecimiento::text, 'sha256'), 'hex');
    v_ident := coalesce(p_enriquecimiento->'identidad', '{}'::jsonb);

    select * into f from public.facturas where id = p_factura_id for update;
    if f.id is null then
        raise exception 'factura no encontrada';
    end if;
    if not exists (
        select 1 from public.cf_configuracion c
         where c.id = true and f.farmacia = any(c.farmacias_habilitadas)
    ) then
        raise exception 'FARMACIA_NO_HABILITADA';
    end if;

    -- Replay: misma clave y mismo contenido -> sin ninguna escritura.
    select h.detalle into v_previo
      from public.historial_facturas h
     where h.factura_id = f.id and h.evento = 'FACTURA_ENRIQUECIDA'
       and h.detalle->>'idempotency_key' = p_idempotency_key
     order by h.id desc
     limit 1;
    if v_previo is not null then
        if v_previo->>'payload_sha256' is distinct from v_hash then
            raise exception 'IDEMPOTENCY_KEY_REUTILIZADA';
        end if;
        return jsonb_build_object('replay', true, 'factura_id', f.id, 'idempotency_key', p_idempotency_key);
    end if;

    if f.estado_conciliacion_cf = 'CONCILIADA' then
        raise exception 'FACTURA_YA_CONCILIADA';
    end if;
    if f.estado_conciliacion_cf <> 'PENDIENTE_CONCILIAR' then
        raise exception 'FACTURA_EN_REVISION_CONCILIACION';
    end if;
    if f.conciliacion_bloqueado_por is not null
       and (f.conciliacion_bloqueado_hasta is null or f.conciliacion_bloqueado_hasta > now()) then
        raise exception 'FACTURA_RECLAMADA_EN_CONCILIACION';
    end if;

    -- Mismo documento origen, mismo SHA e identidad economica identica.
    if p_enriquecimiento->>'documento_id' is distinct from f.documento_id::text then
        raise exception 'DOCUMENTO_NO_COINCIDE';
    end if;
    select archivo_hash into v_hash_archivo from public.documentos_facturas where id = f.documento_id;
    if v_hash_archivo is null or v_hash_archivo is distinct from p_enriquecimiento->>'archivo_hash' then
        raise exception 'SHA_NO_COINCIDE';
    end if;
    if v_ident->>'numero_factura' is distinct from f.numero_factura then
        raise exception 'IDENTIDAD_NO_COINCIDE:numero_factura';
    end if;
    if nullif(v_ident->>'fecha_factura', '')::date is distinct from f.fecha_factura then
        raise exception 'IDENTIDAD_NO_COINCIDE:fecha_factura';
    end if;
    if nullif(v_ident->>'importe_total', '')::numeric is distinct from f.importe_total then
        raise exception 'IDENTIDAD_NO_COINCIDE:importe_total';
    end if;
    v_cif := regexp_replace(upper(coalesce(nullif(f.proveedor_cif, ''),
                                           f.datos_extraidos #>> '{proveedor,nif,valor}', '')), '[^A-Z0-9]', '', 'g');
    if v_cif = '' or regexp_replace(upper(coalesce(v_ident->>'proveedor_cif', '')), '[^A-Z0-9]', '', 'g') <> v_cif then
        raise exception 'IDENTIDAD_NO_COINCIDE:proveedor_cif';
    end if;
    if v_ident->>'identidad_economica_clave' is null
       or v_ident->>'identidad_economica_clave' is distinct from f.datos_extraidos->>'identidad_economica_clave' then
        raise exception 'IDENTIDAD_NO_COINCIDE:identidad_economica_clave';
    end if;

    v_prov := jsonb_build_object('idempotency_key', p_idempotency_key, 'worker_id', p_worker_id,
                                 'normalizador_version', p_enriquecimiento->>'normalizador_version',
                                 'enriquecido_at', now());

    -- Albaranes: solo filas nuevas (mapeo identico al de la migracion 17).
    select coalesce(max(orden), 0) into v_orden
      from public.facturas_albaranes_extraidos where factura_id = f.id;
    for v_item in select value from jsonb_array_elements(coalesce(p_enriquecimiento->'albaranes', '[]'::jsonb)) loop
        if nullif(btrim(v_item #>> '{numero,valor}'), '') is null then
            raise exception 'ALBARAN_SIN_NUMERO';
        end if;
        if exists (
            select 1 from public.facturas_albaranes_extraidos a
             where a.factura_id = f.id
               and regexp_replace(upper(a.numero_albaran), '[^A-Z0-9]', '', 'g')
                 = regexp_replace(upper(v_item #>> '{numero,valor}'), '[^A-Z0-9]', '', 'g')
        ) then
            raise exception 'ALBARAN_YA_PRESENTE:%', v_item #>> '{numero,valor}';
        end if;
        v_orden := v_orden + 1;
        insert into public.facturas_albaranes_extraidos
            (factura_id, numero_albaran, fecha_albaran, tipo_movimiento,
             importe_base, importe_total, descripcion, orden, literal, provenance)
        values (f.id, v_item #>> '{numero,valor}',
            nullif(v_item #>> '{fecha,valor,iso}', '')::date, v_item->>'sentido',
            nullif(v_item #>> '{importe_base,valor}', '')::numeric,
            nullif(v_item #>> '{importe_total,valor}', '')::numeric,
            v_item #>> '{tipo_pedido,valor}', v_orden,
            v_item #>> '{numero,literal}', v_item || jsonb_build_object('enriquecimiento', v_prov));
        v_albaranes := v_albaranes + 1;
    end loop;

    -- Movimientos: solo en facturas MIXTA (cambiar la naturaleza modificaria la factura).
    if jsonb_array_length(coalesce(p_enriquecimiento->'movimientos', '[]'::jsonb)) > 0
       and coalesce(f.datos_extraidos->>'naturaleza_principal', '') <> 'MIXTA' then
        raise exception 'MOVIMIENTOS_REQUIEREN_NATURALEZA_MIXTA';
    end if;
    select coalesce(max(orden), 0) into v_orden
      from public.facturas_movimientos where factura_id = f.id;
    for v_item in select value from jsonb_array_elements(coalesce(p_enriquecimiento->'movimientos', '[]'::jsonb)) loop
        if exists (
            select 1 from public.facturas_movimientos m
             where m.factura_id = f.id
               and upper(btrim(m.descripcion_literal)) = upper(btrim(v_item #>> '{descripcion_literal,valor}'))
               and m.sentido is not distinct from v_item->>'sentido'
               and m.importe is not distinct from nullif(v_item #>> '{importe,valor}', '')::numeric
        ) then
            raise exception 'MOVIMIENTO_YA_PRESENTE:%', v_item #>> '{descripcion_literal,valor}';
        end if;
        v_orden := v_orden + 1;
        insert into public.facturas_movimientos
            (factura_id, normalizacion_ejecucion_id, orden, categoria,
             descripcion_literal, sentido, base, iva, recargo_equivalencia,
             importe, provenance)
        values (f.id, null, v_orden,
            case v_item->>'tipo'
                when 'SERVICIO' then 'SERVICIO'
                when 'DESCUENTO' then 'DESCUENTO'
                when 'DEVOLUCION_MERCANCIA' then 'DEVOLUCION'
                when 'CONDICION_COMERCIAL' then 'CONDICION_COMERCIAL'
                else 'OTRO' end,
            v_item #>> '{descripcion_literal,valor}', v_item->>'sentido',
            nullif(v_item #>> '{base,valor}', '')::numeric,
            nullif(v_item #>> '{iva,valor}', '')::numeric,
            nullif(v_item #>> '{recargo_equivalencia,valor}', '')::numeric,
            nullif(v_item #>> '{importe,valor}', '')::numeric,
            v_item || jsonb_build_object('enriquecimiento', v_prov));
        v_movimientos := v_movimientos + 1;
    end loop;

    -- Vencimientos: solo rellena importes NULL; nunca sobrescribe un valor no nulo.
    for v_item in select value from jsonb_array_elements(coalesce(p_enriquecimiento->'vencimientos', '[]'::jsonb)) loop
        if nullif(v_item #>> '{importe,valor}', '') is null then
            raise exception 'VENCIMIENTO_SIN_IMPORTE';
        end if;
        select count(*) into v_n
          from public.facturas_vencimientos v
         where v.factura_id = f.id
           and v.fecha_vencimiento = nullif(v_item #>> '{fecha,valor,iso}', '')::date;
        if v_n <> 1 then
            raise exception 'VENCIMIENTO_NO_LOCALIZADO:%', v_item #>> '{fecha,valor,iso}';
        end if;
        select v.id, v.importe into v_venc_id, v_venc_importe
          from public.facturas_vencimientos v
         where v.factura_id = f.id
           and v.fecha_vencimiento = nullif(v_item #>> '{fecha,valor,iso}', '')::date;
        if v_venc_importe is not null then
            raise exception 'VENCIMIENTO_CON_IMPORTE_EXISTENTE:%', v_item #>> '{fecha,valor,iso}';
        end if;
        update public.facturas_vencimientos
           set importe = (v_item #>> '{importe,valor}')::numeric,
               provenance = coalesce(provenance, '{}'::jsonb)
                   || jsonb_build_object('enriquecimiento_importe', v_prov || jsonb_build_object('importe', v_item->'importe'))
         where id = v_venc_id and importe is null;
        v_vencimientos := v_vencimientos + 1;
    end loop;

    if v_albaranes + v_movimientos + v_vencimientos = 0 then
        raise exception 'SIN_FILAS_NUEVAS';
    end if;

    insert into public.historial_facturas
        (documento_id, factura_id, evento, origen, actor, estado_nuevo, detalle)
    values (
        f.documento_id, f.id, 'FACTURA_ENRIQUECIDA', 'RPC', p_worker_id,
        jsonb_build_object('albaranes_anadidos', v_albaranes, 'movimientos_anadidos', v_movimientos,
                           'vencimientos_rellenados', v_vencimientos),
        jsonb_build_object('idempotency_key', p_idempotency_key, 'payload_sha256', v_hash,
                           'normalizador_version', p_enriquecimiento->>'normalizador_version',
                           'worker_id', p_worker_id)
    );
    return jsonb_build_object('replay', false, 'factura_id', f.id,
                              'albaranes_anadidos', v_albaranes, 'movimientos_anadidos', v_movimientos,
                              'vencimientos_rellenados', v_vencimientos);
end;
$$;
"""

CABECERA = """-- Migracion 20 (Hito 2AZ): R11 tolerancia proporcional de conciliacion y R12
-- enriquecimiento de facturas persistidas. Generada por
-- pruebas/auditoria_2az/generar_migracion_20.py a partir del texto exacto de la 18.
-- No toca selector, ordering ni elegibilidad. Sin DML sobre filas existentes
-- (solo defaults de columnas nuevas en cf_configuracion). Idempotente.
begin;

-- R11: parametros protegidos por check.
alter table public.cf_configuracion
    add column if not exists conciliacion_tolerancia_suelo numeric(14,4) not null default 0.0500,
    add column if not exists conciliacion_tolerancia_por_albaran numeric(14,4) not null default 0.0100,
    add column if not exists conciliacion_tolerancia_tope numeric(14,4) not null default 0.5000;
alter table public.cf_configuracion
    drop constraint if exists cf_configuracion_tolerancia_r11_check;
alter table public.cf_configuracion
    add constraint cf_configuracion_tolerancia_r11_check check (
        conciliacion_tolerancia_suelo > 0
        and conciliacion_tolerancia_suelo <= conciliacion_tolerancia_tope
        and conciliacion_tolerancia_tope <= 1.0000
        and conciliacion_tolerancia_por_albaran >= 0
        and conciliacion_tolerancia_por_albaran <= 0.0500
    );

-- R11: cierre atomico de la 18 con validacion y registro de la tolerancia aplicada.
"""

PRIVILEGIOS = """
-- Privilegios: SECURITY DEFINER, owner postgres; solo service_role ejecuta.
revoke all on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_conciliacion(uuid, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_enriquecer_factura(uuid, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_enriquecer_factura(uuid, text, text, jsonb)
    to service_role;

comment on function public.cf_enriquecer_factura(uuid, text, text, jsonb) is
    'R12: anade albaranes/movimientos no promovidos y rellena importes de vencimiento NULL de una factura no conciliada. Idempotente; nunca modifica filas ni importes existentes.';

commit;
"""

ROLLBACK_SQL = """-- Rollback de la migracion 20 (Hito 2AZ): devuelve el esquema exacto de la 19.
-- Primero el codigo, despues este SQL (solo con confirmacion de Pio).
begin;

drop function if exists public.cf_enriquecer_factura(uuid, text, text, jsonb);

-- cf_persistir_conciliacion: texto exacto de la migracion 18.
{funcion_18}
alter table public.cf_configuracion
    drop constraint if exists cf_configuracion_tolerancia_r11_check;
alter table public.cf_configuracion
    drop column if exists conciliacion_tolerancia_suelo,
    drop column if exists conciliacion_tolerancia_por_albaran,
    drop column if exists conciliacion_tolerancia_tope;

commit;
"""


def main() -> None:
    DESTINO.write_text(CABECERA + persistir_conciliacion_20() + "\n-- R12: enriquecimiento.\n" + ENRIQUECER
                       + PRIVILEGIOS, encoding="utf-8", newline="\n")
    ROLLBACK.write_text(ROLLBACK_SQL.format(funcion_18=funcion_18("cf_persistir_conciliacion")),
                        encoding="utf-8", newline="\n")
    print(DESTINO.name, ROLLBACK.name)


if __name__ == "__main__":
    main()
