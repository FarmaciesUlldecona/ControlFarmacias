"""Hito 2AT rev2: ensayo local COMPLETO de los scripts de la Fase 4 (norma de REGLAS_CRITICAS).

Base equivalente a produccion: cadena 06-18 + rollback de la 19 + 19 dos veces
(matriz y privilegios por defecto productivos, como en 2AX). Datos equivalentes:
PDF real del 2AO normalizado en local; 08007973 (Alliance, 22,49) con sus 2
albaranes y albaranes operacionales con los importes PUC productivos (12,44 y
10,05). Se ejecutan ``auditoria_readonly`` (preflight, snapshot, candidato,
revalidacion, comparar) y ``ejecutar_una_vez.main`` de principio a fin con los
modulos auxiliares apuntando a la base local:

- ``auditoria_readonly._conectar``: conexion sustituta que ejecuta cada sentencia
  por ``docker exec psql`` dentro de una transaccion REPEATABLE READ READ ONLY
  real (limitacion: una transaccion por sentencia, no una por modo);
- ``_tareas``: tareas programadas sinteticas (Ready, sin ejecucion proxima);
- ``dotenv.dotenv_values``: project ref productivo y clave ``sb_secret_`` ficticia;
- ``src.supabase_client.conexion_supabase``: modulo sustituto que devuelve el
  cliente PostgreSQL local con ``service_role`` (no se importa el real ni se lee
  el ``.env``).
Sin produccion ni Farmatic.
"""
from __future__ import annotations

import json
import sys
import types
from decimal import Decimal
from pathlib import Path

import pytest

from pg17_local import (
    FIXTURES, FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, ClientePg17, _Tabla, _lit, _locks, _registrar, _worker,
)

sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
import auditoria_readonly as ar  # noqa: E402
import ejecutar_una_vez as eu  # noqa: E402

from src.facturas.runtime_supabase import compositor_manual as cm  # noqa: E402
from src.facturas.runtime_supabase.extraccion_productiva import OrquestadorExtraccionProductiva  # noqa: E402
from src.facturas.runtime_supabase.worker_normalizacion import WorkerNormalizacion  # noqa: E402


pytestmark = pytest.mark.pg17_local

ALLIANCE_2AO = FIXTURES / "alliance_2ao_cinco_facturas.pdf"
ROLLBACK_19 = MIG / "19_cf_privilegios_minimos.rollback.sql"
MIGRACION_19 = MIG / "19_cf_privilegios_minimos.sql"
PUC_PRODUCTIVO = {"08M26924": ("12.44", "17.95", 280242), "08C23236": ("10.05", "14.30", 280269)}


# --------------------------------------------------------------------------
# Conexion sustituta READ_ONLY sobre docker exec psql
# --------------------------------------------------------------------------

def _interpolar(sql: str, params) -> str:
    if params is None:
        return sql
    if isinstance(params, dict):
        for clave, valor in params.items():
            sql = sql.replace(f"%({clave})s", _lit(valor))
        return sql
    partes = sql.split("%s")
    assert len(partes) == len(params) + 1, sql
    return "".join(p + (_lit(v) if i < len(params) else "") for i, (p, v) in
                   enumerate(zip(partes, [*params, None])))


class _CursorPg17:
    def __init__(self, pg, registro: list[str]):
        self.pg, self.registro, self.prefijo, self.filas = pg, registro, [], []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        texto = _interpolar(sql, params)
        self.registro.append(texto)
        if texto.lstrip().lower().startswith("set local"):
            self.prefijo.append(texto)
            self.filas = []
            return
        # Cada fila como lista JSON en el orden de columnas (json_each conserva duplicados).
        envuelta = (
            "begin transaction isolation level repeatable read read only; "
            + "".join(p + "; " for p in self.prefijo)
            + "select coalesce(json_agg((select json_agg(e.valor order by e.n) from json_each(row_to_json(t)) "
              "with ordinality as e(clave, valor, n))), '[]'::json)::text "
            + f"from ({texto}) t; rollback;")
        self.filas = [tuple(f) for f in json.loads(self.pg.sql(envuelta), parse_float=Decimal)]

    def fetchall(self):
        return self.filas


class _ConexionPg17:
    def __init__(self, pg, registro: list[str]):
        self.pg, self.registro, self.rollbacks, self.cerrada = pg, registro, 0, False

    def cursor(self):
        return _CursorPg17(self.pg, self.registro)

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.cerrada = True


class _TablaBool(_Tabla):
    """``eq('id', True)`` de obtener_configuracion: el harness compara ``col::text``."""

    def eq(self, columna, valor):
        if isinstance(valor, bool):
            self.filtros.append(f"{columna}::text = {_lit(str(valor).lower())}")
            return self
        return super().eq(columna, valor)


