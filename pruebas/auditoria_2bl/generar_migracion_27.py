"""Hito 2BL: genera la migracion 27 y su rollback a partir del texto exacto de la migracion 26.

Problema (serie 2BJ, Alliance de la posicion 57): la persistencia supero el ``statement_timeout`` y el worker
registro el fallo con la misma clave de idempotencia que la persistencia. En el reintento (mismo PDF, mismo hash,
misma clave) la RPC encontraba esa ejecucion en ERROR y la trataba como una repeticion: la multifactura la
rechazaba con ``IDEMPOTENCIA_PAYLOAD_DISTINTO`` (sin firma que comparar) y la de un documento devolvia la
ejecucion en ERROR sin persistir nada. El documento no podia guardarse nunca.

La 27 cambia solo la deteccion de repeticiones, en los dos nucleos y en el envoltorio de 7 parametros:
- una ejecucion en ERROR sin resultado persistido (``estado = 'ERROR' and resultado_json is null``) no es una
  repeticion; la persistencia es un intento nuevo con fila propia y clave derivada ``<clave>:intento:<n>``
  (``unique (documento_id, idempotency_key)``), el mismo patron de ``cf_registrar_fallo_normalizacion``;
- una ejecucion persistida (con la clave o con su clave derivada) sigue siendo la repeticion: replay como hoy
  y, en la multifactura, rechazo como hoy si la firma de la solicitud es distinta.
Cada sustitucion se comprueba (exactamente una aparicion). El rollback reproduce literalmente las funciones de
la 26. Uso: python -B pruebas/auditoria_2bl/generar_migracion_27.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql/migrations"
ORIGEN = "26_cf_persistencia_multifactura_indexada.sql"
DESTINO = MIG / "27_cf_reintento_tras_fallo_de_persistencia.sql"
ROLLBACK = MIG / "27_cf_reintento_tras_fallo_de_persistencia.rollback.sql"


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


NUCLEO_NORMALIZACION_26 = _lineas(ORIGEN, 33, 307, "create or replace function public.cf_persistir_normalizacion_nucleo(")
NUCLEO_MULTIFACTURA_26 = _lineas(ORIGEN, 311, 450,
                                 "create or replace function public.cf_persistir_documento_multifactura_nucleo(")
ENVOLTORIO_26 = _lineas(ORIGEN, 487, 530, "create or replace function public.cf_persistir_documento_multifactura(")

EJECUCION_PERSISTIDA = """\
-- 27: la ejecucion que hace de repeticion de (documento, clave): la persistida con esa clave o con su clave
-- derivada de reintento. Una ejecucion en ERROR sin resultado persistido nunca lo es.
create or replace function public.cf_ejecucion_persistida(p_documento_id uuid, p_idempotency_key text)
returns uuid
language sql
stable
security definer
set search_path = public
as $$
    select e.id
      from public.normalizacion_ejecuciones e
     where e.documento_id = p_documento_id
       and not (e.estado = 'ERROR' and e.resultado_json is null)
       and (e.idempotency_key = p_idempotency_key
            or (left(e.idempotency_key, length(p_idempotency_key) + 9) = p_idempotency_key || ':intento:'
                and substr(e.idempotency_key, length(p_idempotency_key) + 10) ~ '^[0-9]+$'))
     order by e.intento
     limit 1;
