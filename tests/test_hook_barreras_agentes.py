"""Tests de los hooks del piloto de subagentes (.claude/hooks, 2026-10-23).

Cubren barreras_agentes.py (PreToolUse), registrar_uso_agente.py
(SubagentStop) y estado_git.py. Ningún test conecta con Farmatic ni con
Supabase; la huella de Git se prueba en un repositorio temporal.
"""

import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


RAIZ = Path(__file__).resolve().parents[1]
HOOKS = RAIZ / ".claude" / "hooks"
RUTA_POLITICA = RAIZ / ".claude" / "agentes" / "politica.json"
RUTA_SETTINGS = RAIZ / ".claude" / "settings.json"
PY = "./.venv/Scripts/python.exe"


def _cargar(nombre):
    anterior = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        if str(HOOKS) not in sys.path:
            sys.path.insert(0, str(HOOKS))
        spec = importlib.util.spec_from_file_location(nombre, HOOKS / f"{nombre}.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    finally:
        sys.dont_write_bytecode = anterior
    return modulo


barreras = _cargar("barreras_agentes")
registro_uso = _cargar("registrar_uso_agente")
estado_git = _cargar("estado_git")


def _politica(acceso=False):
    politica = json.loads(RUTA_POLITICA.read_text(encoding="utf-8"))
    politica["explorador-farmatic"]["acceso_farmatic"] = acceso
    return politica


def _decidir(tool_name, tool_input, agente=None, acceso=False):
    entrada = {"tool_name": tool_name, "tool_input": tool_input, "cwd": str(RAIZ)}
    if agente is not None:
        entrada["agent_type"] = agente
    return barreras.decidir(entrada, _politica(acceso))


def _bash(comando, agente=None, acceso=False):
    return _decidir("Bash", {"command": comando}, agente, acceso)


def _explorar(codigo, acceso=True):
    return _bash(f'{PY} -B -c "{codigo}"', "explorador-farmatic", acceso)


# 1. Barreras globales (sesión principal y cualquier subagente)


@pytest.mark.parametrize("agente", [None, "revisor-reglas", "general-purpose"])
@pytest.mark.parametrize("ruta", [".env", "config/.env.produccion", "C:\\x\\.env"])
def test_lectura_env_bloqueada(agente, ruta):
    decision = _decidir("Read", {"file_path": ruta}, agente)
    assert (decision.codigo, decision.motivo) == (2, "env")


def test_venv_no_es_env():
    assert _decidir("Read", {"file_path": ".venv/Scripts/activate"}).codigo == 0


@pytest.mark.parametrize(
    ("comando", "motivo"),
    [
        ("cat .env", "env"),
        ("echo $SUPABASE_SERVICE_ROLE_KEY", "service_role"),
        ("schtasks /query", "schtasks"),
        ("type logs\\agentes\\uso.jsonl", "registro_agentes"),
    ],
)
def test_comandos_globales_bloqueados(comando, motivo):
    decision = _bash(comando)
    assert (decision.codigo, decision.motivo) == (2, motivo)


def test_ruta_service_role_bloqueada():
    assert _decidir("Read", {"file_path": "config/clave_service_role.txt"}).motivo == "service_role"


def test_escritura_en_registro_de_agentes_bloqueada():
    decision = _decidir("Write", {"file_path": str(RAIZ / "logs" / "agentes" / "uso.jsonl"), "content": "{}"})
    assert decision.motivo == "registro_agentes"


def test_sesion_principal_sin_politica_de_agente():
    assert _decidir("Write", {"file_path": str(RAIZ / "src" / "x.py"), "content": ""}).codigo == 0
    assert _bash("git status").codigo == 0


# 2. Commit condicionado al PASS de revisor-reglas


def _uso(tmp_path, *registros):
    ruta = tmp_path / "uso.jsonl"
    ruta.write_text("".join(json.dumps(r) + "\n" for r in registros), encoding="utf-8")
    return str(ruta)


def test_commit_sin_revision_bloqueado(tmp_path):
    decision = barreras.barrera_commit("h1", _uso(tmp_path))
    assert decision.motivo == "commit_sin_revisor"


def test_commit_con_pass_de_la_misma_huella_permitido(tmp_path):
    ruta = _uso(tmp_path, {"agent_type": "revisor-reglas", "veredicto": "PASS", "huella_cambios": "h1"})
    assert barreras.barrera_commit("h1", ruta).codigo == 0


def test_commit_con_cambios_posteriores_bloqueado(tmp_path):
    ruta = _uso(tmp_path, {"agent_type": "revisor-reglas", "veredicto": "PASS", "huella_cambios": "h1"})
    assert barreras.barrera_commit("h2", ruta).motivo == "commit_revision_desfasada"


def test_pass_de_otro_repositorio_no_autoriza_el_commit(tmp_path):
    otro = str(tmp_path / "worktree_temporal")
    ruta = _uso(tmp_path, {"agent_type": "revisor-reglas", "veredicto": "PASS", "huella_cambios": "h1",
                           "repositorio": estado_git.clave_repositorio(otro)})
    assert barreras.barrera_commit("h1", ruta).motivo == "commit_sin_revisor"


def test_veredicto_anota_el_repositorio_revisado(repo, tmp_path):
    ruta, _git = repo
    entrada = {"agent_type": "revisor-reglas", "cwd": str(ruta),
               "agent_transcript_path": _transcript(tmp_path, "VEREDICTO: PASS")}
    vistas = []
    registro = registro_uso.construir_registro(entrada, huella=lambda raiz: vistas.append(raiz) or "h",
                                               coste=lambda m, t: None)
    assert registro["repositorio"] == estado_git.clave_repositorio(str(ruta))
    assert estado_git.clave_repositorio(vistas[0]) == estado_git.clave_repositorio(str(ruta))


def test_commit_con_ultimo_fail_bloqueado(tmp_path):
    ruta = _uso(
        tmp_path,
        {"agent_type": "revisor-reglas", "veredicto": "PASS", "huella_cambios": "h1"},
        {"agent_type": "revisor-reglas", "veredicto": "FAIL", "huella_cambios": "h1"},
    )
    assert barreras.barrera_commit("h1", ruta).motivo == "commit_revisor_fail"


def test_comando_commit_pasa_por_la_barrera(monkeypatch):
    llamadas = []
    monkeypatch.setattr(barreras, "barrera_commit", lambda: llamadas.append(1) or barreras.PERMITIR)
    assert _bash("git add -A && git commit -F mensaje.txt").codigo == 0
    assert llamadas == [1]


# 3. revisor-reglas


@pytest.mark.parametrize("comando", ["git diff HEAD", "git status --porcelain --untracked-files=all", "git log -n 3"])
def test_revisor_git_lectura_permitido(comando):
    assert _bash(comando, "revisor-reglas").codigo == 0


@pytest.mark.parametrize(
    ("comando", "motivo"),
    [
        ("git diff --output=x.txt", "argumento_git"),
        ("git diff --no-index a b", "argumento_git"),
        ("git -c core.pager=x log", "comando_no_permitido"),
        ("git diff | head", "encadenado"),
        ("git commit -m x", "commit_sin_revisor"),
        ("rm -rf docs", "comando_no_permitido"),
    ],
)
def test_revisor_comandos_bloqueados(comando, motivo, monkeypatch, tmp_path):
    monkeypatch.setattr(estado_git, "ruta_uso", lambda: str(tmp_path / "no_existe.jsonl"))
    monkeypatch.setattr(barreras.estado_git, "huella_cambios", lambda: "h")
    monkeypatch.setattr(barreras.estado_git, "ruta_uso", lambda: str(tmp_path / "no_existe.jsonl"))
    assert _bash(comando, "revisor-reglas").motivo == motivo


def test_hook_no_emite_aprobaciones():
    """El hook solo bloquea o calla: nunca concede permisos (2026-10-23)."""
    evento = _evento("Bash", {"command": "git diff HEAD -- .claude/settings.json"}, "revisor-reglas")
    resultado = subprocess.run(
        [str(PYTHON_VENV), "-I", "-S", "-B", str(HOOKS / "barreras_agentes.py")],
        input=json.dumps(evento).encode("utf-8"), capture_output=True, timeout=60,
    )
    assert resultado.returncode == 0
    assert resultado.stdout == b""


@pytest.mark.parametrize("herramienta", ["Write", "Edit"])
def test_revisor_no_escribe(herramienta):
    decision = _decidir(herramienta, {"file_path": str(RAIZ / "docs" / "x.md")}, "revisor-reglas")
    assert decision.motivo == "herramienta_no_permitida"


# 4. adaptador-facturas


def test_adaptador_escribe_en_su_ruta():
    for ruta in ("src/facturas/motor_local/adaptadores/safa.py", "tests/facturas/motor_local/test_safa_local.py"):
        assert _decidir("Write", {"file_path": str(RAIZ / ruta)}, "adaptador-facturas").codigo == 0


@pytest.mark.parametrize(
    ("ruta", "motivo"),
    [
        ("src/facturas/motor_local/adaptadores/registro.py", "ruta_protegida"),
        ("src/facturas/motor_local/adaptadores/base.py", "ruta_protegida"),
        ("src/facturas/motor_local/autoridad.py", "escritura_fuera_de_ruta"),
        ("src/facturas/runtime_supabase/conciliacion.py", "escritura_fuera_de_ruta"),
        ("src/facturas/normalizador_v2/contrato.py", "escritura_fuera_de_ruta"),
        ("docs/contexto/REGLAS_CRITICAS.md", "escritura_fuera_de_ruta"),
        ("src/facturas/motor_local/adaptadores/../servicio.py", "escritura_fuera_de_ruta"),
    ],
)
def test_adaptador_escritura_fuera_de_ruta(ruta, motivo):
    assert _decidir("Edit", {"file_path": str(RAIZ / ruta)}, "adaptador-facturas").motivo == motivo


def test_adaptador_pytest_con_basetemp_permitido():
    comando = f"{PY} -m pytest tests/facturas/motor_local/test_safa_local.py --basetemp=C:/tmp/pa -q"
    assert _bash(comando, "adaptador-facturas").codigo == 0
    comando_ps = ".\\.venv\\Scripts\\python.exe -B -m pytest tests --basetemp C:\\tmp\\pa"
    assert _decidir("PowerShell", {"command": comando_ps}, "adaptador-facturas").codigo == 0


@pytest.mark.parametrize(
    ("comando", "motivo"),
    [
        (f"{PY} -m pytest tests -q", "sin_basetemp"),
        (f"{PY} -c \"print(1)\"", "comando_no_permitido"),
        (f"{PY} -B -m src.facturas.importar_documentos --basetemp=x", "comando_no_permitido"),
        ("python -m pytest tests --basetemp=x", "comando_no_permitido"),
        (f"{PY} -m pytest tests --basetemp=x; rm -rf src", "encadenado"),
    ],
)
def test_adaptador_comandos_bloqueados(comando, motivo):
    assert _bash(comando, "adaptador-facturas").motivo == motivo


# 5. documentador


def test_documentador_escribe_en_docs():
    assert _decidir("Write", {"file_path": str(RAIZ / "docs" / "modulos" / "motor.md")}, "documentador").codigo == 0


@pytest.mark.parametrize(
    ("herramienta", "entrada", "motivo"),
    [
        ("Write", {"file_path": str(RAIZ / "docs" / "contexto" / "ESTADO_ACTUAL.md")}, "ruta_protegida"),
        ("Edit", {"file_path": str(RAIZ / "src" / "x.py")}, "escritura_fuera_de_ruta"),
        ("Bash", {"command": "ls"}, "herramienta_no_permitida"),
    ],
)
def test_documentador_bloqueos(herramienta, entrada, motivo):
    assert _decidir(herramienta, entrada, "documentador").motivo == motivo


# 6. explorador-farmatic


PERSONALES = ["Cliente", "ClienteTarjetas", "Venta", "LineaVenta", "vVentasCliente", "LibroReceta",
              "Tarjeta", "Vendedor", "PACIENTE", "Medico", "Agenda_Cita", "Encargo", "LineaFactura",
              "ValeEstupef", "EMail_Envio", "CajaVenta", "Historico", "AccesosLopd"]
NO_PERSONALES = ["Albaran", "AlbaranRecep", "Recep", "LineaRecep", "LineaRecepAux", "Proveedor",
                 "Articu", "CProvee", "Familia", "LineaFacturaCompra", "Inventario", "HistoInventario"]

VALORES = "from src.sql_explorer.valores_columna import construir_consulta, obtener_valores; "
VER = "from src.sql_explorer.ver_tabla import construir_consulta, obtener_registros; "
REGISTROS = ("from src.sql_explorer.buscar_registros import construir_consulta_registros, "
             "ejecutar_consulta_registros, OPERADORES; ")


def _ver_filas(tabla):
    return VER + f"c, p, d = construir_consulta('dbo', '{tabla}', 20, None, None, False); print(obtener_registros(c, p))"


def _explorar_factura(codigo, activa):
    politica = _politica(acceso=True)
    politica["explorador-farmatic"]["columnas_restringidas"]["Factura"]["activa"] = activa
    entrada = {"tool_name": "Bash", "tool_input": {"command": f'{PY} -B -c "{codigo}"'},
               "cwd": str(RAIZ), "agent_type": "explorador-farmatic"}
    return barreras.decidir(entrada, politica)


def test_explorador_sin_ok_de_pio_bloqueado():
    codigo = "from src.sql_explorer.buscar_objetos import buscar_objetos; print(buscar_objetos('Albaran'))"
    assert _explorar(codigo, acceso=False).motivo == "farmatic_sin_ok"


def test_politica_versionada_con_acceso_y_factura_restringida():
    politica = json.loads(RUTA_POLITICA.read_text(encoding="utf-8"))["explorador-farmatic"]
    assert politica["acceso_farmatic"] is True
    # Activada con OK de Pio el 2026-10-23.
    assert politica["columnas_restringidas"]["Factura"]["activa"] is True
    assert {"CliPro", "Nif", "Titular"} <= set(politica["columnas_restringidas"]["Factura"]["excluidas"])


@pytest.mark.parametrize("tabla", PERSONALES + NO_PERSONALES + ["Factura"])
@pytest.mark.parametrize(
    "plantilla",
    [
        "from src.sql_explorer.describir_tabla import obtener_columnas; print(obtener_columnas('{t}'))",
        "from src.sql_explorer.clave_primaria import obtener_clave_primaria; print(obtener_clave_primaria('{t}'))",
        "from src.sql_explorer.valores_columna import contar_registros_totales; print(contar_registros_totales('dbo', '{t}'))",
        "from src.database.conexion_sql import obtener_conexion; from src.sql_explorer.analizar_tabla import "
        "obtener_relaciones_salientes; print(obtener_relaciones_salientes(obtener_conexion(), 'dbo', '{t}'))",
    ],
)
def test_explorador_estructura_en_todos_los_objetos(tabla, plantilla):
    assert _explorar(plantilla.format(t=tabla)).codigo == 0, tabla


@pytest.mark.parametrize("tabla", PERSONALES)
def test_explorador_personales_sin_filas_ni_valores(tabla):
    assert _explorar(_ver_filas(tabla)).motivo == "tabla_solo_estructura", tabla
    valores = VALORES + f"print(obtener_valores(construir_consulta('dbo', '{tabla}', 'IdCliente', 10)))"
    assert _explorar(valores).motivo == "tabla_solo_estructura", tabla


@pytest.mark.parametrize("tabla", NO_PERSONALES)
def test_explorador_no_personales_con_filas(tabla):
    assert _explorar(_ver_filas(tabla)).codigo == 0, tabla


def test_explorador_agregado_con_top_permitido():
    codigo = VALORES + "print(obtener_valores(construir_consulta('dbo', 'Albaran', 'IdProveedor', 50)))"
    assert _explorar(codigo).codigo == 0


def test_explorador_registros_con_columnas_explicitas():
    codigo = REGISTROS + ("r = construir_consulta_registros('dbo', 'Albaran', ['IdAlbaran', 'Fecha'], 'IdProveedor', "
                          "OPERADORES['1'], '0002', 10, None, 'ASC'); print(ejecutar_consulta_registros(r[0], r[1]))")
    assert _explorar(codigo).codigo == 0


def test_factura_inactiva_es_solo_estructura():
    codigo = REGISTROS + ("r = construir_consulta_registros('dbo', 'Factura', ['IdTipo', 'TotalFactura'], 'IdTipo', "
                          "OPERADORES['1'], 'R', 10, None, 'ASC'); print(ejecutar_consulta_registros(r[0], r[1]))")
    assert _explorar_factura(codigo, activa=False).motivo == "tabla_restringida_inactiva"


def test_factura_activa_sin_columnas_de_cliente():
    permitido = REGISTROS + ("r = construir_consulta_registros('dbo', 'Factura', ['IdTipo', 'TotalFactura'], 'IdTipo', "
                             "OPERADORES['1'], 'S', 10, None, 'ASC'); print(ejecutar_consulta_registros(r[0], r[1]))")
    assert _explorar_factura(permitido, activa=True).codigo == 0
    for columnas, filtro in ((["IdTipo", "Titular"], "IdTipo"), (["IdTipo"], "Nif"), (["IdTipo", "clipro"], "IdTipo")):
        codigo = REGISTROS + (f"r = construir_consulta_registros('dbo', 'Factura', {columnas!r}, '{filtro}', "
                              "OPERADORES['1'], 'x', 10, None, 'ASC'); print(ejecutar_consulta_registros(r[0], r[1]))")
        assert _explorar_factura(codigo, activa=True).motivo == "columna_excluida", columnas
    assert _explorar_factura(_ver_filas("Factura"), activa=True).motivo == "select_todas_restringida"
    valores = VALORES + "print(obtener_valores(construir_consulta('dbo', 'Factura', 'Nif', 10)))"
    assert _explorar_factura(valores, activa=True).motivo == "columna_excluida"


@pytest.mark.parametrize(
    ("codigo", "motivo"),
    [
        # Sin literales el hook no puede clasificar la tabla.
        (VALORES + "t = 'Cliente'; print(obtener_valores(construir_consulta('dbo', t, 'IdCliente', 10)))", "argumento_no_literal"),
        (VALORES + "print(obtener_valores(construir_consulta('dbo', 'Cli' + 'ente', 'IdCliente', 10)))", "argumento_no_literal"),
        # Los ejecutores solo aceptan lo que devuelve un constructor.
        (VALORES + "print(obtener_valores('SELECT TOP 5 * FROM Cliente'))", "ejecutor_sin_constructor"),
        (VER + "print(obtener_registros('SELECT * FROM Cliente', []))", "ejecutor_sin_constructor"),
        (VALORES + "q = construir_consulta('dbo', 'Albaran', 'IdProveedor', 10); q = 'SELECT * FROM Cliente'; print(obtener_valores(q))", "ejecutor_sin_constructor"),
        (VALORES + "f = obtener_valores; print(f(construir_consulta('dbo', 'Albaran', 'IdProveedor', 10)))", "nombre_no_permitido"),
        (VALORES + "construir_consulta = print", "nombre_no_permitido"),
        (VALORES + "construir_consulta('dbo', 'Albaran', 'IdProveedor', 500)", "top_excedido"),
        (VALORES + "construir_consulta('dbo', 'Albaran', 'IdProveedor', limite=n)", "top_excedido"),
        (VER + "construir_consulta('dbo', 'Albaran')", "top_excedido"),
        (REGISTROS + "construir_consulta_registros('dbo', 'Albaran', cols, 'IdProveedor', OPERADORES['1'], 'x', 10, None, 'ASC')", "argumento_no_literal"),
        ("from src.sql_explorer.analizar_tabla import ejecutar_consulta; ejecutar_consulta(None, 'SELECT 1')", "import_no_permitido"),
        ("from src.database.conexion_sql import obtener_conexion; obtener_conexion().cursor()", "atributo_no_permitido"),
        ("from src.sql_explorer.ver_tabla import ver_tabla; ver_tabla()", "import_no_permitido"),
        ("from src.sql_explorer.buscar_objetos import buscar_objetos as _b; _b('x')", "import_no_permitido"),
        ("import os; os.system('x')", "codigo_no_permitido"),
        ("open('docs/x.md', 'w')", "llamada_no_permitida"),
        ("print(__import__('os'))", "nombre_no_permitido"),
        ("from src.sql_explorer.buscar_objetos import buscar_objetos; buscar_objetos.__globals__", "atributo_no_permitido"),
        ("exec('x')", "llamada_no_permitida"),
        ("print(", "codigo_invalido"),
    ],
)
def test_explorador_codigo_bloqueado(codigo, motivo):
    assert _explorar(codigo).motivo == motivo


@pytest.mark.parametrize(
    ("comando", "motivo"),
    [
        (f'{PY} -B -m src.sql_explorer.ver_tabla', "comando_no_permitido"),
        ('python -c "print(1)"', "comando_no_permitido"),
        (f'{PY} -B -c "print(1)" > salida.txt', "encadenado"),
        (f'{PY} -B -c "print(1)";rm -rf docs', "encadenado"),
        (f'{PY} -B -c "print(1)" && whoami', "encadenado"),
        (f'{PY} -B -c "print(\'$(rm -rf docs)\')"', "encadenado"),
        (f'{PY} -B -c "print(`whoami`)"', "encadenado"),
    ],
)
def test_explorador_comandos_bloqueados(comando, motivo):
    assert _bash(comando, "explorador-farmatic", acceso=True).motivo == motivo


@pytest.mark.parametrize("herramienta", ["Write", "Edit", "WebFetch"])
def test_explorador_sin_escritura_ni_red(herramienta):
    decision = _decidir(herramienta, {"file_path": str(RAIZ / "docs" / "x.md"), "url": "https://x"}, "explorador-farmatic")
    assert decision.motivo == "herramienta_no_permitida"


# 7. Subagentes sin política y fallo cerrado


def test_subagente_desconocido_no_escribe():
    decision = _decidir("Write", {"file_path": str(RAIZ / "docs" / "x.md")}, "general-purpose")
    assert decision.motivo == "agente_desconocido"
    assert _decidir("Read", {"file_path": str(RAIZ / "AGENTS.md")}, "general-purpose").codigo == 0


def test_entrada_invalida_bloquea(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(barreras.estado_git, "directorio_logs", lambda: str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"no es json")))
    assert barreras.main() == 2
    assert "error interno" in capsys.readouterr().err
    registro = json.loads((tmp_path / "barreras.jsonl").read_text(encoding="utf-8"))
    assert registro["motivo"].startswith("error_interno")
    assert "command" not in registro


