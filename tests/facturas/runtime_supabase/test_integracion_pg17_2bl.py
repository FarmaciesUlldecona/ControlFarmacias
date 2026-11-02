"""Hito 2BL: migracion 27 (un fallo registrado no bloquea el reintento de la persistencia) en PostgreSQL 17 local.

Plantillas (pg17_local): "26" (estado productivo), "27" = 26 + migracion 27 dos veces, "27_rollback" = 27 +
rollback. Caso de produccion (serie 2BJ, Alliance de la posicion 57): la persistencia cae (statement_timeout),
el worker registra el fallo con la clave de la persistencia y el reintento, con el mismo PDF y la misma clave,
no podia guardar nunca. Payload real del PDF Alliance del 2AP (captura del 2BK). Sin produccion ni Farmatic.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
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
from test_integracion_pg17_2bk import (
    DOC_A, ESCENARIOS, MULTI, _base, _canonico, _captura, _claim, _documento, _intento, _numerado, _persistir,
    _volcado)
from src.facturas.runtime_supabase.clasificacion_fallos import TRANSITORIO, clasificar_fallo
from src.facturas.runtime_supabase.compositor_manual import construir_worker_manual_productivo
from src.facturas.runtime_supabase.modelos import ConfiguracionRuntime

pytestmark = pytest.mark.pg17_local

MIGRACION_27 = MIG / "27_cf_reintento_tras_fallo_de_persistencia.sql"
ROLLBACK_27 = MIG / "27_cf_reintento_tras_fallo_de_persistencia.rollback.sql"
RUTA_27 = "sql/migrations/27_cf_reintento_tras_fallo_de_persistencia.sql"
SCRIPT_27 = ROOT / "pruebas/auditoria_2bl/desplegar_27.py"
TIMEOUT = "{'message': 'canceling statement due to statement timeout', 'code': '57014', 'hint': None, 'details': None}"


class APIError(Exception):
    """Mismo nombre de clase que el error de postgrest (``error_codigo`` del fallo)."""


def _fallo(pg, doc, worker, clave):
    """Lo que registro el worker en produccion tras el timeout: el fallo con la clave de la persistencia."""
    return pg.sql(f"select public.cf_registrar_fallo_normalizacion({_lit(doc)}::uuid, {_lit(worker)}, "
                  f"'MANUAL_ONE_SHOT', {_lit(clave)}, 'APIError', {_lit(TIMEOUT)}, "
                  f"{_lit(clasificar_fallo('APIError', TIMEOUT))});")


def _vence_backoff(pg, doc):
    pg.sql(f"update public.documentos_facturas set proximo_reintento_at = now() - interval '1 second' "
           f"where id = {_lit(doc)};")


def _estado(pg, doc):
    [fila] = pg.json("select estado_lectura, estado_persistencia, intentos_fallo_normalizacion as intentos, "
                     "ultima_clase_fallo, (select count(*) from public.facturas f where f.documento_id = d.id) "
                     f"as facturas from public.documentos_facturas d where id = {_lit(doc)}")
    return fila


def _ejecuciones(pg, doc):
    return pg.json("select intento, idempotency_key as clave, estado, clase_fallo, error_detalle "
                   f"from public.normalizacion_ejecuciones where documento_id = {_lit(doc)} order by intento")


def _un_documento(pg, captura, worker, clave, *, extra=None):
    factura = dict(captura["p_resultado"]["facturas"][0], factura_id="k-unica")
    resultado = dict(captura["p_resultado"], facturas=[factura], **(extra or {}))
    return _ClienteServiceRole(pg)._rpc("cf_persistir_normalizacion", {
        "p_documento_id": DOC_A, "p_worker_id": worker, "p_disparador": "MANUAL_ONE_SHOT",
        "p_idempotency_key": clave, "p_resultado_hash": captura["p_resultado_hash"],
        "p_resultado": {"resultado_json": resultado, "uso_luna": False}})


def _solo_replay(antes, despues):
    """Un replay no cambia nada salvo anadir eventos NORMALIZACION_REPLAY_IDEMPOTENTE al historial."""
    assert {t: v for t, v in despues.items() if t != "historial_facturas"} == \
        {t: v for t, v in antes.items() if t != "historial_facturas"}
    nuevas = [json.loads(f)["fila"]["evento"] for f in despues["historial_facturas"]
              if f not in antes["historial_facturas"]]
    assert nuevas and set(nuevas) == {"NORMALIZACION_REPLAY_IDEMPOTENTE"}
    assert set(antes["historial_facturas"]) <= set(despues["historial_facturas"])
    return despues


# --------------------------------------------------------------------------- caso de produccion

def test_clasificacion_del_fallo_no_es_defecto_documental():
    assert clasificar_fallo("APIError", TIMEOUT) == TRANSITORIO
    assert clasificar_fallo("APIError", "{'message': 'IDEMPOTENCIA_PAYLOAD_DISTINTO', 'code': 'P0001'}") == TRANSITORIO


@pytest.mark.parametrize("variante", ["26", "27"])
def test_multifactura_fallo_transitorio_y_reintento(pg17_nueva_base, tmp_path, variante):
    captura = _captura(pg17_nueva_base, tmp_path)
    pg = _base(pg17_nueva_base, variante)
    _documento(pg, DOC_A)
    _claim(pg, "w-1")
    _fallo(pg, DOC_A, "w-1", "k-a")
    assert _estado(pg, DOC_A)["estado_lectura"] == "ERROR"
    _vence_backoff(pg, DOC_A)
    _claim(pg, "w-2")
    paso = _intento(_persistir, pg, DOC_A, "w-2", "k-a", captura)
    if variante == "26":
        # El defecto de produccion: el fallo registrado se toma por una repeticion.
        assert paso == ("ERROR", "IDEMPOTENCIA_PAYLOAD_DISTINTO")
        return
    assert paso[0] == "OK"
    assert _estado(pg, DOC_A) == {"estado_lectura": "NORMALIZADA", "estado_persistencia": "COMPLETA",
                                  "intentos": 0, "ultima_clase_fallo": None, "facturas": 3}
    assert [(e["intento"], e["clave"], e["estado"]) for e in _ejecuciones(pg, DOC_A)] == [
        (1, "k-a", "ERROR"), (2, "k-a:intento:2", "COMPLETADA")]
    inventario = pg.json(f"select inventario_facturas from public.documentos_facturas where id = {_lit(DOC_A)}")[0][
        "inventario_facturas"]
    assert sorted(i["estado"] for i in inventario) == ["PERSISTIDAS"] * 3

    # Replay con la misma solicitud: la misma ejecucion; solo el evento de replay de siempre.
    antes = _volcado(pg)
    assert _intento(_persistir, pg, DOC_A, "w-2", "k-a", captura) == ("OK", paso[1])
    antes = _solo_replay(antes, _volcado(pg))
    # Misma clave con otra solicitud: rechazo, como hoy.
    otro = dict(captura["p_resultado"], extra_2bl=1)
    assert _intento(_persistir, pg, DOC_A, "w-2", "k-a", captura, resultado=otro) == \
        ("ERROR", "IDEMPOTENCIA_PAYLOAD_DISTINTO")
    assert _volcado(pg) == antes


@pytest.mark.parametrize("variante", ["26", "27"])
def test_un_documento_fallo_transitorio_y_reintento(pg17_nueva_base, tmp_path, variante):
    captura = _captura(pg17_nueva_base, tmp_path)
    pg = _base(pg17_nueva_base, variante)
    _documento(pg, DOC_A)
    _claim(pg, "w-1")
    fallo = _fallo(pg, DOC_A, "w-1", "k-a")
    _vence_backoff(pg, DOC_A)
    _claim(pg, "w-2")
    paso = _intento(_un_documento, pg, captura, "w-2", "k-a")
    if variante == "26":
        # El defecto de produccion: devuelve la ejecucion del fallo y no persiste nada.
        assert paso == ("OK", fallo) and _estado(pg, DOC_A)["facturas"] == 0
        return
    assert paso[0] == "OK" and paso[1] != fallo
    estado = _estado(pg, DOC_A)
    assert (estado["estado_lectura"], estado["facturas"]) == ("NORMALIZADA", 1)
    assert [(e["intento"], e["clave"], e["estado"]) for e in _ejecuciones(pg, DOC_A)] == [
        (1, "k-a", "ERROR"), (2, "k-a:intento:2", "COMPLETADA")]
    # Replay (tambien con otro payload, como hoy en la RPC de un documento): la misma ejecucion; solo los
    # eventos de replay de siempre.
    antes = _volcado(pg)
    assert _intento(_un_documento, pg, captura, "w-2", "k-a") == ("OK", paso[1])
    assert _intento(_un_documento, pg, captura, "w-2", "k-a", extra={"extra_2bl": 1}) == ("OK", paso[1])
    _solo_replay(antes, _volcado(pg))


class _ClienteQueCaeUnaVez(_ClienteServiceRole):
    """La primera llamada a la RPC multifactura cae como en produccion (statement_timeout, nada escrito)."""

    def __init__(self, pg):
        super().__init__(pg)
        self.caidas = 0

    def _rpc(self, nombre, payload):
        if nombre == MULTI and not self.caidas:
            self.caidas += 1
            raise APIError(TIMEOUT)
        return super()._rpc(nombre, payload)


@pytest.mark.parametrize("variante", ["26", "27"])
def test_worker_real_reintenta_y_guarda_tras_el_timeout(pg17_nueva_base, tmp_path, variante):
    """Camino completo de produccion con el worker manual real: timeout, fallo registrado, reintento."""
    pg = _base(pg17_nueva_base, variante)
    cliente = _ClienteQueCaeUnaVez(pg)
    pdf = pgl.ALLIANCE.read_bytes()
    _documento(pg, DOC_A, sha=hashlib.sha256(pdf).hexdigest())
    cliente.objetos[("facturas-pdf", f"PIO/2BK/{DOC_A}.pdf")] = pdf

    def ejecutar(n):
        return construir_worker_manual_productivo(
            cliente, ConfiguracionRuntime(), f"w-2bl-{n}", tmp_path / f"w{n}").ejecutar_una_manual()

    # documentos_reclamados cuenta los procesados con exito (en la tanda 6 de produccion: 0 tras el fallo).
    assert ejecutar(1).documentos_reclamados == 0 and cliente.caidas == 1
    primera = _ejecuciones(pg, DOC_A)
    assert [(e["intento"], e["estado"], e["clase_fallo"]) for e in primera] == [(1, "ERROR", TRANSITORIO)]
    clave = primera[0]["clave"]
    assert clave.startswith(f"normalizacion:{DOC_A}:MANUAL_ONE_SHOT:") and not clave.endswith(":fallo")

    _vence_backoff(pg, DOC_A)
    assert ejecutar(2).documentos_reclamados == (1 if variante == "27" else 0)
    ejecuciones = [(e["intento"], e["clave"], e["estado"], e["clase_fallo"]) for e in _ejecuciones(pg, DOC_A)]
    if variante == "26":
        # El defecto de produccion (ya clasificado como transitorio, no como defecto documental).
        assert ejecuciones[1][2:] == ("ERROR", TRANSITORIO)
        assert "IDEMPOTENCIA_PAYLOAD_DISTINTO" in _ejecuciones(pg, DOC_A)[1]["error_detalle"]
        assert _estado(pg, DOC_A)["facturas"] == 0
        return
    assert ejecuciones == [(1, clave, "ERROR", TRANSITORIO), (2, f"{clave}:intento:2", "COMPLETADA", None)]
    assert _estado(pg, DOC_A) == {"estado_lectura": "NORMALIZADA", "estado_persistencia": "COMPLETA",
                                  "intentos": 0, "ultima_clase_fallo": None, "facturas": 3}


@pytest.mark.parametrize("escenario", sorted(ESCENARIOS))
def test_sin_fallo_previo_27_da_el_mismo_resultado_que_la_26(pg17_nueva_base, tmp_path, escenario):
    """Los escenarios de equivalencia del 2BK (nuevo, duplicado, replay, relectura, ...) no cambian."""
    captura = _captura(pg17_nueva_base, tmp_path)
    estados = {}
    for variante in ("26", "27"):
        pg = _base(pg17_nueva_base, variante)
        pasos = ESCENARIOS[escenario](pg, captura)
        estados[variante] = _numerado({"pasos": _canonico(pasos), "volcado": _volcado(pg)})
    assert estados["27"] == estados["26"]


# --------------------------------------------------------------------------- migracion

def test_generador_reproduce_la_27_y_su_rollback():
    spec = importlib.util.spec_from_file_location("generar_27", ROOT / "pruebas/auditoria_2bl/generar_migracion_27.py")
    generador = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generador)
    assert generador.migracion() == MIGRACION_27.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert generador.rollback() == ROLLBACK_27.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_rollback_27_devuelve_exactamente_el_esquema_26(pg17_nueva_base):
    assert esquema(pg17_nueva_base("27_rollback")) == esquema(pg17_nueva_base("26"))
    assert esquema(pg17_nueva_base("27")) != esquema(pg17_nueva_base("26"))


def test_27_exige_la_26(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_26_AUSENTE"):
        pg17_nueva_base("25").sql(MIGRACION_27.read_text(encoding="utf-8"))


def test_27_no_altera_datos_existentes(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("26")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    ejecuciones = pg.sql("select md5(string_agg(md5(to_jsonb(e)::text), '' order by e.id)) "
                         "from public.normalizacion_ejecuciones e")
    referencia = esquema(pg17_nueva_base("27"))
    pg.sql(MIGRACION_27.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_27.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql("select md5(string_agg(md5(to_jsonb(e)::text), '' order by e.id)) "
                  "from public.normalizacion_ejecuciones e") == ejecuciones
    assert esquema(pg) == referencia and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_privilegios_de_la_27(pg17_nueva_base):
    pg = pg17_nueva_base("27")
    rpc = ("public.cf_persistir_normalizacion(uuid,text,text,text,text,jsonb)",
           "public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)")
    internas = ("public.cf_ejecucion_persistida(uuid,text)",
                "public.cf_persistir_normalizacion_nucleo(uuid,text,text,text,text,jsonb,jsonb)",
                "public.cf_persistir_documento_multifactura_nucleo(uuid,text,text,text,jsonb,text[],text)",
                "public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[])")
    for funcion in rpc + internas:
        for rol in ("service_role", "anon", "authenticated"):
            esperado = "t" if funcion in rpc and rol == "service_role" else "f"
            assert pg.sql(f"select has_function_privilege('{rol}', '{funcion}', 'EXECUTE')") == esperado, (funcion, rol)
        assert pg.sql(f"select prosecdef::text || '|' || pg_get_userbyid(proowner) from pg_proc "
                      f"where oid = '{funcion}'::regprocedure") == "true|postgres"


# --------------------------------------------------------------------------- despliegue

def _cargar_despliegue(script=SCRIPT_27):
    spec = importlib.util.spec_from_file_location(f"desplegar_27_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_sql_de_precondiciones_27_es_de_solo_lectura(pg17_nueva_base):
    sql = _cargar_despliegue().PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert pg17_nueva_base("26").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 9)
    assert pg17_nueva_base("27").sql("begin read only; " + sql + "; rollback;").split("|")[0] == "f"


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf2bl_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    """Copia byte a byte el script y la migracion a un repositorio git temporal con su commit."""
    for relativa in (RUTA_27, "pruebas/auditoria_2bl/desplegar_27.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 27"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_27.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_2bl/desplegar_27.py")


def test_ensayo_completo_despliegue_27_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "26"))
    _datos_previos(pg, tmp_path)
    referencia = base_desde(nombre, pg.db)
    referencia.sql(MIGRACION_27.read_text(encoding="utf-8"))
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
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "objetos_27": True, "privilegios": True}
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes and _reservas(pg) == reservas

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: ni «27 ausente» ni «funciones de la 26» (ya redefinidas); el resto sigue en verde.
    assert registro["precondiciones"] == [False, True, False, True, True, True, True, True, True]
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_27
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_27_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
