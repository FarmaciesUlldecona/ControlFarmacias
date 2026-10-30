"""Hito 2BI: recuperacion de claims huerfanos de normalizacion (migracion 25) en PostgreSQL 17 local.

Plantillas (pg17_local): "24" (estado productivo actual), "25" = 24 + migracion 25 dos veces,
"25_rollback" = 25 + rollback. El claim es el real (RPC de la 16); el proceso «muere» sin persistir ni
registrar el fallo y el lock se envejece mas alla de la gracia (30 min, aprobada por Pio). Sin produccion
ni Farmatic.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import uuid

import pytest

import pg17_local as pgl
from pg17_local import FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, ClientePg17, _lit, base_desde, esquema
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _datos_previos, _huella, contenedor_tcp)
from test_integracion_pg17_2ba import _reservas

pytestmark = pytest.mark.pg17_local

MIGRACION_25 = MIG / "25_cf_claims_huerfanos_normalizacion.sql"
RECUPERAR = "public.cf_recuperar_claim_huerfano_normalizacion(uuid,text,interval)"
HUERFANOS = "public.cf_huerfanos_normalizacion(interval)"
SENALES = "public.cf_senales_claim_huerfano(uuid)"
HUELLA_DOC = {
    "documentos": "select to_jsonb(d) from public.documentos_facturas d",
    "ejecuciones": "select to_jsonb(e) from public.normalizacion_ejecuciones e",
    "historial": "select to_jsonb(h) from public.historial_facturas h",
    "facturas": "select to_jsonb(f) from public.facturas f",
}


@pytest.fixture
def base25(pg17_nueva_base):
    pg = pg17_nueva_base("25")
    # Nada reclamable salvo los documentos de cada test.
    pg.sql("update public.documentos_facturas set estado_lectura = 'NORMALIZADA' "
           "where estado_lectura in ('PENDIENTE', 'ERROR');")
    return pg


def _documento(pg, farmacia="PIO") -> str:
    doc = str(uuid.uuid4())
    pg.sql("insert into public.documentos_facturas(id,farmacia,archivo_nombre,archivo_ruta,archivo_hash,"
           f"fecha_importacion) values ({_lit(doc)},{_lit(farmacia)},'x.pdf','PIO/2BI/{doc}.pdf',"
           f"{_lit(hashlib.sha256(doc.encode()).hexdigest())}, now());")
    return doc


def _claim(pg, worker="w-muere", modo="MANUAL_ONE_SHOT") -> str:
    if modo == "AUTOMATICO":
        pg.sql("update public.cf_configuracion set normalizacion_automatica = true where id;")
        [fila] = pg.json(f"select id from public.cf_reclamar_documento_normalizacion({_lit(worker)}, 300)")
        pg.sql("update public.cf_configuracion set normalizacion_automatica = false where id;")
    else:
        [fila] = pg.json(f"select id from public.cf_reclamar_documento_normalizacion_manual_one_shot({_lit(worker)}, 300)")
    return fila["id"]


def _envejecer(pg, doc, minutos=31) -> None:
    """El proceso murio: su lock (300 s) caduco hace ``minutos``."""
    pg.sql(f"update public.documentos_facturas set bloqueado_hasta = now() - interval '{minutos} minutes' "
           f"where id = {_lit(doc)};")


def _recuperar(pg, doc, gracia="30 minutes", actor="Usuari") -> dict:
    return json.loads(pg.sql(f"set role service_role; select public.cf_recuperar_claim_huerfano_normalizacion("
                             f"{_lit(doc)}, {_lit(actor)}, {_lit(gracia)}::interval)::text;"))


def _estado(pg, doc) -> dict:
    return pg.json("select estado_lectura, estado_persistencia, bloqueado_por, bloqueado_hasta, "
                   "intentos_fallo_normalizacion as intentos, ultima_clase_fallo, ultimo_error_codigo, "
                   "proximo_reintento_at > now() as backoff_futuro, "
                   "round(extract(epoch from proximo_reintento_at - now()) / 3600) as horas "
                   f"from public.documentos_facturas where id = {_lit(doc)}")[0]


def _eventos(pg, doc) -> list[str]:
    return [e["evento"] for e in pg.json(f"select evento from public.historial_facturas "
                                         f"where documento_id = {_lit(doc)} order by id")]


def _huellas(pg) -> dict:
    return {k: _huella(pg, q) for k, q in HUELLA_DOC.items()}


def _vencer_backoff(pg, doc) -> None:
    pg.sql(f"update public.documentos_facturas set proximo_reintento_at = now() - interval '1 second' "
           f"where id = {_lit(doc)};")


# --------------------------------------------------------------------------- esquema y privilegios

def test_rollback_25_devuelve_exactamente_el_esquema_24(pg17_nueva_base):
    assert esquema(pg17_nueva_base("25_rollback")) == esquema(pg17_nueva_base("24"))
    assert esquema(pg17_nueva_base("25")) != esquema(pg17_nueva_base("24"))


def test_25_exige_la_24(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_24_AUSENTE"):
        pg17_nueva_base("23").sql(MIGRACION_25.read_text(encoding="utf-8"))


def test_25_no_altera_datos_existentes(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("24")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    referencia = esquema(pg17_nueva_base("25"))
    pg.sql(MIGRACION_25.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_25.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert esquema(pg) == referencia and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_privilegios_de_la_25(base25):
    pg = base25
    for funcion in (RECUPERAR, HUERFANOS):
        for rol, esperado in (("service_role", "t"), ("anon", "f"), ("authenticated", "f")):
            assert pg.sql(f"select has_function_privilege('{rol}', '{funcion}', 'EXECUTE')") == esperado
        assert pg.sql(f"select prosecdef::text || '|' || pg_get_userbyid(proowner) from pg_proc "
                      f"where oid = '{funcion}'::regprocedure") == "true|postgres"
    for rol in ("service_role", "anon", "authenticated"):
        assert pg.sql(f"select has_function_privilege('{rol}', '{SENALES}', 'EXECUTE')") == "f"
    assert pg.sql("select has_table_privilege('service_role', 'public.documentos_facturas', 'UPDATE')") == "f"


# --------------------------------------------------------------------------- diagnostico (sin la 25)

def test_sin_recuperacion_el_huerfano_queda_bloqueado(base25):
    pg = base25
    doc = _documento(pg)
    assert _claim(pg) == doc
    _envejecer(pg, doc)
    assert (_estado(pg, doc)["estado_lectura"], _eventos(pg, doc)) == ("NORMALIZANDO", ["NORMALIZACION_CLAIM"])
    assert pg.json("select id from public.cf_reclamar_documento_normalizacion_manual_one_shot('otro', 300)") == []


# --------------------------------------------------------------------------- huerfano limpio

@pytest.mark.parametrize("modo", ["MANUAL_ONE_SHOT", "AUTOMATICO"])
def test_huerfano_limpio_cuenta_como_intento_y_vuelve_a_la_cola(base25, modo):
    pg = base25
    doc = _documento(pg)
    _claim(pg, modo=modo)
    _envejecer(pg, doc)
    respuesta = _recuperar(pg, doc)
    assert (respuesta["resultado"], respuesta["estado_lectura"], respuesta["intentos_fallo"]) == (
        "RECUPERADO", "ERROR", 1)
    e = _estado(pg, doc)
    assert (e["estado_lectura"], e["bloqueado_por"], e["bloqueado_hasta"], e["intentos"]) == ("ERROR", None, None, 1)
    assert (e["ultima_clase_fallo"], e["ultimo_error_codigo"], e["backoff_futuro"], e["horas"]) == (
        "TRANSITORIO", "CLAIM_HUERFANO", True, 1)
    [ejecucion] = pg.json("select estado, disparador, worker_id, clase_fallo, error_codigo, idempotency_key "
                          f"from public.normalizacion_ejecuciones where documento_id = {_lit(doc)}")
    assert (ejecucion["estado"], ejecucion["disparador"], ejecucion["worker_id"], ejecucion["clase_fallo"],
            ejecucion["error_codigo"]) == ("ERROR", modo, "w-muere", "TRANSITORIO", "CLAIM_HUERFANO")
    assert ejecucion["idempotency_key"].startswith(f"huerfano:{doc}:")
    assert _eventos(pg, doc) == ["NORMALIZACION_CLAIM", "NORMALIZACION_ERROR", "NORMALIZACION_CLAIM_HUERFANO"]
    [evento] = pg.json("select actor, detalle from public.historial_facturas where evento = "
                       f"'NORMALIZACION_CLAIM_HUERFANO' and documento_id = {_lit(doc)}")
    assert (evento["actor"], evento["detalle"]["worker"], evento["detalle"]["modo_ejecucion"]) == (
        "Usuari", "w-muere", modo)
    # Al vencer el backoff vuelve a ser reclamable.
    _vencer_backoff(pg, doc)
    assert _claim(pg, worker="w-nuevo") == doc


def test_cuarto_huerfano_seguido_pasa_a_revision(base25):
    """R3: el contador y el maximo (4) son los de cf_registrar_fallo_normalizacion."""
    pg = base25
    doc = _documento(pg)
    for intento in range(1, 5):
        assert _claim(pg, worker=f"w-{intento}") == doc
        _envejecer(pg, doc)
        respuesta = _recuperar(pg, doc)
        assert respuesta["resultado"] == "RECUPERADO" and respuesta["intentos_fallo"] == intento
        if intento < 4:
            assert respuesta["estado_lectura"] == "ERROR"
            _vencer_backoff(pg, doc)
    e = _estado(pg, doc)
    assert (e["estado_lectura"], e["intentos"], e["backoff_futuro"]) == ("REVISION", 4, None)
    assert pg.json("select id from public.cf_reclamar_documento_normalizacion_manual_one_shot('otro', 300)") == []


# --------------------------------------------------------------------------- idempotencia y gracia

def test_idempotencia_segunda_llamada_no_escribe(base25):
    pg = base25
    doc = _documento(pg)
    _claim(pg)
    _envejecer(pg, doc)
    assert _recuperar(pg, doc)["resultado"] == "RECUPERADO"
    antes = _huellas(pg)
    respuesta = _recuperar(pg, doc)
    assert (respuesta["resultado"], respuesta["estado_lectura"]) == ("NO_APLICA", "ERROR")
    assert _huellas(pg) == antes


@pytest.mark.parametrize("minutos", [-1, 29])  # lock vigente; caducado dentro de la gracia
def test_lock_vigente_o_dentro_de_la_gracia_no_escribe(base25, minutos):
    pg = base25
    doc = _documento(pg)
    _claim(pg)
    _envejecer(pg, doc, minutos)
    antes = _huellas(pg)
    assert _recuperar(pg, doc)["resultado"] == "LOCK_VIGENTE"
    assert _huellas(pg) == antes


@pytest.mark.parametrize("gracia,error", [("10 minutes", "GRACIA_INSUFICIENTE"), ("30 minutes", "ACTOR_OBLIGATORIO")])
def test_gracia_minima_y_actor_obligatorio(base25, gracia, error):
    pg = base25
    doc = _documento(pg)
    _claim(pg)
    _envejecer(pg, doc)
    with pytest.raises(RuntimeError, match=error):
        _recuperar(pg, doc, gracia=gracia, actor="" if error == "ACTOR_OBLIGATORIO" else "Usuari")


def test_farmacia_no_habilitada(base25):
    pg = base25
    doc = _documento(pg, farmacia="RITA")
    pg.sql(f"update public.documentos_facturas set estado_lectura = 'NORMALIZANDO', bloqueado_por = 'w', "
           f"bloqueado_hasta = now() - interval '1 hour' where id = {_lit(doc)};")
    with pytest.raises(RuntimeError, match="FARMACIA_NO_HABILITADA"):
        _recuperar(pg, doc)


# --------------------------------------------------------------------------- persistencia parcial

def _senal(pg, doc, caso) -> None:
    if caso == "estado_persistencia":
        pg.sql(f"update public.documentos_facturas set estado_persistencia = 'PARCIAL' where id = {_lit(doc)};")
    elif caso == "factura_enlazada":
        [f] = pg.json("select id from public.facturas order by id limit 1")
        pg.sql(f"update public.facturas set documento_id = {_lit(doc)} where id = {_lit(f['id'])};")
    elif caso == "ejecucion_tras_claim":
        pg.sql("insert into public.normalizacion_ejecuciones (documento_id, idempotency_key, intento, disparador, "
               f"estado, iniciado_at) values ({_lit(doc)}, 'otra', 1, 'MANUAL_ONE_SHOT', 'INCOMPLETA', now());")
    else:  # evento_tras_claim
        pg.sql("insert into public.historial_facturas (documento_id, evento, origen, actor, estado_nuevo) "
               f"values ({_lit(doc)}, 'INVENTARIO_MULTIFACTURA', 'RPC', 'w-muere', '{{}}'::jsonb);")


@pytest.mark.parametrize("caso,senal", [
    ("estado_persistencia", "ESTADO_PERSISTENCIA:PARCIAL"),
    ("factura_enlazada", "FACTURAS_ENLAZADAS:1"),
    ("ejecucion_tras_claim", "EJECUCIONES_TRAS_CLAIM:1"),
    ("evento_tras_claim", "EVENTOS_TRAS_CLAIM:1"),
])
def test_persistencia_parcial_pasa_a_revision_sin_tocar_nada_mas(base25, tmp_path, caso, senal):
    pg = base25
    if caso == "factura_enlazada":
        _datos_previos(pg, tmp_path)
        pg.sql("update public.documentos_facturas set estado_lectura = 'NORMALIZADA' "
               "where estado_lectura in ('PENDIENTE', 'ERROR');")
    doc = _documento(pg)
    _claim(pg)
    _envejecer(pg, doc)
    _senal(pg, doc, caso)
    [prevision] = pg.json(f"select prevision, senales from {HUERFANOS.split('(')[0]}('30 minutes')")
    assert (prevision["prevision"], prevision["senales"]) == ("REVISION", [senal])
    facturas = _huella(pg, HUELLA_DOC["facturas"])
    ejecuciones = _huella(pg, HUELLA_DOC["ejecuciones"])
    respuesta = _recuperar(pg, doc)
    assert (respuesta["resultado"], respuesta["senales"]) == ("REVISION", [senal])
    e = _estado(pg, doc)
    assert (e["estado_lectura"], e["bloqueado_por"], e["intentos"]) == ("REVISION", None, 0)
    assert _huella(pg, HUELLA_DOC["facturas"]) == facturas and _huella(pg, HUELLA_DOC["ejecuciones"]) == ejecuciones
    assert _eventos(pg, doc)[-1] == "NORMALIZACION_CLAIM_HUERFANO_REVISION"
    assert pg.json("select id from public.cf_reclamar_documento_normalizacion_manual_one_shot('otro', 300)") == []


# --------------------------------------------------------------------------- worker vivo

def test_worker_vivo_que_persiste_tras_la_recuperacion_falla_sin_escribir(base25):
    pg = base25
    doc = _documento(pg)
    _claim(pg, worker="w-lento")
    _envejecer(pg, doc)
    assert _recuperar(pg, doc)["resultado"] == "RECUPERADO"
    antes = _huellas(pg)
    with pytest.raises(RuntimeError, match="claim no pertenece al worker"):
        pg.sql(f"set role service_role; select public.cf_persistir_normalizacion({_lit(doc)}, 'w-lento', "
               "'MANUAL_ONE_SHOT', 'normalizacion:tarde', 'h', '{\"facturas\": []}'::jsonb);")
    with pytest.raises(RuntimeError, match="claim no pertenece al worker"):
        pg.sql(f"set role service_role; select public.cf_registrar_fallo_normalizacion({_lit(doc)}, 'w-lento', "
               "'MANUAL_ONE_SHOT', 'normalizacion:tarde:fallo', 'X', 'y', 'TRANSITORIO');")
    assert _huellas(pg) == antes


def test_si_el_worker_cierra_antes_la_recuperacion_no_aplica(base25):
    pg = base25
    doc = _documento(pg)
    _claim(pg, worker="w-lento")
    _envejecer(pg, doc)
    pg.sql(f"set role service_role; select public.cf_registrar_fallo_normalizacion({_lit(doc)}, 'w-lento', "
           "'MANUAL_ONE_SHOT', 'normalizacion:propio', 'X', 'y', 'TRANSITORIO');")
    antes = _huellas(pg)
    assert _recuperar(pg, doc)["resultado"] == "NO_APLICA"
    assert _huellas(pg) == antes and _estado(pg, doc)["intentos"] == 1


def test_ctrl_c_tras_el_claim_ya_no_deja_huerfano(base25, tmp_path):
    """Con el worker real y la RPC real de fallos: Ctrl+C registra el fallo (R3) antes de relanzarse."""
    from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
    from src.facturas.runtime_supabase.worker_normalizacion import WorkerNormalizacion

    pg = base25
    doc = _documento(pg)

    def interrumpir(documento):
        raise KeyboardInterrupt

    worker = WorkerNormalizacion(repositorio=RepositorioRuntimeSupabase(ClientePg17(pg, rol_tablas="service_role")),
                                 materializar_pdf=interrumpir, orquestador=None, campos_requeridos=frozenset(),
                                 worker_id="cf-2bi-manual")
    with pytest.raises(KeyboardInterrupt):
        worker.ejecutar_una_manual_one_shot()
    e = _estado(pg, doc)
    assert (e["estado_lectura"], e["bloqueado_por"], e["intentos"], e["ultimo_error_codigo"]) == (
        "ERROR", None, 1, "KeyboardInterrupt")
    [actor] = [x["actor"] for x in pg.json(f"select actor from public.historial_facturas where documento_id = "
                                           f"{_lit(doc)} and evento = 'NORMALIZACION_CLAIM'")]
    assert actor.startswith("cf-2bi-manual#")
    assert pg.json(f"select prevision from public.cf_huerfanos_normalizacion('30 minutes')") == []


# --------------------------------------------------------------------------- script one-shot

class _ClienteRest(ClientePg17):
    """Como PostgREST: una funcion escalar devuelve su valor, no la fila que la envuelve."""

    def __init__(self, pg):
        super().__init__(pg, rol_tablas="service_role")

    def _rpc(self, nombre, payload):
        if nombre == "cf_huerfanos_normalizacion":  # setof: todas las filas
            argumentos = ", ".join(f"{k} => {_lit(v)}" for k, v in payload.items())
            return json.loads(self.pg.sql("set role service_role; select coalesce(json_agg(r),'[]'::json)::text "
                                          f"from public.{nombre}({argumentos}) r;"))
        valor = super()._rpc(nombre, payload)
        return valor[nombre] if isinstance(valor, dict) and set(valor) == {nombre} else valor


def _script(monkeypatch, pg):
    spec = importlib.util.spec_from_file_location(f"recuperar_2bi_{uuid.uuid4().hex[:6]}",
                                                  ROOT / "pruebas/auditoria_2bi/recuperar_huerfanos.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    monkeypatch.setattr(modulo, "obtener_cliente_supabase", lambda: _ClienteRest(pg))
    monkeypatch.setattr(modulo.getpass, "getuser", lambda: "Usuari")
    return modulo


def test_script_informe_sin_escritura_y_recuperar_una_vez(base25, monkeypatch, tmp_path):
    pg = base25
    doc = _documento(pg)
    _claim(pg)
    _envejecer(pg, doc)
    script = _script(monkeypatch, pg)
    antes = _huellas(pg)
    assert script.main("informe", [], tmp_path / "informe.json") == 0
    assert _huellas(pg) == antes
    [h] = json.loads((tmp_path / "informe.json").read_text(encoding="utf-8"))["huerfanos"]
    assert (h["documento_id"], h["prevision"], h["senales"]) == (doc, "RECUPERABLE", [])

    assert script.main("recuperar", [doc], tmp_path / "recuperar.json") == 0
    registro = json.loads((tmp_path / "recuperar.json").read_text(encoding="utf-8"))
    assert registro["resultado"] == "RECUPERADO" and (tmp_path / f"recuperar_huerfano_{doc}.guard").exists()
    assert _estado(pg, doc)["estado_lectura"] == "ERROR"
    antes = _huellas(pg)
    with pytest.raises(SystemExit, match="GUARD_EXISTENTE"):
        script.main("recuperar", [doc], tmp_path / "otra.json")
    assert _huellas(pg) == antes


def test_script_no_recupera_un_lock_vigente_ni_con_configuracion_inesperada(base25, monkeypatch, tmp_path):
    pg = base25
    doc = _documento(pg)
    _claim(pg)
    script = _script(monkeypatch, pg)
    antes = _huellas(pg)
    with pytest.raises(SystemExit, match="NO_ES_CANDIDATO"):
        script.main("recuperar", [doc], tmp_path / "vigente.json")
    assert not (tmp_path / f"recuperar_huerfano_{doc}.guard").exists() and _huellas(pg) == antes
    _envejecer(pg, doc)
    antes = _huellas(pg)
    pg.sql("update public.cf_configuracion set normalizacion_automatica = true where id;")
    with pytest.raises(SystemExit, match="CONFIGURACION_INESPERADA"):
        script.main("recuperar", [doc], tmp_path / "config.json")
    pg.sql("update public.cf_configuracion set normalizacion_automatica = false where id;")
    assert _huellas(pg) == antes


# --------------------------------------------------------------------------- despliegue

SCRIPT_25 = ROOT / "pruebas/auditoria_2bi/desplegar_25.py"
RUTA_25 = "sql/migrations/25_cf_claims_huerfanos_normalizacion.sql"


def _cargar_despliegue(script=SCRIPT_25):
    spec = importlib.util.spec_from_file_location(f"desplegar_25_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_sql_de_precondiciones_25_es_de_solo_lectura(base25, pg17_nueva_base):
    sql = _cargar_despliegue().PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert ast.parse(SCRIPT_25.read_text(encoding="utf-8"))
    assert pg17_nueva_base("24").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 9)
    assert base25.sql("begin read only; " + sql + "; rollback;").split("|")[0] == "f"


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf2bi_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    """Copia byte a byte el script y la migracion a un repositorio git temporal con su commit: el ensayo
    verifica el SHA contra un commit real sin depender de que la 25 este ya commiteada aqui."""
    for relativa in (RUTA_25, "pruebas/auditoria_2bi/desplegar_25.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 25"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_25.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_2bi/desplegar_25.py")


def test_ensayo_completo_despliegue_25_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "24"))
    _datos_previos(pg, tmp_path)
    referencia = base_desde(nombre, pg.db)
    referencia.sql(MIGRACION_25.read_text(encoding="utf-8"))
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
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "rpc_25": True, "privilegios": True}
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes and _reservas(pg) == reservas

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    assert registro["precondiciones"][0] is False and all(registro["precondiciones"][1:])
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_25
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_25_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
