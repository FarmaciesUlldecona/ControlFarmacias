"""Hook SubagentStop de Claude Code: registro de uso por subagente.

Al terminar cada subagente añade una línea JSON a ``logs/agentes/uso.jsonl``
con fecha, tipo de agente, modelo, tarea (inicio del encargo), tokens reales
(sumados una vez por petición a la API, a partir del transcript del
subagente), número de llamadas a herramientas, herramientas bloqueadas y
resultado (inicio de la respuesta final).

Para ``revisor-reglas`` registra además el veredicto (``PASS``/``FAIL``/``INCONCLUSO``,
leído de la línea ``VEREDICTO:`` de su respuesta y contrastado con su tabla), las
reglas con ``FAIL`` y con ``INCONCLUSO`` de su tabla (``reglas_fail``,
``reglas_inconclusas``) y la huella de los cambios en ese momento;
``barreras_agentes.py`` exige ese PASS con la misma huella antes de permitir
``git commit``.

Nunca bloquea: cualquier error se registra como ``error`` y devuelve 0.
Solo usa la biblioteca estándar.
"""

import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import estado_git  # noqa: E402


LONGITUD_TEXTO = 300
CLAVES_TOKENS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)
CLAVES_CACHE_ESCRITURA = ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")
RUTA_POLITICA = os.path.join(estado_git.DIRECTORIO_PROYECTO, ".claude", "agentes", "politica.json")


def _coste_peticion_usd(tokens: dict, precios: dict) -> float:
    # Tramo de contexto largo (Haiku 5.5: prompts de más de 100.000 tokens).
    tramo = precios.get("tramo_largo")
    prompt = tokens["input_tokens"] + tokens["cache_creation_input_tokens"] + tokens["cache_read_input_tokens"]
    if tramo and prompt > tramo["umbral_prompt"]:
        precios = tramo
    escritura_1h = tokens.get("ephemeral_1h_input_tokens", 0)
    escritura_5m = tokens["cache_creation_input_tokens"] - escritura_1h
    return (
        tokens["input_tokens"] * precios["entrada"]
        + tokens["output_tokens"] * precios["salida"]
        + tokens["cache_read_input_tokens"] * precios["cache_lectura"]
        + escritura_5m * precios["cache_escritura_5m"]
        + escritura_1h * precios["cache_escritura_1h"]
    ) / 1_000_000


def calcular_coste(modelo, peticiones: list[dict], metricas: dict) -> dict | None:
    """Coste en USD y EUR, petición a petición, con la caché a su precio.

    La escritura de caché sin desglose se cuenta a la tarifa de 5 minutos.
    ``precios`` dice si la tarifa del modelo está verificada contra la página
    oficial (con fecha) o es estimada.
    """

    precios = metricas.get("precios_usd_por_mtok", {}).get(modelo)
    if not precios:
        return None
    usd = sum(_coste_peticion_usd(tokens, precios) for tokens in peticiones)
    verificado = precios.get("verificado")
    return {
        "usd": round(usd, 4),
        "eur": round(usd * metricas["eur_por_usd"], 4),
        "eur_por_usd": metricas["eur_por_usd"],
        "precios": f"VERIFICADOS {verificado}" if verificado else "ESTIMADOS",
    }


def cargar_metricas(ruta: str = RUTA_POLITICA) -> dict:
    with open(ruta, encoding="utf-8") as archivo:
        return json.load(archivo).get("metricas", {})


RE_VEREDICTO = re.compile(r"^\s*\**\s*VEREDICTO\s*:?\s*\**\s*:?\s*(PASS|FAIL|INCONCLUSO)\b",
                          re.IGNORECASE | re.MULTILINE)