class _ClienteServiceRole(ClientePg17):
    def __init__(self, pg):
        super().__init__(pg, rol_tablas="service_role")

    def table(self, tabla):
        return _TablaBool(self.pg, tabla, self.rol_tablas)


# --------------------------------------------------------------------------
# Escenario
# --------------------------------------------------------------------------

@pytest.fixture
def escenario(pg17_nueva_base, tmp_path, monkeypatch):
    if not ALLIANCE_2AO.exists():
        pytest.skip("PDF real del 2AO ausente (excluido de git)")
    pg = pg17_nueva_base("18")
    pg.sql(ROLLBACK_19.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_19.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_19.read_text(encoding="utf-8"))

    preparacion = _ClienteServiceRole(pg)
    _registrar(pg, preparacion, ALLIANCE_2AO.read_bytes(), 1)
    assert _worker(preparacion, tmp_path / "prep", "2at").ejecutar_una_manual().documentos_reclamados == 1
    facturas = {f["numero_factura"]: f["id"] for f in pg.json(
        "select id::text, numero_factura from public.facturas where proveedor_literal ilike 'ALLIANCE%'")}
    objetivo = facturas["08007973"]
    # Orden de produccion: 08007973 es el n.o 1 (alli por id, aqui se fija por fecha de las otras aptas).
    pg.sql("update public.facturas set fecha_factura = date '2026-07-01' where numero_factura in "
           "('08007970', '08007972');")
    for numero, (puc, pvp, contador) in PUC_PRODUCTIVO.items():
        pg.sql(
            "insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
            "importe_pvp,importe_puc,descuento,estado) select 'PIO', "
            f"{contador}, '2', '1.- SAFA', a.numero_albaran, a.fecha_albaran, {pvp}, {puc}, 0, 'PENDIENTE' "
            f"from public.facturas_albaranes_extraidos a where a.factura_id = {_lit(objetivo)} "
            f"and a.numero_albaran = {_lit(numero)};")
    assert pg.sql(f"select count(*) from public.facturas_albaranes_extraidos where factura_id = {_lit(objetivo)}") == "2"

    sentencias: list[str] = []
    conexiones: list[_ConexionPg17] = []

    def conectar():
        conexion = _ConexionPg17(pg, sentencias)
        conexiones.append(conexion)
        return ar.PROJECT_REF, conexion

    tareas = {"tareas": [
        {"nombre": n, "estado": "Ready", "proxima": None, "ultima": None, "resultado": 0}
        for n in ar.TAREAS_ESPERADAS]}
    monkeypatch.setattr(ar, "_conectar", conectar)
    monkeypatch.setattr(ar, "_tareas", lambda: tareas)
    monkeypatch.setattr(eu, "_tareas", lambda: tareas)
    monkeypatch.setattr("dotenv.dotenv_values", lambda *_a, **_k: {
        "SUPABASE_URL": f"https://{ar.PROJECT_REF}.supabase.co", "SUPABASE_KEY": "sb_secret_ensayo_local"})
    clientes: list[_ClienteServiceRole] = []

    def obtener_cliente_supabase():
        cliente = _ClienteServiceRole(pg)
        clientes.append(cliente)
        return cliente

    modulo = types.ModuleType("src.supabase_client.conexion_supabase")
    modulo.obtener_cliente_supabase = obtener_cliente_supabase
    monkeypatch.setitem(sys.modules, "src.supabase_client.conexion_supabase", modulo)

    evidencias = tmp_path / "evidencias_2at"
    evidencias.mkdir()
    rutas = {k: evidencias / f"{k}.json" for k in (
        "preflight", "snapshot_pre", "candidato", "revalidacion", "ejecucion", "ejecucion_2", "snapshot_post")}
    return types.SimpleNamespace(pg=pg, objetivo=objetivo, facturas=facturas, rutas=rutas, evidencias=evidencias,
                                 sentencias=sentencias, conexiones=conexiones, clientes=clientes,
                                 directorio=tmp_path / "tmp_f4")


def _preparar_fase4(e) -> dict:
    """Pasos a), b) y c) de la secuencia: preflight, snapshot_pre y revalidacion."""
    assert ar.preflight(e.rutas["preflight"]) == 0
    assert ar.snapshot(e.rutas["snapshot_pre"]) == 0
    assert ar.candidato(e.rutas["candidato"], None) == 0
    assert ar.candidato(e.rutas["revalidacion"], e.rutas["candidato"]) == 0
    candidato = json.loads(e.rutas["revalidacion"].read_text(encoding="utf-8"))
    assert candidato["candidato_1"]["id"] == e.objetivo
    return candidato


