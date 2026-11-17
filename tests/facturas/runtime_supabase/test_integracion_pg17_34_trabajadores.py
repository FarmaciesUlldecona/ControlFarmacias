"""Hito TRAB-34 (TA3): migracion 34 (guardias y festivos de Trabajadores) en PostgreSQL 17 local.

Plantillas (pg17_local): "33" (estado productivo), "34" = 33 + migracion 34 dos veces, "34_rollback" = 34 + rollback.
Diseno: pruebas/auditoria_trab/DISENO_34.md. Se comprueba:
- festivos: un festivo LOCAL sin farmacia (las dos) se admite; uno comun por fecha; ambito LOCAL por defecto;
- guardias_semana: PIO, RITA u OTRA; persona de guardia y apoyo del sabado de esa farmacia, sin anular y de alta; OTRA
  sin personas; una por semana entre no anuladas; se anula aunque las personas ya no esten de alta;
- guardias_festivo: solo en un festivo comun vigente, una por fecha, persona de esa farmacia; anular o mover el festivo
  anula su guardia (con historial y el mismo autor);
- RLS por farmacia del modulo, con las filas OTRA (y su historial) visibles para el modulo; escritura de la web sin
  DELETE ni TRUNCATE; autor obligatorio; historial; lectura de cf_lectura; ningun privilegio ajeno (anon,
  authenticated, el rol del sistema ni PUBLIC) sobre las tablas ni las funciones nuevas;
- guardias_farmacia retirada (la migracion falla cerrado si tiene filas);
- rollback exacto al esquema 33, que falla cerrado con guardias o con festivos LOCAL sin farmacia;
- desplegar_34.py ensayado con el rol que imita al postgres de Supabase (norma 2BN-D), segundo intento revertido y
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
from test_integracion_pg17_31_trabajadores import _como, _trabajadora, _web

pytestmark = pytest.mark.pg17_local

MIGRACION_34 = MIG / "34_cf_trabajadores_guardias.sql"
ROLLBACK_34 = MIG / "34_cf_trabajadores_guardias.rollback.sql"
RUTA_34 = "sql/migrations/34_cf_trabajadores_guardias.sql"
SCRIPT_34 = ROOT / "pruebas/auditoria_trab/desplegar_34.py"
ROL = "cf_trabajadores_web"
SEMANA, FESTIVO = "guardias_semana", "guardias_festivo"
LUNES = "2027-03-01"  # sabado 2027-03-06, domingo 2027-03-07


def _cargar_despliegue(script=SCRIPT_34):
    spec = importlib.util.spec_from_file_location(f"desplegar_34_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar_despliegue()


def _semana(pg, farmacia="PIO", guardia=None, apoyo=None, lunes=LUNES, autor="Marc") -> str:
    return _web(pg, f"insert into public.{SEMANA} (lunes, farmacia, persona_guardia_id, persona_apoyo_sabado_id) "
                    f"values ({_lit(lunes)}, {_lit(farmacia)}, {_lit(guardia)}, {_lit(apoyo)}) returning id",
                autor=autor)


def _festivo(pg, fecha="2027-04-05", farmacia=None, ambito="LOCAL", descripcion="Fiesta local", autor="Marc") -> str:
    return _web(pg, "insert into public.festivos (fecha, ambito, farmacia, descripcion) values "
                    f"({_lit(fecha)}, {_lit(ambito)}, {_lit(farmacia)}, {_lit(descripcion)}) returning id",
                autor=autor)


def _guardia_festivo(pg, farmacia="PIO", persona=None, fecha="2027-04-05", autor="Marc") -> str:
    return _web(pg, f"insert into public.{FESTIVO} (fecha, farmacia, persona_id) values "
                    f"({_lit(fecha)}, {_lit(farmacia)}, {_lit(persona)}) returning id", autor=autor)


@pytest.fixture
def pg34(pg17_nueva_base):
    return pg17_nueva_base("34")


# --------------------------------------------------------------------------- migracion y rollback

def test_rollback_34_devuelve_el_esquema_33(pg17_nueva_base):
    atras = pg17_nueva_base("34_rollback")
    assert esquema(atras) == esquema(pg17_nueva_base("33"))
    for tabla in (SEMANA, FESTIVO):
        assert atras.sql(f"select to_regclass('public.{tabla}') is null") == "t"


def test_34_exige_la_33(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_33_AUSENTE"):
        pg17_nueva_base("32").sql(MIGRACION_34.read_text(encoding="utf-8"))


def test_34_idempotente_sin_cambiar_datos_ni_flags(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("33")
    _datos_previos(pg, tmp_path)
    _festivo(pg, ambito="NACIONAL", descripcion="Reyes", fecha="2027-01-06")
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    festivos = pg.sql("select string_agg(to_jsonb(f)::text, ',') from public.festivos f")
    configuracion = pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id")
    referencia = esquema(pg17_nueva_base("34"))
    pg.sql(MIGRACION_34.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_34.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql("select string_agg(to_jsonb(f)::text, ',') from public.festivos f") == festivos
    assert pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id") == configuracion
    assert esquema(pg) == referencia and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_34_falla_cerrado_si_guardias_farmacia_tiene_filas(pg17_nueva_base):
    pg = pg17_nueva_base("33")
    _web(pg, "insert into public.guardias_farmacia (farmacia, fecha) values ('PIO', '2027-03-06')")
    with pytest.raises(RuntimeError, match="GUARDIAS_FARMACIA_NO_VACIA"):
        pg.sql(MIGRACION_34.read_text(encoding="utf-8"))
    assert pg.sql("select count(*) from public.guardias_farmacia") == "1"
    assert pg.sql(f"select to_regclass('public.{SEMANA}') is null") == "t"


def test_una_guardia_de_farmacia_anulada_tambien_para_la_34(pg17_nueva_base):
    pg = pg17_nueva_base("33")
    g = _web(pg, "insert into public.guardias_farmacia (farmacia, fecha) values ('PIO', '2027-03-06') returning id")
    _web(pg, f"update public.guardias_farmacia set anulada = true where id = {_lit(g)}")
    # Anulada pero con fila: la tabla no esta vacia y la 34 se para.
    with pytest.raises(RuntimeError, match="GUARDIAS_FARMACIA_NO_VACIA"):
        pg.sql(MIGRACION_34.read_text(encoding="utf-8"))
    vacia = pg17_nueva_base("34")
    assert vacia.sql("select to_regclass('public.guardias_farmacia') is null") == "t"


@pytest.mark.parametrize("dato, error", [
    ("semana", "ROLLBACK_34_GUARDIAS_CON_DATOS"),
    ("festivo_local", "ROLLBACK_34_FESTIVOS_LOCALES_SIN_FARMACIA"),
])
def test_rollback_falla_cerrado_sin_borrar_nada(pg34, dato, error):
    if dato == "semana":
        _semana(pg34, farmacia="OTRA")
        _web(pg34, f"update public.{SEMANA} set anulada = true")
    else:
        _festivo(pg34)
    with pytest.raises(RuntimeError, match=error):
        pg34.sql(ROLLBACK_34.read_text(encoding="utf-8"))
    assert pg34.sql(f"select (select count(*) from public.{SEMANA}) + (select count(*) from public.festivos)") == "1"
    assert pg34.sql("select to_regclass('public.guardias_farmacia') is null") == "t"


# --------------------------------------------------------------------------- 1. festivos

def test_festivo_local_sin_farmacia_es_de_las_dos_y_uno_comun_por_fecha(pg34):
    f = _web(pg34, "insert into public.festivos (fecha, descripcion) values ('2027-04-05', 'Fiesta local') "
                   "returning id")
    assert pg34.sql(f"select ambito || ':' || coalesce(farmacia, '-') from public.festivos where id = {_lit(f)}") \
        == "LOCAL:-"
    with pytest.raises(RuntimeError, match="festivos_unico"):
        _festivo(pg34, descripcion="Otra")
    # Un festivo propio de una farmacia sigue admitido (como en la 31).
    _festivo(pg34, farmacia="RITA", descripcion="Solo RITA")
    _web(pg34, f"update public.festivos set anulado = true where id = {_lit(f)}")
    _festivo(pg34, descripcion="Nueva")
    for rol in (ROL, "cf_lectura"):
        assert _como(pg34, rol, "select count(*) from public.festivos where not anulado") == "2"


# --------------------------------------------------------------------------- 2. guardias_semana

def test_la_web_crea_guardias_semanales_de_pio_rita_y_otra(pg34):
    pio, apoyo, rita = _trabajadora(pg34, "PIO"), _trabajadora(pg34, "PIO"), _trabajadora(pg34, "RITA")
    _semana(pg34, "PIO", guardia=pio, apoyo=apoyo)
    _semana(pg34, "RITA", guardia=rita, lunes="2027-03-08")
    o = _semana(pg34, "OTRA", lunes="2027-03-15")
    _web(pg34, f"update public.{SEMANA} set lunes = '2027-03-22' where id = {_lit(o)}")
    assert _web(pg34, f"select string_agg(lunes || ':' || farmacia || ':' || (persona_guardia_id is not null) || ':' "
                      f"|| (persona_apoyo_sabado_id is not null), ',' order by lunes) from public.{SEMANA}") == \
        "2027-03-01:PIO:true:true,2027-03-08:RITA:true:false,2027-03-22:OTRA:false:false"


@pytest.mark.parametrize("caso, error", [
    ("otra_con_persona", "guardias_semana_otra_sin_personas"),
    ("pio_sin_persona", "guardias_semana_guardia_obligatoria"),
    ("apoyo_igual", "guardias_semana_apoyo_distinto"),
    ("persona_de_otra_farmacia", "guardias_semana_persona_guardia"),
    ("apoyo_de_otra_farmacia", "guardias_semana_persona_apoyo"),
    ("no_es_lunes", "guardias_semana_lunes_check"),
    ("farmacia_ajena", "FARMACIA_NO_HABILITADA_EN_MODULO:LUNA"),
])
def test_guardia_semanal_fuera_de_dominio(pg34, caso, error):
    pio, rita = _trabajadora(pg34, "PIO"), _trabajadora(pg34, "RITA")
    argumentos = {
        "otra_con_persona": {"farmacia": "OTRA", "apoyo": pio},
        "pio_sin_persona": {"farmacia": "PIO"},
        "apoyo_igual": {"guardia": pio, "apoyo": pio},
        "persona_de_otra_farmacia": {"guardia": rita},
        "apoyo_de_otra_farmacia": {"guardia": pio, "apoyo": rita},
        "no_es_lunes": {"guardia": pio, "lunes": "2027-03-02"},
        "farmacia_ajena": {"farmacia": "LUNA"},
    }[caso]
    with pytest.raises(RuntimeError, match=error):
        _semana(pg34, **argumentos)
    assert pg34.sql(f"select count(*) from public.{SEMANA}") == "0"


def test_personas_sin_anular_y_de_alta_el_fin_de_semana(pg34):
    # De baja el viernes: no cubre la guardia del sabado y domingo.
    baja_viernes = _trabajadora(pg34, alta="2027-01-01", baja="2027-03-05")
    # De baja el sabado: vale de apoyo del sabado, no de guardia (domingo).
    baja_sabado = _trabajadora(pg34, alta="2027-01-01", baja="2027-03-06")
    alta_domingo = _trabajadora(pg34, alta="2027-03-07")
    anulada = _trabajadora(pg34)
    _web(pg34, f"update public.trabajadoras set anulada = true where id = {_lit(anulada)}")
    vigente = _trabajadora(pg34)
    for guardia, apoyo in ((baja_viernes, None), (baja_sabado, None), (anulada, None), (vigente, baja_viernes),
                           (vigente, alta_domingo)):
        with pytest.raises(RuntimeError, match="PERSONA_NO_VALIDA"):
            _semana(pg34, guardia=guardia, apoyo=apoyo)
    _semana(pg34, guardia=vigente, apoyo=baja_sabado)
    assert pg34.sql(f"select count(*) from public.{SEMANA}") == "1"


def test_una_guardia_por_semana_entre_no_anuladas_y_se_anula_aunque_la_persona_este_de_baja(pg34):
    t = _trabajadora(pg34, alta="2027-01-01")
    g = _semana(pg34, guardia=t)
    with pytest.raises(RuntimeError, match="guardias_semana_lunes_unico"):
        _semana(pg34, farmacia="OTRA")
    _web(pg34, f"update public.trabajadoras set fecha_baja = '2027-03-02' where id = {_lit(t)}")
    with pytest.raises(RuntimeError, match="PERSONA_NO_VALIDA"):
        _web(pg34, f"update public.{SEMANA} set persona_apoyo_sabado_id = null where id = {_lit(g)}")
    _web(pg34, f"update public.{SEMANA} set anulada = true where id = {_lit(g)}", autor="Pio")
    _semana(pg34, farmacia="OTRA")
    assert pg34.sql(f"select string_agg(farmacia || ':' || anulada, ',' order by anulada) from public.{SEMANA}") == \
        "OTRA:false,PIO:true"


# --------------------------------------------------------------------------- 3. guardias_festivo

def test_guardia_de_festivo_solo_en_un_festivo_comun_vigente(pg34):
    pio, rita = _trabajadora(pg34, "PIO"), _trabajadora(pg34, "RITA")
    with pytest.raises(RuntimeError, match="NO_ES_FESTIVO"):
        _guardia_festivo(pg34, persona=pio)
    # Un festivo propio de una farmacia no sostiene una guardia de festivo.
    _festivo(pg34, farmacia="PIO", descripcion="Solo PIO")
    with pytest.raises(RuntimeError, match="NO_ES_FESTIVO"):
        _guardia_festivo(pg34, persona=pio)
    _festivo(pg34)
    with pytest.raises(RuntimeError, match="guardias_festivo_persona"):
        _guardia_festivo(pg34, persona=rita)
    with pytest.raises(RuntimeError, match="guardias_festivo_otra_sin_persona"):
        _guardia_festivo(pg34, "OTRA", persona=pio)
    with pytest.raises(RuntimeError, match="guardias_festivo_persona_obligatoria"):
        _guardia_festivo(pg34, "RITA")
    g = _guardia_festivo(pg34, "RITA", persona=rita)
    with pytest.raises(RuntimeError, match="guardias_festivo_fecha_unico"):
        _guardia_festivo(pg34, "OTRA")
    _web(pg34, f"update public.{FESTIVO} set farmacia = 'OTRA', persona_id = null where id = {_lit(g)}")
    assert _web(pg34, f"select farmacia || ':' || (persona_id is null) from public.{FESTIVO}") == "OTRA:true"


def test_persona_de_la_guardia_de_festivo_de_alta_ese_dia(pg34):
    _festivo(pg34)
    baja = _trabajadora(pg34, alta="2027-01-01", baja="2027-04-04")
    with pytest.raises(RuntimeError, match="PERSONA_NO_VALIDA"):
        _guardia_festivo(pg34, persona=baja)
    _guardia_festivo(pg34, persona=_trabajadora(pg34, alta="2027-04-05"))


@pytest.mark.parametrize("cambio", ["anulado = true", "fecha = '2027-04-06'", "farmacia = 'PIO'"])
def test_anular_o_mover_el_festivo_anula_su_guardia_con_historial(pg34, cambio):
    f = _festivo(pg34)
    g = _guardia_festivo(pg34, persona=_trabajadora(pg34))
    _web(pg34, f"update public.festivos set {cambio} where id = {_lit(f)}", autor="Pio")
    assert pg34.sql(f"select anulada from public.{FESTIVO} where id = {_lit(g)}") == "t"
    assert pg34.sql("select string_agg(operacion || ':' || autor || ':' || (despues->>'anulada'), ',' order by id) "
                    f"from public.trabajadores_historial where tabla = '{FESTIVO}' and registro_id = {_lit(g)}") == \
        "INSERT:Marc:false,UPDATE:Pio:true"


def test_cambiar_la_descripcion_del_festivo_no_toca_su_guardia(pg34):
    f = _festivo(pg34)
    _guardia_festivo(pg34, "OTRA")
    _web(pg34, f"update public.festivos set descripcion = 'Fiesta mayor' where id = {_lit(f)}")
    assert pg34.sql(f"select anulada from public.{FESTIVO}") == "f"


# --------------------------------------------------------------------------- RLS, autor, historial y privilegios

def test_la_rls_oculta_rita_fuera_del_modulo_y_otra_sigue_visible(pg34):
    rita = _trabajadora(pg34, "RITA")
    _semana(pg34, "RITA", guardia=rita)
    _semana(pg34, "OTRA", lunes="2027-03-08")
    _festivo(pg34)
    _guardia_festivo(pg34, "RITA", persona=rita)
    pg34.sql("update public.cf_modulos_farmacias set farmacias = array['PIO'] where modulo = 'TRABAJADORES'")
    for rol in (ROL, "cf_lectura"):
        assert _como(pg34, rol, f"select string_agg(farmacia, ',') from public.{SEMANA}") == "OTRA"
        assert _como(pg34, rol, f"select count(*) from public.{FESTIVO}") == "0"
        assert _como(pg34, rol, "select string_agg(distinct farmacia, ',') from public.trabajadores_historial "
                                f"where tabla = '{SEMANA}'") == "OTRA"
    # Con el trigger, la web no puede escribir en RITA; sin el trigger, la RLS sola tambien lo impide.
    with pytest.raises(RuntimeError, match="FARMACIA_NO_HABILITADA_EN_MODULO:RITA"):
        _semana(pg34, "RITA", guardia=rita, lunes="2027-03-15")
    pg34.sql(f"alter table public.{SEMANA} disable trigger {SEMANA}_farmacia")
    try:
        with pytest.raises(RuntimeError, match="row-level security"):
            _semana(pg34, "RITA", guardia=rita, lunes="2027-03-15")
    finally:
        pg34.sql(f"alter table public.{SEMANA} enable trigger {SEMANA}_farmacia")


def test_historial_y_autor_obligatorio_en_guardias(pg34):
    t = _trabajadora(pg34)
    g = _semana(pg34, guardia=t, autor="Marc")
    _web(pg34, f"update public.{SEMANA} set anulada = true where id = {_lit(g)}", autor="Pio")
    assert pg34.sql("select string_agg(operacion || ':' || autor || ':' || farmacia, ',' order by id) "
                    f"from public.trabajadores_historial where tabla = '{SEMANA}' and registro_id = {_lit(g)}") == \
        "INSERT:Marc:PIO,UPDATE:Pio:PIO"
    _festivo(pg34)
    for autor in (None, "", "  "):
        with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
            _semana(pg34, farmacia="OTRA", autor=autor)
        with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
            _guardia_festivo(pg34, "OTRA", autor=autor)
    assert pg34.sql(f"select (select count(*) from public.{SEMANA}) || '|' || (select count(*) from public.{FESTIVO})") \
        == "1|0"


@pytest.mark.parametrize("tabla", [SEMANA, FESTIVO])
@pytest.mark.parametrize("sentencia", ["delete from public.{t}", "truncate public.{t}"])
def test_la_web_no_borra_ni_vacia_guardias(pg34, tabla, sentencia):
    with pytest.raises(RuntimeError, match="permission denied"):
        _web(pg34, sentencia.format(t=tabla))


def test_lectura_y_privilegios_ajenos_de_las_tablas_y_funciones_nuevas(pg34):
    """cf_lectura lee y no escribe; ni anon, ni authenticated, ni el rol del sistema, ni PUBLIC tienen privilegios."""
    for tabla in (SEMANA, FESTIVO):
        assert _como(pg34, "cf_lectura", f"select count(*) from public.{tabla}") == "0"
        with pytest.raises(RuntimeError, match="permission denied"):
            _como(pg34, "cf_lectura", f"insert into public.{tabla} (farmacia) values ('OTRA')")
        for rol in ("anon", "authenticated"):
            with pytest.raises(RuntimeError, match="permission denied"):
                _como(pg34, rol, f"select count(*) from public.{tabla}")
        assert pg34.sql(f"select relrowsecurity || ':' || (select count(*) from pg_policy p where p.polrelid = c.oid) "
                        f"from pg_class c where c.oid = 'public.{tabla}'::regclass") == "true:3"
    assert pg34.sql(DESPLIEGUE.ACL_AJENA) == "0"
    assert pg34.sql(DESPLIEGUE.ACL_FUNCIONES_AJENA) == "0"
    assert pg34.sql(DESPLIEGUE.PRIVILEGIOS_WEB.join(("select ", ""))) == "t"
    with pytest.raises(RuntimeError, match="permission denied"):
        _web(pg34, "select public.cf_trab_persona_de_alta(gen_random_uuid(), current_date, current_date)")


def test_facturas_y_conciliacion_siguen_solo_pio(pg34):
    assert pg34.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert pg34.sql("select farmacias_habilitadas::text from public.cf_configuracion where id") == "{PIO}"
    assert pg34.sql("select count(*) from pg_proc p where p.pronamespace = 'public'::regnamespace "
                    "and p.proname not like 'cf_trab_%' and p.prosrc like '%guardias_%'") == "0"


def test_el_orquestador_nocturno_trata_las_guardias_como_trabajadores():
    from src.facturas.runtime_supabase import noche_automatica as na

    assert {SEMANA, FESTIVO, "trabajadoras_ajustes_anuales"} <= na.TABLAS_TRABAJADORES <= na.TABLAS_FUERA_DEL_SNAPSHOT


# --------------------------------------------------------------------------- desplegar_34.py

def test_sql_de_precondiciones_34_es_de_solo_lectura(pg17_nueva_base):
    sql = DESPLIEGUE.PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert pg17_nueva_base("33").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 7)
    assert pg17_nueva_base("34").sql("begin read only; " + sql + "; rollback;") == "|".join(["f", "f"] + ["t"] * 5)


def test_precondicion_falla_con_guardias_farmacia_no_vacia(pg17_nueva_base):
    pg = pg17_nueva_base("33")
    _web(pg, "insert into public.guardias_farmacia (farmacia, fecha) values ('RITA', '2027-03-06')")
    assert pg.sql("begin read only; " + DESPLIEGUE.PRECONDICIONES + "; rollback;").split("|")[:2] == ["t", "f"]


def test_postcondiciones_en_la_plantilla_34(pg34):
    # Columnas: datos (3), privilegios de la web, lectura y ACL, estructura y RLS, propietario.
    assert pg34.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[3:] == ["t"] * 4


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf34_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    for relativa in (RUTA_34, "pruebas/auditoria_trab/desplegar_34.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 34"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_34.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_trab/desplegar_34.py")


def _sin_propietario(texto: str, db: str, rol: str) -> str:
    return texto.replace(db, "").replace(f"OWNER TO {rol};", "OWNER TO postgres;").replace(
        f"Owner: {rol}", "Owner: postgres")


def test_ensayo_completo_despliegue_34_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "33"))
    _datos_previos(pg, tmp_path)
    t = _trabajadora(pg)
    _festivo(pg, ambito="NACIONAL", descripcion="Reyes", fecha="2027-01-06")
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
    esquema_33 = esquema(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 7
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "privilegios_web": True, "lectura_y_acl": True,
                                           "estructura_y_rls": True, "propietario": True}
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    # Referencia (superusuario postgres, como el propietario en Supabase): mismo esquema salvo el propietario de los
    # objetos nuevos, que es el rol que despliega (postgres en Supabase).
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "33"))
    referencia.sql(MIGRACION_34.read_text(encoding="utf-8"))
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema(referencia).replace(referencia.db, "")
    # La web funciona sobre lo desplegado por la imitacion.
    _semana(pg, guardia=t)
    _festivo(pg)
    _guardia_festivo(pg, "OTRA")

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: «34 ausente» y «guardias_farmacia vacia» fallan, y aqui tambien «propietarios 2AX» (las tablas
    # nuevas son de la imitacion; en Supabase, de postgres).
    assert registro["precondiciones"] == [False, False, True, True, True, True, False]

    # El rollback tambien funciona con la imitacion (sin guardias ni festivos locales sin farmacia): esquema 33.
    pg.sql(f"set session_replication_role = replica; truncate public.{FESTIVO}, public.{SEMANA}; "
           "delete from public.festivos where ambito = 'LOCAL'")
    atras = pgl.sql_como_supabase(pg, ROLLBACK_34.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema_33.replace(pg.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_34
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_34_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
