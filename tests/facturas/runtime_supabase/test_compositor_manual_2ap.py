"""Hito 2AP: compositor productivo del worker manual, certificado en local.

Usa PDFs reales copiados de FACTURES PIO (excluidos de Git) con Storage y
Supabase simulados en memoria. Ningun test se conecta a produccion.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.facturas.motor_local.autoridad import AUTORIDADES_EXTRACTORES_LOCALES
from src.facturas.motor_local.catalogo import ProveedorLocal
from src.facturas.runtime_supabase import compositor_manual as cm
from src.facturas.runtime_supabase.compositor_manual import (
    AUTORIDAD_COMPOSITOR_MANUAL,
    CAMPO_DOCUMENTO,
    CAMPOS_REQUERIDOS_MANUAL,
    LAYOUTS_CON_PUENTE_CERTIFICADO,
    DocumentoNoAptoManual,
    ExtractorDocumentalAutorizado,
    MaterializadorStoragePrivado,
    autoridad_manual_habilitada,
    construir_worker_manual_productivo,
    ensamblar_documento_manual,
)
from src.facturas.runtime_supabase.extraccion_productiva import (
    OrquestadorExtraccionProductiva,
)
from src.facturas.runtime_supabase.modelos import ConfiguracionRuntime, DocumentoTrabajo
from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "pruebas/facturas/documentos/fixtures_2ap"
ALLIANCE = FIXTURES / "alliance_apto_multifactura.pdf"
HEFAME = FIXTURES / "hefame_no_autorizado.pdf"
NO_RECONOCIDO = FIXTURES / "layout_no_reconocido.pdf"
PENDIENTE_OCR = FIXTURES / "pendiente_ocr.pdf"
ERROR_MOTOR = FIXTURES / "error_motor_local.pdf"
NUMEROS_ALLIANCE = {"08011303", "08011304", "08011305"}
CONFIG = ConfiguracionRuntime()


def _pdf(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"fixture real local ausente: {path}")
    return path


def _sha(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


# --------------------------------------------------------------------------
# Supabase y Storage simulados
# --------------------------------------------------------------------------


class _Respuesta:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class _Consulta:
    def __init__(self, supabase, tabla):
        self.supabase = supabase
        self.tabla = tabla
        self.filtros = {}

    def select(self, _columnas):
        return self

    def eq(self, columna, valor):
        self.filtros[columna] = valor
        return self

    def limit(self, _n):
        return self

    def execute(self):
        assert self.tabla == "documentos_facturas"
        self.supabase.lecturas.append(dict(self.filtros))
        filas = [
            {"id": d["id"], "archivo_ruta": d["archivo_ruta"], "archivo_hash": d["archivo_hash"]}
            for d in self.supabase.documentos
            if all(d.get(k) == v for k, v in self.filtros.items())
        ]
        return _Respuesta(filas)


class _Bucket:
    def __init__(self, supabase, nombre):
        self.supabase = supabase
        self.nombre = nombre

    def download(self, ruta):
        self.supabase.descargas.append((self.nombre, ruta))
        if (self.nombre, ruta) not in self.supabase.objetos:
            raise RuntimeError("Object not found")
        return self.supabase.objetos[(self.nombre, ruta)]


class _Storage:
    def __init__(self, supabase):
        self.supabase = supabase

    def from_(self, nombre):
        return _Bucket(self.supabase, nombre)


class _SupabaseMemoria:
    """Simula claim manual, persistencia y fallo alineados con la migracion 17.

    R1: el replay libera el claim y restaura el estado final. R2/R3: el fallo se
    clasifica (PROVEEDOR_NO_SOPORTADO, ERROR con backoff o REVISION al maximo).
    """

    MAX_INTENTOS = 4

    def __init__(self):
        self.documentos = []
        self.objetos = {}
        self.storage = _Storage(self)
        self.rpcs = []
        self.lecturas = []
        self.descargas = []
        self.locks = {}
        self.facturas = {}
        self.idempotencia = {}
        self.fallos = []

    def registrar(self, documento_id, pdf: Path, *, hash_registrado=None, subir=True):
        contenido = pdf.read_bytes()
        ruta = f"PIO/2026/{documento_id}.pdf"
        self.documentos.append({
            "id": documento_id,
            "archivo_ruta": ruta,
            "archivo_nombre": "no-es-evidencia.pdf",
            "archivo_hash": hash_registrado or _sha(contenido),
            "farmacia": "PIO",
            "estado": "PENDIENTE",
            "intentos_fallo": 0,
            "backoff_futuro": False,
        })
        if subir:
            self.objetos[("facturas-pdf", ruta)] = contenido
        return ruta

    def table(self, tabla):
        return _Consulta(self, tabla)

    def rpc(self, nombre, payload):
        self.rpcs.append((nombre, copy.deepcopy(payload)))
        return _Respuesta(getattr(self, "_" + nombre)(payload))

    def _cf_reclamar_documento_normalizacion_manual_one_shot(self, payload):
        for doc in self.documentos:
            if (doc["estado"] in {"PENDIENTE", "ERROR"} and not doc.get("backoff_futuro")
                    and doc["id"] not in self.locks):
                self.locks[doc["id"]] = payload["p_worker_id"]
                doc["estado"] = "NORMALIZANDO"
                return [dict(doc)]
        return []

    def _cf_reclamar_documento_normalizacion(self, _payload):
        raise AssertionError("La ruta automatica no debe usarse")

    def _cf_persistir_documento_multifactura(self, payload):
        documento_id = payload["p_documento_id"]
        assert self.locks.get(documento_id) == payload["p_worker_id"]
        clave = payload["p_idempotency_key"]
        documento = next(d for d in self.documentos if d["id"] == documento_id)
        if clave in self.idempotencia:
            # R1 (migracion 17): el replay libera el claim y restaura el estado final.
            del self.locks[documento_id]
            documento["estado"] = self.idempotencia[clave]["estado"]
            return self.idempotencia[clave]
        creadas = []
        for factura in payload["p_resultado"]["facturas"]:
            segmento = factura["provenance"]["segment_id"]
            identidad = factura["identidad_economica_clave"]
            if segmento in payload["p_segmentos_autorizados"] and identidad not in self.facturas:
                self.facturas[identidad] = {
                    "documento_id": documento_id,
                    "numero": factura["numero_factura"]["valor"],
                    "total": factura["totales"]["total"]["valor"],
                    "disparador": payload["p_disparador"],
                }
                creadas.append(identidad)
        completa = all(
            f["provenance"]["segment_id"] in payload["p_segmentos_autorizados"]
            for f in payload["p_resultado"]["facturas"]
        )
        estado = "NORMALIZADA" if completa else "REVISION"
        self.idempotencia[clave] = {"creadas": creadas, "estado": estado}
        del self.locks[documento_id]
        documento["estado"] = estado
        documento["intentos_fallo"] = 0
        return {"creadas": creadas}

    def _cf_registrar_fallo_normalizacion(self, payload):
        documento_id = payload["p_documento_id"]
        assert self.locks.get(documento_id) == payload["p_worker_id"]
        self.fallos.append(payload)
        del self.locks[documento_id]
        documento = next(d for d in self.documentos if d["id"] == documento_id)
        if payload["p_clase_fallo"] == "NO_SOPORTADO":
            documento["estado"] = "PROVEEDOR_NO_SOPORTADO"
        else:
            documento["intentos_fallo"] += 1
            maximo = documento["intentos_fallo"] >= self.MAX_INTENTOS
            documento["estado"] = "REVISION" if maximo else "ERROR"
            documento["backoff_futuro"] = not maximo
        return None

    def reabrir(self, documento_id):
        """Equivale a cf_solicitar_reprocesado: vuelve a PENDIENTE y reinicia intentos."""
        documento = next(d for d in self.documentos if d["id"] == documento_id)
        documento.update(estado="PENDIENTE", intentos_fallo=0, backoff_futuro=False)

    def nombres_rpc(self):
        return [nombre for nombre, _ in self.rpcs]


def _worker(supabase, tmp_path, nombre="w"):
    return construir_worker_manual_productivo(
        supabase, CONFIG, f"manual-2ap-{nombre}", tmp_path / nombre
    )


def _doc(documento_id="doc-1", ruta="PIO/2026/doc-1.pdf"):
    return DocumentoTrabajo(documento_id, ruta, "no-es-evidencia.pdf", "PIO")


@pytest.fixture(scope="module")
def normalizado_alliance():
    resultado = ExtractorDocumentalAutorizado().extraer(_pdf(ALLIANCE), CAMPOS_REQUERIDOS_MANUAL)
    return resultado.valores[CAMPO_DOCUMENTO]


# --------------------------------------------------------------------------
# materializar_pdf
# --------------------------------------------------------------------------


def test_materializar_sha_correcto_descarga_solo_la_ruta_reclamada(tmp_path):
    supabase = _SupabaseMemoria()
    ruta = supabase.registrar("doc-1", _pdf(ALLIANCE))
    destino = MaterializadorStoragePrivado(supabase, tmp_path)(_doc(ruta=ruta))
    assert destino == tmp_path / "doc-1.pdf"
    assert destino.read_bytes() == ALLIANCE.read_bytes()
    assert supabase.descargas == [("facturas-pdf", ruta)]
    assert supabase.lecturas == [{"id": "doc-1"}]


def test_materializar_sha_incorrecto_falla_cerrado(tmp_path):
    supabase = _SupabaseMemoria()
    ruta = supabase.registrar("doc-1", _pdf(ALLIANCE), hash_registrado="0" * 64)
    with pytest.raises(DocumentoNoAptoManual, match="SHA256_NO_COINCIDE"):
        MaterializadorStoragePrivado(supabase, tmp_path)(_doc(ruta=ruta))
    assert not (tmp_path / "doc-1.pdf").exists()


def test_materializar_objeto_inexistente_falla_cerrado(tmp_path):
    supabase = _SupabaseMemoria()
    ruta = supabase.registrar("doc-1", _pdf(ALLIANCE), subir=False)
    with pytest.raises(DocumentoNoAptoManual, match="OBJETO_STORAGE_NO_DISPONIBLE"):
        MaterializadorStoragePrivado(supabase, tmp_path)(_doc(ruta=ruta))


def test_materializar_no_acepta_ruta_distinta_ni_documento_ausente(tmp_path):
    supabase = _SupabaseMemoria()
    supabase.registrar("doc-1", _pdf(ALLIANCE))
    with pytest.raises(DocumentoNoAptoManual, match="RUTA_STORAGE_NO_COINCIDE_CON_CLAIM"):
        MaterializadorStoragePrivado(supabase, tmp_path)(_doc(ruta="PIO/otro.pdf"))
    with pytest.raises(DocumentoNoAptoManual, match="DOCUMENTO_RECLAMADO_NO_LOCALIZADO"):
        MaterializadorStoragePrivado(supabase, tmp_path)(_doc("doc-x"))
    assert supabase.descargas == []


def test_materializar_rechaza_ruta_insegura(tmp_path):
    supabase = _SupabaseMemoria()
    supabase.registrar("doc-1", _pdf(ALLIANCE))
    supabase.documentos[0]["archivo_ruta"] = "PIO/../RITA/x.pdf"
    with pytest.raises(DocumentoNoAptoManual, match="RUTA_STORAGE_NO_SEGURA"):
        MaterializadorStoragePrivado(supabase, tmp_path)(_doc(ruta="PIO/../RITA/x.pdf"))
    assert supabase.descargas == []


# --------------------------------------------------------------------------
# Extractor y autoridad por proveedor
# --------------------------------------------------------------------------


def test_extractor_documento_apto_multifactura(normalizado_alliance):
    facturas = normalizado_alliance["facturas"]
    assert normalizado_alliance["documento_completo_demostrado"] is True
    assert {f["numero_factura"]["valor"] for f in facturas} == NUMEROS_ALLIANCE
    for factura in facturas:
        assert factura["factura_completa_demostrada"] is True
        assert factura["estado_validacion"] in {"VALIDADA", "VALIDADA_CON_INCIDENCIAS"}
        assert factura["identidad_economica_clave"]
        assert factura["destinatario"]["nif"]["valor"] == "40901058C"


def test_extractor_no_usa_nombre_de_archivo(tmp_path, normalizado_alliance):
    copia = tmp_path / "HEFAME COFARES RITA.pdf"
    copia.write_bytes(_pdf(ALLIANCE).read_bytes())
    resultado = ExtractorDocumentalAutorizado().extraer(copia, CAMPOS_REQUERIDOS_MANUAL)
    assert resultado.provenance["layout"] == "alliance-local"
    assert resultado.valores[CAMPO_DOCUMENTO] == normalizado_alliance


def _truncar(origen: Path, destino: Path, conservar: list[int]) -> Path:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(origen))
    for indice in sorted(set(range(len(pdf))) - set(conservar), reverse=True):
        pdf.del_page(indice)
    pdf.save(str(destino))
    pdf.close()
    return destino


def test_extractor_documento_incompleto_no_autoriza_factura_truncada(tmp_path):
    pdf = _truncar(_pdf(ALLIANCE), tmp_path / "truncado.pdf", list(range(8)))
    resultado = ExtractorDocumentalAutorizado().extraer(pdf, CAMPOS_REQUERIDOS_MANUAL)
    facturas = {f["numero_factura"]["valor"]: f for f in resultado.valores[CAMPO_DOCUMENTO]["facturas"]}
    assert facturas["08011305"]["factura_completa_demostrada"] is False
    cliente = _SupabaseMemoria()
    cliente.locks["doc-1"] = "w"
    cliente.documentos.append({"id": "doc-1"})
    RepositorioRuntimeSupabase(cliente).persistir_documento_automatico(
        _doc(), _resultado(resultado.valores[CAMPO_DOCUMENTO]), "h", "w", "MANUAL_ONE_SHOT", "k",
    )
    nombre, payload = cliente.rpcs[-1]
    autorizados = set(payload["p_segmentos_autorizados"])
    assert facturas["08011305"]["provenance"]["segment_id"] not in autorizados
    assert len(payload["p_resultado"]["facturas"]) == 3


def test_extractor_documento_incompleto_monofactura_falla_cerrado(tmp_path):
    pdf = _truncar(_pdf(ALLIANCE), tmp_path / "factura_sin_ultima_pagina.pdf", [0, 1])
    resultado = ExtractorDocumentalAutorizado().extraer(pdf, CAMPOS_REQUERIDOS_MANUAL)
    documento = resultado.valores[CAMPO_DOCUMENTO]
    assert [f["factura_completa_demostrada"] for f in documento["facturas"]] == [False]
    with pytest.raises(ValueError, match="NINGUNA_FACTURA_AUTORIZABLE_AUTOMATICAMENTE"):
        RepositorioRuntimeSupabase(_SupabaseMemoria()).persistir_documento_automatico(
            _doc(), _resultado(documento), "h", "w", "MANUAL_ONE_SHOT", "k",
        )


def _resultado(documento):
    from src.facturas.runtime_supabase.modelos import ResultadoExtraccionProductiva

    return ResultadoExtraccionProductiva({}, (), (), None, (), documento_normalizado=documento)


def test_farmacia_contradictoria_falla_cerrado(normalizado_alliance):
    documento = copy.deepcopy(normalizado_alliance)
    for factura in documento["facturas"]:
        nif = factura["destinatario"]["nif"]
        nif.update(valor="B00000000", literal="B00000000")
        for evidencia in nif["evidencia"]:
            evidencia["literal"] = "B00000000"
    with pytest.raises(ValueError):
        RepositorioRuntimeSupabase(_SupabaseMemoria()).persistir_documento_automatico(
            _doc(), _resultado(documento), "h", "w", "MANUAL_ONE_SHOT", "k",
        )


def test_identidad_economica_no_demostrada_falla_cerrado(normalizado_alliance):
    documento = copy.deepcopy(normalizado_alliance)
    for factura in documento["facturas"]:
        factura["numero_factura"]["evidencia"] = []
    cliente = _SupabaseMemoria()
    with pytest.raises(ValueError, match="NINGUNA_FACTURA_AUTORIZABLE_AUTOMATICAMENTE"):
        RepositorioRuntimeSupabase(cliente).persistir_documento_automatico(
            _doc(), _resultado(documento), "h", "w", "MANUAL_ONE_SHOT", "k",
        )
    assert cliente.rpcs == []


def test_autoridad_manual_solo_alliance_y_registro_global_intacto():
    assert dict(AUTORIDAD_COMPOSITOR_MANUAL) == {ProveedorLocal.ALLIANCE: "alliance-local"}
    assert set(AUTORIDAD_COMPOSITOR_MANUAL.values()) <= LAYOUTS_CON_PUENTE_CERTIFICADO
    assert autoridad_manual_habilitada("alliance-local") is True
    for layout in ("hefame-local", "cofares-local", "fedefarma-local", None, "desconocido"):
        assert autoridad_manual_habilitada(layout) is False
    assert all(not a.habilitada for a in AUTORIDADES_EXTRACTORES_LOCALES.values())
    with pytest.raises(TypeError):
        AUTORIDAD_COMPOSITOR_MANUAL[ProveedorLocal.HEFAME] = "hefame-local"  # type: ignore[index]


def test_autoridad_sin_puente_certificado_no_se_concede(monkeypatch):
    from types import MappingProxyType

    monkeypatch.setattr(cm, "AUTORIDAD_COMPOSITOR_MANUAL", MappingProxyType({
        ProveedorLocal.ALLIANCE: "alliance-local", ProveedorLocal.HEFAME: "hefame-local",
    }))
    assert cm.autoridad_manual_habilitada("hefame-local") is False


@pytest.mark.parametrize(("pdf", "motivo"), [
    (HEFAME, "PROVEEDOR_NO_SOPORTADO_MANUAL"),
    (NO_RECONOCIDO, "PROVEEDOR_NO_RECONOCIDO"),
    (PENDIENTE_OCR, "REQUIERE_OCR_O_LUNA_NO_AUTORIZADO"),
    (ERROR_MOTOR, "EXTRACCION_LOCAL_ERROR"),
])
def test_proveedor_no_habilitado_falla_cerrado(pdf, motivo):
    resultado = ExtractorDocumentalAutorizado().extraer(_pdf(pdf), CAMPOS_REQUERIDOS_MANUAL)
    assert dict(resultado.valores) == {}
    assert resultado.provenance["motivo"] == motivo


# --------------------------------------------------------------------------
# Ensamblado, Luna y composicion
# --------------------------------------------------------------------------


def test_ensamblado_valido_para_persistencia_oficial(normalizado_alliance):
    cliente = _SupabaseMemoria()
    cliente.documentos.append({"id": "doc-1"})
    cliente.locks["doc-1"] = "w"
    resultado = OrquestadorExtraccionProductiva(
        extractor_especifico=_Fija(normalizado_alliance),
        extractor_generico_local=None, extractor_ocr_local=None, extractor_luna=None,
    ).extraer(Path("x.pdf"), CAMPOS_REQUERIDOS_MANUAL)
    documento = ensamblar_documento_manual(_doc(), resultado)
    RepositorioRuntimeSupabase(cliente).persistir_documento_automatico(
        _doc(), _resultado(documento), "h", "w", "MANUAL_ONE_SHOT", "k",
    )
    nombre, payload = cliente.rpcs[-1]
    assert nombre == "cf_persistir_documento_multifactura"
    assert payload["p_disparador"] == "MANUAL_ONE_SHOT"
    assert len(payload["p_segmentos_autorizados"]) == 3


class _Fija:
    codigo = "FIJA"

    def __init__(self, documento):
        self.documento = documento

    def extraer(self, _ruta, _pendientes):
        from src.facturas.runtime_supabase.modelos import ResultadoEtapa

        return ResultadoEtapa(valores={"proveedor_layout": "alliance-local", CAMPO_DOCUMENTO: self.documento})


class _LunaEspia:
    codigo = "LUNA"
    llamadas = 0

    def extraer_campos(self, *_args):
        type(self).llamadas += 1
        raise AssertionError("Luna no debe invocarse")


def test_documento_que_requeriria_luna_falla_cerrado_sin_invocarla():
    _LunaEspia.llamadas = 0
    resultado = OrquestadorExtraccionProductiva(
        extractor_especifico=ExtractorDocumentalAutorizado(),
        extractor_generico_local=None, extractor_ocr_local=None,
        extractor_luna=_LunaEspia(),
    ).extraer(_pdf(PENDIENTE_OCR), CAMPOS_REQUERIDOS_MANUAL)
    assert _LunaEspia.llamadas == 0
    assert resultado.uso_luna is None
    assert [i.codigo for i in resultado.incidencias] == ["CAMPOS_PENDIENTES_TRAS_EXTRACCION"]
    with pytest.raises(DocumentoNoAptoManual, match="REQUIERE_OCR_O_LUNA_NO_AUTORIZADO"):
        ensamblar_documento_manual(_doc(), resultado)


def test_compositor_rechaza_luna_y_farmacias_distintas_de_pio(tmp_path):
    with pytest.raises(ValueError, match="LUNA"):
        construir_worker_manual_productivo(
            _SupabaseMemoria(), ConfiguracionRuntime(luna_habilitada=True), "w", tmp_path)
    with pytest.raises(ValueError, match="SOLO_PIO"):
        construir_worker_manual_productivo(
            _SupabaseMemoria(), ConfiguracionRuntime(farmacias_habilitadas=("PIO", "RITA")), "w", tmp_path)


def test_compositor_sin_centinelas_shadow_ni_luna(tmp_path):
    worker = _worker(_SupabaseMemoria(), tmp_path)
    normalizacion = worker.normalizacion
    orquestador = normalizacion.orquestador
    assert type(orquestador) is OrquestadorExtraccionProductiva
    assert [type(e) for e in orquestador._etapas] == [ExtractorDocumentalAutorizado]
    assert orquestador._luna is None
    assert orquestador._configuracion.luna_habilitada is False
    assert type(normalizacion.materializar_pdf) is MaterializadorStoragePrivado
    assert normalizacion.ensamblar_documento is ensamblar_documento_manual
    assert type(normalizacion.repositorio) is RepositorioRuntimeSupabase
    assert normalizacion.campos_requeridos == CAMPOS_REQUERIDOS_MANUAL
    piezas = [normalizacion.materializar_pdf, orquestador, *orquestador._etapas,
              normalizacion.ensamblar_documento, normalizacion.repositorio]
    for pieza in piezas:
        nombre = (getattr(pieza, "__name__", None) or type(pieza).__name__).lower()
        modulo = (getattr(pieza, "__module__", None) or type(pieza).__module__).lower()
        assert not any(t in nombre for t in ("centinela", "sentinel", "shadow", "luna", "lambda"))
        assert "shadow" not in modulo and "pruebas" not in modulo
    fuente = inspect.getsource(cm).lower()
    for prohibido in ("shadow", "openai", "centinela", "ejecutar_una(", "obtener_configuracion",
                      "cf_configuracion", ".update(", ".insert(", ".upsert("):
        assert prohibido not in fuente, prohibido


# --------------------------------------------------------------------------
# Extremo a extremo local
# --------------------------------------------------------------------------


def test_extremo_a_extremo_apto_manual_one_shot(tmp_path):
    supabase = _SupabaseMemoria()
    supabase.registrar("doc-alliance", _pdf(ALLIANCE))
    supabase.registrar("doc-segundo", _pdf(HEFAME))
    resultado = _worker(supabase, tmp_path).ejecutar_una_manual()
    assert resultado.documentos_reclamados == 1
    assert resultado.facturas_conciliacion_reclamadas == 0
    assert resultado.modo_ejecucion == "MANUAL_ONE_SHOT"
    assert supabase.nombres_rpc() == [
        "cf_reclamar_documento_normalizacion_manual_one_shot",
        "cf_persistir_documento_multifactura",
    ]
    payload = supabase.rpcs[-1][1]
    assert payload["p_disparador"] == "MANUAL_ONE_SHOT"
    assert payload["p_idempotency_key"].startswith("normalizacion:doc-alliance:MANUAL_ONE_SHOT:")
    assert {f["numero"] for f in supabase.facturas.values()} == NUMEROS_ALLIANCE
    assert {f["disparador"] for f in supabase.facturas.values()} == {"MANUAL_ONE_SHOT"}
    assert sum(Decimal(f["total"]) for f in supabase.facturas.values()) == Decimal("14007.37")
    assert supabase.locks == {}
    assert supabase.descargas == [("facturas-pdf", "PIO/2026/doc-alliance.pdf")]
    assert [d["estado"] for d in supabase.documentos] == ["NORMALIZADA", "PENDIENTE"]


def test_extremo_a_extremo_fail_closed_no_salta_al_segundo(tmp_path):
    supabase = _SupabaseMemoria()
    supabase.registrar("doc-hefame", _pdf(HEFAME))
    supabase.registrar("doc-alliance", _pdf(ALLIANCE))
    resultado = _worker(supabase, tmp_path).ejecutar_una_manual()
    assert resultado.documentos_reclamados == 0
    assert supabase.nombres_rpc() == [
        "cf_reclamar_documento_normalizacion_manual_one_shot",
        "cf_registrar_fallo_normalizacion",
    ]
    fallo = supabase.fallos[0]
    assert fallo["p_documento_id"] == "doc-hefame"
    assert fallo["p_disparador"] == "MANUAL_ONE_SHOT"
    assert fallo["p_error_codigo"] == "DocumentoNoAptoManual"
    assert fallo["p_error_detalle"] == "PROVEEDOR_NO_SOPORTADO_MANUAL"
    assert fallo["p_clase_fallo"] == "NO_SOPORTADO"
    assert supabase.facturas == {}
    assert supabase.locks == {}
    assert supabase.descargas == [("facturas-pdf", "PIO/2026/doc-hefame.pdf")]
    assert [d["estado"] for d in supabase.documentos] == ["PROVEEDOR_NO_SOPORTADO", "PENDIENTE"]


def test_extremo_a_extremo_sha_incorrecto_libera_lock(tmp_path):
    supabase = _SupabaseMemoria()
    supabase.registrar("doc-1", _pdf(ALLIANCE), hash_registrado="f" * 64)
    supabase.registrar("doc-2", _pdf(ALLIANCE))
    _worker(supabase, tmp_path).ejecutar_una_manual()
    assert supabase.fallos[0]["p_error_detalle"] == "SHA256_NO_COINCIDE"
    assert supabase.fallos[0]["p_clase_fallo"] == "DEFECTO_DOCUMENTO"
    assert (supabase.documentos[0]["estado"], supabase.documentos[0]["intentos_fallo"]) == ("ERROR", 1)
    assert supabase.facturas == {} and supabase.locks == {}
    assert supabase.documentos[1]["estado"] == "PENDIENTE"


def test_idempotencia_sobre_cadena_compuesta(tmp_path):
    supabase = _SupabaseMemoria()
    supabase.registrar("doc-alliance", _pdf(ALLIANCE))
    _worker(supabase, tmp_path, "uno").ejecutar_una_manual()
    supabase.reabrir("doc-alliance")
    _worker(supabase, tmp_path, "dos").ejecutar_una_manual()
    persistencias = [p for n, p in supabase.rpcs if n == "cf_persistir_documento_multifactura"]
    assert len(persistencias) == 2
    primera, segunda = persistencias
    assert primera["p_resultado_hash"] == segunda["p_resultado_hash"]
    assert primera["p_idempotency_key"] == segunda["p_idempotency_key"]
    assert primera["p_idempotency_key"].split(":")[:3] == ["normalizacion", "doc-alliance", "MANUAL_ONE_SHOT"]
    assert json.dumps(primera["p_resultado"], sort_keys=True) == json.dumps(segunda["p_resultado"], sort_keys=True)
    assert [f["identidad_economica_clave"] for f in primera["p_resultado"]["facturas"]] == \
        [f["identidad_economica_clave"] for f in segunda["p_resultado"]["facturas"]]
    assert len(supabase.facturas) == 3
    assert str(tmp_path) not in json.dumps(primera["p_resultado"])
    assert supabase.locks == {}
    assert supabase.documentos[0]["estado"] == "NORMALIZADA"


def test_aislamiento_compositor_sin_scheduler_ni_ruta_automatica():
    referencias = []
    for patron in ("*.bat", "*.cmd", "*.ps1", "*.xml"):
        for archivo in ROOT.glob(patron):
            if "compositor_manual" in archivo.read_text(encoding="utf-8", errors="ignore"):
                referencias.append(archivo)
    for archivo in (ROOT / "src").rglob("*.py"):
        if archivo.name == "compositor_manual.py":
            continue
        if "compositor_manual" in archivo.read_text(encoding="utf-8", errors="ignore"):
            referencias.append(archivo)
    assert referencias == []
    fuente = inspect.getsource(cm)
    assert "obtener_cliente_supabase" not in fuente and "create_client" not in fuente
    assert "__main__" not in fuente


def test_limite_conocido_factura_alliance_entera_omitida(tmp_path):
    """LIMITE CONOCIDO (2AQ, decision de Pio): documenta, no corrige.

    Alliance solo pagina por factura; retirar las paginas 8-9 (factura 08011305
    entera) no es detectable por contenido. Las facturas presentes se autorizan y
    la omitida no aparece en el inventario.
    """
    pdf = _truncar(_pdf(ALLIANCE), tmp_path / "sin_08011305.pdf", list(range(7)))
    resultado = ExtractorDocumentalAutorizado().extraer(pdf, CAMPOS_REQUERIDOS_MANUAL)
    assert resultado.provenance["motivo"] == "AUTORIZADO"
    documento = resultado.valores[CAMPO_DOCUMENTO]
    assert documento["documento_completo_demostrado"] is True
    assert documento["numero_paginas"] == 7
    facturas = {f["numero_factura"]["valor"]: f for f in documento["facturas"]}
    assert set(facturas) == {"08011304", "08011303"}
    assert all(f["factura_completa_demostrada"] is True for f in facturas.values())
    cliente = _SupabaseMemoria()
    cliente.documentos.append({"id": "doc-1"})
    cliente.locks["doc-1"] = "w"
    RepositorioRuntimeSupabase(cliente).persistir_documento_automatico(
        _doc(), _resultado(documento), "h", "w", "MANUAL_ONE_SHOT", "k",
    )
    payload = cliente.rpcs[-1][1]
    assert len(payload["p_segmentos_autorizados"]) == 2
    assert "08011305" not in json.dumps(payload["p_resultado"])


def test_simulador_r3_cuatro_intentos_y_revision(tmp_path):
    """Alineado con la migracion 17 (2AS): 3 fallos con backoff, el 4.o a REVISION."""
    supabase = _SupabaseMemoria()
    supabase.registrar("doc-1", _pdf(ALLIANCE), hash_registrado="f" * 64)
    documento = supabase.documentos[0]
    for intento in range(1, 5):
        documento["backoff_futuro"] = False  # simula el vencimiento del backoff
        _worker(supabase, tmp_path, f"i{intento}").ejecutar_una_manual()
        esperado = "REVISION" if intento == 4 else "ERROR"
        assert (documento["estado"], documento["intentos_fallo"]) == (esperado, intento)
    documento["backoff_futuro"] = False
    assert _worker(supabase, tmp_path, "i5").ejecutar_una_manual().documentos_reclamados == 0
    assert len(supabase.fallos) == 4 and supabase.locks == {}
