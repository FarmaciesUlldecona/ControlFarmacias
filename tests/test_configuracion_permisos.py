"""Tests de las reglas de permisos de Claude Code (.claude/settings.json).

El emulador de este archivo reproduce la semántica documentada de las reglas:
``*`` equivale a cualquier texto, un ``*`` final precedido de espacio también
encaja con el comando sin argumentos, PowerShell no distingue mayúsculas y la
precedencia es deny, luego ask, luego allow. Garantiza la coherencia de las
reglas con la intención aprobada por Pio; no sustituye al matcher real de
Claude Code, que además divide comandos compuestos y elimina envoltorios.

Ningún test conecta con Farmatic ni con Supabase.
"""

import json
import re
from pathlib import Path

import pytest


RAIZ = Path(__file__).resolve().parents[1]
RUTA_SETTINGS = RAIZ / ".claude" / "settings.json"
RUTA_SETTINGS_LOCAL = RAIZ / ".claude" / "settings.local.json"

HERRAMIENTAS = ("PowerShell", "Bash")

PY_PS = r".\.venv\Scripts\python.exe"
PY_BASH = "./.venv/Scripts/python.exe"

MODULOS_METADATOS = {
    "buscar_objetos",
    "buscar_columnas",
    "describir_tabla",
    "clave_primaria",
    "listar_objetos",
}
MODULOS_SQL_EXPLORER_ASK = {
    "analizar_tabla",
    "exportar_diccionario",
    "mapa_relaciones",
    "ver_tabla",
    "buscar_registros",
    "valores_columna",
}
MODULOS_SQL_EXPLORER_SIN_REGLA = {"__init__", "entrada", "seguridad_sql"}

DENY_ORIGINAL = {
    f"{herramienta}({patron})"
    for herramienta in HERRAMIENTAS
    for patron in (
        "git push *",
        "git reset *",
        "git clean *",
        "git checkout -- *",
        "git restore *",
        "git stash drop *",
        "git stash clear",
        "pip install *",
        "pip3 install *",
        "* -m pip install *",
        "winget *",
        "*pyvenv.cfg*",
    )
} | {"Edit(**/pyvenv.cfg)"}


def _settings() -> dict:
    return json.loads(RUTA_SETTINGS.read_text(encoding="utf-8"))


PERMISOS = _settings()["permissions"]

_REGLA = re.compile(r"^(?P<herramienta>[A-Za-z]+)(?:\((?P<patron>.*)\))?$", re.DOTALL)


def _partir(regla: str) -> tuple[str, str | None]:
    coincidencia = _REGLA.match(regla)
    assert coincidencia, f"regla mal formada: {regla!r}"
    return coincidencia["herramienta"], coincidencia["patron"]


def _coincide_comando(patron: str, comando: str, sin_mayusculas: bool) -> bool:
    flags = re.DOTALL | (re.IGNORECASE if sin_mayusculas else 0)
    regex = "".join(".*" if c == "*" else re.escape(c) for c in patron)

    if re.fullmatch(regex, comando, flags):
        return True

    if patron.endswith(" *") and patron.count("*") == 1:
        desnudo = patron[:-2]
        return (
            comando.casefold() == desnudo.casefold()
            if sin_mayusculas
            else comando == desnudo
        )

    return False


def _glob_a_regex(patron: str) -> str:
    patron = patron.lstrip("/")
    partes = []
    i = 0

    while i < len(patron):
        if patron.startswith("**/", i):
            partes.append("(?:.*/)?")
            i += 3
        elif patron.startswith("**", i):
            partes.append(".*")
            i += 2
        elif patron[i] == "*":
            partes.append("[^/]*")
            i += 1
        else:
            partes.append(re.escape(patron[i]))
            i += 1

    return "".join(partes)


def decidir_comando(herramienta: str, comando: str) -> str | None:
    for categoria in ("deny", "ask", "allow"):
        for regla in PERMISOS.get(categoria, []):
            nombre, patron = _partir(regla)

            if nombre != herramienta or patron is None:
                continue

            if _coincide_comando(patron, comando, herramienta == "PowerShell"):
                return categoria

    return None


def decidir_edicion(ruta_relativa: str) -> str | None:
    for categoria in ("deny", "ask", "allow"):
        for regla in PERMISOS.get(categoria, []):
            nombre, patron = _partir(regla)

            if nombre != "Edit" or patron is None:
                continue

            if re.fullmatch(_glob_a_regex(patron), ruta_relativa):
                return categoria

    return None


# 1. Presencia, paridad PowerShell/Bash y ausencia de duplicados


@pytest.mark.parametrize("categoria", ["allow", "ask", "deny"])
def test_sin_reglas_duplicadas(categoria):
    reglas = PERMISOS[categoria]
    assert len(reglas) == len(set(reglas))


