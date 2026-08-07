from __future__ import annotations

from collections import Counter
import json
import re
from pathlib import Path
from typing import Any
import unicodedata


RAIZ = Path(__file__).resolve().parents[2]
RUTA_PATRON = (
    RAIZ
    / "pruebas/facturas/patron"
    / "pruebas_lectura_facturas_resultado_esperado_PATRON_OFICIAL_v1_0.json"
)
RUTA_NORMALIZADA = (
    RAIZ
    / "pruebas/facturas/resultados/openai/normalizacion_fedefarma"
    / "factura_normalizada.json"
)
RUTA_BASE = (
    RAIZ
    / "pruebas/facturas/resultados/openai/benchmark_luna_terra_sol_v1"
    / "evaluacion/general/caso_04/gpt-5.6-luna.json"
)
RUTA_GENERAL = (
    RAIZ
    / "pruebas/facturas/resultados/openai/benchmark_luna_terra_sol_v1"
    / "general/caso_04/gpt-5.6-luna/estructurado.json"
)
RUTA_LITERAL = (
    RAIZ
    / "pruebas/facturas/resultados/openai/fedefarma_tablas_literales"
    / "estructurado.json"
)
RUTA_METRICAS_LITERAL = RUTA_LITERAL.with_name("metricas.json")
RUTA_SALIDA = RUTA_NORMALIZADA.parent
RUTAS_PRODUCCION = (
    RAIZ / "src/facturas/normalizadores/fedefarma.py",
    RAIZ / "src/facturas/normalizar_fedefarma.py",
    RAIZ / "src/facturas/motores/openai/extraer_tablas_fedefarma.py",
)


