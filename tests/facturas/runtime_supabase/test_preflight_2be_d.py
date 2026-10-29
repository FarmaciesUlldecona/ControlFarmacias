"""Hito 2BE-D: herramientas READ_ONLY (pasos 1 y 3) ensayadas en PostgreSQL 17 local.

Patron de ``test_preflight_2bf_d.py``: la puerta del 2AT (``_conectar``) se sustituye por la base local envuelta
en transacciones READ ONLY (``_ConexionPg17``); las tareas programadas, por un estado fijo. Sin produccion ni
Farmatic. Produccion simulada en la 23 con 08007969 (PDF del 2AO) y la recepcion 50898 real; el despliegue se
simula aplicando la 24.
"""
from __future__ import annotations

import importlib.util
import json
import uuid

import pytest

from pg17_local import MIG, ROOT
from test_ensayo_fase4_2at import _ConexionPg17
from test_integracion_pg17_2az import _datos_previos
from test_integracion_pg17_2be import _recepcion_50898

pytestmark = pytest.mark.pg17_local

MIGRACION_24 = MIG / "24_cf_r17_recepcion.sql"


def _herramienta(monkeypatch, pg, sentencias):
    spec = importlib.util.spec_from_file_location(f"preflight_2bed_{uuid.uuid4().hex[:6]}",
                                                  ROOT / "pruebas/auditoria_2be_d/preflight_readonly.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    import auditoria_readonly as ar

    monkeypatch.setattr(ar, "_conectar", lambda: (ar.PROJECT_REF, _ConexionPg17(pg, sentencias)))
    monkeypatch.setattr(modulo, "_tareas", lambda: {"tareas": [
        {"nombre": n, "proxima": None, "ultima": None, "resultado": 0} for n in ar.TAREAS_ESPERADAS]})
    return modulo


def _referencia(pg17_nueva_base, herramienta, variante, ruta):
    esquema = json.loads(pg17_nueva_base(variante).sql(herramienta.SQL_ESQUEMA + ";"))
    ruta.write_text(json.dumps({"variante": variante, "esquema": esquema}), encoding="utf-8")
    return ruta


def _leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


@pytest.fixture
def escenario(pg17_nueva_base, tmp_path, monkeypatch):
    pg = pg17_nueva_base("23")
    _, ids = _datos_previos(pg, tmp_path)
    _recepcion_50898(pg, ids["08007969"])
    pg.sql("update public.facturas set estado_conciliacion_cf = 'PENDIENTE_CONCILIAR' "
           f"where id = '{ids['08007969']}';")
    sentencias: list[str] = []
    h = _herramienta(monkeypatch, pg, sentencias)
    rutas = {n: tmp_path / f"{n}.json" for n in ("local_23", "local_24", "alcance", "precondiciones", "pre",
                                                 "comparar_pre", "post", "despliegue")}
    _referencia(pg17_nueva_base, h, "23", rutas["local_23"])
    _referencia(pg17_nueva_base, h, "24", rutas["local_24"])
    return pg, h, rutas, sentencias


def _solo_lectura(sentencias):
    assert sentencias and all(s.lstrip().lower().startswith(("select", "with", "set local")) for s in sentencias)


def test_precondiciones_son_las_de_desplegar_24(escenario):
    _, h, _, _ = escenario
    spec = importlib.util.spec_from_file_location("desplegar_24", ROOT / "pruebas/auditoria_2be/desplegar_24.py")
    desplegar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desplegar)
    assert h.sql_precondiciones() == desplegar.PRECONDICIONES


