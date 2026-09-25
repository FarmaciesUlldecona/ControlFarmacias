"""Hito 2AR: certificacion de la migracion 17 sobre PostgreSQL 17 REAL local.

R1 replay sin estado intermedio, R2 PROVEEDOR_NO_SOPORTADO, R3 reintentos acotados,
R4 ordering intacto, flags constantes, idempotencia de la migracion y rollback.
"""
from __future__ import annotations

import pytest

from pg17_local import (
    ALLIANCE, FLAGS_ESPERADOS, FLAGS_SQL, HEFAME, MIGRACION_17, ClientePg17, _ejecuciones,
    _estado, _facturas_de, _huella_facturas, _lit, _locks, _registrar, _siguiente_candidato,
    _truncado, _worker, esquema, orden_de_claims,
)


pytestmark = pytest.mark.pg17_local


@pytest.fixture
def base(pg17_nueva_base):
    return pg17_nueva_base("17")


def _reprocesar(pg, documento_id):
    pg.sql(f"select public.cf_solicitar_reprocesado({_lit(documento_id)}::uuid,'PIO-LOCAL-2AR');")


def _replays(pg, documento_id):
    return pg.json(
        "select actor,estado_nuevo->>'estado_lectura' as lectura,"
        "estado_nuevo->>'estado_persistencia' as persistencia,"
        "detalle->>'origen' as origen,(detalle->>'claim_liberado')::boolean as liberado "
        f"from public.historial_facturas where documento_id={_lit(documento_id)} "
        "and evento='NORMALIZACION_REPLAY_IDEMPOTENTE' order by id")


def _segundos_hasta_reintento(pg, documento_id) -> float:
    return float(pg.sql(
        "select extract(epoch from proximo_reintento_at - now()) "
        f"from public.documentos_facturas where id={_lit(documento_id)};"))


def _avanzar_tiempo(pg, documento_id):
    """Simula el paso del tiempo local: vence el backoff del documento."""
    pg.sql("update public.documentos_facturas set proximo_reintento_at = now() - interval '1 second' "
           f"where id={_lit(documento_id)};")


# --------------------------------------------------------------------------
# 4.1 / 4.2 Replay (R1)
# --------------------------------------------------------------------------


def test_4_1_replay_restaura_completa_y_libera_claim(base, tmp_path):
    cliente = ClientePg17(base, vigilar_flags=True)
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 1)
    _worker(cliente, tmp_path, "uno").ejecutar_una_manual()
    assert (_estado(base, alliance)["estado_lectura"], _estado(base, alliance)["estado_persistencia"]) == (
        "NORMALIZADA", "COMPLETA")
    facturas = _huella_facturas(base)
    _reprocesar(base, alliance)
    assert _estado(base, alliance)["estado_lectura"] == "PENDIENTE"
    resultado = _worker(cliente, tmp_path, "dos").ejecutar_una_manual()
    assert resultado.documentos_reclamados == 1
    estado = _estado(base, alliance)
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("NORMALIZADA", "COMPLETA")
    assert estado["bloqueado_por"] is None and estado["bloqueado_hasta"] is None
    assert base.sql(f"select reprocesar_solicitado_at is null from public.documentos_facturas "
                    f"where id={_lit(alliance)}") == "t"
    assert _locks(base) == "0|0"
    assert base.sql("select count(*) from pg_stat_activity where application_name ilike '%worker%'") == "0"
    assert _huella_facturas(base) == facturas
    assert len(_facturas_de(base, alliance)) == 3
    assert len(_ejecuciones(base, alliance)) == 1
    assert _replays(base, alliance) == [{
        "actor": "manual-2aq-dos", "lectura": "NORMALIZADA", "persistencia": "COMPLETA",
        "origen": "MULTIFACTURA", "liberado": True}]
    assert set(cliente.flags_observadas) == {FLAGS_ESPERADOS}