def test_settings_registra_los_hooks():
    hooks = json.loads(RUTA_SETTINGS.read_text(encoding="utf-8"))["hooks"]
    (barrera,) = [g for g in hooks["PreToolUse"] if g["matcher"] == "*"]
    assert barrera["hooks"][0]["args"][-1].endswith("/.claude/hooks/barreras_agentes.py")
    (uso,) = hooks["SubagentStop"]
    assert uso["hooks"][0]["args"][-1].endswith("/.claude/hooks/registrar_uso_agente.py")


@pytest.mark.parametrize("agente", ["explorador-farmatic", "revisor-reglas", "adaptador-facturas", "documentador"])
def test_definiciones_de_agentes_coherentes_con_el_hook(agente):
    texto = (RAIZ / ".claude" / "agents" / f"{agente}.md").read_text(encoding="utf-8")
    cabecera = texto.split("---")[1]
    assert f"name: {agente}" in cabecera
    herramientas = {h.strip() for h in cabecera.split("tools:")[1].splitlines()[0].split(",")}
    assert "Agent" not in herramientas
    assert agente in barreras.POLITICAS
    if agente in ("explorador-farmatic", "revisor-reglas"):
        assert not herramientas & {"Write", "Edit", "NotebookEdit"}
    if agente == "documentador":
        assert not herramientas & {"Bash", "PowerShell"}


