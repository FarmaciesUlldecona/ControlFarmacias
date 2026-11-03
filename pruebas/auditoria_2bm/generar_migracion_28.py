"""Hito 2BM: genera la migracion 28 y su rollback a partir del texto exacto de la migracion 27.

Problema (serie 2BJ, tandas 7 y 9): la persistencia multifactura tarda 5,9 s en produccion (posicion 57) y supera
el statement_timeout de 8 s (posicion 82). Diagnostico local con el payload real de la posicion 122 (274 lineas,
4,6 MB): 1,20 s en el servidor; el payload se copia varias veces y se guarda dos veces (``resultado_json`` y
``facturas.datos_extraidos``). Decisiones de Pio (2026-11-03), puntos 1-4:
1. ``lz4`` en las columnas jsonb grandes (solo valores nuevos; las filas existentes no se reescriben);
2. ``resultado_json`` de la multifactura sin el contenido de las facturas que esta misma ejecucion persiste: en su
   lugar, una referencia ``{"_factura_persistida": {"proyeccion_clave", "claves_originales"}}`` a
   ``facturas.datos_extraidos`` (completo). Las facturas no persistidas aqui (pendientes, duplicadas, en
   revision, ya persistidas) siguen completas. Historico: antes de que cambie ``datos_extraidos`` de una fila o
   de que se borre, por cualquier camino, toda ejecucion del documento que la referencia recibe su copia completa
   (trigger ``facturas_materializar_referencia``);
3. el payload no se copia para pasarlo al nucleo de normalizacion (nucleo de 9 parametros: documento y facturas
   aparte; el de 7 queda como envoltorio) y las facturas nuevas se acumulan en un array, no en un jsonb que se
   recopia en cada vuelta;
4. la identidad de cada factura se calcula una vez (antes se recalculaba al compararla con cada hermana);
y (decision de Pio, 2026-11-03) la firma de la solicitud se calcula sin copiar el payload en un objeto
intermedio; una repeticion de una ejecucion guardada con la formula de la 15-27 se comprueba con esa formula.
Replay, rechazo, inventario, estados y filas proyectadas: los mismos que la 27.
Cada sustitucion se comprueba. El rollback materializa las referencias (resultado_json completo, formato 27) y
reproduce literalmente las funciones de la 27. Uso: python -B pruebas/auditoria_2bm/generar_migracion_28.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql/migrations"
ORIGEN = "27_cf_reintento_tras_fallo_de_persistencia.sql"
DESTINO = MIG / "28_cf_persistencia_multifactura_ligera.sql"
ROLLBACK = MIG / "28_cf_persistencia_multifactura_ligera.rollback.sql"

COLUMNAS_LZ4 = (("normalizacion_ejecuciones", "resultado_json"), ("facturas", "datos_extraidos"),
                ("facturas_albaranes_extraidos", "provenance"), ("facturas_vencimientos", "provenance"),
                ("facturas_impuestos", "provenance"), ("facturas_movimientos", "provenance"),
                ("facturas_incidencias", "provenance"), ("facturas_incidencias", "detalle_tecnico"))
FACTURAS_27 = "coalesce(v_documento_normalizado->'facturas', '[]'::jsonb)"
FIRMA_27 = ("encode(extensions.digest(jsonb_build_object('documento',p_resultado,'seleccion',"
            "to_jsonb(p_segmentos_autorizados))::text,'sha256'),'hex')")


def _lineas(nombre: str, desde: int, hasta: int, primera: str) -> str:
    lineas = (MIG / nombre).read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    bloque = "\n".join(lineas[desde - 1:hasta])
    if not bloque.startswith(primera) or not bloque.endswith("$$;"):
        raise SystemExit(f"LIMITES_INESPERADOS:{nombre}:{desde}-{hasta}")
    return bloque


def _sustituir(texto: str, viejo: str, nuevo: str, veces: int = 1) -> str:
    if texto.count(viejo) != veces:
        raise SystemExit(f"SUSTITUCION_INESPERADA:{viejo[:60]!r}:{texto.count(viejo)}!={veces}")
    return texto.replace(viejo, nuevo)


NUCLEO_NORMALIZACION_27 = _lineas(ORIGEN, 44, 322, "create or replace function public.cf_persistir_normalizacion_nucleo(")
NUCLEO_MULTIFACTURA_27 = _lineas(ORIGEN, 326, 466,
                                 "create or replace function public.cf_persistir_documento_multifactura_nucleo(")

AUXILIARES = """\
-- 28: referencia a la factura persistida por la misma ejecucion (en lugar de su contenido). Guarda los valores
-- originales de las dos claves que la persistencia anade a datos_extraidos, para reconstruir el original.
create or replace function public.cf_referencia_factura(p_factura jsonb, p_clave text)
returns jsonb
language sql
immutable
security definer
set search_path = public
as $$
    select jsonb_build_object('_factura_persistida', jsonb_build_object(
        'proyeccion_clave', p_clave,
        'claves_originales', (select coalesce(jsonb_object_agg(k, p_factura->k), '{}'::jsonb)
                                from unnest(array['factura_id', 'identidad_economica_clave']) k
                               where p_factura ? k)));
