"""Hook PreToolUse de Claude Code: barreras globales y por subagente.

Se ejecuta antes de cada herramienta. Devuelve exit 2 (Claude Code bloquea la
llamada) cuando:

- cualquier llamada (sesión principal o subagente) toca una ruta ``.env*``,
  nombra ``service_role`` en una ruta o comando, o ejecuta ``schtasks``;
- se intenta ``git commit`` sin un PASS de ``revisor-reglas`` registrado para
  el estado actual exacto de los cambios;
- un subagente del piloto usa una herramienta, ruta o comando fuera de su
  política (``POLITICAS``); un subagente desconocido intenta escribir con
  Write, Edit o NotebookEdit.

La identidad del subagente llega en ``agent_type`` (ausente en la sesión
principal), comprobado empíricamente el 2026-10-23 con Claude Code 2.1.296.

Es una capa adicional: no sustituye a ``verificar_identidad_farmatic.py`` ni a
``obtener_conexion()``, que siguen siendo la barrera de Farmatic.

Cualquier error interno devuelve exit 2 (bloquea). Cada bloqueo se añade como
línea JSON a ``logs/agentes/barreras.jsonl`` sin el texto del comando.

Solo usa la biblioteca estándar. Se lanza con ``-I -S -B`` desde el Python del
``.venv``.
"""

import ast
import datetime
import json
import os
import re
import shlex
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import estado_git  # noqa: E402


DIRECTORIO_PROYECTO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
RUTA_POLITICA = os.path.join(DIRECTORIO_PROYECTO, ".claude", "agentes", "politica.json")
NOMBRE_REGISTRO = "barreras.jsonl"

HERRAMIENTAS_ESCRITURA = frozenset({"Write", "Edit", "NotebookEdit"})
HERRAMIENTAS_SHELL = frozenset({"Bash", "PowerShell"})
CLAVES_RUTA = ("file_path", "path", "notebook_path", "glob")

# Metacaracteres de shell que permitirían encadenar, redirigir o sustituir.
METACARACTERES = re.compile(r"[;&|<>`$\n\r]")

RE_ENV = re.compile(r"(^|[\\/\s\"'=:])\.env", re.IGNORECASE)

ARGUMENTOS_GIT_PROHIBIDOS = (
    "--output",
    "--ext-diff",
    "--textconv",
    "--no-index",
    "--exec",
)

# --- explorador-farmatic: lista blanca de funciones de src/sql_explorer ----
#
# ESTRUCTURA: metadatos (catálogo sys/INFORMATION_SCHEMA) o recuento total;
#   permitidas en todos los objetos de Farmatic.
# CONSTRUCTOR: construye una consulta de filas o valores; la tabla y las
#   columnas deben ser literales para que el hook pueda clasificarlas.
# EJECUTOR: ejecuta solo lo que devuelve un CONSTRUCTOR (nunca SQL escrito a
#   mano), así que la clasificación del constructor cubre la lectura.

ESTRUCTURA = "estructura"
CONSTRUCTOR = "constructor"
EJECUTOR = "ejecutor"
CONEXION = "conexion"
CONSTANTE = "constante"