def _ejecutar(e, esperada: str, salida: str = "ejecucion") -> tuple[int | str, dict]:
    try:
        codigo = eu.main(esperada, e.rutas["preflight"], e.rutas["revalidacion"], e.rutas[salida], e.directorio)
    except SystemExit as exc:
        codigo = str(exc)
    return codigo, json.loads(e.rutas[salida].read_text(encoding="utf-8"))


def _claims(pg) -> list[dict]:
    return pg.json("select factura_id::text, actor, detalle from public.historial_facturas "
                   "where evento = 'CONCILIACION_CLAIM' order by id")


def _todas_lecturas(e) -> None:
    assert all(ar._SOLO_LECTURA.match(s) or s.lstrip().lower().startswith("set local") for s in e.sentencias)
    assert all(c.rollbacks == 1 and c.cerrada for c in e.conexiones)


# --------------------------------------------------------------------------
# a) caso normal (+ d) sin normalizacion)
# --------------------------------------------------------------------------

@pytest.fixture
def sin_normalizacion(escenario, monkeypatch):
    """Se activa DESPUES de la normalizacion de preparacion del escenario."""
    llamadas: list[str] = []

    def prohibido(nombre):
        def _f(*_a, **_k):
            llamadas.append(nombre)
            raise AssertionError(f"NORMALIZACION_INVOCADA: {nombre}")
        return _f

    for clase, metodo in ((WorkerNormalizacion, "ejecutar_una"), (WorkerNormalizacion, "ejecutar_una_manual_one_shot"),
                          (WorkerNormalizacion, "_procesar_documento"), (cm.MaterializadorStoragePrivado, "__call__"),
                          (cm.ExtractorDocumentalAutorizado, "extraer"), (OrquestadorExtraccionProductiva, "extraer")):
        monkeypatch.setattr(clase, metodo, prohibido(f"{clase.__name__}.{metodo}"))
    return llamadas


def test_a_caso_normal_una_llamada_conciliada(escenario, sin_normalizacion):
    e = escenario
    pg = e.pg
    candidato = _preparar_fase4(e)
    simulacion = candidato["simulacion"]
    assert (simulacion["resultado"], simulacion["diferencia"]) == ("CONCILIADA", "0.0000")
    documentos_antes = pg.sql("select md5(string_agg(to_jsonb(d)::text, '|' order by id)) from public.documentos_facturas d")
    ejecuciones_antes = pg.sql("select count(*) from public.normalizacion_ejecuciones")

    codigo, registro = _ejecutar(e, e.objetivo)

    assert codigo == 0
    assert (registro["resultado"], registro["invocaciones"]) == ("RETORNO", 1)
    assert registro["revalidacion"]["ok"] is True
    assert registro["cliente"] == {"project_ref": ar.PROJECT_REF, "rol_clave": "service_role"}
    assert registro["retorno"] == {"documentos_reclamados": 0, "facturas_conciliacion_reclamadas": 1,
                                   "automatismos_habilitados": False, "modo_ejecucion": "MANUAL_ONE_SHOT"}
    guard = e.evidencias / eu.NOMBRE_GUARD
    assert guard.exists() and e.objetivo in guard.read_text(encoding="utf-8")
    assert registro["directorio_temporal_borrado"] is True
    assert registro["estado_posterior_readonly"]["factura"]["estado_conciliacion_cf"] == "CONCILIADA"
    assert registro["estado_posterior_readonly"]["claims_conciliacion"] == 0

    [c] = pg.json("select factura_id::text, disparador, estado, es_actual, resultado, importe_factura::text, "
                  "importe_explicado::text, diferencia::text, worker_id, idempotency_key, "
                  "provenance->>'modo_ejecucion' as modo, id::text from public.conciliaciones")
    assert c["factura_id"] == e.objetivo
    assert (c["disparador"], c["modo"], c["estado"], c["es_actual"]) == (
        "MANUAL_ONE_SHOT", "MANUAL_ONE_SHOT", "COMPLETADA", True)
    assert (c["resultado"], c["importe_factura"], c["importe_explicado"], c["diferencia"]) == (
        "CONCILIADA", "22.4900", "22.4900", "0.0000")
    assert c["worker_id"] == eu.WORKER_ID
    assert c["idempotency_key"] == simulacion["idempotency_key_prevista"]  # simulacion == realidad
    detalles = pg.json("select tipo_relacion, albaran_id_contador, coincidencia_numero_literal, "
                       "importe_aplicado::text, estado from public.conciliacion_detalles "
                       f"where conciliacion_id = {_lit(c['id'])} order by orden")
    assert detalles == [
        {"tipo_relacion": "UNO_A_UNO", "albaran_id_contador": 280242, "coincidencia_numero_literal": True,
         "importe_aplicado": "12.4400", "estado": "COINCIDE"},
        {"tipo_relacion": "UNO_A_UNO", "albaran_id_contador": 280269, "coincidencia_numero_literal": True,
         "importe_aplicado": "10.0500", "estado": "COINCIDE"}]
    [f] = pg.json("select estado_conciliacion_cf, conciliacion_bloqueado_por, conciliacion_bloqueado_hasta, "
                  f"conciliacion_intentos_fallo from public.facturas where id = {_lit(e.objetivo)}")
    assert f == {"estado_conciliacion_cf": "CONCILIADA", "conciliacion_bloqueado_por": None,
                 "conciliacion_bloqueado_hasta": None, "conciliacion_intentos_fallo": 0}
    assert [(x["factura_id"], x["actor"], x["detalle"]["modo_ejecucion"]) for x in _claims(pg)] == [
        (e.objetivo, eu.WORKER_ID, "MANUAL_ONE_SHOT")]
    assert _locks(pg) == "0|0" and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS

    # d) ninguna pieza de normalizacion: ni worker, ni materializador, ni extractores, ni documentos.
    assert sin_normalizacion == []
    [cliente] = e.clientes
    assert [n for n, _ in cliente.rpcs] == ["cf_reclamar_factura_conciliacion_manual_one_shot",
                                            "cf_persistir_conciliacion"]
    assert cliente.descargas == []
    assert pg.sql("select md5(string_agg(to_jsonb(d)::text, '|' order by id)) "
                  "from public.documentos_facturas d") == documentos_antes
    assert pg.sql("select count(*) from public.normalizacion_ejecuciones") == ejecuciones_antes

    # e) y f): snapshot posterior y postcheck.
    assert ar.snapshot(e.rutas["snapshot_post"]) == 0
    assert ar.comparar(e.rutas["snapshot_pre"], e.rutas["snapshot_post"], e.objetivo) == 0
    _todas_lecturas(e)


