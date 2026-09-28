"""Hito 2AX: ensayo local COMPLETO de pruebas/auditoria_2ax/desplegar_19.py.

Norma (REGLAS_CRITICAS.md): todo script de despliegue productivo se ensaya de
principio a fin en local antes de usarlo en produccion.

El script se ejecuta sin modificar (``main()``): verifica el SHA contra el
commit, evalua sus 8 precondiciones, aplica la 19 en una transaccion y registra
el resultado. Solo se redirige ``psycopg2.connect`` a un PostgreSQL 17 local
(contenedor propio escuchando en 127.0.0.1). Doble barrera: el DSN del entorno
se sustituye por uno productivo FICTICIO sin credenciales, de modo que ni un
fallo de la redireccion podria conectar a produccion.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

import pg17_local as pgl
from pg17_local import ALLIANCE, MIG, ROOT, ClientePg17, _registrar, _worker

sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ax"))
from inventario_readonly import SQL_DEFAULT_ACL, SQL_MATRIZ  # noqa: E402


pytestmark = pytest.mark.pg17_local

SCRIPT = ROOT / "pruebas/auditoria_2ax/desplegar_19.py"
COMMIT = "f9ff625"
SHA_LF = "3a923261419d3a85dbe786881f428c945833f9930c188266ece8d675b4a2cd93"
DSN_FICTICIO = "postgresql://sin-credenciales@db.vklaiuytvegkelgyspxc.supabase.co:5432/postgres"
MIGRACION_19 = MIG / "19_cf_privilegios_minimos.sql"
ROLLBACK_19 = MIG / "19_cf_privilegios_minimos.rollback.sql"


def _cargar_script():
    spec = importlib.util.spec_from_file_location(f"desplegar_19_{uuid.uuid4().hex[:6]}", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def sql_precondiciones() -> str:
    """Extrae del script, sin ejecutarlo, el SQL exacto de sus precondiciones."""
    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute"
                and n.args and isinstance(n.args[0], (ast.Constant, ast.JoinedStr, ast.BinOp))]
    [consulta] = [c for c in llamadas if "has_table_privilege" in ast.unparse(c.args[0])]
    return eval(compile(ast.Expression(consulta.args[0]), str(SCRIPT), "eval"), vars(_cargar_script()))


@pytest.fixture(scope="module")
def contenedor_tcp():
    if pgl._docker("image", "inspect", pgl.IMAGEN, comprobar=False).returncode:
        pytest.skip("imagen local no disponible")
    nombre = "cf-pg17-ensayo2ax-" + uuid.uuid4().hex[:8]
    pgl._docker("run", "-d", "--rm", "--name", nombre, "--label", "controlfarmacias.certificacion=pg17_local",
                "-p", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql/data",
                "-e", "POSTGRES_PASSWORD=local-only", pgl.IMAGEN)
    try:
        listos = 0
        for _ in range(240):
            ok = pgl._docker("exec", nombre, "psql", "-U", "postgres", "-qAt", "-c", "select 1",
                             comprobar=False).returncode == 0
            listos = listos + 1 if ok else 0
            if listos >= 6:
                break
            time.sleep(0.5)
        puerto = int(pgl._docker("port", nombre, "5432/tcp").stdout.strip().rsplit(":", 1)[1])
        plantilla = pgl.construir_plantilla(nombre, "18")
        yield nombre, puerto, plantilla
    finally:
        pgl._docker("rm", "-f", nombre, comprobar=False)


def _base_produccion(contenedor_tcp, tmp_path):
    """Estado 18 con la matriz y los privilegios por defecto de produccion y 12 conciliaciones."""
    nombre, _, plantilla = contenedor_tcp
    pg = pgl.base_desde(nombre, plantilla)
    pg.sql(ROLLBACK_19.read_text(encoding="utf-8"))
    cliente = ClientePg17(pg)
    _registrar(pg, cliente, ALLIANCE.read_bytes(), 1)
    assert _worker(cliente, tmp_path, "ensayo").ejecutar_una_manual().documentos_reclamados == 1
    pg.sql("insert into public.conciliaciones (factura_id,intento,disparador,estado,es_actual,importe_factura,"
           "importe_explicado,diferencia,resultado,worker_id,finalizado_at) "
           "select f.id, i, 'MANUAL', 'COMPLETADA', i = 4, 1, 1, 0, 'CONCILIADA', 'ensayo-2ax', now() "
           "from (select id from public.facturas where proveedor_literal ilike 'ALLIANCE%') f "
           "cross join generate_series(1, 4) i;")
    assert pg.sql("select count(*) from public.conciliaciones") == "12"
    return pg


def _ejecutar(pg, puerto, salida, monkeypatch) -> tuple[dict, list[str]]:
    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    import psycopg2

    real = getattr(psycopg2, "_connect_original_2ax", psycopg2.connect)
    psycopg2._connect_original_2ax = real
    dsns = []

    def conectar_local(dsn, **_kwargs):
        dsns.append(dsn)
        return real(host="127.0.0.1", port=puerto, dbname=pg.db, user="postgres", password="local-only",
                    connect_timeout=10)

    monkeypatch.setattr(psycopg2, "connect", conectar_local)
    monkeypatch.setenv("CONTROLFARMACIAS_SUPABASE_DB_URL", DSN_FICTICIO)
    try:
        _cargar_script().main(COMMIT, SHA_LF, salida)
    except SystemExit:
        pass
    return json.loads(salida.read_text(encoding="utf-8")), dsns


def _matriz(pg):
    return json.loads(pg.sql(SQL_MATRIZ + ";")), json.loads(pg.sql(SQL_DEFAULT_ACL + ";"))


def test_ensayo_completo_aplica_la_19_y_un_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch):
    if not ALLIANCE.exists():
        pytest.skip("fixture real 2AP ausente")
    nombre, puerto, _ = contenedor_tcp
    pg = _base_produccion(contenedor_tcp, tmp_path)
    referencia = pgl.base_desde(nombre, pg.db)
    referencia.sql(MIGRACION_19.read_text(encoding="utf-8"))

    # Las 8 precondiciones, en una transaccion READ_ONLY, antes de desplegar.
    assert pg.sql("begin read only; " + sql_precondiciones() + "; rollback;") == "t|t|t|t|t|t|t|t"

    registro, dsns = _ejecutar(pg, puerto, tmp_path / "primero.json", monkeypatch)
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", SHA_LF, COMMIT)
    assert registro["precondiciones"] == [True] * 8
    assert _matriz(pg) == _matriz(referencia)
    assert pg.sql("select has_table_privilege('anon', 'public.albaranes', 'SELECT')") == "f"
    volcado = os.environ.get("CF_2AX_VOLCAR_MATRIZ")
    if volcado:  # comparacion manual con la referencia local_19.json del hito
        matriz, defecto = _matriz(pg)
        Path(volcado).write_text(json.dumps({"matriz": matriz, "default_acl": defecto}), encoding="utf-8")

    antes = _matriz(pg)
    registro, _ = _ejecutar(pg, puerto, tmp_path / "segundo.json", monkeypatch)
    assert registro["resultado"] == "REVERTIDA"
    assert "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    assert registro["precondiciones"][:2] == [False, False] and all(registro["precondiciones"][2:])
    assert _matriz(pg) == antes


def test_sql_de_precondiciones_es_valido_y_de_solo_lectura():
    sql = sql_precondiciones()
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter "))
