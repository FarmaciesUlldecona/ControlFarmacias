from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path
import socket
import sys

import pytest

from src.facturas.motor_local.adaptadores.cofares import AdaptadorCofares
from src.facturas.motor_local.adaptadores.hefame import AdaptadorHefame
from src.facturas.motor_local.backend.base import BackendPdf
from src.facturas.motor_local.configuracion import ConfiguracionShadow
from src.facturas.motor_local.geometria.campos import fecha_iso, palabras_fecha, palabras_importe
from src.facturas.motor_local.geometria.lineas import agrupar_por_linea, parsear_importe
from src.facturas.motor_local.modelos import DocumentoLocal, PaginaLocal, PalabraLocal, RegionLocal
from src.facturas.motor_local.observabilidad import ObservabilidadMemoria
from src.facturas.motor_local.servicio import MotorDocumentoLocal, hash_funcional, serializar_canonico
from src.facturas.motor_local.shadow import ejecutar_con_shadow_cofares


ROOT = Path(__file__).resolve().parents[3]
PDF_COFARES = ROOT / "pruebas/facturas/documentos/2o_gold_standard/COFARES VTO 30.8.26 PIO.pdf"
PDF_HEFAME = ROOT / "pruebas/facturas/documentos/2o_gold_standard/HEFAME VTO 5.8.26 PIO.pdf"
MOTOR_ROOT = ROOT / "src/facturas/motor_local"


class BackendFalso:
    id = "falso"
    version = "1"

    def __init__(self, documento: DocumentoLocal):
        self.documento = documento
        self.llamadas = 0

    def cargar_pdf(self, ruta):
        self.llamadas += 1
        return self.documento


class MotorFalla:
    def extraer(self, ruta):
        raise ValueError("fallo shadow controlado")


def _documento_cofares_falso() -> DocumentoLocal:
    textos = ["GRUPO COFARES RESUMEN DE SUMINISTROS F.PEDIDO N ALBARAN TOTAL BASES T.PED 16.07.2026 1010686313 177,98 170,32 603"]
    palabras = [PalabraLocal(t, 1, RegionLocal(i * 10, 10, i * 10 + 8, 20), i) for i, t in enumerate(textos)]
    pagina = PaginaLocal(1, 600, 800, textos[0], palabras, agrupar_por_linea(palabras))
    return DocumentoLocal("local.pdf", "a" * 64, [pagina])


def test_modelos_geometria_y_serializacion_deterministas():
    assert parsear_importe("1.234,56") == 1234.56
    assert parsear_importe("12,00-") == -12.0
    backend = BackendFalso(_documento_cofares_falso())
    assert isinstance(backend, BackendPdf)
    resultado = MotorDocumentoLocal(backend).extraer("ignorado.pdf")
    assert serializar_canonico(resultado) == serializar_canonico(resultado)
    assert hash_funcional(resultado) == hash_funcional(resultado)


def test_registro_productivo_contiene_cofares_hefame_y_fedefarma():
    motor = MotorDocumentoLocal(BackendFalso(_documento_cofares_falso()))
    assert [(a.id, a.version) for a in motor.adaptadores] == [
        ("cofares-local", "1.0.0"),
        ("hefame-local", "1.1.0"),
        ("fedefarma-local", "1.2.0"),
    ]


def test_primitivas_generales_fecha_e_importes_sin_hefame():
    palabras = [
        PalabraLocal("01.08.2026", 1, RegionLocal(10, 10, 50, 20), 1),
        PalabraLocal("1.234,56-", 1, RegionLocal(60, 10, 100, 20), 2),
    ]
    linea = agrupar_por_linea(palabras)[0]
    assert [p.texto for p in palabras_fecha(linea)] == ["01.08.2026"]
    assert [(p.texto, v) for p, v in palabras_importe(linea)] == [("1.234,56-", -1234.56)]
    assert fecha_iso("01.08.2026") == "2026-08-01"


def test_reconocimiento_cofares_es_por_contenido():
    documento = _documento_cofares_falso()
    reconocimiento = AdaptadorCofares().reconocer(documento)
    assert reconocimiento.estado == "RECONOCIDO"
    assert reconocimiento.puntuacion == 100


def test_shadow_off_no_ejecuta_motor_y_conserva_identidad(tmp_path):
    oficial = {"resultado": "oficial"}
    backend = BackendFalso(_documento_cofares_falso())
    observado = ObservabilidadMemoria([])
    salida = ejecutar_con_shadow_cofares(
        lambda ruta: oficial,
        tmp_path / "no_necesita_existir.pdf",
        configuracion=ConfiguracionShadow(False),
        motor_local=MotorDocumentoLocal(backend),
        observabilidad=observado,
    )
    assert salida is oficial
    assert backend.llamadas == 0
    assert observado.eventos == []


