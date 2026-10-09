"""Hito 2BA: migracion 21 (R15 exclusividad de albaranes, R16) certificada en PostgreSQL 17 local.

Plantillas (pg17_local): "20" (estado productivo actual), "21" = 20 + migracion 21 dos
veces, "21_rollback" = 21 + rollback. Caso real: PDF del 2AO (fixture local excluido de
git), normalizado con el extractor vigente salvo en 08007971, que reproduce el estado 2AO
para enriquecerlo (helpers del 2AZ). Sin produccion ni Farmatic.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import pg17_local as pgl
from pg17_local import FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, _lit, _locks, base_desde, esquema
from test_integracion_pg17_2az import (
    CONSULTAS_HUELLA, DSN_FICTICIO, _albaranes_operacionales_08007971, _datos_previos, _elegibilidad, _huella,
    _operacionales_sinteticos, _preparar_2ao, _solo_primera, _sr, contenedor_tcp,  # noqa: F401 (fixture)
)
from src.facturas.runtime_supabase.compositor_manual import construir_worker_enriquecimiento_manual
from src.facturas.runtime_supabase.modelos import ConfiguracionRuntime
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion


pytestmark = pytest.mark.pg17_local

MIGRACION_21 = MIG / "21_cf_exclusividad_albaranes.sql"
ROLLBACK_21 = MIG / "21_cf_exclusividad_albaranes.rollback.sql"
RESERVAS = "public.conciliacion_albaranes_reservados"


@pytest.fixture
def base21(pg17_nueva_base):
    return pg17_nueva_base("21")


def _orden(pg, ids, primeras: list[str]) -> None:
    """Ordering del selector: ``primeras`` en ese orden, el resto despues."""
    pg.sql(f"update public.facturas set fecha_factura = date '2026-07-01' "
           f"where id in ({','.join(_lit(v) for v in ids.values())});")
    for i, numero in enumerate(primeras, 1):
        pg.sql(f"update public.facturas set fecha_factura = date '2026-06-0{i}' where id = {_lit(ids[numero])};")


def _reservas(pg) -> list[dict]:
    return pg.json(f"select albaran_farmacia, albaran_id_contador, factura_id::text, conciliacion_id::text, orden "
                   f"from {RESERVAS} order by albaran_id_contador")


def _vigente(pg, factura_id) -> dict:
    return pg.json("select id::text, intento, resultado, diferencia::text, "
                   "(select count(*) from public.conciliacion_detalles d where d.conciliacion_id = c.id "
                   "   and d.tipo_relacion = 'UNO_A_UNO') as casados, "
                   "(select json_agg(d.provenance->>'estado_matching' order by d.orden) "
                   "   from public.conciliacion_detalles d where d.conciliacion_id = c.id) as estados "
                   f"from public.conciliaciones c where c.factura_id = {_lit(factura_id)} and c.es_actual")[0]


def _persistir_directo(pg, factura_id, detalles, *, resultado="DIFERENCIA", diferencia="1"):
    # Una linea UNO_A_UNO necesita origen documental (conciliacion_detalles_origen_check, migracion 14):
    # se enlaza con los albaranes extraidos de la propia factura, por orden.
    extraidos = [r["id"] for r in pg.json("select id::text from public.facturas_albaranes_extraidos "
                                          f"where factura_id = {_lit(factura_id)} order by orden, id")]
    assert extraidos
    detalles = [{"factura_albaran_extraido_id": extraidos[i % len(extraidos)], **d} for i, d in enumerate(detalles)]
    worker = "w-" + uuid.uuid4().hex[:6]
    pg.sql("update public.facturas set fecha_factura = date '2026-05-01', conciliacion_proximo_at = null, "
           f"estado_conciliacion_cf = 'PENDIENTE_CONCILIAR' where id = {_lit(factura_id)};")
    assert _sr(pg, f"select id from public.cf_reclamar_factura_conciliacion_manual_one_shot('{worker}', 300);") == \
        factura_id
    cuerpo = {"resultado": resultado, "importe_factura": "1", "importe_explicado": "0", "diferencia": diferencia,
              "tolerancia": "0.0500", "detalles": detalles}
    try:
        return _sr(pg, f"select public.cf_persistir_conciliacion({_lit(factura_id)}::uuid, '{worker}', "
                       f"'MANUAL_ONE_SHOT', 'directa-{uuid.uuid4().hex}', {_lit(json.dumps(cuerpo))}::jsonb);")
    finally:
        pg.sql("update public.facturas set conciliacion_bloqueado_por = null, conciliacion_bloqueado_hasta = null, "
               f"fecha_factura = date '2026-07-15' where id = {_lit(factura_id)};")


# --------------------------------------------------------------------------- R15: dos facturas, un albaran

def test_r15_dos_facturas_compiten_por_el_mismo_albaran(base21, tmp_path):
    pg = base21
    cliente, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    a, b = ids["08007973"], ids["08007972"]
    _operacionales_sinteticos(pg, a, 0, 970000)  # albaranes con el numero y el importe de 08007973
    [x] = pg.json(f"select e.id::text as extraido, e.numero_albaran, al.id_contador from public.facturas_albaranes_extraidos e "
                  f"join public.albaranes al on al.numero_albaran = e.numero_albaran and al.id_contador >= 970000 "
                  f"where e.factura_id = {_lit(a)} order by e.orden limit 1")
    # B documenta tambien el albaran X (mismo numero, fecha e importe).
    pg.sql("insert into public.facturas_albaranes_extraidos (factura_id, numero_albaran, fecha_albaran, tipo_movimiento, "
           "importe_base, importe_total, descripcion, orden, literal, provenance) "
           f"select {_lit(b)}, numero_albaran, fecha_albaran, tipo_movimiento, importe_base, importe_total, descripcion, "
           f"999, literal, provenance from public.facturas_albaranes_extraidos where id = {_lit(x['extraido'])};")
    assert _elegibilidad(pg, b).startswith("APTA")
    repo = RepositorioRuntimeSupabase(cliente)

    _orden(pg, ids, ["08007973", "08007972"])
    assert construir_worker_conciliacion(repo, "conc-a").ejecutar_una_manual() is True
    conc_a = _vigente(pg, a)
    assert conc_a["resultado"] == "CONCILIADA"
    assert x["id_contador"] in [r["albaran_id_contador"] for r in _reservas(pg) if r["factura_id"] == a]

    assert construir_worker_conciliacion(repo, "conc-b").ejecutar_una_manual() is True
    conc_b = _vigente(pg, b)
    assert "ALBARAN_YA_CONCILIADO" in conc_b["estados"] and conc_b["resultado"] == "DIFERENCIA"
    assert not [r for r in _reservas(pg) if r["factura_id"] == b and r["albaran_id_contador"] == x["id_contador"]]
    assert _vigente(pg, a) == conc_a  # la conciliacion de A no cambia

    # Nuevo intento de A: reutiliza sus propios albaranes y sus reservas pasan a la nueva conciliacion.
    pg.sql(f"select public.cf_solicitar_reintento_conciliacion({_lit(a)}::uuid, 'test-2ba');")
    assert construir_worker_conciliacion(repo, "auto").ejecutar_una() is True
    nueva_a = _vigente(pg, a)
    assert nueva_a["intento"] == conc_a["intento"] + 1 and nueva_a["resultado"] == "CONCILIADA"
    assert {r["conciliacion_id"] for r in _reservas(pg) if r["factura_id"] == a} == {nueva_a["id"]}
    assert _locks(pg) == "0|0" and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_r15_la_bd_rechaza_por_rpc_albaran_de_otra_factura_o_repetido(base21, tmp_path):
    pg = base21
    _, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    a, b = ids["08007973"], ids["08007972"]
    linea = {"tipo_relacion": "UNO_A_UNO", "importe_aplicado": "1", "estado": "COINCIDE", "albaran_farmacia": "PIO"}
    _persistir_directo(pg, a, [{**linea, "orden": 1, "albaran_id_contador": 555001},
                               {**linea, "orden": 2, "albaran_id_contador": 555002}])
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    reservas = _reservas(pg)
    assert [r["albaran_id_contador"] for r in reservas] == [555001, 555002]

    with pytest.raises(RuntimeError, match="ALBARAN_YA_CONCILIADO:PIO:555002"):
        _persistir_directo(pg, b, [{**linea, "orden": 1, "albaran_id_contador": 555002}])
    with pytest.raises(RuntimeError, match="ALBARAN_YA_CONCILIADO:PIO:555009"):
        _persistir_directo(pg, b, [{**linea, "orden": 1, "albaran_id_contador": 555009},
                                   {**linea, "orden": 2, "albaran_id_contador": "555009"}])
    # Los rechazos no dejan nada (el claim y su liberacion solo tocan facturas e historial).
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items() if k not in ("facturas", "historial")} == {
        k: v for k, v in antes.items() if k not in ("facturas", "historial")}
    assert _reservas(pg) == reservas

    # La misma factura si puede reutilizar sus albaranes en un nuevo intento.
    _persistir_directo(pg, a, [{**linea, "orden": 1, "albaran_id_contador": 555002}])
    assert [r["albaran_id_contador"] for r in _reservas(pg)] == [555002]
    _persistir_directo(pg, b, [{**linea, "orden": 1, "albaran_id_contador": 555001}])
    assert {r["albaran_id_contador"]: r["factura_id"] for r in _reservas(pg)} == {555001: b, 555002: a}


def test_r15_escritura_directa_en_la_tabla_de_reservas_denegada(base21):
    for rol in ("service_role", "anon", "authenticated"):
        with pytest.raises(RuntimeError, match="permission denied"):
            base21.sql(f"set role {rol}; insert into {RESERVAS} (albaran_farmacia, albaran_id_contador, factura_id, "
                       f"conciliacion_id, orden) values ('PIO', 1, gen_random_uuid(), gen_random_uuid(), 1);")
    for rol in ("anon", "authenticated"):
        with pytest.raises(RuntimeError, match="permission denied"):
            base21.sql(f"set role {rol}; select count(*) from {RESERVAS};")
    assert base21.sql(f"set role service_role; select count(*) from {RESERVAS};") == "0"


# --------------------------------------------------------------------------- casos reales

def test_08007971_enriquecida_y_conciliada_con_la_21(base21, tmp_path):
    pg = base21
    cliente, ids = _preparar_2ao(pg, tmp_path)
    objetivo = ids["08007971"]
    resultado = construir_worker_enriquecimiento_manual(cliente, ConfiguracionRuntime(), "enr-2ba",
                                                        tmp_path / "enr").ejecutar(objetivo)
    assert (resultado["albaranes"], resultado["vencimientos"]) == (3, 1)
    _albaranes_operacionales_08007971(pg)
    _solo_primera(pg, ids, "08007971")
    assert construir_worker_conciliacion(RepositorioRuntimeSupabase(cliente), "conc-2ba").ejecutar_una_manual() is True
    c = _vigente(pg, objetivo)
    assert (c["resultado"], c["diferencia"], c["casados"]) == ("CONCILIADA", "-0.0100", 3)
    clases = pg.json("select d.provenance->>'numero_documental' as doc, d.provenance->>'clase_numero' as clase "
                     f"from public.conciliacion_detalles d where d.conciliacion_id = {_lit(c['id'])} order by d.orden")
    assert [(x["doc"], x["clase"]) for x in clases] == [("08C18299", "INTERNO"), ("08M24229", "EXACTA"),
                                                         ("08M25574", "EXACTA")]
    assert sorted(r["albaran_id_contador"] for r in _reservas(pg)) == [279694, 279774, 280053]


def test_r16_08007969_apta_con_la_21_y_no_apta_con_la_20(pg17_nueva_base, tmp_path):
    estados = {}
    for variante in ("20", "21"):
        pg = pg17_nueva_base(variante)
        _, ids = _preparar_2ao(pg, tmp_path / variante, estado_2ao=False)
        estados[variante] = {n: _elegibilidad(pg, i) for n, i in ids.items()}
    assert estados["20"]["08007969"] == "NO_APTA:TOTAL_NO_EXPLICADO"
    assert estados["21"]["08007969"] == "APTA:APTA_MIXTA"
    # Casos de control: el resto de facturas no cambia de elegibilidad.
    assert {n: e for n, e in estados["21"].items() if n != "08007969"} == {
        n: e for n, e in estados["20"].items() if n != "08007969"}


def test_casos_de_control_08007970_y_08007973_sin_cambios(base21, tmp_path):
    """Mismos resultados que con la 20 (2AZ: 08007970 CONCILIADA -0,08 con 71; produccion: 08007973 0,00 con 2).

    El codigo 2BA no concilia sobre el esquema 20 (falla cerrado sin la tabla de reservas):
    el orden de despliegue es primero la 21 y despues el codigo.
    """
    pg = base21
    cliente, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    _operacionales_sinteticos(pg, ids["08007970"], 4, 950000)  # 71 albaranes, diferencia -0,08
    _operacionales_sinteticos(pg, ids["08007973"], 0, 960000)
    _orden(pg, ids, ["08007970", "08007973"])
    repo = RepositorioRuntimeSupabase(cliente)
    for nombre in ("w1", "w2"):
        assert construir_worker_conciliacion(repo, nombre).ejecutar_una_manual() is True
    resultados = {n: {k: v for k, v in _vigente(pg, ids[n]).items() if k in ("resultado", "diferencia", "casados")}
                  for n in ("08007970", "08007973")}
    assert resultados == {"08007970": {"resultado": "CONCILIADA", "diferencia": "-0.0800", "casados": 71},
                          "08007973": {"resultado": "CONCILIADA", "diferencia": "0.0000", "casados": 2}}
    assert len(_reservas(pg)) == 73


# --------------------------------------------------------------------------- datos existentes, rollback, privilegios

def test_21_no_altera_conciliaciones_existentes_y_carga_las_reservas_vigentes(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("20")
    _datos_previos(pg, tmp_path)
    # Conciliaciones vigentes con albaran y un intento anterior que repite uno de ellos. Solo los detalles
    # con albaran extraido pueden ser UNO_A_UNO (origen_check de la 14): 08007971, en estado 2AO, no tiene
    # extraidos y su detalle sigue SIN_COINCIDENCIA, de modo que quedan 4 vigentes con albaran.
    pg.sql("update public.conciliacion_detalles d set tipo_relacion = 'UNO_A_UNO', albaran_farmacia = 'PIO', "
           "albaran_id_contador = 700000 + c.intento * 10 + (select count(*) from public.conciliaciones c2 "
           "  where c2.factura_id < c.factura_id) from public.conciliaciones c where c.id = d.conciliacion_id "
           "and d.factura_albaran_extraido_id is not null;")
    pg.sql("update public.conciliacion_detalles d set albaran_id_contador = 900001 from public.conciliaciones c "
           "where c.id = d.conciliacion_id and not c.es_actual and c.intento = 1 "
           "and d.factura_albaran_extraido_id is not null;")
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    pg.sql(MIGRACION_21.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_21.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    vigentes = pg.json("select d.albaran_farmacia, d.albaran_id_contador, c.factura_id::text, c.id::text as conciliacion_id, "
                       "d.orden from public.conciliaciones c join public.conciliacion_detalles d on d.conciliacion_id = c.id "
                       "where c.es_actual and d.albaran_id_contador is not null order by d.albaran_id_contador")
    assert len(vigentes) == 4 and _reservas(pg) == vigentes
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_21_aborta_si_dos_lineas_vigentes_comparten_albaran(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("20")
    _datos_previos(pg, tmp_path)
    pg.sql("update public.conciliacion_detalles d set tipo_relacion = 'UNO_A_UNO', albaran_farmacia = 'PIO', "
           "albaran_id_contador = 800000 from public.conciliaciones c where c.id = d.conciliacion_id and c.es_actual "
           "and d.factura_albaran_extraido_id is not null;")
    referencia = esquema(pg)
    with pytest.raises(RuntimeError, match="conciliacion_albaranes_reservados_pkey"):
        pg.sql(MIGRACION_21.read_text(encoding="utf-8"))
    assert esquema(pg) == referencia


def test_rollback_21_devuelve_exactamente_el_esquema_20(pg17_nueva_base):
    assert esquema(pg17_nueva_base("21_rollback")) == esquema(pg17_nueva_base("20"))
    assert esquema(pg17_nueva_base("21")) != esquema(pg17_nueva_base("20"))


def test_rollback_21_conserva_las_conciliaciones(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("21")
    _, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    linea = {"tipo_relacion": "UNO_A_UNO", "importe_aplicado": "1", "estado": "COINCIDE", "albaran_farmacia": "PIO"}
    _persistir_directo(pg, ids["08007973"], [{**linea, "orden": 1, "albaran_id_contador": 555001}])
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    pg.sql(ROLLBACK_21.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql(f"select to_regclass('{RESERVAS}') is null") == "t"


def test_privilegios_de_la_21(base21):
    filas = {f["f"]: f for f in base21.json(
        "select p.proname as f, p.prosecdef as definer, pg_get_userbyid(p.proowner) as owner, "
        "exists(select 1 from aclexplode(p.proacl) a where a.grantee = 0) as public, "
        "has_function_privilege('anon', p.oid, 'EXECUTE') as anon, "
        "has_function_privilege('authenticated', p.oid, 'EXECUTE') as authenticated, "
        "has_function_privilege('service_role', p.oid, 'EXECUTE') as service_role "
        "from pg_proc p where p.pronamespace = 'public'::regnamespace "
        "and p.proname in ('cf_persistir_conciliacion', 'cf_evaluar_elegibilidad_conciliacion', 'cf_enriquecer_factura')")}
    for nombre, f in filas.items():
        assert (f["definer"], f["owner"], f["public"], f["anon"], f["authenticated"], f["service_role"]) == (
            True, "postgres", False, False, False, True), nombre
    [t] = base21.json(
        "select c.relrowsecurity as rls, pg_get_userbyid(c.relowner) as owner, "
        "has_table_privilege('service_role', c.oid, 'SELECT') as sr_select, "
        "has_table_privilege('service_role', c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE') as sr_escribe, "
        "has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE') as anon, "
        "has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE') as authenticated "
        f"from pg_class c where c.oid = '{RESERVAS}'::regclass")
    assert t == {"rls": True, "owner": "postgres", "sr_select": True, "sr_escribe": False, "anon": False,
                 "authenticated": False}


# --------------------------------------------------------------------------- ensayo del script de despliegue de la 21

SCRIPT_21 = ROOT / "pruebas/auditoria_2ba/desplegar_21.py"


def _commit_de_la_21() -> tuple[str, str]:
    commit = subprocess.run(["git", "-C", str(ROOT), "log", "-n", "1", "--format=%H", "--",
                             "sql/migrations/21_cf_exclusividad_albaranes.sql"],
                            capture_output=True, text=True).stdout.strip()
    if not commit:
        pytest.skip("migracion 21 sin commit: el ensayo del despliegue exige verificar el SHA contra un commit")
    import hashlib
    local = MIGRACION_21.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return commit, hashlib.sha256(local.encode("utf-8")).hexdigest()


def _cargar_script():
    spec = importlib.util.spec_from_file_location(f"desplegar_21_{uuid.uuid4().hex[:6]}", SCRIPT_21)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _sql_precondiciones() -> str:
    arbol = ast.parse(SCRIPT_21.read_text(encoding="utf-8"))
    [consulta] = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute"
                  and n.args and "has_table_privilege" in ast.unparse(n.args[0])]
    return eval(compile(ast.Expression(consulta.args[0]), str(SCRIPT_21), "eval"), vars(_cargar_script()))


def test_ensayo_completo_despliegue_21_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch):
    commit, sha = _commit_de_la_21()
    nombre, puerto, plantilla_19 = contenedor_tcp
    plantilla = pgl.construir_plantilla(nombre, "20")
    pg = base_desde(nombre, plantilla)
    _datos_previos(pg, tmp_path)
    pg.sql("update public.conciliacion_detalles d set tipo_relacion = 'UNO_A_UNO', albaran_farmacia = 'PIO', "
           "albaran_id_contador = 600000 + c.intento + (select count(*) * 10 from public.conciliaciones c2 "
           "  where c2.factura_id < c.factura_id) from public.conciliaciones c where c.id = d.conciliacion_id "
           # origen_check de la 14: 08007971 (estado 2AO) no tiene extraidos; su detalle sigue SIN_COINCIDENCIA.
           "and d.factura_albaran_extraido_id is not null;")
    referencia = base_desde(nombre, pg.db)
    referencia.sql(MIGRACION_21.read_text(encoding="utf-8"))
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

    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit)
    assert registro["precondiciones"] == [True] * 9
    assert registro["reservas_cargadas"] == registro["lineas_vigentes_con_albaran"] == 4
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    assert registro["precondiciones"][0] is False and all(registro["precondiciones"][1:])
    assert esquema(pg) == esquema(referencia)


def test_sql_de_precondiciones_21_es_de_solo_lectura():
    sql = _sql_precondiciones()
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter "))


# --------------------------------------------------------------------------- lector READ_ONLY del 2AT paginado (2BA)

def _lector_2at(pg):
    """``_Lector`` del 2AT sobre una transaccion REPEATABLE READ READ ONLY real (conexion del ensayo 2AT)."""
    sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
    import auditoria_readonly as ar
    from test_ensayo_fase4_2at import _ConexionPg17

    sentencias: list[str] = []
    return ar, ar._Lector(_ConexionPg17(pg, sentencias).cursor()), sentencias


def test_lector_2at_pagina_todas_las_filas_con_mas_de_1000(base21):
    from src.facturas.runtime_supabase.repositorios import leer_paginado

    base21.sql("insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
               "importe_pvp,importe_puc,descuento,estado) select 'PIO', 800000 + n, '2', '1.- SAFA', "
               "'08P' || lpad(n::text, 5, '0'), date '2026-07-01', 2, 1, 0, 'PENDIENTE' "
               "from generate_series(1, 2500) n;")
    ar, lector, sentencias = _lector_2at(base21)
    cliente = ar._ClienteLectura(lector)

    filas = leer_paginado(lambda: cliente.table("albaranes").select("id_contador,numero_albaran")
                          .eq("farmacia", "PIO").gte("id_contador", 800001).order("id_contador"))

    assert [f["id_contador"] for f in filas] == list(range(800001, 802501))  # todas, sin huecos ni duplicados
    paginas = [s for s in sentencias if " limit " in s]
    assert len(paginas) == 4  # 1000 + 1000 + 500 + pagina vacia
    assert all(ar._SOLO_LECTURA.match(s) or s.lstrip().lower().startswith("set local") for s in sentencias)
    # La tabla de reservas de la 21 es legible por el lector (R15).
    assert leer_paginado(lambda: cliente.table("conciliacion_albaranes_reservados")
                         .select("albaran_farmacia,albaran_id_contador,factura_id").order("albaran_id_contador")) == []


def test_lector_2at_rango_falla_cerrado(base21):
    ar, lector, _ = _lector_2at(base21)
    cliente = ar._ClienteLectura(lector)
    with pytest.raises(PermissionError, match="RANGO_SIN_ORDEN"):
        cliente.table("albaranes").select("id_contador").range(0, 999).execute()
    with pytest.raises(PermissionError, match="RANGO_SIN_ORDEN_O_CON_SINGLE"):
        cliente.table("albaranes").select("id_contador").order("id_contador").range(0, 0).single().execute()
    for inicio, fin in ((-1, 10), (10, 9), ("0", 9)):
        with pytest.raises(PermissionError, match="RANGO_NO_VALIDO"):
            cliente.table("albaranes").range(inicio, fin)
    with pytest.raises(PermissionError, match="TABLA_NO_AUTORIZADA"):
        cliente.table("conciliaciones")
