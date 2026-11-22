"""Hito H7: migracion 38 (Cashflow) en PostgreSQL 17 local.

Plantillas (pg17_local): "37" (estado productivo), "38" = 37 + migracion 38 dos veces, "38_rollback" = 38 + rollback.
Diseno: pruebas/auditoria_h7/DISENO.md (C1-C8, E1-E7, propuestas de redondeo aprobadas; respuestas de Pio del
2026-11-22: saldos sin margen, categorias nuevas en el script 38-B). Se comprueba:
- rollback exacto al esquema 37, que falla cerrado con datos; la 38 exige la 37; idempotente; ningun dato cambia salvo
  la fila CASHFLOW = {PIO, RITA} del permiso por modulo;
- cuentas fijas (PIO, RITA, SL) y solo insercion en las cuatro tablas (SOLO_INSERCION, BORRADO_NO_PERMITIDO), con la
  unica excepcion del cambio de vigente dentro de la RPC;
- la RPC: OK -> importes, saldos y vigente (la anterior deja de serlo); ERROR -> solo la cabecera; todas sus
  validaciones fallan cerrado sin escribir nada; cuadre E1 con RS positivos y negativos y el signo de la celda;
  margen de 0,005 por importe redondeado y ninguno por saldo; E5 (SL sin saldo en la primera decena) y E7 (saldo de
  bancos distinto o vacio); decenas 1/11/21 con fin el 10, el 20 o el ultimo dia del mes;
- privilegios: cf_lectura lee con la RLS del modulo CASHFLOW (PIO, RITA y SL) y no escribe ni ejecuta la RPC; ningun
  rol de la web, anon ni authenticated; la RPC con los mismos beneficiarios que la firma de 8 parametros de la 37;
- noche y series: TABLAS_CASHFLOW = las tablas nuevas;
- desplegar_38.py ensayado con el rol que imita al postgres de Supabase (norma 2BN-D), segundo intento revertido y
  rollback con la imitacion;
- probar_acceso_cf_lectura_cashflow.py contra pg17_local.
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
from test_integracion_pg17_31_trabajadores import _como
from test_integracion_pg17_35_pagos import _sin_propietario

pytestmark = pytest.mark.pg17_local

MIGRACION_38 = MIG / "38_cf_cashflow.sql"
ROLLBACK_38 = MIG / "38_cf_cashflow.rollback.sql"
RUTA_38 = "sql/migrations/38_cf_cashflow.sql"
SCRIPT_38 = ROOT / "pruebas/auditoria_h7/desplegar_38.py"
SCRIPT_ACCESO = ROOT / "pruebas/auditoria_h7/probar_acceso_cf_lectura_cashflow.py"
TABLAS = ("cf_cashflow_cuentas", "cf_cashflow_importaciones", "cf_cashflow_importes", "cf_cashflow_saldos")
RPC = "public.cf_cashflow_registrar_importacion(jsonb,jsonb,jsonb)"
FIRMA_FALLO_8 = "public.cf_registrar_fallo_normalizacion(uuid,text,text,text,text,text,text,jsonb)"
CONTEOS = ("select (select count(*) from public.cf_cashflow_importaciones) || '|' || "
           "(select count(*) from public.cf_cashflow_importes) || '|' || "
           "(select count(*) from public.cf_cashflow_saldos)")


def _cargar(script, prefijo):
    spec = importlib.util.spec_from_file_location(f"{prefijo}_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar(SCRIPT_38, "desplegar_38")


@pytest.fixture
def pg38(pg17_nueva_base):
    return pg17_nueva_base("38")


def _hash() -> str:
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()


def _importe(cuenta="PIO", inicio="2026-01-01", fin="2026-01-10", categoria="RE Ventas", importe="1000.00",
             fila=10, **extra) -> dict:
    return {"cuenta": cuenta, "decena_inicio": inicio, "decena_fin": fin, "categoria": categoria,
            "concepto": "concepto de prueba", "importe": importe, "fila_excel": fila, **extra}


def _saldo(cuenta="PIO", inicio="2026-01-01", inicial="500.00", formulas="1000.00", bancos=None) -> dict:
    return {"cuenta": cuenta, "decena_inicio": inicio, "saldo_inicial": inicial, "saldo_formulas": formulas,
            "saldo_bancos": bancos}


def _ejemplo() -> tuple[list[dict], list[dict]]:
    """PIO: RE 1000, RS 300 (salida) y RS -50 (devolucion, suma): 500 + 1000 - 300 + 50 = 1250. RITA: 100 + 200 = 300,
    con saldo de bancos distinto (E7). SL: primera decena sin saldo ni importes (E5); segunda, saldo sin importes."""
    importes = [_importe(), _importe(categoria="RS Proveedores", importe="300.00", fila=20),
                _importe(categoria="RS Devoluciones", importe="-50.00", fila=21),
                _importe(cuenta="RITA", inicio="2026-01-11", fin="2026-01-20", importe="200.00", fila=12)]
    saldos = [_saldo(formulas="1250.00"), _saldo("RITA", "2026-01-11", "100.00", "300.00", "299.00"),
              _saldo("SL", "2026-01-11", "0.00", "0.00")]
    return importes, saldos


def _cabecera(estado="OK", filas=None, hash_=None, detalle=None, origen="MANUAL", **extra) -> dict:
    return {"archivo_nombre": "CASHFLOW 2026.xlsm", "archivo_hash": hash_ or _hash(), "origen": origen,
            "estado": estado, "detalle_error": detalle, "filas": filas, **extra}


def _registrar(pg, cabecera, importes, saldos) -> dict:
    return json.loads(pg.sql(f"select public.cf_cashflow_registrar_importacion({_lit(json.dumps(cabecera))}::jsonb, "
                             f"{_lit(json.dumps(importes))}::jsonb, {_lit(json.dumps(saldos))}::jsonb)::text"))


def _ok(pg, importes=None, saldos=None, **cabecera) -> dict:
    if importes is None:
        importes, saldos = _ejemplo()
    return _registrar(pg, _cabecera(filas=len(importes), **cabecera), importes, saldos)


def _vigentes(pg) -> list[str]:
    return [f["id"] for f in pg.json("select id from public.cf_cashflow_importaciones where vigente")]


# --------------------------------------------------------------------------- migracion y rollback

def test_rollback_38_devuelve_exactamente_el_esquema_37(pg17_nueva_base):
    atras = pg17_nueva_base("38_rollback")
    assert esquema(atras) == esquema(pg17_nueva_base("37"))
    assert esquema(pg17_nueva_base("38")) != esquema(pg17_nueva_base("37"))
    assert atras.sql("select count(*) from public.cf_modulos_farmacias where modulo = 'CASHFLOW'") == "0"
    for tabla in TABLAS:
        assert atras.sql(f"select to_regclass('public.{tabla}') is null") == "t"


def test_38_exige_la_37(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_37_AUSENTE"):
        pg17_nueva_base("36").sql(MIGRACION_38.read_text(encoding="utf-8"))


def test_38_idempotente_sin_cambiar_datos_ni_flags(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("37")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    configuracion = pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id")
    trabajadores = pg.sql("select farmacias::text from public.cf_modulos_farmacias where modulo = 'TRABAJADORES'")
    pg.sql(MIGRACION_38.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_38.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id") == configuracion
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert pg.sql("select string_agg(modulo || '=' || farmacias::text, ',' order by modulo) "
                  "from public.cf_modulos_farmacias") == f"CASHFLOW={{PIO,RITA}},TRABAJADORES={trabajadores}"
    assert esquema(pg) == esquema(pg17_nueva_base("38"))


def test_rollback_falla_cerrado_con_datos(pg38):
    _ok(pg38)
    conteos = pg38.sql(CONTEOS)
    with pytest.raises(RuntimeError, match="ROLLBACK_38_CASHFLOW_CON_DATOS"):
        pg38.sql(ROLLBACK_38.read_text(encoding="utf-8"))
    assert pg38.sql(CONTEOS) == conteos
    assert pg38.sql("select count(*) from public.cf_modulos_farmacias where modulo = 'CASHFLOW'") == "1"


def test_permiso_por_modulo_solo_admite_trabajadores_y_cashflow(pg38):
    with pytest.raises(RuntimeError, match="cf_modulos_farmacias_modulo_check"):
        pg38.sql("insert into public.cf_modulos_farmacias (modulo, farmacias) values ('FACTURAS', array['RITA'])")
    assert pg38.sql("select farmacias_habilitadas::text from public.cf_configuracion where id") == "{PIO}"


# --------------------------------------------------------------------------- cuentas y solo insercion

def test_cuentas_fijas(pg38):
    assert pg38.sql("select string_agg(codigo || ':' || coalesce(farmacia, '-') || ':' || hoja, ',' order by codigo) "
                    "from public.cf_cashflow_cuentas") == DESPLIEGUE.CUENTAS_ESPERADAS
    with pytest.raises(RuntimeError, match="cf_cashflow_cuentas_fija"):
        pg38.sql("insert into public.cf_cashflow_cuentas (codigo, farmacia, hoja) values ('SL', 'PIO', 'SL')")


@pytest.mark.parametrize("sentencia, error", [
    ("update public.cf_cashflow_cuentas set hoja = 'X' where codigo = 'SL'", "SOLO_INSERCION"),
    ("delete from public.cf_cashflow_cuentas where codigo = 'SL'", "BORRADO_NO_PERMITIDO"),
    ("truncate public.cf_cashflow_cuentas cascade", "BORRADO_NO_PERMITIDO"),
    ("update public.cf_cashflow_importes set importe = 1", "SOLO_INSERCION"),
    ("delete from public.cf_cashflow_saldos", "BORRADO_NO_PERMITIDO"),
    ("truncate public.cf_cashflow_importes", "BORRADO_NO_PERMITIDO"),
    ("truncate public.cf_cashflow_saldos", "BORRADO_NO_PERMITIDO"),
    ("delete from public.cf_cashflow_importaciones", "BORRADO_NO_PERMITIDO"),
    ("update public.cf_cashflow_importaciones set vigente = false", "SOLO_INSERCION"),
    ("update public.cf_cashflow_importaciones set origen = 'NOCHE'", "SOLO_INSERCION"),
])
def test_solo_insercion(pg38, sentencia, error):
    _ok(pg38)
    conteos = pg38.sql(CONTEOS)
    with pytest.raises(RuntimeError, match=error):
        pg38.sql(sentencia)
    assert pg38.sql(CONTEOS) == conteos


def test_la_excepcion_de_vigente_solo_cambia_vigente_y_nunca_a_un_error(pg38):
    _ok(pg38)
    _registrar(pg38, _cabecera("ERROR", 0, detalle="EXCEL_AMBIGUO"), [], [])
    # Con la variable puesta (fuera de la RPC) tampoco se cambia otra columna ni se hace vigente un ERROR.
    with pytest.raises(RuntimeError, match="SOLO_INSERCION"):
        pg38.sql("begin; select set_config('cf.cashflow_vigente', 'on', true); "
                 "update public.cf_cashflow_importaciones set vigente = false, filas = filas + 1 where vigente; commit;")
    with pytest.raises(RuntimeError, match="SOLO_INSERCION"):
        pg38.sql("begin; select set_config('cf.cashflow_vigente', 'on', true); "
                 "update public.cf_cashflow_importaciones set vigente = false where vigente; "
                 "update public.cf_cashflow_importaciones set vigente = true where estado = 'ERROR'; commit;")
    assert len(_vigentes(pg38)) == 1


# --------------------------------------------------------------------------- RPC

def test_importacion_ok_guarda_importes_saldos_y_la_hace_vigente(pg38):
    r = _ok(pg38)
    assert (r["estado"], r["vigente"], r["importes"], r["saldos"], r["anterior"]) == ("OK", True, 4, 3, None)
    assert _vigentes(pg38) == [r["importacion_id"]]
    # Signo de la celda (E1) y farmacia copiada de la cuenta (null en SL).
    assert pg38.sql("select string_agg(cuenta || ':' || coalesce(farmacia, '-') || ':' || categoria || ':' || "
                    "importe, ',' order by fila_excel) from public.cf_cashflow_importes") == (
        "PIO:PIO:RE Ventas:1000.00,RITA:RITA:RE Ventas:200.00,PIO:PIO:RS Proveedores:300.00,"
        "PIO:PIO:RS Devoluciones:-50.00")
    assert pg38.sql("select string_agg(cuenta || ':' || coalesce(farmacia, '-') || ':' || saldo_inicial || ':' || "
                    "saldo_formulas || ':' || coalesce(saldo_bancos::text, 'null'), ',' order by cuenta) "
                    "from public.cf_cashflow_saldos") == (
        "PIO:PIO:500.00:1250.00:null,RITA:RITA:100.00:300.00:299.00,SL:-:0.00:0.00:null")
    assert pg38.sql("select filas || ':' || origen || ':' || (detalle_error is null) "
                    "from public.cf_cashflow_importaciones") == "4:MANUAL:true"


def test_una_nueva_ok_sustituye_a_la_vigente_y_un_error_no(pg38):
    primera = _ok(pg38)["importacion_id"]
    segunda = _ok(pg38, origen="NOCHE")
    assert (segunda["anterior"], _vigentes(pg38)) == (primera, [segunda["importacion_id"]])
    error = _registrar(pg38, _cabecera("ERROR", 0, detalle="CUADRE_NO_VALIDO:3"), [], [])
    assert (error["estado"], error["vigente"], error["importes"]) == ("ERROR", False, 0)
    assert _vigentes(pg38) == [segunda["importacion_id"]]
    assert pg38.sql("select count(*) from public.cf_cashflow_importes "
                    f"where importacion_id = {_lit(error['importacion_id'])}") == "0"


def _caso(nombre):
    importes, saldos = _ejemplo()
    cabecera = _cabecera(filas=len(importes))
    if nombre == "hash_repetido":
        cabecera["archivo_hash"] = "a" * 64
    elif nombre == "error_con_datos":
        cabecera.update(estado="ERROR", detalle_error="X", filas=0)
    elif nombre == "filas":
        cabecera["filas"] = 3
    elif nombre == "vacia":
        importes, saldos, cabecera["filas"] = [], [], 0
    elif nombre == "cuenta":
        importes[0]["cuenta"] = "OTRA"
    elif nombre == "decena_inicio":
        importes[0].update(decena_inicio="2026-01-05")
    elif nombre == "decena_fin":
        importes[0].update(decena_fin="2026-01-11")
    elif nombre == "decena_saldo":
        saldos[0]["decena_inicio"] = "2026-01-02"
    elif nombre == "categoria":
        importes[0]["categoria"] = "XX Otra"
    elif nombre == "cero":
        importes.append(_importe(categoria="RE Otra", importe="0", fila=30))
        cabecera["filas"] = 5
    elif nombre == "decimales":
        importes[0]["importe"] = "1000.004"
    elif nombre == "saldo_decimales":
        saldos[0]["saldo_inicial"] = "500.001"
    elif nombre == "saldo_repetido":
        saldos.append(_saldo(formulas="1250.00"))
    elif nombre == "sin_saldo":
        saldos = saldos[1:]
    elif nombre == "cuadre":
        saldos[0]["saldo_formulas"] = "1150.00"  # suma literal: RS como entrada
    elif nombre == "clave":
        importes[0]["otra"] = 1
    elif nombre == "clave_cabecera":
        cabecera["vigente"] = True
    elif nombre == "nombre_con_ruta":
        cabecera["archivo_nombre"] = r"C:\GoogleDrive\CASHFLOW\CASHFLOW.xlsm"
    elif nombre == "hash_no_valido":
        cabecera["archivo_hash"] = "ABC"
    elif nombre == "origen":
        cabecera["origen"] = "WEB"
    elif nombre == "incompleto":
        del importes[0]["fila_excel"]
    return cabecera, importes, saldos


@pytest.mark.parametrize("nombre, error", [
    ("hash_repetido", "HASH_YA_IMPORTADO"), ("error_con_datos", "ERROR_CON_DATOS"), ("filas", "FILAS_NO_COINCIDEN"),
    ("vacia", "IMPORTACION_OK_VACIA"), ("cuenta", "CUENTA_DESCONOCIDA"), ("decena_inicio", "DECENA_NO_VALIDA"),
    ("decena_fin", "DECENA_NO_VALIDA"), ("decena_saldo", "DECENA_NO_VALIDA"), ("categoria", "CATEGORIA_SIN_PREFIJO"),
    ("cero", "IMPORTE_CERO"), ("decimales", "IMPORTE_CON_MAS_DE_2_DECIMALES"),
    ("saldo_decimales", "SALDO_CON_MAS_DE_2_DECIMALES"), ("saldo_repetido", "SALDO_REPETIDO"),
    ("sin_saldo", "IMPORTES_SIN_SALDO"), ("cuadre", "CUADRE_NO_VALIDO"), ("clave", "CLAVE_NO_ADMITIDA:importes"),
    ("clave_cabecera", "CLAVE_NO_ADMITIDA:importacion"), ("nombre_con_ruta", "check"),
    ("hash_no_valido", "check"), ("origen", "check"), ("incompleto", "IMPORTE_INCOMPLETO"),
])
def test_la_rpc_falla_cerrado_sin_escribir_nada(pg38, nombre, error):
    previa = _ok(pg38, hash_="a" * 64)["importacion_id"]
    conteos = pg38.sql(CONTEOS)
    cabecera, importes, saldos = _caso(nombre)
    with pytest.raises(RuntimeError, match=error):
        _registrar(pg38, cabecera, importes, saldos)
    assert pg38.sql(CONTEOS) == conteos and _vigentes(pg38) == [previa]


@pytest.mark.parametrize("formulas, redondeados, cuadra", [
    ("1250.00", 0, True), ("1250.01", 0, False), ("1250.004", None, None),
    ("1250.00", 1, True), ("1250.01", 2, True), ("1250.01", 1, False), ("1250.01", 3, True)])
def test_margen_de_cuadre_por_importe_redondeado(pg38, formulas, redondeados, cuadra):
    """Propuesta aprobada: hasta 0,005 por importe redondeado de esa cuenta y decena; 0 sin ninguno."""
    importes, saldos = _ejemplo()
    if redondeados is None:  # el saldo con mas de 2 decimales no se admite (lo redondea el script)
        saldos[0]["saldo_formulas"] = formulas
        with pytest.raises(RuntimeError, match="SALDO_CON_MAS_DE_2_DECIMALES"):
            _ok(pg38, importes, saldos)
        return
    for i in range(redondeados):
        importes[i]["redondeado"] = True
    saldos[0]["saldo_formulas"] = formulas
    if cuadra:
        assert _ok(pg38, importes, saldos)["estado"] == "OK"
    else:
        with pytest.raises(RuntimeError, match="CUADRE_NO_VALIDO"):
            _ok(pg38, importes, saldos)


def test_sin_margen_por_saldo_redondeado(pg38):
    """Decision de Pio (2026-11-22): un saldo redondeado no da margen; el redondeado de otra cuenta tampoco."""
    importes, saldos = _ejemplo()
    importes[3]["redondeado"] = True  # RITA
    saldos[0]["saldo_formulas"] = "1250.01"  # PIO
    with pytest.raises(RuntimeError, match="CUADRE_NO_VALIDO"):
        _ok(pg38, importes, saldos)


def test_decenas_validas_hasta_el_ultimo_dia_del_mes(pg38):
    importes = [_importe(inicio="2028-02-21", fin="2028-02-29"), _importe(inicio="2026-02-21", fin="2026-02-28",
                                                                          fila=11),
                _importe(inicio="2026-01-21", fin="2026-01-31", fila=12)]
    saldos = [_saldo(inicio="2028-02-21", formulas="1500.00"), _saldo(inicio="2026-02-21", formulas="1500.00"),
              _saldo(inicio="2026-01-21", formulas="1500.00")]
    assert _ok(pg38, importes, saldos)["importes"] == 3
    with pytest.raises(RuntimeError, match="DECENA_NO_VALIDA"):
        _ok(pg38, [_importe(inicio="2026-02-21", fin="2026-02-27")], [_saldo(inicio="2026-02-21", formulas="1500.00")])


def test_sl_sin_saldo_en_la_primera_decena_solo_sin_importes(pg38):
    """E5: la decena de SL sin saldo no tiene fila de saldos y no puede llevar importes."""
    importes, saldos = _ejemplo()
    assert _ok(pg38, importes, saldos)["estado"] == "OK"
    importes.append(_importe(cuenta="SL", inicio="2026-01-01", importe="10.00", fila=40))
    with pytest.raises(RuntimeError, match="IMPORTES_SIN_SALDO"):
        _ok(pg38, importes, saldos)


# --------------------------------------------------------------------------- privilegios y RLS

def test_cf_lectura_lee_con_la_rls_del_modulo_cashflow(pg38):
    _ok(pg38)
    visibles = ("select (select string_agg(codigo, ',' order by codigo) from public.cf_cashflow_cuentas) || '|' || "
                "(select string_agg(distinct coalesce(farmacia, 'SL'), ',' order by coalesce(farmacia, 'SL')) "
                "from public.cf_cashflow_saldos) || '|' || "
                "(select string_agg(distinct farmacia, ',' order by farmacia) from public.cf_cashflow_importes) || '|' || "
                "(select count(*) from public.cf_cashflow_importaciones)")
    assert _como(pg38, "cf_lectura", visibles) == "PIO,RITA,SL|PIO,RITA,SL|PIO,RITA|1"
    # Sin RITA en el modulo, RITA deja de verse; SL (sin farmacia) sigue visible.
    pg38.sql("update public.cf_modulos_farmacias set farmacias = array['PIO'] where modulo = 'CASHFLOW'")
    assert _como(pg38, "cf_lectura", visibles) == "PIO,SL|PIO,SL|PIO|1"


@pytest.mark.parametrize("sentencia", [
    "insert into public.cf_cashflow_importaciones (archivo_nombre, archivo_hash, origen, estado, filas) "
    f"values ('x', '{'b' * 64}', 'MANUAL', 'ERROR', 0)",
    "delete from public.cf_cashflow_saldos",
    "update public.cf_cashflow_cuentas set hoja = hoja",
    f"select public.cf_cashflow_registrar_importacion('{{}}'::jsonb, '[]'::jsonb, '[]'::jsonb)",
])
def test_cf_lectura_no_escribe_ni_ejecuta_la_rpc(pg38, sentencia):
    with pytest.raises(RuntimeError, match="permission denied"):
        _como(pg38, "cf_lectura", sentencia)


@pytest.mark.parametrize("rol", ["anon", "authenticated", "cf_trabajadores_web", "cf_pagos_web"])
def test_ni_la_web_ni_anon_ni_authenticated_tocan_cashflow(pg38, rol):
    for tabla in TABLAS:
        with pytest.raises(RuntimeError, match="permission denied"):
            _como(pg38, rol, f"select count(*) from public.{tabla}")
    with pytest.raises(RuntimeError, match="permission denied"):
        _como(pg38, rol, f"select public.cf_cashflow_registrar_importacion('{{}}'::jsonb, '[]'::jsonb, '[]'::jsonb)")


def test_acl_de_lo_nuevo(pg38):
    """Tablas: propietario y SELECT de cf_lectura; secuencias y trigger: solo el propietario; RPC: los mismos
    beneficiarios que la firma de 8 parametros de la 37 (un unico rol) y nada para anon, authenticated ni PUBLIC."""
    for consulta in (DESPLIEGUE.ACL_TABLAS_AJENA, DESPLIEGUE.ACL_SECUENCIAS_AJENA, DESPLIEGUE.ACL_TRIGGER_AJENA):
        assert pg38.sql(consulta) == "0"
    beneficiarios = pg38.sql(f"select {DESPLIEGUE._beneficiarios(RPC)}")
    assert beneficiarios and beneficiarios == pg38.sql(f"select {DESPLIEGUE._beneficiarios(FIRMA_FALLO_8)}")
    assert "," not in beneficiarios
    assert pg38.sql(f"select prosecdef::text || '|' || pg_get_userbyid(proowner) from pg_proc "
                    f"where oid = '{RPC}'::regprocedure") == "true|postgres"
    assert pg38.sql(f"select {DESPLIEGUE.RPC_PRIVILEGIOS}") == "t"


def test_el_sistema_de_facturas_no_usa_cashflow(pg38):
    assert pg38.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert pg38.sql("select count(*) from pg_proc p where p.pronamespace = 'public'::regnamespace "
                    "and p.proname not like 'cf_cashflow_%' and p.prosrc like '%cf_cashflow_%'") == "0"


def test_la_noche_y_las_series_tratan_cashflow_aparte():
    from src.facturas.runtime_supabase import noche_automatica as na

    assert na.TABLAS_CASHFLOW == set(TABLAS) == set(DESPLIEGUE.TABLAS_NUEVAS)
    assert na.TABLAS_CASHFLOW <= na.TABLAS_FUERA_DEL_SNAPSHOT


# --------------------------------------------------------------------------- desplegar_38.py

def test_sql_de_precondiciones_38_es_de_solo_lectura(pg17_nueva_base):
    sql = DESPLIEGUE.PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert pg17_nueva_base("37").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 6)
    assert pg17_nueva_base("38").sql("begin read only; " + sql + "; rollback;") == "|".join(["f"] + ["t"] * 5)
    assert pg17_nueva_base("36").sql("begin read only; " + sql + "; rollback;").split("|")[:2] == ["t", "f"]


def test_postcondiciones_en_la_plantilla_38(pg38):
    assert pg38.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[-4:] == ["t"] * 4


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf38_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    for relativa in (RUTA_38, "pruebas/auditoria_h7/desplegar_38.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 38"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_38.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar(destino / "pruebas/auditoria_h7/desplegar_38.py", "desplegar_38_copia")


def test_ensayo_completo_despliegue_38_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "37"))
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
    esquema_37 = esquema(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 6
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "estructura_y_rls": True,
                                           "privilegios_y_acl": True, "rpc_y_beneficiarios": True,
                                           "propietario": True}
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    # Referencia (superusuario postgres, como el propietario en Supabase): mismo esquema salvo el propietario de los
    # objetos nuevos, que es el rol que despliega (postgres en Supabase).
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "37"))
    referencia.sql(MIGRACION_38.read_text(encoding="utf-8"))
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema(referencia).replace(referencia.db, "")
    # La RPC funciona sobre lo desplegado por la imitacion y cf_lectura lee lo importado.
    assert _ok(pg)["estado"] == "OK"
    assert _como(pg, "cf_lectura", "select count(*) from public.cf_cashflow_saldos") == "3"

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: «38 ausente» falla, y aqui tambien «propietarios 2AX» (las tablas nuevas son de la imitacion; en
    # Supabase, de postgres).
    assert registro["precondiciones"] == [False, True, True, True, True, False]

    # El rollback falla cerrado con datos y funciona con la imitacion sin ellos: esquema 37.
    con_datos = pgl.sql_como_supabase(pg, ROLLBACK_38.read_text(encoding="utf-8"))
    assert con_datos.returncode != 0 and "ROLLBACK_38_CASHFLOW_CON_DATOS" in con_datos.stderr
    pg.sql("set session_replication_role = replica; delete from public.cf_cashflow_importes; "
           "delete from public.cf_cashflow_saldos; delete from public.cf_cashflow_importaciones")
    atras = pgl.sql_como_supabase(pg, ROLLBACK_38.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema_37.replace(pg.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_38
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_38_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")


# --------------------------------------------------------------------------- probar_acceso_cf_lectura_cashflow.py

def test_prueba_de_acceso_contra_pg17_local(contenedor_tcp):
    nombre, puerto, _plantilla = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "38"))
    _ok(pg)
    pg.sql("set password_encryption = 'scram-sha-256'; alter role cf_lectura password 'local-only'")
    antes = pg.sql(CONTEOS)
    try:
        resultado = _cargar(SCRIPT_ACCESO, "acceso_h7").probar("127.0.0.1", puerto, "cf_lectura", "local-only",
                                                               dbname=pg.db, sslmode="disable")
    finally:
        pg.sql("alter role cf_lectura password null")
    assert resultado["veredicto"] == "ACCESO_OK", resultado
    assert resultado["cuentas_visibles"] == ["PIO", "RITA", "SL"]
    assert resultado["farmacias_saldos"] == ["PIO", "RITA", "SL"]
    assert resultado["modulo_cashflow"] == ["PIO", "RITA"]
    assert resultado["conteos"] == {"cf_cashflow_cuentas": 3, "cf_cashflow_importaciones": 1,
                                    "cf_cashflow_importes": 4, "cf_cashflow_saldos": 3}
    for clave in ("insert_importacion", "update_cuentas", "delete_saldos", "rpc_importacion"):
        assert resultado[clave]["falla"], (clave, resultado[clave])
    assert pg.sql(CONTEOS) == antes


def test_prueba_de_acceso_sin_contrasena_no_conecta(monkeypatch):
    acceso = _cargar(SCRIPT_ACCESO, "acceso_h7")
    monkeypatch.delenv(acceso.VARIABLE, raising=False)
    monkeypatch.setattr(acceso, "probar", lambda *a, **k: pytest.fail("no debe conectar"))
    assert acceso.VARIABLE == "CF_LECTURA_PASSWORD"
    assert acceso.main(["host", "5432"]) == 2
    with pytest.raises(SystemExit):
        acceso.main(["host", "5432", "contrasena-como-argumento"])


def test_prueba_de_acceso_no_imprime_la_contrasena(monkeypatch, capsys):
    acceso = _cargar(SCRIPT_ACCESO, "acceso_h7")
    secreto = "secreto-" + uuid.uuid4().hex
    monkeypatch.setenv(acceso.VARIABLE, secreto)
    recibidos = []

    def falla(host, puerto, usuario, contrasena, **_k):
        recibidos.append((usuario, contrasena))
        raise RuntimeError("conexion rechazada")

    monkeypatch.setattr(acceso, "probar", falla)
    assert acceso.main(["host", "5432"]) == 2
    assert recibidos == [(f"cf_lectura.{acceso.PROJECT_REF}", secreto)]
    assert secreto not in capsys.readouterr().out
