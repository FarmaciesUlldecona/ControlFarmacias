"""Hito 2BK: genera la migracion 26 y su rollback a partir del texto exacto de las migraciones 15 y 17.

La 26 conserva la logica de la persistencia multifactura y cambia solo dos cosas:
- la busqueda de otras versiones de la misma factura usa un indice de expresion sobre la misma funcion de
  identidad del bucle (``cf_componentes_identidad_factura(datos_extraidos))[1:4]``) en vez de leer
  ``datos_extraidos`` de toda la tabla; mismo orden de visita (``order by ctid``, el de la lectura secuencial);
- la ejecucion se escribe una sola vez, ya con la lectura completa, el inventario y el modo de ejecucion (antes:
  insercion y dos actualizaciones del mismo ``resultado_json``).
Cada sustitucion se comprueba (exactamente una aparicion). El rollback reproduce literalmente las funciones de
la 15 y la 17. Uso: python -B pruebas/auditoria_2bk/generar_migracion_26.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql/migrations"
DESTINO = MIG / "26_cf_persistencia_multifactura_indexada.sql"
ROLLBACK = MIG / "26_cf_persistencia_multifactura_indexada.rollback.sql"


def _lineas(nombre: str, desde: int, hasta: int, primera: str) -> str:
    lineas = (MIG / nombre).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    bloque = "\n".join(lineas[desde - 1:hasta])
    if not bloque.startswith(primera) or not bloque.endswith("$$;"):
        raise SystemExit(f"LIMITES_INESPERADOS:{nombre}:{desde}-{hasta}")
    return bloque


def _sustituir(texto: str, viejo: str, nuevo: str) -> str:
    if texto.count(viejo) != 1:
        raise SystemExit(f"SUSTITUCION_NO_UNICA:{viejo[:60]!r}:{texto.count(viejo)}")
    return texto.replace(viejo, nuevo)


MULTIFACTURA_15 = _lineas("15_cf_multifactura.sql", 49, 180,
                          "create or replace function public.cf_persistir_documento_multifactura(")
NORMALIZACION_17 = _lineas("17_cf_replay_y_fallos_no_bloqueantes.sql", 121, 394,
                           "create or replace function public.cf_persistir_normalizacion(")
ENVOLTORIO_17 = _lineas("17_cf_replay_y_fallos_no_bloqueantes.sql", 397, 449,
                        "create or replace function public.cf_persistir_documento_multifactura(")


def nucleo_normalizacion() -> str:
    texto = _sustituir(NORMALIZACION_17, "function public.cf_persistir_normalizacion(",
                       "function public.cf_persistir_normalizacion_nucleo(")
    texto = _sustituir(texto, "    p_resultado jsonb\n)", "    p_resultado jsonb,\n    p_resultado_json_guardado jsonb\n)")
    return _sustituir(texto, "        v_documento_normalizado, p_worker_id, now(), now()",
                      "        coalesce(p_resultado_json_guardado, v_documento_normalizado), p_worker_id, now(), now()")


def nucleo_multifactura() -> str:
    texto = _sustituir(MULTIFACTURA_15, "function public.cf_persistir_documento_multifactura(",
                       "function public.cf_persistir_documento_multifactura_nucleo(")
    texto = _sustituir(texto, "p_resultado jsonb, p_segmentos_autorizados text[]\n)",
                       "p_resultado jsonb, p_segmentos_autorizados text[],\n    p_disparador text\n)")
    texto = _sustituir(
        texto,
        "        for otra in select id,documento_id,datos_extraidos from public.facturas loop\n",
        "        -- 26: solo las filas con el mismo nucleo de identidad (indice de expresion), en el orden de la\n"
        "        -- lectura secuencial; las demas nunca cumplian la condicion de abajo.\n"
        "        for otra in select id,documento_id,datos_extraidos from public.facturas\n"
        "            where (public.cf_componentes_identidad_factura(datos_extraidos))[1:4]=partes[1:4]\n"
        "            order by ctid loop\n")
    return _sustituir(
        texto,
        "    ejecucion:=public.cf_persistir_normalizacion(d.id,p_worker_id,'MANUAL',p_idempotency_key,p_resultado_hash,\n"
        "        jsonb_build_object('resultado_json',payload,'uso_luna',false,'uso_ocr',false));\n"
        "    -- Guardar lectura completa e inventario, no solo el subconjunto economico elegido.\n"
        "    update public.normalizacion_ejecuciones set resultado_json=p_resultado || jsonb_build_object(\n"
        "        'multifactura',jsonb_build_object('firma_solicitud',firma,'segmentos_autorizados',"
        "to_jsonb(p_segmentos_autorizados)))\n"
        "      where id=ejecucion;\n",
        "    -- Guardar lectura completa e inventario, no solo el subconjunto economico elegido.\n"
        "    -- 26: una sola escritura de la ejecucion, con el modo de ejecucion del envoltorio de 7 parametros.\n"
        "    ejecucion:=public.cf_persistir_normalizacion_nucleo(d.id,p_worker_id,coalesce(p_disparador,'MANUAL'),\n"
        "        p_idempotency_key,p_resultado_hash,\n"
        "        jsonb_build_object('resultado_json',payload,'uso_luna',false,'uso_ocr',false),\n"
        "        p_resultado || jsonb_build_object(\n"
        "        'multifactura',jsonb_build_object('firma_solicitud',firma,'segmentos_autorizados',"
        "to_jsonb(p_segmentos_autorizados)))\n"
        "        || case when p_disparador is null then '{}'::jsonb else jsonb_build_object('provenance_ejecucion',\n"
        "           jsonb_build_object('modo_ejecucion',p_disparador)) end);\n")


CABECERA = """\
-- Migracion 26 (Hito 2BK): persistencia multifactura sin recorrer facturas.datos_extraidos.
-- Generada por pruebas/auditoria_2bk/generar_migracion_26.py a partir del texto de la 15 y la 17.
-- En produccion la RPC multifactura supero el statement_timeout de 8 s (Alliance de 4 facturas, serie 2BJ):
-- por cada factura del documento se leia y descomprimia datos_extraidos de toda la tabla facturas, coste
-- que crece con cada documento. Cambios, con el mismo resultado que la 17:
-- - indice de expresion sobre la misma funcion de identidad del bucle; el bucle solo visita las filas con
--   el mismo nucleo [1:4], en el orden de la lectura secuencial (order by ctid); la funcion declara su coste
--   real para que el planificador use el indice;
-- - la ejecucion se escribe una sola vez (antes: insercion y dos actualizaciones de resultado_json).
-- cf_persistir_normalizacion y las dos firmas de cf_persistir_documento_multifactura delegan en dos nucleos
-- internos (solo propietario). Firmas, privilegios de las RPC y filas existentes no cambian.
-- Si se redefine cf_componentes_identidad_factura hay que reconstruir el indice (REINDEX).
-- Requiere la 25. Diseno: pruebas/auditoria_2bk/DISENO.md.
begin;

