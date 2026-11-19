"""R20 (DECISION DE PIO, 2026-11-19): migracion 36 en PostgreSQL 17 local.

Plantillas (pg17_local): "35" (estado productivo), "36" = 35 + migracion 36 dos veces, "36_rollback" = 36 + rollback.
Se comprueba:
- rollback exacto al esquema 35; la 36 exige la 35; ACL de la auxiliar sin cambios; columna marca true por defecto;
  ningun dato cambia;
- la BD acepta la pareja R20 (exacto + letra final) y rechaza las variantes, incluida la fecha fuera de +-15 dias;
  R17 sigue aceptandose;
- caso 08007969 del 2AO con el segundo albaran de la recepcion convertido en la variante 08C20268A: con la 36 el worker
  persiste CONCILIADA con la linea R20 y las dos reservas; sin la 36, o con la marca a false, la noche lo deja para
  revisar sin reclamar ni gastar intentos (DIFERENCIA, R20 desactivada); el simulador 2AT cuenta la linea R20;
- desplegar_36.py ensayado con el rol que imita al postgres de Supabase (norma 2BN-D), segundo intento revertido y
  rollback con la imitacion.
Reutiliza el escenario del 2BE: ``base24`` se sobrescribe aqui para que sus fixtures usen la plantilla indicada.
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
import test_integracion_pg17_2be as t2be
from pg17_local import FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, _lit, base_desde, esquema
from test_ensayo_fase4_2at import _ConexionPg17
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _datos_previos, _huella, contenedor_tcp)
from test_integracion_pg17_2ba import _reservas, _vigente
from test_integracion_pg17_2be import _albaran, _linea_sintetica, _pareja, _persistir, factura_r17  # noqa: F401
from src.facturas.runtime_supabase import noche_automatica as na
from src.facturas.runtime_supabase.lectura_readonly import LectorReadOnly, r20_habilitada
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase

pytestmark = pytest.mark.pg17_local

MIGRACION_36 = MIG / "36_cf_r20_letra_final.sql"
ROLLBACK_36 = MIG / "36_cf_r20_letra_final.rollback.sql"
RUTA_36 = "sql/migrations/36_cf_r20_letra_final.sql"
SCRIPT_36 = ROOT / "pruebas/auditoria_r20/desplegar_36.py"
AUXILIAR = "public.cf_linea_r17_valida(uuid,text,jsonb,jsonb)"
PERSISTIR = "public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)"

@pytest.fixture
def base24(pg17_nueva_base):
    """Sobrescribe el fixture del 2BE: su escenario (``factura_r17``) se monta sobre la plantilla 36."""
    return pg17_nueva_base("36")


def _lector(pg) -> LectorReadOnly:
    return LectorReadOnly(_ConexionPg17(pg, []).cursor())


# --------------------------------------------------------------------------- esquema, datos y privilegios

def test_rollback_36_devuelve_exactamente_el_esquema_35(pg17_nueva_base):
    assert esquema(pg17_nueva_base("36_rollback")) == esquema(pg17_nueva_base("35"))
    assert esquema(pg17_nueva_base("36")) != esquema(pg17_nueva_base("35"))


def test_36_exige_la_35(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_35_AUSENTE"):
        pg17_nueva_base("34").sql(MIGRACION_36.read_text(encoding="utf-8"))


def test_36_no_altera_datos_y_solo_anade_la_marca(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("35")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    reservas = _reservas(pg)
    config = _huella(pg, "select to_jsonb(c) from public.cf_configuracion c")
    acl = pg.sql(f"select coalesce(proacl::text, '') || pg_get_userbyid(proowner) from pg_proc "
                 f"where oid = '{AUXILIAR}'::regprocedure")
    persistir = pg.sql(f"select md5(prosrc || coalesce(proacl::text, '')) from pg_proc where oid = '{PERSISTIR}'::regprocedure")
    pg.sql(MIGRACION_36.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_36.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert _reservas(pg) == reservas
    assert _huella(pg, "select to_jsonb(c) - 'conciliacion_r20' from public.cf_configuracion c") == config
    assert pg.sql("select conciliacion_r20 from public.cf_configuracion where id") == "t"
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert pg.sql(f"select coalesce(proacl::text, '') || pg_get_userbyid(proowner) from pg_proc "
                  f"where oid = '{AUXILIAR}'::regprocedure") == acl
    assert pg.sql(f"select md5(prosrc || coalesce(proacl::text, '')) from pg_proc "
                  f"where oid = '{PERSISTIR}'::regprocedure") == persistir
    assert esquema(pg) == esquema(pg17_nueva_base("36"))


def test_privilegios_de_la_auxiliar_tras_la_36(pg17_nueva_base):
    pg = pg17_nueva_base("36")
    for rol in ("anon", "authenticated"):
        assert pg.sql(f"select has_function_privilege('{rol}', '{AUXILIAR}', 'EXECUTE')") == "f"
    assert pg.sql(f"select count(*) from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, "
                  f"acldefault('f', p.proowner))) a where p.oid = '{AUXILIAR}'::regprocedure "
                  "and a.grantee <> p.proowner") == "0"


def test_deteccion_de_la_36_sin_abortar_la_lectura(pg17_nueva_base):
    assert r20_habilitada(_lector(pg17_nueva_base("35"))) is False
    pg = pg17_nueva_base("36")
    assert r20_habilitada(_lector(pg)) is True
    pg.sql("update public.cf_configuracion set conciliacion_r20 = false where id;")
    assert r20_habilitada(_lector(pg)) is False
    assert r20_habilitada(_lector(pg17_nueva_base("36_rollback"))) is False


# --------------------------------------------------------------------------- la BD revalida R20

def _r20(factura_r17):
    pg, factura, linea, ids = factura_r17
    pg.sql(f"update public.facturas_albaranes_extraidos set fecha_albaran = date '2026-06-25' where id = {_lit(linea)};")
    _albaran(pg, 810003, "08Z00001A", "3.00", 7001)
    return pg, factura, linea, ids


def test_la_bd_acepta_la_pareja_r20_y_reserva_ambos(factura_r17):
    pg, factura, linea, _ = _r20(factura_r17)
    _persistir(pg, factura, _pareja(linea, b=(810003, "3.00")))
    assert {r["albaran_id_contador"]: r["factura_id"] for r in _reservas(pg)} == {810001: factura, 810003: factura}


def test_r17_se_sigue_aceptando_tras_la_36(factura_r17):
    pg, factura, linea, _ = _r20(factura_r17)
    _persistir(pg, factura, _pareja(linea))
    assert sorted(r["albaran_id_contador"] for r in _reservas(pg)) == [810001, 810002]


@pytest.mark.parametrize("caso", ["otra_recepcion", "sin_recepcion", "otro_proveedor", "suma_fuera",
                                  "importe_no_es_el_puc", "a_fuera_de_ventana", "b_fuera_de_ventana",
                                  "linea_sin_fecha", "dos_exactos", "dos_variantes", "variante_de_otro_numero",
                                  "abono", "otra_factura", "un_detalle"])
def test_la_bd_rechaza_parejas_que_no_son_r20(factura_r17, caso):
    pg, factura, linea, ids = _r20(factura_r17)
    detalles = _pareja(linea, b=(810003, "3.00"))
    if caso == "otra_recepcion":
        pg.sql("update public.albaranes set id_recepcion = 7002 where id_contador = 810003;")
    elif caso == "sin_recepcion":
        pg.sql("update public.albaranes set id_recepcion = null where id_contador in (810001, 810003);")
    elif caso == "otro_proveedor":
        pg.sql("update public.albaranes set id_proveedor = '52' where id_contador = 810003;")
    elif caso == "suma_fuera":
        pg.sql("update public.albaranes set importe_puc = 3.06 where id_contador = 810003;")
        detalles = _pareja(linea, b=(810003, "3.06"))
    elif caso == "importe_no_es_el_puc":
        detalles = _pareja(linea, a=(810001, "97.01"), b=(810003, "3.00"))
    elif caso == "a_fuera_de_ventana":
        pg.sql("update public.albaranes set fecha = date '2026-07-11' where id_contador = 810001;")
    elif caso == "b_fuera_de_ventana":
        pg.sql("update public.albaranes set fecha = date '2026-06-09' where id_contador = 810003;")
    elif caso == "linea_sin_fecha":
        pg.sql(f"update public.facturas_albaranes_extraidos set fecha_albaran = null where id = {_lit(linea)};")
    elif caso == "dos_exactos":
        _albaran(pg, 810004, "08Z00001", "3.00", 7001, id_proveedor="0002")  # R9: el mismo proveedor
        detalles = _pareja(linea, b=(810004, "3.00"))
    elif caso == "dos_variantes":
        _albaran(pg, 810004, "08Z00001B", "97.00", 7001)
        detalles = _pareja(linea, a=(810004, "97.00"), b=(810003, "3.00"))
    elif caso == "variante_de_otro_numero":
        _albaran(pg, 810004, "08Z00002A", "3.00", 7001)
        detalles = _pareja(linea, b=(810004, "3.00"))
    elif caso == "abono":
        pg.sql(f"update public.facturas_albaranes_extraidos set tipo_movimiento = 'ABONO' where id = {_lit(linea)};")
    elif caso == "otra_factura":
        otra = _linea_sintetica(pg, ids["08007972"])
        pg.sql(f"update public.facturas_albaranes_extraidos set fecha_albaran = date '2026-06-25' where id = {_lit(otra)};")
        detalles = _pareja(otra, b=(810003, "3.00"))
    elif caso == "un_detalle":
        detalles = detalles[:1]
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items() if k not in ("facturas", "historial")}
    with pytest.raises(RuntimeError, match="LINEA_R17_NO_VALIDA|conciliacion_detalles_origen_check"):
        _persistir(pg, factura, detalles)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items() if k not in ("facturas", "historial")} == antes
    assert _reservas(pg) == []


def test_dentro_de_la_ventana_de_15_dias_la_bd_acepta(factura_r17):
    pg, factura, linea, _ = _r20(factura_r17)
    pg.sql("update public.albaranes set fecha = date '2026-07-10' where id_contador = 810001;"
           "update public.albaranes set fecha = date '2026-06-10' where id_contador = 810003;")
    _persistir(pg, factura, _pareja(linea, b=(810003, "3.00")))
    assert sorted(r["albaran_id_contador"] for r in _reservas(pg)) == [810001, 810003]


# --------------------------------------------------------------------------- 08007969 con la variante (worker y noche)

def _variante_en_la_recepcion(monkeypatch):
    """El segundo albaran de la recepcion 50898 (3,16) pasa a ser la variante 08C20268A: ya no es R17 sino R20."""
    original = t2be._recepcion_50898

    def recepcion(pg, factura_id, **kwargs):
        original(pg, factura_id, **kwargs)
        pg.sql("update public.albaranes set numero_albaran = '08C20268A' where id_contador = 280004;")

    monkeypatch.setattr(t2be, "_recepcion_50898", recepcion)


def _repositorio_con_deteccion(monkeypatch, registro):
    """El worker del 2BE con la deteccion de la noche (sesion de solo lectura e information_schema)."""

    def construir(cliente):
        pg = cliente.pg
        registro["pg"] = pg
        return RepositorioRuntimeSupabase(cliente, r20_habilitada=lambda: r20_habilitada(_lector(pg)))

    monkeypatch.setattr(t2be, "RepositorioRuntimeSupabase", construir)


def test_08007969_con_la_variante_concilia_por_r20_con_la_36(pg17_nueva_base, tmp_path, monkeypatch):
    _variante_en_la_recepcion(monkeypatch)
    _repositorio_con_deteccion(monkeypatch, {})
    pg = pg17_nueva_base("36")
    objetivo = t2be._conciliar_08007969(pg, tmp_path)
    c = _vigente(pg, objetivo)
    assert (c["resultado"], c["diferencia"], c["casados"]) == ("CONCILIADA", "0.0700", 127)
    detalles = pg.json("select albaran_id_contador, importe_aplicado::text as importe, provenance->>'regla' as regla, "
                       "provenance->>'papel_r20' as papel from public.conciliacion_detalles "
                       f"where conciliacion_id = {_lit(c['id'])} and tipo_relacion = 'UNO_A_VARIOS' order by orden")
    assert [(d["albaran_id_contador"], d["importe"], d["regla"], d["papel"]) for d in detalles] == [
        (280005, "500.8600", "R20", "NUMERO"), (280004, "3.1600", "R20", "LETRA_FINAL")]
    reservas = {r["albaran_id_contador"]: r["factura_id"] for r in _reservas(pg)}
    assert reservas[280005] == objetivo and reservas[280004] == objetivo


class _NocheSinReclamar:
    """Sustituye al worker: hace lo que la noche antes de reclamar (simulacion del n.o 1) y no reclama nada."""

    def __init__(self, registro):
        self.registro = registro

    def ejecutar_una_manual(self):
        pg = self.registro["pg"]
        factura, simulacion, motivo = na._n1_conciliacion(_lector(pg), "MANUAL_ONE_SHOT")
        self.registro.update(factura=factura, simulacion=simulacion, motivo=motivo)
        sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
        import auditoria_readonly as ar

        self.registro["simulador_2at"] = ar._simular(ar._Lector(_ConexionPg17(pg, []).cursor()), factura)
        return False


@pytest.mark.parametrize("plantilla, marca, motivo, lineas_r20", [
    ("35", None, "DIFERENCIA", 0),       # sin la 36: R20 desactivada, para revisar
    ("36", False, "DIFERENCIA", 0),      # con la 36 y la marca a false: igual, sin rollback
    ("36", True, None, 1),               # con la 36: el n.o 1 simula CONCILIADA y la noche lo reclamaria
])
def test_la_noche_sin_la_36_lo_deja_para_revisar_sin_gastar_intentos(pg17_nueva_base, tmp_path, monkeypatch,
                                                                     plantilla, marca, motivo, lineas_r20):
    _variante_en_la_recepcion(monkeypatch)
    registro: dict = {}
    _repositorio_con_deteccion(monkeypatch, registro)
    monkeypatch.setattr(t2be, "construir_worker_conciliacion", lambda repositorio, _id: _NocheSinReclamar(registro))
    pg = pg17_nueva_base(plantilla)
    if marca is not None:
        pg.sql(f"update public.cf_configuracion set conciliacion_r20 = {str(marca).lower()} where id;")
    objetivo = t2be._conciliar_08007969(pg, tmp_path, persiste=False)
    assert registro["factura"] == objetivo and registro["motivo"] == motivo
    esperado = ("DIFERENCIA", "504.0900") if motivo else ("CONCILIADA", "0.0700")
    assert (registro["simulacion"]["resultado"], registro["simulacion"]["diferencia"]) == esperado
    assert registro["simulador_2at"]["resumen_detalles"]["lineas_r20"] == lineas_r20
    assert registro["simulador_2at"]["resumen_detalles"]["lineas_r17"] == 0
    # Nada reclamado ni escrito: sin conciliaciones, sin reservas, sin intentos ni fallos.
    assert pg.sql(f"select count(*) from public.conciliaciones where factura_id = {_lit(objetivo)}") == "0"
    assert pg.sql("select conciliacion_intentos || '|' || coalesce(conciliacion_intentos_fallo, 0) || '|' "
                  "|| estado_conciliacion_cf || '|' || (conciliacion_bloqueado_por is null) "
                  f"from public.facturas where id = {_lit(objetivo)}") == "0|0|PENDIENTE_CONCILIAR|true"


# --------------------------------------------------------------------------- despliegue

def _cargar_despliegue(script=SCRIPT_36):
    spec = importlib.util.spec_from_file_location(f"desplegar_36_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar_despliegue()


def test_sql_de_precondiciones_36_es_de_solo_lectura(pg17_nueva_base):
    pg = pg17_nueva_base("35")
    texto = DESPLIEGUE.PRECONDICIONES.lower()
    assert texto.lstrip().startswith("select") and not any(
        p in texto for p in (" insert ", " update ", " delete ", " alter ", " create ", " drop ", " grant "))
    assert pg.sql(DESPLIEGUE.PRECONDICIONES) == "|".join(["t"] * 5)


def test_postcondiciones_en_la_plantilla_36(pg17_nueva_base):
    pg = pg17_nueva_base("36")
    assert pg.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[-2:] == ["t", "t"]


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf36_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    for relativa in (RUTA_36, "pruebas/auditoria_r20/desplegar_36.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 36"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_36.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_r20/desplegar_36.py")


def test_ensayo_completo_despliegue_36_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "35"))
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

    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    esquema_35 = esquema(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 5
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "columna_marca": True, "auxiliar_r17_r20": True}
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "35"))
    referencia.sql(MIGRACION_36.read_text(encoding="utf-8"))
    assert esquema(pg).replace(pg.db, "") == esquema(referencia).replace(referencia.db, "")

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    assert registro["precondiciones"] == [False, True, True, True, True]

    atras = pgl.sql_como_supabase(pg, ROLLBACK_36.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    assert esquema(pg).replace(pg.db, "") == esquema_35.replace(pg.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_36
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_36_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