$$;

-- 28: la factura original a partir de su referencia y de datos_extraidos.
create or replace function public.cf_factura_desde_referencia(p_referencia jsonb, p_datos jsonb)
returns jsonb
language sql
immutable
security definer
set search_path = public
as $$
    select (p_datos - 'factura_id' - 'identidad_economica_clave')
           || (p_referencia #> '{_factura_persistida,claves_originales}');
$$;

-- 28: historico. Antes de que cambie datos_extraidos de una factura o de que se borre la fila (por cualquier
-- camino), toda ejecucion del documento que la referencia recibe la copia completa de su factura (formato 27).
-- No depende de normalizacion_ejecucion_id (un upsert con datos identicos lo cambia sin cambiar el contenido).
create or replace function public.cf_materializar_referencia()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if tg_op = 'UPDATE' and old.datos_extraidos is not distinct from new.datos_extraidos then
        return new;
    end if;
    update public.normalizacion_ejecuciones e
       set resultado_json = jsonb_set(e.resultado_json, '{facturas}', (
           select jsonb_agg(case when x #>> '{_factura_persistida,proyeccion_clave}' = old.proyeccion_clave
                                 then public.cf_factura_desde_referencia(x, old.datos_extraidos) else x end
                            order by o)
             from jsonb_array_elements(e.resultado_json->'facturas') with ordinality t(x, o)))
     where e.documento_id = old.documento_id
       and jsonb_typeof(e.resultado_json->'facturas') = 'array'
       and exists (select 1 from jsonb_array_elements(e.resultado_json->'facturas') x
                    where x #>> '{_factura_persistida,proyeccion_clave}' = old.proyeccion_clave);
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

drop trigger if exists facturas_materializar_referencia on public.facturas;
create trigger facturas_materializar_referencia
before update of datos_extraidos or delete on public.facturas
for each row
execute function public.cf_materializar_referencia();"""

NUCLEO_7 = """\
-- 28: firma de 7 parametros (la que usa cf_persistir_normalizacion): delega en el nucleo de 9.
create or replace function public.cf_persistir_normalizacion_nucleo(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_resultado_hash text,
    p_resultado jsonb,
    p_resultado_json_guardado jsonb
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
begin
    return public.cf_persistir_normalizacion_nucleo(
        p_documento_id, p_worker_id, p_disparador, p_idempotency_key, p_resultado_hash, p_resultado,
        p_resultado_json_guardado, null::jsonb, null::jsonb);
end;
$$;"""


def nucleo_normalizacion() -> str:
    """Nucleo de 9 parametros: el documento y sus facturas llegan aparte (sin copiar el payload)."""
    texto = _sustituir(NUCLEO_NORMALIZACION_27, "    p_resultado_json_guardado jsonb\n)",
                       "    p_resultado_json_guardado jsonb,\n    p_documento jsonb,\n    p_facturas jsonb\n)")
    texto = _sustituir(
        texto,
        "    v_documento_normalizado jsonb := coalesce(p_resultado->'resultado_json', p_resultado);\n",
        "    v_documento_normalizado jsonb := coalesce(p_documento, p_resultado->'resultado_json', p_resultado);\n"
        f"    v_facturas jsonb := coalesce(p_facturas, {FACTURAS_27});\n")
    texto = _sustituir(texto, FACTURAS_27, "v_facturas", veces=7)
    # La declaracion de v_facturas tambien contenia el texto: se restaura.
    texto = _sustituir(texto, "    v_facturas jsonb := coalesce(p_facturas, v_facturas);\n",
                       f"    v_facturas jsonb := coalesce(p_facturas, {FACTURAS_27});\n")
    return texto


def nucleo_multifactura() -> str:
    texto = _sustituir(
        NUCLEO_MULTIFACTURA_27,
        f"    firma:={FIRMA_27};\n",
        "    -- 28: firma sin construir un objeto intermedio con todo el payload (texto del documento y seleccion;\n"
        "    -- el texto jsonb de un objeto acaba donde acaba el objeto: la concatenacion no es ambigua).\n"
        "    firma:=encode(extensions.digest(p_resultado::text || '|' || to_jsonb(p_segmentos_autorizados)::text,"
        "'sha256'),'hex');\n")
    texto = _sustituir(
        texto,
        "        if replay#>>'{multifactura,firma_solicitud}' is distinct from firma then raise exception "
        "'IDEMPOTENCIA_PAYLOAD_DISTINTO'; end if;\n",
        "        if replay#>>'{multifactura,firma_solicitud}' is distinct from firma then\n"
        "            -- 28: ejecuciones guardadas con la formula de la 15-27 se comprueban con esa formula.\n"
        f"            if replay#>>'{{multifactura,firma_solicitud}}' is distinct from {FIRMA_27} then\n"
        "                raise exception 'IDEMPOTENCIA_PAYLOAD_DISTINTO'; end if;\n"
        "        end if;\n")
    texto = _sustituir(texto, "    nuevas jsonb := '[]'::jsonb;\n",
                       "    nuevas jsonb := '[]'::jsonb;\n"
                       "    nuevas_arr jsonb[] := '{}'::jsonb[];\n"
                       "    guardadas jsonb[] := '{}'::jsonb[];\n"
                       "    identidades jsonb;\n")
    texto = _sustituir(
        texto,
        "    for f in select value from jsonb_array_elements(p_resultado->'facturas') loop\n",
        "    -- 28: identidad de cada factura calculada una vez (comparacion con las hermanas).\n"
        "    identidades:=(select jsonb_agg(to_jsonb(public.cf_componentes_identidad_factura(x)) order by o)\n"
        "        from jsonb_array_elements(p_resultado->'facturas') with ordinality t(x,o));\n"
        "    for f in select value from jsonb_array_elements(p_resultado->'facturas') loop\n")
    texto = _sustituir(
        texto,
        "        if exists(select 1 from jsonb_array_elements(p_resultado->'facturas') sibling\n"
        "            where (public.cf_componentes_identidad_factura(sibling))[1:4]=partes[1:4]\n"
        "              and public.cf_componentes_identidad_factura(sibling)<>partes) then\n",
        "        if exists(select 1 from jsonb_array_elements(identidades) s\n"
        "            where jsonb_typeof(s)='array'\n"
        "              and (array(select v from jsonb_array_elements_text(s) with ordinality u(v,o) order by o))[1:4]"
        "=partes[1:4]\n"
        "              and array(select v from jsonb_array_elements_text(s) with ordinality u(v,o) order by o)"
        "<>partes) then\n")
    texto = _sustituir(
        texto,
        "            nuevas:=nuevas || jsonb_build_array(f || jsonb_build_object('factura_id',clave,'identidad_economica_clave',clave));\n"
        "            estado:='PERSISTIDAS';\n"
        "        end if;\n",
        "            -- 28: array (sin recopiar el jsonb en cada vuelta) y referencia en lugar del contenido.\n"
        "            nuevas_arr:=nuevas_arr || (f || jsonb_build_object('factura_id',clave,'identidad_economica_clave',clave));\n"
        "            guardadas:=guardadas || public.cf_referencia_factura(f,clave);\n"
        "            estado:='PERSISTIDAS';\n"
        "        else\n"
        "            guardadas:=guardadas || f;\n"
        "        end if;\n")
    texto = _sustituir(texto, "    payload:=p_resultado || jsonb_build_object('facturas',nuevas);\n",
                       "    nuevas:=to_jsonb(nuevas_arr);\n")
    return _sustituir(
        texto,
        "        jsonb_build_object('resultado_json',payload,'uso_luna',false,'uso_ocr',false),\n"
        "        p_resultado || jsonb_build_object(\n"
        "        'multifactura',jsonb_build_object('firma_solicitud',firma,'segmentos_autorizados',"
        "to_jsonb(p_segmentos_autorizados)))\n"
        "        || case when p_disparador is null then '{}'::jsonb else jsonb_build_object('provenance_ejecucion',\n"
        "           jsonb_build_object('modo_ejecucion',p_disparador)) end);\n",
        "        jsonb_build_object('uso_luna',false,'uso_ocr',false),\n"
        "        -- 28: lectura completa salvo las facturas que persiste esta ejecucion (referencias).\n"
        "        (p_resultado - 'facturas') || jsonb_build_object('facturas',to_jsonb(guardadas),\n"
        "        'multifactura',jsonb_build_object('firma_solicitud',firma,'segmentos_autorizados',"
        "to_jsonb(p_segmentos_autorizados)))\n"
        "        || case when p_disparador is null then '{}'::jsonb else jsonb_build_object('provenance_ejecucion',\n"
        "           jsonb_build_object('modo_ejecucion',p_disparador)) end,\n"
        "        p_resultado, nuevas);\n")


CABECERA = """\
-- Migracion 28 (Hito 2BM): persistencia multifactura sin copias ni duplicados del payload.
-- Generada por pruebas/auditoria_2bm/generar_migracion_28.py a partir del texto de la 27.
-- En produccion la persistencia multifactura tarda 5,9 s (Alliance de la posicion 57) y supero el
-- statement_timeout de 8 s (posicion 82). Cambios, con el mismo resultado que la 27:
-- - lz4 en las columnas jsonb grandes (valores nuevos);
-- - resultado_json sin el contenido de las facturas que persiste la propia ejecucion: referencia a
--   facturas.datos_extraidos (completo); antes de que cambie o se borre una fila (trigger), copia completa en
--   las ejecuciones que la referencian;
-- - el payload no se copia para pasarlo al nucleo de normalizacion (nucleo de 9 parametros);
-- - identidad de cada factura calculada una vez;
-- - firma de la solicitud sin objeto intermedio; las repeticiones de ejecuciones con la firma de la 15-27 se
--   comprueban con esa formula.
-- Firmas y privilegios de las RPC sin cambios; filas existentes sin cambios. Requiere la 27.
-- Diseno: pruebas/auditoria_2bm/DISENO.md.
begin;

do $$
begin
    if to_regprocedure('public.cf_ejecucion_persistida(uuid,text)') is null then
        raise exception 'MIGRACION_27_AUSENTE';
    end if;
end;
$$;
"""

PRIVILEGIOS = """\
-- Privilegios (patron 25-27): owner postgres; funciones internas solo propietario.
""" + "".join(f"""revoke all on function public.{f}
    from public, anon, authenticated, service_role;
""" for f in ("cf_referencia_factura(jsonb, text)", "cf_factura_desde_referencia(jsonb, jsonb)",
              "cf_materializar_referencia()",
              "cf_persistir_normalizacion_nucleo(uuid, text, text, text, text, jsonb, jsonb)",
              "cf_persistir_normalizacion_nucleo(uuid, text, text, text, text, jsonb, jsonb, jsonb, jsonb)",
              "cf_persistir_documento_multifactura_nucleo(uuid, text, text, text, jsonb, text[], text)"))

CABECERA_ROLLBACK = """\
-- Rollback de la migracion 28 (Hito 2BM): devuelve el esquema exacto de la 27.
-- Generado por pruebas/auditoria_2bm/generar_migracion_28.py: las funciones de la 27, literales.
-- Antes, materializa las referencias: todo resultado_json vuelve al formato 27 (lectura completa).
-- Solo con confirmacion de Pio. Facturas e historial se conservan.
begin;

update public.normalizacion_ejecuciones e
   set resultado_json = jsonb_set(e.resultado_json, '{facturas}', (
       select jsonb_agg(case when x ? '_factura_persistida'
                             then public.cf_factura_desde_referencia(x, (
                                 select f.datos_extraidos from public.facturas f
                                  where f.documento_id = e.documento_id
                                    and f.proyeccion_clave = x #>> '{_factura_persistida,proyeccion_clave}'))
                             else x end order by o)
         from jsonb_array_elements(e.resultado_json->'facturas') with ordinality t(x, o)))
 where jsonb_typeof(e.resultado_json->'facturas') = 'array'
   and exists (select 1 from jsonb_array_elements(e.resultado_json->'facturas') x where x ? '_factura_persistida');

do $$
begin
    if exists (select 1 from public.normalizacion_ejecuciones e
                where jsonb_typeof(e.resultado_json->'facturas') = 'array'
                  and exists (select 1 from jsonb_array_elements(e.resultado_json->'facturas') x
                               where x is null or x ? '_factura_persistida')) then
        raise exception 'ROLLBACK_28_REFERENCIA_NO_RESUELTA';
    end if;
end;
$$;

"""

PRIVILEGIOS_ROLLBACK = """\
revoke all on function public.cf_persistir_normalizacion_nucleo(uuid, text, text, text, text, jsonb, jsonb)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_persistir_documento_multifactura_nucleo(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated, service_role;

drop function if exists public.cf_persistir_normalizacion_nucleo(uuid, text, text, text, text, jsonb, jsonb, jsonb, jsonb);
drop trigger if exists facturas_materializar_referencia on public.facturas;
drop function if exists public.cf_materializar_referencia();
drop function if exists public.cf_factura_desde_referencia(jsonb, jsonb);
drop function if exists public.cf_referencia_factura(jsonb, text);
""" + "".join(f"alter table public.{t} alter column {c} set compression default;\n" for t, c in COLUMNAS_LZ4) + """
commit;
"""


def migracion() -> str:
    lz4 = ("-- 1. lz4 en las columnas jsonb grandes (solo afecta a valores nuevos).\n"
           + "".join(f"alter table public.{t} alter column {c} set compression lz4;\n" for t, c in COLUMNAS_LZ4))
    return "\n\n".join([
        CABECERA.rstrip("\n"),
        lz4.rstrip("\n"),
        AUXILIARES,
        "-- Nucleo de normalizacion (27) con el documento y sus facturas aparte y el historico de la 28.",
        nucleo_normalizacion(),
        NUCLEO_7,
        "-- Nucleo multifactura (27) con referencias, sin copias del payload e identidad calculada una vez.",
        nucleo_multifactura(),
        PRIVILEGIOS.rstrip("\n"),
        "commit;",
    ]) + "\n"


def rollback() -> str:
    return CABECERA_ROLLBACK + "\n\n".join([NUCLEO_NORMALIZACION_27, NUCLEO_MULTIFACTURA_27, PRIVILEGIOS_ROLLBACK])


if __name__ == "__main__":
    DESTINO.write_text(migracion(), encoding="utf-8", newline="\n")
    ROLLBACK.write_text(rollback(), encoding="utf-8", newline="\n")
    print(DESTINO.relative_to(ROOT), ROLLBACK.relative_to(ROOT))