def _patrones(categoria: str, herramienta: str) -> set[str]:
    resultado = set()

    for regla in PERMISOS[categoria]:
        nombre, patron = _partir(regla)
        if nombre == herramienta and patron is not None:
            resultado.add(patron)

    return resultado


@pytest.mark.parametrize("categoria", ["ask", "deny"])
def test_paridad_powershell_bash(categoria):
    assert _patrones(categoria, "PowerShell") == _patrones(categoria, "Bash")


def test_paridad_allow_salvo_rutas_windows():
    powershell = _patrones("allow", "PowerShell")
    bash = _patrones("allow", "Bash")

    assert bash <= powershell
    assert all(".venv\\" in patron for patron in powershell - bash)


PATRONES_ASK_APROBADOS = [
    "git commit", "git commit *", "git merge *", "git rebase *",
    "git cherry-pick *", "git revert *", "git tag *",
    "git stash", "git stash -*", "git stash push *", "git stash save *",
    "git stash pop *", "git stash apply *", "git stash branch *",
    "git stash store *", "git stash create *",
    "git switch *", "git checkout *",
    "git branch -d *", "git branch -D *", "git branch -m *", "git branch -M *",
    "git branch -c *", "git branch -C *", "git branch --delete *",
    "git branch --move *", "git branch -f *", "git branch --force *",
    "git -c *", "git -C *",
    "supabase *", "npx supabase *", "psql *", "pg_dump *", "pg_restore *",
    "docker *", "docker-compose *",
    "*desplegar*", "*sql/migrations*", "*sql\\migrations*", "*supabase*",
    "*guardar_albaranes*", "*pruebas/*", "*pruebas\\*",
    "*analizar_tabla*", "*exportar_diccionario*", "*mapa_relaciones*",
    "*ver_tabla*", "*buscar_registros*", "*valores_columna*",
    "*.claude*",
]


@pytest.mark.parametrize("herramienta", HERRAMIENTAS)
@pytest.mark.parametrize("patron", PATRONES_ASK_APROBADOS)
def test_reglas_ask_aprobadas_presentes(herramienta, patron):
    assert f"{herramienta}({patron})" in PERMISOS["ask"]


def test_ask_edicion_de_claude():
    assert "Edit(/.claude/**)" in PERMISOS["ask"]


@pytest.mark.parametrize("modulo", sorted(MODULOS_METADATOS))
def test_allow_exacto_metadatos(modulo):
    assert f"PowerShell({PY_PS} -B -m src.sql_explorer.{modulo})" in PERMISOS["allow"]
    assert f"Bash({PY_BASH} -B -m src.sql_explorer.{modulo})" in PERMISOS["allow"]


# 2. Prohibiciones


def test_allow_sin_comodin_en_python():
    for regla in PERMISOS["allow"]:
        if "python" in regla.casefold():
            assert "*" not in regla, regla


def test_allow_sin_python_c_ni_pytest():
    for regla in PERMISOS["allow"]:
        assert " -c " not in regla, regla
        assert "pytest" not in regla, regla


def test_allow_sin_comodin_total():
    for regla in PERMISOS["allow"]:
        nombre, patron = _partir(regla)
        assert patron not in (None, "*"), regla
        assert not (patron or "").startswith("*"), regla


def test_sin_reglas_de_ruta_write_ignoradas():
    """Claude Code acepta Write(ruta) pero nunca la consulta: se usa Edit."""

    for categoria in ("allow", "ask", "deny"):
        for regla in PERMISOS[categoria]:
            nombre, patron = _partir(regla)
            assert not (nombre in ("Write", "MultiEdit", "NotebookEdit") and patron), regla


def test_settings_local_sin_reglas_amplias():
    if not RUTA_SETTINGS_LOCAL.exists():
        pytest.skip("no existe settings.local.json")

    local = json.loads(RUTA_SETTINGS_LOCAL.read_text(encoding="utf-8"))

    for regla in local.get("permissions", {}).get("allow", []):
        assert not ("python" in regla.casefold() and "*" in regla), regla


# 3. Tabla de decisiones


AMBAS = HERRAMIENTAS

