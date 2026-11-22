"""Utilidades compartidas por los hooks de agentes: huella de cambios y registro.

La huella identifica el estado exacto de los cambios respecto de ``HEAD``:
commit base más, por cada ruta que ``git status`` declara cambiada (incluidas
las no rastreadas), el SHA-256 de su contenido en disco o ``BORRADO``. No
depende del índice, así que es la misma antes y después de ``git add -A``.
``logs/`` está ignorado por Git, de modo que escribir los registros no la
cambia.

Solo usa la biblioteca estándar.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess


DIRECTORIO_PROYECTO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
NOMBRE_USO = "uso.jsonl"
AGENTE_REVISOR = "revisor-reglas"
TIMEOUT_GIT_SEGUNDOS = 30


def directorio_logs() -> str:
    # Misma convención que src/utils/logger.py: pytest apunta
    # CONTROLFARMACIAS_LOG_DIR a una raíz temporal (tests/conftest.py).
    raiz = os.environ.get("CONTROLFARMACIAS_LOG_DIR") or os.path.join(DIRECTORIO_PROYECTO, "logs")
    return os.path.join(raiz, "agentes")


def ruta_uso() -> str:
    return os.path.join(directorio_logs(), NOMBRE_USO)


def _git(*argumentos: str, directorio: str) -> bytes:
    ejecutable = shutil.which("git")
    if ejecutable is None:
        raise RuntimeError("git no está en PATH")
    resultado = subprocess.run(
        [ejecutable, *argumentos],
        cwd=directorio,
        capture_output=True,
        timeout=TIMEOUT_GIT_SEGUNDOS,
        check=True,
    )
    return resultado.stdout


def raiz_repositorio(directorio: str) -> str:
    return _git("rev-parse", "--show-toplevel", directorio=directorio).decode("utf-8").strip()


def rutas_cambiadas(directorio: str = DIRECTORIO_PROYECTO) -> list[str]:
    salida = _git(
        "status", "--porcelain=v1", "-z", "--untracked-files=all",
        directorio=directorio,
    ).decode("utf-8")
    campos = salida.split("\0")
    rutas: list[str] = []
    i = 0
    while i < len(campos):
        campo = campos[i]
        i += 1
        if not campo:
            continue
        estado, ruta = campo[:2], campo[3:]
        rutas.append(ruta)
        if "R" in estado or "C" in estado:
            # El origen del renombrado viene en el campo siguiente.
            rutas.append(campos[i])
            i += 1
    return sorted(set(rutas))


# DECISIÓN DE PIO (2026-11-18): el revisor puede LEER (solo lectura, con Read) los ficheros de src/, sql/,
# tests/ y pruebas/ que cite el diff; logs/, .env* y el resto, igual que antes.
PREFIJOS_CITABLES = ("src", "sql", "tests", "pruebas")
_RUTA_CITADA = re.compile(r"(?<![\w.\-/\\])(?:src|sql|tests|pruebas)[\\/][\w.\-\\/]+")
MAXIMO_BYTES_NO_RASTREADO = 2_000_000


def _no_rastreadas(directorio: str) -> list[str]:
    salida = _git("ls-files", "--others", "--exclude-standard", "-z", directorio=directorio).decode("utf-8")
    return [r for r in salida.split("\0") if r]


def texto_diff(directorio: str = DIRECTORIO_PROYECTO) -> str:
    """``git diff HEAD`` de los rastreados más el contenido de los no rastreados (su diff es el fichero entero)."""
    partes = [_git("diff", "HEAD", "--no-color", "--no-ext-diff", directorio=directorio).decode("utf-8", "replace")]
    for ruta in _no_rastreadas(directorio):
        completa = os.path.join(directorio, ruta)
        if os.path.isfile(completa) and os.path.getsize(completa) <= MAXIMO_BYTES_NO_RASTREADO:
            with open(completa, "rb") as archivo:
                partes.append(archivo.read().decode("utf-8", "replace"))
    return "\n".join(partes)


def _citable(relativa: str) -> bool:
    partes = relativa.split("/")
    return (partes[0] in PREFIJOS_CITABLES and ".." not in partes
            and not any(p.lower().startswith(".env") for p in partes)
            and "logs" not in (p.lower() for p in partes))


def rutas_citadas(directorio: str = DIRECTORIO_PROYECTO) -> list[str]:
    """Ficheros existentes de src/, sql/, tests/ y pruebas/ que nombra el texto del diff (relativos, con /)."""
    rutas = set()
    for encontrada in _RUTA_CITADA.findall(texto_diff(directorio)):
        relativa = encontrada.replace("\\", "/").rstrip(".-/")
        if _citable(relativa) and os.path.isfile(os.path.join(directorio, relativa)):
            rutas.add(relativa)
    return sorted(rutas)


def detalle_cambios(directorio: str = DIRECTORIO_PROYECTO) -> dict:
    """Commit base y ``[ruta, sha256 | BORRADO]`` de cada ruta cambiada: lo que resume la huella."""
    base = _git("rev-parse", "HEAD", directorio=directorio).decode("ascii").strip()
    elementos = []
    for ruta in rutas_cambiadas(directorio):
        completa = os.path.join(directorio, ruta)
        if os.path.isfile(completa):
            with open(completa, "rb") as archivo:
                contenido = hashlib.sha256(archivo.read()).hexdigest()
        else:
            contenido = "BORRADO"
        elementos.append([ruta, contenido])
    return {"base": base, "rutas": elementos}


def huella_de(detalle: dict) -> str:
    texto = json.dumps({"base": detalle["base"], "rutas": detalle["rutas"]}, sort_keys=True)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def huella_cambios(directorio: str = DIRECTORIO_PROYECTO) -> str:
    return huella_de(detalle_cambios(directorio))


# --- registro de suites (Hito 2BH) ------------------------------------------
#
# Norma de Pio de tests antes de commit (REGLAS_CRITICAS, «Pruebas»): suite completa con pg17_local si el
# commit toca algo distinto de documentación; suite rápida si solo toca documentación. pytest añade una línea
# por ejecución a ``logs/agentes/suites.jsonl`` (tests/registro_suite.py) con la huella exacta del árbol
# probado; la barrera de commit la exige.

NOMBRE_SUITES = "suites.jsonl"
ALCANCES = ("parcial", "rapida", "completa", "historica", "total")


def ruta_suites() -> str:
    return os.path.join(directorio_logs(), NOMBRE_SUITES)


def solo_documentacion(rutas: list[str]) -> bool:
    """Documentación = ficheros ``.md`` fuera de ``.claude/`` (las definiciones de agentes no cuentan)."""
    return all(r.replace("\\", "/").lower().endswith(".md")
               and not r.replace("\\", "/").startswith(".claude/") for r in rutas)


def suite_exigida(rutas: list[str]) -> str:
    return "rapida" if solo_documentacion(rutas) else "completa"


def suite_valida(huella: str, exigida: str, ruta: str | None = None,
                 repositorio: str = DIRECTORIO_PROYECTO) -> dict | None:
    """Última ejecución registrada sobre ``huella`` con alcance suficiente (``CUBRE``), o None.

    Una ejecución de menor alcance posterior no la invalida; una de alcance suficiente posterior sí (si
    falla, la última manda). Hito SUITE: para commits, ``suites_para_commit``.
    """
    return _ultima(_registros_suite(ruta, repositorio), huella, exigida)


# --- Hito SUITE: completa sin histórica, reparación e histórica ---------------
#
# pruebas/auditoria_suite/DISENO.md (decisiones de Pio D1-D8, 2026-11-20). Alcances del registro:
# ``total`` (sin -m), ``completa`` (-m "not historica"), ``historica`` (-m historica), ``rapida`` y ``parcial``.

CUBRE = {"rapida": ("rapida", "completa", "total"), "completa": ("completa", "total"),
         "historica": ("historica", "total")}
INFRAESTRUCTURA_TESTS = ("tests/conftest.py", "tests/facturas/runtime_supabase/pg17_local.py",
                         "tests/registro_suite.py", "tests/consultar_suite.py")
CONFTEST_HISTORICA = "tests/facturas/runtime_supabase/conftest.py"
MAXIMO_FALLADOS_REPETICION = 3
DIAS_HISTORICA = 7
_RUTAS_HISTORICA = re.compile(
    r"^(sql/|tests/facturas/runtime_supabase/(pg17_local|conftest)\.py$|pruebas/auditoria_2at/"
    r"|pruebas/.*/(desplegar_[^/]*|preflight[^/]*)\.py$|src/facturas/runtime_supabase/puerta_git\.py$)")


def _registros_suite(ruta: str | None, repositorio: str) -> list[dict]:
    clave = clave_repositorio(repositorio)
    return [r for r in leer_uso(ruta or ruta_suites()) if r.get("repositorio") == clave]


def _ultima(registros: list[dict], huella: str, exigida: str) -> dict | None:
    validas = [r for r in registros if r.get("huella") == huella and r.get("alcance") in CUBRE[exigida]]
    return validas[-1] if validas else None


def modulos_historicos(repositorio: str = DIRECTORIO_PROYECTO) -> set[str]:
    """Módulos con tests de ``SUITE_HISTORICA`` (leído con ``ast``, sin importar el conftest)."""
    import ast
    try:
        with open(os.path.join(repositorio, CONFTEST_HISTORICA), encoding="utf-8") as archivo:
            arbol = ast.parse(archivo.read())
        for nodo in arbol.body:
            if isinstance(nodo, ast.Assign) and any(getattr(t, "id", None) == "SUITE_HISTORICA"
                                                    for t in nodo.targets):
                return {f"tests/facturas/runtime_supabase/{m}" for m in ast.literal_eval(nodo.value)}
    except (OSError, SyntaxError, ValueError):
        pass
    return set()


def historica_exigida(rutas: list[str], repositorio: str = DIRECTORIO_PROYECTO) -> str:
    """``exacta`` si el cambio toca rutas de despliegue o módulos históricos; si no, ``semanal``."""
    modulos = modulos_historicos(repositorio)
    normalizadas = [r.replace("\\", "/") for r in rutas]
    if any(_RUTAS_HISTORICA.search(r) or r in modulos for r in normalizadas) or not modulos:
        return "exacta"
    return "semanal"


def _fecha(texto) -> "datetime.datetime | None":
    import datetime
    try:
        fecha = datetime.datetime.fromisoformat(str(texto))
    except ValueError:
        return None
    return fecha if fecha.tzinfo else None


def historica_valida(huella: str, modo: str, ruta: str | None = None, repositorio: str = DIRECTORIO_PROYECTO,
                     ahora=None) -> dict | None:
    """``exacta``: la última histórica (o total) sobre la huella. ``semanal``: la última histórica (o total) del
    repositorio, si terminó hace 7 días o menos. Devuelve la línea (verde o no) o None."""
    import datetime
    registros = _registros_suite(ruta, repositorio)
    if modo == "exacta":
        return _ultima(registros, huella, "historica")
    historicas = [r for r in registros if r.get("alcance") in CUBRE["historica"] and r.get("huella")]
    if not historicas:
        return None
    ultima = historicas[-1]
    fin = _fecha(ultima.get("ts_fin"))
    ahora = ahora or datetime.datetime.now(datetime.timezone.utc)
    if fin is None or ahora - fin > datetime.timedelta(days=DIAS_HISTORICA):
        return None
    return ultima


def _diferencias(rutas_a: list, rutas_b: list) -> set[str]:
    a = {r[0]: r[1] for r in rutas_a or []}
    b = {r[0]: r[1] for r in rutas_b or []}
    return {r for r in set(a) | set(b) if a.get(r) != b.get(r)}


def _es_modulo_de_test(ruta: str) -> bool:
    ruta = ruta.replace("\\", "/")
    return (ruta.startswith("tests/") and ruta not in INFRAESTRUCTURA_TESTS
            and os.path.basename(ruta).startswith("test_") and ruta.endswith(".py"))


def _cubre_modulo(parcial: dict, modulo: str) -> bool:
    """La parcial ejecutó el módulo entero: lo pasó como argumento, sin -k/-m ni deseleccionados, y todo lo
    colectado se ejecutó."""
    args = [str(a).replace("\\", "/").rstrip("/") for a in parcial.get("args") or []]
    nodeids = parcial.get("nodeids") or []
    return (any(a == modulo or a.endswith("/" + modulo) or modulo.endswith("/" + a) and a.endswith(".py")
                for a in args)
            and not parcial.get("keyword") and not parcial.get("markexpr") and not parcial.get("deselected")
            and parcial.get("ejecutados") == parcial.get("colectados")
            and any(n.split("::", 1)[0] == modulo for n in nodeids))


def completa_valida(detalle: dict, ruta: str | None = None, repositorio: str = DIRECTORIO_PROYECTO) -> dict | None:
    """Suite completa sobre el estado exacto, directa o por la regla de reparación (DISENO §2.4).

    Devuelve la línea que vale (con ``via``: ``directa``, ``reparacion_a`` o ``reparacion_b``) o, si no vale
    ninguna, la última completa sobre la huella (roja) o None.
    """
    huella = huella_de(detalle)
    registros = _registros_suite(ruta, repositorio)
    directa = _ultima(registros, huella, "completa")
    if directa is not None and directa.get("verde"):
        return {**directa, "via": "directa"}
    indices = [i for i, r in enumerate(registros) if r.get("alcance") in CUBRE["completa"]
               and r.get("base") == detalle["base"] and r.get("huella")]
    if not indices:
        return directa
    i0 = indices[-1]
    origen = registros[i0]
    fallados = origen.get("fallados") or []
    if origen.get("verde") or not fallados:
        return directa
    parciales = [r for r in registros[i0 + 1:] if r.get("alcance") == "parcial" and r.get("huella") == huella
                 and r.get("base") == detalle["base"]]
    if not parciales:
        return directa
    if origen.get("huella") == huella:
        primera = parciales[0]
        if (len(fallados) <= MAXIMO_FALLADOS_REPETICION and primera.get("verde")
                and set(fallados) <= set(primera.get("nodeids") or [])):
            return {**primera, "via": "reparacion_a"}
        return directa
    cambiadas = _diferencias(origen.get("rutas"), detalle["rutas"])
    if not cambiadas or not all(_es_modulo_de_test(r) for r in cambiadas):
        return directa
    ultima = parciales[-1]
    vivos = [r.replace("\\", "/") for r in cambiadas
             if dict((x[0], x[1]) for x in detalle["rutas"]).get(r) != "BORRADO"]
    if (ultima.get("verde") and set(fallados) <= set(ultima.get("nodeids") or [])
            and all(_cubre_modulo(ultima, m) for m in vivos)):
        return {**ultima, "via": "reparacion_b"}
    return directa


def suites_para_commit(rutas: list[str], ruta: str | None = None, repositorio: str = DIRECTORIO_PROYECTO,
                       detalle: dict | None = None, ahora=None) -> dict:
    """Lo que exige la barrera de commit (y T2) sobre el estado exacto de los cambios.

    Documentación: la rápida (o más). Código: la completa (directa o por reparación) en verde y la histórica en
    verde, sobre la misma huella si el cambio toca rutas de despliegue o módulos históricos, o de 7 días o menos.
    """
    detalle = detalle if detalle is not None else detalle_cambios(repositorio)
    huella = huella_de(detalle)
    exigida = suite_exigida(rutas)
    if exigida == "rapida":
        suite = _ultima(_registros_suite(ruta, repositorio), huella, "rapida")
        return {"exigida": exigida, "suite": suite, "historica_modo": None, "historica": None,
                "ok": bool(suite and suite.get("verde"))}
    suite = completa_valida(detalle, ruta, repositorio)
    modo = historica_exigida(rutas, repositorio)
    historica = historica_valida(huella, modo, ruta, repositorio, ahora)
    return {"exigida": exigida, "suite": suite, "historica_modo": modo, "historica": historica,
            "ok": bool(suite and suite.get("verde") and historica and historica.get("verde"))}


RE_DESPLIEGUE = re.compile(r"\bpython[\w.]*\s[^|;&]*\bdesplegar_\d+(\.py)?\b")


def es_despliegue(texto: str) -> bool:
    """Ejecución de un script ``desplegar_<n>`` (no una lectura ni pytest)."""
    texto = texto.casefold()
    return bool(RE_DESPLIEGUE.search(texto)) and "pytest" not in texto


def leer_uso(ruta: str | None = None) -> list[dict]:
    ruta = ruta or ruta_uso()
    registros = []
    try:
        with open(ruta, encoding="utf-8") as archivo:
            for linea in archivo:
                try:
                    registro = json.loads(linea)
                except ValueError:
                    continue
                if isinstance(registro, dict):
                    registros.append(registro)
    except FileNotFoundError:
        pass
    return registros


def clave_repositorio(raiz: str) -> str:
    return os.path.normcase(os.path.realpath(raiz))


CONTADORES = ("peticiones_api", "llamadas_herramientas", "herramientas_bloqueadas")


def _sumar_tokens(ejecuciones: list[dict]) -> dict:
    total: dict[str, int] = {}
    for ejecucion in ejecuciones:
        for clave, valor in (ejecucion.get("tokens") or {}).items():
            if isinstance(valor, int):
                total[clave] = total.get(clave, 0) + valor
    return total


def _sumar_coste(ejecuciones: list[dict]) -> dict | None:
    costes = [e["coste"] for e in ejecuciones if isinstance(e.get("coste"), dict)]
    if not costes:
        return None
    return {
        "usd": round(sum(c.get("usd", 0) for c in costes), 4),
        "eur": round(sum(c.get("eur", 0) for c in costes), 4),
        "parcial": len(costes) < len(ejecuciones),
    }


def _veredicto_grupo(lineas: list[dict]) -> str:
    """Veredicto de una huella (ver ``agrupar_revisiones``).

    PASS si cada línea es PASS, o es un FAIL solo por T2 seguido de un PASS, o es un INCONCLUSO seguido de un PASS
    (DECISIÓN DE PIO, 2026-11-14). Cualquier otro FAIL manda (``FAIL``); si no lo hay, un INCONCLUSO sin PASS
    posterior deja la huella ``INCONCLUSO``. Ambos bloquean el commit.
    """
    pases = [i for i, r in enumerate(lineas) if r.get("veredicto") == "PASS"]
    inconcluso = False
    for i, registro in enumerate(lineas):
        veredicto = registro.get("veredicto")
        if veredicto == "PASS":
            continue
        pase_posterior = bool(pases) and pases[-1] > i
        if veredicto == "INCONCLUSO":
            inconcluso = inconcluso or not pase_posterior
            continue
        if not (registro.get("reglas_fail") == ["T2"] and pase_posterior):
            return "FAIL"
    return "INCONCLUSO" if inconcluso else "PASS"


def agrupar_revisiones(registros: list[dict], repositorio_por_defecto: str = DIRECTORIO_PROYECTO) -> list[dict]:
    """Revisiones de revisor-reglas agrupadas por (repositorio, huella) al leer.

    ``uso.jsonl`` es append-only: cada SubagentStop añade una línea, y un mismo
    subagente puede parar varias veces con el uso acumulado de su transcript
    (16 líneas en la revisión de bbee3e2, 2026-10-23). Un grupo es una
    revisión; dentro, una ejecución por ``agent_id`` con su última línea, que
    ya es el acumulado. Tokens, coste y contadores suman las ejecuciones, nunca
    las líneas repetidas. Veredicto PASS solo si todas las líneas del grupo son
    PASS (decisión de Pio, 2026-10-27), con una excepción (Pio, 2026-11-02): un
    FAIL cuya única regla fallida es T2 (``reglas_fail == ["T2"]``) no cuenta si
    hay un PASS posterior de la misma huella. La suite registrada la sigue
    exigiendo ``barrera_commit``. Cualquier otro FAIL, o uno sin
    ``reglas_fail`` (registros anteriores), sigue contando. Un INCONCLUSO
    (un bloqueo impidió comprobar alguna regla; Pio, 2026-11-14) tampoco
    cuenta si hay un PASS posterior de la misma huella.

    Las líneas sin huella (p. ej. transcript no disponible) no forman grupo.
    Orden: por la última línea de cada grupo.
    """

    defecto = clave_repositorio(repositorio_por_defecto)
    grupos: dict[tuple[str, str], dict] = {}
    for indice, registro in enumerate(registros):
        if registro.get("agent_type") != AGENTE_REVISOR or not registro.get("huella_cambios"):
            continue
        clave = (registro.get("repositorio", defecto), registro["huella_cambios"])
        grupo = grupos.setdefault(clave, {"lineas": [], "ejecuciones": {}})
        grupo["lineas"].append(registro)
        grupo["ultima"] = indice
        ejecucion = registro.get("agent_id") or f"sin_agent_id:{indice}"
        anterior = grupo["ejecuciones"].get(ejecucion)
        grupo["ejecuciones"][ejecucion] = {
            "registro": registro,
            "paradas": (anterior["paradas"] if anterior else 0) + 1,
        }

    revisiones = []
    for (repositorio, huella), grupo in sorted(grupos.items(), key=lambda item: item[1]["ultima"]):
        lineas = grupo["lineas"]
        ultimas = [e["registro"] for e in grupo["ejecuciones"].values()]
        revision = {
            "agent_type": AGENTE_REVISOR,
            "repositorio": repositorio,
            "huella_cambios": huella,
            "ts_inicio": lineas[0].get("ts"),
            "ts": lineas[-1].get("ts"),
            "veredicto": _veredicto_grupo(lineas),
            "ejecuciones": len(ultimas),
            "lineas": len(lineas),
            "paradas_por_ejecucion": {k: e["paradas"] for k, e in grupo["ejecuciones"].items()},
            "modelo": lineas[-1].get("modelo"),
            "tarea": lineas[-1].get("tarea"),
            "resultado": lineas[-1].get("resultado"),
            "tokens": _sumar_tokens(ultimas),
            "coste": _sumar_coste(ultimas),
        }
        for contador in CONTADORES:
            revision[contador] = sum(r.get(contador) or 0 for r in ultimas)
        revisiones.append(revision)
    return revisiones


def resumen_uso(registros: list[dict]) -> list[dict]:
    """Registros para métricas: revisiones agrupadas y el resto tal cual."""

    otros = [
        r for r in registros
        if r.get("agent_type") != AGENTE_REVISOR or not r.get("huella_cambios")
    ]
    return otros + agrupar_revisiones(registros)


def revision_de_huella(huella: str, ruta: str | None = None, repositorio: str = DIRECTORIO_PROYECTO) -> dict | None:
    """Revisión agrupada de ``huella`` sobre ``repositorio``, o None.

    Los veredictos de otros repositorios (worktrees temporales) se ignoran; un
    registro sin repositorio cuenta como del proyecto.
    """

    clave = clave_repositorio(repositorio)
    for revision in agrupar_revisiones(leer_uso(ruta), repositorio):
        if revision["repositorio"] == clave and revision["huella_cambios"] == huella:
            return revision
    return None


def hay_revisiones(ruta: str | None = None, repositorio: str = DIRECTORIO_PROYECTO) -> bool:
    clave = clave_repositorio(repositorio)
    return any(
        r.get("agent_type") == AGENTE_REVISOR and r.get("repositorio", clave) == clave
        for r in leer_uso(ruta)
    )


if __name__ == "__main__":
    # Resumen de métricas: python estado_git.py [ruta de uso.jsonl]
    import sys

    for registro in resumen_uso(leer_uso(sys.argv[1] if len(sys.argv) > 1 else None)):
        print(json.dumps(registro, ensure_ascii=False))
