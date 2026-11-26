"""Hito TA4-2: migracion 41 (guardias por asignar y estado de la guardia, Trabajadores) en PostgreSQL 17 local.

Plantillas (pg17_local): "40" (estado productivo), "41" = 40 + migracion 41 dos veces, "41_rollback" = 41 + rollback.
Diseno: pruebas/auditoria_trab/DISENO_41.md (peticion web TA4-2, DECISION DE PIO del 2026-11-26). Se comprueba:
- guardias_semana y guardias_festivo: OTRA sigue siempre sin persona; PIO y RITA admiten la persona nula («por
  asignar»); los triggers de la 34 siguen validando la persona cuando la hay;
- columna estado PLANIFICADO | CONFIRMADO, not null; las filas existentes quedan CONFIRMADO sin reescribirse (ni
  updated_at ni historial); CONFIRMADO sin persona se admite en PIO y RITA;
- se mantienen anular y nunca borrar, el autor por transaccion, el historial (con el estado), la RLS y los privilegios:
  la web escribe la columna nueva y cf_lectura la lee;
- rollback exacto al esquema 40, que falla cerrado con guardias por asignar o PLANIFICADO (tambien anuladas);
- desplegar_41.py ensayado con el rol que imita al postgres de Supabase, segundo intento revertido y rollback con la
  imitacion.
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
from test_integracion_pg17_31_trabajadores import _como, _trabajadora, _web

pytestmark = pytest.mark.pg17_local

MIGRACION_41 = MIG / "41_cf_trabajadores_guardias_estado.sql"
ROLLBACK_41 = MIG / "41_cf_trabajadores_guardias_estado.rollback.sql"
RUTA_41 = "sql/migrations/41_cf_trabajadores_guardias_estado.sql"
SCRIPT_41 = ROOT / "pruebas/auditoria_trab/desplegar_41.py"
ROL = "cf_trabajadores_web"
SEMANA, FESTIVO = "guardias_semana", "guardias_festivo"
LUNES = "2027-03-01"  # sabado 2027-03-06, domingo 2027-03-07
FECHA_FESTIVO = "2027-04-05"
HISTORIAL_GUARDIAS = ("select to_jsonb(h) from public.trabajadores_historial h "
                      f"where tabla in ('{SEMANA}', '{FESTIVO}')")


def _cargar_despliegue(script=SCRIPT_41):
    spec = importlib.util.spec_from_file_location(f"desplegar_41_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar_despliegue()


def _semana(pg, farmacia="PIO", guardia=None, apoyo=None, lunes=LUNES, estado=None, autor="Marc") -> str:
    columnas, valores = "lunes, farmacia, persona_guardia_id, persona_apoyo_sabado_id", \
        f"{_lit(lunes)}, {_lit(farmacia)}, {_lit(guardia)}, {_lit(apoyo)}"
    if estado is not None:
        columnas, valores = columnas + ", estado", valores + f", {_lit(estado)}"
    return _web(pg, f"insert into public.{SEMANA} ({columnas}) values ({valores}) returning id", autor=autor)


def _festivo(pg, fecha=FECHA_FESTIVO, autor="Marc") -> str:
    return _web(pg, "insert into public.festivos (fecha, ambito, descripcion) values "
                    f"({_lit(fecha)}, 'LOCAL', 'Fiesta local') returning id", autor=autor)


def _guardia_festivo(pg, farmacia="PIO", persona=None, fecha=FECHA_FESTIVO, estado=None, autor="Marc") -> str:
    columnas, valores = "fecha, farmacia, persona_id", f"{_lit(fecha)}, {_lit(farmacia)}, {_lit(persona)}"
    if estado is not None:
        columnas, valores = columnas + ", estado", valores + f", {_lit(estado)}"
    return _web(pg, f"insert into public.{FESTIVO} ({columnas}) values ({valores}) returning id", autor=autor)


def _guardias_previas(pg) -> None:
    """Guardias como en produccion antes de la 41: PIO y RITA con persona, OTRA sin ella, alguna anulada."""
    pio, rita = _trabajadora(pg, "PIO"), _trabajadora(pg, "RITA")
    _semana(pg, "PIO", guardia=pio)
    _semana(pg, "RITA", guardia=rita, lunes="2027-03-08")
    o = _semana(pg, "OTRA", lunes="2027-03-15")
    _web(pg, f"update public.{SEMANA} set anulada = true where id = {_lit(o)}")
    _festivo(pg)
    _guardia_festivo(pg, "RITA", persona=rita)


@pytest.fixture
def pg41(pg17_nueva_base):
    return pg17_nueva_base("41")


# --------------------------------------------------------------------------- migracion y rollback

def test_rollback_41_devuelve_exactamente_el_esquema_40(pg17_nueva_base):
    atras = pg17_nueva_base("41_rollback")
    assert esquema(atras) == esquema(pg17_nueva_base("40"))
    for tabla in (SEMANA, FESTIVO):
        assert atras.sql("select count(*) from information_schema.columns where table_schema = 'public' "
                         f"and table_name = '{tabla}' and column_name = 'estado'") == "0"


def test_41_exige_la_40(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_40_AUSENTE"):
        pg17_nueva_base("39").sql(MIGRACION_41.read_text(encoding="utf-8"))


def test_41_idempotente_sin_reescribir_guardias_ni_cambiar_datos_ni_flags(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("40")
    _datos_previos(pg, tmp_path)
    _guardias_previas(pg)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    filas = {t: pg.sql(f"select string_agg((to_jsonb(g))::text, ',' order by id) from public.{t} g")
             for t in (SEMANA, FESTIVO)}
    historial = _huella(pg, HISTORIAL_GUARDIAS)
    configuracion = pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id")
    referencia = esquema(pg17_nueva_base("41"))
    pg.sql(MIGRACION_41.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_41.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    for tabla, previas in filas.items():
        # Mismas filas (tambien updated_at) con estado CONFIRMADO; ninguna fila de historial nueva.
        assert pg.sql(f"select string_agg((to_jsonb(g) - 'estado')::text, ',' order by id) from public.{tabla} g") \
            == previas
        assert pg.sql(f"select string_agg(distinct estado, ',') from public.{tabla}") == "CONFIRMADO"
    assert _huella(pg, HISTORIAL_GUARDIAS) == historial
    assert pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id") == configuracion
    assert esquema(pg) == referencia and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


@pytest.mark.parametrize("caso, error", [
    ("semana_por_asignar", "ROLLBACK_41_GUARDIAS_POR_ASIGNAR"),
    ("festivo_por_asignar", "ROLLBACK_41_GUARDIAS_POR_ASIGNAR"),
    ("semana_planificada", "ROLLBACK_41_GUARDIAS_PLANIFICADAS"),
    ("festivo_planificado", "ROLLBACK_41_GUARDIAS_PLANIFICADAS"),
])
def test_rollback_falla_cerrado_sin_cambiar_nada_aunque_la_guardia_este_anulada(pg41, caso, error):
    t = _trabajadora(pg41, "PIO")
    _festivo(pg41)
    if caso == "semana_por_asignar":
        g, tabla = _semana(pg41, "PIO"), SEMANA
    elif caso == "festivo_por_asignar":
        g, tabla = _guardia_festivo(pg41, "RITA"), FESTIVO
    elif caso == "semana_planificada":
        g, tabla = _semana(pg41, "PIO", guardia=t, estado="PLANIFICADO"), SEMANA
    else:
        g, tabla = _guardia_festivo(pg41, "OTRA", estado="PLANIFICADO"), FESTIVO
    _web(pg41, f"update public.{tabla} set anulada = true where id = {_lit(g)}")
    referencia = esquema(pg41)
    with pytest.raises(RuntimeError, match=error):
        pg41.sql(ROLLBACK_41.read_text(encoding="utf-8"))
    assert esquema(pg41) == referencia
    assert pg41.sql(f"select count(*) from public.{tabla} where id = {_lit(g)}") == "1"


# --------------------------------------------------------------------------- 1. persona por asignar

def test_pio_y_rita_admiten_la_guardia_por_asignar_y_otra_sigue_sin_persona(pg41):
    pio = _trabajadora(pg41, "PIO")
    _semana(pg41, "PIO")
    _semana(pg41, "RITA", lunes="2027-03-08", estado="PLANIFICADO")
    _festivo(pg41)
    _guardia_festivo(pg41, "PIO")
    assert _web(pg41, f"select string_agg(farmacia || ':' || (persona_guardia_id is null) || ':' || estado, ',' "
                      f"order by lunes) from public.{SEMANA}") == "PIO:true:CONFIRMADO,RITA:true:PLANIFICADO"
    assert _web(pg41, f"select farmacia || ':' || (persona_id is null) || ':' || estado from public.{FESTIVO}") == \
        "PIO:true:CONFIRMADO"
    with pytest.raises(RuntimeError, match="guardias_semana_otra_sin_personas"):
        _semana(pg41, "OTRA", guardia=pio, lunes="2027-03-15")
    with pytest.raises(RuntimeError, match="guardias_semana_otra_sin_personas"):
        _semana(pg41, "OTRA", apoyo=pio, lunes="2027-03-15")
    with pytest.raises(RuntimeError, match="guardias_festivo_otra_sin_persona"):
        _web(pg41, f"update public.{FESTIVO} set farmacia = 'OTRA', persona_id = {_lit(pio)}")


def test_asignar_la_persona_despues_sigue_validando_farmacia_y_alta(pg41):
    g = _semana(pg41, "PIO", estado="PLANIFICADO")
    rita = _trabajadora(pg41, "RITA")
    baja = _trabajadora(pg41, "PIO", alta="2027-01-01", baja="2027-03-05")
    with pytest.raises(RuntimeError, match="guardias_semana_persona_guardia"):
        _web(pg41, f"update public.{SEMANA} set persona_guardia_id = {_lit(rita)} where id = {_lit(g)}")
    with pytest.raises(RuntimeError, match="PERSONA_NO_VALIDA"):
        _web(pg41, f"update public.{SEMANA} set persona_guardia_id = {_lit(baja)} where id = {_lit(g)}")
    pio = _trabajadora(pg41, "PIO")
    _web(pg41, f"update public.{SEMANA} set persona_guardia_id = {_lit(pio)}, estado = 'CONFIRMADO' "
               f"where id = {_lit(g)}", autor="Pio")
    assert pg41.sql(f"select (persona_guardia_id is not null) || ':' || estado from public.{SEMANA}") == \
        "true:CONFIRMADO"
    # Apoyo del sabado con la guardia aun por asignar: se admite (el apoyo ya era opcional) y se valida igual.
    g2 = _semana(pg41, "PIO", apoyo=pio, lunes="2027-03-08")
    with pytest.raises(RuntimeError, match="guardias_semana_apoyo_distinto"):
        _web(pg41, f"update public.{SEMANA} set persona_guardia_id = {_lit(pio)} where id = {_lit(g2)}")


# --------------------------------------------------------------------------- 2. estado

def test_estado_por_defecto_confirmado_y_confirmado_sin_persona(pg41):
    g = _semana(pg41, "PIO")
    assert pg41.sql(f"select estado || ':' || (persona_guardia_id is null) from public.{SEMANA} "
                    f"where id = {_lit(g)}") == "CONFIRMADO:true"
    p = _semana(pg41, "RITA", lunes="2027-03-08", estado="PLANIFICADO")
    _web(pg41, f"update public.{SEMANA} set estado = 'CONFIRMADO' where id = {_lit(p)}")
    _web(pg41, f"update public.{SEMANA} set estado = 'PLANIFICADO' where id = {_lit(p)}")
    assert pg41.sql(f"select estado from public.{SEMANA} where id = {_lit(p)}") == "PLANIFICADO"


@pytest.mark.parametrize("tabla", [SEMANA, FESTIVO])
@pytest.mark.parametrize("valor, error", [
    ("'BORRADOR'", "_estado"),
    ("'confirmado'", "_estado"),
    ("null", "null value in column \"estado\""),
])
def test_estado_fuera_de_dominio(pg41, tabla, valor, error):
    _festivo(pg41)
    g = _semana(pg41, "OTRA") if tabla == SEMANA else _guardia_festivo(pg41, "OTRA")
    with pytest.raises(RuntimeError, match=error):
        _web(pg41, f"update public.{tabla} set estado = {valor} where id = {_lit(g)}")
    assert pg41.sql(f"select estado from public.{tabla} where id = {_lit(g)}") == "CONFIRMADO"


# --------------------------------------------------------------------------- 3. reglas que se mantienen

def test_historial_con_estado_y_autor_obligatorio(pg41):
    g = _semana(pg41, "PIO", estado="PLANIFICADO", autor="Marc")
    _web(pg41, f"update public.{SEMANA} set estado = 'CONFIRMADO' where id = {_lit(g)}", autor="Pio")
    assert pg41.sql("select string_agg(operacion || ':' || autor || ':' || coalesce(antes->>'estado', '-') || '>' "
                    "|| (despues->>'estado'), ',' order by id) from public.trabajadores_historial "
                    f"where tabla = '{SEMANA}' and registro_id = {_lit(g)}") == \
        "INSERT:Marc:->PLANIFICADO,UPDATE:Pio:PLANIFICADO>CONFIRMADO"
    _festivo(pg41)
    for autor in (None, "", "  "):
        with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
            _semana(pg41, "RITA", lunes="2027-03-08", autor=autor)
        with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
            _guardia_festivo(pg41, "PIO", estado="PLANIFICADO", autor=autor)
        with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
            _web(pg41, f"update public.{SEMANA} set estado = 'PLANIFICADO' where id = {_lit(g)}", autor=autor)


@pytest.mark.parametrize("tabla", [SEMANA, FESTIVO])
@pytest.mark.parametrize("sentencia", ["delete from public.{t}", "truncate public.{t}"])
def test_la_web_sigue_sin_borrar_ni_vaciar_guardias(pg41, tabla, sentencia):
    with pytest.raises(RuntimeError, match="permission denied"):
        _web(pg41, sentencia.format(t=tabla))


def test_la_web_escribe_y_cf_lectura_lee_el_estado_con_la_misma_rls(pg41):
    rita = _trabajadora(pg41, "RITA")
    _semana(pg41, "RITA", guardia=rita, estado="PLANIFICADO")
    _semana(pg41, "OTRA", lunes="2027-03-08", estado="PLANIFICADO")
    for rol in (ROL, "cf_lectura"):
        assert _como(pg41, rol, f"select string_agg(farmacia || ':' || estado, ',' order by lunes) "
                                f"from public.{SEMANA}") == "RITA:PLANIFICADO,OTRA:PLANIFICADO"
    with pytest.raises(RuntimeError, match="permission denied"):
        _como(pg41, "cf_lectura", f"update public.{SEMANA} set estado = 'CONFIRMADO'")
    for rol in ("anon", "authenticated"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _como(pg41, rol, f"select estado from public.{SEMANA}")
    pg41.sql("update public.cf_modulos_farmacias set farmacias = array['PIO'] where modulo = 'TRABAJADORES'")
    for rol in (ROL, "cf_lectura"):
        assert _como(pg41, rol, f"select string_agg(farmacia, ',') from public.{SEMANA}") == "OTRA"
    assert pg41.sql(DESPLIEGUE.PRIVILEGIOS_WEB.join(("select ", ""))) == "t"
    assert pg41.sql(DESPLIEGUE.LECTURA.join(("select ", ""))) == "t"


def test_facturas_y_conciliacion_siguen_solo_pio(pg41):
    assert pg41.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert pg41.sql("select farmacias_habilitadas::text from public.cf_configuracion where id") == "{PIO}"


def test_la_41_no_nombra_el_rol_del_sistema_ni_crea_objetos():
    for ruta in (MIGRACION_41, ROLLBACK_41):
        texto = ruta.read_text(encoding="utf-8").lower()
        assert "grant " not in texto and "revoke " not in texto
        assert "create table" not in texto and "create or replace function" not in texto


# --------------------------------------------------------------------------- desplegar_41.py

def test_sql_de_precondiciones_41_es_de_solo_lectura(pg17_nueva_base):
    sql = DESPLIEGUE.PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert pg17_nueva_base("40").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 7)
    assert pg17_nueva_base("41").sql("begin read only; " + sql + "; rollback;") == "|".join(["f"] + ["t"] * 6)


def test_postcondiciones_en_la_plantilla_41(pg41):
    assert pg41.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[DESPLIEGUE.N_DATOS:] == ["t"] * 4


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf41_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    for relativa in (RUTA_41, "pruebas/auditoria_trab/desplegar_41.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 41"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_41.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_trab/desplegar_41.py")


def test_ensayo_completo_despliegue_41_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "40"))
    _datos_previos(pg, tmp_path)
    _guardias_previas(pg)
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
    historial = _huella(pg, HISTORIAL_GUARDIAS)
    esquema_40 = esquema(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 7
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "privilegios_web": True, "lectura": True,
                                           "estructura": True, "propietario": True}
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert _huella(pg, HISTORIAL_GUARDIAS) == historial
    # Referencia (superusuario postgres, como el propietario en Supabase): mismo esquema. La 41 no crea objetos, asi que
    # no hay propietario que normalizar.
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "40"))
    referencia.sql(MIGRACION_41.read_text(encoding="utf-8"))
    assert esquema(pg).replace(pg.db, "") == esquema(referencia).replace(referencia.db, "")
    # La web funciona sobre lo desplegado por la imitacion.
    _semana(pg, "PIO", lunes="2027-03-22", estado="PLANIFICADO")

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: solo «41 ausente» falla (no hay objetos nuevos de la imitacion que rompan los propietarios 2AX).
    assert registro["precondiciones"] == [False] + [True] * 6

    # El rollback tambien funciona con la imitacion (sin guardias por asignar ni PLANIFICADO): esquema 40.
    pg.sql(f"set session_replication_role = replica; delete from public.{SEMANA} where persona_guardia_id is null "
           "and farmacia <> 'OTRA'")
    atras = pgl.sql_como_supabase(pg, ROLLBACK_41.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    assert esquema(pg).replace(pg.db, "") == esquema_40.replace(pg.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_41
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_41_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