$$;"""


def nucleo_normalizacion() -> str:
    texto = _sustituir(NUCLEO_NORMALIZACION_26, "    v_estado_factura text;\n",
                       "    v_estado_factura text;\n    v_clave text := p_idempotency_key;\n")
    texto = _sustituir(
        texto,
        "    select id into v_ejecucion_id\n"
        "      from public.normalizacion_ejecuciones\n"
        "     where documento_id = p_documento_id\n"
        "       and idempotency_key = p_idempotency_key;\n",
        "    -- 27: una ejecucion en ERROR sin resultado persistido no es una repeticion.\n"
        "    v_ejecucion_id := public.cf_ejecucion_persistida(p_documento_id, p_idempotency_key);\n")
    texto = _sustituir(
        texto,
        "     where documento_id = p_documento_id;\n\n    insert into public.normalizacion_ejecuciones (\n",
        "     where documento_id = p_documento_id;\n"
        "    -- 27: si la clave ya la ocupa un fallo, el intento nuevo lleva fila y clave propias.\n"
        "    if exists (select 1 from public.normalizacion_ejecuciones\n"
        "                where documento_id = p_documento_id and idempotency_key = p_idempotency_key) then\n"
        "        v_clave := p_idempotency_key || ':intento:' || v_intento;\n"
        "    end if;\n\n"
        "    insert into public.normalizacion_ejecuciones (\n")
    return _sustituir(texto, "        p_documento_id, p_idempotency_key, v_intento, p_disparador,\n",
                      "        p_documento_id, v_clave, v_intento, p_disparador,\n")


def nucleo_multifactura() -> str:
    return _sustituir(
        NUCLEO_MULTIFACTURA_26,
        "    select id,resultado_json into ejecucion,replay from public.normalizacion_ejecuciones\n"
        "      where documento_id=d.id and idempotency_key=p_idempotency_key;\n",
        "    -- 27: una ejecucion en ERROR sin resultado persistido no es una repeticion.\n"
        "    select id,resultado_json into ejecucion,replay from public.normalizacion_ejecuciones\n"
        "      where id=public.cf_ejecucion_persistida(d.id,p_idempotency_key);\n")


def envoltorio() -> str:
    return _sustituir(
        ENVOLTORIO_26,
        "    select id into v_previa\n"
        "      from public.normalizacion_ejecuciones\n"
        "     where documento_id = p_documento_id and idempotency_key = p_idempotency_key;\n",
        "    -- 27: misma deteccion de repeticion que el nucleo.\n"
        "    v_previa := public.cf_ejecucion_persistida(p_documento_id, p_idempotency_key);\n")


CABECERA = """\
-- Migracion 27 (Hito 2BL): un fallo registrado no bloquea el reintento de la persistencia.
-- Generada por pruebas/auditoria_2bl/generar_migracion_27.py a partir del texto de la 26.
-- En produccion (serie 2BJ) la persistencia de un Alliance supero el statement_timeout y el fallo quedo
-- registrado con la clave de la persistencia; el reintento (misma clave) lo tomaba por una repeticion y no
-- podia guardar nunca. Cambios:
-- - una ejecucion en ERROR sin resultado persistido no es una repeticion: intento nuevo con fila propia y
--   clave derivada <clave>:intento:<n>;
-- - ejecucion persistida con la misma solicitud: replay como hoy; multifactura con otra firma: rechazo como hoy.
-- Firmas, privilegios de las RPC y filas existentes no cambian. Requiere la 26.
-- Diseno: pruebas/auditoria_2bl/DISENO.md.
begin;

do $$
begin
    if to_regprocedure('public.cf_persistir_documento_multifactura_nucleo(uuid,text,text,text,jsonb,text[],text)')
       is null then
        raise exception 'MIGRACION_26_AUSENTE';
    end if;
end;
$$;
"""

PRIVILEGIOS = """\
-- Privilegios (patron 25/26): owner postgres; funciones internas solo propietario; RPC con su ACL de la 16/17.
revoke all on function public.cf_ejecucion_persistida(uuid, text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_normalizacion_nucleo(uuid, text, text, text, text, jsonb, jsonb)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura_nucleo(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    to service_role;
"""

CABECERA_ROLLBACK = """\
-- Rollback de la migracion 27 (Hito 2BL): devuelve el esquema exacto de la 26.
-- Generado por pruebas/auditoria_2bl/generar_migracion_27.py: las funciones de la 26, literales.
-- Solo con confirmacion de Pio. Las ejecuciones, facturas e historial ya registrados se conservan.
begin;

"""

PRIVILEGIOS_ROLLBACK = """\
revoke all on function public.cf_persistir_normalizacion_nucleo(uuid, text, text, text, text, jsonb, jsonb)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura_nucleo(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    to service_role;

drop function if exists public.cf_ejecucion_persistida(uuid, text);

commit;
"""


def migracion() -> str:
    return "\n\n".join([
        CABECERA.rstrip("\n"),
        EJECUCION_PERSISTIDA,
        "-- Nucleo de cf_persistir_normalizacion (26) con la deteccion de repeticion de la 27.",
        nucleo_normalizacion(),
        "-- Nucleo multifactura (26) con la deteccion de repeticion de la 27.",
        nucleo_multifactura(),
        "-- Envoltorio multifactura de 7 parametros (26) con la deteccion de repeticion de la 27.",
        envoltorio(),
        PRIVILEGIOS.rstrip("\n"),
        "commit;",
    ]) + "\n"


def rollback() -> str:
    return CABECERA_ROLLBACK + "\n\n".join([NUCLEO_NORMALIZACION_26, NUCLEO_MULTIFACTURA_26, ENVOLTORIO_26,
                                           PRIVILEGIOS_ROLLBACK])


if __name__ == "__main__":
    DESTINO.write_text(migracion(), encoding="utf-8", newline="\n")
    ROLLBACK.write_text(rollback(), encoding="utf-8", newline="\n")
    print(DESTINO.relative_to(ROOT), ROLLBACK.relative_to(ROOT))
