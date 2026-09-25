"""Genera la migracion 17 y su rollback a partir de los cuerpos certificados 12/16.

Reproducible: copia literalmente las funciones originales y aplica solo los
parches documentados en DISENO.md. Uso: python pruebas/auditoria_2ar/generar_migracion_17.py
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "sql" / "migrations"
DESTINO = MIG / "17_cf_replay_y_fallos_no_bloqueantes.sql"
ROLLBACK = MIG / "17_cf_replay_y_fallos_no_bloqueantes.rollback.sql"


def _funcion(texto: str, nombre: str) -> str:
    inicio = texto.index(f"create or replace function public.{nombre}(")
    return texto[inicio:texto.index("\n$$;", inicio) + 4]


def _parche(texto: str, antes: str, despues: str) -> str:
    assert texto.count(antes) == 1, antes
    return texto.replace(antes, despues)


M12 = (MIG / "12_cf_views_rls_rpc.sql").read_text(encoding="utf-8")
M16 = (MIG / "16_cf_worker_manual_one_shot.sql").read_text(encoding="utf-8")
ORIG_PERSISTIR = _funcion(M12, "cf_persistir_normalizacion")
ORIG_FALLO = _funcion(M12, "cf_registrar_fallo_normalizacion")
ORIG_REPROCESADO = _funcion(M12, "cf_solicitar_reprocesado")
ORIG_ENVOLTORIO = _funcion(M16, "cf_persistir_documento_multifactura")

CHECK_16 = (
    "'PENDIENTE','PROCESANDO','EXTRAIDA','REVISION','ERROR',\n"
    "        'NORMALIZANDO','NORMALIZADA'"
)

PERSISTIR_17 = _parche(
    ORIG_PERSISTIR,
    """    if v_ejecucion_id is not null then
        return v_ejecucion_id;
    end if;""",
    """    if v_ejecucion_id is not null then
        -- R1: el replay nunca deja claim, lock ni estado intermedio.
        perform public.cf_cerrar_replay_normalizacion(
            p_documento_id, p_worker_id, v_ejecucion_id, 'NORMALIZACION');
        return v_ejecucion_id;
    end if;""",
)
PERSISTIR_17 = _parche(
    PERSISTIR_17,
    "reprocesar_solicitado_at = null, ultimo_error_codigo = null,",
    "reprocesar_solicitado_at = null, ultimo_error_codigo = null,\n"
    "           intentos_fallo_normalizacion = 0, ultima_clase_fallo = null,\n"
    "           proximo_reintento_at = null,",
)
REPROCESADO_17 = _parche(
    ORIG_REPROCESADO,
    "           proximo_reintento_at = null,\n",
    "           proximo_reintento_at = null,\n"
    "           intentos_fallo_normalizacion = 0,\n"
    "           ultima_clase_fallo = null,\n",
)

MIGRACION = f"""-- Migracion 17 (Hito 2AR): replay idempotente sin estado intermedio (R1),
-- estado PROVEEDOR_NO_SOPORTADO (R2) y reintentos acotados con backoff (R3).
-- R4: no redefine el selector ni el ordering; el nucleo de la migracion 16 ya
-- excluye estados distintos de PENDIENTE/ERROR y proximo_reintento_at futuro.
-- Idempotente. Sin DML sobre datos existentes salvo defaults de columnas nuevas.
-- Generada por pruebas/auditoria_2ar/generar_migracion_17.py.
begin;

-- R2: nuevo estado documental no reclamable.
alter table public.documentos_facturas
    drop constraint if exists cf_documentos_estado_lectura_check;
alter table public.documentos_facturas
    add constraint cf_documentos_estado_lectura_check
    check (estado_lectura in (
        {CHECK_16},
        'PROVEEDOR_NO_SOPORTADO'
    ));

-- R3: contador, clase del ultimo fallo y parametros configurables.
alter table public.documentos_facturas
    add column if not exists intentos_fallo_normalizacion integer not null default 0,
    add column if not exists ultima_clase_fallo text;
alter table public.documentos_facturas
    drop constraint if exists cf_documentos_intentos_fallo_check,
    drop constraint if exists cf_documentos_ultima_clase_fallo_check;
alter table public.documentos_facturas
    add constraint cf_documentos_intentos_fallo_check
        check (intentos_fallo_normalizacion >= 0),
    add constraint cf_documentos_ultima_clase_fallo_check
        check (ultima_clase_fallo is null or ultima_clase_fallo in
            ('NO_SOPORTADO', 'DEFECTO_DOCUMENTO', 'TRANSITORIO'));