FUNCIONES_EXPLORADOR = {
    "src.sql_explorer.buscar_objetos": {"buscar_objetos": ESTRUCTURA},
    "src.sql_explorer.buscar_columnas": {"buscar_columnas": ESTRUCTURA},
    "src.sql_explorer.describir_tabla": {"obtener_columnas": ESTRUCTURA},
    "src.sql_explorer.clave_primaria": {"obtener_clave_primaria": ESTRUCTURA},
    "src.sql_explorer.listar_objetos": {"obtener_tablas_y_vistas": ESTRUCTURA},
    "src.sql_explorer.analizar_tabla": {
        "obtener_informacion_general": ESTRUCTURA,
        "obtener_indices": ESTRUCTURA,
        "obtener_relaciones_salientes": ESTRUCTURA,
        "obtener_relaciones_entrantes": ESTRUCTURA,
        "obtener_relaciones_probables": ESTRUCTURA,
        "obtener_objetos_dependientes": ESTRUCTURA,
    },
    "src.sql_explorer.valores_columna": {
        "contar_registros_totales": ESTRUCTURA,
        "construir_consulta": CONSTRUCTOR,
        "obtener_valores": EJECUTOR,
    },
    "src.sql_explorer.ver_tabla": {
        "construir_consulta": CONSTRUCTOR,
        "obtener_registros": EJECUTOR,
    },
    "src.sql_explorer.buscar_registros": {
        "construir_consulta_registros": CONSTRUCTOR,
        "construir_consulta_recuento": CONSTRUCTOR,
        "ejecutar_consulta_registros": EJECUTOR,
        "ejecutar_consulta_recuento": EJECUTOR,
        "OPERADORES": CONSTANTE,
    },
    "src.database.conexion_sql": {"obtener_conexion": CONEXION},
}

PARAMETROS_CONSTRUCTOR = {
    ("src.sql_explorer.valores_columna", "construir_consulta"):
        ("esquema", "tabla", "columna", "limite"),
    ("src.sql_explorer.ver_tabla", "construir_consulta"):
        ("esquema", "tabla", "limite", "columna_nombre", "columna_ordenacion", "excluir_eco"),
    ("src.sql_explorer.buscar_registros", "construir_consulta_registros"):
        ("esquema", "tabla", "columnas_resultado", "columna_filtro", "operador", "valor",
         "limite", "columna_orden", "direccion_orden"),
    ("src.sql_explorer.buscar_registros", "construir_consulta_recuento"):
        ("esquema", "tabla", "columna_filtro", "operador", "valor"),
}

PARAMETROS_COLUMNA = frozenset(
    {"columna", "columna_nombre", "columna_ordenacion", "columnas_resultado",
     "columna_filtro", "columna_orden"}
)

# Constructores que leen todas las columnas (SELECT *): nunca sobre una tabla
# con columnas restringidas.
SELECT_TODAS = frozenset({("src.sql_explorer.ver_tabla", "construir_consulta")})

BUILTINS_EXPLORADOR = frozenset(
    {"print", "len", "sorted", "str", "int", "list", "dict", "set", "sum",
     "min", "max", "enumerate", "range", "repr", "tuple", "zip"}
)

METODOS_EXPLORADOR = frozenset(
    {"get", "items", "keys", "values", "join", "upper", "lower", "startswith",
     "endswith", "strip", "split", "format", "count", "append"}
)

NODOS_EXPLORADOR = (
    ast.Module, ast.Expr, ast.Assign, ast.ImportFrom, ast.alias, ast.Call,
    ast.Name, ast.Load, ast.Store, ast.Constant, ast.keyword, ast.List,
    ast.Tuple, ast.Dict, ast.Subscript, ast.Slice, ast.Attribute, ast.ListComp,
    ast.comprehension, ast.For, ast.If, ast.Compare, ast.BoolOp, ast.And,
    ast.Or, ast.Not, ast.UnaryOp, ast.Eq, ast.NotEq, ast.In, ast.NotIn,
    ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.JoinedStr, ast.FormattedValue,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Mod,
)


class Decision(NamedTuple):
    codigo: int
    mensaje: str = ""
    motivo: str | None = None


PERMITIR = Decision(0)


def bloquear(motivo: str, mensaje: str) -> Decision:
    return Decision(2, f"BLOQUEADO por barreras_agentes ({motivo}): {mensaje}", motivo)


# --- utilidades ------------------------------------------------------------


def normalizar(ruta: str, cwd: str) -> str:
    if not os.path.isabs(ruta):
        ruta = os.path.join(cwd, ruta)
    return os.path.normcase(os.path.realpath(ruta))


def dentro_de(ruta: str, raiz: str) -> bool:
    raiz = os.path.normcase(os.path.realpath(raiz))
    try:
        return os.path.commonpath([ruta, raiz]) == raiz
    except ValueError:
        return False


