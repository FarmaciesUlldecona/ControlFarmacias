"""Migracion 37 (DECISIONES DE PIO D1-D7, 2026-11-18/19): defectos de extraccion directos a REVISION, en PostgreSQL 17.

Plantillas (pg17_local): "36" (estado productivo), "37" = 36 + migracion 37 dos veces, "37_rollback" = 37 + rollback.
Se comprueba:
- rollback exacto al esquema 36; la 37 exige la 36; idempotente; ningun dato cambia; privilegios de la firma nueva
  (mismos beneficiarios que la de 7 parametros, nada para anon ni authenticated); deteccion READ_ONLY;
- con la 37: defecto de extraccion o de identidad de farmacia -> REVISION al primer intento, con lector y la regla en el
  historial; almacenamiento y transitorio -> ERROR con espera y REVISION al 4.o; NO_SOPORTADO sin intento; huerfano
  limpio (25) igual; la firma de 7 parametros tambien aplica la regla (lector null); lector no valido -> nada escrito;
  reprocesado tras el defecto -> PENDIENTE con 0 intentos; rollback con un documento ya en REVISION -> se queda;
- sin la 37 (plantilla 36) el codigo detecta su ausencia y sigue la regla de la 17;
- worker manual real con un PDF ilegible: EXTRACCION_LOCAL_ERROR, REVISION y lector alliance-local 1.3.2;
- desplegar_37.py ensayado con el rol que imita al postgres de Supabase (norma 2BN-D), segundo intento revertido y
  rollback con la imitacion.
Sin produccion ni Farmatic.
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
from test_ensayo_fase4_2at import _ConexionPg17
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _datos_previos, _huella, contenedor_tcp)
from test_integracion_pg17_2bi import _claim, _documento, _envejecer, _estado, _eventos, _recuperar, _vencer_backoff
from test_integracion_pg17_35_pagos import _sin_propietario
from src.facturas.runtime_supabase.compositor_manual import construir_worker_manual_productivo
from src.facturas.runtime_supabase.lectura_readonly import LectorReadOnly, defectos_37_en_bd
from src.facturas.runtime_supabase.modelos import ConfiguracionRuntime, DocumentoTrabajo
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase

pytestmark = pytest.mark.pg17_local

MIGRACION_37 = MIG / "37_cf_defectos_directos_a_revision.sql"
ROLLBACK_37 = MIG / "37_cf_defectos_directos_a_revision.rollback.sql"
RUTA_37 = "sql/migrations/37_cf_defectos_directos_a_revision.sql"
SCRIPT_37 = ROOT / "pruebas/auditoria_37/desplegar_37.py"
FIRMA_8 = "public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text,jsonb)"
FIRMA_7 = "public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text)"
LECTOR = {"adaptador": "alliance-local", "version_adaptador": "1.3.2", "layout": None}
HUELLA_37 = {
    **CONSULTAS_HUELLA,
    "documentos": "select to_jsonb(d) from public.documentos_facturas d",
    "ejecuciones": "select to_jsonb(e) - 'lector' from public.normalizacion_ejecuciones e",
}


def _cargar_despliegue(script=SCRIPT_37):
    spec = importlib.util.spec_from_file_location(f"desplegar_37_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar_despliegue()


def _lector(pg) -> LectorReadOnly:
    return LectorReadOnly(_ConexionPg17(pg, []).cursor())


def _limpia(pg):
    """Nada reclamable salvo los documentos de cada test."""
    pg.sql("update public.documentos_facturas set estado_lectura = 'NORMALIZADA' "
           "where estado_lectura in ('PENDIENTE', 'ERROR');")
    return pg


@pytest.fixture
def base37(pg17_nueva_base):
    return _limpia(pg17_nueva_base("37"))


def _repositorio(pg, detectar=True):
    deteccion = (lambda: defectos_37_en_bd(_lector(pg))) if detectar else None
    return RepositorioRuntimeSupabase(pgl.ClientePg17(pg), defectos_37=deteccion)


def _fallar(pg, doc, worker, detalle, *, codigo="DocumentoNoAptoManual", lector=LECTOR, detectar=True):
    documento = DocumentoTrabajo(documento_id=doc, archivo_ruta=f"PIO/2BI/{doc}.pdf", archivo_nombre="x.pdf",
                                 farmacia="PIO")
    _repositorio(pg, detectar).fallar_ejecucion(documento, codigo, detalle, worker, "MANUAL_ONE_SHOT",
                                                f"normalizacion:{doc}:MANUAL_ONE_SHOT:fallo", lector=lector)


def _ejecuciones(pg, doc) -> list[dict]:
    return pg.json("select intento, estado, clase_fallo, error_detalle, lector from public.normalizacion_ejecuciones "
                   f"where documento_id = {_lit(doc)} order by intento")


def _ultimo_error(pg, doc) -> dict:
    return pg.json("select estado_nuevo, detalle from public.historial_facturas where evento = 'NORMALIZACION_ERROR' "
                   f"and documento_id = {_lit(doc)} order by id desc limit 1")[0]


# --------------------------------------------------------------------------- esquema, datos y privilegios

def test_rollback_37_devuelve_exactamente_el_esquema_36(pg17_nueva_base):
    assert esquema(pg17_nueva_base("37_rollback")) == esquema(pg17_nueva_base("36"))
    assert esquema(pg17_nueva_base("37")) != esquema(pg17_nueva_base("36"))


def test_37_exige_la_36(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_36_AUSENTE"):
        pg17_nueva_base("35").sql(MIGRACION_37.read_text(encoding="utf-8"))


def test_37_no_altera_datos_y_es_idempotente(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("36")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in HUELLA_37.items()}
    config = _huella(pg, "select to_jsonb(c) from public.cf_configuracion c")
    acl_7 = pg.sql(f"select coalesce(proacl::text, '') || pg_get_userbyid(proowner) from pg_proc "
                   f"where oid = '{FIRMA_7}'::regprocedure")
    pg.sql(MIGRACION_37.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_37.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in HUELLA_37.items()} == antes
    assert _huella(pg, "select to_jsonb(c) from public.cf_configuracion c") == config
    assert pg.sql("select count(*) from public.normalizacion_ejecuciones where lector is not null") == "0"
    assert pg.sql(f"select coalesce(proacl::text, '') || pg_get_userbyid(proowner) from pg_proc "
                  f"where oid = '{FIRMA_7}'::regprocedure") == acl_7
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert esquema(pg) == esquema(pg17_nueva_base("37"))


def test_privilegios_de_la_firma_nueva(pg17_nueva_base):
    pg = pg17_nueva_base("37")
    for rol in ("anon", "authenticated"):
        assert pg.sql(f"select has_function_privilege('{rol}', '{FIRMA_8}', 'EXECUTE')") == "f"
    beneficiarios_8 = pg.sql(f"select {DESPLIEGUE._beneficiarios(FIRMA_8)}")
    assert beneficiarios_8 and beneficiarios_8 == pg.sql(f"select {DESPLIEGUE._beneficiarios(FIRMA_7)}")
    assert "," not in beneficiarios_8  # un unico beneficiario ademas del propietario
    assert pg.sql(f"select prosecdef::text || '|' || pg_get_userbyid(proowner) from pg_proc "
                  f"where oid = '{FIRMA_8}'::regprocedure") == "true|postgres"


def test_deteccion_de_la_37_sin_abortar_la_lectura(pg17_nueva_base):
    assert defectos_37_en_bd(_lector(pg17_nueva_base("36"))) is False
    assert defectos_37_en_bd(_lector(pg17_nueva_base("37"))) is True
    assert defectos_37_en_bd(_lector(pg17_nueva_base("37_rollback"))) is False


# --------------------------------------------------------------------------- regla nueva (con la 37)

@pytest.mark.parametrize("codigo, detalle", [
    ("DocumentoNoAptoManual", "EXTRACCION_LOCAL_ERROR"),
    ("DocumentoNoAptoManual", "DOCUMENTO_INCOMPLETO"),
    ("ValueError", "NINGUNA_FACTURA_AUTORIZABLE_AUTOMATICAMENTE"),
    ("DocumentoNoAptoManual", "FARMACIA_DOCUMENTO_CONTRADICTORIA"),
    ("ErrorFarmaciaDocumental", "texto"),
    ("ErrorCompletitudDocumental", "texto"),
])
def test_defecto_pasa_a_revision_al_primer_intento_con_lector(base37, codigo, detalle):
    pg = base37
    doc = _documento(pg)
    _claim(pg, worker="w37#1")
    _fallar(pg, doc, "w37#1", detalle, codigo=codigo)
    e = _estado(pg, doc)
    assert (e["estado_lectura"], e["intentos"], e["ultima_clase_fallo"], e["backoff_futuro"], e["bloqueado_por"]) == (
        "REVISION", 1, "DEFECTO_DOCUMENTO", None, None)
    [ejecucion] = _ejecuciones(pg, doc)
    assert (ejecucion["estado"], ejecucion["clase_fallo"], ejecucion["lector"]) == ("ERROR", "DEFECTO_DOCUMENTO", LECTOR)
    error = _ultimo_error(pg, doc)
    assert error["estado_nuevo"] == {"estado_lectura": "REVISION", "proximo_reintento_at": None}
    assert (error["detalle"]["regla"], error["detalle"]["intentos_fallo"]) == ("DEFECTO_DIRECTO_A_REVISION", 1)
    assert pg.json("select id from public.cf_reclamar_documento_normalizacion_manual_one_shot('otro', 300)") == []


@pytest.mark.parametrize("detalle", ["SHA256_NO_COINCIDE", "OBJETO_STORAGE_VACIO", "timeout de red"])
def test_almacenamiento_y_transitorio_reintentan_y_revision_al_cuarto(base37, detalle):
    pg = base37
    doc = _documento(pg)
    for intento in (1, 2, 3, 4):
        assert _claim(pg, worker=f"w37#{intento}") == doc
        _fallar(pg, doc, f"w37#{intento}", detalle, codigo="RuntimeError")
        e = _estado(pg, doc)
        assert (e["intentos"], e["ultima_clase_fallo"]) == (intento, "TRANSITORIO")
        if intento < 4:
            assert (e["estado_lectura"], e["backoff_futuro"]) == ("ERROR", True)
            _vencer_backoff(pg, doc)
        else:
            assert (e["estado_lectura"], e["backoff_futuro"]) == ("REVISION", None)
        assert "regla" not in _ultimo_error(pg, doc)["detalle"]
    assert [x["lector"] for x in _ejecuciones(pg, doc)] == [LECTOR] * 4


def test_no_soportado_sin_intento(base37):
    pg = base37
    doc = _documento(pg)
    _claim(pg, worker="w37#1")
    _fallar(pg, doc, "w37#1", "PROVEEDOR_NO_SOPORTADO_AUTOMATICO")
    e = _estado(pg, doc)
    assert (e["estado_lectura"], e["intentos"], e["ultima_clase_fallo"]) == ("PROVEEDOR_NO_SOPORTADO", 0, "NO_SOPORTADO")


def test_la_firma_de_7_parametros_tambien_aplica_la_regla_sin_lector(base37):
    pg = base37
    doc = _documento(pg)
    _claim(pg, worker="w37#1")
    _fallar(pg, doc, "w37#1", "EXTRACCION_LOCAL_ERROR", detectar=False)
    assert (_estado(pg, doc)["estado_lectura"], _ejecuciones(pg, doc)[0]["lector"]) == ("REVISION", None)
    assert _ultimo_error(pg, doc)["detalle"]["regla"] == "DEFECTO_DIRECTO_A_REVISION"


def test_huerfano_limpio_sigue_igual_con_la_37(base37):
    pg = base37
    doc = _documento(pg)
    _claim(pg)
    _envejecer(pg, doc)
    respuesta = _recuperar(pg, doc)
    assert (respuesta["resultado"], respuesta["estado_lectura"], respuesta["intentos_fallo"]) == (
        "RECUPERADO", "ERROR", 1)
    e = _estado(pg, doc)
    assert (e["ultima_clase_fallo"], e["ultimo_error_codigo"], e["backoff_futuro"]) == (
        "TRANSITORIO", "CLAIM_HUERFANO", True)
    assert _ejecuciones(pg, doc)[0]["lector"] is None


def test_lector_no_valido_no_escribe_nada(base37):
    pg = base37
    doc = _documento(pg)
    _claim(pg, worker="w37#1")
    # Directo a la RPC: el repositorio ya exige un diccionario; aqui se prueba la barrera de la BD.
    with pytest.raises(RuntimeError, match="LECTOR_NO_VALIDO"):
        pgl.ClientePg17(pg).rpc("cf_registrar_fallo_normalizacion", {
            "p_documento_id": doc, "p_worker_id": "w37#1", "p_disparador": "MANUAL_ONE_SHOT",
            "p_idempotency_key": "k", "p_error_codigo": "DocumentoNoAptoManual",
            "p_error_detalle": "EXTRACCION_LOCAL_ERROR", "p_clase_fallo": "DEFECTO_DOCUMENTO",
            "p_lector": ["no", "es", "objeto"]}).execute()
    assert _ejecuciones(pg, doc) == []
    assert (_estado(pg, doc)["estado_lectura"], _eventos(pg, doc)) == ("NORMALIZANDO", ["NORMALIZACION_CLAIM"])


def test_reprocesado_tras_el_defecto_vuelve_a_pendiente(base37):
    pg = base37
    doc = _documento(pg)
    _claim(pg, worker="w37#1")
    _fallar(pg, doc, "w37#1", "EXTRACCION_LOCAL_ERROR")
    pg.sql(f"select public.cf_solicitar_reprocesado({_lit(doc)}, 'Pio');")
    e = _estado(pg, doc)
    assert (e["estado_lectura"], e["intentos"], e["ultima_clase_fallo"], e["backoff_futuro"]) == (
        "PENDIENTE", 0, None, None)
    assert _claim(pg, worker="w37#2") == doc


def test_rollback_con_un_documento_ya_en_revision_lo_deja_ahi(base37):
    pg = base37
    doc = _documento(pg)
    _claim(pg, worker="w37#1")
    _fallar(pg, doc, "w37#1", "EXTRACCION_LOCAL_ERROR")
    fila = _huella(pg, f"select to_jsonb(d) from public.documentos_facturas d where id = {_lit(doc)}")
    pg.sql(ROLLBACK_37.read_text(encoding="utf-8"))
    assert _huella(pg, f"select to_jsonb(d) from public.documentos_facturas d where id = {_lit(doc)}") == fila
    assert [x["estado"] for x in pg.json("select estado from public.normalizacion_ejecuciones "
                                         f"where documento_id = {_lit(doc)}")] == ["ERROR"]
    assert defectos_37_en_bd(_lector(pg)) is False
    # Tras el rollback vuelve la regla de la 17.
    otro = _documento(pg)
    _claim(pg, worker="w37#2")
    _fallar(pg, otro, "w37#2", "EXTRACCION_LOCAL_ERROR")
    assert (_estado(pg, otro)["estado_lectura"], _estado(pg, otro)["intentos"]) == ("ERROR", 1)


# --------------------------------------------------------------------------- sin la 37: regla de la 17

def test_sin_la_37_el_codigo_sigue_la_regla_de_la_17(pg17_nueva_base):
    pg = _limpia(pg17_nueva_base("36"))
    doc = _documento(pg)
    _claim(pg, worker="w36#1")
    cliente = pgl.ClientePg17(pg)
    RepositorioRuntimeSupabase(cliente, defectos_37=lambda: defectos_37_en_bd(_lector(pg))).fallar_ejecucion(
        DocumentoTrabajo(doc, f"PIO/2BI/{doc}.pdf", "x.pdf", "PIO"), "DocumentoNoAptoManual",
        "EXTRACCION_LOCAL_ERROR", "w36#1", "MANUAL_ONE_SHOT", "k", lector=LECTOR)
    [(_, payload)] = cliente.rpcs
    assert "p_lector" not in payload
    e = _estado(pg, doc)
    assert (e["estado_lectura"], e["intentos"], e["ultima_clase_fallo"], e["backoff_futuro"]) == (
        "ERROR", 1, "DEFECTO_DOCUMENTO", True)


# --------------------------------------------------------------------------- worker manual real

@pytest.mark.parametrize("plantilla, estado", [("37", "REVISION"), ("36", "ERROR")])
def test_worker_real_con_un_pdf_ilegible(pg17_nueva_base, tmp_path, plantilla, estado):
    pg = _limpia(pg17_nueva_base(plantilla))
    cliente = pgl.ClientePg17(pg)
    doc = pgl._registrar(pg, cliente, b"esto no es un pdf", 1)
    worker = construir_worker_manual_productivo(cliente, ConfiguracionRuntime(), "manual-37", tmp_path / "w",
                                                defectos_37=lambda: defectos_37_en_bd(_lector(pg)))
    worker.ejecutar_una_manual()
    e = _estado(pg, doc)
    assert (e["estado_lectura"], e["intentos"], e["ultima_clase_fallo"]) == (estado, 1, "DEFECTO_DOCUMENTO")
    columnas = "error_codigo, error_detalle" + (", lector" if plantilla == "37" else "")
    [ejecucion] = pg.json(f"select {columnas} from public.normalizacion_ejecuciones where documento_id = {_lit(doc)}")
    assert (ejecucion["error_codigo"], ejecucion["error_detalle"]) == ("DocumentoNoAptoManual", "EXTRACCION_LOCAL_ERROR")
    if plantilla == "37":
        assert ejecucion["lector"] == LECTOR


# --------------------------------------------------------------------------- despliegue

def test_sql_de_precondiciones_37_es_de_solo_lectura(pg17_nueva_base):
    pg = pg17_nueva_base("36")
    texto = DESPLIEGUE.PRECONDICIONES.lower()
    assert texto.lstrip().startswith("select") and not any(
        p in texto for p in (" insert ", " update ", " delete ", " alter ", " create ", " drop ", " grant "))
    assert pg.sql(DESPLIEGUE.PRECONDICIONES) == "|".join(["t"] * 5)


def test_postcondiciones_en_la_plantilla_37(pg17_nueva_base):
    pg = pg17_nueva_base("37")
    assert pg.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[-3:] == ["t", "t", "t"]


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf37_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    for relativa in (RUTA_37, "pruebas/auditoria_37/desplegar_37.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 37"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_37.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_37/desplegar_37.py")


def test_ensayo_completo_despliegue_37_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "36"))
    _datos_previos(pg, tmp_path)
    rol_despliegue = pgl.rol_supabase(nombre)
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)

    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    import dotenv
    import psycopg2

    real = getattr(psycopg2, "_connect_original_2az", psycopg2.connect)
    psycopg2._connect_original_2az = real
    dsns = []

    def conectar_local(dsn, **_kwargs):
        dsns.append(dsn)
        return real(host="127.0.0.1", port=puerto, dbname=pg.db, user=rol_despliegue,
                    password=pgl.CLAVE_ROL_SUPABASE, connect_timeout=10)

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

    antes = {k: _huella(pg, q) for k, q in HUELLA_37.items()}
    esquema_36 = esquema(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 5
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "columna_lector": True,
                                           "firma_8_regla_y_privilegios": True, "firma_7_envoltorio": True}
    assert {k: _huella(pg, q) for k, q in HUELLA_37.items()} == antes
    # Referencia (superusuario postgres, como el propietario en Supabase): mismo esquema salvo el propietario de la
    # firma nueva, que es el rol que despliega (postgres en Supabase).
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "36"))
    referencia.sql(MIGRACION_37.read_text(encoding="utf-8"))
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema(referencia).replace(referencia.db, "")

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: «37 ausente» falla, y aqui tambien «propietarios 2AX» (la firma nueva es de la imitacion; en
    # Supabase, de postgres).
    assert registro["precondiciones"] == [False, True, True, True, False]

    atras = pgl.sql_como_supabase(pg, ROLLBACK_37.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    assert esquema(pg).replace(pg.db, "") == esquema_36.replace(pg.db, "")
    assert {k: _huella(pg, q) for k, q in HUELLA_37.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_37
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_37_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
