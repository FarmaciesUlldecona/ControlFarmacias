"""Hito 2BI: el worker de normalizacion no deja claims huerfanos por Ctrl+C/SystemExit y usa un worker_id
unico por ejecucion. Sin base de datos (repositorio doble)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.facturas.runtime_supabase.worker_normalizacion import WorkerNormalizacion


class _Repo:
    def __init__(self, *, fallo_falla=False):
        self.claims, self.fallos, self.persistidos = [], [], []
        self.fallo_falla = fallo_falla

    def _doc(self, worker_id):
        self.claims.append(worker_id)
        return SimpleNamespace(documento_id="d1", farmacia="PIO", reprocesado_manual=False)

    reclamar_documento = _doc
    reclamar_documento_manual_one_shot = _doc

    def fallar_ejecucion(self, documento, codigo, detalle, worker_id, disparador, clave):
        self.fallos.append((codigo, worker_id, disparador))
        if self.fallo_falla:
            raise ConnectionError("sin red")

    def persistir_normalizacion(self, documento, resultado, resultado_hash, worker_id, disparador, clave):
        self.persistidos.append(worker_id)


def _worker(repo, materializar):
    return WorkerNormalizacion(repositorio=repo, materializar_pdf=materializar, orquestador=None,
                               campos_requeridos=frozenset(), worker_id="cf-base")


def _lanza(excepcion):
    def materializar(documento):
        raise excepcion
    return materializar


@pytest.mark.parametrize("excepcion", [KeyboardInterrupt(), SystemExit(2)])
@pytest.mark.parametrize("ruta", ["ejecutar_una", "ejecutar_una_manual_one_shot"])
def test_interrupcion_registra_el_fallo_y_se_relanza(excepcion, ruta):
    repo = _Repo()
    with pytest.raises(type(excepcion)):
        getattr(_worker(repo, _lanza(excepcion)), ruta)()
    [(codigo, worker_id, disparador)] = repo.fallos
    assert codigo == type(excepcion).__name__ and worker_id == repo.claims[0]
    assert disparador == ("AUTOMATICO" if ruta == "ejecutar_una" else "MANUAL_ONE_SHOT")


def test_si_registrar_el_fallo_falla_la_interrupcion_original_no_se_pierde():
    repo = _Repo(fallo_falla=True)
    with pytest.raises(KeyboardInterrupt):
        _worker(repo, _lanza(KeyboardInterrupt())).ejecutar_una_manual_one_shot()
    assert len(repo.fallos) == 1


def test_una_excepcion_normal_sigue_igual():
    repo = _Repo()
    assert _worker(repo, _lanza(ValueError("pdf"))).ejecutar_una_manual_one_shot() is False
    assert [c for c, _, _ in repo.fallos] == ["ValueError"]


def test_worker_id_unico_por_ejecucion_y_el_mismo_en_toda_la_ejecucion():
    repo = _Repo()
    worker = _worker(repo, _lanza(ValueError("x")))
    worker.ejecutar_una_manual_one_shot()
    worker.ejecutar_una_manual_one_shot()
    primero, segundo = repo.claims
    assert primero != segundo and all(c.startswith("cf-base#") for c in repo.claims)
    assert [w for _, w, _ in repo.fallos] == [primero, segundo]
