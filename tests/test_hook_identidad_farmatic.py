"""Tests del hook PreToolUse de identidad Farmatic (.claude/hooks).

La identidad se simula inyectando la función: el hook no admite ninguna
variable de entorno que la sustituya. Ningún test conecta con Farmatic ni con
Supabase.
"""

import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


RAIZ = Path(__file__).resolve().parents[1]
RUTA_HOOK = RAIZ / ".claude" / "hooks" / "verificar_identidad_farmatic.py"
RUTA_SETTINGS = RAIZ / ".claude" / "settings.json"

IDENTIDAD_CORRECTA = "mostrador\\controlfarmaciasro"


def _cargar_hook():
    anterior = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(
            "verificar_identidad_farmatic",
            RUTA_HOOK,
        )
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    finally:
        sys.dont_write_bytecode = anterior
    return modulo


hook = _cargar_hook()


def _entrada(comando, herramienta="PowerShell"):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": herramienta,
        "tool_input": {"command": comando},
    }


def _identidad_fija(valor):
    return lambda: valor


def _identidad_prohibida():
    raise AssertionError("no debe consultarse la identidad")


def _ejecutar_main(monkeypatch, datos: bytes, identidad):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(datos)))
    monkeypatch.setattr(hook, "obtener_identidad", identidad)
    return hook.main()


COMANDOS_SENSIBLES = [
    ("PowerShell", '"Familia" | .\\.venv\\Scripts\\python.exe -B -m src.sql_explorer.buscar_objetos'),
    ("Bash", "./.venv/Scripts/python.exe -B -m src.sql_explorer.ver_tabla"),
    ("PowerShell", ".\\.venv\\Scripts\\python.exe src\\sql_explorer\\describir_tabla.py"),
    ("Bash", "python -c 'from src.database.leer_albaranes import obtener_nuevos_albaranes'"),
    ("PowerShell", "python -c \"from src.database.conexion_sql import obtener_conexion\""),
    ("PowerShell", ".\\.venv\\Scripts\\python.exe -m src.sincronizar_albaranes"),
    ("Bash", "python -m src.importar_albaranes_historicos"),
    ("Bash", "python -m src.probar_albaranes"),
    ("PowerShell", "python -m src.database.explorar_base_datos"),
    ("PowerShell", "python -m src.facturas.importar_facturas_drive"),
    ("PowerShell", "cmd /c ejecutar_sincronizacion.bat"),
    ("Bash", "cmd //c EJECUTAR_IMPORTACION_FACTURAS.BAT"),
    ("Bash", "python -c 'import pyodbc'"),
    ("PowerShell", "sqlcmd -S MOSTRADOR -Q \"SELECT 1\""),
    ("PowerShell", "Invoke-Sqlcmd -Query 'SELECT 1'"),
    ("PowerShell", "New-Object System.Data.SqlClient.SqlConnection"),
    ("Bash", "python -c 'import mssql_python'"),
    ("Monitor", "python -m src.sql_explorer.listar_objetos"),
]


@pytest.mark.parametrize(("herramienta", "comando"), COMANDOS_SENSIBLES)
def test_identidad_correcta_permite(herramienta, comando):
    codigo, mensaje = hook.decidir(
        _entrada(comando, herramienta),
        _identidad_fija(IDENTIDAD_CORRECTA),
    )

    assert codigo == 0
    assert mensaje == ""


@pytest.mark.parametrize(
    "identidad",
    [
        "mostrador\\usuari",
        "MOSTRADOR\\ControlFarmaciasRO",
        "",
        "mostrador\\controlfarmaciasro2",
        "otro\\controlfarmaciasro",
    ],
)
@pytest.mark.parametrize(("herramienta", "comando"), COMANDOS_SENSIBLES)
def test_identidad_incorrecta_bloquea(herramienta, comando, identidad):
    codigo, mensaje = hook.decidir(
        _entrada(comando, herramienta),
        _identidad_fija(identidad),
    )

    assert codigo == 2
    assert "BLOQUEADO" in mensaje
    assert repr(identidad) in mensaje