# 7b. El hook como proceso, con el intérprete y los flags de settings.json


PYTHON_VENV = RAIZ / ".venv" / "Scripts" / "python.exe"


def _proceso(evento):
    if not PYTHON_VENV.exists():
        pytest.skip("sin .venv")
    resultado = subprocess.run(
        [str(PYTHON_VENV), "-I", "-S", "-B", str(HOOKS / "barreras_agentes.py")],
        input=json.dumps(evento).encode("utf-8"),
        capture_output=True,
        timeout=60,
    )
    # Decodificación estricta: el mensaje debe salir en UTF-8 (acentos intactos).
    return resultado.returncode, resultado.stderr.decode("utf-8")


def _evento(tool_name, tool_input, agente):
    # Misma forma que la entrada real capturada el 2026-10-23 (Claude Code 2.1.296).
    return {
        "session_id": "s", "transcript_path": "t", "cwd": str(RAIZ), "permission_mode": "default",
        "hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input,
        "tool_use_id": "u", "agent_id": "a1", "agent_type": agente,
    }


@pytest.mark.parametrize(
    ("agente", "tool_name", "tool_input", "codigo", "motivo"),
    [
        ("documentador", "Write", {"file_path": str(RAIZ / "docs" / "contexto" / "X.md"), "content": "x"}, 2, "ruta_protegida"),
        ("documentador", "Write", {"file_path": str(RAIZ / "docs" / "modulos" / "x.md"), "content": "x"}, 0, None),
        ("adaptador-facturas", "Edit", {"file_path": str(RAIZ / "src" / "facturas" / "motor_local" / "adaptadores" / "registro.py"),
                                        "old_string": "a", "new_string": "b"}, 2, "ruta_protegida"),
        ("explorador-farmatic", "Bash", {"command": f"{PY} -B -c \"{_ver_filas('Cliente')}\""}, 2, "tabla_solo_estructura"),
        ("explorador-farmatic", "Bash", {"command": f"{PY} -B -c \"from src.sql_explorer.describir_tabla import obtener_columnas; print(obtener_columnas('Cliente'))\""}, 0, None),
        ("explorador-farmatic", "Bash", {"command": f"{PY} -B -c \"{_ver_filas('Factura')}\""}, 2, "select_todas_restringida"),
        ("explorador-farmatic", "Bash", {"command": f"{PY} -B -c \"" + REGISTROS + "r = construir_consulta_registros('dbo', 'Factura', ['IdTipo', 'Nif'], 'IdTipo', OPERADORES['1'], 'S', 10, None, 'ASC'); print(ejecutar_consulta_registros(r[0], r[1]))\""}, 2, "columna_excluida"),
        ("explorador-farmatic", "Bash", {"command": f"{PY} -B -c \"" + REGISTROS + "r = construir_consulta_registros('dbo', 'Factura', ['IdTipo', 'TotalFactura'], 'IdTipo', OPERADORES['1'], 'R', 10, None, 'ASC'); print(ejecutar_consulta_registros(r[0], r[1]))\""}, 0, None),
        ("revisor-reglas", "Bash", {"command": "git diff HEAD --stat"}, 0, None),
        ("revisor-reglas", "Write", {"file_path": str(RAIZ / "docs" / "x.md"), "content": "x"}, 2, "herramienta_no_permitida"),
        ("general-purpose", "Read", {"file_path": str(RAIZ / ".env")}, 2, "env"),
    ],
)
def test_hook_como_proceso(agente, tool_name, tool_input, codigo, motivo):
    real = RAIZ / "logs" / "agentes" / "barreras.jsonl"
    antes = real.read_bytes() if real.exists() else None
    devuelto, error = _proceso(_evento(tool_name, tool_input, agente))
    assert devuelto == codigo, error
    if motivo:
        assert f"({motivo})" in error
    # El registro va a la raíz temporal de pytest, nunca a logs/ del repositorio.
    assert (real.read_bytes() if real.exists() else None) == antes


