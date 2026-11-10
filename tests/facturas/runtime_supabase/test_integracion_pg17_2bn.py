"""Hito 2BN: migracion 29 (rol de solo lectura cf_lectura) en PostgreSQL 17 local.

Plantillas (pg17_local): "28" (estado productivo), "29" = 28 + migracion 29 dos veces, "29_rollback" = 29 +
rollback. El rol es del cluster (lo comparten las bases del contenedor); los privilegios y las politicas, de cada
base. Se comprueba con SET ROLE y con un inicio de sesion real del rol (el contenedor acepta conexiones locales
sin contrasena): lee lo previsto, la RLS limita a las farmacias habilitadas, no puede escribir ni ejecutar RPC de
escritura y no tiene credencial en el repositorio. Sin produccion ni Farmatic.
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
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _datos_previos, _huella, contenedor_tcp)
from test_integracion_pg17_2ba import _reservas

pytestmark = pytest.mark.pg17_local

MIGRACION_29 = MIG / "29_cf_rol_lectura.sql"
ROLLBACK_29 = MIG / "29_cf_rol_lectura.rollback.sql"
RUTA_29 = "sql/migrations/29_cf_rol_lectura.sql"
SCRIPT_29 = ROOT / "pruebas/auditoria_2bn/desplegar_29.py"
ROL = "cf_lectura"


def _cargar_despliegue(script=SCRIPT_29):
    spec = importlib.util.spec_from_file_location(f"desplegar_29_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar_despliegue()


def _como_rol(pg, sentencia: str) -> str:
    """Ejecuta como cf_lectura (SET ROLE) dentro de una transaccion que se deshace."""
    return pg.sql(f"begin; set local role {ROL}; {sentencia}; rollback;")


def _sesion_del_rol(pg, sentencia: str) -> subprocess.CompletedProcess:
    """Inicio de sesion real como cf_lectura (los ajustes del rol se aplican al iniciar sesion)."""
    return subprocess.run(["docker", "exec", pg.contenedor, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                           "-U", ROL, "-d", pg.db, "-c", sentencia], capture_output=True, text=True,
                          encoding="utf-8", timeout=60)


@pytest.fixture
def con_datos(pg17_nueva_base, tmp_path):
    """Base 29 con datos de PIO y filas de otra farmacia (no habilitada) en las tablas con columna farmacia."""
    pg = pg17_nueva_base("29")
    _datos_previos(pg, tmp_path)
    return _con_rita(pg)


def _con_rita(pg):
    pg.sql("insert into public.documentos_facturas(id,farmacia,archivo_nombre,archivo_ruta,archivo_hash) values "
           "('00000000-0000-4000-8000-0000000002b0','RITA','r.pdf','RITA/r.pdf',"
           f"{_lit(hashlib.sha256(b'rita-2bn').hexdigest())});")
    pg.sql("insert into public.albaranes(farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
           "importe_pvp,importe_puc,descuento,estado) values ('RITA',990002,'2','1.- SAFA','R-2BN',current_date,"
           "1,1,0,'PENDIENTE');")
    return pg


# --------------------------------------------------------------------------- lectura y RLS

@pytest.mark.parametrize("objeto", DESPLIEGUE.LECTURA)
def test_lee_cada_objeto_previsto(con_datos, objeto):
    assert _como_rol(con_datos, f"select count(*) from public.{objeto}").isdigit()


def test_la_rls_limita_a_las_farmacias_habilitadas(con_datos):
    pg = con_datos
    for tabla in ("documentos_facturas", "albaranes"):
        total = int(pg.sql(f"select count(*) from public.{tabla}"))
        rita = int(pg.sql(f"select count(*) from public.{tabla} where farmacia = 'RITA'"))
        assert rita >= 1
        assert _como_rol(pg, f"select count(*) from public.{tabla} where farmacia = 'RITA'") == "0"
        assert int(_como_rol(pg, f"select count(*) from public.{tabla}")) == total - rita
    # Las hijas se ven a traves de la factura de una farmacia habilitada.
    assert _como_rol(pg, "select count(*) from public.facturas") == pg.sql("select count(*) from public.facturas "
                                                                           "where farmacia = 'PIO'")
    assert int(_como_rol(pg, "select count(*) from public.conciliacion_detalles")) > 0


def test_politicas_de_lectura(con_datos):
    roles = {f"{t}.{p}": con_datos.sql(f"select array_to_string({DESPLIEGUE._roles_politica(t, p)}, ',')")
             for t, p in DESPLIEGUE.POLITICAS_COMPARTIDAS + DESPLIEGUE.POLITICAS_NUEVAS}
    assert {k: v for k, v in roles.items() if k.split(".")[1].endswith("_authenticated_select")} == {
        f"{t}.{p}": f"authenticated,{ROL}" for t, p in DESPLIEGUE.POLITICAS_COMPARTIDAS}
    assert {k: v for k, v in roles.items() if k.split(".")[1].endswith("_lectura_select")} == {
        f"{t}.{p}": ROL for t, p in DESPLIEGUE.POLITICAS_NUEVAS}


def test_no_lee_nada_fuera_de_la_lista(con_datos):
    fuera = con_datos.sql(
        "select coalesce(string_agg(c.relname, ',' order by c.relname), '') from pg_class c "
        "where c.relnamespace = 'public'::regnamespace and c.relkind in ('r','p','v','m','f') "
        f"and has_table_privilege('{ROL}', c.oid, 'SELECT') "
        f"and c.relname <> all(array[{', '.join(_lit(o) for o in DESPLIEGUE.LECTURA)}])")
    assert fuera == ""


# --------------------------------------------------------------------------- sin escritura ni RPC

def test_ningun_privilegio_de_escritura_en_public(con_datos):
    assert con_datos.sql(
        "select count(*) from pg_class c where c.relnamespace = 'public'::regnamespace "
        f"and c.relkind in ('r','p','v','m','f') and has_table_privilege('{ROL}', c.oid, "
        "'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')") == "0"
    assert con_datos.sql(
        "select count(*) from pg_class c where c.relnamespace = 'public'::regnamespace and c.relkind = 'S' "
        f"and case when c.relkind = 'S' then has_sequence_privilege('{ROL}', c.oid, 'USAGE,SELECT,UPDATE') end") == "0"


@pytest.mark.parametrize("sentencia", [
    "update public.facturas set importe_total = importe_total",
    "delete from public.documentos_facturas",
    "insert into public.albaranes(farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,importe_pvp,"
    "importe_puc,descuento,estado) values ('PIO',990003,'2','x','x',current_date,1,1,0,'PENDIENTE')",
    "update public.cf_configuracion set normalizacion_automatica = true",
    "truncate public.historial_facturas",
])
def test_no_puede_escribir(con_datos, sentencia):
    with pytest.raises(RuntimeError, match="permission denied"):
        _como_rol(con_datos, sentencia)


def test_no_puede_ejecutar_funciones_privilegiadas_ni_que_escriben(con_datos):
    ejecutables = con_datos.sql(
        "select coalesce(string_agg(p.oid::regprocedure::text, ',' order by 1), '') from pg_proc p "
        f"where p.pronamespace = 'public'::regnamespace and has_function_privilege('{ROL}', p.oid, 'EXECUTE') "
        "and p.prorettype <> 'event_trigger'::regtype "
        "and (p.prosecdef or (p.provolatile = 'v' and p.prorettype <> 'trigger'::regtype))")
    # Las event_trigger (rls_auto_enable, 2BQ) no se pueden llamar: ver test_cf_lectura_no_puede_llamar_a_rls_auto_enable.
    assert ejecutables == ""
    for llamada in ("select public.cf_solicitar_reprocesado('00000000-0000-4000-8000-0000000002b0'::uuid, 'x')",
                    "select * from public.cf_reclamar_documento_normalizacion_manual_one_shot('x', 60)",
                    "select public.cf_ejecucion_persistida('00000000-0000-4000-8000-0000000002b0'::uuid, 'k')"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _como_rol(con_datos, llamada)


def test_inicio_de_sesion_real_en_solo_lectura(con_datos):
    pg = con_datos
    lectura = _sesion_del_rol(pg, "show default_transaction_read_only")
    assert lectura.returncode == 0 and lectura.stdout.strip() == "on", lectura.stderr
    assert _sesion_del_rol(pg, "select count(*) > 0 from public.facturas").stdout.strip() == "t"
    escritura = _sesion_del_rol(pg, "update public.facturas set importe_total = importe_total")
    assert escritura.returncode != 0 and ("read-only transaction" in escritura.stderr
                                           or "permission denied" in escritura.stderr)


def test_atributos_y_credencial(pg17_nueva_base):
    pg = pg17_nueva_base("29")
    [rol] = pg.json(f"select r.rolcanlogin, r.rolsuper, r.rolbypassrls, r.rolcreaterole, r.rolcreatedb, "
                    f"r.rolreplication, r.rolinherit, r.rolconnlimit, r.rolconfig, a.rolpassword is null as "
                    f"sin_contrasena from pg_roles r join pg_authid a on a.oid = r.oid where r.rolname = '{ROL}'")
    assert rol == {"rolcanlogin": True, "rolsuper": False, "rolbypassrls": False, "rolcreaterole": False,
                   "rolcreatedb": False, "rolreplication": False, "rolinherit": False, "rolconnlimit": 5,
                   "rolconfig": ["default_transaction_read_only=on", "statement_timeout=60s",
                                 "idle_in_transaction_session_timeout=60s"],
                   "sin_contrasena": True}
    # Nunca miembro de otro rol (no hereda privilegios ajenos).
    assert pg.sql(f"select count(*) from pg_auth_members where member = '{ROL}'::regrole") == "0"
    assert "password" not in MIGRACION_29.read_text(encoding="utf-8").lower()


# --------------------------------------------------------------------------- migracion

def test_rollback_29_devuelve_el_esquema_28(pg17_nueva_base):
    atras = pg17_nueva_base("29_rollback")
    assert esquema(atras) == esquema(pg17_nueva_base("28"))
    for t, p in DESPLIEGUE.POLITICAS_COMPARTIDAS:
        assert atras.sql(f"select array_to_string({DESPLIEGUE._roles_politica(t, p)}, ',')") == "authenticated"
    for t, p in DESPLIEGUE.POLITICAS_NUEVAS:
        assert atras.sql(f"select count(*) from pg_policy where polrelid = 'public.{t}'::regclass "
                         f"and polname = '{p}'") == "0"
    # El rol es del cluster: si sigue existiendo (otras bases del contenedor lo usan), aqui no tiene privilegios.
    if atras.sql(f"select count(*) from pg_roles where rolname = '{ROL}'") == "1":
        assert atras.sql("select count(*) from pg_class c where c.relnamespace = 'public'::regnamespace "
                         f"and has_table_privilege('{ROL}', c.oid, 'SELECT,INSERT,UPDATE,DELETE')") == "0"
        # USAGE sobre public lo tiene cualquier rol via PUBLIC; lo que no queda es la concesion directa.
        assert atras.sql("select count(*) from pg_namespace n cross join lateral aclexplode(n.nspacl) a "
                         f"where n.nspname = 'public' and a.grantee = '{ROL}'::regrole") == "0"


def test_29_exige_la_28(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_28_AUSENTE"):
        pg17_nueva_base("27").sql(MIGRACION_29.read_text(encoding="utf-8"))


def test_29_no_altera_datos_existentes(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("28")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    referencia = esquema(pg17_nueva_base("29"))
    pg.sql(MIGRACION_29.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_29.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert esquema(pg) == referencia and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


# --------------------------------------------------------------------------- despliegue

def test_sql_de_precondiciones_29_es_de_solo_lectura(pg17_nueva_base):
    sql = DESPLIEGUE.PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert pg17_nueva_base("28").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 9)
    assert pg17_nueva_base("29").sql("begin read only; " + sql + "; rollback;").split("|")[:3] == ["f", "t", "f"]


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf2bn_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    """Copia byte a byte el script y la migracion a un repositorio git temporal con su commit."""
    for relativa in (RUTA_29, "pruebas/auditoria_2bn/desplegar_29.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 29"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_29.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_2bn/desplegar_29.py")


def test_ensayo_completo_despliegue_29_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "28"))
    _datos_previos(pg, tmp_path)
    # Como en produccion: el rol no existe en el cluster y se despliega con la imitacion del postgres de Supabase.
    assert pg.sql(f"select count(*) from pg_roles where rolname = '{ROL}'") == "0"
    rol_despliegue = pgl.rol_supabase(nombre)
    # Como en produccion, la plantilla trae rls_auto_enable() (SECURITY DEFINER, event_trigger, EXECUTE para PUBLIC;
    # 2BQ). El segundo despliegue de la 29 se revirtio porque la postcondicion la contaba como privilegiada (2BN-D).
    assert pg.sql("select count(*) from pg_proc where oid = 'public.rls_auto_enable()'::regprocedure") == "1"
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
    reservas = _reservas(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit)
    assert registro["precondiciones"] == [True] * 9
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "rol": True, "privilegios": True,
                                           "politicas": True}
    # Referencia (superusuario) despues del despliegue: el rol ya existe y lo creo la imitacion.
    referencia = pgl.base_desde(nombre, pgl.construir_plantilla(nombre, "28"))
    _datos_previos(referencia, tmp_path)
    referencia.sql(MIGRACION_29.read_text(encoding="utf-8"))
    assert esquema(pg).replace(pg.db, "") == esquema(referencia).replace(referencia.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes and _reservas(pg) == reservas

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: ni «29 ausente» ni «politicas de la 28»; el resto sigue en verde.
    assert registro["precondiciones"] == [False, True, False, True, True, True, True, True, True]
    assert esquema(pg).replace(pg.db, "") == esquema(referencia).replace(referencia.db, "")

    # El rollback tambien funciona con la imitacion: politicas de vuelta a authenticated, sin privilegios del rol.
    atras = pgl.sql_como_supabase(pg, ROLLBACK_29.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    for t, p in DESPLIEGUE.POLITICAS_COMPARTIDAS:
        assert pg.sql(f"select array_to_string({DESPLIEGUE._roles_politica(t, p)}, ',')") == "authenticated"
    assert pg.sql("select count(*) from pg_class c where c.relnamespace = 'public'::regnamespace "
                  f"and has_table_privilege('{ROL}', c.oid, 'SELECT')") == "0"


def test_la_imitacion_del_postgres_de_supabase_rechaza_lo_que_rechaza_produccion(contenedor_tcp):
    """2BN-D: el primer despliegue de la 29 se revirtio por un ALTER ROLE ... NOSUPERUSER (postgres no es
    superusuario en Supabase). La imitacion reproduce ese rechazo y no puede adoptar postgres."""
    nombre, _puerto, _plantilla = contenedor_tcp
    pg = pgl._Pg(nombre, "postgres")
    rol = pgl.rol_supabase(nombre)
    assert pg.sql(f"select rolsuper, rolcreaterole, rolreplication, rolbypassrls from pg_roles "
                  f"where rolname = '{rol}'") == "f|t|t|t"
    rechazo = pgl.sql_como_supabase(pg, f"alter role {rol} nosuperuser")
    assert rechazo.returncode != 0 and "permission denied to alter role" in rechazo.stderr
    adoptar = pgl.sql_como_supabase(pg, "set role postgres")
    assert adoptar.returncode != 0 and "permission denied" in adoptar.stderr
    assert pgl.sql_como_supabase(pg, "select current_setting('is_superuser')").stdout.strip() == "off"


def test_cf_lectura_no_puede_llamar_a_rls_auto_enable(con_datos):
    """La postcondicion excluye las funciones event_trigger: el rol tiene EXECUTE (via PUBLIC), pero no se pueden
    llamar directamente."""
    pg = con_datos
    assert pg.sql(f"select has_function_privilege('{ROL}', 'public.rls_auto_enable()', 'EXECUTE'), p.prosecdef "
                  "from pg_proc p where p.oid = 'public.rls_auto_enable()'::regprocedure") == "t|t"
    llamada = _sesion_del_rol(pg, "select public.rls_auto_enable()")
    assert llamada.returncode != 0 and "trigger functions can only be called as triggers" in llamada.stderr
    # La postcondicion de privilegios del despliegue sigue en verde con la funcion presente.
    # Columnas: datos (2), rol, privilegios, politicas.
    assert pg.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[2:] == ["t", "t", "t"]


def test_la_29_no_altera_atributos_del_rol():
    """Los atributos solo se fijan en CREATE ROLE; ningun ALTER ROLE de la 29 nombra atributos."""
    import re

    sql = re.sub(r"--[^\n]*", "", MIGRACION_29.read_text(encoding="utf-8")).lower()
    alteraciones = re.findall(r"alter role\s+cf_lectura\s+([a-z_]+)", sql)
    assert alteraciones and set(alteraciones) == {"set"}


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_29
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_29_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")


# --------------------------------------------------------------------------- prueba de acceso (2BN-D)
# Al final del modulo: usan contenedor_tcp despues del ensayo de despliegue (que exige el rol ausente al empezar).

SCRIPT_ACCESO = ROOT / "pruebas/auditoria_2bn_d/probar_acceso_cf_lectura.py"


def _cargar_acceso():
    spec = importlib.util.spec_from_file_location(f"acceso_2bnd_{uuid.uuid4().hex[:6]}", SCRIPT_ACCESO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_prueba_de_acceso_contra_pg17_local(contenedor_tcp, tmp_path):
    nombre, puerto, _plantilla = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "29"))
    _datos_previos(pg, tmp_path)
    _con_rita(pg)
    pg.sql(f"alter role {ROL} password 'local-only'")
    try:
        resultado = _cargar_acceso().probar("127.0.0.1", puerto, ROL, "local-only", dbname=pg.db, sslmode="disable")
    finally:
        pg.sql(f"alter role {ROL} password null")
    assert resultado["veredicto"] == "ACCESO_OK", resultado
    assert resultado["farmacias_visibles"] == ["PIO"]
    assert resultado["insert"]["sqlstate"] == "42501" and resultado["rpc_escritura"]["sqlstate"] == "42501"
    pio = ("select (select count(*) from public.facturas where farmacia = 'PIO'), "
           "(select count(*) from public.conciliaciones c join public.facturas f on f.id = c.factura_id "
           "where f.farmacia = 'PIO'), (select count(*) from public.documentos_facturas where farmacia = 'PIO')")
    assert "|".join(str(v) for v in resultado["conteos"].values()) == pg.sql(pio)


def test_prueba_de_acceso_sin_contrasena_no_conecta(monkeypatch, capsys):
    acceso = _cargar_acceso()
    monkeypatch.delenv(acceso.VARIABLE, raising=False)
    monkeypatch.setattr(acceso, "probar", lambda *a, **k: pytest.fail("no debe conectar"))
    assert acceso.main(["host", "6543"]) == 2
    with pytest.raises(SystemExit):
        acceso.main(["host", "6543", "contrasena-como-argumento"])


def test_prueba_de_acceso_no_imprime_la_contrasena(monkeypatch, capsys):
    acceso = _cargar_acceso()
    secreto = "secreto-" + uuid.uuid4().hex
    monkeypatch.setenv(acceso.VARIABLE, secreto)
    recibidos = []

    def falla(host, puerto, usuario, contrasena, **_k):
        recibidos.append((usuario, contrasena))
        raise RuntimeError("conexion rechazada")

    monkeypatch.setattr(acceso, "probar", falla)
    assert acceso.main(["host", "6543"]) == 2
    assert recibidos == [(f"cf_lectura.{acceso.PROJECT_REF}", secreto)]
    assert secreto not in capsys.readouterr().out