def rutas_de(tool_input: dict) -> list[str]:
    return [
        valor
        for clave in CLAVES_RUTA
        if isinstance((valor := tool_input.get(clave)), str) and valor
    ]


def cargar_politica(ruta: str = RUTA_POLITICA) -> dict:
    with open(ruta, encoding="utf-8") as archivo:
        politica = json.load(archivo)
    if not isinstance(politica, dict):
        raise ValueError("politica.json no es un objeto")
    return politica


class ComandoEncadenado(ValueError):
    """El comando encadena, redirige o sustituye otros comandos."""


def tokens_shell(comando: str) -> list[str]:
    """Separa el comando respetando comillas.

    ``$`` y la comilla invertida se rechazan en cualquier posición porque
    Bash y PowerShell los expanden también dentro de comillas dobles. ``;``,
    ``&``, ``|``, ``<`` y ``>`` solo se aceptan dentro de comillas.
    """

    if re.search(r"[$`\r\n]", comando):
        raise ComandoEncadenado("sustitución o salto de línea")
    lexer = shlex.shlex(comando.replace("\\", "/"), posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    partes = list(lexer)
    if any(parte and set(parte) <= set(";&|<>()") for parte in partes):
        raise ComandoEncadenado("operador de shell fuera de comillas")
    return partes


def separar_python(comando: str) -> list[str] | None:
    """Devuelve los argumentos tras el Python del .venv, o None si no lo es.

    Lanza ``ComandoEncadenado`` si el comando encadena o redirige.
    """

    texto = comando.strip()
    if texto.startswith("& "):
        texto = texto[2:].strip()
    try:
        partes = tokens_shell(texto)
    except ComandoEncadenado:
        raise
    except ValueError:
        return None
    if not partes:
        return None
    ejecutable = partes[0].replace("\\", "/").casefold()
    if ejecutable.startswith("./"):
        ejecutable = ejecutable[2:]
    proyecto = DIRECTORIO_PROYECTO.replace("\\", "/").casefold().rstrip("/") + "/"
    if ejecutable.startswith(proyecto):
        ejecutable = ejecutable[len(proyecto):]
    if ejecutable not in (".venv/scripts/python.exe", ".venv/scripts/python"):
        return None
    return partes[1:]


# --- barreras globales -----------------------------------------------------


def barrera_global(tool_name: str, tool_input: dict, cwd: str) -> Decision:
    for ruta in rutas_de(tool_input):
        base = os.path.basename(ruta.replace("\\", "/").rstrip("/"))
        if base.casefold().startswith(".env") or RE_ENV.search(ruta):
            return bloquear("env", "acceso a ficheros .env* prohibido.")
        if "service_role" in ruta.casefold():
            return bloquear("service_role", "ruta con service_role prohibida.")
        protegidos = (
            os.path.join(DIRECTORIO_PROYECTO, "logs", "agentes"),
            estado_git.directorio_logs(),
        )
        if tool_name in HERRAMIENTAS_ESCRITURA and any(
            dentro_de(normalizar(ruta, cwd), p) for p in protegidos
        ):
            return bloquear("registro_agentes", "logs/agentes solo lo escriben los hooks.")

    if tool_name in HERRAMIENTAS_SHELL:
        comando = tool_input.get("command")
        if not isinstance(comando, str):
            raise ValueError("command no es texto")
        texto = comando.casefold()
        if "service_role" in texto:
            return bloquear("service_role", "comando con service_role prohibido.")
        if "schtasks" in texto:
            return bloquear("schtasks", "Task Scheduler solo lo toca Pio a mano.")
        if RE_ENV.search(comando):
            return bloquear("env", "comando que nombra .env* prohibido.")
        if re.search(r"logs[\\/]+agentes|uso\.jsonl|barreras\.jsonl", texto):
            return bloquear("registro_agentes", "logs/agentes solo lo escriben los hooks.")
        if re.search(r"\bgit\b[^\n]*\bcommit\b", texto):
            return barrera_commit()

    return PERMITIR


def barrera_commit(huella_actual=None, ruta_uso=None) -> Decision:
    huella = huella_actual if huella_actual is not None else estado_git.huella_cambios()
    ultimo = estado_git.ultimo_veredicto_revisor(ruta_uso)
    if ultimo is None:
        return bloquear(
            "commit_sin_revisor",
            "no hay revisión de revisor-reglas registrada; lanza revisor-reglas antes de proponer el commit.",
        )
    if ultimo.get("huella_cambios") != huella:
        return bloquear(
            "commit_revision_desfasada",
            "los cambios difieren de los revisados por revisor-reglas; vuelve a revisarlos.",
        )
    if ultimo.get("veredicto") != "PASS":
        return bloquear(
            "commit_revisor_fail",
            "la última revisión de revisor-reglas no es PASS.",
        )
    return PERMITIR


# --- políticas por subagente ----------------------------------------------


def comando_shell(tool_input: dict) -> str:
    comando = tool_input.get("command")
    if not isinstance(comando, str):
        raise ValueError("command no es texto")
    return comando


def lecturas_revisor(cwd: str) -> set[str]:
    """REGLAS_CRITICAS y los ficheros que toca el diff del repositorio revisado."""

    raiz = estado_git.raiz_repositorio(cwd)
    rutas = [os.path.join("docs", "contexto", "REGLAS_CRITICAS.md"), *estado_git.rutas_cambiadas(raiz)]
    return {normalizar(os.path.join(raiz, r), raiz) for r in rutas}


def politica_revisor(tool_name: str, tool_input: dict, cwd: str, politica: dict) -> Decision:
    if tool_name in ("Read", "Grep"):
        ruta = tool_input.get("file_path") if tool_name == "Read" else tool_input.get("path")
        if not isinstance(ruta, str) or not ruta:
            return bloquear("lectura_fuera_de_diff", "revisor-reglas solo lee ficheros concretos.")
        if normalizar(ruta, cwd) not in lecturas_revisor(cwd):
            return bloquear(
                "lectura_fuera_de_diff",
                "revisor-reglas solo lee el diff, REGLAS_CRITICAS y los ficheros que toca el diff.",
            )
        return PERMITIR
    if tool_name not in HERRAMIENTAS_SHELL:
        return bloquear("herramienta_no_permitida", f"revisor-reglas no puede usar {tool_name}.")
    comando = comando_shell(tool_input)
    if METACARACTERES.search(comando):
        return bloquear("encadenado", "revisor-reglas no puede encadenar ni redirigir comandos.")
    if not re.fullmatch(r"\s*git\s+(diff|status|log)(\s[^\n]*)?", comando):
        return bloquear("comando_no_permitido", "revisor-reglas solo ejecuta git diff, git status y git log.")
    texto = comando.casefold()
    if re.search(r"(^|\s)-c(\s|$)", texto) or any(a in texto for a in ARGUMENTOS_GIT_PROHIBIDOS):
        return bloquear("argumento_git", "argumento de git no permitido para revisor-reglas.")
    # Un git sobre .claude/ lo sigue denegando la regla ask de *.claude* en un
    # proceso claude -p: Claude Code no acepta la aprobación de un hook frente a
    # esa regla (probado el 2026-10-23). El revisor lee esos ficheros enteros.
    return PERMITIR


def politica_adaptador(tool_name: str, tool_input: dict, cwd: str, politica: dict) -> Decision:
    if tool_name in ("Read", "Grep", "Glob"):
        return PERMITIR
    if tool_name in ("Write", "Edit"):
        conf = politica["adaptador-facturas"]
        ruta = normalizar(tool_input.get("file_path", ""), cwd)
        if any(dentro_de(ruta, os.path.join(DIRECTORIO_PROYECTO, p)) for p in conf["rutas_protegidas"]):
            return bloquear(
                "ruta_protegida",
                "registro/activación de adaptadores: REQUIERE_OK_PIO.",
            )
        if any(dentro_de(ruta, os.path.join(DIRECTORIO_PROYECTO, p)) for p in conf["rutas_escritura"]):
            return PERMITIR
        return bloquear("escritura_fuera_de_ruta", "adaptador-facturas solo escribe en adaptadores y sus tests.")
    if tool_name in HERRAMIENTAS_SHELL:
        comando = comando_shell(tool_input)
        try:
            argumentos = separar_python(comando)
        except ComandoEncadenado:
            return bloquear("encadenado", "adaptador-facturas no puede encadenar, redirigir ni sustituir comandos.")
        if argumentos is None or argumentos[:2] not in (["-m", "pytest"], ["-B", "-m"]):
            return bloquear("comando_no_permitido", "adaptador-facturas solo ejecuta pytest con el Python del .venv.")
        if argumentos[:2] == ["-B", "-m"] and argumentos[2:3] != ["pytest"]:
            return bloquear("comando_no_permitido", "adaptador-facturas solo ejecuta pytest con el Python del .venv.")
        if not any(a.startswith("--basetemp") for a in argumentos):
            return bloquear("sin_basetemp", "pytest exige --basetemp=<directorio temporal propio> (CLAUDE.md).")
        return PERMITIR
    return bloquear("herramienta_no_permitida", f"adaptador-facturas no puede usar {tool_name}.")


def politica_documentador(tool_name: str, tool_input: dict, cwd: str, politica: dict) -> Decision:
    if tool_name in ("Read", "Grep", "Glob"):
        return PERMITIR
    if tool_name in ("Write", "Edit"):
        conf = politica["documentador"]
        ruta = normalizar(tool_input.get("file_path", ""), cwd)
        if any(dentro_de(ruta, os.path.join(DIRECTORIO_PROYECTO, p)) for p in conf["rutas_protegidas"]):
            return bloquear("ruta_protegida", "los documentos canónicos los actualiza la sesión principal.")
        if any(dentro_de(ruta, os.path.join(DIRECTORIO_PROYECTO, p)) for p in conf["rutas_escritura"]):
            return PERMITIR
        return bloquear("escritura_fuera_de_ruta", "documentador solo escribe en docs/.")
    return bloquear("herramienta_no_permitida", f"documentador no puede usar {tool_name}.")


DATOS = "datos"
SOLO_ESTRUCTURA = "solo_estructura"
RESTRINGIDA = "restringida"


def clasificar_tabla(tabla: str, conf: dict) -> tuple[str, dict | None]:
    """Devuelve (DATOS | SOLO_ESTRUCTURA | RESTRINGIDA, configuración).

    Una tabla con columnas restringidas inactiva cuenta como solo estructura.
    """

    nombre = tabla.split(".")[-1].strip().strip("[]")
    clave = nombre.casefold()
    for restringida, conf_restringida in conf["columnas_restringidas"].items():
        if restringida.casefold() == clave:
            if conf_restringida.get("activa") is True:
                return RESTRINGIDA, conf_restringida
            return SOLO_ESTRUCTURA, conf_restringida
    lista = conf["solo_estructura"]
    if clave in {e.casefold() for e in lista["excepciones"]}:
        return DATOS, None
    if clave in {t.casefold() for t in lista["exactas"]}:
        return SOLO_ESTRUCTURA, None
    if any(re.search(p, nombre, re.IGNORECASE) for p in lista["patrones"]):
        return SOLO_ESTRUCTURA, None
    return DATOS, None


def es_literal_texto(nodo, admite_none: bool = False) -> bool:
    return isinstance(nodo, ast.Constant) and (
        isinstance(nodo.value, str) or (admite_none and nodo.value is None)
    )


def validar_constructor(llamada: ast.Call, clave: tuple[str, str], locales: dict, conf: dict) -> Decision:
    parametros = PARAMETROS_CONSTRUCTOR[clave]
    if len(llamada.args) > len(parametros):
        return bloquear("argumento_no_literal", f"{clave[1]}: demasiados argumentos.")
    argumentos = dict(zip(parametros, llamada.args))
    for kw in llamada.keywords:
        if kw.arg is None or kw.arg not in parametros or kw.arg in argumentos:
            return bloquear("argumento_no_literal", f"{clave[1]}: argumento con nombre no admitido.")
        argumentos[kw.arg] = kw.value

    tabla = argumentos.get("tabla")
    if not es_literal_texto(argumentos.get("esquema")) or not es_literal_texto(tabla):
        return bloquear("argumento_no_literal", f"{clave[1]}: esquema y tabla deben ser texto literal.")

    columnas: list[str] = []
    for nombre, valor in argumentos.items():
        if nombre in PARAMETROS_COLUMNA:
            if nombre == "columnas_resultado":
                if not (isinstance(valor, ast.List) and valor.elts
                        and all(es_literal_texto(e) for e in valor.elts)):
                    return bloquear("argumento_no_literal", "columnas_resultado debe ser una lista literal de textos.")
                columnas += [e.value for e in valor.elts]
            elif es_literal_texto(valor, admite_none=True):
                if valor.value is not None:
                    columnas.append(valor.value)
            else:
                return bloquear("argumento_no_literal", f"{clave[1]}: la columna {nombre} debe ser texto literal.")
        elif nombre == "limite":
            if not (isinstance(valor, ast.Constant) and type(valor.value) is int
                    and 1 <= valor.value <= conf["top_maximo"]):
                return bloquear("top_excedido", f"el límite debe ser un entero literal entre 1 y {conf['top_maximo']}.")
        elif nombre == "operador":
            es_dict = isinstance(valor, ast.Dict) and all(
                isinstance(n, ast.Constant) for n in [*valor.keys, *valor.values]
            )
            es_operador = (
                isinstance(valor, ast.Subscript) and isinstance(valor.value, ast.Name)
                and locales.get(valor.value.id, (None, None, None))[2] == CONSTANTE
                and isinstance(valor.slice, ast.Constant)
            )
            if not (es_dict or es_operador):
                return bloquear("argumento_no_literal", "operador debe ser un literal u OPERADORES['n'].")
        elif nombre not in ("esquema", "tabla") and not isinstance(valor, ast.Constant):
            return bloquear("argumento_no_literal", f"{clave[1]}: {nombre} debe ser literal.")

    if "limite" in parametros and "limite" not in argumentos:
        return bloquear("top_excedido", "el límite es obligatorio en las lecturas de filas.")

    clase, conf_tabla = clasificar_tabla(tabla.value, conf)
    if clase == SOLO_ESTRUCTURA:
        motivo = "tabla_restringida_inactiva" if conf_tabla else "tabla_solo_estructura"
        return bloquear(motivo, f"{tabla.value!r}: solo estructura (sin filas ni valores).")
    if clase == RESTRINGIDA:
        if clave in SELECT_TODAS:
            return bloquear("select_todas_restringida", f"{tabla.value!r}: elige columnas explícitas (buscar_registros).")
        excluidas = {c.casefold() for c in conf_tabla["excluidas"]}
        for columna in columnas:
            if columna.casefold() in excluidas:
                return bloquear("columna_excluida", f"{tabla.value}.{columna} identifica al cliente.")
    return PERMITIR


def validar_codigo_explorador(codigo: str, conf: dict) -> Decision:
    try:
        arbol = ast.parse(codigo, mode="exec")
    except SyntaxError:
        return bloquear("codigo_invalido", "el código del explorador no es Python válido.")

    # nombre local -> (módulo, función, clase)
    locales: dict[str, tuple[str, str, str]] = {}
    asignaciones: dict[str, int] = {}

    for nodo in ast.walk(arbol):
        if not isinstance(nodo, NODOS_EXPLORADOR):
            return bloquear("codigo_no_permitido", f"construcción no permitida: {type(nodo).__name__}.")
        if isinstance(nodo, ast.ImportFrom):
            catalogo = FUNCIONES_EXPLORADOR.get(nodo.module or "")
            if catalogo is None or nodo.level:
                return bloquear("import_no_permitido", f"módulo no permitido: {nodo.module}.")
            for alias in nodo.names:
                local = alias.asname or alias.name
                if alias.name not in catalogo or local.startswith("_") or local in locales:
                    return bloquear("import_no_permitido", f"función no permitida: {alias.name}.")
                locales[local] = (nodo.module, alias.name, catalogo[alias.name])
        if isinstance(nodo, ast.Attribute) and (
            nodo.attr.startswith("_") or nodo.attr not in METODOS_EXPLORADOR
        ):
            return bloquear("atributo_no_permitido", f"atributo no permitido: {nodo.attr}.")
        if isinstance(nodo, ast.Name):
            if nodo.id.startswith("_"):
                return bloquear("nombre_no_permitido", f"nombre no permitido: {nodo.id}.")
            if isinstance(nodo.ctx, ast.Store):
                asignaciones[nodo.id] = asignaciones.get(nodo.id, 0) + 1

    if any(nombre in locales for nombre in asignaciones):
        return bloquear("nombre_no_permitido", "no se pueden reasignar las funciones importadas.")

    llamadas_directas = {
        id(nodo.func) for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
    }

    def es_constructor(nodo) -> bool:
        return (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                and locales.get(nodo.func.id, (None, None, None))[2] == CONSTRUCTOR)

    # Nombres ligados una sola vez al resultado de un constructor.
    ligados: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and es_constructor(nodo.value):
            for objetivo in nodo.targets:
                nombres = objetivo.elts if isinstance(objetivo, ast.Tuple) else [objetivo]
                for n in nombres:
                    if isinstance(n, ast.Name) and asignaciones.get(n.id) == 1:
                        ligados.add(n.id)

    def de_constructor(nodo) -> bool:
        if es_constructor(nodo):
            return True
        if isinstance(nodo, ast.Name):
            return nodo.id in ligados
        if isinstance(nodo, ast.Subscript):
            return isinstance(nodo.value, ast.Name) and nodo.value.id in ligados
        return False

    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Load) and nodo.id in locales:
            clase = locales[nodo.id][2]
            if clase != CONSTANTE and id(nodo) not in llamadas_directas:
                return bloquear("nombre_no_permitido", f"{nodo.id} solo puede llamarse directamente.")
        if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)):
            continue
        nombre = nodo.func.id
        if nombre not in locales:
            if nombre not in BUILTINS_EXPLORADOR:
                return bloquear("llamada_no_permitida", f"llamada no permitida: {nombre}.")
            continue
        modulo, funcion, clase = locales[nombre]
        if clase == CONSTANTE:
            return bloquear("llamada_no_permitida", f"{nombre} no es invocable.")
        if clase == CONSTRUCTOR:
            decision = validar_constructor(nodo, (modulo, funcion), locales, conf)
            if decision.codigo:
                return decision
        if clase == EJECUTOR:
            argumentos = list(nodo.args) + [kw.value for kw in nodo.keywords]
            if any(kw.arg is None for kw in nodo.keywords) or not argumentos:
                return bloquear("ejecutor_sin_constructor", f"{nombre} exige el resultado de un constructor.")
            if not de_constructor(argumentos[0]):
                return bloquear("ejecutor_sin_constructor", f"{nombre} solo ejecuta consultas de un constructor.")
            for resto in argumentos[1:]:
                if not (de_constructor(resto) or isinstance(resto, (ast.Constant, ast.List))):
                    return bloquear("ejecutor_sin_constructor", f"{nombre}: parámetros no admitidos.")

    return PERMITIR


