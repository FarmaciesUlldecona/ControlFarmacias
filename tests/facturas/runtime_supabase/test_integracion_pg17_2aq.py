"""Hito 2AQ: extremo a extremo del compositor manual sobre PostgreSQL 17 REAL local.

Se ejecuta sobre tres variantes de esquema (harness ``pg17_local``):
- ``16``: cadena certificada 2AN (06-16). Fija los defectos D1/D2 hallados en 2AQ.
- ``17``: 16 + migracion 17 (Hito 2AR). Regresion 4.6: D1/D2 corregidos.
- ``16_rollback``: 16 + 17 + rollback. Certificacion 4.8: vuelve al estado 16.
Skip si Docker, la imagen o los fixtures no estan disponibles.
"""
from __future__ import annotations

import pytest

from pg17_local import (
    ALLIANCE, FLAGS_ESPERADOS, FLAGS_SQL, HEFAME, ClientePg17, _ejecuciones, _estado,
    _facturas_de, _huella_facturas, _huella_resto, _lit, _locks, _registrar,
    _siguiente_candidato, _truncado, _worker,
)


pytestmark = pytest.mark.pg17_local


@pytest.fixture(params=["16", "17", "16_rollback"])
def variante(request):
    return request.param


@pytest.fixture
def base(pg17_nueva_base, variante):
    return pg17_nueva_base(variante)


@pytest.fixture
def cliente(base, variante):
    return ClientePg17(base, compat_16=variante != "17")


# --------------------------------------------------------------------------
# 2.1 a 2.6
# --------------------------------------------------------------------------


def test_pg17_esquema_y_flags(base):
    assert base.sql("show server_version").startswith("17.")
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert base.sql(
        "select to_regprocedure('public.cf_reclamar_documento_normalizacion_manual_one_shot(text,integer)') is not null,"
        "to_regprocedure('public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)') is not null,"
        "has_function_privilege('service_role','public.cf_reclamar_documento_normalizacion_nucleo(text,integer,text)','execute'),"
        "(select pg_get_constraintdef(oid) like '%MANUAL_ONE_SHOT%' from pg_constraint "
        " where conname='normalizacion_ejecuciones_disparador_check')") == "t|t|f|t"


