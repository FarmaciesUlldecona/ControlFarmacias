"""Hook SubagentStop de Claude Code: registro de uso por subagente.

Al terminar cada subagente añade una línea JSON a ``logs/agentes/uso.jsonl``
con fecha, tipo de agente, modelo, tarea (inicio del encargo), tokens reales
(sumados una vez por petición a la API, a partir del transcript del
subagente), número de llamadas a herramientas, herramientas bloqueadas y
resultado (inicio de la respuesta final).

Para ``revisor-reglas`` registra además el veredicto (``PASS``/``FAIL``, leído
de la línea ``VEREDICTO:`` de su respuesta) y la huella de los cambios en ese
momento; ``barreras_agentes.py`` exige ese PASS con la misma huella antes de
permitir ``git commit``.

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


RE_VEREDICTO = re.compile(r"^\s*\**\s*VEREDICTO\s*:?\s*\**\s*:?\s*(PASS|FAIL)\b", re.IGNORECASE | re.MULTILINE)


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
        coincidencias = RE_VEREDICTO.findall(respuesta)
        # Una respuesta con varios veredictos, o sin ninguno, cuenta como FAIL.
        veredictos = {c.upper() for c in coincidencias}
        registro["veredicto"] = "PASS" if veredictos == {"PASS"} else "FAIL"
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
