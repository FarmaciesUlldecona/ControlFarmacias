from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.runtime_supabase.extraccion_productiva import (
    OrquestadorExtraccionProductiva,
)
from src.facturas.runtime_supabase.modelos import (
    ConfiguracionRuntime,
    DocumentoTrabajo,
    ResultadoEtapa,
    ResultadoExtraccionProductiva,
)
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_automatico import (
    MAX_DOCUMENTOS_POR_EJECUCION,
    construir_worker_automatico,
)
from src.facturas.runtime_supabase.worker_normalizacion import WorkerNormalizacion


class _Etapa:
    codigo = "LOCAL"

    def extraer(self, _ruta: Path, pendientes: frozenset[str]):
        return ResultadoEtapa(
            valores={campo: "ok" for campo in pendientes},
            provenance={"fuente": "LOCAL"},
        )


class _Repo:
    def __init__(self, docs):
        self.docs = list(docs)
        self.persistidos = []
        self.fallos = []
        self.claims = 0

    def reclamar_documento(self, _worker):
        self.claims += 1
        return self.docs.pop(0) if self.docs else None

    def persistir_documento_automatico(self, *args):
        self.persistidos.append(args)

    def persistir_normalizacion(self, *_args):
        raise AssertionError("la ruta automática no debe usar la RPC monofactura")

    def fallar_ejecucion(self, *args):
        self.fallos.append(args)


class _WorkerContador:
    def __init__(self, resultado=True, tolerancia=Decimal("0.0500")):
        self.llamadas = 0
        self.resultado = resultado
        self.tolerancia = tolerancia

    def ejecutar_una(self):
        self.llamadas += 1
        return self.resultado


def _campo(valor, pagina=1):
    return {"valor": valor, "literal": str(valor), "evidencia": [{"pagina": pagina, "literal": str(valor)}]}


def _documento_normalizado(numero="F-1", total="121.0000"):
    return {
        "documento_completo_demostrado": True,
        "numero_paginas": 1,
        "facturas": [{
            "factura_id": "provisional",
            "factura_completa_demostrada": True,
            "tipo_documento": _campo("FACTURA"),
            "numero_factura": _campo(numero),
            "fecha_factura": _campo({"iso": "2026-09-01"}),
            "proveedor": {"nif": _campo("A50004324"), "nombre": _campo("PROVEEDOR")},
            "destinatario": {"nif": _campo("40901058C"), "nombre": _campo("PUIG SALOMON, PIO")},
            "totales": {"total": _campo(total)},
            "naturaleza_principal": "SERVICIOS",
            "estado_validacion": "VALIDADA",
            "requiere_conciliacion_albaranes": False,
            "pagina_inicio": 1,
            "pagina_fin": 1,
            "provenance": {"segment_id": "s1", "paginas": [1]},
            "impuestos": [], "vencimientos": [], "albaranes": [],
            "movimientos_comerciales": [], "incidencias": [],
        }],
    }


def _normalizador(repo, documento):
    orquestador = OrquestadorExtraccionProductiva(
        extractor_especifico=_Etapa(), extractor_generico_local=None,
        extractor_ocr_local=None, extractor_luna=None,
    )
    return WorkerNormalizacion(
        repo, lambda _doc: Path("fixture.pdf"), orquestador,
        frozenset({"documento"}), "worker-2ab",
        ensamblar_documento=lambda _doc, _result: documento,
    )


def test_limite_oficial_es_un_documento_y_no_hay_bucle_implicito():
    assert MAX_DOCUMENTOS_POR_EJECUCION == 1
    normalizacion = _WorkerContador()
    conciliacion = _WorkerContador()
    worker = construir_worker_automatico(
        normalizacion, conciliacion,
        ConfiguracionRuntime(normalizacion_automatica=True, conciliacion_automatica=True),
    )
    resultado = worker.ejecutar_una()
    assert normalizacion.llamadas == conciliacion.llamadas == 1
    assert resultado.documentos_reclamados == 1


def test_flags_false_impiden_incluso_el_claim():
    normalizacion = _WorkerContador()
    conciliacion = _WorkerContador()
    resultado = construir_worker_automatico(
        normalizacion, conciliacion, ConfiguracionRuntime(),
    ).ejecutar_una()
    assert normalizacion.llamadas == conciliacion.llamadas == 0
    assert resultado.automatismos_habilitados is False


