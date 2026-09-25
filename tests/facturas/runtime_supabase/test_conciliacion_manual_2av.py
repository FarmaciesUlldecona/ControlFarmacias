"""Hito 2AV: ruta manual de conciliacion, cierre atomico, backoff y R9 (sin PostgreSQL)."""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from simulador_conciliacion_2av import SupabaseConciliacionMemoria
from src.facturas.runtime_supabase import repositorios as repos
from src.facturas.runtime_supabase.clasificacion_fallos import (
    DEFECTO_DOCUMENTO, TRANSITORIO, clasificar_fallo_conciliacion,
)
from src.facturas.runtime_supabase.conciliacion import (
    AlbaranDocumentalTrabajo, CandidatoAlbaranSupabase, _id_proveedor_comparable,
    buscar_candidato_albaran, conciliar_importes,
)
from src.facturas.runtime_supabase.modelos import (
    ConfiguracionRuntime, DetalleConciliacion, FacturaTrabajo, TipoRelacionConciliacion,
    conservar_id_proveedor,
)
from src.facturas.runtime_supabase.worker_automatico import construir_worker_automatico
from src.facturas.runtime_supabase.worker_conciliacion import WorkerConciliacion


ROOT = Path(__file__).resolve().parents[3]
MIG = ROOT / "sql/migrations"
SQL_18 = (MIG / "18_cf_conciliacion_manual_atomica.sql").read_text(encoding="utf-8")
ROLLBACK_18 = (MIG / "18_cf_conciliacion_manual_atomica.rollback.sql").read_text(encoding="utf-8")
SQL_14 = (MIG / "14_cf_claim_conciliacion_v2.sql").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# R9
# --------------------------------------------------------------------------

@pytest.mark.parametrize("valor", ["2", "0002", "0002 ", " 02"])
def test_r9_id_proveedor_comparable_tolera_trim_y_ceros(valor):
    assert _id_proveedor_comparable(valor) == "2"


def test_r9_no_altera_literales_ni_identificadores_no_numericos():
    assert conservar_id_proveedor("0002 ") == "0002 "
    assert _id_proveedor_comparable("A2") == "A2"
    assert _id_proveedor_comparable("0") == "0"
    assert _id_proveedor_comparable("   ") is None
    assert _id_proveedor_comparable("2") != _id_proveedor_comparable("20")


@pytest.mark.parametrize("literal", ["2", "0002", "0002 "])
def test_r9_buscar_candidato_casa_variantes_de_id_proveedor(literal):
    candidato = CandidatoAlbaranSupabase(
        id_contador=1, farmacia="PIO", id_proveedor=literal, proveedor="1.- SAFA",
        numero_albaran="08C1", fecha=date(2026, 6, 23), importe_puc=Decimal("10.00"),
        importe_pvp=Decimal("15.00"), estado="PENDIENTE")
    documental = AlbaranDocumentalTrabajo(
        id="a", numero="08C1", fecha=date(2026, 6, 23), importe=Decimal("10.00"), sentido="CARGO")
    resultado = buscar_candidato_albaran(
        documental, [candidato], proveedor_literal="ALLIANCE", farmatic_id_proveedor="0002")
    assert resultado.estado == "MATCH_UNICO" and resultado.candidato is candidato


def test_r9_proveedor_distinto_no_casa():
    candidato = CandidatoAlbaranSupabase(
        id_contador=1, farmacia="PIO", id_proveedor="20", proveedor="OTRO",
        numero_albaran="08C1", fecha=date(2026, 6, 23), importe_puc=Decimal("10.00"),
        importe_pvp=None, estado="PENDIENTE")
    documental = AlbaranDocumentalTrabajo(
        id="a", numero="08C1", fecha=date(2026, 6, 23), importe=Decimal("10.00"), sentido="CARGO")
    assert buscar_candidato_albaran(
        documental, [candidato], proveedor_literal=None, farmatic_id_proveedor="2").candidato is None