def test_mensaje_de_bloqueo_en_utf8():
    evento = _evento("Write", {"file_path": str(RAIZ / "docs" / "contexto" / "X.md"), "content": "x"}, "documentador")
    devuelto, error = _proceso(evento)
    assert devuelto == 2
    assert "documentos canónicos" in error


# 8. Registro de uso (SubagentStop)


def _transcript(tmp_path, respuesta, handback=None):
    lineas = [
        {"type": "user", "message": {"role": "user", "content": "Revisa los cambios pendientes"}},
        {"type": "assistant", "requestId": "r1", "message": {"model": "claude-opus-5-5", "content": [
            {"type": "tool_use", "name": "Bash", "input": {}}],
            "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 0, "output_tokens": 5}}},
        {"type": "assistant", "requestId": "r1", "message": {"model": "claude-opus-5-5", "content": [
            {"type": "text", "text": "pensando"}],
            "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 0, "output_tokens": 5}}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "is_error": True, "content": "BLOQUEADO por barreras_agentes (x)"}]}},
        {"type": "assistant", "requestId": "r2", "message": {"model": "claude-opus-5-5", "content": [
            {"type": "text", "text": respuesta}],
            "usage": {"input_tokens": 2, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 100, "output_tokens": 50}}},
    ]
    if handback is not None:
        lineas.append({"type": "assistant", "requestId": "r3", "message": {"model": "claude-opus-5-5", "content": [
            {"type": "tool_use", "name": "SubagentHandback", "input": {"report": handback}}],
            "usage": {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0, "output_tokens": 1}}})
    ruta = tmp_path / "agente.jsonl"
    ruta.write_text("".join(json.dumps(l) + "\n" for l in lineas), encoding="utf-8")
    return str(ruta)


def test_tokens_sumados_una_vez_por_peticion(tmp_path):
    datos = registro_uso.analizar_transcript(_transcript(tmp_path, "ok"))
    assert datos["tokens"] == {"input_tokens": 12, "cache_creation_input_tokens": 100,
                               "cache_read_input_tokens": 100, "output_tokens": 55,
                               "ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}
    assert datos["peticiones_api"] == 2
    assert datos["llamadas_herramientas"] == 1
    assert datos["herramientas_bloqueadas"] == 1
    assert datos["tarea"] == "Revisa los cambios pendientes"


def test_tokens_de_salida_acumulados_toman_el_maximo(tmp_path):
    lineas = [
        {"type": "assistant", "requestId": "r1", "message": {"model": "m", "content": [{"type": "text", "text": "a"}],
         "usage": {"input_tokens": 3, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 50, "output_tokens": 8}}},
        {"type": "assistant", "requestId": "r1", "message": {"model": "m", "content": [{"type": "tool_use", "name": "Read", "input": {}}],
         "usage": {"input_tokens": 3, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 50, "output_tokens": 420}}},
    ]
    ruta = tmp_path / "t.jsonl"
    ruta.write_text("".join(json.dumps(l) + "\n" for l in lineas), encoding="utf-8")
    datos = registro_uso.analizar_transcript(str(ruta))
    assert datos["tokens"]["output_tokens"] == 420
    assert datos["tokens"]["cache_read_input_tokens"] == 50
    assert datos["peticiones_api"] == 1


def test_coste_con_cache_a_su_precio():
    metricas = json.loads(RUTA_POLITICA.read_text(encoding="utf-8"))["metricas"]
    tokens = {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000,
              "cache_creation_input_tokens": 2_000_000, "ephemeral_1h_input_tokens": 1_000_000}
    coste = registro_uso.calcular_coste("claude-opus-5-5", [tokens], metricas)
    # 4 entrada + 20 salida + 0,20 lectura + 5 escritura 5 min + 8 escritura 1 h = 37,20 USD
    assert coste["usd"] == 37.2
    assert coste["eur"] == round(37.2 * metricas["eur_por_usd"], 4)
    assert coste["precios"] == "VERIFICADOS 2026-10-23"
    assert registro_uso.calcular_coste("modelo-desconocido", [tokens], metricas) is None


def test_tipo_de_cambio_configurable_y_precios_estimados():
    metricas = json.loads(RUTA_POLITICA.read_text(encoding="utf-8"))["metricas"]
    metricas["eur_por_usd"] = 0.5
    del metricas["precios_usd_por_mtok"]["claude-sonnet-5-5"]["verificado"]
    tokens = {"input_tokens": 0, "output_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000,
              "cache_creation_input_tokens": 0}
    coste = registro_uso.calcular_coste("claude-sonnet-5-5", [tokens], metricas)
    # Sonnet 5.5: salida 10 + lectura de caché 0,10 (página oficial, 2026-10-23).
    assert coste["usd"] == 10.1
    assert coste["eur"] == 5.05
    assert coste["precios"] == "ESTIMADOS"


def test_tramo_largo_de_haiku_por_peticion():
    metricas = json.loads(RUTA_POLITICA.read_text(encoding="utf-8"))["metricas"]
    corta = {"input_tokens": 50_000, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    larga = {"input_tokens": 200_000, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    coste = registro_uso.calcular_coste("claude-haiku-5-5", [corta, larga], metricas)
    # 50 k × 0,10 + 200 k × 0,50 (más de 100.000 tokens de prompt) = 0,005 + 0,10 USD
    assert coste["usd"] == 0.105


def test_desglose_de_escritura_de_cache(tmp_path):
    linea = {"type": "assistant", "requestId": "r1", "message": {"model": "m", "content": [], "usage": {
        "input_tokens": 1, "cache_creation_input_tokens": 30, "cache_read_input_tokens": 0, "output_tokens": 1,
        "cache_creation": {"ephemeral_5m_input_tokens": 10, "ephemeral_1h_input_tokens": 20}}}}
    ruta = tmp_path / "t.jsonl"
    ruta.write_text(json.dumps(linea) + "\n", encoding="utf-8")
    tokens = registro_uso.analizar_transcript(str(ruta))["tokens"]
    assert (tokens["ephemeral_5m_input_tokens"], tokens["ephemeral_1h_input_tokens"]) == (10, 20)


def test_revisor_lee_solo_diff_reglas_y_ficheros_tocados(repo):
    ruta, git = repo
    (ruta / "docs" / "contexto").mkdir(parents=True)
    (ruta / "docs" / "contexto" / "REGLAS_CRITICAS.md").write_text("reglas", encoding="utf-8")
    (ruta / "otro.py").write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base2")
    (ruta / "a.txt").write_text("cambiado", encoding="utf-8")
    (ruta / "nuevo.py").write_text("y", encoding="utf-8")

    def leer(herramienta, objetivo):
        clave = "file_path" if herramienta == "Read" else "path"
        entrada = {"tool_name": herramienta, "tool_input": {clave: str(objetivo), "pattern": "x"},
                   "cwd": str(ruta), "agent_type": "revisor-reglas"}
        return barreras.decidir(entrada, _politica())

    assert leer("Read", ruta / "a.txt").codigo == 0
    assert leer("Read", ruta / "nuevo.py").codigo == 0
    assert leer("Read", ruta / "docs" / "contexto" / "REGLAS_CRITICAS.md").codigo == 0
    assert leer("Grep", ruta / "a.txt").codigo == 0
    assert leer("Read", ruta / "otro.py").motivo == "lectura_fuera_de_diff"
    assert leer("Grep", ruta).motivo == "lectura_fuera_de_diff"
    glob = barreras.decidir({"tool_name": "Glob", "tool_input": {"pattern": "**"}, "cwd": str(ruta),
                             "agent_type": "revisor-reglas"}, _politica())
    assert glob.motivo == "herramienta_no_permitida"


@pytest.mark.parametrize(
    ("respuesta", "veredicto"),
    [
        ("| S1 | PASS |\nVEREDICTO: PASS", "PASS"),
        ("**VEREDICTO: PASS**", "PASS"),
        ("VEREDICTO: FAIL", "FAIL"),
        ("sin veredicto", "FAIL"),
        ("VEREDICTO: PASS\nVEREDICTO: FAIL", "FAIL"),
    ],
)
def test_veredicto_del_revisor(tmp_path, respuesta, veredicto):
    entrada = {"agent_type": "revisor-reglas", "agent_transcript_path": _transcript(tmp_path, respuesta)}
    registro = registro_uso.construir_registro(entrada, huella=lambda raiz: "h1", coste=lambda m, t: None)
    assert registro["veredicto"] == veredicto
    assert registro["huella_cambios"] == "h1"


def test_veredicto_leido_del_handback(tmp_path):
    ruta = _transcript(tmp_path, "texto intermedio", handback="tabla\nVEREDICTO: PASS")
    registro = registro_uso.construir_registro({"agent_type": "revisor-reglas", "agent_transcript_path": ruta}, huella=lambda raiz: "h")
    assert registro["veredicto"] == "PASS"


def test_otros_agentes_sin_veredicto(tmp_path):
    entrada = {"agent_type": "documentador", "agent_transcript_path": _transcript(tmp_path, "VEREDICTO: PASS")}
    registro = registro_uso.construir_registro(entrada, huella=lambda raiz: pytest.fail("no debe calcularse"))
    assert "veredicto" not in registro
    assert registro["modelo"] == "claude-opus-5-5"


def test_transcript_ausente(tmp_path):
    registro = registro_uso.construir_registro({"agent_type": "documentador", "agent_transcript_path": str(tmp_path / "x")})
    assert registro["error"] == "transcript_no_disponible"


# 9. Huella de cambios


@pytest.fixture
def repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git no disponible")
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "a.txt").write_text("uno", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    return tmp_path, git


def test_huella_estable_con_git_add_y_sensible_al_contenido(repo):
    ruta, git = repo
    limpia = estado_git.huella_cambios(str(ruta))
    (ruta / "a.txt").write_text("dos", encoding="utf-8")
    (ruta / "nuevo.txt").write_text("x", encoding="utf-8")
    cambiada = estado_git.huella_cambios(str(ruta))
    assert cambiada != limpia
    git("add", "-A")
    assert estado_git.huella_cambios(str(ruta)) == cambiada
    (ruta / "nuevo.txt").write_text("y", encoding="utf-8")
    assert estado_git.huella_cambios(str(ruta)) != cambiada