def test_4_2_replay_restaura_parcial_revision(base, tmp_path):
    cliente = ClientePg17(base)
    documento = _registrar(base, cliente, _truncado(tmp_path, list(range(8))), 1)
    _worker(cliente, tmp_path, "uno").ejecutar_una_manual()
    assert (_estado(base, documento)["estado_lectura"], _estado(base, documento)["estado_persistencia"]) == (
        "REVISION", "PARCIAL")
    facturas = _huella_facturas(base)
    _reprocesar(base, documento)
    _worker(cliente, tmp_path, "dos").ejecutar_una_manual()
    estado = _estado(base, documento)
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("REVISION", "PARCIAL")
    assert estado["bloqueado_por"] is None
    assert _locks(base) == "0|0"
    assert _huella_facturas(base) == facturas
    assert [r["liberado"] for r in _replays(base, documento)] == [True]


def test_4_1b_retransmision_sin_claim_no_cambia_estado(base, tmp_path):
    cliente = ClientePg17(base)
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 1)
    _worker(cliente, tmp_path, "uno").ejecutar_una_manual()
    nombre, payload = [(n, p) for n, p in cliente.rpcs if n == "cf_persistir_documento_multifactura"][0]
    antes = _estado(base, alliance)
    cliente.rpc(nombre, payload).execute()
    assert _estado(base, alliance) == antes
    assert [r["liberado"] for r in _replays(base, alliance)] == [False]


# --------------------------------------------------------------------------
# 4.3 Proveedor no soportado (R2)
# --------------------------------------------------------------------------


def test_4_3_proveedor_no_soportado_no_bloquea_la_cola(base, tmp_path):
    cliente = ClientePg17(base, vigilar_flags=True)
    hefame = _registrar(base, cliente, HEFAME.read_bytes(), 1)
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 2)
    _worker(cliente, tmp_path, "uno").ejecutar_una_manual()
    estado = _estado(base, hefame)
    assert estado["estado_lectura"] == "PROVEEDOR_NO_SOPORTADO"
    assert estado["proximo_reintento_at"] is None and estado["bloqueado_por"] is None
    assert base.sql(f"select intentos_fallo_normalizacion, ultima_clase_fallo from public.documentos_facturas "
                    f"where id={_lit(hefame)}") == "0|NO_SOPORTADO"
    assert base.json(f"select clase_fallo from public.normalizacion_ejecuciones where documento_id={_lit(hefame)}") == [
        {"clase_fallo": "NO_SOPORTADO"}]
    resultado = _worker(cliente, tmp_path, "dos").ejecutar_una_manual()
    assert resultado.documentos_reclamados == 1
    assert len(_facturas_de(base, alliance)) == 3
    assert _estado(base, hefame)["estado_lectura"] == "PROVEEDOR_NO_SOPORTADO"
    assert _siguiente_candidato(base) not in {hefame, alliance}
    _reprocesar(base, hefame)
    assert _siguiente_candidato(base) == hefame
    assert _locks(base) == "0|0"
    assert set(cliente.flags_observadas) == {FLAGS_ESPERADOS}


# --------------------------------------------------------------------------
# 4.4 Error persistente (R3)
# --------------------------------------------------------------------------


