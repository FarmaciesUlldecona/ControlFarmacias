"""Hito AUTO-A: migracion 32 (resumen nocturno) y noche automatica Alliance en PostgreSQL 17 local.

Plantillas (pg17_local): "31" (estado productivo), "32" = 31 + migracion 32 dos veces, "32_rollback" = 32 + rollback.
Diseno: pruebas/auditoria_auto_alliance/DISENO.md. Se comprueba:
- la 32: tabla con RLS, lectura solo para cf_lectura, nada para anon ni authenticated, rollback exacto al esquema 31,
  y desplegar_32.py ensayado con el rol que imita al postgres de Supabase (segundo intento revertido);
- la noche completa con el orquestador real (``noche_automatica.ejecutar_noche``), el compositor automatico y una
  sesion READ_ONLY real: sombra, normalizacion Alliance / no soportado, conciliacion CONCILIADA con resultado real =
  simulado, DIFERENCIA que para la conciliacion sin reclamar, guard por noche, puertas, limites, noche anterior sin
  cerrar y fila ajena (postcheck 2AX por fila).
La fila de resumen la escribe el cliente de los tests del 2AZ, que usa el rol del sistema con sus privilegios por
defecto (los de Supabase, reproducidos en la base local desde el 2BQ). Sin produccion ni Farmatic.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import uuid

import pytest

import pg17_local as pgl
from pg17_local import ALLIANCE, HEFAME, MIG, ROOT, _lit, _registrar, base_desde, esquema
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _huella, _preparar_2ao, _solo_primera, contenedor_tcp)
from test_integracion_pg17_2be import _recepcion_50898
from src.facturas.runtime_supabase import noche_automatica as na
from src.facturas.runtime_supabase.compositor_automatico import construir_worker_automatico_productivo
from src.facturas.runtime_supabase.lectura_readonly import sesion_lectura

pytestmark = pytest.mark.pg17_local

MIGRACION_32 = MIG / "32_cf_noches_automaticas.sql"
ROLLBACK_32 = MIG / "32_cf_noches_automaticas.rollback.sql"
RUTA_32 = "sql/migrations/32_cf_noches_automaticas.sql"
SCRIPT_32 = ROOT / "pruebas/auditoria_auto_alliance/desplegar_32.py"
TABLA = "cf_noches_automaticas"


def _cargar_despliegue(script=SCRIPT_32):
    spec = importlib.util.spec_from_file_location(f"desplegar_32_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar_despliegue()


# --------------------------------------------------------------------------- migracion 32


@pytest.fixture
def base_efimera(pg17_contenedor, pg17_plantilla):
    """Como ``pg17_nueva_base``, pero borra al terminar cada base que crea: el contenedor compartido es tmpfs y la
    suite completa se queda sin espacio si las copias se acumulan."""
    creadas = []

    def crear(variante: str) -> pgl._Pg:
        pg = base_desde(pg17_contenedor, pg17_plantilla(variante))
        creadas.append(pg.db)
        return pg

    yield crear
    for db in creadas:
        pgl.cerrar_sesiones(pg17_contenedor, db)
        pgl._docker("exec", pg17_contenedor, "dropdb", "-U", "postgres", "--if-exists", db, comprobar=False)


@pytest.fixture
def base32(base_efimera):
    return base_efimera("32")


def test_32_privilegios_rls_y_postcondiciones(base32):
    pg = base32
    assert pg.sql(f"select relrowsecurity from pg_class where oid = 'public.{TABLA}'::regclass") == "t"
    assert pg.sql(f"select count(*) from pg_policy where polrelid = 'public.{TABLA}'::regclass") == "1"
    assert pg.sql(f"select has_table_privilege('cf_lectura', 'public.{TABLA}', 'SELECT'), "
                  f"has_table_privilege('cf_lectura', 'public.{TABLA}', 'INSERT,UPDATE,DELETE,TRUNCATE')") == "t|f"
    for rol in ("anon", "authenticated", "cf_trabajadores_web"):
        assert pg.sql(f"select has_table_privilege('{rol}', 'public.{TABLA}', "
                      "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE')") == "f", rol
    assert pg.sql(f"select ({DESPLIEGUE.ACL_AJENA}), ({DESPLIEGUE.ACL_ESCRITOR})") == "0|t"
    # Columnas: datos (3), tabla, lectura y ACL, configuracion global.
    assert pg.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[3:] == ["t"] * 3
    # cf_lectura lee las filas (politica) y anon no.
    pg.sql(f"insert into public.{TABLA} (fecha, modo, resultado) values ('2026-11-13', 'SOMBRA', 'EN_CURSO')")
    assert pg.sql(f"begin; set local role cf_lectura; select count(*) from public.{TABLA}; rollback;") == "1"


FILAS_INCOHERENTES = [
    f"insert into public.{TABLA} (fecha, modo, resultado, fin) values ('2026-11-13', 'REAL', 'EN_CURSO', now())",
    f"insert into public.{TABLA} (fecha, modo, resultado) values ('2026-11-13', 'REAL', 'NOCHE_OK')",
    f"insert into public.{TABLA} (fecha, modo, resultado) values ('2026-11-13', 'OTRO', 'EN_CURSO')",
    f"insert into public.{TABLA} (fecha, modo, resultado, commit_codigo) values ('2026-11-13', 'REAL', "
    "'EN_CURSO', 'no-es-un-sha')",
    f"insert into public.{TABLA} (fecha, modo, resultado, para_revisar) values ('2026-11-13', 'REAL', "
    "'EN_CURSO', '{}'::jsonb)",
]


def test_32_rechaza_filas_incoherentes(base32):
    for sentencia in FILAS_INCOHERENTES:
        with pytest.raises(Exception):
            base32.sql(sentencia)
    assert base32.sql(f"select count(*) from public.{TABLA}") == "0"


def test_32_una_fila_por_noche(base32):
    base32.sql(f"insert into public.{TABLA} (fecha, modo, resultado) values ('2026-11-13', 'SOMBRA', 'EN_CURSO')")
    with pytest.raises(Exception):
        base32.sql(f"insert into public.{TABLA} (fecha, modo, resultado) values ('2026-11-13', 'REAL', 'EN_CURSO')")


def test_32_exige_la_31(base_efimera):
    with pytest.raises(Exception, match="MIGRACION_31_AUSENTE"):
        base_efimera("30").sql(MIGRACION_32.read_text(encoding="utf-8"))


def test_rollback_32_devuelve_exactamente_el_esquema_31(base_efimera):
    # Sobre una copia de la 32 (sin plantilla 32_rollback en el contenedor compartido).
    atras, limpia = base_efimera("32"), base_efimera("31")
    atras.sql(ROLLBACK_32.read_text(encoding="utf-8"))
    assert esquema(atras).replace(atras.db, "") == esquema(limpia).replace(limpia.db, "")


def test_sql_de_precondiciones_32_es_de_solo_lectura(base_efimera):
    pg = base_efimera("31")
    salida = pg.sql(f"begin read only; {DESPLIEGUE.PRECONDICIONES}; rollback;")
    assert salida.split("|") == ["t"] * 7


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf32_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino):
    for relativa in (RUTA_32, "pruebas/auditoria_auto_alliance/desplegar_32.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 32"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_32.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_auto_alliance/desplegar_32.py")


def test_ensayo_completo_despliegue_32_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "31"))
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

    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 7
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "tabla": True, "lectura_y_acl": True,
                                           "configuracion_global": True}
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    # Mismo esquema que aplicar la 32 como postgres, salvo el propietario de la tabla nueva.
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "31"))
    referencia.sql(MIGRACION_32.read_text(encoding="utf-8"))
    assert esquema(pg).replace(pg.db, "").replace(f"OWNER TO {rol_despliegue};", "OWNER TO postgres;").replace(
        f"Owner: {rol_despliegue}", "Owner: postgres") == esquema(referencia).replace(referencia.db, "")

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: «32 ausente» falla, y tambien «propietarios 2AX» (la tabla es de la imitacion; en Supabase, de
    # postgres).
    assert registro["precondiciones"] == [False, True, True, True, True, True, False]

    atras = pgl.sql_como_supabase(pg, ROLLBACK_32.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    limpia = base_desde(nombre, pgl.construir_plantilla(nombre, "31"))
    assert esquema(pg).replace(pg.db, "") == esquema(limpia).replace(limpia.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_32
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_32_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")


# --------------------------------------------------------------------------- noche automatica


@pytest.fixture
def entorno_noche(contenedor_tcp, tmp_path):
    """Base 32 en el contenedor TCP, sesion READ_ONLY real por psycopg2 y un constructor de entornos."""
    nombre, puerto, _plantilla = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "32"))
    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    import psycopg2

    conexion = psycopg2.connect(host="127.0.0.1", port=puerto, dbname=pg.db, user="postgres",
                                password="local-only", connect_timeout=10)
    ahora = dt.datetime.now(dt.timezone.utc)
    tareas = {"tareas": [{"nombre": n, "ultima": ahora.isoformat(), "resultado": 0} for n in na.TAREAS_PREVIAS]}

    def crear(cliente, *, tareas_=tareas, git=("a" * 40, []), envolver=None, reloj=None):
        def construir(cfg):
            worker = construir_worker_automatico_productivo(cliente, cfg, "auto-test", tmp_path / "w")
            return envolver(worker) if envolver else worker
        return na.Entorno(abrir_lectura=lambda: sesion_lectura(conexion), cliente=cliente, tareas=lambda: tareas_,
                          puerta_git=lambda: git, construir_worker=construir,
                          directorio_informes=tmp_path / "informes", reloj=reloj or (lambda: ahora))

    yield pg, crear, ahora
    conexion.close()


def _flags(pg, normalizacion: bool, conciliacion: bool) -> None:
    pg.sql(f"update public.cf_configuracion set normalizacion_automatica = {str(normalizacion).lower()}, "
           f"conciliacion_automatica = {str(conciliacion).lower()} where id;")


def _fila(pg, fecha) -> dict:
    [fila] = pg.json(f"select n.*, n.fecha::text as fecha from public.{TABLA} n "
                     f"where n.fecha = {_lit(fecha.isoformat())}")
    return fila


def _solo_estos_en_cola(pg, documentos) -> None:
    """Saca de la cola (backoff futuro) los documentos previos del escenario: la noche solo ve los del test."""
    pg.sql("update public.documentos_facturas set proximo_reintento_at = now() + interval '1 day' "
           "where estado_lectura in ('PENDIENTE','ERROR') and id not in ("
           + ",".join(_lit(d) for d in documentos) + ");")


def _hefame(i: int) -> bytes:
    """HEFAME no autorizado con un hash distinto por documento (archivo_hash es unico)."""
    return HEFAME.read_bytes() + b"\n% copia " + str(i).encode() + b"\n"


def _cliente_2ao(pg, tmp_path):
    """Escenario 2AO (PDF real de 08007969, excluido de git): factura conciliable como n.o 1."""
    cliente, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    _recepcion_50898(pg, ids["08007969"])
    _solo_primera(pg, ids, "08007969")
    return cliente, ids


def test_noche_sombra_solo_escribe_su_fila(entorno_noche, tmp_path):
    pg, crear, ahora = entorno_noche
    cliente, ids = _cliente_2ao(pg, tmp_path)
    alliance = _registrar(pg, cliente, ALLIANCE.read_bytes(), 50)
    _solo_estos_en_cola(pg, [alliance])
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    documentos = pg.sql("select md5(string_agg(md5(to_jsonb(d)::text), '' order by d.id)) "
                        "from public.documentos_facturas d")
    assert na.ejecutar_noche("SOMBRA", crear(cliente)) == na.CODIGO_OK
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql("select md5(string_agg(md5(to_jsonb(d)::text), '' order by d.id)) "
                  "from public.documentos_facturas d") == documentos
    fila = _fila(pg, ahora.astimezone().date())
    assert (fila["modo"], fila["resultado"], fila["documentos_reclamados"], fila["conciliadas"]) == (
        "SOMBRA", "NOCHE_OK", 0, 0)
    informe = json.loads((tmp_path / "informes" / fila["fecha"] / "informe.json").read_text(encoding="utf-8"))
    assert informe["postcheck"]["veredicto"] == "POSTCHECK_OK"
    assert informe["postcheck"]["filas_cambiadas_por_tabla"] == {}
    assert alliance in [d["documento_id"] for d in informe["sombra"]["documentos_que_reclamaria"]]
    assert informe["sombra"]["conciliacion_n1"]["factura_id"] == ids["08007969"]
    assert informe["sombra"]["conciliacion_n1"]["resultado"] == "CONCILIADA"
    assert informe["sombra"]["conciliacion_n1_motivo_para_revisar"] is None
    assert fila["informe_sha256"] == hashlib.sha256(
        (tmp_path / "informes" / fila["fecha"] / "informe.json").read_bytes()).hexdigest()


def test_noche_real_concilia_el_n1_y_para_en_la_primera_diferencia(entorno_noche, tmp_path):
    pg, crear, ahora = entorno_noche
    cliente, ids = _cliente_2ao(pg, tmp_path)
    _flags(pg, normalizacion=False, conciliacion=True)
    assert na.ejecutar_noche("REAL", crear(cliente)) == na.CODIGO_OK
    fila = _fila(pg, ahora.astimezone().date())
    informe = json.loads((tmp_path / "informes" / fila["fecha"] / "informe.json").read_text(encoding="utf-8"))
    assert fila["resultado"] == "NOCHE_OK" and fila["conciliadas"] == 1
    [conciliada] = informe["conciliaciones"]
    assert conciliada["factura_id"] == ids["08007969"]
    # Resultado real = simulado: misma clave idempotente (AUTOMATICO), factura CONCILIADA, sin claims.
    real = pg.json(f"select c.idempotency_key, c.disparador, f.estado_conciliacion_cf, f.conciliacion_bloqueado_por "
                   f"from public.conciliaciones c join public.facturas f on f.id = c.factura_id "
                   f"where c.es_actual and c.factura_id = {_lit(ids['08007969'])}")[0]
    assert real == {"idempotency_key": conciliada["idempotency_key"], "disparador": "AUTOMATICO",
                    "estado_conciliacion_cf": "CONCILIADA", "conciliacion_bloqueado_por": None}
    assert informe["postcheck"]["veredicto"] == "POSTCHECK_OK"
    # El siguiente n.o 1 no simula CONCILIADA: se anota y NO se reclama (D2): sin intentos ni conciliaciones nuevas.
    assert [p["tipo"] for p in informe["para_revisar"]] in ([], ["DIFERENCIA"])
    for p in informe["para_revisar"]:
        assert pg.sql(f"select estado_conciliacion_cf, conciliacion_intentos_fallo, "
                      f"(select count(*) from public.conciliaciones c where c.factura_id = f.id) "
                      f"from public.facturas f where f.id = {_lit(p['factura_id'])}") == "PENDIENTE_CONCILIAR|0|0"


def test_noche_real_normaliza_alliance_y_deja_no_soportado_al_resto(entorno_noche, tmp_path):
    pg, crear, ahora = entorno_noche
    cliente, _ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    alliance = _registrar(pg, cliente, ALLIANCE.read_bytes(), 50)
    hefame = _registrar(pg, cliente, HEFAME.read_bytes(), 51)
    _solo_estos_en_cola(pg, [alliance, hefame])
    _flags(pg, normalizacion=True, conciliacion=False)
    assert na.ejecutar_noche("REAL", crear(cliente)) == na.CODIGO_OK
    fila = _fila(pg, ahora.astimezone().date())
    assert pg.sql(f"select estado_lectura from public.documentos_facturas where id = {_lit(alliance)}") == \
        "NORMALIZADA"
    assert pg.sql(f"select estado_lectura, intentos_fallo_normalizacion from public.documentos_facturas "
                  f"where id = {_lit(hefame)}") == "PROVEEDOR_NO_SOPORTADO|0"
    facturas = int(pg.sql(f"select count(*) from public.facturas where documento_id = {_lit(alliance)}"))
    assert facturas >= 1
    assert (fila["resultado"], fila["documentos_reclamados"], fila["alliance_persistidos"], fila["no_soportados"],
            fila["facturas_creadas"], fila["conciliadas"]) == ("NOCHE_OK", 2, 1, 1, facturas, 0)
    disparadores = pg.sql(f"select string_agg(distinct disparador, ',') from public.normalizacion_ejecuciones "
                          f"where documento_id in ({_lit(alliance)}, {_lit(hefame)})")
    assert disparadores == "AUTOMATICO"
    informe = json.loads((tmp_path / "informes" / fila["fecha"] / "informe.json").read_text(encoding="utf-8"))
    assert informe["postcheck"]["veredicto"] == "POSTCHECK_OK"


def test_noche_respeta_el_limite_de_la_primera_noche(entorno_noche, tmp_path):
    pg, crear, ahora = entorno_noche
    cliente, _ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    hefame = [_registrar(pg, cliente, _hefame(i), 60 + i) for i in range(6)]
    _solo_estos_en_cola(pg, hefame)
    _flags(pg, normalizacion=True, conciliacion=False)
    assert na.ejecutar_noche("REAL", crear(cliente)) == na.CODIGO_OK
    fila = _fila(pg, ahora.astimezone().date())
    assert (fila["resultado"], fila["documentos_reclamados"], fila["limites"]["documentos"]) == ("FIN_LIMITE", 5, 5)
    assert pg.sql("select count(*) from public.documentos_facturas where estado_lectura = 'PENDIENTE' and id in ("
                  + ",".join(_lit(h) for h in hefame) + ")") == "1"


def test_tres_noches_reales_buenas_dan_limites_plenos(entorno_noche, tmp_path):
    pg, crear, ahora = entorno_noche
    cliente, _ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    hoy = ahora.astimezone().date()
    for dias in (1, 2, 3):
        pg.sql(f"insert into public.{TABLA} (fecha, modo, resultado, fin) values "
               f"({_lit((hoy - dt.timedelta(days=dias)).isoformat())}, 'REAL', 'NOCHE_OK', now())")
    _solo_estos_en_cola(pg, [_registrar(pg, cliente, _hefame(99), 99)])
    _flags(pg, normalizacion=True, conciliacion=False)
    assert na.ejecutar_noche("REAL", crear(cliente)) == na.CODIGO_OK
    assert _fila(pg, hoy)["limites"] == {"documentos": 20, "conciliaciones": 20, "minutos": 60}


def test_guard_una_sola_noche_por_fecha(entorno_noche, tmp_path):
    pg, crear, ahora = entorno_noche
    cliente, _ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    assert na.ejecutar_noche("SOMBRA", crear(cliente)) == na.CODIGO_OK
    antes = pg.sql(f"select to_jsonb(n)::text from public.{TABLA} n")
    nuevo = _registrar(pg, cliente, HEFAME.read_bytes(), 70)
    _solo_estos_en_cola(pg, [nuevo])
    _flags(pg, normalizacion=True, conciliacion=False)
    assert na.ejecutar_noche("REAL", crear(cliente)) == na.CODIGO_YA_EJECUTADA
    assert pg.sql(f"select to_jsonb(n)::text from public.{TABLA} n") == antes
    assert pg.sql(f"select estado_lectura from public.documentos_facturas where id = {_lit(nuevo)}") == "PENDIENTE"


@pytest.mark.parametrize("caso", ["flags_apagados", "tarea_con_error", "git", "noche_anterior_en_curso"])
def test_puerta_fallida_para_sin_reclamar(entorno_noche, tmp_path, caso):
    pg, crear, ahora = entorno_noche
    cliente, _ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    pendiente = _registrar(pg, cliente, HEFAME.read_bytes(), 80)
    _solo_estos_en_cola(pg, [pendiente])
    _flags(pg, normalizacion=caso != "flags_apagados", conciliacion=False)
    kwargs = {}
    if caso == "tarea_con_error":
        kwargs["tareas_"] = {"tareas": [{"nombre": n, "ultima": ahora.isoformat(), "resultado": 1}
                                        for n in na.TAREAS_PREVIAS]}
    if caso == "git":
        kwargs["git"] = ("a" * 40, ["GIT_ARBOL_NO_LIMPIO"])
    if caso == "noche_anterior_en_curso":
        ayer = ahora.astimezone().date() - dt.timedelta(days=1)
        pg.sql(f"insert into public.{TABLA} (fecha, modo, resultado) values ({_lit(ayer.isoformat())}, 'REAL', "
               "'EN_CURSO')")
    assert na.ejecutar_noche("REAL", crear(cliente, **kwargs)) == na.CODIGO_PARADA
    fila = _fila(pg, ahora.astimezone().date())
    assert fila["resultado"] == "PARADA" and fila["motivo"].startswith("PUERTAS:")
    assert pg.sql(f"select estado_lectura from public.documentos_facturas where id = {_lit(pendiente)}") == \
        "PENDIENTE"


def test_fila_ajena_cambiada_es_parada(entorno_noche, tmp_path):
    pg, crear, ahora = entorno_noche
    cliente, _ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    _solo_estos_en_cola(pg, [_registrar(pg, cliente, HEFAME.read_bytes(), 90)])
    _flags(pg, normalizacion=True, conciliacion=False)

    def envolver(worker):
        from types import SimpleNamespace

        def ejecutar_y_tocar_un_albaran():
            pg.sql("update public.albaranes set importe_puc = importe_puc + 1 where id_contador = "
                   "(select min(id_contador) from public.albaranes);")
            return worker.normalizacion.ejecutar_una()
        return SimpleNamespace(normalizacion=SimpleNamespace(ejecutar_una=ejecutar_y_tocar_un_albaran),
                               conciliacion=worker.conciliacion)

    if pg.sql("select count(*) from public.albaranes") == "0":
        pytest.skip("sin albaranes en el escenario")
    assert na.ejecutar_noche("REAL", crear(cliente, envolver=envolver)) == na.CODIGO_PARADA
    fila = _fila(pg, ahora.astimezone().date())
    assert fila["resultado"] == "PARADA" and "POSTCHECK_FILAS_AJENAS" in fila["motivo"]


def test_sin_flag_de_normalizacion_no_se_normaliza(entorno_noche, tmp_path):
    pg, crear, ahora = entorno_noche
    cliente, _ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    pendiente = _registrar(pg, cliente, ALLIANCE.read_bytes(), 95)
    _solo_estos_en_cola(pg, [pendiente])
    _flags(pg, normalizacion=False, conciliacion=True)
    na.ejecutar_noche("REAL", crear(cliente))
    assert pg.sql(f"select estado_lectura from public.documentos_facturas where id = {_lit(pendiente)}") == \
        "PENDIENTE"
    assert _fila(pg, ahora.astimezone().date())["documentos_reclamados"] == 0