CASOS_COMANDOS = [
    # Git
    (AMBAS, "git commit -m x", "ask"),
    (AMBAS, "git commit", "ask"),
    (AMBAS, "git merge main", "ask"),
    (AMBAS, "git rebase main", "ask"),
    (AMBAS, "git cherry-pick abc123", "ask"),
    (AMBAS, "git revert abc123", "ask"),
    (AMBAS, "git tag v1", "ask"),
    (AMBAS, "git stash", "ask"),
    (AMBAS, "git stash -u", "ask"),
    (AMBAS, "git stash push -m x", "ask"),
    (AMBAS, "git stash pop", "ask"),
    (AMBAS, "git stash apply", "ask"),
    (AMBAS, "git stash list", None),
    (AMBAS, "git stash show -p", None),
    (AMBAS, "git stash drop", "deny"),
    (AMBAS, "git stash clear", "deny"),
    (AMBAS, "git switch main", "ask"),
    (AMBAS, "git checkout main", "ask"),
    (AMBAS, "git checkout -b rama", "ask"),
    (AMBAS, "git checkout -- a.py", "deny"),
    (AMBAS, "git branch -d rama", "ask"),
    (AMBAS, "git branch -D rama", "ask"),
    (AMBAS, "git branch -m a b", "ask"),
    (AMBAS, "git branch --delete rama", "ask"),
    (AMBAS, "git branch", "allow"),
    (AMBAS, "git branch -a", "allow"),
    (AMBAS, "git -c user.name=x commit -m y", "ask"),
    (AMBAS, "git -C . push origin main", "ask"),
    (AMBAS, "git push origin main", "deny"),
    (AMBAS, "git status --short", "allow"),
    (AMBAS, "git log -3 --oneline", "allow"),
    # Base de datos y contenedores
    (AMBAS, "supabase db push", "ask"),
    (AMBAS, "npx supabase db push", "ask"),
    (AMBAS, "psql -h db.example -U postgres", "ask"),
    (AMBAS, "pg_dump postgres", "ask"),
    (AMBAS, "pg_restore -d postgres copia.dump", "ask"),
    (AMBAS, "docker ps", "ask"),
    (AMBAS, "docker-compose up", "ask"),
    # Scripts y módulos con escritura en Supabase
    (AMBAS, "python pruebas/auditoria_2ax/desplegar_19.py", "ask"),
    (("PowerShell",), f"{PY_PS} pruebas\\auditoria_2ax\\desplegar_19.py", "ask"),
    (AMBAS, "python pruebas/auditoria_2p/desplegar.py", "ask"),
    (("PowerShell",), f"{PY_PS} pruebas\\piloto_productivo_2i.py", "ask"),
    (AMBAS, "psql -f sql/migrations/19_cf_privilegios_minimos.sql", "ask"),
    (("PowerShell",), "Get-Content sql\\migrations\\19_cf_privilegios_minimos.sql", "ask"),
    (AMBAS, 'python -c "from src.facturas.runtime_supabase.repositorios import RepositorioRuntimeSupabase"', "ask"),
    (AMBAS, 'python -c "from src.supabase_client.guardar_albaranes import guardar_albaran"', "ask"),
    (AMBAS, "python -m src.probar_supabase", "ask"),
    # sql_explorer
    (("PowerShell",), f"{PY_PS} -B -m src.sql_explorer.buscar_objetos", "allow"),
    (("PowerShell",), f"{PY_BASH} -B -m src.sql_explorer.buscar_objetos", "allow"),
    (("Bash",), f"{PY_BASH} -B -m src.sql_explorer.listar_objetos", "allow"),
    (("PowerShell",), f"{PY_PS} -B -m src.sql_explorer.buscar_objetos --otro", None),
    (("PowerShell",), f"{PY_PS} -B -m src.sql_explorer.analizar_tabla", "ask"),
    (("PowerShell",), f"{PY_PS} -B -m src.sql_explorer.exportar_diccionario", "ask"),
    (("PowerShell",), f"{PY_PS} -B -m src.sql_explorer.mapa_relaciones", "ask"),
    (("PowerShell",), f"{PY_PS} -B -m src.sql_explorer.ver_tabla", "ask"),
    (("Bash",), f"{PY_BASH} -B -m src.sql_explorer.buscar_registros", "ask"),
    (("Bash",), f"{PY_BASH} -B -m src.sql_explorer.valores_columna", "ask"),
    # Sin regla: los decide el modo de permisos
    (AMBAS, 'python -B -c "print(1)"', None),
    (("PowerShell",), f'{PY_PS} -B -m pytest tests/ -q -m "not pg17_local" --basetemp=C:\\x', None),
    (("PowerShell",), "Get-Content CLAUDE.md", None),
    # Autoprotección de .claude
    (("PowerShell",), "Set-Content .claude\\settings.json '{}'", "ask"),
    (("PowerShell",), "Get-Content .claude\\hooks\\verificar_identidad_farmatic.py", "ask"),
    (("Bash",), "cat .claude/settings.json", "ask"),
    (("Bash",), "echo x > .claude/settings.local.json", "ask"),
    (AMBAS, "python -c \"open('.claude/settings.json', 'w')\"", "ask"),
]


@pytest.mark.parametrize(
    ("herramienta", "comando", "esperado"),
    [
        (herramienta, comando, esperado)
        for herramientas, comando, esperado in CASOS_COMANDOS
        for herramienta in herramientas
    ],
)
def test_tabla_de_decisiones_comandos(herramienta, comando, esperado):
    assert decidir_comando(herramienta, comando) == esperado


