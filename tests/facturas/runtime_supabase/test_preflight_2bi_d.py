"""Hito 2BI-D: herramientas READ_ONLY (pasos de preflight y postcheck) ensayadas en PostgreSQL 17 local.

Patron de ``test_preflight_2be_d.py``: la puerta del 2AT (``_conectar``) se sustituye por la base local envuelta
en transacciones READ ONLY (``_ConexionPg17``); las tareas programadas, por un estado fijo. Sin produccion ni
Farmatic. Produccion simulada en la 24 con datos (PDF del 2AO); el despliegue se simula aplicando la 25.
"""
from __future__ import annotations

import importlib.util
import json
import uuid

import pytest

from pg17_local import MIG, ROOT
from test_ensayo_fase4_2at import _ConexionPg17
from test_integracion_pg17_2az import _datos_previos

pytestmark = pytest.mark.pg17_local

MIGRACION_25 = MIG / "25_cf_claims_huerfanos_normalizacion.sql"
RECUPERAR = "public.cf_recuperar_claim_huerfano_normalizacion(uuid,text,interval)"


def _herramienta(monkeypatch, pg, sentencias):
    spec = importlib.util.spec_from_file_location(f"preflight_2bid_{uuid.uuid4().hex[:6]}",
                                                  ROOT / "pruebas/auditoria_2bi_d/preflight_readonly.py")
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


def _leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


@pytest.fixture
def escenario(pg17_nueva_base, tmp_path, monkeypatch):
    pg = pg17_nueva_base("24")
    _datos_previos(pg, tmp_path)
    sentencias: list[str] = []
    h = _herramienta(monkeypatch, pg, sentencias)
    rutas = {n: tmp_path / f"{n}.json" for n in ("local_24", "local_25", "alcance", "precondiciones", "pre",
                                                 "comparar_pre", "post", "despliegue")}
    _referencia(pg17_nueva_base, h, "24", rutas["local_24"])
    _referencia(pg17_nueva_base, h, "25", rutas["local_25"])
    return pg, h, rutas, sentencias


def test_precondiciones_son_las_de_desplegar_25(escenario):
    _, h, _, _ = escenario
    spec = importlib.util.spec_from_file_location("desplegar_25", ROOT / "pruebas/auditoria_2bi/desplegar_25.py")
    desplegar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desplegar)
    assert h.sql_precondiciones() == desplegar.PRECONDICIONES


def test_preflight_despliegue_y_postcheck_con_produccion_simulada(escenario):
    pg, h, r, sentencias = escenario
    assert h.alcance(r["local_24"], r["local_25"], r["alcance"]) == 0
    alcance = _leer(r["alcance"])
    assert alcance["eliminados"] == [] and set(alcance["alcance_25"]) == set(alcance["nuevos"]) == {
        "funcion:cf_recuperar_claim_huerfano_normalizacion(uuid,text,interval)",
        "funcion:cf_huerfanos_normalizacion(interval)", "funcion:cf_senales_claim_huerfano(uuid)"}
    assert h.precondiciones(r["precondiciones"]) == 0
    assert _leer(r["precondiciones"])["precondiciones"] == [True] * 9
    assert h.captura("pre", r["pre"]) == 0
    pre = _leer(r["pre"])
    assert pre["veredicto"] == "CAPTURA_OK" and pre["marcas"]["25_recuperar"] is False and pre["normalizando"] == []
    assert h.comparar_pre(r["pre"], r["local_24"], r["alcance"], r["comparar_pre"]) == 0

    pg.sql(MIGRACION_25.read_text(encoding="utf-8"))  # despliegue simulado

    assert h.captura("post", r["post"]) == 0
    assert h.comparar_despliegue(r["pre"], r["post"], r["local_25"], r["alcance"], r["despliegue"]) == 0
    despliegue = _leer(r["despliegue"])
    assert despliegue["veredicto"] == "POSTCHECK_OK"
    assert set(despliegue["objetos_cambiados"]) == set(alcance["alcance_25"])
    assert sentencias and all(s.lstrip().lower().startswith(("select", "with", "set local")) for s in sentencias)


def test_postcheck_detecta_un_privilegio_de_mas(escenario):
    pg, h, r, _ = escenario
    h.alcance(r["local_24"], r["local_25"], r["alcance"])
    h.captura("pre", r["pre"])
    pg.sql(MIGRACION_25.read_text(encoding="utf-8"))
    pg.sql(f"grant execute on function {RECUPERAR} to authenticated;")
    h.captura("post", r["post"])
    assert h.comparar_despliegue(r["pre"], r["post"], r["local_25"], r["alcance"], r["despliegue"]) == 3


def test_postcheck_detecta_datos_cambiados(escenario):
    pg, h, r, _ = escenario
    h.alcance(r["local_24"], r["local_25"], r["alcance"])
    h.captura("pre", r["pre"])
    pg.sql(MIGRACION_25.read_text(encoding="utf-8"))
    pg.sql("update public.documentos_facturas set archivo_nombre = 'otro.pdf' "
           "where id = (select min(id::text)::uuid from public.documentos_facturas);")
    h.captura("post", r["post"])
    assert h.comparar_despliegue(r["pre"], r["post"], r["local_25"], r["alcance"], r["despliegue"]) == 3
    assert _leer(r["despliegue"])["huellas_identicas"]["documentos_facturas"] is False


def test_captura_pre_para_si_la_25_ya_esta(escenario):
    pg, h, r, _ = escenario
    pg.sql(MIGRACION_25.read_text(encoding="utf-8"))
    assert h.captura("pre", r["pre"]) == 3
    assert any(f.startswith("MIGRACION_25_YA_PRESENTE") for f in _leer(r["pre"])["fallos"])
    assert h.precondiciones(r["precondiciones"]) == 3


def test_captura_pre_para_con_un_documento_en_normalizando(escenario):
    pg, h, r, _ = escenario
    pg.sql("update public.documentos_facturas set estado_lectura = 'NORMALIZANDO', bloqueado_por = 'w', "
           "bloqueado_hasta = now() - interval '1 hour' where id = (select min(id::text)::uuid "
           "from public.documentos_facturas);")
    assert h.captura("pre", r["pre"]) == 3
    assert any(f.startswith("DOCUMENTOS_EN_NORMALIZANDO") for f in _leer(r["pre"])["fallos"])
    assert h.precondiciones(r["precondiciones"]) == 3