# --------------------------------------------------------------------------
# Clasificacion de fallos (R7)
# --------------------------------------------------------------------------

def test_r7_clasificacion_de_fallos_de_conciliacion():
    assert clasificar_fallo_conciliacion("IMPORTE_FACTURA_AUSENTE", "x") == DEFECTO_DOCUMENTO
    assert clasificar_fallo_conciliacion("ValueError", "TIPO_DOCUMENTAL_NO_DEMOSTRADO") == DEFECTO_DOCUMENTO
    assert clasificar_fallo_conciliacion("ErrorFarmaciaDocumental", "x") == DEFECTO_DOCUMENTO
    assert clasificar_fallo_conciliacion("RuntimeError", "timeout de red") == TRANSITORIO
    assert clasificar_fallo_conciliacion(None, None) == TRANSITORIO


# --------------------------------------------------------------------------
# Payload y clave idempotente (R6)
# --------------------------------------------------------------------------

def _resultado(importe="10"):
    detalle = DetalleConciliacion(
        tipo_relacion=TipoRelacionConciliacion.UNO_A_UNO, importe_aplicado=Decimal(importe),
        albaran_farmacia="PIO", albaran_id_contador=7, factura_albaran_extraido_id="a1",
        coincidencia_numero_literal=True, provenance={"fecha": date(2026, 6, 23)})
    return conciliar_importes(Decimal("10"), [detalle])


def test_r6_clave_idempotente_determinista_y_sensible_a_la_evidencia():
    uno, dos = repos.payload_conciliacion(_resultado()), repos.payload_conciliacion(_resultado())
    assert uno == dos
    clave = repos.clave_idempotente_conciliacion("f1", "MANUAL_ONE_SHOT", uno)
    assert clave == repos.clave_idempotente_conciliacion("f1", "MANUAL_ONE_SHOT", dos)
    assert clave.startswith("conciliacion:f1:MANUAL_ONE_SHOT:")
    distinto = repos.payload_conciliacion(_resultado("9"))
    assert clave != repos.clave_idempotente_conciliacion("f1", "MANUAL_ONE_SHOT", distinto)
    assert uno["detalles"][0]["estado"] == "COINCIDE"
    assert uno["detalles"][0]["provenance"]["fecha"] == "2026-06-23"


class _ClienteRpc:
    """Lecturas minimas de revalidacion + captura de RPC; sin update ni insert."""

    def __init__(self):
        self.rpcs, self._tabla = [], None

    def table(self, nombre):
        self._tabla = nombre
        return self

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def single(self):
        return self

    def execute(self):
        if self._tabla == "facturas":
            return SimpleNamespace(data={"farmacia": "PIO", "normalizacion_ejecucion_id": "n"})
        if self._tabla == "normalizacion_ejecuciones":
            return SimpleNamespace(data={"resultado_json": {}})
        return SimpleNamespace(data="c-1")

    def rpc(self, nombre, payload):
        self.rpcs.append((nombre, payload))
        self._tabla = None
        return self

    def update(self, *_):
        pytest.fail("escritura REST prohibida: solo RPC transaccional")

    insert = update


def test_r6_guardar_conciliacion_es_una_unica_rpc_transaccional(monkeypatch):
    monkeypatch.setattr(repos, "validar_documento_antes_de_persistir", lambda *_: None)
    cliente = _ClienteRpc()
    factura = FacturaTrabajo("f1", "d1", "PIO", Decimal("10"))
    repos.RepositorioRuntimeSupabase(cliente).guardar_conciliacion(
        factura, "w", _resultado(), disparador="MANUAL_ONE_SHOT")
    assert [n for n, _ in cliente.rpcs] == ["cf_persistir_conciliacion"]
    payload = cliente.rpcs[0][1]
    assert payload["p_disparador"] == "MANUAL_ONE_SHOT"
    assert payload["p_idempotency_key"] == repos.clave_idempotente_conciliacion(
        "f1", "MANUAL_ONE_SHOT", payload["p_resultado"])


