"""Hito H7b: migracion 40 (prevision de Cashflow: conceptos, recurrentes y apuntes de la web) en PostgreSQL 17 local.

Plantillas (pg17_local): "39" (estado productivo), "40" = 39 + migracion 40 dos veces, "40_rollback" = 40 + rollback.
Diseno: pruebas/auditoria_h7b/DISENO.md (corregido y aprobado por Pio; OK del 2026-11-26). Se comprueba:
- rollback exacto al esquema 39, que falla cerrado con datos; la 40 exige la 39; idempotente; ningun dato cambia;
- la web (cf_cashflow_web) da de alta conceptos, recurrentes y apuntes con autor e historial, y solo anula; nadie borra
  ni vacia; no se reabre ni se cambia el importe;
- cada validacion de §3 rechaza con su motivo sin escribir nada;
- ocurrencias: mensual el dia 31 en febrero (ultimo dia), trimestral y anual desde inicio, fin opcional, una ocurrencia
  anulada, recurrente anulada; la BD no elige fuente por celda ni calcula la media;
- sustitucion confirmada: anula el apunte (o la ocurrencia) con la factura y el orden del vencimiento, validados;
- RLS del modulo CASHFLOW (PIO y RITA) para la web y cf_lectura; RITA ve sus apuntes y ninguna factura; privilegios
  minimos y ningun privilegio ajeno (anon, authenticated, el rol del sistema ni PUBLIC) sobre lo nuevo;
- una importacion nueva no toca los apuntes y los apuntes no cambian el cuadre E1; el sistema no los lee;
- desplegar_40.py ensayado con el rol que imita al postgres de Supabase (norma 2BN-D), segundo intento revertido y
  rollback con la imitacion; probar_acceso_cf_cashflow_web.py contra pg17_local.
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
from test_integracion_pg17_38_cashflow import _cabecera, _importe, _registrar, _saldo

pytestmark = pytest.mark.pg17_local

MIGRACION_40 = MIG / "40_cf_cashflow_prevision.sql"
ROLLBACK_40 = MIG / "40_cf_cashflow_prevision.rollback.sql"
RUTA_40 = "sql/migrations/40_cf_cashflow_prevision.sql"
SCRIPT_40 = ROOT / "pruebas/auditoria_h7b/desplegar_40.py"
SCRIPT_ACCESO = ROOT / "pruebas/auditoria_h7b/probar_acceso_cf_cashflow_web.py"
ROL = "cf_cashflow_web"
CONCEPTOS, RECURRENTES, APUNTES = "cf_cashflow_conceptos", "cf_cashflow_recurrentes", "cf_cashflow_apuntes"
HISTORIAL = "cf_cashflow_apuntes_historial"
TABLAS = (CONCEPTOS, RECURRENTES, APUNTES, HISTORIAL)
CONTEOS = "select " + " || '|' || ".join(f"(select count(*) from public.{t})" for t in TABLAS)


def _cargar(script, prefijo):
    spec = importlib.util.spec_from_file_location(f"{prefijo}_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar(SCRIPT_40, "desplegar_40")


def _web(pg, sentencia: str, autor: str | None = "Marc") -> str:
    """Como el rol de la web (SET ROLE), con el autor que fija la web; cada sentencia se confirma."""
    prefijo = f"set role {ROL}; " + (f"set cf.autor = {_lit(autor)}; " if autor is not None else "")
    return pg.sql(prefijo + sentencia)


# Importacion vigente de ejemplo. PIO: decena 1-10/01 cuadrada con el banco (700) y 11-20/01 sin saldo de bancos (E7):
# el ultimo saldo de bancos de PIO es el 2026-01-10. RITA: 11-20/01 cuadrada: ultimo saldo el 2026-01-20. Plantilla:
# PIO «RE Ventas» (Ventas mostrador) y «RS Proveedores» (Alliance); RITA «RE Ventas» (Ventas RITA).
ULTIMO_PIO, ULTIMO_RITA = "2026-01-10", "2026-01-20"


def _importacion(pg, bancos_pio="700.00") -> dict:
    importes = [
        _importe(categoria="RE Ventas", importe="1000.00", fila=10) | {"concepto": "Ventas mostrador"},
        _importe(categoria="RS Proveedores", importe="300.00", fila=20) | {"concepto": "Alliance"},
        _importe(inicio="2026-01-11", fin="2026-01-20", categoria="RE Ventas", importe="500.00", fila=10)
        | {"concepto": "Ventas mostrador"},
        _importe(cuenta="RITA", inicio="2026-01-11", fin="2026-01-20", categoria="RE Ventas", importe="200.00",
                 fila=12) | {"concepto": "Ventas RITA"},
    ]
    saldos = [_saldo("PIO", "2026-01-01", "0.00", "700.00", bancos_pio),
              _saldo("PIO", "2026-01-11", "700.00", "1200.00", None),
              _saldo("RITA", "2026-01-11", "100.00", "300.00", "300.00")]
    return _registrar(pg, _cabecera(filas=len(importes)), importes, saldos)


@pytest.fixture
def pg40(pg17_nueva_base):
    pg = pg17_nueva_base("40")
    assert _importacion(pg)["vigente"] is True
    return pg


def _concepto(pg, nombre="Seguro local", cuenta="PIO", categoria="RS Proveedores", cif=None, autor="Marc") -> str:
    return _web(pg, f"insert into public.{CONCEPTOS} (cuenta, categoria, nombre, proveedor_cif) values "
                    f"({_lit(cuenta)}, {_lit(categoria)}, {_lit(nombre)}, {_lit(cif) if cif else 'null'}) "
                    "returning id", autor=autor)


def _apunte(pg, fecha="2026-01-15", importe="120.00", cuenta="PIO", categoria="RE Ventas",
            concepto="Ventas mostrador", nota=None, autor="Marc") -> str:
    return _web(pg, f"insert into public.{APUNTES} (cuenta, fecha, categoria, concepto, importe, nota) values "
                    f"({_lit(cuenta)}, {_lit(fecha)}, {_lit(categoria)}, {_lit(concepto)}, "
                    f"{_lit(importe) if importe is not None else 'null'}, {_lit(nota) if nota else 'null'}) "
                    "returning id", autor=autor)


def _recurrente(pg, frecuencia="MENSUAL", dia=31, inicio="2026-01-31", fin=None, importe="50.00", cuenta="PIO",
                categoria="RS Proveedores", concepto="Alliance", autor="Marc") -> str:
    return _web(pg, f"insert into public.{RECURRENTES} (cuenta, categoria, concepto, importe, frecuencia, dia, inicio, "
                    f"fin) values ({_lit(cuenta)}, {_lit(categoria)}, {_lit(concepto)}, "
                    f"{_lit(importe) if importe is not None else 'null'}, {_lit(frecuencia)}, "
                    f"{dia if dia is not None else 'null'}, {_lit(inicio)}, {_lit(fin) if fin else 'null'}) "
                    "returning id", autor=autor)


def _anular_ocurrencia(pg, recurrente, fecha, factura=None, orden=None, autor="Marc") -> str:
    return _web(pg, f"insert into public.{APUNTES} (recurrente_id, fecha_ocurrencia, fecha, cuenta, categoria, "
                    f"concepto, sustituido_factura_id, sustituido_vencimiento_orden) values ({_lit(recurrente)}, "
                    f"{_lit(fecha)}, {_lit(fecha)}, 'PIO', 'x', 'x', {_lit(factura) if factura else 'null'}, "
                    f"{orden if orden is not None else 'null'}) returning id", autor=autor)


def _anular(pg, tabla, fila, motivo="ya no aplica", autor="Pio", extra="") -> str:
    return _web(pg, f"update public.{tabla} set anulado = true, motivo_anulacion = {_lit(motivo)}{extra} "
                    f"where id = {_lit(fila)} returning id", autor=autor)


def _ocurrencias(pg, desde, hasta, rol="cf_lectura") -> list[str]:
    salida = _como(pg, rol, f"select recurrente_id || ':' || fecha from public.cf_cashflow_ocurrencias("
                            f"{_lit(desde)}, {_lit(hasta)})")
    return salida.splitlines() if salida else []


def _factura(pg, farmacia="PIO", vencimientos=(("2026-02-10", "300.00"),)) -> str:
    documento, factura = str(uuid.uuid4()), str(uuid.uuid4())
    pg.sql("insert into public.documentos_facturas (id, farmacia, archivo_nombre, archivo_ruta, archivo_hash) values "
           f"({_lit(documento)}, {_lit(farmacia)}, 'h7b.pdf', 'h7b/h7b.pdf', md5({_lit(documento)}))")
    pg.sql(f"insert into public.facturas (id, documento_id, farmacia) values ({_lit(factura)}, {_lit(documento)}, "
           f"{_lit(farmacia)})")
    for orden, (fecha, importe) in enumerate(vencimientos, start=1):
        pg.sql("insert into public.facturas_vencimientos (factura_id, fecha_vencimiento, importe, orden) values "
               f"({_lit(factura)}, {_lit(fecha)}, {_lit(importe)}, {orden})")
    return factura


# --------------------------------------------------------------------------- migracion y rollback

def test_rollback_40_devuelve_exactamente_el_esquema_39(pg17_nueva_base):
    atras = pg17_nueva_base("40_rollback")
    assert esquema(atras) == esquema(pg17_nueva_base("39"))
    assert esquema(pg17_nueva_base("40")) != esquema(pg17_nueva_base("39"))
    for tabla in TABLAS:
        assert atras.sql(f"select to_regclass('public.{tabla}') is null") == "t"
    # El rol es del cluster (la plantilla 40 aun le concede): aqui queda sin privilegios.
    assert atras.sql("select (select count(*) from pg_class c cross join lateral aclexplode(c.relacl) a "
                     f" where a.grantee = r.oid) + (select count(*) from pg_namespace n "
                     f" cross join lateral aclexplode(n.nspacl) a where a.grantee = r.oid) "
                     f"from pg_roles r where rolname = '{ROL}'") in ("", "0")


def test_40_exige_la_39(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_39_AUSENTE"):
        pg17_nueva_base("38").sql(MIGRACION_40.read_text(encoding="utf-8"))


def test_40_idempotente_sin_cambiar_datos_ni_flags(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("39")
    _datos_previos(pg, tmp_path)
    _importacion(pg)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    configuracion = pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id")
    modulos = pg.sql("select string_agg(modulo || '=' || farmacias::text, ',' order by modulo) "
                     "from public.cf_modulos_farmacias")
    importado = pg.sql("select md5(string_agg(to_jsonb(t)::text, '' order by t.id)) from public.cf_cashflow_importes t")
    pg.sql(MIGRACION_40.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_40.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id") == configuracion
    assert pg.sql("select string_agg(modulo || '=' || farmacias::text, ',' order by modulo) "
                  "from public.cf_modulos_farmacias") == modulos
    assert pg.sql("select md5(string_agg(to_jsonb(t)::text, '' order by t.id)) "
                  "from public.cf_cashflow_importes t") == importado
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert esquema(pg) == esquema(pg17_nueva_base("40"))


@pytest.mark.parametrize("dato", ["concepto", "recurrente", "apunte"])
def test_rollback_falla_cerrado_con_datos(pg40, dato):
    fila = {"concepto": _concepto, "recurrente": _recurrente, "apunte": _apunte}[dato](pg40)
    tabla = {"concepto": CONCEPTOS, "recurrente": RECURRENTES, "apunte": APUNTES}[dato]
    _anular(pg40, tabla, fila)
    with pytest.raises(RuntimeError, match="ROLLBACK_40_CON_DATOS"):
        pg40.sql(ROLLBACK_40.read_text(encoding="utf-8"))
    assert pg40.sql(f"select count(*) from public.{tabla}") == "1"
    assert pg40.sql(f"select count(*) from public.{HISTORIAL}") == "2"


# --------------------------------------------------------------------------- altas, autor e historial

def test_la_web_da_de_alta_y_el_trigger_pone_autor_farmacia_y_anulacion_vacia(pg40):
    a = _web(pg40, f"insert into public.{APUNTES} (cuenta, farmacia, fecha, categoria, concepto, importe, autor, "
                   "anulado, anulado_por, motivo_anulacion) values ('RITA', 'PIO', '2026-01-25', 'RE Ventas', "
                   "' ventas  rita ', 80, 'otro', false, null, null) returning id")
    assert pg40.sql(f"select cuenta || ':' || farmacia || ':' || autor || ':' || importe || ':' || anulado "
                    f"from public.{APUNTES} where id = {_lit(a)}") == "RITA:RITA:Marc:80.00:false"
    assert pg40.sql(f"select string_agg(tabla || ':' || operacion || ':' || autor || ':' || farmacia, ',') "
                    f"from public.{HISTORIAL} where registro_id = {_lit(a)}") == f"{APUNTES}:INSERT:Marc:RITA"
    r = _recurrente(pg40)
    c = _concepto(pg40, cif="B12345678")
    assert pg40.sql(f"select string_agg(tabla, ',' order by id) from public.{HISTORIAL} "
                    f"where registro_id in ({_lit(r)}, {_lit(c)})") == f"{RECURRENTES},{CONCEPTOS}"


def test_un_concepto_nuevo_vale_para_apuntes_y_al_anularlo_deja_de_valer(pg40):
    with pytest.raises(RuntimeError, match="CONCEPTO_DESCONOCIDO"):
        _apunte(pg40, categoria="RS Proveedores", concepto="Seguro local")
    c = _concepto(pg40)
    _apunte(pg40, categoria="RS Proveedores", concepto="  SEGURO   local ")
    # Unico por (cuenta, categoria, nombre normalizado) entre los no anulados.
    with pytest.raises(RuntimeError, match="cf_cashflow_conceptos_vigente"):
        _concepto(pg40, nombre="seguro LOCAL")
    _concepto(pg40, nombre="Seguro local", categoria="RE Ventas")
    _anular(pg40, CONCEPTOS, c)
    with pytest.raises(RuntimeError, match="CONCEPTO_DESCONOCIDO"):
        _apunte(pg40, categoria="RS Proveedores", concepto="Seguro local")
    _concepto(pg40, nombre="seguro LOCAL")


def test_un_cif_solo_en_un_concepto_vigente_por_cuenta(pg40):
    """H7B-D3: el concepto con el proveedor_cif coloca sus vencimientos; dos lo harian ambiguo (falla cerrado)."""
    c = _concepto(pg40, nombre="Alliance", cif="A08000001")
    with pytest.raises(RuntimeError, match="cf_cashflow_conceptos_cif"):
        _concepto(pg40, nombre="Otro", cif="A08000001")
    _concepto(pg40, nombre="Alliance RITA", cuenta="RITA", categoria="RE Ventas", cif="A08000001")
    _anular(pg40, CONCEPTOS, c)
    _concepto(pg40, nombre="Otro", cif="A08000001")
    with pytest.raises(RuntimeError, match="cf_cashflow_conceptos_proveedor_cif_check"):
        _concepto(pg40, nombre="Minusculas", cif="a08000001")


# --------------------------------------------------------------------------- validaciones (§3)

@pytest.mark.parametrize("caso, error", [
    ("sin_autor", "AUTOR_AUSENTE"),
    ("autor_vacio", "AUTOR_AUSENTE"),
    ("cuenta_sl", "CUENTA_NO_VALIDA:SL"),
    ("categoria_fuera", "CATEGORIA_FUERA_DE_PLANTILLA:RS Alquiler"),
    ("categoria_de_otra_cuenta", "CATEGORIA_FUERA_DE_PLANTILLA:RS Proveedores"),
    ("concepto_desconocido", "CONCEPTO_DESCONOCIDO"),
    ("concepto_de_otra_categoria", "CONCEPTO_DESCONOCIDO"),
    ("importe_cero", "IMPORTE_NO_POSITIVO"),
    ("importe_negativo", "IMPORTE_NO_POSITIVO"),
    ("importe_nulo", "IMPORTE_NO_POSITIVO"),
    ("fecha_del_ultimo_saldo", "FECHA_NO_FUTURA:2026-01-10"),
    ("fecha_pasada", "FECHA_NO_FUTURA:2026-01-10"),
    ("rita_hasta_su_saldo", "FECHA_NO_FUTURA:2026-01-20"),
    ("nota_larga", "cf_cashflow_apuntes_nota_check"),
])
def test_apunte_rechazado(pg40, caso, error):
    argumentos = {
        "sin_autor": {"autor": None}, "autor_vacio": {"autor": "  "},
        "cuenta_sl": {"cuenta": "SL"},
        "categoria_fuera": {"categoria": "RS Alquiler"},
        "categoria_de_otra_cuenta": {"cuenta": "RITA", "categoria": "RS Proveedores", "concepto": "Alliance",
                                     "fecha": "2026-01-25"},
        "concepto_desconocido": {"concepto": "Ventas web"},
        "concepto_de_otra_categoria": {"concepto": "Alliance"},
        "importe_cero": {"importe": "0"}, "importe_negativo": {"importe": "-5"}, "importe_nulo": {"importe": None},
        "fecha_del_ultimo_saldo": {"fecha": ULTIMO_PIO}, "fecha_pasada": {"fecha": "2025-12-31"},
        "rita_hasta_su_saldo": {"cuenta": "RITA", "concepto": "Ventas RITA", "fecha": ULTIMO_RITA},
        "nota_larga": {"nota": "x" * 501},
    }[caso]
    with pytest.raises(RuntimeError, match=error):
        _apunte(pg40, **argumentos)
    assert pg40.sql(CONTEOS) == "0|0|0|0"


def test_sin_importacion_vigente_o_sin_saldo_de_bancos_no_se_admite_nada(pg17_nueva_base):
    pg = pg17_nueva_base("40")
    for alta in (_apunte, _recurrente, _concepto):
        with pytest.raises(RuntimeError, match="SIN_IMPORTACION_VIGENTE"):
            alta(pg)
    # Vigente, pero PIO sin ninguna decena cuadrada con el banco (E7): sin referencia, falla cerrado.
    _importacion(pg, bancos_pio=None)
    for alta in (_apunte, _recurrente):
        with pytest.raises(RuntimeError, match="SIN_SALDO_DE_BANCO:PIO"):
            alta(pg)
    _concepto(pg)
    assert pg.sql(CONTEOS) == "1|0|0|1"


def test_farmacia_fuera_del_modulo_cashflow(pg40):
    pg40.sql("update public.cf_modulos_farmacias set farmacias = array['PIO'] where modulo = 'CASHFLOW'")
    with pytest.raises(RuntimeError, match="FARMACIA_NO_HABILITADA:RITA"):
        _apunte(pg40, cuenta="RITA", concepto="Ventas RITA", fecha="2026-01-25")
    _apunte(pg40)


@pytest.mark.parametrize("argumentos, error", [
    ({"frecuencia": "SEMANAL"}, "FRECUENCIA_NO_VALIDA:SEMANAL"),
    ({"dia": 0}, "DIA_NO_VALIDO:0"),
    ({"dia": 32}, "DIA_NO_VALIDO:32"),
    ({"dia": None}, "DIA_NO_VALIDO"),
    ({"importe": "0"}, "IMPORTE_NO_POSITIVO"),
    ({"fin": "2026-01-30"}, "FIN_ANTERIOR_A_INICIO"),
    ({"dia": 15}, "INICIO_NO_ES_OCURRENCIA:2026-01-31:15"),
    ({"inicio": "2025-11-30", "dia": 30, "fin": "2026-01-10"}, "FECHA_NO_FUTURA:2026-01-10"),
    ({"concepto": "Ventas mostrador"}, "CONCEPTO_DESCONOCIDO"),
    ({"autor": None}, "AUTOR_AUSENTE"),
])
def test_recurrente_rechazada(pg40, argumentos, error):
    with pytest.raises(RuntimeError, match=error):
        _recurrente(pg40, **argumentos)
    assert pg40.sql(CONTEOS) == "0|0|0|0"


def test_recurrente_con_inicio_pasado_y_ocurrencias_futuras_se_admite(pg40):
    """Basta una ocurrencia posterior al ultimo saldo de bancos; las pasadas no cuentan (las filtra la web)."""
    r = _recurrente(pg40, frecuencia="MENSUAL", dia=5, inicio="2025-12-05")
    assert _ocurrencias(pg40, "2025-12-01", "2026-02-28") == [f"{r}:2025-12-05", f"{r}:2026-01-05", f"{r}:2026-02-05"]
    # Una ocurrencia pasada no se anula (no es prevision).
    with pytest.raises(RuntimeError, match="FECHA_NO_FUTURA"):
        _anular_ocurrencia(pg40, r, "2026-01-05")


# --------------------------------------------------------------------------- solo anular, nunca borrar

@pytest.mark.parametrize("cambio", ["importe = 1", "fecha = '2026-03-01'", "concepto = 'x'", "autor = 'x'",
                                    "cuenta = 'RITA'"])
def test_la_web_no_cambia_mas_que_la_anulacion(pg40, cambio):
    a = _apunte(pg40)
    with pytest.raises(RuntimeError, match="permission denied"):
        _web(pg40, f"update public.{APUNTES} set {cambio} where id = {_lit(a)}")
    # Ni el propietario: el trigger lo impide.
    with pytest.raises(RuntimeError, match="SOLO_ANULAR"):
        pg40.sql(f"set cf.autor = 'Pio'; update public.{APUNTES} set {cambio} where id = {_lit(a)}")


def test_anular_exige_motivo_y_autor_y_no_se_reabre(pg40):
    a = _apunte(pg40)
    for motivo in ("", "  "):
        with pytest.raises(RuntimeError, match="MOTIVO_ANULACION_AUSENTE"):
            _anular(pg40, APUNTES, a, motivo=motivo)
    with pytest.raises(RuntimeError, match="MOTIVO_ANULACION_AUSENTE"):
        _web(pg40, f"update public.{APUNTES} set anulado = true where id = {_lit(a)}")
    with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
        _anular(pg40, APUNTES, a, autor=None)
    with pytest.raises(RuntimeError, match="SOLO_ANULAR"):
        _web(pg40, f"update public.{APUNTES} set motivo_anulacion = 'x' where id = {_lit(a)}")
    # El trigger pone anulado_por y anulado_at, aunque la web no los pueda escribir.
    _anular(pg40, APUNTES, a, motivo="duplicado", autor="Pio")
    assert pg40.sql(f"select anulado || ':' || anulado_por || ':' || (anulado_at is not null) || ':' || "
                    f"motivo_anulacion from public.{APUNTES} where id = {_lit(a)}") == "true:Pio:true:duplicado"
    for otra in ("anulado = false", "anulado = true, motivo_anulacion = 'otra vez'"):
        with pytest.raises(RuntimeError, match="SOLO_ANULAR"):
            _web(pg40, f"update public.{APUNTES} set {otra} where id = {_lit(a)}")
    assert pg40.sql(f"select string_agg(operacion || ':' || autor, ',' order by id) from public.{HISTORIAL} "
                    f"where registro_id = {_lit(a)}") == "INSERT:Marc,UPDATE:Pio"
    with pytest.raises(RuntimeError, match="permission denied"):
        _web(pg40, f"update public.{APUNTES} set anulado_por = 'x' where id = {_lit(a)}")


@pytest.mark.parametrize("tabla", TABLAS)
def test_nadie_borra_ni_vacia(pg40, tabla):
    _concepto(pg40)
    _recurrente(pg40)
    _apunte(pg40)
    for sentencia in (f"delete from public.{tabla}", f"truncate public.{tabla} cascade"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _web(pg40, sentencia)
        error = "solo de insercion" if tabla == HISTORIAL else "BORRADO_NO_PERMITIDO"
        with pytest.raises(RuntimeError, match=error):
            pg40.sql(sentencia)
    if tabla == HISTORIAL:
        with pytest.raises(RuntimeError, match="permission denied"):
            _web(pg40, f"update public.{HISTORIAL} set autor = 'x'")
        with pytest.raises(RuntimeError, match="solo de insercion"):
            pg40.sql(f"update public.{HISTORIAL} set autor = 'x'")
    assert pg40.sql(CONTEOS) == "1|1|1|3"


# --------------------------------------------------------------------------- ocurrencias

def test_mensual_dia_31_cae_el_ultimo_dia_del_mes(pg40):
    r = _recurrente(pg40, frecuencia="MENSUAL", dia=31, inicio="2026-01-31")
    assert _ocurrencias(pg40, "2026-01-01", "2026-05-31") == [
        f"{r}:2026-01-31", f"{r}:2026-02-28", f"{r}:2026-03-31", f"{r}:2026-04-30", f"{r}:2026-05-31"]
    r2 = _recurrente(pg40, frecuencia="MENSUAL", dia=30, inicio="2027-12-30", concepto="Alliance")
    assert [o for o in _ocurrencias(pg40, "2028-01-01", "2028-03-31") if o.startswith(r2)] == [
        f"{r2}:2028-01-30", f"{r2}:2028-02-29", f"{r2}:2028-03-30"]


def test_trimestral_y_anual_desde_inicio_con_fin_opcional(pg40):
    t = _recurrente(pg40, frecuencia="TRIMESTRAL", dia=15, inicio="2026-02-15", fin="2026-11-15")
    a = _recurrente(pg40, frecuencia="ANUAL", dia=1, inicio="2026-03-01")

    def de(fila, desde, hasta):
        return [o for o in _ocurrencias(pg40, desde, hasta) if o.startswith(fila)]

    assert de(t, "2026-01-01", "2027-12-31") == [
        f"{t}:2026-02-15", f"{t}:2026-05-15", f"{t}:2026-08-15", f"{t}:2026-11-15"]
    assert de(a, "2026-01-01", "2028-12-31") == [f"{a}:2026-03-01", f"{a}:2027-03-01", f"{a}:2028-03-01"]
    assert de(a, "2026-03-02", "2027-02-28") == []


def test_anular_una_ocurrencia_y_la_recurrente(pg40):
    r = _recurrente(pg40, frecuencia="MENSUAL", dia=31, inicio="2026-01-31", fin="2026-04-30")
    o = _anular_ocurrencia(pg40, r, "2026-02-28")
    assert pg40.sql(f"select cuenta || ':' || categoria || ':' || concepto || ':' || fecha || ':' || "
                    f"coalesce(importe::text, '-') from public.{APUNTES} where id = {_lit(o)}") == \
        "PIO:RS Proveedores:Alliance:2026-02-28:-"
    assert _ocurrencias(pg40, "2026-01-01", "2026-12-31") == [f"{r}:2026-01-31", f"{r}:2026-03-31", f"{r}:2026-04-30"]
    with pytest.raises(RuntimeError, match="cf_cashflow_apuntes_ocurrencia"):
        _anular_ocurrencia(pg40, r, "2026-02-28")
    for fecha, error in (("2026-02-27", "OCURRENCIA_NO_VALIDA"), ("2026-05-31", "OCURRENCIA_NO_VALIDA")):
        with pytest.raises(RuntimeError, match=error):
            _anular_ocurrencia(pg40, r, fecha)
    with pytest.raises(RuntimeError, match="IMPORTE_EN_ANULACION_DE_OCURRENCIA"):
        _web(pg40, f"insert into public.{APUNTES} (recurrente_id, fecha_ocurrencia, fecha, cuenta, categoria, concepto, "
                   f"importe) values ({_lit(r)}, '2026-03-31', '2026-03-31', 'PIO', 'x', 'x', 5)")
    # Deshacer la anulacion de la ocurrencia la recupera.
    _anular(pg40, APUNTES, o)
    assert _ocurrencias(pg40, "2026-02-01", "2026-02-28") == [f"{r}:2026-02-28"]
    # Anular la recurrente anula todas sus ocurrencias.
    _anular(pg40, RECURRENTES, r)
    assert _ocurrencias(pg40, "2026-01-01", "2026-12-31") == []
    with pytest.raises(RuntimeError, match="RECURRENTE_ANULADA"):
        _anular_ocurrencia(pg40, r, "2026-03-31")
    with pytest.raises(RuntimeError, match="RECURRENTE_NO_ENCONTRADA"):
        _anular_ocurrencia(pg40, str(uuid.uuid4()), "2026-03-31")


def test_la_bd_no_elige_fuente_por_celda_ni_calcula_la_media(pg40):
    """§2.1: la eleccion por celda (apunte > Excel > media; con vencimientos, el mayor en valor absoluto) y la media son
    del motor de la web. La BD no tiene funcion ni vista que las calcule."""
    assert pg40.sql("select string_agg(proname, ',' order by proname) from pg_proc p "
                    "where p.pronamespace = 'public'::regnamespace and proname like 'cf_cashflow%' "
                    "and has_function_privilege('cf_lectura', p.oid, 'EXECUTE')") == \
        "cf_cashflow_fechas_recurrente,cf_cashflow_ocurrencias"
    assert pg40.sql("select count(*) from pg_views where schemaname = 'public' and viewname like '%cashflow%'") == "0"


# --------------------------------------------------------------------------- sustitucion confirmada (H7B-D6)

def test_sustitucion_confirmada_anula_el_apunte(pg40):
    f = _factura(pg40, vencimientos=(("2026-02-10", "300.00"), ("2026-03-10", "300.00")))
    a = _apunte(pg40, fecha="2026-02-05", importe="290.00", categoria="RS Proveedores", concepto="Alliance")
    # Solo al anular: un apunte suelto nuevo no nace sustituido.
    with pytest.raises(RuntimeError, match="SUSTITUCION_SOLO_AL_ANULAR"):
        _web(pg40, f"insert into public.{APUNTES} (cuenta, fecha, categoria, concepto, importe, sustituido_factura_id, "
                   f"sustituido_vencimiento_orden) values ('PIO', '2026-02-05', 'RE Ventas', 'Ventas mostrador', 1, "
                   f"{_lit(f)}, 1)")
    for extra, error in ((f", sustituido_factura_id = {_lit(str(uuid.uuid4()))}, sustituido_vencimiento_orden = 1",
                          "FACTURA_NO_ENCONTRADA"),
                         (f", sustituido_factura_id = {_lit(f)}, sustituido_vencimiento_orden = 9",
                          "VENCIMIENTO_NO_ENCONTRADO"),
                         (f", sustituido_factura_id = {_lit(f)}", "SUSTITUCION_INCOMPLETA")):
        with pytest.raises(RuntimeError, match=error):
            _anular(pg40, APUNTES, a, motivo="sustituido por factura", extra=extra)
    _anular(pg40, APUNTES, a, motivo="sustituido por factura",
            extra=f", sustituido_factura_id = {_lit(f)}, sustituido_vencimiento_orden = 1")
    assert pg40.sql(f"select anulado || ':' || sustituido_vencimiento_orden from public.{APUNTES} "
                    f"where id = {_lit(a)}") == "true:1"
    # Un vencimiento sustituye a un solo apunte.
    b = _apunte(pg40, fecha="2026-02-06", importe="300.00", categoria="RS Proveedores", concepto="Alliance")
    with pytest.raises(RuntimeError, match="cf_cashflow_apuntes_sustituto"):
        _anular(pg40, APUNTES, b, motivo="x", extra=f", sustituido_factura_id = {_lit(f)}, "
                                                    "sustituido_vencimiento_orden = 1")
    _anular(pg40, APUNTES, b, motivo="x", extra=f", sustituido_factura_id = {_lit(f)}, sustituido_vencimiento_orden = 2")


def test_sustitucion_de_una_ocurrencia_y_farmacia_de_la_factura(pg40):
    f = _factura(pg40)
    r = _recurrente(pg40, frecuencia="MENSUAL", dia=10, inicio="2026-02-10")
    _anular_ocurrencia(pg40, r, "2026-02-10", factura=f, orden=1)
    assert _ocurrencias(pg40, "2026-02-01", "2026-03-31") == [f"{r}:2026-03-10"]
    with pytest.raises(RuntimeError, match="SUSTITUCION_INCOMPLETA"):
        _anular_ocurrencia(pg40, r, "2026-03-10", factura=f)
    # Una factura de PIO no sustituye un apunte de RITA.
    a = _apunte(pg40, cuenta="RITA", concepto="Ventas RITA", fecha="2026-02-05")
    with pytest.raises(RuntimeError, match="FARMACIA_DISTINTA_DE_LA_FACTURA:RITA:PIO"):
        _anular(pg40, APUNTES, a, extra=f", sustituido_factura_id = {_lit(f)}, sustituido_vencimiento_orden = 1")


# --------------------------------------------------------------------------- RLS y privilegios

def test_rls_del_modulo_cashflow_y_rita_sin_facturas(pg40):
    _apunte(pg40)
    _apunte(pg40, cuenta="RITA", concepto="Ventas RITA", fecha="2026-01-25")
    _factura(pg40, farmacia="PIO")
    for rol in (ROL, "cf_lectura"):
        assert _como(pg40, rol, f"select string_agg(cuenta, ',' order by cuenta) from public.{APUNTES}") == "PIO,RITA"
        assert _como(pg40, rol, f"select count(*) from public.{HISTORIAL}") == "2"
    # RITA sigue fuera de facturas: cf_lectura no ve facturas de RITA y farmacias_habilitadas no cambia.
    _factura(pg40, farmacia="RITA")
    assert _como(pg40, "cf_lectura", "select count(*) filter (where farmacia = 'RITA') || ':' || "
                                     "(count(*) > 0) from public.facturas") == "0:true"
    assert pg40.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    # Sin RITA en el modulo: sus filas desaparecen para ambos roles y la web no puede anularlas.
    pg40.sql("update public.cf_modulos_farmacias set farmacias = array['PIO'] where modulo = 'CASHFLOW'")
    for rol in (ROL, "cf_lectura"):
        assert _como(pg40, rol, f"select string_agg(cuenta, ',') from public.{APUNTES}") == "PIO"
        assert _como(pg40, rol, f"select count(*) from public.{HISTORIAL}") == "1"
    assert _web(pg40, f"update public.{APUNTES} set anulado = true, motivo_anulacion = 'x' "
                      "where cuenta = 'RITA' returning id") == ""
    # Sin el trigger, la RLS sola tambien impide escribir en una farmacia fuera del modulo.
    pg40.sql(f"alter table public.{CONCEPTOS} disable trigger {CONCEPTOS}_alta")
    try:
        with pytest.raises(RuntimeError, match="row-level security"):
            _web(pg40, f"insert into public.{CONCEPTOS} (cuenta, farmacia, categoria, nombre, autor) values "
                       "('RITA', 'RITA', 'RE Ventas', 'x', 'Marc')")
    finally:
        pg40.sql(f"alter table public.{CONCEPTOS} enable trigger {CONCEPTOS}_alta")


def test_privilegios_de_la_web_y_de_cf_lectura(pg40):
    # ESTRUCTURA exige las tablas vacias: se comprueba en la plantilla (test de postcondiciones).
    for clave in ("PRIVILEGIOS_WEB", "ATRIBUTOS_ROL", "LECTURA"):
        assert pg40.sql(getattr(DESPLIEGUE, clave).join(("select ", ""))) == "t", clave
    for clave in ("ACL_AJENA", "ACL_COLUMNAS_AJENA", "ACL_SECUENCIA_AJENA", "ACL_FUNCIONES_AJENA"):
        assert pg40.sql(getattr(DESPLIEGUE, clave)) == "0", clave
    for tabla in ("cf_cashflow_importes", "cf_cashflow_saldos", "cf_cashflow_importaciones", "cf_cashflow_cuentas",
                  "facturas", "facturas_vencimientos", "cf_configuracion", "cf_modulos_farmacias",
                  "vencimientos_marcas_pago", "trabajadoras"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _web(pg40, f"select count(*) from public.{tabla}")
    with pytest.raises(RuntimeError, match="permission denied"):
        _web(pg40, f"insert into public.{HISTORIAL} (tabla, registro_id, cuenta, farmacia, operacion, despues, autor) "
                   f"values ('{APUNTES}', gen_random_uuid(), 'PIO', 'PIO', 'INSERT', '{{}}', 'x')")
    for llamada in ("select public.cf_cashflow_registrar_importacion('{}', '[]', '[]')",
                    "select public.cf_cashflow_ultimo_saldo_banco('PIO')",
                    "select public.cf_cashflow_validar_celda('PIO', 'RE Ventas', null)"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _web(pg40, llamada)
    # cf_lectura: lee lo nuevo y las ocurrencias, sin la funcion de la RLS de la web (2BN) y sin escribir.
    assert _como(pg40, "cf_lectura", "select count(*) from public.cf_cashflow_ocurrencias('2026-01-01', "
                                     "'2026-12-31')") == "0"
    with pytest.raises(RuntimeError, match="permission denied"):
        _como(pg40, "cf_lectura", "select public.cf_cashflow_farmacia_habilitada('PIO')")
    with pytest.raises(RuntimeError, match="permission denied"):
        _como(pg40, "cf_lectura", f"insert into public.{CONCEPTOS} (cuenta, categoria, nombre) "
                                  "values ('PIO', 'RE Ventas', 'x')")
    for rol in ("anon", "authenticated", "cf_pagos_web", "cf_trabajadores_web"):
        for tabla in TABLAS:
            with pytest.raises(RuntimeError, match="permission denied"):
                _como(pg40, rol, f"select count(*) from public.{tabla}")
        with pytest.raises(RuntimeError, match="permission denied"):
            _como(pg40, rol, "select count(*) from public.cf_cashflow_ocurrencias('2026-01-01', '2026-12-31')")


# --------------------------------------------------------------------------- independencia del sistema

def test_una_importacion_nueva_no_toca_los_apuntes_ni_el_cuadre(pg40):
    _concepto(pg40)
    _recurrente(pg40)
    a = _apunte(pg40)
    antes = pg40.sql(f"select md5(string_agg(to_jsonb(t)::text, '' order by t.id)) from public.{APUNTES} t")
    # Una importacion con otro hash y el mismo cuadre E1: OK y vigente, con apuntes existentes.
    nueva = _importacion(pg40)
    assert nueva["estado"] == "OK" and nueva["vigente"] is True
    assert pg40.sql(f"select md5(string_agg(to_jsonb(t)::text, '' order by t.id)) from public.{APUNTES} t") == antes
    assert pg40.sql(CONTEOS) == "1|1|1|3"
    # El apunte sigue sin escribir en las tablas importadas.
    assert pg40.sql("select count(*) from public.cf_cashflow_importes where concepto = 'Seguro local'") == "0"
    assert pg40.sql(f"select count(*) from public.{APUNTES} where id = {_lit(a)} and not anulado") == "1"


def test_el_sistema_no_usa_los_apuntes(pg40):
    """Ninguna funcion fuera de las de la 40 lee estas tablas; la importacion de la 38 no cambia."""
    assert pg40.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    funciones = ", ".join(f"'{f}'" for f in DESPLIEGUE.FUNCIONES_NUEVAS)
    assert pg40.sql("select count(*) from pg_proc p where p.pronamespace = 'public'::regnamespace "
                    f"and p.proname not in ({funciones}) and (p.prosrc like '%cf_cashflow_apuntes%' "
                    "or p.prosrc like '%cf_cashflow_recurrentes%' or p.prosrc like '%cf_cashflow_conceptos%')") == "0"


def test_el_orquestador_nocturno_trata_la_prevision_aparte():
    from src.facturas.runtime_supabase import noche_automatica as na

    assert set(DESPLIEGUE.TABLAS_NUEVAS) <= na.TABLAS_CASHFLOW <= na.TABLAS_FUERA_DEL_SNAPSHOT
    assert set(TABLAS) == set(DESPLIEGUE.TABLAS_NUEVAS)


# --------------------------------------------------------------------------- desplegar_40.py

def test_sql_de_precondiciones_40_es_de_solo_lectura(pg17_nueva_base):
    sql = DESPLIEGUE.PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert pg17_nueva_base("39").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 7)
    assert pg17_nueva_base("40").sql("begin read only; " + sql + "; rollback;") == "|".join(["f"] + ["t"] * 6)
    assert pg17_nueva_base("38").sql("begin read only; " + sql + "; rollback;").split("|")[:2] == ["t", "f"]


def test_postcondiciones_en_la_plantilla_40(pg17_nueva_base):
    pg = pg17_nueva_base("40")
    assert pg.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[DESPLIEGUE.N_DATOS:] == ["t"] * 4


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf40_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    for relativa in (RUTA_40, "pruebas/auditoria_h7b/desplegar_40.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 40"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_40.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar(destino / "pruebas/auditoria_h7b/desplegar_40.py", "desplegar_40_repo")


def test_ensayo_completo_despliegue_40_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "39"))
    _datos_previos(pg, tmp_path)
    _importacion(pg)
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
    esquema_39 = esquema(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 7
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "privilegios_web": True, "lectura_y_acl": True,
                                           "estructura_y_rls": True, "propietario": True}
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    # Referencia (superusuario postgres, como el propietario en Supabase): mismo esquema salvo el propietario de los
    # objetos nuevos, que es el rol que despliega (postgres en Supabase).
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "39"))
    referencia.sql(MIGRACION_40.read_text(encoding="utf-8"))
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema(referencia).replace(referencia.db, "")
    # La web funciona sobre lo desplegado por la imitacion (triggers security definer de la imitacion).
    _concepto(pg)
    _apunte(pg)
    r = _recurrente(pg)
    assert _ocurrencias(pg, "2026-02-01", "2026-02-28") == [f"{r}:2026-02-28"]
    assert _como(pg, "cf_lectura", f"select count(*) from public.{HISTORIAL}") == "3"

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: «40 ausente» falla, y aqui tambien «propietarios 2AX» (las tablas nuevas son de la imitacion; en
    # Supabase, de postgres).
    assert registro["precondiciones"] == [False, True, True, True, True, True, False]

    # El rollback tambien funciona con la imitacion (sin datos de la 40): esquema 39.
    pg.sql(f"set session_replication_role = replica; truncate public.{APUNTES}, public.{RECURRENTES}, "
           f"public.{CONCEPTOS}, public.{HISTORIAL}")
    atras = pgl.sql_como_supabase(pg, ROLLBACK_40.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema_39.replace(pg.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_40
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_40_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")


# --------------------------------------------------------------------------- probar_acceso_cf_cashflow_web.py

def test_prueba_de_acceso_contra_pg17_local(contenedor_tcp):
    nombre, puerto, _plantilla = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "40"))
    _importacion(pg)
    # Regla: las contrasenas de roles se fijan siempre con SCRAM (el pooler rechaza otro formato).
    pg.sql(f"set password_encryption = 'scram-sha-256'; alter role {ROL} password 'local-only'")
    assert pg.sql(f"select left(rolpassword, 14) from pg_authid where rolname = '{ROL}'") == "SCRAM-SHA-256$"
    antes = pg.sql(CONTEOS)
    try:
        resultado = _cargar(SCRIPT_ACCESO, "acceso_40d").probar("127.0.0.1", puerto, ROL, "local-only", "RE Ventas",
                                                              dbname=pg.db, sslmode="disable")
    finally:
        pg.sql(f"alter role {ROL} password null")
    assert resultado["veredicto"] == "ACCESO_OK", resultado
    assert set(resultado["lee_sus_tablas"]) == set(TABLAS)
    assert resultado["escritura_con_autor"] | {"nombre_prueba": None} == {
        "nombre_prueba": None, "inserta_y_anula": True, "historial_con_autor": True, "deshecho": True}
    assert resultado["insert_sin_autor"]["mensaje"] == "AUTOR_AUSENTE"
    assert resultado["categoria_inexistente"]["mensaje"].startswith("CATEGORIA_FUERA_DE_PLANTILLA")
    for clave in ("delete_conceptos", "delete_apuntes", "cambiar_importe", "leer_importes", "leer_saldos",
                  "leer_facturas", "leer_vencimientos", "escribir_importaciones", "escribir_historial",
                  "ejecutar_rpc_importacion"):
        assert resultado[clave]["sqlstate"] == "42501", (clave, resultado[clave])
    assert pg.sql(CONTEOS) == antes


def test_prueba_de_acceso_sin_contrasena_no_conecta(monkeypatch):
    acceso = _cargar(SCRIPT_ACCESO, "acceso_40d")
    monkeypatch.delenv(acceso.VARIABLE, raising=False)
    monkeypatch.setattr(acceso, "probar", lambda *a, **k: pytest.fail("no debe conectar"))
    assert acceso.VARIABLE == "CF_CASHFLOW_PASSWORD"
    assert acceso.main(["host", "5432", "RE Ventas"]) == 2
    with pytest.raises(SystemExit):
        acceso.main(["host", "5432", "RE Ventas", "contrasena-como-argumento"])


def test_prueba_de_acceso_no_imprime_la_contrasena(monkeypatch, capsys):
    acceso = _cargar(SCRIPT_ACCESO, "acceso_40d")
    secreto = "secreto-" + uuid.uuid4().hex
    monkeypatch.setenv(acceso.VARIABLE, secreto)
    recibidos = []

    def falla(host, puerto, usuario, contrasena, categoria, **_k):
        recibidos.append((usuario, contrasena, categoria))
        raise RuntimeError("conexion rechazada")

    monkeypatch.setattr(acceso, "probar", falla)
    assert acceso.main(["host", "5432", "RE Ventas"]) == 2
    assert recibidos == [(f"cf_cashflow_web.{acceso.PROJECT_REF}", secreto, "RE Ventas")]
    assert secreto not in capsys.readouterr().out