# --------------------------------------------------------------------------
# b) segunda ejecucion con el guard presente
# --------------------------------------------------------------------------

def test_b_segunda_ejecucion_con_guard_no_llama(escenario, sin_normalizacion):
    e = escenario
    _preparar_fase4(e)
    assert _ejecutar(e, e.objetivo)[0] == 0
    conciliaciones = e.pg.sql("select count(*) from public.conciliaciones")

    codigo, registro = _ejecutar(e, e.objetivo, "ejecucion_2")

    assert "GUARD_EXISTENTE" in codigo
    assert (registro["resultado"], registro["invocaciones"]) == ("NO_EJECUTADO_GUARD_EXISTENTE", 0)
    assert "revalidacion" not in registro and len(e.clientes) == 1
    assert len(_claims(e.pg)) == 1
    assert e.pg.sql("select count(*) from public.conciliaciones") == conciliaciones == "1"
    assert sin_normalizacion == []


# --------------------------------------------------------------------------
# c) candidato n.o 1 distinto del esperado
# --------------------------------------------------------------------------

def _sin_llamada(e, codigo, registro) -> None:
    assert "REVALIDACION_FALLIDA" in codigo
    assert (registro["resultado"], registro["invocaciones"]) == ("NO_EJECUTADO_REVALIDACION_FALLIDA", 0)
    assert registro["revalidacion"]["ok"] is False
    assert not (e.evidencias / eu.NOMBRE_GUARD).exists()
    assert e.clientes == [] and _claims(e.pg) == []
    assert e.pg.sql("select count(*) from public.conciliaciones") == "0"
    assert _locks(e.pg) == "0|0"


def test_c_factura_esperada_distinta_del_numero_1(escenario):
    e = escenario
    candidato = _preparar_fase4(e)
    segunda = candidato["elegibles"][1]["id"]
    assert segunda != e.objetivo

    codigo, registro = _ejecutar(e, segunda)

    assert registro["revalidacion"]["inmediata"]["selector_primero"] == e.objetivo
    _sin_llamada(e, codigo, registro)


def test_c_numero_1_cambia_tras_la_revalidacion(escenario):
    e = escenario
    candidato = _preparar_fase4(e)
    segunda = candidato["elegibles"][1]["id"]
    # Un reintento solicitado adelanta a otra factura en el ordering oficial.
    e.pg.sql(f"select public.cf_solicitar_reintento_conciliacion({_lit(segunda)}::uuid, 'ensayo-2at');")

    codigo, registro = _ejecutar(e, e.objetivo)

    assert registro["revalidacion"]["inmediata"]["selector_primero"] == segunda
    _sin_llamada(e, codigo, registro)
