"""Hito 2BD: migracion 22 (resincronizacion de albaranes) certificada en PostgreSQL 17 local.

Plantillas (pg17_local): "21" (estado productivo actual), "22" = 21 + migracion 22 dos veces,
"22_rollback" = 22 + rollback. Farmatic SIMULADO: espejo de ``Supabase.albaranes`` con los
cambios de cada caso (sin Farmatic real ni produccion). El caso de modificacion es un albaran
sintetico (``08Z90001``, 500,86 -> 504,02), no 08C20268.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta

import pytest

import pg17_local as pgl
from pg17_local import (FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, ClientePg17, _lit, _locks, base_desde,
                        esquema)
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    DSN_FICTICIO, _datos_previos, _huella, _preparar_2ao, _sr, contenedor_tcp)
from test_integracion_pg17_2ba import _persistir_directo
from src.models.albaran import Albaran
from src.supabase_client import resincronizacion_albaranes as resync

pytestmark = pytest.mark.pg17_local

MIGRACION_22 = MIG / "22_cf_resincronizacion_albaranes.sql"
ROLLBACK_22 = MIG / "22_cf_resincronizacion_albaranes.rollback.sql"
CAMBIOS = "public.albaranes_cambios"
HOY = date.today()
RECIENTE = (HOY - timedelta(days=10)).isoformat()
HUELLAS_SIN_22 = {
    "facturas": "select to_jsonb(f) from public.facturas f",
    "conciliaciones": "select to_jsonb(c) from public.conciliaciones c",
    "detalles": "select to_jsonb(d) from public.conciliacion_detalles d",
    "reservas": "select to_jsonb(r) from public.conciliacion_albaranes_reservados r",
    "albaranes": "select to_jsonb(a) - 'id_recepcion' from public.albaranes a",
    "historial": "select to_jsonb(h) from public.historial_facturas h",
    "configuracion": "select to_jsonb(c) from public.cf_configuracion c",
}


@pytest.fixture
def base22(pg17_nueva_base):
    return pg17_nueva_base("22")


def _albaran(pg, contador, numero, puc, *, pvp="740.00", fecha=RECIENTE, id_proveedor="2", descuento="32.22",
             recepcion=None):
    # Sin recepcion no se nombra la columna: el helper sirve tambien para el esquema 21.
    columna, valor = (",id_recepcion", f", {_lit(recepcion)}") if recepcion is not None else ("", "")
    pg.sql("insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
           f"importe_pvp,importe_puc,descuento,estado{columna}) values ('PIO', "
           f"{contador}, {_lit(id_proveedor)}, '1.- SAFA', {_lit(numero)}, date {_lit(fecha)}, {pvp}, {puc}, "
           f"{descuento}, 'PENDIENTE'{valor});")


def _fila(pg, contador) -> dict:
    return pg.json("select id_contador, id_proveedor, numero_albaran, fecha::text, importe_puc::text, "
                   "importe_pvp::text, descuento::text, id_recepcion from public.albaranes "
                   f"where farmacia = 'PIO' and id_contador = {contador}")[0]


def _cambios(pg, contador=None) -> list[dict]:
    filtro = f"where id_contador = {contador}" if contador is not None else ""
    return pg.json(f"select id_contador, origen, campo, valor_anterior, valor_nuevo, accion, motivo, detalle "
                   f"from {CAMBIOS} {filtro} order by id")


def _valores(numero="08Z90001", puc="504.02", *, pvp="740.00", fecha=RECIENTE, id_proveedor="0002 ",
             recepcion=50898, descuento="32.22") -> dict:
    return {"id_proveedor": id_proveedor, "proveedor": "1.- SAFA", "numero_albaran": numero, "fecha": fecha,
            "importe_pvp": pvp, "importe_puc": puc, "descuento": descuento, "id_recepcion": recepcion}


def _resync(pg, contador, valores, origen="RESYNC_VENTANA"):
    return ClientePg17(pg).rpc("cf_resincronizar_albaran", {
        "p_farmacia": "PIO", "p_id_contador": contador, "p_valores": valores, "p_origen": origen,
        "p_ejecucion_id": "test-2bd"}).execute().data


def _ausente(pg, contador):
    return ClientePg17(pg).rpc("cf_registrar_albaran_ausente", {
        "p_farmacia": "PIO", "p_id_contador": contador, "p_origen": "RESYNC_VENTANA",
        "p_ejecucion_id": "test-2bd"}).execute().data


# --------------------------------------------------------------------------- esquema y privilegios

def test_rollback_22_devuelve_exactamente_el_esquema_21(pg17_nueva_base):
    assert esquema(pg17_nueva_base("22_rollback")) == esquema(pg17_nueva_base("21"))
    assert esquema(pg17_nueva_base("22")) != esquema(pg17_nueva_base("21"))


def test_22_no_altera_datos_existentes_ni_conciliaciones(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("21")
    _datos_previos(pg, tmp_path)
    _albaran(pg, 990001, "08Z99001", "10.00")
    antes = {k: _huella(pg, q) for k, q in HUELLAS_SIN_22.items()}
    referencia = esquema(pg17_nueva_base("22"))
    pg.sql(MIGRACION_22.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_22.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in HUELLAS_SIN_22.items()} == antes
    assert pg.sql("select count(*), count(id_recepcion) from public.albaranes where id_contador = 990001") == "1|0"
    assert pg.sql(f"select count(*) from {CAMBIOS}") == "0"
    assert esquema(pg) == referencia
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_privilegios_de_la_22(base22):
    funciones = {f["f"]: f for f in base22.json(
        "select p.oid::regprocedure::text as f, p.prosecdef as definer, pg_get_userbyid(p.proowner) as owner, "
        "exists(select 1 from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a where a.grantee = 0) "
        "  as public, has_function_privilege('anon', p.oid, 'EXECUTE') as anon, "
        "has_function_privilege('authenticated', p.oid, 'EXECUTE') as authenticated, "
        "has_function_privilege('service_role', p.oid, 'EXECUTE') as service_role "
        "from pg_proc p where p.pronamespace = 'public'::regnamespace and p.proname in ("
        "'cf_resincronizar_albaran', 'cf_registrar_albaran_ausente', 'cf_persistir_conciliacion', "
        "'cf_albaran_ausente_abierto', 'cf_id_proveedor_comparable', 'cf_albaranes_cambios_append_only')")}
    rpcs = ("cf_resincronizar_albaran(text,bigint,jsonb,text,text)",
            "cf_registrar_albaran_ausente(text,bigint,text,text)",
            "cf_persistir_conciliacion(uuid,text,text,text,jsonb)")
    for firma, f in funciones.items():
        nombre = firma.replace("public.", "").replace(" ", "")
        assert (f["owner"], f["public"], f["anon"], f["authenticated"]) == ("postgres", False, False, False), firma
        assert f["service_role"] is (nombre in rpcs), firma
        if nombre in rpcs:
            assert f["definer"] is True, firma
    [t] = base22.json(
        "select c.relrowsecurity as rls, pg_get_userbyid(c.relowner) as owner, "
        "has_table_privilege('service_role', c.oid, 'SELECT') as sr_select, "
        "has_table_privilege('service_role', c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE') as sr_escribe, "
        "has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE') as anon, "
        "has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE') as authenticated, "
        "has_sequence_privilege('service_role', 'public.albaranes_cambios_id_seq', 'USAGE,SELECT,UPDATE') as sr_seq, "
        "has_table_privilege('service_role', 'public.albaranes', 'UPDATE') as sr_update_albaranes "
        f"from pg_class c where c.oid = '{CAMBIOS}'::regclass")
    assert t == {"rls": True, "owner": "postgres", "sr_select": True, "sr_escribe": False, "anon": False,
                 "authenticated": False, "sr_seq": False, "sr_update_albaranes": False}
    with pytest.raises(RuntimeError, match="permission denied"):
        base22.sql(f"set role anon; select count(*) from {CAMBIOS};")
    with pytest.raises(RuntimeError, match="permission denied"):
        base22.sql("set role service_role; update public.albaranes set importe_puc = 1 where false;")


def test_historial_append_only(base22):
    _albaran(base22, 990001, "08Z90001", "500.86")
    _resync(base22, 990001, _valores())
    for sentencia in (f"update {CAMBIOS} set motivo = 'x';", f"delete from {CAMBIOS};", f"truncate {CAMBIOS};"):
        with pytest.raises(RuntimeError, match="ALBARANES_CAMBIOS_APPEND_ONLY"):
            base22.sql(sentencia)


# --------------------------------------------------------------------------- RPC

def test_caso_sintetico_modificado_sin_reserva_se_actualiza_con_historial(base22):
    """Patrón de 08C20268 con un albarán sintético: Farmatic corrige el PUC 500,86 -> 504,02."""
    _albaran(base22, 990001, "08Z90001", "500.86")
    r = _resync(base22, 990001, _valores())
    assert (r["accion"], r["motivo"], r["revision_cerrada"]) == ("ACTUALIZADO", None, False)
    f = _fila(base22, 990001)
    assert (f["importe_puc"], f["importe_pvp"], f["id_recepcion"], f["id_proveedor"]) == ("504.02", "740.00", 50898, "2")
    assert [(c["campo"], c["valor_anterior"], c["valor_nuevo"], c["accion"]) for c in _cambios(base22, 990001)] == [
        ("importe_puc", "500.86", "504.02", "ACTUALIZADO"), ("id_recepcion", None, "50898", "ACTUALIZADO")]
    # Idempotente: los mismos valores no escriben nada.
    assert _resync(base22, 990001, _valores())["accion"] == "SIN_CAMBIOS"
    assert len(_cambios(base22, 990001)) == 2


def test_proveedor_con_otro_formato_no_es_cambio_de_identidad(base22):
    _albaran(base22, 990001, "08Z90001", "504.02", recepcion=50898)
    for literal in ("0002", "0002 ", "2"):
        assert _resync(base22, 990001, _valores(id_proveedor=literal))["accion"] == "SIN_CAMBIOS"
    assert _cambios(base22) == []


def test_cambio_de_identidad_queda_en_revision_sin_actualizar(base22):
    _albaran(base22, 990001, "08Z90001", "500.86")
    antes = _fila(base22, 990001)
    r = _resync(base22, 990001, _valores(numero="08Z90002", id_proveedor="0101"))
    assert (r["accion"], r["motivo"]) == ("REVISION", "CAMBIO_IDENTIDAD")
    assert _fila(base22, 990001) == antes  # ni importe ni recepcion
    assert [(c["campo"], c["accion"], c["motivo"]) for c in _cambios(base22, 990001)] == [
        ("numero_albaran", "REVISION", "CAMBIO_IDENTIDAD"), ("id_proveedor", "REVISION", "CAMBIO_IDENTIDAD")]
    _resync(base22, 990001, _valores(numero="08Z90002", id_proveedor="0101"))
    assert len(_cambios(base22, 990001)) == 2  # una revision identica no se repite


def test_albaran_reservado_queda_en_revision_y_la_reserva_se_relee_en_la_bd(base22, tmp_path):
    pg = base22
    _, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    _albaran(pg, 990001, "08Z90001", "500.86")
    linea = {"tipo_relacion": "UNO_A_UNO", "importe_aplicado": "1", "estado": "COINCIDE", "albaran_farmacia": "PIO"}
    _persistir_directo(pg, ids["08007973"], [{**linea, "orden": 1, "albaran_id_contador": 990001}])
    r = _resync(pg, 990001, _valores())
    assert (r["accion"], r["motivo"]) == ("REVISION", "RESERVADO:08007973")
    f = _fila(pg, 990001)
    assert f["importe_puc"] == "500.86" and f["id_recepcion"] == 50898  # el metadato si se actualiza
    assert [(c["campo"], c["accion"], c["motivo"]) for c in _cambios(pg, 990001)] == [
        ("importe_puc", "REVISION", "RESERVADO:08007973"), ("id_recepcion", "ACTUALIZADO", None)]
    _resync(pg, 990001, _valores())
    assert len(_cambios(pg, 990001)) == 2
    assert _locks(pg) == "0|0" and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_ausente_se_registra_una_vez_queda_fuera_del_casado_y_se_cierra_al_reaparecer(base22, tmp_path):
    pg = base22
    _, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    _albaran(pg, 990004, "Q999921/2026", "3.16")
    antes = _fila(pg, 990004)
    r = _ausente(pg, 990004)
    assert (r["accion"], r["motivo"], r["reservado_por"]) == ("REVISION", "AUSENTE_EN_FARMATIC", None)
    assert _ausente(pg, 990004)["accion"] == "YA_REGISTRADA"
    assert _fila(pg, 990004) == antes  # nunca se borra ni se modifica
    linea = {"tipo_relacion": "UNO_A_UNO", "importe_aplicado": "3.16", "estado": "COINCIDE", "albaran_farmacia": "PIO"}
    with pytest.raises(RuntimeError, match="ALBARAN_AUSENTE_EN_FARMATIC:PIO:990004"):
        _persistir_directo(pg, ids["08007973"], [{**linea, "orden": 1, "albaran_id_contador": 990004}])
    # Reaparece en Farmatic con los mismos valores: se cierra la revision y vuelve a poder casarse.
    r = _resync(pg, 990004, _valores(numero="Q999921/2026", puc="3.16", pvp="740.00", recepcion=None))
    assert r["revision_cerrada"] is True
    _persistir_directo(pg, ids["08007973"], [{**linea, "orden": 1, "albaran_id_contador": 990004}])
    assert [(c["campo"], c["valor_nuevo"], c["accion"]) for c in _cambios(pg, 990004)] == [
        ("presencia", "AUSENTE", "REVISION"), ("presencia", "PRESENTE", "REVISION_CERRADA")]


def test_rpc_validan_entradas_y_fallan_cerrado(base22):
    _albaran(base22, 990001, "08Z90001", "500.86")
    with pytest.raises(RuntimeError, match="ALBARAN_NO_EXISTE"):
        _resync(base22, 123456789, _valores())
    with pytest.raises(RuntimeError, match="ORIGEN_NO_ADMITIDO"):
        _resync(base22, 990001, _valores(), origen="OTRO")
    with pytest.raises(RuntimeError, match="VALORES_INCOMPLETOS"):
        _resync(base22, 990001, {"importe_puc": "1"})
    with pytest.raises(RuntimeError, match="FARMACIA_NO_HABILITADA"):
        ClientePg17(base22).rpc("cf_registrar_albaran_ausente", {
            "p_farmacia": "RITA", "p_id_contador": 990001, "p_origen": "RESYNC_VENTANA",
            "p_ejecucion_id": "x"}).execute()
    assert _cambios(base22) == []


# --------------------------------------------------------------------------- sincronización con Farmatic simulado

def _espejo(pg, desde: date, hasta: date) -> list[Albaran]:
    filas = pg.json("select id_contador, id_proveedor, proveedor, numero_albaran, fecha::text, "
                    "importe_pvp::float8 as pvp, importe_puc::float8 as puc, descuento::float8 as dto, id_recepcion "
                    "from public.albaranes where farmacia = 'PIO' "
                    f"and fecha >= date {_lit(desde.isoformat())} and fecha < date {_lit(hasta.isoformat())} "
                    "order by id_contador")
    # Farmatic conoce la recepcion de todos (la de Supabase si ya se cargo; si no, una sintetica).
    return [Albaran(f["id_contador"], f["id_proveedor"], f["proveedor"], f["numero_albaran"],
                    datetime.fromisoformat(f["fecha"]), f["pvp"], f["puc"], f["dto"],
                    id_recepcion=f["id_recepcion"] if f["id_recepcion"] is not None
                    else 60000 + f["id_contador"] % 1000) for f in filas]


@pytest.fixture
def farmatic_simulado(base22, monkeypatch):
    """Farmatic = espejo de Supabase.albaranes + ``cambios`` + ``nuevos`` - ``ausentes``."""
    sincronizador = importlib.import_module("src.sincronizar_albaranes")
    guardado = importlib.import_module("src.supabase_client.guardar_albaranes")
    base22.sql("update public.albaranes set importe_pvp = coalesce(importe_pvp, 0), "
               "importe_puc = coalesce(importe_puc, 0), descuento = coalesce(descuento, 0);")
    estado = {"cambios": {}, "nuevos": [], "ausentes": set()}
    cliente = ClientePg17(base22, rol_tablas="service_role")

    def entre_fechas(desde, hasta):
        albaranes = [a for a in _espejo(base22, desde, hasta) if a.id_contador not in estado["ausentes"]]
        albaranes = [estado["cambios"].get(a.id_contador, a) for a in albaranes]
        return albaranes + [a for a in estado["nuevos"]
                            if desde <= a.fecha.date() < hasta
                            and a.id_contador not in {x.id_contador for x in albaranes}]

    def nuevos(ultimo):
        return [a for a in estado["nuevos"] if a.id_contador > ultimo]

    for modulo in (sincronizador,):
        monkeypatch.setattr(modulo, "obtener_cliente_supabase", lambda: cliente)
        monkeypatch.setattr(modulo, "obtener_albaranes_entre_fechas", entre_fechas)
        monkeypatch.setattr(modulo, "obtener_nuevos_albaranes_con_recepcion", nuevos)
        monkeypatch.setattr(modulo, "obtener_albaranes_por_contadores",
                            lambda cs: [a for a in entre_fechas(date(1900, 1, 1), date(2999, 1, 1))
                                        if a.id_contador in cs])
    monkeypatch.setattr(guardado, "obtener_cliente_supabase", lambda: cliente)
    monkeypatch.setenv(resync.VARIABLE_ACTIVACION, "1")
    estado["modulo"] = sincronizador
    return estado


def test_sincronizacion_nocturna_v2_nuevos_modificados_y_ausentes(base22, farmatic_simulado):
    pg, f = base22, farmatic_simulado
    _albaran(pg, 990001, "08Z90001", "500.86")
    _albaran(pg, 990002, "08Z90002", "12.00")
    _albaran(pg, 990003, "08Z90003", "7.00")
    corregido = Albaran(990001, "0002 ", "1.- SAFA", "08Z90001", datetime.fromisoformat(RECIENTE),
                        740.0, 504.0199999, 32.22, id_recepcion=50898)
    f["cambios"][990001] = corregido
    f["ausentes"].add(990002)
    f["nuevos"].append(Albaran(990010, "0002", "1.- SAFA", "08Z90010", datetime.fromisoformat(RECIENTE),
                               20.0, 10.0, 0.0, id_recepcion=50900))
    total_antes = int(pg.sql("select count(*) from public.albaranes"))

    assert f["modulo"].sincronizar_albaranes() == 0

    assert int(pg.sql("select count(*) from public.albaranes")) == total_antes + 1
    assert _fila(pg, 990010)["id_recepcion"] == 50900
    assert (_fila(pg, 990001)["importe_puc"], _fila(pg, 990001)["id_recepcion"]) == ("504.02", 50898)
    assert [(c["campo"], c["accion"]) for c in _cambios(pg, 990001)] == [
        ("importe_puc", "ACTUALIZADO"), ("id_recepcion", "ACTUALIZADO")]
    assert [(c["campo"], c["valor_nuevo"], c["motivo"]) for c in _cambios(pg, 990002)] == [
        ("presencia", "AUSENTE", "AUSENTE_EN_FARMATIC")]
    # Primera pasada: rellena la recepcion de los demas albaranes de la ventana (metadato).
    assert all(c["campo"] == "id_recepcion" for c in _cambios(pg) if c["id_contador"] not in (990001, 990002))
    assert pg.sql(f"select count(*) from {CAMBIOS} where origen <> 'RESYNC_VENTANA'") == "0"
    # Segunda noche sin cambios en Farmatic: no escribe nada.
    n = len(_cambios(pg))
    assert f["modulo"].sincronizar_albaranes() == 0
    assert len(_cambios(pg)) == n
    assert _locks(pg) == "0|0" and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


@pytest.mark.parametrize("variante", ["21", "22"])
def test_modo_informe_no_escribe_nada(pg17_nueva_base, monkeypatch, tmp_path, variante):
    pg = pg17_nueva_base(variante)
    sincronizador = importlib.import_module("src.sincronizar_albaranes")
    _albaran_sin_recepcion = ("insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,"
                              "numero_albaran,fecha,importe_pvp,importe_puc,descuento,estado) values ('PIO', 990001, "
                              f"'2', '1.- SAFA', '08Z90001', date {_lit(RECIENTE)}, 740, 500.86, 32.22, 'PENDIENTE');")
    pg.sql(_albaran_sin_recepcion)
    cliente = ClientePg17(pg, rol_tablas="service_role")
    monkeypatch.setattr(sincronizador, "obtener_cliente_supabase", lambda: cliente)
    monkeypatch.setattr(sincronizador, "obtener_albaranes_entre_fechas", lambda d, h: [
        Albaran(990001, "0002", "1.- SAFA", "08Z90001", datetime.fromisoformat(RECIENTE), 740.0, 504.02, 32.22,
                id_recepcion=50898)])
    monkeypatch.setattr(sincronizador, "obtener_albaranes_por_contadores", lambda cs: [])
    antes = esquema(pg), _huella(pg, "select to_jsonb(a) from public.albaranes a")
    contenido = sincronizador.generar_informe(tmp_path / "informe.json")
    assert (esquema(pg), _huella(pg, "select to_jsonb(a) from public.albaranes a")) == antes
    assert contenido["esquema_22"] is (variante == "22")
    assert {c["id_contador"]: c["prevision"] for c in contenido["cambios"]} == {990001: "ACTUALIZAR"}
    assert contenido["resumen"]["cambios"] == 1 and contenido["resumen"]["ausentes"] >= 0


# --------------------------------------------------------------------------- carga histórica

def _cargar_carga():
    spec = importlib.util.spec_from_file_location(f"carga_2bd_{uuid.uuid4().hex[:6]}",
                                                  ROOT / "pruebas/auditoria_2bd/carga_historica.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_carga_historica_abril_mayo_informe_ejecucion_unica(base22, monkeypatch, tmp_path):
    pg = base22
    _albaran(pg, 990020, "08Z90020", "5.00", fecha="2026-05-20")  # ya estaba, Farmatic lo corrige
    farmatic = [
        Albaran(990020, "0002", "1.- SAFA", "08Z90020", datetime(2026, 5, 20), 740.0, 5.50, 32.22, id_recepcion=1),
        Albaran(990021, "0002", "1.- SAFA", "08Z90021", datetime(2026, 4, 1), 10.0, 6.0, 0.0, id_recepcion=2),
        Albaran(990022, "0101", "2.- COFARES", "C-1", datetime(2026, 5, 31), 11.0, 7.0, 0.0, id_recepcion=None),
    ]
    carga = _cargar_carga()
    cliente = ClientePg17(pg, rol_tablas="service_role")
    monkeypatch.setattr(carga, "obtener_cliente_supabase", lambda: cliente)
    monkeypatch.setattr(carga, "obtener_albaranes_entre_fechas",
                        lambda d, h: [a for a in farmatic if d <= a.fecha.date() < h])
    monkeypatch.setattr(carga, "obtener_albaranes_por_contadores", lambda cs: [])

    antes = _huella(pg, "select to_jsonb(a) from public.albaranes a")
    assert carga.main("informe", tmp_path / "informe.json") == 0
    assert _huella(pg, "select to_jsonb(a) from public.albaranes a") == antes
    informe = json.loads((tmp_path / "informe.json").read_text(encoding="utf-8"))
    assert informe["resumen"]["nuevos"] == 2 and informe["resumen"]["cambios"] == 1

    assert carga.main("ejecutar", tmp_path / "carga.json") == 0
    registro = json.loads((tmp_path / "carga.json").read_text(encoding="utf-8"))
    assert registro["resultado"] == "COMPLETADA"
    assert (registro["resumen"]["insertados"], registro["resumen"]["actualizados"]) == (2, 1)
    assert _fila(pg, 990020)["importe_puc"] == "5.50" and _fila(pg, 990021)["id_recepcion"] == 2
    assert {c["origen"] for c in _cambios(pg)} == {"CARGA_HISTORICA"}
    with pytest.raises(SystemExit, match="GUARD_EXISTENTE"):
        carga.main("ejecutar", tmp_path / "carga_2.json")


def test_carga_historica_sin_la_22_no_escribe(pg17_nueva_base, monkeypatch, tmp_path):
    pg = pg17_nueva_base("21")
    carga = _cargar_carga()
    monkeypatch.setattr(carga, "obtener_cliente_supabase", lambda: ClientePg17(pg, rol_tablas="service_role"))
    monkeypatch.setattr(carga, "obtener_albaranes_entre_fechas", lambda d, h: [
        Albaran(990021, "0002", "1.- SAFA", "08Z90021", datetime(2026, 4, 1), 10.0, 6.0, 0.0, id_recepcion=2)])
    monkeypatch.setattr(carga, "obtener_albaranes_por_contadores", lambda cs: [])
    antes = _huella(pg, "select to_jsonb(a) from public.albaranes a")
    with pytest.raises(RuntimeError):
        carga.main("ejecutar", tmp_path / "carga.json")
    assert _huella(pg, "select to_jsonb(a) from public.albaranes a") == antes
    assert not (tmp_path / carga.NOMBRE_GUARD).exists()


# --------------------------------------------------------------------------- ensayo del script de despliegue de la 22

SCRIPT_22 = ROOT / "pruebas/auditoria_2bd/desplegar_22.py"


def _commit_de_la_22() -> tuple[str, str]:
    commit = subprocess.run(["git", "-C", str(ROOT), "log", "-n", "1", "--format=%H", "--",
                             "sql/migrations/22_cf_resincronizacion_albaranes.sql"],
                            capture_output=True, text=True).stdout.strip()
    if not commit:
        pytest.skip("migracion 22 sin commit: el ensayo del despliegue exige verificar el SHA contra un commit")
    import hashlib
    local = MIGRACION_22.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return commit, hashlib.sha256(local.encode("utf-8")).hexdigest()


def _cargar_script():
    spec = importlib.util.spec_from_file_location(f"desplegar_22_{uuid.uuid4().hex[:6]}", SCRIPT_22)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _sql_precondiciones() -> str:
    arbol = ast.parse(SCRIPT_22.read_text(encoding="utf-8"))
    [consulta] = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute"
                  and n.args and "has_table_privilege" in ast.unparse(n.args[0])]
    return eval(compile(ast.Expression(consulta.args[0]), str(SCRIPT_22), "eval"), vars(_cargar_script()))


def test_ensayo_completo_despliegue_22_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch):
    commit, sha = _commit_de_la_22()
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "21"))
    _datos_previos(pg, tmp_path)
    _albaran(pg, 990001, "08Z90001", "500.86")
    referencia = base_desde(nombre, pg.db)
    referencia.sql(MIGRACION_22.read_text(encoding="utf-8"))
    assert pg.sql("begin read only; " + _sql_precondiciones() + "; rollback;") == "|".join(["t"] * 9)

    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    import psycopg2

    real = getattr(psycopg2, "_connect_original_2az", psycopg2.connect)
    psycopg2._connect_original_2az = real
    dsns = []

    def conectar_local(dsn, **_kwargs):
        dsns.append(dsn)
        return real(host="127.0.0.1", port=puerto, dbname=pg.db, user="postgres", password="local-only",
                    connect_timeout=10)

    monkeypatch.setattr(psycopg2, "connect", conectar_local)
    monkeypatch.setenv("CONTROLFARMACIAS_SUPABASE_DB_URL", DSN_FICTICIO)

    def ejecutar(salida):
        try:
            _cargar_script().main(commit, sha, salida)
        except SystemExit:
            pass
        return json.loads(salida.read_text(encoding="utf-8"))

    antes = {k: _huella(pg, q) for k, q in HUELLAS_SIN_22.items()}
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit)
    assert registro["precondiciones"] == [True] * 9
    assert registro["postcondiciones"] == {"albaranes_cambios": 0, "albaranes_con_recepcion": 0, "rpcs": True,
                                           "persistir_rechaza_ausentes": True}
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in HUELLAS_SIN_22.items()} == antes

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    assert registro["precondiciones"][0] is False and all(registro["precondiciones"][1:])
    assert esquema(pg) == esquema(referencia)


def test_sql_de_precondiciones_22_es_de_solo_lectura():
    sql = _sql_precondiciones()
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter "))