@pytest.mark.parametrize("disparador", ["MANUAL", "REINTENTO", "TEST", "OTRO"])
def test_r8_guardar_rechaza_disparadores_no_admitidos(disparador):
    with pytest.raises(ValueError, match="disparador"):
        repos.RepositorioRuntimeSupabase(_ClienteRpc()).guardar_conciliacion(
            FacturaTrabajo("f1", "d1", "PIO", Decimal("10")), "w", _resultado(), disparador=disparador)


def test_r7_fallar_conciliacion_envia_clase_y_worker():
    cliente = _ClienteRpc()
    repos.RepositorioRuntimeSupabase(cliente).fallar_conciliacion(
        FacturaTrabajo("f1", "d1", "PIO", None), "IMPORTE_FACTURA_AUSENTE", "sin total", "w", "MANUAL_ONE_SHOT")
    nombre, payload = cliente.rpcs[0]
    assert nombre == "cf_registrar_fallo_conciliacion"
    assert payload["p_worker_id"] == "w" and payload["p_disparador"] == "MANUAL_ONE_SHOT"
    assert payload["p_clase_fallo"] == DEFECTO_DOCUMENTO


# --------------------------------------------------------------------------
# Workers (R5/R8)
# --------------------------------------------------------------------------

class _RepoDoble:
    def __init__(self, facturas):
        self.facturas = list(facturas)
        self.claims, self.guardados, self.fallos = [], [], []

    def reclamar_factura(self, worker_id):
        self.claims.append("AUTOMATICO")
        return self.facturas.pop(0) if self.facturas else None

    def reclamar_factura_manual_one_shot(self, worker_id):
        self.claims.append("MANUAL_ONE_SHOT")
        return self.facturas.pop(0) if self.facturas else None

    def guardar_conciliacion(self, factura, worker_id, resultado, *, disparador="AUTOMATICO"):
        self.guardados.append((factura.factura_id, disparador))
        return "c"

    def fallar_conciliacion(self, factura, codigo, detalle, worker_id, disparador="AUTOMATICO"):
        self.fallos.append((factura.factura_id, codigo, disparador))


def _detalle(_factura):
    return [DetalleConciliacion(tipo_relacion=TipoRelacionConciliacion.UNO_A_UNO,
                                importe_aplicado=Decimal("10"), albaran_farmacia="PIO",
                                albaran_id_contador=1, factura_albaran_extraido_id="a")]


def test_r5_manual_reclama_como_maximo_una_factura_con_provenance_manual():
    repo = _RepoDoble([FacturaTrabajo("f1", "d", "PIO", Decimal("10")),
                       FacturaTrabajo("f2", "d", "PIO", Decimal("10"))])
    assert WorkerConciliacion(repo, _detalle, "w").ejecutar_una_manual() is True
    assert repo.claims == ["MANUAL_ONE_SHOT"]
    assert repo.guardados == [("f1", "MANUAL_ONE_SHOT")]
    assert [f.factura_id for f in repo.facturas] == ["f2"]


def test_r8_ruta_automatica_conserva_disparador_automatico():
    repo = _RepoDoble([FacturaTrabajo("f1", "d", "PIO", Decimal("10"))])
    assert WorkerConciliacion(repo, _detalle, "w").ejecutar_una() is True
    assert repo.claims == ["AUTOMATICO"] and repo.guardados == [("f1", "AUTOMATICO")]


def test_r7_manual_sin_total_registra_fallo_manual():
    repo = _RepoDoble([FacturaTrabajo("f1", "d", "PIO", None)])
    assert WorkerConciliacion(repo, _detalle, "w").ejecutar_una_manual() is False
    assert repo.fallos == [("f1", "IMPORTE_FACTURA_AUSENTE", "MANUAL_ONE_SHOT")]


