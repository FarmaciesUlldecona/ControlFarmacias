from __future__ import annotations

import inspect
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
)
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_automatico import (
    MAX_DOCUMENTOS_POR_EJECUCION,
    construir_worker_automatico,
)
from src.facturas.runtime_supabase.worker_normalizacion import WorkerNormalizacion


ROOT = Path(__file__).resolve().parents[3]
SQL = (ROOT / "sql" / "migrations" / "16_cf_worker_manual_one_shot.sql").read_text(
    encoding="utf-8"
)


class _Etapa:
    codigo = "LOCAL"

    def extraer(self, _ruta: Path, pendientes: frozenset[str]):
        return ResultadoEtapa(
            valores={campo: "ok" for campo in pendientes},
            provenance={"fuente": "LOCAL"},
        )


class _RepoMemoria:
    def __init__(self, documentos=(), *, auto=False, duplicado=False):
        self.documentos = list(documentos)
        self.auto = auto
        self.duplicado = duplicado
        self.claims_auto = 0
        self.claims_manual = 0
        self.persistidos = []
        self.fallos = []
        self.lock = None

    def _claim(self):
        if not self.documentos:
            return None
        documento = self.documentos.pop(0)
        self.lock = documento.documento_id
        return documento

    def reclamar_documento(self, _worker_id):
        self.claims_auto += 1
        return self._claim() if self.auto else None

    def reclamar_documento_manual_one_shot(self, _worker_id):
        self.claims_manual += 1
        return self._claim()

    def persistir_documento_automatico(self, *args):
        if not self.duplicado:
            self.persistidos.append(args)
        self.lock = None

    def persistir_normalizacion(self, *_args):
        raise AssertionError("La ruta oficial debe conservar multifactura")

    def fallar_ejecucion(self, *args):
        self.fallos.append(args)
        self.lock = None


class _Conciliacion:
    tolerancia = Decimal("0.0500")

    def __init__(self):
        self.llamadas = 0

    def ejecutar_una(self):
        self.llamadas += 1
        return True


class _Cliente:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []
        self.data = None

    def rpc(self, name, payload):
        self.calls.append((name, payload))
        self.data = self.rows
        return self

    def execute(self):
        return self


def _campo(valor, pagina=1):
    return {
        "valor": valor,
        "literal": str(valor),
        "evidencia": [{"pagina": pagina, "literal": str(valor)}],
    }


def _factura(numero="F-1", pagina=1, segmento="s1"):
    return {
        "factura_id": f"provisional-{segmento}",
        "factura_completa_demostrada": True,
        "tipo_documento": _campo("FACTURA", pagina),
        "numero_factura": _campo(numero, pagina),
        "fecha_factura": _campo({"iso": "2026-09-01"}, pagina),
        "proveedor": {
            "nif": _campo("A50004324", pagina),
            "nombre": _campo("PROVEEDOR", pagina),
        },
        "destinatario": {
            "nif": _campo("40901058C", pagina),
            "nombre": _campo("PUIG SALOMON, PIO", pagina),
        },
        "totales": {"total": _campo("121.0000", pagina)},
        "naturaleza_principal": "SERVICIOS",
        "estado_validacion": "VALIDADA",
        "requiere_conciliacion_albaranes": False,
        "pagina_inicio": pagina,
        "pagina_fin": pagina,
        "provenance": {"segment_id": segmento, "paginas": [pagina]},
        "impuestos": [],
        "vencimientos": [],
        "albaranes": [],
        "movimientos_comerciales": [],
        "incidencias": [],
    }


def _documento(*facturas):
    facturas = facturas or (_factura(),)
    return {
        "documento_completo_demostrado": True,
        "numero_paginas": len(facturas),
        "facturas": list(facturas),
    }


def _normalizador(repo, documento=None):
    servicio = OrquestadorExtraccionProductiva(
        extractor_especifico=_Etapa(),
        extractor_generico_local=None,
        extractor_ocr_local=None,
        extractor_luna=None,
    )
    return WorkerNormalizacion(
        repositorio=repo,
        materializar_pdf=lambda _doc: Path("shadow.pdf"),
        orquestador=servicio,
        campos_requeridos=frozenset({"documento"}),
        worker_id="worker-manual-2al",
        ensamblar_documento=lambda _doc, _result: documento or _documento(),
    )


def _worker(repo, documento=None, configuracion=None):
    conciliacion = _Conciliacion()
    worker = construir_worker_automatico(
        _normalizador(repo, documento),
        conciliacion,
        configuracion or ConfiguracionRuntime(),
    )
    return worker, conciliacion


def _docs(n=2):
    return [
        DocumentoTrabajo(f"d{i}", f"PIO/{i}.pdf", f"{i}.pdf", "PIO")
        for i in range(1, n + 1)
    ]


def test_flag_false_mantiene_ruta_automatica_sin_claim():
    repo = _RepoMemoria(_docs())
    resultado = _worker(repo)[0].ejecutar_una()
    assert resultado.documentos_reclamados == 0
    assert repo.claims_auto == repo.claims_manual == 0


def test_flag_false_permite_claim_manual_exactamente_uno():
    repo = _RepoMemoria(_docs())
    resultado = _worker(repo)[0].ejecutar_una_manual()
    assert resultado.documentos_reclamados == 1
    assert repo.claims_manual == 1 and len(repo.documentos) == 1


def test_manual_no_modifica_configuracion():
    configuracion = ConfiguracionRuntime()
    repo = _RepoMemoria(_docs(1))
    _worker(repo, configuracion=configuracion)[0].ejecutar_una_manual()
    assert configuracion == ConfiguracionRuntime()


