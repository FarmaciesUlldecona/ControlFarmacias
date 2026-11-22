"""Migracion 37 (DECISIONES DE PIO D1-D7, pruebas/auditoria_37/DISENO.md): tests unitarios sin base de datos.

- Clasificacion de §2.1: listas A (extraccion) y B (identidad de farmacia) -> DEFECTO_DOCUMENTO; lista C
  (almacenamiento) -> TRANSITORIO; motivo desconocido -> TRANSITORIO.
- El repositorio usa el 8.o parametro (``p_lector``) SOLO si detecta la 37; sin ella, o si la deteccion falla, la
  llamada de 7 parametros de siempre.
- El worker guarda el lector autorizado de su compositor con el layout reconocido (null antes de reconocerlo) y, sin
  lector autorizado, llama como antes.
- Deteccion READ_ONLY de la 37, prediccion de la serie 2BJ y motivo en el para_revisar de la noche.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.facturas.motor_local.adaptadores.alliance import AdaptadorAlliance
from src.facturas.runtime_supabase import clasificacion_fallos as cf
from src.facturas.runtime_supabase.compositor_automatico import (
    AUTORIDAD_COMPOSITOR_AUTOMATICO, lector_autorizado_automatico)
from src.facturas.runtime_supabase.compositor_manual import lector_autorizado_manual
from src.facturas.runtime_supabase.lectura_readonly import FIRMA_FALLO_37, SQL_MIGRACION_37, defectos_37_en_bd
from src.facturas.runtime_supabase.modelos import DocumentoTrabajo, PasoExtraccion, ResultadoExtraccionProductiva
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase
from src.facturas.runtime_supabase.worker_normalizacion import WorkerNormalizacion

ROOT = Path(__file__).resolve().parents[3]

LISTA_A = ("EXTRACCION_LOCAL_ERROR", "EXTRACCION_INCOMPLETA_REQUIERE_REVISION", "CAMPOS_PENDIENTES_TRAS_EXTRACCION",
           "DOCUMENTO_NORMALIZADO_AUSENTE", "DOCUMENTO_INCOMPLETO", "COBERTURA_DOCUMENTAL_INCOMPLETA",
           "INVENTARIO_DOCUMENTAL_INVALIDO", "INVENTARIO_RELECTURA_INCOMPATIBLE", "SEGMENTO_DUPLICADO_O_AUSENTE",
           "SEGMENTOS_SOLAPADOS", "RANGO_FACTURA_INVALIDO", "EVIDENCIA_FUERA_DE_FACTURA",
           "SELECCION_NO_PERTENECE_AL_DOCUMENTO", "PROVENANCE_INCOMPLETA",
           "NINGUNA_FACTURA_AUTORIZABLE_AUTOMATICAMENTE")
LISTA_B = ("FARMACIA_DOCUMENTO_NO_DEMOSTRABLE", "FARMACIA_DOCUMENTO_CONTRADICTORIA")
LISTA_C = ("SHA256_NO_COINCIDE", "SHA256_REGISTRADO_INVALIDO", "OBJETO_STORAGE_VACIO",
           "DOCUMENTO_RECLAMADO_NO_LOCALIZADO", "RUTA_STORAGE_NO_COINCIDE_CON_CLAIM", "RUTA_STORAGE_NO_SEGURA")


# --------------------------------------------------------------------------- clasificacion (§2.1, D5)

def test_listas_de_la_decision_d5():
    assert cf.MOTIVOS_DEFECTO_DOCUMENTO == frozenset(LISTA_A + LISTA_B)
    assert cf.MOTIVOS_ALMACENAMIENTO == frozenset(LISTA_C)
    assert len(LISTA_A) == 15 and len(LISTA_B) == 2 and len(LISTA_C) == 6
    assert not cf.MOTIVOS_DEFECTO_DOCUMENTO & cf.MOTIVOS_ALMACENAMIENTO
    assert not (cf.MOTIVOS_DEFECTO_DOCUMENTO | cf.MOTIVOS_ALMACENAMIENTO) & cf.MOTIVOS_NO_SOPORTADO
    assert cf.CODIGOS_DEFECTO_DOCUMENTO == {"ErrorCompletitudDocumental", "ErrorFarmaciaDocumental"}


@pytest.mark.parametrize("motivo", LISTA_A + LISTA_B)
def test_extraccion_e_identidad_de_farmacia_son_defecto(motivo):
    assert cf.clasificar_fallo("DocumentoNoAptoManual", motivo) == cf.DEFECTO_DOCUMENTO
    assert cf.clasificar_fallo("ValueError", f"{motivo}: detalle") == cf.DEFECTO_DOCUMENTO


@pytest.mark.parametrize("motivo", LISTA_C)
def test_almacenamiento_es_transitorio(motivo):
    assert cf.clasificar_fallo("DocumentoNoAptoManual", motivo) == cf.TRANSITORIO
    assert cf.clasificar_fallo("DocumentoNoAptoManual", f"{motivo}: esperado != real") == cf.TRANSITORIO


@pytest.mark.parametrize("codigo", ["ErrorCompletitudDocumental", "ErrorFarmaciaDocumental"])
def test_codigos_de_defecto(codigo):
    assert cf.clasificar_fallo(codigo, "texto libre") == cf.DEFECTO_DOCUMENTO


@pytest.mark.parametrize("codigo, detalle", [
    ("RuntimeError", "MOTIVO_NUEVO_QUE_NADIE_CONOCE"), ("ConnectionError", "timeout"), (None, None),
    ("RuntimeError", "IDEMPOTENCIA_PAYLOAD_DISTINTO"), ("KeyboardInterrupt", "KeyboardInterrupt")])
def test_desconocido_sigue_siendo_transitorio(codigo, detalle):
    assert cf.clasificar_fallo(codigo, detalle) == cf.TRANSITORIO


def test_relectura_incompatible_dentro_del_texto_y_no_soportado_sin_cambios():
    assert cf.clasificar_fallo("ValueError", "x INVENTARIO_RELECTURA_INCOMPATIBLE y") == cf.DEFECTO_DOCUMENTO
    assert cf.clasificar_fallo("DocumentoNoAptoManual", "PROVEEDOR_NO_SOPORTADO_AUTOMATICO") == cf.NO_SOPORTADO


def test_la_conciliacion_no_cambia():
    assert cf.clasificar_fallo_conciliacion("x", "SHA256_NO_COINCIDE") == cf.TRANSITORIO
    assert cf.clasificar_fallo_conciliacion("x", "FARMACIA_DOCUMENTO_NO_DEMOSTRABLE") == cf.DEFECTO_DOCUMENTO


# --------------------------------------------------------------------------- repositorio: 8.o parametro solo con la 37

class _Cliente:
    def __init__(self):
        self.llamadas = []

    def rpc(self, nombre, payload):
        self.llamadas.append((nombre, payload))
        return self

    def execute(self):
        return None


DOC = DocumentoTrabajo(documento_id="d1", archivo_ruta="PIO/x.pdf", archivo_nombre="x.pdf", farmacia="PIO")
LECTOR = {"adaptador": "alliance-local", "version_adaptador": "1.3.1", "layout": None}
CLAVES_17 = {"p_documento_id", "p_worker_id", "p_disparador", "p_idempotency_key", "p_error_codigo",
             "p_error_detalle", "p_clase_fallo"}


def _fallo(deteccion, **kwargs):
    cliente = _Cliente()
    RepositorioRuntimeSupabase(cliente, defectos_37=deteccion).fallar_ejecucion(
        DOC, "DocumentoNoAptoManual", "EXTRACCION_LOCAL_ERROR", "w#1", "AUTOMATICO", "k", **kwargs)
    [(nombre, payload)] = cliente.llamadas
    assert nombre == "cf_registrar_fallo_normalizacion"
    return payload


def _rota():
    raise RuntimeError("sin conexion")


@pytest.mark.parametrize("deteccion", [None, lambda: False, _rota, lambda: "t", lambda: 1])
def test_sin_la_37_la_llamada_de_7_parametros(deteccion):
    payload = _fallo(deteccion, lector=LECTOR)
    assert set(payload) == CLAVES_17
    assert payload["p_clase_fallo"] == cf.DEFECTO_DOCUMENTO


def test_con_la_37_el_octavo_parametro_con_el_lector():
    payload = _fallo(lambda: True, lector=LECTOR)
    assert set(payload) == CLAVES_17 | {"p_lector"}
    assert payload["p_lector"] == LECTOR and payload["p_lector"] is not LECTOR


def test_con_la_37_y_sin_lector_el_octavo_parametro_va_a_null():
    assert _fallo(lambda: True)["p_lector"] is None


def test_deteccion_del_repositorio():
    assert RepositorioRuntimeSupabase(None).defectos_37() is False
    assert RepositorioRuntimeSupabase(None, defectos_37=_rota).defectos_37() is False
    assert RepositorioRuntimeSupabase(None, defectos_37=lambda: True).defectos_37() is True


# --------------------------------------------------------------------------- worker: lector autorizado + layout

class _Repositorio:
    def __init__(self):
        self.fallos = []

    def reclamar_documento(self, worker_id):
        return DOC

    def fallar_ejecucion(self, documento, codigo, detalle, worker_id, disparador, clave, **kwargs):
        self.fallos.append((codigo, detalle, kwargs))


class _Orquestador:
    def __init__(self, resultado=None, error=None):
        self.resultado, self.error = resultado, error

    def extraer(self, ruta, campos):
        if self.error:
            raise self.error
        return self.resultado


def _resultado(*layouts):
    pasos = tuple(PasoExtraccion(etapa="E", campos_solicitados=(), campos_resueltos=(),
                                 provenance={"motivo": "DOCUMENTO_INCOMPLETO", **({"layout": l} if l else {})})
                  for l in layouts)
    return ResultadoExtraccionProductiva(valores={}, campos_pendientes=("x",), pasos=pasos, uso_luna=None,
                                         incidencias=())


def _ensamblar_que_falla(_documento, resultado):
    raise ValueError("DOCUMENTO_INCOMPLETO")


def _worker(orquestador, lector_autorizado=None):
    repositorio = _Repositorio()
    worker = WorkerNormalizacion(repositorio=repositorio, materializar_pdf=lambda d: Path("x.pdf"),
                                 orquestador=orquestador, campos_requeridos=frozenset({"x"}), worker_id="w",
                                 ensamblar_documento=_ensamblar_que_falla, lector_autorizado=lector_autorizado)
    return worker, repositorio


AUTORIZADO = {"adaptador": "alliance-local", "version_adaptador": "1.3.1"}


def test_el_worker_guarda_el_lector_autorizado_con_el_layout_reconocido():
    worker, repositorio = _worker(_Orquestador(_resultado(None, "alliance-local")), AUTORIZADO)
    assert worker.ejecutar_una() is False
    [(_, detalle, kwargs)] = repositorio.fallos
    assert detalle == "DOCUMENTO_INCOMPLETO"
    assert kwargs == {"lector": {**AUTORIZADO, "layout": "alliance-local"}}


def test_el_worker_sin_layout_reconocido_guarda_layout_null():
    worker, repositorio = _worker(_Orquestador(_resultado(None)), AUTORIZADO)
    worker.ejecutar_una()
    assert repositorio.fallos[0][2] == {"lector": {**AUTORIZADO, "layout": None}}


def test_el_worker_que_falla_antes_de_extraer_guarda_layout_null():
    worker, repositorio = _worker(_Orquestador(error=RuntimeError("SHA256_NO_COINCIDE")), AUTORIZADO)
    worker.ejecutar_una()
    assert repositorio.fallos[0][2] == {"lector": {**AUTORIZADO, "layout": None}}


def test_el_worker_sin_lector_autorizado_llama_como_antes():
    worker, repositorio = _worker(_Orquestador(_resultado("alliance-local")))
    worker.ejecutar_una()
    assert repositorio.fallos[0][2] == {}


def test_lectores_autorizados_de_los_compositores():
    assert lector_autorizado_automatico() == {"adaptador": "alliance-local", "version_adaptador": "1.3.1"}
    assert tuple(lector_autorizado_automatico().values()) in AUTORIDAD_COMPOSITOR_AUTOMATICO.values()
    assert lector_autorizado_manual() == {"adaptador": AdaptadorAlliance.id, "version_adaptador": AdaptadorAlliance.version}


# --------------------------------------------------------------------------- deteccion READ_ONLY

class _Lector:
    def __init__(self, valor):
        self.valor_devuelto, self.consultas = valor, []

    def valor(self, sql, params=None):
        self.consultas.append(sql)
        return self.valor_devuelto


@pytest.mark.parametrize("valor, esperado", [(True, True), (False, False), (None, False), ("t", False)])
def test_deteccion_de_la_37_solo_con_catalogo(valor, esperado):
    lector = _Lector(valor)
    assert defectos_37_en_bd(lector) is esperado
    assert lector.consultas == [SQL_MIGRACION_37]
    assert SQL_MIGRACION_37.lstrip().startswith("select") and "to_regprocedure" in SQL_MIGRACION_37
    assert FIRMA_FALLO_37.endswith("text,jsonb)")


# --------------------------------------------------------------------------- serie 2BJ

def _serie():
    spec = importlib.util.spec_from_file_location("serie_2bj_37", ROOT / "pruebas/auditoria_2bj/serie_normalizacion.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_serie_2bj_con_la_37_el_defecto_pasa_a_revision_al_primer_fallo():
    m = _serie()
    for antes in (0, 1, 2):
        assert m.resultado_esperado({"clase": "DEFECTO"}, antes, 4, True) == {
            "estado_lectura": "REVISION", "ultima_clase_fallo": cf.DEFECTO_DOCUMENTO, "intentos": antes + 1,
            "facturas": []}
    assert m.resultado_esperado({"clase": "DEFECTO"}, 0, 4)["estado_lectura"] == "ERROR"
    assert m.resultado_esperado({"clase": "NO_SOPORTADO"}, 1, 4, True)["estado_lectura"] == "PROVEEDOR_NO_SOPORTADO"


def test_serie_2bj_el_almacenamiento_queda_sin_prediccion():
    m = _serie()
    p = m.prediccion_desde_analisis({"etapa_detencion": "EXTRACCION", "motivo": "SHA256_NO_COINCIDE"})
    assert p["clase"] == "SIN_PREDICCION"
    assert m.prediccion_desde_analisis({"etapa_detencion": "EXTRACCION_MOTOR"}) == {
        "clase": "DEFECTO", "motivo": "EXTRACCION_LOCAL_ERROR"}


# --------------------------------------------------------------------------- noche: motivo en para_revisar

@pytest.mark.parametrize("ejecucion, motivo", [
    ({"error_codigo": "DocumentoNoAptoManual", "error_detalle": "EXTRACCION_LOCAL_ERROR"}, "EXTRACCION_LOCAL_ERROR"),
    ({"error_detalle": "SHA256_NO_COINCIDE: a != b"}, "SHA256_NO_COINCIDE"),
    ({"error_codigo": "X"}, None), ({}, None), ({"error_detalle": "  "}, None)])
def test_motivo_del_defecto_en_la_noche(ejecucion, motivo):
    from src.facturas.runtime_supabase.noche_automatica import motivo_defecto

    assert motivo_defecto(ejecucion) == motivo