def test_4_4_error_persistente_backoff_y_revision(base, tmp_path):
    cliente = ClientePg17(base, vigilar_flags=True)
    defectuoso = _registrar(base, cliente, ALLIANCE.read_bytes(), 1, hash_registrado="f" * 64)
    segundo = _registrar(base, cliente, HEFAME.read_bytes(), 2)

    _worker(cliente, tmp_path, "i1").ejecutar_una_manual()
    estado = _estado(base, defectuoso)
    assert estado["estado_lectura"] == "ERROR"
    assert 3500 < _segundos_hasta_reintento(base, defectuoso) <= 3600
    assert base.sql(f"select intentos_fallo_normalizacion from public.documentos_facturas "
                    f"where id={_lit(defectuoso)}") == "1"

    _worker(cliente, tmp_path, "s").ejecutar_una_manual()
    assert _estado(base, segundo)["estado_lectura"] == "PROVEEDOR_NO_SOPORTADO"
    assert _estado(base, defectuoso)["estado_lectura"] == "ERROR"

    _avanzar_tiempo(base, defectuoso)
    assert _siguiente_candidato(base) == defectuoso
    _worker(cliente, tmp_path, "i2").ejecutar_una_manual()
    assert _estado(base, defectuoso)["estado_lectura"] == "ERROR"
    assert 6 * 3600 - 100 < _segundos_hasta_reintento(base, defectuoso) <= 6 * 3600

    _avanzar_tiempo(base, defectuoso)
    _worker(cliente, tmp_path, "i3").ejecutar_una_manual()
    assert _estado(base, defectuoso)["estado_lectura"] == "ERROR"
    assert 24 * 3600 - 100 < _segundos_hasta_reintento(base, defectuoso) <= 24 * 3600

    _avanzar_tiempo(base, defectuoso)
    _worker(cliente, tmp_path, "i4").ejecutar_una_manual()
    estado = _estado(base, defectuoso)
    assert estado["estado_lectura"] == "REVISION"
    assert estado["proximo_reintento_at"] is None and estado["bloqueado_por"] is None
    assert base.sql(f"select intentos_fallo_normalizacion, ultima_clase_fallo from public.documentos_facturas "
                    f"where id={_lit(defectuoso)}") == "4|DEFECTO_DOCUMENTO"
    ejecuciones = _ejecuciones(base, defectuoso)
    assert [(e["estado"], e["error_detalle"]) for e in ejecuciones] == [("ERROR", "SHA256_NO_COINCIDE")] * 4
    claves = [e["idempotency_key"] for e in ejecuciones]
    base_clave = f"normalizacion:{defectuoso}:MANUAL_ONE_SHOT:fallo"
    assert claves[0] == base_clave and len(set(claves)) == 4
    assert all(c.startswith(base_clave + ":intento:") for c in claves[1:])
    assert _siguiente_candidato(base) != defectuoso
    assert _facturas_de(base, defectuoso) == []
    assert _locks(base) == "0|0"
    assert set(cliente.flags_observadas) == {FLAGS_ESPERADOS}

    _reprocesar(base, defectuoso)
    assert _siguiente_candidato(base) == defectuoso
    assert base.sql(f"select intentos_fallo_normalizacion from public.documentos_facturas "
                    f"where id={_lit(defectuoso)}") == "0"


def test_4_4b_parametros_configurables(base, tmp_path):
    assert base.sql("select normalizacion_max_intentos, normalizacion_backoff from public.cf_configuracion") == (
        "4|{01:00:00,06:00:00,24:00:00}")
    base.sql("update public.cf_configuracion set normalizacion_max_intentos = 1;")
    cliente = ClientePg17(base)
    defectuoso = _registrar(base, cliente, ALLIANCE.read_bytes(), 1, hash_registrado="f" * 64)
    _worker(cliente, tmp_path).ejecutar_una_manual()
    assert _estado(base, defectuoso)["estado_lectura"] == "REVISION"
    with pytest.raises(RuntimeError, match="cf_configuracion_reintentos_check"):
        base.sql("update public.cf_configuracion set normalizacion_backoff = '{}'::interval[];")


# --------------------------------------------------------------------------
# 4.5 Ordering (R4)
# --------------------------------------------------------------------------


def _escenario_ordering(pg):
    cliente = ClientePg17(pg)
    fijos = [
        ("00000000-0000-4000-8000-000000000003", 3), ("00000000-0000-4000-8000-000000000001", 1),
        ("00000000-0000-4000-8000-000000000002", 1), ("00000000-0000-4000-8000-000000000004", 5),
    ]
    for documento_id, minuto in fijos:
        pg.sql("insert into public.documentos_facturas(id,farmacia,archivo_nombre,archivo_ruta,archivo_hash,"
               f"fecha_importacion) values ({_lit(documento_id)},'PIO','x.pdf',{_lit('PIO/o/' + documento_id)},"
               f"md5({_lit(documento_id)})||md5({_lit(documento_id)}),"
               f"timestamptz '2000-01-01' + interval '{minuto} minutes');")
    pg.sql("update public.documentos_facturas set estado_lectura='ERROR' "
           "where id='00000000-0000-4000-8000-000000000004';")
    _reprocesar(pg, "00000000-0000-4000-8000-000000000003")
    return cliente


