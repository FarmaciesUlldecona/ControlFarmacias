"""Hito 2AX: migracion 19 (privilegios minimos) certificada en PostgreSQL 17 local.

Base "produccion": cadena 06-18 + rollback de la 19, que fija EXACTAMENTE la
matriz de privilegios y los privilegios por defecto de postgres inventariados en
produccion (incluidos los privilegios por defecto de Supabase para anon,
authenticated y service_role). Sobre ella se aplica la 19 dos veces.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from pg17_local import (
    ALLIANCE, MIG, ROOT, ClientePg17, _lit, _locks, _registrar, _worker, FLAGS_ESPERADOS, FLAGS_SQL,
)
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion

sys.path.insert(0, str(ROOT / "pruebas/auditoria_2ax"))
from inventario_readonly import SQL_DEFAULT_ACL, SQL_MATRIZ  # noqa: E402


pytestmark = pytest.mark.pg17_local

MIGRACION_19 = MIG / "19_cf_privilegios_minimos.sql"
ROLLBACK_19 = MIG / "19_cf_privilegios_minimos.rollback.sql"
USO_SERVICE_ROLE = {
    "documentos_facturas": ["INSERT", "SELECT"], "albaranes": ["INSERT", "SELECT"],
    "facturas": ["SELECT"], "cf_configuracion": ["SELECT"], "proveedores": ["SELECT"],
    "facturas_movimientos": ["SELECT"], "facturas_albaranes_extraidos": ["SELECT"],
    "normalizacion_ejecuciones": ["SELECT"],
}


def _matriz(pg) -> dict:
    return json.loads(pg.sql(SQL_MATRIZ + ";"))


def _default_acl(pg) -> list:
    return json.loads(pg.sql(SQL_DEFAULT_ACL + ";"))


@pytest.fixture
def produccion(pg17_nueva_base):
    pg = pg17_nueva_base("18")
    pg.sql(ROLLBACK_19.read_text(encoding="utf-8"))
    return pg


@pytest.fixture
def base(produccion):
    produccion.sql(MIGRACION_19.read_text(encoding="utf-8"))
    produccion.sql(MIGRACION_19.read_text(encoding="utf-8"))
    return produccion


def _relaciones(pg) -> list[tuple[str, str]]:
    return [(r["relname"], r["relkind"]) for r in pg.json(
        "select relname, relkind::text from pg_class where relnamespace = 'public'::regnamespace "
        "and relkind in ('r','v') order by relname")]


def _columna(pg, tabla: str) -> str:
    return pg.sql("select attname from pg_attribute where attrelid = "
                  f"'public.{tabla}'::regclass and attnum > 0 and not attisdropped order by attnum limit 1")


def _denegado(pg, rol: str, sentencia: str, *, vista: bool = False) -> None:
    # En vistas no actualizables PostgreSQL rechaza la escritura antes del control de privilegios.
    patron = "permission denied|cannot (insert into|update|delete from) view" if vista else "permission denied"
    with pytest.raises(RuntimeError, match=patron):
        pg.sql(f"set role {rol}; {sentencia}")


# --------------------------------------------------------------------------
# anon y authenticated sin acceso
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rol", ["anon", "authenticated"])
def test_rol_publico_sin_acceso_a_tablas_ni_vistas(base, rol):
    relaciones = _relaciones(base)
    assert len(relaciones) == 20
    for tabla, tipo in relaciones:
        columna, vista = _columna(base, tabla), tipo == "v"
        _denegado(base, rol, f"select 1 from public.{tabla} limit 1;")
        _denegado(base, rol, f"insert into public.{tabla} default values;", vista=vista)
        _denegado(base, rol, f"update public.{tabla} set {columna} = {columna} where false;", vista=vista)
        _denegado(base, rol, f"delete from public.{tabla} where false;", vista=vista)
        assert base.sql(
            f"select bool_or(has_table_privilege('{rol}', 'public.{tabla}', p)) from unnest(array["
            "'SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p") == "f", tabla
    for secuencia in ("albaranes_id_seq", "historial_facturas_id_seq"):
        _denegado(base, rol, f"select nextval('public.{secuencia}');")


@pytest.mark.parametrize("rol", ["anon", "authenticated", "service_role"])
def test_validar_y_desvalidar_solo_propietario(base, rol):
    factura = base.sql("select id from public.facturas where farmacia = 'PIO' order by id limit 1")
    for funcion in ("cf_validar_factura", "cf_desvalidar_factura"):
        _denegado(base, rol, f"select public.{funcion}({_lit(factura)}::uuid, 'x');")


def test_matriz_resultante(base):
    matriz = _matriz(base)
    for clave, v in matriz.items():
        tipo, nombre = clave.split(":", 1)
        if tipo in ("tabla", "vista", "secuencia"):
            p = v["privilegios"]
            assert (p["PUBLIC"], p["anon"], p["authenticated"]) == ([], [], []), clave
            assert p["service_role"] == USO_SERVICE_ROLE.get(nombre, []), clave
            if tipo == "tabla":
                assert v["rls"] is True, clave
    for f in ("cf_validar_factura(uuid,text)", "cf_desvalidar_factura(uuid,text)"):
        p = matriz[f"funcion:{f}"]["privilegios"]
        assert all(p[r] == [] for r in p), f


def test_funciones_fuera_de_alcance_sin_cambios(produccion):
    """Triggers, cf_resultado_conciliacion, RPC y demas funciones: la 19 solo toca P2."""
    antes = {k: v for k, v in _matriz(produccion).items() if k.startswith("funcion:")}
    produccion.sql(MIGRACION_19.read_text(encoding="utf-8"))
    despues = {k: v for k, v in _matriz(produccion).items() if k.startswith("funcion:")}
    p2 = {"funcion:cf_validar_factura(uuid,text)", "funcion:cf_desvalidar_factura(uuid,text)"}
    assert {k: v for k, v in antes.items() if k not in p2} == {k: v for k, v in despues.items() if k not in p2}
    assert despues["funcion:cf_persistir_conciliacion(uuid,text,text,text,jsonb)"]["privilegios"]["service_role"] == [
        "EXECUTE"]


def test_objetos_nuevos_de_postgres_sin_privilegios_publicos(base):
    base.sql("create table public._t2ax (id int); "
             "create function public._f2ax() returns int language sql as $$ select 1 $$;")
    for rol in ("anon", "authenticated"):
        assert base.sql(f"select has_table_privilege('{rol}', 'public._t2ax', 'SELECT'), "
                        f"has_function_privilege('{rol}', 'public._f2ax()', 'EXECUTE')") == "f|f"
    assert base.sql("select has_function_privilege('public', 'public._f2ax()', 'EXECUTE')") == "f"
    # service_role conserva sus privilegios por defecto (P3 solo cierra PUBLIC/anon/authenticated).
    assert base.sql("select has_table_privilege('service_role', 'public._t2ax', 'SELECT')") == "t"
    defecto = {(d["rol"], d["esquema"], d["tipo"]): d["acl"] for d in _default_acl(base)}
    for clave, acl in defecto.items():
        if clave[0] == "postgres":
            assert "anon=" not in acl and "authenticated=" not in acl, clave
    assert defecto[("postgres", "*", "f")] == "{postgres=X/postgres}"


# --------------------------------------------------------------------------
# service_role: flujos reales del codigo
# --------------------------------------------------------------------------

def test_service_role_normalizacion_y_conciliacion_manual(base, tmp_path):
    cliente = ClientePg17(base, rol_tablas="service_role")
    _registrar(base, cliente, ALLIANCE.read_bytes(), 1)
    resultado = _worker(cliente, tmp_path, "sr").ejecutar_una_manual()
    assert resultado.documentos_reclamados == 1
    assert base.sql("select count(*) from public.facturas where proveedor_literal ilike 'ALLIANCE%'") == "3"
    base.sql(
        "insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
        "importe_pvp,importe_puc,descuento,estado) select 'PIO', 910000 + row_number() over (order by a.id), '2', "
        "'1.- SAFA', a.numero_albaran, a.fecha_albaran, abs(a.importe_total), abs(a.importe_total), 0, 'PENDIENTE' "
        "from public.facturas_albaranes_extraidos a on conflict do nothing;")
    worker = construir_worker_conciliacion(RepositorioRuntimeSupabase(cliente), "conc-sr")
    assert worker.ejecutar_una_manual() is True
    assert base.sql("select count(*), min(disparador) from public.conciliaciones") == "1|MANUAL_ONE_SHOT"
    assert _locks(base) == "0|0" and base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_service_role_sincronizacion_de_albaranes(base, monkeypatch):
    from src.supabase_client import guardar_albaranes as ga

    cliente = ClientePg17(base, rol_tablas="service_role")
    monkeypatch.setattr(ga, "obtener_cliente_supabase", lambda: cliente)
    ultimo = ga.obtener_ultimo_id_contador("PIO")
    insertado = ga.guardar_albaran({
        "farmacia": "PIO", "id_contador": ultimo + 1, "id_proveedor": "2", "proveedor": "1.- SAFA",
        "numero_albaran": "08C2AX01", "fecha": "2026-09-28", "importe_pvp": 10.0, "importe_puc": 6.0,
        "descuento": 0.0, "estado": "PENDIENTE", "observaciones": None})
    assert insertado and insertado[0]["id_contador"] == ultimo + 1
    assert ga.obtener_ultimo_id_contador("PIO") == ultimo + 1


def test_service_role_importacion_de_facturas(base, monkeypatch):
    from src.facturas import importar_facturas_drive as imp

    cliente = ClientePg17(base, rol_tablas="service_role")
    monkeypatch.setattr(imp, "obtener_cliente_supabase", lambda: cliente)
    antes = imp.obtener_hashes_documentos_supabase()
    imp.registrar_documento_factura(cliente, Path("factura_2ax.pdf"), "PIO/2AX/factura_2ax.pdf", "a" * 64)
    assert imp.obtener_hashes_documentos_supabase() == antes | {"a" * 64}


# --------------------------------------------------------------------------
# Rollback e idempotencia
# --------------------------------------------------------------------------

def test_rollback_restaura_la_matriz_y_los_privilegios_por_defecto(produccion):
    matriz, defecto = _matriz(produccion), _default_acl(produccion)
    produccion.sql(MIGRACION_19.read_text(encoding="utf-8"))
    assert _matriz(produccion) != matriz
    produccion.sql(ROLLBACK_19.read_text(encoding="utf-8"))
    assert _matriz(produccion) == matriz
    assert _default_acl(produccion) == defecto


def test_19_idempotente(base):
    matriz, defecto = _matriz(base), _default_acl(base)
    base.sql(MIGRACION_19.read_text(encoding="utf-8"))
    assert (_matriz(base), _default_acl(base)) == (matriz, defecto)


def test_19_estatico_sin_dml_y_con_todos_los_revokes():
    import re
    sql = re.sub(r"--[^\n]*", "", MIGRACION_19.read_text(encoding="utf-8")).casefold()
    assert re.search(r"^\s*(insert|update|delete|truncate)\b", sql, re.M) is None
    assert "revoke all on function public.cf_validar_factura(uuid, text)" in sql
    assert "alter default privileges for role postgres\n    revoke execute on functions from public;" in sql
    for prohibido in ("cf_historial_append_only", "cf_set_updated_at", "cf_resultado_conciliacion",
                      "rls_auto_enable", "policy", "storage."):
        assert prohibido not in sql