@pytest.mark.parametrize(
    "comando",
    [
        "git status --short",
        "whoami",
        "Get-ChildItem docs",
        "pytest tests/ --basetemp=C:/tmp/x",
    ],
)
def test_comando_no_sensible_no_consulta_identidad(comando):
    codigo, mensaje = hook.decidir(_entrada(comando), _identidad_prohibida)

    assert (codigo, mensaje) == (0, "")


def test_monitor_websocket_sin_comando_permite():
    entrada = {
        "tool_name": "Monitor",
        "tool_input": {"ws": {"url": "wss://ejemplo.invalid"}},
    }

    assert hook.decidir(entrada, _identidad_prohibida) == (0, "")


def test_main_identidad_correcta_devuelve_0(monkeypatch):
    datos = json.dumps(_entrada("python -m src.sql_explorer.buscar_objetos")).encode()

    assert _ejecutar_main(monkeypatch, datos, _identidad_fija(IDENTIDAD_CORRECTA)) == 0


def test_main_identidad_incorrecta_devuelve_2(monkeypatch, capsys):
    datos = json.dumps(_entrada("python -m src.sql_explorer.buscar_objetos")).encode()

    codigo = _ejecutar_main(monkeypatch, datos, _identidad_fija("mostrador\\usuari"))

    assert codigo == 2
    assert "BLOQUEADO" in capsys.readouterr().err


@pytest.mark.parametrize(
    "error",
    [
        OSError("whoami no disponible"),
        subprocess.TimeoutExpired(cmd="whoami", timeout=10),
        subprocess.CalledProcessError(returncode=1, cmd="whoami"),
        KeyError("SystemRoot"),
    ],
)
def test_error_al_obtener_identidad_bloquea(monkeypatch, capsys, error):
    def fallar():
        raise error

    datos = json.dumps(_entrada("python -m src.sql_explorer.ver_tabla")).encode()

    assert _ejecutar_main(monkeypatch, datos, fallar) == 2
    assert "error interno" in capsys.readouterr().err


@pytest.mark.parametrize(
    "datos",
    [
        b"",
        b"{no es json",
        b"[]",
        b'"texto"',
        json.dumps({"tool_name": "Bash"}).encode(),
        json.dumps({"tool_name": "Bash", "tool_input": "x"}).encode(),
        json.dumps({"tool_name": "Bash", "tool_input": {}}).encode(),
        json.dumps({"tool_name": "PowerShell", "tool_input": {"command": 5}}).encode(),
        json.dumps({"tool_name": "Monitor", "tool_input": {"description": "x"}}).encode(),
    ],
)
def test_entrada_invalida_bloquea(monkeypatch, datos):
    assert _ejecutar_main(monkeypatch, datos, _identidad_prohibida) == 2


def _ejecutar_script(ruta_script, datos: bytes):
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(ruta_script)],
        input=datos,
        capture_output=True,
        timeout=60,
    )


def test_subproceso_real_comando_no_sensible_devuelve_0():
    resultado = _ejecutar_script(
        RUTA_HOOK,
        json.dumps(_entrada("git status --short")).encode(),
    )

    assert resultado.returncode == 0
    assert resultado.stderr == b""


def test_subproceso_real_json_invalido_bloquea():
    resultado = _ejecutar_script(RUTA_HOOK, b"{no es json")

    assert resultado.returncode == 2
    assert b"BLOQUEADO" in resultado.stderr


def test_script_ausente_bloquea(tmp_path):
    """Python devuelve 2 si no encuentra el script: Claude Code lo trata como bloqueo."""

    resultado = _ejecutar_script(tmp_path / "no_existe.py", b"{}")

    assert resultado.returncode == 2


