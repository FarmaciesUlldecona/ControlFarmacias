"""Hito 2BF-D: herramientas READ_ONLY (pasos 1, 3 y 8) ensayadas en PostgreSQL 17 local.

La puerta del 2AT (``_conectar``) se sustituye por la base local envuelta en transacciones READ ONLY
(``_ConexionPg17``); las tareas programadas, por un estado fijo. Sin produccion ni Farmatic. El despliegue
se simula aplicando la 23 y la aplicacion con las RPC de la 23, como harian ``desplegar_23.py`` y
``aplicar_aprobacion.py``.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import uuid

import pytest

from pg17_local import MIG, ROOT
from test_ensayo_fase4_2at import _ConexionPg17
from test_integracion_pg17_2az import _datos_previos
from test_integracion_pg17_2bf import _albaran_279410, _aplicar, _farmatic_279410, _registrar
from test_integracion_pg17_2bd import _albaran, _resync

pytestmark = pytest.mark.pg17_local

MIGRACION_23 = MIG / "23_cf_aprobaciones_albaranes.sql"


def _herramienta(monkeypatch, pg, sentencias):
    spec = importlib.util.spec_from_file_location(f"preflight_2bfd_{uuid.uuid4().hex[:6]}",
                                                  ROOT / "pruebas/auditoria_2bf_d/preflight_readonly.py")
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
    """Produccion simulada en la 22 con la revision real de 279410 pendiente."""
    pg = pg17_nueva_base("22")
    _datos_previos(pg, tmp_path)
    _albaran_279410(pg)
    _albaran(pg, 990001, "08Z90001", "500.86")
    _resync(pg, 279410, _farmatic_279410())
    sentencias: list[str] = []
    h = _herramienta(monkeypatch, pg, sentencias)
    rutas = {n: tmp_path / f"{n}.json" for n in ("local_22", "local_23", "alcance", "precondiciones", "pre",
                                                 "comparar_pre", "post", "despliegue", "post_aplicar",
                                                 "aplicacion")}
    _referencia(pg17_nueva_base, h, "22", rutas["local_22"])
    _referencia(pg17_nueva_base, h, "23", rutas["local_23"])
    return pg, h, rutas, sentencias


def _solo_lectura(sentencias):
    assert sentencias and all(s.lstrip().lower().startswith(("select", "with", "set local")) for s in sentencias)


def test_pasos_1_3_y_8_con_produccion_simulada(escenario):
    pg, h, r, sentencias = escenario
    assert h.alcance(r["local_22"], r["local_23"], r["alcance"]) == 0
    alcance = _leer(r["alcance"])["alcance_23"]
    assert {"tabla:albaranes_aprobaciones", "tabla:albaranes_aprobaciones_aplicadas",
            "funcion:cf_resincronizar_albaran(text,bigint,jsonb,text,text)",
            "funcion:cf_aplicar_aprobacion_albaran(bigint,jsonb,text)"} <= set(alcance)
    assert "tabla:albaranes" not in alcance and "tabla:albaranes_cambios" not in alcance

    # Paso 1: precondiciones de desplegar_23.py y captura pre.
    assert h.precondiciones(r["precondiciones"]) == 0
    assert _leer(r["precondiciones"])["precondiciones"] == [True] * 9
    assert h.captura("pre", r["pre"]) == 0
    pre = _leer(r["pre"])
    assert pre["veredicto"] == "CAPTURA_OK" and "aprobaciones" not in pre
    assert [(c["campo"], c["accion"]) for c in pre["cambios_objetivo"]] == [
        ("numero_albaran", "REVISION"), ("id_proveedor", "REVISION")]
    assert h.comparar_pre(r["pre"], r["local_22"], r["alcance"], r["comparar_pre"]) == 0

    # Paso 2 (simulado): la 23.
    pg.sql(MIGRACION_23.read_text(encoding="utf-8"))

    # Paso 3: captura post y postcheck 2AX.
    assert h.captura("post", r["post"]) == 0
    assert h.comparar_despliegue(r["pre"], r["post"], r["local_23"], r["alcance"], r["despliegue"]) == 0
    despliegue = _leer(r["despliegue"])
    assert despliegue["veredicto"] == "POSTCHECK_OK" and set(despliegue["objetos_cambiados"]) == set(alcance)

    # Pasos 5 y 7 (simulados): registrar y aplicar.
    aprobacion_id = _registrar(pg)["aprobacion_id"]
    assert _aplicar(pg, aprobacion_id, _farmatic_279410())["accion"] == "APLICADA"

    # Paso 8: captura posterior y comparacion de la aplicacion.
    assert h.captura("post_aplicar", r["post_aplicar"]) == 0
    assert h.comparar_aplicacion(r["post"], r["post_aplicar"], r["aplicacion"]) == 0
    aplicacion = _leer(r["aplicacion"])
    assert aplicacion["veredicto"] == "APLICACION_OK"
    assert aplicacion["albaran"]["campos_cambiados"] == ["fecha_actualizacion", "id_proveedor", "numero_albaran"]
    assert aplicacion["albaran"]["despues"]["numero_albaran"] == "08C16912A"
    assert len(aplicacion["revisiones_pendientes_pre"]) == 2
    _solo_lectura(sentencias)


def test_postcheck_detecta_un_privilegio_de_mas(escenario):
    pg, h, r, _ = escenario
    h.alcance(r["local_22"], r["local_23"], r["alcance"])
    h.captura("pre", r["pre"])
    pg.sql(MIGRACION_23.read_text(encoding="utf-8"))
    pg.sql("grant insert on public.albaranes_aprobaciones to service_role;")
    h.captura("post", r["post"])
    assert h.comparar_despliegue(r["pre"], r["post"], r["local_23"], r["alcance"], r["despliegue"]) == 3
    despliegue = _leer(r["despliegue"])
    assert despliegue["veredicto"] == "POSTCHECK_CON_DIFERENCIAS"
    assert despliegue["c2_alcance_igual_a_local_23"]["tabla:albaranes_aprobaciones"] is False


def test_postcheck_detecta_datos_cambiados_durante_el_despliegue(escenario):
    pg, h, r, _ = escenario
    h.alcance(r["local_22"], r["local_23"], r["alcance"])
    h.captura("pre", r["pre"])
    pg.sql(MIGRACION_23.read_text(encoding="utf-8"))
    pg.sql("update public.albaranes set importe_puc = 1 where id_contador = 990001;")
    h.captura("post", r["post"])
    assert h.comparar_despliegue(r["pre"], r["post"], r["local_23"], r["alcance"], r["despliegue"]) == 3
    assert _leer(r["despliegue"])["huellas_identicas"]["albaranes"] is False


def test_captura_pre_para_si_la_23_ya_esta(escenario):
    pg, h, r, _ = escenario
    pg.sql(MIGRACION_23.read_text(encoding="utf-8"))
    assert h.captura("pre", r["pre"]) == 3
    assert any(f.startswith("MIGRACION_23_YA_PRESENTE") for f in _leer(r["pre"])["fallos"])
    assert h.precondiciones(r["precondiciones"]) == 3


@pytest.mark.parametrize("variante", ["otro_albaran", "otra_aprobacion", "sin_aplicar"])
def test_comparar_aplicacion_detecta_cambios_fuera_de_lo_aprobado(escenario, variante):
    pg, h, r, _ = escenario
    pg.sql(MIGRACION_23.read_text(encoding="utf-8"))
    h.captura("post", r["post"])
    if variante == "otra_aprobacion":
        cambio = [{"campo": "numero_albaran", "anterior": "08C16912", "nuevo": "08C16912A"}]
        aprobacion_id = _registrar(pg, cambio=cambio)["aprobacion_id"]
    else:
        aprobacion_id = _registrar(pg)["aprobacion_id"]
    if variante != "sin_aplicar":
        _aplicar(pg, aprobacion_id, _farmatic_279410())
    if variante == "otro_albaran":
        pg.sql("update public.albaranes set importe_puc = 1 where id_contador = 990001;")
    h.captura("post_aplicar", r["post_aplicar"])
    assert h.comparar_aplicacion(r["post"], r["post_aplicar"], r["aplicacion"]) == 3
    problemas = _leer(r["aplicacion"])["problemas"]
    esperado = {"otro_albaran": "HUELLAS_DISTINTAS", "otra_aprobacion": "APROBACION_DISTINTA_DE_LA_APROBADA",
                "sin_aplicar": "APLICACIONES_INESPERADAS"}[variante]
    assert any(p.startswith(esperado) for p in problemas), problemas


def test_registrar_no_carga_farmatic():
    """El paso 5 se ejecuta con Usuari: cargar el script y registrar no importa el lector de Farmatic."""
    codigo = (
        "import importlib.util, sys; "
        f"spec = importlib.util.spec_from_file_location('s', r'{ROOT / 'pruebas/auditoria_2bf/aplicar_aprobacion.py'}'); "
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
        "print(any(n.startswith('src.database') or n == 'pyodbc' for n in sys.modules))")
    salida = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True, cwd=ROOT)
    assert salida.returncode == 0, salida.stderr
    assert salida.stdout.strip() == "False"
