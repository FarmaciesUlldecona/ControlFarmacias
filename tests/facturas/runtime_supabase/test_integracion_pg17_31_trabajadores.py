"""Hito TRAB: migracion 31 (esquema de Trabajadores) en PostgreSQL 17 local.

Plantillas (pg17_local): "30" (estado productivo), "31" = 30 + migracion 31 dos veces, "31_rollback" = 31 +
rollback. Diseno: pruebas/auditoria_trab/DISENO.md. Se comprueba:
- el rol de la web (cf_trabajadores_web): SELECT, INSERT y UPDATE solo en el modulo, sin DELETE ni TRUNCATE, nada fuera
  del modulo (facturas, albaranes, conciliacion, configuracion, RPC);
- el permiso de farmacia por modulo (PIO y RITA en Trabajadores) y que facturas, albaranes y conciliacion siguen solo
  PIO;
- dominios, unicidad, horas por defecto, relleno del ano e historial solo de insercion con autor;
- cf_lectura lee el modulo; anon, authenticated y el rol del sistema no tienen ningun privilegio sobre el;
- desplegar_31.py ensayado con el rol que imita al postgres de Supabase (norma 2BN-D), segundo intento revertido y
  rollback con la imitacion.
Sin produccion ni Farmatic.
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
from pg17_local import FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, _lit, base_desde, esquema
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _datos_previos, _huella, contenedor_tcp)

pytestmark = pytest.mark.pg17_local

MIGRACION_31 = MIG / "31_cf_trabajadores.sql"
ROLLBACK_31 = MIG / "31_cf_trabajadores.rollback.sql"
RUTA_31 = "sql/migrations/31_cf_trabajadores.sql"
SCRIPT_31 = ROOT / "pruebas/auditoria_trab/desplegar_31.py"
ROL = "cf_trabajadores_web"


def _cargar_despliegue(script=SCRIPT_31):
    spec = importlib.util.spec_from_file_location(f"desplegar_31_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar_despliegue()


def _web(pg, sentencia: str, autor: str | None = "Marc") -> str:
    """Ejecuta como el rol de la web (SET ROLE), con el autor que fija la web; cada sentencia se confirma."""
    prefijo = f"set role {ROL}; " + (f"set cf.autor = {_lit(autor)}; " if autor is not None else "")
    return pg.sql(prefijo + sentencia)


def _como(pg, rol: str, sentencia: str) -> str:
    return pg.sql(f"begin; set local role {rol}; {sentencia}; rollback;")


def _trabajadora(pg, farmacia="PIO", nombre=None, jornada="COMPLETA", horas=8, alta="2027-01-01",
                 baja=None) -> str:
    nombre = nombre or f"T-{uuid.uuid4().hex[:6]}"
    return _web(pg, "insert into public.trabajadoras (farmacia, nombre, categoria, tipo_jornada, horas_diarias, "
                    f"fecha_alta, fecha_baja) values ({_lit(farmacia)}, {_lit(nombre)}, 'TECNICA', {_lit(jornada)}, "
                    f"{horas}, {_lit(alta)}, {_lit(baja)}) returning id")


def _evento(pg, trabajadora, fecha="2027-02-01", franja="MANANA", tipo="JORNADA", farmacia="PIO", nota=None,
            horas=None, extra="") -> str:
    return _web(pg, "insert into public.eventos_calendario (trabajadora_id, farmacia, fecha, franja, tipo, estado, "
                    f"horas, nota) values ({_lit(trabajadora)}, {_lit(farmacia)}, {_lit(fecha)}, {_lit(franja)}, "
                    f"{_lit(tipo)}, 'PLANIFICADO', {_lit(horas)}, {_lit(nota)}) {extra} returning id")


@pytest.fixture
def pg31(pg17_nueva_base):
    return pg17_nueva_base("31")


# --------------------------------------------------------------------------- migracion

def test_rollback_31_devuelve_el_esquema_30(pg17_nueva_base):
    atras = pg17_nueva_base("31_rollback")
    assert esquema(atras) == esquema(pg17_nueva_base("30"))
    for o in DESPLIEGUE.OBJETOS:
        assert atras.sql(f"select to_regclass('public.{o}') is null") == "t"


def test_31_exige_la_30(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_30_AUSENTE"):
        pg17_nueva_base("29").sql(MIGRACION_31.read_text(encoding="utf-8"))


def test_31_no_altera_datos_ni_flags(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("30")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    configuracion = pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id")
    referencia = esquema(pg17_nueva_base("31"))
    pg.sql(MIGRACION_31.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_31.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id") == configuracion
    assert esquema(pg) == referencia and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_permiso_del_modulo(pg31):
    assert pg31.sql("select modulo || ':' || array_to_string(farmacias, ',') from public.cf_modulos_farmacias") == \
        "TRABAJADORES:PIO,RITA"


# --------------------------------------------------------------------------- rol de la web

def test_atributos_y_credencial_del_rol(pg31):
    [rol] = pg31.json(f"select r.rolcanlogin, r.rolsuper, r.rolbypassrls, r.rolcreaterole, r.rolcreatedb, "
                      f"r.rolreplication, r.rolinherit, r.rolconnlimit, r.rolconfig, a.rolpassword is null as "
                      f"sin_contrasena from pg_roles r join pg_authid a on a.oid = r.oid where r.rolname = '{ROL}'")
    assert rol == {"rolcanlogin": True, "rolsuper": False, "rolbypassrls": False, "rolcreaterole": False,
                   "rolcreatedb": False, "rolreplication": False, "rolinherit": False, "rolconnlimit": 5,
                   "rolconfig": ["statement_timeout=60s", "idle_in_transaction_session_timeout=60s"],
                   "sin_contrasena": True}
    assert pg31.sql(f"select count(*) from pg_auth_members where member = '{ROL}'::regrole") == "0"
    assert "password" not in MIGRACION_31.read_text(encoding="utf-8").lower()


def test_la_web_lee_inserta_y_actualiza_en_pio_y_rita(pg31):
    pio, rita = _trabajadora(pg31, "PIO"), _trabajadora(pg31, "RITA")
    _evento(pg31, rita, farmacia="RITA")
    _web(pg31, f"update public.trabajadoras set categoria = 'AUXILIAR' where id = {_lit(pio)}")
    _web(pg31, "insert into public.convenio_anual (anio, jornada_max_horas, asuntos_propios_dias, "
               "permiso_medico_horas, estado, fuente) values (2027, 1780, 2, 20, 'FIRMADO_PENDIENTE_PUBLICACION', "
               "'Convenio provincial')")
    _web(pg31, "update public.convenio_anual set estado = 'PUBLICADO' where anio = 2027")
    _web(pg31, "insert into public.guardias_farmacia (farmacia, fecha) values ('RITA', '2027-03-01')")
    _web(pg31, "insert into public.festivos (fecha, ambito, descripcion) values ('2027-01-06', 'NACIONAL', 'Reyes')")
    assert _web(pg31, "select string_agg(farmacia || ':' || categoria, ',' order by farmacia) "
                      "from public.trabajadoras") == "PIO:AUXILIAR,RITA:TECNICA"
    assert _web(pg31, "select horas_semanales_referencia || '|' || estado from public.convenio_anual") == \
        "40.00|PUBLICADO"
    assert _web(pg31, "select count(*) from public.v_eventos_calendario_horas") == "1"


@pytest.mark.parametrize("tabla", DESPLIEGUE.ESCRITURA)
def test_la_web_no_puede_borrar_ni_vaciar(pg31, tabla):
    for sentencia in (f"delete from public.{tabla}", f"truncate public.{tabla}"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _web(pg31, sentencia)


@pytest.mark.parametrize("sentencia", [
    "select count(*) from public.facturas",
    "select count(*) from public.documentos_facturas",
    "select count(*) from public.albaranes",
    "select count(*) from public.conciliaciones",
    "select count(*) from public.cf_configuracion",
    "update public.cf_configuracion set farmacias_habilitadas = array['PIO','RITA']",
    "insert into public.albaranes(farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,importe_pvp,"
    "importe_puc,descuento,estado) values ('RITA',990031,'2','x','x',current_date,1,1,0,'PENDIENTE')",
    "insert into public.trabajadores_historial (tabla, registro_id, operacion, despues, autor) "
    "values ('x', 'x', 'INSERT', '{}', 'Marc')",
    "update public.cf_modulos_farmacias set farmacias = array['PIO']",
    "insert into public.cf_modulos_farmacias values ('TRABAJADORES', array['PIO'])",
])
def test_la_web_no_toca_nada_fuera_del_modulo(pg31, sentencia):
    with pytest.raises(RuntimeError, match="permission denied"):
        _web(pg31, sentencia)


def test_la_web_no_ejecuta_funciones_privilegiadas_ni_que_escriben(pg31):
    ejecutables = pg31.sql(
        "select coalesce(string_agg(p.oid::regprocedure::text, ',' order by 1), '') from pg_proc p "
        f"where p.pronamespace = 'public'::regnamespace and has_function_privilege('{ROL}', p.oid, 'EXECUTE') "
        "and p.prorettype <> 'event_trigger'::regtype "
        "and (p.prosecdef or (p.provolatile = 'v' and p.prorettype <> 'trigger'::regtype))")
    assert ejecutables == ""
    for llamada in ("select public.cf_solicitar_reprocesado('00000000-0000-4000-8000-0000000002b0'::uuid, 'x')",
                    "select * from public.cf_reclamar_documento_normalizacion_manual_one_shot('x', 60)",
                    "select public.cf_trab_comprobar_farmacia()"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _web(pg31, llamada)
    assert pg31.sql(DESPLIEGUE.PRIVILEGIOS_WEB.join(("select ", ""))) == "t"


def test_inicio_de_sesion_real_del_rol(pg31):
    def sesion(sentencia):
        return subprocess.run(["docker", "exec", pg31.contenedor, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                               "-U", ROL, "-d", pg31.db, "-c", sentencia], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)

    assert sesion("show statement_timeout").stdout.strip() == "1min"
    r = sesion("begin; set local cf.autor = 'Marc'; insert into public.trabajadoras (farmacia, nombre, categoria, "
               "tipo_jornada, horas_diarias, fecha_alta) values ('RITA', 'Sesion', 'OTRA', 'MEDIA_TARDE', 4, "
               "'2027-01-01'); commit;")
    assert r.returncode == 0, r.stderr
    assert pg31.sql("select autor from public.trabajadores_historial where despues->>'nombre' = 'Sesion'") == "Marc"
    borrar = sesion("delete from public.trabajadoras")
    assert borrar.returncode != 0 and "permission denied" in borrar.stderr


# --------------------------------------------------------------------------- farmacias

def test_farmacia_fuera_del_modulo_se_rechaza_con_y_sin_rls(pg31):
    pg31.sql("update public.cf_modulos_farmacias set farmacias = array['PIO'] where modulo = 'TRABAJADORES'")
    # El trigger (antes que la RLS) lo impide para la web y para el propietario, que se salta la RLS.
    with pytest.raises(RuntimeError, match="FARMACIA_NO_HABILITADA_EN_MODULO:RITA"):
        _trabajadora(pg31, "RITA")
    with pytest.raises(RuntimeError, match="FARMACIA_NO_HABILITADA_EN_MODULO:RITA"):
        pg31.sql("set cf.autor = 'Marc'; insert into public.trabajadoras (farmacia, nombre, categoria, tipo_jornada, "
                 "horas_diarias, fecha_alta) values ('RITA', 'X', 'OTRA', 'COMPLETA', 8, '2027-01-01')")
    with pytest.raises(RuntimeError, match="FARMACIA_NO_HABILITADA_EN_MODULO:LUNA"):
        _trabajadora(pg31, "LUNA")
    # Sin el trigger, la RLS sola tambien lo impide a la web (segunda barrera).
    pg31.sql("alter table public.trabajadoras disable trigger trabajadoras_farmacia")
    with pytest.raises(RuntimeError, match="row-level security"):
        _trabajadora(pg31, "RITA")
    pg31.sql("alter table public.trabajadoras enable trigger trabajadoras_farmacia")
    assert _web(pg31, "select count(*) from public.trabajadoras") == "0"


def test_la_rls_oculta_las_farmacias_fuera_del_modulo(pg31):
    _trabajadora(pg31, "PIO")
    _trabajadora(pg31, "RITA")
    pg31.sql("update public.cf_modulos_farmacias set farmacias = array['PIO'] where modulo = 'TRABAJADORES'")
    for rol in (ROL, "cf_lectura"):
        assert _como(pg31, rol, "select string_agg(farmacia, ',') from public.trabajadoras") == "PIO"


def test_facturas_albaranes_y_conciliacion_siguen_solo_pio(pg31, tmp_path):
    pg = pg31
    _datos_previos(pg, tmp_path)
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    candidato = pgl._siguiente_candidato(pg)
    pg.sql("insert into public.documentos_facturas(id,farmacia,archivo_nombre,archivo_ruta,archivo_hash,"
           "fecha_importacion) values ('00000000-0000-4000-8000-000000000031','RITA','r.pdf','RITA/r.pdf',"
           f"{_lit(hashlib.sha256(b'rita-31').hexdigest())}, timestamptz '1990-01-01');")
    pg.sql("insert into public.albaranes(farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
           "importe_pvp,importe_puc,descuento,estado) values ('RITA',990031,'2','1.- SAFA','R-31',current_date,"
           "1,1,0,'PENDIENTE');")
    # El selector de normalizacion ignora el documento de RITA (aunque sea el mas antiguo).
    assert pgl._siguiente_candidato(pg) == candidato
    for tabla in ("documentos_facturas", "albaranes"):
        assert _como(pg, "cf_lectura", f"select count(*) from public.{tabla} where farmacia = 'RITA'") == "0"
    # La configuracion global no admite otra farmacia que PIO y RITA, y sigue en {PIO}.
    assert pg.sql("select farmacias_habilitadas::text from public.cf_configuracion where id") == "{PIO}"
    # Las funciones y politicas de facturas, albaranes y conciliacion no dependen del permiso del modulo.
    assert pg.sql("select count(*) from pg_proc p where p.pronamespace = 'public'::regnamespace "
                  "and p.proname not like 'cf_trab_%' and p.prosrc like '%cf_modulos_farmacias%'") == "0"
    assert pg.sql("select count(*) from pg_policy where polrelid not in (" + ", ".join(
        f"'public.{t}'::regclass" for t in DESPLIEGUE.TABLAS) + ") and pg_get_expr(polqual, polrelid) "
        "like '%cf_modulos_farmacias%'") == "0"


# --------------------------------------------------------------------------- dominios

@pytest.mark.parametrize("jornada,horas,ok", [
    ("COMPLETA", 8, True), ("COMPLETA", 7.5, False), ("MEDIA_MANANA", 4, True), ("MEDIA_TARDE", 7.99, True),
    ("MEDIA_TARDE", 8, False), ("MEDIA_MANANA", 0, False), ("MEDIA_MAÑANA", 4, False),
])
def test_horas_diarias_segun_la_jornada(pg31, jornada, horas, ok):
    if ok:
        _trabajadora(pg31, jornada=jornada, horas=horas)
    else:
        with pytest.raises(RuntimeError, match="violates check constraint"):
            _trabajadora(pg31, jornada=jornada, horas=horas)


@pytest.mark.parametrize("sentencia", [
    "insert into public.trabajadoras (farmacia, nombre, categoria, tipo_jornada, horas_diarias, fecha_alta) "
    "values ('PIO', 'X', 'DIRECTORA', 'COMPLETA', 8, '2027-01-01')",
    "insert into public.trabajadoras (farmacia, nombre, categoria, tipo_jornada, horas_diarias, fecha_alta, "
    "fecha_baja) values ('PIO', 'X', 'OTRA', 'COMPLETA', 8, '2027-01-01', '2026-12-31')",
    "insert into public.trabajadoras (farmacia, nombre, categoria, tipo_jornada, horas_diarias, fecha_alta) "
    "values ('PIO', ' X', 'OTRA', 'COMPLETA', 8, '2027-01-01')",
    "insert into public.convenio_anual (anio, jornada_max_horas, asuntos_propios_dias, permiso_medico_horas, estado, "
    "fuente) values (2027, 1780, 2, 20, 'VIGENTE', 'x')",
    "insert into public.festivos (fecha, ambito, descripcion) values ('2027-05-02', 'LOCAL', 'Sin farmacia')",
])
def test_valores_fuera_de_dominio(pg31, sentencia):
    with pytest.raises(RuntimeError, match="violates check constraint"):
        _web(pg31, sentencia)


def test_tipos_franjas_y_nota(pg31):
    t = _trabajadora(pg31)
    tipos = ("JORNADA", "VACACIONES", "ASUNTOS_PROPIOS", "PERMISO_RETRIBUIDO", "PERMISO_NO_RETRIBUIDO",
             "PERMISO_MEDICO", "DESCANSO_COMPENSATORIO", "BAJA", "FESTIVO", "TURNO_GUARDIA", "LOCALIZADA")
    for i, tipo in enumerate(tipos):
        _evento(pg31, t, fecha=str(dt.date(2027, 3, 1) + dt.timedelta(days=i)), tipo=tipo)
    for malo in ({"tipo": "TRABAJO"}, {"franja": "MAÑANA"}, {"franja": "NOCHE"}, {"nota": "x" * 201},
                 {"horas": 9}, {"horas": 0}):
        with pytest.raises(RuntimeError, match="violates check constraint"):
            _evento(pg31, t, fecha="2027-04-01", **malo)
    _evento(pg31, t, fecha="2027-04-01", nota="x" * 200)
    assert _web(pg31, "select count(*) from public.eventos_calendario") == str(len(tipos) + 1)


def test_evento_unico_y_on_conflict_no_pisa(pg31):
    t = _trabajadora(pg31)
    _evento(pg31, t, tipo="VACACIONES")
    with pytest.raises(RuntimeError, match="eventos_calendario_unico"):
        _evento(pg31, t)
    assert _evento(pg31, t, extra="on conflict (trabajadora_id, fecha, franja) do nothing") == ""
    assert _web(pg31, "select tipo from public.eventos_calendario") == "VACACIONES"


def test_evento_fuera_del_alta_o_de_otra_farmacia(pg31):
    t = _trabajadora(pg31, alta="2027-01-10", baja="2027-06-30")
    for fecha in ("2027-01-09", "2027-07-01"):
        with pytest.raises(RuntimeError, match="EVENTO_FUERA_DEL_ALTA"):
            _evento(pg31, t, fecha=fecha)
    with pytest.raises(RuntimeError, match="eventos_calendario_trabajadora"):
        _evento(pg31, t, farmacia="RITA")
    _web(pg31, f"update public.trabajadoras set anulada = true where id = {_lit(t)}")
    with pytest.raises(RuntimeError, match="EVENTO_FUERA_DEL_ALTA"):
        _evento(pg31, t)


def test_franja_contraria_de_media_jornada_se_acepta(pg31):
    t = _trabajadora(pg31, jornada="MEDIA_MANANA", horas=4)
    _evento(pg31, t, franja="TARDE")
    assert _web(pg31, "select horas_efectivas from public.v_eventos_calendario_horas") == "4.00"


def test_horas_por_defecto_y_explicitas(pg31):
    completa = _trabajadora(pg31)
    media = _trabajadora(pg31, jornada="MEDIA_TARDE", horas=3.75)
    _evento(pg31, completa, franja="MANANA")
    _evento(pg31, completa, franja="TARDE")
    _evento(pg31, completa, fecha="2027-02-02", franja="MANANA", tipo="PERMISO_MEDICO", horas=1.5)
    _evento(pg31, media, franja="TARDE")
    assert _web(pg31, "select string_agg(t.tipo_jornada || ':' || v.fecha || ':' || v.franja || ':' || "
                      "v.horas_efectivas, ',' order by t.tipo_jornada, v.fecha, v.franja) "
                      "from public.v_eventos_calendario_horas v join public.trabajadoras t on t.id = v.trabajadora_id") \
        == ("COMPLETA:2027-02-01:MANANA:4.50,COMPLETA:2027-02-01:TARDE:3.50,COMPLETA:2027-02-02:MANANA:1.50,"
            "MEDIA_TARDE:2027-02-01:TARDE:3.75")


# --------------------------------------------------------------------------- relleno del ano

# Relleno de referencia (lo hace la web con este INSERT; basta el privilegio INSERT): lunes a viernes, en las franjas
# de la jornada, dentro del alta y la baja; JORNADA en laborables y FESTIVO en los festivos de su farmacia o comunes;
# todos PLANIFICADO; nunca pisa un evento existente.
RELLENO = """
insert into public.eventos_calendario (trabajadora_id, farmacia, fecha, franja, tipo, estado)
select t.id, t.farmacia, d::date, f.franja,
       case when exists (select 1 from public.festivos x where x.fecha = d::date and not x.anulado
                         and (x.farmacia is null or x.farmacia = t.farmacia)) then 'FESTIVO' else 'JORNADA' end,
       'PLANIFICADO'