def test_limitacion_conocida_interprete_ausente_no_bloquea(tmp_path):
    """LIMITACIÓN CONOCIDA aceptada por Pio.

    Si falta el Python del .venv, el proceso no llega a arrancar: no hay
    exit 2 y Claude Code lo trata como error no bloqueante. No se resuelve.
    """

    interprete_ausente = tmp_path / "no_existe" / "python.exe"

    with pytest.raises(OSError):
        subprocess.run(
            [str(interprete_ausente), str(RUTA_HOOK)],
            input=b"{}",
            capture_output=True,
            timeout=60,
        )


def test_limitacion_conocida_error_de_sintaxis_no_bloquea(tmp_path):
    """LIMITACIÓN CONOCIDA aceptada por Pio.

    Un error de sintaxis en el hook sale con 1, no con 2: Claude Code no
    bloquea. No se resuelve.
    """

    copia_rota = tmp_path / "hook_roto.py"
    copia_rota.write_text(
        RUTA_HOOK.read_text(encoding="utf-8") + "\n)(\n",
        encoding="utf-8",
    )

    resultado = _ejecutar_script(
        copia_rota,
        json.dumps(_entrada("python -m src.sql_explorer.ver_tabla")).encode(),
    )

    assert resultado.returncode == 1


def _settings():
    return json.loads(RUTA_SETTINGS.read_text(encoding="utf-8"))


def test_configuracion_del_hook():
    grupos = _settings()["hooks"]["PreToolUse"]

    assert len(grupos) == 1
    assert grupos[0]["matcher"] == "Bash|PowerShell|Monitor"

    (entrada,) = grupos[0]["hooks"]

    assert entrada["type"] == "command"
    assert entrada["timeout"] == 30
    assert entrada["command"] == "${CLAUDE_PROJECT_DIR}/.venv/Scripts/python.exe"
    assert entrada["args"] == [
        "-I",
        "-S",
        "-B",
        "${CLAUDE_PROJECT_DIR}/.claude/hooks/verificar_identidad_farmatic.py",
    ]


def test_configuracion_de_permisos():
    permisos = _settings()["permissions"]

    assert "PowerShell(.\\.venv\\Scripts\\python.exe -B -m src.sql_explorer.*)" in permisos["allow"]

    for herramienta in ("PowerShell", "Bash"):
        for regla in (
            "git push *",
            "git reset *",
            "git clean *",
            "git checkout -- *",
            "git restore *",
            "git stash drop *",
            "git stash clear",
            "pip install *",
            "* -m pip install *",
            "winget *",
            "*pyvenv.cfg*",
        ):
            assert f"{herramienta}({regla})" in permisos["deny"]

        for modulo in (
            "sincronizar_albaranes",
            "importar_albaranes_historicos",
            "probar_albaranes",
            "explorar_base_datos",
            "importar_facturas_drive",
            "schtasks",
        ):
            assert f"{herramienta}(*{modulo}*)" in permisos["ask"]

    assert "Edit(**/pyvenv.cfg)" in permisos["deny"]


USO_DE_FARMATIC = re.compile(
    r"\bobtener_conexion\b"
    r"|\bleer_albaranes\b"
    r"|\bconexion_sql\b"
    r"|^\s*(?:import|from)\s+(?:pyodbc|mssql_python)\b",
    re.MULTILINE,
)


def test_deriva_patrones_cubren_modulos_con_acceso_a_farmatic():
    modulos = []

    for ruta in sorted((RAIZ / "src").rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        if USO_DE_FARMATIC.search(ruta.read_text(encoding="utf-8")):
            modulos.append(ruta.relative_to(RAIZ))

    assert modulos, "el escaneo no encontró ningún módulo"

    sin_cubrir = [
        str(ruta)
        for ruta in modulos
        if hook.patron_sensible(".".join(ruta.with_suffix("").parts)) is None
        or hook.patron_sensible(str(ruta)) is None
    ]

    assert sin_cubrir == []
