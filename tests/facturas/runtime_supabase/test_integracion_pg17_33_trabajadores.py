"""Hito TRAB-33: migracion 33 (ajustes de Trabajadores) en PostgreSQL 17 local.

Plantillas (pg17_local): "32" (estado productivo), "33" = 32 + migracion 33 dos veces, "33_rollback" = 33 + rollback.
Diseno: pruebas/auditoria_trab/DISENO_33.md. Se comprueba:
- eventos_calendario.anulado: unicidad (trabajadora, fecha, franja) solo entre no anulados, ON CONFLICT de la web con
  WHERE NOT anulado, anulacion con historial (tambien de una trabajadora ya de baja), vista con el campo;
- convenio_anual.vacaciones_dias_naturales: 30 en 2026-2028 (filas existentes), con fuente y autor en el historial;
- trabajadoras_ajustes_anuales: dominios, unica por (trabajadora, ano) entre no anuladas, RLS por farmacia del modulo,
  escritura de la web sin DELETE ni TRUNCATE, autor obligatorio, historial, lectura de cf_lectura y ningun privilegio
  para anon, authenticated ni el rol del sistema;
- rollback exacto al esquema 32 (y falla cerrado con eventos anulados duplicados);
- desplegar_33.py ensayado con el rol que imita al postgres de Supabase (norma 2BN-D), segundo intento revertido y
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
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _datos_previos, _huella, contenedor_tcp)
from test_integracion_pg17_31_trabajadores import RELLENO, _como, _evento, _trabajadora, _web

pytestmark = pytest.mark.pg17_local

MIGRACION_33 = MIG / "33_cf_trabajadores_ajustes.sql"
ROLLBACK_33 = MIG / "33_cf_trabajadores_ajustes.rollback.sql"
RUTA_33 = "sql/migrations/33_cf_trabajadores_ajustes.sql"
SCRIPT_33 = ROOT / "pruebas/auditoria_trab/desplegar_33.py"
ROL = "cf_trabajadores_web"
TABLA = "trabajadoras_ajustes_anuales"
# ON CONFLICT que debe usar la web desde la 33 (el indice unico es parcial: la inferencia exige su predicado).
ON_CONFLICT_EVENTOS = "on conflict (trabajadora_id, fecha, franja) where not anulado do nothing"


def _cargar_despliegue(script=SCRIPT_33):
    spec = importlib.util.spec_from_file_location(f"desplegar_33_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar_despliegue()


def _ajuste(pg, trabajadora, anio=2027, extra="2.5", farmacia="PIO", nota=None, autor="Marc") -> str:
    return _web(pg, f"insert into public.{TABLA} (trabajadora_id, farmacia, anio, vacaciones_dias_extra, nota) "
                    f"values ({_lit(trabajadora)}, {_lit(farmacia)}, {anio}, {extra}, {_lit(nota)}) returning id",
                autor=autor)


@pytest.fixture
def pg33(pg17_nueva_base):
    return pg17_nueva_base("33")


# --------------------------------------------------------------------------- migracion y rollback

def test_rollback_33_devuelve_el_esquema_32(pg17_nueva_base):
    atras = pg17_nueva_base("33_rollback")
    assert esquema(atras) == esquema(pg17_nueva_base("32"))
    assert atras.sql(f"select to_regclass('public.{TABLA}') is null") == "t"


def test_33_exige_la_32(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_32_AUSENTE"):
        pg17_nueva_base("31").sql(MIGRACION_33.read_text(encoding="utf-8"))


def test_33_idempotente_sin_cambiar_datos_ni_flags(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("32")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    configuracion = pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id")
    referencia = esquema(pg17_nueva_base("33"))
    pg.sql(MIGRACION_33.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_33.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id") == configuracion
    assert esquema(pg) == referencia and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_33_conserva_los_eventos_existentes_como_no_anulados(pg17_nueva_base):
    pg = pg17_nueva_base("32")
    t = _trabajadora(pg)
    _evento(pg, t, tipo="VACACIONES")
    pg.sql(MIGRACION_33.read_text(encoding="utf-8"))
    assert pg.sql("select tipo || '|' || anulado from public.eventos_calendario") == "VACACIONES|false"


def test_rollback_falla_cerrado_con_eventos_anulados_duplicados(pg33):
    t = _trabajadora(pg33)
    e = _evento(pg33, t)
    _web(pg33, f"update public.eventos_calendario set anulado = true where id = {_lit(e)}")
    _evento(pg33, t)
    with pytest.raises(RuntimeError, match="ROLLBACK_33_EVENTOS_ANULADOS_DUPLICADOS"):
        pg33.sql(ROLLBACK_33.read_text(encoding="utf-8"))
    assert pg33.sql("select count(*) from public.eventos_calendario") == "2"
    assert pg33.sql(f"select to_regclass('public.{TABLA}') is not null") == "t"


# --------------------------------------------------------------------------- 1. eventos anulados

def test_unicidad_solo_entre_no_anulados_y_on_conflict_de_la_web(pg33):
    t = _trabajadora(pg33)
    e = _evento(pg33, t, tipo="VACACIONES")
    with pytest.raises(RuntimeError, match="eventos_calendario_unico"):
        _evento(pg33, t)
    assert _evento(pg33, t, extra=ON_CONFLICT_EVENTOS) == ""
    # Sin el predicado no hay indice que inferir: la web debe usar el ON CONFLICT nuevo.
    with pytest.raises(RuntimeError, match="no unique or exclusion constraint matching"):
        _evento(pg33, t, extra="on conflict (trabajadora_id, fecha, franja) do nothing")
    _web(pg33, f"update public.eventos_calendario set anulado = true where id = {_lit(e)}")
    nuevo = _evento(pg33, t, tipo="JORNADA", extra=ON_CONFLICT_EVENTOS)
    assert nuevo != ""
    assert pg33.sql("select string_agg(tipo || ':' || anulado, ',' order by anulado) "
                    "from public.eventos_calendario") == "JORNADA:false,VACACIONES:true"
    # Un segundo anulado en la misma franja tambien se admite.
    _web(pg33, f"update public.eventos_calendario set anulado = true where id = {_lit(nuevo)}")
    _evento(pg33, t)
    assert pg33.sql("select count(*) from public.eventos_calendario") == "3"


def test_anulacion_con_historial_y_la_vista_no_suma_anulados(pg33):
    """Decision de Pio (2026-11-14): un evento anulado nunca suma horas."""
    t = _trabajadora(pg33)
    e = _evento(pg33, t)
    _evento(pg33, t, franja="TARDE")
    horas = "select coalesce(sum(horas_efectivas), 0) || '|' || count(*) from public.v_eventos_calendario_horas"
    assert _web(pg33, horas) == "8.00|2"
    _web(pg33, f"update public.eventos_calendario set anulado = true where id = {_lit(e)}", autor="Pio")
    assert pg33.sql("select operacion || '|' || autor || '|' || (antes->>'anulado') || '>' || (despues->>'anulado') "
                    "from public.trabajadores_historial where tabla = 'eventos_calendario' and operacion = 'UPDATE'") \
        == "UPDATE|Pio|false>true"
    assert _web(pg33, horas) == "3.50|1"
    # Un nuevo evento vigente en la franja anulada vuelve a sumar; el anulado sigue sin sumar.
    _evento(pg33, t, tipo="PERMISO_MEDICO", horas=1.5, extra=ON_CONFLICT_EVENTOS)
    assert _web(pg33, horas) == "5.00|2"
    # Mismas columnas que en la 31.
    assert pg33.sql("select string_agg(column_name, ',' order by ordinal_position) from information_schema.columns "
                    "where table_schema = 'public' and table_name = 'v_eventos_calendario_horas'") == \
        "id,trabajadora_id,farmacia,fecha,franja,tipo,estado,horas,nota,horas_efectivas"


def test_anular_evento_de_trabajadora_de_baja_o_anulada(pg33):
    t = _trabajadora(pg33, alta="2027-01-01")
    e = _evento(pg33, t, fecha="2027-03-01")
    _web(pg33, f"update public.trabajadoras set fecha_baja = '2027-02-28' where id = {_lit(t)}")
    # Fuera del alta: no se puede cambiar a otro tipo, pero si anular.
    with pytest.raises(RuntimeError, match="EVENTO_FUERA_DEL_ALTA"):
        _web(pg33, f"update public.eventos_calendario set tipo = 'BAJA' where id = {_lit(e)}")
    _web(pg33, f"update public.eventos_calendario set anulado = true where id = {_lit(e)}")
    # Y crear eventos fuera del alta sigue prohibido (salvo ya anulados).
    with pytest.raises(RuntimeError, match="EVENTO_FUERA_DEL_ALTA"):
        _evento(pg33, t, fecha="2027-03-02")
    assert pg33.sql("select anulado from public.eventos_calendario") == "t"


def test_relleno_con_el_on_conflict_nuevo_no_pisa_y_rellena_lo_anulado(pg33):
    t = _trabajadora(pg33, alta="2027-01-01")
    vac = _evento(pg33, t, fecha="2027-01-04", franja="MANANA", tipo="VACACIONES")
    anulado = _evento(pg33, t, fecha="2027-01-05", franja="MANANA", tipo="VACACIONES")
    _web(pg33, f"update public.eventos_calendario set anulado = true where id = {_lit(anulado)}")
    _web(pg33, RELLENO.format(anio=2027).replace("on conflict (trabajadora_id, fecha, franja) do nothing",
                                                 ON_CONFLICT_EVENTOS))
    tipos = {r["fecha"]: r["tipo"] for r in pg33.json(
        "select fecha::text, tipo from public.eventos_calendario where franja = 'MANANA' and not anulado "
        "and fecha in ('2027-01-04', '2027-01-05')")}
    assert tipos == {"2027-01-04": "VACACIONES", "2027-01-05": "JORNADA"}
    assert pg33.sql(f"select tipo from public.eventos_calendario where id = {_lit(vac)}") == "VACACIONES"


# --------------------------------------------------------------------------- 2. vacaciones del convenio

def test_vacaciones_30_en_2026_2028_con_fuente_y_autor(pg17_nueva_base):
    pg = pg17_nueva_base("32")
    for anio in range(2025, 2030):
        _web(pg, "insert into public.convenio_anual (anio, jornada_max_horas, asuntos_propios_dias, "
                 f"permiso_medico_horas, estado, fuente) values ({anio}, 1780, 2, 20, "
                 "'FIRMADO_PENDIENTE_PUBLICACION', 'Convenio provincial')")
    pg.sql(MIGRACION_33.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_33.read_text(encoding="utf-8"))  # idempotente: no repite el historial
    filas = {r["anio"]: (r["vacaciones_dias_naturales"], r["vacaciones_fuente"]) for r in pg.json(
        "select anio, vacaciones_dias_naturales, vacaciones_fuente from public.convenio_anual")}
    fuente = "Decision de Pio (2026-11-14), pendiente de texto publicado"
    assert filas == {2025: (None, None), 2026: (30, fuente), 2027: (30, fuente), 2028: (30, fuente),
                     2029: (None, None)}
    assert pg.sql("select string_agg(registro_id || ':' || autor, ',' order by registro_id) "
                  "from public.trabajadores_historial where tabla = 'convenio_anual' and operacion = 'UPDATE'") == \
        "2026:Migracion 33,2027:Migracion 33,2028:Migracion 33"


def test_vacaciones_dominio_y_fuente_obligatoria(pg33):
    base = ("insert into public.convenio_anual (anio, jornada_max_horas, asuntos_propios_dias, permiso_medico_horas, "
            "estado, fuente, vacaciones_dias_naturales, vacaciones_fuente) values (2030, 1780, 2, 20, 'PUBLICADO', "
            "'x', {dias}, {fuente})")
    for dias, fuente in (("-1", "'x'"), ("367", "'x'"), ("30", "null")):
        with pytest.raises(RuntimeError, match="violates check constraint"):
            _web(pg33, base.format(dias=dias, fuente=fuente))
    _web(pg33, base.format(dias="31", fuente="'BOP'"))
    assert _web(pg33, "select vacaciones_dias_naturales from public.convenio_anual where anio = 2030") == "31"


# --------------------------------------------------------------------------- 3. ajustes anuales

def test_la_web_crea_actualiza_y_anula_ajustes_en_pio_y_rita(pg33):
    pio, rita = _trabajadora(pg33, "PIO"), _trabajadora(pg33, "RITA")
    a = _ajuste(pg33, pio, extra="2.5", nota="Antiguedad")
    _ajuste(pg33, rita, farmacia="RITA", extra="0")
    _web(pg33, f"update public.{TABLA} set vacaciones_dias_extra = 3 where id = {_lit(a)}")
    with pytest.raises(RuntimeError, match=f"{TABLA}_unico"):
        _ajuste(pg33, pio)
    _web(pg33, f"update public.{TABLA} set anulada = true where id = {_lit(a)}")
    _ajuste(pg33, pio, extra="1")
    _ajuste(pg33, pio, anio=2028, extra="0.5")
    assert _web(pg33, f"select string_agg(farmacia || ':' || anio || ':' || vacaciones_dias_extra || ':' || anulada, "
                      f"',' order by farmacia, anio, anulada) from public.{TABLA}") == \
        "PIO:2027:1.00:false,PIO:2027:3.00:true,PIO:2028:0.50:false,RITA:2027:0.00:false"


@pytest.mark.parametrize("cambio", [{"extra": "-0.5"}, {"anio": 2019}, {"nota": "x" * 201}])
def test_ajuste_fuera_de_dominio(pg33, cambio):
    t = _trabajadora(pg33)
    with pytest.raises(RuntimeError, match="violates check constraint"):
        _ajuste(pg33, t, **cambio)


def test_ajuste_de_otra_farmacia_o_fuera_del_modulo(pg33):
    t = _trabajadora(pg33, "PIO")
    # La farmacia del ajuste es la de la trabajadora (clave externa compuesta).
    with pytest.raises(RuntimeError, match=f"{TABLA}_trabajadora"):
        _ajuste(pg33, t, farmacia="RITA")
    # El trigger del modulo rechaza una farmacia no habilitada antes que la clave externa.
    with pytest.raises(RuntimeError, match="FARMACIA_NO_HABILITADA_EN_MODULO:LUNA"):
        _ajuste(pg33, t, farmacia="LUNA")


def test_la_rls_oculta_ajustes_de_farmacias_fuera_del_modulo(pg33):
    _ajuste(pg33, _trabajadora(pg33, "PIO"))
    rita = _trabajadora(pg33, "RITA")
    _ajuste(pg33, rita, farmacia="RITA")
    pg33.sql("update public.cf_modulos_farmacias set farmacias = array['PIO'] where modulo = 'TRABAJADORES'")
    for rol in (ROL, "cf_lectura"):
        assert _como(pg33, rol, f"select string_agg(farmacia, ',') from public.{TABLA}") == "PIO"
    # Con el trigger, la web no puede escribir en RITA; sin el trigger, la RLS sola tambien lo impide.
    with pytest.raises(RuntimeError, match="FARMACIA_NO_HABILITADA_EN_MODULO:RITA"):
        _ajuste(pg33, rita, anio=2028, farmacia="RITA")
    pg33.sql(f"alter table public.{TABLA} disable trigger {TABLA}_farmacia")
    try:
        with pytest.raises(RuntimeError, match="row-level security"):
            _ajuste(pg33, rita, anio=2028, farmacia="RITA")
    finally:
        pg33.sql(f"alter table public.{TABLA} enable trigger {TABLA}_farmacia")


def test_historial_y_autor_obligatorio_en_ajustes(pg33):
    t = _trabajadora(pg33)
    a = _ajuste(pg33, t, autor="Marc")
    _web(pg33, f"update public.{TABLA} set nota = 'Revisado' where id = {_lit(a)}", autor="Pio")
    assert pg33.sql("select string_agg(operacion || ':' || autor || ':' || farmacia, ',' order by id) "
                    f"from public.trabajadores_historial where tabla = '{TABLA}' and registro_id = {_lit(a)}") == \
        "INSERT:Marc:PIO,UPDATE:Pio:PIO"
    for autor in (None, "", "  "):
        with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
            _ajuste(pg33, t, anio=2029, autor=autor)
    assert pg33.sql(f"select count(*) from public.{TABLA}") == "1"


@pytest.mark.parametrize("sentencia", [f"delete from public.{TABLA}", f"truncate public.{TABLA}"])
def test_la_web_no_borra_ni_vacia_ajustes(pg33, sentencia):
    with pytest.raises(RuntimeError, match="permission denied"):
        _web(pg33, sentencia)


def test_lectura_y_privilegios_ajenos_de_la_tabla_nueva(pg33):
    """cf_lectura lee y no escribe; ni anon, ni authenticated, ni el rol del sistema, ni PUBLIC tienen privilegios."""
    assert _como(pg33, "cf_lectura", f"select count(*) from public.{TABLA}") == "0"
    with pytest.raises(RuntimeError, match="permission denied"):
        _como(pg33, "cf_lectura", f"delete from public.{TABLA}")
    for rol in ("anon", "authenticated"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _como(pg33, rol, f"select count(*) from public.{TABLA}")
    assert pg33.sql(DESPLIEGUE.ACL_AJENA) == "0"
    assert pg33.sql(DESPLIEGUE.PRIVILEGIOS_WEB.join(("select ", ""))) == "t"
    assert pg33.sql(f"select relrowsecurity || ':' || (select count(*) from pg_policy p where p.polrelid = c.oid) "
                    f"from pg_class c where c.oid = 'public.{TABLA}'::regclass") == "true:3"


def test_facturas_y_conciliacion_siguen_solo_pio(pg33):
    assert pg33.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert pg33.sql("select farmacias_habilitadas::text from public.cf_configuracion where id") == "{PIO}"
    assert pg33.sql("select count(*) from pg_proc p where p.pronamespace = 'public'::regnamespace "
                    "and p.proname not like 'cf_trab_%' and p.prosrc like '%trabajadoras_ajustes%'") == "0"


# --------------------------------------------------------------------------- desplegar_33.py

def test_sql_de_precondiciones_33_es_de_solo_lectura(pg17_nueva_base):
    sql = DESPLIEGUE.PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert pg17_nueva_base("32").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 7)
    assert pg17_nueva_base("33").sql("begin read only; " + sql + "; rollback;") == "|".join(["f", "f"] + ["t"] * 5)


def test_postcondiciones_en_la_plantilla_33(pg33):
    # Columnas: datos (3), privilegios de la web, lectura y ACL, estructura y RLS, vacaciones, propietario.
    assert pg33.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[3:] == ["t"] * 5


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf33_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    for relativa in (RUTA_33, "pruebas/auditoria_trab/desplegar_33.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 33"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_33.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_trab/desplegar_33.py")


def _sin_propietario(texto: str, db: str, rol: str) -> str:
    return texto.replace(db, "").replace(f"OWNER TO {rol};", "OWNER TO postgres;").replace(
        f"Owner: {rol}", "Owner: postgres")


def test_ensayo_completo_despliegue_33_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "32"))
    _datos_previos(pg, tmp_path)
    t = _trabajadora(pg)
    _evento(pg, t)
    _web(pg, "insert into public.convenio_anual (anio, jornada_max_horas, asuntos_propios_dias, permiso_medico_horas, "
             "estado, fuente) values (2026, 1780, 2, 20, 'FIRMADO_PENDIENTE_PUBLICACION', 'Convenio')")
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
    esquema_32 = esquema(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 7 and registro["convenio_2026_2028_filas"] == 1
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "privilegios_web": True, "lectura_y_acl": True,
                                           "estructura_y_rls": True, "vacaciones": True, "propietario": True}
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql("select vacaciones_dias_naturales from public.convenio_anual where anio = 2026") == "30"
    # Referencia (superusuario postgres, como el propietario en Supabase): mismo esquema salvo el propietario de la
    # tabla nueva, que es el rol que despliega (postgres en Supabase).
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "32"))
    referencia.sql(MIGRACION_33.read_text(encoding="utf-8"))
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema(referencia).replace(referencia.db, "")
    # La web funciona sobre lo desplegado por la imitacion.
    _ajuste(pg, t)
    assert _evento(pg, t, extra=ON_CONFLICT_EVENTOS) == ""

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: «33 ausente» y la unicidad de la 31 fallan, y aqui tambien «propietarios 2AX» (la tabla nueva es de
    # la imitacion; en Supabase, de postgres).
    assert registro["precondiciones"] == [False, False, True, True, True, True, False]

    # El rollback tambien funciona con la imitacion: esquema 32 (la vista recreada es de quien hace el rollback).
    atras =pgl.sql_como_supabase(pg, ROLLBACK_33.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema_32.replace(pg.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_33
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_33_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
