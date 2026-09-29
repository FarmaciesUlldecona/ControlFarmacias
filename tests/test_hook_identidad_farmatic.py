"""Tests del hook PreToolUse de identidad Farmatic (.claude/hooks).

La identidad se simula inyectando la función: el hook no admite ninguna
variable de entorno que la sustituya. Ningún test conecta con Farmatic ni con
Supabase.
"""

import datetime
import importlib.util
import io
import json
import os
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

# Valor anterior a cualquier redirección de los fixtures.
LOCALAPPDATA_REAL = os.environ.get("LOCALAPPDATA")


def _estado_registro_real():
    """Tamaño y fecha del registro real, o None si no existe."""

    if not LOCALAPPDATA_REAL:
        return None

    ruta = Path(LOCALAPPDATA_REAL) / "ControlFarmacias" / "hooks" / hook.NOMBRE_REGISTRO

    try:
        estado = ruta.stat()
    except FileNotFoundError:
        return None

    return estado.st_size, estado.st_mtime_ns


@pytest.fixture(scope="module", autouse=True)
def _registro_real_intacto():
    antes = _estado_registro_real()
    yield
    assert _estado_registro_real() == antes, "un test escribió en el registro real"


@pytest.fixture(autouse=True)
def localappdata_temporal(monkeypatch, tmp_path):
    """Ningún test, ni sus subprocesos, escribe en el registro real."""

    directorio = tmp_path / "localappdata"
    directorio.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(directorio))
    return directorio


def _ruta_registro_temporal(localappdata: Path) -> Path:
    return localappdata / "ControlFarmacias" / "hooks" / hook.NOMBRE_REGISTRO


def _eventos(ruta: Path) -> list[dict]:
    return [
        json.loads(linea)
        for linea in ruta.read_text(encoding="utf-8").splitlines()
    ]


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

    assert "PowerShell(.\\.venv\\Scripts\\python.exe -B -m src.sql_explorer.buscar_objetos)" in permisos["allow"]
    assert not any("src.sql_explorer.*" in regla for regla in permisos["allow"])

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


# Trazabilidad: registro JSONL de decisiones


CAMPOS_EVENTO = {"ts", "herramienta", "patron", "identidad", "decision", "motivo"}

CENTINELA = "CENTINELA_NO_REGISTRAR_7f3a"


def _main_con_registro(monkeypatch, comando, identidad, herramienta="PowerShell"):
    datos = json.dumps(_entrada(comando, herramienta)).encode()
    return _ejecutar_main(monkeypatch, datos, identidad)


def test_registro_permitido_escribe_linea_completa(monkeypatch, localappdata_temporal):
    codigo = _main_con_registro(
        monkeypatch,
        "python -m src.sql_explorer.buscar_objetos",
        _identidad_fija(IDENTIDAD_CORRECTA),
    )

    (evento,) = _eventos(_ruta_registro_temporal(localappdata_temporal))

    assert codigo == 0
    assert set(evento) == CAMPOS_EVENTO
    assert evento["herramienta"] == "PowerShell"
    assert evento["patron"] == "sql_explorer"
    assert evento["identidad"] == IDENTIDAD_CORRECTA
    assert evento["decision"] == "permitido"
    assert evento["motivo"] is None


def test_registro_bloqueo_por_identidad(monkeypatch, localappdata_temporal):
    codigo = _main_con_registro(
        monkeypatch,
        "sqlcmd -Q \"SELECT 1\"",
        _identidad_fija("mostrador\\usuari"),
        herramienta="Bash",
    )

    (evento,) = _eventos(_ruta_registro_temporal(localappdata_temporal))

    assert codigo == 2
    assert evento["herramienta"] == "Bash"
    assert evento["patron"] == "sqlcmd"
    assert evento["identidad"] == "mostrador\\usuari"
    assert evento["decision"] == "bloqueado"
    assert evento["motivo"] == "identidad_distinta"


def test_registro_comando_sin_patron_no_escribe(monkeypatch, localappdata_temporal):
    codigo = _main_con_registro(monkeypatch, "git status --short", _identidad_prohibida)

    assert codigo == 0
    assert not _ruta_registro_temporal(localappdata_temporal).exists()