def test_r5_worker_automatico_manual_conciliacion_no_normaliza():
    class _Normalizacion:
        def ejecutar_una(self):
            pytest.fail("no debe normalizar")

        ejecutar_una_manual_one_shot = ejecutar_una

    repo = _RepoDoble([FacturaTrabajo("f1", "d", "PIO", Decimal("10"))])
    worker = construir_worker_automatico(
        _Normalizacion(), WorkerConciliacion(repo, _detalle, "w"), ConfiguracionRuntime())
    resultado = worker.ejecutar_una_manual_conciliacion()
    assert resultado.facturas_conciliacion_reclamadas == 1
    assert resultado.documentos_reclamados == 0
    assert resultado.automatismos_habilitados is False
    assert resultado.modo_ejecucion == "MANUAL_ONE_SHOT"


# --------------------------------------------------------------------------
# Simulador alineado con la 18
# --------------------------------------------------------------------------

def _sim(*ids, automatica=False):
    sim = SupabaseConciliacionMemoria(conciliacion_automatica=automatica)
    for i in ids:
        sim.anadir(i, "2026-06-30")
    return sim


def _persistir(sim, factura, worker, disparador, clave="k1"):
    return sim.rpc("cf_persistir_conciliacion", {
        "p_factura_id": factura, "p_worker_id": worker, "p_disparador": disparador,
        "p_idempotency_key": clave, "p_resultado": {"resultado": "CONCILIADA", "detalles": [{}]}}).data


def test_simulador_manual_flag_apagado_y_ordering():
    sim = _sim("b", "a")
    assert sim.rpc("cf_reclamar_factura_conciliacion", {"p_worker_id": "w"}).data == []
    assert sim.rpc("cf_reclamar_factura_conciliacion_manual_one_shot", {"p_worker_id": "w"}).data[0]["id"] == "a"


def test_simulador_replay_libera_claim_y_no_duplica():
    sim = _sim("a")
    sim.rpc("cf_reclamar_factura_conciliacion_manual_one_shot", {"p_worker_id": "w"})
    primero = _persistir(sim, "a", "w", "MANUAL_ONE_SHOT")
    sim.solicitar_reintento("a")
    sim.rpc("cf_reclamar_factura_conciliacion_manual_one_shot", {"p_worker_id": "w2"})
    assert _persistir(sim, "a", "w2", "MANUAL_ONE_SHOT") == primero
    assert sim.estado("a") == {"estado": "CONCILIADA", "intentos_fallo": 0, "bloqueado": False,
                               "conciliaciones": 1, "backoff_horas": None}


def test_simulador_disparador_debe_coincidir_con_el_claim():
    sim = _sim("a")
    sim.rpc("cf_reclamar_factura_conciliacion_manual_one_shot", {"p_worker_id": "w"})
    with pytest.raises(RuntimeError, match="DISPARADOR_NO_COINCIDE"):
        _persistir(sim, "a", "w", "AUTOMATICO")


def test_simulador_backoff_y_revision():
    sim = _sim("a")
    horas = []
    for _ in range(4):
        sim.rpc("cf_reclamar_factura_conciliacion_manual_one_shot", {"p_worker_id": "w"})
        assert sim.rpc("cf_registrar_fallo_conciliacion", {
            "p_factura_id": "a", "p_worker_id": "w", "p_clase_fallo": TRANSITORIO}).data is True
        horas.append(sim.estado("a")["backoff_horas"])
        sim.avanzar_tiempo("a")
    assert horas == [1, 6, 24, None]
    assert sim.estado("a")["estado"] == "REVISION_CONCILIACION"
    assert sim.rpc("cf_reclamar_factura_conciliacion_manual_one_shot", {"p_worker_id": "w"}).data == []
    sim.solicitar_reintento("a")
    sim.rpc("cf_reclamar_factura_conciliacion_manual_one_shot", {"p_worker_id": "w"})
    sim.rpc("cf_registrar_fallo_conciliacion", {"p_factura_id": "a", "p_worker_id": "w",
                                                "p_clase_fallo": TRANSITORIO})
    assert sim.estado("a")["intentos_fallo"] == 1 and sim.estado("a")["backoff_horas"] == 1


