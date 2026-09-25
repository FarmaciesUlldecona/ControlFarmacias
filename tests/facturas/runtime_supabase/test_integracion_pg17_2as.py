"""Hito 2AS: la migracion 17 funciona ejecutada COMO service_role (sin superusuario)
con los privilegios por defecto de Supabase emulados (pg_default_acl productivo).
"""
from __future__ import annotations

import json

import pytest

from pg17_local import (
    ALLIANCE, FLAGS_ESPERADOS, FLAGS_SQL, MIGRACION_17, ClientePg17, _ejecuciones, _estado,
    _facturas_de, _huella_facturas, _lit, _locks, _registrar, _worker,
)


pytestmark = pytest.mark.pg17_local

FUNCIONES_17 = (
    "cf_cerrar_replay_normalizacion", "cf_persistir_normalizacion",
    "cf_persistir_documento_multifactura", "cf_registrar_fallo_normalizacion",
    "cf_solicitar_reprocesado",
)


@pytest.fixture
def base(pg17_nueva_base):
    pg = pg17_nueva_base("16")
    pg.sql("alter default privileges for role postgres in schema public "
           "grant execute on functions to anon, authenticated, service_role;")
    pg.sql(MIGRACION_17.read_text(encoding="utf-8"))
    return pg


def _como_service_role(pg, sentencia: str) -> str:
    """Ejecuta con SET ROLE service_role; devuelve tambien el rol efectivo."""
    return pg.sql(f"set role service_role; select current_user; {sentencia}")


def _reclamar(pg, worker: str) -> str:
    salida = _como_service_role(
        pg, f"select id from public.cf_reclamar_documento_normalizacion_manual_one_shot({_lit(worker)}, 300);")
    rol, documento = salida.splitlines()
    assert rol == "service_role"
    return documento


def _procesar_y_reprocesar(pg, tmp_path):
    cliente = ClientePg17(pg)
    alliance = _registrar(pg, cliente, ALLIANCE.read_bytes(), 1)
    _worker(cliente, tmp_path, "uno").ejecutar_una_manual()
    pg.sql(f"select public.cf_solicitar_reprocesado({_lit(alliance)}::uuid,'PIO-LOCAL-2AS');")
    return cliente, alliance


def test_security_definer_de_las_funciones_17(base):
    filas = base.json(
        "select p.oid::regprocedure::text as f, p.prosecdef as definer, pg_get_userbyid(p.proowner) as owner "
        "from pg_proc p where p.pronamespace='public'::regnamespace and p.proname in ("
        + ",".join(_lit(f) for f in FUNCIONES_17) + ")")
    assert len(filas) == 7
    assert all(f["definer"] is True and f["owner"] == "postgres" for f in filas), filas


def test_a_replay_multifactura_como_service_role(base, tmp_path):
    cliente, alliance = _procesar_y_reprocesar(base, tmp_path)
    facturas = _huella_facturas(base)
    payload = [p for n, p in cliente.rpcs if n == "cf_persistir_documento_multifactura"][0]
    assert _reclamar(base, "sr-a") == alliance
    args = ", ".join([
        f"p_documento_id => {_lit(alliance)}", "p_worker_id => 'sr-a'",
        f"p_idempotency_key => {_lit(payload['p_idempotency_key'])}",
        f"p_resultado_hash => {_lit(payload['p_resultado_hash'])}",
        f"p_resultado => {_lit(json.dumps(payload['p_resultado'], ensure_ascii=False))}::jsonb",
        "p_segmentos_autorizados => array[" + ",".join(_lit(s) for s in payload["p_segmentos_autorizados"]) + "]::text[]",
        "p_disparador => 'MANUAL_ONE_SHOT'",
    ])
    _como_service_role(base, f"select public.cf_persistir_documento_multifactura({args});")
    estado = _estado(base, alliance)
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("NORMALIZADA", "COMPLETA")
    assert estado["bloqueado_por"] is None and _locks(base) == "0|0"
    assert _huella_facturas(base) == facturas and len(_ejecuciones(base, alliance)) == 1
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_b_replay_persistir_normalizacion_como_service_role(base, tmp_path):
    cliente, alliance = _procesar_y_reprocesar(base, tmp_path)
    facturas = _huella_facturas(base)
    clave = _ejecuciones(base, alliance)[0]["idempotency_key"]
    assert _reclamar(base, "sr-b") == alliance
    _como_service_role(base, (
        f"select public.cf_persistir_normalizacion({_lit(alliance)}::uuid, 'sr-b', 'MANUAL', "
        f"{_lit(clave)}, 'h', '{{}}'::jsonb);"))
    estado = _estado(base, alliance)
    assert estado["estado_lectura"] == "NORMALIZADA"
    assert estado["bloqueado_por"] is None and _locks(base) == "0|0"
    assert _huella_facturas(base) == facturas and len(_ejecuciones(base, alliance)) == 1
    replay = base.json(
        "select detalle->>'origen' as origen, (detalle->>'claim_liberado')::boolean as liberado "
        f"from public.historial_facturas where documento_id={_lit(alliance)} "
        "and evento='NORMALIZACION_REPLAY_IDEMPOTENTE'")
    assert replay == [{"origen": "NORMALIZACION", "liberado": True}]


def _registrar_pendiente(pg, orden: int) -> str:
    cliente = ClientePg17(pg)
    return _registrar(pg, cliente, ALLIANCE.read_bytes(), orden)


def test_c_fallo_siete_parametros_como_service_role(base):
    documento = _registrar_pendiente(base, 1)
    assert _reclamar(base, "sr-c") == documento
    _como_service_role(base, (
        f"select public.cf_registrar_fallo_normalizacion({_lit(documento)}::uuid, 'sr-c', 'MANUAL_ONE_SHOT', "
        "'k-c', 'DocumentoNoAptoManual', 'SHA256_NO_COINCIDE', 'DEFECTO_DOCUMENTO');"))
    estado = _estado(base, documento)
    assert estado["estado_lectura"] == "ERROR" and estado["proximo_reintento_at"] is not None
    assert estado["bloqueado_por"] is None and _locks(base) == "0|0"
    assert [(e["estado"], e["error_detalle"]) for e in _ejecuciones(base, documento)] == [
        ("ERROR", "SHA256_NO_COINCIDE")]


def test_d_fallo_envoltorio_seis_parametros_como_service_role(base):
    documento = _registrar_pendiente(base, 1)
    assert _reclamar(base, "sr-d") == documento
    _como_service_role(base, (
        f"select public.cf_registrar_fallo_normalizacion({_lit(documento)}::uuid, 'sr-d', 'MANUAL_ONE_SHOT', "
        "'k-d', 'RuntimeError', 'fallo sin clase');"))
    estado = _estado(base, documento)
    assert estado["estado_lectura"] == "ERROR" and estado["bloqueado_por"] is None
    assert base.sql(f"select ultima_clase_fallo, intentos_fallo_normalizacion from public.documentos_facturas "
                    f"where id={_lit(documento)}") == "TRANSITORIO|1"
    assert _facturas_de(base, documento) == [] and _locks(base) == "0|0"


def test_service_role_no_invoca_cerrar_replay_directamente(base):
    with pytest.raises(RuntimeError, match="permission denied"):
        _como_service_role(base, (
            "select public.cf_cerrar_replay_normalizacion(gen_random_uuid(), 'x', gen_random_uuid(), 'MULTIFACTURA');"))
