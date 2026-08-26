import hashlib
from pathlib import Path
import subprocess
import sys

import pytest

from ejecutor_local import (
    EjecutorLocal,
    ErrorSolicitudLocal,
    OperacionLocal,
    SolicitudEjecucionLocal,
)
from politica_recursos import NivelTests


def _ejecutor(tmp_path: Path) -> EjecutorLocal:
    return EjecutorLocal(
        python_executable=sys.executable,
        pytest_basetemp=tmp_path / "pytest-interno",
    )


def _solicitud(tmp_path: Path, operacion, **kwargs) -> SolicitudEjecucionLocal:
    return SolicitudEjecucionLocal(operacion=operacion, raiz=tmp_path, **kwargs)


def test_sha256_se_calcula_localmente(tmp_path):
    contenido = b"ControlFarmacias\n"
    (tmp_path / "dato.bin").write_bytes(contenido)

    resultado = _ejecutor(tmp_path).ejecutar(
        _solicitud(tmp_path, OperacionLocal.CALCULAR_SHA256, rutas=("dato.bin",))
    )

    assert resultado.exito is True
    assert resultado.returncode == 0
    assert resultado.datos["sha256"]["dato.bin"] == hashlib.sha256(contenido).hexdigest()


def test_json_valido_e_invalido_se_representan_sin_excepcion(tmp_path):
    (tmp_path / "valido.json").write_text('{"ok": true}', encoding="utf-8")
    (tmp_path / "invalido.json").write_text('{"ok":', encoding="utf-8")
    ejecutor = _ejecutor(tmp_path)

    valido = ejecutor.ejecutar(
        _solicitud(tmp_path, OperacionLocal.VALIDAR_JSON, rutas=("valido.json",))
    )
    invalido = ejecutor.ejecutar(
        _solicitud(tmp_path, OperacionLocal.VALIDAR_JSON, rutas=("invalido.json",))
    )

    assert valido.exito is True
    assert valido.datos["resultados"][0]["valido"] is True
    assert invalido.exito is False
    assert invalido.returncode == 1
    assert invalido.error == "JSON_INVALIDO"
    assert invalido.datos["resultados"][0]["valido"] is False


def test_py_compile_devuelve_resultado_estructurado_para_codigo_valido_e_invalido(tmp_path):
    (tmp_path / "valido.py").write_text("valor = 1\n", encoding="utf-8")
    (tmp_path / "invalido.py").write_text("def rota(:\n", encoding="utf-8")
    ejecutor = _ejecutor(tmp_path)

    valido = ejecutor.ejecutar(
        _solicitud(tmp_path, OperacionLocal.PY_COMPILE, rutas=("valido.py",))
    )
    invalido = ejecutor.ejecutar(
        _solicitud(tmp_path, OperacionLocal.PY_COMPILE, rutas=("invalido.py",))
    )

    assert valido.exito is True
    assert valido.returncode == 0
    assert invalido.exito is False
    assert invalido.returncode != 0
    assert invalido.stderr


def test_pytest_focal_se_ejecuta_localmente(tmp_path):
    (tmp_path / "test_ejemplo.py").write_text(
        "def test_local():\n    assert 2 + 2 == 4\n", encoding="utf-8"
    )

    resultado = _ejecutor(tmp_path).ejecutar(
        _solicitud(
            tmp_path,
            OperacionLocal.EJECUTAR_TESTS,
            rutas=("test_ejemplo.py",),
            nivel_tests=NivelTests.TEST_FOCAL,
        )
    )

    assert resultado.exito is True
    assert resultado.returncode == 0
    assert "1 passed" in resultado.stdout