def test_pasos_1_y_3_con_produccion_simulada(escenario):
    pg, h, r, sentencias = escenario
    assert h.alcance(r["local_23"], r["local_24"], r["alcance"]) == 0
    alcance = _leer(r["alcance"])
    assert alcance["eliminados"] == []
    assert set(alcance["alcance_24"]) == {"funcion:cf_persistir_conciliacion(uuid,text,text,text,jsonb)",
                                          "funcion:cf_linea_r17_valida(uuid,text,jsonb,jsonb)"}

    # Paso 1: precondiciones de desplegar_24.py, captura pre y esquema 23.
    assert h.precondiciones(r["precondiciones"]) == 0
    assert _leer(r["precondiciones"])["precondiciones"] == [True] * 9
    assert h.captura("pre", r["pre"]) == 0
    pre = _leer(r["pre"])
    assert pre["veredicto"] == "CAPTURA_OK" and pre["marcas"]["24_auxiliar_r17"] is False
    assert [a["id_contador"] for a in pre["albaranes_r17"]] == [280004, 280005]
    assert h.comparar_pre(r["pre"], r["local_23"], r["alcance"], r["comparar_pre"]) == 0

    # Paso 2 (simulado): la 24.
    pg.sql(MIGRACION_24.read_text(encoding="utf-8"))

    # Paso 3: captura post y postcheck 2AX.
    assert h.captura("post", r["post"]) == 0
    assert h.comparar_despliegue(r["pre"], r["post"], r["local_24"], r["alcance"], r["despliegue"]) == 0
    despliegue = _leer(r["despliegue"])
    assert despliegue["veredicto"] == "POSTCHECK_OK"
    assert set(despliegue["objetos_cambiados"]) == set(alcance["alcance_24"])
    _solo_lectura(sentencias)


def test_postcheck_detecta_un_privilegio_de_mas(escenario):
    pg, h, r, _ = escenario
    h.alcance(r["local_23"], r["local_24"], r["alcance"])
    h.captura("pre", r["pre"])
    pg.sql(MIGRACION_24.read_text(encoding="utf-8"))
    pg.sql("grant execute on function public.cf_linea_r17_valida(uuid,text,jsonb,jsonb) to service_role;")
    h.captura("post", r["post"])
    assert h.comparar_despliegue(r["pre"], r["post"], r["local_24"], r["alcance"], r["despliegue"]) == 3
    despliegue = _leer(r["despliegue"])
    assert despliegue["c2_alcance_igual_a_local_24"]["funcion:cf_linea_r17_valida(uuid,text,jsonb,jsonb)"] is False


def test_postcheck_detecta_datos_cambiados_durante_el_despliegue(escenario):
    pg, h, r, _ = escenario
    h.alcance(r["local_23"], r["local_24"], r["alcance"])
    h.captura("pre", r["pre"])
    pg.sql(MIGRACION_24.read_text(encoding="utf-8"))
    pg.sql("update public.albaranes set importe_pvp = 1 where id_contador = 280004;")
    h.captura("post", r["post"])
    assert h.comparar_despliegue(r["pre"], r["post"], r["local_24"], r["alcance"], r["despliegue"]) == 3
    despliegue = _leer(r["despliegue"])
    assert despliegue["huellas_identicas"]["albaranes"] is False and despliegue["objetivo_identico"] is False


def test_captura_pre_para_si_la_24_ya_esta(escenario):
    pg, h, r, _ = escenario
    pg.sql(MIGRACION_24.read_text(encoding="utf-8"))
    assert h.captura("pre", r["pre"]) == 3
    assert any(f.startswith("MIGRACION_24_YA_PRESENTE") for f in _leer(r["pre"])["fallos"])
    assert h.precondiciones(r["precondiciones"]) == 3


@pytest.mark.parametrize("variante,esperado", [
    ("otra_recepcion", "ALBARAN_R17_DISTINTO:280004"),
    ("tercer_albaran", "RECEPCION_50898_CON_3_ALBARANES"),
    ("puc_corregido", "ALBARAN_R17_DISTINTO:280005"),
    ("conciliada", "FACTURA_08007969_NO_PENDIENTE"),
])
def test_captura_pre_para_si_el_objetivo_no_es_el_medido(escenario, variante, esperado):
    pg, h, r, _ = escenario
    pg.sql({
        "otra_recepcion": "update public.albaranes set id_recepcion = 50899 where id_contador = 280004;",
        "tercer_albaran": "update public.albaranes set id_recepcion = 50898 where id_contador = "
                          "(select min(id_contador) from public.albaranes where id_recepcion is null);",
        "puc_corregido": "update public.albaranes set importe_puc = 504.02 where id_contador = 280005;",
        "conciliada": "update public.facturas set estado_conciliacion_cf = 'CONCILIADA' "
                      "where numero_factura = '08007969';",
    }[variante])
    assert h.captura("pre", r["pre"]) == 3
    assert any(f.startswith(esperado) for f in _leer(r["pre"])["fallos"]), _leer(r["pre"])["fallos"]