def cargar(ruta: Path) -> dict[str, Any]:
    if not ruta.is_file():
        raise FileNotFoundError(f"No se encuentra el archivo requerido: {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def simplificar(valor: Any) -> Any:
    if not isinstance(valor, str):
        return valor
    sin_tildes = "".join(
        x
        for x in unicodedata.normalize("NFD", valor)
        if unicodedata.category(x) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().casefold()


def atomos(valor: Any, prefijo: str = "") -> dict[str, Any]:
    if isinstance(valor, dict):
        resultado = {}
        for clave, dato in valor.items():
            if clave in {"procedencia", "pagina", "seccion", "orden_reconstruido"}:
                continue
            ruta = f"{prefijo}.{clave}" if prefijo else clave
            resultado.update(atomos(dato, ruta))
        return resultado
    if isinstance(valor, list):
        if not valor:
            return {prefijo: []}
        resultado = {}
        for indice, dato in enumerate(valor):
            resultado.update(atomos(dato, f"{prefijo}[{indice}]"))
        return resultado
    return {prefijo: valor}


def comparar(campo: str, esperado: Any, obtenido: Any) -> dict[str, Any]:
    esperados = atomos(esperado, campo)
    obtenidos = atomos(obtenido, campo)
    detalles = []
    conteo = Counter()
    for ruta in sorted(set(esperados) | set(obtenidos)):
        valor_esperado = esperados.get(ruta)
        valor_obtenido = obtenidos.get(ruta)
        if valor_esperado == valor_obtenido:
            estado = "CORRECTO"
        elif valor_obtenido is None or valor_obtenido == []:
            estado = "AUSENTE"
        elif valor_esperado is None or valor_esperado == []:
            estado = "INVENTADO"
        elif simplificar(valor_esperado) == simplificar(valor_obtenido):
            estado = "DIFERENCIA_FORMATO"
        else:
            estado = "INCORRECTO"
        conteo[estado] += 1
        detalles.append(
            {
                "ruta": ruta,
                "esperado": valor_esperado,
                "obtenido": valor_obtenido,
                "estado": estado,
            }
        )
    if set(conteo) == {"CORRECTO"}:
        estado_campo = "CORRECTO"
    elif conteo["INVENTADO"] and not (conteo["CORRECTO"] or conteo["INCORRECTO"]):
        estado_campo = "INVENTADO"
    elif conteo["AUSENTE"] == sum(conteo.values()):
        estado_campo = "AUSENTE"
    elif conteo["CORRECTO"] or conteo["DIFERENCIA_FORMATO"]:
        estado_campo = "PARCIAL"
    else:
        estado_campo = "INCORRECTO"
    return {
        "campo": campo,
        "estado": estado_campo,
        "esperado": esperado,
        "obtenido": obtenido,
        "conteo_atomico": dict(conteo),
        "detalles": detalles,
    }


def verificar_aislamiento() -> dict[str, Any]:
    prohibidos = ("PATRON_OFICIAL", "facturas/patron", "cargar_patron", "evaluar_")
    hallazgos = []
    for ruta in RUTAS_PRODUCCION:
        texto = ruta.read_text(encoding="utf-8").replace("\\", "/").casefold()
        for prohibido in prohibidos:
            if prohibido.casefold() in texto:
                hallazgos.append({"archivo": str(ruta), "referencia": prohibido})
    return {"cumple": not hallazgos, "hallazgos": hallazgos}


def evaluar_albaranes(esperados: list[dict], obtenidos: list[dict]) -> dict[str, int]:
    numeros_esperados = [x.get("numero_albaran") for x in esperados]
    numeros_obtenidos = [x.get("numero_albaran") for x in obtenidos]
    conteo = Counter(numeros_obtenidos)
    por_numero_esperado = {x.get("numero_albaran"): x for x in esperados}
    por_numero_obtenido = {x.get("numero_albaran"): x for x in obtenidos}
    comunes = set(por_numero_esperado) & set(por_numero_obtenido)
    return {
        "esperados": len(esperados),
        "obtenidos": len(obtenidos),
        "numeros_correctos": len(comunes),
        "fechas_correctas": sum(
            por_numero_esperado[x].get("fecha_albaran")
            == por_numero_obtenido[x].get("fecha_albaran")
            for x in comunes
        ),
        "bases_correctas": sum(
            por_numero_esperado[x].get("importe_base")
            == por_numero_obtenido[x].get("importe_base")
            for x in comunes
        ),
        "totales_correctos": sum(
            por_numero_esperado[x].get("importe_total")
            == por_numero_obtenido[x].get("importe_total")
            for x in comunes
        ),
        "ausentes": len(set(numeros_esperados) - set(numeros_obtenidos)),
        "duplicados": sum(x - 1 for x in conteo.values() if x > 1),
        "inventados": len(set(numeros_obtenidos) - set(numeros_esperados)),
    }


def evaluar() -> tuple[Path, Path]:
    aislamiento = verificar_aislamiento()
    if not aislamiento["cumple"]:
        raise RuntimeError(
            f"Produccion contiene referencias prohibidas: {aislamiento['hallazgos']}"
        )
    documento = cargar(RUTA_NORMALIZADA)
    obtenido = documento["resultado_normalizado"]
    patron = cargar(RUTA_PATRON)
    candidatos = [
        x for x in patron["documentos"] if x["archivo"] == documento["archivo_origen"]
    ]
    if len(candidatos) != 1 or len(candidatos[0]["facturas"]) != 1:
        raise RuntimeError("No se encontro exactamente un documento FEDEFARMA evaluable.")
    esperado = candidatos[0]["facturas"][0]
    campos = sorted(set(esperado) | set(obtenido))
    comparaciones = [
        comparar(campo, esperado.get(campo), obtenido.get(campo)) for campo in campos
    ]
    conteo = Counter(x["estado"] for x in comparaciones)
    total = len(comparaciones)
    correctos = conteo["CORRECTO"]
    inventados = sum(
        x["conteo_atomico"].get("INVENTADO", 0) for x in comparaciones
    )
    resumen = {
        "campos_evaluados": total,
        "correctos": correctos,
        "incorrectos": conteo["INCORRECTO"],
        "parciales": conteo["PARCIAL"],
        "ausentes": conteo["AUSENTE"],
        "acierto_estricto": round(100 * correctos / total, 2),
        "cobertura": round(100 * (total - conteo["AUSENTE"]) / total, 2),
        "inventados": inventados,
    }
    base = cargar(RUTA_BASE)
    general = cargar(RUTA_GENERAL)["factura"].get("albaranes", [])
    literal = cargar(RUTA_LITERAL)["transcripcion"].get("filas", [])
    metricas_literal = cargar(RUTA_METRICAS_LITERAL)
    coste_literal = metricas_literal["coste_total_usd"]
    incidencias = cargar(RUTA_SALIDA / "incidencias.json")["incidencias"]
    albaranes = evaluar_albaranes(esperado.get("albaranes", []), obtenido.get("albaranes", []))
    salida = {
        "aislamiento": aislamiento,
        "antes_luna_general": base["resumen"],
        "despues_fedefarma_v1": resumen,
        "comparacion_fuentes_albaranes": {
            "general_luna_filas": len(general),
            "literal_luna_filas": len(literal),
            "normalizadas": len(obtenido.get("albaranes", [])),
        },
        "albaranes": albaranes,
        "llamada_literal": {
            "metricas": metricas_literal,
            "coste_60_facturas_fedefarma_mes_usd": round(coste_literal * 60, 2),
            "coste_60_facturas_fedefarma_anual_usd": round(coste_literal * 60 * 12, 2),
        },
        "cantidad_incidencias": len(incidencias),
        "incidencias": incidencias,
        "validaciones_monetarias": documento["validaciones_monetarias"],
        "comparaciones": comparaciones,
    }
    ruta_json = RUTA_SALIDA / "evaluacion_patron.json"
    ruta_md = RUTA_SALIDA / "evaluacion_patron.md"
    ruta_json.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    diferencias = [x for x in comparaciones if x["estado"] != "CORRECTO"]
    lineas = [
        "# Evaluacion independiente FEDEFARMA v1",
        "",
        f"- Luna general: {base['resumen']['correctos']}/22 correctos; "
        f"{base['resumen']['acierto_estricto']:.2f} %; "
        f"{base['resumen']['inventados']} invenciones.",
        f"- FEDEFARMA v1: {correctos}/{total} correctos; "
        f"{resumen['acierto_estricto']:.2f} %; cobertura {resumen['cobertura']:.2f} %; "
        f"{inventados} invenciones.",
        f"- Albaranes: general {len(general)}, literal {len(literal)}, normalizados "
        f"{len(obtenido.get('albaranes', []))}.",
        f"- Coste literal: {coste_literal:.6f} USD.",
        f"- Incidencias: {len(incidencias)}.",
        "",
        "## Resultado de albaranes",
        "",
        json.dumps(albaranes, ensure_ascii=False),
        "",
        "## Diferencias",
        "",
    ]
    lineas.extend(f"- `{x['campo']}`: {x['estado']}" for x in diferencias)
    ruta_md.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(json.dumps(albaranes, ensure_ascii=False, indent=2))
    return ruta_json, ruta_md


if __name__ == "__main__":
    evaluar()
