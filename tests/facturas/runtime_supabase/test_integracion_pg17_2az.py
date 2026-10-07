"""Hito 2AZ: migracion 20 (R11 y R12) certificada en PostgreSQL 17 local, como service_role.

Plantillas (pg17_local): "19" = cadena 06-18 + rollback de la 19 (matriz y privilegios
por defecto productivos, 2AX) + 19; "20" = 19 + migracion 20 dos veces; "20_rollback".
Caso real: PDF del 2AO (fixture local excluido de git). El estado 2AO de 08007971 (sin
albaranes, vencimiento sin importe) se reproduce normalizando con la clasificacion
previa a R10 y sin R14 (parche en memoria solo durante la preparacion). Albaranes
operacionales de 08007971 con los valores reales de Supabase (volcado READ_ONLY del
2026-10-06). Sin produccion ni Farmatic.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
import time
import types
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

import pg17_local as pgl
from pg17_local import (
    FIXTURES, FLAGS_ESPERADOS, FLAGS_SQL, MIG, ROOT, _lit, _locks, _registrar, _worker, base_desde, esquema,
)
from test_ensayo_fase4_2at import _ClienteServiceRole, _ConexionPg17
from src.facturas.motor_local.adaptadores import alliance as al
from src.facturas.runtime_supabase.compositor_manual import construir_worker_enriquecimiento_manual
from src.facturas.runtime_supabase.conciliacion import ReglaTolerancia
from src.facturas.runtime_supabase.modelos import ConfiguracionRuntime
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion


pytestmark = pytest.mark.pg17_local

PDF_2AO = FIXTURES / "alliance_2ao_cinco_facturas.pdf"
MIGRACION_20 = MIG / "20_cf_alliance_tolerancia_enriquecimiento.sql"
ROLLBACK_20 = MIG / "20_cf_alliance_tolerancia_enriquecimiento.rollback.sql"
TIPOS_PREVIOS_R10 = frozenset({"NORMAL ACUSTICO", "NETOS PLUS", "PLATAFORMA 360", "COSTO LABORAT.", "ECOCEUTICS"})
# Valores reales de Supabase.albaranes para 08007971 (READ_ONLY, 2026-10-06).
ALBARANES_08007971 = (("Q039904/2026", "2026-06-23", "191.84", "313.29", 279694),
                      ("08M24229", "2026-06-23", "150.99", "270.70", 279774),
                      ("08M25574", "2026-06-25", "21.65", "35.37", 280053))


def _sr(pg, sentencia: str) -> str:
    salida = pg.sql(f"set role service_role; select current_user; {sentencia}").splitlines()
    assert salida[0] == "service_role"
    return "\n".join(salida[1:])


def _preparar_2ao(pg, tmp_path, *, estado_2ao: bool = True) -> tuple[_ClienteServiceRole, dict]:
    if not PDF_2AO.exists():
        pytest.skip("PDF real del 2AO ausente (excluido de git)")
    cliente = _ClienteServiceRole(pg)
    _registrar(pg, cliente, PDF_2AO.read_bytes(), 1)
    with pytest.MonkeyPatch.context() as mp:
        if estado_2ao:  # version anterior del extractor: sin R10 ni R14
            mp.setattr(al, "TIPOS_PEDIDO_MERCANCIA_ALLIANCE", TIPOS_PREVIOS_R10)
            mp.setattr(al.AdaptadorAlliance, "_total_factura_legible", lambda self, documento, pagina: None)
        assert _worker(cliente, tmp_path, "prep-2az").ejecutar_una_manual().documentos_reclamados == 1
    ids = {f["numero_factura"]: f["id"] for f in pg.json("select id::text, numero_factura from public.facturas "
                                                          "where proveedor_literal ilike 'ALLIANCE%'")}
    return cliente, ids


def _albaranes_operacionales_08007971(pg) -> None:
    for numero, fecha, puc, pvp, contador in ALBARANES_08007971:
        pg.sql("insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
               f"importe_pvp,importe_puc,descuento,estado) values ('PIO',{contador},'2','1.- SAFA',{_lit(numero)},"
               f"date {_lit(fecha)},{pvp},{puc},0,'PENDIENTE');")


def _solo_primera(pg, ids, numero) -> None:
    """Ordering: deja ``numero`` como n.o 1 desplazando la fecha de las demas Alliance."""
    otras = ",".join(_lit(v) for k, v in ids.items() if k != numero)
    pg.sql(f"update public.facturas set fecha_factura = date '2026-07-01' where id in ({otras});")


def _estado(pg, factura_id) -> dict:
    return pg.json(
        "select f.estado_conciliacion_cf, f.conciliacion_bloqueado_por, "
        "(select count(*) from public.facturas_albaranes_extraidos a where a.factura_id = f.id) as albaranes, "
        "(select json_agg(json_build_object('fecha', v.fecha_vencimiento, 'importe', v.importe::text)) "
        "   from public.facturas_vencimientos v where v.factura_id = f.id) as vencimientos, "
        "(select count(*) from public.historial_facturas h where h.factura_id = f.id "
        "   and h.evento = 'FACTURA_ENRIQUECIDA') as enriquecimientos, "
        "md5(to_jsonb(f)::text) as huella_factura "
        f"from public.facturas f where f.id = {_lit(factura_id)}")[0]


def _elegibilidad(pg, factura_id) -> str:
    return pg.sql(f"select estado || ':' || razon from public.cf_evaluar_elegibilidad_conciliacion({_lit(factura_id)}::uuid)")


def _huella(pg, consulta: str) -> str:
    return pg.sql(f"select md5(coalesce(string_agg(t::text, '|' order by t::text), '')) from ({consulta}) t;")


@pytest.fixture
def base20(pg17_nueva_base):
    return pg17_nueva_base("20")


# --------------------------------------------------------------------------- 08007971 real

def test_08007971_enriquecimiento_conciliacion_y_replay(base20, tmp_path):
    pg = base20
    cliente, ids = _preparar_2ao(pg, tmp_path)
    objetivo = ids["08007971"]
    antes = _estado(pg, objetivo)
    assert antes["albaranes"] == 0 and [v["importe"] for v in antes["vencimientos"]] == [None]
    assert _elegibilidad(pg, objetivo) == "NO_APTA:FALTAN_ALBARANES_MERCANCIA"
    otras = _huella(pg, f"select to_jsonb(a) from public.facturas_albaranes_extraidos a "
                        f"where factura_id <> {_lit(objetivo)}")

    worker = construir_worker_enriquecimiento_manual(cliente, ConfiguracionRuntime(), "enr-2az", tmp_path / "enr")
    resultado = worker.ejecutar(objetivo)

    assert (resultado["albaranes"], resultado["movimientos"], resultado["vencimientos"]) == (3, 0, 1)
    assert resultado["respuesta"]["replay"] is False
    despues = _estado(pg, objetivo)
    assert despues["albaranes"] == 3 and despues["enriquecimientos"] == 1
    assert [v["importe"] for v in despues["vencimientos"]] == ["364.4700"]
    assert despues["huella_factura"] == antes["huella_factura"]  # la fila de la factura no cambia
    assert _huella(pg, f"select to_jsonb(a) from public.facturas_albaranes_extraidos a "
                       f"where factura_id <> {_lit(objetivo)}") == otras
    filas = pg.json("select numero_albaran, importe_total::text, descripcion, orden, "
                    "provenance->'enriquecimiento'->>'worker_id' as worker from public.facturas_albaranes_extraidos "
                    f"where factura_id = {_lit(objetivo)} order by orden")
    assert [(f["numero_albaran"], f["importe_total"], f["descripcion"], f["worker"]) for f in filas] == [
        ("08C18299", "191.8400", "DIRECTO", "enr-2az"), ("08M24229", "150.9800", "DIRECTO", "enr-2az"),
        ("08M25574", "21.6500", "DIRECTO", "enr-2az")]
    assert _elegibilidad(pg, objetivo) == "APTA:APTA_MERCANCIA"

    # Replay: misma clave y mismo contenido -> sin ningun efecto.
    [(_, payload)] = [(n, p) for n, p in cliente.rpcs if n == "cf_enriquecer_factura"]
    total = _huella(pg, "select to_jsonb(h) from public.historial_facturas h")
    replay = RepositorioRuntimeSupabase(cliente).enriquecer_factura(
        objetivo, "enr-2az", payload["p_idempotency_key"], payload["p_enriquecimiento"])
    assert replay["replay"] is True
    assert _estado(pg, objetivo) == despues
    assert _huella(pg, "select to_jsonb(h) from public.historial_facturas h") == total
    # Misma clave con contenido distinto -> rechazo.
    with pytest.raises(RuntimeError, match="IDEMPOTENCY_KEY_REUTILIZADA"):
        RepositorioRuntimeSupabase(cliente).enriquecer_factura(
            objetivo, "enr-2az", payload["p_idempotency_key"], {**payload["p_enriquecimiento"], "x": 1})

    # Conciliacion manual (ruta oficial) con los albaranes reales de Supabase.
    _albaranes_operacionales_08007971(pg)
    _solo_primera(pg, ids, "08007971")
    assert construir_worker_conciliacion(RepositorioRuntimeSupabase(cliente), "conc-2az").ejecutar_una_manual() is True
    [c] = pg.json("select factura_id::text, disparador, resultado, importe_explicado::text, diferencia::text, "
                  "tolerancia::text, provenance->'tolerancia_regla' as regla from public.conciliaciones")
    assert (c["factura_id"], c["disparador"], c["resultado"]) == (objetivo, "MANUAL_ONE_SHOT", "CONCILIADA")
    assert (c["importe_explicado"], c["diferencia"], c["tolerancia"]) == ("364.4800", "-0.0100", "0.0500")
    assert c["regla"]["albaranes_casados"] == 3
    assert _locks(pg) == "0|0" and pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS

    # Tras conciliar, un enriquecimiento nuevo se rechaza (factura conciliada).
    with pytest.raises(RuntimeError, match="FACTURA_YA_CONCILIADA"):
        RepositorioRuntimeSupabase(cliente).enriquecer_factura(
            objetivo, "enr-2az", f"enriquecimiento:{objetivo}:otra", {**payload["p_enriquecimiento"], "x": 2})


@pytest.mark.parametrize("cambio,error", [
    ({"identidad": {"numero_factura": "08007999"}}, "IDENTIDAD_NO_COINCIDE:numero_factura"),
    ({"identidad": {"importe_total": "364.48"}}, "IDENTIDAD_NO_COINCIDE:importe_total"),
    ({"identidad": {"proveedor_cif": "B00000000"}}, "IDENTIDAD_NO_COINCIDE:proveedor_cif"),
    ({"archivo_hash": "0" * 64}, "SHA_NO_COINCIDE"),
    ({"documento_id": str(uuid.uuid4())}, "DOCUMENTO_NO_COINCIDE"),
])
def test_enriquecimiento_rechazado_si_cambia_identidad_documento_o_sha(base20, tmp_path, cambio, error):
    pg = base20
    cliente, ids = _preparar_2ao(pg, tmp_path)
    objetivo = ids["08007971"]
    payload = _payload_valido(cliente, objetivo, tmp_path)
    for clave, valor in cambio.items():
        payload[clave] = {**payload[clave], **valor} if isinstance(valor, dict) else valor
    antes = _estado(pg, objetivo)
    with pytest.raises(RuntimeError, match=error):
        RepositorioRuntimeSupabase(cliente).enriquecer_factura(objetivo, "enr", f"enriquecimiento:{objetivo}:k", payload)
    assert _estado(pg, objetivo) == antes


def _payload_valido(cliente, factura_id, tmp_path) -> dict:
    """Payload que construiria el worker, sin enviarlo (RPC interceptada)."""
    capturado = {}
    repo = RepositorioRuntimeSupabase(cliente)
    original = repo.enriquecer_factura
    worker = construir_worker_enriquecimiento_manual(cliente, ConfiguracionRuntime(), "enr", tmp_path / "p")
    worker.repositorio = types.SimpleNamespace(
        datos_para_enriquecer=repo.datos_para_enriquecer,
        enriquecer_factura=lambda f, w, k, p: capturado.update(payload=p) or {"replay": False})
    worker.ejecutar(factura_id)
    assert original  # el repositorio real no se usa para escribir
    return json.loads(json.dumps(capturado["payload"]))


def test_enriquecimiento_no_sobrescribe_importe_de_vencimiento_existente(base20, tmp_path):
    pg = base20
    cliente, ids = _preparar_2ao(pg, tmp_path)
    objetivo = ids["08007971"]
    payload = _payload_valido(cliente, objetivo, tmp_path)
    pg.sql(f"update public.facturas_vencimientos set importe = 364.47 where factura_id = {_lit(objetivo)};")
    antes = _estado(pg, objetivo)
    with pytest.raises(RuntimeError, match="VENCIMIENTO_CON_IMPORTE_EXISTENTE"):
        RepositorioRuntimeSupabase(cliente).enriquecer_factura(objetivo, "enr", f"enriquecimiento:{objetivo}:k", payload)
    assert _estado(pg, objetivo) == antes  # transaccion completa revertida: tampoco entran los albaranes


def test_enriquecimiento_solo_rellena_vencimientos_nulos(base20, tmp_path):
    pg = base20
    cliente, ids = _preparar_2ao(pg, tmp_path)
    objetivo = ids["08007970"]  # ya tenia sus 71 albaranes; solo falta el importe del vencimiento
    assert _estado(pg, objetivo)["albaranes"] == 71
    resultado = construir_worker_enriquecimiento_manual(cliente, ConfiguracionRuntime(), "enr", tmp_path / "v").ejecutar(
        objetivo)
    assert (resultado["albaranes"], resultado["vencimientos"]) == (0, 1)
    assert [v["importe"] for v in _estado(pg, objetivo)["vencimientos"]] == ["2356.6400"]


def test_enriquecimiento_rechaza_movimientos_en_factura_no_mixta_y_estado_revision(base20, tmp_path):
    pg = base20
    cliente, ids = _preparar_2ao(pg, tmp_path)
    objetivo = ids["08007971"]
    payload = _payload_valido(cliente, objetivo, tmp_path)
    movimiento = {"orden": 1, "tipo": "SERVICIO", "sentido": "CARGO",
                  "descripcion_literal": {"valor": "X", "literal": "X", "evidencia": []},
                  "importe": {"valor": "1.00", "literal": "1,00", "evidencia": []}}
    with pytest.raises(RuntimeError, match="MOVIMIENTOS_REQUIEREN_NATURALEZA_MIXTA"):
        RepositorioRuntimeSupabase(cliente).enriquecer_factura(
            objetivo, "enr", f"enriquecimiento:{objetivo}:m", {**payload, "movimientos": [movimiento]})
    pg.sql(f"update public.facturas set estado_conciliacion_cf = 'REVISION_CONCILIACION' where id = {_lit(objetivo)};")
    with pytest.raises(RuntimeError, match="FACTURA_EN_REVISION_CONCILIACION"):
        RepositorioRuntimeSupabase(cliente).enriquecer_factura(objetivo, "enr", f"enriquecimiento:{objetivo}:r", payload)


# --------------------------------------------------------------------------- R11

def _operacionales_sinteticos(pg, factura_id, desplazados: int, base_contador: int) -> None:
    """PUC = importe documental; ``desplazados`` albaranes con +0,01 (redondeo de centimo)."""
    pg.sql(
        "insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
        "importe_pvp,importe_puc,descuento,estado) "
        f"select 'PIO', {base_contador} + row_number() over (order by a.orden), '2', '1.- SAFA', a.numero_albaran, "
        "a.fecha_albaran, round(abs(a.importe_total) * 1.6, 2), "
        f"abs(a.importe_total) + case when row_number() over (order by a.orden) <= {desplazados} then 0.01 else 0 end, "
        f"0, 'PENDIENTE' from public.facturas_albaranes_extraidos a where a.factura_id = {_lit(factura_id)} "
        "on conflict do nothing;")


def test_r11_ruta_manual_y_automatica_registran_la_tolerancia(base20, tmp_path):
    pg = base20
    cliente, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    _operacionales_sinteticos(pg, ids["08007970"], 4, 950000)  # 71 albaranes, diferencia -0,08
    _operacionales_sinteticos(pg, ids["08007972"], 0, 960000)
    _solo_primera(pg, ids, "08007970")
    repo = RepositorioRuntimeSupabase(cliente)
    assert construir_worker_conciliacion(repo, "manual").ejecutar_una_manual() is True
    pg.sql(f"select public.cf_solicitar_reintento_conciliacion({_lit(ids['08007972'])}::uuid, 'test-2az');")
    assert construir_worker_conciliacion(repo, "auto").ejecutar_una() is True  # ruta automatica (reintento)
    filas = {c["factura_id"]: c for c in pg.json(
        "select factura_id::text, disparador, resultado, diferencia::text, tolerancia::text, "
        "provenance->'tolerancia_regla' as regla, "
        "(select count(*) from public.conciliacion_detalles d where d.conciliacion_id = c.id "
        "   and d.tipo_relacion = 'UNO_A_UNO') as casados from public.conciliaciones c")}
    manual, auto = filas[ids["08007970"]], filas[ids["08007972"]]
    assert (manual["disparador"], manual["resultado"], manual["diferencia"], manual["tolerancia"], manual["casados"]) == (
        "MANUAL_ONE_SHOT", "CONCILIADA", "-0.0800", "0.5000", 71)  # con T1 seria DIFERENCIA
    assert (auto["disparador"], auto["tolerancia"]) == ("AUTOMATICO", str(ReglaTolerancia().para(auto["casados"])))
    for c in (manual, auto):
        assert c["regla"] == {"suelo": 0.05, "por_albaran": 0.01, "tope": 0.5, "albaranes_casados": c["casados"],
                              "tolerancia": float(c["tolerancia"])}
    assert _locks(pg) == "0|0"


def test_r11_la_bd_rechaza_tolerancia_o_resultado_incoherente(base20, tmp_path):
    pg = base20
    _, ids = _preparar_2ao(pg, tmp_path, estado_2ao=False)
    _solo_primera(pg, ids, "08007970")
    objetivo = _sr(pg, "select id from public.cf_reclamar_factura_conciliacion_manual_one_shot('w', 300);")
    assert objetivo == ids["08007970"]
    detalles = [{"orden": i, "tipo_relacion": "UNO_A_UNO", "importe_aplicado": "1", "estado": "COINCIDE",
                 "albaran_farmacia": "PIO", "albaran_id_contador": 1000 + i} for i in range(1, 21)]

    def persistir(resultado):
        cuerpo = {"importe_factura": "20", "importe_explicado": "20", "detalles": detalles, **resultado}
        return _sr(pg, f"select public.cf_persistir_conciliacion({_lit(objetivo)}::uuid, 'w', 'MANUAL_ONE_SHOT', "
                       f"'clave-r11-{uuid.uuid4().hex}', {_lit(json.dumps(cuerpo))}::jsonb);")

    with pytest.raises(RuntimeError, match="TOLERANCIA_NO_COINCIDE_CON_R11"):
        persistir({"resultado": "CONCILIADA", "diferencia": "0", "tolerancia": "0.0500"})  # 20 casados -> 0,20
    with pytest.raises(RuntimeError, match="RESULTADO_INCOHERENTE_CON_TOLERANCIA"):
        persistir({"resultado": "CONCILIADA", "diferencia": "0.30", "tolerancia": "0.2000"})
    with pytest.raises(RuntimeError, match="TOLERANCIA_REGLA_NO_COINCIDE"):
        persistir({"resultado": "CONCILIADA", "diferencia": "0.10", "tolerancia": "0.2000",
                   "tolerancia_regla": {"suelo": "0.05", "por_albaran": "0.02", "tope": "0.5", "albaranes_casados": 20}})
    assert pg.sql("select count(*) from public.conciliaciones") == "0"


# --------------------------------------------------------------------------- datos existentes, rollback, privilegios

def _datos_previos(pg, tmp_path):
    cliente, ids = _preparar_2ao(pg, tmp_path)
    facturas = list(ids.values())
    # 13 conciliaciones preexistentes (como en produccion), con detalles.
    pg.sql("insert into public.conciliaciones (factura_id,intento,disparador,estado,es_actual,importe_factura,"
           "importe_explicado,diferencia,resultado,worker_id,finalizado_at) "
           "select f, i, 'MANUAL', 'COMPLETADA', i = case when f = " + _lit(facturas[0]) + " then 5 else 2 end, "
           "1, 1, 0, 'CONCILIADA', 'previo-2az', now() from unnest(array[" + ",".join(_lit(f) for f in facturas) +
           "]::uuid[]) f cross join generate_series(1, 5) i where i <= case when f = " + _lit(facturas[0]) +
           " then 5 else 2 end;")
    pg.sql("insert into public.conciliacion_detalles (conciliacion_id,orden,factura_albaran_extraido_id,tipo_relacion,"
           "importe_aplicado,estado) select c.id, 1, (select a.id from public.facturas_albaranes_extraidos a "
           "where a.factura_id = c.factura_id order by a.id limit 1), 'SIN_COINCIDENCIA', 0, 'DIFERENCIA' "
           "from public.conciliaciones c;")
    assert pg.sql("select count(*) from public.conciliaciones") == "13"
    return cliente, ids


CONSULTAS_HUELLA = {
    "facturas": "select to_jsonb(f) from public.facturas f",
    "conciliaciones": "select to_jsonb(c) from public.conciliaciones c",
    "detalles": "select to_jsonb(d) from public.conciliacion_detalles d",
    "albaranes_extraidos": "select to_jsonb(a) from public.facturas_albaranes_extraidos a",
    "movimientos": "select to_jsonb(m) from public.facturas_movimientos m",
    "vencimientos": "select to_jsonb(v) from public.facturas_vencimientos v",
    "albaranes": "select to_jsonb(a) from public.albaranes a",
    "historial": "select to_jsonb(h) from public.historial_facturas h",
}


def test_20_no_altera_facturas_ni_conciliaciones_existentes(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("19")
    _datos_previos(pg, tmp_path)
    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    config = _huella(pg, "select to_jsonb(c) from public.cf_configuracion c")
    pg.sql(MIGRACION_20.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_20.read_text(encoding="utf-8"))
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes
    assert _huella(pg, "select to_jsonb(c) - 'conciliacion_tolerancia_suelo' - 'conciliacion_tolerancia_por_albaran' "
                       "- 'conciliacion_tolerancia_tope' from public.cf_configuracion c") == config
    assert pg.sql("select conciliacion_tolerancia_suelo, conciliacion_tolerancia_por_albaran, "
                  "conciliacion_tolerancia_tope from public.cf_configuracion") == "0.0500|0.0100|0.5000"
    assert pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS
    with pytest.raises(RuntimeError, match="cf_configuracion_tolerancia_r11_check"):
        pg.sql("update public.cf_configuracion set conciliacion_tolerancia_tope = 2 where id;")


def test_rollback_20_devuelve_exactamente_el_esquema_19(pg17_nueva_base):
    assert esquema(pg17_nueva_base("20_rollback")) == esquema(pg17_nueva_base("19"))
    assert esquema(pg17_nueva_base("20")) != esquema(pg17_nueva_base("19"))


def test_privilegios_de_la_20(base20):
    filas = {f["f"]: f for f in base20.json(
        "select p.proname as f, p.prosecdef as definer, pg_get_userbyid(p.proowner) as owner, "
        "exists(select 1 from aclexplode(p.proacl) a where a.grantee = 0) as public, "
        "has_function_privilege('anon', p.oid, 'EXECUTE') as anon, "
        "has_function_privilege('authenticated', p.oid, 'EXECUTE') as authenticated, "
        "has_function_privilege('service_role', p.oid, 'EXECUTE') as service_role "
        "from pg_proc p where p.pronamespace = 'public'::regnamespace "
        "and p.proname in ('cf_enriquecer_factura', 'cf_persistir_conciliacion')")}
    for nombre in ("cf_enriquecer_factura", "cf_persistir_conciliacion"):
        f = filas[nombre]
        assert (f["definer"], f["owner"], f["public"], f["anon"], f["authenticated"], f["service_role"]) == (
            True, "postgres", False, False, False, True), nombre
    for rol in ("anon", "authenticated"):
        with pytest.raises(RuntimeError, match="permission denied"):
            base20.sql(f"set role {rol}; select public.cf_enriquecer_factura(gen_random_uuid(), 'x', 'y', '{{}}'::jsonb);")


# --------------------------------------------------------------------------- ensayo del script de enriquecimiento

def test_ensayo_completo_script_enriquecimiento(base20, tmp_path, monkeypatch):
    pg = base20
    cliente, ids = _preparar_2ao(pg, tmp_path)
    objetivo = ids["08007971"]
    sys.path.insert(0, str(ROOT / "pruebas/auditoria_2az"))
    sys.path.insert(0, str(ROOT / "pruebas/auditoria_2at"))
    import auditoria_readonly as ar
    import enriquecer_una_vez as eu

    tareas = {"tareas": [{"nombre": n, "estado": "Ready", "proxima": None, "ultima": None, "resultado": 0}
                         for n in ar.TAREAS_ESPERADAS]}
    monkeypatch.setattr(ar, "_conectar", lambda: (ar.PROJECT_REF, _ConexionPg17(pg, [])))
    monkeypatch.setattr(eu, "_tareas", lambda: tareas)
    monkeypatch.setattr("dotenv.dotenv_values", lambda *_a, **_k: {
        "SUPABASE_URL": f"https://{ar.PROJECT_REF}.supabase.co", "SUPABASE_KEY": "sb_secret_ensayo_local"})
    modulo = types.ModuleType("src.supabase_client.conexion_supabase")
    modulo.obtener_cliente_supabase = lambda: cliente
    monkeypatch.setitem(sys.modules, "src.supabase_client.conexion_supabase", modulo)
    evidencias = tmp_path / "evidencias_2az"
    evidencias.mkdir()

    codigo = eu.main(objetivo, evidencias / "enriquecimiento.json", tmp_path / "tmp_enr")
    registro = json.loads((evidencias / "enriquecimiento.json").read_text(encoding="utf-8"))
    assert codigo == 0 and (registro["resultado"], registro["invocaciones"]) == ("RETORNO", 1)
    assert registro["revalidacion"]["ok"] is True
    assert (registro["retorno"]["albaranes"], registro["retorno"]["vencimientos"]) == (3, 1)
    assert registro["estado_posterior_readonly"]["factura"]["albaranes"] == 3
    assert registro["estado_posterior_readonly"]["factura"]["vencimientos_sin_importe"] == 0
    assert (evidencias / f"enriquecimiento_unico_{objetivo}.guard").exists()
    assert registro["directorio_temporal_borrado"] is True

    with pytest.raises(SystemExit, match="GUARD_EXISTENTE"):
        eu.main(objetivo, evidencias / "segunda.json", tmp_path / "tmp_enr2")
    assert _estado(pg, objetivo)["enriquecimientos"] == 1


# --------------------------------------------------------------------------- ensayo del script de despliegue de la 20

SCRIPT_20 = ROOT / "pruebas/auditoria_2az/desplegar_20.py"
DSN_FICTICIO = "postgresql://sin-credenciales@db.vklaiuytvegkelgyspxc.supabase.co:5432/postgres"


def _commit_de_la_20() -> tuple[str, str]:
    commit = subprocess.run(["git", "-C", str(ROOT), "log", "-n", "1", "--format=%H", "--",
                             "sql/migrations/20_cf_alliance_tolerancia_enriquecimiento.sql"],
                            capture_output=True, text=True).stdout.strip()
    if not commit:
        pytest.skip("migracion 20 sin commit: el ensayo del despliegue exige verificar el SHA contra un commit")
    import hashlib
    local = MIGRACION_20.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return commit, hashlib.sha256(local.encode("utf-8")).hexdigest()


def _cargar_script():
    spec = importlib.util.spec_from_file_location(f"desplegar_20_{uuid.uuid4().hex[:6]}", SCRIPT_20)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _sql_precondiciones() -> str:
    arbol = ast.parse(SCRIPT_20.read_text(encoding="utf-8"))
    [consulta] = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute"
                  and n.args and "has_table_privilege" in ast.unparse(n.args[0])]
    return eval(compile(ast.Expression(consulta.args[0]), str(SCRIPT_20), "eval"), vars(_cargar_script()))


@pytest.fixture(scope="module")
def contenedor_tcp():
    if pgl._docker("image", "inspect", pgl.IMAGEN, comprobar=False).returncode:
        pytest.skip("imagen local no disponible")
    nombre = "cf-pg17-ensayo2az-" + uuid.uuid4().hex[:8]
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
        puerto = int(pgl._docker("port", nombre, "5432/tcp").stdout.strip().rsplit(":", 1)[1])
        yield nombre, puerto, pgl.construir_plantilla(nombre, "19")
    finally:
        pgl._docker("rm", "-f", nombre, comprobar=False)


def test_ensayo_completo_despliegue_20_y_segundo_intento_revierte(contenedor_tcp, tmp_path, monkeypatch):
    commit, sha = _commit_de_la_20()
    nombre, puerto, plantilla = contenedor_tcp
    pg = base_desde(nombre, plantilla)
    _datos_previos(pg, tmp_path)
    referencia = base_desde(nombre, pg.db)
    referencia.sql(MIGRACION_20.read_text(encoding="utf-8"))
    assert pg.sql("begin read only; " + _sql_precondiciones() + "; rollback;") == "|".join(["t"] * 9)

    sys.path.insert(0, str(ROOT / "tmp_pg_probe_deps"))
    import psycopg2

    real = getattr(psycopg2, "_connect_original_2az", psycopg2.connect)
    psycopg2._connect_original_2az = real
    dsns = []

    def conectar_local(dsn, **_kwargs):
        dsns.append(dsn)
        return real(host="127.0.0.1", port=puerto, dbname=pg.db, user="postgres", password="local-only",
                    connect_timeout=10)

    monkeypatch.setattr(psycopg2, "connect", conectar_local)
    monkeypatch.setenv("CONTROLFARMACIAS_SUPABASE_DB_URL", DSN_FICTICIO)

    def ejecutar(salida):
        try:
            _cargar_script().main(commit, sha, salida)
        except SystemExit:
            pass
        return json.loads(salida.read_text(encoding="utf-8"))

    antes = {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()}
    registro = ejecutar(tmp_path / "primero.json")
    assert dsns == [DSN_FICTICIO]
    assert (registro["resultado"], registro["sha256_lf"], registro["commit"]) == ("APLICADA", sha, commit)
    assert registro["precondiciones"] == [True] * 9
    assert esquema(pg) == esquema(referencia)
    assert {k: _huella(pg, q) for k, q in CONSULTAS_HUELLA.items()} == antes

    registro = ejecutar(tmp_path / "segundo.json")
    assert registro["resultado"] == "REVERTIDA" and "PRECONDICIONES_NO_CUMPLIDAS" in registro["error"]
    assert registro["precondiciones"][:2] == [False, False] and all(registro["precondiciones"][2:])
    assert esquema(pg) == esquema(referencia)


def test_sql_de_precondiciones_20_es_de_solo_lectura():
    sql = _sql_precondiciones()
    assert sql.lstrip().lower().startswith("select ")
    assert not any(p in sql.lower() for p in ("insert ", "update ", "delete ", "grant ", "revoke ", "alter "))
