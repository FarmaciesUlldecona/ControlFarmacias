"""Hito 2BJ: serie supervisada de normalizacion (``pruebas/auditoria_2bj/serie_normalizacion.py``).

PostgreSQL 17 local (plantilla "28"; desde el 2BL la serie exige la 27) con una cola real: HEFAME no autorizado (R2,
NO_SOPORTADO), un PDF roto (defecto de extraccion, R3) y el PDF Alliance multifactura del 2AP. Lecturas por la
puerta del 2AT sobre la base local en READ ONLY; escrituras con el worker manual real sobre ``ClientePg17``.
Tareas programadas fijas. Sin produccion ni Farmatic.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from types import SimpleNamespace

import pytest

import pg17_local as pgl
from pg17_local import ROOT, _lit, _registrar
from test_ensayo_fase4_2at import _ClienteServiceRole, _ConexionPg17

ROTO = b"%PDF-1.4\nno es un pdf valido 2BJ\n"


def _modulo():
    spec = importlib.util.spec_from_file_location(f"serie_2bj_{uuid.uuid4().hex[:6]}",
                                                  ROOT / "pruebas/auditoria_2bj/serie_normalizacion.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# --------------------------------------------------------------------------- sin base de datos

@pytest.mark.parametrize("analisis,esperado", [
    ({"etapa_detencion": "EXTRACCION_MOTOR", "motivo": "EXCEPCION_MOTOR"}, ("DEFECTO", "EXTRACCION_LOCAL_ERROR")),
    ({"etapa_detencion": "RECONOCIMIENTO", "motivo": "LAYOUT_NO_RECONOCIDO"}, ("NO_SOPORTADO", "PROVEEDOR_NO_RECONOCIDO")),
    ({"etapa_detencion": "RECONOCIMIENTO", "motivo": "PENDIENTE_OCR"},
     ("NO_SOPORTADO", "REQUIERE_OCR_O_LUNA_NO_AUTORIZADO")),
    ({"etapa_detencion": "AUTORIDAD", "motivo": "PROVEEDOR_NO_SOPORTADO_MANUAL"},
     ("NO_SOPORTADO", "PROVEEDOR_NO_SOPORTADO_MANUAL")),
    ({"etapa_detencion": "COMPLETITUD", "motivo": "DOCUMENTO_INCOMPLETO"}, ("DEFECTO", "DOCUMENTO_INCOMPLETO")),
    ({"etapa_detencion": "TIEMPO_LIMITE", "motivo": "TIMEOUT_180S"}, ("SIN_PREDICCION", "TIMEOUT_180S")),
    ({"etapa_detencion": "AUTORIZACION", "motivo": "algo raro"}, ("SIN_PREDICCION", "algo raro")),
])
def test_prediccion_traduce_al_motivo_y_la_clase_del_worker_real(analisis, esperado):
    p = _modulo().prediccion_desde_analisis(analisis)
    assert (p["clase"], p["motivo"]) == esperado


def test_defecto_previsto_pasa_a_revision_al_maximo_r3():
    m = _modulo()
    assert m.resultado_esperado({"clase": "DEFECTO"}, 2, 4)["estado_lectura"] == "ERROR"
    assert m.resultado_esperado({"clase": "DEFECTO"}, 3, 4) == {
        "estado_lectura": "REVISION", "ultima_clase_fallo": "DEFECTO_DOCUMENTO", "intentos": 4, "facturas": []}


def test_postcheck_informa_trabajadores_aparte_sin_veredicto():
    """Mejora aprobada por Pio (2026-11-13): Trabajadores se informa aparte y no hace fallar el postcheck."""
    m = _modulo()
    antes = {"trabajadoras": {"t1": ["h1", None]}, "festivos": {}, "albaranes": {"a1": ["ha", None]}}
    despues = {"trabajadoras": {"t1": ["h1b", None], "t2": ["h2", None]}, "festivos": {"f1": ["hf", None]},
               "albaranes": {"a1": ["ha", None]}}
    assert m.diferencias_filas(antes, despues, set(), {"documentos_facturas"}) == []
    assert m.cambios_trabajadores(antes, despues) == {"festivos": 1, "trabajadoras": 2}
    # Fuera de Trabajadores el criterio 2AX no cambia.
    despues["albaranes"] = {"a1": ["otra", None]}
    assert m.diferencias_filas(antes, despues, set(), {"documentos_facturas"}) == ["FILA_CAMBIADA_AJENA:albaranes:a1"]


# --------------------------------------------------------------------------- PostgreSQL 17 local

@pytest.fixture
def serie(pg17_nueva_base, tmp_path, monkeypatch):
    return _serie(pg17_nueva_base, tmp_path, monkeypatch, "28")


def _serie(pg17_nueva_base, tmp_path, monkeypatch, variante):
    pg = pg17_nueva_base(variante)
    pg.sql("update public.documentos_facturas set estado_lectura = 'NORMALIZADA' "
           "where estado_lectura in ('PENDIENTE', 'ERROR');")
    cliente = _ClienteServiceRole(pg)  # como PostgREST con la clave de servicio (2AT)
    pdfs = {"hefame": pgl.HEFAME.read_bytes(), "roto": ROTO, "alliance": pgl.ALLIANCE.read_bytes()}
    ids = {nombre: _registrar(pg, cliente, contenido, orden) for orden, (nombre, contenido)
           in enumerate(pdfs.items(), start=1)}
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    for nombre, contenido in pdfs.items():
        (mirror / f"{nombre}.pdf").write_bytes(contenido)
    sentencias: list[str] = []
    m = _modulo()
    import auditoria_readonly as ar

    monkeypatch.setattr(ar, "_conectar", lambda: (ar.PROJECT_REF, _ConexionPg17(pg, sentencias)))
    monkeypatch.setattr(m, "_tareas", lambda: {"tareas": [
        {"nombre": n, "proxima": None, "ultima": None, "resultado": 0} for n in ar.TAREAS_ESPERADAS]})
    monkeypatch.setattr(m, "_cliente", lambda: cliente)
    plan = tmp_path / "plan.json"
    assert m.plan(plan, mirror) == 0
    return SimpleNamespace(pg=pg, m=m, ids=ids, plan=plan, raiz=tmp_path / "serie", sentencias=sentencias,
                           cliente=cliente)


def _leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


def _huella(pg):
    return pg.sql("select md5(string_agg(md5(to_jsonb(d)::text), '' order by id)) from public.documentos_facturas d")


def _estado(pg, documento_id):
    return pg.sql(f"select estado_lectura from public.documentos_facturas where id = {_lit(documento_id)}")


def test_plan_predice_en_orden_y_es_de_solo_lectura(serie):
    plan = _leer(serie.plan)
    assert [d["id"] for d in plan["documentos"]] == [serie.ids["hefame"], serie.ids["roto"], serie.ids["alliance"]]
    assert [d["prediccion"]["clase"] for d in plan["documentos"]] == ["NO_SOPORTADO", "DEFECTO", "ALLIANCE"]
    alliance = plan["documentos"][2]["prediccion"]
    assert alliance["completa"] and len(alliance["facturas"]) == 3
    assert serie.sentencias and all(s.lstrip().lower().startswith(("select", "with", "set local"))
                                    for s in serie.sentencias)


def test_primera_tanda_como_maximo_5(serie):
    with pytest.raises(SystemExit, match="TAMANO_DE_TANDA_NO_ADMITIDO:6>5"):
        serie.m.tanda(6, serie.plan, serie.raiz / "t01")
    assert not (serie.raiz / "t01").exists()


def test_tanda_ejecuta_hasta_el_corte_alliance_con_postcheck_por_fila(serie):
    pg, m = serie.pg, serie.m
    assert m.tanda(5, serie.plan, serie.raiz / "t01") == 0
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["veredicto"] == "TANDA_OK" and registro["postcheck"]["veredicto"] == "POSTCHECK_OK"
    assert [(e["clase"], e["real"]["estado_lectura"]) for e in registro["ejecuciones"]] == [
        ("NO_SOPORTADO", "PROVEEDOR_NO_SOPORTADO"), ("DEFECTO", "ERROR"), ("ALLIANCE", "NORMALIZADA")]
    assert registro["postcheck"]["corte_alliance"] is True
    assert len(registro["ejecuciones"][2]["real"]["facturas"]) == 3
    assert pg.sql("select count(*) from public.documentos_facturas where estado_lectura = 'NORMALIZANDO'") == "0"
    # Guard: la misma tanda no se repite.
    with pytest.raises(FileExistsError):
        m.tanda(5, serie.plan, serie.raiz / "t01")
    # Tras una tanda correcta se admiten 20; la cola queda vacia (el defecto esta en backoff): PARADA sin escribir.
    antes = _huella(pg)
    assert m.tanda(20, serie.plan, serie.raiz / "t02") == 3
    registro = _leer(serie.raiz / "t02" / "tanda.json")
    assert (registro["maximo"], registro["motivos"], registro["ejecuciones"]) == (20, ["COLA_VACIA"], [])
    assert _huella(pg) == antes


def test_parada_por_resultado_distinto_del_plan(serie):
    plan = _leer(serie.plan)
    plan["documentos"][0]["prediccion"] = {"clase": "DEFECTO", "motivo": "EXTRACCION_LOCAL_ERROR"}
    serie.plan.write_text(json.dumps(plan), encoding="utf-8")
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert len(registro["ejecuciones"]) == 1 and registro["veredicto"] == "PARADA"
    assert any(x.startswith("RESULTADO_INESPERADO:estado_lectura") for x in registro["motivos"])
    assert _estado(serie.pg, serie.ids["roto"]) == "PENDIENTE"  # no siguio
    # 2BK: la parada tambien hace el postcheck 2AX por fila (solo cambio el documento ejecutado).
    assert registro["postcheck"] == {"veredicto": "POSTCHECK_OK", "problemas": [],
                                     "documentos": [serie.ids["hefame"]], "corte_alliance": False,
                                     "trabajadores": {"afecta_al_veredicto": False, "filas_cambiadas_por_tabla": {}}}
    assert (serie.raiz / "t01" / "snapshot_post.json").exists()


def test_parada_por_persistencia_cancelada_con_postcheck(serie, monkeypatch):
    """Caso de produccion (tanda 5, 2026-11-02): la RPC multifactura cae por statement timeout."""
    real = serie.cliente._rpc

    def cancelada(nombre, payload):
        if nombre == "cf_persistir_documento_multifactura":
            raise RuntimeError("canceling statement due to statement timeout")
        return real(nombre, payload)

    monkeypatch.setattr(serie.cliente, "_rpc", cancelada)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["veredicto"] == "PARADA" and len(registro["ejecuciones"]) == 3
    assert any(x.startswith("RETORNO_INESPERADO") for x in registro["motivos"])
    assert registro["postcheck"]["veredicto"] == "POSTCHECK_OK"
    assert registro["postcheck"]["documentos"] == [serie.ids["hefame"], serie.ids["roto"], serie.ids["alliance"]]
    assert _estado(serie.pg, serie.ids["alliance"]) == "ERROR"
    assert serie.pg.sql("select count(*) from public.facturas f join public.documentos_facturas d "
                        f"on d.id = f.documento_id where d.id = {_lit(serie.ids['alliance'])}") == "0"


def test_parada_antes_de_ejecutar_si_el_numero_1_no_esta_en_el_plan(serie):
    pg = serie.pg
    nuevo = _registrar(pg, serie.cliente, b"%PDF-1.4\notro documento\n", 0)
    antes = _huella(pg)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["motivos"] == [f"NUMERO_1_FUERA_DEL_PLAN:{nuevo}"] and registro["ejecuciones"] == []
    assert _huella(pg) == antes


def test_parada_antes_de_ejecutar_sin_prediccion(serie):
    plan = _leer(serie.plan)
    plan["documentos"][0]["prediccion"] = {"clase": "SIN_PREDICCION", "motivo": "AUSENTE_DEL_MIRROR"}
    serie.plan.write_text(json.dumps(plan), encoding="utf-8")
    antes = _huella(serie.pg)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    assert _leer(serie.raiz / "t01" / "tanda.json")["motivos"][0].startswith("NUMERO_1_SIN_PREDICCION")
    assert _huella(serie.pg) == antes


def test_parada_por_excepcion(serie, monkeypatch):
    def fallar(cliente, directorio):
        raise RuntimeError("caida")

    monkeypatch.setattr(serie.m, "_ejecutar_una", fallar)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert "EXCEPCION" in registro["motivos"] and len(registro["ejecuciones"]) == 1


def test_parada_por_huerfano(serie, monkeypatch):
    def morir_tras_el_claim(cliente, directorio):
        serie.pg.json("select id from public.cf_reclamar_documento_normalizacion_manual_one_shot('w-muere', 300)")
        return SimpleNamespace(documentos_reclamados=1, modo_ejecucion="MANUAL_ONE_SHOT")

    monkeypatch.setattr(serie.m, "_ejecutar_una", morir_tras_el_claim)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert "HUERFANO:1" in registro["motivos"]
    assert "NORMALIZANDO_O_HUERFANOS_TRAS_LA_TANDA" in registro["postcheck"]["problemas"]


def test_parada_por_fila_ajena_cambiada(serie, monkeypatch):
    real = serie.m._ejecutar_una

    def con_efecto_colateral(cliente, directorio):
        retorno = real(cliente, directorio)
        serie.pg.sql("update public.albaranes set importe_pvp = importe_pvp + 1 "
                     "where id = (select min(id) from public.albaranes);")
        return retorno

    monkeypatch.setattr(serie.m, "_ejecutar_una", con_efecto_colateral)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert any(x.startswith("FILA_CAMBIADA_AJENA:albaranes:") for x in registro["motivos"])
    assert len(registro["ejecuciones"]) == 1
    assert registro["postcheck"]["veredicto"] == "POSTCHECK_REVISAR"
    assert any(x.startswith("FILA_CAMBIADA_AJENA:albaranes:") for x in registro["postcheck"]["problemas"])


@pytest.mark.parametrize("variante,esperado", [("26", "f"), ("27_rollback", "f"), ("27", "t"), ("28", "t"),
                                               ("28_rollback", "t")])
def test_marcas_de_la_27_por_variante(pg17_nueva_base, variante, esperado):
    assert pg17_nueva_base(variante).sql(_modulo().SQL_MARCAS_27 + ";") == esperado


@pytest.mark.parametrize("variante", ["26", "27_rollback"])
def test_sin_la_27_para_antes_de_ejecutar(pg17_nueva_base, tmp_path, monkeypatch, variante):
    """2BL (decision de Pio): sin las marcas de la 27, PARADA sin ejecutar nada."""
    serie = _serie(pg17_nueva_base, tmp_path, monkeypatch, variante)
    antes = _huella(serie.pg)
    assert serie.m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["veredicto"] == "PARADA" and registro["ejecuciones"] == []
    assert registro["motivos"] == ["MIGRACION_27_AUSENTE"]
    assert _huella(serie.pg) == antes


@pytest.mark.parametrize("caso", ["flags", "tareas", "normalizando"])
def test_puertas_paran_antes_de_ejecutar(serie, monkeypatch, caso):
    pg, m = serie.pg, serie.m
    if caso == "flags":
        pg.sql("update public.cf_configuracion set normalizacion_automatica = true where id;")
    elif caso == "tareas":
        import datetime as dt
        proxima = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20)).isoformat()
        import auditoria_readonly as ar
        monkeypatch.setattr(m, "_tareas", lambda: {"tareas": [
            {"nombre": n, "proxima": proxima, "ultima": None, "resultado": 0} for n in ar.TAREAS_ESPERADAS]})
    else:
        pg.sql("update public.documentos_facturas set estado_lectura = 'NORMALIZANDO', bloqueado_por = 'w', "
               f"bloqueado_hasta = now() - interval '1 hour' where id = {_lit(serie.ids['roto'])};")
    antes = _huella(pg)
    assert m.tanda(5, serie.plan, serie.raiz / "t01") == 3
    registro = _leer(serie.raiz / "t01" / "tanda.json")
    assert registro["ejecuciones"] == [] and registro["veredicto"] == "PARADA"
    esperado = {"flags": "FLAGS_INESPERADOS", "tareas": "TAREA", "normalizando": "DOCUMENTOS_EN_NORMALIZANDO"}[caso]
    assert any(esperado in x for x in registro["motivos"]), registro["motivos"]
    assert _huella(pg) == antes
    assert registro["postcheck"]["documentos"] == [] and registro["postcheck"]["veredicto"] == (
        "POSTCHECK_REVISAR" if caso == "normalizando" else "POSTCHECK_OK")


pytestmark = pytest.mark.pg17_local