def test_4_5_ordering_entre_elegibles_identico_a_16(pg17_nueva_base):
    # Mismos datos antes/despues: dos copias de la misma plantilla 16; la 17 se
    # aplica solo a una (el seed genera ids y fechas propios por plantilla).
    base16, base17 = pg17_nueva_base("16"), pg17_nueva_base("16")
    base17.sql(MIGRACION_17.read_text(encoding="utf-8"))
    for pg in (base16, base17):
        _escenario_ordering(pg)
    orden16, orden17 = orden_de_claims(base16, 20), orden_de_claims(base17, 20)
    assert len(orden16) == 20 and orden16 == orden17
    assert orden16[:4] == [
        "00000000-0000-4000-8000-000000000003", "00000000-0000-4000-8000-000000000001",
        "00000000-0000-4000-8000-000000000002", "00000000-0000-4000-8000-000000000004"]
    definiciones = (
        "select string_agg(pg_get_functiondef(p.oid), '' order by p.oid::regprocedure::text) "
        "from pg_proc p where p.proname like 'cf_reclamar_documento_normalizacion%'")
    assert base16.sql(definiciones) == base17.sql(definiciones)


# --------------------------------------------------------------------------
# 4.8 Rollback y idempotencia de la migracion
# --------------------------------------------------------------------------


def test_4_8_rollback_devuelve_el_esquema_16(pg17_nueva_base):
    assert esquema(pg17_nueva_base("16")) == esquema(pg17_nueva_base("16_rollback"))


def test_migracion_17_idempotente(pg17_nueva_base):
    una_vez = pg17_nueva_base("16")
    una_vez.sql(MIGRACION_17.read_text(encoding="utf-8"))
    dos_veces = pg17_nueva_base("17")
    assert esquema(una_vez) == esquema(dos_veces)
    assert dos_veces.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert esquema(una_vez) != esquema(pg17_nueva_base("16"))


FUNCIONES_17 = (
    "cf_cerrar_replay_normalizacion(uuid,text,uuid,text)",
    "cf_persistir_normalizacion(uuid,text,text,text,text,jsonb)",
    "cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)",
    "cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text)",
    "cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text)",
    "cf_solicitar_reprocesado(uuid,text)",
)


def _matriz(pg):
    filas = pg.json(
        "select p.oid::regprocedure::text as f, "
        "p.proacl is null or exists(select 1 from aclexplode(p.proacl) a "
        "  where a.grantee=0 and a.privilege_type='EXECUTE') as public, "
        "has_function_privilege('anon',p.oid,'EXECUTE') as anon, "
        "has_function_privilege('authenticated',p.oid,'EXECUTE') as authenticated, "
        "has_function_privilege('service_role',p.oid,'EXECUTE') as service_role "
        "from pg_proc p where p.pronamespace='public'::regnamespace")
    return {f["f"].replace(" ", ""): f for f in filas}


def test_2as_privilegios_con_default_acl_de_supabase(pg17_nueva_base):
    """Emula pg_default_acl productivo (EXECUTE por defecto a anon/authenticated/
    service_role) y exige que ninguna funcion de la 17 quede ejecutable por
    PUBLIC, anon ni authenticated."""
    pg = pg17_nueva_base("16")
    pg.sql("alter default privileges for role postgres in schema public "
           "grant execute on functions to anon, authenticated, service_role;")
    assert _matriz(pg)["cf_solicitar_reprocesado(uuid,text)"]["authenticated"] is True
    pg.sql(MIGRACION_17.read_text(encoding="utf-8"))
    matriz = _matriz(pg)
    for firma in FUNCIONES_17:
        fila = matriz[firma]
        assert (fila["public"], fila["anon"], fila["authenticated"]) == (False, False, False), firma
    assert matriz["cf_cerrar_replay_normalizacion(uuid,text,uuid,text)"]["service_role"] is False
    for firma in FUNCIONES_17[1:5]:
        assert matriz[firma]["service_role"] is True, firma


def test_permisos_migracion_17(base):
    assert base.sql(
        "select has_function_privilege('service_role','public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text)','execute'),"
        "has_function_privilege('service_role','public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text)','execute'),"
        "has_function_privilege('service_role','public.cf_cerrar_replay_normalizacion(uuid,text,uuid,text)','execute'),"
        "has_function_privilege('anon','public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text)','execute'),"
        "has_function_privilege('authenticated','public.cf_cerrar_replay_normalizacion(uuid,text,uuid,text)','execute')"
    ) == "t|t|f|f|f"