@pytest.mark.parametrize(
    "identidad",
    [IDENTIDAD_CORRECTA, "mostrador\\usuari"],
)
def test_registro_nunca_contiene_el_comando(monkeypatch, localappdata_temporal, identidad):
    _main_con_registro(
        monkeypatch,
        f"python -m src.sql_explorer.ver_tabla --nota {CENTINELA}",
        _identidad_fija(identidad),
    )

    contenido = _ruta_registro_temporal(localappdata_temporal).read_text(encoding="utf-8")

    assert CENTINELA not in contenido
    assert "ver_tabla" not in contenido


@pytest.mark.parametrize(
    ("identidad", "codigo_esperado"),
    [(IDENTIDAD_CORRECTA, 0), ("mostrador\\usuari", 2)],
)
def test_fallo_de_escritura_no_cambia_la_decision(
    monkeypatch,
    capsys,
    localappdata_temporal,
    identidad,
    codigo_esperado,
):
    # La ruta del registro es un directorio: open() falla.
    _ruta_registro_temporal(localappdata_temporal).mkdir(parents=True)

    codigo = _main_con_registro(
        monkeypatch,
        "python -m src.sql_explorer.buscar_objetos",
        _identidad_fija(identidad),
    )

    assert codigo == codigo_esperado
    assert ("BLOQUEADO" in capsys.readouterr().err) == (codigo_esperado == 2)


def test_fallo_de_open_no_cambia_la_decision(monkeypatch, capsys):
    def open_roto(*args, **kwargs):
        raise PermissionError("sin permiso")

    monkeypatch.setattr(hook, "open", open_roto, raising=False)

    codigo = _main_con_registro(
        monkeypatch,
        "python -m src.sql_explorer.buscar_objetos",
        _identidad_fija("mostrador\\usuari"),
    )

    assert codigo == 2
    assert "BLOQUEADO por el hook" in capsys.readouterr().err