def test_pg17_2_1_alliance_apto(base, cliente, tmp_path, variante):
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 1)
    segundo = _registrar(base, cliente, HEFAME.read_bytes(), 2)
    resto, facturas_previas = _huella_resto(base, alliance), _huella_facturas(base)
    conciliaciones = base.sql("select count(*) from public.conciliaciones")
    resultado = _worker(cliente, tmp_path).ejecutar_una_manual()
    assert resultado.documentos_reclamados == 1
    assert resultado.facturas_conciliacion_reclamadas == 0
    assert [n for n, _ in cliente.rpcs] == [
        "cf_reclamar_documento_normalizacion_manual_one_shot", "cf_persistir_documento_multifactura"]
    assert cliente.descargas == [f"PIO/2AQ/{alliance}.pdf"]
    facturas = _facturas_de(base, alliance)
    assert [(f["numero_factura"], f["total"]) for f in facturas] == [
        ("08011303", "9670.9200"), ("08011304", "4195.2400"), ("08011305", "141.2100")]
    assert {f["estado_conciliacion_cf"] for f in facturas} == {"PENDIENTE_CONCILIAR"}
    ejecuciones = _ejecuciones(base, alliance)
    assert [(e["disparador"], e["modo"], e["estado"]) for e in ejecuciones] == [
        ("MANUAL_ONE_SHOT", "MANUAL_ONE_SHOT", "COMPLETADA")]
    estado = _estado(base, alliance)
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("NORMALIZADA", "COMPLETA")
    assert estado["bloqueado_por"] is None and estado["bloqueado_hasta"] is None
    assert _huella_resto(base, alliance) == resto
    assert _estado(base, segundo)["estado_lectura"] == "PENDIENTE"
    assert base.sql("select count(*) from public.conciliaciones") == conciliaciones
    assert base.sql("select count(*) from public.facturas") == str(3 + 3)
    assert facturas_previas != _huella_facturas(base)
    assert _locks(base) == "0|0"
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_pg17_2_2_hefame_no_soportado_y_cabeza_de_cola(base, cliente, tmp_path, variante):
    hefame = _registrar(base, cliente, HEFAME.read_bytes(), 1)
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 2)
    resto, facturas_previas = _huella_resto(base, hefame), _huella_facturas(base)
    resultado = _worker(cliente, tmp_path).ejecutar_una_manual()
    assert resultado.documentos_reclamados == 0
    assert [n for n, _ in cliente.rpcs] == [
        "cf_reclamar_documento_normalizacion_manual_one_shot", "cf_registrar_fallo_normalizacion"]
    ejecuciones = _ejecuciones(base, hefame)
    assert [(e["disparador"], e["estado"], e["error_codigo"], e["error_detalle"]) for e in ejecuciones] == [
        ("MANUAL_ONE_SHOT", "ERROR", "DocumentoNoAptoManual", "PROVEEDOR_NO_SOPORTADO_MANUAL")]
    estado = _estado(base, hefame)
    assert estado["estado_lectura"] == ("PROVEEDOR_NO_SOPORTADO" if variante == "17" else "ERROR")
    assert estado["estado_persistencia"] == "PENDIENTE"
    assert estado["ultimo_error_codigo"] == "DocumentoNoAptoManual"
    assert estado["proximo_reintento_at"] is None
    assert estado["bloqueado_por"] is None and estado["bloqueado_hasta"] is None
    assert _facturas_de(base, hefame) == [] and _facturas_de(base, alliance) == []
    assert _huella_facturas(base) == facturas_previas
    assert _huella_resto(base, hefame) == resto
    assert _estado(base, alliance)["estado_lectura"] == "PENDIENTE"
    if variante == "17":
        # R2: el documento no soportado deja de bloquear la cabeza de cola.
        assert _siguiente_candidato(base) == alliance
    else:
        # D2: sin backoff ni penalizacion el documento fallido sigue siendo el n.1.
        assert _siguiente_candidato(base) == hefame
    assert _locks(base) == "0|0"
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_pg17_2_3_sha_incorrecto(base, cliente, tmp_path, variante):
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 1, hash_registrado="f" * 64)
    segundo = _registrar(base, cliente, HEFAME.read_bytes(), 2)
    _worker(cliente, tmp_path).ejecutar_una_manual()
    ejecuciones = _ejecuciones(base, alliance)
    assert [(e["estado"], e["error_detalle"]) for e in ejecuciones] == [("ERROR", "SHA256_NO_COINCIDE")]
    estado = _estado(base, alliance)
    assert estado["estado_lectura"] == "ERROR" and estado["bloqueado_por"] is None
    # R3 (17): backoff tras el primer fallo; en 16 no hay backoff.
    assert (estado["proximo_reintento_at"] is not None) == (variante == "17")
    assert _facturas_de(base, alliance) == []
    assert not (tmp_path / "a" / f"{alliance}.pdf").exists()
    assert _estado(base, segundo)["estado_lectura"] == "PENDIENTE"
    assert _locks(base) == "0|0"
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_pg17_2_4_multifactura_con_factura_incompleta(base, cliente, tmp_path, variante):
    documento = _registrar(base, cliente, _truncado(tmp_path, list(range(8))), 1)
    segundo = _registrar(base, cliente, HEFAME.read_bytes(), 2)
    _worker(cliente, tmp_path).ejecutar_una_manual()
    assert [(f["numero_factura"]) for f in _facturas_de(base, documento)] == ["08011303", "08011304"]
    estado = _estado(base, documento)
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("REVISION", "PARCIAL")
    inventario = {i["componentes"][1]: i["estado"] for i in estado["inventario_facturas"]}
    assert inventario == {"08011304": "PERSISTIDAS", "08011303": "PERSISTIDAS",
                          "08011305": "REQUIERE_REVISION"}
    historial = base.json(
        "select evento,estado_nuevo->>'estado_persistencia' as persistencia from public.historial_facturas "
        f"where documento_id={_lit(documento)} and evento='INVENTARIO_MULTIFACTURA'")
    assert historial == [{"evento": "INVENTARIO_MULTIFACTURA", "persistencia": "PARCIAL"}]
    assert estado["bloqueado_por"] is None
    # REVISION no es reclamable: el siguiente candidato ya no es este documento.
    assert _siguiente_candidato(base) == segundo
    assert _locks(base) == "0|0"
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_pg17_limite_conocido_factura_entera_omitida(base, cliente, tmp_path, variante):
    documento = _registrar(base, cliente, _truncado(tmp_path, list(range(7))), 1)
    _worker(cliente, tmp_path).ejecutar_una_manual()
    assert [f["numero_factura"] for f in _facturas_de(base, documento)] == ["08011303", "08011304"]
    estado = _estado(base, documento)
    # LIMITE CONOCIDO: la omision de la factura entera no deja rastro documental.
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("NORMALIZADA", "COMPLETA")
    assert len(estado["inventario_facturas"]) == 2


