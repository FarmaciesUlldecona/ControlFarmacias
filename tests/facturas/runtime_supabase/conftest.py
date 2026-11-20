"""Fixtures compartidas de integracion PostgreSQL 17 local (Hitos 2AQ y 2AR) y reparto de la suite (Hito SUITE).

Hito SUITE (pruebas/auditoria_suite/DISENO.md):
- ``SUITE_HISTORICA``: ensayos de despliegue y rollbacks de migraciones ya desplegadas (marca ``historica``).
  La barrera de commit lee este diccionario (sin importar el modulo) para las rutas tocadas.
- ``FAMILIAS``: grupo ``xdist_group`` de cada modulo ``pg17_local`` (reparto ``--dist loadgroup``).
- ``pg17_contenedor_tcp``: un contenedor con puerto TCP limpio por modulo para los ensayos de despliegue (D5).
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

import pytest

import pg17_local as pgl


# Modulo -> nombres de test (sin parametros) o "*" (modulo entero). Al desplegar una migracion, sus ensayos
# entran aqui en el commit que registra el despliegue (el «D»).
SUITE_HISTORICA = {
    "test_ensayo_despliegue_19_2ax.py": ("*",),
    "test_ensayo_fase4_2at.py": ("*",),
    "test_preflight_2be_d.py": ("*",),
    "test_preflight_2bf_d.py": ("*",),
    "test_preflight_2bi_d.py": ("*",),
    "test_integracion_pg17_2ar.py": ("test_4_8_rollback_devuelve_el_esquema_16",),
    "test_integracion_pg17_2av.py": ("test_4_13_rollback_devuelve_el_esquema_17_con_datos_de_la_18",),
    "test_integracion_pg17_2ax.py": ("test_rollback_restaura_la_matriz_y_los_privilegios_por_defecto",),
    "test_integracion_pg17_2az.py": (
        "test_rollback_20_devuelve_exactamente_el_esquema_19", "test_ensayo_completo_script_enriquecimiento",
        "test_ensayo_completo_despliegue_20_y_segundo_intento_revierte",
        "test_sql_de_precondiciones_20_es_de_solo_lectura"),
    "test_integracion_pg17_2ba.py": (
        "test_rollback_21_devuelve_exactamente_el_esquema_20", "test_rollback_21_conserva_las_conciliaciones",
        "test_ensayo_completo_despliegue_21_y_segundo_intento_revierte",
        "test_sql_de_precondiciones_21_es_de_solo_lectura"),
    "test_integracion_pg17_2bd.py": (
        "test_rollback_22_devuelve_exactamente_el_esquema_21",
        "test_ensayo_completo_despliegue_22_y_segundo_intento_revierte",
        "test_sql_de_precondiciones_22_es_de_solo_lectura"),
    "test_integracion_pg17_2be.py": (
        "test_rollback_24_devuelve_exactamente_el_esquema_23", "test_sql_de_precondiciones_24_es_de_solo_lectura",
        "test_ensayo_completo_despliegue_24_y_segundo_intento_revierte"),
    "test_integracion_pg17_2bf.py": (
        "test_rollback_23_devuelve_exactamente_el_esquema_22",
        "test_ensayo_completo_despliegue_23_y_segundo_intento_revierte",
        "test_sql_de_precondiciones_23_es_de_solo_lectura", "test_script_informe_registrar_y_aplicar_una_vez",
        "test_script_no_aplicada_si_farmatic_no_coincide_y_sin_configuracion_segura",
        "test_script_sin_la_23_no_escribe"),
    "test_integracion_pg17_2bi.py": (
        "test_rollback_25_devuelve_exactamente_el_esquema_24",
        "test_ensayo_completo_despliegue_25_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_25_es_de_solo_lectura",
        "test_script_informe_sin_escritura_y_recuperar_una_vez",
        "test_script_no_recupera_un_lock_vigente_ni_con_configuracion_inesperada"),
    "test_integracion_pg17_2bk.py": (
        "test_generador_reproduce_la_26_y_su_rollback", "test_rollback_26_devuelve_exactamente_el_esquema_25",
        "test_ensayo_completo_despliegue_26_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_26_es_de_solo_lectura"),
    "test_integracion_pg17_2bl.py": (
        "test_generador_reproduce_la_27_y_su_rollback", "test_rollback_27_devuelve_exactamente_el_esquema_26",
        "test_ensayo_completo_despliegue_27_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_27_es_de_solo_lectura"),
    "test_integracion_pg17_2bm.py": (
        "test_generador_reproduce_la_28_y_su_rollback", "test_rollback_28_devuelve_exactamente_el_esquema_27",
        "test_rollback_28_devuelve_resultado_json_al_formato_27",
        "test_ensayo_completo_despliegue_28_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_28_es_de_solo_lectura"),
    "test_integracion_pg17_2bn.py": (
        "test_rollback_29_devuelve_el_esquema_28", "test_ensayo_completo_despliegue_29_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_29_es_de_solo_lectura"),
    "test_integracion_pg17_2br.py": (
        "test_rollback_30_devuelve_exactamente_el_esquema_29",
        "test_rollback_devuelve_los_valores_previos_y_la_semantica_anterior",
        "test_relleno_de_septiembre_con_la_formula_unica_y_rollback_exacto",
        "test_ensayo_completo_despliegue_30_y_segundo_intento_revierte",
        "test_sql_de_precondiciones_30_es_de_solo_lectura", "test_constantes_de_produccion_de_la_precondicion_3",
        "test_precondicion_3_exige_exactamente_los_detalles_de_septiembre"),
    "test_integracion_pg17_31_trabajadores.py": (
        "test_rollback_31_devuelve_el_esquema_30", "test_ensayo_completo_despliegue_31_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_31_es_de_solo_lectura",
        "test_postcondiciones_en_la_plantilla_31"),
    "test_integracion_pg17_32_auto_alliance.py": (
        "test_rollback_32_devuelve_exactamente_el_esquema_31",
        "test_ensayo_completo_despliegue_32_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_32_es_de_solo_lectura"),
    "test_integracion_pg17_33_trabajadores.py": (
        "test_rollback_33_devuelve_el_esquema_32", "test_rollback_falla_cerrado_con_eventos_anulados_duplicados",
        "test_ensayo_completo_despliegue_33_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_33_es_de_solo_lectura",
        "test_postcondiciones_en_la_plantilla_33"),
    "test_integracion_pg17_34_trabajadores.py": (
        "test_rollback_34_devuelve_el_esquema_33", "test_rollback_falla_cerrado_sin_borrar_nada",
        "test_ensayo_completo_despliegue_34_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_34_es_de_solo_lectura",
        "test_precondicion_falla_con_guardias_farmacia_no_vacia", "test_postcondiciones_en_la_plantilla_34"),
    "test_integracion_pg17_35_pagos.py": (
        "test_rollback_35_devuelve_el_esquema_34", "test_rollback_falla_cerrado_sin_borrar_nada",
        "test_ensayo_completo_despliegue_35_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_35_es_de_solo_lectura",
        "test_postcondiciones_en_la_plantilla_35"),
    "test_integracion_pg17_r20.py": (
        "test_rollback_36_devuelve_exactamente_el_esquema_35",
        "test_ensayo_completo_despliegue_36_y_segundo_intento_revierte",
        "test_el_despliegue_rechaza_un_sql_distinto_del_commit", "test_sql_de_precondiciones_36_es_de_solo_lectura",
        "test_postcondiciones_en_la_plantilla_36"),
}

# Modulo pg17_local -> familia (grupo xdist_group). Los modulos sin entrada forman su propia familia. Medicion del
# 2026-11-20 con 8 workers (DISENO §5): la familia mas larga es la serie 2BP (~8 min) y marca el minimo; los
# modulos de Trabajadores comparten la cadena de plantillas 31-34 y van juntos.
FAMILIAS: dict[str, str] = {
    "test_integracion_pg17_31_trabajadores.py": "trabajadores",
    "test_integracion_pg17_33_trabajadores.py": "trabajadores",
    "test_integracion_pg17_34_trabajadores.py": "trabajadores",
}

_DIRECTORIO = Path(__file__).resolve().parent


def es_historico(modulo: str, nombre: str) -> bool:
    nombres = SUITE_HISTORICA.get(modulo, ())
    return "*" in nombres or nombre.split("[", 1)[0] in nombres


def familia(modulo: str) -> str:
    return "familia_" + FAMILIAS.get(modulo, Path(modulo).stem.removeprefix("test_"))


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    """Antes de la deseleccion por ``-m`` y del sufijo de grupo de xdist: marca ``historica`` y familia."""
    for item in items:
        ruta = Path(str(item.fspath)).resolve()
        if ruta.parent != _DIRECTORIO:
            continue
        if es_historico(ruta.name, item.name):
            item.add_marker(pytest.mark.historica)
        if item.get_closest_marker("pg17_local"):
            item.add_marker(pytest.mark.xdist_group(familia(ruta.name)))


@pytest.fixture(scope="session")
def pg17_contenedor():
    if shutil.which("docker") is None:
        pytest.skip("Docker no disponible")
    if pgl._docker("image", "inspect", pgl.IMAGEN, comprobar=False).returncode:
        pytest.skip(f"imagen local {pgl.IMAGEN} no disponible")
    if not pgl.ALLIANCE.exists() or not pgl.HEFAME.exists():
        pytest.skip("fixtures reales 2AP ausentes")
    nombre = "cf-pg17-" + uuid.uuid4().hex[:12]
    pgl._docker("run", "-d", "--rm", "--name", nombre,
                "--label", "controlfarmacias.certificacion=pg17_local",
                "--network", "none", "--tmpfs", "/var/lib/postgresql/data",
                "-e", "POSTGRES_PASSWORD=local-only", pgl.IMAGEN)
    try:
        for _ in range(120):
            if pgl._docker("exec", nombre, "pg_isready", "-U", "postgres", "-q",
                           comprobar=False).returncode == 0:
                break
            time.sleep(0.5)
        info = json.loads(pgl._docker("inspect", nombre).stdout)[0]
        assert info["HostConfig"]["NetworkMode"] == "none"
        assert not info["HostConfig"]["PortBindings"]
        yield nombre
    finally:
        pgl.cerrar_sesiones(nombre)
        pgl._docker("rm", "-f", nombre, comprobar=False)


@pytest.fixture(scope="module")
def pg17_contenedor_tcp():
    """Hito SUITE (D5, corregida por Pio el 2026-11-20): un contenedor con puerto TCP **limpio por modulo**, solo en
    127.0.0.1 y en tmpfs, para los ensayos de despliegue (el script se conecta con psycopg2). Uno por worker no
    vale: los roles son comunes al cluster y el ensayo de la 29 encontro el rol que debe crear, creado por un modulo
    anterior del mismo worker. Fixture unica para 2AX y 2AZ (y los modulos que importan la de 2AZ).
    Devuelve ``(nombre, puerto)``; cada modulo construye en el sus plantillas."""
    if pgl._docker("image", "inspect", pgl.IMAGEN, comprobar=False).returncode:
        pytest.skip("imagen local no disponible")
    nombre = "cf-pg17-tcp-" + uuid.uuid4().hex[:8]
    pgl._docker("run", "-d", "--rm", "--name", nombre, "--label", "controlfarmacias.certificacion=pg17_local",
                "-p", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql/data",
                "-e", "POSTGRES_PASSWORD=local-only", pgl.IMAGEN)
    try:
        listos = 0
        for _ in range(240):
            ok = pgl._docker("exec", nombre, "psql", "-U", "postgres", "-qAt", "-c", "select 1",
                             comprobar=False).returncode == 0
            listos = listos + 1 if ok else 0
            if listos >= 6:
                break
            time.sleep(0.5)
        info = json.loads(pgl._docker("inspect", nombre).stdout)[0]
        assert all(e.get("HostIp") == "127.0.0.1" for v in info["HostConfig"]["PortBindings"].values() for e in v)
        puerto = int(pgl._docker("port", nombre, "5432/tcp").stdout.strip().rsplit(":", 1)[1])
        yield nombre, puerto
    finally:
        pgl.cerrar_sesiones(nombre)
        pgl._docker("rm", "-f", nombre, comprobar=False)


@pytest.fixture(autouse=True)
def _cerrar_sesiones_pg17():
    """2BH: las sesiones psql persistentes no sobreviven al test (mismo aislamiento que un proceso por
    sentencia; tampoco se acumulan conexiones en el contenedor)."""
    yield
    pgl.cerrar_sesiones()


@pytest.fixture(scope="session")
def pg17_plantilla(pg17_contenedor):
    cache: dict[str, str] = {}

    def obtener(variante: str) -> str:
        if variante not in cache:
            cache[variante] = pgl.construir_plantilla(pg17_contenedor, variante)
        return cache[variante]

    return obtener


@pytest.fixture
def pg17_nueva_base(pg17_contenedor, pg17_plantilla):
    """Cada base vive solo durante su test: el contenedor guarda los datos en tmpfs (memoria de la maquina de
    Docker) y, sin borrarlas, la suite completa agotaba el espacio («No space left on device», 2026-11-15, al
    sumarse las plantillas de la 33)."""
    creadas: list[str] = []

    def crear(variante: str) -> pgl._Pg:
        pg = pgl.base_desde(pg17_contenedor, pg17_plantilla(variante))
        creadas.append(pg.db)
        return pg

    yield crear
    pgl.cerrar_sesiones()
    for db in creadas:
        pgl._docker("exec", pg17_contenedor, "dropdb", "-U", "postgres", "--force", "--if-exists", db)
