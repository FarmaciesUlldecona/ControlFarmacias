"""Hito 2AR: clasificacion de fallos, payload del repositorio y contrato estatico de la migracion 17."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.facturas.runtime_supabase.clasificacion_fallos import (
    CLASES_FALLO,
    DEFECTO_DOCUMENTO,
    MOTIVOS_DEFECTO_DOCUMENTO,
    MOTIVOS_NO_SOPORTADO,
    NO_SOPORTADO,
    TRANSITORIO,
    clasificar_fallo,
)
from src.facturas.runtime_supabase.modelos import DocumentoTrabajo
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase


ROOT = Path(__file__).resolve().parents[3]
MIGRACION = ROOT / "sql/migrations/17_cf_replay_y_fallos_no_bloqueantes.sql"
ROLLBACK = ROOT / "sql/migrations/17_cf_replay_y_fallos_no_bloqueantes.rollback.sql"


@pytest.mark.parametrize(("codigo", "detalle", "clase"), [
    ("DocumentoNoAptoManual", "PROVEEDOR_NO_SOPORTADO_MANUAL", NO_SOPORTADO),
    ("DocumentoNoAptoManual", "PROVEEDOR_NO_RECONOCIDO", NO_SOPORTADO),
    ("DocumentoNoAptoManual", "REQUIERE_OCR_O_LUNA_NO_AUTORIZADO", NO_SOPORTADO),
    ("DocumentoNoAptoManual", "ADAPTACION_NO_CERTIFICADA", NO_SOPORTADO),
    ("DocumentoNoAptoManual", "SHA256_NO_COINCIDE", DEFECTO_DOCUMENTO),
    ("DocumentoNoAptoManual", "EXTRACCION_LOCAL_ERROR", DEFECTO_DOCUMENTO),
    ("DocumentoNoAptoManual", "OBJETO_STORAGE_NO_DISPONIBLE:RuntimeError", TRANSITORIO),
    ("ValueError", "NINGUNA_FACTURA_AUTORIZABLE_AUTOMATICAMENTE", DEFECTO_DOCUMENTO),
    ("ValueError", "DOCUMENTO_INCOMPLETO", DEFECTO_DOCUMENTO),
    ("ErrorFarmaciaDocumental", "FARMACIA_DOCUMENTO_CONTRADICTORIA", DEFECTO_DOCUMENTO),
    ("ErrorCompletitudDocumental", "EXTRACCION_INCOMPLETA_REQUIERE_REVISION", DEFECTO_DOCUMENTO),
    ("APIError", "{'message': 'IDEMPOTENCIA_PAYLOAD_DISTINTO'}", DEFECTO_DOCUMENTO),
    ("APIError", "{'message': 'CLAIM_DOCUMENTAL_NO_VALIDO'}", TRANSITORIO),
    ("ConnectionError", "timeout", TRANSITORIO),
    (None, None, TRANSITORIO),
])
def test_clasificacion_de_motivos(codigo, detalle, clase):
    assert clasificar_fallo(codigo, detalle) == clase


def test_clasificacion_conjuntos_disjuntos_y_desconocido_nunca_no_soportado():
    assert not MOTIVOS_NO_SOPORTADO & MOTIVOS_DEFECTO_DOCUMENTO
    assert CLASES_FALLO == {NO_SOPORTADO, DEFECTO_DOCUMENTO, TRANSITORIO}
    assert clasificar_fallo("DocumentoNoAptoManual", "MOTIVO_NUEVO_DESCONOCIDO") == TRANSITORIO


def test_todos_los_motivos_del_compositor_estan_clasificados():
    fuente = (ROOT / "src/facturas/runtime_supabase/compositor_manual.py").read_text(encoding="utf-8")
    motivos = set(re.findall(r'"([A-Z][A-Z0-9_]{5,})"', fuente))
    # No son motivos de fallo: identificadores, codigo de incidencia o errores de composicion.
    motivos -= {"PIO", "MOTOR_LOCAL_AUTORIZADO_MANUAL", "AUTORIZADO", "WORKER_ID_OBLIGATORIO",
                "SOLO_PIO_AUTORIZADA_EN_COMPOSITOR_MANUAL", "PENDIENTE_OCR"}
    # TRANSITORIO documentado en DISENO.md 2AR.
    transitorios = {"OBJETO_STORAGE_NO_DISPONIBLE", "CAMPOS_NO_SOLICITADOS"}
    assert all(clasificar_fallo("DocumentoNoAptoManual", m) == TRANSITORIO for m in transitorios)
    sin_clasificar = motivos - MOTIVOS_NO_SOPORTADO - MOTIVOS_DEFECTO_DOCUMENTO - transitorios
    assert sin_clasificar == set()


class _Cliente:
    def __init__(self):
        self.llamadas = []

    def rpc(self, nombre, payload):
        self.llamadas.append((nombre, payload))
        return self

    def execute(self):
        return self


def test_repositorio_envia_motivo_clasificado():
    cliente = _Cliente()
    documento = DocumentoTrabajo("doc-1", "PIO/x.pdf", "x.pdf", "PIO")
    RepositorioRuntimeSupabase(cliente).fallar_ejecucion(
        documento, "DocumentoNoAptoManual", "PROVEEDOR_NO_SOPORTADO_MANUAL",
        "w", "MANUAL_ONE_SHOT", "normalizacion:doc-1:MANUAL_ONE_SHOT:fallo")
    nombre, payload = cliente.llamadas[0]
    assert nombre == "cf_registrar_fallo_normalizacion"
    assert payload["p_clase_fallo"] == NO_SOPORTADO
    assert set(payload) == {"p_documento_id", "p_worker_id", "p_disparador", "p_idempotency_key",
                            "p_error_codigo", "p_error_detalle", "p_clase_fallo"}


def _sin_cuerpos(sql: str) -> str:
    return re.sub(r"\$\$.*?\$\$", "$$<cuerpo>$$", sql, flags=re.S)


def test_migracion_17_sin_dml_ni_cambio_de_selector():
    sql = MIGRACION.read_text(encoding="utf-8")
    fuera = _sin_cuerpos(sql).lower()
    assert not re.search(r"^\s*(insert|update|delete|truncate)\b", fuera, re.M)
    assert "cf_reclamar_documento_normalizacion" not in sql
    assert "order by" not in fuera
    assert sql.lstrip("-").count("begin;") == 1 and sql.rstrip().endswith("commit;")


def test_rollback_17_documenta_unico_dml():
    sql = ROLLBACK.read_text(encoding="utf-8")
    fuera = _sin_cuerpos(sql).lower()
    sentencias = re.findall(r"^\s*(insert|update|delete|truncate)\b.*", fuera, re.M)
    assert sentencias == ["update"]
    assert "estado_lectura = 'proveedor_no_soportado'" in fuera


def test_migracion_17_generada_reproducible():
    import runpy

    generador = runpy.run_path(str(ROOT / "pruebas/auditoria_2ar/generar_migracion_17.py"))
    assert generador["MIGRACION"] == MIGRACION.read_text(encoding="utf-8")
    assert generador["ROLLBACK_SQL"] == ROLLBACK.read_text(encoding="utf-8")