@pytest.mark.parametrize(
    ("ruta", "esperado"),
    [
        (".claude/settings.json", "ask"),
        (".claude/settings.local.json", "ask"),
        (".claude/hooks/verificar_identidad_farmatic.py", "ask"),
        (".claude/skills/farmatic-sql-explorer/SKILL.md", "ask"),
        ("src/sql_explorer/entrada.py", None),
        ("tests/test_configuracion_permisos.py", None),
        (".venv/pyvenv.cfg", "deny"),
    ],
)
def test_tabla_de_decisiones_ediciones(ruta, esperado):
    assert decidir_edicion(ruta) == esperado


# 4. Deriva: lo que escribe en Supabase o en producción sigue cubierto


def _archivos_del_repositorio(patron: str) -> list[Path]:
    return sorted(
        ruta
        for ruta in RAIZ.rglob(patron)
        if not {".venv", "__pycache__", ".git"} & set(ruta.relative_to(RAIZ).parts)
    )


def _formas_de_invocar(ruta: Path) -> list[tuple[str, str]]:
    relativa = ruta.relative_to(RAIZ)
    posix = relativa.as_posix()
    windows = str(relativa).replace("/", "\\")
    formas = [(herramienta, f"python {posix}") for herramienta in HERRAMIENTAS]
    formas.append(("PowerShell", f"{PY_PS} {windows}"))

    if ruta.suffix == ".py" and relativa.parts[0] == "src":
        modulo = ".".join(relativa.with_suffix("").parts)
        formas += [(herramienta, f"python -m {modulo}") for herramienta in HERRAMIENTAS]

    return formas


def test_deriva_scripts_de_despliegue_cubiertos():
    scripts = _archivos_del_repositorio("desplegar*.py")

    assert scripts, "no se encontró ningún script de despliegue"

    sin_cubrir = [
        f"{herramienta}: {comando}"
        for ruta in scripts
        for herramienta, comando in _formas_de_invocar(ruta)
        if decidir_comando(herramienta, comando) != "ask"
    ]

    assert sin_cubrir == []


def test_deriva_migraciones_cubiertas():
    migraciones = sorted((RAIZ / "sql" / "migrations").glob("*.sql"))

    assert migraciones

    sin_cubrir = [
        f"{herramienta}: {comando}"
        for ruta in migraciones
        for herramienta, comando in _formas_de_invocar(ruta)
        if decidir_comando(herramienta, comando) != "ask"
    ]

    assert sin_cubrir == []


ACCESO_SUPABASE = re.compile(
    r"\.rpc\(|\.table\(|create_client|obtener_cliente_supabase|\.storage\b"
)


def test_deriva_modulos_con_acceso_a_supabase_cubiertos():
    modulos = [
        ruta
        for ruta in _archivos_del_repositorio("*.py")
        if ruta.relative_to(RAIZ).parts[0] == "src"
        and ACCESO_SUPABASE.search(ruta.read_text(encoding="utf-8"))
    ]

    assert modulos, "el escaneo no encontró ningún módulo con acceso a Supabase"

    sin_cubrir = [
        f"{herramienta}: {comando}"
        for ruta in modulos
        for herramienta, comando in _formas_de_invocar(ruta)
        if decidir_comando(herramienta, comando) != "ask"
    ]

    assert sin_cubrir == []


def test_deriva_modulos_de_sql_explorer_clasificados():
    """Un módulo nuevo en sql_explorer obliga a decidir su regla."""

    modulos = {
        ruta.stem
        for ruta in (RAIZ / "src" / "sql_explorer").glob("*.py")
    }
    clasificados = (
        MODULOS_METADATOS
        | MODULOS_SQL_EXPLORER_ASK
        | MODULOS_SQL_EXPLORER_SIN_REGLA
    )

    assert modulos == clasificados

    for modulo in MODULOS_SQL_EXPLORER_ASK:
        for herramienta, python in (("PowerShell", PY_PS), ("Bash", PY_BASH)):
            comando = f"{python} -B -m src.sql_explorer.{modulo}"
            assert decidir_comando(herramienta, comando) == "ask", comando


# 5. Sin regresión de la configuración anterior


def test_deny_original_conservado():
    assert DENY_ORIGINAL <= set(PERMISOS["deny"])


def test_hook_de_identidad_conservado():
    grupos = _settings()["hooks"]["PreToolUse"]

    assert len(grupos) == 1
    assert grupos[0]["matcher"] == "Bash|PowerShell|Monitor"
    (entrada,) = grupos[0]["hooks"]
    assert entrada["args"][-1] == (
        "${CLAUDE_PROJECT_DIR}/.claude/hooks/verificar_identidad_farmatic.py"
    )