def test_worker_reclama_un_solo_pdf_aunque_haya_dos_disponibles():
    docs = [
        DocumentoTrabajo("d1", "PIO/1.pdf", "1.pdf", "PIO"),
        DocumentoTrabajo("d2", "PIO/2.pdf", "2.pdf", "PIO"),
    ]
    repo = _Repo(docs)
    worker = _normalizador(repo, _documento_normalizado())
    assert worker.ejecutar_una() is True
    assert repo.claims == 1 and len(repo.docs) == 1 and len(repo.persistidos) == 1


def test_idempotencia_deriva_del_contenido_y_no_de_uuid():
    keys = []
    for _ in range(2):
        repo = _Repo([DocumentoTrabajo("d1", "PIO/1.pdf", "1.pdf", "PIO")])
        assert _normalizador(repo, _documento_normalizado()).ejecutar_una() is True
        keys.append(repo.persistidos[0][-1])
    assert keys[0] == keys[1]
    assert keys[0].startswith("normalizacion:d1:AUTOMATICO:")


def test_hash_cambia_si_cambia_la_economia_normalizada():
    hashes = []
    for total in ("121.0000", "122.0000"):
        repo = _Repo([DocumentoTrabajo("d1", "PIO/1.pdf", "1.pdf", "PIO")])
        assert _normalizador(repo, _documento_normalizado(total=total)).ejecutar_una()
        hashes.append(repo.persistidos[0][2])
    assert hashes[0] != hashes[1]


def test_luna_y_tolerancia_superior_quedan_bloqueadas():
    normalizacion, conciliacion = _WorkerContador(), _WorkerContador()
    with pytest.raises(ValueError, match="LUNA_NO_AUTORIZADA"):
        construir_worker_automatico(
            normalizacion, conciliacion,
            ConfiguracionRuntime(luna_habilitada=True),
        )
    with pytest.raises(ValueError, match="TOLERANCIA_RUNTIME"):
        construir_worker_automatico(
            normalizacion, conciliacion,
            ConfiguracionRuntime(tolerancia_conciliacion=Decimal("0.06")),
        )
    with pytest.raises(ValueError, match="SOLO_PIO"):
        construir_worker_automatico(
            normalizacion, conciliacion,
            ConfiguracionRuntime(farmacias_habilitadas=("PIO", "RITA")),
        )


def test_error_rpc_se_registra_y_no_se_da_por_persistido():
    class RepoError(_Repo):
        def persistir_documento_automatico(self, *_args):
            raise RuntimeError("RPC_CAIDA")

    repo = RepoError([DocumentoTrabajo("d1", "PIO/1.pdf", "1.pdf", "PIO")])
    assert _normalizador(repo, _documento_normalizado()).ejecutar_una() is False
    assert repo.persistidos == [] and len(repo.fallos) == 1
    assert repo.fallos[0][-1].startswith("normalizacion:d1:AUTOMATICO:")


class _Response:
    data = None


class _Client:
    def __init__(self):
        self.calls = []

    def rpc(self, name, payload):
        self.calls.append((name, payload))
        return self

    def execute(self):
        return _Response()


def test_repositorio_automatico_usa_rpc_multifactura_e_identidad_economica():
    client = _Client()
    resultado = ResultadoExtraccionProductiva(
        valores={}, campos_pendientes=(), pasos=(), uso_luna=None,
        incidencias=(),
        documento_normalizado=_documento_normalizado(),
    )
    RepositorioRuntimeSupabase(client).persistir_documento_automatico(
        DocumentoTrabajo("d1", "PIO/1.pdf", "1.pdf", "PIO"),
        resultado, "hash", "worker", "AUTOMATICO", "idem",
    )
    name, payload = client.calls[0]
    assert name == "cf_persistir_documento_multifactura"
    assert payload["p_segmentos_autorizados"] == ["s1"]
    assert payload["p_resultado"]["facturas"][0]["identidad_economica_clave"]


def test_identidad_no_demostrada_impide_persistencia_automatica():
    document = _documento_normalizado()
    document["facturas"][0]["proveedor"]["nif"]["evidencia"] = []
    result = ResultadoExtraccionProductiva(
        valores={}, campos_pendientes=(), pasos=(), uso_luna=None,
        incidencias=(),
        documento_normalizado=document,
    )
    with pytest.raises(ValueError, match="NINGUNA_FACTURA_AUTORIZABLE"):
        RepositorioRuntimeSupabase(_Client()).persistir_documento_automatico(
            DocumentoTrabajo("d1", "PIO/1.pdf", "1.pdf", "PIO"),
            result, "hash", "worker", "AUTOMATICO", "idem",
        )