# Fila de la tabla del revisor: ``| T2 | FAIL | ...`` (Id, Resultado). Primera celda: cualquier texto.
RE_FILA_REGLA = re.compile(r"^\s*\|([^|\n]*)\|([^|\n]*)\|", re.MULTILINE)
RE_ID_REGLA = re.compile(r"^[\s*`]*([A-Za-z]\d+)[\s*`]*$")
RE_RESULTADO = re.compile(r"^[\s*`]*(PASS|FAIL|N/A|INCONCLUSO)[\s*`]*$", re.IGNORECASE)
# Reglas de la tabla obligatoria de .claude/agents/revisor-reglas.md.
REGLAS_REVISOR = frozenset({"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "E1", "P1", "M1", "T1", "T2", "C1"})


def resultados_tabla(respuesta: str) -> dict[str, str] | None:
    """Resultado de cada regla en la tabla del revisor (``PASS``, ``FAIL``, ``N/A`` o ``INCONCLUSO``).

    Fallo cerrado: None (sin detalle) si alguna fila de regla no tiene un resultado reconocido, si una regla
    aparece dos veces o si falta alguna de ``REGLAS_REVISOR``; así un FAIL mal escrito nunca se pierde.
    """
    resultados: dict[str, str] = {}
    for celda_id, celda_resultado in RE_FILA_REGLA.findall(respuesta):
        identificador = RE_ID_REGLA.match(celda_id)
        if not identificador:
            continue
        regla = identificador.group(1).upper()
        resultado = RE_RESULTADO.match(celda_resultado)
        if not resultado or regla in resultados:
            return None
        resultados[regla] = resultado.group(1).upper()
    if set(resultados) != REGLAS_REVISOR:
        return None
    return resultados


def reglas_fail(respuesta: str) -> list[str] | None:
    """Ids de las reglas con resultado FAIL en la tabla del revisor (None si la tabla no es fiable)."""
    resultados = resultados_tabla(respuesta)
    if resultados is None:
        return None
    return sorted(regla for regla, resultado in resultados.items() if resultado == "FAIL")


def veredicto_revisor(respuesta: str) -> str:
    """``PASS``, ``INCONCLUSO`` o ``FAIL`` (DECISIÓN DE PIO, 2026-11-14).

    ``INCONCLUSO``: un bloqueo impidió comprobar alguna regla. Solo vale con la tabla completa y fiable, al menos
    una regla ``INCONCLUSO`` y ninguna ``FAIL``. Fallo cerrado: varios veredictos, ninguno, una tabla con algún
    ``FAIL`` o un ``INCONCLUSO`` sin tabla fiable cuentan como ``FAIL``; un ``PASS`` cuya tabla fiable trae alguna
    regla ``INCONCLUSO`` cuenta como ``INCONCLUSO``.
    """
    veredictos = {c.upper() for c in RE_VEREDICTO.findall(respuesta)}
    if len(veredictos) != 1:
        return "FAIL"
    [declarado] = veredictos
    resultados = resultados_tabla(respuesta)
    if resultados is not None and "FAIL" in resultados.values():
        return "FAIL"
    if declarado == "INCONCLUSO":
        return "INCONCLUSO" if resultados is not None and "INCONCLUSO" in resultados.values() else "FAIL"
    if declarado == "PASS" and resultados is not None and "INCONCLUSO" in resultados.values():
        return "INCONCLUSO"
    return declarado


def texto_de(contenido) -> str:
    if isinstance(contenido, str):
        return contenido
    if isinstance(contenido, list):
        return "\n".join(
            bloque.get("text", "")
            for bloque in contenido
            if isinstance(bloque, dict) and bloque.get("type") == "text"
        )
    return ""


def resumir(texto: str) -> str:
    texto = " ".join(texto.split())
    return texto[:LONGITUD_TEXTO]


def analizar_transcript(ruta: str) -> dict:
    # Una petición a la API aparece en varias entradas (una por bloque de
    # contenido) y su uso crece mientras se emite: se toma el máximo de cada
    # campo por petición y después se suman las peticiones.
    por_peticion: dict[str, dict[str, int]] = {}
    modelo = None
    tarea = None
    respuesta = ""
    llamadas = 0
    bloqueos = 0

    with open(ruta, encoding="utf-8") as archivo:
        for linea in archivo:
            try:
                registro = json.loads(linea)
            except ValueError:
                continue
            if not isinstance(registro, dict):
                continue
            mensaje = registro.get("message")
            if not isinstance(mensaje, dict):
                continue
            tipo = registro.get("type")

            if tipo == "user" and tarea is None and not registro.get("isMeta"):
                texto = texto_de(mensaje.get("content"))
                if texto:
                    tarea = texto

            if tipo == "user" and isinstance(mensaje.get("content"), list):
                for bloque in mensaje["content"]:
                    if (isinstance(bloque, dict) and bloque.get("type") == "tool_result"
                            and bloque.get("is_error")
                            and "BLOQUEADO" in texto_de(bloque.get("content")) + str(bloque.get("content"))):
                        bloqueos += 1

            if tipo == "assistant":
                modelo = mensaje.get("model") or modelo
                peticion = registro.get("requestId") or mensaje.get("id")
                uso = mensaje.get("usage")
                if isinstance(uso, dict):
                    acumulado = por_peticion.setdefault(
                        peticion, dict.fromkeys(CLAVES_TOKENS + CLAVES_CACHE_ESCRITURA, 0)
                    )
                    detalle = uso.get("cache_creation") if isinstance(uso.get("cache_creation"), dict) else {}
                    for clave in CLAVES_TOKENS + CLAVES_CACHE_ESCRITURA:
                        valor = uso.get(clave, detalle.get(clave))
                        if isinstance(valor, int):
                            acumulado[clave] = max(acumulado[clave], valor)
                contenido = mensaje.get("content")
                if isinstance(contenido, list):
                    llamadas += sum(
                        1 for b in contenido
                        if isinstance(b, dict) and b.get("type") == "tool_use"
                    )
                texto = texto_de(contenido)
                if texto.strip():
                    respuesta = texto

    tokens = {
        clave: sum(uso[clave] for uso in por_peticion.values())
        for clave in CLAVES_TOKENS + CLAVES_CACHE_ESCRITURA
    }
    return {
        "modelo": modelo,
        "tarea": tarea or "",
        "respuesta": respuesta,
        "tokens": tokens,
        "por_peticion": list(por_peticion.values()),
        "peticiones_api": len(por_peticion),
        "llamadas_herramientas": llamadas,
        "herramientas_bloqueadas": bloqueos,
    }


def respuesta_handback(ruta: str) -> str:
    """Texto entregado con SubagentHandback, si el subagente lo usó."""

    texto = ""
    with open(ruta, encoding="utf-8") as archivo:
        for linea in archivo:
            try:
                registro = json.loads(linea)
            except ValueError:
                continue
            mensaje = registro.get("message") if isinstance(registro, dict) else None
            if not isinstance(mensaje, dict) or registro.get("type") != "assistant":
                continue
            for bloque in mensaje.get("content") or []:
                if (isinstance(bloque, dict) and bloque.get("type") == "tool_use"
                        and bloque.get("name") == "SubagentHandback"):
                    entrada = bloque.get("input") or {}
                    for valor in entrada.values():
                        if isinstance(valor, str) and len(valor) > len(texto):
                            texto = valor
    return texto


def coste_por_defecto(modelo, peticiones: list[dict]) -> dict | None:
    try:
        return calcular_coste(modelo, peticiones, cargar_metricas())
    except (OSError, ValueError, KeyError, TypeError):
        return None


def construir_registro(entrada: dict, huella=estado_git.huella_cambios, coste=coste_por_defecto) -> dict:
    agente = entrada.get("agent_type")
    registro = {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "agent_type": agente,
        "agent_id": entrada.get("agent_id"),
        "session_id": entrada.get("session_id"),
    }
    ruta = entrada.get("agent_transcript_path")
    if not isinstance(ruta, str) or not os.path.isfile(ruta):
        registro["error"] = "transcript_no_disponible"
        return registro

    datos = analizar_transcript(ruta)
    respuesta = respuesta_handback(ruta) or datos["respuesta"]
    registro.update({
        "modelo": datos["modelo"],
        "tarea": resumir(datos["tarea"]),
        "tokens": datos["tokens"],
        "coste": coste(datos["modelo"], datos["por_peticion"]),
        "peticiones_api": datos["peticiones_api"],
        "llamadas_herramientas": datos["llamadas_herramientas"],
        "herramientas_bloqueadas": datos["herramientas_bloqueadas"],
        "resultado": resumir(respuesta),
    })

    if agente == estado_git.AGENTE_REVISOR:
        # Una respuesta con varios veredictos, o sin ninguno, cuenta como FAIL.
        registro["veredicto"] = veredicto_revisor(respuesta)
        resultados = resultados_tabla(respuesta)
        if resultados is not None:
            registro["reglas_fail"] = sorted(r for r, v in resultados.items() if v == "FAIL")
            registro["reglas_inconclusas"] = sorted(r for r, v in resultados.items() if v == "INCONCLUSO")
        # La huella es la del repositorio que revisó el subagente (puede ser un
        # worktree temporal), nunca la del proyecto por defecto.
        raiz = estado_git.raiz_repositorio(entrada.get("cwd") or estado_git.DIRECTORIO_PROYECTO)
        registro["repositorio"] = estado_git.clave_repositorio(raiz)
        registro["huella_cambios"] = huella(raiz)

    return registro


def main() -> int:
    try:
        entrada = json.loads(sys.stdin.buffer.read())
        if not isinstance(entrada, dict):
            raise ValueError("la entrada del hook no es un objeto")
        registro = construir_registro(entrada)
    except BaseException as error:
        registro = {
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "error": f"{type(error).__name__}",
        }
    try:
        ruta = estado_git.ruta_uso()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "a", encoding="utf-8", newline="\n") as archivo:
            archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except BaseException:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
