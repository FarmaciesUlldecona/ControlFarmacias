"""Hito 2BF: migracion 23 (aprobaciones de Pio de cambios de identidad) en PostgreSQL 17 local.

Plantillas (pg17_local): "22" (estado productivo actual), "23" = 22 + migracion 23 dos veces,
"23_rollback" = 23 + rollback. Farmatic SIMULADO (sin Farmatic real ni produccion). Caso real 279410:
identidad real (Supabase 08C16912 / 52 CINFA; Farmatic 08C16912A / '0002 ' / 1.- SAFA, recepcion 50781,
informe V2 de la tanda RO) e importes sinteticos salvo el PUC (422,86).
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import uuid
from datetime import datetime

import pytest

from pg17_local import FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, ClientePg17, _locks, esquema
from test_integracion_pg17_2az import _datos_previos, _huella, _preparar_2ao
from test_integracion_pg17_2ba import _persistir_directo
from test_integracion_pg17_2bd import RECIENTE, _albaran, _ausente, _cambios, _espejo, _resync
from src.models.albaran import Albaran
from src.supabase_client import resincronizacion_albaranes as resync

pytestmark = pytest.mark.pg17_local

MIGRACION_23 = MIG / "23_cf_aprobaciones_albaranes.sql"
APROBACIONES = "public.albaranes_aprobaciones"
APLICADAS = "public.albaranes_aprobaciones_aplicadas"
APROBACION_279410 = json.loads((ROOT / "pruebas/auditoria_2bf/aprobacion_279410.json").read_text(encoding="utf-8"))
HUELLAS = {
    "albaranes": "select to_jsonb(a) from public.albaranes a",
    "cambios": "select to_jsonb(c) from public.albaranes_cambios c",
    "facturas": "select to_jsonb(f) from public.facturas f",
    "conciliaciones": "select to_jsonb(c) from public.conciliaciones c",
    "reservas": "select to_jsonb(r) from public.conciliacion_albaranes_reservados r",
    "historial": "select to_jsonb(h) from public.historial_facturas h",
    "configuracion": "select to_jsonb(c) from public.cf_configuracion c",
}


@pytest.fixture
def base23(pg17_nueva_base):
    return pg17_nueva_base("23")


def _albaran_279410(pg, fecha="2026-06-22"):
    pg.sql("insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
           "importe_pvp,importe_puc,descuento,estado) values ('PIO', 279410, '52', 'CINFA', '08C16912', "
           f"date '{fecha}', 600.00, 422.86, 0, 'PENDIENTE');")


def _farmatic_279410(numero="08C16912A", id_proveedor="0002 ", fecha="2026-06-22") -> dict:
    return {"id_proveedor": id_proveedor, "proveedor": "1.- SAFA", "numero_albaran": numero, "fecha": fecha,
            "importe_pvp": "600.00", "importe_puc": "422.86", "descuento": "0.00", "id_recepcion": 50781}


def _fila(pg, contador=279410) -> dict:
    return pg.json("select numero_albaran, id_proveedor, proveedor, importe_puc::text, id_recepcion "
                   f"from public.albaranes where farmacia = 'PIO' and id_contador = {contador}")[0]


def _registrar(pg, cambio=None, **otros):
    datos = {**APROBACION_279410, **({"cambio": cambio} if cambio is not None else {}), **otros}
    return ClientePg17(pg).rpc("cf_registrar_aprobacion_albaran", {
        "p_farmacia": datos["farmacia"], "p_id_contador": datos["id_contador"], "p_cambio": datos["cambio"],
        "p_aprobado_por": datos["aprobado_por"], "p_aprobado_at": datos["aprobado_at"],
        "p_referencia": datos["referencia"], "p_registrado_por": "test-2bf"}).execute().data


def _aplicar(pg, aprobacion_id, valores):
    return ClientePg17(pg).rpc("cf_aplicar_aprobacion_albaran", {
        "p_aprobacion_id": aprobacion_id, "p_valores": valores, "p_ejecucion_id": "test-2bf"}).execute().data


def _revisiones(pg, contador=279410):
    return [(c["campo"], c["valor_anterior"], c["valor_nuevo"]) for c in _cambios(pg, contador)
            if c["accion"] == "REVISION"]


def _cambio(numero="08C16912A", proveedor="0002"):
    return [{"campo": "id_proveedor", "anterior": "52", "nuevo": proveedor},
            {"campo": "numero_albaran", "anterior": "08C16912", "nuevo": numero}]


# --------------------------------------------------------------------------- esquema y privilegios

def test_rollback_23_devuelve_exactamente_el_esquema_22(pg17_nueva_base):
    assert esquema(pg17_nueva_base("23_rollback")) == esquema(pg17_nueva_base("22"))
    assert esquema(pg17_nueva_base("23")) != esquema(pg17_nueva_base("22"))


def test_23_no_altera_datos_existentes(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("22")
    _datos_previos(pg, tmp_path)
    _albaran_279410(pg)
    _resync(pg, 279410, _farmatic_279410())
    antes = {k: _huella(pg, q) for k, q in HUELLAS.items()}
    referencia = esquema(pg17_nueva_base("23"))
    pg.sql(MIGRACION_23.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_23.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in HUELLAS.items()} == antes
    assert pg.sql(f"select (select count(*) from {APROBACIONES}), (select count(*) from {APLICADAS})") == "0|0"
    assert esquema(pg) == referencia
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_privilegios_de_la_23(base23):
    funciones = {f["f"]: f for f in base23.json(
        "select p.oid::regprocedure::text as f, p.prosecdef as definer, pg_get_userbyid(p.proowner) as owner, "
        "exists(select 1 from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a where a.grantee = 0) "
        "  as public, has_function_privilege('anon', p.oid, 'EXECUTE') as anon, "
        "has_function_privilege('authenticated', p.oid, 'EXECUTE') as authenticated, "
        "has_function_privilege('service_role', p.oid, 'EXECUTE') as service_role "
        "from pg_proc p where p.pronamespace = 'public'::regnamespace and p.proname in ("
        "'cf_registrar_aprobacion_albaran', 'cf_aplicar_aprobacion_albaran', 'cf_resincronizar_albaran', "
        "'cf_revision_albaran_pendiente', 'cf_identidad_valor_comparable', 'cf_cambio_identidad_comparable', "
        "'cf_albaranes_aprobaciones_append_only')")}
    assert len(funciones) == 7
    rpcs = ("cf_registrar_aprobacion_albaran(text,bigint,jsonb,text,timestampwithtimezone,text,text)",
            "cf_aplicar_aprobacion_albaran(bigint,jsonb,text)",
            "cf_resincronizar_albaran(text,bigint,jsonb,text,text)")
    for firma, f in funciones.items():
        nombre = firma.replace("public.", "").replace(" ", "")
        assert (f["owner"], f["public"], f["anon"], f["authenticated"]) == ("postgres", False, False, False), firma
        assert f["service_role"] is (nombre in rpcs), firma
        if nombre in rpcs:
            assert f["definer"] is True, firma
    for tabla in (APROBACIONES, APLICADAS):
        [t] = base23.json(
            "select c.relrowsecurity as rls, pg_get_userbyid(c.relowner) as owner, "
            "has_table_privilege('service_role', c.oid, 'SELECT') as sr_select, "
            "has_table_privilege('service_role', c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE') as sr_escribe, "
            "has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE') as anon, "
            "has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE') as authenticated, "
            "has_table_privilege('service_role', 'public.albaranes', 'UPDATE') as sr_update_albaranes "
            f"from pg_class c where c.oid = '{tabla}'::regclass")
        assert t == {"rls": True, "owner": "postgres", "sr_select": True, "sr_escribe": False, "anon": False,
                     "authenticated": False, "sr_update_albaranes": False}, tabla
    assert base23.sql("select has_sequence_privilege('service_role', 'public.albaranes_aprobaciones_id_seq', "
                      "'USAGE,SELECT,UPDATE')") == "f"
    with pytest.raises(RuntimeError, match="permission denied"):
        base23.sql(f"set role service_role; insert into {APROBACIONES} (farmacia) values ('PIO');")
    with pytest.raises(RuntimeError, match="permission denied"):
        base23.sql(f"set role anon; select count(*) from {APROBACIONES};")


def test_aprobaciones_y_aplicaciones_append_only(base23):
    _albaran_279410(base23)
    _resync(base23, 279410, _farmatic_279410())
    _aplicar(base23, _registrar(base23)["aprobacion_id"], _farmatic_279410())
    for tabla in (APROBACIONES, APLICADAS):
        for sentencia in (f"update {tabla} set farmacia = 'x';", f"delete from {tabla};", f"truncate {tabla} cascade;"):
            with pytest.raises(RuntimeError, match="ALBARANES_APROBACIONES_APPEND_ONLY"):
                base23.sql(sentencia)


# --------------------------------------------------------------------------- caso real 279410

def test_caso_real_279410_revision_aprobacion_y_aplicacion(base23):
    pg = base23
    _albaran_279410(pg)
    for _noche in range(3):  # tres noches con la misma diferencia: una sola revision por campo
        r = _resync(pg, 279410, _farmatic_279410())
        assert (r["accion"], r["motivo"]) == ("REVISION", "CAMBIO_IDENTIDAD")
    assert _revisiones(pg) == [("numero_albaran", "08C16912", "08C16912A"), ("id_proveedor", "52", "0002 ")]
    ids_revision = [int(x) for x in pg.sql(
        "select string_agg(id::text, ',' order by id) from public.albaranes_cambios "
        "where id_contador = 279410 and accion = 'REVISION'").split(",")]

    registro = _registrar(pg)
    assert registro["accion"] == "REGISTRADA"
    assert _registrar(pg) == {"accion": "YA_REGISTRADA", "aprobacion_id": registro["aprobacion_id"]}
    [aprobacion] = pg.json(f"select aprobado_por, aprobado_at::date::text as dia, registrado_por, motivo, cambio "
                           f"from {APROBACIONES}")
    assert (aprobacion["aprobado_por"], aprobacion["dia"], aprobacion["registrado_por"], aprobacion["motivo"]) == (
        "Pio", "2026-10-28", "test-2bf", "CAMBIO_IDENTIDAD")
    assert aprobacion["cambio"] == _cambio()
    assert _fila(pg)["numero_albaran"] == "08C16912"  # registrar no toca el albaran

    r = _aplicar(pg, registro["aprobacion_id"], _farmatic_279410())
    assert r["accion"] == "APLICADA" and r["revisiones_resueltas"] == ids_revision
    # Solo la identidad aprobada, con el literal de Farmatic; el resto lo hace la resincronizacion.
    assert _fila(pg) == {"numero_albaran": "08C16912A", "id_proveedor": "0002 ", "proveedor": "CINFA",
                         "importe_puc": "422.86", "id_recepcion": None}
    [aplicada] = pg.json(f"select valores_anteriores, valores_nuevos, revisiones_resueltas, ejecucion_id from {APLICADAS}")
    assert aplicada == {"valores_anteriores": {"numero_albaran": "08C16912", "id_proveedor": "52"},
                        "valores_nuevos": {"numero_albaran": "08C16912A", "id_proveedor": "0002 "},
                        "revisiones_resueltas": ids_revision, "ejecucion_id": "test-2bf"}
    assert _aplicar(pg, registro["aprobacion_id"], _farmatic_279410())["accion"] == "YA_APLICADA"
    assert pg.sql(f"select count(*) from {APLICADAS}") == "1"

    # Noche siguiente: valores y recepcion con historial, sin nuevas revisiones.
    assert _resync(pg, 279410, _farmatic_279410())["accion"] == "ACTUALIZADO"
    assert _fila(pg)["proveedor"] == "1.- SAFA" and _fila(pg)["id_recepcion"] == 50781
    assert [(c["campo"], c["accion"]) for c in _cambios(pg, 279410)] == [
        ("numero_albaran", "REVISION"), ("id_proveedor", "REVISION"),
        ("proveedor", "ACTUALIZADO"), ("id_recepcion", "ACTUALIZADO")]
    assert _resync(pg, 279410, _farmatic_279410())["accion"] == "SIN_CAMBIOS"
    assert _locks(pg) == "0|0" and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


@pytest.mark.parametrize("caso", ["otro_numero", "solo_proveedor", "otro_proveedor", "sin_revision",
                                  "farmatic_cambio_despues"])
def test_cambio_distinto_de_lo_aprobado_no_se_aplica_y_sigue_en_revision(base23, caso):
    pg = base23
    _albaran_279410(pg)
    if caso != "sin_revision":
        _resync(pg, 279410, _farmatic_279410())
    cambio = {"otro_numero": _cambio(numero="08C16912B"), "solo_proveedor": _cambio()[:1],
              "otro_proveedor": _cambio(proveedor="0003")}.get(caso, _cambio())
    aprobacion_id = _registrar(pg, cambio=cambio)["aprobacion_id"]
    farmatic = _farmatic_279410(numero="08C16912B") if caso == "farmatic_cambio_despues" else _farmatic_279410()
    if caso == "farmatic_cambio_despues":
        _resync(pg, 279410, farmatic)  # la revision 08C16912 -> 08C16912B tambien queda registrada
    antes = {k: _huella(pg, q) for k, q in HUELLAS.items()}
    r = _aplicar(pg, aprobacion_id, farmatic)
    assert (r["accion"], r["motivo"]) == ("NO_APLICADA", "CAMBIO_NO_COINCIDE")
    assert {k: _huella(pg, q) for k, q in HUELLAS.items()} == antes
    assert pg.sql(f"select count(*) from {APLICADAS}") == "0"
    assert _fila(pg)["numero_albaran"] == "08C16912"


def test_farmatic_vuelve_a_lo_aprobado_y_se_resuelven_tambien_las_revisiones_superadas(base23):
    pg = base23
    _albaran_279410(pg)
    _resync(pg, 279410, _farmatic_279410(numero="08C16912B"))
    _resync(pg, 279410, _farmatic_279410())
    aprobacion_id = _registrar(pg)["aprobacion_id"]
    r = _aplicar(pg, aprobacion_id, _farmatic_279410())
    assert r["accion"] == "APLICADA" and len(r["revisiones_resueltas"]) == 3  # B, A y el proveedor
    assert pg.sql("select count(*) from public.albaranes_cambios c where c.accion = 'REVISION' "
                  "and public.cf_revision_albaran_pendiente(c.id)") == "0"


def test_albaran_reservado_no_se_aplica(base23, tmp_path):
    pg = base23
    _, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    _albaran_279410(pg)
    _resync(pg, 279410, _farmatic_279410())
    linea = {"tipo_relacion": "UNO_A_UNO", "importe_aplicado": "1", "estado": "COINCIDE", "albaran_farmacia": "PIO"}
    _persistir_directo(pg, ids["08007973"], [{**linea, "orden": 1, "albaran_id_contador": 279410}])
    aprobacion_id = _registrar(pg)["aprobacion_id"]
    antes = {k: _huella(pg, q) for k, q in HUELLAS.items()}
    r = _aplicar(pg, aprobacion_id, _farmatic_279410())
    assert (r["accion"], r["motivo"]) == ("NO_APLICADA", "RESERVADO:08007973")
    assert {k: _huella(pg, q) for k, q in HUELLAS.items()} == antes
    assert _locks(pg) == "0|0"


def test_albaran_ausente_no_se_aplica(base23):
    _albaran_279410(base23)
    _resync(base23, 279410, _farmatic_279410())
    _ausente(base23, 279410)
    r = _aplicar(base23, _registrar(base23)["aprobacion_id"], _farmatic_279410())
    assert (r["accion"], r["motivo"]) == ("NO_APLICADA", "AUSENTE_EN_FARMATIC")
    assert _fila(base23)["numero_albaran"] == "08C16912"


def test_identidad_ocupada_por_otro_albaran_no_cambia_nada(base23):
    pg = base23
    _albaran_279410(pg)
    _albaran(pg, 990001, "08C16912A", "1.00", id_proveedor="0002 ")
    _resync(pg, 279410, _farmatic_279410())
    aprobacion_id = _registrar(pg)["aprobacion_id"]
    antes = {k: _huella(pg, q) for k, q in HUELLAS.items()}
    with pytest.raises(RuntimeError, match="IDENTIDAD_OCUPADA"):
        _aplicar(pg, aprobacion_id, _farmatic_279410())
    assert {k: _huella(pg, q) for k, q in HUELLAS.items()} == antes
    assert pg.sql(f"select count(*) from {APLICADAS}") == "0"


def test_registro_y_aplicacion_validan_entradas_y_fallan_cerrado(base23):
    pg = base23
    _albaran_279410(pg)
    casos = [
        ({"aprobado_por": "Marc"}, "APROBADOR_NO_ADMITIDO"),
        ({"aprobado_at": "2999-01-01"}, "FECHA_APROBACION_INVALIDA"),
        ({"referencia": " "}, "REFERENCIA_Y_REGISTRADOR_OBLIGATORIOS"),
        ({"farmacia": "RITA"}, "FARMACIA_NO_HABILITADA"),
        ({"id_contador": 123456789}, "ALBARAN_NO_EXISTE"),
        ({"cambio": []}, "CAMBIO_INVALIDO"),
        ({"cambio": [{"campo": "importe_puc", "anterior": "422.86", "nuevo": "1"}]}, "CAMBIO_INVALIDO"),
        ({"cambio": _cambio()[:1] * 2}, "CAMBIO_INVALIDO"),
        ({"cambio": [{"campo": "id_proveedor", "anterior": "52", "nuevo": "0052"}]}, "CAMBIO_INVALIDO"),
        ({"cambio": [{"campo": "id_proveedor", "anterior": "53", "nuevo": "0002"}]},
         "APROBACION_NO_CORRESPONDE_AL_ALBARAN"),
        ({"cambio": [{"campo": "id_proveedor", "anterior": "52", "nuevo": "0002", "extra": 1}]}, "CAMBIO_INVALIDO"),
    ]
    for otros, error in casos:
        with pytest.raises(RuntimeError, match=error):
            _registrar(pg, **otros)
    with pytest.raises(RuntimeError, match="APROBACION_NO_EXISTE"):
        _aplicar(pg, 987654, _farmatic_279410())
    with pytest.raises(RuntimeError, match="VALORES_INCOMPLETOS"):
        _aplicar(pg, 987654, {"numero_albaran": "x"})
    assert pg.sql(f"select (select count(*) from {APROBACIONES}), (select count(*) from {APLICADAS})") == "0|0"


# --------------------------------------------------------------------------- A6: solo revisiones pendientes

def test_revision_resuelta_que_reaparece_identica_se_registra_de_nuevo(base23):
    """Con la 22 una revision identica ya resuelta quedaria silenciada para siempre."""
    pg = base23
    _albaran_279410(pg)
    _resync(pg, 279410, _farmatic_279410())
    _aplicar(pg, _registrar(pg)["aprobacion_id"], _farmatic_279410())
    # Farmatic revierte a 52 / 08C16912; Pio aprueba la reversion.
    revertido = _farmatic_279410(numero="08C16912", id_proveedor="52")
    _resync(pg, 279410, revertido)
    reversion = [{"campo": "id_proveedor", "anterior": "0002", "nuevo": "52"},
                 {"campo": "numero_albaran", "anterior": "08C16912A", "nuevo": "08C16912"}]
    assert _aplicar(pg, _registrar(pg, cambio=reversion)["aprobacion_id"], revertido)["accion"] == "APLICADA"
    # Farmatic vuelve a 08C16912A: la revision es identica a la primera (resuelta) y se registra otra vez.
    _resync(pg, 279410, _farmatic_279410())
    assert _revisiones(pg) == [("numero_albaran", "08C16912", "08C16912A"), ("id_proveedor", "52", "0002 "),
                               ("numero_albaran", "08C16912A", "08C16912"), ("id_proveedor", "0002 ", "52"),
                               ("numero_albaran", "08C16912", "08C16912A"), ("id_proveedor", "52", "0002 ")]
    _resync(pg, 279410, _farmatic_279410())
    assert len(_revisiones(pg)) == 6


def test_revision_por_reserva_deja_de_estar_pendiente_si_el_campo_se_actualiza(base23):
    pg = base23
    _albaran(pg, 990001, "08Z90001", "500.86")
    pg.sql("insert into public.albaranes_cambios (farmacia, id_contador, origen, ejecucion_id, campo, "
           "valor_anterior, valor_nuevo, accion, motivo) values "
           "('PIO', 990001, 'RESYNC_VENTANA', 't', 'importe_puc', '500.86', '504.02', 'REVISION', 'RESERVADO:X'), "
           "('PIO', 990001, 'RESYNC_VENTANA', 't', 'importe_puc', '500.86', '504.02', 'ACTUALIZADO', null), "
           "('PIO', 990001, 'RESYNC_VENTANA', 't', 'descuento', '1.00', '2.00', 'REVISION', 'RESERVADO:X');")
    assert pg.sql("select string_agg(public.cf_revision_albaran_pendiente(id)::text, ',' order by id) "
                  "from public.albaranes_cambios") == "false,false,true"


# --------------------------------------------------------------------------- tarea nocturna con la 23

def test_sincronizacion_nocturna_con_la_23_no_registra_una_fila_por_noche(base23, monkeypatch):
    pg = base23
    sincronizador = importlib.import_module("src.sincronizar_albaranes")
    pg.sql("update public.albaranes set importe_pvp = coalesce(importe_pvp, 0), "
           "importe_puc = coalesce(importe_puc, 0), descuento = coalesce(descuento, 0);")
    _albaran_279410(pg, fecha=RECIENTE)
    corregido = Albaran(279410, "0002 ", "1.- SAFA", "08C16912A", datetime.fromisoformat(RECIENTE),
                        600.0, 422.86, 0.0, id_recepcion=50781)
    cliente = ClientePg17(pg, rol_tablas="service_role")
    monkeypatch.setattr(sincronizador, "obtener_cliente_supabase", lambda: cliente)
    monkeypatch.setattr(sincronizador, "obtener_nuevos_albaranes_con_recepcion", lambda ultimo: [])
    # Farmatic = espejo de Supabase (2BD) con 279410 corregido en Farmatic.
    monkeypatch.setattr(sincronizador, "obtener_albaranes_entre_fechas", lambda d, h: [
        corregido if a.id_contador == 279410 else a for a in _espejo(pg, d, h)])
    monkeypatch.setattr(sincronizador, "obtener_albaranes_por_contadores", lambda cs: [])
    monkeypatch.setattr(importlib.import_module("src.supabase_client.guardar_albaranes"),
                        "obtener_cliente_supabase", lambda: cliente)
    monkeypatch.setenv(resync.VARIABLE_ACTIVACION, "1")
    for _noche in range(3):
        assert sincronizador.sincronizar_albaranes() == 0
        assert _revisiones(pg) == [("numero_albaran", "08C16912", "08C16912A"), ("id_proveedor", "52", "0002 ")]
    assert _fila(pg)["numero_albaran"] == "08C16912"


# --------------------------------------------------------------------------- script one-shot

def _cargar_script():
    spec = importlib.util.spec_from_file_location(f"aplicar_2bf_{uuid.uuid4().hex[:6]}",
                                                  ROOT / "pruebas/auditoria_2bf/aplicar_aprobacion.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _script(pg, monkeypatch, farmatic_numero="08C16912A"):
    script = _cargar_script()
    cliente = ClientePg17(pg, rol_tablas="service_role")
    monkeypatch.setattr(script, "obtener_cliente_supabase", lambda: cliente)
    monkeypatch.setattr(script, "obtener_albaranes_por_contadores", lambda cs: [
        Albaran(279410, "0002 ", "1.- SAFA", farmatic_numero, datetime(2026, 6, 22), 600.0, 422.86, 0.0,
                id_recepcion=50781)] if list(cs) == [279410] else [])
    return script


def test_script_informe_registrar_y_aplicar_una_vez(base23, monkeypatch, tmp_path):
    pg = base23
    _albaran_279410(pg)
    _resync(pg, 279410, _farmatic_279410())
    script = _script(pg, monkeypatch)
    ruta_aprobacion = ROOT / "pruebas/auditoria_2bf/aprobacion_279410.json"

    antes = {k: _huella(pg, q) for k, q in HUELLAS.items()}
    assert script.main("informe", "279410", tmp_path / "informe_0.json") == 0
    assert {k: _huella(pg, q) for k, q in HUELLAS.items()} == antes
    informe = json.loads((tmp_path / "informe_0.json").read_text(encoding="utf-8"))
    assert informe["resultado"] == "INFORME_SIN_ESCRITURA" and informe["aprobaciones"] == []
    assert sorted(c["campo"] for c in informe["detectado_ahora"]) == ["id_proveedor", "numero_albaran"]

    assert script.main("registrar", str(ruta_aprobacion), tmp_path / "registrar.json") == 0
    registro = json.loads((tmp_path / "registrar.json").read_text(encoding="utf-8"))
    assert registro["resultado"] == "REGISTRADA"
    aprobacion_id = registro["respuesta"]["aprobacion_id"]
    assert pg.sql(f"select registrado_por <> '' from {APROBACIONES}") == "t"
    assert _fila(pg)["numero_albaran"] == "08C16912"

    script.main("informe", "279410", tmp_path / "informe_1.json")
    informe = json.loads((tmp_path / "informe_1.json").read_text(encoding="utf-8"))
    assert [a["prevision"] for a in informe["aprobaciones"]] == ["APLICABLE"]

    assert script.main("aplicar", str(aprobacion_id), tmp_path / "aplicar.json") == 0
    assert json.loads((tmp_path / "aplicar.json").read_text(encoding="utf-8"))["resultado"] == "APLICADA"
    assert _fila(pg)["numero_albaran"] == "08C16912A"
    with pytest.raises(SystemExit, match="GUARD_EXISTENTE"):
        script.main("aplicar", str(aprobacion_id), tmp_path / "aplicar_2.json")
    script.main("informe", "279410", tmp_path / "informe_2.json")
    informe = json.loads((tmp_path / "informe_2.json").read_text(encoding="utf-8"))
    assert [a["prevision"] for a in informe["aprobaciones"]] == ["YA_APLICADA"] and informe["pendientes"] == []


def test_script_no_aplicada_si_farmatic_no_coincide_y_sin_configuracion_segura(base23, monkeypatch, tmp_path):
    pg = base23
    _albaran_279410(pg)
    _resync(pg, 279410, _farmatic_279410())
    aprobacion_id = _registrar(pg)["aprobacion_id"]
    script = _script(pg, monkeypatch, farmatic_numero="08C16912B")
    assert script.main("aplicar", str(aprobacion_id), tmp_path / "aplicar.json") == 3
    registro = json.loads((tmp_path / "aplicar.json").read_text(encoding="utf-8"))
    assert (registro["resultado"], registro["respuesta"]["motivo"]) == ("NO_APLICADA", "CAMBIO_NO_COINCIDE")
    assert _fila(pg)["numero_albaran"] == "08C16912"

    pg.sql("update public.cf_configuracion set luna_habilitada = true;")
    (tmp_path / "otra").mkdir()
    with pytest.raises(SystemExit, match="CONFIGURACION_INESPERADA"):
        _script(pg, monkeypatch).main("aplicar", str(aprobacion_id), tmp_path / "otra" / "aplicar.json")
    assert not (tmp_path / "otra" / f"aplicar_aprobacion_{aprobacion_id}.guard").exists()


def test_script_sin_la_23_no_escribe(pg17_nueva_base, monkeypatch, tmp_path):
    pg = pg17_nueva_base("22")
    _albaran_279410(pg)
    _resync(pg, 279410, _farmatic_279410())
    antes = {k: _huella(pg, q) for k, q in HUELLAS.items()}
    script = _script(pg, monkeypatch)
    with pytest.raises(RuntimeError):
        script.main("registrar", str(ROOT / "pruebas/auditoria_2bf/aprobacion_279410.json"), tmp_path / "r.json")
    with pytest.raises(RuntimeError):
        script.main("aplicar", "1", tmp_path / "a.json")
    assert not (tmp_path / "aplicar_aprobacion_1.guard").exists()
    assert {k: _huella(pg, q) for k, q in HUELLAS.items()} == antes
