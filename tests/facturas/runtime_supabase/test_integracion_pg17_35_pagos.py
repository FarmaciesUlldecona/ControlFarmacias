"""Hito H6: migracion 35 (marcas de pago de vencimientos y forma de pago por proveedor) en PostgreSQL 17 local.

Plantillas (pg17_local): "34" (estado productivo), "35" = 34 + migracion 35 dos veces, "35_rollback" = 35 + rollback.
Diseno: pruebas/auditoria_h6/DISENO.md (D1-D9 aprobadas por Pio el 2026-11-16). Se comprueba:
- la web (cf_pagos_web) escribe solo en vencimientos_marcas_pago y proveedores_forma_pago y lee su historial; nada
  sobre facturas, vencimientos, conciliacion, configuracion ni otras funciones;
- solo anular (SOLO_ANULAR), nunca borrar ni vaciar (sin privilegio y BORRADO_NO_PERMITIDO), autor obligatorio e
  historial solo de insercion;
- una marca vigente por vencimiento y una forma vigente por CIF; formato del CIF;
- el trigger valida factura, farmacia y vencimiento (factura_id, orden), copia fecha e importe, rechaza vencimientos sin
  importe o sin fecha, y una fecha de pago posterior a hoy en Europe/Madrid (D3), sea cual sea la zona de la sesion;
- DOMICILIADOS (D2): forma DOMICILIACION, fecha de pago = fecha de vencimiento y vencimiento ya pasado;
- D7: sin claves externas; una persistencia que reemplaza los vencimientos no falla por las marcas y la marca desfasada
  se detecta; facturas y vencimientos no cambian de estructura;
- RLS por cf_configuracion.farmacias_habilitadas (D1), lectura de cf_lectura sin funciones privilegiadas (2BN) y
  ningun privilegio ajeno (anon, authenticated, el rol del sistema ni PUBLIC) sobre lo nuevo;
- rollback exacto al esquema 34, que falla cerrado con datos;
- desplegar_35.py ensayado con el rol que imita al postgres de Supabase (norma 2BN-D), segundo intento revertido y
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
from test_integracion_pg17_31_trabajadores import _como

pytestmark = pytest.mark.pg17_local

MIGRACION_35 = MIG / "35_cf_pagos_marcas.sql"
ROLLBACK_35 = MIG / "35_cf_pagos_marcas.rollback.sql"
RUTA_35 = "sql/migrations/35_cf_pagos_marcas.sql"
SCRIPT_35 = ROOT / "pruebas/auditoria_h6/desplegar_35.py"
ROL = "cf_pagos_web"
MARCAS, FORMAS, HISTORIAL = "vencimientos_marcas_pago", "proveedores_forma_pago", "pagos_historial"
VENCIMIENTO = ("2026-10-31", "123.45")


def _cargar_despliegue(script=SCRIPT_35):
    spec = importlib.util.spec_from_file_location(f"desplegar_35_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar_despliegue()


def _web(pg, sentencia: str, autor: str | None = "Marc") -> str:
    """Como el rol de la web (SET ROLE), con el autor que fija la web; cada sentencia se confirma."""
    prefijo = f"set role {ROL}; " + (f"set cf.autor = {_lit(autor)}; " if autor is not None else "")
    return pg.sql(prefijo + sentencia)


def _factura(pg, farmacia="PIO", vencimientos=(VENCIMIENTO,)) -> str:
    """Documento, factura y vencimientos (orden 1, 2...) escritos como el sistema (superusuario)."""
    documento, factura = str(uuid.uuid4()), str(uuid.uuid4())
    pg.sql("insert into public.documentos_facturas (id, farmacia, archivo_nombre, archivo_ruta, archivo_hash) values "
           f"({_lit(documento)}, {_lit(farmacia)}, 'h6.pdf', 'h6/h6.pdf', md5({_lit(documento)}))")
    pg.sql(f"insert into public.facturas (id, documento_id, farmacia) values ({_lit(factura)}, {_lit(documento)}, "
           f"{_lit(farmacia)})")
    for orden, (fecha, importe) in enumerate(vencimientos, start=1):
        pg.sql("insert into public.facturas_vencimientos (factura_id, fecha_vencimiento, importe, orden) values "
               f"({_lit(factura)}, {_lit(fecha)}, {_lit(importe)}, {orden})")
    return factura


def _marca(pg, factura, orden=1, fecha_pago="2026-11-02", forma="TRANSFERENCIA", origen="MANUAL", farmacia="PIO",
           autor="Marc") -> str:
    return _web(pg, f"insert into public.{MARCAS} (farmacia, factura_id, vencimiento_orden, fecha_pago, forma, origen) "
                    f"values ({_lit(farmacia)}, {_lit(factura)}, {orden}, {_lit(fecha_pago)}, {_lit(forma)}, "
                    f"{_lit(origen)}) returning id", autor=autor)


def _forma(pg, cif="B12345678", forma="TRANSFERENCIA", farmacia="PIO", autor="Marc") -> str:
    return _web(pg, f"insert into public.{FORMAS} (farmacia, cif, forma) values ({_lit(farmacia)}, {_lit(cif)}, "
                    f"{_lit(forma)}) returning id", autor=autor)


def _hoy_madrid(pg) -> str:
    return pg.sql("select public.cf_pagos_dia_madrid(now())")


def _tablas(pg, *tablas) -> str:
    salida = pgl._docker("exec", pg.contenedor, "pg_dump", "-U", "postgres", "-s",
                         *[f"--table=public.{t}" for t in tablas], pg.db).stdout
    return "\n".join(l for l in salida.splitlines() if not l.startswith(("\\restrict", "\\unrestrict")))


@pytest.fixture
def pg35(pg17_nueva_base):
    return pg17_nueva_base("35")


# --------------------------------------------------------------------------- migracion y rollback

def test_rollback_35_devuelve_el_esquema_34(pg17_nueva_base):
    atras = pg17_nueva_base("35_rollback")
    assert esquema(atras) == esquema(pg17_nueva_base("34"))
    for tabla in (MARCAS, FORMAS, HISTORIAL):
        assert atras.sql(f"select to_regclass('public.{tabla}') is null") == "t"


def test_35_exige_la_34(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_34_AUSENTE"):
        pg17_nueva_base("33").sql(MIGRACION_35.read_text(encoding="utf-8"))


def test_35_idempotente_sin_cambiar_datos_ni_flags(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("34")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    configuracion = pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id")
    referencia = esquema(pg17_nueva_base("35"))
    pg.sql(MIGRACION_35.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_35.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql("select to_jsonb(c)::text from public.cf_configuracion c where id") == configuracion
    assert esquema(pg) == referencia and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_facturas_y_vencimientos_no_cambian_de_estructura(pg17_nueva_base):
    """D7: sin claves externas ni triggers nuevos en las tablas de facturas."""
    tablas = ("facturas", "facturas_vencimientos", "documentos_facturas")
    assert _tablas(pg17_nueva_base("35"), *tablas) == _tablas(pg17_nueva_base("34"), *tablas)


@pytest.mark.parametrize("dato", ["marca", "forma"])
def test_rollback_falla_cerrado_sin_borrar_nada(pg35, dato):
    if dato == "marca":
        _marca(pg35, _factura(pg35))
        _web(pg35, f"update public.{MARCAS} set anulada = true")
    else:
        _forma(pg35)
    with pytest.raises(RuntimeError, match="ROLLBACK_35_PAGOS_CON_DATOS"):
        pg35.sql(ROLLBACK_35.read_text(encoding="utf-8"))
    assert pg35.sql(f"select (select count(*) from public.{MARCAS}) + (select count(*) from public.{FORMAS}) "
                    f"|| ':' || (select count(*) from public.{HISTORIAL})") == ("1:2" if dato == "marca" else "1:1")


# --------------------------------------------------------------------------- marcas de pago

def test_la_web_marca_un_vencimiento_y_el_trigger_copia_fecha_e_importe(pg35):
    f = _factura(pg35)
    m = _web(pg35, f"insert into public.{MARCAS} (farmacia, factura_id, vencimiento_orden, fecha_pago, forma, "
                   f"fecha_vencimiento, importe) values ('PIO', {_lit(f)}, 1, '2026-11-02', 'EFECTIVO', '2000-01-01', 1) "
                   "returning id")
    assert pg35.sql(f"select fecha_vencimiento || ':' || importe || ':' || origen || ':' || anulada "
                    f"from public.{MARCAS} where id = {_lit(m)}") == "2026-10-31:123.4500:MANUAL:false"
    assert pg35.sql(f"select string_agg(tabla || ':' || operacion || ':' || autor || ':' || farmacia, ',') "
                    f"from public.{HISTORIAL} where registro_id = {_lit(m)}") == f"{MARCAS}:INSERT:Marc:PIO"


def test_una_marca_vigente_por_vencimiento_y_anular_permite_otra(pg35):
    f = _factura(pg35, vencimientos=(VENCIMIENTO, ("2026-11-30", "10.00")))
    m = _marca(pg35, f)
    _marca(pg35, f, orden=2)
    with pytest.raises(RuntimeError, match="vencimientos_marcas_pago_vigente"):
        _marca(pg35, f, forma="EFECTIVO")
    _web(pg35, f"update public.{MARCAS} set anulada = true where id = {_lit(m)}", autor="Pio")
    _marca(pg35, f, forma="EFECTIVO")
    assert pg35.sql(f"select string_agg(vencimiento_orden || ':' || forma || ':' || anulada, ',' "
                    f"order by vencimiento_orden, anulada) from public.{MARCAS}") == \
        "1:EFECTIVO:false,1:TRANSFERENCIA:true,2:TRANSFERENCIA:false"
    assert pg35.sql(f"select string_agg(operacion || ':' || autor, ',' order by id) from public.{HISTORIAL} "
                    f"where registro_id = {_lit(m)}") == "INSERT:Marc,UPDATE:Pio"


@pytest.mark.parametrize("cambio", [
    "fecha_pago = '2026-11-03'", "forma = 'EFECTIVO'", "importe = 1", "vencimiento_orden = 2",
    "anulada = true, forma = 'EFECTIVO'", "anulada = false",
])
def test_solo_se_anula(pg35, cambio):
    f = _factura(pg35, vencimientos=(VENCIMIENTO, ("2026-11-30", "10.00")))
    m = _marca(pg35, f)
    with pytest.raises(RuntimeError, match="SOLO_ANULAR"):
        _web(pg35, f"update public.{MARCAS} set {cambio} where id = {_lit(m)}")
    _web(pg35, f"update public.{MARCAS} set anulada = true where id = {_lit(m)}")
    # Una anulada no se reactiva ni se vuelve a anular.
    for otra in ("anulada = false", "anulada = true"):
        with pytest.raises(RuntimeError, match="SOLO_ANULAR"):
            _web(pg35, f"update public.{MARCAS} set {otra} where id = {_lit(m)}")
    c = _forma(pg35)
    with pytest.raises(RuntimeError, match="SOLO_ANULAR"):
        _web(pg35, f"update public.{FORMAS} set forma = 'EFECTIVO' where id = {_lit(c)}")


@pytest.mark.parametrize("tabla", [MARCAS, FORMAS, HISTORIAL])
def test_nadie_borra_ni_vacia(pg35, tabla):
    _marca(pg35, _factura(pg35))
    _forma(pg35)
    for sentencia in (f"delete from public.{tabla}", f"truncate public.{tabla}"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _web(pg35, sentencia)
        # Ni el propietario: el trigger lo impide.
        error = "pagos_historial es solo de insercion" if tabla == HISTORIAL else "BORRADO_NO_PERMITIDO"
        with pytest.raises(RuntimeError, match=error):
            pg35.sql(sentencia)
    if tabla == HISTORIAL:
        with pytest.raises(RuntimeError, match="permission denied"):
            _web(pg35, f"update public.{HISTORIAL} set autor = 'x'")
        with pytest.raises(RuntimeError, match="solo de insercion"):
            pg35.sql(f"update public.{HISTORIAL} set autor = 'x'")
    assert pg35.sql(f"select count(*) from public.{tabla}") == ("2" if tabla == HISTORIAL else "1")


def test_autor_obligatorio(pg35):
    f = _factura(pg35)
    m = _marca(pg35, f)
    c = _forma(pg35)
    for autor in (None, "", "  "):
        with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
            _marca(pg35, _factura(pg35), autor=autor)
        with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
            _forma(pg35, cif="A87654321", autor=autor)
        for tabla, fila in ((MARCAS, m), (FORMAS, c)):
            with pytest.raises(RuntimeError, match="AUTOR_AUSENTE"):
                _web(pg35, f"update public.{tabla} set anulada = true where id = {_lit(fila)}", autor=autor)
    assert pg35.sql(f"select (select count(*) from public.{MARCAS} where not anulada) || ':' || "
                    f"(select count(*) from public.{FORMAS} where not anulada) || ':' || "
                    f"(select count(*) from public.{HISTORIAL})") == "1:1:2"


@pytest.mark.parametrize("caso, error", [
    ("factura_inexistente", "FACTURA_NO_ENCONTRADA"),
    ("orden_inexistente", "VENCIMIENTO_NO_ENCONTRADO"),
    ("sin_importe", "VENCIMIENTO_SIN_IMPORTE"),
    ("sin_fecha", "VENCIMIENTO_SIN_FECHA"),
    ("farmacia_no_habilitada", "FARMACIA_NO_HABILITADA:RITA"),
    ("farmacia_ajena", "FARMACIA_NO_HABILITADA:LUNA"),  # el trigger actua antes que el check (PIO o RITA)
    ("forma_ajena", "vencimientos_marcas_pago_forma_check"),
])
def test_marca_rechazada(pg35, caso, error):
    f = _factura(pg35, vencimientos=(VENCIMIENTO, ("2026-11-30", None), (None, "5.00")))
    argumentos = {
        "factura_inexistente": {"factura": str(uuid.uuid4())},
        "orden_inexistente": {"factura": f, "orden": 4},
        "sin_importe": {"factura": f, "orden": 2},
        "sin_fecha": {"factura": f, "orden": 3},
        "farmacia_no_habilitada": {"factura": f, "farmacia": "RITA"},
        "farmacia_ajena": {"factura": f, "farmacia": "LUNA"},
        "forma_ajena": {"factura": f, "forma": "PAGADO_BANCO"},
    }[caso]
    with pytest.raises(RuntimeError, match=error):
        _marca(pg35, **argumentos)
    assert pg35.sql(f"select (select count(*) from public.{MARCAS}) + (select count(*) from public.{HISTORIAL})") == "0"


def test_la_farmacia_de_la_marca_es_la_de_la_factura(pg35):
    pg35.sql("update public.cf_configuracion set farmacias_habilitadas = array['PIO', 'RITA'] where id")
    f = _factura(pg35)
    with pytest.raises(RuntimeError, match="FARMACIA_DISTINTA_DE_LA_FACTURA:RITA:PIO"):
        _marca(pg35, f, farmacia="RITA")
    _marca(pg35, _factura(pg35, farmacia="RITA"), farmacia="RITA")


@pytest.mark.parametrize("zona", ["Europe/Madrid", "UTC", "Pacific/Kiritimati", "Etc/GMT+12"])
def test_fecha_de_pago_no_posterior_a_hoy_en_madrid(pg35, zona):
    """D3: «hoy» es el de Madrid aunque la sesion este en otra zona."""
    hoy = _hoy_madrid(pg35)
    manana = pg35.sql(f"select ({_lit(hoy)}::date + 1)::text")
    f = _factura(pg35, vencimientos=(VENCIMIENTO, ("2026-11-30", "10.00")))
    with pytest.raises(RuntimeError, match="FECHA_PAGO_FUTURA"):
        _web(pg35, f"set timezone = {_lit(zona)}; insert into public.{MARCAS} (farmacia, factura_id, vencimiento_orden, "
                   f"fecha_pago, forma) values ('PIO', {_lit(f)}, 1, {_lit(manana)}, 'EFECTIVO')")
    _web(pg35, f"set timezone = {_lit(zona)}; insert into public.{MARCAS} (farmacia, factura_id, vencimiento_orden, "
               f"fecha_pago, forma) values ('PIO', {_lit(f)}, 2, {_lit(hoy)}, 'EFECTIVO')")


@pytest.mark.parametrize("momento, dia", [
    ("2027-03-01 22:59:59+00", "2027-03-01"),   # invierno (UTC+1): aun es dia 1 en Madrid
    ("2027-03-01 23:00:00+00", "2027-03-02"),   # ya es dia 2 en Madrid, dia 1 en UTC
    ("2027-07-01 21:59:59+00", "2027-07-01"),   # verano (UTC+2)
    ("2027-07-01 22:00:00+00", "2027-07-02"),
])
def test_cambio_de_dia_en_madrid(pg35, momento, dia):
    assert pg35.sql(f"select public.cf_pagos_dia_madrid({_lit(momento)}::timestamptz)") == dia


def test_domiciliados(pg35):
    hoy = _hoy_madrid(pg35)
    f = _factura(pg35, vencimientos=(VENCIMIENTO, (hoy, "10.00")))
    with pytest.raises(RuntimeError, match="vencimientos_marcas_pago_domiciliados_forma"):
        _marca(pg35, f, fecha_pago=VENCIMIENTO[0], origen="DOMICILIADOS", forma="TRANSFERENCIA")
    with pytest.raises(RuntimeError, match="DOMICILIADO_NO_VALIDO"):
        _marca(pg35, f, fecha_pago="2026-11-01", origen="DOMICILIADOS", forma="DOMICILIACION")
    # Vence hoy: aun no se confirma como domiciliado (si como marca manual).
    with pytest.raises(RuntimeError, match="DOMICILIADO_NO_VALIDO"):
        _marca(pg35, f, orden=2, fecha_pago=hoy, origen="DOMICILIADOS", forma="DOMICILIACION")
    _marca(pg35, f, orden=2, fecha_pago=hoy, forma="DOMICILIACION")
    _marca(pg35, f, fecha_pago=VENCIMIENTO[0], origen="DOMICILIADOS", forma="DOMICILIACION")
    assert pg35.sql(f"select string_agg(vencimiento_orden || ':' || origen, ',' order by vencimiento_orden) "
                    f"from public.{MARCAS}") == "1:DOMICILIADOS,2:MANUAL"


def test_reproceso_reemplaza_vencimientos_sin_fallar_y_la_marca_desfasada_se_detecta(pg35):
    """D7: la persistencia borra y reinserta los vencimientos (28:265-272) y conserva la factura (upsert, 28:241)."""
    f = _factura(pg35, vencimientos=(VENCIMIENTO, ("2026-11-30", "10.00")))
    m = _marca(pg35, f)
    _marca(pg35, f, orden=2)
    pg35.sql(f"begin; delete from public.facturas_vencimientos where factura_id = {_lit(f)}; "
             "insert into public.facturas_vencimientos (factura_id, fecha_vencimiento, importe, orden) values "
             f"({_lit(f)}, '2026-10-31', 120.00, 1), ({_lit(f)}, '2026-11-30', 10.00, 2); commit;")
    assert pg35.sql(f"select count(*) from public.{MARCAS} where not anulada") == "2"
    # La web compara la copia con el vencimiento vigente: la del orden 1 queda «a revisar», nunca «pagado».
    assert pg35.sql(f"select string_agg(m.id::text, ',') from public.{MARCAS} m "
                    "join public.facturas_vencimientos v on v.factura_id = m.factura_id "
                    "and v.orden = m.vencimiento_orden where not m.anulada "
                    "and (v.importe, v.fecha_vencimiento) is distinct from (m.importe, m.fecha_vencimiento)") == m


# --------------------------------------------------------------------------- forma de pago por proveedor

def test_forma_de_pago_por_cif_cambiar_y_volver_a_por_defecto(pg35):
    c = _forma(pg35)
    with pytest.raises(RuntimeError, match="proveedores_forma_pago_vigente"):
        _forma(pg35, forma="EFECTIVO")
    _forma(pg35, cif="A87654321", forma="COMPENSACION_ABONO")
    # Cambiar: anular la vigente e insertar la nueva en la misma transaccion, con el mismo autor.
    _web(pg35, f"begin; update public.{FORMAS} set anulada = true where id = {_lit(c)}; insert into public.{FORMAS} "
               "(farmacia, cif, forma) values ('PIO', 'B12345678', 'EFECTIVO'); commit;", autor="Pio")
    assert pg35.sql(f"select string_agg(operacion || ':' || autor || ':' || (despues->>'forma'), ',' order by id) "
                    f"from public.{HISTORIAL} where despues->>'cif' = 'B12345678'") == \
        "INSERT:Marc:TRANSFERENCIA,UPDATE:Pio:TRANSFERENCIA,INSERT:Pio:EFECTIVO"
    # Volver a «por defecto» (DOMICILIACION): anular la vigente.
    _web(pg35, f"update public.{FORMAS} set anulada = true where cif = 'B12345678' and not anulada")
    assert pg35.sql(f"select count(*) from public.{FORMAS} where cif = 'B12345678' and not anulada") == "0"


@pytest.mark.parametrize("cif, forma, error", [
    ("b12345678", "EFECTIVO", "proveedores_forma_pago_cif_check"),
    ("B-1234567", "EFECTIVO", "proveedores_forma_pago_cif_check"),
    ("B123", "EFECTIVO", "proveedores_forma_pago_cif_check"),
    ("B" * 21, "EFECTIVO", "proveedores_forma_pago_cif_check"),
    ("B12345678", "PAGADO_BANCO", "proveedores_forma_pago_forma_check"),
])
def test_forma_de_pago_fuera_de_dominio(pg35, cif, forma, error):
    with pytest.raises(RuntimeError, match=error):
        _forma(pg35, cif=cif, forma=forma)
    assert pg35.sql(f"select count(*) from public.{FORMAS}") == "0"


# --------------------------------------------------------------------------- RLS y privilegios

def test_la_rls_sigue_a_cf_configuracion(pg35):
    _marca(pg35, _factura(pg35))
    _forma(pg35)
    pg35.sql("update public.cf_configuracion set farmacias_habilitadas = array['RITA'] where id")
    for rol in (ROL, "cf_lectura"):
        for tabla in (MARCAS, FORMAS, HISTORIAL):
            assert _como(pg35, rol, f"select count(*) from public.{tabla}") == "0"
    # La web no puede anular lo que no ve ni escribir en una farmacia no habilitada.
    assert _web(pg35, f"update public.{FORMAS} set anulada = true returning id") == ""
    with pytest.raises(RuntimeError, match="FARMACIA_NO_HABILITADA:PIO"):
        _forma(pg35, cif="A87654321")
    # Sin el trigger, la RLS sola tambien lo impide.
    pg35.sql(f"alter table public.{FORMAS} disable trigger {FORMAS}_farmacia")
    try:
        with pytest.raises(RuntimeError, match="row-level security"):
            _forma(pg35, cif="A87654321")
    finally:
        pg35.sql(f"alter table public.{FORMAS} enable trigger {FORMAS}_farmacia")
    pg35.sql("update public.cf_configuracion set farmacias_habilitadas = array['PIO'] where id")
    for rol in (ROL, "cf_lectura"):
        assert _como(pg35, rol, f"select (select count(*) from public.{MARCAS}) || ':' || "
                                f"(select count(*) from public.{HISTORIAL})") == "1:2"


def test_privilegios_de_la_web_y_de_cf_lectura(pg35):
    assert pg35.sql(DESPLIEGUE.PRIVILEGIOS_WEB.join(("select ", ""))) == "t"
    assert pg35.sql(DESPLIEGUE.ATRIBUTOS_ROL.join(("select ", ""))) == "t"
    assert pg35.sql(DESPLIEGUE.LECTURA.join(("select ", ""))) == "t"
    assert pg35.sql(DESPLIEGUE.ACL_AJENA) == "0"
    assert pg35.sql(DESPLIEGUE.ACL_SECUENCIA_AJENA) == "0"
    assert pg35.sql(DESPLIEGUE.ACL_FUNCIONES_AJENA) == "0"
    for tabla in ("facturas", "facturas_vencimientos", "conciliaciones", "cf_configuracion", "trabajadoras"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _web(pg35, f"select count(*) from public.{tabla}")
    with pytest.raises(RuntimeError, match="permission denied"):
        _web(pg35, f"insert into public.{HISTORIAL} (tabla, registro_id, operacion, despues, autor) "
                   f"values ('{FORMAS}', 'x', 'INSERT', '{{}}', 'x')")
    for llamada in ("select public.cf_pagos_dia_madrid(now())",
                    "select * from public.cf_reclamar_documento_normalizacion_manual_one_shot('x', 60)"):
        with pytest.raises(RuntimeError, match="permission denied"):
            _web(pg35, llamada)
    # cf_lectura lee sin la funcion de la web (2BN: ninguna funcion security definer) y no escribe.
    with pytest.raises(RuntimeError, match="permission denied"):
        _como(pg35, "cf_lectura", "select public.cf_pagos_farmacia_habilitada('PIO')")
    with pytest.raises(RuntimeError, match="permission denied"):
        _como(pg35, "cf_lectura",
              f"insert into public.{FORMAS} (farmacia, cif, forma) values ('PIO', 'B1234', 'EFECTIVO')")
    for rol in ("anon", "authenticated", "cf_trabajadores_web"):
        for tabla in (MARCAS, FORMAS, HISTORIAL):
            with pytest.raises(RuntimeError, match="permission denied"):
                _como(pg35, rol, f"select count(*) from public.{tabla}")
    assert pg35.sql("select string_agg(c.relname || ':' || c.relrowsecurity || ':' || (select count(*) from pg_policy p "
                    "where p.polrelid = c.oid), ',' order by c.relname) from pg_class c "
                    f"where c.relnamespace = 'public'::regnamespace and c.relname in ('{MARCAS}', '{FORMAS}', "
                    f"'{HISTORIAL}')") == f"{HISTORIAL}:true:2,{FORMAS}:true:4,{MARCAS}:true:4"


def test_el_sistema_no_usa_las_marcas(pg35):
    """Ninguna funcion fuera de H6 lee estas tablas; facturas y conciliacion siguen solo PIO."""
    assert pg35.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert pg35.sql("select count(*) from pg_proc p where p.pronamespace = 'public'::regnamespace "
                    "and p.proname not like 'cf_pagos_%' and (p.prosrc like '%marcas_pago%' "
                    "or p.prosrc like '%forma_pago%' or p.prosrc like '%pagos_historial%')") == "0"


def test_el_orquestador_nocturno_trata_los_pagos_aparte():
    from src.facturas.runtime_supabase import noche_automatica as na

    assert na.TABLAS_PAGOS == {MARCAS, FORMAS, HISTORIAL} == set(DESPLIEGUE.TABLAS_NUEVAS)
    assert na.TABLAS_PAGOS <= na.TABLAS_FUERA_DEL_SNAPSHOT and not na.TABLAS_PAGOS & na.TABLAS_TRABAJADORES


# --------------------------------------------------------------------------- desplegar_35.py

def test_sql_de_precondiciones_35_es_de_solo_lectura(pg17_nueva_base):
    sql = DESPLIEGUE.PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert pg17_nueva_base("34").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 7)
    assert pg17_nueva_base("35").sql("begin read only; " + sql + "; rollback;") == "|".join(["f"] + ["t"] * 6)
    assert pg17_nueva_base("33").sql("begin read only; " + sql + "; rollback;").split("|")[:2] == ["t", "f"]


def test_postcondiciones_en_la_plantilla_35(pg35):
    # Columnas: datos (5), privilegios de la web, lectura y ACL, estructura y RLS, propietario.
    assert pg35.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[5:] == ["t"] * 4


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf35_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    for relativa in (RUTA_35, "pruebas/auditoria_h6/desplegar_35.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 35"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_35.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_h6/desplegar_35.py")


def _sin_propietario(texto: str, db: str, rol: str) -> str:
    return texto.replace(db, "").replace(f"OWNER TO {rol};", "OWNER TO postgres;").replace(
        f"Owner: {rol}", "Owner: postgres")


def test_ensayo_completo_despliegue_35_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "34"))
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
    esquema_34 = esquema(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 7
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "privilegios_web": True, "lectura_y_acl": True,
                                           "estructura_y_rls": True, "propietario": True}
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    # Referencia (superusuario postgres, como el propietario en Supabase): mismo esquema salvo el propietario de los
    # objetos nuevos, que es el rol que despliega (postgres en Supabase).
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "34"))
    referencia.sql(MIGRACION_35.read_text(encoding="utf-8"))
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema(referencia).replace(referencia.db, "")
    # La web funciona sobre lo desplegado por la imitacion (triggers security definer de la imitacion).
    _marca(pg, _factura(pg))
    _forma(pg)
    assert _como(pg, "cf_lectura", f"select count(*) from public.{HISTORIAL}") == "2"

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: «35 ausente» falla, y aqui tambien «propietarios 2AX» (las tablas nuevas son de la imitacion; en
    # Supabase, de postgres).
    assert registro["precondiciones"] == [False, True, True, True, True, True, False]

    # El rollback tambien funciona con la imitacion (sin datos de pagos): esquema 34.
    pg.sql(f"set session_replication_role = replica; truncate public.{MARCAS}, public.{FORMAS}, public.{HISTORIAL}; "
           "delete from public.facturas_vencimientos where factura_id in (select id from public.facturas "
           "where documento_id in (select id from public.documentos_facturas where archivo_nombre = 'h6.pdf')); "
           "delete from public.facturas where documento_id in (select id from public.documentos_facturas "
           "where archivo_nombre = 'h6.pdf'); delete from public.documentos_facturas where archivo_nombre = 'h6.pdf'")
    atras = pgl.sql_como_supabase(pg, ROLLBACK_35.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    assert _sin_propietario(esquema(pg), pg.db, rol_despliegue) == esquema_34.replace(pg.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_35
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_35_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")


# --------------------------------------------------------------------------- probar_acceso_cf_pagos_web.py

SCRIPT_ACCESO = ROOT / "pruebas/auditoria_h6/probar_acceso_cf_pagos_web.py"


def _cargar_acceso():
    spec = importlib.util.spec_from_file_location(f"acceso_h6d_{uuid.uuid4().hex[:6]}", SCRIPT_ACCESO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_prueba_de_acceso_contra_pg17_local(contenedor_tcp):
    nombre, puerto, _plantilla = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "35"))
    # Regla: las contrasenas de roles se fijan siempre con SCRAM (el pooler rechaza otro formato).
    pg.sql(f"set password_encryption = 'scram-sha-256'; alter role {ROL} password 'local-only'")
    assert pg.sql(f"select left(rolpassword, 14) from pg_authid where rolname = '{ROL}'") == "SCRAM-SHA-256$"
    filas = (f"select (select count(*) from public.{MARCAS})||'|'||(select count(*) from public.{FORMAS})||'|'||"
             f"(select count(*) from public.{HISTORIAL})||'|'||(select count(*) from public.facturas_vencimientos)")
    antes = pg.sql(filas)
    try:
        resultado = _cargar_acceso().probar("127.0.0.1", puerto, ROL, "local-only", dbname=pg.db, sslmode="disable")
    finally:
        pg.sql(f"alter role {ROL} password null")
    assert resultado["veredicto"] == "ACCESO_OK", resultado
    assert set(resultado["lee_sus_tablas"]) == {MARCAS, FORMAS, HISTORIAL}
    assert resultado["escritura_con_autor"] | {"cif_prueba": None} == {
        "cif_prueba": None, "inserta_y_anula": True, "historial_con_autor": True, "deshecho": True}
    assert resultado["insert_sin_autor"]["mensaje"] == "AUTOR_AUSENTE"
    assert resultado["marca_factura_inexistente"]["mensaje"].startswith("FACTURA_NO_ENCONTRADA")
    for clave in ("delete_marcas", "delete_formas", "leer_facturas", "leer_vencimientos", "escribir_facturas",
                  "escribir_vencimientos", "escribir_historial"):
        assert resultado[clave]["sqlstate"] == "42501", (clave, resultado[clave])
    # Todo se deshace.
    assert pg.sql(filas) == antes


def test_prueba_de_acceso_sin_contrasena_no_conecta(monkeypatch):
    acceso = _cargar_acceso()
    monkeypatch.delenv(acceso.VARIABLE, raising=False)
    monkeypatch.setattr(acceso, "probar", lambda *a, **k: pytest.fail("no debe conectar"))
    assert acceso.VARIABLE == "CF_PAGOS_PASSWORD"
    assert acceso.main(["host", "5432"]) == 2
    with pytest.raises(SystemExit):
        acceso.main(["host", "5432", "contrasena-como-argumento"])


def test_prueba_de_acceso_no_imprime_la_contrasena(monkeypatch, capsys):
    acceso = _cargar_acceso()
    secreto = "secreto-" + uuid.uuid4().hex
    monkeypatch.setenv(acceso.VARIABLE, secreto)
    recibidos = []

    def falla(host, puerto, usuario, contrasena, **_k):
        recibidos.append((usuario, contrasena))
        raise RuntimeError("conexion rechazada")

    monkeypatch.setattr(acceso, "probar", falla)
    assert acceso.main(["host", "5432"]) == 2
    assert recibidos == [(f"cf_pagos_web.{acceso.PROJECT_REF}", secreto)]
    assert secreto not in capsys.readouterr().out