from public.trabajadoras t
cross join generate_series(make_date({anio}, 1, 1), make_date({anio}, 12, 31), interval '1 day') d
join (values ('MANANA'), ('TARDE')) f(franja)
  on t.tipo_jornada = 'COMPLETA' or (t.tipo_jornada = 'MEDIA_MANANA' and f.franja = 'MANANA')
  or (t.tipo_jornada = 'MEDIA_TARDE' and f.franja = 'TARDE')
where not t.anulada and extract(isodow from d) <= 5 and d::date >= t.fecha_alta
  and (t.fecha_baja is null or d::date <= t.fecha_baja)
on conflict (trabajadora_id, fecha, franja) do nothing
"""


def test_relleno_del_ano(pg31):
    pio = _trabajadora(pg31, "PIO", nombre="Completa", alta="2027-01-01")
    media = _trabajadora(pg31, "RITA", nombre="Media", jornada="MEDIA_TARDE", horas=4, alta="2027-07-01")
    _trabajadora(pg31, "PIO", nombre="Baja", alta="2026-01-01", baja="2026-12-31")
    _web(pg31, "insert into public.festivos (fecha, ambito, descripcion) values ('2027-01-06', 'NACIONAL', 'Reyes')")
    _web(pg31, "insert into public.festivos (fecha, ambito, farmacia, descripcion) "
               "values ('2027-01-07', 'LOCAL', 'RITA', 'Local RITA'), ('2027-09-06', 'LOCAL', 'RITA', 'Local RITA 2')")
    _web(pg31, "insert into public.festivos (fecha, ambito, descripcion, anulado) "
               "values ('2027-01-08', 'NACIONAL', 'Anulado', true)")
    # Un evento previo no se pisa.
    _evento(pg31, pio, fecha="2027-01-04", franja="MANANA", tipo="VACACIONES")
    _web(pg31, RELLENO.format(anio=2027))

    laborables = [d for d in (dt.date(2027, 1, 1) + dt.timedelta(days=i) for i in range(365)) if d.isoweekday() <= 5]
    eventos = {(r["trabajadora_id"], r["fecha"], r["franja"]): r["tipo"] for r in pg31.json(
        "select trabajadora_id, fecha::text, franja, tipo from public.eventos_calendario")}
    assert len([k for k in eventos if k[0] == pio]) == 2 * len(laborables)
    assert len([k for k in eventos if k[0] == media]) == len([d for d in laborables if d >= dt.date(2027, 7, 1)])
    assert {k[2] for k in eventos if k[0] == media} == {"TARDE"}
    assert eventos[(pio, "2027-01-06", "MANANA")] == eventos[(pio, "2027-01-06", "TARDE")] == "FESTIVO"
    assert eventos[(pio, "2027-01-07", "MANANA")] == "JORNADA"  # el local de RITA no es de PIO
    assert eventos[(pio, "2027-01-08", "MANANA")] == "JORNADA"  # festivo anulado
    assert eventos[(media, "2027-09-06", "TARDE")] == "FESTIVO"
    assert eventos[(pio, "2027-01-04", "MANANA")] == "VACACIONES"
    assert pg31.sql("select count(*) from public.eventos_calendario where estado <> 'PLANIFICADO' "
                    "or extract(isodow from fecha) > 5") == "0"
    assert len(eventos) == 2 * len(laborables) + len([d for d in laborables if d >= dt.date(2027, 7, 1)])
    # Un segundo relleno no cambia nada (ni eventos ni historial).
    huella = pg31.sql("select md5(string_agg(to_jsonb(e)::text, '' order by id)) from public.eventos_calendario e")
    historial = pg31.sql("select count(*) from public.trabajadores_historial")
    _web(pg31, RELLENO.format(anio=2027))
    assert pg31.sql("select md5(string_agg(to_jsonb(e)::text, '' order by id)) from public.eventos_calendario e") \
        == huella
    assert pg31.sql("select count(*) from public.trabajadores_historial") == historial


def test_festivo_trabajado_pasa_a_turno_de_guardia(pg31):
    t = _trabajadora(pg31)
    _web(pg31, "insert into public.festivos (fecha, ambito, descripcion) values ('2027-01-06', 'NACIONAL', 'Reyes')")
    _web(pg31, RELLENO.format(anio=2027))
    _web(pg31, f"update public.eventos_calendario set tipo = 'TURNO_GUARDIA', estado = 'CONFIRMADO' "
               f"where trabajadora_id = {_lit(t)} and fecha = '2027-01-06' and franja = 'MANANA'")
    assert pg31.sql("select antes->>'tipo' || '>' || (despues->>'tipo') from public.trabajadores_historial "
                    "where operacion = 'UPDATE'") == "FESTIVO>TURNO_GUARDIA"


# --------------------------------------------------------------------------- historial

def test_historial_con_autor_y_antes_despues(pg31):
    t = _trabajadora(pg31)
    _web(pg31, f"update public.trabajadoras set fecha_baja = '2027-12-31' where id = {_lit(t)}", autor="Pio")
    filas = pg31.json("select tabla, registro_id, farmacia, operacion, autor, antes->>'fecha_baja' as antes, "
                      "despues->>'fecha_baja' as despues from public.trabajadores_historial order by id")
    assert filas == [
        {"tabla": "trabajadoras", "registro_id": t, "farmacia": "PIO", "operacion": "INSERT", "autor": "Marc",
         "antes": None, "despues": None},
        {"tabla": "trabajadoras", "registro_id": t, "farmacia": "PIO", "operacion": "UPDATE", "autor": "Pio",
         "antes": None, "despues": "2027-12-31"}]
    _web(pg31, "insert into public.convenio_anual (anio, jornada_max_horas, asuntos_propios_dias, "
               "permiso_medico_horas, estado, fuente) values (2028, 1780, 2, 20, 'PUBLICADO', 'x')")
    assert pg31.sql("select registro_id || '|' || coalesce(farmacia, '-') from public.trabajadores_historial "
                    "where tabla = 'convenio_anual'") == "2028|-"
    assert _web(pg31, "select count(*) from public.trabajadores_historial") == "3"


@pytest.mark.parametrize("autor", [None, "", "   "])
def test_sin_autor_no_se_escribe_nada(pg31, autor):
    with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
        _web(pg31, "insert into public.trabajadoras (farmacia, nombre, categoria, tipo_jornada, horas_diarias, "
                   "fecha_alta) values ('PIO', 'X', 'OTRA', 'COMPLETA', 8, '2027-01-01')", autor=autor)
    assert pg31.sql("select count(*) from public.trabajadoras") == "0"
    assert pg31.sql("select count(*) from public.trabajadores_historial") == "0"


@pytest.mark.parametrize("sentencia", [
    "update public.trabajadores_historial set autor = 'otro'",
    "delete from public.trabajadores_historial",
    "truncate public.trabajadores_historial",
])
def test_historial_solo_de_insercion(pg31, sentencia):
    _trabajadora(pg31)
    with pytest.raises(RuntimeError, match="solo de insercion"):
        pg31.sql(sentencia)
    assert pg31.sql("select count(*) from public.trabajadores_historial") == "1"


# --------------------------------------------------------------------------- lectura y privilegios ajenos

@pytest.mark.parametrize("objeto", DESPLIEGUE.OBJETOS)
def test_cf_lectura_lee_cada_objeto(pg31, objeto):
    assert _como(pg31, "cf_lectura", f"select count(*) from public.{objeto}").isdigit()


@pytest.mark.parametrize("tabla", DESPLIEGUE.TABLAS)
def test_cf_lectura_no_escribe_y_anon_authenticated_no_ven(pg31, tabla):
    with pytest.raises(RuntimeError, match="permission denied"):
        _como(pg31, "cf_lectura", f"delete from public.{tabla}")
    for rol in ("anon", "authenticated"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _como(pg31, rol, f"select count(*) from public.{tabla}")


def test_nadie_mas_tiene_privilegios_sobre_el_modulo(pg31):
    """Ni anon, ni authenticated, ni el rol del sistema, ni PUBLIC: solo el propietario, la web y cf_lectura."""
    assert pg31.sql(DESPLIEGUE.ACL_AJENA) == "0"
    assert pg31.sql(DESPLIEGUE.ACL_AJENA_SECUENCIA) == "0"
    assert pg31.sql(DESPLIEGUE.ACL_AJENA_FUNCIONES) == "0"
    # La revocacion es necesaria: una tabla nueva de postgres recibe privilegios por defecto de otros roles.
    pg31.sql("create table public.zz_prueba_31 (x int)")
    try:
        ajenos = int(pg31.sql("select count(*) from pg_class c cross join lateral aclexplode(c.relacl) a "
                              "where c.oid = 'public.zz_prueba_31'::regclass and a.grantee <> c.relowner"))
    finally:
        pg31.sql("drop table public.zz_prueba_31")
    assert ajenos > 0


def test_politicas_y_rls(pg31):
    filas = pg31.json("select c.relname, c.relrowsecurity, count(p.*) as politicas from pg_class c "
                      "left join pg_policy p on p.polrelid = c.oid where c.oid = any(array[" + ", ".join(
                          f"'public.{t}'::regclass" for t in DESPLIEGUE.TABLAS) + "]) group by 1, 2 order by 1")
    assert {f["relname"]: (f["relrowsecurity"], f["politicas"]) for f in filas} == {
        "cf_modulos_farmacias": (True, 1), "convenio_anual": (True, 3), "eventos_calendario": (True, 3),
        "festivos": (True, 3), "guardias_farmacia": (True, 3), "trabajadoras": (True, 3),
        "trabajadores_historial": (True, 1)}


# --------------------------------------------------------------------------- desplegar_31.py

def test_sql_de_precondiciones_31_es_de_solo_lectura(pg17_nueva_base):
    sql = DESPLIEGUE.PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert pg17_nueva_base("30").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 7)
    assert pg17_nueva_base("31").sql("begin read only; " + sql + "; rollback;") == "|".join(["f"] + ["t"] * 6)


def test_postcondiciones_en_la_plantilla_31(pg31):
    # Columnas: datos (3), rol, privilegios de la web, ACL, RLS y modulo, propietarios (postgres = current_user).
    assert pg31.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[3:] == ["t"] * 5


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf31_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    """Copia byte a byte el script y la migracion a un repositorio git temporal con su commit."""
    for relativa in (RUTA_31, "pruebas/auditoria_trab/desplegar_31.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 31"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_31.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_trab/desplegar_31.py")


def test_ensayo_completo_despliegue_31_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "30"))
    _datos_previos(pg, tmp_path)
    # Como en produccion: el rol no existe en el cluster y se despliega con la imitacion del postgres de Supabase.
    assert pg.sql(f"select count(*) from pg_roles where rolname = '{ROL}'") == "0"
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
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "rol": True, "privilegios_web": True,
                                           "acl": True, "rls_y_modulo": True, "propietarios": True}
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    # Referencia (superusuario postgres, como el propietario en Supabase): mismo esquema salvo el propietario de los
    # objetos nuevos, que es el rol que despliega (postgres en Supabase).
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "30"))
    _datos_previos(referencia, tmp_path)
    referencia.sql(MIGRACION_31.read_text(encoding="utf-8"))
    assert esquema(pg).replace(pg.db, "").replace(f"OWNER TO {rol_despliegue};", "OWNER TO postgres;").replace(
        f"Owner: {rol_despliegue}", "Owner: postgres") == esquema(referencia).replace(referencia.db, "")
    # La web funciona sobre lo desplegado por la imitacion.
    _trabajadora(pg, "RITA")
    assert pg.sql("select count(*) from public.trabajadores_historial") == "1"

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: «31 ausente» falla, y aqui tambien «propietarios 2AX» (los objetos nuevos son de la imitacion; en
    # Supabase, de postgres).
    assert registro["precondiciones"] == [False, True, True, True, True, True, False]

    # El rollback tambien funciona con la imitacion: esquema 30 y datos como antes.
    atras = pgl.sql_como_supabase(pg, ROLLBACK_31.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    limpia = base_desde(nombre, pgl.construir_plantilla(nombre, "30"))
    assert esquema(pg).replace(pg.db, "") == esquema(limpia).replace(limpia.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_31
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_31_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