alter table public.normalizacion_ejecuciones
    add column if not exists clase_fallo text;
alter table public.normalizacion_ejecuciones
    drop constraint if exists cf_ejecuciones_clase_fallo_check;
alter table public.normalizacion_ejecuciones
    add constraint cf_ejecuciones_clase_fallo_check
        check (clase_fallo is null or clase_fallo in
            ('NO_SOPORTADO', 'DEFECTO_DOCUMENTO', 'TRANSITORIO'));

alter table public.cf_configuracion
    add column if not exists normalizacion_max_intentos integer not null default 4,
    add column if not exists normalizacion_backoff interval[] not null
        default array[interval '1 hour', interval '6 hours', interval '24 hours'];
alter table public.cf_configuracion
    drop constraint if exists cf_configuracion_reintentos_check;
alter table public.cf_configuracion
    add constraint cf_configuracion_reintentos_check check (
        normalizacion_max_intentos between 1 and 20
        and cardinality(normalizacion_backoff) >= 1
        and cardinality(normalizacion_backoff) >= normalizacion_max_intentos - 1
        and interval '0' < all(normalizacion_backoff)
    );

-- R1: cierre comun del replay. Libera el claim del llamante y restaura el estado
-- final de la ejecucion original. No crea ni modifica facturas ni ejecuciones.
create or replace function public.cf_cerrar_replay_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_ejecucion_id uuid,
    p_origen text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    d public.documentos_facturas%rowtype;
    v_persistencia text;
    v_lectura text;
    v_liberado boolean := false;
begin
    if p_origen not in ('MULTIFACTURA', 'NORMALIZACION') then
        raise exception 'ORIGEN_REPLAY_NO_ADMITIDO';
    end if;
    select * into d from public.documentos_facturas where id = p_documento_id for update;
    if d.id is null then
        raise exception 'documento no encontrado';
    end if;
    v_persistencia := d.estado_persistencia;
    v_lectura := d.estado_lectura;
    if d.bloqueado_por is not null and d.bloqueado_por = p_worker_id then
        if p_origen = 'MULTIFACTURA' then
            select h.estado_nuevo->>'estado_persistencia' into v_persistencia
              from public.historial_facturas h
             where h.documento_id = d.id
               and h.evento = 'INVENTARIO_MULTIFACTURA'
               and h.detalle->>'ejecucion_id' = p_ejecucion_id::text
             order by h.created_at desc, h.id desc
             limit 1;
            v_persistencia := coalesce(v_persistencia, d.estado_persistencia);
            v_lectura := case when v_persistencia = 'COMPLETA' then 'NORMALIZADA' else 'REVISION' end;
        else
            v_lectura := 'NORMALIZADA';
        end if;
        update public.documentos_facturas
           set estado_lectura = v_lectura,
               estado_persistencia = v_persistencia,
               bloqueado_por = null,
               bloqueado_hasta = null,
               reprocesar_solicitado_at = null,
               fecha_actualizacion = now()
         where id = d.id;
        v_liberado := true;
    end if;
    insert into public.historial_facturas
        (documento_id, evento, origen, actor, estado_nuevo, detalle)
    values (
        d.id, 'NORMALIZACION_REPLAY_IDEMPOTENTE', 'RPC', p_worker_id,
        jsonb_build_object('estado_lectura', v_lectura, 'estado_persistencia', v_persistencia),
        jsonb_build_object('ejecucion_id', p_ejecucion_id, 'origen', p_origen,
                           'claim_liberado', v_liberado)
    );
end;
$$;

-- R1 en la persistencia de un documento (mismo patron de retorno temprano).
{PERSISTIR_17}

-- R1 en el envoltorio multifactura de 7 parametros.
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

    v_ejecucion := public.cf_persistir_documento_multifactura(
        p_documento_id,
        p_worker_id,
        p_idempotency_key,
        p_resultado_hash,
        p_resultado,
        p_segmentos_autorizados
    );

    if v_previa is not null then
        perform public.cf_cerrar_replay_normalizacion(
            p_documento_id, p_worker_id, v_ejecucion, 'MULTIFACTURA');
        return v_ejecucion;
    end if;

    update public.normalizacion_ejecuciones
       set disparador = p_disparador,
           resultado_json = coalesce(resultado_json, '{{}}'::jsonb)
               || jsonb_build_object(
                   'provenance_ejecucion',
                   jsonb_build_object('modo_ejecucion', p_disparador)
               )
     where id = v_ejecucion;
    return v_ejecucion;
