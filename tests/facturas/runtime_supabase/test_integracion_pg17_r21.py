"""R21 (DECISIONES DE PIO, 2026-11-24; R21-D1 revisada el 2026-11-25): migracion 39 en PostgreSQL 17 local.

Plantillas (pg17_local): "38" (estado productivo), "39" = 38 + migracion 39 dos veces, "39_rollback" = 39 + rollback.
Se comprueba:
- rollback exacto al esquema 38; la 39 exige la 38; ACL de la auxiliar y RPC de persistencia sin cambios; columna marca
  false por defecto (R21-D5); ningun dato cambia;
- la BD acepta R21 (A + 1 a 3 complementarios de la misma recepcion o, sin recepcion, del mismo dia) solo con la marca a
  true y rechaza las variantes; R17 y R20 se siguen aceptando con la marca apagada y encendida;
- el rollback aborta con una linea R21 vigente;
- caso 08007969 del 2AO convertido en R21 (A 498,86 + interno 3,16 de la recepcion + variante 2,00 sin recepcion del
  mismo dia): con la 39 y la marca, el worker persiste CONCILIADA con 3 detalles y 3 reservas; sin la 39, o con la marca
  a false, la noche lo deja para revisar sin reclamar ni gastar intentos; el simulador 2AT cuenta la linea R21;
- desplegar_39.py ensayado con el rol que imita al postgres de Supabase (norma 2BN-D), segundo intento revertido y
  rollback con la imitacion.
Reutiliza el escenario del 2BE: ``base24`` se sobrescribe aqui para que sus fixtures usen la plantilla 39.
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
from src.facturas.runtime_supabase.lectura_readonly import LectorReadOnly, r20_habilitada, r21_habilitada
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase

pytestmark = pytest.mark.pg17_local

MIGRACION_39 = MIG / "39_cf_r21_complementarios.sql"
ROLLBACK_39 = MIG / "39_cf_r21_complementarios.rollback.sql"
RUTA_39 = "sql/migrations/39_cf_r21_complementarios.sql"
SCRIPT_39 = ROOT / "pruebas/auditoria_r21/desplegar_39.py"
AUXILIAR = "public.cf_linea_r17_valida(uuid,text,jsonb,jsonb)"
PERSISTIR = "public.cf_persistir_conciliacion(uuid,text,text,text,jsonb)"
MARCA = "update public.cf_configuracion set conciliacion_r21 = {} where id;"


@pytest.fixture
def base24(pg17_nueva_base):
    """Sobrescribe el fixture del 2BE: su escenario (``factura_r17``) se monta sobre la plantilla 39."""
    return pg17_nueva_base("39")


def _lector(pg) -> LectorReadOnly:
    return LectorReadOnly(_ConexionPg17(pg, []).cursor())


# --------------------------------------------------------------------------- esquema, datos y privilegios

def test_rollback_39_devuelve_exactamente_el_esquema_38(pg17_nueva_base):
    assert esquema(pg17_nueva_base("39_rollback")) == esquema(pg17_nueva_base("38"))
    assert esquema(pg17_nueva_base("39")) != esquema(pg17_nueva_base("38"))


def test_39_exige_la_38(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_38_AUSENTE"):
        pg17_nueva_base("37").sql(MIGRACION_39.read_text(encoding="utf-8"))


def test_39_no_altera_datos_y_solo_anade_la_marca_a_false(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("38")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    reservas = _reservas(pg)
    config = _huella(pg, "select to_jsonb(c) from public.cf_configuracion c")
    acl = pg.sql(f"select coalesce(proacl::text, '') || pg_get_userbyid(proowner) from pg_proc "
                 f"where oid = '{AUXILIAR}'::regprocedure")
    persistir = pg.sql(f"select md5(prosrc || coalesce(proacl::text, '')) from pg_proc "
                       f"where oid = '{PERSISTIR}'::regprocedure")
    pg.sql(MIGRACION_39.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_39.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert _reservas(pg) == reservas
    assert _huella(pg, "select to_jsonb(c) - 'conciliacion_r21' from public.cf_configuracion c") == config
    assert pg.sql("select conciliacion_r21 from public.cf_configuracion where id") == "f"
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    assert pg.sql(f"select coalesce(proacl::text, '') || pg_get_userbyid(proowner) from pg_proc "
                  f"where oid = '{AUXILIAR}'::regprocedure") == acl
    assert pg.sql(f"select md5(prosrc || coalesce(proacl::text, '')) from pg_proc "
                  f"where oid = '{PERSISTIR}'::regprocedure") == persistir
    assert esquema(pg) == esquema(pg17_nueva_base("39"))


def test_privilegios_de_la_auxiliar_tras_la_39(pg17_nueva_base):
    pg = pg17_nueva_base("39")
    for rol in ("anon", "authenticated"):
        assert pg.sql(f"select has_function_privilege('{rol}', '{AUXILIAR}', 'EXECUTE')") == "f"
    assert pg.sql(f"select count(*) from pg_proc p cross join lateral aclexplode(coalesce(p.proacl, "
                  f"acldefault('f', p.proowner))) a where p.oid = '{AUXILIAR}'::regprocedure "
                  "and a.grantee <> p.proowner") == "0"


def test_deteccion_de_la_39_sin_abortar_la_lectura(pg17_nueva_base):
    assert r21_habilitada(_lector(pg17_nueva_base("38"))) is False
    pg = pg17_nueva_base("39")
    assert r21_habilitada(_lector(pg)) is False  # R21-D5: false por defecto
    pg.sql(MARCA.format("true"))
    assert r21_habilitada(_lector(pg)) is True
    assert r20_habilitada(_lector(pg)) is True
    assert r21_habilitada(_lector(pg17_nueva_base("39_rollback"))) is False


# --------------------------------------------------------------------------- la BD revalida R21

def _detalles(linea, *pares):
    return [{"tipo_relacion": "UNO_A_VARIOS", "factura_albaran_extraido_id": linea, "albaran_farmacia": "PIO",
             "albaran_id_contador": c, "importe_aplicado": i, "provenance": {"regla": "R21"}} for c, i in pares]


TRES = ((810001, "97.00"), (810004, "1.00"), (810003, "2.00"))


def _r21(factura_r17, *, marca=True):
    """Linea 08Z00001 (25/06, 100,00): A 810001 (97,00, recepcion 7001), 810004 interno de la recepcion (1,00) y
    810003 variante sin recepcion del mismo dia (2,00). La pareja R17 del 2BE (810001 + 810002) sigue existiendo."""
    pg, factura, linea, ids = factura_r17
    pg.sql(f"update public.facturas_albaranes_extraidos set fecha_albaran = date '2026-06-25' where id = {_lit(linea)};")
    _albaran(pg, 810003, "08Z00001A", "2.00", None)
    _albaran(pg, 810004, "Q999002/2026", "1.00", 7001)
    if marca:
        pg.sql(MARCA.format("true"))
    return pg, factura, linea, ids


def test_la_bd_acepta_r21_con_tres_detalles_y_reserva_los_tres(factura_r17):
    pg, factura, linea, _ = _r21(factura_r17)
    _persistir(pg, factura, _detalles(linea, *TRES))
    assert {r["albaran_id_contador"]: r["factura_id"] for r in _reservas(pg)} == {
        810001: factura, 810003: factura, 810004: factura}


def test_la_bd_acepta_r21_con_cuatro_detalles(factura_r17):
    pg, factura, linea, _ = _r21(factura_r17)
    _albaran(pg, 810007, "Q999003/2026", "0.50", 7001)
    pg.sql(f"update public.facturas_albaranes_extraidos set importe_total = 100.50 where id = {_lit(linea)};")
    _persistir(pg, factura, _detalles(linea, *TRES, (810007, "0.50")))
    assert sorted(r["albaran_id_contador"] for r in _reservas(pg)) == [810001, 810003, 810004, 810007]


def test_la_bd_acepta_r21_de_dos_detalles_sin_recepcion_y_mismo_dia(factura_r17):
    pg, factura, linea, _ = _r21(factura_r17)
    pg.sql(f"update public.facturas_albaranes_extraidos set importe_total = 99.00 where id = {_lit(linea)};")
    _persistir(pg, factura, _detalles(linea, (810001, "97.00"), (810003, "2.00")))
    assert sorted(r["albaran_id_contador"] for r in _reservas(pg)) == [810001, 810003]


def test_complementario_de_la_misma_recepcion_y_otro_dia_si_vale(factura_r17):
    pg, factura, linea, _ = _r21(factura_r17)
    pg.sql("update public.albaranes set fecha = date '2026-06-20' where id_contador = 810004;")
    _persistir(pg, factura, _detalles(linea, *TRES))
    assert len(_reservas(pg)) == 3


@pytest.mark.parametrize("caso", [
    "marca_apagada", "suma_fuera", "importe_no_es_el_puc", "otro_proveedor", "otra_recepcion",
    "sin_recepcion_otro_dia", "a_sin_recepcion", "puc_cero", "cinco_detalles", "dos_a", "a_fuera_de_ventana",
    "linea_sin_fecha", "repetido", "variante_de_otro_numero", "no_interno_ni_variante", "abono", "otra_factura"])
def test_la_bd_rechaza_combinaciones_que_no_son_r21(factura_r17, caso):
    pg, factura, linea, ids = _r21(factura_r17, marca=caso != "marca_apagada")
    detalles = _detalles(linea, *TRES)
    if caso == "suma_fuera":
        pg.sql("update public.albaranes set importe_puc = 2.06 where id_contador = 810003;")
        detalles = _detalles(linea, TRES[0], TRES[1], (810003, "2.06"))
    elif caso == "importe_no_es_el_puc":
        detalles = _detalles(linea, (810001, "97.01"), TRES[1], (810003, "1.99"))
    elif caso == "otro_proveedor":
        pg.sql("update public.albaranes set id_proveedor = '52' where id_contador = 810004;")
    elif caso == "otra_recepcion":
        pg.sql("update public.albaranes set id_recepcion = 7002 where id_contador = 810004;")
    elif caso == "sin_recepcion_otro_dia":
        pg.sql("update public.albaranes set fecha = date '2026-06-26' where id_contador = 810003;")
    elif caso == "a_sin_recepcion":
        pg.sql("update public.albaranes set id_recepcion = null where id_contador = 810001;")
    elif caso == "puc_cero":
        pg.sql("update public.albaranes set importe_puc = 0 where id_contador = 810003;"
               f"update public.facturas_albaranes_extraidos set importe_total = 98.00 where id = {_lit(linea)};")
        detalles = _detalles(linea, TRES[0], TRES[1], (810003, "0.00"))
    elif caso == "cinco_detalles":
        _albaran(pg, 810007, "Q999003/2026", "0.50", 7001)
        _albaran(pg, 810008, "Q999004/2026", "0.50", 7001)
        pg.sql(f"update public.facturas_albaranes_extraidos set importe_total = 101.00 where id = {_lit(linea)};")
        detalles = _detalles(linea, *TRES, (810007, "0.50"), (810008, "0.50"))
    elif caso == "dos_a":
        _albaran(pg, 810006, "08Z00001", "1.00", 7001, id_proveedor="0002")  # R9: el mismo proveedor
        detalles = _detalles(linea, TRES[0], (810006, "1.00"), TRES[2])
    elif caso == "a_fuera_de_ventana":
        pg.sql("update public.albaranes set fecha = date '2026-07-11' where id_contador in (810001, 810003);")
    elif caso == "linea_sin_fecha":
        pg.sql(f"update public.facturas_albaranes_extraidos set fecha_albaran = null where id = {_lit(linea)};")
    elif caso == "repetido":
        pg.sql(f"update public.facturas_albaranes_extraidos set importe_total = 99.00 where id = {_lit(linea)};")
        detalles = _detalles(linea, TRES[0], TRES[1], TRES[1])
    elif caso == "variante_de_otro_numero":
        pg.sql("update public.albaranes set numero_albaran = '08Z00002A' where id_contador = 810003;")
    elif caso == "no_interno_ni_variante":
        pg.sql("update public.albaranes set numero_albaran = '08Z00009' where id_contador = 810003;")
    elif caso == "abono":
        pg.sql(f"update public.facturas_albaranes_extraidos set tipo_movimiento = 'ABONO' where id = {_lit(linea)};")
    elif caso == "otra_factura":
        otra = _linea_sintetica(pg, ids["08007972"])
        pg.sql(f"update public.facturas_albaranes_extraidos set fecha_albaran = date '2026-06-25' "
               f"where id = {_lit(otra)};")
        detalles = _detalles(otra, *TRES)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items() if k not in ("facturas", "historial")}
    # Un albaran repetido lo para la RPC (R15) antes del validador.
    esperado = "ALBARAN_YA_CONCILIADO" if caso == "repetido" else "LINEA_R17_NO_VALIDA|conciliacion_detalles_origen_check"
    with pytest.raises(RuntimeError, match=esperado):
        _persistir(pg, factura, detalles)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items() if k not in ("facturas", "historial")} == antes
    assert _reservas(pg) == []


def test_la_bd_rechaza_un_albaran_repetido_en_el_validador(factura_r17):
    """El validador tambien lo rechaza (albaranes distintos), sin depender de la RPC."""
    pg, factura, linea, _ = _r21(factura_r17)
    pg.sql(f"update public.facturas_albaranes_extraidos set importe_total = 99.00 where id = {_lit(linea)};")
    todos = _detalles(linea, TRES[0], TRES[1], TRES[1])
    assert pg.sql(f"select public.cf_linea_r17_valida({_lit(factura)}::uuid, {_lit(linea)}, "
                  f"{_lit(json.dumps(todos))}::jsonb, {_lit(json.dumps(todos))}::jsonb)") == "f"
    todos = _detalles(linea, *TRES)
    pg.sql(f"update public.facturas_albaranes_extraidos set importe_total = 100.00 where id = {_lit(linea)};")
    assert pg.sql(f"select public.cf_linea_r17_valida({_lit(factura)}::uuid, {_lit(linea)}, "
                  f"{_lit(json.dumps(todos))}::jsonb, {_lit(json.dumps(todos))}::jsonb)") == "t"


@pytest.mark.parametrize("marca", [False, True])
def test_r17_se_sigue_aceptando_tras_la_39(factura_r17, marca):
    pg, factura, linea, _ = _r21(factura_r17, marca=marca)
    _persistir(pg, factura, _pareja(linea))
    assert sorted(r["albaran_id_contador"] for r in _reservas(pg)) == [810001, 810002]


@pytest.mark.parametrize("marca", [False, True])
def test_r20_se_sigue_aceptando_tras_la_39(factura_r17, marca):
    pg, factura, linea, _ = _r21(factura_r17, marca=marca)
    _albaran(pg, 810005, "08Z00001B", "3.00", 7001)
    _persistir(pg, factura, _pareja(linea, b=(810005, "3.00")))
    assert sorted(r["albaran_id_contador"] for r in _reservas(pg)) == [810001, 810005]


def test_el_rollback_aborta_con_una_linea_r21_vigente(factura_r17):
    pg, factura, linea, _ = _r21(factura_r17)
    _persistir(pg, factura, _detalles(linea, *TRES))
    previo = esquema(pg)
    with pytest.raises(RuntimeError, match="ROLLBACK_39_CON_LINEAS_R21_VIGENTES"):
        pg.sql(ROLLBACK_39.read_text(encoding="utf-8"))
    assert esquema(pg) == previo
    assert len(_reservas(pg)) == 3


# --------------------------------------------------------------------------- 08007969 como R21 (worker y noche)

def _r21_en_la_recepcion(monkeypatch):
    """A (08C20268) pasa a 498,86; el interno Q039921/2026 (3,16) sigue en la recepcion 50898; se anade la variante
    08C20268A (2,00) sin recepcion y del mismo dia que A. 498,86 + 3,16 + 2,00 = 504,02 (la linea): ya no es R17."""
    original = t2be._recepcion_50898

    def recepcion(pg, factura_id, **kwargs):
        original(pg, factura_id, **kwargs)
        pg.sql("update public.albaranes set importe_puc = 498.86 where id_contador = 280005;"
               "insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
               "importe_pvp,importe_puc,descuento,estado,id_recepcion) select 'PIO', 280006, '2', '1.- SAFA', "
               "'08C20268A', fecha, 3.00, 2.00, 0, 'PENDIENTE', null from public.albaranes "
               "where farmacia = 'PIO' and id_contador = 280005;")

    monkeypatch.setattr(t2be, "_recepcion_50898", recepcion)


def _repositorio_con_deteccion(monkeypatch, registro):
    """El worker del 2BE con la deteccion de la noche (sesion de solo lectura e information_schema)."""

    def construir(cliente):
        pg = cliente.pg
        registro["pg"] = pg
        return RepositorioRuntimeSupabase(cliente, r20_habilitada=lambda: r20_habilitada(_lector(pg)),
                                          r21_habilitada=lambda: r21_habilitada(_lector(pg)))

    monkeypatch.setattr(t2be, "RepositorioRuntimeSupabase", construir)


def test_08007969_concilia_por_r21_con_la_39_y_la_marca(pg17_nueva_base, tmp_path, monkeypatch):
    _r21_en_la_recepcion(monkeypatch)
    _repositorio_con_deteccion(monkeypatch, {})
    pg = pg17_nueva_base("39")
    pg.sql(MARCA.format("true"))
    objetivo = t2be._conciliar_08007969(pg, tmp_path)
    c = _vigente(pg, objetivo)
    assert (c["resultado"], c["diferencia"], c["casados"]) == ("CONCILIADA", "0.0700", 127)
    detalles = pg.json("select albaran_id_contador, importe_aplicado::text as importe, provenance->>'regla' as regla, "
                       "provenance->>'papel_r21' as papel, provenance->>'motivo_r21' as motivo, "
                       "factura_albaran_extraido_id::text as linea from public.conciliacion_detalles "
                       f"where conciliacion_id = {_lit(c['id'])} and tipo_relacion = 'UNO_A_VARIOS' order by orden")
    assert sorted((d["albaran_id_contador"], d["importe"], d["regla"], d["papel"], d["motivo"]) for d in detalles) == [
        (280004, "3.1600", "R21", "INTERNO", "MISMA_RECEPCION"),
        (280005, "498.8600", "R21", "NUMERO", None),
        (280006, "2.0000", "R21", "LETRA_FINAL", "MISMO_DIA_SIN_RECEPCION")]
    assert len({d["linea"] for d in detalles}) == 1
    regla = pg.json(f"select provenance->'tolerancia_regla' as r from public.conciliaciones where id = {_lit(c['id'])}")
    assert regla[0]["r"]["albaranes_casados"] == 128  # 127 UNO_A_UNO + la linea R21 (R11)
    reservas = {r["albaran_id_contador"]: r["factura_id"] for r in _reservas(pg)}
    assert reservas[280004] == reservas[280005] == reservas[280006] == objetivo


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


@pytest.mark.parametrize("plantilla, marca, motivo, lineas_r21", [
    ("38", None, "DIFERENCIA", 0),       # sin la 39: R21 desactivada, para revisar
    ("39", False, "DIFERENCIA", 0),      # con la 39 y la marca a false (R21-D5, por defecto): igual
    ("39", True, None, 1),               # con la marca: el n.o 1 simula CONCILIADA y la noche lo reclamaria
])
def test_la_noche_sin_la_39_o_sin_la_marca_lo_deja_para_revisar_sin_gastar_intentos(
        pg17_nueva_base, tmp_path, monkeypatch, plantilla, marca, motivo, lineas_r21):
    _r21_en_la_recepcion(monkeypatch)
    registro: dict = {}
    _repositorio_con_deteccion(monkeypatch, registro)
    monkeypatch.setattr(t2be, "construir_worker_conciliacion", lambda repositorio, _id: _NocheSinReclamar(registro))
    pg = pg17_nueva_base(plantilla)
    if marca is not None:
        pg.sql(MARCA.format(str(marca).lower()))
    objetivo = t2be._conciliar_08007969(pg, tmp_path, persiste=False)
    assert registro["factura"] == objetivo and registro["motivo"] == motivo
    assert registro["simulacion"]["resultado"] == ("DIFERENCIA" if motivo else "CONCILIADA")
    if not motivo:
        assert registro["simulacion"]["diferencia"] == "0.0700"
    resumen = registro["simulador_2at"]["resumen_detalles"]
    assert (resumen["lineas_r21"], resumen["lineas_r17"], resumen["lineas_r20"]) == (lineas_r21, 0, 0)
    # Nada reclamado ni escrito: sin conciliaciones, sin reservas, sin intentos ni fallos.
    assert pg.sql(f"select count(*) from public.conciliaciones where factura_id = {_lit(objetivo)}") == "0"
    assert pg.sql("select conciliacion_intentos || '|' || coalesce(conciliacion_intentos_fallo, 0) || '|' "
                  "|| estado_conciliacion_cf || '|' || (conciliacion_bloqueado_por is null) "
                  f"from public.facturas where id = {_lit(objetivo)}") == "0|0|PENDIENTE_CONCILIAR|true"


# --------------------------------------------------------------------------- despliegue

def _cargar_despliegue(script=SCRIPT_39):
    spec = importlib.util.spec_from_file_location(f"despliegue_39_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


DESPLIEGUE = _cargar_despliegue()


def test_sql_de_precondiciones_39_es_de_solo_lectura(pg17_nueva_base):
    pg = pg17_nueva_base("38")
    texto = DESPLIEGUE.PRECONDICIONES.lower()
    assert texto.lstrip().startswith("select") and not any(
        p in texto for p in (" insert ", " update ", " delete ", " alter ", " create ", " drop ", " grant "))
    assert pg.sql(DESPLIEGUE.PRECONDICIONES) == "|".join(["t"] * 5)
    # Sobre la 37 (sin la 38), la precondicion 2 falla.
    assert pg17_nueva_base("37").sql(DESPLIEGUE.PRECONDICIONES).split("|")[1] == "f"


def test_postcondiciones_en_la_plantilla_39(pg17_nueva_base):
    pg = pg17_nueva_base("39")
    assert pg.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[-2:] == ["t", "t"]
    pg.sql(MARCA.format("true"))
    assert pg.sql(DESPLIEGUE.POSTCONDICIONES).split("|")[-2:] == ["f", "t"]


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf39_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    for relativa in (RUTA_39, "pruebas/auditoria_r21/desplegar_39.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 39"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_39.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_r21/desplegar_39.py")


def test_ensayo_completo_despliegue_39_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "38"))
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
    esquema_38 = esquema(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit), registro
    assert registro["precondiciones"] == [True] * 5
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "columna_marca": True,
                                           "auxiliar_r17_r20_r21": True}
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    referencia = base_desde(nombre, pgl.construir_plantilla(nombre, "38"))
    referencia.sql(MIGRACION_39.read_text(encoding="utf-8"))
    assert esquema(pg).replace(pg.db, "") == esquema(referencia).replace(referencia.db, "")

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    assert registro["precondiciones"] == [False, True, True, True, True]

    atras = pgl.sql_como_supabase(pg, ROLLBACK_39.read_text(encoding="utf-8"))
    assert atras.returncode == 0, atras.stderr
    assert esquema(pg).replace(pg.db, "") == esquema_38.replace(pg.db, "")
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_39
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_39_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