do $$
begin
    if to_regprocedure('public.cf_recuperar_claim_huerfano_normalizacion(uuid,text,interval)') is null then
        raise exception 'MIGRACION_25_AUSENTE';
    end if;
end;
$$;

create index if not exists facturas_identidad_nucleo_idx
    on public.facturas (((public.cf_componentes_identidad_factura(datos_extraidos))[1:4]));

-- Con el coste por defecto (100) el planificador recorre la tabla y descomprime datos_extraidos de cada fila
-- (perfil 2BK: 1,5-1,8 s por factura con 54 facturas). Coste declarado acorde: solo cambia el plan.
alter function public.cf_componentes_identidad_factura(jsonb) cost 10000;
"""

ENVOLTORIOS = """\
-- RPC de un documento (12/17): misma firma y comportamiento; delega en el nucleo.
create or replace function public.cf_persistir_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_resultado_hash text,
    p_resultado jsonb
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
begin
    return public.cf_persistir_normalizacion_nucleo(
        p_documento_id, p_worker_id, p_disparador, p_idempotency_key, p_resultado_hash, p_resultado, null);
end;
$$;

-- Firma de 6 parametros (15): sin modo de ejecucion, como antes; solo propietario desde la 16.
create or replace function public.cf_persistir_documento_multifactura(
    p_documento_id uuid, p_worker_id text, p_idempotency_key text,
    p_resultado_hash text, p_resultado jsonb, p_segmentos_autorizados text[]
)
returns uuid language plpgsql security definer set search_path=public as $$
begin
    return public.cf_persistir_documento_multifactura_nucleo(
        p_documento_id, p_worker_id, p_idempotency_key, p_resultado_hash, p_resultado,
        p_segmentos_autorizados, null);
