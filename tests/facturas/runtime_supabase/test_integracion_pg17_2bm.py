"""Hito 2BM: migracion 28 (persistencia multifactura ligera) en PostgreSQL 17 local.

Plantillas (pg17_local): "27" (estado productivo), "28" = 27 + migracion 28 dos veces, "28_rollback" = 28 +
rollback. Equivalencia: cada escenario del 2BK con el MISMO payload real (PDF Alliance multifactura del 2AP) sobre
una base 27 y otra 28; el estado completo de las tablas de normalizacion coincide, con ``resultado_json``
comparado tras reconstruir las referencias desde ``facturas.datos_extraidos`` (y sin la firma de la solicitud,
cuya formula cambia en la 28). Sin produccion ni Farmatic.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import uuid
from types import SimpleNamespace

import pytest

import pg17_local as pgl
from pg17_local import FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, _lit, base_desde, esquema
from test_ensayo_fase4_2at import _ClienteServiceRole
from test_integracion_pg17_2az import (  # noqa: F401 (fixture)
    CONSULTAS_HUELLA, DSN_FICTICIO, _datos_previos, _huella, contenedor_tcp)
from test_integracion_pg17_2ba import _reservas
from test_integracion_pg17_2bk import (
    DOC_A, DOC_B, ESCENARIOS, ESPERADO, MULTI, TABLAS, UUID, _base, _canonico, _captura, _claim, _documento,
    _intento, _numerado, _nuevo, _persistir)
from src.facturas.completitud_documental import validar_documento_antes_de_persistir
from src.facturas.runtime_supabase.multifactura import reconstruir_resultado_json, tiene_referencias

pytestmark = pytest.mark.pg17_local

MIGRACION_28 = MIG / "28_cf_persistencia_multifactura_ligera.sql"
ROLLBACK_28 = MIG / "28_cf_persistencia_multifactura_ligera.rollback.sql"
RUTA_28 = "sql/migrations/28_cf_persistencia_multifactura_ligera.sql"
SCRIPT_28 = ROOT / "pruebas/auditoria_2bm/desplegar_28.py"
COLUMNAS_LZ4 = (("normalizacion_ejecuciones", "resultado_json"), ("facturas", "datos_extraidos"),
                ("facturas_albaranes_extraidos", "provenance"), ("facturas_vencimientos", "provenance"),
                ("facturas_impuestos", "provenance"), ("facturas_movimientos", "provenance"),
                ("facturas_incidencias", "provenance"), ("facturas_incidencias", "detalle_tecnico"))

# resultado_json con las referencias sustituidas por su factura original (formato 27), en SQL puro: vale para
# bases 27 (sin referencias) y 28.
RECONSTRUIDO = (
    "case when jsonb_typeof(t.resultado_json->'facturas') = 'array' then jsonb_set(t.resultado_json, '{facturas}', "
    "(select coalesce(jsonb_agg(case when x ? '_factura_persistida' then "
    "((select f.datos_extraidos from public.facturas f where f.documento_id = t.documento_id "
    "and f.proyeccion_clave = x #>> '{_factura_persistida,proyeccion_clave}') - 'factura_id' "
    "- 'identidad_economica_clave') || (x #> '{_factura_persistida,claves_originales}') else x end order by o), "
    "'[]'::jsonb) from jsonb_array_elements(t.resultado_json->'facturas') with ordinality u(x, o))) "
    "else t.resultado_json end")
GRANDES = {
    "facturas": "to_jsonb(t) - 'datos_extraidos' || jsonb_build_object('datos_md5', md5(t.datos_extraidos::text))",
    "normalizacion_ejecuciones": "to_jsonb(t) - 'resultado_json' || jsonb_build_object('resultado_md5', "
                                 f"md5(coalesce((({RECONSTRUIDO}) #- '{{multifactura,firma_solicitud}}')::text, '')))",
}


def _volcado(pg) -> dict:
    """Estado de las tablas de normalizacion; resultado_json reconstruido y sin la firma de la solicitud."""
    filas = {}
    for tabla in TABLAS:
        expresion = GRANDES.get(tabla, "to_jsonb(t)")
        filas[tabla] = sorted(
            (json.dumps(_canonico(f), sort_keys=True, ensure_ascii=False)
             for f in pg.json(f"select {expresion} as fila from public.{tabla} t")),
            key=lambda s: UUID.sub("U", s))
    return filas


def _resultados(pg, doc=DOC_A) -> list:
    return [r["r"] for r in pg.json(f"select resultado_json as r from public.normalizacion_ejecuciones "
                                    f"where documento_id = {_lit(doc)} order by intento")]


def _reconstruidos(pg, doc=DOC_A) -> list:
    return [r["r"] for r in pg.json(f"select {RECONSTRUIDO} as r from public.normalizacion_ejecuciones t "
                                    f"where t.documento_id = {_lit(doc)} order by t.intento")]


def _firma_28(pg, captura, segmentos=None) -> str:
    segmentos = captura["p_segmentos_autorizados"] if segmentos is None else segmentos
    documento = _lit(json.dumps(captura["p_resultado"], ensure_ascii=False)) + "::jsonb"
    seleccion = "array[" + ",".join(_lit(s) for s in segmentos) + "]::text[]"
    return pg.sql(f"select encode(extensions.digest({documento}::text || '|' || to_jsonb({seleccion})::text, "
                  "'sha256'), 'hex');")


# --------------------------------------------------------------------------- equivalencia con la 27

@pytest.mark.parametrize("escenario", sorted(ESCENARIOS))
def test_28_da_el_mismo_resultado_que_la_27(pg17_nueva_base, tmp_path, escenario):
    captura = _captura(pg17_nueva_base, tmp_path)
    estados = {}
    for variante in ("27", "28"):
        pg = _base(pg17_nueva_base, variante)
        pasos = ESCENARIOS[escenario](pg, captura)
        estados[variante] = _numerado({"pasos": _canonico(pasos), "volcado": _volcado(pg)})
    assert estados["28"] == estados["27"]
    if escenario in ESPERADO:
        objetivo = DOC_B if escenario in ("duplicado", "version_incompatible") else DOC_A
        [documento] = pg.json("select estado_persistencia, inventario_facturas from public.documentos_facturas "
                              f"where id = {_lit(objetivo)}")
        persistencia, inventario = ESPERADO[escenario]
        assert documento["estado_persistencia"] == persistencia
        assert sorted(i["estado"] for i in documento["inventario_facturas"]) == sorted(inventario)


@pytest.mark.parametrize("escenario,referencias,completas", [("nuevo", 3, 0), ("parcial", 1, 2), ("duplicado", 0, 3)])
def test_28_guarda_referencias_solo_de_las_facturas_que_persiste(pg17_nueva_base, tmp_path, escenario, referencias,
                                                                  completas):
    captura = _captura(pg17_nueva_base, tmp_path)
    pg = _base(pg17_nueva_base, "28")
    ESCENARIOS[escenario](pg, captura)
    ultimo = pg.json("select documento_id, resultado_json from public.normalizacion_ejecuciones "
                     "order by created_at desc, intento desc limit 1")[0]
    facturas = ultimo["resultado_json"]["facturas"]
    assert sum("_factura_persistida" in f for f in facturas) == referencias
    assert sum("_factura_persistida" not in f for f in facturas) == completas
    # Trazabilidad: datos_extraidos de cada factura referenciada es la factura completa (mas las dos claves).
    for f in facturas:
        if "_factura_persistida" in f:
            [fila] = pg.json("select datos_extraidos from public.facturas where documento_id = "
                             f"{_lit(ultimo['documento_id'])} and proyeccion_clave = "
                             f"{_lit(f['_factura_persistida']['proyeccion_clave'])}")
            original = next(o for o in captura["p_resultado"]["facturas"]
                            if o["provenance"]["segment_id"] == fila["datos_extraidos"]["provenance"]["segment_id"])
            assert {**{k: v for k, v in fila["datos_extraidos"].items()
                       if k not in ("factura_id", "identidad_economica_clave")},
                    **f["_factura_persistida"]["claves_originales"]} == original
    # La lectura reconstruida es la de la 27: el payload con la firma y la seleccion.
    reconstruido = _reconstruidos(pg, ultimo["documento_id"])[-1]
    assert reconstruido["facturas"] == captura["p_resultado"]["facturas"]


def test_28_escribe_menos(pg17_nueva_base, tmp_path):
    captura = _captura(pg17_nueva_base, tmp_path)
    tamanos = {}
    for variante in ("27", "28"):
        pg = _base(pg17_nueva_base, variante)
        _nuevo(pg, captura)
        tamanos[variante] = int(pg.sql("select pg_column_size(resultado_json) from public.normalizacion_ejecuciones "
                                       f"where documento_id = {_lit(DOC_A)}"))
    assert tamanos["28"] * 20 < tamanos["27"], tamanos


# --------------------------------------------------------------------------- firma de la solicitud

def test_replay_y_rechazo_con_la_firma_nueva(pg17_nueva_base, tmp_path):
    captura = _captura(pg17_nueva_base, tmp_path)
    pg = _base(pg17_nueva_base, "28")
    [paso] = _nuevo(pg, captura)
    assert paso[0] == "OK"
    assert _resultados(pg)[0]["multifactura"]["firma_solicitud"] == _firma_28(pg, captura)
    assert _intento(_persistir, pg, DOC_A, "w-a", "k-a", captura) == paso
    otro = dict(captura["p_resultado"], extra_2bm=1)
    assert _intento(_persistir, pg, DOC_A, "w-a", "k-a", captura, resultado=otro) == \
        ("ERROR", "IDEMPOTENCIA_PAYLOAD_DISTINTO")
    assert _intento(_persistir, pg, DOC_A, "w-a", "k-a", captura, segmentos=captura["p_segmentos_autorizados"][:1]) \
        == ("ERROR", "IDEMPOTENCIA_PAYLOAD_DISTINTO")


def test_replay_de_ejecucion_con_la_firma_antigua_sin_falsos_rechazos(pg17_nueva_base, tmp_path):
    """Ejecucion guardada con la 27 (firma con objeto intermedio); la 28 se despliega despues."""
    captura = _captura(pg17_nueva_base, tmp_path)
    pg = _base(pg17_nueva_base, "27")
    [paso] = _nuevo(pg, captura)
    firma_27 = _resultados(pg)[0]["multifactura"]["firma_solicitud"]
    pg.sql(MIGRACION_28.read_text(encoding="utf-8"))
    assert firma_27 != _firma_28(pg, captura)
    antes = _volcado(pg)
    # Misma solicitud: replay de la ejecucion antigua, sin rechazo.
    assert _intento(_persistir, pg, DOC_A, "w-a", "k-a", captura) == paso
    # Otra solicitud con la misma clave: rechazo, como hoy.
    otro = dict(captura["p_resultado"], extra_2bm=1)
    assert _intento(_persistir, pg, DOC_A, "w-a", "k-a", captura, resultado=otro) == \
        ("ERROR", "IDEMPOTENCIA_PAYLOAD_DISTINTO")
    despues = _volcado(pg)
    assert {t: v for t, v in despues.items() if t != "historial_facturas"} == \
        {t: v for t, v in antes.items() if t != "historial_facturas"}
    assert _resultados(pg)[0]["multifactura"]["firma_solicitud"] == firma_27


# --------------------------------------------------------------------------- historico de relecturas

def test_relectura_que_sobrescribe_conserva_la_copia_completa_en_la_ejecucion_previa(pg17_nueva_base, tmp_path):
    captura = _captura(pg17_nueva_base, tmp_path)
    pg = _base(pg17_nueva_base, "28")
    _nuevo(pg, captura)
    [primera] = _reconstruidos(pg)
    assert tiene_referencias(_resultados(pg)[0])
    [fila] = pg.json("select proyeccion_clave, datos_extraidos from public.facturas "
                     f"where documento_id = {_lit(DOC_A)} order by numero_factura limit 1")
    clave = fila["proyeccion_clave"]
    nueva = dict(fila["datos_extraidos"], factura_id=clave, relectura_2bm=True)
    # Relectura explicita (reprocesado) que sobrescribe la fila con la RPC de un documento.
    pg.sql(f"select public.cf_solicitar_reprocesado({_lit(DOC_A)}, 'pio');")
    _claim(pg, "w-r")
    paso = _intento(_ClienteServiceRole(pg)._rpc, "cf_persistir_normalizacion", {
        "p_documento_id": DOC_A, "p_worker_id": "w-r", "p_disparador": "REPROCESADO",
        "p_idempotency_key": "k-r", "p_resultado_hash": captura["p_resultado_hash"],
        "p_resultado": {"resultado_json": dict(captura["p_resultado"], facturas=[nueva]), "uso_luna": False}})
    assert paso[0] == "OK"
    assert pg.json(f"select datos_extraidos from public.facturas where documento_id = {_lit(DOC_A)} "
                   f"and proyeccion_clave = {_lit(clave)}")[0]["datos_extraidos"]["relectura_2bm"] is True
    previa = _resultados(pg)[0]
    # La factura sobrescrita esta ahora completa en la ejecucion previa; las demas siguen referenciadas.
    sobrescrita = [f for f in previa["facturas"] if "_factura_persistida" not in f]
    assert len(sobrescrita) == 1 and "relectura_2bm" not in sobrescrita[0]
    assert sum("_factura_persistida" in f for f in previa["facturas"]) == 2
    # La lectura previa reconstruida no cambia.
    assert _reconstruidos(pg)[0] == primera


def test_upsert_con_datos_identicos_no_desvia_el_historico(pg17_nueva_base, tmp_path):
    """Un upsert identico cambia normalizacion_ejecucion_id sin cambiar el contenido; un cambio posterior debe
    seguir conservando la lectura de la ejecucion original (revision 2BM)."""
    captura = _captura(pg17_nueva_base, tmp_path)
    pg = _base(pg17_nueva_base, "28")
    _nuevo(pg, captura)
    [primera] = _reconstruidos(pg)
    [fila] = pg.json("select proyeccion_clave, datos_extraidos from public.facturas "
                     f"where documento_id = {_lit(DOC_A)} order by numero_factura limit 1")
    pg.sql(f"select public.cf_solicitar_reprocesado({_lit(DOC_A)}, 'pio');")
    _claim(pg, "w-r")
    paso = _intento(_ClienteServiceRole(pg)._rpc, "cf_persistir_normalizacion", {
        "p_documento_id": DOC_A, "p_worker_id": "w-r", "p_disparador": "REPROCESADO",
        "p_idempotency_key": "k-r", "p_resultado_hash": captura["p_resultado_hash"],
        "p_resultado": {"resultado_json": dict(captura["p_resultado"], facturas=[fila["datos_extraidos"]]),
                        "uso_luna": False}})
    assert paso[0] == "OK"
    assert pg.sql(f"select normalizacion_ejecucion_id::text from public.facturas where documento_id = {_lit(DOC_A)} "
                  f"and proyeccion_clave = {_lit(fila['proyeccion_clave'])}") == paso[1]
    assert tiene_referencias(_resultados(pg)[0])
    pg.sql("update public.facturas set datos_extraidos = jsonb_set(datos_extraidos, '{cambio_2bm}', 'true') "
           f"where documento_id = {_lit(DOC_A)};")
    previa = _resultados(pg)[0]
    assert not tiene_referencias(previa) and previa == primera


def test_borrar_una_factura_conserva_la_lectura_previa(pg17_nueva_base, tmp_path):
    """Una factura persistida no se puede borrar (historial append-only); el trigger cubre igualmente el DELETE
    (fila sin historial)."""
    captura = _captura(pg17_nueva_base, tmp_path)
    pg = _base(pg17_nueva_base, "28")
    _nuevo(pg, captura)
    [primera] = _reconstruidos(pg)
    crudo = _resultados(pg)
    with pytest.raises(RuntimeError, match="historial_facturas es append-only"):
        pg.sql(f"delete from public.facturas where documento_id = {_lit(DOC_A)};")
    assert _resultados(pg) == crudo
    # Sin historial (solo para ejercitar el trigger): el borrado deja la lectura completa en la ejecucion.
    pg.sql("alter table public.historial_facturas disable trigger user;"
           f"delete from public.historial_facturas where documento_id = {_lit(DOC_A)};"
           "alter table public.historial_facturas enable trigger user;")
    pg.sql(f"delete from public.facturas where documento_id = {_lit(DOC_A)};")
    [previa] = _resultados(pg)
    assert not tiene_referencias(previa) and previa == primera


def test_cualquier_cambio_de_datos_extraidos_conserva_la_lectura_previa(pg17_nueva_base, tmp_path):
    """El trigger cubre tambien un UPDATE directo; los demas cambios de la fila no tocan las ejecuciones."""
    captura = _captura(pg17_nueva_base, tmp_path)
    pg = _base(pg17_nueva_base, "28")
    _nuevo(pg, captura)
    [primera] = _reconstruidos(pg)
    crudo = _resultados(pg)
    pg.sql("update public.facturas set fecha_actualizacion = now(), estado_conciliacion_cf = estado_conciliacion_cf "
           f"where documento_id = {_lit(DOC_A)};")
    assert _resultados(pg) == crudo
    pg.sql("update public.facturas set datos_extraidos = jsonb_set(datos_extraidos, '{cambio_2bm}', 'true') "
           f"where documento_id = {_lit(DOC_A)};")
    [previa] = _resultados(pg)
    assert not tiene_referencias(previa) and previa == primera


# --------------------------------------------------------------------------- conciliacion

def test_reconstruccion_pura():
    datos = {"a": 1, "factura_id": "K", "identidad_economica_clave": "K"}
    resultado = {"documento_completo_demostrado": True, "facturas": [
        {"_factura_persistida": {"proyeccion_clave": "K", "claves_originales": {"factura_id": "orig"}}},
        {"b": 2}]}
    assert reconstruir_resultado_json(resultado, {"K": datos}) == {
        "documento_completo_demostrado": True, "facturas": [{"a": 1, "factura_id": "orig"}, {"b": 2}]}
    assert not tiene_referencias({"facturas": [{"b": 2}]})
    sin = {"facturas": [{"b": 2}]}
    assert reconstruir_resultado_json(sin, {}) is sin
    with pytest.raises(ValueError, match="RESULTADO_JSON_REFERENCIA_NO_RESUELTA"):
        reconstruir_resultado_json(resultado, {})


def test_conciliacion_revalida_la_farmacia_sobre_la_lectura_reconstruida(pg17_nueva_base, tmp_path):
    sys.path.insert(0, str(ROOT / "pruebas/auditoria_2bk"))
    import medir_persistencia as mp

    captura = _captura(pg17_nueva_base, tmp_path)
    resultados = {}
    for variante in ("27", "28"):
        pg = _base(pg17_nueva_base, variante)
        _nuevo(pg, captura)
        if variante == "28":
            crudo = _resultados(pg)[0]
            # Sin reconstruir, la barrera de farmacia no puede demostrar las facturas referenciadas.
            with pytest.raises(Exception):
                validar_documento_antes_de_persistir("PIO", crudo)
            validar_documento_antes_de_persistir("PIO", _reconstruidos(pg)[0])
        cliente = _ClienteServiceRole(pg)
        conciliacion = mp._conciliar(pg, cliente, SimpleNamespace(medidas=[]))
        resultados[variante] = {k: conciliacion[k] for k in ("factura", "lineas", "vigente", "concilio")}
    assert resultados["28"] == resultados["27"]
    assert resultados["28"]["concilio"] is True and resultados["28"]["vigente"]


# --------------------------------------------------------------------------- migracion

def test_generador_reproduce_la_28_y_su_rollback():
    spec = importlib.util.spec_from_file_location("generar_28", ROOT / "pruebas/auditoria_2bm/generar_migracion_28.py")
    generador = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generador)
    assert generador.migracion() == MIGRACION_28.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert generador.rollback() == ROLLBACK_28.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_rollback_28_devuelve_exactamente_el_esquema_27(pg17_nueva_base):
    assert esquema(pg17_nueva_base("28_rollback")) == esquema(pg17_nueva_base("27"))
    assert esquema(pg17_nueva_base("28")) != esquema(pg17_nueva_base("27"))


def test_rollback_28_devuelve_resultado_json_al_formato_27(pg17_nueva_base, tmp_path):
    captura = _captura(pg17_nueva_base, tmp_path)
    pg = _base(pg17_nueva_base, "28")
    ESCENARIOS["parcial"](pg, captura)
    reconstruidos = _reconstruidos(pg)
    pg.sql(ROLLBACK_28.read_text(encoding="utf-8"))
    assert _resultados(pg) == reconstruidos
    assert not any(tiene_referencias(r) for r in _resultados(pg))


def test_28_exige_la_27(pg17_nueva_base):
    with pytest.raises(RuntimeError, match="MIGRACION_27_AUSENTE"):
        pg17_nueva_base("26").sql(MIGRACION_28.read_text(encoding="utf-8"))


def test_28_no_altera_datos_existentes(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("27")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    consulta = ("select md5(string_agg(md5(to_jsonb(e)::text), '' order by e.id)) "
                "from public.normalizacion_ejecuciones e")
    ejecuciones = pg.sql(consulta)
    referencia = esquema(pg17_nueva_base("28"))
    pg.sql(MIGRACION_28.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_28.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert pg.sql(consulta) == ejecuciones
    assert esquema(pg) == referencia and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_privilegios_y_compresion_de_la_28(pg17_nueva_base):
    pg = pg17_nueva_base("28")
    rpc = ("public.cf_persistir_normalizacion(uuid,text,text,text,text,jsonb)",
           "public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[],text)")
    internas = ("public.cf_referencia_factura(jsonb,text)", "public.cf_factura_desde_referencia(jsonb,jsonb)",
                "public.cf_materializar_referencia()",
                "public.cf_persistir_normalizacion_nucleo(uuid,text,text,text,text,jsonb,jsonb)",
                "public.cf_persistir_normalizacion_nucleo(uuid,text,text,text,text,jsonb,jsonb,jsonb,jsonb)",
                "public.cf_persistir_documento_multifactura_nucleo(uuid,text,text,text,jsonb,text[],text)",
                "public.cf_persistir_documento_multifactura(uuid,text,text,text,jsonb,text[])")
    for funcion in rpc + internas:
        for rol in ("service_role", "anon", "authenticated"):
            esperado = "t" if funcion in rpc and rol == "service_role" else "f"
            assert pg.sql(f"select has_function_privilege('{rol}', '{funcion}', 'EXECUTE')") == esperado, (funcion, rol)
        assert pg.sql(f"select prosecdef::text || '|' || pg_get_userbyid(proowner) from pg_proc "
                      f"where oid = '{funcion}'::regprocedure") == "true|postgres"
    for tabla, columna in COLUMNAS_LZ4:
        assert pg.sql(f"select attcompression from pg_attribute where attrelid = 'public.{tabla}'::regclass "
                      f"and attname = '{columna}'") == "l", (tabla, columna)


# --------------------------------------------------------------------------- despliegue

def _cargar_despliegue(script=SCRIPT_28):
    spec = importlib.util.spec_from_file_location(f"desplegar_28_{uuid.uuid4().hex[:6]}", script)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_sql_de_precondiciones_28_es_de_solo_lectura(pg17_nueva_base):
    sql = _cargar_despliegue().PRECONDICIONES
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter ",
                                              "create ", "drop "))
    assert pg17_nueva_base("27").sql("begin read only; " + sql + "; rollback;") == "|".join(["t"] * 9)
    assert pg17_nueva_base("28").sql("begin read only; " + sql + "; rollback;").split("|")[0] == "f"


@pytest.fixture
def repo_corto():
    """Directorio corto: con el basetemp de la suite, la ruta de ``git show`` supera MAX_PATH en Windows."""
    import tempfile
    from pathlib import Path

    ruta = Path(tempfile.mkdtemp(prefix="cf2bm_"))
    yield ruta
    shutil.rmtree(ruta, ignore_errors=True)


def _repositorio_con_commit(destino) -> tuple[str, str, object]:
    """Copia byte a byte el script y la migracion a un repositorio git temporal con su commit."""
    for relativa in (RUTA_28, "pruebas/auditoria_2bm/desplegar_28.py"):
        (destino / relativa).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relativa, destino / relativa)
    git = ["git", "-C", str(destino), "-c", "user.name=ensayo", "-c", "user.email=ensayo@local",
           "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "ensayo 28"], check=True)
    commit = subprocess.run([*git, "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    sha = hashlib.sha256(MIGRACION_28.read_bytes().decode("utf-8").replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return commit, sha, _cargar_despliegue(destino / "pruebas/auditoria_2bm/desplegar_28.py")


def test_ensayo_completo_despliegue_28_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch, repo_corto):
    nombre, puerto, _plantilla_19 = contenedor_tcp
    pg = base_desde(nombre, pgl.construir_plantilla(nombre, "27"))
    _datos_previos(pg, tmp_path)
    referencia = base_desde(nombre, pg.db)
    referencia.sql(MIGRACION_28.read_text(encoding="utf-8"))
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)

    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    import dotenv
    import psycopg2

    real = getattr(psycopg2, "_connect_original_2az", psycopg2.connect)
    psycopg2._connect_original_2az = real
    dsns = []

    def conectar_local(dsn, **_kwargs):
        dsns.append(dsn)
        return real(host="127.0.0.1", port=puerto, dbname=pg.db, user="postgres", password="local-only",
                    connect_timeout=10)

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
    reservas = _reservas(pg)
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit)
    assert registro["precondiciones"] == [True] * 9
    assert registro["postcondiciones"] == {"datos_sin_cambios": True, "objetos_28": True, "privilegios": True}
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes and _reservas(pg) == reservas

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    # Ya aplicada: ni «28 ausente» ni «funciones y compresion de la 27»; el resto sigue en verde.
    assert registro["precondiciones"] == [False, True, False, True, True, True, True, True, True]
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes


def test_el_despliegue_rechaza_un_sql_distinto_del_commit(tmp_path, repo_corto):
    commit, sha, despliegue = _repositorio_con_commit(repo_corto)
    copia = repo_corto / RUTA_28
    copia.write_text(copia.read_text(encoding="utf-8") + "\n-- cambio\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="MIGRACION_28_NO_COINCIDE_CON_COMMIT"):
        despliegue.main(commit, sha, tmp_path / "x.json")