def politica_explorador(tool_name: str, tool_input: dict, cwd: str, politica: dict) -> Decision:
    if tool_name in ("Read", "Grep", "Glob"):
        return PERMITIR
    if tool_name not in HERRAMIENTAS_SHELL:
        return bloquear("herramienta_no_permitida", f"explorador-farmatic no puede usar {tool_name}.")
    conf = politica["explorador-farmatic"]
    comando = comando_shell(tool_input)
    try:
        argumentos = separar_python(comando)
    except ComandoEncadenado:
        return bloquear("encadenado", "explorador-farmatic no puede encadenar, redirigir ni sustituir comandos.")
    if argumentos is None or argumentos[:1] == ["-B"] and argumentos[1:2] != ["-c"]:
        return bloquear("comando_no_permitido", "explorador-farmatic solo ejecuta el Python del .venv con -c.")
    if argumentos[:1] == ["-B"]:
        argumentos = argumentos[1:]
    if len(argumentos) != 2 or argumentos[0] != "-c":
        return bloquear("comando_no_permitido", "explorador-farmatic solo ejecuta el Python del .venv con -c.")
    decision = validar_codigo_explorador(argumentos[1], conf)
    if decision.codigo:
        return decision
    if conf.get("acceso_farmatic") is not True:
        return bloquear(
            "farmatic_sin_ok",
            "acceso a Farmatic del explorador desactivado hasta el OK de Pio (politica.json).",
        )
    return PERMITIR


