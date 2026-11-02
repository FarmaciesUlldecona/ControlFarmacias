"""Hito 2BK: migracion 26 (persistencia multifactura indexada) en PostgreSQL 17 local.

Plantillas (pg17_local): "25" (estado productivo), "26" = 25 + migracion 26 dos veces, "26_rollback" = 26 +
rollback. Equivalencia: cada escenario se ejecuta con el MISMO payload real (PDF Alliance multifactura del 2AP,
capturado una vez del worker manual real) sobre una base 25 y otra 26, y el estado completo de las tablas de
normalizacion debe coincidir (UUID generados por la base, sufijo del worker y marcas de tiempo canonicalizados).
Sin produccion ni Farmatic.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import uuid

import pytest

import pg17_local as pgl
from pg17_local import FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, _lit, base_desde, esquema
from test_ensayo_fase4_2at import _ClienteServiceRole
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _datos_previos, _huella, contenedor_tcp)
from test_integracion_pg17_2ba import _reservas
from src.facturas.runtime_supabase.compositor_manual import construir_worker_manual_productivo
from src.facturas.runtime_supabase.modelos import ConfiguracionRuntime

pytestmark = pytest.mark.pg17_local

MIGRACION_26 = MIG / "26_cf_persistencia_multifactura_indexada.sql"
ROLLBACK_26 = MIG / "26_cf_persistencia_multifactura_indexada.rollback.sql"
RUTA_26 = "sql/migrations/26_cf_persistencia_multifactura_indexada.sql"
SCRIPT_26 = ROOT / "pruebas/auditoria_2bk/desplegar_26.py"
MULTI = "cf_persistir_documento_multifactura"
DOC_A = "00000000-0000-4000-8000-00000000000a"
DOC_B = "00000000-0000-4000-8000-00000000000b"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
MARCA_TIEMPO = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
GRANDES = {
    "facturas": "to_jsonb(t) - 'datos_extraidos' || jsonb_build_object('datos_md5', md5(t.datos_extraidos::text))",
    "normalizacion_ejecuciones": "to_jsonb(t) - 'resultado_json' "
                                 "|| jsonb_build_object('resultado_md5', md5(coalesce(t.resultado_json::text, '')))",
}
TABLAS = ("documentos_facturas", "facturas", "facturas_albaranes_extraidos", "facturas_impuestos",
          "facturas_vencimientos", "facturas_movimientos", "facturas_incidencias", "historial_facturas",
          "normalizacion_ejecuciones")
_CAPTURA: dict = {}


# --------------------------------------------------------------------------- utilidades

def _base(pg17_nueva_base, variante):
    pg = pg17_nueva_base(variante)
    pg.sql("update public.documentos_facturas set estado_lectura = 'NORMALIZADA' "
           "where estado_lectura in ('PENDIENTE', 'ERROR');")
    return pg


def _documento(pg, doc, orden=1, sha=None):
    sha = sha or hashlib.sha256(doc.encode()).hexdigest()
    pg.sql("insert into public.documentos_facturas(id,farmacia,archivo_nombre,archivo_ruta,archivo_hash,"
           f"fecha_importacion) values ({_lit(doc)},'PIO','no-es-evidencia.pdf','PIO/2BK/{doc}.pdf',"
           f"{_lit(sha)}, timestamptz '2000-01-01' + interval '{orden} minutes');")


def _claim(pg, worker):
    return pg.json(f"select id from public.cf_reclamar_documento_normalizacion_manual_one_shot({_lit(worker)}, 300)")


def _captura(pg17_nueva_base, tmp_path) -> dict:
    """Payload real de la RPC multifactura (una vez por sesion): worker manual sobre el PDF Alliance del 2AP."""
    if not _CAPTURA:
        pg = _base(pg17_nueva_base, "25")
        cliente = _ClienteServiceRole(pg)
        pdf = pgl.ALLIANCE.read_bytes()
        _documento(pg, DOC_A, sha=hashlib.sha256(pdf).hexdigest())  # el worker comprueba el SHA del PDF
        cliente.objetos[("facturas-pdf", f"PIO/2BK/{DOC_A}.pdf")] = pdf
        retorno = construir_worker_manual_productivo(
            cliente, ConfiguracionRuntime(), "captura-2bk", tmp_path / "captura").ejecutar_una_manual()
        assert retorno.documentos_reclamados == 1
        [payload] = [p for n, p in cliente.rpcs if n == MULTI]
        _CAPTURA.update(payload)
    return dict(_CAPTURA)


def _persistir(pg, doc, worker, clave, captura, *, resultado=None, segmentos=None, disparador="MANUAL_ONE_SHOT"):
    return _ClienteServiceRole(pg)._rpc(MULTI, {
        "p_documento_id": doc, "p_worker_id": worker, "p_idempotency_key": clave,
        "p_resultado_hash": captura["p_resultado_hash"],
        "p_resultado": captura["p_resultado"] if resultado is None else resultado,
        "p_segmentos_autorizados": captura["p_segmentos_autorizados"] if segmentos is None else segmentos,
        "p_disparador": disparador})


def _intento(funcion, *args, **kwargs):
    """Resultado o codigo de error (primera linea ERROR) de una llamada."""
    try:
        return ("OK", funcion(*args, **kwargs))
    except RuntimeError as exc:
        return ("ERROR", re.search(r"ERROR:\s+(.*)", str(exc)).group(1).strip())


def _canonico(valor):
    if isinstance(valor, dict):
        return {k: _canonico(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_canonico(v) for v in valor]
    if isinstance(valor, str):
        if MARCA_TIEMPO.match(valor):
            return "<ts>"
        return re.sub(r"#[0-9a-f]{12}\b", "#W", valor)
    return valor


def _numerado(valor):
    """UUID numerados por orden de aparicion (las bases generan los suyos)."""
    numeros: dict[str, str] = {}
    texto = json.dumps(valor, ensure_ascii=False)
    return json.loads(UUID.sub(lambda m: numeros.setdefault(m.group(0), f"U{len(numeros)}"), texto))


def _volcado(pg) -> dict:
    """Estado completo de las tablas de normalizacion (filas ordenadas sin depender de los UUID)."""
    filas = {}
    for tabla in TABLAS:
        expresion = GRANDES.get(tabla, "to_jsonb(t)")
        filas[tabla] = sorted(
            (json.dumps(_canonico(f), sort_keys=True, ensure_ascii=False)
             for f in pg.json(f"select {expresion} as fila from public.{tabla} t")),
            key=lambda s: UUID.sub("U", s))
    return filas


# --------------------------------------------------------------------------- escenarios

def _nuevo(pg, c):
    _documento(pg, DOC_A)
    _claim(pg, "w-a")
    return [_intento(_persistir, pg, DOC_A, "w-a", "k-a", c)]


def _duplicado(pg, c):
    pasos = _nuevo(pg, c)
    _documento(pg, DOC_B, 2)
    _claim(pg, "w-b")
    return pasos + [_intento(_persistir, pg, DOC_B, "w-b", "k-b", c)]


def _version_incompatible(pg, c):
    pasos = _nuevo(pg, c)
    # Misma factura (nucleo [1:4]) con otro total: la fila indexada cambia y la busqueda la debe encontrar.
    pg.sql("update public.facturas set datos_extraidos = jsonb_set(datos_extraidos, '{totales,total,valor}', "
           "to_jsonb((datos_extraidos#>>'{totales,total,valor}')::numeric + 1)) "
           f"where id = (select id from public.facturas where documento_id = {_lit(DOC_A)} "
           "order by numero_factura limit 1);")
    _documento(pg, DOC_B, 2)
    _claim(pg, "w-b")
    return pasos + [_intento(_persistir, pg, DOC_B, "w-b", "k-b", c)]


def _replay(pg, c):
    pasos = _nuevo(pg, c)
    otro = dict(c["p_resultado"], extra_2bk=1)
    return pasos + [_intento(_persistir, pg, DOC_A, "w-a", "k-a", c),
                    _intento(_persistir, pg, DOC_A, "w-a", "k-a", c, resultado=otro)]


def _relectura(pg, c):
    pasos = _nuevo(pg, c)
    pg.sql(f"select public.cf_solicitar_reprocesado({_lit(DOC_A)}, 'pio');")
    _claim(pg, "w-r")
    return pasos + [_intento(_persistir, pg, DOC_A, "w-r", "k-r", c, disparador="REPROCESADO")]


def _parcial(pg, c):
    _documento(pg, DOC_A)
    _claim(pg, "w-a")
    return [_intento(_persistir, pg, DOC_A, "w-a", "k-a", c, segmentos=c["p_segmentos_autorizados"][:1])]


def _seis_parametros(pg, c):
    _documento(pg, DOC_A)
    _claim(pg, "w-a")
    segmentos = "array[" + ",".join(_lit(s) for s in c["p_segmentos_autorizados"]) + "]::text[]"
    resultado = _lit(json.dumps(c["p_resultado"], ensure_ascii=False)) + "::jsonb"
    return [_intento(pg.sql, f"select public.{MULTI}({_lit(DOC_A)}::uuid, 'w-a', 'k-a', "
                             f"{_lit(c['p_resultado_hash'])}, {resultado}, {segmentos});")]


def _un_documento(pg, c):
    _documento(pg, DOC_A)
    _claim(pg, "w-a")
    factura = dict(c["p_resultado"]["facturas"][0], factura_id="k-unica")
    payload = {"resultado_json": dict(c["p_resultado"], facturas=[factura]), "uso_luna": False}
    cliente = _ClienteServiceRole(pg)
    return [_intento(cliente._rpc, "cf_persistir_normalizacion", {
        "p_documento_id": DOC_A, "p_worker_id": "w-a", "p_disparador": "MANUAL_ONE_SHOT",
        "p_idempotency_key": "k-a", "p_resultado_hash": c["p_resultado_hash"], "p_resultado": payload})]


def _claim_ajeno(pg, c):
    _documento(pg, DOC_A)
    _claim(pg, "w-a")
    return [_intento(_persistir, pg, DOC_A, "otro", "k-a", c)]


ESCENARIOS = {"nuevo": _nuevo, "duplicado": _duplicado, "version_incompatible": _version_incompatible,
              "replay": _replay, "relectura": _relectura, "parcial": _parcial,
              "seis_parametros": _seis_parametros, "un_documento": _un_documento, "claim_ajeno": _claim_ajeno}
# Lo que cada escenario debe ejercitar (para que la igualdad no sea trivial).
ESPERADO = {
    "nuevo": ("COMPLETA", ["PERSISTIDAS"] * 3),
    "duplicado": ("COMPLETA", ["DUPLICADAS"] * 3),
    "version_incompatible": ("REQUIERE_REVISION", ["DUPLICADAS", "DUPLICADAS", "REQUIERE_REVISION"]),
    "relectura": ("COMPLETA", ["PERSISTIDAS"] * 3),
    "parcial": ("PARCIAL", ["PENDIENTES", "PENDIENTES", "PERSISTIDAS"]),
    "seis_parametros": ("COMPLETA", ["PERSISTIDAS"] * 3),
}


@pytest.mark.parametrize("escenario", sorted(ESCENARIOS))
def test_26_da_el_mismo_resultado_que_la_25(pg17_nueva_base, tmp_path, escenario):
    captura = _captura(pg17_nueva_base, tmp_path)
    estados = {}
    for variante in ("25", "26"):
        pg = _base(pg17_nueva_base, variante)
        pasos = ESCENARIOS[escenario](pg, captura)
        estados[variante] = _numerado({"pasos": _canonico(pasos), "volcado": _volcado(pg)})
    assert estados["26"] == estados["25"]
    pasos = estados["26"]["pasos"]
    objetivo = DOC_B if escenario in ("duplicado", "version_incompatible") else DOC_A
    [documento] = pg.json("select estado_lectura, estado_persistencia, inventario_facturas "
                          f"from public.documentos_facturas where id = {_lit(objetivo)}")
    if escenario in ESPERADO:
        persistencia, inventario = ESPERADO[escenario]
        assert documento["estado_persistencia"] == persistencia
        assert sorted(i["estado"] for i in documento["inventario_facturas"]) == sorted(inventario)
    if escenario == "replay":
        assert pasos[1][0] == "OK" and pasos[2] == ["ERROR", "IDEMPOTENCIA_PAYLOAD_DISTINTO"]
    if escenario == "claim_ajeno":
        assert pasos == [["ERROR", "CLAIM_DOCUMENTAL_NO_VALIDO"]]
    if escenario == "un_documento":
        assert pasos[0][0] == "OK" and documento["estado_lectura"] == "NORMALIZADA"


def _escrituras_ejecuciones(pg) -> dict:
    pg.sql("select pg_stat_force_next_flush();")
    return pg.json("select n_tup_ins as inserciones, n_tup_upd as actualizaciones from pg_stat_user_tables "
                   "where relid = 'public.normalizacion_ejecuciones'::regclass")[0]


def test_la_26_escribe_la_ejecucion_una_sola_vez_con_el_mismo_contenido(pg17_nueva_base, tmp_path):
    captura = _captura(pg17_nueva_base, tmp_path)
    contenido, escrituras = {}, {}
    for variante in ("25", "26"):
        pg = _base(pg17_nueva_base, variante)
        antes = _escrituras_ejecuciones(pg)
        _nuevo(pg, captura)
        despues = _escrituras_ejecuciones(pg)
        escrituras[variante] = {k: despues[k] - antes[k] for k in despues}
        contenido[variante] = pg.json(
            "select disparador, md5(resultado_json::text) as resultado, "
            "resultado_json->'provenance_ejecucion' as provenance "
            f"from public.normalizacion_ejecuciones where documento_id = {_lit(DOC_A)}")
    assert contenido["26"] == contenido["25"]
    assert contenido["26"][0]["provenance"] == {"modo_ejecucion": "MANUAL_ONE_SHOT"}
    assert contenido["26"][0]["disparador"] == "MANUAL_ONE_SHOT"
    assert escrituras == {"25": {"inserciones": 1, "actualizaciones": 2},
                          "26": {"inserciones": 1, "actualizaciones": 0}}


def test_la_busqueda_de_identidad_usa_el_indice_aun_sin_estadisticas(pg17_nueva_base, tmp_path):
    """Plan generico (como el de PL/pgSQL) sobre una tabla sin ANALYZE: la 25 recorre la tabla, la 26 no."""
    captura = _captura(pg17_nueva_base, tmp_path)
    planes = {}
    for variante in ("25", "26"):
        pg = _base(pg17_nueva_base, variante)
        _nuevo(pg, captura)
        planes[variante] = pg.sql(
            "set plan_cache_mode = force_generic_plan; "
            "prepare q(text[]) as select id, documento_id, datos_extraidos from public.facturas "
            "where (public.cf_componentes_identidad_factura(datos_extraidos))[1:4] = $1[1:4] order by ctid; "
            "explain (costs off) execute q('{A50004324,08007970,FACTURA,40901058C}');")
    assert "Seq Scan on facturas" in planes["25"]
    assert "Index Scan using facturas_identidad_nucleo_idx" in planes["26"] and "Seq Scan" not in planes["26"]


# --------------------------------------------------------------------------- migracion

def test_generador_reproduce_la_26_y_su_rollback():
    spec = importlib.util.spec_from_file_location("generar_26", ROOT / "pruebas/auditoria_2bk/generar_migracion_26.py")
    generador = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generador)
    assert generador.migracion() == MIGRACION_26.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert generador.rollback() == ROLLBACK_26.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_rollback_26_devuelve_exactamente_el_esquema_25(pg17_nueva_base):
    assert esquema(pg17_nueva_base("26_rollback")) == esquema(pg17_nueva_base("25"))
    assert esquema(pg17_nueva_base("26")) != esquema(pg17_nueva_base("25"))


def test_26_exige_la_25(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_25_AUSENTE"):
        pg17_nueva_base("24").sql(MIGRACION_26.read_text(encoding="utf-8"))


def test_26_no_altera_datos_existentes(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("25")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    facturas = pg.sql("select md5(string_agg(md5(to_jsonb(f)::text), '' order by f.id)) from public.facturas f")
    referencia = esquema(pg17_nueva_base("26"))
    pg.sql(MIGRACION_26.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_26.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql("select md5(string_agg(md5(to_jsonb(f)::text), '' order by f.id)) from public.facturas f") == facturas
    assert esquema(pg) == referencia and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_privilegios_de_la_26(pg17_nueva_base):
    pg = pg17_nueva_base("26")
    rpc = ("public.cf_persistir_normalizacion(uuid,text,text,text,text,jsonb)",
           "public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)")
    internas = ("public.cf_persistir_normalizacion_nucleo(uuid,text,text,text,text,jsonb,jsonb)",
                "public.cf_persistir_documento_multifactura_nucleo(uuid,text,text,text,jsonb,text[],text)",
                "public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[])")
    for funcion in rpc + internas:
        for rol in ("service_role", "anon", "authenticated"):
            esperado = "t" if funcion in rpc and rol == "service_role" else "f"
            assert pg.sql(f"select has_function_privilege('{rol}', '{funcion}', 'EXECUTE')") == esperado, (funcion, rol)
        assert pg.sql(f"select prosecdef::text || '|' || pg_get_userbyid(proowner) from pg_proc "
                      f"where oid = '{funcion}'::regprocedure") == "true|postgres"
    assert pg.sql("select procost from pg_proc where oid = 'public.cf_componentes_identidad_factura(jsonb)'::regprocedure") \
        == "10000"
    assert pg.sql("select pg_get_userbyid(c.relowner) from pg_class c where c.oid = "
                  "'public.facturas_identidad_nucleo_idx'::regclass") == "postgres"


# --------------------------------------------------------------------------- despliegue

def _cargar_despliegue(script=SCRIPT_26):
    spec = importlib.util.spec_from_file_location(f"desplegar_26_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_sql_de_precondiciones_26_es_de_solo_lectura(pg17_nueva_base):
    sql = _cargar_despliegue().PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert ast.parse(SCRIPT_26.read_text(encoding="utf-8"))
    assert pg17_nueva_base("25").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 9)
    assert pg17_nueva_base("26").sql("begin read only; " + sql + "; rollback;").split("|")[0] == "f"


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf2bk_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    """Copia byte a byte el script y la migracion a un repositorio git temporal con su commit."""
    for relativa in (RUTA_26, "pruebas/auditoria_2bk/desplegar_26.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 26"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_26.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_2bk/desplegar_26.py")


def test_ensayo_completo_despliegue_26_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "25"))
    _datos_previos(pg, tmp_path)
    referencia = base_desde(nombre, pg.db)
    referencia.sql(MIGRACION_26.read_text(encoding="utf-8"))
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)

    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    import dotenv
    import psycopg2

    real = getattr(psycopg2, "_connect_original_2az", psycopg2.connect)
    psycopg2._connect_original_2az = real
    dsns = []

    def conectar_local(dsn, **_kwargs):
        dsns.append(dsn)
        return real(host="127.0.0.1", port=puerto, dbname=pg.db, user="postgres", password="local-only",
                    connect_timeout=10)

    monkeypatch.setattr(psycopg2, "connect", conectar_local)
    monkeypatch.setattr(dotenv, "dotenv_values",
                        lambda ruta: {"SUPABASE_URL": f"https://{despliegue.PROJECT_REF}.supabase.co"})
    monkeypatch.setenv("CONTROLFARMACIAS_SUPABASE_DB_URL", DSN_FICTICIO)

    def ejecutar(salida):
        try:
            despliegue.main(commit, sha, salida)
        except SystemExit:
            pass
        return json.loads(salida.read_text(encoding="utf-8"))

    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    reservas = _reservas(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit)
    assert registro["precondiciones"] == [True] * 9
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "objetos_26": True, "privilegios": True}
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes and _reservas(pg) == reservas

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: ni «26 ausente» ni «funciones de la 15/17» (ya redefinidas); el resto sigue en verde.
    assert registro["precondiciones"] == [False, True, False, True, True, True, True, True, True]
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_26
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_26_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