def test_selector_automatico_y_manual_comparten_nucleo_sql():
    # Definicion, dos wrappers y REVOKE del nucleo privado.
    assert SQL.count("cf_reclamar_documento_normalizacion_nucleo(") == 4
    assert "from public.cf_reclamar_documento_normalizacion_nucleo(" in SQL


def test_ordering_oficial_esta_una_sola_vez_en_el_nucleo():
    ordering = "(d.reprocesar_solicitado_at is not null) desc,\n       d.fecha_importacion,\n       d.id"
    assert SQL.count(ordering) == 1
    assert "for update of d skip locked" in SQL.casefold()


def test_rpc_manual_no_admite_parametros_de_preseleccion():
    firma = inspect.signature(RepositorioRuntimeSupabase.reclamar_documento_manual_one_shot)
    assert tuple(firma.parameters) == ("self", "worker_id")
    cabecera = SQL.split(
        "create or replace function public.cf_reclamar_documento_normalizacion_manual_one_shot",
        1,
    )[1].split(")", 1)[0]
    assert all(x not in cabecera for x in ("documento_id", "filename", "sha", "proveedor"))


def test_limite_duro_sigue_siendo_un_documento():
    assert MAX_DOCUMENTOS_POR_EJECUCION == 1
    repo = _RepoMemoria(_docs(3))
    _worker(repo)[0].ejecutar_una_manual()
    assert repo.claims_manual == 1 and len(repo.documentos) == 2


def test_multifactura_desde_un_documento_esta_permitida():
    repo = _RepoMemoria(_docs(1))
    documento = _documento(_factura("F-1", 1, "s1"), _factura("F-2", 2, "s2"))
    assert _worker(repo, documento)[0].ejecutar_una_manual().documentos_reclamados == 1
    assert len(repo.persistidos) == 1


def test_candidato_no_apto_falla_cerrado_y_no_prueba_el_siguiente():
    repo = _RepoMemoria(_docs(2))
    incompleto = {"documento_completo_demostrado": False, "facturas": []}
    resultado = _worker(repo, incompleto)[0].ejecutar_una_manual()
    assert resultado.documentos_reclamados == 0
    assert len(repo.fallos) == 1 and repo.claims_manual == 1 and len(repo.documentos) == 1


def test_lock_se_libera_tras_exito():
    repo = _RepoMemoria(_docs(1))
    _worker(repo)[0].ejecutar_una_manual()
    assert repo.lock is None


def test_lock_se_libera_tras_error():
    repo = _RepoMemoria(_docs(1))
    _worker(repo, {"documento_completo_demostrado": False, "facturas": []})[0].ejecutar_una_manual()
    assert repo.lock is None


def test_idempotencia_incluye_provenance_manual_one_shot():
    keys = []
    for _ in range(2):
        repo = _RepoMemoria(_docs(1))
        _worker(repo)[0].ejecutar_una_manual()
        keys.append(repo.persistidos[0][-1])
    assert keys[0] == keys[1]
    assert keys[0].startswith("normalizacion:d1:MANUAL_ONE_SHOT:")


def test_duplicado_economico_no_crea_factura_en_shadow():
    repo = _RepoMemoria(_docs(1), duplicado=True)
    assert _worker(repo)[0].ejecutar_una_manual().documentos_reclamados == 1
    assert repo.persistidos == []


def test_rita_sigue_bloqueada():
    with pytest.raises(ValueError, match="SOLO_PIO"):
        construir_worker_automatico(
            _normalizador(_RepoMemoria()),
            _Conciliacion(),
            ConfiguracionRuntime(farmacias_habilitadas=("PIO", "RITA")),
        )


def test_luna_sigue_bloqueada():
    with pytest.raises(ValueError, match="LUNA_NO_AUTORIZADA"):
        construir_worker_automatico(
            _normalizador(_RepoMemoria()),
            _Conciliacion(),
            ConfiguracionRuntime(luna_habilitada=True),
        )


def test_manual_no_fuerza_conciliacion():
    repo = _RepoMemoria(_docs(1))
    worker, conciliacion = _worker(repo)
    resultado = worker.ejecutar_una_manual()
    assert conciliacion.llamadas == 0
    assert resultado.facturas_conciliacion_reclamadas == 0


def test_provenance_manual_one_shot_llega_a_persistencia():
    repo = _RepoMemoria(_docs(1))
    resultado = _worker(repo)[0].ejecutar_una_manual()
    assert resultado.modo_ejecucion == "MANUAL_ONE_SHOT"
    assert repo.persistidos[0][-2] == "MANUAL_ONE_SHOT"
    assert "'provenance_ejecucion'" in SQL and "p_disparador" in SQL


def test_ruta_automatica_con_flag_true_conserva_comportamiento():
    repo = _RepoMemoria(_docs(1), auto=True)
    resultado = _worker(
        repo,
        configuracion=ConfiguracionRuntime(normalizacion_automatica=True),
    )[0].ejecutar_una()
    assert resultado.documentos_reclamados == 1
    assert repo.persistidos[0][-2] == "AUTOMATICO"


def test_repositorio_manual_invoca_solo_rpc_explicita():
    cliente = _Cliente()
    RepositorioRuntimeSupabase(cliente).reclamar_documento_manual_one_shot("worker")
    nombre, payload = cliente.calls[0]
    assert nombre == "cf_reclamar_documento_normalizacion_manual_one_shot"
    assert payload == {"p_worker_id": "worker", "p_bloqueo_segundos": 300}


def test_scheduler_no_tiene_ruta_manual():
    textos = "\n".join(
        ruta.read_text(encoding="utf-8", errors="replace")
        for ruta in ROOT.glob("*.bat")
    )
    assert "ejecutar_una_manual" not in textos
    assert "manual_one_shot" not in textos.casefold()