def test_sin_localappdata_no_cambia_la_decision(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA")

    codigo = _main_con_registro(
        monkeypatch,
        "python -m src.sql_explorer.buscar_objetos",
        _identidad_fija(IDENTIDAD_CORRECTA),
    )

    assert codigo == 0


def test_error_interno_registra_solo_el_tipo(monkeypatch, localappdata_temporal):
    def fallar():
        raise OSError(f"detalle privado {CENTINELA}")

    codigo = _main_con_registro(
        monkeypatch,
        "python -m src.sql_explorer.ver_tabla",
        fallar,
    )

    ruta = _ruta_registro_temporal(localappdata_temporal)
    (evento,) = _eventos(ruta)

    assert codigo == 2
    assert evento["decision"] == "bloqueado"
    assert evento["patron"] == "sql_explorer"
    assert evento["identidad"] is None
    assert evento["motivo"] == "error_interno:OSError"
    assert CENTINELA not in ruta.read_text(encoding="utf-8")


def test_error_interno_json_invalido_se_registra(monkeypatch, localappdata_temporal):
    assert _ejecutar_main(monkeypatch, b"{no es json", _identidad_prohibida) == 2

    (evento,) = _eventos(_ruta_registro_temporal(localappdata_temporal))

    assert evento["herramienta"] is None
    assert evento["patron"] is None
    assert evento["motivo"] == "error_interno:JSONDecodeError"


def test_decidir_conserva_la_excepcion_original():
    def fallar():
        raise subprocess.TimeoutExpired(cmd="whoami", timeout=10)

    with pytest.raises(subprocess.TimeoutExpired):
        hook.decidir(_entrada("python -m src.sql_explorer.ver_tabla"), fallar)


def test_registro_anade_una_linea_por_evento(monkeypatch, localappdata_temporal):
    for identidad in (IDENTIDAD_CORRECTA, "mostrador\\usuari", IDENTIDAD_CORRECTA):
        _main_con_registro(
            monkeypatch,
            "python -m src.sql_explorer.buscar_objetos",
            _identidad_fija(identidad),
        )

    ruta = _ruta_registro_temporal(localappdata_temporal)
    lineas = ruta.read_bytes().split(b"\n")

    assert lineas[-1] == b""
    assert b"\r" not in ruta.read_bytes()
    assert [evento["decision"] for evento in _eventos(ruta)] == [
        "permitido",
        "bloqueado",
        "permitido",
    ]


def test_rotacion_al_alcanzar_el_limite(monkeypatch, tmp_path):
    ruta = tmp_path / "registro.jsonl"
    monkeypatch.setattr(hook, "TAMANO_MAXIMO_REGISTRO", 100)

    ruta.write_text("x" * 100, encoding="utf-8")
    (tmp_path / "registro.jsonl.1").write_text("copia anterior", encoding="utf-8")

    evaluacion = hook.Evaluacion(0, "", "sql_explorer", IDENTIDAD_CORRECTA)
    hook.registrar_evento("PowerShell", evaluacion, ruta=str(ruta))

    assert (tmp_path / "registro.jsonl.1").read_text(encoding="utf-8") == "x" * 100
    (evento,) = _eventos(ruta)
    assert evento["decision"] == "permitido"


def test_sin_rotacion_por_debajo_del_limite(monkeypatch, tmp_path):
    ruta = tmp_path / "registro.jsonl"
    monkeypatch.setattr(hook, "TAMANO_MAXIMO_REGISTRO", 10_000)

    evaluacion = hook.Evaluacion(0, "", "sql_explorer", IDENTIDAD_CORRECTA)
    hook.registrar_evento("PowerShell", evaluacion, ruta=str(ruta))
    hook.registrar_evento("PowerShell", evaluacion, ruta=str(ruta))

    assert len(_eventos(ruta)) == 2
    assert not (tmp_path / "registro.jsonl.1").exists()


def test_marca_de_tiempo_iso_con_zona(tmp_path):
    ruta = tmp_path / "registro.jsonl"
    fijo = datetime.datetime(
        2026, 9, 29, 20, 15, 3, 123456,
        tzinfo=datetime.timezone(datetime.timedelta(hours=2)),
    )

    evaluacion = hook.Evaluacion(0, "", "sql_explorer", IDENTIDAD_CORRECTA)
    hook.registrar_evento("PowerShell", evaluacion, ruta=str(ruta), reloj=lambda: fijo)

    (evento,) = _eventos(ruta)

    assert evento["ts"] == "2026-09-29T20:15:03.123+02:00"


def test_marca_de_tiempo_real_tiene_zona(monkeypatch, localappdata_temporal):
    _main_con_registro(
        monkeypatch,
        "python -m src.sql_explorer.buscar_objetos",
        _identidad_fija(IDENTIDAD_CORRECTA),
    )

    (evento,) = _eventos(_ruta_registro_temporal(localappdata_temporal))

    assert datetime.datetime.fromisoformat(evento["ts"]).utcoffset() is not None


def test_subproceso_real_escribe_en_localappdata_redirigido(localappdata_temporal):
    """Hook completo en un proceso real: comando con patrón y JSON inválido.

    La identidad real de este equipo no se simula; solo se comprueba que el
    evento llega al registro redirigido y que coincide con el código de salida.
    """

    resultado = _ejecutar_script(
        RUTA_HOOK,
        json.dumps(_entrada(f"python -m src.sql_explorer.ver_tabla {CENTINELA}")).encode(),
    )

    ruta = _ruta_registro_temporal(localappdata_temporal)
    (evento,) = _eventos(ruta)

    assert resultado.returncode in (0, 2)
    assert evento["decision"] == ("permitido" if resultado.returncode == 0 else "bloqueado")
    assert evento["patron"] == "sql_explorer"
    assert CENTINELA not in ruta.read_text(encoding="utf-8")


def test_ruta_por_defecto_fuera_del_repositorio(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    ruta = Path(hook.ruta_registro()).resolve()

    assert ruta == (tmp_path / "ControlFarmacias" / "hooks" / "identidad_farmatic.jsonl").resolve()
    assert RAIZ.resolve() not in ruta.parents
    assert "logs" not in [parte.lower() for parte in ruta.relative_to(tmp_path.resolve()).parts]


def test_localappdata_real_fuera_del_repositorio():
    if not LOCALAPPDATA_REAL:
        pytest.skip("LOCALAPPDATA no está definida en este equipo")

    assert RAIZ.resolve() not in Path(LOCALAPPDATA_REAL).resolve().parents
