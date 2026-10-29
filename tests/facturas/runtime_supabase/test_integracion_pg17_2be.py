"""Hito 2BE: migracion 24 (R17) en PostgreSQL 17 local.

Plantillas (pg17_local): "23" (estado productivo actual), "24" = 23 + migracion 24 dos veces,
"24_rollback" = 24 + rollback. Caso real 08007969: PDF del 2AO (fixture local excluido de git) y, para
08C20268, los albaranes reales de la recepcion 50898 (280005 08C20268 500,86 y 280004 Q039921/2026 3,16;
medicion READ_ONLY del 2026-10-29); el resto de albaranes, sinteticos con PUC = importe documental.
Sin produccion ni Farmatic.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
import uuid

import pytest

import pg17_local as pgl
from pg17_local import FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, _lit, base_desde, esquema
from test_ensayo_fase4_2at import _ConexionPg17
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _datos_previos, _huella, _operacionales_sinteticos, _preparar_2ao,
    _solo_primera, _sr, contenedor_tcp)
from test_integracion_pg17_2ba import _reservas, _vigente
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion

pytestmark = pytest.mark.pg17_local

MIGRACION_24 = MIG / "24_cf_r17_recepcion.sql"
PERSISTIR = "public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)"
AUXILIAR = "public.cf_linea_r17_valida(uuid,text,jsonb,jsonb)"


@pytest.fixture
def base24(pg17_nueva_base):
    return pg17_nueva_base("24")


# --------------------------------------------------------------------------- esquema y privilegios

def test_rollback_24_devuelve_exactamente_el_esquema_23(pg17_nueva_base):
    assert esquema(pg17_nueva_base("24_rollback")) == esquema(pg17_nueva_base("23"))
    assert esquema(pg17_nueva_base("24")) != esquema(pg17_nueva_base("23"))


def test_24_no_altera_datos_existentes(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("23")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    reservas = _reservas(pg)
    referencia = esquema(pg17_nueva_base("24"))
    pg.sql(MIGRACION_24.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_24.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert _reservas(pg) == reservas
    assert esquema(pg) == referencia
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_24_exige_la_23(pg17_nueva_base):
    pg = pg17_nueva_base("22")
    with pytest.raises(RuntimeError, match="MIGRACION_23_AUSENTE"):
        pg.sql(MIGRACION_24.read_text(encoding="utf-8"))


def test_privilegios_de_la_24(base24):
    pg = base24
    for rol, esperado in (("service_role", "t"), ("anon", "f"), ("authenticated", "f")):
        assert pg.sql(f"select has_function_privilege('{rol}', '{PERSISTIR}', 'EXECUTE')") == esperado
    for rol in ("service_role", "anon", "authenticated"):
        assert pg.sql(f"select has_function_privilege('{rol}', '{AUXILIAR}', 'EXECUTE')") == "f"
    assert pg.sql(f"select prosecdef::text || '|' || pg_get_userbyid(proowner) from pg_proc "
                  f"where oid = '{PERSISTIR}'::regprocedure") == "true|postgres"
    assert pg.sql(f"select pg_get_userbyid(proowner) from pg_proc where oid = '{AUXILIAR}'::regprocedure") == \
        "postgres"
    assert pg.sql("select has_table_privilege('service_role', 'public.albaranes', 'UPDATE')") == "f"


# --------------------------------------------------------------------------- caso real 08007969

def _recepcion_50898(pg, factura_id, *, recepcion_interno=50898):
    """08C20268 con el PUC real (500,86) y el interno Q039921/2026 (3,16) de la recepcion 50898."""
    _operacionales_sinteticos(pg, factura_id, 0, 940000)
    [linea] = pg.json("select numero_albaran, fecha_albaran::text as fecha, importe_total::text as importe "
                      f"from public.facturas_albaranes_extraidos where factura_id = {_lit(factura_id)} "
                      "and numero_albaran = '08C20268'")
    assert linea["importe"] == "504.0200"
    pg.sql("update public.albaranes set id_contador = 280005, importe_puc = 500.86, id_recepcion = 50898 "
           "where id_contador >= 940000 and numero_albaran = '08C20268';")
    pg.sql("insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
           f"importe_pvp,importe_puc,descuento,estado,id_recepcion) values ('PIO', 280004, '2', '1.- SAFA', "
           f"'Q039921/2026', date {_lit(linea['fecha'])}, 4.68, 3.16, 32.48, 'PENDIENTE', {recepcion_interno});")


def _conciliar_08007969(pg, tmp_path, *, persiste=True, **kwargs):
    cliente, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    objetivo = ids["08007969"]
    _recepcion_50898(pg, objetivo, **kwargs)
    _solo_primera(pg, ids, "08007969")
    worker = construir_worker_conciliacion(RepositorioRuntimeSupabase(cliente), "conc-2be")
    assert worker.ejecutar_una_manual() is persiste
    return objetivo


def _detalles_r17(pg, conciliacion_id):
    return pg.json("select albaran_id_contador, importe_aplicado::text as importe, "
                   "provenance->>'papel_r17' as papel, provenance->>'id_recepcion' as recepcion, "
                   "factura_albaran_extraido_id::text as linea from public.conciliacion_detalles "
                   f"where conciliacion_id = {_lit(conciliacion_id)} and tipo_relacion = 'UNO_A_VARIOS' order by orden")


def test_caso_real_08007969_concilia_con_r17_y_reserva_los_dos_albaranes(base24, tmp_path):
    pg = base24
    objetivo = _conciliar_08007969(pg, tmp_path)
    c = _vigente(pg, objetivo)
    assert (c["resultado"], c["diferencia"], c["casados"]) == ("CONCILIADA", "0.0700", 127)
    detalles = _detalles_r17(pg, c["id"])
    assert [(d["albaran_id_contador"], d["importe"], d["papel"], d["recepcion"]) for d in detalles] == [
        (280005, "500.8600", "NUMERO", "50898"), (280004, "3.1600", "INTERNO", "50898")]
    assert len({d["linea"] for d in detalles}) == 1
    regla = pg.json(f"select provenance->'tolerancia_regla' as r from public.conciliaciones where id = {_lit(c['id'])}")
    assert regla[0]["r"]["albaranes_casados"] == 128  # 127 UNO_A_UNO + la linea R17
    reservas = {r["albaran_id_contador"]: r["factura_id"] for r in _reservas(pg)}
    assert reservas[280005] == objetivo and reservas[280004] == objetivo and len(reservas) == 129


def test_08007969_sin_la_recepcion_comun_sigue_en_diferencia(base24, tmp_path):
    pg = base24
    objetivo = _conciliar_08007969(pg, tmp_path, recepcion_interno=50899)
    c = _vigente(pg, objetivo)
    assert (c["resultado"], c["diferencia"], c["casados"]) == ("DIFERENCIA", "504.0900", 127)
    assert _detalles_r17(pg, c["id"]) == []
    assert 280004 not in {r["albaran_id_contador"] for r in _reservas(pg)}


def test_el_codigo_2be_sin_la_24_no_persiste_una_linea_r17(pg17_nueva_base, tmp_path):
    """Orden de despliegue: primero la 24. Con la 23, R11 de la BD no cuenta la linea R17 y rechaza."""
    pg = pg17_nueva_base("23")
    objetivo = _conciliar_08007969(pg, tmp_path, persiste=False)
    assert pg.sql(f"select count(*) from public.conciliaciones where factura_id = {_lit(objetivo)}") == "0"
    assert pg.sql(f"select count(*) from public.conciliacion_albaranes_reservados where factura_id = "
                  f"{_lit(objetivo)}") == "0"
    assert "TOLERANCIA_REGLA_NO_COINCIDE" in pg.sql(
        f"select conciliacion_ultimo_error from public.facturas where id = {_lit(objetivo)}")


def test_simulador_2at_preve_la_linea_r17(base24, tmp_path, monkeypatch):
    pg = base24
    cliente, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    _recepcion_50898(pg, ids["08007969"])
    _solo_primera(pg, ids, "08007969")
    sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
    import auditoria_readonly as ar

    sentencias: list[str] = []
    monkeypatch.setattr(ar, "_conectar", lambda: (ar.PROJECT_REF, _ConexionPg17(pg, sentencias)))
    monkeypatch.setattr(ar, "_tareas", lambda: {"tareas": [
        {"nombre": n, "estado": "Ready", "proxima": None, "ultima": None, "resultado": 0}
        for n in ar.TAREAS_ESPERADAS]})
    salida = tmp_path / "candidato.json"
    ar.candidato(salida, None)
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["candidato_1"]["id"] == ids["08007969"]
    simulacion = datos["simulacion"]
    assert (simulacion["resultado"], simulacion["diferencia"]) == ("CONCILIADA", "0.0700")
    assert simulacion["resumen_detalles"]["lineas_r17"] == 1
    assert pg.sql("select count(*) from public.conciliaciones") == "0"
    assert all(s.lstrip().lower().startswith(("select", "with", "set local")) for s in sentencias)


# --------------------------------------------------------------------------- la BD revalida R17

def _linea_sintetica(pg, factura_id, *, numero="08Z00001", importe="100.00", tipo="CARGO"):
    [e] = pg.json("select id::text from public.facturas_albaranes_extraidos "
                  f"where factura_id = {_lit(factura_id)} order by orden, id limit 1")
    pg.sql(f"update public.facturas_albaranes_extraidos set numero_albaran = {_lit(numero)}, "
           f"importe_total = {importe}, tipo_movimiento = {_lit(tipo)} where id = {_lit(e['id'])};")
    return e["id"]


def _albaran(pg, contador, numero, puc, recepcion, id_proveedor="2"):
    pg.sql("insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
           f"importe_pvp,importe_puc,descuento,estado,id_recepcion) values ('PIO', {contador}, {_lit(id_proveedor)}, "
           f"'1.- SAFA', {_lit(numero)}, date '2026-06-25', 1, {puc}, 0, 'PENDIENTE', "
           f"{'null' if recepcion is None else recepcion});")


def _persistir(pg, factura_id, detalles):
    worker = "w-" + uuid.uuid4().hex[:6]
    pg.sql("update public.facturas set fecha_factura = date '2026-05-01', conciliacion_proximo_at = null, "
           f"estado_conciliacion_cf = 'PENDIENTE_CONCILIAR' where id = {_lit(factura_id)};")
    assert _sr(pg, f"select id from public.cf_reclamar_factura_conciliacion_manual_one_shot('{worker}', 300);") == \
        factura_id
    # R11 de la 24: UNO_A_UNO + lineas UNO_A_VARIOS distintas.
    lineas = sum(d["tipo_relacion"] == "UNO_A_UNO" for d in detalles) + len(
        {d.get("factura_albaran_extraido_id") for d in detalles if d["tipo_relacion"] == "UNO_A_VARIOS"} - {None})
    cuerpo = {"resultado": "DIFERENCIA", "importe_factura": "1000", "importe_explicado": "0", "diferencia": "1000",
              "tolerancia": "0.0500", "detalles": [{"orden": i, "estado": "DIFERENCIA", **d}
                                                   for i, d in enumerate(detalles, 1)],
              "tolerancia_regla": {"suelo": "0.05", "por_albaran": "0.01", "tope": "0.50",
                                   "albaranes_casados": lineas, "tolerancia": "0.0500"}}
    try:
        return _sr(pg, f"select public.cf_persistir_conciliacion({_lit(factura_id)}::uuid, '{worker}', "
                       f"'MANUAL_ONE_SHOT', 'directa-{uuid.uuid4().hex}', {_lit(json.dumps(cuerpo))}::jsonb);")
    finally:
        pg.sql("update public.facturas set conciliacion_bloqueado_por = null, conciliacion_bloqueado_hasta = null, "
               f"fecha_factura = date '2026-07-15' where id = {_lit(factura_id)};")


def _pareja(linea, a=(810001, "97.00"), b=(810002, "3.00")):
    return [{"tipo_relacion": "UNO_A_VARIOS", "factura_albaran_extraido_id": linea, "albaran_farmacia": "PIO",
             "albaran_id_contador": c, "importe_aplicado": i} for c, i in (a, b)]


@pytest.fixture
def factura_r17(base24, tmp_path):
    pg = base24
    _, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    factura = ids["08007973"]
    linea = _linea_sintetica(pg, factura)
    _albaran(pg, 810001, "08Z00001", "97.00", 7001)
    _albaran(pg, 810002, "Q999001/2026", "3.00", 7001)
    return pg, factura, linea, ids


def test_la_bd_acepta_la_pareja_r17_y_reserva_ambos(factura_r17):
    pg, factura, linea, _ = factura_r17
    _persistir(pg, factura, _pareja(linea))
    assert {r["albaran_id_contador"]: r["factura_id"] for r in _reservas(pg)} == {810001: factura, 810002: factura}


@pytest.mark.parametrize("caso", ["otra_recepcion", "sin_recepcion", "sin_interno", "dos_internos", "otro_numero",
                                  "importe_no_es_el_puc", "suma_fuera", "un_detalle", "tres_detalles",
                                  "otra_factura", "abono", "otro_proveedor", "sin_origen"])
def test_la_bd_rechaza_parejas_que_no_son_r17(factura_r17, caso):
    pg, factura, linea, ids = factura_r17
    detalles = _pareja(linea)
    if caso == "otra_recepcion":
        _albaran(pg, 810003, "Q999003/2026", "3.00", 7002)
        detalles = _pareja(linea, b=(810003, "3.00"))
    elif caso == "sin_recepcion":
        pg.sql("update public.albaranes set id_recepcion = null where id_contador in (810001, 810002);")
    elif caso == "sin_interno":
        _albaran(pg, 810003, "08Z00009", "3.00", 7001)
        detalles = _pareja(linea, b=(810003, "3.00"))
    elif caso == "dos_internos":
        _albaran(pg, 810003, "Q999003/2026", "97.00", 7001)
        detalles = _pareja(linea, a=(810003, "97.00"))
    elif caso == "otro_numero":
        _albaran(pg, 810003, "08Z00002", "97.00", 7001)
        detalles = _pareja(linea, a=(810003, "97.00"))
    elif caso == "importe_no_es_el_puc":
        detalles = _pareja(linea, a=(810001, "97.01"))
    elif caso == "suma_fuera":
        pg.sql("update public.albaranes set importe_puc = 3.06 where id_contador = 810002;")
        detalles = _pareja(linea, b=(810002, "3.06"))
    elif caso == "un_detalle":
        detalles = detalles[:1]
    elif caso == "tres_detalles":
        detalles = detalles + [{**detalles[0], "tipo_relacion": "UNO_A_UNO", "albaran_id_contador": None,
                                "albaran_farmacia": None, "importe_aplicado": "0"}]
    elif caso == "otra_factura":
        detalles = _pareja(_linea_sintetica(pg, ids["08007972"]))
    elif caso == "abono":
        pg.sql(f"update public.facturas_albaranes_extraidos set tipo_movimiento = 'ABONO' where id = {_lit(linea)};")
    elif caso == "otro_proveedor":
        pg.sql("update public.albaranes set id_proveedor = '52' where id_contador = 810002;")
    elif caso == "sin_origen":
        detalles = [{k: v for k, v in d.items() if k != "factura_albaran_extraido_id"} for d in detalles]
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items() if k not in ("facturas", "historial")}
    with pytest.raises(RuntimeError, match="LINEA_R17_NO_VALIDA|conciliacion_detalles_origen_check"):
        _persistir(pg, factura, detalles)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items() if k not in ("facturas", "historial")} == antes
    assert _reservas(pg) == []


def test_la_bd_acepta_la_letra_final(factura_r17):
    pg, factura, linea, _ = factura_r17
    _albaran(pg, 810003, "08Z00001A", "97.00", 7001)
    _persistir(pg, factura, _pareja(linea, a=(810003, "97.00")))
    assert sorted(r["albaran_id_contador"] for r in _reservas(pg)) == [810002, 810003]


def test_la_bd_rechaza_un_albaran_r17_reservado_por_otra_factura(factura_r17):
    pg, factura, linea, ids = factura_r17
    otra = ids["08007972"]
    otra_linea = _linea_sintetica(pg, otra, numero="08Z00005", importe="3.00")
    _persistir(pg, otra, [{"tipo_relacion": "UNO_A_UNO", "factura_albaran_extraido_id": otra_linea,
                           "albaran_farmacia": "PIO", "albaran_id_contador": 810002, "importe_aplicado": "3.00"}])
    with pytest.raises(RuntimeError, match="ALBARAN_YA_CONCILIADO:PIO:810002"):
        _persistir(pg, factura, _pareja(linea))


# --------------------------------------------------------------------------- despliegue

SCRIPT_24 = ROOT / "pruebas/auditoria_2be/desplegar_24.py"


def _commit_de_la_24() -> tuple[str, str]:
    commit = subprocess.run(["git", "-C", str(ROOT), "log", "-n", "1", "--format=%H", "--",
                             "sql/migrations/24_cf_r17_recepcion.sql"],
                            capture_output=True, text=True).stdout.strip()
    if not commit:
        pytest.skip("migracion 24 sin commit: el ensayo del despliegue exige verificar el SHA contra un commit")
    local = MIGRACION_24.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return commit, hashlib.sha256(local.encode("utf-8")).hexdigest()


def _cargar_despliegue():
    spec = importlib.util.spec_from_file_location(f"desplegar_24_{uuid.uuid4().hex[:6]}", SCRIPT_24)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_sql_de_precondiciones_24_es_de_solo_lectura(base24, pg17_nueva_base):
    sql = _cargar_despliegue().PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert ast.parse(SCRIPT_24.read_text(encoding="utf-8"))
    pg23 = pg17_nueva_base("23")
    assert pg23.sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 9)
    assert base24.sql("begin read only; " + sql + "; rollback;").split("|")[0] == "f"


def test_ensayo_completo_despliegue_24_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch):
    commit, sha = _commit_de_la_24()
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "23"))
    _datos_previos(pg, tmp_path)
    referencia = base_desde(nombre, pg.db)
    referencia.sql(MIGRACION_24.read_text(encoding="utf-8"))

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
            _cargar_despliegue().main(commit, sha, salida)
        except SystemExit:
            pass
        return json.loads(salida.read_text(encoding="utf-8"))

    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    reservas = _reservas(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit)
    assert registro["precondiciones"] == [True] * 9
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "rpc_r17": True, "privilegios": True}
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes and _reservas(pg) == reservas

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    assert registro["precondiciones"][0] is False and all(registro["precondiciones"][1:])
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
