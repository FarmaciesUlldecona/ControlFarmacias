"""Hito 2BP: serie supervisada de conciliacion (``pruebas/auditoria_2bp/serie_conciliacion.py``).

PostgreSQL 17 local (plantilla "30"; sin la 30 la serie PARA) con las cinco facturas reales del 2AO: 08007969 (R17
con la recepcion 50898 del 2BE, o DIFERENCIA sin ella), 08007970, 08007972 y 08007973 con albaranes sinteticos (PUC =
importe documental; 08007970 con 4 desplazados de un centimo) y 08007971 (con el extractor vigente tiene
albaranes; tambien sinteticos). Las facturas de la semilla de staging quedan fuera (NO_APTA). Lecturas por la
puerta READ_ONLY del 2AT sobre la base local; escrituras con el worker manual real sobre ``ClientePg17`` con el rol
de servicio. Tareas y git fijos. Sin produccion ni Farmatic.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import uuid
from types import SimpleNamespace

import pytest

from pg17_local import ROOT, _lit
from test_ensayo_fase4_2at import _ClienteServiceRole, _ConexionPg17
from test_integracion_pg17_2az import _operacionales_sinteticos, _preparar_2ao, _solo_primera
from test_integracion_pg17_2be import _recepcion_50898

GIT_LIMPIO = {"status": "", "head": "a" * 40, "origin": "a" * 40, "origin_ancestro": True, "cambios": []}


def _modulo():
    spec = importlib.util.spec_from_file_location(f"serie_2bp_{uuid.uuid4().hex[:6]}",
                                                  ROOT / "pruebas/auditoria_2bp/serie_conciliacion.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# --------------------------------------------------------------------------- sin base de datos

@pytest.mark.parametrize("git, esperado", [
    (GIT_LIMPIO, []),
    ({**GIT_LIMPIO, "status": " M src/x.py"}, ["GIT_ARBOL_NO_LIMPIO"]),
    ({**GIT_LIMPIO, "head": "b" * 40, "cambios": ["docs/contexto/ESTADO_ACTUAL.md", "pruebas/x/DISENO.md"]}, []),
    ({**GIT_LIMPIO, "head": "b" * 40, "cambios": ["docs/a.md", "src/b.py"]}, ["GIT_COMMITS_NO_DOCUMENTALES:src/b.py"]),
    ({**GIT_LIMPIO, "head": "b" * 40, "origin_ancestro": False}, ["GIT_HEAD_NO_DESCIENDE_DE_ORIGIN"]),
    ({"error": "sin git"}, ["GIT_NO_DETERMINABLE:sin git"]),
])
def test_puerta_git(git, esperado):
    assert _modulo().puerta_git(git) == esperado


def test_postcheck_informa_trabajadores_aparte_sin_veredicto():
    """Mejora aprobada por Pio (2026-11-13): Trabajadores se informa aparte y no hace fallar el postcheck."""
    m = _modulo()
    antes = {"guardias_farmacia": {"g1": ["h1", None]}, "albaranes": {"a1": ["ha", None]}}
    despues = {"guardias_farmacia": {}, "trabajadores_historial": {"x": ["hx", None]},
               "albaranes": {"a1": ["ha", None]}}
    assert m.diferencias_filas(antes, despues, set()) == []
    assert m.cambios_trabajadores(antes, despues) == {"guardias_farmacia": 1, "trabajadores_historial": 1}
    despues["albaranes"] = {}
    assert m.diferencias_filas(antes, despues, set()) == ["FILA_BORRADA:albaranes:a1"]


def _prev(**kw):
    base = {"camino": "PERSISTIR", "resultado": "CONCILIADA", "importe_factura": "10.0000",
            "importe_explicado": "10.0000", "diferencia": "0.0000", "tolerancia": "0.0500",
            "idempotency_key_prevista": "k"}
    return {**base, **kw}


def test_comprobar_simulacion_para_si_el_numero_1_no_simula_conciliada():
    m = _modulo()
    f = {"id": "f1", "numero_factura": "0800", "prevision": _prev()}
    assert m.comprobar_simulacion(f, _prev(), {}) == []
    assert m.comprobar_simulacion(f, _prev(idempotency_key_prevista="otra"), {}) == [
        "SIMULACION_DISTINTA_DEL_PLAN:idempotency_key_prevista:k!=otra"]
    dif = {"id": "f1", "numero_factura": "0800", "prevision": _prev(resultado="DIFERENCIA", diferencia="3.1600")}
    actual = _prev(resultado="DIFERENCIA", diferencia="3.1600")
    assert m.comprobar_simulacion(dif, actual, {}) == ["NUMERO_1_SIMULA_DIFERENCIA:f1:0800:3.1600"]
    # Decision de Pio caso a caso: solo esa factura y esa diferencia.
    assert m.comprobar_simulacion(dif, actual, {"f1": {"decision": "CONCILIAR_CON_DIFERENCIA",
                                                      "diferencia": "3.1600"}}) == []
    assert m.comprobar_simulacion(dif, actual, {"f1": {"decision": "CONCILIAR_CON_DIFERENCIA",
                                                      "diferencia": "3.1500"}}) != []
    fallo = {"camino": "FALLO", "fallo": {"codigo": "ValueError"}, **{k: None for k in m.CAMPOS_PREVISION[1:]}}
    assert m.comprobar_simulacion({"id": "f1", "numero_factura": "0800", "prevision": fallo}, fallo, {}) == [
        "NUMERO_1_SIMULA_FALLO:f1:ValueError"]


# --------------------------------------------------------------------------- PostgreSQL 17 local

def _serie(pg17_nueva_base, tmp_path, monkeypatch, variante="30", *, recepcion_interno=50898, primera=None):
    pg = pg17_nueva_base(variante)
    cliente, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    _recepcion_50898(pg, ids["08007969"], recepcion_interno=recepcion_interno)
    for numero, desplazados, contador in (("08007970", 4, 950000), ("08007972", 0, 960000),
                                          ("08007973", 0, 970000), ("08007971", 0, 980000)):
        _operacionales_sinteticos(pg, ids[numero], desplazados, contador)
    if primera:
        _solo_primera(pg, ids, primera)
    sentencias: list[str] = []
    m = _modulo()
    import auditoria_readonly as ar

    monkeypatch.setattr(ar, "_conectar", lambda: (ar.PROJECT_REF, _ConexionPg17(pg, sentencias)))
    monkeypatch.setattr(m, "_tareas", lambda: {"tareas": [
        {"nombre": n, "proxima": None, "ultima": None, "resultado": 0} for n in ar.TAREAS_ESPERADAS]})
    servicio = _ClienteServiceRole(pg)
    monkeypatch.setattr(m, "_cliente", lambda: servicio)
    monkeypatch.setattr(m, "_estado_git", lambda: dict(GIT_LIMPIO))
    plan = tmp_path / "plan.json"
    assert m.plan(plan) == 0
    return SimpleNamespace(pg=pg, m=m, ids=ids, plan=plan, raiz=tmp_path / "serie", sentencias=sentencias)


@pytest.fixture
def serie(pg17_nueva_base, tmp_path, monkeypatch):
    return _serie(pg17_nueva_base, tmp_path, monkeypatch)


def _leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


def _huella(pg):
    return pg.sql("select md5(string_agg(t, '' order by t)) from ("
                  "select md5(to_jsonb(f)::text) t from public.facturas f union all "
                  "select md5(to_jsonb(c)::text) from public.conciliaciones c union all "
                  "select md5(to_jsonb(d)::text) from public.conciliacion_detalles d union all "
                  "select md5(to_jsonb(r)::text) from public.conciliacion_albaranes_reservados r union all "
                  "select md5(to_jsonb(h)::text) from public.historial_facturas h) x")


def _estado(pg, factura_id):
    return pg.sql("select estado_conciliacion_cf || '|' || conciliacion_intentos_fallo from public.facturas "
                  f"where id = {_lit(factura_id)}")


def _editar_plan(serie, cambio):
    datos = _leer(serie.plan)
    cambio(datos)
    serie.plan.write_text(json.dumps(datos), encoding="utf-8")


def test_plan_simula_en_el_orden_del_selector_y_es_de_solo_lectura(serie):
    plan = _leer(serie.plan)
    assert serie.sentencias and all(s.lstrip().lower().startswith(("select", "with", "set local"))
                                    for s in serie.sentencias)
    oficial = serie.pg.sql("select string_agg(f.id::text, ',' order by f.fecha_factura nulls last, f.id) "
                           "from public.facturas f cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e "
                           "where e.estado = 'APTA' and f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR'").split(",")
    assert [f["id"] for f in plan["facturas"]] == oficial
    assert {f["numero_factura"] for f in plan["facturas"]} == {"08007969", "08007970", "08007971", "08007972",
                                                              "08007973"}
    assert plan["resumen"] == {"CONCILIADA": 5} and plan["primera_no_conciliada"] is None
    previsto = {f["numero_factura"]: f["prevision"] for f in plan["facturas"]}
    assert (previsto["08007969"]["diferencia"], previsto["08007969"]["resumen_detalles"]["lineas_r17"]) == ("0.0700", 1)
    assert previsto["08007970"]["diferencia"] == "-0.0800"
    # Fuera de la cola: solo las facturas de la semilla de staging, no aptas.
    assert plan["no_elegibles"] and {x["elegibilidad"] for x in plan["no_elegibles"]} == {"NO_APTA"}
    assert plan["migracion_30"] == {"cf_detalles_por_linea": True, "valores_previos": True,
                                    "cf_persistir_conciliacion": True}
    assert serie.pg.sql("select count(*) from public.conciliaciones") == "0"


def test_la_simulacion_encadenada_ve_los_albaranes_que_reservaria_otra_factura(serie):
    """R15: la reserva prevista de una factura anterior en el plan ocupa el albaran para las siguientes."""
    pg, m = serie.pg, serie.m
    import auditoria_readonly as ar

    objetivo = serie.ids["08007973"]
    contador = int(pg.sql("select min(id_contador) from public.albaranes where id_contador > 970000"))
    libre = ar._ejecutar_lectura(lambda lector: m.prevision(ar._simular(lector, objetivo)))[1]
    with m._reservas_previstas({("PIO", contador): serie.ids["08007972"]}):
        ocupado = ar._ejecutar_lectura(lambda lector: {"s": ar._simular(lector, objetivo)})[1]["s"]
    with m._reservas_previstas({("PIO", contador): objetivo}):  # la propia reserva no ocupa
        propia = ar._ejecutar_lectura(lambda lector: m.prevision(ar._simular(lector, objetivo)))[1]
    assert libre["resultado"] == propia["resultado"] == "CONCILIADA"
    assert ocupado["resultado"] == "DIFERENCIA"
    assert "ALBARAN_YA_CONCILIADO" in {d["provenance"].get("estado_matching") for d in ocupado["detalles"]}


def test_tanda_concilia_lo_previsto_con_postcheck_por_fila(serie):
    pg, m = serie.pg, serie.m
    plan = _leer(serie.plan)
    assert m.tanda(5, serie.plan, serie.raiz / "t01") == 0
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["veredicto"] == "TANDA_OK" and registro["postcheck"]["veredicto"] == "POSTCHECK_OK"
    assert [e["factura_id"] for e in registro["ejecuciones"]] == [f["id"] for f in plan["facturas"]]
    for e, f in zip(registro["ejecuciones"], plan["facturas"]):
        assert e["real"]["vigente"] == [["CONCILIADA", f["prevision"]["diferencia"],
                                         f["prevision"]["idempotency_key_prevista"], "MANUAL_ONE_SHOT"]]
        assert e["motivos"] == [] and _estado(pg, e["factura_id"]) == "CONCILIADA|0"
    assert pg.sql("select count(*) from public.facturas where conciliacion_bloqueado_por is not null") == "0"
    # Detalle por linea (2BR): la linea R17 con su diferencia de linea.
    assert pg.sql("select string_agg(distinct d.estado || ':' || d.diferencia, ',') from public.conciliacion_detalles d "
                  "where d.tipo_relacion = 'UNO_A_VARIOS'") == "COINCIDE:0.0000"
    # Guard: la misma tanda no se repite; la siguiente (hasta 20) encuentra la cola vacia y para sin escribir.
    with pytest.raises(FileExistsError):
        m.tanda(5, serie.plan, serie.raiz / "t01")
    antes = _huella(pg)
    assert m.tanda(20, serie.plan, serie.raiz / "t02") == 3
    registro = _leer(serie.raiz / "t02" / "tanda.json")
    assert (registro["maximo"], registro["motivos"], registro["ejecuciones"]) == (20, ["COLA_VACIA"], [])
    assert _huella(pg) == antes


def test_primera_tanda_como_maximo_5(serie):
    with pytest.raises(SystemExit, match="TAMANO_DE_TANDA_NO_ADMITIDO:6>5"):
        serie.m.tanda(6, serie.plan, serie.raiz / "t01")
    assert not (serie.raiz / "t01").exists()


@pytest.fixture
def serie_diferencia(pg17_nueva_base, tmp_path, monkeypatch):
    """08007969 sin la recepcion comun (50899): n.o 1 y DIFERENCIA 504,09."""
    return _serie(pg17_nueva_base, tmp_path, monkeypatch, recepcion_interno=50899, primera="08007969")


def test_para_si_el_numero_1_simula_diferencia(serie_diferencia):
    serie = serie_diferencia
    plan = _leer(serie.plan)
    assert (plan["facturas"][0]["numero_factura"], plan["facturas"][0]["prevision"]["resultado"],
            plan["facturas"][0]["prevision"]["diferencia"], plan["primera_no_conciliada"]) == (
        "08007969", "DIFERENCIA", "504.0900", 1)
    antes = _huella(serie.pg)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["motivos"] == [f"NUMERO_1_SIMULA_DIFERENCIA:{serie.ids['08007969']}:08007969:504.0900"]
    assert registro["ejecuciones"][0]["no_ejecutada"] is True and "retorno" not in registro["ejecuciones"][0]
    assert registro["postcheck"] == {"veredicto": "POSTCHECK_OK", "problemas": [], "facturas": [],
                                     "trabajadores": {"afecta_al_veredicto": False, "filas_cambiadas_por_tabla": {}}}
    assert _huella(serie.pg) == antes


def test_con_decision_de_pio_concilia_esa_diferencia_y_sigue(serie_diferencia):
    serie = serie_diferencia
    objetivo = serie.ids["08007969"]
    _editar_plan(serie, lambda d: d["decisiones_pio"].update(
        {objetivo: {"decision": "CONCILIAR_CON_DIFERENCIA", "diferencia": "504.0900"}}))
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 0
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["veredicto"] == "TANDA_OK" and len(registro["ejecuciones"]) == 5
    assert registro["ejecuciones"][0]["real"]["vigente"][0][:2] == ["DIFERENCIA", "504.0900"]
    assert _estado(serie.pg, objetivo) == "PENDIENTE_CONCILIAR|1"  # D-A: consume un intento, con backoff
    assert {_estado(serie.pg, serie.ids[n]) for n in ("08007970", "08007971", "08007972", "08007973")} == {
        "CONCILIADA|0"}


@pytest.mark.parametrize("variante", ["29", "30_rollback"])
def test_sin_la_30_para_antes_de_ejecutar(pg17_nueva_base, tmp_path, monkeypatch, variante):
    """Decision de Pio (2BR): primero desplegar la 30, despues conciliar."""
    serie = _serie(pg17_nueva_base, tmp_path, monkeypatch, variante)
    assert not all(_leer(serie.plan)["migracion_30"].values())
    antes = _huella(serie.pg)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["veredicto"] == "PARADA" and registro["ejecuciones"] == []
    assert registro["motivos"] == ["MIGRACION_30_AUSENTE:cf_detalles_por_linea", "MIGRACION_30_AUSENTE:valores_previos",
                                   "MIGRACION_30_AUSENTE:cf_persistir_conciliacion"]
    assert registro["postcheck"]["veredicto"] == "POSTCHECK_OK"
    assert _huella(serie.pg) == antes


def test_para_si_la_simulacion_inmediata_no_es_la_del_plan(serie):
    pg = serie.pg
    primero = _leer(serie.plan)["facturas"][0]
    pg.sql("update public.albaranes set importe_puc = importe_puc + 1 where id_contador = (select min(a.id_contador) "
           "from public.albaranes a join public.facturas_albaranes_extraidos e on e.numero_albaran = a.numero_albaran "
           f"where e.factura_id = {_lit(primero['id'])});")
    antes = _huella(pg)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["motivos"] and all(x.startswith("SIMULACION_DISTINTA_DEL_PLAN") for x in registro["motivos"])
    assert _huella(pg) == antes


def test_para_si_el_numero_1_no_esta_en_el_plan(serie):
    primero = _leer(serie.plan)["facturas"][0]["id"]
    _editar_plan(serie, lambda d: d.update(facturas=d["facturas"][1:]))
    antes = _huella(serie.pg)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    assert _leer(serie.raiz / "t01" / "tanda.json")["motivos"] == [f"NUMERO_1_FUERA_DEL_PLAN:{primero}"]
    assert _huella(serie.pg) == antes


def test_para_si_la_fila_del_numero_1_cambio_desde_el_plan(serie):
    primero = _leer(serie.plan)["facturas"][0]["id"]
    serie.pg.sql(f"update public.facturas set observaciones = 'cambio' where id = {_lit(primero)};")
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    assert _leer(serie.raiz / "t01" / "tanda.json")["motivos"] == [f"NUMERO_1_FILA_DISTINTA_DEL_PLAN:{primero}"]


@pytest.mark.parametrize("caso", ["git", "flags", "tareas", "claim"])
def test_puertas_paran_antes_de_ejecutar(serie, monkeypatch, caso):
    pg, m = serie.pg, serie.m
    if caso == "git":
        monkeypatch.setattr(m, "_estado_git", lambda: {**GIT_LIMPIO, "status": " M src/x.py"})
    elif caso == "flags":
        pg.sql("update public.cf_configuracion set conciliacion_automatica = true where id;")
    elif caso == "tareas":
        import auditoria_readonly as ar
        proxima = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20)).isoformat()
        monkeypatch.setattr(m, "_tareas", lambda: {"tareas": [
            {"nombre": n, "proxima": proxima, "ultima": None, "resultado": 0} for n in ar.TAREAS_ESPERADAS]})
    else:
        pg.sql("update public.facturas set conciliacion_bloqueado_por = 'otro', conciliacion_bloqueado_hasta = "
               f"now() + interval '5 minutes' where id = {_lit(serie.ids['08007971'])};")
    antes = _huella(pg)
    assert m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["ejecuciones"] == [] and registro["veredicto"] == "PARADA"
    esperado = {"git": "GIT_ARBOL_NO_LIMPIO", "flags": "FLAGS_INESPERADOS", "tareas": "TAREA",
                "claim": "CLAIMS_CONCILIACION"}[caso]
    assert any(esperado in x for x in registro["motivos"]), registro["motivos"]
    assert "postcheck" in registro and registro["postcheck"]["facturas"] == []
    assert _huella(pg) == antes


def test_para_por_fila_ajena_cambiada_con_postcheck(serie, monkeypatch):
    real = serie.m._ejecutar_una

    def con_efecto_colateral(cliente, directorio):
        retorno = real(cliente, directorio)
        serie.pg.sql("update public.albaranes set importe_pvp = importe_pvp + 1 "
                     "where id = (select min(id) from public.albaranes);")
        return retorno

    monkeypatch.setattr(serie.m, "_ejecutar_una", con_efecto_colateral)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert len(registro["ejecuciones"]) == 1
    assert any(x.startswith("FILA_CAMBIADA_AJENA:albaranes:") for x in registro["motivos"])
    assert registro["postcheck"]["veredicto"] == "POSTCHECK_REVISAR"


def test_para_por_excepcion(serie, monkeypatch):
    def fallar(cliente, directorio):
        raise RuntimeError("caida")

    monkeypatch.setattr(serie.m, "_ejecutar_una", fallar)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert "EXCEPCION" in registro["motivos"] and len(registro["ejecuciones"]) == 1
    assert registro["postcheck"]["veredicto"] == "POSTCHECK_OK"


pytestmark = pytest.mark.pg17_local