end;
$$;

-- R2/R3: fallo clasificado. Retransmision sin claim -> devuelve la ejecucion
-- existente sin cambios; misma clave con claim vigente -> nuevo intento con clave
-- derivada unica.
create or replace function public.cf_registrar_fallo_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_error_codigo text,
    p_error_detalle text,
    p_clase_fallo text
)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
    d public.documentos_facturas%rowtype;
    v_existente uuid;
    v_ejecucion_id uuid;
    v_intento integer;
    v_clave text := p_idempotency_key;
    v_fallos integer;
    v_max integer;
    v_backoff interval[];
    v_estado text;
    v_proximo timestamptz;
begin
    if p_clase_fallo is null
       or p_clase_fallo not in ('NO_SOPORTADO', 'DEFECTO_DOCUMENTO', 'TRANSITORIO') then
        raise exception 'CLASE_FALLO_NO_ADMITIDA';
    end if;
    if nullif(btrim(p_worker_id), '') is null
       or nullif(btrim(p_idempotency_key), '') is null then
        raise exception 'worker_id e idempotency_key obligatorios';
    end if;

    select * into d from public.documentos_facturas where id = p_documento_id for update;
    select id into v_existente
      from public.normalizacion_ejecuciones
     where documento_id = p_documento_id and idempotency_key = p_idempotency_key;

    if d.id is null
       or d.bloqueado_por is distinct from p_worker_id
       or not exists (
           select 1 from public.cf_configuracion c
            where c.id = true and d.farmacia = any(c.farmacias_habilitadas)
       ) then
        if v_existente is not null then
            return v_existente;
        end if;
        raise exception 'claim no pertenece al worker';
    end if;

    select coalesce(max(intento), 0) + 1 into v_intento
      from public.normalizacion_ejecuciones where documento_id = p_documento_id;
    if v_existente is not null then
        v_clave := p_idempotency_key || ':intento:' || v_intento;
    end if;

    select normalizacion_max_intentos, normalizacion_backoff
      into v_max, v_backoff
      from public.cf_configuracion where id = true;

    if p_clase_fallo = 'NO_SOPORTADO' then
        v_estado := 'PROVEEDOR_NO_SOPORTADO';
        v_fallos := d.intentos_fallo_normalizacion;
        v_proximo := null;
    else
        v_fallos := d.intentos_fallo_normalizacion + 1;
        if v_fallos >= v_max then
            v_estado := 'REVISION';
            v_proximo := null;
        else
            v_estado := 'ERROR';
            v_proximo := now() + v_backoff[least(v_fallos, cardinality(v_backoff))];
        end if;
    end if;

    insert into public.normalizacion_ejecuciones
        (documento_id, idempotency_key, intento, disparador, estado, worker_id,
         iniciado_at, finalizado_at, error_codigo, error_detalle, clase_fallo)
    values (p_documento_id, v_clave, v_intento, p_disparador, 'ERROR',
        p_worker_id, now(), now(), p_error_codigo, p_error_detalle, p_clase_fallo)
    returning id into v_ejecucion_id;

    update public.documentos_facturas
       set estado_lectura = v_estado,
           ultimo_error_codigo = p_error_codigo,
           ultima_clase_fallo = p_clase_fallo,
           intentos_fallo_normalizacion = v_fallos,
           proximo_reintento_at = v_proximo,
           bloqueado_hasta = null, bloqueado_por = null,
           reprocesar_solicitado_at = null, fecha_actualizacion = now()
     where id = p_documento_id;
    insert into public.historial_facturas
        (documento_id, evento, origen, actor, estado_nuevo, detalle)
    values (p_documento_id, 'NORMALIZACION_ERROR', 'RPC', p_worker_id,
        jsonb_build_object('estado_lectura', v_estado,
                           'proximo_reintento_at', v_proximo),
        jsonb_build_object('ejecucion_id', v_ejecucion_id, 'codigo', p_error_codigo,
                           'clase_fallo', p_clase_fallo, 'intentos_fallo', v_fallos,
                           'max_intentos', v_max));
    return v_ejecucion_id;
end;
$$;

