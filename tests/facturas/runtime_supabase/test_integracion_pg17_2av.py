"""Hito 2AV: migracion 18 certificada en PostgreSQL 17 local (casos 4.1-4.14).

Base: cadena 06-17 (plantilla ``17``), privilegios por defecto de Supabase
emulados y migracion 18 aplicada dos veces. Las RPC se ejecutan COMO
service_role (``ClientePg17`` hace ``set role service_role``). Sin produccion.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from pg17_local import (
    ALLIANCE, FIXTURES, FLAGS_ESPERADOS, FLAGS_SQL, MIGRACION_18, ROLLBACK_18, ClientePg17,
    _lit, _locks, _registrar, _worker, base_desde, esquema,
)
from simulador_conciliacion_2av import SupabaseConciliacionMemoria
from src.facturas.runtime_supabase.conciliacion import conciliar_importes
from src.facturas.runtime_supabase.modelos import FacturaTrabajo
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_conciliacion import construir_worker_conciliacion


pytestmark = pytest.mark.pg17_local

ALLIANCE_2AO = FIXTURES / "alliance_2ao_cinco_facturas.pdf"
FUNCIONES_18 = {
    "cf_reclamar_factura_conciliacion_nucleo(text,integer,text)": False,
    "cf_reclamar_factura_conciliacion(text,integer)": True,
    "cf_reclamar_factura_conciliacion_manual_one_shot(text,integer)": True,
    "cf_persistir_conciliacion(uuid,text,text,text,jsonb)": True,
    "cf_registrar_fallo_conciliacion(uuid,text,text,text,text,text)": True,
}
EMULAR_DEFAULT_ACL = ("alter default privileges for role postgres in schema public "
                      "grant execute on functions to anon, authenticated, service_role;")


def _aplicar_18(pg):
    pg.sql(EMULAR_DEFAULT_ACL)
    pg.sql(MIGRACION_18.read_text(encoding="utf-8"))
    pg.sql(MIGRACION_18.read_text(encoding="utf-8"))
    return pg


@pytest.fixture
def base(pg17_nueva_base):
    return _aplicar_18(pg17_nueva_base("17"))


def _normalizar(pg, tmp_path, pdf: Path = ALLIANCE, nombre="n") -> ClientePg17:
    cliente = ClientePg17(pg)
    _registrar(pg, cliente, pdf.read_bytes(), 1)
    assert _worker(cliente, tmp_path, nombre).ejecutar_una_manual().documentos_reclamados == 1
    return cliente


def _albaranes(pg, variantes=("2",), numeros: list[str] | None = None) -> None:
    """Albaranes operacionales SINTETICOS: numero, fecha y PUC copiados de los extraidos."""
    filtro = f"and f.numero_factura = any(array[{','.join(_lit(n) for n in numeros)}])" if numeros else ""
    casos = " ".join(f"when {i} then {_lit(v)}" for i, v in enumerate(variantes))
    pg.sql(
        "insert into public.albaranes (farmacia,id_contador,id_proveedor,proveedor,numero_albaran,fecha,"
        "importe_pvp,importe_puc,descuento,estado) "
        f"select 'PIO', 900000 + row_number() over (order by a.id), "
        # Variantes repartidas dentro de cada factura: toda factura con >=3 albaranes las recibe todas.
        f"case (row_number() over (partition by a.factura_id order by a.orden, a.id) % {len(variantes)}) "
        f"{casos} end, "
        "'1.- SAFA', a.numero_albaran, a.fecha_albaran, round(abs(a.importe_total) * 1.6, 2), "
        "abs(a.importe_total), 0, 'PENDIENTE' "
        "from public.facturas_albaranes_extraidos a join public.facturas f on f.id = a.factura_id "
        f"where f.proveedor_literal ilike 'ALLIANCE%' {filtro} on conflict do nothing;")


SELECTOR_LECTURA = (
    "select f.id from public.facturas f cross join public.cf_configuracion c "
    "cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e "
    "where c.id = true and f.farmacia = any(c.farmacias_habilitadas) "
    "and f.estado_conciliacion_cf = 'PENDIENTE_CONCILIAR' and e.estado = 'APTA' "
    "and coalesce(f.conciliacion_proximo_at,'-infinity'::timestamptz) <= now() "
    "and coalesce(f.conciliacion_bloqueado_hasta,'-infinity'::timestamptz) <= now() "
    "order by (f.conciliacion_reintento_solicitado_at is not null) desc, f.fecha_factura nulls last, f.id")


def _orden_oficial(pg) -> list[str]:
    """Reproduce READ_ONLY el ordering oficial (modo MANUAL_ONE_SHOT, sin claim)."""
    return [f["id"] for f in pg.json(SELECTOR_LECTURA)]


def _conc(cliente: ClientePg17, nombre: str):
    return construir_worker_conciliacion(RepositorioRuntimeSupabase(cliente), f"conc-{nombre}")


def _sr(pg, sentencia: str) -> str:
    salida = pg.sql(f"set role service_role; select current_user; {sentencia}").splitlines()
    assert salida[0] == "service_role"
    return "\n".join(salida[1:])


def _claim_manual(pg, worker: str) -> str | None:
    fila = _sr(pg, f"select id from public.cf_reclamar_factura_conciliacion_manual_one_shot({_lit(worker)}, 300);")
    return fila or None


def _factura(pg, factura_id: str) -> dict:
    return pg.json(
        "select estado_conciliacion_cf, conciliacion_bloqueado_por, conciliacion_bloqueado_hasta, "
        "conciliacion_intentos, conciliacion_intentos_fallo, conciliacion_ultima_clase_fallo, "
        "conciliacion_proximo_at, conciliacion_reintento_solicitado_at, conciliacion_ultimo_error, "
        "round(extract(epoch from conciliacion_proximo_at - updated_at) / 3600)::int as backoff_horas "
        f"from public.facturas where id = {_lit(factura_id)}")[0]


def _conciliaciones(pg, factura_id: str | None = None) -> list[dict]:
    filtro = f"where factura_id = {_lit(factura_id)}" if factura_id else ""
    return pg.json(
        "select id::text, factura_id::text, intento, disparador, estado, es_actual, resultado, "
        "importe_factura::text, importe_explicado::text, diferencia::text, worker_id, idempotency_key, "
        "provenance->>'modo_ejecucion' as modo, "
        "(select count(*) from public.conciliacion_detalles d where d.conciliacion_id = c.id) as detalles "
        f"from public.conciliaciones c {filtro} order by created_at, intento")


def _eventos(pg, evento: str, factura_id: str | None = None) -> list[dict]:
    filtro = f"and factura_id = {_lit(factura_id)}" if factura_id else ""
    return pg.json(f"select actor, detalle from public.historial_facturas where evento = {_lit(evento)} {filtro} order by id")


def _huella(pg, consulta: str) -> str:
    return pg.sql(f"select md5(coalesce(string_agg(t::text, '|' order by t::text), '')) from ({consulta}) t;")


# --------------------------------------------------------------------------
# 4.1 - 4.3
# --------------------------------------------------------------------------

def test_4_1_manual_con_flag_apagado_reclama_el_numero_1(base, tmp_path):
    cliente = _normalizar(base, tmp_path)
    _albaranes(base)
    orden = _orden_oficial(base)
    assert len(orden) == 3
    assert base.sql("select count(*) from public.facturas where conciliacion_reintento_solicitado_at is not null") == "0"
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS

    assert _conc(cliente, "a").ejecutar_una_manual() is True

    [c] = _conciliaciones(base)
    assert c["factura_id"] == orden[0]
    assert (c["disparador"], c["modo"], c["estado"], c["es_actual"]) == ("MANUAL_ONE_SHOT", "MANUAL_ONE_SHOT", "COMPLETADA", True)
    assert c["idempotency_key"].startswith(f"conciliacion:{orden[0]}:MANUAL_ONE_SHOT:")
    assert c["resultado"] == "CONCILIADA" and c["detalles"] > 0
    assert [e["detalle"]["modo_ejecucion"] for e in _eventos(base, "CONCILIACION_CLAIM")] == ["MANUAL_ONE_SHOT"]
    assert len(_eventos(base, "CONCILIACION_PERSISTIDA", orden[0])) == 1
    f = _factura(base, orden[0])
    assert f["estado_conciliacion_cf"] == "CONCILIADA" and f["conciliacion_bloqueado_por"] is None
    assert _locks(base) == "0|0" and base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def _claims(pg, n: int, rpc: str) -> list[str]:
    return [_sr(pg, f"select id from public.{rpc}('orden-{i}', 300);") for i in range(n)]


def test_4_2_ordering_identico_manual_automatico_y_previo(base, tmp_path, pg17_contenedor):
    _normalizar(base, tmp_path)
    _albaranes(base)
    esperado = _orden_oficial(base)
    automatica = base_desde(pg17_contenedor, base.db)
    previa = base_desde(pg17_contenedor, base.db)

    manual = _claims(base, 3, "cf_reclamar_factura_conciliacion_manual_one_shot")

    automatica.sql("update public.cf_configuracion set conciliacion_automatica = true where id;")
    auto = _claims(automatica, 3, "cf_reclamar_factura_conciliacion")

    previa.sql(ROLLBACK_18.read_text(encoding="utf-8"))  # claim literal de la migracion 14
    previa.sql("update public.cf_configuracion set conciliacion_automatica = true where id;")
    migracion_14 = _claims(previa, 3, "cf_reclamar_factura_conciliacion")

    assert manual == auto == migracion_14 == esperado
    assert _claims(base, 1, "cf_reclamar_factura_conciliacion_manual_one_shot") == [""]


def test_4_3_maximo_una_factura_y_numero_2_intacto(base, tmp_path):
    cliente = _normalizar(base, tmp_path)
    _albaranes(base)
    orden = _orden_oficial(base)
    resto = f"select to_jsonb(f) from public.facturas f where id <> {_lit(orden[0])}"
    antes = _huella(base, resto)

    resultado = _conc(cliente, "a").ejecutar_una_manual()

    assert resultado is True
    assert [c["factura_id"] for c in _conciliaciones(base)] == [orden[0]]
    assert _huella(base, resto) == antes
    assert len(_eventos(base, "CONCILIACION_CLAIM")) == 1
    assert _orden_oficial(base) == orden[1:]
    assert _locks(base) == "0|0"


# --------------------------------------------------------------------------
# 4.4 Cierre atomico con fallo inyectado en cada escritura
# --------------------------------------------------------------------------

INYECCIONES = {
    "es_actual": ("conciliaciones", "before update", "true"),
    "cabecera": ("conciliaciones", "before insert", "true"),
    "detalles": ("conciliacion_detalles", "before insert", "true"),
    "factura": ("facturas", "before update",
                "new.conciliacion_intentos is distinct from old.conciliacion_intentos"),
    "historial": ("historial_facturas", "before insert", "new.evento = 'CONCILIACION_PERSISTIDA'"),
}


@pytest.mark.parametrize("escritura", sorted(INYECCIONES))
def test_4_4_fallo_inyectado_no_persiste_nada_y_libera_el_lock(base, tmp_path, escritura):
    cliente = _normalizar(base, tmp_path)
    _albaranes(base)
    objetivo = _orden_oficial(base)[0]
    if escritura == "es_actual":
        # Conciliacion previa y evidencia distinta: el cierre debe desmarcar es_actual.
        assert _conc(cliente, "previa").ejecutar_una_manual() is True
        base.sql(
            "update public.albaranes set importe_puc = importe_puc + 0.01 where id_contador = "
            "(select min(al.id_contador) from public.albaranes al join public.facturas_albaranes_extraidos a "
            f"on a.numero_albaran = al.numero_albaran where a.factura_id = {_lit(objetivo)});"
            f"select public.cf_solicitar_reintento_conciliacion({_lit(objetivo)}::uuid, 'test-2av');")
    tabla, momento, condicion = INYECCIONES[escritura]
    base.sql(
        "create function public._test_fallo_2av() returns trigger language plpgsql as $$ "
        f"begin if {condicion} then raise exception 'FALLO_INYECTADO_{escritura.upper()}'; end if; "
        "return new; end $$;"
        f"create trigger _test_fallo_2av {momento} on public.{tabla} "
        "for each row execute function public._test_fallo_2av();")
    conciliaciones = _huella(base, "select to_jsonb(c) from public.conciliaciones c")
    detalles = _huella(base, "select to_jsonb(d) from public.conciliacion_detalles d")
    persistidas = len(_eventos(base, "CONCILIACION_PERSISTIDA"))

    assert _conc(cliente, "a").ejecutar_una_manual() is False

    assert _huella(base, "select to_jsonb(c) from public.conciliaciones c") == conciliaciones
    assert _huella(base, "select to_jsonb(d) from public.conciliacion_detalles d") == detalles
    assert len(_eventos(base, "CONCILIACION_PERSISTIDA")) == persistidas
    f = _factura(base, objetivo)
    assert f["conciliacion_bloqueado_por"] is None and f["conciliacion_bloqueado_hasta"] is None
    assert f["estado_conciliacion_cf"] == "PENDIENTE_CONCILIAR"
    assert f["conciliacion_intentos_fallo"] == 1 and f["backoff_horas"] == 1
    assert f"FALLO_INYECTADO_{escritura.upper()}" in f["conciliacion_ultimo_error"]
    assert f["conciliacion_ultima_clase_fallo"] == "TRANSITORIO"
    assert len(_eventos(base, "CONCILIACION_ERROR", objetivo)) == 1
    assert _locks(base) == "0|0"


# --------------------------------------------------------------------------
# 4.5 Replay idempotente, 4.6 lock caducado
# --------------------------------------------------------------------------

def test_4_5_replay_idempotente(base, tmp_path):
    cliente = _normalizar(base, tmp_path)
    _albaranes(base)
    objetivo = _orden_oficial(base)[0]
    assert _conc(cliente, "a").ejecutar_una_manual() is True
    [original] = _conciliaciones(base, objetivo)
    [payload] = [p for n, p in cliente.rpcs if n == "cf_persistir_conciliacion"]
    base.sql(f"select public.cf_solicitar_reintento_conciliacion({_lit(objetivo)}::uuid, 'test-2av');")

    assert _conc(cliente, "b").ejecutar_una_manual() is True  # misma evidencia -> misma clave

    assert _conciliaciones(base, objetivo) == [original]
    f = _factura(base, objetivo)
    assert f["estado_conciliacion_cf"] == "CONCILIADA"
    assert f["conciliacion_bloqueado_por"] is None and f["conciliacion_reintento_solicitado_at"] is None
    replay = _eventos(base, "CONCILIACION_REPLAY_IDEMPOTENTE", objetivo)
    assert [(e["actor"], e["detalle"]["claim_liberado"]) for e in replay] == [("conc-b", True)]
    assert _locks(base) == "0|0"

    # Retransmision sin claim: devuelve la original y no cambia nada.
    antes = _huella(base, "select to_jsonb(f) from public.facturas f")
    retransmitida = _sr(base, (
        f"select public.cf_persistir_conciliacion({_lit(objetivo)}::uuid, 'intruso', 'MANUAL_ONE_SHOT', "
        f"{_lit(payload['p_idempotency_key'])}, "
        f"{_lit(json.dumps(payload['p_resultado'], ensure_ascii=False))}::jsonb);"))
    assert retransmitida == original["id"]
    assert _huella(base, "select to_jsonb(f) from public.facturas f") == antes
    assert _eventos(base, "CONCILIACION_REPLAY_IDEMPOTENTE", objetivo)[-1]["detalle"]["claim_liberado"] is False
    assert len(_conciliaciones(base)) == 1


def test_4_6_lock_caducado_vuelve_a_ser_elegible(base, tmp_path):
    cliente = _normalizar(base, tmp_path)
    _albaranes(base)
    orden = _orden_oficial(base)
    assert _claim_manual(base, "muerto") == orden[0]
    assert _orden_oficial(base) == orden[1:]  # lock vigente: excluida

    base.sql("update public.facturas set conciliacion_bloqueado_hasta = now() - interval '1 second' "
             f"where id = {_lit(orden[0])};")
    assert _orden_oficial(base)[0] == orden[0]

    assert _conc(cliente, "vivo").ejecutar_una_manual() is True
    [c] = _conciliaciones(base, orden[0])
    assert c["worker_id"] == "conc-vivo" and _locks(base) == "0|0"
    with pytest.raises(RuntimeError, match="claim no pertenece al worker"):
        _sr(base, (f"select public.cf_persistir_conciliacion({_lit(orden[0])}::uuid, 'muerto', "
                   "'MANUAL_ONE_SHOT', 'otra-clave', "
                   "'{\"resultado\":\"CONCILIADA\",\"detalles\":[]}'::jsonb);"))


# --------------------------------------------------------------------------
# 4.7 Backoff R7
# --------------------------------------------------------------------------

def _fallo(pg, factura_id: str, worker: str) -> str:
    return _sr(pg, (f"select public.cf_registrar_fallo_conciliacion({_lit(factura_id)}::uuid, {_lit(worker)}, "
                    "'MANUAL_ONE_SHOT', 'RuntimeError', 'timeout', 'TRANSITORIO');"))


def _vencer_backoff(pg, factura_id: str) -> None:
    pg.sql("update public.facturas set conciliacion_proximo_at = now() - interval '1 second' "
           f"where id = {_lit(factura_id)};")


def test_4_7_backoff_revision_y_reintento(base, tmp_path):
    cliente = _normalizar(base, tmp_path)
    _albaranes(base)
    orden = _orden_oficial(base)
    f = orden[0]
    assert _fallo(base, f, "sin-claim") == "f"

    for intento, horas in ((1, 1), (2, 6), (3, 24)):
        assert _claim_manual(base, "w") == f
        assert _fallo(base, f, "w") == "t"
        estado = _factura(base, f)
        assert (estado["estado_conciliacion_cf"], estado["conciliacion_intentos_fallo"], estado["backoff_horas"]) == (
            "PENDIENTE_CONCILIAR", intento, horas)
        assert estado["conciliacion_bloqueado_por"] is None
        assert f not in _orden_oficial(base)  # backoff futuro: no reclamable
        _vencer_backoff(base, f)

    assert _claim_manual(base, "w") == f
    assert _fallo(base, f, "w") == "t"
    estado = _factura(base, f)
    assert (estado["estado_conciliacion_cf"], estado["conciliacion_intentos_fallo"]) == ("REVISION_CONCILIACION", 4)
    assert estado["conciliacion_proximo_at"] is None
    assert f not in _orden_oficial(base)
    assert _claim_manual(base, "w2") == orden[1]
    base.sql(f"update public.facturas set conciliacion_bloqueado_por = null, conciliacion_bloqueado_hasta = null "
             f"where id = {_lit(orden[1])};")

    # Reintento solicitado: vuelve a la cola y reinicia el presupuesto de fallos.
    base.sql(f"select public.cf_solicitar_reintento_conciliacion({_lit(f)}::uuid, 'test-2av');")
    assert _claim_manual(base, "w") == f
    assert _fallo(base, f, "w") == "t"
    estado = _factura(base, f)
    assert (estado["estado_conciliacion_cf"], estado["conciliacion_intentos_fallo"], estado["backoff_horas"]) == (
        "PENDIENTE_CONCILIAR", 1, 1)

    # Un exito reinicia el contador.
    base.sql(f"select public.cf_solicitar_reintento_conciliacion({_lit(f)}::uuid, 'test-2av');")
    assert _conc(cliente, "ok").ejecutar_una_manual() is True
    estado = _factura(base, f)
    assert (estado["estado_conciliacion_cf"], estado["conciliacion_intentos_fallo"]) == ("CONCILIADA", 0)
    assert estado["conciliacion_ultima_clase_fallo"] is None and estado["conciliacion_proximo_at"] is None
    assert len(_eventos(base, "CONCILIACION_ERROR", f)) == 5


# --------------------------------------------------------------------------
# 4.8 R9, 4.9 ruta automatica
# --------------------------------------------------------------------------

def test_4_8_r9_variantes_de_id_proveedor_casan_igual(base, tmp_path):
    cliente = _normalizar(base, tmp_path)
    _albaranes(base, variantes=("2", "0002", "0002 "))
    base.sql(
        "update public.proveedores set farmatic_id_proveedor = '0002' where codigo = 'PROV-STG';"
        "update public.facturas set proveedor_id = (select id from public.proveedores where codigo = 'PROV-STG') "
        "where proveedor_literal ilike 'ALLIANCE%';")
    objetivo = _orden_oficial(base)[0]

    assert _conc(cliente, "r9").ejecutar_una_manual() is True

    [c] = _conciliaciones(base, objetivo)
    extraidos = int(base.sql(f"select count(*) from public.facturas_albaranes_extraidos where factura_id = {_lit(objetivo)}"))
    # Solo los detalles de albaran (una MIXTA anade movimientos de servicio sin proveedor).
    detalles = base.json(
        "select tipo_relacion, provenance->>'id_proveedor' as id_proveedor from public.conciliacion_detalles "
        f"where conciliacion_id = {_lit(c['id'])} and factura_albaran_extraido_id is not null")
    assert c["resultado"] == "CONCILIADA"
    assert len(detalles) == extraidos and {d["tipo_relacion"] for d in detalles} == {"UNO_A_UNO"}
    assert {d["id_proveedor"] for d in detalles} == {"2", "0002", "0002 "}
    assert base.sql("select string_agg(distinct id_proveedor, '|' order by id_proveedor) from public.albaranes "
                    "where id_contador >= 900000") == "0002|0002 |2"  # literales intactos


def test_4_9_ruta_automatica_sin_cambios(base, tmp_path):
    cliente = _normalizar(base, tmp_path)
    _albaranes(base)
    orden = _orden_oficial(base)

    assert _conc(cliente, "auto-off").ejecutar_una() is False
    assert _eventos(base, "CONCILIACION_CLAIM") == [] and _conciliaciones(base) == []

    base.sql(f"select public.cf_solicitar_reintento_conciliacion({_lit(orden[1])}::uuid, 'test-2av');")
    assert _conc(cliente, "auto-reintento").ejecutar_una() is True
    assert [(c["factura_id"], c["disparador"]) for c in _conciliaciones(base)] == [(orden[1], "AUTOMATICO")]

    base.sql("update public.cf_configuracion set conciliacion_automatica = true where id;")
    assert _conc(cliente, "auto-on").ejecutar_una() is True
    base.sql("update public.cf_configuracion set conciliacion_automatica = false where id;")
    ultima = _conciliaciones(base)[-1]
    assert (ultima["factura_id"], ultima["disparador"], ultima["modo"]) == (orden[0], "AUTOMATICO", "AUTOMATICO")
    assert [e["detalle"]["modo_ejecucion"] for e in _eventos(base, "CONCILIACION_CLAIM")] == ["AUTOMATICO"] * 2
    assert base.sql(FLAGS_SQL) == FLAGS_ESPERADOS and _locks(base) == "0|0"


# --------------------------------------------------------------------------
# 4.10 - 4.13 Datos existentes, privilegios, flags y rollback
# --------------------------------------------------------------------------

NUEVAS_FACTURAS = "'conciliacion_intentos_fallo' - 'conciliacion_ultima_clase_fallo'"
NUEVAS_CONFIG = "'conciliacion_max_intentos' - 'conciliacion_backoff'"


def test_4_10_y_4_12_conciliaciones_existentes_y_flags_intactos(pg17_nueva_base, tmp_path):
    pg = pg17_nueva_base("17")
    _normalizar(pg, tmp_path)
    _albaranes(pg)
    objetivo = _orden_oficial(pg)[0]
    # Conciliacion preexistente (como las 12 productivas), creada con el esquema 17.
    pg.sql(
        "insert into public.conciliaciones (factura_id,intento,disparador,estado,es_actual,importe_factura,"
        "importe_explicado,diferencia,resultado,worker_id,finalizado_at) "
        f"values ({_lit(objetivo)},1,'MANUAL','COMPLETADA',true,10,10,0,'CONCILIADA','manual-hito-previo',now());"
        "insert into public.conciliacion_detalles (conciliacion_id,orden,factura_albaran_extraido_id,"
        "tipo_relacion,importe_aplicado,estado) select c.id,1,a.id,'UNO_A_UNO',10,'COINCIDE' "
        "from public.conciliaciones c join public.facturas_albaranes_extraidos a on a.factura_id=c.factura_id "
        "order by a.id limit 1;")
    consultas = {
        "conciliaciones": "select to_jsonb(c) from public.conciliaciones c",
        "detalles": "select to_jsonb(d) from public.conciliacion_detalles d",
        "facturas": "select to_jsonb(f) from public.facturas f",
        "albaranes": "select to_jsonb(a) from public.albaranes a",
        "config": "select to_jsonb(c) from public.cf_configuracion c",
    }
    antes = {k: _huella(pg, q) for k, q in consultas.items()}
    flags = pg.sql(FLAGS_SQL)

    _aplicar_18(pg)

    despues = {
        "conciliaciones": _huella(pg, "select to_jsonb(c) - 'idempotency_key' from public.conciliaciones c"),
        "detalles": _huella(pg, consultas["detalles"]),
        "facturas": _huella(pg, f"select to_jsonb(f) - {NUEVAS_FACTURAS} from public.facturas f"),
        "albaranes": _huella(pg, consultas["albaranes"]),
        "config": _huella(pg, f"select to_jsonb(c) - {NUEVAS_CONFIG} from public.cf_configuracion c"),
    }
    assert despues == antes
    assert pg.sql("select count(*) from public.conciliaciones where idempotency_key is not null") == "0"
    assert pg.sql("select count(*) from public.facturas where conciliacion_intentos_fallo <> 0") == "0"
    assert pg.sql("select conciliacion_max_intentos, conciliacion_backoff from public.cf_configuracion") == (
        "4|{01:00:00,06:00:00,24:00:00}")
    assert flags == pg.sql(FLAGS_SQL) == FLAGS_ESPERADOS


def test_4_11_matriz_de_grants_y_security_definer(base):
    filas = base.json(
        "select p.oid::regprocedure::text as f, p.prosecdef as definer, pg_get_userbyid(p.proowner) as owner, "
        "p.proacl is null or exists(select 1 from aclexplode(p.proacl) a where a.grantee = 0) as public, "
        "has_function_privilege('anon', p.oid, 'EXECUTE') as anon, "
        "has_function_privilege('authenticated', p.oid, 'EXECUTE') as authenticated, "
        "has_function_privilege('service_role', p.oid, 'EXECUTE') as service_role "
        "from pg_proc p where p.pronamespace = 'public'::regnamespace and p.proname in ("
        "'cf_reclamar_factura_conciliacion_nucleo','cf_reclamar_factura_conciliacion',"
        "'cf_reclamar_factura_conciliacion_manual_one_shot','cf_persistir_conciliacion',"
        "'cf_registrar_fallo_conciliacion')")
    matriz = {f["f"].replace(" ", "").replace("public.", ""): f for f in filas}
    assert set(matriz) == set(FUNCIONES_18)
    for firma, service_role in FUNCIONES_18.items():
        f = matriz[firma]
        assert (f["definer"], f["owner"]) == (True, "postgres"), firma
        assert (f["public"], f["anon"], f["authenticated"]) == (False, False, False), firma
        assert f["service_role"] is service_role, firma
    # Funciones de conciliacion no redefinidas: privilegios de la migracion 12/14 sin cambios.
    assert base.sql("select has_function_privilege('authenticated', "
                    "'public.cf_solicitar_reintento_conciliacion(uuid,text)', 'EXECUTE')") == "t"
    with pytest.raises(RuntimeError, match="permission denied"):
        _sr(base, "select * from public.cf_reclamar_factura_conciliacion_nucleo('x', 300, 'MANUAL_ONE_SHOT');")


def test_4_13_rollback_devuelve_el_esquema_17_con_datos_de_la_18(pg17_nueva_base, tmp_path):
    referencia = esquema(pg17_nueva_base("17"))
    assert esquema(pg17_nueva_base("17_rollback")) == referencia

    usada = _aplicar_18(pg17_nueva_base("17"))
    cliente = _normalizar(usada, tmp_path)
    _albaranes(usada)
    orden = _orden_oficial(usada)
    assert _conc(cliente, "a").ejecutar_una_manual() is True
    usada.sql("update public.facturas set estado_conciliacion_cf = 'REVISION_CONCILIACION' "
              f"where id = {_lit(orden[1])};")
    usada.sql(ROLLBACK_18.read_text(encoding="utf-8"))
    assert usada.sql("select string_agg(disparador, ',') from public.conciliaciones") == "MANUAL"
    assert usada.sql(f"select estado_conciliacion_cf from public.facturas where id = {_lit(orden[1])}") == (
        "PENDIENTE_CONCILIAR")
    # Solo difieren los permisos por defecto emulados en esta base (y sus comentarios).
    def _sentencias(texto):
        return [l for l in texto.splitlines()
                if l.strip() and not l.startswith("--") and "DEFAULT PRIVILEGES" not in l]

    assert _sentencias(esquema(usada)) == _sentencias(referencia)


# --------------------------------------------------------------------------
# 4.14 Caso real (PDF del 2AO, albaranes operacionales sinteticos)
# --------------------------------------------------------------------------

TOTALES_2AO = {"08007969": "12807.1700", "08007970": "2356.6400", "08007971": "364.4700",
               "08007972": "464.7600", "08007973": "22.4900"}


@pytest.mark.skipif(not ALLIANCE_2AO.exists(), reason="PDF real del 2AO ausente (excluido de git)")
def test_4_14_caso_real_08007970(base, tmp_path):
    cliente = _normalizar(base, tmp_path, ALLIANCE_2AO, "2ao")
    facturas = {f["numero_factura"]: f for f in base.json(
        "select f.id::text, f.numero_factura, f.importe_total::text as total, e.estado, e.razon "
        "from public.facturas f cross join lateral public.cf_evaluar_elegibilidad_conciliacion(f.id) e "
        "where f.proveedor_literal ilike 'ALLIANCE%'")}
    assert {n: f["total"] for n, f in facturas.items()} == TOTALES_2AO
    assert (facturas["08007970"]["estado"], facturas["08007970"]["razon"]) == ("APTA", "APTA_MERCANCIA")
    assert (facturas["08007971"]["estado"], facturas["08007971"]["razon"]) == ("NO_APTA", "FALTAN_ALBARANES_MERCANCIA")
    # MIXTA: albaranes 13020.88 + movimientos -213.78 = 12807.10 frente a 12807.17 (0.07 > 0.05).
    assert (facturas["08007969"]["estado"], facturas["08007969"]["razon"]) == ("NO_APTA", "TOTAL_NO_EXPLICADO")
    assert {n for n, f in facturas.items() if f["estado"] == "APTA"} == {"08007970", "08007972", "08007973"}
    _albaranes(base, numeros=["08007970"])

    # Simulacion READ_ONLY (sin claim) con la construccion de detalles oficial.
    objetivo = FacturaTrabajo(facturas["08007970"]["id"], "", "PIO", Decimal("2356.64"))
    detalles = RepositorioRuntimeSupabase(cliente).construir_detalles(objetivo)
    resultado = conciliar_importes(objetivo.importe_total, detalles)
    assert (resultado.resultado, resultado.importe_explicado, resultado.diferencia) == (
        "CONCILIADA", Decimal("2356.6800"), Decimal("-0.0400"))
    assert len(detalles) == 71
    assert {d.tipo_relacion.value for d in detalles} == {"UNO_A_UNO"}
    assert all(d.coincidencia_numero_literal for d in detalles)
    assert _eventos(base, "CONCILIACION_CLAIM") == [] and _locks(base) == "0|0"

    # Ruta manual oficial: reclama el n.o 1 del ordering, sea cual sea.
    orden = _orden_oficial(base)
    assert len(orden) == 3
    assert _conc(cliente, "real").ejecutar_una_manual() is True
    [c] = _conciliaciones(base)
    assert (c["factura_id"], c["disparador"]) == (orden[0], "MANUAL_ONE_SHOT")
    if c["factura_id"] == objetivo.factura_id:
        assert (c["resultado"], c["importe_explicado"], c["diferencia"], c["detalles"]) == (
            "CONCILIADA", "2356.6800", "-0.0400", 71)
    assert [e["actor"] for e in _eventos(base, "CONCILIACION_CLAIM")] == ["conc-real"]
    assert _locks(base) == "0|0" and base.sql(FLAGS_SQL) == FLAGS_ESPERADOS


# --------------------------------------------------------------------------
# Divergencias simulador / PostgreSQL
# --------------------------------------------------------------------------

def _estado_pg(pg, factura_id):
    f = _factura(pg, factura_id)
    return {"estado": f["estado_conciliacion_cf"], "intentos_fallo": f["conciliacion_intentos_fallo"],
            "bloqueado": f["conciliacion_bloqueado_por"] is not None,
            "conciliaciones": len(_conciliaciones(pg, factura_id)),
            "backoff_horas": f["backoff_horas"]}


def test_simulador_y_postgresql_coinciden(base, tmp_path):
    _normalizar(base, tmp_path)
    orden = _orden_oficial(base)
    sim = SupabaseConciliacionMemoria()
    for factura_id in orden:
        sim.anadir(factura_id, "2026-09-20")
    pg = ClientePg17(base)
    resultado = {"resultado": "CONCILIADA", "importe_factura": "1", "importe_explicado": "1",
                 "diferencia": "0", "tolerancia": "0.0500", "detalles": []}

    def ambos(nombre, payload):
        return sim.rpc(nombre, payload).data, pg.rpc(nombre, payload).execute().data

    def claim(worker):
        s, p = ambos("cf_reclamar_factura_conciliacion_manual_one_shot", {"p_worker_id": worker, "p_bloqueo_segundos": 300})
        return (s[0]["id"] if s else None), (p[0]["id"] if p else None)

    def persistir(factura_id, worker, clave):
        payload = {"p_factura_id": factura_id, "p_worker_id": worker, "p_disparador": "MANUAL_ONE_SHOT",
                   "p_idempotency_key": clave, "p_resultado": resultado}
        s, p = ambos("cf_persistir_conciliacion", payload)
        return s is not None, p is not None

    def fallo(factura_id, worker):
        return ambos("cf_registrar_fallo_conciliacion", {
            "p_factura_id": factura_id, "p_worker_id": worker, "p_disparador": "MANUAL_ONE_SHOT",
            "p_error_codigo": "RuntimeError", "p_error_detalle": "x", "p_clase_fallo": "TRANSITORIO"})

    def comparar():
        for factura_id in orden:
            assert sim.estado(factura_id) == _estado_pg(base, factura_id), factura_id

    a, b = orden[0], orden[1]
    s, p = claim("w")
    assert s == p == a
    assert persistir(a, "w", "k1") == (True, True)
    comparar()
    sim.solicitar_reintento(a)
    base.sql(f"select public.cf_solicitar_reintento_conciliacion({_lit(a)}::uuid, 'test-2av');")
    assert claim("w2") == (a, a)
    assert persistir(a, "w2", "k1") == (True, True)  # replay
    comparar()
    for intento in range(1, 5):
        assert claim("w") == (b, b)
        assert fallo(b, "w") == (True, True)
        comparar()
        if intento < 4:  # tras el 4.o queda en REVISION_CONCILIACION, sin backoff
            sim.avanzar_tiempo(b)
            _vencer_backoff(base, b)
    assert claim("w") == (orden[2], orden[2])
    assert fallo(orden[2], "otro") == (False, False)
    comparar()