@pytest.mark.parametrize(
    ("nivel", "rutas", "objetivo_esperado"),
    [
        (NivelTests.TEST_MODULO, ("tests",), "tests"),
        (NivelTests.SUITE_COMPLETA, (), None),
    ],
)
def test_pytest_soporta_nivel_modulo_y_suite_completa(
    tmp_path, monkeypatch, nivel, rutas, objetivo_esperado
):
    (tmp_path / "tests").mkdir()
    capturado = {}

    def completar(argumentos, **kwargs):
        capturado["argumentos"] = argumentos
        return subprocess.CompletedProcess(argumentos, 0, "ok", "")

    monkeypatch.setattr("ejecutor_local.subprocess.run", completar)
    resultado = _ejecutor(tmp_path).ejecutar(
        _solicitud(
            tmp_path,
            OperacionLocal.EJECUTAR_TESTS,
            rutas=rutas,
            nivel_tests=nivel,
        )
    )

    assert resultado.exito is True
    if objetivo_esperado is None:
        assert str(tmp_path) in capturado["argumentos"]
    else:
        assert str(tmp_path / objetivo_esperado) in capturado["argumentos"]


def test_comprobacion_y_listado_de_archivos_tienen_alcance_controlado(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "dato.txt").write_text("x", encoding="utf-8")
    ejecutor = _ejecutor(tmp_path)

    comprobacion = ejecutor.ejecutar(
        _solicitud(
            tmp_path,
            OperacionLocal.COMPROBAR_ARCHIVO,
            rutas=("sub/dato.txt", "ausente.txt"),
        )
    )
    listado = ejecutor.ejecutar(
        _solicitud(tmp_path, OperacionLocal.LISTAR_ARCHIVOS, recursivo=True)
    )
    fuera = ejecutor.ejecutar(
        _solicitud(tmp_path, OperacionLocal.CALCULAR_SHA256, rutas=("../fuera",))
    )

    assert comprobacion.datos["elementos"][0]["es_archivo"] is True
    assert comprobacion.datos["elementos"][1]["existe"] is False
    assert listado.datos["archivos"] == [str(Path("sub") / "dato.txt")]
    assert fuera.exito is False
    assert "fuera del alcance" in fuera.error


def test_operacion_desconocida_se_rechaza_antes_de_ejecutar(tmp_path):
    with pytest.raises(ErrorSolicitudLocal, match="no soportada"):
        _solicitud(tmp_path, "BORRAR_TODO")


def test_timeout_conserva_salida_y_error_estructurados(tmp_path, monkeypatch):
    (tmp_path / "test_lento.py").write_text("def test_x(): pass\n", encoding="utf-8")

    def agotar(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 0.1, output=b"salida", stderr=b"error")

    monkeypatch.setattr("ejecutor_local.subprocess.run", agotar)
    resultado = _ejecutor(tmp_path).ejecutar(
        _solicitud(
            tmp_path,
            OperacionLocal.EJECUTAR_TESTS,
            rutas=("test_lento.py",),
            nivel_tests=NivelTests.TEST_FOCAL,
            timeout_segundos=0.1,
        )
    )

    assert resultado.exito is False
    assert resultado.timeout is True
    assert resultado.returncode is None
    assert resultado.stdout == "salida"
    assert resultado.stderr == "error"
    assert resultado.error == "TIMEOUT"


def test_subprocess_usa_lista_sin_shell_y_captura_returncode(tmp_path, monkeypatch):
    capturado = {}

    def completar(argumentos, **kwargs):
        capturado["argumentos"] = argumentos
        capturado.update(kwargs)
        return subprocess.CompletedProcess(argumentos, 7, "stdout-local", "stderr-local")

    monkeypatch.setattr("ejecutor_local.subprocess.run", completar)
    resultado = _ejecutor(tmp_path).ejecutar(
        _solicitud(tmp_path, OperacionLocal.GIT_STATUS)
    )

    assert isinstance(capturado["argumentos"], list)
    assert capturado["shell"] is False
    assert capturado["timeout"] == 120.0
    assert resultado.returncode == 7
    assert resultado.stdout == "stdout-local"
    assert resultado.stderr == "stderr-local"
