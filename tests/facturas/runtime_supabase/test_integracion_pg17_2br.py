"""Hito 2BR: migracion 30 (detalle por linea en la conciliacion) en PostgreSQL 17 local.

Plantillas (pg17_local): "29" (estado productivo), "30" = 29 + migracion 30 dos veces, "30_rollback" = 30 + rollback.
Hallazgo de la web: en produccion ``conciliacion_detalles`` guarda los importes por linea en NULL y el estado de la
factura en cada linea. La 30 los calcula por linea (``cf_detalles_por_linea``), rellena los existentes sin cambiar su
resultado y valida lo que trae el codigo 2BR. Caso real 08007969 (PDF del 2AO, fixture local excluido de git) con la
recepcion 50898 del 2BE. Sin produccion ni Farmatic.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import uuid
from decimal import Decimal

import pytest

import pg17_local as pgl
from pg17_local import FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, _lit, base_desde, esquema
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _huella, _preparar_2ao, _solo_primera, contenedor_tcp)
from test_integracion_pg17_2ba import _reservas, _vigente
from test_integracion_pg17_2be import _albaran, _linea_sintetica, _pareja, _persistir, _recepcion_50898
from src.facturas.runtime_supabase.conciliacion import ValoresLinea, valores_por_linea
from src.facturas.runtime_supabase.modelos import DetalleConciliacion, TipoRelacionConciliacion as T
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion

pytestmark = pytest.mark.pg17_local

MIGRACION_30 = MIG / "30_cf_detalle_por_linea.sql"
ROLLBACK_30 = MIG / "30_cf_detalle_por_linea.rollback.sql"
RUTA_30 = "sql/migrations/30_cf_detalle_por_linea.sql"
SCRIPT_30 = ROOT / "pruebas/auditoria_2br/desplegar_30.py"
PERSISTIR = "public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)"
POR_LINEA = "public.cf_detalles_por_linea(uuid,jsonb)"
PREVIO = "public.conciliacion_detalles_previo_30"
SIN_LINEA = ("'importe_documental'", "'importe_farmatic'", "'diferencia'", "'estado'")


def _cargar_despliegue(script=SCRIPT_30):
    spec = importlib.util.spec_from_file_location(f"desplegar_30_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def base30(pg17_nueva_base):
    return pg17_nueva_base("30")


def _detalles(pg, factura_id=None):
    """Detalles (de la conciliacion vigente de la factura, o todos) sin ids generados: comparables entre bases."""
    filtro = (f"join public.conciliaciones c on c.id = d.conciliacion_id and c.es_actual "
              f"and c.factura_id = {_lit(factura_id)}" if factura_id else "")
    return pg.json("select d.orden, d.tipo_relacion, d.albaran_id_contador, d.importe_aplicado::text as aplicado, "
                   "d.importe_documental::text as documental, d.importe_farmatic::text as farmatic, "
                   "d.diferencia::text as diferencia, d.estado from public.conciliacion_detalles d "
                   f"{filtro} order by d.conciliacion_id, d.orden")


def _conciliar(pg, tmp_path, *, recepcion_interno=50898, estado_de_factura=False):
    """08007969 conciliada con el codigo 2BR. ``estado_de_factura``: deja los detalles como los escribia el codigo
    anterior (estado de la factura en cada linea, importes por linea NULL), que es lo que hay en produccion."""
    cliente, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    objetivo = ids["08007969"]
    _recepcion_50898(pg, objetivo, recepcion_interno=recepcion_interno)
    _solo_primera(pg, ids, "08007969")
    worker = construir_worker_conciliacion(RepositorioRuntimeSupabase(cliente), "conc-2br")
    assert worker.ejecutar_una_manual() is True
    if estado_de_factura:
        pg.sql("update public.conciliacion_detalles d set importe_documental = null, importe_farmatic = null, "
               "diferencia = null, estado = case when c.resultado = 'CONCILIADA' then 'COINCIDE' else 'DIFERENCIA' "
               "end from public.conciliaciones c where c.id = d.conciliacion_id;")
    return objetivo


def _huellas(pg):
    huellas = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items() if k != "detalles"}
    huellas["detalles_sin_linea"] = _huella(
        pg, "select to_jsonb(d) - " + " - ".join(SIN_LINEA) + " from public.conciliacion_detalles d")
    return huellas


# --------------------------------------------------------------------------- esquema y privilegios

def test_rollback_30_devuelve_exactamente_el_esquema_29(pg17_nueva_base):
    assert esquema(pg17_nueva_base("30_rollback")) == esquema(pg17_nueva_base("29"))
    assert esquema(pg17_nueva_base("30")) != esquema(pg17_nueva_base("29"))


def test_30_exige_la_29(pg17_nueva_base):
    pg = pg17_nueva_base("28")
    with pytest.raises(RuntimeError, match="MIGRACION_29_AUSENTE"):
        pg.sql(MIGRACION_30.read_text(encoding="utf-8"))


def test_privilegios_de_la_30(base30):
    pg = base30
    for rol, esperado in (("service_role", "t"), ("anon", "f"), ("authenticated", "f"), ("cf_lectura", "f")):
        assert pg.sql(f"select has_function_privilege('{rol}', '{PERSISTIR}', 'EXECUTE')") == esperado
    for rol in ("service_role", "anon", "authenticated", "cf_lectura"):
        assert pg.sql(f"select has_function_privilege('{rol}', '{POR_LINEA}', 'EXECUTE')") == "f"
        assert pg.sql(f"select has_table_privilege('{rol}', '{PREVIO}', 'SELECT,INSERT,UPDATE,DELETE')") == "f"
    assert pg.sql(f"select prosecdef::text || '|' || pg_get_userbyid(proowner) from pg_proc "
                  f"where oid = '{PERSISTIR}'::regprocedure") == "true|postgres"
    assert pg.sql(f"select pg_get_userbyid(proowner) from pg_proc where oid = '{POR_LINEA}'::regprocedure") == \
        "postgres"
    assert pg.sql(f"select relrowsecurity::text || '|' || pg_get_userbyid(relowner) from pg_class "
                  f"where oid = '{PREVIO}'::regclass") == "true|postgres"
    # La web (cf_lectura) lee las columnas nuevas de conciliacion_detalles (29, sin cambios).
    assert pg.sql("select has_column_privilege('cf_lectura', 'public.conciliacion_detalles', 'diferencia', "
                  "'SELECT')") == "t"
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


# --------------------------------------------------------------------------- relleno = conciliar con la 30

@pytest.mark.parametrize("recepcion_interno, resultado", [(50898, "CONCILIADA"), (50899, "DIFERENCIA")])
def test_relleno_equivale_a_conciliar_con_la_30_y_no_cambia_el_resultado(pg17_nueva_base, tmp_path,
                                                                          recepcion_interno, resultado):
    # Produccion: conciliada con la 29 y el codigo anterior (estado de la factura, importes por linea NULL).
    pg = pg17_nueva_base("29")
    objetivo = _conciliar(pg, tmp_path / "a", recepcion_interno=recepcion_interno, estado_de_factura=True)
    previos = _detalles(pg, objetivo)
    assert {(d["estado"], d["documental"], d["farmatic"], d["diferencia"]) for d in previos} == {
        ("COINCIDE" if resultado == "CONCILIADA" else "DIFERENCIA", None, None, None)}
    vigente = _vigente(pg, objetivo)
    antes, reservas = _huellas(pg), _reservas(pg)

    pg.sql(MIGRACION_30.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_30.read_text(encoding="utf-8"))  # idempotente: el relleno no se repite

    assert _huellas(pg) == antes and _reservas(pg) == reservas and _vigente(pg, objetivo) == vigente
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    rellenos = _detalles(pg, objetivo)
    # Referencia: los mismos datos conciliados directamente con la 30 y el codigo 2BR (la BD valida lo que trae).
    ref = pg17_nueva_base("30")
    ref_objetivo = _conciliar(ref, tmp_path / "b", recepcion_interno=recepcion_interno)
    assert rellenos == _detalles(ref, ref_objetivo)
    assert {k: v for k, v in _vigente(ref, ref_objetivo).items() if k != "id"} == \
        {k: v for k, v in vigente.items() if k != "id"}
    assert vigente["resultado"] == resultado

    por_estado = {}
    for d in rellenos:
        por_estado.setdefault(d["estado"], []).append(d)
    if resultado == "CONCILIADA":
        # La linea R17 08C20268 (504,02 = 500,86 + 3,16): misma diferencia y estado en los dos detalles.
        r17 = [d for d in rellenos if d["tipo_relacion"] == "UNO_A_VARIOS"]
        assert [(d["albaran_id_contador"], d["documental"], d["farmatic"], d["diferencia"], d["estado"])
                for d in r17] == [(280005, "504.0200", "500.8600", "0.0000", "COINCIDE"),
                                  (280004, "504.0200", "3.1600", "0.0000", "COINCIDE")]
        assert set(por_estado) <= {"COINCIDE", "NO_EVALUABLE"}
    else:
        # Antes las 128 lineas decian DIFERENCIA; ahora solo la que no casa.
        [linea] = por_estado["DIFERENCIA"]
        assert (linea["tipo_relacion"], linea["documental"], linea["farmatic"], linea["diferencia"]) == (
            "SIN_COINCIDENCIA", "504.0200", None, "504.0200")
        assert len(por_estado["COINCIDE"]) == len(rellenos) - 1 - len(por_estado.get("NO_EVALUABLE", []))
    # NO_EVALUABLE: solo los movimientos documentales (sin contraparte en Farmatic), con su importe del PDF.
    assert all(d["tipo_relacion"] == "MOVIMIENTO_NO_FARMATIC" and d["documental"] == d["aplicado"]
               and d["farmatic"] is None and d["diferencia"] is None for d in por_estado.get("NO_EVALUABLE", []))
    assert all(d["estado"] == "NO_EVALUABLE" for d in rellenos if d["tipo_relacion"] == "MOVIMIENTO_NO_FARMATIC")
    for d in rellenos:
        if d["tipo_relacion"] == "UNO_A_UNO":
            assert Decimal(d["diferencia"]) == Decimal(d["documental"]) - Decimal(d["farmatic"])
    # Los valores previos quedan guardados tal cual para el rollback.
    assert pg.json(f"select p.estado, p.importe_documental, p.importe_farmatic, p.diferencia from {PREVIO} p "
                   "join public.conciliacion_detalles d on d.id = p.detalle_id order by d.orden") == [
        {"estado": d["estado"], "importe_documental": None, "importe_farmatic": None, "diferencia": None}
        for d in previos]


# --------------------------------------------------------------------------- la BD valida lo que trae el codigo

@pytest.fixture
def factura_r17_30(base30, tmp_path):
    pg = base30
    _, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    factura = ids["08007973"]
    linea = _linea_sintetica(pg, factura)
    _albaran(pg, 810001, "08Z00001", "97.00", 7001)
    _albaran(pg, 810002, "Q999001/2026", "3.00", 7001)
    return pg, factura, linea


def _con_valores(detalles, valores):
    return [{**d, "importe_documental": v[0], "importe_farmatic": v[1], "diferencia": v[2], "estado": v[3]}
            for d, v in zip(detalles, valores)]


CORRECTOS = (("100.00", "97.00", "0", "COINCIDE"), ("100.0000", "3.0000", "0.0000", "COINCIDE"))


def test_la_bd_acepta_los_valores_por_linea_correctos(factura_r17_30):
    pg, factura, linea = factura_r17_30
    conciliacion = _persistir(pg, factura, _con_valores(_pareja(linea), CORRECTOS))
    assert pg.json("select importe_documental::text as doc, importe_farmatic::text as farm, diferencia::text as dif, "
                   f"estado from public.conciliacion_detalles where conciliacion_id = {_lit(conciliacion)} "
                   "order by orden") == [{"doc": "100.0000", "farm": "97.0000", "dif": "0.0000", "estado": "COINCIDE"},
                                         {"doc": "100.0000", "farm": "3.0000", "dif": "0.0000", "estado": "COINCIDE"}]


@pytest.mark.parametrize("indice, valores", [
    (0, ("100.00", "97.00", "0", "DIFERENCIA")),   # estado de la factura en vez del de la linea
    (1, ("100.00", "3.00", "97.00", "COINCIDE")),  # diferencia del albaran, no de la linea
    (0, ("97.00", "97.00", "0", "COINCIDE")),      # importe documental equivocado
    (1, ("100.00", None, "0", "COINCIDE")),        # sin importe de Farmatic
    (0, (None, None, None, "COINCIDE")),           # valores vacios declarados
])
def test_la_bd_rechaza_valores_por_linea_que_no_coinciden(factura_r17_30, indice, valores):
    pg, factura, linea = factura_r17_30
    filas = list(CORRECTOS)
    filas[indice] = valores
    with pytest.raises(RuntimeError, match=f"DETALLE_LINEA_NO_COINCIDE:{indice + 1}"):
        _persistir(pg, factura, _con_valores(_pareja(linea), filas))
    assert pg.sql(f"select count(*) from public.conciliaciones where factura_id = {_lit(factura)}") == "0"
    assert _reservas(pg) == []


def test_sin_valores_por_linea_la_bd_los_calcula(factura_r17_30):
    """Codigo anterior contra la 30: estado de la factura en el resultado; la BD guarda los de la linea."""
    pg, factura, linea = factura_r17_30
    conciliacion = _persistir(pg, factura, _pareja(linea))
    assert pg.json("select estado, diferencia::text as dif from public.conciliacion_detalles "
                   f"where conciliacion_id = {_lit(conciliacion)} order by orden") == [
        {"estado": "COINCIDE", "dif": "0.0000"}, {"estado": "COINCIDE", "dif": "0.0000"}]


# --------------------------------------------------------------------------- equivalencia Python = SQL

def test_cf_detalles_por_linea_es_espejo_de_valores_por_linea(base30, tmp_path):
    pg = base30
    _, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    factura = ids["08007969"]
    lineas = [e["id"] for e in pg.json("select id::text from public.facturas_albaranes_extraidos "
                                       f"where factura_id = {_lit(factura)} order by orden, id limit 7")]
    importes = [("100.00", "CARGO"), ("100.00", "CARGO"), ("20.00", "ABONO"), ("504.02", "CARGO"), (None, "CARGO"),
                ("10.00", "CARGO"), ("-7.50", "ABONO")]
    for linea, (importe, tipo) in zip(lineas, importes):
        pg.sql(f"update public.facturas_albaranes_extraidos set importe_total = {importe or 'null'}, "
               f"tipo_movimiento = {_lit(tipo)} where id = {_lit(linea)};")
    otra = pg.json("select id::text from public.facturas_albaranes_extraidos "
                   f"where factura_id = {_lit(ids['08007970'])} limit 1")[0]["id"]

    def alb(tipo, aplicado, linea, contador=None, **kw):
        return DetalleConciliacion(tipo_relacion=tipo, importe_aplicado=Decimal(aplicado), factura_albaran_extraido_id=linea,
                                   albaran_farmacia="PIO" if contador else None, albaran_id_contador=contador, **kw)

    documental = {linea: (None if i is None else (-abs(Decimal(i)) if t == "ABONO" else Decimal(i)))
                  for linea, (i, t) in zip(lineas, importes)}
    documental[otra] = Decimal("5.0000")  # Python cree que la linea es de esta factura; la BD lo comprueba
    detalles = [
        alb(T.UNO_A_UNO, "99.97", lineas[0], 1),                 # COINCIDE (0,03)
        alb(T.UNO_A_UNO, "99.90", lineas[1], 2),                 # DIFERENCIA (0,10)
        alb(T.UNO_A_UNO, "-20.02", lineas[2], 3),                # abono
        alb(T.UNO_A_VARIOS, "500.86", lineas[3], 4),             # R17
        alb(T.UNO_A_VARIOS, "3.16", lineas[3], 5),
        alb(T.SIN_COINCIDENCIA, "0", lineas[4]),                 # sin importe documental
        alb(T.SIN_COINCIDENCIA, "0", lineas[5]),                 # sin coincidencia
        alb(T.UNO_A_UNO, "-7.49", lineas[6], 6),                 # abono con importe negativo en el PDF
        alb(T.UNO_A_UNO, "5.00", otra, 7),                       # linea de otra factura: no evaluable en la BD
        DetalleConciliacion(tipo_relacion=T.MOVIMIENTO_NO_FARMATIC, importe_aplicado=Decimal("31.46"),
                            factura_movimiento_id=str(uuid.uuid4())),
        DetalleConciliacion(tipo_relacion=T.MOVIMIENTO_NO_FARMATIC, importe_aplicado=Decimal("1.20"),
                            provenance={"fuente": "FISCALIDAD_AJUSTE_DOCUMENTAL"}),
    ]
    detalles = [DetalleConciliacion(**{**{s: getattr(d, s) for s in d.__slots__},
                                       "importe_documental": documental.get(d.factura_albaran_extraido_id)})
                for d in detalles]
    entrada = [{"orden": i, "tipo_relacion": d.tipo_relacion.value, "importe_aplicado": str(d.importe_aplicado),
                "factura_albaran_extraido_id": d.factura_albaran_extraido_id}
               for i, d in enumerate(detalles, 1)]
    sql = pg.json(f"select * from public.cf_detalles_por_linea({_lit(factura)}::uuid, "
                  f"{_lit(json.dumps(entrada))}::jsonb) order by orden")

    def dec(v):
        return None if v is None else Decimal(str(v)).quantize(Decimal("0.0001"))

    desde_sql = tuple(ValoresLinea(dec(f["importe_documental"]), dec(f["importe_farmatic"]), dec(f["diferencia"]),
                                   f["estado"]) for f in sql)
    python = valores_por_linea(detalles)
    # La linea de otra factura: Python no sabe de quien es la linea (la BD si) -> la BD la deja NO_EVALUABLE y
    # rechazaria el resultado (DETALLE_LINEA_NO_COINCIDE). El resto, identico.
    assert desde_sql[8] == ValoresLinea(None, Decimal("5.0000"), None, "NO_EVALUABLE")
    assert python[8] == ValoresLinea(Decimal("5.0000"), Decimal("5.0000"), Decimal("0.0000"), "COINCIDE")
    assert desde_sql[:8] + desde_sql[9:] == python[:8] + python[9:]
    assert [v.estado for v in python[:8]] == ["COINCIDE", "DIFERENCIA", "COINCIDE", "COINCIDE", "COINCIDE",
                                              "NO_EVALUABLE", "DIFERENCIA", "COINCIDE"]


# --------------------------------------------------------------------------- rollback exacto

def test_rollback_devuelve_los_valores_previos_y_la_semantica_anterior(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("29")
    objetivo = _conciliar(pg, tmp_path / "a", recepcion_interno=50899, estado_de_factura=True)
    detalles_antes = _huella(pg, "select to_jsonb(d) from public.conciliacion_detalles d")
    pg.sql(MIGRACION_30.read_text(encoding="utf-8"))
    # Una conciliacion persistida despues de la 30 (ruta directa con valores por linea): no tiene valores previos.
    ids = {f["numero_factura"]: f["id"] for f in pg.json("select id::text, numero_factura from public.facturas")}
    linea = _linea_sintetica(pg, ids["08007973"])
    _albaran(pg, 810001, "08Z00001", "97.00", 7001)
    _albaran(pg, 810002, "Q999001/2026", "3.00", 7001)
    nueva = _persistir(pg, ids["08007973"], _con_valores(_pareja(linea), CORRECTOS))
    assert pg.sql("select string_agg(estado, ',' order by orden) from public.conciliacion_detalles "
                  f"where conciliacion_id = {_lit(nueva)}") == "COINCIDE,COINCIDE"

    pg.sql(ROLLBACK_30.read_text(encoding="utf-8"))
    pg.sql(ROLLBACK_30.read_text(encoding="utf-8"))  # idempotente
    assert pg.sql(f"select to_regclass('{PREVIO}') is null and to_regprocedure('{POR_LINEA}') is null") == "t"
    # Los rellenados, exactamente como antes de la 30; los posteriores, con la semantica anterior (resultado de la
    # factura DIFERENCIA, importes por linea NULL).
    assert _huella(pg, "select to_jsonb(d) from public.conciliacion_detalles d "
                       f"where d.conciliacion_id <> {_lit(nueva)}") == detalles_antes
    assert pg.json("select estado, importe_documental, importe_farmatic, diferencia from public.conciliacion_detalles "
                   f"where conciliacion_id = {_lit(nueva)} order by orden") == [
        {"estado": "DIFERENCIA", "importe_documental": None, "importe_farmatic": None, "diferencia": None}] * 2
    assert _vigente(pg, objetivo)["resultado"] == "DIFERENCIA"


# --------------------------------------------------------------------------- desplegar_30.py

@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf2br_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    """Copia byte a byte el script y la migracion a un repositorio git temporal con su commit."""
    for relativa in (RUTA_30, "pruebas/auditoria_2br/desplegar_30.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 30"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_30.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_2br/desplegar_30.py")


def test_sql_de_precondiciones_30_es_de_solo_lectura(pg17_nueva_base):
    despliegue = _cargar_despliegue()
    pg = pg17_nueva_base("29")
    assert pg.sql(f"begin read only; {despliegue.PRECONDICIONES}; rollback;") == "|".join(["t"] * 9)
    # Ya aplicada: «30 ausente» falla (la plantilla no tiene detalles, asi que «importes vacios» se cumple).
    pg30 = pg17_nueva_base("30")
    assert pg30.sql(f"begin read only; {despliegue.PRECONDICIONES}; rollback;").split("|")[:3] == ["t", "f", "t"]


def test_ensayo_completo_despliegue_30_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "29"))
    objetivo = _conciliar(pg, tmp_path / "a", recepcion_interno=50899, estado_de_factura=True)
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
        # Norma 2BN-D: el ensayo se conecta con el rol que imita al postgres de Supabase.
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

    antes, reservas, vigente = _huellas(pg), _reservas(pg), _vigente(pg, objetivo)
    detalles_antes = _huella(pg, "select to_jsonb(d) from public.conciliacion_detalles d")
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 9
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "relleno": True, "valores_previos": True,
                                           "privilegios": True, "propietarios": True}
    assert {(r["tipo_relacion"], r["estado"]) for r in registro["resumen_detalles"]} == {
        ("UNO_A_UNO", "COINCIDE"), ("SIN_COINCIDENCIA", "DIFERENCIA"), ("MOVIMIENTO_NO_FARMATIC", "NO_EVALUABLE")}
    assert _huellas(pg) == antes and _reservas(pg) == reservas and _vigente(pg, objetivo) == vigente
    # Referencia (superusuario postgres, como el propietario en Supabase): mismo esquema salvo el propietario de los
    # dos objetos nuevos, que es el rol que despliega (postgres en Supabase).
    referencia = pgl.base_desde(nombre, pgl.construir_plantilla(nombre, "29"))
    referencia.sql(MIGRACION_30.read_text(encoding="utf-8"))
    assert esquema(pg).replace(pg.db, "").replace(f"OWNER TO {rol_despliegue};", "OWNER TO postgres;").replace(
        f"Owner: {rol_despliegue}", "Owner: postgres") == esquema(referencia).replace(referencia.db, "")
    assert pg.sql("select string_agg(o, ',' order by o) from ("
                  "select oid::regclass::text as o from pg_class where relnamespace = 'public'::regnamespace "
                  f"and relkind in ('r','v','m','S','f','p') and pg_get_userbyid(relowner) = '{rol_despliegue}' "
                  "union all select oid::regprocedure::text from pg_proc where pronamespace = 'public'::regnamespace "
                  f"and pg_get_userbyid(proowner) = '{rol_despliegue}') t") == \
        "cf_detalles_por_linea(uuid,jsonb),conciliacion_detalles_previo_30"
    assert pg.sql(f"select pg_get_userbyid(proowner) from pg_proc where oid = '{PERSISTIR}'::regprocedure") == \
        "postgres"

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: ni «30 ausente» ni «importes por linea vacios»; el resto sigue en verde.
    assert registro["precondiciones"] == [True, False, False, True, True, True, True, True, False]
    assert _huellas(pg) == antes

    # El rollback tambien funciona con la imitacion: esquema 29 y detalles como antes de la 30.
    atras = pgl.sql_como_supabase(pg, ROLLBACK_30.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    limpia = pgl.base_desde(nombre, pgl.construir_plantilla(nombre, "29"))
    assert esquema(pg).replace(pg.db, "") == esquema(limpia).replace(limpia.db, "")
    assert _huella(pg, "select to_jsonb(d) from public.conciliacion_detalles d") == detalles_antes
    assert {(d["estado"], d["documental"]) for d in _detalles(pg, objetivo)} == {("DIFERENCIA", None)}