-- Firma de 6 parametros conservada por compatibilidad: sin clase explicita se
-- trata como TRANSITORIO (reintentos acotados), nunca como no soportado.
create or replace function public.cf_registrar_fallo_normalizacion(
    p_documento_id uuid,
    p_worker_id text,
    p_disparador text,
    p_idempotency_key text,
    p_error_codigo text,
    p_error_detalle text
)
returns uuid
language sql
security definer
set search_path = public
as $$
    select public.cf_registrar_fallo_normalizacion(
        p_documento_id, p_worker_id, p_disparador, p_idempotency_key,
        p_error_codigo, p_error_detalle, 'TRANSITORIO');
$$;

-- Reprocesado explicito: unica via de vuelta a la cola para
-- PROVEEDOR_NO_SOPORTADO y REVISION; reinicia el presupuesto de reintentos.
{REPROCESADO_17}

revoke all on function public.cf_cerrar_replay_normalizacion(uuid, text, uuid, text)
    from public, anon, authenticated, service_role;
revoke all on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text)
    from public, anon, authenticated;
revoke all on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text)
    to service_role;
grant execute on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text)
    to service_role;

-- 2AS: privilegios explicitos tambien en las funciones redefinidas. En Supabase
-- las funciones nuevas de public reciben EXECUTE por defecto para anon,
-- authenticated y service_role; ninguna funcion de la 17 depende de la ACL previa.
revoke all on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_normalizacion(uuid, text, text, text, text, jsonb)
    to service_role;
revoke all on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    from public, anon, authenticated;
grant execute on function public.cf_persistir_documento_multifactura(uuid, text, text, text, jsonb, text[], text)
    to service_role;
-- Ningun rol del sistema invoca el reprocesado: solo accion explicita de Pio.
-- Retira el EXECUTE de authenticated concedido por la migracion 12.
revoke all on function public.cf_solicitar_reprocesado(uuid, text)
    from public, anon, authenticated;

comment on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text) is
    'Fallo clasificado (R2/R3): NO_SOPORTADO -> PROVEEDOR_NO_SOPORTADO; resto -> ERROR con backoff o REVISION al maximo.';

commit;
"""

ROLLBACK_SQL = f"""-- Rollback de la migracion 17 (Hito 2AR). Devuelve el esquema al estado 16.
-- DML inevitable y documentado: PROVEEDOR_NO_SOPORTADO -> ERROR (el check 16 no
-- admite el estado nuevo). Se pierden contadores y clase de fallo (columnas 17).
-- Generado por pruebas/auditoria_2ar/generar_migracion_17.py.
begin;

drop function if exists public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text, text);

{ORIG_FALLO}

{ORIG_PERSISTIR}

{ORIG_REPROCESADO}

{ORIG_ENVOLTORIO}

drop function if exists public.cf_cerrar_replay_normalizacion(uuid, text, uuid, text);

update public.documentos_facturas
   set estado_lectura = 'ERROR'
 where estado_lectura = 'PROVEEDOR_NO_SOPORTADO';

alter table public.documentos_facturas
    drop constraint if exists cf_documentos_estado_lectura_check;
alter table public.documentos_facturas
    add constraint cf_documentos_estado_lectura_check
    check (estado_lectura in (
        {CHECK_16}
    ));

alter table public.documentos_facturas
    drop constraint if exists cf_documentos_intentos_fallo_check,
    drop constraint if exists cf_documentos_ultima_clase_fallo_check,
    drop column if exists intentos_fallo_normalizacion,
    drop column if exists ultima_clase_fallo;
alter table public.normalizacion_ejecuciones
    drop constraint if exists cf_ejecuciones_clase_fallo_check,
    drop column if exists clase_fallo;
alter table public.cf_configuracion
    drop constraint if exists cf_configuracion_reintentos_check,
    drop column if exists normalizacion_max_intentos,
    drop column if exists normalizacion_backoff;

revoke all on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.cf_registrar_fallo_normalizacion(uuid, text, text, text, text, text)
    to service_role;
-- Restaura el grant de la migracion 12 retirado por la 17.
grant execute on function public.cf_solicitar_reprocesado(uuid, text) to authenticated;

commit;
"""


def main() -> None:
    DESTINO.write_text(MIGRACION, encoding="utf-8")
    ROLLBACK.write_text(ROLLBACK_SQL, encoding="utf-8")
    print(DESTINO)
    print(ROLLBACK)


if __name__ == "__main__":
    main()