end;
$$;

-- R1 en el envoltorio multifactura de 7 parametros (17): el modo de ejecucion viaja al nucleo y se guarda
-- en la misma insercion de la ejecucion.
create or replace function public.cf_persistir_documento_multifactura(
    p_documento_id uuid,
    p_worker_id text,
    p_idempotency_key text,
    p_resultado_hash text,
    p_resultado jsonb,
    p_segmentos_autorizados text[],
    p_disparador text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    v_previa uuid;
    v_ejecucion uuid;
begin
    if p_disparador not in ('AUTOMATICO', 'REPROCESADO', 'MANUAL_ONE_SHOT') then
        raise exception 'DISPARADOR_MULTIFACTURA_NO_ADMITIDO';
    end if;
    -- Mismo candado que la RPC certificada: la deteccion de replay es serializada.
    perform pg_advisory_xact_lock(2151501);
    select id into v_previa
      from public.normalizacion_ejecuciones
     where documento_id = p_documento_id and idempotency_key = p_idempotency_key;

    v_ejecucion := public.cf_persistir_documento_multifactura_nucleo(
        p_documento_id,
        p_worker_id,
        p_idempotency_key,
        p_resultado_hash,
        p_resultado,
        p_segmentos_autorizados,
        p_disparador
    );

    if v_previa is not null then
        perform public.cf_cerrar_replay_normalizacion(
            p_documento_id, p_worker_id, v_ejecucion, 'MULTIFACTURA');
    end if;
    return v_ejecucion;
end;
$$;
"""

PRIVILEGIOS = """\
-- Privilegios (patron 25): owner postgres; nucleos solo propietario; las RPC redefinidas con su ACL de la 16/17.
revoke all on function public.cf_persistir_normalizacion_nucleo(uuid, text, text, text, text, jsonb, jsonb)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura_nucleo(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[])
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    to service_role;
"""

CABECERA_ROLLBACK = """\
-- Rollback de la migracion 26 (Hito 2BK): devuelve el esquema exacto de la 25.
-- Generado por pruebas/auditoria_2bk/generar_migracion_26.py: las funciones de la 15 y la 17, literales.
-- Solo con confirmacion de Pio. Las ejecuciones, facturas e historial ya registrados se conservan.
begin;

"""

PRIVILEGIOS_ROLLBACK = """\
revoke all on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[])
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    to service_role;

drop function if exists public.cf_persistir_documento_multifactura_nucleo(uuid, text, text, text, jsonb, text[], text);
drop function if exists public.cf_persistir_normalizacion_nucleo(uuid, text, text, text, text, jsonb, jsonb);
drop index if exists public.facturas_identidad_nucleo_idx;
alter function public.cf_componentes_identidad_factura(jsonb) cost 100;

commit;
"""


def migracion() -> str:
    return "\n\n".join([
        CABECERA.rstrip("\n"),
        "-- Nucleo de cf_persistir_normalizacion (17) con la ejecucion ya completa como argumento opcional.",
        nucleo_normalizacion(),
        "-- Nucleo multifactura (15) con la busqueda indexada y el modo de ejecucion.",
        nucleo_multifactura(),
        ENVOLTORIOS.rstrip("\n"),
        PRIVILEGIOS.rstrip("\n"),
        "commit;",
    ]) + "\n"


def rollback() -> str:
    return CABECERA_ROLLBACK + "\n\n".join([NORMALIZACION_17, MULTIFACTURA_15, ENVOLTORIO_17,
                                           PRIVILEGIOS_ROLLBACK])


if __name__ == "__main__":
    DESTINO.write_text(migracion(), encoding="utf-8", newline="\n")
    ROLLBACK.write_text(rollback(), encoding="utf-8", newline="\n")
    print(DESTINO.relative_to(ROOT), ROLLBACK.relative_to(ROOT))