# --------------------------------------------------------------------------
# Estaticos de la migracion 18
# --------------------------------------------------------------------------

def _funciones(sql):
    return re.findall(r"create or replace function public\.(\w+)\(([^)]*)\)", sql, re.I)


def _tipos(parametros):
    tipos = []
    for p in parametros.split(","):
        partes = p.strip().split()
        if partes:
            tipos.append(partes[1])
    return ", ".join(tipos)


def test_18_toda_funcion_revoca_public_anon_authenticated_y_es_security_definer():
    for nombre, parametros in _funciones(SQL_18):
        firma = f"public.{nombre}({_tipos(parametros)})"
        patron = rf"revoke all on function {re.escape(firma)}\s+from public, anon, authenticated"
        assert re.search(patron, SQL_18), firma
    cuerpos = re.split(r"create or replace function ", SQL_18)[1:]
    assert len(cuerpos) == 5
    assert all("security definer" in c.split("as $$")[0] for c in cuerpos)


def test_18_nucleo_interno_sin_grant_a_service_role():
    assert re.search(r"revoke all on function public\.cf_reclamar_factura_conciliacion_nucleo"
                     r"\(text, integer, text\)\s+from public, anon, authenticated, service_role", SQL_18)
    assert "grant execute on function public.cf_reclamar_factura_conciliacion_nucleo" not in SQL_18


def _bloque_selector(sql, inicio):
    cuerpo = sql[sql.rindex(inicio):]
    bloque = cuerpo[cuerpo.index("select f.id"):cuerpo.index("limit 1;")]
    bloque = re.sub(r"--[^\n]*", "", bloque)
    return re.sub(r"\s+", " ", bloque).strip()


def test_r5_selector_y_ordering_identicos_a_la_14_salvo_el_interruptor():
    previo = _bloque_selector(SQL_14, "create or replace function public.cf_reclamar_factura_conciliacion(")
    nuevo = _bloque_selector(SQL_18, "create or replace function public.cf_reclamar_factura_conciliacion_nucleo(")
    interruptor_14 = "and (c.conciliacion_automatica or f.conciliacion_reintento_solicitado_at is not null)"
    interruptor_18 = ("and ( p_modo_ejecucion = 'MANUAL_ONE_SHOT' or c.conciliacion_automatica "
                      "or f.conciliacion_reintento_solicitado_at is not null )")
    assert interruptor_14 in previo and interruptor_18 in nuevo
    assert previo.replace(interruptor_14, "") == nuevo.replace(interruptor_18, "")


def test_18_sin_dml_sobre_datos_existentes_fuera_de_funciones():
    fuera = re.sub(r"\$\$.*?\$\$", "", SQL_18, flags=re.S).casefold()
    assert re.search(r"^\s*(update|delete|insert|truncate)\b", fuera, re.M) is None


def test_rollback_18_solo_mapea_valores_nuevos():
    fuera = re.sub(r"\$\$.*?\$\$", "", ROLLBACK_18, flags=re.S)
    dml = re.findall(r"^\s*(update|delete|insert)\b[^;]*;", fuera, re.M | re.I | re.S)
    assert len(dml) == 2
    assert "where estado_conciliacion_cf = 'REVISION_CONCILIACION'" in fuera
    assert "where disparador = 'MANUAL_ONE_SHOT'" in fuera


def test_18_no_redefine_funciones_de_conciliacion_existentes_salvo_el_claim():
    nombres = {n for n, _ in _funciones(SQL_18)}
    assert nombres == {
        "cf_reclamar_factura_conciliacion_nucleo", "cf_reclamar_factura_conciliacion",
        "cf_reclamar_factura_conciliacion_manual_one_shot", "cf_persistir_conciliacion",
        "cf_registrar_fallo_conciliacion",
    }