def test_pg17_2_5_idempotencia(base, cliente, tmp_path, variante):
    alliance = _registrar(base, cliente, ALLIANCE.read_bytes(), 1)
    _worker(cliente, tmp_path, "uno").ejecutar_una_manual()
    facturas = _huella_facturas(base)
    primera = [p for n, p in cliente.rpcs if n == "cf_persistir_documento_multifactura"][0]
    base.sql(f"select public.cf_solicitar_reprocesado({_lit(alliance)}::uuid,'PIO-LOCAL-2AQ');")
    assert _siguiente_candidato(base) == alliance
    _worker(cliente, tmp_path, "dos").ejecutar_una_manual()
    segunda = [p for n, p in cliente.rpcs if n == "cf_persistir_documento_multifactura"][1]
    assert primera["p_idempotency_key"] == segunda["p_idempotency_key"]
    assert primera["p_resultado_hash"] == segunda["p_resultado_hash"]
    assert _huella_facturas(base) == facturas
    assert base.sql(
        f"select count(*) from public.facturas where documento_id={_lit(alliance)}") == "3"
    assert len(_ejecuciones(base, alliance)) == 1
    estado = _estado(base, alliance)
    if variante == "17":
        # R1: el replay restaura el estado final y libera el claim en el acto.
        assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("NORMALIZADA", "COMPLETA")
        assert estado["bloqueado_por"] is None and estado["bloqueado_hasta"] is None
        assert _locks(base) == "0|0"
        assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS
        return
    # D1 (esquema 16): el replay idempotente de la RPC multifactura retorna antes de
    # actualizar el documento. El claim del segundo worker queda retenido y el
    # documento en NORMALIZANDO; al expirar el lock no vuelve a ser reclamable.
    assert (estado["estado_lectura"], estado["estado_persistencia"]) == ("NORMALIZANDO", "COMPLETA")
    assert estado["bloqueado_por"] == "manual-2aq-dos" and estado["bloqueado_hasta"] is not None
    assert _locks(base) == "1|0"
    base.sql(f"update public.documentos_facturas set bloqueado_hasta=now()-interval '1 second' where id={_lit(alliance)};")
    assert _siguiente_candidato(base) != alliance
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_pg17_2_6_flags_constantes_durante_todo(base, cliente, tmp_path, variante):
    _registrar(base, cliente, ALLIANCE.read_bytes(), 1)
    cliente.vigilar_flags = True
    _worker(cliente, tmp_path).ejecutar_una_manual()
    assert len(cliente.flags_observadas) == 4
    assert set(cliente.flags_observadas) == {FLAGS_ESPERADOS}