POLITICAS = {
    "explorador-farmatic": politica_explorador,
    "revisor-reglas": politica_revisor,
    "adaptador-facturas": politica_adaptador,
    "documentador": politica_documentador,
}


def decidir(entrada: dict, politica: dict | None = None) -> Decision:
    tool_name = entrada.get("tool_name")
    tool_input = entrada.get("tool_input")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        raise ValueError("entrada sin tool_name o tool_input")
    cwd = entrada.get("cwd") or DIRECTORIO_PROYECTO

    decision = barrera_global(tool_name, tool_input, cwd)
    if decision.codigo:
        return decision

    agente = entrada.get("agent_type")
    if agente is None:
        return PERMITIR

    funcion = POLITICAS.get(agente)
    if funcion is None:
        if tool_name in HERRAMIENTAS_ESCRITURA:
            return bloquear("agente_desconocido", f"el subagente {agente!r} no tiene política de escritura.")
        return PERMITIR

    if politica is None:
        politica = cargar_politica()
    return funcion(tool_name, tool_input, cwd, politica)


def ahora() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def registrar(entrada: dict, decision: Decision, ruta: str | None = None) -> None:
    """Añade el bloqueo al registro. Nunca propaga errores."""

    try:
        if not decision.codigo:
            return
        if ruta is None:
            ruta = os.path.join(estado_git.directorio_logs(), NOMBRE_REGISTRO)
        evento = {
            "ts": ahora().isoformat(timespec="milliseconds"),
            "agent_type": entrada.get("agent_type") if isinstance(entrada, dict) else None,
            "herramienta": entrada.get("tool_name") if isinstance(entrada, dict) else None,
            "decision": "bloqueado",
            "motivo": decision.motivo,
        }
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "a", encoding="utf-8", newline="\n") as archivo:
            archivo.write(json.dumps(evento, ensure_ascii=False) + "\n")
    except BaseException:
        pass


def main() -> int:
    entrada: dict = {}
    try:
        entrada = json.loads(sys.stdin.buffer.read())
        if not isinstance(entrada, dict):
            raise ValueError("la entrada del hook no es un objeto")
        decision = decidir(entrada)
    except BaseException as error:
        decision = Decision(
            2,
            f"BLOQUEADO: error interno de barreras_agentes ({type(error).__name__}: {error}).",
            f"error_interno:{type(error).__name__}",
        )

    registrar(entrada, decision)

    if decision.mensaje:
        try:
            # Claude Code lee stderr como UTF-8; en Windows el valor por
            # defecto (cp1252) corrompe los acentos.
            sys.stderr.buffer.write((decision.mensaje + "\n").encode("utf-8"))
            sys.stderr.flush()
        except BaseException:
            pass

    return decision.codigo


if __name__ == "__main__":
    sys.exit(main())