def test_shadow_on_conserva_salida_oficial_y_registra_local(tmp_path):
    ruta = tmp_path / "entrada.pdf"
    ruta.write_bytes(b"%PDF-falso")
    oficial = {"resultado": "oficial"}
    observado = ObservabilidadMemoria([])
    salida = ejecutar_con_shadow_cofares(
        lambda _: oficial,
        ruta,
        configuracion=ConfiguracionShadow(True),
        motor_local=MotorDocumentoLocal(BackendFalso(_documento_cofares_falso())),
        observabilidad=observado,
    )
    assert salida is oficial
    assert len(observado.eventos) == 1
    assert observado.eventos[0]["tipo"] == "SHADOW_LOCAL_RESULTADO"


def test_error_shadow_no_rompe_pipeline(tmp_path):
    ruta = tmp_path / "entrada.pdf"
    ruta.write_bytes(b"%PDF-falso")
    oficial = object()
    observado = ObservabilidadMemoria([])
    salida = ejecutar_con_shadow_cofares(
        lambda _: oficial,
        ruta,
        configuracion=ConfiguracionShadow(True),
        motor_local=MotorFalla(),
        observabilidad=observado,
    )
    assert salida is oficial
    assert observado.eventos[0]["tipo"] == "SHADOW_LOCAL_ERROR"


def test_solo_backend_pdfium_importa_pypdfium2():
    infractores = []
    for ruta in MOTOR_ROOT.rglob("*.py"):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))
        imports = []
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                imports.extend(alias.name for alias in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                imports.append(nodo.module)
        if any(nombre == "pypdfium2" or nombre.startswith("pypdfium2.") for nombre in imports):
            if ruta.relative_to(MOTOR_ROOT).as_posix() != "backend/pdfium.py":
                infractores.append(str(ruta))
    assert infractores == []


def test_capas_propias_importan_sin_pypdfium2(monkeypatch):
    nombres = [
        "src.facturas.motor_local.modelos",
        "src.facturas.motor_local.evidencia.modelos",
        "src.facturas.motor_local.geometria.lineas",
        "src.facturas.motor_local.backend.base",
        "src.facturas.motor_local.adaptadores.cofares",
    ]
    for nombre in nombres:
        sys.modules.pop(nombre, None)
    import builtins

    original = builtins.__import__

    def bloqueado(name, *args, **kwargs):
        if name == "pypdfium2" or name.startswith("pypdfium2."):
            raise AssertionError("capa propia intento importar backend concreto")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", bloqueado)
    for nombre in nombres:
        importlib.import_module(nombre)


@pytest.mark.skipif(not PDF_COFARES.exists(), reason="PDF COFARES local no disponible")
def test_backend_pdfium_version_y_replay_cofares_39():
    from src.facturas.motor_local.backend.pdfium import BackendPdfium

    backend = BackendPdfium()
    resultado = MotorDocumentoLocal(backend).extraer(PDF_COFARES)
    assert resultado.documento["layout"] == "cofares-local"
    assert len(resultado.albaranes) == 39
    assert all(fila.sentido is None for fila in resultado.albaranes)


@pytest.mark.skipif(not PDF_COFARES.exists(), reason="PDF COFARES local no disponible")
def test_replay_offline_bloquea_socket_dns_y_conserva_hash(monkeypatch):
    from src.facturas.motor_local.backend.pdfium import BackendPdfium

    normal = MotorDocumentoLocal(BackendPdfium()).extraer(PDF_COFARES)

    def red_bloqueada(*args, **kwargs):
        raise AssertionError("intento de red del motor local")

    monkeypatch.setattr(socket, "socket", red_bloqueada)
    monkeypatch.setattr(socket, "create_connection", red_bloqueada)
    monkeypatch.setattr(socket, "getaddrinfo", red_bloqueada)
    offline = MotorDocumentoLocal(BackendPdfium()).extraer(PDF_COFARES)
    assert hash_funcional(offline) == hash_funcional(normal)
    assert len(offline.albaranes) == 39


def test_auditoria_estatica_no_contiene_caminos_de_red():
    terminos = ("socket", "requests", "urllib", "httpx", "aiohttp", "telemetry", "analytics", "openai", "google", "azure")
    hallazgos = []
    for ruta in MOTOR_ROOT.rglob("*.py"):
        contenido = ruta.read_text(encoding="utf-8").casefold()
        for termino in terminos:
            if termino in contenido:
                hallazgos.append((ruta.relative_to(MOTOR_ROOT).as_posix(), termino))
    assert hallazgos == []
